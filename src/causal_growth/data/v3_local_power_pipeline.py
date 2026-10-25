"""Local-power cells: full-chain generation, ITT per repetition and rejection-rate tables.

Synthetic / known DGP. This module answers the empirical half of
``design.local_power.report`` (``target_effect / achieved_effect / rejection_rate /
R / MC_SE / binomial_interval``) for the 20 registered ``design_power_jobs`` cells.

Pipeline per repetition (no shortcut, no re-implementation)
----------------------------------------------------------
``generate_v3_population(scaled_cfg) → five tables → pollution/cleaning → SQL →
observed analysis table → ITT (Welch t on net_profit) → p value``

The *only* difference from a registered scenario is that the treated arm's
purchase-probability increment is rescaled by the calibrated factor from
:mod:`causal_growth.dgp.v3_local_power`. That factor is inverted so that the
mechanism's **analytic** profit effect equals ``multiplier × design MDE``; the
pipeline therefore runs the frozen DGP code path and only receives an explicit
authorization object (absent it: refusal).

Contract with D.1
-----------------
The per-repetition table carries the four columns
:func:`causal_growth.design.v3_power.summarize_power_cells` requires
(``cell_id`` / ``rep_id`` / ``effect_estimate`` / ``reject``), so
:func:`summarize_local_power` delegates the frozen columns
(``n_reps / achieved_effect / achieved_effect_mc_se / rejection_rate / mc_se /
binomial_ci_low / binomial_ci_high / ci_confidence``) to that function instead of
re-deriving them. Everything this module adds is a *diagnostic* on top:
``achieved_effect_analytic`` (the calibrated effect), ``nominal_power``,
``nominal_power_registered_n``, the feasible range, and the measured CPU cost.

Two "achieved effect" columns, never interchangeable
----------------------------------------------------
* ``achieved_effect_analytic`` — the analytic re-integration of the constructed
  mechanism (yuan/person). Its deviation from ``target_effect`` is the
  construction self-check (relative tolerance 1e-6).
* ``achieved_effect`` — the **empirical** mean of the per-repetition ITT
  estimates (D.1's column). It is the effect the full chain actually delivered,
  with ``achieved_effect_mc_se`` as its Monte Carlo standard error. At small R it
  is noisy; it must not be replaced by the analytic value.

What the rejection rate does and does **not** mean
--------------------------------------------------
``rejection_rate`` = share of repetitions with ``p < alpha`` on ``net_profit``
(yuan per assigned user, R1 denominator). ``mc_se = sqrt(p(1-p)/R)`` and the
Clopper–Pearson interval come from D.1. ``nominal_power`` is the analytic
two-sample power at the *same* per-arm size using the **observed** arm standard
deviations (they include within-order amount/refund variance; the analytic
conditional-mean σ in :class:`causal_growth.dgp.v3_local_power.ProfitEffectCurve`
is only a lower bound and is never used here).

``multiplier = 0`` is **not** an AA cell and **not** the increment-null cell: its
true profit effect is calibrated to exactly 0 by *raising* the purchase
probability enough to offset the coupon's mechanical debit. Its rejection rate is
a size statement for the profit metric at a calibrated zero; the pipeline's
false-positive rate is D.2's virtual-label AA.

Discipline
----------
* Per-repetition truth is used only in the optional audit columns
  (``realized_effect``), never to build the effect.
* Every manifest keeps ``formal_repetitions_completed = 0``.
* Failures are loud: a missing arm, a foreign run_id, a non-finite p value or a
  denominator that differs from the analysis table raises instead of being dropped.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats

from causal_growth.config import Config
from causal_growth.data.v3_pipeline import build_observed_pipeline
from causal_growth.design.v3_power import POWER_CELL_CLASSES, profit_power, split_counts, summarize_power_cells
from causal_growth.dgp.v3_engine import V3Population, generate_v3_population
from causal_growth.dgp.v3_local_power import (
    LOCAL_POWER_EFFECT_CONSTRUCTION,
    LocalPowerCalibration,
    ProfitEffectCurve,
    ReferencePanel,
    build_reference_panel,
    calibrate_local_power_cell,
    configured_multiplier,
    per_purchase_profit,
    profit_effect_curve,
    verify_scaled_mechanism,
)
from causal_growth.estimate.itt import itt_difference_means, itt_difference_proportions
from causal_growth.v3_config import V3Protocol, load_v3_protocol

__all__ = [
    "DESIGN_MDE_TABLE",
    "PROJECT_ROOT",
    "SUMMARY_COLUMNS",
    "LocalPowerBundle",
    "LocalPowerPlan",
    "audit_population_effect",
    "calibrate_plans",
    "design_mde_table",
    "design_sigma_table",
    "environment_fault",
    "feasibility_table",
    "local_power_plan",
    "main",
    "run_local_power_cell",
    "run_local_power_matrix",
    "run_local_power_rep",
    "summarize_local_power",
]

#: 项目根目录（``src/causal_growth/data/v3_local_power_pipeline.py`` 往上三层）。
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

#: 设计先导的 MDE 表（D.1 产物，只提供设计期 MDE 与设计 σ，不提供任何效应）。
DESIGN_MDE_TABLE: Path = PROJECT_ROOT / "outputs" / "tables" / "v3_phase_D_mde.csv"

#: 汇总表的稳定列序；报告里引用的每个数字都落在这里。
#: 前 4 段依次是：格身份 → 设计期量 → 可行性/构造 → 实测功效 → 成本/审计。
SUMMARY_COLUMNS: tuple[str, ...] = (
    "source_label", "cell_id", "base_scenario_id", "level", "multiplier", "power_cell_class",
    "design_mde", "target_effect", "achieved_effect_analytic", "relative_deviation",
    "increment_scale", "mean_purchase_increment",
    "reference_n", "reference_sampling_se", "effect_at_zero_increment", "effect_upper",
    "binding_constraint",
    "design_sigma_treatment", "design_sigma_control",
    "profit_sd_treatment_observed", "profit_sd_control_observed",
    "nominal_power", "nominal_power_registered_n",
    "n_reps", "empirical_n_reps", "n_total", "n_treatment_mean", "n_control_mean",
    "alpha", "ci_confidence",
    "rejection_rate", "rejections", "mc_se", "binomial_ci_low", "binomial_ci_high",
    "measured_minus_nominal",
    "achieved_effect", "achieved_effect_mc_se",
    "mean_p_value", "median_p_value",
    "realized_effect_mean", "realized_effect_se", "realized_effect_reps",
    "selection_bias", "selection_bias_ratio_to_mde", "propensity_min", "propensity_max",
    "estimator_warning",
    "purchase_increment_mean", "purchase_rejection_rate",
    "dgp_cpu_s_mean", "pipeline_cpu_s_mean", "itt_cpu_s_mean", "audit_cpu_s_mean",
    "total_cpu_s_mean", "wall_s_mean", "environment_retries_total",
    "config_hash", "scaled_config_hash", "effect_construction", "interpretation", "note",
)

_SOURCE_LABEL = "合成数据 / 已知 DGP"

#: 逐 rep 表里供给 D.1 :func:`summarize_power_cells` 的四列（顺序即契约）。
POWER_CELL_INPUT_COLUMNS: tuple[str, ...] = ("cell_id", "rep_id", "effect_estimate", "reject")

#: C 阶段源码绑定门禁在 "rep 执行期间有 ``src/**/v3*.py`` 被改写" 时抛出的固定片段。
#: 与 :data:`causal_growth.evaluation.v3_aa.SOURCE_CHANGED_MARKER` 同一消息；多代理并发
#: 写盘时会出现。它是**环境故障**：同一 rep 序号重跑得到逐位相同的数据。
SOURCE_CHANGED_MARKER = "source files changed during the data run"

#: Windows 上"文件被短暂占用"的 winerror：5=拒绝访问，32=共享冲突，33=锁冲突。
_WINDOWS_LOCK_WINERRORS = frozenset({5, 32, 33})


def environment_fault(exc: BaseException) -> str | None:
    """判断异常是否为**唯一**允许重试的两类环境故障；其余一律原样抛出。

    Returns
    -------
    str | None
        ``"source_changed"``（rep 执行期间有源码被改写）、``"windows_file_lock"``
        （落盘 `.tmp → os.replace` 撞上扫描器/索引器的短暂占用），或 ``None``。
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError) and getattr(current, "winerror", None) in _WINDOWS_LOCK_WINERRORS:
            return "windows_file_lock"
        if isinstance(current, RuntimeError) and SOURCE_CHANGED_MARKER in str(current):
            return "source_changed"
        current = current.__context__ or current.__cause__
    return None


