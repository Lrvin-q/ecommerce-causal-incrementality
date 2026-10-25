"""Local-power effect construction and rejection-rate entry point.

Every test runs at ``n <= 3000`` and never creates a formal repetition; the heavy
20-cell grid is exercised analytically on small reference panels only.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.data import v3_local_power_pipeline as local_power_pipeline
from causal_growth.data.v3_local_power_pipeline import (
    SOURCE_CHANGED_MARKER,
    audit_population_effect,
    design_mde_table,
    design_sigma_table,
    environment_fault,
    feasibility_table,
    local_power_plan,
    run_local_power_rep,
    summarize_local_power,
)
from causal_growth.data.v3_pipeline import build_observed_pipeline
from causal_growth.design.v3_power import profit_power, split_counts
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.dgp.v3_local_power import (
    DEFAULT_RELATIVE_TOLERANCE,
    LOCAL_POWER_EFFECT_CONSTRUCTION,
    LocalPowerInfeasible,
    build_reference_panel,
    calibrate_local_power_cell,
    configured_multiplier,
    increment_scale_key,
    mechanism_signature,
    profit_effect_curve,
    scaled_increment_config,
    verify_scaled_mechanism,
    x_only_integral_is_u_invariant,
)
from causal_growth.v3_config import load_v3_protocol

#: 小规模参考人群（唯一被允许的规模档：n <= 3000）。
REFERENCE_N = 600
#: 端到端 rep 的人群规模。
RUN_N = 300


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


@pytest.fixture(scope="module")
def l1_panel(protocol):
    return build_reference_panel(protocol.scenario("L1_main"), reference_n=REFERENCE_N)


@pytest.fixture(scope="module")
def l1_curve(l1_panel):
    return profit_effect_curve(l1_panel)


@pytest.fixture(scope="module")
def l0_panel(protocol):
    return build_reference_panel(protocol.scenario("L0_P_main"), reference_n=REFERENCE_N)


@pytest.fixture(scope="module")
def l3_panel(protocol):
    return build_reference_panel(protocol.scenario("L3_fixed_lt000"), reference_n=300)


@pytest.fixture(scope="module")
def panels(protocol):
    """四层基础场景各一块小参考面板（20 格可行性用）。"""
    return {base: build_reference_panel(protocol.scenario(base), reference_n=REFERENCE_N)
            for base in ("L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000")}


def _calibrate(protocol, panels, cell_id: str, mde: float):
    plan = [item for item in local_power_plan(protocol) if item.cell_id == cell_id][0]
    panel = panels[plan.base_scenario_id]
    curve = profit_effect_curve(panel)
    return calibrate_local_power_cell(panel, protocol.scenario(cell_id), design_mde=mde, curve=curve)


# --------------------------------------------------------------------------- #
# 效应构造：仿射关系与可逆性
# --------------------------------------------------------------------------- #
def test_curve_is_affine_and_invertible(l1_curve) -> None:
    """τ(s) = τ0 + s·Δ，且 scale_for_effect 是 effect_at 的精确逆。"""
    assert l1_curve.effect_per_unit_increment_scale > 0
    assert l1_curve.effect_at(0) == pytest.approx(l1_curve.effect_at_zero_increment, abs=0, rel=0)
    for scale in (0.0, 0.25, 1.0, 1.3):
        effect = l1_curve.effect_at(scale)
        assert l1_curve.scale_for_effect(effect) == pytest.approx(scale, rel=1e-12, abs=1e-15)
    # 仿射性：中点效应等于两端点效应的中点。
    midpoint = 0.5 * (l1_curve.effect_at(0.4) + l1_curve.effect_at(2.0))
    assert l1_curve.effect_at(1.2) == pytest.approx(midpoint, rel=1e-12)
    # 注册倍数 1 处的效应与闭式一致。
    assert l1_curve.effect_at_registered_scale == pytest.approx(
        l1_curve.effect_at(1.0), rel=1e-12,
    )


def test_multiplier_zero_targets_zero_and_needs_positive_increment(protocol, panels) -> None:
    """倍数 0 的目标是 0，achieved 必须恰为 0，且它靠**正**增量实现（不是 s=0）。"""
    plan = [item for item in local_power_plan(protocol) if item.cell_id == "L1_power_mde000"][0]
    assert plan.target_effect == 0.0
    calibration = _calibrate(protocol, panels, "L1_power_mde000", plan.design_mde)
    assert calibration.achieved_effect == pytest.approx(0.0, abs=1e-9)
    assert calibration.consistent
    assert calibration.increment_scale > 0
    assert calibration.increment_scale == pytest.approx(
        -calibration.curve.effect_at_zero_increment / calibration.curve.effect_per_unit_increment_scale,
        rel=1e-12,
    )
    # 增量零对照的真值显著为负：它不是零效应格。
    assert calibration.curve.effect_at_zero_increment < -0.3


def test_increment_null_matches_phase_b_negative_control(l0_panel) -> None:
    """L0 增量零负对照的解析真值必须复现 Phase B 审计的 −0.559 元/人。"""
    curve = profit_effect_curve(l0_panel)
    assert curve.effect_at_zero_increment == pytest.approx(-0.559, abs=0.02)


# --------------------------------------------------------------------------- #
# 可行域：越界抛错且报告上界
# --------------------------------------------------------------------------- #
def test_target_above_upper_bound_raises_with_the_bound(l1_curve) -> None:
    """超出机制可行域的目标效应必须抛错，且消息里带上界（不静默截断）。"""
    too_high = l1_curve.effect_upper * 1.5 + 1.0
    with pytest.raises(LocalPowerInfeasible) as excinfo:
        l1_curve.scale_for_effect(too_high)
    message = str(excinfo.value)
    assert "feasible upper bound" in message
    assert f"{l1_curve.effect_upper:.6f}" in message
    assert l1_curve.binding_constraint in message


def test_target_below_floor_raises(l1_curve) -> None:
    """低于"增量零"负对照真值的目标不可达：需要负增量。"""
    with pytest.raises(LocalPowerInfeasible, match="reachable floor"):
        l1_curve.scale_for_effect(l1_curve.effect_min - 0.5)


def test_registered_amplitude_cap_binds_for_layers(l1_curve, protocol) -> None:
    """L1/L2/L3 的机制自身上界 = maximum_purchase_increment / amplitude。"""
    maximum = float(protocol.scenario("L1_main").require("dgp.l1.maximum_purchase_increment"))
    amplitude = l1_curve.registered_amplitude
    assert amplitude is not None and amplitude > 0
    assert l1_curve.scale_bound_registered == pytest.approx(maximum / amplitude, rel=1e-12)
    assert l1_curve.scale_upper == min(l1_curve.scale_bound_legal, l1_curve.scale_bound_registered)
    assert l1_curve.binding_constraint == "registered_maximum_purchase_increment"
    assert l1_curve.effect_upper == pytest.approx(
        l1_curve.effect_at_zero_increment + l1_curve.scale_upper * l1_curve.effect_per_unit_increment_scale,
        rel=1e-12,
    )


# --------------------------------------------------------------------------- #
# achieved vs target
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cell_id", ["L1_power_mde050", "L1_power_mde100", "L1_power_mde200"])
def test_achieved_effect_matches_target_on_both_channels(protocol, panels, l1_panel, cell_id) -> None:
    """两条独立通道（构造式 + DGP 概率代码）都必须落在 1e-6 相对容差内。"""
    plan = [item for item in local_power_plan(protocol) if item.cell_id == cell_id][0]
    calibration = _calibrate(protocol, panels, cell_id, plan.design_mde)
    assert calibration.target_effect == pytest.approx(plan.multiplier * plan.design_mde, rel=1e-15)
    assert abs(calibration.achieved_effect - calibration.target_effect) <= (
        DEFAULT_RELATIVE_TOLERANCE * abs(calibration.target_effect) + 1e-12
    )
    assert calibration.relative_deviation is not None
    assert calibration.relative_deviation <= DEFAULT_RELATIVE_TOLERANCE
    verification = verify_scaled_mechanism(l1_panel, calibration)
    assert verification["passed"]
    assert verification["p0_max_abs_change"] == 0.0
    assert abs(verification["achieved_effect_dgp"] - calibration.target_effect) <= (
        DEFAULT_RELATIVE_TOLERANCE * abs(calibration.target_effect) + 1e-12
    )


def test_consistency_tolerance_is_enforced(protocol, panels) -> None:
    """把容差收紧到 0 时，浮点残差必须让自检失败（证明检查不是装饰）。"""
    plan = [item for item in local_power_plan(protocol) if item.cell_id == "L1_power_mde100"][0]
    panel = panels[plan.base_scenario_id]
    curve = profit_effect_curve(panel)
    with pytest.raises(Exception) as excinfo:
        calibrate_local_power_cell(
            panel, protocol.scenario(plan.cell_id), design_mde=plan.design_mde, curve=curve,
            relative_tolerance=1e-30,
        )
    assert "achieved" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# 概率增量合法性
# --------------------------------------------------------------------------- #
def test_probability_increments_stay_legal(l1_panel, l1_curve, protocol) -> None:
    """放缩只把 p1 抬到 (p0,1) 内：p0 不动、p1 单调、越界即抛。"""
    plan = [item for item in local_power_plan(protocol) if item.cell_id == "L1_power_mde200"][0]
    calibration = calibrate_local_power_cell(
        l1_panel, protocol.scenario("L1_power_mde200"), design_mde=plan.design_mde, curve=l1_curve,
    )
    p0 = l1_panel.p0
    previous = None
    for scale in (0.0, calibration.increment_scale, 1.0):
        p1 = p0 + (1.0 - p0) * scale * l1_panel.headroom
        assert np.all(p1 > 0.0) and np.all(p1 < 1.0)
        assert np.all(p1 >= p0)
        if previous is not None:
            assert np.all(p1 >= previous)
        previous = p1
    # 超过 p1 < 1 的数学上界必须抛，而不是被裁剪。
    with pytest.raises(LocalPowerInfeasible, match="legal"):
        _increment_check(l1_panel, l1_curve.scale_bound_legal + 1.0)


def _increment_check(panel, scale):
    """调用校准路径里的概率构造检查（复用同一条断言链）。"""
    from causal_growth.dgp.v3_local_power import _increment_probabilities

    return _increment_probabilities(panel, scale)


def test_l0_legal_bound_is_the_mathematical_one(l0_panel, protocol) -> None:
    """L0 齐次购买机制没有幅度上限，唯一上界是 p1 < 1。"""
    curve = profit_effect_curve(l0_panel)
    cfg = protocol.scenario("L0_P_main")
    increment = float(cfg.require("dgp.l0.purchase_increment"))
    p0 = float(np.mean(l0_panel.p0))
    assert curve.scale_bound_registered is None
    assert curve.scale_bound_legal == pytest.approx((1.0 - p0) / increment, rel=1e-9)
    assert curve.binding_constraint == "mathematical_p1_lt_1"


# --------------------------------------------------------------------------- #
# 派生配置：只改增量参数
# --------------------------------------------------------------------------- #
def _changed_paths(left: dict, right: dict, prefix: str = "") -> set[str]:
    changed: set[str] = set()
    for key in set(left) | set(right):
        path = f"{prefix}{key}"
        if key not in left or key not in right:
            changed.add(path)
            continue
        if isinstance(left[key], dict) and isinstance(right[key], dict):
            changed |= _changed_paths(left[key], right[key], f"{path}.")
        elif left[key] != right[key]:
            changed.add(path)
    return changed


def test_scaled_config_changes_only_the_increment(protocol, panels) -> None:
    """派生配置只改增量键；对照概率与其它机制参数一字不动。"""
    plan = [item for item in local_power_plan(protocol) if item.cell_id == "L1_power_mde150"][0]
    cfg = protocol.scenario(plan.cell_id)
    calibration = _calibrate(protocol, panels, plan.cell_id, plan.design_mde)
    derived = calibration.scaled_config()
    changed = _changed_paths(cfg.to_dict(), derived.to_dict())
    key = increment_scale_key(cfg)
    assert changed == {key}, changed
    assert float(derived.require(key)) == pytest.approx(
        calibration.increment_scale * float(cfg.require(key)), rel=1e-15,
    )
    assert calibration.scaled_config_hash == derived.hash(64)
    assert calibration.base_config_hash == cfg.hash(64)
    # 机制指纹不变：放缩增量不属于"换机制"。
    assert mechanism_signature(cfg) == mechanism_signature(derived)
    assert derived.require("active_scenario.id") == plan.cell_id
    # 冻结配置本身没有被改写。
    assert protocol.scenario(plan.cell_id).hash(64) == cfg.hash(64)
    assert calibration.effect_construction == LOCAL_POWER_EFFECT_CONSTRUCTION


def test_scaled_increment_config_rejects_negative_scale(protocol) -> None:
    """负倍数没有概率解释，必须抛。"""
    with pytest.raises(LocalPowerInfeasible):
        scaled_increment_config(protocol.scenario("L1_main"), -0.5)
    with pytest.raises(TypeError):
        scaled_increment_config(protocol.scenario("L1_main"), True)


def test_u_invariance_of_the_x_only_integral(l3_panel, protocol) -> None:
    """L3 的 X-only 积分与 audit-U 取值逐位无关（因此构造不读真值）。"""
    assert x_only_integral_is_u_invariant(protocol.scenario("L3_fixed_lt000"), l3_panel.users, rows=2)


# --------------------------------------------------------------------------- #
# 生成入口：默认拒绝 / 凭据不匹配拒绝 / 合法凭据放行
# --------------------------------------------------------------------------- #
def test_pipeline_refuses_without_authorization(protocol, tmp_path: Path) -> None:
    """不传凭据时行为与改动前一致：拒绝并声明需要校准入口。"""
    cell = protocol.scenario("L1_power_mde100")
    population = generate_v3_population(protocol.scenario("L1_main"), n=60)
    with pytest.raises(ValueError, match="calibrated"):
        build_observed_pipeline(*population.observation_bundle(), cell, directory=tmp_path / "refused",
                                run_id="refused", rep_id=0, stream_prefix="test.local_power.refused")
    assert not (tmp_path / "refused").exists()


def test_pipeline_rejects_foreign_or_stale_authorization(protocol, panels, tmp_path: Path) -> None:
    """凭据必须绑定本格、本倍数与本派生配置；错配一律拒绝。"""
    calibration = _calibrate(protocol, panels, "L1_power_mde100", 0.130262)
    other_cell = protocol.scenario("L1_power_mde200")
    with pytest.raises(ValueError, match="different"):
        build_observed_pipeline(*_fake_bundle(protocol, other_cell, calibration),
                                other_cell, directory=tmp_path / "wrong-cell",
                                run_id="wrong", rep_id=0, stream_prefix="test.local_power.wrong",
                                local_power_authorization=calibration)
    # 用本格的派生配置但故意改一个机制键：哈希不匹配必须拒绝。
    tampered = calibration.scaled_config().with_overrides({"business.refund_rate": 0.0750001})
    tampered_population = generate_v3_population(tampered, n=60)
    with pytest.raises(ValueError, match="scaled configuration"):
        build_observed_pipeline(*tampered_population.observation_bundle(), tampered,
                                directory=tmp_path / "tampered",
                                run_id="tampered", rep_id=0, stream_prefix="test.local_power.tampered",
                                local_power_authorization=calibration)


def _fake_bundle(protocol, cfg, calibration):
    population = generate_v3_population(protocol.scenario("L1_main"), n=60)
    return population.observation_bundle()


def test_pipeline_runs_with_authorization_and_records_it(
    protocol, panels, tmp_path: Path,
) -> None:
    """合法凭据放行：五表链路跑通，manifest 记录放行对象与一致的 achieved effect。"""
    calibration = _calibrate(protocol, panels, "L1_power_mde100", 0.130262)
    cfg = calibration.scaled_config()
    population = generate_v3_population(cfg, n=120)
    result = build_observed_pipeline(
        *population.observation_bundle(), cfg, directory=tmp_path / "authorized",
        run_id="authorized", rep_id=0, stream_prefix="test.local_power.ok",
        local_power_authorization=calibration,
    )
    assert len(result.dataset.observations) == 120
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    record = manifest["local_power_authorization"]
    assert record["cell_id"] == "L1_power_mde100"
    assert record["consistent"] is True
    assert record["scaled_config_hash"] == cfg.hash(64)
    assert record["effect_construction"] == LOCAL_POWER_EFFECT_CONSTRUCTION
    assert manifest["formal_repetitions_completed"] == 0


def test_base_scenario_manifest_has_no_local_power_record(protocol, tmp_path: Path) -> None:
    """基础场景的 manifest 不新增字段（行为不变）。"""
    cfg = protocol.scenario("L1_main")
    population = generate_v3_population(cfg, n=80)
    result = build_observed_pipeline(*population.observation_bundle(), cfg,
                                     directory=tmp_path / "base", run_id="base", rep_id=0,
                                     stream_prefix="test.local_power.base")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert "local_power_authorization" not in manifest


# --------------------------------------------------------------------------- #
# 单 rep 链路与拒绝率统计
# --------------------------------------------------------------------------- #
def test_single_rep_produces_itt_and_audits_the_realized_effect(
    protocol, panels, tmp_path: Path,
) -> None:
    """一个 rep：ITT 出 diff/p，审计列复现目标效应方向，且增量真的落到数据上。"""
    calibration = _calibrate(protocol, panels, "L1_power_mde200", 0.130262)
    row = run_local_power_rep(calibration, rep=0, n=RUN_N, run_dir=tmp_path / "rep0", audit=True)
    assert row["n_total"] == RUN_N
    assert row["n_treatment"] + row["n_control"] == RUN_N
    assert 0.0 <= row["itt_p_value"] <= 1.0
    assert math.isfinite(row["itt_diff"]) and math.isfinite(row["itt_se"])
    # 审计：该 rep 的有限总体真值应明显高于"增量零"负对照，并且接近目标（抽样内）。
    assert row["realized_effect"] > calibration.curve.effect_at_zero_increment + 0.3
    assert abs(row["realized_effect"] - calibration.target_effect) < 0.5
    # 实测购买增量 ≈ 校准的平均增量（同一条放缩落到了生成人群上）。
    assert row["purchase_diff"] == pytest.approx(calibration.mean_purchase_increment, abs=0.05)
    assert row["total_cpu_s"] > 0


def test_summary_reports_rejection_rate_mcse_and_interval(protocol, panels) -> None:
    """拒绝率、MC_SE、Clopper–Pearson 区间与名义功效必须口径一致。"""
    calibration = _calibrate(protocol, panels, "L1_power_mde100", 0.130262)
    p_values = [0.001, 0.01, 0.02, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.9]
    effects = list(np.linspace(0.05, 0.5, 10))
    frame = pd.DataFrame({
        "cell_id": [calibration.cell_id] * 10,
        "rep_id": list(range(10)),
        "effect_estimate": effects,
        "reject": [value < 0.05 for value in p_values],
        "itt_p_value": p_values,
        "purchase_diff": [0.04] * 10,
        "purchase_p_value": [0.001] * 10,
        "n_total": [1000] * 10, "n_treatment": [500] * 10, "n_control": [500] * 10,
        "sd_profit_treated": [10.0] * 10, "sd_profit_control": [9.5] * 10,
        "config_hash": ["x"] * 10,
        "dgp_cpu_s": [0.1] * 10, "pipeline_cpu_s": [1.0] * 10, "itt_cpu_s": [0.01] * 10,
        "audit_cpu_s": [0.0] * 10, "total_cpu_s": [1.11] * 10, "total_wall_s": [1.2] * 10,
        "realized_effect": [np.nan] * 10,
    })
    summary = summarize_local_power(
        frame, [calibration], alpha=0.05,
        registered_n={calibration.cell_id: 200000},
        design_sigma={calibration.cell_id: (10.0, 9.5)},
    )
    row = summary.iloc[0]
    assert row["n_reps"] == 10 and row["empirical_n_reps"] == 10
    assert row["rejections"] == 3
    assert row["rejection_rate"] == pytest.approx(0.3)
    assert row["mc_se"] == pytest.approx(math.sqrt(0.3 * 0.7 / 10))
    assert 0.0 <= row["binomial_ci_low"] < row["rejection_rate"] < row["binomial_ci_high"] <= 1.0
    assert row["ci_confidence"] == pytest.approx(0.95)
    # D.1 的实测列与解析列必须分开：achieved_effect 是逐 rep 估计的均值。
    assert row["achieved_effect"] == pytest.approx(float(np.mean(effects)))
    assert row["achieved_effect_mc_se"] == pytest.approx(float(np.std(effects, ddof=1) / math.sqrt(10)))
    assert row["achieved_effect_analytic"] == pytest.approx(calibration.achieved_effect)
    expected_nominal = profit_power(calibration.target_effect, 10.0, 9.5, 500, 500, alpha=0.05)
    assert row["nominal_power"] == pytest.approx(expected_nominal, rel=1e-12)
    counts = split_counts(200000, (0.5, 0.5))
    expected_registered = profit_power(calibration.target_effect, 10.0, 9.5, counts[0], counts[1], alpha=0.05)
    assert row["nominal_power_registered_n"] == pytest.approx(expected_registered, rel=1e-12)
    assert row["measured_minus_nominal"] == pytest.approx(0.3 - expected_nominal, rel=1e-12)
    assert row["power_cell_class"] == "boundary_zero_margin"
    assert row["interpretation"] == "power_at_design_mde_boundary_zero_margin"


def test_summary_requires_two_repetitions(protocol, panels) -> None:
    """R=1 时 MC_SE 无定义：D.1 的入口会抛，本模块不得悄悄给出 0。"""
    calibration = _calibrate(protocol, panels, "L1_power_mde100", 0.130262)
    frame = pd.DataFrame({
        "cell_id": [calibration.cell_id], "rep_id": [0], "effect_estimate": [0.1], "reject": [True],
        "itt_p_value": [0.01], "purchase_diff": [0.04], "purchase_p_value": [0.01],
        "n_total": [1000], "n_treatment": [500], "n_control": [500],
        "sd_profit_treated": [10.0], "sd_profit_control": [9.5], "config_hash": ["x"],
        "dgp_cpu_s": [0.1], "pipeline_cpu_s": [1.0], "itt_cpu_s": [0.01], "audit_cpu_s": [0.0],
        "total_cpu_s": [1.11], "total_wall_s": [1.2], "realized_effect": [np.nan],
    })
    with pytest.raises(ValueError, match="MC_SE"):
        summarize_local_power(frame, [calibration], alpha=0.05)


# --------------------------------------------------------------------------- #
# 20 格：计划、可行域与可达性
# --------------------------------------------------------------------------- #
def test_power_plan_matches_the_frozen_registry(protocol) -> None:
    """20 格、5 个倍数、目标 = 倍数 × 设计 MDE，且设计 MDE 来自 D.1 的表。"""
    plans = local_power_plan(protocol)
    assert len(plans) == 20
    assert {plan.level for plan in plans} == {"L0", "L1", "L2", "L3"}
    assert sorted({plan.multiplier for plan in plans}) == [0.0, 0.5, 1.0, 1.5, 2.0]
    table = design_mde_table()
    assert len(table) == 20
    for plan in plans:
        assert plan.target_effect == pytest.approx(plan.multiplier * plan.design_mde, rel=1e-15)
        assert table[(plan.base_scenario_id, plan.multiplier)] == pytest.approx(plan.design_mde)
        cfg = protocol.scenario(plan.cell_id)
        assert configured_multiplier(cfg) == plan.multiplier
    sigmas = design_sigma_table()
    assert set(sigmas) == {plan.base_scenario_id for plan in plans}


def test_all_twenty_cells_are_reachable_and_consistent(protocol, panels) -> None:
    """20 格全部可达：achieved==target、增量在上界内、可行域诊断表齐备。"""
    plans = local_power_plan(protocol)
    calibrations = []
    for base, panel in panels.items():
        curve = profit_effect_curve(panel)
        for plan in (item for item in plans if item.base_scenario_id == base):
            calibration = calibrate_local_power_cell(
                panel, protocol.scenario(plan.cell_id), design_mde=plan.design_mde, curve=curve,
            )
            assert calibration.consistent
            assert abs(calibration.achieved_effect - plan.target_effect) <= (
                DEFAULT_RELATIVE_TOLERANCE * abs(plan.target_effect) + 1e-9
            )
            assert 0.0 < calibration.increment_scale < curve.scale_upper
            assert calibration.mean_purchase_increment > 0.0
            assert calibration.mean_purchase_probability_treated < 1.0
            calibrations.append(calibration)
    assert len(calibrations) == 20
    feasibility = feasibility_table(calibrations)
    assert len(feasibility) == 20
    assert feasibility["reachable"].all()
    assert (feasibility["scale_margin_to_upper"] > 1.0).all()
    assert (feasibility["target_effect"] >= 0.0).all()
    # 每层的可行域下界（增量零真值）都是负的，说明"零效应"只能靠正增量实现。
    assert (feasibility["effect_at_zero_increment"] < 0).all()


def test_audit_population_effect_uses_the_generated_truth(protocol, panels) -> None:
    """审计函数只读该 rep 的审计字段，并对放缩后的概率给出正效应。"""
    calibration = _calibrate(protocol, panels, "L1_power_mde150", 0.130262)
    cfg = calibration.scaled_config()
    population = generate_v3_population(cfg, rep_id=0, n=400)
    audit = audit_population_effect(population, cfg)
    assert audit["realized_effect"] > calibration.curve.effect_at_zero_increment + 0.3
    assert audit["realized_mean_purchase_treated"] == pytest.approx(
        float(population.audit_probabilities.p1_conditional.mean()),
    )
    assert 0.0 < audit["realized_mean_purchase_control"] < audit["realized_mean_purchase_treated"] < 1.0


# --------------------------------------------------------------------------- #
# 估计目标诊断：未调整 ITT 在协变量依赖随机化下不是 ATE
# --------------------------------------------------------------------------- #
def test_selection_bias_diagnostic_flags_l3_only(protocol, panels) -> None:
    """L0/L1/L2 的 50/50 随机化偏差为 0；L3 的协变量依赖随机化必须被标出。"""
    l1 = _calibrate(protocol, panels, "L1_power_mde000", 0.130262)
    cfg1 = l1.scaled_config()
    population1 = generate_v3_population(cfg1, rep_id=0, n=2000)
    audit1 = audit_population_effect(population1, cfg1)
    assert audit1["propensity_min"] == pytest.approx(0.5)
    assert audit1["propensity_max"] == pytest.approx(0.5)
    assert abs(audit1["selection_bias"]) < 1e-9

    l3 = _calibrate(protocol, panels, "L3_power_mde000", 0.130823)
    cfg3 = l3.scaled_config()
    population3 = generate_v3_population(cfg3, rep_id=0, n=2000)
    audit3 = audit_population_effect(population3, cfg3)
    assert audit3["propensity_max"] - audit3["propensity_min"] > 0.5
    # 校准到零效应的 L3 人群：真 ATE ≈ 0，但未调整均值差被选择效应推向 +1 元/人量级。
    assert abs(audit3["realized_effect"]) < 0.3
    assert audit3["selection_bias"] > 0.5
    assert audit3["selection_bias"] > 3.0 * 0.130823


def test_summary_flags_biased_estimand(protocol, panels) -> None:
    """汇总层必须把 L3 型的估计目标偏差写进 estimator_warning。"""
    calibration = _calibrate(protocol, panels, "L3_power_mde100", 0.130823)
    frame = pd.DataFrame({
        "cell_id": [calibration.cell_id] * 2, "rep_id": [0, 1],
        "effect_estimate": [1.3, 1.5], "reject": [True, True],
        "itt_p_value": [1e-4, 2e-5], "purchase_diff": [0.06, 0.07], "purchase_p_value": [1e-3, 1e-3],
        "n_total": [3000, 3000], "n_treatment": [1500, 1500], "n_control": [1500, 1500],
        "sd_profit_treated": [10.0, 10.0], "sd_profit_control": [9.5, 9.5], "config_hash": ["x", "x"],
        "dgp_cpu_s": [0.3, 0.3], "pipeline_cpu_s": [3.0, 3.0], "itt_cpu_s": [0.01, 0.01],
        "audit_cpu_s": [0.5, 0.0], "total_cpu_s": [3.81, 3.31], "total_wall_s": [4.0, 3.5],
        "realized_effect": [0.13, np.nan], "selection_bias": [1.35, np.nan],
        "propensity_min": [0.16, np.nan], "propensity_max": [0.96, np.nan],
    })
    summary = summarize_local_power(frame, [calibration], alpha=0.05)
    row = summary.iloc[0]
    assert row["selection_bias"] == pytest.approx(1.35)
    assert row["selection_bias_ratio_to_mde"] > 5.0
    assert row["propensity_min"] == pytest.approx(0.16)
    assert "propensity_weighted_contrast" in row["estimator_warning"]
    assert row["rejection_rate"] == pytest.approx(1.0)

    frame["selection_bias"] = [0.0, np.nan]
    clean = summarize_local_power(frame, [calibration], alpha=0.05)
    assert clean.iloc[0]["estimator_warning"] == ""


# --------------------------------------------------------------------------- #
# 环境故障：只重试源码绑定门禁与 Windows 落盘占用
# --------------------------------------------------------------------------- #
class _FakeLock(OSError):
    """带 ``winerror`` 的 OSError，模拟 Windows 落盘短暂占用（跨平台可构造）。"""

    winerror = 32


def test_environment_fault_classification() -> None:
    """只有两类环境故障可重试，其余真 bug 必须冒出。"""
    assert environment_fault(RuntimeError(f"{SOURCE_CHANGED_MARKER}; retain this attempt as failed")) \
        == "source_changed"
    assert environment_fault(_FakeLock("busy")) == "windows_file_lock"
    assert environment_fault(ValueError("a real bug")) is None
    try:
        try:
            raise _FakeLock("busy")
        except OSError as exc:
            raise ValueError("run is already terminal") from exc
    except ValueError as wrapped:
        assert environment_fault(wrapped) == "windows_file_lock"


def test_cell_retries_environment_faults_only(monkeypatch, protocol, panels, tmp_path: Path) -> None:
    """源码被并发改写时用新目录重试；真异常不重试也不吞。"""
    calibration = _calibrate(protocol, panels, "L1_power_mde050", 0.130262)
    real = local_power_pipeline.run_local_power_rep
    calls = {"count": 0}

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError(f"{SOURCE_CHANGED_MARKER}; retain this attempt as failed")
        return real(*args, **kwargs)

    monkeypatch.setattr(local_power_pipeline, "run_local_power_rep", flaky)
    frame = local_power_pipeline.run_local_power_cell(
        calibration, reps=1, n=120, run_root=tmp_path / "retry", max_environment_retries=2,
    )
    assert calls["count"] == 2
    assert int(frame.iloc[0]["environment_retries"]) == 1
    assert frame.iloc[0]["n_total"] == 120

    calls["count"] = 0

    def broken(*args, **kwargs):
        calls["count"] += 1
        raise ValueError("a real bug")

    monkeypatch.setattr(local_power_pipeline, "run_local_power_rep", broken)
    with pytest.raises(ValueError, match="real bug"):
        local_power_pipeline.run_local_power_cell(
            calibration, reps=1, n=120, run_root=tmp_path / "broken", max_environment_retries=3,
        )
    assert calls["count"] == 1
