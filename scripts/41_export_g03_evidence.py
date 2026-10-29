"""G03（24 格矩阵）+ G02 固定 bootstrap 的证据导出与独立复算。

回答方案里的哪个问题："20 个机制代表格各自到底跑出了什么，能不能只用证据区重建？"
本脚本**不重跑**任何 rep，只做两件事：

1. 把两次 formal 跑的逐 rep 表、遥测、rep0 manifest、合并汇总、运行汇总、快照绑定、日志
   复制进 ``outputs/evidence/g03_formal/``（AGENTS §12.1：``out/`` 不入库）；
2. 用本文件自带的公式独立重算 4 个指标的 mean / sd / MC_SE 并与 34 号汇总表逐格比对，
   同时校验每格的 rep 覆盖、唯一性与正式状态；不一致即非零退出（§12.7，不静默跳过）。

用法::

    python scripts/41_export_g03_evidence.py            # 导出并复算
    python scripts/41_export_g03_evidence.py --check    # 只复算，不写盘
    # 夹具演练（指向 R=1 的 engineering 跑，只验证程序会正确报错）：
    python scripts/41_export_g03_evidence.py --check --matrix-root out/g03_r1 --fixed-root out/g03_r1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MATRIX_ROOT = ROOT / "out" / "g03_formal"
FIXED_ROOT = ROOT / "out" / "g02_fixed"
LOGS = ROOT / "out" / "g03_logs"
SNAPSHOT_BINDING = ROOT / "out" / "g03_snapshot" / "snapshot_binding.json"
DEST = ROOT / "outputs" / "evidence" / "g03_formal"
TABLES = ROOT / "outputs" / "tables"
BEIJING = timezone(timedelta(hours=8))

CORE_R = 500
TIER2_R = 30
RESAMPLES = 1000
PRIMARY_BUDGET = 0.2
METRICS = ("ate", "ate_test", "ate_paid_purchase_7d", "ate_any_refund_30d")
APPROVALS = {"matrix": "G03-FORMAL-20261029", "fixed": "G02-FORMAL-20261029"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def expected_cells() -> dict[str, str]:
    """格 → block。24 格是注册事实（4 core + 20 Tier2），不读代码常量，避免与执行器同源。"""
    core = ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"]
    tier2 = [
        "L0_Pi_heterogeneous_cost", "L0_zero_purchase_effect",
        "L1_heterogeneity_000", "L1_heterogeneity_150", "L1_signal_weak",
        "L1_misspec_omit_new_channel", "L1_mar_double", "L1_cost_prediction_under",
        "L2_n30000_p050", "L2_n100000_p050", "L2_drift_smooth",
        "L2_composition_shift", "L2_immature_negative_control",
        "L3_fixed_lt025", "L3_fixed_lt075", "L3_fixed_lt150",
        "L3_joint_lam000", "L3_joint_lam150", "L3_overlap_extreme",
        "L3_missing_confounders",
    ]
    return {**{c: "g_core" for c in core}, **{c: "g_tier2" for c in tier2}}


def cell_runs(root: Path, cell: str) -> list[Path]:
    return sorted(root.glob(f"shards/{cell}_s*/{cell}"))


def load_cell(root: Path, cell: str) -> tuple[pd.DataFrame, list[str]]:
    """把一格所有分片的逐 rep 表拼起来；分片之间 rep 重叠要响（17 号会静默去重）。"""
    problems: list[str] = []
    parts = []
    for part in cell_runs(root, cell):
        path = part / "repetitions.csv"
        if not path.is_file():
            provisional = part / "repetitions_provisional.csv"
            problems.append(
                f"{cell}: {part.name} 没有 repetitions.csv"
                + ("（只有 provisional）" if provisional.is_file() else "")
            )
            continue
        parts.append(pd.read_csv(path))
    if not parts:
        return pd.DataFrame(), problems or [f"{cell}: 找不到任何分片"]
    frame = pd.concat(parts, ignore_index=True)
    frame["rep"] = frame["rep"].astype(int)
    if frame["rep"].duplicated().any():
        dups = sorted(frame.loc[frame["rep"].duplicated(), "rep"].tolist())[:5]
        problems.append(f"{cell}: 分片间 rep 重叠 {dups}")
    return frame.sort_values("rep").reset_index(drop=True), problems


def check_cell(cell: str, block: str, frame: pd.DataFrame) -> list[str]:
    problems: list[str] = []
    want_r = CORE_R if block == "g_core" else TIER2_R
    if len(frame) != want_r:
        problems.append(f"{cell}: rows={len(frame)} != R={want_r}")
    if sorted(frame["rep"].tolist()) != list(range(want_r)):
        problems.append(f"{cell}: rep 不是 0..{want_r - 1}（缺口或越界）")
    for col in ("status", "protocol_config_hash", "n_total", "block", "tier"):
        values = frame[col].dropna().unique()
        if len(values) != 1:
            problems.append(f"{cell}: {col} 不唯一 {list(values)[:5]}")
    if len(values) == 1 and str(frame["status"].iloc[0]) != "formal":
        problems.append(f"{cell}: status={frame['status'].iloc[0]!r} 不是 formal")
    if str(frame["block"].iloc[0]) != block:
        problems.append(f"{cell}: block={frame['block'].iloc[0]!r} != {block}")
    if int(frame["validation_bootstrap_resamples"].fillna(0).max()) != 0:
        problems.append(f"{cell}: 矩阵臂不应带 bootstrap（found resamples>0）")
    return problems


def recompute(frame: pd.DataFrame, cell: str, block: str) -> list[dict]:
    rows = []
    r = int(len(frame))
    for metric in METRICS:
        values = frame[metric].astype(float)
        sd = float(values.std(ddof=1))
        rows.append({
            "cell_id": cell,
            "block": block,
            "metric": metric,
            "R": r,
            "mean": float(values.mean()),
            "sd": sd,
            "MC_SE": sd / math.sqrt(r) if r > 0 else float("nan"),
        })
    return rows


def compare_summary(recomputed: pd.DataFrame, summary_paths: list[Path]) -> list[str]:
    bad: list[str] = []
    existing = [p for p in summary_paths if p.is_file()]
    if not existing:
        return ["找不到 34 号正式汇总表（v3_g_g_core.csv / v3_g_g_tier2.csv 都不在）"]
    ref = pd.concat([pd.read_csv(p) for p in existing], ignore_index=True)
    ref = ref[~ref.get("provisional", False).astype(bool)]
    keys = ["cell_id", "metric"]
    merged = ref.set_index(keys)
    for _, row in recomputed.iterrows():
        key = (row["cell_id"], row["metric"])
        if key not in merged.index:
            bad.append(f"{key}: 汇总表缺行")
            continue
        ref_row = merged.loc[key]
        if int(ref_row["R"]) != int(row["R"]):
            bad.append(f"{key}: R {row['R']} != {int(ref_row['R'])}")
        for col in ("mean", "sd", "MC_SE"):
            a, b = float(row[col]), float(ref_row[col])
            if abs(a - b) > 1e-9 * max(1.0, abs(b)):
                bad.append(f"{key}/{col}: 复算 {a!r} != 汇总 {b!r}")
    return bad


def fixed_bootstrap_rows(root: Path) -> tuple[pd.DataFrame, list[str]]:
    problems: list[str] = []
    frames = []
    for cell in expected_cells():
        runs = cell_runs(root, cell)
        if len(runs) != 1:
            problems.append(f"{cell}: 固定 bootstrap 分片数 {len(runs)} != 1")
            continue
        path = runs[0] / "rep0" / "validation" / "fixed_bootstrap.csv"
        if not path.is_file():
            problems.append(f"{cell}: 缺 rep0/validation/fixed_bootstrap.csv")
            continue
        part = pd.read_csv(path)
        if len(part) != 1:
            problems.append(f"{cell}: fixed_bootstrap 行数 {len(part)} != 1")
        if not math.isclose(float(part["budget_cny_per_user"].iloc[0]), PRIMARY_BUDGET):
            problems.append(f"{cell}: budget={part['budget_cny_per_user'].iloc[0]} != 0.2")
        if int(part["resamples"].iloc[0]) != RESAMPLES:
            problems.append(f"{cell}: resamples={part['resamples'].iloc[0]} != {RESAMPLES}")
        if not (float(part["ci_low"].iloc[0]) <= float(part["point_diff"].iloc[0])
                <= float(part["ci_high"].iloc[0])):
            problems.append(f"{cell}: point_diff 不在 CI 内")
        part = part.copy()
        part.insert(0, "cell_id", cell)
        frames.append(part)
    if not frames:
        return pd.DataFrame(), problems or ["没有任何固定 bootstrap 结果"]
    return pd.concat(frames, ignore_index=True), problems


def _record(target: Path, dest_root: Path, source: Path, kind: str, note: str | None = None) -> dict:
    record = {
        "kind": kind,
        "target": (dest_root / target).relative_to(ROOT).as_posix(),
        "source": source.relative_to(ROOT).as_posix(),
        "bytes": target.stat().st_size,
        "sha256": sha256(target),
    }
    if note:
        record["note"] = note
    return record


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G03 + G02 固定 bootstrap 证据导出")
    parser.add_argument("--check", action="store_true", help="只复算并比对，不写盘")
    parser.add_argument("--matrix-root", type=Path, default=MATRIX_ROOT)
    parser.add_argument("--fixed-root", type=Path, default=FIXED_ROOT)
    parser.add_argument("--dest", type=Path, default=DEST)
    args = parser.parse_args(argv)

    matrix_root = args.matrix_root if args.matrix_root.is_absolute() else ROOT / args.matrix_root
    fixed_root = args.fixed_root if args.fixed_root.is_absolute() else ROOT / args.fixed_root
    dest = args.dest if args.dest.is_absolute() else ROOT / args.dest

    problems: list[str] = []
    frames: dict[str, pd.DataFrame] = {}
    recomputed: list[dict] = []
    for cell, block in expected_cells().items():
        frame, bad = load_cell(matrix_root, cell)
        problems.extend(bad)
        if frame.empty:
            continue
        problems.extend(check_cell(cell, block, frame))
        frames[cell] = frame
        recomputed.extend(recompute(frame, cell, block))
    recomputed_frame = pd.DataFrame(recomputed)

    fixed_frame, fixed_bad = fixed_bootstrap_rows(fixed_root)
    problems.extend(fixed_bad)

    summary_paths = [TABLES / "v3_g_g_core.csv", TABLES / "v3_g_g_tier2.csv"]
    problems.extend(compare_summary(recomputed_frame, summary_paths))

    for name, root in (("matrix", matrix_root), ("fixed", fixed_root)):
        summary_file = root / "run_summary.json"
        if not summary_file.is_file():
            problems.append(f"{name}: 缺 run_summary.json（未跑完）")
        else:
            payload = json.loads(summary_file.read_text(encoding="utf-8"))
            if payload.get("status") != "formal":
                problems.append(f"{name}: run_summary.status={payload.get('status')!r} != formal")
            if payload.get("failures"):
                problems.append(f"{name}: failures={payload['failures'][:3]}")
            if payload.get("bootstrap_resamples") != (RESAMPLES if name == "fixed" else 0):
                problems.append(
                    f"{name}: bootstrap_resamples={payload.get('bootstrap_resamples')!r} 不符"
                )

    print(f"[g03-ev] 矩阵 {matrix_root.relative_to(ROOT)}：{len(frames)}/24 格有逐 rep 表")
    print(f"[g03-ev] 固定 bootstrap：{len(fixed_frame)}/24 格")
    print(f"[g03-ev] 复算汇总 {len(recomputed_frame)} 行（4 指标 × 24 格 = 96）")
    if problems:
        print("[g03-ev] 校验未过，禁止导出：")
        for line in problems[:40]:
            print(f"  - {line}")
        if len(problems) > 40:
            print(f"  … 另有 {len(problems) - 40} 条")
        return 2
    print("[g03-ev] 校验全过")

    if args.check:
        return 0

    if dest.exists():
        backup = ROOT / "out" / "g03_evidence_bak"
        if backup.exists():
            shutil.rmtree(backup)
        dest.rename(backup)
        try:
            payload = _write_evidence(dest, matrix_root, fixed_root, frames, fixed_frame, recomputed_frame)
        except BaseException:
            if dest.exists():
                shutil.rmtree(dest)
            backup.rename(dest)
            raise
        shutil.rmtree(backup)
    else:
        payload = _write_evidence(dest, matrix_root, fixed_root, frames, fixed_frame, recomputed_frame)
    print(json.dumps({k: v for k, v in payload.items() if k != "records"},
                     ensure_ascii=False, indent=2))
    return 0


def _write_evidence(dest: Path, matrix_root: Path, fixed_root: Path,
                    frames: dict[str, pd.DataFrame], fixed_frame: pd.DataFrame,
                    recomputed: pd.DataFrame) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    def emit(source: Path, target: Path, kind: str, note: str | None = None) -> None:
        _copy(source, target)
        records.append(_record(target, dest, source, kind, note))

    for cell, frame in frames.items():
        candidates = cell_runs(matrix_root, cell)
        # 分片原件逐个导出（core 格被切成 10 片，只导合并件会让"合并是否忠实"不可核）
        for run in candidates:
            emit(run / "repetitions.csv",
                 dest / "per_cell" / "shards" / f"{cell}__{run.name}__repetitions.csv",
                 "g03_repetitions_shard", note=f"分片 {run.parent.name}")
            telemetry = run / "repetitions_telemetry.csv"
            if telemetry.is_file():
                emit(telemetry,
                     dest / "per_cell" / "shards" / f"{cell}__{run.name}__telemetry.csv",
                     "g03_telemetry_shard")
        merged = dest / "per_cell" / f"{cell}__repetitions.csv"
        merged.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(merged, index=False, encoding="utf-8-sig")
        records.append({
            "kind": "g03_repetitions_merged",
            "target": merged.relative_to(ROOT).as_posix(),
            "source": (matrix_root / "shards").relative_to(ROOT).as_posix(),
            "bytes": merged.stat().st_size,
            "sha256": sha256(merged),
            "rows": int(len(frame)),
            "note": (f"由 {len(candidates)} 个分片按 rep 排序拼接（分片原件同在 "
                     "per_cell/shards/；rep 重叠已在复算阶段拒绝）"),
        })

    fixed_path = dest / "fixed_bootstrap.csv"
    fixed_frame.to_csv(fixed_path, index=False, encoding="utf-8-sig")
    records.append({
        "kind": "g02_fixed_bootstrap_merged",
        "target": fixed_path.relative_to(ROOT).as_posix(),
        "source": fixed_root.relative_to(ROOT).as_posix(),
        "bytes": fixed_path.stat().st_size,
        "sha256": sha256(fixed_path),
        "rows": int(len(fixed_frame)),
        "note": "24 格 × rep 0 × 主预算 0.2 元 × 1000 次重抽；其余预算档未重抽样",
    })

    for cell in expected_cells():
        for tag, root in (("fixed", fixed_root), ("matrix", matrix_root)):
            runs = cell_runs(root, cell)
            if len(runs) != 1:
                continue
            manifest = runs[0] / "rep0" / "manifest.json"
            if manifest.is_file():
                emit(manifest, dest / "manifests" / f"{cell}__{tag}_rep0.json",
                     f"g03_{tag}_manifest")

    for name in ("v3_g_g_core.csv", "v3_g_g_tier2.csv"):
        source = TABLES / name
        if source.is_file():
            emit(source, dest / "summary" / name, "g03_summary")

    for tag, root in (("matrix", matrix_root), ("fixed", fixed_root)):
        summary = root / "run_summary.json"
        if summary.is_file():
            emit(summary, dest / "runs" / f"{tag}_run_summary.json", "g03_run_summary",
                 note=("G03 矩阵臂：24 格 × 注册 R（core 500 / Tier2 30），bootstrap 0"
                       if tag == "matrix" else
                       "G02 固定 bootstrap 臂：24 格 × rep 0，1000 次重抽，主预算 0.2"))

    if SNAPSHOT_BINDING.is_file():
        emit(SNAPSHOT_BINDING, dest / "binding" / "snapshot_binding.json", "g03_snapshot_binding",
             note="A/B 两阶段共用的 49 文件字节快照绑定")
    for log in ("chain.log", "g02_fixed.log", "g03.log", "chain.status"):
        source = LOGS / log
        if source.is_file():
            emit(source, dest / "logs" / log, "g03_log")

    recomputed_path = dest / "recomputed_summary.csv"
    recomputed.to_csv(recomputed_path, index=False, encoding="utf-8-sig")
    records.append({
        "kind": "g03_recomputed_summary",
        "target": recomputed_path.relative_to(ROOT).as_posix(),
        "source": "scripts/41_export_g03_evidence.py",
        "bytes": recomputed_path.stat().st_size,
        "sha256": sha256(recomputed_path),
        "rows": int(len(recomputed)),
    })

    total = sum(int(r["bytes"]) for r in records)
    payload = {
        "kind": "g03_evidence_coverage",
        "generated_at": now(),
        "cells": len(frames),
        "fixed_cells": len(fixed_frame),
        "records": records,
        "total_bytes": total,
    }
    (dest / "coverage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[g03-ev] 导出 {len(records)} 个文件 → {dest.relative_to(ROOT)}，共 {total} B")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
