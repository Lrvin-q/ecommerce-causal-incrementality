"""利润核算测试 —— 守 GOAL.md 的三条否证式红线。

R1 退款单不得剔除、分母是全部随机分配用户
R2 两个窗口分开、等长
R3 券成本只扣一次

这三条一旦被违反，项目结论直接作废，而且**不会报错**——只会悄悄错掉。
所以这里把它们做成可执行的断言。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth.config import load_config
from causal_growth.data.profit import (
    aggregate_user_profit,
    build_user_outcomes,
    compute_order_components,
    expected_order_net_profit,
    validate_orders_schema,
)
from causal_growth.contracts import CONVERT_WINDOW, PROFIT_WINDOW


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _one_order(**over: object) -> pd.DataFrame:
    row = {
        "order_id": "O1",
        "user_id": 1,
        "order_time": pd.Timestamp("2024-03-02"),
        "pay_amount": 100.0,
        "refund_amount": 0.0,
        "goods_cost": 68.0,
        "fulfill_cost": 5.0,
        "coupon_used": False,
        "coupon_value": 0.0,
        "refunded": False,
    }
    row.update(over)
    return pd.DataFrame([row])


class TestR3CouponCostCountedOnce:
    """R3：券核销成本在 Π^net 里出现**且仅出现一次**。"""

    def test_coupon_cost_appears_exactly_once(self, cfg) -> None:
        no_coupon = compute_order_components(_one_order(), cfg)["net_profit"].iloc[0]
        with_coupon = compute_order_components(
            _one_order(coupon_used=True, coupon_value=10.0), cfg
        )["net_profit"].iloc[0]
        # 只差一个面额，不多不少 —— 差两倍就是重复扣减
        assert no_coupon - with_coupon == pytest.approx(10.0)

    def test_coupon_component_column_reflects_single_deduction(self, cfg) -> None:
        comp = compute_order_components(_one_order(coupon_used=True, coupon_value=10.0), cfg)
        assert comp["coupon_cost_net"].iloc[0] == pytest.approx(10.0)
        # 手工重算：每一项各减一次
        expected = (
            comp["revenue_net"].iloc[0]
            - comp["goods_cost_net"].iloc[0]
            - comp["fulfill_cost"].iloc[0]
            - comp["coupon_cost_net"].iloc[0]
            - comp["refund_handling_fee"].iloc[0]
        )
        assert comp["net_profit"].iloc[0] == pytest.approx(expected)

    def test_unused_coupon_costs_nothing(self, cfg) -> None:
        """未核销的券不产生成本——「面额」不等于「成本」。"""
        unused = compute_order_components(
            _one_order(coupon_used=False, coupon_value=20.0), cfg
        )["net_profit"].iloc[0]
        plain = compute_order_components(_one_order(), cfg)["net_profit"].iloc[0]
        assert unused == pytest.approx(plain)


class TestRefundAccounting:
    """方案 §2.3.3 的退款四项处理。"""

    def test_refund_four_components(self, cfg) -> None:
        comp = compute_order_components(
            _one_order(refunded=True, refund_amount=100.0), cfg
        ).iloc[0]
        fee_rate = float(cfg.require("business.refund_handling_fee_rate"))
        recyclable = float(cfg.require("business.refundable_goods_ratio"))

        assert comp["revenue_net"] == pytest.approx(0.0)          # 收入冲减为 0
        assert comp["refund_handling_fee"] == pytest.approx(100.0 * fee_rate)
        assert comp["goods_recovered"] == pytest.approx(68.0 * recyclable)
        assert comp["goods_cost_net"] == pytest.approx(68.0 * (1 - recyclable))
        assert comp["fulfill_cost"] == pytest.approx(5.0)          # 履约成本不回收
        # 退款单整体必须是净流出
        assert comp["net_profit"] < 0

    def test_refund_handling_fee_not_double_counted(self, cfg) -> None:
        """手续费只能出现在 net 里一次。若既进 revenue_net 又单列，会被这条抓到。"""
        fee_rate = float(cfg.require("business.refund_handling_fee_rate"))
        comp = compute_order_components(_one_order(refunded=True, refund_amount=100.0), cfg)
        row = comp.iloc[0]
        manual = (
            100.0
            - 100.0
            - 68.0 * (1 - float(cfg.require("business.refundable_goods_ratio")))
            - 5.0
            - 0.0
            - 100.0 * fee_rate
        )
        assert row["net_profit"] == pytest.approx(manual, abs=1e-9)

    def test_refunded_order_kept_in_sample(self, cfg) -> None:
        """R1：退款单必须留在样本里，不能过滤掉。"""
        orders = pd.concat(
            [
                _one_order(order_id="O1", user_id=1),
                _one_order(order_id="O2", user_id=2, refunded=True, refund_amount=100.0),
            ],
            ignore_index=True,
        )
        components = compute_order_components(orders, cfg)
        assert len(components) == 2
        assert (components["net_profit"] < 0).sum() == 1

    def test_coupon_returned_on_refund_reduces_cost(self, cfg) -> None:
        kept = compute_order_components(
            _one_order(refunded=True, refund_amount=100.0, coupon_used=True, coupon_value=10.0), cfg
        )["coupon_cost_net"].iloc[0]
        assert kept == pytest.approx(10.0)  # 默认券不退回 → 成本保留

        returned_cfg = cfg.with_overrides({"business.coupon_returned_on_refund": True})
        returned = compute_order_components(
            _one_order(refunded=True, refund_amount=100.0, coupon_used=True, coupon_value=10.0),
            returned_cfg,
        )["coupon_cost_net"].iloc[0]
        assert returned == pytest.approx(0.0)

    def test_missing_required_columns_raises(self, cfg) -> None:
        bad = _one_order().drop(columns=["goods_cost"])
        with pytest.raises(ValueError, match="必需列"):
            validate_orders_schema(bad)
        with pytest.raises(ValueError, match="必需列"):
            compute_order_components(bad, cfg)


class TestR1DenominatorIsAllUsers:
    def test_non_converted_users_get_zero_not_dropped(self, cfg) -> None:
        orders = _one_order(user_id=1)
        all_users = np.array([1, 2, 3, 4])
        series = aggregate_user_profit(orders, all_users, cfg)
        assert len(series) == 4          # 分母是全部随机分配用户
        assert series.loc[1] != 0.0
        assert (series.loc[[2, 3, 4]] == 0.0).all()

    def test_order_level_aggregation_would_be_wrong(self, cfg) -> None:
        """反例：只按订单聚合 = 只分析成功支付订单 = 引入处理后选择偏差。"""
        orders = _one_order(user_id=1)
        all_users = np.array([1, 2, 3, 4])
        correct = aggregate_user_profit(orders, all_users, cfg).mean()
        naive = compute_order_components(orders, cfg)["net_profit"].mean()
        assert not np.isclose(correct, naive)


class TestR2TwoWindows:
    def _tables(self, cfg):
        n = 50
        users = np.arange(n)
        assign = pd.DataFrame(
            {"user_id": users, "assign_time": pd.Timestamp("2024-03-01")}
        )
        orders = pd.DataFrame(
            {
                "order_id": [f"O{i}" for i in range(10)],
                "user_id": np.arange(10),
                "order_time": pd.Timestamp("2024-03-03"),
                "pay_amount": 120.0,
                "refund_amount": 0.0,
                "goods_cost": 81.6,
                "fulfill_cost": 5.0,
                "coupon_used": False,
                "coupon_value": 0.0,
                "refunded": False,
            }
        )
        return orders, assign, users

    def test_each_user_has_exactly_two_windows(self, cfg) -> None:
        orders, assign, users = self._tables(cfg)
        out = build_user_outcomes(orders, assign, users, cfg)
        assert len(out) == 2 * len(users)
        per_user = out.groupby("user_id").size()
        assert (per_user == 2).all()
        assert set(out["window_type"]) == {CONVERT_WINDOW, PROFIT_WINDOW}

    def test_convert_window_profit_is_unmatured(self, cfg) -> None:
        """转化窗口只有"是否下单"，利润尚未成熟 —— 这正是两窗口必须分开的原因。"""
        orders, assign, users = self._tables(cfg)
        out = build_user_outcomes(orders, assign, users, cfg)
        conv = out[out["window_type"] == CONVERT_WINDOW]
        assert conv["net_profit"].isna().all()

    def test_profit_window_has_no_nan_profit(self, cfg) -> None:
        orders, assign, users = self._tables(cfg)
        out = build_user_outcomes(orders, assign, users, cfg)
        profit = out[out["window_type"] == PROFIT_WINDOW]
        assert profit["net_profit"].notna().all()
        assert profit["net_profit"].sum() > 0

    def test_conversion_counts_match(self, cfg) -> None:
        orders, assign, users = self._tables(cfg)
        out = build_user_outcomes(orders, assign, users, cfg)
        conv = out[out["window_type"] == CONVERT_WINDOW]
        assert conv["converted"].sum() == len(orders)

    def test_order_outside_profit_window_is_excluded(self, cfg) -> None:
        """超过利润成熟窗口的订单不计入——窗口是等长的，不随用户浮动。"""
        orders, assign, users = self._tables(cfg)
        late = orders.copy()
        late.loc[0, "order_time"] = pd.Timestamp("2024-05-30")  # 远超 30 天
        out = build_user_outcomes(late, assign, users, cfg)
        profit = out[out["window_type"] == PROFIT_WINDOW]
        assert profit.loc[profit["user_id"] == 0, "converted"].iloc[0] == 0


class TestAnalyticVsMonteCarlo:
    """解析式 ``expected_order_net_profit`` 必须与逐单核算的蒙特卡洛均值一致。

    这是"真值"与"实现"之间的桥梁：如果两者有偏，所有 ATE 对比都失去意义。
    """

    def test_expected_matches_monte_carlo_no_refund_path(self, cfg) -> None:
        b = cfg.section("business")
        rng = np.random.default_rng(0)
        n = 400_000
        pay = np.clip(rng.normal(b["aov_mean"], b["aov_sd"], n), b["aov_min"], None)
        fulfill = np.clip(rng.normal(b["fulfill_cost_mean"], b["fulfill_cost_sd"], n), 0.5, None)
        refunded = rng.random(n) < b["refund_rate"]

        orders = pd.DataFrame(
            {
                "order_id": [f"O{i}" for i in range(n)],
                "user_id": np.arange(n),
                "order_time": pd.Timestamp("2024-03-02"),
                "pay_amount": pay,
                "refund_amount": np.where(refunded, pay, 0.0),
                "goods_cost": pay * b["goods_cost_ratio"],
                "fulfill_cost": fulfill,
                "coupon_used": False,
                "coupon_value": 0.0,
                "refunded": refunded,
            }
        )
        mc = compute_order_components(orders, cfg)["net_profit"].mean()
        analytic = expected_order_net_profit(
            pay_mean=b["aov_mean"],
            goods_cost_ratio=b["goods_cost_ratio"],
            fulfill_mean=b["fulfill_cost_mean"],
            refund_rate=b["refund_rate"],
            refundable_goods_ratio=b["refundable_goods_ratio"],
            refund_handling_fee_rate=b["refund_handling_fee_rate"],
            coupon_cost_expectation=0.0,
        )
        # n=40 万，SE ≈ 0.02，取 0.15 元容差约 7σ
        assert abs(mc - analytic) < 0.15, f"蒙特卡洛 {mc:.4f} vs 解析 {analytic:.4f}"
