"""第一轮数据构建：五张关系表 + 脏数据层 + 质量检查 + 数据字典。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\01_build_data.py

产物
----
* ``data/*.parquet``                    —— 五张关系表（可完整重生成，不入库）
* ``data/users_raw.parquet`` 等         —— 注入了脏数据层的版本
* ``outputs/tables/r1_data_dictionary.csv`` —— 数据字典
* ``outputs/tables/r1_quality_*.csv``   —— 质量检查结果
* ``outputs/tables/r1_truth_*.csv``     —— **答案卷**（逐用户真值，严禁并入分析）

设计原则
--------
先写规范再写代码（方案 §3.6 Step 2）。数据字典与质量检查清单在这里生成，
报告的"数据模型与口径"一节直接引用它们，保证文档与数据不会漂移。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt

from causal_growth import dgp
from causal_growth.config import load_config
from causal_growth.data.cleaning import clean_analysis_frame, deduplicate_events
from causal_growth.data.dirt import apply_dirty_layer
from causal_growth.data.quality import check_tables, summarize
from causal_growth.data.tables import (
    build_analysis_frame,
    build_five_tables,
    build_truth_frame,
    cross_check_profit,
)
from causal_growth.io_utils import data_dir, ensure_dir, save_table, write_csv
from causal_growth.viz import add_source_note, save_fig

#: 数据字典：列 → (类型, 含义, 口径/取值说明)。手写是为了让"业务含义"可读，
#: 而不是从 DataFrame dtype 机械推断出一堆 object/int64。
DATA_DICTIONARY: dict[str, list[tuple[str, str, str, str]]] = {
    "users": [
        ("user_id", "int64", "用户唯一标识", "主键；同一用户全局唯一"),
        ("is_new", "int8", "是否新客", "1 = 注册 30 天内"),
        ("reg_date", "date", "注册日期", "新客近 30 天内，老客近 2 年内"),
        ("channel", "category", "获客渠道", "search / feed / xhs / other"),
        ("hist_gmv", "float64", "历史累计 GMV（元）", "新老客分两支分布"),
        ("cart_value_at_assign", "float64", "加购金额（元）", "随机分配时点快照；脏数据层会注入 MNAR 缺失"),
        ("browse_depth_7d", "int64", "近 7 天浏览事件数", "= user_events 中分配前 7 天的事件数"),
    ],
    "user_events": [
        ("user_id", "int64", "用户标识", "外键 → users.user_id"),
        ("event_type", "category", "行为类型", "page_view / add_to_cart"),
        ("event_time", "datetime", "**事件发生**时间", "统计口径必须用它，不是 ts_ingested"),
        ("sku_id", "int64", "商品标识", "—"),
        ("ts_ingested", "datetime", "日志入库时间", "受上报延迟影响；脏数据层会放大"),
    ],
    "coupon_assignment": [
        ("exp_id", "str", "实验标识", "同一实验内唯一"),
        ("user_id", "int64", "用户标识", "外键 → users.user_id；**每用户仅一行**"),
        ("group", "category", "实验分组", "treatment / control；随机分配"),
        ("coupon_value", "float64", "券面额（元）", "对照组为 0"),
        ("assign_time", "datetime", "分配时间", "两个观察窗口都以它为起点"),
    ],
    "orders": [
        ("order_id", "str", "订单唯一标识", "主键"),
        ("user_id", "int64", "用户标识", "外键 → users.user_id"),
        ("order_time", "datetime", "下单时间", "用于判定落在哪个观察窗口"),
        ("pay_amount", "float64", "支付金额（元）", "退款单也保留此列"),
        ("refund_amount", "float64", "退款金额（元）", "未退款为 0"),
        ("goods_cost", "float64", "商品成本（元）", "= pay_amount × 商品成本率"),
        ("fulfill_cost", "float64", "履约成本（元）", "配送+仓储+包材；**不可回收**"),
        ("coupon_used", "bool", "券是否核销", "仅处理组且已转化用户可能为 True"),
        ("coupon_value", "float64", "核销券面额（元）", "未核销为 0"),
        ("refunded", "bool", "是否退款", "**退款单必须保留在样本中**（R1）"),
        ("refund_time", "datetime", "退款时间", "未退款为 NaT；须在利润成熟窗口内"),
    ],
    "user_outcomes": [
        ("user_id", "int64", "用户标识", "每用户恰有 2 行（两个窗口各一行）"),
        ("window_type", "category", "观察窗口", "convert_7d / profit_30d；**等长，不得混用**"),
        ("converted", "int8", "该窗口内是否下单", "分析分母是全部随机分配用户"),
        ("gmv", "float64", "该窗口内支付金额（元）", "—"),
        ("net_profit", "float64", "净贡献利润（元）", "convert_7d 为 NaN（利润未成熟）；已含券成本（R3）"),
        ("refunded", "bool", "该窗口内是否退款", "convert_7d 为 NaN（尚未结算）"),
    ],
}


def _seed(cfg) -> int:
    return int(cfg.require("project.master_seed"))


def build_data_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for table, cols in DATA_DICTIONARY.items():
        actual = set(tables[table].columns)
        for name, dtype, meaning, note in cols:
            rows.append(
                {
                    "表": table,
                    "字段": name,
                    "类型": dtype,
                    "业务含义": meaning,
                    "口径说明": note,
                    "在表中存在": name in actual,
                }
            )
        extra = actual - {c[0] for c in cols}
        for name in sorted(extra):
            rows.append(
                {
                    "表": table, "字段": name, "类型": str(tables[table][name].dtype),
                    "业务含义": "（字典未覆盖）", "口径说明": "", "在表中存在": True,
                }
            )
    return pd.DataFrame(rows)


def plot_overview(df_clean: pd.DataFrame, cfg) -> None:
    """数据概览图：分组转化率、利润分布、分渠道转化。"""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    grp = df_clean.groupby("treatment", observed=True)["converted"].mean()
    axes[0].bar(["对照组", "处理组"], grp.to_numpy(), color=["#9E9E9E", "#1E88E5"])
    axes[0].set_ylabel("转化率")
    axes[0].set_title("分组转化率（随机分配后）")
    for i, v in enumerate(grp.to_numpy()):
        axes[0].text(i, v + 0.002, f"{v:.3f}", ha="center", fontsize=9)

    prof = df_clean["net_profit"].to_numpy()
    axes[1].hist(prof[prof != 0], bins=60, color="#2E7D32", alpha=0.85)
    axes[1].set_xlabel("人均净贡献利润（元，仅非零用户）")
    axes[1].set_ylabel("人数")
    axes[1].set_title(f"利润分布高度零膨胀\n零值占比 {(prof == 0).mean():.1%}")

    ch = (
        df_clean.groupby("channel", observed=True)
        .agg(conv=("converted", "mean"), n=("user_id", "size"))
        .sort_values("conv")
    )
    axes[2].barh(ch.index.astype(str), ch["conv"], color="#FB8C00")
    axes[2].set_xlabel("转化率")
    axes[2].set_title("分渠道转化率（异质性的来源之一）")

    add_source_note(fig, f"seed={_seed(cfg)} | n={len(df_clean)}")
    save_fig(fig, "r1_data_overview")


def main() -> int:
    cfg = load_config()
    seed = _seed(cfg)
    print(f"[config] seed={seed}  n_users={cfg.require('dgp.n_users')}")

    # ---------- 1. 生成总体与五张表 ----------
    print("[1/5] 生成 L1 总体与五张关系表 ...")
    pop = dgp.build("L1", cfg, 0)
    pop = dgp.assign_random(cfg, pop)
    tables = build_five_tables(pop, cfg)
    for name, frame in tables.items():
        print(f"      {name:<18} {len(frame):>9,} 行 × {frame.shape[1]} 列")

    # ---------- 2. 脏数据层 ----------
    print("[2/5] 注入脏数据层（MNAR 缺失 / 刷单 / 重复上报 / 事件延迟）...")
    dirty = apply_dirty_layer(tables, cfg, master_seed=seed, index=0)
    cart_col = "cart_value_at_assign"
    miss = dirty["users"][cart_col].isna()
    print(f"      cart_value 缺失 {int(miss.sum()):,} 行（{miss.mean():.2%}）")
    print(f"      user_events 行数 {len(tables['user_events']):,} → 脏后 {len(dirty['user_events']):,}")
    delay = (dirty["user_events"]["ts_ingested"] - dirty["user_events"]["event_time"]).dt.total_seconds() / 3600
    # 关键校验：延迟只影响 ts_ingested，**event_time 一个都不能被改动**
    # （去重后行数会变，所以比的是事件时间取值的集合，而不是逐行对齐）
    et_unchanged = set(dirty["user_events"]["event_time"]) == set(tables["user_events"]["event_time"])
    print(f"      上报延迟最大 {delay.max():.1f} 小时；event_time 未被改动：{et_unchanged}")

    # ---------- 3. 质量检查 ----------
    print("[3/5] 数据质量检查 ...")
    checks_clean = check_tables(tables, cfg)
    checks_dirty = check_tables(dirty, cfg)
    for label, checks in (("干净数据", checks_clean), ("脏数据", checks_dirty)):
        s = summarize(checks)
        failed = [c.name for c in checks if not c.passed]
        print(f"      [{label}] 共 {len(checks)} 项，通过 {sum(c.passed for c in checks)} 项，"
              f"失败 {failed}")
        if label == "脏数据" and failed:
            print(f"      → 预期失败项（正是脏数据层注入的问题，去重/填补后应恢复）：{failed}")
        write_csv(s, data_dir() / f"quality_{'clean' if label == '干净数据' else 'dirty'}.csv")
        save_table(s, f"r1_quality_{'clean' if label == '干净数据' else 'dirty'}")

    # ---------- 4. 清洗演示 ----------
    print("[4/5] 清洗演示（去重 / 按渠道中位数填补 / 截尾）...")
    deduped, dedup_log = deduplicate_events(dirty["user_events"])
    print(f"      事件去重：{len(dirty['user_events']):,} → {len(deduped):,}（移除 {dedup_log}）")

    # 分析框架也必须走一遍"污染 → 清洗"，否则清洗演示是空转
    from causal_growth.data.dirt import apply_dirty_to_frame

    df_raw = apply_dirty_to_frame(build_analysis_frame(pop, cfg), cfg, master_seed=seed, index=0)
    df_clean, clean_log = clean_analysis_frame(df_raw, cfg)
    impute = clean_log["impute"]
    print(f"      分析框架：缺失 {impute['n_missing']:,} 行 → 填补 {impute['n_imputed']:,} 行，"
          f"残留缺失 {impute['n_unresolved']}")
    print(f"      分渠道填补中位数：{ {k: round(v, 2) for k, v in impute['fill_values'].items()} }")
    print(f"      截尾：{clean_log['winsorize']['n_winsorized']:,} 行（未删除任何行）")

    # ---------- 5. 落盘 ----------
    print("[5/6] 落盘 ...")
    out = ensure_dir(data_dir())
    for name, frame in tables.items():
        write_csv(frame, out / f"{name}.csv")
    for name, frame in dirty.items():
        write_csv(frame, out / f"{name}_dirty.csv")
    write_csv(deduped, out / "user_events_deduped.csv")

    save_table(build_data_dictionary(tables), "r1_data_dictionary")
    save_table(df_clean, "r1_analysis_frame_clean")
    save_table(build_truth_frame(pop), "r1_truth_L1")  # 答案卷，另存
    save_table(summarize(checks_dirty), "r1_quality_dirty")

    # 两条利润路径一致性（GOAL 验收项 ⑤⑦ 的机器证据）
    cc = cross_check_profit(pop, cfg, tables)
    max_diff = float(cc["diff"].abs().max())
    # 容差的算法依据：关系表里每个金额字段按**分**存储（round(2)），
    # 单笔订单 3 个金额字段（pay / goods / fulfill）各带 ≤0.005 元舍入，
    # 复购用户有 2 笔订单 → 上限约 6×0.005 = 0.03 元。取 0.05 元留余量。
    tol = 0.05
    save_table(
        pd.DataFrame(
            [{
                "对比": "快速路径 vs 关系表聚合",
                "用户数": len(cc),
                "最大绝对差_元": max_diff,
                "平均绝对差_元": float(cc["diff"].abs().mean()),
                "容差_元": tol,
                "结论": "一致（差异仅来自金额按分存储的舍入）" if max_diff <= tol else "**不一致，需排查**",
            }]
        ),
        "r1_profit_crosscheck",
    )
    print(f"      两条利润路径最大差 {max_diff:.4f} 元（容差 {tol} 元 = 两单×3 字段按分存储的舍入上限）")

    # 复购路径的可核对数字：第二单有多少人、值多少钱、折算到全体用户是多少。
    # 正文的 13.98 / 17,555 / 0.088 / 13% 必须来自这张表，而不是手算。
    from causal_growth.data.profit import compute_order_components

    ord_net = tables["orders"].copy()
    ord_net["net_profit"] = compute_order_components(ord_net, cfg)["net_profit"].to_numpy()
    ord_net = ord_net.sort_values(["user_id", "order_time"], kind="stable")
    ord_net["seq"] = ord_net.groupby("user_id", observed=True).cumcount()
    second = ord_net[ord_net["seq"] == 1]
    n_users = len(pop)
    truth_ate = float(np.mean(pop.truth.cate_profit))
    repeat_sum = float(second["net_profit"].sum())
    repeat_per_user = repeat_sum / n_users
    save_table(
        pd.DataFrame(
            [
                {"项": "多单用户数", "值": float(second["user_id"].nunique()), "单位": "人",
                 "说明": "订单表里同一 user_id 出现两次的用户"},
                {"项": "第二单单均净贡献", "值": float(second["net_profit"].mean()), "单位": "元/单",
                 "说明": "复购单不带券；退款按其自身标记核算"},
                {"项": "第二单净贡献合计", "值": repeat_sum, "单位": "元",
                 "说明": "全部第二单之和"},
                {"项": "折算到全体用户", "值": repeat_per_user, "单位": "元/人",
                 "说明": "第二单合计 ÷ 全部被分配用户（R1 分母）"},
                {"项": "L1 真值 ITT（解析）", "值": truth_ate, "单位": "元/人",
                 "说明": "作为复购占比的分母"},
                {"项": "占真值 ITT 比例", "值": repeat_per_user / truth_ate, "单位": "比例",
                 "说明": "复购被静默丢弃时利润低估的量级"},
            ]
        ),
        "r1_repeat_check",
    )
    print(f"      复购核对：{second['user_id'].nunique():,} 人二单，合计 {repeat_sum:,.0f} 元，"
          f"折合 {repeat_per_user:.4f} 元/人（真值 ITT 的 {repeat_per_user / truth_ate:.1%}）")

    # ---------- 6. 落库到 SQLite 并跑 SQL 分析（核心数据能力） ----------
    print("[6/6] 建立 SQLite 数据库并执行 SQL 分析 ...")
    from causal_growth.data.sql_layer import SQLStore, build_database, list_queries

    db_path = build_database(tables, cfg, verbose=True)
    store = SQLStore(db_path)
    print(f"      库文件 {db_path.name}（{db_path.stat().st_size / 1024 / 1024:.1f} MB）"
          f"  表 {len(store.tables())} / 视图 {len(store.views())} / 命名查询 {len(list_queries())}")

    sql_itt = store.run("itt_difference").iloc[0]
    print(f"      SQL 口径 ITT：利润 {sql_itt['itt_net_profit']:+.4f} 元/人，"
          f"转化 {sql_itt['itt_conversion']:+.4f}，GMV {sql_itt['itt_gmv']:+.4f} 元/人")

    for query_name in (
        "channel_funnel",
        "new_vs_returning",
        "daily_rollup",
        "itt_group_summary",
        "qc_treatment_share",
        "qc_refund_retention",
    ):
        save_table(store.run(query_name), f"r1_sql_{query_name}")
    print("      已落盘 6 张 SQL 分析结果表（outputs/tables/r1_sql_*.csv）")

    checks = {
        "孤儿订单": int(store.run("qc_orphan_orders").iloc[0, 0]),
        "重复分配": int(store.run("qc_multi_assignment").iloc[0, 0]),
        "窗口异常用户": int(store.run("qc_window_integrity").iloc[0, 0]),
        "转化窗口含利润": int(store.run("qc_convert_window_profit_must_be_null").iloc[0, 0]),
        "对照组持有券": int(store.run("qc_coupon_only_in_treatment").iloc[0, 0]),
    }
    if any(v != 0 for v in checks.values()):
        raise RuntimeError(f"SQL 质量门禁未通过：{checks}")
    print(f"      SQL 质量门禁：{[f'{k}={v}' for k, v in checks.items()]}，全部通过")

    plot_overview(df_clean, cfg)

    print(f"\n[done] 数据 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
