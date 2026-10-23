"""SQL 数据层测试：结构约束、视图口径、与 pandas 路径的交叉一致性。

这一组测试证明"SQL 层不是演示，而是权威口径"：
同一条口径（R1/R2/R3）在 SQL 与 pandas 两条独立实现上必须给出同一个数。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causal_growth import dgp
from causal_growth.config import load_config
from causal_growth.data.sql_layer import SQLStore, build_database, list_queries, load_query_sql
from causal_growth.data.tables import build_analysis_frame, build_five_tables


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    cfg = load_config(overrides={"dgp.n_users": 4000})
    pop = dgp.assign_random(cfg, dgp.build("L1", cfg, 0))
    tables = build_five_tables(pop, cfg)
    db = tmp_path_factory.mktemp("sql") / "test.db"
    build_database(tables, cfg, path=db)
    return cfg, pop, tables, SQLStore(db)


class TestStructure:
    def test_tables_and_views_created(self, env) -> None:
        _, _, _, store = env
        assert set(store.tables()) == {
            "users",
            "user_events",
            "coupon_assignment",
            "orders",
            "user_outcomes",
        }
        assert "v_user_profit" in store.views()
        assert "v_outcome_profit" in store.views()

    def test_query_registry_is_nonempty(self) -> None:
        names = list_queries()
        assert len(names) >= 15
        for required in ("dedup_events", "profit_by_user", "itt_difference", "channel_funnel"):
            assert required in names

    def test_every_query_is_syntactically_valid(self, env) -> None:
        """逐个查询执行一次，确保没有语法错误与缺表。"""
        _, _, _, store = env
        with store.connect() as conn:
            for name, sql in load_query_sql().items():
                pd.read_sql_query(sql, conn)  # 不通过即抛异常


class TestSchemaConstraints:
    """DDL 里的 CHECK 必须真的能挡住违反口径的写入。"""

    def test_control_group_cannot_hold_coupon(self, env) -> None:
        _, _, _, store = env
        with store.connect() as conn:
            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO coupon_assignment VALUES ('X', 1, 'control', 10.0, '2024-03-01 00:00:00')"
                )

    def test_refund_cannot_exceed_payment(self, env) -> None:
        _, _, _, store = env
        with store.connect() as conn:
            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO orders VALUES "
                    "('T1', 1, '2024-03-02 00:00:00', 100.0, 120.0, 60.0, 5.0, 0, 0.0, 1, '2024-03-05 00:00:00')"
                )

    def test_convert_window_cannot_carry_profit(self, env) -> None:
        """R2：转化窗口的 net_profit 必须为 NULL。"""
        _, _, _, store = env
        with store.connect() as conn:
            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO user_outcomes VALUES (1, 'convert_7d', 1, 100.0, 12.3, NULL)"
                )

    def test_user_can_be_assigned_only_once(self, env) -> None:
        _, _, _, store = env
        with store.connect() as conn:
            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO coupon_assignment VALUES "
                    "('X', 1, 'treatment', 10.0, '2024-03-01 00:00:00')"
                )


class TestSQLMatchesPandas:
    """SQL 与 pandas 两条路径必须逐用户一致。"""

    def test_user_profit_identical(self, env) -> None:
        cfg, pop, _, store = env
        sql_df = store.run("profit_by_user").set_index("user_id")["net_profit"]
        pd_df = build_analysis_frame(pop, cfg).set_index("user_id")["net_profit"]
        joined = pd.concat([sql_df.rename("sql"), pd_df.rename("pandas")], axis=1)
        # 库内金额按分存储，容差 0.02 元
        assert np.abs(joined["sql"] - joined["pandas"]).max() <= 0.02

    def test_non_converted_users_get_zero_not_dropped(self, env) -> None:
        """R1：分母是全部被分配用户。"""
        cfg, pop, tables, store = env
        df = store.run("profit_by_user")
        assert len(df) == len(pop)
        assert (tables["orders"]["user_id"].nunique() < len(df))
        assert (df["net_profit"] == 0).mean() > 0.5

    def test_itt_difference_matches_pandas(self, env) -> None:
        cfg, pop, _, store = env
        row = store.run("itt_difference").iloc[0]
        frame = build_analysis_frame(pop, cfg)
        t = frame["treatment"] == 1
        sql_itt = float(row["itt_net_profit"])
        pd_itt = float(frame.loc[t, "net_profit"].mean() - frame.loc[~t, "net_profit"].mean())
        # 库内金额按分存储：单用户误差上限约 0.015 元，均值上的残差约 1e-5 量级
        assert sql_itt == pytest.approx(pd_itt, abs=1e-3)

        sql_conv = float(row["itt_conversion"])
        pd_conv = float(frame.loc[t, "converted"].mean() - frame.loc[~t, "converted"].mean())
        assert sql_conv == pytest.approx(pd_conv, abs=1e-12)


class TestWindowViews:
    def test_two_windows_per_user(self, env) -> None:
        _, pop, _, store = env
        df = store.run("outcomes_both_windows")
        assert len(df) == 2 * len(pop)
        assert set(df["window_type"]) == {"convert_7d", "profit_30d"}

    def test_convert_window_profit_is_null(self, env) -> None:
        _, _, _, store = env
        df = store.run("outcomes_both_windows")
        conv = df[df["window_type"] == "convert_7d"]
        assert conv["net_profit"].isna().all()

    def test_profit_window_has_no_null_profit(self, env) -> None:
        _, _, _, store = env
        prof = store.run("outcomes_both_windows").query("window_type == 'profit_30d'")
        assert prof["net_profit"].notna().all()


class TestQualityGateQueries:
    def test_duplicate_events_detected(self, env) -> None:
        _, _, tables, store = env
        # 注入一条完全重复的事件
        dup = tables["user_events"].iloc[[0]]
        with store.connect() as conn:
            dup.to_sql("user_events", conn, if_exists="append", index=False)
        assert store.scalar("qc_duplicate_events") >= 1

    def test_orphan_orders_zero(self, env) -> None:
        _, _, _, store = env
        assert store.scalar("qc_orphan_orders") == 0

    def test_multi_assignment_zero(self, env) -> None:
        _, _, _, store = env
        assert store.scalar("qc_multi_assignment") == 0

    def test_treatment_share_near_design(self, env) -> None:
        cfg, _, _, store = env
        df = store.run("qc_treatment_share").set_index("grp")["share"]
        assert df["treatment"] == pytest.approx(
            float(cfg.require("experiment.treatment_share")), abs=0.03
        )


class TestBusinessQueries:
    def test_channel_funnel_covers_all_channels(self, env) -> None:
        cfg, _, _, store = env
        df = store.run("channel_funnel")
        assert set(df["channel"]) == set(cfg.section("business")["channels"])

    def test_new_vs_returning_has_four_rows(self, env) -> None:
        _, _, _, store = env
        df = store.run("new_vs_returning")
        assert len(df) == 4
        assert set(df["segment"]) == {"new", "returning"}

    def test_daily_rollup_totals_match(self, env) -> None:
        _, pop, _, store = env
        df = store.run("daily_rollup")
        assert df["n_assigned"].sum() == len(pop)
