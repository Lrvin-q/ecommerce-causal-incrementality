"""合成数据 / 已知 DGP：金额边界、独立十进制账和积分一致性。"""

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import replace
from math import fsum

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import norm, truncnorm

from causal_growth.dgp.v3_amounts import (
    _pairwise_gamma, _pairwise_sum,
    amount_distribution, conditional_expectation_numerical_error, conditional_order_expectation, conditional_user_expectation,
    fulfillment_calibration, posted_components, round_ratio_cent, sample_amounts, sample_fraction,
    paired_conditional_expectation_numerical_error,
)
from causal_growth.rng import child_rng
from causal_growth.v3_config import load_v3_protocol
from causal_growth.v3_numerics import load_v3_numerics


@pytest.fixture(scope="module")
def cfg():
    return load_v3_protocol().config


def decimal_round(amount, ratio):
    return int((Decimal(int(amount)) * Decimal(str(ratio))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@pytest.mark.parametrize("ratio", [0.55, 0.68, 0.85, 0.01, 0.3333333333333333, 0.1234567890123456])
def test_half_up_matches_independent_decimal(ratio):
    cents = np.arange(2001)
    expected = np.array([decimal_round(v, ratio) for v in cents])
    np.testing.assert_array_equal(round_ratio_cent(cents, ratio), expected)
    assert round_ratio_cent(10, .55) == 6


def test_distinct_user_cost_ratios_match_decimal_without_group_scans():
    rng = child_rng(20261025, "test.distinct.cost.ratios")
    amounts = rng.integers(0, 1000000, 20000)
    ratios = rng.uniform(.02, .98, amounts.size)
    expected = [decimal_round(g, float(r)) for g, r in zip(amounts, ratios)]
    np.testing.assert_array_equal(round_ratio_cent(amounts, ratios), expected)


def test_fraction_is_truncated_inverse_cdf_and_amounts_respect_boundaries(cfg):
    uniforms = np.array([0, .01, .50, .99, np.nextafter(1., 0.)])
    p = cfg.section("business.first_order_cart_fraction")
    mu, sd = p["mean_before_truncation"], p["sd_before_truncation"]
    reference = truncnorm.ppf(uniforms, (p["lower_exclusive"] - mu) / sd,
                              (p["upper_inclusive"] - mu) / sd, loc=mu, scale=sd)
    q = sample_fraction(uniforms, cfg)
    np.testing.assert_allclose(q, reference, atol=1e-12)
    assert np.all(q > 0) and np.all(q <= 1)
    carts = np.tile(load_v3_numerics().require("validation.boundary_cart_cents"), 100)
    sample = sample_amounts(carts, cfg, master_seed=20261025, stream="test.boundary")
    assert np.all(sample.first_gross_cent <= carts)
    assert np.all(sample.first_gross_cent >= 0)
    assert np.all(sample.first_gross_cent[carts <= 1] == 0)
    assert np.all(np.abs(sample.repeat_gross_cent - .55 * sample.first_gross_cent) <= .5 + 1e-12)
    shorter = sample_amounts(carts[:10], cfg, master_seed=20261025, stream="test.boundary")
    for name in ("first_gross_cent", "repeat_gross_cent", "fraction", "fulfill_cent"):
        np.testing.assert_array_equal(getattr(shorter, name), getattr(sample, name)[:10])


@pytest.mark.parametrize("returned", [False, True])
def test_integer_ledger_matches_independent_decimal_all_combinations(cfg, returned):
    cfg = cfg.with_overrides({"business.coupon_returned_on_refund": returned})
    gross = np.array([0, 1, 999, 1000, 1001, 13001] * 4)
    redeemed = np.repeat([False, False, True, True], 6)
    refunded = np.repeat([False, True, False, True], 6)
    got = posted_components(gross, 500, redeemed, refunded, cfg)
    for i, g in enumerate(gross):
        goods = decimal_round(g, .68)
        discount = min(int(g), 1000) if redeemed[i] else 0
        recover = decimal_round(goods, .85) if refunded[i] else 0
        fee = decimal_round(g, .01) if refunded[i] else 0
        coupon = discount if not (returned and refunded[i]) else 0
        expected = int(g) * (not refunded[i]) - goods + recover - 500 - coupon - fee
        assert got["net_profit"][i] == expected
        assert got["consumer_refund"][i] == (g - discount) * refunded[i]
        assert got["coupon_cost"][i] == coupon
    assert np.issubdtype(got["net_profit"].dtype, np.integer)
    assert np.any(got["net_profit"] < 0)
    no_coupon = posted_components(gross, 500, True, False, cfg, coupon_eligible=False)
    assert np.all(no_coupon["coupon_cost"] == 0)


@pytest.mark.parametrize("cart", [0, 1, 17, 1500, 13000, 50000])
def test_full_cent_pmf_and_expectations_match_separate_survival_sum(cfg, cart):
    support, pmf = amount_distribution(cart, cfg)
    assert abs(pmf.sum() - 1) < 1e-12
    assert np.all(pmf >= 0)
    assert not support.flags.writeable and not pmf.flags.writeable
    mu, sd = .7, .1
    if cart:
        thresholds = np.arange(1, cart) / cart
        expected_gross = np.sum(truncnorm.sf(thresholds, -mu / sd, (1 - mu) / sd, loc=mu, scale=sd)) / 100
    else:
        expected_gross = 0
    moments = conditional_order_expectation(cart, cfg)
    assert abs(float(moments["first_gross"]) - expected_gross) < 1e-9
    if cart <= 17:
        normalization = norm.cdf((1 - mu) / sd) - norm.cdf(-mu / sd)
        integral = sum(quad(lambda q: norm.pdf((q - mu) / sd) / sd / normalization,
                            k / cart, (k + 1) / cart, epsabs=1e-13)[0] * decimal_round(k, .68)
                       for k in range(cart)) / 100 if cart else 0
        assert abs(float(moments["first_goods"]) - integral) < 1e-10


def test_zero_purchase_zero_components_and_refund_probability_includes_second_order(cfg):
    zero = conditional_user_expectation([0, 1500, 13000], cfg, purchase_probability=0,
                                        refund_probability=.075, redemption_probability=.55)
    for value in zero.values():
        np.testing.assert_array_equal(value, np.zeros(3))
    all_refund = conditional_user_expectation([13000], cfg, purchase_probability=1,
                                              refund_probability=1, redemption_probability=0)
    assert all_refund["any_refund_probability"][0] <= 1
    assert all_refund["any_refund_probability"][0] > .9983922564
    no_repeat = conditional_user_expectation([13000], cfg.with_overrides({"business.repeat.enabled": False}),
                                             purchase_probability=1, refund_probability=.075, redemption_probability=0)
    with_repeat = conditional_user_expectation([13000], cfg, purchase_probability=1,
                                               refund_probability=.075, redemption_probability=0)
    assert with_repeat["any_refund_probability"][0] > no_repeat["any_refund_probability"][0]


@pytest.mark.parametrize("sd", [.6, 1.2, 2.4])
def test_clipped_rounded_fulfillment_calibration_and_independent_mc(cfg, sd):
    cfg = cfg.with_overrides({"business.fulfill_cost_sd": sd})
    result = fulfillment_calibration(cfg)
    assert abs(result.mean - 5) + result.mean_tail_bound < 1e-6
    assert result.second_moment_tail_bound < 1e-6
    # 独立于生产采样流；保存精度来自MC_SE而非指定近似均值。
    n = int(load_v3_numerics().require("validation.independent_mc_n"))
    raw = child_rng(20261025, "test.independent.fulfillment").normal(result.raw_location, sd, n)
    amounts = np.floor(np.maximum(raw, .5) * 100 + .5) / 100
    se = amounts.std(ddof=1) / np.sqrt(n)
    assert abs(amounts.mean() - result.mean) < max(.001, 4 * se)
    assert abs(amounts.std() - result.standard_deviation) < .01


def test_signal_changes_variance_not_conditional_mean(cfg):
    low = cfg.with_overrides({"business.fulfill_cost_sd": .6})
    high = cfg.with_overrides({"business.fulfill_cost_sd": 2.4})
    assert fulfillment_calibration(high).standard_deviation > fulfillment_calibration(low).standard_deviation
    a = conditional_user_expectation([1500, 13000, 50000], low, purchase_probability=.15,
                                     refund_probability=.075, redemption_probability=.55)
    b = conditional_user_expectation([1500, 13000, 50000], high, purchase_probability=.15,
                                     refund_probability=.075, redemption_probability=.55)
    np.testing.assert_allclose(a["net_profit"], b["net_profit"], atol=1e-10, rtol=0)


def test_inputs_fail_loudly(cfg):
    with pytest.raises(ValueError):
        amount_distribution(-1, cfg)
    with pytest.raises(ValueError):
        posted_components(1.5, 0, False, False, cfg)
    with pytest.raises(ValueError):
        sample_fraction([1], cfg)
    with pytest.raises(ValueError):
        conditional_order_expectation([1500], cfg, goods_cost_ratio=1.1)


def test_numerical_error_diagnostics_are_separate_cny_components_and_scale_with_purchase(cfg):
    carts = [0, 1500, 13000, 50000]
    full = conditional_expectation_numerical_error(carts, cfg, purchase_probability=1,
                                                  refund_probability=.07725, redemption_probability=.55)
    partial = conditional_expectation_numerical_error(carts, cfg, purchase_probability=.15,
                                                     refund_probability=.07725, redemption_probability=.55)
    pieces = [key for key in full if key.startswith("net_profit_") and key != "net_profit_numerical_error_estimate_cny"]
    np.testing.assert_allclose(sum(full[key] for key in pieces), full["net_profit_numerical_error_estimate_cny"], rtol=0, atol=0)
    for key in pieces:
        assert np.all(np.isfinite(full[key])) and np.all(full[key] >= 0)
        np.testing.assert_allclose(partial[key], .15 * full[key], rtol=1e-14, atol=0)
    assert np.all(full["net_profit_numerical_error_estimate_cny"] < 1e-6)
    business = conditional_user_expectation(carts, cfg, purchase_probability=1,
                                            refund_probability=.07725, redemption_probability=.55)
    assert not set(business) & set(full)
    assert np.all(full["conditional_profit_absolute_envelope_cny"] >= abs(business["net_profit"]))


def test_time_error_is_propagated_to_currency_and_not_merely_reported(cfg, monkeypatch):
    import causal_growth.dgp.v3_amounts as module
    arguments = dict(purchase_probability=.15, refund_probability=.07725, redemption_probability=.55)
    original = module.timing_coefficients(cfg)
    baseline = conditional_expectation_numerical_error([13000], cfg, **arguments)
    multiplier = 2 * float(load_v3_numerics().require("integration.absolute_tolerance")) / float(baseline["net_profit_time_error_estimate_cny"][0])
    monkeypatch.setattr(module, "timing_coefficients", lambda _: replace(original, integration_error_bound=original.integration_error_bound * multiplier))
    inflated = conditional_expectation_numerical_error([13000], cfg, **arguments)
    np.testing.assert_allclose(inflated["net_profit_time_error_estimate_cny"], baseline["net_profit_time_error_estimate_cny"] * multiplier)
    assert inflated["net_profit_numerical_error_estimate_cny"][0] > 1e-6


def test_paired_error_keeps_shared_cancellation_and_exact_null(cfg):
    carts = np.array([0, 1500, 13000, 50000])
    a = dict(purchase_probability0=.1, purchase_probability1=.15, refund_probability0=.075,
             refund_probability1=.07725, redemption_probability0=0, redemption_probability1=.55)
    paired = paired_conditional_expectation_numerical_error(carts, cfg, **a)
    zero = conditional_user_expectation(carts, cfg, purchase_probability=.1, refund_probability=.075, redemption_probability=0)
    one = conditional_user_expectation(carts, cfg, purchase_probability=.15, refund_probability=.07725, redemption_probability=.55)
    np.testing.assert_allclose(paired["net_profit_difference_cny"], one["net_profit"] - zero["net_profit"], atol=1e-13, rtol=0)
    identical = paired_conditional_expectation_numerical_error(
        carts, cfg, **{**a, "purchase_probability1": .1, "refund_probability1": .075, "redemption_probability1": 0})
    for value in identical.values():
        np.testing.assert_array_equal(value, np.zeros(carts.shape))


@pytest.mark.parametrize("target", [1e-5, 1e-7])
def test_near_zero_cate_meets_both_precision_gates_after_pairwise_refinement(cfg, target):
    a0 = float(conditional_user_expectation(13000, cfg, purchase_probability=1,
                                          refund_probability=.075, redemption_probability=0)["net_profit"])
    a1 = float(conditional_user_expectation(13000, cfg, purchase_probability=1,
                                          refund_probability=.07725, redemption_probability=.55)["net_profit"])
    p1 = (.1 * a0 + target) / a1
    result = paired_conditional_expectation_numerical_error(
        13000, cfg, purchase_probability0=.1, purchase_probability1=p1, refund_probability0=.075,
        refund_probability1=.07725, redemption_probability0=0, redemption_probability1=.55)
    assert abs(float(result["net_profit_difference_cny"]) - target) < 1e-13
    error = float(result["net_profit_numerical_error_estimate_cny"])
    actual = float(result["net_profit_difference_cny"])
    numerical = load_v3_numerics()
    assert 0 < error <= float(numerical.require("integration.absolute_tolerance"))
    assert error / abs(actual) <= float(numerical.require("integration.relative_tolerance"))
    # 本接口只交付元单位误差；相对门禁和零真值NA由审计层明示，不能静默给True。
    assert not any("passed" in key or "relative" in key for key in result)


@pytest.mark.parametrize("size", [1, 2, 3, 17, 1025])
def test_explicit_pairwise_sum_respects_actual_tree_depth_bound(size):
    rng = child_rng(20261025, "test.pairwise.sum", size)
    values = rng.normal(size=size) * np.power(2., rng.integers(-20, 20, size=size))
    actual = _pairwise_sum(values)
    reference = fsum(map(float, values))
    bound = _pairwise_gamma(size) * fsum(map(float, abs(values)))
    assert abs(actual - reference) <= bound
