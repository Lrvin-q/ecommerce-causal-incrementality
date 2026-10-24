"""Unsupported changes to mechanism meaning fail before simulation."""

import pytest

from causal_growth.config import ConfigError
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.dgp.v3_semantics import validate_mechanism_semantics
from causal_growth.v3_config import load_v3_protocol


@pytest.mark.parametrize("key,value", [
    ("business.first_order_cart_fraction.distribution", "uniform"),
    ("business.first_order_cart_fraction.sampler", "clip_normal"),
    ("business.repeat.share_fulfillment_draw_with_first_order", False),
    ("business.repeat.require_first_order", False),
    ("business.repeat.coupon_used", True),
    ("business.order_timing.repeat_delay_origin", "assignment_time"),
    ("business.coupon_eligible_order", "every_order"),
    ("business.accounting.revenue_basis", "consumer_paid"),
    ("dgp.l3.u_distributions.normal.sd", 2),
    ("dgp.l3.u_distributions.logistic_standardized.raw_scale", 2),
    ("dgp.l3.calibrate_assignment_intercept_every_rep", False),
    ("windows.boundary", "exclusive"),
])
def test_semantic_mutation_is_rejected_by_generation_entry(key, value) -> None:
    cfg = load_v3_protocol().scenario("L0_P_main").with_overrides({key: value})
    with pytest.raises(ConfigError, match="Unsupported"):
        generate_v3_population(cfg, n=10)


def test_all_approved_scenarios_are_supported() -> None:
    protocol = load_v3_protocol()
    for row in protocol.config.require("scenarios"):
        validate_mechanism_semantics(protocol.scenario(row["id"]))
