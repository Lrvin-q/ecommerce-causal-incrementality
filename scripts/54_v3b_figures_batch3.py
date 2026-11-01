"v3b 长稿配图第三批：机制示意、金额链路、预算与求解器、观测闭环与成本校准。"

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from causal_growth import viz

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
FIG_OUT = ROOT / "outputs" / "figures" / "v3b"
PAPER_FIG = ROOT / "paper" / "v3b" / "figures"

CAPTIONS: list[tuple[str, str]] = []
BASE, ACCENT, COOL, MUTED, GREEN = "#2c3e50", "#c0392b", "#2980b9", "#95a5a6", "#27ae60"


def _finish(fig, name: str, note: str, caption: str) -> None:
    # 数据来源统一在附录说明，逐图不再重复（用户要求）
    _ = note
    path = viz.save_fig(fig, name, subdir="v3b")
    CAPTIONS.append((f"{name}.png", caption))
    print(f"  ✓ {path.relative_to(ROOT)}")


def _box(ax, x, y, w, h, title, body="", *, face="#eef3f8", edge=BASE, title_size=10):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                linewidth=1.0, edgecolor=edge, facecolor=face))
    ty = y + h - 0.05 if body else y + h / 2 - 0.01
    ax.text(x + w / 2, ty, title, ha="center", va="top", fontsize=title_size, fontweight="bold", color=edge)
    if body:
        ax.text(x + w / 2, ty - 0.055, body, ha="center", va="top", fontsize=8.0,
                color="#34495e", linespacing=1.5)


def _arrow(ax, p0, p1, color=MUTED):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=12,
                                 linewidth=1.1, color=color, shrinkA=2, shrinkB=2))


# --------------------------------------------------------------------------- #
# 图 2：四层各放松一条假设
# --------------------------------------------------------------------------- #
def fig2_layers() -> None:
    fig, axes = plt.subplots(1, 4, figsize=(14.0, 3.9))
    specs = [
        ("L0", "机制最干净", ["处理分配与结果无关", "效应同质", "成本同质", "单期窗口"],
         "回答：估计量本身是否无偏", "#eaf4fb", COOL),
        ("L1", "真实金额链路", ["+ 购物车→首单→复购", "+ 效应随特征变化", "+ 成本随特征变化", "券只对首单"],
         "回答：异质性能否被辨识", "#eaf4fb", COOL),
        ("L2", "时间与人群", ["+ 分周投放", "+ 效应平滑漂移", "+ 人群构成变化", "+ 结果成熟延迟"],
         "回答：结论的时间稳定性", "#fef5e7", "#b9770e"),
        ("L3", "不可观测混淆", ["+ 不可观测因子 U", "U 经 logit 进入购买概率", "U 影响处理分配", "+ 极端重叠"],
         "回答：失效的定量位置", "#fdecea", ACCENT),
    ]
    for ax, (tag, title, items, answer, face, edge) in zip(axes, specs):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0.02, 0.02), 0.96, 0.96, boxstyle="round,pad=0.01,rounding_size=0.03",
                                    linewidth=1.2, edgecolor=edge, facecolor=face))
        ax.text(0.5, 0.90, tag, ha="center", va="center", fontsize=15, fontweight="bold", color=edge)
        ax.text(0.5, 0.80, title, ha="center", va="center", fontsize=9.5, color=BASE)
        for i, it in enumerate(items):
            ax.text(0.5, 0.66 - i * 0.105, it, ha="center", va="center", fontsize=8.0, color="#2d3436")
        ax.text(0.5, 0.10, answer, ha="center", va="center", fontsize=8.2, color=edge, style="italic")

    for i in range(3):
        _arrow(axes[i], (1.0, 0.5), (1.06, 0.5), color=MUTED)

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.07, 1, 0.93))
    _finish(fig, "fig2_layer_mechanisms",
            "示意图，不含数据；参数取值见附录 A",
            "图 2　四层机制。L0 只是「机制最干净」的基准；L1 引入金额链路与异质性；"
            "L2 引入时间与人群变化；L3 引入不可观测因子及其对分配与结果的双重作用。")