# --------------------------------------------------------------------------- #
# 设计期 MDE / σ：只读 D.1 的观测方差表
# --------------------------------------------------------------------------- #
def design_mde_table(path: str | Path | None = None) -> dict[tuple[str, float], float]:
    """读 ``outputs/tables/v3_phase_D_mde.csv`` 的 ``power_cell`` 行，返回设计 MDE。

    Returns
    -------
    dict
        ``{(base_scenario_id, configured_multiplier): mde}``；同一基础场景的 MDE
        在 5 个倍数上必须完全相同（倍数只改目标效应，不改方差来源），否则抛错。
    """
    source = Path(path) if path is not None else DESIGN_MDE_TABLE
    frame = pd.read_csv(source, encoding="utf-8-sig")
    required = {"record_type", "scenario_id", "configured_multiplier", "mde", "target_effect"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"design MDE table lacks columns: {sorted(missing)}")
    cells = frame.loc[frame.record_type == "power_cell"]
    if cells.empty:
        raise ValueError("design MDE table has no power_cell rows")
    table: dict[tuple[str, float], float] = {}
    for scenario_id, subset in cells.groupby("scenario_id", sort=True):
        values = sorted({round(float(value), 12) for value in subset["mde"]})
        if len(values) != 1:
            raise ValueError(f"{scenario_id}: design MDE varies across multipliers: {values}")
        for multiplier in subset["configured_multiplier"]:
            table[(str(scenario_id), float(multiplier))] = values[0]
    return table


def design_sigma_table(path: str | Path | None = None) -> dict[str, tuple[float, float]]:
    """读 D.1 表里设计先导的 ``(sigma_treatment, sigma_control)``，按基础场景索引。

    这两个 σ 是**观测**方差（含单笔订单内部方差），是"名义功效"的合法输入之一；
    不能用 :class:`ProfitEffectCurve` 的条件均值分量代替（它只是下界）。
    """
    source = Path(path) if path is not None else DESIGN_MDE_TABLE
    frame = pd.read_csv(source, encoding="utf-8-sig")
    required = {"record_type", "scenario_id", "sigma_treatment", "sigma_control"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"design MDE table lacks columns: {sorted(missing)}")
    cells = frame.loc[frame.record_type == "power_cell"]
    table: dict[str, tuple[float, float]] = {}
    for scenario_id, subset in cells.groupby("scenario_id", sort=True):
        pairs = {(round(float(t), 9), round(float(c), 9))
                 for t, c in zip(subset["sigma_treatment"], subset["sigma_control"], strict=True)}
        if len(pairs) != 1:
            raise ValueError(f"{scenario_id}: design sigma varies across multipliers: {sorted(pairs)}")
        table[str(scenario_id)] = pairs.pop()
    return table


# --------------------------------------------------------------------------- #
# 逐格执行计划
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LocalPowerPlan:
    """一个功效格的执行计划：注册元数据 + 设计 MDE/设计 σ（不含任何已算效应）。"""

    cell_id: str
    base_scenario_id: str
    level: str
    multiplier: float
    registered_n: int
    registered_reps: int
    design_mde: float
    design_sigma_treatment: float
    design_sigma_control: float

    @property
    def target_effect(self) -> float:
        """目标利润效应（元/人）= 倍数 × 设计 MDE。"""
        return self.multiplier * self.design_mde

    @property
    def power_cell_class(self) -> str:
        """与 D.1 同一判据：低于/等于/高于设计 MDE（``required_multiplier == 倍数``）。"""
        if abs(self.multiplier - 1.0) <= 1e-9:
            return "boundary_zero_margin"
        return "above_design_mde" if self.multiplier > 1.0 else "below_design_mde"

    def as_record(self) -> dict[str, Any]:
        """JSON-safe 计划记录。"""
        return {
            "cell_id": self.cell_id, "base_scenario_id": self.base_scenario_id, "level": self.level,
            "multiplier": self.multiplier, "registered_n": self.registered_n,
            "registered_reps": self.registered_reps, "design_mde": self.design_mde,
            "target_effect": self.target_effect, "power_cell_class": self.power_cell_class,
            "design_sigma_treatment": self.design_sigma_treatment,
            "design_sigma_control": self.design_sigma_control,
        }


