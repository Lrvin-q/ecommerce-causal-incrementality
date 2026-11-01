"""G01 的 AA 臂：四层完整链路 AA → 17 号可合并的逐层表。

为什么需要它
------------
G01 的验收口径是"每层 250 次、四层合计 1000 次、n=200 000"的**池化**假阳性率，
合并权威是 ``scripts/17_merge_aa_layers.py``；它只读 ``<root>/<layer>/aa_repetitions.csv``。
而 ``v3_aa.run_full_chain_aa`` 把四层写进**一个** ``aa_repetitions.csv``（带 ``level`` 列）。
直接把 34 号矩阵驱动器的产物接上去，17 号会"四层全缺"——不是报错，是空合并。
本脚本只做这层适配，并补齐 G01 的门禁与绑定：正式跑必须带批准号与快照。

不重算任何统计
--------------
FPR、Clopper–Pearson 区间、SE 校准全部由 17 号算，本脚本不复制那套公式，
避免两处口径分叉。本脚本只负责：跑、拆层、落绑定、核完整性。

用法::

    # 看计划（不跑）
    python scripts/36_g_aa_run.py plan

    # 工程冒烟：四层各 1 次、n=2000
    python scripts/36_g_aa_run.py run --reps 1 --n 2000 --out-root out/g_aa_smoke

    # 正式跑（必须带批准号 + 快照；PYTHONPATH 指向快照）
    python scripts/36_g_aa_run.py run --status formal \
        --formal-approval "<登记号>" --snapshot out/g_snapshot --workers 4

    # 合并（调用 17 号，未跑满会自动写 _provisional）
    python scripts/36_g_aa_run.py merge out/g_aa_formal
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from causal_growth.evaluation import v3_aa  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")
MERGE_SCRIPT = ROOT / "scripts" / "17_merge_aa_layers.py"
ENGINEERING_MAX_REPS = 5


def _now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(f"[G-AA {datetime.now(BEIJING).strftime('%H:%M:%S')}] {message}", flush=True)


def _load_34():
    """复用 34 号的快照读取/校验，避免两处各写一份而口径分叉。"""
    spec = importlib.util.spec_from_file_location(
        "g_matrix_run_34", ROOT / "scripts" / "34_g_matrix_run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layer_cells(protocol) -> dict[str, "v3_aa.AACell"]:
    """层 → 该层唯一的完整 AA 格；由 ``v3_aa.aa_cells`` 的合同检查兜底。"""
    return {cell.level: cell for cell in v3_aa.aa_cells(protocol)}


def declared_reps(protocol) -> int:
    return int(protocol.config.require("execution.formal_repeats.tier1_aa_per_layer"))


def gate(*, status: str, approval: str | None, snapshot, allow_live: bool,
         reps: int | None, declared: int, rep_start: int) -> int:
    """返回本次要跑的 rep 数；不满足门禁直接抛 ``SystemExit``。"""
    if status == "formal":
        if not approval:
            raise SystemExit("--status formal 必须带 --formal-approval（用户批准的登记号）")
        if snapshot is None and not allow_live:
            raise SystemExit(
                "正式跑必须提供 --snapshot；如确要 live 运行，"
                "设 CG_G_AA_ALLOW_LIVE_FORMAL=1 并自行承担 AGENTS §11 风险"
            )
        target = declared if reps is None else int(reps)
    else:
        if reps is None:
            raise SystemExit("工程跑必须显式给 --reps（防止把 250 当成默认值误跑）")
        target = int(reps)
        if target > ENGINEERING_MAX_REPS:
            raise SystemExit(
                f"工程跑上限 {ENGINEERING_MAX_REPS} rep/层；要跑更多请用 --status formal 并走开跑门禁"
            )
    if target < 1:
        raise SystemExit(f"reps 必须 >= 1，收到 {target}")
    if rep_start < 0:
        raise SystemExit(f"rep-start 必须 >= 0，收到 {rep_start}")
    if rep_start + target > declared:
        raise SystemExit(f"rep 区间 [{rep_start}, {rep_start + target}) 超出注册 R={declared}")
    return target


def split_layer_table(frame: pd.DataFrame, *, layer: str, scenario_id: str,
                      protocol_hash: str) -> pd.DataFrame:
    """把多层逐 rep 表筛成单层 ``true_aa`` 表；混入别层或别协议立即失败。

    静默按 block 过滤会把"跑错格"变成"这层少几行"，两者外观完全一样。
    """
    if "block" not in frame.columns or "scenario_id" not in frame.columns:
        raise SystemExit("逐 rep 表缺少 block/scenario_id 列，无法拆层")
    foreign = sorted(set(frame["scenario_id"]) - {scenario_id})
    if foreign:
        raise SystemExit(f"{layer} 层出现非本层格：{foreign}（期望只有 {scenario_id}）")
    if "protocol_config_hash" in frame.columns:
        hashes = sorted(frame["protocol_config_hash"].dropna().unique())
        if hashes != [protocol_hash]:
            raise SystemExit(f"{layer} 层的 protocol_config_hash 与当前协议不一致：{hashes}")
    subset = frame[frame["block"] == v3_aa._BLOCK_TRUE_AA].reset_index(drop=True)
    if subset.empty:
        raise SystemExit(f"{layer} 层没有任何 true_aa 行（block 取值 {sorted(set(frame['block']))}）")
    return subset


def _worker(task: dict) -> dict:
    from causal_growth.v3_config import load_v3_protocol as _load

    protocol = _load()
    expected = layer_cells(protocol)[task["layer"]].scenario_id
    bundle = v3_aa.run_full_chain_aa(
        protocol, reps=task["reps"], n=task["n"], layers=[task["layer"]],
        rep_start=task["rep_start"], run_root=task["run_root"],
        keep_representative=task["keep_representative"],
        include_negative_control=False, cost_anchor_reps=0,
        max_source_retries=task["max_source_retries"],
        resume_from=task["resume_from"], progress=_say,
    )
    table = split_layer_table(
        bundle.repetitions, layer=task["layer"], scenario_id=expected,
        protocol_hash=protocol.config_hash,
    )
    layer_dir = Path(task["out_root"]) / task["layer"]
    layer_dir.mkdir(parents=True, exist_ok=True)
    table_path = layer_dir / "aa_repetitions.csv"
    table.to_csv(table_path, index=False, encoding="utf-8-sig", lineterminator="\n")
    digest = hashlib.sha256(table_path.read_bytes()).hexdigest()
    manifest = {**bundle.manifest, "g_layer": task["layer"], "g_status": task["status"],
                "g_formal_approval": task["formal_approval"],
                "layer_table": table_path.relative_to(ROOT).as_posix() if table_path.is_relative_to(ROOT)
                else table_path.as_posix(),
                "layer_table_sha256": digest, "layer_table_rows": int(len(table))}
    (layer_dir / "aa_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "layer": task["layer"], "scenario_id": expected,
        "rows": int(len(table)),
        "reps": sorted(int(value) for value in table["rep"].unique()),
        "table": table_path.as_posix(), "sha256": digest,
        "cpu_s": float(table["total_cpu_s"].sum()) if "total_cpu_s" in table.columns else None,
        "wall_s_median": float(table["total_wall_s"].median()) if "total_wall_s" in table.columns else None,
        "run_root": str(bundle.run_root),
    }


def _resume_source(out_root: Path, layer: str) -> Path | None:
    """找该层最近的完整逐 rep 表；只认同一 (alpha, n) 由 run 时校验。"""
    candidates = sorted(
        (out_root / "layer_runs").glob(f"{layer}*/aa_repetitions.csv"),
        key=lambda path: path.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G01 AA 臂执行器（薄编排）")
    parser.add_argument("mode", choices=("plan", "run", "merge"))
    parser.add_argument("roots", nargs="*", help="merge 模式的 G 根目录")
    parser.add_argument("--layers", nargs="*", default=None)
    parser.add_argument("--reps", type=int, default=None)
    parser.add_argument("--rep-start", type=int, default=0)
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out-root", type=Path, default=ROOT / "out" / "g_aa")
    parser.add_argument("--status", default="engineering",
                        choices=("engineering", "provisional", "formal"))
    parser.add_argument("--formal-approval", default=None)
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keep-representative", dest="keep_representative",
                        action="store_true", default=True,
                        help="保留每层 rep==0 的五表/SQL 产物（默认开）")
    parser.add_argument("--no-keep-representative", dest="keep_representative",
                        action="store_false", help="冒烟时丢弃产物目录")
    parser.add_argument("--max-source-retries", type=int, default=3)
    args = parser.parse_args(argv)

    protocol = load_v3_protocol()
    cells = layer_cells(protocol)
    declared = declared_reps(protocol)
    layers = list(args.layers) if args.layers else list(cells)
    unknown = [layer for layer in layers if layer not in cells]
    if unknown:
        parser.error(f"未知层：{unknown}；已注册 {sorted(cells)}")
    if args.workers > len(layers):
        parser.error(f"workers={args.workers} 超过层数 {len(layers)}（一层一个进程）")

    if args.mode == "plan":
        per_rep_s = 160.0
        total = len(layers) * declared * per_rep_s
        for layer in layers:
            cell = cells[layer]
            print(f"{layer}: {cell.scenario_id}  R={declared}  n={cell.registered_n}（注册规模）")
        print(f"层数={len(layers)} 合计 rep={len(layers) * declared}  "
              f"预计 CPU·h≈{total / 3600:.1f}（单 rep 160 s 实测，D01 外推）")
        return 0

    if args.mode == "merge":
        if not args.roots:
            parser.error("merge 模式需要至少一个 G 根目录")
        import subprocess
        command = [sys.executable, str(MERGE_SCRIPT), "--root", *args.roots]
        _say("合并交给 17 号：" + " ".join(command))
        return subprocess.call(command)

    target = gate(
        status=args.status, approval=args.formal_approval, snapshot=args.snapshot,
        allow_live=os.environ.get("CG_G_AA_ALLOW_LIVE_FORMAL") == "1",
        reps=args.reps, declared=declared, rep_start=args.rep_start,
    )
    snapshot = None
    if args.snapshot is not None:
        g34 = _load_34()
        snapshot = g34._snapshot_from(args.snapshot)
        g34._verify_snapshot(snapshot, protocol)
        _say(f"快照绑定：{snapshot['source_hashes_sha256'][:16]}…")

    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    (out_root / "layer_runs").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(BEIJING).strftime("%H%M%S")
    tasks = []
    for layer in layers:
        cell = cells[layer]
        size = cell.registered_n if args.n is None else int(args.n)
        if args.status == "formal" and size != cell.registered_n:
            raise SystemExit(
                f"正式跑 {layer} 的 n={size} 与注册规模 {cell.registered_n} 不符；"
                "17 号会拒绝合并，不可用工程规模冒充正式规模"
            )
        run_root = out_root / "layer_runs" / f"{layer}_{stamp}"
        if run_root.exists():
            raise SystemExit(f"run_root 已存在，拒绝覆盖：{run_root}")
        resume_from = _resume_source(out_root, layer) if args.resume else None
        tasks.append({
            "layer": layer, "reps": target, "rep_start": args.rep_start,
            "n": size, "run_root": run_root, "out_root": out_root.as_posix(),
            "status": args.status, "formal_approval": args.formal_approval,
            "keep_representative": args.keep_representative,
            "max_source_retries": args.max_source_retries,
            "resume_from": resume_from.as_posix() if resume_from else None,
        })
        if resume_from:
            _say(f"{layer}: 将从 {resume_from} 续跑（v3_aa 会校验 alpha/n）")

    _say(f"{len(layers)} 层 / 每层 {target} rep；workers={args.workers} status={args.status}")
    started = _now()
    results, failures = [], []
    if args.workers == 1:
        for task in tasks:
            try:
                results.append(_worker(task))
            except Exception as exc:  # noqa: BLE001 - 单层失败不得吞掉其余层的记录
                failures.append({"layer": task["layer"], "error": f"{type(exc).__name__}: {exc}"})
                _say(f"失败 {task['layer']}: {type(exc).__name__}: {exc}")
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_worker, task): task for task in tasks}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    failures.append({"layer": task["layer"],
                                     "error": f"{type(exc).__name__}: {exc}"})
                    _say(f"失败 {task['layer']}: {type(exc).__name__}: {exc}")

    expected_reps = set(range(args.rep_start, args.rep_start + target))
    complete = {
        item["layer"]: set(item["reps"]) == expected_reps for item in results
    }
    all_complete = len(results) == len(layers) and all(complete.values())
    payload = {
        "source_label": "合成数据 / 已知 DGP",
        "purpose": "g01_aa_arm",
        "status": args.status,
        "formal_approval": args.formal_approval,
        "snapshot_binding": None if snapshot is None else {
            "source_hashes_sha256": snapshot["source_hashes_sha256"],
            "n_files": snapshot.get("n_files"),
        },
        "protocol_config_hash": protocol.config_hash,
        "declared_reps_per_layer": declared,
        "requested": {"reps": target, "rep_start": args.rep_start, "n": args.n},
        "layers": results,
        "complete": complete,
        "all_complete": all_complete,
        "failures": failures,
        "started_at": started,
        "finished_at": _now(),
        "note": ("内层 aa_manifest.json 的 purpose/formal_repetitions_completed 是 "
                 "v3_aa 模块的 D 阶段固定标签，**不是** G01 的计数器；G01 的正式状态与 "
                 "rep 完整性以本文件为准。"),
    }
    summary_path = out_root / "g_aa_run_summary.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _say(f"完成 {len(results)}/{len(layers)} 层；all_complete={all_complete}；"
         f"汇总 {summary_path}")
    if not all_complete:
        _say("未跑满：逐层表仍按原路径落盘，但 17 号合并会自动写 _provisional，不得当验收凭据")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
