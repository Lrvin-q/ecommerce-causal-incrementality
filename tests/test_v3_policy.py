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
        pol.BudgetPlan(expected=1.0, buffered=0.9, worst_case=10.0, n_target=100, face_value=10.0)


def test_budget_plan_rejects_negative_and_bad_n() -> None:
    with pytest.raises(ValueError, match="预算不能为负"):
        pol.BudgetPlan(expected=-1.0, buffered=1.0, worst_case=1.0, n_target=100, face_value=10.0)
    with pytest.raises(ValueError, match="目标用户数"):
        pol.BudgetPlan(expected=1.0, buffered=1.25, worst_case=10.0, n_target=0, face_value=10.0)


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


def test_policy_and_solver_names_match_the_contract() -> None:
    """9 个候选策略、5 个求解器，名称与 policy.yaml 一一对应。"""
    assert len(pol.POLICY_NAMES) == 9
    assert set(pol.SOLVER_NAMES) == {"greedy", "local_swap", "cent_exact_dp", "milp", "lp_relaxation"}
    assert "greedy_incremental_profit_per_cost" in pol.POLICY_NAMES
    assert "greedy_local_swap" in pol.POLICY_NAMES


# ---------------------------------------------------------------------------
# 求解器行为：冻结反例、枚举互证、顺序约束
# ---------------------------------------------------------------------------
def _brute_force(value: np.ndarray, cost: np.ndarray, budget: float) -> tuple[float, np.ndarray]:
    """2^n 枚举的最优解（仅用于 n ≤ 12 的互证，不进生产路径）。"""
    n = value.size
    best_value, best_mask = -np.inf, np.zeros(n, dtype=np.bool_)
    for bits in range(1 << n):
        mask = np.array([(bits >> i) & 1 for i in range(n)], dtype=np.bool_)
        if cost[mask].sum() <= budget + 1e-9:
            candidate = float(value[mask].sum())
            if candidate > best_value:
                best_value, best_mask = candidate, mask
    return best_value, best_mask


def test_frozen_counterexample_greedy_loses_a_third() -> None:
    """policy.yaml 冻结反例：贪心得 12，最优得 18，损失 33%。

    这条是 greedy 不能声称"近似最优"的硬证据；若代码改动导致它不再复现，
    说明目标或成本口径被动过。
    """
    value = np.array([12.0, 9.0, 9.0])
    cost = np.array([6.0, 5.0, 5.0])
    budget = 10.0

    greedy = pol.greedy_by_ratio(value, cost, budget)
    assert greedy.selected_count == 1, "贪心应只选比值最高的第一件"
    assert greedy.predicted_value == pytest.approx(12.0)

    exact = pol.cent_exact_dp(np.array([1200, 900, 900], dtype=np.int64),
                              np.array([600, 500, 500], dtype=np.int64), 1000)
    assert exact.selected_count == 2, "精确解应选后两件"
    assert exact.predicted_value == pytest.approx(1800.0), "单位是分"

    loss = (1800.0 - 1200.0) / 1800.0
    assert loss == pytest.approx(1.0 / 3.0, abs=1e-9)


def test_exact_dp_matches_brute_force_on_small_instances() -> None:
    """分币精确 DP 必须与 2^n 枚举在同一整数化问题上给出同一最优值。"""
    from causal_growth.rng import child_rng

    rng = child_rng(master_seed=20240101, stream="test.policy.enum", index=0)
    for trial in range(5):
        n = 10
        value_cents = rng.integers(1, 2000, size=n)
        cost_cents = rng.integers(100, 800, size=n)
        budget_cents = int(rng.integers(800, 2400))

        exact = pol.cent_exact_dp(value_cents, cost_cents, budget_cents)
        expected, _ = _brute_force(value_cents.astype(float), cost_cents.astype(float), float(budget_cents))
        assert exact.predicted_value == pytest.approx(expected), f"trial {trial}"


def test_milp_objective_matches_exact_dp_in_yuan() -> None:
    """MILP 与分币 DP 在换算到元后应给出同一个最优目标值。"""
    value = np.array([12.0, 9.0, 9.0, 7.0, 4.0])
    cost = np.array([6.0, 5.0, 5.0, 3.0, 2.0])
    budget = 10.0

    milp = pol.milp_select(value, cost, budget, time_limit_seconds=30.0, relative_gap=0.0)
    assert milp.status == "optimal"
    assert milp.may_claim_optimal is True

    exact = pol.cent_exact_dp((value * 100).astype(np.int64), (cost * 100).astype(np.int64), 1000)
    assert milp.selection.predicted_value == pytest.approx(exact.predicted_value / 100.0)


