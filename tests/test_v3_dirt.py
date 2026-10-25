"""合成数据 / 已知 DGP：污染正交、配对入库延迟和确定性去重。"""

import numpy as np
import pandas as pd
import pytest

from causal_growth.data.v3_tables import build_raw_tables, copy_tables
from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.v3_config import load_v3_protocol
from causal_growth.rng import child_rng


@pytest.fixture(scope="module")
def raw():
    cfg = load_v3_protocol().scenario("L0_P_main").with_overrides({
        "dgp.l0.baseline_purchase_probability": .8, "dgp.l0.purchase_increment": .05,
        "business.refund_rate": 1., "business.refund_rate_treated_multiplier": 1.,
        "business.repeat.probability_given_first_order": 1.,
    })
    pop = generate_v3_population(cfg, 4, 64)
    tables = build_raw_tables(*pop.observation_bundle(), cfg, run_id="dirt", rep_id=4, stream_prefix=pop.metadata["stream_prefix"])
    return tables, cfg, pop.metadata["stream_prefix"]


def test_declared_dirt_is_lossless_for_facts_and_does_not_mutate_input(raw):
    tables, cfg, prefix = raw
    before = copy_tables(tables)
    cfg = cfg.with_overrides({"data.dirty.cart_missing_by_channel": {k: 1. for k in cfg.require("business.channels")},
                              "data.dirty.fraud_user_rate": 1., "data.dirty.duplicate_event_rate": 1.})
    dirty = inject_dirt(tables, cfg, rep_id=4, stream_prefix=prefix)
    assert dirty.tables["users"].cart_value_cent.isna().all()
    assert "cart_value" not in dirty.tables["users"]
    np.testing.assert_allclose(dirty.tables["users"].hist_gmv, tables["users"].hist_gmv * cfg.require("data.dirty.fraud_hist_gmv_multiplier"))
    assert len(dirty.tables["user_events"]) == 2 * len(tables["user_events"])
    untouched = [c for c in tables["orders"] if "ingested" not in c]
    pd.testing.assert_frame_equal(dirty.tables["orders"][untouched], tables["orders"][untouched])
    for name in before:
        pd.testing.assert_frame_equal(tables[name], before[name])
    clean = deduplicate_events(dirty.tables, cfg)
    assert len(clean.tables["user_events"]) == len(tables["user_events"])
    assert clean.counts["duplicate_events_removed"] == len(tables["user_events"])
    assert clean.tables["users"].cart_value_cent.isna().all()
    assert len(clean.tables["orders"]) == len(tables["orders"])
    assert clean.data_config_hash == dirty.data_config_hash


def test_ingestion_delays_follow_potential_user_order_not_factual_row_position(raw):
    tables, cfg, prefix = raw
    full = inject_dirt(tables, cfg, rep_id=4, stream_prefix=prefix).tables["orders"]
    subset = copy_tables(tables)
    keep_users = subset["orders"].user_id.unique()[::2]
    kept = subset["orders"].loc[subset["orders"].user_id.isin(keep_users)]
    subset["orders"] = kept.iloc[child_rng(20261025, "test.order.permutation").permutation(len(kept))].reset_index(drop=True)
    altered = inject_dirt(subset, cfg, rep_id=4, stream_prefix=prefix).tables["orders"]
    fields = ["paid_ingested_day", "refund_ingested_day"]
    pd.testing.assert_frame_equal(altered.set_index("order_id")[fields].sort_index(), full.set_index("order_id").loc[altered.order_id, fields].sort_index())


def test_cart_missing_knob_does_not_change_other_random_streams(raw):
    tables, cfg, prefix = raw
    first = inject_dirt(tables, cfg, rep_id=4, stream_prefix=prefix)
    changed = cfg.with_overrides({"data.dirty.missing_rate_multiplier": 0.})
    second = inject_dirt(tables, changed, rep_id=4, stream_prefix=prefix)
    for table in ("orders", "user_events", "coupon_assignment"):
        pd.testing.assert_frame_equal(first.tables[table], second.tables[table])
    pd.testing.assert_series_equal(first.tables["users"].hist_gmv, second.tables["users"].hist_gmv)


def test_disabled_dirt_and_l3_main_keep_complete_confounders(raw):
    tables, cfg, prefix = raw
    disabled = inject_dirt(tables, cfg.with_overrides({"data.dirty.enabled": False}), rep_id=4, stream_prefix=prefix)
    for name in tables:
        pd.testing.assert_frame_equal(disabled.tables[name], tables[name])
    cfg3 = load_v3_protocol().scenario("L3_fixed_lt000")
    pop = generate_v3_population(cfg3, 0, 120)
    raw3 = build_raw_tables(*pop.observation_bundle(), cfg3, run_id="l3", rep_id=0, stream_prefix=pop.metadata["stream_prefix"])
    dirty3 = inject_dirt(raw3, cfg3, rep_id=0, stream_prefix=pop.metadata["stream_prefix"])
    assert dirty3.counts["cart_missing_injected"] == dirty3.counts["hist_fraud_injected"] == 0
    pd.testing.assert_series_equal(dirty3.tables["users"].cart_value_cent, raw3["users"].cart_value_cent)
    pd.testing.assert_series_equal(dirty3.tables["users"].hist_gmv, raw3["users"].hist_gmv)


def test_conflicting_duplicate_payload_raises_instead_of_choosing_a_row(raw):
    tables, cfg, _ = raw
    bad = copy_tables(tables)
    duplicate = bad["user_events"].iloc[[0]].copy()
    duplicate["event_type"] = "cart" if duplicate.event_type.iloc[0] != "cart" else "browse"
    bad["user_events"] = pd.concat([bad["user_events"], duplicate], ignore_index=True)
    with pytest.raises(ValueError, match="载荷冲突"):
        deduplicate_events(bad, cfg)


def test_duplicate_earliest_arrival_is_deterministic(raw):
    tables, cfg, _ = raw
    dirty = copy_tables(tables)
    duplicate = dirty["user_events"].iloc[[0]].copy()
    duplicate["ingested_day"] += 1
    dirty["user_events"] = pd.concat([duplicate, dirty["user_events"]], ignore_index=True)
    result = deduplicate_events(dirty, cfg)
    selected = result.tables["user_events"].set_index("event_id").loc[duplicate.event_id.iloc[0]]
    assert selected.ingested_day == tables["user_events"].iloc[0].ingested_day
