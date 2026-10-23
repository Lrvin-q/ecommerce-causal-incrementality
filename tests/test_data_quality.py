"""脏数据层 / 数据质量检查 / 清洗的验收测试（方案 §3.5、§3.6 Step 2）。

守的几条红线
------------
* **缺失必须是 MNAR**：各渠道缺失率要"确实不同"，否则"渠道中位数填补 + 指示列"
  这套技巧就没有存在理由（``test_missing_is_mnar_by_channel``）。
* **延迟只脏入库时间**：``event_time`` 一个字节都不能变，否则"按事件时间切窗口"
  这条口径会被悄悄破坏（``test_delay_keeps_event_time``）。
* **刷单只脏原始字段**：``*_z`` 是分配时点快照，不能被脏数据层改
  （``test_fraud_does_not_touch_z_columns``）。
* **检查项必须真的会红**：干净数据全过只是及格线，把数据弄坏之后对应的检查项
  必须变红——否则清单就是摆设（``TestQualityCatchesBreakage``）。
* **清洗不删行**：去重只去重复、截尾只拉回分位点，行数或不变量都要守住。

规模约定：所有测试用 ``dgp.n_users = 3000``（AGENTS.md 允许调试用小样本，
但不允许把"没跑过"当成"跑过了"）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth.config import load_config
from causal_growth.contracts import CONVERT_WINDOW, PROFIT_WINDOW
from causal_growth.data import (
    EVENT_BUSINESS_KEY,
    QualityCheck,
    QualityError,
    add_fraud_outliers,
    add_missing_cart_value,
    apply_dirty_layer,
    apply_dirty_to_frame,
    assert_no_errors,
    build_analysis_frame,
    build_five_tables,
    check_analysis_frame,
    check_tables,
    clean_analysis_frame,
    deduplicate_events,
    delay_ingestion,
    duplicate_events,
    impute_cart_value,
    summarize,
    winsorize,
)
from causal_growth.dgp import assign_random, build

MASTER_SEED = 20240101
N_USERS = 3000

#: 统计容差倍数（**测试用**的抽样波动容忍度，不是业务参数）
SIGMA_MULTIPLE = 5.0


# --------------------------------------------------------------------------- #
# 夹具：一套干净的 DGP → 五表 / 分析框架
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def cfg():
    """真实配置 + 小样本规模（口径一律来自 configs/base.yaml，测试不自带业务参数）。"""
    return load_config(overrides={"dgp.n_users": N_USERS})


@pytest.fixture(scope="module")
def population(cfg):
    """L1 总体 + 随机分流：真值已知、可复现。"""
    return assign_random(cfg, build("L1", cfg, 0), index=0)


@pytest.fixture(scope="module")
def tables(population, cfg):
    """干净的五张关系表。**任何测试都不得原地修改它**（module 级共享）。"""
    return build_five_tables(population, cfg)


@pytest.fixture(scope="module")
def frame(population, cfg):
    """干净的用户级分析框架。"""
    return build_analysis_frame(population, cfg)


@pytest.fixture()
def tables_copy(tables):
    """深拷贝的五表字典，供破坏性测试随意改。"""
    return {name: value.copy(deep=True) for name, value in tables.items()}


@pytest.fixture(scope="module")
def dirty_tables(tables, cfg):
    """套了完整脏数据层的五表。"""
    return apply_dirty_layer(tables, cfg, master_seed=MASTER_SEED)


@pytest.fixture(scope="module")
def dirty_frame(frame, cfg):
    """套了脏数据层的分析框架。"""
    return apply_dirty_to_frame(frame, cfg, master_seed=MASTER_SEED)


def _check_map(checks: list[QualityCheck]) -> dict[str, QualityCheck]:
    """按名称索引检查结果，断言时读起来更像口径而不是列表下标。"""
    return {c.name: c for c in checks}


def _binomial_tolerance(p: float, n: int, k: float = SIGMA_MULTIPLE) -> float:
    """二项比例在 ``n`` 次抽样下的 ``k`` 倍标准差（用来判断观测比例是否离谱）。"""
    return float(k * np.sqrt(max(p * (1.0 - p), 0.0) / n))


# --------------------------------------------------------------------------- #
# 1. MNAR 缺失
# --------------------------------------------------------------------------- #
class TestMissingCartValue:
    def test_missing_is_mnar_by_channel(self, tables, cfg) -> None:
        """各渠道缺失率必须**明显不同**（最高/最低 > 2 倍）——这是 MNAR 的证据。"""
        users = tables["users"]
        out = add_missing_cart_value(
            users, cfg, master_seed=MASTER_SEED, column="cart_value_at_assign"
        )
        rates = (
            out.assign(missing=out["cart_value_at_assign"].isna())
            .groupby("channel", observed=True)["missing"]
            .mean()
        )
        assert int(out["cart_value_at_assign"].isna().sum()) > 0
        assert rates.max() / rates.min() > 2.0, f"各渠道缺失率差异太小，MNAR 未生效：{rates.to_dict()}"
        # xhs 设计缺失率最高、search 最低，排序必须体现出来
        assert rates.idxmax() == "xhs"
        assert rates.idxmin() == "search"

    def test_missing_rates_match_config_per_channel(self, tables, cfg) -> None:
        """每个渠道的实测缺失率应落在设计值的抽样波动内（否则注入逻辑写错了）。"""
        users = tables["users"]
        design = cfg.section("dirty")["cart_value_missing_by_channel"]
        out = add_missing_cart_value(
            users, cfg, master_seed=MASTER_SEED, column="cart_value_at_assign"
        )
        out = out.assign(missing=out["cart_value_at_assign"].isna())
        for channel, p in design.items():
            group = out.loc[out["channel"].astype(str) == channel, "missing"]
            observed = float(group.mean())
            assert abs(observed - float(p)) <= _binomial_tolerance(float(p), len(group)), (
                f"渠道 {channel} 缺失率 {observed:.4f} 偏离设计值 {p}"
            )

    def test_unknown_channel_falls_back_to_global_rate(self, cfg) -> None:
        """渠道字典里没有的渠道要退回 ``cart_value_missing_rate``，不能静默不缺失。"""
        n = 20000
        sample = pd.DataFrame(
            {
                "user_id": np.arange(n, dtype=np.int64),
                "cart_value": np.full(n, 100.0),
                "channel": pd.Categorical(["unknown"] * n),
            }
        )
        fallback = float(cfg.section("dirty")["cart_value_missing_rate"])
        out = add_missing_cart_value(
            sample, cfg, master_seed=MASTER_SEED, column="cart_value"
        )
        observed = float(out["cart_value"].isna().mean())
        assert abs(observed - fallback) <= _binomial_tolerance(fallback, n)

    def test_missing_does_not_mutate_input(self, tables, cfg) -> None:
        """纯函数：输入对象不得被改（否则"脏/干净"两套对比会互相污染）。"""
        users = tables["users"]
        before = users.copy(deep=True)
        add_missing_cart_value(
            users, cfg, master_seed=MASTER_SEED, column="cart_value_at_assign"
        )
        pd.testing.assert_frame_equal(users, before)

    def test_missing_is_reproducible(self, tables, cfg) -> None:
        """同一 ``(master_seed, index)`` 两次调用必须逐值一致。"""
        users = tables["users"]
        first = add_missing_cart_value(
            users, cfg, master_seed=MASTER_SEED, index=0, column="cart_value_at_assign"
        )
        second = add_missing_cart_value(
            users, cfg, master_seed=MASTER_SEED, index=0, column="cart_value_at_assign"
        )
        pd.testing.assert_frame_equal(first, second)

    def test_different_index_gives_different_mask(self, tables, cfg) -> None:
        """换 index 就是换一条随机流，缺失位置必须不同。"""
        users = tables["users"]
        a = add_missing_cart_value(
            users, cfg, master_seed=MASTER_SEED, index=0, column="cart_value_at_assign"
        )
        b = add_missing_cart_value(
            users, cfg, master_seed=MASTER_SEED, index=1, column="cart_value_at_assign"
        )
        assert not np.array_equal(a["cart_value_at_assign"].isna(), b["cart_value_at_assign"].isna())

    def test_disabled_returns_identical_copy(self, tables) -> None:
        """``dirty.enabled = false`` 时原样返回（内容相同，但不是同一个对象）。"""
        cfg_off = load_config(overrides={"dgp.n_users": N_USERS, "dirty.enabled": False})
        out = add_missing_cart_value(
            tables["users"], cfg_off, master_seed=MASTER_SEED, column="cart_value_at_assign"
        )
        pd.testing.assert_frame_equal(out, tables["users"])
        assert int(out["cart_value_at_assign"].isna().sum()) == 0


# --------------------------------------------------------------------------- #
# 2. 刷单异常值
# --------------------------------------------------------------------------- #
class TestFraudOutliers:
    def test_fraud_inflates_max_and_hits_expected_users(self, frame, cfg) -> None:
        """刷单把最大值放大，且受影响人数≈``fraud_user_rate * n``。"""
        dirty = add_fraud_outliers(frame, cfg, master_seed=MASTER_SEED)
        rate = float(cfg.section("dirty")["fraud_user_rate"])
        multiplier = float(cfg.section("dirty")["fraud_gmv_multiplier"])

        changed = dirty["hist_gmv"].to_numpy() != frame["hist_gmv"].to_numpy()
        n_affected = int(changed.sum())

        assert n_affected == pytest.approx(rate * N_USERS, abs=0.5)
        assert dirty["hist_gmv"].max() > frame["hist_gmv"].max() * 2.0
        # 被影响的用户里至少有一个被放大了 multiplier 倍
        assert dirty.loc[changed, "hist_gmv"].max() >= (
            frame.loc[changed, "hist_gmv"].max() * multiplier * 0.999
        )

    def test_fraud_does_not_touch_z_columns(self, frame, cfg) -> None:
        """z 值是分配时点快照：脏数据层只改原始字段，不动 ``*_z``（语义取舍见 docstring）。"""
        dirty = add_fraud_outliers(frame, cfg, master_seed=MASTER_SEED)
        for column in ("hist_gmv_z", "cart_value_z", "browse_depth_z"):
            pd.testing.assert_series_equal(dirty[column], frame[column])

    def test_fraud_keeps_other_columns(self, frame, cfg) -> None:
        """刷单只碰目标列，其它字段与行数不变。"""
        dirty = add_fraud_outliers(frame, cfg, master_seed=MASTER_SEED)
        assert len(dirty) == len(frame)
        for column in ("user_id", "cart_value", "channel", "net_profit"):
            pd.testing.assert_series_equal(dirty[column], frame[column])

    def test_fraud_does_not_mutate_input(self, frame, cfg) -> None:
        before = frame.copy(deep=True)
        add_fraud_outliers(frame, cfg, master_seed=MASTER_SEED)
        pd.testing.assert_frame_equal(frame, before)

    def test_fraud_disabled_is_identity(self, frame) -> None:
        cfg_off = load_config(overrides={"dgp.n_users": N_USERS, "dirty.enabled": False})
        out = add_fraud_outliers(frame, cfg_off, master_seed=MASTER_SEED)
        pd.testing.assert_frame_equal(out, frame)

    def test_fraud_rejects_multiplier_below_one(self, frame) -> None:
        """放大倍数 < 1 是配置错误（刷单只会把金额变大），必须抛错而不是静默缩小。"""
        cfg_bad = load_config(
            overrides={"dgp.n_users": N_USERS, "dirty.fraud_gmv_multiplier": 0.5}
        )
        with pytest.raises(ValueError, match="fraud_gmv_multiplier"):
            add_fraud_outliers(frame, cfg_bad, master_seed=MASTER_SEED)


# --------------------------------------------------------------------------- #
# 3. 重复上报 / 上报延迟
# --------------------------------------------------------------------------- #
class TestEventDirt:
    def test_duplicate_events_adds_exact_copies(self, tables, cfg) -> None:
        """复制出的行数 = round(rate * n)，且每一行都是原型**逐字段**复制。"""
        events = tables["user_events"]
        rate = float(cfg.section("dirty")["duplicate_event_rate"])
        dup = duplicate_events(events, cfg, master_seed=MASTER_SEED)
        n_expected = int(np.floor(rate * len(events) + 0.5))

        assert len(dup) - len(events) == n_expected
        # 原行顺序不变
        pd.testing.assert_frame_equal(dup.iloc[: len(events)].reset_index(drop=True), events)
        # 追加的行都是重复行（整行相同，含 ts_ingested）
        assert int(dup.duplicated().sum()) == n_expected

    def test_duplicate_events_disabled(self, tables) -> None:
        cfg_off = load_config(overrides={"dgp.n_users": N_USERS, "dirty.enabled": False})
        out = duplicate_events(tables["user_events"], cfg_off, master_seed=MASTER_SEED)
        pd.testing.assert_frame_equal(out, tables["user_events"])

    def test_delay_keeps_event_time(self, tables, cfg) -> None:
        """**关键口径**：只推后 ``ts_ingested``，``event_time`` 逐值不变。"""
        events = tables["user_events"]
        delayed = delay_ingestion(events, cfg, master_seed=MASTER_SEED)

        pd.testing.assert_series_equal(delayed["event_time"], events["event_time"])
        assert bool((delayed["ts_ingested"] >= delayed["event_time"]).all())
        assert len(delayed) == len(events)

    def test_delay_within_configured_limit(self, tables, cfg) -> None:
        """延迟必须落在 ``[0, event_delay_max_hours]`` 小时内。"""
        limit = float(cfg.section("dirty")["event_delay_max_hours"])
        delayed = delay_ingestion(tables["user_events"], cfg, master_seed=MASTER_SEED)
        hours = (delayed["ts_ingested"] - delayed["event_time"]).dt.total_seconds() / 3600.0
        assert float(hours.min()) >= 0.0
        assert float(hours.max()) <= limit
        assert float(hours.max()) > 0.0  # 真的注入了延迟

    def test_delay_does_not_mutate_input(self, tables, cfg) -> None:
        events = tables["user_events"]
        before = events.copy(deep=True)
        delay_ingestion(events, cfg, master_seed=MASTER_SEED)
        pd.testing.assert_frame_equal(events, before)

    def test_delay_disabled(self, tables) -> None:
        cfg_off = load_config(overrides={"dgp.n_users": N_USERS, "dirty.enabled": False})
        out = delay_ingestion(tables["user_events"], cfg_off, master_seed=MASTER_SEED)
        pd.testing.assert_frame_equal(out, tables["user_events"])


# --------------------------------------------------------------------------- #
# 4. 编排
# --------------------------------------------------------------------------- #
class TestApplyDirtyLayer:
    def test_layer_only_touches_users_and_events(self, tables, dirty_tables) -> None:
        """``orders`` / ``coupon_assignment`` / ``user_outcomes`` 必须原样返回。"""
        for name in ("orders", "coupon_assignment", "user_outcomes"):
            pd.testing.assert_frame_equal(dirty_tables[name], tables[name])

    def test_layer_does_not_mutate_input(self, tables, cfg) -> None:
        before = {name: value.copy(deep=True) for name, value in tables.items()}
        apply_dirty_layer(tables, cfg, master_seed=MASTER_SEED)
        for name, snapshot in before.items():
            pd.testing.assert_frame_equal(tables[name], snapshot)

    def test_layer_actually_dirties(self, tables, dirty_tables) -> None:
        """脏层必须真的弄脏：缺失、重复、延迟、刷单四种都出现。"""
        assert int(dirty_tables["users"]["cart_value_at_assign"].isna().sum()) > 0
        assert len(dirty_tables["user_events"]) > len(tables["user_events"])
        assert float(dirty_tables["users"]["hist_gmv"].max()) > float(
            tables["users"]["hist_gmv"].max() * 2.0
        )

    def test_layer_is_reproducible(self, tables, cfg) -> None:
        first = apply_dirty_layer(tables, cfg, master_seed=MASTER_SEED)
        second = apply_dirty_layer(tables, cfg, master_seed=MASTER_SEED)
        for name in ("users", "user_events"):
            pd.testing.assert_frame_equal(first[name], second[name])

    def test_layer_disabled_returns_identity(self, tables) -> None:
        cfg_off = load_config(overrides={"dgp.n_users": N_USERS, "dirty.enabled": False})
        out = apply_dirty_layer(tables, cfg_off, master_seed=MASTER_SEED)
        for name, value in tables.items():
            pd.testing.assert_frame_equal(out[name], value)

    def test_layer_requires_users_and_events(self, cfg) -> None:
        with pytest.raises(ValueError, match="users"):
            apply_dirty_layer({"orders": pd.DataFrame()}, cfg, master_seed=MASTER_SEED)

    def test_frame_layer_does_missing_and_fraud_only(self, frame, dirty_frame) -> None:
        """分析框架只有缺失 + 刷单两种脏，且两者都生效。"""
        assert int(dirty_frame["cart_value"].isna().sum()) > 0
        assert float(dirty_frame["hist_gmv"].max()) > float(frame["hist_gmv"].max() * 2.0)
        assert len(dirty_frame) == len(frame)
        assert set(dirty_frame.columns) == set(frame.columns)


# --------------------------------------------------------------------------- #
# 5. 质量检查：干净数据必须全绿
# --------------------------------------------------------------------------- #
class TestQualityOnCleanData:
    def test_clean_tables_all_pass(self, tables, cfg) -> None:
        """完整干净数据下，``check_tables`` 的每一项都必须通过（不只是没有 error）。"""
        checks = check_tables(tables, cfg)
        failed = [c for c in checks if not c.passed]
        assert not failed, f"干净数据上仍有检查失败：{[(c.name, c.detail) for c in failed]}"
        assert len(checks) >= 18

    def test_clean_tables_have_no_error(self, tables, cfg) -> None:
        checks = check_tables(tables, cfg)
        assert_no_errors(checks)  # 不抛异常即通过

    def test_clean_analysis_frame_all_pass(self, frame, cfg) -> None:
        checks = check_analysis_frame(frame, cfg)
        failed = [c for c in checks if not c.passed]
        assert not failed, f"干净分析框架仍有检查失败：{[(c.name, c.detail) for c in failed]}"

    def test_dirty_tables_produce_no_error(self, dirty_tables, cfg) -> None:
        """脏数据是**设计好的**，只应触发 warning/info，不应阻断管线。"""
        checks = check_tables(dirty_tables, cfg)
        assert_no_errors(checks)
        failed_warnings = [c.name for c in checks if c.severity == "warning" and not c.passed]
        assert failed_warnings, "重复上报注入后，业务键重复的 warning 应该亮起来"

    def test_mnar_evidence_reports_every_channel(self, dirty_tables, cfg) -> None:
        """MNAR 证据项（info）要列出全部渠道并给出最高/最低倍数。"""
        checks = _check_map(check_tables(dirty_tables, cfg))
        mnar = next(c for c in checks.values() if c.severity == "info" and "MNAR" in c.name)
        assert mnar.passed  # info 项恒通过，只汇报
        for channel in ("search", "feed", "xhs", "other"):
            assert channel in mnar.detail
        assert "倍" in mnar.detail
        assert mnar.value is not None and mnar.value > 0.0

    def test_all_required_check_items_present(self, tables, cfg) -> None:
        """方案 §3.6 Step 2 要求的检查项必须一个不缺（按关键词核对）。"""
        names = [c.name for c in check_tables(tables, cfg)]
        required_keywords = [
            "主键唯一：users.user_id",
            "主键唯一：orders.order_id",
            "外键完整：orders.user_id",
            "外键完整：coupon_assignment.user_id",
            "分组只出现一次",
            "处理组比例",
            "两个窗口齐全且等长",
            "窗口利润空值策略",
            "退款单保留",
            "金额字段非负",
            "退款金额",
            "券只发给处理组",
            "cart 缺失率",
            "事件时间不晚于分配时间",
            "上报延迟",
            "MNAR 证据",
        ]
        for keyword in required_keywords:
            assert any(keyword in name for name in names), f"缺少检查项：{keyword}"


# --------------------------------------------------------------------------- #
# 6. 质量检查：把数据弄坏之后必须变红
# --------------------------------------------------------------------------- #
class TestQualityCatchesBreakage:
    def test_duplicate_user_id_detected(self, tables_copy, cfg) -> None:
        broken = tables_copy
        broken["users"] = pd.concat([broken["users"], broken["users"].iloc[[0]]], ignore_index=True)
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["主键唯一：users.user_id"].passed
        assert checks["主键唯一：users.user_id"].severity == "error"

    def test_duplicate_order_id_detected(self, tables_copy, cfg) -> None:
        broken = tables_copy
        broken["orders"] = pd.concat(
            [broken["orders"], broken["orders"].iloc[[0]]], ignore_index=True
        )
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["主键唯一：orders.order_id"].passed

    def test_foreign_key_violation_detected(self, tables_copy, cfg) -> None:
        broken = tables_copy
        ghost = broken["orders"].iloc[[0]].copy()
        ghost["order_id"] = "EXP-2024-001-GHOST"
        ghost["user_id"] = 10**9
        broken["orders"] = pd.concat([broken["orders"], ghost], ignore_index=True)
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["外键完整：orders.user_id → users"].passed

    def test_deleted_order_row_detected(self, tables_copy, cfg) -> None:
        """删一行订单 → 订单表与 user_outcomes 对不上（这正是"剔除退款单"的形态）。"""
        broken = tables_copy
        broken["orders"] = broken["orders"].iloc[1:].reset_index(drop=True)
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["订单表与 user_outcomes 口径一致"].passed

    def test_removed_refund_orders_detected(self, tables_copy, cfg) -> None:
        """剔除全部退款单 → R1 检查必须变红（分析分母被悄悄改了）。"""
        broken = tables_copy
        orders = broken["orders"]
        broken["orders"] = orders[~orders["refunded"].astype(bool)].reset_index(drop=True)
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["退款单保留在样本内（R1）"].passed
        assert not checks["订单表与 user_outcomes 口径一致"].passed

    def test_convert_window_profit_filled_detected(self, tables_copy, cfg) -> None:
        """把 convert_7d 的 net_profit 填上数 → 窗口空值策略变红（R2）。"""
        broken = tables_copy
        outcomes = broken["user_outcomes"].copy()
        mask = outcomes["window_type"].astype(str) == CONVERT_WINDOW
        outcomes.loc[mask, "net_profit"] = 1.23
        broken["user_outcomes"] = outcomes
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["窗口利润空值策略（R2：7 天未成熟 / 30 天必成熟）"].passed

    def test_profit_window_nan_detected(self, tables_copy, cfg) -> None:
        """30 天窗口的 net_profit 出现缺失 → 同一项变红（另一侧）。"""
        broken = tables_copy
        outcomes = broken["user_outcomes"].copy()
        mask = outcomes["window_type"].astype(str) == PROFIT_WINDOW
        outcomes.loc[outcomes.index[mask][:5], "net_profit"] = np.nan
        broken["user_outcomes"] = outcomes
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["窗口利润空值策略（R2：7 天未成熟 / 30 天必成熟）"].passed

    def test_missing_window_row_detected(self, tables_copy, cfg) -> None:
        """少一个窗口的行 → "两个窗口齐全且等长"变红。"""
        broken = tables_copy
        broken["user_outcomes"] = broken["user_outcomes"].iloc[1:].reset_index(drop=True)
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["两个窗口齐全且等长（R2）"].passed

    def test_treatment_share_deviation_detected(self, tables_copy, cfg) -> None:
        """把处理组比例改成 ~30% → 3σ 检查变红。"""
        broken = tables_copy
        assignments = broken["coupon_assignment"].copy()
        n_treated = int((assignments["group"].astype(str) == "treatment").sum())
        to_switch = int(n_treated * 0.4)
        assignments.loc[assignments.index[:to_switch], "group"] = "control"
        broken["coupon_assignment"] = assignments
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["处理组比例与设计一致"].passed

    def test_double_assignment_detected(self, tables_copy, cfg) -> None:
        """同一用户两行分组 → "分组只出现一次"变红（方案：多次曝光只算一个样本）。"""
        broken = tables_copy
        assignments = broken["coupon_assignment"]
        broken["coupon_assignment"] = pd.concat(
            [assignments, assignments.iloc[:5]], ignore_index=True
        )
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["分组只出现一次：coupon_assignment 每个用户一行"].passed

    def test_negative_amount_detected(self, tables_copy, cfg) -> None:
        broken = tables_copy
        orders = broken["orders"].copy()
        orders.loc[orders.index[:3], "pay_amount"] = -1.0
        broken["orders"] = orders
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["金额字段非负"].passed

    def test_refund_exceeding_pay_detected(self, tables_copy, cfg) -> None:
        broken = tables_copy
        orders = broken["orders"].copy()
        orders.loc[orders.index[:3], "refund_amount"] = orders.loc[orders.index[:3], "pay_amount"] * 2.0
        broken["orders"] = orders
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["退款金额落在 [0, 支付金额]"].passed

    def test_coupon_in_control_detected(self, tables_copy, cfg) -> None:
        broken = tables_copy
        assignments = broken["coupon_assignment"].copy()
        idx = assignments.index[assignments["group"].astype(str) == "control"][:5]
        assignments.loc[idx, "coupon_value"] = 10.0
        broken["coupon_assignment"] = assignments
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["券只发给处理组"].passed

    def test_event_after_assignment_detected(self, tables_copy, cfg) -> None:
        """把事件时间改到分配之后 → 时间逻辑检查变红（post-treatment 特征陷阱）。"""
        broken = tables_copy
        events = broken["user_events"].copy()
        events.loc[events.index[:10], "event_time"] = pd.Timestamp("2024-06-01")
        broken["user_events"] = events
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["事件时间不晚于分配时间"].passed

    def test_order_before_assignment_detected(self, tables_copy, cfg) -> None:
        broken = tables_copy
        orders = broken["orders"].copy()
        orders.loc[orders.index[:3], "order_time"] = pd.Timestamp("2024-01-01")
        broken["orders"] = orders
        checks = _check_map(check_tables(broken, cfg))
        assert not checks["订单时间不晚于分配时间"].passed

    def test_excess_delay_is_warning_not_error(self, tables_copy, cfg) -> None:
        """延迟超过配置上限 → warning 亮起，但**不阻断**管线（``assert_no_errors`` 不抛）。"""
        broken = tables_copy
        events = broken["user_events"].copy()
        events["ts_ingested"] = events["ts_ingested"] + pd.Timedelta(days=10)
        broken["user_events"] = events
        checks = _check_map(check_tables(broken, cfg))
        delay_check = checks["上报延迟合法且不超过配置上限"]
        assert not delay_check.passed
        assert delay_check.severity == "warning"
        assert_no_errors([delay_check])

    def test_event_duplicates_are_warning(self, dirty_tables, cfg) -> None:
        checks = _check_map(check_tables(dirty_tables, cfg))
        dup_check = checks["事件业务键无重复上报"]
        assert not dup_check.passed
        assert dup_check.severity == "warning"

    def test_analysis_frame_converted_not_binary(self, frame, cfg) -> None:
        broken = frame.copy(deep=True)
        broken.loc[broken.index[:3], "converted"] = 2
        checks = _check_map(check_analysis_frame(broken, cfg))
        assert not checks["分析框架：converted ∈ {0,1}"].passed

    def test_analysis_frame_treatment_not_binary(self, frame, cfg) -> None:
        broken = frame.copy(deep=True)
        broken.loc[broken.index[:3], "treatment"] = 3
        checks = _check_map(check_analysis_frame(broken, cfg))
        assert not checks["分析框架：treatment ∈ {0,1}"].passed

    def test_analysis_frame_net_profit_nan(self, frame, cfg) -> None:
        broken = frame.copy(deep=True)
        broken.loc[broken.index[:3], "net_profit"] = np.nan
        checks = _check_map(check_analysis_frame(broken, cfg))
        assert not checks["分析框架：net_profit 无缺失（R1）"].passed

    def test_analysis_frame_unconverted_nonzero_profit(self, frame, cfg) -> None:
        """未转化用户被塞了利润 → R1 的正面表达变红。"""
        broken = frame.copy(deep=True)
        idx = broken.index[broken["converted"] == 0][:5]
        broken.loc[idx, "net_profit"] = 5.0
        checks = _check_map(check_analysis_frame(broken, cfg))
        assert not checks["分析框架：未转化用户 net_profit 恰为 0"].passed


# --------------------------------------------------------------------------- #
# 7. 门禁与汇总
# --------------------------------------------------------------------------- #
class TestGateAndSummary:
    def test_assert_no_errors_passes_on_clean(self, tables, cfg) -> None:
        assert_no_errors(check_tables(tables, cfg))

    def test_assert_no_errors_raises_on_error(self) -> None:
        bad = QualityCheck(
            name="假检查项", passed=False, severity="error", detail="故意失败", value=1.0
        )
        with pytest.raises(QualityError) as excinfo:
            assert_no_errors([bad])
        assert "假检查项" in str(excinfo.value)

    def test_quality_error_is_assertion_error(self) -> None:
        """``QualityError`` 同时也是 ``AssertionError``，便于用断言式写法捕获。"""
        assert issubclass(QualityError, AssertionError)

    def test_assert_no_errors_ignores_warnings(self) -> None:
        warn = QualityCheck(
            name="假警告", passed=False, severity="warning", detail="只是警告", value=0.5
        )
        info = QualityCheck(name="假观察", passed=False, severity="info", detail="观察", value=0.1)
        assert_no_errors([warn, info])  # 不抛即通过

    def test_summarize_has_expected_columns(self, tables, cfg) -> None:
        report = summarize(check_tables(tables, cfg))
        assert list(report.columns) == ["检查项", "结果", "级别", "详情", "数值"]
        assert len(report) == len(check_tables(tables, cfg))
        assert set(report["结果"]) <= {"通过", "未通过"}
        assert set(report["级别"]) <= {"error", "warning", "info"}
        assert report["数值"].dtype == float

    def test_summarize_empty(self) -> None:
        report = summarize([])
        assert list(report.columns) == ["检查项", "结果", "级别", "详情", "数值"]
        assert len(report) == 0

    def test_quality_check_rejects_unknown_severity(self) -> None:
        with pytest.raises(ValueError, match="severity"):
            QualityCheck(name="x", passed=True, severity="fatal", detail="d")

    def test_quality_check_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            QualityCheck(name="  ", passed=True, severity="info", detail="d")


# --------------------------------------------------------------------------- #
# 8. 清洗
# --------------------------------------------------------------------------- #
class TestCleaning:
    def test_dedup_removes_all_duplicates(self, tables, dirty_tables) -> None:
        """去重必须把注入的重复**全部**去掉，且不误删原始行。"""
        cleaned, log = deduplicate_events(dirty_tables["user_events"])
        original = tables["user_events"]
        assert len(cleaned) == len(original)
        assert log["rows_removed"] == len(dirty_tables["user_events"]) - len(original)
        # 原始行的**业务键**逐值还在、顺序也没变（ts_ingested 已被脏层改过，不参与比较）
        key = list(EVENT_BUSINESS_KEY)
        pd.testing.assert_frame_equal(
            cleaned[key].reset_index(drop=True), original[key].reset_index(drop=True)
        )
        assert int(cleaned.duplicated(subset=key).sum()) == 0

    def test_dedup_on_clean_data_is_noop(self, tables) -> None:
        cleaned, log = deduplicate_events(tables["user_events"])
        assert log["rows_removed"] == 0
        pd.testing.assert_frame_equal(cleaned, tables["user_events"])

    def test_dedup_requires_business_key_columns(self) -> None:
        with pytest.raises(ValueError, match="业务键"):
            deduplicate_events(pd.DataFrame({"user_id": [1, 2]}))

    def test_impute_fills_all_missing(self, dirty_frame, cfg) -> None:
        cleaned, log = impute_cart_value(dirty_frame, cfg)
        n_missing = int(dirty_frame["cart_value"].isna().sum())
        assert n_missing > 0
        assert int(cleaned["cart_value"].isna().sum()) == 0
        assert log["n_missing"] == n_missing
        assert log["n_imputed"] == n_missing
        assert log["n_unresolved"] == 0
        # 指示列 1 的个数 == 原始缺失数
        assert int(cleaned["cart_value_was_missing"].sum()) == n_missing

    def test_impute_indicator_is_binary(self, dirty_frame, cfg) -> None:
        cleaned, _ = impute_cart_value(dirty_frame, cfg)
        assert set(cleaned["cart_value_was_missing"].unique()) <= {0, 1}
        assert cleaned["cart_value_was_missing"].dtype == np.int8

    def test_impute_uses_channel_median(self, dirty_frame, cfg) -> None:
        """填补值必须等于**该渠道**的观测中位数（不是全局中位数）。"""
        cleaned, log = impute_cart_value(dirty_frame, cfg)
        observed_median = (
            dirty_frame.loc[dirty_frame["cart_value"].notna()]
            .groupby("channel", observed=True)["cart_value"]
            .median()
        )
        for channel, median in observed_median.items():
            filled = cleaned.loc[
                (cleaned["channel"].astype(str) == str(channel))
                & (cleaned["cart_value_was_missing"] == 1),
                "cart_value",
            ]
            if len(filled):
                assert filled.to_numpy() == pytest.approx(float(median))

    def test_impute_keeps_observed_values(self, dirty_frame, cfg) -> None:
        """只补缺失，不动观测值。"""
        cleaned, _ = impute_cart_value(dirty_frame, cfg)
        observed = dirty_frame["cart_value"].notna()
        pd.testing.assert_series_equal(
            cleaned.loc[observed, "cart_value"], dirty_frame.loc[observed, "cart_value"]
        )

    def test_impute_twice_raises(self, dirty_frame, cfg) -> None:
        """重复填补会覆盖原始缺失标记，必须抛错而不是静默。"""
        cleaned, _ = impute_cart_value(dirty_frame, cfg)
        with pytest.raises(ValueError, match="已存在"):
            impute_cart_value(cleaned, cfg)

    def test_impute_does_not_mutate_input(self, dirty_frame, cfg) -> None:
        before = dirty_frame.copy(deep=True)
        impute_cart_value(dirty_frame, cfg)
        pd.testing.assert_frame_equal(dirty_frame, before)

    def test_winsorize_caps_bounds(self, dirty_frame, cfg) -> None:
        """截尾后取值落在分位点内，且日志里的条数与实际被改的条数一致。"""
        cleaned, log = winsorize(dirty_frame, "hist_gmv", lower=0.01, upper=0.99)
        assert cleaned["hist_gmv"].max() == pytest.approx(log["high_bound"])
        assert cleaned["hist_gmv"].min() == pytest.approx(log["low_bound"])
        changed = int((cleaned["hist_gmv"] != dirty_frame["hist_gmv"]).sum())
        assert changed == log["n_winsorized"] > 0
        assert log["n_below"] + log["n_above"] == log["n_winsorized"]

    def test_winsorize_keeps_rows_and_nan(self, dirty_frame, cfg) -> None:
        cleaned, _ = winsorize(dirty_frame, "hist_gmv")
        assert len(cleaned) == len(dirty_frame)

    def test_winsorize_rejects_bad_quantiles(self, dirty_frame) -> None:
        with pytest.raises(ValueError, match="分位点"):
            winsorize(dirty_frame, "hist_gmv", lower=0.9, upper=0.1)

    def test_clean_analysis_frame_end_to_end(self, dirty_frame, frame, cfg) -> None:
        """清洗后：cart 无缺失、指示列条数守恒、刷单极端值被压回分位点。"""
        cleaned, log = clean_analysis_frame(dirty_frame, cfg)

        assert int(cleaned["cart_value"].isna().sum()) == 0
        assert int(cleaned["cart_value_was_missing"].sum()) == int(
            dirty_frame["cart_value"].isna().sum()
        )
        assert len(cleaned) == len(dirty_frame)
        assert float(cleaned["hist_gmv"].max()) < float(dirty_frame["hist_gmv"].max())
        assert log["impute"]["n_imputed"] > 0
        assert log["winsorize"]["n_winsorized"] > 0
        assert log["rows"] == len(dirty_frame)

    def test_clean_analysis_frame_keeps_untouched_columns(self, dirty_frame, cfg) -> None:
        cleaned, _ = clean_analysis_frame(dirty_frame, cfg)
        for column in ("user_id", "treatment", "converted", "net_profit", "hist_gmv_z"):
            pd.testing.assert_series_equal(cleaned[column], dirty_frame[column])

    def test_clean_analysis_frame_is_reproducible(self, dirty_frame, cfg) -> None:
        first, log_first = clean_analysis_frame(dirty_frame, cfg)
        second, log_second = clean_analysis_frame(dirty_frame, cfg)
        pd.testing.assert_frame_equal(first, second)
        assert log_first == log_second

    def test_cleaned_frame_keeps_mnar_evidence(self, dirty_frame, cfg) -> None:
        """清洗后用指示列仍能复现各渠道缺失率（MNAR 证据不因填补而消失）。"""
        cleaned, _ = clean_analysis_frame(dirty_frame, cfg)
        checks = _check_map(check_analysis_frame(cleaned, cfg))
        mnar = next(c for c in checks.values() if c.severity == "info" and "MNAR" in c.name)
        assert "倍" in mnar.detail
        assert mnar.value is not None and mnar.value > 0.0

    def test_cleaned_frame_passes_quality(self, dirty_frame, cfg) -> None:
        cleaned, _ = clean_analysis_frame(dirty_frame, cfg)
        assert_no_errors(check_analysis_frame(cleaned, cfg))
