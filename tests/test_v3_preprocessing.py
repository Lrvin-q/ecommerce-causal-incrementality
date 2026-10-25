"""合成数据 / 已知 DGP：训练专属统计、变换冻结、完整共同原因与泄漏拒绝。"""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from causal_growth.config import ConfigError
from causal_growth.data.v3_preprocessing import FrozenPreprocessor, fit_preprocessor
from causal_growth.data.v3_split import rolling_training_candidates
from causal_growth.v3_config import load_v3_protocol


def _training():
    return pd.DataFrame({"run_id": "r", "user_id": np.arange(1, 9), "split": "train",
        "is_new": [0, 1] * 4, "hist_gmv": [10, 20, 30, 40, 50, 60, 70, 80],
        "cart_value": [10., 30., np.nan, np.nan, 50., 70., 90., 110.],
        "browse_depth": [1, 2, 3, 4, 5, 6, 7, 8],
        "channel": ["search", "search", "feed", "feed", "xhs", "xhs", "other", "other"],
        "assignment_week": [1, 2, 3, 4, 5, 1, 2, 3],
        "assignment_day": [0., 7., 14., 21., 28., 0., 7., 14.],
        "required_ingestion_day": [30., 37., 44., 51., 58., 30., 37., 44.],
        "complete_after_day": [32., 39., 46., 53., 60., 32., 39., 46.]})


def test_train_channel_median_and_global_fallback_with_missing_indicator():
    cfg = load_v3_protocol().scenario("L1_main")
    state = fit_preprocessor(_training(), cfg, role="train")
    params = state.to_dict()["numeric_state"]["cart_value"]
    assert params["channel_medians"]["search"] == 20
    assert "feed" not in params["channel_medians"]
    assert params["global_median"] == 60
    test = _training().iloc[[0, 2]].assign(split="test", cart_value=np.nan)
    transformed = state.transform(test)
    col = transformed.feature_names.index("cart_value")
    expected = (np.array([20, 60]) - params["mean"]) / params["scale"]
    np.testing.assert_allclose(transformed.matrix[:, col], expected)
    np.testing.assert_array_equal(transformed.matrix[:, transformed.feature_names.index("cart_value_missing")], [1, 1])


def test_test_and_validation_mutations_do_not_change_fit_or_frozen_state():
    cfg = load_v3_protocol().scenario("L1_main")
    train = _training()
    state = fit_preprocessor(train, cfg, role="train")
    initial = state.to_dict()
    validation = train.assign(split="validation", hist_gmv=1e12, cart_value=-1e12)
    test = train.assign(split="test", hist_gmv=-1e12, cart_value=1e12)
    state.transform(validation)
    state.transform(test)
    assert state.to_dict() == initial
    refit = fit_preprocessor(train, cfg, role="train")
    assert refit.hash == state.hash
    # Outcome mutation within training is also irrelevant to preprocessing state.
    assert fit_preprocessor(train.assign(net_profit_30d=1e20), cfg, role="train").hash == state.hash


def test_l3_complete_confounders_remain_invertible_under_extreme_extrapolation():
    cfg = load_v3_protocol().scenario("L3_fixed_lt000")
    training = _training().fillna({"cart_value": 60})
    state = fit_preprocessor(training, cfg, role="train")
    test = training.assign(split="test", cart_value=np.linspace(1e4, 1e8, len(training)))
    transformed = state.transform(test)
    for name in ["is_new", "hist_gmv", "cart_value", "browse_depth"]:
        parameter = state.to_dict()["numeric_state"][name]
        assert parameter["winsor_lower"] is parameter["winsor_upper"] is None
        recovered = transformed.matrix[:, transformed.feature_names.index(name)] * parameter["scale"] + parameter["mean"]
        np.testing.assert_allclose(recovered, test[name])
        assert transformed.log["by_feature"][name]["winsorized_n"] == 0
        assert transformed.log["by_feature"][name]["standardized_clipped_n"] == 0


def test_state_roundtrip_and_dict_copies_are_frozen():
    state = fit_preprocessor(_training(), load_v3_protocol().scenario("L1_main"), role="train")
    copied = state.to_dict()
    restored = FrozenPreprocessor.from_dict(json.loads(json.dumps(copied, ensure_ascii=False)))
    assert restored.hash == state.hash
    np.testing.assert_array_equal(restored.transform(_training()).matrix, state.transform(_training()).matrix)
    copied["numeric_state"]["cart_value"]["mean"] = 999
    assert copied != state.to_dict()
    corrupt = state.to_dict()
    corrupt["numeric_columns"].append("net_profit_30d")
    with pytest.raises(ValueError, match="边界"):
        FrozenPreprocessor.from_dict(corrupt)


@pytest.mark.parametrize("role", ["test", "validation", "train", "rolling_train"])
def test_fit_cannot_default_or_relabel_test_rows(role):
    cfg = load_v3_protocol().scenario("L1_main")
    with pytest.raises(ValueError):
        fit_preprocessor(_training().assign(split="test"), cfg, role=role)
    with pytest.raises(TypeError):
        fit_preprocessor(_training(), cfg)


def test_all_missing_global_feature_fails_without_test_fallback():
    with pytest.raises(ValueError, match="全缺失"):
        fit_preprocessor(_training().assign(cart_value=np.nan), load_v3_protocol().scenario("L1_main"), role="train")


