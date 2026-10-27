r"""E 阶段正文证据：成本校准、求解器互证、桶宽收敛、随机基线、误差分解、规模与预算口径。

本模块回答 ``docs/v3_phase_E_coverage.md`` 里 12 个"需要真实数据/编排层"的缺口，
并与 ``v3_policy_grid`` 共享同一套 9 列契约：

``user_id, is_new, cart_value, purchase_propensity, predicted_profit,
tau_hat, cost_hat, tau_true, cost_true``

三条纪律
--------
1. **真值隔离**：所有 mask 先算完，``tau_true`` / ``cost_true`` 只用于评估，
   评估列统一带 ``true_`` / ``actual_`` 前缀。毒化真值不得改变任何选人列。
2. **单位**：对外数值一律为 **元**；分币整数化只在 ``to_cents_half_up`` 内部出现。
   ``cent_exact_dp`` 返回的 ``Selection.predicted_*`` 单位是分，本模块一律不用它汇总。
3. **小池预算**：小池 / 桶宽 / 误差分解用 ``per_user_budget × pool_size``，
   保持与全量相同的"人均预算强度"；不是把全量预算塞给一个小池子。

**不预设阈值**：桶宽收敛只出曲线，收敛阈值必须在看到曲线后由协议评审确定，
不得在代码里写死"gap < x% 即通过"。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from causal_growth.config import Config
from causal_growth.policy import v3_policy as pol
from causal_growth.policy.v3_policy_grid import require_grid_frame
from causal_growth.rng import child_rng

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
IntArray = NDArray[np.int64]

SOLVERS: tuple[str, ...] = (
    "greedy",
    "greedy_local_swap",
    "cent_exact_dp",
    "milp",
    "lp_relaxation",
)

POOL_COLUMNS: tuple[str, ...] = (
    "pool_size", "per_user_budget_cny", "budget_cny", "solver", "exactness",
    "n_selected", "predicted_value_cny", "predicted_cost_cny", "within_budget_by_hat",
    "feasible_under_original_cost", "status", "incumbent_cny", "bound_cny",
    "relative_gap", "may_claim_optimal", "true_value_per_user", "true_total_value_cny",
    "actual_spend_cny", "within_budget_by_true", "seconds",
)

BUCKET_COLUMNS: tuple[str, ...] = (
    "pool_size", "per_user_budget_cny", "budget_cny", "method", "width_cny",
    "n_selected", "predicted_value_cny", "predicted_cost_cny", "within_budget_by_hat",
    "feasible_under_original_cost", "n_dropped_for_feasibility", "gap_to_exact_cny",
    "gap_per_user_cny", "true_value_per_user", "actual_spend_cny", "seconds",
)

RANDOM_COLUMNS: tuple[str, ...] = (
    "n_total", "per_user_budget_cny", "budget_cny", "seed", "n_selected", "predicted_cost_cny",
    "within_budget_by_hat", "true_value_per_user", "true_total_value_cny",
    "actual_spend_cny", "within_budget_by_true", "overrun_cny",
)

RANDOM_SUMMARY_COLUMNS: tuple[str, ...] = (
    "n_total", "per_user_budget_cny", "budget_cny", "seeds", "mean_true_value_per_user",
    "sd_true_value_per_user", "mean_se", "q025", "q500", "q975",
    "overrun_probability", "mean_actual_spend_cny", "max_overrun_cny",
    "mean_predicted_cost_cny", "mean_n_selected", "interpretation",
)

DECOMPOSITION_COLUMNS: tuple[str, ...] = (
    "pool_size", "per_user_budget_cny", "budget_cny", "actual_solver",
    "learning_error_cny_per_user", "optimization_error_cny_per_user",
    "total_regret_cny_per_user", "identity_residual",
    "true_value_actual", "true_value_oracle_under_hat", "true_value_truth",
    "oracle_exactness", "truth_exactness", "truth_solver",
    "truth_milp_status", "truth_milp_relative_gap",
    "truth_milp_bound_cny", "truth_milp_incumbent_cny", "truth_milp_may_claim_optimal",
    "truth_milp_cost_basis", "truth_milp_cost_floor_cny",
    "truth_feasible_under_original_cost", "seconds",
)

SCALE_COLUMNS: tuple[str, ...] = (
    "pool_size", "pool_is_full_test", "per_user_budget_cny", "budget_cny", "solver",
    "n_selected", "predicted_value_cny", "predicted_cost_cny",
    "feasible_under_original_cost", "status", "incumbent_cny", "bound_cny",
    "relative_gap", "may_claim_optimal", "lp_upper_bound_cny",
    "incumbent_to_lp_ratio", "true_value_per_user", "actual_spend_cny",
    "within_budget_by_true", "seconds",
)

CONSERVATIVE_COLUMNS: tuple[str, ...] = (
    "n_total", "mode", "policy", "per_user_budget_cny", "budget_cny", "mode_budget_cny",
    "seeds", "selected_count_mean", "predicted_cost_mean", "actual_spend_mean",
    "actual_spend_q025", "actual_spend_q975", "overrun_probability",
    "overrun_vs_expected_probability",
    "true_value_per_user_mean", "true_total_value_cny_mean", "audited_value_cny_mean",
    "evidence_basis", "value_basis", "observed_value_status",
)


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def to_cents_half_up(amounts: FloatArray) -> IntArray:
    """``decimal_half_up_to_cent``：按十进制字符串做四舍五入到分。

    不用 ``floor(x * 100 + 0.5)``：二进制浮点会把 1.005 变成 1.004999…，
    与策略配置里冻结的整数化规则不一致。
    """
    array = np.asarray(amounts, dtype=np.float64)
    if array.ndim != 1:
        raise ValueError("金额必须是一维数组")
    if not np.isfinite(array).all():
        raise ValueError("金额含非有限值")
    if (array < 0).any():
        raise ValueError("金额不能为负")
    cent = Decimal("0.01")
    return np.array(
        [int(Decimal(str(float(x))).quantize(cent, rounding=ROUND_HALF_UP) * 100) for x in array],
        dtype=np.int64,
    )


def to_signed_cents_half_up(amounts: FloatArray) -> IntArray:
    """带符号的 half-up 分币整数化；``tau_hat`` / ``tau_true`` 可以为负。"""
    array = np.asarray(amounts, dtype=np.float64)
    if array.ndim != 1:
        raise ValueError("金额必须是一维数组")
    if not np.isfinite(array).all():
        raise ValueError("金额含非有限值")
    sign = np.sign(array)
    return (sign * to_cents_half_up(np.abs(array))).astype(np.int64)


def _as_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """校验 9 列契约，并按 ``user_id`` 升序固定 tie-break 的输入顺序。"""
    require_grid_frame(frame)
    return frame.sort_values("user_id", kind="stable").reset_index(drop=True)


def _master_seed(cfg: Config) -> int:
    return int(cfg.require("project.master_seed"))


def _per_user_grid(cfg: Config) -> list[float]:
    return [float(x) for x in cfg.require("policy.budget.per_user_grid_cny")]


def _pool_frame(frame: pd.DataFrame, size: int, master_seed: int, stream: str,
                seed_index: int) -> pd.DataFrame:
    """从全量表中确定性抽取一个无放回小池；池内按 ``user_id`` 升序。"""
    if size <= 0:
        raise ValueError("池子大小必须为正")
    if size > len(frame):
        raise ValueError(f"池子 {size} 大于可用用户数 {len(frame)}")
    if size == len(frame):
        return frame.copy()
    rng = child_rng(master_seed, stream, seed_index)
    index = np.sort(rng.choice(len(frame), size=size, replace=False))
    return frame.iloc[index].reset_index(drop=True)


def _arrays(frame: pd.DataFrame) -> dict[str, NDArray]:
    return {
        "tau_hat": frame["tau_hat"].to_numpy(dtype=np.float64),
        "cost_hat": frame["cost_hat"].to_numpy(dtype=np.float64),
        "tau_true": frame["tau_true"].to_numpy(dtype=np.float64),
        "cost_true": frame["cost_true"].to_numpy(dtype=np.float64),
    }


def _mask_metrics(mask: BoolArray, arrays: dict[str, NDArray], budget: float) -> dict[str, Any]:
    """mask 冻结后同时给出预测口径与真值口径的汇总（元）。"""
    mask = np.asarray(mask, dtype=np.bool_)
    tau_hat, cost_hat = arrays["tau_hat"], arrays["cost_hat"]
    tau_true, cost_true = arrays["tau_true"], arrays["cost_true"]
    predicted_value = float(tau_hat[mask].sum())
    predicted_cost = float(cost_hat[mask].sum())
    actual_spend = float(cost_true[mask].sum())
    true_value = float(tau_true[mask].sum()) / mask.size
    return {
        "n_selected": int(mask.sum()),
        "predicted_value_cny": predicted_value,
        "predicted_cost_cny": predicted_cost,
        "within_budget_by_hat": bool(predicted_cost <= budget + pol.BUDGET_TOLERANCE),
        "feasible_under_original_cost": bool(
            predicted_cost <= budget + pol.BUDGET_TOLERANCE
        ),
        "true_value_per_user": true_value,
        "true_total_value_cny": true_value * mask.size,
        "actual_spend_cny": actual_spend,
        "within_budget_by_true": bool(actual_spend <= budget + pol.BUDGET_TOLERANCE),
    }


def _brute_force_mask(value: FloatArray, cost: FloatArray, budget: float) -> tuple[BoolArray, float]:
    """``n ≤ 20`` 的**浮点原问题**穷举最优（验证用，不是策略）。"""
    n = value.size
    if n > 20:
        raise ValueError(f"穷举只支持 n ≤ 20，收到 {n}")
    masks = (
        (np.arange(1 << n, dtype=np.int64)[:, None] >> np.arange(n, dtype=np.int64)) & 1
    ).astype(np.bool_)
    costs = masks.astype(np.float64) @ cost
    values = masks.astype(np.float64) @ value
    values = np.where(costs <= budget + pol.BUDGET_TOLERANCE, values, -np.inf)
    best = int(np.argmax(values))
    return masks[best].copy(), float(values[best])


def _bucket_weights(cost: FloatArray, width: float) -> IntArray:
    """把原成本换成整数桶权重；``width=0.01`` 精确走分币 half-up。

    其他宽度用浮点 half-up。浮点 ``1.005/0.01`` 会得到 100.4999…，
    直接 ``floor(x+0.5)`` 会把 1.005 舍成 100 分；分币路径改用 Decimal，
    避免在最小桶宽上制造假收敛。
    """
    values = np.asarray(cost, dtype=np.float64)
    if np.isclose(width, 0.01, rtol=0.0, atol=1e-12):
        return to_cents_half_up(values)
    return np.floor(values / width + 0.5 + 1e-9).astype(np.int64)


def _bucket_dp_mask(
    value: FloatArray, cost: FloatArray, budget: float, width: float
) -> tuple[BoolArray, int, int]:
    """近似桶宽 DP：成本按 ``width`` 四舍五入成整数桶，再按原成本复核并回退。

    这是近似，**不声称最优**。``width=0.01`` 的权重与分币 half-up 一致，
    但桶权重为 0 的人（成本不足半桶）会先被无偿选中，再由原成本复核回退，
    因此仍不保证与 ``cent_exact_dp`` 逐位相同。
    """
    if width <= 0:
        raise ValueError("桶宽必须为正")
    value = np.asarray(value, dtype=np.float64)
    cost = np.asarray(cost, dtype=np.float64)
    n = value.size
    cap = int(np.floor(budget / width + 1e-9))
    mask = np.zeros(n, dtype=np.bool_)
    if cap <= 0:
        return mask, 0, cap

    weights = _bucket_weights(cost, width)
    free = (weights == 0) & (value > 0)
    mask = free.copy()
    base = float(value[free].sum())
    dp = np.full(cap + 1, base, dtype=np.float64)
    take = np.zeros((n, cap + 1), dtype=np.bool_)
    for i in range(n):
        vi, wi = float(value[i]), int(weights[i])
        if vi <= 0 or wi <= 0 or wi > cap:
            continue
        candidate = dp[: cap + 1 - wi] + vi
        better = candidate > dp[wi:]
        if better.any():
            take[i, wi:] = better
            dp[wi:] = np.where(better, candidate, dp[wi:])

    remaining = int(np.argmax(dp))
    for i in range(n - 1, -1, -1):
        if take[i, remaining]:
            mask[i] = True
            remaining -= int(weights[i])
            if remaining <= 0:
                break

    spent = float(cost[mask].sum())
    dropped = 0
    if spent > budget + pol.BUDGET_TOLERANCE:
        # 桶权重可能低估原成本；按价值升序回退到可行，回退件数要如实上报。
        order = np.flatnonzero(mask)
        order = order[np.argsort(value[order], kind="stable")]
        for index in order:
            if spent <= budget + pol.BUDGET_TOLERANCE:
                break
            mask[index] = False
            spent -= float(cost[index])
            dropped += 1
    return mask, dropped, cap


# ---------------------------------------------------------------------------
# 1. 成本模型校准（只在 validation 观测日志上做，不回流拟合）
# ---------------------------------------------------------------------------
def calibrate_cost_predictions(
    predicted: FloatArray, observed: FloatArray
) -> dict[str, Any]:
    """validation 上的成本校准：偏差、斜率、MAE/RMSE、相关性。

    回答 ``cost_model.calibration_only_on_validation``：预测的期望核销成本
    在**没见过拟合的 validation 观测**上是否无偏、是否能分辨高低。
    校准结果只用于报告，**不得回流**改成本模型或选人阈值。
    """
    pred = np.asarray(predicted, dtype=np.float64)
    obs = np.asarray(observed, dtype=np.float64)
    if pred.shape != obs.shape:
        raise ValueError("predicted 与 observed 必须等长")
    if pred.ndim != 1:
        raise ValueError("只接受一维数组")
    if pred.size == 0:
        raise ValueError("校准样本不能为空")
    if not np.isfinite(pred).all() or not np.isfinite(obs).all():
        raise ValueError("校准输入含非有限值")
    if (pred <= 0).any() or (obs < 0).any():
        raise ValueError("预测成本必须为正，观测成本不能为负")

    n = int(pred.size)
    mean_pred = float(pred.mean())
    mean_obs = float(obs.mean())
    bias = mean_obs - mean_pred
    residual = obs - pred
    mae = float(np.abs(residual).mean())
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    pred_sd = float(pred.std(ddof=1)) if n > 1 else 0.0
    obs_sd = float(obs.std(ddof=1)) if n > 1 else 0.0
    if n > 1 and pred_sd > 0 and obs_sd > 0:
        pearson = float(np.corrcoef(pred, obs)[0, 1])
        slope = float(np.cov(pred, obs, ddof=1)[0, 1] / np.var(pred, ddof=1))
        intercept = float(mean_obs - slope * mean_pred)
    else:
        pearson = float("nan")
        slope = float("nan")
        intercept = float("nan")
    return {
        "n": n,
        "mean_predicted_cny": mean_pred,
        "mean_observed_cny": mean_obs,
        "bias_cny": bias,
        "relative_bias": bias / mean_pred,
        "sum_ratio_observed_to_predicted": float(obs.sum() / pred.sum()),
        "mae_cny": mae,
        "rmse_cny": rmse,
        "pearson": pearson,
        "ols_slope": slope,
        "ols_intercept_cny": intercept,
        "predicted_sd_cny": pred_sd,
        "observed_sd_cny": obs_sd,
        "calibration_basis": "validation_observed_logs_only",
    }


# ---------------------------------------------------------------------------
# 2. 小池精确求解互证（20 / 100 / 500）
# ---------------------------------------------------------------------------
def small_pool_solver_table(
    frame: pd.DataFrame,
    cfg: Config,
    *,
    pool_sizes: list[int] | None = None,
    budgets: list[float] | None = None,
    seed_offset: int = 0,
    include_brute_force: bool = True,
    milp_time_limit_seconds: float | None = None,
    milp_relative_gap: float | None = None,
) -> pd.DataFrame:
    """在 20/100/500 人小池上跑 5 个求解器，并给出浮点原问题的穷举参照。

    回答 ``optimization.small_exact``：贪心/局部交换/分币 DP/MILP/LP 上界
    在同一池、同一预算上各自的预测目标、可行性、证明状态与真值。
    分币 DP 的精确性**只对分币整数化问题**成立；MILP 只有 ``gap=0`` 才可说最优。
    """
    data = _as_frame(frame)
    arrays = _arrays(data)
    if pool_sizes is None:
        pool_sizes = [int(x) for x in cfg.require("policy.optimization.small_exact.pool_sizes")]
    if budgets is None:
        budgets = _per_user_grid(cfg)
    time_limit = float(
        cfg.require("policy.optimization.large.milp_time_limit_seconds")
        if milp_time_limit_seconds is None else milp_time_limit_seconds
    )
    gap_tol = float(
        cfg.require("policy.optimization.large.milp_relative_gap_tolerance")
        if milp_relative_gap is None else milp_relative_gap
    )
    max_passes = int(cfg.require("policy.optimization.local_swap.max_passes"))
    candidate_limit = int(cfg.require("policy.optimization.local_swap.exchange_candidate_limit"))
    master_seed = _master_seed(cfg)

    rows: list[dict[str, Any]] = []
    for pool_size in pool_sizes:
        if pool_size <= 0:
            raise ValueError("池子大小必须为正")
        pool = _pool_frame(
            data, int(pool_size), master_seed,
            f"e.evidence.pool.{seed_offset}", int(pool_size),
        )
        pool_arrays = _arrays(pool)
        tau_hat = pool_arrays["tau_hat"]
        cost_hat = pool_arrays["cost_hat"]
        for per_user in budgets:
            budget = float(per_user) * len(pool)

            def add(solver: str, mask: BoolArray, *, exactness: str, status: str,
                    incumbent: float = float("nan"), bound: float = float("nan"),
                    gap: float = float("nan"), may_claim: bool = False,
                    metrics_override: dict[str, Any] | None = None) -> None:
                metrics = _mask_metrics(mask, pool_arrays, budget)
                if metrics_override is not None:
                    metrics.update(metrics_override)
                rows.append({
                    "pool_size": len(pool),
                    "per_user_budget_cny": float(per_user),
                    "budget_cny": budget,
                    "solver": solver,
                    "exactness": exactness,
                    **metrics,
                    "status": status,
                    "incumbent_cny": incumbent,
                    "bound_cny": bound,
                    "relative_gap": gap,
                    "may_claim_optimal": may_claim,
                    "seconds": float("nan"),
                })

            import time as _time

            started = _time.perf_counter()
            greedy = pol.greedy_by_ratio(tau_hat, cost_hat, budget)
            add("greedy", greedy.mask, exactness="heuristic", status="heuristic")
            rows[-1]["seconds"] = _time.perf_counter() - started

            started = _time.perf_counter()
            swap = pol.local_swap(
                greedy, tau_hat, cost_hat, budget,
                max_passes=max_passes, exchange_candidate_limit=candidate_limit,
            )
            add("greedy_local_swap", swap.mask, exactness="heuristic", status="heuristic")
            rows[-1]["seconds"] = _time.perf_counter() - started

            started = _time.perf_counter()
            cost_cents = to_cents_half_up(cost_hat)
            budget_cents = int(np.floor(budget * 100 + 1e-9))
            exact = pol.cent_exact_dp(
                to_signed_cents_half_up(tau_hat), cost_cents, budget_cents
            )
            add(
                "cent_exact_dp", exact.mask,
                exactness="exact_for_cent_integerized_problem",
                status="optimal_for_integerized_problem",
                incumbent=float(tau_hat[exact.mask].sum()),
                bound=float(tau_hat[exact.mask].sum()), gap=0.0, may_claim=False,
            )
            rows[-1]["seconds"] = _time.perf_counter() - started

            started = _time.perf_counter()
            milp = pol.milp_select(tau_hat, cost_hat, budget, time_limit, gap_tol)
            if milp.status == "time_limit_no_incumbent":
                # 时限内没有可行解：空 mask 的 0 花费/0 价值会被误读成
                # "合法但无收益的名单"，因此该行所有选中量写 NaN。
                add(
                    "milp", milp.selection.mask,
                    exactness="optimal_only_if_gap_zero",
                    status=milp.status, incumbent=float("nan"), bound=milp.bound,
                    gap=milp.relative_gap, may_claim=False,
                    metrics_override={
                        key: float("nan") for key in (
                            "n_selected", "predicted_value_cny", "predicted_cost_cny",
                            "within_budget_by_hat", "feasible_under_original_cost",
                            "true_value_per_user", "true_total_value_cny",
                            "actual_spend_cny", "within_budget_by_true",
                        )
                    },
                )
            else:
                add(
                    "milp", milp.selection.mask,
                    exactness="optimal_only_if_gap_zero",
                    status=milp.status, incumbent=milp.incumbent, bound=milp.bound,
                    gap=milp.relative_gap, may_claim=milp.may_claim_optimal,
                )
            rows[-1]["seconds"] = _time.perf_counter() - started

            lp_bound = pol.lp_upper_bound(tau_hat, cost_hat, budget)
            rows.append({
                "pool_size": len(pool),
                "per_user_budget_cny": float(per_user),
                "budget_cny": budget,
                "solver": "lp_relaxation",
                "exactness": "upper_bound_only",
                "n_selected": float("nan"),
                "predicted_value_cny": float(lp_bound),
                "predicted_cost_cny": float("nan"),
                "within_budget_by_hat": float("nan"),
                # LP 只有分数解上界，没有选人集合；写 False 会被误读成
                # "该策略不可行"，故与其余无选中量一致写 NaN。
                "feasible_under_original_cost": float("nan"),
                "status": "upper_bound_only",
                "incumbent_cny": float("nan"),
                "bound_cny": float(lp_bound),
                "relative_gap": float("nan"),
                "may_claim_optimal": False,
                "true_value_per_user": float("nan"),
                "true_total_value_cny": float("nan"),
                "actual_spend_cny": float("nan"),
                "within_budget_by_true": float("nan"),
                "seconds": float("nan"),
            })

            if include_brute_force and len(pool) <= 20:
                started = _time.perf_counter()
                brute_mask, brute_value = _brute_force_mask(tau_hat, cost_hat, budget)
                add(
                    "brute_force_float",
                    brute_mask,
                    exactness="float_problem_reference_only",
                    status="optimal_float_reference",
                    incumbent=brute_value, bound=brute_value, gap=0.0, may_claim=True,
                )
                rows[-1]["seconds"] = _time.perf_counter() - started

    table = pd.DataFrame(rows)
    if not set(POOL_COLUMNS).issubset(table.columns):
        raise ValueError("小池求解表列与契约不一致")
    failed = table.loc[table["status"] == "error"]
    if len(failed):
        raise RuntimeError(f"小池求解出现 error 状态：{failed[['pool_size', 'per_user_budget_cny', 'solver']].to_dict('records')}")
    return table.loc[:, list(POOL_COLUMNS)]


# ---------------------------------------------------------------------------
# 3. 桶宽收敛（pool 500，5 档宽度）
# ---------------------------------------------------------------------------
def bucket_convergence_table(
    frame: pd.DataFrame,
    cfg: Config,
    *,
    pool_size: int | None = None,
    budgets: list[float] | None = None,
    widths: list[float] | None = None,
    seed_offset: int = 0,
) -> pd.DataFrame:
    """在固定 500 人池上比较 5 档桶宽与分币精确解的预测目标差。

    回答 ``optimization.bucket_convergence``：桶宽变细时，近似 DP 的预测目标
    是否收敛到分币精确解，以及为恢复原成本可行性回退了多少件。
    **只出曲线，不设通过阈值**——阈值必须由协议评审在看曲线后确定。
    """
    import time as _time

    data = _as_frame(frame)
    if pool_size is None:
        pool_size = int(cfg.require("policy.optimization.bucket_convergence.pool_size"))
    if budgets is None:
        budgets = _per_user_grid(cfg)
    if widths is None:
        widths = [
            float(x)
            for x in cfg.require("policy.optimization.bucket_convergence.widths_cny")
        ]
    if not widths:
        raise ValueError("至少需要一个桶宽")
    pool = _pool_frame(
        data, int(pool_size), _master_seed(cfg),
        f"e.evidence.bucket.{seed_offset}", int(pool_size),
    )
    arrays = _arrays(pool)
    tau_hat, cost_hat = arrays["tau_hat"], arrays["cost_hat"]

    rows: list[dict[str, Any]] = []
    for per_user in budgets:
        budget = float(per_user) * len(pool)
        started = _time.perf_counter()
        exact = pol.cent_exact_dp(
            to_signed_cents_half_up(tau_hat),
            to_cents_half_up(cost_hat),
            int(np.floor(budget * 100 + 1e-9)),
        )
        exact_metrics = _mask_metrics(exact.mask, arrays, budget)
        exact_value = float(tau_hat[exact.mask].sum())
        rows.append({
            "pool_size": len(pool),
            "per_user_budget_cny": float(per_user),
            "budget_cny": budget,
            "method": "cent_exact_dp",
            "width_cny": float("nan"),
            **exact_metrics,
            "n_dropped_for_feasibility": 0,
            "gap_to_exact_cny": 0.0,
            "gap_per_user_cny": 0.0,
            "seconds": _time.perf_counter() - started,
        })

        for width in widths:
            started = _time.perf_counter()
            mask, dropped, _ = _bucket_dp_mask(tau_hat, cost_hat, budget, float(width))
            metrics = _mask_metrics(mask, arrays, budget)
            value = float(tau_hat[mask].sum())
            rows.append({
                "pool_size": len(pool),
                "per_user_budget_cny": float(per_user),
                "budget_cny": budget,
                "method": "bucket_dp",
                "width_cny": float(width),
                **metrics,
                "n_dropped_for_feasibility": int(dropped),
                "gap_to_exact_cny": exact_value - value,
                "gap_per_user_cny": (exact_value - value) / len(pool),
                "seconds": _time.perf_counter() - started,
            })

    table = pd.DataFrame(rows)
    if not set(BUCKET_COLUMNS).issubset(table.columns):
        raise ValueError("桶宽收敛表列与契约不一致")
    return table.loc[:, list(BUCKET_COLUMNS)]


# ---------------------------------------------------------------------------
# 4. 随机基线（每个数据集 × 预算 200 个种子）
# ---------------------------------------------------------------------------
def random_baseline_table(
    frame: pd.DataFrame,
    cfg: Config,
    *,
    budgets: list[float] | None = None,
    seeds: int | None = None,
    seed_offset: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """同一预算下的随机名单基线：200 个种子的真值、实际支出与超支概率。

    回答 ``random_baseline``：随机名单换一批人会波动多少，以及
    **按真值成本**核算时超预算的频率。分位数是名单间变异，不是均值的置信区间；
    均值的标准误另列 ``mean_se``。
    """
    data = _as_frame(frame)
    arrays = _arrays(data)
    tau_hat, cost_hat = arrays["tau_hat"], arrays["cost_hat"]
    if budgets is None:
        budgets = _per_user_grid(cfg)
    if seeds is None:
        seeds = int(cfg.require("policy.random_baseline.seeds_per_frozen_dataset_and_budget"))
    if seeds < 2:
        raise ValueError("随机基线至少需要 2 个种子，否则分位数与超支概率没有变异含义")
    quantiles = [float(q) for q in cfg.require("policy.random_baseline.quantiles")]
    master_seed = _master_seed(cfg)
    n_total = len(data)

    long_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for per_user in budgets:
        budget = float(per_user) * len(data)
        values: list[float] = []
        spends: list[float] = []
        predicted_costs: list[float] = []
        counts: list[int] = []
        overruns: list[float] = []
        stream = f"e.evidence.random.{seed_offset}.{float(per_user):.4f}"
        for seed in range(int(seeds)):
            rng = child_rng(master_seed, stream, int(seed))
            selection = pol.random_under_budget(tau_hat, cost_hat, budget, rng)
            metrics = _mask_metrics(selection.mask, arrays, budget)
            overrun = max(0.0, metrics["actual_spend_cny"] - (budget + pol.BUDGET_TOLERANCE))
            long_rows.append({
                "n_total": n_total,
                "per_user_budget_cny": float(per_user),
                "budget_cny": budget,
                "seed": int(seed),
                "n_selected": metrics["n_selected"],
                "predicted_cost_cny": metrics["predicted_cost_cny"],
                "within_budget_by_hat": metrics["within_budget_by_hat"],
                "true_value_per_user": metrics["true_value_per_user"],
                "true_total_value_cny": metrics["true_total_value_cny"],
                "actual_spend_cny": metrics["actual_spend_cny"],
                "within_budget_by_true": metrics["within_budget_by_true"],
                "overrun_cny": overrun,
            })
            values.append(metrics["true_value_per_user"])
            spends.append(metrics["actual_spend_cny"])
            predicted_costs.append(metrics["predicted_cost_cny"])
            counts.append(metrics["n_selected"])
            overruns.append(overrun)

        summary = pol.summarize_random_baseline(values, quantiles)
        quantile_map = summary["quantiles"]
        summary_rows.append({
            "n_total": n_total,
            "per_user_budget_cny": float(per_user),
            "budget_cny": budget,
            "seeds": int(seeds),
            "mean_true_value_per_user": summary["mean"],
            "sd_true_value_per_user": summary["sd"],
            "mean_se": summary["mean_se"],
            "q025": quantile_map[quantiles[0]],
            "q500": quantile_map[quantiles[1]],
            "q975": quantile_map[quantiles[2]],
            "overrun_probability": float(np.mean([x > 0 for x in overruns])),
            "mean_actual_spend_cny": float(np.mean(spends)),
            "max_overrun_cny": float(np.max(overruns)),
            "mean_predicted_cost_cny": float(np.mean(predicted_costs)),
            "mean_n_selected": float(np.mean(counts)),
            "interpretation": summary["interpretation"],
        })

    long_frame = pd.DataFrame(long_rows)
    summary_frame = pd.DataFrame(summary_rows)
    if not set(RANDOM_COLUMNS).issubset(long_frame.columns):
        raise ValueError("随机基线长表列与契约不一致")
    if not set(RANDOM_SUMMARY_COLUMNS).issubset(summary_frame.columns):
        raise ValueError("随机基线汇总表列与契约不一致")
    return long_frame.loc[:, list(RANDOM_COLUMNS)], summary_frame.loc[:, list(RANDOM_SUMMARY_COLUMNS)]


# ---------------------------------------------------------------------------
# 5. 学习误差与优化误差分解（pool 500）
# ---------------------------------------------------------------------------
def error_decomposition_table(
    frame: pd.DataFrame,
    cfg: Config,
    *,
    pool_size: int | None = None,
    budgets: list[float] | None = None,
    seed_offset: int = 0,
    truth_time_limit_seconds: float | None = None,
    truth_relative_gap: float | None = None,
) -> pd.DataFrame:
    r"""把真值 regret 拆成 learning / optimization 两项。

    回答 E 的核心问题"差距来自猜错 $\tau$ 还是没解到 $\hat\tau$ 的最优"：

    - ``oracle_under_hat`` = 分币整数化后的 **$\hat\tau$ 下精确解**；
    - ``truth_optimal`` = 真值 $\tau$ 下的分币精确解，另用 MILP 复核界与 gap；
    - ``actual`` = 贪心 / 局部交换（线上候选）。

    ``optimization_error`` **允许为负**：$\hat\tau$ 有噪声时，"$\hat\tau$ 下的最优"
    在真值下可能不如某个次优解；这不是 bug，identity 仍逐项闭合。
    """
    import time as _time

    data = _as_frame(frame)
    if pool_size is None:
        pool_size = int(cfg.require("policy.optimization.bucket_convergence.pool_size"))
    if budgets is None:
        budgets = _per_user_grid(cfg)
    time_limit = float(
        cfg.require("policy.optimization.large.milp_time_limit_seconds")
        if truth_time_limit_seconds is None else truth_time_limit_seconds
    )
    gap_tol = float(
        cfg.require("policy.optimization.large.milp_relative_gap_tolerance")
        if truth_relative_gap is None else truth_relative_gap
    )
    max_passes = int(cfg.require("policy.optimization.local_swap.max_passes"))
    candidate_limit = int(cfg.require("policy.optimization.local_swap.exchange_candidate_limit"))
    pool = _pool_frame(
        data, int(pool_size), _master_seed(cfg),
        f"e.evidence.bucket.{seed_offset}", int(pool_size),
    )
    arrays = _arrays(pool)
    tau_hat, cost_hat = arrays["tau_hat"], arrays["cost_hat"]
    tau_true, cost_true = arrays["tau_true"], arrays["cost_true"]
    cost_floor = float(cfg.require("policy.cost_model.cost_floor_cny"))
    truth_cost_for_milp = np.maximum(cost_true, cost_floor)

    rows: list[dict[str, Any]] = []
    for per_user in budgets:
        budget = float(per_user) * len(pool)
        started = _time.perf_counter()

        greedy = pol.greedy_by_ratio(tau_hat, cost_hat, budget)
        swap = pol.local_swap(
            greedy, tau_hat, cost_hat, budget,
            max_passes=max_passes, exchange_candidate_limit=candidate_limit,
        )
        oracle = pol.cent_exact_dp(
            to_signed_cents_half_up(tau_hat),
            to_cents_half_up(cost_hat),
            int(np.floor(budget * 100 + 1e-9)),
        )
        truth_exact = pol.cent_exact_dp(
            to_signed_cents_half_up(tau_true),
            to_cents_half_up(cost_true),
            int(np.floor(budget * 100 + 1e-9)),
        )
        # MILP 的共享校验要求成本严格为正；真值成本大量为 0，按冻结下界抬高后再解。
        # 真值精确解本身用 raw cost_true（分币 DP 允许 0），MILP 只用于复核界与 gap。
        truth_milp = pol.milp_select(
            tau_true, truth_cost_for_milp, budget, time_limit, gap_tol
        )
        oracle_value = pol.policy_value(oracle.mask, tau_true)
        truth_value = pol.policy_value(truth_exact.mask, tau_true)
        truth_feasible = bool(
            float(cost_true[truth_exact.mask].sum()) <= budget + pol.BUDGET_TOLERANCE
        )

        for solver_name, mask in (("greedy", greedy.mask), ("greedy_local_swap", swap.mask)):
            decomposition = pol.decompose_error(
                mask, oracle.mask, truth_exact.mask, tau_true
            )
            rows.append({
                "pool_size": len(pool),
                "per_user_budget_cny": float(per_user),
                "budget_cny": budget,
                "actual_solver": solver_name,
                "learning_error_cny_per_user": decomposition.learning_error,
                "optimization_error_cny_per_user": decomposition.optimization_error,
                "total_regret_cny_per_user": decomposition.total_regret,
                "identity_residual": (
                    decomposition.total_regret
                    - decomposition.learning_error
                    - decomposition.optimization_error
                ),
                "true_value_actual": pol.policy_value(mask, tau_true),
                "true_value_oracle_under_hat": oracle_value,
                "true_value_truth": truth_value,
                "oracle_exactness": "exact_for_cent_integerized_hat_problem",
                "truth_exactness": "exact_for_cent_integerized_raw_truth_problem",
                "truth_solver": "cent_exact_dp+MILP",
                "truth_milp_status": truth_milp.status,
                "truth_milp_relative_gap": truth_milp.relative_gap,
                "truth_milp_bound_cny": truth_milp.bound,
                "truth_milp_incumbent_cny": truth_milp.incumbent,
                "truth_milp_may_claim_optimal": truth_milp.may_claim_optimal,
                # MILP 求的是把 0 成本抬到 cost_floor 后的**收紧问题**：
                # 它的 bound/incumbent 不是 raw truth 问题的界，只能看 status/gap。
                "truth_milp_cost_basis": "truth_cost_floored_at_cost_floor_cny",
                "truth_milp_cost_floor_cny": cost_floor,
                "truth_feasible_under_original_cost": truth_feasible,
                "seconds": _time.perf_counter() - started,
            })
    table = pd.DataFrame(rows)
    if not set(DECOMPOSITION_COLUMNS).issubset(table.columns):
        raise ValueError("误差分解表列与契约不一致")
    if (table["truth_milp_status"] == "error").any():
        raise RuntimeError("真值 MILP 出现 error 状态，不能把该表当证据")
    return table.loc[:, list(DECOMPOSITION_COLUMNS)]


# ---------------------------------------------------------------------------
# 6. 规模扫描（1000 / 5000 / full_test）
# ---------------------------------------------------------------------------
def scale_table(
    frame: pd.DataFrame,
    cfg: Config,
    *,
    pool_sizes: list[Any] | None = None,
    budgets: list[float] | None = None,
    seed_offset: int = 0,
    include_milp: bool = True,
    milp_time_limit_seconds: float | None = None,
    milp_relative_gap: float | None = None,
) -> pd.DataFrame:
    """在 1000/5000/全测试集上跑贪心、局部交换、时间受限 MILP 与 LP 上界。

    回答 ``optimization.large``：规模变大后，启发式离 LP 上界多远、
    时间受限 MILP 是否还带 ``incumbent/bound/gap/status``。
    **LP 是上界不是可行解**；MILP 只有 ``gap=0`` 才允许说最优。
    """
    import time as _time

    data = _as_frame(frame)
    arrays = _arrays(data)
    tau_hat, cost_hat = arrays["tau_hat"], arrays["cost_hat"]
    if pool_sizes is None:
        pool_sizes = list(cfg.require("policy.optimization.large.pool_sizes"))
    if budgets is None:
        budgets = _per_user_grid(cfg)
    time_limit = float(
        cfg.require("policy.optimization.large.milp_time_limit_seconds")
        if milp_time_limit_seconds is None else milp_time_limit_seconds
    )
    gap_tol = float(
        cfg.require("policy.optimization.large.milp_relative_gap_tolerance")
        if milp_relative_gap is None else milp_relative_gap
    )
    max_passes = int(cfg.require("policy.optimization.local_swap.max_passes"))
    candidate_limit = int(cfg.require("policy.optimization.local_swap.exchange_candidate_limit"))
    master_seed = _master_seed(cfg)

    rows: list[dict[str, Any]] = []
    for spec in pool_sizes:
        full = spec in {"full_test", "full"} if isinstance(spec, str) else int(spec) >= len(data)
        pool_size = len(data) if full else int(spec)
        pool = _pool_frame(
            data, pool_size, master_seed,
            f"e.evidence.scale.{seed_offset}", pool_size,
        )
        pool_arrays = _arrays(pool)
        p_tau_hat, p_cost_hat = pool_arrays["tau_hat"], pool_arrays["cost_hat"]
        for per_user in budgets:
            budget = float(per_user) * len(pool)
            lp_bound = pol.lp_upper_bound(p_tau_hat, p_cost_hat, budget)

            def append_row(solver: str, metrics: dict[str, Any], *, status: str,
                           incumbent: float = float("nan"), bound: float = float("nan"),
                           gap: float = float("nan"), may_claim: bool = False,
                           feasible: bool | None = None, seconds: float = float("nan")) -> None:
                rows.append({
                    "pool_size": len(pool),
                    "pool_is_full_test": bool(full),
                    "per_user_budget_cny": float(per_user),
                    "budget_cny": budget,
                    "solver": solver,
                    **metrics,
                    "feasible_under_original_cost": (
                        metrics["feasible_under_original_cost"] if feasible is None else bool(feasible)
                    ),
                    "status": status,
                    "incumbent_cny": incumbent,
                    "bound_cny": bound,
                    "relative_gap": gap,
                    "may_claim_optimal": bool(may_claim),
                    "lp_upper_bound_cny": float(lp_bound),
                    "incumbent_to_lp_ratio": (
                        float(incumbent / lp_bound)
                        if np.isfinite(incumbent) and lp_bound > 0 else float("nan")
                    ),
                    "seconds": seconds,
                })

            started = _time.perf_counter()
            greedy = pol.greedy_by_ratio(p_tau_hat, p_cost_hat, budget)
            elapsed = _time.perf_counter() - started
            append_row(
                "greedy", _mask_metrics(greedy.mask, pool_arrays, budget),
                status="heuristic", seconds=elapsed,
            )

            started = _time.perf_counter()
            swap = pol.local_swap(
                greedy, p_tau_hat, p_cost_hat, budget,
                max_passes=max_passes, exchange_candidate_limit=candidate_limit,
            )
            elapsed = _time.perf_counter() - started
            append_row(
                "greedy_local_swap", _mask_metrics(swap.mask, pool_arrays, budget),
                status="heuristic", seconds=elapsed,
            )

            if include_milp:
                started = _time.perf_counter()
                milp = pol.milp_select(p_tau_hat, p_cost_hat, budget, time_limit, gap_tol)
                elapsed = _time.perf_counter() - started
                if milp.status == "time_limit_no_incumbent":
                    # 时限内没有可行解：空 mask 的 0 花费/0 价值会被误读成
                    # "合法但无收益的名单"，因此该行所有选中量写 NaN。
                    append_row(
                        "time_limited_milp",
                        {
                            "n_selected": float("nan"),
                            "predicted_value_cny": float("nan"),
                            "predicted_cost_cny": float("nan"),
                            "within_budget_by_hat": float("nan"),
                            "feasible_under_original_cost": float("nan"),
                            "true_value_per_user": float("nan"),
                            "true_total_value_cny": float("nan"),
                            "actual_spend_cny": float("nan"),
                            "within_budget_by_true": float("nan"),
                        },
                        status=milp.status, incumbent=float("nan"), bound=milp.bound,
                        gap=milp.relative_gap, may_claim=False, seconds=elapsed,
                    )
                else:
                    append_row(
                        "time_limited_milp", _mask_metrics(milp.selection.mask, pool_arrays, budget),
                        status=milp.status, incumbent=milp.incumbent, bound=milp.bound,
                        gap=milp.relative_gap, may_claim=milp.may_claim_optimal,
                        seconds=elapsed,
                    )

            rows.append({
                "pool_size": len(pool),
                "pool_is_full_test": bool(full),
                "per_user_budget_cny": float(per_user),
                "budget_cny": budget,
                "solver": "lp_relaxation",
                "n_selected": float("nan"),
                "predicted_value_cny": float(lp_bound),
                "predicted_cost_cny": float("nan"),
                "within_budget_by_hat": float("nan"),
                # LP 只有分数解上界，没有选人集合；写 False 会被误读成
                # "该策略不可行"，故与其余无选中量一致写 NaN。
                "feasible_under_original_cost": float("nan"),
                "status": "upper_bound_only",
                "incumbent_cny": float("nan"),
                "bound_cny": float(lp_bound),
                "relative_gap": float("nan"),
                "may_claim_optimal": False,
                "lp_upper_bound_cny": float(lp_bound),
                "incumbent_to_lp_ratio": float("nan"),
                "true_value_per_user": float("nan"),
                "true_total_value_cny": float("nan"),
                "actual_spend_cny": float("nan"),
                "within_budget_by_true": float("nan"),
                "seconds": float("nan"),
            })
    table = pd.DataFrame(rows)
    if not set(SCALE_COLUMNS).issubset(table.columns):
        raise ValueError("规模扫描表列与契约不一致")
    failed = table.loc[table["status"] == "error"]
    if len(failed):
        raise RuntimeError(f"规模扫描出现 error 状态：{failed[['pool_size', 'per_user_budget_cny', 'solver']].to_dict('records')}")
    return table.loc[:, list(SCALE_COLUMNS)]


# ---------------------------------------------------------------------------
# 7. 三种预算口径的保守比较
# ---------------------------------------------------------------------------
def conservative_comparison_table(
    frame: pd.DataFrame,
    cfg: Config,
    *,
    budgets: list[float] | None = None,
    seeds: int | None = None,
    seed_offset: int = 0,
) -> pd.DataFrame:
    """在同一预算下比较 expected / buffered / worst-case face 三种口径。

    回答 ``policy.budget.conservative_comparison``：
    缓冲口径把可用预算放大 ``multiplier``（不是硬上限）；面额口径按
    ``floor(B / face)`` 限人数，保证券面支出不超预算。报告每口径的
    实际支出区间与**按真值成本**的超预算概率。

    真值价值以 DGP 的 ``tau_true`` 为审计值；``observed_value`` 要用观测结局，
    属 F 阶段 OPE，本表只标状态、不伪造数字。
    """
    data = _as_frame(frame)
    arrays = _arrays(data)
    tau_hat, cost_hat = arrays["tau_hat"], arrays["cost_hat"]
    tau_true = arrays["tau_true"]
    face = float(cfg.require("policy.face_value_cny"))
    multiplier = float(
        cfg.require("policy.budget.conservative_comparison.modes.buffered_expected.multiplier")
    )
    face_cost = float(
        cfg.require("policy.budget.conservative_comparison.modes.worst_case_face.cost_per_user_cny")
    )
    if abs(face_cost - face) > 1e-9:
        raise ValueError("面额口径的每人成本与 policy.face_value_cny 不一致")
    if budgets is None:
        budgets = _per_user_grid(cfg)
    if seeds is None:
        seeds = int(
            cfg.require(
                "policy.budget.conservative_comparison.random_seeds_per_dataset_budget_mode"
            )
        )
    if int(seeds) < 2:
        raise ValueError("保守比较至少需要 2 个随机种子，否则超支概率没有变异含义")
    max_passes = int(cfg.require("policy.optimization.local_swap.max_passes"))
    candidate_limit = int(cfg.require("policy.optimization.local_swap.exchange_candidate_limit"))
    master_seed = _master_seed(cfg)
    n = len(data)

    rows: list[dict[str, Any]] = []
    for per_user in budgets:
        expected = float(per_user) * n
        mode_specs = {
            "expected": (expected, "cost_hat"),
            "buffered_expected": (expected * multiplier, "cost_hat"),
            "worst_case_face": (expected, "face"),
        }
        for mode, (mode_budget, cost_basis) in mode_specs.items():
            selection_cost = np.full(n, face, dtype=np.float64) if cost_basis == "face" else cost_hat
            for policy_name in ("random_same_budget", "greedy_incremental_profit_per_cost",
                                "greedy_local_swap"):
                sweep = int(seeds) if policy_name == "random_same_budget" else 1
                spends: list[float] = []
                values: list[float] = []
                predicted_costs: list[float] = []
                counts: list[int] = []
                for seed in range(sweep):
                    rng = child_rng(
                        master_seed,
                        f"e.evidence.conservative.{seed_offset}.{mode}.{float(per_user):.4f}",
                        int(seed),
                    )
                    if policy_name == "random_same_budget":
                        selection = pol.random_under_budget(
                            tau_hat, selection_cost, mode_budget, rng
                        )
                    elif policy_name == "greedy_incremental_profit_per_cost":
                        selection = pol.greedy_by_ratio(
                            tau_hat, selection_cost, mode_budget
                        )
                    else:
                        greedy = pol.greedy_by_ratio(tau_hat, selection_cost, mode_budget)
                        selection = pol.local_swap(
                            greedy, tau_hat, selection_cost, mode_budget,
                            max_passes=max_passes, exchange_candidate_limit=candidate_limit,
                        )
                    mask = selection.mask
                    spends.append(float(arrays["cost_true"][mask].sum()))
                    values.append(float(tau_true[mask].sum()) / n)
                    predicted_costs.append(float(cost_hat[mask].sum()))
                    counts.append(int(mask.sum()))

                true_values = np.asarray(values, dtype=np.float64)
                spend_array = np.asarray(spends, dtype=np.float64)
                overrun = spend_array > mode_budget + pol.BUDGET_TOLERANCE
                overrun_expected = spend_array > expected + pol.BUDGET_TOLERANCE
                rows.append({
                    "n_total": n,
                    "mode": mode,
                    "policy": policy_name,
                    "per_user_budget_cny": float(per_user),
                    "budget_cny": expected,
                    "mode_budget_cny": float(mode_budget),
                    "seeds": sweep,
                    "selected_count_mean": float(np.mean(counts)),
                    "predicted_cost_mean": float(np.mean(predicted_costs)),
                    "actual_spend_mean": float(spend_array.mean()),
                    "actual_spend_q025": float(np.quantile(spend_array, 0.025)),
                    "actual_spend_q975": float(np.quantile(spend_array, 0.975)),
                    "overrun_probability": float(overrun.mean()),
                    "overrun_vs_expected_probability": float(overrun_expected.mean()),
                    "true_value_per_user_mean": float(true_values.mean()),
                    "true_total_value_cny_mean": float(true_values.mean()) * n,
                    "audited_value_cny_mean": float(true_values.mean()) * n,
                    "evidence_basis": (
                        "random_sweep" if policy_name == "random_same_budget"
                        else "single_deterministic_solution"
                    ),
                    "value_basis": "dgp_truth_tau",
                    "observed_value_status": "deferred_to_F_ope",
                })
    table = pd.DataFrame(rows)
    if not set(CONSERVATIVE_COLUMNS).issubset(table.columns):
        raise ValueError("保守比较表列与契约不一致")
    return table.loc[:, list(CONSERVATIVE_COLUMNS)]


__all__ = [
    "BUCKET_COLUMNS",
    "CONSERVATIVE_COLUMNS",
    "DECOMPOSITION_COLUMNS",
    "POOL_COLUMNS",
    "RANDOM_COLUMNS",
    "RANDOM_SUMMARY_COLUMNS",
    "SCALE_COLUMNS",
    "SOLVERS",
    "bucket_convergence_table",
    "calibrate_cost_predictions",
    "conservative_comparison_table",
    "error_decomposition_table",
    "random_baseline_table",
    "scale_table",
    "small_pool_solver_table",
    "to_cents_half_up",
    "to_signed_cents_half_up",
]
