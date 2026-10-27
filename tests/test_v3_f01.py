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
    aligned = truth.set_index("user_id").reindex(
        pd.Index([1, 2, 3, 4], name="user_id")
    ).reset_index()
    assert greedy["audit_truth_sha256"] == f01.truth_frame_sha256(aligned)
    pd.testing.assert_frame_equal(selection, selection_before)
    pd.testing.assert_frame_equal(policy_frame, policy_before)

    # 定向分解恒等式：增量差 = 覆盖效应 + 单位人群效应。
    targeting = f01.targeting_decomposition_table(table, n_users=4)
    row = targeting.loc[
        (targeting["policy"] == f01.PRIMARY_POLICY)
        & (targeting["baseline"] == "random_same_budget")
    ].iloc[0]
    assert row["audit_coverage_effect"] == pytest.approx(0.0)
    assert row["audit_per_user_effect"] == pytest.approx(-0.25)
    assert row["audit_difference"] == pytest.approx(-0.25)
    assert row["audit_coverage_effect"] + row["audit_per_user_effect"] == pytest.approx(
        row["audit_difference"]
    )
    assert row["audit_coverage_share"] == pytest.approx(0.0)
    assert row["audit_per_user_share"] == pytest.approx(1.0)
    # 基线 zero-coverage 时覆盖项按 0 处理，全部增量归单位效应。
    zero_base = targeting.loc[
        (targeting["policy"] == f01.PRIMARY_POLICY)
        & (targeting["baseline"] == "no_coupon")
    ].iloc[0]
    assert zero_base["audit_coverage_effect"] == pytest.approx(0.0)
    assert zero_base["audit_per_user_effect"] == pytest.approx(0.25)
    assert zero_base["audit_difference"] == pytest.approx(0.25)
    assert np.isnan(zero_base["audit_mean_tau_baseline"])


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
    with pytest.raises(ValueError, match="manifest"):
        f01.require_truth_frame(
            truth, truth["user_id"].to_numpy(), freeze_id="b" * 64,
            manifest={"freeze_id": "c" * 64},
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
        # ESS 必须按臂内人数归一：任何启用的臂，占比都不能超过 1。
        if masks[name].sum() > 0:
            assert 0.0 < gate["ess_fraction_treated"] <= 1.0 + 1e-12
        if masks[name].sum() < len(masks[name]):
            assert 0.0 < gate["ess_fraction_control"] <= 1.0 + 1e-12

    assert tuple(bundle.increment_table.columns) == f01.INCREMENT_TABLE_COLUMNS
    dr_increment = bundle.increment_table.loc[
        np.isclose(bundle.increment_table["per_user_budget_cny"], 0.2)
        & (bundle.increment_table["estimator"] == "dr_increment")
    ].set_index("policy")
    baseline_value = float(
        bundle.value_table.loc[
            np.isclose(bundle.value_table["per_user_budget_cny"], 0.2)
            & (bundle.value_table["estimator"] == "dr_increment")
            & (bundle.value_table["policy"] == "no_coupon"),
            "value_cny_per_user",
        ].iloc[0]
    )
    for name in f01.CANDIDATE_POLICIES:
        reference_value = float(
            bundle.value_table.loc[
                np.isclose(bundle.value_table["per_user_budget_cny"], 0.2)
                & (bundle.value_table["estimator"] == "dr_increment")
                & (bundle.value_table["policy"] == name),
                "value_cny_per_user",
            ].iloc[0]
        )
        assert dr_increment.loc[name, "increment_cny_per_user"] == pytest.approx(
            reference_value - baseline_value, abs=1e-12
        )
    assert dr_increment.loc["no_coupon", "increment_cny_per_user"] == pytest.approx(0.0)

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
        if row.comparison == "policy_vs_no_coupon" and row.name != "no_coupon":
            assert np.isfinite(row.ope_se_cny_per_user)
            assert row.ope_z == pytest.approx(
                row.ope_value_cny_per_user / row.ope_se_cny_per_user
            )
    contrast_row = recon.loc[
        (recon["comparison"] == "contrast")
        & (recon["name"] == "selected_targeted_minus_no_coupon")
    ].iloc[0]
    assert bool(contrast_row["sign_agrees"]) is True
    family_row = bundle.family.set_index("contrast").loc[
        "selected_targeted_minus_no_coupon"
    ]
    assert contrast_row["ope_one_sided_p_value"] == pytest.approx(
        family_row["one_sided_p_value"], abs=1e-12
    )


def test_random_policy_distribution_reproduces_frozen_arm_and_is_deterministic() -> None:
    selection, inputs, truth = _fixture(n=600, seed=21)
    cfg = load_v3_protocol().config
    policy_frame, _ = f01.build_policies(selection, cfg, budget_per_user=0.2, seed_index=3)
    observed, features = _observed(selection, inputs)
    bundle = f01.ope_bundle(observed, features, {0.2: policy_frame}, cfg, seed_index=3)
    freeze_id = "d" * 64
    calls = dict(
        freeze_id=freeze_id, seed_index=3, n_seeds=20, seed_offset=0,
    )
    per_seed_a, summary_a = f01.random_policy_distribution(
        bundle, observed, selection, {0.2: policy_frame}, truth, cfg, **calls
    )
    per_seed_b, summary_b = f01.random_policy_distribution(
        bundle, observed, selection, {0.2: policy_frame}, truth, cfg, **calls
    )
    pd.testing.assert_frame_equal(per_seed_a, per_seed_b)
    pd.testing.assert_frame_equal(summary_a, summary_b)
    assert tuple(per_seed_a.columns) == f01.RANDOM_DIST_COLUMNS
    assert tuple(summary_a.columns) == f01.RANDOM_DIST_SUMMARY_COLUMNS
    assert len(per_seed_a) == 20
    assert len(summary_a) == 2

    audit = f01.truth_audit_table(
        selection, {0.2: policy_frame}, truth, freeze_id=freeze_id
    )
    audit_rows = audit.loc[
        np.isclose(audit["per_user_budget_cny"], 0.2)
    ].set_index("policy")
    frozen = per_seed_a.loc[per_seed_a["seed"] == 3].iloc[0]
    assert frozen["audit_n_selected"] == audit_rows.loc[
        "random_same_budget", "audit_n_selected"
    ]
    assert frozen["audit_increment"] == pytest.approx(
        audit_rows.loc[
            "random_same_budget", "audit_increment_vs_no_coupon_cny_per_user"
        ],
        abs=1e-12,
    )
    assert frozen["audit_actual_spend"] == pytest.approx(
        audit_rows.loc["random_same_budget", "audit_actual_spend_cny"], abs=1e-9
    )

    audit_summary = summary_a.set_index("estimator").loc["audit"]
    assert audit_summary["frozen_seed_index"] == 3
    assert audit_summary["frozen_seed_value"] == pytest.approx(
        frozen["audit_increment"], abs=1e-12
    )
    assert audit_summary["targeted_value"] == pytest.approx(
        audit_rows.loc[
            f01.PRIMARY_POLICY, "audit_increment_vs_no_coupon_cny_per_user"
        ],
        abs=1e-12,
    )
    assert 0.0 <= audit_summary["frozen_seed_rank_low"] <= 1.0
    assert 0 <= audit_summary["n_random_at_least_targeted"] <= 20
    assert audit_summary["targeted_minus_mean"] == pytest.approx(
        audit_summary["targeted_value"] - audit_summary["mean"]
    )
    assert np.isfinite(audit_summary["equal_spend_slope"])
    # 斜率标准误必须能用逐种子支出行独立复算，否则"等支出参照"无法判断是否只是噪声。
    assert np.isfinite(audit_summary["equal_spend_slope_se"])
    assert audit_summary["equal_spend_slope_se"] > 0.0
    assert audit_summary["equal_spend_slope_t"] == pytest.approx(
        audit_summary["equal_spend_slope"] / audit_summary["equal_spend_slope_se"],
        rel=1e-12,
    )
    spends = per_seed_a["audit_actual_spend"].to_numpy(dtype=float)
    values = per_seed_a["audit_increment"].to_numpy(dtype=float)
    ref_slope, ref_intercept = np.polyfit(spends, values, 1)
    ref_ss_res = float(np.sum((values - (ref_intercept + ref_slope * spends)) ** 2))
    ref_sxx = float(np.sum((spends - spends.mean()) ** 2))
    ref_se = float(np.sqrt(ref_ss_res / (spends.size - 2) / ref_sxx))
    assert audit_summary["equal_spend_slope"] == pytest.approx(ref_slope, rel=1e-12)
    assert audit_summary["equal_spend_slope_se"] == pytest.approx(ref_se, rel=1e-10)
    target_spend = float(audit_summary["equal_spend_target"])
    assert bool(
        audit_summary["equal_spend_target_within_random_spend_range"]
    ) == (spends.min() <= target_spend <= spends.max())
    dr_summary = summary_a.set_index("estimator").loc["dr_increment"]
    assert np.isnan(dr_summary["equal_spend_slope"])
    assert np.isnan(dr_summary["equal_spend_slope_se"])
    assert np.isnan(dr_summary["equal_spend_target_within_random_spend_range"])
    assert np.isfinite(dr_summary["mean"])
    with pytest.raises(ValueError, match="不在"):
        f01.random_policy_distribution(
            bundle, observed, selection, {0.2: policy_frame}, truth, cfg,
            freeze_id=freeze_id, seed_index=99, n_seeds=20,
        )


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


def test_primary_estimator_is_registered_and_drives_family_table() -> None:
    cfg = load_v3_protocol().config
    assert f01.PRIMARY_ESTIMATOR in ope.ESTIMATORS
    rows = []
    for contrast in f01.FAMILY_CONTRASTS:
        policy, baseline = f01.FAMILY_CONTRASTS[contrast]
        rows.append({
            "contrast": contrast,
            "policy": policy,
            "baseline": baseline,
            "estimator": f01.PRIMARY_ESTIMATOR,
            "diff_cny_per_user": 2.0,
            "se_diff": 0.5,
            "ci_low": 1.0,
            "ci_high": 3.0,
            "one_sided_p_value": 0.01,
            "n": 1000,
        })
    table = f01.family_table(pd.DataFrame(rows), cfg)
    assert set(table["estimator"]) == {f01.PRIMARY_ESTIMATOR}
    other = pd.DataFrame(rows).assign(estimator="ipw_increment")
    with pytest.raises(ValueError, match="DR 行应恰为 1"):
        f01.family_table(other, cfg)


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
