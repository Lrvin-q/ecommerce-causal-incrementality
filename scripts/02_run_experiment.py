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

    # S1：约束者翻转的**临界 MDE**。两个指标的样本量都与 MDE² 成反比，
    # 令 n_profit(Δ*) = n_conversion 得 Δ* = Δ_profit · sqrt(n_profit / n_conv)。
    # 低于 Δ* 时约束者从转化率翻转为利润；这就是"预算/合格用户口径"下
    # 0.5 元/人的业务含义必须被拿出来对照的原因。
    n_conv = int(ss.n_per_group_conversion)
    n_prof = int(ss.n_per_group_profit)
    mde_profit = float(cfg.require("experiment.mde.profit_per_user"))
    df["临界利润MDE_元每人"] = mde_profit * float(np.sqrt(n_prof / max(n_conv, 1)))
    df["约束者"] = ss.binding_metric

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

    # 利润侵蚀分解：每 100 名用户的利润变化 = 多转化收益 − 券成本 + 订单经济差异。
    # 三项与净增在**代数上恒等**（不是拟合），因此这也是分解口径的自检。
    # 旧稿只把结果画在图 4(b) 里，表 B1 找不到"利润分解表"，读者无法复算。
    p0 = float(aux["转化率"].iloc[0])
    p1 = float(aux["转化率"].iloc[1])
    profit0 = float(aux["人均净贡献利润"].iloc[0])
    profit1 = float(aux["人均净贡献利润"].iloc[1])
    a0, a1 = profit0 / p0, profit1 / p1
    red_share = float(aux["券核销率_占已下单"].iloc[1])
    face = float(cfg.require("business.coupon_reference_face"))
    gain = (p1 - p0) * a1 * 100.0
    coupon_cost = -p0 * face * red_share * 100.0
    econ = p0 * ((a1 - a0) + face * red_share) * 100.0
    net = (profit1 - profit0) * 100.0
    decomp = pd.DataFrame(
        [
            {"项": "多转化增益", "符号": "(p1−p0)·A1",
             "值_元每百人": gain, "说明": f"A1={a1:.4f} 元/已转化用户（含复购期望）"},
            {"项": "券成本", "符号": "−p0·面额·核销率",
             "值_元每百人": coupon_cost,
             "说明": f"面额 {face:.0f} 元、已下单核销率 {red_share:.4f}"},
            {"项": "订单经济差异（剩余项）", "符号": "p0·[(A1−A0)+面额·核销率]",
             "值_元每百人": econ, "说明": "客单价、成本、退款与复购的综合差异"},
            {"项": "净增 = ITT", "符号": "三项之和",
             "值_元每百人": net, "说明": "与 r1_itt.csv 的 L1 利润 ITT×100 一致"},
            {"项": "代数校验（三项和 − 净增）", "符号": "=0",
             "值_元每百人": gain + coupon_cost + econ - net,
             "说明": "浮点误差内应为 0"},
        ]
    )
    save_table(decomp, "r1_profit_decomposition")

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


#: 护栏的两个分母口径。R1 要求主分析的分母是**随机分配的全部用户**；
#: "已下单为分母"是条件指标（单笔退款质量），只作为灵敏度分析。
GUARDRAIL_DENOMS: tuple[tuple[str, str], ...] = (
    ("R1 全用户（主口径）", "全部分配用户"),
    ("条件口径（灵敏度）", "已下单用户"),
)


def _guardrail_counts(df: pd.DataFrame, denominator: str) -> tuple[int, int, int, int]:
    """返回 ``(处理组退款人数, 处理组分母, 对照组退款人数, 对照组分母)``。"""
    t = df["treatment"].to_numpy() == 1
    conv = df["converted"].to_numpy() == 1
    ref = df["refunded"].to_numpy() == 1
    if denominator == "全部分配用户":
        return int((ref & t).sum()), int(t.sum()), int((ref & ~t).sum()), int((~t).sum())
    return (
        int((ref & t & conv).sum()),
        int((t & conv).sum()),
        int((ref & ~t & conv).sum()),
        int((~t & conv).sum()),
    )


