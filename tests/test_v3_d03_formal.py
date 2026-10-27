"""D03 正式报告聚合层的口径测试：配对、覆盖、双口径合规。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth.evaluation import v3_d03_formal as formal

MODELS = ("constant", "t_learner")
POLICIES = (
    "no_coupon",
    "business_rule_new_user_then_cart",
    "greedy_incremental_profit_per_cost",
)
BASELINE = "business_rule_new_user_then_cart"


def _per_rep() -> pd.DataFrame:
    spec = {
        0: {
            "constant": dict(chosen=True, rank=1, score=0.10, bias=0.05, rel=0.10,
                             slope=0.90, pearson=0.80, rmse=0.30),
            "t_learner": dict(chosen=False, rank=2, score=0.05, bias=0.20, rel=0.30,
                              slope=0.50, pearson=0.60, rmse=0.50),
        },
        1: {
            "constant": dict(chosen=False, rank=2, score=0.02, bias=0.15, rel=0.20,
                             slope=0.70, pearson=0.70, rmse=0.40),
            "t_learner": dict(chosen=True, rank=1, score=0.20, bias=0.01, rel=0.05,
                              slope=0.95, pearson=0.90, rmse=0.20),
        },
    }
    rows = []
    for rep, per_model in spec.items():
        for model, values in per_model.items():
            rows.append({
                "rep_id": rep, "model": model, "chosen": values["chosen"],
                "rank": values["rank"], "selection_score": values["score"],
                "bias_mean": values["bias"], "relative_bias": values["rel"],
                "calibration_slope": values["slope"], "pearson_r": values["pearson"],
                "rmse": values["rmse"],
            })
    return pd.DataFrame(rows)


def _grid() -> pd.DataFrame:
    # rep0 选 constant：business 10 > greedy 9；rep1 选 t：greedy 11 > business 10。
    # 池化 chosen 行会得到差 0，但按模型配对是 −1 与 +1（AGENTS §12.6 的反例）。
    values = {
        (0, "constant"): {"business_rule_new_user_then_cart": 10.0,
                          "greedy_incremental_profit_per_cost": 9.0,
                          "no_coupon": 0.0},
        (0, "t_learner"): {"business_rule_new_user_then_cart": 8.0,
                           "greedy_incremental_profit_per_cost": 8.0,
                           "no_coupon": 0.0},
        (1, "constant"): {"business_rule_new_user_then_cart": 5.0,
                          "greedy_incremental_profit_per_cost": 5.0,
                          "no_coupon": 0.0},
        (1, "t_learner"): {"business_rule_new_user_then_cart": 10.0,
                           "greedy_incremental_profit_per_cost": 11.0,
                           "no_coupon": 0.0},
    }
    rows = []
    for (rep, model), per_policy in values.items():
        chosen = (rep == 0 and model == "constant") or (rep == 1 and model == "t_learner")
        for policy, true_value in per_policy.items():
            rows.append({
                "rep_id": rep,
                "model": model,
                "chosen": chosen,
                "per_user_budget_cny": 0.04,
                "budget_cny": 4.0,
                "policy": policy,
                "n_selected": 10 if policy != "no_coupon" else 0,
                "predicted_value": true_value + 0.5,
                "true_value_per_user": true_value,
                "actual_spend_cny": 5.0 if policy.startswith("greedy") else (
                    4.0 if policy.startswith("business") else 0.0
                ),
                "within_budget_by_hat": True,
                "within_budget_by_true": not policy.startswith("greedy"),
            })
    return pd.DataFrame(rows)


def test_selection_frequency_counts_reps_not_model_rows() -> None:
    table = formal.selection_frequency(_per_rep())
    assert tuple(table.columns) == formal.SELECTION_COLUMNS
    by_model = table.set_index("model")
    assert by_model.loc["constant", "times_chosen"] == 1
    assert by_model.loc["t_learner", "times_chosen"] == 1
    assert np.allclose(table["share_chosen"], 0.5)
    assert np.allclose(table["mean_rank"], 1.5)


def test_calibration_summary_medians_and_chosen_scope() -> None:
    per_rep = _per_rep()
    all_models = formal.calibration_summary(per_rep).set_index("model")
    assert all_models.loc["constant", "n_reps"] == 2
    assert np.isclose(all_models.loc["constant", "median_calibration_slope"], 0.80)
    assert np.isclose(all_models.loc["t_learner", "median_calibration_slope"], 0.725)

    chosen = formal.calibration_summary(per_rep, chosen_only=True).set_index("model")
    assert chosen.loc["constant", "n_reps"] == 1
    assert np.isclose(chosen.loc["constant", "median_calibration_slope"], 0.90)
    assert np.isclose(chosen.loc["t_learner", "median_calibration_slope"], 0.95)
    assert (chosen["scope"] == "chosen_only").all()


def test_paired_difference_stays_within_rep_model_budget() -> None:
    grid = _grid()
    chosen = formal.paired_policy_difference(grid, BASELINE, chosen_only=True)
    greedy = chosen.loc[
        chosen["policy"] == "greedy_incremental_profit_per_cost"
    ].set_index("model")
    assert greedy.loc["constant", "n_pairs"] == 1
    assert np.isclose(greedy.loc["constant", "mean_diff_cny_per_user"], -1.0)
    assert np.isclose(greedy.loc["t_learner", "mean_diff_cny_per_user"], 1.0)
    # 池化 chosen 行（不按模型分组）会得到 0；按模型配对后才能看到两个相反符号。
    pooled = grid.loc[grid["chosen"]].pivot_table(
        index="policy", values="true_value_per_user", aggfunc="mean"
    )
    pooled_diff = (
        pooled.loc["greedy_incremental_profit_per_cost", "true_value_per_user"]
        - pooled.loc[BASELINE, "true_value_per_user"]
    )
    assert np.isclose(pooled_diff, 0.0)
    assert not np.allclose(
        [greedy.loc["constant", "mean_diff_cny_per_user"],
         greedy.loc["t_learner", "mean_diff_cny_per_user"]],
        pooled_diff,
    )
    all_models = formal.paired_policy_difference(grid, BASELINE, chosen_only=False)
    constant = all_models.loc[
        (all_models["model"] == "constant")
        & (all_models["policy"] == "greedy_incremental_profit_per_cost")
    ]
    assert int(constant["n_pairs"].iloc[0]) == 2


def test_paired_difference_requires_complete_policy_grid() -> None:
    grid = _grid().drop(index=0)
    with pytest.raises(ValueError, match="缺格"):
        formal.paired_policy_difference(grid, BASELINE)


def test_paired_difference_rejects_duplicate_cells() -> None:
    grid = pd.concat([_grid(), _grid().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="不唯一"):
        formal.paired_policy_difference(grid, BASELINE)


def test_oracle_regret_identifies_best_policy_per_model() -> None:
    table = formal.oracle_regret_summary(_grid())
    by_key = table.set_index(["model", "policy"])
    # constant 在 rep0 最优是 business(10)，rep1 最优是 business/greedy 并列 5：
    # greedy regret = (1 + 0) / 2 = 0.5；business 两 rep 都最优。
    assert np.isclose(
        by_key.loc[("constant", "greedy_incremental_profit_per_cost"),
                   "mean_regret_cny_per_user"], 0.5
    )
    assert np.isclose(
        by_key.loc[("constant", "business_rule_new_user_then_cart"),
                   "mean_regret_cny_per_user"], 0.0
    )
    assert np.isclose(
        by_key.loc[("t_learner", "greedy_incremental_profit_per_cost"),
                   "mean_regret_cny_per_user"], 0.0
    )
    # t：rep0 两者并列 8，rep1 greedy 11 胜 business 10 → business 均值 0.5。
    assert np.isclose(
        by_key.loc[("t_learner", "business_rule_new_user_then_cart"),
                   "mean_regret_cny_per_user"], 0.5
    )
    assert np.isclose(
        by_key.loc[("constant", "business_rule_new_user_then_cart"), "share_optimal"], 1.0
    )
    assert np.isclose(
        by_key.loc[("t_learner", "greedy_incremental_profit_per_cost"), "share_optimal"], 1.0
    )


def test_oracle_regret_excludes_unconstrained_reference() -> None:
    # 全发券参考不受预算约束；若把它算进"事后最优"，所有策略的后悔值都会被抬高。
    grid = _grid()
    reference = grid.loc[grid["policy"] == "no_coupon"].copy()
    reference["policy"] = "all_coupon_unconstrained_reference"
    reference["true_value_per_user"] = 1000.0
    with_reference = pd.concat([grid, reference], ignore_index=True)
    base = formal.oracle_regret_summary(grid)
    table = formal.oracle_regret_summary(with_reference)
    assert "all_coupon_unconstrained_reference" not in set(table["policy"])
    pd.testing.assert_frame_equal(
        table.reset_index(drop=True), base.reset_index(drop=True)
    )


def test_compliance_separates_hat_and_true_cost() -> None:
    table = formal.compliance_summary(_grid()).set_index(["model", "policy"])
    business = table.loc[("constant", "business_rule_new_user_then_cart")]
    greedy = table.loc[("constant", "greedy_incremental_profit_per_cost")]
    assert business["share_within_budget_by_hat"] == 1.0
    assert business["share_within_budget_by_true"] == 1.0
    assert np.isclose(business["mean_spend_to_budget_ratio"], 1.0)
    assert greedy["share_within_budget_by_hat"] == 1.0
    assert greedy["share_within_budget_by_true"] == 0.0
    assert np.isclose(greedy["mean_spend_to_budget_ratio"], 1.25)


def test_policy_value_summary_uses_reps_as_unit() -> None:
    table = formal.policy_value_summary(_grid()).set_index(
        ["model", "policy"]
    )
    constant = table.loc[("constant", "business_rule_new_user_then_cart")]
    assert constant["n_reps"] == 2
    assert np.isclose(constant["mean_true_value_per_user"], 7.5)
    assert np.isclose(constant["mean_predicted_value"], 8.0)


def test_require_formal_tables_accepts_complete_fixture() -> None:
    formal.require_formal_tables(
        _per_rep(), _grid(),
        expected_reps=2,
        expected_models=MODELS,
        expected_policies=POLICIES,
        expected_budgets=[0.04],
    )
    broken = _grid().drop(index=0)
    with pytest.raises(ValueError):
        formal.require_formal_tables(
            _per_rep(), broken,
            expected_reps=2,
            expected_models=MODELS,
            expected_policies=POLICIES,
            expected_budgets=[0.04],
        )


def test_require_formal_tables_rejects_two_chosen_models_in_a_rep() -> None:
    per_rep = _per_rep()
    per_rep.loc[(per_rep["rep_id"] == 0) & (per_rep["model"] == "t_learner"), "chosen"] = True
    with pytest.raises(ValueError, match="恰好一个 chosen"):
        formal.require_formal_tables(
            per_rep, _grid(),
            expected_reps=2,
            expected_models=MODELS,
            expected_policies=POLICIES,
            expected_budgets=[0.04],
        )
