"""合成数据 / 已知 DGP：仅由可观测事实构造五表，主分析利润留给SQL。"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from causal_growth.config import Config
from causal_growth.rng import child_rng
from causal_growth.v3_data_config import load_v3_data_config


SOURCE_USER_COLUMNS = (
    "user_id", "is_new", "hist_gmv", "cart_value_cent", "browse_depth", "channel",
    "assignment_week", "assignment_day", "assignment_elapsed_days", "split",
)
SOURCE_ASSIGNMENT_COLUMNS = ("user_id", "actual_action", "label", "design_probability")
OPTIONAL_ASSIGNMENT_COLUMNS = ("assigned_policy_arm", "policy_arm_probability")
SOURCE_ORDER_COLUMNS = (
    "user_id", "order_id", "order_number", "action", "assignment_day", "paid_day", "refund_day", "refunded",
    "gross_order_amount_cent", "goods_cost_cent", "fulfill_cost_cent", "coupon_discount_cent",
    "coupon_cost_initial_cent", "consumer_paid_cent", "goods_cost_recovered_cent", "refund_processing_fee_cent",
    "gross_refund_reversal_cent", "consumer_refund_cent", "coupon_return_cent",
)
OUTCOME_MONEY_COLUMNS = tuple(f"{name}_cent" for name in (
    "gross_order_amount", "gross_refund_reversal", "goods_cost", "goods_cost_recovered", "fulfill_cost",
    "coupon_cost_initial", "coupon_return", "coupon_cost", "refund_processing_fee", "consumer_paid",
    "consumer_refund", "net_profit", "net_transaction_amount",
))
OUTPUT_COLUMNS: dict[str, tuple[str, ...]] = {
    "users": ("run_id", *SOURCE_USER_COLUMNS, "event_retained_count", "event_truncated_count"),
    "user_events": ("run_id", "event_id", "user_id", "event_type", "event_day", "ingested_day"),
    "coupon_assignment": ("run_id", *SOURCE_ASSIGNMENT_COLUMNS, *OPTIONAL_ASSIGNMENT_COLUMNS,
                          "assignment_day", "ingested_day", "coupon_face_cent"),
    "orders": ("run_id", *SOURCE_ORDER_COLUMNS, "paid_ingested_day", "refund_ingested_day"),
    "user_outcomes": (
        "run_id", "user_id", "window_type", "window_days", "window_end_day", "asof_day", "mature",
        "converted", "refunded", "paid_orders", "refunded_orders", *OUTCOME_MONEY_COLUMNS,
        "required_ingestion_day", "complete_after_day",
    ),
}


def empty_table(name: str) -> pd.DataFrame:
    """返回已声明schema的空表，尤其供SQL后续物化user_outcomes。"""
    if name not in OUTPUT_COLUMNS:
        raise ValueError(f"unknown v3 table {name}")
    text = {"run_id", "event_id", "event_type", "channel", "split", "label", "assigned_policy_arm", "window_type"}
    floating = {"hist_gmv", "design_probability", "policy_arm_probability", "window_days"}
    return pd.DataFrame({
        column: pd.Series(dtype=("object" if column in text else "float64" if column in floating or column.endswith("_day") or column == "assignment_elapsed_days"
                                 else "Int64" if column == "cart_value_cent" else "int64"))
        for column in OUTPUT_COLUMNS[name]
    })


def copy_tables(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """复制五表以保持raw/dirty/clean阶段不发生就地修改。"""
    if set(tables) != set(OUTPUT_COLUMNS):
        raise ValueError("v3输入必须恰好为五张已声明表")
    if not all(isinstance(frame, pd.DataFrame) for frame in tables.values()):
        raise TypeError("v3五表值必须为DataFrame")
    return {name: frame.copy(deep=True) for name, frame in tables.items()}


def _source_schema(frame: pd.DataFrame, required: tuple[str, ...], optional: tuple[str, ...], name: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name}只接受观测DataFrame")
    if frame.columns.duplicated().any():
        raise ValueError(f"{name}存在重复列名")
    missing = set(required) - set(frame)
    extra = set(frame) - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"{name}违反观测白名单：missing={sorted(missing)},extra={sorted(extra)}")


def _events(users: pd.DataFrame, cfg: Config, data_cfg: Config, rep_id: int, stream_prefix: str) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    if data_cfg.require("events.cap_scope") != "all_pre_assignment_events_first_chronological":
        raise ValueError("未实现的数据事件cap口径")
    depth = users["browse_depth"].to_numpy(dtype=np.int64)
    cap = int(cfg.require("data.event_log_cap"))
    include_cart = bool(data_cfg.require("events.include_eligibility_cart_event"))
    totals = depth + int(include_cart)
    retained = np.minimum(totals, cap)
    if not totals.sum():
        return empty_table("user_events"), retained, totals - retained
    owner = np.repeat(np.arange(len(users)), totals)
    starts = np.repeat(np.cumsum(totals) - totals, totals)
    position = np.arange(len(owner)) - starts
    is_cart = position == depth[owner]
    uniforms = child_rng(int(cfg.require("project.master_seed")), f"{stream_prefix}.tables.pre_assignment_events", rep_id).random(len(owner))
    days = users.assignment_day.to_numpy()[owner] - uniforms * float(data_cfg.require("events.pre_assignment_window_days"))
    days[is_cart] = users.assignment_day.to_numpy()[owner[is_cart]] + float(data_cfg.require("events.cart_event_offset_days"))
    order = np.lexsort((position, days, owner))
    ranks = np.arange(len(owner)) - starts
    keep = ranks < cap
    selected = order[keep]
    ids = users.user_id.to_numpy()[owner[selected]]
    frame = pd.DataFrame({
        "run_id": users.run_id.to_numpy()[owner[selected]],
        "event_id": [f"{user_id}:{sequence}" for user_id, sequence in zip(ids, ranks[keep], strict=True)],
        "user_id": ids,
        "event_type": np.where(is_cart[selected], data_cfg.require("events.event_types.cart"), data_cfg.require("events.event_types.browse")),
        "event_day": days[selected], "ingested_day": days[selected],
    })
    # 这是已合资格人群的合成日志。首cap条可能不含末尾cart事件；资格由上游提供，
    # 不通过补造cart日志或更改cap来掩盖截断，也不声称证明SKU集合包含关系。
    return frame.loc[:, OUTPUT_COLUMNS["user_events"]], retained, totals - retained


def build_raw_tables(
    users: pd.DataFrame, assignments: pd.DataFrame, factual_orders: pd.DataFrame, cfg: Config, *,
    run_id: str, rep_id: int, stream_prefix: str,
) -> dict[str, pd.DataFrame]:
    """回答五表能否只由事实重建：不接收审计状态、不计算主分析利润、保留所有分配者。"""
    _source_schema(users, SOURCE_USER_COLUMNS, ("cart_value",), "users")
    _source_schema(assignments, SOURCE_ASSIGNMENT_COLUMNS, OPTIONAL_ASSIGNMENT_COLUMNS, "assignments")
    _source_schema(factual_orders, SOURCE_ORDER_COLUMNS, (), "factual_orders")
    if not isinstance(run_id, str) or not run_id.strip() or not isinstance(stream_prefix, str) or not stream_prefix.strip():
        raise ValueError("run_id与stream_prefix必须为非空字符串")
    if isinstance(rep_id, bool) or not isinstance(rep_id, (int, np.integer)) or rep_id < 0:
        raise ValueError("rep_id必须为非负整数")
    if users.user_id.duplicated().any() or assignments.user_id.duplicated().any() or set(users.user_id) != set(assignments.user_id):
        raise ValueError("用户与分配必须逐人一一对应")
    if not assignments.actual_action.isin((0, 1)).all():
        raise ValueError("输入actual_action必须为二元整数，不能截断转换")
    integer_features = users[["user_id", "is_new", "cart_value_cent", "browse_depth", "assignment_week"]].to_numpy(dtype=float)
    if not np.isfinite(integer_features).all() or np.any(integer_features != np.floor(integer_features)) or (users.browse_depth < 0).any():
        raise ValueError("原始用户整数特征非法")
    unit = int(cfg.require("business.money.cents_per_yuan"))
    if "cart_value" in users and not np.allclose(users.cart_value, users.cart_value_cent / unit, atol=0, rtol=0):
        raise ValueError("输入cart重复表示不一致，不能任选一列")
    data_cfg = load_v3_data_config()
    output = {name: empty_table(name) for name in OUTPUT_COLUMNS}
    output["users"] = users.loc[:, SOURCE_USER_COLUMNS].copy(deep=True)
    output["users"].insert(0, "run_id", run_id)
    events, retained, truncated = _events(output["users"], cfg, data_cfg, rep_id, stream_prefix)
    output["users"]["event_retained_count"] = retained
    output["users"]["event_truncated_count"] = truncated
    output["users"]["cart_value_cent"] = output["users"]["cart_value_cent"].astype("Int64")
    output["user_events"] = events
    assigned = assignments.copy(deep=True)
    for name in OPTIONAL_ASSIGNMENT_COLUMNS:
        if name not in assigned:
            assigned[name] = None if name == "assigned_policy_arm" else np.nan
    assigned.insert(0, "run_id", run_id)
    assigned["assignment_day"] = assigned.user_id.map(users.set_index("user_id").assignment_day)
    assigned["ingested_day"] = assigned.assignment_day
    face = float(cfg.require("business.coupon_reference_face")) * unit
    if face != np.floor(face):
        raise ValueError("券面额必须为整数分")
    assigned["actual_action"] = assigned.actual_action.astype(np.int64)
    assigned["coupon_face_cent"] = assigned.actual_action * int(face)
    output["coupon_assignment"] = assigned.loc[:, OUTPUT_COLUMNS["coupon_assignment"]]
    orders = factual_orders.copy(deep=True)
    orders.insert(0, "run_id", run_id)
    for column in ("user_id", "order_id", "order_number", "action", "refunded", *(c for c in SOURCE_ORDER_COLUMNS if c.endswith("_cent"))):
        if len(orders) and (orders[column].isna().any() or np.any(orders[column] != np.floor(orders[column].astype(float)))):
            raise ValueError(f"订单{column}不是整数事实")
        orders[column] = orders[column].astype(np.int64)
    for column in ("assignment_day", "paid_day", "refund_day"):
        orders[column] = orders[column].astype(float)
    orders["paid_ingested_day"] = orders.paid_day
    orders["refund_ingested_day"] = orders.refund_day
    output["orders"] = orders.loc[:, OUTPUT_COLUMNS["orders"]]
    from causal_growth.data.v3_quality import validate_tables

    validate_tables(output, cfg, stage="raw")
    return output
