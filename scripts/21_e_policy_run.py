"""E 阶段策略编排：9 个候选策略 × 8 个预算点。

为什么单独成脚本
----------------
``v3_policy`` 只提供**组件**（成本模型、5 个求解器、预算三口径、误差分解、排序）。
"把 9 个策略在 8 个预算下各跑一遍并评估"属于编排层，需要真实预测与真值，
不应该塞进接口模块，否则接口模块会被数据路径绑死。

输入契约（CSV，``utf-8-sig``，列名固定）
----------------------------------------
``user_id, is_new, cart_value, purchase_propensity, predicted_profit,
tau_hat, cost_hat, tau_true, cost_true``

- **选人只用** ``tau_hat`` / ``cost_hat`` / ``purchase_propensity`` / ``predicted_profit``；
- **评估只用** ``tau_true``（未触及真值的策略才是"盲"的）；
- 预算合规同时报两件事：按 ``cost_hat`` 是否超预算、按 ``cost_true`` 实际支出了多少。

``--synthetic`` 时按已知 DGP 生成，用于在没有 D 阶段导出表时验证编排链路。
生成的数据**不能**用来下策略结论——它只证明代码能跑通。

用法
----
    $env:PYTHONUTF8='1'
    .\\venv\\Scripts\\python.exe scripts\\21_e_policy_run.py --synthetic --synthetic-n 50000 --out out/e_smoke
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.config import Config  # noqa: E402
from causal_growth.policy import v3_policy as pol  # noqa: E402
from causal_growth.rng import child_rng  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

POLICIES = (
    "no_coupon",
    "all_coupon_unconstrained_reference",
    "random_same_budget",
    "business_rule_new_user_then_cart",
    "purchase_propensity_rank",
    "predicted_profit_rank",
    "incremental_profit_rank",
    "greedy_incremental_profit_per_cost",
    "greedy_local_swap",
)

REQUIRED_COLUMNS = (
    "user_id", "is_new", "cart_value", "purchase_propensity", "predicted_profit",
    "tau_hat", "cost_hat", "tau_true", "cost_true",
)


def _synthetic(n: int, cfg: Config) -> pd.DataFrame:
    """已知 DGP 的合成表；只用于打通链路，不用于结论。"""
    rng = child_rng(int(cfg.require("project.master_seed")), "e.synthetic", 0)
    propensity = rng.beta(2.0, 5.0, size=n)
    is_new = (rng.random(n) < 0.35).astype(np.int64)
    cart_value = np.round(rng.lognormal(3.8, 0.7, size=n), 2)
    # 真值增量：新客与高意向更敏感，加上异质项
    tau_true = 0.35 * is_new + 0.9 * propensity + 0.02 * np.log1p(cart_value) + rng.normal(0, 0.15, n)
    face = float(cfg.require("policy.face_value_cny"))
    p_redeem = np.clip(0.25 + 0.55 * propensity, 0.02, 0.95)
    cost_true = face * (rng.random(n) < p_redeem)
    # 预测：τ̂ 带噪声；ĉ 是期望核销成本（不是面额）
    tau_hat = tau_true + rng.normal(0, 0.35, n)
    cost_hat = np.maximum(face * propensity ** 0.5 * 0.8, float(cfg.require("policy.cost_model.cost_floor_cny")))
    return pd.DataFrame({
        "user_id": np.arange(n, dtype=np.int64),
        "is_new": is_new,
        "cart_value": cart_value,
        "purchase_propensity": propensity,
        "predicted_profit": propensity * np.maximum(cart_value * 0.08, 0.0),
        "tau_hat": tau_hat,
        "cost_hat": cost_hat,
        "tau_true": tau_true,
        "cost_true": cost_true,
    })


def _load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"输入缺列：{missing}")
    return frame


def _business_rule(frame: pd.DataFrame, budget: float) -> pol.Selection:
    """business_rule：新客优先、购物车金额次之、user_id 兜底。"""
    order = np.lexsort((
        frame["user_id"].to_numpy(),
        -frame["cart_value"].to_numpy(),
        -frame["is_new"].to_numpy(),
    ))
    cost = frame["cost_hat"].to_numpy(dtype=float)
    mask = np.zeros(len(frame), dtype=bool)
    spent = 0.0
    for index in order:
        if spent + cost[index] <= budget + pol.BUDGET_TOLERANCE:
            mask[index] = True
            spent += cost[index]
    return pol.Selection(
        mask=mask,
        predicted_value=float(frame["tau_hat"].to_numpy()[mask].sum()),
        predicted_cost=spent,
        algorithm="business_rule_new_user_then_cart",
    )


def run_policy(name: str, frame: pd.DataFrame, budget: float, rng: np.random.Generator) -> pol.Selection:
    """把 9 个策略分派到各自的实现。"""
    tau_hat = frame["tau_hat"].to_numpy(dtype=float)
    cost_hat = frame["cost_hat"].to_numpy(dtype=float)
    user_id = frame["user_id"].to_numpy()

    if name == "no_coupon":
        mask = np.zeros(len(frame), dtype=bool)
        return pol.Selection(mask=mask, predicted_value=0.0, predicted_cost=0.0, algorithm=name)
    if name == "all_coupon_unconstrained_reference":
        mask = np.ones(len(frame), dtype=bool)
        return pol.Selection(mask=mask, predicted_value=float(tau_hat.sum()),
                             predicted_cost=float(cost_hat.sum()), algorithm=name)
    if name == "random_same_budget":
        return pol.random_under_budget(tau_hat, cost_hat, budget, rng)
    if name == "business_rule_new_user_then_cart":
        return _business_rule(frame, budget)
    if name == "purchase_propensity_rank":
        return pol.rank_and_select(frame["purchase_propensity"].to_numpy(float), cost_hat,
                                   budget, user_id, name)
    if name == "predicted_profit_rank":
        return pol.rank_and_select(frame["predicted_profit"].to_numpy(float), cost_hat,
                                   budget, user_id, name)
    if name == "incremental_profit_rank":
        return pol.rank_and_select(tau_hat, cost_hat, budget, user_id, name)
    if name == "greedy_incremental_profit_per_cost":
        greedy = pol.greedy_by_ratio(tau_hat, cost_hat, budget)
        return pol.Selection(mask=greedy.mask, predicted_value=greedy.predicted_value,
                             predicted_cost=greedy.predicted_cost, algorithm=name)
    if name == "greedy_local_swap":
        greedy = pol.greedy_by_ratio(tau_hat, cost_hat, budget)
        swap = pol.local_swap(greedy, tau_hat, cost_hat, budget,
                              max_passes=10, exchange_candidate_limit=500)
        return pol.Selection(mask=swap.mask, predicted_value=swap.predicted_value,
                             predicted_cost=swap.predicted_cost, algorithm=name)
    raise ValueError(f"未注册的策略名：{name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E 阶段：9 策略 × 8 预算点的编排与评估")
    parser.add_argument("--input", type=Path, default=None, help="输入 CSV；不给则用 --synthetic")
    parser.add_argument("--synthetic", action="store_true", help="用已知 DGP 生成（仅打通链路）")
    parser.add_argument("--synthetic-n", type=int, default=50_000)
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "e_policy")
    args = parser.parse_args(argv)

    cfg = load_v3_protocol().config
    if args.input is not None:
        frame = _load(args.input)
        source = f"csv:{args.input}"
    else:
        if not args.synthetic:
            parser.error("必须给 --input 或 --synthetic")
        frame = _synthetic(args.synthetic_n, cfg)
        source = f"synthetic:{args.synthetic_n}"
    print(f"[数据] {source}  n={len(frame)}")

    n_total = len(frame)
    base = float(cfg.require("policy.budget.base_per_user_cny"))
    grid = [float(x) for x in cfg.require("policy.budget.per_user_grid_cny")]
    rng = child_rng(int(cfg.require("project.master_seed")), "e.policy.random", 0)
    tau_true = frame["tau_true"].to_numpy(dtype=float)
    cost_true = frame["cost_true"].to_numpy(dtype=float)

    rows: list[dict[str, object]] = []
    for per_user in grid:
        plan = pol.build_budget_plan(cfg, n_target=n_total)
        budget = per_user * n_total
        for name in POLICIES:
            selection = run_policy(name, frame, budget, rng)
            value = pol.policy_value(selection.mask, tau_true)
            actual_spend = float(cost_true[selection.mask].sum())
            rows.append({
                "per_user_budget_cny": per_user,
                "budget_cny": budget,
                "policy": name,
                "n_selected": selection.selected_count,
                "predicted_value": selection.predicted_value,
                "predicted_cost": selection.predicted_cost,
                "true_value_per_user": value,
                "true_total_value": value * n_total,
                "actual_spend_cny": actual_spend,
                "within_budget_by_hat": selection.predicted_cost <= budget + pol.BUDGET_TOLERANCE,
                "within_budget_by_true": actual_spend <= budget + pol.BUDGET_TOLERANCE,
            })
            assert plan.expected == base * n_total, "预算计划口径漂移"

    summary = pd.DataFrame(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "e_policy_grid.csv"
    summary.to_csv(target, index=False, encoding="utf-8-sig")

    print(f"\n[完成] {len(summary)} 行 = {len(grid)} 预算 × {len(POLICIES)} 策略 → {target}")
    pivot = summary.pivot(index="policy", columns="per_user_budget_cny", values="true_value_per_user")
    print("\n真实人均增量价值（元/人）：")
    print(pivot.round(4).to_string())
    violations = summary[~summary["within_budget_by_hat"] & (summary["policy"] != "all_coupon_unconstrained_reference")]
    if not violations.empty:
        print(f"\n[警告] 按预测成本超预算的组合：{len(violations)} 个")
        print(violations[["per_user_budget_cny", "policy"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
