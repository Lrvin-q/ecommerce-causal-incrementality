"""Verification-author tests for independent evidence and failed-attempt retention."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.evaluation import v3_mechanism_checks as checks
from causal_growth.rng import child_rng
from causal_growth.v3_config import load_v3_protocol
from causal_growth.v3_numerics import load_v3_numerics


def test_streaming_mean_and_mc_se_agree_with_full_sample() -> None:
    numerics = load_v3_numerics()
    values = child_rng(numerics.require("validation.master_seed"), "test.validation.moments").normal(size=numerics.require("validation.mechanism_check_n"))
    stats = checks.Moments()
    midpoint = len(values) // 2
    stats.add(values[:midpoint])
    stats.add(values[midpoint:])
    assert stats.n == len(values)
    assert stats.mean == pytest.approx(values.mean())
    assert stats.mean_se == pytest.approx(values.std(ddof=1) / np.sqrt(len(values)))
    assert np.isfinite(stats.sd_se) and stats.sd_se > 0


def test_independent_mc_keeps_zero_order_users_and_never_charges_control() -> None:
    cfg = load_v3_protocol().scenario("L0_P_main")
    numerics = load_v3_numerics()
    n = numerics.require("validation.mechanism_check_n")
    worlds = checks.independent_worlds(
        numerics.require("validation.conditional_mc_cart_cents")[0], cfg, n,
        seed=numerics.require("validation.master_seed"), stream="test.validation.independent_worlds", chunk=0,
        purchase_probabilities=(0, 1),
    )
    assert all(len(x) == n and np.all(x == 0) for x in worlds[0].values())
    assert np.all(worlds[1]["purchase_probability_7d"] == 1)
    assert np.all(worlds[1]["order_count"] >= 1)
    assert worlds[1]["coupon_cost"].max() <= cfg.require("business.coupon_reference_face")
    assert np.all(worlds[1]["coupon_cost"] >= 0)


def test_failed_check_is_written_before_raise(tmp_path: Path) -> None:
    run = checks.CheckRun(tmp_path, load_v3_numerics())
    run.check("fault_injection", "bad_result", 0, 1, tolerance=0)
    with pytest.raises(AssertionError, match="mechanism checks failed"):
        run.checkpoint()
    rows = pd.read_csv(tmp_path / "checks.csv", encoding="utf-8-sig")
    assert len(rows) == 1 and not rows.passed.iloc[0]
    assert rows.absolute_error.iloc[0] == 1


def test_failed_attempt_keeps_manifest_and_does_not_advance_formal_R(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def injected_failure(run: checks.CheckRun, protocol: object) -> None:
        run.invariant("injected_bad_stage", False)

    monkeypatch.setattr(checks, "check_amount_distribution", injected_failure)
    with pytest.raises(AssertionError):
        checks.run_mechanism_validation(tmp_path)
    manifest_path, = tmp_path.glob("phase_b_*/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["stages"][0]["status"] == "failed"
    assert manifest["formal_repetitions_completed"] == 0
    assert manifest["n_failed_checks"] == 1
    assert manifest["source_hashes"] and manifest["outputs"]["checks.csv"]
