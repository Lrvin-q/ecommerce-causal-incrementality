"""Phase D D.2：**完整 DGP 链路**的 AA（随机化有效性）校验。

回答哪个问题
------------
HITL 修订建议 §7.2 原文："完整 AA 必须走五表、污染/清洗、SQL 及估计流程：
同一处理条件下分配虚拟 A/B 标签，两个标签不改变购买、券成本或退款机制。
原二元/正态 AA 保留为检验模块单测，明确与完整 AA 分开。"

本模块就是这条要求的可执行入口：对 L0–L3 各取**一个已注册的** ``*_AA`` 格，
把「分析标签」与「实际发券动作」解耦，跑完
``生成人群 → 五表 → 污染/清洗 → SQL → 观测表 → ITT``，
再用 p 值分布 / 假阳性率 / 覆盖率 / CPU 成本给出结论。

为什么不能只做"二元正态玩具"
----------------------------
:mod:`causal_growth.design.aa` 的玩具 AA 只检验"抽样 + t 检验"这一步。它无法发现
五表构造、污染注入、确定性去重、SQL 物化、拆分与观察表投影里引入的
「标签—结果」伪关联——而这些环节恰好是真实分析流程里最可能出错的地方。
完整 AA 是唯一能证明**整条链路**没有把随机标签变成伪处理变量的证据。

虚拟标签怎么贴、为什么不改变机制
--------------------------------
冻结配置 ``configs/v3/scenarios.yaml`` 已注册四个 AA 格（``L0_AA``…``L3_AA``），
覆盖 ``dgp.virtual_aa_labels: true`` 与 ``dgp.actual_action_override: 0``：

1. **实际动作**：``dgp/v3_probability.assign_treatment`` 把 ``actual_action`` 全置为
   ``design.aa.actual_action``（=0，全员不发券），不读任何协变量；因此券面额
   ``coupon_face_cent = actual_action × 面额`` 恒为 0，券成本、核销、退款乘子
   （``refund_rate_treated_multiplier`` 只对 action=1 生效）全部与标签无关。
2. **虚拟标签**：独立随机流 ``{prefix}.assignment.aa_virtual_label`` 派生
   Bernoulli(``design.aa.virtual_label_probability=0.5``)，与动作流
   ``{prefix}.assignment.action``、购买/退款/核销/金额/时点各流互不共享。
3. **结果机制**：购买、金额、履约、退款、时点全部只由 X/U 与 ``actual_action``
   决定（见 ``dgp/v3_engine._world_orders``）。标签既不在结果函数里出现，也不改
   任何一个随机流，故两个标签是**同一结果机制**下的两次随机分组。
4. **SQL 落库**：``v3_analytics.sql`` 以 ``label AS treatment`` 作分析标签，
   ``actual_action`` 只驱动券面额；质量门禁 ``historical_action_label`` 强制
   AA 场景下 ``actual_action`` 全等于冻结动作。

**这不是"购买零增量 + 照常发券"的负对照。** 后者（``L0_zero_purchase_effect``）
的处理组真的领券并产生补贴成本，利润效应可以显著为负；把它当"利润零效应 AA"
是把"可干预动作差"与"标签差"混为一谈（B 阶段审计：该格平均利润 CATE −0.559 元，
见 ``docs/reviews/v3_phase_B_review.md``）。本模块用 ``block`` 列把两者分开登记，
只有 ``block=true_aa`` 的行可以被称为"AA 通过"。

估计与汇总口径
--------------
* 主指标 ``net_profit``（元/合格用户）走 Welch t；诊断指标 ``paid_purchase_7d``
  与护栏指标 ``any_refund_30d`` 走两比例 z（pooled 检验 / unpooled 区间，
  见 :mod:`causal_growth.estimate.itt`）。主指标先报，辅助指标不参与主决策。
* 分析分母是**随机贴标签的全部用户**（R1）；``full`` 为全部分配用户，
  ``test`` 为冻结 30% 测试拆分上的同一估计（诊断，防止结论只是分拆产物）。
* 假阳性率 = ``mean(p < alpha)``，区间用 **Clopper–Pearson 精确区间**（本模块实现），
  同时报二项 MC 标准误 ``sqrt(p(1-p)/R)``：有限 R 下不可能精确等于 alpha，
  必须让读者看到"0.05 ± 多少"。
* 覆盖率 = 95% 置信区间是否含 0（AA 下真值为 0）。**读法警告**：对 Welch t，
  "区间含 0" 与 "p ≥ alpha" 是同一个事件，所以覆盖率 ≡ 1 − 假阳性率，
  它不是独立证据；只有两比例检验（CI 用非合并方差、检验用合并方差）两者才略有差别。

纪律
----
* 只接触 ``ObservedDataset.observations`` 的可观测列与
  ``population.observation_bundle()``；不读 ``audit_*``、不 import ``audit/``。
* 随机性只经 :func:`causal_growth.rng.child_rng`（由 DGP 内部派生），
  同一 ``(master_seed, stream, index)`` 逐位可复现；本模块不新增随机流。
* 链路不变量失败立即抛 :class:`AAChainError`，不吞掉继续跑；失败 rep 的产物保留。
* 本入口不改变任何正式计数器（``formal_repetitions_completed`` 仍为 0）。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe -m causal_growth.evaluation.v3_aa --reps 50 --n 10000

正式规模（**需用户裁决后才执行**）::

    .\\.venv\\Scripts\\python.exe -m causal_growth.evaluation.v3_aa --reps 1000 --n 200000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import numpy as np
import pandas as pd
from scipy import stats

from causal_growth.config import Config
from causal_growth.data.v3_pipeline import build_observed_pipeline
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.estimate.itt import (
    ITTResult,
    itt_difference_means,
    itt_difference_proportions,
)
from causal_growth.v3_config import V3Protocol, load_v3_protocol
from causal_growth.v3_data_config import load_v3_data_config

__all__ = [
    "AA_METRICS",
    "AABundle",
    "AACell",
    "AAChainError",
    "AAMetric",
    "PROJECT_ROOT",
    "SOURCE_CHANGED_MARKER",
    "SUMMARY_COLUMNS",
    "aa_cells",
    "clopper_pearson",
    "is_source_changed_error",
    "main",
    "run_aa_rep",
    "run_full_chain_aa",
    "summarize_repetitions",
    "write_outputs",
]

#: 项目根目录（``src/causal_growth/evaluation/v3_aa.py`` 往上三层）。
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

#: 假阳性率 Clopper–Pearson 区间的置信水平。统计惯例，不是业务参数。
_CP_CONFIDENCE = 0.95

#: 样本比例失衡（SRM）诊断的显著性水平。工程惯例（先定 0.001 再看结果）。
_SRM_ALPHA = 0.001

#: 汇总表的稳定列序；报告里引用的每个数字都落在这里。
SUMMARY_COLUMNS: tuple[str, ...] = (
    "source_label", "block", "row_kind", "scenario_id", "level", "metric", "metric_role",
    "analysis_population", "truth", "R", "n_registered", "n_total_mean", "n_label1_mean",
    "n_label0_mean", "alpha", "fpr", "fpr_cp_lower", "fpr_cp_upper", "fpr_mc_se",
    "coverage", "coverage_cp_lower", "coverage_cp_upper", "mean_p", "median_p",
    "ks_uniform_stat", "ks_uniform_pvalue", "mean_diff", "mean_diff_se", "mean_ci_width",
    "label_share_min", "label_share_max", "srm_rejections_at_0.001", "srm_reps",
    "dgp_cpu_s_mean", "pipeline_cpu_s_mean", "itt_cpu_s_mean", "total_cpu_s_mean",
    "total_cpu_s_median", "wall_s_mean", "config_hash", "interpretation", "note",
)

_SOURCE_LABEL = "合成数据 / 已知 DGP"

#: 汇总表里的 ``row_kind``：指标诊断 vs 成本/随机化完整性。
_ROW_METRIC = "metric_aa"
_ROW_COST = "cost_integrity"

_BLOCK_TRUE_AA = "true_aa"
_BLOCK_NEGATIVE_CONTROL = "purchase_null_negative_control"
_BLOCK_COST_ANCHOR = "cost_anchor"

_POOLED = "POOLED_4_LAYERS"

#: 每个（分析人群 × 指标）在逐 rep 表里展开的字段（与 :class:`ITTResult` 同名）。
_ITT_FIELDS: tuple[str, ...] = ("diff", "se", "ci_lower", "ci_upper", "p_value", "n_treated", "n_control")

#: 两个分析人群。``full`` 是 R1 口径的全部分配用户；``test`` 是冻结拆分的诊断。
_POPULATIONS: tuple[str, ...] = ("full", "test")


class AAChainError(RuntimeError):
    """完整链路违反 AA 不变量：标签与结果机制不再等价，必须立即停。"""


#: C 阶段源码绑定门禁在"rep 执行期间有源码被改写"时抛出的固定消息片段。
#: 多代理并行写 ``src/causal_growth/**/v3*.py`` 时会出现；它是**环境故障**，
#: 不是链路/口径异常——同一 rep 序号重跑得到逐位相同的数据。
SOURCE_CHANGED_MARKER = "source files changed during the data run"


def is_source_changed_error(exc: BaseException) -> bool:
    """是否属于"并发写盘触发源码绑定门禁"这一**唯一**允许重试/跳过的异常。"""
    return (isinstance(exc, RuntimeError) and not isinstance(exc, AAChainError)
            and SOURCE_CHANGED_MARKER in str(exc))


#: Windows 上"文件被短暂占用"的 winerror：5=拒绝访问，32=共享冲突，33=锁冲突。
_WINDOWS_LOCK_WINERRORS = frozenset({5, 32, 33})


def find_windows_file_lock(exc: BaseException) -> OSError | None:
    """在异常链里找出 Windows 文件占用错误（``os.replace`` 的原子替换会撞上）。

    ``RunArtifactWriter`` 每次落盘都用 ``.tmp → replace``；Windows 上扫描器/索引器
    短暂持有文件时 ``os.replace`` 抛 ``PermissionError [WinError 5]``。该错误还会被
    流水线的兜底 ``writer.finish(passed=False)`` 二次包装成
    ``ValueError: run is already terminal``，所以必须沿 ``__context__/__cause__`` 链找。
    它属于**环境故障**（同一 rep 重跑逐位相同），不是链路/口径异常。
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError) and getattr(current, "winerror", None) in _WINDOWS_LOCK_WINERRORS:
            return current
        current = current.__context__ or current.__cause__
    return None


