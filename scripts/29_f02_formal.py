"""F02 正式 200 rep 的分片入口：串行跑指定 rep 区间，逐 rep 落盘并写分片 summary。

为什么需要分片
--------------
单个 rep 在 n=200 000 下约 7 分钟（5 模型拟合 + 20 万验证用户生成 + 五表/SQL），
200 个 rep 单进程约一天。按 ``--rep-start/--rep-stop`` 切片，每个分片独立进程、
独立输出目录，最后由 ``30_merge_f02_formal.py`` 合并并校验。

纪律
----
- ``--status formal`` 必须带用户批准的 ``--formal-approval``；脚本不猜登记号。
- 每个 rep 的产物由 :func:`causal_growth.evaluation.v3_f02.run_f02_rep` 落盘，
  冻结文件先于真值审计写盘，本脚本不碰真值。
- ``--resume`` 只在登记号、``config_hash``、``source_hashes``、``n_users`` 全部
  一致时复用已有 rep；任何漂移都抛错，避免 200 个 rep 混入不同协议。
- 分片 summary 每完成一个 rep 就重写一次，进程崩了能看出跑到哪。

用法::

    # 单个 rep 的工程验证（不构成证据）
    python scripts/29_f02_formal.py --n 2000 --rep-start 0 --rep-stop 1 \
        --policy greedy_incremental_profit_per_cost --models constant \
        --out-root out/f02_formal_smoke --status engineering

    # 正式分片（需先用批准登记号）
    python scripts/29_f02_formal.py --n 200000 --rep-start 0 --rep-stop 49 \
        --policy greedy_incremental_profit_per_cost \
        --out-root out/f02_formal/shard0 --status formal \
        --formal-approval "<登记号>"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from causal_growth.data.v3_pipeline import pipeline_source_hashes  # noqa: E402
from causal_growth.evaluation.v3_f02 import run_f02_rep  # noqa: E402
from causal_growth.evaluation.v3_f02_formal import plan_formal_shard  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(f"[F02 formal {datetime.now(BEIJING).strftime('%H:%M:%S')}] {message}", flush=True)


def _sha256_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _write_summary(path: Path, summary: dict) -> None:
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F02 正式 200 rep 分片入口")
    parser.add_argument("--scenario", default="L1_main")
    parser.add_argument("--n", type=int, default=200_000)
    parser.add_argument("--rep-start", type=int, required=True)
    parser.add_argument("--rep-stop", type=int, required=True, help="含端点")
    parser.add_argument("--policy", default="greedy_incremental_profit_per_cost")
    parser.add_argument("--models", default="", help="逗号分隔；默认 5 个全跑")
    parser.add_argument("--time-mode", default="static")
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--status", default="formal",
                        choices=("provisional", "engineering", "formal"))
    parser.add_argument("--formal-approval", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true",
                        help="非 formal 状态下允许覆盖已有 rep 目录")
    args = parser.parse_args(argv)

    if args.rep_start < 0 or args.rep_stop < args.rep_start:
        parser.error("rep 区间非法：要求 0 <= rep-start <= rep-stop")
    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    cfg = load_v3_protocol().scenario(args.scenario)
    config_hash = cfg.hash(64)
    source_hashes = pipeline_source_hashes()
    models = None if not args.models else tuple(
        item.strip() for item in args.models.split(",") if item.strip()
    )
    rep_ids = list(range(args.rep_start, args.rep_stop + 1))

    if args.status == "formal":
        if not args.formal_approval:
            parser.error("--status formal 必须带 --formal-approval（用户批准的登记号）")
        to_run, skipped = plan_formal_shard(
            out_root, rep_ids,
            config_hash=config_hash,
            source_hashes=source_hashes,
            formal_approval=args.formal_approval,
            n_users=args.n,
            resume=args.resume,
        )
    else:
        existing = [rep for rep in rep_ids if (out_root / f"rep{rep}" / "manifest.json").is_file()]
        if existing and not args.overwrite:
            parser.error(f"{out_root} 已有 rep {existing}；要覆盖请显式 --overwrite")
        to_run, skipped = rep_ids, []

    out_root.mkdir(parents=True, exist_ok=True)
    summary_path = out_root / "summary.json"
    if args.status == "formal" and args.resume and not to_run and summary_path.is_file():
        _say("所有 rep 已存在且校验通过；保留原 summary，不重写")
        print(json.dumps({
            "summary": str(summary_path),
            "completed": [],
            "skipped": skipped,
            "note": "resume_noop",
        }, ensure_ascii=False, indent=2))
        return 0
    summary: dict = {
        "phase": "F02_formal_shard",
        "status": args.status,
        "formal_approval": (args.formal_approval or "").strip() or None,
        "scenario": args.scenario,
        "n_per_rep": args.n,
        "policy": args.policy,
        "models": list(models) if models else None,
        "time_mode": args.time_mode,
        "config_hash": config_hash,
        "source_hashes": source_hashes,
        "source_hashes_sha256": _sha256_payload(source_hashes),
        "rep_ids_requested": rep_ids,
        "to_run": to_run,
        "skipped_rep_ids": skipped,
        "completed_rep_ids": [],
        "reps": [],
        "failures": [],
        "started_at": _now(),
        "finished_at": None,
    }
    _write_summary(summary_path, summary)
    _say(
        f"分片 rep {args.rep_start}-{args.rep_stop}：待跑 {len(to_run)}，复用 {len(skipped)}；"
        f"n={args.n} status={args.status}"
    )
    _say(f"source_hashes_sha256={summary['source_hashes_sha256'][:16]}… config={config_hash[:12]}…")

    shard_started = time.perf_counter()
    for rep_id in to_run:
        rep_started = time.perf_counter()
        _say(f"rep {rep_id} 开始")
        try:
            result = run_f02_rep(
                scenario=args.scenario,
                n=args.n,
                rep_id=rep_id,
                policy=args.policy,
                models=models,
                time_mode=args.time_mode,
                out_dir=out_root / f"rep{rep_id}",
                status=args.status,
                formal_approval=args.formal_approval,
            )
        except Exception as exc:  # noqa: BLE001 - 分片必须留下失败记录再退出
            summary["failures"].append({
                "rep_id": rep_id,
                "error": f"{type(exc).__name__}: {exc}",
                "at": _now(),
            })
            summary["finished_at"] = _now()
            _write_summary(summary_path, summary)
            _say(f"rep {rep_id} 失败：{type(exc).__name__}: {exc}")
            raise
        elapsed = time.perf_counter() - rep_started
        summary["completed_rep_ids"].append(rep_id)
        summary["reps"].append({
            "rep_id": rep_id,
            "selected_model": result.model,
            "selected_policy": result.policy,
            "freeze_hash": result.freeze_hash,
            "decision_hash": result.manifest["decision_hash"],
            "guardrail_hash": result.manifest["guardrail_hash"],
            "per_user_hash": result.manifest["per_user_hash"],
            "elapsed_seconds": round(elapsed, 3),
        })
        summary["finished_at"] = _now()
        _write_summary(summary_path, summary)
        _say(
            f"rep {rep_id} 完成：model={result.model} "
            f"{elapsed:.1f}s（累计 {time.perf_counter() - shard_started:.1f}s）"
        )

    summary["finished_at"] = _now()
    summary["total_elapsed_seconds"] = round(time.perf_counter() - shard_started, 3)
    _write_summary(summary_path, summary)
    _say(f"分片完成：跑完 {len(summary['completed_rep_ids'])} 个 rep；summary={summary_path}")
    print(json.dumps({
        "summary": str(summary_path),
        "completed": summary["completed_rep_ids"],
        "skipped": skipped,
        "config_hash": config_hash,
        "source_hashes_sha256": summary["source_hashes_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
