"""一键复现入口。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\run_all.py --round 1     # 第一轮
    .\\.venv\\Scripts\\python.exe scripts\\run_all.py --round all   # 全部

设计原则
--------
* 只做编排：按顺序调用各阶段脚本，不在这里写任何业务逻辑。
* **失败要响**：任一阶段非零退出，立刻停并把 stderr 打出来，
  绝不"继续跑完再说"（否则会产出看似完整但口径已坏的报告）。
* 每阶段打印耗时，便于定位慢在哪。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"

#: 轮次 → 要按顺序执行的脚本
PIPELINE: dict[str, list[str]] = {
    "1": ["01_build_data.py", "02_run_experiment.py"],
    "2": ["03_cate_obs.py"],
    "3": ["04_policy.py"],
}


def _resolve(rounds: str) -> list[str]:
    if rounds == "all":
        keys = list(PIPELINE)
    elif rounds in PIPELINE:
        keys = [rounds]
    else:
        raise SystemExit(f"未知轮次 {rounds!r}；可选：{list(PIPELINE)} 或 all")
    scripts: list[str] = []
    for k in keys:
        for s in PIPELINE[k]:
            if s not in scripts:
                scripts.append(s)
    return scripts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一键复现第一/二/三轮产物")
    parser.add_argument("--round", default="1", help="1 / 2 / 3 / all")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不执行")
    args = parser.parse_args(argv)

    if not PY.exists():
        raise SystemExit(f"找不到虚拟环境解释器：{PY}\n请先创建 .venv 并安装依赖")

    scripts = _resolve(args.round)
    existing = [s for s in scripts if (ROOT / "scripts" / s).exists()]
    missing = [s for s in scripts if s not in existing]

    print(f"计划 ({len(scripts)} 步)：")
    for s in scripts:
        flag = "  " if s in existing else "（尚未实现）"
        print(f"  - scripts/{s} {flag}")
    if args.dry_run:
        return 0

    failed: list[tuple[str, int]] = []
    for name in existing:
        print(f"\n{'=' * 70}\n>>> {name}\n{'=' * 70}")
        t0 = time.perf_counter()
        proc = subprocess.run(
            [str(PY), str(ROOT / "scripts" / name)],
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
        )
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            failed.append((name, proc.returncode))
            print(f"!!! {name} 失败（exit={proc.returncode}），流水线中止")
            break
        print(f"<<< {name} 完成，耗时 {elapsed:.1f}s")

    if failed:
        print("\n失败阶段：", failed)
        return 1
    print("\n全部完成。")
    if missing:
        print("未实现（后续轮次）：", missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
