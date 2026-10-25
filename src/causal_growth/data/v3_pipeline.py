"""Observed-only five-table execution and auditable training transformations.

Synthetic / known DGP. This module accepts factual records only. Generation,
latent states, counterfactual outcomes and the independent audit ledger stay
outside this production path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from causal_growth.config import Config
from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_preprocessing import FrozenPreprocessor, fit_preprocessor
from causal_growth.data.v3_quality import validate_tables
from causal_growth.data.v3_sql import SqlAnalysisResult, run_sql_pipeline, sql_source_hash
from causal_growth.data.v3_storage import RunArtifactWriter, dataframe_sha256, file_sha256
from causal_growth.data.v3_tables import build_raw_tables
from causal_growth.v3_data_config import load_v3_data_config


@dataclass(frozen=True)
class DataPipelineResult:
    """Completed observations and engineering evidence; never a formal repetition."""

    dataset: ObservedDataset
    sql: SqlAnalysisResult
    manifest_path: Path
    stage_counts: dict[str, Any]
    preprocessor: FrozenPreprocessor | None


def pipeline_source_hashes() -> dict[str, str]:
    """Bind implementation and engineering settings at both ends of a run."""
    root = Path(__file__).resolve().parents[3]
    files = sorted(set((root / "src" / "causal_growth").rglob("v3*.py"))
                   | set((root / "sql").glob("v3*.sql"))
                   | set((root / "configs").glob("v3*.yaml"))
                   | set((root / "configs" / "v3").glob("*.yaml")))
    return {path.relative_to(root).as_posix(): file_sha256(path) for path in files}


def build_observed_pipeline(
    users: pd.DataFrame, assignments: pd.DataFrame, factual_orders: pd.DataFrame, cfg: Config, *,
    directory: str | Path, run_id: str, rep_id: int, stream_prefix: str,
    population_kind: str = "history", persist_database: bool = False,
    frozen_preprocessor: FrozenPreprocessor | None = None,
    retention_scope: str = "engineering_full",
) -> DataPipelineResult:
    """Execute raw→dirty→deduplicated five tables→SQL→observed training split.

    All outcomes are SQL materializations. Dirty and clean outcome tables share
    the same SQL projection because event duplicates affect neither orders nor
    assignments; that reuse is recorded explicitly. Missing amounts remain
    missing in business tables. Only the separately saved training-fitted model
    transformation imputes or clips features.

    Independent validation receives no split or fit operation. Its optional
    transformer must already have been frozen on historical training users.
    Local-power mechanism cells require Phase D calibration and are refused here
    until a dedicated, reviewed calibration entry point is implemented.
    """
    if population_kind not in {"history", "validation"}:
        raise ValueError("population_kind must be history or validation")
    if retention_scope not in {"engineering_full", "representative_full"}:
        raise ValueError("this full-table entry point cannot save formal nonrepresentative validation runs")
    if cfg.require("design.local_power.active_mde_multiplier") is not None:
        raise ValueError("local-power cells require the Phase D calibrated mechanism entry point")
    if population_kind == "history" and frozen_preprocessor is not None:
        raise ValueError("historical preprocessing must be fitted on this run's training users")
    data_cfg = load_v3_data_config()
    if (population_kind == "validation" and retention_scope == "representative_full"
            and rep_id != data_cfg.require("validation.representative_rep")):
        raise ValueError("full representative validation is restricted to the registered representative rep")
    source_before = pipeline_source_hashes()
    writer = RunArtifactWriter(Path(directory), {
        "run_id": run_id, "scenario_id": cfg.require("active_scenario.id"), "rep_id": rep_id,
        "population_kind": population_kind, "purpose": "engineering_or_downstream_input_not_formal_completion",
        "retention_scope": retention_scope,
        "config_hash": cfg.hash(64), "data_config_hash": data_cfg.hash(64),
        "sql_sha256": sql_source_hash(), "analysis_producer": "v3_sql",
        "source_hashes_before": source_before,
        "source_observation_hashes": {"users": dataframe_sha256(users),
                                     "assignments": dataframe_sha256(assignments),
                                     "factual_orders": dataframe_sha256(factual_orders)},
        "n_registered": cfg.require("design.n_total"), "n_actual": len(users),
        "master_seed": cfg.require("project.master_seed"), "stream_prefix": stream_prefix,
        "split_stream": f"{stream_prefix}.split", "database_persisted": persist_database,
        "analysis_lineage": {"producer": "v3_sql", "source_stage": "clean",
                             "split_source": "sql_observations_history_only"},
    })
    try:
        raw = build_raw_tables(users, assignments, factual_orders, cfg, run_id=run_id,
                               rep_id=rep_id, stream_prefix=stream_prefix)
        dirty_stage = inject_dirt(raw, cfg, rep_id=rep_id, stream_prefix=stream_prefix)
        clean_stage = deduplicate_events(dirty_stage.tables, cfg)
        dirty, clean = dirty_stage.tables, clean_stage.tables
        raw_sql = run_sql_pipeline(raw, cfg)
        raw_dataset = ObservedDataset.from_sql_result(raw_sql, cfg)
        if raw_dataset.population_kind != population_kind:
            raise ValueError("declared population kind disagrees with observed assignment schema")
        if population_kind == "history":
            split_dataset, split_manifest = raw_dataset.assign_splits(cfg, stream=f"{stream_prefix}.split", index=rep_id)
            split_labels = split_dataset.observations.set_index(["run_id", "user_id"]).split
            for tables in (raw, dirty, clean):
                keys = pd.MultiIndex.from_frame(tables["users"][["run_id", "user_id"]])
                tables["users"]["split"] = split_labels.reindex(keys).to_numpy()
        else:
            if not raw["users"].split.eq("test").all():
                raise ValueError("independent validation users must remain held out")
            split_manifest = {"method": "independent_randomized_policy_validation_no_training_split",
                              "n_users": len(users), "counts": {"test": len(users)}}
        database_name = data_cfg.require("io.representative_sqlite_name")
        database_path = writer.directory / database_name if persist_database else None
        clean_sql = run_sql_pipeline(clean, cfg, database_path=database_path)
        dataset = ObservedDataset.from_sql_result(clean_sql, cfg)
        raw["user_outcomes"] = raw_sql.user_outcomes.copy(deep=True)
        clean["user_outcomes"] = clean_sql.user_outcomes.copy(deep=True)
        dirty["user_outcomes"] = clean_sql.user_outcomes.copy(deep=True)
        stage_counts = {
            "raw": validate_tables(raw, cfg, stage="raw", require_outcomes=True),
            "dirty": validate_tables(dirty, cfg, stage="dirty", require_outcomes=True),
            "clean": validate_tables(clean, cfg, stage="clean", require_outcomes=True),
            "pollution": dirty_stage.counts, "repair": clean_stage.counts,
            "outcome_lineage": {
                "raw": "SQL from raw facts before any pollution; outcome schema excludes split",
                "dirty": "same SQL order/assignment projection as clean; deduplication changes events only",
                "clean": "SQL from clean facts; full assigned-user denominator",
            },
        }
        for stage, tables in (("raw", raw), ("dirty", dirty), ("clean", clean)):
            for name, frame in tables.items():
                writer.write_frame(f"{stage}/{name}.parquet", frame, role=stage)
        writer.write_frame("sql/analysis.parquet", dataset.observations, role="observed_sql")
        writer.write_frame("sql/quality.parquet", clean_sql.quality, role="observed_sql")
        for name, frame in clean_sql.summaries.items():
            writer.write_frame(f"sql/{name}.parquet", frame, role="observed_sql")
        writer.write_json("lineage/stages.json", stage_counts, role="observed")
        writer.write_json("lineage/splits.json", split_manifest, role="observed")
        transformer = frozen_preprocessor
        if population_kind == "history":
            transformer = fit_preprocessor(dataset.select_split("train").observations, cfg, role="train")
        if transformer is not None:
            if transformer.to_dict()["config_hash"] != cfg.hash(64):
                raise ValueError("frozen validation transformer belongs to a different scenario configuration")
            observations = dataset.observations
            transformed = transformer.transform(observations)
            features = pd.DataFrame(transformed.matrix, columns=transformed.feature_names)
            features.insert(0, "user_id", observations.user_id.to_numpy())
            features.insert(0, "run_id", observations.run_id.to_numpy())
            writer.write_frame("preprocessing/features.parquet", features, role="preprocessing")
            writer.write_json("preprocessing/state.json", transformer.to_dict(), role="preprocessing")
            writer.write_json("preprocessing/transform_log.json", transformed.log, role="preprocessing")
        if database_path is not None:
            writer.register_existing(database_name, role="observed_sql")
            writer.write_csv("examples/analysis_preview.csv",
                             dataset.observations.head(int(data_cfg.require("io.csv_preview_rows"))),
                             role="observed_sql", source_rows=len(users))
            for name in ("groups", "cost_ledger"):
                writer.write_csv(f"examples/{name}.csv", clean_sql.summaries[name], role="observed_sql")
        source_after = pipeline_source_hashes()
        if source_before != source_after:
            raise RuntimeError("source files changed during the data run; retain this attempt as failed")
        writer.write_json("lineage/source_hashes_after.json", source_after, role="observed")
        manifest = writer.finish(passed=True, checks={
            "full_denominator": len(dataset.observations) == len(users),
            "two_windows_per_user": len(clean_sql.user_outcomes) == 2 * len(users),
            "source_hashes_unchanged": True, "sql_quality_passed": True,
            "formal_repetitions_completed": 0,
        })
        return DataPipelineResult(dataset, clean_sql, manifest, stage_counts, transformer)
    except Exception as exc:
        writer.finish(passed=False, checks={"formal_repetitions_completed": 0}, error=f"{type(exc).__name__}: {exc}")
        raise
