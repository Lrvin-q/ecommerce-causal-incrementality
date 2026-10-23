"""观察性因果：naive / PSM / IPW / DR（方案 §2.4 主线三）。

为什么这四种要放在一起对比
--------------------------
它们的**识别假设强弱不同**，代价也不同：

| 方法 | 需要的假设 | 弱点 |
|---|---|---|
| Naive 差分 | 无（但它估的不是因果效应） | 只要有选择偏差就全错 |
| PSM | 可忽略性（给定 X） | 只能平衡**可观测** X；匹配会丢样本 |
| IPW | 可忽略性 + 正性（重叠） | 倾向得分接近 0/1 时权重爆炸，方差失控 |
| DR | 可忽略性（其中一模型正确即可） | 双稳健，但两个模型都错时仍偏 |

本项目用 L3 的 ``λ`` 旋钮破坏可忽略性：``U`` 是未观测混淆。
**PSM/IPW/DR 只能平衡可观测的 X，对 U 无能为力**——这才是要量化的东西。

口径提醒
--------
* 全部方法估计的都是**人均净增量贡献利润** ``E[Π(1)−Π(0)]``。
* 退款单保留、券成本只扣一次——这两条由 ``data.profit`` 保证，
  估计器只消费 ``net_profit`` 列，不得自己再算一遍利润。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from causal_growth.config import Config

__all__ = [
    "OBS_METHODS",
    "ObsEstimate",
    "dr_estimate",
    "estimate_all",
    "fit_propensity",
    "ipw_estimate",
    "naive_difference",
    "psm_estimate",
    "standardized_mean_diff",
]

OBS_METHODS: tuple[str, ...] = ("naive", "psm", "ipw", "dr")


@dataclass(frozen=True)
class ObsEstimate:
    """一次观察性估计的结果与诊断。"""

    method: str
    estimate: float
    se: float
    ci_lower: float
    ci_upper: float
    n_treated: int
    n_control: int
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def covered_zero(self) -> bool:
        return self.ci_lower <= 0.0 <= self.ci_upper

    def as_row(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "estimate": self.estimate,
            "se": self.se,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "n_treated": self.n_treated,
            "n_control": self.n_control,
        }


def _check_inputs(y: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float)
    t = np.asarray(t)
    if y.shape != t.shape:
        raise ValueError(f"y 与 t 长度不一致：{y.shape} vs {t.shape}")
    if not np.all(np.isin(np.unique(t), (0, 1))):
        raise ValueError("t 只能取 0/1")
    if np.isnan(y).any():
        raise ValueError("y 含 NaN——未被处理的用户净贡献利润应记 0，不是 NaN")
    if (t == 1).sum() < 2 or (t == 0).sum() < 2:
        raise ValueError("每组至少需要 2 个观测")
    return y, t.astype(int)


def _ci(estimate: float, se: float, alpha: float) -> tuple[float, float]:
    z = float(stats.norm.ppf(1.0 - alpha / 2.0))
    return estimate - z * se, estimate + z * se


# --------------------------------------------------------------------------- #
# Naive
# --------------------------------------------------------------------------- #
def naive_difference(y: np.ndarray, t: np.ndarray, *, alpha: float = 0.05) -> ObsEstimate:
    """朴素差分 ``mean(y|T=1) − mean(y|T=0)``。

    它**不是因果效应**：只要处理组与对照组在潜在结果上不同（选择偏差），
    这个数就把"本来就不同"混进了"处理效应"。作为偏差参照系使用。
    """
    y, t = _check_inputs(y, t)
    y1, y0 = y[t == 1], y[t == 0]
    diff = float(y1.mean() - y0.mean())
    se = float(np.sqrt(y1.var(ddof=1) / y1.size + y0.var(ddof=1) / y0.size))
    lo, hi = _ci(diff, se, alpha)
    return ObsEstimate(
        method="naive", estimate=diff, se=se, ci_lower=lo, ci_upper=hi,
        n_treated=int(y1.size), n_control=int(y0.size),
        diagnostics={"note": "未做任何调整，选择偏差全部混入估计"},
    )


# --------------------------------------------------------------------------- #
# 倾向得分
# --------------------------------------------------------------------------- #
def fit_propensity(X: np.ndarray, t: np.ndarray, *, clip: float = 1e-3) -> np.ndarray:
    """Logistic 回归估计倾向得分 ``e(X)=P(T=1|X)``。

    只用到**可观测** X —— 这正是 PSM/IPW/DR 在 L3 下会失效的根源：
    U 不可观测，无法进入 X，所以 e(X) 估的不是真正的 e(X,U)。
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    X = np.asarray(X, dtype=float)
    t = np.asarray(t).astype(int)
    if X.ndim != 2 or X.shape[0] != t.shape[0]:
        raise ValueError(f"X 形状 {X.shape} 与 t 长度 {t.shape[0]} 不匹配")

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(max_iter=2000, C=1.0)
    model.fit(Xs, t)
    e = model.predict_proba(Xs)[:, 1]
    return np.clip(e, clip, 1.0 - clip)


