"""G 阶段矩阵驱动的验收测试（任务书 §8 A1–A10）。

纪律
----
- 所有断言都对着**真实构建链路**（n=400 的工程规模），不 mock 数据生成。
- A1 与 A8 是硬门槛：A1 证明"学习复用同一份 rep 数据"不改变估计；A8 证明
  选人只读预测列，篡改真值后名单逐字节不变。
- A2 的逐字节比较只覆盖 ``repetitions.csv``；CPU 计时在
  ``repetitions_telemetry.csv``，是硬件遥测，任何两次运行都不可能相同。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causal_growth.config import ConfigError
from causal_growth.evaluation import v3_g_matrix as g
from causal_growth.v3_config import load_v3_protocol

CORE = "L1_main"
TIER2 = "L0_zero_purchase_effect"
N_TINY = 400
MODELS = ("constant",)
REPO = Path(__file__).resolve().parents[1]
OVERLAY = REPO / "configs" / "budget" / "tier2_overlay.yaml"


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


@pytest.fixture(scope="module")
def plan(protocol):
    return g.load_budget_plan(protocol, overlay=OVERLAY)


def _run_cell(protocol, plan, out_root, *, reps, target_reps, **kwargs):
    options = {
        "n": N_TINY,
        "plan": plan,
        "models": MODELS,
        "with_learning": False,
        "with_validation": False,
        "status": "engineering",
    }
    options.update(kwargs)
    return g.run_cell(
        protocol, CORE, out_root=out_root, reps=reps, target_reps=target_reps, **options
    )


# --------------------------------------------------------------------------- #
# A1：共用 rep 不改变估计，且每个 rep 只建一次数据
# --------------------------------------------------------------------------- #
def test_a1_shared_rep_matches_independent_ate(protocol, plan, tmp_path, monkeypatch):
    spec = g.plan_cell(protocol, CORE, plan)
    real_build = g.build_history_dataset
    real_fit = g.fit_history_models
    builds: list[int] = []
    fit_ids: list[int] = []

    def counting_build(*args, **kwargs):
        result = real_build(*args, **kwargs)
        builds.append(id(result[0]))
        return result

    def recording_fit(dataset, *args, **kwargs):
        fit_ids.append(id(dataset))
        return real_fit(dataset, *args, **kwargs)

    monkeypatch.setattr(g, "build_history_dataset", counting_build)
    monkeypatch.setattr(g, "fit_history_models", recording_fit)

    row = g.run_g_rep(
        protocol, CORE, 0, out_dir=tmp_path / "shared", n=N_TINY, plan=plan,
        models=MODELS, with_learning=True, with_validation=False,
    )

    assert len(builds) == 1, "学习路径重建了历史数据"
    assert row["history_pipeline_builds"] == 1
    assert row["validation_pipeline_builds"] == 0
    assert fit_ids == builds, "学习用的不是 ATE 那一份数据对象"

    cfg = protocol.scenario(CORE)
    run_id = f"g:{CORE}:{spec['block']}:rep0"
    ds_a, _, _ = real_build(cfg, rep_id=0, n=N_TINY, run_id=run_id)
    ds_b, _, _ = real_build(cfg, rep_id=0, n=N_TINY, run_id=run_id)
    ate_a = g.estimate_ate(ds_a, cfg)

    assert ds_a.content_hash == row["observed_hash"] == ds_b.content_hash
    assert float(ate_a["ate"]) == float(row["ate"]), "共用路径与独立路径的 ATE 不是逐位相同"
    assert abs(float(ate_a["ate"]) - float(row["ate"])) < 1e-12


# --------------------------------------------------------------------------- #
# A2：中断后 resume 与不中断跑完逐字节相同
# --------------------------------------------------------------------------- #
def test_a2_resume_is_byte_identical(protocol, plan, tmp_path):
    first = _run_cell(protocol, plan, tmp_path / "resume", reps=[0], target_reps=2)
    assert first["provisional"] is True

    resumed = _run_cell(
        protocol, plan, tmp_path / "resume", reps=[0, 1], target_reps=2,
        resume_from=Path(first["rows_path"]),
    )
    fresh = _run_cell(protocol, plan, tmp_path / "fresh", reps=[0, 1], target_reps=2)

    resumed_bytes = Path(resumed["rows_path"]).read_bytes()
    fresh_bytes = Path(fresh["rows_path"]).read_bytes()
    assert resumed_bytes == fresh_bytes, "resume 与一次跑完的逐 rep 表不是逐字节相同"
    assert resumed["provisional"] is True and fresh["provisional"] is True

    telemetry = tmp_path / "resume" / CORE / "repetitions_telemetry.csv"
    assert telemetry.is_file()
    header = telemetry.read_text(encoding="utf-8-sig").splitlines()[0]
    assert header.split(",") == list(g.TELEMETRY_COLUMNS)


# --------------------------------------------------------------------------- #
# A3：n / config_hash 漂移必须拒绝拼接
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field,value", [("n", "401"), ("config_hash", "0" * 64)])
def test_a3_resume_rejects_parameter_drift(protocol, plan, tmp_path, field, value):
    result = _run_cell(protocol, plan, tmp_path / f"base_{field}", reps=[0], target_reps=2)
    rows = g.read_repetition_rows(result["rows_path"])
    rows[0][field] = value
    drifted = tmp_path / f"drifted_{field}.csv"
    g.write_repetition_rows(drifted, rows)

    with pytest.raises(ValueError, match="续跑参数"):
        _run_cell(
            protocol, plan, tmp_path / f"base_{field}", reps=[1], target_reps=2,
            resume_from=drifted,
        )


# --------------------------------------------------------------------------- #
# A4：多根合并按 (scenario_id, block, rep) 去重，重复计数可核对
# --------------------------------------------------------------------------- #
def _fake_row(rep: int, ate: float) -> dict[str, str]:
    row = {column: "" for column in g.row_columns()}
    row.update({
        "cell_id": CORE, "scenario_id": CORE, "level": "L1", "tier": "1",
        "block": g.BLOCK_CORE, "rep": str(rep), "n": str(N_TINY),
        "ate": repr(float(ate)), "status": "engineering", "provisional": "True",
    })
    return row


def test_a4_multi_root_merge_counts_duplicates(tmp_path):
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    g.write_repetition_rows(root_a / CORE / "repetitions_provisional.csv",
                            [_fake_row(0, 1.0), _fake_row(1, 2.0)])
    g.write_repetition_rows(root_b / CORE / "repetitions_provisional.csv",
                            [_fake_row(1, 2.0), _fake_row(2, 3.0)])

    merged, report = g.merge_roots([root_a, root_b])
    assert report["rows_raw"] == 4
    assert report["rows_deduped"] == 3
    assert report["duplicates_removed"] == 1
    assert report["rows_raw"] - report["rows_deduped"] == report["duplicates_removed"]
    assert sorted(int(row["rep"]) for row in merged) == [0, 1, 2]

    root_c = tmp_path / "root_c"
    g.write_repetition_rows(root_c / CORE / "repetitions_provisional.csv",
                            [_fake_row(0, 9.0)])
    with pytest.raises(ValueError, match="内容不同"):
        g.merge_roots([root_a, root_c])


# --------------------------------------------------------------------------- #
# A5：未跑满只写 provisional，且 formal 必须带批准号
# --------------------------------------------------------------------------- #
def test_a5_unfinished_writes_only_provisional(protocol, plan, tmp_path):
    result = _run_cell(protocol, plan, tmp_path / "cell", reps=[0], target_reps=2)
    assert result["provisional"] is True
    assert Path(result["rows_path"]).name == "repetitions_provisional.csv"
    assert not (tmp_path / "cell" / CORE / "repetitions.csv").is_file()
    state = json.loads(Path(result["state_path"]).read_text(encoding="utf-8"))
    assert state["provisional"] is True
    assert state["target_reps"] == 2

    with pytest.raises(ValueError, match="formal_approval"):
        _run_cell(protocol, plan, tmp_path / "cell", reps=[1], target_reps=2,
                  status="formal")


# --------------------------------------------------------------------------- #
# A6：overlay 改 R 立即生效，冻结配置 hash 不变
# --------------------------------------------------------------------------- #
def test_a6_overlay_changes_reps_without_touching_frozen_hash(protocol, tmp_path):
    before = load_v3_protocol().config_hash
    text = OVERLAY.read_text(encoding="utf-8").replace("tier2_reps: 30", "tier2_reps: 7")
    overlay = tmp_path / "overlay7.yaml"
    overlay.write_text(text, encoding="utf-8")

    plan7 = g.load_budget_plan(protocol, overlay=overlay)
    spec = g.plan_cell(protocol, TIER2, plan7)
    assert plan7.tier2_reps == 7
    assert (spec["R_ate"], spec["R_learn"], spec["R_validation"]) == (7, 7, 7)

    after = load_v3_protocol().config_hash
    assert after == before == "00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3"

    bad = tmp_path / "bad.yaml"
    bad.write_text(text + "\nbogus_key: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="未注册键"):
        g.load_budget_plan(protocol, overlay=bad)


# --------------------------------------------------------------------------- #
# A7：每格汇总都带 R 与 MC_SE，且 MC_SE = sd/sqrt(R)
# --------------------------------------------------------------------------- #
def test_a7_summary_reports_R_and_mc_se(tmp_path):
    rows = []
    for rep in range(30):
        row = _fake_row(rep, 0.10 + 0.01 * rep)
        row.update({"tier": "2", "block": g.BLOCK_TIER2, "cell_id": TIER2,
                    "scenario_id": TIER2, "level": "L0",
                    "ate_test": "0.1", "ate_paid_purchase_7d": "0.01",
                    "ate_any_refund_30d": "0.0"})
        rows.append(row)

    table = g.summarize_repetitions(rows, provisional=True)
    cell = table[(table["cell_id"] == TIER2) & (table["metric"] == "ate")].iloc[0]
    values = np.array([0.10 + 0.01 * rep for rep in range(30)])
    expected = float(values.std(ddof=1) / np.sqrt(30))
    assert int(cell["R"]) == 30
    assert float(cell["MC_SE"]) == pytest.approx(expected, rel=1e-12)
    assert table["MC_SE"].notna().all()
    assert set(table["R"]) == {30}

    path = g.write_summary_table(rows, tmp_path / "v3_g_tier2.csv", provisional=True)
    assert path.name == "v3_g_tier2_provisional.csv"
    assert path.is_file()


# --------------------------------------------------------------------------- #
# A8：选人只读预测列；篡改真值后名单逐字节不变（硬门槛）
# --------------------------------------------------------------------------- #
def _prediction_frame(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    return pd.DataFrame({
        "user_id": np.arange(n),
        "is_new": rng.integers(0, 2, n),
        "cart_value": rng.uniform(10, 100, n),
        "purchase_propensity": rng.uniform(0, 1, n),
        "predicted_profit": rng.uniform(0, 5, n),
        "tau_hat": rng.uniform(0, 2, n),
        "cost_hat": rng.uniform(0, 1, n),
    })


def test_a8_selection_rejects_truth_columns_and_ignores_values(protocol):
    cfg = protocol.scenario(CORE)
    frame = _prediction_frame()
    with pytest.raises(ValueError, match="真值列"):
        g.select_policy_list(
            frame.assign(tau_true=0.0), policy="greedy_incremental_profit_per_cost",
            budget_cny=0.2, seed_index=0, cfg=cfg,
        )

    clean = g.select_policy_list(
        frame, policy="greedy_incremental_profit_per_cost",
        budget_cny=0.2, seed_index=0, cfg=cfg,
    )
    rng = np.random.default_rng(99)
    truth = pd.DataFrame({
        "user_id": frame["user_id"],
        "tau_true": rng.normal(size=len(frame)),
        "cost_true": rng.uniform(size=len(frame)),
    })
    merged = g.assemble_e_columns(frame, truth)
    assert list(merged.columns) == list(g.E_COLUMNS)
    again = g.select_policy_list(
        merged.loc[:, list(g.E_PREDICTION_COLUMNS)],
        policy="greedy_incremental_profit_per_cost",
        budget_cny=0.2, seed_index=0, cfg=cfg,
    )
    assert clean.equals(again), "真值变化影响了选人结果"


def test_a8_tampered_truth_leaves_policy_list_identical(protocol, plan, tmp_path, monkeypatch):
    g.run_g_rep(
        protocol, CORE, 0, out_dir=tmp_path / "clean", n=N_TINY, plan=plan,
        models=MODELS, with_learning=True, with_validation=True,
    )
    clean_list = (tmp_path / "clean" / "validation" / "policy_list.csv").read_bytes()
    clean_freeze = json.loads(
        (tmp_path / "clean" / "validation" / "freeze.json").read_text(encoding="utf-8")
    )
    assert clean_freeze["truth_columns_present"] is False

    def tampered_audit(population, cfg, *, info, observed, assignment):
        n = len(observed)
        rng = np.random.default_rng(1234)
        return {
            "users": pd.DataFrame({
                "user_id": observed["user_id"].to_numpy(),
                "tau_true": rng.normal(size=n) * 1e6,
                "cost_true": rng.uniform(size=n) * 1e6,
            }),
            "policy": pd.DataFrame({"user_id": observed["user_id"].to_numpy(),
                                    "truth_policy_value": rng.normal(size=n) * 1e6}),
            "arms": pd.DataFrame({"arm": ["targeted", "random", "control"],
                                  "true_mean": [1e6, 1e6, 1e6]}),
            "contrasts": pd.DataFrame({"contrast": ["targeted_minus_random"],
                                       "true_diff": [1e6]}),
        }

    monkeypatch.setattr(g, "_audit_truth", tampered_audit)
    g.run_g_rep(
        protocol, CORE, 0, out_dir=tmp_path / "tampered", n=N_TINY, plan=plan,
        models=MODELS, with_learning=True, with_validation=True,
    )
    tampered_list = (tmp_path / "tampered" / "validation" / "policy_list.csv").read_bytes()
    assert tampered_list == clean_list, "篡改真值改变了冻结名单"


# --------------------------------------------------------------------------- #
# A9：快照绑定与实际源码快照一致；漂移拒绝登记
# --------------------------------------------------------------------------- #
def test_a9_snapshot_binding_matches_snapshot(protocol, plan, tmp_path):
    binding = g.create_snapshot(tmp_path / "snap")
    assert binding["kind"] == "byte_snapshot"
    assert binding["source_hashes"] == g.pipeline_source_hashes()
    payload = json.dumps(binding["source_hashes"], sort_keys=True, separators=(",", ":"))
    assert binding["source_hashes_sha256"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()

    g.run_g_rep(
        protocol, CORE, 0, out_dir=tmp_path / "snap_run", n=N_TINY, plan=plan,
        models=MODELS, with_learning=False, with_validation=False, snapshot=binding,
    )
    manifest = json.loads(
        (tmp_path / "snap_run" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["snapshot_binding"]["source_hashes_sha256"] == binding["source_hashes_sha256"]
    assert manifest["snapshot_binding"]["kind"] == "byte_snapshot"

    tampered = json.loads(json.dumps(binding))
    first = next(iter(tampered["source_hashes"]))
    tampered["source_hashes"][first] = "0" * 64
    with pytest.raises(RuntimeError, match=g.SOURCE_CHANGED_MARKER):
        g.run_g_rep(
            protocol, CORE, 0, out_dir=tmp_path / "tampered_run", n=N_TINY, plan=plan,
            models=MODELS, with_learning=False, with_validation=False, snapshot=tampered,
        )


# --------------------------------------------------------------------------- #
# A10：小规模两格跑通，产物结构符合 §4.3
# --------------------------------------------------------------------------- #
def test_a10_two_cells_small_scale_contract(protocol, plan, tmp_path):
    required = set(g.row_columns())
    # 第二个格必须选有真实购买的格：零购买效应格在小 n 下处理组购买者 <10，成本模型会按设计拒绝
    for cell in (CORE, "L0_Pi_heterogeneous_cost"):
        result = g.run_cell(
            protocol, cell, out_root=tmp_path / "two_cells", reps=[0],
            target_reps=1, n=N_TINY, plan=plan, models=MODELS,
            with_learning=True, with_validation=True, status="engineering",
        )
        assert result["provisional"] is True
        rows = g.read_repetition_rows(result["rows_path"])
        assert len(rows) == 1
        assert set(rows[0]) == required
        rep_dir = tmp_path / "two_cells" / cell / "rep0"
        for name in ("manifest.json", "row.json", "validation/policy_list.csv",
                     "validation/freeze.json", "validation/truth_users.csv"):
            assert (rep_dir / name).is_file(), f"{cell} 缺少 {name}"
        manifest = json.loads((rep_dir / "manifest.json").read_text(encoding="utf-8"))
        for key in ("run_id", "scenario_id", "rep_range", "n", "R_ate", "R_learn",
                    "R_validation", "source_hashes_before", "source_hashes_after",
                    "sql_sha256", "config_hash", "data_config_hash",
                    "protocol_config_hash", "snapshot_binding", "budget_plan"):
            assert key in manifest, f"manifest 缺少 {key}"
        assert manifest["history_pipeline_builds"] == 1
        assert manifest["validation_pipeline_builds"] == 1
        assert manifest["truth_columns_present"] is False
