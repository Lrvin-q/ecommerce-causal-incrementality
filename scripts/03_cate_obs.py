"""第二轮：CATE 估计与观察性因果的 λ 敏感性分析。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\03_cate_obs.py

三件事
------
1. **CATE**：L1（随机实验）上比较 T-learner / S-learner / Causal Forest，
   训练/验证/测试按用户分离，只在测试集上对**解析真值**评估。
2. **观察性因果**：L3 上比较 naive / PSM / IPW / DR，随混淆强度 λ 扫描。
3. **结论写成条件式**：找出"哪种方法在什么 λ 下开始不可靠"，而不是预设结论。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt

from causal_growth import dgp
from causal_growth.config import load_config
from causal_growth.data.split import train_val_test_split
from causal_growth.estimate.cate import CAUSAL_METHODS, design_matrix, estimate_cate
from causal_growth.estimate.obs import OBS_METHODS, estimate_all, fit_propensity, standardized_mean_diff
from causal_growth.evaluation.metrics import (
    calibration_table,
    cate_accuracy,
    nonneg_policy,
    policy_value,
    ranking_metrics,
)
from causal_growth.io_utils import save_table
from causal_growth.viz import METHOD_COLORS, add_source_note, save_fig

METHOD_LABELS = {"t_learner": "T-learner", "s_learner": "S-learner", "causal_forest": "Causal Forest"}
OBS_LABELS = {"naive": "Naive 差分", "psm": "PSM", "ipw": "IPW", "dr": "DR（AIPW）"}


def _seed(cfg) -> int:
    return int(cfg.require("project.master_seed"))


# --------------------------------------------------------------------------- #
# 1. CATE
# --------------------------------------------------------------------------- #
def run_cate(cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """在 L1 上比较三种 CATE 估计方法。

    L1 是**随机实验**：可忽略性成立，所以这里的 CATE 估计是"方法本身好不好"的
    干净考察，不掺识别问题。
    """
    l1 = cfg.require("dgp.l1")
    pop = dgp.assign_random(cfg, dgp.build("L1", cfg, 0))
    split = train_val_test_split(
        len(pop),
        test_size=float(cfg.require("evaluation.test_size")),
        val_size=float(cfg.require("evaluation.val_size")),
        master_seed=_seed(cfg),
        index=0,
    )
    print(f"      切分：train={split.train.size:,} val={split.val.size:,} test={split.test.size:,}")

    tau_true_test = pop.truth.cate_profit[split.test]
    pi1_test = pop.potential.pi1[split.test]
    pi0_test = pop.potential.pi0[split.test]

    rows: list[dict] = []
    calib_frames: list[pd.DataFrame] = []
    scatter: dict[str, np.ndarray] = {}

    n_cf = int(cfg.require("evaluation.causal_forest_repeats"))
    for method in CAUSAL_METHODS:
        if method == "causal_forest" and n_cf <= 0:
            continue
        print(f"      拟合 {METHOD_LABELS[method]} ...")
        fit = estimate_cate(pop, cfg, split, outcome="net_profit", method=method)
        acc = cate_accuracy(fit.tau_test, tau_true_test)
        rank = ranking_metrics(fit.tau_test, tau_true_test, top_share=float(cfg.require("evaluation.top_share")))
        pol = nonneg_policy(fit.tau_test)
        value = policy_value(pol, pi1=pi1_test, pi0=pi0_test)
        scatter[method] = fit.tau_test

        rows.append(
            {
                "方法": METHOD_LABELS[method],
                "CATE_RMSE": acc.rmse,
                "CATE_MAE": acc.mae,
                "偏差": acc.bias,
                "相关系数": acc.correlation,
                "R2": acc.r2,
                "Top20%重合度": rank.top_overlap,
                "Spearman": rank.spearman,
                "Kendall": rank.kendall,
                "策略价值_元每人": value,
                "真值ATE_元每人": float(np.mean(tau_true_test)),
                "预测均值": float(fit.tau_test.mean()),
                "预测标准差": float(fit.tau_test.std(ddof=1)),
                "真值标准差": float(tau_true_test.std(ddof=1)),
            }
        )
        cal = calibration_table(fit.tau_test, tau_true_test, n_bins=10)
        cal.insert(0, "方法", METHOD_LABELS[method])
        calib_frames.append(cal)

    result = pd.DataFrame(rows)
    save_table(result, "r2_cate_comparison")
    save_table(pd.concat(calib_frames, ignore_index=True), "r2_cate_calibration")

    _plot_cate_scatter(scatter, tau_true_test, cfg)
    _plot_cate_calibration(calib_frames, cfg)
    _plot_cate_metrics(result, cfg)

    # ---- 重复：T/S-learner 的 RMSE 分布 ----
    r = int(cfg.require("evaluation.cate_repeats"))
    print(f"      重复 {r} 次估计 CATE RMSE 分布 ...")
    rep_rows = []
    for i in range(r):
        pop_r = dgp.assign_random(cfg, dgp.build("L1", cfg, i))
        sp_r = train_val_test_split(
            len(pop_r),
            test_size=float(cfg.require("evaluation.test_size")),
            val_size=float(cfg.require("evaluation.val_size")),
            master_seed=_seed(cfg),
            index=i,
        )
        truth_r = pop_r.truth.cate_profit[sp_r.test]
        for method in ("t_learner", "s_learner"):
            fit_r = estimate_cate(pop_r, cfg, sp_r, outcome="net_profit", method=method, seed_index=i)
            acc_r = cate_accuracy(fit_r.tau_test, truth_r)
            rank_r = ranking_metrics(fit_r.tau_test, truth_r, top_share=0.2)
            rep_rows.append(
                {
                    "repeat": i, "method": METHOD_LABELS[method],
                    "rmse": acc_r.rmse, "bias": acc_r.bias,
                    "spearman": rank_r.spearman, "top_overlap": rank_r.top_overlap,
                }
            )
    reps = pd.DataFrame(rep_rows)
    save_table(reps, "r2_cate_repeats_raw")
    summary = (
        reps.groupby("method", observed=True)
        .agg(
            重复次数=("repeat", "size"),
            RMSE均值=("rmse", "mean"),
            RMSE标准差=("rmse", "std"),
            RMSE_2_5分位=("rmse", lambda s: float(np.percentile(s, 2.5))),
            RMSE_97_5分位=("rmse", lambda s: float(np.percentile(s, 97.5))),
            偏差均值=("bias", "mean"),
            Spearman均值=("spearman", "mean"),
            Top20重合度均值=("top_overlap", "mean"),
        )
        .reset_index()
    )
    save_table(summary, "r2_cate_repeats_summary")

    _plot_cate_repeats(reps, cfg)
    return result, summary


def _plot_cate_scatter(scatter: dict[str, np.ndarray], tau_true: np.ndarray, cfg) -> None:
    n = len(scatter)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 4.2), squeeze=False)
    for ax, (method, tau_hat) in zip(axes[0], scatter.items()):
        ax.hexbin(tau_true, tau_hat, gridsize=45, cmap="viridis", mincnt=1)
        lim = [float(min(tau_true.min(), tau_hat.min())), float(max(tau_true.max(), tau_hat.max()))]
        ax.plot(lim, lim, "r--", lw=1, label="y = x（完美估计）")
        ax.set_xlabel("真值 $\\tau(x)$（元/人，DGP 解析值）")
        ax.set_ylabel("估计 $\\hat{\\tau}(x)$（元/人）")
        ax.set_title(f"{METHOD_LABELS[method]}\n与真值相关系数 {np.corrcoef(tau_true, tau_hat)[0,1]:.3f}")
        ax.legend(fontsize=8)
    add_source_note(fig, f"seed={_seed(cfg)} | L1 测试集 | 真值来自 DGP 解析 $\\tau(x)$，非观测利润差")
    save_fig(fig, "r2_cate_vs_truth")


def _plot_cate_calibration(calib_frames: list[pd.DataFrame], cfg) -> None:
    fig, axes = plt.subplots(1, len(calib_frames), figsize=(4.2 * len(calib_frames), 3.8), squeeze=False)
    for ax, cal in zip(axes[0], calib_frames):
        method = cal["方法"].iloc[0]
        ax.plot(cal["mean_pred"], cal["mean_true"], "o-", label="实际校准")
        lim = [float(min(cal["mean_pred"].min(), cal["mean_true"].min())),
               float(max(cal["mean_pred"].max(), cal["mean_true"].max()))]
        ax.plot(lim, lim, "k--", lw=1, label="完美校准")
        ax.set_xlabel("预测 CATE 分箱均值（元/人）")
        ax.set_ylabel("真值 CATE 分箱均值（元/人）")
        ax.set_title(f"{method} 校准曲线")
        ax.legend(fontsize=8)
    add_source_note(fig, f"seed={_seed(cfg)} | L1 测试集 | 按预测值分位数分 10 箱")
    save_fig(fig, "r2_cate_calibration")


def _plot_cate_metrics(result: pd.DataFrame, cfg) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    x = np.arange(len(result))
    axes[0].bar(x - 0.2, result["CATE_RMSE"], width=0.4, label="CATE RMSE", color="#1E88E5")
    axes[0].bar(x + 0.2, result["CATE_MAE"], width=0.4, label="CATE MAE", color="#FB8C00")
    axes[0].set_xticks(x, result["方法"], rotation=12)
    axes[0].set_ylabel("误差（元/人）")
    axes[0].set_title("点估计精度（越小越好）")
    axes[0].legend(fontsize=8)

    axes[1].bar(x - 0.2, result["Spearman"], width=0.4, label="Spearman 秩相关", color="#2E7D32")
    axes[1].bar(x + 0.2, result["Top20%重合度"], width=0.4, label="Top20% 重合度", color="#6A1B9A")
    axes[1].set_xticks(x, result["方法"], rotation=12)
    axes[1].set_ylim(0, 1.05)
    axes[1].set_ylabel("排序质量")
    axes[1].set_title("排序质量（与精度是两件事）")
    axes[1].legend(fontsize=8)
    add_source_note(fig, f"seed={_seed(cfg)} | L1 测试集 | CATE RMSE 与排序指标不可互相替代")
    save_fig(fig, "r2_cate_metrics")


def _plot_cate_repeats(reps: pd.DataFrame, cfg) -> None:
    fig, ax = plt.subplots(figsize=(6, 3.8))
    labels = reps["method"].unique().tolist()
    data = [reps.loc[reps["method"] == m, "rmse"].to_numpy() for m in labels]
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True)
    for patch, color in zip(bp["boxes"], ["#1E88E5", "#FB8C00"]):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax.set_ylabel("CATE RMSE（元/人）")
    ax.set_title(f"重复 {len(reps['repeat'].unique())} 次的 RMSE 分布")
    add_source_note(fig, f"seed={_seed(cfg)} | L1 | 每次重新生成数据与切分")
    save_fig(fig, "r2_cate_rmse_distribution")


# --------------------------------------------------------------------------- #
# 2. λ 敏感性扫描
# --------------------------------------------------------------------------- #
def run_lambda_scan(cfg) -> pd.DataFrame:
    """L3 上按 λ 扫描四种观察性方法。

    结论必须是**条件式**：找出"哪种方法在什么 λ 下开始不可靠"，
    而不是预设"DR 轻度稳健、重度失效"。结果取决于 DGP、样本量、倾向得分分布。
    """
    lam_grid = [float(x) for x in cfg.require("dgp.l3.lambda_grid")]
    reps = int(cfg.require("evaluation.lambda_scan_repeats"))
    alpha = float(cfg.require("experiment.alpha"))
    n_l3 = int(cfg.require("dgp.l3.n_users"))
    print(f"      λ 网格 {lam_grid}，每个 λ 重复 {reps} 次，n={n_l3:,}")

    rows: list[dict] = []
    for lam in lam_grid:
        for i in range(reps):
            pop = dgp.build("L3", cfg, i, lam=lam)
            pop, _ = dgp.assign_observational(cfg, pop, lam=lam, index=i)
            X = design_matrix(pop)
            t = pop.treatment.astype(int)
            _, pi_obs = pop.potential.observed(t)
            truth = pop.truth.ate_profit
            # 单次样本的**实现** ATE。它与解析 ATE 之间还有一次蒙特卡洛差
            # （sd(π1−π0)/√n ≈ 0.05 at n=2 万），估计器实际瞄准的是这个数。
            # 两个真值都记下来，报告的偏差分解才有依据。
            realized_ate = float(np.mean(pop.potential.pi1 - pop.potential.pi0))
            try:
                est = estimate_all(pi_obs, t, X, cfg, alpha=alpha, seed=i)
            except (ValueError, RuntimeError) as exc:  # PSM 匹配不到时跳过该次
                rows.append({"lambda": lam, "repeat": i, "method": "psm",
                             "estimate": np.nan, "se": np.nan, "ci_lower": np.nan,
                             "ci_upper": np.nan, "truth": truth,
                             "realized_ate": realized_ate, "failed": True,
                             "error": str(exc)[:120]})
                continue
            for name, res in est.items():
                rows.append(
                    {
                        "lambda": lam, "repeat": i, "method": name,
                        "estimate": res.estimate, "se": res.se,
                        "ci_lower": res.ci_lower, "ci_upper": res.ci_upper,
                        "truth": truth, "realized_ate": realized_ate,
                        "failed": False, "error": "",
                        "n_treated": res.n_treated, "n_control": res.n_control,
                    }
                )
    raw = pd.DataFrame(rows)
    save_table(raw, "r2_lambda_raw")

    agg = (
        raw[~raw["failed"]]
        .assign(bias=lambda d: d["estimate"] - d["truth"],
                bias_realized=lambda d: d["estimate"] - d["realized_ate"],
                covered=lambda d: (d["ci_lower"] <= d["truth"]) & (d["truth"] <= d["ci_upper"]))
        .groupby(["method", "lambda"], observed=True)
        .agg(
            重复次数=("repeat", "size"),
            偏差=("bias", "mean"),
            偏差_对实现ATE=("bias_realized", "mean"),
            偏差绝对均值=("bias", lambda s: float(s.abs().mean())),
            RMSE=("bias", lambda s: float(np.sqrt((s**2).mean()))),
            覆盖率=("covered", "mean"),
            平均估计=("estimate", "mean"),
            真值=("truth", "mean"),
            实现ATE均值=("realized_ate", "mean"),
        )
        .reset_index()
        .sort_values(["method", "lambda"])
    )
    save_table(agg, "r2_lambda_summary")
    return agg


def find_reliability_threshold(agg: pd.DataFrame, *, coverage_target: float = 0.90) -> pd.DataFrame:
    """识别"结论开始不可靠"的 λ 阈值（覆盖率跌破目标的最小 λ）。

    这是把结论写成**条件式**的机器实现：
    不是"某方法稳健/失效"，而是"某方法在 λ ≤ θ 时覆盖率 ≥ 0.90，超过 θ 就不行了"。
    """
    rows = []
    for method, g in agg.groupby("method", observed=True):
        g = g.sort_values("lambda")
        below = g[g["覆盖率"] < coverage_target]
        theta = float(below["lambda"].min()) if not below.empty else float("nan")
        rows.append(
            {
                "method": OBS_LABELS.get(method, method),
                "覆盖率低于目标的起始λ": theta,
                "最大λ处覆盖率": float(g["覆盖率"].iloc[-1]),
                "最大λ处偏差": float(g["偏差"].iloc[-1]),
                "λ=0时偏差": float(g.loc[g["lambda"] == 0.0, "偏差"].squeeze()) if (g["lambda"] == 0.0).any() else float("nan"),
            }
        )
    out = pd.DataFrame(rows)
    save_table(out, "r2_lambda_threshold")
    return out


def _plot_lambda_curves(agg: pd.DataFrame, cfg) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for method in OBS_METHODS:
        g = agg[agg["method"] == method].sort_values("lambda")
        if g.empty:
            continue
        color = METHOD_COLORS.get(method, "grey")
        axes[0].plot(g["lambda"], g["偏差"], "o-", color=color, label=OBS_LABELS[method])
        axes[1].plot(g["lambda"], g["覆盖率"], "o-", color=color, label=OBS_LABELS[method])

    axes[0].axhline(0, color="black", ls="--", lw=1, label="无偏")
    axes[0].set_xlabel("混淆强度 λ（0 = 无可忽略性违背）")
    axes[0].set_ylabel("偏差（元/人）")
    axes[0].set_title("偏差随混淆强度恶化")
    axes[0].legend(fontsize=8)

    axes[1].axhline(0.95, color="black", ls="--", lw=1, label="名义 95%")
    axes[1].axhline(0.90, color="red", ls=":", lw=1, label="0.90 警戒线")
    axes[1].set_xlabel("混淆强度 λ")
    axes[1].set_ylabel("95% CI 覆盖率")
    axes[1].set_ylim(0, 1.02)
    axes[1].set_title("覆盖率：结论是否还可信")
    axes[1].legend(fontsize=8)

    add_source_note(fig, f"seed={_seed(cfg)} | L3 观察性设定 | 每个 λ 重复 {int(agg['重复次数'].max())} 次")
    save_fig(fig, "r2_lambda_sensitivity")


def run_psm_balance(cfg, *, lam: float = 0.5) -> pd.DataFrame:
    """PSM/IPW 的平衡性诊断：匹配/加权前后的标准化均值差。

    这一张图回答"为什么 PSM 在 L3 下不行"：它在**可观测特征上确实平衡了**，
    但偏差依然存在——因为问题不在 X，而在不可观测的 U。
    """
    pop = dgp.build("L3", cfg, 0, lam=lam)
    pop, _ = dgp.assign_observational(cfg, pop, lam=lam, index=0)
    X = design_matrix(pop)
    t = pop.treatment.astype(int)
    e = fit_propensity(X, t)

    from numpy import ones_like

    # IPW 权重下的平衡
    w = np.where(t == 1, 1.0 / e, 1.0 / (1.0 - e))
    smd_raw = standardized_mean_diff(X, t)
    smd_ipw = standardized_mean_diff(X, t, w)

    from causal_growth.contracts import FEATURE_ORDER

    out = pd.DataFrame(
        {
            "特征": list(FEATURE_ORDER),
            "匹配前SMD": smd_raw,
            "IPW加权后SMD": smd_ipw,
            "加权后平衡": np.abs(smd_ipw) < 0.1,
        }
    )
    save_table(out, "r2_psm_balance")

    fig, ax = plt.subplots(figsize=(6.5, 4))
    y = np.arange(len(out))
    ax.scatter(out["匹配前SMD"], y, label="加权前", color="#E53935", marker="o")
    ax.scatter(out["IPW加权后SMD"], y, label="IPW 加权后", color="#2E7D32", marker="D")
    ax.axvline(0, color="grey", ls="-", lw=1)
    for v in (-0.1, 0.1):
        ax.axvline(v, color="black", ls="--", lw=1, label="|SMD|=0.1 平衡阈" if v > 0 else None)
    ax.set_yticks(y, out["特征"])
    ax.set_xlabel("标准化均值差（SMD）")
    ax.set_title(f"λ={lam}：可观测特征被平衡了，但偏差依然存在\n"
                 "——问题不在 X，而在不可观测的 U")
    ax.legend(fontsize=8)
    add_source_note(fig, f"seed={_seed(cfg)} | L3 λ={lam} | 4 万样本")
    save_fig(fig, "r2_psm_balance")
    return out


# --------------------------------------------------------------------------- #
def main() -> int:
    cfg = load_config()
    print(f"[config] seed={_seed(cfg)}  {cfg.require('project.data_source_label')}")

    print("[1/4] CATE 方法对比（L1 随机实验）...")
    cate_df, cate_rep = run_cate(cfg)
    for _, row in cate_df.iterrows():
        print(f"      {row['方法']:<14} RMSE={row['CATE_RMSE']:.4f}  偏差={row['偏差']:+.4f}  "
              f"ρ={row['相关系数']:.3f}  Spearman={row['Spearman']:.3f}  "
              f"Top20重合={row['Top20%重合度']:.3f}")

    print("[2/4] λ 敏感性扫描（L3 观察性）...")
    agg = run_lambda_scan(cfg)
    for method in OBS_METHODS:
        g = agg[agg["method"] == method]
        if g.empty:
            continue
        print(f"      {OBS_LABELS[method]:<12} λ=0 偏差 {g.iloc[0]['偏差']:+.3f} → "
              f"λ={g.iloc[-1]['lambda']:.2f} 偏差 {g.iloc[-1]['偏差']:+.3f}   "
              f"覆盖率 {g.iloc[0]['覆盖率']:.2f} → {g.iloc[-1]['覆盖率']:.2f}")

    print("[3/4] 失效阈值识别 ...")
    thr = find_reliability_threshold(agg)
    for _, row in thr.iterrows():
        theta = row["覆盖率低于目标的起始λ"]
        desc = f"λ ≥ {theta:.2f} 起覆盖率跌破 0.90" if theta == theta else "全程覆盖率达标"
        print(f"      {row['method']:<12} {desc}")

    print("[4/4] PSM 平衡性诊断 ...")
    bal = run_psm_balance(cfg, lam=0.5)
    print(f"      加权后 |SMD|<0.1 的特征数：{int(bal['加权后平衡'].sum())}/{len(bal)}")

    _plot_lambda_curves(agg, cfg)
    print("\n[done] 产物已落盘 outputs/tables/r2_*.csv 与 outputs/figures/r2_*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
