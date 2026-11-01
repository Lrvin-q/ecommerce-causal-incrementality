"""Four-layer v3 simulator with explicitly separate observations and audit state.

Synthetic / known DGP. The five-table pipeline receives observation_bundle();
potential worlds, true propensities and conditional expectations stay here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from causal_growth.config import Config
from causal_growth.dgp.v3_amounts import (
    AmountDraws, conditional_expectation_numerical_error, conditional_user_expectation,
    paired_conditional_expectation_numerical_error, posted_components, sample_amounts,
)
from causal_growth.dgp.v3_covariates import generate_covariates
from causal_growth.dgp.v3_ledger import ORDER_COLUMNS, audit_window_ledger
from causal_growth.dgp.v3_probability import AssignmentDraw, PurchaseProbabilities, assign_treatment, purchase_probabilities
from causal_growth.dgp.v3_semantics import validate_mechanism_semantics
from causal_growth.dgp.v3_timing import OrderTiming, sample_order_timing
from causal_growth.rng import child_rng
from causal_growth.v3_numerics import load_v3_numerics


@dataclass
class V3Population:
    """Observed inputs and isolated simulation state for one repetition.

    Arrays prefixed audit_ are forbidden learner inputs. They support mechanism
    verification and the final frozen-policy audit, not the SQL analysis path.
    """

    users: pd.DataFrame
    assignments: pd.DataFrame
    observed_orders: pd.DataFrame
    audit_potential_orders: dict[int, pd.DataFrame]
    audit_probabilities: PurchaseProbabilities
    audit_u: np.ndarray
    audit_true_propensity: np.ndarray
    audit_goods_cost_ratio: np.ndarray
    audit_redemption_probability: np.ndarray
    audit_control: pd.DataFrame | None
    metadata: dict[str, Any]
    audit_u_integral_refined: np.ndarray | None = None

    def observation_bundle(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Supply only factual inputs to Phase C's five-table construction."""
        return self.users.copy(), self.assignments.copy(), self.observed_orders.copy()


def _world_orders(
    users: pd.DataFrame, cfg: Config, action: int, purchase: np.ndarray,
    uniforms: dict[str, np.ndarray], amounts: AmountDraws, times: OrderTiming,
    goods_ratio: np.ndarray, redemption_probability: np.ndarray,
) -> pd.DataFrame:
    purchased = uniforms["purchase"] < purchase
    repeated = purchased & (uniforms["repeat"] < float(cfg.require("business.repeat.probability_given_first_order")))
    if not cfg.require("business.repeat.enabled"):
        repeated[:] = False
    refund_rate = float(cfg.require("business.refund_rate"))
    if action:
        refund_rate *= float(cfg.require("business.refund_rate_treated_multiplier"))
    if not 0 <= refund_rate <= 1:
        raise ValueError("action-specific refund probability outside [0,1]")
    redeemed = (uniforms["redemption"] < redemption_probability) & bool(action)
    rows: list[pd.DataFrame] = []
    for number, mask, gross, paid_day, refund_day, refund_uniform in (
        (1, purchased, amounts.first_gross_cent, times.first_order_day, times.first_refund_day, uniforms["refund_first"]),
        (2, repeated, amounts.repeat_gross_cent, times.repeat_order_day, times.repeat_refund_day, uniforms["refund_repeat"]),
    ):
        selected = np.flatnonzero(mask)
        if not len(selected):
            continue
        refund = refund_uniform[selected] < refund_rate
        initial = posted_components(gross[selected], amounts.fulfill_cent[selected], redeemed[selected], np.zeros(len(selected), bool),
                                    cfg, goods_cost_ratio=goods_ratio[selected], coupon_eligible=number == 1)
        final = posted_components(gross[selected], amounts.fulfill_cent[selected], redeemed[selected], refund,
                                  cfg, goods_cost_ratio=goods_ratio[selected], coupon_eligible=number == 1)
        assigned = users["assignment_day"].to_numpy()[selected]
        ids = users["user_id"].to_numpy()[selected]
        frame = pd.DataFrame({
            "user_id": ids, "order_id": ids * 2 + number - 1, "order_number": number,
            "action": action, "assignment_day": assigned,
            "paid_day": assigned + paid_day[selected],
            "refund_day": np.where(refund, assigned + refund_day[selected], np.nan),
            "refunded": refund,
        })
        for name in ("gross_order_amount", "goods_cost", "fulfill_cost", "coupon_discount", "consumer_paid"):
            frame[f"{name}_cent"] = initial[name]
        frame["coupon_cost_initial_cent"] = initial["coupon_cost"]
        for name in ("goods_cost_recovered", "refund_processing_fee", "gross_refund_reversal", "consumer_refund"):
            frame[f"{name}_cent"] = final[name]
        frame["coupon_return_cent"] = initial["coupon_cost"] - final["coupon_cost"]
        rows.append(frame.loc[:, ORDER_COLUMNS])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=ORDER_COLUMNS)


