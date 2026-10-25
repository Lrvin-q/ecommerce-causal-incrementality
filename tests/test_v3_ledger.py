"""Mechanism audit tests with refunds and repeat orders on both sides of day 30."""

import numpy as np
import pandas as pd
import pytest

from causal_growth.dgp.v3_ledger import ORDER_COLUMNS, audit_window_ledger
from causal_growth.v3_config import load_v3_protocol


def _case() -> tuple[pd.DataFrame, pd.DataFrame]:
    users = pd.DataFrame({"user_id": [0, 1, 2]})
    rows = []
    for uid, oid, number, paid, refund in ((0, 0, 1, 1.0, 20.0), (1, 2, 1, 2.0, 31.0), (1, 3, 2, 32.0, 40.0)):
        row = dict.fromkeys(ORDER_COLUMNS, 0)
        row.update(user_id=uid, order_id=oid, order_number=number, action=1,
                   assignment_day=0.0, paid_day=paid, refund_day=refund, refunded=True,
                   gross_order_amount_cent=10000, goods_cost_cent=6800,
                   fulfill_cost_cent=500, coupon_discount_cent=1000,
                   coupon_cost_initial_cent=1000, consumer_paid_cent=9000,
                   goods_cost_recovered_cent=5780, refund_processing_fee_cent=100,
                   gross_refund_reversal_cent=10000, consumer_refund_cent=9000,
                   coupon_return_cent=1000)
        rows.append(row)
    return users, pd.DataFrame(rows)


def test_late_refund_and_repeat_cannot_enter_mature_profit_early() -> None:
    users, orders = _case()
    cfg = load_v3_protocol().scenario("L1_main")
    out = audit_window_ledger(users, orders, cfg)
    # Returned coupon cost is posted only for the day-20 refund, not day 31.
    assert out.net_profit_cent.tolist() == [-1620, 1700, 0]
    assert out.coupon_cost_cent.tolist() == [0, 1000, 0]
    assert out.any_refund_30d.tolist() == [1, 0, 0]
    assert out.paid_orders_30d.tolist() == [1, 1, 0]
    assert out.paid_purchase_7d.tolist() == [1, 1, 0]
    assert len(orders) == 3  # out-of-window events are retained in the source


def test_coupon_retained_after_refund_and_zero_users_are_not_dropped() -> None:
    users, orders = _case()
    orders["coupon_return_cent"] = 0
    out = audit_window_ledger(users, orders, load_v3_protocol().scenario("L1_main"))
    assert out.net_profit_cent.tolist() == [-2620, 1700, 0]
    assert len(out) == len(users)


def test_window_boundaries_are_inclusive_and_purchase_is_separate() -> None:
    users, orders = _case()
    orders.loc[0, ["paid_day", "refund_day"]] = [7, 30]
    orders.loc[1, ["paid_day", "refund_day"]] = [8, 31]
    out = audit_window_ledger(users, orders, load_v3_protocol().scenario("L1_main"))
    assert out.paid_purchase_7d.tolist() == [1, 0, 0]
    assert out.any_refund_30d.tolist() == [1, 0, 0]


def test_empty_orders_keep_all_assigned_users() -> None:
    users, orders = _case()
    out = audit_window_ledger(users, orders.iloc[:0], load_v3_protocol().scenario("L1_main"))
    assert len(out) == 3
    assert out.net_profit_cent.sum() == 0


@pytest.mark.parametrize(("days", "assignment_day"), [(7, 1.3), (30, 6.7928292744855945)])
def test_fractional_assignment_closed_endpoints_and_one_ulp_outside(days: int, assignment_day: float) -> None:
    users, orders = _case()
    orders["assignment_day"] = assignment_day
    endpoint = orders.assignment_day + days
    orders["paid_day"] = endpoint
    orders["refund_day"] = endpoint
    cfg = load_v3_protocol().scenario("L1_main").with_overrides({
        "windows.convert_days": days, "windows.profit_days": days,
    })
    assert ((orders.paid_day - orders.assignment_day) > days).any()
    inside = audit_window_ledger(users, orders, cfg)
    assert inside.paid_orders_30d.tolist() == [1, 2, 0]
    assert inside.refunded_orders_30d.tolist() == [1, 2, 0]
    assert inside.paid_purchase_7d.tolist() == [1, 1, 0]
    orders["paid_day"] = np.nextafter(endpoint, np.inf)
    orders["refund_day"] = orders.paid_day
    outside = audit_window_ledger(users, orders, cfg)
    assert outside.paid_orders_30d.sum() == 0
    assert outside.refunded_orders_30d.sum() == 0
    assert outside.paid_purchase_7d.sum() == 0
    assert outside.net_profit_cent.sum() == 0


@pytest.mark.parametrize("issue", ["duplicate", "unknown_user", "negative", "fractional", "missing_refund_time"])
def test_invalid_ledger_fails_loudly(issue: str) -> None:
    users, orders = _case()
    if issue == "duplicate":
        orders.loc[1, "order_id"] = orders.loc[0, "order_id"]
    elif issue == "unknown_user":
        orders.loc[0, "user_id"] = 999
    elif issue == "negative":
        orders.loc[0, "gross_order_amount_cent"] = -1
    elif issue == "fractional":
        orders["gross_order_amount_cent"] = orders["gross_order_amount_cent"].astype(float)
        orders.loc[0, "gross_order_amount_cent"] = 1.5
    else:
        orders.loc[0, "refund_day"] = np.nan
    with pytest.raises(ValueError):
        audit_window_ledger(users, orders, load_v3_protocol().scenario("L1_main"))
