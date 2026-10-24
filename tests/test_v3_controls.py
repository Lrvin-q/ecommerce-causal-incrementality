"""合成数据 / 已知 DGP：人工同质化的合法性、真实成本与审计隔离。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth.config import ConfigError
from causal_growth.dgp.v3_amounts import amount_distribution, conditional_user_expectation
from causal_growth.dgp.v3_controls import audit_common_feasible_mask, solve_l0_profit_control
from causal_growth.dgp.v3_timing import timing_coefficients
from causal_growth.v3_config import load_v3_protocol
from causal_growth.v3_numerics import load_v3_numerics


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


def _probabilities(cfg):
    p0 = float(cfg.require("dgp.l0.baseline_purchase_probability"))
    return p0, p0 + float(cfg.require("dgp.l0.purchase_increment"))


@pytest.mark.parametrize("scenario", ["L0_Pi_equal_cost", "L0_Pi_heterogeneous_cost"])
def test_legal_knob_hits_target_only_on_feasible_subset(protocol, scenario):
    cfg = protocol.scenario(scenario)
    cart = load_v3_numerics().require("validation.boundary_cart_cents")
    p0, p1 = _probabilities(cfg)
    result = solve_l0_profit_control(cart, p0, p1, cfg)
    audit = result.audit
    feasible = audit.control_feasible
    assert len(audit) == len(cart)
    assert feasible.any() and (~feasible).any()
    tolerance = cfg.require("dgp.l0.control.homogeneity_numerical_tolerance_cny")
    assert audit.loc[feasible, "profit_residual_cny"].abs().max() <= tolerance
    low, high = cfg.require("dgp.l0.control.effective_gross_margin_bounds")
    assert ((1 - result.goods_cost_ratio[feasible] >= low - np.finfo(float).eps)
            & (1 - result.goods_cost_ratio[feasible] <= high + np.finfo(float).eps)).all()
    assert (result.goods_cost_ratio[~feasible] == cfg.require("business.goods_cost_ratio")).all()
    assert (result.redemption_probability[~feasible] == cfg.require("business.redemption_rate")).all()
    assert ((result.redemption_probability >= 0) & (result.redemption_probability <= 1)).all()
    refund0 = cfg.require("business.refund_rate")
    refund1 = refund0 * cfg.require("business.refund_rate_treated_multiplier")
    mu0 = conditional_user_expectation(cart, cfg, purchase_probability=p0,
        refund_probability=refund0, redemption_probability=0, goods_cost_ratio=result.goods_cost_ratio)
    mu1 = conditional_user_expectation(cart, cfg, purchase_probability=p1,
        refund_probability=refund1, redemption_probability=result.redemption_probability,
        goods_cost_ratio=result.goods_cost_ratio)
    np.testing.assert_allclose(mu1["net_profit"] - mu0["net_profit"], audit.profit_cate_cny,
                               rtol=0, atol=load_v3_numerics().require("integration.absolute_tolerance"))
    assert audit.attrs["audit_only"] is True


@pytest.mark.parametrize("returned", [False, True])
def test_equal_cost_is_actual_capped_windowed_redemption_spend(protocol, returned):
    cfg = protocol.scenario("L0_Pi_equal_cost").with_overrides({"business.coupon_returned_on_refund": returned})
    p0, p1 = _probabilities(cfg)
    carts = [5000, 13000, 50000]
    result = solve_l0_profit_control(carts, p0, p1, cfg)
    assert result.audit.control_feasible.all()
    timing = timing_coefficients(cfg)
    refund1 = cfg.require("business.refund_rate") * cfg.require("business.refund_rate_treated_multiplier")
    target = cfg.require("dgp.l0.control.constant_expected_coupon_cost_cny")
    units = cfg.require("business.money.cents_per_yuan")
    face_cent = cfg.require("business.coupon_reference_face") * units
    for cart, redemption in zip(carts, result.redemption_probability, strict=True):
        gross, pmf = amount_distribution(cart, cfg)
        cap = np.dot(np.minimum(gross, face_cent), pmf) / units
        actual = p1 * redemption * cap * (timing.first_order - returned * refund1 * timing.first_refund)
        assert actual == pytest.approx(target, rel=0, abs=load_v3_numerics().require("integration.absolute_tolerance"))
    if returned:
        baseline = solve_l0_profit_control(carts, p0, p1, protocol.scenario("L0_Pi_equal_cost"))
        assert (result.redemption_probability > baseline.redemption_probability).all()


def test_natural_cost_preserves_redemption_and_retains_cost_variation(protocol):
    cfg = protocol.scenario("L0_Pi_heterogeneous_cost")
    result = solve_l0_profit_control([0, 1500, 13000, 50000], *_probabilities(cfg), cfg)
    assert (result.redemption_probability == cfg.require("business.redemption_rate")).all()
    assert result.audit.coupon_cost_cny.max() > result.audit.coupon_cost_cny.min()
    assert not result.audit.redemption_control_applied.any()


def test_probability_only_diagnostic_uses_legal_range_without_clipping(protocol):
    cfg = protocol.scenario("L0_Pi_equal_cost")
    p0, p1 = _probabilities(cfg)
    result = solve_l0_profit_control([0, 1500, 5000, 13000], p0, p1, cfg)
    target = cfg.require("dgp.l0.control.target_profit_cate_cny")
    for row in result.audit.itertuples():
        assert row.probability_only_feasible == (0 <= row.probability_only_required_p1 <= 1)
        if row.probability_only_feasible:
            assert row.probability_only_effect_min_cny <= target <= row.probability_only_effect_max_cny
    assert (result.audit.probability_only_required_p1 < 0).any()
    # At zero gross, reducing loss-making purchases can create a positive effect;
    # that diagnostic does not imply the fixed p1=.15 artificial control is feasible.
    assert result.audit.iloc[0].probability_only_feasible
    assert not result.audit.iloc[0].control_feasible


def test_zero_cost_capacity_is_not_clipped_to_a_false_equal_cost_claim(protocol):
    cfg = protocol.scenario("L0_Pi_equal_cost")
    result = solve_l0_profit_control([0, 1, 100], *_probabilities(cfg), cfg)
    assert not result.audit.cost_control_feasible.any()
    assert not result.audit.control_feasible.any()
    assert result.audit.candidate_redemption_probability.iloc[-1] > 1
    assert (result.redemption_probability == cfg.require("business.redemption_rate")).all()


def test_all_feasible_batch_and_common_subset_keep_all_user_rows(protocol):
    equal_cfg, natural_cfg = (protocol.scenario(name) for name in ("L0_Pi_equal_cost", "L0_Pi_heterogeneous_cost"))
    p0, p1 = _probabilities(equal_cfg)
    high_carts = [13000, 50000]
    assert solve_l0_profit_control(high_carts, p0, p1, equal_cfg).audit.control_feasible.all()
    carts = [0, 1500, 5000, 13000, 50000]
    equal = solve_l0_profit_control(carts, p0, p1, equal_cfg)
    natural = solve_l0_profit_control(carts, p0, p1, natural_cfg)
    common = audit_common_feasible_mask(equal, natural)
    assert common.any() and (~common).any()
    assert len(equal.audit) == len(natural.audit) == len(carts)
    np.testing.assert_array_equal(common, equal.audit.control_feasible & natural.audit.control_feasible)
    reversed_natural = solve_l0_profit_control(carts[::-1], p0, p1, natural_cfg)
    with pytest.raises(ValueError, match="相同顺序"):
        audit_common_feasible_mask(equal, reversed_natural)


def test_impossible_profit_target_preserves_both_natural_mechanisms(protocol):
    cfg = protocol.scenario("L0_Pi_equal_cost").with_overrides({"dgp.l0.control.target_profit_cate_cny": 10000})
    result = solve_l0_profit_control([13000], *_probabilities(cfg), cfg)
    assert result.audit.cost_control_feasible.all()
    assert not result.audit.control_feasible.any()
    assert result.goods_cost_ratio[0] == cfg.require("business.goods_cost_ratio")
    assert result.redemption_probability[0] == cfg.require("business.redemption_rate")
    assert result.audit.reason.iloc[0] == "profit_target_outside_bounded_knob_range"


def test_cache_preserves_duplicate_order_and_configuration_identity(protocol):
    cfg = protocol.scenario("L0_Pi_equal_cost")
    snapshot = cfg.to_dict()
    carts = [13000, 1500, 13000]
    first = solve_l0_profit_control(carts, *_probabilities(cfg), cfg)
    second = solve_l0_profit_control(carts, *_probabilities(cfg), cfg)
    pd.testing.assert_frame_equal(first.audit, second.audit)
    assert first.goods_cost_ratio[0] == first.goods_cost_ratio[-1]
    assert cfg.to_dict() == snapshot
    altered = cfg.with_overrides({"dgp.l0.control.target_profit_cate_cny": 1})
    changed = solve_l0_profit_control(carts, *_probabilities(altered), altered)
    assert changed.audit.attrs["config_hash"] != first.audit.attrs["config_hash"]
    assert changed.goods_cost_ratio[0] != first.goods_cost_ratio[0]


@pytest.mark.parametrize("scenario", ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"])
def test_knob_cannot_leak_outside_l0_profit_control(protocol, scenario):
    cfg = protocol.scenario(scenario)
    with pytest.raises(ConfigError, match="只允许"):
        solve_l0_profit_control([13000], .1, .15, cfg)


@pytest.mark.parametrize("cart,p0,p1", [([-1], .1, .15), ([1.5], .1, .15), ([np.nan], .1, .15),
    ([13000], -.1, .15), ([13000], .1, 1.1), ([13000], .1, np.nan)])
def test_invalid_mechanism_input_fails_loudly(protocol, cart, p0, p1):
    with pytest.raises(ValueError):
        solve_l0_profit_control(cart, p0, p1, protocol.scenario("L0_Pi_equal_cost"))


def test_empty_batch_is_supported_without_inventing_users(protocol):
    result = solve_l0_profit_control([], .1, .15, protocol.scenario("L0_Pi_equal_cost"))
    assert result.audit.empty
    assert result.goods_cost_ratio.size == result.redemption_probability.size == 0


def test_discrete_step_gap_is_infeasible_even_when_linear_candidate_exists(protocol):
    cfg = protocol.scenario("L0_Pi_heterogeneous_cost")
    p0, p1 = _probabilities(cfg)
    refund0 = cfg.require("business.refund_rate")
    refund1 = refund0 * cfg.require("business.refund_rate_treated_multiplier")
    endpoints = []
    for ratio in (.02, .98):
        mu0 = conditional_user_expectation(2, cfg, purchase_probability=p0,
            refund_probability=refund0, redemption_probability=0, goods_cost_ratio=ratio)
        mu1 = conditional_user_expectation(2, cfg, purchase_probability=p1,
            refund_probability=refund1, redemption_probability=cfg.require("business.redemption_rate"), goods_cost_ratio=ratio)
        endpoints.append(float(mu1["net_profit"] - mu0["net_profit"]))
    modified = cfg.with_overrides({
        "dgp.l0.control.target_profit_cate_cny": sum(endpoints) / 2,
        "dgp.l0.control.homogeneity_numerical_tolerance_cny": 1e-12,
    })
    result = solve_l0_profit_control([2], p0, p1, modified)
    assert not result.audit.control_feasible.any()
    assert result.audit.reason.iloc[0] == "no_step_value_within_effect_tolerance"
    assert result.audit.exact_expectation_evaluations.iloc[0] > 4
    assert result.goods_cost_ratio[0] == cfg.require("business.goods_cost_ratio")
