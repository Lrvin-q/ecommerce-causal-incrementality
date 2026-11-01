"""样本量估算：**这个实验要多大？**（方案 §2.4 主线二）

回答方案里的哪个问题
--------------------
方案 §2.4 把样本量口径**写死**为：

    n_每组 = (z_{1-α/2} + z_{1-β})² · [p1(1-p1) + p0(1-p0)] / Δ²

本模块给出三个算法 + 一个按配置装配的入口：

* :func:`sample_size_proportion` —— 转化率（二元指标）的每组样本；
* :func:`sample_size_mean` —— 人均净增量贡献利润（连续指标）的每组样本；
* :func:`sample_size_unequal` —— 处理组占比 ≠ 0.5 时的 (处理组, 对照组) 样本；
* :func:`design_sample_size` —— 从 ``configs/base.yaml`` 读参数，**两个指标分别算、
  取较大值**（方案 §2.4 原文："转化率公式不保证利润指标功效，主指标功效是设计依据"），
  返回可追溯的 :class:`SampleSizeResult`。

符号红线（AGENTS.md §4）
-----------------------
``n_per_group`` 是**每组**样本，``n_total`` 是**总**样本；1:1 分流时
``n_total = 2 * n_per_group``。两个字段名严格区分，禁止互相顶替。

公式来源与假设
--------------
* 两独立样本的正态近似：双侧 α、功效 ``1-β``，z 值一律用 ``scipy.stats.norm.ppf``
  现算，不手写 1.96 / 0.84（手写取整会带来 ±1 人的偏差，方案要求"口径写死"）。
* 二元指标用两独立比例的方差和 ``p1(1-p1) + p0(1-p0)``，不做连续性校正。
* 一律 ``math.ceil`` 向上取整；每组至少 2 人（单组 1 人时样本方差无定义）。
* 参数越界一律抛 ``ValueError`` / ``TypeError``，不 print 警告后继续（AGENTS.md §3.6）。
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Any

from scipy.stats import norm

from causal_growth.config import Config

__all__ = [
    "SampleSizeResult",
    "design_sample_size",
    "sample_size_mean",
    "sample_size_proportion",
    "sample_size_unequal",
]

#: 每组样本下限。统计惯例（自由度/方差定义），不是业务参数。
_MIN_PER_GROUP = 2

#: 判定"配置里的 treatment_share 是否等于 0.5"的浮点容差。
_SHARE_TOL = 1e-12


@dataclass(frozen=True)
class SampleSizeResult:
    """一次样本量设计的完整结果（字段名即报告字段名，禁止混用）。

    Attributes
    ----------
    n_per_group_conversion:
        转化率指标所需的**每组**样本。
    n_per_group_profit:
        利润指标所需的**每组**样本。
    n_per_group:
        两者最大值 —— 方案 §2.4 规定"主指标功效是设计依据"。
    n_total:
        1:1 分流下的**总**样本 = ``2 * n_per_group``（不是每组样本）。
    binding_metric:
        决定样本量的指标，``"conversion"`` 或 ``"profit"``；两者相等时取 ``"profit"``
        （利润是项目的主决策指标）。
    inputs:
        参与计算的全部输入（含 z 值、MDE、σ、α、功效、分流比例），供报告逐项追溯。
    """

    n_per_group_conversion: int
    n_per_group_profit: int
    n_per_group: int
    n_total: int
    binding_metric: str
    inputs: dict[str, Any]


# --------------------------------------------------------------------------- #
# 入参校验（失败要响：AGENTS.md §3.6）
# --------------------------------------------------------------------------- #
def _as_float(name: str, value: Any) -> float:
    """收成有限实数；非数值抛 ``TypeError``，NaN/inf 抛 ``ValueError``。"""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} 必须是实数，收到 {type(value).__name__}")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} 必须是有限实数，收到 {value!r}")
    return out


def _validate_alpha_power(alpha: Any, power: Any) -> tuple[float, float]:
    """α 与功效（``1-β``）都必须严格落在 (0,1) 内。"""
    a = _as_float("alpha", alpha)
    p = _as_float("power", power)
    if not 0.0 < a < 1.0:
        raise ValueError(f"alpha 必须在 (0,1) 内，收到 {a}")
    if not 0.0 < p < 1.0:
        raise ValueError(f"power（= 1-β）必须在 (0,1) 内，收到 {p}")
    return a, p


def _z_critical(alpha: float, power: float) -> tuple[float, float]:
    """返回 ``(z_{1-α/2}, z_{1-β})``；用 ``norm.ppf`` 现算，不硬编码 1.96/0.84。"""
    return (
        float(norm.ppf(1.0 - alpha / 2.0)),
        float(norm.ppf(power)),
    )


def _validate_proportion_shift(p0: Any, mde_abs: Any) -> tuple[float, float]:
    """校验二元指标的 (p0, Δ)：p0∈(0,1)、Δ>0、p0+Δ≤1。"""
    base = _as_float("p0", p0)
    delta = _as_float("mde_abs", mde_abs)
    if not 0.0 < base < 1.0:
        raise ValueError(f"p0 必须在 (0,1) 内，收到 {base}")
    if delta <= 0.0:
        raise ValueError(f"mde_abs 必须为正，收到 {delta}")
    if base + delta > 1.0:
        raise ValueError(
            f"p0 + mde_abs = {base} + {delta} = {base + delta} > 1，"
            "概率尺度越界（处理组概率不能超过 1）"
        )
    return base, delta


# --------------------------------------------------------------------------- #
# 三个算法
# --------------------------------------------------------------------------- #
def sample_size_proportion(
    p0: float,
    mde_abs: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """转化率（二元指标）每次比较所需的**每组**样本。

    回答方案 §2.4 的问题："要把 1pp 的转化率增量推到显著，每组要多少人？"

    公式（方案 §2.4 明文）::

        n = (z_{1-α/2} + z_{1-β})² · [p1(1-p1) + p0(1-p0)] / Δ² ,  p1 = p0 + Δ

    Parameters
    ----------
    p0:
        对照组基线转化率，必须落在 (0,1) 内（业务值见 ``business.baseline_conversion``）。
    mde_abs:
        最小可检测的**绝对**增量 Δ，必须 > 0，且 ``p0 + mde_abs <= 1``。
    alpha:
        双侧第一类错误率，默认 0.05（统计惯例；项目实际值取自
        ``experiment.alpha``）。
    power:
        目标功效 ``1-β``，默认 0.80（统计惯例；项目实际值取自 ``experiment.power``）。

    Returns
    -------
    int
        **每组**样本量（向上取整，且 ≥ 2）。总样本在 1:1 分流下为它的 2 倍，
        由 :class:`SampleSizeResult` 的 ``n_total`` 字段承载，不要在此混用。

    Raises
    ------
    ValueError
        ``p0`` 越界、``mde_abs <= 0``、``p0 + mde_abs > 1``、``alpha``/``power`` 越界。
    TypeError
        入参不是实数。
    """
    base, delta = _validate_proportion_shift(p0, mde_abs)
    a, pw = _validate_alpha_power(alpha, power)
    z_alpha, z_beta = _z_critical(a, pw)

    treated = base + delta
    variance_sum = treated * (1.0 - treated) + base * (1.0 - base)
    n_raw = (z_alpha + z_beta) ** 2 * variance_sum / delta**2
    return max(_MIN_PER_GROUP, int(math.ceil(n_raw)))


def sample_size_mean(
    sigma: float,
    mde_abs: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """连续指标（人均净增量贡献利润）每次比较所需的**每组**样本。

    回答方案 §2.4 的问题："要把 1 元/人的利润增量推到显著，每组要多少人？"
    转化率公式不保证利润指标的功效，所以利润必须单独算一遍再取较大值。

    公式（两独立样本均值差，正态近似）::

        n = (z_{1-α/2} + z_{1-β})² · 2σ² / Δ²

    Parameters
    ----------
    sigma:
        个体利润的标准差 σ（元/人），必须 > 0。业务值见
        ``experiment.mde.profit_sd_assumed``，报告中须说明"若真实方差是假设值的 k 倍，
        每组样本量需乘以 k²"。
    mde_abs:
        最小可检测的均值差 Δ（元/人），必须 > 0。业务值见
        ``experiment.mde.profit_per_user``。
    alpha:
        双侧第一类错误率，默认 0.05。
    power:
        目标功效，默认 0.80。

    Returns
    -------
    int
        **每组**样本量（向上取整，且 ≥ 2）。

    Raises
    ------
    ValueError
        ``sigma <= 0``、``mde_abs <= 0``、``alpha``/``power`` 越界。
    TypeError
        入参不是实数。
    """
    sd = _as_float("sigma", sigma)
    delta = _as_float("mde_abs", mde_abs)
    if sd <= 0.0:
        raise ValueError(f"sigma 必须为正，收到 {sd}")
    if delta <= 0.0:
        raise ValueError(f"mde_abs 必须为正，收到 {delta}")
    a, pw = _validate_alpha_power(alpha, power)
    z_alpha, z_beta = _z_critical(a, pw)

    n_raw = (z_alpha + z_beta) ** 2 * 2.0 * sd**2 / delta**2
    return max(_MIN_PER_GROUP, int(math.ceil(n_raw)))


def sample_size_unequal(
    p0: float,
    mde_abs: float,
    treatment_share: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> tuple[int, int]:
    """处理组占比 ≠ 0.5 时的 (处理组样本, 对照组样本)。

    回答方案 §2.4 之外但项目必须回答的问题："L2 层分流比例是 0.30，样本量怎么变？"
    —— 方案把 1:1 写死为主设计，非等比分流只能作为灵敏度参考，不能悄悄替代主设计。

    推导：设处理组占比 w、对照组占比 ``1-w``，两比例方差和除以总样本 N 得::

        N = (z_{1-α/2} + z_{1-β})² · [p1(1-p1)/w + p0(1-p0)/(1-w)] / Δ²
        n_处理组 = ceil(w · N),  n_对照组 = ceil((1-w) · N)

    ``w = 0.5`` 时退化为 :func:`sample_size_proportion` 的每组样本（各取整后相同）。

    Parameters
    ----------
    p0, mde_abs:
        同 :func:`sample_size_proportion`。
    treatment_share:
        处理组占比 w，必须严格落在 (0,1) 内。
    alpha, power:
        同 :func:`sample_size_proportion`。

    Returns
    -------
    tuple[int, int]
        ``(n_treatment, n_control)``，各自向上取整且 ≥ 2。注意返回的是**两组各自的**
        样本量，不是总样本。

    Raises
    ------
    ValueError
        ``treatment_share`` 越界或比例参数越界。
    TypeError
        入参不是实数。
    """
    base, delta = _validate_proportion_shift(p0, mde_abs)
    share = _as_float("treatment_share", treatment_share)
    if not 0.0 < share < 1.0:
        raise ValueError(f"treatment_share 必须在 (0,1) 内，收到 {share}")
    a, pw = _validate_alpha_power(alpha, power)
    z_alpha, z_beta = _z_critical(a, pw)

    treated = base + delta
    variance_factor = treated * (1.0 - treated) / share + base * (1.0 - base) / (1.0 - share)
    n_total_raw = (z_alpha + z_beta) ** 2 * variance_factor / delta**2

    n_treat = max(_MIN_PER_GROUP, int(math.ceil(share * n_total_raw)))
    n_control = max(_MIN_PER_GROUP, int(math.ceil((1.0 - share) * n_total_raw)))
    return n_treat, n_control


# --------------------------------------------------------------------------- #
# 按配置装配
# --------------------------------------------------------------------------- #
def design_sample_size(cfg: Config) -> SampleSizeResult:
    """从 YAML 配置装配样本量设计（方案 §2.4 的"取较大值"口径）。

    回答方案里的哪个问题："本轮实验应该招多少人？" 需要两份样本量：
    转化率（二元）与人均净增量利润（连续，主指标）。**两者取较大值作为设计依据**，
    并明确写出是哪个指标在起约束作用（``binding_metric``）。

    读取的配置键
    ------------
    * ``business.baseline_conversion`` —— 对照组基线转化率 p0
    * ``experiment.alpha`` —— 双侧 α
    * ``experiment.power`` —— 目标功效 ``1-β``
    * ``experiment.mde.conversion_abs`` —— 转化率绝对 MDE
    * ``experiment.mde.profit_per_user`` —— 人均利润 MDE（元/人）
    * ``experiment.mde.profit_sd_assumed`` —— 个体利润标准差假设 σ（元/人）
    * ``experiment.treatment_share``（可选）—— 若存在且 ≠ 0.5，本函数抛错：
      ``n_total = 2 * n_per_group`` 只在 1:1 分流下成立，非等比分流请改用
      :func:`sample_size_unequal`，绝不在这里悄悄混用符号。

    Returns
    -------
    SampleSizeResult
        ``n_per_group = max(n_per_group_conversion, n_per_group_profit)``，
        ``n_total = 2 * n_per_group``，``inputs`` 保留全部输入与 z 值供报告追溯。

    Raises
    ------
    ConfigError
        配置缺键（由 :meth:`causal_growth.config.Config.require` 抛出）。
    ValueError
        参数越界，或配置的分流比例不是 1:1。
    """
    p0 = _as_float("business.baseline_conversion", cfg.require("business.baseline_conversion"))
    alpha = _as_float("experiment.alpha", cfg.require("experiment.alpha"))
    power = _as_float("experiment.power", cfg.require("experiment.power"))
    mde_conversion = _as_float(
        "experiment.mde.conversion_abs", cfg.require("experiment.mde.conversion_abs")
    )
    mde_profit = _as_float(
        "experiment.mde.profit_per_user", cfg.require("experiment.mde.profit_per_user")
    )
    sigma = _as_float(
        "experiment.mde.profit_sd_assumed", cfg.require("experiment.mde.profit_sd_assumed")
    )

    share_raw = cfg.get("experiment.treatment_share")
    treatment_share = 0.5 if share_raw is None else _as_float(
        "experiment.treatment_share", share_raw
    )
    if abs(treatment_share - 0.5) > _SHARE_TOL:
        raise ValueError(
            "design_sample_size 只对 1:1 分流成立（n_total = 2 * n_per_group）；"
            f"配置 experiment.treatment_share = {treatment_share}，"
            "非等比分流请改用 sample_size_unequal()"
        )

    n_conversion = sample_size_proportion(p0, mde_conversion, alpha=alpha, power=power)
    n_profit = sample_size_mean(sigma, mde_profit, alpha=alpha, power=power)
    n_per_group = max(n_conversion, n_profit)
    binding_metric = "profit" if n_profit >= n_conversion else "conversion"
    z_alpha, z_beta = _z_critical(alpha, power)

    inputs: dict[str, Any] = {
        "p0": p0,
        "p1": p0 + mde_conversion,
        "alpha": alpha,
        "power": power,
        "z_1_minus_alpha_over_2": z_alpha,
        "z_1_minus_beta": z_beta,
        "mde_conversion_abs": mde_conversion,
        "mde_profit_per_user": mde_profit,
        "profit_sd_assumed": sigma,
        "treatment_share": treatment_share,
        "allocation": "1:1",
        "n_per_group_conversion": n_conversion,
        "n_per_group_profit": n_profit,
        "formula_conversion": (
            "(z_{1-alpha/2}+z_{1-beta})^2*[p1(1-p1)+p0(1-p0)]/mde_abs^2"
        ),
        "formula_profit": "(z_{1-alpha/2}+z_{1-beta})^2*2*sigma^2/mde_abs^2",
    }

    return SampleSizeResult(
        n_per_group_conversion=n_conversion,
        n_per_group_profit=n_profit,
        n_per_group=n_per_group,
        n_total=2 * n_per_group,
        binding_metric=binding_metric,
        inputs=inputs,
    )
