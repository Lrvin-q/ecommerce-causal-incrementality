"""把 D01 pilot 的运行凭据与逐 rep 表导出到 ``outputs/evidence/d01_pilot/``。

为什么需要它（2026-10-28 21:20，北京时间）
------------------------------------------
D01 独立评审的 P1-5：唯一带 ``START``/``EXIT=0``/``END`` 的证据在 ``out/logs/``，
而 ``.gitignore`` 忽略整个 ``out/``；``coverage.json`` 74 条里 0 条 D01。
tracked 的 CSV/summary 能重建统计量，但重建不了"谁在何时以什么命令跑完 20 rep"。

导出什么
--------
- 两份运行日志（20 rep 主作业 + L0/L3 各 1 rep 补测）；
- 4 张逐 rep 表与 4 份 summary（r20 / L0 / L3）；
- ``run_manifest.json``：命令、START/END/EXIT、主机、行数、sha256、关键派生值；
- ``coverage.json``：目录级索引（33 号脚本据此把身份类 JSON 提升进顶层登记表）。

纪律
----
- 源文件缺失一律 exit 2 并列出全部缺失项，不静默跳过；
- 目标已存在且字节不同 → exit 2（``--force`` 才覆盖），避免"导出物被悄悄改写"；
- 写盘后重算 sha256/bytes 与索引对照；关键数字全部从**导出后的文件**反算。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "outputs" / "evidence" / "d01_pilot"

LOGS: tuple[tuple[str, str], ...] = (
    ("out/logs/d01_pilot_20261028_1651.log", "logs/d01_pilot_20261028_1651.log"),
    ("out/logs/d01_l0_l3_20261028_1848.log", "logs/d01_l0_l3_20261028_1848.log"),
)
TABLES: tuple[str, ...] = (
    "v3_phase_D_pilot_raw_r20.csv",
    "v3_phase_D_pilot_summary_r20.json",
    "v3_phase_D_pilot_raw_L0_r1.csv",
    "v3_phase_D_pilot_summary_L0_r1.json",
    "v3_phase_D_pilot_raw_L3_r1.csv",
    "v3_phase_D_pilot_summary_L3_r1.json",
)
SUMMARY_TABLE = "outputs/tables"
RECIPE = "pilot_cost_table_v1"
#: 5 模型参照来自 D03 正式实测（docs/v3_phase_D03_formal.md §1：rep 0 = 308.1 s、rep 199 = 303.2 s）。
FIVE_MODEL_REF_S = (303.2, 308.1)
COUNTS = {
    "historical_dgp_jobs": 9_500,
    "full_learning_data_jobs": 7_300,
    "independent_validation_jobs": 7_300,
    "complete_aa_jobs": 1_000,
    "additional_design_power_jobs": 2_000,
    "retraining_bootstrap_jobs": 800,
}
EXTERNAL_RETRAINING_S = 476.1


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_log(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    start = re.search(r"^START (.+)$", text, re.MULTILINE)
    end = re.search(r"^END (.+)$", text, re.MULTILINE)
    exit_code = re.search(r"^EXIT=(-?\d+)$", text, re.MULTILINE)
    reps = [int(value) for value in re.findall(r"^\[pilot\] rep=(\d+)", text, re.MULTILINE)]
    return {
        "start": start.group(1).strip() if start else None,
        "end": end.group(1).strip() if end else None,
        "exit": int(exit_code.group(1)) if exit_code else None,
        "rep_blocks": reps,
        "failed_lines": len(re.findall(r"FAILED", text)),
    }


def _key_numbers() -> dict[str, object]:
    """全部从导出后的文件反算，不手抄任何数字。"""
    raw = _read_rows(TARGET / "tables" / "v3_phase_D_pilot_raw_r20.csv")
    summary = json.loads((TARGET / "tables" / "v3_phase_D_pilot_summary_r20.json").read_text(encoding="utf-8"))
    l0 = json.loads((TARGET / "tables" / "v3_phase_D_pilot_summary_L0_r1.json").read_text(encoding="utf-8"))
    l3 = json.loads((TARGET / "tables" / "v3_phase_D_pilot_summary_L3_r1.json").read_text(encoding="utf-8"))

    reps = sorted(int(row["rep"]) for row in raw)
    cpu_ratio = [float(row["G3_full_with_cf_s"]) / float(row["elapsed_wall_s"]) for row in raw]
    whole_ratio = [float(row["G3_plus_dgp_s"]) / float(row["elapsed_wall_s"]) for row in raw]
    mean_g2 = float(summary["mean_G2_tables_sql_estimation_s"])
    mean_cf = float(summary["mean_cf_s"])
    derived_validation_s = mean_g2 - mean_cf

    def total_hours(validation_s: float, learning_s: float) -> float:
        return (
            COUNTS["historical_dgp_jobs"] * 0.406
            + COUNTS["full_learning_data_jobs"] * learning_s
            + COUNTS["independent_validation_jobs"] * validation_s
            + COUNTS["complete_aa_jobs"] * validation_s
            + COUNTS["additional_design_power_jobs"] * validation_s
            + COUNTS["retraining_bootstrap_jobs"] * EXTERNAL_RETRAINING_S
        ) / 3600.0

    learning_s = mean_g2
    lower = total_hours(derived_validation_s, learning_s)
    five_model = [
        total_hours(derived_validation_s, reference) for reference in FIVE_MODEL_REF_S
    ]

    def rel(value: float, base: float) -> float:
        return (value - base) / base

    return {
        "rows": len(raw),
        "rep_min": reps[0],
        "rep_max": reps[-1],
        "rep_gaps": [rep for rep in range(reps[0], reps[-1] + 1) if rep not in reps],
        "failed": int(summary["failed"]),
        "mean_G1_s": summary["mean_G1_estimation_s"],
        "mean_G2_s": mean_g2,
        "mean_G3_s": summary["mean_G3_full_with_cf_s"],
        "mean_G3_plus_dgp_s": summary["mean_G3_plus_dgp_s"],
        "mean_wall_s": summary["mean_wall_s"],
        "mean_cf_cpu_s": mean_cf,
        "derived_validation_cpu_s": round(derived_validation_s, 4),
        "cpu_over_wall_mean": round(sum(cpu_ratio) / len(cpu_ratio), 6),
        "cpu_over_wall_min": round(min(cpu_ratio), 6),
        "cpu_over_wall_max": round(max(cpu_ratio), 6),
        "whole_rep_cpu_over_wall_mean": round(sum(whole_ratio) / len(whole_ratio), 6),
        "total_cpu_h_lower": round(lower, 2),
        "total_cpu_h_five_model": [round(value, 2) for value in five_model],
        "counts": COUNTS,
        "external_retraining_s": EXTERNAL_RETRAINING_S,
        "five_model_reference_s": list(FIVE_MODEL_REF_S),
        "l3_vs_l1": {
            "G1": round(rel(float(l3["mean_G1_estimation_s"]), float(summary["mean_G1_estimation_s"])), 6),
            "G3_plus_dgp": round(rel(float(l3["mean_G3_plus_dgp_s"]), float(summary["mean_G3_plus_dgp_s"])), 6),
            "wall": round(rel(float(l3["mean_wall_s"]), float(summary["mean_wall_s"])), 6),
            "peak": round(rel(float(l3["max_peak_mb"]), float(summary["max_peak_mb"])), 6),
        },
        "l0_vs_l1": {
            "G1": round(rel(float(l0["mean_G1_estimation_s"]), float(summary["mean_G1_estimation_s"])), 6),
            "G3_plus_dgp": round(rel(float(l0["mean_G3_plus_dgp_s"]), float(summary["mean_G3_plus_dgp_s"])), 6),
            "wall": round(rel(float(l0["mean_wall_s"]), float(summary["mean_wall_s"])), 6),
            "peak": round(rel(float(l0["max_peak_mb"]), float(summary["max_peak_mb"])), 6),
        },
        "summary_csv_field": summary.get("csv"),
        "summary_csv_field_note": "指向 out/（被忽略）；复算请用 tables/v3_phase_D_pilot_raw_r20.csv 副本",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="目标字节不同时允许覆盖")
    args = parser.parse_args()

    plan: list[tuple[Path, str]] = [(ROOT / src, dst) for src, dst in LOGS]
    plan += [(ROOT / SUMMARY_TABLE / name, f"tables/{name}") for name in TABLES]

    missing = [src for src, _ in plan if not src.is_file()]
    if missing:
        print("[d01-evidence] 缺少源文件，拒绝导出：")
        for src in missing:
            print(f"  - {_rel(src)}")
        return 2

    TARGET.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    conflicts: list[str] = []
    for source, rel in plan:
        destination = TARGET / rel
        payload = source.read_bytes()
        if destination.exists() and destination.read_bytes() != payload and not args.force:
            conflicts.append(rel)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_bytes() != payload:
            destination.write_bytes(payload)
        records.append({"path": rel, "kind": "d01_log" if rel.startswith("logs/") else "d01_table",
                        "source": _rel(source), "bytes": destination.stat().st_size,
                        "sha256": _sha256(destination)})
    if conflicts:
        print("[d01-evidence] 目标已存在且字节不同，拒绝覆盖（确认后加 --force）：")
        for rel in conflicts:
            print(f"  - {rel}")
        return 2

    manifest = {
        "purpose": "d01_pilot_run_manifest",
        "recipe": RECIPE,
        "command": "scripts/13_v3_pilot.py --scenario L1_main --n 200000 --reps 20 --start-rep 0",
        "extra_runs": "L0_P_main / L3_fixed_lt000 各 1 rep（n=200000，三粒度）",
        "host": {"platform": platform.platform(), "node": platform.node(), "python": platform.python_version()},
        "logs": {rel: _parse_log(TARGET / rel) for _, rel in LOGS},
        "files": {record["path"]: record["sha256"] for record in records},
    }
    manifest_path = TARGET / "run_manifest.json"
    manifest_payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous.pop("host", None)
        current = json.loads(manifest_payload)
        current.pop("host", None)
        if previous != current and not args.force:
            print("[d01-evidence] run_manifest.json 已存在且内容不同，拒绝重写（--force 才覆盖）")
            return 2
    manifest_path.write_text(manifest_payload, encoding="utf-8", newline="\r\n")
    records.append({"path": "run_manifest.json", "kind": "d01_run_manifest",
                    "source": _rel(Path(__file__)), "bytes": manifest_path.stat().st_size,
                    "sha256": _sha256(manifest_path)})

    coverage = {
        "source_label": "合成数据 / 已知 DGP",
        "status": "engineering_pilot",
        "generated_by": _rel(Path(__file__)),
        "purpose": "D01 20 rep pilot 的运行身份与逐 rep 表（原始日志在 out/，被 .gitignore 排除）",
        "file_count": len(records),
        "total_bytes": sum(int(record["bytes"]) for record in records),
        "files": records,
        "key_numbers": _key_numbers(),
        "note": ("只支撑排期；L0/L3 各 1 rep 无层内方差，不构成等价性实测。"
                 "summary 的 csv 字段指向 out/，复算以本目录 tables/ 副本为准。"),
    }
    coverage_path = TARGET / "coverage.json"
    payload = json.dumps(coverage, ensure_ascii=False, indent=2)
    if coverage_path.exists():
        previous = json.loads(coverage_path.read_text(encoding="utf-8"))
        if previous != coverage and not args.force:
            print("[d01-evidence] coverage.json 已存在且内容不同，拒绝重写（--force 才覆盖）")
            return 2
    coverage_path.write_text(payload, encoding="utf-8", newline="\r\n")

    bad = [record["path"] for record in records
           if _sha256(TARGET / str(record["path"])) != record["sha256"]
           or (TARGET / str(record["path"])).stat().st_size != record["bytes"]]
    if bad:
        print("[d01-evidence] 写盘后复核失败：" + ", ".join(bad))
        return 2
    registered = {str(record["path"]) for record in records}
    unregistered = [path.relative_to(TARGET).as_posix() for path in TARGET.rglob("*.json")
                    if path.relative_to(TARGET).as_posix() not in registered | {"coverage.json"}]
    if unregistered:
        print("[d01-evidence] 有 JSON 未被 coverage 登记：" + ", ".join(unregistered))
        return 2

    numbers = coverage["key_numbers"]
    print(f"[d01-evidence] {len(records)} 件 / {coverage['total_bytes']} B → {_rel(coverage_path)}")
    print(f"  rows={numbers['rows']} reps={numbers['rep_min']}–{numbers['rep_max']} failed={numbers['failed']}")
    print(f"  cpu/wall={numbers['cpu_over_wall_mean']} whole={numbers['whole_rep_cpu_over_wall_mean']}")
    print(f"  validation_cpu={numbers['derived_validation_cpu_s']} s "
          f"total={numbers['total_cpu_h_lower']}–{numbers['total_cpu_h_five_model'][1]} CPU·h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
