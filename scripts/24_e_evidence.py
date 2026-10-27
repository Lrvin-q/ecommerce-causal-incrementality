"""E 阶段正文证据入口：一个代表 rep 的 9 列帧 → 7 张证据表（薄入口）。

证据逻辑在 :mod:`causal_growth.policy.v3_policy_evidence`；本脚本只负责
生成/读取逐用户帧、调用证据函数、落盘与打印摘要。

两种输入
--------
- ``--input``：已有的 9 列 CSV（``utf-8-sig``），用于冒烟与复用；
  没有 validation 切分，成本校准会标成不可用。
- ``--from-d03``（默认）：用 ``_d03_rep_artifacts`` 重建一个 rep 的
  5 模型链路，额外在 **validation 处理组**上做成本校准。

产物（``outputs/tables/`` 下，UTF-8-SIG）
-----------------------------------------
``v3_phase_E_calibration.json``、``v3_phase_E_small_pool.csv``、
``v3_phase_E_bucket_convergence.csv``、``v3_phase_E_random_long.csv``、
``v3_phase_E_random_summary.csv``、``v3_phase_E_decomposition.csv``、
``v3_phase_E_conservative.csv``、``v3_phase_E_scale.csv``、
``v3_phase_E_evidence_meta.json``。

用法
----
    $env:PYTHONUTF8='1'
    .\\venv\\Scripts\\python.exe scripts\\24_e_evidence.py --input out\\d03_smoke_test\\pred.csv --smoke
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.config import Config  # noqa: E402
from causal_growth.estimate.v3_models import (  # noqa: E402
    _d03_rep_artifacts,
    _observations_for_keys,
)
from causal_growth.policy import v3_policy as pol  # noqa: E402
from causal_growth.policy import v3_policy_evidence as ev  # noqa: E402
from causal_growth.policy.v3_policy_grid import require_grid_frame  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(f"[E evidence {datetime.now(BEIJING).strftime('%H:%M:%S')}] {message}", flush=True)


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _json_safe(value):
    """把 NaN/Inf 换成 None，保证写出的是严格 JSON（NaN 不是合法 JSON）。"""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    _say(f"wrote {_rel(path)} ({len(frame)} rows)")


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    _say(f"wrote {_rel(path)}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_ints(text: str) -> list[int]:
    return [int(item) for item in text.split(",") if item.strip()]


def _parse_floats(text: str) -> list[float]:
    return [float(item) for item in text.split(",") if item.strip()]


def _parse_pools(text: str) -> list[object]:
    pools: list[object] = []
    for item in text.split(","):
        token = item.strip()
        if not token:
            continue
        pools.append(token if token in {"full_test", "full"} else int(token))
    return pools


def _load_input(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    require_grid_frame(frame)
    return frame


def _build_from_d03(args: argparse.Namespace) -> tuple[pd.DataFrame, dict, str]:
    _say(
        f"重建 D03 rep={args.rep_id} scenario={args.scenario} n={args.n} "
        f"（5 模型链路，约数分钟）"
    )
    started = time.perf_counter()
    models = None if not args.models else tuple(
        item.strip() for item in args.models.split(",") if item.strip()
    )
    artifacts = _d03_rep_artifacts(
        scenario=args.scenario,
        n=int(args.n),
        rep_id=int(args.rep_id),
        models=models,
        time_mode=args.time_mode,
    )
    elapsed = time.perf_counter() - started
    _say(f"D03 重建完成：chosen={artifacts.chosen_model}，test={len(artifacts.frame)}，{elapsed:.1f}s")

    cfg = artifacts.cfg
    validation = artifacts.data.validation
    treated = validation.treatment == 1
    if int(treated.sum()) < 2:
        raise ValueError("validation 处理组不足 2 人，无法校准成本模型")
    predicted = pol.predict_expected_cost(
        artifacts.cost_model, validation.X[treated], cfg
    )
    keys = validation.keys.loc[treated].reset_index(drop=True)
    observed = _observations_for_keys(
        artifacts.dataset, keys, ("coupon_cost",)
    )["coupon_cost"].to_numpy(dtype=np.float64)
    calibration = ev.calibrate_cost_predictions(predicted, observed)
    calibration["n_validation_treated"] = int(treated.sum())
    calibration["n_validation_total"] = int(validation.n)
    calibration["chosen_model"] = artifacts.chosen_model
    return artifacts.frame.copy(), calibration, artifacts.chosen_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E 阶段正文证据：7 张真实数据表")
    parser.add_argument("--input", type=Path, default=None, help="9 列 CSV；给了就不用 --from-d03")
    parser.add_argument("--from-d03", action="store_true", default=False)
    parser.add_argument("--scenario", default="L1_main")
    parser.add_argument("--n", type=int, default=200_000)
    parser.add_argument("--rep-id", type=int, default=0)
    parser.add_argument("--models", default="", help="逗号分隔；默认 5 个全跑")
    parser.add_argument("--time-mode", default="static")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "out" / "e_evidence")
    parser.add_argument("--tables-dir", type=Path, default=ROOT / "outputs" / "tables")
    parser.add_argument("--small-pools", default="")
    parser.add_argument("--budgets", default="")
    parser.add_argument("--widths", default="")
    parser.add_argument("--scale-pools", default="")
    parser.add_argument("--scale-budgets", default="")
    parser.add_argument("--random-seeds", type=int, default=None)
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--skip-small-pool", action="store_true")
    parser.add_argument("--skip-bucket", action="store_true")
    parser.add_argument("--skip-random", action="store_true")
    parser.add_argument("--skip-decomposition", action="store_true")
    parser.add_argument("--skip-conservative", action="store_true")
    parser.add_argument("--skip-scale", action="store_true")
    parser.add_argument("--scale-milp-time-limit", type=float, default=None)
    parser.add_argument("--smoke", action="store_true", help="缩小网格，只验证链路")
    args = parser.parse_args(argv)
    if args.input is not None and args.from_d03:
        parser.error("--input 与 --from-d03 只能二选一")
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    args.tables_dir = (
        args.tables_dir if args.tables_dir.is_absolute() else ROOT / args.tables_dir
    )
    if args.input is not None and not args.input.is_absolute():
        args.input = ROOT / args.input
    if args.smoke:
        # 冒烟产物绝不能落在正式 outputs/tables，避免小 n 数字被误当正文证据。
        args.tables_dir = args.out_dir / "tables"

    protocol = load_v3_protocol()
    cfg = protocol.config
    started_at = _now()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.tables_dir.mkdir(parents=True, exist_ok=True)

    calibration: dict = {"status": "not_run"}
    chosen_model = "unknown"
    if args.input is not None:
        frame = _load_input(args.input)
        calibration = {
            "status": "unavailable_input_csv",
            "reason": "输入 CSV 没有 validation 切分与成本模型，校准必须用 --from-d03",
        }
        source = str(args.input)
        _say(f"读入 {args.input}：{len(frame)} 行")
    else:
        frame, calibration, chosen_model = _build_from_d03(args)
        source = f"d03:{args.scenario}:n={args.n}:rep={args.rep_id}"
    frame = frame.sort_values("user_id", kind="stable").reset_index(drop=True)
    require_grid_frame(frame)
    n_rows = len(frame)

    frame_path = args.out_dir / f"frame_rep{args.rep_id}.csv"
    _write_csv(frame, frame_path)
    frame_sha = _sha256(frame_path)

    budgets = _parse_floats(args.budgets) if args.budgets else [
        float(x) for x in cfg.require("policy.budget.per_user_grid_cny")
    ]
    if args.smoke:
        budgets = budgets[:2]
    _say(f"帧 {n_rows} 行；预算 {budgets}；chosen={chosen_model}")

    outputs: dict[str, str] = {}
    timings: dict[str, float] = {}
    small_pools_used: list[int] | None = None
    widths_used: list[float] | None = None
    seeds_used: int | None = None
    scale_pools_used: list[object] | None = None
    scale_budgets_used: list[float] | None = None

    if not args.skip_small_pool:
        pools = _parse_ints(args.small_pools) if args.small_pools else [
            int(x) for x in cfg.require("policy.optimization.small_exact.pool_sizes")
        ]
        if args.smoke:
            pools = [p for p in pools if p <= max(20, n_rows // 10)] or [20]
        pools = [p for p in pools if p <= n_rows]
        if not pools:
            raise ValueError(f"没有 ≤ {n_rows} 的小池大小")
        _say(f"小池求解器互证：pools={pools}")
        started = time.perf_counter()
        table = ev.small_pool_solver_table(
            frame, cfg, pool_sizes=pools, budgets=budgets,
            seed_offset=args.seed_offset, include_brute_force=True,
        )
        timings["small_pool"] = time.perf_counter() - started
        small_pools_used = list(pools)
        path = args.tables_dir / "v3_phase_E_small_pool.csv"
        _write_csv(table, path)
        outputs["small_pool"] = _rel(path)

    if not args.skip_bucket:
        pool_size = int(cfg.require("policy.optimization.bucket_convergence.pool_size"))
        pool_size = min(pool_size, n_rows)
        widths = _parse_floats(args.widths) if args.widths else None
        _say(f"桶宽收敛：pool={pool_size} widths={widths or 'config'}")
        started = time.perf_counter()
        table = ev.bucket_convergence_table(
            frame, cfg, pool_size=pool_size, budgets=budgets,
            widths=widths, seed_offset=args.seed_offset,
        )
        timings["bucket"] = time.perf_counter() - started
        widths_used = (
            list(widths) if widths is not None
            else [float(x) for x in cfg.require("policy.optimization.bucket_convergence.widths_cny")]
        )
        path = args.tables_dir / "v3_phase_E_bucket_convergence.csv"
        _write_csv(table, path)
        outputs["bucket_convergence"] = _rel(path)

    if not args.skip_random:
        seeds = args.random_seeds
        if args.smoke and seeds is None:
            seeds = 5
        _say(f"随机基线：budgets={len(budgets)} seeds={seeds or 'config'}")
        started = time.perf_counter()
        long_frame, summary = ev.random_baseline_table(
            frame, cfg, budgets=budgets, seeds=seeds, seed_offset=args.seed_offset
        )
        timings["random"] = time.perf_counter() - started
        seeds_used = (
            int(seeds) if seeds is not None
            else int(cfg.require("policy.random_baseline.seeds_per_frozen_dataset_and_budget"))
        )
        long_path = args.tables_dir / "v3_phase_E_random_long.csv"
        summary_path = args.tables_dir / "v3_phase_E_random_summary.csv"
        _write_csv(long_frame, long_path)
        _write_csv(summary, summary_path)
        outputs["random_long"] = _rel(long_path)
        outputs["random_summary"] = _rel(summary_path)

    if not args.skip_decomposition:
        pool_size = int(cfg.require("policy.optimization.bucket_convergence.pool_size"))
        pool_size = min(pool_size, n_rows)
        _say(f"误差分解：pool={pool_size}")
        started = time.perf_counter()
        table = ev.error_decomposition_table(
            frame, cfg, pool_size=pool_size, budgets=budgets,
            seed_offset=args.seed_offset,
        )
        timings["decomposition"] = time.perf_counter() - started
        path = args.tables_dir / "v3_phase_E_decomposition.csv"
        _write_csv(table, path)
        outputs["decomposition"] = _rel(path)

    if not args.skip_conservative:
        seeds = args.random_seeds
        if args.smoke and seeds is None:
            seeds = 5
        _say("三种预算口径：expected / buffered / worst-case face")
        started = time.perf_counter()
        table = ev.conservative_comparison_table(
            frame, cfg, budgets=budgets, seeds=seeds, seed_offset=args.seed_offset
        )
        timings["conservative"] = time.perf_counter() - started
        if seeds_used is None:
            seeds_used = (
                int(seeds) if seeds is not None
                else int(cfg.require("policy.random_baseline.seeds_per_frozen_dataset_and_budget"))
            )
        path = args.tables_dir / "v3_phase_E_conservative.csv"
        _write_csv(table, path)
        outputs["conservative"] = _rel(path)

    if not args.skip_scale:
        pools = _parse_pools(args.scale_pools) if args.scale_pools else list(
            cfg.require("policy.optimization.large.pool_sizes")
        )
        pools = [
            pool for pool in pools
            if isinstance(pool, str) or int(pool) <= n_rows
        ]
        if not pools:
            pools = ["full_test"]
        scale_budgets = (
            _parse_floats(args.scale_budgets) if args.scale_budgets else budgets
        )
        _say(f"规模扫描：pools={pools} budgets={scale_budgets}")
        started = time.perf_counter()
        table = ev.scale_table(
            frame, cfg, pool_sizes=pools, budgets=scale_budgets,
            seed_offset=args.seed_offset, include_milp=True,
            milp_time_limit_seconds=args.scale_milp_time_limit,
        )
        timings["scale"] = time.perf_counter() - started
        scale_pools_used = list(pools)
        scale_budgets_used = list(scale_budgets)
        path = args.tables_dir / "v3_phase_E_scale.csv"
        _write_csv(table, path)
        outputs["scale"] = _rel(path)

    calibration_path = args.tables_dir / "v3_phase_E_calibration.json"
    _write_json(calibration, calibration_path)
    outputs["calibration"] = _rel(calibration_path)

    meta = {
        "phase": "E_evidence",
        "status": "evidence_not_formal_R",
        "created_at": started_at,
        "finished_at": _now(),
        "source": source,
        "scenario": args.scenario,
        "n_rows": n_rows,
        "rep_id": args.rep_id,
        "chosen_model": chosen_model,
        "frame_path": _rel(frame_path),
        "frame_sha256": frame_sha,
        "budgets_cny_per_user": budgets,
        "seed_offset": args.seed_offset,
        "small_pools_used": small_pools_used,
        "bucket_widths_used_cny": widths_used,
        "random_seeds_used": seeds_used,
        "scale_pools_used": scale_pools_used,
        "scale_budgets_cny_per_user": scale_budgets_used,
        "timings_seconds": {key: round(value, 3) for key, value in timings.items()},
        "outputs": outputs,
        "notes": [
            "小池/桶宽/误差分解的预算是 per_user_budget × pool_size，不是全量预算。",
            "分币 DP 的精确性只对分币整数化问题成立；MILP 只有 gap=0 才可说最优。",
            "LP 是上界，不是可行策略。",
            "桶宽收敛只出曲线，未设通过阈值。",
            "observed_value 需观测结局与 OPE，属 F 阶段；本表只给 DGP 真值审计值。",
        ],
    }
    meta_path = args.tables_dir / "v3_phase_E_evidence_meta.json"
    _write_json(meta, meta_path)
    _say(f"完成：{len(outputs)} 个产物；总耗时 {sum(timings.values()):.1f}s")
    print(json.dumps({"meta": _rel(meta_path), "outputs": outputs},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
