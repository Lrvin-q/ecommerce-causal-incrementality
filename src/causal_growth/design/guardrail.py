"""护栏指标非劣效检验：**增长有没有以退款率恶化为代价？**（方案 §2.4 主线二）

回答方案里的哪个问题
--------------------
方案 §2.4 原文："预设非劣效界值（如退款率恶化不超过 0.5pp），用单侧置信区间判断。
**'不显著'不等于'安全'**。"

为什么必须写成非劣效检验
------------------------
"两组退款率差异不显著"只说明证据不足以拒绝"没有差异"，它**无法排除**"退款率
恶化了 0.4pp 但样本量不够"这种情形。正确的问法是："退款率恶化的单侧 (1-α) 置信
上界，是否小于业务可接受的最大恶化幅度（界值 margin）？" 只有上界低于界值，
才算在预设的容忍度内证明"没有实质性恶化"。

方法（单侧 Wald 区间）
----------------------
* 差值 ``diff = p_treat - p_control``；对退款率而言**正数 = 恶化**。
* 标准误用**非合并方差**：``se = sqrt(p_t(1-p_t)/n_t + p_c(1-p_c)/n_c)`` ——
  区间估计不假设 H0 成立，所以不能用合并方差（合并方差是 AA/z 检验在 H0 下的做法）。
* 单侧置信上界：``diff + z_{1-α} · se``。
* 判定：``passed = ci_one_sided_upper < margin``。

边界
----
``n <= 0``、成功数越界、``margin <= 0``、``alpha_one_sided`` 越界一律抛错
（AGENTS.md §3.6：失败要响）。两组比例都退化在 0 或 1 上时 ``se = 0``，此时上界
等于点估计，属于"数据完全无变异"的极端情形，本模块如实返回而不额外放宽。
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Any

from scipy.stats import norm

__all__ = ["NonInferiorityResult", "noninferiority_binary"]

#: 判定方法的落名（报告与表格里要能追到算法）。
_METHOD = "wald_1sided_ci_unpooled_se"


@dataclass(frozen=True)
class NonInferiorityResult:
    """一次护栏非劣效检验的结果。

    Attributes
    ----------
    metric:
        指标名（默认 ``"refund_rate"``），报告里必须与界值口径一起写明。
    diff:
        ``p_treat - p_control``。对退款率这类"越低越好"的护栏指标，**正数 = 恶化**。
    se:
        差值的标准误（**非合并**方差）。
    margin:
        预设的非劣效界值：允许恶化的最大幅度（概率尺度，0.005 = 0.5pp）。
    alpha_one_sided:
        单侧显著性水平（方案取 0.05）。
    ci_one_sided_upper:
        单侧 ``1 - alpha`` 置信上界 ``diff + z_{1-α} · se``。
    passed:
        是否通过非劣效判定：``ci_one_sided_upper < margin``。
    method:
        判定方法标识，便于报告追溯。
    """

    metric: str
    diff: float
    se: float
    margin: float
    alpha_one_sided: float
    ci_one_sided_upper: float
    passed: bool
    method: str


def _as_float(name: str, value: Any) -> float:
    """收成有限实数；非数值抛 ``TypeError``，NaN/inf 抛 ``ValueError``。"""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} 必须是实数，收到 {type(value).__name__}")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} 必须是有限实数，收到 {value!r}")
    return out


def _as_count(name: str, value: Any) -> int:
    """收成非负整数计数；bool 与浮点一律拒绝。"""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise TypeError(f"{name} 必须是整数，收到 {type(value).__name__}")
    return int(value)


def noninferiority_binary(
    successes_treat: int,
    n_treat: int,
    successes_control: int,
    n_control: int,
    *,
    margin: float,
    alpha_one_sided: float = 0.05,
    metric: str = "refund_rate",
) -> NonInferiorityResult:
    """二元护栏指标的单侧非劣效检验（方案 §2.4：界值 + 单侧 CI，不看"是否显著"）。

    回答方案里的哪个问题："处理组退款率的单侧 95% 上界，是否低于 0.5pp 的可容忍
    恶化幅度？" 只有低于界值才能说"非劣效"；"差异不显著"不构成安全的证据。

    公式
    ----
    ``diff = p_t - p_c``，
    ``se = sqrt(p_t(1-p_t)/n_t + p_c(1-p_c)/n_c)``（非合并方差），
    ``ci_upper = diff + z_{1-α} · se``，
    ``passed = ci_upper < margin``。

    Parameters
    ----------
    successes_treat, n_treat:
        处理组的退款单数与随机分配用户数（**分母是随机分配用户**，不是支付用户，
        见 GOAL.md R1）。
    successes_control, n_control:
        对照组同样的两个数。
    margin:
        预设非劣效界值，必须 > 0（业务值见
        ``experiment.guardrail.noninferiority_margin``，默认 0.005 = 0.5pp）。
    alpha_one_sided:
        单侧显著性水平，默认 0.05（``experiment.guardrail.alpha_one_sided``）。
    metric:
        指标名，默认 ``"refund_rate"``；写进结果便于报告追溯。

    Returns
    -------
    NonInferiorityResult

    Raises
    ------
    ValueError
        ``n <= 0``、``0 <= successes <= n`` 不成立、``margin <= 0``、
        ``alpha_one_sided`` 不在 (0,1) 内。
    TypeError
        参数类型不对（如把 3.0 当计数传入）。
    """
    k_t = _as_count("successes_treat", successes_treat)
    n_t = _as_count("n_treat", n_treat)
    k_c = _as_count("successes_control", successes_control)
    n_c = _as_count("n_control", n_control)

    if n_t <= 0:
        raise ValueError(f"n_treat 必须为正，收到 {n_t}")
    if n_c <= 0:
        raise ValueError(f"n_control 必须为正，收到 {n_c}")
    if not 0 <= k_t <= n_t:
        raise ValueError(f"successes_treat({k_t}) 必须落在 [0, n_treat={n_t}] 内")
    if not 0 <= k_c <= n_c:
        raise ValueError(f"successes_control({k_c}) 必须落在 [0, n_control={n_c}] 内")

    margin_value = _as_float("margin", margin)
    if margin_value <= 0.0:
        raise ValueError(
            f"margin 必须为正（表示允许恶化的最大幅度），收到 {margin_value}"
        )
    alpha = _as_float("alpha_one_sided", alpha_one_sided)
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha_one_sided 必须在 (0,1) 内，收到 {alpha}")
    if not isinstance(metric, str) or not metric.strip():
        raise ValueError(f"metric 必须是非空字符串，收到 {metric!r}")

    p_t = k_t / n_t
    p_c = k_c / n_c
    diff = p_t - p_c
    se = math.sqrt(p_t * (1.0 - p_t) / n_t + p_c * (1.0 - p_c) / n_c)
    z = float(norm.ppf(1.0 - alpha))
    ci_upper = diff + z * se

    return NonInferiorityResult(
        metric=metric,
        diff=diff,
        se=se,
        margin=margin_value,
        alpha_one_sided=alpha,
        ci_one_sided_upper=ci_upper,
        passed=bool(ci_upper < margin_value),
        method=_METHOD,
    )
