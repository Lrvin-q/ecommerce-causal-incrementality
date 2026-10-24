"""Auditable Phase B checks using independent draws and posted-ledger arithmetic.

Synthetic / known DGP. These checks do not execute formal learning repetitions.
The independent MC deliberately does not use the production amount, timing,
posting or population samplers to construct its outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import hashlib
from importlib.metadata import version
import json
import os
import platform
from pathlib import Path
import time
import traceback
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy.integrate import quad
from scipy.special import expit
from scipy.stats import logistic, norm, truncnorm, uniform

from causal_growth.config import Config
from causal_growth.dgp.v3_amounts import (
    conditional_order_expectation, conditional_user_expectation,
    fulfillment_calibration, posted_components, round_ratio_cent, sample_fraction,
)
from causal_growth.dgp.v3_controls import L0ControlResult, audit_common_feasible_mask
from causal_growth.dgp.v3_covariates import generate_covariates
from causal_growth.dgp.v3_engine import audit_conditional_truth, generate_v3_population
from causal_growth.dgp.v3_probability import calibrate_probability_mechanism, purchase_probabilities
from causal_growth.dgp.v3_timing import timing_coefficients
from causal_growth.rng import child_rng
from causal_growth.v3_config import V3Protocol, load_v3_protocol
from causal_growth.v3_numerics import load_v3_numerics


@dataclass
class Moments:
    """Accumulate independent MC observations and their first four raw moments."""

    n: int = 0
    first: float = 0.0
    second: float = 0.0
    third: float = 0.0
    fourth: float = 0.0

    def add(self, values: np.ndarray) -> None:
        """Update sufficient statistics without retaining all simulated users."""
        x = np.asarray(values, dtype=float)
        self.n += x.size
        x2 = x * x
        self.first += float(x.sum())
        self.second += float(x2.sum())
        self.third += float((x2 * x).sum())
        self.fourth += float((x2 * x2).sum())

    @property
    def mean(self) -> float:
        return self.first / self.n

    @property
    def variance(self) -> float:
        return max((self.second - self.first**2 / self.n) / (self.n - 1), 0.0)

    @property
    def mean_se(self) -> float:
        return float(np.sqrt(self.variance / self.n))

    @property
    def sd_se(self) -> float:
        m = self.mean
        central_fourth = self.fourth / self.n - (2 + 2) * m * self.third / self.n
        central_fourth += (2 * (1 + 2)) * m**2 * self.second / self.n - (1 + 2) * m**4
        return float(np.sqrt(max(central_fourth - self.variance**2, 0) / self.n) / (2 * np.sqrt(self.variance))) if self.variance else 0.0


def independent_half_up(amount: np.ndarray | int, ratio: float) -> np.ndarray:
    """Check posted cents with exact rational arithmetic independent of production helpers."""
    numerator, denominator = Fraction(str(ratio)).as_integer_ratio()
    values = np.asarray(amount, dtype=np.int64)
    return ((2 * numerator * values + denominator) // (2 * denominator)).astype(np.int64)


def rejection_fraction(size: int, cfg: Config, rng: np.random.Generator) -> np.ndarray:
    """Sample Q by rejection, independently checking the production inverse-CDF path."""
    p = cfg.section("business.first_order_cart_fraction")
    values = rng.normal(p["mean_before_truncation"], p["sd_before_truncation"], size)
    invalid = (values <= p["lower_exclusive"]) | (values > p["upper_inclusive"])
    while invalid.any():
        values[invalid] = rng.normal(p["mean_before_truncation"], p["sd_before_truncation"], int(invalid.sum()))
        invalid = (values <= p["lower_exclusive"]) | (values > p["upper_inclusive"])
    return values


def independent_worlds(
    cart_cent: int, cfg: Config, size: int, *, seed: int, stream: str, chunk: int,
    purchase_probabilities: tuple[float, float],
) -> dict[int, dict[str, np.ndarray]]:
    """Generate paired worlds from fresh raw draws, retaining the full-user denominator.

    This is a validation implementation of the declared transaction truth table;
    no production posting, timing or conditional-expectation function is called.
    """
    def rng(name: str) -> np.random.Generator:
        return child_rng(seed, f"{stream}.{name}", chunk)

    unit = int(cfg.require("business.money.cents_per_yuan"))
    fraction = rejection_fraction(size, cfg, rng("q_rejection"))
    gross1 = np.floor(cart_cent * fraction).astype(np.int64)
    gross2 = independent_half_up(gross1, float(cfg.require("business.repeat.gross_value_ratio")))
    calibration = fulfillment_calibration(cfg)
    raw_f = rng("fulfillment_raw").normal(calibration.raw_location, cfg.require("business.fulfill_cost_sd"), size)
    fulfill = np.floor(unit * np.maximum(raw_f, cfg.require("business.fulfill_cost_min")) + 1 / 2).astype(np.int64)
    t = cfg.section("business.order_timing")
    first = np.clip(rng("first_delay").gamma(t["first_order_delay_gamma_shape"], t["first_order_delay_gamma_scale_days"], size), *t["first_order_delay_clip_days"])
    repeat = first + np.clip(rng("repeat_delay").gamma(t["repeat_delay_gamma_shape"], t["repeat_delay_gamma_scale_days"], size), *t["repeat_delay_clip_days"])
    refund1_day = first + rng("refund1_delay").uniform(*t["refund_delay_uniform_days"], size)
    refund2_day = repeat + rng("refund2_delay").uniform(*t["refund_delay_uniform_days"], size)
    randoms = {name: rng(name).random(size) for name in ("purchase", "repeat", "redemption", "refund1", "refund2")}
    face = int(independent_half_up(unit, float(cfg.require("business.coupon_reference_face"))))
    states: dict[int, dict[str, np.ndarray]] = {}
    for action, probability in enumerate(purchase_probabilities):
        bought = randoms["purchase"] < probability
        repeated = bought & (randoms["repeat"] < cfg.require("business.repeat.probability_given_first_order")) & bool(cfg.require("business.repeat.enabled"))
        refund_rate = cfg.require("business.refund_rate") * (cfg.require("business.refund_rate_treated_multiplier") if action else 1)
        redemption = (randoms["redemption"] < cfg.require("business.redemption_rate")) & bool(action)
        total: dict[str, np.ndarray] = {}
        any_refund = np.zeros(size, dtype=bool)
        order_count = np.zeros(size)
        for order, exists, gross, paid_day, refund_day, refund_u in (
            (0, bought, gross1, first, refund1_day, randoms["refund1"]),
            (1, repeated, gross2, repeat, refund2_day, randoms["refund2"]),
        ):
            paid = exists & (paid_day <= cfg.require("windows.profit_days"))
            refunded = paid & (refund_u < refund_rate) & (refund_day <= cfg.require("windows.profit_days"))
            discount = np.minimum(face, gross) * redemption * (order == 0)
            goods = independent_half_up(gross, float(cfg.require("business.goods_cost_ratio")))
            coupon = discount * paid - discount * refunded * bool(cfg.require("business.coupon_returned_on_refund"))
            values = {
                "gross_order_amount": gross * paid,
                "gross_refund_reversal": gross * refunded,
                "goods_cost": goods * paid,
                "goods_cost_recovered": independent_half_up(goods, float(cfg.require("business.refundable_goods_ratio"))) * refunded,
                "fulfill_cost": fulfill * paid,
                "coupon_discount": discount * paid,
                "coupon_cost": coupon,
                "refund_processing_fee": independent_half_up(gross, float(cfg.require("business.refund_handling_fee_rate"))) * refunded,
                "consumer_paid": (gross - discount) * paid,
                "consumer_refund": (gross - discount) * refunded,
            }
            for key, value in values.items():
                total[key] = total.get(key, np.zeros(size)) + value / unit
            any_refund |= refunded
            order_count += paid
        total["net_transaction_amount"] = total["gross_order_amount"] - total["gross_refund_reversal"]
        total["net_profit"] = total["net_transaction_amount"] - total["goods_cost"] + total["goods_cost_recovered"] - total["fulfill_cost"] - total["coupon_cost"] - total["refund_processing_fee"]
        total["any_refund_probability"] = any_refund.astype(float)
        total["purchase_probability_7d"] = (bought & (first <= cfg.require("windows.convert_days"))).astype(float)
        total["order_count"] = order_count
        states[action] = total
    return states


class CheckRun:
    """Persist each validation stage before raising, including all failed rows."""

    def __init__(self, output: Path, numerics: Config):
        self.output = output
        self.numerics = numerics
        self.label = str(numerics.require("validation.source_label"))
        self.records: list[dict[str, Any]] = []
        self.stage = "initializing"

    def check(self, category: str, metric: str, expected: float, observed: float, *, se: float = 0, n: int = 0, tolerance: float | None = None, **context: Any) -> None:
        """Record an explicit criterion and numerical evidence for one mechanism claim."""
        if tolerance is None:
            tolerance = max(float(self.numerics.require("validation.mc_absolute_floor_cny")), float(self.numerics.require("validation.mc_standard_error_multiplier")) * se)
        finite = np.isfinite(expected) and np.isfinite(observed) and np.isfinite(se)
        error = abs(observed - expected)
        self.records.append({"source_label": self.label, "category": category, "metric": metric,
                             "expected": expected, "observed": observed, "absolute_error": error,
                             "MC_SE": se, "n": n, "tolerance": tolerance, "passed": bool(finite and error <= tolerance), **context})

    def invariant(self, metric: str, value: bool, **context: Any) -> None:
        """Record an exact invariant; false cannot pass through a numeric tolerance."""
        self.check(self.stage, metric, 1, int(value), tolerance=0, **context)

    def table(self, filename: str, rows: pd.DataFrame | list[dict[str, Any]]) -> None:
        """Write Excel-compatible UTF-8 tables with an explicit synthetic-data label."""
        frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
        if "source_label" not in frame:
            frame.insert(0, "source_label", self.label)
        frame.to_csv(self.output / filename, index=False, encoding="utf-8-sig")

    def checkpoint(self) -> None:
        """Persist the complete ledger then raise on any failed numerical criterion."""
        self.table("checks.csv", self.records)
        failures = [r for r in self.records if not r["passed"]]
        if failures:
            raise AssertionError(f"{len(failures)} mechanism checks failed: {[(r['category'], r['metric']) for r in failures]}")


def _chunks(numerics: Config):
    n = int(numerics.require("validation.independent_mc_n"))
    size = int(numerics.require("validation.mc_chunk_size"))
    for i, start in enumerate(range(0, n, size)):
        yield i, min(size, n - start)


def _deterministic_tolerance(run: CheckRun) -> float:
    return float(run.numerics.require("integration.absolute_tolerance"))


def check_amount_distribution(run: CheckRun, protocol: V3Protocol) -> None:
    """Answer B01: truncated Q, mean-fixed cost noise, and exact cent rounding."""
    cfg = protocol.scenario("L1_main")
    seed = int(run.numerics.require("validation.master_seed"))
    p = cfg.section("business.first_order_cart_fraction")
    a = (p["lower_exclusive"] - p["mean_before_truncation"]) / p["sd_before_truncation"]
    b = (p["upper_inclusive"] - p["mean_before_truncation"]) / p["sd_before_truncation"]
    mean, variance = truncnorm.stats(a, b, loc=p["mean_before_truncation"], scale=p["sd_before_truncation"], moments="mv")
    for sampler in ("independent_rejection", "production_inverse_cdf"):
        stats = Moments()
        atoms, invalid = 0, 0
        for chunk, size in _chunks(run.numerics):
            rng = child_rng(seed, f"v3.mechanism_check.q.{sampler}", chunk)
            values = rejection_fraction(size, cfg, rng) if sampler == "independent_rejection" else sample_fraction(rng.random(size), cfg)
            stats.add(values)
            atoms += int((values == p["upper_inclusive"]).sum())
            invalid += int(((values <= p["lower_exclusive"]) | (values > p["upper_inclusive"])).sum())
        run.check("Q", "mean", float(mean), stats.mean, se=stats.mean_se, n=stats.n, sampler=sampler)
        run.check("Q", "standard_deviation", float(np.sqrt(variance)), float(np.sqrt(stats.variance)), se=stats.sd_se, n=stats.n, sampler=sampler)
        run.invariant("Q_no_clipping_atom_or_outside_value", atoms == invalid == 0, sampler=sampler, n=stats.n)
    scenarios = [s["id"] for s in protocol.config.require("scenarios") if "business.fulfill_cost_sd" in s["overrides"]] + ["L1_main"]
    calibrations = []
    for scenario_id in scenarios:
        config = protocol.scenario(scenario_id)
        calibration = fulfillment_calibration(config)
        stats = Moments()
        unit = int(config.require("business.money.cents_per_yuan"))
        for chunk, size in _chunks(run.numerics):
            raw = child_rng(seed, f"v3.mechanism_check.fulfillment.{scenario_id}", chunk).normal(calibration.raw_location, config.require("business.fulfill_cost_sd"), size)
            rounded = np.floor(np.maximum(raw, config.require("business.fulfill_cost_min")) * unit + 1 / 2) / unit
            stats.add(rounded)
        run.check("fulfillment", "fixed_post_round_mean_exact", float(config.require("business.fulfill_cost_mean")), calibration.mean, tolerance=_deterministic_tolerance(run), scenario_id=scenario_id)
        run.check("fulfillment", "mean_mc", calibration.mean, stats.mean, se=stats.mean_se, n=stats.n, scenario_id=scenario_id)
        run.check("fulfillment", "sd_mc", calibration.standard_deviation, float(np.sqrt(stats.variance)), se=stats.sd_se, n=stats.n, scenario_id=scenario_id)
        calibrations.append({"scenario_id": scenario_id, "input_sd": config.require("business.fulfill_cost_sd"), **calibration.__dict__, "mc_mean": stats.mean, "mc_variance": stats.variance, "n": stats.n})
    calibrations.sort(key=lambda row: row["input_sd"])
    run.invariant("fulfillment_variance_strictly_increases", bool(np.all(np.diff([c["standard_deviation"]**2 for c in calibrations]) > 0)))
    run.table("b01_fulfillment.csv", calibrations)
    noise_targets = []
    carts = run.numerics.require("validation.conditional_mc_cart_cents")
    probabilities = (float(cfg.require("dgp.l0.baseline_purchase_probability")),
                     float(cfg.require("dgp.l0.baseline_purchase_probability")) + float(cfg.require("dgp.l0.purchase_increment")))
    base_f = fulfillment_calibration(cfg)
    times = timing_coefficients(cfg)
    repeat_probability = float(cfg.require("business.repeat.probability_given_first_order")) if cfg.require("business.repeat.enabled") else 0
    for scenario in scenarios:
        config = protocol.scenario(scenario)
        f = fulfillment_calibration(config)
        both = []
        for action, probability in enumerate(probabilities):
            arguments = {"purchase_probability": probability,
                         "refund_probability": cfg.require("business.refund_rate") * (cfg.require("business.refund_rate_treated_multiplier") if action else 1),
                         "redemption_probability": cfg.require("business.redemption_rate") if action else 0}
            baseline = conditional_user_expectation(carts, cfg, **arguments)["net_profit"]
            candidate = conditional_user_expectation(carts, config, **arguments)["net_profit"]
            both.append(candidate)
            # F is independent of event counts and the other ledger components.
            # The shared order-fulfillment draw has coefficient K=A+AB;
            # E[K²]=p(a1+3*rho*a2), so this variance delta is exact.
            second_count = probability * (times.first_order + (1 + 2) * repeat_probability * times.repeat_order)
            variance_delta = second_count * (f.standard_deviation**2 - base_f.standard_deviation**2)
            for i, cart in enumerate(carts):
                run.check("fulfillment", "conditional_profit_mean_unchanged", float(baseline[i]), float(candidate[i]),
                          tolerance=_deterministic_tolerance(run), scenario_id=scenario, action=action, cart_cent=cart)
                noise_targets.append({"scenario_id": scenario, "cart_cent": cart, "action": action,
                                      "fixed_purchase_probability": probability, "net_profit_mean_cny": float(candidate[i]),
                                      "baseline_net_profit_mean_cny": float(baseline[i]), "input_fulfillment_sd": config.require("business.fulfill_cost_sd"),
                                      "analytic_net_profit_variance_delta_from_base_cny2": variance_delta,
                                      "variance_identity": "independent_F_shared_across_orders; E[K^2]*(VarF-VarF_base)"})
        for i, cart in enumerate(carts):
            noise_targets.append({"scenario_id": scenario, "cart_cent": cart, "action": "paired_cate",
                                  "net_profit_mean_cny": float(both[1][i] - both[0][i])})
    run.table("b01_noise_conditional_targets.csv", noise_targets)
    rounding = []
    rates = [cfg.require("business.repeat.gross_value_ratio"), cfg.require("business.goods_cost_ratio"), cfg.require("business.refundable_goods_ratio"), cfg.require("business.refund_handling_fee_rate")]
    for cents in run.numerics.require("validation.boundary_cart_cents"):
        for rate in rates:
            expected = int((Decimal(int(cents)) * Decimal(str(rate))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            observed = int(round_ratio_cent(cents, rate))
            rounding.append({"amount_cent": cents, "ratio": rate, "expected_cent": expected, "observed_cent": observed})
            run.check("rounding", "decimal_half_up", expected, observed, tolerance=_deterministic_tolerance(run), amount_cent=cents, ratio=rate)
        for redeemed in (False, True):
            for refunded in (False, True):
                got = posted_components(cents, 0, redeemed, refunded, cfg)
                goods = independent_half_up(cents, float(cfg.require("business.goods_cost_ratio")))
                recovery = independent_half_up(goods, float(cfg.require("business.refundable_goods_ratio"))) * refunded
                fee = independent_half_up(cents, float(cfg.require("business.refund_handling_fee_rate"))) * refunded
                coupon = min(int(independent_half_up(cfg.require("business.money.cents_per_yuan"), float(cfg.require("business.coupon_reference_face")))), cents) * redeemed
                expected = cents * (1 - refunded) - goods + recovery - coupon - fee
                run.check("rounding", "posted_profit_truth_table", float(expected), float(got["net_profit"]), tolerance=_deterministic_tolerance(run), amount_cent=cents, redeemed=redeemed, refunded=refunded)
    run.table("b01_rounding.csv", rounding)


def check_conditional_mc(run: CheckRun, protocol: V3Protocol) -> None:
    """Answer B01: every 30-day ledger component and paired CATE vs fresh raw MC."""
    cfg = protocol.scenario("L0_P_main")
    seed = int(run.numerics.require("validation.master_seed"))
    p0 = float(cfg.require("dgp.l0.baseline_purchase_probability"))
    p1 = p0 + float(cfg.require("dgp.l0.purchase_increment"))
    for cart in run.numerics.require("validation.conditional_mc_cart_cents"):
        stats: dict[tuple[str, str], Moments] = {}
        expected = {}
        for action, p in enumerate((p0, p1)):
            expected[action] = conditional_user_expectation(cart, cfg, purchase_probability=p,
                refund_probability=cfg.require("business.refund_rate") * (cfg.require("business.refund_rate_treated_multiplier") if action else 1),
                redemption_probability=cfg.require("business.redemption_rate") if action else 0)
        for chunk, size in _chunks(run.numerics):
            worlds = independent_worlds(cart, cfg, size, seed=seed, stream=f"v3.mechanism_check.components.cart{cart}", chunk=chunk, purchase_probabilities=(p0, p1))
            for action in (0, 1):
                for name, value in worlds[action].items():
                    stats.setdefault((str(action), name), Moments()).add(value)
            for name in worlds[0]:
                stats.setdefault(("paired_difference", name), Moments()).add(worlds[1][name] - worlds[0][name])
        for (action, name), value in stats.items():
            truth = expected[int(action)][name] if action != "paired_difference" else expected[1][name] - expected[0][name]
            run.check("conditional_components", name, float(truth), value.mean, se=value.mean_se, n=value.n, cart_cent=cart, action=action)
        run.table("b01_conditional_mc.csv", [r for r in run.records if r["category"] == "conditional_components"])
        run.checkpoint()
        print(f"  independent component MC cart={cart}: {next(iter(stats.values())).n} paired users", flush=True)


def _u_law(name: str) -> Any:
    if name == "normal":
        return norm()
    if name == "logistic_standardized":
        return logistic(scale=np.sqrt(1 + 2) / np.pi)
    if name == "uniform_bounded":
        return uniform(loc=-np.sqrt(1 + 2), scale=2 * np.sqrt(1 + 2))
    raise ValueError(name)


def _with_u_law(cfg: Config, name: str) -> Config:
    data = cfg.to_dict()
    data["dgp"]["l3"]["u_distribution"] = name
    return Config(data, name=f"{cfg.name}_audit_{name}")


def check_u_integrals(run: CheckRun, protocol: V3Protocol) -> None:
    """Answer B02: X-only targets under all U laws vs adaptive quadrature and MC."""
    cfg = protocol.scenario("L3_fixed_lt050")
    seed = int(run.numerics.require("validation.master_seed"))
    carts = run.numerics.require("validation.conditional_mc_cart_cents")
    users = generate_covariates(cfg, int(run.numerics.require("validation.representative_rep")), len(carts), pairing_group="phase_b_representative_X").users
    users["cart_value_cent"] = carts
    users["cart_value"] = users.cart_value_cent / cfg.require("business.money.cents_per_yuan")
    run.table("b02_representative_X.csv", users)
    calibration = calibrate_probability_mechanism(cfg)
    features = {"is_new": users.is_new.to_numpy()}
    for name, (mean, sd) in calibration.feature_moments.items():
        features[f"{name}_z"] = (users[name].to_numpy() - mean) / sd
    for channel in cfg.section("business.channels"):
        features[f"channel_{channel}"] = (users.channel.to_numpy() == channel).astype(float)
    score = np.full(len(users), calibration.baseline_intercept)
    effect = np.full(len(users), calibration.heterogeneity_intercept)
    for name, coefficient in cfg.section("dgp.l1.baseline_coefficients").items():
        score += coefficient * features[name]
    for name, coefficient in cfg.section("dgp.l1.effect_coefficients").items():
        effect += coefficient * features[name] * cfg.require("dgp.l1.heterogeneity_coefficient_multiplier")
    effect += cfg.require("dgp.l1.effect_interaction_is_new_cart_z") * features["is_new"] * features["cart_value_z"]
    headroom = calibration.headroom_amplitude * expit(effect)
    kernels = {}
    for action in (0, 1):
        kernels[action] = conditional_user_expectation(carts, cfg, purchase_probability=1,
            refund_probability=cfg.require("business.refund_rate") * (cfg.require("business.refund_rate_treated_multiplier") if action else 1),
            redemption_probability=cfg.require("business.redemption_rate") if action else 0)["net_profit"]
    distributions = []
    for law_name in cfg.section("dgp.l3.u_distributions"):
        config = _with_u_law(cfg, law_name)
        law = _u_law(law_name)
        lambda_y = float(config.require("dgp.l3.lambda_y"))
        production = purchase_probabilities(users, config, np.zeros(len(users)), integrate_u=True)
        stats = {(i, metric): Moments() for i in range(len(users)) for metric in ("p0", "p1", "cate_profit")}
        u_stats, all_u = Moments(), []
        for chunk, size in _chunks(run.numerics):
            u = law.rvs(size=size, random_state=child_rng(seed, f"v3.mechanism_check.u.{law_name}", chunk))
            u_stats.add(u)
            all_u.append(u)
            for i in range(len(users)):
                p0 = expit(score[i] + lambda_y * u)
                p1 = p0 + (1 - p0) * headroom[i]
                stats[i, "p0"].add(p0)
                stats[i, "p1"].add(p1)
                stats[i, "cate_profit"].add(p1 * kernels[1][i] - p0 * kernels[0][i])
        all_values = np.concatenate(all_u)
        distributions.append({"u_distribution": law_name, "n": u_stats.n, "mean": u_stats.mean,
                              "variance": u_stats.variance, "min": float(all_values.min()), "max": float(all_values.max()),
                              **{f"q_{q}": float(np.quantile(all_values, q)) for q in run.numerics.require("validation.report_quantiles")}})
        run.check("U_law", "mean", 0, u_stats.mean, se=u_stats.mean_se, n=u_stats.n, u_distribution=law_name)
        run.check("U_law", "sd", 1, float(np.sqrt(u_stats.variance)), se=u_stats.sd_se, n=u_stats.n, u_distribution=law_name)
        for i in range(len(users)):
            lower, upper = law.support()
            independent_integral, quad_error = quad(lambda u: float(expit(score[i] + lambda_y * u) * law.pdf(u)), lower, upper,
                epsabs=float(run.numerics.require("integration.quad_epsabs")),
                epsrel=float(run.numerics.require("integration.quad_epsrel")),
                limit=int(run.numerics.require("integration.quad_limit")))
            p1_integral = independent_integral + (1 - independent_integral) * headroom[i]
            exact = {"p0": float(production.p0_given_x[i]), "p1": float(production.p1_given_x[i]),
                     "cate_profit": float(production.p1_given_x[i] * kernels[1][i] - production.p0_given_x[i] * kernels[0][i])}
            adaptive = {"p0": independent_integral, "p1": p1_integral,
                        "cate_profit": p1_integral * kernels[1][i] - independent_integral * kernels[0][i]}
            for metric in exact:
                run.check("U_integral_quad", metric, adaptive[metric], exact[metric], tolerance=_deterministic_tolerance(run),
                          u_distribution=law_name, representative_row=i, cart_cent=carts[i], quad_reported_error=quad_error,
                          production_integration_diagnostic=production.integration_max_abs_error, production_nodes=production.integration_nodes)
                value = stats[i, metric]
                run.check("U_integral_MC", metric, exact[metric], value.mean, se=value.mean_se, n=value.n,
                          u_distribution=law_name, representative_row=i, cart_cent=carts[i])
        run.table("b02_u_distribution.csv", distributions)
        run.table("b02_u_integrals.csv", [r for r in run.records if r["category"].startswith("U_")])
        run.checkpoint()
        print(f"  U law {law_name}: adaptive integral and {u_stats.n} independent draws", flush=True)


def check_l3_paired(run: CheckRun, protocol: V3Protocol) -> None:
    """Answer B02: fixed-lambdaY assignment scans preserve X/U/worlds and CATE."""
    n = int(run.numerics.require("validation.mechanism_check_n"))
    rep = int(run.numerics.require("validation.representative_rep"))
    scenarios = [s for s in protocol.config.require("scenarios") if s["id"].startswith("L3_fixed_lt")]
    base = None
    baseline_truth = None
    rows = []
    for scenario in scenarios:
        cfg = protocol.scenario(scenario["id"])
        population = generate_v3_population(cfg, rep, n)
        truth = audit_conditional_truth(population, cfg)
        _save_truth_precision(run, truth, population.users, scenario["id"])
        if base is None:
            base, baseline_truth = population, truth
        run.invariant("L3_users_identical", population.users.equals(base.users), scenario_id=scenario["id"], n=n)
        run.invariant("L3_U_identical", np.array_equal(population.audit_u, base.audit_u), scenario_id=scenario["id"], n=n)
        for action in (0, 1):
            run.invariant(f"L3_potential_orders_{action}_identical", population.audit_potential_orders[action].equals(base.audit_potential_orders[action]), scenario_id=scenario["id"], n=n)
        target_columns = [c for c in truth if c != "true_propensity"]
        run.invariant("L3_integrated_truth_identical", truth[target_columns].equals(baseline_truth[target_columns]), scenario_id=scenario["id"], n=n)
        expected_share = float(cfg.require("design.treatment_probability"))
        run.check("L3_pairing", "calibrated_assignment_mean", expected_share, float(population.audit_true_propensity.mean()),
                  tolerance=_deterministic_tolerance(run), scenario_id=scenario["id"], n=n)
        run.invariant("L3_true_propensity_not_observed_design", population.assignments.design_probability.isna().all(), scenario_id=scenario["id"])
        rows.append({"scenario_id": scenario["id"], "lambda_t": cfg.require("dgp.l3.lambda_t"), "lambda_y": cfg.require("dgp.l3.lambda_y"),
                     "n": n, "actual_treatment_share": population.assignments.actual_action.mean(), "propensity_mean": population.audit_true_propensity.mean(),
                     "assignment_intercept": population.metadata["assignment_intercept"], "cate_profit_mean": truth.cate_profit.mean(),
                     "cate_profit_sd": truth.cate_profit.std(), "max_cate_difference_from_first": (truth.cate_profit - baseline_truth.cate_profit).abs().max(),
                     "changed_actions_from_first": int((population.assignments.actual_action != base.assignments.actual_action).sum()),
                     "formal_repeats_completed": 0})
        run.table("b02_l3_fixed_truth.csv", rows)
        run.checkpoint()
        print(f"  fixed-truth {scenario['id']}: paired n={n}", flush=True)


def check_l2_time_and_prefix(run: CheckRun, protocol: V3Protocol) -> None:
    """Answer B02: shared prefixes, calendar cohorts, drift and validation covariates."""
    n = int(run.numerics.require("validation.mechanism_check_n"))
    rep = int(run.numerics.require("validation.representative_rep"))
    base_cfg = protocol.scenario("L2_n200000_p050")
    base = generate_v3_population(base_cfg, rep, n)
    prefix = generate_v3_population(base_cfg, rep, n // 2)
    run.invariant("L2_covariate_public_prefix", prefix.users.equals(base.users.iloc[:n // 2].reset_index(drop=True)))
    run.invariant("L2_latent_public_prefix", np.array_equal(prefix.audit_u, base.audit_u[:n // 2]))
    for action in (0, 1):
        expected = base.audit_potential_orders[action].loc[lambda frame: frame.user_id <= n // 2].reset_index(drop=True)
        run.invariant(f"L2_potential_order_prefix_{action}", prefix.audit_potential_orders[action].equals(expected))
    rows = []
    scenarios = [s for s in protocol.config.require("scenarios") if s["level"] == "L2"]
    for scenario in scenarios:
        cfg = protocol.scenario(scenario["id"])
        batch = generate_covariates(cfg, rep, n)
        users = batch.users
        calendar = cfg.section("design.temporal")
        low, high = calendar["assignment_day_within_week_uniform"]
        day = users.assignment_day - (users.assignment_week - 1) * calendar["days_per_week"]
        run.invariant("L2_days_within_assigned_week", bool(day.between(low, high).all()), scenario_id=scenario["id"])
        for split in ("train", "validation", "test"):
            run.invariant(f"L2_{split}_weeks", bool(users.loc[users.split == split, "assignment_week"].isin(calendar[f"{split}_weeks"]).all()), scenario_id=scenario["id"])
        actual = purchase_probabilities(users, cfg, batch.audit_u, integrate_u=False)
        unshifted = purchase_probabilities(users, base_cfg, batch.audit_u, integrate_u=False)
        schedule = cfg.require(f"dgp.l2.effect_multipliers_by_active_cohort.{cfg.require('dgp.l2.drift')}")
        weights = dict(zip(calendar["assignment_weeks"], schedule, strict=True))
        expected_increment = (unshifted.p1_conditional - unshifted.p0_conditional) * users.assignment_week.map(weights).to_numpy()
        run.check("L2_time", "drift_implementation_max_error", 0, float(np.max(np.abs(actual.p1_conditional - actual.p0_conditional - expected_increment))),
                  tolerance=_deterministic_tolerance(run), scenario_id=scenario["id"])
        cohort_share = dict(zip(calendar["assignment_weeks"], calendar["cohort_shares"], strict=True))
        for week, group in users.groupby("assignment_week", sort=True):
            mask = users.assignment_week.to_numpy() == week
            run.check("L2_time", "cohort_count", n * cohort_share[week], len(group), tolerance=0, scenario_id=scenario["id"], assignment_week=week)
            rows.append({"scenario_id": scenario["id"], "registered_n": scenario["n"], "mechanism_n": n, "assignment_week": week,
                         "split": group.split.iloc[0], "cohort_n": len(group), "assignment_day_min": group.assignment_day.min(), "assignment_day_max": group.assignment_day.max(),
                         "effect_multiplier": weights[week], "mean_p0": float(actual.p0_conditional[mask].mean()),
                         "mean_purchase_increment": float((actual.p1_conditional[mask] - actual.p0_conditional[mask]).mean()),
                         "new_share": group.is_new.mean(), **{f"channel_{c}": float((group.channel == c).mean()) for c in cfg.section("business.channels")}})
        validation = generate_covariates(cfg, rep, n, population_kind="validation")
        run.invariant("L2_independent_future_validation_covariates", not set(validation.users.user_id).intersection(users.user_id)
                      and validation.stream_prefix != batch.stream_prefix
                      and bool(validation.users.assignment_week.isin(calendar["test_weeks"]).all()), scenario_id=scenario["id"])
        run.invariant("L2_independent_validation_draws_differ", not np.array_equal(validation.users.cart_value_cent, users.cart_value_cent), scenario_id=scenario["id"])
    run.table("b02_l2_cohorts.csv", rows)


def _save_truth_precision(run: CheckRun, truth: pd.DataFrame, users: pd.DataFrame, scenario: str) -> None:
    """Keep the engine's final monetary diagnostics, including zero/NA semantics."""
    diagnostics = [c for c in truth if any(token in c for token in ("error", "bound", "relative", "refin", "tolerance", "precision")) or c == "u_integration_method"]
    if not diagnostics:
        raise RuntimeError("Final engine truth has no monetary numerical-error diagnostics")
    evidence = truth.loc[:, ["user_id", "cate_profit", *diagnostics]].copy()
    evidence.insert(1, "cart_value_cent", users.set_index("user_id").loc[evidence.user_id, "cart_value_cent"].to_numpy())
    evidence["scenario_id"] = scenario
    run.table(f"b02_truth_precision_{scenario}.csv", evidence)


