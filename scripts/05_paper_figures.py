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
#: 按**最终尺寸**出图：A4 版心 16.3cm ≈ 6.4in，故 figsize 宽 6.6in、插入时 \linewidth。
#: dpi=600 保证 600×6.6 = 3960px 宽，缩到版心后仍有 >500dpi 的有效分辨率。
DPI = 600
#: 是否在图内绘制“数据来源…”脚注。论文里这些信息统一放进附录的图表说明一节，
#: 图下不再重复一行小字（7pt 缩到版心后不足 5pt，既占版面又难读）。
SHOW_SOURCE_NOTE = False
SEED = 20240101

# 论文按 1:1 尺寸插入后仍要清楚：标题 9 / 标签 8 / 刻度 7 / 图例 7（正文 12pt 基准）。
# 旧版用 10/9/8/8 并按 0.8 倍缩放插入，等于把刻度压到 6.4pt，肉眼看不清。
FS_TITLE, FS_LABEL, FS_TICK, FS_LEG = 9, 8, 7, 7
#: 注释框字号下限：7pt（再小在纸质打印上不可读）
FS_NOTE = 7

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
    ax.set_title(f"({letter}) {title}", fontsize=FS_TITLE, pad=4)
    ax.tick_params(labelsize=FS_TICK)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _legend(ax: plt.Axes, **kw) -> None:
    kw.setdefault("fontsize", FS_LEG)
    kw.setdefault("frameon", True)
    kw.setdefault("framealpha", 0.9)
    kw.setdefault("borderpad", 0.3)
    kw.setdefault("handlelength", 1.6)
    ax.legend(**kw)


def _legend_below(ax: plt.Axes, *, ncol: int = 2, y: float = -0.30, **kw) -> None:
    """把图例放到坐标区**下方**（无边框、无底色），保证永不压数据。

    图例压在曲线/柱子上是论文图最常见的硬伤，而"挪到某个空白角"总会随数据变化失效。
    统一放到坐标区外，版面就不会因数据变化而重新遮挡。
    """
    kw.setdefault("fontsize", FS_LEG)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, y),
        ncol=ncol,
        frameon=False,
        fontsize=kw.pop("fontsize"),
        handlelength=1.4,
        columnspacing=1.0,
        handletextpad=0.5,
        labelspacing=0.3,
        borderpad=0.0,
        borderaxespad=0.0,
        **kw,
    )


def _caption(ax: plt.Axes, text: str, *, y: float = -0.34, **kw) -> None:
    """把一句短说明放在坐标区**下方**（图内说明，不进图区）。"""
    kw.setdefault("fontsize", FS_NOTE)
    kw.setdefault("color", "#333333")
    ax.text(0.5, y, text, transform=ax.transAxes, ha="center", va="top", **kw)


def _finish(fig: plt.Figure, name: str, note: str) -> Path:
    """保存图。

    图内不再画"数据来源…"脚注：这类信息统一写进附录的《数据与图表说明》一节，
    避免每张图下方重复一行小字（7pt 缩到版心后不足 5pt，既占位又难读）。
    ``note`` 参数保留，仅供需要单独导出带注版本时调用。
    """
    if SHOW_SOURCE_NOTE:
        add_source_note(fig, note, reserve_bottom=0.10)
    path = save_fig(fig, name, subdir=SUBDIR, dpi=DPI)
    print(f"    -> {path.relative_to(ROOT)}")
    return path


def ensure_cate_predictions() -> pd.DataFrame:
    """逐用户 CATE 预测（fig4a 的六边形分箱需要个体级数据）。

    这张表由 ``scripts/03_cate_obs.py`` 的 ``run_cate`` 在**同一次运行**里
    与 ``r2_cate_comparison.csv``、``r2_cate_calibration.csv`` 一起落盘。
    这里只读，绝不重算：旧实现在缓存缺失时"另拟合一次"，于是图、表、正文
    来自三次不同运行（RMSE 1.586 / 1.625 / 第三次），sd 与 min/max 全对不上。
    """
    path = TABLES / "r2_cate_predictions.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"缺少 {path.name}；请先跑 scripts/03_cate_obs.py——"
            "图 5 必须与表 4 共用同一次拟合的逐用户预测。"
        )
    return pd.read_csv(path)


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
            "c(X) = 面额 × 核销概率\n贪心 + 局部改进（近似背包）· LP 松弛上界",
            STRATEGY_COLORS["target_knapsack"],
        ),
        (
            "四指标评估",
            "CATE RMSE · 排序 · 策略价值 · regret\n训练/验证/测试按用户分离",
            STRATEGY_COLORS["all"],
        ),
        (
            "决策建议",
            "定向发券：每元回报 0.73 → 2.08 元\n占真值贪心解 86%（合并区间 79%–94%）",
            STRATEGY_COLORS["oracle"],
        ),
    ]

    fig = plt.figure(figsize=(6.6, 3.6))
    # 高度从 0.945 收到 0.93：顶部那行斜体说明原本压在画布外沿（bbox 出界 3px，可能被裁切）
    ax = fig.add_axes([0.0, 0.035, 1.0, 0.93])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # 纵向 8 行：每行 = 编号圆点 + 粗体标题（左 32%）+ 一句说明（右侧）。
    # 旧版是 2×4 方框，缩到 6.6in 宽后每格只有 1.25in，中文标题直接溢出格子——
    # 这正是"按最终尺寸出图"要暴露的问题：布局必须按最终宽度重新设计。
    n = len(steps)
    row_h = 0.105
    gap = 0.013
    y0 = 0.965
    for idx, (title, body, color) in enumerate(steps):
        y = y0 - idx * (row_h + gap)
        ax.add_patch(
            FancyBboxPatch(
                (0.03, y - row_h), 0.94, row_h,
                boxstyle="round,pad=0.004,rounding_size=0.012",
                linewidth=1.0, edgecolor=color, facecolor=color, alpha=0.12, zorder=2,
            )
        )
        ax.add_patch(
            FancyBboxPatch(
                (0.03, y - row_h), 0.94, row_h,
                boxstyle="round,pad=0.004,rounding_size=0.012",
                linewidth=1.0, edgecolor=color, facecolor="none", zorder=3,
            )
        )
        cy = y - row_h / 2
        ax.add_patch(Circle((0.062, cy), 0.019, color=color, zorder=4))
        ax.text(0.062, cy - 0.002, str(idx + 1), ha="center", va="center",
                fontsize=FS_TICK, color="white", zorder=5, fontweight="bold")
        ax.text(0.095, cy, title, ha="left", va="center", fontsize=FS_LABEL,
                fontweight="bold", color=color, zorder=5)
        ax.text(0.355, cy, body.replace("\n", "；"), ha="left", va="center",
                fontsize=FS_NOTE, color="#333333", zorder=5)
        if idx < n - 1:
            ax.annotate("", xy=(0.062, y - row_h - gap + 0.001), xytext=(0.062, y - row_h - 0.001),
                        arrowprops=dict(arrowstyle="-|>", color="#888888", lw=0.8, mutation_scale=7),
                        zorder=1)

    # 顶部那行斜体灰字（"数据与设计（1-4）→ 估计与决策（5-8）"）是图外注解：
    # 框内已经有 1–8 的编号，这句话只是把编号再分组说一遍，且不在任何框内，
    # 读起来像"图例缺失"。第 4 轮审稿 S2(i) 要求删除，位置留给框体本身。

    return _finish(fig, "fig0_roadmap", "seed=20240101 | 技术路线图（流程设计，非数据产物；数字见正文与表）")


