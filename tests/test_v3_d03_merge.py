"""合并门禁的合成用例：缺 rep / 重复 rep / 篡改合规标记都要拒。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "25_merge_d03_formal.py"

MODELS = ("constant", "t_learner", "s_learner", "causal_forest", "dr_learner")
BUDGETS = (0.04, 0.10, 0.20, 0.30, 0.40, 0.60, 0.80, 1.00)
POLICIES = (
    "no_coupon", "all_coupon_unconstrained_reference", "random_same_budget",
    "business_rule_new_user_then_cart", "purchase_propensity_rank",
    "predicted_profit_rank", "incremental_profit_rank",
    "greedy_incremental_profit_per_cost", "greedy_local_swap",
)
STAT_COLUMNS = (
    "tau_hat_mean", "bias_mean", "relative_bias", "calibration_slope",
    "calibration_intercept", "pearson_r", "rmse", "mae",
    "error_q10", "error_q50", "error_q90",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("merge_d03_formal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _per_rep(rep_ids: list[int]) -> pd.DataFrame:
    rows = []
    for rep in rep_ids:
        for index, model in enumerate(MODELS):
            row = {"rep_id": rep, "model": model, "chosen": index == 0,
                   "tau_true_mean": 0.2 + rep * 0.001, "n_test": 1000}
            for column in STAT_COLUMNS:
                row[column] = 0.1 if column != "calibration_slope" else 1.0
            rows.append(row)
    return pd.DataFrame(rows)


def _grid(rep_ids: list[int]) -> pd.DataFrame:
    rows = []
    for rep in rep_ids:
        for model in MODELS:
            for budget in BUDGETS:
                for policy in POLICIES:
                    cost = budget * 1000 * 0.9
                    rows.append({
                        "rep_id": rep, "model": model, "chosen": model == "constant",
                        "per_user_budget_cny": budget, "budget_cny": budget * 1000,
                        "policy": policy, "n_selected": 10,
                        "predicted_value": 1.0, "predicted_cost": cost,
                        "true_value_per_user": 0.1, "true_total_value": 100.0,
                        "actual_spend_cny": cost * 2.0,
                        "within_budget_by_hat": True,
                        "within_budget_by_true": cost * 2.0 <= budget * 1000 + 1e-9,
                    })
    return pd.DataFrame(rows)


def _summary(rep_ids: list[int]) -> dict:
    return {
        "status": "formal_r", "formal_r": True, "reps": len(rep_ids),
        "n_per_rep": 1000, "rep_ids": rep_ids,
        "scenario": "L1_main", "level": "L1",
        "identification_mode": "randomized", "time_mode": "timestamp",
        "source_label": "合成数据 / 已知 DGP",
        "selection_rule": "validation_crossfit_dr_policy_value_lower_confidence_bound",
        "truth_isolation": {"used_for_selection": False, "used_for_evaluation": True},
        "chosen_model_counts": {"constant": len(rep_ids)},
        "config_hash": "abc123",
        "reps_meta": [
            {"rep_id": rep, "n_total": 1000, "observed_hash": f"obs-{rep}",
             "split_fingerprint": f"split-{rep}"}
            for rep in rep_ids
        ],
    }


def _write_shard(directory: Path, rep_ids: list[int], *, per_rep=None, grid=None,
                 summary=None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (per_rep if per_rep is not None else _per_rep(rep_ids)).to_csv(
        directory / "v3_phase_D03_diagnostic_per_rep.csv", index=False, encoding="utf-8-sig")
    (grid if grid is not None else _grid(rep_ids)).to_csv(
        directory / "v3_phase_D03_diagnostic_policy_grid.csv", index=False, encoding="utf-8-sig")
    (directory / "v3_phase_D03_diagnostic_summary.json").write_text(
        json.dumps(summary if summary is not None else _summary(rep_ids), ensure_ascii=False),
        encoding="utf-8")
    return directory


def test_merge_two_shards(tmp_path):
    module = _load_module()
    shard0 = _write_shard(tmp_path / "shard0", [0, 1])
    shard1 = _write_shard(tmp_path / "shard1", [2, 3])
    per_rep, grid, summary = module.merge([shard0, shard1], 4, 1000, False)
    assert len(per_rep) == 4 * 5
    assert len(grid) == 4 * 5 * 8 * 9
    assert summary["chosen_model_counts"] == {"constant": 4}
    assert summary["rep_ids"] == [0, 1, 2, 3]
    assert len(summary["reps_meta"]) == 4


def test_merge_rejects_missing_rep(tmp_path):
    module = _load_module()
    shard0 = _write_shard(tmp_path / "shard0", [0, 1])
    shard1 = _write_shard(tmp_path / "shard1", [2])
    with pytest.raises(ValueError, match="缺少 rep"):
        module.merge([shard0, shard1], 4, 1000, False)


def test_merge_rejects_duplicate_rep(tmp_path):
    module = _load_module()
    shard0 = _write_shard(tmp_path / "shard0", [0, 1])
    shard1 = _write_shard(tmp_path / "shard1", [1, 2])
    with pytest.raises(ValueError):
        module.merge([shard0, shard1], 3, 1000, False)


def test_merge_rejects_tampered_budget_flag(tmp_path):
    module = _load_module()
    grid = _grid([0])
    grid.loc[grid.index[0], "within_budget_by_true"] = not bool(
        grid.loc[grid.index[0], "within_budget_by_true"])
    shard = _write_shard(tmp_path / "shard0", [0], grid=grid)
    with pytest.raises(ValueError, match="within_budget_by_true"):
        module.merge([shard], 1, 1000, False)


def test_merge_rejects_wrong_chosen_count(tmp_path):
    module = _load_module()
    per_rep = _per_rep([0])
    per_rep["chosen"] = False
    shard = _write_shard(tmp_path / "shard0", [0], per_rep=per_rep)
    with pytest.raises(ValueError, match="chosen"):
        module.merge([shard], 1, 1000, False)


def test_merge_rejects_inconsistent_config_hash(tmp_path):
    module = _load_module()
    shard0 = _write_shard(tmp_path / "shard0", [0])
    summary = _summary([1])
    summary["config_hash"] = "different"
    shard1 = _write_shard(tmp_path / "shard1", [1], summary=summary)
    with pytest.raises(ValueError, match="config_hash"):
        module.merge([shard0, shard1], 2, 1000, False)


def test_merge_rejects_nonformal_shard(tmp_path):
    module = _load_module()
    summary = _summary([0])
    summary["formal_r"] = False
    summary["status"] = "diagnostic"
    shard = _write_shard(tmp_path / "shard0", [0], summary=summary)
    with pytest.raises(ValueError, match="不是正式 R"):
        module.merge([shard], 1, 1000, False)
