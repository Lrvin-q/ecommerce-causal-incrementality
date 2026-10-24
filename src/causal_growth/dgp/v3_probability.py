"""Positive-headroom purchase mechanisms and calibrated v3 assignment.

Synthetic / known DGP. This is mechanism and audit code, never a learner input.
The independent reference population defines parameters once; evaluation data
only enter the explicitly required per-repetition assignment calibration.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.integrate import quad
from scipy.optimize import brentq
from scipy.special import expit, roots_legendre
from scipy.stats import logistic, norm, uniform

from causal_growth.config import Config, ConfigError
from causal_growth.dgp.v3_covariates import generate_covariates, stream_prefix
from causal_growth.rng import child_rng
from causal_growth.v3_numerics import load_v3_numerics

FEATURES = ("is_new", "hist_gmv_z", "cart_value_z", "browse_depth_z", "channel_search", "channel_feed", "channel_xhs")
_REFERENCE_CACHE: OrderedDict[str, tuple[np.ndarray, dict[str, tuple[float, float]]]] = OrderedDict()
_CALIBRATION_CACHE: OrderedDict[str, "ProbabilityCalibration"] = OrderedDict()


@dataclass(frozen=True)
class ProbabilityCalibration:
    """Scalar mechanism calibration, auditable independently of final test rows."""

    feature_moments: dict[str, tuple[float, float]]
    baseline_intercept: float
    heterogeneity_intercept: float
    headroom_amplitude: float
    reference_n: int
    reference_baseline_mean: float
    reference_h_mean: float
    reference_increment_mean: float


@dataclass(frozen=True)
class PurchaseProbabilities:
    """Separate X,U conditional probabilities from the X-only integral target."""

    p0_conditional: np.ndarray
    p1_conditional: np.ndarray
    p0_given_x: np.ndarray | None
    p1_given_x: np.ndarray | None
    calibration: ProbabilityCalibration | None
    integration_max_abs_error: float = 0.0
    integration_nodes: int = 0
    integration_error_per_row: np.ndarray | None = None


@dataclass(frozen=True)
class AssignmentDraw:
    """Observed action/label/design metadata and separately retained true e."""

    action: np.ndarray
    label: np.ndarray
    design_probability: np.ndarray
    true_propensity: np.ndarray
    intercept: float | None


def _cache_put(cache: OrderedDict, key: str, value: Any, maximum: int) -> None:
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > maximum:
        cache.popitem(last=False)


def clear_probability_caches() -> None:
    """Release cached reference matrices between workers or resource experiments."""
    _REFERENCE_CACHE.clear()
    _CALIBRATION_CACHE.clear()


def mechanism_features(users: pd.DataFrame, moments: dict[str, tuple[float, float]]) -> np.ndarray:
    """Reproduce mechanism predictors entirely from recorded pre-action X."""
    columns = [users["is_new"].to_numpy(dtype=float)]
    for name in ("hist_gmv", "cart_value", "browse_depth"):
        center, scale = moments[name]
        if scale <= 0:
            raise ConfigError(f"Degenerate calibration feature: {name}")
        columns.append((users[name].to_numpy(dtype=float) - center) / scale)
    columns.extend((users["channel"].to_numpy() == name).astype(float) for name in ("search", "feed", "xhs"))
    matrix = np.column_stack(columns)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Mechanism requires complete finite recorded X")
    return matrix


def _reference(cfg: Config) -> tuple[np.ndarray, dict[str, tuple[float, float]], str]:
    definition = {
        "seed": cfg.require("project.master_seed"),
        "n": cfg.require("design.numerical.calibration_reference_n"),
        "business": {key: cfg.section(f"business.{key}") for key in ("hist_gmv", "cart_value", "browse_depth", "channels")},
        "new_share": cfg.require("business.new_user_share"),
        "cents": cfg.require("business.money.cents_per_yuan"),
    }
    key = json.dumps(definition, sort_keys=True)
    if key not in _REFERENCE_CACHE:
        ref = generate_covariates(cfg, 0, int(definition["n"]), population_kind="reference", pairing_group="mechanism_calibration")
        moments = {name: (float(ref.users[name].mean()), float(ref.users[name].std(ddof=0))) for name in ("hist_gmv", "cart_value", "browse_depth")}
        matrix = mechanism_features(ref.users, moments)
        matrix.setflags(write=False)
        _cache_put(_REFERENCE_CACHE, key, (matrix, moments), int(load_v3_numerics().require("cache.reference_max_entries")))
    _REFERENCE_CACHE.move_to_end(key)
    matrix, moments = _REFERENCE_CACHE[key]
    return matrix, moments, key


def _score(matrix: np.ndarray, coefficients: dict[str, float]) -> np.ndarray:
    unknown = set(coefficients) - set(FEATURES)
    if unknown:
        raise ConfigError(f"Unknown mechanism coefficients: {unknown}")
    return matrix @ np.array([coefficients.get(name, 0.0) for name in FEATURES])


def _intercept(score: np.ndarray, target: float) -> float:
    if not 0 < target < 1:
        raise ConfigError("Calibrated probability target must be strictly between zero and one")
    num = load_v3_numerics()
    lo, hi = num.require("root.bracket")
    return float(brentq(
        lambda value: float(expit(score + value).mean()) - target,
        float(lo), float(hi), xtol=float(num.require("root.absolute_tolerance")),
        rtol=float(num.require("root.relative_tolerance")), maxiter=int(num.require("root.max_iterations")),
    ))


def _effect_score(matrix: np.ndarray, cfg: Config) -> np.ndarray:
    score = _score(matrix, cfg.section("dgp.l1.effect_coefficients")) * float(cfg.require("dgp.l1.heterogeneity_coefficient_multiplier"))
    score += float(cfg.require("dgp.l1.effect_interaction_is_new_cart_z")) * matrix[:, FEATURES.index("is_new")] * matrix[:, FEATURES.index("cart_value_z")]
    return score


def calibrate_probability_mechanism(cfg: Config) -> ProbabilityCalibration:
    """Fix L1 intercepts/amplitude on the independent configured reference only.

    L3 reuses these coefficients and adds lambda_Y U; it does not recalibrate
    away the joint mechanism scan. h_target and mean increment are two distinct
    equations, while maximum_purchase_increment bounds the headroom amplitude.
    """
    matrix, moments, ref_key = _reference(cfg)
    key = ref_key + json.dumps(cfg.section("dgp.l1"), sort_keys=True)
    if key not in _CALIBRATION_CACHE:
        baseline = _score(matrix, cfg.section("dgp.l1.baseline_coefficients"))
        beta0 = _intercept(baseline, float(cfg.require("dgp.l1.baseline_purchase_target")))
        p0 = expit(beta0 + baseline)
        score = _effect_score(matrix, cfg)
        gamma0 = _intercept(score, float(cfg.require("dgp.l1.h_target")))
        h = expit(gamma0 + score)
        denominator = float(np.mean((1 - p0) * h))
        amplitude = float(cfg.require("dgp.l1.purchase_increment_target")) / denominator
        maximum = float(cfg.require("dgp.l1.maximum_purchase_increment"))
        if not 0 <= amplitude <= maximum <= 1:
            raise ConfigError(f"Purchase target infeasible: required headroom amplitude {amplitude}, maximum {maximum}")
        result = ProbabilityCalibration(moments, beta0, gamma0, amplitude, len(matrix), float(p0.mean()), float(h.mean()), float(np.mean((1 - p0) * amplitude * h)))
        _cache_put(_CALIBRATION_CACHE, key, result, int(load_v3_numerics().require("cache.reference_max_entries")))
    _CALIBRATION_CACHE.move_to_end(key)
    return _CALIBRATION_CACHE[key]


def _u_distribution(name: str) -> Any:
    three = 1 + 2
    if name == "normal":
        return norm()
    if name == "logistic_standardized":
        return logistic(scale=np.sqrt(three) / np.pi)
    if name == "uniform_bounded":
        return uniform(loc=-np.sqrt(three), scale=2 * np.sqrt(three))
    raise ConfigError(f"Unknown U distribution: {name}")


def integrate_baseline_over_u(
    score: np.ndarray, lambda_y: float, distribution: str,
    *, integration_method: str = "batched", return_per_row: bool = False,
) -> tuple[np.ndarray, float, int] | tuple[np.ndarray, float, int, np.ndarray]:
    """Integrate logistic purchase probability over U with tail/error accounting.

    Consecutive Gaussian-Legendre rules are compared on every supplied X,
    including finite-density-mass discrepancy and the excluded probability tail.
    Adaptive refinement uses full-support quad on selected rows. The returned
    node count is zero for that method (it has no common fixed-node rule).
    ``return_per_row`` appends each row's own absolute error estimate, allowing
    the engine to propagate it to profit without using a batch maximum.
    """
    values = np.asarray(score, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)) or not np.isfinite(lambda_y):
        raise ValueError("Baseline score must be a finite one-dimensional array and lambda_y finite")
    if integration_method not in {"batched", "adaptive"}:
        raise ValueError(f"Unknown U integration method: {integration_method}")
    law = _u_distribution(distribution)

    def packed(result: np.ndarray, errors: np.ndarray, nodes: int) -> tuple:
        basic = (result, float(errors.max(initial=0)), nodes)
        return (*basic, errors) if return_per_row else basic

    if lambda_y == 0:
        return packed(expit(values), np.zeros_like(values), 0)
    num = load_v3_numerics()
    if integration_method == "adaptive":
        result, errors = _adaptive_u_integral(values, lambda_y, law, num)
        return packed(result, errors, 0)
    tail = float(num.require("integration.tail_probability_budget"))
    lo, hi = law.ppf([tail / 2, 1 - tail / 2])
    mass = float(law.cdf(hi) - law.cdf(lo))
    previous: np.ndarray | None = None
    nodes = int(num.require("integration.u_initial_nodes"))
    maximum = int(num.require("integration.u_max_nodes"))
    batch = int(num.require("integration.u_batch_size"))
    atol = float(num.require("integration.quad_epsabs"))
    rtol = float(num.require("integration.quad_epsrel"))
    while nodes <= maximum:
        abscissa, weights = roots_legendre(nodes)
        points = lo + (abscissa + 1) * (hi - lo) / 2
        weights = weights * (hi - lo) / 2 * law.pdf(points)
        result = np.empty_like(values)
        for start in range(0, len(values), batch):
            stop = min(start + batch, len(values))
            result[start:stop] = expit(values[start:stop, None] + lambda_y * points) @ weights
        mass_error = abs(float(weights.sum()) - mass) + (1 - mass)
        if previous is not None:
            point_error = np.abs(result - previous) + mass_error
            if np.all(point_error <= atol + rtol * np.abs(result)):
                return packed(result, point_error, nodes)
        previous = result
        nodes *= 2
    raise ArithmeticError(f"U integral failed tolerance at {maximum} nodes ({distribution}, lambda_y={lambda_y})")


def _adaptive_u_integral(values: np.ndarray, lambda_y: float, law: Any, num: Config) -> tuple[np.ndarray, np.ndarray]:
    """Refine selected X using symmetry and the distribution's complete support."""
    atol = float(num.require("integration.refinement_epsabs"))
    rtol = float(num.require("integration.refinement_epsrel"))
    limit = int(num.require("integration.refinement_limit"))
    _, upper = law.support()
    result, errors = np.empty_like(values), np.empty_like(values)
    for index, value in enumerate(values):
        if value == 0:
            result[index], errors[index] = 1 / 2, 0
            continue
        # Symmetric U gives I(s)=1-I(-s). Integrating the smaller probability
        # avoids forcing quad to estimate the unit-mass term to high precision.
        negative_score = -abs(float(value))
        answer = quad(
            lambda u: (expit(negative_score + lambda_y * u) + expit(negative_score - lambda_y * u)) * law.pdf(u),
            0, upper, epsabs=atol, epsrel=rtol, limit=limit, full_output=1,
        )
        integral, error = answer[:2]
        if len(answer) > 3 and error > atol + rtol * abs(integral):
            raise ArithmeticError(f"Adaptive U integral failed at score={value}: {answer[3]}")
        if not np.isfinite(integral) or not np.isfinite(error):
            raise ArithmeticError("Adaptive U integral produced a nonfinite value/error")
        result[index] = 1 - integral if value > 0 else integral
        # Include one floating-point spacing for the result/complement operation.
        errors[index] = error + abs(np.spacing(result[index]))
    return result, errors


