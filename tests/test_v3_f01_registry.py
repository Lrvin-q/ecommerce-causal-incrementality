"""F01 顶层证据登记表刷新：既要刷新自身前缀，也要全表复算并拒绝篡改。

对应 AGENTS §12.1/§12.3：``out/`` 不入库，所以顶层 ``outputs/evidence/coverage.json``
是别人复算的入口；它曾经因为"只清自己前缀、从不复算全表"而与磁盘长期不一致
（旧 freeze_id、旧 source、11 条指向已消失文件的记录）。这里把那些篡改用例钉住。
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "31_f01_ope.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("f01_ope_script", SCRIPT)
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_bytes(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """搭一个最小仓库：一条他前缀记录 + 一条过期 F01 记录 + 一条已消失记录。"""
    root = tmp_path.resolve()
    run = root / "out" / "f01_run_x"
    ev = root / "outputs" / "evidence" / "f01_ope"
    aa = root / "outputs" / "evidence" / "aa"
    for path in (run, ev, aa):
        path.mkdir(parents=True)

    freeze_payload = {"freeze_id": "new-freeze-id", "created_at": "2026-10-28T02:57:03+08:00"}
    meta_payload = {"git_commit": "abc123", "formal_repetitions": 0}
    (run / "freeze.json").write_text(json.dumps(freeze_payload), encoding="utf-8")
    (run / "meta.json").write_text(json.dumps(meta_payload), encoding="utf-8")

    # 导出副本与运行产物一致（这是 _export_evidence 的真实行为）；
    # **过期的是顶层索引里的记录**：旧内容的 sha、旧 freeze_id、指向旧 run 目录的 source。
    shutil.copy2(run / "freeze.json", ev / "freeze.json")
    shutil.copy2(run / "meta.json", ev / "meta.json")
    previous_freeze = json.dumps({"freeze_id": "old-freeze-id"}).encode("utf-8")

    other = aa / "manifest_L1.json"
    other.write_text(json.dumps({"ok": True}), encoding="utf-8")

    registry = {
        "source_label": "test",
        "records": [
            {
                "kind": "aa_manifest",
                "source": "out/aa/manifest_L1.json",
                "target": "outputs/evidence/aa/manifest_L1.json",
                "bytes": other.stat().st_size,
                "sha256": _sha(other),
                "note": "别的前缀，必须原样保留",
            },
            {
                "kind": "f01_freeze",
                "source": "out/f01_ope/freeze.json",
                "target": "outputs/evidence/f01_ope/freeze.json",
                "bytes": len(previous_freeze),
                "sha256": _sha_bytes(previous_freeze),
                "freeze_id": "old-freeze-id",
                "note": "F01 冻结清单",
            },
            {
                "kind": "f01_gone",
                "source": "out/f01_ope/gone.csv",
                "target": "outputs/evidence/f01_ope/gone.csv",
                "bytes": 10,
                "sha256": "0" * 64,
            },
        ],
        "total_bytes": 999_999,
    }
    top = root / "outputs" / "evidence" / "coverage.json"
    top.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

    module = _load_module()
    monkeypatch.setattr(module, "ROOT", root)
    return {
        "module": module,
        "root": root,
        "target": ev,
        "freeze": run / "freeze.json",
        "meta": run / "meta.json",
        "top": top,
        "other": other,
    }


def _refresh(repo) -> dict:
    repo["module"]._refresh_top_registry(
        repo["target"], freeze_path=repo["freeze"], meta_path=repo["meta"]
    )
    return json.loads(repo["top"].read_text(encoding="utf-8"))


def test_refresh_replaces_own_prefix_and_keeps_others(repo):
    top = _refresh(repo)
    targets = [record["target"] for record in top["records"]]
    assert targets == [
        "outputs/evidence/aa/manifest_L1.json",
        "outputs/evidence/f01_ope/freeze.json",
        "outputs/evidence/f01_ope/meta.json",
    ], "他前缀记录必须原位保留，已消失记录必须被清掉"

    freeze = next(r for r in top["records"] if r["kind"] == "f01_freeze")
    assert freeze["freeze_id"] == "new-freeze-id"
    assert freeze["created_at_in_file"] == "2026-10-28T02:57:03+08:00"
    assert freeze["source"] == "out/f01_run_x/freeze.json", "source 必须指向本次运行产物"
    assert freeze["note"] == "F01 冻结清单", "刷新不得丢掉已有说明"
    assert freeze["sha256"] == _sha(repo["target"] / "freeze.json")

    assert top["total_bytes"] == sum(int(r["bytes"]) for r in top["records"])
    assert top["total_bytes"] != 999_999


def test_refresh_verifies_every_record_not_only_its_own(repo):
    top = json.loads(repo["top"].read_text(encoding="utf-8"))
    top["records"][0]["sha256"] = "f" * 64
    repo["top"].write_text(json.dumps(top, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="全表复算"):
        _refresh(repo)


def test_refresh_rejects_missing_file_anywhere_in_table(repo):
    repo["other"].unlink()
    with pytest.raises(RuntimeError, match="文件缺失"):
        _refresh(repo)


def test_refresh_rejects_stale_copy_of_this_run(repo):
    (repo["target"] / "freeze.json").write_text(json.dumps({"freeze_id": "别的"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="证据副本与运行产物不一致"):
        _refresh(repo)


def test_refresh_fails_loud_when_registry_absent(repo):
    repo["top"].unlink()
    with pytest.raises(FileNotFoundError, match="顶层证据登记表缺失"):
        _refresh(repo)
