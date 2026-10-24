"""Protocol tests protect required scope before expensive formal simulations."""

from __future__ import annotations

import copy

import pytest

from causal_growth.config import ConfigError
from causal_growth.v3_config import load_v3_protocol, planned_counts, protocol_rows, validate_v3_config


@pytest.fixture
def protocol():
    return load_v3_protocol()


def test_every_registered_cell_resolves_without_changing_base(protocol):
    before = protocol.config.to_dict()
    for cell in before["scenarios"] + before["design_power_jobs"]:
        resolved = protocol.scenario(cell["id"])
        assert resolved.require("design.n_total") == cell["n"]
        assert resolved.require("design.treatment_probability") == cell["treatment_probability"]
    assert protocol.config.to_dict() == before


@pytest.mark.parametrize("mutation", ["unknown_override", "reduced_cf_scope", "reduced_repeats", "duplicate_id", "audit_feature", "false_aa", "count_drift", "knob_leak"])
def test_protocol_rejects_silent_scope_and_information_changes(protocol, mutation):
    data = copy.deepcopy(protocol.config.to_dict())
    cell = data["scenarios"][0]
    if mutation == "unknown_override":
        cell["overrides"]["dgp.typo_purchase_probability"] = 0
    elif mutation == "reduced_cf_scope":
        cell["models"].remove("causal_forest")
    elif mutation == "reduced_repeats":
        cell["formal_repetitions"]["full_learning_per_model"] -= 1
    elif mutation == "duplicate_id":
        data["scenarios"][1]["id"] = cell["id"]
    elif mutation == "audit_feature":
        data["models"]["feature_whitelist"].append("U")
    elif mutation == "false_aa":
        aa = next(s for s in data["scenarios"] if s["formal_repetitions"]["complete_aa"])
        aa["overrides"]["dgp.actual_action_override"] = 1
    elif mutation == "count_drift":
        data["planned_counts"]["historical_dgp_jobs"] += 1
    elif mutation == "knob_leak":
        non_l0 = next(s for s in data["scenarios"] if s["level"] != "L0")
        non_l0["overrides"]["dgp.l0.control.enabled"] = True
    with pytest.raises(ConfigError):
        validate_v3_config(data)


def test_manifest_distinguishes_plan_and_evidence(protocol):
    rows = protocol_rows(protocol)
    assert rows
    assert all(row["status"] == "planned" and row["successful"] == 0 and row["MC_SE"] == "not_run" for row in rows)
    assert len(rows) == planned_counts(protocol.config.to_dict())["scenario_cells"] + planned_counts(protocol.config.to_dict())["design_power_cells"]


def test_unknown_scenario_fails(protocol):
    with pytest.raises(ConfigError):
        protocol.scenario("unregistered_result_selected_after_looking")


def test_power_cells_inherit_their_own_level_mechanism(protocol):
    for cell in protocol.config.to_dict()["design_power_jobs"]:
        resolved = protocol.scenario(cell["id"])
        parent = protocol.scenario(cell["base_scenario_id"])
        assert resolved.require("dgp.profile") == parent.require("dgp.profile")
        for path in parent.section("active_scenario")["overrides"]:
            if path not in cell["overrides"]:
                assert resolved.require(path) == parent.require(path)


def test_l2_crossed_resource_design_and_l3_fixed_truth_grid_are_complete(protocol):
    # These literals are acceptance criteria from HITL §4.4 and §4.5,
    # not business defaults consumed by the generator.
    cells = protocol.config.to_dict()["scenarios"]
    l2 = [s for s in cells if s["id"].startswith("L2_n")]
    assert {(s["n"], s["treatment_probability"]) for s in l2} == {
        (n, p) for n in (30000, 60000, 100000, 200000) for p in (0.5, 0.3, 0.1)
    }
    fixed = [s for s in cells if s["id"].startswith("L3_fixed_lt")]
    assert len(fixed) == 7
    assert len({s["pairing_group"] for s in fixed}) == 1


def test_l3_ignorability_baseline_does_not_lose_observed_confounders(protocol):
    data = protocol.config.to_dict()
    baseline = next(s for s in data["scenarios"] if s["id"] == "L3_fixed_lt000")
    baseline["overrides"]["data.dirty.fraud_user_rate"] = data["data"]["dirty"]["fraud_user_rate"]
    with pytest.raises(ConfigError, match="Coarsened confounders"):
        validate_v3_config(data)
