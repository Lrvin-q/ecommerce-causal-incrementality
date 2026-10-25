"""合成数据 / 已知 DGP：Phase C 工程参数校验，不改变冻结业务矩阵。"""

from pathlib import Path

import pytest
import yaml

from causal_growth.config import ConfigError
from causal_growth.v3_data_config import load_v3_data_config


def _changed(tmp_path: Path, key: str, value) -> Path:
    document = load_v3_data_config().to_dict()
    node = document
    parts = key.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value
    target = tmp_path / "data_config.yaml"
    target.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return target


def test_default_engineering_config_is_separate_and_does_not_advance_R():
    cfg = load_v3_data_config()
    assert cfg.require("validation.formal_repetitions_completed") == 0
    assert cfg.require("io.parquet_engine") == "pyarrow"
    assert cfg.require("io.compression") == "zstd"
    assert {"audit", "truth"}.issubset(cfg.require("isolation.forbidden_path_segments"))
    assert cfg.require("isolation.audit_requires_policy_and_observed_results_frozen") is True
    assert cfg.hash(64) == load_v3_data_config().hash(64)


@pytest.mark.parametrize("key", ["time.hours_per_day", "events.pre_assignment_window_days", "sql.insert_chunk_size", "sql.busy_timeout_seconds"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_positive_controls_reject_nonfinite_and_nonpositive(tmp_path, key, value):
    with pytest.raises(ConfigError):
        load_v3_data_config(_changed(tmp_path, key, value))


@pytest.mark.parametrize("key,value", [
    ("events.cart_event_offset_days", 1),
    ("events.cap_scope", "last_events"),
    ("preprocessing.unknown_channel_policy", "silent_zero"),
    ("validation.formal_repetitions_completed", 1),
    ("validation.formal_repetitions_completed", -1),
    ("validation.formal_repetitions_completed", 0.5),
    ("sql.insert_chunk_size", 0.5),
])
def test_unsupported_semantics_and_noninteger_counts_rejected(tmp_path, key, value):
    with pytest.raises(ConfigError):
        load_v3_data_config(_changed(tmp_path, key, value))


@pytest.mark.parametrize("source", ["- invalid\n- root\n", "time:\n  hours_per_day: 24\n  hours_per_day: 48\n"])
def test_mapping_and_duplicate_key_validation(tmp_path, source):
    path = tmp_path / "invalid.yaml"
    path.write_text(source, encoding="utf-8")
    with pytest.raises((ConfigError, yaml.YAMLError)):
        load_v3_data_config(path)


def test_engineering_parameter_change_changes_only_its_own_hash(tmp_path):
    original = load_v3_data_config()
    changed = load_v3_data_config(_changed(tmp_path, "sql.insert_chunk_size", original.require("sql.insert_chunk_size") + 1))
    assert original.hash(64) != changed.hash(64)
    assert original.hash(64) == load_v3_data_config().hash(64)
