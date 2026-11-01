"""F01 审计对照的正文表：OPE 误差随预算档变化、0.2 档三条口径的差距。

回答的问题：同一帧上，离策略估计值离真值审计值有多远、误差是否在自己的
标准误以内、两条收益主张的幅度被高估还是低估。只做对齐与派生列，不改任何估计。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OPE = ROOT / "outputs/tables/v3_phase_F01_ope_vs_audit.csv"
VALUE = ROOT / "outputs/tables/v3_phase_F01_value.csv"
INCREMENT = ROOT / "outputs/tables/v3_phase_F01_increment.csv"
FAMILY = ROOT / "outputs/tables/v3_phase_F01_family.csv"
OUT_BUDGET = ROOT / "outputs/tables/v3_phase_F01_audit_by_budget.csv"
OUT_EST = ROOT / "outputs/tables/v3_phase_F01_estimator_compare.csv"
OUT_CONTRAST = ROOT / "outputs/tables/v3_phase_F01_contrast_audit.csv"

POLICIES = ("greedy_incremental_profit_per_cost", "random_same_budget")
PRIMARY_BUDGET = 0.2
PRIMARY_ESTIMATOR = "dr_increment"
ESTIMATOR_BUDGETS = (0.04, PRIMARY_BUDGET)


def main() -> int:
    ope = pd.read_csv(OPE, encoding="utf-8-sig")
    value = pd.read_csv(VALUE, encoding="utf-8-sig")
    increment = pd.read_csv(INCREMENT, encoding="utf-8-sig")

    rows = ope[(ope.comparison == "policy_vs_no_coupon") & ope.name.isin(POLICIES)].copy()
    rows = rows.rename(columns={"name": "policy"})
    ess = value[value.estimator == PRIMARY_ESTIMATOR][
        ["per_user_budget_cny", "policy", "ess_fraction_treated", "ess_fraction_control"]
    ]
    rows = rows.merge(
        ess, on=["per_user_budget_cny", "policy"], how="left", validate="one_to_one"
    )
    assert rows.ess_fraction_treated.notna().all(), "ESS 合并失败"
    rows["abs_error_over_se"] = (rows.value_error_cny_per_user / rows.ope_se_cny_per_user).abs()
    rows["policy_order"] = rows.policy.map({p: i for i, p in enumerate(POLICIES)})
    rows = rows.sort_values(["per_user_budget_cny", "policy_order"])
    out = rows[[
        "per_user_budget_cny", "policy", "ope_value_cny_per_user", "audit_value_cny_per_user",
        "value_error_cny_per_user", "ope_se_cny_per_user", "abs_error_over_se",
        "ope_spend_per_user_cny", "audit_spend_per_user_cny", "spend_error_cny_per_user",
        "ess_fraction_treated", "ess_fraction_control", "reliability_passed", "sign_agrees",
    ]]
    assert len(out) == 16, len(out)
    # 全额预算下两臂选同一批人，估计与审计都应逐位相同
    full = out[out.per_user_budget_cny >= 0.999]
    assert full.ope_value_cny_per_user.nunique() == 1
    assert full.audit_value_cny_per_user.nunique() == 1
    out.to_csv(OUT_BUDGET, index=False, encoding="utf-8-sig")
    print("budget rows", len(out))

    primary = increment[
        increment.per_user_budget_cny.isin(ESTIMATOR_BUDGETS) & increment.policy.isin(POLICIES)
    ].copy()
    wide = primary.pivot_table(
        index=["per_user_budget_cny", "policy"], columns="estimator",
        values="increment_cny_per_user",
    )
    spread = (wide.max(axis=1) - wide.min(axis=1)).rename("estimator_spread")
    med = primary[primary.estimator == PRIMARY_ESTIMATOR].set_index(
        ["per_user_budget_cny", "policy"]
    )[["se_increment", "z", "one_sided_p_value"]]
    audit = ope[
        (ope.comparison == "policy_vs_no_coupon")
        & ope.per_user_budget_cny.isin(ESTIMATOR_BUDGETS)
        & ope.name.isin(POLICIES)
    ].set_index(["per_user_budget_cny", "name"])["audit_value_cny_per_user"]
    audit.index = audit.index.set_names(["per_user_budget_cny", "policy"])
    est = wide.join(spread).join(med).join(audit)
    est = est.reset_index()
    est["dr_error_vs_audit"] = est["dr_increment"] - est.audit_value_cny_per_user
    est.to_csv(OUT_EST, index=False, encoding="utf-8-sig")
    assert len(est) == len(ESTIMATOR_BUDGETS) * len(POLICIES), len(est)
    print(est.round(6).to_string(index=False))

    family = pd.read_csv(FAMILY, encoding="utf-8-sig")
    audit_pairs = ope[
        (ope.comparison == "contrast") & (ope.per_user_budget_cny == PRIMARY_BUDGET)
    ][["name", "audit_value_cny_per_user"]].rename(
        columns={"name": "contrast", "audit_value_cny_per_user": "audit_diff"}
    )
    family = family.merge(audit_pairs, on="contrast", how="left", validate="one_to_one")
    assert family.audit_diff.notna().all(), "审计差未对齐"
    family["ope_minus_audit"] = family.diff_cny_per_user - family.audit_diff
    family["per_user_budget_cny"] = PRIMARY_BUDGET
    out_contrast = family[[
        "per_user_budget_cny", "contrast", "diff_cny_per_user", "audit_diff",
        "ope_minus_audit", "se_diff", "one_sided_p_value", "holm_adjusted_p_value",
        "holm_lower_bound_cny_per_user", "claim_passed", "n",
    ]]
    assert len(out_contrast) == 2, len(out_contrast)
    out_contrast.to_csv(OUT_CONTRAST, index=False, encoding="utf-8-sig")
    print(out_contrast.round(6).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
