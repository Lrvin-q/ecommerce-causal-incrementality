"""分层 DGP：L0 → L3，每层只放松一个假设（方案 §3.3）。

| 层级 | 现实多了什么麻烦 | 违反哪条假设 | 上层方法为何失效 |
|---|---|---|---|
| L0 | 无，教科书世界 | 无 | —（作用是校准评估流程） |
| L1 | 不同人效果不同 | 无 | 平均效应掩盖分层价值 |
| L2 | 样本有限、效应随时间漂移、护栏指标 | 无（设计约束） | 无限样本不现实 |
| L3 | 运营挑人，有看不见的因素 | **可忽略性** | 朴素/PSM 只能平衡可观测 X |

L4（时间趋势 / DID）**有条件才做**，见 ``l4_did.py`` 与 GOAL.md 第五部分。
L5/L6 不纳入，只做讨论。

随机流的命名刻意**不含 λ / 面额**：这样 λ 扫描与面额扫描在同一批用户、
同一组随机数上进行比较，差异只来自被扫描的那个参数，而不是换了批数据。
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.special import expit

from causal_growth.config import Config
from causal_growth.contracts import Population
from causal_growth.dgp.base import (
    build_population_from_curves,
    calibrate_intercept,
    coefs_from_section,
    enforce_probability_bounds,
    face_response,
    generate_covariates,
    linear_predictor,
    sample_order_draws,
)
from causal_growth.rng import child_rng

__all__ = ["build_l0", "build_l1", "build_l2", "build_l3", "reference_face"]


def reference_face(cfg: Config) -> float:
    return float(cfg.require("business.coupon_reference_face"))


def _face_gain(cfg: Config, face_value: float) -> float:
    """``g(f) / g(f_ref)``，用于把参考面额下的 target_ate 折算到当前面额。"""
    scale = float(cfg.require("business.coupon_response_scale"))
    faces = list(cfg.require("business.coupon_face_values"))
    max_face = float(max(faces))
    g_ref = face_response(reference_face(cfg), scale=scale, max_face=max_face)
    g_now = face_response(face_value, scale=scale, max_face=max_face)
    return g_now / g_ref


def _common_inputs(cfg: Config, level: str, index: int, n: int) -> tuple[Any, Any, Any]:
    """统一构造 (covariates, order_draws, conversion_u)，各自独立随机流。"""
    seed = int(cfg.require("project.master_seed"))
    covariates = generate_covariates(cfg, child_rng(seed, f"dgp.{level}.cov", index), n)
    order_draws = sample_order_draws(cfg, child_rng(seed, f"dgp.{level}.orders", index), n)
    conversion_u = child_rng(seed, f"dgp.{level}.conversion", index).random(n)
    return covariates, order_draws, conversion_u


def _heterogeneity_shape(
    cfg: Config, covariates: Any, section: dict[str, float], h_target: float
) -> np.ndarray:
    """``h(X) = σ(γᵀX + γ₀)``，γ₀ 校准使 ``E[h] = h_target``。"""
    lp = linear_predictor(covariates, coefs_from_section(section), intercept=0.0)
    delta = calibrate_intercept(lp, h_target)
    return expit(lp + delta)


def _p0_curve(
    cfg: Config, covariates: Any, section: dict[str, float], target_mean: float
) -> np.ndarray:
    """``p0(X) = σ(βᵀX + β₀)``，β₀ 校准使 ``E[p0] = target_mean``。"""
    lp = linear_predictor(covariates, coefs_from_section(section), intercept=0.0)
    delta = calibrate_intercept(lp, target_mean)
    return expit(lp + delta)


# --------------------------------------------------------------------------- #
# L0：理想基线
# --------------------------------------------------------------------------- #
def build_l0(cfg: Config, index: int = 0, *, face_value: float | None = None) -> Population:
    """L0 理想基线：``T ⟂ X``，常数效应。

    作用不是"讲故事"，而是**校准评估流程**：如果连这里都有偏，
    后面所有层级的结果都不可信（方案 §3.3 L0）。
    """
    l0 = cfg.require("dgp.l0")
    n = int(cfg.require("dgp.n_users"))
    face = reference_face(cfg) if face_value is None else float(face_value)

    covariates, order_draws, conversion_u = _common_inputs(cfg, "l0", index, n)
    p0 = np.full(n, float(l0["target_conversion"]))
    tau = np.full(n, float(l0["target_ate_conversion"]))

    return build_population_from_curves(
        cfg=cfg,
        level="L0",
        index=index,
        covariates=covariates,
        p0=p0,
        tau_conversion=tau,
        face_value=face,
        order_draws=order_draws,
        conversion_u=conversion_u,
        params={"target_conversion": float(l0["target_conversion"]),
                "target_ate_conversion": float(l0["target_ate_conversion"]),
                "face_value": face},
    )


# --------------------------------------------------------------------------- #
# L1：异质性
# --------------------------------------------------------------------------- #
def build_l1(cfg: Config, index: int = 0, *, face_value: float | None = None) -> Population:
    """L1 异质性：``p0(X)=σ(βᵀX+β₀)``，``τ_Y(X)=scale(f)·σ(γᵀX+γ₀)``。

    上层为何失效：平均效应掩盖分层价值。新客 CATE 远高于老客时，
    随机发券会让预算大量流向"本来就会买"的人（利润侵蚀）。
    """
    l1 = cfg.section("dgp.l1")
    n = int(cfg.require("dgp.n_users"))
    face = reference_face(cfg) if face_value is None else float(face_value)

    covariates, order_draws, conversion_u = _common_inputs(cfg, "l1", index, n)

    p0 = _p0_curve(cfg, covariates, l1["p0"], float(l1["p0"]["target_mean"]))
    h_target = float(l1["tau"]["h_target"])
    h = _heterogeneity_shape(cfg, covariates, l1["tau"], h_target)

    # scale 的推导：E[τ] = scale · E[h] = scale · h_target = target_ate · g(f)/g(f_ref)
    scale = float(l1["tau"]["target_ate"]) * _face_gain(cfg, face) / h_target
    p0, tau, bounds = enforce_probability_bounds(p0, scale * h)

    return build_population_from_curves(
        cfg=cfg,
        level="L1",
        index=index,
        covariates=covariates,
        p0=p0,
        tau_conversion=tau,
        face_value=face,
        order_draws=order_draws,
        conversion_u=conversion_u,
        params={
            "face_value": face,
            "target_ate": float(l1["tau"]["target_ate"]),
            "ate_conversion_achieved": float(np.mean(tau)),
            "h_target": h_target,
            "tau_scale": scale,
            "p0_target_mean": float(l1["p0"]["target_mean"]),
            "p0_mean_achieved": float(np.mean(p0)),
            "probability_bounds": bounds,
        },
    )


# --------------------------------------------------------------------------- #
# L2：实验约束（有限样本 / 不等分流 / 效应漂移 / 护栏）
# --------------------------------------------------------------------------- #
def build_l2(cfg: Config, index: int = 0, *, face_value: float | None = None) -> Population:
    """L2 实验约束：样本有限、处理比例 ≠ 0.5、效应逐周衰减、护栏指标真实小幅恶化。

    真值 = 各周效应的样本加权平均（方案 §3.3 L2）。
    """
    l2 = cfg.section("dgp.l2")
    base_l1 = cfg.section("dgp.l1")
    n = int(l2["n_users"])
    face = reference_face(cfg) if face_value is None else float(face_value)

    covariates, order_draws, conversion_u = _common_inputs(cfg, "l2", index, n)

    p0 = _p0_curve(cfg, covariates, base_l1["p0"], float(l2["p0_target_mean"]))
    h_target = float(l2["h_target"])
    h = _heterogeneity_shape(cfg, covariates, base_l1["tau"], h_target)

    weekly_effect = np.asarray(l2["weekly_effect"], dtype=float)
    weekly_share = np.asarray(l2["weekly_share"], dtype=float)
    if len(weekly_effect) != len(weekly_share):
        raise ValueError("l2.weekly_effect 与 l2.weekly_share 长度必须一致")
    if not np.isclose(weekly_share.sum(), 1.0):
        raise ValueError(f"l2.weekly_share 之和必须为 1，当前 {weekly_share.sum()}")

    week_rng = child_rng(int(cfg.require("project.master_seed")), "dgp.l2.week", index)
    week = week_rng.choice(len(weekly_effect), size=n, p=weekly_share)
    # 每周的 scale 使 E[τ | week] 精确等于该周目标效应
    scale_by_week = weekly_effect / h_target
    p0, tau, bounds = enforce_probability_bounds(p0, scale_by_week[week] * h)

    pop = build_population_from_curves(
        cfg=cfg,
        level="L2",
        index=index,
        covariates=covariates,
        p0=p0,
        tau_conversion=tau,
        face_value=face,
        order_draws=order_draws,
        conversion_u=conversion_u,
        latent={"week": week.astype(np.int8)},
        params={
            "face_value": face,
            "weekly_effect": weekly_effect.tolist(),
            "weekly_share": weekly_share.tolist(),
            "ate_conversion_target": float(np.sum(weekly_effect * weekly_share)),
            "ate_conversion_achieved": float(np.mean(tau)),
            "treatment_share": float(l2["treatment_share"]),
            "probability_bounds": bounds,
        },
    )
    return pop


# --------------------------------------------------------------------------- #
# L3：选择偏差（未观测混淆）
# --------------------------------------------------------------------------- #
def build_l3(
    cfg: Config,
    index: int = 0,
    *,
    lam: float = 0.0,
    face_value: float | None = None,
) -> Population:
    """L3 选择偏差：``T ~ Bernoulli(σ(αᵀX + α₀ + λU))``，``p0(X,U)=σ(βᵀX+β₀+λU)``。

    ``U`` 是未观测混淆（如线下客服私下推荐），同时影响发券与购买。
    ``λ`` 是混淆强度旋钮：0（无混淆）/ 0.5 / 1.0，Round 2 用更细网格定位失效阈值。

    真值仍可算，因为模拟器知道 ``U``（方案 §3.3 L3）。**估计器不得读取 U**。
    """
    l3 = cfg.section("dgp.l3")
    base_l1 = cfg.section("dgp.l1")
    # λ 扫描是"7 个 λ × 20 次重复 × 4 种方法"，用 20 万样本会跑几小时，
    # 因此 L3 允许独立设定样本量（默认 4 万）。
    n = int(l3.get("n_users", cfg.require("dgp.n_users")))
    face = reference_face(cfg) if face_value is None else float(face_value)

    covariates, order_draws, conversion_u = _common_inputs(cfg, "l3", index, n)

    # 未观测混淆 U：Logistic(0,1) 标准化到 mean 0 / sd 1，并截断到 ±2
    # （截断的理由：无界 U 会把极端用户的 p0 推到 0.99，让 p0+τ 越界；
    #   业务上"客服私下推荐"这种混淆因素的强度本来就有上限）
    u_raw = child_rng(int(cfg.require("project.master_seed")), "dgp.l3.u", index).logistic(size=n)
    u = np.clip(
        (u_raw - float(np.mean(u_raw))) / float(np.std(u_raw)), -2.0, 2.0
    )

    p0_lp = linear_predictor(covariates, coefs_from_section(base_l1["p0"]), intercept=0.0)
    beta0 = calibrate_intercept(p0_lp, float(l3["p0_target_mean"]))
    p0 = expit(p0_lp + beta0 + float(lam) * u)

    h_target = float(l3["h_target"])
    h = _heterogeneity_shape(cfg, covariates, base_l1["tau"], h_target)
    scale = float(l3["tau_target_ate"]) * _face_gain(cfg, face) / h_target
    p0, tau, bounds = enforce_probability_bounds(p0, scale * h)

    pop = build_population_from_curves(
        cfg=cfg,
        level=f"L3(λ={lam:g})",
        index=index,
        covariates=covariates,
        p0=p0,
        tau_conversion=tau,
        face_value=face,
        order_draws=order_draws,
        conversion_u=conversion_u,
        latent={"u": u, "lambda": np.full(n, float(lam))},
        params={
            "lambda": float(lam),
            "face_value": face,
            "tau_target_ate": float(l3["tau_target_ate"]),
            "ate_conversion_achieved": float(np.mean(tau)),
            "h_target": h_target,
            "p0_target_mean": float(l3["p0_target_mean"]),
            "p0_mean_achieved": float(np.mean(p0)),
            "probability_bounds": bounds,
        },
    )
    return pop