def step_guardrail(cfg, df: pd.DataFrame) -> pd.DataFrame:
    """护栏非劣效检验：退款率，**两套分母并列**。

    R1 规定分析分母是随机分配的全部用户，因此主口径必须是"发生退款的用户数 /
    全部分配用户数"。但全用户口径会把"处理组转化率更高 → 更多人下单 → 更多人
    退款"的构成效应一并算进护栏；条件口径（已下单用户为分母）才回答"单笔退款
    质量是否恶化"。两者可以符号相反，报告必须写清用的是哪一个。

    "不显著" ≠ "安全"：对 0 的双侧检验只作对照，判定一律用单侧上界对预设界值。
    """
    margin = float(cfg.require("experiment.guardrail.noninferiority_margin"))
    alpha_one = float(cfg.require("experiment.guardrail.alpha_one_sided"))
    from causal_growth.estimate.itt import itt_difference_proportions

    rows: list[dict[str, object]] = []
    for label, denominator in GUARDRAIL_DENOMS:
        s_t, n_t, s_c, n_c = _guardrail_counts(df, denominator)
        ni = noninferiority_binary(
            s_t, n_t, s_c, n_c, margin=margin, alpha_one_sided=alpha_one
        )
        sub = df if denominator == "全部分配用户" else df[df["converted"].to_numpy() == 1]
        two = itt_difference_proportions(
            sub, "refunded", alpha=float(cfg.require("experiment.alpha"))
        )
        base = {
            "检验": "非劣效检验（对预设界值）",
            "口径": label,
            "分母": denominator,
            "处理组退款人数": s_t,
            "处理组分母": n_t,
            "对照组退款人数": s_c,
            "对照组分母": n_c,
            "处理组": s_t / n_t,
            "对照组": s_c / n_c,
            "差值_pp": ni.diff * 100,
            "标准误_pp": ni.se * 100,
            "界值_pp": margin * 100,
            "单侧CI上界_pp": ni.ci_one_sided_upper * 100,
            "方法": ni.method,
        }
        rows.append(
            {
                **base,
                "结论": "通过：未显著超过界值" if ni.passed else "未通过：显著超过界值",
                "p值": np.nan,
            }
        )
        rows.append(
            {
                **base,
                "检验": "双侧显著性检验（对 0）",
                "界值_pp": 0.0,
                "单侧CI上界_pp": two.ci_upper * 100,
                "结论": "对 0 显著" if two.p_value < 0.05 else "对 0 不显著（**不等于安全**）",
                "p值": two.p_value,
                "方法": two.method,
            }
        )
    out = pd.DataFrame(rows)
    save_table(out, "r1_guardrail")

    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ypos = {"全部分配用户": 0.22, "已下单用户": -0.22}
    for label, denominator in GUARDRAIL_DENOMS:
        s_t, n_t, s_c, n_c = _guardrail_counts(df, denominator)
        ni = noninferiority_binary(
            s_t, n_t, s_c, n_c, margin=margin, alpha_one_sided=alpha_one
        )
        y = ypos[denominator]
        ax.errorbar(
            [ni.diff * 100], [y],
            xerr=[[0.0], [(ni.ci_one_sided_upper - ni.diff) * 100]],
            fmt="o", capsize=6, lw=2,
            color=METHOD_COLORS["psm"] if denominator == "全部分配用户" else METHOD_COLORS["ipw"],
            label=f"{label}：{ni.diff*100:+.2f}pp，上界 {ni.ci_one_sided_upper*100:+.2f}pp",
        )
    ax.axvline(margin * 100, color="red", ls="--", label=f"非劣效界值 {margin*100:.2f}pp")
    ax.axvline(0, color="grey", ls=":", label="无差异")
    ax.set_xlim(-0.9, margin * 100 + 0.5)
    ax.set_ylim(-0.6, 0.6)
    ax.set_yticks([])
    ax.set_xlabel("退款率差异（百分点，处理组 − 对照组）")
    ax.set_title("护栏非劣效：分母不同，符号可以相反")
    ax.legend(fontsize=7, loc="upper left")
    add_source_note(fig, f"seed={_seed(cfg)} | 单侧 α={alpha_one} | 界值={margin*100:.2f}pp")
    save_fig(fig, "r1_guardrail_ci")
    return out