# --------------------------------------------------------------------------- #
# 图 3：金额链路与账务四格
# --------------------------------------------------------------------------- #
def fig3_money_chain() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.3))

    ax = axes[0]
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    steps = [
        (0.02, "购物车", "金额 $V_i$"),
        (0.27, "首单", "金额 $Q_i V_i$，$Q_i\\sim$ 截断正态(0.70, 0.10²)"),
        (0.55, "是否核销", "概率 0.55，核销则扣券 10 元"),
        (0.79, "复购", "以 5% 概率发生，金额为首单 55%"),
    ]
    for x, title, body in steps:
        _box(ax, x, 0.42, 0.19, 0.30, title, body, face="#eaf4fb", edge=COOL, title_size=9.5)
    for x in (0.21, 0.46, 0.74):
        _arrow(ax, (x, 0.57), (x + 0.06, 0.57), color=BASE)
    ax.text(0.5, 0.20, "券只对首单生效：复购不带券，因此复购是「基线收入」而非增量",
            ha="center", va="center", fontsize=8.6, color=ACCENT)
    ax.set_title("(a) 金额链路：券的作用点只有一处")

    ax = axes[1]
    rows = [("收入", "毛额计入", "全额冲减"), ("商品成本", "全额扣除", "按 85% 回收"),
            ("履约成本", "全额扣除", "刚性，不回收"), ("券成本", "核销则扣除", "不退还，保留"),
            ("退款手续费", "不计", "按毛额 1% 加收")]
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.20, 0.92, "未退款订单", ha="center", fontsize=9.5, fontweight="bold", color=BASE)
    ax.text(0.72, 0.92, "退款订单", ha="center", fontsize=9.5, fontweight="bold", color=ACCENT)
    for i, (name, normal, refunded) in enumerate(rows):
        y = 0.80 - i * 0.15
        ax.text(0.02, y, name, ha="left", va="center", fontsize=8.6, color="#2d3436")
        ax.text(0.20, y, normal, ha="center", va="center", fontsize=8.2, color=BASE)
        ax.text(0.72, y, refunded, ha="center", va="center", fontsize=8.2,
                color=ACCENT if "不退还" in refunded or "冲减" in refunded else BASE,
                fontweight=("bold" if ("不退还" in refunded) else "normal"))
    ax.axvline(0.46, color=MUTED, lw=0.8, ls=":")
    ax.set_title("(b) 账务四格：一单退款，收入全冲、券不退")

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.07, 1, 0.93))
    _finish(fig, "fig3_money_chain",
            "示意图，参数取值见附录 A 与附录 B",
            "图 3　金额链路与账务。(a) 券只作用于首单，复购不带券；(b) 退款订单的收入全额冲减、"
            "商品成本按 85% 回收、履约成本不回收、券成本保留，因此一单退款同时损失收入与券。")


