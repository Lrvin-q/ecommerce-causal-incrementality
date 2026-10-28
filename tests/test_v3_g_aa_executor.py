"""G01 AA 臂执行器（``scripts/36_g_aa_run.py``）的验收测试。

为什么这些断言必须有
--------------------
36 号是纯编排层，但它有三个"错了也看起来正常"的失败模式：

1. **拆层拆错**：把别层/别协议的行混进 ``<layer>/aa_repetitions.csv``，
   17 号会照常池化——数字对、来源错。``split_layer_table`` 必须抛而不是过滤。
2. **规模冒充**：工程跑的 n 被当成正式 n，17 号才拒；应在 36 号就拒。
3. **门禁被绕过**：正式跑不带批准号/快照就开跑，或工程跑默认 250 rep。

这些测试不跑真实 AA 链路（4 层 × 2000 人由 ``--reps 1`` 冒烟覆盖），
只钉住编排契约；真实链路由 ``tests/test_v3_aa.py`` 负责。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "36_g_aa_run.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("g_aa_run_36", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def protocol():
    from causal_growth.v3_config import load_v3_protocol

    return load_v3_protocol()


def test_layer_cells_cover_four_layers_with_distinct_cells(mod, protocol):
    cells = mod.layer_cells(protocol)
    assert sorted(cells) == ["L0", "L1", "L2", "L3"]
    ids = [cell.scenario_id for cell in cells.values()]
    assert len(set(ids)) == 4
    assert all(cell.tier == 1 for cell in cells.values())
    assert {cell.registered_n for cell in cells.values()} == {200_000}


def test_declared_reps_matches_frozen_config(mod, protocol):
    assert mod.declared_reps(protocol) == 250


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"status": "formal", "approval": None, "snapshot": None}, "formal-approval"),
        ({"status": "formal", "approval": "X", "snapshot": None}, "snapshot"),
        ({"status": "engineering", "reps": None}, "reps"),
        ({"status": "engineering", "reps": 6}, "上限"),
        ({"status": "engineering", "reps": 0}, ">= 1"),
        ({"status": "formal", "approval": "X", "snapshot": {"a": 1}, "reps": 250, "rep_start": 1},
         "超出注册"),
    ],
)
def test_gate_rejects(mod, kwargs, message):
    args = {"status": "engineering", "approval": None, "snapshot": None,
            "allow_live": False, "reps": 1, "declared": 250, "rep_start": 0}
    args.update(kwargs)
    with pytest.raises(SystemExit) as excinfo:
        mod.gate(**args)
    assert message in str(excinfo.value)


def test_gate_formal_defaults_to_declared(mod):
    assert mod.gate(status="formal", approval="X", snapshot={"a": 1},
                    allow_live=False, reps=None, declared=250, rep_start=0) == 250


def test_gate_live_formal_requires_explicit_override(mod):
    assert mod.gate(status="formal", approval="X", snapshot=None,
                    allow_live=True, reps=250, declared=250, rep_start=0) == 250


def _row(block: str, scenario: str, rep: int, protocol_hash: str) -> dict:
    return {"block": block, "scenario_id": scenario, "rep": rep,
            "protocol_config_hash": protocol_hash, "n_total": 2000, "alpha": 0.05}


def test_split_keeps_only_true_aa_rows(mod):
    frame = pd.DataFrame([
        _row("true_aa", "L0_AA", 0, "h"),
        _row("cost_anchor", "L0_AA", 0, "h"),
        _row("true_aa", "L0_AA", 1, "h"),
    ])
    out = mod.split_layer_table(frame, layer="L0", scenario_id="L0_AA", protocol_hash="h")
    assert out["rep"].tolist() == [0, 1]
    assert set(out["block"]) == {"true_aa"}


def test_split_rejects_foreign_scenario(mod):
    frame = pd.DataFrame([_row("true_aa", "L0_AA", 0, "h"),
                          _row("true_aa", "L1_AA", 0, "h")])
    with pytest.raises(SystemExit) as excinfo:
        mod.split_layer_table(frame, layer="L0", scenario_id="L0_AA", protocol_hash="h")
    assert "非本层格" in str(excinfo.value)


def test_split_rejects_protocol_drift(mod):
    frame = pd.DataFrame([_row("true_aa", "L0_AA", 0, "other")])
    with pytest.raises(SystemExit) as excinfo:
        mod.split_layer_table(frame, layer="L0", scenario_id="L0_AA", protocol_hash="h")
    assert "protocol_config_hash" in str(excinfo.value)


def test_split_rejects_empty_true_aa(mod):
    frame = pd.DataFrame([_row("cost_anchor", "L0_AA", 0, "h")])
    with pytest.raises(SystemExit) as excinfo:
        mod.split_layer_table(frame, layer="L0", scenario_id="L0_AA", protocol_hash="h")
    assert "没有任何 true_aa" in str(excinfo.value)


def test_resume_picks_newest_table(mod, tmp_path):
    layer_runs = tmp_path / "layer_runs"
    layer_runs.mkdir()
    older = layer_runs / "L0_100000" / "aa_repetitions.csv"
    newer = layer_runs / "L0_200000" / "aa_repetitions.csv"
    other = layer_runs / "L1_300000" / "aa_repetitions.csv"
    for path, payload in ((older, "old"), (newer, "new"), (other, "x")):
        path.parent.mkdir(parents=True)
        path.write_text(payload, encoding="utf-8")
    import os
    import time

    os.utime(older, (time.time() - 100, time.time() - 100))
    os.utime(newer, (time.time(), time.time()))
    assert mod._resume_source(tmp_path, "L0") == newer
    assert mod._resume_source(tmp_path, "L2") is None


def test_merge_delegates_to_script_17(mod):
    assert mod.MERGE_SCRIPT.name == "17_merge_aa_layers.py"
    assert mod.MERGE_SCRIPT.is_file()