def test_fixed_channel_dictionary_and_unknown_category_error():
    cfg = load_v3_protocol().scenario("L1_main")
    training = _training().iloc[:2]
    state = fit_preprocessor(training, cfg, role="train")
    # A configured category absent from this tiny training sample is not an
    # unknown dictionary value, and its imputation uses the training fallback.
    valid = training.assign(channel="xhs", split="test", cart_value=np.nan)
    assert state.transform(valid).matrix.shape[0] == len(valid)
    with pytest.raises(ValueError, match="冻结渠道"):
        state.transform(valid.assign(channel="unseen_external_channel"))


@pytest.mark.parametrize("column", ["U", "true_cate", "potential_profit0", "common_feasible", "p0"])
def test_truth_columns_rejected_even_when_not_requested_features(column):
    cfg = load_v3_protocol().scenario("L1_main")
    with pytest.raises(ValueError, match="审计"):
        fit_preprocessor(_training().assign(**{column: 1}), cfg, role="train")


def test_audit_source_path_is_rejected():
    frame = _training()
    frame.attrs["source_path"] = "D:/project/audit/v3/truth/users.csv"
    with pytest.raises(ValueError, match="路径"):
        fit_preprocessor(frame, load_v3_protocol().scenario("L1_main"), role="train")


def test_feature_misspecification_omits_explicit_new_user_and_channel():
    protocol = load_v3_protocol()
    scenario = next(row["id"] for row in protocol.config.to_dict()["scenarios"]
                    if row["overrides"].get("models.feature_specification") == "omit_new_user_and_channel")
    state = fit_preprocessor(_training(), protocol.scenario(scenario), role="train")
    assert "is_new" not in state.feature_names and "is_new_missing" not in state.feature_names
    assert not any(name.startswith("channel_") for name in state.feature_names)
    invalid = protocol.scenario("L1_main").with_overrides({"models.feature_whitelist": ["net_profit_30d"]})
    with pytest.raises(ConfigError, match="白名单"):
        fit_preprocessor(_training(), invalid, role="train")


def test_rolling_requires_matching_receipt_and_rechecks_actual_times():
    cfg = load_v3_protocol().scenario("L2_n200000_p050")
    training = _training().fillna({"cart_value": 60})
    prior = training.iloc[:2].assign(user_id=[20, 21], split="test", assignment_week=16,
                                    assignment_day=105., required_ingestion_day=135., complete_after_day=137.)
    all_rows = pd.concat([training, prior], ignore_index=True)
    selection = rolling_training_candidates(all_rows, cfg, origin_week=22)
    chosen = all_rows.merge(selection.train_user_keys, on=["run_id", "user_id"], validate="one_to_one")
    state = fit_preprocessor(chosen, cfg, role="rolling_train", time_mode="rolling_retrain",
                             selection_receipt=selection.manifest)
    assert "assignment_week" in state.feature_names and "assignment_elapsed_days" in state.feature_names
    assert state.to_dict()["training_n"] == len(chosen)
    wrong = copy.deepcopy(selection.manifest)
    wrong["train_user_key_hash"] = "forged"
    with pytest.raises(ValueError, match="凭据"):
        fit_preprocessor(chosen, cfg, role="rolling_train", selection_receipt=wrong)
    future = chosen.copy()
    future.loc[0, "assignment_day"] = 1e6
    with pytest.raises(ValueError, match="未来"):
        fit_preprocessor(future, cfg, role="rolling_train", selection_receipt=selection.manifest)


def test_static_has_no_time_features_and_time_modes_are_explicit():
    cfg = load_v3_protocol().scenario("L2_n200000_p050")
    static = fit_preprocessor(_training(), cfg, role="train", time_mode="static")
    temporal = fit_preprocessor(_training(), cfg, role="train", time_mode="time_features")
    assert "assignment_week" not in static.feature_names
    assert "assignment_week" in temporal.feature_names
    future = _training().iloc[:3].assign(split="test", assignment_week=[16, 22, 28], assignment_day=[105., 147., 189.])
    transformed = temporal.transform(future)
    for name in ("assignment_week", "assignment_elapsed_days"):
        assert len(np.unique(transformed.matrix[:, transformed.feature_names.index(name)])) == len(future)
        assert transformed.log["by_feature"][name]["winsorized_n"] == 0
        assert transformed.log["by_feature"][name]["standardized_clipped_n"] == 0
    with pytest.raises(ConfigError):
        fit_preprocessor(_training(), cfg, role="train", time_mode="future_outcome")


@pytest.mark.parametrize("marker", ["source_kind", "kind_column", "policy_arm", "diagnostic_attribute", "diagnostic_column"])
def test_validation_and_diagnostic_training_rejected_even_if_split_is_train(marker):
    cfg = load_v3_protocol().scenario("L1_main")
    training = _training()
    state = fit_preprocessor(training, cfg, role="train")
    marked = training.copy()
    if marker == "source_kind":
        marked.attrs["population_kind"] = "validation"
    elif marker == "kind_column":
        marked["population_kind"] = "validation"
    elif marker == "policy_arm":
        marked["assigned_policy_arm"] = np.nan
        marked.loc[0, "assigned_policy_arm"] = 0
    elif marker == "diagnostic_attribute":
        marked.attrs["diagnostic_snapshot"] = True
    else:
        marked["diagnostic_snapshot"] = False
        marked.loc[0, "diagnostic_snapshot"] = True
    with pytest.raises(ValueError, match="验证|诊断"):
        fit_preprocessor(marked, cfg, role="train")
    # Applying already-frozen preprocessing to new observable X remains legal.
    assert state.transform(marked).matrix.shape[0] == len(marked)
