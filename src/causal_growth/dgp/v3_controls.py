"""合成数据 / 已知 DGP：L0-Π 的显式人工同质化控制及隔离审计。

本模块只改变实际商品成本率与实际核销概率，不修改最终利润或真值。
所有可行性字段属于审计信息，不能加入学习者的用户特征或资格筛选。
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike, NDArray

from causal_growth.config import Config, ConfigError
from causal_growth.dgp.v3_amounts import conditional_order_expectation, conditional_user_expectation
from causal_growth.dgp.v3_timing import timing_coefficients
from causal_growth.v3_numerics import load_v3_numerics


@dataclass(frozen=True)
class L0ControlResult:
    """人工成本机制与审计分开；仅前两个数组用于生成潜在交易。"""

    goods_cost_ratio: NDArray[np.float64]
    redemption_probability: NDArray[np.float64]
    audit: pd.DataFrame


@dataclass(frozen=True, slots=True)
class _ScalarControl:
    goods_cost_ratio: float
    redemption_probability: float
    natural_profit_cate_cny: float
    profit_cate_cny: float
    coupon_cost_cny: float
    target_profit_cate_cny: float
    profit_residual_cny: float
    candidate_goods_cost_ratio: float
    candidate_redemption_probability: float
    candidate_profit_residual_cny: float
    unrounded_goods_candidate_ratio: float
    probability_only_effect_min_cny: float
    probability_only_effect_max_cny: float
    probability_only_required_p1: float
    probability_only_feasible: bool
    cost_control_feasible: bool
    profit_control_feasible: bool
    control_feasible: bool
    knob_applied: bool
    redemption_control_applied: bool
    reason: str
    exact_expectation_evaluations: int


_CACHE: OrderedDict[tuple[str, int, float, float], _ScalarControl] = OrderedDict()


def _validate(cfg: Config) -> None:
    level = cfg.get("active_scenario.level")
    if (
        level != "L0"
        or cfg.require("dgp.profile") != "l0_profit_control"
        or not cfg.require("dgp.l0.control.enabled")
        or level not in cfg.require("dgp.l0.control.knob_allowed_levels")
    ):
        raise ConfigError("同质化旋钮只允许已显式启用的 L0-Π 场景")
    mode = cfg.require("dgp.l0.control.cost_mode")
    if mode not in {"natural_expected_cost", "constant_expected_cost"}:
        raise ConfigError(f"未知 L0 控制成本模式：{mode}")
    bounds = np.asarray(cfg.require("dgp.l0.control.effective_gross_margin_bounds"), dtype=float)
    if bounds.shape != (2,) or not 0 <= bounds[0] < bounds[1] <= 1:
        raise ConfigError("有效毛利率边界必须为 [lower, upper] 且位于 [0,1]")
    if cfg.require("dgp.l0.control.natural_goods_cost_ratio") != cfg.require("business.goods_cost_ratio"):
        raise ConfigError("自然商品成本率与业务基准不一致，不能隐式选择回退机制")
    for key in ("business.redemption_rate", "business.refund_rate", "business.refundable_goods_ratio"):
        if not 0 <= float(cfg.require(key)) <= 1:
            raise ConfigError(f"{key} 必须位于 [0,1]")
    if not 0 <= float(cfg.require("business.refund_rate")) * float(cfg.require("business.refund_rate_treated_multiplier")) <= 1:
        raise ConfigError("发券状态退款概率越界")
    if float(cfg.require("dgp.l0.control.homogeneity_numerical_tolerance_cny")) <= 0:
        raise ConfigError("利润同质容差必须为正")
    if float(cfg.require("dgp.l0.control.constant_expected_coupon_cost_cny")) < 0:
        raise ConfigError("等成本目标不能为负")


def _scalar_expectation(
    cart: int, cfg: Config, p: float, refund: float, redemption: float, goods: float,
) -> tuple[float, float]:
    expected = conditional_user_expectation(
        cart, cfg, purchase_probability=p, refund_probability=refund,
        redemption_probability=redemption, goods_cost_ratio=goods,
    )
    return float(np.asarray(expected["net_profit"])), float(np.asarray(expected["coupon_cost"]))


def _solve_scalar(cart: int, p0: float, p1: float, cfg: Config) -> _ScalarControl:
    natural_g = float(cfg.require("dgp.l0.control.natural_goods_cost_ratio"))
    natural_r = float(cfg.require("business.redemption_rate"))
    target = float(cfg.require("dgp.l0.control.target_profit_cate_cny"))
    tolerance = float(cfg.require("dgp.l0.control.homogeneity_numerical_tolerance_cny"))
    refund0 = float(cfg.require("business.refund_rate"))
    refund1 = refund0 * float(cfg.require("business.refund_rate_treated_multiplier"))
    # Every user uses the same goods rate in both states and both orders. Since
    # rounded recovery increases by at most the increase in rounded goods cost,
    # these sufficient bounds establish a common monotone direction even when
    # refund events cross the window boundary. Reject unsupported shapes rather
    # than treating an arbitrary function as a monotone one.
    goods_weight = -(p1 - p0)
    recovery_weight = p1 * refund1 - p0 * refund0
    nonincreasing = goods_weight + max(recovery_weight, 0) <= 0
    nondecreasing = goods_weight + min(recovery_weight, 0) >= 0
    if not (nonincreasing or nondecreasing):
        raise ConfigError("当前 p0/p1 与退款机制不满足有界单调搜索条件")

    a0, _ = _scalar_expectation(cart, cfg, 1, refund0, 0, natural_g)
    a1, _ = _scalar_expectation(cart, cfg, 1, refund1, natural_r, natural_g)
    probability_endpoints = (-p0 * a0, a1 - p0 * a0)
    required_p1 = (target + p0 * a0) / a1 if a1 != 0 else float("nan")
    probability_feasible = (
        0 <= required_p1 <= 1 if a1 != 0 else abs(target + p0 * a0) <= tolerance
    )
    natural_cate = p1 * a1 - p0 * a0
    _, natural_cost = _scalar_expectation(cart, cfg, p1, refund1, natural_r, natural_g)

    chosen_r = natural_r
    cost_feasible = True
    if cfg.require("dgp.l0.control.cost_mode") == "constant_expected_cost":
        cost_target = float(cfg.require("dgp.l0.control.constant_expected_coupon_cost_cny"))
        # Integrates min(face,G), actual purchase, coupon returns and event time.
        # For the frozen no-return mechanism this is p1 E[min(face,G1)].
        _, denominator = _scalar_expectation(cart, cfg, p1, refund1, 1, natural_g)
        if denominator == 0:
            chosen_r = natural_r if cost_target == 0 else float("nan")
            cost_feasible = cost_target == 0
        else:
            chosen_r = cost_target / denominator
            cost_feasible = 0 <= chosen_r <= 1

    count = 0
    values: dict[float, float] = {}

    def effect(goods: float) -> float:
        nonlocal count
        if goods not in values:
            mu0, _ = _scalar_expectation(cart, cfg, p0, refund0, 0, goods)
            mu1, _ = _scalar_expectation(cart, cfg, p1, refund1, chosen_r, goods)
            values[goods] = mu1 - mu0
            count += 1
        return values[goods]

    candidate_g = natural_g
    candidate_residual = natural_cate - target
    unrounded_candidate = float("nan")
    profit_feasible = False
    reason = "coupon_cost_target_infeasible"
    if cost_feasible:
        margins = cfg.require("dgp.l0.control.effective_gross_margin_bounds")
        lo, hi = (float(1 - Fraction(str(margins[index]))) for index in (1, 0))
        bound_lo, bound_hi = lo, hi

        def nearest_legal_candidate() -> float:
            return min((candidate for candidate in values if bound_lo <= candidate <= bound_hi),
                       key=lambda candidate: (abs(values[candidate] - target), candidate))

        left, right = effect(lo), effect(hi)
        candidate_g = nearest_legal_candidate()
        if min(left, right) - tolerance <= target <= max(left, right) + tolerance:
            # Remove rounding only from goods and recovery for an algebraic
            # initial proposal. Gross, fees and coupon caps keep their exact
            # cent-distribution moments. The proposal is never accepted without
            # checking the fully rounded ledger expectation.
            moments = conditional_order_expectation(cart, cfg, goods_cost_ratio=natural_g)
            timing = timing_coefficients(cfg)
            repeat = float(cfg.require("business.repeat.probability_given_first_order")) if cfg.require("business.repeat.enabled") else 0
            recovery_ratio = float(cfg.require("business.refundable_goods_ratio"))
            rounded_goods_part = (
                goods_weight * (timing.first_order * float(moments["first_goods"])
                                + repeat * timing.repeat_order * float(moments["repeat_goods"]))
                + recovery_weight * (timing.first_refund * float(moments["first_recovered"])
                                     + repeat * timing.repeat_refund * float(moments["repeat_recovered"]))
            )
            slope = (
                float(moments["first_gross"]) * (goods_weight * timing.first_order + recovery_weight * recovery_ratio * timing.first_refund)
                + repeat * float(moments["repeat_gross"]) * (goods_weight * timing.repeat_order + recovery_weight * recovery_ratio * timing.repeat_refund)
            )
            intercept = effect(natural_g) - rounded_goods_part
            if slope != 0:
                unrounded_candidate = (target - intercept) / slope
            if lo <= unrounded_candidate <= hi:
                effect(unrounded_candidate)
                candidate_g = nearest_legal_candidate()
            max_iterations = int(cfg.require("dgp.l0.control.numerical_solver.max_iterations"))
            interval_tolerance = float(cfg.require("dgp.l0.control.numerical_solver.parameter_interval_tolerance"))
            for _ in range(max_iterations):
                if abs(values[candidate_g] - target) <= tolerance or hi - lo <= interval_tolerance:
                    break
                middle = (lo + hi) / 2
                value = effect(middle)
                candidate_g = nearest_legal_candidate()
                if (value < target) == nondecreasing:
                    lo = middle
                else:
                    hi = middle
            profit_feasible = abs(values[candidate_g] - target) <= tolerance
            reason = "within_declared_numerical_tolerance" if profit_feasible else "no_step_value_within_effect_tolerance"
        else:
            reason = "profit_target_outside_bounded_knob_range"
        candidate_residual = values[candidate_g] - target

    feasible = cost_feasible and profit_feasible
    actual_g = candidate_g if feasible else natural_g
    actual_r = chosen_r if feasible else natural_r
    if feasible:
        cate = values[candidate_g]
        _, cost = _scalar_expectation(cart, cfg, p1, refund1, actual_r, actual_g)
    else:
        cate, cost = natural_cate, natural_cost
    return _ScalarControl(
        goods_cost_ratio=actual_g, redemption_probability=actual_r,
        natural_profit_cate_cny=natural_cate, profit_cate_cny=cate,
        coupon_cost_cny=cost, target_profit_cate_cny=target,
        profit_residual_cny=cate - target, candidate_goods_cost_ratio=candidate_g,
        candidate_redemption_probability=chosen_r,
        candidate_profit_residual_cny=candidate_residual,
        unrounded_goods_candidate_ratio=unrounded_candidate,
        probability_only_effect_min_cny=min(probability_endpoints),
        probability_only_effect_max_cny=max(probability_endpoints),
        probability_only_required_p1=required_p1,
        probability_only_feasible=bool(probability_feasible),
        cost_control_feasible=bool(cost_feasible), profit_control_feasible=bool(profit_feasible),
        control_feasible=bool(feasible), knob_applied=bool(feasible and actual_g != natural_g),
        redemption_control_applied=bool(feasible and actual_r != natural_r),
        reason=reason, exact_expectation_evaluations=count,
    )


def solve_l0_profit_control(
    cart_cent: ArrayLike, p0: ArrayLike, p1: ArrayLike, cfg: Config,
) -> L0ControlResult:
    """回答 L0-Π 是否能在合法成本旋钮内实现目标及真实等期望核销成本。

    输入允许标量或可广播的一维数组；数组位置对应同一批用户。失败用户仍
    保留自然商品成本率和自然核销概率。审计表不得进入学习或策略选择接口。
    重复的 ``(配置, cart_cent, p0, p1)`` 复用确定性求解，不复用随机结果。
    """
    _validate(cfg)
    raw_cart, raw_p0, raw_p1 = np.broadcast_arrays(
        np.asarray(cart_cent), np.asarray(p0, dtype=float), np.asarray(p1, dtype=float),
    )
    if raw_cart.ndim > 1:
        raise ValueError("L0 控制输入必须为标量或一维用户数组")
    if not np.issubdtype(raw_cart.dtype, np.number) or not np.all(np.isfinite(raw_cart)):
        raise ValueError("cart_cent 必须为有限整数分")
    if np.any(raw_cart < 0) or np.any(raw_cart != np.floor(raw_cart)):
        raise ValueError("cart_cent 必须为非负整数分")
    if np.any(raw_cart > np.iinfo(np.int64).max):
        raise OverflowError("cart_cent 超过 int64 分币上限")
    if not (np.all(np.isfinite(raw_p0)) and np.all(np.isfinite(raw_p1))):
        raise ValueError("购买概率必须有限")
    if np.any((raw_p0 < 0) | (raw_p0 > 1) | (raw_p1 < 0) | (raw_p1 > 1)):
        raise ValueError("购买概率必须位于 [0,1]，不会静默裁剪")
    cart = np.atleast_1d(raw_cart).astype(np.int64)
    before, after = np.atleast_1d(raw_p0), np.atleast_1d(raw_p1)
    keys = np.rec.fromarrays([cart, before, after], names="cart,p0,p1")
    unique, inverse = np.unique(keys, return_inverse=True)
    config_hash = cfg.hash(length=64)  # Full SHA-256 cache identity; not a business parameter.
    cache_capacity = int(load_v3_numerics().require("controls.cache_max_entries"))
    if cache_capacity < 0:
        raise ConfigError("controls.cache_max_entries 不能为负")
    solved: list[dict[str, Any]] = []
    for item in unique:
        key = (config_hash, int(item.cart), float(item.p0), float(item.p1))
        if key in _CACHE:
            scalar = _CACHE.pop(key)
        else:
            scalar = _solve_scalar(key[1], key[2], key[3], cfg)
        if cache_capacity:
            _CACHE[key] = scalar
            while len(_CACHE) > cache_capacity:
                _CACHE.popitem(last=False)
        solved.append(asdict(scalar))
    if not solved:
        fields = list(_ScalarControl.__dataclass_fields__)
        audit = pd.DataFrame(columns=fields)
    else:
        audit = pd.DataFrame(solved).iloc[inverse].reset_index(drop=True)
    audit.insert(0, "cart_cent", cart)
    audit.insert(1, "p0", before)
    audit.insert(2, "p1", after)
    audit.attrs.update(source="合成数据 / 已知 DGP", audit_only=True, config_hash=config_hash,
                       cost_mode=cfg.require("dgp.l0.control.cost_mode"))
    return L0ControlResult(audit["goods_cost_ratio"].to_numpy(dtype=float),
                           audit["redemption_probability"].to_numpy(dtype=float), audit)


def audit_common_feasible_mask(
    equal_cost: L0ControlResult, natural_cost: L0ControlResult,
) -> NDArray[np.bool_]:
    """仅用于冻结后审计：给出两个控制场景同一批用户的共同可行子集。

    本函数不筛除任何用户、不修改生成数据，也不产生可学习的特征。主流程
    必须在观测策略与评估冻结后调用，并同时报告全体与该子集结果。
    """
    if equal_cost.audit.attrs.get("cost_mode") != "constant_expected_cost" or natural_cost.audit.attrs.get("cost_mode") != "natural_expected_cost":
        raise ValueError("共同域要求一个等成本控制及一个自然成本控制")
    columns = ["cart_cent", "p0", "p1"]
    if not equal_cost.audit[columns].equals(natural_cost.audit[columns]):
        raise ValueError("两个控制场景必须使用相同顺序的用户与购买概率")
    return (equal_cost.audit["control_feasible"].to_numpy(dtype=bool)
            & natural_cost.audit["control_feasible"].to_numpy(dtype=bool))
