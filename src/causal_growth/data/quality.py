"""数据质量检查清单 —— 数据交付前的"体检报告"。

本模块回答方案里的哪个问题
--------------------------
《项目方案思路.md》§3.6 Step 2：「五张表 + 三个口径 + 利润核算规则 +
**数据质量检查清单**。先把数据字典和利润计算规范写清楚，再写代码。」
以及 §2.4 / GOAL.md 的口径红线（R1 退款单保留、R2 两窗口等长、R3 券成本只扣一次）。

每个检查项都在防一种**不会报错、只会悄悄算错**的错误
----------------------------------------------------
数据质量问题最阴的地方是：它不抛异常。重复的用户会让人均指标被重复计权，
错配的外键会让利润聚合悄悄丢人，被剔除的退款单会让转化率虚高——
下游所有因果估计都会带着这些偏差跑出"显著"的结果。所以每项检查都要回答
"如果不查，会错成什么样"，并且**带具体数字**落到报告里（见 ``summarize``）。

三个级别
--------
* ``error``  —— 违反口径红线或数据契约，``assert_no_errors`` 直接抛异常。
* ``warning`` —— 数值可疑但不阻断（如缺失率偏离预期），需在报告中披露。
* ``info``   —— 纯观察项，``passed`` 恒为 ``True``，只提供数字供报告引用
  （如"各渠道 cart 缺失率差异"，它的作用是**证明缺失确实是非随机的**）。

用法
----
>>> checks = check_tables(tables, cfg) + check_analysis_frame(frame, cfg)
>>> summarize(checks)            # 落盘成 outputs/tables/data_quality.csv
>>> assert_no_errors(checks)     # 有 error 级失败就中止管线
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from causal_growth.contracts import CONVERT_WINDOW, PROFIT_WINDOW
from causal_growth.data.cleaning import EVENT_BUSINESS_KEY
from causal_growth.data.tables import FIVE_TABLE_NAMES

__all__ = [
    "SEVERITIES",
    "QualityCheck",
    "QualityError",
    "assert_no_errors",
    "check_analysis_frame",
    "check_tables",
    "summarize",
]

#: 检查级别（``severity`` 的合法取值）
SEVERITIES: tuple[str, ...] = ("error", "warning", "info")

#: 购物车金额列名的候选顺序：``users`` 表用第一个，分析框架用第二个
CART_VALUE_COLUMNS: tuple[str, ...] = ("cart_value_at_assign", "cart_value")

#: 一小时有多少秒（单位换算常数，不是业务参数）
_SECONDS_PER_HOUR: float = 3600.0

#: detail 里最多列几个示例值（纯展示）
_MAX_EXAMPLES: int = 3


# --------------------------------------------------------------------------- #
# 结果载体
# --------------------------------------------------------------------------- #
class QualityError(AssertionError):
    """``error`` 级检查未通过时抛出的异常。

    继承 ``AssertionError``：语义上这就是一条"口径断言"失败，
    因此 ``except AssertionError`` 也能捕获（AGENTS.md §4 的断言式写法）。
    """


@dataclass(frozen=True)
class QualityCheck:
    """一条检查结果。

    ``value`` 的含义**随检查项而定**（重复行数 / 比率 / 最大延迟小时数），
    单位写在 ``detail`` 里，不要跨检查项对 ``value`` 做聚合。
    """

    name: str
    passed: bool
    severity: str
    detail: str
    value: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("QualityCheck.name 不能为空")
        if self.severity not in SEVERITIES:
            raise ValueError(
                f"severity 必须是 {SEVERITIES} 之一，收到 {self.severity!r}"
            )


def _check(
    *,
    name: str,
    passed: bool,
    severity: str,
    ok: str,
    bad: str,
    value: float | None = None,
) -> QualityCheck:
    """按 ``passed`` 选一句结论，组装成 ``QualityCheck``（减少重复分支）。"""
    return QualityCheck(
        name=name,
        passed=bool(passed),
        severity=severity,
        detail=ok if passed else bad,
        value=value,
    )


def _pct(x: float) -> str:
    return f"{x:.2%}"


def _examples(values: Iterable[Any]) -> str:
    """取前几个示例值，便于在报告里定位问题行。"""
    head = sorted({v for v in values})[:_MAX_EXAMPLES]
    return str(head)


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, where: str) -> None:
    """列不齐直接抛错：列都认不出，后面的检查全是假的通过。"""
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{where} 缺少必需列 {missing}；现有列：{list(frame.columns)}")


def _cart_column(frame: pd.DataFrame) -> str:
    """找到购物车金额列（``users`` 表与分析框架列名不同）。"""
    for candidate in CART_VALUE_COLUMNS:
        if candidate in frame.columns:
            return candidate
    raise ValueError(
        f"找不到购物车金额列（尝试过 {list(CART_VALUE_COLUMNS)}）；现有列：{list(frame.columns)}"
    )


def _missing_rates_by_channel(
    frame: pd.DataFrame, missing: pd.Series, channel_col: str
) -> dict[str, tuple[float, int, int]]:
    """按渠道统计缺失率，返回 ``{渠道: (缺失率, 缺失数, 样本数)}``（按渠道名排序）。"""
    out: dict[str, tuple[float, int, int]] = {}
    channels = frame[channel_col].astype(str)
    for name in sorted(channels.unique()):
        mask = (channels == name).to_numpy()
        n_channel = int(mask.sum())
        if n_channel == 0:
            continue
        n_missing = int(missing.to_numpy()[mask].sum())
        out[name] = (n_missing / n_channel, n_missing, n_channel)
    return out


# --------------------------------------------------------------------------- #
# 单项检查：结构类
# --------------------------------------------------------------------------- #
def _check_unique_key(
    frame: pd.DataFrame, column: str, *, name: str, table: str, severity: str = "error"
) -> QualityCheck:
    """**主键唯一** —— 防"同一个实体被算两次"。

    一个 user_id 出现两行，``groupby("user_id").sum()`` 就会把利润翻倍，
    人均指标、方差、置信区间全部失真；orders.order_id 重复则会把同一笔钱
    记两次（等价于 R3 的重复扣减）。这类错误不会抛异常，只会让结论偏。
    """
    if len(frame) == 0:
        return _check(
            name=name,
            passed=True,
            severity=severity,
            ok=f"{table} 为空表，主键唯一性真空成立",
            bad="",
            value=0.0,
        )
    dup_rows = frame[column].duplicated(keep=False)
    n_dup_rows = int(dup_rows.sum())
    n_dup_values = int(frame.loc[dup_rows, column].nunique())
    passed = n_dup_rows == 0
    return _check(
        name=name,
        passed=passed,
        severity=severity,
        ok=f"{len(frame)} 行 {column} 全部唯一（重复 0 个）",
        bad=(
            f"{n_dup_values} 个 {column} 出现重复，共 {n_dup_rows} 行，"
            f"示例 {_examples(frame.loc[dup_rows, column])}；"
            "重复主键会让聚合指标重复计权"
        ),
        value=float(n_dup_rows),
    )


def _check_foreign_key(
    child: pd.DataFrame,
    child_col: str,
    parent_ids: set[Any],
    *,
    name: str,
    severity: str = "error",
) -> QualityCheck:
    """**外键完整** —— 防"订单挂在一个不存在的用户上"。

    子表里出现父表没有的 id，``merge(how="left"/"inner")`` 会静默丢行或产生
    空值，利润聚合与人群画像就会少人/多人。这里只报"孤儿行数"，
    因为孤儿行是**指得出具体 id** 的可修问题。
    """
    if len(child) == 0:
        return _check(
            name=name,
            passed=True,
            severity=severity,
            ok=f"{child_col} 所在表为空，外键完整性真空成立",
            bad="",
            value=0.0,
        )
    child_ids = set(child[child_col].unique())
    orphans = child_ids - parent_ids
    n_orphan_rows = int(child[child_col].isin(orphans).sum())
    return _check(
        name=name,
        passed=not orphans,
        severity=severity,
        ok=f"{len(child)} 行 {child_col} 全部能在父表找到（孤儿 0 行）",
        bad=(
            f"{len(orphans)} 个 {child_col} 不在父表中，涉及 {n_orphan_rows} 行，"
            f"示例 {_examples(orphans)}；聚合时这些行会被静默丢弃"
        ),
        value=float(n_orphan_rows),
    )


def _check_assignment_unique_per_user(
    assignments: pd.DataFrame, *, name: str, severity: str = "error"
) -> QualityCheck:
    """**分组只出现一次** —— 方案"同一用户多次曝光只算一个样本"。

    真实投放里一个人可能被多轮活动命中；若不去重，处理组会被重复计入，
    ITT 的分子分母不一致（分母按用户、分子按曝光），效应估计直接偏。
    本项目的口径是**每人一行**：``coupon_assignment`` 的粒度必须是用户。
    """
    if len(assignments) == 0:
        return _check(
            name=name,
            passed=True,
            severity=severity,
            ok="coupon_assignment 为空表，分组唯一性真空成立",
            bad="",
            value=0.0,
        )
    per_user = assignments.groupby("user_id").size()
    n_multi = int((per_user > 1).sum())
    n_extra_rows = int((per_user - 1).clip(lower=0).sum())
    return _check(
        name=name,
        passed=n_multi == 0,
        severity=severity,
        ok=f"{len(per_user)} 个用户各仅 1 行分组记录（{len(assignments)} 行）",
        bad=(
            f"{n_multi} 个用户出现多次分组，多出 {n_extra_rows} 行，"
            f"示例 {_examples(per_user[per_user > 1].index)}；"
            "重复曝光必须只算一个样本"
        ),
        value=float(n_extra_rows),
    )


def _check_treatment_share(
    assignments: pd.DataFrame, cfg: Any, *, name: str, n_sigma: float = 3.0
) -> QualityCheck:
    """**处理组比例** —— 与设计值偏差须在二项分布 ``n_sigma`` 个标准差内。

    分流比例跑偏（比如 50% 设计值实际只有 42%）说明随机化实现有 bug，
    或者有用户被重复分配。比例本身不直接影响 ITT 的无偏性，
    但它是一颗"分流代码可信度"的廉价探针：``T ~ Bernoulli(p)`` 的
    标准差是 ``sqrt(p(1-p)/n)``，3σ 之外的偏差在 1000 次里几乎不会自然出现。
    """
    n = len(assignments)
    p_design = float(cfg.require("experiment.treatment_share"))
    if n == 0:
        return _check(
            name=name,
            passed=False,
            severity="error",
            ok="",
            bad="coupon_assignment 为空表，无法核对分流比例",
            value=None,
        )
    is_treated = assignments["group"].astype(str).to_numpy() == "treatment"
    n_treated = int(is_treated.sum())
    observed = n_treated / n
    sigma = float(np.sqrt(p_design * (1.0 - p_design) / n))
    tolerance = n_sigma * sigma
    deviation = observed - p_design
    passed = abs(deviation) <= tolerance
    tail = (
        f"观察 {_pct(observed)}（treatment {n_treated}/{n}），设计 {_pct(p_design)}，"
        f"偏差 {deviation:+.2%}，{n_sigma:g}σ 容差 ±{_pct(tolerance)}"
    )
    return _check(
        name=name,
        passed=passed,
        severity="error",
        ok=tail,
        bad=tail + "；偏差超出抽样波动，怀疑分流实现有 bug 或存在重复分配",
        value=float(observed),
    )


def _check_two_windows(user_outcomes: pd.DataFrame, *, name: str) -> QualityCheck:
    """**两个窗口齐全且等长** —— GOAL.md R2。

    每个用户必须**各有一行** ``convert_7d`` 与 ``profit_30d``，且都以自己的
    ``assign_time`` 为起点。少一个窗口 → 有人没进利润分母；多一行 → 分母被
    放大。混用两个窗口（拿 7 天的转化配 30 天的利润）是最隐蔽的口径错误：
    数字看起来完全正常，只是含义错了。
    """
    expected = {CONVERT_WINDOW, PROFIT_WINDOW}
    if len(user_outcomes) == 0:
        return _check(
            name=name,
            passed=False,
            severity="error",
            ok="",
            bad="user_outcomes 为空表，两个窗口都不存在",
            value=None,
        )
    n_users = int(user_outcomes["user_id"].nunique())
    per_user = user_outcomes.groupby("user_id").size()
    types_per_user = user_outcomes.groupby("user_id")["window_type"].nunique()
    observed_types = set(user_outcomes["window_type"].astype(str).unique())
    rows_ok = int(per_user.min()) == 2 and int(per_user.max()) == 2
    types_ok = observed_types == expected
    per_user_ok = bool((types_per_user == 2).all())
    passed = rows_ok and types_ok and per_user_ok
    status = (
        f"{n_users} 个用户，每用户 {int(per_user.min())}~{int(per_user.max())} 行，"
        f"window_type={sorted(observed_types)}，期望每用户 2 行且 ={sorted(expected)}"
    )
    return _check(
        name=name,
        passed=passed,
        severity="error",
        ok=status,
        bad=status + "；两窗口必须等长且不混用（R2）",
        value=float(len(user_outcomes) / n_users) if n_users else None,
    )


# --------------------------------------------------------------------------- #
# 单项检查：数值 / 口径类
# --------------------------------------------------------------------------- #
def _check_window_nan_policy(
    user_outcomes: pd.DataFrame, *, name: str, severity: str = "error"
) -> QualityCheck:
    """**convert_7d 的 net_profit 必须全空、profit_30d 的必须全有**。

    这是 R2 的机器化表达：7 天时利润还没成熟（退款、结算都没走完），
    硬填一个数就是**用未来信息**，而且会把"转化窗口"与"利润窗口"粘成一个。
    反过来 ``profit_30d`` 出现 NaN 更糟：``groupby.mean()`` 会静默跳过 NaN，
    等于悄悄把一批人从利润均值里删掉——和"剔除未转化用户"是同一个错误的变种。
    """
    conv_mask = user_outcomes["window_type"].astype(str) == CONVERT_WINDOW
    prof_mask = user_outcomes["window_type"].astype(str) == PROFIT_WINDOW
    n_conv_filled = int(user_outcomes.loc[conv_mask, "net_profit"].notna().sum())
    n_prof_missing = int(user_outcomes.loc[prof_mask, "net_profit"].isna().sum())
    passed = n_conv_filled == 0 and n_prof_missing == 0
    status = (
        f"convert_7d 共 {int(conv_mask.sum())} 行，其中 net_profit 非空 {n_conv_filled} 行；"
        f"profit_30d 共 {int(prof_mask.sum())} 行，其中缺失 {n_prof_missing} 行"
    )
    return _check(
        name=name,
        passed=passed,
        severity=severity,
        ok=status + "（符合「利润未成熟 / 已成熟」两种状态）",
        bad=status + "；7 天窗口不得有利润数，30 天窗口不得缺利润",
        value=float(n_conv_filled + n_prof_missing),
    )


def _check_refund_orders_kept(orders: pd.DataFrame, user_ids: set[Any], *, name: str) -> QualityCheck:
    """**退款单必须留在样本里** —— GOAL.md R1 的第一道闸。

    剔除退款订单会让处理组的转化与利润同时虚高（券拉来的边际买家更容易反悔，
    而他们恰好最可能退款）。而且这种剔除在代码里往往只写一句
    ``orders = orders[~orders.refunded]``，看起来像"数据清洗"，实际是**改变
    分析分母**。这里同时校验"退款单存在"与"这些单的用户仍在父表里"。
    """
    if len(orders) == 0:
        return _check(
            name=name,
            passed=False,
            severity="error",
            ok="",
            bad="orders 为空表：没有任何订单意味着退款单也不可能保留（R1 无法校验）",
            value=0.0,
        )
    refunded = orders["refunded"].astype(bool).to_numpy()
    n_refunded = int(refunded.sum())
    refunded_ids = set(orders.loc[refunded, "user_id"].unique())
    orphans = refunded_ids - user_ids
    passed = n_refunded > 0 and not orphans
    status = f"退款单 {n_refunded}/{len(orders)} 行（{_pct(n_refunded / len(orders))}）"
    return _check(
        name=name,
        passed=passed,
        severity="error",
        ok=status + "保留在样本内，且对应用户均在 users 表中",
        bad=(
            status + f"，其中用户不在 users 表的 {len(orphans)} 个；"
            "退款单被剔除或丢失意味着分析分母被悄悄改动（R1）"
        ),
        value=float(n_refunded),
    )


def _check_amounts_non_negative(orders: pd.DataFrame, *, name: str, columns: Sequence[str]) -> QualityCheck:
    """**金额非负** —— 防"负的支付额把利润拉低/拉高"。

    金额出现负值只有两种可能：退款被记成了负数支付（重复扣减），
    或者上游单位/符号错。它不会报错，只会让利润均值莫名其妙地偏移，
    而偏移方向通常与处理组相关（券单退款更多），于是效应估计被污染。
    """
    counts = {col: int((orders[col].to_numpy(dtype=float) < 0.0).sum()) for col in columns}
    n_bad_rows = int((orders[list(columns)].to_numpy(dtype=float) < 0.0).any(axis=1).sum())
    passed = n_bad_rows == 0
    detail = "、".join(f"{col} 负值 {cnt}" for col, cnt in counts.items())
    return _check(
        name=name,
        passed=passed,
        severity="error",
        ok=f"{len(orders)} 行订单，{len(columns)} 个金额列均为非负（{detail}）",
        bad=f"{n_bad_rows} 行出现负金额（{detail}）；负金额会污染利润分布",
        value=float(n_bad_rows),
    )


def _check_refund_amount_bounded(orders: pd.DataFrame, *, name: str) -> QualityCheck:
    """**退款金额不超过支付金额** —— 防"退得比付的多"。

    超额退款会让 ``revenue_net = pay - refund`` 变成负数，利润核算把一笔
    "没赚还倒贴"的订单算进来；更常见的是部分退款被写成全额 + 运费补偿，
    实际业务上不允许。同时检查 ``refund_amount >= 0``，负退款等于反向收入。
    """
    refund = orders["refund_amount"].to_numpy(dtype=float)
    pay = orders["pay_amount"].to_numpy(dtype=float)
    n_over = int((refund > pay).sum())
    n_negative = int((refund < 0.0).sum())
    passed = n_over == 0 and n_negative == 0
    worst = float(refund.max()) if len(refund) else 0.0
    return _check(
        name=name,
        passed=passed,
        severity="error",
        ok=f"{len(orders)} 行订单：退款金额均落在 [0, 支付金额]（最小 0，最大 {worst:.2f} 元）",
        bad=(
            f"{n_over} 行退款金额超过支付金额、{n_negative} 行为负；"
            "超额退款会让净收入变负，属于利润口径错误"
        ),
        value=float(n_over + n_negative),
    )


def _check_coupon_only_treated(assignments: pd.DataFrame, *, name: str) -> QualityCheck:
    """**券只发给处理组** —— 防"对照组也被塞了券"。

    对照组一旦有券，ITT 的"未被干预"参照系就没了，效应被稀释甚至反号；
    反过来若处理组没有券，就是"处理组没接受处理"，同样毁掉对比。
    这里只查方案要求的方向（有券 ⇒ treatment），因为"处理组是否人人有券"
    取决于投放策略（可能是定向发放），不宜当硬错误。
    """
    group = assignments["group"].astype(str).to_numpy()
    has_coupon = assignments["coupon_value"].to_numpy(dtype=float) > 0.0
    n_with_coupon = int(has_coupon.sum())
    n_violations = int((has_coupon & (group != "treatment")).sum())
    return _check(
        name=name,
        passed=n_violations == 0,
        severity="error",
        ok=f"有券用户 {n_with_coupon} 个，全部落在 treatment 组",
        bad=(
            f"有券用户 {n_with_coupon} 个，其中 {n_violations} 个落在对照组；"
            "对照组被发券会毁掉未被干预的参照系"
        ),
        value=float(n_violations),
    )


def _expected_cart_missing_rate(
    frame: pd.DataFrame, cfg: Any, *, channel_col: str
) -> float:
    """按渠道占比加权算出"应该"的整体缺失率（来自 ``dirty`` 配置）。"""
    section = cfg.get("dirty") if hasattr(cfg, "get") else None
    params = dict(section.to_dict()) if hasattr(section, "to_dict") else dict(section or {})
    fallback = float(params.get("cart_value_missing_rate", 0.0))
    by_channel = params.get("cart_value_missing_by_channel") or {}
    shares = frame[channel_col].astype(str).value_counts(normalize=True)
    return float(
        sum(float(share) * float(by_channel.get(str(name), fallback)) for name, share in shares.items())
    )


def _check_cart_missing_rate(
    frame: pd.DataFrame,
    cfg: Any,
    *,
    name: str,
    column: str | None = None,
    channel_col: str = "channel",
    n_sigma: float = 3.0,
) -> QualityCheck:
    """**cart 缺失率不超过设计上限** —— 只报 warning，不阻断。

    为什么不是 error：缺失本身是**设计好的脏数据**（方案 §3.5），不是 bug。
    但缺失率若比渠道加权预期高出 3σ 以上，说明有别的事发生了——常见两种：
    ① 上游字段丢失/整行丢失，缺失比设计更多；
    ② 有人把部分缺失误填成 0 又另造了新的缺失。
    这两种都必须进报告，所以设成 warning 并给出具体数字，让人去查。

    **单边**判据（只罚"太多"，不罚"太少"）：干净数据（未注入脏层）的缺失率
    本来就该是 0，低于设计值不是错误；把 0 判成 warning 会让"干净对照跑一遍"
    这条最常用的流程满屏告警。真正要抓的是"比设计值多出来的缺失"。
    """
    col = column or _cart_column(frame)
    n = len(frame)
    if n == 0:
        return _check(
            name=name,
            passed=True,
            severity="warning",
            ok="空表，缺失率真空成立",
            bad="",
            value=None,
        )
    n_missing = int(frame[col].isna().sum())
    observed = n_missing / n
    expected = _expected_cart_missing_rate(frame, cfg, channel_col=channel_col)
    sigma = float(np.sqrt(max(expected * (1.0 - expected), 0.0) / n))
    upper_bound = min(expected + n_sigma * sigma, 1.0)
    passed = observed <= upper_bound
    status = (
        f"{col} 缺失 {n_missing}/{n}（{_pct(observed)}），"
        f"渠道加权设计值 {_pct(expected)}，{n_sigma:g}σ 上限 {_pct(upper_bound)}"
    )
    return _check(
        name=name,
        passed=passed,
        severity="warning",
        ok=status + "；缺失水平未超设计上限",
        bad=status + "；缺失多于设计值，请确认是上游丢失还是填补时抹掉了缺失（需留指示列）",
        value=float(observed),
    )


def _check_events_before_assignment(
    events: pd.DataFrame, assignments: pd.DataFrame, *, name: str
) -> QualityCheck:
    """**事件时间不得晚于分配时间** —— 抓时间逻辑错误。

    行为日志里出现"分配之后才发生的浏览/加购"，只有两种解释：时区错位，
    或者事件时间被错误地写成了入库时间/当前时间。无论哪种，按"分配前 7 天
    行为"构造的特征就混进了**发券之后**的行为——这在因果上是致命的：
    处理组的行为会被券本身影响，特征成了处理后变量（post-treatment），
    用它做 CATE 会把券的效果当成用户的先天差异，估计直接偏。
    """
    if len(events) == 0:
        return _check(
            name=name,
            passed=True,
            severity="error",
            ok="user_events 为空表，时间逻辑真空成立",
            bad="",
            value=0.0,
        )
    assign = assignments.loc[:, ["user_id", "assign_time"]]
    merged = events.loc[:, ["user_id", "event_time"]].merge(
        assign, on="user_id", how="left"
    )
    n_unmatched = int(merged["assign_time"].isna().sum())
    n_late = int((merged["event_time"] > merged["assign_time"]).sum())
    passed = n_late == 0 and n_unmatched == 0
    status = (
        f"{len(events)} 条事件：晚于分配时间 {n_late} 条，"
        f"找不到分配记录 {n_unmatched} 条"
    )
    return _check(
        name=name,
        passed=passed,
        severity="error",
        ok=status + "；全部事件都发生在分配时点之前",
        bad=status + "；分配后的事件会被券本身影响（post-treatment），不能当特征",
        value=float(n_late + n_unmatched),
    )


def _check_ingestion_delay(events: pd.DataFrame, cfg: Any, *, name: str) -> QualityCheck:
    """**上报延迟不超过配置上限** —— 防"按入库时间切窗口"。

    延迟本身是正常业务现象（方案 §3.5 有意注入）。但延迟一旦超过配置上限，
    要么是注入实现写错，要么是上游补传失控。更重要的是这条检查把
    ``ts_ingested − event_time`` 的分布**显式摆出来**：任何人想按
    ``ts_ingested`` 聚日期，都会先看到这个差值。同时校验延迟非负
    （入库早于发生是逻辑不可能）。
    """
    if len(events) == 0:
        return _check(
            name=name,
            passed=True,
            severity="warning",
            ok="user_events 为空表，延迟真空成立",
            bad="",
            value=None,
        )
    delta_hours = (
        (events["ts_ingested"] - events["event_time"]).dt.total_seconds() / _SECONDS_PER_HOUR
    )
    max_hours = float(delta_hours.max())
    n_negative = int((delta_hours < 0).sum())
    limit = float(cfg.require("dirty.event_delay_max_hours"))
    passed = max_hours <= limit and n_negative == 0
    status = f"最大延迟 {max_hours:.2f} 小时（配置上限 {limit:g} 小时），负延迟 {n_negative} 条"
    return _check(
        name=name,
        passed=passed,
        severity="warning",
        ok=status + "；统计一律按 event_time，不用 ts_ingested",
        bad=status + "；超出上限或有负延迟，说明入库时间不可用于时间切分",
        value=max_hours,
    )


def _check_order_after_assignment(
    orders: pd.DataFrame, assignments: pd.DataFrame, *, name: str
) -> QualityCheck:
    """**下单时间不得早于分配时间** —— 防"订单挂错人/时间串位"。

    先下单后发券，在因果上等于"结果先于原因"。真实成因多是订单表与曝光表
    的时间字段错位（一个用 UTC 一个用北京时间），或者是同一个 user_id 在不同
    活动间被复用。无论哪种，这笔订单都不该进入本次实验的效应计算。
    """
    if len(orders) == 0:
        return _check(
            name=name,
            passed=True,
            severity="error",
            ok="orders 为空表，时间逻辑真空成立",
            bad="",
            value=0.0,
        )
    merged = orders.loc[:, ["user_id", "order_time"]].merge(
        assignments.loc[:, ["user_id", "assign_time"]], on="user_id", how="left"
    )
    n_unmatched = int(merged["assign_time"].isna().sum())
    n_early = int((merged["order_time"] < merged["assign_time"]).sum())
    passed = n_early == 0 and n_unmatched == 0
    return _check(
        name=name,
        passed=passed,
        severity="error",
        ok=f"{len(orders)} 笔订单均发生在分配之后（早于分配 0 笔，无分配记录 0 笔）",
        bad=(
            f"{n_early} 笔订单早于分配时间、{n_unmatched} 笔找不到分配记录；"
            "结果先于原因，通常是时区/字段串位"
        ),
        value=float(n_early + n_unmatched),
    )


def _check_outcomes_match_orders(
    orders: pd.DataFrame, user_outcomes: pd.DataFrame, *, name: str
) -> QualityCheck:
    """**订单表与 user_outcomes 口径一致** —— 抓"订单被悄悄删掉"。

    ``user_outcomes`` 是从订单派生的；两边对不上说明中间有行被过滤过。
    最常见的过滤就是剔除退款单：某个用户的唯一一笔订单退款后被删掉，
    他在 ``profit_30d`` 里仍然 ``converted = 1``，但订单表里查无此人。
    这条检查是 R1 的第二道闸（第一道是"退款单数 > 0"，它抓不到"只删一部分"
    的情形——而"只删一部分"恰恰是最容易被写进管线的错）。
    """
    prof = user_outcomes[user_outcomes["window_type"].astype(str) == PROFIT_WINDOW]
    converted_ids = set(prof.loc[prof["converted"].to_numpy() == 1, "user_id"].unique())
    order_ids = set(orders["user_id"].unique())
    missing_in_orders = converted_ids - order_ids
    missing_in_outcomes = order_ids - converted_ids
    passed = not missing_in_orders and not missing_in_outcomes
    status = (
        f"profit_30d 转化用户 {len(converted_ids)} 个，订单表用户 {len(order_ids)} 个；"
        f"转化但无订单 {len(missing_in_orders)} 个，有订单却未记转化 {len(missing_in_outcomes)} 个"
    )
    return _check(
        name=name,
        passed=passed,
        severity="error",
        ok=status + "；订单表与结果表完全对得上",
        bad=(
            status + "；两边对不上说明有订单行被过滤（剔除退款单是最常见的一种，R1）"
        ),
        value=float(len(missing_in_orders) + len(missing_in_outcomes)),
    )


def _check_event_key_duplicates(events: pd.DataFrame, *, name: str) -> QualityCheck:
    """**事件业务键重复** —— 防"同一曝光被算成两次行为"。

    重复上报（方案 §3.5 有意注入）会让"人均浏览深度""加购率"等行为指标虚高，
    而且虚高幅度与用户活跃度相关（活跃用户事件多、被重放的概率也高）。
    这里同时给出"整行重复"与"业务键重复"两个数：前者是 ``drop_duplicates()``
    能去掉的，后者才是**正确口径**（``ts_ingested`` 是入库时间，不是事件身份）。
    """
    if len(events) == 0:
        return _check(
            name=name,
            passed=True,
            severity="warning",
            ok="user_events 为空表，重复问题真空成立",
            bad="",
            value=0.0,
        )
    n_full_dup = int(events.duplicated().sum())
    n_key_dup = int(events.duplicated(subset=list(EVENT_BUSINESS_KEY)).sum())
    passed = n_key_dup == 0
    status = (
        f"{len(events)} 条事件：整行重复 {n_full_dup} 条"
        f"（{_pct(n_full_dup / len(events))}），业务键重复 {n_key_dup} 条"
        f"（{_pct(n_key_dup / len(events))}）"
    )
    return _check(
        name=name,
        passed=passed,
        severity="warning",
        ok=status + "；无需去重",
        bad=status + "；需按业务键去重（见 cleaning.deduplicate_events）",
        value=float(n_key_dup),
    )


def _check_browse_depth_consistency(
    events: pd.DataFrame, users: pd.DataFrame, *, name: str
) -> QualityCheck:
    """**browse_depth_7d 与事件计数一致** —— info 级交叉校验。

    ``users.browse_depth_7d`` 声称是"分配前 7 天事件数"，而 ``user_events``
    是它的原始出处。两者不一致有两种无害原因：一是 ``tables`` 对事件数做了
    上限裁剪（重度用户只记前 N 条），二是脏数据层的重复上报。
    这条检查的价值在于把"特征与事实"的差额**量化**出来，而不是假设它为零。
    """
    if len(users) == 0 or len(events) == 0:
        return _check(
            name=name,
            passed=True,
            severity="info",
            ok="用户表或事件表为空，无法交叉校验",
            bad="",
            value=None,
        )
    depth = users.set_index("user_id")["browse_depth_7d"]
    counts = events.groupby("user_id").size().reindex(depth.index, fill_value=0)
    match = counts.to_numpy() == depth.to_numpy()
    n_match = int(match.sum())
    n_bad = int((~match).sum())
    status = (
        f"{n_match}/{len(depth)} 用户的事件数与 browse_depth_7d 相等（不匹配 {n_bad} 个；"
        f"用户最大事件数 {int(counts.max())}，browse_depth_7d 最大 {int(depth.max())}）"
    )
    return _check(
        name=name,
        passed=True,  # info 级：只汇报，不设门禁
        severity="info",
        ok=status + "；差额来自事件数上限裁剪或重复上报，需在报告中说明",
        bad="",
        value=n_match / len(depth),
    )


def _check_mnar_evidence(
    frame: pd.DataFrame,
    *,
    name: str,
    column: str | None = None,
    channel_col: str = "channel",
    indicator: str | None = None,
) -> QualityCheck:
    """**非随机缺失的证据** —— 按渠道报 cart 缺失率差异（info 级）。

    为什么单列一项：``warning`` 只告诉你"总缺失率偏离预期"，证明不了缺失
    **与渠道相关**。而"缺失是 MNAR"正是方案 §3.5 的设计要点，也是"必须留
    缺失指示列、不能直接丢行"的唯一理由。这里把各渠道的缺失率并排列出来，
    谁高谁低一目了然；最高/最低的倍数就是报告里那句"缺失确实非随机"的证据。

    ``indicator`` 列存在时（清洗后）优先用它——否则清洗后的帧全是 0 缺失，
    这条证据就消失了。这保证**清洗前后都能拿出同一份 MNAR 证据**。
    """
    col = column or _cart_column(frame)
    if len(frame) == 0:
        return _check(
            name=name,
            passed=True,
            severity="info",
            ok="空表，无缺失可统计",
            bad="",
            value=None,
        )
    if indicator is not None and indicator in frame.columns:
        missing = frame[indicator].to_numpy(dtype=float) > 0.0
    else:
        missing = frame[col].isna().to_numpy()
    rates = _missing_rates_by_channel(frame, pd.Series(missing, index=frame.index), channel_col)
    if not rates:
        return _check(
            name=name,
            passed=True,
            severity="info",
            ok="无渠道列可用，跳过",
            bad="",
            value=None,
        )
    parts = "、".join(
        f"{chan} {_pct(rate)}（{n_miss}/{n_chan}）"
        for chan, (rate, n_miss, n_chan) in rates.items()
    )
    values = [r[0] for r in rates.values()]
    highest, lowest = max(values), min(values)
    if lowest > 0.0:
        ratio_text = f"最高/最低 = {highest / lowest:.2f} 倍"
    elif highest > 0.0:
        ratio_text = "最低渠道缺失为 0，比值不可比"
    else:
        ratio_text = "各渠道缺失率均为 0，无 MNAR 迹象"
    return _check(
        name=name,
        passed=True,  # info 级：只汇报，不设门禁
        severity="info",
        ok=f"{col} 各渠道缺失率：{parts}；{ratio_text}",
        bad="",
        value=float(highest),
    )


# --------------------------------------------------------------------------- #
# 对外：五表清单
# --------------------------------------------------------------------------- #
def check_tables(tables: dict[str, pd.DataFrame], cfg: Any, *, n_sigma: float = 3.0) -> list[QualityCheck]:
    """对五张关系表跑完整清单，返回检查结果列表（顺序固定，便于报告对比）。

    参数
    ----
    tables : ``build_five_tables`` 的输出（必须是完整的五表，缺表直接抛错）。
    cfg : 配置对象；读 ``experiment.treatment_share`` 与 ``dirty.*``。
    n_sigma : 比例类检查的容差倍数（二项分布标准差），默认 3σ。

    返回
    ----
    ``list[QualityCheck]``。**不抛异常**——是否阻断由调用方用
    ``assert_no_errors`` 决定，这样先把体检做全、再决定要不要停。
    """
    absent = [name for name in FIVE_TABLE_NAMES if name not in tables]
    if absent:
        raise ValueError(f"check_tables 需要完整的五表，缺少 {absent}；收到 {sorted(tables)}")

    users = tables["users"]
    events = tables["user_events"]
    assignments = tables["coupon_assignment"]
    orders = tables["orders"]
    outcomes = tables["user_outcomes"]

    _require_columns(users, ("user_id", "channel"), where="users")
    _require_columns(
        events, ("user_id", "event_type", "event_time", "sku_id", "ts_ingested"), where="user_events"
    )
    _require_columns(
        assignments, ("user_id", "group", "coupon_value", "assign_time"), where="coupon_assignment"
    )
    _require_columns(
        orders,
        ("order_id", "user_id", "order_time", "pay_amount", "refund_amount", "goods_cost",
         "fulfill_cost", "refunded"),
        where="orders",
    )
    _require_columns(outcomes, ("user_id", "window_type", "converted", "net_profit"), where="user_outcomes")

    user_ids = set(users["user_id"].unique())
    checks: list[QualityCheck] = [
        # ---- 结构与键 ----
        _check_unique_key(users, "user_id", name="主键唯一：users.user_id", table="users"),
        _check_unique_key(orders, "order_id", name="主键唯一：orders.order_id", table="orders"),
        _check_foreign_key(
            orders, "user_id", user_ids, name="外键完整：orders.user_id → users"
        ),
        _check_foreign_key(
            assignments,
            "user_id",
            user_ids,
            name="外键完整：coupon_assignment.user_id → users",
        ),
        _check_assignment_unique_per_user(
            assignments, name="分组只出现一次：coupon_assignment 每个用户一行"
        ),
        _check_treatment_share(
            assignments, cfg, name="处理组比例与设计一致", n_sigma=n_sigma
        ),
        # ---- 两窗口口径 ----
        _check_two_windows(outcomes, name="两个窗口齐全且等长（R2）"),
        _check_window_nan_policy(
            outcomes, name="窗口利润空值策略（R2：7 天未成熟 / 30 天必成熟）"
        ),
        # ---- 退款与金额 ----
        _check_refund_orders_kept(orders, user_ids, name="退款单保留在样本内（R1）"),
        _check_amounts_non_negative(
            orders,
            name="金额字段非负",
            columns=("pay_amount", "goods_cost", "fulfill_cost"),
        ),
        _check_refund_amount_bounded(orders, name="退款金额落在 [0, 支付金额]"),
        _check_coupon_only_treated(assignments, name="券只发给处理组"),
        # ---- 时间逻辑 ----
        _check_events_before_assignment(
            events, assignments, name="事件时间不晚于分配时间"
        ),
        _check_order_after_assignment(orders, assignments, name="订单时间不晚于分配时间"),
        _check_ingestion_delay(events, cfg, name="上报延迟合法且不超过配置上限"),
        # ---- 一致性 ----
        _check_outcomes_match_orders(orders, outcomes, name="订单表与 user_outcomes 口径一致"),
        _check_event_key_duplicates(events, name="事件业务键无重复上报"),
        # ---- 缺失 ----
        _check_cart_missing_rate(users, cfg, name="cart 缺失率在预期区间内"),
        _check_mnar_evidence(users, name="MNAR 证据：各渠道 cart 缺失率（用户表）"),
        # ---- 观察项 ----
        _check_browse_depth_consistency(
            events, users, name="browse_depth_7d 与事件计数一致（交叉校验）"
        ),
    ]
    return checks


# --------------------------------------------------------------------------- #
# 单项检查：分析框架（0/1 变量与结果列）
# --------------------------------------------------------------------------- #
def _check_binary(df: pd.DataFrame, column: str, *, name: str, severity: str = "error") -> QualityCheck:
    """**0/1 变量取值合法** —— 防"converted = 2 或 0.5"。

    ``converted`` 若出现 2（如"下单笔数"被误当"是否下单"）或 0.5（概率而非
    实现值），``mean()`` 算出来的就不再是转化率。``treatment`` 出现非 0/1
    同理：分组差分会把"2"当成两倍处理强度。这类错误极其隐蔽，因为数值范围
    看起来"差不多"。
    """
    values = df[column].to_numpy()
    observed = sorted({float(v) for v in values if not pd.isna(v)})
    illegal = [v for v in observed if v not in (0.0, 1.0)]
    n_nan = int(pd.isna(values).sum())
    passed = not illegal and n_nan == 0
    return _check(
        name=name,
        passed=passed,
        severity=severity,
        ok=f"{len(df)} 行 {column} 取值 {observed}，全部合法且无缺失",
        bad=(
            f"{len(df)} 行 {column} 出现非法取值 {illegal[: _MAX_EXAMPLES]}、缺失 {n_nan} 行；"
            "非 0/1 会让均值不再是比例"
        ),
        value=float(len(illegal) + n_nan),
    )


def _check_no_nan(df: pd.DataFrame, column: str, *, name: str, severity: str = "error") -> QualityCheck:
    """**关键结果列不得缺失** —— 防"groupby 静默跳过 NaN"。

    ``pandas`` 的 ``mean()/sum()`` 默认跳过 NaN：缺失不会报错，只会让分母
    悄悄变小。对 ``net_profit`` 而言，这等于把一部分用户从利润均值里删掉
    （R1 的反面）。所以结果变量的缺失必须是硬错误。
    """
    n_nan = int(df[column].isna().sum())
    return _check(
        name=name,
        passed=n_nan == 0,
        severity=severity,
        ok=f"{len(df)} 行 {column} 无缺失",
        bad=f"{n_nan}/{len(df)} 行 {column} 缺失；聚合时会静默少算这些人（R1）",
        value=float(n_nan),
    )


def _check_unconverted_zero_profit(df: pd.DataFrame, *, name: str) -> QualityCheck:
    """**未转化用户的 net_profit 恰为 0** —— R1 的正面表达。

    未下单用户的净贡献利润必须是 **0**（保留在分母里、贡献为零），
    而不是 NaN（被跳过）也不是某个"平均订单利润"（凭空造钱）。
    若这一项不过，几乎可以肯定是有人把未转化用户剔除了，再拿"人均订单利润"
    当"人均利润"。
    """
    unconverted = df["converted"].to_numpy() == 0
    values = df["net_profit"].to_numpy(dtype=float)[unconverted]
    n_wrong = int((values != 0.0).sum())
    return _check(
        name=name,
        passed=n_wrong == 0,
        severity="error",
        ok=f"未转化用户 {int(unconverted.sum())} 个，net_profit 全为 0",
        bad=(
            f"未转化用户 {int(unconverted.sum())} 个，其中 {n_wrong} 个 net_profit 非 0；"
            "未转化用户必须留在分母且贡献为 0（R1）"
        ),
        value=float(n_wrong),
    )


def check_analysis_frame(
    df: pd.DataFrame, cfg: Any, *, n_sigma: float = 3.0
) -> list[QualityCheck]:
    """对用户级分析框架跑清单。

    分析框架是**估计器的直接输入**，所以额外要求：处理/结果变量必须是 0/1，
    利润不得缺失，未转化用户的利润必须恰好为 0（R1：未转化用户留在分母里，
    他们的净贡献利润是 0，而不是被剔出样本）。

    参数
    ----
    df : ``build_analysis_frame`` 的输出，**也可以**是 ``clean_analysis_frame``
        的输出（此时优先用 ``cart_value_was_missing`` 指示列还原 MNAR 证据）。
    cfg : 配置对象。
    n_sigma : 比例类检查的容差倍数，默认 3σ。
    """
    _require_columns(
        df,
        ("user_id", "treatment", "converted", "net_profit", "channel"),
        where="分析框架",
    )
    cart_col = _cart_column(df)
    indicator = f"{cart_col}_was_missing"

    checks: list[QualityCheck] = [
        _check_binary(df, "treatment", name="分析框架：treatment ∈ {0,1}"),
        _check_binary(df, "converted", name="分析框架：converted ∈ {0,1}"),
        _check_no_nan(df, "net_profit", name="分析框架：net_profit 无缺失（R1）"),
        _check_unconverted_zero_profit(df, name="分析框架：未转化用户 net_profit 恰为 0"),
        _check_unique_key(df, "user_id", name="分析框架：每用户仅一行", table="分析框架"),
        _check_cart_missing_rate(
            df,
            cfg,
            name="分析框架：cart 缺失率在预期区间内",
            column=cart_col,
            n_sigma=n_sigma,
        ),
        _check_mnar_evidence(
            df,
            name="MNAR 证据：各渠道 cart 缺失率（分析框架）",
            column=cart_col,
            indicator=indicator,
        ),
    ]
    return checks


# --------------------------------------------------------------------------- #
# 汇总与门禁
# --------------------------------------------------------------------------- #
def summarize(checks: Sequence[QualityCheck]) -> pd.DataFrame:
    """把检查结果汇总成一张中文报表（列：检查项/结果/级别/详情/数值）。"""
    columns = ["检查项", "结果", "级别", "详情", "数值"]
    if not checks:
        empty = pd.DataFrame(
            {
                "检查项": pd.Series(dtype="object"),
                "结果": pd.Series(dtype="object"),
                "级别": pd.Series(dtype="object"),
                "详情": pd.Series(dtype="object"),
                "数值": pd.Series(dtype="float64"),
            }
        )
        return empty.loc[:, columns]
    return pd.DataFrame(
        [
            {
                "检查项": c.name,
                "结果": "通过" if c.passed else "未通过",
                "级别": c.severity,
                "详情": c.detail,
                "数值": c.value,
            }
            for c in checks
        ],
        columns=columns,
    )


def assert_no_errors(checks: Sequence[QualityCheck]) -> None:
    """有 ``error`` 级失败就抛 ``QualityError``（AGENTS.md §3.6 失败要响）。

    ``warning`` / ``info`` 级失败**不阻断**：它们是给人看的披露项，
    应该在报告里出现，而不是让管线停下。但 ``error`` 级失败意味着口径已被
    破坏，此时继续跑出来的任何结论都是错的，必须当场停。
    """
    failed = [c for c in checks if c.severity == "error" and not c.passed]
    if not failed:
        return
    lines = [f"  - [{c.name}] {c.detail}" for c in failed]
    raise QualityError(
        f"数据质量门禁未通过：{len(failed)} 项 error 级检查失败\n" + "\n".join(lines)
    )
