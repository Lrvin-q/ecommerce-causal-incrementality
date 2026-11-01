"""AA 校验：**分流与检验流程本身可信吗？**（方案 §2.4 主线二）

回答方案里的哪个问题
--------------------
方案 §2.4 原文："重复 1000 次 AA 模拟，报告 p 值分布（应接近 Uniform）和假阳性率
（应接近 α），**不看单次 AA 是否显著**。"

所以本模块的输出是一组**分布层面**的诊断量：

* ``false_positive_rate`` —— 在 α 下的经验第一类错误率，应 ≈ α（项目验收区间
  [0.035, 0.065] 见 GOAL.md ⑨）；
* ``fpr_ci`` —— 该假阳性率的 Wilson 95% 置信区间（1000 次重复本身也有抽样误差，
  不给区间就无法判断"0.047 与 0.05 的差距是噪声还是偏倚"）；
* ``mean_p_value`` —— 应 ≈ 0.5（Uniform 的均值）；
* ``ks_uniform_stat`` / ``ks_uniform_pvalue`` —— p 值对 Uniform(0,1) 的 KS 检验。

**正确读法（写进报告时必须照此表述）**：AA 校验看的是"1000 个 p 值是否接近
Uniform、假阳性率是否接近 α"。单次 AA 显著（p < 0.05）在 5% 的概率下本来就会发生，
**它不是流程有问题的证据，也不能作为"实验没问题"的结论**；反过来，单次 AA 不显著
也不证明流程无偏。

方法
----
* 二元指标：每次重复让两组都从同一个 ``Bernoulli(p0)`` 抽样（H0 成立，无处理效应），
  再用**合并方差**的两比例 z 检验比较（与主分析的口径一致：合并方差对应 H0 下的
  共同比例，正是 AA 场景下正确的方差估计）。
* 连续指标：两组都从 ``Normal(mean, sd)`` 抽样，用 **Welch t 检验**（不假设等方差，
  与利润指标存在异方差时的实际用法一致）。
* 随机数一律经 :func:`causal_growth.rng.child_rng` 派生，stream 固定为
  ``design.aa.binary`` / ``design.aa.continuous``，``index`` 为重复序号，
  因此同一 ``master_seed`` 逐位可复现（AGENTS.md §3.3）。
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import kstest, norm, ttest_ind

from causal_growth.rng import child_rng

__all__ = [
    "AAResult",
    "aa_test_binary",
    "aa_test_continuous",
    "summarize_pvalues",
]

#: 随机流名（带语义，便于追溯；AGENTS.md §3.3）
_STREAM_BINARY = "design.aa.binary"
_STREAM_CONTINUOUS = "design.aa.continuous"

#: 假阳性率置信区间的水平。统计惯例（Wilson 区间），不是业务参数。
_CI_CONFIDENCE = 0.95


@dataclass(frozen=True)
class AAResult:
    """一次 AA 校验的汇总结果。

    Attributes
    ----------
    p_values:
        长度为 ``n_repeats`` 的 p 值数组（每次重复一个）。
    n_repeats:
        重复次数（方案要求 1000）。
    alpha:
        判定假阳性的显著性水平。
    false_positive_rate:
        ``mean(p_values < alpha)``，经验第一类错误率，应 ≈ alpha。
    fpr_ci:
        假阳性率的 Wilson 95% 置信区间 ``(lower, upper)``。
    mean_p_value:
        p 值均值，Uniform(0,1) 下应 ≈ 0.5。
    ks_uniform_stat:
        p 值对 Uniform(0,1) 的 KS 统计量（越小越像 Uniform）。
    ks_uniform_pvalue:
        该 KS 检验的 p 值；**不应**显著拒绝 Uniform（项目测试要求 > 0.01）。
    """

    p_values: np.ndarray
    n_repeats: int
    alpha: float
    false_positive_rate: float
    fpr_ci: tuple[float, float]
    mean_p_value: float
    ks_uniform_stat: float
    ks_uniform_pvalue: float


# --------------------------------------------------------------------------- #
# 校验与工具
# --------------------------------------------------------------------------- #
def _as_int(name: str, value: Any) -> int:
    """收成整数；bool 与浮点一律拒绝，避免 1000.0 次这种静默转换。"""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise TypeError(f"{name} 必须是整数，收到 {type(value).__name__}")
    return int(value)


def _as_float(name: str, value: Any) -> float:
    """收成有限实数；非数值抛 ``TypeError``，NaN/inf 抛 ``ValueError``。"""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} 必须是实数，收到 {type(value).__name__}")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} 必须是有限实数，收到 {value!r}")
    return out


def _validate_alpha(alpha: Any) -> float:
    """α 必须严格落在 (0,1) 内。"""
    out = _as_float("alpha", alpha)
    if not 0.0 < out < 1.0:
        raise ValueError(f"alpha 必须在 (0,1) 内，收到 {out}")
    return out


def _validate_pvalues(p_values: Any) -> np.ndarray:
    """把入参收成合法的一维 p 值数组。

    Raises
    ------
    ValueError
        空数组、非一维、含 NaN/inf、或取值落在 [0,1] 之外 —— 这些都是"上游算错了"，
        必须立即响，不能当作有效 p 值参与汇总（AGENTS.md §3.6）。
    """
    arr = np.asarray(p_values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"p 值必须是一维数组，收到 {arr.ndim} 维")
    if arr.size == 0:
        raise ValueError("p 值数组为空，无法汇总（AA 至少要 1 次重复）")
    if not np.all(np.isfinite(arr)):
        raise ValueError("p 值数组含 NaN/inf，无法汇总")
    if np.any(arr < 0.0) or np.any(arr > 1.0):
        raise ValueError("p 值必须落在 [0,1] 内，请检查上游检验实现")
    return arr


def _wilson_interval(
    successes: int, n: int, confidence: float = _CI_CONFIDENCE
) -> tuple[float, float]:
    """二项比例的 Wilson 置信区间（比正态近似更适合 ``p̂`` 靠近 0 的场景）。

    Wilson 区间在小样本、极端比例下仍能给出非退化的区间，AA 的假阳性率
    ``p̂ ≈ 0.05`` 正属于这种"靠近边界但 n 不算大"的场景，因此不用 Wald 区间。
    """
    if n <= 0:
        raise ValueError(f"Wilson 区间需要 n > 0，收到 {n}")
    z = float(norm.ppf(0.5 + confidence / 2.0))
    phat = successes / n
    denom = 1.0 + z**2 / n
    center = (phat + z**2 / (2.0 * n)) / denom
    half = z * math.sqrt(phat * (1.0 - phat) / n + z**2 / (4.0 * n**2)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _two_proportion_z_pvalue(x_treat: int, n_treat: int, x_control: int, n_control: int) -> float:
    """两比例 z 检验（合并方差）的双侧 p 值。

    合并方差 ``p̄(1-p̄)(1/n_t + 1/n_c)`` 是 H0（两组同一比例）下的正确估计，
    因此 AA 场景用它；护栏非劣效的区间估计则用**非合并**方差（见 guardrail 模块）。
    当两组成功数都落在 0 或都等于 n 时方差为 0，检验无定义，按"无证据"返回 1.0。
    """
    p_treat = x_treat / n_treat
    p_control = x_control / n_control
    pooled = (x_treat + x_control) / (n_treat + n_control)
    var = pooled * (1.0 - pooled) * (1.0 / n_treat + 1.0 / n_control)
    if var <= 0.0:
        return 1.0
    z = (p_treat - p_control) / math.sqrt(var)
    return float(2.0 * norm.sf(abs(z)))


def _finite_or_one(p_value: float) -> float:
    """把退化抽样造成的非有限 p 值收成 1.0（"无证据"，不是静默降级）。"""
    return float(p_value) if math.isfinite(p_value) else 1.0


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def summarize_pvalues(p_values: Any, alpha: float = 0.05) -> AAResult:
    """把一串 p 值汇总成 AA 诊断结果（假阳性率 + Wilson 区间 + KS 对 Uniform）。

    回答方案里的哪个问题："这 1000 次 AA 的 p 值像不像 Uniform？假阳性率离 α 多远？"

    Parameters
    ----------
    p_values:
        一维 p 值数组，取值必须落在 [0,1] 内且不含 NaN（否则抛 ``ValueError``）。
    alpha:
        判定假阳性的显著性水平，默认 0.05（统计惯例；项目实际值取自
        ``experiment.aa.alpha``）。

    Returns
    -------
    AAResult

    Raises
    ------
    ValueError
        p 值为空/非一维/含 NaN/越界，或 ``alpha`` 越界。
    TypeError
        ``alpha`` 不是实数。
    """
    a = _validate_alpha(alpha)
    arr = _validate_pvalues(p_values)

    n = int(arr.size)
    hits = int(np.count_nonzero(arr < a))
    fpr = hits / n
    ci = _wilson_interval(hits, n)
    mean_p = float(arr.mean())
    ks = kstest(arr, "uniform")

    return AAResult(
        p_values=arr,
        n_repeats=n,
        alpha=a,
        false_positive_rate=fpr,
        fpr_ci=ci,
        mean_p_value=mean_p,
        ks_uniform_stat=float(ks.statistic),
        ks_uniform_pvalue=float(ks.pvalue),
    )


# --------------------------------------------------------------------------- #
# AA 模拟
# --------------------------------------------------------------------------- #
def aa_test_binary(
    p0: float,
    n_per_group: int,
    repeats: int,
    *,
    alpha: float = 0.05,
    master_seed: int,
) -> AAResult:
    """二元指标（转化率）的 AA 模拟：**两组同分布抽样**后做两比例 z 检验。

    回答方案里的哪个问题："如果没有任何处理效应，我们的分流 + 检验流程会不会
    在 5% 的时刻误报？" 每次重复都让处理组与对照组从同一个
    ``Bernoulli(p0)`` 抽 ``n_per_group`` 个用户（1:1 分流），做合并方差的两比例
    z 检验，得到 1000 个 p 值再交给 :func:`summarize_pvalues`。

    **不要把单次 AA 的显著性当作结论**：正确读法是"p 值分布接近 Uniform、
    假阳性率接近 α"（方案 §2.4 原文）。

    Parameters
    ----------
    p0:
        AA 两组的共同转化率，必须落在 (0,1) 内（业务值见
        ``business.baseline_conversion``）。
    n_per_group:
        **每组**样本量（不是总样本），至少 2。
    repeats:
        重复次数，方案要求 1000（``experiment.aa.repeats``）。
    alpha:
        显著性水平，默认 0.05（``experiment.aa.alpha``）。
    master_seed:
        主种子；每次重复用 ``child_rng(master_seed, "design.aa.binary", rep)``
        派生出独立随机流（AGENTS.md §3.3）。

    Returns
    -------
    AAResult

    Raises
    ------
    ValueError
        ``p0`` 越界、``n_per_group < 2``、``repeats < 1``、``alpha`` 越界。
    TypeError
        参数类型不对（如 repeats 传浮点）。
    """
    if isinstance(p0, bool) or not isinstance(p0, numbers.Real):
        raise TypeError(f"p0 必须是实数，收到 {type(p0).__name__}")
    base = _as_float("p0", p0)
    if not 0.0 < base < 1.0:
        raise ValueError(f"p0 必须在 (0,1) 内，收到 {base}")

    n = _as_int("n_per_group", n_per_group)
    if n < 2:
        raise ValueError(f"n_per_group 至少为 2（单组 1 人时方差无定义），收到 {n}")
    reps = _as_int("repeats", repeats)
    if reps < 1:
        raise ValueError(f"repeats 至少为 1，收到 {reps}")
    a = _validate_alpha(alpha)
    seed = _as_int("master_seed", master_seed)

    p_values = np.empty(reps, dtype=float)
    for rep in range(reps):
        rng = child_rng(seed, _STREAM_BINARY, rep)
        control = int(rng.binomial(1, base, size=n).sum())
        treat = int(rng.binomial(1, base, size=n).sum())
        p_values[rep] = _two_proportion_z_pvalue(treat, n, control, n)

    return summarize_pvalues(p_values, alpha=a)


def aa_test_continuous(
    mean: float,
    sd: float,
    n_per_group: int,
    repeats: int,
    *,
    alpha: float = 0.05,
    master_seed: int,
) -> AAResult:
    """连续指标（人均净增量利润）的 AA 模拟：两组同分布抽样后做 Welch t 检验。

    回答方案里的哪个问题："利润指标在无效应情况下，误报率是否也控制在 α？"
    两组都从 ``Normal(mean, sd)`` 抽 ``n_per_group`` 个用户（1:1 分流），
    用不假设等方差的 Welch t 检验比较，得到 1000 个 p 值。

    参数含义与边界条件同 :func:`aa_test_binary`；随机流名为
    ``design.aa.continuous``，与二元指标正交（新增一条流不会扰动另一条）。

    Parameters
    ----------
    mean:
        两组的共同均值（元/人）。
    sd:
        组内标准差，必须 > 0。
    n_per_group:
        **每组**样本量（不是总样本），至少 2。
    repeats:
        重复次数，方案要求 1000。
    alpha:
        显著性水平，默认 0.05。
    master_seed:
        主种子。

    Returns
    -------
    AAResult

    Raises
    ------
    ValueError
        ``sd <= 0``、``n_per_group < 2``、``repeats < 1``、``alpha`` 越界。
    TypeError
        参数类型不对。
    """
    mu = _as_float("mean", mean)
    sigma = _as_float("sd", sd)
    if sigma <= 0.0:
        raise ValueError(f"sd 必须为正，收到 {sigma}")

    n = _as_int("n_per_group", n_per_group)
    if n < 2:
        raise ValueError(f"n_per_group 至少为 2（单组 1 人时方差无定义），收到 {n}")
    reps = _as_int("repeats", repeats)
    if reps < 1:
        raise ValueError(f"repeats 至少为 1，收到 {reps}")
    a = _validate_alpha(alpha)
    seed = _as_int("master_seed", master_seed)

    p_values = np.empty(reps, dtype=float)
    for rep in range(reps):
        rng = child_rng(seed, _STREAM_CONTINUOUS, rep)
        control = rng.normal(mu, sigma, size=n)
        treat = rng.normal(mu, sigma, size=n)
        result = ttest_ind(treat, control, equal_var=False)
        p_values[rep] = _finite_or_one(float(result.pvalue))

    return summarize_pvalues(p_values, alpha=a)
