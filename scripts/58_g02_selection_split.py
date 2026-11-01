"""G02 重训 bootstrap 的选模构成与价值分解。

回答的问题：3.7 报的"重复间 sd"里，有多少来自同一条策略的价值波动、
多少来自"这一轮选中了谁"。只用逐 b 证据表的 chosen_model / policy_value，
不改任何估计，也不重新选模。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PER_CELL = ROOT / "outputs/evidence/g02_formal/per_cell"
AGG = ROOT / "outputs/tables/v3_phase_G02_retrain_bootstrap.csv"
OUT = ROOT / "outputs/tables/v3_phase_G02_selection_split.csv"
CELLS = ("L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000")
MODELS = ("causal_forest", "s_learner", "dr_learner", "t_learner", "constant")


def main() -> int:
    agg = pd.read_csv(AGG, encoding="utf-8-sig").set_index("cell_id")
    rows: list[dict[str, object]] = []
    for cell in CELLS:
        frame = pd.read_csv(PER_CELL / f"{cell}__repetitions.csv", encoding="utf-8-sig")
        assert len(frame) == int(agg.loc[cell, "b_count"]), f"{cell} b 数与聚合表不一致"
        counts = frame.chosen_model.value_counts().reindex(MODELS, fill_value=0)
        assert int(counts.sum()) == len(frame), f"{cell} 选模构成不等于 b 数"
        shares = counts / len(frame)
        grouped = frame.groupby("chosen_model").policy_value.agg(["count", "mean", "std"])
        within_ss = float(((grouped["count"] - 1) * grouped["std"].fillna(0.0) ** 2).sum())
        within_df = int(len(frame) - len(grouped))
        rows.append(
            {
                "cell_id": cell,
                "n_b": len(frame),
                **{f"n_{m}": int(counts[m]) for m in MODELS},
                "agree_prob": float((shares**2).sum()),
                "policy_value_mean": float(frame.policy_value.mean()),
                "policy_value_sd": float(frame.policy_value.std(ddof=1)),
                "between_model_range": float(grouped["mean"].max() - grouped["mean"].min()),
                "within_model_sd": float(np.sqrt(within_ss / within_df)),
                "n_models_chosen": int(len(grouped)),
                "decision_pass_total": int(frame.decision_all_pass.sum()),
                "guardrail_all_pass": bool(frame.guardrail_pass.all()),
            }
        )
        assert np.isclose(
            frame.policy_value.mean(), float(agg.loc[cell, "policy_value_mean"]), atol=1e-9
        ), f"{cell} 策略价值均值与聚合表不一致"
        assert np.isclose(
            frame.policy_value.std(ddof=1), float(agg.loc[cell, "policy_value_sd"]), atol=1e-9
        ), f"{cell} 策略价值 sd 与聚合表不一致"
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(out.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
