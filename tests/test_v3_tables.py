"""合成数据 / 已知 DGP：五表事实构造和禁止真值注入。"""

import numpy as np
import pandas as pd
import pytest

from causal_growth.data.v3_tables import OUTPUT_COLUMNS, build_raw_tables
from causal_growth.data.v3_quality import validate_tables
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.v3_config import load_v3_protocol


@pytest.mark.parametrize("scenario", ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000", "L0_AA", "L1_AA", "L2_AA", "L3_AA"])
def test_four_layers_and_true_aa_keep_all_assigned_users(scenario):
    protocol = load_v3_protocol()
    # AA stable IDs are obtained from the frozen registry instead of invented aliases.
    if scenario.endswith("_AA"):
        scenario = next(cell["id"] for cell in protocol.config.to_dict()["scenarios"]
                        if cell["level"] == scenario[:2] and cell["formal_repetitions"]["complete_aa"])
    cfg = protocol.scenario(scenario)
    pop = generate_v3_population(cfg, 0, 80)
    source = pop.observation_bundle()
    before = [frame.copy(deep=True) for frame in source]
    tables = build_raw_tables(*source, cfg, run_id=scenario, rep_id=0, stream_prefix=pop.metadata["stream_prefix"])
    assert len(tables["users"]) == len(tables["coupon_assignment"]) == 80
    assert len(tables["orders"]) == len(source[2])
    assert not len(tables["user_outcomes"])
    assert "cart_value" not in tables["users"]
    for name, columns in OUTPUT_COLUMNS.items():
        assert tuple(tables[name]) == columns
    for actual, expected in zip(source, before):
        pd.testing.assert_frame_equal(actual, expected)
    if cfg.require("dgp.virtual_aa_labels"):
        assert tables["coupon_assignment"].actual_action.eq(0).all()
        assert tables["coupon_assignment"].coupon_face_cent.eq(0).all()
        assert set(tables["coupon_assignment"].label) == {0, 1}
    validate_tables(tables, cfg, stage="raw")


def test_log_cap_records_missing_eligibility_cart_and_does_not_invent_sku():
    cfg = load_v3_protocol().scenario("L0_P_main")
    pop = generate_v3_population(cfg, 0, 5)
    users, assigned, orders = pop.observation_bundle()
    cap = int(cfg.require("data.event_log_cap"))
    users["browse_depth"] = [0, 1, cap - 1, cap, cap + 5]
    tables = build_raw_tables(users, assigned, orders, cfg, run_id="cap", rep_id=0, stream_prefix=pop.metadata["stream_prefix"])
    np.testing.assert_array_equal(tables["users"].event_retained_count, [1, 2, cap, cap, cap])
    np.testing.assert_array_equal(tables["users"].event_truncated_count, [0, 0, 0, 1, 6])
    absent_cart = tables["user_events"].loc[tables["user_events"].user_id == users.user_id.iloc[-1]]
    assert not absent_cart.event_type.eq("cart").any()
    assert "sku_id" not in tables["user_events"]


def test_empty_order_population_and_zero_amount_order_remain_valid():
    cfg = load_v3_protocol().scenario("L0_P_main").with_overrides({"dgp.l0.baseline_purchase_probability": 1., "dgp.l0.purchase_increment": 0.})
    pop = generate_v3_population(cfg, 0, 8)
    users, assigned, orders = pop.observation_bundle()
    empty = build_raw_tables(users, assigned, orders.iloc[:0], cfg, run_id="empty", rep_id=0, stream_prefix=pop.metadata["stream_prefix"])
    assert len(empty["users"]) == 8 and not len(empty["orders"])
    uid = users.user_id.iloc[0]
    users.loc[users.user_id == uid, ["cart_value_cent", "cart_value"]] = 0
    for column in (c for c in orders if c.endswith("_cent") and c != "fulfill_cost_cent"):
        orders.loc[orders.user_id == uid, column] = 0
    zero = build_raw_tables(users, assigned, orders, cfg, run_id="zero", rep_id=0, stream_prefix=pop.metadata["stream_prefix"])
    assert zero["orders"].loc[zero["orders"].user_id == uid, "gross_order_amount_cent"].eq(0).all()
    assert zero["orders"].loc[zero["orders"].user_id == uid, "fulfill_cost_cent"].gt(0).all()


@pytest.mark.parametrize("where,column", [(0, "audit_u"), (1, "true_propensity"), (2, "cate_profit")])
def test_builder_rejects_unexpected_truth_columns(where, column):
    cfg = load_v3_protocol().scenario("L0_P_main")
    pop = generate_v3_population(cfg, 0, 20)
    source = list(pop.observation_bundle())
    source[where][column] = 0
    with pytest.raises(ValueError, match="白名单"):
        build_raw_tables(*source, cfg, run_id="bad", rep_id=0, stream_prefix=pop.metadata["stream_prefix"])


def test_builder_rejects_disagreeing_cart_alias():
    cfg = load_v3_protocol().scenario("L0_P_main")
    pop = generate_v3_population(cfg, 0, 20)
    users, assigned, orders = pop.observation_bundle()
    users.loc[0, "cart_value"] += 1
    with pytest.raises(ValueError, match="重复表示"):
        build_raw_tables(users, assigned, orders, cfg, run_id="bad", rep_id=0, stream_prefix=pop.metadata["stream_prefix"])


def test_builder_does_not_truncate_fractional_action():
    cfg = load_v3_protocol().scenario("L0_P_main")
    pop = generate_v3_population(cfg, 0, 8)
    users, assigned, orders = pop.observation_bundle()
    assigned["actual_action"] = assigned.actual_action.astype(float)
    assigned.loc[0, "actual_action"] = 1.5
    with pytest.raises(ValueError, match="二元整数"):
        build_raw_tables(users, assigned, orders, cfg, run_id="bad", rep_id=0, stream_prefix=pop.metadata["stream_prefix"])
