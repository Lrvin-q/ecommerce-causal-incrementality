r"""四指标评估 —— 方案 §2.4 主线五「评估与验证」。

四件事，四个指标，永不合并
--------------------------
方案 §2.4 主线五原话：**CATE 准不代表排序好，排序好不代表策略价值高，
策略价值高不代表接近最优**。所以本模块把四件事做成四个互不调用的入口：

| 方案里的问题 | 指标 | 本模块入口 |
|---|---|---|
| 效应估计是否准确 | CATE RMSE / MAE / 偏差 / 相关 / R² | :func:`cate_accuracy` |
| 高增量用户能否排前面 | 估计 top-k 与真实 top-k 重合度、Spearman、Kendall τ-b | :func:`ranking_metrics` |
| 实际决策创造多少净增量利润 | V(π) | :func:`policy_value`（仿真）/ :func:`policy_value_observed`（观测） |
| 距真值最优损失多少 | R(π) = V(π*) − V(π) | :func:`regret` |

配套的校准表（:func:`calibration_table`）与自助法标准误（:func:`bootstrap_se`）
只是让上面四个数**能被审阅**，不构成第五个指标。

本模块**刻意不提供**任何 "综合评分 / 加权总分 / 单一排行榜" 函数。一旦把四个量
压成一个数，"RMSE 变差但排序没变""策略价值还行但离最优很远"这类**关键信息**
就被相互抵消了，方案 §2.4 的并列要求直接失守。需要把四个数并排放进一张表时，
请在各 ``scripts/`` 编排层拼表，不要在这里加聚合函数。

口径红线（AGENTS.md §4 / GOAL.md）
---------------------------------
- **R3 券成本只扣一次**：Π^net 里已经包含券核销成本，``policy_value`` / ``regret``
  只对 Π 做加权求均值，**不再二次扣除券成本**（方案 §2.3.4）。预算约束
  ``E[π(X)c(X)] ≤ B`` 是独立的资源约束，不进入 V(π) 的算式。
- **CATE 真值只来自 DGP 解析式**（``GroundTruth.cate_profit``），
  绝不拿个体观测利润差 ``pi1 - pi0`` 当真值（那含噪声且反事实不可观测）。
- **学习与评估必须来自不同 split**：本模块不负责切分，调用方必须保证
  ``tau_hat`` 不是在评估样本上训练出来的（AGENTS.md §4 高频自伤第四条）。

两处刻意保留的数值退化
----------------------
1. ``tau_true`` 无变异时（例如 L0 层 τ 恒为常数），Pearson 相关与 R² 都是 0/0，
   本模块返回 ``nan`` 而不是 1.0 —— 硬给 1.0 会掩盖"真值没有变异，此时
   排序/解释力讨论本身无意义"这一事实。调用方必须显式检查 ``np.isfinite``。
2. ``regret`` 在浮点误差下可能出现 −1e−16 量级，统一 clamp 到 0（见该函数 docstring）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats

from causal_growth.rng import child_rng

__all__ = [
    "CALIBRATION_COLUMNS",
    "CateAccuracy",
    "RankingMetrics",
    "bootstrap_se",
    "calibration_table",
    "cate_accuracy",
    "nonneg_policy",
    "oracle_policy",
    "policy_value",
    "policy_value_observed",
    "ranking_metrics",
    "regret",
    "top_k_policy",
]

#: :func:`calibration_table` 的输出列（顺序固定，报告与 CSV 直接对齐）
CALIBRATION_COLUMNS: tuple[str, ...] = ("bin", "n", "mean_pred", "mean_true", "diff")

#: 自助法支持的两类统计量（只这两类：够用且语义无歧义）
_BOOTSTRAP_STATISTICS: tuple[str, ...] = ("mean", "median")

_NAN = float("nan")


# --------------------------------------------------------------------------- #
# 输入校验：口径错了要立刻响，不能算出一个"看起来合理"的数
# --------------------------------------------------------------------------- #
def _as_float_vector(values: Any, *, name: str) -> np.ndarray:
    """转成一维 float 数组，并拒绝空数组、多维、NaN/Inf。"""
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} 必须是一维数组，收到 {arr.ndim} 维、形状 {arr.shape}")
    if arr.size == 0:
        raise ValueError(f"{name} 不能为空数组")
    if not np.all(np.isfinite(arr)):
        n_bad = int(np.count_nonzero(~np.isfinite(arr)))
        raise ValueError(
            f"{name} 含 {n_bad} 个 NaN/Inf，指标无定义；请先在数据层处理缺失，"
            "不要在这里静默填充（AGENTS.md §3.6 失败要响）"
        )
    return arr


def _require_same_length(first: np.ndarray, *others: tuple[np.ndarray, str], names: str) -> None:
    """校验若干一维数组长度一致。``names`` 只用于报错信息。"""
    size = first.size
    for arr, name in others:
        if arr.size != size:
            raise ValueError(f"{names} 长度不一致：{size} vs {name}={arr.size}（逐用户一一对应）")


def _as_binary_policy(policy: Any, *, name: str = "policy") -> np.ndarray:
    """转成 0/1 的 ``int8`` 数组，并拒绝非法取值。"""
    arr = np.asarray(policy)
    if arr.ndim != 1:
        raise ValueError(f"{name} 必须是一维数组，收到 {arr.ndim} 维、形状 {arr.shape}")
    if arr.size == 0:
        raise ValueError(f"{name} 不能为空数组")
    if arr.dtype == bool:
        return arr.astype(np.int8)
    as_float = np.asarray(arr, dtype=float)
    if not np.all(np.isin(as_float, (0.0, 1.0))):
        bad = np.unique(as_float[~np.isin(as_float, (0.0, 1.0))])[:5]
        raise ValueError(f"{name} 必须只含 0/1，收到非法取值如 {bad.tolist()}（π(X) ∈ {{0,1}}）")
    return as_float.astype(np.int8)


def _validate_top_share(top_share: Any) -> float:
    """``top_share`` 必须是 (0, 1) 内的实数。"""
    numeric = (int, float, np.integer, np.floating)
    if isinstance(top_share, bool) or not isinstance(top_share, numeric):
        raise ValueError(f"top_share 必须是实数，收到 {type(top_share).__name__}")
    share = float(top_share)
    if not (0.0 < share < 1.0):
        raise ValueError(f"top_share 必须落在开区间 (0, 1)，收到 {share}")
    return share


def _top_k_count(n: int, top_share: float) -> int:
    """``k = max(1, round(n * top_share))``，并保证 ``1 ≤ k ≤ n``。

    ``round`` 用 Python 内置的"四舍六入五取偶"（banker's rounding）：
    避免 n·share 恰为 .5 时一律上舍造成的系统上偏；代价是
    ``n=5, top_share=0.5`` 得 k=2。这是口径选择，报告里要写明。
    """
    return max(1, min(n, int(round(n * top_share))))


def _desc_order(values: np.ndarray) -> np.ndarray:
    """按值降序的稳定排序索引：先按值降序，值并列时按**索引升序**。

    并列 tie-break 必须确定，否则同一份 τ̂ 两次运行可能选出不同的 top-k，
    策略价值与 regret 就会"随机"跳动。方案里没有默认顺序，我们把它写死。
    """
    return np.lexsort((np.arange(values.size), -values))


# --------------------------------------------------------------------------- #
# 一、CATE 精度：效应估计是否准确（方案 §2.4 主线五第 1 行）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CateAccuracy:
    """CATE 估计精度的完整体检结果。

    五个字段对应五类失败方式，**都不许单独使用**：

    - ``rmse``：错了多少（对大误差敏感，方案里的主指标）
    - ``mae``：平均错了多少（对离群个体不敏感）
    - ``bias``：``mean(tau_hat - tau_true)``，系统性高估/低估（正=高估）
    - ``correlation``：Pearson，线性一致性；**尺度偏一点仍可能很高**
    - ``r2``：``1 - SSE/SST``，对真值的解释力；为负说明不如"直接猜均值"

    高 RMSE 但高相关 = "整体尺度偏、个体顺序对"；低 RMSE 但 bias 大 =
    "平均而言高估，只是恰好在接近 0 的区域"。两种错法要分开修。
    """

    rmse: float
    mae: float
    bias: float
    correlation: float
    r2: float

    def as_dict(self) -> dict[str, Any]:
        """供报告表与 ``outputs/tables/*.csv`` 使用的一行字典。"""
        return {
            "cate_rmse": self.rmse,
            "cate_mae": self.mae,
            "cate_bias": self.bias,
            "cate_corr": self.correlation,
            "cate_r2": self.r2,
        }


def _is_constant(values: np.ndarray) -> bool:
    """是否所有元素完全相同（用**极差**判定，不用方差）。

    为什么不用方差判零：``[0.05, 0.05, 0.05]`` 的均值在浮点下是
    ``0.05000000000000001``，偏差平方和约 1e−34 —— 不是 0。
    用方差判零会漏掉"真值恒定"这个**最常见的退化场景**（L0 层 τ 恒定），
    然后在 0/0 上算出一个毫无意义的 1.0。极差为 0 才是"没有变异"的准确判据。
    """
    return float(np.ptp(values)) == 0.0


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson 相关；任一侧无变异时返回 ``nan``（0/0 无定义，不臆造 0 或 1）。"""
    if _is_constant(a) or _is_constant(b):
        return _NAN
    da = a - a.mean()
    db = b - b.mean()
    denom = float(np.sqrt(np.sum(da * da) * np.sum(db * db)))
    if denom == 0.0:
        return _NAN
    value = float(np.sum(da * db) / denom)
    # 浮点误差会给出 1.0000000000000002 这种越界值；相关系数按定义在 [−1, 1]，
    # 裁到边界，避免报告里出现"相关系数 1.0000000000000002"。
    return min(1.0, max(-1.0, value))


def cate_accuracy(tau_hat: Any, tau_true: Any) -> CateAccuracy:
    """CATE 精度五件套。

    **回答方案 §2.4 主线五的哪个问题**："效应估计是否准确"——
    ``RMSE = sqrt(E[(τ̂(X) − τ(X))²])``，真值必须用 DGP 解析式
    （``GroundTruth.cate_profit``），**不是**个体实测利润差 ``pi1 - pi0``。

    为什么相关和 R² 不能代替 RMSE：反过来也不成立。
    若 τ̂ = τ + 5（常数平移），RMSE = 5 但相关系数仍是 1 ——
    排序完全正确，只是整体尺度偏了。这种"尺度没问题、顺序有问题"与
    "顺序没问题、尺度有问题"需要完全不同的补救动作（前者重新调参/校准，
    后者只需减去平均偏差），所以必须并列报告。

    退化处理：``tau_true`` 或 ``tau_hat`` 无变异 → ``correlation`` 与 ``r2``
    返回 ``nan``（0/0 无定义）。L0 层 τ 恒定就属于这种情况。

    Parameters
    ----------
    tau_hat, tau_true : array-like
        形状 ``(n,)``，逐用户的 CATE 估计与真值，一一对应。

    Returns
    -------
    CateAccuracy

    Raises
    ------
    ValueError
        长度不一致、空数组、非一维、含 NaN/Inf。
    """
    hat = _as_float_vector(tau_hat, name="tau_hat")
    true = _as_float_vector(tau_true, name="tau_true")
    _require_same_length(hat, (true, "tau_true"), names="tau_hat 与 tau_true")

    err = hat - true
    sse = float(np.sum(err * err))
    sst = float(np.sum((true - true.mean()) ** 2))
    # 真值无变异 → R² 是 0/0，返回 nan（见模块文档"两处刻意保留的数值退化"）
    r2 = _NAN if (_is_constant(true) or sst == 0.0) else float(1.0 - sse / sst)

    return CateAccuracy(
        rmse=float(np.sqrt(np.mean(err * err))),
        mae=float(np.mean(np.abs(err))),
        bias=float(np.mean(err)),
        correlation=_pearson(hat, true),
        r2=r2,
    )


# --------------------------------------------------------------------------- #
# 二、排序：高增量用户能否排前面（方案 §2.4 主线五第 2 行）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RankingMetrics:
    """排序质量三件套 + 口径回执。

    - ``top_overlap``：估计 top-k 与真实 top-k 的交集 / k。这是**策略视角**
      的指标——真正决定预算花在谁身上的就是这 k 个人。
    - ``spearman``：全样本秩相关，衡量整体排序。
    - ``kendall``：Kendall τ-b（处理并列），衡量两两对的顺序一致率。
    - ``k`` / ``top_share``：口径回执，保证数字可追溯（报告必须同时写 k）。
    """

    top_overlap: float
    spearman: float
    kendall: float
    k: int
    top_share: float

    def as_dict(self) -> dict[str, Any]:
        """供报告表与 ``outputs/tables/*.csv`` 使用的一行字典。"""
        return {
            "rank_top_overlap": self.top_overlap,
            "rank_spearman": self.spearman,
            "rank_kendall": self.kendall,
            "rank_k": self.k,
            "rank_top_share": self.top_share,
        }


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman 秩相关（scipy）；任一侧无变异时返回 ``nan``。"""
    if _is_constant(a) or _is_constant(b):
        return _NAN
    return float(stats.spearmanr(a, b).statistic)


def _kendall(a: np.ndarray, b: np.ndarray) -> float:
    """Kendall τ-b（scipy，处理并列）；任一侧无变异时返回 ``nan``。"""
    if _is_constant(a) or _is_constant(b):
        return _NAN
    return float(stats.kendalltau(a, b, variant="b").statistic)


def ranking_metrics(tau_hat: Any, tau_true: Any, *, top_share: float = 0.20) -> RankingMetrics:
    """排序质量：top-k 重合度 + Spearman + Kendall τ-b。

    **回答方案 §2.4 主线五的哪个问题**："高增量用户能否排前面"。
    方案原文点名 top-20% 重合度与 Spearman，Kendall 作为"两两顺序一致率"
    的补充（对并列更宽容，且与 top-k 决策的解释更直接）。

    为什么排序指标不能由 RMSE 推出来：RMSE 由**全体**用户的误差决定，
    而策略只花在**头部** k 个人身上。常数平移或尾部噪声都能把 RMSE 拉高，
    却完全不动排序；反过来，头部少数人排错对 RMSE 影响很小，对策略价值打击很大。

    口径约定：

    - ``k = max(1, round(n * top_share))``，``top_share ∈ (0, 1)``；
    - 排序用**稳定 tie-break**：先按值降序、值并列时按索引升序，
      同一份输入必然得到同一组 top-k；
    - 秩相关用 ``scipy.stats``（Spearman 与 Kendall τ-b）；
    - 任一侧无变异时秩相关返回 ``nan``。

    Parameters
    ----------
    tau_hat, tau_true : array-like
        形状 ``(n,)``，逐用户 CATE 估计与真值。
    top_share : float, default 0.20
        头部比例，统计惯例取 0.20（方案 §2.4 主线五的 top-20%）。

    Returns
    -------
    RankingMetrics

    Raises
    ------
    ValueError
        ``top_share`` 不在 (0, 1)、长度不一致、空数组、非一维、含 NaN/Inf。
    """
    hat = _as_float_vector(tau_hat, name="tau_hat")
    true = _as_float_vector(tau_true, name="tau_true")
    _require_same_length(hat, (true, "tau_true"), names="tau_hat 与 tau_true")
    share = _validate_top_share(top_share)

    n = hat.size
    k = _top_k_count(n, share)
    top_hat = set(_desc_order(hat)[:k].tolist())
    top_true = set(_desc_order(true)[:k].tolist())
    overlap = float(len(top_hat & top_true) / k)

    return RankingMetrics(
        top_overlap=overlap,
        spearman=_spearman(hat, true),
        kendall=_kendall(hat, true),
        k=k,
        top_share=share,
    )


# --------------------------------------------------------------------------- #
# 校准表：让上面两个数字"可被审阅"，它本身不是新指标
# --------------------------------------------------------------------------- #
def calibration_table(tau_hat: Any, tau_true: Any, *, n_bins: int = 10) -> pd.DataFrame:
    """CATE 校准表：分箱后比较"模型说多少"与"实际多少"。

    **回答方案 §2.4 主线五的哪个问题**："效应估计是否准确"的**诊断版**——
    RMSE 只告诉你错了多少，校准表告诉你**错在哪里**：是高分箱整体高估
    （常见于树模型/森林的极端分箱），还是低分箱整体低估（收缩偏置）。

    按 ``tau_hat`` 的**分位数**分箱而不是等宽分箱：CATE 分布通常偏斜，
    等宽分箱会让绝大部分样本挤在少数几箱里，每箱 n 太小、均值噪声比信号大。

    列（顺序固定，见 ``CALIBRATION_COLUMNS``）：

    - ``bin``：分箱区间标签（``pd.cut`` 生成的右闭左开区间 ``(a, b]``，最左端点
      由 ``include_lowest`` 纳入；全部取值相同时退化为单箱 ``[min, max]``）
    - ``n``：该箱样本数
    - ``mean_pred``：``tau_hat`` 箱内均值
    - ``mean_true``：``tau_true`` 箱内均值
    - ``diff``：``mean_pred - mean_true``，恒等式保证 ``diff == mean_pred - mean_true``

    并列值很多时（例如 τ̂ 有大量相同取值）分位数边界会重复，
    去重后可用的箱数**少于** ``n_bins``；全部取值相同时只有 1 箱。

    Parameters
    ----------
    tau_hat, tau_true : array-like
    n_bins : int, default 10
        目标箱数；实际箱数 ≤ ``n_bins``。

    Returns
    -------
    pandas.DataFrame
        列见上；行数 ≤ ``n_bins``，按 ``bin`` 升序（即 τ̂ 分位数升序）。
    """
    hat = _as_float_vector(tau_hat, name="tau_hat")
    true = _as_float_vector(tau_true, name="tau_true")
    _require_same_length(hat, (true, "tau_true"), names="tau_hat 与 tau_true")
    if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)):
        raise ValueError(f"n_bins 必须是整数，收到 {type(n_bins).__name__}")
    bins = int(n_bins)
    if bins < 1:
        raise ValueError(f"n_bins 必须 >= 1，收到 {bins}")

    frame = pd.DataFrame({"tau_hat": hat, "tau_true": true})
    edges = np.unique(np.quantile(hat, np.linspace(0.0, 1.0, bins + 1)))
    if edges.size < 2:  # 全部 tau_hat 相同：退化成一箱
        frame["bin"] = f"[{float(hat.min()):.4g}, {float(hat.max()):.4g}]"
    else:
        frame["bin"] = pd.cut(hat, bins=edges, include_lowest=True, duplicates="drop")

    grouped = frame.groupby("bin", observed=True, sort=True)
    out = pd.DataFrame(
        {
            "n": grouped.size().astype(np.int64),
            "mean_pred": grouped["tau_hat"].mean(),
            "mean_true": grouped["tau_true"].mean(),
        }
    ).reset_index()
    out["diff"] = out["mean_pred"] - out["mean_true"]
    out["bin"] = out["bin"].astype(str)
    return out.loc[:, list(CALIBRATION_COLUMNS)].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 三、策略价值：实际决策创造多少净增量利润（方案 §2.4 主线五第 3 行）
# --------------------------------------------------------------------------- #
def policy_value(policy: Any, *, pi1: Any, pi0: Any) -> float:
    """已知潜在结果下的策略价值：``V(π) = mean(π(X)·Π(1) + (1−π(X))·Π(0))``。

    **回答方案 §2.4 主线五的哪个问题**："实际决策创造多少净增量利润"。
    **回答方案 §2.3.4 的重复扣减问题**：Π 已经是**净**贡献利润（含券核销成本），
    这里只做加权平均，**不再减券成本**，也不减预算——预算约束
    ``E[π(X)c(X)] ≤ B`` 是独立的资源约束（R3）。

    只能在仿真里用（需要 Π(1)/Π(0) 两个潜在结果）。真实业务请用
    :func:`policy_value_observed`。

    口径提示——两个"策略价值"定义差一个常数，报告必须注明用哪个：

    - 本函数（任务规格）：**绝对水平** ``mean(π·Π(1) + (1−π)·Π(0))``，
      不发券策略的取值是 ``mean(Π(0))``，不是 0；
    - 方案 §2.3.4：**增量口径** ``V(π) = E[π(X)τ_Π(X)]``，不发券策略取 0。

    两者只差 ``E[Π(0)]``（对所有用户相同的加性常数），所以策略之间的排序与
    :func:`regret` **完全不受口径选择影响**；但绝对数值不能混着比。

    Returns
    -------
    float
        逐用户加权平均后的净贡献利润（单位：元/人）。
    """
    pi = _as_binary_policy(policy)
    treated = _as_float_vector(pi1, name="pi1")
    control = _as_float_vector(pi0, name="pi0")
    _require_same_length(
        pi, (treated, "pi1"), (control, "pi0"), names="policy 与 pi1/pi0"
    )
    return float(np.mean(np.where(pi == 1, treated, control)))


def policy_value_observed(
    policy: Any,
    *,
    y_obs: Any,
    treatment: Any,
    propensity: Any | None = None,
) -> float:
    """只有观测数据时的策略价值估计（IPTW 形式）。

    **回答方案 §2.4 主线五的哪个问题**："实际决策创造多少净增量利润"——
    但这是**真实业务路径**的版本：业务里看不到 Π(1)/Π(0)，
    每个用户只留下 ``y_obs = T·Π(1) + (1−T)·Π(0)``。

    估计量
    ------
    用逆概率加权把每个用户"补出"另一个反事实：

    .. code-block:: text

        V̂(π) = (1/n) Σ_i [ π_i · T_i · y_i / ê_i  +  (1−π_i) · (1−T_i) · y_i / (1−ê_i) ]

    它是对 ``V(π) = E[πΠ(1) + (1−π)Π(0)]`` 的 Horvitz–Thompson 型无偏估计
    （在随机化/可忽略性 + 重叠性下），原因是
    ``E[T·y/ê] = E[Π(1)]``、``E[(1−T)·y/(1−ê)] = E[Π(0)]``。
    归一化用 **1/n**（不是 1/n_1 或 1/n_0），这样它和 :func:`policy_value`
    落在同一把尺子上（都是"全体用户的人均利润"），可以直接对照。

    倾向得分从哪来
    --------------
    - ``propensity=None``（默认）：用**观测到的分配比例** ``mean(T)`` 作为常数
      倾向得分。这是**随机实验口径**——与本项目 ITT 主线一致（发券由随机
      分流决定，ê 由设计给出，而不是由模型估出来）。
    - 给了 ``propensity``：按逐用户倾向得分加权，供 L3 观察性场景
      （PSM/IPW/DR 那一路）使用。此时 ê 是估出来的，权重可能极端，
      估计量的方差会明显变大；本函数只给点估计，**不报标准误**。

    与 :func:`policy_value` 的差别要说清：本函数是**估计量**（有抽样误差），
    ``policy_value`` 是**真值**（仿真里直接算）。两者的差就是"观测路径的代价"。

    Parameters
    ----------
    policy : array-like
        0/1 策略向量。
    y_obs : array-like
        逐用户观测到的净贡献利润（未处理者亦可为 0 或负）。
    treatment : array-like
        0/1 实际分配。
    propensity : array-like or None, default None
        倾向得分；``None`` 时取 ``mean(treatment)``。

    Returns
    -------
    float
        估计的 ``V(π)``（元/人）。

    Raises
    ------
    ValueError
        长度不一致、policy/treatment 非 0/1、只剩单一处理臂（无重叠）、
        倾向得分不在 (0, 1) 内、含 NaN/Inf。
    """
    pi = _as_binary_policy(policy)
    y = _as_float_vector(y_obs, name="y_obs")
    t = _as_binary_policy(treatment, name="treatment")
    _require_same_length(
        pi, (y, "y_obs"), (t, "treatment"), names="policy 与 y_obs/treatment"
    )
    n = pi.size

    if propensity is None:
        share = float(np.mean(t))
        if share <= 0.0 or share >= 1.0:
            raise ValueError(
                "treatment 只有单一取值（全 0 或全 1），反事实一侧没有观测，"
                "策略价值不可识别（重叠性不成立）"
            )
        weight_treated = 1.0 / share
        weight_control = 1.0 / (1.0 - share)
    else:
        e = _as_float_vector(propensity, name="propensity")
        _require_same_length(pi, (e, "propensity"), names="policy 与 propensity")
        if not np.all((e > 0.0) & (e < 1.0)):
            raise ValueError("propensity 必须严格落在 (0, 1) 内（重叠性），收到越界取值")
        weight_treated = 1.0 / e
        weight_control = 1.0 / (1.0 - e)

    treated_part = pi.astype(float) * t.astype(float) * y * weight_treated
    control_part = (1.0 - pi) * (1.0 - t) * y * weight_control
    return float(np.sum(treated_part + control_part) / n)


def regret(policy: Any, policy_star: Any, *, pi1: Any, pi0: Any) -> float:
    """策略遗憾：``R(π) = V(π*) − V(π)``，恒 ≥ 0（``π*`` 为真值最优时）。

    **回答方案 §2.4 主线五的哪个问题**："距真值最优损失多少"。
    这是唯一能把"策略价值高"和"接近最优"区分开的指标：
    V(π) 可以很漂亮，但如果 π* 还能再多赚一截，R(π) 就把这段差距量化出来。

    数值误差处理：理论上 ``R ≥ 0``，但浮点减法可能给出 ``−1e−16`` 量级；
    本函数 **clamp 到 0**。因此 R = 0 意味着"在浮点精度内已达到或超过 π*"，
    若 π 真的优于 π*，请先检查 ``policy_star`` 是否由
    :func:`oracle_policy` 在同一份真值上生成。

    口径不变性：:func:`policy_value` 用绝对水平口径（含 ``mean(Π(0))``），
    方案 §2.3.4 用增量口径（``E[πτ]``），两种口径差一个常数 ``E[Π(0)]``，
    **regret 的数值完全相同**。这也是为什么 regret 适合做跨实验比较。

    Parameters
    ----------
    policy, policy_star : array-like
        0/1 策略向量，长度一致。
    pi1, pi0 : array-like
        逐用户潜在净贡献利润（Π 已含券成本，R3）。

    Returns
    -------
    float
        每用户平均损失（元/人），≥ 0。
    """
    value = policy_value(policy, pi1=pi1, pi0=pi0)
    best = policy_value(policy_star, pi1=pi1, pi0=pi0)
    return max(0.0, float(best - value))


# --------------------------------------------------------------------------- #
# 策略构造：上界与两个"可交付策略"的对照物
# --------------------------------------------------------------------------- #
def oracle_policy(tau_true: Any, *, top_share: float | None = None) -> np.ndarray:
    """真值最优策略（上界）：按真实 τ 从大到小发券。

    **回答方案 §2.4 主线五的哪个问题**：给 :func:`regret` 提供 ``π*``，
    也就是"如果一开始就知道真值，最好能做成什么样"。这不是可交付策略，
    是**上界**，只允许出现在评估侧，绝不能进模型输入。

    - ``top_share=None``：选 ``τ > 0`` 的全部用户（不设预算约束时的最优）。
    - ``top_share=s``：选真实 τ 最高的前 ``max(1, round(n·s))`` 人，
      tie-break 与 :func:`top_k_policy` 一致（值降序、索引升序），保证可复现。

    Returns
    -------
    numpy.ndarray
        ``int8`` 的 0/1 数组。
    """
    tau = _as_float_vector(tau_true, name="tau_true")
    if top_share is None:
        return (tau > 0.0).astype(np.int8)
    share = _validate_top_share(top_share)
    k = _top_k_count(tau.size, share)
    policy = np.zeros(tau.size, dtype=np.int8)
    policy[_desc_order(tau)[:k]] = 1
    return policy


def top_k_policy(tau_hat: Any, *, top_share: float = 0.20) -> np.ndarray:
    """按 τ̂ 的 top-k 发券（固定人数、不设预算约束的简单策略）。

    **回答方案 §2.4 主线四/五的哪个问题**：这是"定向-贪心/背包"之前最简单
    的定向基准——固定覆盖前 k 比例的人。它与 :func:`oracle_policy` 的差距
    直接体现**排序质量**，从而把"排序差"和"策略差"两件事连起来看。

    tie-break 与 :func:`ranking_metrics` 完全一致（值降序、索引升序），
    所以 ``top_overlap`` 的 k 与这里选中的 k 是同一个人群口径。

    Returns
    -------
    numpy.ndarray
        ``int8`` 的 0/1 数组。
    """
    tau = _as_float_vector(tau_hat, name="tau_hat")
    share = _validate_top_share(top_share)
    k = _top_k_count(tau.size, share)
    policy = np.zeros(tau.size, dtype=np.int8)
    policy[_desc_order(tau)[:k]] = 1
    return policy


def nonneg_policy(tau_hat: Any) -> np.ndarray:
    """按 ``τ̂ > 0`` 发券（不设预算约束的"能赚就发"策略）。

    **回答方案 §2.4 主线四的哪个问题**：预算不是硬约束时的自然策略，
    也是"不发券 / 全量 / 定向"六策略对比里最朴素的定向版本。
    它和 :func:`oracle_policy` 的差距同样只来自 τ̂ 的符号判错。

    Returns
    -------
    numpy.ndarray
        ``int8`` 的 0/1 数组。
    """
    tau = _as_float_vector(tau_hat, name="tau_hat")
    return (tau > 0.0).astype(np.int8)


# --------------------------------------------------------------------------- #
# 自助法标准误：让上面四个数带上"这个数字有多稳"
# --------------------------------------------------------------------------- #
def bootstrap_se(
    values: Any,
    *,
    n_boot: int = 200,
    statistic: Literal["mean", "median"] = "mean",
    master_seed: int,
    stream: str = "metrics.bootstrap",
    index: int = 0,
) -> float:
    """自助法（bootstrap）标准误，衡量一个统计量有多稳。

    **回答方案 §2.4 主线五的哪个问题**：四指标都是**估计量**，
    报告里必须同时给出不确定性（方案 §5 的覆盖率/误差要求同理）。
    例如 L3 观察性路径下的策略价值、逐用户 τ̂ 误差的均值，
    都需要一个标准误才能判断"两个方法的差距是不是噪声"。

    统计量
    ------
    ``statistic="mean"``（默认）：样本均值（最常用：人均效应、人均价值）。
    ``statistic="median"``：样本中位数（对极端值稳健，适合利润这种重尾指标）。

    返回的是**自助分布的标准差**（``ddof=1``），即统计量的标准误，
    不是百分位置信区间的半宽。

    随机性
    ------
    只用 ``causal_growth.rng.child_rng`` 派生随机流：
    ``(master_seed, stream, index)`` 相同 → 结果**逐位相同**（可复现）。
    在重复实验里用 ``index=rep`` 让每次重复各有一条流。

    Parameters
    ----------
    values : array-like
        一维样本（如逐用户的 τ̂ 误差、逐用户的策略收益）。不是通用自助框架。
    n_boot : int, default 200
        自助次数，统计惯例 200 起；报告要求更稳时可上调。
    statistic : {"mean", "median"}
    master_seed : int
        主种子（必填，禁止隐式随机）。
    stream : str, default "metrics.bootstrap"
    index : int, default 0
        流内序号，与 ``stream`` 一起决定随机序列。

    Returns
    -------
    float
        统计量的自助标准误。

    Raises
    ------
    ValueError
        样本少于 2 个、``n_boot < 2``、未知 ``statistic``、含 NaN/Inf。
    """
    arr = _as_float_vector(values, name="values")
    if arr.size < 2:
        raise ValueError(f"自助法至少需要 2 个观测，收到 {arr.size} 个")
    if isinstance(n_boot, bool) or not isinstance(n_boot, (int, np.integer)):
        raise ValueError(f"n_boot 必须是整数，收到 {type(n_boot).__name__}")
    if int(n_boot) < 2:
        raise ValueError(f"n_boot 必须 >= 2（ddof=1 需要至少两次重抽样），收到 {n_boot}")
    if statistic not in _BOOTSTRAP_STATISTICS:
        raise ValueError(f"statistic 只支持 {_BOOTSTRAP_STATISTICS}，收到 {statistic!r}")

    rng = child_rng(master_seed=master_seed, stream=stream, index=index)
    n = arr.size
    draws = np.empty(int(n_boot), dtype=float)
    for b in range(int(n_boot)):
        sample = arr[rng.integers(0, n, size=n)]
        draws[b] = float(np.mean(sample)) if statistic == "mean" else float(np.median(sample))
    return float(np.std(draws, ddof=1))