# --------------------------------------------------------------------------- #
# 图 9：预算档、价值与超支
# --------------------------------------------------------------------------- #
def fig9_budget() -> None:
    sweep = pd.read_csv(TABLES / "v3_phase_E_budget_sweep.csv")
    cons = pd.read_csv(TABLES / "v3_phase_E_conservative.csv")
    cf = sweep[sweep.frame_model == "causal_forest"]

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.5))

    ax = axes[0]
    g = cf.groupby("per_user_budget_cny").agg(value=("true_value_per_user", "mean"),
                                              eff=("true_value_per_cny_spend", "mean")).reset_index()
    ax.plot(g.per_user_budget_cny, g.value, marker="o", color=BASE, lw=1.9, label="真实价值（元/人）")
    ax.set_xlabel("人均预算（元/人）")
    ax.set_ylabel("真实价值（元/人）")
    ax2 = ax.twinx()
    ax2.plot(g.per_user_budget_cny, g.eff, marker="s", color=ACCENT, lw=1.9, label="每元支出价值")
    ax2.set_ylabel("每元支出的价值")
    ax.set_title("(a) 价值随预算上升，效率随之下降")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")

    ax = axes[1]
    sub = cons[(cons.policy.str.contains("greedy")) & (cons.per_user_budget_cny.isin([0.04, 0.20]))]
    modes = ["expected", "buffered_expected", "worst_case_face"]
    labels = ["期望", "缓冲", "面额上限"]
    width = 0.26
    for i, (mode, lab) in enumerate(zip(modes, labels)):
        vals = [sub[(sub["mode"] == mode) & (sub.per_user_budget_cny == b)].selected_count_mean.mean()
                for b in (0.04, 0.20)]
        ax.bar(np.arange(2) + (i - 1) * width, vals, width=width, label=lab, alpha=0.88,
               color=[BASE, COOL, ACCENT][i])
    ax.set_xticks(np.arange(2))
    ax.set_xticklabels(["0.04 元/人", "0.20 元/人"])
    ax.set_ylabel("入选人数")
    ax.set_title("(b) 面额上限口径以人数换合规")
    ax.legend(fontsize=8)

    ax = axes[2]
    sub2 = cons[(cons.policy.str.contains("greedy")) & (cons.per_user_budget_cny.isin([0.04, 0.20]))]
    for i, (mode, lab) in enumerate(zip(modes, labels)):
        vals = [sub2[(sub2["mode"] == mode) & (sub2.per_user_budget_cny == b)].true_value_per_user_mean.mean()
                for b in (0.04, 0.20)]
        ax.bar(np.arange(2) + (i - 1) * width, vals, width=width, label=lab, alpha=0.88,
               color=[BASE, COOL, ACCENT][i])
    ax.set_xticks(np.arange(2))
    ax.set_xticklabels(["0.04 元/人", "0.20 元/人"])
    ax.set_ylabel("真实价值（元/人）")
    ax.set_title("(c) 合规的代价：价值下降一个量级")
    ax.legend(fontsize=8)

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig9_budget_regimes",
            "预算扫描为单次代表实现；三种口径为 200 个种子；6 万用户测试集",
            "图 9　预算。(a) 真实价值随预算单调上升，每元支出的价值单调下降；"
            "(b) 三种预算口径下的入选人数；(c) 对应的真实价值——面额上限口径用放弃绝大多数投放规模换来不超支。")


# --------------------------------------------------------------------------- #
# 图 10：求解器规模与桶宽
# --------------------------------------------------------------------------- #
def fig10_solvers() -> None:
    scale = pd.read_csv(TABLES / "v3_phase_E_scale.csv")
    bucket = pd.read_csv(TABLES / "v3_phase_E_bucket_convergence.csv")

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.4))

    ax = axes[0]
    if "seconds" in scale.columns:
        for solver, color in zip(sorted(scale.solver.unique())[:4], [BASE, COOL, ACCENT, GREEN]):
            sub = scale[scale.solver == solver].groupby("pool_size").seconds.mean()
            ax.plot(sub.index, sub.values, marker="o", label=solver, color=color, lw=1.7, ms=5)
        ax.set_xlabel("候选池规模")
        ax.set_ylabel("求解时间（秒）")
        ax.legend(fontsize=7.5)
    else:
        ax.axis("off")
        ax.text(0.5, 0.5, "该表无运行时间列", ha="center", va="center", fontsize=9, color=MUTED)
    ax.set_title("(a) 求解时间随规模的变化")

    ax = axes[1]
    for method, color in zip(sorted(bucket.method.unique())[:3], [BASE, COOL, ACCENT]):
        sub = bucket[bucket.method == method].groupby("width_cny").predicted_value_cny.mean()
        ax.plot(sub.index, sub.values, marker="o", label=method, color=color, lw=1.7, ms=5)
    ax.set_xlabel("面额粒度（元）")
    ax.set_ylabel("预测策略价值（元）")
    ax.legend(fontsize=7.5)
    ax.set_title("(b) 桶宽放宽：价值几乎不变")

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig10_solvers",
            "6 万用户测试集；桶宽收敛为同一预算档下的多粒度对照",
            "图 10　求解器。(a) 各求解器的求解时间随候选池规模增长；(b) 面额粒度放宽后策略价值的变化，"
            "说明在该问题上精度不是瓶颈、规模才是。")


