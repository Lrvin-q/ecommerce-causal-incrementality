"""Exercise the actual CLI bytes and its canonical paired engineering streams."""

import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_preprocessing import fit_preprocessor
from causal_growth.data.v3_split import assign_user_splits, user_key_hash
from causal_growth.data.v3_storage import file_sha256
from causal_growth.dgp.v3_covariates import stream_prefix
from causal_growth.rng import child_rng
from causal_growth.v3_config import load_v3_protocol
from causal_growth.v3_data_config import load_v3_data_config


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_evidence(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def cli_workspace(tmp_path_factory) -> dict:
    project_root = Path(__file__).resolve().parents[1]
    workspace = tmp_path_factory.mktemp("v3_cli")
    original = project_root / "scripts/11_build_v3_data.py"
    copied = workspace / "scripts" / original.name
    copied.parent.mkdir()
    copied.write_bytes(original.read_bytes())
    original_hash = file_sha256(original)
    assert file_sha256(copied) == original_hash
    environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "OMP_NUM_THREADS": "1",
                   "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "PYTHONPATH": str(project_root / "src")}
    result = {"project_root": project_root, "workspace": workspace, "original": original, "copied": copied,
              "original_hash": original_hash, "environment": environment}
    write_evidence(workspace / "entry_identity.json", {"source_label": "合成数据 / 已知 DGP",
        "original_cli": str(original), "copied_cli": str(copied), "original_sha256": original_hash,
        "copied_sha256": file_sha256(copied), "formal_repetitions_completed": 0})
    return result


def run_actual_cli(workspace: dict, scenario_id: str, *, expected_exit: int = 0) -> tuple[Path | None, dict]:
    settings = load_v3_data_config()
    rep_id = int(settings.require("validation.representative_rep"))
    log_root = workspace["workspace"] / "logs" / scenario_id
    log_root.mkdir(parents=True)
    command = [str(workspace["project_root"] / ".venv/Scripts/python.exe"), str(workspace["copied"]),
               "--scenario", scenario_id, "--rep", str(rep_id), "--n", str(settings.require("validation.smoke_n"))]
    before = {"original": file_sha256(workspace["original"]), "copied": file_sha256(workspace["copied"])}
    completed = subprocess.run(command, cwd=workspace["workspace"], env=workspace["environment"],
                               capture_output=True, text=True, encoding="utf-8", check=False)
    (log_root / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (log_root / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    after = {"original": file_sha256(workspace["original"]), "copied": file_sha256(workspace["copied"])}
    evidence = {"source_label": "合成数据 / 已知 DGP", "scenario_id": scenario_id, "command": command,
                "cli_hashes_before": before, "cli_hashes_after": after, "returncode": completed.returncode,
                "stdout_path": str(log_root / "stdout.log"), "stderr_path": str(log_root / "stderr.log"),
                "formal_repetitions_completed": 0}
    write_evidence(log_root / "execution.json", evidence)
    assert before == after == {"original": workspace["original_hash"], "copied": workspace["original_hash"]}
    assert completed.returncode == expected_exit, (completed.stdout, completed.stderr)
    if expected_exit:
        assert "Phase D MDE calibration" in completed.stderr
        return None, evidence
    manifests = list((workspace["workspace"] / "data/v3" / settings.require("io.engineering_namespace")
                      / scenario_id / f"rep_{rep_id}").glob("*/manifest.json"))
    assert len(manifests) == 1
    return manifests[0], evidence


def check_canonical_cli_artifacts(manifest_path: Path, execution: dict) -> dict:
    manifest = read_json(manifest_path)
    cfg = load_v3_protocol().scenario(execution["scenario_id"])
    settings = load_v3_data_config()
    canonical = stream_prefix(cfg, "history")
    directory = manifest_path.parent
    relative = directory.relative_to(directory.parents[5] / "data/v3")
    workspace_root = directory.parents[5]
    sealed_directory = workspace_root / "audit/v3" / relative
    generator = read_json(sealed_directory / "generator_metadata.json")
    sealed = read_json(sealed_directory / "manifest.json")
    assert manifest["status"] == sealed["status"] == "passed"
    assert manifest["stream_prefix"] == generator["stream_prefix"] == canonical
    assert manifest["split_stream"] == f"{canonical}.split"
    assert manifest["n_actual"] == generator["n_users"] == settings.require("validation.smoke_n")
    assert manifest["n_registered"] == cfg.require("design.n_total")
    assert manifest["formal_repetitions_completed"] == 0 and sealed["checks"]["released_to_analysis"] is False
    assert sealed["observed_manifest_sha256"] == file_sha256(manifest_path)
    raw = pd.read_parquet(directory / "raw/users.parquet")
    dirty = pd.read_parquet(directory / "dirty/users.parquet")
    seed, rep_id = int(cfg.require("project.master_seed")), int(manifest["rep_id"])
    enabled = bool(cfg.require("data.dirty.enabled"))
    rates = raw.channel.map(cfg.section("data.dirty.cart_missing_by_channel")).to_numpy(dtype=float)
    probabilities = rates * float(cfg.require("data.dirty.missing_rate_multiplier"))
    missing = (child_rng(seed, f"{canonical}.dirty.cart_missing", rep_id).random(len(raw)) < probabilities) & enabled
    fraud = (child_rng(seed, f"{canonical}.dirty.hist_fraud", rep_id).random(len(raw))
             < float(cfg.require("data.dirty.fraud_user_rate"))) & enabled
    expected_cart = raw.cart_value_cent.copy(deep=True)
    expected_cart.loc[missing] = pd.NA
    expected_hist = raw.hist_gmv.copy(deep=True)
    expected_hist.loc[fraud] *= float(cfg.require("data.dirty.fraud_hist_gmv_multiplier"))
    pd.testing.assert_series_equal(dirty.cart_value_cent, expected_cart)
    pd.testing.assert_series_equal(dirty.hist_gmv, expected_hist)
    stages = read_json(directory / "lineage/stages.json")
    assert stages["pollution"]["cart_missing_injected"] == int(missing.sum())
    assert stages["pollution"]["hist_fraud_injected"] == int(fraud.sum())
    assignments = pd.read_parquet(directory / "dirty/coupon_assignment.parquet")
    delay_days = (float(cfg.require("data.dirty.ingestion_delay_max_hours"))
                  / float(settings.require("time.hours_per_day"))) if enabled else 0.0
    positions = pd.Index(raw.user_id).get_indexer(assignments.user_id)
    expected_arrivals = assignments.assignment_day.to_numpy() + (
        child_rng(seed, f"{canonical}.dirty.assignment_ingestion", rep_id).random(len(raw))[positions] * delay_days)
    assert np.array_equal(assignments.ingested_day.to_numpy(), expected_arrivals)
    observed = ObservedDataset.from_manifest(manifest_path, cfg).observations
    expected_split = assign_user_splits(observed, cfg, master_seed=seed, stream=f"{canonical}.split", index=rep_id)
    pd.testing.assert_series_equal(observed.split.reset_index(drop=True), expected_split.assignments.split)
    saved_split = read_json(directory / "lineage/splits.json")
    assert saved_split == expected_split.manifest
    training = observed.loc[expected_split.assignments.split.eq("train")].copy()
    state = read_json(directory / "preprocessing/state.json")
    assert state["training_user_key_hash"] == user_key_hash(training)
    replayed_preprocessor = fit_preprocessor(training, cfg, role="train")
    assert state == replayed_preprocessor.to_dict()
    features = pd.read_parquet(directory / "preprocessing/features.parquet")
    replayed_features = replayed_preprocessor.transform(observed)
    assert np.array_equal(features.loc[:, list(replayed_features.feature_names)].to_numpy(), replayed_features.matrix)
    evidence = {**execution, "observed_manifest": str(manifest_path), "sealed_manifest": str(sealed_directory / "manifest.json"),
        "canonical_stream_prefix": canonical, "pipeline_stream_prefix": manifest["stream_prefix"],
        "generator_stream_prefix": generator["stream_prefix"], "n_actual": len(raw),
        "cart_missing_selected": int(missing.sum()), "hist_fraud_selected": int(fraud.sum()),
        "hist_fraud_changed": int((raw.hist_gmv != dirty.hist_gmv).sum()),
        "split_stream": saved_split["stream"], "preprocessor_training_n": state["training_n"],
        "canonical_mask_values_arrivals_split_preprocessor_verified": True}
    write_evidence(workspace_root / "logs" / execution["scenario_id"] / "verification.json", evidence)
    write_evidence(workspace_root / "cli_delivery.json", {"source_label": "合成数据 / 已知 DGP",
        "cli_sha256": execution["cli_hashes_after"]["original"],
        "runs": [read_json(path) for path in sorted(workspace_root.glob("logs/*/verification.json"))],
        "formal_repetitions_completed": 0})
    return evidence


@pytest.mark.parametrize("scenario_pair", [("L0_P_main", "L0_Pi_equal_cost"), ("L3_fixed_lt000", "L3_fixed_lt050")])
def test_real_cli_preserves_paired_canonical_streams(cli_workspace: dict, scenario_pair: tuple[str, str]) -> None:
    results = []
    for scenario_id in scenario_pair:
        manifest, execution = run_actual_cli(cli_workspace, scenario_id)
        results.append((manifest, check_canonical_cli_artifacts(manifest, execution)))
    assert results[0][1]["canonical_stream_prefix"] == results[1][1]["canonical_stream_prefix"]
    events = [pd.read_parquet(path.parent / "raw/user_events.parquet").drop(columns="run_id") for path, _ in results]
    pd.testing.assert_frame_equal(events[0], events[1])
    pair_name = "__".join(scenario_pair)
    write_evidence(cli_workspace["workspace"] / f"pair_{pair_name}.json", {
        "source_label": "合成数据 / 已知 DGP", "scenario_pair": list(scenario_pair), "raw_events_match_without_run_id": True,
        "events": len(events[0]), "results": [result for _, result in results], "formal_repetitions_completed": 0})
    print(f"CLI integration evidence: {cli_workspace['workspace'] / f'pair_{pair_name}.json'}")


def test_real_cli_rejects_uncalibrated_power_template_before_writing(cli_workspace: dict) -> None:
    protocol = load_v3_protocol()
    scenario = protocol.config.require("design_power_jobs")[0]["id"]
    assert protocol.scenario(scenario).require("design.local_power.active_mde_multiplier") is not None
    before = {str(path) for path in cli_workspace["workspace"].glob("**/manifest.json")}
    manifest, execution = run_actual_cli(cli_workspace, scenario, expected_exit=2)
    assert manifest is None
    assert {str(path) for path in cli_workspace["workspace"].glob("**/manifest.json")} == before
    write_evidence(cli_workspace["workspace"] / "power_rejection.json", {**execution, "no_manifest_created": True})
