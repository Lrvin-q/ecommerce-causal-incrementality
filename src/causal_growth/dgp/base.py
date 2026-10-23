"""DGP 引擎：给定 ``p0(X)`` 与 ``τ(X)``，采样潜在结果并构造解析真值。

四条设计原则
------------
1. **comonotonic coupling**（方案 §3.3 L1）：同一个 ``U ~ Uniform(0,1)`` 驱动
   两个潜在转化结果，``y0 = 1[U < p0]``、``y1 = 1[U < p1]``，于是 ``y1 ≥ y0``
   **逐个体恒成立**，且同一用户的两种潜在结果高度相关。若不这样做，
   个体效应会被"两次独立抽样"的噪声淹没，CATE 学习就变成拟合噪声。
2. **订单特征共享**：``pay_amount`` / ``fulfill_cost`` / 退款倾向 等"订单特征"
   在 T=0 与 T=1 之间复用同一次抽样。这样个体效应只反映"券带来的转化增量"
   与"券成本"，而不是两笔无关订单的随机差值。
3. **真值解析算**：``cate_profit = p1·A1 − p0·A0``，``A`` 为**已转化订单**的
   期望净贡献利润。个体实测利润差 ``pi1 − pi0`` **不是**真值（含噪声）。
4. **截距校准**：``β₀ / γ₀`` 由业务目标（``E[p0]``、``E[τ]``）反解，
   配置里不出现手调截距——每个参数都能回答"从哪来"（方案附录 A.1）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import brentq
from scipy.special import expit

from causal_growth.contracts import (
    FEATURE_ORDER,
    Covariates,
    GroundTruth,
    Population,
    PotentialOutcomes,
)
from causal_growth.data.profit import expected_order_net_profit

__all__ = [
    "OrderDraws",
    "build_population_from_curves",
    "calibrate_intercept",
    "face_response",
    "generate_covariates",
    "linear_predictor",
    "realized_order_net",
    "sample_order_draws",
]


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def calibrate_intercept(
    linear_predictor: np.ndarray,
    target_mean: float,
    *,
    lo: float = -20.0,
    hi: float = 20.0,
) -> float:
    """解 δ 使 ``mean(expit(linear_predictor + δ)) == target_mean``。

    为什么需要它：配置里给的是**业务目标**（"平均转化率 10%"），
    而 DGP 需要的是**模型截距**。硬编码截距等于拍脑袋，且目标一改就对不上。
    这里用一维求根反解，使得 ``E[p0(X)]`` 精确命中目标。
    """
    if not 0.0 < target_mean < 1.0:
        raise ValueError(f"target_mean 必须在 (0,1) 内，收到 {target_mean}")
    lp = np.asarray(linear_predictor, dtype=float)

    def gap(delta: float) -> float:
        return float(np.mean(expit(lp + delta))) - target_mean

    if gap(lo) > 0 or gap(hi) < 0:
        raise ValueError(
            f"无法在 [{lo}, {hi}] 内校准截距：目标 {target_mean} 超出可达范围 "
            f"[{float(np.mean(expit(lp + lo))):.6f}, {float(np.mean(expit(lp + hi))):.6f}]"
        )
    return float(brentq(gap, lo, hi, xtol=1e-13, rtol=1e-15, maxiter=500))


def face_response(
    face_value: float,
    *,
    scale: float,
    max_face: float,
) -> float:
    """券面额 → 效应缩放因子 ``g(f) ∈ (0, 1]``，归一化使 ``g(max_face) = 1``。

    ``g(f) = (1 − e^{−f/scale}) / (1 − e^{−max_face/scale})``

    业务含义：面额越大效果越强，但**边际递减**。有了这条曲线，
    "发多大面额"才是一个真实的最优化问题，而不是"越小越省"的废话。
    """
    if face_value <= 0 or max_face <= 0 or scale <= 0:
        raise ValueError(f"面额/尺度必须为正：face={face_value}, max_face={max_face}, scale={scale}")
    return float((1.0 - np.exp(-face_value / scale)) / (1.0 - np.exp(-max_face / scale)))


def linear_predictor(covariates: Covariates, coefs: dict[str, float], intercept: float = 0.0) -> np.ndarray:
    """按 ``FEATURE_ORDER`` 对齐系数，计算 ``β₀ + βᵀX``。

    配置里缺省的系数按 0 处理，便于只写非零项。多写未知特征名会抛错——
    这是刻意的：拼错特征名若被静默忽略，等于悄悄改掉了 DGP。
    """
    unknown = set(coefs) - set(FEATURE_ORDER)
    if unknown:
        raise ValueError(
            f"未知特征名 {sorted(unknown)}；可用特征：{list(FEATURE_ORDER)}"
        )
    beta = np.array([float(coefs.get(k, 0.0)) for k in FEATURE_ORDER], dtype=float)
    return intercept + covariates.design_matrix() @ beta


#: 配置段里混在系数中的"业务目标"键，提取系数时必须剔除
_COEF_METADATA: frozenset[str] = frozenset({"target_mean", "target_ate", "h_target", "intercept"})


def coefs_from_section(section: dict[str, Any]) -> dict[str, float]:
    """从配置段中提取纯系数（剔除 ``target_mean`` / ``target_ate`` / ``h_target``）。"""
    return {k: float(v) for k, v in section.items() if k not in _COEF_METADATA}


def enforce_probability_bounds(
    p0: np.ndarray,
    tau: np.ndarray,
    *,
    p0_upper: float = 0.90,
    p1_upper: float = 0.995,
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """把 ``p0`` 与 ``p0+τ`` 限制在合法区间，返回 ``(p0, τ_实际, 诊断)``。

    为什么要截断而不是直接报错
    --------------------------
    极端特征组合（如历史 GMV 在 99.9 分位的重度用户）会让 logit 线性预测器
    给出 0.9 以上的"冷转化概率"——业务上不可能。截断是**有意的建模选择**，
    不是掩盖错误：诊断会写进 ``truth.params`` 并在报告中披露，
    同时 ``E[τ]`` 会略低于目标值，报告里两个数都给。

    这也是方案 §3.3 硬约束 ``p0(X)+τ_Y(X) ≤ 1`` 的落实位置。
    """
    p0_raw = np.asarray(p0, dtype=float)
    tau_raw = np.asarray(tau, dtype=float)
    n_p0_clipped = int(np.sum((p0_raw > p0_upper) | (p0_raw < 0.0)))
    n_tau_truncated = int(np.sum(p0_raw + tau_raw > p1_upper))

    p0_out = np.clip(p0_raw, 1e-6, p0_upper)
    p1_out = np.minimum(p0_out + np.maximum(tau_raw, 0.0), p1_upper)
    tau_out = p1_out - p0_out
    return p0_out, tau_out, {
        "n_p0_clipped": n_p0_clipped,
        "n_tau_truncated": n_tau_truncated,
    }


def _gamma_params(mean: float, sd: float) -> tuple[float, float]:
    """由均值/标准差反解 Gamma 分布的 (shape, scale)。"""
    if mean <= 0 or sd <= 0:
        raise ValueError(f"Gamma 参数必须为正：mean={mean}, sd={sd}")
    shape = (mean / sd) ** 2
    scale = sd**2 / mean
    return float(shape), float(scale)


# --------------------------------------------------------------------------- #
# 用户特征
# --------------------------------------------------------------------------- #
def generate_covariates(cfg: Any, rng: np.random.Generator, n: int) -> Covariates:
    """生成用户特征 X（随机分配时点的快照）。

    注意：这里产生的是**真实特征**。脏数据层（``dgp.dirt``）随后制造
    缺失/异常值，只污染**观测到的表**，不污染真值——这正是"数据脏但真值已知"
    的设计，用来检验清洗与稳健性。
    """
    if n <= 0:
        raise ValueError(f"n 必须为正，收到 {n}")
    b = cfg.section("business")

    # ---- 新老客 ----
    is_new = (rng.random(n) < float(b["new_user_share"])).astype(np.int8)

    # ---- 历史 GMV：分新老客两支（新客历史极短）----
    hg = b["hist_gmv"]
    shape_new, scale_new = _gamma_params(hg["new_mean"], hg["new_sd"])
    shape_ret, scale_ret = _gamma_params(hg["returning_mean"], hg["returning_sd"])
    hist_gmv = np.where(
        is_new == 1,
        rng.gamma(shape_new, scale_new, size=n),
        rng.gamma(shape_ret, scale_ret, size=n),
    )

    # ---- 购物车金额：Gamma，截断在业务下限 ----
    shape_cart, scale_cart = _gamma_params(b["cart_value_mean"], b["cart_value_sd"])
    cart_value = np.clip(
        rng.gamma(shape_cart, scale_cart, size=n), float(b["cart_value_min"]), None
    )

    # ---- 浏览深度：负二项（计数、过度离散）----
    mean_bd = float(b["browse_depth_mean"])
    var_bd = float(b["browse_depth_var"])
    if var_bd <= mean_bd:
        raise ValueError(f"browse_depth_var({var_bd}) 必须大于 mean({mean_bd}) 才能用负二项")
    r_nb = mean_bd**2 / (var_bd - mean_bd)
    p_nb = r_nb / (r_nb + mean_bd)
    browse_depth = rng.negative_binomial(r_nb, p_nb, size=n).astype(float)

    # ---- 渠道 ----
    channels = b["channels"]
    names = list(channels)
    probs = np.array([float(channels[k]) for k in names], dtype=float)
    if not np.isclose(probs.sum(), 1.0):
        raise ValueError(f"渠道概率之和必须为 1，当前 {probs.sum()}")
    channel = rng.choice(names, size=n, p=probs)

    # ---- 标准化 ----
    # z 值截断到 ±3：Gamma 分布的重尾（历史 GMV 可到 8σ 以上）会让 logit
    # 线性预测器给出 >0.9 的冷转化概率，业务上不可能。3σ 截断是特征工程惯例。
    def _z(x: np.ndarray, *, cap: float = 3.0) -> np.ndarray:
        sd = float(np.std(x))
        return np.clip((x - float(np.mean(x))) / (sd if sd > 0 else 1.0), -cap, cap)

    user_id = np.arange(n, dtype=np.int64)
    return Covariates(
        user_id=user_id,
        is_new=is_new,
        hist_gmv=hist_gmv,
        cart_value=cart_value,
        browse_depth=browse_depth,
        channel=channel,
        hist_gmv_z=_z(hist_gmv),
        cart_value_z=_z(cart_value),
        browse_depth_z=_z(browse_depth),
    )


# --------------------------------------------------------------------------- #
# 订单经济特征
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OrderDraws:
    """每用户的订单特征一次抽定，在 T=0 / T=1 之间共享（原则 2）。

    ``repeat_u`` / ``refund_u_2`` / ``order_delay_days_2`` 属于**复购路径**（第二单）：
    只有已下单用户才可能兑现，且第二单不带券。它们被安排在抽样序列的最末尾，
    因此新增复购路径**不扰动**前面任何一条随机流（``pay_amount`` 等逐位不变）。
    """

    pay_amount: np.ndarray
    fulfill_cost: np.ndarray
    refund_u: np.ndarray
    redeemed_u: np.ndarray
    order_delay_days: np.ndarray
    refund_delay_days: np.ndarray
    #: 复购倾向 U（< prob 则产生第二单）；B7
    repeat_u: np.ndarray
    #: 第二单的退款倾向 U
    refund_u_2: np.ndarray
    #: 第二单相对首单的下单延迟（天）
    order_delay_days_2: np.ndarray


def sample_order_draws(cfg: Any, rng: np.random.Generator, n: int) -> OrderDraws:
    """抽样订单经济特征。退款/核销用**均匀随机数**而非伯努利，
    这样同一用户在两种处理下的退款/核销状态由同一个 U 决定（单调耦合）。
    """
    b = cfg.section("business")

    pay_amount = np.clip(
        rng.normal(float(b["aov_mean"]), float(b["aov_sd"]), size=n),
        float(b["aov_min"]),
        None,
    )
    fulfill_cost = np.clip(
        rng.normal(float(b["fulfill_cost_mean"]), float(b["fulfill_cost_sd"]), size=n),
        0.5,
        None,
    )
    refund_u = rng.random(n)
    redeemed_u = rng.random(n)
    # 下单延迟：Gamma(2)，均值 2 天，截断在转化窗口内
    convert_days = float(cfg.require("windows.convert_days"))
    order_delay_days = np.clip(rng.gamma(2.0, 1.0, size=n), 0.05, convert_days - 0.05)
    # 退款延迟：下单后 1~25 天（覆盖利润成熟窗口）
    refund_delay_days = rng.uniform(1.0, 25.0, size=n)

    # ---- 复购路径（第二单）的随机流，一律追加在最后，保证既有抽样逐位不变 ----
    repeat_u = rng.random(n)
    refund_u_2 = rng.random(n)
    profit_days = float(cfg.require("windows.profit_days"))
    order_delay_days_2 = np.clip(
        rng.gamma(6.0, 1.5, size=n), 1.0, max(1.5, profit_days - 5.0)
    )

    return OrderDraws(
        pay_amount=pay_amount,
        fulfill_cost=fulfill_cost,
        refund_u=refund_u,
        redeemed_u=redeemed_u,
        order_delay_days=order_delay_days,
        refund_delay_days=refund_delay_days,
        repeat_u=repeat_u,
        refund_u_2=refund_u_2,
        order_delay_days_2=order_delay_days_2,
    )


def realized_order_net(
    draws: OrderDraws,
    *,
    goods_cost_ratio: float,
    refundable_goods_ratio: float,
    refund_handling_fee_rate: float,
    coupon_cost: np.ndarray,
    converted: np.ndarray,
    refund_rate: np.ndarray | float,
    coupon_returned_on_refund: bool = False,
) -> np.ndarray:
    """逐用户实现净贡献利润 ``Π = 1[converted] × 订单净贡献利润``。

    必须与 ``data.profit.compute_order_components`` **代数等价**——
    由 ``tests/test_dgp.py`` 的一致性测试守住（同一笔订单两边算出同一个数）。
    """
    pay = draws.pay_amount
    goods_cost = pay * goods_cost_ratio
    refunded = draws.refund_u < np.asarray(refund_rate, dtype=float)

    refund_amount = np.where(refunded, pay, 0.0)
    handling_fee = np.where(refunded, pay * refund_handling_fee_rate, 0.0)
    goods_recovered = np.where(refunded, goods_cost * refundable_goods_ratio, 0.0)
    # 方案 §2.3.3 最后一行：券不退回则成本保留；退回则冲减
    coupon_effective = np.where(refunded & bool(coupon_returned_on_refund), 0.0, coupon_cost)

    net = (
        (pay - refund_amount - handling_fee)
        - (goods_cost - goods_recovered)
        - draws.fulfill_cost
        - coupon_effective
    )
    return np.where(np.asarray(converted, dtype=bool), net, 0.0)


# --------------------------------------------------------------------------- #
# 总体构造
# --------------------------------------------------------------------------- #
def build_population_from_curves(
    *,
    cfg: Any,
    level: str,
    index: int,
    covariates: Covariates,
    p0: np.ndarray,
    tau_conversion: np.ndarray,
    face_value: float,
    order_draws: OrderDraws,
    conversion_u: np.ndarray,
    latent: dict[str, np.ndarray] | None = None,
    params: dict[str, Any] | None = None,
) -> Population:
    """由 ``p0(X)`` 与 ``τ(X)`` 采样潜在结果，并算出解析真值。

    参数
    ----
    p0, tau_conversion : 逐用户数组，长度等于 ``len(covariates)``。
    face_value : 处理组券面额（无券情形传 0）。
    order_draws : 共享的订单经济特征（见 ``sample_order_draws``）。
    conversion_u : 逐用户 ``Uniform(0,1)``。**同一条 U 同时驱动 y0 与 y1**，
        从而保证 ``y1 ≥ y0`` 逐个体恒成立（comonotonic coupling，方案 §3.3 L1）。
    latent : 额外存放的未观测变量（如 L3 的 U），只供真值/敏感性分析使用。

    真值构造
    --------
    ``cate_profit = p1 · A1 − p0 · A0``，其中 ``A_t`` 是**已转化订单**的期望
    净贡献利润（解析式）。注意这**不是**个体实测利润差 ``pi1 − pi0``。
    """
    b = cfg.section("business")
    n = len(covariates)
    p0 = np.asarray(p0, dtype=float).reshape(-1)
    tau = np.asarray(tau_conversion, dtype=float).reshape(-1)
    conversion_u = np.asarray(conversion_u, dtype=float).reshape(-1)
    if p0.shape != (n,) or tau.shape != (n,):
        raise ValueError(f"p0/tau 长度必须为 {n}，收到 {p0.shape} / {tau.shape}")
    if conversion_u.shape != (n,):
        raise ValueError(f"conversion_u 长度必须为 {n}，收到 {conversion_u.shape}")

    p1 = p0 + tau
    # ---- 硬约束校验（GOAL.md 验收项 ①）----
    if np.any(p0 < 0.0) or np.any(p0 > 1.0):
        raise ValueError(f"p0 必须落在 [0,1]，实际 [{p0.min():.6f}, {p0.max():.6f}]")
    if np.any(tau < 0.0):
        raise ValueError("tau_conversion 必须非负")
    if np.any(p1 > 1.0 + 1e-12):
        raise ValueError(
            f"p0 + tau 越界，最大 {float(np.max(p1)):.6f} > 1（方案 §3.3 L1 约束）"
        )

    redemption_rate = float(b["redemption_rate"])
    coupon_returned = bool(b["coupon_returned_on_refund"])
    refund_rate_control = float(b["refund_rate"])
    refund_rate_treated = refund_rate_control * float(b["refund_rate_treated_multiplier"])

    common = {
        "pay_mean": float(b["aov_mean"]),
        "goods_cost_ratio": float(b["goods_cost_ratio"]),
        "fulfill_mean": float(b["fulfill_cost_mean"]),
        "refundable_goods_ratio": float(b["refundable_goods_ratio"]),
        "refund_handling_fee_rate": float(b["refund_handling_fee_rate"]),
    }
    coupon_expect = face_value * redemption_rate
    net_ctrl_order = expected_order_net_profit(
        coupon_cost_expectation=0.0, refund_rate=refund_rate_control, **common
    )
    net_trt_order = expected_order_net_profit(
        coupon_cost_expectation=coupon_expect,
        coupon_cost_expectation_on_refund=0.0 if coupon_returned else coupon_expect,
        refund_rate=refund_rate_treated,
        **common,
    )

    # ---- 复购路径（第二单）：B7 ----
    # 业务设定：只有已下单用户才可能复购；第二单不带券（首单券一次性）；
    # 第二单客单价 = 首单 × value_ratio，履约成本按同一用户复用。
    rep = cfg.get("dgp.repeat", {}) or {}
    repeat_enabled = bool(rep.get("enabled", False))
    repeat_prob = float(rep.get("prob", 0.0)) if repeat_enabled else 0.0
    repeat_ratio = float(rep.get("value_ratio", 0.55))
    repeat = (order_draws.repeat_u < repeat_prob) if repeat_prob > 0 else np.zeros(n, dtype=bool)

    net_second_ctrl = expected_order_net_profit(
        coupon_cost_expectation=0.0,
        refund_rate=refund_rate_control,
        **{**common, "pay_mean": common["pay_mean"] * repeat_ratio},
    )
    net_second_trt = expected_order_net_profit(
        coupon_cost_expectation=0.0,
        refund_rate=refund_rate_treated,
        **{**common, "pay_mean": common["pay_mean"] * repeat_ratio},
    )

    # 同一条 U 驱动两个潜在结果 → y1 >= y0 恒成立
    y0 = (conversion_u < p0).astype(np.int8)
    y1 = (conversion_u < p1).astype(np.int8)

    redeemed = order_draws.redeemed_u < redemption_rate
    coupon_cost_treated = np.where(redeemed, face_value, 0.0)

    draws_second = OrderDraws(
        pay_amount=order_draws.pay_amount * repeat_ratio,
        fulfill_cost=order_draws.fulfill_cost,
        refund_u=order_draws.refund_u_2,
        redeemed_u=np.ones(n),
        order_delay_days=order_draws.order_delay_days_2,
        refund_delay_days=order_draws.refund_delay_days,
        repeat_u=order_draws.repeat_u,
        refund_u_2=order_draws.refund_u_2,
        order_delay_days_2=order_draws.order_delay_days_2,
    )

    pi0 = realized_order_net(
        order_draws,
        goods_cost_ratio=common["goods_cost_ratio"],
        refundable_goods_ratio=common["refundable_goods_ratio"],
        refund_handling_fee_rate=common["refund_handling_fee_rate"],
        coupon_cost=np.zeros(n),
        converted=y0,
        refund_rate=refund_rate_control,
        coupon_returned_on_refund=coupon_returned,
    )
    pi1 = realized_order_net(
        order_draws,
        goods_cost_ratio=common["goods_cost_ratio"],
        refundable_goods_ratio=common["refundable_goods_ratio"],
        refund_handling_fee_rate=common["refund_handling_fee_rate"],
        coupon_cost=coupon_cost_treated,
        converted=y1,
        refund_rate=refund_rate_treated,
        coupon_returned_on_refund=coupon_returned,
    )
    if repeat_prob > 0:
        # 逐用户利润 = 首单 + 第二单（这才是"多单用户利润等于各单之和"的实现）
        pi0 = pi0 + realized_order_net(
            draws_second,
            goods_cost_ratio=common["goods_cost_ratio"],
            refundable_goods_ratio=common["refundable_goods_ratio"],
            refund_handling_fee_rate=common["refund_handling_fee_rate"],
            coupon_cost=np.zeros(n),
            converted=(y0 == 1) & repeat,
            refund_rate=refund_rate_control,
            coupon_returned_on_refund=coupon_returned,
        )
        pi1 = pi1 + realized_order_net(
            draws_second,
            goods_cost_ratio=common["goods_cost_ratio"],
            refundable_goods_ratio=common["refundable_goods_ratio"],
            refund_handling_fee_rate=common["refund_handling_fee_rate"],
            coupon_cost=np.zeros(n),
            converted=(y1 == 1) & repeat,
            refund_rate=refund_rate_treated,
            coupon_returned_on_refund=coupon_returned,
        )

    # 已转化用户的**期望净贡献**（含复购路径的期望）：A_t = 首单 + prob × 第二单。
    # 真值恒等式 cate_profit = p1·A1 − p0·A0 因此仍然精确成立。
    net_conv_ctrl = net_ctrl_order + repeat_prob * net_second_ctrl
    net_conv_trt = net_trt_order + repeat_prob * net_second_trt

    truth = GroundTruth(
        level=level,
        face_value=float(face_value),
        p0=p0,
        p1=p1,
        tau_conversion=tau,
        # 解析 CATE：E[Π(1)|X] − E[Π(0)|X] = p1·A1 − p0·A0
        cate_profit=p1 * net_conv_trt - p0 * net_conv_ctrl,
        net_per_order_treated=np.full(n, net_trt_order),
        net_per_order_control=np.full(n, net_ctrl_order),
        net_per_converted_treated=np.full(n, net_conv_trt),
        net_per_converted_control=np.full(n, net_conv_ctrl),
        params=dict(params or {}),
    )

    return Population(
        level=level,
        index=int(index),
        covariates=covariates,
        truth=truth,
        potential=PotentialOutcomes(y0=y0, y1=y1, pi0=pi0, pi1=pi1),
        latent={
            "conversion_u": np.asarray(conversion_u),
            "redeemed": redeemed,
            "treated_refund_rate": np.full(n, refund_rate_treated),
            "control_refund_rate": np.full(n, refund_rate_control),
            # 订单经济特征一并存档，供关系表构造与分析框架复用同一批抽样
            "pay_amount": order_draws.pay_amount,
            "fulfill_cost": order_draws.fulfill_cost,
            "refund_u": order_draws.refund_u,
            "redeemed_u": order_draws.redeemed_u,
            "order_delay_days": order_draws.order_delay_days,
            "refund_delay_days": order_draws.refund_delay_days,
            # 复购路径：谁是第二单用户、第二单的金额与时间
            "repeat": repeat,
            "repeat_prob": np.full(n, repeat_prob),
            "pay_amount_2": order_draws.pay_amount * repeat_ratio,
            "refund_u_2": order_draws.refund_u_2,
            "order_delay_days_2": order_draws.order_delay_days_2,
            **(latent or {}),
        },
    )
