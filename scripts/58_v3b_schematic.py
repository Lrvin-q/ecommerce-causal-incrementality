"""重画三张示意图：技术路线、四层假设放松、金额链路。

设计约束（按作者要求）：白底、黑字、无填充、无重叠、字号统一、逻辑一眼可读。
不使用彩色与阴影；框线细、箭头实线。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

from causal_growth import viz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figures" / "v3b"
PAPER = ROOT / "paper" / "v3b" / "figures"

FS_T = 11.0   # 框标题
FS_B = 9.2    # 框正文
FS_N = 8.6    # 注释


def box(ax, x, y, w, h, title, body=(), *, lw=0.9, title_fs=FS_T, body_fs=FS_B, gap=0.052):
    ax.add_patch(Rectangle((x, y), w, h, fill=True, facecolor="white",
                           edgecolor="black", linewidth=lw, zorder=2))
    cx = x + w / 2
    if body:
        ax.text(cx, y + h - 0.045, title, ha="center", va="top",
                fontsize=title_fs, fontweight="bold", zorder=3)
        for i, line in enumerate(body):
            ax.text(cx, y + h - 0.045 - gap * (i + 1.15), line, ha="center", va="top",
                    fontsize=body_fs, zorder=3)
    else:
        ax.text(cx, y + h / 2, title, ha="center", va="center",
                fontsize=title_fs, fontweight="bold", zorder=3)


def arrow(ax, p0, p1, *, lw=0.9):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=9,
                                 linewidth=lw, color="black", shrinkA=1, shrinkB=1, zorder=1))


# --------------------------------------------------------------------------- #
def fig1() -> None:
    fig, ax = plt.subplots(figsize=(7.4, 8.2))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    W, X = 0.58, 0.20
    rows = [
        (0.845, 0.115, "业务问题",
         ["有限预算下，是否发券、发给谁、给多少"]),
        (0.690, 0.115, "目标量与口径",
         ["净增量贡献利润为主指标", "分母＝随机分配的全部用户"]),
        (0.505, 0.150, "四层生成过程",
         ["L0 最理想的基线　L1 金额链路与异质性", "L2 时间与人群　L3 不可观测混淆"]),
        (0.300, 0.170, "三类检验",
         ["流程校准：零效应重复的假阳性率", "平均效应：与解析真值逐层对照",
          "策略与预算：名单、支出与护栏"]),
        (0.080, 0.115, "结论与适用边界",
         ["哪些结论可引用、在什么条件下失效"]),
    ]
    for y, h, title, body in rows:
        box(ax, X, y, W, h, title, body)
    for i in range(len(rows) - 1):
        y_top = rows[i][0]
        y_bot = rows[i + 1][0] + rows[i + 1][1]
        arrow(ax, (X + W / 2, y_top - 0.004), (X + W / 2, y_bot + 0.004))

    # 右侧注释：真值可算
    ax.annotate("真值由解析式给出\n偏差可逐层核对",
                xy=(X + W, 0.575), xytext=(0.815, 0.575),
                ha="left", va="center", fontsize=FS_N,
                arrowprops=dict(arrowstyle="-", lw=0.7, color="black"))
    ax.annotate("每层只增加\n一条假设",
                xy=(X + W, 0.555), xytext=(0.815, 0.300),
                ha="left", va="center", fontsize=FS_N,
                arrowprops=dict(arrowstyle="-", lw=0.7, color="black"))

    viz.save_fig(fig, "fig1_roadmap", subdir="v3b")
    shutil.copy2(OUT / "fig1_roadmap.png", PAPER / "fig1_roadmap.png")


def fig2() -> None:
    fig, ax = plt.subplots(figsize=(9.6, 3.9))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    cols = [
        ("L0", "最理想的基线", ["分配与结果无关", "效应与成本同质"]),
        ("L1", "金额链路与异质性", ["购物车→首单→复购", "效应随特征变化"]),
        ("L2", "时间与人群", ["分周投放与漂移", "人群构成变化"]),
        ("L3", "不可观测混淆", ["存在不可观测因子", "可影响分配与结果"]),
    ]
    w, gap = 0.205, 0.045
    x0 = (1 - (w * 4 + gap * 3)) / 2
    for i, (tag, title, body) in enumerate(cols):
        x = x0 + i * (w + gap)
        ax.add_patch(Rectangle((x, 0.30), w, 0.46, facecolor="white",
                               edgecolor="black", linewidth=0.9))
        ax.text(x + w / 2, 0.705, tag, ha="center", va="center",
                fontsize=15, fontweight="bold")
        ax.text(x + w / 2, 0.640, title, ha="center", va="center", fontsize=FS_T)
        for k, line in enumerate(body):
            ax.text(x + w / 2, 0.545 - k * 0.075, line, ha="center", va="center", fontsize=FS_B)
        if i < 3:
            arrow(ax, (x + w + 0.004, 0.53), (x + w + gap - 0.004, 0.53))

    ax.text(0.5, 0.185, "逐层增加一条假设；前三层的处理分配与结果无关，L3 的核心格亦不含不可观测因子",
            ha="center", va="center", fontsize=FS_N)
    ax.text(0.5, 0.09, "本文因此把这四层当作并列的压力测试，而不是可直接相减的阶梯",
            ha="center", va="center", fontsize=FS_N)

    viz.save_fig(fig, "fig2_layer_mechanisms", subdir="v3b")
    shutil.copy2(OUT / "fig2_layer_mechanisms.png", PAPER / "fig2_layer_mechanisms.png")


def fig3() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.6),
                             gridspec_kw={"width_ratios": [1.55, 1]})

    # (a) 链路
    ax = axes[0]
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    steps = [
        (0.03, "购物车", "金额 $V_i$"),
        (0.28, "首单", "$Q_i V_i$，$Q_i\\sim$ 截断正态\n均值 0.70、标准差 0.10"),
        (0.53, "核销", "概率 0.55；核销则扣券 10 元"),
        (0.76, "复购", "概率 5%；金额为首单 55%"),
    ]
    for x, title, body in steps:
        ax.add_patch(Rectangle((x, 0.40), 0.20, 0.34, facecolor="white",
                               edgecolor="black", linewidth=0.9))
        ax.text(x + 0.10, 0.685, title, ha="center", va="center", fontsize=FS_T, fontweight="bold")
        ax.text(x + 0.10, 0.545, body, ha="center", va="center", fontsize=FS_N)
    for x in (0.235, 0.485, 0.725):
        arrow(ax, (x, 0.57), (x + 0.042, 0.57))
    ax.text(0.5, 0.235, "券只对首单生效：复购不带券，属基线收入而非增量",
            ha="center", va="center", fontsize=FS_B)
    ax.set_title("(a) 金额链路：券的作用点只有一处", fontsize=FS_T)

    # (b) 退款账务
    ax = axes[1]
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.set_title("(b) 一单退款时的账务处理", fontsize=FS_T)
    items = [("收入", "全额冲减"), ("商品成本", "按 85% 回收"),
             ("履约成本", "不回收"), ("券成本", "不退还"),
             ("退款手续费", "按毛额 1% 加收")]
    for i, (name, rule) in enumerate(items):
        y = 0.80 - i * 0.145
        ax.text(0.04, y, name, ha="left", va="center", fontsize=FS_B)
        ax.text(0.97, y, rule, ha="right", va="center", fontsize=FS_B)
        ax.plot([0.04, 0.97], [y - 0.055, y - 0.055], color="black", lw=0.4)
    ax.text(0.5, 0.05, "退款单同时损失收入与券", ha="center", va="center", fontsize=FS_N)

    fig.tight_layout(rect=(0, 0.02, 1, 1))
    viz.save_fig(fig, "fig3_money_chain", subdir="v3b")
    shutil.copy2(OUT / "fig3_money_chain.png", PAPER / "fig3_money_chain.png")


def main() -> None:
    viz.apply_style()
    OUT.mkdir(parents=True, exist_ok=True)
    PAPER.mkdir(parents=True, exist_ok=True)
    fig1(); print("  ✓ fig1")
    fig2(); print("  ✓ fig2")
    fig3(); print("  ✓ fig3")


if __name__ == "__main__":
    raise SystemExit(main())
