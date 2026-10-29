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
    ax.set_ylim(lo * 1.20 if lo < 0 else lo, hi * 1.28 if hi > 0 else hi)
    for i, (v, w) in enumerate(zip(sel.mean_diff_cny_per_user, sel.wins)):
        if v > 0:
            ax.text(i, v * 1.06, f"{w:.0f} 胜", ha="center", va="bottom", fontsize=8)
        else:
            ax.text(i, v * 0.55, f"{w:.0f} 胜", ha="center", va="center", fontsize=8,
                    color="white")
    fig.tight_layout()
    path = OUT / "d03_by_model.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (fig_f02_per_rep(), fig_d03_by_model()):
        print(f"WROTE {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