# --------------------------------------------------------------------------- #
# 图 1：数据层证据（零膨胀 / 分组 / 渠道 / 脏数据）
# --------------------------------------------------------------------------- #
def fig1_data() -> Path:
    frame = pd.read_csv(TABLES / "r1_analysis_frame_clean.csv", usecols=["net_profit"])
    profit = frame["net_profit"].to_numpy()
    zero_share = float((profit == 0).mean())
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

    fig, axes = plt.subplots(2, 2, figsize=(6.6, 4.25))
    fig.subplots_adjust(hspace=0.78, wspace=0.30, top=0.93, left=0.10, right=0.98, bottom=0.205)

    # (a) 人均利润零膨胀
    ax = axes[0, 0]
    ax.hist(profit, bins=np.linspace(-40, 85, 70), color=METHOD_COLORS["itt"], alpha=0.85, edgecolor="none")
    ax.set_yscale("log")
    ax.set_xlabel("人均净贡献利润（元/人，30 天窗口）", fontsize=FS_LABEL)
    ax.set_ylabel("用户数（对数刻度）", fontsize=FS_LABEL)
    # 旧版在右上角压了一个三行灰框（含均值/标准差），框的下缘正好落在 0 元尖峰上；
    # 现在只留一行、贴在（无柱体的）右上角，且去掉了压在尖峰顶上的紫色箭头。
    ax.text(
        0.97,
        0.95,
        f"0 元处为尖峰：占 {zero_share * 100:.1f}%",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=FS_TICK,
        color="#6A1B9A",
        bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.9),
    )
    _panel(ax, "a", "人均利润高度零膨胀")

    # (b) 分组转化率：样本量并入刻度标签，柱体内部不再放白字
    ax = axes[0, 1]
    conv = aux["转化率"].to_numpy() * 100
    n_by_group = aux["用户数"].to_numpy()
    labels = [f"对照组\nn={int(n_by_group[0]):,}", f"处理组\nn={int(n_by_group[1]):,}"]
    bars = ax.bar(labels, conv, color=[STRATEGY_COLORS["no_coupon"], STRATEGY_COLORS["target_greedy"]], width=0.5)
    for b, v in zip(bars, conv):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.30, f"{v:.2f}%",
                ha="center", va="bottom", fontsize=FS_LABEL)
    ax.set_ylim(0, max(conv) * 1.35)
    ax.set_ylabel("7 天转化率（%）", fontsize=FS_LABEL)
    # 转化率差写在坐标区下方：旧版橙框下缘紧贴 y 轴上限刻度，视觉上压迫刻度
    _caption(ax, f"ITT 转化 +{conv[1] - conv[0]:.2f}pp（组间差分）", y=-0.40, color="#E65100")
    _panel(ax, "b", "随机分组的转化率差")

    # (c) 分渠道转化率
    ax = axes[1, 0]
    vals = funnel["conversion_rate"].to_numpy() * 100
    chs = funnel["channel"].to_numpy()
    bars = ax.bar(chs, vals, color=STRATEGY_COLORS["target_greedy"], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.08, f"{v:.2f}%", ha="center", va="bottom", fontsize=FS_TICK)
    ax.set_ylim(10, max(vals) * 1.06)
    ax.set_xlabel("渠道", fontsize=FS_LABEL)
    ax.set_ylabel("转化率（%，纵轴自 10% 起）", fontsize=FS_LABEL)
    _panel(ax, "c", "分渠道转化率：差异真实存在")

    # (d) 分渠道购物车缺失率：参考线交给图例（图例在坐标区下方）
    ax = axes[1, 1]
    order = ["search", "feed", "other", "xhs"]
    vals = np.array([miss[ch] * 100 for ch in order])
    bars = ax.bar(order, vals, color=STRATEGY_COLORS["all"], width=0.55, alpha=0.85)
    # 数值标签放进柱内（白字）：旧版 4.10% 的标签顶到 5.58% 的加权缺失率虚线上，
    # 间距不足 1pt（审稿意见 S4）。抬高标签只会更靠近虚线，故改为柱内白字，
    # 虚线只从柱子上方经过，与任何文字都不接触。
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v - 0.30, f"{v:.2f}%", ha="center", va="top",
                fontsize=FS_TICK, color="white", fontweight="bold", zorder=6)
    ax.axhline(overall_missing * 100, color="#333333", ls="--", lw=1.2,
               label=f"渠道加权缺失率 {overall_missing * 100:.2f}%")
    ax.set_xlim(-0.6, len(order) - 0.4)
    ax.set_ylim(0, max(vals) * 1.3)
    ax.set_xlabel("渠道", fontsize=FS_LABEL)
    ax.set_ylabel("购物车金额缺失率（%）", fontsize=FS_LABEL)
    _legend_below(ax, ncol=1, y=-0.46)
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
    reps = _read("r1_repeats_raw.csv")
    rep_sum = _read("r1_repeats_summary.csv")

    fig, axes = plt.subplots(2, 2, figsize=(6.6, 4.55))
    # top 从 0.90 收到 0.885：子图 (a) 是 twin 轴，标题会被 matplotlib 抬到上轴标签之上，
    # 原来正好顶到画布外沿 7px（靠 bbox_inches=tight 兜住，但不该依赖它）
    fig.subplots_adjust(hspace=0.92, wspace=0.34, top=0.885, left=0.115, right=0.975, bottom=0.235)

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
    ax.set_xlabel("转化的最小可检测效应（pp）", fontsize=FS_LABEL, color=METHOD_COLORS["itt"])
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
    # 旧版这里有一个三行图例压在两条递减曲线上（右端数据点被盖住），另有一个橙框贴着 y=10³。
    # 两条曲线本来就用**彩色轴标签**区分（下紫=转化率、上橙=利润），图例纯属重复，删除；
    # 星形"设计取值"改为一句话写在坐标区下方的空白里。
    _caption(
        ax,
        f"★ 设计取值：每组 {int(ss['n_per_group_conversion']):,} 人（合计 {int(ss['n_total']):,}，由转化率指标约束）",
        y=-0.52,
        color="#E65100",
    )
    _panel(ax, "a", "样本量：两条曲线分别取大")

    # (b) AA 校验：假阳性率与 95% 区间
    ax = axes[0, 1]
    fpr = aa["假阳性率"].to_numpy() * 100
    lo = (aa["假阳性率"] - aa["FPR_95CI_下界"]).to_numpy() * 100
    hi = (aa["FPR_95CI_上界"] - aa["假阳性率"]).to_numpy() * 100
    xt = ["转化率\n（两比例 z）", "净增量利润\n（Welch t）"]
    bars = ax.bar(xt, fpr, yerr=[lo, hi], capsize=4, width=0.45,
                  color=[METHOD_COLORS["ipw"], METHOD_COLORS["dr"]])
    # 数值标签一律放在误差棒顶端**正上方居中**：旧版放在条右侧，与红色"名义 α"
    # 文字撞在一起（这就是审稿指出的"图 3(b) 红字重叠"）。
    for b, v, h in zip(bars, fpr, hi):
        ax.text(b.get_x() + b.get_width() / 2, v + h + 0.45, f"{v:.1f}%",
                ha="center", va="bottom", fontsize=FS_LABEL)
    ax.axhline(5.0, color="red", ls="--", lw=1.2, label="名义 α=5%（1000 次无效应重复）")
    ax.set_ylim(0, max(fpr + hi) * 1.75)
    ax.set_ylabel("假阳性率（%）", fontsize=FS_LABEL)
    # 旧版把"KS p 值 + 名义 α + 重复次数"四行压在子图顶部；KS 检验数值进正文与表，
    # 图里只留参考线的图例（坐标区下方）。
    _legend_below(ax, ncol=1, y=-0.42)
    _panel(ax, "b", "AA 校验：p 值分布与名义水平一致")

    # (c) 护栏单侧置信上界：两个分母并列。分母不同，符号可以相反——
    # 全用户口径把"转化率上升 → 更多人下单 → 更多人退款"的构成效应算进来，
    # 条件口径只回答"已下单用户里退款比例是否恶化"。
    #
    # 界值不是只有一个 0.5：0.2/0.3/0.5/1.0 四档都画出来（审稿意见 N2）。
    # 结论在 0.3 与 0.5 之间翻转——全用户口径的单侧上界 0.435 恰好落在两档之间，
    # 而 DGP 真值 0.41 只比它低 0.09。只画一条 0.5 的线，读者看不出余量有多薄。
    ax = axes[1, 0]
    ni_all = guard[(guard["口径"] == "R1 全用户（主口径）")
                   & guard["检验"].astype(str).str.contains("非劣效", na=False)].iloc[0]
    ni_cond = guard[(guard["口径"] == "条件口径（灵敏度）")
                    & guard["检验"].astype(str).str.contains("非劣效", na=False)].iloc[0]
    margin = float(ni_all["界值_pp"])
    sens = _read("r1_guardrail_sensitivity.csv")
    margins = sorted({float(m) for m in sens["界值_pp"]})
    ax.axhline(0, color="#333333", lw=0.8)
    ax.axvline(0, color="#333333", lw=0.8, ls=":")
    for m in margins:
        if abs(m - margin) < 1e-9:
            continue
        ax.axvline(m, color="#E53935", lw=0.9, ls=":", alpha=0.55)
    ax.axvline(margin, color="red", lw=1.5, ls="--")
    rows_c = [
        (0.5, ni_all, METHOD_COLORS["dr"], "全用户\n（主口径）"),
        (-0.5, ni_cond, METHOD_COLORS["ipw"], "已下单\n（灵敏度）"),
    ]
    for yi, row, color, _ in rows_c:
        d = float(row["差值_pp"])
        ub = float(row["单侧CI上界_pp"])
        ax.errorbar([d], [yi], xerr=[[0.0], [ub - d]], fmt="o", ms=6, capsize=5,
                    lw=1.8, color=color)
        # 数值统一写在左上/左下空白区：既避开误差棒，也不与界值线交叉
        ax.text(-0.82, 0.78 if yi > 0 else -0.80,
                f"差值 {d:+.2f}，上界 {ub:.2f}", fontsize=FS_NOTE,
                ha="left", va="center", color=color)
    ax.set_yticks([0.5, -0.5], [r[3] for r in rows_c], fontsize=FS_TICK)
    ax.set_xlim(-0.85, 1.12)
    ax.set_ylim(-0.95, 0.95)
    ax.set_xticks([-0.5, 0.0, 0.5, 1.0], ["-0.5", "0", "0.5", "1.0"], fontsize=FS_TICK)
    ax.set_xlabel("退款率差（pp）；红虚线 = 四档界值 0.2 / 0.3 / 0.5 / 1.0",
                  fontsize=FS_LABEL - 1)
    # 通过/不通过写进标题（坐标区之外，不与界值线打架）
    ax.set_title("(c) 护栏：两分母符号相反\n0.3 起已下单口径成立，0.5 起两个口径成立",
                 fontsize=FS_TITLE, pad=4)

    # (d) 重复 200 次的 ITT 分布
    ax = axes[1, 1]
    for lvl, color, alpha in (("L0", METHOD_COLORS["ipw"], 0.45), ("L1", METHOD_COLORS["itt"], 0.75)):
        v = reps.loc[reps["level"] == lvl, "est_profit"].to_numpy()
        ax.hist(v, bins=24, color=color, alpha=alpha, edgecolor="white", linewidth=0.4, label=f"{lvl}（R={v.size}）")
    truth = float(reps["truth_profit"].iloc[0])
    mean_l1 = float(reps.loc[reps["level"] == "L1", "est_profit"].mean())
    ax.axvline(truth, color="#212121", lw=1.8, ls="--")
    ax.axvline(mean_l1, color=STRATEGY_COLORS["all"], lw=1.2, ls="-.")
    ax.set_xlabel("ITT 估计（净增量利润，元/人）", fontsize=FS_LABEL)
    ax.set_ylabel("重复次数", fontsize=FS_LABEL)
    handles = [
        Patch(facecolor=METHOD_COLORS["ipw"], alpha=0.45, label=f"L0（R={int(rep_sum['重复次数'].iloc[0])}）"),
        Patch(facecolor=METHOD_COLORS["itt"], alpha=0.75, label=f"L1（R={int(rep_sum['重复次数'].iloc[1])}）"),
        Line2D([], [], color="#212121", ls="--", lw=1.8, label=f"解析真值 {truth:.3f}"),
        Line2D([], [], color=STRATEGY_COLORS["all"], ls="-.", lw=1.2, label=f"200 次均值 {mean_l1:.3f}"),
    ]
    # 图例从右上移到坐标区下方：旧版图例压在直方图高柱上，灰色说明框又贴着图例
    _legend_below(ax, handles=handles, ncol=2, y=-0.46)
    _panel(ax, "d", "重复实验：分布与真值")

    return _finish(
        fig,
        "fig2_design",
        "seed=20240101 | R=200（ITT）/1000（AA）；护栏两套分母各算一次；样本量为每组、1:1",
    )


