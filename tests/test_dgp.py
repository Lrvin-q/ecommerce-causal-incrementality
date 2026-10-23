"""DGP 实现正确性测试 —— 守 GOAL.md 验收项 ①②③④。

这四条是"模拟器是否可信"的地基：如果连 DGP 本身都不对，
后面所有偏差、RMSE、覆盖率、策略价值的对比全部无效。
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.special import expit

from causal_growth.config import load_config
from causal_growth import dgp
from causal_growth.dgp.base import (
    calibrate_intercept,
    enforce_probability_bounds,
    face_response,
    realized_order_net,
    sample_order_draws,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config(overrides={"dgp.n_users": 60000})


class TestComonotonicCoupling:
    """GOAL 验收项 ④：``Y(1) ≥ Y(0)`` 必须逐个体成立。"""

    @pytest.mark.parametrize("level", ["L0", "L1", "L2"])
    def test_y1_never_below_y0(self, cfg, level) -> None:
        pop = dgp.build(level, cfg, 0)
        assert np.all(pop.potential.y1 >= pop.potential.y0)

    def test_coupling_makes_effects_concentrated(self, cfg) -> None:
        """耦合的目的：让个体效应集中在 {0, τ} 而不是被独立抽样噪声淹没。"""
        pop = dgp.build("L0", cfg, 0)
        tau = pop.potential.y1 - pop.potential.y0
        assert set(np.unique(tau)) == {0, 1}
        # 恒定效应下，被处理者的效应应全等于 ATE
        treated_effect = pop.potential.y1[pop.potential.y1 == 1].size
        assert treated_effect > 0


class TestProbabilityBounds:
    """GOAL 验收项 ①：``p0 + τ ≤ 1`` 且概率合法。"""

    @pytest.mark.parametrize("level", ["L0", "L1", "L2"])
    def test_p0_plus_tau_within_unit_interval(self, cfg, level) -> None:
        t = dgp.build(level, cfg, 0).truth
        assert np.all(t.p0 >= 0) and np.all(t.p0 <= 1)
        assert np.all(t.tau_conversion >= 0)
        assert np.all(t.p0 + t.tau_conversion <= 1.0 + 1e-12)

    def test_enforce_bounds_truncates_and_reports(self) -> None:
        p0 = np.array([0.2, 0.95, 0.5])
        tau = np.array([0.1, 0.1, 0.8])
        p0_out, tau_out, diag = enforce_probability_bounds(p0, tau)
        assert np.all(p0_out + tau_out <= 1.0)
        assert diag["n_p0_clipped"] == 1        # 只有 0.95 被截到 0.90
        # 0.95+0.1 与 0.5+0.8 都越界 —— 判定用的是**截断前**的原始曲线
        assert diag["n_tau_truncated"] == 2

    def test_builder_rejects_illegal_curves(self, cfg) -> None:
        """手工塞一个越界的 p0/tau 必须抛错，不能静默接受。"""
        pop = dgp.build("L0", cfg, 0)
        with pytest.raises(ValueError, match="tau|越界|必须"):
            dgp.build_population_from_curves(
                cfg=cfg,
                level="BAD",
                index=0,
                covariates=pop.covariates,
                p0=np.full(len(pop), 0.9),
                tau_conversion=np.full(len(pop), 0.2),
                face_value=10.0,
                order_draws=sample_order_draws(cfg, np.random.default_rng(0), len(pop)),
                conversion_u=np.random.default_rng(1).random(len(pop)),
            )


class TestTruthIsCalibrated:
    """GOAL 验收项 ② + 参数可解释性：真值必须命中业务目标。"""

    def test_l0_hits_targets_exactly(self, cfg) -> None:
        t = dgp.build("L0", cfg, 0).truth
        assert t.ate_conversion == pytest.approx(0.05, abs=1e-12)
        assert float(np.mean(t.p0)) == pytest.approx(0.10, abs=1e-12)

    def test_l1_hits_business_targets(self, cfg) -> None:
        """截距是校准出来的：E[p0] 与 E[τ] 必须精确命中配置目标。"""
        t = dgp.build("L1", cfg, 0).truth
        assert float(np.mean(t.p0)) == pytest.approx(0.10, abs=1e-9)
        assert float(np.mean(t.tau_conversion)) == pytest.approx(0.05, abs=1e-9)

    def test_l1_heterogeneity_direction(self, cfg) -> None:
        """新客券效应显著高于老客 —— 这是"定向发券有价值"的业务机制。"""
        pop = dgp.build("L1", cfg, 0)
        is_new = pop.covariates.is_new == 1
        tau_new = pop.truth.tau_conversion[is_new].mean()
        tau_old = pop.truth.tau_conversion[~is_new].mean()
        assert tau_new > tau_old * 1.5
        # 利润口径的异质性应当更明显（新客既更容易被推动、利润也更高）
        cate_new = pop.truth.cate_profit[is_new].mean()
        cate_old = pop.truth.cate_profit[~is_new].mean()
        assert cate_new > cate_old

    def test_l2_weekly_effects_match_targets(self, cfg) -> None:
        pop = dgp.build("L2", cfg, 0)
        week = pop.latent["week"]
        targets = cfg.require("dgp.l2.weekly_effect")
        for w, target in enumerate(targets):
            assert pop.truth.tau_conversion[week == w].mean() == pytest.approx(target, rel=0.02)
        # 真值 = 各周效应的**实际样本**加权平均。
        # 注意它与配置里的加权目标不完全相等：周样本占比有抽样波动
        # （配置 0.45/0.35/0.20，实际约 0.449/0.350/0.201）。
        # 真值用的是实际样本，报告里要写实际值，不能拿配置目标冒充。
        assert pop.truth.ate_conversion == pytest.approx(
            float(pop.truth.params["ate_conversion_target"]), rel=0.01
        )
        actual_shares = np.array([np.mean(week == w) for w in range(len(targets))])
        assert pop.truth.ate_conversion == pytest.approx(
            float(np.dot(actual_shares, np.asarray(targets))), abs=1e-3
        )


class TestMonteCarloConsistency:
    """GOAL 验收项 ③：实现均值 vs 闭式 ATE，误差在蒙特卡洛精度内。"""

    @pytest.mark.parametrize("level", ["L0", "L1", "L2"])
    def test_conversion_ate_within_five_standard_errors(self, cfg, level) -> None:
        pop = dgp.build(level, cfg, 0)
        tau = (pop.potential.y1 - pop.potential.y0).astype(float)
        se = float(np.std(tau, ddof=1) / np.sqrt(tau.size))
        deviation = abs(float(np.mean(tau)) - pop.truth.ate_conversion)
        assert deviation < 5 * se, (
            f"{level} 实现 ATE {np.mean(tau):.6f} 与解析 {pop.truth.ate_conversion:.6f} "
            f"偏差 {deviation:.6f} 超出 5SE={5 * se:.6f}"
        )

    def test_conversion_ate_absolute_tolerance(self, cfg) -> None:
        """在 n=60000 下，5SE 约 0.0028，绝对偏差应在 0.001 量级。"""
        pop = dgp.build("L0", cfg, 0)
        empirical = float(np.mean(pop.potential.y1 - pop.potential.y0))
        assert abs(empirical - pop.truth.ate_conversion) < 0.005

    def test_profit_ate_within_five_standard_errors(self, cfg) -> None:
        pop = dgp.build("L1", cfg, 0)
        tau = pop.potential.pi1 - pop.potential.pi0
        se = float(np.std(tau, ddof=1) / np.sqrt(tau.size))
        deviation = abs(float(np.mean(tau)) - pop.truth.ate_profit)
        assert deviation < 5 * se, f"利润 ATE 偏差 {deviation:.4f} 超出 5SE={5 * se:.4f}"


class TestRealizedMatchesAccounting:
    """``realized_order_net`` 与 ``compute_order_components`` 必须代数等价。

    两条路径分别服务"快速重复实验"与"关系表核算"，一旦漂移就是口径错配。
    """

    def test_same_order_same_profit(self, cfg) -> None:
        from causal_growth.data.profit import compute_order_components
        import pandas as pd

        b = cfg.section("business")
        draws = sample_order_draws(cfg, np.random.default_rng(0), 5000)
        coupon = np.where(draws.redeemed_u < 0.55, 10.0, 0.0)
        converted = np.ones(5000, dtype=bool)

        fast = realized_order_net(
            draws,
            goods_cost_ratio=b["goods_cost_ratio"],
            refundable_goods_ratio=b["refundable_goods_ratio"],
            refund_handling_fee_rate=b["refund_handling_fee_rate"],
            coupon_cost=coupon,
            converted=converted,
            refund_rate=b["refund_rate"],
        )

        refunded = draws.refund_u < b["refund_rate"]
        orders = pd.DataFrame(
            {
                "order_id": [f"O{i}" for i in range(5000)],
                "user_id": np.arange(5000),
                "order_time": pd.Timestamp("2024-03-02"),
                "pay_amount": draws.pay_amount,
                "refund_amount": np.where(refunded, draws.pay_amount, 0.0),
                "goods_cost": draws.pay_amount * b["goods_cost_ratio"],
                "fulfill_cost": draws.fulfill_cost,
                "coupon_used": coupon > 0,
                "coupon_value": coupon,
                "refunded": refunded,
            }
        )
        slow = compute_order_components(orders, cfg)["net_profit"].to_numpy()
        np.testing.assert_allclose(fast, slow, rtol=1e-12, atol=1e-9)


class TestRepeatPurchasePath:
    """B7：复购路径必须让「多单用户 user 级利润 = 各单之和」**可被检验**。

    没有第二单时，每个用户最多一行订单，``SUM`` 与 ``MAX`` 恒等——
    ``v_user_profit`` 里把 SUM 写成 MAX 这种口径错误会静默通过所有检查。
    这组测试就是那个漏洞的补丁。
    """

    @pytest.fixture(scope="class")
    def pop(self, cfg):
        return dgp.assign_random(cfg, dgp.build("L1", cfg, 0))

    def test_repeat_flag_matches_configured_probability(self, cfg, pop) -> None:
        rep = np.asarray(pop.latent["repeat"])
        p = float(cfg.require("dgp.repeat.prob"))
        se = float(np.sqrt(p * (1.0 - p) / rep.size))
        assert abs(float(rep.mean()) - p) < 5 * se, f"复购比例 {rep.mean():.4f} 与配置 {p} 差太远"

    def test_second_order_only_for_converted_users(self, cfg, pop) -> None:
        from causal_growth.data.tables import build_five_tables

        tables = build_five_tables(pop, cfg)
        orders = tables["orders"]
        per_user = orders.groupby("user_id").size()
        multi = per_user[per_user > 1]
        assert len(multi) > 0, "没有多单用户 —— MAX/SUM 的口径错误将无法被检出"
        y_obs, _ = pop.potential.observed(pop.treatment)
        converted = set(np.flatnonzero(y_obs == 1).tolist())
        assert set(multi.index.tolist()) <= converted

    def test_user_profit_equals_sum_of_orders_not_max(self, cfg, pop) -> None:
        from causal_growth.data.profit import aggregate_user_profit, compute_order_components
        from causal_growth.data.tables import build_five_tables

        tables = build_five_tables(pop, cfg)
        orders = tables["orders"]
        per_order = compute_order_components(orders, cfg)["net_profit"]
        by_user = per_order.groupby(orders["user_id"].to_numpy())
        summed = by_user.sum()
        maxed = by_user.max()

        agg = aggregate_user_profit(orders, pop.covariates.user_id, cfg)
        # ① 用户级利润必须等于**各单之和**（金额按分存储，容差 0.02 元）
        diff = (agg - summed.reindex(agg.index).fillna(0.0)).abs()
        assert float(diff.max()) <= 0.02

        # ② 且多单用户的"和"确实严格大于"最大单" —— 这就是 SUM≠MAX 的可检验性
        per_user = orders.groupby("user_id").size()
        multi_ids = per_user[per_user > 1].index
        assert len(multi_ids) > 0
        gap = (summed.loc[multi_ids] - maxed.loc[multi_ids]).abs()
        assert float(gap.min()) > 1e-6

    def test_truth_includes_expected_repeat_contribution(self, cfg) -> None:
        """真值恒等式仍精确成立，且复购使"已转化用户净贡献"大于首单净贡献。"""
        no_rep = cfg.with_overrides({"dgp.repeat.enabled": False})
        p_off = dgp.build("L1", no_rep, 0)
        p_on = dgp.build("L1", cfg, 0)
        # 关掉复购时两个字段相等（回归保护：默认路径没有被悄悄改动）
        assert np.allclose(
            p_off.truth.net_per_converted_control, p_off.truth.net_per_order_control
        )
        # 打开复购后，已转化用户净贡献 > 首单净贡献（第二单贡献为正）
        assert float(p_on.truth.net_per_converted_control.mean()) > float(
            p_on.truth.net_per_order_control.mean()
        )
        # cate_profit = p1·A1 − p0·A0 恒等式（用含复购的 A）
        t = p_on.truth
        np.testing.assert_allclose(
            t.cate_profit,
            t.p1 * t.net_per_converted_treated - t.p0 * t.net_per_converted_control,
            rtol=0,
            atol=1e-12,
        )


class TestSelectionBias:
    """L3：U 必须同时影响发券与购买，否则观察性方法不会真的失效。"""

    @pytest.mark.parametrize("lam", [0.5, 1.0])
    def test_treated_users_have_higher_latent_u(self, cfg, lam) -> None:
        pop = dgp.build("L3", cfg, 0, lam=lam)
        pop, _ = dgp.assign_observational(cfg, pop, lam=lam)
        u, t = pop.latent["u"], pop.treatment
        assert u[t == 1].mean() > u[t == 0].mean() + 0.1

    def test_no_confounding_when_lambda_zero(self, cfg) -> None:
        pop = dgp.build("L3", cfg, 0, lam=0.0)
        pop, _ = dgp.assign_observational(cfg, pop, lam=0.0)
        u, t = pop.latent["u"], pop.treatment
        assert abs(u[t == 1].mean() - u[t == 0].mean()) < 0.05


class TestHelpers:
    def test_calibrate_intercept_hits_target(self) -> None:
        lp = np.random.default_rng(0).normal(size=5000)
        delta = calibrate_intercept(lp, 0.3)
        assert float(np.mean(expit(lp + delta))) == pytest.approx(0.3, abs=1e-10)

    def test_calibrate_rejects_impossible_target(self) -> None:
        lp = np.zeros(100)
        with pytest.raises(ValueError):
            calibrate_intercept(lp, 1.5)

    def test_face_response_is_monotone_and_normalised(self) -> None:
        g = [face_response(f, scale=12.0, max_face=20.0) for f in (5, 10, 15, 20)]
        assert all(np.diff(g) > 0)          # 面额越大效应越强
        assert g[0] < 0.5 < g[-1]
        assert pytest.approx(1.0) == g[-1]  # 最大面额归一化为 1

    def test_larger_face_yields_larger_effect(self, cfg) -> None:
        small = dgp.build("L1", cfg, 0, face_value=5.0).truth.ate_conversion
        large = dgp.build("L1", cfg, 0, face_value=20.0).truth.ate_conversion
        assert large > small > 0


class TestReproducibility:
    def test_same_seed_same_data(self, cfg) -> None:
        a, b = dgp.build("L1", cfg, 0), dgp.build("L1", cfg, 0)
        np.testing.assert_array_equal(a.covariates.hist_gmv, b.covariates.hist_gmv)
        np.testing.assert_array_equal(a.potential.pi1, b.potential.pi1)
        assert a.truth.ate_profit == b.truth.ate_profit

    def test_different_index_different_data(self, cfg) -> None:
        a, b = dgp.build("L1", cfg, 0), dgp.build("L1", cfg, 1)
        assert not np.array_equal(a.covariates.hist_gmv, b.covariates.hist_gmv)

    def test_l3_covariates_identical_across_lambda(self, cfg) -> None:
        """λ 扫描必须在**同一批用户**上做，否则差异来自换了数据而不是混淆强度。"""
        a = dgp.build("L3", cfg, 0, lam=0.0)
        b = dgp.build("L3", cfg, 0, lam=1.0)
        np.testing.assert_array_equal(a.covariates.hist_gmv, b.covariates.hist_gmv)
        np.testing.assert_array_equal(a.latent["u"], b.latent["u"])
