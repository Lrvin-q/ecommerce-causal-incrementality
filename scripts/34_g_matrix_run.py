"""G 阶段矩阵驱动的薄入口：计划、分片运行、合并与汇总。

为什么不把逻辑写在这里
----------------------
一个 rep 只建一次数据、ATE 与学习共用、验证另建总体、冻结先于真值——这些
语义都在 ``causal_growth.evaluation.v3_g_matrix``；本脚本只做编排：

* ``plan``  打印预算契约下的格、R 与 CPU 估算，不跑任何作业；
* ``run``   按 (cell, rep) 分片派给多个单线程 worker，每个 worker 仍满足
            "一个 rep 只建一次数据"；分片各自落 ``repetitions_provisional.csv``；
* ``merge`` 读**全部** run-root，按 ``[scenario_id, block, rep]`` 去重；只有
            覆盖到目标 R 才写正式 ``repetitions.csv``，否则只写 provisional。

用法::

    # 看计划（不跑）
    python scripts/34_g_matrix_run.py plan

    # 工程小规模：2 格 × R=3，2 个 worker
    python scripts/34_g_matrix_run.py run --cells L1_main L0_Pi_heterogeneous_cost \
        --rep-start 0 --rep-stop 2 --n 2000 --workers 2 --models constant \
        --out-root out/g_smoke --status engineering

    # 合并 + 汇总（未跑满自动写 _provisional）
    python scripts/34_g_matrix_run.py merge out/g_smoke --summary-dir outputs/tables

    # 正式跑：必须带批准号；正式跑前把 PYTHONPATH 指向快照
    python scripts/34_g_matrix_run.py run --status formal \
        --formal-approval "<登记号>" --snapshot out/g_snapshot ...
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from causal_growth.evaluation import v3_g_matrix as g  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")
DEFAULT_OVERLAY = ROOT / "configs" / "budget" / "tier2_overlay.yaml"


def _now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(f"[G {datetime.now(BEIJING).strftime('%H:%M:%S')}] {message}", flush=True)


def planned_cells(protocol, plan) -> list[str]:
    """Tier1 的四个 core 格 + overlay 选中的 Tier2 格。"""
    data = protocol.config.to_dict()
    core = [
        str(cell["id"]) for cell in data["scenarios"]
        if "core" in cell["roles"] and int(cell["tier"]) == 1
    ]
    return core + list(plan.tier2_cells)


def _chunks(values: list[int], size: int) -> list[list[int]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _worker(task: dict) -> dict:
    protocol = load_v3_protocol()
    plan = g.load_budget_plan(protocol, overlay=task["overlay"])
    result = g.run_cell(
        protocol, task["cell"], out_root=task["root"], reps=task["reps"],
        target_reps=len(task["reps"]), status=task["status"],
        formal_approval=task["formal_approval"], plan=plan, n=task["n"],
        models=tuple(task["models"]) if task["models"] else None,
        policy=task["policy"], with_learning=task["with_learning"],
        with_validation=task["with_validation"],
        bootstrap_resamples=int(task["bootstrap_resamples"]), snapshot=task["snapshot"],
        bootstrap_budget_scope=task.get("bootstrap_budget_scope"),
        resume_from=task["resume_from"],
    )
    return {"cell": task["cell"], "reps": task["reps"], "shard": str(task["root"]), **result}


def _snapshot_from(path: Path) -> dict:
    binding = path if path.is_file() else path / "snapshot_binding.json"
    payload = json.loads(binding.read_text(encoding="utf-8"))
    if payload.get("kind") != "byte_snapshot":
        raise SystemExit(f"不是字节快照绑定：{binding}")
    return payload


def _verify_snapshot(binding: dict, protocol) -> None:
    live = g.pipeline_source_hashes()
    snapshot = dict(binding["source_hashes"])
    if snapshot != live:
        stale = sorted(set(snapshot) - set(live)) + sorted(set(live) - set(snapshot))
        changed = sorted(k for k in set(snapshot) & set(live) if snapshot[k] != live[k])
        raise SystemExit(
            f"快照与当前源码不一致：新增/删除 {stale[:5]}，内容变化 {changed[:5]}；"
            "正式跑必须让 PYTHONPATH 指向快照，或重新生成快照"
        )


def _merge_telemetry(roots: list[Path], cell: str, target: Path) -> dict:
    """把各分片的 ``repetitions_telemetry.csv`` 合成一份。

    遥测列落后于 ``repetitions.csv``（A2 要求逐字节复现，计时两次必不同），
    所以它不能进同一张表；但正式跑的证据必须自足，不能只躺在分片目录里。
    同键重复（同一 rep 被两个 root 各跑一次）取排序靠后的 root 的值并计数。
    """
    header = g.TELEMETRY_COLUMNS
    merged: dict[tuple[str, str, int], dict[str, str]] = {}
    duplicates = 0
    for root in sorted(roots):
        path = root / cell / "repetitions_telemetry.csv"
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != header:
                raise SystemExit(f"遥测列不符（{path}）：{reader.fieldnames} != {list(header)}")
            for record in reader:
                key = (record["scenario_id"], record["block"], int(record["rep"]))
                if key in merged:
                    duplicates += 1
                merged[key] = record
    if merged:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
            writer.writeheader()
            for key in sorted(merged):
                writer.writerow(merged[key])
    return {"path": target.as_posix(), "rows": len(merged), "duplicates": duplicates}


def _finalize(roots: list[Path], protocol, plan, summary_dir: Path,
              final_parent: Path | None = None) -> dict:
    rows, report = g.merge_roots(roots)
    specs = {cell: g.plan_cell(protocol, cell, plan) for cell in {r["cell_id"] for r in rows}}
    complete: dict[str, bool] = {}
    for cell, spec in specs.items():
        present = {int(row["rep"]) for row in rows if row["cell_id"] == cell}
        complete[cell] = present == set(range(int(spec["R_ate"])))
    all_complete = all(complete.values())

    final_root = (final_parent or roots[0]) / "_final"
    summary_paths = []
    telemetry: dict[str, dict] = {}
    for block in (g.BLOCK_CORE, g.BLOCK_TIER2):
        block_rows = [row for row in rows if str(row["block"]) == block]
        if not block_rows:
            continue
        for cell in sorted({row["cell_id"] for row in block_rows}):
            cell_rows = [row for row in block_rows if row["cell_id"] == cell]
            target = final_root / cell / (
                "repetitions.csv" if complete.get(cell) else "repetitions_provisional.csv"
            )
            g.write_repetition_rows(target, cell_rows)
            telemetry[cell] = _merge_telemetry(
                roots, cell, target.parent / "repetitions_telemetry.csv"
            )
        path = summary_dir / f"v3_g_{block.lower()}.csv"
        written = g.write_summary_table(block_rows, path, provisional=not all_complete)
        summary_paths.append(written.as_posix())

    payload = {
        "merged": report,
        "cells": {cell: {"complete": done} for cell, done in sorted(complete.items())},
        "all_complete": all_complete,
        "final_root": final_root.as_posix(),
        "telemetry": telemetry,
        "summaries": summary_paths,
        "at": _now(),
    }
    report_path = roots[0] / "merge_report.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G 阶段矩阵驱动薄入口")
    parser.add_argument("mode", choices=("plan", "run", "merge"))
    parser.add_argument("roots", nargs="*", help="merge 模式的 run-root（可多个）")
    parser.add_argument("--cells", nargs="*", default=None)
    parser.add_argument("--rep-start", type=int, default=0)
    parser.add_argument("--rep-stop", type=int, default=None, help="含端点")
    parser.add_argument("--shard-size", type=int, default=50)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--policy", default="greedy_incremental_profit_per_cost")
    parser.add_argument("--no-learning", action="store_true")
    parser.add_argument("--no-validation", action="store_true")
    parser.add_argument(
        "--bootstrap-resamples", type=int, default=0,
        help="验证臂固定策略 bootstrap 重抽次数（0=不跑；协议要求 1000）",
    )
    parser.add_argument(
        "--bootstrap-budget-scope", default=None,
        help="bootstrap 覆盖的预算档声明；正式跑且 resamples>0 时必须为 primary_0.2",
    )
    parser.add_argument("--out-root", type=Path, default=ROOT / "out" / "g_matrix")
    parser.add_argument("--summary-dir", type=Path, default=ROOT / "outputs" / "tables")
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    parser.add_argument("--status", default="engineering",
                        choices=("engineering", "provisional", "formal"))
    parser.add_argument("--formal-approval", default=None)
    parser.add_argument("--snapshot-out", type=Path, default=None)
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--final-parent", type=Path, default=None,
                        help="merge 模式：_final 落在该目录下（默认 roots[0]）")
    args = parser.parse_args(argv)

    protocol = load_v3_protocol()
    plan = g.load_budget_plan(protocol, overlay=args.overlay)
    cells = args.cells or planned_cells(protocol, plan)

    if args.mode == "plan":
        rows = []
        total_seconds = 0.0
        for cell in cells:
            spec = g.plan_cell(protocol, cell, plan)
            rows.append(spec)
            if spec["tier"] == 1:
                ate_s, learn_s, val_s = 117.0, 130.0, 117.0
            else:
                ate_s, learn_s, val_s = 106.0, 130.0, 106.0
            total_seconds += (
                spec["R_ate"] * ate_s
                + spec["R_learn"] * learn_s
                + spec["R_validation"] * val_s
            )
        for spec in rows:
            print(f"{spec['cell_id']:30s} {spec['block']:8s} "
                  f"R_ate={spec['R_ate']:4d} R_learn={spec['R_learn']:4d} "
                  f"R_validation={spec['R_validation']:4d} n={spec['n']}")
        print(f"cells={len(rows)}  预计 CPU·h≈{total_seconds / 3600:.1f}")
        return 0

    if args.mode == "merge":
        roots = [Path(root) for root in args.roots]
        if not roots:
            parser.error("merge 模式需要至少一个 run-root")
        payload = _finalize(roots, protocol, plan, args.summary_dir,
                            final_parent=args.final_parent)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.status == "formal" and not args.formal_approval:
        parser.error("--status formal 必须带 --formal-approval（用户批准的登记号）")
    if (args.status == "formal" and int(args.bootstrap_resamples) > 0
            and args.bootstrap_budget_scope != "primary_0.2"):
        parser.error("正式跑且 --bootstrap-resamples>0 时必须显式 "
                     "--bootstrap-budget-scope primary_0.2（v3_g_matrix.require_bootstrap_scope）")
    started_at = _now()
    snapshot = None
    if args.snapshot_out is not None:
        snapshot = g.create_snapshot(args.snapshot_out)
        _say(f"快照已生成：{args.snapshot_out}（{snapshot['n_files']} 个文件）")
    if args.snapshot is not None:
        snapshot = _snapshot_from(args.snapshot)
        _verify_snapshot(snapshot, protocol)
        _say(f"使用快照绑定：{snapshot['source_hashes_sha256'][:16]}…")
    if args.status == "formal" and snapshot is None:
        if os.environ.get("CG_G_ALLOW_LIVE_FORMAL") != "1":
            parser.error("正式跑必须提供 --snapshot 或 --snapshot-out；"
                         "如确要 live 运行，设 CG_G_ALLOW_LIVE_FORMAL=1 并自行承担 §11 风险")

    args.out_root.mkdir(parents=True, exist_ok=True)
    tasks: list[dict] = []
    for cell in cells:
        spec = g.plan_cell(protocol, cell, plan)
        stop = int(spec["R_ate"] - 1 if args.rep_stop is None else args.rep_stop)
        if args.rep_stop is not None and stop >= int(spec["R_ate"]):
            raise SystemExit(f"{cell} 的 rep-stop {stop} 超出 R_ate={spec['R_ate']}")
        reps = list(range(args.rep_start, stop + 1))
        shards = _chunks(reps, max(1, int(args.shard_size)))
        for index, chunk in enumerate(shards):
            root = args.out_root / "shards" / f"{cell}_s{index:04d}"
            resume_from = None
            if args.resume:
                candidate = root / cell / "repetitions_provisional.csv"
                if candidate.is_file():
                    resume_from = candidate
            tasks.append({
                "cell": cell, "reps": chunk, "root": root,
                "status": args.status, "formal_approval": args.formal_approval,
                "n": args.n, "models": args.models, "policy": args.policy,
                "with_learning": not args.no_learning,
                "with_validation": not args.no_validation,
                "bootstrap_resamples": int(args.bootstrap_resamples),
                "bootstrap_budget_scope": args.bootstrap_budget_scope,
                "snapshot": snapshot, "resume_from": resume_from,
                "overlay": args.overlay.as_posix(),
            })

    _say(f"{len(cells)} 格 / {len(tasks)} 个分片；workers={args.workers} status={args.status}")
    failures = []
    with ProcessPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        futures = {pool.submit(_worker, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - 分片失败必须留记录
                failures.append({"cell": task["cell"], "reps": task["reps"],
                                 "error": f"{type(exc).__name__}: {exc}"})
                _say(f"失败 {task['cell']} reps={task['reps']}: {type(exc).__name__}: {exc}")
                continue
            _say(f"完成 {task['cell']} reps={task['reps']} rows={result['rows']} "
                 f"provisional={result['provisional']}")

    shard_roots = sorted((args.out_root / "shards").glob("*"))
    payload = _finalize(
        [path for path in shard_roots if path.is_dir()],
        protocol, plan, args.summary_dir, final_parent=args.out_root,
    )
    payload["failures"] = failures
    payload["status"] = args.status
    payload["bootstrap_resamples"] = int(args.bootstrap_resamples)
    payload["bootstrap_budget_scope"] = args.bootstrap_budget_scope
    payload["started_at"] = started_at
    payload["finished_at"] = _now()
    (args.out_root / "run_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failures:
        _say(f"{len(failures)} 个分片失败；见 {args.out_root / 'run_summary.json'}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
