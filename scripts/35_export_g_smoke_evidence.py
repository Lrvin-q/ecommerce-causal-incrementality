"""把 G 阶段 A10 小规模验证跑的产物导出到 ``outputs/evidence/g_smoke/``（可入库）。

为什么需要（2026-10-28 20:45，北京时间）
--------------------------------------
任务书 §11 要求：R=3、2 格的工程跑产物落 ``outputs/tables/``，并能只凭
``outputs/evidence/`` 复算关键数字。``out/`` 被 .gitignore 忽略（AGENTS §12.1），
不导出等于评审者拿不到逐 rep 表、冻结、manifest 与快照绑定。

导出内容
--------
- ``per_cell/<cell>_repetitions_provisional.csv``  逐 rep 行（工程运行未跑满 → provisional）
- ``per_cell/<cell>_repetitions_telemetry.csv``    CPU 遥测（与上面分文件，见 A2）
- ``manifests/<cell>_rep0_manifest.json``          源码绑定 / 构建次数 / R / 真值隔离标记
- ``frozen/<cell>/freeze.json``                    策略名单冻结（写于真值之前）
- ``validation/<cell>_rep0_*.csv``                 验证臂：名单、决策、护栏、ITT 对比、真值汇总
- ``snapshot_binding.json``                        49 文件字节快照的绑定哈希
- ``run_summary.json``                             合并计数（rows_raw / rows_deduped / 重复数）
- ``summaries/<table>.csv``                        ``outputs/tables/`` 的两张 provisional 汇总
- ``coverage.json``                                每条 sha256/bytes + 从文件反算的关键数字

三道自检（只准加强，不准削弱）
------------------------------
1. 源文件缺失 → 硬失败，一次列出全部缺项（不逐个撞墙）；
2. 写盘后逐条重算 sha256/bytes，与登记值不符即失败；
3. 证据目录内所有身份类 JSON（``*binding*`` / ``*manifest*`` / ``freeze.json`` /
   ``meta*`` / ``decision.json``）必须被 ``coverage.json`` 登记，漏登记即失败
   （AGENTS §12.7：索引与磁盘双向校验）。

用法::

    .venv/Scripts/python.exe scripts/35_export_g_smoke_evidence.py --dry-run
    .venv/Scripts/python.exe scripts/35_export_g_smoke_evidence.py
    .venv/Scripts/python.exe scripts/35_export_g_smoke_evidence.py --force
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "out" / "g_smoke"
SNAPSHOT_ROOT = ROOT / "out" / "g_smoke_snapshot"
TARGET = ROOT / "outputs" / "evidence" / "g_smoke"
BEIJING = ZoneInfo("Asia/Shanghai")

CELLS: tuple[str, ...] = ("L1_main", "L0_Pi_heterogeneous_cost")
VALIDATION_CSVS: tuple[str, ...] = (
    "policy_list.csv", "decision.csv", "arm_summary.csv", "itt_contrasts.csv",
    "guardrail.csv", "truth_arm_means.csv", "truth_arm_contrasts.csv",
    "truth_policy_values.csv",
)
SUMMARY_TABLES: tuple[str, ...] = (
    "v3_g_g_core_provisional.csv", "v3_g_g_tier2_provisional.csv",
)
IDENTITY_PATTERNS: tuple[str, ...] = (
    "*binding*.json", "*manifest*.json", "freeze.json", "meta*.json", "decision.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def plan() -> list[tuple[Path, str]]:
    """(源, 证据目录内相对路径)；顺序固定，便于逐次比对。"""
    items: list[tuple[Path, str]] = [
        (RUN_ROOT / "run_summary.json", "run_summary.json"),
        (SNAPSHOT_ROOT / "snapshot_binding.json", "snapshot_binding.json"),
    ]
    for cell in CELLS:
        items.append((
            RUN_ROOT / "_final" / cell / "repetitions_provisional.csv",
            f"per_cell/{cell}_repetitions_provisional.csv",
        ))
        items.append((
            RUN_ROOT / "_final" / cell / "repetitions_telemetry.csv",
            f"per_cell/{cell}_repetitions_telemetry.csv",
        ))
        rep0 = RUN_ROOT / "shards" / f"{cell}_s0000" / cell / "rep0"
        items.append((rep0 / "manifest.json", f"manifests/{cell}_rep0_manifest.json"))
        items.append((rep0 / "validation" / "freeze.json", f"frozen/{cell}/freeze.json"))
        for name in VALIDATION_CSVS:
            items.append((rep0 / "validation" / name, f"validation/{cell}_rep0_{name}"))
    for name in SUMMARY_TABLES:
        items.append((ROOT / "outputs" / "tables" / name, f"summaries/{name}"))
    return items


def _is_identity(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pat) for pat in IDENTITY_PATTERNS)


def _kind(rel: str) -> str:
    """33 号脚本要求身份类记录自带 kind；非身份类也给一个便于人读的类型。"""
    if rel == "snapshot_binding.json":
        return "g_a10_snapshot_binding"
    if rel.startswith("manifests/"):
        return "g_a10_manifest"
    if rel.endswith("/freeze.json"):
        return "g_a10_freeze"
    if rel == "run_summary.json":
        return "g_a10_run_summary"
    if rel.startswith("per_cell/") and rel.endswith("_telemetry.csv"):
        return "g_a10_telemetry"
    if rel.startswith("per_cell/"):
        return "g_a10_repetitions"
    if rel.startswith("validation/"):
        return "g_a10_validation_csv"
    if rel.startswith("summaries/"):
        return "g_a10_summary"
    return "g_a10_other"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _key_numbers(items: list[tuple[Path, str]]) -> dict:
    """全部从**导出后的文件**反算，不手抄任何数字。"""
    run = json.loads((TARGET / "run_summary.json").read_text(encoding="utf-8"))
    numbers: dict[str, object] = {
        "run": {
            "status": run.get("status"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "rows_raw": run["merged"]["rows_raw"],
            "rows_deduped": run["merged"]["rows_deduped"],
            "duplicates_removed": run["merged"]["duplicates_removed"],
            "merge_key": run["merged"]["key"],
            "all_complete": run["all_complete"],
            "failures": run.get("failures", []),
        },
        "cells": {},
    }
    for cell in CELLS:
        rows = _read_csv(TARGET / f"per_cell/{cell}_repetitions_provisional.csv")
        telemetry = _read_csv(TARGET / f"per_cell/{cell}_repetitions_telemetry.csv")
        manifest = json.loads(
            (TARGET / f"manifests/{cell}_rep0_manifest.json").read_text(encoding="utf-8")
        )
        freeze = json.loads(
            (TARGET / f"frozen/{cell}/freeze.json").read_text(encoding="utf-8")
        )
        numbers["cells"][cell] = {
            "reps": sorted(int(row["rep"]) for row in rows),
            "n": int(rows[0]["n"]),
            "ate": [float(row["ate"]) for row in rows],
            "ate_se": [float(row["ate_se"]) for row in rows],
            "chosen_model": [row["chosen_model"] for row in rows],
            "observed_hash_without_run_id": [row["observed_hash_without_run_id"] for row in rows],
            "status": [row["status"] for row in rows],
            "R_ate": manifest["R_ate"],
            "R_learn": manifest["R_learn"],
            "R_validation": manifest["R_validation"],
            "history_pipeline_builds": [
                int(row["history_pipeline_builds"]) for row in rows
            ],
            "validation_pipeline_builds": [
                int(row["validation_pipeline_builds"]) for row in rows
            ],
            "truth_columns_present": manifest["truth_columns_present"],
            "budget_plan_source": manifest["budget_plan"].get("source"),
            "snapshot_source_hashes_sha256": manifest["snapshot_binding"].get(
                "source_hashes_sha256"
            ),
            "freeze_written_before_truth": freeze["freeze_written_before_truth"],
            "freeze_hash": freeze["freeze_hash"],
            "cpu_seconds": {
                key: [float(row[key]) for row in telemetry]
                for key in ("cpu_seconds_pipeline", "cpu_seconds_estimate",
                            "cpu_seconds_models")
            },
        }
    summaries: dict[str, dict] = {}
    for name in SUMMARY_TABLES:
        for row in _read_csv(TARGET / f"summaries/{name}"):
            cell = row["cell_id"]
            summaries.setdefault(cell, {})[row["metric"]] = {
                "R": int(row["R"]), "MC_SE": float(row["MC_SE"]),
                "mean": float(row["mean"]), "provisional": row["provisional"] == "True",
            }
    numbers["summaries"] = summaries
    numbers["sources"] = {rel: _rel(src) for src, rel in items}
    return numbers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出 G 阶段 A10 工程跑证据")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="目标已存在且字节不同时仍覆盖（默认拒绝）")
    args = parser.parse_args(argv)

    items = plan()
    missing = [str(src) for src, _ in items if not src.is_file()]
    if missing:
        print("源文件缺失（先跑 34 号工程跑）：", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 2

    conflicts = [
        rel for src, rel in items
        if (TARGET / rel).is_file() and (TARGET / rel).read_bytes() != src.read_bytes()
    ]
    if conflicts and not args.force:
        print("目标已存在且字节不同（证据不可静默改写；确认来源后加 --force）：", file=sys.stderr)
        for rel in conflicts:
            print(f"  - {rel}", file=sys.stderr)
        return 2

    print(f"待导出 {len(items)} 个文件 -> {_rel(TARGET)}")
    for src, rel in items:
        print(f"  {_rel(src)}  ->  {rel}  ({src.stat().st_size} B)")
    if args.dry_run:
        return 0

    TARGET.mkdir(parents=True, exist_ok=True)
    records = []
    for src, rel in items:
        dest = TARGET / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        records.append({
            "path": rel, "kind": _kind(rel), "source": _rel(src),
            "sha256": _sha256(dest), "bytes": dest.stat().st_size,
        })

    numbers = _key_numbers(items)
    coverage = {
        "phase": "G_A10_engineering_smoke",
        "status": "engineering_smoke",
        "created_at": datetime.now(BEIJING).isoformat(timespec="seconds"),
        "representative_rep_dir": "out/g_smoke/shards/<cell>_s0000/<cell>/rep0",
        "files": records,
        "key_numbers": numbers,
        "note": (
            "工程小规模验证跑（R=3、n=2000、constant 单模型），不是正式 G 结果；"
            "逐 rep 表为 provisional，R 以 manifest 的 R_ate/R_learn/R_validation 为准。"
            "CPU 计时单列 repetitions_telemetry.csv，因为计时无法逐字节复现（A2）。"
        ),
    }
    coverage_path = TARGET / "coverage.json"
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8", newline="\r\n"
    )

    # 自检 2：逐条重算 sha256/bytes
    bad = []
    for record in records:
        dest = TARGET / record["path"]
        if _sha256(dest) != record["sha256"] or dest.stat().st_size != record["bytes"]:
            bad.append(record["path"])
    # 自检 3：身份类 JSON 必须全部登记
    registered = {record["path"] for record in records}
    for path in sorted(TARGET.rglob("*.json")):
        rel = path.relative_to(TARGET).as_posix()
        if rel == "coverage.json":
            continue
        if _is_identity(path) and rel not in registered:
            bad.append(f"未登记的身份类 JSON: {rel}")
            continue
        if not _is_identity(path) and rel not in registered:
            bad.append(f"未登记的 JSON: {rel}")
    if bad:
        print("导出自检失败：", file=sys.stderr)
        for item in bad:
            print(f"  - {item}", file=sys.stderr)
        return 2

    print(f"导出完成：{len(records)} 条，sum(bytes)={sum(r['bytes'] for r in records)}")
    print(f"coverage：{_rel(coverage_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
