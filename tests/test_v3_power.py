"""v3 Phase D.1 的 MDE / 护栏非劣效 / 功效格校准口径测试。

覆盖七类断言：
1. **公式正确性**：闭式利润 MDE、两比例数值反解、护栏非劣效 MDE，含蒙特卡洛功效复现；
2. **口径红线**：n 的符号不混用、方差/峰度/退款率只取 train split、失败要响（不返回 nan）；
3. **零硬编码**：α/功效/分流/族大小/队列人数/护栏界值改注册表后结果跟着变；
4. **不读真值**：模块导入期不加载 DGP，隔离列出现即抛错；
5. **C4**：σ 的抽样相对 SE 按实测峰度 `sqrt((κ−1)/(4n))`，不是正态公式；mde100 压力功效约 0.79；
6. **C5**：mde100 边界格编码进表（boundary_flag / margin_ratio / power_cell_class），单侧 α 缺口可查；
7. **C2/C3**：护栏非劣效 MDE 的四层数字；`summarize_power_cells` 只汇总真实逐 rep 结果，CSV 实测列 pending。

合成数据 / 已知 DGP。全部为设计期断言，不构成任何正式重复（R = 0）。
"""

from __future__ import annotations

import ast
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from causal_growth.config import Config
from causal_growth.design import v3_power as vp
from causal_growth.design.power import sample_size_mean, sample_size_proportion
from causal_growth.rng import child_rng
from causal_growth.v3_config import V3Protocol, load_v3_protocol

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(vp.__file__)
#: 冻结的七份配置合并规范化 SHA-256（A 阶段评审凭据，改一个字符即失效）。
FROZEN_CONFIG_HASH = "30511a32bcee9db55e8f5ec1bbc2b9d63eb63dc2a13aa5c720f948c781eccdbe"
BASE_SCENARIOS = ("L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000")


@pytest.fixture(scope="module")
def protocol() -> V3Protocol:
    return load_v3_protocol()


def _profile(
    scenario_id: str = "L1_main",
    *,
    sd_treatment: float = 55.0,
    sd_control: float = 52.0,
    purchase_treatment: float = 0.13,
    purchase_control: float = 0.12,
    rep_id: int = 1000,
    n_treatment: int = 50000,
    n_control: int = 50000,
    kurtosis_treatment: float = 22.0,
    kurtosis_control: float = 21.0,
    refund_treatment: float = 0.0077,
    refund_control: float = 0.0075,
) -> vp.DesignSampleProfile:
    """构造一个只含观测汇总的设计样本画像（单测里替代完整五表 + SQL）。"""
    return vp.DesignSampleProfile(
        scenario_id=scenario_id,
        split="train",
        n_total=n_treatment + n_control,
        n_treatment=n_treatment,
        n_control=n_control,
        profit_mean_treatment=1.5,
        profit_mean_control=1.4,
        profit_sd_treatment=sd_treatment,
        profit_sd_control=sd_control,
        purchase_rate_treatment=purchase_treatment,
        purchase_rate_control=purchase_control,
        rep_id=rep_id,
        observed_dataset_hash="sha256:fixture",
        source_path="fixture://design_sample",
        config_hash="0" * 64,
        profit_kurtosis_treatment=kurtosis_treatment,
        profit_kurtosis_control=kurtosis_control,
        refund_rate_treatment=refund_treatment,
        refund_rate_control=refund_control,
        notes="unit-test fixture",
    )


def _profiles(protocol: V3Protocol) -> dict[str, vp.DesignSampleProfile]:
    """四个基础机制各一份画像（各层 σ 与峰度故意不同，用来验证按层取值）。"""
    return {
        "L0_P_main": _profile("L0_P_main", sd_treatment=60.0, sd_control=52.0, purchase_control=0.115,
                              kurtosis_treatment=20.0, kurtosis_control=19.0,
                              refund_control=0.0072),
        "L1_main": _profile("L1_main", sd_treatment=55.0, sd_control=52.0, purchase_control=0.120,
                            kurtosis_treatment=22.0, kurtosis_control=21.0,
                            refund_control=0.0075),
        "L2_n200000_p050": _profile("L2_n200000_p050", sd_treatment=58.0, sd_control=52.0,
                                    purchase_control=0.118,
                                    kurtosis_treatment=24.0, kurtosis_control=23.0,
                                    refund_control=0.0074),
        "L3_fixed_lt000": _profile("L3_fixed_lt000", sd_treatment=56.0, sd_control=53.0,
                                   purchase_control=0.121,
                                   kurtosis_treatment=40.0, kurtosis_control=35.0,
                                   refund_control=0.0068),
    }


@pytest.fixture(scope="module")
def profiles(protocol) -> dict[str, vp.DesignSampleProfile]:
    """模块级共享画像：同一批对象，才能断言"方差确实来自该层画像"。"""
    return _profiles(protocol)


def _frame(n: int = 400, *, treatment_share: float = 0.5, seed: int = 7) -> pd.DataFrame:
    """观测列小表：只含本模块允许读取的五列（含 C2 护栏列）。"""
    rng = child_rng(master_seed=20240101, stream="test.v3_power.frame", index=seed)
    treatment = np.zeros(n, dtype=int)
    treatment[: int(round(n * treatment_share))] = 1
    purchase = (rng.random(n) < np.where(treatment == 1, 0.13, 0.12)).astype(float)
    profit = np.where(purchase > 0, rng.gamma(2.0, 30.0, n) - 10.0, 0.0)
    refund = (purchase > 0) & (rng.random(n) < 0.075)
    return pd.DataFrame({
        "treatment": treatment,
        "net_profit": profit,
        "paid_purchase_7d": purchase,
        "any_refund_30d": refund.astype(float),
        "split": "train",
    })


# --------------------------------------------------------------------------- #
# 1. 冻结配置与零硬编码
# --------------------------------------------------------------------------- #
def test_config_canonical_hash_is_still_frozen(protocol):
    assert protocol.config_hash == FROZEN_CONFIG_HASH


def test_design_parameters_come_from_the_register(protocol):
    assert vp.alpha_from_config(protocol) == pytest.approx(0.05)
    assert vp.power_targets_from_config(protocol) == (pytest.approx(0.80), pytest.approx(0.90))
    assert vp.allocation_shares_from_config(protocol) == (
        pytest.approx(0.50), pytest.approx(0.30), pytest.approx(0.10))
    assert vp.design_scenario_id(protocol) == protocol.config.require(
        "matrix_contract.reference_scenarios.L1")


def test_allocation_grid_follows_the_register_instead_of_hardcoding(protocol):
    data = protocol.config.to_dict()
    for cell in data["scenarios"]:
        if cell["id"].startswith("L2_n"):
            cell["treatment_probability"] = 0.4 if cell["treatment_probability"] == 0.5 else 0.6
    patched = V3Protocol(Config(data, name="patched"), protocol.source_hashes, protocol.config_hash)
    assert vp.allocation_shares_from_config(patched) == (pytest.approx(0.6), pytest.approx(0.4))


def test_power_targets_change_with_the_register(protocol):
    data = protocol.config.to_dict()
    data["design"]["power_targets"] = [0.75, 0.85]
    patched = V3Protocol(Config(data, name="patched"), protocol.source_hashes, protocol.config_hash)
    assert vp.power_targets_from_config(patched) == (pytest.approx(0.75), pytest.approx(0.85))


def test_unknown_design_scenario_is_refused(protocol):
    data = protocol.config.to_dict()
    data["matrix_contract"]["reference_scenarios"]["L1"] = "not_a_registered_scenario"
    patched = V3Protocol(Config(data, name="patched"), protocol.source_hashes, protocol.config_hash)
    with pytest.raises(Exception):
        vp.design_scenario_id(patched)


# --------------------------------------------------------------------------- #
# 2. z 值与多重校正
# --------------------------------------------------------------------------- #
def test_z_alpha_two_sided_matches_normal_quantile():
    assert vp.z_alpha(0.05, vp.TWO_SIDED) == pytest.approx(1.959963984540054)


def test_z_alpha_one_sided_is_smaller_than_two_sided():
    assert vp.z_alpha(0.05, vp.ONE_SIDED) == pytest.approx(1.6448536269514722)
    assert vp.z_alpha(0.05, vp.ONE_SIDED) < vp.z_alpha(0.05, vp.TWO_SIDED)


