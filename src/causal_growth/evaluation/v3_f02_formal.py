"""F02 正式多 rep 聚合：只读逐 rep 落盘产物，按 rep 配对报告。

回答哪个问题
------------
F02 的单 rep 只说明机制跑通；正式结论要回答：**在 200 个独立验证 rep 上，
两条预声明收益主张各自通过多少次、差值分布如何、护栏通过多少次**。

纪律
----
- 不把 200 个 rep 的 p 值合并成一个"总显著"：报告 rep 级通过率、通过率的
  Clopper-Pearson 区间、差值的均值与 MC 标准误（``sd/√R``）。
- 每个 rep 的检查在同一 rep 内独立完成；聚合只做描述，不重新做检验。
- 正式聚合要求每个 rep 的 ``status=formal``、``formal_approval`` 非空、
  ``config_hash`` 与 ``source_hashes`` 全 rep 一致，rep 编号恰好覆盖
  ``0..expected_reps-1``。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from causal_growth.evaluation.v3_f02 import (
    ARMS,
    DECISION_CLAIMS,
    DECISION_COLUMNS,
    GUARDRAIL_COLUMNS,
    ARM_SUMMARY_COLUMNS,
    CONTRAST_COLUMNS,
)

__all__ = [
    "CLAIM_AGG_COLUMNS",
    "GUARDRAIL_AGG_COLUMNS",
    "ITT_AGG_COLUMNS",
    "SPEND_AGG_COLUMNS",
    "aggregate_f02",
    "load_formal_rep",
    "plan_formal_shard",
]

CLAIM_AGG_COLUMNS = (
    "claim", "n_reps", "pass_count", "pass_rate",
    "pass_rate_ci_low", "pass_rate_ci_high",
    "mean_diff_cny_per_user", "mc_se_diff",
    "mean_one_sided_p_value", "median_holm_adjusted_p_value",
    "mean_adjusted_lower_confidence_limit",
)
GUARDRAIL_AGG_COLUMNS = (
    "contrast", "metric", "margin", "alpha_one_sided",
    "n_reps", "pass_count", "pass_rate", "pass_rate_ci_low", "pass_rate_ci_high",
    "mean_diff", "mc_se_diff", "mean_ci_one_sided_upper",
)
ITT_AGG_COLUMNS = (
    "contrast", "n_reps", "mean_diff_cny_per_user", "mc_se_diff",
    "mean_ci_low", "mean_ci_high", "positive_reps",
)
SPEND_AGG_COLUMNS = (
    "arm", "n_reps", "mean_total_coupon_cost_cny",
    "mean_realized_per_assigned_cny", "max_realized_per_assigned_cny",
    "mean_realized_to_predicted", "min_realized_to_predicted",
    "max_realized_to_predicted",
)

_CLAIM_ALIASES = {claim: alias for claim, alias, _, _ in DECISION_CLAIMS}
_CLAIM_ARMS = {claim: (left, right) for claim, _, left, right in DECISION_CLAIMS}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read_csv(path: Path, columns: Sequence[str]) -> pd.DataFrame:
    if not path.is_file():
        raise ValueError(f"缺少产物：{path}")
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{path} 缺少列：{missing}")
    return frame.loc[:, list(columns)]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"缺少产物：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} 不是 JSON 对象")
    return payload


def _mc_se(values: pd.Series) -> float:
    if len(values) <= 1:
        return float("nan")
    return float(values.std(ddof=1) / np.sqrt(len(values)))


def _as_bool(series: pd.Series, name: str) -> pd.Series:
    if series.dtype == bool:
        return series
    mapping = {True: True, False: False, "True": True, "False": False, 1: True, 0: False}
    if not set(series.unique()).issubset(mapping):
        raise ValueError(f"{name} 必须是布尔值")
    return series.map(mapping).astype(bool)


def _cp_interval(pass_count: int, n_reps: int) -> tuple[float, float]:
    interval = binomtest(int(pass_count), int(n_reps)).proportion_ci(
        confidence_level=0.95, method="exact"
    )
    return float(interval.low), float(interval.high)


def load_formal_rep(rep_dir: str | Path) -> dict[str, Any]:
    """读取并校验一个正式 rep 的六件套，返回聚合所需的最小视图。"""
    directory = Path(rep_dir)
    manifest = _read_json(directory / "manifest.json")
    _require(manifest.get("phase") == "F02", f"{directory} 不是 F02 产物")
    _require(manifest.get("status") == "formal", f"{directory} 不是 formal 产物")
    approval = manifest.get("formal_approval")
    _require(isinstance(approval, str) and bool(approval.strip()),
             f"{directory} 缺少 formal_approval")
    _require(
        manifest.get("audit_unlock_order")
        == "freeze_files_written_then_audit_realized_worlds",
        f"{directory} 的审计解锁顺序不符",
    )
    rep_id = manifest.get("rep_id")
    _require(isinstance(rep_id, int) and rep_id >= 0, f"{directory} 的 rep_id 非法")
    n_users = manifest.get("n_users")
    _require(isinstance(n_users, int) and n_users > 0, f"{directory} 的 n_users 非法")
    _require(isinstance(manifest.get("config_hash"), str), f"{directory} 缺少 config_hash")
    _require(isinstance(manifest.get("source_hashes"), dict), f"{directory} 缺少 source_hashes")

    decision = _read_csv(directory / "decision.csv", DECISION_COLUMNS)
    _require(len(decision) == len(DECISION_CLAIMS),
             f"{directory} 的 decision.csv 必须恰有 {len(DECISION_CLAIMS)} 行")
    _require(set(decision["claim"]) == set(_CLAIM_ALIASES),
             f"{directory} 的 decision.csv 主张集合不符")
    for row in decision.itertuples(index=False):
        _require(row.configured_contrast == _CLAIM_ALIASES[row.claim],
                 f"{directory} 的 {row.claim} 配置别名不符")
        left, right = _CLAIM_ARMS[row.claim]
        n_expected = {
            left: int(row.n_left),
            right: int(row.n_right),
        }
        _require(n_expected[left] > 0 and n_expected[right] > 0,
                 f"{directory} 的 {row.claim} 存在空臂")

    guardrail = _read_csv(directory / "guardrail.csv", GUARDRAIL_COLUMNS)
    _require(len(guardrail) == 1, f"{directory} 的 guardrail.csv 必须恰有一行")
    guard = guardrail.iloc[0]
    _require(guard["contrast"] == "selected_targeted_policy_minus_no_coupon",
             f"{directory} 的护栏对照不符")
    _require(float(guard["margin"]) > 0, f"{directory} 的护栏界值必须为正")
    _require(0 < float(guard["alpha_one_sided"]) < 1,
             f"{directory} 的护栏单侧 alpha 越界")

    arms = _read_csv(directory / "arm_summary.csv", ARM_SUMMARY_COLUMNS)
    _require(set(arms["arm"]) == set(ARMS), f"{directory} 的 arm_summary 臂集合不符")
    _require(int(arms["n_assigned"].sum()) == n_users,
             f"{directory} 的三臂人数之和与 n_users 不符")
    counts = dict(zip(arms["arm"], arms["n_assigned"]))
    for row in decision.itertuples(index=False):
        left, right = _CLAIM_ARMS[row.claim]
        _require(int(row.n_left) == int(counts[left]), f"{directory} 的 {row.claim} 左臂人数不符")
        _require(int(row.n_right) == int(counts[right]), f"{directory} 的 {row.claim} 右臂人数不符")

    contrasts = _read_csv(directory / "itt_contrasts.csv", CONTRAST_COLUMNS)
    _require(len(contrasts) == 3, f"{directory} 的 itt_contrasts.csv 必须恰有三行")

    decision_json = _read_json(directory / "decision.json")
    _require(decision_json.get("truth_columns_present") is False,
             f"{directory} 的 decision.json 标记了真值列")
    freeze = _read_json(directory / "freeze.json")
    _require(freeze.get("truth_columns_present") is False,
             f"{directory} 的 freeze.json 标记了真值列")
    _require(freeze.get("decision_hash") == manifest.get("decision_hash"),
             f"{directory} 的 decision_hash 与 freeze.json 不一致")
    _require(freeze.get("guardrail_hash") == manifest.get("guardrail_hash"),
             f"{directory} 的 guardrail_hash 与 freeze.json 不一致")

    return {
        "rep_id": int(rep_id),
        "n_users": int(n_users),
        "formal_approval": approval.strip(),
        "config_hash": str(manifest["config_hash"]),
        "source_hashes": manifest["source_hashes"],
        "decision": decision,
        "guardrail": guardrail,
        "arms": arms,
        "itt": contrasts,
        "manifest": manifest,
    }


def _aggregate_claims(reps: Sequence[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for claim in _CLAIM_ALIASES:
        block = pd.concat(
            [rep["decision"].loc[rep["decision"]["claim"] == claim] for rep in reps],
            ignore_index=True,
        )
        _require(len(block) == len(reps), f"{claim} 的 rep 行数不完整")
        passed = _as_bool(block["passes_adjusted_test"], f"{claim} 的 passes_adjusted_test")
        pass_count = int(passed.sum())
        low, high = _cp_interval(pass_count, len(block))
        rows.append({
            "claim": claim,
            "n_reps": len(block),
            "pass_count": pass_count,
            "pass_rate": pass_count / len(block),
            "pass_rate_ci_low": low,
            "pass_rate_ci_high": high,
            "mean_diff_cny_per_user": float(block["diff_cny_per_user"].mean()),
            "mc_se_diff": _mc_se(block["diff_cny_per_user"]),
            "mean_one_sided_p_value": float(block["one_sided_p_value"].mean()),
            "median_holm_adjusted_p_value": float(block["holm_adjusted_p_value"].median()),
            "mean_adjusted_lower_confidence_limit": float(
                block["adjusted_lower_confidence_limit"].mean()
            ),
        })
    return pd.DataFrame(rows).loc[:, list(CLAIM_AGG_COLUMNS)]


def _aggregate_guardrail(reps: Sequence[dict[str, Any]]) -> pd.DataFrame:
    block = pd.concat([rep["guardrail"] for rep in reps], ignore_index=True)
    passed = _as_bool(block["passed"], "guardrail 的 passed")
    pass_count = int(passed.sum())
    low, high = _cp_interval(pass_count, len(block))
    return pd.DataFrame([{
        "contrast": str(block["contrast"].iloc[0]),
        "metric": str(block["metric"].iloc[0]),
        "margin": float(block["margin"].iloc[0]),
        "alpha_one_sided": float(block["alpha_one_sided"].iloc[0]),
        "n_reps": len(block),
        "pass_count": pass_count,
        "pass_rate": pass_count / len(block),
        "pass_rate_ci_low": low,
        "pass_rate_ci_high": high,
        "mean_diff": float(block["diff"].mean()),
        "mc_se_diff": _mc_se(block["diff"]),
        "mean_ci_one_sided_upper": float(block["ci_one_sided_upper"].mean()),
    }]).loc[:, list(GUARDRAIL_AGG_COLUMNS)]


def _aggregate_itt(reps: Sequence[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    contrasts = pd.concat([rep["itt"] for rep in reps], ignore_index=True)
    for name, block in contrasts.groupby("contrast", sort=True):
        rows.append({
            "contrast": name,
            "n_reps": len(block),
            "mean_diff_cny_per_user": float(block["diff_cny_per_user"].mean()),
            "mc_se_diff": _mc_se(block["diff_cny_per_user"]),
            "mean_ci_low": float(block["ci_low"].mean()),
            "mean_ci_high": float(block["ci_high"].mean()),
            "positive_reps": int((block["diff_cny_per_user"] > 0).sum()),
        })
    return pd.DataFrame(rows).loc[:, list(ITT_AGG_COLUMNS)]


def _aggregate_spend(reps: Sequence[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        records: list[dict[str, float]] = []
        for rep in reps:
            block = rep["arms"].loc[rep["arms"]["arm"] == arm]
            _require(len(block) == 1, f"rep {rep['rep_id']} 的 {arm} 行数不为 1")
            row = block.iloc[0]
            predicted = float(rep["manifest"]["arms"][arm]["predicted_spend_cny"])
            total = float(row["total_coupon_cost_cny"])
            assigned = int(row["n_assigned"])
            ratio = total / predicted if predicted > 0 else float("nan")
            records.append({
                "total": total,
                "per_assigned": total / assigned,
                "ratio": ratio,
            })
        frame = pd.DataFrame(records)
        rows.append({
            "arm": arm,
            "n_reps": len(frame),
            "mean_total_coupon_cost_cny": float(frame["total"].mean()),
            "mean_realized_per_assigned_cny": float(frame["per_assigned"].mean()),
            "max_realized_per_assigned_cny": float(frame["per_assigned"].max()),
            "mean_realized_to_predicted": float(frame["ratio"].mean()),
            "min_realized_to_predicted": float(frame["ratio"].min()),
            "max_realized_to_predicted": float(frame["ratio"].max()),
        })
    return pd.DataFrame(rows).loc[:, list(SPEND_AGG_COLUMNS)]


def plan_formal_shard(
    out_root: str | Path,
    rep_ids: Sequence[int],
    *,
    config_hash: str,
    source_hashes: Mapping[str, Any],
    formal_approval: str,
    n_users: int,
    resume: bool,
) -> tuple[list[int], list[int]]:
    """决定一个正式分片里哪些 rep 要跑、哪些可复用；任何不一致都抛错。

    复用条件必须同时满足：``status=formal``、登记号、``config_hash``、
    ``source_hashes``、``n_users`` 全部与本次一致。旧产物只要有一项不同，
    就说明协议或代码变了，复用会让 200 个 rep 混入不同口径。
    """
    ids = [int(value) for value in rep_ids]
    _require(ids, "rep_ids 不能为空")
    _require(all(value >= 0 for value in ids), "rep_id 不能为负")
    _require(len(set(ids)) == len(ids), "rep_ids 有重复")
    approval = (formal_approval or "").strip()
    _require(bool(approval), "正式分片必须给出 formal_approval")
    root = Path(out_root)
    to_run: list[int] = []
    skipped: list[int] = []
    for rep_id in ids:
        manifest_path = root / f"rep{rep_id}" / "manifest.json"
        if not manifest_path.is_file():
            to_run.append(rep_id)
            continue
        _require(resume, f"{manifest_path} 已存在；只有 --resume 才允许复用")
        existing = _read_json(manifest_path)
        _require(existing.get("status") == "formal", f"{manifest_path} 不是 formal")
        _require(existing.get("formal_approval") == approval,
                 f"{manifest_path} 的登记号与本次不一致")
        _require(existing.get("config_hash") == config_hash,
                 f"{manifest_path} 的 config_hash 与本次不一致")
        _require(existing.get("source_hashes") == dict(source_hashes),
                 f"{manifest_path} 的 source_hashes 与本次不一致（源码已变）")
        _require(int(existing.get("n_users", -1)) == int(n_users),
                 f"{manifest_path} 的 n_users 与本次不一致")
        skipped.append(rep_id)
    return to_run, skipped


def aggregate_f02(
    rep_dirs: Sequence[str | Path], *, expected_reps: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """聚合正式 rep；任何缺失、重复、口径漂移都抛错。"""
    expected_reps = int(expected_reps)
    _require(expected_reps > 0, "expected_reps 必须为正")
    _require(len(rep_dirs) == expected_reps,
             f"rep 目录数 {len(rep_dirs)} 与 expected_reps={expected_reps} 不符")
    reps = [load_formal_rep(path) for path in rep_dirs]
    ids = [rep["rep_id"] for rep in reps]
    _require(len(set(ids)) == len(ids), "rep_id 重复")
    _require(set(ids) == set(range(expected_reps)),
             f"rep_id 未恰好覆盖 0..{expected_reps - 1}")
    approvals = {rep["formal_approval"] for rep in reps}
    _require(len(approvals) == 1, "formal_approval 跨 rep 不一致")
    configs = {rep["config_hash"] for rep in reps}
    _require(len(configs) == 1, "config_hash 跨 rep 不一致")
    n_users = {rep["n_users"] for rep in reps}
    _require(len(n_users) == 1, "n_users 跨 rep 不一致")
    source_hashes = {json.dumps(rep["source_hashes"], sort_keys=True) for rep in reps}
    _require(len(source_hashes) == 1, "source_hashes 跨 rep 不一致（运行期间源码被改动）")

    claims = _aggregate_claims(reps)
    guardrail = _aggregate_guardrail(reps)
    itt = _aggregate_itt(reps)
    spend = _aggregate_spend(reps)
    source_payload = json.dumps(reps[0]["source_hashes"], sort_keys=True).encode("utf-8")
    meta = {
        "phase": "F02_formal_aggregate",
        "status": "formal_r",
        "expected_reps": expected_reps,
        "n_reps": len(reps),
        "rep_ids": sorted(ids),
        "formal_approval": reps[0]["formal_approval"],
        "config_hash": reps[0]["config_hash"],
        "n_users_per_rep": next(iter(n_users)),
        "source_hashes_sha256": hashlib.sha256(source_payload).hexdigest(),
        "aggregation": "rep_level_paired_pass_rate_and_mc_se_no_pooled_p_value",
    }
    return claims, guardrail, itt, spend, meta
