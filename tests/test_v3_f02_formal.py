"""F02 正式多 rep 聚合的契约测试：只读产物、rep 配对、拒绝口径漂移。

覆盖：
- 通过率按 rep 计、Clopper-Pearson 区间、MC 标准误，不产出合并 p 值；
- rep_id 缺口 / 重复、status 非 formal、formal_approval 为空、source_hashes 漂移、
  decision/freeze 声明含真值列，均必须抛错；
- ``_as_bool`` 不对未知字符串做静默转换。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.evaluation.v3_f02 import (
    ARMS,
    ARM_SUMMARY_COLUMNS,
    CONTRAST_COLUMNS,
    DECISION_CLAIMS,
    DECISION_COLUMNS,
    GUARDRAIL_COLUMNS,
)
from causal_growth.evaluation.v3_f02_formal import (
    aggregate_f02,
    load_formal_rep,
    plan_formal_shard,
)

_ALIAS = {claim: alias for claim, alias, _, _ in DECISION_CLAIMS}
_ARMS = {claim: (left, right) for claim, _, left, right in DECISION_CLAIMS}
_SOURCE_HASHES = {"src/causal_growth/evaluation/v3_f02.py": "deadbeef"}
_APPROVAL = "TEST-APPROVAL-01"


def _decision_rows(reps: int, pass_pattern: dict[str, list[bool]], diff: dict[str, float]):
    rows = []
    for claim in _ALIAS:
        for index in range(reps):
            left, right = _ARMS[claim]
            passed = pass_pattern[claim][index]
            rows.append({
                "claim": claim,
                "contrast": f"{left}_minus_{right}",
                "configured_contrast": _ALIAS[claim],
                "threshold_cny_per_user": 0.0,
                "diff_cny_per_user": diff[claim] + index,
                "se": 0.05,
                "one_sided_p_value": 0.4 if not passed else 0.01,
                "adjusted_alpha": 0.05 if claim == "coupon_worth_issuing" else 0.025,
                "holm_adjusted_p_value": 0.8 if not passed else 0.02,
                "passes_adjusted_test": passed,
                "adjusted_lower_confidence_limit": -0.07 if not passed else 0.02,
                "n_left": 10,
                "n_right": 10,
            })
    return pd.DataFrame(rows).loc[:, list(DECISION_COLUMNS)]


def _write_rep(
    root: Path,
    rep_id: int,
    *,
    status: str = "formal",
    approval: str | None = _APPROVAL,
    source_hashes: dict[str, str] | None = None,
    config_hash: str = "cfg-1",
    decision: pd.DataFrame | None = None,
    rep_offset: int = 0,
    policy: str = "greedy_incremental_profit_per_cost",
) -> Path:
    directory = root / f"rep{rep_id}"
    directory.mkdir(parents=True, exist_ok=True)

    arms = pd.DataFrame({
        "arm": list(ARMS),
        "n_assigned": [10, 10, 10],
        "n_issued": [0, 5, 6],
        "issue_share": [0.0, 0.5, 0.6],
        "mean_net_profit_cny": [1.0 + rep_offset, 1.1, 1.2],
        "se_net_profit_cny": [0.2, 0.2, 0.2],
        "mean_coupon_cost_cny": [0.0, 0.1, 0.12],
        "total_coupon_cost_cny": [0.0, 1.0 + rep_offset, 1.2],
        "n_refund": [1, 1, 2],
        "refund_rate": [0.1, 0.1, 0.2],
    }).loc[:, list(ARM_SUMMARY_COLUMNS)]
    arms.to_csv(directory / "arm_summary.csv", index=False, encoding="utf-8-sig")

    if decision is None:
        decision = _decision_rows(
            1,
            {"coupon_worth_issuing": [rep_offset % 2 == 0],
             "targeting_better_than_random": [rep_offset >= 1]},
            {"coupon_worth_issuing": 0.01 + rep_offset,
             "targeting_better_than_random": 0.02 + rep_offset},
        )
    decision.to_csv(directory / "decision.csv", index=False, encoding="utf-8-sig")

    guardrail = pd.DataFrame([{
        "contrast": "selected_targeted_policy_minus_no_coupon",
        "metric": "any_refund_30d_per_assigned_user",
        "unit": "per_assigned_user",
        "margin": 0.005,
        "alpha_one_sided": 0.05,
        "left_rate": 0.2,
        "right_rate": 0.1,
        "diff": 0.1 + 0.01 * rep_offset,
        "se": 0.05,
        "ci_one_sided_upper": 0.2,
        "passed": rep_offset < 2,
        "n_left": 10,
        "n_right": 10,
        "n_left_refunds": 2,
        "n_right_refunds": 1,
        "method": "wald_unpooled_noninferiority",
    }]).loc[:, list(GUARDRAIL_COLUMNS)]
    guardrail.to_csv(directory / "guardrail.csv", index=False, encoding="utf-8-sig")

    contrasts = pd.DataFrame({
        "contrast": [
            "selected_targeted_policy_minus_no_coupon",
            "selected_targeted_policy_minus_same_budget_random",
            "same_budget_random_minus_no_coupon",
        ],
        "diff_cny_per_user": [0.1 + rep_offset, 0.02, 0.08],
        "se": 0.05,
        "ci_low": -0.05,
        "ci_high": 0.3,
        "two_sided_p_value": 0.5,
        "n_left": 10,
        "n_right": 10,
    }).loc[:, list(CONTRAST_COLUMNS)]
    contrasts.to_csv(directory / "itt_contrasts.csv", index=False, encoding="utf-8-sig")

    manifest = {
        "phase": "F02",
        "status": status,
        "formal_approval": approval,
        "audit_unlock_order": "freeze_files_written_then_audit_realized_worlds",
        "rep_id": rep_id,
        "n_users": 30,
        "config_hash": config_hash,
        "source_hashes": source_hashes or dict(_SOURCE_HASHES),
        "selected_policy": policy,
        "decision_hash": f"decision-{rep_id}",
        "guardrail_hash": f"guardrail-{rep_id}",
        "arms": {
            "no_coupon": {"predicted_spend_cny": 0.0},
            "random_same_budget": {"predicted_spend_cny": 1.1},
            "selected_targeted_policy": {"predicted_spend_cny": 1.3},
        },
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (directory / "decision.json").write_text(
        json.dumps({"truth_columns_present": False}), encoding="utf-8"
    )
    (directory / "freeze.json").write_text(
        json.dumps({
            "truth_columns_present": False,
            "decision_hash": manifest["decision_hash"],
            "guardrail_hash": manifest["guardrail_hash"],
        }),
        encoding="utf-8",
    )
    return directory


def _make_reps(root: Path, count: int) -> list[Path]:
    return [_write_rep(root, index, rep_offset=index) for index in range(count)]


def test_aggregate_reports_rep_level_pass_rate_and_mc_se(tmp_path: Path) -> None:
    reps = _make_reps(tmp_path, 4)
    claims, guardrail, itt, spend, meta = aggregate_f02(reps, expected_reps=4)

    coupon = claims.loc[claims["claim"] == "coupon_worth_issuing"].iloc[0]
    assert coupon["n_reps"] == 4
    assert coupon["pass_count"] == 2
    assert coupon["pass_rate"] == pytest.approx(0.5)
    expected_low = 0.067585
    expected_high = 0.932415
    assert coupon["pass_rate_ci_low"] == pytest.approx(expected_low, abs=1e-5)
    assert coupon["pass_rate_ci_high"] == pytest.approx(expected_high, abs=1e-5)
    assert coupon["mean_diff_cny_per_user"] == pytest.approx(0.01 + 1.5)
    assert coupon["mc_se_diff"] == pytest.approx(np.std([1.0, 2.0, 3.0, 4.0], ddof=1) / 2)

    targeting = claims.loc[claims["claim"] == "targeting_better_than_random"].iloc[0]
    assert targeting["pass_count"] == 3

    assert guardrail.iloc[0]["pass_count"] == 2
    assert guardrail.iloc[0]["n_reps"] == 4

    random_control = itt.loc[itt["contrast"] == "same_budget_random_minus_no_coupon"].iloc[0]
    assert random_control["n_reps"] == 4
    assert random_control["mean_diff_cny_per_user"] == pytest.approx(0.08)

    assert "pooled" not in " ".join(claims.columns)
    assert "combined" not in " ".join(claims.columns)
    assert "mean_one_sided_p_value" in claims.columns
    assert meta["aggregation"] == "rep_level_paired_pass_rate_and_mc_se_no_pooled_p_value"
    assert meta["n_reps"] == 4

    assert spend.loc[spend["arm"] == "no_coupon", "mean_total_coupon_cost_cny"].iloc[0] == 0
    targeted = spend.loc[spend["arm"] == "selected_targeted_policy"].iloc[0]
    assert targeted["mean_total_coupon_cost_cny"] > 0
    assert targeted["max_realized_to_predicted"] >= targeted["min_realized_to_predicted"]


def test_load_rejects_non_formal_and_missing_approval(tmp_path: Path) -> None:
    provisional = _write_rep(tmp_path, 0, status="provisional")
    with pytest.raises(ValueError, match="formal"):
        load_formal_rep(provisional)

    missing = _write_rep(tmp_path, 1, approval="   ")
    with pytest.raises(ValueError, match="formal_approval"):
        load_formal_rep(missing)


def test_load_rejects_truth_columns_present(tmp_path: Path) -> None:
    directory = _write_rep(tmp_path, 0)
    (directory / "decision.json").write_text(
        json.dumps({"truth_columns_present": True}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="真值列"):
        load_formal_rep(directory)


def test_aggregate_rejects_rep_id_gap_and_duplicate(tmp_path: Path) -> None:
    gap = [
        _write_rep(tmp_path / "gap", 0),
        _write_rep(tmp_path / "gap", 1),
        _write_rep(tmp_path / "gap", 3),
    ]
    with pytest.raises(ValueError, match="0\\.\\.2"):
        aggregate_f02(gap, expected_reps=3)

    same = [_write_rep(tmp_path / "dup", 0), _write_rep(tmp_path / "dup", 0)]
    with pytest.raises(ValueError, match="重复"):
        aggregate_f02(same, expected_reps=2)


def test_aggregate_rejects_source_hash_drift(tmp_path: Path) -> None:
    first = _write_rep(tmp_path / "a", 0)
    second = _write_rep(
        tmp_path / "b", 1, source_hashes={"src/causal_growth/evaluation/v3_f02.py": "cafe"}
    )
    with pytest.raises(ValueError, match="source_hashes"):
        aggregate_f02([first, second], expected_reps=2)


def test_aggregate_rejects_policy_drift(tmp_path: Path) -> None:
    first = _write_rep(tmp_path / "a", 0, policy="policy_a")
    second = _write_rep(tmp_path / "b", 1, policy="policy_b")
    with pytest.raises(ValueError, match="selected_policy"):
        aggregate_f02([first, second], expected_reps=2)


def test_load_rejects_missing_policy(tmp_path: Path) -> None:
    directory = _write_rep(tmp_path, 0)
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.pop("selected_policy")
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="selected_policy"):
        load_formal_rep(directory)


def test_as_bool_rejects_unknown_strings(tmp_path: Path) -> None:
    decision = _decision_rows(
        1,
        {"coupon_worth_issuing": [True], "targeting_better_than_random": [True]},
        {"coupon_worth_issuing": 0.01, "targeting_better_than_random": 0.02},
    )
    decision = decision.assign(
        passes_adjusted_test=decision["passes_adjusted_test"].map({True: "maybe", False: "no"})
    )
    directory = _write_rep(tmp_path, 0, decision=decision)
    with pytest.raises(ValueError, match="布尔"):
        aggregate_f02([directory], expected_reps=1)


def test_plan_formal_shard_runs_missing_and_resumes_matching(tmp_path: Path) -> None:
    _write_rep(tmp_path, 0)
    _write_rep(tmp_path, 2)
    to_run, skipped = plan_formal_shard(
        tmp_path,
        [0, 1, 2],
        config_hash="cfg-1",
        source_hashes=_SOURCE_HASHES,
        formal_approval=_APPROVAL,
        n_users=30,
        resume=True,
    )
    assert to_run == [1]
    assert skipped == [0, 2]

    with pytest.raises(ValueError, match="--resume"):
        plan_formal_shard(
            tmp_path, [0], config_hash="cfg-1", source_hashes=_SOURCE_HASHES,
            formal_approval=_APPROVAL, n_users=30, resume=False,
        )


def test_plan_formal_shard_rejects_drift_and_bad_approval(tmp_path: Path) -> None:
    _write_rep(tmp_path, 0)
    with pytest.raises(ValueError, match="config_hash"):
        plan_formal_shard(
            tmp_path, [0], config_hash="cfg-2", source_hashes=_SOURCE_HASHES,
            formal_approval=_APPROVAL, n_users=30, resume=True,
        )
    with pytest.raises(ValueError, match="登记号"):
        plan_formal_shard(
            tmp_path, [0], config_hash="cfg-1", source_hashes=_SOURCE_HASHES,
            formal_approval="OTHER", n_users=30, resume=True,
        )
    with pytest.raises(ValueError, match="不能为空"):
        plan_formal_shard(
            tmp_path, [], config_hash="cfg-1", source_hashes=_SOURCE_HASHES,
            formal_approval=_APPROVAL, n_users=30, resume=True,
        )