# --------------------------------------------------------------------------- #
# 指标定义
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AAMetric:
    """一个参与 AA 检验的观察表列及其统计角色。"""

    column: str
    role: str
    kind: str
    unit: str

    def __post_init__(self) -> None:
        if self.kind not in {"continuous", "binary"}:
            raise ValueError(f"未知指标类型：{self.kind}")
        if self.role not in {"confirmatory_primary", "auxiliary_diagnostic", "guardrail_diagnostic"}:
            raise ValueError(f"未知指标角色：{self.role}")


#: 主指标在前：报告只把 ``net_profit`` 的假阳性率当 AA 结论。
AA_METRICS: tuple[AAMetric, ...] = (
    AAMetric("net_profit", "confirmatory_primary", "continuous", "CNY/person"),
    AAMetric("paid_purchase_7d", "auxiliary_diagnostic", "binary", "share"),
    AAMetric("any_refund_30d", "guardrail_diagnostic", "binary", "share"),
)


# --------------------------------------------------------------------------- #
# Clopper–Pearson 精确区间
# --------------------------------------------------------------------------- #
def clopper_pearson(successes: int, trials: int, confidence: float = _CP_CONFIDENCE) -> tuple[float, float]:
    """二项比例的 Clopper–Pearson 精确区间（Beta 分位数，双尾等尾）。

    回答方案里的哪个问题："R 次 AA 里出现 k 次假阳性，真实假阳性率可能的范围是多少？"
    与 Wilson 区间（:mod:`causal_growth.design.aa` 玩具 AA 所用）相比，CP 更保守，
    在 ``R=50``、``k=1~3`` 这种小样本下不会给出过窄的区间；本项目要求"报告 MC 精度、
    不假装有限 R 能得到精确 0.05"，所以正式区间用 CP。

    Parameters
    ----------
    successes, trials:
        假阳性次数与总重复次数；``0 <= successes <= trials``，``trials >= 1``。
    confidence:
        置信水平，默认 0.95。

    Returns
    -------
    tuple[float, float]
        ``(lower, upper)``；``k=0`` 时下界为 0，``k=R`` 时上界为 1。
    """
    if isinstance(successes, bool) or isinstance(trials, bool):
        raise TypeError("successes/trials 必须是整数，不能是 bool")
    if not isinstance(successes, (int, np.integer)) or not isinstance(trials, (int, np.integer)):
        raise TypeError("successes/trials 必须是整数")
    if trials < 1:
        raise ValueError(f"trials 至少为 1，收到 {trials}")
    if not 0 <= successes <= trials:
        raise ValueError(f"successes 必须落在 [0, trials]：{successes}/{trials} 非法")
    if not 0.0 < float(confidence) < 1.0:
        raise ValueError(f"confidence 必须在 (0,1) 内，收到 {confidence}")
    tail = (1.0 - float(confidence)) / 2.0
    lower = 0.0 if successes == 0 else float(stats.beta.ppf(tail, successes, trials - successes + 1))
    upper = 1.0 if successes == trials else float(stats.beta.ppf(1.0 - tail, successes + 1, trials - successes))
    return lower, upper


# --------------------------------------------------------------------------- #
# 已注册 AA 格
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AACell:
    """一个已注册的完整 AA 格（每层恰好一个）。"""

    scenario_id: str
    level: str
    tier: int
    registered_n: int
    registered_reps: int
    actual_action: int
    virtual_label_probability: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id, "level": self.level, "tier": self.tier,
            "registered_n": self.registered_n, "registered_reps": self.registered_reps,
            "actual_action": self.actual_action,
            "virtual_label_probability": self.virtual_label_probability,
        }


