"""G 阶段矩阵驱动：一次历史数据构建同时服务 ATE、模型学习与独立验证。

回答方案里的哪个问题
--------------------
`configs/v3/execution.yaml` 的 ``job_semantics`` 早已冻结三件事：

- ``full_learning_reuses_first_ate_repetitions``：学习复用前 R_learn 个 ATE rep，不另建数据；
- ``independent_validation_is_extra_population``：验证是额外队列，必须单独生成；
- ``all_models_share_repetition_data_and_split``：同 rep 内所有模型共享数据与拆分。

仓库里此前没有任何代码实现这层语义。若按字面各跑一遍，同一份数据会被建两遍，
多花约 191 CPU·h。本模块把循环固定为：

    对每个 (cell, rep)
        1) 建一次历史观测表（raw→dirty→clean→SQL→split）
        2) ATE（ITT，来自这份观测表）
        3) rep < R_learn 时：准备学习数据 → 各模型 fit_predict → 验证集选模
        4) rep < R_validation 时：独立 20 万队列 → 三臂名单 → 冻结 →（之后才读真值）

纪律
----
- 真值只在 ``freeze.json`` 与 ``policy_list.csv`` 落盘之后才被解锁；选人与选模
  只读预测列，``tau_true`` / ``cost_true`` 不得进入任何选择函数（AGENTS §4 / §12）。
- 历史数据只建一次：``history_pipeline_builds`` 恒为 1；验证队列是第二个、按设计
  必须独立的构建（``validation_pipeline_builds`` 至多 1）。
- 数据构建前后各取一次 ``pipeline_source_hashes()``；不一致立即抛
  ``RuntimeError("source files changed during the data run")``（AGENTS §11）。
- 预算覆盖只读 ``configs/budget/*.yaml``；``configs/v3`` 七份冻结配置的 canonical
  hash 不因覆盖文件变化。

本模块不写正式完成计数：``status`` 只描述本次尝试，``provisional`` 由目标 R 是否
跑满决定。正式运行仍需用户批准与快照（AGENTS §11）。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import yaml

from causal_growth.config import Config, ConfigError
from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_pipeline import pipeline_source_hashes
from causal_growth.data.v3_quality import validate_tables
from causal_growth.data.v3_sql import run_sql_pipeline
from causal_growth.data.v3_storage import dataframe_sha256
from causal_growth.data.v3_tables import build_raw_tables
from causal_growth.dgp.v3_engine import generate_covariates, generate_v3_population
from causal_growth.estimate.itt import itt_difference_means, itt_difference_proportions
from causal_growth.estimate.v3_models import (
    MODEL_NAMES,
    _fit_level_baselines,
    _observations_for_keys,
    fit_cost_model,
    fit_predict,
    fit_validation_scorer,
    prepare_learning_data,
    rank_models,
)
from causal_growth.evaluation import v3_f02 as f02
from causal_growth.v3_config import V3Protocol, load_v3_protocol

#: 历史/验证数据构建期间源码被改写时的固定消息（与 C 阶段门禁一致）。
SOURCE_CHANGED_MARKER = "source files changed during the data run"

#: ``job_semantics`` 中本驱动必须为真的条目；为假说明协议被改过，拒绝运行。
REQUIRED_SEMANTICS: tuple[str, ...] = (
    "full_learning_reuses_first_ate_repetitions",
    "independent_validation_is_extra_population",
    "all_models_share_repetition_data_and_split",
)

BLOCK_CORE = "g_core"
BLOCK_TIER2 = "g_tier2"

_STATUSES: tuple[str, ...] = ("engineering", "provisional", "formal")


_PRIMARY_BOOTSTRAP_SCOPE = "primary_0.2"


def require_bootstrap_scope(status: str, resamples: int, scope: str | None) -> None:
    """正式运行的固定策略 bootstrap 只覆盖主预算档，且必须显式声明。

    缺声明就拒绝：否则产物看起来"跑过 bootstrap"，实际只有主档一次，
    读者会以为全预算都重抽样了（docs/v3_G执行器缺口与设计.md §6.2）。
    工程/临时状态不受限，保留 A10 冒烟能力。
    """
    if int(resamples) <= 0 or status != "formal":
        return
    if scope != _PRIMARY_BOOTSTRAP_SCOPE:
        raise ValueError(
            "正式运行的固定策略 bootstrap 只覆盖主预算档；必须显式传 "
            f"bootstrap_budget_scope={_PRIMARY_BOOTSTRAP_SCOPE!r}，当前为 {scope!r}"
        )


def bootstrap_budget_scopes(protocol: Any, resamples: int) -> dict[str, int | None] | None:
    """运行清单用：主档写次数，其余预算档显式写 None。"""
    if int(resamples) <= 0:
        return None
    data = protocol.config.to_dict()
    grid = list(data["policy"]["budget"]["per_user_grid_cny"])
    primary = float(data["evaluation"]["independent_validation"]["primary_budget_cny_per_user"])
    return {
        str(float(value)): (int(resamples) if abs(float(value) - primary) < 1e-12 else None)
        for value in grid
    }


def require_primary_budget(cfg: Any, budget: float, resamples: int) -> None:
    """固定 bootstrap 的预算必须等于配置主预算（§6.6）。

    验证臂目前只有一个预算档（v3_f02.py:283），这条断言把"现状"变成契约：
    将来若给验证臂加预算参数，这里先炸，避免 bootstrap 悄悄扩到全预算网格。
    """
    if int(resamples) <= 0:
        return
    primary = float(cfg.require("evaluation.independent_validation.primary_budget_cny_per_user"))
    if abs(float(budget) - primary) > 1e-12:
        raise ValueError(
            f"固定 bootstrap 只允许主预算档 {primary} 元；当前预算为 {float(budget)} 元"
        )

#: E 阶段 9 列契约；预测 7 列与真值 2 列必须分文件（任务书 §7）。
E_PREDICTION_COLUMNS: tuple[str, ...] = (
    "user_id", "is_new", "cart_value", "purchase_propensity",
    "predicted_profit", "tau_hat", "cost_hat",
)
E_TRUTH_COLUMNS: tuple[str, ...] = ("user_id", "tau_true", "cost_true")
E_COLUMNS: tuple[str, ...] = E_PREDICTION_COLUMNS + ("tau_true", "cost_true")

#: 逐 rep 表的固定列序；``model_*`` 列在中间按 MODEL_NAMES 顺序展开。
ROW_HEAD: tuple[str, ...] = (
    "cell_id", "scenario_id", "level", "tier", "block", "rep", "n", "treatment_share",
)
ROW_ATE: tuple[str, ...] = (
    "n_treated", "n_control",
    "ate", "ate_se", "ate_p_value", "ate_ci_lower", "ate_ci_upper",
    "ate_test", "ate_test_se", "ate_test_p_value",
    "ate_paid_purchase_7d", "ate_any_refund_30d",
)
ROW_TAIL: tuple[str, ...] = (
    "learning_prefix", "chosen_model",
    "preprocessor_hash", "split_fingerprint",
    "config_hash", "protocol_config_hash",
    "observed_hash", "observed_hash_without_run_id",
    "overlay_source", "overlay_sha256",
    "history_pipeline_builds", "validation_pipeline_builds",
    "validation_n", "validation_targeted_n", "validation_random_n",
    "validation_predicted_spend_per_user", "validation_budget_per_user",
    "validation_freeze_hash", "validation_observed_hash",
    "validation_bootstrap_resamples", "validation_bootstrap_point_diff",
    "validation_bootstrap_se", "validation_bootstrap_ci_low",
    "validation_bootstrap_ci_high",
    "status", "provisional",
)

#: CPU 计时是硬件遥测，任何两次运行都不同；单独落盘，避免污染 A2 的逐字节复现。
TELEMETRY_COLUMNS: tuple[str, ...] = (
    "scenario_id", "block", "rep",
    "cpu_seconds_pipeline", "cpu_seconds_estimate", "cpu_seconds_models",
)


def row_columns() -> tuple[str, ...]:
    """逐 rep 表的完整列序（固定，供字节级续跑比对）。"""
    model_columns = tuple(
        column
        for name in MODEL_NAMES
        for column in (f"model_{name}_tau_mean", f"model_{name}_tau_sd")
    )
    return ROW_HEAD + ROW_ATE + model_columns + ROW_TAIL


#: 汇总表必须带精度：每个格都有 ``R`` 与 ``MC_SE``（任务书 §8 A7）。
SUMMARY_METRICS: tuple[str, ...] = ("ate", "ate_test", "ate_paid_purchase_7d", "ate_any_refund_30d")


# --------------------------------------------------------------------------- #
# 预算覆盖（Package B 的接线点）
# --------------------------------------------------------------------------- #
OVERLAY_KEYS: frozenset[str] = frozenset({
    "schema_version", "kind", "maintained_at_beijing", "supersedes", "notes",
    "tier1_learning_reps", "tier1_validation_reps", "tier2_cells", "tier2_reps",
})


@dataclass(frozen=True)
class BudgetPlan:
    """一次运行的批数契约：来自冻结配置，或来自 ``configs/budget`` 下的覆盖文件。"""

    source: str
    path: str | None
    sha256: str | None
    tier1_learning_reps: int
    tier1_validation_reps: int
    tier2_cells: tuple[str, ...]
    tier2_reps: int
    maintained_at_beijing: str | None = None
    supersedes: str | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "path": self.path,
            "sha256": self.sha256,
            "tier1_learning_reps": self.tier1_learning_reps,
            "tier1_validation_reps": self.tier1_validation_reps,
            "tier2_cells": list(self.tier2_cells),
            "tier2_reps": self.tier2_reps,
            "maintained_at_beijing": self.maintained_at_beijing,
            "supersedes": self.supersedes,
        }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def cell_meta(protocol: V3Protocol, cell_id: str) -> dict[str, Any]:
    """返回注册表里的格元数据；未知/重复一律报错。"""
    data = protocol.config.to_dict()
    matches = [s for s in data["scenarios"] if s["id"] == cell_id]
    if len(matches) != 1:
        raise ConfigError(f"未知或重复的 scenario_id：{cell_id}")
    return matches[0]


def tier2_cell_ids(protocol: V3Protocol) -> tuple[str, ...]:
    """冻结配置下全部 Tier2 灵敏度格（不含 AA 格）。"""
    data = protocol.config.to_dict()
    return tuple(
        s["id"] for s in data["scenarios"]
        if int(s["tier"]) == 2 and "ate" in s["roles"]
    )


def load_budget_plan(
    protocol: V3Protocol | None = None,
    overlay: str | Path | None = None,
) -> BudgetPlan:
    """读冻结批数，或读 ``configs/budget`` 下的覆盖文件。

    覆盖文件必须放在 ``configs/budget/``：``pipeline_source_hashes()`` 只扫
    ``configs/v3*.yaml`` 与 ``configs/v3/*.yaml``，放别处会把"改预算"变成"改源码"。
    读不懂的键直接失败（AGENTS §12.7），不做静默忽略。
    """
    protocol = protocol or load_v3_protocol()
    data = protocol.config.to_dict()
    repeats = data["execution"]["formal_repeats"]
    frozen_tier2 = tier2_cell_ids(protocol)
    if overlay is None:
        return BudgetPlan(
            source="frozen",
            path=None,
            sha256=None,
            tier1_learning_reps=int(repeats["tier1_full_learning_per_model"]),
            tier1_validation_reps=int(repeats["tier1_independent_validation"]),
            tier2_cells=frozen_tier2,
            tier2_reps=int(repeats["tier2_ate"]),
        )
    path = Path(overlay)
    raw = path.read_bytes()
    obj = yaml.safe_load(raw.decode("utf-8-sig"))
    _require(isinstance(obj, dict), f"覆盖文件必须是 mapping：{path}")
    unknown = sorted(set(obj) - OVERLAY_KEYS)
    if unknown:
        raise ConfigError(f"覆盖文件含未注册键 {unknown}；拒绝猜测其含义")
    missing = sorted(OVERLAY_KEYS - set(obj))
    if missing:
        raise ConfigError(f"覆盖文件缺少键 {missing}")
    _require(int(obj["schema_version"]) == 1, f"schema_version 必须是 1：{obj['schema_version']!r}")
    _require(str(obj["kind"]) == "budget_overlay", f"kind 必须是 budget_overlay：{obj['kind']!r}")
    tier2_cells = obj["tier2_cells"]
    _require(isinstance(tier2_cells, list) and tier2_cells, "tier2_cells 必须是非空列表")
    _require(len(tier2_cells) == len(set(tier2_cells)), "tier2_cells 不能重复")
    for cell_id in tier2_cells:
        meta = cell_meta(protocol, str(cell_id))
        _require(int(meta["tier"]) == 2, f"{cell_id} 不是 Tier2 格")
        _require("ate" in meta["roles"], f"{cell_id} 没有 ATE 角色")
    plan = BudgetPlan(
        source="overlay",
        path=path.as_posix(),
        sha256=hashlib.sha256(raw).hexdigest(),
        tier1_learning_reps=int(obj["tier1_learning_reps"]),
        tier1_validation_reps=int(obj["tier1_validation_reps"]),
        tier2_cells=tuple(str(cell_id) for cell_id in tier2_cells),
        tier2_reps=int(obj["tier2_reps"]),
        maintained_at_beijing=str(obj["maintained_at_beijing"]),
        supersedes=str(obj["supersedes"]),
    )
    for name in ("tier1_learning_reps", "tier1_validation_reps", "tier2_reps"):
        _require(getattr(plan, name) > 0, f"{name} 必须为正")
    _require(
        plan.tier1_learning_reps <= int(repeats["tier1_ate"]),
        "学习批数不得超过 ATE 批数：学习是 ATE reps 的前缀子集",
    )
    _require(
        plan.tier1_validation_reps <= int(repeats["tier1_ate"]),
        "验证批数不得超过 ATE 批数：验证在同一 rep 上做",
    )
    return plan


def plan_cell(
    protocol: V3Protocol,
    cell_id: str,
    plan: BudgetPlan | None = None,
) -> dict[str, Any]:
    """把格与批数契约合成为一次运行的批次计划（含前缀约束）。"""
    plan = plan or load_budget_plan(protocol)
    meta = cell_meta(protocol, cell_id)
    roles = tuple(meta["roles"])
    if int(meta["formal_repetitions"]["complete_aa"]):
        raise ValueError(f"{cell_id} 是 AA 格；AA 批由 v3_aa.run_aa_rep 负责，不走本驱动")
    if "ate" not in roles:
        raise ValueError(f"{cell_id} 没有 ATE 角色")
    tier = int(meta["tier"])
    if tier == 1:
        if "core" not in roles:
            raise ValueError(f"{cell_id} 是 Tier1 但非 core；Tier1 正式格只跑注册的 core 格")
        r_ate = int(meta["formal_repetitions"]["ate"])
        r_learn = min(int(plan.tier1_learning_reps), r_ate)
        r_validation = min(int(plan.tier1_validation_reps), r_ate)
        block = BLOCK_CORE
    elif tier == 2:
        if cell_id not in plan.tier2_cells:
            raise ValueError(f"{cell_id} 未被批数契约选中（Tier2 覆盖收缩）")
        r_ate = int(plan.tier2_reps)
        r_learn = r_ate
        r_validation = r_ate
        block = BLOCK_TIER2
    else:
        raise ValueError(f"未注册的 tier：{tier}")
    if r_learn > r_ate or r_validation > r_ate:
        raise ValueError("学习/验证批数必须是 ATE 批数的前缀")
    return {
        "cell_id": cell_id,
        "level": str(meta["level"]),
        "tier": tier,
        "block": block,
        "n": int(meta["n"]),
        "treatment_probability": float(meta["treatment_probability"]),
        "roles": roles,
        "R_ate": r_ate,
        "R_learn": r_learn if "learning" in roles else 0,
        "R_validation": r_validation if "independent_validation" in roles else 0,
    }


def require_job_semantics(cfg: Config) -> dict[str, Any]:
    """拒绝在 ``job_semantics`` 被改成假值的协议上运行。"""
    section = dict(cfg.section("execution.job_semantics"))
    broken = [key for key in REQUIRED_SEMANTICS if section.get(key) is not True]
    if broken:
        raise ConfigError(f"job_semantics 未生效：{broken}；本驱动拒绝退化为重复建数据")
    return section


# --------------------------------------------------------------------------- #
# 数据构建（历史与验证两套入口，前后各哈希一次源码）
# --------------------------------------------------------------------------- #
def _stream_prefix(population: Any) -> str:
    metadata = getattr(population, "metadata", {}) or {}
    prefix = metadata.get("stream_prefix")
    if not prefix:
        raise ValueError("种群缺少 stream_prefix，无法派生随机流")
    return str(prefix)


def _materialize(
    population: Any,
    cfg: Config,
    *,
    run_id: str,
    rep_id: int,
    population_kind: str,
) -> tuple[ObservedDataset, dict[str, Any]]:
    """共用的 raw→dirty→clean→SQL 链路；不写五表，只返回观测数据集。"""
    users, assignments, orders = population.observation_bundle()
    stream = _stream_prefix(population)
    raw = build_raw_tables(
        users, assignments, orders, cfg, run_id=run_id, rep_id=rep_id, stream_prefix=stream,
    )
    dirty = inject_dirt(raw, cfg, rep_id=rep_id, stream_prefix=stream)
    clean = deduplicate_events(dirty.tables, cfg)
    raw_sql = run_sql_pipeline(raw, cfg)
    raw_dataset = ObservedDataset.from_sql_result(raw_sql, cfg)
    if raw_dataset.population_kind != population_kind:
        raise ValueError(
            f"观测表种群类型 {raw_dataset.population_kind!r} 与声明的 {population_kind!r} 不一致"
        )
    if population_kind == "history":
        split_dataset, split_manifest = raw_dataset.assign_splits(
            cfg, stream=f"{stream}.split", index=rep_id
        )
        labels = split_dataset.observations.set_index(["run_id", "user_id"]).split
        for tables in (raw, dirty.tables, clean.tables):
            keys = pd.MultiIndex.from_frame(tables["users"][["run_id", "user_id"]])
            tables["users"]["split"] = labels.reindex(keys).to_numpy()
    else:
        if not raw["users"].split.eq("test").all():
            raise ValueError("独立验证用户必须保持 test 标记")
        split_manifest = {
            "method": "independent_randomized_policy_validation_no_training_split",
            "n_users": len(users),
            "counts": {"test": len(users)},
        }
    clean_sql = run_sql_pipeline(clean.tables, cfg)
    dataset = ObservedDataset.from_sql_result(clean_sql, cfg)
    raw["user_outcomes"] = raw_sql.user_outcomes.copy(deep=True)
    clean.tables["user_outcomes"] = clean_sql.user_outcomes.copy(deep=True)
    dirty.tables["user_outcomes"] = clean_sql.user_outcomes.copy(deep=True)
    validate_tables(clean.tables, cfg, stage="clean", require_outcomes=True)
    return dataset, {
        "split_manifest": split_manifest,
        "n_users": len(users),
        "n_orders": int(len(orders)),
        "raw_sql_hash": raw_dataset.content_hash,
    }


def _guarded_build(
    build: Callable[[], tuple[ObservedDataset, dict[str, Any]]],
) -> tuple[ObservedDataset, dict[str, Any], dict[str, str]]:
    """数据构建前后各取一次源码哈希；变化即失败（AGENTS §11）。"""
    before = pipeline_source_hashes()
    dataset, info = build()
    after = pipeline_source_hashes()
    if before != after:
        raise RuntimeError(f"{SOURCE_CHANGED_MARKER}; retain this attempt as failed")
    return dataset, info, before


def build_history_dataset(
    cfg: Config,
    *,
    rep_id: int,
    n: int,
    run_id: str,
) -> tuple[ObservedDataset, dict[str, Any], dict[str, str]]:
    """建一次历史观测表；调用方必须保证每个 (cell, rep) 只调用一次。"""

    def _build() -> tuple[ObservedDataset, dict[str, Any]]:
        population = generate_v3_population(cfg, rep_id=int(rep_id), n=int(n))
        return _materialize(
            population, cfg, run_id=run_id, rep_id=int(rep_id), population_kind="history"
        )

    dataset, info, hashes = _guarded_build(_build)
    if len(dataset.observations) != int(n):
        raise ValueError("历史观测表的全部分配用户数不等于 n")
    return dataset, info, hashes


def build_validation_dataset(
    cfg: Config,
    *,
    rep_id: int,
    n: int,
    run_id: str,
    assignment: pd.DataFrame,
) -> tuple[ObservedDataset, dict[str, Any], dict[str, str]]:
    """独立验证队列是**额外**种群，必须单独生成（job_semantics 第二条）。"""

    def _build() -> tuple[ObservedDataset, dict[str, Any]]:
        population = generate_v3_population(
            cfg, rep_id=int(rep_id), n=int(n), population_kind="validation",
            validation_assignment=assignment,
        )
        return _materialize(
            population, cfg, run_id=run_id, rep_id=int(rep_id), population_kind="validation"
        )

    dataset, info, hashes = _guarded_build(_build)
    if len(dataset.observations) != int(n) or not dataset.observations["user_id"].is_unique:
        raise ValueError("验证观测表的全臂分母不完整")
    return dataset, info, hashes


# --------------------------------------------------------------------------- #
# ATE 与学习
# --------------------------------------------------------------------------- #
def estimate_ate(dataset: ObservedDataset, cfg: Config) -> dict[str, float]:
    """从**这一份**观测表估 ITT；全人群是 R1 分母，test 只作诊断。"""
    alpha = float(cfg.require("design.alpha_two_sided"))
    observations = dataset.observations
    if "treatment" not in observations or "net_profit" not in observations:
        raise ValueError("观测表缺少 treatment / net_profit，无法估 ATE")
    full = itt_difference_means(observations, "net_profit", alpha=alpha, metric="net_profit")
    if full.n_treated + full.n_control != len(observations):
        raise ValueError("ATE 分母不等于全部分配用户")
    test_frame = observations.loc[observations.split == "test"]
    test = itt_difference_means(test_frame, "net_profit", alpha=alpha, metric="net_profit")
    purchase = itt_difference_proportions(
        observations, "paid_purchase_7d", alpha=alpha, metric="paid_purchase_7d"
    )
    refund = itt_difference_proportions(
        observations, "any_refund_30d", alpha=alpha, metric="any_refund_30d"
    )
    return {
        "n_treated": float(full.n_treated),
        "n_control": float(full.n_control),
        "ate": float(full.diff),
        "ate_se": float(full.se),
        "ate_p_value": float(full.p_value),
        "ate_ci_lower": float(full.ci_lower),
        "ate_ci_upper": float(full.ci_upper),
        "ate_test": float(test.diff),
        "ate_test_se": float(test.se),
        "ate_test_p_value": float(test.p_value),
        "ate_paid_purchase_7d": float(purchase.diff),
        "ate_any_refund_30d": float(refund.diff),
    }


@dataclass(frozen=True)
class HistoryFit:
    """一个 rep 的学习产物；与 ``_d03_rep_artifacts`` 同口径，但复用已建好的数据。"""

    cfg: Config
    dataset: ObservedDataset
    data: Any
    predictions: dict[str, Any]
    ranking: list[dict[str, Any]]
    chosen_model: str
    cost_model: Any
    preprocessor_hash: str
    split_fingerprint: str


def fit_history_models(
    dataset: ObservedDataset,
    cfg: Config,
    *,
    rep_id: int,
    models: Sequence[str] | None = None,
    time_mode: str = "static",
) -> HistoryFit:
    """在已建好的观测表上准备学习数据并拟合各模型（不重建数据）。"""
    names = tuple(MODEL_NAMES if models is None else models)
    if not names:
        raise ValueError("至少需要一个模型")
    unknown = [name for name in names if name not in MODEL_NAMES]
    if unknown:
        raise ValueError(f"未知模型 {unknown}；可用：{MODEL_NAMES}")
    data = prepare_learning_data(dataset, cfg, time_mode=time_mode)
    scorer = fit_validation_scorer(data, cfg, seed_index=int(rep_id))
    predictions = {
        name: fit_predict(
            name, data, cfg, time_mode=time_mode, seed_index=int(rep_id)
        )
        for name in names
    }
    ranking = rank_models(predictions, scorer, cfg)
    chosen_model = str(ranking[0]["model"])
    train_observed = _observations_for_keys(
        dataset, data.train.keys, ("paid_purchase_7d", "coupon_cost")
    )
    cost_model = fit_cost_model(
        data.train.X,
        data.train.treatment,
        train_observed["paid_purchase_7d"].to_numpy(dtype=np.int64),
        train_observed["coupon_cost"].to_numpy(dtype=np.float64),
        cfg,
    )
    return HistoryFit(
        cfg=cfg,
        dataset=dataset,
        data=data,
        predictions=predictions,
        ranking=ranking,
        chosen_model=chosen_model,
        cost_model=cost_model,
        preprocessor_hash=data.preprocessor_hash,
        split_fingerprint=data.split_fingerprint,
    )


# --------------------------------------------------------------------------- #
# 独立验证臂：名单在冻结之后才允许读真值
# --------------------------------------------------------------------------- #
def require_prediction_only(frame: pd.DataFrame, *, name: str = "frame") -> None:
    """拒绝把真值列送进任何选择函数；E 的 9 列契约必须拆成两个文件。"""
    hits = [column for column in frame.columns if "true" in str(column).lower()]
    if hits:
        raise ValueError(f"{name} 含真值列 {hits}；选人与选模只允许预测列")


def select_policy_list(
    frame: pd.DataFrame,
    *,
    policy: str,
    budget_cny: float,
    seed_index: int,
    cfg: Config,
) -> pd.DataFrame:
    """按预测列选人（E 的策略网格），返回冻结的逐用户名单。"""
    require_prediction_only(frame, name="select_policy_list")
    from causal_growth.policy.v3_policy_grid import run_policy
    from causal_growth.rng import child_rng

    rng = child_rng(int(cfg.require("project.master_seed")), "g.policy_list", int(seed_index))
    selection = run_policy(policy, frame, float(budget_cny), rng)
    issued = frame.loc[selection.mask, E_PREDICTION_COLUMNS].copy()
    issued["selected_policy_id"] = str(policy)
    return issued.reset_index(drop=True)


def assemble_e_columns(prediction_frame: pd.DataFrame, truth_frame: pd.DataFrame) -> pd.DataFrame:
    """把 G 的产物拼成 E 的 9 列契约；预测与真值按 ``user_id`` 一对一合并。"""
    missing_pred = [c for c in E_PREDICTION_COLUMNS if c not in prediction_frame]
    if missing_pred:
        raise ValueError(f"预测表缺少列：{missing_pred}")
    missing_truth = [c for c in E_TRUTH_COLUMNS if c not in truth_frame]
    if missing_truth:
        raise ValueError(f"真值表缺少列：{missing_truth}")
    merged = prediction_frame.loc[:, list(E_PREDICTION_COLUMNS)].merge(
        truth_frame.loc[:, list(E_TRUTH_COLUMNS)],
        on="user_id", how="inner", validate="one_to_one",
    )
    if len(merged) != len(prediction_frame):
        raise ValueError("预测与真值的 user_id 不是一一对应")
    return merged.loc[:, list(E_COLUMNS)]


def _audit_truth(
    population: Any,
    cfg: Config,
    *,
    info: Mapping[str, Any],
    observed: pd.DataFrame,
    assignment: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """冻结文件落盘之后才调用的真值审计；单独成函数以便反例测试 monkeypatch。"""
    worlds = f02.audit_realized_worlds(population, cfg)
    audit_users, audit_policy = f02.audit_policy_values(
        population, cfg,
        targeted_ids=info["audit_targeted_ids"],
        random_ids=info["audit_random_ids"],
        user_ids=observed["user_id"].to_numpy(),
        worlds=worlds,
    )
    audit_means, audit_contrasts = f02.true_arm_means(
        population, cfg, assignment, worlds=worlds
    )
    return {
        "users": audit_users,
        "policy": audit_policy,
        "arms": audit_means,
        "contrasts": audit_contrasts,
    }


def two_sample_bootstrap_diff(
    targeted: np.ndarray,
    random_arm: np.ndarray,
    *,
    resamples: int,
    master_seed: int,
    index: int,
) -> dict[str, float | int]:
    """已选/随机两臂净利的双样本 bootstrap（各自有放回重抽），统计量为均值差。

    协议 §7 要求对「已选策略 − 随机策略」做 1000 次重抽样；``metrics.bootstrap_se``
    只支持单样本均值，不能直接用于两臂差，故单列此函数。不重拟合，只重抽已实现利润。
    """
    if int(resamples) <= 0:
        raise ValueError("bootstrap 次数必须为正")
    t = np.asarray(targeted, dtype=float)
    r = np.asarray(random_arm, dtype=float)
    if t.size == 0 or r.size == 0:
        raise ValueError("两臂样本都不能为空")
    from causal_growth.rng import child_rng

    rng = child_rng(int(master_seed), "g.fixed_bootstrap", int(index))
    diffs = np.empty(int(resamples), dtype=float)
    for draw in range(int(resamples)):
        diffs[draw] = (
            t[rng.integers(0, t.size, t.size)].mean()
            - r[rng.integers(0, r.size, r.size)].mean()
        )
    low, high = np.percentile(diffs, [2.5, 97.5])
    return {
        "resamples": int(resamples),
        "n_targeted": int(t.size),
        "n_random": int(r.size),
        "point_diff": float(t.mean() - r.mean()),
        "bootstrap_mean_diff": float(diffs.mean()),
        "bootstrap_se": float(diffs.std(ddof=1)) if diffs.size > 1 else float("nan"),
        "ci_low": float(low),
        "ci_high": float(high),
    }


def _bootstrap_scalar(
    validation: Mapping[str, Any] | None,
    key: str,
    default: float | int = float("nan"),
) -> float | int:
    """从验证臂返回值里取 bootstrap 标量；未跑 bootstrap 时给显式默认值。"""
    if not validation:
        return default
    payload = validation.get("validation_fixed_bootstrap")
    if not payload:
        return default
    return payload[key]


def run_validation_arm(
    fit: HistoryFit,
    cfg: Config,
    *,
    rep_id: int,
    n_validation: int,
    policy: str,
    target_dir: str | Path | None = None,
    bootstrap_resamples: int = 0,
    with_policy_value: bool = False,
) -> dict[str, Any]:
    """独立 20 万队列：三臂 → 冻结名单 → 之后才读真值，并返回逐 rep 摘要。"""
    target = None if target_dir is None else Path(target_dir)
    users = generate_covariates(
        cfg, int(rep_id), int(n_validation), population_kind="validation"
    ).users
    scored = f02.score_validation_users(fit, users, cfg, seed_index=int(rep_id))
    if str(scored.model) != str(fit.chosen_model):
        raise ValueError("验证打分使用的模型与历史选模不一致")
    assignment, info = f02.build_validation_assignment(
        scored, cfg, policy=policy, rep_id=int(rep_id)
    )
    population = generate_v3_population(
        cfg, rep_id=int(rep_id), n=int(n_validation), population_kind="validation",
        validation_assignment=assignment,
    )
    if dataframe_sha256(population.users) != dataframe_sha256(users):
        raise RuntimeError("两次生成的验证用户不一致，三臂分配无法与事实订单对齐")
    dataset, build_info, source_hashes = build_validation_dataset(
        cfg, rep_id=int(rep_id), n=int(n_validation),
        run_id=f"g:{cfg.require('active_scenario.id')}:validation:rep{int(rep_id)}",
        assignment=assignment,
    )
    observed = dataset.observations
    summary = f02.arm_summary(observed)
    contrasts = f02.itt_contrasts(observed, cfg)
    decision = f02.decision_summary(observed, cfg)
    guardrail = f02.guardrail_summary(observed, cfg)
    per_user, freeze_hash = f02.freeze_observed(
        observed, selected_policy=policy, model=str(scored.model)
    )
    freeze_payload = {
        "freeze_hash": freeze_hash,
        "per_user_hash": dataframe_sha256(per_user),
        "decision_hash": dataframe_sha256(decision),
        "guardrail_hash": dataframe_sha256(guardrail),
        "selected_model": str(scored.model),
        "selected_policy": policy,
        "observed_hash": dataset.content_hash,
        "truth_columns_present": False,
        "freeze_written_before_truth": True,
    }
    if target is not None:
        target.mkdir(parents=True, exist_ok=True)
        per_user.to_csv(target / "policy_list.csv", index=False, encoding="utf-8-sig")
        summary.to_csv(target / "arm_summary.csv", index=False, encoding="utf-8-sig")
        contrasts.to_csv(target / "itt_contrasts.csv", index=False, encoding="utf-8-sig")
        decision.to_csv(target / "decision.csv", index=False, encoding="utf-8-sig")
        guardrail.to_csv(target / "guardrail.csv", index=False, encoding="utf-8-sig")
        (target / "freeze.json").write_text(
            json.dumps(freeze_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    # ---- 以下才允许读真值 ----
    truth = _audit_truth(population, cfg, info=info, observed=observed, assignment=assignment)
    if target is not None:
        truth["users"].to_csv(target / "truth_users.csv", index=False, encoding="utf-8-sig")
        truth["policy"].to_csv(target / "truth_policy_values.csv", index=False, encoding="utf-8-sig")
        truth["arms"].to_csv(target / "truth_arm_means.csv", index=False, encoding="utf-8-sig")
        truth["contrasts"].to_csv(target / "truth_arm_contrasts.csv", index=False, encoding="utf-8-sig")
    bootstrap: dict[str, Any] | None = None
    if int(bootstrap_resamples) > 0:
        require_primary_budget(cfg, float(info["budget_cny_per_user"]), int(bootstrap_resamples))
        targeted_profit = observed.loc[
            observed["assigned_policy_arm"] == f02.TARGETED_ARM, "net_profit"
        ].to_numpy(dtype=float)
        random_profit = observed.loc[
            observed["assigned_policy_arm"] == f02.RANDOM_ARM, "net_profit"
        ].to_numpy(dtype=float)
        bootstrap = two_sample_bootstrap_diff(
            targeted_profit, random_profit,
            resamples=int(bootstrap_resamples),
            master_seed=int(cfg.require("project.master_seed")),
            index=int(rep_id),
        )
        if target is not None:
            pd.DataFrame([{
                "rep": int(rep_id),
                "budget_cny_per_user": float(info["budget_cny_per_user"]),
                **bootstrap,
            }]).to_csv(target / "fixed_bootstrap.csv", index=False, encoding="utf-8-sig")
    targeted = info["arms"][f02.TARGETED_ARM]
    random_arm = info["arms"][f02.RANDOM_ARM]
    result: dict[str, Any] = {
        "validation_n": int(n_validation),
        "validation_targeted_n": int(targeted["n_issued"]),
        "validation_random_n": int(random_arm["n_issued"]),
        "validation_predicted_spend_per_user": float(
            targeted["predicted_spend_per_assigned_cny"]
        ),
        "validation_budget_per_user": float(info["budget_cny_per_user"]),
        "validation_freeze_hash": freeze_hash,
        "validation_observed_hash": dataset.content_hash,
        "source_hashes": source_hashes,
        "build_info": build_info,
        "validation_fixed_bootstrap": bootstrap,
    }
    if with_policy_value:
        policy_truth = truth["policy"]
        selected = policy_truth.loc[policy_truth["component"] == "value_targeted_policy"]
        if len(selected) != 1:
            raise ValueError("真值策略表应恰有一行 value_targeted_policy")
        result["validation_decision"] = decision
        result["validation_guardrail"] = guardrail
        result["validation_truth_policy_value"] = float(selected["value_cny_per_user"].iloc[0])
    return result


# --------------------------------------------------------------------------- #
# 单 rep 入口
# --------------------------------------------------------------------------- #
def _git_commit(root: Path) -> str | None:
    head = root / ".git"
    if not head.exists():
        return None
    try:
        ref = (head / "HEAD").read_text(encoding="utf-8").strip()
        if ref.startswith("ref: "):
            target = head / ref.split(" ", 1)[1]
            if target.is_file():
                return target.read_text(encoding="utf-8").strip()[:12]
            packed = head / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(ref.split(" ", 1)[1]):
                        return line.split(" ", 1)[0][:12]
            return None
        return ref[:12]
    except OSError:
        return None


def _snapshot_hashes(directory: Path) -> dict[str, str]:
    """与 ``pipeline_source_hashes`` 同构，但根指向快照目录。"""
    files = sorted(
        set((directory / "src" / "causal_growth").rglob("v3*.py"))
        | set((directory / "sql").glob("v3*.sql"))
        | set((directory / "configs").glob("v3*.yaml"))
        | set((directory / "configs" / "v3").glob("*.yaml"))
    )
    hashed = {}
    for path in files:
        hashed[path.relative_to(directory).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return hashed


def create_snapshot(destination: str | Path, *, source_root: str | Path | None = None) -> dict[str, Any]:
    """把 ``src/ sql/ configs/`` 字节复制成快照并返回绑定；正式跑靠它只读。"""
    source = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[3]
    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"快照目录已存在，拒绝覆盖：{dest}")
    dest.mkdir(parents=True)
    for name in ("src", "sql", "configs"):
        shutil.copytree(
            source / name, dest / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    hashes = _snapshot_hashes(dest)
    payload = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    binding = {
        "kind": "byte_snapshot",
        "path": dest.as_posix(),
        "n_files": len(hashes),
        "source_hashes": hashes,
        "source_hashes_sha256": hashlib.sha256(payload).hexdigest(),
        "git_commit": _git_commit(source),
        "note": "正式跑必须 PYTHONPATH 指向本快照；run_g_rep 会拒绝漂移",
    }
    (dest / "snapshot_binding.json").write_text(
        json.dumps(binding, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return binding


def live_binding(source_hashes: Mapping[str, str]) -> dict[str, Any]:
    """没有快照时的绑定记录；仍然绑定本次实跑的源码字节。"""
    payload = json.dumps(dict(source_hashes), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "kind": "live_tree",
        "n_files": len(source_hashes),
        "source_hashes_sha256": hashlib.sha256(payload).hexdigest(),
        "git_commit": _git_commit(Path(__file__).resolve().parents[3]),
        "note": "工程/试点运行；正式跑必须换成 byte_snapshot",
    }


def _hash_without_run_id(observations: pd.DataFrame) -> str:
    if "run_id" not in observations.columns:
        return dataframe_sha256(observations)
    return dataframe_sha256(observations.drop(columns=["run_id"]))


def run_g_rep(
    protocol: V3Protocol,
    cell_id: str,
    rep: int,
    *,
    out_dir: str | Path,
    n: int | None = None,
    plan: BudgetPlan | None = None,
    status: str = "engineering",
    formal_approval: str | None = None,
    models: Sequence[str] | None = None,
    policy: str = "greedy_incremental_profit_per_cost",
    time_mode: str = "static",
    with_learning: bool = True,
    with_validation: bool = True,
    bootstrap_resamples: int = 0,
    bootstrap_budget_scope: str | None = None,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """跑一个 (cell, rep)：历史数据只建一次，ATE 与学习共用它。"""
    if status not in _STATUSES:
        raise ValueError(f"未注册的状态：{status!r}")
    if status == "formal" and not formal_approval:
        raise ValueError("正式 G 运行必须带用户批准的 formal_approval 登记号")
    plan = plan or load_budget_plan(protocol)
    spec = plan_cell(protocol, cell_id, plan)
    cfg = protocol.scenario(cell_id)
    require_job_semantics(cfg)
    rep = int(rep)
    n = int(spec["n"] if n is None else n)
    if status == "formal" and n != int(spec["n"]):
        raise ValueError("正式运行的 n 必须等于注册 n")
    if int(bootstrap_resamples) > 0 and rep != 0:
        raise ValueError(
            "固定策略 bootstrap 只允许在代表 rep（0）上运行；其他 rep 用预设影响函数区间"
        )
    require_bootstrap_scope(status, int(bootstrap_resamples), bootstrap_budget_scope)
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    run_id = f"g:{cell_id}:{spec['block']}:rep{rep}"

    started = time.process_time()
    dataset, build_info, source_before = build_history_dataset(
        cfg, rep_id=rep, n=n, run_id=run_id
    )
    pipeline_seconds = time.process_time() - started
    history_builds = 1
    if snapshot is not None:
        if dict(snapshot["source_hashes"]) != source_before:
            raise RuntimeError(
                f"{SOURCE_CHANGED_MARKER}: 当前树与快照绑定不一致，拒绝把结果登记为快照运行"
            )

    estimate_started = time.process_time()
    ate = estimate_ate(dataset, cfg)
    estimate_seconds = time.process_time() - estimate_started

    learning_prefix = bool(with_learning and rep < int(spec["R_learn"]))
    fit: HistoryFit | None = None
    model_seconds = 0.0
    needs_fit = learning_prefix or bool(with_validation and rep < int(spec["R_validation"]))
    if needs_fit:
        model_started = time.process_time()
        fit = fit_history_models(
            dataset, cfg, rep_id=rep, models=models, time_mode=time_mode
        )
        model_seconds = time.process_time() - model_started

    validation: dict[str, Any] | None = None
    validation_builds = 0
    if with_validation and rep < int(spec["R_validation"]):
        if fit is None:
            raise RuntimeError("验证臂需要历史拟合结果，但本 rep 未拟合")
        validation_started = time.process_time()
        validation = run_validation_arm(
            fit, cfg, rep_id=rep, n_validation=n, policy=policy,
            target_dir=target / "validation",
            bootstrap_resamples=int(bootstrap_resamples),
        )
        validation_builds = 1
        model_seconds += time.process_time() - validation_started

    row: dict[str, Any] = {
        "cell_id": cell_id,
        "scenario_id": cell_id,
        "level": spec["level"],
        "tier": spec["tier"],
        "block": spec["block"],
        "rep": rep,
        "n": n,
        "treatment_share": spec["treatment_probability"],
        **ate,
        "learning_prefix": learning_prefix,
        "chosen_model": fit.chosen_model if fit is not None else "",
        "preprocessor_hash": fit.preprocessor_hash if fit is not None else "",
        "split_fingerprint": fit.split_fingerprint if fit is not None else "",
        "config_hash": cfg.hash(64),
        "protocol_config_hash": protocol.config_hash,
        "observed_hash": dataset.content_hash,
        "observed_hash_without_run_id": _hash_without_run_id(dataset.observations),
        "overlay_source": plan.source,
        "overlay_sha256": plan.sha256 or "",
        "cpu_seconds_pipeline": pipeline_seconds,
        "cpu_seconds_estimate": estimate_seconds,
        "cpu_seconds_models": model_seconds,
        "history_pipeline_builds": history_builds,
        "validation_pipeline_builds": validation_builds,
        "validation_n": validation["validation_n"] if validation else 0,
        "validation_targeted_n": validation["validation_targeted_n"] if validation else 0,
        "validation_random_n": validation["validation_random_n"] if validation else 0,
        "validation_predicted_spend_per_user": (
            validation["validation_predicted_spend_per_user"] if validation else float("nan")
        ),
        "validation_budget_per_user": (
            validation["validation_budget_per_user"] if validation else float("nan")
        ),
        "validation_freeze_hash": validation["validation_freeze_hash"] if validation else "",
        "validation_observed_hash": validation["validation_observed_hash"] if validation else "",
        "validation_bootstrap_resamples": _bootstrap_scalar(validation, "resamples", 0),
        "validation_bootstrap_point_diff": _bootstrap_scalar(validation, "point_diff"),
        "validation_bootstrap_se": _bootstrap_scalar(validation, "bootstrap_se"),
        "validation_bootstrap_ci_low": _bootstrap_scalar(validation, "ci_low"),
        "validation_bootstrap_ci_high": _bootstrap_scalar(validation, "ci_high"),
        "validation_fixed_bootstrap": (
            validation["validation_fixed_bootstrap"] if validation else None
        ),
        "status": status,
        "provisional": status != "formal",
    }
    for name in MODEL_NAMES:
        prediction = None if fit is None else fit.predictions.get(name)
        row[f"model_{name}_tau_mean"] = (
            float(np.mean(prediction.tau_test)) if prediction is not None else float("nan")
        )
        row[f"model_{name}_tau_sd"] = (
            float(prediction.tau_sd_test) if prediction is not None else float("nan")
        )

    binding = dict(snapshot) if snapshot is not None else live_binding(source_before)
    manifest = {
        "phase": "G_matrix_report",
        "run_id": run_id,
        "cell_id": cell_id,
        "scenario_id": cell_id,
        "block": spec["block"],
        "rep_range": [rep, rep],
        "n": n,
        "status": status,
        "formal_approval": formal_approval,
        "R_ate": int(spec["R_ate"]),
        "R_learn": int(spec["R_learn"]),
        "R_validation": int(spec["R_validation"]),
        "learning_prefix": learning_prefix,
        "job_semantics": require_job_semantics(cfg),
        "source_hashes_before": source_before,
        "source_hashes_after": pipeline_source_hashes(),
        "sql_sha256": dataset.sql_sha256,
        "config_hash": cfg.hash(64),
        "data_config_hash": dataset.data_config_hash,
        "protocol_config_hash": protocol.config_hash,
        "snapshot_binding": binding,
        "budget_plan": plan.describe(),
        "history_pipeline_builds": history_builds,
        "validation_pipeline_builds": validation_builds,
        "n_users": build_info["n_users"],
        "n_orders": build_info["n_orders"],
        "observed_hash": dataset.content_hash,
        "observed_hash_without_run_id": row["observed_hash_without_run_id"],
        "selected_model": row["chosen_model"],
        "selected_policy": policy if validation else "",
        "freeze_hash": row["validation_freeze_hash"],
        "fixed_bootstrap_resamples": int(bootstrap_resamples),
        "fixed_bootstrap_scope": (
            "representative_rep_primary_budget_only" if int(bootstrap_resamples) > 0 else "not_run"
        ),
        "fixed_bootstrap_budget_scopes": bootstrap_budget_scopes(protocol, int(bootstrap_resamples)),
        "fixed_bootstrap": validation["validation_fixed_bootstrap"] if validation else None,
        "truth_columns_present": False,
        "truth_unlock_order": "policy_list_written_then_truth_audit",
        "cpu_seconds": {
            "pipeline": pipeline_seconds,
            "estimate": estimate_seconds,
            "models": model_seconds,
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (target / "row.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    row["_manifest"] = manifest
    return row


# --------------------------------------------------------------------------- #
# 逐 rep 表的字节级读写、续跑与多根合并
# --------------------------------------------------------------------------- #
def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return repr(value)
    if isinstance(value, (np.floating,)):
        return _format_cell(float(value))
    if isinstance(value, (np.integer,)):
        return str(int(value))
    if isinstance(value, (np.bool_,)):
        return "True" if bool(value) else "False"
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def write_repetition_rows(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    """定列序、定浮点表示、LF 行尾；续跑读回原字符串即可逐字节复现。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = row_columns()
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in sorted(rows, key=lambda item: int(item["rep"])):
            missing = [column for column in columns if column not in row]
            if missing:
                raise ValueError(f"逐 rep 行缺少列：{missing}")
            writer.writerow([_format_cell(row[column]) for column in columns])
    return target


def read_repetition_rows(path: str | Path) -> list[dict[str, str]]:
    """按原字符串读回；用于续跑时的字节级不动前缀。"""
    target = Path(path)
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = row_columns()
        if tuple(reader.fieldnames or ()) != expected:
            raise ValueError(
                f"{target} 的表头与当前驱动不一致；拒绝把不同格式拼在一起"
            )
        return [dict(row) for row in reader]


def _int_value(row: Mapping[str, Any], key: str) -> int:
    return int(float(row[key]))


def run_cell(
    protocol: V3Protocol,
    cell_id: str,
    *,
    out_root: str | Path,
    reps: Sequence[int],
    status: str = "engineering",
    formal_approval: str | None = None,
    plan: BudgetPlan | None = None,
    n: int | None = None,
    models: Sequence[str] | None = None,
    policy: str = "greedy_incremental_profit_per_cost",
    with_learning: bool = True,
    with_validation: bool = True,
    bootstrap_resamples: int = 0,
    bootstrap_budget_scope: str | None = None,
    snapshot: Mapping[str, Any] | None = None,
    resume_from: str | Path | None = None,
    target_reps: int,
) -> dict[str, Any]:
    """跑一个格的若干 rep；已完成的 rep 不重跑，参数漂移直接拒绝。

    未跑满 ``target_reps`` 时只写 ``repetitions_provisional.csv``，不占正式路径
    （任务书 §6.3 / A5）。
    """
    if status == "formal" and not formal_approval:
        raise ValueError("正式 G 运行必须带 formal_approval")
    require_bootstrap_scope(status, int(bootstrap_resamples), bootstrap_budget_scope)
    plan = plan or load_budget_plan(protocol)
    spec = plan_cell(protocol, cell_id, plan)
    cell_dir = Path(out_root) / cell_id
    cell_dir.mkdir(parents=True, exist_ok=True)
    formal_path = cell_dir / "repetitions.csv"
    provisional_path = cell_dir / "repetitions_provisional.csv"
    state_path = cell_dir / "run_state.json"
    expected_n = int(spec["n"] if n is None else n)

    existing: list[dict[str, Any]] = []
    resume_path = Path(resume_from) if resume_from is not None else None
    if resume_path is not None and resume_path.is_file():
        existing = read_repetition_rows(resume_path)
    elif resume_path is not None:
        raise FileNotFoundError(f"续跑文件不存在：{resume_path}")

    if existing:
        first = existing[0]
        drifted = []
        if str(first["cell_id"]) != cell_id:
            drifted.append(f"cell_id {first['cell_id']} != {cell_id}")
        if _int_value(first, "n") != expected_n:
            drifted.append(f"n {first['n']} != {expected_n}")
        if str(first["config_hash"]) != protocol.scenario(cell_id).hash(64):
            drifted.append("config_hash 漂移")
        if str(first["protocol_config_hash"]) != protocol.config_hash:
            drifted.append("protocol_config_hash 漂移")
        if int(first["tier"]) == 1 and _int_value(first, "rep") >= int(spec["R_ate"]):
            drifted.append("已有 rep 超出当前 R_ate")
        if any(
            _int_value(row, "validation_bootstrap_resamples") != int(bootstrap_resamples)
            for row in existing
        ):
            drifted.append("bootstrap_resamples 与已有结果不一致")
        if drifted:
            raise ValueError(f"续跑参数与已有结果不一致，拒绝拼接：{drifted}")

    done = {_int_value(row, "rep") for row in existing}
    for rep in reps:
        rep = int(rep)
        if rep < 0 or rep >= int(spec["R_ate"]):
            raise ValueError(f"rep {rep} 超出 R_ate={spec['R_ate']}；未跑满不得扩批")
        if rep in done:
            continue
        run_g_rep(
            protocol, cell_id, rep,
            out_dir=cell_dir / f"rep{rep}",
            n=expected_n, plan=plan, status=status,
            formal_approval=formal_approval, models=models, policy=policy,
            with_learning=with_learning, with_validation=with_validation,
            bootstrap_resamples=int(bootstrap_resamples),
            bootstrap_budget_scope=bootstrap_budget_scope,
            snapshot=snapshot,
        )
        row = json.loads((cell_dir / f"rep{rep}" / "row.json").read_text(encoding="utf-8"))
        existing.append({column: _format_cell(row[column]) for column in row_columns()})
        done.add(rep)

    existing.sort(key=lambda item: _int_value(item, "rep"))
    completed = len(existing)
    provisional = completed < int(target_reps) or status != "formal"
    out_path = provisional_path if provisional else formal_path
    write_repetition_rows(out_path, existing)
    telemetry: list[dict[str, Any]] = []
    for row in existing:
        rep = _int_value(row, "rep")
        row_path = cell_dir / f"rep{rep}" / "row.json"
        if not row_path.is_file():
            continue
        payload = json.loads(row_path.read_text(encoding="utf-8"))
        telemetry.append({column: payload.get(column, "") for column in TELEMETRY_COLUMNS})
    telemetry_path = cell_dir / "repetitions_telemetry.csv"
    with telemetry_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TELEMETRY_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for payload in telemetry:
            writer.writerow({column: _format_cell(payload[column]) for column in TELEMETRY_COLUMNS})
    state = {
        "phase": "G_matrix_cell",
        "cell_id": cell_id,
        "block": spec["block"],
        "status": status,
        "formal_approval": formal_approval,
        "target_reps": int(target_reps),
        "R_ate": int(spec["R_ate"]),
        "R_learn": int(spec["R_learn"]),
        "R_validation": int(spec["R_validation"]),
        "n": expected_n,
        "fixed_bootstrap_resamples": int(bootstrap_resamples),
        "fixed_bootstrap_scope": (
            "representative_rep_primary_budget_only" if int(bootstrap_resamples) > 0 else "not_run"
        ),
        "fixed_bootstrap_budget_scopes": bootstrap_budget_scopes(protocol, int(bootstrap_resamples)),
        "config_hash": protocol.scenario(cell_id).hash(64),
        "protocol_config_hash": protocol.config_hash,
        "completed_reps": [_int_value(row, "rep") for row in existing],
        "rows": completed,
        "provisional": bool(provisional),
        "budget_plan": plan.describe(),
        "snapshot_binding": dict(snapshot) if snapshot is not None else None,
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "cell_id": cell_id,
        "rows_path": str(out_path),
        "rows": completed,
        "provisional": bool(provisional),
        "state_path": str(state_path),
    }


def merge_roots(
    roots: Sequence[str | Path],
    *,
    block: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """读**全部** run-root 并按 ``[scenario_id, block, rep]`` 去重。

    键相同但内容不同即冲突，直接失败；键相同且内容相同算重复行，计数后丢弃。
    只读一个根会得到"看起来正常"的少一半样本（任务书 §6.2）。
    """
    key = ("scenario_id", "block", "rep")
    seen: dict[tuple[str, str, str], dict[str, str]] = {}
    rows_raw = 0
    duplicates = 0
    roots_used: list[str] = []
    for root in roots:
        root_path = Path(root)
        candidates = sorted(root_path.glob("*/repetitions.csv")) + sorted(
            root_path.glob("*/repetitions_provisional.csv")
        )
        if not candidates:
            continue
        roots_used.append(root_path.as_posix())
        for path in candidates:
            if path.name == "repetitions_provisional.csv" and (path.parent / "repetitions.csv").is_file():
                continue
            for row in read_repetition_rows(path):
                if block is not None and str(row["block"]) != block:
                    continue
                rows_raw += 1
                identity = (str(row["scenario_id"]), str(row["block"]), str(row["rep"]))
                previous = seen.get(identity)
                if previous is None:
                    seen[identity] = row
                elif previous == row:
                    duplicates += 1
                else:
                    raise ValueError(f"同一键 {identity} 在不同根里内容不同，拒绝合并")
    if not seen:
        raise ValueError(f"在 {[str(root) for root in roots]} 下没有找到逐 rep 表")
    merged = sorted(
        seen.values(),
        key=lambda row: (str(row["scenario_id"]), str(row["block"]), _int_value(row, "rep")),
    )
    report = {
        "roots": roots_used,
        "rows_raw": rows_raw,
        "rows_deduped": len(merged),
        "duplicates_removed": duplicates,
        "key": list(key),
    }
    return merged, report