def test_z_power_matches_normal_quantile():
    assert vp.z_power(0.80) == pytest.approx(0.8416212335729143)
    assert vp.z_power(0.90) == pytest.approx(1.2815515655446004)


@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1, 1.5, float("nan")])
def test_invalid_alpha_is_refused(alpha):
    with pytest.raises((ValueError, TypeError)):
        vp.z_alpha(alpha, vp.TWO_SIDED)


@pytest.mark.parametrize("power", [0.0, 1.0, -0.5])
def test_invalid_power_is_refused(power):
    with pytest.raises(ValueError):
        vp.z_power(power)


def test_unknown_sides_is_refused():
    with pytest.raises(ValueError):
        vp.z_alpha(0.05, "both")
    with pytest.raises(ValueError):
        vp.profit_mde(1.0, 1.0, 10, 10, alpha=0.05, power=0.8, sides="upper")


def test_holm_per_test_alpha_is_alpha_over_family_size():
    assert vp.holm_per_test_alpha(0.05, 1) == pytest.approx(0.05)
    assert vp.holm_per_test_alpha(0.05, 2) == pytest.approx(0.025)
    assert vp.holm_per_test_alpha(0.05, 3) < vp.holm_per_test_alpha(0.05, 2)


@pytest.mark.parametrize("family_size", [0, -1])
def test_holm_rejects_non_positive_family(family_size):
    with pytest.raises(ValueError):
        vp.holm_per_test_alpha(0.05, family_size)


def test_holm_adjusted_mde_is_larger_than_single_test_mde():
    single = vp.purchase_mde(0.12, 50000, 50000, alpha=0.05, power=0.8)
    joint = vp.purchase_mde(0.12, 50000, 50000, alpha=vp.holm_per_test_alpha(0.05, 2), power=0.8)
    assert joint > single


# --------------------------------------------------------------------------- #
# 3. 分流：n_total 与各臂人数不混用
# --------------------------------------------------------------------------- #
def test_split_counts_equal_allocation_is_exact():
    assert vp.split_counts(200000, (0.5, 0.5)) == (100000, 100000)


@pytest.mark.parametrize("share,expected", [(0.5, (100000, 100000)),
                                            (0.3, (60000, 140000)),
                                            (0.1, (20000, 180000))])
def test_split_counts_matches_registered_resource_shares(share, expected):
    assert vp.split_counts(200000, (share, 1.0 - share)) == expected


def test_split_counts_three_arms_sum_to_total():
    counts = vp.split_counts(200000, (1 / 3, 1 / 3, 1 / 3))
    assert sum(counts) == 200000
    assert max(counts) - min(counts) <= 1


@pytest.mark.parametrize("probabilities", [(0.5, 0.4), (0.5,), (0.5, -0.5), (1.0, 0.0)])
def test_split_counts_rejects_illegal_probabilities(probabilities):
    with pytest.raises(ValueError):
        vp.split_counts(1000, probabilities)


@pytest.mark.parametrize("n_total", [0, -1])
def test_split_counts_rejects_non_positive_total(n_total):
    with pytest.raises(ValueError):
        vp.split_counts(n_total, (0.5, 0.5))


def test_split_counts_rejects_fractional_total():
    with pytest.raises(TypeError):
        vp.split_counts(1000.5, (0.5, 0.5))


def test_split_counts_is_deterministic_and_breaks_ties_by_index():
    first = vp.split_counts(101, (0.5, 0.5))
    second = vp.split_counts(101, (0.5, 0.5))
    assert first == second == (51, 50)


# --------------------------------------------------------------------------- #
# 4. 利润 MDE
# --------------------------------------------------------------------------- #
def test_profit_mde_matches_closed_form():
    sigma, n = 55.0, 100000
    expected = (norm.ppf(0.975) + norm.ppf(0.80)) * math.sqrt(sigma**2 / n + sigma**2 / n)
    assert vp.profit_mde(sigma, sigma, n, n, alpha=0.05, power=0.80) == pytest.approx(expected)


def test_profit_mde_equal_arms_reduces_to_two_sigma_over_sqrt_n():
    sigma, n = 52.0, 100000
    expected = (vp.z_alpha(0.05) + vp.z_power(0.80)) * math.sqrt(2.0) * sigma / math.sqrt(n)
    assert vp.profit_mde(sigma, sigma, n, n, alpha=0.05, power=0.80) == pytest.approx(expected)


def test_profit_mde_rises_with_power_target():
    low = vp.profit_mde(55.0, 52.0, 100000, 100000, alpha=0.05, power=0.80)
    high = vp.profit_mde(55.0, 52.0, 100000, 100000, alpha=0.05, power=0.90)
    assert high > low


def test_profit_mde_one_sided_is_smaller():
    two = vp.profit_mde(55.0, 52.0, 100000, 100000, alpha=0.05, power=0.80, sides=vp.TWO_SIDED)
    one = vp.profit_mde(55.0, 52.0, 100000, 100000, alpha=0.05, power=0.80, sides=vp.ONE_SIDED)
    assert one < two


def test_profit_mde_unequal_allocation_is_harder_than_equal():
    equal = vp.profit_mde(55.0, 55.0, 100000, 100000, alpha=0.05, power=0.80)
    unequal = vp.profit_mde(55.0, 55.0, 20000, 180000, alpha=0.05, power=0.80)
    assert unequal > equal


