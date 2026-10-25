"""清理 `out/` 下的作废脚手架，释放磁盘。

为什么要脚本而不是手删
----------------------
`out/` 里同时存在三类东西：
  1. 已被取代的旧脚手架（v2 论文评审、pytest 临时目录、被正式跑取代的 pilot）；
  2. 正在跑的作业目录（AA 正式跑的 `v3_phase_d_aa_formal`、代理的 `lp_tmp`/`engfix_tmp`）；
  3. 唯一副本的评审证据（`review_d_science` 的验证脚本）。
手删极易把 2 和 3 一起清掉。本脚本用**显式白名单**加三道安全校验，只删第 1 类。

安全校验
--------
- 目标必须解析在项目根目录之内（防相对路径越界）；
- 目标不得是 `data/audit/outputs/src/sql/configs/tests/paper/reports/docs/HITL` 这些关键目录；
- 目标必须命中白名单前缀（`out/` 下的已知作废名）。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\16_cleanup_scratch.py           # 预演，只列出将删的
    .\\.venv\\Scripts\\python.exe scripts\\16_cleanup_scratch.py --apply   # 真删
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 作废脚手架的判定规则：名字命中任一前缀即视为可删（均在 out/ 下）。
OBSOLETE_PREFIXES = (
    "_before", "render", "render_r3", "render_final", "pages", "paper_check",
    "_review_r1", "_review_r2", "_review_r3", "_review_r4", "_review_r5",
    "pytest_baseline_check", "pytest_recheck_", "pytest_v3power", "pytest",
    "v3_phase_d_aa",          # D.2 的 pilot，已被 4 层 ×250 形式跑取代
    "probe_", "prof_",
)

#: 永不删除（正在跑的作业或唯一证据）。
PROTECTED_NAMES = {
    "v3_phase_d_aa_formal",   # 正式 AA 运行中
    "review_d_science",       # 科学评审的验证脚本，唯一副本
    "review_d_eng",           # 工程评审的脚本（大件已单独清过）
    "aa_snapshot",            # 正式 AA 的源码快照，产物绑定的依据
    "v3_phase_a", "v3_phase_b", "v3_phase_c",   # 各阶段证据
    "v3_phase_d", "v3_phase_d_switch", "v3_phase_d_mde", "v3_phase_d_mde_kappa",
}

#: 永不删除的顶层目录。
PROTECTED_TOP = {"data", "audit", "outputs", "src", "sql", "configs", "tests",
                 "paper", "reports", "docs", "HITL", ".git", ".venv"}


def dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def is_obsolete(name: str) -> bool:
    if name in PROTECTED_NAMES:
        return False
    return any(name == p or name.startswith(p) for p in OBSOLETE_PREFIXES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="真正删除；默认只预演")
    args = parser.parse_args()

    out = ROOT / "out"
    if not out.is_dir():
        print("out/ 不存在，无需清理")
        return 0

    candidates = sorted(p for p in out.iterdir() if p.is_dir() and is_obsolete(p.name))
    total = 0
    for path in candidates:
        resolved = path.resolve()
        if resolved.parent != out.resolve():
            print(f"  跳过（不在 out/ 下一层）: {path.name}")
            continue
        if resolved.name in PROTECTED_TOP:
            print(f"  跳过（受保护）: {path.name}")
            continue
        size = dir_size(resolved)
        total += size
        if args.apply:
            shutil.rmtree(resolved, ignore_errors=True)
            status = "已删" if not resolved.exists() else "删除失败"
        else:
            status = "将删"
        print(f"  {status}  {path.name:<40} {size / 1024 / 1024:8.1f} MB")

    verb = "释放" if args.apply else "可释放"
    print(f"\n共 {len(candidates)} 个目录，{verb} {total / 1024 / 1024:.1f} MB")
    if not args.apply:
        print("这是预演；加 --apply 真正删除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
