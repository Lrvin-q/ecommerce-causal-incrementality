"""成本估计与预算口径（方案 §2.4 主线四）。

为什么 ``c(X)`` 是**期望核销成本**而不是面额
--------------------------------------------
面额 10 元的券，只有用户真的下单并用掉它才产生成本。
所以 ``c(X) = 面额 × P(核销 | 发券, X)``，平均约 0.83 元而不是 10 元。
用面额当成本会高估 12 倍预算占用，直接导致策略过度保守。

两个预算口径（方案要求必须写明用哪一个）
------------------------------------------
* ``expected``：约束 ``E[π(X)c(X)] ≤ B``，保证的是**预期**预算。
  实际支出会有波动，可能超。
* ``hard_cap``：企业要求实际支出**硬上限**。做法是把 c(X) 放大到
  核销概率的高分位（默认 90 分位），预留缓冲。
  代价是同样预算能覆盖的人变少。

**选哪个必须在报告里说清**，因为它改变了"预算能买多少人"这个核心数量。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from causal_growth.config import Config
from causal_growth.rng import child_seed

__all__ = [
    "BudgetBasis",
    "CostModel",
    "compute_expected_cost",
    "fit_redemption_model",
]


@dataclass(frozen=True)
class CostModel:
    """成本模型：把用户特征映射到**每人期望券成本**。"""

    face_value: float
    basis: str
    buffer_quantile: float
    buffer_factor: float
    predicted_redemption: np.ndarray

    def cost(self) -> np.ndarray:
        """返回每人成本（元）。``hard_cap`` 口径已含缓冲放大。"""
        raw = self.face_value * self.predicted_redemption
        if self.basis == "hard_cap":
            return raw * self.buffer_factor
        return raw

    def summary(self) -> dict[str, Any]:
        c = self.cost()
        return {
            "face_value": self.face_value,
            "basis": self.basis,
            "mean_cost": float(c.mean()),
            "median_cost": float(np.median(c)),
            "p90_cost": float(np.quantile(c, 0.9)),
            "max_cost": float(c.max()),
            "buffer_factor": self.buffer_factor,
        }


class BudgetBasis(str):
    """预算口径的字符串常量（expected / hard_cap）。"""


def fit_redemption_model(
    X: np.ndarray,
    coupon_used: np.ndarray,
    treatment: np.ndarray,
    *,
    fit_mask: np.ndarray,
    cfg: Config,
    seed_index: int = 0,
) -> np.ndarray:
    """估计 ``P(核销 | 发券, X)``。

    三件必须做对的事
    ----------------
    1. **只在处理组、且只在训练集上拟合**。用测试集拟合再用测试集评估
       就是数据泄漏；用对照组拟合则根本学不到"发券后会不会用券"。
    2. 核销**必须以有订单为前提**（``data/tables.py`` 已经保证
       ``coupon_used ⇒ converted``），这里不重复判断。
    3. 预测值裁剪到 ``[0, 1]``，避免负数成本。

    返回
    ----
    逐用户的核销概率预测（在**全体**样本上，不只是训练集）。
    """
    from lightgbm import LGBMClassifier

    X = np.asarray(X, dtype=float)
    t = np.asarray(treatment).astype(int)
    used = np.asarray(coupon_used).astype(int)
    mask = np.asarray(fit_mask, dtype=bool)
    if X.shape[0] != t.shape[0] or X.shape[0] != used.shape[0]:
        raise ValueError("X / treatment / coupon_used 长度不一致")

    train = mask & (t == 1)
    if train.sum() < 100:
        raise ValueError(f"训练集处理组只有 {int(train.sum())} 人，不足以拟合核销模型")
    if used[train].sum() < 10:
        raise ValueError("训练集处理组中核销人数过少，无法拟合")

    master = int(cfg.require("project.master_seed"))
    seed = child_seed(master, "policy.redemption_model", seed_index)
    params = dict(cfg.section("estimators.cate.lightgbm_params"))
    params["n_estimators"] = min(int(params.get("n_estimators", 300)), 200)

    if len(np.unique(used[train])) < 2:
        raise ValueError("核销标签只有一类，无法拟合")

    model = LGBMClassifier(random_state=seed, verbose=-1, **params)
    model.fit(X[train], used[train])
    return np.clip(model.predict_proba(X)[:, 1], 0.0, 1.0)


def compute_expected_cost(
    predicted_redemption: np.ndarray,
    *,
    face_value: float,
    cfg: Config,
) -> CostModel:
    """按配置的预算口径把核销概率转成成本。

    ``hard_cap`` 的缓冲因子 = ``q_buffer(p̂) / mean(p̂)``。
    含义：如果实际核销率落在 90 分位，总支出会是多少；
    用这个放大成本，约束就变成"即使按乐观核销率估，也不超预算"。
    """
    basis = str(cfg.require("budget.basis"))
    if basis not in ("expected", "hard_cap"):
        raise ValueError(f"budget.basis 只能是 expected / hard_cap，收到 {basis!r}")
    p = np.asarray(predicted_redemption, dtype=float)
    if p.size == 0:
        raise ValueError("核销概率为空")
    if face_value <= 0:
        raise ValueError(f"券面额必须为正，收到 {face_value}")

    q = float(cfg.require("budget.hard_cap_buffer_quantile"))
    mean_p = float(p.mean())
    if basis == "hard_cap" and mean_p > 0:
        buffer = float(np.quantile(p, q)) / mean_p
    else:
        buffer = 1.0

    return CostModel(
        face_value=float(face_value),
        basis=basis,
        buffer_quantile=q,
        buffer_factor=buffer,
        predicted_redemption=p,
    )