def generate_v3_population(
    cfg: Config, rep_id: int = 0, n: int | None = None, *,
    population_kind: str = "history", pairing_group: str | None = None,
    validation_assignment: pd.DataFrame | None = None,
) -> V3Population:
    """Generate four-layer monetary mechanisms while keeping U/truth out of observations.

    n is an explicit mechanism-check size; formal runners must enforce the
    registered n before calling. No formal completion counter is changed here.
    """
    validate_mechanism_semantics(cfg)
    batch = generate_covariates(cfg, rep_id, n, population_kind=population_kind, pairing_group=pairing_group)
    users, size = batch.users, len(batch.users)
    probabilities = purchase_probabilities(users, cfg, batch.audit_u, integrate_u=bool(cfg.require("dgp.l0.control.enabled")))
    policy_rows = None
    if population_kind == "validation":
        if validation_assignment is None:
            raise ValueError("validation requires frozen policy-arm assignments, not historical treatment allocation")
        required = {"user_id", "assigned_policy_arm", "issued_action", "policy_arm_probability"}
        if required - set(validation_assignment):
            raise ValueError("validation policy assignments lack required columns")
        if not validation_assignment.user_id.is_unique or set(validation_assignment.user_id) != set(users.user_id):
            raise ValueError("validation policy assignments do not align with every new user")
        policy_rows = validation_assignment.set_index("user_id").loc[users.user_id].reset_index()
        arms = tuple(cfg.require("evaluation.independent_validation.arms"))
        if not policy_rows.assigned_policy_arm.isin(arms).all() or not policy_rows.issued_action.isin((0, 1)).all():
            raise ValueError("unknown validation policy arm/action")
        arm_probabilities = dict(zip(arms, cfg.require("evaluation.independent_validation.arm_probabilities"), strict=True))
        if not np.allclose(policy_rows.policy_arm_probability, policy_rows.assigned_policy_arm.map(arm_probabilities),
                           atol=float(cfg.require("design.numerical.probability_tolerance")), rtol=0):
            raise ValueError("policy-arm probabilities conflict with frozen randomization")
        if (policy_rows.loc[policy_rows.assigned_policy_arm == "no_coupon", "issued_action"] != 0).any():
            raise ValueError("no-coupon policy arm cannot issue coupons")
        assignment = AssignmentDraw(policy_rows.issued_action.to_numpy(), policy_rows.assigned_policy_arm.to_numpy(),
                                    np.full(size, np.nan), np.full(size, np.nan), None)
    elif population_kind == "history" and validation_assignment is None:
        assignment = assign_treatment(users, cfg, rep_id, audit_u=batch.audit_u,
                                      population_kind=population_kind, pairing_group=pairing_group)
    else:
        raise ValueError("population kind or policy assignment conflicts with generation role")
    seed = int(cfg.require("project.master_seed"))
    uniforms = {name: child_rng(seed, f"{batch.stream_prefix}.outcomes.{name}", rep_id).random(size)
                for name in ("purchase", "repeat", "redemption", "refund_first", "refund_repeat")}
    amounts = sample_amounts(users["cart_value_cent"].to_numpy(), cfg, master_seed=seed, stream=batch.stream_prefix, index=rep_id)
    timing = sample_order_timing(size, cfg, master_seed=seed, stream=batch.stream_prefix, index=rep_id)
    goods = np.full(size, float(cfg.require("business.goods_cost_ratio")))
    redemption = np.full(size, float(cfg.require("business.redemption_rate")))
    control_audit = None
    if cfg.require("dgp.l0.control.enabled"):
        from causal_growth.dgp.v3_controls import solve_l0_profit_control

        control = solve_l0_profit_control(users["cart_value_cent"].to_numpy(), probabilities.p0_given_x,
                                         probabilities.p1_given_x, cfg)
        goods, redemption = control.goods_cost_ratio, control.redemption_probability
        control_audit = control.audit
    worlds = {
        action: _world_orders(users, cfg, action, probability, uniforms, amounts, timing, goods, redemption)
        for action, probability in ((0, probabilities.p0_conditional), (1, probabilities.p1_conditional))
    }
    assignments = pd.DataFrame({"user_id": users.user_id.to_numpy(), "actual_action": assignment.action,
                                "label": assignment.label, "design_probability": assignment.design_probability})
    if policy_rows is not None:
        assignments["assigned_policy_arm"] = policy_rows.assigned_policy_arm.to_numpy()
        assignments["policy_arm_probability"] = policy_rows.policy_arm_probability.to_numpy()
    lookup = assignments.set_index("user_id")["actual_action"]
    observed = pd.concat([world.loc[world.user_id.map(lookup) == action] for action, world in worlds.items()], ignore_index=True)
    metadata = {
        "data_source": cfg.require("project.data_source_label"), "scenario_id": cfg.require("active_scenario.id"),
        "level": cfg.require("active_scenario.level"), "rep_id": rep_id, "n_users": size,
        "registered_n": int(cfg.require("design.n_total")), "population_kind": population_kind,
        "stream_prefix": batch.stream_prefix, "master_seed": seed, "config_hash": cfg.hash(64),
        "numerics_hash": load_v3_numerics().hash(64), "assignment_intercept": assignment.intercept,
        "u_integration_max_abs_error": probabilities.integration_max_abs_error,
        "u_integration_nodes": probabilities.integration_nodes,
        "calibration": asdict(probabilities.calibration) if probabilities.calibration else None,
        "observed_order_count": len(observed), "formal_completion_claim": False,
    }
    return V3Population(users, assignments, observed, worlds, probabilities, batch.audit_u,
                        assignment.true_propensity, goods, redemption, control_audit, metadata)


