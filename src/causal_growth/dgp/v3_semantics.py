"""Reject unimplemented mechanism semantics rather than ignoring configuration.

These strings and Boolean switches describe the implemented mathematical
family. Continuous business parameters remain configurable within that family.
"""

from __future__ import annotations

from causal_growth.config import Config, ConfigError


_SUPPORTED = {
    "units.monetary_storage": "integer_cent",
    "business.coupon_eligible_order": "first_order_only",
    "business.coupon_discount_rule": "min_face_and_gross_order_amount",
    "business.redemption_rate_denominator": "paid_first_orders_in_coupon_action",
    "business.refund_rate_denominator": "paid_orders",
    "business.fulfill_cost_distribution": "mean_calibrated_lower_clipped_normal",
    "business.fulfill_cost_mean_definition": "target_mean_after_floor_and_cent_rounding",
    "business.fulfill_cost_location_calibration": "solve_raw_normal_location_for_target_post_transform_mean",
    "business.hist_gmv.distribution": "gamma_by_new_user_status",
    "business.cart_value.distribution": "lower_clipped_gamma",
    "business.browse_depth.distribution": "negative_binomial",
    "business.first_order_cart_fraction.distribution": "truncated_normal",
    "business.first_order_cart_fraction.sampler": "inverse_cdf",
    "business.first_order_cart_fraction.share_draw_between_actions": True,
    "business.repeat.coupon_used": False,
    "business.repeat.share_fulfillment_draw_with_first_order": True,
    "business.repeat.second_refund_independent_uniform_given_user": True,
    "business.repeat.refund_rate_follows_assigned_action": True,
    "business.repeat.require_first_order": True,
    "business.order_timing.repeat_delay_origin": "first_order_time",
    "business.order_timing.terminal_window_rule": "include_only_events_at_or_before_assignment_plus_profit_days",
    "business.money.currency": "CNY",
    "business.money.rounding": "mixed_explicit_component_rules",
    "business.money.cart_rounding": "floor_to_cent_before_amount_generation",
    "business.money.first_order_rounding": "floor_cart_cent_times_fraction",
    "business.money.repeat_rounding": "round_first_gross_cent_times_repeat_ratio",
    "business.money.component_rounding": "round_each_posted_ledger_component_once",
    "business.accounting.revenue_basis": "gross_before_coupon",
    "business.accounting.consumer_paid": "gross_order_amount_minus_coupon_discount",
    "business.accounting.consumer_refund": "consumer_paid_if_refunded",
    "business.accounting.gross_refund_reversal": "gross_order_amount_if_refunded",
    "business.accounting.refund_processing_fee_basis": "gross_order_amount",
    "business.accounting.goods_cost_basis": "gross_order_amount",
    "business.accounting.coupon_cost_after_refund": "retained_platform_subsidy",
    "business.accounting.gross_refund_interpretation": "reverse_full_gross_revenue_while_retaining_coupon_expense",
    "business.accounting.net_profit_formula": "gross_order_amount-gross_refund_reversal-goods_cost+goods_cost_recovered-fulfill_cost-coupon_cost-refund_processing_fee",
    "business.accounting.subsidy_double_charge_forbidden": True,
    "business.accounting.refund_orders_retained": True,
    "business.accounting.negative_order_profit_allowed": True,
    "business.accounting.gmv": "sum_gross_order_amount_before_refunds",
    "business.accounting.net_transaction_amount": "sum_gross_order_amount_minus_gross_refund_reversal",
    "windows.boundary": "inclusive",
    "windows.analysis_denominator": "all_assigned_eligible_users",
    "windows.late_refund_policy": "retain_event_but_exclude_from_30d_target_if_event_after_window",
    "dgp.probability_rule": "positive_headroom_parameterization_no_silent_clipping",
    "dgp.baseline_and_effect_calibration": "independent_fixed_reference_population",
    "dgp.l2.base_mechanism": "l1",
    "dgp.l3.calibrate_assignment_intercept_every_rep": True,
    "dgp.l3.u_target_mean": 0,
    "dgp.l3.u_target_variance": 1,
    "dgp.l3.u_independent_of_X": True,
    "dgp.l3.u_distributions.logistic_standardized.raw_location": 0,
    "dgp.l3.u_distributions.logistic_standardized.raw_scale": 1,
    "dgp.l3.u_distributions.logistic_standardized.transform": "raw_times_sqrt_3_divided_by_pi",
    "dgp.l3.u_distributions.normal.mean": 0,
    "dgp.l3.u_distributions.normal.sd": 1,
    "dgp.l3.u_distributions.uniform_bounded.lower": "-sqrt(3)",
    "dgp.l3.u_distributions.uniform_bounded.upper": "sqrt(3)",
    "dgp.l3.u_common_random_number_coupling": "inverse_cdf_of_shared_uniform",
    "dgp.l3.learner_cate_truth": "integrate_U_not_condition_on_U",
    "dgp.l3.true_propensity_storage": "audit_only",
}


def validate_mechanism_semantics(cfg: Config) -> None:
    """Check that a requested simulation belongs to the implemented v3 family.

    A new family (for example a uniform cart fraction or independent second-order
    fulfillment) requires implementation and review; changing only its label
    must never silently retain the previous mechanism.
    """
    for key, expected in _SUPPORTED.items():
        actual = cfg.require(key)
        if actual != expected or (isinstance(expected, bool) and not isinstance(actual, bool)):
            raise ConfigError(f"Unsupported v3 mechanism semantics: {key}={actual!r}; supported={expected!r}")
    for key in ("business.repeat.enabled", "business.coupon_returned_on_refund", "dgp.virtual_aa_labels"):
        if not isinstance(cfg.require(key), bool):
            raise ConfigError(f"{key} must be Boolean")
    if tuple(cfg.require("business.action_space")) != (0, 1) or cfg.require("business.face_value_optimization_enabled"):
        raise ConfigError("v3 implements a binary fixed-reference-coupon action space")
    if tuple(cfg.require("business.coupon_face_values")) != (cfg.require("business.coupon_reference_face"),):
        raise ConfigError("configured coupon faces conflict with the single reference action")
    streams = {"purchase_uniform", "fraction_draw", "refund_uniform", "redemption_uniform", "repeat_uniform", "order_delays", "fulfillment"}
    if set(cfg.require("dgp.shared_action_randomness")) != streams:
        raise ConfigError("shared-action random-stream semantics are unsupported")
