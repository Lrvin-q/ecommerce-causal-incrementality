"""第一轮实验主线：样本量 → AA 校验 → ITT → 护栏非劣效 → 多重比较 → 重复实验。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\02_run_experiment.py

产物
----
* ``outputs/tables/r1_*.csv``   —— 报告里每个数字的来源
* ``outputs/figures/r1_*.png``  —— 报告插图

本脚本只做**编排**，不含业务逻辑（AGENTS.md §2：scripts 是薄入口）。
所有计算都在 ``causal_growth`` 包里，便于单测与复用。
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

# 允许直接 `python scripts/02_run_experiment.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt

from causal_growth import dgp
from causal_growth.config import load_config
from causal_growth.data.tables import build_analysis_frame
from causal_growth.design.aa import aa_test_binary, aa_test_continuous
from causal_growth.design.guardrail import noninferiority_binary
from causal_growth.design.multiplicity import adjust
from causal_growth.design.power import design_sample_size, sample_size_mean, sample_size_proportion
from causal_growth.estimate.itt import auxiliary_metrics, estimate_itt
from causal_growth.io_utils import figures_dir, save_table
from causal_growth.viz import METHOD_COLORS, add_source_note, save_fig


def _seed(cfg) -> int:
    return int(cfg.require("project.master_seed"))


# --------------------------------------------------------------------------- #
# 1. 样本量
# --------------------------------------------------------------------------- #
def step_sample_size(cfg) -> pd.DataFrame:
    ss = design_sample_size(cfg)
    df = pd.DataFrame([{**asdict(ss)}])
    # inputs 是嵌套 dict，单独展平存储，便于报告逐项追溯
    inputs = df.pop("inputs").iloc[0]
    flat = pd.DataFrame([{"参数": k, "取值": v} for k, v in inputs.items()])
    save_table(flat, "r1_sample_size_inputs")
    save_table(df, "r1_sample_size")
    return df


def step_sample_size_curve(cfg) -> pd.DataFrame:
    """样本量随 MDE 变化的曲线（说明"为什么取这个 MDE"）。"""
    p0 = float(cfg.require("business.baseline_conversion"))
    sigma = float(cfg.require("experiment.mde.profit_sd_assumed"))
    alpha = float(cfg.require("experiment.alpha"))
    power = float(cfg.require("experiment.power"))

    conv_mde = np.linspace(0.005, 0.03, 26)
    prof_mde = np.linspace(0.2, 2.0, 26)
    rows = [
        {
            "mde_conversion": m,
            "n_per_group_conversion": sample_size_proportion(p0, m, alpha=alpha, power=power),
        }
        for m in conv_mde
    ]
    conv_curve = pd.DataFrame(rows)
    prof_curve = pd.DataFrame(
        [
            {
                "mde_profit": m,
                "n_per_group_profit": sample_size_mean(sigma, m, alpha=alpha, power=power),
            }
            for m in prof_mde
        ]
    )
    save_table(conv_curve, "r1_sample_size_curve_conversion")
    save_table(prof_curve, "r1_sample_size_curve_profit")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot(conv_curve["mde_conversion"] * 100, conv_curve["n_per_group_conversion"], "o-")
    axes[0].axvline(1.0, color="red", ls="--", lw=1, label="选定 MDE = 1pp")
    axes[0].set_xlabel("转化率 MDE（百分点）")
    axes[0].set_ylabel("每组所需样本量")
    axes[0].set_title("转化率指标：MDE 越小，样本量按平方增长")
    axes[0].set_yscale("log")
    axes[0].legend()

    axes[1].plot(prof_curve["mde_profit"], prof_curve["n_per_group_profit"], "s-",
                 color=METHOD_COLORS["ipw"])
    axes[1].axvline(0.5, color="red", ls="--", lw=1, label="选定 MDE = 0.5 元/人")
    axes[1].set_xlabel("人均净增量利润 MDE（元/人）")
    axes[1].set_ylabel("每组所需样本量")
    axes[1].set_title(f"利润指标：σ={sigma:.1f} 元时的样本量")
    axes[1].set_yscale("log")
    axes[1].legend()

    add_source_note(fig, f"seed={_seed(cfg)} | α={alpha}, power={power}")
    save_fig(fig, "r1_sample_size_curve")
    return conv_curve


# --------------------------------------------------------------------------- #
# 2. AA 校验
# --------------------------------------------------------------------------- #
def step_aa(cfg) -> pd.DataFrame:
    """AA：重复 1000 次**无真实效应**的实验，看 p 值分布与假阳性率。

    正确用法不是"看单次 AA 是否显著"，而是看 p 值分布是否接近 Uniform、
    假阳性率是否接近 α（方案 §2.4）。
    """
    ss = design_sample_size(cfg)
    repeats = int(cfg.require("experiment.aa.repeats"))
    alpha = float(cfg.require("experiment.aa.alpha"))
    p0 = float(cfg.require("business.baseline_conversion"))
    sigma = float(cfg.require("experiment.mde.profit_sd_assumed"))

    aa_bin = aa_test_binary(p0, ss.n_per_group_conversion, repeats, alpha=alpha, master_seed=_seed(cfg))
    aa_cont = aa_test_continuous(0.0, sigma, ss.n_per_group_profit, repeats, alpha=alpha, master_seed=_seed(cfg))

    summary = pd.DataFrame(
        [
            {
                "指标": "转化率（二元）",
                "每组样本量": ss.n_per_group_conversion,
                "重复次数": aa_bin.n_repeats,
                "假阳性率": aa_bin.false_positive_rate,
                "FPR_95CI_下界": aa_bin.fpr_ci[0],
                "FPR_95CI_上界": aa_bin.fpr_ci[1],
                "p值均值": aa_bin.mean_p_value,
                "KS统计量": aa_bin.ks_uniform_stat,
                "KS_p值": aa_bin.ks_uniform_pvalue,
                "结论": "p 值接近 Uniform，FPR 接近 α" if aa_bin.ks_uniform_pvalue > 0.01 else "p 值偏离 Uniform",
            },
            {
                "指标": "人均净贡献利润（连续）",
                "每组样本量": ss.n_per_group_profit,
                "重复次数": aa_cont.n_repeats,
                "假阳性率": aa_cont.false_positive_rate,
                "FPR_95CI_下界": aa_cont.fpr_ci[0],
                "FPR_95CI_上界": aa_cont.fpr_ci[1],
                "p值均值": aa_cont.mean_p_value,
                "KS统计量": aa_cont.ks_uniform_stat,
                "KS_p值": aa_cont.ks_uniform_pvalue,
                "结论": "p 值接近 Uniform，FPR 接近 α" if aa_cont.ks_uniform_pvalue > 0.01 else "p 值偏离 Uniform",
            },
        ]
    )
    save_table(summary, "r1_aa_summary")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, res, title in (
        (axes[0], aa_bin, f"转化率 AA（n={ss.n_per_group_conversion}/组，{repeats} 次）"),
        (axes[1], aa_cont, f"利润 AA（n={ss.n_per_group_profit}/组，{repeats} 次）"),
    ):
        ax.hist(res.p_values, bins=20, range=(0, 1), density=True, alpha=0.75,
                color=METHOD_COLORS["ipw"], edgecolor="white")
        ax.axhline(1.0, color="black", ls="--", lw=1, label="Uniform(0,1) 理论密度")
        ax.axvline(res.alpha, color="red", ls=":", lw=1.5, label=f"α={res.alpha}")
        ax.set_xlabel("p 值")
        ax.set_ylabel("密度")
        ax.set_title(f"{title}\nFPR={res.false_positive_rate:.4f}，KS p={res.ks_uniform_pvalue:.3f}")
        ax.legend(fontsize=8)
    add_source_note(fig, f"seed={_seed(cfg)} | 全部为无真实效应的 AA 实验")
    save_fig(fig, "r1_aa_pvalue_distribution")
    return summary


# --------------------------------------------------------------------------- #
# 3-5. 主实验：ITT / 辅助指标 / 护栏 / 多重比较
# --------------------------------------------------------------------------- #
def _run_level(cfg, level: str, index: int = 0) -> tuple[pd.DataFrame, dict]:
    pop = dgp.build(level, cfg, index)
    share = (
        float(cfg.require("dgp.l2.treatment_share"))
        if level == "L2"
        else float(cfg.require("experiment.treatment_share"))
    )
    pop = dgp.assign_random(cfg, pop, treatment_share=share)
    df = build_analysis_frame(pop, cfg)
    return df, {"truth_ate_conversion": pop.truth.ate_conversion,
                "truth_ate_profit": pop.truth.ate_profit,
                "truth_summary": pop.truth.summary()}


def step_main_experiment(cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """L0/L1/L2 三层的 ITT 对比。

    L0 是"评估流程校准"：如果 L0 都有偏，后面全不可信。
    L1 是主结果。L2 加入有限样本、不等分流、效应漂移。
    """
    rows: list[dict] = []
    for level in ("L0", "L1", "L2"):
        df, truth = _run_level(cfg, level)
        itt_profit = estimate_itt(df, cfg, "net_profit")
        itt_conv = estimate_itt(df, cfg, "converted")
        for res, truth_value, kind in (
            (itt_profit, truth["truth_ate_profit"], "net_profit_per_user"),
            (itt_conv, truth["truth_ate_conversion"], "conversion"),
        ):
            rows.append(
                {
                    "层级": level,
                    "指标": kind,
                    "真值": truth_value,
                    "处理组均值": res.mean_treated,
                    "对照组均值": res.mean_control,
                    "ITT估计": res.diff,
                    "标准误": res.se,
                    "CI下界": res.ci_lower,
                    "CI上界": res.ci_upper,
                    "p值": res.p_value,
                    "偏差_估计减真值": res.diff - truth_value,
                    "n处理组": res.n_treated,
                    "n对照组": res.n_control,
                    "方法": res.method,
                }
            )
    itt_df = pd.DataFrame(rows)
    save_table(itt_df, "r1_itt")

    df_l1, _ = _run_level(cfg, "L1")
    aux = auxiliary_metrics(df_l1, cfg)
    save_table(aux, "r1_auxiliary")

    _plot_itt_forest(itt_df, cfg)
    return itt_df, aux


def _plot_itt_forest(itt_df: pd.DataFrame, cfg) -> None:
    order = ["L0", "L1", "L2"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, metric, unit, title in (
        (axes[0], "conversion", "", "转化率增量（概率尺度）"),
        (axes[1], "net_profit_per_user", " 元/人", "人均净增量贡献利润"),
    ):
        sub = itt_df[itt_df["指标"] == metric].set_index("层级").loc[order]
        y = np.arange(len(order))[::-1]
        ax.errorbar(
            sub["ITT估计"], y,
            xerr=[sub["ITT估计"] - sub["CI下界"], sub["CI上界"] - sub["ITT估计"]],
            fmt="o", capsize=5, color=METHOD_COLORS["dr"], label="ITT 估计与 95% CI",
        )
        ax.scatter(sub["真值"], y, marker="D", s=60, facecolors="none",
                   edgecolors="black", label="真值（已知 DGP）", zorder=5)
        ax.axvline(0, color="grey", ls="--", lw=1)
        ax.set_yticks(y, order)
        ax.set_xlabel(f"效应{unit}")
        ax.set_title(title)
        ax.legend(fontsize=8)
    add_source_note(fig, f"seed={_seed(cfg)} | R=1 单次实验")
    save_fig(fig, "r1_itt_forest")


def step_guardrail(cfg, df: pd.DataFrame) -> pd.DataFrame:
    """护栏非劣效检验：退款率。

    **"不显著" ≠ "安全"**。这里对 0 做一个双侧检验作对照，
    再对预设界值做单侧非劣效检验，展示两者给出不同结论的场景。
    """
    margin = float(cfg.require("experiment.guardrail.noninferiority_margin"))
    alpha_one = float(cfg.require("experiment.guardrail.alpha_one_sided"))

    t = df["treatment"].to_numpy() == 1
    conv = df["converted"].to_numpy() == 1
    ref = df["refunded"].to_numpy() == 1

    s_t, n_t = int((ref & t & conv).sum()), int((t & conv).sum())
    s_c, n_c = int((ref & ~t & conv).sum()), int((~t & conv).sum())

    ni = noninferiority_binary(s_t, n_t, s_c, n_c, margin=margin, alpha_one_sided=alpha_one)

    # 对照：对 0 做双侧检验（很多人误以为"不显著就是安全"）
    from causal_growth.estimate.itt import itt_difference_proportions

    sub = df[conv].copy()
    two_sided = itt_difference_proportions(sub, "refunded", alpha=float(cfg.require("experiment.alpha")))

    out = pd.DataFrame(
        [
            {
                "检验": "非劣效检验（对预设界值）",
                "指标": "退款率（已下单为分母）",
                "处理组": s_t / n_t,
                "对照组": s_c / n_c,
                "差值_pp": ni.diff * 100,
                "标准误_pp": ni.se * 100,
                "界值_pp": margin * 100,
                "结论": "通过：未显著超过界值" if ni.passed else "未通过：显著超过界值",
                "单侧CI上界_pp": ni.ci_one_sided_upper * 100,
                "p值": np.nan,
                "方法": ni.method,
            },
            {
                "检验": "双侧显著性检验（对 0）",
                "指标": "退款率（已下单为分母）",
                "处理组": s_t / n_t,
                "对照组": s_c / n_c,
                "差值_pp": two_sided.diff * 100,
                "标准误_pp": two_sided.se * 100,
                "界值_pp": 0.0,
                "结论": "对 0 显著" if two_sided.p_value < 0.05 else "对 0 不显著（**不等于安全**）",
                "单侧CI上界_pp": two_sided.ci_upper * 100,
                "p值": two_sided.p_value,
                "方法": two_sided.method,
            },
        ]
    )
    save_table(out, "r1_guardrail")

    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    # 只画**单侧**区间：从点估计到单侧 95% 上界。只画一个点毫无意义——
    # 非劣效的判定依据是"上界 < 界值"，看不到上界这张图就不成立。
    ax.errorbar(
        [ni.diff * 100], [0],
        xerr=[[0.0], [(ni.ci_one_sided_upper - ni.diff) * 100]],
        fmt="o", capsize=6, lw=2, color=METHOD_COLORS["psm"],
        label="单侧 95% 置信上界",
    )
    ax.axvline(ni.ci_one_sided_upper * 100, color=METHOD_COLORS["psm"], ls=":", lw=1)
    ax.axvline(margin * 100, color="red", ls="--", label=f"非劣效界值 {margin*100:.2f}pp")
    ax.axvline(0, color="grey", ls=":", label="无差异")
    ax.axvspan(-1.2, margin * 100, alpha=0.12, color="green", label="非劣效区域")
    ax.set_xlim(-1.0, margin * 100 + 0.6)
    ax.set_ylim(-0.6, 0.6)
    ax.set_yticks([])
    ax.set_xlabel("退款率差异（百分点，处理组 − 对照组）")
    ax.set_title(
        f"护栏非劣效：差值 {ni.diff*100:+.2f}pp，单侧 95% 上界 "
        f"{ni.ci_one_sided_upper*100:+.2f}pp {'<' if ni.passed else '≥'} "
        f"界值 {margin*100:.2f}pp → {'通过' if ni.passed else '未通过'}"
    )
    ax.legend(fontsize=8, loc="upper left")
    add_source_note(fig, f"seed={_seed(cfg)} | 单侧 α={alpha_one} | 界值={margin*100:.2f}pp")
    save_fig(fig, "r1_guardrail_ci")
    return out


def step_guardrail_power(cfg, df: pd.DataFrame) -> pd.DataFrame:
    """护栏非劣效检验的**功效分析** —— 第一轮最重要的方法论发现。

    问题：界值（0.5pp）与样本量是否匹配？答案是不匹配。

    当前样本下只有约 2.5 万个已转化用户，退款率差值的标准误约 0.34pp，
    而界值仅 0.5pp。要让单侧检验有 80% 功效去分辨"真实恶化 0.225pp 与 0.5pp 界值"，
    需要把标准误压到约 0.11pp，即已转化用户数扩大约 9.5 倍。

    结论：**非劣效检验"通过"这件事本身几乎不携带信息**——
    它主要是功效不足的产物，不是"护栏安全"的证据（方案 §2.4"不显著≠安全"的
    更深一层：**不显著也可能是因为根本测不出来**）。
    """
    from scipy.stats import norm

    margin = float(cfg.require("experiment.guardrail.noninferiority_margin"))
    alpha_one = float(cfg.require("experiment.guardrail.alpha_one_sided"))
    true_uplift = float(cfg.require("business.refund_rate")) * (
        float(cfg.require("business.refund_rate_treated_multiplier")) - 1.0
    )

    t = df["treatment"].to_numpy() == 1
    conv = df["converted"].to_numpy() == 1
    n_conv_t, n_conv_c = int((t & conv).sum()), int((~t & conv).sum())
    p_t = float(df.loc[t & conv, "refunded"].mean())
    p_c = float(df.loc[~t & conv, "refunded"].mean())

    def power_at(n_t: int, n_c: int, true_diff: float) -> float:
        se = float(np.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c))
        if se == 0:
            return float("nan")
        return float(norm.cdf((margin - true_diff) / se - norm.ppf(1 - alpha_one)))

    def required_converters(true_diff: float, target_power: float = 0.80) -> int:
        """在给定真实差值与目标功效下，处理组所需的已转化用户数（1:1 折算）。"""
        z_req = norm.ppf(target_power) + norm.ppf(1 - alpha_one)
        if margin - true_diff <= 0:
            return -1  # 真值已超过界值，任何样本量都救不了
        se_req = (margin - true_diff) / z_req
        # 两组方差近似相等时，se ≈ sqrt(2·p(1-p)/n)，反解得每组 n
        p_bar = (p_t + p_c) / 2
        return int(np.ceil(2.0 * p_bar * (1 - p_bar) / se_req**2))

    rows = []
    for true_diff, label in (
        (0.0, "真实无恶化（0pp）"),
        (true_uplift, f"真实小幅恶化（{true_uplift*100:.3f}pp，DGP 设定）"),
        (margin, f"真实恶化恰在界值（{margin*100:.2f}pp）"),
    ):
        rows.append(
            {
                "情景": label,
                "真实差值_pp": true_diff * 100,
                "当前已转化用户_处理组": n_conv_t,
                "当前已转化用户_对照组": n_conv_c,
                "当前SE_pp": float(
                    np.sqrt(p_t * (1 - p_t) / n_conv_t + p_c * (1 - p_c) / n_conv_c)
                ) * 100,
                "当前功效": power_at(n_conv_t, n_conv_c, true_diff),
                "达到80%功效所需_每组已转化用户": required_converters(true_diff),
                "界值_pp": margin * 100,
                "单侧α": alpha_one,
            }
        )
    out = pd.DataFrame(rows)
    save_table(out, "r1_guardrail_power")

    cur = out.iloc[1]
    print(
        f"      [功效] 真实恶化 {true_uplift*100:.3f}pp、界值 {margin*100:.2f}pp 下，"
        f"当前功效仅 {cur['当前功效']:.3f}；"
        f"要达 80% 需每组约 {int(cur['达到80%功效所需_每组已转化用户'])} 个已转化用户"
    )
    return out


def step_multiplicity(cfg, itt_df: pd.DataFrame) -> pd.DataFrame:
    """两个主指标（利润、转化率）的 Holm 校正。

    报告必须说清：校正针对**预注册的多个主指标**；
    探索性人群切片不在此列，需标注"未校正"（方案 §2.4）。
    """
    l1 = itt_df[itt_df["层级"] == "L1"]
    metrics = list(cfg.require("experiment.multiplicity.primary_metrics"))
    method = str(cfg.require("experiment.multiplicity.method"))
    raw = l1.set_index("指标").loc[metrics, "p值"].to_numpy()
    res = adjust(raw, method, alpha=float(cfg.require("experiment.alpha")))
    out = pd.DataFrame(
        {
            "指标": metrics,
            "原始p值": res.raw_p,
            "校正后p值": res.adjusted_p,
            "是否拒绝": res.rejected,
            "校正方法": method,
            "alpha": res.alpha,
        }
    )
    save_table(out, "r1_multiplicity")
    return out


# --------------------------------------------------------------------------- #
# 6. 重复实验
# --------------------------------------------------------------------------- #
def step_repeats(cfg) -> pd.DataFrame:
    """重复 R 次完整实验，报**分布**而不是单点（方案 §3.6 Step 7）。

    单次实验的 ITT 估计含抽样噪声；重复实验的分布才能回答
    "这套设计能把真值估到多准"。
    """
    r = int(cfg.require("evaluation.repeats_r"))
    rows: list[dict] = []
    for i in range(r):
        for level in ("L0", "L1"):
            df, truth = _run_level(cfg, level, index=i)
            itt_p = estimate_itt(df, cfg, "net_profit")
            itt_c = estimate_itt(df, cfg, "converted")
            rows.append(
                {
                    "repeat": i,
                    "level": level,
                    "est_profit": itt_p.diff,
                    "se_profit": itt_p.se,
                    "ci_profit_lo": itt_p.ci_lower,
                    "ci_profit_hi": itt_p.ci_upper,
                    "truth_profit": truth["truth_ate_profit"],
                    "est_conv": itt_c.diff,
                    "se_conv": itt_c.se,
                    "ci_conv_lo": itt_c.ci_lower,
                    "ci_conv_hi": itt_c.ci_upper,
                    "truth_conv": truth["truth_ate_conversion"],
                    "cover_profit": bool(itt_p.ci_lower <= truth["truth_ate_profit"] <= itt_p.ci_upper),
                    "cover_conv": bool(itt_c.ci_lower <= truth["truth_ate_conversion"] <= itt_c.ci_upper),
                }
            )
    df = pd.DataFrame(rows)
    save_table(df, "r1_repeats_raw")

    summary = (
        df.assign(
            bias_profit=lambda d: d.est_profit - d.truth_profit,
            bias_conv=lambda d: d.est_conv - d.truth_conv,
        )
        .groupby("level", observed=True)
        .apply(
            lambda g: pd.Series(
                {
                    "重复次数": len(g),
                    "利润_均值估计": g.est_profit.mean(),
                    "利润_偏差": g.bias_profit.mean(),
                    "利润_RMSE": float(np.sqrt((g.bias_profit**2).mean())),
                    "利润_覆盖真值率": g.cover_profit.mean(),
                    "转化_均值估计": g.est_conv.mean(),
                    "转化_偏差": g.bias_conv.mean(),
                    "转化_RMSE": float(np.sqrt((g.bias_conv**2).mean())),
                    "转化_覆盖真值率": g.cover_conv.mean(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    save_table(summary, "r1_repeats_summary")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, col, truth_col, title, unit in (
        (axes[0], "est_conv", "truth_conv", "转化率 ITT 估计的重复分布", ""),
        (axes[1], "est_profit", "truth_profit", "人均净贡献利润 ITT 估计的重复分布", " 元/人"),
    ):
        for level, color in (("L0", METHOD_COLORS["ipw"]), ("L1", METHOD_COLORS["dr"])):
            sub = df[df["level"] == level]
            ax.hist(sub[col], bins=30, alpha=0.55, color=color, label=f"{level}（R={len(sub)}）")
            ax.axvline(sub[truth_col].iloc[0], color=color, ls="--", lw=1.5)
        ax.set_xlabel(f"ITT 估计{unit}")
        ax.set_ylabel("频数")
        ax.set_title(f"{title}\n虚线 = 真值")
        ax.legend(fontsize=8)
    add_source_note(fig, f"seed={_seed(cfg)} | R={r} 次独立重复")
    save_fig(fig, "r1_repeats_distribution")
    return summary


# --------------------------------------------------------------------------- #
def main() -> int:
    cfg = load_config()
    print(f"[config] seed={_seed(cfg)}  data={cfg.require('project.data_source_label')}")

    print("[1/6] 样本量与功效曲线 ...")
    ss = step_sample_size(cfg)
    step_sample_size_curve(cfg)
    print(f"      n_per_group={ss.n_per_group.iloc[0]}  n_total={ss.n_total.iloc[0]}  "
          f"binding={ss.binding_metric.iloc[0]}")

    print("[2/6] AA 校验（1000 次无效应重复）...")
    aa = step_aa(cfg)
    for _, row in aa.iterrows():
        print(f"      {row['指标']}: FPR={row['假阳性率']:.4f}  KS p={row['KS_p值']:.3f}")

    print("[3/6] 主实验 ITT（L0/L1/L2）...")
    itt_df, aux = step_main_experiment(cfg)
    for _, row in itt_df.iterrows():
        print(f"      {row['层级']} {row['指标']}: 估计 {row['ITT估计']:+.4f}  "
              f"真值 {row['真值']:+.4f}  CI=[{row['CI下界']:+.4f}, {row['CI上界']:+.4f}]")

    print("[4/6] 护栏非劣效 + 功效分析 ...")
    df_l1, _ = _run_level(cfg, "L1")
    guard = step_guardrail(cfg, df_l1)
    for _, row in guard.iterrows():
        print(f"      {row['检验']}: 差值 {row['差值_pp']:+.3f}pp -> {row['结论']}")
    step_guardrail_power(cfg, df_l1)

    print("[5/6] 多重比较（Holm）...")
    mult = step_multiplicity(cfg, itt_df)
    for _, row in mult.iterrows():
        print(f"      {row['指标']}: p={row['原始p值']:.4g} -> 校正 {row['校正后p值']:.4g}  "
              f"拒绝={row['是否拒绝']}")

    print(f"[6/6] 重复实验 R={cfg.require('evaluation.repeats_r')} ...")
    rep = step_repeats(cfg)
    for _, row in rep.iterrows():
        print(f"      {row['level']}: 利润偏差 {row['利润_偏差']:+.4f}、RMSE {row['利润_RMSE']:.4f}、"
              f"覆盖率 {row['利润_覆盖真值率']:.3f} | 转化率覆盖率 {row['转化_覆盖真值率']:.3f}")

    print(f"\n[done] 表格 -> {figures_dir().parent / 'tables'}")
    print(f"[done] 图   -> {figures_dir()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
