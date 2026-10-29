"""生成正文插图：F02 逐重复净利差分布、D03 按模型配对的策略差。

数据来源均为已冻结的正式产物（F02 200 rep、D03 200 rep），不重新抽样、不重算口径。
输出：paper/v3/figures/*.png（150 dpi），供 paper/v3/body/03_results.md 引用。
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "v3" / "figures"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False


def fig_f02_per_rep() -> Path:
    src = ROOT / "outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_claims.csv"
    df = pd.read_csv(src)
    d = df[df["claim"] == "coupon_worth_issuing"]["diff_cny_per_user"]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.hist(d, bins=28, color="#4c72b0", edgecolor="white", linewidth=0.6)
    ax.axvline(0.0, color="black", linewidth=1.0)
    ax.axvline(d.mean(), color="#c44e52", linewidth=1.2, linestyle="--")
    ax.set_xlabel("定向策略 − 不发券的净利差（元/人）")
    ax.set_ylabel("重复数（个）")
    ax.set_title(f"{len(d)} 个重复中 {int((d > 0).sum())} 个净利差为正；均值 {d.mean():.4f} 元/人")
    ax.text(0.02, 0.95, f"n = {len(d)} 个重复\n红线：均值\n黑线：零", transform=ax.transAxes,
            va="top", fontsize=8)
    fig.tight_layout()
    path = OUT / "f02_per_rep_diff.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def fig_d03_by_model() -> Path:
    src = ROOT / "outputs/tables/v3_phase_D03_formal_paired_diff.csv"
    df = pd.read_csv(src)
    sel = df[(df.per_user_budget_cny == 0.2)
             & (df.policy == "greedy_incremental_profit_per_cost")
             & (df.baseline == "business_rule_new_user_then_cart")]
    order = ["causal_forest", "s_learner", "dr_learner", "t_learner", "constant"]
    sel = sel.set_index("model").loc[order]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    colors = ["#c44e52" if v > 0 else "#4c72b0" for v in sel.mean_diff_cny_per_user]
    ax.bar(range(len(sel)), sel.mean_diff_cny_per_user, yerr=sel.se_diff,
           color=colors, capsize=3, edgecolor="white")
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.set_xticks(range(len(sel)))
    ax.set_xticklabels(["因果森林", "S-learner", "DR-learner", "T-learner", "常数策略"])
    ax.set_ylabel("贪心 − 业务规则的净利差（元/人）")
    ax.set_title("同一贪心策略：按模型配对后符号相反（0.2 元/人，200 对）")
    lo, hi = sel.mean_diff_cny_per_user.min(), sel.mean_diff_cny_per_user.max()
    pad = 0.10 * (hi - lo)
    ax.set_ylim(min(lo * 1.20, lo - pad), hi + pad)
    for i, (v, w) in enumerate(zip(sel.mean_diff_cny_per_user, sel.wins)):
        if v > 0:
            ax.annotate(f"{w:.0f} 胜", (i, v), textcoords="offset points",
                        xytext=(0, 4), ha="center", va="bottom", fontsize=8)
        else:
            ax.text(i, v * 0.55, f"{w:.0f} 胜", ha="center", va="center", fontsize=8,
                    color="white")
    fig.tight_layout()
    path = OUT / "d03_by_model.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def fig_cost_calibration() -> Path:
    src = ROOT / "outputs/evidence/e_evidence_rep0_a/calibration_validation_treated_constant.csv"
    df = pd.read_csv(src)
    df["decile"] = pd.qcut(df["predicted_cost_cny"], 10, labels=False) + 1
    rows = []
    for decile, block in df.groupby("decile"):
        obs = block["observed_coupon_cost_cny"]
        rows.append({
            "decile": int(decile),
            "n": int(len(block)),
            "mean_predicted_cny": float(block["predicted_cost_cny"].mean()),
            "mean_observed_cny": float(obs.mean()),
            "se_observed_cny": float(obs.std(ddof=1) / (len(block) ** 0.5)),
        })
    table = pd.DataFrame(rows)
    table_path = ROOT / "outputs/tables/v3_phase_E_cost_deciles.csv"
    table.to_csv(table_path, index=False, encoding="utf-8-sig", lineterminator="\r\n")

    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    ax.errorbar(table.mean_predicted_cny, table.mean_observed_cny,
                yerr=1.96 * table.se_observed_cny, fmt="o", color="#4c72b0",
                ecolor="#9aa7c7", capsize=3, markersize=5,
                label="预测十分位：均值 ± 95% CI")
    lo = min(table.mean_predicted_cny.min(), table.mean_observed_cny.min()) - 0.05
    hi = max(table.mean_predicted_cny.max(), table.mean_observed_cny.max()) + 0.05
    ax.plot([lo, hi], [lo, hi], color="black", linewidth=1.0, linestyle="--",
            label="y = x（完美校准）")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("预测期望券成本（元/人，十分位均值）")
    ax.set_ylabel("观测券成本（元/人，同组均值）")
    ax.set_title("成本预测的十分位校准：均值贴合，斜率偏平")
    ax.legend(fontsize=8, loc="upper left")
    ax.text(0.98, 0.03, "源：E 层 rep0 验证期处理组 19 987 人\n点越接近对角线，排序越准",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7)
    fig.tight_layout()
    path = OUT / "e_cost_calibration.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def fig_refund_sweep() -> Path:
    src = ROOT / "outputs/tables/v3_phase_F01_refund_sweep.csv"
    df = pd.read_csv(src)
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    styles = {
        "greedy": ("定向贪心", "#c44e52", "o"),
        "random": ("同预算随机", "#4c72b0", "s"),
    }
    for contrast, (label, color, marker) in styles.items():
        block = df[df["contrast"] == contrast].sort_values("per_user_budget_cny")
        ax.errorbar(block.per_user_budget_cny, block.diff_pp,
                    yerr=1.96 * block.se_diff_pp, fmt=marker + "-", color=color,
                    capsize=3, markersize=4, linewidth=1.2, label=label)
    ax.axhline(0.5, color="black", linewidth=1.2, linestyle="--")
    hi = (df.diff_pp + 1.96 * df.se_diff_pp).max()
    ax.set_ylim(top=max(hi, 0.55) + 0.06)
    ax.text(df.per_user_budget_cny.max(), max(hi, 0.55) + 0.02, "非劣效界值 0.5 pp",
            ha="right", va="bottom", fontsize=8)
    ax.axhline(0.0, color="grey", linewidth=0.8)
    ax.set_xlabel("计划预算（元/人）")
    ax.set_ylabel("退款事件率差：发券臂 − 不发券（百分点）")
    ax.set_title("退款率差随预算上升：0.6 档以后误差线上沿逼近界值")
    ax.legend(fontsize=8, loc="upper left")
    ax.text(0.98, 0.03, "误差线：±1.96 SE；单帧 R=0，不与 200 rep 护栏并列",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7)
    fig.tight_layout()
    path = OUT / "f01_refund_sweep.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (fig_f02_per_rep(), fig_d03_by_model(), fig_cost_calibration(),
              fig_refund_sweep()):
        print(f"WROTE {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
