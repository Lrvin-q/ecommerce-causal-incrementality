"""Checked SQL-only dataset boundary for learning and observed policy evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

from causal_growth.config import Config
from causal_growth.data.v3_split import assign_user_splits
from causal_growth.data.v3_sql import ANALYSIS_COLUMNS, SqlAnalysisResult, sql_source_hash
from causal_growth.data.v3_storage import dataframe_sha256, read_verified_frame, validate_artifact_path
from causal_growth.v3_data_config import load_v3_data_config


_SQL_TOKEN = object()


def _check_frame(frame: pd.DataFrame, *, diagnostic: bool) -> None:
    if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
        raise TypeError("observations require a DataFrame with unique columns")
    if tuple(frame.columns) != tuple(ANALYSIS_COLUMNS):
        raise ValueError("observed SQL column whitelist or column order mismatch")
    patterns = load_v3_data_config().require("isolation.forbidden_column_patterns")
    if any(re.search(pattern, str(column)) for pattern in patterns for column in frame.columns):
        raise ValueError("audit, potential or true-effect columns cannot enter observations")
    if frame[["run_id", "user_id"]].isna().any().any() or frame.duplicated(["run_id", "user_id"]).any():
        raise ValueError("observed users must be unique within each run")
    if not diagnostic and (not frame.mature.astype(bool).all() or frame.diagnostic_snapshot.astype(bool).any()):
        raise ValueError("immature snapshots cannot enter the primary observed dataset")
    if not frame.actual_action.isin([0, 1]).all():
        raise ValueError("actual coupon action must be binary")
    policy_rows = frame.assigned_policy_arm.notna()
    if policy_rows.any():
        if (not policy_rows.all() or not frame.treatment.eq(frame.assigned_policy_arm).all()
                or not frame.policy_arm_probability.between(0, 1, inclusive="right").all()):
            raise ValueError("policy validation requires complete randomized arm labels and probabilities")
    elif not frame.treatment.isin([0, 1]).all():
        raise ValueError("historical treatment label must be binary")


@dataclass(frozen=True)
class ObservedDataset:
    """An immutable API view of validated observations, with no audit inputs.

    Construct through from_sql_result/from_manifest. Callers receive copies of
    the observation frame; later learners must accept this type, not a simulator.
    This is an accidental-leakage boundary, not a sandbox against malicious code
    with arbitrary filesystem and Python execution access.
    """

    _frame: pd.DataFrame = field(repr=False)
    config_hash: str
    data_config_hash: str
    sql_sha256: str
    source_path: str
    diagnostic: bool = False
    lineage: dict[str, Any] = field(default_factory=dict)
    _token: object = field(default=None, repr=False, compare=False)
    _content_hash: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self._token is not _SQL_TOKEN:
            raise TypeError("ObservedDataset must originate from verified SQL output")
        validate_artifact_path(self.source_path, role="observed_sql")
        _check_frame(self._frame, diagnostic=self.diagnostic)
        object.__setattr__(self, "_frame", self._frame.copy(deep=True))
        object.__setattr__(self, "lineage", json.loads(json.dumps(self.lineage, ensure_ascii=False)))
        object.__setattr__(self, "_content_hash", dataframe_sha256(self._frame))

    @classmethod
    def from_sql_result(cls, result: SqlAnalysisResult, cfg: Config, *, allow_diagnostic: bool = False) -> ObservedDataset:
        """Verify producer, version and original SQL fingerprint before exposing data."""
        if not isinstance(result, SqlAnalysisResult):
            raise TypeError("learning requires a SqlAnalysisResult, not an arbitrary frame or population")
        if result.config_hash != cfg.hash(64) or result.data_config_hash != load_v3_data_config().hash(64):
            raise ValueError("SQL output configuration does not match the requested dataset")
        if result.sql_sha256 != sql_source_hash() or result.analysis_sha256 != dataframe_sha256(result.analysis):
            raise ValueError("SQL source or observation content changed after materialization")
        if result.diagnostic_snapshot and not allow_diagnostic:
            raise ValueError("diagnostic snapshots need explicit permission and cannot become primary data")
        source = str(result.database_path or Path.cwd() / "data" / "v3" / "in_memory_sql")
        return cls(result.analysis, result.config_hash, result.data_config_hash, result.sql_sha256, source,
                   result.diagnostic_snapshot,
                   {"producer": "v3_sql", "raw_sql_dataframe_sha256": result.analysis_sha256,
                    "input_users_n": result.input_users_n, "visible_assigned_n": result.visible_assigned_n}, _SQL_TOKEN)

    @classmethod
    def from_manifest(cls, manifest_path: str | Path, cfg: Config, *, relative_path: str = "sql/analysis.parquet",
                      allow_diagnostic: bool = False) -> ObservedDataset:
        """Restore observation data after verifying its immutable run artifact record."""
        path = validate_artifact_path(manifest_path, role="observed_sql")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        frame = read_verified_frame(path, relative_path)
        if manifest.get("config_hash") != cfg.hash(64) or manifest.get("data_config_hash") != load_v3_data_config().hash(64):
            raise ValueError("persisted dataset configuration mismatch")
        if manifest.get("sql_sha256") != sql_source_hash() or manifest.get("analysis_producer") != "v3_sql":
            raise ValueError("persisted dataset lacks current SQL provenance")
        diagnostic = bool(frame.diagnostic_snapshot.any())
        if diagnostic and not allow_diagnostic:
            raise ValueError("diagnostic snapshots cannot enter the primary dataset")
        return cls(frame, cfg.hash(64), manifest["data_config_hash"], manifest["sql_sha256"], str(path),
                   diagnostic, manifest.get("analysis_lineage", {}), _SQL_TOKEN)

    @property
    def content_hash(self) -> str:
        """Return the bound observation fingerprint after checking internal integrity."""
        if dataframe_sha256(self._frame) != self._content_hash:
            raise ValueError("observed dataset was modified outside its checked API")
        return self._content_hash

    @property
    def population_kind(self) -> str:
        """Distinguish randomized policy validation from historical binary learning."""
        self.content_hash
        return "validation" if self._frame.assigned_policy_arm.notna().any() else "history"

    def require_history(self) -> None:
        """Reject independent policy validation or diagnostic snapshots as training data."""
        if self.population_kind != "history" or self.diagnostic:
            raise ValueError("learning requires primary historical binary observations")

    @property
    def observations(self) -> pd.DataFrame:
        """Return a copy; modifications cannot alter the shared model input dataset."""
        self.content_hash
        result = self._frame.copy(deep=True)
        result.attrs.update(source_path=self.source_path, config_hash=self.config_hash,
                            observed_dataset_hash=self._content_hash,
                            population_kind=self.population_kind, diagnostic_snapshot=self.diagnostic)
        return result

    def assign_splits(self, cfg: Config, *, stream: str, index: int) -> tuple[ObservedDataset, dict[str, Any]]:
        """Derive only the frozen user split, without accepting arbitrary replacement data."""
        self.require_history()
        if cfg.hash(64) != self.config_hash:
            raise ValueError("split assignment requires a matching primary observation dataset")
        frame = self.observations
        split = assign_user_splits(frame, cfg, master_seed=int(cfg.require("project.master_seed")), stream=stream, index=index)
        labels = split.assignments.set_index(["run_id", "user_id"]).split
        frame["split"] = labels.reindex(pd.MultiIndex.from_frame(frame[["run_id", "user_id"]])).to_numpy()
        child = ObservedDataset(frame, self.config_hash, self.data_config_hash, self.sql_sha256, self.source_path,
                                False, {**self.lineage, "split_manifest": split.manifest}, _SQL_TOKEN)
        return child, split.manifest

    def select_split(self, split: str) -> ObservedDataset:
        """Restrict to a preassigned role; never rewrite a test user as training data."""
        self.require_history()
        if split not in {"train", "validation", "test"}:
            raise ValueError("unknown analysis split")
        frame = self.observations
        selected = frame.loc[frame.split == split].reset_index(drop=True)
        if selected.empty:
            raise ValueError(f"no users assigned to {split}")
        return ObservedDataset(selected, self.config_hash, self.data_config_hash, self.sql_sha256, self.source_path,
                               self.diagnostic, {**self.lineage, "selected_split": split}, _SQL_TOKEN)
