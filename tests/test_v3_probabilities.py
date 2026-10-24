"""Known-DGP mechanism checks, not substitutes for formal v3 repetitions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.integrate import quad
from scipy.special import expit
from scipy.stats import logistic, norm, uniform

from causal_growth.config import ConfigError
from causal_growth.dgp.v3_covariates import generate_covariates, standardized_u
from causal_growth.dgp.v3_probability import (
    assign_treatment,
    calibrate_probability_mechanism,
    integrate_baseline_over_u,
    mechanism_features,
    purchase_probabilities,
)
from causal_growth.v3_config import load_v3_protocol


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


def test_all_registered_scenarios_generate_legal_probabilities(protocol):
    for cell in protocol.config.require("scenarios"):
        cfg = protocol.scenario(cell["id"])
        before = cfg.hash()
        batch = generate_covariates(cfg, 2, n=140)
        p = purchase_probabilities(batch.users, cfg, batch.audit_u)
        assignment = assign_treatment(batch.users, cfg, 2, batch.audit_u)
        assert cfg.hash() == before
        assert len(batch.users) == 140
        assert np.isfinite(p.p0_given_x).all()
        assert np.all((0 <= p.p0_conditional) & (p.p0_conditional <= p.p1_conditional) & (p.p1_conditional <= 1))
        assert set(assignment.action) <= {0, 1}
        if cell["level"] == "L3" and not cfg.require("dgp.virtual_aa_labels"):
            assert np.isnan(assignment.design_probability).all()
            assert abs(assignment.true_propensity.mean() - cfg.require("design.treatment_probability")) < 1e-10
        else:
            assert np.isfinite(assignment.design_probability).all()


def test_reference_calibration_consumes_three_distinct_constraints(protocol):
    cfg = protocol.scenario("L1_main")
    calibration = calibrate_probability_mechanism(cfg)
    assert calibration.reference_n == 1_000_000
    assert abs(calibration.reference_baseline_mean - cfg.require("dgp.l1.baseline_purchase_target")) < 1e-10
    assert abs(calibration.reference_h_mean - cfg.require("dgp.l1.h_target")) < 1e-10
    assert abs(calibration.reference_increment_mean - cfg.require("dgp.l1.purchase_increment_target")) < 1e-10
    assert 0 < calibration.headroom_amplitude < cfg.require("dgp.l1.maximum_purchase_increment")
    # The reference is independent from replication number and scenario X rows.
    a, b = generate_covariates(cfg, 1, 100), generate_covariates(cfg, 2, 100)
    assert not a.users.equals(b.users)
    assert purchase_probabilities(a.users, cfg).calibration is purchase_probabilities(b.users, cfg).calibration


def test_l2_full_crossing_exact_cohorts_and_common_prefix(protocol):
    cells = [cell for cell in protocol.config.require("scenarios") if cell["pairing_group"] == "L2_size_allocation"]
    assert len(cells) == 12
    small_cfg = protocol.scenario("L2_n30000_p050")
    large_cfg = protocol.scenario("L2_n200000_p050")
    small = generate_covariates(small_cfg, 5)
    large = generate_covariates(large_cfg, 5)
    pd.testing.assert_frame_equal(small.users, large.users.iloc[:len(small.users)])
    np.testing.assert_array_equal(small.audit_u, large.audit_u[:len(small.users)])
    assert small.users["split"].value_counts().to_dict() == {"train": 15000, "test": 9000, "validation": 6000}
    assert large.users["split"].value_counts().to_dict() == {"train": 100000, "test": 60000, "validation": 40000}
    for cell in cells:
        cfg = protocol.scenario(cell["id"])
        batch = generate_covariates(cfg, 5, 100)
        pd.testing.assert_frame_equal(batch.users, small.users.iloc[:100])
        np.testing.assert_array_equal(batch.audit_u, small.audit_u[:100])
    assert np.all(large.users.assignment_day >= (large.users.assignment_week - 1) * 7)
    assert np.all(large.users.assignment_day < large.users.assignment_week * 7)


def test_all_covariate_streams_preserve_arbitrary_prefix(protocol):
    cfg = protocol.scenario("L2_n200000_p050")
    small = generate_covariates(cfg, 0, 17)
    large = generate_covariates(cfg, 0, 147)
    pd.testing.assert_frame_equal(small.users, large.users.iloc[:17])
    np.testing.assert_array_equal(small.audit_u, large.audit_u[:17])


def test_validation_population_is_disjoint_and_matches_future_cohorts(protocol):
    cells = protocol.config.require("scenarios")
    cell = next(c for c in cells if c["level"] == "L2" and c["overrides"].get("dgp.l2.composition") == "shift")
    cfg = protocol.scenario(cell["id"])
    historical = generate_covariates(cfg, 0, 20000)
    validation = generate_covariates(cfg, 0, 20000, population_kind="validation")
    assert set(historical.users.user_id).isdisjoint(validation.users.user_id)
    assert set(validation.users.assignment_week) == set(cfg.require("design.temporal.test_weeks"))
    assert set(validation.users.split) == {"test"}
    assert abs(validation.users.is_new.mean() - cfg.require("dgp.l2.composition_schedule.shift.test_new_share")) < .02
    assert not np.array_equal(historical.audit_u, validation.audit_u)
    with pytest.raises(ValueError, match="policy arms"):
        assign_treatment(validation.users, cfg, 0, validation.audit_u, population_kind="validation")


def test_l3_fixed_truth_scan_only_reassigns_treatment(protocol):
    cells = [c for c in protocol.config.require("scenarios") if c["pairing_group"] == "L3_fixed_truth" and c["id"] != "L3_missing_confounders"]
    assert len(cells) == 7
    reference_users, reference_u, reference_p, reference_action = None, None, None, None
    differences = []
    for cell in cells:
        cfg = protocol.scenario(cell["id"])
        batch = generate_covariates(cfg, 7, 1000)
        p = purchase_probabilities(batch.users, cfg, batch.audit_u)
        assignment = assign_treatment(batch.users, cfg, 7, batch.audit_u)
        if reference_users is None:
            reference_users, reference_u, reference_p, reference_action = batch.users, batch.audit_u, p, assignment.action
        pd.testing.assert_frame_equal(batch.users, reference_users)
        np.testing.assert_array_equal(batch.audit_u, reference_u)
        for field in ("p0_conditional", "p1_conditional", "p0_given_x", "p1_given_x"):
            np.testing.assert_array_equal(getattr(p, field), getattr(reference_p, field))
        differences.append(np.mean(assignment.action != reference_action))
        assert abs(assignment.true_propensity.mean() - .5) < 1e-10
    assert differences[-1] > 0


def test_l3_joint_changes_truth_but_not_reference_intercepts(protocol):
    cells = [c for c in protocol.config.require("scenarios") if c["pairing_group"] == "L3_joint_mechanism"]
    left, right = protocol.scenario(cells[0]["id"]), protocol.scenario(cells[-1]["id"])
    x, y = generate_covariates(left, 0, 1000), generate_covariates(right, 0, 1000)
    a, b = purchase_probabilities(x.users, left, x.audit_u), purchase_probabilities(y.users, right, y.audit_u)
    assert a.calibration is b.calibration
    assert not np.allclose(a.p0_given_x, b.p0_given_x)
    assert not np.allclose(a.p1_given_x - a.p0_given_x, b.p1_given_x - b.p0_given_x)


def test_u_shape_cross_pairing_and_distribution_moments(protocol):
    base = generate_covariates(protocol.scenario("L3_fixed_lt050"), 0, 1000)
    shape_cells = [c for c in protocol.config.require("scenarios") if c["pairing_group"] == "L3_u_shape"]
    q = expit(base.audit_u * np.pi / np.sqrt(3))
    for cell in shape_cells:
        cfg = protocol.scenario(cell["id"])
        sample = generate_covariates(cfg, 0, 1000)
        pd.testing.assert_frame_equal(sample.users, base.users)
        np.testing.assert_allclose(sample.audit_u, standardized_u(q, cfg.require("dgp.l3.u_distribution")), atol=1e-12)
    q_grid = (np.arange(200000) + .5) / 200000
    for name in ("normal", "logistic_standardized", "uniform_bounded"):
        u = standardized_u(q_grid, name)
        assert abs(u.mean()) < 1e-10
        assert abs(u.var() - 1) < 1e-4


@pytest.mark.parametrize("distribution", ["normal", "logistic_standardized", "uniform_bounded"])
@pytest.mark.parametrize("lambda_y", [0.0, .5, 1.5])
def test_x_only_u_integral_against_independent_adaptive_quad(distribution, lambda_y):
    scores = np.array([-12., -4., -1., 0., 2., 12.])
    law = {"normal": norm(), "logistic_standardized": logistic(scale=np.sqrt(3) / np.pi), "uniform_bounded": uniform(loc=-np.sqrt(3), scale=2 * np.sqrt(3))}[distribution]
    values, error, _ = integrate_baseline_over_u(scores, lambda_y, distribution)
    lo, hi = law.support()
    expected = np.array([quad(lambda u: expit(score + lambda_y * u) * law.pdf(u), lo, hi, epsabs=1e-12, epsrel=1e-12)[0] for score in scores])
    np.testing.assert_allclose(values, expected, atol=1e-9, rtol=1e-9)
    assert error <= 2e-10


def test_l2_drift_is_the_configured_multiplier(protocol):
    cell = next(c for c in protocol.config.require("scenarios") if c["overrides"].get("dgp.l2.drift") == "smooth" and c["overrides"].get("dgp.l2.composition", "none") == "none")
    drift_cfg, base_cfg = protocol.scenario(cell["id"]), protocol.scenario("L2_n200000_p050")
    batch = generate_covariates(drift_cfg, 3, 1000)
    base_batch = generate_covariates(base_cfg, 3, 1000)
    pd.testing.assert_frame_equal(batch.users, base_batch.users)
    drift, base = purchase_probabilities(batch.users, drift_cfg), purchase_probabilities(batch.users, base_cfg)
    multipliers = dict(zip(drift_cfg.require("design.temporal.assignment_weeks"), drift_cfg.require("dgp.l2.effect_multipliers_by_active_cohort.smooth")))
    ratio = (drift.p1_given_x - drift.p0_given_x) / (base.p1_given_x - base.p0_given_x)
    np.testing.assert_allclose(ratio, batch.users.assignment_week.map(multipliers))


def test_aa_labels_have_no_effect_on_action_or_potential_mechanism(protocol):
    for cell in protocol.config.require("scenarios"):
        if not cell["overrides"].get("dgp.virtual_aa_labels"):
            continue
        cfg = protocol.scenario(cell["id"])
        batch = generate_covariates(cfg, 3, 1000)
        assignment = assign_treatment(batch.users, cfg, 3, batch.audit_u)
        assert np.all(assignment.action == 0)
        assert set(assignment.label) == {0, 1}
        a = purchase_probabilities(batch.users, cfg, batch.audit_u)
        ordinary = cfg.with_overrides({"dgp.virtual_aa_labels": False, "dgp.actual_action_override": None})
        b = purchase_probabilities(batch.users, ordinary, batch.audit_u)
        np.testing.assert_array_equal(a.p1_conditional, b.p1_conditional)


def test_reference_features_use_recorded_x_and_illegal_targets_raise(protocol):
    cfg = protocol.scenario("L3_fixed_lt000")
    batch = generate_covariates(cfg, 0, 50)
    calibration = calibrate_probability_mechanism(cfg)
    matrix = mechanism_features(batch.users, calibration.feature_moments)
    np.testing.assert_array_equal(batch.users.cart_value, batch.users.cart_value_cent / cfg.require("business.money.cents_per_yuan"))
    assert np.isfinite(matrix).all()
    with pytest.raises(ConfigError, match="infeasible"):
        calibrate_probability_mechanism(cfg.with_overrides({"dgp.l1.purchase_increment_target": .9}))
    with pytest.raises(ValueError, match="audit U"):
        purchase_probabilities(batch.users, cfg)
    with pytest.raises(ValueError, match="strictly interior"):
        standardized_u(np.array([0., 1.]), "normal")


def test_sampling_can_skip_truth_integration_without_fabricating_x_targets(protocol):
    for scenario in ("L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt150"):
        cfg = protocol.scenario(scenario)
        batch = generate_covariates(cfg, 0, 50)
        sampling = purchase_probabilities(batch.users, cfg, batch.audit_u, integrate_u=False)
        audit = purchase_probabilities(batch.users, cfg, batch.audit_u)
        assert sampling.p0_given_x is None
        assert sampling.p1_given_x is None
        assert sampling.integration_nodes == 0
        assert sampling.integration_error_per_row is None
        assert audit.integration_error_per_row.shape == (len(batch.users),)
        np.testing.assert_array_equal(sampling.p0_conditional, audit.p0_conditional)
        np.testing.assert_array_equal(sampling.p1_conditional, audit.p1_conditional)


@pytest.mark.parametrize("distribution", ["normal", "logistic_standardized", "uniform_bounded"])
def test_adaptive_u_refinement_reports_each_rows_error(distribution):
    scores = np.array([-12., -4., -1., 0., 2., 12.])
    adaptive, maximum, nodes, row_errors = integrate_baseline_over_u(
        scores, 1.5, distribution, integration_method="adaptive", return_per_row=True,
    )
    batched, _, _, batch_errors = integrate_baseline_over_u(scores, 1.5, distribution, return_per_row=True)
    assert nodes == 0  # adaptive has no common Gaussian rule order
    assert maximum == row_errors.max()
    assert np.all(row_errors >= 0)
    assert maximum < 2e-14
    assert adaptive[3] == .5 and row_errors[3] == 0  # exact symmetry, not an estimated integral
    assert abs(adaptive[0] + adaptive[-1] - 1) < 1e-15
    assert np.ptp(row_errors) > 0  # never broadcast one sample's max to all rows
    assert np.all(abs(adaptive - batched) <= row_errors + batch_errors)
    law = {"normal": norm(), "logistic_standardized": logistic(scale=np.sqrt(3) / np.pi), "uniform_bounded": uniform(loc=-np.sqrt(3), scale=2 * np.sqrt(3))}[distribution]
    lo, hi = law.support()
    expected = np.array([quad(lambda u: expit(score + 1.5 * u) * law.pdf(u), lo, hi, epsabs=1e-13, epsrel=1e-13)[0] for score in scores])
    np.testing.assert_allclose(adaptive, expected, atol=2e-14, rtol=0)


def test_refinement_api_preserves_conditional_mechanism_and_zero_lambda_errors(protocol):
    cfg = protocol.scenario("L3_fixed_lt150")
    batch = generate_covariates(cfg, 0, 20)
    batched = purchase_probabilities(batch.users, cfg, batch.audit_u)
    adaptive = purchase_probabilities(batch.users, cfg, batch.audit_u, integration_method="adaptive")
    np.testing.assert_array_equal(adaptive.p0_conditional, batched.p0_conditional)
    np.testing.assert_array_equal(adaptive.p1_conditional, batched.p1_conditional)
    assert adaptive.integration_max_abs_error == adaptive.integration_error_per_row.max()
    assert adaptive.integration_max_abs_error < batched.integration_max_abs_error
    for method in ("batched", "adaptive"):
        value, error, nodes, rows = integrate_baseline_over_u(np.array([-2., 0., 2.]), 0, "normal", integration_method=method, return_per_row=True)
        np.testing.assert_array_equal(value, expit(np.array([-2., 0., 2.])))
        np.testing.assert_array_equal(rows, np.zeros(3))
        assert error == 0 and nodes == 0
    with pytest.raises(ValueError, match="Unknown U integration method"):
        purchase_probabilities(batch.users, cfg, batch.audit_u, integration_method="unimplemented")
