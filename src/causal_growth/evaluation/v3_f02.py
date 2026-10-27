"""F02 独立三臂随机验证：冻结策略 → 新用户分配 → 五表/SQL → 全臂 ITT → 审计。

回答哪个问题
------------
D03 在历史数据上选出一个模型，E 在它之上选出一个策略。这个策略**在从未参与
训练的新用户上**是否真的创造收益？本模块为每个 rep 额外生成 20 万新用户
（``independent_validation_is_extra_population``），按冻结概率随机分入三臂：

- ``no_coupon``：不发券；
- ``random_same_budget``：同一每用户预算下随机发券；
- ``selected_targeted_policy``：按 D03 选中的模型与冻结策略规则选人发券。

三臂的分母都是**被分配到该臂的全部用户**（全臂 ITT），不是成功支付/核销用户。

冻结与审计顺序
--------------
1. 用历史训练切分拟合 D03 选中模型（同一 ``seed_index``），并冻结其在新用户上的
   ``tau_hat/cost_hat``；
2. 冻结策略名单与三臂动作；
3. 生成事实订单、执行五表清洗与 SQL，计算**观测**全臂 ITT；
4. 把观测汇总与逐用户记录写成 ``freeze_hash``；
5. **之后**才允许读取 ``audit_*`` 世界账本，计算真值审计。

第 5 步之前任何真值列都不存在；``audit_policy_values`` 是唯一读真值的入口。

预算口径
--------
每个活跃臂按 ``evaluation.independent_validation.primary_budget_cny_per_user``
（0.2 元）乘以**该臂分配人数**冻结发券名单：定向臂在臂内按冻结策略选人，随机臂在
臂内随机装填，对照臂不发。这对应配置的
``budget_basis: same_per_assigned_user_in_each_active_arm``，因此每个臂的实际预测
支出都以臂内预算为上限（容差内）。
另算两张**全队列交付**名单（同样 0.2 元/人）只用于冻结后的审计价值对照，不参与
交付，也不参与任何选择；它们回答"如果策略部署到全部目标用户"的真值。

代表 rep
--------
``validation.representative_rep``（当前为 0）在给出 ``out_dir`` 时会额外把完整五表与
SQL 写到 ``out_dir/five_tables/``，并在 manifest 记录其 manifest 路径与 sha256；
其他 rep 只保留逐用户名单、汇总与 manifest。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from causal_growth.config import Config
from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_pipeline import build_observed_pipeline, pipeline_source_hashes
from causal_growth.data.v3_quality import validate_tables
from causal_growth.data.v3_sql import run_sql_pipeline
from causal_growth.data.v3_storage import dataframe_sha256, file_sha256
from causal_growth.data.v3_tables import build_raw_tables
from causal_growth.dgp.v3_engine import (
    audit_realized_worlds,
    generate_covariates,
    generate_v3_population,
)
from causal_growth.estimate.v3_models import (
    _d03_rep_artifacts,
    _fit_level_baselines,
    _fit_learner,
    _observations_for_keys,
)
from causal_growth.policy import v3_policy as pol
from causal_growth.policy.v3_policy import predict_expected_cost
from causal_growth.policy.v3_policy_grid import POLICIES, run_policy
from causal_growth.rng import child_rng
from causal_growth.v3_data_config import load_v3_data_config

ARMS: tuple[str, ...] = (
    "no_coupon",
    "random_same_budget",
    "selected_targeted_policy",
)
TARGETED_ARM = "selected_targeted_policy"
RANDOM_ARM = "random_same_budget"
CONTROL_ARM = "no_coupon"
EXCLUDED_POLICIES = ("no_coupon", "all_coupon_unconstrained_reference")
SCORE_COLUMNS: tuple[str, ...] = (
    "user_id", "is_new", "cart_value", "purchase_propensity",
    "predicted_profit", "tau_hat", "cost_hat",
)
PER_USER_COLUMNS: tuple[str, ...] = (
    "run_id", "user_id", "assigned_policy_arm", "issued_action",
    "selected_policy_id", "observed_net_profit", "observed_coupon_cost",
)
ARM_SUMMARY_COLUMNS: tuple[str, ...] = (
    "arm", "n_assigned", "n_issued", "issue_share",
    "mean_net_profit_cny", "se_net_profit_cny",
    "mean_coupon_cost_cny", "total_coupon_cost_cny",
)
CONTRAST_COLUMNS: tuple[str, ...] = (
    "contrast", "diff_cny_per_user", "se", "ci_low", "ci_high",
    "two_sided_p_value", "n_left", "n_right",
)
AUDIT_COLUMNS: tuple[str, ...] = (
    "run_id", "user_id", "assigned_policy_arm", "issued_action",
    "tau_true", "cost_true",
)


@dataclass(frozen=True)
class ScoredCohort:
    """新用户上的冻结打分（无真值）。"""

    frame: pd.DataFrame
    model: str
    policy: str
    preprocessor_hash: str

    @property
    def n(self) -> int:
        return int(len(self.frame))


@dataclass(frozen=True)
class F02Result:
    """单 rep 的三臂验证产物；``audit`` 只在冻结后生成。"""

    scenario: str
    rep_id: int
    n: int
    model: str
    policy: str
    assignment: pd.DataFrame
    dataset: ObservedDataset
    per_user: pd.DataFrame
    arm_summary: pd.DataFrame
    contrasts: pd.DataFrame
    audit_users: pd.DataFrame
    audit_policy: pd.DataFrame
    audit_contrasts: pd.DataFrame
    freeze_hash: str
    manifest: dict[str, Any]


def _require_policy_name(name: str) -> str:
    if name not in POLICIES:
        raise ValueError(f"未注册的策略名 {name!r}")
    if name in EXCLUDED_POLICIES:
        raise ValueError(f"{name!r} 不是可执行的定向策略，不能进入三臂验证")
    return name


def draw_policy_arms(
    n: int, cfg: Config, *, rep_id: int
) -> np.ndarray:
    """按冻结的三臂概率抽取分配标签；不读取任何结果变量。"""
    arms = tuple(str(value) for value in cfg.require("evaluation.independent_validation.arms"))
    probabilities = np.asarray(
        cfg.require("evaluation.independent_validation.arm_probabilities"), dtype=float
    )
    if arms != ARMS:
        raise ValueError(f"三臂名称与实现不一致：{arms}")
    if probabilities.shape != (len(arms),) or not np.isclose(probabilities.sum(), 1.0):
        raise ValueError("三臂概率必须和为 1")
    if int(n) < 30:
        raise ValueError("三臂验证的用户数过少，无法保证每臂非空")
    rng = child_rng(
        int(cfg.require("project.master_seed")), "f02.arms", int(rep_id)
    )
    indices = rng.choice(len(arms), size=int(n), p=probabilities)
    labels = np.asarray(arms, dtype=object)[indices]
    counts = {arm: int((labels == arm).sum()) for arm in arms}
    if any(value == 0 for value in counts.values()):
        raise ValueError(f"三臂抽样出现空臂：{counts}")
    return labels


def score_validation_users(
    rep: Any,
    users: pd.DataFrame,
    cfg: Config,
    *,
    seed_index: int,
) -> ScoredCohort:
    """用历史训练状态给新用户打分；只产选人列，不读真值。

    ``rep`` 是 :func:`_d03_rep_artifacts` 的返回值。模型在同一训练切分上按同一
    seed 重拟合一次（确定性），因此与 D03 的选中模型逐元素一致。
    """
    if rep.chosen_model not in {name for name in (rep.predictions or {})}:
        raise ValueError("D03 选中模型不在本 rep 的预测集合里")
    required = {"user_id", "is_new", "cart_value", "channel", "hist_gmv", "browse_depth"}
    if required - set(users.columns):
        raise ValueError(f"新用户表缺少打分列：{sorted(required - set(users.columns))}")
    transformed = rep.data.preprocessor.transform(users)
    matrix = np.ascontiguousarray(transformed.matrix, dtype=float)
    predict_fn, _info = _fit_learner(
        rep.chosen_model,
        rep.data.train.X,
        rep.data.train.y,
        rep.data.train.treatment,
        cfg,
        seed_index=int(seed_index),
    )
    tau_hat = np.asarray(predict_fn(matrix), dtype=float).reshape(-1)
    cost_hat = np.asarray(predict_expected_cost(rep.cost_model, matrix, cfg), dtype=float)
    train_observed = _observations_for_keys(
        rep.dataset, rep.data.train.keys, ("paid_purchase_7d", "coupon_cost")
    )
    propensity, predicted_profit = _fit_level_baselines(
        rep.data, train_observed, matrix, cfg, seed_index=int(seed_index)
    )
    frame = pd.DataFrame({
        "user_id": users["user_id"].to_numpy(),
        "is_new": users["is_new"].to_numpy(dtype=np.int64),
        "cart_value": users["cart_value"].to_numpy(dtype=float),
        "purchase_propensity": propensity,
        "predicted_profit": predicted_profit,
        "tau_hat": tau_hat,
        "cost_hat": cost_hat,
    }).loc[:, list(SCORE_COLUMNS)]
    numeric = frame.loc[:, ["cart_value", "purchase_propensity", "predicted_profit", "tau_hat", "cost_hat"]]
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("新用户打分含非有限值")
    if not frame["user_id"].is_unique:
        raise ValueError("新用户 user_id 必须唯一")
    if (frame["cost_hat"] <= 0).any():
        raise ValueError("cost_hat 必须严格为正")
    return ScoredCohort(
        frame=frame,
        model=str(rep.chosen_model),
        policy="",
        preprocessor_hash=rep.data.preprocessor_hash,
    )


def build_validation_assignment(
    scored: ScoredCohort,
    cfg: Config,
    *,
    policy: str,
    rep_id: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """冻结三臂动作；返回分配表与预测支出汇总（只读选人列）。"""
    policy = _require_policy_name(policy)
    frame = scored.frame
    n = len(frame)
    budget = float(
        cfg.require("evaluation.independent_validation.primary_budget_cny_per_user")
    )
    labels = draw_policy_arms(n, cfg, rep_id=rep_id)
    tau_hat = frame["tau_hat"].to_numpy(dtype=float)
    cost_hat = frame["cost_hat"].to_numpy(dtype=float)

    targeted_rng = child_rng(
        int(cfg.require("project.master_seed")), "f02.targeted", int(rep_id)
    )
    in_targeted = labels == TARGETED_ARM
    targeted_frame = frame.loc[in_targeted].reset_index(drop=True)
    targeted = run_policy(
        policy, targeted_frame, budget * int(in_targeted.sum()), targeted_rng
    )

    random_rng = child_rng(
        int(cfg.require("project.master_seed")), "f02.random", int(rep_id)
    )
    in_random = labels == RANDOM_ARM
    random_selection = pol.random_under_budget(
        tau_hat[in_random], cost_hat[in_random], budget * int(in_random.sum()), random_rng
    )

    issued = np.zeros(n, dtype=np.int64)
    issued[in_targeted] = targeted.mask.astype(np.int64)
    issued[in_random] = random_selection.mask.astype(np.int64)

    # 全队列交付名单只进审计：不参与交付，也不参与任何选择。
    audit_targeted_rng = child_rng(
        int(cfg.require("project.master_seed")), "f02.audit_targeted", int(rep_id)
    )
    audit_targeted = run_policy(policy, frame, budget * n, audit_targeted_rng)
    audit_random_rng = child_rng(
        int(cfg.require("project.master_seed")), "f02.audit_random", int(rep_id)
    )
    audit_random = pol.random_under_budget(tau_hat, cost_hat, budget * n, audit_random_rng)
    probabilities = dict(zip(
        ARMS,
        (float(value) for value in cfg.require("evaluation.independent_validation.arm_probabilities")),
        strict=True,
    ))
    assignment = pd.DataFrame({
        "user_id": frame["user_id"].to_numpy(),
        "assigned_policy_arm": labels,
        "issued_action": issued,
        "policy_arm_probability": [probabilities[str(label)] for label in labels],
    })
    if (assignment.loc[assignment["assigned_policy_arm"] == CONTROL_ARM, "issued_action"] != 0).any():
        raise ValueError("no_coupon 臂不得发券")
    if not assignment["user_id"].is_unique:
        raise ValueError("分配表 user_id 必须唯一")

    def _arm_spend(selected: np.ndarray, arm: str) -> dict[str, float]:
        in_arm = labels == arm
        n_arm = int(in_arm.sum())
        spend = float(cost_hat[in_arm][selected].sum())
        return {
            "n_assigned": n_arm,
            "n_issued": int(selected.sum()),
            "predicted_spend_cny": spend,
            "predicted_spend_per_assigned_cny": spend / n_arm,
            "budget_deviation_cny": spend - budget * n_arm,
        }

    n_targeted = int(in_targeted.sum())
    n_random = int(in_random.sum())
    info = {
        "budget_cny_per_user": budget,
        "budget_basis": "same_per_assigned_user_in_each_active_arm",
        "policy": policy,
        "arms": {
            TARGETED_ARM: _arm_spend(targeted.mask, TARGETED_ARM),
            RANDOM_ARM: _arm_spend(random_selection.mask, RANDOM_ARM),
            # 对照臂没有券预算，偏差记为 0；否则会被误读成"预算没花完"。
            CONTROL_ARM: {"n_assigned": int((labels == CONTROL_ARM).sum()), "n_issued": 0,
                          "predicted_spend_cny": 0.0, "predicted_spend_per_assigned_cny": 0.0,
                          "budget_deviation_cny": 0.0},
        },
        "arm_lists": {
            "targeted_n": int(targeted.mask.sum()),
            "targeted_predicted_spend_cny": float(targeted.predicted_cost),
            "targeted_within_budget": float(targeted.predicted_cost) <= budget * n_targeted + pol.BUDGET_TOLERANCE,
            "random_n": int(random_selection.mask.sum()),
            "random_predicted_spend_cny": float(random_selection.predicted_cost),
            "random_within_budget": float(random_selection.predicted_cost) <= budget * n_random + pol.BUDGET_TOLERANCE,
        },
        "audit_full_lists": {
            "budget_cny": budget * n,
            "targeted_n": int(audit_targeted.mask.sum()),
            "targeted_predicted_spend_cny": float(audit_targeted.predicted_cost),
            "targeted_within_budget": float(audit_targeted.predicted_cost) <= budget * n + pol.BUDGET_TOLERANCE,
            "random_n": int(audit_random.mask.sum()),
            "random_predicted_spend_cny": float(audit_random.predicted_cost),
            "random_within_budget": float(audit_random.predicted_cost) <= budget * n + pol.BUDGET_TOLERANCE,
        },
        "audit_targeted_ids": frame["user_id"].to_numpy()[audit_targeted.mask].copy(),
        "audit_random_ids": frame["user_id"].to_numpy()[audit_random.mask].copy(),
    }
    return assignment, info


def _materialize_validation_dataset(
    population: Any,
    cfg: Config,
    *,
    scenario: str,
    rep_id: int,
) -> ObservedDataset:
    """对验证种群执行 raw→dirty→clean→SQL；不保存五表（代表 rep 另行保存）。"""
    users, assignments, orders = population.observation_bundle()
    stream = f"v3.f02.{scenario}"
    raw = build_raw_tables(
        users, assignments, orders, cfg,
        run_id=f"f02:{scenario}:rep{int(rep_id)}", rep_id=int(rep_id), stream_prefix=stream,
    )
    dirty = inject_dirt(raw, cfg, rep_id=int(rep_id), stream_prefix=stream)
    clean = deduplicate_events(dirty.tables, cfg)
    raw_sql = run_sql_pipeline(raw, cfg)
    raw_dataset = ObservedDataset.from_sql_result(raw_sql, cfg)
    if raw_dataset.population_kind != "validation":
        raise ValueError("F02 的观测表必须是独立验证种群")
    clean_sql = run_sql_pipeline(clean.tables, cfg)
    dataset = ObservedDataset.from_sql_result(clean_sql, cfg)
    raw["user_outcomes"] = raw_sql.user_outcomes.copy(deep=True)
    clean.tables["user_outcomes"] = clean_sql.user_outcomes.copy(deep=True)
    dirty.tables["user_outcomes"] = clean_sql.user_outcomes.copy(deep=True)
    validate_tables(clean.tables, cfg, stage="clean", require_outcomes=True)
    return dataset


def _mean_se(values: np.ndarray) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if values.size < 2:
        return float(values.mean()) if values.size else float("nan"), float("nan")
    return float(values.mean()), float(values.std(ddof=1) / np.sqrt(values.size))


def arm_summary(observed: pd.DataFrame) -> pd.DataFrame:
    """全臂 ITT 的逐臂均值；分母是该臂全部分配用户。"""
    if "assigned_policy_arm" not in observed:
        raise ValueError("观测表缺少 assigned_policy_arm")
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        block = observed.loc[observed["assigned_policy_arm"] == arm]
        mean, se = _mean_se(block["net_profit"].to_numpy(dtype=float))
        rows.append({
            "arm": arm,
            "n_assigned": int(len(block)),
            "n_issued": int(block["actual_action"].sum()),
            "issue_share": float(block["actual_action"].mean()) if len(block) else float("nan"),
            "mean_net_profit_cny": mean,
            "se_net_profit_cny": se,
            "mean_coupon_cost_cny": float(block["coupon_cost"].mean()) if len(block) else float("nan"),
            "total_coupon_cost_cny": float(block["coupon_cost"].sum()),
        })
    return pd.DataFrame(rows).loc[:, list(ARM_SUMMARY_COLUMNS)]


def _contrast(
    observed: pd.DataFrame, left: str, right: str, confidence: float
) -> dict[str, Any]:
    a = observed.loc[observed["assigned_policy_arm"] == left, "net_profit"].to_numpy(dtype=float)
    b = observed.loc[observed["assigned_policy_arm"] == right, "net_profit"].to_numpy(dtype=float)
    mean_a, se_a = _mean_se(a)
    mean_b, se_b = _mean_se(b)
    diff = mean_a - mean_b
    se = float(np.sqrt(se_a**2 + se_b**2))
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    low, high = diff - z * se, diff + z * se
    p = (
        float(2.0 * (1.0 - NormalDist().cdf(abs(diff / se))))
        if np.isfinite(se) and se > 0.0 else float("nan")
    )
    return {
        "contrast": f"{left}_minus_{right}",
        "diff_cny_per_user": diff,
        "se": se,
        "ci_low": low,
        "ci_high": high,
        "two_sided_p_value": p,
        "n_left": int(a.size),
        "n_right": int(b.size),
    }


def itt_contrasts(observed: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """三条全臂 ITT 对照：定向−不发券、定向−随机、随机−不发券。"""
    confidence = float(cfg.require("evaluation.confidence_level"))
    rows = [
        _contrast(observed, TARGETED_ARM, CONTROL_ARM, confidence),
        _contrast(observed, TARGETED_ARM, RANDOM_ARM, confidence),
        _contrast(observed, RANDOM_ARM, CONTROL_ARM, confidence),
    ]
    return pd.DataFrame(rows).loc[:, list(CONTRAST_COLUMNS)]


def freeze_observed(
    observed: pd.DataFrame, *, selected_policy: str, model: str
) -> tuple[pd.DataFrame, str]:
    """冻结逐用户观测记录并返回 (记录, freeze_hash)；此步不得读真值。"""
    columns = ["run_id", "user_id", "assigned_policy_arm", "actual_action", "net_profit", "coupon_cost"]
    missing = [column for column in columns if column not in observed]
    if missing:
        raise ValueError(f"观测表缺少冻结列：{missing}")
    per_user = observed.loc[:, columns].rename(columns={
        "actual_action": "issued_action",
        "net_profit": "observed_net_profit",
        "coupon_cost": "observed_coupon_cost",
    })
    delivered_policy = {
        TARGETED_ARM: selected_policy,
        RANDOM_ARM: RANDOM_ARM,
        CONTROL_ARM: CONTROL_ARM,
    }
    per_user = per_user.assign(
        selected_policy_id=per_user["assigned_policy_arm"].map(delivered_policy)
    ).loc[:, list(PER_USER_COLUMNS)]
    per_user = per_user.sort_values("user_id", kind="stable").reset_index(drop=True)
    payload = dataframe_sha256(per_user) + "|" + selected_policy + "|" + model
    freeze_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return per_user, freeze_hash


def audit_policy_values(
    population: Any,
    cfg: Config,
    *,
    targeted_ids: np.ndarray,
    random_ids: np.ndarray,
    user_ids: np.ndarray,
    worlds: Mapping[int, pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """冻结后解锁真值：逐用户 ``tau_true/cost_true`` 与全队列策略真值。

    名单按 ``user_id`` 对齐，不按行位置；``observed`` 是 SQL 输出，行序不可假设。
    """
    worlds = audit_realized_worlds(population, cfg) if worlds is None else worlds
    if set(worlds) != {0, 1}:
        raise ValueError(f"审计世界应恰为 {{0, 1}}，收到 {sorted(worlds)}")
    world1 = worlds[1].set_index("user_id")
    world0 = worlds[0].set_index("user_id")
    if not world1.index.is_unique or not world0.index.is_unique:
        raise ValueError("审计账本 user_id 必须唯一")
    ids = np.asarray(user_ids)
    if np.unique(ids).size != ids.size:
        raise ValueError("observed.user_id 必须唯一")
    missing = ~np.isin(ids, world1.index.to_numpy())
    if missing.any():
        raise ValueError(f"审计账本缺少 {int(missing.sum())} 个验证用户")
    y1 = world1.loc[ids, "net_profit"].to_numpy(dtype=float)
    y0 = world0.loc[ids, "net_profit"].to_numpy(dtype=float)
    cost1 = world1.loc[ids, "coupon_cost"].to_numpy(dtype=float)
    audit_users = pd.DataFrame({
        "user_id": ids,
        "tau_true": y1 - y0,
        "cost_true": cost1,
    })
    targeted_ids = np.asarray(targeted_ids)
    random_ids = np.asarray(random_ids)
    for name, chosen in (("targeted", targeted_ids), ("random", random_ids)):
        if not np.isin(chosen, ids).all():
            raise ValueError(f"{name} 名单含不在观测分母里的用户")

    def _value(chosen: np.ndarray) -> float:
        return float(np.mean(np.where(np.isin(ids, chosen), y1, y0)))

    values = {
        "value_targeted_policy": _value(targeted_ids),
        "value_random_same_budget": _value(random_ids),
        "value_no_coupon": float(np.mean(y0)),
    }
    audit_policy = pd.DataFrame({
        "component": list(values),
        "value_cny_per_user": list(values.values()),
        "n": int(ids.size),
        "n_selected": [targeted_ids.size, random_ids.size, 0],
    })
    return audit_users, audit_policy


def true_arm_means(
    population: Any,
    cfg: Config,
    assignment: pd.DataFrame,
    *,
    worlds: Mapping[int, pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """审计：逐臂真值均值与真值对照（全臂分母）。"""
    worlds = audit_realized_worlds(population, cfg) if worlds is None else worlds
    world1 = worlds[1].set_index("user_id")
    world0 = worlds[0].set_index("user_id")
    ids = assignment["user_id"].to_numpy()
    y1 = world1.loc[ids, "net_profit"].to_numpy(dtype=float)
    y0 = world0.loc[ids, "net_profit"].to_numpy(dtype=float)
    action = assignment["issued_action"].to_numpy(dtype=int)
    realized = np.where(action == 1, y1, y0)
    frame = assignment.assign(true_net_profit=realized, tau_true=y1 - y0)
    rows = []
    for arm in ARMS:
        block = frame.loc[frame["assigned_policy_arm"] == arm]
        rows.append({
            "arm": arm,
            "n_assigned": int(len(block)),
            "true_mean_net_profit_cny": float(block["true_net_profit"].mean()),
            "true_mean_tau_cny": float(block["tau_true"].mean()),
        })
    means = pd.DataFrame(rows)
    confidence = float(cfg.require("evaluation.confidence_level"))
    contrasts = pd.DataFrame([
        _contrast(
            frame.rename(columns={"true_net_profit": "net_profit"}),
            TARGETED_ARM, CONTROL_ARM, confidence,
        ),
        _contrast(
            frame.rename(columns={"true_net_profit": "net_profit"}),
            TARGETED_ARM, RANDOM_ARM, confidence,
        ),
    ]).loc[:, list(CONTRAST_COLUMNS)]
    return means, contrasts


def run_f02_rep(
    *,
    scenario: str = "L1_main",
    n: int = 20_000,
    rep_id: int = 0,
    policy: str = "greedy_incremental_profit_per_cost",
    models: Sequence[str] | None = None,
    time_mode: str = "static",
    out_dir: str | Path | None = None,
    status: str = "provisional",
    formal_approval: str | None = None,
) -> F02Result:
    """跑一个 rep 的完整 F02 链路；不改变任何正式完成计数。

    ``status="formal"`` 必须同时给出 ``formal_approval``（用户批准的登记号），
    否则拒绝——避免把工程冒烟伪装成正式重复。
    """
    from causal_growth.v3_config import load_v3_protocol

    if status not in {"provisional", "engineering", "formal"}:
        raise ValueError(f"未注册的状态：{status!r}")
    if status == "formal" and not formal_approval:
        raise ValueError("正式 F02 需要用户批准并给出 formal_approval 登记号")
    policy = _require_policy_name(policy)
    cfg = load_v3_protocol().scenario(scenario)
    n = int(n)
    if n <= 0:
        raise ValueError("n 必须为正")
    rep = _d03_rep_artifacts(
        scenario=scenario, n=n, rep_id=int(rep_id), models=models, time_mode=time_mode
    )
    first = generate_covariates(
        cfg, int(rep_id), n, population_kind="validation"
    )
    users = first.users
    scored = score_validation_users(rep, users, cfg, seed_index=int(rep_id))
    assignment, assignment_info = build_validation_assignment(
        scored, cfg, policy=policy, rep_id=int(rep_id)
    )
    population = generate_v3_population(
        cfg, rep_id=int(rep_id), n=n, population_kind="validation",
        validation_assignment=assignment,
    )
    if dataframe_sha256(population.users) != dataframe_sha256(users):
        raise RuntimeError("两次生成的验证用户不一致，三臂分配无法与事实订单对齐")
    target = Path(out_dir) if out_dir is not None else None
    representative_rep = int(load_v3_data_config().require("validation.representative_rep"))
    save_five = target is not None and int(rep_id) == representative_rep
    five_manifest: Path | None = None
    if save_five:
        target.mkdir(parents=True, exist_ok=True)
        users_t, assignments_t, orders_t = population.observation_bundle()
        pipeline = build_observed_pipeline(
            users_t, assignments_t, orders_t, cfg,
            directory=target / "five_tables",
            run_id=f"f02:{scenario}:rep{int(rep_id)}",
            rep_id=int(rep_id), stream_prefix=f"v3.f02.{scenario}",
            population_kind="validation", retention_scope="representative_full",
        )
        dataset = pipeline.dataset
        five_manifest = pipeline.manifest_path
    else:
        dataset = _materialize_validation_dataset(
            population, cfg, scenario=scenario, rep_id=int(rep_id)
        )
    observed = dataset.observations
    if len(observed) != n or not observed["user_id"].is_unique:
        raise ValueError("验证观测表的全臂分母不完整")
    summary = arm_summary(observed)
    contrasts = itt_contrasts(observed, cfg)
    per_user, freeze_hash = freeze_observed(
        observed, selected_policy=policy, model=scored.model
    )
    target = Path(out_dir) if out_dir is not None else None
    if target is not None:
        target.mkdir(parents=True, exist_ok=True)
        per_user.to_csv(target / "per_user.csv", index=False, encoding="utf-8-sig")
        summary.to_csv(target / "arm_summary.csv", index=False, encoding="utf-8-sig")
        contrasts.to_csv(target / "itt_contrasts.csv", index=False, encoding="utf-8-sig")
        (target / "freeze.json").write_text(
            json.dumps({
                "freeze_hash": freeze_hash,
                "per_user_hash": dataframe_sha256(per_user),
                "selected_model": scored.model,
                "selected_policy": policy,
                "truth_columns_present": False,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    # ---- 冻结文件已落盘，以下才允许读真值 ----
    worlds = audit_realized_worlds(population, cfg)
    audit_users, audit_policy = audit_policy_values(
        population, cfg,
        targeted_ids=assignment_info["audit_targeted_ids"],
        random_ids=assignment_info["audit_random_ids"],
        user_ids=observed["user_id"].to_numpy(),
        worlds=worlds,
    )
    audit_users = observed.loc[:, ["run_id", "user_id"]].merge(
        audit_users, on="user_id", how="left", validate="one_to_one"
    ).merge(
        assignment.loc[:, ["user_id", "assigned_policy_arm", "issued_action"]],
        on="user_id", how="left", validate="one_to_one",
    ).loc[:, list(AUDIT_COLUMNS)]
    audit_means, audit_contrasts = true_arm_means(
        population, cfg, assignment, worlds=worlds
    )
    manifest = {
        "status": status,
        "formal_approval": formal_approval,
        "phase": "F02",
        "scenario": scenario,
        "rep_id": int(rep_id),
        "n_users": n,
        "selected_model": scored.model,
        "selected_policy": policy,
        "budget_cny_per_user": assignment_info["budget_cny_per_user"],
        "budget_basis": assignment_info["budget_basis"],
        "arms": assignment_info["arms"],
        "arm_lists": assignment_info["arm_lists"],
        "audit_full_lists": assignment_info["audit_full_lists"],
        "preprocessor_hash": scored.preprocessor_hash,
        "config_hash": cfg.hash(64),
        "freeze_hash": freeze_hash,
        "audit_unlock_order": "freeze_files_written_then_audit_realized_worlds",
        "per_user_hash": dataframe_sha256(per_user),
        "assignment_hash": dataframe_sha256(assignment),
        "observed_sql_hash": dataset.content_hash,
        "representative_five_tables": bool(save_five),
        "representative_tables_manifest": str(five_manifest) if five_manifest is not None else None,
        "representative_tables_manifest_sha256": (
            file_sha256(five_manifest) if five_manifest is not None else None
        ),
        "source_hashes": pipeline_source_hashes(),
        "audit_true_arm_means": audit_means.to_dict(orient="records"),
    }
    if target is not None:
        audit_users.to_csv(target / "audit_truth.csv", index=False, encoding="utf-8-sig")
        audit_policy.to_csv(target / "audit_policy_values.csv", index=False, encoding="utf-8-sig")
        audit_contrasts.to_csv(target / "audit_arm_contrasts.csv", index=False, encoding="utf-8-sig")
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return F02Result(
        scenario=scenario,
        rep_id=int(rep_id),
        n=n,
        model=scored.model,
        policy=policy,
        assignment=assignment,
        dataset=dataset,
        per_user=per_user,
        arm_summary=summary,
        contrasts=contrasts,
        audit_users=audit_users,
        audit_policy=audit_policy,
        audit_contrasts=audit_contrasts,
        freeze_hash=freeze_hash,
        manifest=manifest,
    )