def aa_cells(protocol: V3Protocol) -> tuple[AACell, ...]:
    """从冻结矩阵里取"每层一个"的完整 AA 格，并核对 AA 合同。

    格数来自 ``scenarios.yaml`` 的 ``formal_repetitions.complete_aa``，不手抄场景 ID；
    层清单来自 ``matrix_contract.reference_scenarios``，避免漏层或多层。
    """
    data = protocol.config.to_dict()
    levels = tuple(data["matrix_contract"]["reference_scenarios"].keys())
    declared = int(data["execution"]["formal_repeats"]["tier1_aa_per_layer"])
    registered = [s for s in data["scenarios"] if s["formal_repetitions"]["complete_aa"] > 0]
    cells: list[AACell] = []
    for level in levels:
        matches = [s for s in registered if s["level"] == level]
        if len(matches) != 1:
            raise AAChainError(f"每层必须恰有一个完整 AA 格，{level} 实际 {len(matches)} 个")
        cell = matches[0]
        if cell["tier"] != 1:
            raise AAChainError(f"完整 AA 必须是 Tier 1：{cell['id']}")
        if cell["formal_repetitions"]["complete_aa"] != declared or cell["R"] != declared:
            raise AAChainError(
                f"完整 AA 重复数与 execution.formal_repeats.tier1_aa_per_layer 不一致：{cell['id']}"
            )
        if cell["models"]:
            raise AAChainError(f"完整 AA 不拟合模型，但 {cell['id']} 声明了 models")
        overrides = cell["overrides"]
        if not overrides.get("dgp.virtual_aa_labels"):
            raise AAChainError(f"完整 AA 必须开启虚拟标签：{cell['id']}")
        cfg = protocol.scenario(cell["id"])
        actual = int(cfg.require("design.aa.actual_action"))
        if overrides.get("dgp.actual_action_override") != actual:
            raise AAChainError(f"完整 AA 的实际动作与 design.aa.actual_action 不一致：{cell['id']}")
        if float(cfg.require("design.aa.virtual_label_probability")) != 0.5:
            raise AAChainError(f"虚拟标签概率偏离 1:1 设计：{cell['id']}")
        cells.append(AACell(
            scenario_id=cell["id"], level=level, tier=int(cell["tier"]),
            registered_n=int(cell["n"]), registered_reps=declared,
            actual_action=actual,
            virtual_label_probability=float(cfg.require("design.aa.virtual_label_probability")),
        ))
    return tuple(cells)


def _resolve_cell_config(cell: AACell, protocol: V3Protocol) -> tuple[Config, bool]:
    """取出格配置并交叉核对；返回 ``(cfg, 是否虚拟标签AA)``。"""
    cfg = protocol.scenario(cell.scenario_id)
    if str(cfg.require("active_scenario.id")) != cell.scenario_id:
        raise AAChainError(f"场景解析错位：{cfg.require('active_scenario.id')} != {cell.scenario_id}")
    if int(cfg.require("active_scenario.tier")) != cell.tier:
        raise AAChainError(f"{cell.scenario_id} 的 tier 与格记录不一致")
    virtual_aa = bool(cfg.require("dgp.virtual_aa_labels"))
    if virtual_aa:
        actual = int(cfg.require("design.aa.actual_action"))
        if cfg.require("dgp.actual_action_override") != actual:
            raise AAChainError(f"{cell.scenario_id} 的动作覆盖与 design.aa.actual_action 不一致")
        if actual != cell.actual_action:
            raise AAChainError(f"{cell.scenario_id} 的实际动作与格记录不一致")
    return cfg, virtual_aa


# --------------------------------------------------------------------------- #
# 计时
# --------------------------------------------------------------------------- #
class _StageTimer:
    """记录各阶段进程 CPU 秒与墙钟；CPU 秒是 G 阶段外推的口径。"""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, float]] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        cpu0 = time.process_time()
        wall0 = time.perf_counter()
        try:
            yield
        finally:
            self.rows[name] = {"cpu_s": time.process_time() - cpu0,
                               "wall_s": time.perf_counter() - wall0}


# --------------------------------------------------------------------------- #
# 链路不变量
# --------------------------------------------------------------------------- #
def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AAChainError(message)


def _check_assignment_inputs(
    assignments: pd.DataFrame, *, cfg: Config, virtual_aa: bool, n: int,
) -> None:
    """进链路前确认：AA 场景下标签随机、动作冻结；负对照下标签就是动作。"""
    _require(len(assignments) == n, f"分配人数 {len(assignments)} 与请求 n={n} 不符")
    _require(bool(assignments.user_id.is_unique), "分配表用户不唯一")
    labels = set(assignments.label.unique().tolist())
    _require(labels == {0, 1}, f"分析标签必须同时出现 0/1，实际 {sorted(labels)}")
    if virtual_aa:
        frozen_action = int(cfg.require("design.aa.actual_action"))
        actions = set(assignments.actual_action.unique().tolist())
        _require(actions == {frozen_action},
                 f"虚拟标签 AA 的实际动作必须恒为 {frozen_action}，实际 {sorted(actions)}")
        expected_probability = float(cfg.require("design.aa.virtual_label_probability"))
    else:
        _require(bool(np.array_equal(assignments.actual_action.to_numpy(), assignments.label.to_numpy())),
                 "非 AA 场景的分析标签必须等于实际动作")
        expected_probability = float(cfg.require("design.treatment_probability"))
    recorded = assignments.design_probability.to_numpy(dtype=float)
    _require(bool(np.allclose(recorded, expected_probability, atol=1e-12, rtol=0)),
             f"记录的设计概率必须等于冻结随机化概率 {expected_probability}")


def _check_observed_chain(
    observations: pd.DataFrame, users: pd.DataFrame, assignments: pd.DataFrame,
    *, run_id: str, n: int, virtual_aa: bool, frozen_action: int | None = None,
) -> None:
    """确认整条链路没有把虚拟标签变成伪处理变量（违反即刻抛）。"""
    _require(len(observations) == n, f"观测表人数 {len(observations)} != n={n}（违反 R1 分母）")
    _require(bool(observations.user_id.is_unique), "观测表用户键重复")
    _require(set(observations.user_id) == set(users.user_id), "观测表用户集合与生成人群不一致")
    _require(observations.run_id.nunique() == 1 and str(observations.run_id.iloc[0]) == run_id,
             "观测表 run_id 与本 rep 不一致")
    labels = assignments.set_index("user_id")["label"]
    mapped = labels.reindex(observations.user_id)
    _require(bool(mapped.notna().all()), "观测用户缺少输入的标签")
    _require(bool(np.array_equal(mapped.to_numpy(), observations.treatment.to_numpy())),
             "观测表 treatment 不等于输入的标签")
    if virtual_aa:
        _require(bool(observations.actual_action.eq(int(frozen_action)).all()),
                 "观测表实际动作偏离冻结动作：标签被写进了动作列")
        for column in ("coupon_cost", "coupon_cost_cent"):
            _require(bool(observations[column].eq(0).all()),
                     f"虚拟标签 AA 下 {column} 必须恒为 0（实际动作全为 {frozen_action}）")
    else:
        _require(bool(np.array_equal(observations.actual_action.to_numpy(), observations.treatment.to_numpy())),
                 "负对照场景的标签必须等于实际动作")
    _require(bool(observations.mature.astype(bool).all()), "观测表存在未成熟用户")
    if "diagnostic_snapshot" in observations:
        _require(not bool(observations.diagnostic_snapshot.astype(bool).any()), "诊断快照不得进入 AA 主分析")
    _require(bool(observations.split.notna().all()), "观测表存在未分配拆分的用户")
    _require(set(observations.treatment.unique().tolist()) == {0, 1}, "观测表标签退化")


# --------------------------------------------------------------------------- #
# 单 rep
# --------------------------------------------------------------------------- #
def _estimate_metric(frame: pd.DataFrame, metric: AAMetric, alpha: float) -> ITTResult:
    """按指标类型调用冻结的 ITT 实现，并守住"分母 = 全部分配用户"。"""
    if metric.kind == "continuous":
        result = itt_difference_means(frame, metric.column, treatment_col="treatment", alpha=alpha,
                                      metric=metric.column)
    else:
        result = itt_difference_proportions(frame, metric.column, treatment_col="treatment", alpha=alpha,
                                            metric=metric.column)
    if result.n_treated + result.n_control != len(frame):
        raise AAChainError(
            f"{metric.column} 的分母 {result.n_treated}+{result.n_control} != 分析人数 {len(frame)}"
        )
    return result


