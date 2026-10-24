"""合成数据 / 已知 DGP：分币金额、逐组件账务及条件利润的精确离散求和。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import brentq
from scipy.special import log_ndtr, ndtr, ndtri

from causal_growth.config import Config
from causal_growth.dgp.v3_timing import timing_coefficients
from causal_growth.rng import child_rng
from causal_growth.v3_numerics import load_v3_numerics


_NUMERICS = load_v3_numerics()


@dataclass(frozen=True)
class AmountDraws:
    """同一用户两动作共享的潜在金额与履约成本；全部金额单位为分。"""

    first_gross_cent: NDArray[np.int64]
    repeat_gross_cent: NDArray[np.int64]
    fraction: NDArray[np.float64]
    fulfill_cent: NDArray[np.int64]


@dataclass(frozen=True)
class FulfillmentCalibration:
    """裁剪并分币后的履约分布矩及可计算的尾部误差上界，金额单位元。"""

    raw_location: float
    mean: float
    standard_deviation: float
    mean_tail_bound: float
    second_moment_tail_bound: float
    mean_roundoff_bound: float
    mean_cdf_crosscheck_error_estimate: float


def _roundoff_gamma(operation_count: int) -> float:
    """IEEE基本运算模型下γ_n；不给特殊函数本身附加未经证明的精度承诺。"""
    scaled = operation_count * np.finfo(float).eps
    if scaled >= 1:
        raise ArithmeticError("浮点求和误差界失效")
    return float(scaled / (1 - scaled))


def _pairwise_sum(values: ArrayLike) -> float:
    """显式平衡求和；最长加法路径为ceil(log2 n)，不依赖NumPy内部实现。"""
    current = np.asarray(values, dtype=float).reshape(-1)
    if not current.size:
        return 0.0
    while current.size > 1:
        even = (current.size // 2) * 2
        paired = current[:even:2] + current[1:even:2]
        current = np.concatenate((paired, current[-1:])) if even < current.size else paired
    return float(current[0])


def _pairwise_gamma(term_count: int, extra_operations: int = 0) -> float:
    depth = max(term_count - 1, 0).bit_length()
    return _roundoff_gamma(depth + extra_operations)


@dataclass(frozen=True)
class _ArithmeticValue:
    """仅追踪普通浮点加减乘；输入特殊函数数值误差由其他分项处理。"""

    value: NDArray[np.float64]
    error: NDArray[np.float64]

    @staticmethod
    def exact(value: ArrayLike) -> _ArithmeticValue:
        arr = np.asarray(value, dtype=float)
        return _ArithmeticValue(arr, np.zeros_like(arr))

    def __add__(self, other: _ArithmeticValue) -> _ArithmeticValue:
        value = self.value + other.value
        error = self.error + other.error + _roundoff_gamma(1) * abs(value)
        return _ArithmeticValue(value, error)

    def __neg__(self) -> _ArithmeticValue:
        return _ArithmeticValue(-self.value, self.error)

    def __sub__(self, other: _ArithmeticValue) -> _ArithmeticValue:
        return self + (-other)

    def __mul__(self, other: _ArithmeticValue) -> _ArithmeticValue:
        value = self.value * other.value
        error = abs(self.value) * other.error + abs(other.value) * self.error + self.error * other.error
        error = error + _roundoff_gamma(1) * abs(value)
        return _ArithmeticValue(value, error)


def _pairwise_arithmetic_sum(values: list[_ArithmeticValue]) -> _ArithmeticValue:
    current = values
    while len(current) > 1:
        even = (len(current) // 2) * 2
        paired = [current[i] + current[i + 1] for i in range(0, even, 2)]
        current = paired + current[even:]
    return current[0]


def _cent_array(values: ArrayLike, name: str) -> NDArray[np.int64]:
    arr = np.asarray(values)
    if np.any(~np.isfinite(arr)) or np.any(arr < 0) or np.any(arr != np.floor(arr)):
        raise ValueError(f"{name}必须是非负整数分")
    if np.any(arr > np.iinfo(np.int64).max):
        raise OverflowError(f"{name}超过int64")
    return arr.astype(np.int64)


def round_ratio_cent(amount_cent: ArrayLike, ratio: ArrayLike) -> NDArray[np.int64]:
    """按十进制比例逐组件half-up，避免银行家舍入及0.55二进制半分歧义。"""
    amount, rates = np.broadcast_arrays(_cent_array(amount_cent, "金额"), np.asarray(ratio, dtype=float))
    if np.any(~np.isfinite(rates)) or np.any(rates < 0):
        raise ValueError("金额比例必须非负有限")
    if not amount.size:
        return np.empty(amount.shape, dtype=np.int64)
    if np.all(rates == rates.flat[0]):
        numerator, denominator = Fraction(str(float(rates.flat[0]))).as_integer_ratio()
        largest = int(amount.max(initial=0))
        if numerator * largest * 2 + denominator <= np.iinfo(np.int64).max and denominator * 2 <= np.iinfo(np.int64).max:
            return ((amount * numerator * 2 + denominator) // (denominator * 2)).astype(np.int64)
    # 每用户不同成本率时全量向量计算，不作unique(rate)次全数组扫描。
    # float->最短十进制的误差不超过一个float ULP；加乘运算误差后用4 ULP
    # 包住半分判定区。仅该区回退任意精度整数，其余舍入结果必相同。
    raw = amount.astype(np.longdouble) * rates.astype(np.longdouble)
    rounded = np.floor(raw + 1 / 2)
    uncertainty = np.finfo(float).eps * np.maximum(np.abs(raw), 1) * (2 + 2)
    ambiguous = np.abs(raw - np.floor(raw) - 1 / 2) <= uncertainty
    rational_cache: dict[float, tuple[int, int]] = {}
    for j in np.flatnonzero(ambiguous.reshape(-1)):
        rate = float(rates.flat[j])
        if rate not in rational_cache:
            rational_cache[rate] = Fraction(str(rate)).as_integer_ratio()
        numerator, denominator = rational_cache[rate]
        rounded.flat[j] = (int(amount.flat[j]) * numerator * 2 + denominator) // (denominator * 2)
    if np.any(rounded > np.iinfo(np.int64).max):
        raise OverflowError("舍入后的金额超过int64")
    return rounded.astype(np.int64)


def _q_params(cfg: Config) -> tuple[float, float, float, float]:
    p = cfg.section("business.first_order_cart_fraction")
    values = tuple(float(p[k]) for k in (
        "mean_before_truncation", "sd_before_truncation", "lower_exclusive", "upper_inclusive",
    ))
    mean, sd, low, high = values
    if not (sd > 0 and 0 <= low < high <= 1):
        raise ValueError("首单金额比例参数非法")
    return mean, sd, low, high


def sample_fraction(uniform: ArrayLike, cfg: Config) -> NDArray[np.float64]:
    """以逆CDF产生条件截断正态Q，回答首单金额如何受购物车约束。"""
    u = np.asarray(uniform, dtype=float)
    if np.any(~np.isfinite(u)) or np.any((u < 0) | (u >= 1)):
        raise ValueError("逆CDF输入必须位于[0,1)")
    mean, sd, low, high = _q_params(cfg)
    cdf_low, cdf_high = ndtr((np.array([low, high]) - mean) / sd)
    q = mean + sd * ndtri(cdf_low + u * (cdf_high - cdf_low))
    # 修正仅由端点浮点运算产生的误差，非截断前正态的上限裁剪。
    return np.clip(q, np.nextafter(low, high), high)


def _fulfill_moments(location: float, sd: float, lower: float, unit: int, tail: float) -> tuple[float, ...]:
    floor_cent = int(np.floor(lower * unit + 1 / 2))
    upper = int(np.ceil((location + sd * ndtri(1 - tail)) * unit + 1 / 2))
    upper = max(upper, floor_cent)
    k = np.arange(floor_cent + 1, upper + 1, dtype=float)
    survival = ndtr((location * unit - (k - 1 / 2)) / (sd * unit))
    first = (floor_cent + _pairwise_sum(survival)) / unit
    second = (floor_cent**2 + _pairwise_sum((2 * k - 1) * survival)) / unit**2
    threshold = (upper + 1 / 2) / unit
    z = (threshold - location) / sd
    sf = float(ndtr(-z))
    density = float(np.exp(-z**2 / 2) / np.sqrt(2 * np.pi))
    excess = sd * (density - z * sf)
    # 对递减survival和递增线性权重的离散尾使用积分+首项上界。
    mean_bound = sf / unit + max(excess, 0)
    excess2 = sd**2 * ((1 + z**2) * sf - z * density)
    second_bound = (2 * upper + 1) * sf / unit**2
    second_bound += 2 * max(threshold, 0) * max(excess, 0) + max(excess2, 0)
    # 求和边界只控制已算出的survival值。CDF另以log-CDF恒等式复核，
    # 差异是数值估计，不冒称整个特殊函数计算已获严格区间证明。
    roundoff = _pairwise_gamma(len(k), extra_operations=2) * abs(first)
    alternate = (floor_cent + _pairwise_sum(np.exp(log_ndtr((location * unit - (k - 1 / 2)) / (sd * unit))))) / unit
    return float(first), float(second), float(mean_bound), float(second_bound), float(roundoff), abs(float(alternate - first))


@lru_cache(maxsize=int(_NUMERICS.require("cache.parameter_entries")))
def _fulfillment_cached(target: float, sd: float, lower: float, unit: int) -> FulfillmentCalibration:
    if not (sd > 0 and target > lower >= 0):
        raise ValueError("履约分布须满足sd>0且均值目标>下限>=0")
    tail = float(_NUMERICS.require("fulfillment.tail_probability"))
    width = float(_NUMERICS.require("fulfillment.bracket_sd_multiple")) * sd
    root = brentq(
        lambda location: _fulfill_moments(location, sd, lower, unit, tail)[0] - target,
        lower - width, target + width,
        xtol=float(_NUMERICS.require("fulfillment.location_xtol")),
    )
    mean, second, bound, second_bound, roundoff, crosscheck = _fulfill_moments(root, sd, lower, unit, tail)
    if abs(mean - target) + bound > float(_NUMERICS.require("integration.absolute_tolerance")):
        raise ArithmeticError("分币履约均值校准未达精度")
    return FulfillmentCalibration(root, mean, np.sqrt(max(second - mean**2, 0)), bound, second_bound, roundoff, crosscheck)


def fulfillment_calibration(cfg: Config) -> FulfillmentCalibration:
    """反解原始正态位置，保证不同履约噪声强度仍有相同分币后均值。"""
    return _fulfillment_cached(
        float(cfg.require("business.fulfill_cost_mean")), float(cfg.require("business.fulfill_cost_sd")),
        float(cfg.require("business.fulfill_cost_min")), int(cfg.require("business.money.cents_per_yuan")),
    )


def sample_amounts(
    cart_cent: ArrayLike, cfg: Config, *, master_seed: int, stream: str, index: int = 0
) -> AmountDraws:
    """生成共享两潜在动作的Q/首单/复购金额；允许零分订单且不改变随机流前缀。"""
    cart = _cent_array(cart_cent, "购物车")
    q = sample_fraction(child_rng(master_seed, f"{stream}.amounts.fraction", index).random(cart.shape), cfg)
    first = np.floor(cart * q).astype(np.int64)
    second = round_ratio_cent(first, float(cfg.require("business.repeat.gross_value_ratio")))
    calibration = fulfillment_calibration(cfg)
    raw = child_rng(master_seed, f"{stream}.amounts.fulfillment", index).normal(
        calibration.raw_location, float(cfg.require("business.fulfill_cost_sd")), cart.shape,
    )
    unit = int(cfg.require("business.money.cents_per_yuan"))
    fulfill = np.floor(np.maximum(raw, float(cfg.require("business.fulfill_cost_min"))) * unit + 1 / 2).astype(np.int64)
    if np.any(first > cart):
        raise AssertionError("首单金额超过购物车")
    return AmountDraws(first, second, q, fulfill)


def posted_components(
    gross_cent: ArrayLike, fulfill_cent: ArrayLike, redeemed: ArrayLike, refunded: ArrayLike,
    cfg: Config, *, goods_cost_ratio: ArrayLike | None = None, coupon_eligible: bool = True,
) -> dict[str, NDArray[np.int64]]:
    """逐单经营账，输出字段均为整数分；refunded指已计入窗口的退款事件。"""
    gross, fulfill, redeem, refund = np.broadcast_arrays(
        _cent_array(gross_cent, "订单总额"), _cent_array(fulfill_cent, "履约成本"),
        np.asarray(redeemed, dtype=bool), np.asarray(refunded, dtype=bool),
    )
    ratio = cfg.require("business.goods_cost_ratio") if goods_cost_ratio is None else goods_cost_ratio
    if np.any((np.asarray(ratio) < 0) | (np.asarray(ratio) > 1)):
        raise ValueError("商品成本率必须在[0,1]")
    goods = round_ratio_cent(gross, ratio)
    unit = int(cfg.require("business.money.cents_per_yuan"))
    face = int(round_ratio_cent(unit, cfg.require("business.coupon_reference_face")))
    discount = np.minimum(face, gross) * (redeem & coupon_eligible)
    coupon = discount * (1 - refund * bool(cfg.require("business.coupon_returned_on_refund")))
    recovery = round_ratio_cent(goods, cfg.require("business.refundable_goods_ratio")) * refund
    fee = round_ratio_cent(gross, cfg.require("business.refund_handling_fee_rate")) * refund
    result = {
        "gross_order_amount": gross, "gross_refund_reversal": gross * refund,
        "goods_cost": goods, "goods_cost_recovered": recovery, "fulfill_cost": fulfill,
        "coupon_discount": discount, "coupon_cost": coupon, "refund_processing_fee": fee,
        "consumer_paid": gross - discount, "consumer_refund": (gross - discount) * refund,
    }
    result["net_transaction_amount"] = gross - result["gross_refund_reversal"]
    result["net_profit"] = gross - result["gross_refund_reversal"] - goods + recovery - fulfill - coupon - fee
    return {key: np.asarray(value, dtype=np.int64) for key, value in result.items()}


@lru_cache(maxsize=int(_NUMERICS.require("cache.amount_distribution_entries")))
def _amount_distribution_cached(cart_cent: int, params: tuple[float, ...]) -> tuple[NDArray, NDArray]:
    mean, sd, low, high = params
    if cart_cent == 0:
        support, probability = np.array([0], dtype=np.int64), np.array([1.0])
    else:
        support = np.arange(int(np.floor(cart_cent * low)), int(np.ceil(cart_cent * high)), dtype=np.int64)
        left = np.maximum(support / cart_cent, low)
        right = np.minimum((support + 1) / cart_cent, high)
        zlo, zhi = (left - mean) / sd, (right - mean) / sd
        mass = np.where(zlo > 0, ndtr(-zlo) - ndtr(-zhi), ndtr(zhi) - ndtr(zlo))
        norm = ndtr((high - mean) / sd) - ndtr((low - mean) / sd)
        probability = mass / norm
        if np.any(probability < 0) or not np.isclose(_pairwise_sum(probability), 1):
            raise ArithmeticError("分币金额PMF失去概率质量")
    support.setflags(write=False)
    probability.setflags(write=False)
    return support, probability


def amount_distribution(cart_cent: int, cfg: Config) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """返回G1=floor(C_cent Q)的全部支持及精确CDF分段概率；只读数组可安全复用。"""
    cart = _cent_array(cart_cent, "购物车")
    if cart.ndim:
        raise ValueError("amount_distribution只接受一个购物车金额")
    return _amount_distribution_cached(int(cart), _q_params(cfg))


_MOMENT_NAMES = (
    "first_gross", "first_goods", "first_recovered", "first_fee", "first_coupon_cap",
    "repeat_gross", "repeat_goods", "repeat_recovered", "repeat_fee",
)


@lru_cache(maxsize=int(_NUMERICS.require("cache.amount_expectation_entries")))
def _order_moments_cached(cart: int, ratio: float, params: tuple[float, ...]) -> tuple[float, ...]:
    mean, sd, low, high, repeat_ratio, recovery_ratio, fee_ratio, face, unit = params
    gross, prob = _amount_distribution_cached(cart, (mean, sd, low, high))
    second = round_ratio_cent(gross, repeat_ratio)
    goods, second_goods = round_ratio_cent(gross, ratio), round_ratio_cent(second, ratio)
    components = (
        gross, goods, round_ratio_cent(goods, recovery_ratio), round_ratio_cent(gross, fee_ratio),
        np.minimum(gross, int(face)), second, second_goods,
        round_ratio_cent(second_goods, recovery_ratio), round_ratio_cent(second, fee_ratio),
    )
    return tuple(_pairwise_sum(prob * value) / unit for value in components)


def conditional_order_expectation(
    cart_cent: ArrayLike, cfg: Config, *, goods_cost_ratio: ArrayLike | None = None,
) -> dict[str, NDArray[np.float64]]:
    """对Q完整分币求和得到首/复购的已记账组件期望（元），未乘购买/退款概率。"""
    carts, rates = np.broadcast_arrays(
        _cent_array(cart_cent, "购物车"),
        np.asarray(cfg.require("business.goods_cost_ratio") if goods_cost_ratio is None else goods_cost_ratio, dtype=float),
    )
    if np.any(~np.isfinite(rates)) or np.any((rates < 0) | (rates > 1)):
        raise ValueError("商品成本率必须在[0,1]")
    unit = int(cfg.require("business.money.cents_per_yuan"))
    face = int(round_ratio_cent(unit, cfg.require("business.coupon_reference_face")))
    params = (
        *_q_params(cfg), float(cfg.require("business.repeat.gross_value_ratio")),
        float(cfg.require("business.refundable_goods_ratio")), float(cfg.require("business.refund_handling_fee_rate")),
        float(face), float(unit),
    )
    pairs = np.rec.fromarrays([carts.reshape(-1), rates.reshape(-1)], names="cart,rate")
    unique, inverse = np.unique(pairs, return_inverse=True)
    values = np.array([_order_moments_cached(int(pair.cart), float(pair.rate), params) for pair in unique])
    if not len(unique):
        values = np.empty((0, len(_MOMENT_NAMES)))
    result = {key: values[inverse, i].reshape(carts.shape) for i, key in enumerate(_MOMENT_NAMES)}
    result["fulfillment_mean"] = np.full(carts.shape, fulfillment_calibration(cfg).mean)
    return result


def conditional_user_expectation(
    cart_cent: ArrayLike, cfg: Config, *, purchase_probability: ArrayLike,
    refund_probability: ArrayLike, redemption_probability: ArrayLike,
    goods_cost_ratio: ArrayLike | None = None,
) -> dict[str, NDArray[np.float64]]:
    """计算全体分配用户的30天利润/成本真值及任一单退款率；金额输出单位元。"""
    m = conditional_order_expectation(cart_cent, cfg, goods_cost_ratio=goods_cost_ratio)
    purchase, refund, redeem, _ = np.broadcast_arrays(
        np.asarray(purchase_probability, dtype=float), np.asarray(refund_probability, dtype=float),
        np.asarray(redemption_probability, dtype=float), m["first_gross"],
    )
    if any(np.any(~np.isfinite(v)) or np.any((v < 0) | (v > 1)) for v in (purchase, refund, redeem)):
        raise ValueError("购买/退款/核销概率必须位于[0,1]")
    t = timing_coefficients(cfg)
    rho = float(cfg.require("business.repeat.probability_given_first_order")) if cfg.require("business.repeat.enabled") else 0.0
    returned = bool(cfg.require("business.coupon_returned_on_refund"))
    gross = m["first_gross"] * t.first_order + rho * m["repeat_gross"] * t.repeat_order
    gross_refund = refund * (m["first_gross"] * t.first_refund + rho * m["repeat_gross"] * t.repeat_refund)
    goods = m["first_goods"] * t.first_order + rho * m["repeat_goods"] * t.repeat_order
    recovered = refund * (m["first_recovered"] * t.first_refund + rho * m["repeat_recovered"] * t.repeat_refund)
    fee = refund * (m["first_fee"] * t.first_refund + rho * m["repeat_fee"] * t.repeat_refund)
    fulfill = m["fulfillment_mean"] * (t.first_order + rho * t.repeat_order)
    discount = redeem * m["first_coupon_cap"] * t.first_order
    coupon = redeem * m["first_coupon_cap"] * (t.first_order - returned * refund * t.first_refund)
    result: dict[str, Any] = {
        "gross_order_amount": gross, "gross_refund_reversal": gross_refund, "goods_cost": goods,
        "goods_cost_recovered": recovered, "fulfill_cost": fulfill, "coupon_discount": discount,
        "coupon_cost": coupon, "refund_processing_fee": fee,
        "consumer_paid": gross - discount,
        "consumer_refund": gross_refund - redeem * m["first_coupon_cap"] * refund * t.first_refund,
        "net_transaction_amount": gross - gross_refund,
        "net_profit": gross - gross_refund - goods + recovered - fulfill - coupon - fee,
        "any_refund_probability": refund * t.first_refund + rho * refund * t.repeat_refund - rho * refund**2 * t.both_refunds,
        "purchase_probability_7d": t.first_conversion,
        "order_count": t.first_order + rho * t.repeat_order,
    }
    return {key: np.asarray(purchase * value, dtype=float) for key, value in result.items()}


@lru_cache(maxsize=int(_NUMERICS.require("cache.amount_expectation_entries")))
def _order_error_cached(cart: int, ratio: float, params: tuple[float, ...]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """用等价尾和及标准浮点求和界逐组件复核分币质量求和，单位元。"""
    mean, sd, low, high, repeat_ratio, recovery_ratio, fee_ratio, face, unit = params
    gross, prob = _amount_distribution_cached(cart, (mean, sd, low, high))
    second = round_ratio_cent(gross, repeat_ratio)
    goods, second_goods = round_ratio_cent(gross, ratio), round_ratio_cent(second, ratio)
    components = (
        gross, goods, round_ratio_cent(goods, recovery_ratio), round_ratio_cent(gross, fee_ratio),
        np.minimum(gross, int(face)), second, second_goods,
        round_ratio_cent(second_goods, recovery_ratio), round_ratio_cent(second, fee_ratio),
    )
    if cart:
        normalizer = ndtr((high - mean) / sd) - ndtr((low - mean) / sd)
        log_sf = log_ndtr((mean - gross[1:] / cart) / sd)
        log_sf_high = log_ndtr((mean - high) / sd)
        # 稳定log-CDF差构成尾概率；相对原实现同时改变函数和求和恒等式。
        survival = np.exp(log_sf) * (-np.expm1(log_sf_high - log_sf)) / normalizer
    else:
        survival = np.empty(0)
    production = _order_moments_cached(cart, ratio, params)
    mass_defect = abs(_pairwise_sum(prob) - 1)
    roundoff: list[float] = []
    crosscheck: list[float] = []
    for expected, component in zip(production, components):
        terms = np.diff(component) * survival
        tail_value = float((component[0] + _pairwise_sum(terms)) / unit)
        # 生产和交叉核验均显式pairwise；额外路径包含乘法、初值相加和除元。
        gamma = _pairwise_gamma(len(component), extra_operations=2 + 1)
        roundoff.append(gamma * (abs(expected) + abs(tail_value)))
        crosscheck.append(abs(expected - tail_value) + mass_defect * float(component.max()) / unit)
    return tuple(roundoff), tuple(crosscheck)


def _order_error_arrays(
    cart_cent: ArrayLike, cfg: Config, goods_cost_ratio: ArrayLike | None,
) -> tuple[dict[str, NDArray[np.float64]], dict[str, NDArray[np.float64]]]:
    carts, rates = np.broadcast_arrays(
        _cent_array(cart_cent, "购物车"),
        np.asarray(cfg.require("business.goods_cost_ratio") if goods_cost_ratio is None else goods_cost_ratio, dtype=float),
    )
    unit = int(cfg.require("business.money.cents_per_yuan"))
    face = int(round_ratio_cent(unit, cfg.require("business.coupon_reference_face")))
    params = (
        *_q_params(cfg), float(cfg.require("business.repeat.gross_value_ratio")),
        float(cfg.require("business.refundable_goods_ratio")), float(cfg.require("business.refund_handling_fee_rate")),
        float(face), float(unit),
    )
    pairs = np.rec.fromarrays([carts.reshape(-1), rates.reshape(-1)], names="cart,rate")
    unique, inverse = np.unique(pairs, return_inverse=True)
    estimates = np.array([_order_error_cached(int(pair.cart), float(pair.rate), params) for pair in unique])
    if not len(unique):
        estimates = np.empty((0, 2, len(_MOMENT_NAMES)))
    roundoff = {key: estimates[inverse, 0, i].reshape(carts.shape) for i, key in enumerate(_MOMENT_NAMES)}
    crosscheck = {key: estimates[inverse, 1, i].reshape(carts.shape) for i, key in enumerate(_MOMENT_NAMES)}
    return roundoff, crosscheck


def conditional_expectation_numerical_error(
    cart_cent: ArrayLike, cfg: Config, *, purchase_probability: ArrayLike,
    refund_probability: ArrayLike, redemption_probability: ArrayLike,
    goods_cost_ratio: ArrayLike | None = None,
) -> dict[str, NDArray[np.float64]]:
    """将时间/履约/分币数值误差传播到每用户净利润（元），不混入业务组件。

    合计是数值误差估计；仅标明bound的分项对应尾和或标准浮点基本运算界。
    U积分误差属于概率机制，应由上层再乘条件订单利润后加入。
    """
    m = conditional_order_expectation(cart_cent, cfg, goods_cost_ratio=goods_cost_ratio)
    purchase, refund, redeem, _ = np.broadcast_arrays(
        np.asarray(purchase_probability, dtype=float), np.asarray(refund_probability, dtype=float),
        np.asarray(redemption_probability, dtype=float), m["first_gross"],
    )
    if any(np.any(~np.isfinite(v)) or np.any((v < 0) | (v > 1)) for v in (purchase, refund, redeem)):
        raise ValueError("购买/退款/核销概率必须位于[0,1]")
    roundoff, crosscheck = _order_error_arrays(cart_cent, cfg, goods_cost_ratio)
    t = timing_coefficients(cfg)
    e = t.integration_error_bound
    rho = float(cfg.require("business.repeat.probability_given_first_order")) if cfg.require("business.repeat.enabled") else 0.0
    returned = bool(cfg.require("business.coupon_returned_on_refund"))
    f = fulfillment_calibration(cfg)
    time_envelope = (
        abs(m["first_gross"] - m["first_goods"] - f.mean - redeem * m["first_coupon_cap"])
        + rho * abs(m["repeat_gross"] - m["repeat_goods"] - f.mean)
        + refund * abs(-m["first_gross"] + m["first_recovered"] - m["first_fee"] + returned * redeem * m["first_coupon_cap"])
        + rho * refund * abs(-m["repeat_gross"] + m["repeat_recovered"] - m["repeat_fee"])
    )
    # 系数取绝对上界并加入时间误差，覆盖时间与金额误差交叉项。
    weights = {
        "first_gross": t.first_order + e + refund * (t.first_refund + e),
        "first_goods": t.first_order + e,
        "first_recovered": refund * (t.first_refund + e),
        "first_fee": refund * (t.first_refund + e),
        "first_coupon_cap": redeem * (t.first_order + e + returned * refund * (t.first_refund + e)),
        "repeat_gross": rho * (t.repeat_order + e + refund * (t.repeat_refund + e)),
        "repeat_goods": rho * (t.repeat_order + e),
        "repeat_recovered": rho * refund * (t.repeat_refund + e),
        "repeat_fee": rho * refund * (t.repeat_refund + e),
    }
    fulfill_weight = t.first_order + rho * t.repeat_order + (1 + rho) * e
    envelope = sum(weights[key] * abs(m[key]) for key in _MOMENT_NAMES) + fulfill_weight * abs(f.mean)
    pieces = {
        "net_profit_time_error_estimate_cny": purchase * e * time_envelope,
        "net_profit_fulfillment_tail_bound_cny": purchase * fulfill_weight * f.mean_tail_bound,
        "net_profit_fulfillment_roundoff_bound_cny": purchase * fulfill_weight * f.mean_roundoff_bound,
        "net_profit_fulfillment_cdf_crosscheck_estimate_cny": purchase * fulfill_weight * f.mean_cdf_crosscheck_error_estimate,
        "net_profit_discrete_roundoff_bound_cny": purchase * sum(weights[key] * roundoff[key] for key in _MOMENT_NAMES),
        "net_profit_discrete_cdf_crosscheck_estimate_cny": purchase * sum(weights[key] * crosscheck[key] for key in _MOMENT_NAMES),
        "net_profit_assembly_roundoff_bound_cny": purchase * _roundoff_gamma(2 * (len(_MOMENT_NAMES) + 1)**2) * envelope,
    }
    pieces["net_profit_numerical_error_estimate_cny"] = sum(pieces.values())
    pieces["conditional_profit_absolute_envelope_cny"] = envelope
    return {key: np.asarray(value, dtype=float) for key, value in pieces.items()}


def paired_conditional_expectation_numerical_error(
    cart_cent: ArrayLike, cfg: Config, *, purchase_probability0: ArrayLike, purchase_probability1: ArrayLike,
    refund_probability0: ArrayLike, refund_probability1: ArrayLike,
    redemption_probability0: ArrayLike, redemption_probability1: ArrayLike,
    goods_cost_ratio: ArrayLike | None = None,
) -> dict[str, NDArray[np.float64]]:
    """直接汇总两动作共享组件的CATE与误差，避免先加两个粗界后除接近零的CATE。"""
    m = conditional_order_expectation(cart_cent, cfg, goods_cost_ratio=goods_cost_ratio)
    p0, p1, r0, r1, d0, d1, _ = np.broadcast_arrays(
        *map(lambda x: np.asarray(x, dtype=float), (
            purchase_probability0, purchase_probability1, refund_probability0, refund_probability1,
            redemption_probability0, redemption_probability1,
        )), m["first_gross"],
    )
    if any(np.any(~np.isfinite(v)) or np.any((v < 0) | (v > 1)) for v in (p0, p1, r0, r1, d0, d1)):
        raise ValueError("购买/退款/核销概率必须位于[0,1]")
    ap0, ap1, ar0, ar1, ad0, ad1 = map(_ArithmeticValue.exact, (p0, p1, r0, r1, d0, d1))
    adp, adpr, adpd = ap1 - ap0, ap1 * ar1 - ap0 * ar0, ap1 * ad1 - ap0 * ad0
    adprd = ap1 * ar1 * ad1 - ap0 * ar0 * ad0
    dp, dpr, dpd, dprd = adp.value, adpr.value, adpd.value, adprd.value
    identical = (p1 == p0) & (r1 == r0) & (d1 == d0)
    t = timing_coefficients(cfg)
    e = t.integration_error_bound
    rho = float(cfg.require("business.repeat.probability_given_first_order")) if cfg.require("business.repeat.enabled") else 0.0
    returned = bool(cfg.require("business.coupon_returned_on_refund"))
    f = fulfillment_calibration(cfg)
    roundoff, crosscheck = _order_error_arrays(cart_cent, cfg, goods_cost_ratio)
    aa1, aa2, ab1, ab2, arh, aret = map(_ArithmeticValue.exact, (
        t.first_order, t.repeat_order, t.first_refund, t.repeat_refund, rho, returned,
    ))
    arithmetic_weights = {
        "first_gross": adp * aa1 - adpr * ab1,
        "first_goods": -adp * aa1,
        "first_recovered": adpr * ab1,
        "first_fee": -adpr * ab1,
        "first_coupon_cap": -adpd * aa1 + aret * adprd * ab1,
        "repeat_gross": arh * (adp * aa2 - adpr * ab2),
        "repeat_goods": -arh * adp * aa2,
        "repeat_recovered": arh * adpr * ab2,
        "repeat_fee": -arh * adpr * ab2,
    }
    weights = {key: value.value for key, value in arithmetic_weights.items()}
    time_uncertainty = {
        "first_gross": e * (abs(dp) + abs(dpr)), "first_goods": e * abs(dp),
        "first_recovered": e * abs(dpr), "first_fee": e * abs(dpr),
        "first_coupon_cap": e * (abs(dpd) + returned * abs(dprd)),
        "repeat_gross": rho * e * (abs(dp) + abs(dpr)), "repeat_goods": rho * e * abs(dp),
        "repeat_recovered": rho * e * abs(dpr), "repeat_fee": rho * e * abs(dpr),
    }
    absolute_weights = {key: abs(weights[key]) + time_uncertainty[key] for key in _MOMENT_NAMES}
    arithmetic_fulfill_weight = -adp * (aa1 + arh * aa2)
    fulfill_weight = arithmetic_fulfill_weight.value
    absolute_fulfill_weight = abs(fulfill_weight) + abs(dp) * (1 + rho) * e
    time_envelope = (
        abs(dp * (m["first_gross"] - m["first_goods"] - f.mean) - dpd * m["first_coupon_cap"])
        + rho * abs(dp * (m["repeat_gross"] - m["repeat_goods"] - f.mean))
        + abs(dpr * (-m["first_gross"] + m["first_recovered"] - m["first_fee"]) + returned * dprd * m["first_coupon_cap"])
        + rho * abs(dpr * (-m["repeat_gross"] + m["repeat_recovered"] - m["repeat_fee"]))
    )
    # 对δ(pr)等乘积差以及最终平衡加法逐操作追踪，不再使用两臂规模×粗略γ。
    assembled = _pairwise_arithmetic_sum(
        [arithmetic_weights[key] * _ArithmeticValue.exact(m[key]) for key in _MOMENT_NAMES]
        + [arithmetic_fulfill_weight * _ArithmeticValue.exact(f.mean)]
    )
    pieces = {
        "net_profit_time_error_estimate_cny": e * time_envelope,
        "net_profit_fulfillment_tail_bound_cny": absolute_fulfill_weight * f.mean_tail_bound,
        "net_profit_fulfillment_roundoff_bound_cny": absolute_fulfill_weight * f.mean_roundoff_bound,
        "net_profit_fulfillment_cdf_crosscheck_estimate_cny": absolute_fulfill_weight * f.mean_cdf_crosscheck_error_estimate,
        "net_profit_discrete_roundoff_bound_cny": sum(absolute_weights[key] * roundoff[key] for key in _MOMENT_NAMES),
        "net_profit_discrete_cdf_crosscheck_estimate_cny": sum(absolute_weights[key] * crosscheck[key] for key in _MOMENT_NAMES),
        "net_profit_assembly_roundoff_bound_cny": np.where(identical, 0, assembled.error),
    }
    pieces["net_profit_numerical_error_estimate_cny"] = sum(pieces.values())
    pieces["net_profit_difference_cny"] = assembled.value
    pieces["conditional_profit_absolute_envelope_cny"] = sum(absolute_weights[key] * abs(m[key]) for key in _MOMENT_NAMES) + absolute_fulfill_weight * f.mean
    return {key: np.asarray(value, dtype=float) for key, value in pieces.items()}
