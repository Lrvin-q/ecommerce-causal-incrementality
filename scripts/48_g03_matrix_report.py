"""G03 报告 §3 取数：24 格矩阵的 4 指标 mean / sd / MC_SE / 95% CI，只读打印。

回答方案里的哪个问题："在注册的 24 个机制场景下，策略价值与决策通过率如何？"

数据源是 34 号 ``_finalize`` 写的汇总表（``outputs/tables/v3_g_g_core.csv`` /
``v3_g_g_tier2.csv``；未跑满时同名带 ``_provisional`` 后缀），**不重跑、不写证据区**。
注意 ``outputs/tables/v3_g_g_*_provisional.csv`` 也可能是 06:26 工程演练（R=3、1 格）的入册件，
本脚本用"格数 + R + provisional 列"三重校验，遇到那种表会直接报错而不是当成正式结果。
脚本只做三件事：校验（R、provisional、block、4 指标齐全）、算 1.96×MC_SE 的 CI、分区打印
（Tier1 与 Tier2 严禁同表并列排序）。

用法::

    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/48_g03_matrix_report.py
    # 夹具演练（指向手造的临时表，只验证程序会算会拦）：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/48_g03_matrix_report.py \
        --core-table out/scratch/fixture_core.csv --tier2-table out/scratch/fixture_tier2.csv
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
METRICS = ("ate", "ate_test", "ate_paid_purchase_7d", "ate_any_refund_30d")
REGISTERED_R = {"g_core": 500, "g_tier2": 30}
EXPECTED_CELLS = {"g_core": 4, "g_tier2": 20}


def resolve(path: Path | None, stem: str) -> tuple[Path, bool]:
    """返回 (实际路径, 是否 provisional)；两个都没有就失败（§12.7 不静默跳过）。"""
    if path is not None:
        return path, "_provisional" in path.stem
    final = TABLES / f"{stem}.csv"
    if final.is_file():
        return final, False
    provisional = TABLES / f"{stem}_provisional.csv"
    if provisional.is_file():
        return provisional, True
    raise SystemExit(f"[FAIL] 找不到 {final.name} 或 {provisional.name}（34 号 merge 还没跑？）")


def load(path: Path, block: str, problems: list[str]) -> pd.DataFrame:
    frame = pd.read_csv(path)
    need = {"cell_id", "block", "tier", "metric", "R", "MC_SE", "sd", "mean", "provisional"}
    missing = need - set(frame.columns)
    if missing:
        raise SystemExit(f"[FAIL] {path.name} 缺列 {sorted(missing)}")
    if set(frame["block"]) != {block}:
        problems.append(f"{path.name}: block={sorted(set(frame['block']))} != {block}")
    if set(frame["tier"]) != ({1} if block == "g_core" else {2}):
        problems.append(f"{path.name}: tier={sorted(set(frame['tier']))} 与 {block} 不符")
    cells = sorted(set(frame["cell_id"]))
    if len(cells) != EXPECTED_CELLS[block]:
        problems.append(f"{path.name}: {len(cells)} 格 != 注册 {EXPECTED_CELLS[block]}")
    for cell, part in frame.groupby("cell_id"):
        got = set(part["metric"])
        if got != set(METRICS):
            problems.append(f"{cell}: 指标 {sorted(got)} != 注册四项")
        if part["R"].nunique() != 1:
            problems.append(f"{cell}: 同一格 R 不一致 {sorted(set(part['R']))}")
        expected_r = REGISTERED_R[block]
        actual_r = int(part["R"].iloc[0])
        provisional = bool(part["provisional"].iloc[0])
        if actual_r > expected_r:
            problems.append(f"{cell}: R={actual_r} 超过注册 {expected_r}")
        if actual_r < expected_r and not provisional:
            problems.append(f"{cell}: R={actual_r}/{expected_r} 却没标 provisional")
        if actual_r == expected_r and provisional:
            problems.append(f"{cell}: 已跑满却标 provisional")
        for value in part["mean"].astype(float):
            if not math.isfinite(value):
                problems.append(f"{cell}: mean 非有限值 {value}")
    return frame


def render(frame: pd.DataFrame, block: str, title: str, path: Path) -> None:
    display = path.resolve().relative_to(ROOT.resolve()).as_posix()
    print(f"\n### {title}\n")
    print(f"来源：`{display}`；R={int(frame['R'].iloc[0])}，"
          f"provisional={bool(frame['provisional'].iloc[0])}")
    for metric in METRICS:
        part = frame[frame["metric"] == metric].sort_values("cell_id")
        print(f"\n**{metric}**\n")
        print("| 格 | R | mean | sd | MC SE | 95% CI (±1.96×MC SE) |")
        print("|---|---:|---:|---:|---:|---|")
        for row in part.itertuples():
            half = 1.96 * float(row.MC_SE) if math.isfinite(float(row.MC_SE)) else float("nan")
            print(
                f"| `{row.cell_id}` | {int(row.R)} | {float(row.mean):.4f} | "
                f"{float(row.sd):.4f} | {float(row.MC_SE):.4f} | "
                f"[{float(row.mean) - half:.4f}, {float(row.mean) + half:.4f}] |"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="G03 §3 矩阵取数（只读）")
    parser.add_argument("--core-table", type=Path, default=None)
    parser.add_argument("--tier2-table", type=Path, default=None)
    parser.add_argument("--allow-partial", action="store_true",
                        help="允许多格尚未跑满（只打印，仍返回 0；用于 Phase 1 中间态）")
    args = parser.parse_args()

    problems: list[str] = []
    core_path, core_prov = resolve(args.core_table, "v3_g_g_core")
    tier2_path, tier2_prov = resolve(args.tier2_table, "v3_g_g_tier2")
    core = load(core_path, "g_core", problems)
    tier2 = load(tier2_path, "g_tier2", problems)

    if problems:
        print("[FAIL] 汇总表与注册契约不符：", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        return 2

    render(core, "g_core", "Tier1 core（4 格，注册 R_ate=500）", core_path)
    render(tier2, "g_tier2", "Tier2 选中格（20 格，注册 R=30；不与 Tier1 并列）", tier2_path)

    partial = bool(core["provisional"].iloc[0]) or bool(tier2["provisional"].iloc[0])
    if partial and not args.allow_partial:
        print("\n[FAIL] 汇总表仍是 provisional（未跑满注册 R）；用 --allow-partial 只看中间态",
              file=sys.stderr)
        return 3
    print("\n[OK] 4 指标 × 24 格齐全，R 与 provisional 标记自洽。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