def run_aa_rep(
    cell: AACell,
    protocol: V3Protocol,
    *,
    rep: int,
    n: int,
    run_dir: str | Path,
    block: str = _BLOCK_TRUE_AA,
    alpha: float | None = None,
    keep_artifacts: bool = False,
) -> dict[str, Any]:
    """跑一次完整链路 rep，返回一行逐 rep 结果。

    顺序固定：``DGP → 贴虚拟标签 → 五表 → 污染/清洗 → SQL → 观测表 →
    R1 不变量 → 三个指标 × 两个分析人群的 ITT``。任一不变量失败抛
    :class:`AAChainError`，并保留失败 rep 的产物目录。

    同一个函数也服务负对照格：是否套用"虚拟标签"不变量由**该格配置**的
    ``dgp.virtual_aa_labels`` 决定，不由调用方声明，避免调用方误标。

    Parameters
    ----------
    cell, protocol:
        格元数据与协议；两者交叉核对，防止"配置漂移后仍按旧假设跑"。
    rep:
        DGP 重复序号，同时是 ``child_rng`` 的 ``index``；同一
        ``(master_seed, stream, rep)`` 逐位可复现。
    n:
        本次人群规模（工程规模，可小于注册 n；正式运行必须等于注册 n）。
    run_dir:
        本次尝试的**新**目录（不得预先存在），由流水线写入五表 / SQL 产物。
    block:
        结果归属块；只有 ``true_aa`` 与 ``cost_anchor`` 属于 AA。
    alpha:
        显著性水平；``None`` 时取 ``design.alpha_two_sided``。
    keep_artifacts:
        保留产物（失败时无论取值都会保留，作为失败证据）。
    """
    cfg, virtual_aa = _resolve_cell_config(cell, protocol)
    if block == _BLOCK_TRUE_AA and not virtual_aa:
        raise AAChainError(f"{cell.scenario_id} 不是虚拟标签 AA，不能登记为 true_aa")
    if block == _BLOCK_NEGATIVE_CONTROL and virtual_aa:
        raise AAChainError(f"{cell.scenario_id} 是虚拟标签 AA，不能登记为负对照")
    level_alpha = float(cfg.require("design.alpha_two_sided")) if alpha is None else float(alpha)
    if not 0.0 < level_alpha < 1.0:
        raise ValueError(f"alpha 必须在 (0,1) 内，收到 {level_alpha}")
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or int(n) < 2:
        raise ValueError(f"n 必须是 >= 2 的整数，收到 {n!r}")
    if isinstance(rep, bool) or not isinstance(rep, (int, np.integer)) or int(rep) < 0:
        raise ValueError(f"rep 必须是 >= 0 的整数，收到 {rep!r}")
    n, rep = int(n), int(rep)
    frozen_action = int(cfg.require("design.aa.actual_action")) if virtual_aa else None
    run_id = f"aa:{block}:{cell.scenario_id}:rep{rep}:n{n}"
    timer = _StageTimer()
    succeeded = False
    row: dict[str, Any] = {}
    try:
        with timer.stage("dgp"):
            population = generate_v3_population(cfg, rep_id=rep, n=n)
        users, assignments, orders = population.observation_bundle()
        stream_prefix = str(population.metadata["stream_prefix"])
        _check_assignment_inputs(assignments, cfg=cfg, virtual_aa=virtual_aa, n=n)

        with timer.stage("pipeline"):
            result = build_observed_pipeline(
                users, assignments, orders, cfg,
                directory=Path(run_dir), run_id=run_id, rep_id=rep, stream_prefix=stream_prefix,
                persist_database=False, retention_scope="engineering_full",
            )
        observations = result.dataset.observations
        _check_observed_chain(observations, users, assignments, run_id=run_id, n=n,
                              virtual_aa=virtual_aa, frozen_action=frozen_action)

        n_label1 = int(observations.treatment.sum())
        n_label0 = int(len(observations) - n_label1)
        row = {
            "source_label": _SOURCE_LABEL, "block": block, "scenario_id": cell.scenario_id,
            "level": cell.level, "tier": cell.tier, "rep": rep, "run_id": run_id,
            "virtual_aa": virtual_aa, "n_requested": n, "n_total": int(len(observations)),
            "n_label1": n_label1, "n_label0": n_label0, "label_share": n_label1 / len(observations),
            "n_orders": int(len(orders)), "registered_n": cell.registered_n,
            "actual_action_share": float(observations.actual_action.mean()),
            "virtual_label_probability": cell.virtual_label_probability,
            "config_hash": cfg.hash(64), "protocol_config_hash": protocol.config_hash,
            "stream_prefix": stream_prefix, "alpha": level_alpha,
            "coupon_cost_total": float(observations.coupon_cost.sum()),
            "split_train": int((observations.split == "train").sum()),
            "split_validation": int((observations.split == "validation").sum()),
            "split_test": int((observations.split == "test").sum()),
        }
        row["srm_p_value"] = float(
            stats.binomtest(n_label1, len(observations), cell.virtual_label_probability).pvalue
        )

        with timer.stage("itt"):
            for population_name, frame in (
                ("full", observations),
                ("test", observations.loc[observations.split == "test"]),
            ):
                if len(frame) < 4:
                    raise AAChainError(f"{population_name} 人群只有 {len(frame)} 人，无法估计")
                for metric in AA_METRICS:
                    estimate = _estimate_metric(frame, metric, level_alpha)
                    for field in _ITT_FIELDS:
                        value = getattr(estimate, field)
                        row[f"{population_name}_{metric.column}_{field}"] = (
                            int(value) if field.startswith("n_") else float(value)
                        )
        succeeded = True
    finally:
        if succeeded and not keep_artifacts:
            shutil.rmtree(Path(run_dir), ignore_errors=True)

    total_cpu = 0.0
    total_wall = 0.0
    for name, payload in timer.rows.items():
        row[f"{name}_cpu_s"] = payload["cpu_s"]
        row[f"{name}_wall_s"] = payload["wall_s"]
        total_cpu += payload["cpu_s"]
        total_wall += payload["wall_s"]
    row["total_cpu_s"] = total_cpu
    row["total_wall_s"] = total_wall
    return row


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def _truth_and_interpretation(block: str, metric: AAMetric) -> tuple[float, str]:
    """给出该块该指标的**真值口径**与读法，防止把功效当假阳性率。"""
    if block in {_BLOCK_TRUE_AA, _BLOCK_COST_ANCHOR}:
        return 0.0, "false_positive_rate_under_true_null"
    if block == _BLOCK_NEGATIVE_CONTROL:
        if metric.column == "paid_purchase_7d":
            return 0.0, "size_under_true_purchase_null"
        if metric.column == "net_profit":
            return float("nan"), "power_under_nonzero_profit_truth_not_aa"
        return float("nan"), "power_under_nonzero_guardrail_truth_not_aa"
    raise ValueError(f"未知 block：{block}")


