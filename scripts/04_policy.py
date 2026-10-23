"""第三轮：预算约束下的策略学习与六策略对比。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\04_policy.py

本轮的三个核心问题
------------------
1. **定向到底值多少钱？** 六策略在同一测试集、同一预算下对比，报**增量口径**价值。
2. **贪心离最优有多远？** LP 松弛上界量化全规模下的近似程度；
   降规模实例上用精确 DP 测真实整数间隙。
3. **预算松紧怎么改变结论？** 预算敏感性扫描，看"哪种策略最优"是否随 B 变。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt

from causal_growth import dgp
from causal_growth.config import load_config
from causal_growth.data.split import train_val_test_split
from causal_growth.estimate.cate import design_matrix, estimate_cate
from causal_growth.io_utils import save_table
from causal_growth.policy.cost import compute_expected_cost, fit_redemption_model
from causal_growth.policy.selection import (
    SelectionResult,
    evaluate_policy,
    greedy_by_ratio,
    incremental_value,
    knapsack_dp,
    local_improvement,
    lp_upper_bound,
    random_under_budget,
)
from causal_growth.rng import child_rng
from causal_growth.viz import STRATEGY_COLORS, STRATEGY_LABELS, add_source_note, save_fig


def _seed(cfg) -> int:
    return int(cfg.require("project.master_seed"))


def _mk(name: str, policy: np.ndarray, cost: np.ndarray, budget: float) -> SelectionResult:
    return SelectionResult(name=name, policy=policy, cost_total=float(cost[policy].sum()),
                           budget=budget)


# --------------------------------------------------------------------------- #
# 主实验
# --------------------------------------------------------------------------- #
def build_setup(cfg):
    """构造测试集、CATE 估计、成本估计与预算。"""
    pop = dgp.assign_random(cfg, dgp.build("L1", cfg, 0))
    split = train_val_test_split(
        len(pop),
        test_size=float(cfg.require("evaluation.test_size")),
        val_size=float(cfg.require("evaluation.val_size")),
        master_seed=_seed(cfg),
        index=0,
    )
    X = design_matrix(pop)
    t = pop.treatment.astype(int)
    y_obs, pi_obs = pop.potential.observed(t)

    print("      拟合 CATE（Causal Forest）...")
    fit = estimate_cate(pop, cfg, split, outcome="net_profit", method="causal_forest")
    tau_hat_test = fit.tau_test

    print("      拟合核销模型（仅训练集处理组）...")
    train_mask = np.zeros(len(pop), dtype=bool)
    train_mask[split.train] = True
    # 核销 = 发了券 **且** 有订单 **且** 真的用了券。
    # 三个条件缺一不可；少一个就会把"没下单的人"算成"用了券"。
    coupon_used = (t == 1) & (y_obs == 1) & pop.latent["redeemed"]
    p_redeem = fit_redemption_model(
        X, coupon_used, t, fit_mask=train_mask, cfg=cfg
    )

    face = float(pop.truth.face_value)
    cost_model = compute_expected_cost(p_redeem, face_value=face, cfg=cfg)

    test = split.test
    cost_test = cost_model.cost()[test]
    coverage = float(cfg.require("budget.coverage_target"))
    budget = coverage * float(cost_test.sum())

    return {
        "pop": pop, "split": split, "X": X, "test": test,
        "tau_hat": tau_hat_test,
        "tau_true": pop.truth.cate_profit[test],
        "pi1": pop.potential.pi1[test],
        "pi0": pop.potential.pi0[test],
        "cost": cost_test,
        "budget": budget,
        "cost_model": cost_model,
        "cate_fit": fit,
    }


def run_six_strategies(cfg, s) -> pd.DataFrame:
    """六策略对比（同一测试集、同一预算、增量口径价值）。"""
    cost, budget = s["cost"], s["budget"]
    tau_hat, tau_true = s["tau_hat"], s["tau_true"]
    pi1, pi0 = s["pi1"], s["pi0"]
    n = cost.size

    rng = child_rng(_seed(cfg), "policy.random", 0)
    strategies: dict[str, SelectionResult] = {}

    strategies["no_coupon"] = _mk("no_coupon", np.zeros(n, dtype=bool), cost, budget)
    strategies["all"] = _mk("all", np.ones(n, dtype=bool), cost, budget)
    strategies["random"] = random_under_budget(cost, budget, rng)

    g = greedy_by_ratio(tau_hat, cost, budget)
    strategies["target_greedy"] = _mk("target_greedy", g.policy, cost, budget)

    # 全规模精确 DP 不可行（见报告 §4），用 1-2 交换局部搜索作为实用最优基准
    ls = local_improvement(tau_hat, cost, budget, g.policy)
    strategies["target_knapsack"] = _mk("target_knapsack", ls.policy, cost, budget)

    # 真值最优：用**真值 τ 与真值成本**排序 + 局部搜索 —— 这是可达上界
    g_or = greedy_by_ratio(tau_true, cost, budget)
    orc = local_improvement(tau_true, cost, budget, g_or.policy)
    strategies["oracle"] = _mk("oracle", orc.policy, cost, budget)

    oracle_value = incremental_value(strategies["oracle"].policy, pi1, pi0)

    rows = []
    for key, res in strategies.items():
        row = evaluate_policy(res, tau_true=tau_true, pi1=pi1, pi0=pi0, oracle_value=oracle_value)
        row["strategy_key"] = key
        row["strategy"] = STRATEGY_LABELS[key]
        row["n_test"] = n
        row["oracle_value"] = oracle_value
        rows.append(row)
    df = pd.DataFrame(rows)
    # 全量策略天然超预算，报告里必须显式标出来
    df["over_budget"] = df["cost_total"] > budget * 1.0000001
    # 超预算策略的价值**不能**与预算约束下的策略比"达上界百分比"——
    # 它花了 5 倍的钱，拿到的价值当然更高，算百分比只会误导读者。
    df.loc[df["over_budget"], ["pct_of_oracle", "regret"]] = np.nan
    df["note"] = np.where(
        df["over_budget"], "无视预算（成本超支），价值不可与预算约束下的策略比较", ""
    )
    save_table(df, "r3_six_strategies")
    return df


def run_greedy_gap(cfg, s) -> pd.DataFrame:
    """量化贪心的近似程度：LP 上界 + 降规模实例上的精确 DP。"""
    cost, budget = s["cost"], s["budget"]
    tau_hat = s["tau_hat"]
    n = cost.size

    g = greedy_by_ratio(tau_hat, cost, budget)
    ls = local_improvement(tau_hat, cost, budget, g.policy)
    ub = lp_upper_bound(tau_hat, cost, budget)["upper_bound"]
    v_g = float(tau_hat[g.policy].sum())
    v_ls = float(tau_hat[ls.policy].sum())

    rows = [
        {
            "项": "全规模（n=%d）" % n,
            "贪心估计价值": v_g,
            "局部改进估计价值": v_ls,
            "LP松弛上界": ub,
            "贪心/上界": v_g / ub if ub > 0 else np.nan,
            "局部改进/上界": v_ls / ub if ub > 0 else np.nan,
            "精确DP": np.nan,
            "说明": "LP 上界是松弛，不是最优解；比值越接近 1 说明贪心越好",
        }
    ]

    # 降规模实例：取比值最高的 1,000 人，预算按同样覆盖率缩放
    order = np.argsort(-(tau_hat / np.maximum(cost, 1e-12)))
    idx = order[:1000]
    sub_cost = cost[idx]
    sub_budget = float(np.mean(budget / cost.sum()) * sub_cost.sum())
    v_sub, c_sub = tau_hat[idx], sub_cost
    g_sub = greedy_by_ratio(v_sub, c_sub, sub_budget)
    ub_sub = lp_upper_bound(v_sub, c_sub, sub_budget)["upper_bound"]
    dp_sub = knapsack_dp(v_sub, c_sub, sub_budget, max_capacity_units=8000)
    v_g_sub = float(v_sub[g_sub.policy].sum())
    v_dp_sub = float(v_sub[dp_sub.policy].sum())
    rows.append(
        {
            "项": "降规模（n=1000）",
            "贪心估计价值": v_g_sub,
            "局部改进估计价值": v_g_sub,
            "LP松弛上界": ub_sub,
            "贪心/上界": v_g_sub / ub_sub if ub_sub > 0 else np.nan,
            "局部改进/上界": v_g_sub / ub_sub if ub_sub > 0 else np.nan,
            "精确DP": v_dp_sub,
            "说明": (f"精确 DP（unit={dp_sub.unit:.5f} 元，容量 {dp_sub.diagnostics['capacity_units']} 格）；"
                     f"DP/贪心 = {v_dp_sub / v_g_sub:.6f}" if v_g_sub > 0 else ""),
        }
    )

    # 方案给的反例：小规模下贪心会大幅失败
    v_ce = np.array([12.0, 9.0, 9.0])
    c_ce = np.array([6.0, 5.0, 5.0])
    g_ce = greedy_by_ratio(v_ce, c_ce, 10.0)
    dp_ce = knapsack_dp(v_ce, c_ce, 10.0)
    rows.append(
        {
            "项": "方案反例（3 件）",
            "贪心估计价值": float(v_ce[g_ce.policy].sum()),
            "局部改进估计价值": np.nan,
            "LP松弛上界": 19.2,
            "贪心/上界": float(v_ce[g_ce.policy].sum()) / 19.2,
            "局部改进/上界": np.nan,
            "精确DP": float(v_ce[dp_ce.policy].sum()),
            "说明": "预算10：A=6/12、B=5/9、C=5/9。贪心选 A 得 12，最优选 B+C 得 18",
        }
    )
    out = pd.DataFrame(rows)
    save_table(out, "r3_greedy_gap")
    return out


# --------------------------------------------------------------------------- #
# 预算敏感性
# --------------------------------------------------------------------------- #
def run_budget_scan(cfg, s) -> pd.DataFrame:
    """预算从 5% 覆盖扫到 60%，看哪种策略最优是否稳定。"""
    scan = cfg.section("budget.scan")
    ratios = np.linspace(float(scan["min_ratio"]), float(scan["max_ratio"]), int(scan["n_points"]))
    cost, tau_hat, tau_true = s["cost"], s["tau_hat"], s["tau_true"]
    pi1, pi0 = s["pi1"], s["pi0"]
    base_budget = s["budget"]
    rng = child_rng(_seed(cfg), "policy.scan", 0)

    rows = []
    for r in ratios:
        b = base_budget * float(r)
        g = greedy_by_ratio(tau_hat, cost, b)
        orc = local_improvement(tau_true, cost, b, greedy_by_ratio(tau_true, cost, b).policy)
        rnd = random_under_budget(cost, b, rng)
        rows.append(
            {
                "预算倍数": float(r),
                "预算_元": b,
                "覆盖率_贪心": float(g.policy.mean()),
                "价值_贪心": incremental_value(g.policy, pi1, pi0),
                "价值_随机": incremental_value(rnd.policy, pi1, pi0),
                "价值_真值最优": incremental_value(orc.policy, pi1, pi0),
                "定向增益_相对随机": (
                    incremental_value(g.policy, pi1, pi0) - incremental_value(rnd.policy, pi1, pi0)
                ),
            }
        )
    out = pd.DataFrame(rows)
    out["贪心达上界比"] = out["价值_贪心"] / out["价值_真值最优"].replace(0, np.nan)
    out["定向相对优势倍数"] = out["价值_贪心"] / out["价值_随机"].replace(0, np.nan)
    save_table(out, "r3_budget_scan")
    return out


# --------------------------------------------------------------------------- #
# 业务合理性扫描（方案 Step 8）
# --------------------------------------------------------------------------- #
def run_robustness(cfg) -> pd.DataFrame:
    """对四个业务参数各做 ±20% 扰动，看**主结论方向**是否稳定。

    主结论是三条：
    A. 定向-贪心的价值显著高于随机（绝对增益 > 0）；
    B. 定向达真值最优上界的比例约 85%；
    C. 每元预算的净增量利润 > 1（即发券赚钱）。

    为控制计算量，这里用 **S-learner** 做 CATE（主结果用 Causal Forest）——
    两个方法在第二轮已证明方向一致（S-learner R²=0.18、CF R²=0.33，都不改变"新客效应更高"）。
    **报告里必须注明这个替换**，不能让人以为稳健性扫描用的是同一个模型。
    """
    # 每个扰动必须打到 **DGP 真正读取的旋钮** 上，否则扫描是空转。
    # 踩过的坑：`business.baseline_conversion` 只用于样本量公式，DGP 读的是
    # `dgp.l1.p0.target_mean`；而面额效应 `g(f)/g(f_ref)` 在 f = f_ref 处恒等于 1，
    # 所以必须显式传 `face_value` 才能让面额扰动生效。
    ref_face = float(cfg.require("business.coupon_reference_face"))
    scenarios: list[tuple[str, float, dict[str, float], float]] = []
    p0_target = float(cfg.require("dgp.l1.p0.target_mean"))
    redeem = float(cfg.require("business.redemption_rate"))
    refund = float(cfg.require("business.refund_rate"))
    for mult in (0.8, 1.0, 1.2):
        scenarios.append(("基线转化率", mult, {"dgp.l1.p0.target_mean": p0_target * mult}, 1.0))
    for mult in (0.8, 1.0, 1.2):
        scenarios.append(("券核销率", mult, {"business.redemption_rate": redeem * mult}, 1.0))
    for mult in (0.8, 1.0, 1.2):
        scenarios.append(("退款率", mult, {"business.refund_rate": refund * mult}, 1.0))
    for mult in (0.8, 1.0, 1.2):
        scenarios.append(("券面额", mult, {}, mult))

    rows: list[dict] = []
    for label, mult, overrides, face_mult in scenarios:
        variant = cfg.with_overrides(overrides) if overrides else cfg
        face = ref_face * face_mult
        pop = dgp.assign_random(variant, dgp.build("L1", variant, 0, face_value=face))
        sp = train_val_test_split(
            len(pop),
            test_size=float(variant.require("evaluation.test_size")),
            val_size=float(variant.require("evaluation.val_size")),
            master_seed=_seed(variant),
            index=0,
        )
        fit = estimate_cate(pop, variant, sp, outcome="net_profit", method="s_learner")
        X = design_matrix(pop)
        t = pop.treatment.astype(int)
        y_obs, _ = pop.potential.observed(t)
        mask = np.zeros(len(pop), dtype=bool)
        mask[sp.train] = True
        p_red = fit_redemption_model(
            X, (t == 1) & (y_obs == 1) & pop.latent["redeemed"], t,
            fit_mask=mask, cfg=variant,
        )
        cm = compute_expected_cost(p_red, face_value=float(pop.truth.face_value), cfg=variant)
        cost = cm.cost()[sp.test]
        budget = float(variant.require("budget.coverage_target")) * float(cost.sum())
        pi1 = pop.potential.pi1[sp.test]
        pi0 = pop.potential.pi0[sp.test]
        tau_true = pop.truth.cate_profit[sp.test]

        g = greedy_by_ratio(fit.tau_test, cost, budget)
        r = random_under_budget(cost, budget, child_rng(_seed(variant), "robust.rand", 0))
        orc = local_improvement(
            tau_true, cost, budget, greedy_by_ratio(tau_true, cost, budget).policy
        )
        v_g = incremental_value(g.policy, pi1, pi0)
        v_r = incremental_value(r.policy, pi1, pi0)
        v_o = incremental_value(orc.policy, pi1, pi0)
        rows.append(
            {
                "参数": label,
                "扰动": f"×{mult:.1f}",
                "券面额": face,
                "定向价值": v_g,
                "随机价值": v_r,
                "真值最优": v_o,
                "定向减随机": v_g - v_r,
                "达上界比": v_g / v_o if v_o > 0 else np.nan,
                "每元预算回报": (v_g * len(cost)) / g.cost_total if g.cost_total > 0 else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    save_table(out, "r3_robustness")
    return out


# --------------------------------------------------------------------------- #
# 图
# --------------------------------------------------------------------------- #
def plot_six(df: pd.DataFrame, cfg) -> None:
    d = df[df["strategy_key"] != "oracle"].copy()
    order = ["no_coupon", "random", "target_greedy", "target_knapsack", "all"]
    d["k"] = d["strategy_key"]
    d = d.set_index("k").loc[[k for k in order if k in d["k"].values]]

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.2))
    x = np.arange(len(d))
    colors = [STRATEGY_COLORS[k] for k in d.index]

    axes[0].bar(x, d["incremental_value"], color=colors)
    oracle_val = float(df.loc[df["strategy_key"] == "oracle", "oracle_value"].iloc[0])
    axes[0].axhline(oracle_val, color="black", ls="--", lw=1.2,
                    label=f"真值最优上界 {oracle_val:.3f}")
    axes[0].set_xticks(x, [STRATEGY_LABELS[k] for k in d.index], rotation=18, ha="right")
    axes[0].set_ylabel("增量策略价值（元/人）")
    axes[0].set_title("六策略价值对比（同一测试集、同一预算）")
    axes[0].legend(fontsize=8)
    for i, v in enumerate(d["incremental_value"]):
        axes[0].text(i, v + oracle_val * 0.02, f"{v:.3f}", ha="center", fontsize=8)

    axes[1].bar(x, d["budget_utilization"] * 100, color=colors)
    axes[1].axhline(100, color="red", ls="--", lw=1, label="预算 100%")
    axes[1].set_xticks(x, [STRATEGY_LABELS[k] for k in d.index], rotation=18, ha="right")
    axes[1].set_ylabel("预算使用率（%）")
    axes[1].set_title("预算使用率：全量发券必然超预算")
    axes[1].legend(fontsize=8)

    add_source_note(fig, f"seed={_seed(cfg)} | L1 测试集 n={int(d['n_test'].iloc[0]):,} | 增量口径 V(π)=E[π·τ]")
    save_fig(fig, "r3_six_strategies")


def plot_budget_scan(scan: pd.DataFrame, cfg) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(scan["预算倍数"], scan["价值_真值最优"], "o-", color="#212121", label="真值最优")
    axes[0].plot(scan["预算倍数"], scan["价值_贪心"], "s-", color=STRATEGY_COLORS["target_greedy"], label="定向-贪心")
    axes[0].plot(scan["预算倍数"], scan["价值_随机"], "^-", color=STRATEGY_COLORS["random"], label="随机")
    axes[0].set_xlabel("预算倍数（相对基准）")
    axes[0].set_ylabel("增量策略价值（元/人）")
    axes[0].set_title("策略价值随预算放宽而上升")
    axes[0].legend(fontsize=8)

    axes[1].plot(scan["预算倍数"], scan["定向增益_相对随机"], "o-", color="#6A1B9A",
                 label="绝对增益")
    axes[1].axhline(0, color="grey", ls="--", lw=1)
    axes[1].set_xlabel("预算倍数（相对基准）")
    axes[1].set_ylabel("定向相对随机的增益（元/人）")
    axes[1].set_title("定向的绝对增益在中等预算处最大，\n但紧预算时定向的相对优势最强")
    ax2 = axes[1].twinx()
    ax2.plot(scan["预算倍数"], scan["定向相对优势倍数"], "s--", color="#FB8C00",
             alpha=0.7, label="相对优势（倍）")
    ax2.set_ylabel("定向价值 / 随机价值（倍）")
    h1, l1 = axes[1].get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    axes[1].legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right")
    add_source_note(fig, f"seed={_seed(cfg)} | L1 测试集 | 增量口径")
    save_fig(fig, "r3_budget_scan")


# --------------------------------------------------------------------------- #
def main() -> int:
    cfg = load_config()
    print(f"[config] seed={_seed(cfg)}  {cfg.require('project.data_source_label')}")

    print("[1/5] 构造测试集与估计量 ...")
    s = build_setup(cfg)
    cm = s["cost_model"].summary()
    print(f"      测试集 n={s['cost'].size:,}  预算 B={s['budget']:,.1f} 元 "
          f"（覆盖目标 {cfg.require('budget.coverage_target'):.0%}）")
    print(f"      成本模型：口径={cm['basis']} 面额={cm['face_value']:.0f} 元 "
          f"均值={cm['mean_cost']:.4f} 元 90分位={cm['p90_cost']:.4f} 元")

    print("[2/5] 六策略对比 ...")
    six = run_six_strategies(cfg, s)
    for _, row in six.iterrows():
        flag = " (超预算!)" if row["over_budget"] else ""
        print(f"      {row['strategy']:<14} 选中 {int(row['n_selected']):>6,} 人  "
              f"成本 {row['cost_total']:>9,.0f} 元  价值 {row['incremental_value']:+.4f} 元/人  "
              f"达上界 {row['pct_of_oracle']:5.1f}%{flag}")

    print("[3/5] 贪心近似程度 ...")
    gap = run_greedy_gap(cfg, s)
    for _, row in gap.iterrows():
        dp = row["精确DP"]
        print(f"      {row['项']:<18} 贪心/上界={row['贪心/上界']:.6f}  "
              f"DP={dp if isinstance(dp,str) else f'{dp:.4f}'}")

    print("[4/5] 预算敏感性扫描 ...")
    scan = run_budget_scan(cfg, s)
    for _, row in scan.iterrows():
        print(f"      B×{row['预算倍数']:.2f}: 贪心 {row['价值_贪心']:+.4f}  "
              f"随机 {row['价值_随机']:+.4f}  上界 {row['价值_真值最优']:+.4f}  "
              f"定向增益 {row['定向增益_相对随机']:+.4f}")

    print("[5/6] 出图 ...")
    plot_six(six, cfg)
    plot_budget_scan(scan, cfg)

    print("[6/6] 业务合理性扫描（四参数 ±20%）...")
    rob = run_robustness(cfg)
    for _, row in rob.iterrows():
        print(f"      {row['参数']:<10} {row['扰动']}: 定向减随机 {row['定向减随机']:+.4f}  "
              f"达上界 {row['达上界比']:.1%}  每元回报 {row['每元预算回报']:.3f}")
    stable = bool((rob["定向减随机"] > 0).all()) and bool((rob["每元预算回报"] > 1).all())
    print(f"      结论方向稳定性：{'稳定（12/12 单元均满足 定向>随机 且 每元回报>1）' if stable else '**不稳定，需在报告中标注**'}")

    print("\n[done] 产物已落盘 outputs/tables/r3_*.csv 与 outputs/figures/r3_*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
