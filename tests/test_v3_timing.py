"""合成数据 / 已知 DGP：时窗边界与两退款联合系数。"""

import numpy as np
import pytest

from causal_growth.dgp.v3_timing import _timing_cached, sample_order_timing, timing_coefficients
from causal_growth.rng import child_rng
from causal_growth.v3_config import load_v3_protocol
from causal_growth.v3_numerics import load_v3_numerics


@pytest.fixture(scope="module")
def cfg():
    return load_v3_protocol().config


def test_fixed_payment_times_give_exact_joint_refund_case(cfg):
    fixed = cfg.with_overrides({
        "business.order_timing.first_order_delay_clip_days": [5., 5.],
        "business.order_timing.repeat_delay_clip_days": [20., 20.],
        "business.order_timing.refund_delay_uniform_days": [4., 6.],
    })
    t = timing_coefficients(fixed)
    assert t.first_order == t.repeat_order == t.first_refund == 1
    assert t.repeat_refund == t.both_refunds == .5
    at_boundary = timing_coefficients(fixed, profit_days=25)
    assert at_boundary.repeat_order == 1
    assert at_boundary.repeat_refund == 0
    too_early = timing_coefficients(fixed, profit_days=4)
    assert too_early.first_order == too_early.repeat_order == too_early.first_refund == 0


def test_sampler_prefix_support_and_order_origin(cfg):
    a = sample_order_timing(1000, cfg, master_seed=20261025, stream="test.timing")
    b = sample_order_timing(10, cfg, master_seed=20261025, stream="test.timing")
    for name in a.__dataclass_fields__:
        np.testing.assert_array_equal(getattr(b, name), getattr(a, name)[:10])
    assert np.all((a.first_order_day >= .05) & (a.first_order_day <= 6.95))
    assert np.all(a.repeat_order_day >= a.first_order_day + 1)
    assert np.all(a.repeat_order_day <= a.first_order_day + 25)
    assert np.any(a.repeat_refund_day > 30)


def test_independent_mc_all_joint_window_coefficients(cfg):
    n = int(load_v3_numerics().require("validation.independent_mc_n"))
    rng = child_rng(20261025, "test.timing.independent.mc")
    first = np.clip(rng.gamma(2, 1, n), .05, 6.95)
    repeat = first + np.clip(rng.gamma(6, 1.5, n), 1, 25)
    refund1 = first + rng.uniform(1, 25, n)
    refund2 = repeat + rng.uniform(1, 25, n)
    t = timing_coefficients(cfg)
    samples = {
        "first_order": first <= 30, "repeat_order": repeat <= 30,
        "first_refund": refund1 <= 30, "repeat_refund": refund2 <= 30,
        "both_refunds": (refund1 <= 30) & (refund2 <= 30), "first_conversion": first <= 7,
    }
    for name, sample in samples.items():
        p = sample.mean()
        se = np.sqrt(p * (1 - p) / n)
        assert abs(p - getattr(t, name)) <= max(.001, 4 * se)
    assert t.integration_error_bound < 1e-6
    # 两退款共享首单时点，联合项不能默认等于边缘概率乘积。
    assert not np.isclose(t.both_refunds, t.first_refund * t.repeat_refund)


def test_timing_quadrature_tolerance_convergence(cfg):
    p = cfg.section("business.order_timing")
    first = (p["first_order_delay_gamma_shape"], p["first_order_delay_gamma_scale_days"],
             *p["first_order_delay_clip_days"])
    repeat = (p["repeat_delay_gamma_shape"], p["repeat_delay_gamma_scale_days"],
              *p["repeat_delay_clip_days"])
    tolerance = load_v3_numerics()
    baseline = timing_coefficients(cfg)
    tightened = _timing_cached(
        first, repeat, tuple(p["refund_delay_uniform_days"]),
        cfg.require("windows.profit_days"), cfg.require("windows.convert_days"),
        float(tolerance.require("integration.refinement_epsabs")),
        float(tolerance.require("integration.refinement_epsrel")),
        int(tolerance.require("integration.refinement_limit")),
    )
    for key in ("first_order", "repeat_order", "first_refund", "repeat_refund", "both_refunds", "first_conversion"):
        assert abs(getattr(baseline, key) - getattr(tightened, key)) < 1e-10
