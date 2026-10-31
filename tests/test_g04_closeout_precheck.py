"""49 号 G04 收尾体检的判据测试：覆盖计数、状态标记、overlay 身份、git 洁净、裁决码。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "g04_precheck", ROOT / "scripts" / "49_g04_closeout_precheck.py")
pre = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pre)

CORE = ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"]
TIER2 = [f"T{i:02d}_cell" for i in range(1, 21)]


@pytest.fixture(autouse=True)
def _reset():
    pre.problems.clear()
    pre.pending.clear()
    yield
    pre.problems.clear()
    pre.pending.clear()


def _reps(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["rep\n"] + [f"{i}\n" for i in range(rows)]
    path.write_text("".join(lines), encoding="utf-8")


def _final(tmp_path: Path, *, core_rows: int = 500, tier2_rows: int = 30,
           drop: str | None = None, skip_formal: str | None = None) -> None:
    for cell in CORE + TIER2:
        if cell == drop:
            continue
        rows = core_rows if cell in CORE else tier2_rows
        if cell == skip_formal:
            _reps(tmp_path / "out/g03_formal/_final" / cell
                  / "repetitions_provisional.csv", rows)
            continue
        _reps(tmp_path / "out/g03_formal/_final" / cell / "repetitions.csv", rows)


def test_complete_matrix_is_clean(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _final(tmp_path)
    pre.check_g03_rows()
    assert pre.problems == [] and pre.pending == []


def test_missing_cell_is_pending(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _final(tmp_path, drop="T05_cell")
    pre.check_g03_rows()
    assert any("格数 23/24" in item for item in pre.pending)


def test_short_cell_is_pending(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _final(tmp_path, tier2_rows=29)
    pre.check_g03_rows()
    assert any("T01_cell 29/30" in item for item in pre.pending)


def test_provisional_only_cell_is_pending(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _final(tmp_path, skip_formal="L2_n200000_p050")
    pre.check_g03_rows()
    assert any("L2_n200000_p050 无 repetitions.csv" in item for item in pre.pending)


def test_absent_final_is_pending(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    pre.check_g03_rows()
    assert pre.pending == ["g03 _final 尚未生成"]


def test_overlay_hash_mismatch_is_problem(tmp_path: Path, monkeypatch):
    target = tmp_path / "overlay.yaml"
    target.write_bytes(b"not the frozen bytes")
    monkeypatch.setattr(pre, "OVERLAY", target)
    pre.check_overlay()
    assert any("overlay sha256" in item for item in pre.problems)


def test_active_abort_is_problem_but_retired_status_is_info(tmp_path: Path, monkeypatch):
    """19:36 拆 Phase1/Phase2 后，g03_post.status 已退役（§2.6），ABORT 只报 INFO；
    现行门仍是 g02_post / phase1 / phase2，ABORT 必须判 problem。"""
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    (tmp_path / "out/g03_logs").mkdir(parents=True)
    (tmp_path / "out/g02_logs").mkdir(parents=True)
    (tmp_path / "out/g03_logs/post.status").write_text(
        "ABORT: _final incomplete\n", encoding="utf-8")
    (tmp_path / "out/g02_logs/post.status").write_text(
        "ABORT: retrain incomplete\n", encoding="utf-8")
    pre.check_statuses()
    assert not any("g03_post.status" in item for item in pre.problems)
    assert any("g02_post.status 失败标记" in item for item in pre.problems)
    assert any(item == "phase1 未完成" for item in pre.pending)


def test_git_dirty_output_is_problem(monkeypatch):
    monkeypatch.setattr(pre.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout=" M src/causal_growth/data/v3_pipeline.py\n", returncode=0))
    pre.check_git()
    assert any("受绑路径有未提交改动" in item for item in pre.problems)


def test_verdict_codes():
    assert pre.verdict() == 0
    pre.pending.append("还在跑")
    assert pre.verdict() == 2
    pre.problems.append("漂移")
    assert pre.verdict() == 3


def _write_status(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_finalize_missing_is_problem(tmp_path: Path, monkeypatch):
    """C1：G04 收尾完成后 finalize.status 缺失必须判 problem，不能只报 pending。"""
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    pre.check_statuses()
    assert any("finalize.status 缺失" in item for item in pre.problems)


def test_finalize_abort_is_problem(tmp_path: Path, monkeypatch):
    """C1：finalize.status 存在 ABORT 时必须判 problem。"""
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _write_status(tmp_path, "out/g03_logs/finalize.status",
                  "check_exit=0\ndrill_exit=1\nABORT: export failed\n")
    pre.check_statuses()
    assert any("finalize.status" in item and "非零退出" in item for item in pre.problems)


def test_finalize_requires_all_six_zero_and_ok(tmp_path: Path, monkeypatch):
    """C1：六步缺一或没有完成行都算不完整。"""
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _write_status(tmp_path, "out/g03_logs/finalize.status",
                  "check_exit=0\ndrill_exit=0\nexport_exit=0\n"
                  "register_dry_run_exit=0\nreport48_exit=0\nregister_exit=0\n")
    pre.check_statuses()
    assert any("finalize.status 不完整" in item for item in pre.problems)


def test_finalize_all_zero_with_ok_is_clean(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _write_status(tmp_path, "out/g03_logs/finalize.status",
                  "check_exit=0\ndrill_exit=0\nexport_exit=0\n"
                  "register_dry_run_exit=0\nreport48_exit=0\nregister_exit=0\n"
                  "OK: G03 finalize 完成 2026-10-31 19:48:27\n")
    pre.check_statuses()
    assert not any("finalize" in item for item in pre.problems)


def test_ok_with_nonzero_exit_is_problem(tmp_path: Path, monkeypatch):
    """P2-2：'旧 OK + 新非零 exit' 不能被 OK 覆盖。"""
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _write_status(tmp_path, "out/g03_logs/phase2.status",
                  "tier2_exit=1\nOK: forged success line\n")
    pre.check_statuses()
    assert any("phase2.status 非零退出" in item for item in pre.problems)


def test_nonzero_without_ok_is_problem(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pre, "ROOT", tmp_path)
    _write_status(tmp_path, "out/g03_logs/phase2.status", "tier2_exit=2\n")
    pre.check_statuses()
    assert any("phase2.status 非零退出" in item for item in pre.problems)


def test_register_expect_complete_nonzero_is_problem(monkeypatch):
    """C1：顶层索引少一条时 33 返回 5，49 必须判 problem 而不是继续 READY。"""
    monkeypatch.setattr(pre, "_run", lambda *a, **k: SimpleNamespace(
        returncode=5, stdout="expect-complete：拒绝判完备", stderr=""))
    pre.check_register(True)
    assert any("33 --dry-run --expect-complete EXIT=5" in item for item in pre.problems)


def test_register_expect_complete_zero_is_clean(monkeypatch):
    monkeypatch.setattr(pre, "_run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="候选身份类文件 2 个：新增 0", stderr=""))
    pre.check_register(True)
    assert pre.problems == []