def step_guardrail_power(cfg, df: pd.DataFrame) -> pd.DataFrame:
    """护栏非劣效检验的功效分析，**两个分母各算一套**。

    全用户口径的分母大得多（20 万而非 2.5 万已转化用户），标准误更小，但它的
    真实差值也更大：处理组转化率更高，"更多人下单"本身就会带来更多退款。
    这个构成效应由 DGP 参数唯一决定，用观测转化率 × DGP 退款率推算，
    与条件口径的 0.225pp（净退款率 ×1.03）不是同一个量。
    """
    from scipy.stats import norm

    margin = float(cfg.require("experiment.guardrail.noninferiority_margin"))
    alpha_one = float(cfg.require("experiment.guardrail.alpha_one_sided"))
    b = cfg.section("business")
    rate_c = float(b["refund_rate"])
    rate_t = rate_c * float(b["refund_rate_treated_multiplier"])

    t = df["treatment"].to_numpy() == 1
    conv = df["converted"].to_numpy() == 1
    p_conv_t = float(conv[t].mean())
    p_conv_c = float(conv[~t].mean())

    rows: list[dict[str, object]] = []
    for label, denominator in GUARDRAIL_DENOMS:
        s_t, n_t, s_c, n_c = _guardrail_counts(df, denominator)
        p_t, p_c = s_t / n_t, s_c / n_c
        se = float(np.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c))

        if denominator == "全部分配用户":
            unit = "全部分配用户"
            true_diff = p_conv_t * rate_t - p_conv_c * rate_c
            scenarios = (
                (0.0, "真实无恶化（0pp）"),
                (true_diff, f"DGP 隐含（转化率构成效应计入，{true_diff*100:.3f}pp）"),
                (margin, f"真实恶化恰在界值（{margin*100:.2f}pp）"),
            )
        else:
            unit = "已转化用户"
            true_diff = rate_c * (float(b["refund_rate_treated_multiplier"]) - 1.0)
            scenarios = (
                (0.0, "真实无恶化（0pp）"),
                (true_diff, f"真实小幅恶化（{true_diff*100:.3f}pp，DGP 设定）"),
                (margin, f"真实恶化恰在界值（{margin*100:.2f}pp）"),
            )

        z_req = norm.ppf(0.80) + norm.ppf(1 - alpha_one)
        p_bar = (p_t + p_c) / 2.0
        for true_d, scenario in scenarios:
            power = float(norm.cdf((margin - true_d) / se - norm.ppf(1 - alpha_one)))
            if margin - true_d <= 0:
                need, total = -1, float("nan")
            else:
                se_req = (margin - true_d) / z_req
                need = int(np.ceil(2.0 * p_bar * (1 - p_bar) / se_req**2))
                total = (
                    float(need) * (1.0 / p_conv_t + 1.0 / p_conv_c)
                    if denominator == "已下单用户"
                    else float(2 * need)
                )
            rows.append(
                {
                    "口径": label,
                    "分母": denominator,
                    "情景": scenario,
                    "真实差值_pp": true_d * 100,
                    "当前_处理组n": n_t,
                    "当前_对照组n": n_c,
                    "当前SE_pp": se * 100,
                    "当前功效": power,
                    "所需_每组": need,
                    "所需_总样本量": total,
                    "所需单位": unit,
                    "界值_pp": margin * 100,
                    "单侧α": alpha_one,
                }
            )
    out = pd.DataFrame(rows)
    save_table(out, "r1_guardrail_power")

    for _, row in out.iterrows():
        if row["情景"].startswith("真实小幅恶化") or row["情景"].startswith("DGP 隐含"):
            print(
                f"      [功效] {row['分母']}：真实差值 {row['真实差值_pp']:+.3f}pp、"
                f"SE {row['当前SE_pp']:.3f}pp → 功效 {row['当前功效']:.3f}"
            )
    return out


def step_srm(cfg, df: pd.DataFrame) -> pd.DataFrame:
    """样本比例失衡检查（Sample Ratio Mismatch，SRM）。

    分流若不成 50/50，"随机实验"的前提就先破了——后面所有 ITT 都不可信。
    判据用卡方（1 自由度，等价于两比例 z 检验的平方），惯例阈值 p < 0.001
    才判定 SRM（Kohavi 等的工程口径：p < 0.05 在小样本上误报太多）。
    """
    from scipy.stats import chi2

    n_t = int((df["treatment"] == 1).sum())
    n_c = int((df["treatment"] == 0).sum())
    n = n_t + n_c
    expected = n / 2.0
    chi = (n_t - expected) ** 2 / expected + (n_c - expected) ** 2 / expected
    p = float(chi2.sf(chi, df=1))
    z = float((n_t - expected) / np.sqrt(n * 0.25))
    out = pd.DataFrame(
        [
            {
                "检查项": "SRM（分流比例）",
                "处理组": n_t,
                "对照组": n_c,
                "期望每组": expected,
                "处理组占比": n_t / n,
                "z统计量": z,
                "卡方统计量": float(chi),
                "p值": p,
                "判定阈值": 0.001,
                "结论": "不拒绝 50/50" if p >= 0.001 else "**存在 SRM，需排查分流实现**",
            }
        ]
    )
    save_table(out, "r1_srm")
    return out


