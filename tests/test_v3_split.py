"""合成数据 / 已知 DGP：实际日志分层人数与未来训练可见性。"""

import numpy as np
import pandas as pd
import pytest

from causal_growth.data.v3_split import assign_user_splits, rolling_training_candidates
from causal_growth.v3_config import load_v3_protocol


def _users(n):
    index = np.arange(n)
    return pd.DataFrame({"run_id": "r", "user_id": index + 1, "treatment": index % 2,
                         "channel": np.array(["search", "feed", "xhs", "other"])[(index // 2) % 4],
                         "is_new": (index // 8) % 2})


def test_exact_200k_counts_and_complete_user_disjointness():
    cfg = load_v3_protocol().scenario("L1_main")
    n = cfg.require("design.n_total")
    frame = _users(n)
    result = assign_user_splits(frame, cfg, master_seed=cfg.require("project.master_seed"), stream="test.split")
    assert result.manifest["counts"] == {"train": 100000, "validation": 40000, "test": 60000}
    assert not result.assignments.duplicated(["run_id", "user_id"]).any()
    assert set(result.assignments.user_id) == set(frame.user_id)
    merged = frame.merge(result.assignments, on=["run_id", "user_id"], validate="one_to_one")
    sizes = merged.groupby(["treatment", "channel", "is_new", "split"]).size().unstack()
    for role in ["train", "validation", "test"]:
        np.testing.assert_array_equal(sizes[role], sizes.sum(axis=1) * cfg.require(f"design.split.{role}"))


def test_reordering_outcomes_and_model_names_cannot_change_split():
    cfg = load_v3_protocol().scenario("L1_main")
    frame = _users(101)
    args = {"master_seed": cfg.require("project.master_seed"), "stream": "test.split", "index": 1}
    a = assign_user_splits(frame, cfg, **args)
    changed = frame.iloc[::-1].assign(net_profit=1e20, true_model_name="unused_by_split")
    b = assign_user_splits(changed, cfg, **args)
    pd.testing.assert_frame_equal(a.assignments.sort_values("user_id").reset_index(drop=True),
                                  b.assignments.sort_values("user_id").reset_index(drop=True))
    assert a.manifest["split_hash"] == b.manifest["split_hash"]


def test_tiny_strata_and_multiple_runs_preserve_each_run_counts():
    cfg = load_v3_protocol().scenario("L0_P_main")
    frame = pd.concat([_users(7), _users(7).assign(run_id="other")], ignore_index=True)
    result = assign_user_splits(frame, cfg, master_seed=1, stream="test.tiny")
    assert len(result.assignments) == len(frame)
    counts = result.assignments.groupby(["run_id", "split"]).size().unstack(fill_value=0)
    assert counts.loc["r"].to_dict() == {"test": 2, "train": 4, "validation": 1}
    assert counts.loc["other"].to_dict() == counts.loc["r"].to_dict()


def test_l2_uses_frozen_weeks_and_rejects_unknown_week():
    cfg = load_v3_protocol().scenario("L2_n200000_p050")
    weeks = cfg.require("design.temporal.assignment_weeks")
    frame = _users(len(weeks)).assign(assignment_week=weeks)
    result = assign_user_splits(frame, cfg, master_seed=1, stream="test.calendar")
    assert result.assignments.split.tolist() == ["train"] * 5 + ["validation"] * 2 + ["test"] * 3
    frame.loc[0, "assignment_week"] = 999
    with pytest.raises(ValueError, match="未注册"):
        assign_user_splits(frame, cfg, master_seed=1, stream="test.calendar")


def test_rolling_requires_both_mature_outcomes_and_arrived_records():
    cfg = load_v3_protocol().scenario("L2_n200000_p050")
    frame = pd.DataFrame({"run_id": "r", "user_id": [1, 2, 3, 4, 5, 6],
        "split": ["train", "validation", "test", "test", "test", "test"],
        "assignment_week": [1, 10, 16, 16, 22, 28],
        "assignment_day": [0., 63., 105., 111.9, 147., 189.],
        "required_ingestion_day": [30., 93., 135., 160., 177., 219.],
        "complete_after_day": [32., 95., 137., 143.9, 179., 221.]})
    # At week22, prior test user3 is mature and arrived; user4 is mature but late.
    result = rolling_training_candidates(frame, cfg, origin_week=22)
    assert result.train_user_keys.user_id.tolist() == [1, 3]
    assert result.evaluation_user_keys.user_id.tolist() == [5]
    assert result.manifest["excluded_not_ingested_n"] == 1
    assert result.manifest["excluded_validation_n"] == 1
    assert result.manifest["selection_method"] == "past_mature_ingested_train_or_prior_test_validation_held_out"
    first = rolling_training_candidates(frame, cfg, origin_week=16)
    assert first.train_user_keys.user_id.tolist() == [1]
    with pytest.raises(ValueError, match="缺少"):
        rolling_training_candidates(frame.drop(columns="required_ingestion_day"), cfg, origin_week=22)
    incomplete = frame.copy()
    incomplete.loc[incomplete.user_id == 3, "complete_after_day"] = 160
    conservative = rolling_training_candidates(incomplete, cfg, origin_week=22)
    assert conservative.train_user_keys.user_id.tolist() == [1]
    assert conservative.manifest["excluded_completeness_not_guaranteed_n"] == 1


def test_duplicate_user_fails_instead_of_cross_split_leakage():
    cfg = load_v3_protocol().scenario("L1_main")
    frame = _users(5)
    frame.loc[1, "user_id"] = frame.loc[0, "user_id"]
    with pytest.raises(ValueError, match="重复"):
        assign_user_splits(frame, cfg, master_seed=1, stream="test.duplicates")


@pytest.mark.parametrize("marker", ["source_kind", "kind_column", "policy_arm", "diagnostic_attribute", "diagnostic_column"])
def test_validation_and_diagnostic_data_cannot_be_reassigned_as_history(marker):
    cfg = load_v3_protocol().scenario("L1_main")
    frame = _users(10).assign(split="train")
    if marker == "source_kind":
        frame.attrs["population_kind"] = "validation"
    elif marker == "kind_column":
        frame["population_kind"] = "validation"
    elif marker == "policy_arm":
        frame["assigned_policy_arm"] = np.nan
        frame.loc[0, "assigned_policy_arm"] = 0
    elif marker == "diagnostic_attribute":
        frame.attrs["diagnostic_snapshot"] = True
    else:
        frame["diagnostic_snapshot"] = False
        frame.loc[0, "diagnostic_snapshot"] = True
    with pytest.raises(ValueError, match="验证|诊断"):
        assign_user_splits(frame, cfg, master_seed=1, stream="test.validation_guard")


def test_empty_policy_arm_column_does_not_reclassify_history():
    cfg = load_v3_protocol().scenario("L1_main")
    frame = _users(10).assign(assigned_policy_arm=np.nan, diagnostic_snapshot=False)
    frame.attrs.update(population_kind="history", diagnostic_snapshot=False)
    assert len(assign_user_splits(frame, cfg, master_seed=1, stream="test.history").assignments) == len(frame)
