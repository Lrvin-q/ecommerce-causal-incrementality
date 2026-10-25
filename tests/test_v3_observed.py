"""合成数据 / 已知 DGP：学习只能消费经 SQL 验证的观测数据。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.data import v3_observed
from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_sql import ANALYSIS_COLUMNS, run_sql_pipeline
from causal_growth.data.v3_storage import RunArtifactWriter, dataframe_sha256
from causal_growth.data.v3_tables import build_raw_tables
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.rng import child_rng
from causal_growth.v3_config import load_v3_protocol


# This is an API test fixture, not a formal scenario or a policy experiment.
TEST_N = 120
SCENARIOS = ("L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt050")


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


def _tables(cfg, *, validation: bool = False):
    options = {}
    if validation:
        arms = cfg.require("evaluation.independent_validation.arms")
        probabilities = cfg.require("evaluation.independent_validation.arm_probabilities")
        rng = child_rng(int(cfg.require("project.master_seed")), "test.observed.validation_arms", 0)
        labels = rng.choice(arms, TEST_N, p=probabilities)
        # Explicit frozen fixture actions; no use of U, truth, potential worlds or outcomes.
        actions = ((labels != "no_coupon") & (np.arange(TEST_N) % 2 == 0)).astype(int)
        policy = pd.DataFrame({"user_id": -np.arange(1, TEST_N + 1), "assigned_policy_arm": labels,
                               "issued_action": actions,
                               "policy_arm_probability": [dict(zip(arms, probabilities))[arm] for arm in labels]})
        options = {"population_kind": "validation", "validation_assignment": policy}
    population = generate_v3_population(cfg, rep_id=0, n=TEST_N, **options)
    raw = build_raw_tables(*population.observation_bundle(), cfg, run_id=f"observed_{'validation' if validation else cfg.name}",
                           rep_id=0, stream_prefix=population.metadata["stream_prefix"])
    dirty = inject_dirt(raw, cfg, rep_id=0, stream_prefix=population.metadata["stream_prefix"])
    return deduplicate_events(dirty.tables, cfg).tables


@pytest.fixture(scope="module")
def history(protocol):
    cfg = protocol.scenario("L1_main")
    tables = _tables(cfg)
    return cfg, tables, run_sql_pipeline(tables, cfg)


def _persist(tmp_path: Path, result, cfg, *, metadata_override=None):
    metadata = {"config_hash": cfg.hash(64), "data_config_hash": result.data_config_hash,
                "sql_sha256": result.sql_sha256, "analysis_producer": "v3_sql",
                "analysis_lineage": {"input_users_n": result.input_users_n}}
    metadata.update(metadata_override or {})
    writer = RunArtifactWriter(tmp_path / "run", metadata)
    writer.write_frame("sql/analysis.parquet", result.analysis, role="observed_sql")
    return writer.finish(passed=True, checks={"test": True})


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_four_actual_layers_sql_observed_roundtrip_and_full_denominator(protocol, scenario, tmp_path):
    cfg = protocol.scenario(scenario)
    tables = _tables(cfg)
    result = run_sql_pipeline(tables, cfg, database_path=tmp_path / "observed.sqlite")
    observed = ObservedDataset.from_sql_result(result, cfg)
    assert observed.population_kind == "history"
    observed.require_history()
    actual = observed.observations
    assert actual.attrs["population_kind"] == "history"
    assert actual.attrs["diagnostic_snapshot"] is False
    assert tuple(actual.columns) == ANALYSIS_COLUMNS
    assert len(actual) == result.visible_assigned_n == result.input_users_n == TEST_N
    assert result.summaries["groups"].n_total.sum() == TEST_N
    assert (actual.paid_orders_30d == 0).any()  # zero-order users remain eligible observations
    assert set(actual.user_id) == set(tables["users"].user_id)
    assert actual.mature.eq(1).all()
    if scenario.startswith("L3"):
        assert actual.design_probability.isna().all()
    restored = ObservedDataset.from_manifest(_persist(tmp_path, result, cfg), cfg)
    pd.testing.assert_frame_equal(restored.observations, actual, check_exact=True)
    assert restored.content_hash == observed.content_hash


def test_only_sql_result_factory_accepts_learning_data(history):
    cfg, _, result = history
    for source in (result.analysis, {"analysis": result.analysis}, object()):
        with pytest.raises(TypeError, match="SqlAnalysisResult"):
            ObservedDataset.from_sql_result(source, cfg)
    with pytest.raises(TypeError, match="verified SQL"):
        ObservedDataset(result.analysis, result.config_hash, result.data_config_hash, result.sql_sha256, "data/v3/manual")


@pytest.mark.parametrize("field", ["config_hash", "data_config_hash", "sql_sha256", "analysis_sha256"])
def test_sql_result_fingerprints_must_match_current_context(history, field):
    cfg, _, result = history
    with pytest.raises(ValueError):
        ObservedDataset.from_sql_result(replace(result, **{field: "0" * 64}), cfg)


def test_current_sql_source_change_rejects_previously_materialized_result(history, monkeypatch):
    cfg, _, result = history
    monkeypatch.setattr(v3_observed, "sql_source_hash", lambda: "changed-after-materialization")
    with pytest.raises(ValueError, match="source"):
        ObservedDataset.from_sql_result(result, cfg)


@pytest.mark.parametrize("column", ["U", "true_cate", "potential_y0", "audit_cost", "control_feasible", "oracle_profit"])
def test_extra_truth_columns_rejected_even_when_content_digest_is_updated(history, column):
    cfg, _, result = history
    contaminated = result.analysis.assign(**{column: 0})
    forged = replace(result, analysis=contaminated, analysis_sha256=dataframe_sha256(contaminated))
    with pytest.raises(ValueError, match="whitelist"):
        ObservedDataset.from_sql_result(forged, cfg)


@pytest.mark.parametrize("change", ["reordered_columns", "duplicate_users", "missing_user_id", "immature", "diagnostic_flag", "bad_action"])
def test_primary_sql_frame_semantics_cannot_be_bypassed_by_hash_refresh(history, change):
    cfg, _, result = history
    frame = result.analysis.copy()
    if change == "reordered_columns":
        frame = frame.iloc[:, ::-1]
    elif change == "duplicate_users":
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    elif change == "missing_user_id":
        frame["user_id"] = frame.user_id.astype("Int64")
        frame.loc[0, "user_id"] = pd.NA
    elif change == "immature":
        frame.loc[0, "mature"] = 0
    elif change == "diagnostic_flag":
        frame.loc[0, "diagnostic_snapshot"] = 1
    else:
        frame.loc[0, "actual_action"] = 2
    with pytest.raises(ValueError):
        ObservedDataset.from_sql_result(replace(result, analysis=frame, analysis_sha256=dataframe_sha256(frame)), cfg)


def test_modified_values_with_original_sql_fingerprint_rejected(history):
    cfg, _, result = history
    frame = result.analysis.copy()
    frame.loc[0, "net_profit"] += 1
    with pytest.raises(ValueError, match="content"):
        ObservedDataset.from_sql_result(replace(result, analysis=frame), cfg)


def test_input_and_returned_frames_are_copied_and_internal_tampering_detected(history):
    cfg, _, result = history
    supplied = replace(result, analysis=result.analysis.copy())
    observed = ObservedDataset.from_sql_result(supplied, cfg)
    fingerprint = observed.content_hash
    supplied.analysis.loc[0, "net_profit"] += 1
    exported = observed.observations
    exported.loc[0, "net_profit"] -= 1
    exported.attrs["source_path"] = "audit/forged"
    pd.testing.assert_frame_equal(observed.observations, result.analysis)
    assert observed.content_hash == fingerprint
    with pytest.raises(FrozenInstanceError):
        observed.config_hash = "different"
    observed._frame.loc[0, "net_profit"] += 1  # explicit hostile/private mutation must be detected
    for getter in (lambda: observed.content_hash, lambda: observed.observations, lambda: observed.population_kind):
        with pytest.raises(ValueError, match="modified"):
            getter()


@pytest.mark.parametrize("part", ["audit", "TRUTH"])
def test_sql_result_cannot_claim_audit_path(history, tmp_path, part):
    cfg, _, result = history
    with pytest.raises(ValueError, match="audit/truth"):
        ObservedDataset.from_sql_result(replace(result, database_path=tmp_path / part / "observed.sqlite"), cfg)


@pytest.mark.parametrize("field,value", [
    ("config_hash", "wrong"), ("data_config_hash", "wrong"),
    ("sql_sha256", "wrong"), ("analysis_producer", "array_ledger"),
])
def test_persisted_provenance_mismatch_rejected(history, tmp_path, field, value):
    cfg, _, result = history
    manifest = _persist(tmp_path, result, cfg, metadata_override={field: value})
    with pytest.raises(ValueError):
        ObservedDataset.from_manifest(manifest, cfg)


def test_persisted_current_sql_change_rejected(history, tmp_path, monkeypatch):
    cfg, _, result = history
    manifest = _persist(tmp_path, result, cfg)
    monkeypatch.setattr(v3_observed, "sql_source_hash", lambda: "new-current-sql")
    with pytest.raises(ValueError, match="SQL provenance"):
        ObservedDataset.from_manifest(manifest, cfg)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_split_is_exact_disjoint_complete_and_preserves_every_other_value(protocol, scenario):
    cfg = protocol.scenario(scenario)
    result = run_sql_pipeline(_tables(cfg), cfg)
    original = ObservedDataset.from_sql_result(result, cfg)
    split, manifest = original.assign_splits(cfg, stream="test.observed.splits", index=0)
    before, after = original.observations, split.observations
    pd.testing.assert_frame_equal(before.drop(columns="split"), after.drop(columns="split"), check_exact=True)
    assert original.content_hash == result.analysis_sha256
    assert manifest["counts"] == {role: int(TEST_N * cfg.require(f"design.split.{role}")) for role in ("train", "validation", "test")}
    repeat, _ = original.assign_splits(cfg, stream="test.observed.splits", index=0)
    pd.testing.assert_frame_equal(repeat.observations, after, check_exact=True)
    seen = set()
    for role in ("train", "validation", "test"):
        selected = split.select_split(role).observations
        expected = after.loc[after.split == role].reset_index(drop=True)
        pd.testing.assert_frame_equal(selected, expected, check_exact=True)
        keys = set(zip(selected.run_id, selected.user_id))
        assert not seen & keys
        seen |= keys
    assert len(seen) == TEST_N
    manifest["counts"]["train"] = -1
    assert split.lineage["split_manifest"]["counts"]["train"] >= 0
    with pytest.raises(ValueError):
        split.select_split("all")
    with pytest.raises(ValueError):
        original.assign_splits(cfg.with_overrides({"business.coupon_reference_face": 1}), stream="bad", index=0)


def test_diagnostic_snapshot_requires_explicit_permission_and_cannot_become_training(history, tmp_path):
    cfg, tables, _ = history
    result = run_sql_pipeline(tables, cfg, relative_snapshot_days=float(cfg.require("windows.convert_days")), allow_immature=True)
    assert result.diagnostic_snapshot and not result.analysis.mature.any()
    with pytest.raises(ValueError, match="diagnostic"):
        ObservedDataset.from_sql_result(result, cfg)
    diagnostic = ObservedDataset.from_sql_result(result, cfg, allow_diagnostic=True)
    assert diagnostic.diagnostic
    assert diagnostic.observations.attrs["diagnostic_snapshot"] is True
    for operation in (diagnostic.require_history, lambda: diagnostic.assign_splits(cfg, stream="invalid", index=0), lambda: diagnostic.select_split("train")):
        with pytest.raises(ValueError):
            operation()
    manifest = _persist(tmp_path, result, cfg)
    with pytest.raises(ValueError, match="diagnostic"):
        ObservedDataset.from_manifest(manifest, cfg)
    restored = ObservedDataset.from_manifest(manifest, cfg, allow_diagnostic=True)
    assert restored.diagnostic
    pd.testing.assert_frame_equal(restored.observations, diagnostic.observations, check_exact=True)


def test_three_arm_validation_sql_chain_kept_out_of_learning_and_splits(protocol, tmp_path):
    cfg = protocol.scenario("L1_main")
    result = run_sql_pipeline(_tables(cfg, validation=True), cfg, database_path=tmp_path / "validation.sqlite")
    validation = ObservedDataset.from_sql_result(result, cfg)
    frame = validation.observations
    assert validation.population_kind == frame.attrs["population_kind"] == "validation"
    assert set(frame.assigned_policy_arm) == set(cfg.require("evaluation.independent_validation.arms"))
    assert frame.treatment.equals(frame.assigned_policy_arm)
    assert len(frame) == TEST_N and frame.actual_action.isin([0, 1]).all()
    assert frame.loc[frame.assigned_policy_arm == "no_coupon", "actual_action"].eq(0).all()
    for operation in (validation.require_history, lambda: validation.assign_splits(cfg, stream="invalid", index=0), lambda: validation.select_split("train")):
        with pytest.raises(ValueError, match="historical"):
            operation()
    restored = ObservedDataset.from_manifest(_persist(tmp_path, result, cfg), cfg)
    assert restored.population_kind == "validation"
    with pytest.raises(ValueError):
        restored.select_split("train")
    pd.testing.assert_frame_equal(restored.observations, frame, check_exact=True)
