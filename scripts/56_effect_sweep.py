"""效应量级扫描：把购买率增量当作自由变量，重算平均处理效应并求盈亏平衡点。

为什么这样做而不是重跑模拟：期望利润对购买概率是**线性**的（购买事件把每一项都乘上一个概率），
因此固定每用户"每单净利"后，改变 p1 不需要重新生成数据——只需把 p1 换成 p0+Δp 后重算期望。
这让我们可以在几秒钟内扫完 0–8 个百分点，而不是跑几十个小时的重复实验。

输出：
- ``outputs/tables/v3_paper_effect_sweep.csv``：Δp 与对应的 ATE、券成本、净贡献
- ``outputs/figures/v3b/fig15_effect_sweep.png``：盈亏平衡点与设计效应的位置
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth import viz  # noqa: E402
from causal_growth.dgp.v3_engine import audit_conditional_truth, generate_v3_population  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

TABLES = ROOT / "outputs" / "tables"
FIGS = ROOT / "paper" / "v3b" / "figures"


def main() -> int:
    viz.apply_style()
    protocol = load_v3_protocol()
    cfg = protocol.scenario("L1_main")
    n = 40000
    print(f"生成 L1 总体 n={n} …", flush=True)
    pop = generate_v3_population(cfg, 0, n)
    truth = audit_conditional_truth(pop, cfg)

    p0 = truth["purchase_probability_x_0"].to_numpy()
    p1 = truth["purchase_probability_x_1"].to_numpy()
    prof0 = truth["expected_net_profit_0"].to_numpy()
    prof1 = truth["expected_net_profit_1"].to_numpy()
    cost1 = truth["expected_coupon_cost_1"].to_numpy()

    # 每用户"每单净利"（已扣券），用于把 p1 替换成任意值后重算期望
    with np.errstate(divide="ignore", invalid="ignore"):
        per_order1 = np.where(p1 > 1e-12, prof1 / p1, 0.0)
        per_order0 = np.where(p0 > 1e-12, prof0 / p0, 0.0)
        coupon_per_order = np.where(p1 > 1e-12, cost1 / p1, 0.0)

    base = float(np.mean(prof0))
    rows = []
    for dp in np.linspace(0.0, 0.08, 81):
        newp1 = np.clip(p0 + dp, 0.0, 1.0)
        prof1_new = newp1 * per_order1
        ate = float(np.mean(prof1_new)) - base
        coupon = float(np.mean(newp1 * coupon_per_order))
        rows.append({"dp_pp": dp * 100, "ate": ate, "coupon_cost": coupon,
                     "dp_design_pp": 5.0, "n": n})
    df = pd.DataFrame(rows)

    # 盈亏平衡：ATE 穿越 0 的位置（线性插值）
    sign = np.sign(df.ate.to_numpy())
    cross = np.where(np.diff(sign) != 0)[0]
    be = float(np.interp(0.0, df.ate.to_numpy(), df.dp_pp.to_numpy())) if len(cross) else float("nan")
    print(f"  盈亏平衡 Δp* = {be:.3f} pp")
    print(f"  设计效应 5pp 处的 ATE = {float(np.interp(5.0, df.dp_pp, df.ate)):.4f} 元/人")
    print(f"  安全倍数 = {5.0 / be:.2f}x")

    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / "v3_paper_effect_sweep.csv", index=False, encoding="utf-8-sig")

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.4))
    ax = axes[0]
    ax.plot(df.dp_pp, df.ate, color="#2c3e50", lw=2.0)
    ax.axhline(0, color="#95a5a6", ls="--", lw=1.0)
    ax.axvline(be, color="#c0392b", ls=":", lw=1.4)
    ax.axvline(5.0, color="#2980b9", ls=":", lw=1.4)
    ax.annotate(f"盈亏平衡 {be:.2f}pp", (be, 0), textcoords="offset points", xytext=(6, 14),
                fontsize=8.5, color="#c0392b")
    ax.annotate("设计效应 5pp", (5.0, 0), textcoords="offset points", xytext=(6, -18),
                fontsize=8.5, color="#2980b9")
    ax.set_xlabel("购买率增量 Δp（百分点）")
    ax.set_ylabel("人均净增量利润（元/人）")
    ax.set_title("(a) 效应量级与利润：穿越零点")

    ax = axes[1]
    ax.plot(df.dp_pp, df.coupon_cost, color="#c0392b", lw=1.8, label="券成本（元/人）")
    ax.set_xlabel("购买率增量 Δp（百分点）")
    ax.set_ylabel("券成本（元/人）")
    ax.set_title("(b) 成本随效应上升：盈亏平衡不是比值")
    ax.legend(fontsize=8)

    fig.suptitle("图 15　效应量级扫描：5 个百分点的设计效应离盈亏平衡有多远", fontsize=12)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    viz.add_source_note(fig, f"L1 主实验；解析重算（期望利润对购买概率线性），n={n}；不重新抽样")
    path = viz.save_fig(fig, "fig15_effect_sweep", subdir="v3b")
    FIGS.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(path, FIGS / path.name)
    print(f"  图已写出: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