def local_power_plan(
    protocol: V3Protocol | None = None,
    *,
    mde_table: Mapping[tuple[str, float], float] | None = None,
    sigma_table: Mapping[str, tuple[float, float]] | None = None,
    cell_ids: Sequence[str] | None = None,
    layers: Sequence[str] | None = None,
) -> tuple[LocalPowerPlan, ...]:
    """从冻结注册表 + D.1 的 MDE/σ 表生成 20 个格的执行计划。

    倍数与基础场景只从 ``design_power_jobs`` 读，设计 MDE 与设计 σ 只从 D.1 的观测
    方差表读；缺任何一格都抛错（不允许用别的层的方差顶替）。
    """
    proto = protocol or load_v3_protocol()
    table = dict(design_mde_table() if mde_table is None else mde_table)
    sigmas = dict(design_sigma_table() if sigma_table is None else sigma_table)
    jobs = proto.config.to_dict()["design_power_jobs"]
    if len(jobs) != 20:
        raise ValueError(f"expected 20 registered design_power_jobs, found {len(jobs)}")
    plans: list[LocalPowerPlan] = []
    for job in jobs:
        cell_id = str(job["id"])
        base = str(job["base_scenario_id"])
        multiplier = float(job["overrides"]["design.local_power.active_mde_multiplier"])
        if (base, multiplier) not in table:
            raise ValueError(f"{cell_id}: design MDE table has no row for base={base}, multiplier={multiplier}")
        if base not in sigmas:
            raise ValueError(f"{cell_id}: design sigma table has no row for base={base}")
        plans.append(LocalPowerPlan(
            cell_id=cell_id, base_scenario_id=base, level=str(job["level"]), multiplier=multiplier,
            registered_n=int(job["n"]), registered_reps=int(job["R"]),
            design_mde=float(table[(base, multiplier)]),
            design_sigma_treatment=float(sigmas[base][0]), design_sigma_control=float(sigmas[base][1]),
        ))
    if cell_ids is not None:
        wanted = {str(value) for value in cell_ids}
        unknown = wanted - {plan.cell_id for plan in plans}
        if unknown:
            raise ValueError(f"unknown local-power cells: {sorted(unknown)}")
        plans = [plan for plan in plans if plan.cell_id in wanted]
    if layers is not None:
        wanted_layers = {str(value) for value in layers}
        unknown_layers = wanted_layers - {plan.level for plan in plans}
        if unknown_layers:
            raise ValueError(f"unknown layers: {sorted(unknown_layers)}")
        plans = [plan for plan in plans if plan.level in wanted_layers]
    if not plans:
        raise ValueError("no local-power cell selected")
    return tuple(plans)


def calibrate_plans(
    plans: Iterable[LocalPowerPlan],
    protocol: V3Protocol | None = None,
    *,
    reference_n: int | None = None,
    relative_tolerance: float | None = None,
    verify_rows: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[LocalPowerCalibration], list[ProfitEffectCurve], list[dict[str, Any]]]:
    """按基础场景逐个构造参考面板并校准选中的格（每层只建一块面板，控制内存）。

    Returns
    -------
    tuple
        ``(calibrations, curves, verifications)``，顺序与 ``plans`` 对齐。
    """
    proto = protocol or load_v3_protocol()
    ordered = list(plans)
    by_base: dict[str, list[LocalPowerPlan]] = {}
    for plan in ordered:
        by_base.setdefault(plan.base_scenario_id, []).append(plan)
    calibrations: dict[str, LocalPowerCalibration] = {}
    curves: dict[str, ProfitEffectCurve] = {}
    verifications: dict[str, dict[str, Any]] = {}
    for base, group in by_base.items():
        base_cfg = proto.scenario(base)
        size = int(base_cfg.require("design.n_total") if reference_n is None else reference_n)
        if progress is not None:
            progress(f"[panel] {base} reference_n={size}")
        panel: ReferencePanel = build_reference_panel(base_cfg, reference_n=size)
        curve = profit_effect_curve(panel)
        curves[base] = curve
        for plan in group:
            cfg = proto.scenario(plan.cell_id)
            calibration = calibrate_local_power_cell(
                panel, cfg, design_mde=plan.design_mde, curve=curve,
                **({} if relative_tolerance is None else {"relative_tolerance": relative_tolerance}),
            )
            verifications[plan.cell_id] = verify_scaled_mechanism(panel, calibration, rows=verify_rows)
            calibrations[plan.cell_id] = calibration
            if progress is not None:
                progress(
                    f"[calibrate] {plan.cell_id} target={calibration.target_effect:.6f} "
                    f"achieved={calibration.achieved_effect:.6f} scale={calibration.increment_scale:.6f}"
                )
        del panel
    return ([calibrations[plan.cell_id] for plan in ordered],
            [curves[plan.base_scenario_id] for plan in ordered],
            [verifications[plan.cell_id] for plan in ordered])


# --------------------------------------------------------------------------- #
# 审计：该 rep 生成人群的真值效应（只用于核对，不参与构造）
# --------------------------------------------------------------------------- #
def audit_population_effect(population: V3Population, cfg: Config) -> dict[str, float]:
    """用**该 rep 的审计真值**重算人群利润效应（元/人），仅作核对。

    条件概率取 ``population.audit_probabilities`` 的 ``p*_conditional``（含 U 的那一对，
    正是购买抽样所用的概率），条件利润取 :func:`per_purchase_profit`。两者相乘再对
    人群求均值，得到该次生成人群的**有限总体**利润 ATE——它不参与效应构造，只在
    审计列里与目标效应对照，用来证明"放缩真的落到了这批数据上"。

    同时给出**未调整 ITT 的估计目标偏差**（``selection_bias``）：随机化的真实倾向
    ``e(x)`` 若不恒等于 0.5，则两臂简单均值差**不是** ATE，而是
    ``Σ e·μ1/Σe − Σ(1−e)·μ0/Σ(1−e)``。当两者之差不可忽略时（L3 就是这种情况），
    实测拒绝率测的是"倾向加权对照"，不能读成 ATE 的功效。该量由同一批数组即时算出，
    不增加任何额外计算。
    """
    probabilities = population.audit_probabilities
    p0 = np.asarray(probabilities.p0_conditional, dtype=float)
    p1 = np.asarray(probabilities.p1_conditional, dtype=float)
    m0, m1 = per_purchase_profit(population.users, cfg)
    if not (len(p0) == len(p1) == len(m0) == len(m1) == len(population.users)):
        raise ValueError("audit arrays are not aligned with the generated population")
    propensity = np.asarray(population.audit_true_propensity, dtype=float)
    if propensity.shape != (len(population.users),):
        raise ValueError("audit true propensity is not aligned with the generated population")
    profit0, profit1 = p0 * m0, p1 * m1
    ate = float(np.mean(profit1 - profit0))
    result = {
        "realized_effect": ate,
        "realized_mean_purchase_control": float(p0.mean()),
        "realized_mean_purchase_treated": float(p1.mean()),
    }
    if np.all(np.isfinite(propensity)) and 0.0 < float(propensity.min()) and float(propensity.max()) < 1.0:
        treated_weight = float(propensity.sum())
        control_weight = float((1.0 - propensity).sum())
        arm_treated = float(np.sum(propensity * profit1) / treated_weight)
        arm_control = float(np.sum((1.0 - propensity) * profit0) / control_weight)
        result.update({
            "design_arm_treated": arm_treated,
            "design_arm_control": arm_control,
            "selection_bias": (arm_treated - arm_control) - ate,
            "propensity_sd": float(propensity.std(ddof=0)),
            "propensity_min": float(propensity.min()),
            "propensity_max": float(propensity.max()),
        })
    else:  # pragma: no cover - 历史人群的 propensity 永远是有限常数或 logit
        result.update({
            "design_arm_treated": float("nan"), "design_arm_control": float("nan"),
            "selection_bias": float("nan"), "propensity_sd": float("nan"),
            "propensity_min": float("nan"), "propensity_max": float("nan"),
        })
    return result