def _summarize_metric_cell(
    frame: pd.DataFrame, *, block: str, scenario_id: str, level: str, metric: AAMetric,
    population: str, alpha: float, n_registered: int, config_hash: str, note: str = "",
) -> dict[str, Any]:
    """把一个（格 × 指标 × 人群）的 R 个 p 值汇总成 AA 诊断行。"""
    p_values = frame[f"{population}_{metric.column}_p_value"].to_numpy(dtype=float)
    lower = frame[f"{population}_{metric.column}_ci_lower"].to_numpy(dtype=float)
    upper = frame[f"{population}_{metric.column}_ci_upper"].to_numpy(dtype=float)
    diff = frame[f"{population}_{metric.column}_diff"].to_numpy(dtype=float)
    n_label1 = frame[f"{population}_{metric.column}_n_treated"].to_numpy(dtype=float)
    n_label0 = frame[f"{population}_{metric.column}_n_control"].to_numpy(dtype=float)
    repetitions = int(p_values.size)
    if repetitions < 1:
        raise ValueError("汇总至少需要 1 次重复")
    if not np.all(np.isfinite(p_values)):
        raise AAChainError(f"{scenario_id}/{metric.column}/{population} 存在非有限 p 值")
    hits = int(np.count_nonzero(p_values < alpha))
    cp_lower, cp_upper = clopper_pearson(hits, repetitions)
    fpr = hits / repetitions
    truth, interpretation = _truth_and_interpretation(block, metric)
    has_truth = math.isfinite(truth)
    covered = int(np.count_nonzero((lower <= 0.0) & (upper >= 0.0)))
    cov_lower, cov_upper = clopper_pearson(covered, repetitions)
    ks = stats.kstest(p_values, "uniform") if repetitions >= 2 else None
    return {
        "source_label": _SOURCE_LABEL,
        "block": block,
        "row_kind": _ROW_METRIC,
        "scenario_id": scenario_id,
        "level": level,
        "metric": metric.column,
        "metric_role": metric.role,
        "analysis_population": population,
        "truth": truth,
        "R": repetitions,
        "n_registered": n_registered,
        "n_total_mean": float(frame["n_total"].mean()),
        "n_label1_mean": float(n_label1.mean()),
        "n_label0_mean": float(n_label0.mean()),
        "alpha": alpha,
        "fpr": fpr,
        "fpr_cp_lower": cp_lower,
        "fpr_cp_upper": cp_upper,
        "fpr_mc_se": math.sqrt(max(fpr * (1.0 - fpr), 0.0) / repetitions),
        # 真值非 0 时"区间含 0"不是覆盖率，必须留空而不是给出误导数字。
        "coverage": (covered / repetitions) if has_truth else float("nan"),
        "coverage_cp_lower": cov_lower if has_truth else float("nan"),
        "coverage_cp_upper": cov_upper if has_truth else float("nan"),
        "mean_p": float(p_values.mean()),
        "median_p": float(np.median(p_values)),
        "ks_uniform_stat": float(ks.statistic) if ks is not None else float("nan"),
        "ks_uniform_pvalue": float(ks.pvalue) if ks is not None else float("nan"),
        "mean_diff": float(diff.mean()),
        "mean_diff_se": float(diff.std(ddof=1) / math.sqrt(repetitions)) if repetitions > 1 else float("nan"),
        "mean_ci_width": float(np.mean(upper - lower)),
        "config_hash": config_hash,
        "interpretation": interpretation,
        "note": note,
    }


def _summarize_cost_cell(
    frame: pd.DataFrame, *, block: str, scenario_id: str, level: str, n_registered: int,
    config_hash: str, note: str,
) -> dict[str, Any]:
    """把逐 rep 的 CPU / 随机化完整性汇成一行（不重复每个指标）。"""
    srm = frame["srm_p_value"].to_numpy(dtype=float)
    row: dict[str, Any] = {column: float("nan") for column in SUMMARY_COLUMNS}
    row.update({
        "source_label": _SOURCE_LABEL, "block": block, "row_kind": _ROW_COST,
        "scenario_id": scenario_id, "level": level, "metric": "-", "metric_role": "-",
        "analysis_population": "-", "R": int(len(frame)), "n_registered": n_registered,
        "n_total_mean": float(frame["n_total"].mean()),
        "n_label1_mean": float(frame["n_label1"].mean()),
        "n_label0_mean": float(frame["n_label0"].mean()),
        "alpha": float(frame["alpha"].iloc[0]),
        "label_share_min": float(frame["label_share"].min()),
        "label_share_max": float(frame["label_share"].max()),
        "srm_rejections_at_0.001": int(np.count_nonzero(srm < _SRM_ALPHA)),
        "srm_reps": int(len(frame)),
        "dgp_cpu_s_mean": float(frame["dgp_cpu_s"].mean()),
        "pipeline_cpu_s_mean": float(frame["pipeline_cpu_s"].mean()),
        "itt_cpu_s_mean": float(frame["itt_cpu_s"].mean()),
        "total_cpu_s_mean": float(frame["total_cpu_s"].mean()),
        "total_cpu_s_median": float(frame["total_cpu_s"].median()),
        "wall_s_mean": float(frame["total_wall_s"].mean()),
        "config_hash": config_hash,
        "interpretation": "cost_and_randomization_integrity",
        "note": note,
    })
    return row


def summarize_repetitions(
    repetitions: pd.DataFrame, *, alpha: float | None = None,
) -> pd.DataFrame:
    """把逐 rep 结果汇总成报告可直接引用的长表。

    行分两类（``row_kind``）：``metric_aa`` 是某（格 × 指标 × 人群）的
    假阳性率 / CP 区间 / 覆盖率 / p 值分布；``cost_integrity`` 是该格的
    CPU 成本与随机化完整性（SRM），两类的数值列互斥（不适用的位置留 NaN）。

    每层之后另给 ``POOLED_4_LAYERS`` 行：四次检验是同一统计量在独立 rep 上的
    重复，合并后 R 更大、CP 区间更窄，是"整体名义水平是否守住"的汇总证据；
    但它不能替代逐层结果（层间异质性正是要检查的东西）。
    """
    required = {"block", "scenario_id", "level", "n_total", "n_label1", "label_share",
                "srm_p_value", "dgp_cpu_s", "pipeline_cpu_s", "itt_cpu_s",
                "total_cpu_s", "total_wall_s", "alpha", "config_hash", "registered_n"}
    missing = required - set(repetitions.columns)
    if missing:
        raise ValueError(f"逐 rep 表缺少列：{sorted(missing)}")
    if repetitions.empty:
        raise ValueError("逐 rep 表为空，无法汇总")
    level_alpha = float(repetitions["alpha"].iloc[0]) if alpha is None else float(alpha)
    rows: list[dict[str, Any]] = []
    for block in (_BLOCK_TRUE_AA, _BLOCK_NEGATIVE_CONTROL):
        if block not in set(repetitions["block"].unique().tolist()):
            continue
        frame = repetitions.loc[repetitions.block == block].reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"block={block} 为空，无法汇总")
        # 配置哈希按**场景**唯一（每层 `active_scenario` 不同，哈希本就不同）；
        # 同一场景内不一致才是漂移，必须抛。
        hashes_by_scenario: dict[str, str] = {}
        for scenario_id, subset in frame.groupby("scenario_id", sort=True):
            hashes = sorted(set(subset["config_hash"].tolist()))
            if len(hashes) != 1:
                raise AAChainError(f"{block}/{scenario_id} 内配置哈希不唯一：{hashes}")
            hashes_by_scenario[str(scenario_id)] = hashes[0]
        pooled_hash = ("multiple_scenarios(%d)" % len(hashes_by_scenario)
                       if len(hashes_by_scenario) > 1 else next(iter(hashes_by_scenario.values())))
        scenarios = sorted(hashes_by_scenario)
        for scenario_id in scenarios:
            subset = frame.loc[frame.scenario_id == scenario_id].reset_index(drop=True)
            level = str(subset["level"].iloc[0])
            n_registered = int(subset["registered_n"].iloc[0])
            config_hash = hashes_by_scenario[scenario_id]
            for population in _POPULATIONS:
                for metric in AA_METRICS:
                    rows.append(_summarize_metric_cell(
                        subset, block=block, scenario_id=scenario_id, level=level, metric=metric,
                        population=population, alpha=level_alpha, n_registered=n_registered,
                        config_hash=config_hash,
                    ))
            rows.append(_summarize_cost_cell(
                subset, block=block, scenario_id=scenario_id, level=level,
                n_registered=n_registered, config_hash=config_hash,
                note=("" if block == _BLOCK_TRUE_AA else
                      "购买真值0但发券仍产生补贴成本；利润真值<0，本块不是利润零效应AA"),
            ))
        if block == _BLOCK_TRUE_AA and len(scenarios) > 1:
            for population in _POPULATIONS:
                for metric in AA_METRICS:
                    rows.append(_summarize_metric_cell(
                        frame, block=block, scenario_id=_POOLED, level="ALL", metric=metric,
                        population=population, alpha=level_alpha,
                        n_registered=int(frame["registered_n"].iloc[0]), config_hash=pooled_hash,
                        note="四层独立 rep 合并；层间异质性仍以分层行为准",
                    ))
            rows.append(_summarize_cost_cell(
                frame, block=block, scenario_id=_POOLED, level="ALL",
                n_registered=int(frame["registered_n"].iloc[0]), config_hash=pooled_hash,
                note="四层独立 rep 合并",
            ))
    summary = pd.DataFrame(rows)
    return summary.loc[:, list(SUMMARY_COLUMNS)]


