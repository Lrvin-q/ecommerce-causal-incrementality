"""Load and audit the frozen v3 protocol before any simulation can run.

This module answers whether every requested scenario, model and repetition is
explicit, and prevents a typo or stale hand-written count from changing scope.
It does not implement or run an experiment.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from causal_growth.config import Config, ConfigError

CONFIG_FILES = (
    "business.yaml", "design.yaml", "models.yaml", "policy.yaml",
    "evaluation.yaml", "execution.yaml", "scenarios.yaml",
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys rather than silently accepting the last one."""


def _unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    result: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ConfigError(f"Duplicate YAML key {key!r} at {key_node.start_mark}")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


@dataclass(frozen=True)
class V3Protocol:
    """One merged configuration with a byte-level source hash for each input."""

    config: Config
    source_hashes: dict[str, str]
    config_hash: str

    def scenario(self, scenario_id: str) -> Config:
        """Resolve exactly one registered cell; unknown keys are never created."""
        base = self.config.to_dict()
        all_cells = base["scenarios"] + base["design_power_jobs"]
        matches = [s for s in all_cells if s["id"] == scenario_id]
        if len(matches) != 1:
            raise ConfigError(f"Unknown or duplicate scenario: {scenario_id}")
        cell = matches[0]
        if "base_scenario_id" in cell:
            base = self.scenario(cell["base_scenario_id"]).to_dict()
        for path, value in cell["overrides"].items():
            _replace_existing(base, path, value)
        base["design"]["n_total"] = cell["n"]
        base["design"]["treatment_probability"] = cell["treatment_probability"]
        base["active_scenario"] = copy.deepcopy(cell)
        return Config(base, name=scenario_id)


