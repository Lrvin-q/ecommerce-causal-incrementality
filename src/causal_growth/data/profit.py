"""利润核算 —— 项目口径的**唯一实现**。

本文件落地《项目方案思路.md》§2.3 的三条硬规则（对应 GOAL.md 的 R1/R2/R3）：

R1 **退款订单不得剔除**，分析分母是随机分配的**全部用户**（未下单用户利润记 0）。
R2 **两个窗口分开**：转化观察窗口 7 天、利润成熟窗口 30 天，所有用户等长。
R3 **券成本只扣一次**：``net_profit`` 已含券核销成本；下游策略价值 ``V(π)``
   不得再扣一次，预算约束 ``E[π(X)c(X)] ≤ B`` 只限制资源、不扣钱。

单一事实来源
------------
DGP 生成订单、分析侧计算利润、单测断言，**全部调用本模块**。
任何模块私自复制一份利润公式 = 口径错配的开始，禁止。

利润构成（方案 §2.3.3）
-----------------------
::

    Π^net = 支付收入 − 商品成本 − 履约成本 − 券核销成本

    退款订单四项分别处理：
      支付收入    → 冲减为 0，并扣退款手续费
      商品成本    → 可回收部分冲减，不可回收部分保留
      履约成本    → 已发生，不回收，全额保留
      券核销成本  → 券不退回则保留；退回则冲减

即::

    net = (pay_amount − refund_amount − handling_fee)
          − (goods_cost − goods_recoverable)
          − fulfill_cost
          − coupon_cost_net
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from causal_growth.contracts import CONVERT_WINDOW, PROFIT_WINDOW

__all__ = [
    "COMPONENT_COLUMNS",
    "ORDERS_REQUIRED_COLUMNS",
    "ProfitComponents",
    "aggregate_user_profit",
    "build_user_outcomes",
    "compute_order_components",
    "expected_order_net_profit",
    "validate_orders_schema",
]

#: ``orders`` 表参与利润核算的必需列
ORDERS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "order_id",
    "user_id",
    "order_time",
    "pay_amount",
    "refund_amount",
    "goods_cost",
    "fulfill_cost",
    "coupon_used",
    "coupon_value",
    "refunded",
)

#: ``compute_order_components`` 输出的构成列
COMPONENT_COLUMNS: tuple[str, ...] = (
    "revenue_net",
    "goods_cost_net",
    "fulfill_cost",
    "coupon_cost_net",
    "refund_handling_fee",
    "goods_recovered",
)


@dataclass(frozen=True)
class ProfitComponents:
    """单笔订单的利润构成，便于诊断"钱花在哪"。

    每一项都是**独立、互不重叠**的成本项；``net`` 把它们各减一次。
    ``revenue_net`` 刻意保持"纯收入"语义（不退手续费），手续费单列一项，
    避免"既在收入里减、又在净额里减"的重复扣减。
    """

    revenue_net: float
    goods_cost_net: float
    fulfill_cost: float
    coupon_cost_net: float
    refund_handling_fee: float

    @property
    def net(self) -> float:
        return (
            self.revenue_net
            - self.goods_cost_net
            - self.fulfill_cost
            - self.coupon_cost_net
            - self.refund_handling_fee
        )


def validate_orders_schema(orders: pd.DataFrame) -> None:
    """缺列即抛错。宁可当场失败，也不要静默算出错的利润。"""
    missing = [c for c in ORDERS_REQUIRED_COLUMNS if c not in orders.columns]
    if missing:
        raise ValueError(f"orders 表缺少利润核算必需列：{missing}")


def compute_order_components(orders: pd.DataFrame, cfg: Any) -> pd.DataFrame:
    """逐单计算利润构成（向量化）。

    参数
    ----
    orders : 至少含 ``ORDERS_REQUIRED_COLUMNS`` 的订单表。退款单**必须**在里面。
    cfg : 配置对象，读取 ``business.refundable_goods_ratio``、
          ``business.refund_handling_fee_rate``、``business.coupon_returned_on_refund``。

    返回
    ----
    DataFrame，索引与 ``orders`` 对齐，含 ``COMPONENT_COLUMNS`` 与 ``net_profit``。
    """
    validate_orders_schema(orders)

    refundable_ratio = float(cfg.require("business.refundable_goods_ratio"))
    handling_fee_rate = float(cfg.require("business.refund_handling_fee_rate"))
    coupon_returned = bool(cfg.require("business.coupon_returned_on_refund"))

    refunded = orders["refunded"].astype(bool).to_numpy()
    coupon_used = orders["coupon_used"].astype(bool).to_numpy()

    pay_amount = orders["pay_amount"].to_numpy(dtype=float)
    refund_amount = orders["refund_amount"].to_numpy(dtype=float)
    goods_cost = orders["goods_cost"].to_numpy(dtype=float)
    fulfill_cost = orders["fulfill_cost"].to_numpy(dtype=float)
    coupon_value = orders["coupon_value"].to_numpy(dtype=float)

    # ① 支付收入：退款则冲减（refund_amount 已含全额退款）
    revenue_net = pay_amount - refund_amount
    refund_handling_fee = np.where(refunded, pay_amount * handling_fee_rate, 0.0)

    # ② 商品成本：退款后可回收部分冲减，不可回收部分保留
    goods_recovered = np.where(refunded, goods_cost * refundable_ratio, 0.0)
    goods_cost_net = goods_cost - goods_recovered

    # ③ 履约成本：已发生，不回收
    fulfill_cost_net = fulfill_cost

    # ④ 券核销成本：已核销才计入；若退款且券不退回，则成本保留（不冲减）
    coupon_active = coupon_used & (~refunded | ~coupon_returned)
    coupon_cost_net = np.where(coupon_active, coupon_value, 0.0)

    out = pd.DataFrame(
        {
            "revenue_net": revenue_net,
            "goods_cost_net": goods_cost_net,
            "fulfill_cost": fulfill_cost_net,
            "coupon_cost_net": coupon_cost_net,
            "refund_handling_fee": refund_handling_fee,
            "goods_recovered": goods_recovered,
        },
        index=orders.index,
    )
    # 每一项成本只在这里出现**一次**。任何一项若同时进了 revenue_net 又被单独扣，
    # 就是重复扣减（R3 的同类错误），由 tests/test_profit.py 的等式断言守住。
    out["net_profit"] = (
        out["revenue_net"]
        - out["goods_cost_net"]
        - out["fulfill_cost"]
        - out["coupon_cost_net"]
        - out["refund_handling_fee"]
    )
    return out


def aggregate_user_profit(
    orders: pd.DataFrame,
    all_user_ids: np.ndarray,
    cfg: Any,
) -> pd.Series:
    """把订单利润聚合到**用户**粒度。

    关键（R1）：分母是 ``all_user_ids`` —— 随机分配的**全部用户**。
    未下单用户没有订单行，其净贡献利润记为 **0**，而不是被剔出样本。
    如果这里只按订单聚合，就等于"只分析成功支付订单"，引入处理后选择偏差。

    返回
    ----
    Series，索引为 ``all_user_ids``，值为每用户累计净贡献利润。
    """
    components = compute_order_components(orders, cfg)
    by_user = components.groupby(orders["user_id"])["net_profit"].sum()
    series = by_user.reindex(all_user_ids, fill_value=0.0)
    series.index.name = "user_id"
    return series.astype(float)


def build_user_outcomes(
    orders: pd.DataFrame,
    assignments: pd.DataFrame,
    all_user_ids: np.ndarray,
    cfg: Any,
) -> pd.DataFrame:
    """生成 ``user_outcomes`` 长表：**每用户每窗口一行**。

    两个窗口（R2）：
    - ``convert_7d``：发券后 7 天内是否下单。此时利润尚未成熟，
      ``net_profit`` 留空（NaN），``refunded`` 也未知。
    - ``profit_30d``：覆盖支付、退款、成本结算。给出 ``net_profit`` 与 ``refunded``。

    所有用户的窗口长度**等长**：以各自的 ``assign_time`` 为起点，不是自然月。

    返回
    ----
    DataFrame[user_id, window_type, converted, gmv, net_profit, refunded]
    """
    convert_days = int(cfg.require("windows.convert_days"))
    profit_days = int(cfg.require("windows.profit_days"))

    base = assignments.loc[:, ["user_id", "assign_time"]].copy()
    base["assign_time"] = pd.to_datetime(base["assign_time"])

    # 统一的"用户 × 订单"视图，带上距分配的时长；多订单用户后续聚合
    od = orders.loc[:, ["user_id", "order_time", "pay_amount", "refunded", "order_id"]].copy()
    od["order_time"] = pd.to_datetime(od["order_time"])
    joined = od.merge(base, on="user_id", how="inner")
    joined["elapsed_days"] = (joined["order_time"] - joined["assign_time"]).dt.total_seconds() / 86400.0

    # ---- 窗口一：转化观察（convert_days）----
    in_conv = joined[joined["elapsed_days"] <= convert_days]
    conv_agg = in_conv.groupby("user_id").agg(
        n_orders=("order_id", "count"), gmv=("pay_amount", "sum")
    )
    conv = pd.DataFrame({"user_id": all_user_ids}).merge(conv_agg, on="user_id", how="left")
    conv["n_orders"] = conv["n_orders"].fillna(0).astype(np.int64)
    conv["converted"] = (conv["n_orders"] > 0).astype(np.int8)
    conv["gmv"] = conv["gmv"].fillna(0.0).astype(float)
    conv["net_profit"] = np.nan  # 利润未成熟：这正是两个窗口必须分开的原因
    conv["refunded"] = np.nan
    conv["window_type"] = CONVERT_WINDOW

    # ---- 窗口二：利润成熟（profit_days）----
    in_profit = joined[joined["elapsed_days"] <= profit_days]
    components = compute_order_components(orders, cfg)
    joined_net = orders.assign(net_profit=components["net_profit"].to_numpy())
    joined_net = joined_net.merge(base, on="user_id", how="inner")
    joined_net["elapsed_days"] = (
        pd.to_datetime(joined_net["order_time"]) - joined_net["assign_time"]
    ).dt.total_seconds() / 86400.0
    joined_net = joined_net[joined_net["elapsed_days"] <= profit_days]

    profit_agg = joined_net.groupby("user_id").agg(
        n_orders=("order_id", "count"),
        net_profit=("net_profit", "sum"),
        gmv=("pay_amount", "sum"),
        refunded=("refunded", "max"),
    )
    profit_win = pd.DataFrame({"user_id": all_user_ids}).merge(
        profit_agg, on="user_id", how="left"
    )
    profit_win["n_orders"] = profit_win["n_orders"].fillna(0).astype(np.int64)
    profit_win["converted"] = (profit_win["n_orders"] > 0).astype(np.int8)
    profit_win["gmv"] = profit_win["gmv"].fillna(0.0).astype(float)
    profit_win["net_profit"] = profit_win["net_profit"].fillna(0.0).astype(float)
    profit_win["refunded"] = profit_win["refunded"].fillna(False).astype(bool)
    profit_win["window_type"] = PROFIT_WINDOW

    cols = ["user_id", "window_type", "converted", "gmv", "net_profit", "refunded"]
    out = pd.concat([conv[cols], profit_win[cols]], ignore_index=True)
    out["window_type"] = pd.Categorical(out["window_type"], categories=[CONVERT_WINDOW, PROFIT_WINDOW])
    return out


def expected_order_net_profit(
    *,
    pay_mean: float,
    goods_cost_ratio: float,
    fulfill_mean: float,
    refund_rate: float,
    refundable_goods_ratio: float,
    refund_handling_fee_rate: float,
    coupon_cost_expectation: float,
    coupon_cost_expectation_on_refund: float | None = None,
) -> float:
    """**已转化订单**的期望净贡献利润（解析式，供 DGP 真值使用）。

    与 ``compute_order_components`` 必须代数等价；两者的对应关系由
    ``tests/test_profit.py`` 的蒙特卡洛一致性测试守住。

    ``coupon_cost_expectation`` = 面额 × P(核销 | 已转化)。无券情形传 0。
    ``coupon_cost_expectation_on_refund``：退款订单上券成本是否仍保留。
    若不传则与 ``coupon_cost_expectation`` 相同（券不退回的业务默认）。
    券退回时传 0——这是方案 §2.3.3 表格的最后一行。
    """
    if coupon_cost_expectation_on_refund is None:
        coupon_cost_expectation_on_refund = coupon_cost_expectation

    net_no_refund = pay_mean - pay_mean * goods_cost_ratio - fulfill_mean - coupon_cost_expectation
    net_refund = (
        -pay_mean * refund_handling_fee_rate
        - pay_mean * goods_cost_ratio * (1.0 - refundable_goods_ratio)
        - fulfill_mean
        - coupon_cost_expectation_on_refund
    )
    return float((1.0 - refund_rate) * net_no_refund + refund_rate * net_refund)
