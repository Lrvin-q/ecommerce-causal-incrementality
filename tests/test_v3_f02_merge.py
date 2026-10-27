"""F02 正式合并脚本的门禁：分片 summary 与 rep 目录/聚合结果必须一致。

合成 shard 用 :mod:`test_v3_f02_formal` 的 rep 构造器，避免两套假数据漂移。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "30_merge_f02_formal.py"
FIXTURES = ROOT / "tests" / "test_v3_f02_formal.py"

_APPROVAL = "TEST-APPROVAL-01"
_POLICY = "greedy_incremental_profit_per_cost"
_SOURCE_HASHES = {"src/causal_growth/evaluation/v3_f02.py": "deadbeef"}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def merge():
    return _load(SCRIPT, "merge_f02_formal")


@pytest.fixture(scope="module")
def fixture():
    return _load(FIXTURES, "f02_formal_fixtures")


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _write_shard(
    root: Path,
    rep_ids: list[int],
    fixture,
    *,
    config_hash: str = "cfg-1",
    completed: list[int] | None = None,
    failures: list[dict] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rep_id in rep_ids:
        fixture._write_rep(
            root,
            rep_id,
            config_hash=config_hash,
            policy=_POLICY,
            rep_offset=rep_id,
        )
    summary = {
        "phase": "F02_formal_shard",
        "status": "formal",
        "formal_approval": _APPROVAL,
        "scenario": "L1_main",
        "n_per_rep": 30,
        "policy": _POLICY,
        "models": None,
        "time_mode": "convert_7d",
        "config_hash": config_hash,
        "source_hashes": dict(_SOURCE_HASHES),
        "source_hashes_sha256": _digest(_SOURCE_HASHES),
        "rep_ids_requested": list(rep_ids),
        "to_run": list(rep_ids),
        "skipped_rep_ids": [],
        "completed_rep_ids": list(rep_ids) if completed is None else completed,
        "reps": [],
        "failures": failures or [],
        "started_at": "2026-10-27T21:00:00+08:00",
        "finished_at": "2026-10-27T21:01:00+08:00",
    }
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return root


def test_read_shard_summary_rejects_wrong_phase_status_and_failures(
    tmp_path: Path, merge, fixture
) -> None:
    shard = _write_shard(tmp_path / "wrong_phase", [0], fixture)
    summary = json.loads((shard / "summary.json").read_text(encoding="utf-8"))
    summary["phase"] = "something_else"
    (shard / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="F02 分片 summary"):
        merge._read_shard_summary(shard)

    shard = _write_shard(tmp_path / "provisional", [0], fixture)
    summary = json.loads((shard / "summary.json").read_text(encoding="utf-8"))
    summary["status"] = "engineering"
    (shard / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="formal 分片"):
        merge._read_shard_summary(shard)

    shard = _write_shard(
        tmp_path / "failed", [0], fixture,
        failures=[{"rep_id": 0, "error": "boom"}],
    )
    with pytest.raises(ValueError, match="失败 rep"):
        merge._read_shard_summary(shard)


def test_merge_rejects_summary_rep_mismatch(tmp_path: Path, merge, fixture) -> None:
    shard = _write_shard(tmp_path / "shard0", [0, 1], fixture, completed=[0])
    with pytest.raises(ValueError, match="completed_rep_ids"):
        merge.main([
            "--shard-root", str(shard),
            "--expected-reps", "2",
            "--tables-dir", str(tmp_path / "tables"),
        ])


def test_merge_rejects_summary_config_mismatch(tmp_path: Path, merge, fixture) -> None:
    shard = _write_shard(tmp_path / "shard0", [0, 1], fixture, config_hash="cfg-1")
    summary = json.loads((shard / "summary.json").read_text(encoding="utf-8"))
    summary["config_hash"] = "cfg-2"
    (shard / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="config_hash 与 rep 清单不一致"):
        merge.main([
            "--shard-root", str(shard),
            "--expected-reps", "2",
            "--tables-dir", str(tmp_path / "tables"),
        ])


def test_merge_rejects_shard_without_reps(tmp_path: Path, merge, fixture) -> None:
    shard = _write_shard(tmp_path / "empty", [], fixture)
    with pytest.raises(ValueError, match="没有任何 rep 目录"):
        merge.main([
            "--shard-root", str(shard),
            "--expected-reps", "0",
            "--tables-dir", str(tmp_path / "tables"),
        ])


def test_merge_writes_tables_for_consistent_shards(
    tmp_path: Path, merge, fixture
) -> None:
    shard0 = _write_shard(tmp_path / "shard0", [0], fixture)
    shard1 = _write_shard(tmp_path / "shard1", [1], fixture)
    tables = tmp_path / "tables"
    code = merge.main([
        "--shard-root", str(shard0),
        "--shard-root", str(shard1),
        "--expected-reps", "2",
        "--tables-dir", str(tables),
    ])
    assert code == 0

    assert (tables / "v3_phase_F02_formal_per_rep_claims.csv").is_file()
    assert (tables / "v3_phase_F02_formal_spend.csv").is_file()
    summary = json.loads(
        (tables / "v3_phase_F02_formal_summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "formal_r"
    assert summary["n_reps"] == 2
    assert summary["policy"] == _POLICY
    assert sorted(summary["rep_ids"]) == [0, 1]

    import pandas as pd

    per_rep = pd.read_csv(tables / "v3_phase_F02_formal_per_rep_claims.csv", encoding="utf-8-sig")
    assert len(per_rep) == 4
    assert sorted(per_rep["rep_id"].unique().tolist()) == [0, 1]
