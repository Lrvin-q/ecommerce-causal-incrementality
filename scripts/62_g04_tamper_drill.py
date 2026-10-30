#!/usr/bin/env python
"""G04 失败→恢复演练：把正式矩阵的逐 rep 表抽到一个临时根，篡改一格后确认 41 号会拒，复原后重新通过。

只读正式产物：临时根只复制 ``repetitions.csv``（不碰 ``rep*`` 数据目录），篡改与复原都发生在
``out/scratch/`` 内。三步都必须符合预期，任一步不符即非零退出——"门禁会拒"不能靠口头。

用法::

    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/62_g04_tamper_drill.py
    # 演练根保留以便人工查看：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/62_g04_tamper_drill.py --keep
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
MATRIX = ROOT / "out" / "g03_formal"
FIXED = ROOT / "out" / "g02_fixed"
DRILL = ROOT / "out" / "scratch" / "g04_tamper_drill"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
CORE = {"L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"}
TIER2 = {
    "L0_Pi_heterogeneous_cost", "L0_zero_purchase_effect",
    "L1_heterogeneity_000", "L1_heterogeneity_150", "L1_signal_weak",
    "L1_misspec_omit_new_channel", "L1_mar_double", "L1_cost_prediction_under",
    "L2_n30000_p050", "L2_n100000_p050", "L2_drift_smooth",
    "L2_composition_shift", "L2_immature_negative_control",
    "L3_fixed_lt025", "L3_fixed_lt075", "L3_fixed_lt150",
    "L3_joint_lam000", "L3_joint_lam150", "L3_overlap_extreme",
    "L3_missing_confounders",
}
WANT = {**{c: 500 for c in CORE}, **{c: 30 for c in TIER2}}


def say(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def build_drill_root() -> list[str]:
    problems: list[str] = []
    if not (MATRIX / "shards").is_dir():
        return [f"{MATRIX.relative_to(ROOT)}/shards 不存在（Phase 2 未 merge，先别演练）"]
    summary = MATRIX / "run_summary.json"
    if not summary.is_file():
        return [f"{MATRIX.relative_to(ROOT)}/run_summary.json 不存在（41 的准入字段无从复制）"]
    if DRILL.exists():
        shutil.rmtree(DRILL)
    DRILL.mkdir(parents=True)
    shutil.copyfile(summary, DRILL / "run_summary.json")
    seen: dict[str, int] = {}
    for shard in sorted((MATRIX / "shards").iterdir()) if (MATRIX / "shards").is_dir() else []:
        if not shard.is_dir():
            continue
        for cell_dir in sorted(p for p in shard.iterdir() if p.is_dir()):
            formal = cell_dir / "repetitions.csv"
            if not formal.is_file():
                problems.append(f"{shard.name}/{cell_dir.name}: 缺 repetitions.csv")
                continue
            target = DRILL / "shards" / shard.name / cell_dir.name / "repetitions.csv"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(formal, target)
            rows = max(0, len(formal.read_text(encoding="utf-8-sig").splitlines()) - 1)
            seen[cell_dir.name] = seen.get(cell_dir.name, 0) + rows
    for cell, want in sorted(WANT.items()):
        if seen.get(cell, 0) != want:
            problems.append(f"{cell}: 演练根 rows={seen.get(cell, 0)} != {want}")
    extra = sorted(set(seen) - set(WANT))
    if extra:
        problems.append(f"多出未注册格：{extra}")
    return problems


def run41() -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "scripts/41_export_g03_evidence.py", "--check",
         "--matrix-root", str(DRILL), "--fixed-root", str(FIXED)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def tail(text: str, n: int = 6) -> str:
    return "\n".join(text.splitlines()[-n:])


def main() -> int:
    parser = argparse.ArgumentParser(description="G04 失败→恢复演练（只读正式矩阵）")
    parser.add_argument("--keep", action="store_true", help="保留演练根")
    args = parser.parse_args()

    problems = build_drill_root()
    if problems:
        say("ABORT", "演练根无法构建：")
        for line in problems[:10]:
            print("  -", line)
        return 3
    say("OK ", f"演练根已建：{DRILL.relative_to(ROOT)}（24 格逐 rep 表副本）")

    rc, out = run41()
    if rc != 0:
        say("FAIL", f"基线本应 EXIT=0，实得 {rc}：")
        print(tail(out))
        return 4
    say("OK ", "基线 41 --check EXIT=0")

    target = DRILL / "shards" / "L0_P_main_s0000" / "L0_P_main" / "repetitions.csv"
    backup = target.read_bytes()
    lines = target.read_text(encoding="utf-8-sig").splitlines()
    header, rows = lines[0], lines[1:]
    original = rows[0]
    rows[0] = rows[1]
    target.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    say("INFO", f"注入篡改：{target.relative_to(DRILL)} 两行 rep 相同（原首行 {original.split(',')[0]}）")

    try:
        rc, out = run41()
        if rc == 0:
            say("FAIL", "篡改后 41 仍判通过——门禁未拦住")
            return 5
        if "重叠" not in out and "rep" not in out:
            say("FAIL", f"41 拒了（EXIT={rc}）但输出未指向 rep 重叠：")
            print(tail(out))
            return 6
        say("OK ", f"篡改被拒：41 EXIT={rc}（{tail(out, 2)}）")

        target.write_bytes(backup)
        rc, out = run41()
        if rc != 0:
            say("FAIL", f"复原后 41 仍 EXIT={rc}：")
            print(tail(out))
            return 7
    finally:
        if not args.keep:
            shutil.rmtree(DRILL, ignore_errors=True)

    say("PASS", "失败被发现、复原后重新通过（G04 演练完成）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
