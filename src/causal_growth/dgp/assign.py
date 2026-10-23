"""处理分配：随机实验 vs 观察性选择。

两种分配方式对应项目里两条完全不同的技术主线：

* **主线 A（随机实验）**：``assign_random`` —— ``T ⟂ (Y(0), Y(1))``，
  识别可靠，估计 ITT 即可。这是金标准，也是 Round 1 的内容。
* **主线 B（观察性因果）**：``assign_observational`` —— 运营按可观测特征
  **和未观测因素 U** 挑人，可忽略性被破坏。PSM/IPW/DR 只能平衡可观测 X，
  对 U 无能为力，这就是 Round 2 要量化的偏差来源。

分配是**独立随机流**：同一批用户在不同分配方式下拿到不同 T，
但潜在结果不变——这才能让"同一个真值、不同方法"的对比是干净的。
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.special import expit

from causal_growth.config import Config
from causal_growth.contracts import Population
from causal_growth.dgp.base import calibrate_intercept, coefs_from_section, linear_predictor
from causal_growth.rng import child_rng

__all__ = ["assign_observational", "assign_random", "propensity_scores"]


def assign_random(
    cfg: Config,
    population: Population,
    *,
    index: int = 0,
    treatment_share: float | None = None,
    stream: str = "assign.random",
) -> Population:
    """随机分流：``T ~ Bernoulli(p)``，与潜在结果独立。

    这是 Round 1 的主线。注意 ``population.truth`` **不因分配而改变**，
    因为真值只依赖 p0、p1 与订单经济参数。
    """
    n = len(population)
    share = float(
        cfg.require("experiment.treatment_share") if treatment_share is None else treatment_share
    )
    if not 0.0 < share < 1.0:
        raise ValueError(f"treatment_share 必须在 (0,1) 内，收到 {share}")

    seed = int(cfg.require("project.master_seed"))
    treatment = (child_rng(seed, stream, index).random(n) < share).astype(np.int8)
    face = float(population.truth.face_value)
    return population.assign(treatment, np.where(treatment == 1, face, 0.0))


def propensity_scores(
    cfg: Config,
    population: Population,
    *,
    lam: float,
    alpha_intercept: float | None = None,
) -> tuple[np.ndarray, float]:
    """计算 L3 的真实倾向得分 ``e(X,U) = σ(αᵀX + α₀ + λU)``。

    α₀ 在 **λ=0** 处校准到 ``l3.target_treatment_share``，之后固定不变。
    这样 λ 增大时发券比例会**自然上升**（混淆者更可能被挑中），
    而不是被校准强行拉平——后者会把偏差人为抹掉。

    返回 ``(propensity, alpha_intercept)``。**返回值 e(X,U) 含 U，只用于
    生成数据与审计，估计器只能拿到用 X 拟合的**估计**倾向得分。**
    """
    l3 = cfg.require("dgp.l3")
    alpha_x = coefs_from_section(dict(l3["alpha_x"]))
    lp = linear_predictor(population.covariates, alpha_x, intercept=0.0)

    if "u" not in population.latent:
        raise ValueError("population.latent 中缺少 'u'；请用 build_l3 构造总体")

    if alpha_intercept is None:
        alpha_intercept = calibrate_intercept(lp, float(l3["target_treatment_share"]))

    u = population.latent["u"]
    e = expit(lp + alpha_intercept + float(lam) * u)
    return e, float(alpha_intercept)


def assign_observational(
    cfg: Config,
    population: Population,
    *,
    lam: float,
    index: int = 0,
    stream: str = "assign.obs",
    alpha_intercept: float | None = None,
) -> tuple[Population, float]:
    """观察性分配：``T ~ Bernoulli(e(X,U))``，可忽略性被破坏。

    返回 ``(population, alpha_intercept)``，后者供审计与跨 λ 复现。
    """
    n = len(population)
    e, alpha_intercept = propensity_scores(
        cfg, population, lam=lam, alpha_intercept=alpha_intercept
    )
    seed = int(cfg.require("project.master_seed"))
    draws = child_rng(seed, stream, index).random(n)
    treatment = (draws < e).astype(np.int8)

    face = float(population.truth.face_value)
    population.assign(treatment, np.where(treatment == 1, face, 0.0))
    # 把真实倾向得分存档（只供审计/诊断，估计器不得使用）
    population.latent["true_propensity"] = e
    population.latent["alpha_intercept"] = np.full(n, alpha_intercept)
    return population, alpha_intercept