# --------------------------------------------------------------------------- #
# 单 rep
# --------------------------------------------------------------------------- #
class _StageTimer:
    """记录各阶段进程 CPU 秒与墙钟（CPU 秒是排期外推的口径）。"""

    def __init__(self) -> None:
        self.rows: dict[str, float] = {}

    def stage(self, name: str) -> "_Stage":
        return _Stage(self, name)


class _Stage:
    def __init__(self, timer: _StageTimer, name: str) -> None:
        self._timer, self._name = timer, name

    def __enter__(self) -> None:
        self._cpu0, self._wall0 = time.process_time(), time.perf_counter()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._timer.rows[f"{self._name}_cpu_s"] = time.process_time() - self._cpu0
        self._timer.rows[f"{self._name}_wall_s"] = time.perf_counter() - self._wall0
        return False


def _check_observed_chain(
    observations: pd.DataFrame, users: pd.DataFrame, assignments: pd.DataFrame,
    *, run_id: str, n: int, cell_id: str,
) -> None:
    """确认链路没有破坏 R1 分母、标签与人口对齐（违反即刻抛）。"""
    if len(observations) != n:
        raise ValueError(f"{cell_id}: observations has {len(observations)} rows, expected {n} (R1 denominator)")
    if not observations.user_id.is_unique:
        raise ValueError(f"{cell_id}: duplicate user keys in observations")
    if set(observations.user_id) != set(users.user_id):
        raise ValueError(f"{cell_id}: observed users differ from the generated population")
    if observations.run_id.nunique() != 1 or str(observations.run_id.iloc[0]) != run_id:
        raise ValueError(f"{cell_id}: observations carry a foreign run_id")
    labels = assignments.set_index("user_id")["label"].reindex(observations.user_id)
    if labels.isna().any():
        raise ValueError(f"{cell_id}: observed users lack an assigned label")
    if not np.array_equal(labels.to_numpy(), observations.treatment.to_numpy()):
        raise ValueError(f"{cell_id}: observed treatment differs from the assigned label")
    if not observations.mature.astype(bool).all():
        raise ValueError(f"{cell_id}: immature users in the analysis table")
    if set(observations.treatment.unique().tolist()) != {0, 1}:
        raise ValueError(f"{cell_id}: degenerate treatment column")