# --------------------------------------------------------------------------- #
# 图 12：观测闭环与成本校准
# --------------------------------------------------------------------------- #
def fig12_ope() -> None:
    ope = pd.read_csv(TABLES / "v3_phase_F01_ope_vs_audit.csv")
    deciles = pd.read_csv(TABLES / "v3_phase_E_cost_deciles.csv")

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.4))

    ax = axes[0]
    names = ope.name.unique()[:4]
    for name, color in zip(names, [BASE, COOL, ACCENT, GREEN]):
        sub = ope[ope.name == name].sort_values("per_user_budget_cny")
        ax.plot(sub.per_user_budget_cny, sub.value_error_cny_per_user, marker="o",
                label=str(name)[:16], color=color, lw=1.6, ms=5)
    ax.axhline(0, color=MUTED, ls="--", lw=1.0)
    ax.set_xlabel("人均预算（元/人）")
    ax.set_ylabel("估计值 − 审计值（元/人）")
    ax.set_title("(a) 离策略估计的误差随预算变化")
    ax.legend(fontsize=7)

    ax = axes[1]
    ax.plot(deciles.decile, deciles.mean_predicted_cny, marker="o", color=COOL, label="预测成本")
    ax.plot(deciles.decile, deciles.mean_observed_cny, marker="s", color=ACCENT, label="实际成本")
    ax.set_xlabel("按预测成本十分位")
    ax.set_ylabel("人均成本（元）")
    ax.set_title("(b) 成本校准：两端偏差最大")
    ax.legend(fontsize=8)

    ax = axes[2]
    p = ROOT / "outputs" / "evidence" / "f02_formal" / "aggregate" / "v3_phase_F02_formal_per_rep_spend_full.csv"
    if p.exists():
        d = pd.read_csv(p)
        for arm, color, label in (("random_same_budget", COOL, "同预算随机"), ("targeted", ACCENT, "定向")):
            sub = d[(d.arm == arm) & d.realized_to_predicted.notna()]
            if len(sub):
                ax.hist(sub.realized_to_predicted, bins=30, alpha=0.65, color=color, label=label)
        ax.axvline(1.0, color=MUTED, ls="--", lw=1.2)
        ax.set_xlabel("实际支出 / 预测支出")
        ax.set_ylabel("重复次数")
        ax.set_title("(c) 定向策略系统性低估 5.6%")
        ax.legend(fontsize=8)
    else:
        ax.axis("off")

    pass  # 图题由 LaTeX caption 提供，图内不再重复
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    _finish(fig, "fig12_ope_cost",
            "离策略估计为单次代表实现的 48 个预算档；成本校准为十分位对照；"
            "支出比为 200 次独立随机验证",
            "图 12　观测闭环。(a) 离策略估计相对审计值的误差；(b) 预测成本与实际成本按十分位对照，"
            "两端偏差最大；(c) 200 次独立验证中「实际/预测」支出比的分布，定向臂整体右移。")


def main() -> None:
    viz.apply_style()
    FIG_OUT.mkdir(parents=True, exist_ok=True)
    PAPER_FIG.mkdir(parents=True, exist_ok=True)
    for fn in (fig2_layers, fig3_money_chain, fig9_budget, fig10_solvers, fig12_ope):
        print(f"[{fn.__name__}]")
        fn()
    cap_json = PAPER_FIG / "_captions.json"
    store = json.loads(cap_json.read_text(encoding="utf-8")) if cap_json.exists() else {}
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
