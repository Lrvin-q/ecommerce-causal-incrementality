"""D03 正式 R 的报告层聚合：选模、校准、按模型配对的策略比较与口径合规。

回答哪个问题
------------
D03 正式 R 产出两张逐 rep 表（模型对照、按模型配对的策略网格）。本模块只做
**从这两张表可复算的聚合**，不重跑模型、不读逐用户表、不碰真值生成：

1. 选模频率与排名（``selection_frequency``）；
2. 各模型在测试集上的校准（``calibration_summary``）；
3. 各策略的真值价值（``policy_value_summary``）；
4. **同一 rep、同一批用户、同一预算**下的配对差（``paired_policy_difference``）；
5. 真值口径的事后最优差距（``oracle_regret_summary``）；
6. 预测成本与真实成本两个口径的合规率（``compliance_summary``）。

为什么必须按模型配对
--------------------
20 rep 诊断的首版策略网格只用了每个 rep 被选中的模型，聚合后得出"business 规则
全面胜过 greedy"；按模型配对重跑后，``causal_forest`` 被选中的 4 个 rep 里
greedy 在每个预算档都胜过 business。聚合结论被选模频率（constant 9/20）主导。
因此本模块所有策略比较都按 ``(rep_id, model, per_user_budget_cny)`` 做宽表配对，
**分组聚合只允许在配对差之上做**；``chosen_only`` 只是线上口径的子集，不是"全部模型"
的替代。
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from causal_growth.estimate.v3_models import MODEL_NAMES
from causal_growth.policy.v3_policy_grid import POLICIES

PAIR_KEYS: tuple[str, ...] = ("rep_id", "model", "per_user_budget_cny")

#: ``all_coupon_unconstrained_reference`` 不受预算约束，是参照不是可执行策略；
#: 把它算进"事后最优"会虚增所有策略的后悔值。
NON_FEASIBLE_REFERENCE_POLICIES: tuple[str, ...] = (
    "all_coupon_unconstrained_reference",
)

SELECTION_COLUMNS: tuple[str, ...] = (
    "model", "times_chosen", "share_chosen", "mean_rank", "median_selection_score",
)

CALIBRATION_COLUMNS: tuple[str, ...] = (
    "model", "scope", "n_reps", "mean_bias_cny", "se_bias_cny",
    "median_relative_bias", "max_abs_relative_bias",
    "median_calibration_slope", "median_pearson_r", "median_rmse",
)

POLICY_VALUE_COLUMNS: tuple[str, ...] = (
    "model", "per_user_budget_cny", "policy", "n_reps",
    "mean_true_value_per_user", "sd_true_value_per_user", "se_true_value_per_user",
    "mean_n_selected", "mean_predicted_value",
)

PAIRED_DIFF_COLUMNS: tuple[str, ...] = (
    "model", "per_user_budget_cny", "policy", "baseline", "n_pairs",
    "mean_diff_cny_per_user", "sd_diff", "se_diff", "t_stat",
    "wins", "losses", "ties",
)

ORACLE_COLUMNS: tuple[str, ...] = (
    "model", "per_user_budget_cny", "policy", "n_reps",
    "mean_regret_cny_per_user", "se_regret", "share_optimal",
)

COMPLIANCE_COLUMNS: tuple[str, ...] = (
    "model", "per_user_budget_cny", "policy", "n_reps",
    "share_within_budget_by_hat", "share_within_budget_by_true",
    "mean_spend_to_budget_ratio", "max_spend_to_budget_ratio",
)


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} 缺少列：{missing}")


def _require_unique(frame: pd.DataFrame, keys: Sequence[str], name: str) -> None:
    duplicated = frame.duplicated(list(keys), keep=False)
    if duplicated.any():
        sample = frame.loc[duplicated, list(keys)].head(5).to_dict("records")
        raise ValueError(f"{name} 的键 {list(keys)} 不唯一，配对会失真：{sample}")


def _pick(frame: pd.DataFrame, chosen_only: bool) -> pd.DataFrame:
    if not chosen_only:
        return frame
    if "chosen" not in frame.columns:
        raise ValueError("chosen_only=True 但表里没有 chosen 列")
    picked = frame.loc[frame["chosen"].astype(bool)].copy()
    if picked.empty:
        raise ValueError("chosen_only=True 但没有任何 chosen 行")
    return picked


def _se(values: pd.Series) -> float:
    clean = values.dropna().to_numpy(dtype=np.float64)
    if clean.size < 2:
        return float("nan")
    return float(clean.std(ddof=1) / np.sqrt(clean.size))


def selection_frequency(per_rep: pd.DataFrame) -> pd.DataFrame:
    """每个模型被选中的次数、占比与排名；分母是 rep 数，不是模型-行数。"""
    _require_columns(per_rep, ("rep_id", "model", "chosen", "rank", "selection_score"), "per_rep")
    _require_unique(per_rep, ("rep_id", "model"), "per_rep")
    if not per_rep["chosen"].isin([0, 1, True, False]).all():
        raise ValueError("chosen 必须是 0/1 或布尔")
    counts = per_rep.groupby("rep_id")["chosen"].sum()
    if not counts.eq(1).all():
        raise ValueError("每个 rep 必须恰好有一个 chosen 模型")
    stats = per_rep.groupby("model").agg(
        times_chosen=("chosen", "sum"),
        mean_rank=("rank", "mean"),
        median_selection_score=("selection_score", "median"),
    )
    stats["share_chosen"] = stats["times_chosen"] / int(per_rep["rep_id"].nunique())
    stats = stats.reindex(list(MODEL_NAMES)).dropna(how="all").reset_index()
    stats["times_chosen"] = stats["times_chosen"].astype(int)
    return stats.loc[:, list(SELECTION_COLUMNS)].sort_values(
        ["times_chosen", "model"], ascending=[False, True]
    ).reset_index(drop=True)


def calibration_summary(per_rep: pd.DataFrame, *, chosen_only: bool = False) -> pd.DataFrame:
    """按模型汇总测试集校准；chosen_only 给线上口径，all 给方法对照。"""
    _require_columns(
        per_rep,
        ("rep_id", "model", "chosen", "bias_mean", "relative_bias",
         "calibration_slope", "pearson_r", "rmse"),
        "per_rep",
    )
    data = _pick(per_rep, chosen_only)
    scope = "chosen_only" if chosen_only else "all_models"
    rows: list[dict[str, object]] = []
    for model, group in data.groupby("model", sort=False):
        rows.append({
            "model": str(model),
            "scope": scope,
            "n_reps": int(group["rep_id"].nunique()),
            "mean_bias_cny": float(group["bias_mean"].mean()),
            "se_bias_cny": _se(group["bias_mean"]),
            "median_relative_bias": float(group["relative_bias"].median()),
            "max_abs_relative_bias": float(group["relative_bias"].abs().max()),
            "median_calibration_slope": float(group["calibration_slope"].median()),
            "median_pearson_r": float(group["pearson_r"].median()),
            "median_rmse": float(group["rmse"].median()),
        })
    table = pd.DataFrame(rows)
    order = {name: index for index, name in enumerate(MODEL_NAMES)}
    table["_order"] = table["model"].map(order).fillna(len(order))
    return table.sort_values(["_order", "model"]).drop(columns="_order").loc[
        :, list(CALIBRATION_COLUMNS)
    ].reset_index(drop=True)


def policy_value_summary(grid: pd.DataFrame, *, chosen_only: bool = False) -> pd.DataFrame:
    """按模型×预算×策略汇总真值价值；每个单元的重数是 rep 数。"""
    _require_columns(
        grid,
        ("rep_id", "model", "chosen", "per_user_budget_cny", "policy",
         "true_value_per_user", "n_selected", "predicted_value"),
        "policy_grid",
    )
    data = _pick(grid, chosen_only)
    rows: list[dict[str, object]] = []
    for (model, budget, policy), group in data.groupby(
        ["model", "per_user_budget_cny", "policy"], sort=True
    ):
        values = group["true_value_per_user"].astype(np.float64)
        rows.append({
            "model": str(model),
            "per_user_budget_cny": float(budget),
            "policy": str(policy),
            "n_reps": int(group["rep_id"].nunique()),
            "mean_true_value_per_user": float(values.mean()),
            "sd_true_value_per_user": float(values.std(ddof=1)) if len(values) > 1 else float("nan"),
            "se_true_value_per_user": _se(values),
            "mean_n_selected": float(group["n_selected"].mean()),
            "mean_predicted_value": float(group["predicted_value"].mean()),
        })
    return pd.DataFrame(rows).loc[:, list(POLICY_VALUE_COLUMNS)].reset_index(drop=True)


def _paired_wide(grid: pd.DataFrame, chosen_only: bool) -> pd.DataFrame:
    data = _pick(grid, chosen_only)
    _require_unique(data, (*PAIR_KEYS, "policy"), "policy_grid")
    wide = data.pivot(index=list(PAIR_KEYS), columns="policy", values="true_value_per_user")
    if wide.isna().any().any():
        missing = wide.isna().sum()
        raise ValueError(f"策略网格有缺格，不能配对：{missing[missing > 0].to_dict()}")
    return wide


def paired_policy_difference(
    grid: pd.DataFrame,
    baseline: str,
    *,
    chosen_only: bool = False,
) -> pd.DataFrame:
    """同一 rep、同一模型、同一预算下，每个策略减 baseline 的配对差。

    只允许在配对差之上聚合；跨 reps 求均值时同时给 SE 与胜负平计数。
    这正是 AGENTS §12.6 的落点：不按模型配对会把选模频率当成策略优劣。
    """
    wide = _paired_wide(grid, chosen_only)
    if baseline not in wide.columns:
        raise ValueError(f"baseline {baseline!r} 不在策略网格里")
    rows: list[dict[str, object]] = []
    for policy in wide.columns:
        diff = (wide[policy] - wide[baseline]).dropna()
        if diff.empty:
            continue
        for (model, budget), group in diff.groupby(level=["model", "per_user_budget_cny"]):
            values = group.to_numpy(dtype=np.float64)
            mean = float(values.mean())
            se = _se(group)
            rows.append({
                "model": str(model),
                "per_user_budget_cny": float(budget),
                "policy": str(policy),
                "baseline": str(baseline),
                "n_pairs": int(values.size),
                "mean_diff_cny_per_user": mean,
                "sd_diff": float(values.std(ddof=1)) if values.size > 1 else float("nan"),
                "se_diff": se,
                "t_stat": mean / se if se and np.isfinite(se) and se > 0 else float("nan"),
                "wins": int((values > 0).sum()),
                "losses": int((values < 0).sum()),
                "ties": int((values == 0).sum()),
            })
    return pd.DataFrame(rows).loc[:, list(PAIRED_DIFF_COLUMNS)].reset_index(drop=True)


def oracle_regret_summary(grid: pd.DataFrame, *, chosen_only: bool = False) -> pd.DataFrame:
    """每个 rep×模型×预算内的事后最优（按真值），给出各策略的差距与夺魁频率。

    事后最优只在**受预算约束**的策略里取；``all_coupon_unconstrained_reference``
    是参照不是策略，既不参与比较也不出现在结果里。
    """
    wide = _paired_wide(grid, chosen_only)
    feasible = [
        column for column in wide.columns
        if column not in NON_FEASIBLE_REFERENCE_POLICIES
    ]
    if not feasible:
        raise ValueError("策略网格里没有可执行的预算约束策略，无法定义事后最优")
    best = wide[feasible].max(axis=1)
    rows: list[dict[str, object]] = []
    for policy in feasible:
        regret = best - wide[policy]
        for (model, budget), group in regret.groupby(level=["model", "per_user_budget_cny"]):
            values = group.to_numpy(dtype=np.float64)
            rows.append({
                "model": str(model),
                "per_user_budget_cny": float(budget),
                "policy": str(policy),
                "n_reps": int(values.size),
                "mean_regret_cny_per_user": float(values.mean()),
                "se_regret": _se(group),
                "share_optimal": float((values <= 1e-12).mean()),
            })
    return pd.DataFrame(rows).loc[:, list(ORACLE_COLUMNS)].reset_index(drop=True)


def compliance_summary(grid: pd.DataFrame, *, chosen_only: bool = False) -> pd.DataFrame:
    """预测成本与真实成本两个口径的预算合规率；两者不可互相替代。"""
    _require_columns(
        grid,
        ("rep_id", "model", "chosen", "per_user_budget_cny", "policy",
         "budget_cny", "actual_spend_cny", "within_budget_by_hat",
         "within_budget_by_true"),
        "policy_grid",
    )
    data = _pick(grid, chosen_only).copy()
    data["spend_to_budget"] = (
        data["actual_spend_cny"].astype(np.float64)
        / data["budget_cny"].astype(np.float64)
    )
    rows: list[dict[str, object]] = []
    for (model, budget, policy), group in data.groupby(
        ["model", "per_user_budget_cny", "policy"], sort=True
    ):
        rows.append({
            "model": str(model),
            "per_user_budget_cny": float(budget),
            "policy": str(policy),
            "n_reps": int(group["rep_id"].nunique()),
            "share_within_budget_by_hat": float(group["within_budget_by_hat"].mean()),
            "share_within_budget_by_true": float(group["within_budget_by_true"].mean()),
            "mean_spend_to_budget_ratio": float(group["spend_to_budget"].mean()),
            "max_spend_to_budget_ratio": float(group["spend_to_budget"].max()),
        })
    return pd.DataFrame(rows).loc[:, list(COMPLIANCE_COLUMNS)].reset_index(drop=True)


def require_formal_tables(
    per_rep: pd.DataFrame,
    grid: pd.DataFrame,
    *,
    expected_reps: int,
    expected_models: Sequence[str] = MODEL_NAMES,
    expected_policies: Sequence[str] = POLICIES,
    expected_budgets: Sequence[float] | None = None,
) -> None:
    """正式报告入口的覆盖校验；缺一个 rep/模型/策略/预算都直接抛错。"""
    rep_ids = sorted(int(value) for value in per_rep["rep_id"].unique())
    if rep_ids != list(range(expected_reps)):
        raise ValueError(f"per_rep 的 rep 覆盖不是 0..{expected_reps - 1}")
    if set(per_rep["model"].unique()) != set(expected_models):
        raise ValueError("per_rep 的模型集合与协议不一致")
    if not per_rep.groupby("rep_id").size().eq(len(expected_models)).all():
        raise ValueError("每个 rep 的模型行数不一致")
    chosen = per_rep.groupby("rep_id")["chosen"].sum()
    if not chosen.eq(1).all():
        raise ValueError("每个 rep 必须恰好一个 chosen")

    if "chosen" not in grid.columns:
        raise ValueError("网格缺 chosen 列，无法核对线上口径")
    if not grid["chosen"].isin([0, 1, True, False]).all():
        raise ValueError("网格的 chosen 必须是 0/1 或布尔")
    grid_reps = sorted(int(value) for value in grid["rep_id"].unique())
    if grid_reps != list(range(expected_reps)):
        raise ValueError(f"网格的 rep 覆盖不是 0..{expected_reps - 1}")
    budgets = sorted(float(value) for value in grid["per_user_budget_cny"].unique())
    expected_budgets_list = sorted(float(value) for value in expected_budgets or budgets)
    if budgets != expected_budgets_list:
        raise ValueError(f"预算档不一致：{budgets} != {expected_budgets_list}")
    chosen_models = per_rep.loc[per_rep["chosen"].astype(bool)].set_index("rep_id")["model"]
    chosen_grid = grid.loc[grid["chosen"].astype(bool)]
    for rep_id, model in chosen_models.items():
        block = chosen_grid.loc[chosen_grid["rep_id"] == rep_id]
        if set(block["model"].astype(str)) != {str(model)}:
            raise ValueError(f"rep {rep_id} 的网格 chosen 行不属于 {model}")
        expected_rows = len(expected_budgets_list) * len(expected_policies)
        if len(block) != expected_rows:
            raise ValueError(
                f"rep {rep_id} 的网格 chosen 行数 {len(block)} != {expected_rows}"
            )
    if len(chosen_grid) != expected_reps * len(expected_budgets_list) * len(expected_policies):
        raise ValueError("网格的 chosen 行总数不等于 rep×预算×策略")

    if set(grid["model"].unique()) != set(expected_models):
        raise ValueError("网格的模型集合与协议不一致")
    if set(grid["policy"].unique()) != set(expected_policies):
        raise ValueError("网格的策略集合与协议不一致")
    per_cell = grid.groupby(list(PAIR_KEYS)).size()
    if not per_cell.eq(len(expected_policies)).all():
        raise ValueError("每个 rep×模型×预算的策略数不一致")
    if len(per_cell) != expected_reps * len(expected_models) * len(budgets):
        raise ValueError("网格的 rep×模型×预算单元数不完整")
    _require_unique(grid, (*PAIR_KEYS, "policy"), "policy_grid")
    if grid["chosen"].groupby([grid["rep_id"], grid["model"]]).first().groupby(level=0).sum().ne(1).any():
        raise ValueError("每个 rep 的 chosen 没有恰好覆盖一个模型的整张网格")
