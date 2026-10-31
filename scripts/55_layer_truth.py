"""为论文的四个核心格计算解析真值，并与正式重复的估计对照。

为什么需要这个脚本：正式重复表只存了估计的均值与蒙特卡洛标准误，没有存真值。
一篇以"真值已知"为前提的研究，必须能报出"估计 − 真值"的偏差，否则"无偏"只是断言。

做法：对每个核心格，用固定的代表重复号重建总体，调用 DGP 的解析真值接口
（``audit_conditional_truth``）逐用户取两个动作下的期望净贡献利润，相减后取均值，
即为该格的平均处理效应真值。估计值直接读 ``v3_g_g_core.csv``，不重算。

输出：``outputs/tables/v3_paper_truth_core.csv``
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.dgp.v3_engine import audit_conditional_truth, generate_v3_population  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

CORE = ("L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000")
OUT = ROOT / "outputs" / "tables" / "v3_paper_truth_core.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200000, help="与正式运行一致的样本量")
    ap.add_argument("--rep", type=int, default=0, help="代表重复号（真值与重复号无关，取 0）")
    ap.add_argument("--cells", nargs="*", default=list(CORE))
    args = ap.parse_args()

    protocol = load_v3_protocol()
    core = pd.read_csv(ROOT / "outputs" / "tables" / "v3_g_g_core.csv")

    rows: list[dict[str, object]] = []
    for cell in args.cells:
        cfg = protocol.scenario(cell)
        print(f"[{cell}] 生成总体 n={args.n} rep={args.rep} …", flush=True)
        population = generate_v3_population(cfg, args.rep, args.n)
        truth = audit_conditional_truth(population, cfg)

        profit_diff = truth["expected_net_profit_1"].to_numpy() - truth["expected_net_profit_0"].to_numpy()
        purchase_diff = truth["purchase_probability_x_1"].to_numpy() - truth["purchase_probability_x_0"].to_numpy()

        level = str(cfg.require("scenarios").__class__)  # 占位，下面按 cell 名推断
        level = cell.split("_")[0]

        for metric, value, scale in (
            ("ate", float(np.mean(profit_diff)), 1.0),
            ("ate_paid_purchase_7d", float(np.mean(purchase_diff)), 1.0),
        ):
            est_row = core[(core.cell_id == cell) & (core.metric == metric)]
            if est_row.empty:
                continue
            est = float(est_row["mean"].iloc[0])
            mcse = float(est_row["MC_SE"].iloc[0])
            R = int(est_row["R"].iloc[0])
            rows.append({
                "cell_id": cell,
                "level": level,
                "metric": metric,
                "truth": value * scale,
                "estimate": est,
                "bias": est - value * scale,
                "rel_bias_pct": (est - value * scale) / value * 100 if value != 0 else float("nan"),
                "R": R,
                "MC_SE": mcse,
                "bias_over_MCSE": (est - value * scale) / mcse if mcse > 0 else float("nan"),
                "n": args.n,
                "rep": args.rep,
            })
        print(f"  ATE 真值 {np.mean(profit_diff):.4f}，购买率真值 {np.mean(purchase_diff):.4f}")

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n写出 {OUT.relative_to(ROOT)}（{len(df)} 行）")
    print(df.to_string(index=False, max_colwidth=22))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
