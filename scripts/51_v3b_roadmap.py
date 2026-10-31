"""图 1：技术路线图（业务问题 → 四层环境 → 三类检验 → 决策与边界）。

为什么单独一个脚本：路线图是纯矢量流程示意，不含数据，迭代频率低但与正文版式强相关，
和"读表出图"的 50 号脚本分开更好维护。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from causal_growth import viz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figures" / "v3b"
PAPER = ROOT / "paper" / "v3b" / "figures"

INK = "#2c3e50"
ACCENT = "#c0392b"
COOL = "#2980b9"
MUTED = "#7f8c8d"


def _box(ax, x, y, w, h, title, body="", *, face="#eef3f8", edge=INK, title_size=10.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                linewidth=1.1, edgecolor=edge, facecolor=face))
    ty = y + h - 0.052 if body else y + h / 2 - 0.012
    ax.text(x + w / 2, ty, title, ha="center", va="top", fontsize=title_size,
            fontweight="bold", color=edge)
    if body:
        ax.text(x + w / 2, ty - 0.058, body, ha="center", va="top", fontsize=8.2,
                color="#34495e", linespacing=1.5)


def _arrow(ax, p0, p1, *, color=MUTED, style="-|>", lw=1.2):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=13,
                                 linewidth=lw, color=color, shrinkA=2, shrinkB=2))


def main() -> int:
    viz.apply_style()
    OUT.mkdir(parents=True, exist_ok=True)
    PAPER.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12.4, 6.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # 第 1 行：业务问题
    _box(ax, 0.15, 0.845, 0.70, 0.135,
         "业务问题：一笔固定预算，怎么花",
         "是否发券　·　发给谁　·　发多大面额　·　如何说明净增量利润及其边界",
         face="#fdecea", edge=ACCENT, title_size=11)

    # 第 2 行：四层环境
    layers = [
        ("L0", "机制最干净", "保留零膨胀与重尾", "#eaf4fb", COOL),
        ("L1", "金额链路", "首单·复购·异质性", "#eaf4fb", COOL),
        ("L2", "时间与人群", "漂移·构成·成熟", "#eaf4fb", COOL),
        ("L3", "未观测混淆", "混淆强度·重叠·缺失", "#fdecea", ACCENT),
    ]
    w, gap = 0.205, 0.035
    x0 = (1 - (w * 4 + gap * 3)) / 2
    for i, (tag, title, body, face, edge) in enumerate(layers):
        x = x0 + i * (w + gap)
        _box(ax, x, 0.575, w, 0.185, f"{tag}　{title}", body, face=face, edge=edge, title_size=10)
        if i < 3:
            _arrow(ax, (x + w + 0.004, 0.665), (x + w + gap - 0.004, 0.665))

    ax.text(0.5, 0.788, "每层只放松一条假设，失效因此可以被归因",
            ha="center", va="center", fontsize=9, color=INK, style="italic")

    # 第 3 行：三类检验
    checks = [
        ("流程校准", "零效应重复的假阳性率\n标准误校准\n负对照"),
        ("平均效应与异质性", "四层处理效应\n模型对照与选模\n个体排序质量"),
        ("策略与预算", "预算档扫描\n求解器与成本模型\n观测闭环与护栏"),
    ]
    cw, cgap = 0.28, 0.04
    cx0 = (1 - (cw * 3 + cgap * 2)) / 2
    for i, (title, body) in enumerate(checks):
        x = cx0 + i * (cw + cgap)
        _box(ax, x, 0.335, cw, 0.175, title, body, face="#f4f6f7", edge=MUTED, title_size=10)

    # 四层 → 三类检验：中间画一条汇聚线
    ax.plot([0.5, 0.5], [0.565, 0.515], color=MUTED, lw=1.2)
    ax.plot([cx0 + cw / 2, cx0 + (cw + cgap) * 2 + cw / 2], [0.515, 0.515], color=MUTED, lw=1.2)
    for i in range(3):
        x = cx0 + i * (cw + cgap) + cw / 2
        _arrow(ax, (x, 0.515), (x, 0.512), lw=1.0)

    # 第 4 行：决策与边界
    _box(ax, 0.15, 0.125, 0.70, 0.135,
         "决策与适用边界",
         "净增量利润的点估计与区间　·　护栏的两种口径　·　失效条件与证据",
         face="#eafaf1", edge="#27ae60", title_size=11)
    _arrow(ax, (0.5, 0.328), (0.5, 0.268))

    # 左侧纵向标注：三阶段
    for y, label in ((0.905, "提出问题"), (0.665, "构造环境"), (0.425, "分别检验"), (0.19, "回答与划界")):
        ax.text(0.045, y, label, ha="center", va="center", fontsize=8.5,
                color=MUTED, rotation=90)

    viz.add_source_note(fig, "示意图，不含数据；层级划分与检验分工见第 2 节", reserve_bottom=0.10)
    path = viz.save_fig(fig, "fig1_roadmap", subdir="v3b")
    shutil.copy2(path, PAPER / path.name)
    print(f"  ✓ {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
