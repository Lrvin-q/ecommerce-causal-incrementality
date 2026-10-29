"""scripts/48 的契约测试：G03 汇总表的格数、指标、R 与 provisional 判据。

这些用例是 2026-10-29 手工夹具的固化版：48 号负责在 G03 跑完后产出论文 §3 的数字，
它一旦被改坏，最先受伤的是报告而非报错，所以把判据都钉成测试。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "g03_matrix_report", ROOT / "scripts" / "48_g03_matrix_report.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)

CORE_CELLS = ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"]


def _table(tmp_path: Path, *, block: str = "g_core", r: int = 500,
           provisional: int = 0, cells: list[str] | None = None,
           skip_metric: str | None = None, mean: float = 1.0) -> Path:
    cells = CORE_CELLS if cells is None else cells
    tier = 1 if block == "g_core" else 2
    rows = []
    for cell in cells:
        for metric in report.METRICS:
            if metric == skip_metric:
                continue
            rows.append({"cell_id": cell, "block": block, "tier": tier, "metric": metric,
                         "R": r, "MC_SE": 0.01, "sd": 0.1, "mean": mean,
                         "provisional": provisional})
    path = tmp_path / f"{block}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_full_core_table_is_clean(tmp_path: Path):
    problems: list[str] = []
    report.load(_table(tmp_path), "g_core", problems)
    assert problems == []


def test_short_with_provisional_is_allowed(tmp_path: Path):
    problems: list[str] = []
    report.load(_table(tmp_path, r=100, provisional=1), "g_core", problems)
    assert problems == []


def test_short_without_provisional_is_caught(tmp_path: Path):
    problems: list[str] = []
    report.load(_table(tmp_path, r=100, provisional=0), "g_core", problems)
    assert any("却没标 provisional" in item for item in problems)


def test_full_but_provisional_is_caught(tmp_path: Path):
    problems: list[str] = []
    report.load(_table(tmp_path, r=500, provisional=1), "g_core", problems)
    assert any("已跑满却标 provisional" in item for item in problems)


def test_missing_metric_is_caught(tmp_path: Path):
    problems: list[str] = []
    report.load(_table(tmp_path, skip_metric="ate_test"), "g_core", problems)
    assert any("指标" in item for item in problems)


def test_wrong_block_is_caught(tmp_path: Path):
    problems: list[str] = []
    report.load(_table(tmp_path), "g_tier2", problems)
    assert any("block=" in item for item in problems)


def test_cell_count_mismatch_is_caught(tmp_path: Path):
    problems: list[str] = []
    report.load(_table(tmp_path, cells=CORE_CELLS[:3]), "g_core", problems)
    assert any("格 != 注册 4" in item for item in problems)


def test_non_finite_mean_is_caught(tmp_path: Path):
    problems: list[str] = []
    report.load(_table(tmp_path, mean=float("nan")), "g_core", problems)
    assert any("mean 非有限值" in item for item in problems)


def test_resolve_prefers_explicit_then_final(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(report, "TABLES", tmp_path)
    explicit = tmp_path / "custom_provisional.csv"
    assert report.resolve(explicit, "v3_g_g_core") == (explicit, True)
    final = tmp_path / "v3_g_g_core.csv"
    final.write_text("cell_id\n", encoding="utf-8")
    (tmp_path / "v3_g_g_core_provisional.csv").write_text("cell_id\n", encoding="utf-8")
    assert report.resolve(None, "v3_g_g_core") == (final, False)


def test_resolve_raises_when_nothing_on_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(report, "TABLES", tmp_path)
    with pytest.raises(SystemExit):
        report.resolve(None, "v3_g_g_core")
