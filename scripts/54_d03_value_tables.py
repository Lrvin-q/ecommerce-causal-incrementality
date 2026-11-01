"""D03 策略层的两张补充表：0.2 元/人档的绝对价值与选模后悔。

回答的问题：同一策略喂给不同估计模型，各自能拿回多少真实价值；
以及"每个 rep 选中的模型"相对"五模型事后最优"差多少。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GRID = ROOT / "outputs/tables/v3_phase_D03_formal_policy_grid.csv"
OUT_VALUE = ROOT / "outputs/tables/v3_phase_D03_policy_value_020.csv"
OUT_REGRET = ROOT / "outputs/tables/v3_phase_D03_selection_regret.csv"

BUDGET = 0.2
GREEDY = "greedy_incremental_profit_per_cost"


def main() -> int:
    grid = pd.read_csv(GRID, encoding="utf-8-sig")
    sub = grid[(grid.per_user_budget_cny == BUDGET) & (grid.policy != "all_coupon_unconstrained_reference")]
    value = (
        sub.groupby(["policy", "model"])["true_value_per_user"]
        .agg(mean_true_value_per_user="mean", sd="std", n="size")
        .reset_index()
    )
    value["se"] = value["sd"] / value["n"] ** 0.5
    value.to_csv(OUT_VALUE, index=False, encoding="utf-8-sig")
    print("value rows", len(value), "policies", value.policy.nunique(), "models", value.model.nunique())

    g = sub[sub.policy == GREEDY]
    wide = g.pivot_table(index="rep_id", columns="model", values="true_value_per_user")
    chosen = g[g.chosen].set_index("rep_id")["model"]
    assert len(chosen) == len(wide), (len(chosen), len(wide))
    chosen_val = pd.Series(
        [wide.loc[rep, model] for rep, model in chosen.items()], index=chosen.index
    )
    best = wide.max(axis=1)
    regret = (chosen_val - best).rename("chosen_minus_best_cny_per_user")
    out = pd.DataFrame({
        "n_reps": [len(regret)],
        "mean_chosen_minus_best": [regret.mean()],
        "se": [regret.std(ddof=1) / len(regret) ** 0.5],
        "share_nonnegative": [(regret >= 0).mean()],
        "worst": [regret.min()],
    })
    out.to_csv(OUT_REGRET, index=False, encoding="utf-8-sig")
    print(out.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
