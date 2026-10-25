"""SQL-versus-independent-ledger and temporal boundary checks for synthetic v3."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.data.v3_sql import ANALYSIS_COLUMNS, BUSINESS_TABLES, OUTCOME_COLUMNS, run_sql_pipeline
from causal_growth.data.v3_storage import dataframe_sha256
from causal_growth.data.v3_tables import OUTPUT_COLUMNS, build_raw_tables, copy_tables
from causal_growth.dgp.v3_amounts import posted_components
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.dgp.v3_ledger import ORDER_COLUMNS, audit_window_ledger
from causal_growth.v3_config import load_v3_protocol


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


def _raw(cfg, n=1000, rep=0, run="test"):
    population = generate_v3_population(cfg, rep, n=n)
    tables = build_raw_tables(*population.observation_bundle(), cfg, run_id=run, rep_id=rep,
                              stream_prefix=population.metadata["stream_prefix"])
    return population, tables


def _manual(cfg):
    users = pd.DataFrame({
        "user_id": [1, 2, 3, 4], "is_new": [0, 1, 0, 1], "hist_gmv": [100.] * 4,
        "cart_value_cent": [20000] * 4, "cart_value": [200.] * 4, "browse_depth": [0] * 4,
        "channel": ["search", "feed", "xhs", "other"], "assignment_week": [1, 1, 1, 8],
        "assignment_day": [0., 0., 0., 50.], "assignment_elapsed_days": [0., 0., 0., 50.],
        "split": ["pending_stratified"] * 4,
    })
    assignments = pd.DataFrame({"user_id": users.user_id, "actual_action": [1, 0, 0, 1],
                                "label": [1, 0, 0, 1], "design_probability": [.5] * 4})
    records = []
    for uid, number, action, paid, refund, gross, redeemed in (
        (1, 1, 1, 1., 10., 10000, True), (1, 2, 1, 20., 31., 5500, False),
        (2, 1, 0, 8., None, 10000, False), (4, 1, 1, 51., None, 10000, True),
    ):
        assigned = float(users.set_index("user_id").loc[uid, "assignment_day"])
        fulfill = int(cfg.require("business.fulfill_cost_mean") * cfg.require("business.money.cents_per_yuan"))
        initial = posted_components(np.array([gross]), np.array([fulfill]), np.array([redeemed]), np.array([False]), cfg, coupon_eligible=number == 1)
        final = posted_components(np.array([gross]), np.array([fulfill]), np.array([redeemed]), np.array([refund is not None]), cfg, coupon_eligible=number == 1)
        row = {"user_id": uid, "order_id": uid * 2 + number - 1, "order_number": number,
               "action": action, "assignment_day": assigned, "paid_day": paid, "refund_day": refund,
               "refunded": refund is not None}
        for name in ("gross_order_amount", "goods_cost", "fulfill_cost", "coupon_discount", "consumer_paid"):
            row[f"{name}_cent"] = int(initial[name][0])
        row["coupon_cost_initial_cent"] = int(initial["coupon_cost"][0])
        for name in ("goods_cost_recovered", "refund_processing_fee", "gross_refund_reversal", "consumer_refund"):
            row[f"{name}_cent"] = int(final[name][0])
        row["coupon_return_cent"] = int(initial["coupon_cost"][0] - final["coupon_cost"][0])
        records.append(row)
    orders = pd.DataFrame(records).loc[:, ORDER_COLUMNS]
    tables = build_raw_tables(users, assignments, orders, cfg, run_id="manual", rep_id=0, stream_prefix="v3.manual.history")
    return users, orders, tables


@pytest.mark.parametrize("scenario", ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt050"])
def test_four_layers_integer_component_reconciliation(protocol, scenario):
    cfg = protocol.scenario(scenario)
    population, raw = _raw(cfg, n=1000)
    clean = deduplicate_events(inject_dirt(raw, cfg, rep_id=0, stream_prefix=population.metadata["stream_prefix"]).tables, cfg).tables
    result = run_sql_pipeline(clean, cfg)
    independent = audit_window_ledger(population.users, population.observed_orders, cfg).sort_values("user_id")
    actual = result.analysis.sort_values("user_id")
    for column in independent:
        if column in actual:
            np.testing.assert_array_equal(actual[column], independent[column], err_msg=f"{scenario}/{column}")
    assert len(actual) == result.input_users_n == result.visible_assigned_n == 1000
    assert len(result.user_outcomes) == 2 * len(actual)
    assert set(result.user_outcomes.window_type) == {"convert_7d", "profit_30d"}
    assert not result.quality.violations.any()
    assert actual.mature.eq(1).all()
    assert set(actual.columns) == set(ANALYSIS_COLUMNS)
    assert OUTCOME_COLUMNS == OUTPUT_COLUMNS["user_outcomes"]


def test_zero_order_refunds_second_orders_and_coupon_once(protocol):
    cfg = protocol.scenario("L1_main").with_overrides({"business.coupon_returned_on_refund": True})
    users, orders, tables = _manual(cfg)
    result = run_sql_pipeline(tables, cfg)
    actual = result.analysis.set_index("user_id")
    expected = audit_window_ledger(users, orders, cfg).set_index("user_id")
    for column in expected:
        if column in actual:
            np.testing.assert_array_equal(actual[column], expected[column])
    assert actual.loc[1, "paid_orders_30d"] == 2
    assert actual.loc[1, "refunded_orders_30d"] == 1  # second refund at day31 stays in facts
    assert actual.loc[1, "gross_order_amount_cent"] == 15500
    assert actual.loc[1, "coupon_cost_initial_cent"] == 1000
    assert actual.loc[1, "coupon_return_cent"] == 1000
    assert actual.loc[1, "coupon_cost_cent"] == 0
    assert actual.loc[2, "paid_purchase_7d"] == 0 and actual.loc[2, "paid_orders_30d"] == 1
    assert actual.loc[3, "net_profit_cent"] == 0 and actual.loc[3, "paid_orders_30d"] == 0
    assert len(actual) > (actual.coupon_cost_initial_cent > 0).sum()
    assert result.summaries["groups"].n_total.sum() == len(users)
    assert result.summaries["funnel"].assigned_users.sum() == len(users)
    assert tables["orders"].refunded.sum() == 2  # SQL has not deleted the cross-window refund


def test_arrival_snapshot_does_not_expose_future_refund_or_assignment(protocol):
    cfg = protocol.scenario("L1_main").with_overrides({"business.coupon_returned_on_refund": True})
    _, _, tables = _manual(cfg)
    tables["coupon_assignment"].loc[tables["coupon_assignment"].user_id == 1, "ingested_day"] = .5
    first = (tables["orders"].user_id == 1) & (tables["orders"].order_number == 1)
    tables["orders"].loc[first, "paid_ingested_day"] = 2.
    tables["orders"].loc[first, "refund_ingested_day"] = 11.
    before = run_sql_pipeline(tables, cfg, asof_day=10.5, allow_immature=True)
    after = run_sql_pipeline(tables, cfg, asof_day=11., allow_immature=True)
    b, a = before.analysis.set_index("user_id"), after.analysis.set_index("user_id")
    assert before.input_users_n == 4 and before.visible_assigned_n == 3
    assert 4 not in b.index  # assignment day50 is not a past observation
    assert b.loc[1, "any_refund_30d"] == 0 and b.loc[1, "coupon_cost_cent"] == 1000
    assert b.loc[1, "required_ingestion_day"] == 2
    assert a.loc[1, "any_refund_30d"] == 1 and a.loc[1, "coupon_cost_cent"] == 0
    assert a.loc[1, "required_ingestion_day"] == 11
    assert not b.mature.any()
    with pytest.raises(ValueError, match="fully mature"):
        run_sql_pipeline(tables, cfg, asof_day=11.)
    # A changed future refund payload cannot change the earlier observed frame.
    changed = copy_tables(tables)
    changed["orders"].loc[first, "refund_day"] = 12.
    changed["orders"].loc[first, "refund_ingested_day"] = 13.
    invisible = run_sql_pipeline(changed, cfg, asof_day=10.5, allow_immature=True)
    pd.testing.assert_frame_equal(before.analysis, invisible.analysis)


def test_relative_snapshot_uses_each_users_clock_and_assignment_arrival(protocol):
    cfg = protocol.scenario("L1_main")
    _, _, tables = _manual(cfg)
    diagnostic = run_sql_pipeline(tables, cfg, relative_snapshot_days=7., allow_immature=True)
    assert diagnostic.analysis.asof_day.tolist() == [7., 7., 7., 57.]
    assert diagnostic.visible_assigned_n == 4
    assert not diagnostic.analysis.mature.any()
    assert diagnostic.analysis.diagnostic_snapshot.eq(1).all()
    assert diagnostic.analysis.set_index("user_id").loc[4, "paid_purchase_7d"] == 1
    delayed = copy_tables(tables)
    delayed["coupon_assignment"].loc[delayed["coupon_assignment"].user_id == 2, "ingested_day"] = 1.
    zero = run_sql_pipeline(delayed, cfg, relative_snapshot_days=0., allow_immature=True)
    assert 2 not in set(zero.analysis.user_id)
    with pytest.raises(ValueError, match="mutually exclusive"):
        run_sql_pipeline(tables, cfg, asof_day=7., relative_snapshot_days=7., allow_immature=True)
    with pytest.raises(ValueError, match="explicit"):
        run_sql_pipeline(tables, cfg, relative_snapshot_days=7.)


def test_refund_and_payment_arrival_are_independently_posted(protocol):
    cfg = protocol.scenario("L1_main").with_overrides({"business.coupon_returned_on_refund": True})
    _, _, tables = _manual(cfg)
    first = (tables["orders"].user_id == 1) & (tables["orders"].order_number == 1)
    tables["orders"].loc[first, ["paid_ingested_day", "refund_day", "refund_ingested_day"]] = [2.8, 1.5, 1.6]
    result = run_sql_pipeline(tables, cfg, asof_day=2., allow_immature=True)
    user = result.analysis.set_index("user_id").loc[1]
    assert user.paid_orders_30d == 0 and user.refunded_orders_30d == 1
    assert user.coupon_cost_initial_cent == 0 and user.coupon_return_cent == 1000
    assert user.coupon_cost_cent == -1000
    assert user.required_ingestion_day == 1.6


def test_conservative_maturity_and_inclusive_boundaries(protocol):
    cfg = protocol.scenario("L1_main")
    _, _, tables = _manual(cfg)
    before = run_sql_pipeline(tables, cfg, relative_snapshot_days=31., allow_immature=True)
    at = run_sql_pipeline(tables, cfg, relative_snapshot_days=32., allow_immature=True)
    assert not before.analysis.mature.any()
    assert at.analysis.mature.eq(1).all()
    assert np.array_equal(at.analysis.complete_after_day, at.analysis.assignment_day + 32)
    changed = copy_tables(tables)
    user2 = changed["orders"].user_id == 2
    changed["orders"].loc[user2, ["paid_day", "paid_ingested_day"]] = 7.
    boundary = run_sql_pipeline(changed, cfg)
    assert boundary.analysis.set_index("user_id").loc[2, "paid_purchase_7d"] == 1
    second = (changed["orders"].user_id == 1) & (changed["orders"].order_number == 2)
    changed["orders"].loc[second, ["refund_day", "refund_ingested_day"]] = 30.
    boundary = run_sql_pipeline(changed, cfg)
    assert boundary.analysis.set_index("user_id").loc[1, "refunded_orders_30d"] == 2


def test_fractional_assignment_exact_complete_endpoint(protocol):
    cfg = protocol.scenario("L1_main")
    _, tables = _raw(cfg, n=3000)
    at = run_sql_pipeline(tables, cfg, relative_snapshot_days=32., allow_immature=True)
    assert at.analysis.mature.eq(1).all()
    np.testing.assert_array_equal(at.analysis.asof_day, at.analysis.complete_after_day)
    complete = run_sql_pipeline(tables, cfg)
    assert complete.analysis.mature.eq(1).all()
    assert complete.asof_day == complete.analysis.complete_after_day.max()


def _set_boundary_clock(tables, *, event, window_days, assignment_day):
    """Move one complete user clock while preserving the other factual rows."""
    user_id = 2 if event == "paid" else 1
    for table, columns in (
        ("users", ("assignment_day", "assignment_elapsed_days")),
        ("coupon_assignment", ("assignment_day", "ingested_day")),
        ("user_events", ("event_day", "ingested_day")),
        ("orders", ("assignment_day", "paid_day", "paid_ingested_day", "refund_day", "refund_ingested_day")),
    ):
        mask = tables[table].user_id == user_id
        tables[table].loc[mask, list(columns)] += assignment_day
    mask = (tables["orders"].user_id == user_id) & (tables["orders"].order_number == 1)
    end = assignment_day + window_days
    tables["orders"].loc[mask, event + "_day"] = end
    tables["orders"].loc[mask, event + "_ingested_day"] = end + 2.
    return user_id, mask


def test_all_exact_maximum_arrival_bounds_use_endpoints(protocol):
    cfg = protocol.scenario("L1_main")
    _, tables = _raw(cfg, n=3000)
    for table, event, arrival in (
        ("coupon_assignment", "assignment_day", "ingested_day"),
        ("user_events", "event_day", "ingested_day"),
        ("orders", "paid_day", "paid_ingested_day"),
        ("orders", "refund_day", "refund_ingested_day"),
    ):
        tables[table][arrival] = tables[table][event] + 2.
    # This fixture actually reproduces cancellation in the rejected old test.
    assert ((tables["coupon_assignment"].ingested_day - tables["coupon_assignment"].assignment_day) > 2.).any()
    result = run_sql_pipeline(tables, cfg)
    assert result.visible_assigned_n == 3000 and not result.quality.violations.any()


@pytest.mark.parametrize("event", ["paid", "refund"])
@pytest.mark.parametrize("window_days,assignment_day,arrival_later", [
    (7., .000999000999000999, True), (7., .005994005994005994, False),
    (30., .11930130897996623, True), (30., .00999000999000999, False),
])
def test_closed_window_and_maximum_arrival_combination(protocol, tmp_path, event, window_days, assignment_day, arrival_later):
    cfg = protocol.scenario("L1_main").with_overrides({"business.coupon_returned_on_refund": True})
    _, _, tables = _manual(cfg)
    user_id, mask = _set_boundary_clock(tables, event=event, window_days=window_days, assignment_day=assignment_day)
    raw_arrival = float(tables["orders"].loc[mask, event + "_ingested_day"].iloc[0])
    canonical = assignment_day + (window_days + 2.)
    assert raw_arrival != canonical
    assert (raw_arrival > canonical) == arrival_later
    database_path = tmp_path / "boundary.sqlite"
    at = run_sql_pipeline(tables, cfg, relative_snapshot_days=window_days + 2., allow_immature=True, database_path=database_path)
    row = at.user_outcomes.query("user_id == @user_id and window_days == @window_days").iloc[0]
    assert row.mature == 1 and row.asof_day == row.complete_after_day == canonical
    amount_column = "gross_order_amount_cent" if event == "paid" else "gross_refund_reversal_cent"
    assert row[amount_column] == 10000
    assert row.required_ingestion_day == min(raw_arrival, canonical)
    assert row.required_ingestion_day <= row.asof_day  # the same rolling-availability gate
    with sqlite3.connect(database_path) as connection:
        actual = connection.execute(f"SELECT {event}_ingested_day FROM orders WHERE user_id=? AND order_number=1", (user_id,)).fetchone()[0]
    assert actual == raw_arrival  # normalization applies only to the derived window clock
    # A truly incomplete snapshot still compares raw arrivals, even at one ULP.
    before_time = np.nextafter(min(raw_arrival, canonical), -np.inf)
    before = run_sql_pipeline(tables, cfg, asof_day=before_time, allow_immature=True)
    before_row = before.user_outcomes.query("user_id == @user_id and window_days == @window_days").iloc[0]
    assert before_row.mature == 0 and before_row[amount_column] == 0
    # Strict event-window boundaries exclude the next representable future event.
    after = copy_tables(tables)
    after["orders"].loc[mask, event + "_day"] = np.nextafter(assignment_day + window_days, np.inf)
    after["orders"].loc[mask, event + "_ingested_day"] = after["orders"].loc[mask, event + "_day"] + 2.
    after_result = run_sql_pipeline(after, cfg, relative_snapshot_days=window_days + 2., allow_immature=True)
    after_row = after_result.user_outcomes.query("user_id == @user_id and window_days == @window_days").iloc[0]
    assert after_row.mature == 1 and after_row[amount_column] == 0
    # One ULP beyond the event's own valid arrival endpoint is invalid input.
    invalid = copy_tables(tables)
    invalid["orders"].loc[mask, event + "_ingested_day"] = np.nextafter(raw_arrival, np.inf)
    with pytest.raises(ValueError, match="arrival-time"):
        run_sql_pipeline(invalid, cfg)


@pytest.mark.parametrize("table,event,arrival", [
    ("coupon_assignment", "assignment_day", "ingested_day"),
    ("user_events", "event_day", "ingested_day"),
    ("orders", "paid_day", "paid_ingested_day"),
    ("orders", "refund_day", "refund_ingested_day"),
])
def test_strict_arrival_lower_and_upper_bounds(protocol, table, event, arrival):
    cfg = protocol.scenario("L1_main")
    _, _, tables = _manual(cfg)
    selected = tables[table].index[tables[table][event].notna()][0]
    event_day = tables[table].loc[selected, event]
    lower = copy_tables(tables)
    lower[table].loc[selected, arrival] = np.nextafter(event_day, -np.inf)
    with pytest.raises(sqlite3.IntegrityError):
        run_sql_pipeline(lower, cfg)
    upper = copy_tables(tables)
    upper[table].loc[selected, arrival] = np.nextafter(event_day + 2., np.inf)
    with pytest.raises(ValueError, match="arrival-time"):
        run_sql_pipeline(upper, cfg)


def test_closed_event_lower_bound_and_pre_assignment_rejection(protocol):
    cfg = protocol.scenario("L1_main")
    _, _, tables = _manual(cfg)
    first = (tables["orders"].user_id == 1) & (tables["orders"].order_number == 1)
    tables["orders"].loc[first, ["paid_day", "paid_ingested_day", "refund_day", "refund_ingested_day"]] = 0.
    result = run_sql_pipeline(tables, cfg)
    conversion = result.user_outcomes.query("user_id == 1 and window_days == 7").iloc[0]
    assert conversion.paid_orders == conversion.refunded_orders == 1
    for event in ("paid", "refund"):
        invalid = copy_tables(tables)
        invalid["orders"].loc[first, event + "_day"] = np.nextafter(0., -np.inf)
        with pytest.raises(sqlite3.IntegrityError):
            run_sql_pipeline(invalid, cfg)


def test_memory_persistent_sql_and_fixed_provenance_are_identical(protocol, tmp_path):
    cfg = protocol.scenario("L1_main")
    _, _, tables = _manual(cfg)
    memory = run_sql_pipeline(tables, cfg)
    path = tmp_path / "observed.sqlite"
    disk = run_sql_pipeline(tables, cfg, database_path=path)
    pd.testing.assert_frame_equal(memory.analysis, disk.analysis)
    pd.testing.assert_frame_equal(memory.user_outcomes, disk.user_outcomes)
    assert memory.analysis_sha256 == disk.analysis_sha256
    assert memory.sql_sha256 == disk.sql_sha256
    assert len(disk.config_hash) == len(disk.data_config_hash) == 64
    original_hash = disk.analysis_sha256
    disk.analysis.loc[0, "hist_gmv"] += 1
    assert disk.analysis_sha256 == original_hash
    assert dataframe_sha256(disk.analysis) != original_hash
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        tables_in_database = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables_in_database == set(BUSINESS_TABLES)
        assert connection.execute("SELECT COUNT(*) FROM user_outcomes").fetchone()[0] == 8
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO user_events VALUES ('manual','orphan',999,'browse',0,0)")
    with pytest.raises(FileExistsError):
        run_sql_pipeline(tables, cfg, database_path=path)


@pytest.mark.parametrize("corruption", ["duplicate_assignment", "orphan_order", "unknown_truth", "fractional_money", "bad_design_probability", "missing_assignment"])
def test_schema_and_quality_fail_loudly(protocol, corruption):
    cfg = protocol.scenario("L1_main")
    _, _, tables = _manual(cfg)
    if corruption == "duplicate_assignment":
        tables["coupon_assignment"] = pd.concat([tables["coupon_assignment"], tables["coupon_assignment"].iloc[:1]])
    elif corruption == "orphan_order":
        tables["orders"].loc[0, "user_id"] = 999
    elif corruption == "unknown_truth":
        tables["users"]["true_cate"] = 0.
    elif corruption == "fractional_money":
        tables["orders"]["fulfill_cost_cent"] = tables["orders"].fulfill_cost_cent.astype(float)
        tables["orders"].loc[0, "fulfill_cost_cent"] += .1
    elif corruption == "bad_design_probability":
        tables["coupon_assignment"].loc[0, "design_probability"] = .3
    elif corruption == "missing_assignment":
        tables["coupon_assignment"] = tables["coupon_assignment"].loc[tables["coupon_assignment"].user_id != 3]
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        run_sql_pipeline(tables, cfg)


def test_run_id_prevents_cross_replication_join_and_derived_rows_are_recomputed(protocol):
    cfg = protocol.scenario("L1_main")
    _, _, original = _manual(cfg)
    second = copy_tables(original)
    for frame in second.values():
        frame.loc[:, "run_id"] = "other"
    combined = {name: pd.concat([original[name], second[name]], ignore_index=True) for name in BUSINESS_TABLES}
    first = run_sql_pipeline(combined, cfg)
    assert len(first.analysis) == 8 and len(first.user_outcomes) == 16
    assert first.analysis.groupby("run_id").net_profit_cent.sum().nunique() == 1
    combined["user_outcomes"] = first.user_outcomes.copy()
    combined["user_outcomes"].loc[:, "net_profit_cent"] = -1  # untrusted derived inputs never drive analysis
    again = run_sql_pipeline(combined, cfg)
    assert again.recomputed_input_outcomes
    pd.testing.assert_frame_equal(first.analysis, again.analysis)


def test_aa_treatment_is_virtual_label_but_action_and_coupon_remain_zero(protocol):
    cell = next(c for c in protocol.config.require("scenarios") if c["level"] == "L0" and c["overrides"].get("dgp.virtual_aa_labels"))
    cfg = protocol.scenario(cell["id"])
    _, tables = _raw(cfg)
    result = run_sql_pipeline(tables, cfg)
    assert set(result.analysis.treatment) == {0, 1}
    assert result.analysis.treatment.equals(result.analysis.label)
    assert result.analysis.actual_action.eq(0).all()
    assert result.analysis.coupon_cost_cent.eq(0).all()
    assert result.summaries["groups"].n_total.sum() == len(tables["users"])


def test_sql_production_path_has_no_array_ledger_or_audit_dependency():
    source = Path(__file__).resolve().parents[1] / "src" / "causal_growth" / "data" / "v3_sql.py"
    text = source.read_text(encoding="utf-8")
    assert "import audit_window_ledger" not in text
    assert "from causal_growth.dgp" not in text


def test_policy_arm_denominators_are_not_replaced_by_issued_user_counts(protocol):
    cfg = protocol.scenario("L1_main")
    _, _, tables = _manual(cfg)
    arms = ["selected_targeted_policy", "no_coupon", "random_same_budget", "selected_targeted_policy"]
    assigned = tables["coupon_assignment"]
    assigned["label"] = arms
    assigned["assigned_policy_arm"] = arms
    probabilities = dict(zip(cfg.require("evaluation.independent_validation.arms"), cfg.require("evaluation.independent_validation.arm_probabilities")))
    assigned["policy_arm_probability"] = assigned.assigned_policy_arm.map(probabilities)
    assigned["design_probability"] = np.nan
    result = run_sql_pipeline(tables, cfg)
    groups = result.summaries["groups"].set_index("treatment")
    assert groups.n_total.to_dict() == {"no_coupon": 1, "random_same_budget": 1, "selected_targeted_policy": 2}
    assert groups.loc["random_same_budget", "issued_users"] == 0
    assert result.analysis.design_probability.isna().all()
    np.testing.assert_array_equal(result.analysis.treatment, result.analysis.assigned_policy_arm)


def test_empty_visible_snapshot_keeps_input_denominator_and_rejects_future_labels(protocol):
    cfg = protocol.scenario("L1_main")
    _, _, tables = _manual(cfg)
    result = run_sql_pipeline(tables, cfg, asof_day=-1., allow_immature=True)
    assert result.input_users_n == 4 and result.visible_assigned_n == 0
    assert result.analysis.empty and result.user_outcomes.empty
    assert tuple(result.analysis.columns) == ANALYSIS_COLUMNS
    with pytest.raises(ValueError, match="finite"):
        run_sql_pipeline(tables, cfg, asof_day=float("inf"))
