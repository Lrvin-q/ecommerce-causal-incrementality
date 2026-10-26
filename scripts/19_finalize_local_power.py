"""合并 L0/L1/L2 三路的功效格正式结果，产出 D02 第④项的证据表。

它回答的问题
------------
15 个功效格在**注册规模**下的 ``achieved_effect`` / ``rejection_rate`` / ``MC_SE``
分别是多少？这批数字此前一直是 ``pending``（只有设计期的 ``target_effect``）。

为什么要单独一个脚本
--------------------
正式跑按层拆成三个进程（每进程 5 格 × 100 次），各自把 ``local_power_summary.csv``
写在自己的 ``--out`` 目录里。合并不是简单 concat：**必须逐格校验**——

1. 15 格齐全、无重复、无 L3（14:45 的裁决：L3 的未调整 ITT 不是 ATE，5 格不跑）；
2. 每格 ``n_reps`` 必须等于冻结的 R；
3. ``achieved_effect_analytic`` 与 ``target_effect`` 的偏差 ≤ 1e-6（构造正确性）；
4. ``rejection_rate`` 与 ``mc_se`` 非空（R ≥ 2 才有定义）；
5. 带 ``estimator_warning`` 的格必须单独列出，不能混在正常格里。

任何一项不过就**抛异常**，不写表——半成品不进 ``outputs/tables/``。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\19_finalize_local_power.py
    # 指定目录（默认按 formal_L0/L1/L2 发现）
    .\\.venv\\Scripts\\python.exe scripts\\19_finalize_local_power.py --roots out\\a out\\b out\\c

输出
----
- ``outputs/tables/v3_phase_D_local_power_formal.csv``：15 行 × 62 列
- ``outputs/tables/v3_phase_D_local_power_formal.json``：校验结果、来源指纹、逐格判定
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = [ROOT / "out" / "v3_phase_d_local_power" / f"formal_{layer}" for layer in ("L0", "L1", "L2")]
EXPECTED_LAYERS = ("L0", "L1", "L2")
EXPECTED_MULTIPLIERS = (0.0, 0.5, 1.0, 1.5, 2.0)
FORMAL_REPS = 100
TARGET_TOLERANCE = 1e-6
OUT_CSV = ROOT / "outputs" / "tables" / "v3_phase_D_local_power_formal.csv"
OUT_JSON = ROOT / "outputs" / "tables" / "v3_phase_D_local_power_formal.json"
SOURCE_LABEL = "合成数据 / 已知 DGP"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_summaries(roots: list[Path]) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """读三路 ``local_power_summary.csv``；缺文件立刻抛，不跳过。"""
    frames: list[pd.DataFrame] = []
    provenance: list[dict[str, str]] = []
    for root in roots:
        path = root / "local_power_summary.csv"
        if not path.is_file():
            raise FileNotFoundError(f"{root} 没有 local_power_summary.csv —— 该层可能还没跑完")
        frame = pd.read_csv(path, encoding="utf-8-sig")
        frames.append(frame)
        provenance.append({"root": str(root), "summary_sha256": _sha256(path), "rows": str(len(frame))})
    return pd.concat(frames, ignore_index=True), provenance


def validate(frame: pd.DataFrame) -> list[str]:
    """返回所有问题；空列表才算通过。"""
    problems: list[str] = []

    expected = {(layer, mult) for layer in EXPECTED_LAYERS for mult in EXPECTED_MULTIPLIERS}
    actual = {(str(row.level), round(float(row.multiplier), 6)) for row in frame.itertuples()}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        problems.append(f"缺格: {missing}")
    if extra:
        problems.append(f"多余格（含 L3 或未注册倍数）: {extra}")
    duplicated = frame[frame.duplicated("cell_id", keep=False)]["cell_id"].tolist()
    if duplicated:
        problems.append(f"重复格: {sorted(set(duplicated))}")

    bad_reps = frame[frame["n_reps"].astype(int) != FORMAL_REPS]["cell_id"].tolist()
    if bad_reps:
        problems.append(f"n_reps 不等于 {FORMAL_REPS}: {bad_reps}")

    deviation = (frame["achieved_effect_analytic"] - frame["target_effect"]).abs()
    over = frame.loc[deviation > TARGET_TOLERANCE, "cell_id"].tolist()
    if over:
        problems.append(f"achieved 与 target 偏差 > {TARGET_TOLERANCE}: {over}")

    for column in ("rejection_rate", "mc_se", "binomial_ci_low", "binomial_ci_high"):
        blank = frame[frame[column].isna()]["cell_id"].tolist()
        if blank:
            problems.append(f"{column} 为空: {blank}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并功效格正式结果并校验（D02 第④项）")
    parser.add_argument("--roots", nargs="*", type=Path, default=None, help="三路的 --out 目录")
    args = parser.parse_args(argv)

    roots = args.roots or DEFAULT_ROOTS
    frame, provenance = load_summaries(roots)
    frame = frame.sort_values(["level", "multiplier"], kind="stable").reset_index(drop=True)

    problems = validate(frame)
    if problems:
        print("[未通过] 合并前校验发现问题：")
        for item in problems:
            print("  -", item)
        return 1

    # 空值在 CSV 读回后可能是 NaN（float64），直接 fillna("") 会触发 pandas 4 的警告；
    # 用逐元素映射既避免 dtype 冲突，也保证纯空白字符串算作"无警告"。
    warning_text = frame["estimator_warning"].map(lambda value: "" if pd.isna(value) else str(value).strip())
    warnings = frame[warning_text.str.len() > 0]
    if "power_cell_class" in frame:
        boundary = frame[frame["power_cell_class"].astype(str) == "boundary_zero_margin"]
    else:
        boundary = frame.iloc[0:0]

    csv_encoding = "utf-8-sig"
    frame.to_csv(OUT_CSV, index=False, encoding=csv_encoding)

    summary = {
        "source_label": SOURCE_LABEL,
        "purpose": "D02 第④项：15 个功效格的注册规模实测拒绝率",
        "cells": int(len(frame)),
        "layers": sorted(frame["level"].unique().tolist()),
        "multipliers": sorted({round(float(v), 6) for v in frame["multiplier"]}),
        "formal_reps_per_cell": FORMAL_REPS,
        "total_reps": int(frame["n_reps"].sum()),
        "target_tolerance": TARGET_TOLERANCE,
        "validation": "passed",
        "boundary_cells": boundary["cell_id"].tolist() if len(boundary) else [],
        "cells_with_estimator_warning": warnings["cell_id"].tolist() if len(warnings) else [],
        "provenance": provenance,
        "csv": str(OUT_CSV.relative_to(ROOT)),
        "csv_sha256": _sha256(OUT_CSV),
        "note": "L3 的 5 格按 2026-10-25 14:45 裁决不跑：未调整 ITT 在 L3 不是 ATE（选择偏差约 11 倍设计 MDE）。",
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[通过] {len(frame)} 格 × {FORMAL_REPS} 次 = {int(frame['n_reps'].sum())} 次")
    print(f"csv    : {OUT_CSV.relative_to(ROOT)}")
    print(f"summary: {OUT_JSON.relative_to(ROOT)}")
    if len(boundary):
        print(f"边界格（零余量，不得计入“可检出”）: {boundary['cell_id'].tolist()}")
    if len(warnings):
        print(f"带估计量警告的格: {warnings['cell_id'].tolist()}")
    print(frame[["cell_id", "target_effect", "achieved_effect", "rejection_rate", "mc_se"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
