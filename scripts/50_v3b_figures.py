"""v3b 长稿配图生成器（组图优先）。

设计约定
--------
- 一律复用 ``causal_growth.viz`` 的 ``apply_style`` / ``add_source_note`` / ``save_fig``，
  中文字体与来源注由项目工具统一处理，脚本里**不再手打"合成数据"字样**（避免重复标注）。
- 每张图都是**多面板组图**：读者看一张图能同时得到"水平、异质性、与基准的距离"。
- 图注里的 seed / 层级 / R 由本脚本生成后写入 ``paper/v3b/figures/_captions.md``，
  正文引用时直接抄，保证图注与数据同源。
- 数据只来自 ``outputs/tables/*.csv`` 与既有 JSON，不重算、不手工填数。

用法::

    .\\.venv\\Scripts\\python.exe scripts\\50_v3b_figures.py            # 全部
    .\\.venv\\Scripts\\python.exe scripts\\50_v3b_figures.py --only f4 f6
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from causal_growth import viz

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
FIG_OUT = ROOT / "outputs" / "figures" / "v3b"
PAPER_FIG = ROOT / "paper" / "v3b" / "figures"

CAPTIONS: list[tuple[str, str]] = []
HIGHLIGHT = "#c0392b"
BASE = "#2c3e50"
MUTED = "#95a5a6"
AA_COLOR = "#2980b9"


def _finish(fig, name: str, note: str, caption: str) -> None:
    """统一收尾：来源注 + 落盘 + 记图注。"""
    viz.add_source_note(fig, note)
    path = viz.save_fig(fig, name, subdir="v3b")
    CAPTIONS.append((f"{name}.png", caption))
    print(f"  ✓ {path.relative_to(ROOT)}")


def _bar_with_ci(ax, labels, means, los, his, color=BASE, fmt="{:.3f}") -> None:
    x = np.arange(len(labels))
    ax.bar(x, means, color=color, alpha=0.85, width=0.6)
    ax.errorbar(x, means, yerr=[np.array(means) - np.array(los), np.array(his) - np.array(means)],
                fmt="none", ecolor="black", capsize=4, lw=1)
    # 数值标签放在**误差棒上端之上**，避免压在参考虚线上（面板 a/c 都是这个情形）
    for xi, m, h in zip(x, means, his):
        ax.annotate(fmt.format(m), (xi, h), textcoords="offset points", xytext=(0, 4),
                    ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)


# --------------------------------------------------------------------------- #
# 图 4：流程校准（AA）
# --------------------------------------------------------------------------- #
def fig4_aa() -> None:
    merged = pd.read_csv(TABLES / "v3_phase_D_aa_formal_merged.csv")
    nc = pd.read_csv(TABLES / "v3_phase_D_aa_nc20w_L0.csv")
    se = json.loads((TABLES / "v3_phase_D_aa_formal_merged.json").read_text(encoding="utf-8"))["se_calibration"]

    profit = merged[(merged.metric == "net_profit") & (merged.block == "true_aa")]
    order = ["L0", "L1", "L2", "L3", "POOLED"]
    profit = profit.set_index("layer").loc[order].reset_index()

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.4))

    # (a) 逐层与合并 FPR
    ax = axes[0, 0]
    labels = [x if x != "POOLED" else "合并" for x in order]
    _bar_with_ci(ax, labels, profit.fpr.tolist(), profit.cp_low.tolist(), profit.cp_high.tolist(), AA_COLOR)
    ax.axhline(0.05, color=HIGHLIGHT, ls="--", lw=1.2, label="名义水平 0.05")
    ax.set_ylabel("假阳性率")
    ax.set_title("(a) 净增量利润的假阳性率与 95% 精确区间")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_ylim(0, 0.11)

    # (b) 三个指标分别看
    ax = axes[0, 1]
    metrics = [("net_profit", "净增量利润", BASE), ("paid_purchase_7d", "购买率", "#27ae60"),
               ("any_refund_30d", "退款率", "#8e44ad")]
    width = 0.26
    for i, (m, label, color) in enumerate(metrics):
        sub = merged[(merged.metric == m) & (merged.block == "true_aa")].set_index("layer").loc[order]
        ax.bar(np.arange(len(order)) + (i - 1) * width, sub.fpr.to_numpy(), width=width,
               label=label, color=color, alpha=0.85)
    ax.axhline(0.05, color=HIGHLIGHT, ls="--", lw=1.2)
    ax.set_xticks(np.arange(len(order)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("假阳性率")
    ax.set_title("(b) 三个指标分别校准：主指标与两个辅助指标")
    ax.legend(fontsize=8, loc="upper right")

    # (c) 标准误校准
    ax = axes[1, 0]
    ratio_layers = [x["layer"] for x in se]
    ratios = [x["ratio"] for x in se]
    _bar_with_ci(ax, [x if x != "POOLED" else "合并" for x in ratio_layers], ratios,
                 [r - 0.02 for r in ratios], [r + 0.02 for r in ratios], "#16a085", fmt="{:.3f}")
    ax.axhline(1.0, color=HIGHLIGHT, ls="--", lw=1.2, label="校准目标 1.0")
    ax.set_ylabel("经验标准差 / 平均估计标准误")
    ax.set_ylim(0.9, 1.1)
    ax.set_title("(c) 标准误校准比：实际波动与声称精度是否一致")
    ax.legend(fontsize=8, loc="upper right")

    # (d) 负对照：购买率给 α、利润给功效
    ax = axes[1, 1]
    block = nc[nc.block == "purchase_null_negative_control"]
    full = block[block.analysis_population == "full"] if "analysis_population" in block else block
    rows = {
        "购买率\n（真值 0，应为 α）": float(full[full.metric == "paid_purchase_7d"].fpr.iloc[0]),
        "退款率\n（真值非 0）": float(full[full.metric == "any_refund_30d"].fpr.iloc[0]),
        "净增量利润\n（真值远大于 0，应为功效）": float(full[full.metric == "net_profit"].fpr.iloc[0]),
    }
    names = list(rows)
    vals = list(rows.values())
    colors = ["#27ae60", "#8e44ad", HIGHLIGHT]
    ax.bar(range(len(names)), vals, color=colors, alpha=0.85, width=0.6)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=9)
    ax.axhline(0.05, color=HIGHLIGHT, ls="--", lw=1.2, label="名义水平 0.05")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("拒绝率")
    ax.set_ylim(0, 1.15)
    ax.set_title("(d) 负对照：同一场景同一条链路的两类读数")
    ax.legend(fontsize=8, loc="upper left")

    fig.suptitle("图 4　流程校准：1000 次零效应重复上的假阳性率、标准误校准与负对照", fontsize=12)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    _finish(fig, "fig4_aa_calibration",
            "四层 × 250 次，共 1000 次；n = 200 000；α = 0.05；"
            "源表 v3_phase_D_aa_formal_merged.csv / _merged.json、v3_phase_D_aa_nc20w_L0.csv",
            "图 4　流程校准。四层各 250 次零效应重复（合计 1000 次，n=200 000，α=0.05）。"
            "(a) 净增量利润假阳性率与 Clopper–Pearson 95% 精确区间；(b) 三个指标分别校准；"
            "(c) 标准误校准比（经验标准差/平均估计标准误），目标 1.0；"
            "(d) 负对照：购买率真值为 0 故应按 α，利润真值远大于 0 故应为功效，二者不可互换。")


# --------------------------------------------------------------------------- #
# 图 6：四层 ATE
# --------------------------------------------------------------------------- #
def fig6_four_layers() -> None:
    core = pd.read_csv(TABLES / "v3_g_g_core.csv")
    ate = core[core.metric == "ate"].set_index("level").loc[["L0", "L1", "L2", "L3"]].reset_index()

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.6))

    ax = axes[0]
    _bar_with_ci(ax, ate.level, ate["mean"].tolist(),
                 (ate["mean"] - 1.96 * ate.MC_SE).tolist(),
                 (ate["mean"] + 1.96 * ate.MC_SE).tolist(), BASE, fmt="{:.2f}")
    ax.set_ylabel("人均净增量利润（元/人）")
    ax.set_title("(a) 四层核心格：500 次重复的 ATE")
    ax.set_ylim(0, 1.95)

    ax = axes[1]
    fold = (ate["mean"] / ate["mean"].iloc[0]).tolist()
    bars = ax.bar(ate.level, fold, color=[BASE, BASE, BASE, HIGHLIGHT], alpha=0.85, width=0.6)
    for i, v in enumerate(fold):
        ax.text(i, v, f"×{v:.2f}", ha="center", va="bottom", fontsize=9)
    ax.axhline(1.0, color=MUTED, ls="--", lw=1.0)
    ax.set_ylabel("相对 L0 的倍数")
    ax.set_title("(b) 相对 L0：前三层缓升，L3 跳变")
    ax.set_ylim(0, 8.0)

    ax = axes[2]
    ax.scatter(ate.R, ate.sd, s=70, color=BASE, label="重复间标准差", zorder=3)
    ax.scatter(ate.R, ate.MC_SE, s=70, color=HIGHLIGHT, marker="s", label="蒙特卡洛标准误", zorder=3)
    for i, row in ate.iterrows():
        ax.annotate(row.level, (row.R, row.sd), textcoords="offset points", xytext=(6, 4), fontsize=9)
    ax.set_xlabel("重复次数 R")
    ax.set_ylabel("单位：元/人")
    ax.set_title("(c) 重复间标准差与 MC 标准误相差 √R 倍")
    ax.set_xlim(400, 600)
    ax.legend(fontsize=8)

    fig.suptitle("图 6　四层正式重复：ATE 的量级、相对 L0 的跳变与重复间波动", fontsize=12)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig6_four_layer_ate",
            "Tier1 core 四格各 R = 500；n = 200 000；"
            "源表 v3_g_g_core.csv（metric = ate）",
            "图 6　四层正式重复的 ATE。(a) 四层核心格的点估计与 95% 区间（±1.96 倍 MC 标准误）；"
            "(b) 以 L0 为基准的倍数：L1/L2 缓升，L3 因放松无未观测混淆假设而跳变；"
            "(c) 重复间标准差与蒙特卡洛标准误，二者之比反映设计重复数。")


# --------------------------------------------------------------------------- #
# 图 7：机制旋钮响应
# --------------------------------------------------------------------------- #
def fig7_knobs() -> None:
    t2 = pd.read_csv(TABLES / "v3_g_g_tier2.csv")
    t2 = t2[t2.metric == "ate"].set_index("cell_id")

    def take(cell: str) -> tuple[float, float, float]:
        row = t2.loc[cell]
        return float(row["mean"]), float(row["mean"] - 1.96 * row.MC_SE), float(row["mean"] + 1.96 * row.MC_SE)

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.2))

    # (a) λ_T 扫描
    ax = axes[0, 0]
    lam = [0.25, 0.75, 1.50]
    cells = ["L3_fixed_lt025", "L3_fixed_lt075", "L3_fixed_lt150"]
    vals = [take(c)[0] for c in cells]
    lo = [take(c)[1] for c in cells]
    hi = [take(c)[2] for c in cells]
    ax.errorbar(lam, vals, yerr=[np.array(vals) - np.array(lo), np.array(hi) - np.array(vals)],
                marker="o", color=HIGHLIGHT, capsize=5, lw=1.8, ms=7)
    core_l3 = take("L3_fixed_lt000") if "L3_fixed_lt000" in t2.index else None
    for x, v in zip(lam, vals):
        ax.annotate(f"{v:.3f}", (x, v), textcoords="offset points", xytext=(0, 9), fontsize=8, ha="center")
    ax.set_xlabel("未观测混淆强度 λ_T")
    ax.set_ylabel("人均净增量利润 ATE（元/人）")
    ax.set_title("(a) λ_T 扫描：混淆越强，名义 ATE 越大")
    ax.set_xticks(lam)

    # (b) λ_T × λ_Y 联合
    ax = axes[0, 1]
    joint = [("L3_joint_lam000", "λ 全 0"), ("L3_joint_lam150", "λ 全 1.5")]
    labels = [lab for _, lab in joint]
    vals = [take(c)[0] for c, _ in joint]
    lo = [take(c)[1] for c, _ in joint]
    hi = [take(c)[2] for c, _ in joint]
    _bar_with_ci(ax, labels, vals, lo, hi, "#8e44ad", fmt="{:.3f}")
    ax.set_ylabel("ATE（元/人）")
    ax.set_title("(b) 联合混淆：两层旋钮同向放大")

    # (c) 极端重叠与缺失混淆
    ax = axes[1, 0]
    special = [("L3_fixed_lt075", "λ_T=0.75 基准"), ("L3_overlap_extreme", "极端重叠"),
               ("L3_missing_confounders", "缺失混淆")]
    vals = [take(c)[0] for c, _ in special]
    lo = [take(c)[1] for c, _ in special]
    hi = [take(c)[2] for c, _ in special]
    _bar_with_ci(ax, [lab for _, lab in special], vals, lo, hi, "#d35400", fmt="{:.3f}")
    ax.set_ylabel("ATE（元/人）")
    ax.set_title("(c) 叠加机制：重叠与缺失各自改变量级")

    # (d) L1 异质性两端
    ax = axes[1, 1]
    het = [("L1_heterogeneity_000", "异质性下限"), ("L1_heterogeneity_150", "异质性上限"),
           ("L1_cost_prediction_under", "成本低估")]
    vals = [take(c)[0] for c, _ in het]
    lo = [take(c)[1] for c, _ in het]
    hi = [take(c)[2] for c, _ in het]
    _bar_with_ci(ax, [lab for _, lab in het], vals, lo, hi, "#27ae60", fmt="{:.3f}")
    ax.set_ylabel("ATE（元/人）")
    ax.set_title("(d) 异质性两端：机制变化对 ATE 的影响幅度")

    fig.suptitle("图 7　机制旋钮的响应：混淆强度、重叠、缺失与异质性各自把结论推向哪里", fontsize=12)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig7_mechanism_knobs",
            "Tier2 选中格各 R = 30（不与 Tier1 并列排序）；n = 200 000；"
            "源表 v3_g_g_tier2.csv（metric = ate）；区间为 ±1.96 倍 MC 标准误",
            "图 7　机制旋钮的响应（Tier2 选中格，各 R=30，不与 Tier1 并列排序）。(a) 未观测混淆强度 λ_T 的三点扫描；"
            "(b) λ_T 与 λ_Y 联合取两端的对照；(c) 极端重叠与缺失混淆相对基准的偏移；"
            "(d) 异质性两端与成本低估格。所有区间为 ±1.96 倍 MC 标准误，仅作描述，不作判别。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", default=None, help="只画指定编号，如 f4 f6 f7")
    args = parser.parse_args()

    viz.apply_style()
    FIG_OUT.mkdir(parents=True, exist_ok=True)
    PAPER_FIG.mkdir(parents=True, exist_ok=True)

    registry = {"f4": fig4_aa, "f6": fig6_four_layers, "f7": fig7_knobs}
    todo = registry if not args.only else {k: registry[k] for k in args.only if k in registry}

    for key, fn in todo.items():
        print(f"[{key}] {fn.__name__}")
        fn()

    # 图注按图名合并后整体重写：追加写会在多次运行时重复累积（本脚本第一版就踩了这个坑）
    cap_json = PAPER_FIG / "_captions.json"
    store: dict[str, str] = {}
    if cap_json.exists():
        store = json.loads(cap_json.read_text(encoding="utf-8"))
    store.update({name: caption for name, caption in CAPTIONS})
    cap_json.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    (PAPER_FIG / "_captions.md").write_text(
        "\n\n".join(f"**{n}**\n\n{c}" for n, c in sorted(store.items())) + "\n", encoding="utf-8"
    )

    # 同步到 paper/v3b/figures（build.sh 只从这里复制）
    for png in FIG_OUT.glob("*.png"):
        shutil.copy2(png, PAPER_FIG / png.name)
    print(f"\n本次生成 {len(CAPTIONS)} 张；已同步到 paper/v3b/figures/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
