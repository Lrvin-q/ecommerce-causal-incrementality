"""合成数据 / 已知 DGP：逐事件时间与30天截窗的确定性积分。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import quad
from scipy.special import gammainc, gammaln

from causal_growth.config import Config
from causal_growth.rng import child_rng
from causal_growth.v3_numerics import load_v3_numerics


_NUMERICS = load_v3_numerics()

@dataclass(frozen=True)
class OrderTiming:
    """相对分配时间的首单、复购、两笔退款时间，单位天；尚未施加事件发生指示。"""

    first_order_day: NDArray[np.float64]
    repeat_order_day: NDArray[np.float64]
    first_refund_day: NDArray[np.float64]
    repeat_refund_day: NDArray[np.float64]


@dataclass(frozen=True)
class TimingCoefficients:
    """条件首单发生时的联合截窗概率；退款/复购Bernoulli概率另乘。"""

    first_order: float
    repeat_order: float
    first_refund: float
    repeat_refund: float
    both_refunds: float
    first_conversion: float
    integration_error_bound: float


def sample_order_timing(
    n: int, cfg: Config, *, master_seed: int, stream: str, index: int = 0
) -> OrderTiming:
    """回答两窗口如何落实到事件：独立语义随机流、复购相对首单延迟。"""
    if n < 0:
        raise ValueError("n必须非负")
    p = cfg.section("business.order_timing")
    first = np.clip(
        child_rng(master_seed, f"{stream}.timing.first", index).gamma(
            p["first_order_delay_gamma_shape"], p["first_order_delay_gamma_scale_days"], n
        ), *p["first_order_delay_clip_days"],
    )
    second = first + np.clip(
        child_rng(master_seed, f"{stream}.timing.repeat", index).gamma(
            p["repeat_delay_gamma_shape"], p["repeat_delay_gamma_scale_days"], n
        ), *p["repeat_delay_clip_days"],
    )
    lo, hi = p["refund_delay_uniform_days"]
    return OrderTiming(
        first, second,
        first + child_rng(master_seed, f"{stream}.timing.refund_first", index).uniform(lo, hi, n),
        second + child_rng(master_seed, f"{stream}.timing.refund_repeat", index).uniform(lo, hi, n),
    )


def _clipped_gamma_cdf(x: float, shape: float, scale: float, low: float, high: float) -> float:
    if x < low:
        return 0.0
    if x >= high:
        return 1.0
    return float(gammainc(shape, x / scale))


def _expect_clipped_gamma(
    f: Callable[[float], float], params: tuple[float, ...], points: tuple[float, ...],
    epsabs: float, epsrel: float, limit: int,
) -> tuple[float, float]:
    shape, scale, low, high = params
    atoms = float(gammainc(shape, low / scale)) * f(low)
    atoms += (1 - float(gammainc(shape, high / scale))) * f(high)

    def integrand(x: float) -> float:
        density = np.exp((shape - 1) * np.log(x) - x / scale - gammaln(shape) - shape * np.log(scale))
        return float(density * f(x))

    value, error = quad(
        integrand, low, high, points=sorted({v for v in points if low < v < high}),
        epsabs=epsabs, epsrel=epsrel, limit=limit,
    )
    return atoms + value, error


@lru_cache(maxsize=None)
def _timing_cached(
    first: tuple[float, ...], repeat: tuple[float, ...], refund: tuple[float, ...],
    window: float, conversion: float, epsabs: float, epsrel: float, limit: int,
) -> TimingCoefficients:
    refund_lo, refund_hi = refund
    if not (0 <= refund_lo < refund_hi):
        raise ValueError("退款延迟区间非法")

    def refund_cdf(remaining: float) -> float:
        return float(np.clip((remaining - refund_lo) / (refund_hi - refund_lo), 0, 1))

    def integrate_first(f: Callable[[float], float], points: tuple[float, ...]) -> tuple[float, float]:
        return _expect_clipped_gamma(f, first, points, epsabs, epsrel, limit)

    first_in = _clipped_gamma_cdf(window, *first)
    conversion_in = _clipped_gamma_cdf(conversion, *first)
    first_ref, err1 = integrate_first(
        lambda s: refund_cdf(window - s), (window - refund_lo, window - refund_hi),
    )
    repeat_in, err2 = integrate_first(
        lambda s: _clipped_gamma_cdf(window - s, *repeat),
        (window - repeat[2], window - repeat[3]),
    )
    inner_errors: list[float] = []

    def second_refund(s: float) -> float:
        value, error = _expect_clipped_gamma(
            lambda d: refund_cdf(window - s - d), repeat,
            (window - s - refund_lo, window - s - refund_hi), epsabs, epsrel, limit,
        )
        inner_errors.append(error)
        return value

    outer_points = tuple(window - r - d for r in refund for d in repeat[2:])
    second_ref, err3 = integrate_first(second_refund, outer_points)
    both_ref, err4 = integrate_first(
        lambda s: refund_cdf(window - s) * second_refund(s),
        (*outer_points, window - refund_lo, window - refund_hi),
    )
    error = max(err1, err2, err3, err4) + max(inner_errors, default=0.0)
    return TimingCoefficients(first_in, repeat_in, first_ref, second_ref, both_ref, conversion_in, error)


def timing_coefficients(cfg: Config, *, profit_days: float | None = None) -> TimingCoefficients:
    """积分退款与复购跨窗，并保留任一单退款所需的两退款联合项。"""
    p = cfg.section("business.order_timing")
    n = _NUMERICS
    first = (
        float(p["first_order_delay_gamma_shape"]), float(p["first_order_delay_gamma_scale_days"]),
        *map(float, p["first_order_delay_clip_days"]),
    )
    repeat = (
        float(p["repeat_delay_gamma_shape"]), float(p["repeat_delay_gamma_scale_days"]),
        *map(float, p["repeat_delay_clip_days"]),
    )
    result = _timing_cached(
        first, repeat, tuple(map(float, p["refund_delay_uniform_days"])),
        float(cfg.require("windows.profit_days") if profit_days is None else profit_days),
        float(cfg.require("windows.convert_days")),
        float(n.require("integration.quad_epsabs")), float(n.require("integration.quad_epsrel")),
        int(n.require("integration.quad_limit")),
    )
    if result.integration_error_bound > float(n.require("integration.absolute_tolerance")):
        raise ArithmeticError("时间积分未达到绝对精度")
    return result
