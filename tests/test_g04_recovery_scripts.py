"""G04 恢复链脚本的夹具：66 的 6/6 顺序、62 的拒因判据（G04 C4/P3-3、P3-4）。"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "drill62", ROOT / "scripts" / "62_g04_tamper_drill.py")
drill62 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drill62)

BASH = shutil.which("bash")


def _sandbox(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "out" / "g03_logs").mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts" / "66_g03_refresh_evidence_logs.sh",
                    root / "scripts" / "66_g03_refresh_evidence_logs.sh")
    log = root / "out" / "g03_logs" / "finalize.log"
    status = root / "out" / "g03_logs" / "finalize.status"
    out = root / "out" / "g03_logs" / "post_finalize_export.status"
    status.write_text("OK: G03 finalize 完成 2026-10-31 19:48:27\n", encoding="utf-8")
    log.write_text("", encoding="utf-8")
    return root, log, status, out


def _run66(root: Path, log: Path, status: Path, out: Path,
           export: Path | None) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "G66_PY": sys.executable,
        "G66_EXPORT": str(export) if export else str(root / "scripts" / "missing.py"),
        "G66_LOG": str(log),
        "G66_STATUS": str(status),
        "G66_OUT": str(out),
    }
    return subprocess.run(
        [BASH, str(root / "scripts" / "66_g03_refresh_evidence_logs.sh")],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )


@pytest.mark.skipif(BASH is None, reason="需要 Git Bash")
def test_66_failed_export_does_not_write_6_of_6(tmp_path: Path):
    root, log, status, out = _sandbox(tmp_path)
    proc = _run66(root, log, status, out, export=None)
    assert proc.returncode != 0
    text = log.read_text(encoding="utf-8")
    assert "6/6 收尾后重导出" not in text
    assert "6/6 FAILED" in text
    assert "post_finalize_export_exit=0" not in out.read_text(encoding="utf-8")


@pytest.mark.skipif(BASH is None, reason="需要 Git Bash")
def test_66_success_writes_6_of_6_once(tmp_path: Path):
    root, log, status, out = _sandbox(tmp_path)
    ok = root / "scripts" / "ok.py"
    ok.write_text("raise SystemExit(0)\n", encoding="utf-8")
    first = _run66(root, log, status, out, export=ok)
    second = _run66(root, log, status, out, export=ok)
    assert first.returncode == 0 and second.returncode == 0
    assert log.read_text(encoding="utf-8").count("6/6 收尾后重导出") == 1
    assert out.read_text(encoding="utf-8").strip() == "post_finalize_export_exit=0"


@pytest.mark.skipif(BASH is None, reason="需要 Git Bash")
def test_66_refuses_without_finalize_ok(tmp_path: Path):
    root, log, status, out = _sandbox(tmp_path)
    status.write_text("check_exit=0\n", encoding="utf-8")
    proc = _run66(root, log, status, out, export=None)
    assert proc.returncode == 3
    assert "ABORT" in out.read_text(encoding="utf-8")


def test_62_judge_rejects_untouched_success():
    assert drill62.judge_tamper(0, "校验全过") is not None


def test_62_judge_rejects_unrelated_failure():
    out = "  - ('L0_P_main', 'ate_any_refund_30d')/sd: 复算 1 != 汇总 2"
    assert drill62.judge_tamper(2, out) is not None


def test_62_judge_accepts_rep_overlap():
    assert drill62.judge_tamper(2, "L0_P_main: 分片间 rep 重叠 [1]") is None
