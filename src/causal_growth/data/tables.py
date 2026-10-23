"""数据表构造：五张关系表 + 快速分析框架 + 真值卷。

三个层次，各有明确用途
----------------------
1. ``analysis_arrays``  —— **快速路径**（numpy），重复实验 R=200~500 次时用。
   百万次调用也要够快，不能每次都拼 DataFrame。
2. ``build_analysis_frame`` —— 给单次分析、诊断图、报表用。
3. ``build_five_tables`` —— **数据交付物**：``users`` / ``user_events`` /
   ``coupon_assignment`` / ``orders`` / ``user_outcomes`` 五张关系表，
   配数据字典使用，展示数据工程能力。

三条路径的利润数字必须**完全一致**——由 ``tests/test_tables.py`` 的
交叉一致性测试守住。任何一条路径自己实现一份利润公式，都是口径错配的开始。

真值单独存放
------------
``build_truth_frame`` 产出的是**答案卷**（逐用户 τ、p0、p1）。
它只供评估使用，**绝不并入分析框架**——否则就是"用真值训练"。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from causal_growth.contracts import CONVERT_WINDOW, FEATURE_ORDER, PROFIT_WINDOW, Population
from causal_growth.data.profit import build_user_outcomes, compute_order_components

__all__ = [
    "FIVE_TABLE_NAMES",
    "analysis_arrays",
    "build_analysis_frame",
    "build_five_tables",
    "build_truth_frame",
]

FIVE_TABLE_NAMES: tuple[str, ...] = (
    "users",
    "user_events",
    "coupon_assignment",
    "orders",
    "user_outcomes",
)


# --------------------------------------------------------------------------- #
# 快速路径
# --------------------------------------------------------------------------- #
def analysis_arrays(population: Population, cfg: Any) -> dict[str, np.ndarray]:
    """返回重复实验直接可用的 numpy 数组字典（不建 DataFrame）。

    含：``user_id, treatment, converted, net_profit, gmv, refunded,
    coupon_used, coupon_value`` 与全部特征列。
    """
    if population.treatment is None:
        raise ValueError("population 尚未分配处理；请先调用 assign_random / assign_observational")

    b = cfg.section("business")
    t = population.treatment.astype(np.int8)
    y_obs, pi_obs = population.potential.observed(t)

    refund_u = population.latent.get("refund_u")
    if refund_u is None:
        raise ValueError("population.latent 缺少 'refund_u'；请用 dgp 构造总体")
    rate_ctrl = float(b["refund_rate"])
    rate_trt = rate_ctrl * float(b["refund_rate_treated_multiplier"])
    # 退款只可能发生在**已下单**的用户身上。若不乘 converted，
    # "退款标记数 / 已下单人数" 会算出 >70% 的假退款率（分母缩小、分子没缩小）。
    # 用户级退款标记 = **窗口内至少一笔订单退款**（首单或复购第二单），
    # 与 ``user_outcomes``/``v_outcome_profit`` 的 ``MAX(refunded)`` 口径一致。
    # 若只记首单，复购第二单退款的用户会被漏计（SQL 与 pandas 两条路径因此打架）。
    refunded = (refund_u < np.where(t == 1, rate_trt, rate_ctrl)) & (y_obs == 1)

    redeemed = population.latent["redeemed"]
    # 券核销的前提是**有订单**：没下单的人不可能核销券。
    # 少写这个 `& (y_obs == 1)` 会让"核销率"莫名飙到 55% 而转化率只有 15%，
    # 是一个不会报错、但一眼假的口径错误。
    coupon_used = (t == 1) & redeemed & (y_obs == 1)
    coupon_value = np.where(coupon_used, population.truth.face_value, 0.0)

    # 复购路径（B7）：已下单且复购标记为真 → 用户级 GMV 是两单之和。
    # 这条口径必须与 ``orders`` 表的逐行聚合一致，否则两条路径会算出不同的用户利润。
    repeat = np.asarray(population.latent.get("repeat", np.zeros(len(population), dtype=bool)))
    pay2 = np.asarray(population.latent.get("pay_amount_2", np.zeros(len(population))))
    has_second = (y_obs == 1) & repeat

    cov = population.covariates
    out = {
        "user_id": cov.user_id,
        "treatment": t,
        "converted": y_obs.astype(np.int8),
        "net_profit": pi_obs.astype(float),
        "gmv": np.where(
            y_obs == 1,
            np.asarray(population.latent["pay_amount"]) + np.where(has_second, pay2, 0.0),
            0.0,
        ),
        "refunded": (
            refunded | (has_second & (np.asarray(population.latent["refund_u_2"]) < np.where(
                t == 1, rate_trt, rate_ctrl)))
        ).astype(np.int8),
        "coupon_used": coupon_used.astype(np.int8),
        "coupon_value": coupon_value.astype(float),
        "n_orders": np.where(y_obs == 1, 1, 0) + has_second.astype(np.int64),
        "is_new": cov.is_new,
        "hist_gmv": cov.hist_gmv,
        "cart_value": cov.cart_value,
        "browse_depth": cov.browse_depth,
        "channel": cov.channel,
    }
    for name in ("hist_gmv_z", "cart_value_z", "browse_depth_z"):
        out[name] = getattr(cov, name)
    return out


def build_analysis_frame(population: Population, cfg: Any) -> pd.DataFrame:
    """用户级分析表（**只含可观测变量**，不含真值）。

    分析单位是随机分配的**全部用户**：未转化用户的 ``net_profit`` 记 0，
    而不是被剔出样本（GOAL.md R1）。
    """
    arr = analysis_arrays(population, cfg)
    df = pd.DataFrame(arr)
    df["channel"] = pd.Categorical(df["channel"])
    return df


def build_truth_frame(population: Population) -> pd.DataFrame:
    """**答案卷**：逐用户真值。只供评估，禁止并入分析表。"""
    truth = population.truth
    cov = population.covariates
    return pd.DataFrame(
        {
            "user_id": cov.user_id,
            "p0": truth.p0,
            "p1": truth.p1,
            "true_tau_conversion": truth.tau_conversion,
            # 这是 E[Π(1)−Π(0)|X] 的解析值，不是个体实测差
            "true_cate_profit": truth.cate_profit,
            "net_per_order_control": truth.net_per_order_control,
            "net_per_order_treated": truth.net_per_order_treated,
            # 含复购期望的"已转化用户"净贡献（真值恒等式用的是这一对）
            "net_per_converted_control": truth.net_per_converted_control,
            "net_per_converted_treated": truth.net_per_converted_treated,
        }
    )


# --------------------------------------------------------------------------- #
# 五张关系表
# --------------------------------------------------------------------------- #
def build_five_tables(
    population: Population,
    cfg: Any,
    *,
    exp_id: str = "EXP-2024-001",
) -> dict[str, pd.DataFrame]:
    """构造五张关系表（数据交付物）。

    表与粒度（方案 §2.4 主线一）：

    ==================  ==================  ===================================
    表                  粒度                关键字段
    ==================  ==================  ===================================
    ``users``           每用户一行          user_id, is_new, reg_date, channel, hist_gmv
    ``user_events``     每次行为一行        user_id, event_type, event_time, sku_id
    ``coupon_assignment`` 每次分配一行      exp_id, user_id, group, coupon_value, assign_time
    ``orders``          每笔订单一行        pay_amount, refund_amount, goods_cost, fulfill_cost, coupon_used
    ``user_outcomes``   每用户每窗口一行    window_type, converted, gmv, net_profit, refunded
    ==================  ==================  ===================================
    """
    if population.treatment is None:
        raise ValueError("population 尚未分配处理")

    cov = population.covariates
    n = len(population)
    ex_start = pd.Timestamp("2024-03-01 00:00:00")
    delay = np.asarray(population.latent["order_delay_days"])
    refund_delay = np.asarray(population.latent["refund_delay_days"])

    # ---- 分配时间：活动在 3 天内滚动铺开，每人一个时点 ----
    rollout_days = 3.0
    rank = np.argsort(np.argsort(cov.user_id)) / max(n - 1, 1)
    assign_time = ex_start + pd.to_timedelta(rank * rollout_days * 86400.0, unit="s")

    # ---- users ----
    # 注册日期用 user_id 派生抖动（确定性，不额外消耗随机流）：
    # 新客注册在近 30 天内，老客在近 2 年内。
    reg_days = np.where(
        cov.is_new == 1,
        3.0 + (cov.user_id % 27),
        180.0 + (cov.user_id % 540),
    )
    users = pd.DataFrame(
        {
            "user_id": cov.user_id,
            "is_new": cov.is_new.astype(np.int8),
            "reg_date": (ex_start - pd.to_timedelta(reg_days, unit="D")).normalize(),
            "channel": pd.Categorical(cov.channel),
            "hist_gmv": cov.hist_gmv.round(2),
            # 分配时点快照：由 user_events 上游汇总而来，落库时已固化
            "cart_value_at_assign": cov.cart_value.round(2),
            "browse_depth_7d": cov.browse_depth.astype(int),
        }
    )

    # ---- coupon_assignment ----
    t = population.treatment.astype(np.int8)
    coupon_assignment = pd.DataFrame(
        {
            "exp_id": exp_id,
            "user_id": cov.user_id,
            "group": pd.Categorical(np.where(t == 1, "treatment", "control")),
            "coupon_value": np.where(t == 1, float(population.truth.face_value), 0.0),
            "assign_time": assign_time,
        }
    )

    # ---- orders（只含已转化用户；退款单**保留**）----
    y_obs, _ = population.potential.observed(t)
    converted = y_obs.astype(bool)
    idx = np.flatnonzero(converted)

    pay = np.asarray(population.latent["pay_amount"])[idx]
    goods_cost = pay * float(cfg.require("business.goods_cost_ratio"))
    fulfill = np.asarray(population.latent["fulfill_cost"])[idx]
    order_time = assign_time[idx] + pd.to_timedelta(delay[idx] * 86400.0, unit="s")
    rate_ctrl = float(cfg.require("business.refund_rate"))
    rate_trt = rate_ctrl * float(cfg.require("business.refund_rate_treated_multiplier"))
    refunded = np.asarray(population.latent["refund_u"])[idx] < np.where(t[idx] == 1, rate_trt, rate_ctrl)
    coupon_used = (t[idx] == 1) & np.asarray(population.latent["redeemed"])[idx]

    orders = pd.DataFrame(
        {
            "order_id": [f"{exp_id}-O{u:09d}" for u in cov.user_id[idx]],
            "user_id": cov.user_id[idx],
            "order_time": order_time,
            "pay_amount": pay.round(2),
            "refund_amount": np.where(refunded, pay, 0.0).round(2),
            "goods_cost": goods_cost.round(2),
            "fulfill_cost": fulfill.round(2),
            "coupon_used": coupon_used,
            "coupon_value": np.where(coupon_used, float(population.truth.face_value), 0.0),
            "refunded": refunded,
        }
    )
    # 退款时间：只对退款单有值（NaT 表示未退款）
    refund_time = order_time + pd.to_timedelta(refund_delay[idx] * 86400.0, unit="s")
    orders["refund_time"] = pd.to_datetime(refund_time)
    orders.loc[~refunded, "refund_time"] = pd.NaT

    # ---- 复购单（第二单）：B7 让"多单用户 user 级利润 = 各单之和"可被检验 ----
    # 没有这批行，`v_user_profit` 的 MAX/SUM 之争在数据上不可观测——
    # 每个用户最多一单时，MAX 与 SUM 恒等，口径错误会静默通过所有检查。
    # 注意这里的下标维度是**订单行**（已转化用户），不是全体用户。
    repeat_row = np.asarray(population.latent.get("repeat", np.zeros(n, dtype=bool)))[idx]
    if bool(repeat_row.any()):
        jdx = np.flatnonzero(repeat_row)
        pay2 = np.asarray(population.latent["pay_amount_2"])[idx][jdx]
        goods2 = pay2 * float(cfg.require("business.goods_cost_ratio"))
        fulfill2 = fulfill[jdx]
        t2 = t[idx][jdx]
        refunded2 = np.asarray(population.latent["refund_u_2"])[idx][jdx] < np.where(
            t2 == 1, rate_trt, rate_ctrl
        )
        # 第二单时间 = 首单时间 + 复购延迟（均值 ≈ 9 天，落在 30 天利润窗口内）
        second_time = order_time[jdx] + pd.to_timedelta(
            np.asarray(population.latent["order_delay_days_2"])[idx][jdx] * 86400.0, unit="s"
        )
        second = pd.DataFrame(
            {
                "order_id": [f"{exp_id}-O{u:09d}-2" for u in cov.user_id[idx][jdx]],
                "user_id": cov.user_id[idx][jdx],
                "order_time": second_time,
                "pay_amount": pay2.round(2),
                "refund_amount": np.where(refunded2, pay2, 0.0).round(2),
                "goods_cost": goods2.round(2),
                "fulfill_cost": fulfill2.round(2),
                # 第二单不带券：券是首单转化工具，复购属自然复购
                "coupon_used": np.zeros(jdx.size, dtype=bool),
                "coupon_value": np.zeros(jdx.size, dtype=float),
                "refunded": refunded2,
            }
        )
        second["refund_time"] = pd.to_datetime(
            second_time + pd.to_timedelta(refund_delay[idx][jdx] * 86400.0, unit="s")
        )
        second.loc[~refunded2, "refund_time"] = pd.NaT
        orders = pd.concat([orders, second[orders.columns]], ignore_index=True)
        orders = orders.sort_values(["user_id", "order_time"], kind="stable").reset_index(drop=True)

    # ---- user_events（行为日志）----
    user_events = _build_user_events(population, assign_time, cfg)

    # ---- user_outcomes（每用户每窗口一行）----
    user_outcomes = build_user_outcomes(
        orders=orders,
        assignments=coupon_assignment.loc[:, ["user_id", "assign_time"]],
        all_user_ids=cov.user_id,
        cfg=cfg,
    )

    return {
        "users": users,
        "user_events": user_events,
        "coupon_assignment": coupon_assignment,
        "orders": orders,
        "user_outcomes": user_outcomes,
    }


def _build_user_events(
    population: Population, assign_time: np.ndarray, cfg: Any
) -> pd.DataFrame:
    """生成行为日志：分配前的浏览与加购事件。

    粒度是"每次行为一行"。每个用户的最后一次事件是 ``add_to_cart``——
    这正是"加购未支付"人群的定义来源。

    规模控制：单用户事件数上限取自 ``business.user_events_cap``（默认 20）。
    **超过上限的用户，``browse_depth_7d`` 仍记录真实深度，但日志只保留前 N 条**，
    因此 "browse_depth_7d == 事件计数" 只在 ``depth <= cap`` 时严格成立。
    质量检查按这个口径核对，不会误报。
    """
    cov = population.covariates
    cap = int(cfg.require("business.user_events_cap"))
    depth = np.clip(cov.browse_depth.astype(int), 0, cap)
    n_total = int(depth.sum())
    if n_total == 0:
        return pd.DataFrame(
            {
                "user_id": np.array([], dtype=np.int64),
                "event_type": pd.Categorical([], categories=["page_view", "add_to_cart"]),
                "event_time": pd.to_datetime([]),
                "sku_id": np.array([], dtype=np.int64),
                "ts_ingested": pd.to_datetime([]),
            }
        )

    user_idx = np.repeat(np.arange(len(cov)), depth)
    total_per_user = np.repeat(depth, depth)
    starts = np.concatenate(([0], np.cumsum(depth)[:-1]))
    order_in_user = np.arange(n_total) - np.repeat(starts, depth)

    # 事件均匀铺在分配前 (0, 7] 天内，按时间递增
    days_before = 7.0 * (order_in_user + 1) / (total_per_user + 1)
    event_time = assign_time[user_idx] - pd.to_timedelta(days_before * 86400.0, unit="s")

    # 最后一次行为是"加购"——之后未支付，构成目标人群
    is_add_cart = order_in_user == (total_per_user - 1)
    event_type = np.where(is_add_cart, "add_to_cart", "page_view")

    return pd.DataFrame(
        {
            "user_id": cov.user_id[user_idx],
            "event_type": pd.Categorical(event_type, categories=["page_view", "add_to_cart"]),
            "event_time": event_time,
            "sku_id": (cov.user_id[user_idx] % 5000 + 100000).astype(np.int64),
            # 上报时间：正常情况与事件时间一致；脏数据层会放大这个延迟
            "ts_ingested": event_time,
        }
    )


# --------------------------------------------------------------------------- #
# 一致性校验用
# --------------------------------------------------------------------------- #
def cross_check_profit(
    population: Population, cfg: Any, tables: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    """对比"快速路径"与"关系表聚合"两条路径算出的用户利润。

    这是 GOAL.md 验收项 ⑤⑦ 的机器化证据：同一批订单，
    两条路径必须给出同一个 net_profit。
    """
    from causal_growth.data.profit import aggregate_user_profit

    fast = build_analysis_frame(population, cfg).set_index("user_id")["net_profit"]
    slow = aggregate_user_profit(tables["orders"], population.covariates.user_id, cfg)
    return pd.DataFrame({"fast_path": fast, "table_path": slow}).assign(
        diff=lambda d: d["fast_path"] - d["table_path"]
    )