def summarize_repetitions(
    rows: Sequence[Mapping[str, Any]],
    *,
    provisional: bool,
) -> pd.DataFrame:
    """按 (cell_id, block, metric) 汇总，每格都给 ``R`` 与 ``MC_SE``（A7）。"""
    if not rows:
        raise ValueError("没有可汇总的逐 rep 行")
    keys = ("cell_id", "block", "level", "tier")
    records: list[dict[str, Any]] = []
    first_by_cell: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        first_by_cell.setdefault((str(row["cell_id"]), str(row["block"])), row)
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["cell_id"]), str(row["block"])), []).append(row)
    for (cell_id, block), group in sorted(grouped.items()):
        head = first_by_cell[(cell_id, block)]
        for metric in SUMMARY_METRICS:
            values = [
                float(row[metric]) for row in group
                if str(row.get(metric, "")) not in {"", "nan"}
            ]
            count = len(values)
            if count == 0:
                continue
            mean = float(np.mean(values))
            sd = float(np.std(values, ddof=1)) if count > 1 else float("nan")
            mc_se = sd / math.sqrt(count) if count > 1 else float("nan")
            records.append({
                "cell_id": cell_id,
                "block": block,
                "level": head["level"],
                "tier": int(head["tier"]),
                "metric": metric,
                "R": count,
                "MC_SE": mc_se,
                "sd": sd,
                "mean": mean,
                "provisional": bool(provisional),
            })
    return pd.DataFrame(records)


def write_summary_table(
    rows: Sequence[Mapping[str, Any]],
    path: str | Path,
    *,
    provisional: bool,
) -> Path:
    """汇总表落 ``outputs/tables/``（utf-8-sig）；未跑满用 ``_provisional`` 后缀。"""
    target = Path(path)
    if provisional:
        target = target.with_name(f"{target.stem}_provisional{target.suffix}")
    table = summarize_repetitions(rows, provisional=provisional)
    target.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(target, index=False, encoding="utf-8-sig")
    return target
