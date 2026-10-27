"""合并 F02 正式分片 → 逐 rep 表 + 聚合表 + 代表 rep 证据包。

为什么必须单独合并
------------------
正式 200 rep 按分片跑（``29_f02_formal.py``），每个分片只知道自己那几十个 rep。
GOAL 的正式口径是**合计 200 rep**；分片 summary 的 ``n_reps=50`` 不能拿来判定。
合并时必须回答四个问题：

1. 200 个 rep 是否恰好各出现一次（缺 rep、重 rep、越界都要报错）；
2. 每个 rep 是否 ``status=formal``、登记号非空、冻结先于审计；
3. 所有分片是否跑同一份协议（``config_hash`` / ``source_hashes`` 全一致）；
4. 聚合是否只报 rep 级通过率与 MC 标准误，不把 200 个 p 值合并成一个"总显著"。

纪律
----
- 只读逐 rep 产物，不重跑模型、不读逐用户真值；
- 逐 rep 的 decision / guardrail / ITT 表带上 ``freeze_hash`` 等绑定列后落
  ``outputs/tables/``，保证聚合数字可反查；
- 代表 rep 的证据包显式排除 ``per_user.csv`` 与 ``audit_truth.csv``（太大且含真值），
  排除项写进 ``coverage.json``。

用法::

    python scripts/30_merge_f02_formal.py \
        --shard-root out/f02_formal/shard0 --shard-root out/f02_formal/shard1 \
        --shard-root out/f02_formal/shard2 --shard-root out/f02_formal/shard3 \
        --expected-reps 200 \
        --evidence-dir outputs/evidence/f02_formal_rep0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from causal_growth.evaluation.v3_f02_formal import aggregate_f02, load_formal_rep  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")

_REP_BINDING_KEYS = (
    "freeze_hash", "decision_hash", "guardrail_hash",
    "per_user_hash", "observed_sql_hash", "selected_model", "selected_policy",
)
_EVIDENCE_FILES = (
    "arm_summary.csv",
    "itt_contrasts.csv",
    "decision.csv",
    "guardrail.csv",
    "decision.json",
    "freeze.json",
    "manifest.json",
    "five_tables/manifest.json",
)
_EVIDENCE_EXCLUDED = {
    "per_user.csv": "逐用户观测（每 rep 约 15.4 MB）；聚合只依赖汇总表",
    "audit_truth.csv": "逐用户真值；冻结后才生成，仅审计用",
    "audit_policy_values.csv": "聚合审计价值；正式聚合不依赖它",
    "audit_arm_contrasts.csv": "聚合审计对照；正式聚合不依赖它",
    "five_tables/": "五表与 SQL 产物体积大；只导出 manifest.json，原始表可由快照 + rep 0 重建",
}


def _now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(f"[F02 merge {datetime.now(BEIJING).strftime('%H:%M:%S')}] {message}", flush=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _rep_dirs(shard_root: Path) -> list[Path]:
    return sorted(
        (path.parent for path in shard_root.glob("rep*/manifest.json")),
        key=lambda path: int(path.name[3:]),
    )


def _read_shard_summary(shard_root: Path) -> dict[str, Any]:
    path = shard_root / "summary.json"
    _require(path.is_file(), f"{shard_root} 缺少 summary.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("phase") == "F02_formal_shard",
             f"{path} 不是 F02 分片 summary")
    _require(payload.get("status") == "formal", f"{path} 不是 formal 分片")
    _require(not payload.get("failures"), f"{path} 记录了失败 rep：{payload['failures']}")
    return payload


def _with_bindings(frame: pd.DataFrame, rep: dict[str, Any]) -> pd.DataFrame:
    manifest = rep["manifest"]
    bound = frame.copy()
    bound.insert(0, "rep_id", rep["rep_id"])
    bound.insert(1, "n_users", rep["n_users"])
    for key in _REP_BINDING_KEYS:
        bound[key] = manifest.get(key)
    return bound


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    _say(f"wrote {path.relative_to(ROOT).as_posix()} ({len(frame)} rows)")


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _say(f"wrote {path.relative_to(ROOT).as_posix()}")


def _export_rep0_evidence(rep0_dir: Path, target: Path, aggregate_files: list[Path]) -> None:
    _require(rep0_dir.is_dir(), f"缺少代表 rep 目录 {rep0_dir}")
    target.mkdir(parents=True, exist_ok=True)
    (target / "aggregate").mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for relative in _EVIDENCE_FILES:
        source = rep0_dir / relative
        _require(source.is_file(), f"代表 rep 缺文件 {source}")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        records.append({
            "path": relative,
            "source": str(source),
            "sha256": _sha256(destination),
            "bytes": destination.stat().st_size,
        })
    for path in aggregate_files:
        records.append({
            "path": f"aggregate/{path.name}",
            "source": path.relative_to(ROOT).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        })
        shutil.copy2(path, target / "aggregate" / path.name)
    coverage = {
        "phase": "F02_formal_evidence",
        "created_at": _now(),
        "representative_rep_dir": rep0_dir.relative_to(ROOT).as_posix(),
        "files": records,
        "excluded": [
            {"path": name, "reason": reason}
            for name, reason in _EVIDENCE_EXCLUDED.items()
        ],
        "note": (
            "manifest.json 含冻结后聚合的 audit_true_arm_means（整臂均值），"
            "不含逐用户真值；聚合表只由 decision/guardrail/itt 的观测列生成。"
        ),
    }
    _write_json(coverage, target / "coverage.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并 F02 正式分片并导出证据")
    parser.add_argument("--shard-root", action="append", required=True,
                        help="分片输出根目录；可重复")
    parser.add_argument("--expected-reps", type=int, default=200)
    parser.add_argument("--tables-dir", type=Path, default=ROOT / "outputs" / "tables")
    parser.add_argument("--evidence-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    tables_dir = args.tables_dir if args.tables_dir.is_absolute() else ROOT / args.tables_dir
    shard_roots = [
        (path if path.is_absolute() else ROOT / path)
        for path in (Path(item) for item in args.shard_root)
    ]
    summaries = []
    rep_dirs: list[Path] = []
    for shard_root in shard_roots:
        _require(shard_root.is_dir(), f"分片目录不存在：{shard_root}")
        summary = _read_shard_summary(shard_root)
        summaries.append({"root": shard_root.relative_to(ROOT).as_posix(), **{
            key: summary[key] for key in (
                "formal_approval", "config_hash", "source_hashes_sha256",
                "n_per_rep", "policy", "models", "rep_ids_requested",
                "completed_rep_ids", "started_at", "finished_at",
            )
        }})
        rep_dirs.extend(_rep_dirs(shard_root))
    _say(f"分片 {len(shard_roots)} 个；rep 目录 {len(rep_dirs)} 个")

    claims, guardrail, itt, spend, meta = aggregate_f02(
        rep_dirs, expected_reps=args.expected_reps
    )
    reps = [load_formal_rep(path) for path in rep_dirs]

    aggregate_paths = [
        tables_dir / "v3_phase_F02_formal_per_rep_claims.csv",
        tables_dir / "v3_phase_F02_formal_per_rep_guardrail.csv",
        tables_dir / "v3_phase_F02_formal_per_rep_itt.csv",
        tables_dir / "v3_phase_F02_formal_claims.csv",
        tables_dir / "v3_phase_F02_formal_guardrail.csv",
        tables_dir / "v3_phase_F02_formal_itt.csv",
        tables_dir / "v3_phase_F02_formal_spend.csv",
    ]
    _write_csv(
        pd.concat([_with_bindings(rep["decision"], rep) for rep in reps], ignore_index=True),
        aggregate_paths[0],
    )
    _write_csv(
        pd.concat([_with_bindings(rep["guardrail"], rep) for rep in reps], ignore_index=True),
        aggregate_paths[1],
    )
    _write_csv(
        pd.concat([_with_bindings(rep["itt"], rep) for rep in reps], ignore_index=True),
        aggregate_paths[2],
    )
    _write_csv(claims, aggregate_paths[3])
    _write_csv(guardrail, aggregate_paths[4])
    _write_csv(itt, aggregate_paths[5])
    _write_csv(spend, aggregate_paths[6])

    meta.update({
        "created_at": _now(),
        "shards": summaries,
        "status": "formal_r",
        "policy": reps[0]["manifest"].get("selected_policy"),
        "tables": {
            path.name: {"sha256": _sha256(path), "rows": int(len(pd.read_csv(path, encoding="utf-8-sig")))}
            for path in aggregate_paths
        },
        "notes": [
            "通过率按 rep 计，区间为 Clopper-Pearson 精确区间；不做跨 rep 的 p 值合并。",
            "差值的 mc_se 是 rep 间标准差除以 sqrt(R)，描述 rep 抽样波动。",
            "每个 rep 的 decision.csv 在其自身 Holm 家族内独立判定。",
        ],
    })
    summary_path = tables_dir / "v3_phase_F02_formal_summary.json"
    _write_json(meta, summary_path)

    if args.evidence_dir is not None:
        evidence = (
            args.evidence_dir if args.evidence_dir.is_absolute() else ROOT / args.evidence_dir
        )
        rep0_dirs = [path for path in rep_dirs if path.name == "rep0"]
        _require(len(rep0_dirs) == 1, "代表 rep 0 目录必须恰好一个")
        _export_rep0_evidence(rep0_dirs[0], evidence, aggregate_paths)

    coupon = claims.loc[claims["claim"] == "coupon_worth_issuing"].iloc[0]
    targeting = claims.loc[claims["claim"] == "targeting_better_than_random"].iloc[0]
    guard = guardrail.iloc[0]
    print(json.dumps({
        "n_reps": int(meta["n_reps"]),
        "coupon_worth_issuing": {
            "pass_count": int(coupon["pass_count"]),
            "pass_rate": float(coupon["pass_rate"]),
            "ci": [float(coupon["pass_rate_ci_low"]), float(coupon["pass_rate_ci_high"])],
        },
        "targeting_better_than_random": {
            "pass_count": int(targeting["pass_count"]),
            "pass_rate": float(targeting["pass_rate"]),
            "ci": [float(targeting["pass_rate_ci_low"]), float(targeting["pass_rate_ci_high"])],
        },
        "guardrail": {
            "pass_count": int(guard["pass_count"]),
            "pass_rate": float(guard["pass_rate"]),
        },
        "summary": summary_path.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
