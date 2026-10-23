"""ITT（意向处理效应）估计 —— 随机实验主线（方案 §2.4 主线二）。

口径三条，任何一条错了结论就不可信
------------------------------------
1. **估计目标是 ITT，不是 ATT/ATE**。以**随机分配**为准：未领券、未核销的用户
   仍留在实验组。绝不报"领券用户的效果"——那是把随机实验偷换成观察性比较。
2. **分母是随机分配的全部用户**（GOAL.md R1）。未下单用户 ``net_profit = 0``，
   不是被剔除。若按"成功支付订单"建样本，就引入了处理后选择偏差。
3. **主指标是净增量贡献利润**，转化率只是诊断指标，不用于主决策。

为什么 ITT 要配 Welch t 检验而不是等方差 t 检验
-----------------------------------------------
处理组和对照组的利润方差天然不同（处理组多了券成本这一项，且零膨胀结构不同），
等方差假设不成立。Welch 不需要这个假设，代价只是自由度变小。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

__all__ = [
    "ITTResult",
    "auxiliary_metrics",
    "estimate_itt",
    "itt_difference_means",
    "itt_difference_proportions",
    "per_group_summary",
]

#: 主指标（唯一用于主决策）
PRIMARY_METRIC: str = "net_profit_per_user"


@dataclass(frozen=True)
class ITTResult:
    """一次 ITT 估计的完整结果，字段名与报告中的表头一一对应。"""

    metric: str
    mean_treated: float
    mean_control: float
    diff: float
    se: float
    ci_lower: float
    ci_upper: float
    p_value: float
    n_treated: int
    n_control: int
    alpha: float
    method: str

    @property
    def significant(self) -> bool:
        return self.p_value < self.alpha

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "mean_treated": self.mean_treated,
            "mean_control": self.mean_control,
            "diff": self.diff,
            "se": self.se,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "p_value": self.p_value,
            "n_treated": self.n_treated,
            "n_control": self.n_control,
            "alpha": self.alpha,
            "method": self.method,
        }

    def summary_line(self, *, unit: str = "") -> str:
        """报告可直接引用的一行文字。"""
        return (
            f"{self.metric}: 处理组 {self.mean_treated:.4f}{unit} − 对照组 "
            f"{self.mean_control:.4f}{unit} = {self.diff:+.4f}{unit}，"
            f"95% CI [{self.ci_lower:+.4f}, {self.ci_upper:+.4f}]，"
            f"p={self.p_value:.4g}（n={self.n_treated}+{self.n_control}）"
        )


def _split(df: pd.DataFrame, outcome: str, treatment_col: str) -> tuple[np.ndarray, np.ndarray]:
    if treatment_col not in df.columns:
        raise ValueError(f"缺少处理列 {treatment_col!r}")
    if outcome not in df.columns:
        raise ValueError(f"缺少结果列 {outcome!r}")
    t = df[treatment_col].to_numpy()
    y = df[outcome].to_numpy(dtype=float)
    if not np.all(np.isin(t, (0, 1))):
        raise ValueError(f"{treatment_col} 只能取 0/1")
    y_t, y_c = y[t == 1], y[t == 0]
    if y_t.size < 2 or y_c.size < 2:
        raise ValueError(f"每组至少需要 2 个观测：处理组 {y_t.size}，对照组 {y_c.size}")
    return y_t, y_c


def itt_difference_means(
    df: pd.DataFrame,
    outcome: str,
    *,
    treatment_col: str = "treatment",
    alpha: float = 0.05,
    metric: str | None = None,
) -> ITTResult:
    """连续结果的 ITT：Welch 两样本 t 检验 + 正态近似 CI。

    ``diff = mean(T=1) − mean(T=0)``，即方案 §2.3.1 的人均净贡献利润差。
    """
    y_t, y_c = _split(df, outcome, treatment_col)
    n_t, n_c = int(y_t.size), int(y_c.size)
    var_t, var_c = float(np.var(y_t, ddof=1)), float(np.var(y_c, ddof=1))

    diff = float(np.mean(y_t) - np.mean(y_c))
    se = float(np.sqrt(var_t / n_t + var_c / n_c))
    if se == 0.0:
        raise ValueError(f"{outcome} 在两组内方差为 0，无法估计标准误")

    # Welch–Satterthwaite 自由度
    dof = (var_t / n_t + var_c / n_c) ** 2 / (
        (var_t / n_t) ** 2 / (n_t - 1) + (var_c / n_c) ** 2 / (n_c - 1)
    )
    t_crit = float(stats.t.ppf(1.0 - alpha / 2.0, dof))
    p_value = float(2.0 * stats.t.sf(abs(diff / se), dof))

    return ITTResult(
        metric=metric or outcome,
        mean_treated=float(np.mean(y_t)),
        mean_control=float(np.mean(y_c)),
        diff=diff,
        se=se,
        ci_lower=diff - t_crit * se,
        ci_upper=diff + t_crit * se,
        p_value=p_value,
        n_treated=n_t,
        n_control=n_c,
        alpha=alpha,
        method=f"Welch t（df={dof:.1f}）",
    )


def itt_difference_proportions(
    df: pd.DataFrame,
    outcome: str,
    *,
    treatment_col: str = "treatment",
    alpha: float = 0.05,
    metric: str | None = None,
) -> ITTResult:
    """二值结果的 ITT：两比例 z 检验（pooled 方差）与 SE 用非合并方差。

    为什么检验用合并方差、CI 用非合并方差：
    检验的原假设是两组比例相等（合并方差在其下更有效），
    而 CI 要在不假设相等的情况下保持覆盖率（非合并更稳）。
    这是标准做法，报告里会注明。
    """
    y_t, y_c = _split(df, outcome, treatment_col)
    n_t, n_c = int(y_t.size), int(y_c.size)
    p_t, p_c = float(np.mean(y_t)), float(np.mean(y_c))
    diff = p_t - p_c

    se_ci = float(np.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c))
    p_pool = (p_t * n_t + p_c * n_c) / (n_t + n_c)
    se_test = float(np.sqrt(p_pool * (1 - p_pool) * (1.0 / n_t + 1.0 / n_c)))

    if se_ci == 0.0 or se_test == 0.0:
        raise ValueError(f"{outcome} 在两组内取值为常数，无法估计标准误")

    z_crit = float(stats.norm.ppf(1.0 - alpha / 2.0))
    z_stat = diff / se_test
    return ITTResult(
        metric=metric or outcome,
        mean_treated=p_t,
        mean_control=p_c,
        diff=diff,
        se=se_ci,
        ci_lower=diff - z_crit * se_ci,
        ci_upper=diff + z_crit * se_ci,
        p_value=float(2.0 * stats.norm.sf(abs(z_stat))),
        n_treated=n_t,
        n_control=n_c,
        alpha=alpha,
        method="两比例 z 检验（pooled 检验 / unpooled CI）",
    )


def estimate_itt(
    df: pd.DataFrame,
    cfg: Any,
    outcome: str,
    *,
    treatment_col: str = "treatment",
) -> ITTResult:
    """按结果变量类型自动选择方法。

    ``converted`` 这类 0/1 走两比例检验，``net_profit`` / ``gmv`` 走 Welch t。
    """
    alpha = float(cfg.require("experiment.alpha"))
    is_binary = set(np.unique(df[outcome].to_numpy())) <= {0, 1}
    if is_binary:
        return itt_difference_proportions(
            df, outcome, treatment_col=treatment_col, alpha=alpha
        )
    return itt_difference_means(df, outcome, treatment_col=treatment_col, alpha=alpha)


def per_group_summary(df: pd.DataFrame, *, treatment_col: str = "treatment") -> pd.DataFrame:
    """分组描述统计，用于报告的数据概览与平衡性检查。"""
    g = df.groupby(treatment_col, observed=True)
    out = g.agg(
        n=("user_id", "size"),
        conversion_rate=("converted", "mean"),
        net_profit_mean=("net_profit", "mean"),
        net_profit_sd=("net_profit", "std"),
        gmv_mean=("gmv", "mean"),
        refund_rate_among_all=("refunded", "mean"),
        coupon_used_rate=("coupon_used", "mean"),
    )
    out.index = ["对照组", "处理组"]
    return out


def auxiliary_metrics(df: pd.DataFrame, cfg: Any) -> pd.DataFrame:
    """辅助诊断指标（**不用于主决策**）。

    这些指标负责解释"利润为什么变了"，不负责判断"该不该发券"：
    - 转化率增量：分解利润变化的来源
    - 增量 GMV：收入侧
    - 券核销率：成本侧（核销率越高，券成本越实）
    - 退款率：护栏指标，**分母是已转化订单**，不是全部用户

    退款率的分母必须写清：对全部用户算会把转化差异混进退款率里。
    护栏检验用的是"已下单用户中的退款比例"。
    """
    t = df["treatment"].to_numpy() == 1
    conv = df["converted"].to_numpy() == 1
    refund = df["refunded"].to_numpy() == 1
    coupon_used = df["coupon_used"].to_numpy() == 1

    rows: list[dict[str, Any]] = []
    for label, mask in (("对照组", ~t), ("处理组", t)):
        n = int(mask.sum())
        n_conv = int(conv[mask].sum())
        n_redeemed = int(coupon_used[mask].sum())
        rows.append(
            {
                "分组": label,
                "用户数": n,
                "转化用户数": n_conv,
                "转化率": n_conv / n if n else np.nan,
                "券核销用户数": n_redeemed,
                # 口径一：占**已发券**——回答"发出去的券有多少真的被用了"
                "券核销率_占已发券": (n_redeemed / n) if n and label == "处理组" else np.nan,
                # 口径二：占**已下单**——回答"下单的人里有多少用了券"
                # 它受转化率影响，两个口径必须同时报，否则会得出矛盾的数字
                "券核销率_占已下单": (n_redeemed / n_conv) if n_conv else np.nan,
                # 退款率分母是**已转化订单**，不是全部用户
                "退款率_已下单为分母": (int(refund[mask].sum()) / n_conv) if n_conv else np.nan,
                "人均GMV": float(df.loc[mask, "gmv"].mean()),
                "人均净贡献利润": float(df.loc[mask, "net_profit"].mean()),
            }
        )
    return pd.DataFrame(rows)
