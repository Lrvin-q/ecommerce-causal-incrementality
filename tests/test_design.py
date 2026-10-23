"""design 子包的验收测试（方案 §2.4 主线二 / GOAL.md ⑧⑨⑩）。

守的几条红线：

* **符号**：``n_per_group``（每组）与 ``n_total``（总）不得混用（AGENTS.md §4）；
* **取较大值**：转化率与利润分别算样本量、取较大值，且写明是谁在约束（GOAL ⑧）；
* **AA 读法**：看 p 值分布是否接近 Uniform、假阳性率是否 ≈ α，**不看单次是否显著**
  （方案 §2.4 原文；GOAL ⑨）；
* **护栏**："不显著" ≠ "安全"，必须用单侧 CI 对预设界值判断（GOAL ⑩）；
* **多重比较**：保持输入顺序、截断到 [0,1]、Bonferroni/Holm/BH 对已知答案。
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import norm

from causal_growth.config import load_config
from causal_growth.design import (
    AAResult,
    MultiplicityResult,
    NonInferiorityResult,
    SampleSizeResult,
    aa_test_binary,
    aa_test_continuous,
    adjust,
    benjamini_hochberg,
    bonferroni,
    design_sample_size,
    holm,
    noninferiority_binary,
    sample_size_mean,
    sample_size_proportion,
    sample_size_unequal,
    summarize_pvalues,
)

MASTER_SEED = 20240101

#: 与 configs/base.yaml 保持一致的统计量（测试内独立复核用，不是业务参数来源）
Z_ALPHA = float(norm.ppf(1.0 - 0.05 / 2.0))
Z_BETA = float(norm.ppf(0.80))


@pytest.fixture(scope="module")
def cfg():
    """真实配置（口径以 configs/base.yaml 为准，测试不从别处抄业务参数）。"""
    return load_config()


@pytest.fixture(scope="module")
def aa_binary() -> AAResult:
    """二元指标 AA：1000 次重复、每组 2000 人（测试用的适度规模）。"""
    return aa_test_binary(0.10, 2000, 1000, alpha=0.05, master_seed=MASTER_SEED)


@pytest.fixture(scope="module")
def aa_continuous() -> AAResult:
    """连续指标 AA：1000 次重复、每组 2000 人。"""
    return aa_test_continuous(0.0, 45.0, 2000, 1000, alpha=0.05, master_seed=MASTER_SEED)


# --------------------------------------------------------------------------- #
# 1. 样本量：比例指标
# --------------------------------------------------------------------------- #
class TestSampleSizeProportion:
    def test_known_answer_14749(self) -> None:
        """手算基准：p0=0.10、Δ=0.01、α=0.05、power=0.80 → 每组 14749。"""
        n = sample_size_proportion(p0=0.10, mde_abs=0.01, alpha=0.05, power=0.80)
        assert n == 14749

    def test_matches_closed_form_with_ceil(self) -> None:
        """用 norm.ppf 现算闭式公式，验证"向上取整 + 用 ppf 取 z"这两点。"""
        p0, delta = 0.10, 0.01
        p1 = p0 + delta
        raw = (Z_ALPHA + Z_BETA) ** 2 * (p1 * (1 - p1) + p0 * (1 - p0)) / delta**2
        assert sample_size_proportion(p0, delta) == math.ceil(raw)
        assert math.ceil(raw) == 14749

    def test_floor_is_two(self) -> None:
        """极端大 MDE 时公式给 1，但每组下限是 2（单组 1 人方差无定义）。"""
        raw = (Z_ALPHA + Z_BETA) ** 2 * (
            (0.001 + 0.9) * (1 - 0.001 - 0.9) + 0.001 * 0.999
        ) / 0.9**2
        assert raw < 2.0, "构造失败：本例应落在下限以下"
        assert sample_size_proportion(0.001, 0.9) == 2

    def test_smaller_mde_needs_more_users(self) -> None:
        wide = sample_size_proportion(0.10, 0.02)
        narrow = sample_size_proportion(0.10, 0.01)
        assert narrow > wide

    @pytest.mark.parametrize(
        ("p0", "mde"),
        [(0.10, 0.95), (0.5, 0.51), (0.0, 0.01), (1.0, 0.01), (0.10, 0.0), (0.10, -0.01)],
    )
    def test_invalid_probability_shift(self, p0: float, mde: float) -> None:
        with pytest.raises(ValueError):
            sample_size_proportion(p0, mde)

    @pytest.mark.parametrize(("alpha", "power"), [(0.0, 0.8), (1.0, 0.8), (0.05, 0.0), (0.05, 1.0)])
    def test_invalid_alpha_power(self, alpha: float, power: float) -> None:
        with pytest.raises(ValueError):
            sample_size_proportion(0.10, 0.01, alpha=alpha, power=power)

    def test_non_numeric_rejected(self) -> None:
        with pytest.raises(TypeError):
            sample_size_proportion("0.1", 0.01)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 2. 样本量：连续指标
# --------------------------------------------------------------------------- #
class TestSampleSizeMean:
    def test_known_answer_31788(self) -> None:
        """手算基准：σ=45、Δ=1.0、α=0.05、power=0.80 → 每组 31788。

        注意：任务书初稿写 31789 是算术笔误，按公式与 norm.ppf 复核为 31788。
        """
        n = sample_size_mean(sigma=45.0, mde_abs=1.0, alpha=0.05, power=0.80)
        assert n == 31788

    def test_matches_closed_form_with_ceil(self) -> None:
        sigma, delta = 45.0, 1.0
        raw = (Z_ALPHA + Z_BETA) ** 2 * 2.0 * sigma**2 / delta**2
        assert sample_size_mean(sigma, delta) == math.ceil(raw)

    def test_scales_with_sigma_squared(self) -> None:
        """σ 翻倍 → 样本量 ×4（方案要求的"若方差是假设值的 k 倍，样本量乘 k²"）。"""
        base = sample_size_mean(45.0, 1.0)
        doubled = sample_size_mean(90.0, 1.0)
        assert abs(doubled - 4 * base) <= 2

    @pytest.mark.parametrize(("sigma", "mde"), [(0.0, 1.0), (-1.0, 1.0), (45.0, 0.0), (45.0, -1.0)])
    def test_invalid_inputs(self, sigma: float, mde: float) -> None:
        with pytest.raises(ValueError):
            sample_size_mean(sigma, mde)


# --------------------------------------------------------------------------- #
# 3. 样本量：非等比分流
# --------------------------------------------------------------------------- #
class TestSampleSizeUnequal:
    def test_balanced_matches_equal_allocation(self) -> None:
        """w=0.5 时退化为 1:1 的每组 14749。"""
        n_treat, n_control = sample_size_unequal(0.10, 0.01, 0.5)
        assert (n_treat, n_control) == (14749, 14749)
        assert n_treat == sample_size_proportion(0.10, 0.01)

    def test_thirty_seventy(self) -> None:
        """w=0.30 时处理组更小、对照组更大，且总样本多于 1:1 设计。"""
        n_treat, n_control = sample_size_unequal(0.10, 0.01, 0.30)
        assert n_treat < n_control
        assert n_treat + n_control > 2 * sample_size_proportion(0.10, 0.01)
        # 复核份额
        assert n_treat / (n_treat + n_control) == pytest.approx(0.30, abs=0.001)

    @pytest.mark.parametrize("share", [0.0, 1.0, -0.1, 1.5])
    def test_invalid_share(self, share: float) -> None:
        with pytest.raises(ValueError):
            sample_size_unequal(0.10, 0.01, share)


# --------------------------------------------------------------------------- #
# 4. 按配置装配
# --------------------------------------------------------------------------- #
class TestDesignSampleSize:
    def test_binding_metric_is_conversion_in_base_config(self, cfg) -> None:
        """GOAL ⑧：两者取较大值。在本项目基准参数下，**约束者是转化率指标**。

        这是一个反直觉但重要的结果：利润是主指标，却不是样本量的约束者。
        原因是利润指标方差仅 11.08 元/人（87% 用户利润为 0，高度零膨胀），
        检出 0.5 元/人的效应只需 7,709/组；而转化率要检出 1 个百分点的
        绝对增量（相对提升 10%）需要 14,749/组。

        正因如此，方案才要求"分别算、取较大值"——只按利润算样本量，
        转化率的功效会不足。
        """
        result = design_sample_size(cfg)
        assert isinstance(result, SampleSizeResult)
        assert result.n_per_group_conversion > result.n_per_group_profit
        assert result.binding_metric == "conversion"
        assert result.n_per_group == max(
            result.n_per_group_conversion, result.n_per_group_profit
        )

    def test_binding_metric_flips_when_profit_variance_grows(self, cfg) -> None:
        """方差翻倍 → 利润指标所需样本量 ×4，约束者应翻转为 profit。

        这条测试守住"取较大值"逻辑本身，而不是某个具体的绑定结果。
        """
        worse = cfg.with_overrides({"experiment.mde.profit_sd_assumed": 21.6})
        result = design_sample_size(worse)
        assert result.n_per_group_profit > result.n_per_group_conversion
        assert result.binding_metric == "profit"

    def test_symbol_red_line_n_total_is_twice_per_group(self, cfg) -> None:
        """AGENTS.md §4：1:1 分流下 n_total = 2 * n_per_group，禁止混用符号。"""
        result = design_sample_size(cfg)
        assert result.n_total == 2 * result.n_per_group
        assert result.n_total != result.n_per_group

    def test_config_values_are_honoured(self, cfg) -> None:
        """结果必须等于用配置参数分别调两个公式所得（不允许代码里藏业务常数）。"""
        result = design_sample_size(cfg)
        expected_conv = sample_size_proportion(
            float(cfg.require("business.baseline_conversion")),
            float(cfg.require("experiment.mde.conversion_abs")),
            alpha=float(cfg.require("experiment.alpha")),
            power=float(cfg.require("experiment.power")),
        )
        expected_profit = sample_size_mean(
            float(cfg.require("experiment.mde.profit_sd_assumed")),
            float(cfg.require("experiment.mde.profit_per_user")),
            alpha=float(cfg.require("experiment.alpha")),
            power=float(cfg.require("experiment.power")),
        )
        assert result.n_per_group_conversion == expected_conv == 14749
        # 7,709 由 σ=11.08 元/人（加入复购路径后的实测标准差）算出；
        # σ 从 10.8 变成 11.08 使样本量 ×1.053。
        assert result.n_per_group_profit == expected_profit == 7709

    def test_inputs_are_traceable(self, cfg) -> None:
        """报告要能逐项追溯：inputs 里必须有全部业务输入与 z 值。"""
        inputs = design_sample_size(cfg).inputs
        for key in (
            "p0",
            "p1",
            "alpha",
            "power",
            "z_1_minus_alpha_over_2",
            "z_1_minus_beta",
            "mde_conversion_abs",
            "mde_profit_per_user",
            "profit_sd_assumed",
            "allocation",
        ):
            assert key in inputs, key
        assert inputs["p1"] == pytest.approx(inputs["p0"] + inputs["mde_conversion_abs"])
        assert inputs["z_1_minus_alpha_over_2"] == pytest.approx(Z_ALPHA)
        assert inputs["z_1_minus_beta"] == pytest.approx(Z_BETA)
        assert inputs["allocation"] == "1:1"

    def test_baseline_override_changes_conversion_arm(self, cfg) -> None:
        """改 p0 只动转化率那一支的样本量（证明参数确实读自配置）。"""
        base = design_sample_size(cfg)
        changed = design_sample_size(
            cfg.with_overrides({"business.baseline_conversion": 0.12})
        )
        assert changed.n_per_group_conversion != base.n_per_group_conversion
        assert changed.n_per_group_conversion == sample_size_proportion(0.12, 0.01)

    def test_sigma_override_moves_profit_arm(self, cfg) -> None:
        """σ 翻倍 → 利润支样本量约 ×4（用相对倍数，避免写死配置值）。"""
        base = design_sample_size(cfg)
        base_sigma = float(cfg.require("experiment.mde.profit_sd_assumed"))
        doubled = design_sample_size(
            cfg.with_overrides({"experiment.mde.profit_sd_assumed": 2.0 * base_sigma})
        )
        # 样本量 ∝ σ²，翻倍 σ 应得到 4 倍；允许向上取整带来的 ±2 误差
        assert abs(doubled.n_per_group_profit - 4 * base.n_per_group_profit) <= 2

    def test_unequal_allocation_is_rejected(self, cfg) -> None:
        """n_total = 2 * n_per_group 只在 1:1 下成立，非等比分流必须失败要响。"""
        with pytest.raises(ValueError, match="1:1"):
            design_sample_size(cfg.with_overrides({"experiment.treatment_share": 0.30}))


# --------------------------------------------------------------------------- #
# 5. AA 校验（二元）
# --------------------------------------------------------------------------- #
class TestAABinary:
    def test_false_positive_rate_in_acceptance_band(self, aa_binary: AAResult) -> None:
        """GOAL ⑨：假阳性率落在 [0.035, 0.065]。"""
        assert 0.035 <= aa_binary.false_positive_rate <= 0.065, aa_binary.false_positive_rate

    def test_pvalues_look_uniform(self, aa_binary: AAResult) -> None:
        """GOAL ⑨：p 值对 Uniform(0,1) 的 KS 检验不拒绝（p > 0.01）。"""
        assert aa_binary.ks_uniform_pvalue > 0.01
        assert 0.0 <= aa_binary.ks_uniform_stat <= 1.0

    def test_mean_p_value_near_half(self, aa_binary: AAResult) -> None:
        assert aa_binary.mean_p_value == pytest.approx(0.5, abs=0.06)

    def test_metadata_and_array_shape(self, aa_binary: AAResult) -> None:
        assert aa_binary.n_repeats == 1000
        assert aa_binary.alpha == pytest.approx(0.05)
        assert aa_binary.p_values.shape == (1000,)
        assert np.all(aa_binary.p_values >= 0.0) and np.all(aa_binary.p_values <= 1.0)
        assert aa_binary.false_positive_rate == pytest.approx(
            float(np.mean(aa_binary.p_values < 0.05))
        )

    def test_wilson_ci_brackets_point_estimate(self, aa_binary: AAResult) -> None:
        lower, upper = aa_binary.fpr_ci
        assert 0.0 <= lower <= aa_binary.false_positive_rate <= upper <= 1.0
        assert upper - lower < 0.1, "1000 次重复的 FPR 区间不应过宽"

    def test_reproducible_with_same_seed(self) -> None:
        a = aa_test_binary(0.10, 500, 20, master_seed=MASTER_SEED)
        b = aa_test_binary(0.10, 500, 20, master_seed=MASTER_SEED)
        assert np.array_equal(a.p_values, b.p_values)

    def test_different_seed_gives_different_draws(self) -> None:
        a = aa_test_binary(0.10, 500, 20, master_seed=MASTER_SEED)
        b = aa_test_binary(0.10, 500, 20, master_seed=MASTER_SEED + 1)
        assert not np.array_equal(a.p_values, b.p_values)


# --------------------------------------------------------------------------- #
# 6. AA 校验（连续）
# --------------------------------------------------------------------------- #
class TestAAContinuous:
    def test_false_positive_rate_in_acceptance_band(self, aa_continuous: AAResult) -> None:
        assert 0.035 <= aa_continuous.false_positive_rate <= 0.065, (
            aa_continuous.false_positive_rate
        )

    def test_pvalues_look_uniform(self, aa_continuous: AAResult) -> None:
        assert aa_continuous.ks_uniform_pvalue > 0.01
        assert aa_continuous.mean_p_value == pytest.approx(0.5, abs=0.06)

    def test_reproducible_with_same_seed(self) -> None:
        a = aa_test_continuous(0.0, 45.0, 200, 10, master_seed=MASTER_SEED)
        b = aa_test_continuous(0.0, 45.0, 200, 10, master_seed=MASTER_SEED)
        assert np.array_equal(a.p_values, b.p_values)


# --------------------------------------------------------------------------- #
# 7. summarize_pvalues 与入参守卫
# --------------------------------------------------------------------------- #
class TestSummarizePvalues:
    def test_known_small_example(self) -> None:
        p = [0.001, 0.02, 0.5, 0.9, 0.99]
        result = summarize_pvalues(p, alpha=0.05)
        assert result.n_repeats == 5
        assert result.false_positive_rate == pytest.approx(0.4)
        assert result.mean_p_value == pytest.approx(float(np.mean(p)))
        assert result.fpr_ci[0] <= 0.4 <= result.fpr_ci[1]

    @pytest.mark.parametrize(
        "bad",
        [
            [],
            [0.1, float("nan")],
            [0.1, 1.2],
            [-0.01, 0.5],
            [[0.1, 0.2], [0.3, 0.4]],
        ],
    )
    def test_invalid_pvalues_raise(self, bad) -> None:
        with pytest.raises(ValueError):
            summarize_pvalues(bad)

    def test_invalid_alpha_raises(self) -> None:
        with pytest.raises(ValueError):
            summarize_pvalues([0.1, 0.2], alpha=0.0)


class TestAAValidation:
    @pytest.mark.parametrize(
        ("p0", "n", "repeats"),
        [(0.0, 100, 10), (1.0, 100, 10), (0.1, 1, 10), (0.1, 100, 0)],
    )
    def test_binary_invalid(self, p0: float, n: int, repeats: int) -> None:
        with pytest.raises(ValueError):
            aa_test_binary(p0, n, repeats, master_seed=MASTER_SEED)

    @pytest.mark.parametrize(
        ("sd", "n", "repeats"),
        [(0.0, 100, 10), (-1.0, 100, 10), (1.0, 1, 10), (1.0, 100, 0)],
    )
    def test_continuous_invalid(self, sd: float, n: int, repeats: int) -> None:
        with pytest.raises(ValueError):
            aa_test_continuous(0.0, sd, n, repeats, master_seed=MASTER_SEED)

    def test_float_repeats_rejected(self) -> None:
        with pytest.raises(TypeError):
            aa_test_binary(0.1, 100, 10.0, master_seed=MASTER_SEED)  # type: ignore[arg-type]

    def test_bool_seed_rejected(self) -> None:
        with pytest.raises(TypeError):
            aa_test_binary(0.1, 100, 10, master_seed=True)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 8. 护栏非劣效
# --------------------------------------------------------------------------- #
class TestGuardrail:
    def test_clearly_non_inferior_passes(self) -> None:
        """两组退款率相同、单侧上界 0.019 < 界值 0.02 → 判定非劣效通过。"""
        result = noninferiority_binary(75, 1000, 75, 1000, margin=0.02)
        assert result.diff == pytest.approx(0.0)
        assert result.ci_one_sided_upper < 0.02
        assert result.passed is True

    def test_clearly_inferior_fails(self) -> None:
        """退款率恶化 7.5pp、界值 0.5pp → 不通过（哪怕检验本身"显著"）。"""
        result = noninferiority_binary(300, 1000, 225, 1000, margin=0.005)
        assert result.diff == pytest.approx(0.075)
        assert result.passed is False

    def test_same_data_both_verdicts(self) -> None:
        """同一组数据：界值放宽才通过 —— 证明判定由预设界值决定，不是由 p 值决定。"""
        strict = noninferiority_binary(80, 1000, 75, 1000, margin=0.005)
        loose = noninferiority_binary(80, 1000, 75, 1000, margin=0.03)
        assert strict.passed is False
        assert loose.passed is True

    def test_se_uses_unpooled_variance(self) -> None:
        """SE 必须是非合并方差；与合并方差版本对比确认真的有差别。"""
        k_t, n_t, k_c, n_c = 80, 1000, 75, 1000
        p_t, p_c = k_t / n_t, k_c / n_c
        expected = math.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
        result = noninferiority_binary(k_t, n_t, k_c, n_c, margin=0.005)
        assert result.se == pytest.approx(expected)

        pooled = (k_t + k_c) / (n_t + n_c)
        se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_t + 1 / n_c))
        assert abs(result.se - se_pooled) > 1e-9

    def test_ci_upper_formula(self) -> None:
        """上界 = diff + z_{1-α} · se，α 是单侧。"""
        result = noninferiority_binary(80, 1000, 70, 1000, margin=0.01, alpha_one_sided=0.05)
        expected = result.diff + float(norm.ppf(0.95)) * result.se
        assert result.ci_one_sided_upper == pytest.approx(expected)

    def test_metadata(self) -> None:
        result = noninferiority_binary(80, 1000, 75, 1000, margin=0.005)
        assert isinstance(result, NonInferiorityResult)
        assert result.metric == "refund_rate"
        assert result.margin == pytest.approx(0.005)
        assert result.alpha_one_sided == pytest.approx(0.05)
        assert result.method

    def test_positive_diff_means_worse(self) -> None:
        """护栏指标方向必须写死：退款率上正数 = 恶化。"""
        worse = noninferiority_binary(90, 1000, 70, 1000, margin=0.005)
        better = noninferiority_binary(70, 1000, 90, 1000, margin=0.005)
        assert worse.diff > 0 and better.diff < 0
        assert worse.passed is False

    @pytest.mark.parametrize(
        ("k_t", "n_t", "k_c", "n_c", "margin"),
        [
            (5, 0, 5, 100, 0.005),
            (5, 100, 5, 0, 0.005),
            (101, 100, 5, 100, 0.005),
            (-1, 100, 5, 100, 0.005),
            (5, 100, 5, 100, 0.0),
            (5, 100, 5, 100, -0.005),
        ],
    )
    def test_invalid_inputs(self, k_t: int, n_t: int, k_c: int, n_c: int, margin: float) -> None:
        with pytest.raises(ValueError):
            noninferiority_binary(k_t, n_t, k_c, n_c, margin=margin)

    @pytest.mark.parametrize("alpha", [0.0, 1.0])
    def test_invalid_alpha(self, alpha: float) -> None:
        with pytest.raises(ValueError):
            noninferiority_binary(5, 100, 5, 100, margin=0.005, alpha_one_sided=alpha)


# --------------------------------------------------------------------------- #
# 9. 多重比较
# --------------------------------------------------------------------------- #
#: 任务书给定的已知答案输入
KNOWN_P = [0.01, 0.04, 0.03, 0.005]


class TestMultiplicityKnownAnswers:
    def test_bonferroni_known_answer(self) -> None:
        result = bonferroni(KNOWN_P, alpha=0.05)
        assert result.adjusted_p == pytest.approx([0.04, 0.16, 0.12, 0.02])
        assert result.raw_p == pytest.approx(KNOWN_P)

    def test_holm_known_answer(self) -> None:
        """升序 0.005/0.01/0.03/0.04 → 乘 4/3/2/1 并取前缀最大：
        0.02/0.03/0.06/0.06 → 回到输入序 [0.03, 0.06, 0.06, 0.02]。"""
        result = holm(KNOWN_P, alpha=0.05)
        assert result.adjusted_p == pytest.approx([0.03, 0.06, 0.06, 0.02])
        assert result.rejected.tolist() == [True, False, False, True]

    def test_bh_known_answer(self) -> None:
        """升序乘 4/1,4/2,4/3,4/4 得 0.02/0.02/0.04/0.04，
        反向累积最小后不变 → 回到输入序 [0.02, 0.04, 0.04, 0.02]。"""
        result = benjamini_hochberg(KNOWN_P, alpha=0.05)
        assert result.adjusted_p == pytest.approx([0.02, 0.04, 0.04, 0.02])
        assert result.rejected.tolist() == [True, True, True, True]

    def test_holm_monotone_in_sorted_order(self) -> None:
        p = np.array([0.001, 0.2, 0.03, 0.5, 0.0001])
        adjusted = holm(p).adjusted_p
        order = np.argsort(p)
        assert np.all(np.diff(adjusted[order]) >= -1e-12)

    def test_holm_never_worse_than_bonferroni(self) -> None:
        """Holm 一致地不弱于 Bonferroni（同 alpha 下校正 p 值逐点 ≤）。"""
        p = np.array([0.001, 0.02, 0.04, 0.049, 0.5])
        assert np.all(holm(p).adjusted_p <= bonferroni(p).adjusted_p + 1e-12)


class TestMultiplicityProperties:
    def test_length_and_dtype(self) -> None:
        result = adjust(KNOWN_P, "holm")
        assert len(result.adjusted_p) == len(result.raw_p) == len(KNOWN_P)
        assert result.adjusted_p.shape == (4,)
        assert result.rejected.dtype == bool
        assert isinstance(result, MultiplicityResult)

    def test_order_preserved_under_permutation(self) -> None:
        """打乱输入顺序，校正后的值必须跟着原来的 p 走（不是按排序后的位置返回）。"""
        p = np.array([0.04, 0.005, 0.01, 0.03])
        perm = np.array([2, 0, 3, 1])
        for method in ("bonferroni", "holm", "bh"):
            full = adjust(p, method).adjusted_p
            shuffled = adjust(p[perm], method).adjusted_p
            assert np.allclose(shuffled, full[perm]), method

    def test_clipped_to_unit_interval(self) -> None:
        for method in ("bonferroni", "holm", "bh"):
            result = adjust([0.9, 0.8, 0.7], method)
            assert np.all(result.adjusted_p <= 1.0)
            assert np.all(result.adjusted_p >= 0.0)

    def test_single_value_unchanged_bonferroni(self) -> None:
        assert bonferroni([0.03]).adjusted_p == pytest.approx([0.03])

    def test_empty_input_returns_empty(self) -> None:
        for method in ("bonferroni", "holm", "bh"):
            result = adjust([], method)
            assert result.adjusted_p.size == 0
            assert result.rejected.size == 0
            assert result.raw_p.size == 0
            assert result.method == method

    @pytest.mark.parametrize("method", ["bonferroni", "holm", "bh"])
    def test_nan_raises(self, method: str) -> None:
        with pytest.raises(ValueError):
            adjust([0.01, float("nan")], method)

    @pytest.mark.parametrize("bad", [[-0.1, 0.2], [0.1, 1.5], [[0.1, 0.2]]])
    def test_invalid_values_raise(self, bad) -> None:
        with pytest.raises(ValueError):
            adjust(bad, "holm")

    def test_unknown_method_raises(self) -> None:
        with pytest.raises(ValueError, match="未知"):
            adjust([0.1], "sidak")

    def test_adjust_matches_direct_calls(self) -> None:
        pairs = (
            ("bonferroni", bonferroni),
            ("holm", holm),
            ("bh", benjamini_hochberg),
        )
        for method, func in pairs:
            assert np.allclose(adjust(KNOWN_P, method).adjusted_p, func(KNOWN_P).adjusted_p)

    def test_rejected_matches_alpha_rule(self) -> None:
        result = holm([0.001, 0.02, 0.2], alpha=0.05)
        assert result.rejected.tolist() == (result.adjusted_p <= 0.05).tolist()
        assert result.alpha == pytest.approx(0.05)
