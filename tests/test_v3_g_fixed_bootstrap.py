"""固定策略 bootstrap（协议 §7）的验收测试。

覆盖四件事：两臂差与点估计一致、随机流可复现且按 rep 分叉、非法输入必须响、
以及验证臂把 resample 数/预算档/区间落到逐 rep 表与 manifest。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.evaluation import v3_g_matrix as g
from causal_growth.v3_config import load_v3_protocol

CORE = "L1_main"
N_TINY = 400
REPO = Path(__file__).resolve().parents[1]
OVERLAY = REPO / "configs" / "budget" / "tier2_overlay.yaml"


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


@pytest.fixture(scope="module")
def plan(protocol):
    return g.load_budget_plan(protocol, overlay=OVERLAY)


def test_two_sample_bootstrap_matches_point_estimate_and_is_deterministic():
    rng = np.random.default_rng(0)
    targeted = rng.normal(2.0, 1.0, 500)
    random_arm = rng.normal(1.0, 1.0, 700)
    first = g.two_sample_bootstrap_diff(
        targeted, random_arm, resamples=200, master_seed=20240101, index=3
    )
    again = g.two_sample_bootstrap_diff(
        targeted, random_arm, resamples=200, master_seed=20240101, index=3
    )
    assert first == again, "同一 (seed, index) 必须逐位复现"
    assert first["point_diff"] == pytest.approx(
        float(targeted.mean() - random_arm.mean()), abs=1e-12
    )
    assert first["n_targeted"] == 500 and first["n_random"] == 700
    assert first["resamples"] == 200
    assert first["ci_low"] < first["ci_high"]
    assert first["bootstrap_mean_diff"] == pytest.approx(first["point_diff"], abs=0.2)

    other = g.two_sample_bootstrap_diff(
        targeted, random_arm, resamples=200, master_seed=20240101, index=4
    )
    assert other["point_diff"] == first["point_diff"], "点估计与随机流无关"
    assert other["bootstrap_mean_diff"] != first["bootstrap_mean_diff"], "不同 rep 必须分叉"


def test_bootstrap_rejects_bad_inputs():
    with pytest.raises(ValueError, match="次数"):
        g.two_sample_bootstrap_diff(
            np.zeros(5), np.zeros(5), resamples=0, master_seed=1, index=0
        )
    with pytest.raises(ValueError, match="两臂"):
        g.two_sample_bootstrap_diff(
            np.zeros(0), np.zeros(5), resamples=10, master_seed=1, index=0
        )


def test_identical_constant_arms_give_zero_interval():
    arm = np.full(40, 3.5)
    out = g.two_sample_bootstrap_diff(
        arm, arm.copy(), resamples=50, master_seed=1, index=0
    )
    assert out["point_diff"] == 0.0
    assert out["bootstrap_se"] == 0.0
    assert out["ci_low"] == 0.0 and out["ci_high"] == 0.0


def test_bootstrap_only_on_representative_rep(protocol, plan, tmp_path):
    with pytest.raises(ValueError, match="代表 rep"):
        g.run_g_rep(
            protocol, CORE, 1, out_dir=tmp_path / "rep1", n=N_TINY, plan=plan,
            models=("constant",), with_learning=False, with_validation=False,
            bootstrap_resamples=16,
        )


def test_formal_run_refuses_incomplete_bootstrap_scope(protocol, plan, tmp_path):
    with pytest.raises(ValueError, match="全预算"):
        g.run_g_rep(
            protocol, CORE, 0, out_dir=tmp_path / "formal", plan=plan,
            models=("constant",), with_learning=False, with_validation=False,
            bootstrap_resamples=16, status="formal", formal_approval="test-only",
        )


def test_validation_arm_records_fixed_bootstrap(protocol, plan, tmp_path):
    out = tmp_path / "run"
    row = g.run_g_rep(
        protocol, CORE, 0, out_dir=out, n=N_TINY, plan=plan,
        models=("constant",), with_learning=True, with_validation=True,
        bootstrap_resamples=64,
    )
    boot = row["validation_fixed_bootstrap"]
    assert boot is not None and boot["resamples"] == 64
    assert row["validation_bootstrap_resamples"] == 64
    assert row["validation_bootstrap_point_diff"] == pytest.approx(boot["point_diff"])
    assert row["validation_bootstrap_ci_low"] == pytest.approx(boot["ci_low"])

    frame = pd.read_csv(out / "validation" / "fixed_bootstrap.csv")
    assert len(frame) == 1
    assert int(frame.loc[0, "resamples"]) == 64
    assert float(frame.loc[0, "budget_cny_per_user"]) == pytest.approx(
        row["validation_budget_per_user"]
    )
    assert int(frame.loc[0, "n_targeted"]) + int(frame.loc[0, "n_random"]) <= int(
        row["validation_n"]
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fixed_bootstrap_resamples"] == 64
    assert manifest["fixed_bootstrap_scope"] == "representative_rep_primary_budget_only"
    assert manifest["fixed_bootstrap"]["resamples"] == 64


def test_resume_rejects_bootstrap_drift(protocol, plan, tmp_path):
    first = g.run_cell(
        protocol, CORE, out_root=tmp_path, reps=[0], target_reps=1,
        n=N_TINY, plan=plan, models=("constant",),
        with_learning=False, with_validation=False,
        bootstrap_resamples=0,
    )
    with pytest.raises(ValueError, match="bootstrap_resamples"):
        g.run_cell(
            protocol, CORE, out_root=tmp_path, reps=[0, 1], target_reps=2,
            n=N_TINY, plan=plan, models=("constant",),
            with_learning=False, with_validation=False,
            bootstrap_resamples=16,
            resume_from=first["rows_path"],
        )
