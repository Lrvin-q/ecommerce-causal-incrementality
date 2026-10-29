"""41 号矩阵逐格契约：总样本列是 n（不是 n_total），并校验 n 拆分一致。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _load41():
    spec = importlib.util.spec_from_file_location(
        "g41_for_test", ROOT / "scripts" / "41_export_g03_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(**overrides):
    row = {
        "rep": 0,
        "status": "formal",
        "protocol_config_hash": "abc",
        "block": "g_core",
        "tier": 1,
        "n": 200000,
        "n_treated": 100000,
        "n_control": 100000,
        "validation_bootstrap_resamples": 0,
    }
    row.update(overrides)
    return row


def test_check_cell_uses_n_not_n_total():
    module = _load41()
    problems = module.check_cell("L0_P_main", "g_core", pd.DataFrame([_row()]))
    assert not any("缺列" in item for item in problems)
    assert any("rows=1 != R=500" in item for item in problems)


def test_check_cell_rejects_split_mismatch():
    module = _load41()
    problems = module.check_cell("L0_P_main", "g_core", pd.DataFrame([_row(n=200001)]))
    assert any("n_treated+n_control != n" in item for item in problems)


def test_check_cell_reports_missing_column():
    module = _load41()
    frame = pd.DataFrame([_row()]).drop(columns=["n"])
    assert module.check_cell("L0_P_main", "g_core", frame) == [
        "L0_P_main: 缺列 ['n']（逐 rep 表契约）"
    ]


def test_check_cell_green_on_complete_frame():
    """正例：跑满 R 的合法帧必须零问题（验证它真能读好输入，而不只是会拒坏输入）。"""
    module = _load41()
    frame = pd.DataFrame([_row(rep=i) for i in range(module.CORE_R)])
    assert module.check_cell("L0_P_main", "g_core", frame) == []


def test_fixed_bootstrap_rows_real_layout(tmp_path):
    """按阶段 A 真实落盘路径造 24 格；装载器必须零问题并回 24 行。"""
    module = _load41()
    for cell in list(module.expected_cells()):
        part = tmp_path / "shards" / f"{cell}_s0000" / cell / "rep0" / "validation"
        part.mkdir(parents=True)
        pd.DataFrame([{
            "rep": 0,
            "budget_cny_per_user": 0.2,
            "resamples": 1000,
            "n_targeted": 10,
            "n_random": 10,
            "point_diff": 0.5,
            "bootstrap_mean_diff": 0.5,
            "bootstrap_se": 0.1,
            "ci_low": 0.3,
            "ci_high": 0.7,
        }]).to_csv(part / "fixed_bootstrap.csv", index=False)
    frame, problems = module.fixed_bootstrap_rows(tmp_path)
    assert problems == []
    assert len(frame) == len(module.expected_cells()) == 24
    assert set(frame["cell_id"]) == set(module.expected_cells())


def test_fixed_bootstrap_rows_flags_bad_budget(tmp_path):
    module = _load41()
    cell = next(iter(module.expected_cells()))
    part = tmp_path / "shards" / f"{cell}_s0000" / cell / "rep0" / "validation"
    part.mkdir(parents=True)
    pd.DataFrame([{
        "rep": 0, "budget_cny_per_user": 0.5, "resamples": 1000,
        "point_diff": 0.5, "ci_low": 0.3, "ci_high": 0.7,
    }]).to_csv(part / "fixed_bootstrap.csv", index=False)
    _, problems = module.fixed_bootstrap_rows(tmp_path)
    assert any("budget=0.5 != 0.2" in item for item in problems)
