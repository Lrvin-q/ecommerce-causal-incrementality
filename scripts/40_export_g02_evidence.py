"""G02（重训 bootstrap 200 次）证据导出与独立复算。

回答方案里的哪个问题："策略价值不是靠单次拟合碰运气——把 DGP 重抽 200 次，
决策与护栏的通过率还稳不稳？" 本脚本**不重跑**任何 b，只做两件事：

1. 把 4 个 core 格的逐 b 表、run_state、快照绑定、合并表与日志按字节复制进
   ``outputs/evidence/g02_formal/``，让"只用证据区就能重建关键数字"成立（AGENTS §12.1）；
2. 用本文件自带的公式**独立重算**每格的 mean / sd / 95% CI / 通过率 / 极值，
   与 39 号合并表逐格比对；不一致即非零退出（§12.7，不静默跳过）。

用法::

    python scripts/40_export_g02_evidence.py            # 导出并复算
    python scripts/40_export_g02_evidence.py --check    # 只复算，不写盘
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "out" / "g02_retrain"
LOG_ROOT = ROOT / "out" / "g02_logs"
SNAPSHOT_BINDING = ROOT / "out" / "g02_snapshot" / "snapshot_binding.json"
DEST = ROOT / "outputs" / "evidence" / "g02_formal"
TABLES = ROOT / "outputs" / "tables"
MERGE_CSV = TABLES / "v3_phase_G02_retrain_bootstrap.csv"
MERGE_JSON = TABLES / "v3_phase_G02_retrain_bootstrap.json"
APPROVAL = "G02-FORMAL-20261029"
PER_CELL = 50
TOTAL_B = 200
BEIJING = timezone(timedelta(hours=8))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def load_cells() -> list[str]:
    cells = sorted(p.name for p in RUN_ROOT.iterdir() if (p / "repetitions.csv").is_file())
    if len(cells) != 4:
        raise SystemExit(f"应有 4 个 core 格，实际 {cells}")
    return cells


def check_cell(cell: str) -> tuple[pd.DataFrame, list[str]]:
    problems: list[str] = []
    if not (RUN_ROOT / cell / "run_state.json").is_file():
        problems.append(f"{cell}: 缺 run_state.json（未跑完）")
    frame = pd.read_csv(RUN_ROOT / cell / "repetitions.csv")
    if len(frame) != PER_CELL:
        problems.append(f"{cell}: rows={len(frame)} != {PER_CELL}")
    if sorted(frame["b"].astype(int)) != list(range(PER_CELL)):
        problems.append(f"{cell}: b 不是 0..{PER_CELL - 1}")
    if frame["b"].duplicated().any():
        problems.append(f"{cell}: b 重复")
    # 冻结指纹只查与模型无关的两列；validation_observed_hash 含 issued_action，跨 b 本就该变。
    for col in ("validation_frame_hash", "validation_arm_hash"):
        if col not in frame.columns:
            problems.append(f"{cell}: 缺 {col}（旧版 39 号的表，不能作为正式证据）")
        elif int(frame[col].nunique()) != 1:
            problems.append(f"{cell}: {col} 在 b 间不一致（验证队列/随机化臂被重抽）")
    for col in ("status", "protocol_config_hash", "n_history", "n_validation",
                "retraining_bootstrap_total"):
        values = frame[col].dropna().unique()
        if len(values) != 1:
            problems.append(f"{cell}: {col} 不唯一 {values[:5]}")
    for col in ("history_rep_id", "validation_rep"):
        if frame[col].duplicated().any():
            problems.append(f"{cell}: {col} 在 b 间重复")
    return frame, problems


def summarize(frame: pd.DataFrame) -> dict:
    values = frame["policy_value"].to_numpy(dtype=float)
    n = int(values.size)
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    half = 1.96 * sd / math.sqrt(n)
    return {
        "cell_id": str(frame["cell_id"].iloc[0]),
        "b_count": n,
        "policy_value_mean": mean,
        "policy_value_sd": sd,
        "ci95_low": mean - half,
        "ci95_high": mean + half,
        "decision_pass_rate": float(frame["decision_all_pass"].astype(float).mean()),
        "guardrail_pass_rate": float(frame["guardrail_pass"].astype(float).mean()),
        "decision_lower_min_min": float(frame["decision_lower_min"].min()),
        "guardrail_upper_max": float(frame["guardrail_upper"].max()),
        "total_cpu_seconds": float(
            frame[["cpu_seconds_history", "cpu_seconds_fit", "cpu_seconds_validation"]]
            .sum().sum()
        ),
    }


def compare(recomputed: pd.DataFrame) -> list[str]:
    merged = pd.read_csv(MERGE_CSV).set_index("cell_id")
    bad: list[str] = []
    for _, row in recomputed.iterrows():
        cell = row["cell_id"]
        if cell not in merged.index:
            bad.append(f"{cell}: 合并表缺行")
            continue
        ref = merged.loc[cell]
        if int(ref["b_count"]) != int(row["b_count"]):
            bad.append(f"{cell}: b_count {row['b_count']} != {int(ref['b_count'])}")
        for key in ("policy_value_mean", "policy_value_sd", "ci95_low", "ci95_high",
                    "decision_pass_rate", "guardrail_pass_rate",
                    "decision_lower_min_min", "guardrail_upper_max", "total_cpu_seconds"):
            if abs(float(ref[key]) - float(row[key])) > 1e-12:
                bad.append(f"{cell}: {key} {row[key]} != 合并 {ref[key]}")
    if int(merged["b_count"].sum()) != TOTAL_B:
        bad.append(f"合并表 b 合计 {int(merged['b_count'].sum())} != {TOTAL_B}")
    return bad


def write_evidence(cells: list[str], recomputed: pd.DataFrame) -> dict:
    """写进 staging，校验 coverage.json 可解析后再原子替换；不删任何旧备份。

    37 号曾因"先 rmtree 再写"删空证据区；G01 复评又指出"先删旧备份"会在二次故障时
    用半写副本覆盖完好副本。这里两条都避开：DEST 只通过完整 staging 改名出现，
    旧 DEST 改名为带时间戳的备份（不删），失败时 DEST 原样保留、异常原样抛出。
    """
    global DEST
    real = DEST
    staging = ROOT / "out" / "g02_evidence_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    DEST = staging
    try:
        payload = _write_evidence(cells, recomputed)
        json.loads((staging / "coverage.json").read_text(encoding="utf-8"))
    except BaseException:
        DEST = real
        raise
    DEST = real
    if real.exists():
        stamp = datetime.now(BEIJING).strftime("%Y%m%d%H%M%S")
        real.rename(ROOT / "out" / f"g02_evidence_bak_{stamp}")
    staging.rename(real)
    return payload


def _write_evidence(cells: list[str], recomputed: pd.DataFrame) -> dict:
    for sub in ("per_cell", "binding", "merged", "logs"):
        (DEST / sub).mkdir(parents=True, exist_ok=True)

    records: list[dict] = []

    def record(path: Path, kind: str | None = None, note: str = "",
               source: Path | None = None) -> None:
        entry: dict = {
            "path": path.relative_to(DEST).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if kind:
            entry["kind"] = kind
        if source is not None:
            entry["source"] = source.as_posix()
        if note:
            entry["note"] = note
        if path.suffix == ".csv":
            entry["rows"] = int(len(pd.read_csv(path)))
        records.append(entry)

    runs = []
    for cell in cells:
        for src, name, kind in (
            (RUN_ROOT / cell / "repetitions.csv", f"{cell}__repetitions.csv", "g02_per_b_table"),
            (RUN_ROOT / cell / "run_state.json", f"{cell}__run_state.json", "g02_run_state"),
        ):
            target = DEST / "per_cell" / name
            shutil.copy2(src, target)
            record(target, kind=kind, source=src, note=f"core 格 {cell}")
        state = json.loads((RUN_ROOT / cell / "run_state.json").read_text(encoding="utf-8"))
        runs.append({
            "cell_id": cell,
            "b_count": len(state.get("completed_b", [])),
            "run_state_updated_at": state.get("updated_at"),
            "status": state.get("status"),
            "snapshot_binding": state.get("snapshot_binding"),
            "files": [f"per_cell/{cell}__repetitions.csv", f"per_cell/{cell}__run_state.json"],
        })

    shutil.copy2(SNAPSHOT_BINDING, DEST / "binding" / "snapshot_binding.json")
    record(DEST / "binding" / "snapshot_binding.json", kind="g02_snapshot_binding",
           source=SNAPSHOT_BINDING,
           note="正式跑源码字节绑定；39 号运行前已与真树逐文件比对")

    for src, name in ((MERGE_CSV, "v3_phase_G02_retrain_bootstrap.csv"),
                      (MERGE_JSON, "v3_phase_G02_retrain_bootstrap.json")):
        target = DEST / "merged" / name
        shutil.copy2(src, target)
        record(target, kind="g02_merged_summary", source=src)

    for cell in cells:
        src = LOG_ROOT / f"{cell}.log"
        if not src.is_file():
            raise SystemExit(f"缺日志：{src}")
        target = DEST / "logs" / f"{cell}.log"
        shutil.copy2(src, target)
        record(target, kind="g02_run_log", source=src,
               note="日志行只有时分秒、无日期；权威日期见 runs_summary.json 的 note")
    post_log = LOG_ROOT / "post.log"
    if post_log.is_file():
        shutil.copy2(post_log, DEST / "logs" / "post.log")
        record(DEST / "logs" / "post.log", kind="g02_post_log", source=post_log)

    recomputed.to_csv(DEST / "recomputed_bootstrap.csv", index=False,
                      encoding="utf-8-sig", lineterminator="\n")
    record(DEST / "recomputed_bootstrap.csv", kind="g02_recomputed",
           note="本脚本独立重算（不读 39 的 summarize 函数）")

    runs_summary = {
        "kind": "g02_runs_summary",
        "source_label": "合成数据 / 已知 DGP",
        "approval": APPROVAL,
        "cells": runs,
        "total_b": sum(r["b_count"] for r in runs),
        "finished_at_max": max(
            (r["run_state_updated_at"] for r in runs if r["run_state_updated_at"]),
            default=None,
        ),
        "note": (
            "开始时刻 2026-10-29T10:09:04+08:00 来自 out/g02_logs/*.log 首行（行内无日期，"
            "日期由运行注册表与文件 mtime 佐证）；每格完成时刻取 run_state.updated_at。"
        ),
    }
    (DEST / "runs_summary.json").write_text(
        json.dumps(runs_summary, ensure_ascii=False, indent=2).replace("\n", "\r\n"),
        encoding="utf-8", newline="")
    record(DEST / "runs_summary.json", kind="g02_runs_summary")

    payload = {
        "source_label": "合成数据 / 已知 DGP",
        "purpose": "g02_retrain_bootstrap_formal_evidence",
        "exported_at": now(),
        "approval": APPROVAL,
        "status": "formal",
        "declared_per_cell": PER_CELL,
        "declared_total": TOTAL_B,
        "cells": cells,
        "files": records,
    }
    (DEST / "coverage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2).replace("\n", "\r\n"),
        encoding="utf-8", newline="")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G02 证据导出与独立复算")
    parser.add_argument("--check", action="store_true", help="只复算并比对，不写盘")
    args = parser.parse_args(argv)

    cells = load_cells()
    problems: list[str] = []
    frames = []
    for cell in cells:
        frame, bad = check_cell(cell)
        problems.extend(bad)
        frames.append(frame)
    if problems:
        for line in problems:
            print("  ! " + line)
        return 1
    data = pd.concat(frames, ignore_index=True)
    recomputed = pd.DataFrame([summarize(f) for f in frames]).sort_values("cell_id")
    mismatches = compare(recomputed)
    for line in mismatches:
        print("  ! " + line)
    print(recomputed.to_string(index=False))
    if mismatches:
        return 1
    print(f"复算一致：4 格 × {PER_CELL} b = {len(data)} 行；合并表逐格 max|Δ| ≤ 1e-12")
    if args.check:
        print("CHECK ONLY：不写盘")
        return 0
    payload = write_evidence(cells, recomputed)
    print(f"导出 {len(payload['files'])} 个文件 -> {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
