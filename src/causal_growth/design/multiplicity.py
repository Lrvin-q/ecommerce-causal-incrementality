"""多重比较校正：**多个指标/切片一起看时，α 有没有被吃掉？**（方案 §2.4 主线二）

回答方案里的哪个问题
--------------------
方案 §2.4 原文："多个主指标用 Bonferroni/BH；多个人群切片预注册，探索性切片标注
'未校正'；多轮策略尝试用 alpha spending。"

本项目主指标是两个（``net_profit_per_user``、``conversion``，见
``experiment.multiplicity.primary_metrics``），同时检验两个指标会把族错误率
（FWER）抬到 ``1-(1-α)² ≈ 9.75%``。三种校正回答三个不同的问题：

============== ====================================== ==========================
方法            控制什么                                适用场景（本项目的用法）
============== ====================================== ==========================
Bonferroni     FWER（强控制），最保守                    主指标少、任何假阳性都不可接受
Holm            FWER（强控制），一致地优于 Bonferroni     **本项目默认**（配置 ``method: holm``）
Benjamini-Hochberg  FDR（错误发现比例）                 大量探索性切片，允许少量假阳性
============== ====================================== ==========================

约定
----
* **保持输入顺序**：内部排序只为计算步进，返回值必须与输入同序（报告按指标名对齐）。
* ``adjusted_p`` 一律截断到 ``[0,1]``。
* 空输入返回空数组（调用方可能过滤掉了所有切片）；含 NaN、越界、非一维一律抛
  ``ValueError`` —— p 值算错必须当场响，不能靠校正函数兜底（AGENTS.md §3.6）。
* ``rejected`` 用 ``adjusted_p <= alpha`` 判定（等号视为拒绝，避免 Bonferroni
  恰好落在 α 上时出现"adjusted_p = 0.05 却不拒绝"的边界歧义）。
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = [
    "MultiplicityResult",
    "adjust",
    "benjamini_hochberg",
    "bonferroni",
    "holm",
]

#: 支持的方法名（``experiment.multiplicity.method`` 的取值）。
_METHODS: tuple[str, ...] = ("bonferroni", "holm", "bh")


@dataclass(frozen=True)
class MultiplicityResult:
    """一次多重比较校正的结果。

    Attributes
    ----------
    method:
        方法名，``"bonferroni"`` / ``"holm"`` / ``"bh"``。
    adjusted_p:
        校正后 p 值，**与输入同序**，取值截断在 ``[0,1]``。
    rejected:
        是否在 ``alpha`` 下拒绝原假设（``adjusted_p <= alpha``），与输入同序。
    alpha:
        显著性水平。
    raw_p:
        原始 p 值（与输入同序），便于报告并排展示"校正前/校正后"。
    """

    method: str
    adjusted_p: np.ndarray
    rejected: np.ndarray
    alpha: float
    raw_p: np.ndarray


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
    """把入参收成合法的一维 p 值数组（允许空数组）。

    Raises
    ------
    ValueError
        非一维、含 NaN/inf、或取值落在 [0,1] 之外。
    """
    arr = np.asarray(p_values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"p 值必须是一维数组，收到 {arr.ndim} 维")
    if arr.size == 0:
        return arr
    if not np.all(np.isfinite(arr)):
        raise ValueError("p 值数组含 NaN/inf，无法校正")
    if np.any(arr < 0.0) or np.any(arr > 1.0):
        raise ValueError("p 值必须落在 [0,1] 内，请检查上游检验实现")
    return arr


def _build(method: str, raw: np.ndarray, adjusted: np.ndarray, alpha: float) -> MultiplicityResult:
    """组装结果：截断到 [0,1] 并给出 ``adjusted_p <= alpha`` 的拒绝标记。"""
    clipped = np.clip(adjusted, 0.0, 1.0)
    return MultiplicityResult(
        method=method,
        adjusted_p=clipped,
        rejected=clipped <= alpha,
        alpha=alpha,
        raw_p=raw,
    )


# --------------------------------------------------------------------------- #
# 三种方法
# --------------------------------------------------------------------------- #
def bonferroni(p_values: Any, alpha: float = 0.05) -> MultiplicityResult:
    """Bonferroni 校正：``p_adj = min(1, p * m)``。

    回答方案里的哪个问题："两个主指标同时检验时，把 α 平均切给 m 个指标后还剩多少？"
    控制 FWER，最简单也最保守（等价于每项用 ``α/m``）。

    Parameters
    ----------
    p_values:
        一维 p 值数组，可空（返回空结果），含 NaN 抛 ``ValueError``。
    alpha:
        家族显著性水平，默认 0.05。

    Returns
    -------
    MultiplicityResult
        ``adjusted_p`` 与 ``raw_p`` 同序。
    """
    a = _validate_alpha(alpha)
    raw = _validate_pvalues(p_values)
    if raw.size == 0:
        return _build("bonferroni", raw, np.empty(0, dtype=float), a)
    m = raw.size
    adjusted = np.minimum(1.0, raw * m)
    return _build("bonferroni", raw, adjusted, a)


def holm(p_values: Any, alpha: float = 0.05) -> MultiplicityResult:
    """Holm（step-down）校正：按 p 升序做 ``p_adj[i] = max(前一个 p_adj, min(1, p*(m-i)))``。

    回答方案里的哪个问题："既然只检验两个主指标，有没有比 Bonferroni 更省功效、
    但仍强控 FWER 的做法？" 有 —— Holm 一致地不弱于 Bonferroni（本项目默认方法，
    配置 ``experiment.multiplicity.method: holm``）。

    实现要点
    --------
    1. 升序排序，第 i 个（0 基）乘 ``m - i``；
    2. 取前缀最大值，保证校正后 p 值**单调不减**（否则拒绝集会出现逻辑矛盾）；
    3. 最后按原位置还原顺序。

    Parameters
    ----------
    p_values:
        一维 p 值数组，可空。
    alpha:
        家族显著性水平，默认 0.05。

    Returns
    -------
    MultiplicityResult
    """
    a = _validate_alpha(alpha)
    raw = _validate_pvalues(p_values)
    m = raw.size
    if m == 0:
        return _build("holm", raw, np.empty(0, dtype=float), a)

    order = np.argsort(raw, kind="stable")
    sorted_p = raw[order]
    adjusted_sorted = np.empty(m, dtype=float)
    running = 0.0
    for i in range(m):
        running = max(running, min(1.0, sorted_p[i] * (m - i)))
        adjusted_sorted[i] = running

    adjusted = np.empty(m, dtype=float)
    adjusted[order] = adjusted_sorted
    return _build("holm", raw, adjusted, a)


def benjamini_hochberg(p_values: Any, alpha: float = 0.05) -> MultiplicityResult:
    """Benjamini-Hochberg（step-up）校正：控制 FDR。

    回答方案里的哪个问题："探索性切片很多时，允许少量假阳性换取功效，代价怎么算？"
    做法：升序后第 i 个（0 基）取 ``p * m / (i + 1)``，再从**最大**一端做累积最小值，
    保证校正后 p 值随原始 p 值单调不减，最后还原输入顺序。

    Parameters
    ----------
    p_values:
        一维 p 值数组，可空。
    alpha:
        目标 FDR 水平，默认 0.05。

    Returns
    -------
    MultiplicityResult
    """
    a = _validate_alpha(alpha)
    raw = _validate_pvalues(p_values)
    m = raw.size
    if m == 0:
        return _build("bh", raw, np.empty(0, dtype=float), a)

    order = np.argsort(raw, kind="stable")
    sorted_p = raw[order]
    ranks = np.arange(1, m + 1, dtype=float)
    q_sorted = np.minimum(1.0, sorted_p * m / ranks)
    # 从大到小累积最小值：保证 q 随 p 单调不减
    q_sorted = np.minimum.accumulate(q_sorted[::-1])[::-1]

    adjusted = np.empty(m, dtype=float)
    adjusted[order] = q_sorted
    return _build("bh", raw, adjusted, a)


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #
def adjust(p_values: Any, method: str, alpha: float = 0.05) -> MultiplicityResult:
    """按方法名分派到 :func:`bonferroni` / :func:`holm` / :func:`benjamini_hochberg`。

    回答方案里的哪个问题："报告里这一节的校正方法，到底跑的哪一个？" —— 统一入口，
    方法名直接来自配置 ``experiment.multiplicity.method``（``bonferroni`` /
    ``holm`` / ``bh``），不允许多处手写分支导致方法漂移。

    Parameters
    ----------
    p_values:
        一维 p 值数组，可空。
    method:
        ``"bonferroni"`` / ``"holm"`` / ``"bh"``（大小写与首尾空白会被归一化）。
    alpha:
        显著性水平，默认 0.05。

    Returns
    -------
    MultiplicityResult

    Raises
    ------
    ValueError
        未知方法名，或 p 值/alpha 非法。
    TypeError
        参数类型不对。
    """
    if not isinstance(method, str):
        raise TypeError(f"method 必须是字符串，收到 {type(method).__name__}")
    key = method.strip().lower()
    if key not in _METHODS:
        raise ValueError(f"未知的多重比较方法 {method!r}；可选：{list(_METHODS)}")
    if key == "bonferroni":
        return bonferroni(p_values, alpha)
    if key == "holm":
        return holm(p_values, alpha)
    return benjamini_hochberg(p_values, alpha)
