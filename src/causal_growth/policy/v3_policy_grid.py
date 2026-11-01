"""E 阶段编排：9 个候选策略 × 配置预算网格。

为什么单独成模块
----------------
``v3_policy`` 只提供组件（成本模型、求解器、预算口径、误差分解、排序）。
"把 9 个策略在每个预算点各跑一遍并评估"需要逐用户表与真值列，属于编排层；
放在接口模块会让可复用的纯函数被数据路径绑死，放在脚本里又会让 D03 诊断
无法复用同一套口径。本模块只依赖 ``v3_policy`` 与配置。

输入契约（9 列，UTF-8）
----------------------
``user_id, is_new, cart_value, purchase_propensity, predicted_profit,
tau_hat, cost_hat, tau_true, cost_true``

- **选人只用** ``tau_hat`` / ``cost_hat`` / ``purchase_propensity`` / ``predicted_profit``；
- **评估只用** ``tau_true`` / ``cost_true``；
- 预算合规同时报两件事：按 ``cost_hat`` 是否超预算、按 ``cost_true`` 实际支出了多少。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from causal_growth.config import Config
from causal_growth.policy import v3_policy as pol
from causal_growth.rng import child_rng

POLICIES: tuple[str, ...] = (
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

REQUIRED_COLUMNS: tuple[str, ...] = (
    "user_id", "is_new", "cart_value", "purchase_propensity", "predicted_profit",
    "tau_hat", "cost_hat", "tau_true", "cost_true",
)

GRID_COLUMNS: tuple[str, ...] = (
    "per_user_budget_cny", "budget_cny", "policy", "n_selected",
    "predicted_value", "predicted_cost", "true_value_per_user", "true_total_value",
    "actual_spend_cny", "within_budget_by_hat", "within_budget_by_true",
)


def require_grid_frame(frame: pd.DataFrame) -> None:
    """检查输入表是否满足 9 列契约，并对参与计算的列查有限值与成本下界。"""
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"输入缺列：{missing}")
    numeric = [
        "cart_value", "purchase_propensity", "predicted_profit",
        "tau_hat", "cost_hat", "tau_true", "cost_true",
    ]
    if not frame["user_id"].is_unique:
        raise ValueError("user_id 必须唯一；重复行会让配对与预算口径同时失真")
    values = frame.loc[:, numeric].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("策略输入含非有限值")
    if (frame["cost_hat"].to_numpy(dtype=np.float64) <= 0).any():
        raise ValueError("cost_hat 必须严格为正（成本下界失效）")
    if (frame["cost_true"].to_numpy(dtype=np.float64) < 0).any():
        raise ValueError("cost_true 不能为负")


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


def evaluate_policy_grid(
    frame: pd.DataFrame,
    cfg: Config,
    *,
    rng: np.random.Generator | None = None,
) -> pd.DataFrame:
    """在配置预算网格上评估全部策略，返回 ``预算 × 策略`` 长表。

    每行同时给出预测口径（``predicted_value`` / ``predicted_cost`` /
    ``within_budget_by_hat``）与真值口径（``true_value_per_user`` /
    ``actual_spend_cny`` / ``within_budget_by_true``）。``random_same_budget``
    的随机流由 ``rng`` 决定；不传时使用固定的 ``e.policy.random`` 派生流，
    与脚本的历史行为一致。
    """
    # 随机名单按行序抽人、贪心按行序 tie-break：必须先固定成 user_id 升序，
    # 否则同一批用户换个行序就会得到不同的策略名单。
    frame = frame.sort_values("user_id", kind="stable").reset_index(drop=True)
    require_grid_frame(frame)
    if rng is None:
        rng = child_rng(int(cfg.require("project.master_seed")), "e.policy.random", 0)
    n_total = len(frame)
    base = float(cfg.require("policy.budget.base_per_user_cny"))
    grid = [float(value) for value in cfg.require("policy.budget.per_user_grid_cny")]
    tau_true: NDArray[np.float64] = frame["tau_true"].to_numpy(dtype=float)
    cost_true: NDArray[np.float64] = frame["cost_true"].to_numpy(dtype=float)

    rows: list[dict[str, Any]] = []
    for per_user in grid:
        plan = pol.build_budget_plan(cfg, n_target=n_total)
        if plan.expected != base * n_total:
            raise ValueError("预算计划口径漂移：expected != base × n_total")
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
                "within_budget_by_hat": bool(
                    selection.predicted_cost <= budget + pol.BUDGET_TOLERANCE
                ),
                "within_budget_by_true": bool(
                    actual_spend <= budget + pol.BUDGET_TOLERANCE
                ),
            })
    summary = pd.DataFrame(rows)
    if tuple(summary.columns) != GRID_COLUMNS:
        raise ValueError("网格输出列与契约不一致")
    return summary


__all__ = [
    "GRID_COLUMNS",
    "POLICIES",
    "REQUIRED_COLUMNS",
    "evaluate_policy_grid",
    "require_grid_frame",
    "run_policy",
]
