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
authorization object (default otherwise: refusal).

What is reported, and what it does **not** mean
-----------------------------------------------
* ``rejection_rate`` = share of repetitions with ``p < alpha`` on the primary
  metric ``net_profit`` (yuan per assigned user, R1 denominator). Its binomial
  interval is Clopper–Pearson (the same implementation as the D.2 AA table), and
  ``MC_SE = sqrt(rate(1-rate)/R)`` is the Monte Carlo standard error of the rate.
* ``nominal_power`` is the **analytic** two-sample power at the same per-arm
  sample size using the calibrated arm standard deviations. Nominal ≠ measured is
  expected: the analytic formula is a normal approximation to a zero-inflated,
  skewed profit distribution, and it ignores the between-repetition variation of
  the realized population ATE (the reference panel's own sampling error).
* ``multiplier = 0`` is **not** an AA cell. Its true profit effect is calibrated
  to exactly 0 by *raising* the purchase probability enough to offset the coupon's
  mechanical debit, so its rejection rate is a size statement **for the profit
  metric at a calibrated zero**, not the false-positive rate of the analysis
  pipeline. The pipeline's false-positive rate is D.2's job (virtual-label AA).
* ``effect_at_zero_increment`` (τ0) is the profit ATE of the increment-null cell;
  it is reported so nobody can mistake "no purchase increment" for "no effect".

Discipline
----------
* Per-repetition truth is used **only** in the optional audit column
  (``realized_effect``), never to build the effect.
* Every repetition's manifest keeps ``formal_repetitions_completed = 0``; this
  module does not move any formal counter.
* Failures are loud: an ITT with fewer than two users per arm, a missing treatment
  column, or a non-finite p value raises instead of being dropped.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats

from causal_growth.config import Config
from causal_growth.data.v3_pipeline import build_observed_pipeline
from causal_growth.design.v3_power import profit_power, split_counts
from causal_growth.dgp.v3_engine import V3Population, generate_v3_population
from causal_growth.dgp.v3_local_power import (
    LOCAL_POWER_EFFECT_CONSTRUCTION,
    LocalPowerCalibration,
    LocalPowerInfeasible,
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
    "PROJECT_ROOT",
    "SUMMARY_COLUMNS",
    "LocalPowerBundle",
    "LocalPowerPlan",
    "audit_population_effect",
    "design_mde_table",
    "design_sigma_table",
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

#: 设计先导的 MDE 表（D.1 产物，只提供设计期 MDE，不提供任何效应）。
DESIGN_MDE_TABLE: Path = PROJECT_ROOT / "outputs" / "tables" / "v3_phase_D_mde.csv"

#: 汇总表的稳定列序；报告里引用的每个数字都落在这里。
SUMMARY_COLUMNS: tuple[str, ...] = (
    "source_label", "cell_id", "base_scenario_id", "level", "multiplier", "R", "n_total",
    "n_treatment_mean", "n_control_mean", "alpha", "design_mde", "target_effect",
    "achieved_effect", "relative_deviation", "increment_scale", "mean_purchase_increment",
    "reference_n", "reference_sampling_se", "effect_at_zero_increment", "effect_floor",
    "effect_upper", "binding_constraint",
    "profit_sd_treatment_observed", "profit_sd_control_observed",
    "design_sigma_treatment", "design_sigma_control",
    "nominal_power", "nominal_power_registered_n", "rejection_rate", "rejection_mc_se",
    "rejection_cp_lower", "rejection_cp_upper", "rejections", "measured_minus_nominal",
    "mean_itt", "itt_mean_se", "mean_p_value", "median_p_value",
    "realized_effect_mean", "realized_effect_se", "realized_effect_reps",
    "purchase_increment_mean", "purchase_rejection_rate",
    "dgp_cpu_s_mean", "pipeline_cpu_s_mean", "itt_cpu_s_mean", "audit_cpu_s_mean",
    "total_cpu_s_mean", "wall_s_mean",
    "config_hash", "scaled_config_hash", "effect_construction", "interpretation", "note",
)

_SOURCE_LABEL = "合成数据 / 已知 DGP"


# --------------------------------------------------------------------------- #
# 设计期 MDE：只读 D.1 的观测方差表
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

    这两个 σ 是**观测**方差（含单笔订单内部方差），是"名义功效"的唯一合法输入；
    不能用 :class:`ProfitEffectCurve` 的条件均值分量代替（它是下界）。
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


def local_power_plan(
    protocol: V3Protocol | None = None,
    *,
    mde_table: Mapping[tuple[str, float], float] | None = None,
    cell_ids: Sequence[str] | None = None,
    layers: Sequence[str] | None = None,
) -> tuple[LocalPowerPlan, ...]:
    """从冻结注册表 + D.1 的 MDE 表生成 20 个格的执行计划。

    倍数与基础场景只从 ``design_power_jobs`` 读，设计 MDE 只从 D.1 的观测方差表读；
    缺任何一格都抛错（不允许用别的层的方差顶替）。
    """
    proto = protocol or load_v3_protocol()
    table = dict(design_mde_table() if mde_table is None else mde_table)
    sigmas = design_sigma_table()
    jobs = proto.config.to_dict()["design_power_jobs"]
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
            registered_n=int(job["n"]), registered_reps=int(job["R"]), design_mde=float(table[(base, multiplier)]),
            design_sigma_treatment=float(sigmas[base][0]), design_sigma_control=float(sigmas[base][1]),
        ))
    if cell_ids is not None:
        wanted = tuple(str(value) for value in cell_ids)
        known = {plan.cell_id for plan in plans}
        unknown = set(wanted) - known
        if unknown:
            raise ValueError(f"unknown local-power cells: {sorted(unknown)}")
        plans = [plan for plan in plans if plan.cell_id in set(wanted)]
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
    """按基础场景逐个构造参考面板并校准选中的格（每层只建一块面板）。

    Returns
    -------
    tuple
        ``(calibrations, curves, verifications)``；三者顺序与 ``plans`` 对齐。
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
        if progress is not None:
            progress(f"[panel] {base} reference_n={reference_n or base_cfg.require('design.n_total')}")
        panel = build_reference_panel(base_cfg, reference_n=reference_n)
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
    """
    probabilities = population.audit_probabilities
    p0 = np.asarray(probabilities.p0_conditional, dtype=float)
    p1 = np.asarray(probabilities.p1_conditional, dtype=float)
    m0, m1 = per_purchase_profit(population.users, cfg)
    if not (len(p0) == len(p1) == len(m0) == len(m1) == len(population.users)):
        raise ValueError("audit arrays are not aligned with the generated population")
    return {
        "realized_effect": float(np.mean(p1 * m1 - p0 * m0)),
        "realized_mean_purchase_control": float(p0.mean()),
        "realized_mean_purchase_treated": float(p1.mean()),
    }


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
        return None

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
        :func:`calibrate_local_power_cell` 的结果；它同时是放行凭据，且其
        ``scaled_config()`` 是本次生成/流水线使用的唯一配置。
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
        "source_label": _SOURCE_LABEL, "cell_id": calibration.cell_id,
        "base_scenario_id": calibration.base_scenario_id, "level": calibration.level,
        "multiplier": calibration.multiplier, "rep": rep, "run_id": run_id,
        "n_requested": n, "alpha": level_alpha,
        "target_effect": calibration.target_effect, "achieved_effect": calibration.achieved_effect,
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
        row.update({
            "itt_diff": profit.diff, "itt_se": profit.se, "itt_ci_lower": profit.ci_lower,
            "itt_ci_upper": profit.ci_upper, "itt_p_value": profit.p_value,
            "purchase_diff": purchase.diff, "purchase_p_value": purchase.p_value,
            "mean_profit_treated": profit.mean_treated, "mean_profit_control": profit.mean_control,
            "mean_purchase_treated": purchase.mean_treated, "mean_purchase_control": purchase.mean_control,
        })
        profit_values = observations["net_profit"].to_numpy(dtype=float)
        treated_flag = observations["treatment"].to_numpy() == 1
        if not np.all(np.isfinite(profit_values)):
            raise ValueError(f"{calibration.cell_id}: non-finite net_profit in the analysis table")
        row["sd_profit_treated"] = float(np.std(profit_values[treated_flag], ddof=1))
        row["sd_profit_control"] = float(np.std(profit_values[~treated_flag], ddof=1))
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
    progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """跑一个功效格的 ``reps`` 次重复，返回逐 rep 表（失败即抛，不吞）。"""
    if isinstance(reps, bool) or not isinstance(reps, (int, np.integer)) or int(reps) < 1:
        raise ValueError(f"reps must be an integer >= 1, got {reps!r}")
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "tmp"
    tmp.mkdir(exist_ok=True)
    keep_dir = root / "representative"
    keep_dir.mkdir(exist_ok=True)
    rows: list[dict[str, Any]] = []
    for rep in range(int(rep_start), int(rep_start) + int(reps)):
        keep = keep_representative and rep == 0
        directory = (keep_dir if keep else tmp) / f"{calibration.cell_id}_rep{rep}_n{n}"
        if directory.exists():
            raise FileExistsError(f"refusing to overwrite an existing attempt directory: {directory}")
        if progress is not None:
            progress(f"[rep] {calibration.cell_id} rep={rep} n={n}")
        row = run_local_power_rep(
            calibration, rep=rep, n=n, run_dir=directory, alpha=alpha,
            keep_artifacts=keep, audit=bool(audit_rep0 and rep == 0),
        )
        rows.append(row)
        if progress is not None:
            progress(f"[rep]   p={row['itt_p_value']:.4f} cpu={row['total_cpu_s']:.2f}s")
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 汇总：拒绝率 + 二项区间 + MC_SE
# --------------------------------------------------------------------------- #
def _clopper_pearson(successes: int, trials: int) -> tuple[float, float]:
    """复用 D.2 的 Clopper–Pearson 实现，保证功效表与 AA 表的区间口径一致。"""
    from causal_growth.evaluation.v3_aa import clopper_pearson

    return clopper_pearson(int(successes), int(trials))