def test_solver_ordering_greedy_le_swap_le_exact_le_lp() -> None:
    """四种口径的相对位置：贪心 ≤ 局部交换 ≤ 精确 ≤ LP 上界。

    **必须在同一个分币整数化问题上比较**：若用浮点成本再单独取整给 DP，
    两者面对的预算会差几分钱，最优解本来就可能不同（见接口文档 §2.2）。
    """
    from causal_growth.rng import child_rng

    rng = child_rng(master_seed=20240101, stream="test.policy.order", index=0)
    for trial in range(5):
        n = 40
        value_cents = rng.integers(10, 500, size=n)
        cost_cents = rng.integers(10, 100, size=n)
        budget_cents = int(rng.integers(200, 800))

        value = value_cents.astype(np.float64)
        cost = cost_cents.astype(np.float64)
        budget = float(budget_cents)

        greedy = pol.greedy_by_ratio(value, cost, budget)
        swap = pol.local_swap(greedy, value, cost, budget, max_passes=10, exchange_candidate_limit=500)
        exact = pol.cent_exact_dp(value_cents, cost_cents, budget_cents)
        upper = pol.lp_upper_bound(value, cost, budget)

        assert greedy.predicted_value <= swap.predicted_value + 1e-9, f"trial {trial}: swap 不该更差"
        assert swap.predicted_value <= exact.predicted_value + 1e-9, f"trial {trial}: swap 不该超过精确解"
        assert exact.predicted_value <= upper + 1e-9, f"trial {trial}: 精确解不该超过 LP 上界"


def test_all_solvers_respect_the_budget() -> None:
    value = np.array([5.0, 4.0, 3.0, 2.0])
    cost = np.array([3.0, 2.5, 2.0, 1.0])
    budget = 4.5

    greedy = pol.greedy_by_ratio(value, cost, budget)
    swap = pol.local_swap(greedy, value, cost, budget, max_passes=5, exchange_candidate_limit=10)
    milp = pol.milp_select(value, cost, budget, time_limit_seconds=10.0, relative_gap=0.0)
    for selection in (greedy, swap, milp.selection):
        assert selection.predicted_cost <= budget + 1e-9, f"{selection.algorithm} 超预算"


def test_greedy_rejects_unknown_tie_break() -> None:
    with pytest.raises(ValueError, match="user_id_ascending"):
        pol.greedy_by_ratio(np.array([1.0]), np.array([1.0]), 1.0, tie_break="random")


def test_empty_pool_returns_empty_selection() -> None:
    empty = np.zeros(0)
    selection = pol.greedy_by_ratio(empty, empty, 1.0)
    assert selection.selected_count == 0
    assert pol.lp_upper_bound(empty, empty, 1.0) == 0.0


def test_greedy_skips_unaffordable_and_keeps_going() -> None:
    """装不下的跳过，不许直接中断——否则会白白浪费预算。"""
    value = np.array([100.0, 1.0, 1.0])
    cost = np.array([10.0, 1.0, 1.0])
    selection = pol.greedy_by_ratio(value, cost, budget=10.0)
    assert selection.mask.tolist() == [True, False, False]
    # 预算刚好装下第一件；若改成跳过策略，后两件也装不下（10 元预算已用尽）


def test_local_swap_never_worse_than_initial() -> None:
    value = np.array([3.0, 3.0, 2.9, 2.9])
    cost = np.array([2.0, 2.0, 2.0, 2.0])
    initial = pol.greedy_by_ratio(value, cost, budget=4.0)
    improved = pol.local_swap(initial, value, cost, budget=4.0, max_passes=5, exchange_candidate_limit=10)
    assert improved.predicted_value >= initial.predicted_value - 1e-12


# ---------------------------------------------------------------------------
# 预算三口径
# ---------------------------------------------------------------------------
def test_budget_plan_from_frozen_config() -> None:
    """三种口径必须同时给出，数值直接来自 policy.yaml。"""
    from causal_growth.v3_config import load_v3_protocol

    cfg = load_v3_protocol().config
    plan = pol.build_budget_plan(cfg, n_target=200_000)

    assert plan.expected == pytest.approx(0.2 * 200_000)
    assert plan.buffered == pytest.approx(plan.expected * 1.25)
    assert plan.face_value == pytest.approx(10.0)
    assert plan.max_recipients_face == 4_000
    assert plan.worst_case == pytest.approx(10.0 * 4_000)


