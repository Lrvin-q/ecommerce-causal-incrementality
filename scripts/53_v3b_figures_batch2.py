"""v3b 长稿配图第二批：MDE 与功效、模型对照、护栏、重采样。

与 50 号脚本同一套约定（复用 viz 工具、组图优先、图注与数据同源）。
单独成文件的原因：这一批涉及"多表拼接 + 分布图"，与首批的"单表柱状"逻辑不同，
分开后单文件更短、更易维护。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from causal_growth import viz

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
EVID = ROOT / "outputs" / "evidence"
FIG_OUT = ROOT / "outputs" / "figures" / "v3b"
PAPER_FIG = ROOT / "paper" / "v3b" / "figures"

CAPTIONS: list[tuple[str, str]] = []
BASE, ACCENT, COOL, MUTED = "#2c3e50", "#c0392b", "#2980b9", "#95a5a6"


def _finish(fig, name: str, note: str, caption: str) -> None:
    # 数据来源统一在附录说明，逐图不再重复（用户要求）
    _ = note
    path = viz.save_fig(fig, name, subdir="v3b")
    CAPTIONS.append((f"{name}.png", caption))
    print(f"  ✓ {path.relative_to(ROOT)}")


# --------------------------------------------------------------------------- #
# 图 5：最小可检测效应与实测功效
# --------------------------------------------------------------------------- #
def fig5_mde_power() -> None:
    mde = pd.read_csv(TABLES / "v3_phase_D_mde.csv")
    dm = mde[(mde.record_type == "design_mde") & (abs(mde.treatment_share - 0.5) < 1e-9)]

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.5))

    # (a) 逐层 MDE：两个指标、两个尺度
    ax = axes[0]
    layers = ["L0", "L1", "L2", "L3"]
    profit = [dm[(dm.level == lv) & dm.metric.str.contains("net_profit") & (dm.n_total == 200000)].mde.min() for lv in layers]
    ax.bar(np.arange(4) - 0.18, profit, width=0.34, color=BASE, alpha=0.88, label="利润（左轴，元/人）")
    ax.set_ylabel("利润 MDE（元/人）")
    ax.set_xticks(np.arange(4))
    ax.set_xticklabels(layers)
    ax.set_ylim(0, 0.16)
    for i, v in enumerate(profit):
        ax.annotate(f"{v:.3f}", (i - 0.18, v), textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8)
    ax2 = ax.twinx()
    purchase = [dm[(dm.level == lv) & (dm.metric == "paid_purchase_7d") & (dm.n_total == 200000)].mde.min() * 100 for lv in layers]
    ax2.bar(np.arange(4) + 0.18, purchase, width=0.34, color=COOL, alpha=0.85, label="购买率（右轴，百分点）")
    ax2.set_ylabel("购买率 MDE（百分点）")
    ax2.set_ylim(0, 0.55)
    for i, v in enumerate(purchase):
        ax2.annotate(f"{v:.2f}", (i + 0.18, v), textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8)
    ax.set_title("(a) 固定 20 万反算的最小可检测效应")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper center", ncol=2)

    # (b) 实测功效曲线
    ax = axes[1]
    lp = pd.read_csv(TABLES / "v3_phase_D_local_power_formal.csv")
    style = {"below_design_mde": (MUTED, "o", "低于设计 MDE"),
             "boundary_zero_margin": (ACCENT, "s", "零余量边界"),
             "above_design_mde": (COOL, "^", "高于设计 MDE")}
    for cls, (color, marker, label) in style.items():
        sub = lp[lp.power_cell_class == cls]
        ax.scatter(sub.multiplier, sub.rejection_rate, s=54, color=color, marker=marker, label=label, alpha=0.9)
    xs = np.linspace(0, 2.05, 100)
    ax.axhline(0.8, color=ACCENT, ls="--", lw=1.1, label="名义功效 0.80")
    ax.set_xlabel("目标效应 / 设计 MDE")
    ax.set_ylabel("实测拒绝率")
    ax.set_title("(b) 15 个格子各 100 次的实测拒绝率")
    ax.set_ylim(0, 1.06)
    ax.legend(fontsize=7.5, loc="lower right")

    # (c) 子样本与队列的 MDE 代价
    ax = axes[2]
    sub = dm[(dm.level == "L1") & dm.metric.str.contains("net_profit")]
    by_n = sub.groupby("n_total").mde.min().sort_index()
    labels = [f"{int(n/10000)} 万" if n >= 10000 else str(int(n)) for n in by_n.index]
    ax.plot(range(len(by_n)), by_n.values, marker="o", color=BASE, lw=1.8, ms=7)
    for i, v in enumerate(by_n.values):
        ax.annotate(f"{v:.3f}", (i, v), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
    ax.set_xticks(range(len(by_n)))
    ax.set_xticklabels(labels)
    ax.set_xlabel("队列规模")
    ax.set_ylabel("利润 MDE（元/人）")
    ax.set_title("(c) 子样本不能替代全量队列")

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig5_mde_power",
            "设计 MDE 为双侧 80% 功效、50/50 分流；实测功效为 15 格 × 100 次；n = 200 000（除(c)标注）",
            "图 5　检测能力。(a) 四层的利润与购买率 MDE（同为 20 万、50/50）；"
            "(b) 15 个格子的实测拒绝率与名义功效线，边界格单独标出；"
            "(c) 队列规模缩小后 MDE 的上升，说明子样本与全量不可互换。")


# --------------------------------------------------------------------------- #
# 图 8：模型对照与策略价值
# --------------------------------------------------------------------------- #
def fig8_model_comparison() -> None:
    sel = pd.read_csv(TABLES / "v3_phase_D03_formal_selection.csv").sort_values("times_chosen", ascending=True)
    paired = pd.read_csv(TABLES / "v3_phase_D03_formal_paired_diff.csv")

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.6))

    ax = axes[0]
    colors = [ACCENT if m == "constant" else BASE for m in sel.model]
    ax.barh(sel.model, sel.times_chosen, color=colors, alpha=0.88)
    for i, (m, v, s) in enumerate(zip(sel.model, sel.times_chosen, sel.share_chosen)):
        ax.annotate(f"{v}（{s:.1%}）", (v, i), textcoords="offset points", xytext=(4, 0),
                    va="center", fontsize=8)
    ax.set_xlabel("被选中次数（共 200 次重复）")
    ax.set_title("(a) 选模结果：常数策略并非总被淘汰")
    ax.set_xlim(0, 130)

    ax = axes[1]
    ax.scatter(sel.mean_rank, sel.share_chosen, s=70, color=BASE)
    for _, r in sel.iterrows():
        ax.annotate(r.model, (r.mean_rank, r.share_chosen), textcoords="offset points",
                    xytext=(5, 4), fontsize=8)
    ax.set_xlabel("平均名次（1 为最好）")
    ax.set_ylabel("被选中比例")
    ax.set_title("(b) 名次与被选比例一致")

    ax = axes[2]
    cf = paired[(paired.model == "causal_forest") & (paired.baseline.str.contains("business"))]
    budgets = sorted(cf.per_user_budget_cny.unique())
    vals = [cf[cf.per_user_budget_cny == b].mean_diff_cny_per_user.mean() for b in budgets]
    ax.plot(budgets, vals, marker="o", color=ACCENT, lw=1.9, ms=7)
    ax.axhline(0, color=MUTED, ls="--", lw=1.0)
    for x, v in zip(budgets, vals):
        ax.annotate(f"{v:+.3f}", (x, v), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=8)
    ax.set_xlabel("人均预算（元/人）")
    ax.set_ylabel("定向 − 规则 的净利差（元/人）")
    ax.set_title("(c) 同一比较在不同预算档上翻转")

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig8_model_comparison",
            "L1 核心格；5 个模型 × 200 次重复；配对比较为同一 rep、同一批用户、同一预算档",
            "图 8　模型对照（200 次重复）。(a) 五个模型被选中的次数与比例；"
            "(b) 平均名次与被选比例的一致性；"
            "(c) 因果森林下定向策略相对业务规则的净利差随预算档变化，在 0.20 元/人附近穿过零线。")


# --------------------------------------------------------------------------- #
# 图 11：退款率护栏的两种口径
# --------------------------------------------------------------------------- #
def fig11_guardrail() -> None:
    core = pd.read_csv(TABLES / "v3_g_g_core.csv")
    refund = core[core.metric == "ate_any_refund_30d"].set_index("level").loc[["L0", "L1", "L2", "L3"]].reset_index()
    f02 = pd.read_csv(TABLES / "v3_phase_F02_formal_guardrail.csv")
    sweep = pd.read_csv(TABLES / "v3_phase_F01_refund_sweep.csv")

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.5))

    ax = axes[0]
    vals = refund["mean"].to_numpy() * 100
    err = 1.96 * refund.MC_SE.to_numpy() * 100
    bars = ax.bar(refund.level, vals, yerr=err, capsize=4, color=[BASE, BASE, BASE, ACCENT], alpha=0.88)
    for i, v in enumerate(vals):
        ax.annotate(f"{v:.2f}", (i, v + err[i]), textcoords="offset points", xytext=(0, 3), ha="center", fontsize=8)
    ax.axhline(0.5, color=ACCENT, ls="--", lw=1.2, label="非劣效界值 0.5pp")
    ax.set_ylabel("退款率差（百分点）")
    ax.set_title("(a) 全员发券：L3 越过界值")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_ylim(0, 0.85)

    ax = axes[1]
    g = f02[f02.contrast.str.contains("targeted")]
    diff = float(g.mean_diff.iloc[0]) * 100
    upper = float(g.mean_ci_one_sided_upper.iloc[0]) * 100
    ax.bar([0], [diff], width=0.4, color=COOL, alpha=0.88, label="点估计")
    ax.errorbar([0], [diff], yerr=[[0], [upper - diff]], fmt="none", ecolor="black", capsize=6, lw=1.6)
    ax.annotate(f"{diff:.3f}pp", (0, diff), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=9)
    ax.annotate(f"单侧上界 {upper:.3f}pp", (0, upper), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)
    ax.axhline(0.5, color=ACCENT, ls="--", lw=1.2, label="界值 0.5pp")
    ax.set_xlim(-0.7, 0.7)
    ax.set_ylim(0, 0.62)
    ax.set_xticks([0])
    ax.set_xticklabels(["定向发券\n200 次全部通过"])
    ax.set_ylabel("退款率差（百分点）")
    ax.set_title("(b) 定向发券：护栏仍有余量")
    ax.legend(fontsize=8, loc="upper right")

    ax = axes[2]
    greedy = sweep[sweep.contrast == "greedy"].sort_values("per_user_budget_cny")
    random_ = sweep[sweep.contrast == "random"].sort_values("per_user_budget_cny")
    ax.plot(greedy.per_user_budget_cny, greedy.diff_pp, marker="o", color=ACCENT, lw=1.8, label="定向（贪心）")
    ax.plot(random_.per_user_budget_cny, random_.diff_pp, marker="s", color=COOL, lw=1.8, label="同预算随机")
    ax.axhline(0.5, color=MUTED, ls="--", lw=1.1, label="界值 0.5pp")
    ax.set_xlabel("人均预算（元/人）")
    ax.set_ylabel("退款率差（百分点）")
    ax.set_title("(c) 预算越松，护栏余量越小")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_ylim(0, 0.6)

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig11_refund_guardrail",
            "全员口径为四层核心格各 500 次；定向口径为 200 次独立随机验证（每次 20 万新用户）；"
            "预算扫描为单次代表实现的 30 个种子",
            "图 11　退款率护栏。(a) 全员发券口径下四层的退款率差，L3 越过 0.5 个百分点界值；"
            "(b) 定向发券口径下 200 次验证的点估计与单侧上界，距界值仍有余量；"
            "(c) 随预算档升高，两种策略的退款率差与余量的变化。")


# --------------------------------------------------------------------------- #
# 图 13：重采样的两条路径
# --------------------------------------------------------------------------- #
def fig13_bootstrap() -> None:
    g = pd.read_csv(TABLES / "v3_g03_fixed_bootstrap_summary.csv")
    core = g[g.tier == 1].set_index("cell").loc[["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"]].reset_index()
    retrain = pd.read_csv(TABLES / "v3_phase_G02_retrain_bootstrap.csv")

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.6))

    ax = axes[0]
    y = np.arange(len(core))[::-1]
    for yi, (_, r) in zip(y, core.iterrows()):
        color = ACCENT if r.ci_covers_zero else BASE
        ax.plot([r.ci_low, r.ci_high], [yi, yi], color=color, lw=2.6, solid_capstyle="round")
        ax.plot([r.point_diff], [yi], "o", color=color, ms=7)
    ax.axvline(0, color=MUTED, ls="--", lw=1.1)
    ax.set_yticks(y)
    ax.set_yticklabels([c.replace("_n200000_p050", "").replace("_fixed_lt000", "") for c in core.cell])
    ax.set_xlabel("定向 − 随机 的净利差（元/人）")
    ax.set_title("(a) 只重抽用户：两端两层区间跨零")
    for yi, (_, r) in zip(y, core.iterrows()):
        ax.annotate(f"{r.point_diff:+.3f}", (r.ci_high, yi), textcoords="offset points", xytext=(6, 0),
                    va="center", fontsize=8)

    ax = axes[1]
    rt = retrain.copy()
    yy = np.arange(len(rt))[::-1]
    for yi, (_, r) in zip(yy, rt.iterrows()):
        ax.plot([r.ci95_low, r.ci95_high], [yi, yi], color=COOL, lw=2.4, solid_capstyle="round")
        ax.plot([r.policy_value_mean], [yi], "o", color=COOL, ms=6)
    ax.axvline(0, color=MUTED, ls="--", lw=1.1)
    ax.set_yticks(yy)
    ax.set_yticklabels([str(v).replace("_n200000_p050", "").replace("_fixed_lt000", "")[:24] for v in rt.cell_id])
    ax.set_xlabel("策略价值（元/人，含重训波动）")
    ax.set_title("(b) 重抽总体并重训：波动来源更多")

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig13_bootstrap",
            "固定策略重采样 1000 次（只重抽用户）；重训重采样 200 次（重抽总体并重训模型）；0.20 元/人档",
            "图 13　两类重采样。(a) 冻结策略下只重抽用户，四层中 L0 与 L3 的区间跨零；"
            "(b) 重抽历史总体并重训模型，波动来源更多，区间更宽。两者不可互相替代。")


def main() -> None:
    viz.apply_style()
    FIG_OUT.mkdir(parents=True, exist_ok=True)
    PAPER_FIG.mkdir(parents=True, exist_ok=True)

    for fn in (fig5_mde_power, fig8_model_comparison, fig11_guardrail, fig13_bootstrap):
        print(f"[{fn.__name__}]")
        fn()

    cap_json = PAPER_FIG / "_captions.json"
    store: dict[str, str] = json.loads(cap_json.read_text(encoding="utf-8")) if cap_json.exists() else {}
    store.update({n: c for n, c in CAPTIONS})
    cap_json.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    (PAPER_FIG / "_captions.md").write_text(
        "\n\n".join(f"**{n}**\n\n{c}" for n, c in sorted(store.items())) + "\n", encoding="utf-8"
    )
    for png in FIG_OUT.glob("*.png"):
        shutil.copy2(png, PAPER_FIG / png.name)
    print(f"\n本批 {len(CAPTIONS)} 张；累计 {len(store)} 张")


if __name__ == "__main__":
    raise SystemExit(main())