def summarize_local_power(
    repetitions: pd.DataFrame,
    calibrations: Sequence[LocalPowerCalibration],
    *,
    alpha: float,
    registered_n: Mapping[str, int] | None = None,
    design_sigma: Mapping[str, tuple[float, float]] | None = None,
) -> pd.DataFrame:
    """把一个格的 R 次重复汇总成一行（拒绝率、区间、名义功效、成本）。

    ``nominal_power`` 用**本次运行的实测臂内样本 σ**（含单笔订单内部方差）在本次每臂
    人数上解析计算，因此可与实测拒绝率直接对照。
    ``nominal_power_registered_n`` 用 D.1 设计先导的 σ 在注册 n 上计算，即设计期名义
    功效（1×MDE 的格应约为 0.80，这是"名义 vs 实测"的另一半）。

    注意：:class:`ProfitEffectCurve` 的条件均值 σ 是下界，**不用于**功效公式。
    """
    if repetitions.empty:
        raise ValueError("no repetitions to summarize")
    registered = dict(registered_n or {})
    sigmas = dict(design_sigma or {})
    rows: list[dict[str, Any]] = []
    for calibration in calibrations:
        frame = repetitions.loc[repetitions.cell_id == calibration.cell_id].reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"no repetitions recorded for {calibration.cell_id}")
        p_values = frame["itt_p_value"].to_numpy(dtype=float)
        if not np.all(np.isfinite(p_values)):
            raise ValueError(f"{calibration.cell_id}: non-finite p values in the repetition table")
        repetitions_count = int(len(frame))
        rejections = int(np.count_nonzero(p_values < alpha))
        rejection_rate = rejections / repetitions_count
        cp_lower, cp_upper = _clopper_pearson(rejections, repetitions_count)
        n_treatment = int(round(float(frame["n_treatment"].mean())))
        n_control = int(round(float(frame["n_control"].mean())))
        sd_treatment = float(frame["sd_profit_treated"].mean())
        sd_control = float(frame["sd_profit_control"].mean())
        nominal = profit_power(
            calibration.target_effect, sd_treatment, sd_control,
            max(n_treatment, 2), max(n_control, 2), alpha=alpha,
        )
        design_pair = sigmas.get(calibration.cell_id)
        registered_size = registered.get(calibration.cell_id)
        if design_pair is None or registered_size is None:
            nominal_registered = float("nan")
            design_treatment = design_control = float("nan")
        else:
            design_treatment, design_control = float(design_pair[0]), float(design_pair[1])
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
        curve = calibration.curve
        row: dict[str, Any] = {
            "source_label": _SOURCE_LABEL,
            "cell_id": calibration.cell_id,
            "base_scenario_id": calibration.base_scenario_id,
            "level": calibration.level,
            "multiplier": calibration.multiplier,
            "R": repetitions_count,
            "n_total": int(round(float(frame["n_total"].mean()))),
            "n_treatment_mean": n_treatment,
            "n_control_mean": n_control,
            "alpha": float(alpha),
            "design_mde": calibration.design_mde,
            "target_effect": calibration.target_effect,
            "achieved_effect": calibration.achieved_effect,
            "relative_deviation": calibration.relative_deviation,
            "increment_scale": calibration.increment_scale,
            "mean_purchase_increment": calibration.mean_purchase_increment,
            "reference_n": curve.reference_n,
            "reference_sampling_se": curve.reference_sampling_se,
            "effect_at_zero_increment": curve.effect_at_zero_increment,
            "effect_floor": curve.effect_min,
            "effect_upper": curve.effect_upper,
            "binding_constraint": curve.binding_constraint,
            "profit_sd_treatment_observed": sd_treatment,
            "profit_sd_control_observed": sd_control,
            "design_sigma_treatment": design_treatment,
            "design_sigma_control": design_control,
            "nominal_power": nominal,
            "nominal_power_registered_n": nominal_registered,
            "rejection_rate": rejection_rate,
            "rejection_mc_se": math.sqrt(max(rejection_rate * (1.0 - rejection_rate), 0.0) / repetitions_count),
            "rejection_cp_lower": cp_lower,
            "rejection_cp_upper": cp_upper,
            "rejections": rejections,
            "measured_minus_nominal": rejection_rate - nominal,
            "mean_itt": float(frame["itt_diff"].mean()),
            "itt_mean_se": float(frame["itt_diff"].std(ddof=1) / math.sqrt(repetitions_count)),
            "mean_p_value": float(p_values.mean()),
            "median_p_value": float(np.median(p_values)),
            "realized_effect_mean": realized_mean,
            "realized_effect_se": realized_se,
            "realized_effect_reps": realized_reps,
            "purchase_increment_mean": float(frame["purchase_diff"].mean()),
            "purchase_rejection_rate": float(np.count_nonzero(frame["purchase_p_value"].to_numpy() < alpha)
                                             / repetitions_count),
            "dgp_cpu_s_mean": float(frame["dgp_cpu_s"].mean()),
            "pipeline_cpu_s_mean": float(frame["pipeline_cpu_s"].mean()),
            "itt_cpu_s_mean": float(frame["itt_cpu_s"].mean()),
            "audit_cpu_s_mean": float(frame["audit_cpu_s"].mean()),
            "total_cpu_s_mean": float(frame["total_cpu_s"].mean()),
            "wall_s_mean": float(frame["total_wall_s"].mean()),
            "config_hash": str(frame["config_hash"].iloc[0]),
            "scaled_config_hash": calibration.scaled_config_hash,
            "effect_construction": LOCAL_POWER_EFFECT_CONSTRUCTION,
            "interpretation": _interpretation(calibration),
            "note": _note(calibration),
        }
        rows.append(row)
    return pd.DataFrame(rows).loc[:, list(SUMMARY_COLUMNS)]


