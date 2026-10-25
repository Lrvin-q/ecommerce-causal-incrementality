"""Observed production chain and persisted artifacts, without learning from truth."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_pipeline import build_observed_pipeline
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.dgp.v3_archive import archive_sealed_population
from causal_growth.data.v3_storage import read_verified_frame
from causal_growth.v3_config import load_v3_protocol


@pytest.mark.parametrize("scenario", ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"])
def test_full_chain_has_materialized_five_tables_and_sql_roundtrip(tmp_path: Path, scenario: str) -> None:
    cfg = load_v3_protocol().scenario(scenario)
    population = generate_v3_population(cfg, n=300)
    result = build_observed_pipeline(*population.observation_bundle(), cfg, directory=tmp_path / scenario,
                                    run_id=scenario, rep_id=0, stream_prefix="test.pipeline", persist_database=True)
    restored = ObservedDataset.from_manifest(result.manifest_path, cfg)
    pd.testing.assert_frame_equal(restored.observations, result.dataset.observations)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "passed" and manifest["formal_repetitions_completed"] == 0
    assert len(restored.observations) == 300
    example_record = manifest["artifacts"]["examples/analysis_preview.csv"]
    assert example_record["rows"] == 100 and example_record["source_rows"] == 300 and example_record["is_preview"]
    preview_path = result.manifest_path.parent / "examples/analysis_preview.csv"
    assert preview_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert len(pd.read_csv(preview_path, encoding="utf-8-sig")) == 100
    with pytest.raises(ValueError, match="parquet"):
        read_verified_frame(result.manifest_path, "examples/analysis_preview.csv")
    assert restored.observations.mature.eq(1).all()
    assert set(restored.observations.split) == {"train", "validation", "test"}
    assert result.preprocessor.to_dict()["training_n"] == restored.observations.split.eq("train").sum()
    for stage in ("raw", "dirty", "clean"):
        paths = list((result.manifest_path.parent / stage).glob("*.parquet"))
        assert len(paths) == 5
        outcomes = pd.read_parquet(result.manifest_path.parent / stage / "user_outcomes.parquet")
        assert len(outcomes) == 600
        assert set(outcomes.window_type) == {"convert_7d", "profit_30d"}
    assert result.stage_counts["repair"]["duplicate_events_removed"] == result.stage_counts["pollution"]["event_duplicates_injected"]
    clean_users = pd.read_parquet(result.manifest_path.parent / "clean/users.parquet")
    assert clean_users.cart_value_cent.isna().sum() == result.stage_counts["pollution"]["cart_missing_injected"]
    sealed_path = archive_sealed_population(population, cfg, directory=tmp_path / "audit" / scenario,
                                            observed_manifest=result.manifest_path)
    sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
    assert sealed["audit_release_state"] == "sealed_pending_frozen_policy_and_observed_results"
    assert sealed["checks"]["released_to_analysis"] is False
    with pytest.raises(ValueError, match="audit"):
        read_verified_frame(sealed_path, "private_state.parquet")
    wrong_population = replace(population, metadata={**population.metadata, "config_hash": "wrong"})
    with pytest.raises(ValueError, match="does not match"):
        archive_sealed_population(wrong_population, cfg, directory=tmp_path / "audit" / "wrong_cfg",
                                  observed_manifest=result.manifest_path)
    wrong_users = population.users.copy(deep=True)
    wrong_users.loc[0, "hist_gmv"] += 1
    with pytest.raises(ValueError, match="does not match"):
        archive_sealed_population(replace(population, users=wrong_users), cfg,
                                  directory=tmp_path / "audit" / "wrong_population",
                                  observed_manifest=result.manifest_path)


def test_validation_is_evaluation_only_and_can_use_frozen_training_transform(tmp_path: Path) -> None:
    cfg = load_v3_protocol().scenario("L1_main")
    history = generate_v3_population(cfg, n=120)
    fitted = build_observed_pipeline(*history.observation_bundle(), cfg, directory=tmp_path / "history",
                                    run_id="history", rep_id=0, stream_prefix="test.history")
    arms = cfg.require("evaluation.independent_validation.arms")
    probabilities = cfg.require("evaluation.independent_validation.arm_probabilities")
    n = 120
    assignment = pd.DataFrame({
        "user_id": -np.arange(1, n + 1),
        "assigned_policy_arm": [arms[i % len(arms)] for i in range(n)],
        "issued_action": [int(i % len(arms) != 0) for i in range(n)],
        "policy_arm_probability": [probabilities[i % len(arms)] for i in range(n)],
    })
    population = generate_v3_population(cfg, n=n, population_kind="validation", validation_assignment=assignment)
    result = build_observed_pipeline(*population.observation_bundle(), cfg, directory=tmp_path / "validation",
                                    run_id="validation", rep_id=0, stream_prefix="test.validation",
                                    population_kind="validation", frozen_preprocessor=fitted.preprocessor)
    assert result.dataset.population_kind == "validation"
    assert result.preprocessor.hash == fitted.preprocessor.hash
    assert result.dataset.observations.split.eq("test").all()
    with pytest.raises(ValueError, match="historical"):
        result.dataset.select_split("train")


def test_power_template_cannot_silently_run_as_its_base(tmp_path: Path) -> None:
    protocol = load_v3_protocol()
    cell = protocol.config.require("design_power_jobs")[0]
    cfg = protocol.scenario(cell["id"])
    population = generate_v3_population(protocol.scenario(cell["base_scenario_id"]), n=30)
    with pytest.raises(ValueError, match="calibrated"):
        build_observed_pipeline(*population.observation_bundle(), cfg, directory=tmp_path / "power",
                                run_id="power", rep_id=0, stream_prefix="test.power")
    assert not (tmp_path / "power").exists()


def test_failed_pipeline_retains_failed_manifest(tmp_path: Path) -> None:
    cfg = load_v3_protocol().scenario("L1_main")
    population = generate_v3_population(cfg, n=30)
    users, assignments, orders = population.observation_bundle()
    users["true_effect"] = 0
    with pytest.raises(ValueError, match="白名单"):
        build_observed_pipeline(users, assignments, orders, cfg, directory=tmp_path / "failed",
                                run_id="failed", rep_id=0, stream_prefix="test.failed")
    manifest = json.loads((tmp_path / "failed/manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed" and manifest["formal_repetitions_completed"] == 0