def audit_conditional_truth(population: V3Population, cfg: Config) -> pd.DataFrame:
    """Integrate Q, ledger rounding, events and U for the X-only CATE audit target.

    The X,U target and realized coupled difference are separate columns. Neither
    is substituted for the X-only target used to assess models with X inputs.
    """
    _validate_audit_binding(population, cfg)
    validate_mechanism_semantics(cfg)
    probs = population.audit_probabilities
    if probs.p0_given_x is None or probs.p1_given_x is None:
        probs = purchase_probabilities(population.users, cfg, population.audit_u, integrate_u=True)
        population.audit_probabilities = probs
        population.metadata["u_integration_max_abs_error"] = probs.integration_max_abs_error
        population.metadata["u_integration_nodes"] = probs.integration_nodes
    refined_rows = (np.zeros(len(population.users), dtype=bool) if population.audit_u_integral_refined is None
                    else population.audit_u_integral_refined.copy())
    for attempt in (0, 1):
        result = _conditional_truth_with_errors(population, cfg)
        bad = ~result["profit_precision_pass"].to_numpy()
        if not bad.any():
            result["u_integral_refined"] = refined_rows
            result["u_integration_method"] = np.where(refined_rows, "adaptive", "batched") if cfg.require("dgp.profile") == "l3" else "not_required"
            population.metadata["u_integral_refined_rows"] = int(refined_rows.sum())
            population.metadata["u_integration_max_abs_error"] = population.audit_probabilities.integration_max_abs_error
            population.metadata["u_audit_integration_methods"] = sorted(result.u_integration_method.unique().tolist())
            population.metadata["audit_numerics_hash"] = load_v3_numerics().hash(64)
            return result
        if attempt == 0 and cfg.require("dgp.profile") == "l3":
            refined = purchase_probabilities(population.users.loc[bad], cfg, population.audit_u[bad],
                                             integrate_u=True, integration_method="adaptive")
            current = population.audit_probabilities
            x0, x1 = current.p0_given_x.copy(), current.p1_given_x.copy()
            error = current.integration_error_per_row.copy()
            x0[bad], x1[bad], error[bad] = refined.p0_given_x, refined.p1_given_x, refined.integration_error_per_row
            population.audit_probabilities = replace(current, p0_given_x=x0, p1_given_x=x1,
                                                       integration_error_per_row=error,
                                                       integration_max_abs_error=float(error.max(initial=0)))
            refined_rows |= bad
            population.audit_u_integral_refined = refined_rows.copy()
            continue
        raise ArithmeticError(
            f"profit truth failed absolute and relative numerical gates for {int(bad.sum())} users; "
            f"max CATE error estimate={result.loc[bad, 'cate_numerical_error_estimate_cny'].max():.6g}, "
            f"max relative estimate={result.loc[bad, 'cate_relative_error_estimate'].max():.6g}"
        )
    raise AssertionError("unreachable numerical-refinement state")