def _interpretation(calibration: LocalPowerCalibration) -> str:
    """该格的拒绝率该被读成什么（防止把 size 读成功效、把校准零效应读成 AA）。"""
    if calibration.multiplier == 0:
        return "size_at_calibrated_zero_profit_effect_not_aa_not_increment_null"
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
        "target = multiplier x design MDE; achieved re-integrated analytically; "
        f"increment scale {calibration.increment_scale:.4f} of the registered headroom"
    )


# --------------------------------------------------------------------------- #
# 可行域诊断表
# --------------------------------------------------------------------------- #
def feasibility_table(
    calibrations: Sequence[LocalPowerCalibration],
) -> pd.DataFrame:
    """20 格的可行域诊断：目标效应相对该机制上界还剩多少余量。

    列 ``scale_margin_to_upper`` = ``scale_upper / increment_scale``：
    1 表示刚好顶到机制上界，越小越安全。``reachable`` 恒为 True——被拒绝的格
    在校准阶段就抛 :class:`LocalPowerInfeasible`，不会出现在这张表里。
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
            "achieved_effect": calibration.achieved_effect,
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

    正式规模是 ``reps=100, n=200000``（20 格 = 2000 rep）；本函数不设上限，
    但**谁调用谁负责排期**：它只报告实测 CPU，不改变任何正式计数器。
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
    rows: list[dict[str, Any]] = []
    for plan, calibration in zip(chosen, calibrations):
        size = int(plan.registered_n if n is None else n)
        count = int(plan.registered_reps if reps is None else reps)
        frame = run_local_power_cell(
            calibration, reps=count, n=size, run_root=root, alpha=level_alpha,
            keep_representative=keep_representative, audit_rep0=audit_rep0, progress=progress,
        )
        rows.append(frame)
        pd.concat(rows, ignore_index=True).to_csv(flush, index=False, encoding="utf-8-sig")
    repetitions = pd.concat(rows, ignore_index=True)
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
        "cells": [
            {**plan.__dict__, **{"calibration": calibration.as_record(),
                                 "verification": verification}}
            for plan, calibration, verification in zip(chosen, calibrations, verifications)
        ],
        "curves": [curve.as_record() for curve in {c.base_scenario_id: c for c in curves}.values()],
        "n_note": "n is this run's population size; registered n is recorded per cell",
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
    parser.add_argument("--reps", type=int, default=2, help="repetitions per cell (default 2)")
    parser.add_argument("--n", type=int, default=2000, help="population size per rep (default 2000)")
    parser.add_argument("--reference-n", type=int, default=None,
                        help="reference panel size for the analytic effect (default: design n_total)")
    parser.add_argument("--cells", type=str, default=None, help="comma-separated cell ids")
    parser.add_argument("--layers", type=str, default=None, help="comma-separated layers, e.g. L1,L2")
    parser.add_argument("--alpha", type=float, default=None)
    parser.add_argument("--out", type=str, default=None, help="run root (must not exist)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：小规模跑通并打印汇总（默认不触碰 20 万 × 100 的正式排期）。"""
    args = _parse_args(argv)
    protocol = load_v3_protocol()
    plans = local_power_plan(
        protocol,
        cell_ids=None if args.cells is None else [item.strip() for item in args.cells.split(",") if item],
        layers=None if args.layers is None else [item.strip() for item in args.layers.split(",") if item],
    )
    bundle = run_local_power_matrix(
        protocol, plans=plans, reps=args.reps, n=args.n, reference_n=args.reference_n,
        alpha=args.alpha, run_root=args.out, progress=print,
    )
    columns = ["cell_id", "multiplier", "target_effect", "achieved_effect", "nominal_power",
               "rejection_rate", "rejection_cp_lower", "rejection_cp_upper", "mean_itt"]
    print(bundle.summary.loc[:, columns].to_string(index=False))
    print(f"artifacts: {bundle.run_root}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
