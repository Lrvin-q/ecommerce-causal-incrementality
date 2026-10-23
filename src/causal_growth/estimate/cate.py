"""CATE 估计：T-learner / S-learner / Causal Forest（方案 §2.4 主线三）。

三条不可违反的规矩
------------------
1. **训练/验证/测试按用户分离**，绝不重叠（见 ``data.split``）。
   用同一批数据既学 CATE 又评 CATE，会系统性高估效果。
2. **真值只来自 DGP 的解析 τ(x)**，绝不用个体观测利润差 ``pi1 - pi0`` 当真值
   （观测含噪声且反事实不可观测，方案 §2.4 常见坑 6）。
3. **在测试集上评估**，训练集上的 CATE 误差没有意义。

三种方法的区别（面试必问）
--------------------------
* **T-learner**：分别拟合 ``E[Y|X,T=0]`` 与 ``E[Y|X,T=1]`` 再作差。
  灵活，但两组样本量不均时方差差异大；处理效应弱时容易被各自噪声主导。
* **S-learner**：把 T 当成一个普通特征拟合 ``E[Y|X,T]``，再预测 T=0/1 作差。
  样本利用充分，但**正则化会把处理效应一起收缩掉**——当惩罚很强时它会系统性低估 τ。
* **Causal Forest**：局部中心化 + 工具变量式切分，直接对异质性建模。
  通常最准，但慢、且超参敏感。

本项目三种都跑，正是为了展示"为什么选这个方法"而不是"我会用哪个库"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from causal_growth.config import Config
from causal_growth.contracts import FEATURE_ORDER, Population
from causal_growth.data.split import Split
from causal_growth.rng import child_seed

__all__ = ["CATEFit", "design_matrix", "estimate_cate", "CAUSAL_METHODS"]

CAUSAL_METHODS: tuple[str, ...] = ("t_learner", "s_learner", "causal_forest")

#: 连续结果（净贡献利润）与二值结果（是否转化）用不同的基学习器
_CONTINUOUS = "continuous"
_BINARY = "binary"


@dataclass(frozen=True)
class CATEFit:
    """一次 CATE 估计的产物。

    ``tau_*`` 分别对应训练/验证/测试集的预测效应。
    **只有 ``tau_test`` 参与评估**；``tau_train`` 只用于诊断过拟合。
    """

    method: str
    outcome: str
    tau_train: np.ndarray
    tau_val: np.ndarray
    tau_test: np.ndarray
    params: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "outcome": self.outcome,
            "mean_tau_test": float(np.mean(self.tau_test)),
            "sd_tau_test": float(np.std(self.tau_test)),
            "min_tau_test": float(np.min(self.tau_test)),
            "max_tau_test": float(np.max(self.tau_test)),
        }


def design_matrix(population: Population) -> np.ndarray:
    """从总体取特征矩阵。

    刻意复用 ``Covariates.design_matrix()``，而不是从 DataFrame 重新拼一遍——
    这样"模型看到的特征"与"DGP 生成效应用的特征"永远是同一份，不会漂移。
    """
    return population.covariates.design_matrix()


def _outcome_kind(outcome: str) -> str:
    return _BINARY if outcome == "converted" else _CONTINUOUS


def _base_regressor(cfg: Config, *, seed: int) -> Any:
    from lightgbm import LGBMRegressor

    p = cfg.section("estimators.cate.lightgbm_params")
    return LGBMRegressor(random_state=seed, verbose=-1, **p)


def _base_classifier(cfg: Config, *, seed: int) -> Any:
    from lightgbm import LGBMClassifier

    p = cfg.section("estimators.cate.lightgbm_params")
    return LGBMClassifier(random_state=seed, verbose=-1, **p)


def _make_learner(cfg: Config, kind: str, *, seed: int) -> Any:
    return _base_classifier(cfg, seed=seed) if kind == _BINARY else _base_regressor(cfg, seed=seed)


def _predict(learner: Any, X: np.ndarray, kind: str) -> np.ndarray:
    """统一预测接口：二值模型取正类概率，连续模型取点预测。"""
    if kind == _BINARY:
        return learner.predict_proba(X)[:, 1]
    return learner.predict(X)


def _fit_t_learner(
    X: np.ndarray, y: np.ndarray, t: np.ndarray, cfg: Config, kind: str, seed: int
) -> tuple[Any, Any]:
    m1 = _make_learner(cfg, kind, seed=seed)
    m0 = _make_learner(cfg, kind, seed=seed + 1)
    m1.fit(X[t == 1], y[t == 1])
    m0.fit(X[t == 0], y[t == 0])
    return m1, m0


def _fit_s_learner(
    X: np.ndarray, y: np.ndarray, t: np.ndarray, cfg: Config, kind: str, seed: int
) -> Any:
    Xt = np.column_stack([X, t.astype(float)])
    m = _make_learner(cfg, kind, seed=seed)
    m.fit(Xt, y)
    return m


def _s_learner_effect(model: Any, X: np.ndarray, kind: str) -> np.ndarray:
    n = X.shape[0]
    X1 = np.column_stack([X, np.ones(n)])
    X0 = np.column_stack([X, np.zeros(n)])
    return _predict(model, X1, kind) - _predict(model, X0, kind)


def estimate_cate(
    population: Population,
    cfg: Config,
    split: Split,
    *,
    outcome: str = "net_profit",
    method: str = "t_learner",
    seed_index: int = 0,
) -> CATEFit:
    """在给定切分上拟合一种 CATE 估计方法。

    参数
    ----
    population : 必须**已经分配处理**（``treatment`` 不为 None）。
    outcome    : ``"net_profit"``（主指标）或 ``"converted"``（诊断）。
    method     : ``"t_learner"`` / ``"s_learner"`` / ``"causal_forest"``。

    返回
    ----
    ``CATEFit``，其中只有 ``tau_test`` 参与评估。
    """
    if population.treatment is None:
        raise ValueError("population 尚未分配处理")
    if method not in CAUSAL_METHODS:
        raise ValueError(f"未知方法 {method!r}；可用：{CAUSAL_METHODS}")

    X = design_matrix(population)
    t = population.treatment.astype(int)
    y_obs, pi_obs = population.potential.observed(t)
    y = pi_obs if outcome == "net_profit" else y_obs.astype(float)

    kind = _outcome_kind(outcome)
    master_seed = int(cfg.require("project.master_seed"))
    seed = child_seed(master_seed, f"cate.{method}.{outcome}", seed_index)

    X_tr, y_tr, t_tr = X[split.train], y[split.train], t[split.train]
    X_va, X_te = X[split.val], X[split.test]

    if method == "t_learner":
        m1, m0 = _fit_t_learner(X_tr, y_tr, t_tr, cfg, kind, seed)
        tau_tr = _predict(m1, X_tr, kind) - _predict(m0, X_tr, kind)
        tau_va = _predict(m1, X_va, kind) - _predict(m0, X_va, kind)
        tau_te = _predict(m1, X_te, kind) - _predict(m0, X_te, kind)
        params = {"base_learner": "lightgbm", "n_features": X.shape[1],
                  "n_train_treated": int((t_tr == 1).sum()),
                  "n_train_control": int((t_tr == 0).sum())}

    elif method == "s_learner":
        m = _fit_s_learner(X_tr, y_tr, t_tr, cfg, kind, seed)
        tau_tr = _s_learner_effect(m, X_tr, kind)
        tau_va = _s_learner_effect(m, X_va, kind)
        tau_te = _s_learner_effect(m, X_te, kind)
        params = {"base_learner": "lightgbm", "n_features": X.shape[1] + 1,
                  "note": "T 作为普通特征进入模型，正则化会收缩处理效应"}

    else:  # causal_forest
        from econml.dml import CausalForestDML

        cf = cfg.section("estimators.cate.causal_forest_params")
        est = CausalForestDML(
            model_y=_base_regressor(cfg, seed=seed),
            # 处理变量是二值的，第一阶段的 model_t **必须是分类器**。
            # 用回归器去拟合一个 0/1 目标会得到连续预测，DML 的残差正交化就失准
            # （econml 会警告 "First stage model has discrete target but model
            #  is not a classifier!"，这是必须修的真问题，不是噪声）。
            model_t=_base_classifier(cfg, seed=seed + 1),
            discrete_treatment=True,
            n_estimators=cf["n_estimators"],
            min_samples_leaf=cf["min_samples_leaf"],
            max_depth=cf["max_depth"],
            cv=cf["cv"],
            random_state=seed,
        )
        est.fit(y_tr, t_tr, X=X_tr, W=None)
        tau_tr = est.effect(X_tr)
        tau_va = est.effect(X_va)
        tau_te = est.effect(X_te)
        params = {"engine": "econml.CausalForestDML", "n_estimators": cf["n_estimators"],
                  "cv": cf["cv"], "n_features": X.shape[1]}

    return CATEFit(
        method=method,
        outcome=outcome,
        tau_train=np.asarray(tau_tr, dtype=float),
        tau_val=np.asarray(tau_va, dtype=float),
        tau_test=np.asarray(tau_te, dtype=float),
        params={**params, "feature_order": list(FEATURE_ORDER)},
    )