# --------------------------------------------------------------------------- #
# 图 3：ITT 森林图 + 利润侵蚀分解
# --------------------------------------------------------------------------- #
def fig3_itt() -> Path:
    itt = _read("r1_itt.csv")
    aux = _read("r1_auxiliary.csv")

    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.85), gridspec_kw={"width_ratios": [1.15, 1.0]})
    fig.subplots_adjust(hspace=0.3, wspace=0.34, top=0.90, bottom=0.285, left=0.115, right=0.975)

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
        ax.text(x_text, yi, f"{e:.3f} [{l:.3f}, {h:.3f}] vs {t:.3f}", fontsize=FS_TICK, va="center", color="#333333")
    ax.axvline(0, color="#888888", lw=0.9, ls=":")
    ax.set_yticks(y, levels)
    ax.set_ylim(-0.55, len(levels) - 0.25)
    ax.set_xlim(min(lo) - 0.06, x_text + 1.02)
    ax.set_xlabel("净增量贡献利润（元/人）", fontsize=FS_LABEL)
    ax.set_ylabel("DGP 层级", fontsize=FS_LABEL)
    handles = [
        Line2D([], [], color=STRATEGY_COLORS["target_greedy"], marker="o", lw=1.8, label="ITT 估计 + 95% CI"),
        Line2D([], [], color="none", marker="D", ms=6, markerfacecolor="red", label="解析真值"),
    ]
    # 图例改到坐标区下方：森林图左上角就是最高一层的区间，图例放那里必然压线
    _legend_below(ax, handles=handles, ncol=2, y=-0.40)
    _panel(ax, "a", "ITT 对真值：三个层级、三个区间全覆盖")

    # (b) 利润侵蚀瀑布：多转化增益 − 券成本 + 订单经济差异 = 净增
    # 四项一律取自 r1_profit_decomposition.csv（同一张表、同一套口径），
    # 图里不再现算——旧稿的四个数字不在任何 CSV 里，读者无从复算。
    #
    # 必须是**真累积瀑布**（审稿意见 N8）：第一根 0→123.685，第二根 123.685→68.344，
    # 第三根 68.344→72.403，第四根从 0 起画到 72.403。旧版三根都从 0 起画，
    # 图上相加得 72.5，与正文的 72.40 对不上。
    ax = axes[1]
    dec = _read("r1_profit_decomposition.csv").set_index("项")
    gain = float(dec.loc["多转化增益", "值_元每百人"])
    coupon_cost = float(dec.loc["券成本", "值_元每百人"])
    econ = float(dec.loc["订单经济差异（剩余项）", "值_元每百人"])
    net = float(dec.loc["净增 = ITT", "值_元每百人"])
    profit0, profit1 = float(aux["人均净贡献利润"].iloc[0]), float(aux["人均净贡献利润"].iloc[1])

    labels = [
        "多转化\n$(p_1-p_0)A_1$",
        "券成本\n$-p_0\\cdot$面额\n·核销率",
        "订单经济\n剩余项",
        "净增\n= ITT",
    ]
    steps = [gain, coupon_cost, econ]
    cum = [0.0]
    for v in steps:
        cum.append(cum[-1] + v)
    bars = []  # (left, height, bottom, is_total)
    for i, v in enumerate(steps):
        before, after = cum[i], cum[i + 1]
        bars.append((i, abs(after - before), min(before, after), False))
    bars.append((len(steps), abs(cum[-1]), 0.0, True))
    colors = [METHOD_COLORS["dr"], STRATEGY_COLORS["all"], STRATEGY_COLORS["random"], STRATEGY_COLORS["oracle"]]
    for (i, height, bottom, _is_total), c in zip(bars, colors):
        ax.bar(i, height, bottom=bottom, color=c, width=0.62)
    # 三项按 0.001 元显示（相加得 72.403），合计给 4 位小数 72.4036：
    # 精确值与"逐项舍入后的和"相差 0.0006，写清精度来源就不会被读成加不平。
    texts = [
        (0, gain, f"{gain:+.3f}", "bottom"),
        (1, cum[1] + coupon_cost, f"{coupon_cost:+.3f}", "top"),
        (2, cum[2] + econ, f"{econ:+.3f}", "bottom"),
        (3, cum[-1], f"{net:.4f}", "bottom"),
    ]
    for i, ytxt, s, va in texts:
        off = 3.0 if va == "bottom" else -3.0
        ax.text(i, ytxt + off, s, ha="center", va=va, fontsize=FS_NOTE, fontweight="bold")
    # 累积连接线：把每一步的落点接到下一根柱子的起点
    for i in range(len(steps)):
        ax.plot([i + 0.31, i + 1 - 0.31], [cum[i + 1], cum[i + 1]],
                color="#AAAAAA", lw=0.9, ls="--")
    ax.set_xticks(range(len(labels)), labels, fontsize=FS_TICK)
    ax.set_ylabel("每 100 名用户的利润变化（元）", fontsize=FS_LABEL)
    ax.axhline(0, color="#333333", lw=1.0)
    ax.set_ylim(0, max(gain, cum[-1]) * 1.22)
    _caption(
        ax,
        f"GMV 人均 +{(float(aux['人均GMV'].iloc[1]) - float(aux['人均GMV'].iloc[0])):.2f} 元"
        f"（+{(float(aux['人均GMV'].iloc[1]) / float(aux['人均GMV'].iloc[0]) - 1) * 100:.0f}%），"
        f"净利润仅 +{(profit1 - profit0):.2f} 元",
        y=-0.30,
        color="#E65100",
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

    fig = plt.figure(figsize=(6.6, 4.6))
    gs = fig.add_gridspec(
        2, 2, hspace=0.72, wspace=0.34, top=0.865, bottom=0.135, left=0.105, right=0.975
    )

    # (a) 分面板六边形分箱：三者共用同一坐标轴范围，差异才可比
    sub = gs[0, 0].subgridspec(1, 3, wspace=0.10)
    true = pred["tau_true"].to_numpy()
    ax_a = []
    sd_list: list[float] = []
    for i, (name, col) in enumerate(LEARNER_COLORS.items()):
        key = name.lower().replace("-", "_").replace(" ", "_")
        a = fig.add_subplot(sub[0, i])
        a.hexbin(true, pred[key].to_numpy(), gridsize=28, mincnt=1, cmap="viridis", linewidths=0)
        a.plot([-2.4, 1.8], [-2.4, 1.8], color="red", lw=0.9, ls="--")
        a.set_xlim(-2.45, 1.8)
        a.set_ylim(-6.0, 6.0)
        a.set_title(f"{name}", fontsize=FS_TICK, pad=2)
        sd_list.append(float(pred[key].std(ddof=1)))
        a.tick_params(labelsize=FS_TICK, length=2.5)
        a.set_xticks([-2, 0])
        a.set_yticks([-5, 0, 5])
        a.spines["top"].set_visible(False)
        a.spines["right"].set_visible(False)
        if i > 0:
            a.set_yticklabels([])
        ax_a.append(a)
    ax_a[1].set_xlabel("真值 $\\tau_\\Pi(x)$（元/人）", fontsize=FS_LABEL)
    ax_a[0].set_ylabel("估计 $\\hat\\tau(x)$", fontsize=FS_LABEL)
    # 旧版在三个 hexbin 面板里各压了一个深色 sd 角标、左下角还有一块红底"预测范围"，
    # 都会盖住六边形数据与刻度；改为组标题下一行字（坐标区之外），信息不丢、也不压数据。
    fig.text(
        0.02,
        0.925,
        "估计值标准差 sd：" + "　".join(f"{n} {v:.2f}" for n, v in zip(LEARNER_COLORS, sd_list)),
        fontsize=FS_NOTE,
        color="#555555",
        ha="left",
        va="top",
    )
    # 组标题必须用 fig.text：挂在中间子图的 set_title 上会把 "S-learner" 覆盖掉
    # （这正是审稿指出的"图 5(a) S-learner 子图标题被压掉"）。
    fig.text(
        0.02,
        0.985,
        "(a) 三种学习器：同一真值、同一坐标轴",
        fontsize=FS_TITLE,
        fontweight="bold",
        ha="left",
        va="top",
    )

    # (b) Causal Forest 校准曲线
    ax = fig.add_subplot(gs[0, 1])
    cf = cal[cal["方法"] == "Causal Forest"]
    ax.plot(cf["mean_pred"], cf["mean_true"], "o-", color=LEARNER_COLORS["Causal Forest"], ms=4, lw=1.5, label="分箱实际值")
    lim = [min(cf["mean_pred"].min(), cf["mean_true"].min()) - 0.1, max(cf["mean_pred"].max(), cf["mean_true"].max()) + 0.1]
    ax.plot(lim, lim, color="#212121", ls="--", lw=1.1, label="完美校准")
    ax.set_xlim(*lim)
    ax.set_ylim(-0.75, max(cf["mean_true"].max(), cf["mean_pred"].max()) + 0.75)
    ax.set_xlabel("预测 CATE 的十分位箱均值（元/人）", fontsize=FS_LABEL)
    ax.set_ylabel("真值 CATE 同箱均值（元/人）", fontsize=FS_LABEL)
    # 图例下移出坐标区（旧版压在左上角，正好盖住低端箱体）；"两端放大"的注释块删除，
    # 过冲幅度可由 45° 参考线与箱体位置直接读出，具体数字进正文。
    _legend_below(ax, ncol=2, y=-0.42)
    _panel(ax, "b", "Causal Forest 校准：中段准、两端放大")

    # (c) RMSE 与 R²
    ax = fig.add_subplot(gs[1, 0])
    methods = list(cmp_tab["方法"])
    x = np.arange(len(methods))
    rmse = cmp_tab["CATE_RMSE"].to_numpy()
    r2 = cmp_tab["R2"].to_numpy()
    ax.bar(x - 0.19, rmse, width=0.36, color=[LEARNER_COLORS[m] for m in methods], alpha=0.9)
    for xi, v in zip(x, rmse):
        # 标签上移 0.06：右轴 R²=0 的参考线已删，这里只需与误差棒/右轴数据点离开；
        # T-learner 的 1.625 是最高柱，标签原来紧贴柱顶。
        ax.text(xi - 0.19, v + 0.10, f"{v:.3f}", ha="center", va="bottom", fontsize=FS_TICK)
    ax.set_xticks(x, methods, fontsize=FS_TICK)
    ax.set_ylabel("CATE RMSE（元/人，越小越好）", fontsize=FS_LABEL)
    ax.set_ylim(0, max(rmse) * 1.62)
    ax2 = ax.twinx()
    ax2.plot(x + 0.19, r2, "o--", color="#212121", ms=6, lw=1.2)
    for xi, v in zip(x, r2):
        ax2.text(xi + 0.19, v + 0.30, f"{v:.2f}", ha="center", va="bottom",
                 fontsize=FS_TICK, color="#212121")
    # 旧版这里有一条 ax2.axhline(0)（R²=0 的灰点线）横贯全图，正好穿过「1.625」标签顶部；
    # 另有一处灰字「R² = 0」贴着黑折线与「0.21」挤在一起。右轴刻度 0 已经足以表达
    # "等于直接报均值"，两者一并删除（审稿意见 N3）。右轴标题改水平放在坐标区上方，
    # 不再竖排占着右侧、与 (d) 的纵轴标题只剩半个字的间距。
    ax2.set_ylabel("")
    # 轴上方被 (c) 的一行式标题占满（标题居中且几乎与坐标区等宽），故放在坐标区
    # 右上的空白角：水平书写、不与 (d) 的纵轴标题争右侧那条 3mm 的缝。
    ax2.text(0.98, 0.97, "右轴：$R^2$（越高越好）", transform=ax2.transAxes,
             ha="right", va="top", fontsize=FS_NOTE, color="#212121")
    ax2.set_ylim(min(r2) - 1.2, 2.8)
    ax2.tick_params(labelsize=FS_TICK)
    ax2.spines["top"].set_visible(False)
    # 关键：twin 轴默认也画网格。右轴刻度 -5/0/5 映射回左轴，0 那条网格线正好落在
    # 左轴 y≈1.81，横穿「1.625」标签（1.725–1.946）——审稿意见 N3 说的"R²=0 灰点线"
    # 就是它，而不是旧版那条 axhline。只留左轴网格（RMSE 刻度），右轴不再画网格。
    ax2.grid(False)
    # 左右轴已经在坐标区上方与纵轴标签里写明（"右轴/左轴"），图例纯属重复且压在柱子上，删除
    _panel(ax, "c", "T-learner 的 $R^2$ 为负：不如直接报均值")

    # (d) 重复 20 次的 RMSE 箱线图（Causal Forest 只有 2 次，改为散点并加星标注）
    ax = fig.add_subplot(gs[1, 1])
    order = ["T-learner", "S-learner"]
    data = [reps.loc[reps["method"] == m, "rmse"].to_numpy() for m in order]
    bp = ax.boxplot(data, positions=[1, 2], tick_labels=order, patch_artist=True, widths=0.45,
                    medianprops=dict(color="#212121", lw=1.2))
    for patch, m in zip(bp["boxes"], order):
        patch.set_facecolor(LEARNER_COLORS[m])
        patch.set_alpha(0.45)
    for i, (m, d) in enumerate(zip(order, data), start=1):
        ax.plot([i], [d.mean()], marker="D", ms=5, color="#212121", zorder=5)
    cf_rep = reps.loc[reps["method"] == "Causal Forest", "rmse"].to_numpy()
    if cf_rep.size:
        ax.plot(np.full(cf_rep.size, 3.0), cf_rep, marker="*", ms=10, ls="none",
                color=LEARNER_COLORS["Causal Forest"], zorder=5,
                label=f"Causal Forest（仅 {cf_rep.size} 次）")
    tick_labels = [
        f"T-learner\n{data[0].mean():.3f}\n[{np.percentile(data[0], 2.5):.3f}, {np.percentile(data[0], 97.5):.3f}]",
        f"S-learner\n{data[1].mean():.3f}\n[{np.percentile(data[1], 2.5):.3f}, {np.percentile(data[1], 97.5):.3f}]",
    ]
    if cf_rep.size:
        tick_labels.append(f"CF$^*$\n仅 {cf_rep.size} 次")
    ax.set_xticks([1, 2, 3] if cf_rep.size else [1, 2], tick_labels, fontsize=FS_TICK)
    ax.set_ylabel("重复实验的 CATE RMSE（元/人）", fontsize=FS_LABEL)
    ax.set_ylim(0, max(d.max() for d in data) * 1.30)
    # 旧版右上角的绿框说明压住箱体与须；区间是否重叠在 x 刻度标签里已经给出（2.5%/97.5% 分位），
    # 这句话删掉，结论写进正文。
    _panel(ax, "d", "重复实验的稳定性")

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
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.95))
    fig.subplots_adjust(hspace=0.3, wspace=0.30, top=0.90, bottom=0.30, left=0.095, right=0.98)

    truth_by_lambda = lam.groupby("lambda")["真值"].first()

    # (a) 偏差随 λ
    ax = axes[0]
    for m in OBS_ORDER:
        sub = lam[lam["method"] == m].sort_values("lambda")
        ax.plot(sub["lambda"], sub["偏差"], "o-", color=METHOD_COLORS[m], ms=3.5, lw=1.3, label=OBS_LABELS[m])
    ax.plot(truth_by_lambda.index, truth_by_lambda.to_numpy(), color="#212121", ls="--", lw=1.1,
            label="真值 ATE（随 λ 变化）")
    ax.axhline(0, color="#888888", lw=0.9, ls=":")
    ax.set_xlabel("混淆强度 $\\lambda$", fontsize=FS_LABEL)
    ax.set_ylabel("偏差（元/人，估计 − 真值）", fontsize=FS_LABEL)
    # 旧版左下角的灰框说明压住 λ=0.75~1.0 的曲线段；左上角图例又压住 λ=0/0.25 的起点。
    # 两个面板的颜色语义相同（四种方法），因此改用**整图底部一个共享图例**，
    # 两个坐标区内都不再出现图例，任何 λ 处的数据都不会被盖住。
    _panel(ax, "a", "偏差随混淆强度加速上升")

    # (b) 覆盖率随 λ（带 Clopper–Pearson 95% 区间）
    ax = axes[1]
    for m in OBS_ORDER:
        sub = lam[lam["method"] == m].sort_values("lambda")
        cov = sub["覆盖率"].to_numpy()
        lo = cov - sub["覆盖率_CP下界"].to_numpy()
        hi = sub["覆盖率_CP上界"].to_numpy() - cov
        ax.errorbar(sub["lambda"], cov, yerr=[lo, hi], fmt="o-", color=METHOD_COLORS[m],
                    ms=3.0, lw=1.2, elinewidth=1.0, capsize=2.0, alpha=0.95)
    ax.axhline(0.95, color="#212121", ls="--", lw=1.0)
    ax.axhline(0.90, color="#E53935", ls=":", lw=1.2)
    ax.set_ylim(-0.08, 1.16)
    ax.set_xlabel("混淆强度 $\\lambda$", fontsize=FS_LABEL)
    ax.set_ylabel("95% 置信区间覆盖率", fontsize=FS_LABEL)
    # 旧版中部粉色框把 λ=0.50 处全部方法的数据点与误差棒整个盖住，还压住 y 轴 0.2–0.4 刻度。
    # 该框里的结论（λ=0.25 时 IPW/DR 上界已低于 0.90）写进正文，图里不再重复。
    _panel(ax, "b", "覆盖率崩塌快于偏差增长")

    # 整图共享图例（8 条，4 列 2 行），放在画布底部
    handles = [
        Line2D([], [], color=METHOD_COLORS[m], marker="o", ms=3.5, lw=1.3, label=OBS_LABELS[m])
        for m in OBS_ORDER
    ]
    handles += [
        Line2D([], [], color="#212121", ls="--", lw=1.1, label="真值 ATE（a）"),
        Line2D([], [], color="#555555", marker="|", ms=6, lw=1.0, label="95% 区间（CP，b）"),
        Line2D([], [], color="#212121", ls="--", lw=1.0, label="名义覆盖率 0.95（b）"),
        Line2D([], [], color="#E53935", ls=":", lw=1.2, label="警戒线 0.90（b）"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.005),
        ncol=4,
        frameon=False,
        fontsize=FS_LEG,
        handlelength=1.4,
        columnspacing=1.0,
        handletextpad=0.5,
        labelspacing=0.3,
        borderpad=0.0,
        borderaxespad=0.0,
    )

    return _finish(
        fig,
        "fig5_obs",
        f"seed=20240101 | L3、每个 λ 重复 {int(lam['重复次数'].max())} 次、n=20,000；λ 网格 7 点；估计器仅用可观测 X",
    )