def _control_summary(frame: pd.DataFrame, users: pd.DataFrame, mask: np.ndarray, scenario: str, subset: str, quantiles: list[float]) -> list[dict[str, Any]]:
    result = []
    metrics = {name: frame[name].to_numpy(dtype=float) for name in (
        "goods_cost_ratio", "redemption_probability", "profit_cate_cny", "natural_profit_cate_cny", "coupon_cost_cny",
        "probability_only_feasible", "control_feasible", "knob_applied", "redemption_control_applied")}
    metrics.update({name: users[name].to_numpy(dtype=float) for name in ("is_new", "cart_value", "hist_gmv", "browse_depth")})
    for metric, values in metrics.items():
        selected = values[mask]
        result.append({"scenario_id": scenario, "subset": subset, "metric": metric, "n": int(mask.sum()), "full_n": len(frame),
                       "share_of_full": float(mask.mean()), "mean": float(selected.mean()) if selected.size else np.nan,
                       "standard_deviation": float(selected.std()) if selected.size else np.nan,
                       **{f"q_{q}": float(np.quantile(selected, q)) if selected.size else np.nan for q in quantiles}})
    for channel in users.channel.unique():
        selected = users.loc[mask, "channel"]
        result.append({"scenario_id": scenario, "subset": subset, "metric": f"channel_share_{channel}", "n": len(selected), "full_n": len(frame),
                       "share_of_full": float(mask.mean()), "mean": float((selected == channel).mean()) if len(selected) else np.nan})
    return result