def purchase_probabilities(
    users: pd.DataFrame, cfg: Config, audit_u: np.ndarray | None = None,
    *, integrate_u: bool = True, integration_method: str = "batched",
) -> PurchaseProbabilities:
    """Answer potential purchase and optionally X-only probability questions.

    Sampling and AA can skip audit integration explicitly. In that case both
    given-X fields are None, so an uncomputed target cannot masquerade as truth.
    """
    if integration_method not in {"batched", "adaptive"}:
        raise ValueError(f"Unknown U integration method: {integration_method}")
    profile = str(cfg.require("dgp.profile"))
    if profile in {"l0_purchase", "l0_profit_control"}:
        p0 = np.full(len(users), float(cfg.require("dgp.l0.baseline_purchase_probability")))
        p1 = p0 + float(cfg.require("dgp.l0.purchase_increment"))
        _check_probabilities(p0, p1)
        return PurchaseProbabilities(
            p0, p1, p0.copy() if integrate_u else None, p1.copy() if integrate_u else None,
            None, integration_error_per_row=np.zeros(len(users)) if integrate_u else None,
        )
    if profile not in {"l1", "l2", "l3"}:
        raise ConfigError(f"Unknown mechanism profile: {profile}")
    calibration = calibrate_probability_mechanism(cfg)
    matrix = mechanism_features(users, calibration.feature_moments)
    score = calibration.baseline_intercept + _score(matrix, cfg.section("dgp.l1.baseline_coefficients"))
    h = expit(calibration.heterogeneity_intercept + _effect_score(matrix, cfg))
    headroom = calibration.headroom_amplitude * h
    if profile == "l2":
        schedule = cfg.require(f"dgp.l2.effect_multipliers_by_active_cohort.{cfg.require('dgp.l2.drift')}")
        multipliers = dict(zip(cfg.require("design.temporal.assignment_weeks"), schedule, strict=True))
        headroom *= users["assignment_week"].map(multipliers).to_numpy(dtype=float)
    if np.any(~np.isfinite(headroom)) or np.any((headroom < 0) | (headroom > 1)):
        raise ConfigError("Temporal/effect headroom is outside its legal domain")
    error, nodes = 0.0, 0
    row_errors = np.zeros(len(users)) if integrate_u else None
    if profile == "l3":
        if audit_u is None or np.shape(audit_u) != (len(users),) or not np.all(np.isfinite(audit_u)):
            raise ValueError("L3 conditional probabilities require aligned finite audit U")
        lambda_y = float(cfg.require("dgp.l3.lambda_y"))
        p0 = expit(score + lambda_y * np.asarray(audit_u))
        if integrate_u:
            p0_x, error, nodes, row_errors = integrate_baseline_over_u(
                score, lambda_y, str(cfg.require("dgp.l3.u_distribution")),
                integration_method=integration_method, return_per_row=True,
            )
        else:
            p0_x = None
    else:
        p0 = expit(score)
        p0_x = p0.copy() if integrate_u else None
    p1 = p0 + (1 - p0) * headroom
    p1_x = None if p0_x is None else p0_x + (1 - p0_x) * headroom
    _check_probabilities(p0, p1)
    if p0_x is not None and p1_x is not None:
        _check_probabilities(p0_x, p1_x)
    return PurchaseProbabilities(p0, p1, p0_x, p1_x, calibration, error, nodes, row_errors)


