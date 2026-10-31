#!/usr/bin/env python
"""G04 收尾只读体检：状态文件、覆盖计数、源码哈希、overlay 身份、git 洁净。

只读；不写任何产物。--with-check 追加跑 40/41 的 --check，--with-register 跑 33 --dry-run，
--with-claims 跑 42 数字门禁。
退出码：0=READY；2=仍有未完成项；3=有不一致（必须人工处理）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
OVERLAY = ROOT / "configs" / "budget" / "g02_bootstrap_overlay.yaml"
OVERLAY_SHA = "c58d5a905ea75de5f67cb7b5e9e8d3eae85615bb8009d6b49ebb0bb329ec810b"
CORE = ["L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"]
CORE_R, TIER2_R = 500, 30
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

problems: list[str] = []
pending: list[str] = []


def say(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def check_statuses() -> None:
    """G03 于 19:36 改拆 Phase1/Phase2（run registry §2.6），旧链与旧看护已退役：
    只对现行三个状态文件判门，旧文件仅报告，不参与 READY 判定。"""
    for name, path in (("g02_post", ROOT / "out/g02_logs/post.status"),
                       ("phase1", ROOT / "out/g03_logs/phase1.status"),
                       ("phase2", ROOT / "out/g03_logs/phase2.status")):
        text = read(path)
        bad_exit = [line.strip() for line in text.splitlines()
                    if re.fullmatch(r"[a-z0-9_]+_exit=[1-9]\d*", line.strip())]
        if "OK:" in text:
            say("OK ", f"{name}.status 含 OK：{text.strip().splitlines()[-1][:80]}")
        elif bad_exit:
            problems.append(f"{name}.status 非零退出：{bad_exit[:4]}")
            say("FAIL", f"{name}.status 非零退出 {bad_exit[:4]}")
        elif any(token in text for token in ("STOP", "TIMEOUT", "STALL", "FAIL", "ABORT")):
            problems.append(f"{name}.status 失败标记：{text.strip()[:160]}")
            say("FAIL", f"{name}.status 失败标记")
        else:
            pending.append(f"{name} 未完成")
            say("WAIT", f"{name}.status 尚无 OK（当前：{text.strip()[:60] or '空'}）")
    for name, path in (("chain", ROOT / "out/g03_logs/chain.status"),
                       ("g03_post", ROOT / "out/g03_logs/post.status")):
        text = read(path).strip()
        say("INFO", f"{name}.status 已退役（§2.6），不参与判定："
                    f"{text.splitlines()[-1][:60] if text else '缺失'}")


def check_g02_rows() -> None:
    for cell in CORE:
        path = ROOT / "out/g02_retrain" / cell / "repetitions.csv"
        rows = max(0, len(read(path).splitlines()) - 1) if path.is_file() else 0
        if rows == 50:
            say("OK ", f"g02 {cell} rows=50")
        elif rows > 50:
            problems.append(f"g02 {cell} rows={rows} > 50")
        else:
            pending.append(f"g02 {cell} rows={rows}/50")


def check_g03_rows() -> None:
    final = ROOT / "out/g03_formal/_final"
    cells = sorted(p.name for p in final.iterdir() if p.is_dir()) if final.is_dir() else []
    if not cells:
        pending.append("g03 _final 尚未生成")
        say("WAIT", "g03 _final 尚未生成（阶段 B 未跑完或未 merge）")
        return
    bad = []
    for cell in cells:
        want = CORE_R if cell in CORE else TIER2_R
        formal = final / cell / "repetitions.csv"
        if not formal.is_file():
            bad.append(f"{cell} 无 repetitions.csv")
            continue
        rows = len(read(formal).splitlines()) - 1
        if rows != want:
            bad.append(f"{cell} {rows}/{want}")
    if len(cells) != 24:
        bad.append(f"格数 {len(cells)}/24")
    if bad:
        pending.append("g03 覆盖不全：" + "；".join(bad[:6]))
        say("WAIT", f"g03 覆盖不全：{'；'.join(bad[:6])}")
    else:
        say("OK ", "g03 24 格 repetitions.csv 全部达 R")


def check_sources() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from causal_growth.data.v3_pipeline import pipeline_source_hashes

    live = pipeline_source_hashes()
    say("INFO", f"源码绑定集 {len(live)} 文件")
    snap = ROOT / "out/g03_snapshot/snapshot_binding.json"
    if not snap.is_file():
        say("INFO", "g03 快照未生成，源码哈希暂无可比基准（链条启动后再查）")
        return
    bound = json.loads(snap.read_text(encoding="utf-8"))["source_hashes"]
    missing = sorted(set(bound) - set(live))
    extra = sorted(set(live) - set(bound))
    drifted = sorted(k for k in set(live) & set(bound) if live[k] != bound[k])
    if missing or extra or drifted:
        problems.append(
            f"源码与 g03 快照不一致：缺 {missing[:3]} 多 {extra[:3]} 变 {drifted[:3]}")
        say("FAIL", f"源码漂移 missing={len(missing)} extra={len(extra)} drifted={len(drifted)}")
    else:
        say("OK ", f"源码 {len(live)} 文件与 g03 快照逐文件一致")


def check_overlay() -> None:
    if not OVERLAY.is_file():
        problems.append("g02_bootstrap_overlay.yaml 缺失")
        return
    got = hashlib.sha256(OVERLAY.read_bytes()).hexdigest()
    if got != OVERLAY_SHA:
        problems.append(f"overlay sha256 {got[:16]}… != 记录 {OVERLAY_SHA[:16]}…")
        say("FAIL", "overlay 身份变化")
    else:
        say("OK ", f"overlay sha256 {got[:16]}… 与记录一致（{OVERLAY.stat().st_size} B）")


def check_git() -> None:
    proc = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--",
                           "src", "sql", "configs"], capture_output=True, text=True)
    dirty = [line for line in proc.stdout.splitlines() if line.strip()]
    if dirty:
        problems.append(f"受绑路径有未提交改动：{dirty[:3]}")
        say("FAIL", f"受绑路径 git 不干净（{len(dirty)} 条）")
    else:
        say("OK ", "src/ sql/ configs/ git 干净")


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(PY), f"scripts/{script}", *args], cwd=ROOT,
                          capture_output=True, text=True, env=ENV)


def check_evidence(with_check: bool) -> None:
    if not with_check:
        return
    for name in ("40_export_g02_evidence.py", "41_export_g03_evidence.py"):
        proc = _run(name, "--check")
        tail = ((proc.stdout + proc.stderr).strip().splitlines() or [""])[-1]
        if proc.returncode == 0:
            say("OK ", f"{name} --check EXIT=0")
        else:
            problems.append(f"{name} --check EXIT={proc.returncode}：{tail[:160]}")
            say("FAIL", f"{name} --check EXIT={proc.returncode}")


def check_register(with_register: bool) -> None:
    if not with_register:
        return
    proc = _run("33_register_evidence_top.py", "--dirs", "g02_formal", "g03_formal",
                "--dry-run")
    if proc.returncode != 0:
        problems.append(f"33 --dry-run EXIT={proc.returncode}")
        say("FAIL", f"33 --dry-run EXIT={proc.returncode}")
    else:
        say("INFO", "33 --dry-run EXIT=0（全表复算一致；实登记已于 19:48 完成）")
    print("\n".join((proc.stdout + proc.stderr).strip().splitlines()[-12:]))


def check_claims(with_claims: bool) -> None:
    if not with_claims:
        return
    proc = _run("42_claim_number_gate.py")
    if proc.returncode != 0:
        problems.append(f"42 claim gate EXIT={proc.returncode}")
        say("FAIL", f"42 claim gate EXIT={proc.returncode}")
    else:
        say("OK ", "42 claim gate EXIT=0")
    print("\n".join((proc.stdout or proc.stderr).strip().splitlines()[-3:]))


def verdict() -> int:
    print()
    if problems:
        say("VERDICT", "NOT READY：有必须人工处理的项")
        for item in problems:
            print("  !", item)
        return 3
    if pending:
        say("VERDICT", "NOT READY：仍有未完成项")
        for item in pending:
            print("  -", item)
        return 2
    say("VERDICT", "READY：可进入 33 登记与报告填数")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="G04 收尾只读体检")
    parser.add_argument("--with-check", action="store_true")
    parser.add_argument("--with-register", action="store_true")
    parser.add_argument("--with-claims", action="store_true")
    args = parser.parse_args()
    say("TIME", datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"))
    check_statuses()
    check_g02_rows()
    check_g03_rows()
    check_sources()
    check_overlay()
    check_git()
    check_claims(args.with_claims)
    check_evidence(args.with_check)
    check_register(args.with_register)
    return verdict()


if __name__ == "__main__":
    sys.exit(main())
