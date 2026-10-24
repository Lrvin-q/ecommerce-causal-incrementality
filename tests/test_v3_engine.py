"""Cross-module checks of coupled worlds and factual observation projection."""

import numpy as np
import pandas as pd
import pytest
from dataclasses import replace

import causal_growth.dgp.v3_engine as engine
from causal_growth.dgp.v3_engine import audit_conditional_truth, audit_realized_worlds, generate_v3_population
from causal_growth.dgp.v3_ledger import audit_window_ledger
from causal_growth.v3_config import load_v3_protocol


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


@pytest.mark.parametrize("scenario", ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"])
def test_each_layer_factual_ledger_selects_only_assigned_world(protocol, scenario) -> None:
    cfg = protocol.scenario(scenario)
    population = generate_v3_population(cfg, n=200)
    factual = audit_window_ledger(population.users, population.observed_orders, cfg).set_index("user_id")
    worlds = {a: frame.set_index("user_id") for a, frame in audit_realized_worlds(population, cfg).items()}
    action = population.assignments.set_index("user_id").actual_action
    expected = np.where(action == 1, worlds[1].net_profit_cent, worlds[0].net_profit_cent)
    np.testing.assert_array_equal(factual.net_profit_cent, expected)
    assert len(factual) == len(population.users)
    users, assignments, orders = population.observation_bundle()
    assert not {"audit_u", "true_propensity", "cate_profit", "goods_cost_ratio", "homogeneous_mask"} & set(users.columns)
    assert "true_propensity" not in assignments
    assert len(orders) == len(population.observed_orders)
    assert population.metadata["formal_completion_claim"] is False


def test_l3_fixed_scan_keeps_potential_worlds_and_x_only_truth(protocol) -> None:
    baseline = protocol.scenario("L3_fixed_lt000")
    shifted = protocol.scenario("L3_fixed_lt150")
    first = generate_v3_population(baseline, n=100)
    second = generate_v3_population(shifted, n=100)
    pd.testing.assert_frame_equal(first.users, second.users)
    for action in (0, 1):
        pd.testing.assert_frame_equal(first.audit_potential_orders[action], second.audit_potential_orders[action])
    a = audit_conditional_truth(first, baseline)
    b = audit_conditional_truth(second, shifted)
    np.testing.assert_array_equal(a.cate_profit, b.cate_profit)
    assert not np.allclose(a.cate_profit, a.cate_profit_xu)
    assert not np.allclose(first.audit_true_propensity, second.audit_true_propensity)
    assert first.assignments.design_probability.isna().all()


@pytest.mark.parametrize("scenario", ["L0_AA", "L1_AA", "L2_AA", "L3_AA"])
def test_actual_aa_action_and_label_effect_are_distinct(protocol, scenario) -> None:
    cfg = protocol.scenario(scenario)
    population = generate_v3_population(cfg, n=40)
    assert (population.assignments.actual_action == 0).all()
    assert population.assignments.label.nunique() == 2
    expected = population.audit_potential_orders[0].reset_index(drop=True)
    pd.testing.assert_frame_equal(population.observed_orders, expected)
    truth = audit_conditional_truth(population, cfg)
    assert (truth.label_cate_profit == 0).all()


def test_independent_validation_has_distinct_ids_and_latent_stream(protocol) -> None:
    cfg = protocol.scenario("L1_main")
    history = generate_v3_population(cfg, n=60)
    policy = pd.DataFrame({"user_id": -np.arange(1, 61), "assigned_policy_arm": "no_coupon", "issued_action": 0,
                           "policy_arm_probability": cfg.require("evaluation.independent_validation.arm_probabilities")[0]})
    validation = generate_v3_population(cfg, n=60, population_kind="validation", validation_assignment=policy)
    assert not set(history.users.user_id) & set(validation.users.user_id)
    assert history.metadata["stream_prefix"] != validation.metadata["stream_prefix"]
    assert not np.array_equal(history.users.cart_value_cent, validation.users.cart_value_cent)


def test_validation_cannot_silently_reuse_historical_treatment_design(protocol) -> None:
    with pytest.raises(ValueError, match="frozen policy-arm"):
        generate_v3_population(protocol.scenario("L1_main"), n=20, population_kind="validation")


def test_l2_sample_size_pair_retains_user_and_potential_prefix(protocol) -> None:
    a = generate_v3_population(protocol.scenario("L2_n30000_p050"), n=60)
    b = generate_v3_population(protocol.scenario("L2_n200000_p050"), n=100)
    pd.testing.assert_frame_equal(a.users, b.users.iloc[:60].reset_index(drop=True))
    for action in (0, 1):
        matched = b.audit_potential_orders[action].query("user_id <= 60").reset_index(drop=True)
        pd.testing.assert_frame_equal(a.audit_potential_orders[action], matched)


def test_zero_purchase_effect_still_incurs_coupon_and_refund_costs(protocol) -> None:
    cfg = protocol.scenario("L0_zero_purchase_effect")
    population = generate_v3_population(cfg, n=40)
    truth = audit_conditional_truth(population, cfg)
    assert (truth.cate_purchase_7d == 0).all()
    assert (truth.cate_profit < 0).all()


@pytest.mark.parametrize("scenario", ["L0_Pi_equal_cost", "L0_Pi_heterogeneous_cost"])
def test_l0_control_reaches_generator_ledger_and_stays_out_of_user_features(protocol, scenario) -> None:
    cfg = protocol.scenario(scenario)
    population = generate_v3_population(cfg, n=20)
    truth = audit_conditional_truth(population, cfg)
    assert population.audit_control is not None
    controlled = population.audit_control.control_feasible.to_numpy()
    assert controlled.any()
    residual = truth.cate_profit.to_numpy()[controlled] - cfg.require("dgp.l0.control.target_profit_cate_cny")
    assert np.max(np.abs(residual)) <= cfg.require("dgp.l0.control.homogeneity_numerical_tolerance_cny")
    assert "control_feasible" not in population.observation_bundle()[0]
    if cfg.require("dgp.l0.control.cost_mode") == "constant_expected_cost":
        np.testing.assert_allclose(truth.expected_coupon_cost_1.to_numpy()[controlled],
                                   cfg.require("dgp.l0.control.constant_expected_coupon_cost_cny"), atol=1e-10, rtol=0)


@pytest.mark.parametrize("audit", [audit_conditional_truth, audit_realized_worlds])
def test_audit_cannot_mix_generated_population_with_another_configuration(protocol, audit) -> None:
    cfg = protocol.scenario("L0_P_main")
    population = generate_v3_population(cfg, n=5)
    mismatch = cfg.with_overrides({"business.first_order_cart_fraction.mean_before_truncation": 0.56})
    with pytest.raises(ValueError, match="does not match"):
        audit(population, mismatch)


@pytest.mark.parametrize("audit", [audit_conditional_truth, audit_realized_worlds])
def test_audit_cannot_mix_numerical_versions(protocol, audit, monkeypatch) -> None:
    cfg = protocol.scenario("L0_P_main")
    population = generate_v3_population(cfg, n=5)
    changed = engine.load_v3_numerics().with_overrides({"integration.quad_epsabs": 1e-12})
    monkeypatch.setattr(engine, "load_v3_numerics", lambda: changed)
    with pytest.raises(ValueError, match="numerical configuration does not match"):
        audit(population, cfg)


def test_profit_error_gate_rejects_large_monetary_uncertainty(protocol, monkeypatch) -> None:
    cfg = protocol.scenario("L0_P_main")
    population = generate_v3_population(cfg, n=5)
    original = engine.paired_conditional_expectation_numerical_error

    def inaccurate(*args, **kwargs):
        answer = original(*args, **kwargs)
        answer["net_profit_numerical_error_estimate_cny"] = np.ones(len(population.users))
        return answer

    monkeypatch.setattr(engine, "paired_conditional_expectation_numerical_error", inaccurate)
    with pytest.raises(ArithmeticError, match="absolute and relative numerical gates"):
        audit_conditional_truth(population, cfg)


def test_l3_refines_only_rows_failing_profit_error_gate(protocol, monkeypatch) -> None:
    cfg = protocol.scenario("L3_fixed_lt000")
    population = generate_v3_population(cfg, n=10)
    probabilities = engine.purchase_probabilities(population.users, cfg, population.audit_u)
    inflated = probabilities.integration_error_per_row.copy()
    inflated[0] = 1
    population.audit_probabilities = replace(probabilities, integration_error_per_row=inflated)
    original = engine.purchase_probabilities
    refined_ids = []

    def record_refinement(users, *args, **kwargs):
        if kwargs.get("integration_method") == "adaptive":
            refined_ids.extend(users.user_id.tolist())
        return original(users, *args, **kwargs)

    monkeypatch.setattr(engine, "purchase_probabilities", record_refinement)
    result = audit_conditional_truth(population, cfg)
    assert refined_ids == [population.users.user_id.iloc[0]]
    assert result.u_integral_refined.tolist() == [True] + [False] * 9
    assert result.profit_precision_pass.all()
    assert population.metadata["u_integral_refined_rows"] == 1
    assert population.metadata["u_integration_max_abs_error"] < 1e-6
    second = audit_conditional_truth(population, cfg)
    pd.testing.assert_frame_equal(result, second)
    assert refined_ids == [population.users.user_id.iloc[0]]
    assert population.metadata["u_integral_refined_rows"] == 1
    assert population.metadata["u_audit_integration_methods"] == ["adaptive", "batched"]
