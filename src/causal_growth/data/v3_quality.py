"""合成数据 / 已知 DGP：五表事实、时窗与整数账务的硬门禁。"""

from __future__ import annotations

from fractions import Fraction
from typing import Mapping

import numpy as np
import pandas as pd

from causal_growth.config import Config
from causal_growth.data.v3_tables import OUTCOME_MONEY_COLUMNS, OUTPUT_COLUMNS
from causal_growth.v3_data_config import load_v3_data_config


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _integers(frame: pd.DataFrame, columns: list[str], *, allow_negative: bool = False, nullable: bool = False) -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float, na_value=np.nan)
        valid = ~np.isnan(values) if nullable else np.ones(len(values), dtype=bool)
        _require(bool(np.isfinite(values[valid]).all()), f"{column}必须是有限整数")
        _require(bool(np.all(values[valid] == np.floor(values[valid]))), f"{column}不是整数")
        if not allow_negative:
            _require(bool(np.all(values[valid] >= 0)), f"{column}不能为负")


def _keys(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.MultiIndex:
    return pd.MultiIndex.from_frame(frame.loc[:, columns])


def _round_component(values: pd.Series, rate: float) -> np.ndarray:
    numerator, denominator = Fraction(str(rate)).as_integer_ratio()
    integer = values.to_numpy(dtype=np.int64)
    _require(not len(integer) or int(integer.max()) * numerator * 2 + denominator <= np.iinfo(np.int64).max,
             "金额超出独立分币校验的整数范围")
    return (integer * numerator * 2 + denominator) // (2 * denominator)


def _same_event_payload(events: pd.DataFrame) -> None:
    if events.duplicated(["run_id", "event_id"]).any():
        distinct = events.groupby(["run_id", "event_id"], dropna=False)[["user_id", "event_type", "event_day"]].nunique(dropna=False)
        _require(bool((distinct <= 1).all().all()), "重复event_id的业务载荷冲突")


def validate_tables(
    tables: Mapping[str, pd.DataFrame], cfg: Config, *, stage: str = "clean", require_outcomes: bool = False,
) -> dict[str, int]:
    """回答五表是否满足分母、事实与时窗口径；只容许声明的污染，任何失配均抛异常。"""
    _require(stage in {"raw", "dirty", "clean"}, "未知数据阶段")
    _require(set(tables) == set(OUTPUT_COLUMNS), "必须恰好包含五张业务表")
    for name, columns in OUTPUT_COLUMNS.items():
        frame = tables[name]
        _require(isinstance(frame, pd.DataFrame), f"{name}必须是DataFrame")
        _require(not frame.columns.duplicated().any(), f"{name}重复列名")
        _require(set(frame) == set(columns), f"{name}违反观测列白名单")
        _require(bool(frame.run_id.map(lambda x: isinstance(x, str) and bool(x.strip())).all()), f"{name}缺少run_id")
        _integers(frame, ["user_id"], allow_negative=True)
        _require(not frame[["run_id", "user_id"]].isna().any().any(), f"{name}实体键缺失")
    users, assignments, orders, events, outcomes = (tables[n] for n in ("users", "coupon_assignment", "orders", "user_events", "user_outcomes"))
    for frame, key, name in (
        (users, ("run_id", "user_id"), "users"), (assignments, ("run_id", "user_id"), "coupon_assignment"),
        (orders, ("run_id", "order_id"), "orders"), (outcomes, ("run_id", "user_id", "window_type"), "user_outcomes"),
    ):
        _require(not frame[list(key)].isna().any().any() and not frame.duplicated(list(key)).any(), f"{name}主键非法/重复")
    user_keys = _keys(users, ("run_id", "user_id"))
    _require(len(assignments) == len(users) and bool(_keys(assignments, ("run_id", "user_id")).isin(user_keys).all()), "用户与分配分母不一致")
    for name in ("orders", "user_events", "user_outcomes"):
        _require(bool(_keys(tables[name], ("run_id", "user_id")).isin(user_keys).all()), f"{name}引用未分配用户或错误run_id")
    _integers(users, ["is_new", "browse_depth", "assignment_week", "event_retained_count", "event_truncated_count"])
    _require((users.assignment_week >= 1).all(), "分配周从1开始")
    _integers(users, ["cart_value_cent"], nullable=stage != "raw")
    _require(users.is_new.isin((0, 1)).all(), "is_new必须二元")
    _require(users.channel.isin(tuple(cfg.require("business.channels"))).all(), "未知用户渠道")
    _require(users.split.isin(("train", "validation", "test", "pending_stratified")).all(), "未知用户拆分标签")
    _require(np.isfinite(users.hist_gmv.to_numpy(dtype=float)).all() and (users.hist_gmv >= 0).all(), "历史GMV非法")
    for column in ("assignment_day", "assignment_elapsed_days"):
        _require(np.isfinite(users[column].to_numpy(dtype=float)).all(), f"用户{column}非法")
    _require(np.array_equal(users.assignment_day.to_numpy(), users.assignment_elapsed_days.to_numpy()), "用户分配日和日历elapsed不一致")
    _integers(assignments, ["actual_action", "coupon_face_cent"])
    _require(assignments.actual_action.isin((0, 1)).all(), "actual_action必须二元")
    join = assignments.merge(users[["run_id", "user_id", "assignment_day"]], on=["run_id", "user_id"], validate="one_to_one", suffixes=("", "_user"))
    _require(np.array_equal(join.assignment_day.to_numpy(), join.assignment_day_user.to_numpy()), "分配表时间与用户不一致")
    _require(np.isfinite(assignments.ingested_day.to_numpy(dtype=float)).all() and (assignments.ingested_day >= assignments.assignment_day).all(), "分配入库早于事件")
    face = float(cfg.require("business.coupon_reference_face")) * int(cfg.require("business.money.cents_per_yuan"))
    _require((assignments.coupon_face_cent == assignments.actual_action * face).all(), "券面额与实际动作不符")
    policy = assignments.assigned_policy_arm.notna()
    _require(assignments.loc[~policy, "policy_arm_probability"].isna().all(), "历史分配混入政策臂概率")
    if policy.any():
        known_arms = dict(zip(cfg.require("evaluation.independent_validation.arms"), cfg.require("evaluation.independent_validation.arm_probabilities"), strict=True))
        _require(assignments.loc[policy, "assigned_policy_arm"].isin(known_arms).all(), "未知验证政策臂")
        _require(np.allclose(assignments.loc[policy, "policy_arm_probability"], assignments.loc[policy, "assigned_policy_arm"].map(known_arms), atol=float(cfg.require("design.numerical.probability_tolerance")), rtol=0), "政策臂概率不符")
        _require(assignments.loc[policy, "design_probability"].isna().all(), "政策臂随机概率不得冒充逐人发券概率")
        _require((assignments.loc[policy, "label"] == assignments.loc[policy, "assigned_policy_arm"]).all(), "验证标签与政策臂不符")
        _require((assignments.loc[assignments.assigned_policy_arm == "no_coupon", "actual_action"] == 0).all(), "no_coupon臂实际发券")
    historical = assignments.loc[~policy]
    _require(historical.label.isin((0, 1)).all(), "历史分析标签必须二元")
    if bool(cfg.require("dgp.virtual_aa_labels")):
        _require((historical.actual_action == int(cfg.require("design.aa.actual_action"))).all(), "真正AA动作发生分歧")
        probability = float(cfg.require("design.aa.virtual_label_probability"))
    else:
        _require((historical.label == historical.actual_action).all(), "非AA标签与实际动作不同")
        probability = float(cfg.require("design.treatment_probability"))
    if str(cfg.require("dgp.profile")) == "l3" and not cfg.require("dgp.virtual_aa_labels"):
        _require(historical.design_probability.isna().all(), "L3真实倾向泄漏到设计概率")
    else:
        _require(np.allclose(historical.design_probability.to_numpy(dtype=float), probability, atol=float(cfg.require("design.numerical.probability_tolerance")), rtol=0), "随机分配概率不符")
    _validate_events(events, users, cfg, stage)
    _validate_orders(orders, users, assignments, cfg)
    _validate_arrival_bounds(tables, cfg, stage)
    _validate_outcomes(outcomes, users, assignments, cfg, require_outcomes)
    return {
        "users": len(users), "assignments": len(assignments), "orders": len(orders), "events": len(events), "outcomes": len(outcomes),
        "cart_missing": int(users.cart_value_cent.isna().sum()), "event_duplicate_rows": int(events.duplicated(["run_id", "event_id"]).sum()),
        "event_truncated": int(users.event_truncated_count.sum()), "refund_orders_retained": int(orders.refunded.sum()),
    }


def _validate_arrival_bounds(tables: Mapping[str, pd.DataFrame], cfg: Config, stage: str) -> None:
    data_cfg = load_v3_data_config()
    maximum = float(cfg.require("data.dirty.ingestion_delay_max_hours")) / float(data_cfg.require("time.hours_per_day"))
    if stage == "raw" or not bool(cfg.require("data.dirty.enabled")):
        maximum = 0.0
    for table, event, arrived in (
        ("user_events", "event_day", "ingested_day"), ("coupon_assignment", "assignment_day", "ingested_day"),
        ("orders", "paid_day", "paid_ingested_day"), ("orders", "refund_day", "refund_ingested_day"),
    ):
        frame = tables[table]
        valid = frame[event].notna()
        event_time = frame.loc[valid, event].to_numpy(dtype=float)
        arrival_time = frame.loc[valid, arrived].to_numpy(dtype=float)
        _require(np.all(arrival_time <= event_time + maximum), f"{table}.{arrived}超出声明的入库延迟上限")


def _validate_events(events: pd.DataFrame, users: pd.DataFrame, cfg: Config, stage: str) -> None:
    data_cfg = load_v3_data_config()
    _require(events.event_id.map(lambda x: isinstance(x, str) and bool(x)).all(), "event_id必须为非空文本")
    _same_event_payload(events)
    if stage != "dirty":
        _require(not events.duplicated(["run_id", "event_id"]).any(), "事件主键未去重")
    types = tuple(data_cfg.require("events.event_types").values())
    _require(events.event_type.isin(types).all(), "未知事件类型")
    _require(np.isfinite(events[["event_day", "ingested_day"]].to_numpy(dtype=float)).all(), "事件时间不完整")
    _require((events.ingested_day >= events.event_day).all(), "事件入库早于发生")
    joined = events.merge(users[["run_id", "user_id", "assignment_day"]], on=["run_id", "user_id"], validate="many_to_one")
    _require((joined.event_day <= joined.assignment_day).all(), "分配前特征包含未来事件")
    _require((joined.event_day >= joined.assignment_day - float(data_cfg.require("events.pre_assignment_window_days"))).all(), "行为事件超出声明的预窗")
    cap = int(cfg.require("data.event_log_cap"))
    total = users.browse_depth + int(bool(data_cfg.require("events.include_eligibility_cart_event")))
    _require((users.event_retained_count == np.minimum(total, cap)).all(), "事件保留计数不符")
    _require((users.event_truncated_count == total - users.event_retained_count).all(), "事件截断计数不符")
    counts = events.drop_duplicates(["run_id", "event_id"]).groupby(["run_id", "user_id"]).size()
    actual = counts.reindex(_keys(users, ("run_id", "user_id")), fill_value=0).to_numpy()
    _require(np.array_equal(actual, users.event_retained_count.to_numpy()), "事件行数与保留计数不符")


def _validate_orders(orders: pd.DataFrame, users: pd.DataFrame, assignments: pd.DataFrame, cfg: Config) -> None:
    _integers(orders, ["order_id"], allow_negative=True)
    _integers(orders, ["order_number", "action", "refunded", *(c for c in orders if c.endswith("_cent"))])
    _require(orders.order_number.isin((1, 2)).all() and orders.action.isin((0, 1)).all() and orders.refunded.isin((0, 1)).all(), "订单类别非法")
    _require(not orders.duplicated(["run_id", "user_id", "order_number"]).any(), "同一用户重复订单序号")
    _require(np.isfinite(orders[["assignment_day", "paid_day", "paid_ingested_day"]].to_numpy(dtype=float)).all(), "订单支付时间不完整")
    _require((orders.paid_day >= orders.assignment_day).all() and (orders.paid_ingested_day >= orders.paid_day).all(), "支付或入库先于相应事件")
    joined = orders.merge(assignments[["run_id", "user_id", "actual_action", "assignment_day", "coupon_face_cent"]], on=["run_id", "user_id"], validate="many_to_one", suffixes=("", "_assigned"))
    _require((joined.action == joined.actual_action).all() and (joined.assignment_day == joined.assignment_day_assigned).all(), "订单动作/分配日与事实分配不符")
    refund = orders.refunded.astype(bool)
    _require(np.isfinite(orders.loc[refund, ["refund_day", "refund_ingested_day"]].to_numpy(dtype=float)).all(), "退款事实缺少时间")
    _require((orders.loc[refund, "refund_day"] >= orders.loc[refund, "paid_day"]).all(), "退款早于支付")
    _require((orders.loc[refund, "refund_ingested_day"] >= orders.loc[refund, "refund_day"]).all(), "退款入库早于事件")
    _require(orders.loc[~refund, ["refund_day", "refund_ingested_day"]].isna().all().all(), "未退款订单有退款时间")
    refund_money = ["goods_cost_recovered_cent", "refund_processing_fee_cent", "gross_refund_reversal_cent", "consumer_refund_cent", "coupon_return_cent"]
    _require((orders.loc[~refund, refund_money] == 0).all().all(), "未退款订单有退款账务")
    _require((orders.goods_cost_cent <= orders.gross_order_amount_cent).all(), "商品成本大于订单总额")
    _require((orders.consumer_paid_cent == orders.gross_order_amount_cent - orders.coupon_discount_cent).all(), "消费者实付与抵扣不符")
    _require((orders.coupon_cost_initial_cent == orders.coupon_discount_cent).all(), "初始券成本重复或漏记")
    cap = np.minimum(joined.coupon_face_cent, joined.gross_order_amount_cent)
    _require(((joined.coupon_discount_cent == 0) | (joined.coupon_discount_cent == cap)).all(), "核销抵扣不符合封顶规则")
    _require((orders.loc[(orders.action == 0) | (orders.order_number != 1), ["coupon_discount_cent", "coupon_cost_initial_cent", "coupon_return_cent"]] == 0).all().all(), "无券动作或复购使用了券")
    _require((orders.loc[refund, "gross_refund_reversal_cent"] == orders.loc[refund, "gross_order_amount_cent"]).all(), "退款总额冲减不符")
    _require((orders.loc[refund, "consumer_refund_cent"] == orders.loc[refund, "consumer_paid_cent"]).all(), "消费者退款不符")
    _require(np.array_equal(orders.loc[refund, "goods_cost_recovered_cent"].to_numpy(), _round_component(orders.loc[refund, "goods_cost_cent"], float(cfg.require("business.refundable_goods_ratio")))), "回收成本舍入或基数不符")
    _require(np.array_equal(orders.loc[refund, "refund_processing_fee_cent"].to_numpy(), _round_component(orders.loc[refund, "gross_order_amount_cent"], float(cfg.require("business.refund_handling_fee_rate")))), "退款手续费不符")
    expected_return = orders.loc[refund, "coupon_cost_initial_cent"] * bool(cfg.require("business.coupon_returned_on_refund"))
    _require((orders.loc[refund, "coupon_return_cent"] == expected_return).all(), "退款退券开关不符")
    first = orders.loc[orders.order_number == 1]
    repeat = orders.loc[orders.order_number == 2]
    _require(bool(cfg.require("business.repeat.enabled")) or not len(repeat), "禁用复购仍有复购订单")
    _require(_keys(repeat, ("run_id", "user_id")).isin(_keys(first, ("run_id", "user_id"))).all(), "没有首单却有复购")
    if len(repeat):
        pairs = repeat.merge(first[["run_id", "user_id", "gross_order_amount_cent", "paid_day"]], on=["run_id", "user_id"], validate="one_to_one", suffixes=("", "_first"))
        _require(np.array_equal(pairs.gross_order_amount_cent, _round_component(pairs.gross_order_amount_cent_first, float(cfg.require("business.repeat.gross_value_ratio")))), "复购金额比例/舍入不符")
        _require((pairs.paid_day >= pairs.paid_day_first).all(), "复购发生在首单前")
    observed_cart = first.merge(users[["run_id", "user_id", "cart_value_cent"]], on=["run_id", "user_id"], validate="many_to_one")
    known = observed_cart.cart_value_cent.notna()
    _require((observed_cart.loc[known, "gross_order_amount_cent"] <= observed_cart.loc[known, "cart_value_cent"]).all(), "首单超过已知购物车")


def _validate_outcomes(outcomes: pd.DataFrame, users: pd.DataFrame, assignments: pd.DataFrame, cfg: Config, required: bool) -> None:
    if not len(outcomes) and not required:
        return
    data_cfg = load_v3_data_config()
    windows = {str(data_cfg.require("sql.convert_window_name")): float(cfg.require("windows.convert_days")),
               str(data_cfg.require("sql.profit_window_name")): float(cfg.require("windows.profit_days"))}
    _require(len(outcomes) == len(users) * len(windows), "SQL结果未覆盖全体用户的两个窗口")
    _require(outcomes.window_type.isin(windows).all(), "SQL混用未知窗口")
    count = outcomes.groupby(["run_id", "user_id"]).window_type.nunique()
    _require((count == len(windows)).all(), "SQL结果用户缺窗口")
    _integers(outcomes, ["mature", "converted", "refunded", "paid_orders", "refunded_orders"])
    signed = {"coupon_cost_cent", "net_profit_cent", "net_transaction_amount_cent"}
    _integers(outcomes, list(signed), allow_negative=True)
    _integers(outcomes, [c for c in OUTCOME_MONEY_COLUMNS if c not in signed])
    _require(outcomes.mature.isin((0, 1)).all() and outcomes.converted.isin((0, 1)).all() and outcomes.refunded.isin((0, 1)).all(), "SQL结果二元字段非法")
    joined = outcomes.merge(users[["run_id", "user_id", "assignment_day"]], on=["run_id", "user_id"], validate="many_to_one")
    expected_days = joined.window_type.map(windows)
    _require((joined.window_days == expected_days).all() and (joined.window_end_day == joined.assignment_day + expected_days).all(), "SQL窗口长度/终点错误")
    _require(np.isfinite(outcomes[["window_days", "window_end_day", "asof_day", "required_ingestion_day", "complete_after_day"]].to_numpy(dtype=float)).all(), "SQL时窗/可见性字段不完整")
    maximum_delay = float(cfg.require("data.dirty.ingestion_delay_max_hours")) / float(data_cfg.require("time.hours_per_day"))
    # 与SQL及相对快照使用同一时钟运算：先加持续时间，再加用户分配日。
    # (assignment_day + window_days) + delay会在分数日期的边界多舍入一次。
    expected_complete = joined.assignment_day + (expected_days + maximum_delay)
    _require((joined.complete_after_day == expected_complete).all(), "SQL成熟最晚日期不符合配置入库上限")
    _require((outcomes.mature == (outcomes.asof_day >= outcomes.complete_after_day).astype(int)).all(), "SQL成熟状态错误")
    _require((outcomes.required_ingestion_day <= outcomes.asof_day).all(), "SQL结果读取了尚未入库的事件")
    _require((outcomes.converted == (outcomes.paid_orders > 0).astype(int)).all() and (outcomes.refunded == (outcomes.refunded_orders > 0).astype(int)).all(), "SQL用户事件指示与订单数不一致")
    profit = (outcomes.gross_order_amount_cent - outcomes.gross_refund_reversal_cent - outcomes.goods_cost_cent
              + outcomes.goods_cost_recovered_cent - outcomes.fulfill_cost_cent - outcomes.coupon_cost_cent - outcomes.refund_processing_fee_cent)
    _require((outcomes.net_profit_cent == profit).all(), "SQL净利润组件恒等式失败")
    _require((outcomes.coupon_cost_cent == outcomes.coupon_cost_initial_cent - outcomes.coupon_return_cent).all(), "SQL券成本重复扣减或漏记")
    _require((outcomes.net_transaction_amount_cent == outcomes.gross_order_amount_cent - outcomes.gross_refund_reversal_cent).all(), "SQL净交易额不符")
    zero = (outcomes.paid_orders == 0) & (outcomes.refunded_orders == 0)
    _require((outcomes.loc[zero, OUTCOME_MONEY_COLUMNS] == 0).all().all(), "窗口内无订单/退款却出现账务")
