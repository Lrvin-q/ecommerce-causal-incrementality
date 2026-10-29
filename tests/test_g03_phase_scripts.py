"""50/51 号 Phase 启动脚本的契约：行尾、语法、格名来自 scenarios、硬门不可删。"""
from __future__ import annotations

import functools
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PHASE1 = ROOT / "scripts" / "50_g03_phase1_core.sh"
PHASE2 = ROOT / "scripts" / "51_g03_phase2.sh"
SCENARIOS = ROOT / "configs" / "v3" / "scenarios.yaml"


@pytest.mark.parametrize("script", [PHASE1, PHASE2], ids=["phase1", "phase2"])
def test_script_is_lf_only(script: Path):
    assert b"\r\n" not in script.read_bytes(), "CRLF 会让 bash 报 bad interpreter"


@functools.lru_cache(maxsize=1)
def _bash() -> str | None:
    """Windows 上 `which bash` 可能拿到 WSL 存根（找不到 /bin/bash），要逐候选试跑。"""
    for cand in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if not cand or not Path(cand).is_file():
            continue
        probe = subprocess.run([cand, "-c", "true"], capture_output=True, text=True)
        if probe.returncode == 0:
            return cand
    return None


@pytest.mark.parametrize("script", [PHASE1, PHASE2], ids=["phase1", "phase2"])
def test_script_syntax_ok(script: Path):
    bash = _bash()
    if bash is None:
        pytest.skip("没有可用的 GNU bash")
    assert subprocess.run([bash, "-n", str(script)]).returncode == 0


def _tier2() -> list[str]:
    text = PHASE2.read_text(encoding="utf-8")
    return re.search(r'^TIER2="([^"]+)"', text, re.M).group(1).split()


def test_tier2_cells_are_registered_scenarios():
    registered = set(re.findall(r"^- id: (\S+)$", SCENARIOS.read_text(encoding="utf-8"),
                                re.M))
    cells = _tier2()
    assert len(cells) == 20 and len(set(cells)) == 20
    assert set(cells) <= registered, f"未注册格名 {sorted(set(cells) - registered)}"
    core = {"L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"}
    assert not set(cells) & core, "Tier2 列表混进了 core 格"


@pytest.mark.parametrize(
    "needle",
    ["Phase 1 未完成", "已存在，拒绝重复写", "final_check_exit",
     "ABORT: _final incomplete", "exit 9", "OK: G03 Phase2 完成"],
    ids=["phase1-gate", "outroot-gate", "final-check", "final-abort", "final-exit", "ok"],
)
def test_phase2_hard_gates_present(needle: str):
    assert needle in PHASE2.read_text(encoding="utf-8")
