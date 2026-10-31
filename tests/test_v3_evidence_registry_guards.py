"""证据登记/导出两道新校验的反例夹具（AGENTS §12.7，G03 复核 N2/N9）。

- ``scripts/33_register_evidence_top.py``：目录级全表逐条核 sha/bytes、拒绝重复 target；
  仓外绝对路径（``in_repository:false``）必须按原路径核验，不能映射成 ``evidence_dir/<basename>``。
- ``scripts/41_export_g03_evidence.py``：导出后自检拒绝 target 重名、缺失、哈希不符、数量不符。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


top_reg = _load("top_reg_guards", "scripts/33_register_evidence_top.py")
export41 = _load("export41_guards", "scripts/41_export_g03_evidence.py")


def _blob(path: Path, data: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _dir_record(local: Path, root: Path, rel: str) -> dict:
    body = _blob(local, b"a,b\n1,2\n")
    return {"target": f"{root.name}/g03_fixture/{rel}",
            "kind": "g03_repetitions_shard", **body}


def _abs_record(path: Path, data: bytes) -> dict:
    body = _blob(path, data)
    return {
        "target": str(path),
        "kind": "f01_masks_derivable",
        "in_repository": False,
        **body,
    }


def _coverage(records: list[dict]) -> dict:
    return {"kind": "fixture", "files": records}


@pytest.fixture()
def ev_root(tmp_path: Path) -> Path:
    root = tmp_path / "ev"
    (root / "g03_fixture").mkdir(parents=True)
    return root


def _write_cov(root: Path, records: list[dict]) -> None:
    (root / "g03_fixture" / "coverage.json").write_text(
        json.dumps(_coverage(records), ensure_ascii=False), encoding="utf-8")


def _ok_record(root: Path) -> dict:
    return _dir_record(root / "g03_fixture" / "shard_a.csv", root, "shard_a.csv")


def test_clean_dir_passes(ev_root: Path):
    _write_cov(ev_root, [_ok_record(ev_root)])
    candidates, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert bad == []
    assert candidates == []  # 非身份类文件只核验、不提升


def test_tampered_file_fails(ev_root: Path):
    record = _ok_record(ev_root)
    _write_cov(ev_root, [record])
    (ev_root / "g03_fixture" / "shard_a.csv").write_bytes(b"tampered")
    _, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert any("sha256/bytes 与目录级 coverage.json 不符" in item for item in bad)


def test_missing_file_fails(ev_root: Path):
    record = _ok_record(ev_root)
    _write_cov(ev_root, [record])
    (ev_root / "g03_fixture" / "shard_a.csv").unlink()
    _, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert any("文件缺失" in item for item in bad)


def test_duplicate_target_fails(ev_root: Path):
    record = _ok_record(ev_root)
    _write_cov(ev_root, [record, dict(record)])
    _, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert any("同一 target 被 2 条记录登记" in item for item in bad)


def test_unregistered_identity_file_fails(ev_root: Path):
    _write_cov(ev_root, [_ok_record(ev_root)])
    (ev_root / "g03_fixture" / "snapshot_binding.json").write_text("{}", encoding="utf-8")
    _, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert any("未登记" in item and "snapshot_binding.json" in item for item in bad)


def test_unreadable_record_fails(ev_root: Path):
    _write_cov(ev_root, [{"target": "g03_fixture/x.csv"}])
    _, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert any("files[0] 缺 sha256/bytes" in item for item in bad)


def test_outside_absolute_target_with_correct_sha_passes(ev_root: Path, tmp_path: Path):
    """N2 回归：f01_ope 的 in_repository:false 记录真实存在，不得误报"文件缺失"。"""
    outside = tmp_path / "out_run" / "policy_masks_long.csv.gz"
    _write_cov(ev_root, [_abs_record(outside, b"gz-bytes")])
    candidates, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert bad == []
    assert candidates == []


def test_outside_absolute_target_with_wrong_sha_fails(ev_root: Path, tmp_path: Path):
    outside = tmp_path / "out_run" / "policy_masks_long.csv.gz"
    _write_cov(ev_root, [_abs_record(outside, b"gz-bytes")])
    outside.write_bytes(b"tampered")
    _, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert any("sha256/bytes 与目录级 coverage.json 不符" in item for item in bad)


def test_outside_absolute_identity_record_fails(ev_root: Path, tmp_path: Path):
    outside = tmp_path / "out_run" / "meta.json"
    _write_cov(ev_root, [_abs_record(outside, b"{}")])
    _, bad = top_reg.collect(["g03_fixture"], ev_root)
    assert any("身份类记录在仓外绝对路径" in item for item in bad)


def test_cli_refuses_fixture_root_with_real_top(ev_root: Path, tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(top_reg, "ROOT", tmp_path)
    monkeypatch.setattr(top_reg, "REAL_EVIDENCE", tmp_path / "ev_real")
    monkeypatch.setattr(top_reg, "TOP", tmp_path / "top_real.json")
    monkeypatch.setattr(sys, "argv", ["33", "--evidence-root", "ev"])
    with pytest.raises(SystemExit, match="拒绝写盘"):
        top_reg.main()


def test_cli_default_all_dirs_no_longer_blocked_by_outside_records(
        ev_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """N2 回归的 CLI 层：默认扫描（不带 --dirs）也要 rc=0。"""
    outside = tmp_path / "out_run" / "policy_masks_long.csv.gz"
    _write_cov(ev_root, [_abs_record(outside, b"gz-bytes")])
    top = ev_root / "top.json"
    top.write_text(json.dumps({"records": [], "total_bytes": 0}), encoding="utf-8")
    monkeypatch.setattr(top_reg, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "33", "--evidence-root", "ev", "--top", "ev/top.json", "--dry-run",
    ])
    assert top_reg.main() == 0


# --- 41 导出后自检 ---------------------------------------------------------

def _dest(tmp_path: Path) -> tuple[Path, Path, Path]:
    dest = tmp_path / "ev" / "g03_formal"
    dest.mkdir(parents=True)
    return dest, Path("ev/g03_formal"), dest / "x.csv"


def _record(path: Path, target: str, data: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"target": target, "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def test_41_self_check_clean_passes(tmp_path: Path):
    dest, prefix, path = _dest(tmp_path)
    rec = _record(path, "ev/g03_formal/x.csv", b"1\n")
    export41._post_export_self_check([rec], dest, prefix)


def test_41_self_check_duplicate_target_fails(tmp_path: Path):
    dest, prefix, path = _dest(tmp_path)
    rec = _record(path, "ev/g03_formal/x.csv", b"1\n")
    with pytest.raises(RuntimeError, match="导出目标重名"):
        export41._post_export_self_check([rec, dict(rec)], dest, prefix)


def test_41_self_check_missing_file_fails(tmp_path: Path):
    dest, prefix, path = _dest(tmp_path)
    rec = _record(path, "ev/g03_formal/x.csv", b"1\n")
    path.unlink()
    with pytest.raises(RuntimeError, match="不在 staging"):
        export41._post_export_self_check([rec], dest, prefix)


def test_41_self_check_wrong_hash_fails(tmp_path: Path):
    dest, prefix, path = _dest(tmp_path)
    rec = _record(path, "ev/g03_formal/x.csv", b"1\n")
    path.write_bytes(b"2\n")
    with pytest.raises(RuntimeError, match="sha256/bytes 与记录不符"):
        export41._post_export_self_check([rec], dest, prefix)


def test_41_self_check_extra_file_fails(tmp_path: Path):
    dest, prefix, path = _dest(tmp_path)
    rec = _record(path, "ev/g03_formal/x.csv", b"1\n")
    (dest / "stray.csv").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="staging 有 2 个文件，记录 1 条"):
        export41._post_export_self_check([rec], dest, prefix)
