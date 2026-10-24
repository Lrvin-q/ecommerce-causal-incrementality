"""Recorded v3 covariates and isolated latent U (synthetic / known DGP).

Each feature has its own named stream. Extending n therefore preserves earlier
users, while a separate validation stream creates genuinely new users.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import lcm

import numpy as np
import pandas as pd
from scipy.special import ndtri

from causal_growth.config import Config, ConfigError
from causal_growth.rng import child_rng


@dataclass(frozen=True)
class CovariateBatch:
    """Keep recorded users separate from U, which is only available to audit."""

    users: pd.DataFrame
    audit_u: np.ndarray
    stream_prefix: str


def stream_prefix(cfg: Config, population_kind: str, pairing_group: str | None = None) -> str:
    """Resolve cross-family references so controlled contrasts share latent draws."""
    if population_kind not in {"history", "validation", "reference"}:
        raise ValueError(f"Unknown population kind: {population_kind}")
    group = pairing_group or str(cfg.require("active_scenario.pairing_group"))
    # Frozen matrix references define intentional comparisons across named groups.
    references = cfg.section("matrix_contract.cross_pairing_references")
    cells = {cell["id"]: cell for cell in cfg.require("scenarios")}
    seen: set[str] = set()
    while group in references:
        if group in seen:
            raise ConfigError("Cyclic cross-pairing reference")
        seen.add(group)
        group = cells[references[group]]["pairing_group"]
    return f"v3.{group}.{population_kind}"


def standardized_u(uniform: np.ndarray, distribution: str) -> np.ndarray:
    """Map one common uniform stream to the three mean-zero, variance-one U laws."""
    q = np.asarray(uniform, dtype=float)
    if np.any(~np.isfinite(q)) or np.any((q <= 0) | (q >= 1)):
        raise ValueError("U inverse CDF requires strictly interior uniform draws")
    three = 1 + 2
    if distribution == "normal":
        return ndtri(q)
    if distribution == "logistic_standardized":
        return (np.log(q) - np.log1p(-q)) * np.sqrt(three) / np.pi
    if distribution == "uniform_bounded":
        return (2 * q - 1) * np.sqrt(three)
    raise ConfigError(f"Unknown U distribution: {distribution}")


def _balanced_labels(n: int, shares: tuple[float, ...], rng: np.random.Generator) -> np.ndarray:
    fractions = [Fraction(str(value)) for value in shares]
    if sum(fractions) != 1 or any(value <= 0 for value in fractions):
        raise ConfigError("Cohort shares must be positive and sum exactly to one")
    block = lcm(*(value.denominator for value in fractions))
    labels = np.repeat(np.arange(len(shares)), [int(value * block) for value in fractions])
    count = (n + block - 1) // block
    # Drawing the same complete block even for a partial suffix preserves prefixes.
    order = np.argsort(rng.random((count, block)), axis=1, kind="stable")
    return np.take(labels, order).ravel()[:n]


def _uniform(cfg: Config, prefix: str, name: str, rep_id: int, n: int) -> np.ndarray:
    q = child_rng(int(cfg.require("project.master_seed")), f"{prefix}.covariates.{name}", rep_id).random(n)
    # Generator can emit exact zero. Replace that endpoint only by the adjacent
    # representable interior number, rather than clipping the simulated law.
    return np.maximum(q, np.nextafter(0.0, 1.0))


def generate_covariates(
    cfg: Config,
    rep_id: int,
    n: int | None = None,
    *,
    population_kind: str = "history",
    pairing_group: str | None = None,
) -> CovariateBatch:
    """Generate recorded X, calendar cohorts and audit U for one v3 population.

    Non-temporal historical splits are deliberately pending: Phase C performs
    frozen treatment/channel/new-user stratification after action assignment.
    L2 assigns calendar cohorts before outcomes. Validation uses only future
    test cohorts, matching the target population of historical evaluation.
    """
    size = int(n if n is not None else cfg.require("design.n_total"))
    if size <= 0:
        raise ValueError("n must be positive")
    prefix = stream_prefix(cfg, population_kind, pairing_group)
    seed = int(cfg.require("project.master_seed"))
    profile = str(cfg.require("dgp.profile"))
    temporal = profile == "l2" and population_kind != "reference"
    weeks = np.ones(size, dtype=np.int64)
    split = np.full(size, "pending_stratified", dtype=object)
    new_share = np.full(size, float(cfg.require("business.new_user_share")))
    base_channels = cfg.section("business.channels")
    channel_names = list(base_channels)
    channel_probs = np.tile(np.array(list(base_channels.values())), (size, 1))
    if temporal:
        all_weeks = np.asarray(cfg.require("design.temporal.assignment_weeks"), dtype=np.int64)
        if population_kind == "validation":
            eligible = np.isin(all_weeks, cfg.require("design.temporal.test_weeks"))
            week_options = all_weeks[eligible]
            weights = np.asarray(cfg.require("design.temporal.cohort_shares"))[eligible]
            weights = weights / weights.sum()
            cohort = np.searchsorted(np.cumsum(weights), _uniform(cfg, prefix, "cohort", rep_id, size), side="right")
            weeks = week_options[cohort]
            split[:] = "test"
        else:
            cohort = _balanced_labels(
                size,
                tuple(cfg.require("design.temporal.cohort_shares")),
                child_rng(seed, f"{prefix}.covariates.cohort", rep_id),
            )
            weeks = all_weeks[cohort]
            for name in ("train", "validation", "test"):
                split[np.isin(weeks, cfg.require(f"design.temporal.{name}_weeks"))] = name
        composition = str(cfg.require("dgp.l2.composition"))
        schedule = cfg.section(f"dgp.l2.composition_schedule.{composition}")
        for name in ("train", "validation", "test"):
            mask = split == name
            new_share[mask] = schedule[f"{name}_new_share"]
            channel_probs[mask] = [schedule[f"{name}_channels"][channel] for channel in channel_names]
    elif population_kind == "validation":
        split[:] = "test"
    if np.any(channel_probs < 0) or not np.allclose(channel_probs.sum(axis=1), 1):
        raise ConfigError("Invalid channel probability vector")
    is_new = (_uniform(cfg, prefix, "is_new", rep_id, size) < new_share).astype(np.int8)
    hist = np.empty(size)
    for status, label in ((0, "returning"), (1, "new")):
        mean = float(cfg.require(f"business.hist_gmv.{label}_mean"))
        sd = float(cfg.require(f"business.hist_gmv.{label}_sd"))
        values = child_rng(seed, f"{prefix}.covariates.hist_gmv_{label}", rep_id).gamma((mean / sd) ** 2, sd ** 2 / mean, size)
        mask = is_new == status
        hist[mask] = values[mask]
    mean = float(cfg.require("business.cart_value.mean_before_floor"))
    sd = float(cfg.require("business.cart_value.sd_before_floor"))
    cart = child_rng(seed, f"{prefix}.covariates.cart", rep_id).gamma((mean / sd) ** 2, sd ** 2 / mean, size)
    cart = np.maximum(cart, float(cfg.require("business.cart_value.minimum")))
    cents = int(cfg.require("business.money.cents_per_yuan"))
    cart_cent = np.floor(cart * cents).astype(np.int64)
    # All mechanisms consume precisely these recorded, cent-valued covariates.
    hist = np.floor(hist * cents) / cents
    depth_mean = float(cfg.require("business.browse_depth.mean"))
    depth_var = float(cfg.require("business.browse_depth.variance"))
    if depth_var <= depth_mean:
        raise ConfigError("Negative-binomial variance must exceed its mean")
    depth = child_rng(seed, f"{prefix}.covariates.browse", rep_id).negative_binomial(
        depth_mean ** 2 / (depth_var - depth_mean), depth_mean / depth_var, size,
    )
    channel_q = _uniform(cfg, prefix, "channel", rep_id, size)
    channel_index = (channel_q[:, None] >= np.cumsum(channel_probs, axis=1)).sum(axis=1)
    channels = np.asarray(channel_names, dtype=object)[channel_index]
    day_bounds = cfg.require("design.temporal.assignment_day_within_week_uniform")
    within_day = float(day_bounds[0]) + _uniform(cfg, prefix, "assignment_day", rep_id, size) * (float(day_bounds[1]) - float(day_bounds[0]))
    days = (weeks - 1) * int(cfg.require("design.temporal.days_per_week")) + within_day
    ids = np.arange(1, size + 1, dtype=np.int64)
    if population_kind == "validation":
        ids = -ids
    users = pd.DataFrame({
        "user_id": ids, "is_new": is_new, "hist_gmv": hist,
        "cart_value_cent": cart_cent, "cart_value": cart_cent / cents,
        "browse_depth": depth, "channel": channels, "assignment_week": weeks,
        "assignment_day": days, "assignment_elapsed_days": days, "split": split,
    })
    u = standardized_u(_uniform(cfg, prefix, "audit_u", rep_id, size), str(cfg.require("dgp.l3.u_distribution")))
    return CovariateBatch(users, u, prefix)
