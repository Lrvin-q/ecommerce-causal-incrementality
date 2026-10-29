"""H04 数字门禁的行为测试：正例、篡改、自检夹具。"""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "claim_gate", ROOT / "scripts" / "42_claim_number_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

REGISTRY = ROOT / "outputs/tables/v3_h04_claim_registry.csv"


def _copy_registry(tmp_path: Path, **override: str) -> Path:
    with REGISTRY.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    target = tmp_path / "reg.csv"
    with target.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        for index, row in enumerate(rows):
            if index == 0:
                row.update(override)
            writer.writerow(row)
    return target


def test_registry_is_clean():
    assert gate.validate(REGISTRY) == []


def test_tampered_digit_is_caught(tmp_path: Path):
    path = _copy_registry(tmp_path, display_value="0.047")
    problems = gate.validate(path)
    assert any("显示值" in item for item in problems)


def test_tier2_in_abstract_is_caught(tmp_path: Path):
    path = _copy_registry(tmp_path, tier="Tier2", in_abstract="yes",
                          precision_note="R=30 精度")
    problems = gate.validate(path)
    assert any("摘要只允许 Tier1" in item for item in problems)


def test_ambiguous_filter_is_caught(tmp_path: Path):
    path = _copy_registry(tmp_path, filter="metric == 'net_profit'")
    problems = gate.validate(path)
    assert any("必须恰好 1 行" in item for item in problems)


def test_self_test_all_pass():
    assert gate.self_test() == 0
