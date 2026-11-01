"""重画图 3：金额链路与退款账务。两栏对齐列表，不做窄框，避免文字溢出。"""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib.pyplot as plt

from causal_growth import viz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figures" / "v3b"
PAPER = ROOT / "paper" / "v3b" / "figures"

FS_T, FS_B, FS_N = 10.5, 8.9, 8.4


def two_col_list(ax, title, rows, *, top=0.88, step=0.165):
    ax.set_title(title, fontsize=FS_T, pad=10)
    for i, (left, right) in enumerate(rows):
        y = top - i * step
        ax.text(0.02, y, left, ha="left", va="center", fontsize=FS_B, fontweight="bold")
        ax.text(0.30, y, right, ha="left", va="center", fontsize=FS_B)
        ax.plot([0.02, 0.98], [y - step * 0.42, y - step * 0.42], color="black", lw=0.4)


def main() -> None:
    viz.apply_style()
    OUT.mkdir(parents=True, exist_ok=True)
    PAPER.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.9),
                             gridspec_kw={"width_ratios": [1.22, 1]})
    for ax in axes:
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    two_col_list(axes[0], "(a) 金额链路：券只作用在首单", [
        ("购物车", "金额 $V_i$"),
        ("首单", "$Q_i V_i$，$Q_i\\sim$ 截断正态（0.70±0.10）"),
        ("核销", "概率 0.55；核销则扣券 10 元"),
        ("退款", "概率 7.5%，发券组 ×1.03"),
        ("复购", "概率 5%；金额为首单的 55%"),
    ])
    axes[0].text(0.02, 0.02, "复购不带券，属基线收入而非增量", ha="left", va="center", fontsize=FS_N)

    two_col_list(axes[1], "(b) 一单退款时的账务处理", [
        ("收入", "全额冲减"),
        ("商品成本", "按 85% 回收"),
        ("履约成本", "不回收"),
        ("券成本", "不退还"),
        ("退款手续费", "按毛额 1% 加收"),
    ])
    axes[1].text(0.02, 0.02, "结果：退款单同时损失收入与券", ha="left", va="center", fontsize=FS_N)

    fig.tight_layout(rect=(0, 0.01, 1, 1))
    viz.save_fig(fig, "fig3_money_chain", subdir="v3b")
    shutil.copy2(OUT / "fig3_money_chain.png", PAPER / "fig3_money_chain.png")
    print("  ✓ fig3")


if __name__ == "__main__":
    raise SystemExit(main())
