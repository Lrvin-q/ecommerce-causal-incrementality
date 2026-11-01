"""合成数据 / 已知 DGP：只消费 SQL 观测用户表的拆分与滚动成熟门禁。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from causal_growth.config import Config, ConfigError
from causal_growth.rng import child_rng


_ROLES = ("train", "validation", "test")
_KEYS = ("run_id", "user_id")


def require_historical_training_input(frame: pd.DataFrame) -> None:
    """阻止独立政策验证与诊断快照被改名为历史训练或重新划分。

    同时检查来源属性和政策臂列，不把 split 字符串当作队列来源证明。
    冻结预处理的 transform 不调用此门禁，仍可服务独立验证的新 X。
    """
    if frame.attrs.get("population_kind") == "validation":
        raise ValueError("独立政策验证队列不得用于训练或历史重新拆分")
    if "population_kind" in frame and frame.population_kind.eq("validation").any():
        raise ValueError("独立政策验证队列不得用于训练或历史重新拆分")
    if "assigned_policy_arm" in frame and frame.assigned_policy_arm.notna().any():
        raise ValueError("存在独立政策验证臂，不得用于历史训练或重新拆分")
    if bool(frame.attrs.get("diagnostic_snapshot", False)):
        raise ValueError("诊断快照不得用于训练或历史重新拆分")
    if "diagnostic_snapshot" in frame and frame.diagnostic_snapshot.fillna(False).astype(bool).any():
        raise ValueError("诊断快照不得用于训练或历史重新拆分")


def _validate_users(frame: pd.DataFrame) -> None:
    if not set(_KEYS).issubset(frame):
        raise ValueError("观测表缺少 run_id/user_id 用户键")
    if frame[list(_KEYS)].isna().any().any() or frame.duplicated(list(_KEYS)).any():
        raise ValueError("用户键不能为空或重复；拆分单位为 run_id+user_id")


def user_key_hash(frame: pd.DataFrame) -> str:
    """给观测用户键集合生成可持久化指纹，供跨模型共享拆分与成熟训练核对。"""
    _validate_users(frame)
    pairs = sorted((str(run), str(user)) for run, user in frame[list(_KEYS)].itertuples(index=False, name=None))
    return hashlib.sha256(json.dumps(pairs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SplitResult:
    """每位观测用户恰有一个角色，manifest 记录种子和实际人数。"""

    assignments: pd.DataFrame
    manifest: dict[str, Any]


@dataclass(frozen=True)
class RollingSplitResult:
    """截止时点可训练用户、当前测试周用户及排除原因计数。"""

    train_user_keys: pd.DataFrame
    evaluation_user_keys: pd.DataFrame
    manifest: dict[str, Any]


def _allocate_total(n: int, fractions: np.ndarray) -> np.ndarray:
    expected = fractions * n
    counts = np.floor(expected).astype(np.int64)
    remainder = n - int(counts.sum())
    order = np.argsort(-(expected - counts), kind="stable")
    counts[order[:remainder]] += 1
    return counts


def _allocate_strata(counts: np.ndarray, target: int) -> np.ndarray:
    if target == 0:
        return np.zeros_like(counts)
    if target < 0 or target > counts.sum():
        raise ValueError("分层目标人数超出剩余用户数")
    return _allocate_with_weights(counts, target)


def _allocate_with_weights(counts: np.ndarray, target: int) -> np.ndarray:
    expected = counts * (target / counts.sum())
    allocated = np.floor(expected).astype(np.int64)
    order = np.argsort(-(expected - allocated), kind="stable")
    allocated[order[:target - int(allocated.sum())]] += 1
    if np.any(allocated > counts):
        raise ArithmeticError("分层整数分配超过层内人数")
    return allocated


def assign_user_splits(
    observed: pd.DataFrame, cfg: Config, *, master_seed: int, stream: str, index: int = 0,
) -> SplitResult:
    """回答训练/验证/测试如何无交叉覆盖：非时间场景分层，L2按冻结周次。

    仅读取用户键、冻结分层字段与入组周次；不使用利润、核销或任何真值。
    同一用户键集合与种子不因输入行顺序或后续模型选择而改变角色。
    """
    require_historical_training_input(observed)
    _validate_users(observed)
    fractions = np.array([cfg.require(f"design.split.{role}") for role in _ROLES], dtype=float)
    if np.any(fractions < 0) or not np.isclose(fractions.sum(), 1):
        raise ConfigError("拆分比例必须非负且合计为 1")
    assigned = observed[list(_KEYS)].copy().reset_index(drop=True)
    labels = np.empty(len(observed), dtype=object)
    source = observed.reset_index(drop=True)
    temporal = cfg.require("active_scenario.level") == "L2"
    if temporal:
        if "assignment_week" not in source:
            raise ValueError("L2 拆分缺少 assignment_week")
        role_map = {week: role for role in _ROLES for week in cfg.require(f"design.temporal.{role}_weeks")}
        weeks = source.assignment_week
        if weeks.isna().any() or not set(weeks).issubset(role_map):
            raise ValueError("L2 存在未注册入组周次")
        if len(role_map) != sum(len(cfg.require(f"design.temporal.{role}_weeks")) for role in _ROLES):
            raise ConfigError("L2 训练/验证/测试周次发生交叉")
        labels[:] = weeks.map(role_map).to_numpy()
    else:
        strata = list(cfg.require("design.split.random_split_stratify_on"))
        if not set(strata).issubset(source) or source[strata].isna().any().any():
            raise ValueError("冻结分层字段缺失或为空")
        if not source.treatment.isin([0, 1]).all():
            raise ValueError("treatment 必须是实际日志记录的二元分配标签")
        for run, run_rows in source.groupby("run_id", sort=True):
            groups = list(run_rows.groupby(strata, sort=True, dropna=False))
            counts = np.array([len(group) for _, group in groups], dtype=np.int64)
            target = _allocate_total(len(run_rows), fractions)
            train_counts = _allocate_strata(counts, int(target[0]))
            validation_counts = _allocate_strata(counts - train_counts, int(target[1]))
            for group_index, (key, group) in enumerate(groups):
                key_text = json.dumps([str(run), list(key) if isinstance(key, tuple) else [key]],
                                      ensure_ascii=False, separators=(",", ":"), default=str)
                ordered = group.assign(_stable_user_key=group.user_id.astype(str)).sort_values("_stable_user_key", kind="stable").index.to_numpy()
                permuted = child_rng(master_seed, f"{stream}.split.{key_text}", index).permutation(ordered)
                end_train = int(train_counts[group_index])
                end_validation = end_train + int(validation_counts[group_index])
                labels[permuted[:end_train]] = "train"
                labels[permuted[end_train:end_validation]] = "validation"
                labels[permuted[end_validation:]] = "test"
    assigned["split"] = labels
    if not assigned.split.isin(_ROLES).all() or len(assigned) != len(observed):
        raise ArithmeticError("拆分没有完整覆盖全部用户")
    manifest = {
        "source": "合成数据 / 已知 DGP", "method": "frozen_calendar_weeks" if temporal else "stratified_hamilton_counts",
        "seed": master_seed, "stream": stream, "index": index,
        "config_hash": cfg.hash(length=64), "user_key_hash": user_key_hash(assigned),
        "counts": {role: int((labels == role).sum()) for role in _ROLES},
        "run_counts": assigned.groupby(["run_id", "split"]).size().rename("n").reset_index().to_dict("records"),
    }
    manifest["split_hash"] = hashlib.sha256(assigned.sort_values(list(_KEYS)).to_csv(index=False).encode("utf-8")).hexdigest()
    if not temporal:
        diagnostics = source[["run_id", *strata]].copy()
        diagnostics["split"] = labels
        manifest["strata_counts"] = diagnostics.groupby(["run_id", *strata, "split"]).size().rename("n").reset_index().to_dict("records")
    return SplitResult(assigned, manifest)


def rolling_training_candidates(
    observed: pd.DataFrame, cfg: Config, *, origin_week: int,
    ingestion_day_column: str = "required_ingestion_day",
    completeness_day_column: str = "complete_after_day",
) -> RollingSplitResult:
    """回答滚动起点能看到哪些训练结果；原验证用户始终留作验证。

    SQL 必须提供每用户30天核算必需记录的最晚入库日，以及覆盖最大延迟的
    完整性保障时点；只看到已到记录不证明没有迟到事件。返回键不重写原
    split，不混入当前或未来测试周。
    """
    require_historical_training_input(observed)
    _validate_users(observed)
    if cfg.require("active_scenario.level") != "L2":
        raise ConfigError("滚动时间门禁只适用于 L2")
    if origin_week not in cfg.require("design.temporal.rolling_origin_weeks"):
        raise ConfigError("滚动起点不在冻结清单中")
    required = {"split", "assignment_day", "assignment_week", ingestion_day_column, completeness_day_column}
    if not required.issubset(observed):
        raise ValueError(f"滚动门禁缺少 {sorted(required - set(observed))}")
    if not observed.split.isin(_ROLES).all():
        raise ValueError("必须先完成训练/验证/测试角色分配")
    cutoff = (origin_week - 1) * float(cfg.require("design.temporal.days_per_week"))
    times = observed[["assignment_day", "assignment_week", ingestion_day_column, completeness_day_column]].to_numpy(dtype=float)
    if not np.isfinite(times).all():
        raise ValueError("成熟与入库时点必须已知且有限")
    past = (observed.assignment_day < cutoff) & (observed.assignment_week < origin_week)
    mature = observed.assignment_day + float(cfg.require("windows.profit_days")) <= cutoff
    arrived = observed[ingestion_day_column] <= cutoff
    complete = observed[completeness_day_column] <= cutoff
    eligible_role = observed.split.isin(["train", "test"])
    train = past & mature & arrived & complete & eligible_role
    evaluation = (observed.assignment_week == origin_week) & (observed.split == "test")
    train_keys = observed.loc[train, list(_KEYS)].copy()
    evaluation_keys = observed.loc[evaluation, list(_KEYS)].copy()
    manifest = {
        "source": "合成数据 / 已知 DGP", "origin_week": origin_week, "cutoff_day": cutoff,
        "selection_method": "past_mature_ingested_train_or_prior_test_validation_held_out",
        "source_kind": "sql_observed",
        "source_path": str(observed.attrs["source_path"]) if observed.attrs.get("source_path") is not None else None,
        "train_n": int(train.sum()), "evaluation_n": int(evaluation.sum()),
        "excluded_validation_n": int((~eligible_role).sum()),
        "excluded_future_or_current_n": int((eligible_role & ~past).sum()),
        "excluded_immature_n": int((eligible_role & past & ~mature).sum()),
        "excluded_not_ingested_n": int((eligible_role & past & mature & ~arrived).sum()),
        "excluded_completeness_not_guaranteed_n": int((eligible_role & past & mature & arrived & ~complete).sum()),
        "train_user_key_hash": user_key_hash(train_keys),
        "ingestion_day_column": ingestion_day_column, "config_hash": cfg.hash(length=64),
        "completeness_day_column": completeness_day_column,
    }
    return RollingSplitResult(train_keys, evaluation_keys, manifest)
