"""完整 DGP 链路 AA（:mod:`causal_growth.evaluation.v3_aa`）的测试。

覆盖四类断言：
1. **统计口径**：Clopper–Pearson 区间与蒙特卡洛精度必须与手算/分位数定义一致；
2. **配置合同**：每层恰有一个已注册 AA 格，且"同条件 + 虚拟标签"没被配置漂移破坏；
3. **链路不变量**：走完五表/污染清洗/SQL 后，标签仍不等于动作、券成本恒为 0；
   一旦链路把标签写进动作或成本，必须抛 :class:`AAChainError`（失败要响）；
4. **负对照分界**：购买零增量的负对照不得被汇总成"AA 通过"（决策 Q2）。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.evaluation import v3_aa
from causal_growth.evaluation.v3_aa import (
    find_windows_file_lock,
    AA_METRICS,
    SOURCE_CHANGED_MARKER,
    SUMMARY_COLUMNS,
    AAChainError,
    aa_cells,
    clopper_pearson,
    is_source_changed_error,
    run_aa_rep,
    run_full_chain_aa,
    summarize_repetitions,
)
from causal_growth.v3_config import load_v3_protocol

_CHAIN_N = 4000


def _run_or_skip(*args, **kwargs):
    """跑完整链路；**只**跳过"并发写盘触发源码绑定门禁"这一环境故障。

    项目有多个代理并行写 ``src/causal_growth/**/v3*.py``，而 C 阶段门禁会在
    ``build_observed_pipeline`` 前后哈希源码，期间任何写盘都会让本次 attempt 失败。
    这不是 AA 逻辑失败，也不是本模块能修复的问题（门禁不能放宽）；按主控要求
    只跳过这一类异常并在测试报告里显式列出，其余失败一律原样抛出。
    """
    try:
        return run_aa_rep(*args, **kwargs)
    except RuntimeError as exc:
        if is_source_changed_error(exc):
            pytest.skip(f"并发写盘：{SOURCE_CHANGED_MARKER}（源码绑定门禁，需串行复跑）")
        raise


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


@pytest.fixture(scope="module")
def chain_cell(protocol):
    return next(cell for cell in aa_cells(protocol) if cell.level == "L0")


@pytest.fixture(scope="module")
def chain_run(tmp_path_factory, protocol, chain_cell):
    """跑一次完整链路并保留产物；后面的用例复用，避免重复几秒级的流水线。"""
    root = Path(tmp_path_factory.mktemp("v3_aa_chain"))
    run_dir = root / "true_aa_L0_AA_rep0"
    row = _run_or_skip(chain_cell, protocol, rep=0, n=_CHAIN_N, run_dir=run_dir, keep_artifacts=True)
    return row, run_dir


# --------------------------------------------------------------------------- #
# 1. 统计口径
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "successes, trials, expected_lower, expected_upper",
    [
        (0, 50, 0.0, 0.0711217365),
        (1, 50, 0.0005062280, 0.1064695457),
        (2, 50, 0.0048814334, 0.1371376256),
        (10, 10, 0.6915028922, 1.0),
        (0, 10, 0.0, 0.3084971078),
    ],
)
def test_clopper_pearson_matches_exact_beta_quantiles(successes, trials, expected_lower, expected_upper):
    """CP 区间必须等于 Beta 分位数定义（黄金值由 scipy 独立算得并硬编码）。"""
    lower, upper = clopper_pearson(successes, trials)
    assert lower == pytest.approx(expected_lower, abs=1e-9)
    assert upper == pytest.approx(expected_upper, abs=1e-9)


def test_clopper_pearson_is_conservative_and_rejects_illegal_inputs():
    """CP 必须比 Wald 宽（小样本不外窄），且非法计数要抛而不是静默截断。"""
    lower, upper = clopper_pearson(1, 50)
    wald = 1 / 50 + 1.96 * np.sqrt((1 / 50) * (49 / 50) / 50)
    assert upper > wald
    with pytest.raises(ValueError):
        clopper_pearson(3, 2)
    with pytest.raises(ValueError):
        clopper_pearson(0, 0)
    with pytest.raises(TypeError):
        clopper_pearson(True, 10)
    with pytest.raises(TypeError):
        clopper_pearson(1.0, 10)
    with pytest.raises(ValueError):
        clopper_pearson(1, 10, confidence=1.5)


def test_primary_metric_is_net_profit_and_others_are_not_confirmatory():
    """主指标只有一个：净增量利润；购买率与护栏不得抢占 confirmatory 角色。"""
    assert AA_METRICS[0].column == "net_profit"
    assert AA_METRICS[0].role == "confirmatory_primary"
    assert AA_METRICS[0].kind == "continuous"
    assert [metric.role for metric in AA_METRICS[1:]] == ["auxiliary_diagnostic", "guardrail_diagnostic"]


def _fake_repetitions(block: str, scenario: str, level: str, p_values, covered, *, tag: str = "a"):
    """构造一份符合逐 rep 表合同的假数据，用于纯统计汇总测试（不跑链路）。"""
    repetitions = len(p_values)
    frame = pd.DataFrame({
        "block": [block] * repetitions, "scenario_id": [scenario] * repetitions,
        "level": [level] * repetitions, "rep": list(range(repetitions)),
        "n_total": [4000] * repetitions, "n_label1": [2000] * repetitions,
        "n_label0": [2000] * repetitions,
        "label_share": [0.5] * repetitions, "srm_p_value": [0.5] * repetitions,
        "registered_n": [200_000] * repetitions, "alpha": [0.05] * repetitions,
        "config_hash": [tag * 64] * repetitions,
        "dgp_cpu_s": [1.0] * repetitions, "pipeline_cpu_s": [2.0] * repetitions,
        "itt_cpu_s": [0.1] * repetitions, "total_cpu_s": [3.1] * repetitions,
        "total_wall_s": [3.2] * repetitions,
    })
    for population in ("full", "test"):
        for metric in ("net_profit", "paid_purchase_7d", "any_refund_30d"):
            frame[f"{population}_{metric}_p_value"] = list(p_values)
            frame[f"{population}_{metric}_diff"] = [0.05] * repetitions
            frame[f"{population}_{metric}_se"] = [0.1] * repetitions
            frame[f"{population}_{metric}_ci_lower"] = [-0.1 if flag else 0.2 for flag in covered]
            frame[f"{population}_{metric}_ci_upper"] = [0.1 if flag else 0.4 for flag in covered]
            frame[f"{population}_{metric}_n_treated"] = [2000] * repetitions
            frame[f"{population}_{metric}_n_control"] = [2000] * repetitions
    return frame


def test_summary_reports_cp_interval_mc_precision_and_coverage():
    """汇总行必须同时给出假阳性率、CP 区间、二项 MC 标准误与经验覆盖率。"""
    p_values = [0.01, 0.2, 0.6, 0.9]
    covered = [False, True, True, True]
    # 每层 active_scenario 不同 → 配置哈希本就不同（曾因误设"整块唯一"而炸过）
    frame = pd.concat([
        _fake_repetitions("true_aa", "L0_AA", "L0", p_values, covered, tag="a"),
        _fake_repetitions("true_aa", "L1_AA", "L1", p_values, covered, tag="b"),
    ], ignore_index=True)
    summary = summarize_repetitions(frame)
    assert list(summary.columns) == list(SUMMARY_COLUMNS)

    primary = summary.loc[
        (summary.block == "true_aa") & (summary.row_kind == "metric_aa")
        & (summary.scenario_id == "L0_AA") & (summary.metric == "net_profit")
        & (summary.analysis_population == "full")
    ].iloc[0]
    assert primary.R == 4
    assert primary.fpr == pytest.approx(0.25)
    expected = clopper_pearson(1, 4)
    assert primary.fpr_cp_lower == pytest.approx(expected[0])
    assert primary.fpr_cp_upper == pytest.approx(expected[1])
    assert primary.fpr_mc_se == pytest.approx(np.sqrt(0.25 * 0.75 / 4))
    assert primary.coverage == pytest.approx(0.75)
    assert primary.coverage_cp_upper >= primary.coverage_cp_lower
    assert primary.truth == 0.0
    assert primary.interpretation == "false_positive_rate_under_true_null"

    pooled = summary.loc[(summary.scenario_id == "POOLED_4_LAYERS") & (summary.metric == "net_profit")
                         & (summary.analysis_population == "full")].iloc[0]
    assert pooled.R == 8
    assert pooled.fpr == pytest.approx(0.25)
    assert pooled.fpr_cp_upper < primary.fpr_cp_upper  # 合并后区间更窄

    cost = summary.loc[(summary.scenario_id == "L0_AA") & (summary.row_kind == "cost_integrity")].iloc[0]
    assert cost.R == 4
    assert cost.total_cpu_s_mean == pytest.approx(3.1)
    assert cost.srm_reps == 4
    assert np.isnan(cost.fpr)


def test_summary_separates_negative_control_from_true_aa():
    """购买零增量负对照不得被读成"利润零效应 AA"（HITL Q2）。"""
    frame = pd.concat([
        _fake_repetitions("true_aa", "L0_AA", "L0", [0.01, 0.9], [False, True], tag="a"),
        _fake_repetitions("purchase_null_negative_control", "L0_zero_purchase_effect", "L0",
                          [0.01, 0.02], [False, False], tag="b"),
    ], ignore_index=True)
    summary = summarize_repetitions(frame)

    aa_profit = summary.loc[(summary.block == "true_aa") & (summary.metric == "net_profit")].iloc[0]
    assert aa_profit.interpretation == "false_positive_rate_under_true_null"
    assert aa_profit.truth == 0.0
    assert not np.isnan(aa_profit.coverage)

    nc_profit = summary.loc[(summary.block == "purchase_null_negative_control")
                            & (summary.metric == "net_profit")].iloc[0]
    assert np.isnan(nc_profit.truth), "负对照的利润真值不是 0，不能填 0"
    assert np.isnan(nc_profit.coverage), "真值非 0 时'区间含 0'不是覆盖率，不能报数"
    assert nc_profit.interpretation == "power_under_nonzero_profit_truth_not_aa"
    assert nc_profit.fpr == pytest.approx(1.0)

    nc_purchase = summary.loc[(summary.block == "purchase_null_negative_control")
                              & (summary.metric == "paid_purchase_7d")].iloc[0]
    assert nc_purchase.truth == 0.0
    assert nc_purchase.interpretation == "size_under_true_purchase_null"
    assert nc_purchase.fpr == pytest.approx(1.0)

    nc_refund = summary.loc[(summary.block == "purchase_null_negative_control")
                            & (summary.metric == "any_refund_30d")].iloc[0]
    assert np.isnan(nc_refund.truth)
    assert nc_refund.interpretation == "power_under_nonzero_guardrail_truth_not_aa"

    flagged = set(summary.loc[summary.block != "true_aa", "interpretation"])
    assert "false_positive_rate_under_true_null" not in flagged


# --------------------------------------------------------------------------- #
# 2. 配置合同
# --------------------------------------------------------------------------- #
def test_registered_aa_cells_are_one_per_layer_and_match_the_frozen_design(protocol):
    """格数来自注册表：每层恰一个 Tier1 完整 AA，1000 次、全员同一动作。"""
    cells = aa_cells(protocol)
    assert [cell.level for cell in cells] == ["L0", "L1", "L2", "L3"]
    assert all(cell.tier == 1 for cell in cells)
    assert all(cell.registered_reps == 1000 for cell in cells)
    assert all(cell.registered_n == 200_000 for cell in cells)
    assert all(cell.actual_action == 0 for cell in cells)
    assert all(cell.virtual_label_probability == 0.5 for cell in cells)
    design = protocol.config.require("design.aa")
    assert tuple(design) == ("actual_action", "virtual_label_probability", "label_effect_on_mechanism",
                            "pipeline", "repeats_per_layer")
    assert design["label_effect_on_mechanism"] == "none"
    assert tuple(design["pipeline"]) == ("five_tables", "dirty", "clean", "sql", "estimation")
    assert design["repeats_per_layer"] == 1000


def test_virtual_labels_only_replace_the_treatment_column_in_generated_data(protocol, chain_cell):
    """贴标签前后：动作恒为冻结动作、订单动作全为 0、标签是唯一新增的随机构造。"""
    cfg = protocol.scenario(chain_cell.scenario_id)
    population = generate_v3_population(cfg, rep_id=0, n=800)
    users, assignments, orders = population.observation_bundle()
    assert set(assignments.actual_action.unique().tolist()) == {chain_cell.actual_action}
    assert set(orders.action.unique().tolist()) == {chain_cell.actual_action}
    assert set(assignments.label.unique().tolist()) == {0, 1}
    assert assignments.design_probability.eq(0.5).all()
    assert assignments.label.nunique() == 2 and 0.3 < assignments.label.mean() < 0.7


# --------------------------------------------------------------------------- #
# 3. 完整链路不变量
# --------------------------------------------------------------------------- #
def test_full_chain_rep_runs_five_tables_sql_and_keeps_artifacts(chain_run):
    """一次 AA rep 必须真的落五表 + SQL 产物，且观测表里标签≠动作、券成本为 0。"""
    row, run_dir = chain_run
    assert row["virtual_aa"] is True
    assert row["n_total"] == _CHAIN_N
    assert row["n_label1"] + row["n_label0"] == _CHAIN_N
    assert row["actual_action_share"] == 0.0
    assert row["coupon_cost_total"] == 0.0
    assert row["split_train"] + row["split_validation"] + row["split_test"] == _CHAIN_N
    assert 0.0 <= row["full_net_profit_p_value"] <= 1.0
    assert row["full_net_profit_ci_lower"] <= row["full_net_profit_diff"] <= row["full_net_profit_ci_upper"]
    assert row["total_cpu_s"] > 0 and row["pipeline_cpu_s"] > 0

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "passed"
    assert manifest["formal_repetitions_completed"] == 0
    artifacts = set(manifest["artifacts"])
    for expected in ("raw/users.parquet", "dirty/user_events.parquet", "clean/orders.parquet",
                     "clean/user_outcomes.parquet", "sql/analysis.parquet",
                     "preprocessing/features.parquet", "lineage/stages.json"):
        assert expected in artifacts, expected
    assert manifest["checks"]["full_denominator"] is True
    assert manifest["checks"]["two_windows_per_user"] is True


def test_same_rep_is_bitwise_reproducible(tmp_path, protocol, chain_cell, chain_run):
    """同一 ``(master_seed, stream, rep)`` 必须逐位复现（AGENTS §3.3）。"""
    first, _ = chain_run
    second = _run_or_skip(chain_cell, protocol, rep=0, n=_CHAIN_N, run_dir=tmp_path / "repeat_rep0", keep_artifacts=False)
    for field in ("full_net_profit_diff", "full_net_profit_p_value", "full_net_profit_se",
                  "n_label1", "coupon_cost_total", "full_paid_purchase_7d_p_value"):
        assert second[field] == first[field], field
    assert not (tmp_path / "repeat_rep0").exists(), "非代表 rep 的临时产物必须删除"


def test_chain_that_writes_the_label_into_the_action_column_fails_loudly(tmp_path, protocol, chain_cell, monkeypatch):
    """链路一旦让券成本随标签变化，必须抛 AAChainError（不吞掉继续跑）。"""
    cfg = protocol.scenario(chain_cell.scenario_id)
    population = generate_v3_population(cfg, rep_id=3, n=200)
    users, assignments, _ = population.observation_bundle()

    def fake_pipeline(users_arg, assignments_arg, orders_arg, cfg_arg, *, run_id, **_kwargs):
        frame = pd.DataFrame({
            "run_id": run_id,
            "user_id": assignments_arg.user_id.to_numpy(),
            "treatment": assignments_arg.label.to_numpy(),
            "actual_action": np.ones(len(assignments_arg), dtype=int),  # 被污染：标签变动作
            "coupon_cost": np.full(len(assignments_arg), 5.5),
            "coupon_cost_cent": np.full(len(assignments_arg), 550),
            "mature": np.ones(len(assignments_arg), dtype=int),
            "split": np.array(["test"] * len(assignments_arg)),
            "diagnostic_snapshot": np.zeros(len(assignments_arg), dtype=int),
        })
        return SimpleNamespace(dataset=SimpleNamespace(observations=frame))

    monkeypatch.setattr(v3_aa, "build_observed_pipeline", fake_pipeline)
    with pytest.raises(AAChainError, match="实际动作"):
        run_aa_rep(chain_cell, protocol, rep=3, n=200, run_dir=tmp_path / "polluted", keep_artifacts=False)

    def fake_wrong_label(users_arg, assignments_arg, orders_arg, cfg_arg, *, run_id, **_kwargs):
        frame = pd.DataFrame({
            "run_id": run_id,
            "user_id": assignments_arg.user_id.to_numpy(),
            "treatment": 1 - assignments_arg.label.to_numpy(),  # 标签被改写
            "actual_action": np.zeros(len(assignments_arg), dtype=int),
            "coupon_cost": np.zeros(len(assignments_arg)),
            "coupon_cost_cent": np.zeros(len(assignments_arg), dtype=int),
            "mature": np.ones(len(assignments_arg), dtype=int),
            "split": np.array(["test"] * len(assignments_arg)),
            "diagnostic_snapshot": np.zeros(len(assignments_arg), dtype=int),
        })
        return SimpleNamespace(dataset=SimpleNamespace(observations=frame))

    monkeypatch.setattr(v3_aa, "build_observed_pipeline", fake_wrong_label)
    with pytest.raises(AAChainError, match="treatment 不等于输入的标签"):
        run_aa_rep(chain_cell, protocol, rep=3, n=200, run_dir=tmp_path / "relabeled", keep_artifacts=False)


def test_block_labels_cannot_be_swapped(protocol, tmp_path):
    """AA 格不能被登记成负对照，负对照也不能被登记成 AA。"""
    control_cell = next(cell for cell in aa_cells(protocol) if cell.level == "L1")
    with pytest.raises(AAChainError, match="不能登记为负对照"):
        run_aa_rep(control_cell, protocol, rep=0, n=400, run_dir=tmp_path / "x",
                   block="purchase_null_negative_control", keep_artifacts=False)
    negative = v3_aa._scenario_cell(protocol, "L0_zero_purchase_effect")
    with pytest.raises(AAChainError, match="不能登记为 true_aa"):
        run_aa_rep(negative, protocol, rep=0, n=400, run_dir=tmp_path / "y",
                   block="true_aa", keep_artifacts=False)


# --------------------------------------------------------------------------- #
# 4. 入口与纪律
# --------------------------------------------------------------------------- #
def test_batch_entry_rejects_illegal_parameters(tmp_path, protocol):
    """非法参数直接抛，不做静默降级。"""
    existing = tmp_path / "already_there"
    existing.mkdir()
    with pytest.raises(ValueError, match="reps"):
        run_full_chain_aa(protocol, reps=0, n=1000, layers=["L0"], cost_anchor_reps=0,
                          include_negative_control=False, run_root=tmp_path / "a")
    with pytest.raises(ValueError, match="层"):
        run_full_chain_aa(protocol, reps=1, n=1000, layers=["L9"], cost_anchor_reps=0,
                          include_negative_control=False, run_root=tmp_path / "b")
    with pytest.raises(FileExistsError):
        run_full_chain_aa(protocol, reps=1, n=1000, layers=["L0"], cost_anchor_reps=0,
                          include_negative_control=False, run_root=existing)
    with pytest.raises(AAChainError, match="负对照"):
        run_full_chain_aa(protocol, reps=1, n=1000, layers=["L0"], cost_anchor_reps=0,
                          include_negative_control=True,
                          negative_control_scenario="L0_AA", run_root=tmp_path / "c")


def test_cli_writes_traceable_summary_csv(tmp_path):
    """命令行入口必须落一份带来源标记的汇总表，且不推进正式重复数。"""
    run_root = tmp_path / "cli_run"
    summary_csv = tmp_path / "summary.csv"
    try:
        code = v3_aa.main([
            "--reps", "1", "--n", str(_CHAIN_N), "--layers", "L0",
            "--no-negative-control", "--cost-anchor-reps", "0",
            "--run-root", str(run_root), "--summary-csv", str(summary_csv), "--quiet",
        ])
    except RuntimeError as exc:
        if is_source_changed_error(exc):
            pytest.skip(f"并发写盘：{SOURCE_CHANGED_MARKER}（源码绑定门禁，需串行复跑）")
        raise
    assert code == 0
    frame = pd.read_csv(summary_csv, encoding="utf-8-sig")
    assert list(frame.columns) == list(SUMMARY_COLUMNS)
    assert frame.source_label.iloc[0].startswith("合成数据")
    metrics = frame.loc[frame.row_kind == "metric_aa"]
    assert set(metrics.scenario_id) == {"L0_AA"}
    assert metrics.R.eq(1).all()
    manifest = json.loads((run_root / "aa_manifest.json").read_text(encoding="utf-8"))
    assert manifest["formal_repetitions_completed"] == 0
    assert manifest["reps"] == 1 and manifest["n"] == _CHAIN_N
    assert (run_root / "aa_repetitions.csv").exists()


def test_source_change_detector_matches_only_the_gate_message():
    """只有"源码在 rep 执行期间被改写"这一条异常允许重试/跳过。"""
    assert is_source_changed_error(RuntimeError(SOURCE_CHANGED_MARKER + "；保留本次尝试"))
    assert not is_source_changed_error(RuntimeError("source files changed unnecessarily"))
    assert not is_source_changed_error(RuntimeError("some other runtime failure"))
    assert not is_source_changed_error(ValueError(SOURCE_CHANGED_MARKER))
    assert not is_source_changed_error(AAChainError(SOURCE_CHANGED_MARKER))


def test_source_change_is_retried_within_the_budget_only(monkeypatch, tmp_path, protocol):
    """并发写盘的门禁异常可以重试，但重试次数有上限，超限后必须抛。"""
    calls: list[int] = []

    def gate(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError("source files changed during the data run; retain this attempt as failed")

    monkeypatch.setattr(v3_aa, "run_aa_rep", gate)
    with pytest.raises(RuntimeError, match="source files changed"):
        run_full_chain_aa(protocol, reps=1, n=1000, layers=["L0"], cost_anchor_reps=0,
                          include_negative_control=False, run_root=tmp_path / "retry",
                          max_source_retries=2)
    assert len(calls) == 3


def test_other_runtime_errors_are_not_retried(monkeypatch, tmp_path, protocol):
    """其它运行期异常一律立即抛，不得被当成并发写盘而重试。"""
    calls: list[int] = []

    def boom(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError("pipeline exploded for a real reason")

    monkeypatch.setattr(v3_aa, "run_aa_rep", boom)
    with pytest.raises(RuntimeError, match="pipeline exploded"):
        run_full_chain_aa(protocol, reps=3, n=1000, layers=["L0"], cost_anchor_reps=0,
                          include_negative_control=False, run_root=tmp_path / "noretry",
                          max_source_retries=3)
    assert len(calls) == 1


def test_windows_file_lock_detector_walks_the_exception_chain():
    """原子落盘的 WinError 5/32/33 属于可重试环境故障，且必须能穿过包装层。"""
    denied = PermissionError(13, "拒绝访问")
    denied.winerror = 5
    wrapped = ValueError("run is already terminal")
    wrapped.__context__ = denied
    assert find_windows_file_lock(wrapped) is denied
    sharing = OSError(32, "共享冲突")
    sharing.winerror = 32
    assert find_windows_file_lock(sharing) is sharing
    assert find_windows_file_lock(RuntimeError("real bug")) is None
    real = OSError(2, "file not found")
    real.winerror = 2
    assert find_windows_file_lock(real) is None


def _batch_or_skip(**kwargs):
    """批量入口；只跳过并发写盘的门禁异常（其余一律抛出）。"""
    try:
        return run_full_chain_aa(**kwargs)
    except RuntimeError as exc:
        if is_source_changed_error(exc):
            pytest.skip(f"并发写盘：{SOURCE_CHANGED_MARKER}（源码绑定门禁，需串行复跑）")
        raise


def test_flush_is_incremental_and_resume_skips_completed_reps(tmp_path, protocol, monkeypatch):
    """每完成一个 rep 就落盘；续跑只补缺口，不重复执行。"""
    flush = tmp_path / "reps.csv"
    bundle = _batch_or_skip(protocol=protocol, reps=1, n=_CHAIN_N, layers=["L0"],
                            cost_anchor_reps=0, include_negative_control=False, max_source_retries=3,
                            run_root=tmp_path / "first", flush_path=flush)
    assert len(bundle.repetitions) == 1
    stored = pd.read_csv(flush, encoding="utf-8-sig")
    assert len(stored) == 1 and stored.scenario_id.iloc[0] == "L0_AA"
    assert stored.file_lock_retries.eq(0).all() and stored.source_retries.eq(0).all()

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("续跑时不应重复执行已完成的 rep")

    monkeypatch.setattr(v3_aa, "run_aa_rep", must_not_run)
    resumed = run_full_chain_aa(protocol, reps=1, n=_CHAIN_N, layers=["L0"],
                                cost_anchor_reps=0, include_negative_control=False,
                                run_root=tmp_path / "second", resume_from=flush)
    assert len(resumed.repetitions) == 1
    metrics = resumed.summary.loc[resumed.summary.row_kind == "metric_aa"]
    assert metrics.R.eq(1).all()


def test_resume_rejects_mismatched_batch_parameters(tmp_path, protocol, chain_run):
    """续跑文件与当前请求的 n/alpha 不一致时必须拒绝，不能混批。"""
    row, _ = chain_run
    frame = pd.DataFrame([row])
    wrong_n = frame.copy()
    wrong_n.loc[:, "n_total"] = 123
    path = tmp_path / "wrong_n.csv"
    wrong_n.to_csv(path, index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="n 与当前请求不一致"):
        run_full_chain_aa(protocol, reps=1, n=_CHAIN_N, layers=["L0"], cost_anchor_reps=0,
                          include_negative_control=False, run_root=tmp_path / "r1",
                          resume_from=path)
    wrong_alpha = frame.copy()
    wrong_alpha.loc[:, "alpha"] = 0.1
    path2 = tmp_path / "wrong_alpha.csv"
    wrong_alpha.to_csv(path2, index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="alpha 与当前协议不一致"):
        run_full_chain_aa(protocol, reps=1, n=_CHAIN_N, layers=["L0"], cost_anchor_reps=0,
                          include_negative_control=False, run_root=tmp_path / "r2",
                          resume_from=path2)


def test_module_reads_no_truth_state():
    """静态纪律：不得 import 封存真值模块，也不得读 population 的 audit 字段。"""
    source = Path(v3_aa.__file__).read_text(encoding="utf-8")
    assert "v3_archive" not in source
    assert "audit_window_ledger" not in source
    assert "audit_potential_orders" not in source
    assert ".audit_" not in source
    assert "cate_profit" not in source
    assert "true_propensity" not in source


