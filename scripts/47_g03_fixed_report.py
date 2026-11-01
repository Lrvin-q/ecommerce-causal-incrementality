"""G03 报告 §4 取数：Stage A 固定 bootstrap（24 格 × rep0 × 1 000 次）汇总。

回答方案里的哪个问题："在同一个 rep、同一批用户、同一预算档上，定向发券相对随机发券
的差异有多大，区间是否跨零？"

只读 ``out/g02_fixed/shards/<cell>_s0000/<cell>/rep0/validation/fixed_bootstrap.csv``，
逐格校验"单行 / 预算 0.2 / 重抽 1 000 次"后写出
``outputs/tables/v3_g03_fixed_bootstrap_summary.csv``，并把 Tier1 与 Tier2 分成两张表打印
（Tier2 不得与 Tier1 并列，AGENTS/交付约束）。

用法::

    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/47_g03_fixed_report.py
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIXED_ROOT = ROOT / "out" / "g02_fixed"
OUT_TABLE = ROOT / "outputs" / "tables" / "v3_g03_fixed_bootstrap_summary.csv"


def load_contract():
    """格清单与预算/重抽数取自 41 号（消费方契约，避免两处手抄漂移）。"""
    spec = importlib.util.spec_from_file_location(
        "g03_export_contract", ROOT / "scripts" / "41_export_g03_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    contract = load_contract()
    cells = contract.expected_cells()
    rows: list[dict] = []
    problems: list[str] = []

    for cell, block in cells.items():
        path = FIXED_ROOT / "shards" / f"{cell}_s0000" / cell / "rep0" / "validation" / "fixed_bootstrap.csv"
        if not path.is_file():
            problems.append(f"{cell}: 缺 {path.relative_to(ROOT)}")
            continue
        frame = pd.read_csv(path)
        if len(frame) != 1:
            problems.append(f"{cell}: 行数 {len(frame)} != 1")
            continue
        row = frame.iloc[0]
        budget = float(row["budget_cny_per_user"])
        resamples = int(row["resamples"])
        if not math.isclose(budget, contract.PRIMARY_BUDGET):
            problems.append(f"{cell}: 预算 {budget} != {contract.PRIMARY_BUDGET}")
        if resamples != contract.RESAMPLES:
            problems.append(f"{cell}: 重抽 {resamples} != {contract.RESAMPLES}")
        ci_low = float(row["ci_low"])
        ci_high = float(row["ci_high"])
        rows.append(
            {
                "tier": 1 if block == "g_core" else 2,
                "block": block,
                "cell": cell,
                "budget_cny_per_user": budget,
                "resamples": resamples,
                "n_targeted": int(row["n_targeted"]),
                "n_random": int(row["n_random"]),
                "point_diff": float(row["point_diff"]),
                "bootstrap_mean_diff": float(row["bootstrap_mean_diff"]),
                "bootstrap_se": float(row["bootstrap_se"]),
                "ci_low": ci_low,
                "ci_high": ci_high,
                "ci_width": ci_high - ci_low,
                "ci_covers_zero": bool(ci_low <= 0.0 <= ci_high),
                "point_diff_positive": bool(float(row["point_diff"]) > 0.0),
                "source": str(path.relative_to(ROOT)).replace("\\", "/"),
            }
        )

    if problems:
        for item in problems:
            print(f"[FAIL] {item}", file=sys.stderr)
        return 2
    if len(rows) != len(cells):
        print(f"[FAIL] 汇总 {len(rows)} 格 != 契约 {len(cells)} 格", file=sys.stderr)
        return 2

    table = pd.DataFrame(rows).sort_values(["tier", "cell"]).reset_index(drop=True)
    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_TABLE, index=False, encoding="utf-8-sig")
    print(f"写盘：{OUT_TABLE.relative_to(ROOT)}（{len(table)} 行）")
    print("预算恒 0.2 / 重抽恒 1000：OK")

    def render(tier: int, title: str) -> None:
        part = table[table["tier"] == tier]
        print(f"\n### {title}（{len(part)} 格）\n")
        print("| 格 | n_targeted | n_random | 点差 | bootstrap SE | 95% CI | CI 跨零 |")
        print("|---|---|---|---|---|---|---|")
        for row in part.itertuples():
            print(
                f"| `{row.cell}` | {row.n_targeted:,} | {row.n_random:,} | "
                f"{row.point_diff:+.4f} | {row.bootstrap_se:.4f} | "
                f"[{row.ci_low:+.4f}, {row.ci_high:+.4f}] | "
                f"{'是' if row.ci_covers_zero else '否'} |"
            )
        cover = int(part["ci_covers_zero"].sum())
        positive = int(part["point_diff_positive"].sum())
        print(f"\n{tier} 档小计：CI 跨零 {cover}/{len(part)}；点差为正 {positive}/{len(part)}；"
              f"中位半宽 {part['ci_width'].median() / 2:.4f}")

    render(1, "Tier1 core（4 格，R_ate=500 设计中的 rep0）")
    render(2, "Tier2 选中格（20 格，R=30 设计中的 rep0；精度只判方向，不与 Tier1 并列）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
