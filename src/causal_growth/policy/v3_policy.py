r"""E 阶段策略接口（冻结版）：成本预测、二元选择器、预算与真值审计。

**本模块只定义接口与契约，不实现算法。** 所有算法函数抛 ``NotImplementedError``，
由 E 阶段实现填充。契约来源见 ``docs/v3_phase_E_interface.md``，
口径唯一来源 ``configs/v3/policy.yaml``（A 阶段冻结）。

它回答方案里的哪个问题
----------------------
给定 $\hat\tau(X)$ 与 $\hat c(X)$，在预算 $B$ 下选谁发券、能拿多少净增量利润；
以及这个选择离真值最优有多远、误差来自**学习**还是**优化**。

三条硬约束（违反即结果作废）
----------------------------
1. **名实相符**：``greedy_by_ratio`` / ``local_swap`` 不许叫背包或最优；
   ``cent_exact_dp`` 的精确性只针对**分币整数化问题**；``milp_select`` 在 gap>0 时不许写"最优"。
2. **两种差距分开**：预测目标上的 gap（求解器质量）与真值 regret（策略质量）不得合成一个数。
3. **三种预算分开**：预期核销成本、缓冲后、面额紧预算；``hard_cap_claim_allowed`` 为 false，
   主口径下只能说"期望不超"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from causal_growth.config import Config

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

#: 9 个候选策略（policy.yaml ``candidates`` 的顺序即契约顺序）。
POLICY_NAMES: tuple[str, ...] = (
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

#: 5 个求解器标识。名称即口径，不得替换含义。
SOLVER_NAMES: tuple[str, ...] = ("greedy", "local_swap", "cent_exact_dp", "milp", "lp_relaxation")

#: 预算口径标识。
BUDGET_BASES: tuple[str, ...] = ("expected", "buffered_expected", "worst_case_face")

ERROR_IDENTITY_TOLERANCE = 1e-9


# ---------------------------------------------------------------------------
# 数据结构（契约的一部分，完整实现）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Selection:
    """一次选择的结果。``mask`` 与输入逐用户对齐，长度必须一致。"""

    mask: BoolArray
    predicted_value: float
    predicted_cost: float
    algorithm: str

    def __post_init__(self) -> None:
        if self.algorithm not in SOLVER_NAMES + POLICY_NAMES:
            raise ValueError(f"未注册的算法名: {self.algorithm!r}")
        if self.mask.dtype != np.bool_:
            raise TypeError("mask 必须是布尔数组（True = 发券）")
        if not np.isfinite([self.predicted_value, self.predicted_cost]).all():
            raise ValueError("predicted_value / predicted_cost 必须是有限值")
        if self.predicted_cost < 0:
            raise ValueError("预测成本不能为负")

    @property
    def selected_count(self) -> int:
        return int(self.mask.sum())

    @property
    def per_user_cost(self) -> float:
        """人均预测成本；选中 0 人时为 0，不返回 NaN。"""
        return float(self.predicted_cost / self.selected_count) if self.selected_count else 0.0


@dataclass(frozen=True)
class CostModel:
    """两阶段成本模型：P(购买) × E[核销金额 | 购买]，另配直接回归作对照。"""

    stage_purchase: Any
    stage_redemption: Any
    auxiliary_direct: Any
    target: str = "expected_coupon_cost_given_assigned_coupon_and_observable_features"
    fitted_on: str = "training_only"

    def __post_init__(self) -> None:
        if self.target != "expected_coupon_cost_given_assigned_coupon_and_observable_features":
            raise ValueError("成本模型目标与 policy.yaml 的注册口径不一致")
        if self.fitted_on != "training_only":
            raise ValueError("成本模型只允许在 training 上拟合；validation 仅用于校准")


@dataclass(frozen=True)
class MilpResult:
    """带证明状态的 MILP 结果。``relative_gap`` > 0 时不得声称最优。"""

    selection: Selection
    status: str
    incumbent: float
    bound: float
    relative_gap: float
    time_limit_seconds: float

    def __post_init__(self) -> None:
        if self.status not in {"optimal", "time_limit", "infeasible", "error"}:
            raise ValueError(f"未注册的 MILP 状态: {self.status!r}")
        if not np.isfinite([self.incumbent, self.bound, self.relative_gap]).all():
            raise ValueError("incumbent / bound / gap 必须是有限值")
        if self.bound + 1e-9 < self.incumbent:
            raise ValueError("上界不得小于可行解目标值")

    @property
    def may_claim_optimal(self) -> bool:
        """只有 gap 为 0 且状态为 optimal 才允许说"最优"。"""
        return self.status == "optimal" and self.relative_gap <= 1e-12


@dataclass(frozen=True)
class BudgetPlan:
    """三种预算口径必须同时存在，且不得互相替代。"""

    expected: float
    buffered: float
    worst_case: float
    n_target: int
    multiplier: float = 1.25

    def __post_init__(self) -> None:
        if min(self.expected, self.buffered, self.worst_case) < 0:
            raise ValueError("预算不能为负")
        if self.n_target <= 0:
            raise ValueError("目标用户数必须为正")
        if self.buffered < self.expected:
            raise ValueError("缓冲预算不得低于期望预算")


@dataclass(frozen=True)
class ErrorDecomposition:
    """学习误差与优化误差的分解；``identity_residual`` 应接近 0。"""

    learning_error: float
    optimization_error: float
    total_regret: float
    identity_residual: float = field(init=False)

    def __post_init__(self) -> None:
        residual = self.total_regret - (self.learning_error + self.optimization_error)
        object.__setattr__(self, "identity_residual", float(residual))
        if abs(residual) > ERROR_IDENTITY_TOLERANCE:
            raise ValueError(
                f"误差分解不闭合：total={self.total_regret:.6f} "
                f"≠ learning+optimization={self.learning_error + self.optimization_error:.6f}"
            )


# ---------------------------------------------------------------------------
# 契约层（实现；供实现阶段与测试复用）
# ---------------------------------------------------------------------------
def require_same_length(value: FloatArray, cost: FloatArray, *extra: Any) -> None:
    """逐用户数组必须等长；长度不一致一律抛，不广播。"""
    lengths = {len(value), len(cost), *(len(item) for item in extra)}
    if len(lengths) != 1:
        raise ValueError(f"逐用户数组长度不一致: {sorted(lengths)}")


def require_non_negative_cost(cost: FloatArray, floor: float) -> None:
    """成本必须严格为正（下界 ``cost_floor_cny``），否则比值排序会除零或发散。"""
    if np.any(cost <= 0):
        raise ValueError("预测成本必须严格为正；请先施加 cost_floor_cny")
    if np.any(cost < floor):
        raise ValueError(f"预测成本低于冻结下界 {floor}")


def require_binary_mask(mask: BoolArray, n: int) -> None:
    """选中向量必须是长度 n 的布尔数组。"""
    if mask.shape != (n,):
        raise ValueError(f"mask 形状应为 ({n},)，实际 {mask.shape}")


def tie_break_order(user_ids: Any) -> NDArray[np.int64]:
    """确定性的平手规则：``user_id_ascending``（policy.yaml 冻结）。

    返回按 user_id 升序的索引；调用方在同一分数上必须用它打破平手，
    不得依赖 ``argsort`` 的默认不稳定行为。
    """
    identifiers = np.asarray(user_ids)
    return np.argsort(identifiers, kind="stable")


# ---------------------------------------------------------------------------
# 成本模型接口（不实现）
# ---------------------------------------------------------------------------
def fit_cost_model(learning: Any, cfg: Config) -> CostModel:
    """在 training 观测上拟合两阶段成本模型；validation 只用于校准。"""
    raise NotImplementedError("E 阶段实现：两阶段成本模型")


def predict_expected_cost(model: CostModel, frame: pd.DataFrame, cfg: Config) -> FloatArray:
    r"""逐用户预测 $\hat c(X)$（元），下界 ``policy.cost_model.cost_floor_cny``。"""
    raise NotImplementedError("E 阶段实现：期望成本预测")


# ---------------------------------------------------------------------------
# 求解器族（已实现；口径见 docs/v3_phase_E_interface.md §4）
# ---------------------------------------------------------------------------
BUDGET_TOLERANCE = 1e-9


def _validate_solver_inputs(value: FloatArray, cost: FloatArray, budget: float) -> None:
    """求解器统一入口校验：等长、逐用户成本严格为正、预算非负。"""
    require_same_length(value, cost)
    if budget < 0:
        raise ValueError("预算不能为负")
    require_non_negative_cost(np.asarray(cost, dtype=np.float64), floor=0.0)


def _assemble(value: FloatArray, cost: FloatArray, mask: BoolArray, algorithm: str) -> Selection:
    """由 mask 汇总预测价值与预测成本，统一构造 Selection。"""
    mask = np.asarray(mask, dtype=np.bool_)
    return Selection(
        mask=mask,
        predicted_value=float(np.asarray(value, dtype=np.float64)[mask].sum()),
        predicted_cost=float(np.asarray(cost, dtype=np.float64)[mask].sum()),
        algorithm=algorithm,
    )


def greedy_by_ratio(value: FloatArray, cost: FloatArray, budget: float,
                    tie_break: str = "user_id_ascending") -> Selection:
    r"""按 $\hat\tau/\hat c$ 降序选到预算用完。**不是背包，也不是最优。**

    平手规则：输入必须已按 ``user_id`` 升序排列；本函数用 **stable** 排序，
    因此比值相同的候选保持输入顺序，等价于冻结的 ``user_id_ascending``。
    装不下的人**跳过继续看后面**，不直接中断——直接 break 会白白浪费预算。
    只对预测价值为正的人排序（``no_negative_predicted_increment_for_targeting``）。
    """
    if tie_break != "user_id_ascending":
        raise ValueError("只支持 user_id_ascending（policy.yaml 冻结口径）")
    _validate_solver_inputs(value, cost, budget)
    value = np.asarray(value, dtype=np.float64)
    cost = np.asarray(cost, dtype=np.float64)

    mask = np.zeros(value.size, dtype=np.bool_)
    eligible = np.flatnonzero(value > 0)
    if eligible.size == 0:
        return _assemble(value, cost, mask, "greedy")

    order = eligible[np.argsort(-(value[eligible] / cost[eligible]), kind="stable")]
    spent = 0.0
    for index in order:
        if spent + cost[index] <= budget + BUDGET_TOLERANCE:
            mask[index] = True
            spent += float(cost[index])
    return _assemble(value, cost, mask, "greedy")


def local_swap(initial: Selection, value: FloatArray, cost: FloatArray, budget: float,
               max_passes: int, exchange_candidate_limit: int) -> Selection:
    """贪心解上做成对交换的局部改进。**仍不保证最优。**

    每轮尝试"移出一个已选、加入一个未选"，只在**价值严格上升且预算可行**时接受；
    未选者按价值降序只看前 ``exchange_candidate_limit`` 个，避免 O(n²)。
    任何一轮没有改进就停。
    """
    _validate_solver_inputs(value, cost, budget)
    require_binary_mask(initial.mask, value.size)
    if max_passes < 0 or exchange_candidate_limit <= 0:
        raise ValueError("max_passes 不能为负，exchange_candidate_limit 必须为正")

    value = np.asarray(value, dtype=np.float64)
    cost = np.asarray(cost, dtype=np.float64)
    mask = initial.mask.copy()
    spent = float(cost[mask].sum())

    for _ in range(max_passes):
        selected = np.flatnonzero(mask)
        unselected = np.flatnonzero(~mask)
        if selected.size == 0 or unselected.size == 0:
            break
        unselected = unselected[np.argsort(-value[unselected], kind="stable")][:exchange_candidate_limit]

        improved = False
        for out_index in selected:
            room = budget - (spent - cost[out_index])
            candidates = unselected[(cost[unselected] <= room + BUDGET_TOLERANCE)
                                    & (value[unselected] > value[out_index])]
            if candidates.size == 0:
                continue
            in_index = int(candidates[np.argmax(value[candidates])])
            mask[out_index] = False
            mask[in_index] = True
            spent += float(cost[in_index] - cost[out_index])
            unselected = unselected[unselected != in_index]
            improved = True
            break
        if not improved:
            break
    return _assemble(value, cost, mask, "local_swap")


def cent_exact_dp(value_cents: NDArray[np.int64], cost_cents: NDArray[np.int64],
                  budget_cents: int) -> Selection:
    """**分币整数化问题**上的精确 0/1 背包 DP（``decimal_half_up_to_cent``）。

    精确性只对该整数化问题成立；浮点原问题可能有不同最优解，**不得声称原问题最优**。
    返回的 ``predicted_value`` / ``predicted_cost`` 单位是**分**（与输入一致）。
    规模化使用注意：时间与内存都是 ``O(n × budget_cents)``，只用于小池子（≤ 500）。
    """
    value = np.asarray(value_cents, dtype=np.int64)
    cost = np.asarray(cost_cents, dtype=np.int64)
    if value.shape != cost.shape:
        raise ValueError("value_cents 与 cost_cents 必须等长")
    if value.ndim != 1:
        raise ValueError("只接受一维数组")
    if np.any(cost < 0):
        raise ValueError("整数化成本不能为负")
    budget = int(budget_cents)
    if budget < 0:
        raise ValueError("预算不能为负")

    n = value.size
    neg_inf = np.int64(-(1 << 62))
    table = np.full((n + 1, budget + 1), neg_inf, dtype=np.int64)
    table[0, :] = 0
    take = np.zeros((n, budget + 1), dtype=np.bool_)

    for i in range(n):
        ci, vi = int(cost[i]), int(value[i])
        table[i + 1] = table[i]
        if ci <= budget and vi > 0:
            candidate = table[i, : budget + 1 - ci] + vi
            improved = candidate > table[i + 1, ci:]
            positions = np.flatnonzero(improved) + ci
            table[i + 1, positions] = candidate[improved]
            take[i, positions] = True

    best_budget = int(np.argmax(table[n]))
    mask = np.zeros(n, dtype=np.bool_)
    remaining = best_budget
    for i in range(n - 1, -1, -1):
        if take[i, remaining]:
            mask[i] = True
            remaining -= int(cost[i])
    return _assemble(value.astype(np.float64), cost.astype(np.float64), mask, "cent_exact_dp")


def milp_select(value: FloatArray, cost: FloatArray, budget: float,
                time_limit_seconds: float, relative_gap: float) -> MilpResult:
    """时间受控 MILP（scipy 内置 HiGHS），必须同时返回 incumbent / bound / gap / status。

    只有 ``status == "optimal"`` 且 ``gap ≈ 0`` 时 ``may_claim_optimal`` 才为真；
    时间受限时返回的是**带上下界的可行解**，正文只能这么写。
    """
    from scipy.optimize import Bounds, LinearConstraint, milp

    _validate_solver_inputs(value, cost, budget)
    if time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds 必须为正")

    value = np.asarray(value, dtype=np.float64)
    cost = np.asarray(cost, dtype=np.float64)
    result = milp(
        c=-value,
        constraints=LinearConstraint(cost.reshape(1, -1), -np.inf, budget),
        integrality=np.ones(value.size),
        bounds=Bounds(0, 1),
        options={"time_limit": float(time_limit_seconds), "mip_rel_gap": float(relative_gap), "disp": False},
    )

    status_map = {0: "optimal", 1: "time_limit", 2: "infeasible"}
    status = status_map.get(int(result.status), "error")
    if result.x is None:
        empty = np.zeros(value.size, dtype=np.bool_)
        selection = _assemble(value, cost, empty, "milp")
        incumbent = 0.0
        bound = 0.0
        gap = 0.0
    else:
        mask = np.asarray(result.x, dtype=np.float64) > 0.5
        selection = _assemble(value, cost, mask, "milp")
        incumbent = float(selection.predicted_value)
        bound = float(-result.mip_dual_bound) if getattr(result, "mip_dual_bound", None) is not None else incumbent
        gap = float(getattr(result, "mip_gap", 0.0) or 0.0)
    return MilpResult(
        selection=selection,
        status=status,
        incumbent=max(incumbent, 0.0),
        bound=max(bound, max(incumbent, 0.0)),
        relative_gap=max(gap, 0.0),
        time_limit_seconds=float(time_limit_seconds),
    )


def lp_upper_bound(value: FloatArray, cost: FloatArray, budget: float) -> float:
    """分数背包松弛的**上界**（不是可行解，不得当策略用）。

    与贪心使用**完全相同**的目标与成本（``policy.optimization``），否则上界没有意义。
    只考虑预测价值为正的人：负价值的人在任何最优解里都不会被选中。
    """
    _validate_solver_inputs(value, cost, budget)
    value = np.asarray(value, dtype=np.float64)
    cost = np.asarray(cost, dtype=np.float64)
    eligible = np.flatnonzero(value > 0)
    if eligible.size == 0:
        return 0.0

    order = eligible[np.argsort(-(value[eligible] / cost[eligible]), kind="stable")]
    remaining = float(budget)
    total = 0.0
    for index in order:
        if cost[index] <= remaining + BUDGET_TOLERANCE:
            total += float(value[index])
            remaining -= float(cost[index])
        else:
            total += float(value[index]) * (remaining / float(cost[index]))
            break
    return float(total)


# ---------------------------------------------------------------------------
# 预算接口（不实现）
# ---------------------------------------------------------------------------
def build_budget_plan(budget_cfg: Any, n_target: int) -> BudgetPlan:
    """由 ``policy.budget`` 构造三种预算口径。"""
    raise NotImplementedError("E 阶段实现：预算三口径")


def audit_budget(selection: Selection, observed_cost: FloatArray, plan: BudgetPlan) -> dict[str, Any]:
    """报告预期成本、实际支出、超支概率；主口径下**不得**声称硬上限。"""
    raise NotImplementedError("E 阶段实现：预算审计")


# ---------------------------------------------------------------------------
# 评估与审计接口（不实现）
# ---------------------------------------------------------------------------
def policy_value(mask: BoolArray, profit_true: FloatArray, baseline: FloatArray | None = None) -> float:
    """给定名单的**真实**净增量利润（元/人）；只在冻结后由审计入口调用。"""
    raise NotImplementedError("E 阶段实现：策略真值价值")


def truth_regret(mask: BoolArray, truth_optimal_mask: BoolArray, profit_true: FloatArray) -> float:
    """与真值最优名单的差（元）；这是**策略质量**，不是求解器质量。"""
    raise NotImplementedError("E 阶段实现：真值 regret")


def decompose_error(mask: BoolArray, tau_hat: FloatArray, profit_true: FloatArray,
                    truth_optimal_mask: BoolArray) -> ErrorDecomposition:
    """拆成 learning / optimization 两项，并校验恒等式闭合。"""
    raise NotImplementedError("E 阶段实现：误差分解")
