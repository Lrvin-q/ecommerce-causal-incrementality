"""Local-power cells: turn a target profit effect into a legal purchase-probability increment.

Synthetic / known DGP. This is mechanism and calibration code, never a learner
input, and it never reads potential outcomes of an evaluation population.

What question this answers
--------------------------
``configs/v3/scenarios.yaml`` registers 20 ``design_power_jobs`` cells whose target
profit effect is ``active_mde_multiplier × design MDE`` (5 multipliers × 4 layers).
The DGP cannot "add τ yuan to profit": profit is an integral over
``purchase probability → order → amount → cost``. So the only legal knob is the
**purchase-probability increment**, and this module implements exactly the frozen
``design.local_power.effect_construction =
rescale_legal_purchase_probability_increment_then_reintegrate_profit``:

1. Take the registered mechanism's own headroom ``h(x)`` (``p1 = p0 + (1-p0)·h``,
   ``0 < h(x) < 1``, already amplitude-calibrated in
   :mod:`causal_growth.dgp.v3_probability`).
2. Multiply it by one scalar ``s ≥ 0``: ``p1(s, x) = p0(x) + (1-p0(x))·s·h(x)``.
   Nothing else changes — coefficients, intercepts, amplitude cap, refund rate,
   redemption rate, amounts and timing stay exactly as registered.
3. Re-integrate profit **analytically** (no Monte Carlo) on a reference
   population drawn by the mechanism's own covariate generator:

   ``τ(s) = E_x[ p1(s,x)·m1(x) − p0(x)·m0(x) ]``

   where ``m_a(x) = E[net profit of one assigned user | purchase, action a]`` is
   the exact discrete (cent-rounded) expectation returned by
   :func:`causal_growth.dgp.v3_amounts.conditional_user_expectation` at
   ``purchase_probability = 1``. Because ``p1`` enters linearly,

   ``τ(s) = τ0 + s·Δ``,  ``τ0 = E[p0·(m1−m0)]``,  ``Δ = E[(1−p0)·h·m1]``.

Why ``τ0 ≠ 0`` is the central finding
-------------------------------------
``τ0`` is the profit effect of the coupon **at unchanged purchase probability**:
the treated arm still redeems (coupon cost) and refunds slightly more. It is
negative and large (≈ −0.56 yuan/person, i.e. 4–5 design MDEs), and it matches
the Phase B audited negative control ``L0_zero_purchase_effect``. Consequences:

* ``multiplier = 0`` is **not** "no purchase increment". Hitting a zero profit
  effect needs a *positive* increment (``s ≈ 0.64–0.72``) that exactly offsets the
  coupon debit. ``s = 0`` is an *increment-null* cell with true profit ATE
  ``τ0 ≈ −0.56``, which would be rejected with near-certainty — it is a negative
  control, not a size check.
* The feasible profit-effect range is ``[τ0, τ(scale_upper)]``; every target below
  ``τ0`` is unreachable, and reports must say so instead of silently clipping.
  ``scale_upper`` is the smaller of the mathematical bound (``p1 < 1``) and the
  mechanism's own registered cap
  (``headroom_amplitude ≤ dgp.l1.maximum_purchase_increment``).

Discipline
----------
* **Construction never reads truth.** The reference panel uses
  ``generate_covariates(..., population_kind="reference")`` (the same kind of draw
  the probability mechanism is already calibrated on), the *X-only* integrated
  ``p0``/``p1`` and analytic per-purchase profit. For L3 the
  ``purchase_probabilities`` signature demands an audit-U vector; this module
  passes a constant zero vector because the X-only integral is computed from the
  score alone, and :func:`x_only_integral_is_u_invariant` proves that.
* **Scale is the only overridden parameter**, and the derived config is what the
  pipeline receives, so the generated data and its audit truth are produced by
  the registered DGP code path — not by a re-implementation.
* **Failure is loud.** Out-of-domain targets raise :class:`LocalPowerInfeasible`
  with the feasible upper bound in the message; the achieved-vs-target
  self-check raises :class:`LocalPowerConsistencyError` rather than reporting a
  cell as done.
* **No formal repetition counter is touched.** ``formal_repetitions_completed``
  stays 0 in every manifest produced here.

Units: profit effects are yuan per *assigned* user (R1 denominator), probability
increments are absolute probability units.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from causal_growth.config import Config, ConfigError
from causal_growth.dgp.v3_amounts import conditional_user_expectation
from causal_growth.dgp.v3_covariates import generate_covariates
from causal_growth.dgp.v3_probability import calibrate_probability_mechanism, purchase_probabilities
from causal_growth.v3_numerics import load_v3_numerics

__all__ = [
    "DEFAULT_RELATIVE_TOLERANCE",
    "LOCAL_POWER_EFFECT_CONSTRUCTION",
    "LOCAL_POWER_MECHANISM_RULE",
    "REFERENCE_PAIRING_PREFIX",
    "LocalPowerCalibration",
    "LocalPowerConsistencyError",
    "LocalPowerInfeasible",
    "ProfitEffectCurve",
    "ReferencePanel",
    "build_reference_panel",
    "calibrate_local_power_cell",
    "configured_multiplier",
    "increment_scale_key",
    "mechanism_signature",
    "per_purchase_profit",
    "profit_effect_curve",
    "scaled_increment_config",
    "verify_scaled_mechanism",
    "x_only_integral_is_u_invariant",
]

#: 冻结的效应构造口径（``configs/v3/design.yaml`` 的原文）。
LOCAL_POWER_EFFECT_CONSTRUCTION = "rescale_legal_purchase_probability_increment_then_reintegrate_profit"
#: 冻结的机制规则（``design_power_jobs[*].mechanism_rule`` 的原文）。
LOCAL_POWER_MECHANISM_RULE = (
    "invert_purchase_increment_scale_to_design_sample_profit_mde_target; "
    "report achieved effect; fail if probability constraint infeasible"
)

#: 参考人群随机流的分组前缀；新建流，不扰动任何已注册场景的抽样。
REFERENCE_PAIRING_PREFIX = "local_power_reference"

#: achieved vs target 的默认相对容差（数值自检口径，不是业务参数）。
DEFAULT_RELATIVE_TOLERANCE = 1e-6

#: 影响结果机制的配置段；两个配置的指纹相同才允许共用同一个参考面板。
_MECHANISM_SECTIONS: tuple[str, ...] = ("business", "dgp", "windows", "design.temporal")

#: 效应构造唯一允许拧的旋钮：(配置段, 子段, 键)。指纹刻意排除它们，
#: 于是"只有增量被放缩"这件事本身可被指纹核对。
_INCREMENT_KEYS: tuple[tuple[str, str, str], ...] = (
    ("dgp", "l1", "purchase_increment_target"),
    ("dgp", "l0", "purchase_increment"),
)

#: 支持的功效格基础机制（L0 齐次购买 / L1 / L2 / L3）。
_SUPPORTED_PROFILES = frozenset({"l0_purchase", "l1", "l2", "l3"})


class LocalPowerInfeasible(ValueError):
    """目标利润效应落在该机制的可行域之外；消息必须带可行域上界。"""


class LocalPowerConsistencyError(ArithmeticError):
    """achieved_effect 与目标效应的偏差超出容差，或两条独立通道互相矛盾。"""


# --------------------------------------------------------------------------- #
# 机制指纹与受支持范围
# --------------------------------------------------------------------------- #
def mechanism_signature(cfg: Config) -> str:
    """指纹化"结果机制"，用于确认参考面板与待跑配置来自同一机制。

    只取影响结果分布的配置段（``business`` / ``dgp`` / ``windows`` /
    ``design.temporal``）与主种子；``design.n_total``、``treatment_probability``、
    ``design.local_power.*`` 刻意排除——它们不改变机制，只改变样本量与目标。
    购买概率增量本身（:data:`_INCREMENT_KEYS`）也排除：它是 local-power 构造
    **唯一**允许放缩的量，因此"放缩前后指纹相同"恰好等价于"只动了这一个旋钮"。
    """
    sections: dict[str, Any] = {}
    for name in _MECHANISM_SECTIONS:
        if cfg.get(name) is None:
            continue
        data = cfg.section(name)
        if name == "dgp":
            data = json.loads(json.dumps(data))
            for section, sub, key in _INCREMENT_KEYS:
                if section == name and isinstance(data.get(sub), dict):
                    data[sub].pop(key, None)
        sections[name] = data
    payload = {"master_seed": cfg.require("project.master_seed"), "sections": sections}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def increment_scale_key(cfg: Config) -> str:
    """返回"购买概率增量"在配置里的键名（唯一被放缩的参数）。

    ``l0_purchase`` / ``l0_profit_control`` 用 ``dgp.l0.purchase_increment``；
    ``l1``/``l2``/``l3`` 的增量由 ``dgp.l1.purchase_increment_target`` 经解析
    幅度校准得到，放缩该目标即等价于放缩 headroom（幅度对目标是线性的）。
    """
    profile = str(cfg.require("dgp.profile"))
    if profile in {"l0_purchase", "l0_profit_control"}:
        return "dgp.l0.purchase_increment"
    if profile in {"l1", "l2", "l3"}:
        return "dgp.l1.purchase_increment_target"
    raise ConfigError(f"Unknown mechanism profile for local power: {profile}")


def configured_multiplier(cfg: Config) -> float:
    """读该格的 ``design.local_power.active_mde_multiplier``（必须是冻结值）。"""
    value = cfg.require("design.local_power.active_mde_multiplier")
    if value is None:
        raise ConfigError("this configuration is not a registered local-power cell")
    multiplier = float(value)
    if not math.isfinite(multiplier) or multiplier < 0:
        raise ConfigError(f"active_mde_multiplier must be a finite non-negative number, got {value!r}")
    return multiplier


def _require_supported(cfg: Config) -> str:
    """拒绝本模块无法如实构造效应的机制变体（失败要响，不猜）。"""
    profile = str(cfg.require("dgp.profile"))
    if profile not in _SUPPORTED_PROFILES:
        raise ConfigError(f"local power does not support dgp.profile={profile!r}")
    if cfg.get("dgp.l0.control.enabled"):
        raise ConfigError(
            "local power does not support the L0 homogeneity control knob: its treated-arm "
            "goods-cost ratio and redemption probability are solved per user, so a single "
            "purchase-increment scale would not describe the profit effect"
        )
    if cfg.get("dgp.virtual_aa_labels"):
        raise ConfigError("local power cells are not AA cells; virtual labels have no profit effect to scale")
    if str(cfg.require("design.local_power.effect_construction")) != LOCAL_POWER_EFFECT_CONSTRUCTION:
        raise ConfigError("unsupported design.local_power.effect_construction")
    return profile


# --------------------------------------------------------------------------- #
# 解析真值：每购买一次的条件利润（元/人）
# --------------------------------------------------------------------------- #
def per_purchase_profit(users: pd.DataFrame, cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    """两动作的"给定购买"期望净利润（元/人），只由机制参数与 X 决定。

    与 :func:`causal_growth.dgp.v3_engine._conditional_truth_with_errors` 同源：
    ``purchase_probability = 1`` 调同一个离散分币积分，退款率按动作取
    ``refund_rate``/``refund_rate_treated_multiplier``，核销率对照组为 0、处理组为
    ``business.redemption_rate``（L0 旋钮关闭时全人群常量）。
    """
    cart = users["cart_value_cent"].to_numpy()
    refund_control = float(cfg.require("business.refund_rate"))
    refund_treated = refund_control * float(cfg.require("business.refund_rate_treated_multiplier"))
    redemption_treated = float(cfg.require("business.redemption_rate"))
    if not 0 <= refund_control <= 1 or not 0 <= refund_treated <= 1 or not 0 <= redemption_treated <= 1:
        raise ConfigError("refund/redemption probabilities must lie in [0, 1]")
    control = conditional_user_expectation(
        cart, cfg, purchase_probability=1, refund_probability=refund_control, redemption_probability=0,
    )["net_profit"]
    treated = conditional_user_expectation(
        cart, cfg, purchase_probability=1, refund_probability=refund_treated,
        redemption_probability=redemption_treated,
    )["net_profit"]
    return np.asarray(control, dtype=float), np.asarray(treated, dtype=float)


# --------------------------------------------------------------------------- #
# 参考面板
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReferencePanel:
    """效应构造所需的全部解析量（参考人群，不含任何潜在结果）。

    Attributes
    ----------
    users:
        参考人群的已记录 X（与机制校准同一类抽样，``population_kind="reference"``）。
        只用 ``cart_value_cent`` 与机制特征列；不含任何结果列。
    p0:
        X-only 积分后的对照购买概率（L3 已对 U 积分）。
    headroom:
        注册机制的相对增量 ``h = (p1-p0)/(1-p0) ∈ (0,1]``；放缩它即为唯一干预。
    per_purchase_profit_control, per_purchase_profit_treated:
        :func:`per_purchase_profit` 的两个动作条件利润。
    """

    base_scenario_id: str
    config_hash: str
    mechanism_signature: str
    reference_n: int
    pairing_group: str
    profile: str
    users: pd.DataFrame = field(repr=False, compare=False)
    p0: np.ndarray = field(repr=False, compare=False)
    headroom: np.ndarray = field(repr=False, compare=False)
    per_purchase_profit_control: np.ndarray = field(repr=False, compare=False)
    per_purchase_profit_treated: np.ndarray = field(repr=False, compare=False)
    registered_amplitude: float | None
    maximum_purchase_increment: float | None


def build_reference_panel(
    cfg: Config, *, reference_n: int | None = None, pairing_group: str | None = None,
) -> ReferencePanel:
    """构造效应构造用的参考面板（一次，可被同一层 5 个倍数复用）。

    Parameters
    ----------
    cfg:
        基础场景配置（``design_power_jobs[*].base_scenario_id`` 解析出的配置）。
    reference_n:
        参考人群规模；``None`` 取 ``design.n_total``（与格的注册 n 一致）。
        参考均值的抽样标准误 ``sd(τ_i)/sqrt(reference_n)`` 随面板一起报出。
    pairing_group:
        随机流分组；``None`` 时为 ``local_power_reference_<scenario>``。

    Raises
    ------
    ConfigError
        机制变体不受支持（L0 旋钮、虚拟标签、未知 profile、口径不符）。
    """
    profile = _require_supported(cfg)
    scenario_id = str(cfg.require("active_scenario.id"))
    n = int(cfg.require("design.n_total") if reference_n is None else reference_n)
    if n < 2:
        raise ValueError(f"reference_n must be at least 2, got {n}")
    group = pairing_group or f"{REFERENCE_PAIRING_PREFIX}_{scenario_id}"
    batch = generate_covariates(cfg, 0, n, population_kind="reference", pairing_group=group)
    users = batch.users
    # L3 的签名要求一个 audit U；X-only 积分只由 score 决定，故传常量零向量，
    # 且下方只使用 *_given_x 字段（见 x_only_integral_is_u_invariant 的测试）。
    zeros = np.zeros(len(users))
    probabilities = purchase_probabilities(users, cfg, zeros, integrate_u=True)
    if probabilities.p0_given_x is None or probabilities.p1_given_x is None:
        raise AssertionError("reference panel requires integrated X-only probabilities")
    p0 = np.asarray(probabilities.p0_given_x, dtype=float)
    p1 = np.asarray(probabilities.p1_given_x, dtype=float)
    if np.any(~np.isfinite(p0)) or np.any((p0 <= 0) | (p0 >= 1)):
        raise ConfigError("reference control probability left (0,1)")
    if np.any(p1 < p0) or np.any(p1 > 1):
        raise ConfigError("reference treated probability violates p0 <= p1 <= 1")
    complement = 1.0 - p0
    headroom = np.divide(p1 - p0, complement, out=np.zeros_like(p0), where=complement > 0)
    if np.any(headroom < 0) or np.any(headroom >= 1):
        raise ConfigError("registered headroom left [0,1); mechanism is not positive-headroom parameterized")
    control, treated = per_purchase_profit(users, cfg)
    amplitude: float | None = None
    maximum: float | None = None
    if profile in {"l1", "l2", "l3"}:
        amplitude = float(calibrate_probability_mechanism(cfg).headroom_amplitude)
        maximum = float(cfg.require("dgp.l1.maximum_purchase_increment"))
        if not 0 <= amplitude <= maximum <= 1:
            raise ConfigError("registered headroom amplitude is outside the frozen mechanism domain")
    return ReferencePanel(
        base_scenario_id=scenario_id, config_hash=cfg.hash(64),
        mechanism_signature=mechanism_signature(cfg), reference_n=n, pairing_group=group,
        profile=profile, users=users, p0=p0, headroom=headroom,
        per_purchase_profit_control=control, per_purchase_profit_treated=treated,
        registered_amplitude=amplitude, maximum_purchase_increment=maximum,
    )


def x_only_integral_is_u_invariant(cfg: Config, users: pd.DataFrame, *, rows: int = 1) -> bool:
    """证明 X-only 购买概率积分与 audit-U 取值无关（因此零向量不引入真值）。

    对同一批 X 取两种常量 U（0 与 1），比较 ``p0_given_x`` / ``p1_given_x``：
    L3 的积分只由 score 决定，必须逐位相同；其它 profile 的 U 参数本就被忽略。
    ``rows`` 只取前若干行以控制成本（默认 1 行足以证明该恒等式）。
    """
    if not isinstance(users, pd.DataFrame) or users.empty:
        raise ValueError("x_only_integral_is_u_invariant requires a non-empty user frame")
    sample = users.head(max(1, int(rows))).copy()
    first = purchase_probabilities(sample, cfg, np.zeros(len(sample)), integrate_u=True)
    second = purchase_probabilities(sample, cfg, np.ones(len(sample)), integrate_u=True)
    if first.p0_given_x is None or second.p0_given_x is None:
        raise AssertionError("integrated probabilities are required")
    return bool(np.array_equal(first.p0_given_x, second.p0_given_x)
                and np.array_equal(first.p1_given_x, second.p1_given_x))


# --------------------------------------------------------------------------- #
# 效应曲线 τ(s) = τ0 + s·Δ 与可行域
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProfitEffectCurve:
    """一个机制的解析效应曲线、可行域与诊断量（元/人、概率单位）。

    Attributes
    ----------
    effect_at_zero_increment:
        ``τ0 = E[p0·(m1−m0)]``：购买增量恰为 0 时的利润效应（券成本与退款通道），
        通常显著为负。它不是"零效应"，而是"增量零"负对照的真值。
    effect_per_unit_increment_scale:
        ``Δ = E[(1−p0)·h·m1]``：每 1 单位增量倍数的利润效应（元/人）。
    scale_bound_legal / scale_bound_registered / scale_upper:
        ``p1 < 1`` 的数学上界、机制自身上界（幅度 ≤ ``maximum_purchase_increment``）
        与两者较小者；``binding_constraint`` 标明是谁在约束。
    effect_upper:
        ``τ(scale_upper)``；目标效应超过它即不可达。
    reference_sampling_se:
        参考人群均值的抽样标准误 ``sd(τ_i)/sqrt(n_ref)``，评估于注册倍数处。
    profit_sd_mean_component_*:
        ``sqrt(E[p·m²] − (E[p·m])²)``：个体利润里**只由条件均值**贡献的那部分标准差。
        单笔订单内部还有金额/履约/退款/复购方差，所以它是真实个体利润标准差的下界，
        **不能**直接当功效公式里的 σ 用；名义功效一律用实测样本 σ 或设计先导的 σ。
    """

    base_scenario_id: str
    reference_n: int
    pairing_group: str
    effect_at_zero_increment: float
    effect_per_unit_increment_scale: float
    effect_at_registered_scale: float
    scale_bound_legal: float
    scale_bound_registered: float | None
    scale_upper: float
    binding_constraint: str
    effect_upper: float
    max_headroom: float
    mean_purchase_probability_control: float
    mean_purchase_increment_registered: float
    profit_sd_mean_component_control: float
    profit_sd_mean_component_treatment: float
    reference_effect_sd: float
    reference_sampling_se: float
    registered_amplitude: float | None
    maximum_purchase_increment: float | None

    @property
    def effect_min(self) -> float:
        """可行域下界 = 增量倍数 0 处的效应（不可再低）。"""
        return self.effect_at_zero_increment

    def effect_at(self, scale: float) -> float:
        """``τ(s)``：给定增量倍数返回解析利润效应（元/人）。"""
        value = _finite_float("increment_scale", scale)
        if value < 0:
            raise LocalPowerInfeasible(f"increment_scale must be >= 0, got {value}")
        return self.effect_at_zero_increment + value * self.effect_per_unit_increment_scale

    def scale_for_effect(self, effect: float) -> float:
        """反解增量倍数：``s = (τ − τ0)/Δ``，并检查 τ 落在可行域内。

        Raises
        ------
        LocalPowerInfeasible
            τ 低于 ``effect_at_zero_increment``（需要负增量）或高于 ``effect_upper``
            （需要 p1 ≥ 1 或越过机制已注册的幅度上限）。消息给出可行域上界。
        """
        target = _finite_float("target_effect", effect)
        slack = abs(self.effect_upper) * 1e-12 + 1e-12
        if target < self.effect_min - slack:
            raise LocalPowerInfeasible(
                f"{self.base_scenario_id}: target profit effect {target:.6f} yuan/person is below the "
                f"mechanism's reachable floor {self.effect_min:.6f} (the coupon's mechanical debit at zero "
                "purchase increment); no legal probability increment can go lower"
            )
        if target > self.effect_upper + slack:
            raise LocalPowerInfeasible(
                f"{self.base_scenario_id}: target profit effect {target:.6f} yuan/person exceeds the "
                f"feasible upper bound {self.effect_upper:.6f} "
                f"(increment scale {self.scale_upper:.6f}, binding constraint {self.binding_constraint}); "
                "refusing to clip the probability increment"
            )
        if self.effect_per_unit_increment_scale <= 0:
            raise LocalPowerInfeasible("effect slope is non-positive; mechanism has no increasing purchase channel")
        scale = (target - self.effect_at_zero_increment) / self.effect_per_unit_increment_scale
        if scale < 0:
            raise LocalPowerInfeasible(f"solved increment scale is negative: {scale}")
        return scale

    def as_record(self) -> dict[str, Any]:
        """JSON-safe 摘要（非有限值转 ``None``，不写 NaN/inf）。"""
        return {
            "base_scenario_id": self.base_scenario_id,
            "reference_n": self.reference_n,
            "pairing_group": self.pairing_group,
            "effect_at_zero_increment": self.effect_at_zero_increment,
            "effect_per_unit_increment_scale": self.effect_per_unit_increment_scale,
            "effect_at_registered_scale": self.effect_at_registered_scale,
            "scale_bound_legal": self.scale_bound_legal,
            "scale_bound_registered": _json_float(self.scale_bound_registered),
            "scale_upper": self.scale_upper,
            "binding_constraint": self.binding_constraint,
            "effect_upper": self.effect_upper,
            "max_headroom": self.max_headroom,
            "mean_purchase_probability_control": self.mean_purchase_probability_control,
            "mean_purchase_increment_registered": self.mean_purchase_increment_registered,
            "profit_sd_mean_component_control": self.profit_sd_mean_component_control,
            "profit_sd_mean_component_treatment": self.profit_sd_mean_component_treatment,
            "reference_effect_sd": self.reference_effect_sd,
            "reference_sampling_se": self.reference_sampling_se,
            "registered_amplitude": _json_float(self.registered_amplitude),
            "maximum_purchase_increment": _json_float(self.maximum_purchase_increment),
        }


def profit_effect_curve(panel: ReferencePanel) -> ProfitEffectCurve:
    """从参考面板解析地导出 ``τ(s) = τ0 + s·Δ``、可行域与诊断量。

    全部为闭式均值运算（无蒙特卡洛、无根搜索）：同一份面板被该层的 5 个倍数复用。
    """
    p0 = panel.p0
    headroom = panel.headroom
    m0 = panel.per_purchase_profit_control
    m1 = panel.per_purchase_profit_treated
    tau0 = float(np.mean(p0 * (m1 - m0)))
    slope = float(np.mean((1.0 - p0) * headroom * m1))
    if not math.isfinite(tau0) or not math.isfinite(slope):
        raise ArithmeticError("non-finite effect curve")
    max_headroom = float(headroom.max(initial=0.0))
    if max_headroom <= 0:
        raise ConfigError("registered mechanism has no purchase headroom; cannot construct any effect")
    scale_legal = 1.0 / max_headroom
    scale_registered: float | None = None
    if panel.registered_amplitude is not None and panel.maximum_purchase_increment is not None:
        if panel.registered_amplitude <= 0:
            raise ConfigError("registered headroom amplitude is not positive")
        scale_registered = panel.maximum_purchase_increment / panel.registered_amplitude
    candidates = [("mathematical_p1_lt_1", scale_legal)]
    if scale_registered is not None:
        candidates.append(("registered_maximum_purchase_increment", scale_registered))
    binding, scale_upper = min(candidates, key=lambda item: item[1])
    p1_registered = p0 + (1.0 - p0) * headroom
    tau_registered = float(np.mean(p1_registered * m1 - p0 * m0))
    tau_i = p1_registered * m1 - p0 * m0
    return ProfitEffectCurve(
        base_scenario_id=panel.base_scenario_id,
        reference_n=panel.reference_n,
        pairing_group=panel.pairing_group,
        effect_at_zero_increment=tau0,
        effect_per_unit_increment_scale=slope,
        effect_at_registered_scale=tau_registered,
        scale_bound_legal=scale_legal,
        scale_bound_registered=scale_registered,
        scale_upper=scale_upper,
        binding_constraint=binding,
        effect_upper=tau0 + scale_upper * slope,
        max_headroom=max_headroom,
        mean_purchase_probability_control=float(p0.mean()),
        mean_purchase_increment_registered=float((p1_registered - p0).mean()),
        profit_sd_mean_component_control=_profit_sd(p0, m0),
        profit_sd_mean_component_treatment=_profit_sd(p1_registered, m1),
        reference_effect_sd=float(tau_i.std(ddof=0)),
        reference_sampling_se=float(tau_i.std(ddof=0) / math.sqrt(panel.reference_n)),
        registered_amplitude=panel.registered_amplitude,
        maximum_purchase_increment=panel.maximum_purchase_increment,
    )


def _profit_sd(probability: np.ndarray, per_purchase_profit: np.ndarray) -> float:
    """单臂个体利润的标准差：Bernoulli(p)·m 的精确二阶矩（元/人）。"""
    mean = float(np.mean(probability * per_purchase_profit))
    second = float(np.mean(probability * per_purchase_profit**2))
    return math.sqrt(max(second - mean * mean, 0.0))


def _increment_probabilities(panel: ReferencePanel, scale: float) -> np.ndarray:
    """``p1(s) = p0 + (1-p0)·s·h``，并在构造点检查合法性（0 < p1 < 1、p1 ≥ p0）。"""
    value = _finite_float("increment_scale", scale)
    if value < 0:
        raise LocalPowerInfeasible(f"increment_scale must be >= 0, got {value}")
    max_headroom = float(panel.headroom.max(initial=0.0))
    increment = value * panel.headroom
    if np.any(increment >= 1.0):
        raise LocalPowerInfeasible(
            f"increment scale {value} makes the relative increment reach 1 at some users "
            f"(max headroom {max_headroom:.6f}, legal bound {1.0 / max(max_headroom, 1e-300):.6f})"
        )
    p1 = panel.p0 + (1.0 - panel.p0) * increment
    if np.any(~np.isfinite(p1)) or np.any((p1 <= 0) | (p1 >= 1)) or np.any(p1 < panel.p0):
        raise LocalPowerInfeasible("scaled treated probabilities left the legal domain (0, 1)")
    return p1


# --------------------------------------------------------------------------- #
# 单格校准
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LocalPowerCalibration:
    """一个功效格的校准结果，同时是放行 ``build_observed_pipeline`` 的凭据。

    Attributes
    ----------
    target_effect / achieved_effect:
        目标利润效应（元/人）与解析重积分得到的实际效应。两者偏差必须落在
        ``relative_tolerance`` 内（目标为 0 时退化为绝对容差）。
    increment_scale:
        唯一被放缩的量：``p1 = p0 + (1-p0)·scale·h``。它不是概率增量本身，
        而是相对注册 headroom 的倍数。
    scaled_increment_value:
        派生配置里被改写的那个参数的数值（审计用）。
    profit_sd_mean_component_control:
        ``sqrt(E[p0·m0²] − (E[p0·m0])²)``：对照臂个体利润里只由条件均值贡献的标准差。
        它**不含**单笔订单内部的金额/履约/退款方差，是真实个体利润标准差的下界，
        不可直接用作功效公式里的 σ（名义功效用实测样本 σ 或设计先导 σ）。
    profit_sd_mean_component_treatment:
        同上，处理臂（``p1`` 于校准倍数处）。
    """

    cell_id: str
    base_scenario_id: str
    level: str
    multiplier: float
    design_mde: float
    target_effect: float
    increment_scale: float
    achieved_effect: float
    absolute_deviation: float
    relative_deviation: float | None
    relative_tolerance: float
    absolute_tolerance: float
    consistent: bool
    mean_purchase_probability_treated: float
    mean_purchase_increment: float
    profit_sd_mean_component_control: float
    profit_sd_mean_component_treatment: float
    increment_parameter: str
    scaled_increment_value: float
    base_increment_value: float
    base_config_hash: str
    scaled_config_hash: str
    numerics_hash: str
    curve: ProfitEffectCurve = field(repr=False, compare=False)
    scaled_config_object: Config = field(repr=False, compare=False)

    @property
    def effect_construction(self) -> str:
        """冻结口径标签，写进 manifest。"""
        return LOCAL_POWER_EFFECT_CONSTRUCTION

    def scaled_config(self) -> Config:
        """返回已放缩增量参数的派生配置（生成入口必须使用的配置）。"""
        return self.scaled_config_object

    def authorization_record(self) -> dict[str, Any]:
        """``build_observed_pipeline`` 需要的放行字段（也写进 manifest）。"""
        return {
            "cell_id": self.cell_id,
            "base_scenario_id": self.base_scenario_id,
            "level": self.level,
            "multiplier": self.multiplier,
            "design_mde": self.design_mde,
            "target_effect": self.target_effect,
            "achieved_effect": self.achieved_effect,
            "increment_scale": self.increment_scale,
            "increment_parameter": self.increment_parameter,
            "scaled_increment_value": self.scaled_increment_value,
            "effect_construction": self.effect_construction,
            "consistent": self.consistent,
            "reference_n": self.curve.reference_n,
            "scaled_config_hash": self.scaled_config_hash,
        }

    def as_record(self) -> dict[str, Any]:
        """逐格落盘记录（JSON-safe）。"""
        return {
            "cell_id": self.cell_id,
            "base_scenario_id": self.base_scenario_id,
            "level": self.level,
            "multiplier": self.multiplier,
            "design_mde": self.design_mde,
            "target_effect": self.target_effect,
            "increment_scale": self.increment_scale,
            "achieved_effect": self.achieved_effect,
            "absolute_deviation": self.absolute_deviation,
            "relative_deviation": _json_float(self.relative_deviation),
            "relative_tolerance": self.relative_tolerance,
            "absolute_tolerance": self.absolute_tolerance,
            "consistent": self.consistent,
            "mean_purchase_probability_treated": self.mean_purchase_probability_treated,
            "mean_purchase_increment": self.mean_purchase_increment,
            "profit_sd_mean_component_control": self.profit_sd_mean_component_control,
            "profit_sd_mean_component_treatment": self.profit_sd_mean_component_treatment,
            "increment_parameter": self.increment_parameter,
            "scaled_increment_value": self.scaled_increment_value,
            "base_increment_value": self.base_increment_value,
            "base_config_hash": self.base_config_hash,
            "scaled_config_hash": self.scaled_config_hash,
            "numerics_hash": self.numerics_hash,
            "effect_construction": self.effect_construction,
            "mechanism_rule": LOCAL_POWER_MECHANISM_RULE,
            "curve": self.curve.as_record(),
        }


def scaled_increment_config(cfg: Config, scale: float) -> Config:
    """把增量参数乘上 ``scale`` 的派生配置（不改任何其它键）。"""
    key = increment_scale_key(cfg)
    base = float(cfg.require(key))
    multiplier = _finite_float("increment_scale", scale)
    if multiplier < 0:
        raise LocalPowerInfeasible(f"increment_scale must be >= 0, got {multiplier}")
    if base <= 0:
        raise ConfigError(f"{key} must be positive, got {base}")
    value = multiplier * base
    if multiplier > 0 and value <= 0:
        raise LocalPowerInfeasible("scaled increment is not positive")
    return cfg.with_overrides({key: value})


def calibrate_local_power_cell(
    panel: ReferencePanel,
    cfg: Config,
    *,
    design_mde: float,
    curve: ProfitEffectCurve | None = None,
    relative_tolerance: float = DEFAULT_RELATIVE_TOLERANCE,
    absolute_tolerance: float | None = None,
) -> LocalPowerCalibration:
    """把 ``multiplier × design_mde`` 反解成合法的增量倍数并重积分核对。

    Parameters
    ----------
    panel:
        该层基础场景的参考面板（**机制必须与 ``cfg`` 相同**，用指纹交叉核对）。
    cfg:
        该功效格的注册配置（含 ``design.local_power.active_mde_multiplier``）。
    design_mde:
        该格的设计 MDE（元/人）。来自设计先导的**观测**方差表
        （``outputs/tables/v3_phase_D_mde.csv`` 的 ``mde`` 列），不是本模块自算。
    curve:
        已算好的效应曲线（同一层 5 格复用时传入，省去重复求均值）。
    relative_tolerance, absolute_tolerance:
        自检容差。目标效应为 0 时相对偏差无定义，退化为绝对容差，默认取
        ``v3_numerics.integration.absolute_tolerance``（元/人）。

    Raises
    ------
    LocalPowerInfeasible
        目标效应在可行域外（消息含可行域上界）。
    LocalPowerConsistencyError
        重积分得到的 achieved_effect 与目标偏差超容差。
    """
    _require_supported(cfg)
    if mechanism_signature(cfg) != panel.mechanism_signature:
        raise ConfigError("reference panel belongs to a different mechanism than this cell")
    base_from_cell = cfg.get("active_scenario.base_scenario_id")
    if base_from_cell is not None and str(base_from_cell) != panel.base_scenario_id:
        raise ConfigError(
            f"cell {cfg.require('active_scenario.id')} declares base {base_from_cell} but the panel is "
            f"{panel.base_scenario_id}"
        )
    mde = _finite_float("design_mde", design_mde)
    if mde <= 0:
        raise ValueError(f"design_mde must be positive, got {mde}")
    multiplier = configured_multiplier(cfg)
    target = multiplier * mde
    effect_curve = profit_effect_curve(panel) if curve is None else curve
    if effect_curve.base_scenario_id != panel.base_scenario_id:
        raise ConfigError("effect curve and reference panel disagree on the base scenario")
    scale = effect_curve.scale_for_effect(target)
    p1 = _increment_probabilities(panel, scale)
    m0 = panel.per_purchase_profit_control
    m1 = panel.per_purchase_profit_treated
    achieved = float(np.mean(p1 * m1 - panel.p0 * m0))
    absolute_deviation = abs(achieved - target)
    relative_deviation = None if target == 0 else absolute_deviation / abs(target)
    tol_abs = float(load_v3_numerics().require("integration.absolute_tolerance")
                    if absolute_tolerance is None else absolute_tolerance)
    if not math.isfinite(float(relative_tolerance)) or float(relative_tolerance) <= 0:
        raise ValueError(f"relative_tolerance must be positive, got {relative_tolerance}")
    consistent = (relative_deviation <= float(relative_tolerance)
                  if relative_deviation is not None else absolute_deviation <= tol_abs)
    key = increment_scale_key(cfg)
    base_value = float(cfg.require(key))
    derived = scaled_increment_config(cfg, scale)
    calibration = LocalPowerCalibration(
        cell_id=str(cfg.require("active_scenario.id")),
        base_scenario_id=panel.base_scenario_id,
        level=str(cfg.require("active_scenario.level")),
        multiplier=multiplier,
        design_mde=mde,
        target_effect=target,
        increment_scale=scale,
        achieved_effect=achieved,
        absolute_deviation=absolute_deviation,
        relative_deviation=relative_deviation,
        relative_tolerance=float(relative_tolerance),
        absolute_tolerance=tol_abs,
        consistent=bool(consistent),
        mean_purchase_probability_treated=float(p1.mean()),
        mean_purchase_increment=float((p1 - panel.p0).mean()),
        profit_sd_mean_component_control=_profit_sd(panel.p0, m0),
        profit_sd_mean_component_treatment=_profit_sd(p1, m1),
        increment_parameter=key,
        scaled_increment_value=float(derived.require(key)),
        base_increment_value=base_value,
        base_config_hash=cfg.hash(64),
        scaled_config_hash=derived.hash(64),
        numerics_hash=load_v3_numerics().hash(64),
        curve=effect_curve,
        scaled_config_object=derived,
    )
    if not calibration.consistent:
        raise LocalPowerConsistencyError(
            f"{calibration.cell_id}: achieved {achieved:.12f} vs target {target:.12f} yuan/person "
            f"(absolute {absolute_deviation:.3e}, relative {relative_deviation!r}, "
            f"tolerance {calibration.relative_tolerance:g} / {calibration.absolute_tolerance:g})"
        )
    return calibration


def verify_scaled_mechanism(
    panel: ReferencePanel, calibration: LocalPowerCalibration, *, rows: int | None = None,
) -> dict[str, Any]:
    """独立核对：走 DGP 自己的概率代码，确认放缩配置产出同一效应。

    构造通道用的是"面板 p0/h × 解析 m"；本函数改用
    ``purchase_probabilities(derived_cfg)``（即真实生成时会调用的同一段代码）
    重新积分 ``p1``，再算 ``mean(p1·m1 − p0·m0)``。两条通道只共享"给定购买的条件
    利润"，因此它能抓出"幅度对目标非线性""p0 被连带改动""放缩键写错"这类错误。

    ``rows`` 只取前若干行以控制成本（``None`` 表示整块面板）。

    Raises
    ------
    LocalPowerConsistencyError
        DGP 通道的效应与目标偏差超容差，或对照概率被放缩连带改动。
    """
    if not isinstance(calibration, LocalPowerCalibration):
        raise TypeError("verification requires the calibrated effect object")
    users = panel.users if rows is None else panel.users.head(int(rows))
    if users.empty:
        raise ValueError("verification requires at least one reference user")
    m0 = panel.per_purchase_profit_control[: len(users)]
    m1 = panel.per_purchase_profit_treated[: len(users)]
    p0_panel = panel.p0[: len(users)]
    derived = calibration.scaled_config()
    probabilities = purchase_probabilities(users, derived, np.zeros(len(users)), integrate_u=True)
    if probabilities.p0_given_x is None or probabilities.p1_given_x is None:
        raise AssertionError("verification requires integrated X-only probabilities")
    p0_dgp = np.asarray(probabilities.p0_given_x, dtype=float)
    p1_dgp = np.asarray(probabilities.p1_given_x, dtype=float)
    p0_change = float(np.abs(p0_dgp - p0_panel).max(initial=0.0))
    achieved = float(np.mean(p1_dgp * m1 - p0_dgp * m0))
    absolute = abs(achieved - calibration.target_effect)
    relative = None if calibration.target_effect == 0 else absolute / abs(calibration.target_effect)
    passed = (relative <= calibration.relative_tolerance if relative is not None
              else absolute <= calibration.absolute_tolerance)
    if p0_change > 0:
        raise LocalPowerConsistencyError(
            f"{calibration.cell_id}: rescaling the purchase increment moved the control probability by "
            f"{p0_change:.3e}; the increment is not the only changed quantity"
        )
    if not passed:
        raise LocalPowerConsistencyError(
            f"{calibration.cell_id}: the DGP probability path achieves {achieved:.12f} vs target "
            f"{calibration.target_effect:.12f} (absolute {absolute:.3e}, relative {relative!r}); "
            "the scaled configuration does not reproduce the calibrated effect"
        )
    return {
        "achieved_effect_dgp": achieved,
        "absolute_deviation": absolute,
        "relative_deviation": relative,
        "p0_max_abs_change": p0_change,
        "rows_verified": int(len(users)),
        "passed": bool(passed),
    }


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _finite_float(name: str, value: Any) -> float:
    """有限实数校验（NaN/inf/非数值一律抛错，不返回 nan）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating, np.integer)):
        raise TypeError(f"{name} must be a real number, got {type(value).__name__}")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return out


def _json_float(value: float | None) -> float | None:
    """把非有限值转成 ``None``，保证 ``json.dumps(allow_nan=False)`` 可写。"""
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None
