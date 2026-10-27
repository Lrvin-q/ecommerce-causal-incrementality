from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth.policy import v3_policy as pol
from causal_growth.policy import v3_policy_evidence as ev
from causal_growth.v3_config import load_v3_protocol


@pytest.fixture(scope="module")
def cfg():
    return load_v3_protocol().config


def _frame(n: int = 40, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    tau_hat = rng.normal(0.4, 0.6, n)
    cost_hat = np.maximum(rng.uniform(0.05, 4.0, n), 1e-3)
    tau_true = tau_hat + rng.normal(0.0, 0.25, n)
    cost_true = np.where(rng.random(n) < 0.35, rng.uniform(0.0, 8.0, n), 0.0)
    return pd.DataFrame({
        "user_id": np.arange(n, dtype=np.int64) * 3 + 1,
        "is_new": rng.integers(0, 2, n),
        "cart_value": np.round(rng.lognormal(3.5, 0.7, n), 2),
        "purchase_propensity": rng.uniform(0, 1, n),
        "predicted_profit": rng.normal(0.5, 2.0, n),
        "tau_hat": tau_hat,
        "cost_hat": cost_hat,
        "tau_true": tau_true,
        "cost_true": cost_true,
    })


def _poison(frame: pd.DataFrame) -> pd.DataFrame:
    poisoned = frame.copy()
    poisoned["tau_true"] = poisoned["tau_true"] * 2.0 + 5.0
    poisoned["cost_true"] = poisoned["cost_true"] * 3.0 + 1.0
    return poisoned


def _selection_columns(table: pd.DataFrame) -> list[str]:
    """选人相关列：不含真值评估列、耗时列。"""
    truth_prefixes = ("true_", "actual_spend", "within_budget_by_true")
    return [
        column for column in table.columns
        if not column.startswith(truth_prefixes) and column != "seconds"
    ]


def test_to_cents_half_up_uses_decimal_rule() -> None:
    amounts = np.array([1.005, 1.004, 0.005, 0.004, 0.0])
    assert ev.to_cents_half_up(amounts).tolist() == [101, 100, 1, 0, 0]
    signed = ev.to_signed_cents_half_up(np.array([-1.005, 1.005, 0.0]))
    assert signed.tolist() == [-101, 101, 0]
    with pytest.raises(ValueError):
        ev.to_cents_half_up(np.array([0.0, np.nan]))
    with pytest.raises(ValueError):
        ev.to_cents_half_up(np.array([-0.01]))


def test_calibrate_cost_predictions_reports_degenerate_correlation() -> None:
    report = ev.calibrate_cost_predictions(
        np.array([1.0, 2.0, 3.0]), np.array([2.0, 2.0, 2.0])
    )
    assert report["n"] == 3
    assert report["bias_cny"] == pytest.approx(0.0)
    assert report["sum_ratio_observed_to_predicted"] == pytest.approx(1.0)
    assert report["mae_cny"] == pytest.approx(2.0 / 3.0)
    assert report["rmse_cny"] == pytest.approx(np.sqrt(2.0 / 3.0))
    assert np.isnan(report["pearson"])
    assert np.isnan(report["ols_slope"])
    assert report["calibration_basis"] == "validation_observed_logs_only"


def test_lp_upper_bound_handles_free_items() -> None:
    # 成本校验要求严格为正；1e-12 在预算容差内，按"免费券"处理，不能除零。
    bound = pol.lp_upper_bound(
        np.array([5.0, 7.0, 1.0]), np.array([1e-12, 10.0, 10.0]), 5.0
    )
    assert np.isfinite(bound)
    assert bound == pytest.approx(5.0 + 7.0 * 0.5)


def test_small_pool_solver_table_contract_and_dominance(cfg) -> None:
    frame = _frame()
    table = ev.small_pool_solver_table(
        frame, cfg, pool_sizes=[20], budgets=[0.04, 0.2], include_brute_force=True
    )
    assert tuple(table.columns) == ev.POOL_COLUMNS
    assert len(table) == 2 * 6  # 5 个契约求解器 + 浮点穷举参照

    for _, group in table.groupby("per_user_budget_cny"):
        by_solver = group.set_index("solver")
        assert by_solver.loc["greedy_local_swap", "predicted_value_cny"] >= (
            by_solver.loc["greedy", "predicted_value_cny"] - 1e-9
        )
        milp = by_solver.loc["milp"]
        assert milp["bound_cny"] >= milp["incumbent_cny"] - 1e-9
        if milp["status"] == "optimal":
            assert milp["incumbent_cny"] >= by_solver.loc["greedy", "predicted_value_cny"] - 1e-9
        assert by_solver.loc["cent_exact_dp", "exactness"] == (
            "exact_for_cent_integerized_problem"
        )
        assert not bool(by_solver.loc["cent_exact_dp", "may_claim_optimal"])
        brute = by_solver.loc["brute_force_float"]
        if by_solver.loc["cent_exact_dp", "feasible_under_original_cost"]:
            assert brute["incumbent_cny"] >= (
                by_solver.loc["cent_exact_dp", "incumbent_cny"] - 1e-9
            )
        lp = by_solver.loc["lp_relaxation"]
        assert lp["predicted_value_cny"] >= brute["incumbent_cny"] - 1e-9


def test_small_pool_solver_table_does_not_read_truth(cfg) -> None:
    frame = _frame()
    clean = ev.small_pool_solver_table(
        frame, cfg, pool_sizes=[20], budgets=[0.04], include_brute_force=False
    )
    poisoned = ev.small_pool_solver_table(
        _poison(frame), cfg, pool_sizes=[20], budgets=[0.04], include_brute_force=False
    )
    columns = _selection_columns(clean)
    pd.testing.assert_frame_equal(clean.loc[:, columns], poisoned.loc[:, columns])


def test_bucket_convergence_repairs_infeasible_masks_and_keeps_truth_isolated(cfg) -> None:
    frame = _frame()
    table = ev.bucket_convergence_table(
        frame, cfg, pool_size=20, budgets=[0.04, 0.2], widths=[0.5, 0.1, 0.01]
    )
    assert tuple(table.columns) == ev.BUCKET_COLUMNS
    assert len(table) == 2 * (1 + 3)
    exact = table[table["method"] == "cent_exact_dp"]
    assert (exact["gap_to_exact_cny"] == 0.0).all()
    bucket = table[table["method"] == "bucket_dp"]
    assert bucket["feasible_under_original_cost"].all()
    assert (bucket["n_dropped_for_feasibility"] >= 0).all()
    assert np.isfinite(bucket["predicted_value_cny"]).all()

    poisoned = ev.bucket_convergence_table(
        _poison(frame), cfg, pool_size=20, budgets=[0.04, 0.2], widths=[0.5, 0.1, 0.01]
    )
    columns = _selection_columns(table)
    pd.testing.assert_frame_equal(table.loc[:, columns], poisoned.loc[:, columns])


def test_random_baseline_is_reproducible_and_truth_isolated(cfg) -> None:
    frame = _frame()
    long_a, summary_a = ev.random_baseline_table(
        frame, cfg, budgets=[0.04, 0.2], seeds=5
    )
    long_b, summary_b = ev.random_baseline_table(
        frame, cfg, budgets=[0.04, 0.2], seeds=5
    )
    pd.testing.assert_frame_equal(long_a, long_b)
    pd.testing.assert_frame_equal(summary_a, summary_b)
    assert tuple(long_a.columns) == ev.RANDOM_COLUMNS
    assert tuple(summary_a.columns) == ev.RANDOM_SUMMARY_COLUMNS
    assert len(long_a) == 10 and len(summary_a) == 2
    assert (summary_a["q025"] <= summary_a["q500"] + 1e-12).all()
    assert (summary_a["q500"] <= summary_a["q975"] + 1e-12).all()
    assert summary_a["overrun_probability"].between(0.0, 1.0).all()
    assert summary_a["mean_se"].notna().all()
    assert summary_a["interpretation"].str.contains("not the CI").all()

    long_poisoned, poisoned_summary = ev.random_baseline_table(
        _poison(frame), cfg, budgets=[0.04, 0.2], seeds=5
    )
    stable = ["n_selected", "predicted_cost_cny", "within_budget_by_hat", "budget_cny", "seed"]
    pd.testing.assert_frame_equal(long_a.loc[:, stable], long_poisoned.loc[:, stable])
    assert not np.allclose(
        summary_a["mean_true_value_per_user"].to_numpy(),
        poisoned_summary["mean_true_value_per_user"].to_numpy(),
    )


def test_error_decomposition_identity_and_truth_bound(cfg) -> None:
    frame = _frame()
    table = ev.error_decomposition_table(
        frame, cfg, pool_size=20, budgets=[0.04, 0.2]
    )
    assert tuple(table.columns) == ev.DECOMPOSITION_COLUMNS
    assert len(table) == 4
    assert table["identity_residual"].abs().max() < 1e-9
    assert np.allclose(
        table["total_regret_cny_per_user"],
        table["learning_error_cny_per_user"] + table["optimization_error_cny_per_user"],
    )
    assert set(table["truth_status"]) <= {"optimal", "time_limit", "infeasible", "error"}
    assert table["truth_bound_cny"].ge(table["truth_incumbent_cny"] - 1e-9).all()
    assert np.isfinite(table["total_regret_cny_per_user"]).all()


def test_scale_table_contract_and_lp_bound(cfg) -> None:
    frame = _frame()
    table = ev.scale_table(
        frame, cfg, pool_sizes=[20, "full_test"], budgets=[0.04, 0.2], include_milp=True
    )
    assert tuple(table.columns) == ev.SCALE_COLUMNS
    assert len(table) == 2 * 2 * 4
    assert table.loc[table["pool_size"] == len(frame), "pool_is_full_test"].all()
    feasibility = table[table["solver"] != "lp_relaxation"]
    assert (
        feasibility["predicted_value_cny"] <= feasibility["lp_upper_bound_cny"] + 1e-9
    ).all()
    milp = table[table["solver"] == "time_limited_milp"]
    assert milp["bound_cny"].ge(milp["incumbent_cny"] - 1e-9).all()


def test_conservative_face_mode_cannot_overrun(cfg) -> None:
    frame = _frame()
    table = ev.conservative_comparison_table(
        frame, cfg, budgets=[0.2, 1.0], seeds=5
    )
    assert tuple(table.columns) == ev.CONSERVATIVE_COLUMNS
    assert len(table) == 2 * 3 * 3
    face = table[table["mode"] == "worst_case_face"]
    assert (face["overrun_probability"] == 0.0).all()
    assert (face["overrun_vs_expected_probability"] == 0.0).all()
    for row in face.itertuples():
        assert row.selected_count_mean <= np.floor(row.mode_budget_cny / 10.0) + 1e-9
    assert (table["observed_value_status"] == "deferred_to_F_ope").all()
    assert (table["value_basis"] == "dgp_truth_tau").all()