def check_l0_controls(run: CheckRun, protocol: V3Protocol) -> None:
    """Answer B02: retain every user, expose both feasible domains and actual costs."""
    n = int(run.numerics.require("validation.mechanism_check_n"))
    rep = int(run.numerics.require("validation.representative_rep"))
    seed = int(run.numerics.require("validation.master_seed"))
    ids = ("L0_Pi_equal_cost", "L0_Pi_heterogeneous_cost")
    populations = {}
    control_results = {}
    for scenario in ids:
        start = time.perf_counter()
        cfg = protocol.scenario(scenario)
        print(f"  control solve {scenario}: n={n} (all failures retained)", flush=True)
        pop = generate_v3_population(cfg, rep, n)
        truth = audit_conditional_truth(pop, cfg)
        _save_truth_precision(run, truth, pop.users, scenario)
        populations[scenario] = pop
        control_results[scenario] = L0ControlResult(pop.audit_goods_cost_ratio, pop.audit_redemption_probability, pop.audit_control)
        frame = pop.audit_control.copy()
        frame.insert(0, "user_id", pop.users.user_id.to_numpy())
        frame["scenario_id"] = scenario
        frame["elapsed_seconds"] = time.perf_counter() - start
        run.table(f"b02_control_users_{scenario}.csv", frame)
        run.invariant("L0_all_users_retained", len(frame) == n and len(pop.assignments) == n, scenario_id=scenario)
        run.check("L0_controls", "solver_vs_engine_truth", 0, float(np.max(np.abs(frame.profit_cate_cny.to_numpy() - truth.cate_profit.to_numpy()))),
                  tolerance=_deterministic_tolerance(run), scenario_id=scenario, n=n)
        feasible = frame.control_feasible.to_numpy(dtype=bool)
        target = float(cfg.require("dgp.l0.control.target_profit_cate_cny"))
        tolerance = float(cfg.require("dgp.l0.control.homogeneity_numerical_tolerance_cny"))
        if feasible.any():
            run.check("L0_controls", "max_feasible_profit_residual", 0, float(np.max(np.abs(frame.loc[feasible, "profit_cate_cny"] - target))),
                      tolerance=tolerance, scenario_id=scenario, n=int(feasible.sum()))
        run.invariant("L0_infeasible_natural_goods_retained", np.all(frame.loc[~feasible, "goods_cost_ratio"] == cfg.require("business.goods_cost_ratio")), scenario_id=scenario)
        run.invariant("L0_infeasible_natural_redemption_retained", np.all(frame.loc[~feasible, "redemption_probability"] == cfg.require("business.redemption_rate")), scenario_id=scenario)
        run.invariant("L0_generation_uses_knob_arrays", np.array_equal(pop.audit_goods_cost_ratio, frame.goods_cost_ratio) and np.array_equal(pop.audit_redemption_probability, frame.redemption_probability), scenario_id=scenario)
        goods_lower = 1 - float(cfg.require("dgp.l0.control.effective_gross_margin_bounds")[1])
        goods_upper = 1 - float(cfg.require("dgp.l0.control.effective_gross_margin_bounds")[0])
        run.invariant("L0_legal_cost_rates", bool(frame.goods_cost_ratio.between(goods_lower - _deterministic_tolerance(run), goods_upper + _deterministic_tolerance(run)).all()), scenario_id=scenario)
        run.invariant("L0_legal_redemption_rates", bool(frame.redemption_probability.between(0, 1).all()), scenario_id=scenario)
        if cfg.require("dgp.l0.control.cost_mode") == "constant_expected_cost" and feasible.any():
            run.check("L0_controls", "equal_expected_cost_on_feasible", 0,
                      float(np.max(np.abs(frame.loc[feasible, "coupon_cost_cny"] - cfg.require("dgp.l0.control.constant_expected_coupon_cost_cny")))),
                      tolerance=_deterministic_tolerance(run), scenario_id=scenario, n=int(feasible.sum()))
        # Inspect actual generated order entries using Decimal, not the amount helper.
        redemption_draw = pd.Series(child_rng(int(cfg.require("project.master_seed")),
                                             f"{pop.metadata['stream_prefix']}.outcomes.redemption", rep).random(n), index=pop.users.user_id)
        redemption_by_user = pd.Series(pop.audit_redemption_probability, index=pop.users.user_id)
        face_cent = int(independent_half_up(int(cfg.require("business.money.cents_per_yuan")), float(cfg.require("business.coupon_reference_face"))))
        for action, orders in pop.audit_potential_orders.items():
            rates = pd.Series(pop.audit_goods_cost_ratio, index=pop.users.user_id).loc[orders.user_id].to_numpy()
            exact_goods = np.array([int((Decimal(int(g)) * Decimal(str(r))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                                    for g, r in zip(orders.gross_order_amount_cent, rates, strict=True)])
            run.invariant("L0_generated_goods_postings_match_decimal", np.array_equal(exact_goods, orders.goods_cost_cent), scenario_id=scenario, action=action)
            expected_discount = (np.minimum(face_cent, orders.gross_order_amount_cent.to_numpy())
                                 * (redemption_draw.loc[orders.user_id].to_numpy() < redemption_by_user.loc[orders.user_id].to_numpy())
                                 * (orders.order_number.to_numpy() == 1) * action)
            run.invariant("L0_actual_engine_uses_controlled_redemption", np.array_equal(expected_discount, orders.coupon_discount_cent), scenario_id=scenario, action=action)
            if action == 0:
                run.invariant("L0_control_world_no_coupon", bool((orders.coupon_discount_cent == 0).all()), scenario_id=scenario)
        print(f"  control {scenario}: {int(feasible.sum())}/{n} feasible, elapsed {time.perf_counter()-start:.1f}s", flush=True)
        run.checkpoint()
    common = audit_common_feasible_mask(control_results[ids[0]], control_results[ids[1]])
    run.invariant("L0_control_common_user_order", populations[ids[0]].users.equals(populations[ids[1]].users))
    summaries, reasons = [], []
    for scenario in ids:
        cfg, pop = protocol.scenario(scenario), populations[scenario]
        frame = pop.audit_control
        masks = {"full": np.ones(n, dtype=bool), "own_feasible": frame.control_feasible.to_numpy(dtype=bool), "common_feasible": common,
                 "outside_own_feasible": ~frame.control_feasible.to_numpy(dtype=bool)}
        for subset, mask in masks.items():
            summaries.extend(_control_summary(frame, pop.users, mask, scenario, subset, run.numerics.require("validation.report_quantiles")))
        for reason, count in frame.reason.value_counts(dropna=False).items():
            reasons.append({"scenario_id": scenario, "reason": reason, "count": count, "n": n, "share": count / n})
        indexed = frame.copy()
        indexed.insert(0, "user_id", pop.users.user_id)
        indexed["common_feasible"] = common
        run.table(f"b02_control_domains_{scenario}.csv", indexed)
        # Re-sample actual purchase/redemption/capped-discount events over the
        # fixed observed cart population; never pass a constant cost to the sampler.
        cost_stats = {name: Moments() for name, mask in masks.items() if mask.any()}
        unit = int(cfg.require("business.money.cents_per_yuan"))
        face = int(independent_half_up(unit, float(cfg.require("business.coupon_reference_face"))))
        for chunk, size in _chunks(run.numerics):
            stream = f"v3.mechanism_check.control_cost.{scenario}"
            indexes = child_rng(seed, f"{stream}.user_index", chunk).integers(0, n, size)
            q = rejection_fraction(size, cfg, child_rng(seed, f"{stream}.q_rejection", chunk))
            gross = np.floor(frame.cart_cent.to_numpy()[indexes] * q).astype(np.int64)
            bought = child_rng(seed, f"{stream}.purchase", chunk).random(size) < frame.p1.to_numpy()[indexes]
            redeemed = child_rng(seed, f"{stream}.redemption", chunk).random(size) < pop.audit_redemption_probability[indexes]
            # Frozen control first orders all lie in the 30-day window; explicitly
            # reject incompatible extensions rather than silently ignore them.
            run.invariant("L0_cost_MC_window_assumption", cfg.require("business.order_timing.first_order_delay_clip_days")[1] <= cfg.require("windows.profit_days")
                          and not cfg.require("business.coupon_returned_on_refund"), scenario_id=scenario, chunk=chunk)
            realized = np.minimum(face, gross) * bought * redeemed / unit
            for subset, stats in cost_stats.items():
                stats.add(realized[masks[subset][indexes]])
        for subset, stats in cost_stats.items():
            run.check("L0_actual_redemption_MC", "coupon_cost", float(frame.loc[masks[subset], "coupon_cost_cny"].mean()), stats.mean,
                      se=stats.mean_se, n=stats.n, scenario_id=scenario, subset=subset,
                      total_generated_n=int(run.numerics.require("validation.independent_mc_n")))
    run.table("b02_control_summary.csv", summaries)
    run.table("b02_control_failure_reasons.csv", reasons)
    run.table("b02_control_actual_cost_mc.csv", [r for r in run.records if r["category"] == "L0_actual_redemption_MC"])


def check_negative_controls(run: CheckRun, protocol: V3Protocol) -> None:
    """Distinguish zero purchase increment from true randomized AA labels."""
    n = int(run.numerics.require("validation.mechanism_check_n"))
    rep = int(run.numerics.require("validation.representative_rep"))
    rows = []
    for scenario in ("L0_P_main", "L0_zero_purchase_effect", "L0_AA"):
        cfg = protocol.scenario(scenario)
        pop = generate_v3_population(cfg, rep, n)
        truth = audit_conditional_truth(pop, cfg)
        rows.append({"scenario_id": scenario, "n": n, "mean_purchase_cate": truth.cate_purchase_7d.mean(), "mean_profit_cate": truth.cate_profit.mean(),
                     "mean_label_cate": truth.label_cate_profit.mean(), "actual_action_share": pop.assignments.actual_action.mean(),
                     "label_share": pop.assignments.label.mean(), "observed_order_count": len(pop.observed_orders)})
        if scenario == "L0_zero_purchase_effect":
            run.invariant("zero_purchase_increment_is_not_profit_AA", bool((truth.cate_purchase_7d == 0).all()) and float(truth.cate_profit.mean()) < 0)
        if scenario == "L0_AA":
            run.invariant("AA_actual_actions_match_protocol", bool((pop.assignments.actual_action == cfg.require("design.aa.actual_action")).all()))
            run.invariant("AA_label_truth_zero", bool((truth.label_cate_profit == 0).all()))
            run.invariant("AA_virtual_labels_both_present", pop.assignments.label.nunique() == 2)
            run.invariant("AA_observed_orders_have_only_real_action", bool((pop.observed_orders.action == cfg.require("design.aa.actual_action")).all()))
    run.table("b02_negative_controls.csv", rows)


def _source_hashes(root: Path) -> dict[str, str]:
    paths = list((root / "configs/v3").glob("*.yaml")) + [root / "configs/v3_numerics.yaml"]
    paths += list((root / "src/causal_growth/dgp").glob("v3_*.py"))
    paths += [root / "src/causal_growth/evaluation/v3_mechanism_checks.py", root / "scripts/10_validate_v3_mechanism.py",
              root / "src/causal_growth/v3_config.py", root / "src/causal_growth/v3_numerics.py", root / "src/causal_growth/rng.py",
              root / "src/causal_growth/config.py"]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def run_mechanism_validation(output_root: Path) -> Path:
    """Execute B01/B02 with running/failed/passed states, immutable attempts and hashes."""
    root = Path(__file__).resolve().parents[3]
    started = datetime.now(timezone.utc)
    output = Path(output_root) / ("phase_b_" + started.strftime("%Y%m%dT%H%M%S%fZ") + f"_pid{os.getpid()}")
    output.mkdir(parents=True, exist_ok=False)
    numerics, protocol = load_v3_numerics(), load_v3_protocol()
    run = CheckRun(output, numerics)
    before = _source_hashes(root)
    manifest: dict[str, Any] = {"status": "running", "started_at_utc": started.isoformat(), "pid": os.getpid(),
        "source_label": run.label, "formal_repetitions_completed": 0, "protocol_hash": protocol.config_hash,
        "numerics_hash": numerics.hash(64), "source_hashes": before, "validation_parameters": numerics.section("validation"), "stages": [],
        "python_version": platform.python_version(), "dependency_versions": {name: version(name) for name in ("numpy", "pandas", "scipy", "PyYAML")}}

    def write_manifest() -> None:
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    write_manifest()
    print(f"Validation output: {output}", flush=True)
    checks: list[tuple[str, Callable[[CheckRun, V3Protocol], None]]] = [
        ("b01_amount_distribution", check_amount_distribution), ("b01_conditional_mc", check_conditional_mc),
        ("b02_u_integrals", check_u_integrals), ("b02_l3_fixed_truth", check_l3_paired),
        ("b02_l2_calendar", check_l2_time_and_prefix), ("b02_l0_controls", check_l0_controls),
        ("b02_negative_controls", check_negative_controls),
    ]
    try:
        for name, function in checks:
            run.stage = name
            stage = {"name": name, "status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat()}
            manifest["stages"].append(stage)
            write_manifest()
            print(f"[{name}] running", flush=True)
            tick = time.perf_counter()
            function(run, protocol)
            run.checkpoint()
            stage.update(status="passed", elapsed_seconds=time.perf_counter() - tick)
            write_manifest()
            print(f"[{name}] passed in {stage['elapsed_seconds']:.2f}s", flush=True)
        after = _source_hashes(root)
        manifest["source_hashes_after"] = after
        if before != after:
            raise RuntimeError("Sources changed during validation; retain this attempt but rerun the final source state")
        manifest["status"] = "passed"
    except BaseException as exc:
        manifest.update(status="failed", error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
        if manifest["stages"] and manifest["stages"][-1]["status"] == "running":
            manifest["stages"][-1]["status"] = "failed"
        run.table("checks.csv", run.records)
        raise
    finally:
        manifest["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["n_checks"] = len(run.records)
        manifest["n_failed_checks"] = sum(not r["passed"] for r in run.records)
        manifest["outputs"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob("*.csv"))}
        write_manifest()
    return output
