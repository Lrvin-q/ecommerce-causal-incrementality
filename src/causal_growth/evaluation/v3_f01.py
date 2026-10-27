"""F01 历史留出 OPE：先冻结策略名单，再用观测数据估价值，最后才做真值审计。

回答哪个问题
------------
E 阶段用 DGP 真值评估策略；F01 换一个更严格的问题：**不看真值**，只用 D03 test
split 的观测记录 ``(T, Y, C, R)`` 与随机化设计概率，能否把同一批冻结名单的策略价值、
配对差、成本与退款率估出来？估计值与冻结后的真值审计差多少？

硬顺序
------
1. 只在 7 列选人表上构造名单（``no_coupon`` / ``random_same_budget`` /
   ``greedy_incremental_profit_per_cost`` / ``greedy_local_swap``）；
2. 把名单、用户顺序、设计概率、配置与源码哈希写进冻结 manifest 并落盘；
3. 重读 manifest，逐项复算 ``freeze_id``；
4. **之后**才允许合并 ``tau_true`` / ``cost_true`` 做审计，审计列一律 ``audit_`` 前缀。
本模块没有"先看真值再选策略"的入口，也不把真值传给任何拟合函数。

估计量
------
价值、配对差、成本与护栏复用 :mod:`causal_growth.evaluation.v3_ope` 的原语；主估计量
是交叉拟合 DR（AIPW），IPW/SNIPS 只作敏感性。确证性家族来自冻结配置
``evaluation.decision.benefit_evidence``：定向 − 不发券、定向 − 同预算随机，
单侧 Holm（α 见配置），两条主张分开陈述，**不合并成一个"推荐"**。

预算
----
主预算 ``evaluation.independent_validation.primary_budget_cny_per_user``（0.2 元/人）
承担确证性家族；其余预算只做历史留出 OPE 与真值审计，对应配置
``other_budgets: historical_heldout_ope_and_truth_audit_only``。nuisance 与预算无关，
所有预算共用**同一次**交叉拟合。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from causal_growth.config import Config
from causal_growth.data.v3_storage import dataframe_sha256
from causal_growth.evaluation import v3_ope as ope
from causal_growth.policy import v3_policy as pol
from causal_growth.policy.v3_policy_grid import run_policy
from causal_growth.rng import child_rng

FREEZE_SCHEMA = "f01-freeze-v1"

#: D03 交接的前 7 列；后 2 列真值永远不进入选人表。
FREEZE_COLUMNS: tuple[str, ...] = (
    "user_id",
    "is_new",
    "cart_value",
    "purchase_propensity",
    "predicted_profit",
    "tau_hat",
    "cost_hat",
)

OBSERVED_COLUMNS: tuple[str, ...] = (
    "user_id",
    "treatment",
    "net_profit",
    "coupon_cost",
    "any_refund_30d",
    "design_probability",
)

CANDIDATE_POLICIES: tuple[str, ...] = (
    "no_coupon",
    "random_same_budget",
    "greedy_incremental_profit_per_cost",
    "greedy_local_swap",
)

#: E 接口文档 §3 注册的主策略；确证性家族只围绕它构造。
PRIMARY_POLICY = "greedy_incremental_profit_per_cost"

#: 配置家族名 → (策略, 基线)。配置若改名，本模块会显式报错而不是悄悄换对照。
FAMILY_CONTRASTS: dict[str, tuple[str, str]] = {
    "selected_targeted_minus_no_coupon": (PRIMARY_POLICY, "no_coupon"),
    "selected_targeted_minus_same_budget_random": (
        PRIMARY_POLICY,
        "random_same_budget",
    ),
}

VALUE_TABLE_COLUMNS: tuple[str, ...] = ("per_user_budget_cny",) + ope.VALUE_COLUMNS
CONTRAST_TABLE_COLUMNS: tuple[str, ...] = (
    "per_user_budget_cny", "contrast"
) + ope.DIFF_COLUMNS
COST_TABLE_COLUMNS: tuple[str, ...] = ("per_user_budget_cny",) + ope.COMPONENT_COLUMNS
FAMILY_TABLE_COLUMNS: tuple[str, ...] = (
    "contrast", "policy", "baseline", "estimator",
    "diff_cny_per_user", "se_diff", "ci_low", "ci_high",
    "one_sided_p_value", "adjusted_alpha", "holm_adjusted_p_value", "holm_alpha",
    "holm_rejected", "holm_lower_bound_cny_per_user", "holm_confidence_level",
    "claim_passed", "n",
)
AUDIT_TABLE_COLUMNS: tuple[str, ...] = (
    "per_user_budget_cny", "policy", "audit_freeze_id",
    "audit_n_selected", "audit_increment_vs_no_coupon_cny_per_user",
    "audit_total_increment_cny", "audit_actual_spend_cny",
    "audit_spend_per_user_cny", "audit_budget_cny",
    "audit_within_budget_by_true",
)
OPE_VS_AUDIT_COLUMNS: tuple[str, ...] = (
    "per_user_budget_cny", "comparison", "name",
    "ope_value_cny_per_user", "audit_value_cny_per_user",
    "value_error_cny_per_user", "ope_spend_per_user_cny",
    "audit_spend_per_user_cny", "spend_error_cny_per_user",
    "reliability_passed", "holm_rejected", "sign_agrees",
)

_FORBIDDEN_PREFIXES = ("audit_", "truth_", "potential_")
_FORBIDDEN_NAMES = ("tau_true", "cost_true", "u_true")


# --------------------------------------------------------------------------- #
# 校验与哈希
# --------------------------------------------------------------------------- #
def _forbidden_columns(frame: pd.DataFrame) -> list[str]:
    return [
        str(column)
        for column in frame.columns
        if str(column).endswith("_true")
        or str(column) in _FORBIDDEN_NAMES
        or any(str(column).startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)
    ]


def require_freeze_frame(selection: pd.DataFrame) -> pd.DataFrame:
    """校验 7 列选人表并按 ``user_id`` 升序返回副本；真值列直接拒收。"""
    forbidden = _forbidden_columns(selection)
    if forbidden:
        raise ValueError(f"选人表混入真值/审计列，禁止进入冻结：{forbidden}")
    if tuple(selection.columns) != FREEZE_COLUMNS:
        raise ValueError(
            f"选人表列必须恰为 {FREEZE_COLUMNS}，收到 {tuple(selection.columns)}"
        )
    if selection["user_id"].duplicated().any():
        raise ValueError("选人表的 user_id 必须唯一")
    numeric = selection.loc[
        :, ["cart_value", "purchase_propensity", "predicted_profit", "tau_hat", "cost_hat"]
    ].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("选人列含非有限值")
    propensity = selection["purchase_propensity"].to_numpy(dtype=float)
    if ((propensity < 0.0) | (propensity > 1.0)).any():
        raise ValueError("purchase_propensity 必须落在 [0, 1]")
    if (selection["cost_hat"].to_numpy(dtype=float) <= 0.0).any():
        raise ValueError("cost_hat 必须严格为正")
    return selection.sort_values("user_id", kind="stable").reset_index(drop=True)


def _require_design_vector(values: Any, user_id: NDArray[Any]) -> NDArray[np.float64]:
    """把设计概率按 ``user_id`` 对齐并校验严格落在 (0,1)。"""
    if isinstance(values, pd.Series):
        series = values.copy()
        if not series.index.is_unique:
            raise ValueError("design_probability 的索引必须唯一")
        missing = ~pd.Index(user_id).isin(series.index)
        if missing.any():
            raise ValueError(f"design_probability 缺少 {int(missing.sum())} 个用户")
        aligned = series.reindex(pd.Index(user_id))
        array = aligned.to_numpy(dtype=float)
    else:
        array = np.asarray(values, dtype=float).reshape(-1)
        if array.shape != user_id.shape:
            raise ValueError(
                f"design_probability 长度应为 {user_id.size}，收到 {array.shape}"
            )
    if not np.isfinite(array).all():
        raise ValueError("design_probability 含非有限值")
    if not ((array > 0.0) & (array < 1.0)).all():
        raise ValueError("design_probability 必须严格落在 (0,1)")
    return array


def _array_sha256(array: NDArray[Any], *, label: str) -> str:
    values = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(label.encode("utf-8"))
    digest.update(str(values.dtype).encode("utf-8"))
    digest.update(str(values.shape).encode("utf-8"))
    digest.update(values.tobytes())
    return digest.hexdigest()


def _mask_sha256(mask: NDArray[Any]) -> str:
    values = np.asarray(mask, dtype=bool)
    digest = hashlib.sha256()
    digest.update(b"mask")
    digest.update(str(values.size).encode("utf-8"))
    digest.update(np.packbits(values.astype(np.uint8)).tobytes())
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def budget_key(per_user: float) -> str:
    """预算的稳定字符串键（用于 JSON 与 CSV 连接）。"""
    return format(float(per_user), ".12g")


def _align_policy_masks(
    policy_frame: pd.DataFrame, user_id: NDArray[Any]
) -> dict[str, NDArray[np.float64]]:
    """按 ``user_id`` 对齐策略 0/1 列；集合不等或取值非法直接报错。"""
    missing = [name for name in CANDIDATE_POLICIES if name not in policy_frame.columns]
    if "user_id" not in policy_frame.columns or missing:
        raise ValueError(f"策略表缺少列：user_id / {missing}")
    if policy_frame["user_id"].duplicated().any():
        raise ValueError("策略表的 user_id 必须唯一")
    if set(policy_frame["user_id"]) != set(user_id):
        raise ValueError("策略表与目标用户集合不一致，不能按行号硬对齐")
    aligned = policy_frame.set_index("user_id").reindex(pd.Index(user_id))
    masks: dict[str, NDArray[np.float64]] = {}
    for name in CANDIDATE_POLICIES:
        values = aligned[name].to_numpy(dtype=float)
        if not np.isin(values, [0.0, 1.0]).all():
            raise ValueError(f"策略 {name} 必须是 0/1")
        masks[name] = values
    return masks


# --------------------------------------------------------------------------- #
# 名单构造
# --------------------------------------------------------------------------- #
def build_policies(
    selection: pd.DataFrame,
    cfg: Config,
    *,
    budget_per_user: float,
    seed_index: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """在冻结选人表上构造 4 个候选名单；返回 (逐用户 0/1 表, 预算/预测汇总)。

    随机基线用 ``f01.policy.random`` 派生流；同一 ``seed_index`` 在不同预算下
    复用同一随机顺序（共同随机数），名单随预算单调嵌套。
    """
    ordered = require_freeze_frame(selection)
    per_user = float(budget_per_user)
    if not np.isfinite(per_user) or per_user <= 0.0:
        raise ValueError("budget_per_user 必须是正有限数")
    n = len(ordered)
    budget = per_user * n
    rng = child_rng(int(cfg.require("project.master_seed")), "f01.policy.random", seed_index)
    columns: dict[str, NDArray[Any]] = {"user_id": ordered["user_id"].to_numpy()}
    meta_rows: list[dict[str, Any]] = []
    for name in CANDIDATE_POLICIES:
        chosen = run_policy(name, ordered, budget, rng)
        mask = np.asarray(chosen.mask, dtype=bool)
        columns[name] = mask.astype(np.int8)
        meta_rows.append({
            "per_user_budget_cny": per_user,
            "budget_cny": budget,
            "policy": name,
            "n_selected": int(mask.sum()),
            "predicted_value": float(chosen.predicted_value),
            "predicted_cost": float(chosen.predicted_cost),
            "within_budget_by_hat": bool(
                chosen.predicted_cost <= budget + pol.BUDGET_TOLERANCE
            ),
        })
    policy_frame = pd.DataFrame(columns).loc[
        :, ["user_id", *CANDIDATE_POLICIES]
    ]
    meta = pd.DataFrame(meta_rows).loc[
        :, [
            "per_user_budget_cny", "budget_cny", "policy", "n_selected",
            "predicted_value", "predicted_cost", "within_budget_by_hat",
        ]
    ]
    return policy_frame, meta


# --------------------------------------------------------------------------- #
# 冻结 manifest
# --------------------------------------------------------------------------- #
def _freeze_payload(
    selection: pd.DataFrame,
    policy_frames: Mapping[float, pd.DataFrame],
    design_probability: Any,
    *,
    scenario: str,
    n_dgp: int,
    n_users: int,
    rep_id: int,
    chosen_model: str,
    config_hash: str,
    source_hashes: Mapping[str, str],
) -> dict[str, Any]:
    ordered = require_freeze_frame(selection)
    if len(ordered) != int(n_users):
        raise ValueError(f"选人表 {len(ordered)} 行与 n_users={n_users} 不一致")
    if int(n_dgp) < int(n_users):
        raise ValueError("n_dgp 不能小于 n_users")
    user_id = ordered["user_id"].to_numpy()
    design = _require_design_vector(design_probability, user_id)
    if not policy_frames:
        raise ValueError("至少需要一个预算的名单")
    budgets: dict[str, Any] = {}
    for per_user in sorted(float(value) for value in policy_frames):
        key = budget_key(per_user)
        masks = _align_policy_masks(policy_frames[per_user], user_id)
        budgets[key] = {
            "per_user_budget_cny": per_user,
            "budget_cny": per_user * int(n_users),
            "policy_sha256": {name: _mask_sha256(mask) for name, mask in masks.items()},
            "n_selected": {name: int(mask.sum()) for name, mask in masks.items()},
        }
    return {
        "schema": FREEZE_SCHEMA,
        "scenario": str(scenario),
        "n_dgp": int(n_dgp),
        "n_users": int(n_users),
        "rep_id": int(rep_id),
        "chosen_model": str(chosen_model),
        "config_hash": str(config_hash),
        "source_hashes": dict(source_hashes),
        "selection_columns": list(FREEZE_COLUMNS),
        "selection_sha256": dataframe_sha256(ordered),
        "user_id_sha256": _array_sha256(
            ordered["user_id"].to_numpy(dtype=np.int64), label="user_id"
        ),
        "design_probability_sha256": _array_sha256(design, label="design_probability"),
        "budgets": budgets,
        "family_contrasts": {
            name: list(pair) for name, pair in FAMILY_CONTRASTS.items()
        },
    }


def _freeze_id(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(dict(payload)).encode("utf-8")).hexdigest()


def build_freeze_manifest(
    selection: pd.DataFrame,
    policy_frames: Mapping[float, pd.DataFrame],
    design_probability: Any,
    *,
    scenario: str,
    n_dgp: int,
    n_users: int,
    rep_id: int,
    chosen_model: str,
    config_hash: str,
    source_hashes: Mapping[str, str],
    created_at: str,
) -> dict[str, Any]:
    """构造冻结 manifest；``freeze_id`` 覆盖全部内容，``created_at`` 不参与哈希。"""
    if not created_at:
        raise ValueError("created_at 不能为空")
    payload = _freeze_payload(
        selection,
        policy_frames,
        design_probability,
        scenario=scenario,
        n_dgp=n_dgp,
        n_users=n_users,
        rep_id=rep_id,
        chosen_model=chosen_model,
        config_hash=config_hash,
        source_hashes=source_hashes,
    )
    return {**payload, "freeze_id": _freeze_id(payload), "created_at": str(created_at)}


def verify_freeze_manifest(
    manifest: Mapping[str, Any],
    selection: pd.DataFrame,
    policy_frames: Mapping[float, pd.DataFrame],
    design_probability: Any,
    *,
    scenario: str,
    n_dgp: int,
    n_users: int,
    rep_id: int,
    chosen_model: str,
    config_hash: str,
    source_hashes: Mapping[str, str],
) -> str:
    """用当前名单/设计重算 manifest；任何一份内容被改动都会抛错。"""
    payload = _freeze_payload(
        selection,
        policy_frames,
        design_probability,
        scenario=scenario,
        n_dgp=n_dgp,
        n_users=n_users,
        rep_id=rep_id,
        chosen_model=chosen_model,
        config_hash=config_hash,
        source_hashes=source_hashes,
    )
    for key, expected in payload.items():
        if manifest.get(key) != expected:
            raise ValueError(f"freeze manifest 的 {key} 与当前内容不一致")
    expected_id = _freeze_id(payload)
    if manifest.get("freeze_id") != expected_id:
        raise ValueError("freeze_id 与当前内容不一致：名单/设计/配置可能被改动")
    if not str(manifest.get("created_at", "")):
        raise ValueError("freeze manifest 缺少 created_at")
    return expected_id


# --------------------------------------------------------------------------- #
# 观测表与真值审计
# --------------------------------------------------------------------------- #
def build_observed_frame(
    *,
    user_id: Any,
    treatment: Any,
    net_profit: Any,
    coupon_cost: Any,
    any_refund_30d: Any,
    design_probability: Any,
    features: Any,
) -> tuple[pd.DataFrame, NDArray[np.float64]]:
    """拼出 OPE 观测表并按 ``user_id`` 升序**同时重排特征**。

    返回 ``(观测表, 特征矩阵)``；两者行序一致。调用方不需要自己再排序，
    这是防止"特征跟着旧行序走"的唯一入口。
    """
    ids = np.asarray(user_id)
    n = ids.size
    arrays = {
        "treatment": np.asarray(treatment).reshape(-1),
        "net_profit": np.asarray(net_profit, dtype=float).reshape(-1),
        "coupon_cost": np.asarray(coupon_cost, dtype=float).reshape(-1),
        "any_refund_30d": np.asarray(any_refund_30d, dtype=float).reshape(-1),
        "design_probability": np.asarray(design_probability, dtype=float).reshape(-1),
    }
    for name, values in arrays.items():
        if values.shape != (n,):
            raise ValueError(f"{name} 长度应为 {n}，收到 {values.shape}")
    X = np.asarray(features, dtype=float)
    if X.ndim != 2 or X.shape[0] != n:
        raise ValueError("features 必须是 (n, p) 矩阵")
    if len(pd.Index(ids).unique()) != n:
        raise ValueError("user_id 必须唯一")
    if not np.isfinite(X).all():
        raise ValueError("features 含非有限值")
    frame = pd.DataFrame({"user_id": ids, **arrays})
    ordered = frame.sort_values("user_id", kind="stable").reset_index(drop=True)
    order = frame["user_id"].to_numpy().argsort(kind="stable")
    return ordered, np.ascontiguousarray(X[order], dtype=float)


def require_truth_frame(
    truth: pd.DataFrame, user_id: NDArray[Any], *, freeze_id: str
) -> pd.DataFrame:
    """校验审计真值只含 ``tau_true`` / ``cost_true``，且与冻结用户一一对齐。"""
    if not isinstance(freeze_id, str) or len(freeze_id) != 64:
        raise ValueError("审计真值必须绑定一个 64 位 freeze_id")
    missing = [column for column in ("user_id", "tau_true", "cost_true")
               if column not in truth.columns]
    if missing:
        raise ValueError(f"审计真值缺少列：{missing}")
    block = truth.loc[:, ["user_id", "tau_true", "cost_true"]].copy()
    if block["user_id"].duplicated().any():
        raise ValueError("审计真值的 user_id 必须唯一")
    if set(block["user_id"]) != set(user_id):
        raise ValueError("审计真值的用户集合与冻结名单不一致")
    aligned = block.set_index("user_id").reindex(pd.Index(user_id))
    values = aligned.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("审计真值含非有限值")
    if (aligned["cost_true"].to_numpy(dtype=float) < 0.0).any():
        raise ValueError("cost_true 不能为负")
    return aligned.reset_index()


def truth_audit_table(
    selection: pd.DataFrame,
    policy_frames: Mapping[float, pd.DataFrame],
    truth: pd.DataFrame,
    *,
    freeze_id: str,
) -> pd.DataFrame:
    """冻结后审计：逐预算、逐策略计算真值增量与实际支出。

    分母是**全部被分配用户**，不是入选用户；所有真值列以 ``audit_`` 开头。
    本函数不修改选人表或名单，也不参与任何拟合。
    """
    ordered = require_freeze_frame(selection)
    user_id = ordered["user_id"].to_numpy()
    aligned = require_truth_frame(truth, user_id, freeze_id=freeze_id)
    tau = aligned["tau_true"].to_numpy(dtype=float)
    cost = aligned["cost_true"].to_numpy(dtype=float)
    n = len(ordered)
    rows: list[dict[str, Any]] = []
    for per_user in sorted(float(value) for value in policy_frames):
        budget_cny = per_user * n
        masks = _align_policy_masks(policy_frames[per_user], user_id)
        for name in CANDIDATE_POLICIES:
            mask = masks[name]
            increment = float(np.mean(mask * tau))
            spend = float(np.sum(mask * cost))
            rows.append({
                "per_user_budget_cny": per_user,
                "policy": name,
                "audit_freeze_id": freeze_id,
                "audit_n_selected": int(mask.sum()),
                "audit_increment_vs_no_coupon_cny_per_user": increment,
                "audit_total_increment_cny": increment * n,
                "audit_actual_spend_cny": spend,
                "audit_spend_per_user_cny": spend / n,
                "audit_budget_cny": budget_cny,
                "audit_within_budget_by_true": bool(
                    spend <= budget_cny + pol.BUDGET_TOLERANCE
                ),
            })
    table = pd.DataFrame(rows).loc[:, list(AUDIT_TABLE_COLUMNS)]
    return table


# --------------------------------------------------------------------------- #
# OPE 表
# --------------------------------------------------------------------------- #
def influence_se(influence: Any) -> float:
    """影响函数的标准误 ``sd(IF)/√n``（ddof=1）。"""
    values = np.asarray(influence, dtype=float)
    if values.size < 2:
        return float("nan")
    return float(values.std(ddof=1) / np.sqrt(values.size))


def normal_interval(value: float, se: float, confidence: float) -> tuple[float, float]:
    if not np.isfinite(se) or se <= 0.0:
        return float("nan"), float("nan")
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    return value - z * se, value + z * se


def _value_table(
    frame: pd.DataFrame,
    nuisance: ope.OpeNuisances,
    masks: Mapping[str, NDArray[np.float64]],
    cfg: Config,
    confidence: float,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    y = frame["net_profit"].to_numpy(dtype=float)
    t = frame["treatment"].to_numpy(dtype=float)
    e = nuisance.propensity
    rows: list[dict[str, Any]] = []
    gates: dict[str, dict] = {}
    for name in CANDIDATE_POLICIES:
        pi = ope.require_policy(masks[name], len(frame), name=f"policy {name}")
        gate = ope.reliability_gate(pi, t, e, cfg)
        gates[name] = gate
        estimates = {
            "ipw_increment": ope.policy_value_ipw(pi, y, t, e),
            "dr_increment": ope.policy_value_dr(pi, y, t, nuisance.mu1, nuisance.mu0, e),
            "snips_increment": ope.policy_value_snips(pi, y, t, e),
        }
        for estimator in ope.ESTIMATORS:
            value, influence = estimates[estimator]
            se = influence_se(influence)
            low, high = normal_interval(value, se, confidence)
            rows.append({
                "policy": name,
                "estimator": estimator,
                "value_cny_per_user": value,
                "se_cny_per_user": se,
                "ci_low_cny_per_user": low,
                "ci_high_cny_per_user": high,
                "n": len(frame),
                "ess_treated": gate["ess_treated"],
                "ess_control": gate["ess_control"],
                "ess_fraction_treated": gate["ess_fraction_treated"],
                "ess_fraction_control": gate["ess_fraction_control"],
                "support_violation_fraction": gate["support_violation_fraction"],
                "reliability_passed": bool(gate["passed"]),
                "reliability_label": gate["label"],
            })
    return pd.DataFrame(rows).loc[:, list(ope.VALUE_COLUMNS)], gates


def _contrast_table(
    frame: pd.DataFrame,
    nuisance: ope.OpeNuisances,
    masks: Mapping[str, NDArray[np.float64]],
    confidence: float,
) -> pd.DataFrame:
    y = frame["net_profit"].to_numpy(dtype=float)
    t = frame["treatment"].to_numpy(dtype=float)
    e = nuisance.propensity
    rows: list[dict[str, Any]] = []
    for contrast, (policy_name, baseline_name) in FAMILY_CONTRASTS.items():
        pi = ope.require_policy(masks[policy_name], len(frame), name=policy_name)
        base = ope.require_policy(masks[baseline_name], len(frame), name=baseline_name)
        for estimator in ope.ESTIMATORS:
            if estimator == "ipw_increment":
                value_a, if_a = ope.policy_value_ipw(pi, y, t, e)
                value_b, if_b = ope.policy_value_ipw(base, y, t, e)
            elif estimator == "dr_increment":
                value_a, if_a = ope.policy_value_dr(
                    pi, y, t, nuisance.mu1, nuisance.mu0, e
                )
                value_b, if_b = ope.policy_value_dr(
                    base, y, t, nuisance.mu1, nuisance.mu0, e
                )
            else:
                value_a, if_a = ope.policy_value_snips(pi, y, t, e)
                value_b, if_b = ope.policy_value_snips(base, y, t, e)
            diff = value_a - value_b
            diff_influence = if_a - if_b
            se = influence_se(diff_influence)
            low, high = normal_interval(diff, se, confidence)
            z = diff / se if np.isfinite(se) and se > 0.0 else float("nan")
            p_one_sided = (
                float(1.0 - NormalDist().cdf(z)) if np.isfinite(z) else float("nan")
            )
            rows.append({
                "contrast": contrast,
                "policy": policy_name,
                "baseline": baseline_name,
                "estimator": estimator,
                "diff_cny_per_user": diff,
                "se_diff": se,
                "ci_low": low,
                "ci_high": high,
                "one_sided_p_value": p_one_sided,
                "n": len(frame),
            })
    return pd.DataFrame(rows).loc[:, ["contrast", *ope.DIFF_COLUMNS]]


def _cost_table(
    frame: pd.DataFrame,
    nuisance: ope.OpeNuisances,
    masks: Mapping[str, NDArray[np.float64]],
    confidence: float,
) -> pd.DataFrame:
    cost = frame["coupon_cost"].to_numpy(dtype=float)
    refund = frame["any_refund_30d"].to_numpy(dtype=float)
    t = frame["treatment"].to_numpy(dtype=float)
    rows: list[dict[str, Any]] = []
    for name in CANDIDATE_POLICIES:
        pi = ope.require_policy(masks[name], len(frame), name=name)
        components = {
            "coupon_cost_total_per_assigned_user": (
                "cny_per_user",
                ope.policy_cost_dr(pi, cost, t, nuisance.cost_mu1, nuisance.propensity),
            ),
            "refund_rate_30d": (
                "rate",
                ope.policy_guardrail_dr(
                    pi, refund, t, nuisance.refund_mu1, nuisance.refund_mu0,
                    nuisance.propensity,
                ),
            ),
        }
        for component, (unit, (value, influence)) in components.items():
            se = influence_se(influence)
            low, high = normal_interval(value, se, confidence)
            rows.append({
                "policy": name,
                "component": component,
                "unit": unit,
                "value": value,
                "se": se,
                "ci_low": low,
                "ci_high": high,
                "n": len(frame),
            })
    return pd.DataFrame(rows).loc[:, list(ope.COMPONENT_COLUMNS)]


def family_table(contrast_frame: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """对配置家族内的两条 DR 配对差做单侧 Holm，并给出同族反演下界。

    ``adjusted_alpha`` 是逐步阈值 ``alpha/(m-rank+1)``，供同族反演区间使用；
    ``holm_adjusted_p_value`` 是累计调整 p。两种判定等价：
    ``holm_adjusted_p_value <= holm_alpha`` 当且仅当逐步检验拒绝。
    """
    block = cfg.section("evaluation.decision.benefit_evidence")
    family = [str(name) for name in block["family"]]
    alpha = float(block["family_alpha_one_sided"])
    if set(family) != set(FAMILY_CONTRASTS):
        raise ValueError(
            f"配置家族 {family} 与本模块登记的 {sorted(FAMILY_CONTRASTS)} 不一致"
        )
    dr_rows = contrast_frame.loc[contrast_frame["estimator"] == "dr_increment"]
    p_values: dict[str, float] = {}
    for name in family:
        block_rows = dr_rows.loc[dr_rows["contrast"] == name]
        if len(block_rows) != 1:
            raise ValueError(f"contrast {name} 的 DR 行应恰为 1，收到 {len(block_rows)}")
        p_values[name] = float(block_rows["one_sided_p_value"].iloc[0])
    holm = ope.holm_step_down(p_values, alpha)
    rows: list[dict[str, Any]] = []
    for name in family:
        row = dr_rows.loc[dr_rows["contrast"] == name].iloc[0]
        outcome = holm[name]
        rejected = bool(outcome["rejected"])
        adjusted_alpha = float(outcome["adjusted_alpha"])
        if rejected:
            z = NormalDist().inv_cdf(1.0 - adjusted_alpha)
            lower = float(row["diff_cny_per_user"]) - z * float(row["se_diff"])
            interval_level = 1.0 - adjusted_alpha
        else:
            lower = float("nan")
            interval_level = float("nan")
        rows.append({
            "contrast": name,
            "policy": row["policy"],
            "baseline": row["baseline"],
            "estimator": "dr_increment",
            "diff_cny_per_user": float(row["diff_cny_per_user"]),
            "se_diff": float(row["se_diff"]),
            "ci_low": float(row["ci_low"]),
            "ci_high": float(row["ci_high"]),
            "one_sided_p_value": float(outcome["p_value"]),
            "adjusted_alpha": adjusted_alpha,
            "holm_adjusted_p_value": float(outcome["adjusted_p_value"]),
            "holm_alpha": alpha,
            "holm_rejected": rejected,
            "holm_lower_bound_cny_per_user": lower,
            "holm_confidence_level": interval_level,
            "claim_passed": rejected,
            "n": int(row["n"]),
        })
    return pd.DataFrame(rows).loc[:, list(FAMILY_TABLE_COLUMNS)]


@dataclass(frozen=True)
class F01OpeBundle:
    """一次交叉拟合产出的 F01 OPE 表。"""

    value_table: pd.DataFrame
    contrast_table: pd.DataFrame
    cost_table: pd.DataFrame
    family: pd.DataFrame
    gates: dict[float, dict[str, dict]]
    nuisance_diagnostics: dict[str, Any]
    nuisance_sha256: str
    primary_budget_cny_per_user: float


def _nuisance_sha256(nuisance: ope.OpeNuisances) -> str:
    digest = hashlib.sha256()
    for label, array in (
        ("mu1", nuisance.mu1),
        ("mu0", nuisance.mu0),
        ("propensity", nuisance.propensity),
        ("fold_id", nuisance.fold_id),
        ("cost_mu1", nuisance.cost_mu1),
        ("refund_mu1", nuisance.refund_mu1),
        ("refund_mu0", nuisance.refund_mu0),
    ):
        digest.update(_array_sha256(np.asarray(array), label=label).encode("utf-8"))
    digest.update(str(nuisance.propensity_source).encode("utf-8"))
    return digest.hexdigest()


def ope_bundle(
    frame: pd.DataFrame,
    features: Any,
    policy_frames: Mapping[float, pd.DataFrame],
    cfg: Config,
    *,
    seed_index: int = 0,
) -> F01OpeBundle:
    """一次交叉拟合，产出所有预算的 OPE 价值/配对差/成本表与主预算 Holm。"""
    if "user_id" not in frame.columns or not frame["user_id"].is_monotonic_increasing:
        raise ValueError("观测表必须已按 user_id 升序；features 不会重排")
    observed = ope.require_observed_frame(frame)
    if tuple(observed["user_id"]) != tuple(frame["user_id"]):
        raise ValueError("require_observed_frame 改动了行序，特征对齐失效")
    if "design_probability" not in observed.columns:
        raise ValueError("F01 要求观测表带 design_probability（known_design）")
    design = _require_design_vector(
        observed["design_probability"].to_numpy(dtype=float),
        observed["user_id"].to_numpy(),
    )
    X = np.asarray(features, dtype=float)
    if X.ndim != 2 or X.shape[0] != len(observed):
        raise ValueError("features 必须是 (n, p) 矩阵且与观测表行数一致")
    user_id = observed["user_id"].to_numpy()
    masks_by_budget = {
        float(per_user): _align_policy_masks(policy_frame, user_id)
        for per_user, policy_frame in policy_frames.items()
    }
    if not masks_by_budget:
        raise ValueError("至少需要一个预算的名单")
    primary = float(
        cfg.require("evaluation.independent_validation.primary_budget_cny_per_user")
    )
    if not any(np.isclose(primary, value, rtol=0.0, atol=1e-12)
               for value in masks_by_budget):
        raise ValueError(f"policy_frames 缺少主预算 {primary}")
    nuisance = ope.fit_ope_nuisances(
        observed,
        X,
        cfg,
        propensity_source="known_design",
        design_probability=design,
        seed_index=seed_index,
    )
    confidence = float(cfg.require("evaluation.confidence_level"))
    values: list[pd.DataFrame] = []
    contrasts: list[pd.DataFrame] = []
    costs: list[pd.DataFrame] = []
    gates: dict[float, dict[str, dict]] = {}
    for per_user in sorted(masks_by_budget):
        masks = masks_by_budget[per_user]
        value_frame, gate = _value_table(observed, nuisance, masks, cfg, confidence)
        value_frame.insert(0, "per_user_budget_cny", per_user)
        contrast_frame = _contrast_table(observed, nuisance, masks, confidence)
        contrast_frame.insert(0, "per_user_budget_cny", per_user)
        cost_frame = _cost_table(observed, nuisance, masks, confidence)
        cost_frame.insert(0, "per_user_budget_cny", per_user)
        values.append(value_frame)
        contrasts.append(contrast_frame)
        costs.append(cost_frame)
        gates[per_user] = gate
    value_table = pd.concat(values, ignore_index=True)
    contrast_table = pd.concat(contrasts, ignore_index=True)
    cost_table = pd.concat(costs, ignore_index=True)
    primary_contrasts = contrast_table.loc[
        np.isclose(contrast_table["per_user_budget_cny"], primary, rtol=0.0, atol=1e-12)
    ]
    family = family_table(primary_contrasts, cfg)
    return F01OpeBundle(
        value_table=value_table.loc[:, list(VALUE_TABLE_COLUMNS)],
        contrast_table=contrast_table.loc[:, list(CONTRAST_TABLE_COLUMNS)],
        cost_table=cost_table.loc[:, list(COST_TABLE_COLUMNS)],
        family=family,
        gates=gates,
        nuisance_diagnostics=nuisance.diagnostics(),
        nuisance_sha256=_nuisance_sha256(nuisance),
        primary_budget_cny_per_user=primary,
    )


# --------------------------------------------------------------------------- #
# 观测估计 vs 冻结后真值审计
# --------------------------------------------------------------------------- #
def ope_vs_audit_table(
    bundle: F01OpeBundle,
    audit_table: pd.DataFrame,
    cfg: Config,
) -> pd.DataFrame:
    """把 OPE 估计与真值审计并排；只作审计对账，不用真值回头修改任何名单。"""
    if set(audit_table["policy"]) != set(CANDIDATE_POLICIES):
        raise ValueError("审计表策略集合与候选名单不一致")
    dr = bundle.value_table.loc[bundle.value_table["estimator"] == "dr_increment"]
    cost = bundle.cost_table.loc[
        bundle.cost_table["component"] == "coupon_cost_total_per_assigned_user"
    ]
    rows: list[dict[str, Any]] = []
    for per_user in sorted(bundle.gates):
        value_block = dr.loc[
            np.isclose(dr["per_user_budget_cny"], per_user, rtol=0.0, atol=1e-12)
        ].set_index("policy")
        cost_block = cost.loc[
            np.isclose(cost["per_user_budget_cny"], per_user, rtol=0.0, atol=1e-12)
        ].set_index("policy")
        audit_block = audit_table.loc[
            np.isclose(
                audit_table["per_user_budget_cny"], per_user, rtol=0.0, atol=1e-12
            )
        ].set_index("policy")
        if set(value_block.index) != set(CANDIDATE_POLICIES):
            raise ValueError(f"预算 {per_user} 的 OPE 价值表缺策略")
        baseline_value = float(value_block.loc["no_coupon", "value_cny_per_user"])
        for name in CANDIDATE_POLICIES:
            ope_increment = float(value_block.loc[name, "value_cny_per_user"]) - baseline_value
            audit_increment = float(
                audit_block.loc[name, "audit_increment_vs_no_coupon_cny_per_user"]
            )
            ope_spend = float(cost_block.loc[name, "value"])
            audit_spend = float(audit_block.loc[name, "audit_spend_per_user_cny"])
            rows.append({
                "per_user_budget_cny": per_user,
                "comparison": "policy_vs_no_coupon",
                "name": name,
                "ope_value_cny_per_user": ope_increment,
                "audit_value_cny_per_user": audit_increment,
                "value_error_cny_per_user": ope_increment - audit_increment,
                "ope_spend_per_user_cny": ope_spend,
                "audit_spend_per_user_cny": audit_spend,
                "spend_error_cny_per_user": ope_spend - audit_spend,
                "reliability_passed": bool(
                    value_block.loc[name, "reliability_passed"]
                ),
                "holm_rejected": float("nan"),
                "sign_agrees": bool(np.sign(ope_increment) == np.sign(audit_increment)),
            })
        contrast_block = bundle.contrast_table.loc[
            (np.isclose(
                bundle.contrast_table["per_user_budget_cny"], per_user,
                rtol=0.0, atol=1e-12,
            ))
            & (bundle.contrast_table["estimator"] == "dr_increment")
        ].set_index("contrast")
        family_block = bundle.family.set_index("contrast")
        for contrast, (policy_name, baseline_name) in FAMILY_CONTRASTS.items():
            ope_diff = float(contrast_block.loc[contrast, "diff_cny_per_user"])
            audit_diff = float(
                audit_block.loc[policy_name, "audit_increment_vs_no_coupon_cny_per_user"]
                - audit_block.loc[baseline_name, "audit_increment_vs_no_coupon_cny_per_user"]
            )
            holm_value: Any = float("nan")
            if np.isclose(
                per_user, bundle.primary_budget_cny_per_user, rtol=0.0, atol=1e-12
            ) and contrast in family_block.index:
                holm_value = bool(family_block.loc[contrast, "holm_rejected"])
            rows.append({
                "per_user_budget_cny": per_user,
                "comparison": "contrast",
                "name": contrast,
                "ope_value_cny_per_user": ope_diff,
                "audit_value_cny_per_user": audit_diff,
                "value_error_cny_per_user": ope_diff - audit_diff,
                "ope_spend_per_user_cny": float("nan"),
                "audit_spend_per_user_cny": float("nan"),
                "spend_error_cny_per_user": float("nan"),
                "reliability_passed": bool(
                    bundle.gates[per_user][policy_name]["passed"]
                ),
                "holm_rejected": holm_value,
                "sign_agrees": bool(np.sign(ope_diff) == np.sign(audit_diff)),
            })
    return pd.DataFrame(rows).loc[:, list(OPE_VS_AUDIT_COLUMNS)]


def config_family(cfg: Config) -> list[str]:
    """读配置家族名（供脚本打印/断言）。"""
    return [str(name) for name in cfg.require(
        "evaluation.decision.benefit_evidence.family"
    )]


def check_family_registered(cfg: Config) -> None:
    """配置家族与模块登记必须完全一致；不一致直接报错。"""
    family = config_family(cfg)
    if set(family) != set(FAMILY_CONTRASTS):
        raise ValueError(
            f"配置家族 {family} 与本模块登记的 {sorted(FAMILY_CONTRASTS)} 不一致"
        )


__all__ = [
    "AUDIT_TABLE_COLUMNS",
    "CANDIDATE_POLICIES",
    "CONTRAST_TABLE_COLUMNS",
    "COST_TABLE_COLUMNS",
    "F01OpeBundle",
    "FAMILY_CONTRASTS",
    "FAMILY_TABLE_COLUMNS",
    "FREEZE_COLUMNS",
    "FREEZE_SCHEMA",
    "OBSERVED_COLUMNS",
    "OPE_VS_AUDIT_COLUMNS",
    "PRIMARY_POLICY",
    "VALUE_TABLE_COLUMNS",
    "budget_key",
    "build_freeze_manifest",
    "build_observed_frame",
    "build_policies",
    "check_family_registered",
    "family_table",
    "influence_se",
    "normal_interval",
    "ope_bundle",
    "ope_vs_audit_table",
    "require_freeze_frame",
    "require_truth_frame",
    "truth_audit_table",
    "verify_freeze_manifest",
]
