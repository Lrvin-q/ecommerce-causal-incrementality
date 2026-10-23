"""跨模块数据契约。

为什么单独一个文件
------------------
DGP、利润核算、评估、策略四个模块必须共用**同一套字段名和同一套真值定义**。
本项目最致命的错误是**口径错配**：它不会报错，只会让结论悄悄错掉
（例如一个人把 τ 理解为"实测利润差"，另一个人理解为"条件期望效应"）。

把契约集中在这里，任何字段语义的改动都必须经过这一个文件，便于审阅与复核。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "CONVERT_WINDOW",
    "FEATURE_ORDER",
    "PROFIT_WINDOW",
    "Covariates",
    "GroundTruth",
    "Population",
    "PotentialOutcomes",
]

#: 两个窗口的标识（GOAL.md R2：必须分开，不得混用）
CONVERT_WINDOW: str = "convert_7d"
PROFIT_WINDOW: str = "profit_30d"

#: 线性预测器使用的特征顺序。β / γ / α 系数向量必须按此顺序对齐。
#: 渠道以 one-hot 进入，``other`` 作为基线被去掉（避免哑变量陷阱）。
FEATURE_ORDER: tuple[str, ...] = (
    "is_new",
    "hist_gmv_z",
    "cart_value_z",
    "browse_depth_z",
    "channel_search",
    "channel_feed",
    "channel_xhs",
)


@dataclass(frozen=True)
class Covariates:
    """用户特征 X —— 随机分配时点的快照。

    注意 ``*_z`` 是**标准化后**的版本：DGP 的线性预测器用 z 值，
    这样配置里的系数可以按"每增加 1 个标准差"解释，跨特征可比。
    """

    user_id: np.ndarray
    is_new: np.ndarray
    hist_gmv: np.ndarray
    cart_value: np.ndarray
    browse_depth: np.ndarray
    channel: np.ndarray
    hist_gmv_z: np.ndarray
    cart_value_z: np.ndarray
    browse_depth_z: np.ndarray

    def __len__(self) -> int:
        return int(self.user_id.shape[0])

    def frame(self) -> pd.DataFrame:
        """转成用户级 DataFrame（写入 ``users`` 表与 ``user_events`` 汇总）。"""
        return pd.DataFrame(
            {
                "user_id": self.user_id,
                "is_new": self.is_new.astype(np.int8),
                "hist_gmv": self.hist_gmv,
                "cart_value": self.cart_value,
                "browse_depth": self.browse_depth,
                "channel": pd.Categorical(self.channel),
            }
        )

    def design_matrix(self) -> np.ndarray:
        """返回 ``n × len(FEATURE_ORDER)`` 的设计矩阵，列序严格等于 FEATURE_ORDER。"""
        channel = np.asarray(self.channel)
        return np.column_stack(
            [
                self.is_new.astype(float),
                self.hist_gmv_z,
                self.cart_value_z,
                self.browse_depth_z,
                (channel == "search").astype(float),
                (channel == "feed").astype(float),
                (channel == "xhs").astype(float),
            ]
        )


@dataclass(frozen=True)
class GroundTruth:
    """模拟器真值。**估计器永远不得访问**（这是评估的答案卷）。

    关键区分（方案 §2.4 主线三 / 常见坑 6）：
    ``cate_profit`` 是 **E[Π(1) − Π(0) | X]** 的解析值，
    不是个体实测利润差 ``pi1 - pi0``（后者含噪声且反事实不可观测）。
    用它当真值会把"噪声"算成"方法的误差"。
    """

    level: str
    face_value: float
    #: 潜在转化概率
    p0: np.ndarray
    p1: np.ndarray
    #: 逐用户转化率效应 τ_Y(X) = p1 − p0
    tau_conversion: np.ndarray
    #: 逐用户净增量贡献利润 CATE 的**解析真值**
    cate_profit: np.ndarray
    #: 已转化订单在有/无券下的期望净贡献利润
    net_per_order_treated: np.ndarray
    net_per_order_control: np.ndarray
    #: 生成该真值所用的参数快照（写进报告，保证可追溯）
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def ate_conversion(self) -> float:
        return float(np.mean(self.tau_conversion))

    @property
    def ate_profit(self) -> float:
        return float(np.mean(self.cate_profit))

    def summary(self) -> dict[str, Any]:
        """供报告与 run meta 使用的一行摘要。"""
        return {
            "level": self.level,
            "face_value": self.face_value,
            "ate_conversion": self.ate_conversion,
            "ate_profit_per_user": self.ate_profit,
            "mean_p0": float(np.mean(self.p0)),
            "mean_p1": float(np.mean(self.p1)),
            "mean_net_per_order_control": float(np.mean(self.net_per_order_control)),
            "mean_net_per_order_treated": float(np.mean(self.net_per_order_treated)),
        }


@dataclass(frozen=True)
class PotentialOutcomes:
    """个体潜在结果。

    ``y1 >= y0`` 由 comonotonic coupling 保证（方案 §3.3 L1）：
    用**同一个** U ~ Uniform(0,1) 驱动两个潜在结果，
    ``y0 = 1[U < p0]``、``y1 = 1[U < p1]``，因此 y1 ≥ y0 恒成立，
    且同一用户的两种潜在结果高度相关（避免效应估计被无关噪声淹没）。
    """

    y0: np.ndarray
    y1: np.ndarray
    pi0: np.ndarray
    pi1: np.ndarray

    def observed(self, treatment: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """按实际分配返回可观测结果 ``(Y_obs, Π_obs)``。"""
        t = np.asarray(treatment).astype(bool)
        if t.shape != self.y0.shape:
            raise ValueError(f"treatment 形状 {t.shape} 与潜在结果 {self.y0.shape} 不一致")
        return np.where(t, self.y1, self.y0), np.where(t, self.pi1, self.pi0)

    @property
    def tau_y_realized(self) -> np.ndarray:
        return (self.y1 - self.y0).astype(float)

    @property
    def tau_pi_realized(self) -> np.ndarray:
        return self.pi1 - self.pi0


@dataclass
class Population:
    """一次模拟产生的完整总体。

    ``latent`` 存放**未观测**混淆变量（如 L3 的 U）。它只供真值计算与
    敏感性分析使用，任何估计器都不得读取——这是"观察性因果"实验成立的前提。
    """

    level: str
    index: int
    covariates: Covariates
    truth: GroundTruth
    potential: PotentialOutcomes
    treatment: np.ndarray | None = None
    coupon_value: np.ndarray | None = None
    latent: dict[str, np.ndarray] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.covariates)

    def assign(self, treatment: np.ndarray, coupon_value: np.ndarray | None = None) -> Population:
        """写入随机分配结果（返回自身，便于链式调用）。"""
        self.treatment = np.asarray(treatment).astype(np.int8)
        self.coupon_value = (
            np.zeros(len(self), dtype=float)
            if coupon_value is None
            else np.asarray(coupon_value, dtype=float)
        )
        return self