def run_local_power_rep(
    calibration: LocalPowerCalibration,
    *,
    rep: int,
    n: int,
    run_dir: str | Path,
    alpha: float | None = None,
    keep_artifacts: bool = False,
    audit: bool = False,
) -> dict[str, Any]:
    """跑一次功效格 rep：放缩机制 → 五表 → 污染清洗 → SQL → ITT。

    Parameters
    ----------
    calibration:
        :func:`causal_growth.dgp.v3_local_power.calibrate_local_power_cell` 的结果；
        它同时是放行凭据，且其 ``scaled_config()`` 是本次生成/流水线使用的唯一配置。
    rep:
        DGP 重复序号；同一 ``(master_seed, stream, rep)`` 逐位可复现。
    n:
        本次人群规模（工程规模可小于注册 n；正式运行取注册 n）。
    run_dir:
        本次尝试的**新**目录（不得预先存在）。
    alpha:
        显著性水平；``None`` 取 ``design.alpha_two_sided``。
    keep_artifacts:
        是否保留五表产物（失败时无论取值都保留，作为失败证据）。
    audit:
        是否用该 rep 的审计真值重算人群效应（只写审计列，不参与构造）。
    """
    if isinstance(rep, bool) or not isinstance(rep, (int, np.integer)) or int(rep) < 0:
        raise ValueError(f"rep must be a non-negative integer, got {rep!r}")
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or int(n) < 4:
        raise ValueError(f"n must be an integer >= 4, got {n!r}")
    rep, n = int(rep), int(n)
    cfg = calibration.scaled_config()
    level_alpha = float(cfg.require("design.alpha_two_sided")) if alpha is None else float(alpha)
    if not 0.0 < level_alpha < 1.0:
        raise ValueError(f"alpha must lie in (0,1), got {level_alpha}")
    run_id = f"lp:{calibration.cell_id}:rep{rep}:n{n}"
    timer = _StageTimer()
    succeeded = False
    row: dict[str, Any] = {
        "source_label": _SOURCE_LABEL, "cell_id": calibration.cell_id, "rep_id": rep,
        "base_scenario_id": calibration.base_scenario_id, "level": calibration.level,
        "multiplier": calibration.multiplier, "run_id": run_id,
        "n_requested": n, "alpha": level_alpha,
        "target_effect": calibration.target_effect,
        "achieved_effect_analytic": calibration.achieved_effect,
        "increment_scale": calibration.increment_scale,
        "config_hash": cfg.hash(64), "scaled_config_hash": calibration.scaled_config_hash,
        "effect_construction": LOCAL_POWER_EFFECT_CONSTRUCTION,
    }
    try:
        with timer.stage("dgp"):
            population = generate_v3_population(cfg, rep_id=rep, n=n)
        users, assignments, orders = population.observation_bundle()
        stream_prefix = str(population.metadata["stream_prefix"])
        row.update({"n_total": int(len(users)), "n_orders": int(len(orders)),
                    "stream_prefix": stream_prefix})
        with timer.stage("pipeline"):
            result = build_observed_pipeline(
                users, assignments, orders, cfg, directory=Path(run_dir), run_id=run_id,
                rep_id=rep, stream_prefix=stream_prefix, persist_database=False,
                local_power_authorization=calibration,
            )
        observations = result.dataset.observations
        _check_observed_chain(observations, users, assignments, run_id=run_id, n=n,
                              cell_id=calibration.cell_id)
        n_treated = int(observations.treatment.sum())
        row.update({"n_treatment": n_treated, "n_control": int(len(observations) - n_treated)})
        row["srm_p_value"] = float(stats.binomtest(
            n_treated, len(observations), float(cfg.require("design.treatment_probability")),
        ).pvalue)
        with timer.stage("itt"):
            profit = itt_difference_means(observations, "net_profit", treatment_col="treatment",
                                          alpha=level_alpha, metric="net_profit")
            purchase = itt_difference_proportions(observations, "paid_purchase_7d",
                                                  treatment_col="treatment", alpha=level_alpha,
                                                  metric="paid_purchase_7d")
            if profit.n_treated + profit.n_control != len(observations):
                raise ValueError(f"{calibration.cell_id}: ITT denominator differs from the analysis table")
        profit_values = observations["net_profit"].to_numpy(dtype=float)
        treated_flag = observations["treatment"].to_numpy() == 1
        if not np.all(np.isfinite(profit_values)):
            raise ValueError(f"{calibration.cell_id}: non-finite net_profit in the analysis table")
        row.update({
            "itt_diff": profit.diff, "itt_se": profit.se, "itt_ci_lower": profit.ci_lower,
            "itt_ci_upper": profit.ci_upper, "itt_p_value": profit.p_value,
            "purchase_diff": purchase.diff, "purchase_p_value": purchase.p_value,
            "mean_profit_treated": profit.mean_treated, "mean_profit_control": profit.mean_control,
            "mean_purchase_treated": purchase.mean_treated, "mean_purchase_control": purchase.mean_control,
            "sd_profit_treated": float(np.std(profit_values[treated_flag], ddof=1)),
            "sd_profit_control": float(np.std(profit_values[~treated_flag], ddof=1)),
            "reject": bool(profit.p_value < level_alpha),
            "effect_estimate": float(profit.diff),
        })
        if audit:
            with timer.stage("audit"):
                row.update(audit_population_effect(population, cfg))
        succeeded = True
    finally:
        if succeeded and not keep_artifacts:
            shutil.rmtree(Path(run_dir), ignore_errors=True)
    total_cpu = 0.0
    total_wall = 0.0
    for name in ("dgp", "pipeline", "itt", "audit"):
        row[f"{name}_cpu_s"] = timer.rows.get(f"{name}_cpu_s", 0.0)
        total_cpu += row[f"{name}_cpu_s"]
        total_wall += timer.rows.get(f"{name}_wall_s", 0.0)
    row["total_cpu_s"] = total_cpu
    row["total_wall_s"] = total_wall
    return row


