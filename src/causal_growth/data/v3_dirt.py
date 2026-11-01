"""合成数据 / 已知 DGP：独立污染流与仅按事件键实施的确定性去重。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from causal_growth.config import Config
from causal_growth.data.v3_tables import copy_tables
from causal_growth.data.v3_quality import _same_event_payload, validate_tables
from causal_growth.rng import child_rng
from causal_growth.v3_data_config import load_v3_data_config


@dataclass(frozen=True)
class StageResult:
    """污染或清洗输出；计数及技术配置哈希可直接写入运行manifest。"""

    tables: dict[str, pd.DataFrame]
    counts: dict[str, int]
    data_config_hash: str


def inject_dirt(
    tables: Mapping[str, pd.DataFrame], cfg: Config, *, rep_id: int, stream_prefix: str,
) -> StageResult:
    """注入声明的MAR/倍率异常/重复/延迟，不改事件事实、金额账或分配分母。"""
    validate_tables(tables, cfg, stage="raw")
    if len(tables["user_outcomes"]):
        raise ValueError("污染必须在SQL物化前实施")
    out = copy_tables(tables)
    data_cfg = load_v3_data_config()
    enabled = bool(cfg.require("data.dirty.enabled"))
    seed = int(cfg.require("project.master_seed"))

    def draw(name: str, n: int) -> np.ndarray:
        return child_rng(seed, f"{stream_prefix}.dirty.{name}", rep_id).random(n)

    users, assignments, orders, events = (out[name] for name in ("users", "coupon_assignment", "orders", "user_events"))
    missing_rates = cfg.section("data.dirty.cart_missing_by_channel")
    probabilities = users.channel.map(missing_rates).to_numpy(dtype=float) * float(cfg.require("data.dirty.missing_rate_multiplier"))
    if np.any(~np.isfinite(probabilities)) or np.any((probabilities < 0) | (probabilities > 1)):
        raise ValueError("MAR概率缺失或不在[0,1]")
    fraud_rate = float(cfg.require("data.dirty.fraud_user_rate"))
    duplicate_rate = float(cfg.require("data.dirty.duplicate_event_rate"))
    delay_hours = float(cfg.require("data.dirty.ingestion_delay_max_hours"))
    if not 0 <= fraud_rate <= 1 or not 0 <= duplicate_rate <= 1 or delay_hours < 0:
        raise ValueError("污染概率/延迟配置非法")
    missing = (draw("cart_missing", len(users)) < probabilities) & enabled
    fraud = (draw("hist_fraud", len(users)) < fraud_rate) & enabled
    users.loc[missing, "cart_value_cent"] = pd.NA
    multiplier = float(cfg.require("data.dirty.fraud_hist_gmv_multiplier"))
    if not np.isfinite(multiplier) or multiplier < 0:
        raise ValueError("历史GMV异常倍率非法")
    users.loc[fraud, "hist_gmv"] = users.loc[fraud, "hist_gmv"] * multiplier
    delay_days = delay_hours / float(data_cfg.require("time.hours_per_day")) if enabled else 0.0
    user_keys = pd.MultiIndex.from_frame(users[["run_id", "user_id"]])
    event_positions = user_keys.get_indexer(pd.MultiIndex.from_frame(events[["run_id", "user_id"]]))
    event_order = np.lexsort((events.event_id.to_numpy(dtype=str), events.event_day.to_numpy(), event_positions))
    event_delays = np.empty(len(events))
    event_delays[event_order] = draw("event_ingestion", len(events)) * delay_days
    events["ingested_day"] = events.event_day + event_delays
    assignment_positions = user_keys.get_indexer(pd.MultiIndex.from_frame(assignments[["run_id", "user_id"]]))
    assignments["ingested_day"] = assignments.assignment_day + draw("assignment_ingestion", len(users))[assignment_positions] * delay_days
    # 对全部分配用户×潜在订单序号抽延迟，再映射到事实订单。
    # 不按factual_orders的行号抽样，否则lambda_T改变订单选择后会破坏配对。
    order_positions = user_keys.get_indexer(pd.MultiIndex.from_frame(orders[["run_id", "user_id"]]))
    for number in (1, 2):
        selected = orders.order_number.to_numpy() == number
        payment_delay = draw(f"orders.{number}.paid_ingestion", len(users)) * delay_days
        refund_delay = draw(f"orders.{number}.refund_ingestion", len(users)) * delay_days
        positions = order_positions[selected]
        orders.loc[selected, "paid_ingested_day"] = orders.loc[selected, "paid_day"] + payment_delay[positions]
        # NaN退款时间与NaN入库时间同步保留；窗外退款仍存在。
        orders.loc[selected, "refund_ingested_day"] = orders.loc[selected, "refund_day"] + refund_delay[positions]
    duplicate = np.empty(len(events), dtype=bool)
    duplicate[event_order] = (draw("event_duplicate", len(events)) < duplicate_rate) & enabled
    repeated = events.loc[duplicate].copy(deep=True)
    # 重复上报保留同一事件身份与事实，入库时间也可完全相同。
    out["user_events"] = pd.concat([events, repeated], ignore_index=True)
    counts = {
        "users": len(users), "cart_missing_injected": int(missing.sum()), "hist_fraud_injected": int(fraud.sum()),
        "event_duplicates_injected": int(duplicate.sum()), "events_before": len(events), "events_after": len(out["user_events"]),
        "events_delayed": int((events.ingested_day > events.event_day).sum()),
        "assignments_delayed": int((assignments.ingested_day > assignments.assignment_day).sum()),
        "payments_delayed": int((orders.paid_ingested_day > orders.paid_day).sum()),
        "refunds_delayed": int((orders.refund_ingested_day > orders.refund_day).sum()),
        "event_truncated": int(users.event_truncated_count.sum()),
    }
    validate_tables(out, cfg, stage="dirty")
    return StageResult(out, counts, data_cfg.hash(64))


def deduplicate_events(tables: Mapping[str, pd.DataFrame], cfg: Config) -> StageResult:
    """只去重事件，保留最早入库记录；冲突载荷失败，MAR与异常不在此拟合修复。"""
    validate_tables(tables, cfg, stage="dirty")
    out = copy_tables(tables)
    events = out["user_events"]
    _same_event_payload(events)
    before = len(events)
    # stable保证完全相同的重复行有确定的保留规则，不改变业务事件身份。
    out["user_events"] = events.sort_values("ingested_day", kind="stable").drop_duplicates(
        ["run_id", "event_id"], keep="first",
    ).sort_values(["run_id", "user_id", "event_day", "event_id"], kind="stable").reset_index(drop=True)
    counts = {
        "events_before": before, "events_after": len(out["user_events"]),
        "duplicate_events_removed": before - len(out["user_events"]),
        "cart_missing_retained": int(out["users"].cart_value_cent.isna().sum()),
        "users_removed": 0, "refund_orders_removed": 0,
    }
    validate_tables(out, cfg, stage="clean")
    return StageResult(out, counts, load_v3_data_config().hash(64))
