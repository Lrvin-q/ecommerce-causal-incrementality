"""E 阶段策略接口的契约测试。

这些测试**不测算法**（算法尚未实现），只锁住三件事：
1. 数据结构会拒绝违反口径的输入（非法算法名、负成本、非布尔 mask、不闭合的误差分解）；
2. 名实相符的边界被编码进类型（MILP 只有 gap=0 才允许声称最优）；
3. 接口函数确实存在且明确未实现——避免"以为做完了"。
"""

from __future__ import annotations

import numpy as np
import pytest

from causal_growth.policy import v3_policy as pol


def _mask(*bits: bool) -> np.ndarray:
    return np.array(bits, dtype=np.bool_)


def test_selection_rejects_unknown_algorithm() -> None:
    with pytest.raises(ValueError, match="未注册的算法名"):
        pol.Selection(mask=_mask(True), predicted_value=1.0, predicted_cost=0.1, algorithm="knapsack_dp")


def test_selection_requires_boolean_mask() -> None:
    with pytest.raises(TypeError, match="布尔"):
        pol.Selection(mask=np.array([1, 0]), predicted_value=1.0, predicted_cost=0.1, algorithm="greedy")


def test_selection_rejects_negative_cost() -> None:
    with pytest.raises(ValueError, match="不能为负"):
        pol.Selection(mask=_mask(True), predicted_value=1.0, predicted_cost=-0.01, algorithm="greedy")


def test_milp_gap_blocks_optimality_claim() -> None:
    """gap > 0 时不得声称最优——这是名实相符的硬约束。"""
    selection = pol.Selection(mask=_mask(True), predicted_value=1.0, predicted_cost=0.1, algorithm="milp")
    tight = pol.MilpResult(selection=selection, status="optimal", incumbent=10.0, bound=10.0,
                           relative_gap=0.0, time_limit_seconds=60.0)
    loose = pol.MilpResult(selection=selection, status="time_limit", incumbent=9.9, bound=10.0,
                           relative_gap=0.001, time_limit_seconds=60.0)
    assert tight.may_claim_optimal is True
    assert loose.may_claim_optimal is False


def test_milp_rejects_bound_below_incumbent() -> None:
    selection = pol.Selection(mask=_mask(True), predicted_value=1.0, predicted_cost=0.1, algorithm="milp")
    with pytest.raises(ValueError, match="上界不得小于"):
        pol.MilpResult(selection=selection, status="optimal", incumbent=10.0, bound=9.0,
                       relative_gap=0.0, time_limit_seconds=60.0)


def test_error_decomposition_must_close() -> None:
    """learning + optimization 必须等于 total，否则说明分解口径错。"""
    with pytest.raises(ValueError, match="不闭合"):
        pol.ErrorDecomposition(learning_error=0.3, optimization_error=0.2, total_regret=0.9)


def test_error_decomposition_accepts_closed_identity() -> None:
    decomposition = pol.ErrorDecomposition(learning_error=0.3, optimization_error=0.2, total_regret=0.5)
    assert abs(decomposition.identity_residual) <= pol.ERROR_IDENTITY_TOLERANCE


def test_budget_plan_requires_buffered_above_expected() -> None:
    with pytest.raises(ValueError, match="缓冲预算"):
        pol.BudgetPlan(expected=1.0, buffered=0.9, worst_case=10.0, n_target=100)


def test_budget_plan_rejects_negative_and_bad_n() -> None:
    with pytest.raises(ValueError, match="预算不能为负"):
        pol.BudgetPlan(expected=-1.0, buffered=1.0, worst_case=1.0, n_target=100)
    with pytest.raises(ValueError, match="目标用户数"):
        pol.BudgetPlan(expected=1.0, buffered=1.25, worst_case=10.0, n_target=0)


def test_tie_break_is_stable_by_user_id() -> None:
    order = pol.tie_break_order(["u3", "u1", "u2"])
    assert order.tolist() == [1, 2, 0]


def test_cost_floor_is_enforced() -> None:
    pol.require_non_negative_cost(np.array([1.0, 2.0]), floor=1e-6)
    with pytest.raises(ValueError, match="严格为正"):
        pol.require_non_negative_cost(np.array([1.0, 0.0]), floor=1e-6)


def test_length_mismatch_is_rejected_not_broadcast() -> None:
    with pytest.raises(ValueError, match="长度不一致"):
        pol.require_same_length(np.zeros(3), np.zeros(2))


@pytest.mark.parametrize(
    "call",
    [
        lambda: pol.fit_cost_model(None, None),
        lambda: pol.predict_expected_cost(None, None, None),
        lambda: pol.greedy_by_ratio(np.zeros(1), np.ones(1), 1.0),
        lambda: pol.local_swap(None, np.zeros(1), np.ones(1), 1.0, 10, 500),
        lambda: pol.cent_exact_dp(np.zeros(1, dtype=np.int64), np.ones(1, dtype=np.int64), 100),
        lambda: pol.milp_select(np.zeros(1), np.ones(1), 1.0, 60.0, 0.001),
        lambda: pol.lp_upper_bound(np.zeros(1), np.ones(1), 1.0),
        lambda: pol.build_budget_plan(None, 100),
        lambda: pol.audit_budget(None, np.zeros(1), None),
        lambda: pol.policy_value(_mask(True), np.zeros(1)),
        lambda: pol.truth_regret(_mask(True), _mask(True), np.zeros(1)),
        lambda: pol.decompose_error(_mask(True), np.zeros(1), np.zeros(1), _mask(True)),
    ],
)
def test_interfaces_are_declared_but_not_implemented(call) -> None:
    """E 阶段实现前，每个接口都必须明确抛 NotImplementedError，而不是静默返回。"""
    with pytest.raises(NotImplementedError):
        call()


def test_policy_and_solver_names_match_the_contract() -> None:
    """9 个候选策略、5 个求解器，名称与 policy.yaml 一一对应。"""
    assert len(pol.POLICY_NAMES) == 9
    assert set(pol.SOLVER_NAMES) == {"greedy", "local_swap", "cent_exact_dp", "milp", "lp_relaxation"}
    assert "greedy_incremental_profit_per_cost" in pol.POLICY_NAMES
    assert "greedy_local_swap" in pol.POLICY_NAMES