def run_local_power_cell(
    calibration: LocalPowerCalibration,
    *,
    reps: int,
    n: int,
    run_root: str | Path,
    alpha: float | None = None,
    rep_start: int = 0,
    keep_representative: bool = True,
    audit_rep0: bool = True,
    audit_all: bool = False,
    max_environment_retries: int = 3,
    progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """跑一个功效格的 ``reps`` 次重复，返回逐 rep 表（失败即抛，不吞）。

    ``max_environment_retries`` 只覆盖 :func:`environment_fault` 认定的两类环境故障
    （源码在 rep 执行期间被并发改写、Windows 落盘短暂占用）；它们不改变数据，所以
    重试不改变结果，但**每次 attempt 的目录都保留**（失败证据）。其它任何异常一律
    原样抛出，不重试、不吞掉。
    """
    if isinstance(reps, bool) or not isinstance(reps, (int, np.integer)) or int(reps) < 1:
        raise ValueError(f"reps must be an integer >= 1, got {reps!r}")
    if (isinstance(max_environment_retries, bool) or not isinstance(max_environment_retries, (int, np.integer))
            or int(max_environment_retries) < 0):
        raise ValueError(f"max_environment_retries must be an integer >= 0, got {max_environment_retries!r}")
    retries = int(max_environment_retries)
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "tmp"
    tmp.mkdir(exist_ok=True)
    keep_dir = root / "representative"
    keep_dir.mkdir(exist_ok=True)
    rows: list[dict[str, Any]] = []
    for rep in range(int(rep_start), int(rep_start) + int(reps)):
        keep = keep_representative and rep == 0
        base = (keep_dir if keep else tmp) / f"{calibration.cell_id}_rep{rep}_n{n}"
        row: dict[str, Any] | None = None
        for attempt in range(retries + 1):
            directory = base if attempt == 0 else base.with_name(f"{base.name}_attempt{attempt}")
            if directory.exists():
                raise FileExistsError(f"refusing to overwrite an existing attempt directory: {directory}")
            if progress is not None:
                progress(f"[rep] {calibration.cell_id} rep={rep} n={n} attempt={attempt}")
            try:
                row = run_local_power_rep(
                    calibration, rep=rep, n=n, run_dir=directory, alpha=alpha,
                    keep_artifacts=keep, audit=bool(audit_all or (audit_rep0 and rep == 0)),
                )
            except Exception as exc:  # noqa: BLE001 - 先分类，不是所有异常都可重试
                fault = environment_fault(exc)
                if fault is None or attempt >= retries:
                    raise
                if progress is not None:
                    progress(f"[rep]   retry after environment fault ({fault}); "
                             f"attempt {attempt + 1}/{retries} uses a new directory")
                continue
            row["environment_retries"] = attempt
            row["environment_faults"] = "|".join(
                "retried" for _ in range(attempt)
            )
            if progress is not None:
                progress(f"[rep]   p={row['itt_p_value']:.4f} effect={row['itt_diff']:+.4f} "
                         f"cpu={row['total_cpu_s']:.2f}s")
            break
        if row is None:  # pragma: no cover - 循环内要么赋值要么抛出
            raise AssertionError("unreachable local-power repetition state")
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 汇总：拒绝率 + 二项区间 + MC_SE（冻结列交给 D.1 的入口）
# --------------------------------------------------------------------------- #
def summarize_local_power(
    repetitions: pd.DataFrame,
    calibrations: Sequence[LocalPowerCalibration],
    *,
    alpha: float,
    confidence: float = 0.95,
    registered_n: Mapping[str, int] | None = None,
    design_sigma: Mapping[str, tuple[float, float]] | None = None,
) -> pd.DataFrame:
    """把一个格的 R 次重复汇总成一行；冻结统计列由 D.1 的 ``summarize_power_cells`` 产出。

    ``repetitions`` 必须含 :data:`POWER_CELL_INPUT_COLUMNS`；每格 ``R >= 2``
    （否则 ``MC_SE`` 无定义，D.1 会抛）。``nominal_power`` 用**本次运行的实测臂内
    样本 σ** 在本次每臂人数上解析计算；``nominal_power_registered_n`` 用 D.1 设计
    先导的 σ 在注册 n 上计算，即设计期名义功效。
    """
    if repetitions.empty:
        raise ValueError("no repetitions to summarize")
    missing = set(POWER_CELL_INPUT_COLUMNS) - set(repetitions.columns)
    if missing:
        raise ValueError(f"repetition table lacks the D.1 contract columns: {sorted(missing)}")
    canonical = summarize_power_cells(
        repetitions.loc[:, list(POWER_CELL_INPUT_COLUMNS)], confidence=confidence,
    ).set_index("cell_id")
    registered = dict(registered_n or {})
    sigmas = dict(design_sigma or {})
    rows: list[dict[str, Any]] = []
    for calibration in calibrations:
        frame = repetitions.loc[repetitions.cell_id == calibration.cell_id].reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"no repetitions recorded for {calibration.cell_id}")
        if calibration.cell_id not in canonical.index:
            raise ValueError(f"{calibration.cell_id}: D.1 summary is missing this cell")
        block = canonical.loc[calibration.cell_id]
        p_values = frame["itt_p_value"].to_numpy(dtype=float)
        if not np.all(np.isfinite(p_values)):
            raise ValueError(f"{calibration.cell_id}: non-finite p values in the repetition table")
        n_treatment = int(round(float(frame["n_treatment"].mean())))
        n_control = int(round(float(frame["n_control"].mean())))
        sd_treatment = float(frame["sd_profit_treated"].mean())
        sd_control = float(frame["sd_profit_control"].mean())
        nominal = profit_power(
            calibration.target_effect, sd_treatment, sd_control,
            max(n_treatment, 2), max(n_control, 2), alpha=alpha,
        )
        pair = sigmas.get(calibration.cell_id)
        registered_size = registered.get(calibration.cell_id)
        if pair is None or registered_size is None:
            nominal_registered = float("nan")
            design_treatment = design_control = float("nan")
        else:
            design_treatment, design_control = float(pair[0]), float(pair[1])
            counts = split_counts(int(registered_size), (0.5, 0.5))
            nominal_registered = profit_power(
                calibration.target_effect, design_treatment, design_control,
                counts[0], counts[1], alpha=alpha,
            )
        realized = frame.get("realized_effect")
        realized_reps = 0 if realized is None else int(realized.notna().sum())
        realized_mean = float(realized.mean()) if realized_reps else float("nan")
        realized_se = (float(realized.std(ddof=1) / math.sqrt(realized_reps)) if realized_reps > 1
                       else float("nan"))
        bias_series = frame.get("selection_bias")
        bias_reps = 0 if bias_series is None else int(bias_series.notna().sum())
        selection_bias = float(bias_series.mean()) if bias_reps else float("nan")
        bias_ratio = (abs(selection_bias) / calibration.design_mde
                      if bias_reps and math.isfinite(selection_bias) else float("nan"))
        propensity_low = (float(frame["propensity_min"].min()) if bias_reps else float("nan"))
        propensity_high = (float(frame["propensity_max"].max()) if bias_reps else float("nan"))
        estimator_warning = _estimator_warning(selection_bias, bias_reps, calibration.design_mde)
        curve = calibration.curve
        rows.append({
            "source_label": _SOURCE_LABEL,
            "cell_id": calibration.cell_id,
            "base_scenario_id": calibration.base_scenario_id,
            "level": calibration.level,
            "multiplier": calibration.multiplier,
            "power_cell_class": _power_cell_class(calibration.multiplier),
            "design_mde": calibration.design_mde,
            "target_effect": calibration.target_effect,
            "achieved_effect_analytic": calibration.achieved_effect,
            "relative_deviation": calibration.relative_deviation,
            "increment_scale": calibration.increment_scale,
            "mean_purchase_increment": calibration.mean_purchase_increment,
            "reference_n": curve.reference_n,
            "reference_sampling_se": curve.reference_sampling_se,
            "effect_at_zero_increment": curve.effect_at_zero_increment,
            "effect_upper": curve.effect_upper,
            "binding_constraint": curve.binding_constraint,
            "design_sigma_treatment": design_treatment,
            "design_sigma_control": design_control,
            "profit_sd_treatment_observed": sd_treatment,
            "profit_sd_control_observed": sd_control,
            "nominal_power": nominal,
            "nominal_power_registered_n": nominal_registered,
            "n_reps": int(block["n_reps"]),
            "empirical_n_reps": int(block["n_reps"]),
            "n_total": int(round(float(frame["n_total"].mean()))),
            "n_treatment_mean": n_treatment,
            "n_control_mean": n_control,
            "alpha": float(alpha),
            "ci_confidence": float(block["ci_confidence"]),
            "rejection_rate": float(block["rejection_rate"]),
            "rejections": int(np.count_nonzero(p_values < alpha)),
            "mc_se": float(block["mc_se"]),
            "binomial_ci_low": float(block["binomial_ci_low"]),
            "binomial_ci_high": float(block["binomial_ci_high"]),
            "measured_minus_nominal": float(block["rejection_rate"]) - nominal,
            "achieved_effect": float(block["achieved_effect"]),
            "achieved_effect_mc_se": float(block["achieved_effect_mc_se"]),
            "mean_p_value": float(p_values.mean()),
            "median_p_value": float(np.median(p_values)),
            "realized_effect_mean": realized_mean,
            "realized_effect_se": realized_se,
            "realized_effect_reps": realized_reps,
            "selection_bias": selection_bias,
            "selection_bias_ratio_to_mde": bias_ratio,
            "propensity_min": propensity_low,
            "propensity_max": propensity_high,
            "estimator_warning": estimator_warning,
            "purchase_increment_mean": float(frame["purchase_diff"].mean()),
            "purchase_rejection_rate": float(
                np.count_nonzero(frame["purchase_p_value"].to_numpy() < alpha) / len(frame)
            ),
            "dgp_cpu_s_mean": float(frame["dgp_cpu_s"].mean()),
            "pipeline_cpu_s_mean": float(frame["pipeline_cpu_s"].mean()),
            "itt_cpu_s_mean": float(frame["itt_cpu_s"].mean()),
            "audit_cpu_s_mean": float(frame["audit_cpu_s"].mean()),
            "total_cpu_s_mean": float(frame["total_cpu_s"].mean()),
            "wall_s_mean": float(frame["total_wall_s"].mean()),
            "environment_retries_total": (int(frame["environment_retries"].sum())
                                          if "environment_retries" in frame.columns else 0),
            "config_hash": str(frame["config_hash"].iloc[0]),
            "scaled_config_hash": calibration.scaled_config_hash,
            "effect_construction": LOCAL_POWER_EFFECT_CONSTRUCTION,
            "interpretation": _interpretation(calibration),
            "note": _note(calibration),
        })
    return pd.DataFrame(rows).loc[:, list(SUMMARY_COLUMNS)]