def test_budget_plan_rejects_non_positive_n() -> None:
    from causal_growth.v3_config import load_v3_protocol

    cfg = load_v3_protocol().config
    with pytest.raises(ValueError, match="目标用户数"):
        pol.build_budget_plan(cfg, n_target=0)


def test_face_bound_floor_rounds_down() -> None:
    """面额口径下人数必须向下取整，不能因为余数多给一张券。"""
    plan = pol.BudgetPlan(expected=95.0, buffered=118.75, worst_case=90.0, n_target=100, face_value=10.0)
    assert plan.max_recipients_face == 9


def test_audit_budget_flags_overrun_and_never_claims_hard_cap() -> None:
    plan = pol.BudgetPlan(expected=100.0, buffered=125.0, worst_case=100.0, n_target=500, face_value=10.0)
    mask = np.array([True, True, False, False], dtype=np.bool_)
    selection = pol.Selection(mask=mask, predicted_value=5.0, predicted_cost=4.0, algorithm="greedy")

    within = pol.audit_budget(selection, np.array([30.0, 30.0, 0.0, 0.0]), plan)
    assert within["observed_cost_total"] == pytest.approx(60.0)
    assert within["within_expected"] is True
    assert within["face_bound_respected"] is True
    assert within["hard_cap_claim_allowed"] is False

    overrun = pol.audit_budget(selection, np.array([70.0, 60.0, 0.0, 0.0]), plan)
    assert overrun["observed_cost_total"] == pytest.approx(130.0)
    assert overrun["within_expected"] is False
    assert overrun["within_buffered"] is False
    assert overrun["hard_cap_claim_allowed"] is False


# ---------------------------------------------------------------------------
# 策略价值与误差分解
# ---------------------------------------------------------------------------
def test_policy_value_uses_all_users_as_denominator() -> None:
    """分母是全部目标用户，不是被选中的人——否则不同预算下的价值不可比。"""
    profit = np.array([1.0, 2.0, 3.0, 4.0])
    mask = np.array([True, False, True, False], dtype=np.bool_)
    assert pol.policy_value(mask, profit) == pytest.approx((1.0 + 3.0) / 4)


def test_truth_regret_is_zero_for_the_optimal_mask() -> None:
    profit = np.array([1.0, 2.0])
    mask = np.array([True, False], dtype=np.bool_)
    assert pol.truth_regret(mask, mask, profit) == pytest.approx(0.0)


def test_decompose_error_closes_and_allows_negative_optimization() -> None:
    """optimization_error 允许为负：τ̂ 有噪声时，"τ̂ 下最优"在真值下可能更差。"""
    profit = np.array([10.0, -5.0, 0.0, 0.0])
    truth_optimal = np.array([True, False, False, False], dtype=np.bool_)
    oracle_under_hat = np.array([False, True, False, False], dtype=np.bool_)
    actual = np.array([False, False, True, False], dtype=np.bool_)

    decomposition = pol.decompose_error(actual, oracle_under_hat, truth_optimal, profit)

    assert decomposition.learning_error == pytest.approx((10.0 - (-5.0)) / 4)
    assert decomposition.optimization_error == pytest.approx((-5.0 - 0.0) / 4)
    assert decomposition.optimization_error < 0
    assert decomposition.total_regret == pytest.approx(10.0 / 4)
    assert abs(decomposition.identity_residual) <= pol.ERROR_IDENTITY_TOLERANCE


# ---------------------------------------------------------------------------
# 成本模型（两阶段）
# ---------------------------------------------------------------------------
def _synthetic_cost_data(n: int = 2000, seed_index: int = 0):
    """构造购买与核销都受 X 驱动的合成数据，附带真实期望成本。"""
    from causal_growth.rng import child_rng

    rng = child_rng(master_seed=20240101, stream="test.policy.cost", index=seed_index)
    X = rng.normal(size=(n, 3))
    p_purchase = 1.0 / (1.0 + np.exp(-(2.0 * X[:, 0] - 1.0)))
    bought = rng.binomial(1, p_purchase).astype(np.int64)
    p_redeem = 1.0 / (1.0 + np.exp(-(2.0 * X[:, 1])))
    redeemed = (bought == 1) & (rng.random(n) < p_redeem)
    coupon_cost = redeemed.astype(np.float64) * 10.0
    treatment = np.ones(n, dtype=np.int64)
    return X, treatment, bought, coupon_cost, 10.0 * p_purchase * p_redeem


