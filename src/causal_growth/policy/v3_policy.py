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
# 求解器接口（不实现）
# ---------------------------------------------------------------------------
def greedy_by_ratio(value: FloatArray, cost: FloatArray, budget: float,
                    tie_break: str = "user_id_ascending") -> Selection:
    r"""按 $\hat\tau/\hat c$ 降序选到预算用完。**不是背包，也不是最优。**"""
    raise NotImplementedError("E 阶段实现：比值贪心")


def local_swap(initial: Selection, value: FloatArray, cost: FloatArray, budget: float,
               max_passes: int, exchange_candidate_limit: int) -> Selection:
    """贪心解上做成对交换的局部改进。**仍不保证最优。**"""
    raise NotImplementedError("E 阶段实现：贪心后局部交换")


def cent_exact_dp(value_cents: NDArray[np.int64], cost_cents: NDArray[np.int64],
                  budget_cents: int) -> Selection:
    """**分币整数化问题**上的精确 DP（``decimal_half_up_to_cent``）。

    精确性只对该整数化问题成立，不得声称原浮点问题最优。
    """
    raise NotImplementedError("E 阶段实现：分币精确 DP")


def milp_select(value: FloatArray, cost: FloatArray, budget: float,
                time_limit_seconds: float, relative_gap: float) -> MilpResult:
    """时间受控 MILP，必须同时返回 incumbent / bound / gap / status。"""
    raise NotImplementedError("E 阶段实现：MILP 对照")


def lp_upper_bound(value: FloatArray, cost: FloatArray, budget: float) -> float:
    """分数背包松弛给出的**上界**；不是可行解，不得当策略用。"""
    raise NotImplementedError("E 阶段实现：LP 上界")


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