def _conditional_truth_with_errors(population: V3Population, cfg: Config) -> pd.DataFrame:
    probs = population.audit_probabilities
    cart = population.users.cart_value_cent.to_numpy()
    result = pd.DataFrame({"user_id": population.users.user_id.to_numpy(), "audit_u": population.audit_u,
                           "true_propensity": population.audit_true_propensity})
    per_purchase: dict[int, np.ndarray] = {}
    kernel_error: dict[int, np.ndarray] = {}
    arm_error: dict[int, np.ndarray] = {}
    refund_rates: dict[int, float] = {}
    u_error = probs.integration_error_per_row
    if u_error is None:
        raise AssertionError("X-only truth requires computed pointwise probability integration errors")
    complement = 1 - probs.p0_given_x
    headroom = np.divide(probs.p1_given_x - probs.p0_given_x, complement,
                         out=np.zeros(len(cart)), where=complement > 0)
    for action in (0, 1):
        refund = float(cfg.require("business.refund_rate")) * (float(cfg.require("business.refund_rate_treated_multiplier")) if action else 1)
        refund_rates[action] = refund
        redemption = population.audit_redemption_probability if action else 0
        p_x = probs.p1_given_x if action else probs.p0_given_x
        p_xu = probs.p1_conditional if action else probs.p0_conditional
        expected = conditional_user_expectation(cart, cfg, purchase_probability=p_x, refund_probability=refund,
                                               redemption_probability=redemption, goods_cost_ratio=population.audit_goods_cost_ratio)
        result[f"purchase_probability_x_{action}"] = p_x
        result[f"purchase_probability_xu_{action}"] = p_xu
        for name, values in expected.items():
            result[f"expected_{name}_{action}"] = values
        # Q/costs/timing are independent of U given recorded X and the action.
        conditional_per_purchase = conditional_user_expectation(cart, cfg, purchase_probability=1,
                                                                refund_probability=refund, redemption_probability=redemption,
                                                                goods_cost_ratio=population.audit_goods_cost_ratio)
        per_purchase[action] = conditional_per_purchase["net_profit"]
        conditional_error = conditional_expectation_numerical_error(
            cart, cfg, purchase_probability=1, refund_probability=refund,
            redemption_probability=redemption, goods_cost_ratio=population.audit_goods_cost_ratio,
        )
        kernel_error[action] = conditional_error["net_profit_numerical_error_estimate_cny"]
        sensitivity = 1 - headroom if action else np.ones(len(cart))
        probability_error = u_error * sensitivity
        # The product of the probability and monetary approximation errors is retained.
        arm_error[action] = (p_x * kernel_error[action]
                             + probability_error * (np.abs(per_purchase[action]) + kernel_error[action]))
        result[f"net_profit_error_estimate_cny_{action}"] = arm_error[action]
        result[f"expected_net_profit_xu_{action}"] = p_xu * conditional_per_purchase["net_profit"]
    paired = paired_conditional_expectation_numerical_error(
        cart, cfg, purchase_probability0=probs.p0_given_x, purchase_probability1=probs.p1_given_x,
        refund_probability0=refund_rates[0], refund_probability1=refund_rates[1],
        redemption_probability0=0, redemption_probability1=population.audit_redemption_probability,
        goods_cost_ratio=population.audit_goods_cost_ratio,
    )
    result["cate_profit"] = paired["net_profit_difference_cny"]
    u_sensitivity = np.abs((1 - headroom) * per_purchase[1] - per_purchase[0])
    u_sensitivity = np.where(complement > 0, u_sensitivity, np.abs(per_purchase[0]) + np.abs(per_purchase[1]))
    u_profit_error = u_error * (u_sensitivity + kernel_error[0] + kernel_error[1])
    result["cate_amount_time_error_estimate_cny"] = paired["net_profit_numerical_error_estimate_cny"]
    for name, value in paired.items():
        if name.startswith("net_profit_") and name not in {"net_profit_difference_cny", "net_profit_numerical_error_estimate_cny"}:
            result[f"cate_{name.removeprefix('net_profit_')}"] = value
    result["cate_u_error_estimate_cny"] = u_profit_error
    result["cate_numerical_error_estimate_cny"] = paired["net_profit_numerical_error_estimate_cny"] + u_profit_error
    result["u_probability_error_estimate"] = u_error
    numerics = load_v3_numerics()
    absolute = float(numerics.require("integration.absolute_tolerance"))
    relative = float(numerics.require("integration.relative_tolerance"))
    result["absolute_tolerance_cny"] = absolute
    result["relative_tolerance"] = relative
    passes = np.ones(len(cart), dtype=bool)
    for target, error, name in (
        (result.expected_net_profit_0.to_numpy(), arm_error[0], "mu0"),
        (result.expected_net_profit_1.to_numpy(), arm_error[1], "mu1"),
        (result.cate_profit.to_numpy(), result.cate_numerical_error_estimate_cny.to_numpy(), "cate"),
    ):
        rel = np.divide(error, np.abs(target), out=np.full(len(cart), np.nan), where=target != 0)
        result[f"{name}_relative_error_estimate"] = rel
        result[f"{name}_relative_error_defined"] = target != 0
        passes &= np.isfinite(target) & np.isfinite(error) & (error <= absolute) & ((target == 0) | (rel <= relative))
    result["profit_precision_pass"] = passes
    result["cate_profit_xu"] = result.expected_net_profit_xu_1 - result.expected_net_profit_xu_0
    result["cate_purchase_7d"] = result.expected_purchase_probability_7d_1 - result.expected_purchase_probability_7d_0
    result["cate_any_refund_30d"] = result.expected_any_refund_probability_1 - result.expected_any_refund_probability_0
    result["label_cate_profit"] = 0 if cfg.require("dgp.virtual_aa_labels") else result.cate_profit
    return result


def audit_realized_worlds(population: V3Population, cfg: Config) -> dict[int, pd.DataFrame]:
    """Expose a windowed array ledger only for mechanism/SQL reconciliation audits."""
    _validate_audit_binding(population, cfg)
    return {action: audit_window_ledger(population.users, orders, cfg) for action, orders in population.audit_potential_orders.items()}


def _validate_audit_binding(population: V3Population, cfg: Config) -> None:
    if cfg.hash(64) != population.metadata["config_hash"]:
        raise ValueError("audit configuration does not match the generated population")
    if load_v3_numerics().hash(64) != population.metadata["numerics_hash"]:
        raise ValueError("audit numerical configuration does not match the generated population")
