"""Engineering settings for the v3 five-table and isolation pipeline."""

from pathlib import Path
import math

import yaml

from causal_growth.config import Config, ConfigError
from causal_growth.v3_config import _UniqueKeyLoader


def load_v3_data_config(path: str | Path | None = None) -> Config:
    """Load Phase C engineering controls with duplicate-key and boundary validation.

    The file is versioned separately from the approved business/experiment matrix;
    manifests must record both hashes instead of silently folding it into Phase A.
    """
    source = Path(path) if path is not None else Path(__file__).resolve().parents[2] / "configs" / "v3_data.yaml"
    raw = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(raw, dict):
        raise ConfigError("v3 data configuration must be a mapping")
    cfg = Config(raw, name="v3_data")
    for key in ("time.hours_per_day", "events.pre_assignment_window_days", "sql.insert_chunk_size", "sql.busy_timeout_seconds"):
        value = cfg.require(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ConfigError(f"{key} must be positive and finite")
    for key in ("sql.insert_chunk_size", "validation.per_scenario_n", "validation.representative_n",
                "validation.smoke_n", "validation.independent_validation_n", "io.csv_preview_rows"):
        value = cfg.require(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ConfigError(f"{key} must be a positive integer")
    offset = cfg.require("events.cart_event_offset_days")
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset) or offset > 0:
        raise ConfigError("eligibility event must be known no later than assignment")
    if cfg.require("events.cap_scope") != "all_pre_assignment_events_first_chronological":
        raise ConfigError("unsupported event truncation semantics")
    if cfg.require("preprocessing.unknown_channel_policy") != "error":
        raise ConfigError("unknown channels require an explicit supported policy")
    completed = cfg.require("validation.formal_repetitions_completed")
    if isinstance(completed, bool) or not isinstance(completed, int) or completed != 0:
        raise ConfigError("engineering checks cannot advance formal repetitions")
    return cfg