def standardized_mean_diff(X: np.ndarray, t: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    """标准化均值差（SMD），逐特征。

    ``SMD = (m1 − m0) / sqrt((s1² + s0²)/2)``，加权版本用于 IPW 后的平衡诊断。
    经验阈值：|SMD| < 0.1 视为平衡。
    """
    X = np.asarray(X, dtype=float)
    t = np.asarray(t).astype(bool)
    w = np.ones_like(t, dtype=float) if w is None else np.asarray(w, dtype=float)

    def _wmean(Xg: np.ndarray, wg: np.ndarray) -> np.ndarray:
        return np.average(Xg, axis=0, weights=wg)

    def _wvar(Xg: np.ndarray, wg: np.ndarray, mu: np.ndarray) -> np.ndarray:
        return np.average((Xg - mu) ** 2, axis=0, weights=wg)

    X1, w1 = X[t], w[t]
    X0, w0 = X[~t], w[~t]
    mu1, mu0 = _wmean(X1, w1), _wmean(X0, w0)
    v1, v0 = _wvar(X1, w1, mu1), _wvar(X0, w0, mu0)
    denom = np.sqrt((v1 + v0) / 2.0)
    denom = np.where(denom > 0, denom, 1.0)
    return (mu1 - mu0) / denom


# --------------------------------------------------------------------------- #
# IPW
# --------------------------------------------------------------------------- #
def ipw_estimate(
    y: np.ndarray,
    t: np.ndarray,
    e: np.ndarray,
    *,
    alpha: float = 0.05,
    clip_quantile: float = 0.99,
) -> ObsEstimate:
    """逆概率加权（Hájek 归一化版本 + 权重截断）。

    为什么用 Hájek 而不是 Horvitz–Thompson：
    HT 在权重和偏离期望时会给出 >1 的"比例"或巨大方差；Hájek 用加权均值归一化，
    在估计 ``E[Y(1)]−E[Y(0)]`` 时更稳，代价是轻微的小样本偏。

    为什么必须截断：``e`` 接近 0/1 时单个样本能主导整个估计。
    截断到 ``clip_quantile`` 分位，并在诊断里报告被截断的比例——
    **截断本身引入偏差**，报告必须披露，不能悄悄做。
    """
    y, t = _check_inputs(y, t)
    e = np.asarray(e, dtype=float)
    if e.shape != y.shape:
        raise ValueError("e 与 y 长度不一致")
    if np.any(e <= 0) or np.any(e >= 1):
        raise ValueError("倾向得分必须严格落在 (0,1)")

    cut = float(np.quantile(e, clip_quantile))
    e_clipped = np.minimum(e, cut)
    n_clipped = int(np.sum(e > cut))

    w1 = t / e_clipped
    w0 = (1 - t) / (1 - e_clipped)

    mu1 = float(np.sum(w1 * y) / np.sum(w1))
    mu0 = float(np.sum(w0 * y) / np.sum(w0))
    diff = mu1 - mu0

    # 影响函数标准误（Hájek 形式）
    n = y.size
    if1 = w1 * (y - mu1) / np.mean(w1)
    if0 = w0 * (y - mu0) / np.mean(w0)
    se = float(np.sqrt((np.var(if1, ddof=1) + np.var(if0, ddof=1)) / n))

    lo, hi = _ci(diff, se, alpha)
    ess = float((w1.sum() ** 2) / (w1**2).sum() + (w0.sum() ** 2) / (w0**2).sum())
    return ObsEstimate(
        method="ipw", estimate=diff, se=se, ci_lower=lo, ci_upper=hi,
        n_treated=int(t.sum()), n_control=int((1 - t).sum()),
        diagnostics={
            "ess_total": ess,
            "max_weight": float(max(w1.max(), w0.max())),
            "n_e_clipped": n_clipped,
            "clip_quantile": clip_quantile,
            "weight_clip_note": f"{n_clipped} 个倾向得分被截断（引入偏差，需披露）",
        },
    )


# --------------------------------------------------------------------------- #
# DR（AIPW）
# --------------------------------------------------------------------------- #
def dr_estimate(
    y: np.ndarray,
    t: np.ndarray,
    e: np.ndarray,
    X: np.ndarray,
    cfg: Config,
    *,
    alpha: float = 0.05,
    seed: int = 0,
) -> ObsEstimate:
    """双稳健（AIPW）估计。

    ``τ = E[ μ1(X) − μ0(X) + T(Y−μ1(X))/e − (1−T)(Y−μ0(X))/(1−e) ]``

    双稳健的含义：倾向得分模型与结果模型**只要有一个对**，估计就一致。
    但两个都错时会偏——L3 里遗漏的 U 同时进入两个模型，所以两个都错。

    标准误用影响函数：``sd(τ_i)/sqrt(n)``，其中 τ_i 是括号内那一项。
    """
    from lightgbm import LGBMRegressor

    y, t = _check_inputs(y, t)
    e = np.asarray(e, dtype=float)
    X = np.asarray(X, dtype=float)
    if not (e.shape == y.shape and X.shape[0] == y.shape[0]):
        raise ValueError("y / t / e / X 长度不一致")

    params = cfg.section("estimators.cate.lightgbm_params")
    params = dict(params)
    # DR 在 λ 扫描里要被调用 7×20 次，必须压小；200 棵已足够拟合
    # 这个 7 特征的平滑结果面（它的作用不是精确预测 y，而是残差正交化）。
    params["n_estimators"] = min(int(params.get("n_estimators", 300)), 100)

    m1 = LGBMRegressor(random_state=seed, verbose=-1, **params)
    m0 = LGBMRegressor(random_state=seed + 1, verbose=-1, **params)
    # 用全部样本拟合两个结果模型（不做交叉拟合；报告里注明这是简化）
    m1.fit(X[t == 1], y[t == 1])
    m0.fit(X[t == 0], y[t == 0])
    mu1 = m1.predict(X)
    mu0 = m0.predict(X)

    e = np.clip(e, 1e-2, 1 - 1e-2)
    psi = mu1 - mu0 + t * (y - mu1) / e - (1 - t) * (y - mu0) / (1 - e)
    diff = float(psi.mean())
    se = float(psi.std(ddof=1) / np.sqrt(psi.size))

    lo, hi = _ci(diff, se, alpha)
    return ObsEstimate(
        method="dr", estimate=diff, se=se, ci_lower=lo, ci_upper=hi,
        n_treated=int(t.sum()), n_control=int((1 - t).sum()),
        diagnostics={
            "mu1_mean": float(mu1.mean()),
            "mu0_mean": float(mu0.mean()),
            "note": "结果模型用全样本拟合（未做交叉拟合），报告已注明",
        },
    )


# --------------------------------------------------------------------------- #
# PSM
# --------------------------------------------------------------------------- #
def psm_estimate(
    y: np.ndarray,
    t: np.ndarray,
    e: np.ndarray,
    *,
    alpha: float = 0.05,
    caliper: float = 0.02,
) -> ObsEstimate:
    """倾向得分 1:1 最近邻匹配（有放回，卡钳约束）。

    有放回 + 卡钳：无放回会因"抢同一个对照"导致匹配顺序依赖；
    卡钳保证不把倾向得分差太远的人配成一对（否则匹配失去意义）。

    **标准误的近似**：用配对差值的标准差 / sqrt(配对数)。
    这忽略了"对照被重复使用"带来的相关性，会低估 SE。
    本项目在报告局限性里明确披露，不假装它是精确的。
    """
    from sklearn.neighbors import NearestNeighbors

    y, t = _check_inputs(y, t)
    e = np.asarray(e, dtype=float)

    idx_t = np.flatnonzero(t == 1)
    idx_c = np.flatnonzero(t == 0)
    if idx_t.size == 0 or idx_c.size == 0:
        raise ValueError("PSM 需要两组都有样本")

    nn = NearestNeighbors(n_neighbors=1).fit(e[idx_c].reshape(-1, 1))
    dist, pos = nn.kneighbors(e[idx_t].reshape(-1, 1))
    within = dist.ravel() <= caliper
    matched_t = idx_t[within]
    matched_c = idx_c[pos.ravel()[within]]

    if matched_t.size < 2:
        raise ValueError(
            f"卡钳 {caliper} 下只匹配到 {matched_t.size} 对，无法估计；请放宽 caliper"
        )

    diffs = y[matched_t] - y[matched_c]
    diff = float(diffs.mean())
    se = float(diffs.std(ddof=1) / np.sqrt(diffs.size))
    lo, hi = _ci(diff, se, alpha)

    return ObsEstimate(
        method="psm", estimate=diff, se=se, ci_lower=lo, ci_upper=hi,
        n_treated=int(matched_t.size), n_control=int(np.unique(matched_c).size),
        diagnostics={
            "caliper": caliper,
            "n_pairs": int(matched_t.size),
            "match_rate": float(matched_t.size / idx_t.size),
            "n_unique_control": int(np.unique(matched_c).size),
            "se_note": "配对 SE 忽略对照重复使用的相关性，可能低估",
        },
    )


def estimate_all(
    y: np.ndarray,
    t: np.ndarray,
    X: np.ndarray,
    cfg: Config,
    *,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict[str, ObsEstimate]:
    """一次性跑完四种方法，共享同一份倾向得分。

    共享倾向得分是刻意的：**差异只应来自估计方法**，而不是"各自拟合了一个
    不同的倾向得分模型"。
    """
    psm_caliper = float(cfg.require("estimators.obs.psm_caliper"))
    clip_q = float(cfg.require("estimators.obs.ipw_weight_clip_quantile"))

    e = fit_propensity(X, t)
    return {
        "naive": naive_difference(y, t, alpha=alpha),
        "psm": psm_estimate(y, t, e, alpha=alpha, caliper=psm_caliper),
        "ipw": ipw_estimate(y, t, e, alpha=alpha, clip_quantile=clip_q),
        "dr": dr_estimate(y, t, e, X, cfg, alpha=alpha, seed=seed),
    }
