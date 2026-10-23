"""四指标评估测试 —— 手工可复核的数字 + 口径红线。

为什么这些测试长这样
--------------------
方案 §2.4 主线五要求**四个指标并列**，理由是"CATE 准不代表排序好，排序好不代表
策略价值高，策略价值高不代表接近最优"。所以这里不只测"函数能跑"，
而是把下面这些**手算得出的数字**钉死：

- 常数平移 τ̂ = τ + 5：RMSE = 5、bias = 5，但排序指标**全部为 1**；
- 已知小数组的 RMSE = sqrt(1/3)、R² = 0.5、corr = 3/sqrt(28/3)；
- 真实 top-1 被换到第二位：RMSE 只有 0.5（最大 τ 的 0.8%），
  R² 还有 0.992，但 top-1 重合度 = 0、regret > 0；
- 上例同时构成"无单一排序"的反证：RMSE 说 C 比 B 好，top-1 重合度说 B 比 C 好
  —— 四个指标**不存在可替代关系**（见 ``TestFourMetricsAreNotInterchangeable``）。

另外守住两条口径：**Π 已含券成本，V(π) 不再二次扣减（R3）**；
**真值为常数时相关/R² 是 0/0，必须返回 nan，不许伪造 1.0**。

测试里的随机性一律走 ``causal_growth.rng.child_rng``（AGENTS.md §3.3），
不用裸 ``np.random.*``。
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import causal_growth.evaluation as eval_pkg
from causal_growth.evaluation.metrics import (
    CALIBRATION_COLUMNS,
    CateAccuracy,
    RankingMetrics,
    bootstrap_se,
    calibration_table,
    cate_accuracy,
    nonneg_policy,
    oracle_policy,
    policy_value,
    policy_value_observed,
    ranking_metrics,
    regret,
    top_k_policy,
)
from causal_growth.rng import child_rng

#: 换头场景的样本量：足够大，使"换掉头部两人"对 RMSE 的稀释效果明显
_SWAP_N = 200


@pytest.fixture(scope="module")
def randomized_sample() -> dict[str, np.ndarray]:
    """一次固定种子的"随机实验 + 已知潜在结果"小仿真。

    用来验证 :func:`policy_value_observed`（只有观测结果的 IPTW 估计）
    能否逼近 :func:`policy_value`（仿真里可算的真值）。
    随机流固定，所以数字是确定的，不是"偶尔能过"。
    """
    n = 20_000
    rng = child_rng(master_seed=20240101, stream="test.metrics.pv_observed", index=0)
    pi0 = rng.normal(1.0, 3.0, size=n)
    tau = rng.normal(0.5, 2.0, size=n)
    pi1 = pi0 + tau
    treatment = rng.binomial(1, 0.5, size=n)
    y_obs = np.where(treatment == 1, pi1, pi0)
    policy_mix = rng.binomial(1, 0.5, size=n)
    propensity = rng.uniform(0.3, 0.7, size=n)
    treatment_het = rng.binomial(1, propensity)
    y_obs_het = np.where(treatment_het == 1, pi1, pi0)
    return {
        "pi0": pi0,
        "pi1": pi1,
        "tau": tau,
        "treatment": treatment,
        "y_obs": y_obs,
        "policy_mix": policy_mix,
        "propensity": propensity,
        "treatment_het": treatment_het,
        "y_obs_het": y_obs_het,
    }


def _swap_head_sample() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """构造"头部两人被换位"的样本：真值 top-1 = 用户 0，估计 top-1 = 用户 1。

    真值：60, 55, 0.5, 0.5, ...
    估计：55, 60, 0.5, 0.5, ...
    这样 RMSE 只被两个人稀释到 0.5，但**策略选谁完全错了**。
    """
    tau_true = np.concatenate([[60.0, 55.0], np.full(_SWAP_N - 2, 0.5)])
    tau_hat = np.concatenate([[55.0, 60.0], np.full(_SWAP_N - 2, 0.5)])
    pi0 = np.zeros(_SWAP_N)
    pi1 = tau_true.copy()  # Π(0)=0，于是 V(π) = mean(π·τ)，便于手算
    return tau_true, tau_hat, pi1, pi0


# --------------------------------------------------------------------------- #
# 一、CATE 精度
# --------------------------------------------------------------------------- #
class TestCateAccuracy:
    """RMSE / MAE / bias / 相关 / R² 五个字段的手算对照。"""

    def test_perfect_prediction_answers_all_zero_and_one(self) -> None:
        """τ̂ = τ 时五个字段的基准值：RMSE=MAE=bias=0，corr=R²=1。"""
        tau = np.array([0.01, 0.05, 0.20, -0.03])
        acc = cate_accuracy(tau, tau)
        assert acc.rmse == 0.0
        assert acc.mae == 0.0
        assert acc.bias == 0.0
        assert acc.correlation == pytest.approx(1.0)
        assert acc.r2 == pytest.approx(1.0)

    def test_hand_computed_small_array(self) -> None:
        """τ_true=[1,2,3]、τ̂=[1,2,4]：RMSE=sqrt(1/3)、MAE=bias=1/3、R²=0.5。

        手算：
        - 误差 = [0, 0, 1] → SSE = 1，RMSE = sqrt(1/3)，MAE = 1/3，bias = 1/3
        - SST = (1−2)² + (2−2)² + (3−2)² = 2 → R² = 1 − 1/2 = 0.5
        - corr = 3 / sqrt((14/3)·2) = 0.981980506…
        """
        acc = cate_accuracy([1, 2, 4], [1, 2, 3])
        assert acc.rmse == pytest.approx(math.sqrt(1.0 / 3.0))
        assert acc.mae == pytest.approx(1.0 / 3.0)
        assert acc.bias == pytest.approx(1.0 / 3.0)
        assert acc.r2 == pytest.approx(0.5)
        assert acc.correlation == pytest.approx(3.0 / math.sqrt(14.0 / 3.0 * 2.0))

    def test_constant_shift_rmse_5_bias_5(self) -> None:
        """常数平移 τ̂ = τ + 5：RMSE = 5、bias = 5、MAE = 5、corr = 1。

        R² = 1 − 75/2 = −36.5，**远小于 0**：平移后的预测不如直接猜均值。
        这正是"RMSE 差 ≠ 排序差"的那条（排序部分见
        ``TestRankingMetrics.test_constant_shift_keeps_ranking_perfect``）。
        """
        acc = cate_accuracy([6.0, 7.0, 8.0], [1.0, 2.0, 3.0])
        assert acc.rmse == pytest.approx(5.0)
        assert acc.bias == pytest.approx(5.0)
        assert acc.mae == pytest.approx(5.0)
        assert acc.correlation == pytest.approx(1.0)
        # 浮点误差可能算出 1+2e−16；相关系数按定义不得越界
        assert acc.correlation <= 1.0
        assert acc.r2 == pytest.approx(-36.5)

    def test_reversed_order_gives_negative_correlation(self) -> None:
        """完全反向：corr = −1，R² = 1 − 56/2 = −27（比猜均值差得多）。"""
        acc = cate_accuracy([-1.0, -2.0, -3.0], [1.0, 2.0, 3.0])
        assert acc.correlation == pytest.approx(-1.0)
        assert acc.bias == pytest.approx(-4.0)
        assert acc.r2 == pytest.approx(-27.0)

    def test_constant_truth_returns_nan_not_one(self) -> None:
        """真值恒定（L0 层 τ 恒为 0.05）：corr 与 R² 是 0/0，必须是 nan。

        若这里返回 1.0，报告就会写"CATE 完全准确"，而真相是
        "真值没有变异，排序与解释力的讨论本身无意义"。宁可见 nan。
        """
        acc = cate_accuracy([0.05, 0.05, 0.05], [0.05, 0.05, 0.05])
        assert acc.rmse == 0.0
        assert np.isnan(acc.correlation)
        assert np.isnan(acc.r2)

    def test_constant_hat_with_varying_truth(self) -> None:
        """τ̂ 恒定而真值有变异：corr = nan，但 R² 仍可算（SST > 0）。"""
        acc = cate_accuracy([0.0] * 4, [1.0, 2.0, 3.0, 4.0])
        assert np.isnan(acc.correlation)
        assert acc.bias == pytest.approx(-2.5)
        assert acc.r2 == pytest.approx(-5.0)  # 1 − SSE/SST = 1 − 30/5

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="长度不一致"):
            cate_accuracy([1.0, 2.0], [1.0, 2.0, 3.0])

    @pytest.mark.parametrize(
        "bad",
        [
            [1.0, float("nan")],
            [1.0, float("inf")],
            [1.0, float("-inf")],
        ],
    )
    def test_non_finite_raises(self, bad: list[float]) -> None:
        """NaN/Inf 一律抛错，不做静默填充（AGENTS.md §3.6 失败要响）。"""
        with pytest.raises(ValueError, match="NaN/Inf"):
            cate_accuracy(bad, [1.0, 2.0])

    @pytest.mark.parametrize("bad", [np.zeros((2, 2)), [], [[1.0, 2.0]]])
    def test_bad_shape_raises(self, bad: object) -> None:
        with pytest.raises(ValueError):
            cate_accuracy(bad, [1.0])

    def test_as_dict_names_are_report_ready(self) -> None:
        acc = cate_accuracy([1, 2, 3], [1, 2, 3])
        assert set(acc.as_dict()) == {"cate_rmse", "cate_mae", "cate_bias", "cate_corr", "cate_r2"}


# --------------------------------------------------------------------------- #
# 二、排序
# --------------------------------------------------------------------------- #
class TestRankingMetrics:
    """top-k 重合度与秩相关：手算对照 + 并列 tie-break + k 的口径。"""

    def test_perfect_ranking(self) -> None:
        """τ̂ 与 τ 完全单调一致：三个排序指标都为 1。"""
        tau_true = np.array([0.01, 0.05, 0.20, -0.03, 0.10])
        rk = ranking_metrics(tau_true, tau_true)
        assert rk.top_overlap == 1.0
        assert rk.spearman == pytest.approx(1.0)
        assert rk.kendall == pytest.approx(1.0)
        assert rk.k == 1  # n=5、top_share=0.2 → max(1, round(1.0)) = 1
        assert rk.top_share == pytest.approx(0.20)

    def test_constant_shift_keeps_ranking_perfect(self) -> None:
        """τ̂ = τ + 5：RMSE = 5，但排序指标**依然全 1**。

        这条是"RMSE 差 ≠ 排序差"的核心证据（配套断言在 TestCateAccuracy）。
        排序只关心顺序，不理尺度；所以"尺度偏了"不能用"排序变差"来描述。
        """
        tau_true = np.array([1.0, 2.0, 3.0, 4.0])
        rk = ranking_metrics(tau_true + 5.0, tau_true, top_share=0.5)
        assert rk.top_overlap == 1.0
        assert rk.spearman == pytest.approx(1.0)
        assert rk.kendall == pytest.approx(1.0)
        assert rk.k == 2  # round(4 × 0.5) = 2

    def test_hand_computed_top_overlap_is_zero(self) -> None:
        """τ_true=[5,4,3,2,1]、τ̂=[1,2,3,4,5]、top_share=0.2 → k=1、overlap=0。

        真实 top-1 = 索引 0（τ=5），估计 top-1 = 索引 4（τ̂=5，而真值是 1）。
        Spearman 与 Kendall 同时为 −1，三件指标一起指向"排序完全反了"。
        """
        rk = ranking_metrics([1, 2, 3, 4, 5], [5, 4, 3, 2, 1], top_share=0.2)
        assert rk.k == 1
        assert rk.top_overlap == 0.0
        assert rk.spearman == pytest.approx(-1.0)
        assert rk.kendall == pytest.approx(-1.0)

    @pytest.mark.parametrize(
        ("n", "share", "expected_k"),
        [
            (3, 0.20, 1),  # round(0.6) = 1
            (4, 0.20, 1),  # round(0.8) = 1
            (10, 0.20, 2),
            (15, 0.20, 3),
            (100, 0.20, 20),
            (5, 0.50, 2),  # round(2.5) = 2（banker's rounding，取偶）
            (7, 0.50, 4),  # round(3.5) = 4
        ],
    )
    def test_k_formula(self, n: int, share: float, expected_k: int) -> None:
        """k = max(1, round(n·top_share))，且并列时按索引升序 tie-break。"""
        tau_hat = np.arange(n, dtype=float)
        rk = ranking_metrics(tau_hat, tau_hat, top_share=share)
        assert rk.k == expected_k

    def test_tie_break_prefers_lower_index(self) -> None:
        """全部并列时按索引升序取人：同一份输入两次运行结果必须一致。"""
        tau_hat = np.zeros(4)
        assert top_k_policy(tau_hat, top_share=0.5).tolist() == [1, 1, 0, 0]
        assert top_k_policy(tau_hat, top_share=0.5).tolist() == [1, 1, 0, 0]
        rk = ranking_metrics(tau_hat, [1, 2, 3, 4], top_share=0.5)
        # 估计 top-2 = {0, 1}，真实 top-2 = {2, 3} → 交集为空
        assert rk.top_overlap == 0.0
        assert np.isnan(rk.spearman)
        assert np.isnan(rk.kendall)

    def test_spearman_and_kendall_match_scipy(self) -> None:
        """秩相关必须来自 scipy.stats（口径：与教科书实现逐位对得上）。"""
        rng = child_rng(master_seed=20240101, stream="test.metrics.rank", index=0)
        tau_hat = rng.normal(size=300)
        tau_true = 0.6 * tau_hat + rng.normal(size=300)
        rk = ranking_metrics(tau_hat, tau_true)
        assert rk.spearman == pytest.approx(float(stats.spearmanr(tau_hat, tau_true).statistic))
        assert rk.kendall == pytest.approx(
            float(stats.kendalltau(tau_hat, tau_true, variant="b").statistic)
        )

    @pytest.mark.parametrize("bad_share", [0.0, 1.0, -0.1, 1.5, 2.0])
    def test_top_share_out_of_range_raises(self, bad_share: float) -> None:
        with pytest.raises(ValueError, match="top_share"):
            ranking_metrics([1.0, 2.0], [1.0, 2.0], top_share=bad_share)

    def test_top_share_wrong_type_raises(self) -> None:
        with pytest.raises(ValueError, match="top_share"):
            ranking_metrics([1.0, 2.0], [1.0, 2.0], top_share="0.2")  # type: ignore[arg-type]

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN/Inf"):
            ranking_metrics([1.0, float("nan")], [1.0, 2.0])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="长度不一致"):
            ranking_metrics([1.0, 2.0, 3.0], [1.0, 2.0])

    def test_as_dict_echoes_calibration_of_k(self) -> None:
        rk = ranking_metrics(np.arange(10.0), np.arange(10.0))
        payload = rk.as_dict()
        assert payload["rank_k"] == 2
        assert payload["rank_top_share"] == pytest.approx(0.20)


# --------------------------------------------------------------------------- #
# 三、校准表
# --------------------------------------------------------------------------- #
class TestCalibrationTable:
    """分位数分箱、列名固定、``diff == mean_pred − mean_true`` 恒等式。"""

    def test_columns_and_diff_identity(self) -> None:
        """列必须恰好是 CALIBRATION_COLUMNS，且 diff 就是两者之差。"""
        rng = child_rng(master_seed=20240101, stream="test.metrics.calib", index=0)
        tau_hat = rng.normal(size=300)
        tau_true = tau_hat + rng.normal(scale=0.3, size=300)
        table = calibration_table(tau_hat, tau_true, n_bins=10)
        assert tuple(table.columns) == CALIBRATION_COLUMNS
        assert len(table) == 10
        assert np.allclose(
            table["diff"].to_numpy(),
            (table["mean_pred"] - table["mean_true"]).to_numpy(),
            rtol=0.0,
            atol=0.0,
        )

    def test_row_count_equals_n_bins_when_no_ties(self) -> None:
        table = calibration_table(np.arange(100.0), np.arange(100.0) * 2.0, n_bins=10)
        assert len(table) == 10
        assert int(table["n"].sum()) == 100

    def test_ties_reduce_bin_count(self) -> None:
        """90% 的 τ̂ 相同 → 分位数边界重复，去重后箱数 < n_bins。"""
        tied = np.concatenate([np.zeros(90), np.linspace(1.0, 10.0, 10)])
        table = calibration_table(tied, tied, n_bins=10)
        assert 1 < len(table) < 10
        assert int(table["n"].sum()) == tied.size

    def test_all_equal_gives_single_bin(self) -> None:
        table = calibration_table(np.zeros(20), np.arange(20.0), n_bins=10)
        assert len(table) == 1
        assert int(table["n"].iloc[0]) == 20
        assert table["mean_pred"].iloc[0] == pytest.approx(0.0)

    def test_monotone_prediction_yields_increasing_mean_pred(self) -> None:
        """完美排序时，箱内 mean_pred 逐箱递增（分位数分箱的方向性检查）。"""
        tau = np.linspace(-1.0, 1.0, 200)
        table = calibration_table(tau, tau, n_bins=8)
        preds = table["mean_pred"].to_numpy()
        assert np.all(np.diff(preds) > 0)
        # 真值也单调，所以每箱 diff 应在 0 附近（是同一条序列）
        assert np.allclose(table["diff"].to_numpy(), 0.0)

    @pytest.mark.parametrize("bad_bins", [0, -3, 2.5, True])
    def test_invalid_n_bins_raises(self, bad_bins: object) -> None:
        with pytest.raises(ValueError, match="n_bins"):
            calibration_table([1.0, 2.0], [1.0, 2.0], n_bins=bad_bins)  # type: ignore[arg-type]

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN/Inf"):
            calibration_table([1.0, float("nan")], [1.0, 2.0])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="长度不一致"):
            calibration_table([1.0, 2.0], [1.0, 2.0, 3.0])


# --------------------------------------------------------------------------- #
# 四、策略价值（仿真真值）
# --------------------------------------------------------------------------- #
class TestPolicyValue:
    """V(π) 的加权平均口径 + R3（券成本只扣一次）。"""

    def test_hand_computed_policy_value(self) -> None:
        """pi1=[10,20]、pi0=[0,5]、policy=[1,0] → (10 + 5)/2 = 7.5。"""
        value = policy_value([1, 0], pi1=[10.0, 20.0], pi0=[0.0, 5.0])
        assert value == pytest.approx(7.5)

    def test_all_zero_policy_is_baseline_and_all_one_is_treated(self) -> None:
        pi1, pi0 = np.array([10.0, 20.0, 30.0]), np.array([0.0, 5.0, -1.0])
        assert policy_value(np.zeros(3), pi1=pi1, pi0=pi0) == pytest.approx(np.mean(pi0))
        assert policy_value(np.ones(3), pi1=pi1, pi0=pi0) == pytest.approx(np.mean(pi1))

    def test_cost_inside_pi_is_deducted_exactly_once(self) -> None:
        """R3：券成本已在 Π^net 里，V(π) 不再二次扣减。

        把同一笔成本 c=3 从 Π(1)、Π(0) 各扣一次（模拟"Π 已含券成本"），
        V(π) 必须恰好下降 3，而不是 6。下降 6 就是重复扣减。
        """
        before = policy_value([1, 0], pi1=[10.0, 20.0], pi0=[0.0, 5.0])
        after = policy_value([1, 0], pi1=[7.0, 17.0], pi0=[-3.0, 2.0])
        assert before == pytest.approx(7.5)
        assert after == pytest.approx(4.5)
        assert before - after == pytest.approx(3.0)

    @pytest.mark.parametrize("bad", [[0, 2], [-1, 0], [0.5, 1], [0, 0.9]])
    def test_non_binary_policy_raises(self, bad: list[float]) -> None:
        with pytest.raises(ValueError, match="0/1"):
            policy_value(bad, pi1=[1.0, 2.0], pi0=[0.0, 0.0])

    def test_bool_policy_is_accepted(self) -> None:
        assert policy_value([True, False], pi1=[10.0, 20.0], pi0=[0.0, 5.0]) == pytest.approx(7.5)

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="长度不一致"):
            policy_value([1, 0, 1], pi1=[1.0, 2.0], pi0=[0.0, 0.0])

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN/Inf"):
            policy_value([1, 0], pi1=[1.0, float("nan")], pi0=[0.0, 0.0])


# --------------------------------------------------------------------------- #
# 五、策略价值（只有观测数据时的 IPTW 估计）
# --------------------------------------------------------------------------- #
class TestPolicyValueObserved:
    """IPTW 估计量：确定性等式 + 随机化下的量级逼近。"""

    def test_all_one_policy_equals_treated_mean_exactly(self, randomized_sample) -> None:
        """全量发券 → V̂ = mean(Y | T=1)（IPTW 权重恰为 n/n₁ 时的恒等式）。"""
        s = randomized_sample
        policy = np.ones_like(s["treatment"])
        est = policy_value_observed(policy, y_obs=s["y_obs"], treatment=s["treatment"])
        assert est == pytest.approx(float(s["y_obs"][s["treatment"] == 1].mean()))

    def test_all_zero_policy_equals_control_mean_exactly(self, randomized_sample) -> None:
        s = randomized_sample
        policy = np.zeros_like(s["treatment"])
        est = policy_value_observed(policy, y_obs=s["y_obs"], treatment=s["treatment"])
        assert est == pytest.approx(float(s["y_obs"][s["treatment"] == 0].mean()))

    def test_randomized_all_one_close_to_true_value(self, randomized_sample) -> None:
        """50/50 随机分配 + 全量发券：估计值应接近真值 mean(Π(1))。

        n = 20000，抽样误差约 0.02 量级；容差 0.12 ≈ 5 个标准误，
        足以容纳抽样波动，又不会放过"公式写错"（错公式的偏差 > 1）。
        """
        s = randomized_sample
        policy = np.ones_like(s["treatment"])
        est = policy_value_observed(policy, y_obs=s["y_obs"], treatment=s["treatment"])
        true = policy_value(policy, pi1=s["pi1"], pi0=s["pi0"])
        assert est == pytest.approx(true, abs=0.12)

    def test_randomized_mixed_policy_close_to_true_value(self, randomized_sample) -> None:
        """50% 定向的混合策略：两条臂都参与加权，估计值仍逼近真值。"""
        s = randomized_sample
        est = policy_value_observed(
            s["policy_mix"], y_obs=s["y_obs"], treatment=s["treatment"]
        )
        true = policy_value(s["policy_mix"], pi1=s["pi1"], pi0=s["pi0"])
        assert est == pytest.approx(true, abs=0.12)

    def test_constant_propensity_equals_default(self, randomized_sample) -> None:
        """显式传入常数倾向得分 mean(T) 与默认行为逐位相同（同一估计量）。"""
        s = randomized_sample
        n = s["treatment"].size
        default = policy_value_observed(
            s["policy_mix"], y_obs=s["y_obs"], treatment=s["treatment"]
        )
        explicit = policy_value_observed(
            s["policy_mix"],
            y_obs=s["y_obs"],
            treatment=s["treatment"],
            propensity=np.full(n, float(s["treatment"].mean())),
        )
        assert default == explicit

    def test_heterogeneous_propensity_close_to_true_value(self, randomized_sample) -> None:
        """倾向得分异质（e∈[0.3,0.7]）且已知时，IPW 加权仍能还原真值。"""
        s = randomized_sample
        est = policy_value_observed(
            s["policy_mix"],
            y_obs=s["y_obs_het"],
            treatment=s["treatment_het"],
            propensity=s["propensity"],
        )
        true = policy_value(s["policy_mix"], pi1=s["pi1"], pi0=s["pi0"])
        assert est == pytest.approx(true, abs=0.20)

    def test_single_arm_raises(self) -> None:
        """全 0 或全 1 的分配：反事实一侧没有观测，重叠性不成立。"""
        with pytest.raises(ValueError, match="重叠性"):
            policy_value_observed([1, 1], y_obs=[1.0, 2.0], treatment=[1, 1])
        with pytest.raises(ValueError, match="重叠性"):
            policy_value_observed([1, 1], y_obs=[1.0, 2.0], treatment=[0, 0])

    @pytest.mark.parametrize("bad_propensity", [[0.0, 0.5], [0.5, 1.0], [-0.1, 0.5]])
    def test_propensity_out_of_range_raises(self, bad_propensity: list[float]) -> None:
        with pytest.raises(ValueError, match="propensity"):
            policy_value_observed(
                [1, 0],
                y_obs=[1.0, 2.0],
                treatment=[1, 0],
                propensity=bad_propensity,
            )

    def test_non_binary_policy_raises(self) -> None:
        with pytest.raises(ValueError, match="0/1"):
            policy_value_observed([0, 2], y_obs=[1.0, 2.0], treatment=[1, 0])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="长度不一致"):
            policy_value_observed([1, 0, 1], y_obs=[1.0, 2.0], treatment=[1, 0])

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN/Inf"):
            policy_value_observed([1, 0], y_obs=[1.0, float("nan")], treatment=[1, 0])


# --------------------------------------------------------------------------- #
# 六、策略构造
# --------------------------------------------------------------------------- #
class TestPolicyConstructors:
    """oracle / top-k / nonneg 三种策略向量的定义与可复现性。"""

    def test_oracle_top_share_picks_largest(self) -> None:
        """τ=[5,4,3,2,1]、top_share=0.4 → k=2 → 索引 0、1。"""
        policy = oracle_policy([5.0, 4.0, 3.0, 2.0, 1.0], top_share=0.4)
        assert policy.tolist() == [1, 1, 0, 0, 0]

    def test_oracle_none_picks_positive_effect_only(self) -> None:
        """top_share=None → 选 τ > 0 的全部（τ=0 不选，因为不赚钱）。"""
        policy = oracle_policy([-1.0, 0.0, 2.0, 3.0])
        assert policy.tolist() == [0, 0, 1, 1]

    def test_top_k_policy_equals_oracle_when_estimate_is_truth(self) -> None:
        """τ̂ = τ 时，估计的 top-k 策略必须与真值最优策略**逐位相同**（regret=0 的前提）。"""
        tau = np.array([0.4, -0.2, 0.9, 0.1, 0.7, 0.0])
        assert np.array_equal(
            top_k_policy(tau, top_share=0.5), oracle_policy(tau, top_share=0.5)
        )

    def test_top_k_policy_has_exactly_k_selected(self) -> None:
        tau = np.arange(100.0)
        policy = top_k_policy(tau, top_share=0.20)
        assert int(policy.sum()) == 20
        assert policy.max() == 1 and policy.min() == 0

    def test_nonneg_policy_follows_sign(self) -> None:
        """按 τ̂ > 0 发券；τ̂ = 0 不发（不多花一分钱）。"""
        assert nonneg_policy([-1.0, 0.0, 0.5, 2.0]).tolist() == [0, 0, 1, 1]

    @pytest.mark.parametrize("bad_share", [0.0, 1.0, -0.5])
    def test_invalid_top_share_raises(self, bad_share: float) -> None:
        with pytest.raises(ValueError, match="top_share"):
            oracle_policy([1.0, 2.0], top_share=bad_share)
        with pytest.raises(ValueError, match="top_share"):
            top_k_policy([1.0, 2.0], top_share=bad_share)

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN/Inf"):
            oracle_policy([1.0, float("nan")])
        with pytest.raises(ValueError, match="NaN/Inf"):
            nonneg_policy([1.0, float("nan")])


# --------------------------------------------------------------------------- #
# 七、Regret
# --------------------------------------------------------------------------- #
class TestRegret:
    """R(π) = V(π*) − V(π)：自比为 0、手算为正、数值误差 clamp 到 0。"""

    @pytest.fixture()
    def six_users(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """τ=[10,9,8,1,0,−1]，Π(0)=0 → V(π) = mean(π·τ)，可以手算。"""
        tau = np.array([10.0, 9.0, 8.0, 1.0, 0.0, -1.0])
        pi0 = np.zeros(6)
        return tau, tau.copy(), pi0

    def test_regret_of_oracle_against_itself_is_zero(self, six_users) -> None:
        tau, pi1, pi0 = six_users
        star = oracle_policy(tau, top_share=1.0 / 3.0)  # k = 2 → 用户 0、1
        assert regret(star, star, pi1=pi1, pi0=pi0) == 0.0

    def test_hand_computed_regret(self, six_users) -> None:
        """π 选了 {10, 1}，π* 选了 {10, 9}：
        V(π) = 11/6、V(π*) = 19/6、R = 8/6 = 1.3333…。
        """
        tau, pi1, pi0 = six_users
        star = oracle_policy(tau, top_share=1.0 / 3.0)
        policy = np.array([1, 0, 0, 1, 0, 0])
        assert policy_value(policy, pi1=pi1, pi0=pi0) == pytest.approx(11.0 / 6.0)
        assert policy_value(star, pi1=pi1, pi0=pi0) == pytest.approx(19.0 / 6.0)
        assert regret(policy, star, pi1=pi1, pi0=pi0) == pytest.approx(8.0 / 6.0)

    def test_negative_regret_is_clamped_to_zero(self, six_users) -> None:
        """π 优于 π* 时（π* 本身不是真值最优）结果 clamp 到 0，绝不返回负数。"""
        tau, pi1, pi0 = six_users
        star = oracle_policy(tau, top_share=1.0 / 3.0)  # 选 {0, 1}，V* = 19/6
        weak_star = np.array([1, 0, 0, 0, 0, 0])  # 只选用户 0，V = 10/6
        # V(star) − V(weak_star) < 0 → 必须 clamp 到 0，而不是报 −0.5
        assert regret(star, weak_star, pi1=pi1, pi0=pi0) == 0.0
        # 自己对自己也必须严格为 0（不是 −0.0 之类的浮点残渣）
        assert regret(star, star, pi1=pi1, pi0=pi0) == 0.0

    def test_regret_invariant_to_baseline_shift(self, six_users) -> None:
        """口径：V(π) 加一个所有人相同的基线常数，regret 不变。

        这条说明"绝对水平口径"与方案 §2.3.4 的"增量口径 E[πτ]"
        只在水平上差常数 E[Π(0)]，**regret 完全一致**，可跨实验比较。
        """
        tau, pi1, pi0 = six_users
        star = oracle_policy(tau, top_share=1.0 / 3.0)
        policy = np.array([1, 0, 0, 1, 0, 0])
        base = regret(policy, star, pi1=pi1, pi0=pi0)
        shifted = regret(policy, star, pi1=pi1 + 7.0, pi0=pi0 + 7.0)
        assert base == pytest.approx(shifted)

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="长度不一致"):
            regret([1, 0], [1, 0, 1], pi1=[1.0, 2.0], pi0=[0.0, 0.0])

    def test_non_binary_policy_raises(self) -> None:
        with pytest.raises(ValueError, match="0/1"):
            regret([1, 2], [1, 0], pi1=[1.0, 2.0], pi0=[0.0, 0.0])


# --------------------------------------------------------------------------- #
# 八、自助法标准误
# --------------------------------------------------------------------------- #
class TestBootstrapSe:
    """可复现性 + 与解析标准误的量级一致 + 参数校验。"""

    def test_same_seed_is_bitwise_identical(self) -> None:
        """同一 (master_seed, stream, index) → 结果必须**逐位相同**。"""
        rng = child_rng(master_seed=20240101, stream="test.metrics.boot", index=0)
        values = rng.normal(2.0, 5.0, size=300)
        first = bootstrap_se(values, n_boot=200, master_seed=20240101)
        second = bootstrap_se(values, n_boot=200, master_seed=20240101)
        assert first == second
        third = bootstrap_se(values, n_boot=200, master_seed=20240101, index=1)
        assert third != first  # 换 index → 换随机流

    def test_different_stream_changes_result(self) -> None:
        rng = child_rng(master_seed=20240101, stream="test.metrics.boot2", index=0)
        values = rng.normal(size=200)
        a = bootstrap_se(values, n_boot=100, master_seed=20240101, stream="metrics.a")
        b = bootstrap_se(values, n_boot=100, master_seed=20240101, stream="metrics.b")
        assert a != b

    def test_mean_se_is_close_to_analytic(self) -> None:
        """均值的自助标准误应接近解析解 sd/sqrt(n)（同量级，容差 15%）。"""
        rng = child_rng(master_seed=20240101, stream="test.metrics.boot3", index=0)
        values = rng.uniform(0.0, 1.0, size=400)
        se = bootstrap_se(values, n_boot=400, master_seed=20240101)
        analytic = float(np.std(values, ddof=1) / np.sqrt(values.size))
        assert se == pytest.approx(analytic, rel=0.15)

    def test_median_statistic_runs_and_is_positive(self) -> None:
        rng = child_rng(master_seed=20240101, stream="test.metrics.boot4", index=0)
        values = rng.normal(0.0, 3.0, size=200)
        se_mean = bootstrap_se(values, n_boot=200, master_seed=20240101)
        se_median = bootstrap_se(values, n_boot=200, statistic="median", master_seed=20240101)
        # 正态下中位数的标准误约为均值的 1.25 倍；只断言"同量级"，不拟合具体倍数
        assert se_median > 0.0
        assert 0.5 < se_median / se_mean < 2.5

    def test_unknown_statistic_raises(self) -> None:
        with pytest.raises(ValueError, match="statistic"):
            bad_stat = "median_abs"  # type: ignore[var-annotated]
            bootstrap_se([1.0, 2.0, 3.0], statistic=bad_stat, master_seed=1)

    @pytest.mark.parametrize("bad_n_boot", [0, 1, -5, 2.5])
    def test_invalid_n_boot_raises(self, bad_n_boot: object) -> None:
        with pytest.raises(ValueError, match="n_boot"):
            bootstrap_se([1.0, 2.0, 3.0], n_boot=bad_n_boot, master_seed=1)

    def test_single_observation_raises(self) -> None:
        with pytest.raises(ValueError, match="至少需要 2 个观测"):
            bootstrap_se([1.0], master_seed=1)

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN/Inf"):
            bootstrap_se([1.0, float("nan")], master_seed=1)

    def test_master_seed_is_required(self) -> None:
        """禁止隐式随机：不给种子必须报错，不能悄悄用全局随机状态。"""
        with pytest.raises(TypeError):
            bootstrap_se([1.0, 2.0, 3.0])  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# 九、四个指标不可互相替代（方案 §2.4 主线五的核心主张）
# --------------------------------------------------------------------------- #
class TestFourMetricsAreNotInterchangeable:
    """用同一份数据证明四指标**不存在总序**——所以只能并列报告。

    ``_swap_head_sample()`` 的三份估计：

    | 估计 | RMSE | top-1 重合度 | regret |
    |---|---|---|---|
    | A = τ（完美） | 0 | 1 | 0 |
    | B = τ + 5（尺度偏） | 5 | 1 | 0 |
    | C = 换头（顺序错） | 0.5 | 0 | > 0 |

    RMSE 说 C(0.5) 比 B(5) 好，top-1 重合度说 B(1) 比 C(0) 好 —— **两个指标给出
    相反结论**。任何"综合评分"都会把这个矛盾掩盖掉。
    """

    def test_big_rmse_with_perfect_ranking(self) -> None:
        """τ̂ = τ + 5：RMSE = 5，排序指标仍全为 1（需求第 2 条的下半截）。"""
        tau_true, _, _, _ = _swap_head_sample()
        acc = cate_accuracy(tau_true + 5.0, tau_true)
        rk = ranking_metrics(tau_true + 5.0, tau_true, top_share=0.005)
        assert acc.rmse == pytest.approx(5.0)
        assert rk.top_overlap == 1.0
        assert rk.spearman == pytest.approx(1.0)
        assert rk.k == 1

    def test_tiny_relative_rmse_but_wrong_top_one(self) -> None:
        """换掉 top-1：RMSE 只有最大值 τ 的 0.83%、R² 还有 0.992，但 top-1 重合度 = 0。

        这是"RMSE 好 ≠ 排序好"的极端版本：RMSE 被 n=200 稀释，
        而策略只买 1 个人——稀释掉的正是决策最在乎的那部分。
        """
        tau_true, tau_hat, pi1, pi0 = _swap_head_sample()
        acc = cate_accuracy(tau_hat, tau_true)
        rk = ranking_metrics(tau_hat, tau_true, top_share=0.005)
        assert acc.rmse == pytest.approx(0.5)
        assert acc.rmse / tau_true.max() < 0.01  # 不到最大 τ 的 1%
        assert acc.r2 == pytest.approx(0.9922426739813079)
        assert rk.top_overlap == 0.0  # 但 top-1 完全选错
        assert rk.spearman > 0.999  # 秩相关几乎看不出问题
        policy = top_k_policy(tau_hat, top_share=0.005)
        star = oracle_policy(tau_true, top_share=0.005)
        loss = regret(policy, star, pi1=pi1, pi0=pi0)
        assert loss == pytest.approx(0.025)
        # 相对损失：V* = 60/200 = 0.3，损失 0.025 是上界的 8.3%
        assert loss / policy_value(star, pi1=pi1, pi0=pi0) > 0.08

    def test_high_policy_value_still_has_positive_regret(self) -> None:
        """V(π) = 1.83 > 0 看起来"赚了"，但距最优还差 1.33（V* 的 42%）。

        策略价值高 ≠ 接近最优。只有 regret 能回答"还能多赚多少"。
        """
        tau = np.array([10.0, 9.0, 8.0, 1.0, 0.0, -1.0])
        pi1, pi0 = tau.copy(), np.zeros(6)
        star = oracle_policy(tau, top_share=1.0 / 3.0)
        policy = np.array([1, 0, 0, 1, 0, 0])
        value = policy_value(policy, pi1=pi1, pi0=pi0)
        best = policy_value(star, pi1=pi1, pi0=pi0)
        assert value > 0.0
        assert regret(policy, star, pi1=pi1, pi0=pi0) == pytest.approx(best - value)
        assert regret(policy, star, pi1=pi1, pi0=pi0) / best > 0.40

    def test_rmse_and_top_overlap_disagree_on_which_estimate_is_better(self) -> None:
        """同一份数据，两份估计：RMSE 与 top-1 重合度给出**相反**的优劣判断。

        B（尺度平移）: RMSE 5.0，top-1 重合度 1.0
        C（换头）    : RMSE 0.5，top-1 重合度 0.0
        若把四指标压成一个数，这个矛盾被平均掉；并列报告才能同时看到两件事。
        """
        tau_true, tau_hat, pi1, pi0 = _swap_head_sample()
        shifted = tau_true + 5.0
        rmse_b = cate_accuracy(shifted, tau_true).rmse
        rmse_c = cate_accuracy(tau_hat, tau_true).rmse
        overlap_b = ranking_metrics(shifted, tau_true, top_share=0.005).top_overlap
        overlap_c = ranking_metrics(tau_hat, tau_true, top_share=0.005).top_overlap
        assert rmse_c < rmse_b  # RMSE 认为 C 更好
        assert overlap_b > overlap_c  # top-k 重合度认为 B 更好
        # regret 站 B 这边：B 完美选中真值最优，C 损失真金白银
        star = oracle_policy(tau_true, top_share=0.005)
        regret_b = regret(top_k_policy(shifted, top_share=0.005), star, pi1=pi1, pi0=pi0)
        regret_c = regret(top_k_policy(tau_hat, top_share=0.005), star, pi1=pi1, pi0=pi0)
        assert regret_b == 0.0
        assert regret_c > 0.0


# --------------------------------------------------------------------------- #
# 十、包的对外接口
# --------------------------------------------------------------------------- #
class TestPackageExports:
    """``from causal_growth.evaluation import ...`` 必须能直接拿到四指标入口。"""

    def test_reexports_resolve_to_metrics_module(self) -> None:
        assert eval_pkg.cate_accuracy is cate_accuracy
        assert eval_pkg.ranking_metrics is ranking_metrics
        assert eval_pkg.policy_value is policy_value
        assert eval_pkg.policy_value_observed is policy_value_observed
        assert eval_pkg.regret is regret
        assert eval_pkg.calibration_table is calibration_table
        assert eval_pkg.bootstrap_se is bootstrap_se
        assert eval_pkg.oracle_policy is oracle_policy
        assert eval_pkg.top_k_policy is top_k_policy
        assert eval_pkg.nonneg_policy is nonneg_policy
        assert eval_pkg.CateAccuracy is CateAccuracy
        assert eval_pkg.RankingMetrics is RankingMetrics

    def test_no_combined_score_function_exists(self) -> None:
        """方案 §2.4 要求四指标并列：包里**不允许**出现综合评分函数。"""
        forbidden = ("score", "composite", "aggregate", "total", "overall", "combined")
        public_names = [name for name in dir(eval_pkg) if not name.startswith("_")]
        offenders = [
            name for name in public_names if any(word in name.lower() for word in forbidden)
        ]
        assert offenders == []

    def test_calibration_columns_constant_is_exported(self) -> None:
        assert eval_pkg.CALIBRATION_COLUMNS == ("bin", "n", "mean_pred", "mean_true", "diff")


def test_calibration_table_returns_dataframe() -> None:
    """校准表是 pandas.DataFrame（要直接落 CSV，不能是裸数组）。"""
    table = calibration_table(np.arange(50.0), np.arange(50.0), n_bins=5)
    assert isinstance(table, pd.DataFrame)
    assert table["n"].dtype.kind in "iu"