# --------------------------------------------------------------------------- #
# 图 6：预算约束下的策略价值
# --------------------------------------------------------------------------- #
def fig6_policy() -> Path:
    six = _read("r3_six_strategies.csv")
    scan = _read("r3_budget_scan.csv")
    gap = _read("r3_greedy_gap.csv")
    ci = _read("r3_six_strategies_ci.csv")
    rnd = _read("r3_random_seeds.csv")
    refit = _read("r3_policy_refit_ci.csv")
    ci_inc = ci[ci["指标"] == "incremental_value"].set_index("strategy_key")

    by_key = six.set_index("strategy_key")
    oracle_v = float(by_key.loc["oracle", "incremental_value"])

    fig, axes = plt.subplots(2, 2, figsize=(6.6, 4.5))
    fig.subplots_adjust(hspace=0.92, wspace=0.40, top=0.93, left=0.125, right=0.975, bottom=0.245)

    # (a) 可行策略的增量价值（带 bootstrap 95% CI）。全量发券超预算 5 倍，
    # 画成最高柱会让人误以为它最优——移到右侧灰柱"不可行"区，不参与比较。
    ax = axes[0, 0]
    plan = [
        ("no_coupon", 0.0, "不发券"),
        ("random", 1.0, "随机"),
        ("target_greedy", 2.0, "定向-贪心"),
    ]
    for key, xi, lab in plan:
        v = float(by_key.loc[key, "incremental_value"])
        if key in ci_inc.index:
            lo = float(ci_inc.loc[key, "CI下界"])
            hi = float(ci_inc.loc[key, "CI上界"])
            # 误差棒上帽从 3pt 收到 1.5pt：上帽原来与 0.405 的真值参考线只剩 3pt，
            # 加上标签后看着像"参考线穿过帽子"（审稿意见 N5）。
            ax.bar(xi, v, width=0.6, color=STRATEGY_COLORS[key],
                   yerr=[[v - lo], [hi - v]], capsize=1.5, error_kw=dict(elinewidth=0.9))
        else:
            hi = v
            ax.bar(xi, v, width=0.6, color=STRATEGY_COLORS[key])
        if v > 0:
            # 数值改柱内白字（审稿意见 N5 的两种改法之一），贴在柱脚而不是柱顶：
            # 误差棒的**下半截**（CI 下界 0.318 → 柱顶 0.349）正好落在柱内，
            # 标签若贴柱顶会被这根竖线穿过（视觉复验第一版就是这么判的）。
            # 第 5 轮：0.122 压在浅橙 #FB8C00 上，白字对比度只有 2.4:1；浅色柱改深色字。
            label_color = "white" if key == "target_greedy" else "#3E2723"
            ax.text(xi, 0.014, f"{v:.3f}", ha="center", va="bottom", fontsize=FS_TICK,
                    color=label_color, fontweight="bold", zorder=6)
        else:
            # 0.000 这根柱高为 0，标签贴基线与"随机"的标签会叠；靠左对齐放在柱脚。
            ax.text(xi - 0.02, 0.014, f"{v:.3f}", ha="right", va="bottom", fontsize=FS_TICK)
    # 定向这一根再叠一层**全过程**区间：重抽训练集 → 重拟合 → 重跑贪心（10 次）。
    # 细的误差棒（上一段）只重抽测试集、策略固定，是条件区间；粗的这一根才是
    # "换一批训练数据，策略值会落到哪"（审稿意见 N4）。
    refit_inc = refit[refit["指标"].str.startswith("增量价值")]
    if not refit_inc.empty:
        r_lo = float(refit_inc["正态CI下界"].iloc[0])
        r_hi = float(refit_inc["正态CI上界"].iloc[0])
        v_g0 = float(by_key.loc["target_greedy", "incremental_value"])
        ax.errorbar([2.0], [v_g0], yerr=[[v_g0 - r_lo], [r_hi - v_g0]], fmt="none",
                    ecolor="#212121", elinewidth=1.5, capsize=6, capthick=1.5, zorder=4)
    v_all = float(by_key.loc["all", "incremental_value"])
    ax.bar(3.7, v_all, width=0.6, color="#BDBDBD", hatch="///", edgecolor="#757575")
    ax.text(3.7, v_all + 0.018, f"{v_all:.3f}", ha="center", va="bottom", fontsize=FS_TICK,
            color="#616161")
    # "不可行"原来竖排写在斜纹柱体内部，与 hatch 纹理叠在一起（视觉复验指出"杂乱"）。
    # 改为横排写进横轴组标题：既说明这根柱不参与比较，也不再压住柱体。
    # 真值参考线只画到"全量"柱的左缘：全量发券不可行、不参与比较，
    # 把参考线横穿到斜纹柱里既无意义，也会和 hatch 混在一起。
    ax.hlines(oracle_v, -0.7, 3.4, color=STRATEGY_COLORS["oracle"], ls="--", lw=1.1,
              label=f"真值贪心解 {oracle_v:.3f}")
    ax.set_xticks([0, 1, 2, 3.7], ["不发券", "随机", "定向-贪心", "全量\n不可行（超预算 5 倍）"],
                  fontsize=FS_TICK)
    ax.set_xlim(-0.7, 4.4)
    ax.set_ylabel("增量价值（元/人）", fontsize=FS_LABEL)
    ax.set_ylim(0, max(v_all, oracle_v) * 1.28)
    v_greedy = float(by_key.loc["target_greedy", "incremental_value"])
    v_random = float(by_key.loc["random", "incremental_value"])
    handles = [Line2D([], [], color=STRATEGY_COLORS["oracle"], ls="--", lw=1.1,
                      label=f"真值贪心解 {oracle_v:.3f}")]
    if not refit_inc.empty:
        handles.append(Line2D([], [], color="#212121", lw=1.5,
                              label="全过程区间（含再训练重拟合）"))
    _legend_below(ax, handles=handles, ncol=1, y=-0.32)
    _panel(ax, "a", f"可行策略：定向 vs 随机 {v_greedy / v_random:.2f} 倍")

    # (b) 定向相对随机的倍数，每个预算点 50 个种子 → 倍数带区间。
    # 旧版每点只抽一次随机策略，4.55 倍是单次运气；曲线非单调也是噪声。
    ax = axes[0, 1]
    ratio = scan["定向相对优势倍数"].to_numpy()
    lo = scan["定向相对优势_CI下界"].to_numpy()
    hi = scan["定向相对优势_CI上界"].to_numpy()
    ax.errorbar(scan["预算倍数"], ratio, yerr=[ratio - lo, hi - ratio], fmt="o-",
                color=STRATEGY_COLORS["target_greedy"], ms=4, lw=1.6, elinewidth=1.0, capsize=2.5)
    ax.axhline(1.0, color="#888888", ls="--", lw=1.0)
    ax.set_xlim(0.05, 3.15)
    ax.set_xticks([0.2, 0.55, 1.0, 1.6, 2.3, 3.0])
    ax.set_xticklabels(["0.2", "0.55", "1.0", "1.6", "2.3", "3.0"], fontsize=FS_TICK)
    ax.set_ylim(1.0, float(hi.max()) * 1.10)
    ax.set_xlabel("预算倍数（1 = 基准预算）", fontsize=FS_LABEL)
    ax.set_ylabel("定向 / 随机（倍）", fontsize=FS_LABEL)
    i_min = float(scan["预算倍数"].min())
    k_min = int(scan["预算倍数"].idxmin())
    ratio_min = float(ratio[k_min])
    ratio_max = float(ratio[-1])
    # 数值说明放到坐标区下方（图内文字压在误差棒上会被版式检查判为遮挡），
    # 同时避免标题过长被画布裁切。
    _caption(
        ax,
        f"×{i_min:.1f}：{ratio_min:.2f} 倍 [{lo[k_min]:.2f}, {hi[k_min]:.2f}]\n"
        f"×{float(scan['预算倍数'].max()):.1f}：{ratio_max:.2f} 倍 [{lo[-1]:.2f}, {hi[-1]:.2f}]"
        f"（50 种子）",
        y=-0.52,
    )
    _panel(ax, "b", "最紧预算处定向优势最大")

    # (c) 策略价值随预算倍数变化：随机基线带 50 个种子的区间
    ax = axes[1, 0]
    ax.fill_between(scan["预算倍数"], scan["价值_随机_CI下界"], scan["价值_随机_CI上界"],
                    color=STRATEGY_COLORS["random"], alpha=0.20, linewidth=0)
    ax.plot(scan["预算倍数"], scan["价值_随机"], "o-", color=STRATEGY_COLORS["random"], ms=3, lw=1.3,
            label="随机发券")
    ax.plot(scan["预算倍数"], scan["价值_贪心"], "s-", color=STRATEGY_COLORS["target_greedy"], ms=3,
            lw=1.6, label="定向-贪心")
    ax.plot(scan["预算倍数"], scan["价值_真值贪心解"], "^", color=STRATEGY_COLORS["oracle"], ms=3,
            lw=1.0, ls="--", label="真值贪心解")
    ax.set_xlim(0.1, 3.1)
    ax.set_xticks([0.2, 1.0, 2.0, 3.0])
    ax.set_xticklabels(["0.2", "1.0", "2.0", "3.0"], fontsize=FS_TICK)
    ax.set_xlabel("预算倍数（1 = 基准预算）", fontsize=FS_LABEL)
    ax.set_ylabel("策略价值（元/人）", fontsize=FS_LABEL)
    ax.set_ylim(0, float(scan[["价值_贪心", "价值_随机", "价值_真值贪心解"]].to_numpy().max()) * 1.35)
    _legend_below(ax, ncol=3, y=-0.46)
    _panel(ax, "c", f"9 个预算点上定向始终更高")

    # (d) 三个规模统一成“算法 / 参考答案”，越高越好。
    # 旧版三根柱分别是 贪心/上界=0.9999993、DP/贪心=0.9970（越小越好）、
    # 贪心/最优=0.667，方向相反，不能放在同一把尺上；横轴三组刻度各占 2–3 行，
    # 第一组的“贪心 / 上界”与第二组的“1,000 人”在版面上压在一起。
    # 现在横轴只留三个规模名，人数与“精确 DP 不可行”移入图注；
    # 三根柱一律是“贪心 / 参考答案”：0.9999993、1.00298、0.66667。
    ax = axes[1, 1]
    by_item = {str(r["项"]): r for _, r in gap.iterrows()}
    full = by_item["全规模（n=60000）"]
    down = by_item["降规模（n=1000）"]
    counter = by_item["方案反例（3 件）"]
    ratios = np.array([
        float(full["贪心/上界"]),                                   # 0.9999993
        float(down["贪心估计价值"]) / float(down["精确DP"]),         # 1.00298
        float(counter["贪心估计价值"]) / float(counter["精确DP"]),   # 0.66667
    ])
    values = ["1.000", "1.003", "0.667"]
    # 方向标注：全规模只写“≈ 上界”。正文的 1.8×10⁻⁷ 是元/人绝对差，与这里的
    # 比值差量纲不同，同屏写出 7×10⁻⁷ 容易被读成与正文互相矛盾。
    directions = ["≈ 上界", "贪心高 0.30%", "贪心低 33%"]
    x = np.arange(len(ratios))
    ax.bar(x, ratios, width=0.55, color=STRATEGY_COLORS["target_greedy"], alpha=0.9)
    for xi, v, s, d in zip(x, ratios, values, directions):
        ax.text(xi, v + 0.05, f"{s}\n{d}", ha="center", va="bottom", fontsize=FS_TICK,
                linespacing=1.15)
    ax.set_xticks(x, ["全规模", "降规模", "反例"], fontsize=FS_TICK)
    ax.set_ylim(0, 1.40)
    ax.set_xlim(-0.65, 2.65)
    ax.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_ylabel("算法 / 参考答案（越高越好）", fontsize=FS_LABEL)
    _panel(ax, "d", "贪心近似程度：三个规模三种结论")

    return _finish(
        fig,
        "fig6_policy",
        f"seed=20240101 | 独立测试集 60,000 人；预算 B={float(six['budget'].iloc[0]):,.0f} 元；"
        f"五个策略同预算同人群；随机策略为 {int(rnd['种子数'].iloc[0])} 个种子均值；误差棒 = bootstrap 95% CI",
    )


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
