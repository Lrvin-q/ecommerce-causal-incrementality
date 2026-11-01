"""Write-only separated simulation state, unavailable through observed readers."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from causal_growth.config import Config
from causal_growth.data.v3_storage import RunArtifactWriter, dataframe_sha256, file_sha256, validate_artifact_path
from causal_growth.dgp.v3_engine import V3Population


def archive_sealed_population(population: V3Population, cfg: Config, *, directory: str | Path,
                              observed_manifest: str | Path) -> Path:
    """Retain DGP-only audit state separately without computing or releasing truth.

    Phase F must verify frozen policies AND observed evaluation results before
    introducing any reader for these files. This write path does not certify that
    release gate and is never imported by the observed five-table pipeline.
    """
    manifest = validate_artifact_path(observed_manifest, role="observed_sql")
    observed_record = json.loads(manifest.read_text(encoding="utf-8"))
    hashes = {"users": dataframe_sha256(population.users),
              "assignments": dataframe_sha256(population.assignments),
              "factual_orders": dataframe_sha256(population.observed_orders)}
    if (population.metadata["config_hash"] != cfg.hash(64) or observed_record.get("config_hash") != cfg.hash(64)
            or observed_record.get("status") != "passed" or observed_record.get("source_observation_hashes") != hashes
            or observed_record.get("n_actual") != len(population.users)
            or observed_record.get("rep_id") != population.metadata["rep_id"]
            or observed_record.get("population_kind") != population.metadata["population_kind"]):
        raise ValueError("sealed population does not match the completed observed run")
    writer = RunArtifactWriter(Path(directory), {
        "config_hash": cfg.hash(64), "scenario_id": cfg.require("active_scenario.id"),
        "observed_manifest": str(manifest), "observed_manifest_sha256": file_sha256(manifest),
        "audit_release_state": "sealed_pending_frozen_policy_and_observed_results",
        "purpose": "retained_simulation_state_not_learning_input",
    }, role="audit")
    try:
        writer.write_frame("original_users.parquet", population.users, role="audit")
        probabilities = population.audit_probabilities
        state = pd.DataFrame({
            "user_id": population.users.user_id.to_numpy(), "U": population.audit_u,
            "true_propensity": population.audit_true_propensity,
            "goods_cost_ratio": population.audit_goods_cost_ratio,
            "redemption_probability": population.audit_redemption_probability,
            "p0_given_xu": probabilities.p0_conditional, "p1_given_xu": probabilities.p1_conditional,
        })
        writer.write_frame("private_state.parquet", state, role="audit")
        for action, orders in population.audit_potential_orders.items():
            writer.write_frame(f"potential_orders_{action}.parquet", orders, role="audit")
        if population.audit_control is not None:
            writer.write_frame("control_parameters.parquet", population.audit_control, role="audit")
        writer.write_json("generator_metadata.json", population.metadata, role="audit")
        writer.write_json("calibration_metadata.json",
                          {"calibration": asdict(probabilities.calibration) if probabilities.calibration is not None else None},
                          role="audit")
        return writer.finish(passed=True, checks={"released_to_analysis": False,
                                                "conditional_truth_computed_here": False})
    except Exception as exc:
        writer.finish(passed=False, checks={"released_to_analysis": False}, error=f"{type(exc).__name__}: {exc}")
        raise