def step_guardrail_sensitivity(cfg, df: pd.DataFrame) -> pd.DataFrame:
    """界值敏感性：同一份差值放到 0.2/0.3/0.5/1.0pp 四个界值下，逐口径看结论。

    界值是可以调的。只报"0.5pp 通过"没有信息量；两个分母同时给出，
    才能看出"结论翻转"究竟来自数据还是来自分母。
    """
    alpha_one = float(cfg.require("experiment.guardrail.alpha_one_sided"))
    rows: list[dict[str, object]] = []
    for label, denominator in GUARDRAIL_DENOMS:
        s_t, n_t, s_c, n_c = _guardrail_counts(df, denominator)
        for margin_pp in (0.2, 0.3, 0.5, 1.0):
            ni = noninferiority_binary(
                s_t, n_t, s_c, n_c, margin=margin_pp / 100.0, alpha_one_sided=alpha_one
            )
            rows.append(
                {
                    "口径": label,
                    "分母": denominator,
                    "界值_pp": margin_pp,
                    "差值_pp": ni.diff * 100,
                    "标准误_pp": ni.se * 100,
                    "单侧CI上界_pp": ni.ci_one_sided_upper * 100,
                    "上界是否低于界值": bool(ni.ci_one_sided_upper < margin_pp / 100.0),
                    "结论": "非劣效成立" if ni.passed else "**非劣效不成立**",
                }
            )
    out = pd.DataFrame(rows)
    save_table(out, "r1_guardrail_sensitivity")
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

    print("[1/7] 样本量与功效曲线 ...")
    ss = step_sample_size(cfg)
    step_sample_size_curve(cfg)
    print(f"      n_per_group={ss.n_per_group.iloc[0]}  n_total={ss.n_total.iloc[0]}  "
          f"binding={ss.binding_metric.iloc[0]}")

    print("[2/7] AA 校验（1000 次无效应重复）...")
    aa = step_aa(cfg)
    for _, row in aa.iterrows():
        print(f"      {row['指标']}: FPR={row['假阳性率']:.4f}  KS p={row['KS_p值']:.3f}")

    print("[3/7] 主实验 ITT（L0/L1/L2）...")
    itt_df, aux = step_main_experiment(cfg)
    for _, row in itt_df.iterrows():
        print(f"      {row['层级']} {row['指标']}: 估计 {row['ITT估计']:+.4f}  "
              f"真值 {row['真值']:+.4f}  CI=[{row['CI下界']:+.4f}, {row['CI上界']:+.4f}]")

    print("[4/7] 护栏非劣效 + 界值敏感性 + 功效分析 ...")
    df_l1, _ = _run_level(cfg, "L1")
    guard = step_guardrail(cfg, df_l1)
    for _, row in guard.iterrows():
        print(f"      [{row['口径']}] {row['检验']}: 差值 {row['差值_pp']:+.3f}pp "
              f"上界 {row['单侧CI上界_pp']:+.3f}pp -> {row['结论']}")
    sens = step_guardrail_sensitivity(cfg, df_l1)
    for _, row in sens.iterrows():
        print(f"      [{row['口径']}] 界值 {row['界值_pp']:.1f}pp: "
              f"单侧上界 {row['单侧CI上界_pp']:+.3f}pp -> {row['结论']}")
    step_guardrail_power(cfg, df_l1)

    print("[5/7] SRM（分流比例）检验 ...")
    srm = step_srm(cfg, df_l1)
    print(f"      {srm.iloc[0]['处理组']:,} / {srm.iloc[0]['对照组']:,}  "
          f"z={srm.iloc[0]['z统计量']:+.3f}  p={srm.iloc[0]['p值']:.4f}  → {srm.iloc[0]['结论']}")

    print("[6/7] 多重比较（Holm）...")
    mult = step_multiplicity(cfg, itt_df)
    for _, row in mult.iterrows():
        print(f"      {row['指标']}: p={row['原始p值']:.4g} -> 校正 {row['校正后p值']:.4g}  "
              f"拒绝={row['是否拒绝']}")

    print(f"[7/7] 重复实验 R={cfg.require('evaluation.repeats_r')} ...")
    rep = step_repeats(cfg)
    for _, row in rep.iterrows():
        print(f"      {row['level']}: 利润偏差 {row['利润_偏差']:+.4f}、RMSE {row['利润_RMSE']:.4f}、"
              f"覆盖率 {row['利润_覆盖真值率']:.3f} | 转化率覆盖率 {row['转化_覆盖真值率']:.3f}")

    print(f"\n[done] 表格 -> {figures_dir().parent / 'tables'}")
    print(f"[done] 图   -> {figures_dir()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
