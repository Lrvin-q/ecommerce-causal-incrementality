"""F02 三臂随机验证的口径测试：全臂分母、预算、冻结顺序与审计隔离。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.evaluation import v3_f02 as f02
from causal_growth.v3_config import load_v3_protocol

ARM_NAMES = f02.ARMS


def _cfg():
    return load_v3_protocol().scenario("L1_main")


def _scored(n: int = 3000, seed: int = 0) -> f02.ScoredCohort:
    rng = np.random.default_rng(seed)
    tau = rng.normal(0.2, 0.1, n)
    frame = pd.DataFrame({
        "user_id": np.arange(1, n + 1),
        "is_new": rng.integers(0, 2, n),
        "cart_value": rng.uniform(10.0, 300.0, n),
        "purchase_propensity": rng.uniform(0.0, 1.0, n),
        "predicted_profit": rng.uniform(0.0, 50.0, n),
        "tau_hat": tau,
        "cost_hat": np.full(n, 0.5),
    })
    return f02.ScoredCohort(
        frame=frame, model="constant", policy="", preprocessor_hash="unit-test"
    )


def _observed() -> pd.DataFrame:
    return pd.DataFrame({
        "run_id": "f02:unit",
        "user_id": [1, 2, 3, 4, 5, 6],
        "assigned_policy_arm": [
            f02.CONTROL_ARM, f02.CONTROL_ARM, f02.RANDOM_ARM,
            f02.RANDOM_ARM, f02.TARGETED_ARM, f02.TARGETED_ARM,
        ],
        "actual_action": [0, 0, 1, 0, 1, 1],
        "net_profit": [1.0, 2.0, 3.0, 4.0, 5.0, 7.0],
        "coupon_cost": [0.0, 0.0, 1.5, 0.0, 2.0, 2.0],
    })


def test_assignment_has_one_arm_per_user_and_control_never_issues() -> None:
    scored = _scored()
    assignment, info = f02.build_validation_assignment(
        scored, _cfg(), policy="incremental_profit_rank", rep_id=0
    )
    assert len(assignment) == len(scored.frame)
    assert assignment["user_id"].is_unique
    assert set(assignment["assigned_policy_arm"]) == set(ARM_NAMES)
    assert assignment.loc[assignment["assigned_policy_arm"] == f02.CONTROL_ARM, "issued_action"].eq(0).all()
    assert assignment["issued_action"].isin([0, 1]).all()
    assert assignment["policy_arm_probability"].between(0, 1).all()
    counts = assignment["assigned_policy_arm"].value_counts()
    assert counts.min() > len(assignment) / 5
    for arm in ARM_NAMES:
        assert info["arms"][arm]["n_assigned"] == int(counts.get(arm, 0))
    assert info["arm_lists"]["targeted_n"] > 0
    assert info["arm_lists"]["random_n"] > 0
    assert info["audit_full_lists"]["targeted_n"] > 0
    assert info["budget_cny_per_user"] == pytest.approx(0.2)
    assert info["budget_basis"] == "same_per_assigned_user_in_each_active_arm"


def test_assignment_is_deterministic_and_respects_budget_by_hat() -> None:
    scored = _scored()
    cfg = _cfg()
    first, info_first = f02.build_validation_assignment(
        scored, cfg, policy="business_rule_new_user_then_cart", rep_id=7
    )
    second, info_second = f02.build_validation_assignment(
        scored, cfg, policy="business_rule_new_user_then_cart", rep_id=7
    )
    pd.testing.assert_frame_equal(first, second)
    assert info_first["arms"] == info_second["arms"]
    assert info_first["audit_full_lists"] == info_second["audit_full_lists"]
    # 每个活跃臂按臂内人数获得 0.2 元/人预算，实际支出不得超出该臂预算（容差内）。
    cost = scored.frame.set_index("user_id")["cost_hat"]
    for arm in (f02.TARGETED_ARM, f02.RANDOM_ARM):
        block = first.loc[first["assigned_policy_arm"] == arm]
        spend = cost.loc[block.loc[block["issued_action"] == 1, "user_id"]].sum()
        budget = info_first["budget_cny_per_user"] * len(block)
        assert spend <= budget + 1e-9
        assert block["issued_action"].mean() > 0.1
    # 全队列交付名单只用于审计，同样不得超预算。
    assert info_first["audit_full_lists"]["targeted_within_budget"]
    assert info_first["audit_full_lists"]["random_within_budget"]


def test_assignment_rejects_non_actionable_policy() -> None:
    with pytest.raises(ValueError, match="不是可执行的定向策略"):
        f02.build_validation_assignment(
            _scored(), _cfg(), policy="all_coupon_unconstrained_reference", rep_id=0
        )


def test_arm_summary_uses_all_assigned_users() -> None:
    table = f02.arm_summary(_observed()).set_index("arm")
    assert table.loc[f02.CONTROL_ARM, "n_assigned"] == 2
    assert np.isclose(table.loc[f02.CONTROL_ARM, "mean_net_profit_cny"], 1.5)
    assert np.isclose(table.loc[f02.RANDOM_ARM, "mean_net_profit_cny"], 3.5)
    assert np.isclose(table.loc[f02.RANDOM_ARM, "issue_share"], 0.5)
    assert table.loc[f02.CONTROL_ARM, "total_coupon_cost_cny"] == 0.0
    assert np.isclose(table.loc[f02.TARGETED_ARM, "mean_coupon_cost_cny"], 2.0)


def test_itt_contrast_is_difference_of_full_arm_means() -> None:
    table = f02.itt_contrasts(_observed(), _cfg()).set_index("contrast")
    targeted_minus_control = table.loc[
        f"{f02.TARGETED_ARM}_minus_{f02.CONTROL_ARM}"
    ]
    assert np.isclose(targeted_minus_control["diff_cny_per_user"], 4.5)
    expected_se = np.sqrt((np.var([5.0, 7.0], ddof=1) / 2) + (np.var([1.0, 2.0], ddof=1) / 2))
    assert np.isclose(targeted_minus_control["se"], expected_se)
    assert targeted_minus_control["n_left"] == 2
    assert targeted_minus_control["n_right"] == 2


def test_freeze_observed_strips_truth_and_is_value_sensitive() -> None:
    observed = _observed()
    observed["tau_true"] = 9.0
    observed["cost_true"] = 9.0
    per_user, digest = f02.freeze_observed(
        observed, selected_policy="incremental_profit_rank", model="constant"
    )
    assert tuple(per_user.columns) == f02.PER_USER_COLUMNS
    assert "tau_true" not in per_user.columns
    assert "cost_true" not in per_user.columns
    again, digest_again = f02.freeze_observed(
        observed, selected_policy="incremental_profit_rank", model="constant"
    )
    assert digest == digest_again
    changed = observed.copy()
    changed.loc[0, "net_profit"] = 99.0
    _, digest_changed = f02.freeze_observed(
        changed, selected_policy="incremental_profit_rank", model="constant"
    )
    assert digest_changed != digest


def test_audit_policy_values_align_by_user_id_not_row_order() -> None:
    ids = np.arange(1, 7)
    worlds = {
        0: pd.DataFrame({
            "user_id": ids,
            "net_profit": np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
            "coupon_cost": np.zeros(6),
        }),
        1: pd.DataFrame({
            "user_id": ids,
            "net_profit": np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0]),
            "coupon_cost": np.ones(6),
        }),
    }
    targeted = np.array([1, 3, 5])
    random_ids = np.array([2, 4])
    ordered, table = f02.audit_policy_values(
        None, _cfg(), targeted_ids=targeted, random_ids=random_ids,
        user_ids=ids, worlds=worlds,
    )
    _, reversed_table = f02.audit_policy_values(
        None, _cfg(), targeted_ids=targeted, random_ids=random_ids,
        user_ids=ids[::-1], worlds=worlds,
    )
    values = table.set_index("component")["value_cny_per_user"]
    assert np.isclose(values.loc["value_targeted_policy"], np.mean([10, 1, 12, 3, 14, 5]))
    assert np.isclose(values.loc["value_random_same_budget"], np.mean([0, 11, 2, 13, 4, 5]))
    pd.testing.assert_frame_equal(
        table.set_index("component").sort_index(),
        reversed_table.set_index("component").sort_index(),
    )
    assert table["n_selected"].tolist() == [3, 2, 0]
    assert ordered["user_id"].tolist() == ids.tolist()


def test_formal_status_requires_approval() -> None:
    with pytest.raises(ValueError, match="formal_approval"):
        f02.run_f02_rep(scenario="L1_main", n=3000, rep_id=0, status="formal")
    with pytest.raises(ValueError, match="未注册的状态"):
        f02.run_f02_rep(scenario="L1_main", n=3000, rep_id=0, status="informal")


def test_run_f02_rep_end_to_end(tmp_path) -> None:
    result = f02.run_f02_rep(
        scenario="L1_main",
        n=2000,
        rep_id=0,
        policy="incremental_profit_rank",
        models=("constant",),
        out_dir=tmp_path,
    )
    assert result.manifest["status"] == "provisional"
    assert result.manifest["audit_unlock_order"].startswith("freeze_files_written_then_audit")
    assert result.manifest["freeze_hash"] == result.freeze_hash
    assert len(result.per_user) == 2000
    assert result.per_user["user_id"].nunique() == 2000
    assert set(result.per_user.columns) == set(f02.PER_USER_COLUMNS)
    assert not any(column.endswith("_true") for column in result.per_user.columns)
    counts = result.assignment["assigned_policy_arm"].value_counts()
    assert counts.sum() == 2000
    assert (counts > 0).all()
    assert result.audit_users["user_id"].nunique() == 2000
    assert np.isfinite(result.audit_users["tau_true"].to_numpy()).all()
    assert set(result.audit_policy["component"]) == {
        "value_targeted_policy", "value_random_same_budget", "value_no_coupon",
    }
    for name in (
        "per_user.csv", "arm_summary.csv", "itt_contrasts.csv", "freeze.json",
        "audit_truth.csv", "audit_policy_values.csv", "audit_arm_contrasts.csv",
        "manifest.json",
    ):
        assert (tmp_path / name).exists(), name
    # 代表 rep（配置的 representative_rep=0）必须落盘完整五表与 SQL。
    assert result.manifest["representative_five_tables"] is True
    analysis_path = tmp_path / "five_tables" / "sql" / "analysis.parquet"
    assert analysis_path.exists()
    five_manifest = result.manifest["representative_tables_manifest"]
    assert five_manifest is not None and json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )["representative_tables_manifest"] == five_manifest
    assert result.manifest["representative_tables_manifest_sha256"] == hashlib.sha256(
        Path(five_manifest).read_bytes()
    ).hexdigest()
    freeze = json.loads((tmp_path / "freeze.json").read_text(encoding="utf-8"))
    assert freeze["freeze_hash"] == result.freeze_hash
    assert freeze["truth_columns_present"] is False
    observed = result.arm_summary.set_index("arm")
    assert observed.loc[f02.CONTROL_ARM, "n_issued"] == 0
    assert observed["n_assigned"].sum() == 2000
