"""F01 OPE 口径测试：估计量公式、配对协方差、可靠性门禁与真值隔离。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth.evaluation import v3_ope as ope
from causal_growth.v3_config import load_v3_protocol


def _fixture(n: int = 4000, seed: int = 11):
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    treatment = rng.binomial(1, 0.5, size=n)
    y0 = 0.2 + 0.5 * x1 + rng.normal(scale=0.5, size=n)
    y1 = y0 + 1.0 + 0.3 * x1
    cost1 = 2.0 + 0.2 * x2
    refund1 = rng.binomial(1, 0.10, size=n)
    refund0 = rng.binomial(1, 0.08, size=n)
    frame = pd.DataFrame({
        "user_id": np.arange(n),
        "treatment": treatment,
        "net_profit": np.where(treatment == 1, y1, y0),
        "coupon_cost": np.where(treatment == 1, cost1, 0.0),
        "any_refund_30d": np.where(treatment == 1, refund1, refund0),
        "design_probability": 0.5,
        "x1": x1,
        "x2": x2,
    })
    truth = {
        "y1": y1, "y0": y0, "cost1": cost1,
        "refund1": refund1, "refund0": refund0,
    }
    return frame, truth


def _policies(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    x1 = frame["x1"].to_numpy()
    return {
        "treat_all": np.ones(len(frame)),
        "treat_none": np.zeros(len(frame)),
        "treat_x1_positive": (x1 > 0).astype(float),
    }


def _true_value(policy: np.ndarray, truth: dict) -> float:
    return float(np.mean(
        policy * truth["y1"] + (1.0 - policy) * truth["y0"]
    ))


def test_snips_matches_hand_computed_formula() -> None:
    pi = np.array([1, 0, 1, 0], dtype=float)
    y = np.array([2.0, 1.0, 3.0, 4.0])
    t = np.array([1, 0, 0, 1], dtype=float)
    e = np.full(4, 0.5)
    w1 = pi * t / e
    w0 = (1 - pi) * (1 - t) / (1 - e)
    r1 = (w1 * y).sum() / w1.sum()
    r0 = (w0 * y).sum() / w0.sum()
    expected = 0.5 * r1 + 0.5 * r0
    value, influence = ope.policy_value_snips(pi, y, t, e)
    assert np.isclose(value, expected)
    assert np.isclose(influence.mean(), 0.0, atol=1e-12)


def test_snips_degenerates_to_single_arm_for_no_coupon_and_all_coupon() -> None:
    rng = np.random.default_rng(3)
    y = rng.normal(size=500)
    t = rng.binomial(1, 0.5, size=500).astype(float)
    e = np.full(500, 0.5)
    for pi in (np.zeros(500), np.ones(500)):
        value, influence = ope.policy_value_snips(pi, y, t, e)
        assert np.isfinite(value)
        assert np.isfinite(influence).all()


def test_ipw_dr_snips_recover_known_policy_values() -> None:
    frame, truth = _fixture()
    policies = _policies(frame)
    cfg = load_v3_protocol().config
    table, _, nuisance, gates = ope.evaluate_policies(
        frame, policies, cfg,
        features=frame[["x1", "x2"]].to_numpy(),
        propensity_source="known_design",
        design_probability=frame["design_probability"].to_numpy(),
    )
    assert nuisance.propensity_source == "known_design"
    assert set(table["estimator"]) == set(ope.ESTIMATORS)
    assert set(table["policy"]) == set(policies)
    for name, pi in policies.items():
        true_value = _true_value(pi, truth)
        block = table.loc[table["policy"] == name]
        for _, row in block.iterrows():
            assert abs(row["value_cny_per_user"] - true_value) < 0.08, (
                name, row["estimator"], row["value_cny_per_user"], true_value
            )
            assert row["se_cny_per_user"] > 0
        assert gates[name]["passed"], gates[name]


def test_no_coupon_gate_does_not_require_treated_arm() -> None:
    frame, _ = _fixture(n=1000)
    cfg = load_v3_protocol().config
    gate = ope.reliability_gate(
        np.zeros(len(frame)), frame["treatment"].to_numpy(),
        frame["design_probability"].to_numpy(), cfg,
    )
    assert gate["passed"], gate["reasons"]


def test_reliability_gate_rejects_low_ess_and_support_violation() -> None:
    cfg = load_v3_protocol().config
    n = 1000
    treatment = np.tile([1.0, 0.0], n // 2)
    pi = np.zeros(n)
    pi[:10] = 1.0
    propensity = np.full(n, 0.5)
    propensity[:10] = 0.02
    gate = ope.reliability_gate(pi, treatment, propensity, cfg)
    assert not gate["passed"]
    assert any("ESS" in reason for reason in gate["reasons"])

    support = np.full(n, 0.5)
    support[:30] = 0.005
    gate = ope.reliability_gate(np.ones(n), treatment, support, cfg)
    assert not gate["passed"]
    assert any("支持违规" in reason for reason in gate["reasons"])


def test_paired_difference_uses_covariance_not_independent_se() -> None:
    rng = np.random.default_rng(5)
    n = 5000
    y = rng.normal(size=n)
    t = rng.binomial(1, 0.5, size=n).astype(float)
    e = np.full(n, 0.5)
    pi_a = (rng.normal(size=n) > 0).astype(float)
    pi_b = (rng.normal(size=n) > 0.2).astype(float)
    va, if_a = ope.policy_value_ipw(pi_a, y, t, e)
    vb, if_b = ope.policy_value_ipw(pi_b, y, t, e)
    se_paired = (if_a - if_b).std(ddof=1) / np.sqrt(n)
    se_independent = np.sqrt(
        if_a.var(ddof=1) / n + if_b.var(ddof=1) / n
    )
    assert not np.isclose(se_paired, se_independent)

    frame = pd.DataFrame({
        "user_id": np.arange(n),
        "treatment": t,
        "net_profit": y,
        "coupon_cost": np.where(t == 1, 1.0, 0.0),
        "any_refund_30d": np.zeros(n),
        "design_probability": 0.5,
        "x": rng.normal(size=n),
    })
    policies = {"a": pi_a, "b": pi_b}
    table, _, _ = ope.paired_policy_differences(
        frame, policies, "b", load_v3_protocol().config,
        features=frame[["x"]].to_numpy(),
        propensity_source="known_design",
        design_probability=frame["design_probability"].to_numpy(),
    )
    row = table.loc[(table["policy"] == "a") & (table["estimator"] == "ipw_increment")].iloc[0]
    assert np.isclose(row["diff_cny_per_user"], va - vb)
    assert np.isclose(row["se_diff"], se_paired)


def test_cost_and_guardrail_recover_known_components() -> None:
    frame, truth = _fixture(n=6000)
    policies = _policies(frame)
    table = ope.cost_and_guardrail(
        frame, policies, load_v3_protocol().config,
        features=frame[["x1", "x2"]].to_numpy(),
        propensity_source="known_design",
        design_probability=frame["design_probability"].to_numpy(),
    )
    for name, pi in policies.items():
        true_cost = float(np.mean(pi * truth["cost1"]))
        true_refund = float(np.mean(
            pi * truth["refund1"] + (1 - pi) * truth["refund0"]
        ))
        cost = table.loc[
            (table["policy"] == name)
            & (table["component"] == "coupon_cost_total_per_assigned_user")
        ].iloc[0]
        refund = table.loc[
            (table["policy"] == name) & (table["component"] == "refund_rate_30d")
        ].iloc[0]
        assert abs(cost["value"] - true_cost) < 0.08
        assert abs(refund["value"] - true_refund) < 0.03


def test_observed_frame_rejects_truth_columns_but_accepts_actual_action() -> None:
    frame, _ = _fixture(n=200)
    ope.require_observed_frame(frame.assign(actual_action=frame["treatment"]))
    with pytest.raises(ValueError, match="真值"):
        ope.require_observed_frame(frame.assign(tau_true=1.0))
    with pytest.raises(ValueError, match="真值"):
        ope.require_observed_frame(frame.assign(audit_u=1.0))


def test_holm_step_down_adjusts_thresholds() -> None:
    result = ope.holm_step_down({"a": 0.01, "b": 0.04, "c": 0.03}, alpha=0.05)
    assert result["a"]["rejected"]
    assert result["a"]["adjusted_alpha"] == pytest.approx(0.05 / 3)
    assert not result["c"]["rejected"]
    assert not result["b"]["rejected"]
    assert result["a"]["adjusted_p_value"] == pytest.approx(0.03)
