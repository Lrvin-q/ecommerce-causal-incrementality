"""合成数据 / 已知 DGP：篡改、跨窗退款与复合外键必须被正确处理。"""

import numpy as np
import pandas as pd
import pytest

from causal_growth.data.v3_tables import build_raw_tables, copy_tables
from causal_growth.data.v3_quality import validate_tables
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.v3_config import load_v3_protocol
from causal_growth.v3_data_config import load_v3_data_config


@pytest.fixture(scope="module")
def case():
    cfg = load_v3_protocol().scenario("L0_P_main").with_overrides({
        "dgp.l0.baseline_purchase_probability": .8, "dgp.l0.purchase_increment": .05,
        "business.refund_rate": 1., "business.refund_rate_treated_multiplier": 1.,
        "business.repeat.probability_given_first_order": 1.,
    })
    pop = generate_v3_population(cfg, 0, 30)
    raw = build_raw_tables(*pop.observation_bundle(), cfg, run_id="quality", rep_id=0, stream_prefix=pop.metadata["stream_prefix"])
    return cfg, raw


@pytest.mark.parametrize("violation", ["missing_assignment", "foreign_run", "foreign_user", "duplicate_assignment", "duplicate_order", "fractional_money", "negative_money", "refund_time", "missing_refund", "consumer_paid", "coupon_twice", "goods_recovery", "refund_fee", "no_first_order", "repeat_amount", "first_exceeds_cart", "future_feature", "event_count", "truth_column"])
def test_exact_contract_tampering_fails(case, violation):
    cfg, original = case
    tables = copy_tables(original)
    o, a, u, e = (tables[k] for k in ("orders", "coupon_assignment", "users", "user_events"))
    idx = o.index[0]
    if violation == "missing_assignment":
        tables["coupon_assignment"] = a.iloc[1:]
    elif violation == "foreign_run":
        o.loc[idx, "run_id"] = "other_repetition"
    elif violation == "foreign_user":
        o.loc[idx, "user_id"] = int(u.user_id.max()) + 1
    elif violation == "duplicate_assignment":
        tables["coupon_assignment"] = pd.concat([a, a.iloc[[0]]], ignore_index=True)
    elif violation == "duplicate_order":
        tables["orders"] = pd.concat([o, o.iloc[[0]]], ignore_index=True)
    elif violation == "fractional_money":
        o["gross_order_amount_cent"] = o.gross_order_amount_cent.astype(float)
        o.loc[idx, "gross_order_amount_cent"] += .5
    elif violation == "negative_money":
        o.loc[idx, "fulfill_cost_cent"] = -1
    elif violation == "refund_time":
        o.loc[idx, "refund_day"] = o.loc[idx, "paid_day"] - 1
    elif violation == "missing_refund":
        o.loc[idx, "refund_day"] = np.nan
    elif violation == "consumer_paid":
        o.loc[idx, "consumer_paid_cent"] += 1
    elif violation == "coupon_twice":
        o.loc[idx, "coupon_cost_initial_cent"] += 1
    elif violation == "goods_recovery":
        o.loc[idx, "goods_cost_recovered_cent"] += 1
    elif violation == "refund_fee":
        o.loc[idx, "refund_processing_fee_cent"] += 1
    elif violation == "no_first_order":
        uid = o.loc[o.order_number == 2, "user_id"].iloc[0]
        tables["orders"] = o.loc[~((o.user_id == uid) & (o.order_number == 1))]
    elif violation == "repeat_amount":
        second = o.index[o.order_number == 2][0]
        o.loc[second, "gross_order_amount_cent"] += 1
        o.loc[second, "consumer_paid_cent"] += 1
        o.loc[second, "gross_refund_reversal_cent"] += 1
        o.loc[second, "consumer_refund_cent"] += 1
    elif violation == "first_exceeds_cart":
        uid = o.loc[o.order_number == 1, "user_id"].iloc[0]
        u.loc[u.user_id == uid, "cart_value_cent"] = 0
    elif violation == "future_feature":
        row = e.index[0]
        end = float(u.set_index("user_id").loc[e.loc[row, "user_id"], "assignment_day"])
        e.loc[row, ["event_day", "ingested_day"]] = end + 1
    elif violation == "event_count":
        u.loc[u.index[0], "event_retained_count"] += 1
    else:
        u["audit_u"] = 0
    with pytest.raises(ValueError):
        validate_tables(tables, cfg, stage="raw")


def test_refund_boundary_and_late_refund_remain_fact_rows(case):
    cfg, original = case
    tables = copy_tables(original)
    orders = tables["orders"]
    first_two = orders.index[:2]
    orders.loc[first_two, "refund_day"] = orders.loc[first_two, "assignment_day"].to_numpy() + np.array([30., 31.])
    orders.loc[first_two, "refund_ingested_day"] = orders.loc[first_two, "refund_day"]
    before = len(orders)
    validate_tables(tables, cfg, stage="raw")
    assert len(tables["orders"]) == before
    assert tables["orders"].loc[first_two, "gross_refund_reversal_cent"].gt(0).all()


def test_same_user_ids_in_different_runs_do_not_cross_join(case):
    cfg, first = case
    second = copy_tables(first)
    for frame in second.values():
        frame["run_id"] = "second"
    combined = {name: pd.concat([first[name], second[name]], ignore_index=True) for name in first}
    report = validate_tables(combined, cfg, stage="raw")
    assert report["users"] == 2 * len(first["users"])
    assert report["orders"] == 2 * len(first["orders"])


def test_outcome_materialization_is_required_when_requested(case):
    cfg, tables = case
    with pytest.raises(ValueError, match="两个窗口"):
        validate_tables(tables, cfg, require_outcomes=True)