def _replace_existing(data: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    target = data
    for part in parts[:-1]:
        if not isinstance(target, dict) or part not in target:
            raise ConfigError(f"Unknown override path: {path}")
        target = target[part]
    if not isinstance(target, dict) or parts[-1] not in target:
        raise ConfigError(f"Unknown override path: {path}")
    target[parts[-1]] = copy.deepcopy(value)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def load_v3_protocol(root: Path | str | None = None) -> V3Protocol:
    """Load all seven files and validate scope without using v2 defaults."""
    config_root = Path(root) if root is not None else Path(__file__).resolve().parents[2] / "configs" / "v3"
    merged: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for name in CONFIG_FILES:
        path = config_root / name
        raw = path.read_bytes()
        obj = yaml.load(raw.decode("utf-8-sig"), Loader=_UniqueKeyLoader)
        _require(isinstance(obj, dict), f"Expected a mapping: {path}")
        for key, value in obj.items():
            if key in merged and merged[key] != value:
                raise ConfigError(f"Conflicting top-level section {key!r} in {name}")
            merged[key] = value
        hashes[name] = hashlib.sha256(raw).hexdigest()
    validate_v3_config(merged)
    canonical = json.dumps(merged, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return V3Protocol(Config(merged, name="v3"), hashes, hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def planned_counts(data: dict[str, Any]) -> dict[str, Any]:
    """Count data jobs, model mode jobs and resamples, without conflating them."""
    cells = data["scenarios"]
    core = [s for s in cells if "core" in s["roles"]]
    aa = [s for s in cells if "aa" in s["roles"] or s["formal_repetitions"]["complete_aa"]]
    outer = [s for s in cells if s["tier"] == 2]
    learning = [s for s in cells if s["formal_repetitions"]["full_learning_per_model"]]
    budgets = len(data["policy"]["budget"]["per_user_grid_cny"])
    reps = data["execution"]["formal_repeats"]
    origins = len(data["design"]["temporal"]["rolling_origin_weeks"])
    conservative = data["policy"]["budget"]["conservative_comparison"]
    conservative_cells = len(conservative["scenario_ids"]) * len(conservative["modes"]) * budgets

    def mode_calls(s: dict) -> int:
        return sum(origins if mode == "rolling_retrain" else 1 for mode in s["time_modes"])

    result = {
        "scenario_cells": len(cells),
        "by_level": dict(sorted(Counter(s["level"] for s in cells).items())),
        "tier1_core_cells": len(core),
        "tier1_aa_cells": len(aa),
        "tier2_complete_cells": len(outer),
        "design_power_cells": len(data["design_power_jobs"]),
        "historical_dgp_jobs": sum(max(s["formal_repetitions"].values()) for s in cells),
        "full_learning_data_jobs": sum(s["formal_repetitions"]["full_learning_per_model"] for s in cells),
        "independent_validation_jobs": sum(s["formal_repetitions"]["independent_validation"] for s in cells),
        "model_mode_jobs": sum(s["formal_repetitions"]["full_learning_per_model"] * len(s["models"]) * len(s["time_modes"]) for s in learning),
        "learner_fit_calls_excluding_internal_nuisance_fits": sum(s["formal_repetitions"]["full_learning_per_model"] * len(s["models"]) * mode_calls(s) for s in learning),
        "complete_aa_jobs": sum(s["formal_repetitions"]["complete_aa"] for s in cells),
        "additional_design_power_jobs": sum(s["R"] for s in data["design_power_jobs"]),
        "retraining_bootstrap_jobs": len(core) * reps["retraining_bootstrap"],
        "retraining_bootstrap_model_mode_jobs": sum(len(s["models"]) * len(s["time_modes"]) for s in core) * reps["retraining_bootstrap"],
        "retraining_bootstrap_learner_fit_calls": sum(len(s["models"]) * mode_calls(s) for s in core) * reps["retraining_bootstrap"],
        "fixed_bootstrap_resamples": len(learning) * budgets * reps["fixed_policy_bootstrap"],
        "random_baseline_lists": sum(s["formal_repetitions"]["full_learning_per_model"] for s in learning) * budgets * reps["random_list_seeds_per_budget"],
        "conservative_budget_comparison_cells": conservative_cells,
        "additional_conservative_random_baseline_lists": conservative_cells * conservative["random_seeds_per_dataset_budget_mode"],
        "budget_risk_predictive_resamples": sum(s["formal_repetitions"]["full_learning_per_model"] for s in learning) * data["evaluation"]["decision"]["budget_evidence"]["overrun_predictive_bootstrap_repeats"],
    }
    return result


def validate_v3_config(data: dict[str, Any]) -> None:
    """Reject missing scope, illegal probabilities, leakage and count drift."""
    business, design, execution = data["business"], data["design"], data["execution"]
    _require(business["coupon_face_values"] == [business["coupon_reference_face"]], "Only the reference face is permitted")
    _require(not business["face_value_optimization_enabled"], "Q2 forbids face-value optimization")
    _require(data["policy"]["face_value_cny"] == business["coupon_reference_face"], "Coupon amount differs between business and policy")
    _require(data["windows"]["profit_days"] > data["windows"]["convert_days"], "Profit and purchase windows must be distinct")
    _require(abs(sum(design["split"][k] for k in ("train", "validation", "test")) - 1) < design["numerical"]["probability_tolerance"], "Split shares do not sum to one")
    _require(execution["resources"]["default_parallel_workers"] <= execution["resources"]["max_parallel_workers"], "Default concurrency exceeds cap")
    _require(execution["resources"]["model_internal_threads"] == 1, "Nested model parallelism is forbidden")
    _require(data["models"]["causal_forest"]["n_jobs"] == execution["resources"]["model_internal_threads"], "CF threads violate resource protocol")
    _require(data["evaluation"]["independent_validation"]["primary_budget_cny_per_user"] == data["policy"]["budget"]["base_per_user_cny"], "Validation and history budgets differ")
    _require(data["evaluation"]["reporting"]["abstract_and_conclusion_quantitative_tiers"] == [1], "Q1 restricts summary claims to Tier 1")
    allowed = set(data["models"]["feature_whitelist"])
    forbidden = set(data["models"]["forbidden_features"])
    _require(not allowed & forbidden, "Audit feature is in observed whitelist")

    cells = data["scenarios"]
    all_cells = cells + data["design_power_jobs"]
    ids = [s["id"] for s in all_cells]
    _require(len(ids) == len(set(ids)), "Scenario IDs must be unique")
    levels = set(data["matrix_contract"]["reference_scenarios"])
    _require(set(s["level"] for s in cells) == levels, "A required level is missing")
    reps = execution["formal_repeats"]
    required_models = set(data["models"]["common"])
    for s in all_cells:
        _require(s["n"] > 0 and isinstance(s["n"], int), f"Invalid sample size: {s['id']}")
        _require(0 < s["treatment_probability"] < 1, f"Invalid allocation: {s['id']}")
        trial = copy.deepcopy(data)
        for path, value in s["overrides"].items():
            _replace_existing(trial, path, value)
        if "design_power" in s["roles"]:
            _require(s["R"] == design["local_power"]["repeats_per_point"], f"Power R drift: {s['id']}")
            _require(s["base_scenario_id"] in {cell["id"] for cell in cells}, f"Power base must be a main registered scenario: {s['id']}")
            continue
        fr = s["formal_repetitions"]
        _require(s["R"] == max(fr.values()), f"Top-level R disagrees: {s['id']}")
        if fr["complete_aa"]:
            _require(fr["complete_aa"] == reps["tier1_aa_per_layer"] and not s["models"], f"AA contract drift: {s['id']}")
            _require(trial["dgp"]["virtual_aa_labels"] and trial["dgp"]["actual_action_override"] == design["aa"]["actual_action"], f"AA changes treatment: {s['id']}")
        else:
            prefix = "tier1" if s["tier"] == 1 else "tier2"
            for field, suffix in (("ate", "ate"), ("full_learning_per_model", "full_learning_per_model"), ("independent_validation", "independent_validation")):
                _require(fr[field] == reps[f"{prefix}_{suffix}"], f"Formal repetitions drift: {s['id']}/{field}")
            extra = set(data["models"]["additional_by_level"][s["level"]])
            _require(required_models | extra <= set(s["models"]), f"Required model absent: {s['id']}")
        if s["level"] != "L0":
            _require(not trial["dgp"]["l0"]["control"]["enabled"], f"L0 artificial knob leaked: {s['id']}")
        if s["level"] == "L3" and not fr["complete_aa"] and s["id"] != data["matrix_contract"]["l3_observability"]["missing_stress_scenario"]:
            dirty, cleaning = trial["data"]["dirty"], trial["data"]["cleaning"]
            _require(all(v == 0 for v in dirty["cart_missing_by_channel"].values()), f"Incomplete confounders in L3 calibration/scan: {s['id']}")
            _require(dirty["fraud_user_rate"] == 0 and cleaning["numeric_winsor_quantiles"] == [0, 1] and cleaning["standardized_feature_clip"] is None, f"Coarsened confounders in L3 calibration/scan: {s['id']}")
    for level in levels:
        _require(sum(s["level"] == level and "core" in s["roles"] for s in cells) == 1, f"Need one core for {level}")
        _require(sum(s["level"] == level and s["formal_repetitions"]["complete_aa"] > 0 for s in cells) == 1, f"Need one true AA for {level}")
    actual = planned_counts(data)
    for name, value in data["planned_counts"].items():
        _require(name in actual, f"Unknown count measure: {name}")
        _require(value == actual[name], f"Planned count drift {name}: declared={value}, derived={actual[name]}")


def protocol_rows(protocol: V3Protocol) -> list[dict[str, Any]]:
    """Export every cell, including design-only power jobs, with explicit roles."""
    data = protocol.config.to_dict()
    rows = []
    for s in data["scenarios"] + data["design_power_jobs"]:
        rows.append({
            "data_source": data["project"]["data_source_label"],
            "scenario_id": s["id"], "level": s["level"], "tier": s["tier"],
            "n": s["n"], "treatment_probability": s["treatment_probability"],
            "R": s["R"], "MC_SE": "not_run", "planned": s["R"],
            "successful": 0, "failed": 0, "effective": 0, "status": "planned",
            "models": "|".join(s["models"]), "roles": "|".join(s["roles"]),
            "pairing_group": s["pairing_group"],
            "repetitions": json.dumps(s["formal_repetitions"], sort_keys=True),
            "overrides": json.dumps(s["overrides"], ensure_ascii=False, sort_keys=True),
            "config_hash": protocol.config_hash,
        })
    return rows