# --------------------------------------------------------------------------- #
# 批量运行
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AABundle:
    """一次 AA 批量运行的完整产物（逐 rep 表 + 成本锚 + 汇总表 + manifest）。"""

    repetitions: pd.DataFrame
    anchor: pd.DataFrame
    summary: pd.DataFrame
    manifest: dict[str, Any]
    run_root: Path


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _scenario_cell(protocol: V3Protocol, scenario_id: str) -> AACell:
    """把任意已注册场景包成运行元数据（负对照专用，不要求它是 AA 格）。"""
    cfg = protocol.scenario(scenario_id)
    return AACell(
        scenario_id=scenario_id,
        level=str(cfg.require("active_scenario.level")),
        tier=int(cfg.require("active_scenario.tier")),
        registered_n=int(cfg.require("active_scenario.n")),
        registered_reps=int(cfg.require("active_scenario.R")),
        actual_action=int(cfg.require("design.aa.actual_action")),
        virtual_label_probability=float(cfg.require("design.aa.virtual_label_probability")),
    )


def run_full_chain_aa(
    protocol: V3Protocol | None = None,
    *,
    reps: int = 50,
    n: int = 10_000,
    layers: Sequence[str] | None = None,
    rep_start: int = 0,
    run_root: str | Path | None = None,
    keep_representative: bool = True,
    include_negative_control: bool = True,
    negative_control_reps: int | None = None,
    negative_control_scenario: str = "L0_zero_purchase_effect",
    cost_anchor_reps: int = 1,
    cost_anchor_n: int | None = None,
    max_source_retries: int = 3,
    resume_from: str | Path | None = None,
    flush_path: str | Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> AABundle:
    """对每层各一个无效应 AA 格跑 ``reps`` 次完整链路，并汇总。

    回答方案里的哪个问题："这套五表 + 污染清洗 + SQL + ITT 的流程，在**真的没有
    效应**时会以 alpha 的概率误报吗？每次要花多少 CPU？"

    Parameters
    ----------
    reps, n:
        本次重复次数与人群规模。小规模验证用 ``reps=50, n=10_000``（每组约 5,000 人）；
        正式值由冻结矩阵给定（每层 1000 次、n=200,000），**须用户裁决后另行执行**。
    layers:
        只跑指定层（如 ``["L0"]``），用于冒烟；``None`` 表示四层全跑。
    rep_start:
        起始 rep 序号，便于分段续跑；同一 rep 序号逐位可复现。
    run_root:
        本次尝试的根目录（不得预先存在）；``None`` 时落在
        ``out/v3_phase_d_aa/run_<UTC>_pid<pid>``。
    keep_representative:
        保留每层 ``rep == 0`` 的完整五表/SQL 产物作为工程证据，其余立即删除。
    include_negative_control:
        是否同条件跑 ``L0_zero_purchase_effect`` 负对照（**不是 AA**，见模块文档）。
    cost_anchor_reps, cost_anchor_n:
        在注册规模（默认取格的注册 n）上补测 CPU 的 rep 数。锚点只用于资源外推，
        其 p 值不进入任何假阳性率汇总。
    max_source_retries:
        单个 rep 允许因"并发写盘触发源码绑定门禁"重试的次数（**仅**这一类异常；
        其余异常一律原样抛出）。失败 attempt 的目录保留，不覆盖、不丢弃。
    """
    protocol = load_v3_protocol() if protocol is None else protocol
    if isinstance(reps, bool) or not isinstance(reps, (int, np.integer)) or int(reps) < 1:
        raise ValueError(f"reps 必须是 >= 1 的整数，收到 {reps!r}")
    if isinstance(rep_start, bool) or not isinstance(rep_start, (int, np.integer)) or int(rep_start) < 0:
        raise ValueError(f"rep_start 必须是 >= 0 的整数，收到 {rep_start!r}")
    if (isinstance(max_source_retries, bool) or not isinstance(max_source_retries, (int, np.integer))
            or int(max_source_retries) < 0):
        raise ValueError(f"max_source_retries 必须是 >= 0 的整数，收到 {max_source_retries!r}")
    reps, rep_start, max_source_retries = int(reps), int(rep_start), int(max_source_retries)
    alpha = float(protocol.config.require("design.alpha_two_sided"))
    cells = list(aa_cells(protocol))
    if layers is not None:
        wanted = tuple(dict.fromkeys(str(layer) for layer in layers))
        known = {cell.level for cell in cells}
        unknown = set(wanted) - known
        if unknown:
            raise ValueError(f"未知层：{sorted(unknown)}；已注册 AA 层为 {sorted(known)}")
        cells = [cell for cell in cells if cell.level in wanted]
    if not cells:
        raise ValueError("没有可运行的 AA 格")

    # 负对照先验：必须在跑任何 rep 之前就确认它不是 AA、也没被写成 AA。
    control_cell: AACell | None = None
    control_reps = 0
    if include_negative_control:
        control_reps = reps if negative_control_reps is None else int(negative_control_reps)
        if control_reps < 1:
            raise ValueError("negative_control_reps 必须 >= 1")
        control_cfg = protocol.scenario(negative_control_scenario)
        if bool(control_cfg.require("dgp.virtual_aa_labels")):
            raise AAChainError("负对照格不能是虚拟标签 AA；两者必须分开")
        if negative_control_scenario in {cell.scenario_id for cell in cells}:
            raise AAChainError("负对照格不能同时是 AA 格")
        control_cell = _scenario_cell(protocol, negative_control_scenario)

    if run_root is None:
        run_root = PROJECT_ROOT / "out" / "v3_phase_d_aa" / f"run_{_utc_stamp()}_pid{os.getpid()}"
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=False)
    (run_root / "tmp").mkdir()
    (run_root / "representative").mkdir()
    if flush_path is None:
        flush_path = run_root / "aa_repetitions.csv"
    flush_path = Path(flush_path)
    flush_path.parent.mkdir(parents=True, exist_ok=True)

    def log(message: str) -> None:
        if progress is not None:
            progress(message)

    def attempt_dir(block: str, scenario_id: str, rep: int, size: int, keep: bool) -> Path:
        return run_root / ("representative" if keep else "tmp") / f"{block}_{scenario_id}_rep{rep}_n{size}"

    def run_with_retry(
        cell: AACell, *, rep: int, size: int, block: str, keep: bool,
    ) -> dict[str, Any]:
        """跑一个 rep，只对两类**环境故障**重试，且逐次记录原因。

        1. ``source_changed``：``build_observed_pipeline`` 跑前跑后各哈希一次
           ``src/causal_growth/**/v3*.py``，期间有人写盘就抛
           ``RuntimeError: source files changed during the data run``
           （C 阶段评审过的源码绑定门禁，不能放宽）；
        2. ``windows_file_lock``：观测流水线用 ``.tmp → os.replace`` 原子落盘，
           Windows 上文件被扫描器/索引器短暂占用时抛 ``PermissionError [WinError 5]``
           （常被兜底 ``finish()`` 再包装成 ``ValueError: run is already terminal``）。

        两者都是**环境故障**而非链路/口径异常：同一 ``rep`` 序号重跑得到逐位相同的
        数据，所以重试不改变任何结果；失败的 attempt 目录原样保留（协议要求失败
        重试全部保留）。**其他任何异常一律原样抛出，绝不重试、不吞掉。**
        """
        base = attempt_dir(block, cell.scenario_id, rep, size, keep)
        source_retries = 0
        lock_retries = 0
        for attempt in range(int(max_source_retries) + 1):
            directory = base if attempt == 0 else base.with_name(f"{base.name}_attempt{attempt}")
            try:
                row = run_aa_rep(cell, protocol, rep=rep, n=size, run_dir=directory,
                                 block=block, alpha=alpha, keep_artifacts=keep)
            except Exception as exc:  # noqa: BLE001 - 先分类，不是所有异常都可重试
                lock = find_windows_file_lock(exc)
                source_changed = is_source_changed_error(exc)
                if not (lock is not None or source_changed):
                    raise
                if attempt >= int(max_source_retries):
                    raise
                if source_changed:
                    source_retries += 1
                    log(f"   [retry] 源码在 {cell.scenario_id} rep={rep} 执行期间被改写"
                        f"（并发写盘，门禁按设计拒绝本次 attempt）；"
                        f"重试 {attempt + 1}/{max_source_retries}")
                else:
                    lock_retries += 1
                    log(f"   [retry] {cell.scenario_id} rep={rep} 落盘时文件被短暂占用"
                        f"（WinError {getattr(lock, 'winerror', '?')}）；重试 {attempt + 1}/{max_source_retries}")
                continue
            row["source_retries"] = source_retries
            row["file_lock_retries"] = lock_retries
            row["retry_attempt_dirs"] = "|".join(
                str(base if index == 0 else base.with_name(f"{base.name}_attempt{index}"))
                for index in range(attempt)
            )
            return row
        raise AssertionError("unreachable retry state")

    # ---- 续跑：只接受同一批参数产出的逐 rep 表，参数不一致立即抛 ----
    resumed = pd.DataFrame()
    completed: set[tuple[str, str, int]] = set()
    if resume_from is not None:
        resume_path = Path(resume_from)
        if not resume_path.exists():
            raise FileNotFoundError(f"续跑文件不存在：{resume_path}")
        resumed = pd.read_csv(resume_path, encoding="utf-8-sig")
        missing = {"block", "scenario_id", "rep", "n_total", "alpha", "config_hash"} - set(resumed.columns)
        if missing:
            raise ValueError(f"续跑文件缺少列：{sorted(missing)}")
        if not resumed.empty:
            if set(resumed["block"].unique().tolist()) - {_BLOCK_TRUE_AA, _BLOCK_NEGATIVE_CONTROL}:
                raise ValueError("续跑文件含非 AA/负对照块，拒绝续跑")
            if not resumed["alpha"].eq(alpha).all():
                raise ValueError("续跑文件的 alpha 与当前协议不一致")
            if not resumed["n_total"].eq(n).all():
                raise ValueError("续跑文件的 n 与当前请求不一致")
            completed = set(zip(resumed["block"], resumed["scenario_id"],
                                resumed["rep"].astype(int), strict=True))
            log(f"[resume] 已有 {len(resumed)} 个 rep，跳过重复项")

    def flush(frame: pd.DataFrame) -> None:
        """每完成一个 rep 就落盘：崩溃后不丢已完成结果（协议要求失败重试全部保留）。"""
        frame.to_csv(flush_path, index=False, encoding="utf-8-sig")

    new_rows: list[dict[str, Any]] = []
    for cell in cells:
        for rep in range(rep_start, rep_start + reps):
            if (_BLOCK_TRUE_AA, cell.scenario_id, rep) in completed:
                continue
            keep = keep_representative and rep == 0
            log(f"[aa] {cell.scenario_id} rep={rep} n={n} keep={keep}")
            row = run_with_retry(cell, rep=rep, size=n, block=_BLOCK_TRUE_AA, keep=keep)
            new_rows.append(row)
            flush(pd.concat([resumed, pd.DataFrame(new_rows)], ignore_index=True))
            log(f"[aa]   p(net_profit/full)={row['full_net_profit_p_value']:.4f} cpu={row['total_cpu_s']:.2f}s")

    if control_cell is not None:
        for rep in range(rep_start, rep_start + control_reps):
            if (_BLOCK_NEGATIVE_CONTROL, negative_control_scenario, rep) in completed:
                continue
            keep = keep_representative and rep == 0
            log(f"[nc] {negative_control_scenario} rep={rep} n={n} keep={keep}")
            new_rows.append(run_with_retry(
                control_cell, rep=rep, size=n, block=_BLOCK_NEGATIVE_CONTROL, keep=keep,
            ))
            flush(pd.concat([resumed, pd.DataFrame(new_rows)], ignore_index=True))

    repeated = pd.concat([resumed, pd.DataFrame(new_rows)], ignore_index=True) if new_rows or not resumed.empty \
        else pd.DataFrame()
    if repeated.empty:
        raise ValueError("没有任何 rep 结果（续跑文件为空且本次未执行）")
    flush(repeated)
    repetitions = repeated

    anchor_rows: list[dict[str, Any]] = []
    if cost_anchor_reps > 0:
        if isinstance(cost_anchor_reps, bool) or not isinstance(cost_anchor_reps, (int, np.integer)):
            raise ValueError("cost_anchor_reps 必须是整数")
        for cell in cells:
            anchor_n = int(cell.registered_n if cost_anchor_n is None else cost_anchor_n)
            for rep in range(rep_start, rep_start + int(cost_anchor_reps)):
                log(f"[cost] {cell.scenario_id} rep={rep} n={anchor_n}（只计成本）")
                anchor_rows.append(run_with_retry(
                    cell, rep=rep, size=anchor_n, block=_BLOCK_COST_ANCHOR, keep=False,
                ))
    anchor = pd.DataFrame(anchor_rows)

    summary_parts = [summarize_repetitions(repetitions, alpha=alpha)]
    if not anchor.empty:
        anchor_summary: list[dict[str, Any]] = []
        for cell in cells:
            subset = anchor.loc[anchor.scenario_id == cell.scenario_id].reset_index(drop=True)
            if subset.empty:
                continue
            anchor_summary.append(_summarize_cost_cell(
                subset, block=_BLOCK_COST_ANCHOR, scenario_id=cell.scenario_id, level=cell.level,
                n_registered=int(subset["n_total"].iloc[0]),
                config_hash=str(subset["config_hash"].iloc[0]),
                note="注册规模成本锚；单 rep p 值不进入假阳性率汇总",
            ))
        summary_parts.append(pd.DataFrame(anchor_summary).loc[:, list(SUMMARY_COLUMNS)])
    summary = pd.concat(summary_parts, ignore_index=True)

    manifest = {
        "source_label": _SOURCE_LABEL,
        "purpose": "phase_d_complete_aa_not_formal_completion",
        "formal_repetitions_completed": 0,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_config_hash": protocol.config_hash,
        "protocol_source_hashes": dict(protocol.source_hashes),
        "data_config_hash": load_v3_data_config().hash(64),
        "master_seed": int(protocol.config.require("project.master_seed")),
        "alpha": alpha,
        "reps": reps, "n": n, "rep_start": rep_start,
        "layers": [cell.level for cell in cells],
        "cells": [cell.as_dict() for cell in cells],
        "include_negative_control": include_negative_control,
        "negative_control_scenario": negative_control_scenario if include_negative_control else None,
        "negative_control_reps": control_reps,
        "cost_anchor_reps": int(cost_anchor_reps),
        "cost_anchor_n": cost_anchor_n,
        "max_source_retries": max_source_retries,
        "resume_from": str(resume_from) if resume_from is not None else None,
        "flush_path": str(flush_path),
        "source_retries_total": int(repetitions.get("source_retries", pd.Series(dtype=int)).sum())
        + (int(anchor.get("source_retries", pd.Series(dtype=int)).sum()) if not anchor.empty else 0),
        "file_lock_retries_total": int(repetitions.get("file_lock_retries", pd.Series(dtype=int)).sum())
        + (int(anchor.get("file_lock_retries", pd.Series(dtype=int)).sum()) if not anchor.empty else 0),
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "v3_aa_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "run_root": str(run_root),
    }
    return AABundle(repetitions=repetitions, anchor=anchor, summary=summary,
                    manifest=manifest, run_root=run_root)


