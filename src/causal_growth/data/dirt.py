"""脏数据层：把干净的关系表 / 分析框架污染成"真实业务数据"的样子。

本模块回答方案里的哪个问题
--------------------------
《项目方案思路.md》§3.5「给模拟数据加"脏数据"层」：真实数据是脏的，模拟器
也要脏，否则"缺失机制 / 异常值处理 / 日志去重 / 事件时间口径"这些能力
全都无从展示。本模块只负责**制造**脏数据，不做任何清洗——清洗在
``causal_growth.data.cleaning``，检查在 ``causal_growth.data.quality``。
三者分工固定：脏 → 查 → 洗，任何一环越界都会让"清洗前 / 清洗后"的对比失效。

四种脏，各有各的业务来历
------------------------
1. **非随机缺失（MNAR）**：``cart_value`` 的缺失率**按渠道不同**——不同渠道
   埋点质量不同（外部渠道跳转链路最容易丢加购金额）。这是本模块最重要的
   设计取舍：如果缺失是 MCAR，"按渠道中位数填补"就是无偏的，清洗环节毫无
   难度；只有缺失概率与**观测到的渠道**相关，填补才会引入偏差、才必须留
   缺失指示列（见 ``cleaning.impute_cart_value``）。
2. **刷单异常值**：极少数用户 ``hist_gmv`` 被放大 ``fraud_gmv_multiplier`` 倍，
   给下游一个"不截尾就被极端值带偏"的陷阱。
3. **重复上报**：一部分事件行被复制（逐字段相同，含 ``ts_ingested``），模拟
   埋点重放 / 同一曝光多次上报，必须靠业务键去重。
4. **上报延迟**：``ts_ingested`` 被推后 ``[0, event_delay_max_hours]`` 小时，
   而 ``event_time`` **一点都不动**——这是整条口径链的关键：所有统计必须按
   **事件时间**而非入库时间切窗口，否则窗口边界会随延迟漂移。

三条工程约束
------------
* **纯函数**：每个函数都返回**新对象**，绝不原地改输入。上游拿到的那份干净
  数据必须还能原样使用，否则"脏 / 干净"两套对比就无从谈起。
* **可复现**：随机性一律走 ``rng.child_rng(master_seed, stream, index)``，
  四个随机流分别是 ``dirty.missing`` / ``dirty.fraud`` / ``dirty.duplicate`` /
  ``dirty.delay``（AGENTS.md §3.3）。新增一种脏数据只会引入新的 stream，
  不会扰动已有流。
* **可关闭**：``cfg.dirty.enabled = false`` 时所有函数原样返回（仍是副本），
  便于跑"无脏数据"的对照组。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from causal_growth.rng import child_rng

__all__ = [
    "STREAM_DELAY",
    "STREAM_DUPLICATE",
    "STREAM_FRAUD",
    "STREAM_MISSING",
    "USERS_CART_COLUMN",
    "add_fraud_outliers",
    "add_missing_cart_value",
    "apply_dirty_layer",
    "apply_dirty_to_frame",
    "delay_ingestion",
    "duplicate_events",
]

# --------------------------------------------------------------------------- #
# 随机流命名（AGENTS.md §3.3：新增随机流不得扰动已有流）
# --------------------------------------------------------------------------- #
STREAM_MISSING: str = "dirty.missing"
STREAM_FRAUD: str = "dirty.fraud"
STREAM_DUPLICATE: str = "dirty.duplicate"
STREAM_DELAY: str = "dirty.delay"

#: ``users`` 表里"分配时点的购物车金额"列名。与 ``build_analysis_frame`` 的
#: ``cart_value`` 是**同一口径的两个落库名**，脏数据注入必须两边都能打。
USERS_CART_COLUMN: str = "cart_value_at_assign"

#: 分析框架里购物车金额的列名（``build_analysis_frame`` 的列）
FRAME_CART_COLUMN: str = "cart_value"

#: 刷单污染的目标列（分析框架与 ``users`` 表同名列）
FRAUD_COLUMN: str = "hist_gmv"


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _plain_mapping(node: Any) -> dict[str, Any]:
    """把 ``Config`` / ``dict`` 统一成普通字典（``Config`` 的嵌套项仍是 ``Config``）。"""
    if node is None:
        return {}
    if hasattr(node, "to_dict"):
        return dict(node.to_dict())
    return dict(node)


def _dirty_params(cfg: Any) -> dict[str, Any]:
    """取出 ``dirty`` 配置段为普通字典。

    取不到就抛错而不是静默用默认值：脏数据参数决定了数据长什么样，
    悄悄换成默认值等于悄悄换掉实验条件（AGENTS.md §3.6 失败要响）。
    """
    section = cfg.get("dirty") if hasattr(cfg, "get") else None
    if section is None:
        raise ValueError("配置缺少 dirty 段；脏数据层需要 cfg.dirty（见 configs/base.yaml）")
    return _plain_mapping(section)


def _enabled(params: dict[str, Any]) -> bool:
    """``dirty.enabled`` 是否为真（缺省视为开启，与 base.yaml 一致）。"""
    return bool(params.get("enabled", True))


def _param(params: dict[str, Any], key: str) -> float:
    """读一个必需的浮点脏数据参数，缺项/非法立即报错。"""
    if key not in params:
        raise ValueError(f"dirty 段缺少参数 {key!r}；请检查 configs/base.yaml 的 dirty 段")
    return float(params[key])


def _probability(value: float, *, key: str) -> float:
    """概率类参数必须落在 [0, 1]；越界说明配置写错，不能靠 ``< p`` 蒙混过去。"""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{key} 必须落在 [0, 1] 内，收到 {value}")
    return value


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], *, where: str) -> None:
    """列不齐就抛错：脏数据注入打错列名若被静默忽略，等于没注入。"""
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{where} 缺少必需列 {missing}；现有列：{list(frame.columns)}")


def _as_float(frame: pd.DataFrame, column: str) -> None:
    """把数值列升为 float，避免往整数列写 NaN 时 pandas 报错/静默截断。"""
    if not pd.api.types.is_float_dtype(frame[column]):
        frame[column] = frame[column].astype(float)


def _cart_column(frame: pd.DataFrame) -> str:
    """定位购物车金额列：``users`` 表叫 ``cart_value_at_assign``，分析框架叫 ``cart_value``。"""
    for candidate in (USERS_CART_COLUMN, FRAME_CART_COLUMN):
        if candidate in frame.columns:
            return candidate
    raise ValueError(
        f"找不到购物车金额列（尝试过 {USERS_CART_COLUMN!r} / {FRAME_CART_COLUMN!r}）；"
        f"现有列：{list(frame.columns)}"
    )


# --------------------------------------------------------------------------- #
# 1. 非随机缺失
# --------------------------------------------------------------------------- #
def add_missing_cart_value(
    df: pd.DataFrame,
    cfg: Any,
    *,
    master_seed: int,
    index: int = 0,
    column: str = FRAME_CART_COLUMN,
    channel_col: str = "channel",
) -> pd.DataFrame:
    """按**渠道差异化**概率把 ``column`` 置为 NaN —— 制造 MNAR 缺失。

    参数
    ----
    df : 含购物车金额列与渠道列的 DataFrame（``users`` 表或分析框架）。
    cfg : 配置对象，读 ``dirty.enabled``、``dirty.cart_value_missing_by_channel``，
          渠道字典缺该渠道时退回 ``dirty.cart_value_missing_rate``。
    master_seed, index : 随机流派生参数（stream = ``dirty.missing``）。
    column, channel_col : 列名，``users`` 表请传 ``column="cart_value_at_assign"``。

    返回
    ----
    新的 DataFrame；输入对象不被修改。``enabled=false`` 时是输入的**副本**。

    为什么必须是"按渠道"
    --------------------
    这是方案 §3.5 的原话："cart_value 5% 缺失，且缺失与渠道相关（非随机缺失）"。
    只有缺失概率依赖观测到的渠道，``cleaning.impute_cart_value`` 的
    "渠道内中位数填补 + 缺失指示列"才是有意义的技巧；若做成随机缺失，
    填补误差只会由"样本量"决定，面试里讲不出任何业务机制。

    实现细节
    --------
    * 每个用户消费**一次**均匀随机数，无论该渠道的缺失率是多少，
      这样同一 ``(master_seed, index)`` 下换配置不会改变随机流的对齐关系。
    * 渠道值统一走 ``astype(str)`` 再查表，兼容 ``category`` 与 ``object``
      两种 dtype，未知渠道（或空渠道）落到 ``cart_value_missing_rate``。
    """
    out = df.copy()
    params = _dirty_params(cfg)
    if not _enabled(params):
        return out

    _require_columns(out, (column, channel_col), where="add_missing_cart_value")

    fallback = _probability(
        _param(params, "cart_value_missing_rate"), key="dirty.cart_value_missing_rate"
    )
    raw_by_channel = _plain_mapping(params.get("cart_value_missing_by_channel"))
    by_channel = {
        str(name): _probability(
            float(rate), key=f"dirty.cart_value_missing_by_channel.{name}"
        )
        for name, rate in raw_by_channel.items()
    }

    n = len(out)
    if n == 0:
        return out

    probs = (
        out[channel_col]
        .astype(str)
        .map(by_channel)
        .fillna(fallback)
        .to_numpy(dtype=float)
    )
    rng = child_rng(master_seed, STREAM_MISSING, index)
    mask = rng.random(n) < probs

    _as_float(out, column)
    out.loc[mask, column] = np.nan
    return out


# --------------------------------------------------------------------------- #
# 2. 刷单异常值
# --------------------------------------------------------------------------- #
def add_fraud_outliers(
    df: pd.DataFrame,
    cfg: Any,
    *,
    master_seed: int,
    index: int = 0,
    column: str = FRAUD_COLUMN,
) -> pd.DataFrame:
    """随机抽 ``fraud_user_rate`` 比例的用户，把 ``column`` 放大 ``fraud_gmv_multiplier`` 倍。

    参数
    ----
    df : 含 ``column``（默认 ``hist_gmv``）的用户级 DataFrame。
    cfg : 读 ``dirty.enabled``、``dirty.fraud_user_rate``、``dirty.fraud_gmv_multiplier``。
    master_seed, index : stream = ``dirty.fraud``。

    返回
    ----
    新的 DataFrame；输入对象不被修改。

    为什么刷单要放大的是"历史 GMV"
    -------------------------------
    平台侧的历史 GMV 是刷单重灾区（虚假交易冲高店铺/用户等级），而它同时是
    DGP 里 ``hist_gmv_z`` 的来源、策略优化里判断"老客购买力"的特征。被污染
    之后，均值会跳、分位数会歪、按比值排序会失真——这正是要交给
    ``cleaning.winsorize`` 处理的问题。

    取舍（重要，勿改）
    ------------------
    **只放大 ``hist_gmv``，不动 ``hist_gmv_z`` 等任何 z 值列。** 理由：
    ``*_z`` 是**分配时点固化的快照**（``tables.build_five_tables`` 落库时已定稿，
    与 ``users.hist_gmv`` 同一时刻写入），而刷单是**事后稽查**才发现的记录错误。
    语义上"当时的特征快照"与"后来发现原始记录被篡改"并不矛盾：z 值代表
    分配当时系统以为的样子，脏的是后来查出来的原始字段。
    这条取舍还制造了一个真实的陷阱——``hist_gmv`` 被清洗（截尾）之后，
    它与 ``hist_gmv_z`` 不再自洽；任何下游若假设"z 等于 hist_gmv 的标准化"，
    就会算错。要修必须在 ETL 层重算 z，而不是在这里假装同步。
    """
    out = df.copy()
    params = _dirty_params(cfg)
    if not _enabled(params):
        return out

    _require_columns(out, (column,), where="add_fraud_outliers")

    rate = _probability(_param(params, "fraud_user_rate"), key="dirty.fraud_user_rate")
    multiplier = _param(params, "fraud_gmv_multiplier")
    if multiplier < 1.0:
        raise ValueError(
            f"dirty.fraud_gmv_multiplier 必须 >= 1（刷单是把金额放大），收到 {multiplier}"
        )

    n = len(out)
    # 四舍五入到最近整数；0.5 一律进位，避免 Python 银行家舍入带来的不可预期
    n_fraud = int(np.floor(rate * n + 0.5))
    if n == 0 or n_fraud == 0:
        return out

    rng = child_rng(master_seed, STREAM_FRAUD, index)
    picked = rng.choice(n, size=n_fraud, replace=False)  # 位置索引，不放回

    values = out[column].to_numpy(dtype=float, copy=True)
    values[picked] *= multiplier
    out[column] = values
    return out


# --------------------------------------------------------------------------- #
# 3. 重复上报
# --------------------------------------------------------------------------- #
def duplicate_events(
    events: pd.DataFrame,
    cfg: Any,
    *,
    master_seed: int,
    index: int = 0,
) -> pd.DataFrame:
    """按 ``duplicate_event_rate`` 复制一部分事件行（逐字段完全相同）。

    参数
    ----
    events : ``user_events`` 表（``user_id / event_type / event_time / sku_id / ts_ingested``）。
    cfg : 读 ``dirty.enabled``、``dirty.duplicate_event_rate``。
    master_seed, index : stream = ``dirty.duplicate``。

    返回
    ----
    新 DataFrame：原行在前、重复行追加在后（``ignore_index=True``），行数增加。
    输入对象不被修改。

    为什么这样造
    ------------
    真实成因是"同一曝光多次上报"（客户端重试、埋点 SDK 重放、离线补传）。
    重复行与原型**逐字段相同**——包括 ``ts_ingested``：重放发生在同一次入库
    批次里。因此**整行去重**（``drop_duplicates()``）也能去掉它们，但工程上
    正确做法仍是按业务键 ``(user_id, event_type, event_time, sku_id)`` 去重
    （``cleaning.deduplicate_events``）：``ts_ingested`` 是入库时间，不是事件
    身份，一旦延迟注入让同一事件的两次入库时间不同，整行去重就会失效。
    """
    out = events.copy()
    params = _dirty_params(cfg)
    if not _enabled(params):
        return out

    rate = _probability(
        _param(params, "duplicate_event_rate"), key="dirty.duplicate_event_rate"
    )
    n = len(out)
    n_dup = int(np.floor(rate * n + 0.5))
    if n == 0 or n_dup == 0:
        return out

    rng = child_rng(master_seed, STREAM_DUPLICATE, index)
    picked = rng.choice(n, size=n_dup, replace=False)  # 同一行只复制一次
    return pd.concat([out, out.iloc[picked]], ignore_index=True)


# --------------------------------------------------------------------------- #
# 4. 上报延迟
# --------------------------------------------------------------------------- #
def delay_ingestion(
    events: pd.DataFrame,
    cfg: Any,
    *,
    master_seed: int,
    index: int = 0,
) -> pd.DataFrame:
    """把 ``ts_ingested`` 推后 ``[0, event_delay_max_hours]`` 小时，``event_time`` 不动。

    参数
    ----
    events : ``user_events`` 表，至少含 ``event_time`` 与 ``ts_ingested``。
    cfg : 读 ``dirty.enabled``、``dirty.event_delay_max_hours``。
    master_seed, index : stream = ``dirty.delay``。

    返回
    ----
    新 DataFrame；``event_time`` 逐值不变，``ts_ingested >= event_time`` 恒成立。

    为什么"只动入库时间"是这条口径的命门
    ------------------------------------
    埋点延迟（离线补传、kafka 积压）会让"按 ``ts_ingested`` 切 7 天窗口"的人
    把窗口算歪：同一批事件因为晚到而被记到别的日期。而**事件时间才是业务
    事实**——用户是在 3 月 2 日加购的，不管日志 3 月 4 日才进来。
    所以：``event_time`` 一个字节都不改，脏的只有 ``ts_ingested``。
    下游任何"按入库时间聚合"的代码都会被这项注入抓出来。
    """
    out = events.copy()
    params = _dirty_params(cfg)
    if not _enabled(params):
        return out

    _require_columns(out, ("event_time", "ts_ingested"), where="delay_ingestion")

    max_hours = _param(params, "event_delay_max_hours")
    if max_hours < 0.0:
        raise ValueError(f"dirty.event_delay_max_hours 必须非负，收到 {max_hours}")

    n = len(out)
    if n == 0:
        return out

    rng = child_rng(master_seed, STREAM_DELAY, index)
    delays = pd.to_timedelta(rng.uniform(0.0, max_hours, size=n), unit="h")
    out["ts_ingested"] = pd.to_datetime(out["event_time"]) + delays
    return out


# --------------------------------------------------------------------------- #
# 编排
# --------------------------------------------------------------------------- #
def apply_dirty_layer(
    tables: dict[str, pd.DataFrame],
    cfg: Any,
    *,
    master_seed: int,
    index: int = 0,
) -> dict[str, pd.DataFrame]:
    """给五张表套上完整脏数据层，返回**新的**表字典。

    编排（顺序有讲究）：

    ==============  =========================================  ===============
    表              注入                                       随机流
    ==============  =========================================  ===============
    ``users``       购物车金额按渠道 MNAR 缺失；刷单放大 GMV    missing / fraud
    ``user_events`` 先算入库延迟、再复制重复行                   delay / duplicate
    其余三张表       原样返回（复制一份）                        —
    ==============  =========================================  ===============

    **先延迟、后复制**：这样重复行与原型**逐字段相同**（含 ``ts_ingested``），
    才是"同一次入库批次里的事件被重放两次"的真实形态。若先复制后延迟，
    两条记录的入库时间会不同，整行去重就失效了——虽然按业务键去重仍然有效，
    但那会让"去重该用什么键"这个考点消失。

    缺失注入打在 ``users.cart_value_at_assign``（分配时点快照）上，因为分析
    框架的 ``cart_value`` 就是从这一列来的（``tables.build_five_tables``）。
    """
    absent = [name for name in ("users", "user_events") if name not in tables]
    if absent:
        raise ValueError(
            f"apply_dirty_layer 需要 users / user_events 两张表，缺少 {absent}；"
            f"收到 {sorted(tables)}"
        )

    out: dict[str, pd.DataFrame] = {name: frame.copy() for name, frame in tables.items()}

    events = delay_ingestion(out["user_events"], cfg, master_seed=master_seed, index=index)
    events = duplicate_events(events, cfg, master_seed=master_seed, index=index)
    out["user_events"] = events

    users = add_missing_cart_value(
        out["users"],
        cfg,
        master_seed=master_seed,
        index=index,
        column=_cart_column(out["users"]),
        channel_col="channel",
    )
    users = add_fraud_outliers(users, cfg, master_seed=master_seed, index=index)
    out["users"] = users
    return out


def apply_dirty_to_frame(
    df: pd.DataFrame,
    cfg: Any,
    *,
    master_seed: int,
    index: int = 0,
) -> pd.DataFrame:
    """给分析框架套上脏数据层：只做**缺失 + 刷单**（框架里没有事件表）。

    参数
    ----
    df : ``build_analysis_frame`` 的输出（含 ``cart_value`` / ``hist_gmv`` / ``channel``）。
    cfg : 配置对象。
    master_seed, index : 随机流派生参数。

    返回
    ----
    新的 DataFrame；输入对象不被修改。

    注意
    ----
    重复上报与上报延迟只影响 ``user_events``，分析框架是**用户级**宽表，
    天然没有这两类脏；不要为了"对称"往框架里塞事件级脏数据。
    """
    out = add_missing_cart_value(
        df,
        cfg,
        master_seed=master_seed,
        index=index,
        column=FRAME_CART_COLUMN if FRAME_CART_COLUMN in df.columns else _cart_column(df),
        channel_col="channel",
    )
    return add_fraud_outliers(out, cfg, master_seed=master_seed, index=index)