@pytest.mark.parametrize("table,event,arrival", [
    ("user_events", "event_day", "ingested_day"),
    ("coupon_assignment", "assignment_day", "ingested_day"),
    ("orders", "paid_day", "paid_ingested_day"),
    ("orders", "refund_day", "refund_ingested_day"),
])
def test_ingestion_delay_cannot_exceed_declared_maximum(case, table, event, arrival):
    cfg, original = case
    tables = copy_tables(original)
    maximum = cfg.require("data.dirty.ingestion_delay_max_hours") / load_v3_data_config().require("time.hours_per_day")
    frame = tables[table]
    idx = frame.index[frame[event].notna()][0]
    frame.loc[idx, arrival] = frame.loc[idx, event] + maximum + 1
    with pytest.raises(ValueError, match="延迟上限"):
        validate_tables(tables, cfg, stage="dirty")


@pytest.mark.parametrize("table,event,arrival", [
    ("user_events", "event_day", "ingested_day"),
    ("coupon_assignment", "assignment_day", "ingested_day"),
    ("orders", "paid_day", "paid_ingested_day"),
    ("orders", "refund_day", "refund_ingested_day"),
])
def test_exact_ingestion_endpoint_passes_and_next_float_fails(case, table, event, arrival):
    cfg, original = case
    tables = copy_tables(original)
    maximum = cfg.require("data.dirty.ingestion_delay_max_hours") / load_v3_data_config().require("time.hours_per_day")
    frame = tables[table]
    valid = frame[event].notna()
    endpoints = frame.loc[valid, event].to_numpy() + maximum
    frame.loc[valid, arrival] = endpoints
    validate_tables(tables, cfg, stage="dirty")
    idx = frame.index[valid][0]
    frame.loc[idx, arrival] = np.nextafter(frame.loc[idx, arrival], np.inf)
    with pytest.raises(ValueError, match="延迟上限"):
        validate_tables(tables, cfg, stage="dirty")


def test_refund_arrival_before_payment_arrival_is_a_valid_fact(case):
    cfg, original = case
    tables = copy_tables(original)
    maximum = cfg.require("data.dirty.ingestion_delay_max_hours") / load_v3_data_config().require("time.hours_per_day")
    orders = tables["orders"]
    idx = orders.index[0]
    orders.loc[idx, "refund_day"] = orders.loc[idx, "paid_day"] + maximum / 2
    orders.loc[idx, "refund_ingested_day"] = orders.loc[idx, "refund_day"]
    orders.loc[idx, "paid_ingested_day"] = orders.loc[idx, "paid_day"] + maximum
    validate_tables(tables, cfg, stage="dirty")
    assert orders.loc[idx, "refund_ingested_day"] < orders.loc[idx, "paid_ingested_day"]


def test_sql_materialized_outcomes_pass_full_cohort_quality_and_reject_tampering(case):
    from causal_growth.data.v3_sql import OUTCOME_COLUMNS, run_sql_pipeline

    cfg, original = case
    tables = copy_tables(original)
    result = run_sql_pipeline(tables, cfg)
    tables["user_outcomes"] = result.user_outcomes
    assert tuple(tables["user_outcomes"]) == OUTCOME_COLUMNS
    report = validate_tables(tables, cfg, stage="raw", require_outcomes=True)
    assert report["outcomes"] == 2 * report["users"]
    for column in ("net_profit_cent", "complete_after_day", "window_end_day", "converted"):
        changed = copy_tables(tables)
        changed["user_outcomes"].loc[0, column] += 1
        with pytest.raises(ValueError):
            validate_tables(changed, cfg, stage="raw", require_outcomes=True)


def test_fractional_assignment_exact_maturity_endpoint_survives_sql_and_quality(tmp_path):
    from causal_growth.data.v3_sql import run_sql_pipeline

    cfg = load_v3_protocol().scenario("L1_main")
    pop = generate_v3_population(cfg, 0, 200)
    tables = build_raw_tables(*pop.observation_bundle(), cfg, run_id="fractional_endpoint", rep_id=0,
                              stream_prefix=pop.metadata["stream_prefix"])
    window = float(cfg.require("windows.profit_days"))
    delay = float(cfg.require("data.dirty.ingestion_delay_max_hours")) / load_v3_data_config().require("time.hours_per_day")
    assignment = tables["users"].assignment_day.to_numpy()
    endpoint = assignment + (window + delay)
    # 保证该例确实包含浮点结合顺序有区别的日期，而非整数日期的无效回归。
    assert np.any(endpoint != (assignment + window) + delay)
    at = run_sql_pipeline(tables, cfg, database_path=tmp_path / "fractional.sqlite",
                          relative_snapshot_days=window + delay, allow_immature=True)
    tables["user_outcomes"] = at.user_outcomes
    validate_tables(tables, cfg, stage="raw", require_outcomes=True)
    profit = at.user_outcomes.loc[at.user_outcomes.window_type == load_v3_data_config().require("sql.profit_window_name")]
    np.testing.assert_array_equal(profit.asof_day, profit.complete_after_day)
    assert profit.mature.eq(1).all()
    full = run_sql_pipeline(tables, cfg)
    tables["user_outcomes"] = full.user_outcomes
    validate_tables(tables, cfg, stage="raw", require_outcomes=True)
    assert full.analysis.mature.eq(1).all()
    tampered = copy_tables(tables)
    complete = tampered["user_outcomes"].complete_after_day.to_numpy()
    tampered["user_outcomes"]["complete_after_day"] = np.nextafter(complete, np.inf)
    with pytest.raises(ValueError, match="成熟最晚日期"):
        validate_tables(tampered, cfg, stage="raw", require_outcomes=True)
