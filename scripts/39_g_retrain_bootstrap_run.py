"""G02 再训练 bootstrap（参数化 DGP 重抽）：4 个 core 格 × 50 b = 200 次（裁决 A）。

语义（docs/v3_G执行器缺口与设计.md §6.1/§6.1.a）
-------------------------------------------------
每个 b 都从**已知 DGP** 重抽一个历史总体（`history_rep_id = RETRAIN_OFFSET + b`），
走完整链路：建历史五表 → SQL → 清洗 → 重训策略 → 在**冻结验证帧**上评估。
这不是对已观测历史的非参数 resample（`ObservedDataset` 与 SQL 输出逐字节绑定，
重抽观测表会直接破坏校验）；报告与表头一律写"参数化 bootstrap（已知 DGP 重抽）"。

验证帧固定：`VALIDATION_REP = 0`。`run_validation_arm` 的 `rep_id` 同时决定验证队列
与 bootstrap 种子，50 个 b 全传同一个值，并用 `validation_observed_hash` 断言逐字节相同。

用法::

    python scripts/39_g_retrain_bootstrap_run.py plan
    # 工程冒烟（小 n，跑 1 个 b）
    python scripts/39_g_retrain_bootstrap_run.py run --reps 1 --n 2000 \
        --out-root out/g02_retrain_smoke
    # 正式跑（必须带批准号 + 快照）
    python scripts/39_g_retrain_bootstrap_run.py run --status formal \
        --formal-approval "<登记号>" --snapshot out/g_snapshot \
        --overlay configs/budget/g02_reps50_overlay.yaml --out-root out/g02_retrain
    python scripts/39_g_retrain_bootstrap_run.py merge out/g02_retrain
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from causal_growth.evaluation.v3_g_matrix import (  # noqa: E402
    build_history_dataset,
    cell_meta,
    fit_history_models,
    load_budget_plan,
    plan_cell,
    require_job_semantics,
    run_validation_arm,
)
from causal_growth.estimate.v3_models import MODEL_NAMES  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")
RETRAIN_OFFSET = 1_000_000
VALIDATION_REP = 0
BOOTSTRAP_OVERLAY = ROOT / "configs" / "budget" / "g02_bootstrap_overlay.yaml"
ENGINEERING_MAX_REPS = 2
REQUIRED_BOOTSTRAP_KEYS = {
    "source_label", "retraining_bootstrap_total", "retraining_bootstrap_per_cell",
    "retraining_bootstrap_label", "fixed_bootstrap_resamples", "fixed_bootstrap_budget_scope",
}


def _now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(f"[G02 {datetime.now(BEIJING).strftime('%H:%M:%S')}] {message}", flush=True)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def core_cells(protocol) -> list[str]:
    """tier==1 且 roles 含 core+ate 的注册格；数量必须与 overlay 自校验一致。"""
    data = protocol.config.to_dict()
    cells = [
        s["id"] for s in data["scenarios"]
        if int(s["tier"]) == 1 and "core" in s["roles"] and "ate" in s["roles"]
    ]
    if not cells:
        raise SystemExit("注册表里没有 core 格")
    return cells


def read_bootstrap_overlay() -> dict:
    if not BOOTSTRAP_OVERLAY.is_file():
        raise SystemExit(f"缺少 {BOOTSTRAP_OVERLAY}")
    obj = yaml.safe_load(BOOTSTRAP_OVERLAY.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise SystemExit("bootstrap overlay 必须是 mapping")
    missing = sorted(REQUIRED_BOOTSTRAP_KEYS - set(obj))
    if missing:
        raise SystemExit(f"bootstrap overlay 缺键：{missing}")
    unknown = sorted(set(obj) - REQUIRED_BOOTSTRAP_KEYS)
    if unknown:
        raise SystemExit(f"bootstrap overlay 含未注册键：{unknown}")
    return obj


def check_counts(protocol, overlay: dict) -> tuple[list[str], int, int]:
    cells = core_cells(protocol)
    total = int(overlay["retraining_bootstrap_total"])
    per_cell = int(overlay["retraining_bootstrap_per_cell"])
    if per_cell * len(cells) != total:
        raise SystemExit(
            f"per_cell({per_cell}) × len(core)({len(cells)}) = {per_cell * len(cells)} ≠ total({total})"
        )
    if per_cell < 1:
        raise SystemExit("per_cell 必须为正")
    return cells, per_cell, total


def applicable_models(cfg) -> tuple[str, ...]:
    """与 `require_model_applicable` 同一口径：common ∪ additional_by_level[level]。

    必须显式给模型列表，不能传 None——`fit_history_models` 在 None 时会试全部模型，
    L0/L2 上的 dr_learner 会直接抛 ModelNotApplicableError（34 号也是显式传 --models）。
    """
    level = str(cfg.require("active_scenario.level"))
    additional = cfg.section("models.additional_by_level")
    if level not in additional:
        raise SystemExit(f"未注册层级 {level!r}；additional_by_level={sorted(additional)}")
    allowed = {str(n) for n in cfg.require("models.common")}
    allowed |= {str(n) for n in additional[level]}
    names = tuple(n for n in MODEL_NAMES if n in allowed)
    if not names:
        raise SystemExit(f"{level} 没有可用模型")
    return names


def _load_34():
    spec = importlib.util.spec_from_file_location(
        "g_matrix_run_34", ROOT / "scripts" / "34_g_matrix_run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate(*, status: str, approval: str | None, snapshot, allow_live: bool,
         reps: int | None, declared: int, n: int | None, registered_n: int) -> int:
    if status == "formal":
        if not approval:
            raise SystemExit("--status formal 必须带 --formal-approval（用户批准的登记号）")
        if snapshot is None and not allow_live:
            raise SystemExit(
                "正式跑必须提供 --snapshot；如确要 live 运行，"
                "设 CG_G02_ALLOW_LIVE_FORMAL=1 并自行承担 AGENTS §11 风险"
            )
        if n is not None and int(n) != int(registered_n):
            raise SystemExit(f"正式跑的 n 必须等于注册 n={registered_n}")
        target = declared if reps is None else int(reps)
        if target != declared:
            raise SystemExit(f"正式跑必须跑满 per_cell={declared}，收到 {target}")
        return target
    if reps is None:
        raise SystemExit("工程跑必须显式给 --reps（防止把 50 当成默认值误跑）")
    target = int(reps)
    if target < 1 or target > ENGINEERING_MAX_REPS:
        raise SystemExit(f"工程跑 reps 必须在 [1, {ENGINEERING_MAX_REPS}]")
    return target


def _row_path(cell_dir: Path) -> Path:
    return cell_dir / "repetitions.csv"


def _load_done(cell_dir: Path) -> pd.DataFrame:
    path = _row_path(cell_dir)
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def _append_row(cell_dir: Path, row: dict, columns: list[str]) -> None:
    cell_dir.mkdir(parents=True, exist_ok=True)
    path = _row_path(cell_dir)
    frame = pd.DataFrame([row]).loc[:, columns]
    if path.is_file():
        old = pd.read_csv(path)
        if set(old["b"]) & set(frame["b"]):
            raise RuntimeError(f"b={int(frame['b'].iloc[0])} 已存在，拒绝重复写入")
        frame = pd.concat([old, frame], ignore_index=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


ROW_COLUMNS = [
    "cell_id", "b", "history_rep_id", "validation_rep", "chosen_model",
    "policy_value", "decision_all_pass", "decision_lower_min",
    "guardrail_pass", "guardrail_upper",
    "n_history", "n_validation", "validation_observed_hash", "freeze_hash",
    "status", "config_hash", "protocol_config_hash", "overlay_sha256",
    "retraining_bootstrap_total", "cpu_seconds_history", "cpu_seconds_fit",
    "cpu_seconds_validation",
]


def run_one(protocol, cell_id: str, b: int, *, n: int | None, status: str,
            approval: str | None, plan, total: int, snapshot,
            policy: str = "greedy_incremental_profit_per_cost",
            models=None) -> dict:
    cfg = protocol.scenario(cell_id)
    require_job_semantics(cfg)
    spec = plan_cell(protocol, cell_id, plan)
    n_use = int(spec["n"] if n is None else n)
    history_rep_id = RETRAIN_OFFSET + int(b)
    run_id = f"g:{cell_id}:core:retrain:b{int(b)}"

    started = time.process_time()
    dataset, info, source_before = build_history_dataset(
        cfg, rep_id=history_rep_id, n=n_use, run_id=run_id
    )
    history_seconds = time.process_time() - started
    if snapshot is not None and dict(snapshot["source_hashes"]) != source_before:
        raise RuntimeError("当前树与快照绑定不一致，拒绝把结果登记为快照运行")

    fit_started = time.process_time()
    fit = fit_history_models(
        dataset, cfg, rep_id=history_rep_id,
        models=models or applicable_models(cfg), time_mode="static",
    )
    fit_seconds = time.process_time() - fit_started

    validation_started = time.process_time()
    validation = run_validation_arm(
        fit, cfg, rep_id=VALIDATION_REP, n_validation=n_use, policy=policy,
        target_dir=None, bootstrap_resamples=0, with_policy_value=True,
    )
    validation_seconds = time.process_time() - validation_started

    decision = validation["validation_decision"]
    guardrail = validation["validation_guardrail"]
    return {
        "cell_id": cell_id,
        "b": int(b),
        "history_rep_id": history_rep_id,
        "validation_rep": VALIDATION_REP,
        "chosen_model": str(fit.chosen_model),
        "policy_value": float(validation["validation_truth_policy_value"]),
        "decision_all_pass": bool(decision["passes_adjusted_test"].all()),
        "decision_lower_min": float(decision["adjusted_lower_confidence_limit"].min()),
        "guardrail_pass": bool(guardrail["passed"].iloc[0]),
        "guardrail_upper": float(guardrail["ci_one_sided_upper"].iloc[0]),
        "n_history": n_use,
        "n_validation": int(validation["validation_n"]),
        "validation_observed_hash": str(validation["validation_observed_hash"]),
        "freeze_hash": str(validation["validation_freeze_hash"]),
        "status": status,
        "config_hash": cfg.hash(64),
        "protocol_config_hash": protocol.config_hash,
        "overlay_sha256": plan.sha256 or "",
        "retraining_bootstrap_total": int(total),
        "cpu_seconds_history": history_seconds,
        "cpu_seconds_fit": fit_seconds,
        "cpu_seconds_validation": validation_seconds,
    }


def command_plan(args) -> int:
    protocol = load_v3_protocol()
    overlay = read_bootstrap_overlay()
    cells, per_cell, total = check_counts(protocol, overlay)
    plan = load_budget_plan(protocol, overlay=args.overlay)
    print(json.dumps({
        "bootstrap_kind": "parametric_dgp_redraw",
        "label": overlay["retraining_bootstrap_label"],
        "cells": cells,
        "per_cell": per_cell,
        "total": total,
        "retrain_offset": RETRAIN_OFFSET,
        "validation_rep": VALIDATION_REP,
        "budget_plan": plan.describe(),
        "registered_n": {c: int(cell_meta(protocol, c)["n"]) for c in cells},
        "eta_hours_at_240s": round(total * 240 / 3600, 1),
        "eta_hours_at_365s": round(total * 365 / 3600, 1),
        "eta_hours_at_670s": round(total * 670 / 3600, 1),
    }, ensure_ascii=False, indent=2))
    return 0


def command_run(args) -> int:
    protocol = load_v3_protocol()
    overlay = read_bootstrap_overlay()
    cells, per_cell, total = check_counts(protocol, overlay)
    if args.cells:
        wanted = [c.strip() for c in args.cells.split(",") if c.strip()]
        unknown = [c for c in wanted if c not in cells]
        if unknown:
            raise SystemExit(f"未注册的 core 格：{unknown}")
        cells = wanted
    plan = load_budget_plan(protocol, overlay=args.overlay)
    registered_n = min(int(cell_meta(protocol, c)["n"]) for c in cells)
    snapshot = None
    if args.snapshot is not None:
        g34 = _load_34()
        snapshot = g34._snapshot_from(args.snapshot)
        g34._verify_snapshot(snapshot, protocol)
    reps = gate(
        status=args.status, approval=args.formal_approval, snapshot=snapshot,
        allow_live=os.environ.get("CG_G02_ALLOW_LIVE_FORMAL") == "1",
        reps=args.reps, declared=per_cell, n=args.n, registered_n=registered_n,
    )
    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    out_root.mkdir(parents=True, exist_ok=True)
    _say(f"开始：{len(cells)} 格 × {reps} b；n={args.n or '注册值'}；out={out_root}")
    for cell_id in cells:
        cell_dir = out_root / cell_id
        done = _load_done(cell_dir)
        seen_hash = None if done.empty else str(done["validation_observed_hash"].iloc[0])
        for b in range(reps):
            if not done.empty and int(b) in set(done["b"].astype(int)):
                continue
            row = run_one(
                protocol, cell_id, b, n=args.n, status=args.status,
                approval=args.formal_approval, plan=plan, total=total, snapshot=snapshot,
                models=tuple(args.models) if args.models else None,
            )
            if seen_hash is not None and row["validation_observed_hash"] != seen_hash:
                raise RuntimeError(
                    f"{cell_id} b={b} 的验证帧哈希与 b=0 不同：验证帧被重抽了"
                )
            seen_hash = row["validation_observed_hash"]
            _append_row(cell_dir, row, ROW_COLUMNS)
            _say(
                f"{cell_id} b={b} (hist rep {row['history_rep_id']}) "
                f"model={row['chosen_model']} value={row['policy_value']:.4f} "
                f"cpu={row['cpu_seconds_history'] + row['cpu_seconds_fit'] + row['cpu_seconds_validation']:.0f}s"
            )
        state = {
            "phase": "G02_retrain_bootstrap",
            "bootstrap_kind": "parametric_dgp_redraw",
            "cell_id": cell_id,
            "status": args.status,
            "formal_approval": args.formal_approval,
            "per_cell": per_cell,
            "retraining_bootstrap_total": total,
            "retraining_bootstrap_per_cell": per_cell,
            "validation_rep": VALIDATION_REP,
            "retrain_offset": RETRAIN_OFFSET,
            "budget_plan": plan.describe(),
            "models": list(args.models) if args.models else "applicable_by_level",
            "snapshot_binding": dict(snapshot) if snapshot is not None else None,
            "completed_b": [int(x) for x in _load_done(cell_dir).get("b", [])],
            "updated_at": _now(),
        }
        (cell_dir / "run_state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    _say("完成本批")
    return 0


def command_merge(args) -> int:
    root = args.root if args.root.is_absolute() else ROOT / args.root
    overlay = read_bootstrap_overlay()
    protocol = load_v3_protocol()
    cells, per_cell, total = check_counts(protocol, overlay)
    rows = []
    for cell_id in cells:
        path = root / cell_id / "repetitions.csv"
        if not path.is_file():
            raise SystemExit(f"缺少 {path}")
        frame = pd.read_csv(path)
        if frame["b"].duplicated().any():
            raise SystemExit(f"{cell_id} 的 b 重复")
        if int(frame["validation_observed_hash"].nunique()) != 1:
            raise SystemExit(f"{cell_id} 的验证帧哈希不一致，拒绝合并")
        rows.append(frame)
    frame = pd.concat(rows, ignore_index=True)
    incomplete = {c: int((frame["cell_id"] == c).sum()) for c in cells}
    incomplete = {c: v for c, v in incomplete.items() if v != per_cell}
    suffix = "_provisional" if incomplete else ""
    if incomplete:
        print(f"  ⚠ 未跑满：{incomplete}（目标 {per_cell}/格）；写 {suffix} 副本，不得作为验收凭据")
    summary = []
    for cell_id in cells:
        part = frame[frame["cell_id"] == cell_id]
        values = part["policy_value"].to_numpy(dtype=float)
        n = int(values.size)
        mean = float(values.mean()) if n else float("nan")
        sd = float(values.std(ddof=1)) if n > 1 else float("nan")
        half = 1.96 * sd / math.sqrt(n) if n > 1 else float("nan")
        summary.append({
            "cell_id": cell_id,
            "b_count": n,
            "policy_value_mean": mean,
            "policy_value_sd": sd,
            "ci95_low": mean - half,
            "ci95_high": mean + half,
            "decision_pass_rate": float(part["decision_all_pass"].mean()) if n else float("nan"),
            "guardrail_pass_rate": float(part["guardrail_pass"].mean()) if n else float("nan"),
            "decision_lower_min_min": float(part["decision_lower_min"].min()) if n else float("nan"),
            "guardrail_upper_max": float(part["guardrail_upper"].max()) if n else float("nan"),
            "total_cpu_seconds": float(
                part[["cpu_seconds_history", "cpu_seconds_fit", "cpu_seconds_validation"]].sum().sum()
            ) if n else float("nan"),
        })
    tables = ROOT / "outputs" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    csv_path = tables / f"v3_phase_G02_retrain_bootstrap{suffix}.csv"
    pd.DataFrame(summary).to_csv(csv_path, index=False, encoding="utf-8-sig")
    meta = {
        "bootstrap_kind": "parametric_dgp_redraw",
        "bootstrap_label": overlay["retraining_bootstrap_label"],
        "source_label": overlay["source_label"],
        "retraining_bootstrap_total": total,
        "retraining_bootstrap_per_cell": per_cell,
        "validation_rep": VALIDATION_REP,
        "retrain_offset": RETRAIN_OFFSET,
        "cells": cells,
        "rows": int(len(frame)),
        "provisional": bool(incomplete),
        "merged_at": _now(),
        "table": csv_path.relative_to(ROOT).as_posix(),
    }
    (tables / f"v3_phase_G02_retrain_bootstrap{suffix}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G02 再训练 bootstrap（参数化 DGP 重抽）")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--overlay", default=None)

    p_run = sub.add_parser("run")
    p_run.add_argument("--status", choices=("engineering", "provisional", "formal"), default="engineering")
    p_run.add_argument("--formal-approval", default=None)
    p_run.add_argument("--snapshot", type=Path, default=None)
    p_run.add_argument("--overlay", default=None)
    p_run.add_argument("--out-root", type=Path, default=Path("out/g02_retrain"))
    p_run.add_argument("--reps", type=int, default=None)
    p_run.add_argument("--n", type=int, default=None)
    p_run.add_argument("--cells", default=None)
    p_run.add_argument("--models", nargs="*", default=None)

    p_merge = sub.add_parser("merge")
    p_merge.add_argument("root", type=Path)

    args = parser.parse_args(argv)
    if args.mode == "plan":
        return command_plan(args)
    if args.mode == "run":
        return command_run(args)
    return command_merge(args)


if __name__ == "__main__":
    raise SystemExit(main())