def _estimator_warning(selection_bias: float, bias_reps: int, design_mde: float) -> str:
    """未调整 ITT 的估计目标是否被真实倾向的选择效应污染（空串 = 未发现）。

    判据：设计层面的选择偏差达到设计 MDE 的量级，就说明实测拒绝率测的不是 ATE。
    L3 的真实倾向 ``e(x)`` 在 0.16–0.96 之间、与利润相关 ~0.65，偏差约 +1.4 元/人
    （≈10 倍设计 MDE），因此 L3 的格只能用 IPW/DR 或改用倾向加权估计目标。
    """
    if not bias_reps or not math.isfinite(selection_bias):
        return ""
    if abs(selection_bias) < max(float(design_mde), 1e-12):
        return ""
    return ("unadjusted_itt_estimand_is_propensity_weighted_contrast; "
            f"design selection bias {selection_bias:+.4f} yuan/person "
            f"({abs(selection_bias) / max(float(design_mde), 1e-12):.1f}x design MDE); "
            "use IPW/DR or restrict the estimand before reading this rejection rate as ATE power")


def _power_cell_class(multiplier: float) -> str:
    """与 D.1 同判据的格类别（``required_multiplier`` 恒等于配置倍数）。"""
    if abs(float(multiplier) - 1.0) <= 1e-9:
        return POWER_CELL_CLASSES[1]
    return POWER_CELL_CLASSES[2] if float(multiplier) > 1.0 else POWER_CELL_CLASSES[0]


def _interpretation(calibration: LocalPowerCalibration) -> str:
    """该格的拒绝率该被读成什么（防止把 size 读成功效、把校准零效应读成 AA）。"""
    if calibration.multiplier == 0:
        return "size_at_calibrated_zero_profit_effect_not_aa_not_increment_null"
    if abs(calibration.multiplier - 1.0) <= 1e-9:
        return "power_at_design_mde_boundary_zero_margin"
    return "power_at_constructed_profit_effect"


def _note(calibration: LocalPowerCalibration) -> str:
    """每行都要能自我解释：增量是放缩放出来的，不是注册增量。"""
    if calibration.multiplier == 0:
        base = calibration.curve.effect_at_zero_increment
        return (
            "zero profit effect needs a positive purchase increment "
            f"(scale {calibration.increment_scale:.4f}); the increment-null cell has true "
            f"profit ATE {base:.4f} yuan/person and is a negative control, not a size check"
        )
    return (
        "target = multiplier x design MDE; achieved_effect_analytic re-integrated analytically; "
        f"increment scale {calibration.increment_scale:.4f} of the registered headroom"
    )


