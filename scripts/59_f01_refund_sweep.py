"""F01 单帧的退款率随预算档变化：每档两条发券臂相对不发券的差、z 与距界值余量。

回答的问题：3.6 的护栏只在 0.2 元/人上判定过；把预算换到别的档位，
退款率差会不会逼近 0.5 个百分点的界值。只做重排与算术，不重算口径、不重新拟合。
输出 outputs/tables/v3_phase_F01_refund_sweep.csv。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "outputs/tables/v3_phase_F01_cost.csv"
OUT = ROOT / "outputs/tables/v3_phase_F01_refund_sweep.csv"
MARGIN_PP = 0.5
TARGET = "greedy_incremental_profit_per_cost"
RANDOM = "random_same_budget"
NO_COUPON = "no_coupon"


def main() -> int:
    frame = pd.read_csv(SRC, encoding="utf-8-sig")
    refund = frame[frame.component == "refund_rate_30d"]
    assert set(refund.policy) == {TARGET, "greedy_local_swap", RANDOM, NO_COUPON}, refund.policy.unique()
    wide = refund.pivot(index="per_user_budget_cny", columns="policy", values="value")
    sess = refund.pivot(index="per_user_budget_cny", columns="policy", values="se")
    n = refund.n.unique()
    assert len(n) == 1, "各档样本量不一致，df 不可比"

    rows = []
    for budget in sorted(wide.index):
        base = wide.loc[budget, NO_COUPON]
        base_se = sess.loc[budget, NO_COUPON]
        for policy, label in ((TARGET, "greedy"), (RANDOM, "random")):
            diff = wide.loc[budget, policy] - base
            se = float(np.hypot(sess.loc[budget, policy], base_se))
            rows.append({
                "per_user_budget_cny": budget,
                "contrast": label,
                "refund_no_coupon": base,
                "refund_policy": wide.loc[budget, policy],
                "diff_pp": diff * 100.0,
                "se_diff_pp": se * 100.0,
                "z": diff / se,
                "margin_pp": MARGIN_PP,
                "margin_left_pp": MARGIN_PP - diff * 100.0,
                "margin_over_se": (MARGIN_PP - diff * 100.0) / (se * 100.0),
                "n_per_arm": int(n[0]),
            })
    out = pd.DataFrame(rows)
    greedy = out[out.contrast == "greedy"].set_index("per_user_budget_cny")
    random = out[out.contrast == "random"].set_index("per_user_budget_cny")
    gap = (greedy.refund_policy - random.refund_policy).abs() * 100.0
    out["gap_vs_random_pp"] = [
        float(gap.loc[budget]) if contrast == "greedy" else float("nan")
        for budget, contrast in zip(out.per_user_budget_cny, out.contrast)
    ]
    print(greedy[["refund_no_coupon", "refund_policy", "diff_pp", "z", "margin_left_pp"]].round(4).to_string())
    print("max |greedy-random| pp:", round(float(gap.max()), 4), "at", float(gap.idxmax()))
    print("min margin_left_pp:", round(float(greedy.margin_left_pp.min()), 4))
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print("WROTE", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