# --------------------------------------------------------------------------- #
# 落盘
# --------------------------------------------------------------------------- #
def write_outputs(
    bundle: AABundle, *, summary_csv: str | Path | None = None,
) -> dict[str, str]:
    """把汇总表写入 ``outputs/tables/``，逐 rep 表与 manifest 留在 ``out/``。

    汇总表是报告唯一可引用的数字来源（AGENTS §6）；逐 rep 表用于复核 p 值分布，
    体积大且可由同一命令重生成，因此不放进 ``outputs/tables/``。
    """
    target = (PROJECT_ROOT / "outputs" / "tables" / "v3_phase_D_aa.csv"
              if summary_csv is None else Path(summary_csv))
    target.parent.mkdir(parents=True, exist_ok=True)
    bundle.summary.to_csv(target, index=False, encoding="utf-8-sig")
    paths = {"summary_csv": str(target)}
    if not bundle.repetitions.empty:
        reps_path = bundle.run_root / "aa_repetitions.csv"
        bundle.repetitions.to_csv(reps_path, index=False, encoding="utf-8-sig")
        paths["repetitions_csv"] = str(reps_path)
    if not bundle.anchor.empty:
        anchor_path = bundle.run_root / "aa_cost_anchor.csv"
        bundle.anchor.to_csv(anchor_path, index=False, encoding="utf-8-sig")
        paths["cost_anchor_csv"] = str(anchor_path)
    paths["manifest_json"] = str(bundle.run_root / "aa_manifest.json")
    Path(paths["manifest_json"]).write_text(
        json.dumps({**bundle.manifest, "artifacts": paths}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return paths


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _format_report(summary: pd.DataFrame) -> str:
    """把主指标块打成一张可贴进报告的窄表（仅用于终端提示）。"""
    lines = ["", "block              scenario              metric                pop   R   FPR(p<.05)   CP95                  coverage   p_med"]
    for row in summary.itertuples(index=False):
        if row.row_kind != _ROW_METRIC or row.metric != "net_profit":
            continue
        lines.append(
            f"{row.block:<18} {row.scenario_id:<21} {row.metric:<21} {row.analysis_population:<5} "
            f"{row.R:<3} {row.fpr:<11.3f} [{row.fpr_cp_lower:.3f},{row.fpr_cp_upper:.3f}]"
            f"     {row.coverage:<10.3f} {row.median_p:<.3f}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：默认只跑小规模验证，正式 R 必须显式改参数且由用户裁决。"""
    parser = argparse.ArgumentParser(
        description="Phase D 完整 DGP 链路 AA（不推进正式 R）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--reps", type=int, default=50, help="每层重复次数（正式为 1000，未裁决前不跑）")
    parser.add_argument("--n", type=int, default=10_000, help="每次人群规模（每组约一半）")
    parser.add_argument("--layers", nargs="*", default=None, help="只跑指定层，如 L0 L1")
    parser.add_argument("--rep-start", type=int, default=0, help="起始 rep 序号")
    parser.add_argument("--no-negative-control", action="store_true", help="跳过购买零增量负对照")
    parser.add_argument("--negative-control-reps", type=int, default=None, help="负对照重复次数（默认同 --reps）")
    parser.add_argument("--cost-anchor-reps", type=int, default=1, help="注册规模成本锚 rep 数（0 = 不测）")
    parser.add_argument("--cost-anchor-n", type=int, default=None, help="成本锚人群规模（默认取注册 n）")
    parser.add_argument("--max-source-retries", type=int, default=3,
                        help="单 rep 因并发写盘/文件占用等环境故障时的重试次数（仅这两类异常）")
    parser.add_argument("--resume-from", default=None,
                        help="从已完成批次的逐 rep CSV 续跑（参数不一致会拒绝）")
    parser.add_argument("--run-root", default=None, help="本次尝试目录（必须不存在）")
    parser.add_argument("--summary-csv", default=None, help="汇总表路径（默认 outputs/tables/v3_phase_D_aa.csv）")
    parser.add_argument("--no-keep-representative", action="store_true", help="不保留 rep 0 的完整产物")
    parser.add_argument("--quiet", action="store_true", help="不打印逐 rep 进度")
    args = parser.parse_args(argv)

    bundle = run_full_chain_aa(
        reps=args.reps, n=args.n, layers=args.layers, rep_start=args.rep_start,
        run_root=args.run_root, keep_representative=not args.no_keep_representative,
        include_negative_control=not args.no_negative_control,
        negative_control_reps=args.negative_control_reps,
        cost_anchor_reps=args.cost_anchor_reps, cost_anchor_n=args.cost_anchor_n,
        max_source_retries=args.max_source_retries,
        resume_from=args.resume_from,
        progress=None if args.quiet else print,
    )
    paths = write_outputs(bundle, summary_csv=args.summary_csv)
    print(_format_report(bundle.summary))
    print("")
    print(f"汇总表：{paths['summary_csv']}")
    print(f"逐 rep：{paths.get('repetitions_csv', '-')}")
    print(f"manifest：{paths['manifest_json']}")
    print("说明：本入口只产出工程与统计诊断，formal_repetitions_completed 仍为 0。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