# --------------------------------------------------------------------------- #
# 可行域诊断表
# --------------------------------------------------------------------------- #
def feasibility_table(calibrations: Sequence[LocalPowerCalibration]) -> pd.DataFrame:
    """20 格的可行域诊断：目标效应相对该机制上界还剩多少余量。

    ``scale_margin_to_upper`` = ``scale_upper / increment_scale``（1 表示刚好顶到上界）；
    ``reachable`` 恒为 True——不可达的格在校准阶段就抛
    :class:`~causal_growth.dgp.v3_local_power.LocalPowerInfeasible`，不会进这张表。
    """
    rows: list[dict[str, Any]] = []
    for calibration in calibrations:
        curve = calibration.curve
        rows.append({
            "cell_id": calibration.cell_id,
            "base_scenario_id": calibration.base_scenario_id,
            "level": calibration.level,
            "multiplier": calibration.multiplier,
            "design_mde": calibration.design_mde,
            "target_effect": calibration.target_effect,
            "achieved_effect_analytic": calibration.achieved_effect,
            "relative_deviation": calibration.relative_deviation,
            "effect_at_zero_increment": curve.effect_at_zero_increment,
            "effect_at_registered_scale": curve.effect_at_registered_scale,
            "effect_upper": curve.effect_upper,
            "increment_scale": calibration.increment_scale,
            "scale_bound_legal": curve.scale_bound_legal,
            "scale_bound_registered": curve.scale_bound_registered,
            "scale_upper": curve.scale_upper,
            "binding_constraint": curve.binding_constraint,
            "scale_margin_to_upper": curve.scale_upper / calibration.increment_scale,
            "reachable": True,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 批量入口
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LocalPowerBundle:
    """一次功效格批量运行的产物（逐 rep 表 / 汇总 / 可行域 / 校准记录 / manifest）。"""

    repetitions: pd.DataFrame
    summary: pd.DataFrame
    feasibility: pd.DataFrame
    calibrations: list[LocalPowerCalibration]
    manifest: dict[str, Any]
    run_root: Path


def run_local_power_matrix(
    protocol: V3Protocol | None = None,
    *,
    plans: Sequence[LocalPowerPlan] | None = None,
    reps: int | None = None,
    n: int | None = None,
    reference_n: int | None = None,
    alpha: float | None = None,
    run_root: str | Path | None = None,
    keep_representative: bool = True,
    audit_rep0: bool = True,
    flush_path: str | Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> LocalPowerBundle:
    """跑选中的功效格（默认 20 格）并汇总；``reps``/``n`` 缺省取注册值。

    正式规模是 ``reps=100, n=200000``（20 格 = 2000 rep）。本函数不设上限，但**谁调用
    谁负责排期**：它只报告实测 CPU，不改变任何正式计数器。
    """
    proto = protocol or load_v3_protocol()
    chosen = list(plans) if plans is not None else list(local_power_plan(proto))
    level_alpha = float(proto.config.require("design.alpha_two_sided")) if alpha is None else float(alpha)
    if run_root is None:
        run_root = PROJECT_ROOT / "out" / "v3_phase_d_local_power" / time.strftime("run_%Y%m%dT%H%M%S")
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=False)
    flush = Path(flush_path) if flush_path is not None else root / "local_power_repetitions.csv"

    def log(message: str) -> None:
        if progress is not None:
            progress(message)

    calibrations, curves, verifications = calibrate_plans(
        chosen, proto, reference_n=reference_n, progress=progress,
    )
    frames: list[pd.DataFrame] = []
    for plan, calibration in zip(chosen, calibrations):
        size = int(plan.registered_n if n is None else n)
        count = int(plan.registered_reps if reps is None else reps)
        log(f"[cell] {plan.cell_id} reps={count} n={size} target={plan.target_effect:.6f}")
        frames.append(run_local_power_cell(
            calibration, reps=count, n=size, run_root=root, alpha=level_alpha,
            keep_representative=keep_representative, audit_rep0=audit_rep0, progress=progress,
        ))
        pd.concat(frames, ignore_index=True).to_csv(flush, index=False, encoding="utf-8-sig")
    repetitions = pd.concat(frames, ignore_index=True)
    summary = summarize_local_power(
        repetitions, calibrations, alpha=level_alpha,
        registered_n={plan.cell_id: plan.registered_n for plan in chosen},
        design_sigma={plan.cell_id: (plan.design_sigma_treatment, plan.design_sigma_control)
                      for plan in chosen},
    )
    feasibility = feasibility_table(calibrations)
    summary.to_csv(root / "local_power_summary.csv", index=False, encoding="utf-8-sig")
    feasibility.to_csv(root / "local_power_feasibility.csv", index=False, encoding="utf-8-sig")
    manifest = {
        "source_label": _SOURCE_LABEL,
        "record_type": "local_power_rejection_rates",
        "formal_repetitions_completed": 0,
        "effect_construction": LOCAL_POWER_EFFECT_CONSTRUCTION,
        "protocol_config_hash": proto.config_hash,
        "alpha": level_alpha,
        "repetition_contract": list(POWER_CELL_INPUT_COLUMNS),
        "cells": [
            {**plan.as_record(), "calibration": calibration.as_record(),
             "verification": verification}
            for plan, calibration, verification in zip(chosen, calibrations, verifications)
        ],
        "curves": [curve.as_record() for curve in {c.base_scenario_id: c for c in curves}.values()],
        "n_note": "n is this run's population size; the registered n is recorded per cell",
    }
    (root / "local_power_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    return LocalPowerBundle(repetitions, summary, feasibility, calibrations, manifest, root)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local-power cells end to end (small n by default; formal schedule needs approval).",
    )
    parser.add_argument("--reps", type=int, default=3, help="repetitions per cell (default 3)")
    parser.add_argument("--n", type=int, default=2000, help="population size per rep (default 2000)")
    parser.add_argument("--reference-n", type=int, default=None,
                        help="reference panel size for the analytic effect (default: design n_total)")
    parser.add_argument("--cells", type=str, default=None, help="comma-separated cell ids")
    parser.add_argument("--layers", type=str, default=None, help="comma-separated layers, e.g. L1,L2")
    parser.add_argument("--alpha", type=float, default=None)
    parser.add_argument("--calibrate-only", action="store_true",
                        help="only build the analytic curves / feasibility diagnosis (no data runs)")
    parser.add_argument("--out", type=str, default=None, help="run root (must not exist)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：小规模跑通并打印汇总（默认不触碰 20 万 × 100 的正式排期）。

    ``--calibrate-only`` 只做解析部分：20 格的 τ0/Δ/可行域/achieved-vs-target 诊断，
    不生成任何数据、不产生任何 rep——这是 §2 那张可行域表的可复现入口。
    """
    args = _parse_args(argv)
    protocol = load_v3_protocol()
    plans = local_power_plan(
        protocol,
        cell_ids=None if args.cells is None else [item.strip() for item in args.cells.split(",") if item],
        layers=None if args.layers is None else [item.strip() for item in args.layers.split(",") if item],
    )
    if args.calibrate_only:
        root = (Path(args.out) if args.out is not None else
                PROJECT_ROOT / "out" / "v3_phase_d_local_power" / time.strftime("calibrate_%Y%m%dT%H%M%S"))
        root.mkdir(parents=True, exist_ok=False)
        calibrations, curves, verifications = calibrate_plans(
            plans, protocol, reference_n=args.reference_n, progress=print,
        )
        feasibility = feasibility_table(calibrations)
        checks = pd.DataFrame([
            {"cell_id": plan.cell_id, "target_effect": calibration.target_effect,
             "achieved_effect_analytic": calibration.achieved_effect,
             "absolute_deviation": calibration.absolute_deviation,
             "relative_deviation": calibration.relative_deviation,
             "dgp_path_relative_deviation": verification["relative_deviation"],
             "p0_max_abs_change": verification["p0_max_abs_change"],
             "consistent": calibration.consistent}
            for plan, calibration, verification in zip(plans, calibrations, verifications)
        ])
        feasibility.to_csv(root / "local_power_feasibility.csv", index=False, encoding="utf-8-sig")
        checks.to_csv(root / "local_power_consistency_checks.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame([curve.as_record() for curve in {c.base_scenario_id: c for c in curves}.values()])\
            .to_csv(root / "local_power_curves.csv", index=False, encoding="utf-8-sig")
        print(feasibility.loc[:, ["cell_id", "multiplier", "target_effect", "achieved_effect_analytic",
                                  "relative_deviation", "effect_at_zero_increment", "effect_upper",
                                  "increment_scale", "scale_upper", "binding_constraint"]]
              .to_string(index=False))
        print(checks.loc[:, ["cell_id", "relative_deviation", "dgp_path_relative_deviation",
                             "p0_max_abs_change", "consistent"]].to_string(index=False))
        print(f"artifacts: {root}")
        return 0
    bundle = run_local_power_matrix(
        protocol, plans=plans, reps=args.reps, n=args.n, reference_n=args.reference_n,
        alpha=args.alpha, run_root=args.out, progress=print,
    )
    columns = ["cell_id", "multiplier", "target_effect", "achieved_effect_analytic",
               "nominal_power", "nominal_power_registered_n", "rejection_rate",
               "binomial_ci_low", "binomial_ci_high", "achieved_effect", "estimator_warning"]
    print(bundle.summary.loc[:, columns].to_string(index=False))
    print(f"artifacts: {bundle.run_root}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
