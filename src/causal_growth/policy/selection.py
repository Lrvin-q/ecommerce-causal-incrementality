"""预算约束下的策略选择：贪心 / 0-1 背包 / 六策略对比（方案 §2.4 主线四）。

问题形式化
----------
``max_π Σ πᵢτᵢ  s.t.  Σ πᵢcᵢ ≤ B,  πᵢ ∈ {0,1}``

* ``τᵢ`` 是人均净增量贡献利润（**已含券成本**，R3）
* ``cᵢ`` 是期望核销成本，**只用来限制资源**，不再扣钱
* 两者不重复扣减——这是本项目最容易错的地方（方案 §2.3.4）

贪心为什么不是最优
------------------
按 ``τᵢ/cᵢ`` 排序依次取，是**分数背包**的最优解，但对 0-1 背包只是近似。
方案给的反例：预算 10，A 成本 6 利润 12（比值 2.0），B、C 各成本 5 利润 9（比值 1.8）。
贪心选 A 得 12；选 B+C 得 18。**比值高的那个反而害了你。**

一个必须讲清的规模事实
----------------------
本项目里 ``c ≈ 0.83 元``、``B = 3 万元``，要选**几万人**。
这种"大量小件"的背包，贪心与最优的差距**不超过单件最大价值**
（交换论证：若最优解与贪心解不同，差异只可能发生在边界那一两件上）。
所以本模块给出三样东西：
1. 全规模下的贪心 + **LP 松弛上界**（含分数件），用它量化贪心的近似程度；
2. **降规模实例上的精确 DP**，测量真实的整数间隙；
3. 方案给的反例，作为"贪心何时会大幅失败"的独立证据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "MAX_CAPACITY_UNITS",
    "SelectionResult",
    "brute_force_optimal",
    "evaluate_policy",
    "greedy_by_ratio",
    "incremental_value",
    "knapsack_dp",
    "local_improvement",
    "lp_upper_bound",
    "random_under_budget",
]

#: DP 允许的最大容量格数。决定了成本离散化的粗精细程度与内存占用。
MAX_CAPACITY_UNITS: int = 5_000


@dataclass(frozen=True)
class SelectionResult:
    """一次策略选择的产物与预算核算。"""

    name: str
    policy: np.ndarray
    cost_total: float
    budget: float
    unit: float = float("nan")
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def n_selected(self) -> int:
        return int(self.policy.sum())

    @property
    def feasible(self) -> bool:
        return self.cost_total <= self.budget * (1.0 + 1e-9)

    @property
    def budget_utilization(self) -> float:
        return self.cost_total / self.budget if self.budget > 0 else float("nan")

    def summary(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "n_selected": self.n_selected,
            "cost_total": self.cost_total,
            "budget": self.budget,
            "budget_utilization": self.budget_utilization,
            "feasible": self.feasible,
            "unit": self.unit,
            **self.diagnostics,
        }


def _validate(value: np.ndarray, cost: np.ndarray, budget: float) -> tuple[np.ndarray, np.ndarray]:
    v = np.asarray(value, dtype=float).reshape(-1)
    c = np.asarray(cost, dtype=float).reshape(-1)
    if v.shape != c.shape:
        raise ValueError(f"value 与 cost 长度不一致：{v.shape} vs {c.shape}")
    if np.isnan(v).any() or np.isnan(c).any():
        raise ValueError("value / cost 含 NaN")
    if (c < 0).any():
        raise ValueError("cost 不能为负")
    if budget < 0:
        raise ValueError(f"budget 不能为负，收到 {budget}")
    return v, c


# --------------------------------------------------------------------------- #
# 贪心
# --------------------------------------------------------------------------- #
def greedy_by_ratio(value: np.ndarray, cost: np.ndarray, budget: float) -> SelectionResult:
    """按 ``τ/c`` 降序取，取到预算用完（装不下的跳过，继续看后面）。

    "装不下就跳过"这个细节很重要：直接 break 会浪费预算。
    跳过后的结果仍然只是近似，因为它没考虑"用两个小件替换一个大件"。
    """
    v, c = _validate(value, cost, budget)
    n = v.size
    policy = np.zeros(n, dtype=bool)

    # 只考虑正价值、正成本的人；零成本的正价值件直接全取
    free = (c <= 0) & (v > 0)
    policy[free] |= True

    eligible = np.flatnonzero((v > 0) & (c > 0))
    if eligible.size == 0:
        return SelectionResult("greedy", policy, float(c[policy].sum()), budget,
                               diagnostics={"n_candidates": 0})

    ratio = v[eligible] / c[eligible]
    order = eligible[np.argsort(-ratio, kind="stable")]
    spent = float(c[free].sum())
    for idx in order:
        if spent + c[idx] <= budget:
            policy[idx] = True
            spent += c[idx]

    return SelectionResult(
        name="greedy",
        policy=policy,
        cost_total=spent,
        budget=budget,
        diagnostics={"n_candidates": int(eligible.size),
                     "n_skipped_due_to_budget": int(eligible.size - (policy[eligible].sum()))},
    )


def lp_upper_bound(value: np.ndarray, cost: np.ndarray, budget: float) -> dict[str, Any]:
    """分数背包的**上界**：按比值取，最后一件允许取小数。

    这给出 0-1 背包最优值的上界（松弛），因此
    ``(上界 − 贪心值) / 上界`` 可以量化贪心的近似程度。
    注意它是**上界**，不是最优解——把它当成"最优"是常见误读。
    """
    v, c = _validate(value, cost, budget)
    eligible = np.flatnonzero((v > 0) & (c > 0))
    total_free = float(v[(c <= 0) & (v > 0)].sum())
    if eligible.size == 0:
        return {"upper_bound": total_free, "fractional_item": -1, "fraction": 0.0}

    ratio = v[eligible] / c[eligible]
    order = eligible[np.argsort(-ratio, kind="stable")]
    remaining = budget
    total = total_free
    frac = 0.0
    frac_idx = -1
    for idx in order:
        if c[idx] <= remaining:
            total += v[idx]
            remaining -= c[idx]
        else:
            frac = remaining / c[idx]
            frac_idx = int(idx)
            total += v[idx] * frac
            break
    return {"upper_bound": float(total), "fractional_item": frac_idx, "fraction": float(frac)}


# --------------------------------------------------------------------------- #
# 精确 DP（降规模实例 + 反例验证）
# --------------------------------------------------------------------------- #
def knapsack_dp(
    value: np.ndarray,
    cost: np.ndarray,
    budget: float,
    *,
    max_capacity_units: int = MAX_CAPACITY_UNITS,
) -> SelectionResult:
    """0-1 背包动态规划（精确，但对规模敏感）。

    成本离散化：``unit = budget / max_capacity_units``，每件重量
    ``wᵢ = max(1, round(cᵢ/unit))``。**这是近似**：离散化会把
    "装得下"判成"装不下"（或反之），误差上限约为 ``unit × 件数``。
    因此本函数只用于**降规模实例**，不作为全规模的求解器。

    内存：``n × (capacity+1)`` 个布尔决策位。n=2000、cap=5000 时约 10MB。
    """
    v, c = _validate(value, cost, budget)
    n = v.size
    if n == 0:
        return SelectionResult("knapsack_dp", np.zeros(0, dtype=bool), 0.0, budget)
    if budget <= 0:
        return SelectionResult("knapsack_dp", np.zeros(n, dtype=bool), 0.0, budget)
    if max_capacity_units < 10:
        raise ValueError("max_capacity_units 太小，离散化误差会不可接受")

    unit = budget / max_capacity_units
    weights = np.maximum(1, np.round(c / unit)).astype(np.int64)
    cap = int(max_capacity_units)

    # 超出容量的件永远装不进，先剔除（但要保留其索引）
    keep = (weights <= cap) & (v > 0)
    free = (c <= 0) & (v > 0)
    policy = np.zeros(n, dtype=bool)
    policy[free] = True
    base_value = float(v[free].sum())
    base_cost = float(c[free].sum())

    idx_keep = np.flatnonzero(keep)
    if idx_keep.size == 0:
        return SelectionResult("knapsack_dp", policy, base_cost, budget, unit=unit)

    wk = weights[idx_keep]
    vk = v[idx_keep]
    m = idx_keep.size

    dp = np.zeros(cap + 1, dtype=float)
    take = np.zeros((m, cap + 1), dtype=bool)
    for i in range(m):
        wi, vi = int(wk[i]), float(vk[i])
        if wi > cap:
            continue
        cand = dp[: cap + 1 - wi] + vi
        better = cand > dp[wi:]
        take[i, wi:] = better
        dp[wi:] = np.where(better, cand, dp[wi:])

    # 回溯
    w = int(np.argmax(dp))
    for i in range(m - 1, -1, -1):
        if take[i, w]:
            policy[idx_keep[i]] = True
            w -= int(wk[i])
            if w <= 0:
                break

    total_cost = float(c[policy].sum())
    # 离散化可能让"选中的总成本"略超预算，回退最后几件直到可行
    if total_cost > budget:
        for idx in np.flatnonzero(policy)[::-1]:
            if total_cost <= budget:
                break
            policy[idx] = False
            total_cost -= float(c[idx])

    return SelectionResult(
        name="knapsack_dp",
        policy=policy,
        cost_total=float(c[policy].sum()),
        budget=budget,
        unit=unit,
        diagnostics={
            "n_candidates": int(m),
            "capacity_units": cap,
            "discretization_note": f"unit={unit:.6f} 元，单件误差约 ±{unit/2:.4f} 元",
            "dp_value": float(dp.max() + base_value),
        },
    )


def brute_force_optimal(value: np.ndarray, cost: np.ndarray, budget: float) -> SelectionResult:
    """穷举最优（仅用于 n ≤ 20 的验证与反例）。"""

    v, c = _validate(value, cost, budget)
    n = v.size
    if n > 20:
        raise ValueError(f"穷举只支持 n ≤ 20，收到 {n}")
    best_value = -np.inf
    best_policy = np.zeros(n, dtype=bool)
    for mask in range(1 << n):
        bits = np.array([(mask >> i) & 1 for i in range(n)], dtype=bool)
        if c[bits].sum() > budget:
            continue
        val = float(v[bits].sum())
        if val > best_value:
            best_value, best_policy = val, bits
    return SelectionResult(
        "brute_force", best_policy, float(c[best_policy].sum()), budget,
        diagnostics={"optimal_value": float(best_value)},
    )


# --------------------------------------------------------------------------- #
# 局部改进与随机基线
# --------------------------------------------------------------------------- #
def local_improvement(
    value: np.ndarray,
    cost: np.ndarray,
    budget: float,
    policy: np.ndarray,
    *,
    max_rounds: int = 20,
) -> SelectionResult:
    """1-2 交换局部搜索：试着"去掉一件、换进一两件更值的"。

    这是贪心的实用补丁。它保证不劣于贪心，但**不保证全局最优**。
    """
    v, c = _validate(value, cost, budget)
    pol = np.asarray(policy, dtype=bool).copy()
    spent = float(c[pol].sum())

    for _ in range(max_rounds):
        improved = False
        out_idx = np.flatnonzero(pol)
        in_idx = np.flatnonzero(~pol & (v > 0))
        if out_idx.size == 0 or in_idx.size == 0:
            break
        # 用最差的几件去换最值的几件
        worst_out = out_idx[np.argsort(v[out_idx] / np.maximum(c[out_idx], 1e-12))[:50]]
        best_in = in_idx[np.argsort(-(v[in_idx] / np.maximum(c[in_idx], 1e-12)))[:200]]
        for o in worst_out:
            for a in best_in:
                if pol[a]:
                    continue
                new_spent = spent - c[o] + c[a]
                if new_spent <= budget and v[a] > v[o]:
                    pol[o], pol[a] = False, True
                    spent = new_spent
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break

    return SelectionResult("local_search", pol, float(c[pol].sum()), budget)


def random_under_budget(
    cost: np.ndarray, budget: float, rng: np.random.Generator
) -> SelectionResult:
    """随机选人到预算用完——这是"有预算但没模型"的基线。

    它的价值就是人均效应，不含任何定向能力。任何定向策略都必须显著超过它。
    """
    c = np.asarray(cost, dtype=float).reshape(-1)
    n = c.size
    order = rng.permutation(n)
    pol = np.zeros(n, dtype=bool)
    spent = 0.0
    for idx in order:
        if spent + c[idx] <= budget:
            pol[idx] = True
            spent += c[idx]
    return SelectionResult("random", pol, spent, budget)


# --------------------------------------------------------------------------- #
# 价值评估
# --------------------------------------------------------------------------- #
def incremental_value(policy: np.ndarray, pi1: np.ndarray, pi0: np.ndarray) -> float:
    """**增量口径**的策略价值 ``V(π) = mean(π(X)·(Π(1)−Π(0)))``。

    这是方案 §2.3.4 的口径：不发券 = 0。
    与 ``evaluation.metrics.policy_value``（绝对水平口径）只差常数 ``E[Π(0)]``。
    """
    p = np.asarray(policy, dtype=bool).reshape(-1)
    a = np.asarray(pi1, dtype=float).reshape(-1)
    b = np.asarray(pi0, dtype=float).reshape(-1)
    if not (p.size == a.size == b.size):
        raise ValueError("policy / pi1 / pi0 长度不一致")
    return float(np.mean(p * (a - b)))


def evaluate_policy(
    result: SelectionResult,
    *,
    tau_true: np.ndarray,
    pi1: np.ndarray,
    pi0: np.ndarray,
    oracle_value: float | None = None,
) -> dict[str, Any]:
    """把一个策略的价值、成本、regret 汇总成一行报告数据。"""
    value = incremental_value(result.policy, pi1, pi0)
    row = {
        **result.summary(),
        "incremental_value": value,
        "value_per_yuan": (value * result.policy.size / result.cost_total)
        if result.cost_total > 0 else float("nan"),
        "mean_tau_selected": float(np.mean(tau_true[result.policy]))
        if result.n_selected else float("nan"),
    }
    if oracle_value is not None:
        row["regret"] = oracle_value - value
        row["pct_of_oracle"] = 100.0 * value / oracle_value if oracle_value > 0 else float("nan")
    return row