def _check_probabilities(p0: np.ndarray, p1: np.ndarray) -> None:
    if np.any(~np.isfinite(p0)) or np.any(~np.isfinite(p1)) or np.any((p0 < 0) | (p1 < p0) | (p1 > 1)):
        raise ConfigError("Potential purchase probabilities violate 0 <= p0 <= p1 <= 1")


def assign_treatment(
    users: pd.DataFrame, cfg: Config, rep_id: int, audit_u: np.ndarray | None = None,
    *, population_kind: str = "history", pairing_group: str | None = None,
) -> AssignmentDraw:
    """Generate randomized/selected action, or true AA independent virtual labels.

    L3 true propensity is an audit field. Its observed design_probability is NaN,
    never the requested overall allocation fraction masquerading as individual e.
    Policy-arm randomization of independent validation is implemented downstream.
    """
    if population_kind != "history":
        raise ValueError("Historical assignment only; validation requires randomized policy arms")
    prefix = stream_prefix(cfg, population_kind, pairing_group)
    seed = int(cfg.require("project.master_seed"))
    n = len(users)
    draw = child_rng(seed, f"{prefix}.assignment.action", rep_id).random(n)
    intercept: float | None = None
    if bool(cfg.require("dgp.virtual_aa_labels")):
        override = cfg.require("dgp.actual_action_override")
        if override != cfg.require("design.aa.actual_action"):
            raise ConfigError("AA actual action differs from frozen design")
        probability = float(cfg.require("design.aa.virtual_label_probability"))
        virtual = child_rng(seed, f"{prefix}.assignment.aa_virtual_label", rep_id).random(n)
        action = np.full(n, int(override), dtype=np.int8)
        label = (virtual < probability).astype(np.int8)
        return AssignmentDraw(action, label, np.full(n, probability), np.full(n, float(override)), None)
    if cfg.require("dgp.actual_action_override") is not None:
        raise ConfigError("An actual-action override requires the explicit AA profile")
    target = float(cfg.require("design.treatment_probability"))
    if str(cfg.require("dgp.profile")) == "l3":
        if audit_u is None or np.shape(audit_u) != (n,) or not np.all(np.isfinite(audit_u)):
            raise ValueError("L3 assignment requires aligned finite audit U")
        calibration = calibrate_probability_mechanism(cfg)
        matrix = mechanism_features(users, calibration.feature_moments)
        score = float(cfg.require("dgp.l3.assignment_slope_multiplier")) * _score(matrix, cfg.section("dgp.l3.assignment_coefficients"))
        score += float(cfg.require("dgp.l3.lambda_t")) * np.asarray(audit_u)
        intercept = _intercept(score, target)
        propensity = expit(intercept + score)
        design = np.full(n, np.nan)
    else:
        if not 0 < target < 1:
            raise ConfigError("Randomized assignment probability must be interior")
        propensity = np.full(n, target)
        design = propensity.copy()
    action = (draw < propensity).astype(np.int8)
    return AssignmentDraw(action, action.copy(), design, propensity, intercept)
