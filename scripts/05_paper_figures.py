"""第五阶段：论文组图（6 张组图 + 1 张技术路线图）。

为什么单独一个脚本
------------------
正文要压到 10 页，14 张单图必须改成组图。组图不是把单图拼起来，而是
**按论点重新组织子图**：一张组图只讲一件事，四个子图分别给证据链的四个环节。

数据来源纪律
------------
除技术路线图（流程图，非数据产物）外，**每一个数字都从 ``outputs/tables/*.csv``
读取**，脚本内不写任何业务常数。逐用户利润分布与 CATE 散点需要个体级数据，
分别来自 ``outputs/tables/r1_analysis_frame_clean.csv`` 与
``outputs/tables/r2_cate_predictions.csv``（后者由本脚本按 03_cate_obs.py 的
同一套切分与估计器生成并缓存，见 ``ensure_cate_predictions``）。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\05_paper_figures.py

产物：``outputs/figures/paper/fig0_roadmap.png`` … ``fig6_policy.png``（dpi=300）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib
import matplotlib.ticker as mticker

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Patch

from causal_growth.viz import (
    METHOD_COLORS,
    METHOD_LABELS,
    STRATEGY_COLORS,
    STRATEGY_LABELS,
    add_source_note,
    apply_style,
    available_cjk_font,
    save_fig,
)

TABLES = ROOT / "outputs" / "tables"
SUBDIR = "paper"
DPI = 300
SEED = 20240101

# 论文缩放到 0.85 倍版心宽度后仍要清楚：标题 10 / 标签 9 / 刻度 8（正文 12pt 基准）
FS_TITLE, FS_LABEL, FS_TICK, FS_LEG = 10, 9, 8, 8

# 三个学习器的固定配色：沿用 viz.METHOD_COLORS 的红 / 蓝 / 绿
LEARNER_COLORS = {
    "T-learner": METHOD_COLORS["naive"],
    "S-learner": METHOD_COLORS["ipw"],
    "Causal Forest": METHOD_COLORS["dr"],
}
# 四种观察性方法：沿用 viz.METHOD_COLORS
OBS_ORDER = ["naive", "psm", "ipw", "dr"]
OBS_LABELS = {
    "naive": "Naive 差分",
    "psm": "PSM",
    "ipw": "IPW",
    "dr": "DR（AIPW）",
}


# --------------------------------------------------------------------------- #
# 公共工具
# --------------------------------------------------------------------------- #
def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(TABLES / name)


def _panel(ax: plt.Axes, letter: str, title: str) -> None:
    """统一子图编号风格：标题前缀 (a)(b)(c)(d)。"""
    ax.set_title(f"({letter}) {title}", fontsize=FS_TITLE, pad=5)
    ax.tick_params(labelsize=FS_TICK)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _legend(ax: plt.Axes, **kw) -> None:
    kw.setdefault("fontsize", FS_LEG)
    kw.setdefault("frameon", True)
    kw.setdefault("framealpha", 0.9)
    ax.legend(**kw)


def _finish(fig: plt.Figure, name: str, note: str) -> Path:
    add_source_note(fig, note)
    path = save_fig(fig, name, subdir=SUBDIR, dpi=DPI)
    print(f"    -> {path.relative_to(ROOT)}")
    return path


def ensure_cate_predictions() -> pd.DataFrame:
    """逐用户 CATE 预测（fig4a 的六边形分箱需要个体级数据）。

    表里没有逐用户预测，故按 ``scripts/03_cate_obs.py`` 中 ``run_cate`` 的同一套
    切分与同一套估计器重算一次并缓存到 ``outputs/tables/r2_cate_predictions.csv``
    （约 30 秒）。重算结果与 ``r2_cate_comparison.csv`` 的 RMSE / R² 逐位一致，
    因此图与表不会打架。
    """
    path = TABLES / "r2_cate_predictions.csv"
    if path.exists():
        return pd.read_csv(path)

    from causal_growth import dgp
    from causal_growth.config import load_config
    from causal_growth.data.split import train_val_test_split
    from causal_growth.estimate.cate import CAUSAL_METHODS, estimate_cate

    print("    [缓存缺失] 重算逐用户 CATE 预测（约 30 秒）...")
    cfg = load_config()
    pop = dgp.assign_random(cfg, dgp.build("L1", cfg, 0))
    split = train_val_test_split(
        len(pop),
        test_size=float(cfg.require("evaluation.test_size")),
        val_size=float(cfg.require("evaluation.val_size")),
        master_seed=int(cfg.require("project.master_seed")),
        index=0,
    )
    out = pd.DataFrame(
        {
            "user_id": np.arange(len(pop), dtype=int)[split.test],
            "tau_true": pop.truth.cate_profit[split.test],
        }
    )
    for method in CAUSAL_METHODS:
        out[method] = estimate_cate(pop, cfg, split, outcome="net_profit", method=method).tau_test
    out.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.6f")
    return out


# --------------------------------------------------------------------------- #
# 图 0：技术路线图（流程图，唯一不看 CSV 的图）
# --------------------------------------------------------------------------- #
def fig0_roadmap() -> Path:
    """八步技术路线：业务问题 → 数据 → DGP → 实验 → 异质/观察 → 优化 → 评估 → 决策。

    配色与 STRATEGY_COLORS / METHOD_COLORS 协调：灰（无策略）→ 紫（SQL 层，
    对应 ITT 色）→ 蓝（DGP）→ 绿（随机实验，对应 DR 色）→ 橙（观察性）→
    深蓝（优化，对应背包色）→ 红（评估）→ 黑（决策，对应真值最优色）。
    """
    steps = [
        (
            "业务问题",
            "加购未支付用户首单转化率约 10%\n决策：是否发券、发给谁、发多大面额",
            STRATEGY_COLORS["no_coupon"],
        ),
        (
            "数据建模：五表 / SQLite",
            "用户·事件·分配·订单·结果 五张关系表\n6 视图 + 19 命名查询，红线写成 DDL 约束",
            METHOD_COLORS["itt"],
        ),
        (
            "分层 DGP：L0–L3",
            "每层只放松一条假设\n解析真值 τ(x) 可算，估计才有对照",
            STRATEGY_COLORS["target_greedy"],
        ),
        (
            "随机实验：ITT / AA / 护栏",
            "样本量双指标取大、AA 校验 1000 次\nWelch t + Holm 校正 + 非劣效上界",
            METHOD_COLORS["dr"],
        ),
        (
            "异质性与观察性",
            "T/S-learner 对 Causal Forest\nPSM · IPW · DR 随混淆强度 λ 失效",
            METHOD_COLORS["psm"],
        ),
        (
            "预算约束优化",
            "c(X) = 面额 × 核销概率\n贪心 · 0-1 背包 · 线性松弛上界 · 精确 DP",
            STRATEGY_COLORS["target_knapsack"],
        ),
        (
            "四指标评估",
            "CATE RMSE · 排序 · 策略价值 · regret\n训练/验证/测试按用户分离",
            STRATEGY_COLORS["all"],
        ),
        (
            "决策建议",
            "定向发券：每元回报 0.77 → 1.97 元\n达真值最优上界 84.9%",
            STRATEGY_COLORS["oracle"],
        ),
    ]

    fig = plt.figure(figsize=(11, 4.6))
    ax = fig.add_axes([0.0, 0.07, 1.0, 0.91])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    w, h = 0.185, 0.32
    top_y, bot_y = 0.70, 0.26
    xs = [0.110, 0.360, 0.610, 0.860]
    pos = [(x, top_y) for x in xs] + [(x, bot_y) for x in reversed(xs)]

    for idx, ((title, body, color), (x, y)) in enumerate(zip(steps, pos)):
        box = FancyBboxPatch(
            (x - w / 2, y - h / 2),
            w,
            h,
            boxstyle="round,pad=0.008,rounding_size=0.018",
            linewidth=1.5,
            edgecolor=color,
            facecolor=color,
            alpha=0.13,
            zorder=2,
        )
        ax.add_patch(box)
        ax.add_patch(
            FancyBboxPatch(
                (x - w / 2, y - h / 2),
                w,
                h,
                boxstyle="round,pad=0.008,rounding_size=0.018",
                linewidth=1.5,
                edgecolor=color,
                facecolor="none",
                zorder=3,
            )
        )
        ax.add_patch(Circle((x - w / 2 + 0.016, y + h / 2 - 0.035), 0.0155, color=color, zorder=4))
        ax.text(
            x - w / 2 + 0.016,
            y + h / 2 - 0.0355,
            str(idx + 1),
            ha="center",
            va="center",
            fontsize=7.5,
            color="white",
            zorder=5,
            fontweight="bold",
        )
        ax.text(
            x,
            y + h / 2 - 0.070,
            title,
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=color,
            zorder=5,
        )
        ax.text(
            x,
            y - 0.030,
            body,
            ha="center",
            va="center",
            fontsize=7.2,
            color="#333333",
            linespacing=1.5,
            zorder=5,
        )

    arrow_kw = dict(arrowstyle="-|>", linewidth=1.5, mutation_scale=12, shrinkA=0, shrinkB=0, zorder=1)
    # 第一行：左 → 右
    for i in range(3):
        ax.add_patch(
            FancyArrowPatch(
                (xs[i] + w / 2 + 0.004, top_y), (xs[i + 1] - w / 2 - 0.004, top_y), color="#555555", **arrow_kw
            )
        )
    # 转行：第 4 步 → 第 5 步（右侧竖直向下）
    ax.add_patch(
        FancyArrowPatch((xs[3], top_y - h / 2 - 0.004), (xs[3], bot_y + h / 2 + 0.004), color="#555555", **arrow_kw)
    )
    # 第二行：右 → 左
    for i in range(3, 0, -1):
        ax.add_patch(
            FancyArrowPatch(
                (xs[i] - w / 2 - 0.004, bot_y), (xs[i - 1] + w / 2 + 0.004, bot_y), color="#555555", **arrow_kw
            )
        )

    ax.text(0.012, 0.965, "数据与设计", fontsize=8.5, color="#888888", style="italic", va="top")
    ax.text(0.012, 0.045, "估计与决策", fontsize=8.5, color="#888888", style="italic", va="bottom")
    return _finish(fig, "fig0_roadmap", "seed=20240101 | 技术路线图（本文流程设计，非数据产物；数字见正文与表）")


# --------------------------------------------------------------------------- #
# 图 1：数据层证据（零膨胀 / 分组 / 渠道 / 脏数据）
# --------------------------------------------------------------------------- #
def fig1_data() -> Path:
    frame = pd.read_csv(TABLES / "r1_analysis_frame_clean.csv", usecols=["net_profit"])
    profit = frame["net_profit"].to_numpy()
    zero_share = float((profit == 0).mean())
    n_user = int(profit.size)
    aux = _read("r1_auxiliary.csv")
    funnel = _read("r1_sql_channel_funnel.csv").sort_values("conversion_rate", ascending=False)
    dirty = _read("r1_quality_dirty.csv")

    # (d) 分渠道购物车缺失率：从质量表里"MNAR 证据"一行的明细解析（该行给出各渠道计数）
    mnar_row = dirty[dirty["检查项"].astype(str).str.contains("MNAR", na=False)].iloc[0]
    import re

    detail = str(mnar_row["详情"])
    miss = {
        ch: int(num) / int(den)
        for ch, _pct, num, den in re.findall(r"([a-z]+)\s+([\d.]+)%（(\d+)/(\d+)）", detail)
    }
    overall_row = dirty[dirty["检查项"].astype(str).str.contains("cart 缺失率", na=False)].iloc[0]
    overall_missing = float(overall_row["数值"])

    fig, axes = plt.subplots(2, 2, figsize=(10, 6))
    fig.subplots_adjust(hspace=0.52, wspace=0.26, top=0.92, left=0.085, right=0.98)

    # (a) 人均利润零膨胀
    ax = axes[0, 0]
    ax.hist(profit, bins=np.linspace(-40, 85, 70), color=METHOD_COLORS["itt"], alpha=0.85, edgecolor="none")
    ax.set_yscale("log")
    ax.set_xlabel("人均净贡献利润（元/人，30 天窗口）", fontsize=FS_LABEL)
    ax.set_ylabel("用户数（对数刻度）", fontsize=FS_LABEL)
    n_nonzero = int((profit != 0).sum())
    ax.annotate(
        f"利润 = 0 的用户占 {zero_share * 100:.1f}%\n（{n_nonzero:,} / {n_user:,} 人非零）\n"
        f"标准差 {profit.std(ddof=1):.2f} 元，均值 {profit.mean():.2f} 元",
        xy=(0.97, 0.97),
        xycoords="axes fraction",
        va="top",
        ha="right",
        fontsize=FS_TICK,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#BBBBBB", alpha=0.92),
    )
    ax.annotate(
        "0 元处为尖峰",
        xy=(0.0, (n_user - n_nonzero) * 0.35),
        xytext=(0.22, 0.55),
        textcoords="axes fraction",
        fontsize=FS_TICK,
        color="#6A1B9A",
        arrowprops=dict(arrowstyle="->", color="#6A1B9A", lw=0.9),
    )
    _panel(ax, "a", "人均利润高度零膨胀")

    # (b) 分组转化率
    ax = axes[0, 1]
    conv = aux["转化率"].to_numpy() * 100
    labels = ["对照组", "处理组"]
    bars = ax.bar(labels, conv, color=[STRATEGY_COLORS["no_coupon"], STRATEGY_COLORS["target_greedy"]], width=0.5)
    for b, v, n in zip(bars, conv, aux["用户数"].to_numpy()):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.35, f"{v:.2f}%", ha="center", fontsize=FS_LABEL)
        ax.text(b.get_x() + b.get_width() / 2, 0.45, f"n={n:,}", ha="center", fontsize=FS_TICK, color="white")
    ax.annotate(
        f"ITT 转化 +{conv[1] - conv[0]:.2f} 个百分点",
        xy=(0.5, 0.90),
        xycoords="axes fraction",
        ha="center",
        fontsize=FS_TICK,
        bbox=dict(boxstyle="round,pad=0.3", fc="#FFF3E0", ec="#FB8C00"),
    )
    ax.set_ylim(0, max(conv) * 1.35)
    ax.set_ylabel("7 天转化率（%）", fontsize=FS_LABEL)
    _panel(ax, "b", "随机分组的转化率差")

    # (c) 分渠道转化率
    ax = axes[1, 0]
    vals = funnel["conversion_rate"].to_numpy() * 100
    chs = funnel["channel"].to_numpy()
    bars = ax.bar(chs, vals, color=STRATEGY_COLORS["target_greedy"], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.08, f"{v:.2f}%", ha="center", fontsize=FS_TICK)
    ax.set_ylim(10, max(vals) * 1.06)
    ax.set_xlabel("渠道", fontsize=FS_LABEL)
    ax.set_ylabel("转化率（%，纵轴自 10% 起）", fontsize=FS_LABEL)
    _panel(ax, "c", "分渠道转化率：差异真实存在")

    # (d) 分渠道购物车缺失率
    ax = axes[1, 1]
    order = ["search", "feed", "other", "xhs"]
    vals = np.array([miss[ch] * 100 for ch in order])
    bars = ax.bar(order, vals, color=STRATEGY_COLORS["all"], width=0.55, alpha=0.85)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.22, f"{v:.2f}%", ha="center", fontsize=FS_TICK)
    ax.axhline(overall_missing * 100, color="#333333", ls="--", lw=1.2)
    ax.text(
        -0.45,
        overall_missing * 100 + 0.60,
        f"渠道加权 {overall_missing * 100:.2f}%",
        ha="left",
        fontsize=FS_TICK,
        color="#333333",
    )
    ax.set_xlim(-0.6, len(order) - 0.4)
    ax.set_ylim(0, max(vals) * 1.3)
    ax.set_xlabel("渠道", fontsize=FS_LABEL)
    ax.set_ylabel("购物车金额缺失率（%）", fontsize=FS_LABEL)
    _panel(ax, "d", "脏数据层：渠道差异化缺失")

    return _finish(
        fig,
        "fig1_data",
        "seed=20240101 | 200,000 用户；缺失率取自 dirty 层质量表；渠道口径见 SQL 视图 channel_funnel",
    )


# --------------------------------------------------------------------------- #
# 图 2：实验设计（样本量 / AA / 护栏 / 重复实验）
# --------------------------------------------------------------------------- #
def fig2_design() -> Path:
    ss = _read("r1_sample_size.csv").iloc[0]
    curve_c = _read("r1_sample_size_curve_conversion.csv").sort_values("mde_conversion")
    curve_p = _read("r1_sample_size_curve_profit.csv").sort_values("mde_profit")
    aa = _read("r1_aa_summary.csv")
    guard = _read("r1_guardrail.csv")
    power = _read("r1_guardrail_power.csv")
    reps = _read("r1_repeats_raw.csv")
    rep_sum = _read("r1_repeats_summary.csv")

    fig, axes = plt.subplots(2, 2, figsize=(10, 6.2))
    fig.subplots_adjust(hspace=0.62, wspace=0.30, top=0.90, left=0.085, right=0.98)

    # (a) 样本量随 MDE 的双曲线
    ax = axes[0, 0]
    ax.set_yscale("log")
    ax.set_xscale("log")
    ax.plot(
        curve_c["mde_conversion"] * 100,
        curve_c["n_per_group_conversion"],
        color=METHOD_COLORS["itt"],
        marker="o",
        ms=2.6,
        lw=1.5,
        label="转化率指标",
    )
    ax.set_xlabel("转化的最小可检测效应（百分点）", fontsize=FS_LABEL, color=METHOD_COLORS["itt"])
    ax.set_ylabel("每组样本量（对数）", fontsize=FS_LABEL)
    ax.tick_params(axis="x", colors=METHOD_COLORS["itt"], labelsize=FS_TICK)
    ax.set_xticks([0.5, 1.0, 2.0, 3.0])
    ax.set_xticklabels(["0.5", "1.0", "2.0", "3.0"])
    ax.xaxis.set_minor_locator(mticker.NullLocator())

    ax2 = ax.twiny()
    ax2.set_xscale("log")
    ax2.plot(
        curve_p["mde_profit"],
        curve_p["n_per_group_profit"],
        color=STRATEGY_COLORS["target_greedy"],
        marker="s",
        ms=2.6,
        lw=1.5,
        label="利润指标",
    )
    ax2.set_xlabel("利润的最小可检测效应（元/人）", fontsize=FS_LABEL, color=STRATEGY_COLORS["target_greedy"])
    ax2.tick_params(axis="x", colors=STRATEGY_COLORS["target_greedy"], labelsize=FS_TICK)
    ax2.set_xticks([0.2, 0.3, 0.5, 1.0, 2.0])
    ax2.set_xticklabels(["0.2", "0.3", "0.5", "1.0", "2.0"])
    ax2.xaxis.set_minor_locator(mticker.NullLocator())
    ax2.spines["top"].set_visible(True)
    ax2.spines["right"].set_visible(False)

    ax.plot(
        [1.0],
        [float(ss["n_per_group_conversion"])],
        marker="*",
        ms=13,
        color=METHOD_COLORS["itt"],
        zorder=5,
    )
    ax2.plot([0.5], [float(ss["n_per_group_profit"])], marker="*", ms=13, color=STRATEGY_COLORS["target_greedy"], zorder=5)
    ax.annotate(
        f"约束者：转化率\n每组 {int(ss['n_per_group_conversion']):,} → 合计 {int(ss['n_total']):,}",
        xy=(0.03, 0.10),
        xycoords="axes fraction",
        va="bottom",
        fontsize=FS_TICK,
        bbox=dict(boxstyle="round,pad=0.3", fc="#FFF3E0", ec="#FB8C00"),
    )
    handles = [
        Line2D([], [], color=METHOD_COLORS["itt"], marker="o", ms=4, label="转化率指标"),
        Line2D([], [], color=STRATEGY_COLORS["target_greedy"], marker="s", ms=4, label="利润指标"),
        Line2D([], [], color="none", marker="*", ms=10, markerfacecolor="#555555", label="设计取值"),
    ]
    _legend(ax, handles=handles, loc="upper right")
    _panel(ax, "a", "样本量：两条曲线分别取大")

    # (b) AA 校验：假阳性率与 95% 区间
    ax = axes[0, 1]
    fpr = aa["假阳性率"].to_numpy() * 100
    lo = (aa["假阳性率"] - aa["FPR_95CI_下界"]).to_numpy() * 100
    hi = (aa["FPR_95CI_上界"] - aa["假阳性率"]).to_numpy() * 100
    xt = ["转化率（两比例 z）", "净增量利润（Welch t）"]
    bars = ax.bar(xt, fpr, yerr=[lo, hi], capsize=5, width=0.45, color=[METHOD_COLORS["ipw"], METHOD_COLORS["dr"]])
    for b, v, h in zip(bars, fpr, hi):
        ax.text(b.get_x() + b.get_width() / 2 + 0.25, v + h * 0.05, f"{v:.1f}%", ha="left", fontsize=FS_LABEL)
    ax.axhline(5.0, color="red", ls="--", lw=1.2)
    ax.text(1.42, 5.3, "名义 α = 5%", color="red", fontsize=FS_TICK, ha="right")
    ax.set_ylim(0, max(fpr + hi) * 1.85)
    ax.set_ylabel("假阳性率（%）", fontsize=FS_LABEL)
    txt = "　".join(
        f"{m}：p 均值={r['p值均值']:.3f}，KS p={r['KS_p值']:.3f}"
        for m, (_, r) in zip(["转化", "利润"], aa.iterrows())
    )
    ax.annotate(
        txt + "\n（1000 次无效应重复，KS 不拒绝 Uniform）",
        xy=(0.03, 0.99),
        xycoords="axes fraction",
        va="top",
        fontsize=6.8,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#BBBBBB", alpha=0.92),
    )
    ax.tick_params(labelsize=7)
    _panel(ax, "b", "AA 校验：p 值分布与名义水平一致")

    # (c) 护栏单侧置信上界
    ax = axes[1, 0]
    ni = guard[guard["检验"].astype(str).str.contains("非劣效", na=False)].iloc[0]
    d = float(ni["差值_pp"])
    ub = float(ni["单侧CI上界_pp"])
    margin = float(ni["界值_pp"])
    ax.axhline(0, color="#333333", lw=0.9)
    ax.axvline(0, color="#333333", lw=0.9, ls=":")
    ax.axvline(margin, color="red", lw=1.6, ls="--")
    ax.axvline(ub, color=METHOD_COLORS["dr"], lw=1.0, ls="-.")
    ax.plot([-2.4, d], [0, 0], color=METHOD_COLORS["ipw"], lw=5, alpha=0.35, solid_capstyle="butt")
    ax.plot([d, ub], [0, 0], color=METHOD_COLORS["ipw"], lw=5, alpha=0.85, solid_capstyle="butt")
    ax.plot([d], [0], marker="o", ms=7, color=METHOD_COLORS["ipw"], zorder=5)
    ax.annotate(f"点估计 {d:+.2f}", xy=(d, 0), xytext=(d - 0.05, 0.28), fontsize=FS_TICK, ha="right", color=METHOD_COLORS["ipw"])
    ax.annotate(f"单侧 95% 上界 {ub:.2f}", xy=(ub, 0), xytext=(ub + 0.04, -0.30), fontsize=FS_TICK, color=METHOD_COLORS["dr"])
    ax.annotate(f"界值 {margin:.1f} pp", xy=(margin, 0), xytext=(margin + 0.03, 0.34), fontsize=FS_TICK, color="red")
    ax.text(-2.3, -0.32, "← 单侧区间无下界", fontsize=FS_TICK, color="#666666")
    ax.set_xlim(-2.4, 0.95)
    ax.set_ylim(-0.55, 0.55)
    ax.set_yticks([])
    ax.set_xlabel("退款率差（处理组 − 对照组，百分点）", fontsize=FS_LABEL)
    pw = power.set_index("情景")["当前功效"]
    ax.annotate(
        f"结论：非劣效成立，但功效仅 {pw.iloc[1]:.2f}\n"
        f"（真实恶化 {power['真实差值_pp'].iloc[1]:.3f} pp；达 0.8 功效需每组 "
        f"{int(power['达到80%功效所需_每组已转化用户'].iloc[1]):,} 已转化用户）",
        xy=(0.02, 0.97),
        xycoords="axes fraction",
        va="top",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.3", fc="#FFEBEE", ec="#E53935", alpha=0.95),
    )
    _panel(ax, "c", "护栏非劣效：上界合格 ≠ 测得出")

    # (d) 重复 200 次的 ITT 分布
    ax = axes[1, 1]
    for lvl, color, alpha in (("L0", METHOD_COLORS["ipw"], 0.45), ("L1", METHOD_COLORS["itt"], 0.75)):
        v = reps.loc[reps["level"] == lvl, "est_profit"].to_numpy()
        ax.hist(v, bins=24, color=color, alpha=alpha, edgecolor="white", linewidth=0.4, label=f"{lvl}（R={v.size}）")
    truth = float(reps["truth_profit"].iloc[0])
    mean_l1 = float(reps.loc[reps["level"] == "L1", "est_profit"].mean())
    cov = rep_sum.set_index("level")["利润_覆盖真值率"]
    ax.axvline(truth, color="#212121", lw=1.8, ls="--")
    ax.axvline(mean_l1, color=STRATEGY_COLORS["all"], lw=1.2, ls="-.")
    ax.annotate(
        f"均值 {mean_l1:.4f}（偏差 {mean_l1 - truth:+.4f}）\n95% 覆盖率 L0={cov['L0']:.3f}、L1={cov['L1']:.3f}",
        xy=(0.03, 0.97),
        xycoords="axes fraction",
        va="top",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#BBBBBB", alpha=0.92),
    )
    ax.set_xlabel("ITT 估计（净增量利润，元/人）", fontsize=FS_LABEL)
    ax.set_ylabel("重复次数", fontsize=FS_LABEL)
    ax.set_ylim(0, 34)
    handles = [
        Patch(facecolor=METHOD_COLORS["ipw"], alpha=0.45, label=f"L0（R={int(rep_sum['重复次数'].iloc[0])}）"),
        Patch(facecolor=METHOD_COLORS["itt"], alpha=0.75, label=f"L1（R={int(rep_sum['重复次数'].iloc[1])}）"),
        Line2D([], [], color="#212121", ls="--", lw=1.8, label=f"解析真值 {truth:.4f}"),
        Line2D([], [], color=STRATEGY_COLORS["all"], ls="-.", lw=1.2, label=f"200 次均值 {mean_l1:.4f}"),
    ]
    _legend(ax, handles=handles, loc="upper right", fontsize=6.8)
    _panel(ax, "d", "重复实验：分布与真值")

    return _finish(
        fig,
        "fig2_design",
        "seed=20240101 | R=200（ITT）/1000（AA）；护栏功效由已转化用户数解析计算；样本量为每组、1:1",
    )


# --------------------------------------------------------------------------- #
# 图 3：ITT 森林图 + 利润侵蚀分解
# --------------------------------------------------------------------------- #
def fig3_itt() -> Path:
    itt = _read("r1_itt.csv")
    aux = _read("r1_auxiliary.csv")
    face = float(_read("r3_robustness.csv").loc[lambda d: d["扰动"] == "×1.0", "券面额"].iloc[0])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), gridspec_kw={"width_ratios": [1.15, 1.0]})
    fig.subplots_adjust(hspace=0.3, wspace=0.30, top=0.90, bottom=0.21, left=0.085, right=0.985)

    # (a) 森林图
    ax = axes[0]
    prof = itt[itt["指标"] == "net_profit_per_user"].copy()
    levels = list(prof["层级"])
    y = np.arange(len(levels))[::-1]
    est = prof["ITT估计"].to_numpy()
    lo = prof["CI下界"].to_numpy()
    hi = prof["CI上界"].to_numpy()
    truth = prof["真值"].to_numpy()
    ax.errorbar(
        est,
        y,
        xerr=[est - lo, hi - est],
        fmt="o",
        ms=6,
        color=STRATEGY_COLORS["target_greedy"],
        ecolor=STRATEGY_COLORS["target_greedy"],
        elinewidth=1.8,
        capsize=4,
        label="ITT 点估计与 95% CI",
    )
    for yi, t in zip(y, truth):
        ax.plot([t], [yi], marker="D", ms=6, color="red", zorder=5)
    x_text = max(hi) + 0.06
    for yi, e, l, h, t in zip(y, est, lo, hi, truth):
        ax.text(x_text, yi, f"{e:.4f}  [{l:.4f}, {h:.4f}]  真值 {t:.4f}", fontsize=7, va="center", color="#333333")
    ax.axvline(0, color="#888888", lw=0.9, ls=":")
    ax.set_yticks(y, levels)
    ax.set_ylim(-0.55, len(levels) - 0.25)
    ax.set_xlim(min(lo) - 0.06, x_text + 0.78)
    ax.set_xlabel("净增量贡献利润（元/人）", fontsize=FS_LABEL)
    ax.set_ylabel("DGP 层级", fontsize=FS_LABEL)
    handles = [
        Line2D([], [], color=STRATEGY_COLORS["target_greedy"], marker="o", lw=1.8, label="ITT 估计 + 95% CI"),
        Line2D([], [], color="none", marker="D", ms=6, markerfacecolor="red", label="解析真值"),
    ]
    _legend(ax, handles=handles, loc="upper left", fontsize=7.5)
    _panel(ax, "a", "ITT 对真值：六个区间全部覆盖")

    # (b) 利润侵蚀瀑布：多转化增益 − 券成本 + 订单经济差异 = 净增
    ax = axes[1]
    p0, p1 = float(aux["转化率"].iloc[0]), float(aux["转化率"].iloc[1])
    n0, n1 = float(aux["用户数"].iloc[0]), float(aux["用户数"].iloc[1])
    profit0, profit1 = float(aux["人均净贡献利润"].iloc[0]), float(aux["人均净贡献利润"].iloc[1])
    a0, a1 = profit0 / p0, profit1 / p1
    red_share = float(aux["券核销率_占已下单"].iloc[1])
    coupon_per_order = face * red_share
    gain = (p1 - p0) * a1 * 100.0
    coupon_cost = -p0 * coupon_per_order * 100.0
    econ = p0 * ((a1 - a0) + coupon_per_order) * 100.0
    net = (profit1 - profit0) * 100.0

    labels = [
        "多转化增益\n$(p_1-p_0)A_1$",
        "券成本侵蚀\n$-p_0\\cdot$面额×核销率",
        "订单经济差异\n剩余项",
        "净增\n= ITT",
    ]
    vals = [gain, coupon_cost, econ, net]
    bottoms = [0.0, gain, gain + coupon_cost, 0.0]
    colors = [METHOD_COLORS["dr"], STRATEGY_COLORS["all"], STRATEGY_COLORS["random"], STRATEGY_COLORS["oracle"]]
    for i, (v, b, c) in enumerate(zip(vals, bottoms, colors)):
        ax.bar(i, v, bottom=b, color=c, width=0.62)
        ytxt = b + v + (4 if v >= 0 else -4)
        ax.text(i, ytxt, f"{v:+.1f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=FS_LABEL, fontweight="bold")
    for i in range(len(vals) - 1):
        top = bottoms[i] + vals[i]
        ax.plot([i + 0.31, i + 1 - 0.31], [top, top], color="#AAAAAA", lw=0.9, ls="--")
    ax.set_xticks(range(len(labels)), labels, fontsize=FS_TICK)
    ax.set_ylabel("每 100 名用户的利润变化（元）", fontsize=FS_LABEL)
    ax.axhline(0, color="#333333", lw=1.0)
    ax.set_ylim(-52, max(gain, net) + 40)
    ax.annotate(
        f"GMV 人均 +{(float(aux['人均GMV'].iloc[1]) - float(aux['人均GMV'].iloc[0])):.2f} 元（+{(float(aux['人均GMV'].iloc[1]) / float(aux['人均GMV'].iloc[0]) - 1) * 100:.0f}%）\n"
        f"但人均净利润仅 +{(profit1 - profit0):.2f} 元（+{(profit1 / profit0 - 1) * 100:.0f}%）",
        xy=(0.03, 0.02),
        xycoords="axes fraction",
        va="bottom",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.3", fc="#FFF8E1", ec="#FB8C00"),
    )
    _panel(ax, "b", "利润去了哪里：GMV 增长被券成本吃掉")

    return _finish(
        fig,
        "fig3_itt",
        "seed=20240101 | n=200,000；分组统计取自 r1_auxiliary.csv，券面额取自 r3_robustness.csv（×1.0 档）",
    )


# --------------------------------------------------------------------------- #
# 图 4：异质性效应学习
# --------------------------------------------------------------------------- #
def fig4_cate() -> Path:
    pred = ensure_cate_predictions()
    cal = _read("r2_cate_calibration.csv")
    cmp_tab = _read("r2_cate_comparison.csv")
    reps = _read("r2_cate_repeats_raw.csv")

    fig = plt.figure(figsize=(10, 6.6))
    gs = fig.add_gridspec(
        2, 2, hspace=0.62, wspace=0.30, top=0.90, bottom=0.185, left=0.085, right=0.98
    )

    # (a) 分面板六边形分箱：三者共用同一坐标轴范围，差异才可比
    sub = gs[0, 0].subgridspec(1, 3, wspace=0.08)
    true = pred["tau_true"].to_numpy()
    ax_a = []
    for i, (name, col) in enumerate(LEARNER_COLORS.items()):
        key = name.lower().replace("-", "_").replace(" ", "_")
        a = fig.add_subplot(sub[0, i])
        a.hexbin(true, pred[key].to_numpy(), gridsize=28, mincnt=1, cmap="viridis", linewidths=0)
        a.plot([-2.4, 1.8], [-2.4, 1.8], color="red", lw=0.9, ls="--")
        a.set_xlim(-2.45, 1.8)
        a.set_ylim(-6.0, 6.0)
        a.set_title(f"{name}", fontsize=8, pad=3)
        a.text(
            0.96,
            0.96,
            f"sd($\\hat\\tau$)={pred[key].std(ddof=1):.2f}",
            transform=a.transAxes,
            fontsize=6.8,
            ha="right",
            va="top",
            color="white",
            bbox=dict(boxstyle="round,pad=0.18", fc="#333333", ec="none", alpha=0.65),
        )
        a.tick_params(labelsize=7)
        a.spines["top"].set_visible(False)
        a.spines["right"].set_visible(False)
        if i > 0:
            a.set_yticklabels([])
        ax_a.append(a)
    ax_a[1].set_xlabel("真值 $\\tau_\\Pi(x)$（元/人）", fontsize=FS_LABEL)
    ax_a[0].set_ylabel("估计 $\\hat\\tau(x)$", fontsize=FS_LABEL)
    ax_a[0].text(
        0.04,
        0.03,
        f"预测范围\n{pred['t_learner'].min():.1f} ~ {pred['t_learner'].max():.1f}\n（超出画面）",
        transform=ax_a[0].transAxes,
        fontsize=6.5,
        color="white",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.2", fc="#E53935", ec="none", alpha=0.75),
    )
    ax_a[1].set_title("(a) 三种学习器：同一真值、同一坐标轴", fontsize=FS_TITLE, pad=17)

    # (b) Causal Forest 校准曲线
    ax = fig.add_subplot(gs[0, 1])
    cf = cal[cal["方法"] == "Causal Forest"]
    ax.plot(cf["mean_pred"], cf["mean_true"], "o-", color=LEARNER_COLORS["Causal Forest"], ms=5, lw=1.6, label="分箱实际值")
    lim = [min(cf["mean_pred"].min(), cf["mean_true"].min()) - 0.1, max(cf["mean_pred"].max(), cf["mean_true"].max()) + 0.1]
    ax.plot(lim, lim, color="#212121", ls="--", lw=1.1, label="完美校准")
    hi_pt = cf.iloc[-1]
    lo_pt = cf.iloc[0]
    ax.annotate(
        f"高端过冲：预测 {hi_pt['mean_pred']:.2f}\n→ 真值仅 {hi_pt['mean_true']:.2f}（+{hi_pt['diff']:.2f}）",
        xy=(hi_pt["mean_pred"], hi_pt["mean_true"]),
        xytext=(1.05, 0.28),
        fontsize=7,
        arrowprops=dict(arrowstyle="->", color="#555555", lw=0.9),
        bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#BBBBBB"),
    )
    ax.annotate(
        f"低端过冲：{lo_pt['mean_pred']:.2f} → {lo_pt['mean_true']:.2f}",
        xy=(lo_pt["mean_pred"], lo_pt["mean_true"]),
        xytext=(0.05, -0.42),
        fontsize=7,
        arrowprops=dict(arrowstyle="->", color="#555555", lw=0.9),
        bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#BBBBBB"),
    )
    ax.set_xlim(*lim)
    ax.set_ylim(-0.65, max(cf["mean_true"].max(), cf["mean_pred"].max()) + 0.55)
    ax.set_xlabel("预测 CATE 的十分位箱均值（元/人）", fontsize=FS_LABEL)
    ax.set_ylabel("真值 CATE 同箱均值（元/人）", fontsize=FS_LABEL)
    _legend(ax, loc="upper left")
    _panel(ax, "b", "Causal Forest 校准：中段准、两端放大")

    # (c) RMSE 与 R²
    ax = fig.add_subplot(gs[1, 0])
    methods = list(cmp_tab["方法"])
    x = np.arange(len(methods))
    rmse = cmp_tab["CATE_RMSE"].to_numpy()
    r2 = cmp_tab["R2"].to_numpy()
    ax.bar(x - 0.19, rmse, width=0.36, color=[LEARNER_COLORS[m] for m in methods], alpha=0.9, label="CATE RMSE（左轴）")
    for xi, v in zip(x, rmse):
        ax.text(xi - 0.19, v + 0.04, f"{v:.3f}", ha="center", fontsize=FS_TICK)
    ax.set_xticks(x, methods, fontsize=FS_TICK)
    ax.set_ylabel("CATE RMSE（元/人，越小越好）", fontsize=FS_LABEL)
    ax.set_ylim(0, max(rmse) * 1.62)
    ax2 = ax.twinx()
    ax2.plot(x + 0.19, r2, "o--", color="#212121", ms=6, lw=1.2, label="$R^2$（右轴）")
    for xi, v in zip(x, r2):
        ax2.text(xi + 0.19, v + 0.18, f"{v:.2f}", ha="center", fontsize=FS_TICK, color="#212121")
    ax2.axhline(0, color="#888888", lw=0.9, ls=":")
    ax2.set_ylabel("$R^2$（右轴）", fontsize=FS_LABEL)
    ax2.set_ylim(min(r2) - 1.2, 2.8)
    ax2.tick_params(labelsize=FS_TICK)
    ax2.spines["top"].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    _legend(ax, handles=h1 + h2, labels=l1 + l2, loc="upper left", fontsize=7.5)
    _panel(ax, "c", "T-learner 的 $R^2$ 为负：不如直接报均值")

    # (d) 重复 20 次的 RMSE 箱线图
    ax = fig.add_subplot(gs[1, 1])
    order = ["T-learner", "S-learner"]
    data = [reps.loc[reps["method"] == m, "rmse"].to_numpy() for m in order]
    bp = ax.boxplot(data, tick_labels=order, patch_artist=True, widths=0.45, medianprops=dict(color="#212121", lw=1.4))
    for patch, m in zip(bp["boxes"], order):
        patch.set_facecolor(LEARNER_COLORS[m])
        patch.set_alpha(0.45)
    for i, (m, d) in enumerate(zip(order, data), start=1):
        ax.plot([i], [d.mean()], marker="D", ms=6, color="#212121", zorder=5)
    ax.set_xticks(
        [1, 2],
        [
            f"T-learner\n均值 {data[0].mean():.3f}\n95% 区间 [{np.percentile(data[0], 2.5):.3f}, {np.percentile(data[0], 97.5):.3f}]",
            f"S-learner\n均值 {data[1].mean():.3f}\n95% 区间 [{np.percentile(data[1], 2.5):.3f}, {np.percentile(data[1], 97.5):.3f}]",
        ],
        fontsize=7,
    )
    ax.set_ylabel("重复实验的 CATE RMSE（元/人）", fontsize=FS_LABEL)
    ax.set_ylim(0, max(d.max() for d in data) * 1.18)
    ax.annotate(
        f"两组 95% 区间不重叠\n→ 差异非抽样偶然（R={reps['repeat'].nunique()}）",
        xy=(0.97, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.28", fc="#E8F5E9", ec="#2E7D32"),
    )
    _panel(ax, "d", "重复 20 次的稳定性")

    return _finish(
        fig,
        "fig4_cate",
        "seed=20240101 | L1、测试集 60,000 人、按用户切分；真值为解析 CATE，非观测利润差",
    )


# --------------------------------------------------------------------------- #
# 图 5：观察性识别的失效边界
# --------------------------------------------------------------------------- #
def fig5_obs() -> Path:
    lam = _read("r2_lambda_summary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    fig.subplots_adjust(hspace=0.3, wspace=0.26, top=0.90, bottom=0.20, left=0.085, right=0.98)

    truth_by_lambda = lam.groupby("lambda")["真值"].first()

    # (a) 偏差随 λ
    ax = axes[0]
    for m in OBS_ORDER:
        sub = lam[lam["method"] == m].sort_values("lambda")
        ax.plot(sub["lambda"], sub["偏差"], "o-", color=METHOD_COLORS[m], ms=4.5, lw=1.6, label=OBS_LABELS[m])
    ax.plot(truth_by_lambda.index, truth_by_lambda.to_numpy(), color="#212121", ls="--", lw=1.3, label="真值 ATE（随 λ 变化）")
    ax.axhline(0, color="#888888", lw=0.9, ls=":")
    ax.set_xlabel("混淆强度 $\\lambda$", fontsize=FS_LABEL)
    ax.set_ylabel("偏差（元/人，估计 − 真值）", fontsize=FS_LABEL)
    ax.annotate(
        "$\\lambda=0$：三种调整法偏差 $<0.06$\nNaive 已达 "
        f"{lam.loc[(lam['method'] == 'naive') & (lam['lambda'] == 0.0), '偏差'].iloc[0]:.2f}",
        xy=(0.97, 0.42),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#BBBBBB"),
    )
    _legend(ax, loc="upper left")
    _panel(ax, "a", "偏差随混淆强度线性扩大")

    # (b) 覆盖率随 λ
    ax = axes[1]
    for m in OBS_ORDER:
        sub = lam[lam["method"] == m].sort_values("lambda")
        ax.plot(sub["lambda"], sub["覆盖率"], "o-", color=METHOD_COLORS[m], ms=4.5, lw=1.6, label=OBS_LABELS[m])
    ax.axhline(0.95, color="#212121", ls="--", lw=1.1)
    ax.axhline(0.90, color="#E53935", ls=":", lw=1.3)
    ax.text(lam["lambda"].max(), 0.958, "名义 0.95", ha="right", fontsize=FS_TICK, color="#212121")
    ax.text(lam["lambda"].max(), 0.845, "判据 0.90", ha="right", fontsize=FS_TICK, color="#E53935")
    ax.set_ylim(-0.04, 1.10)
    ax.set_xlabel("混淆强度 $\\lambda$", fontsize=FS_LABEL)
    ax.set_ylabel("95% 置信区间覆盖率", fontsize=FS_LABEL)
    ax.annotate(
        "$\\lambda=0.25$ 时偏差仅约真值的 20%\n覆盖率却已跌至 0.75–0.85",
        xy=(0.97, 0.42),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.28", fc="#FFEBEE", ec="#E53935"),
    )
    _panel(ax, "b", "覆盖率崩塌快于偏差增长")

    return _finish(
        fig,
        "fig5_obs",
        "seed=20240101 | L3、每组重复 20 次、n=20,000；λ 网格 7 点；估计器仅用可观测 X",
    )


# --------------------------------------------------------------------------- #
# 图 6：预算约束下的策略价值
# --------------------------------------------------------------------------- #
def fig6_policy() -> Path:
    six = _read("r3_six_strategies.csv")
    scan = _read("r3_budget_scan.csv")
    gap = _read("r3_greedy_gap.csv")

    fig, axes = plt.subplots(2, 2, figsize=(10, 6.4))
    fig.subplots_adjust(hspace=0.58, wspace=0.30, top=0.91, left=0.085, right=0.98)

    six = six.sort_values("incremental_value", ascending=False).reset_index(drop=True)
    keys = list(six["strategy_key"])

    # (a) 六策略增量价值
    ax = axes[0, 0]
    vals = six["incremental_value"].to_numpy()
    colors = [STRATEGY_COLORS[k] for k in keys]
    bars = ax.bar(range(len(keys)), vals, color=colors, width=0.62)
    for i, (b, v, k) in enumerate(zip(bars, vals, keys)):
        if bool(six.loc[i, "over_budget"]):
            b.set_hatch("///")
        pct = six.loc[i, "pct_of_oracle"]
        tag = f"{v:.3f}" if not bool(six.loc[i, "over_budget"]) else f"{v:.3f}\n超预算 5 倍"
        ax.text(i, v + 0.012, tag, ha="center", fontsize=7)
        if pd.notna(pct) and not bool(six.loc[i, "over_budget"]):
            ax.text(i, v / 2, f"{pct:.0f}%", ha="center", color="white", fontsize=FS_TICK, fontweight="bold")
    oracle_v = float(six.loc[six["strategy_key"] == "oracle", "incremental_value"].iloc[0])
    ax.axhline(oracle_v, color=STRATEGY_COLORS["oracle"], ls="--", lw=1.2, label=f"真值最优 {oracle_v:.3f}")
    short = {
        "no_coupon": "不发券",
        "all": "全量发券",
        "random": "随机",
        "target_greedy": "定向-贪心",
        "target_knapsack": "定向-背包",
        "oracle": "真值最优",
    }
    ax.set_xticks(range(len(keys)), [short[k] for k in keys], rotation=18, ha="right", fontsize=7.5)
    ax.set_ylabel("增量价值（元/人）", fontsize=FS_LABEL)
    ax.set_ylim(0, max(vals) * 1.30)
    _legend(ax, loc="upper right", fontsize=7.5)
    _panel(ax, "a", "定向 vs 随机：2.56 倍，且跨过盈亏线")

    # (b) 预算使用率
    ax = axes[0, 1]
    util = six["budget_utilization"].to_numpy() * 100
    ypos = np.arange(len(keys))[::-1]
    bars = ax.barh(ypos, np.clip(util, 0, 112), color=colors, height=0.6)
    for yi, u, b, k in zip(ypos, util, bars, keys):
        if u > 112:
            b.set_hatch("///")
        ax.text(np.clip(u, 0, 112) + 1.5, yi, f"{u:.0f}%" if u > 5 else f"{u:.0f}%", va="center", fontsize=FS_TICK)
    ax.axvline(100, color="#E53935", ls="--", lw=1.2)
    ax.set_yticks(ypos, [STRATEGY_LABELS[k].replace("（预算 B）", "") for k in keys], fontsize=7)
    ax.set_xlim(0, 128)
    ax.set_xlabel("预算使用率（%，100% = 预算 B）", fontsize=FS_LABEL)
    ax.annotate(
        "全量发券实测 500%：价值不可与约束内策略比较",
        xy=(0.30, 0.045),
        xycoords="axes fraction",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.28", fc="#FFEBEE", ec="#E53935"),
    )
    _panel(ax, "b", "预算使用率：谁真的花完了预算")

    # (c) 策略价值随预算倍数变化
    ax = axes[1, 0]
    ax.plot(scan["预算倍数"], scan["价值_随机"], "o-", color=STRATEGY_COLORS["random"], ms=4, lw=1.6, label="随机发券")
    ax.plot(scan["预算倍数"], scan["价值_贪心"], "s-", color=STRATEGY_COLORS["target_greedy"], ms=4, lw=1.8, label="定向-贪心")
    ax.plot(scan["预算倍数"], scan["价值_真值最优"], "^", color=STRATEGY_COLORS["oracle"], ms=4, lw=1.2, ls="--", label="真值最优")
    ax.fill_between(scan["预算倍数"], scan["价值_随机"], scan["价值_贪心"], color=STRATEGY_COLORS["target_greedy"], alpha=0.12)
    ax.set_xlabel("预算倍数（1 = 基准预算）", fontsize=FS_LABEL)
    ax.set_ylabel("策略价值（元/人，增量口径）", fontsize=FS_LABEL)
    ax2 = ax.twinx()
    ax2.plot(scan["预算倍数"], scan["定向相对优势倍数"], ":", color="#6A1B9A", ms=4, marker="d", lw=1.2)
    ax2.set_ylabel("定向相对随机的倍数（右轴）", fontsize=FS_LABEL, color="#6A1B9A")
    ax2.tick_params(labelcolor="#6A1B9A", labelsize=FS_TICK)
    ax2.set_ylim(0.5, 7.2)
    ax2.spines["top"].set_visible(False)
    i_min = int(scan["定向相对优势倍数"].to_numpy().argmax())
    ax2.annotate(
        f"预算最紧时 {scan['定向相对优势倍数'].iloc[i_min]:.2f}×",
        xy=(scan["预算倍数"].iloc[i_min], scan["定向相对优势倍数"].iloc[i_min]),
        xytext=(0.85, 6.1),
        fontsize=7,
        color="#6A1B9A",
        arrowprops=dict(arrowstyle="->", color="#6A1B9A", lw=0.9),
        bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#6A1B9A"),
    )
    i_peak = int(scan["定向增益_相对随机"].to_numpy().argmax())
    ax.annotate(
        f"绝对增益峰值 {scan['定向增益_相对随机'].iloc[i_peak]:+.3f}（预算 ×{scan['预算倍数'].iloc[i_peak]:.1f}）",
        xy=(0.97, 0.04),
        xycoords="axes fraction",
        ha="right",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.28", fc="#E3F2FD", ec="#1E88E5"),
    )
    _legend(ax, loc="upper left", fontsize=7.5)
    _panel(ax, "c", "预算越紧，定向越是必需品")

    # (d) 贪心 / LP 上界 / 精确 DP
    ax = axes[1, 1]
    items = list(gap["项"])
    x = np.arange(len(items))
    greedy = gap["贪心估计价值"].to_numpy()
    lp = gap["LP松弛上界"].to_numpy()
    dp = gap["精确DP"].to_numpy()
    ax.bar(x - 0.26, greedy, width=0.24, color=STRATEGY_COLORS["target_greedy"], label="贪心")
    ax.bar(x, lp, width=0.24, color=STRATEGY_COLORS["no_coupon"], label="线性松弛上界")
    ax.bar(x + 0.26, np.nan_to_num(dp, nan=0.0), width=0.24, color=STRATEGY_COLORS["target_knapsack"], label="精确 DP")
    ax.set_yscale("log")
    for xi, g, l, d in zip(x, greedy, lp, dp):
        ax.text(xi - 0.26, g * 1.12, f"{g:.1f}", ha="center", fontsize=7)
        ax.text(xi, l * 1.12, f"{l:.1f}", ha="center", fontsize=7)
        if np.isfinite(d):
            ax.text(xi + 0.26, d * 1.12, f"{d:.1f}", ha="center", fontsize=7)
        else:
            ax.text(xi + 0.26, 2.2, "不可行", ha="center", fontsize=7, rotation=90, color="#555555")
    ax.set_xticks(x, items, fontsize=7)
    ax.set_ylabel("策略总价值（元，对数刻度）", fontsize=FS_LABEL)
    ax.set_ylim(1, max(lp) * 14)
    ratio = float(gap.loc[gap["项"].str.startswith("全规模"), "贪心/上界"].iloc[0])
    ax.annotate(
        f"全规模：贪心 = 上界的 {ratio * 100:.4f}%\n反例：贪心 12.00 vs 精确 18.00（−33%）",
        xy=(0.03, 0.99),
        xycoords="axes fraction",
        va="top",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="#BBBBBB"),
    )
    _legend(ax, loc="upper right", fontsize=7.5)
    _panel(ax, "d", "贪心近似程度：三个规模三种结论")

    return _finish(
        fig,
        "fig6_policy",
        "seed=20240101 | 独立测试集 60,000 人；预算 B=10,042 元；六策略同预算同人群；DP 为降规模实例",
    )


# --------------------------------------------------------------------------- #
def main() -> int:
    apply_style()
    font = available_cjk_font()
    print(f"[字体] {font}")
    print("[1/7] 技术路线图 ...")
    fig0_roadmap()
    print("[2/7] 数据层证据 ...")
    fig1_data()
    print("[3/7] 实验设计 ...")
    fig2_design()
    print("[4/7] ITT 与利润分解 ...")
    fig3_itt()
    print("[5/7] 异质性效应 ...")
    fig4_cate()
    print("[6/7] 观察性识别 ...")
    fig5_obs()
    print("[7/7] 政策优化 ...")
    fig6_policy()
    print("完成：7 张图已写入 outputs/figures/paper/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
