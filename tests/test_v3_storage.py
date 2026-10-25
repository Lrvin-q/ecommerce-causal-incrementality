"""合成数据 / 已知 DGP：独立核对不可变存储与来源隔离边界。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from causal_growth.data.v3_storage import (
    RunArtifactWriter, dataframe_sha256, file_sha256, read_verified_frame, validate_artifact_path,
)


@pytest.fixture
def frame() -> pd.DataFrame:
    """Small storage fixture, not an experimental population or formal repetition."""
    return pd.DataFrame({
        "user_id": pd.Series([1, 2, 3], dtype="Int64"),
        "nullable_cents": pd.Series([0, pd.NA, 123], dtype="Int64"),
        "channel": pd.Series(["搜索", pd.NA, "feed"], dtype="string"),
        "nullable_float": pd.Series([1 / 3, pd.NA, -0.0], dtype="Float64"),
        "float64": np.array([np.nextafter(1.0, 2.0), np.nan, -1.25]),
        "nullable_bool": pd.Series([True, pd.NA, False], dtype="boolean"),
    })


def _saved(tmp_path: Path, frame: pd.DataFrame, *, role: str = "observed_sql") -> tuple[RunArtifactWriter, Path]:
    writer = RunArtifactWriter(tmp_path / "run", {"config_hash": "test-config", "data_config_hash": "test-data"})
    writer.write_frame("sql/analysis.parquet", frame, role=role)
    return writer, writer.finish(passed=True, checks={"roundtrip": True})


def _edit_manifest(path: Path, edit) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    edit(value)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_parquet_nullable_string_float_roundtrip_and_metadata(tmp_path, frame):
    writer, manifest = _saved(tmp_path, frame)
    actual = read_verified_frame(manifest, "sql/analysis.parquet")
    pd.testing.assert_frame_equal(actual, frame, check_exact=True)
    assert dataframe_sha256(actual) == dataframe_sha256(frame)
    path = writer.directory / "sql/analysis.parquet"
    metadata = pq.read_schema(path).metadata
    assert metadata[b"source_label"].decode("utf-8") == "合成数据 / 已知 DGP"
    assert metadata[b"artifact_role"] == b"observed_sql"
    assert metadata[b"config_hash"] == b"test-config"
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert saved["status"] == "passed" and saved["formal_repetitions_completed"] == 0
    assert saved["artifacts"]["sql/analysis.parquet"]["sha256"] == file_sha256(path)


@pytest.mark.parametrize("change", ["values", "dtype", "columns", "row_order"])
def test_dataframe_fingerprint_binds_data_dtype_column_and_row_order(frame, change):
    other = frame.copy()
    if change == "values":
        other.loc[0, "nullable_cents"] = 1
    elif change == "dtype":
        other["user_id"] = other.user_id.astype("int64")
    elif change == "columns":
        other = other.iloc[:, ::-1]
    else:
        other = other.iloc[::-1]
    assert dataframe_sha256(frame) != dataframe_sha256(other)
    assert dataframe_sha256(frame) == dataframe_sha256(frame.set_axis([8, 9, 10]))


@pytest.mark.parametrize("mutation", ["byte_hash", "data_hash", "rows", "columns", "role", "namespace"])
def test_manifest_forgery_is_rejected(tmp_path, frame, mutation):
    _, manifest = _saved(tmp_path, frame)
    def edit(value):
        record = value["artifacts"]["sql/analysis.parquet"]
        if mutation == "byte_hash":
            record["sha256"] = "0" * 64
        elif mutation == "data_hash":
            record["dataframe_sha256"] = "0" * 64
        elif mutation == "rows":
            record["rows"] += 1
        elif mutation == "columns":
            record["columns"] = ["forged_schema"]
        elif mutation == "role":
            record["role"] = "audit"
        else:
            value["artifact_namespace"] = "audit"
    _edit_manifest(manifest, edit)
    with pytest.raises(ValueError):
        read_verified_frame(manifest, "sql/analysis.parquet")


@pytest.mark.parametrize("change", ["value", "dtype", "column_order"])
def test_changed_parquet_rejected_even_if_file_byte_hash_is_refreshed(tmp_path, frame, change):
    writer, manifest = _saved(tmp_path, frame)
    changed = frame.copy()
    if change == "value":
        changed.loc[0, "nullable_cents"] = 1
    elif change == "dtype":
        changed["user_id"] = changed.user_id.astype("int64")
    else:
        changed = changed.iloc[:, ::-1]
    path = writer.directory / "sql/analysis.parquet"
    changed.to_parquet(path, index=False)
    _edit_manifest(manifest, lambda value: value["artifacts"]["sql/analysis.parquet"].update(sha256=file_sha256(path)))
    with pytest.raises(ValueError):
        read_verified_frame(manifest, "sql/analysis.parquet")


@pytest.mark.parametrize("key,value", [(b"artifact_role", b"audit"), (b"config_hash", b"different-config")])
def test_embedded_parquet_provenance_must_agree_with_manifest(tmp_path, frame, key, value):
    writer, manifest = _saved(tmp_path, frame)
    path = writer.directory / "sql/analysis.parquet"
    table = pq.read_table(path)
    metadata = {**table.schema.metadata, key: value}
    pq.write_table(table.replace_schema_metadata(metadata), path)
    _edit_manifest(manifest, lambda document: document["artifacts"]["sql/analysis.parquet"].update(sha256=file_sha256(path)))
    with pytest.raises(ValueError):
        read_verified_frame(manifest, "sql/analysis.parquet")


def test_non_sql_frame_cannot_be_relabelled_only_in_manifest(tmp_path, frame):
    _, manifest = _saved(tmp_path, frame, role="clean")
    _edit_manifest(manifest, lambda value: value["artifacts"]["sql/analysis.parquet"].update(role="observed_sql"))
    with pytest.raises(ValueError):
        read_verified_frame(manifest, "sql/analysis.parquet")


@pytest.mark.parametrize("status", ["running", "failed"])
def test_incomplete_or_failed_attempt_cannot_be_read(tmp_path, frame, status):
    writer = RunArtifactWriter(tmp_path / "run", {})
    writer.write_frame("sql/analysis.parquet", frame, role="observed_sql")
    if status == "failed":
        writer.finish(passed=False, checks={}, error="test failure retained")
    with pytest.raises(ValueError, match="completed"):
        read_verified_frame(writer.directory / "manifest.json", "sql/analysis.parquet")
    assert (writer.directory / "sql/analysis.parquet").is_file()


@pytest.mark.parametrize("passed", [False, True])
def test_terminal_attempt_immutable_through_every_writer_entry(tmp_path, frame, passed):
    writer = RunArtifactWriter(tmp_path / "run", {})
    writer.write_frame("sql/analysis.parquet", frame, role="observed_sql")
    external = writer.directory / "observed.sqlite"
    external.write_bytes(b"test existing artifact")
    writer.finish(passed=passed, checks={}, error=None if passed else "retained failure")
    before = (writer.directory / "manifest.json").read_bytes()
    actions = [
        lambda: writer.write_frame("new.parquet", frame, role="observed_sql"),
        lambda: writer.write_json("new.json", {"key": "value"}, role="preprocessing"),
        lambda: writer.register_existing("observed.sqlite", role="observed_sql"),
        lambda: writer.finish(passed=True, checks={}),
    ]
    for action in actions:
        with pytest.raises(ValueError, match="terminal|immutable"):
            action()
        assert (writer.directory / "manifest.json").read_bytes() == before


def test_existing_attempt_or_file_is_never_overwritten(tmp_path, frame):
    writer = RunArtifactWriter(tmp_path / "run", {})
    with pytest.raises(FileExistsError):
        RunArtifactWriter(writer.directory, {})
    writer.write_frame("sql/analysis.parquet", frame, role="observed_sql")
    before = (writer.directory / "sql/analysis.parquet").read_bytes()
    with pytest.raises(FileExistsError):
        writer.write_frame("sql/analysis.parquet", frame, role="observed_sql")
    assert (writer.directory / "sql/analysis.parquet").read_bytes() == before


@pytest.mark.parametrize("field", ["status", "artifacts", "formal_repetitions_completed"])
def test_lifecycle_metadata_cannot_override_writer(tmp_path, field):
    with pytest.raises(ValueError):
        RunArtifactWriter(tmp_path / "run", {field: 1})
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("relative", ["../outside.parquet", "audit/leak.parquet", "truth.parquet", "TRUTH/leak.parquet"])
def test_observation_writer_rejects_path_escape_and_truth_paths(tmp_path, frame, relative):
    writer = RunArtifactWriter(tmp_path / "run", {})
    with pytest.raises(ValueError):
        writer.write_frame(relative, frame, role="observed_sql")


def test_reader_rejects_path_escape_even_with_forged_manifest_record(tmp_path, frame):
    writer, manifest = _saved(tmp_path, frame)
    outside = tmp_path / "outside.parquet"
    outside.write_bytes((writer.directory / "sql/analysis.parquet").read_bytes())
    _edit_manifest(manifest, lambda value: value["artifacts"].update({"../outside.parquet": value["artifacts"]["sql/analysis.parquet"]}))
    with pytest.raises(ValueError, match="escapes"):
        read_verified_frame(manifest, "../outside.parquet")


def test_audit_and_observed_writer_namespaces_do_not_mix(tmp_path, frame):
    with pytest.raises(ValueError):
        RunArtifactWriter(tmp_path / "not_audit", {}, role="audit")
    audit = RunArtifactWriter(tmp_path / "audit" / "run", {}, role="audit")
    audit.write_frame("truth.parquet", frame, role="audit")
    with pytest.raises(ValueError):
        audit.write_frame("observed.parquet", frame, role="observed_sql")
    with pytest.raises(ValueError):
        read_verified_frame(audit.directory / "manifest.json", "truth.parquet", role="audit")
    with pytest.raises(ValueError):
        validate_artifact_path(tmp_path / "test", role="unknown")


def test_modified_artifact_cannot_be_marked_passed_and_failure_is_retained(tmp_path, frame):
    writer = RunArtifactWriter(tmp_path / "run", {})
    writer.write_frame("sql/analysis.parquet", frame, role="observed_sql")
    path = writer.directory / "sql/analysis.parquet"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="changed"):
        writer.finish(passed=True, checks={})
    writer.finish(passed=False, checks={}, error="checksum mismatch")
    assert json.loads((writer.directory / "manifest.json").read_text(encoding="utf-8"))["status"] == "failed"
