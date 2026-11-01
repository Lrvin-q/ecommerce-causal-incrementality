"""Immutable run artifacts, fingerprints and manifests for v3 observations.

Synthetic / known DGP. Writing data does not advance formal experiment counters.
Audit and observed artifacts are routed through distinct path checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from causal_growth.v3_data_config import load_v3_data_config


def file_sha256(path: str | Path) -> str:
    """Identify an artifact's exact bytes without loading large files at once."""
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def dataframe_sha256(frame: pd.DataFrame) -> str:
    """Bind SQL output to ordered columns, dtypes and values, excluding its index."""
    header = json.dumps({"columns": frame.columns.tolist(), "dtypes": [str(v) for v in frame.dtypes]},
                        ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(header)
    digest.update(pd.util.hash_pandas_object(frame, index=False, categorize=True).to_numpy().tobytes())
    return digest.hexdigest()


def validate_artifact_path(path: str | Path, *, role: str) -> Path:
    """Reject an audit path as an observation source, including resolved symlinks."""
    target = Path(path).resolve()
    parts = {p.casefold() for p in target.parts} | {target.stem.casefold()}
    forbidden = {str(p).casefold() for p in load_v3_data_config().require("isolation.forbidden_path_segments")}
    if role == "audit":
        if "audit" not in parts:
            raise ValueError("audit artifacts must remain under a separate audit directory")
    elif role in {"raw", "dirty", "clean", "observed_sql", "observed", "preprocessing", "diagnostic"}:
        if parts & forbidden:
            raise ValueError("audit/truth paths cannot be observation sources or destinations")
    else:
        raise ValueError(f"unknown artifact role: {role}")
    return target


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


@dataclass
class RunArtifactWriter:
    """Save a unique attempt and preserve incomplete artifacts on failure.

    Each caller supplies a new directory. Existing runs are never overwritten or
    silently resumed; the later execution registry decides whether reuse is valid.
    """

    directory: Path
    metadata: Mapping[str, Any]
    role: str = "observed"
    _manifest: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.directory = validate_artifact_path(self.directory, role=self.role)
        if {"status", "artifacts", "formal_repetitions_completed"} & self.metadata.keys():
            raise ValueError("run metadata cannot override lifecycle or formal completion fields")
        self.directory.mkdir(parents=True, exist_ok=False)
        self._manifest = {**dict(self.metadata), "source_label": "合成数据 / 已知 DGP",
                          "artifact_namespace": self.role,
                          "status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
                          "formal_repetitions_completed": 0, "artifacts": {}}
        self._flush()

    def _flush(self) -> None:
        _atomic_json(self.directory / "manifest.json", self._manifest)

    def _target(self, relative_path: str, role: str) -> Path:
        if self._manifest["status"] != "running":
            raise ValueError("a terminal run is immutable")
        if (self.role == "audit") != (role == "audit"):
            raise ValueError("audit and observed artifacts cannot share a run writer")
        target = (self.directory / relative_path).resolve()
        if not target.is_relative_to(self.directory) or target == self.directory:
            raise ValueError("artifact path escapes its run directory")
        validate_artifact_path(target, role=role)
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def write_frame(self, relative_path: str, frame: pd.DataFrame, *, role: str) -> dict[str, Any]:
        """Persist full tables or SQL output with lossless compression and source metadata."""
        target = self._target(relative_path, role)
        if target.suffix != ".parquet":
            raise ValueError("lossless table artifacts use parquet")
        settings = load_v3_data_config()
        if settings.require("io.parquet_engine") != "pyarrow":
            raise ValueError("unsupported parquet engine")
        table = pa.Table.from_pandas(frame, preserve_index=False)
        metadata = dict(table.schema.metadata or {})
        metadata.update({b"source_label": "合成数据 / 已知 DGP".encode("utf-8"),
                         b"artifact_role": role.encode("utf-8"),
                         b"config_hash": str(self._manifest.get("config_hash", "")).encode("utf-8")})
        temporary = target.with_suffix(target.suffix + ".tmp")
        pq.write_table(table.replace_schema_metadata(metadata), temporary, compression=settings.require("io.compression"))
        temporary.replace(target)
        record = {"role": role, "sha256": file_sha256(target), "rows": len(frame),
                  "columns": frame.columns.tolist(), "dataframe_sha256": dataframe_sha256(frame)}
        self._manifest["artifacts"][relative_path] = record
        self._flush()
        return record.copy()

    def write_json(self, relative_path: str, value: Mapping[str, Any], *, role: str) -> dict[str, Any]:
        """Save preprocessing state or lineage without inventing experiment success."""
        target = self._target(relative_path, role)
        _atomic_json(target, value)
        record = {"role": role, "sha256": file_sha256(target)}
        self._manifest["artifacts"][relative_path] = record
        self._flush()
        return record.copy()

    def write_csv(self, relative_path: str, frame: pd.DataFrame, *, role: str,
                  source_rows: int | None = None) -> dict[str, Any]:
        """Export readable examples with explicit preview/full row counts and UTF-8 BOM."""
        target = self._target(relative_path, role)
        if target.suffix != ".csv":
            raise ValueError("CSV examples require a .csv filename")
        source_rows = len(frame) if source_rows is None else source_rows
        if isinstance(source_rows, bool) or not isinstance(source_rows, int) or source_rows < len(frame):
            raise ValueError("CSV source row count must include every exported row")
        temporary = target.with_suffix(target.suffix + ".tmp")
        frame.to_csv(temporary, index=False, encoding=load_v3_data_config().require("io.csv_encoding"))
        temporary.replace(target)
        record = {"role": role, "format": "csv", "sha256": file_sha256(target), "rows": len(frame),
                  "source_rows": source_rows, "is_preview": source_rows > len(frame),
                  "columns": frame.columns.tolist(), "source_label": "合成数据 / 已知 DGP"}
        self._manifest["artifacts"][relative_path] = record
        self._flush()
        return record.copy()

    def register_existing(self, relative_path: str, *, role: str) -> dict[str, Any]:
        """Register a SQLite file produced within this attempt by the SQL engine."""
        if self._manifest["status"] != "running":
            raise ValueError("a terminal run is immutable")
        if (self.role == "audit") != (role == "audit"):
            raise ValueError("audit and observed artifacts cannot share a run writer")
        path = (self.directory / relative_path).resolve()
        if not path.is_relative_to(self.directory) or not path.is_file():
            raise ValueError("registered artifact must exist inside the run")
        validate_artifact_path(path, role=role)
        if relative_path in self._manifest["artifacts"]:
            raise ValueError("artifact already registered")
        record = {"role": role, "sha256": file_sha256(path)}
        self._manifest["artifacts"][relative_path] = record
        self._flush()
        return record.copy()

    def finish(self, *, passed: bool, checks: Mapping[str, Any], error: str | None = None) -> Path:
        """Close the attempt while retaining failed files and an explicit failure reason."""
        if self._manifest["status"] != "running":
            raise ValueError("run is already terminal")
        if passed and error:
            raise ValueError("a failed attempt cannot be marked passed")
        if passed:
            for relative, record in self._manifest["artifacts"].items():
                if file_sha256(self.directory / relative) != record["sha256"]:
                    raise ValueError(f"artifact changed before completion: {relative}")
        self._manifest.update(status="passed" if passed else "failed", checks=dict(checks), error=error,
                              finished_at_utc=datetime.now(timezone.utc).isoformat())
        self._flush()
        return self.directory / "manifest.json"


def read_verified_frame(manifest_path: str | Path, relative_path: str, *, role: str = "observed_sql") -> pd.DataFrame:
    """Load an observed table only after path, role, lifecycle and byte/hash checks."""
    if role != "observed_sql":
        raise ValueError("analysis reader only accepts observed SQL artifacts; audit needs a separate release gate")
    manifest_file = validate_artifact_path(manifest_path, role=role)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest["status"] != "passed" or manifest["artifact_namespace"] == "audit":
        raise ValueError("only completed observation artifacts can enter analysis")
    path = (manifest_file.parent / relative_path).resolve()
    if not path.is_relative_to(manifest_file.parent):
        raise ValueError("artifact path escapes manifest directory")
    validate_artifact_path(path, role=role)
    if path.suffix != ".parquet":
        raise ValueError("observed analysis reader requires the lossless parquet artifact, not CSV previews")
    record = manifest["artifacts"][relative_path]
    if record["role"] != role or file_sha256(path) != record["sha256"]:
        raise ValueError("observed artifact role or file hash mismatch")
    metadata = pq.read_metadata(path).metadata or {}
    if (metadata.get(b"artifact_role") != role.encode("utf-8")
            or metadata.get(b"config_hash") != str(manifest.get("config_hash", "")).encode("utf-8")):
        raise ValueError("Parquet source role or configuration differs from the manifest")
    frame = pd.read_parquet(path)
    if (dataframe_sha256(frame) != record["dataframe_sha256"] or len(frame) != record["rows"]
            or frame.columns.tolist() != record["columns"]):
        raise ValueError("observed table content or schema differs from its SQL manifest")
    return frame
