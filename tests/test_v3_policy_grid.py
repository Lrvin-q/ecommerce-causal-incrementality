"""E 网格编排模块的契约测试（不进 DGP，只测输入/输出口径）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth.policy import v3_policy_grid as grid
from causal_growth.rng import child_rng
from causal_growth.v3_config import load_v3_protocol

BUDGET_TOLERANCE = 1e-9


@pytest.fixture(scope="module")
def cfg():
    return load_v3_protocol().config


def _frame(n: int = 400) -> pd.DataFrame:
    rng = child_rng(20240101, "test.v3_policy_grid", 0)
    propensity = rng.uniform(0.05, 0.9, n)
    cart_value = np.round(rng.lognormal(3.5, 0.6, n), 2)
    tau_true = rng.normal(0.5, 0.8, n)
    return pd.DataFrame({
        "user_id": np.arange(n, dtype=np.int64),
        "is_new": (rng.random(n) < 0.4).astype(np.int64),
        "cart_value": cart_value,
        "purchase_propensity": propensity,
        "predicted_profit": propensity * cart_value * 0.1,
        "tau_hat": tau_true + rng.normal(0.0, 0.5, n),
        "cost_hat": np.maximum(10.0 * propensity * 0.5, 0.01),
        "tau_true": tau_true,
        "cost_true": 10.0 * (rng.random(n) < 0.2),
    })


def test_grid_is_budgets_times_policies(cfg) -> None:
    frame = _frame()
    result = grid.evaluate_policy_grid(frame, cfg)
    budgets = [float(value) for value in cfg.require("policy.budget.per_user_grid_cny")]
    assert tuple(result.columns) == grid.GRID_COLUMNS
    assert len(result) == len(budgets) * len(grid.POLICIES)
    assert sorted(result["per_user_budget_cny"].unique()) == sorted(budgets)
    assert set(result["policy"]) == set(grid.POLICIES)
    assert result["within_budget_by_hat"].dtype == bool
    assert result["within_budget_by_true"].dtype == bool


def test_reference_policy_budget_flags_follow_own_spend(cfg) -> None:
    frame = _frame()
    result = grid.evaluate_policy_grid(frame, cfg)
    reference = result.loc[
        result["policy"] == "all_coupon_unconstrained_reference"
    ].set_index("per_user_budget_cny")
    for budget, row in reference.iterrows():
        assert row["within_budget_by_hat"] == (
            row["predicted_cost"] <= row["budget_cny"] + BUDGET_TOLERANCE
        )
        assert row["within_budget_by_true"] == (
            row["actual_spend_cny"] <= row["budget_cny"] + BUDGET_TOLERANCE
        )
    no_coupon = result.loc[result["policy"] == "no_coupon"]
    assert (no_coupon["n_selected"] == 0).all()
    assert (no_coupon["true_value_per_user"] == 0.0).all()


def test_grid_frame_rejects_broken_inputs(cfg) -> None:
    frame = _frame()
    with pytest.raises(ValueError, match="缺列"):
        grid.require_grid_frame(frame.drop(columns=["tau_true"]))
    with_nan = frame.copy()
    with_nan.loc[0, "tau_hat"] = np.nan
    with pytest.raises(ValueError, match="非有限值"):
        grid.require_grid_frame(with_nan)
    zero_cost = frame.copy()
    zero_cost.loc[0, "cost_hat"] = 0.0
    with pytest.raises(ValueError, match="cost_hat"):
        grid.require_grid_frame(zero_cost)
    negative_truth = frame.copy()
    negative_truth.loc[0, "cost_true"] = -1.0
    with pytest.raises(ValueError, match="cost_true"):
        grid.require_grid_frame(negative_truth)