def test_cost_model_recovers_expected_cost_structure() -> None:
    """两阶段模型应恢复 E[券成本] = 面额 × P(购买) × P(核销|购买)。

    这是**结构与量级**检查，不是精度承诺：LightGBM 在 2000 样本上必有噪声，
    所以只断言相关性足够高、取值区间合法。
    """
    from causal_growth.v3_config import load_v3_protocol

    cfg = load_v3_protocol().config
    X, treatment, bought, coupon_cost, true_expected = _synthetic_cost_data()

    model = pol.fit_cost_model(X, treatment, bought, coupon_cost, cfg)
    predicted = pol.predict_expected_cost(model, X, cfg)

    assert predicted.shape == (X.shape[0],)
    assert predicted.min() >= float(cfg.require("policy.cost_model.cost_floor_cny")) - 1e-12
    assert predicted.max() <= 10.0 + 1e-9
    correlation = float(np.corrcoef(predicted, true_expected)[0, 1])
    assert correlation > 0.75, f"预测与真实期望成本相关性过低：{correlation:.3f}"


def test_cost_model_rejects_samples_without_treated() -> None:
    from causal_growth.v3_config import load_v3_protocol

    cfg = load_v3_protocol().config
    X = np.zeros((100, 3))
    with pytest.raises(ValueError, match="treatment=1"):
        pol.fit_cost_model(X, np.zeros(100, dtype=np.int64), np.zeros(100, dtype=np.int64),
                           np.zeros(100), cfg)


def test_cost_model_rejects_constant_purchase_label() -> None:
    from causal_growth.v3_config import load_v3_protocol

    cfg = load_v3_protocol().config
    X = np.zeros((100, 3))
    with pytest.raises(ValueError, match="购买标签"):
        pol.fit_cost_model(X, np.ones(100, dtype=np.int64), np.zeros(100, dtype=np.int64),
                           np.zeros(100), cfg)


def test_predict_expected_cost_rejects_1d_input() -> None:
    from causal_growth.v3_config import load_v3_protocol

    cfg = load_v3_protocol().config
    with pytest.raises(ValueError, match="二维"):
        pol.predict_expected_cost(None, np.zeros(5), cfg)


# ---------------------------------------------------------------------------
# 排序类策略与随机基线
# ---------------------------------------------------------------------------
def test_rank_and_select_breaks_ties_by_user_id_ascending() -> None:
    """同分时按 user_id 升序——这是 policy.yaml 冻结的 tie-break，不能交给不稳定排序。"""
    score = np.array([0.0, 5.0, 5.0, 1.0])
    cost = np.ones(4)
    user_id = np.array([3, 2, 1, 4])

    selection = pol.rank_and_select(score, cost, budget=2.0, user_id=user_id,
                                    algorithm="incremental_profit_rank")

    assert selection.mask.tolist() == [False, True, True, False], "应选中两个 5 分且 user_id 较小的"
    assert selection.selected_count == 2


def test_rank_and_select_stops_at_non_positive_scores() -> None:
    score = np.array([-1.0, 0.5])
    cost = np.ones(2)
    user_id = np.array([1, 2])

    selection = pol.rank_and_select(score, cost, budget=10.0, user_id=user_id,
                                    algorithm="incremental_profit_rank")

    assert selection.mask.tolist() == [False, True], "负分的人不该因为预算宽裕就被选中"


def test_rank_and_select_rejects_unregistered_algorithm_name() -> None:
    with pytest.raises(ValueError, match="未注册的算法名"):
        pol.rank_and_select(np.array([1.0]), np.array([1.0]), 1.0, np.array([1]), "our_best_policy")


def test_random_under_budget_is_reproducible_and_respects_budget() -> None:
    from causal_growth.rng import child_rng

    value = np.ones(100)
    cost = np.full(100, 0.5)

    first = pol.random_under_budget(value, cost, budget=10.0, rng=child_rng(20240101, "test.rand", 0))
    second = pol.random_under_budget(value, cost, budget=10.0, rng=child_rng(20240101, "test.rand", 0))

    assert first.mask.tolist() == second.mask.tolist(), "同一种子必须给出同一名单"
    assert first.selected_count == 20, "10 元预算 / 每人 0.5 元 = 20 人"
    assert first.predicted_cost <= 10.0 + 1e-9
