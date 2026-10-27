"""F01 冻结、OPE 表与冻结后真值审计的口径测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth.evaluation import v3_f01 as f01
from causal_growth.evaluation import v3_ope as ope
from causal_growth.v3_config import load_v3_protocol


def _fixture(n: int = 2000, seed: int = 17):
    rng = np.random.default_rng(seed)
    ids = np.arange(1000, 1000 + n)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    treatment = rng.binomial(1, 0.5, size=n)
    tau = 0.5 + 0.8 * (x1 > 0).astype(float)
    y0 = 0.2 + 0.4 * x1 + rng.normal(scale=0.5, size=n)
    y1 = y0 + tau
    cost1 = 2.0 + 0.5 * (x2 > 0).astype(float)
    refund1 = rng.binomial(1, 0.10, size=n).astype(float)
    refund0 = rng.binomial(1, 0.08, size=n).astype(float)
    selection = pd.DataFrame({
        "user_id": ids,
        "is_new": rng.binomial(1, 0.3, size=n),
        "cart_value": np.maximum(rng.normal(50.0, 20.0, size=n), 0.0),
        "purchase_propensity": np.clip(0.5 + 0.1 * x1, 0.0, 1.0),
        "predicted_profit": np.maximum(1.0 + 0.5 * x1, 0.0),
        "tau_hat": tau + rng.normal(scale=0.05, size=n),
        "cost_hat": np.maximum(cost1 + rng.normal(scale=0.05, size=n), 1e-3),
    })
    order = rng.permutation(n)
    observed_inputs = {
        "user_id": ids[order],
        "treatment": treatment[order],
        "net_profit": np.where(treatment == 1, y1, y0)[order],
        "coupon_cost": np.where(treatment == 1, cost1, 0.0)[order],
        "any_refund_30d": np.where(treatment == 1, refund1, refund0)[order],
        "design_probability": np.full(n, 0.5)[order],
        "features": np.column_stack([x1, x2])[order],
    }
    truth = pd.DataFrame({
        "user_id": ids,
        "tau_true": tau,
        "cost_true": cost1,
    })
    return selection, observed_inputs, truth


def _observed(selection, inputs):
    return f01.build_observed_frame(
        **{key: value for key, value in inputs.items() if key != "features"},
        features=inputs["features"],
    )


def _policy_masks(policy_frame, user_id):
    aligned = policy_frame.set_index("user_id").reindex(pd.Index(user_id))
    return {name: aligned[name].to_numpy(dtype=float) for name in f01.CANDIDATE_POLICIES}


def test_build_observed_frame_reorders_features_with_user_id() -> None:
    selection, inputs, _ = _fixture(n=50, seed=3)
    frame, features = _observed(selection, inputs)
    assert frame["user_id"].is_monotonic_increasing
    assert frame["user_id"].is_unique
    lookup = {
        int(uid): (x1, x2)
        for uid, x1, x2 in zip(
            inputs["user_id"], inputs["features"][:, 0], inputs["features"][:, 1]
        )
    }
    for row, (x1, x2) in zip(frame.itertuples(), features):
        expected = lookup[int(row.user_id)]
        assert (x1, x2) == pytest.approx(expected)


def test_build_policies_is_order_stable_and_budget_feasible() -> None:
    selection, _, _ = _fixture()
    cfg = load_v3_protocol().config
    frame_a, meta_a = f01.build_policies(selection, cfg, budget_per_user=0.2, seed_index=4)
    shuffled = selection.sample(frac=1.0, random_state=9).reset_index(drop=True)
    frame_b, meta_b = f01.build_policies(shuffled, cfg, budget_per_user=0.2, seed_index=4)
    pd.testing.assert_frame_equal(frame_a, frame_b)
    pd.testing.assert_frame_equal(meta_a, meta_b)
    assert (frame_a["no_coupon"].to_numpy() == 0).all()
    for row in meta_a.itertuples():
        assert row.predicted_cost <= row.budget_cny + 1e-9
        assert row.n_selected == int(frame_a[row.policy].sum())


def test_freeze_manifest_detects_mask_design_and_id_tampering() -> None:
    selection, inputs, _ = _fixture(n=400, seed=5)
    cfg = load_v3_protocol().config
    policy_frame, _ = f01.build_policies(selection, cfg, budget_per_user=0.2, seed_index=0)
    design = pd.Series(
        inputs["design_probability"], index=pd.Index(inputs["user_id"])
    )
    kwargs = dict(
        scenario="L1_main",
        n_dgp=400,
        n_users=400,
        rep_id=0,
        chosen_model="constant",
        config_hash=cfg.hash(64),
        source_hashes={"a": "b"},
    )
    manifest = f01.build_freeze_manifest(
        selection, {0.2: policy_frame}, design, created_at="2026-10-27 20:00", **kwargs
    )
    freeze_id = f01.verify_freeze_manifest(
        manifest, selection, {0.2: policy_frame}, design, **kwargs
    )
    assert freeze_id == manifest["freeze_id"]
    assert np.isclose(manifest["budgets"]["0.2"]["budget_cny"], 80.0)

    tampered = policy_frame.copy()
    column = "greedy_incremental_profit_per_cost"
    index = int(np.flatnonzero(tampered[column].to_numpy() == 0)[0])
    tampered.loc[index, column] = 1 - tampered.loc[index, column]
    with pytest.raises(ValueError, match="budgets"):
        f01.verify_freeze_manifest(
            manifest, selection, {0.2: tampered}, design, **kwargs
        )

    changed_design = design.copy()
    changed_design.iloc[0] = 0.6
    with pytest.raises(ValueError, match="design_probability_sha256"):
        f01.verify_freeze_manifest(
            manifest, selection, {0.2: policy_frame}, changed_design, **kwargs
        )

    with pytest.raises(ValueError, match="freeze_id"):
        f01.verify_freeze_manifest(
            {**manifest, "freeze_id": "0" * 64},
            selection, {0.2: policy_frame}, design, **kwargs,
        )

    with pytest.raises(ValueError, match="created_at"):
        f01.verify_freeze_manifest(
            {**manifest, "created_at": ""},
            selection, {0.2: policy_frame}, design, **kwargs,
        )


def test_freeze_manifest_created_at_does_not_change_id() -> None:
    selection, inputs, _ = _fixture(n=200, seed=6)
    cfg = load_v3_protocol().config
    policy_frame, _ = f01.build_policies(selection, cfg, budget_per_user=0.2, seed_index=0)
    design = pd.Series(inputs["design_probability"], index=pd.Index(inputs["user_id"]))
    kwargs = dict(
        scenario="L1_main", n_dgp=200, n_users=200, rep_id=0, chosen_model="constant",
        config_hash=cfg.hash(64), source_hashes={"a": "b"},
    )
    first = f01.build_freeze_manifest(
        selection, {0.2: policy_frame}, design, created_at="2026-10-27 20:00", **kwargs
    )
    second = f01.build_freeze_manifest(
        selection, {0.2: policy_frame}, design, created_at="2026-10-27 20:01", **kwargs
    )
    assert first["freeze_id"] == second["freeze_id"]


def test_freeze_rejects_truth_columns() -> None:
    selection, inputs, truth = _fixture(n=100, seed=7)
    contaminated = selection.copy()
    contaminated["tau_true"] = truth["tau_true"]
    with pytest.raises(ValueError, match="真值"):
        f01.require_freeze_frame(contaminated)


def test_truth_audit_exact_and_does_not_mutate_inputs() -> None:
    selection = pd.DataFrame({
        "user_id": [3, 1, 2, 4],
        "is_new": [0, 1, 0, 1],
        "cart_value": [0.0, 1.0, 2.0, 3.0],
        "purchase_propensity": [0.5, 0.5, 0.5, 0.5],
        "predicted_profit": [0.0, 1.0, 2.0, 3.0],
        "tau_hat": [1.0, 1.0, 1.0, 1.0],
        "cost_hat": [1.0, 1.0, 1.0, 1.0],
    })
    policy_frame = pd.DataFrame({
        "user_id": [1, 2, 3, 4],
        **{name: [0, 0, 0, 0] for name in f01.CANDIDATE_POLICIES},
    })
    policy_frame.loc[0, "greedy_incremental_profit_per_cost"] = 1
    policy_frame.loc[1, "random_same_budget"] = 1
    truth = pd.DataFrame({
        "user_id": [4, 3, 2, 1],
        "tau_true": [4.0, 3.0, 2.0, 1.0],
        "cost_true": [0.4, 0.3, 0.2, 0.1],
    })
    selection_before = selection.copy()
    policy_before = policy_frame.copy()
    table = f01.truth_audit_table(
        selection, {0.2: policy_frame}, truth, freeze_id="a" * 64
    )
    assert table.columns[0] == "per_user_budget_cny"
    assert all(column.startswith("audit_") for column in table.columns[3:])
    greedy = table.loc[
        table["policy"] == "greedy_incremental_profit_per_cost"
    ].iloc[0]
    # 分母是全部 4 人，不是入选 2 人：0.2 元/人 × 4 = 0.8 元预算。
    assert greedy["audit_n_selected"] == 1
    assert greedy["audit_increment_vs_no_coupon_cny_per_user"] == pytest.approx(1.0 / 4.0)
    assert greedy["audit_actual_spend_cny"] == pytest.approx(0.1)
    assert greedy["audit_budget_cny"] == pytest.approx(0.8)
    assert bool(greedy["audit_within_budget_by_true"]) is True
    pd.testing.assert_frame_equal(selection, selection_before)
    pd.testing.assert_frame_equal(policy_frame, policy_before)


def test_require_truth_frame_rejects_mismatch_and_missing_freeze_id() -> None:
    _, _, truth = _fixture(n=20, seed=8)
    with pytest.raises(ValueError, match="freeze_id"):
        f01.require_truth_frame(truth, truth["user_id"].to_numpy(), freeze_id="short")
    wrong = truth.copy()
    wrong.loc[0, "user_id"] = -1
    with pytest.raises(ValueError, match="用户集合"):
        f01.require_truth_frame(
            wrong, truth["user_id"].to_numpy(), freeze_id="b" * 64
        )


def test_ope_bundle_matches_public_ope_and_paired_difference() -> None:
    selection, inputs, truth = _fixture(n=1500, seed=11)
    cfg = load_v3_protocol().config
    policy_frame, _ = f01.build_policies(selection, cfg, budget_per_user=0.2, seed_index=2)
    observed, features = _observed(selection, inputs)
    bundle = f01.ope_bundle(
        observed, features, {0.2: policy_frame}, cfg, seed_index=2
    )
    masks = _policy_masks(policy_frame, observed["user_id"].to_numpy())
    table, _, nuisance, gates = ope.evaluate_policies(
        observed, masks, cfg,
        features=features,
        propensity_source="known_design",
        design_probability=observed["design_probability"].to_numpy(),
        seed_index=2,
    )
    value = bundle.value_table.loc[
        np.isclose(bundle.value_table["per_user_budget_cny"], 0.2)
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        value.loc[:, list(ope.VALUE_COLUMNS)], table, check_exact=False, atol=1e-10
    )
    assert set(gates) == set(f01.CANDIDATE_POLICIES)
    for name, gate in gates.items():
        assert gate["passed"] == bundle.gates[0.2][name]["passed"]

    baseline = "no_coupon"
    diff_table, _, _ = ope.paired_policy_differences(
        observed, masks, baseline, cfg,
        features=features,
        propensity_source="known_design",
        design_probability=observed["design_probability"].to_numpy(),
        seed_index=2,
    )
    contrast_name = "selected_targeted_minus_no_coupon"
    ours = bundle.contrast_table.loc[
        (bundle.contrast_table["contrast"] == contrast_name)
        & (bundle.contrast_table["estimator"] == "dr_increment")
    ].iloc[0]
    reference = diff_table.loc[
        (diff_table["policy"] == f01.PRIMARY_POLICY)
        & (diff_table["estimator"] == "dr_increment")
    ].iloc[0]
    assert ours["diff_cny_per_user"] == pytest.approx(
        reference["diff_cny_per_user"], abs=1e-10
    )
    assert ours["se_diff"] == pytest.approx(reference["se_diff"], abs=1e-10)

    random_reference = ope.policy_value_dr(
        masks[f01.PRIMARY_POLICY],
        observed["net_profit"].to_numpy(dtype=float),
        observed["treatment"].to_numpy(dtype=float),
        nuisance.mu1, nuisance.mu0, nuisance.propensity,
    )[0] - ope.policy_value_dr(
        masks["random_same_budget"],
        observed["net_profit"].to_numpy(dtype=float),
        observed["treatment"].to_numpy(dtype=float),
        nuisance.mu1, nuisance.mu0, nuisance.propensity,
    )[0]
    random_row = bundle.contrast_table.loc[
        (bundle.contrast_table["contrast"]
         == "selected_targeted_minus_same_budget_random")
        & (bundle.contrast_table["estimator"] == "dr_increment")
    ].iloc[0]
    assert random_row["diff_cny_per_user"] == pytest.approx(random_reference, abs=1e-10)

    audit = f01.truth_audit_table(
        selection, {0.2: policy_frame}, truth, freeze_id="c" * 64
    )
    recon = f01.ope_vs_audit_table(bundle, audit, cfg)
    assert len(recon) == len(f01.CANDIDATE_POLICIES) + len(f01.FAMILY_CONTRASTS)
    for row in recon.itertuples():
        assert row.value_error_cny_per_user == pytest.approx(
            row.ope_value_cny_per_user - row.audit_value_cny_per_user
        )
    contrast_row = recon.loc[
        (recon["comparison"] == "contrast")
        & (recon["name"] == "selected_targeted_minus_no_coupon")
    ].iloc[0]
    assert bool(contrast_row["sign_agrees"]) is True


def test_family_table_holm_thresholds_and_adjusted_lower_bound() -> None:
    cfg = load_v3_protocol().config
    rows = []
    for contrast, p_value in (
        ("selected_targeted_minus_no_coupon", 0.01),
        ("selected_targeted_minus_same_budget_random", 0.06),
    ):
        policy, baseline = f01.FAMILY_CONTRASTS[contrast]
        rows.append({
            "contrast": contrast,
            "policy": policy,
            "baseline": baseline,
            "estimator": "dr_increment",
            "diff_cny_per_user": 2.0,
            "se_diff": 0.5,
            "ci_low": 1.0,
            "ci_high": 3.0,
            "one_sided_p_value": p_value,
            "n": 1000,
        })
    table = f01.family_table(pd.DataFrame(rows), cfg).set_index("contrast")
    first = table.loc["selected_targeted_minus_no_coupon"]
    second = table.loc["selected_targeted_minus_same_budget_random"]
    assert first["adjusted_alpha"] == pytest.approx(0.025)
    assert first["holm_adjusted_p_value"] == pytest.approx(0.02)
    assert first["holm_alpha"] == pytest.approx(0.05)
    assert bool(first["holm_rejected"]) is True
    assert first["holm_lower_bound_cny_per_user"] == pytest.approx(
        2.0 - 1.959963984540054 * 0.5, rel=1e-12
    )
    assert first["holm_confidence_level"] == pytest.approx(0.975)
    assert second["adjusted_alpha"] == pytest.approx(0.05)
    assert second["holm_adjusted_p_value"] == pytest.approx(0.06)
    assert bool(second["holm_rejected"]) is False
    assert np.isnan(second["holm_lower_bound_cny_per_user"])
    # 逐步拒绝与“累计调整 p ≤ 总体 α”必须等价，否则展示口径会自相矛盾。
    for _, row in table.iterrows():
        assert bool(row["holm_rejected"]) == (
            row["holm_adjusted_p_value"] <= row["holm_alpha"]
        )


def test_ope_bundle_rejects_unsorted_frame_and_missing_primary_budget() -> None:
    selection, inputs, _ = _fixture(n=200, seed=12)
    cfg = load_v3_protocol().config
    policy_frame, _ = f01.build_policies(selection, cfg, budget_per_user=0.2, seed_index=0)
    observed, features = _observed(selection, inputs)
    shuffled = observed.sample(frac=1.0, random_state=4).reset_index(drop=True)
    with pytest.raises(ValueError, match="user_id 升序"):
        f01.ope_bundle(shuffled, features, {0.2: policy_frame}, cfg)
    with pytest.raises(ValueError, match="主预算"):
        f01.ope_bundle(observed, features, {0.1: policy_frame}, cfg)
