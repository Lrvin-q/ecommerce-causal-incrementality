"""Independent array ledger for windowed v3 potential-outcome auditing.

Formal analyses must consume the five-table SQL result. This implementation is
an audit comparator, retaining every assigned user and all out-of-window events.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from causal_growth.config import Config


ORDER_COLUMNS = (
    "user_id", "order_id", "order_number", "action", "assignment_day", "paid_day",
    "refund_day", "refunded", "gross_order_amount_cent", "goods_cost_cent",
    "fulfill_cost_cent", "coupon_discount_cent", "coupon_cost_initial_cent",
    "consumer_paid_cent", "goods_cost_recovered_cent", "refund_processing_fee_cent",
    "gross_refund_reversal_cent", "consumer_refund_cent", "coupon_return_cent",
)


def audit_window_ledger(users: pd.DataFrame, orders: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Answer the 7-day purchase/30-day profit question using integer ledger entries.

    Refund postings, including any returned coupon cost, enter only on their
    actual event date. Zero-order users remain present. The input contains one
    realized world, never both potential orders for the same user.
    """
    user_ids = users["user_id"].to_numpy()
    if not users["user_id"].is_unique:
        raise ValueError("assigned user IDs must be unique")
    if set(ORDER_COLUMNS) - set(orders.columns):
        raise ValueError(f"missing order columns: {set(ORDER_COLUMNS) - set(orders.columns)}")
    if not orders["order_id"].is_unique:
        raise ValueError("one realized world must have unique order IDs")
    if not orders["user_id"].isin(user_ids).all():
        raise ValueError("orders reference unassigned users")
    components = (
        "gross_order_amount_cent", "gross_refund_reversal_cent", "goods_cost_cent",
        "goods_cost_recovered_cent", "fulfill_cost_cent", "coupon_cost_cent",
        "refund_processing_fee_cent", "consumer_paid_cent", "consumer_refund_cent",
    )
    result = pd.DataFrame({"user_id": user_ids}).set_index("user_id")
    for name in (*components, "paid_purchase_7d", "any_refund_30d", "paid_orders_30d", "refunded_orders_30d"):
        result[name] = np.zeros(len(result), dtype=np.int64)
    if len(orders):
        money_columns = [c for c in ORDER_COLUMNS if c.endswith("_cent")]
        money = orders[money_columns].to_numpy()
        if not np.isfinite(money).all() or (money < 0).any() or (money != np.floor(money)).any():
            raise ValueError("posted components must be nonnegative integer cents")
        if (orders["paid_day"] < orders["assignment_day"]).any():
            raise ValueError("payment predates assignment")
        refunded = orders["refunded"].astype(bool)
        if (orders.loc[refunded, "refund_day"] < orders.loc[refunded, "paid_day"]).any():
            raise ValueError("refund predates payment")
        if orders.loc[refunded, "refund_day"].isna().any():
            raise ValueError("refunded order lacks event time")
        # Compare stored absolute event times with the declared closed endpoint.
        # Subtracting a fractional assignment day can round an exact endpoint
        # above the window length and incorrectly exclude a valid posting.
        profit_end = orders["assignment_day"] + float(cfg.require("windows.profit_days"))
        convert_end = orders["assignment_day"] + float(cfg.require("windows.convert_days"))
        paid = orders["paid_day"] <= profit_end
        refund = refunded & (orders["refund_day"] <= profit_end)
        purchase = orders["paid_day"] <= convert_end
        posted = pd.DataFrame({"user_id": orders["user_id"].to_numpy()})
        for name in ("gross_order_amount_cent", "goods_cost_cent", "fulfill_cost_cent", "consumer_paid_cent"):
            posted[name] = np.where(paid, orders[name], 0).astype(np.int64)
        for name in ("gross_refund_reversal_cent", "goods_cost_recovered_cent", "refund_processing_fee_cent", "consumer_refund_cent"):
            posted[name] = np.where(refund, orders[name], 0).astype(np.int64)
        posted["coupon_cost_cent"] = (
            np.where(paid, orders["coupon_cost_initial_cent"], 0)
            - np.where(refund, orders["coupon_return_cent"], 0)
        ).astype(np.int64)
        for name, mask in (("paid_orders_30d", paid), ("refunded_orders_30d", refund)):
            posted[name] = np.asarray(mask, dtype=np.int64)
        sums = posted.groupby("user_id", sort=False).sum()
        result.loc[sums.index, sums.columns] = sums
        for name, mask in (("paid_purchase_7d", purchase), ("any_refund_30d", refund)):
            marked = orders.loc[mask, "user_id"].unique()
            result.loc[marked, name] = 1
    result["net_profit_cent"] = (
        result["gross_order_amount_cent"] - result["gross_refund_reversal_cent"]
        - result["goods_cost_cent"] + result["goods_cost_recovered_cent"]
        - result["fulfill_cost_cent"] - result["coupon_cost_cent"]
        - result["refund_processing_fee_cent"]
    )
    result["net_transaction_amount_cent"] = result["gross_order_amount_cent"] - result["gross_refund_reversal_cent"]
    cents = int(cfg.require("business.money.cents_per_yuan"))
    for name in ("net_profit", "coupon_cost", "gross_order_amount", "net_transaction_amount"):
        result[name] = result[f"{name}_cent"] / cents
    return result.reset_index()
