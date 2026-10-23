"""清洗：把脏数据层制造的四类脏变成可分析的数据，并把每一步记成日志。

本模块回答方案里的哪个问题
--------------------------
《项目方案思路.md》§3.5 的脏数据层只负责"变脏"；真正要展示的是**清洗能力**
——"发现问题 → 对症处理 → 留下可追溯的日志"。所以本模块的每个函数都返回
``(清洗后数据, 日志字典)``：日志里的数字（去重多少行、填补多少条、截尾多少条）
正是报告里要引用、且要能对上 ``quality`` 检查结果的那几个数。

四个函数，对应四类脏
--------------------
============================  ==========================================
函数                           处理什么 / 为什么这么做
============================  ==========================================
``deduplicate_events``        重复上报 → 按**业务键**去重（不是整行）
``impute_cart_value``         MNAR 缺失 → 渠道内中位数 + **缺失指示列**
``winsorize``                 刷单极端值 → 分位数截尾（不删行）
``clean_analysis_frame``      编排：先填补、再截尾
============================  ==========================================

两条不容商量的原则
------------------
1. **不删行、不删列**：退款订单、未转化用户、极端值用户都留在样本里
   （GOAL.md R1）。截尾只是把值拉回分位点，行还在；填补只是补值，
   还额外留一个指示列。任何"删掉就干净了"的操作都会改变分析分母。
2. **纯函数**：输入不被修改，全部返回新对象——"清洗前 / 清洗后"的对比
   必须能在同一个进程里对同一份数据做两遍。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from causal_growth.data.dirt import FRAUD_COLUMN, FRAME_CART_COLUMN

__all__ = [
    "EVENT_BUSINESS_KEY",
    "clean_analysis_frame",
    "deduplicate_events",
    "impute_cart_value",
    "winsorize",
]

#: 事件的**业务键**：``ts_ingested`` 不在其中，因为它是入库时间、不是事件身份。
#: 重复上报的正确判据就是这四个字段全等（见 ``quality._check_event_key_duplicates``）。
EVENT_BUSINESS_KEY: tuple[str, ...] = ("user_id", "event_type", "event_time", "sku_id")

#: 分析框架里渠道列的名字（填补时按它分组）
CHANNEL_COLUMN: str = "channel"


# --------------------------------------------------------------------------- #
# 1. 去重
# --------------------------------------------------------------------------- #
def deduplicate_events(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """按业务键去掉重复上报的事件行，保留**首次**出现的那一行。

    参数
    ----
    events : ``user_events`` 表（至少含 ``EVENT_BUSINESS_KEY`` 四列）。

    返回
    ----
    ``(去重后表, 日志)``。日志键：``key / rows_before / rows_after /
    rows_removed / rows_removed_rate``。

    为什么按业务键而不是 ``drop_duplicates()``
    -----------------------------------------
    整行去重依赖"重复行的 ``ts_ingested`` 也一模一样"。这在"同一次入库批次
    里重放"时成立，但一旦上报延迟让同一事件的两次入库时间不同，
    整行去重就完全失效——重复行会被当成两条不同的行为留下。
    事件身份由 ``(user_id, event_type, event_time, sku_id)`` 决定，
    ``ts_ingested`` 只是这条记录**什么时候被写进库**，与"发生了什么"无关。

    保留 ``first`` 而不是任意一条：原行按事件顺序排在前面，重复行是后来
    重放追加的，保留 first 等价于"保留最早入库的那条"，语义正确且可复现。
    """
    missing = [c for c in EVENT_BUSINESS_KEY if c not in events.columns]
    if missing:
        raise ValueError(
            f"deduplicate_events：user_events 缺少业务键列 {missing}；"
            f"现有列：{list(events.columns)}"
        )

    out = events.drop_duplicates(subset=list(EVENT_BUSINESS_KEY), keep="first")
    out = out.reset_index(drop=True)
    n_before = int(len(events))
    n_after = int(len(out))
    n_removed = n_before - n_after
    log: dict[str, Any] = {
        "key": list(EVENT_BUSINESS_KEY),
        "rows_before": n_before,
        "rows_after": n_after,
        "rows_removed": n_removed,
        "rows_removed_rate": (n_removed / n_before) if n_before else 0.0,
    }
    return out, log


# --------------------------------------------------------------------------- #
# 2. 缺失填补
# --------------------------------------------------------------------------- #
def impute_cart_value(
    df: pd.DataFrame,
    cfg: Any,
    *,
    column: str = FRAME_CART_COLUMN,
    channel_col: str = CHANNEL_COLUMN,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """按**渠道内中位数**填补购物车金额，并新增 ``<column>_was_missing`` 指示列。

    参数
    ----
    df : 含 ``column`` 与 ``channel_col`` 的用户级表（分析框架用默认列名，
         ``users`` 表需传 ``column="cart_value_at_assign"``）。
    cfg : 配置对象；``business.cart_value_min`` 作为填补值的业务下限
        （小样本渠道的中位数理论上可能落到不可能的低价区间，用业务下限兜底）。
    column, channel_col : 列名。

    返回
    ----
    ``(填补后表, 日志)``。日志键：``column / indicator_column / rows /
    n_missing / missing_rate / n_imputed / n_unresolved / fill_values /
    global_median / n_channels``。

    为什么是"渠道内"中位数
    ----------------------
    缺失是 MNAR：不同渠道的埋点质量不同，缺失概率与渠道相关
    （见 ``dirt.add_missing_cart_value``）。用**全局**中位数填补，等于假设
    "缺失者的购物车金额与全体同分布"，而实际上缺失集中在某个渠道——
    那个渠道的真实金额分布若与全局不同，填补值就系统性偏移。
    渠道内中位数至少让填补值与该渠道的观测分布对齐。

    为什么必须留指示列
    ------------------
    就算按渠道填补，剩下的不确定性也没有消失：缺失者与同渠道的非缺失者
    仍然可能不同（MNAR 的定义就是如此）。指示列把这个不确定性**显式**交给
    下游——CATE 模型能自己学"缺失的人是不是更难转化"，报告里也能说
    "做了敏感性分析：带/不带指示列，结论是否一致"。直接丢信息（
    ``dropna()``）则会同时丢掉样本量和这条线索，是最差的选择。

    中位数仍是 NaN 时（整列全缺失 / 渠道全缺失）退回全局中位数；
    全局中位数也没有就抛错——不猜、不填 0。
    """
    missing_cols = [c for c in (column, channel_col) if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"impute_cart_value：缺少列 {missing_cols}；现有列：{list(df.columns)}"
        )
    indicator = f"{column}_was_missing"
    if indicator in df.columns:
        raise ValueError(
            f"impute_cart_value：{indicator!r} 已存在，说明这份数据已经填补过；"
            "重复填补会覆盖原始的缺失标记，丢失 MNAR 证据"
        )

    out = df.copy()
    was_missing = out[column].isna()
    n_rows = int(len(out))
    n_missing = int(was_missing.sum())
    out[indicator] = was_missing.astype("int8")

    # 渠道内中位数（observed=True 避免分类变量的空类别告警）
    channel_median = out.groupby(channel_col, observed=True)[column].median()
    channel_map = {
        str(name): float(value) for name, value in channel_median.items() if pd.notna(value)
    }
    global_median = float(out[column].median()) if n_rows and out[column].notna().any() else np.nan
    if not np.isfinite(global_median):
        raise ValueError(
            f"impute_cart_value：{column!r} 全为缺失，无法确定任何中位数；"
            "请检查上游是否真的产出了该列"
        )

    # 显式 astype(str/float)：渠道列是 category 时 map 会返回 Categorical，
    # 后续不能做数值比较（pandas 只允许无序分类做相等判断）。
    fill_values = out[channel_col].astype(str).map(channel_map).astype(float)
    # 业务下限兜底：只作用在填补值上，不改动任何观测到的值
    min_value = cfg.get("business.cart_value_min") if hasattr(cfg, "get") else None
    if min_value is not None:
        fill_values = fill_values.where(fill_values >= float(min_value), float(min_value))
    fill_values = fill_values.fillna(global_median)

    out[column] = out[column].fillna(fill_values).astype(float)
    n_imputed = int((was_missing & out[column].notna()).sum())
    n_unresolved = int(out[column].isna().sum())

    log: dict[str, Any] = {
        "column": column,
        "indicator_column": indicator,
        "rows": n_rows,
        "n_missing": n_missing,
        "missing_rate": (n_missing / n_rows) if n_rows else 0.0,
        "n_imputed": n_imputed,
        "n_unresolved": n_unresolved,
        "n_channels": int(len(channel_median)),
        "global_median": float(global_median),
        "fill_values": {str(k): float(v) for k, v in channel_median.items() if pd.notna(v)},
    }
    return out, log


# --------------------------------------------------------------------------- #
# 3. 截尾
# --------------------------------------------------------------------------- #
def winsorize(
    df: pd.DataFrame,
    column: str,
    *,
    lower: float = 0.01,
    upper: float = 0.99,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """把 ``column`` 截尾到 ``[lower, upper]`` 分位点之间（不删行、不改缺失）。

    参数
    ----
    df : 含 ``column`` 的表。
    column : 数值列名（本项目用来处理刷单污染的 ``hist_gmv``）。
    lower, upper : 分位点，必须满足 ``0 <= lower < upper <= 1``。

    返回
    ----
    ``(截尾后表, 日志)``。日志键：``column / lower / upper / low_bound /
    high_bound / n_below / n_above / n_winsorized / rows``。

    为什么用截尾而不是删掉刷单用户
    ------------------------------
    刷单用户是**真实存在的用户**，他们同样被随机分配到处理组/对照组。
    删掉他们会：
    ① 改变分析分母（R1 的反面）；
    ② 若刷单与渠道/新老客相关，删行会引入选择偏差。
    截尾保留行、只把极端金额拉回分位点，既压住了对均值/方差/排序的支配
    作用，又不丢样本。代价是这少数用户的金额不再是真实值——这一点必须在
    报告里写明（截尾影响的人数和分位点边界都在日志里）。

    NaN 不参与分位数计算，也不会被写入（``clip`` 保持 NaN）。
    """
    if column not in df.columns:
        raise ValueError(f"winsorize：缺少列 {column!r}；现有列：{list(df.columns)}")
    if not 0.0 <= float(lower) < float(upper) <= 1.0:
        raise ValueError(
            f"winsorize：分位点必须满足 0 <= lower < upper <= 1，收到 {lower} / {upper}"
        )
    out = df.copy()
    series = out[column]
    n_valid = int(series.notna().sum())
    if n_valid == 0:
        raise ValueError(f"winsorize：{column!r} 全为缺失，无法计算分位数")

    low_bound = float(series.quantile(float(lower)))
    high_bound = float(series.quantile(float(upper)))
    below = series < low_bound
    above = series > high_bound
    n_below = int(below.sum())
    n_above = int(above.sum())

    out[column] = series.clip(lower=low_bound, upper=high_bound)
    log: dict[str, Any] = {
        "column": column,
        "lower": float(lower),
        "upper": float(upper),
        "low_bound": low_bound,
        "high_bound": high_bound,
        "n_below": n_below,
        "n_above": n_above,
        "n_winsorized": n_below + n_above,
        "rows": int(len(out)),
    }
    return out, log


# --------------------------------------------------------------------------- #
# 4. 编排
# --------------------------------------------------------------------------- #
def clean_analysis_frame(
    df: pd.DataFrame,
    cfg: Any,
    *,
    lower: float = 0.01,
    upper: float = 0.99,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """分析框架的标准清洗流程：**先填补缺失，再对历史 GMV 截尾**。

    参数
    ----
    df : 脏的（或干净的）分析框架，``build_analysis_frame`` 的输出。
    cfg : 配置对象。
    lower, upper : 截尾分位点（默认 1% / 99%，改它等于改实验条件，
        必须写进报告）。

    返回
    ----
    ``(清洗后框架, 日志)``。日志结构::

        {"rows": 3000,
         "impute":    {...impute_cart_value 的日志...},
         "winsorize": {...winsorize 的日志...},
         "notes": [...]}

    **顺序不能反**：先截尾再填补，分位点会被刷单极端值拉高（刷单值可能
    占到上分位的份额），填补用的中位数不受影响但截尾边界会失真。
    先填补、再截尾时，填补值参与分位数计算——它们是同渠道中位数，
    不会把右尾拉长；这个顺序与"先把数据补全、再做稳健化"的常规做法一致。

    不做什么
    --------
    **不重算 ``*_z`` 列。** z 值是分配时点固化的快照（``dirt`` 模块文档里
    说明了原因），清洗只在原始字段上做。这意味着清洗后 ``hist_gmv`` 与
    ``hist_gmv_z`` 会轻微不自洽：谁要用 z 值做建模，必须自己在 ETL 层
    按清洗后的 ``hist_gmv`` 重算，并把这个改动写进数据字典。
    """
    out = df.copy()
    out, impute_log = impute_cart_value(out, cfg, column=FRAME_CART_COLUMN)
    out, winsor_log = winsorize(out, FRAUD_COLUMN, lower=lower, upper=upper)
    log: dict[str, Any] = {
        "rows": int(len(out)),
        "impute": impute_log,
        "winsorize": winsor_log,
        "notes": [
            "缺失按渠道内中位数填补，并留 cart_value_was_missing 指示列（MNAR）",
            f"只对 {FRAUD_COLUMN} 做 {lower:.0%}/{upper:.0%} 分位截尾，未删除任何行",
            "未重算 *_z 列：z 值是分配时点快照，重算需在 ETL 层进行",
        ],
    }
    return out, log
