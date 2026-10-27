"""F01 观测闭环：交叉拟合 IPW / SNIPS / DR 的策略价值、配对差与可靠性门禁。

回答哪个问题
------------
策略在**只有观测数据**时值多少：每个用户只留下 ``(T, Y, C, R)``，反事实不可见。
本模块把 D03 的冻结策略（逐用户 0/1 名单）放到观测表上评估，给出：

1. ``ipw_increment``：Horvitz–Thompson 逆概率加权；
2. ``snips_increment``：处理/对照两臂**分别归一化**的自归一化 IPW；
3. ``dr_increment``：交叉拟合 AIPW（双稳健）；
4. 策略两两**配对差**：同一批用户上计算，SE 用影响函数之差，自动含协方差；
5. 成本与护栏（30 天退款率）的 DR 估计；
6. ESS / 支持违规的可靠性门禁（阈值全部来自 ``configs/v3/evaluation.yaml``）。

识别与隔离
----------
- 随机化层用观测表记录的 ``design_probability``（``propensity_source="known_design"``，
  不截断）；观察性层用观测特征估计 e 并按配置截断，同时保留 raw/截断计数。
- 观测表不得含任何真值列（``tau_true``/``cost_true``/``audit_*``…）；本模块入口直接拒收。
- 策略名单必须在**同一行序、同一 user_id** 上给出；入口校验唯一性与对齐。

公式（元/人；Y 为含券成本的净贡献利润）
--------------------------------------
``V(π) = E[π·Y(1) + (1−π)·Y(0)]``

- IPW：``V̂ = 1/n Σ [π T Y/e + (1−π)(1−T)Y/(1−e)]``；
- SNIPS（两臂分别归一化，再按选择份额还原）：
  ``V̂ = p̄·Σ(πTY/e)/Σ(πT/e) + q̄·Σ((1−π)(1−T)Y/(1−e))/Σ((1−π)(1−T)/(1−e))``，
  其中 ``p̄ = mean(π)``、``q̄ = 1−p̄``；
- DR：``ψ = π[m1 + T(Y−m1)/e] + (1−π)[m0 + (1−T)(Y−m0)/(1−e)]``，``V̂ = mean(ψ)``。

SE 一律用影响函数 ``sd(IF)/√n``；配对差用 ``sd(IF_A−IF_B)/√n``。这是大样本一阶近似，
不校正 nuisance 的二阶项（与 D03 的 crossfit DR 口径一致）。
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from causal_growth.config import Config
from causal_growth.estimate.v3_models import (
    crossfit_nuisance,
    crossfit_two_arm_outcome,
)

ESTIMATORS: tuple[str, ...] = ("ipw_increment", "dr_increment", "snips_increment")
REQUIRED_COLUMNS: tuple[str, ...] = (
    "user_id", "treatment", "net_profit", "coupon_cost", "any_refund_30d",
)
FORBIDDEN_COLUMN_PATTERNS: tuple[str, ...] = (
    "audit_", "truth_", "potential_",
)
FORBIDDEN_COLUMN_NAMES: tuple[str, ...] = (
    "tau_true", "cost_true", "u_true",
)

VALUE_COLUMNS: tuple[str, ...] = (
    "policy", "estimator", "value_cny_per_user", "se_cny_per_user",
    "ci_low_cny_per_user", "ci_high_cny_per_user", "n",
    "ess_treated", "ess_control", "ess_fraction_treated", "ess_fraction_control",
    "support_violation_fraction", "reliability_passed", "reliability_label",
)
DIFF_COLUMNS: tuple[str, ...] = (
    "policy", "baseline", "estimator", "diff_cny_per_user", "se_diff",
    "ci_low", "ci_high", "one_sided_p_value", "n",
)
COMPONENT_COLUMNS: tuple[str, ...] = (
    "policy", "component", "unit", "value", "se",
    "ci_low", "ci_high", "n",
)


@dataclass(frozen=True)
class OpeNuisances:
    """与主结局共用折划分的 OPE nuisance。"""

    mu1: np.ndarray
    mu0: np.ndarray
    propensity: np.ndarray
    fold_id: np.ndarray
    cost_mu1: np.ndarray
    refund_mu1: np.ndarray
    refund_mu0: np.ndarray
    propensity_source: str
    propensity_raw_min: float
    propensity_raw_max: float
    propensity_clipped_count: int
    propensity_clip_low: float
    propensity_clip_high: float

    @property
    def n(self) -> int:
        return int(self.mu1.shape[0])

    def diagnostics(self) -> dict[str, object]:
        return {
            "propensity_source": self.propensity_source,
            "propensity_min": float(self.propensity.min()),
            "propensity_max": float(self.propensity.max()),
            "propensity_raw_min": self.propensity_raw_min,
            "propensity_raw_max": self.propensity_raw_max,
            "propensity_clipped_count": self.propensity_clipped_count,
            "propensity_clip_low": self.propensity_clip_low,
            "propensity_clip_high": self.propensity_clip_high,
            "folds": int(self.fold_id.max()) + 1,
        }


def require_observed_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """校验观测表可用且不含真值列；返回按 ``user_id`` 稳定排序的副本。"""
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"观测表缺少列：{missing}")
    forbidden = [
        column for column in frame.columns
        if str(column).endswith("_true")
        or str(column) in FORBIDDEN_COLUMN_NAMES
        or any(str(column).startswith(pattern) for pattern in FORBIDDEN_COLUMN_PATTERNS)
    ]
    if forbidden:
        raise ValueError(f"观测表混入真值/审计列，禁止进入 OPE：{forbidden}")
    if frame["user_id"].duplicated().any():
        raise ValueError("观测表的 user_id 不唯一，策略名单无法对齐")
    ordered = frame.sort_values("user_id", kind="stable").reset_index(drop=True)
    treatment = ordered["treatment"].to_numpy()
    if not np.isin(treatment, [0, 1]).all():
        raise ValueError("treatment 必须是 0/1")
    for column in ("net_profit", "coupon_cost", "any_refund_30d"):
        values = ordered[column].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"{column} 含非有限值")
    if (ordered["coupon_cost"].to_numpy(dtype=float) < 0).any():
        raise ValueError("coupon_cost 不能为负")
    if not np.isin(ordered["any_refund_30d"].to_numpy(), [0, 1]).all():
        raise ValueError("any_refund_30d 必须是 0/1")
    return ordered


def require_policy(
    policy: Any, n: int, *, name: str = "policy"
) -> np.ndarray:
    """校验策略名单是长度 n 的 0/1 向量。"""
    values = np.asarray(policy)
    if values.shape != (n,):
        raise ValueError(f"{name} 长度应为 {n}，收到 {values.shape}")
    if not np.isin(values, [0, 1, True, False]).all():
        raise ValueError(f"{name} 必须是 0/1")
    return values.astype(float)


def fit_ope_nuisances(
    frame: pd.DataFrame,
    features: Any,
    cfg: Config,
    *,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
    seed_index: int = 0,
) -> OpeNuisances:
    """交叉拟合主结局、成本与退款模型；成本/退款复用主结局的折号。"""
    X = np.asarray(features, dtype=float)
    if X.ndim != 2 or X.shape[0] != len(frame):
        raise ValueError("features 必须是 (n, p) 矩阵")
    y = frame["net_profit"].to_numpy(dtype=float)
    t = frame["treatment"].to_numpy(dtype=int)
    cost = frame["coupon_cost"].to_numpy(dtype=float)
    refund = frame["any_refund_30d"].to_numpy(dtype=float)
    nuisance = crossfit_nuisance(
        X, y, t, cfg,
        seed_index=seed_index,
        propensity_source=propensity_source,
        design_probability=design_probability,
    )
    if nuisance.fold_id is None:
        raise RuntimeError("crossfit_nuisance 未返回折号，无法复用折划分")
    cost_mu1, _ = crossfit_two_arm_outcome(
        X, cost, t, cfg,
        fold_id=nuisance.fold_id,
        seed_index=seed_index,
        seed_prefix="ope.cost",
    )
    refund_mu1, refund_mu0 = crossfit_two_arm_outcome(
        X, refund, t, cfg,
        fold_id=nuisance.fold_id,
        seed_index=seed_index,
        seed_prefix="ope.refund",
        classifier=True,
    )
    return OpeNuisances(
        mu1=nuisance.mu1,
        mu0=nuisance.mu0,
        propensity=nuisance.propensity,
        fold_id=nuisance.fold_id,
        cost_mu1=cost_mu1,
        refund_mu1=refund_mu1,
        refund_mu0=refund_mu0,
        propensity_source=nuisance.propensity_source,
        propensity_raw_min=nuisance.propensity_raw_min,
        propensity_raw_max=nuisance.propensity_raw_max,
        propensity_clipped_count=nuisance.propensity_clipped_count,
        propensity_clip_low=nuisance.propensity_clip_low,
        propensity_clip_high=nuisance.propensity_clip_high,
    )


def _ipw_contributions(
    pi: np.ndarray, y: np.ndarray, t: np.ndarray, e: np.ndarray
) -> np.ndarray:
    return pi * t * y / e + (1.0 - pi) * (1.0 - t) * y / (1.0 - e)


def policy_value_ipw(
    pi: Any, y: Any, t: Any, propensity: Any
) -> tuple[float, np.ndarray]:
    """HT 逆概率加权；返回 (值, 影响函数)。"""
    pi = require_policy(pi, len(y))
    y = np.asarray(y, dtype=float)
    t = np.asarray(t, dtype=float)
    e = np.asarray(propensity, dtype=float)
    if not (pi.shape == y.shape == t.shape == e.shape):
        raise ValueError("pi/y/t/propensity 长度不一致")
    if not np.isfinite(e).all() or np.any(e <= 0.0) or np.any(e >= 1.0):
        raise ValueError("倾向得分必须严格落在 (0,1)")
    contrib = _ipw_contributions(pi, y, t, e)
    value = float(contrib.mean())
    return value, contrib - value


def policy_value_snips(
    pi: Any, y: Any, t: Any, propensity: Any
) -> tuple[float, np.ndarray]:
    """两臂分别归一化的 SNIPS；影响函数含份额估计项。"""
    pi = require_policy(pi, len(y))
    y = np.asarray(y, dtype=float)
    t = np.asarray(t, dtype=float)
    e = np.asarray(propensity, dtype=float)
    if not (pi.shape == y.shape == t.shape == e.shape):
        raise ValueError("pi/y/t/propensity 长度不一致")
    if not np.isfinite(e).all() or np.any(e <= 0.0) or np.any(e >= 1.0):
        raise ValueError("倾向得分必须严格落在 (0,1)")
    p_bar = float(pi.mean())
    q_bar = 1.0 - p_bar
    w1 = pi * t / e
    w0 = (1.0 - pi) * (1.0 - t) / (1.0 - e)
    z1 = w1 * y
    z0 = w0 * y
    value = 0.0
    influence = np.zeros_like(pi)
    if p_bar > 0.0:
        s1 = float(w1.sum())
        if s1 <= 0.0:
            raise ValueError("SNIPS 处理臂没有有效权重")
        r1 = float(z1.sum()) / s1
        value += p_bar * r1
        influence += r1 * (pi - p_bar) + (z1 - r1 * w1)
    if q_bar > 0.0:
        s0 = float(w0.sum())
        if s0 <= 0.0:
            raise ValueError("SNIPS 对照臂没有有效权重")
        r0 = float(z0.sum()) / s0
        value += q_bar * r0
        influence += r0 * ((1.0 - pi) - q_bar) + (z0 - r0 * w0)
    return float(value), influence


def policy_value_dr(
    pi: Any, y: Any, t: Any, mu1: Any, mu0: Any, propensity: Any
) -> tuple[float, np.ndarray]:
    """交叉拟合 AIPW 策略价值；返回 (值, 影响函数)。"""
    pi = require_policy(pi, len(y))
    y = np.asarray(y, dtype=float)
    t = np.asarray(t, dtype=float)
    e = np.asarray(propensity, dtype=float)
    mu1 = np.asarray(mu1, dtype=float)
    mu0 = np.asarray(mu0, dtype=float)
    if not (pi.shape == y.shape == t.shape == e.shape == mu1.shape == mu0.shape):
        raise ValueError("pi/y/t/mu1/mu0/propensity 长度不一致")
    if not np.isfinite(e).all() or np.any(e <= 0.0) or np.any(e >= 1.0):
        raise ValueError("倾向得分必须严格落在 (0,1)")
    g1 = mu1 + t * (y - mu1) / e
    g0 = mu0 + (1.0 - t) * (y - mu0) / (1.0 - e)
    psi = pi * g1 + (1.0 - pi) * g0
    value = float(psi.mean())
    return value, psi - value


def policy_cost_dr(
    pi: Any, cost: Any, t: Any, cost_mu1: Any, propensity: Any
) -> tuple[float, np.ndarray]:
    """选中策略的券成本（元/分配用户）：对照臂成本恒为 0。"""
    pi = require_policy(pi, len(cost))
    cost = np.asarray(cost, dtype=float)
    t = np.asarray(t, dtype=float)
    e = np.asarray(propensity, dtype=float)
    mu1 = np.asarray(cost_mu1, dtype=float)
    if not (pi.shape == cost.shape == t.shape == e.shape == mu1.shape):
        raise ValueError("pi/cost/t/cost_mu1/propensity 长度不一致")
    if not np.isfinite(e).all() or np.any(e <= 0.0) or np.any(e >= 1.0):
        raise ValueError("倾向得分必须严格落在 (0,1)")
    psi = pi * (mu1 + t * (cost - mu1) / e)
    value = float(psi.mean())
    return value, psi - value


def policy_guardrail_dr(
    pi: Any, refund: Any, t: Any, mu1: Any, mu0: Any, propensity: Any
) -> tuple[float, np.ndarray]:
    """选中策略的 30 天退款率（用户级），用与主结局相同的 DR 结构。"""
    return policy_value_dr(pi, refund, t, mu1, mu0, propensity)


def _se_from_influence(influence: np.ndarray) -> float:
    values = np.asarray(influence, dtype=float)
    if values.size < 2:
        return float("nan")
    return float(values.std(ddof=1) / np.sqrt(values.size))


def _normal_interval(
    value: float, se: float, confidence: float
) -> tuple[float, float]:
    if not np.isfinite(se) or se <= 0.0:
        return float("nan"), float("nan")
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    return value - z * se, value + z * se


def _ess(weights: np.ndarray) -> float:
    weights = np.asarray(weights, dtype=float)
    total = float(weights.sum())
    squared = float(np.square(weights).sum())
    if squared <= 0.0:
        return 0.0
    return total * total / squared


def reliability_gate(
    pi: np.ndarray,
    treatment: np.ndarray,
    propensity: np.ndarray,
    cfg: Config,
) -> dict[str, object]:
    """按冻结配置判定该策略的 OPE 是否可靠（ESS / 支持违规）。"""
    gate = cfg.section("evaluation.reliability_gate")
    minimum_ess = float(gate["minimum_ess_per_action"])
    minimum_fraction = float(gate["minimum_ess_fraction_per_action"])
    max_violation = float(gate["maximum_observed_support_violation_fraction"])
    bounds = [float(value) for value in gate["probability_support_bounds"]]
    fail_label = str(gate["fail_label"])

    t = np.asarray(treatment, dtype=float)
    e = np.asarray(propensity, dtype=float)
    w1 = pi / e
    w0 = (1.0 - pi) / (1.0 - e)
    ess_t = _ess(w1)
    ess_c = _ess(w0)
    n_treated = int((t == 1).sum())
    n_control = int((t == 0).sum())
    ess_t_frac = ess_t / max(1, n_treated)
    ess_c_frac = ess_c / max(1, n_control)
    violation = float(((e < bounds[0]) | (e > bounds[1])).mean())

    uses_treated = float(pi.sum()) > 0.0
    uses_control = float((1.0 - pi).sum()) > 0.0
    reasons: list[str] = []
    if uses_treated and (ess_t < minimum_ess or ess_t_frac < minimum_fraction):
        reasons.append(f"处理臂 ESS {ess_t:.1f}（占比 {ess_t_frac:.3f}）低于门禁")
    if uses_control and (ess_c < minimum_ess or ess_c_frac < minimum_fraction):
        reasons.append(f"对照臂 ESS {ess_c:.1f}（占比 {ess_c_frac:.3f}）低于门禁")
    if violation > max_violation:
        reasons.append(f"支持违规比例 {violation:.4f} 超过 {max_violation}")
    return {
        "passed": not reasons,
        "label": None if not reasons else fail_label,
        "reasons": reasons,
        "ess_treated": ess_t,
        "ess_control": ess_c,
        "ess_fraction_treated": ess_t_frac,
        "ess_fraction_control": ess_c_frac,
        "support_violation_fraction": violation,
        "n_treated": int((t == 1).sum()),
        "n_control": int((t == 0).sum()),
    }


def _values_for_policy(
    policy_name: str,
    pi: np.ndarray,
    frame: pd.DataFrame,
    nuisance: OpeNuisances,
    cfg: Config,
    confidence: float,
) -> tuple[list[dict[str, object]], dict[str, tuple[float, np.ndarray]]]:
    y = frame["net_profit"].to_numpy(dtype=float)
    t = frame["treatment"].to_numpy(dtype=float)
    e = nuisance.propensity
    gate = reliability_gate(pi, t, e, cfg)
    estimates: dict[str, tuple[float, np.ndarray]] = {
        "ipw_increment": policy_value_ipw(pi, y, t, e),
        "dr_increment": policy_value_dr(pi, y, t, nuisance.mu1, nuisance.mu0, e),
        "snips_increment": policy_value_snips(pi, y, t, e),
    }
    rows: list[dict[str, object]] = []
    for estimator in ESTIMATORS:
        value, influence = estimates[estimator]
        se = _se_from_influence(influence)
        low, high = _normal_interval(value, se, confidence)
        rows.append({
            "policy": policy_name,
            "estimator": estimator,
            "value_cny_per_user": value,
            "se_cny_per_user": se,
            "ci_low_cny_per_user": low,
            "ci_high_cny_per_user": high,
            "n": len(pi),
            "ess_treated": gate["ess_treated"],
            "ess_control": gate["ess_control"],
            "ess_fraction_treated": gate["ess_fraction_treated"],
            "ess_fraction_control": gate["ess_fraction_control"],
            "support_violation_fraction": gate["support_violation_fraction"],
            "reliability_passed": bool(gate["passed"]),
            "reliability_label": gate["label"],
        })
    return rows, estimates


def evaluate_policies(
    frame: pd.DataFrame,
    policies: Mapping[str, Any],
    cfg: Config,
    *,
    features: Any,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
    seed_index: int = 0,
) -> tuple[pd.DataFrame, dict[str, tuple[float, np.ndarray]], OpeNuisances, dict[str, dict]]:
    """评估一组冻结策略；返回 (价值表, 每策略估计, nuisance, 门禁明细)。"""
    ordered = require_observed_frame(frame)
    nuisance = fit_ope_nuisances(
        ordered, features, cfg,
        propensity_source=propensity_source,
        design_probability=design_probability,
        seed_index=seed_index,
    )
    confidence = float(cfg.require("evaluation.confidence_level"))
    t = ordered["treatment"].to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    estimates: dict[str, tuple[float, np.ndarray]] = {}
    gates: dict[str, dict] = {}
    for name, pi_raw in policies.items():
        pi = require_policy(pi_raw, len(ordered), name=f"policy {name}")
        policy_rows, policy_estimates = _values_for_policy(
            name, pi, ordered, nuisance, cfg, confidence
        )
        rows.extend(policy_rows)
        estimates[name] = policy_estimates["dr_increment"]
        gates[name] = reliability_gate(pi, t, nuisance.propensity, cfg)
    table = pd.DataFrame(rows).loc[:, list(VALUE_COLUMNS)]
    return table, estimates, nuisance, gates


def paired_policy_differences(
    frame: pd.DataFrame,
    policies: Mapping[str, Any],
    baseline: str,
    cfg: Config,
    *,
    features: Any,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
    seed_index: int = 0,
) -> tuple[pd.DataFrame, dict[str, tuple[float, np.ndarray]], OpeNuisances]:
    """同一批用户、同一 nuisance 下的策略 − baseline 配对差（SE 含协方差）。"""
    ordered = require_observed_frame(frame)
    nuisance = fit_ope_nuisances(
        ordered, features, cfg,
        propensity_source=propensity_source,
        design_probability=design_probability,
        seed_index=seed_index,
    )
    if baseline not in policies:
        raise ValueError(f"baseline {baseline!r} 不在策略集合里")
    y = ordered["net_profit"].to_numpy(dtype=float)
    t = ordered["treatment"].to_numpy(dtype=float)
    e = nuisance.propensity
    confidence = float(cfg.require("evaluation.confidence_level"))
    point: dict[str, dict[str, tuple[float, np.ndarray]]] = {}
    for name, pi_raw in policies.items():
        pi = require_policy(pi_raw, len(ordered), name=f"policy {name}")
        point[name] = {
            "ipw_increment": policy_value_ipw(pi, y, t, e),
            "dr_increment": policy_value_dr(pi, y, t, nuisance.mu1, nuisance.mu0, e),
            "snips_increment": policy_value_snips(pi, y, t, e),
        }
    rows: list[dict[str, object]] = []
    for name, per_estimator in point.items():
        if name == baseline:
            continue
        for estimator in ESTIMATORS:
            value, influence = per_estimator[estimator]
            base_value, base_influence = point[baseline][estimator]
            diff = value - base_value
            diff_influence = influence - base_influence
            se = _se_from_influence(diff_influence)
            low, high = _normal_interval(diff, se, confidence)
            z = diff / se if np.isfinite(se) and se > 0.0 else float("nan")
            p_one_sided = (
                float(1.0 - NormalDist().cdf(z)) if np.isfinite(z) else float("nan")
            )
            rows.append({
                "policy": name,
                "baseline": baseline,
                "estimator": estimator,
                "diff_cny_per_user": diff,
                "se_diff": se,
                "ci_low": low,
                "ci_high": high,
                "one_sided_p_value": p_one_sided,
                "n": len(ordered),
            })
    table = pd.DataFrame(rows).loc[:, list(DIFF_COLUMNS)]
    dr_estimates = {name: per["dr_increment"] for name, per in point.items()}
    return table, dr_estimates, nuisance


def holm_step_down(
    p_values: Mapping[str, float], alpha: float
) -> dict[str, dict[str, object]]:
    """Holm step-down：返回每个假设的调整阈值、调整后 p 与是否拒绝。"""
    names = list(p_values)
    ordered = sorted(names, key=lambda name: p_values[name])
    m = len(ordered)
    result: dict[str, dict[str, object]] = {}
    previous = 0.0
    rejecting = True
    for rank, name in enumerate(ordered, start=1):
        p = float(p_values[name])
        threshold = alpha / (m - rank + 1)
        adjusted_p = min(1.0, max(previous, (m - rank + 1) * p))
        previous = adjusted_p
        rejected = rejecting and p <= threshold
        if not rejected:
            rejecting = False
        result[name] = {
            "p_value": p,
            "adjusted_p_value": adjusted_p,
            "adjusted_alpha": threshold,
            "rejected": bool(rejected),
        }
    return result


def cost_and_guardrail(
    frame: pd.DataFrame,
    policies: Mapping[str, Any],
    cfg: Config,
    *,
    features: Any,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
    seed_index: int = 0,
    confidence: float = 0.95,
) -> pd.DataFrame:
    """逐策略的 DR 券成本与退款率（含区间），与价值表分开列示。"""
    ordered = require_observed_frame(frame)
    nuisance = fit_ope_nuisances(
        ordered, features, cfg,
        propensity_source=propensity_source,
        design_probability=design_probability,
        seed_index=seed_index,
    )
    cost = ordered["coupon_cost"].to_numpy(dtype=float)
    refund = ordered["any_refund_30d"].to_numpy(dtype=float)
    t = ordered["treatment"].to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    for name, pi_raw in policies.items():
        pi = require_policy(pi_raw, len(ordered), name=f"policy {name}")
        components = {
            "coupon_cost_total_per_assigned_user": (
                "cny_per_user",
                policy_cost_dr(pi, cost, t, nuisance.cost_mu1, nuisance.propensity),
            ),
            "refund_rate_30d": (
                "rate",
                policy_guardrail_dr(
                    pi, refund, t, nuisance.refund_mu1, nuisance.refund_mu0,
                    nuisance.propensity,
                ),
            ),
        }
        for component, (unit, (value, influence)) in components.items():
            se = _se_from_influence(influence)
            low, high = _normal_interval(value, se, confidence)
            rows.append({
                "policy": name,
                "component": component,
                "unit": unit,
                "value": value,
                "se": se,
                "ci_low": low,
                "ci_high": high,
                "n": len(ordered),
            })
    return pd.DataFrame(rows).loc[:, list(COMPONENT_COLUMNS)]
