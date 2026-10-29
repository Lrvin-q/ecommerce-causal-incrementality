"""40 号证据导出的替换契约：写失败不许动 DEST，成功不许删旧备份。

对应 G01 复评 R2-P2-2：旧写法先删备份、失败再还原，会在二次故障时用半写副本
覆盖完好副本，并可能用清理异常掩盖原始异常。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "40_export_g02_evidence.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("g02_export_40", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(dest: Path) -> None:
    dest.mkdir(parents=True)
    (dest / "old.txt").write_text("old", encoding="utf-8")


def test_failure_keeps_dest_and_original_exception(mod, tmp_path, monkeypatch):
    dest = tmp_path / "evidence"
    _seed(dest)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "DEST", dest)

    class Boom(RuntimeError):
        pass

    def explode(cells, recomputed):
        (Path(mod.DEST) / "partial.txt").write_text("partial", encoding="utf-8")
        raise Boom("write failed")

    monkeypatch.setattr(mod, "_write_evidence", explode)
    with pytest.raises(Boom, match="write failed"):
        mod.write_evidence([], None)
    assert (dest / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (dest / "partial.txt").exists()


def test_success_swaps_and_keeps_old_copy(mod, tmp_path, monkeypatch):
    dest = tmp_path / "evidence"
    _seed(dest)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "DEST", dest)

    def write(cells, recomputed):
        (Path(mod.DEST) / "coverage.json").write_text('{"ok": true}', encoding="utf-8")
        return {"ok": True}

    monkeypatch.setattr(mod, "_write_evidence", write)
    payload = mod.write_evidence([], None)
    assert payload == {"ok": True}
    assert (dest / "coverage.json").is_file()
    assert not (dest / "old.txt").exists()
    backups = list((tmp_path / "out").glob("g02_evidence_bak_*"))
    assert any((b / "old.txt").is_file() for b in backups), "旧目录必须留档而不是删除"


def test_success_refuses_unparseable_coverage(mod, tmp_path, monkeypatch):
    dest = tmp_path / "evidence"
    _seed(dest)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "DEST", dest)

    def write(cells, recomputed):
        (Path(mod.DEST) / "coverage.json").write_text("{not json", encoding="utf-8")
        return {}

    monkeypatch.setattr(mod, "_write_evidence", write)
    with pytest.raises(ValueError):
        mod.write_evidence([], None)
    assert (dest / "old.txt").read_text(encoding="utf-8") == "old"


def _full_cell(mod, tmp_path, monkeypatch, **overrides):
    """造一个 50 b 的完整格目录；默认是**正确**形状：验证 rep 固定为 0。"""
    import pandas as pd

    monkeypatch.setattr(mod, "RUN_ROOT", tmp_path)
    cell = "L0_P_main"
    cell_dir = tmp_path / cell
    cell_dir.mkdir(parents=True)
    (cell_dir / "run_state.json").write_text("{}", encoding="utf-8")
    n = mod.PER_CELL
    data = {
        "b": list(range(n)),
        "history_rep_id": [1_000_000 + i for i in range(n)],
        "validation_rep": [0] * n,
        "validation_frame_hash": ["f"] * n,
        "validation_arm_hash": ["a"] * n,
        "status": ["formal"] * n,
        "protocol_config_hash": ["p"] * n,
        "n_history": [200_000] * n,
        "n_validation": [5_000] * n,
        "retraining_bootstrap_total": [200] * n,
    }
    data.update(overrides)
    pd.DataFrame(data).to_csv(cell_dir / "repetitions.csv", index=False, encoding="utf-8-sig")
    return cell


def test_check_cell_accepts_fixed_validation_rep(mod, tmp_path, monkeypatch):
    # 设计上 50 个 b 共用 VALIDATION_REP=0：重复是要求，不能报成缺陷
    cell = _full_cell(mod, tmp_path, monkeypatch)
    _, problems = mod.check_cell(cell)
    assert problems == [], problems


def test_check_cell_rejects_drifting_validation_rep(mod, tmp_path, monkeypatch):
    cell = _full_cell(mod, tmp_path, monkeypatch, validation_rep=[0, 1] * 25)
    _, problems = mod.check_cell(cell)
    assert any("validation_rep 在 b 间不一致" in p for p in problems), problems


def test_check_cell_rejects_duplicate_history_rep(mod, tmp_path, monkeypatch):
    cell = _full_cell(mod, tmp_path, monkeypatch,
                      history_rep_id=[1_000_000] * mod.PER_CELL)
    _, problems = mod.check_cell(cell)
    assert any("history_rep_id 在 b 间重复" in p for p in problems), problems
