"""重画图 1：技术路线。按内容行数自动计算框高，从上往下顺序排布，避免溢出。"""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

from causal_growth import viz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figures" / "v3b"
PAPER = ROOT / "paper" / "v3b" / "figures"

FS_T, FS_B, FS_N = 10.5, 8.8, 8.4
LINE = 0.040          # 每行正文占用的高度（归一化坐标）
PAD_TOP, PAD_BOT = 0.034, 0.022


def h_for(n_lines: int) -> float:
    return PAD_TOP + PAD_BOT + LINE * n_lines


def draw(ax, x, y, w, h, title, lines):
    ax.add_patch(Rectangle((x, y), w, h, facecolor="white", edgecolor="black", linewidth=0.8))
    ax.text(x + w / 2, y + h - PAD_TOP / 2, title, ha="center", va="center",
            fontsize=FS_T, fontweight="bold")
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - PAD_TOP - LINE * (i + 0.5), line,
                ha="center", va="center", fontsize=FS_B)


def arrow(ax, x, y0, y1):
    ax.add_patch(FancyArrowPatch((x, y0), (x, y1), arrowstyle="-|>", mutation_scale=8,
                                 linewidth=0.8, color="black", shrinkA=0, shrinkB=0))


def main() -> None:
    viz.apply_style()
    OUT.mkdir(parents=True, exist_ok=True)
    PAPER.mkdir(parents=True, exist_ok=True)

    blocks = [
        ("业务问题", ["有限预算下，是否发券、发给谁、给多少"]),
        ("目标量与口径", ["净增量贡献利润为主指标", "分母＝随机分配的全部用户"]),
        ("四层生成过程", ["L0 最理想的基线　L1 金额链路与异质性",
                          "L2 时间与人群　L3 不可观测混淆"]),
        ("三类检验", ["流程校准：零效应重复的假阳性率",
                      "平均效应：与解析真值逐层对照",
                      "策略与预算：名单、支出与护栏"]),
        ("结论与适用边界", ["哪些结论可引用、在什么条件下失效"]),
    ]
    gap = 0.052
    total = sum(h_for(len(b[1])) for b in blocks) + gap * (len(blocks) - 1)
    fig_h_in = 9.2
    fig, ax = plt.subplots(figsize=(7.0, fig_h_in))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    W, X = 0.62, 0.19
    y = (1 + total) / 2 - 0.02          # 顶部起点
    boxes = []
    for title, lines in blocks:
        h = h_for(len(lines))
        y -= h
        draw(ax, X, y, W, h, title, lines)
        boxes.append((y, h))
        y -= gap

    for (y0, h0), (y1, h1) in zip(boxes, boxes[1:]):
        arrow(ax, X + W / 2, y0 - 0.004, y0 - (y0 - (y1 + h1)) + 0.004)

    ax.text(0.5, 0.035,
            "真值由数据生成过程的解析式给出，偏差逐层可核对；四层是并列的压力测试，不是可直接相减的阶梯。",
            ha="center", va="center", fontsize=FS_N)

    viz.save_fig(fig, "fig1_roadmap", subdir="v3b")
    shutil.copy2(OUT / "fig1_roadmap.png", PAPER / "fig1_roadmap.png")
    print("  ✓ fig1")


if __name__ == "__main__":
    raise SystemExit(main())