@pytest.mark.parametrize("sigma_treatment,sigma_control", [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
def test_profit_mde_rejects_non_positive_sigma(sigma_treatment, sigma_control):
    with pytest.raises(ValueError):
        vp.profit_mde(sigma_treatment, sigma_control, 100, 100, alpha=0.05, power=0.8)


@pytest.mark.parametrize("n_treatment,n_control", [(0, 100), (100, 0), (-5, 100)])
def test_profit_mde_rejects_non_positive_sample(n_treatment, n_control):
    with pytest.raises(ValueError):
        vp.profit_mde(1.0, 1.0, n_treatment, n_control, alpha=0.05, power=0.8)


def test_profit_mde_rejects_fractional_sample():
    with pytest.raises(TypeError):
        vp.profit_mde(1.0, 1.0, 100.0, 100, alpha=0.05, power=0.8)


@pytest.mark.parametrize("alpha,power", [(0.0, 0.8), (0.05, 0.0), (0.05, 1.0), (1.0, 0.8)])
def test_profit_mde_rejects_illegal_alpha_power(alpha, power):
    with pytest.raises(ValueError):
        vp.profit_mde(1.0, 1.0, 100, 100, alpha=alpha, power=power)


def test_profit_mde_agrees_with_existing_sample_size_inversion():
    sigma, target = 52.0, 1.0
    n_per_group = sample_size_mean(sigma, target, alpha=0.05, power=0.80)
    assert vp.profit_mde(sigma, sigma, n_per_group, n_per_group, alpha=0.05, power=0.80) <= target


# --------------------------------------------------------------------------- #
# 5. 利润功效
# --------------------------------------------------------------------------- #
def test_profit_power_at_zero_equals_half_alpha_two_sided():
    assert vp.profit_power(0.0, 55.0, 52.0, 100000, 100000, alpha=0.05) == pytest.approx(0.025)


def test_profit_power_at_zero_equals_alpha_one_sided():
    assert vp.profit_power(0.0, 55.0, 52.0, 100000, 100000, alpha=0.05,
                           sides=vp.ONE_SIDED) == pytest.approx(0.05)


def test_profit_power_round_trips_through_mde():
    for power in (0.80, 0.90):
        mde = vp.profit_mde(55.0, 52.0, 100000, 100000, alpha=0.05, power=power)
        assert vp.profit_power(mde, 55.0, 52.0, 100000, 100000, alpha=0.05) == pytest.approx(power)


def test_profit_power_is_monotone_in_effect():
    powers = [vp.profit_power(e, 55.0, 52.0, 100000, 100000, alpha=0.05)
              for e in (0.0, 0.2, 0.5, 0.8, 1.2)]
    assert powers == sorted(powers)
    assert len(set(powers)) == len(powers)


def test_profit_power_rejects_negative_effect():
    with pytest.raises(ValueError):
        vp.profit_power(-0.1, 55.0, 52.0, 100000, 100000, alpha=0.05)


def test_profit_mde_matches_monte_carlo_rejection_rate():
    """解析 MDE 对应的真实拒绝率必须接近名义功效（蒙特卡洛，不是闭式复算）。"""
    sigma, n, reps, nominal = 20.0, 300, 800, 0.80
    mde = vp.profit_mde(sigma, sigma, n, n, alpha=0.05, power=nominal)
    rng = child_rng(master_seed=20240101, stream="test.v3_power.mc_profit", index=0)
    treated = rng.normal(mde, sigma, size=(reps, n))
    control = rng.normal(0.0, sigma, size=(reps, n))
    se = np.sqrt(treated.var(axis=1, ddof=1) / n + control.var(axis=1, ddof=1) / n)
    z = (treated.mean(axis=1) - control.mean(axis=1)) / se
    rejection = float(np.mean(np.abs(z) > norm.ppf(0.975)))
    assert abs(rejection - nominal) < 0.05


# --------------------------------------------------------------------------- #
# 6. σ 的抽样不确定性：峰度修正（C4）
# --------------------------------------------------------------------------- #
def test_sample_kurtosis_matches_bernoulli_closed_form():
    """伯努利(p) 的 κ = [(1−p)^3 + p^3] / [p(1−p)]，用来钉住"非超额峰度"的定义。"""
    p = 0.1
    values = np.concatenate([np.ones(1000), np.zeros(9000)])
    expected = ((1.0 - p) ** 3 + p**3) / (p * (1.0 - p))
    assert vp.sample_kurtosis(values) == pytest.approx(expected, rel=1e-9)


def test_sample_kurtosis_rejects_degenerate_samples():
    with pytest.raises(ValueError):
        vp.sample_kurtosis([1.0, 1.0, 1.0, 1.0])
    with pytest.raises(ValueError):
        vp.sample_kurtosis([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        vp.sample_kurtosis([1.0, 2.0, float("nan"), 4.0])


def test_sigma_relative_se_follows_the_kurtosis_formula_not_the_normal_one():
    kappa, n_arm = 22.0, 50000
    expected = math.sqrt((kappa - 1.0) / (4.0 * n_arm))
    assert vp.sigma_relative_se(kappa, n_arm) == pytest.approx(expected)
    # 正态公式 1/sqrt(2n) 会把误差低估 sqrt((κ−1)/2) 倍；L1 的 κ≈22 时约 3.2 倍。
    ratio = expected / (1.0 / math.sqrt(2.0 * n_arm))
    assert ratio == pytest.approx(math.sqrt((kappa - 1.0) / 2.0))
    assert 3.0 < ratio < 5.0


@pytest.mark.parametrize("kurtosis,n_arm", [(0.5, 1000), (22.0, 1), (22.0, 0)])
def test_sigma_relative_se_rejects_illegal_inputs(kurtosis, n_arm):
    with pytest.raises(ValueError):
        vp.sigma_relative_se(kurtosis, n_arm)


def test_sigma_relative_se_reproduces_the_sampling_error_by_simulation():
    """用零膨胀重尾分布做一次轻量 MC：实测 sd(σ̂)/σ 必须贴近峰度公式。"""
    rng = child_rng(master_seed=20240101, stream="test.v3_power.kurtosis_mc", index=0)
    n_arm, reps = 5000, 400
    pays = rng.random((reps, n_arm)) < 0.10
    amounts = rng.gamma(2.0, 30.0, size=(reps, n_arm))
    sample = np.where(pays, amounts, 0.0)
    sd = sample.std(axis=1, ddof=1)
    kurtosis = vp.sample_kurtosis(sample.ravel())
    predicted = vp.sigma_relative_se(kurtosis, n_arm)
    measured = float(sd.std(ddof=1) / sd.mean())
    assert measured == pytest.approx(predicted, rel=0.10)


def test_mde_relative_se_is_the_weighted_combination_of_arm_errors(protocol):
    profile = _profile("L1_main", sd_treatment=55.0, sd_control=55.0,
                       kurtosis_treatment=22.0, kurtosis_control=22.0)
    r = vp.sigma_relative_se(22.0, 50000)
    expected = math.sqrt(0.25 * r * r + 0.25 * r * r)
    assert vp.mde_relative_se(profile, 100000, 100000) == pytest.approx(expected)
    assert expected < r


def test_mde_relative_se_refuses_a_profile_without_kurtosis():
    profile = _profile("L1_main", kurtosis_treatment=None)
    with pytest.raises(ValueError, match="峰度"):
        vp.mde_relative_se(profile, 100000, 100000)
    with pytest.raises(ValueError, match="峰度"):
        vp.sigma_stress_relative_se(profile)


def test_sigma_stress_power_matches_the_closed_form():
    sigma, n, target = 20.0, 100000, 0.05
    mde = vp.profit_mde(sigma, sigma, n, n, alpha=target, power=0.80)
    stress = 0.012
    expected = float(norm.cdf((vp.z_alpha(target) + vp.z_power(0.80)) / (1.0 + stress)
                              - vp.z_alpha(target)))
    assert vp.profit_power_sigma_stress(mde, sigma, sigma, n, n, alpha=target,
                                        relative_inflation=stress) == pytest.approx(expected)


def test_unit_multiplier_true_power_under_sigma_stress_is_about_079(calibrations):
    """C4：mde100 的"解析 0.8000"在 σ 上行 1 个抽样 SE 后只有约 0.79。"""
    for cell in calibrations:
        if cell.configured_multiplier != pytest.approx(1.0):
            continue
        assert cell.power_at_sigma_plus_1se < cell.analytic_power
        assert 0.780 < cell.power_at_sigma_plus_1se < 0.800
        assert 0.005 < cell.sigma_stress_relative_se < 0.02
        assert 0.005 < cell.mde_relative_se < cell.sigma_stress_relative_se


# --------------------------------------------------------------------------- #
# 7. 购买率：两比例数值反解
# --------------------------------------------------------------------------- #
def test_purchase_power_at_zero_delta_equals_half_alpha():
    assert vp.purchase_power(0.12, 0.0, 100000, 100000, alpha=0.05) == pytest.approx(0.025)


def test_purchase_power_is_monotone_in_delta():
    values = [vp.purchase_power(0.12, d, 20000, 20000, alpha=0.05)
              for d in (0.0, 0.005, 0.01, 0.02, 0.05)]
    assert values == sorted(values)


@pytest.mark.parametrize("power", [0.80, 0.90])
@pytest.mark.parametrize("sides", [vp.TWO_SIDED, vp.ONE_SIDED])
def test_purchase_mde_round_trips_to_target_power(power, sides):
    mde = vp.purchase_mde(0.12, 100000, 100000, alpha=0.05, power=power, sides=sides)
    assert vp.purchase_power(0.12, mde, 100000, 100000, alpha=0.05,
                             sides=sides) == pytest.approx(power, abs=1e-7)


def test_purchase_mde_one_sided_is_smaller():
    two = vp.purchase_mde(0.12, 100000, 100000, alpha=0.05, power=0.80)
    one = vp.purchase_mde(0.12, 100000, 100000, alpha=0.05, power=0.80, sides=vp.ONE_SIDED)
    assert one < two


def test_purchase_mde_shrinks_with_more_users():
    small = vp.purchase_mde(0.12, 10000, 10000, alpha=0.05, power=0.80)
    large = vp.purchase_mde(0.12, 100000, 100000, alpha=0.05, power=0.80)
    assert large < small
    # 样本量 ×10 时 MDE 应约为 1/sqrt(10)；用宽松区间验证量级而不是硬编码数值。
    assert small / large == pytest.approx(math.sqrt(10.0), rel=0.05)


def test_purchase_mde_agrees_with_existing_proportion_inversion():
    p0, target = 0.12, 0.004
    n_per_group = sample_size_proportion(p0, target, alpha=0.05, power=0.80)
    solved = vp.purchase_mde(p0, n_per_group, n_per_group, alpha=0.05, power=0.80)
    assert solved == pytest.approx(target, rel=0.10)


@pytest.mark.parametrize("p0", [0.0, 1.0, -0.2, 1.2])
def test_purchase_rate_rejects_illegal_baseline(p0):
    with pytest.raises(ValueError):
        vp.purchase_mde(p0, 1000, 1000, alpha=0.05, power=0.8)


@pytest.mark.parametrize("n", [0, -3])
def test_purchase_mde_rejects_non_positive_sample(n):
    with pytest.raises(ValueError):
        vp.purchase_mde(0.12, n, 1000, alpha=0.05, power=0.8)


@pytest.mark.parametrize("power", [0.02, 0.025])
def test_purchase_mde_refuses_power_not_above_null_rejection(power):
    with pytest.raises(ValueError):
        vp.purchase_mde(0.12, 1000, 1000, alpha=0.05, power=power)


def test_purchase_mde_refuses_unreachable_power():
    with pytest.raises(ValueError):
        vp.purchase_mde(0.12, 2, 2, alpha=0.05, power=0.999999)


@pytest.mark.parametrize("n", [5000, 10000])
def test_profit_mde_normal_approximation_survives_zero_inflated_profit(n):
    """利润是"九成零 + 少数大额"的零膨胀变量（偏度≈5.7、超额峰度≈45），
    MDE 却用正态近似：在真实形状下，MDE 处的实际拒绝率应随 n 增大逼近名义功效。"""
    p_pay, payer_mean, payer_sd = 0.10, 26.0, 22.2
    shape = (payer_mean / payer_sd) ** 2
    scale = payer_sd**2 / payer_mean
    sigma = math.sqrt(p_pay * payer_sd**2 + p_pay * (1 - p_pay) * payer_mean**2)
    mde = vp.profit_mde(sigma, sigma, n, n, alpha=0.05, power=0.80)
    rng = child_rng(master_seed=20240101, stream="test.v3_power.mc_zero_inflated", index=0)
    reps = 600

    def draw(uplift_per_assigned_user: float) -> np.ndarray:
        """MDE 是"每个合格用户"的利润增量；购买者只占 p_pay，故购买者需抬高 mde/p_pay。"""
        pays = rng.random((reps, n)) < p_pay
        amounts = rng.gamma(shape, scale, size=(reps, n)) + uplift_per_assigned_user / p_pay
        return np.where(pays, amounts, 0.0)

    treated, control = draw(mde), draw(0.0)
    se = np.sqrt(treated.var(axis=1, ddof=1) / n + control.var(axis=1, ddof=1) / n)
    z = (treated.mean(axis=1) - control.mean(axis=1)) / se
    rejection = float(np.mean(np.abs(z) > norm.ppf(0.975)))
    # 实测：n=5000 → 0.747，n=10000 → 0.780（正态近似在强偏态下偏乐观）。
    # 断言留 0.08 的余量：只要不是"完全没功效"或"离谱地高"就算通过。
    assert abs(rejection - 0.80) < 0.08
    assert rejection > 0.05


def test_purchase_power_rejects_probability_overflow():
    with pytest.raises(ValueError):
        vp.purchase_power(0.9, 0.2, 100, 100, alpha=0.05)


def test_purchase_mde_matches_monte_carlo_rejection_rate():
    """两比例 MDE 对应的真实拒绝率必须接近名义功效（蒙特卡洛二项抽样）。"""
    p0, n, reps, nominal = 0.12, 2000, 600, 0.80
    mde = vp.purchase_mde(p0, n, n, alpha=0.05, power=nominal)
    rng = child_rng(master_seed=20240101, stream="test.v3_power.mc_purchase", index=0)
    treated = (rng.random((reps, n)) < (p0 + mde)).astype(float)
    control = (rng.random((reps, n)) < p0).astype(float)
    pooled = (treated.sum(axis=1) + control.sum(axis=1)) / (2 * n)
    se_null = np.sqrt(pooled * (1 - pooled) * (2.0 / n))
    z = (treated.mean(axis=1) - control.mean(axis=1)) / se_null
    rejection = float(np.mean(np.abs(z) > norm.ppf(0.975)))
    assert abs(rejection - nominal) < 0.05


# --------------------------------------------------------------------------- #
# 8. 护栏非劣效 MDE（C2）
# --------------------------------------------------------------------------- #
def test_guardrail_config_comes_from_the_register(protocol):
    config = vp.guardrail_config(protocol)
    assert config["metric"] == "any_refund_30d_per_assigned_user"
    assert config["margin"] == pytest.approx(0.005)
    assert config["alpha_one_sided"] == pytest.approx(0.05)
    assert config["power_targets"] == (pytest.approx(0.80), pytest.approx(0.90))


def test_noninferiority_power_at_the_margin_equals_alpha():
    # H1 与 H0 的二项方差在同一点略有差异（p1=0.0125 vs 合并 0.01），故留有 1e-4 级偏差。
    assert vp.noninferiority_power(0.0075, 0.005, 100000, 100000,
                                   margin=0.005, alpha=0.05) == pytest.approx(0.05, abs=5e-4)


def test_noninferiority_power_is_one_when_there_is_no_worsening():
    power = vp.noninferiority_power(0.0075, 0.0, 100000, 100000,
                                    margin=0.005, alpha=0.05)
    assert power > 0.9999


def test_noninferiority_mde_round_trips_to_the_target_power():
    p0, margin = 0.0075, 0.005
    for power in (0.80, 0.90):
        effect = vp.noninferiority_mde(p0, 100000, 100000, margin=margin,
                                       alpha=0.05, power=power)
        assert vp.noninferiority_power(p0, margin - effect, 100000, 100000,
                                       margin=margin, alpha=0.05) == pytest.approx(power, abs=1e-7)


def test_noninferiority_mde_shrinks_with_more_users():
    small = vp.noninferiority_mde(0.0075, 10000, 10000, margin=0.005, alpha=0.05, power=0.80)
    large = vp.noninferiority_mde(0.0075, 100000, 100000, margin=0.005, alpha=0.05, power=0.80)
    assert large < small
    assert small / large == pytest.approx(math.sqrt(10.0), rel=0.05)


@pytest.mark.parametrize("p0,margin", [(0.0, 0.005), (1.0, 0.005), (0.997, 0.005),
                                       (0.0075, 0.0), (0.0075, -0.5)])
def test_noninferiority_mde_rejects_illegal_inputs(p0, margin):
    with pytest.raises(ValueError):
        vp.noninferiority_mde(p0, 1000, 1000, margin=margin, alpha=0.05, power=0.8)


def test_guardrail_mde_follows_the_register(protocol, mde_rows):
    """把界值改大必须让 MDE（到界值的距离）变大：零硬编码。"""
    data = protocol.config.to_dict()
    data["design"]["guardrail"]["noninferiority_margin_probability_points"] = 0.01
    patched = V3Protocol(Config(data, name="patched"), protocol.source_hashes, protocol.config_hash)
    patched_rows = vp.build_mde_rows(patched, _profiles(protocol))
    base = [row for row in mde_rows
            if row["record_type"] == "guardrail_mde" and row["scenario_id"] == "L1_main"
            and row["power_target"] == pytest.approx(0.80)][0]
    wider = [row for row in patched_rows
             if row["record_type"] == "guardrail_mde" and row["scenario_id"] == "L1_main"
             and row["power_target"] == pytest.approx(0.80)][0]
    assert vp.guardrail_config(patched)["margin"] == pytest.approx(0.01)
    assert wider["noninferiority_margin"] == pytest.approx(0.01)
    assert wider["mde"] > base["mde"]


def test_guardrail_rows_cover_four_layers_and_two_powers(mde_rows, protocol):
    guardrail = [row for row in mde_rows if row["record_type"] == "guardrail_mde"]
    assert len(guardrail) == 8
    assert {row["level"] for row in guardrail} == {"L0", "L1", "L2", "L3"}
    assert sorted(row["power_target"] for row in guardrail) == pytest.approx(
        [0.80, 0.80, 0.80, 0.80, 0.90, 0.90, 0.90, 0.90])
    metric = protocol.config.require("design.guardrail.primary_metric")
    for row in guardrail:
        assert row["metric"] == metric
        assert row["sides"] == vp.ONE_SIDED
        assert row["alpha_per_test"] == pytest.approx(0.05)
        assert row["alpha_one_sided"] == pytest.approx(0.05)
        assert row["noninferiority_margin"] == pytest.approx(0.005)
        assert row["n_total"] == 200000
        assert row["n_treatment"] == row["n_control"] == 100000
        assert row["p0_baseline"] == pytest.approx(row["control_mean"])
        assert row["p1_at_mde"] == pytest.approx(
            row["p0_baseline"] + row["noninferiority_margin"] - row["mde"])
        assert row["treatment_control_delta_at_mde"] == pytest.approx(
            row["noninferiority_margin"] - row["mde"])
        assert row["p1_at_mde"] == pytest.approx(
            row["p0_baseline"] + row["treatment_control_delta_at_mde"])
        assert row["mde_pp"] == pytest.approx(row["mde"] * 100.0)
        assert row["mde_relative_to_margin_pct"] == pytest.approx(row["mde"] / 0.005 * 100.0)
        assert row["power_at_zero_effect"] > 0.9999
        assert row["analytic_power"] == pytest.approx(row["power_target"])


def test_guardrail_mde_is_a_small_fraction_of_the_margin(mde_rows):
    """20 万/50-50 下护栏很灵敏：到界值的可检测距离约 0.1pp，是 0.5pp 界值的 1/5。"""
    guardrail = [row for row in mde_rows if row["record_type"] == "guardrail_mde"]
    for row in guardrail:
        assert 0.08 < row["mde_pp"] < 0.15
        assert 0.15 < row["mde"] / 0.005 < 0.30


def test_guardrail_rows_leave_empirics_pending(mde_rows):
    guardrail = [row for row in mde_rows if row["record_type"] == "guardrail_mde"]
    for row in guardrail:
        assert row["achieved_effect"] is None
        assert row["rejection_rate"] is None
        assert row["mc_se"] is None
        assert vp.PENDING_LOCAL_POWER in row["notes"]


# --------------------------------------------------------------------------- #
# 9. 倍数校准
# --------------------------------------------------------------------------- #
def test_multiplier_round_trips_with_target_effect():
    mde = 0.72
    for multiplier in (0.0, 0.5, 1.0, 1.5, 2.0):
        target = vp.target_effect_for_multiplier(multiplier, mde)
        assert vp.multiplier_for_target_effect(target, mde) == pytest.approx(multiplier)


def test_zero_target_effect_gives_zero_multiplier():
    assert vp.multiplier_for_target_effect(0.0, 0.72) == 0.0


@pytest.mark.parametrize("target,mde", [(-0.1, 0.72), (0.5, 0.0), (0.5, -1.0)])
def test_multiplier_rejects_illegal_inputs(target, mde):
    with pytest.raises(ValueError):
        vp.multiplier_for_target_effect(target, mde)


def test_multiplier_for_reference_power_is_one():
    assert vp.multiplier_for_power(0.80, alpha=0.05, reference_power=0.80) == pytest.approx(1.0)


def test_multiplier_for_ninety_percent_power():
    expected = (vp.z_alpha(0.05) + vp.z_power(0.90)) / (vp.z_alpha(0.05) + vp.z_power(0.80))
    assert vp.multiplier_for_power(0.90, alpha=0.05) == pytest.approx(expected)


def test_multiplier_for_power_is_mechanism_independent():
    """同一倍数在不同 σ 下都给出同一功效：倍数与机制无关。"""
    multiplier = vp.multiplier_for_power(0.90, alpha=0.05)
    for sigma in (20.0, 55.0, 200.0):
        mde = vp.profit_mde(sigma, sigma, 100000, 100000, alpha=0.05, power=0.80)
        assert vp.profit_power(multiplier * mde, sigma, sigma, 100000, 100000,
                               alpha=0.05) == pytest.approx(0.90)


def test_multiplier_power_round_trip_through_reference_mde():
    for power in (0.85, 0.90, 0.95):
        multiplier = vp.multiplier_for_power(power, alpha=0.05)
        reference_mde = vp.profit_mde(55.0, 55.0, 100000, 100000, alpha=0.05, power=0.80)
        assert vp.profit_power(multiplier * reference_mde, 55.0, 55.0, 100000, 100000,
                               alpha=0.05) == pytest.approx(power)


# --------------------------------------------------------------------------- #
# 10. 设计样本画像：只读五列、只取 train
# --------------------------------------------------------------------------- #
def test_profile_from_frame_computes_sample_statistics():
    frame = _frame(400, treatment_share=0.5)
    profile = vp.profile_from_frame(
        frame, scenario_id="L1_main", rep_id=1000,
        observed_dataset_hash="hash", source_path="path", config_hash="0" * 64)
    treated = frame.loc[frame.treatment == 1, "net_profit"].to_numpy()
    control = frame.loc[frame.treatment == 0, "net_profit"].to_numpy()
    assert profile.n_treatment == treated.size
    assert profile.n_control == control.size
    assert profile.n_total == len(frame)
    assert profile.profit_sd_treatment == pytest.approx(treated.std(ddof=1))
    assert profile.profit_sd_control == pytest.approx(control.std(ddof=1))
    assert profile.purchase_rate_treatment == pytest.approx(
        frame.loc[frame.treatment == 1, "paid_purchase_7d"].mean())
    assert profile.refund_rate_control == pytest.approx(
        frame.loc[frame.treatment == 0, "any_refund_30d"].mean())
    assert profile.refund_rate_treatment == pytest.approx(
        frame.loc[frame.treatment == 1, "any_refund_30d"].mean())
    for arm, values in (("treatment", treated), ("control", control)):
        centered = values - values.mean()
        expected = float(np.mean(centered**4) / np.mean(centered**2) ** 2)
        assert getattr(profile, f"profit_kurtosis_{arm}") == pytest.approx(expected)
    assert profile.split == "train"


def test_profile_rejects_mixed_split_rows():
    frame = _frame(200)
    frame.loc[frame.index[:10], "split"] = "test"
    with pytest.raises(ValueError, match="train"):
        vp.profile_from_frame(frame, scenario_id="L1_main", rep_id=1,
                              observed_dataset_hash="h", source_path="p", config_hash="c")


def test_profile_rejects_truth_columns():
    frame = _frame(200)
    frame["tau_true"] = 0.0
    with pytest.raises(ValueError, match="真值"):
        vp.profile_from_frame(frame, scenario_id="L1_main", rep_id=1,
                              observed_dataset_hash="h", source_path="p", config_hash="c")


def test_profile_rejects_missing_observable_columns():
    frame = _frame(200).drop(columns=["paid_purchase_7d"])
    with pytest.raises(ValueError, match="缺少可观测列"):
        vp.profile_from_frame(frame, scenario_id="L1_main", rep_id=1,
                              observed_dataset_hash="h", source_path="p", config_hash="c")


def test_profile_rejects_single_arm_frame():
    frame = _frame(200)
    frame["treatment"] = 1
    with pytest.raises(ValueError):
        vp.profile_from_frame(frame, scenario_id="L1_main", rep_id=1,
                              observed_dataset_hash="h", source_path="p", config_hash="c")


def test_profile_rejects_non_binary_purchase():
    frame = _frame(200)
    frame.loc[frame.index[0], "paid_purchase_7d"] = 2.0
    with pytest.raises(ValueError, match="paid_purchase_7d"):
        vp.profile_from_frame(frame, scenario_id="L1_main", rep_id=1,
                              observed_dataset_hash="h", source_path="p", config_hash="c")


def test_profile_rejects_non_finite_profit():
    frame = _frame(200)
    frame.loc[frame.index[0], "net_profit"] = float("inf")
    with pytest.raises(ValueError, match="net_profit"):
        vp.profile_from_frame(frame, scenario_id="L1_main", rep_id=1,
                              observed_dataset_hash="h", source_path="p", config_hash="c")


def test_profile_rejects_non_dataframe():
    with pytest.raises(TypeError):
        vp.profile_from_frame([1, 2, 3], scenario_id="L1_main", rep_id=1,
                              observed_dataset_hash="h", source_path="p", config_hash="c")


def test_design_sample_profile_refuses_non_observed_dataset():
    with pytest.raises(TypeError):
        vp.design_sample_profile(_frame(100), scenario_id="L1_main", rep_id=1)  # type: ignore[arg-type]


def test_profile_rejects_non_train_split_label():
    with pytest.raises(ValueError):
        vp.profile_from_frame(_frame(100), scenario_id="L1_main", rep_id=1,
                              observed_dataset_hash="h", source_path="p", config_hash="c",
                              split="test")


def test_profile_record_round_trips_through_json(tmp_path):
    profiles = list(_profiles(load_v3_protocol()).values())
    path = vp.write_profiles_json(profiles, tmp_path / "profiles.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["formal_repetitions_completed"] == 0
    assert payload["source_label"].startswith("合成数据")
    restored = vp.read_profiles_json(path)
    assert set(restored) == {profile.scenario_id for profile in profiles}
    assert restored["L1_main"] == profiles[1]


def test_profile_record_missing_field_is_refused():
    record = vp.profile_to_record(_profile())
    record.pop("profit_sd_control")
    with pytest.raises(ValueError, match="缺字段"):
        vp.profile_from_record(record)


def test_profile_rejects_zero_variance():
    with pytest.raises(ValueError):
        _profile(sd_treatment=0.0)


# --------------------------------------------------------------------------- #
# 11. 队列与对比
# --------------------------------------------------------------------------- #
def test_contrasts_follow_the_registered_cohorts(protocol):
    contrasts = {contrast.cohort_id: contrast for contrast in vp.contrasts_from_config(protocol)}
    assert set(contrasts) == {"full_history", "training", "heldout_test",
                              "independent_validation", "split_validation"}
    assert contrasts["full_history"].n_total == 200000
    assert contrasts["training"].n_total == 100000
    assert contrasts["heldout_test"].n_total == 60000
    assert contrasts["split_validation"].n_total == 40000
    assert "派生" in contrasts["split_validation"].provenance


def test_validation_contrasts_use_three_arm_randomisation(protocol):
    rows = [c for c in vp.contrasts_from_config(protocol) if c.cohort_id == "independent_validation"]
    assert len(rows) == 2
    assert {row.contrast for row in rows} == {"targeted_vs_same_budget_random",
                                              "targeted_vs_no_coupon"}
    for row in rows:
        assert row.family_size == 2
        assert row.arm_labels[0] == "selected_targeted_policy"
        assert row.n_total == 200000
        assert row.n_treatment + row.n_control < row.n_total
        assert abs(row.n_treatment - 200000 / 3) < 1


def test_validation_cohort_is_not_the_same_as_full_history(protocol):
    contrasts = {c.cohort_id: c for c in vp.contrasts_from_config(protocol)}
    assert contrasts["full_history"].n_treatment == 100000
    validation = [c for c in vp.contrasts_from_config(protocol)
                  if c.cohort_id == "independent_validation"]
    assert all(c.n_treatment < 70000 for c in validation)


def test_derived_validation_cohort_tracks_the_split_config(protocol):
    data = protocol.config.to_dict()
    data["design"]["split"] = {**data["design"]["split"], "validation": 0.30}
    patched = V3Protocol(Config(data, name="patched"), protocol.source_hashes, protocol.config_hash)
    contrasts = {c.cohort_id: c for c in vp.contrasts_from_config(patched)}
    assert contrasts["split_validation"].n_total == 60000


# --------------------------------------------------------------------------- #
# 12. 20 个功效格
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def calibrations(protocol, profiles):
    return vp.calibrate_power_cells(protocol, profiles)


def test_all_twenty_power_cells_are_calibrated(protocol, calibrations):
    registered = protocol.config.to_dict()["design_power_jobs"]
    assert len(calibrations) == len(registered) == 20
    assert [cell.cell_id for cell in calibrations] == [cell["id"] for cell in registered]


def test_power_cells_inherit_variance_from_their_own_base_scenario(protocol, calibrations, profiles):
    for cell in calibrations:
        assert cell.profile is profiles[cell.base_scenario_id]
        assert cell.base_scenario_id in protocol.config.require("design.local_power.base_scenarios")


def test_power_cells_use_the_frozen_multiplier_grid(protocol, calibrations):
    grid = protocol.config.require("design.local_power.relative_to_observed_design_mde")
    assert sorted({cell.configured_multiplier for cell in calibrations}) == sorted(float(v) for v in grid)
    for cell in calibrations:
        assert cell.required_multiplier == pytest.approx(cell.configured_multiplier)


def test_unit_multiplier_gives_exactly_the_reference_power(calibrations):
    for cell in calibrations:
        if cell.configured_multiplier == pytest.approx(1.0):
            assert cell.analytic_power == pytest.approx(cell.reference_power)
            assert cell.detectable_at_reference is True
            assert cell.detectable_at_90 is False


def test_zero_multiplier_gives_the_null_rejection_rate(protocol, calibrations):
    alpha = vp.alpha_from_config(protocol)
    for cell in calibrations:
        if cell.configured_multiplier == 0.0:
            assert cell.target_effect == 0.0
            assert cell.analytic_power == pytest.approx(alpha / 2.0)
            assert cell.detectable_at_reference is False


def test_underpowered_cells_are_exactly_the_halved_and_zero_multipliers(calibrations):
    """点名：倍数 0 与 0.5 的 8 个格"目标效应 < MDE"，在 80% 功效下验不出。"""
    failing = {cell.cell_id for cell in calibrations if not cell.detectable_at_reference}
    expected = {
        f"{level}_power_mde{label}"
        for level in ("L0", "L1", "L2", "L3")
        for label in ("000", "050")
    }
    assert failing == expected
    assert len(failing) == 8


def test_ninety_percent_target_needs_more_than_unit_multiplier(calibrations):
    """倍数 1.0 只给到 80% 功效；要 90% 必须 >= 1.157。"""
    failing_90 = {cell.cell_id for cell in calibrations if not cell.detectable_at_90}
    expected = {
        f"{level}_power_mde{label}"
        for level in ("L0", "L1", "L2", "L3")
        for label in ("000", "050", "100")
    }
    assert failing_90 == expected
    assert all(cell.required_multiplier_90 == pytest.approx(1.1570290737998699, rel=1e-9)
               for cell in calibrations)


def test_high_multiplier_cells_clear_both_targets(calibrations):
    for cell in calibrations:
        if cell.configured_multiplier >= 1.5:
            assert cell.detectable_at_reference and cell.detectable_at_90
            assert cell.analytic_power > 0.98


def test_power_cell_boundary_flag_separates_the_zero_margin_cells(mde_rows):
    """C5：mde100 必须被编码为边界格，不能只靠散文；下游只看 detectable_at_80 会误判。"""
    cells = [row for row in mde_rows if row["record_type"] == "power_cell"]
    assert len(cells) == 20
    boundary = [row for row in cells if row["boundary_flag"]]
    assert len(boundary) == 4
    assert sorted(row["configured_multiplier"] for row in boundary) == pytest.approx(
        [1.0, 1.0, 1.0, 1.0])
    for row in boundary:
        assert row["power_cell_class"] == "boundary_zero_margin"
        assert row["margin_ratio"] == pytest.approx(1.0)
        assert row["effect_margin"] == pytest.approx(0.0, abs=1e-12)
        assert row["power_margin"] == pytest.approx(0.0, abs=1e-12)
        assert "边界格" in row["boundary_note"]
        assert row["power_at_sigma_plus_1se"] < row["analytic_power"]
    below = [row for row in cells if row["power_cell_class"] == "below_design_mde"]
    above = [row for row in cells if row["power_cell_class"] == "above_design_mde"]
    assert len(below) == 8 and len(above) == 8
    for row in below:
        assert row["margin_ratio"] < 1.0
        assert row["detectable_at_80"] is False
    for row in above:
        assert row["margin_ratio"] > 1.0
        assert row["detectable_at_80"] is True
        assert row["power_margin"] > 0.0


def test_downstream_gate_that_ignores_boundary_flag_would_overcount(mde_rows):
    cells = [row for row in mde_rows if row["record_type"] == "power_cell"]
    naive_pass = [row for row in cells if row["detectable_at_80"]]
    safe_pass = [row for row in naive_pass if not row["boundary_flag"]]
    assert len(naive_pass) == 12
    assert len(safe_pass) == 8
    assert sorted(row["configured_multiplier"] for row in safe_pass) == pytest.approx(
        [1.5, 1.5, 1.5, 1.5, 2.0, 2.0, 2.0, 2.0])


def test_one_sided_rows_annotate_the_alpha_caliber_gap(mde_rows):
    """C5：主检验单侧行沿用双侧 α=0.05（不是 0.025），必须在表里可识别。"""
    design = [row for row in mde_rows if row["record_type"] == "design_mde"]
    one_sided = [row for row in design if row["sides"] == vp.ONE_SIDED]
    two_sided = [row for row in design if row["sides"] == vp.TWO_SIDED]
    assert one_sided and two_sided
    for row in one_sided:
        assert row["alpha_one_sided"] == pytest.approx(0.05)
        assert "one_sided_uses_alpha_two_sided_value" in row["sides_note"]
    for row in two_sided:
        assert row["alpha_one_sided"] is None
        assert row["sides_note"] is None


def test_calibration_entry_accepts_an_explicit_target_effect(protocol):
    profile = _profiles(protocol)["L1_main"]
    reference = vp.calibrate_power_cell(
        "probe", profile, level="L1", n_total=200000, treatment_probability=0.5,
        alpha=0.05, reference_power=0.80, configured_multiplier=1.0)
    doubled = vp.calibrate_power_cell(
        "probe", profile, level="L1", n_total=200000, treatment_probability=0.5,
        alpha=0.05, reference_power=0.80, configured_multiplier=1.0,
        target_effect=2.0 * reference.design_mde)
    assert doubled.required_multiplier == pytest.approx(2.0)
    assert doubled.analytic_power > reference.analytic_power
    assert doubled.detectable_at_90 is True


def test_calibration_entry_flags_targets_below_the_design_mde(protocol):
    profile = _profiles(protocol)["L1_main"]
    mde = vp.profit_mde(profile.profit_sd_treatment, profile.profit_sd_control, 100000, 100000,
                        alpha=0.05, power=0.80)
    weak = vp.calibrate_power_cell(
        "probe", profile, level="L1", n_total=200000, treatment_probability=0.5,
        alpha=0.05, reference_power=0.80, configured_multiplier=1.0,
        target_effect=0.9 * mde)
    assert weak.required_multiplier == pytest.approx(0.9)
    assert weak.detectable_at_reference is False


def test_calibration_entry_rejects_negative_target(protocol):
    with pytest.raises(ValueError):
        vp.calibrate_power_cell(
            "probe", _profiles(protocol)["L1_main"], level="L1", n_total=200000,
            treatment_probability=0.5, alpha=0.05, reference_power=0.80,
            configured_multiplier=1.0, target_effect=-1.0)


def test_missing_base_scenario_profile_is_refused(protocol):
    profiles = _profiles(protocol)
    profiles.pop("L3_fixed_lt000")
    with pytest.raises(ValueError, match="缺少"):
        vp.calibrate_power_cells(protocol, profiles)


def test_power_cell_without_frozen_multiplier_is_refused(protocol):
    data = protocol.config.to_dict()
    for cell in data["design_power_jobs"]:
        cell["overrides"].pop("design.local_power.active_mde_multiplier", None)
    patched = V3Protocol(Config(data, name="patched"), protocol.source_hashes, protocol.config_hash)
    with pytest.raises(ValueError, match="active_mde_multiplier"):
        vp.calibrate_power_cells(patched, _profiles(protocol))


# --------------------------------------------------------------------------- #
# 13. 汇总表
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def mde_rows(protocol, profiles):
    return vp.build_mde_rows(protocol, profiles)


def test_rows_cover_design_and_power_cells(mde_rows, protocol):
    base_scenarios = [str(name) for name in protocol.config.require("design.local_power.base_scenarios")]
    assert len(mde_rows) == 176 * len(base_scenarios) + 2 * len(base_scenarios) + 20
    assert sum(1 for row in mde_rows if row["record_type"] == "design_mde") == 176 * len(base_scenarios)
    assert sum(1 for row in mde_rows if row["record_type"] == "guardrail_mde") == 2 * len(base_scenarios)
    assert sum(1 for row in mde_rows if row["record_type"] == "power_cell") == 20
    assert all(row["data_source"] == protocol.config.require("project.data_source_label")
               for row in mde_rows)


def test_rows_cover_every_reference_mechanism(protocol, mde_rows):
    """σ 与 p0 随机制变化，所以四层都要各有 design_mde 行，不能只报 L1。"""
    reference = protocol.config.section("matrix_contract")["reference_scenarios"]
    design_rows = [row for row in mde_rows if row["record_type"] == "design_mde"]
    assert {row["scenario_id"] for row in design_rows} == set(reference.values())
    assert {row["level"] for row in design_rows} == set(reference)
    for level, scenario_id in reference.items():
        per_level = [row for row in design_rows if row["scenario_id"] == scenario_id]
        assert len(per_level) == 176
        assert {row["level"] for row in per_level} == {level}


def test_primary_rows_are_confined_to_the_primary_design_scenario(protocol, mde_rows):
    primary_design = [row for row in mde_rows
                      if row["record_type"] == "design_mde" and row["primary_row"]]
    assert primary_design
    assert {row["scenario_id"] for row in primary_design} == {vp.design_scenario_id(protocol)}
    assert all(row["sides"] == vp.TWO_SIDED for row in primary_design)
    assert all(row["power_target"] == pytest.approx(0.80) for row in primary_design)
    assert all(row["multiplicity"] == "none" for row in primary_design)


def test_rows_never_mix_total_sample_with_arm_samples(mde_rows):
    for row in mde_rows:
        assert row["n_treatment"] + row["n_control"] <= row["n_total"]
        assert row["n_treatment"] > 0 and row["n_control"] > 0
        assert row["treatment_share"] == pytest.approx(
            row["n_treatment"] / (row["n_treatment"] + row["n_control"]))


def test_rows_report_both_power_targets_and_both_sides(mde_rows):
    design = [row for row in mde_rows if row["record_type"] == "design_mde"]
    assert sorted({row["power_target"] for row in design}) == pytest.approx([0.80, 0.90])
    assert {row["sides"] for row in design} == {vp.TWO_SIDED, vp.ONE_SIDED}
    cells = [row for row in mde_rows if row["record_type"] == "power_cell"]
    assert all(row["power_target"] == pytest.approx(0.80) for row in cells)


def test_rows_report_three_allocation_shares_for_history_cohorts(mde_rows):
    shares = {round(row["treatment_share"], 10) for row in mde_rows
              if row["cohort_id"] in {"full_history", "training", "heldout_test"}}
    assert shares == {0.5, 0.3, 0.1}


def test_rows_report_holm_and_single_test_variants(mde_rows):
    holm = [row for row in mde_rows if row["multiplicity"] == "holm"]
    assert holm
    assert all(row["family_size"] == 2 for row in holm)
    assert all(row["alpha_per_test"] == pytest.approx(row["alpha"] / 2.0) for row in holm)
    single = [row for row in mde_rows if row["multiplicity"] == "none"]
    assert all(row["alpha_per_test"] == pytest.approx(row["alpha"]) for row in single)


def test_rows_keep_mde_positive_and_analytic_power_consistent(mde_rows):
    """design_mde 行的 analytic_power 是"MDE 处的功效"（== 目标功效，自校验）；
    power_cell 行的是"目标效应处的功效"，所以只有前者能对 power_target 取值。"""
    for row in mde_rows:
        assert math.isfinite(row["mde"]) and row["mde"] > 0.0
        if row["record_type"] == "design_mde":
            assert row["analytic_power"] == pytest.approx(row["power_target"], abs=1e-9)
        else:
            assert 0.0 < row["analytic_power"] < 1.0


def test_purchase_rows_report_baseline_rate_and_percentage_points(mde_rows):
    purchase = [row for row in mde_rows if row["metric"] == "paid_purchase_7d"]
    assert purchase
    for row in purchase:
        assert 0.0 < row["p0_baseline"] < 1.0
        assert row["p1_at_mde"] == pytest.approx(row["p0_baseline"] + row["mde"])
        assert row["mde_pp"] == pytest.approx(row["mde"] * 100.0)
        assert row["mde_unit"] == "probability"
    profit = [row for row in mde_rows if row["metric"] == "net_profit_30d_per_assigned_user"]
    assert all(row["p0_baseline"] is None and row["mde_pp"] is None for row in profit)
    assert all(row["mde_unit"] == "CNY_per_assigned_user" for row in profit)


def test_power_rows_flag_detectability_and_pending_empirics(mde_rows):
    cells = [row for row in mde_rows if row["record_type"] == "power_cell"]
    assert all(row["primary_row"] is True for row in cells)
    assert all("pending" in row["notes"] for row in cells)
    assert {row["detectable_at_80"] for row in cells} == {True, False}
    for row in cells:
        assert row["target_effect"] == pytest.approx(row["configured_multiplier"] * row["mde"])


def test_csv_writer_round_trips_with_utf8_bom(mde_rows, tmp_path):
    path = vp.write_mde_csv(mde_rows, tmp_path / "mde.csv")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    frame = vp.read_mde_csv(path)
    assert tuple(frame.columns) == vp.MDE_TABLE_COLUMNS
    assert len(frame) == len(mde_rows)
    assert frame["mde"].notna().all()


def test_csv_writer_refuses_unknown_columns(mde_rows, tmp_path):
    rows = [dict(mde_rows[0], surprise_column=1.0)]
    with pytest.raises(ValueError, match="未登记列"):
        vp.write_mde_csv(rows, tmp_path / "bad.csv")


def test_committed_table_matches_its_schema(protocol):
    path = ROOT / "outputs" / "tables" / "v3_phase_D_mde.csv"
    if not path.exists():  # pragma: no cover - 表由 --table 生成后才会存在
        pytest.skip("尚未生成 v3_phase_D_mde.csv")
    frame = vp.read_mde_csv(path)
    dataset_cells = len(protocol.config.require("design.local_power.base_scenarios"))
    assert len(frame) == 176 * dataset_cells + 2 * dataset_cells + 20
    assert set(frame["record_type"]) == {"design_mde", "guardrail_mde", "power_cell"}
    assert frame["data_source"].str.startswith("合成数据").all()


# --------------------------------------------------------------------------- #
# 14. 实测功效汇总入口（C3）：只汇总真实逐 rep 结果，不伪造
# --------------------------------------------------------------------------- #
def _rep_rows(cell_id: str = "L1_power_mde100", reps: int = 100, hits: int = 80,
              effect: float = 0.1303) -> list[dict[str, object]]:
    """构造 R 次重复的逐 rep 结果（含达成效应与是否拒绝）。"""
    return [
        {"cell_id": cell_id, "rep_id": rep, "effect_estimate": effect + 0.0001 * rep,
         "reject": rep < hits}
        for rep in range(reps)
    ]


def test_summarize_power_cells_recomputes_rate_and_binomial_interval():
    rows = _rep_rows(reps=100, hits=80)
    summary = vp.summarize_power_cells(rows)
    assert tuple(summary.columns) == vp.POWER_CELL_SUMMARY_COLUMNS
    row = summary.iloc[0]
    assert row["n_reps"] == 100
    assert row["rejection_rate"] == pytest.approx(0.80)
    assert row["mc_se"] == pytest.approx(math.sqrt(0.8 * 0.2 / 100))
    assert row["binomial_ci_low"] < 0.80 < row["binomial_ci_high"]
    assert row["binomial_ci_low"] == pytest.approx(0.708, abs=0.01)
    assert row["binomial_ci_high"] == pytest.approx(0.874, abs=0.01)
    assert row["achieved_effect"] == pytest.approx(
        np.mean([row_["effect_estimate"] for row_ in rows]))
    assert row["achieved_effect_mc_se"] == pytest.approx(
        np.std([row_["effect_estimate"] for row_ in rows], ddof=1) / math.sqrt(100))


def test_summarize_power_cells_accepts_a_dataframe_and_multiple_cells():
    rows = _rep_rows("L1_power_mde100", reps=50, hits=40) + _rep_rows(
        "L3_power_mde050", reps=50, hits=5, effect=0.05)
    summary = vp.summarize_power_cells(pd.DataFrame(rows))
    assert list(summary["cell_id"]) == ["L1_power_mde100", "L3_power_mde050"]
    assert summary.iloc[1]["rejection_rate"] == pytest.approx(0.10)


@pytest.mark.parametrize("mutation,message", [
    (lambda rows: [{"cell_id": "x", "rep_id": 0, "effect_estimate": 1.0} for _ in range(2)], "缺少列"),
    (lambda rows: [], "为空"),
])
def test_summarize_power_cells_rejects_missing_payload(mutation, message):
    with pytest.raises(ValueError, match=message):
        vp.summarize_power_cells(mutation(_rep_rows()))


def test_summarize_power_cells_rejects_duplicate_reps():
    rows = _rep_rows(reps=4)
    rows.append(dict(rows[0]))
    with pytest.raises(ValueError, match="重复"):
        vp.summarize_power_cells(rows)


def test_summarize_power_cells_rejects_single_rep():
    with pytest.raises(ValueError, match="MC_SE"):
        vp.summarize_power_cells(_rep_rows(reps=1))


@pytest.mark.parametrize("reject,effect", [(2, 0.1), (True, float("nan")), (False, float("inf"))])
def test_summarize_power_cells_rejects_bad_values(reject, effect):
    rows = _rep_rows(reps=4)
    rows[0] = {"cell_id": "x", "rep_id": 0, "effect_estimate": effect, "reject": reject}
    with pytest.raises(ValueError):
        vp.summarize_power_cells(rows)


def test_power_cell_rows_leave_empirics_empty_and_pending(mde_rows):
    """C3：没有真实重复时，实测列必须为空并写 pending，绝不能用解析功效冒充。"""
    cells = [row for row in mde_rows if row["record_type"] == "power_cell"]
    for row in cells:
        for column in ("achieved_effect", "rejection_rate", "mc_se",
                       "binomial_ci_low", "binomial_ci_high", "empirical_n_reps"):
            assert row[column] is None
        assert vp.PENDING_LOCAL_POWER in row["notes"]


def test_committed_table_leaves_empirics_empty_and_marks_pending():
    path = ROOT / "outputs" / "tables" / "v3_phase_D_mde.csv"
    if not path.exists():  # pragma: no cover - 表由 --table 生成后才会存在
        pytest.skip("尚未生成 v3_phase_D_mde.csv")
    frame = vp.read_mde_csv(path)
    for column in ("achieved_effect", "rejection_rate", "mc_se",
                   "binomial_ci_low", "binomial_ci_high", "empirical_n_reps"):
        assert frame[column].isna().all()
    assert frame["notes"].str.contains(vp.PENDING_LOCAL_POWER, regex=False).all()


# --------------------------------------------------------------------------- #
# 15. 不读真值：导入期与 AST 双重证据
# --------------------------------------------------------------------------- #
def test_module_does_not_import_dgp_at_import_time():
    code = ("import sys; import causal_growth.design.v3_power; "
            "print('causal_growth.dgp' in sys.modules)")
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                               encoding="utf-8", check=True)
    assert completed.stdout.strip() == "False"


def test_dgp_import_is_confined_to_the_pilot_generator():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    offenders: list[str] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        suspicious = [m for m in modules if m.startswith("causal_growth.dgp") or ".audit" in m]
        if not suspicious:
            continue
        holders = [fn.name for fn in functions
                   if any(child is node for child in ast.walk(fn))]
        if holders != ["_generate_design_sample"]:
            offenders.append(f"line {node.lineno}: {suspicious} in {holders}")
    assert offenders == []


def test_module_only_reads_the_registered_observable_columns():
    """观测列白名单是**五列**：四个原列 + C2 的护栏退款列；真值/审计列仍在禁止名单。"""
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "OBSERVED_COLUMNS" in source
    assert set(vp.OBSERVED_COLUMNS) == {"treatment", "net_profit", "paid_purchase_7d",
                                        "any_refund_30d", "split"}
    assert vp.GUARDRAIL_COLUMN == "any_refund_30d"
    for forbidden in ("audit_u", "potential_outcome", "true_propensity", "l0.control"):
        assert forbidden not in source


# --------------------------------------------------------------------------- #
# 16. 先导模拟的编号纪律
# --------------------------------------------------------------------------- #
def test_pilot_rep_ids_start_after_the_formal_grid(protocol):
    data = protocol.config.to_dict()
    max_r = max(cell["R"] for cell in data["scenarios"] + data["design_power_jobs"])
    reps = vp.design_pilot_rep_ids(protocol, 4)
    assert len(reps) == 4
    assert min(reps) >= max_r
    assert list(reps) == list(range(max_r, max_r + 4))


def test_pilot_rep_ids_refuse_zero_count(protocol):
    with pytest.raises(ValueError):
        vp.design_pilot_rep_ids(protocol, 0)


def test_pilot_rejects_mismatched_rep_count(protocol):
    with pytest.raises(ValueError):
        vp.run_design_pilot(["L1_main"], work_root="out/_unused", protocol=protocol, rep_ids=[1, 2])
