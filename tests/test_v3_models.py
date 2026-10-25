"""合成数据 / 已知 DGP：D.3 统一学习接口的口径、边界与 DR 数学。

测试纪律
--------
- 只验证**接口与估计器**；不把任何真值列喂进学习路径。合成样本的真值只出现在
  "估计器是否把已知 ATE 估对"的断言里，由测试自己生成，不来自 DGP/audit 产物。
- 数据链路走 ``run_sql_pipeline``（生产 SQL 与拆分规则不变），**不走**
  ``build_observed_pipeline``：后者的"源码前后哈希"门禁会在多代理并发写
  ``v3*.py`` 时假红，而全链路本身已由 ``tests/test_v3_pipeline.py`` 覆盖。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from causal_growth.config import Config, ConfigError
from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_preprocessing import fit_preprocessor
from causal_growth.data.v3_sql import run_sql_pipeline
from causal_growth.data.v3_split import user_key_hash
from causal_growth.data.v3_tables import build_raw_tables
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.estimate import v3_models as models
from causal_growth.rng import child_rng
from causal_growth.v3_config import V3Protocol, load_v3_protocol

ROOT = Path(__file__).resolve().parents[1]
SMOKE_CSV = ROOT / "outputs" / "tables" / "v3_phase_D_models_smoke.csv"
SCENARIOS = {
    "L0": "L0_P_main",
    "L1": "L1_main",
    "L2": "L2_n200000_p050",
    "L3": "L3_fixed_lt000",
}


# --------------------------------------------------------------------------- #
# 观测数据：生产 SQL 链路，不经全链路 manifest 与源码哈希门禁
# --------------------------------------------------------------------------- #
def _observed(scenario: str, n: int) -> tuple[Config, ObservedDataset, dict[str, Any]]:
    cfg = load_v3_protocol().scenario(scenario)
    population = generate_v3_population(cfg, n=n)
    users, assignments, orders = population.observation_bundle()
    stream = f"test.v3.models.{scenario}"
    raw = build_raw_tables(
        users, assignments, orders, cfg,
        run_id=f"test:{scenario}", rep_id=0, stream_prefix=stream,
    )
    dirty = inject_dirt(raw, cfg, rep_id=0, stream_prefix=stream)
    clean = deduplicate_events(dirty.tables, cfg)
    raw_dataset = ObservedDataset.from_sql_result(run_sql_pipeline(raw, cfg), cfg)
    split_dataset, split_manifest = raw_dataset.assign_splits(
        cfg, stream=f"{stream}.split", index=0
    )
    labels = split_dataset.observations.set_index(["run_id", "user_id"]).split
    for tables in (raw, dirty.tables, clean.tables):
        keys = pd.MultiIndex.from_frame(tables["users"][["run_id", "user_id"]])
        tables["users"]["split"] = labels.reindex(keys).to_numpy()
    clean_sql = run_sql_pipeline(clean.tables, cfg)
    dataset = ObservedDataset.from_sql_result(clean_sql, cfg)
    return cfg, dataset, split_manifest


@pytest.fixture(scope="module")
def protocol() -> V3Protocol:
    return load_v3_protocol()


@pytest.fixture(scope="module")
def l1() -> tuple[Config, ObservedDataset, models.LearningData, dict[str, Any]]:
    cfg, dataset, split_manifest = _observed("L1_main", 1500)
    return cfg, dataset, models.prepare_learning_data(dataset, cfg), split_manifest


@pytest.fixture(scope="module")
def l3() -> tuple[Config, ObservedDataset, models.LearningData, dict[str, Any]]:
    cfg, dataset, split_manifest = _observed("L3_fixed_lt000", 800)
    return cfg, dataset, models.prepare_learning_data(dataset, cfg), split_manifest


@pytest.fixture(scope="module")
def l1_predictions(l1) -> dict[str, models.Predictions]:
    cfg, _dataset, data, _manifest = l1
    return {name: models.fit_predict(name, data, cfg) for name in models.MODEL_NAMES}


@pytest.fixture(scope="module")
def l3_predictions(l3) -> dict[str, models.Predictions]:
    cfg, _dataset, data, _manifest = l3
    return {name: models.fit_predict(name, data, cfg) for name in ("constant", "dr_learner")}


@pytest.fixture(scope="module")
def l1_scorer(l1) -> models.ValidationScorer:
    cfg, _dataset, data, _manifest = l1
    return models.fit_validation_scorer(data, cfg)


# --------------------------------------------------------------------------- #
# 合成样本：只在测试侧生成，用于检验估计器数学
# --------------------------------------------------------------------------- #
def _confounded_sample(n: int = 6000) -> dict[str, np.ndarray]:
    rng = child_rng(20240101, "test.v3_models.confounded", 0)
    x = rng.normal(size=n)
    propensity = 1.0 / (1.0 + np.exp(-2.0 * x))
    treatment = (rng.random(n) < propensity).astype(int)
    y = 1.0 + 2.0 * x + treatment * (1.0 + x) + rng.normal(scale=1.0, size=n)
    return {"X": x.reshape(-1, 1), "y": y, "t": treatment, "tau": 1.0 + x}


def _heterogeneous_sample(n: int = 6000) -> dict[str, np.ndarray]:
    rng = child_rng(20240101, "test.v3_models.heterogeneous", 0)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    propensity = 1.0 / (1.0 + np.exp(-1.5 * x1))
    treatment = (rng.random(n) < propensity).astype(int)
    tau = 1.0 + 2.0 * x1
    y = 0.5 + x1 + 0.5 * x2 + treatment * tau + rng.normal(scale=1.0, size=n)
    return {"X": np.column_stack([x1, x2]), "y": y, "t": treatment, "tau": tau}


# --------------------------------------------------------------------------- #
# 特征边界：禁用列硬拒绝 + 白名单完整性
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "column",
    ["U", "true_propensity", "true_cate", "potential_profit0", "potential_purchase1",
     "potential_brand_new_metric"],
)
def test_forbidden_feature_columns_are_rejected_at_interface(l1, column: str) -> None:
    cfg, dataset, _data, _manifest = l1
    contaminated = dataset.observations.assign(**{column: 1.0})
    with pytest.raises(models.FeatureBoundaryError, match="禁用"):
        models.require_feature_boundary(contaminated, cfg)


@pytest.mark.parametrize("column", ["audit_flag", "latent_quality", "oracle_effect", "true_effect"])
def test_audit_and_latent_patterns_are_rejected_even_if_not_in_models_yaml(l1, column: str) -> None:
    cfg, dataset, _data, _manifest = l1
    contaminated = dataset.observations.assign(**{column: 1.0})
    with pytest.raises(models.FeatureBoundaryError, match="禁用"):
        models.require_feature_boundary(contaminated, cfg)


def test_feature_block_must_match_whitelist_exactly(l1) -> None:
    cfg, _dataset, data, _manifest = l1
    with pytest.raises(models.FeatureBoundaryError, match="白名单"):
        models.require_whitelisted_feature_names((*data.feature_names, "net_profit"), cfg)
    with pytest.raises(models.FeatureBoundaryError, match="白名单"):
        models.require_whitelisted_feature_names(data.feature_names[:-1], cfg)
    with pytest.raises(models.FeatureBoundaryError, match="禁用"):
        models.require_whitelisted_feature_names(("is_new", "true_cate"), cfg)


def test_allowed_feature_names_equal_fitted_preprocessor(l1) -> None:
    cfg, _dataset, data, _manifest = l1
    assert set(models.allowed_feature_names(cfg)) == set(data.feature_names)
    assert "channel" in cfg.require("models.feature_whitelist")


def test_fit_predict_runs_frame_boundary_gate_and_propagates_failure(l1, monkeypatch) -> None:
    cfg, dataset, _data, _manifest = l1
    original = models.require_feature_boundary
    calls: list[str] = []

    def spy(frame_or_names, config, time_mode="static"):
        calls.append(type(frame_or_names).__name__)
        return original(frame_or_names, config, time_mode)

    monkeypatch.setattr(models, "require_feature_boundary", spy)
    models.fit_predict("constant", dataset, cfg)
    assert calls == ["DataFrame"]

    def refuse(*_args, **_kwargs):
        raise models.FeatureBoundaryError("禁用特征列")

    monkeypatch.setattr(models, "require_feature_boundary", refuse)
    with pytest.raises(models.FeatureBoundaryError, match="禁用"):
        models.fit_predict("constant", dataset, cfg)


# --------------------------------------------------------------------------- #
# 数据准备：拆分完整性、配置绑定、配对证据
# --------------------------------------------------------------------------- #
def test_prepare_requires_observed_dataset(l1) -> None:
    cfg, _dataset, _data, _manifest = l1
    with pytest.raises(TypeError, match="ObservedDataset"):
        models.prepare_learning_data(pd.DataFrame({"split": ["train"]}), cfg)


def test_prepare_rejects_missing_split_roles(l1) -> None:
    cfg, dataset, _data, _manifest = l1
    with pytest.raises(ValueError, match="不能为空"):
        models.prepare_learning_data(dataset.select_split("test"), cfg)


def test_prepare_rejects_config_mismatch(l1, protocol: V3Protocol) -> None:
    _cfg, dataset, _data, _manifest = l1
    with pytest.raises(ValueError, match="配置"):
        models.prepare_learning_data(dataset, protocol.scenario("L0_P_main"))


def test_prepare_records_pairing_evidence(l1) -> None:
    cfg, dataset, data, split_manifest = l1
    observations = dataset.observations
    train_frame = observations.loc[observations.split == "train"].reset_index(drop=True)
    assert data.preprocessor_hash == fit_preprocessor(train_frame, cfg, role="train").hash
    assert data.observed_hash == dataset.content_hash
    assert data.train.key_hash == user_key_hash(train_frame[["run_id", "user_id"]])
    assert len({data.train.key_hash, data.validation.key_hash, data.test.key_hash}) == 3
    assert data.split_fingerprint == hashlib.sha256(
        json.dumps(
            {
                "train": data.train.key_hash,
                "validation": data.validation.key_hash,
                "test": data.test.key_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert split_manifest["counts"]["train"] == data.train.n


def test_learning_data_binds_level_and_identification_mode(l1, l3) -> None:
    _cfg1, _dataset1, data1, _m1 = l1
    _cfg3, _dataset3, data3, _m3 = l3
    assert (data1.level, data1.identification_mode) == ("L1", "randomized")
    assert (data3.level, data3.identification_mode) == ("L3", "observational")
    assert data1.train.has_design_probability is True
    assert data3.train.has_design_probability is False
    assert data1.train.design_probability.min() == 0.5


# --------------------------------------------------------------------------- #
# 模型适用性与配置口径
# --------------------------------------------------------------------------- #
def test_unknown_model_name_raises(l1) -> None:
    cfg, _dataset, data, _manifest = l1
    with pytest.raises(ValueError, match="未知模型"):
        models.fit_predict("meta_learner", data, cfg)


@pytest.mark.parametrize("level", ["L0", "L2"])
def test_dr_learner_not_applicable_outside_registered_levels(l1, protocol, level) -> None:
    _cfg, _dataset, data, _manifest = l1
    cfg = protocol.scenario(SCENARIOS[level])
    with pytest.raises(models.ModelNotApplicableError, match="不适用"):
        models.fit_predict("dr_learner", data, cfg)


def test_model_applicability_mirrors_frozen_config(protocol: V3Protocol) -> None:
    additional = protocol.config.section("models.additional_by_level")
    common = {str(name) for name in protocol.config.require("models.common")}
    allowed_levels = {level for level, names in additional.items() if "dr_learner" in set(names)}
    assert allowed_levels == {"L1", "L3"}
    assert "dr_learner" not in common
    for level, scenario in SCENARIOS.items():
        cfg = protocol.scenario(scenario)
        if level in allowed_levels:
            models.require_model_applicable("dr_learner", cfg)
        else:
            with pytest.raises(models.ModelNotApplicableError):
                models.require_model_applicable("dr_learner", cfg)


def test_identification_mode_matches_sql_rule(protocol: V3Protocol) -> None:
    assert models.identification_mode(protocol.scenario("L0_P_main")) == "randomized"
    assert models.identification_mode(protocol.scenario("L1_main")) == "randomized"
    assert models.identification_mode(protocol.scenario("L2_n200000_p050")) == "randomized"
    assert models.identification_mode(protocol.scenario("L3_fixed_lt000")) == "observational"


def test_constant_source_paths_are_registered(protocol: V3Protocol) -> None:
    randomized = protocol.scenario("L1_main")
    assert models.constant_source(randomized) == "training_itt"
    assert models.constant_source(protocol.scenario("L3_fixed_lt000")) == "training_crossfit_dr_ate"
    bad_path = randomized.with_overrides({"models.constant.randomized": "mean_outcome"})
    with pytest.raises(ConfigError, match="常数模型"):
        models.constant_source(bad_path)


def test_dr_learner_spec_must_be_registered(l3) -> None:
    cfg, _dataset, data, _manifest = l3
    bad = cfg.with_overrides({"models.dr_learner.final_model": "linear_regression"})
    with pytest.raises(ConfigError, match="DR"):
        models.dr_learner_cate(
            data.train.X, data.train.y, data.train.treatment, data.train.X, bad
        )


# --------------------------------------------------------------------------- #
# 同拆分配对与预测对齐
# --------------------------------------------------------------------------- #
def test_all_models_share_the_same_split_and_preprocessor(l1, l1_predictions) -> None:
    cfg, _dataset, data, _manifest = l1
    for name, prediction in l1_predictions.items():
        info = prediction.info
        assert info["preprocessor_hash"] == data.preprocessor_hash
        assert info["config_hash"] == data.config_hash == cfg.hash(64)
        assert info["observed_hash"] == data.observed_hash
        assert info["train_user_key_hash"] == data.train.key_hash
        assert info["validation_user_key_hash"] == data.validation.key_hash
        assert info["test_user_key_hash"] == data.test.key_hash
        assert info["n_features"] == len(data.feature_names) == 12
        assert info["train_n"] == data.train.n and info["test_n"] == data.test.n
        assert info["train_cpu_seconds"] >= 0.0 and info["predict_cpu_seconds"] >= 0.0
        assert name == prediction.model_name
    assert len({p.info["test_user_key_hash"] for p in l1_predictions.values()}) == 1
    assert len({p.info["preprocessor_hash"] for p in l1_predictions.values()}) == 1


def test_predictions_align_with_test_keys(l1, l1_predictions) -> None:
    _cfg, _dataset, data, _manifest = l1
    prediction = l1_predictions["t_learner"]
    pd.testing.assert_frame_equal(prediction.test_keys.reset_index(drop=True), data.test.keys)
    assert prediction.tau_test.shape == (data.test.n,)
    assert prediction.tau_validation.shape == (data.validation.n,)
    assert np.isfinite(prediction.tau_test).all()
    assert prediction.ate == pytest.approx(float(prediction.tau_test.mean()), abs=1e-12)
    assert prediction.tau_sd_test == pytest.approx(float(np.std(prediction.tau_test, ddof=1)))


def test_fit_predict_accepts_observed_dataset_and_reuses_frozen_state(l1) -> None:
    cfg, dataset, data, _manifest = l1
    direct = models.fit_predict("constant", dataset, cfg)
    prepared = models.fit_predict("constant", data, cfg)
    assert direct.info["preprocessor_hash"] == prepared.info["preprocessor_hash"]
    assert direct.info["observed_hash"] == prepared.info["observed_hash"]
    assert direct.ate == pytest.approx(prepared.ate, abs=1e-12)


def test_fit_predict_rejects_time_mode_mismatch(l1) -> None:
    cfg, _dataset, data, _manifest = l1
    with pytest.raises(ValueError, match="时间特征模式"):
        models.fit_predict("constant", data, cfg, time_mode="time_features")


def test_fit_predict_rejects_cross_scenario_data(l1, protocol: V3Protocol) -> None:
    _cfg, _dataset, data, _manifest = l1
    with pytest.raises(ValueError, match="配置"):
        models.fit_predict("constant", data, protocol.scenario("L0_P_main"))


# --------------------------------------------------------------------------- #
# 常数模型两条口径
# --------------------------------------------------------------------------- #
def test_constant_randomized_equals_training_itt(l1, l1_predictions) -> None:
    _cfg, _dataset, data, _manifest = l1
    treated = data.train.y[data.train.treatment == 1]
    control = data.train.y[data.train.treatment == 0]
    expected = float(treated.mean() - control.mean())
    prediction = l1_predictions["constant"]
    assert prediction.info["constant_source"] == "training_itt"
    assert prediction.info["tau_constant"] == pytest.approx(expected, abs=1e-12)
    assert prediction.tau_sd_test == 0.0
    np.testing.assert_allclose(prediction.tau_test, expected, atol=1e-12)


def test_constant_observational_equals_crossfit_dr_ate(l3, l3_predictions) -> None:
    cfg, _dataset, data, _manifest = l3
    prediction = l3_predictions["constant"]
    estimate = models.crossfit_dr_ate(
        data.train.X, data.train.y, data.train.treatment, cfg
    )
    assert prediction.info["constant_source"] == "training_crossfit_dr_ate"
    assert prediction.info["tau_constant"] == pytest.approx(estimate.ate, abs=1e-9)
    assert prediction.tau_sd_test == 0.0
    assert estimate.folds == 3


def test_constant_observational_shares_nuisance_with_dr_learner(l3, l3_predictions) -> None:
    _cfg, _dataset, _data, _manifest = l3
    constant = l3_predictions["constant"]
    dr = l3_predictions["dr_learner"]
    assert constant.info["tau_constant"] == pytest.approx(dr.info["dr_ate_training"], abs=1e-9)
    assert constant.info["crossfit_folds"] == dr.info["crossfit_folds"] == 3


# --------------------------------------------------------------------------- #
# 冻结超参
# --------------------------------------------------------------------------- #
def test_causal_forest_estimator_uses_frozen_hyperparameters(protocol: V3Protocol) -> None:
    cfg = protocol.scenario("L1_main")
    spec = cfg.section("models.causal_forest")
    estimator = models.causal_forest_estimator(cfg, seed=7)
    assert (estimator.n_estimators, spec["n_estimators"]) == (300, 300)
    assert (estimator.min_samples_leaf, spec["min_samples_leaf"]) == (60, 60)
    assert estimator.max_depth is spec["max_depth"] is None
    assert (estimator.cv, spec["cv"]) == (3, 3)
    assert estimator.discrete_treatment is True
    assert estimator.inference is False
    assert estimator.n_jobs == spec["n_jobs"] == 1
    assert estimator.random_state == 7
    assert type(estimator.model_t).__name__ == "LGBMClassifier"
    assert type(estimator.model_y).__name__ == "LGBMRegressor"


def test_causal_forest_info_records_frozen_spec(l1, l1_predictions) -> None:
    cfg, _dataset, _data, _manifest = l1
    spec = cfg.section("models.causal_forest")
    recorded = l1_predictions["causal_forest"].info["hyperparameters"]["causal_forest"]
    for key in (
        "n_estimators", "min_samples_leaf", "cv", "n_jobs", "discrete_treatment", "inference"
    ):
        assert recorded[key] == spec[key]
    assert l1_predictions["causal_forest"].info["engine"] == "econml.CausalForestDML"


def test_dr_learner_metadata_and_propensity_clip(l3_predictions) -> None:
    info = l3_predictions["dr_learner"].info
    assert info["crossfit_folds"] == 3
    assert info["final_model"] == "lightgbm_regressor"
    assert len(info["fold_sizes"]) == 3
    assert 0.01 <= info["propensity_min"] <= info["propensity_max"] <= 0.99
    assert info["pseudo_outcome_sd"] > 0.0
    assert info["n_train"] == info["n_treated"] + info["n_control"]


# --------------------------------------------------------------------------- #
# DR 数学（合成样本，真值只用于断言）
# --------------------------------------------------------------------------- #
def test_aipw_pseudo_outcome_algebra() -> None:
    y = np.array([5.0, 1.0, 3.0, 2.0])
    t = np.array([1, 0, 1, 0])
    mu1 = np.array([4.0, 4.0, 2.0, 2.0])
    mu0 = np.array([1.0, 1.0, 1.0, 1.0])
    propensity = np.full(4, 0.5)
    np.testing.assert_allclose(
        models.aipw_pseudo_outcome(y, t, mu1, mu0, propensity), [5.0, 3.0, 3.0, -1.0]
    )
    exact_y = np.array([mu1[0], mu0[1]])
    np.testing.assert_allclose(
        models.aipw_pseudo_outcome(exact_y, np.array([1, 0]), mu1[:2], mu0[:2], propensity[:2]),
        mu1[:2] - mu0[:2],
    )
    with pytest.raises(ValueError, match="严格"):
        models.aipw_pseudo_outcome(y, t, mu1, mu0, np.array([1.0, 0.5, 0.5, 0.5]))


def test_crossfit_dr_ate_corrects_confounding(protocol: V3Protocol) -> None:
    cfg = protocol.scenario("L1_main")
    sample = _confounded_sample()
    y, t = sample["y"], sample["t"]
    naive = float(y[t == 1].mean() - y[t == 0].mean())
    estimate = models.crossfit_dr_ate(sample["X"], y, t, cfg)
    assert abs(naive - 1.0) > 2.0
    assert abs(estimate.ate - 1.0) < 0.25
    assert abs(estimate.ate - 1.0) * 4 < abs(naive - 1.0)
    assert estimate.folds == 3 and estimate.n == y.size and estimate.se > 0.0


def test_dr_learner_recovers_heterogeneous_effect(protocol: V3Protocol) -> None:
    cfg = protocol.scenario("L1_main")
    sample = _heterogeneous_sample()
    tau_hat, info = models.dr_learner_cate(
        sample["X"], sample["y"], sample["t"], sample["X"], cfg
    )
    assert tau_hat.shape == sample["tau"].shape
    assert abs(tau_hat.mean() - 1.0) < 0.2
    assert np.corrcoef(tau_hat, sample["tau"])[0, 1] > 0.4
    assert tau_hat.std(ddof=1) > 0.5
    assert info["crossfit_folds"] == 3
    assert abs(info["dr_ate_training"] - 1.0) < 0.2


def test_crossfit_nuisance_is_deterministic_and_clipped(protocol: V3Protocol) -> None:
    cfg = protocol.scenario("L1_main")
    sample = _confounded_sample(n=1200)
    first = models.crossfit_nuisance(sample["X"], sample["y"], sample["t"], cfg)
    second = models.crossfit_nuisance(sample["X"], sample["y"], sample["t"], cfg)
    np.testing.assert_array_equal(first.propensity, second.propensity)
    np.testing.assert_array_equal(first.mu1, second.mu1)
    np.testing.assert_array_equal(first.mu0, second.mu0)
    other = models.crossfit_nuisance(sample["X"], sample["y"], sample["t"], cfg, seed_index=1)
    assert not np.array_equal(first.propensity, other.propensity)
    clip = [float(value) for value in cfg.require("models.propensity.estimated_probability_clip")]
    assert first.propensity_min >= clip[0] and first.propensity_max <= clip[1]
    assert first.folds == 3 and sum(first.fold_sizes) == sample["y"].size


def test_crossfit_rejects_too_small_sample(protocol: V3Protocol) -> None:
    cfg = protocol.scenario("L1_main")
    with pytest.raises(ValueError, match="太小"):
        models.crossfit_nuisance(
            np.zeros((8, 2)), np.zeros(8), np.array([0, 1] * 4), cfg
        )


# --------------------------------------------------------------------------- #
# 验证集打分与模型选择
# --------------------------------------------------------------------------- #
def test_validation_scorer_uses_validation_split_only(l1, l1_scorer) -> None:
    cfg, _dataset, data, _manifest = l1
    assert l1_scorer.n == data.validation.n
    assert l1_scorer.propensity_source == "recorded_design_probability"
    assert l1_scorer.propensity_min == l1_scorer.propensity_max == 0.5
    assert l1_scorer.scoring == "validation_crossfit_dr_policy_value_lower_confidence_bound"
    swapped = dataclasses.replace(data, test=data.validation)
    replay = models.fit_validation_scorer(swapped, cfg)
    assert replay.n == l1_scorer.n
    np.testing.assert_array_equal(replay.psi, l1_scorer.psi)


def test_validation_score_rejects_bad_vectors(l1, l1_scorer) -> None:
    cfg, _dataset, data, _manifest = l1
    with pytest.raises(ValueError, match="长度"):
        l1_scorer.score(np.zeros(3), cfg)
    broken = np.zeros(data.validation.n)
    broken[0] = np.nan
    with pytest.raises(ValueError, match="非有限"):
        l1_scorer.score(broken, cfg)
    with pytest.raises(ValueError, match="预算"):
        l1_scorer.score(np.zeros(data.validation.n), cfg, budget_per_user_cny=-1.0)


def test_validation_score_is_budget_aware(l1, l1_scorer, l1_predictions) -> None:
    cfg, _dataset, data, _manifest = l1
    tau = l1_predictions["dr_learner"].tau_validation
    low = l1_scorer.score(tau, cfg, budget_per_user_cny=0.04)
    high = l1_scorer.score(tau, cfg, budget_per_user_cny=1.0)
    assert low["n_selected"] <= high["n_selected"]
    assert low["spend_cny"] <= low["budget_cny"] * (1.0 + 1e-9)
    assert high["spend_cny"] <= high["budget_cny"] * (1.0 + 1e-9)
    assert low["budget_cny"] == pytest.approx(0.04 * data.validation.n)
    assert low["policy_value_lcb"] < low["policy_value"]
    assert low["scoring"] == "validation_crossfit_dr_policy_value_lower_confidence_bound"
    assert low["cost_per_user_mean_cny"] == pytest.approx(10.0 * 0.55)
    assert low["n_selected"] <= int(low["budget_cny"] / low["cost_per_user_mean_cny"]) + 1


def test_validation_score_grid_covers_frozen_budget_grid(l1, l1_scorer, l1_predictions) -> None:
    cfg, _dataset, _data, _manifest = l1
    tau = l1_predictions["s_learner"].tau_validation
    grid = l1_scorer.score_grid(tau, cfg)
    assert [row["budget_per_user_cny"] for row in grid] == [
        float(value) for value in cfg.require("policy.budget.per_user_grid_cny")
    ]
    assert all(np.isfinite(row["policy_value_lcb"]) for row in grid)


def test_validation_scoring_refuses_truth_based_selection(l1, l1_scorer, l1_predictions) -> None:
    cfg, _dataset, data, _manifest = l1
    tau = l1_predictions["constant"].tau_validation
    truth_scoring = cfg.with_overrides({"models.selection.scoring": "validation_truth_rmse"})
    with pytest.raises(ConfigError, match="打分"):
        l1_scorer.score(tau, truth_scoring)
    truth_tuning = cfg.with_overrides({"models.selection.true_effect_tuning_forbidden": False})
    with pytest.raises(ConfigError, match="真值"):
        l1_scorer.score(tau, truth_tuning)


def test_rank_models_orders_by_validation_lcb_with_tie_break(l1, l1_scorer, l1_predictions) -> None:
    cfg, _dataset, _data, _manifest = l1
    rows = models.rank_models(l1_predictions, l1_scorer, cfg)
    assert [row["rank"] for row in rows] == [1, 2, 3, 4, 5]
    scores = [row["selection_score"] for row in rows]
    assert scores == sorted(scores, reverse=True)
    tie_order = [str(name) for name in cfg.require("models.selection.tie_break_order")]
    for row in rows:
        assert row["tie_break_index"] == tie_order.index(row["model"])
        assert len(row["policy_value_lcb_by_budget"]) == len(
            cfg.require("policy.budget.per_user_grid_cny")
        )
        assert row["worst_budget_lcb"] <= row["selection_score"] + 1e-12
    with pytest.raises(ValueError, match="没有可排序"):
        models.rank_models({}, l1_scorer, cfg)


# --------------------------------------------------------------------------- #
# 学习曲线：规模效应，不用真值
# --------------------------------------------------------------------------- #
def test_learning_curve_subsample_is_shared_and_reproducible(l1, l1_scorer) -> None:
    cfg, _dataset, data, _manifest = l1
    count = 300
    constant_rows = models.learning_curve("constant", data, cfg, counts=[count], scorer=l1_scorer)
    t_rows = models.learning_curve("t_learner", data, cfg, counts=[count], scorer=l1_scorer)
    assert len(constant_rows) == len(t_rows) == 1
    assert constant_rows[0]["subsample_key_hash"] == t_rows[0]["subsample_key_hash"]
    rng = child_rng(20240101, "v3.models.learning_curve.subsample", 0)
    indices = np.sort(rng.permutation(data.train.n)[:count])
    assert constant_rows[0]["subsample_key_hash"] == user_key_hash(data.train.keys.iloc[indices])
    assert constant_rows[0]["n_train"] == count
    assert constant_rows[0]["stability_rmse_vs_largest"] == 0.0
    assert constant_rows[0]["tau_sd_validation"] == 0.0
    assert np.isfinite(t_rows[0]["validation_policy_value_lcb"])
    assert constant_rows[0]["subsample_key_hash"] not in {
        data.train.key_hash, data.validation.key_hash, data.test.key_hash
    }


def test_learning_curve_reports_only_truth_free_columns(l1, l1_scorer) -> None:
    cfg, _dataset, data, _manifest = l1
    rows = models.learning_curve("t_learner", data, cfg, counts=[200, 400], scorer=l1_scorer)
    expected = {
        "model", "n_train", "n_train_available", "n_features", "tau_mean_validation",
        "tau_sd_validation", "validation_policy_value", "validation_policy_value_lcb",
        "validation_n_selected", "train_cpu_seconds", "subsample_key_hash", "preprocessor_hash",
        "config_hash", "stability_rmse_vs_largest", "stability_corr_vs_largest",
        "reference_n_train",
    }
    assert set(rows[0]) == expected
    assert [row["n_train"] for row in rows] == [200, 400]
    assert rows[1]["stability_rmse_vs_largest"] == 0.0
    assert rows[0]["stability_rmse_vs_largest"] > 0.0
    assert rows[0]["subsample_key_hash"] != rows[1]["subsample_key_hash"]


def test_learning_curve_drops_unavailable_counts_and_rejects_empty(l1, l1_scorer) -> None:
    cfg, _dataset, data, _manifest = l1
    rows = models.learning_curve("constant", data, cfg, counts=[200, 10**9], scorer=l1_scorer)
    assert [row["n_train"] for row in rows] == [200]
    with pytest.raises(ValueError, match="规模"):
        models.learning_curve("constant", data, cfg, counts=[10**9], scorer=l1_scorer)
    with pytest.raises(ValueError, match="未知模型"):
        models.learning_curve("meta_learner", data, cfg, counts=[200], scorer=l1_scorer)


# --------------------------------------------------------------------------- #
# 泄漏边界与冒烟表
# --------------------------------------------------------------------------- #
def test_estimation_module_does_not_import_truth_or_dgp() -> None:
    code = (
        "import sys\n"
        "import causal_growth.estimate.v3_models\n"
        "bad = sorted(name for name in sys.modules\n"
        "             if name.startswith('causal_growth.dgp') or name.split('.')[0] == 'audit')\n"
        "print('|'.join(bad))\n"
    )
    environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=str(ROOT), env=environment,
        capture_output=True, text=True, encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ""


def test_smoke_table_has_no_truth_columns_and_paired_hashes(protocol: V3Protocol) -> None:
    assert SMOKE_CSV.exists(), f"缺少冒烟结果表：{SMOKE_CSV}"
    frame = pd.read_csv(SMOKE_CSV, encoding="utf-8-sig")
    cfg = protocol.scenario("L1_main")
    assert len(frame) == 5
    assert list(frame["model"]) == list(models.MODEL_NAMES)
    assert frame["scenario"].eq("L1_main").all()
    forbidden = {str(name) for name in cfg.require("models.forbidden_features")}
    assert not forbidden & set(frame.columns)
    assert not any(str(column).startswith("potential_") for column in frame.columns)
    assert not any("truth" in str(column).lower() for column in frame.columns)
    assert frame["n_total"].eq(20_000).all()
    assert frame["n_train"].eq(10_000).all()
    assert frame["preprocessor_hash"].nunique() == 1
    assert frame["config_hash"].nunique() == 1
    assert frame["observed_hash"].nunique() == 1
    assert frame["split_fingerprint"].nunique() == 1
    assert frame["test_user_key_hash"].nunique() == 1
    assert frame["constant_source"].iloc[0] == "training_itt"
    assert (frame["total_cpu_seconds"] >= 0.0).all()
    assert frame["tau_sd_test"].ge(0.0).all()
    assert frame["validation_policy_value_lcb"].notna().all()
