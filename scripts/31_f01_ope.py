"""F01 观测闭环入口：冻结 D03 rep 的名单 → 观测 OPE → 冻结后真值审计（薄入口）。

顺序（脚本硬编码，不提供调换开关）
----------------------------------
1. 重建 D03 单 rep（``_d03_rep_artifacts``，只取 7 列选人表与设计概率）；
2. 在选人表上构造 4 个策略 × 配置预算网格的名单；
3. 写 ``freeze.json``（名单/用户顺序/设计概率/配置与源码哈希）并**重读复算**；
4. 冻结校验通过后，才拼观测结局、拟合 OPE nuisance、合并真值做 ``audit_`` 审计。

``--smoke`` 只缩小 n 与预算网格，产物落在 ``out/`` 下，绝不写 ``outputs/tables``。

用法::

    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\31_f01_ope.py \\
        --scenario L1_main --n 200000 --rep-id 0 \\
        --out-dir out/f01_ope --tables-dir outputs/tables
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.data.v3_pipeline import pipeline_source_hashes  # noqa: E402
from causal_growth.data.v3_storage import dataframe_sha256, file_sha256  # noqa: E402
from causal_growth.estimate.v3_models import (  # noqa: E402
    D03_EXPORT_COLUMNS,
    _d03_rep_artifacts,
    _observations_for_keys,
)
from causal_growth.evaluation import v3_f01 as f01  # noqa: E402
from causal_growth.policy import v3_policy as pol  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")
SOURCE_LABEL = "合成数据 / 已知 DGP"


def _now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(f"[{_now()}] {message}", flush=True)


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
    except OSError:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(value), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _json_safe(value: object) -> object:
    """把 NaN/inf 与 numpy 标量转成严格 JSON 可表示的 Python 值。"""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(float(value)) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _write_table(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return {
        "path": str(path),
        "rows": int(len(frame)),
        "sha256": file_sha256(path),
    }


def _write_csv_gz(path: Path, frame: pd.DataFrame) -> None:
    """写确定性 gzip CSV（``mtime=0``），保证同一帧每次跑出同样字节。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = frame.to_csv(index=False, encoding="utf-8").encode("utf-8")
    with path.open("wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as gz:
            gz.write(payload)


def _budget_list(args: argparse.Namespace, cfg: object, primary: float) -> list[float]:
    if args.budgets:
        values = [float(item) for item in args.budgets.split(",") if item.strip()]
    elif args.smoke:
        values = [primary]
    else:
        values = [float(value) for value in cfg.require("policy.budget.per_user_grid_cny")]
        values.append(primary)
    deduped: list[float] = []
    for value in sorted(values):
        if not any(np.isclose(value, kept, rtol=0.0, atol=1e-12) for kept in deduped):
            deduped.append(value)
    if not deduped or min(deduped) <= 0.0:
        raise ValueError("预算必须为正")
    return deduped


def _rel_posix(path: Path) -> str:
    """登记表里一律存相对 ROOT 的 POSIX 路径，换机器也能复算。"""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _refresh_top_registry(target: Path, *, freeze_path: Path, meta_path: Path) -> int:
    """把 F01 的 freeze/meta 刷进顶层索引，并对**全表**逐条复算。

    顶层 ``outputs/evidence/coverage.json`` 只收录 freeze/meta 这类登记文件，
    逐用户大文件由目录级 coverage.json 负责（AGENTS §12.1）。此前顶层索引没人
    刷新，留下过旧 ``freeze_id`` 与旧 ``source``（指向已被后续运行取代的
    ``out/f01_ope/``），所以这里除刷新自身前缀外还要复算所有记录：任何文件缺失、
    sha256 或 bytes 不符都抛错。登记表只准加强，不准削弱（§12.3）。
    """
    top_path = ROOT / "outputs" / "evidence" / "coverage.json"
    if not top_path.is_file():
        raise FileNotFoundError(f"顶层证据登记表缺失：{top_path}")
    top = json.loads(top_path.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = list(top.get("records", []))
    prefix = _rel_posix(target) + "/"

    upsert: dict[str, dict[str, object]] = {}
    for source, kind in ((freeze_path, "f01_freeze"), (meta_path, "f01_meta")):
        if not source.is_file():
            raise FileNotFoundError(f"运行产物缺失：{source}")
        destination = target / source.name
        if not destination.is_file():
            raise FileNotFoundError(f"证据副本缺失：{destination}")
        if file_sha256(source) != file_sha256(destination):
            raise RuntimeError(
                f"证据副本与运行产物不一致：{source} vs {destination}；"
                "登记前必须重新导出，不能拿旧副本充当本次运行的证据"
            )
        relative = _rel_posix(destination)
        old = next((r for r in records if r.get("target") == relative), None)
        record: dict[str, object] = dict(old) if old is not None else {}
        record["kind"] = kind
        record["source"] = _rel_posix(source)
        record["target"] = relative
        record["bytes"] = destination.stat().st_size
        record["sha256"] = file_sha256(destination)
        if kind == "f01_freeze":
            payload = json.loads(destination.read_text(encoding="utf-8"))
            record["freeze_id"] = payload["freeze_id"]
            record["created_at_in_file"] = payload["created_at"]
        upsert[relative] = record

    stale = 0
    refreshed = len(upsert)
    merged: list[dict[str, object]] = []
    for record in records:
        target_key = str(record.get("target", ""))
        if target_key in upsert:
            merged.append(upsert.pop(target_key))
        elif target_key.startswith(prefix):
            stale += 1
        else:
            merged.append(record)
    merged.extend(upsert.values())

    bad: list[str] = []
    for record in merged:
        path = Path(str(record["target"]))
        path = path if path.is_absolute() else ROOT / path
        if not path.is_file():
            bad.append(f"{record['target']}: 文件缺失")
        elif file_sha256(path) != record["sha256"]:
            bad.append(f"{record['target']}: sha256 不符")
        elif int(record["bytes"]) != path.stat().st_size:
            bad.append(f"{record['target']}: bytes 不符")
    if bad:
        raise RuntimeError(
            "顶层证据登记表与磁盘不一致（改登记表必须全表复算，不能只校验自己那部分）：\n  "
            + "\n  ".join(bad)
        )

    top["records"] = merged
    top["total_bytes"] = sum(int(record["bytes"]) for record in merged)
    top["last_refreshed_at"] = _now()
    top_path.write_text(json.dumps(top, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _say(
        f"更新顶层 coverage.json：{prefix} 下刷新 {refreshed} 条、清理失效 {stale} 条，"
        f"全表 {len(merged)} 条复算一致，total_bytes={top['total_bytes']}"
    )
    return len(merged)


def _export_evidence(
    target: Path,
    *,
    out_dir: Path,
    selection: pd.DataFrame,
    policy_frames: dict[float, pd.DataFrame],
    observed: pd.DataFrame,
    features: np.ndarray,
    truth: pd.DataFrame,
    freeze_path: Path,
    meta_path: Path,
    table_paths: dict[str, Path],
) -> Path:
    """导出可重建 OPE 与审计的逐用户材料，并登记 sha256/行数。

    逐用户大文件以**确定性 gzip**（``mtime=0``）入库，保证重跑字节一致。
    名单长表只落 ``out/``：它能由选人表 + 冻结配置 + ``rep_id`` 逐位重建，
    入库会把证据包从 ~10 MB 抬到 ~80 MB。
    真值文件单独命名并在 coverage 里标注"仅审计"；任何选择/拟合都不得读它。
    """
    import shutil

    target.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []

    def add(source: Path, relative: str, kind: str, rows: int | None = None) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"证据源缺失：{source}")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        record = {
            "kind": kind,
            "source": str(source),
            "target": str(destination),
            "in_repository": True,
            "bytes": destination.stat().st_size,
            "sha256": file_sha256(destination),
        }
        if rows is not None:
            record["rows"] = int(rows)
        records.append(record)

    def write_gz(
        frame: pd.DataFrame,
        destination: Path,
        kind: str,
        *,
        in_repository: bool,
        note: str | None = None,
    ) -> None:
        _write_csv_gz(destination, frame)
        record: dict[str, object] = {
            "kind": kind,
            "source": "generated_from_frozen_inputs",
            "target": str(destination),
            "in_repository": bool(in_repository),
            "encoding": "utf-8 csv in gzip(mtime=0)",
            "bytes": destination.stat().st_size,
            "sha256": file_sha256(destination),
            "rows": int(len(frame)),
            "dataframe_sha256": dataframe_sha256(frame),
        }
        if note is not None:
            record["note"] = note
        records.append(record)

    write_gz(
        selection.loc[:, list(f01.FREEZE_COLUMNS)],
        target / "selection_7cols.csv.gz",
        "f01_selection",
        in_repository=True,
    )
    write_gz(observed, target / "observed.csv.gz", "f01_observed", in_repository=True)
    feature_frame = pd.DataFrame(
        np.asarray(features, dtype=float),
        columns=[f"x{index}" for index in range(np.asarray(features).shape[1])],
    )
    feature_frame.insert(0, "user_id", observed["user_id"].to_numpy())
    write_gz(feature_frame, target / "features.csv.gz", "f01_features", in_repository=True)
    write_gz(
        truth.loc[:, ["user_id", "tau_true", "cost_true"]],
        target / "truth_audit_only.csv.gz",
        "f01_truth_audit_only",
        in_repository=True,
        note="只用于冻结后的 audit_ 对账，不进入任何名单或拟合",
    )
    mask_rows = []
    for per_user, policy_frame in sorted(policy_frames.items()):
        block = policy_frame.melt(
            id_vars="user_id", value_vars=list(f01.CANDIDATE_POLICIES),
            var_name="policy", value_name="mask",
        )
        block.insert(0, "per_user_budget_cny", float(per_user))
        mask_rows.append(block)
    write_gz(
        pd.concat(mask_rows, ignore_index=True),
        out_dir / "policy_masks_long.csv.gz",
        "f01_masks_derivable",
        in_repository=False,
        note=(
            "不入库：可由 selection_7cols.csv.gz + configs/v3 + rep_id 经 "
            "f01.build_policies 逐位重建；此处只登记哈希与行数"
        ),
    )
    add(freeze_path, "freeze.json", "f01_freeze")
    add(meta_path, "meta.json", "f01_meta")
    for name, path in table_paths.items():
        add(path, f"tables/{path.name}", f"f01_table_{name}")
    mask_record = next(record for record in records if record["kind"] == "f01_masks_derivable")
    coverage = {
        "phase": "F01",
        "purpose": "F01 单 rep 历史留出 OPE 证据包：冻结名单、逐用户观测/特征、真值审计与全部表",
        "created_at": _now(),
        "records": records,
        "total_bytes": sum(int(record["bytes"]) for record in records),
        "in_repository_bytes": sum(
            int(record["bytes"]) for record in records if record.get("in_repository")
        ),
        "rebuild": [
            "名单：f01.build_policies(read_csv('selection_7cols.csv.gz'), cfg, "
            "budget_per_user=<网格>, seed_index=rep_id)",
            "OPE：f01.ope_bundle(read_csv('observed.csv.gz'), features(read_csv('features.csv.gz')), "
            "policy_frames, cfg, seed_index=rep_id)",
            "真值审计：f01.truth_audit_table(selection, policy_frames, "
            "read_csv('truth_audit_only.csv.gz'), freeze_id=freeze.json.freeze_id, manifest=freeze.json)",
            "随机分布：f01.random_policy_distribution(...)，种子数/偏移见 meta.random_policy_distribution",
        ],
        "excluded": [
            {
                "path": "policy_masks_long.csv.gz",
                "reason": (
                    f"长表 {mask_record['rows']} 行、gzip 后 {int(mask_record['bytes']) / 1e6:.2f} MB；"
                    "可由选人表 + 冻结配置 + rep_id 逐位重建，只落 out/ 并登记哈希"
                ),
            },
            {
                "path": "D03 全链路中间产物",
                "reason": "可由 31 号脚本以同一 rep/n 重建；本包已含其 7 列选人表与观测表",
            },
        ],
        "truth_usage": "truth_audit_only.csv.gz 只用于冻结后的 audit_ 对账，不进入任何名单或拟合",
    }
    coverage_path = target / "coverage.json"
    _write_json(coverage_path, coverage)
    _refresh_top_registry(target, freeze_path=freeze_path, meta_path=meta_path)
    return coverage_path


def _check_reference_frame(path: Path, selection: pd.DataFrame) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"参考帧不存在：{path}")
    reference = pd.read_csv(path, encoding="utf-8-sig")
    if tuple(reference.columns) != D03_EXPORT_COLUMNS:
        raise ValueError(f"参考帧列应为 {D03_EXPORT_COLUMNS}，收到 {tuple(reference.columns)}")
    reference_selection = reference.loc[:, list(f01.FREEZE_COLUMNS)]
    ours = selection.loc[:, list(f01.FREEZE_COLUMNS)].reset_index(drop=True)
    if dataframe_sha256(reference_selection) != dataframe_sha256(ours):
        raise ValueError(
            "7 列选人表与参考帧不一致：rep 不可复现，或参考帧不是同一场景/同一 n"
        )
    return {
        "path": str(path),
        "rows": int(len(reference)),
        "selection_sha256": dataframe_sha256(reference_selection),
        "frame_sha256": dataframe_sha256(reference),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F01 观测闭环：冻结、OPE 与真值审计")
    parser.add_argument("--scenario", default="L1_main")
    parser.add_argument("--n", type=int, default=200_000)
    parser.add_argument("--rep-id", type=int, default=0)
    parser.add_argument("--models", default="", help="逗号分隔；默认 5 个全跑")
    parser.add_argument("--time-mode", default="static")
    parser.add_argument("--budgets", default="", help="逗号分隔；默认主预算 + 配置网格")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "out" / "f01_ope")
    parser.add_argument("--tables-dir", type=Path, default=ROOT / "outputs" / "tables")
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--reference-frame", type=Path, default=None)
    parser.add_argument(
        "--random-seeds", type=int, default=200,
        help="random_same_budget 的分布种子数（默认 200，冻结臂只是其中一条）",
    )
    parser.add_argument("--random-seed-offset", type=int, default=0)
    parser.add_argument("--smoke", action="store_true", help="缩小链路，只验证工程")
    args = parser.parse_args(argv)
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    args.tables_dir = (
        args.tables_dir if args.tables_dir.is_absolute() else ROOT / args.tables_dir
    )
    if args.smoke:
        args.tables_dir = args.out_dir / "tables"
        args.evidence_dir = args.out_dir / "evidence"
        args.random_seeds = min(int(args.random_seeds), 20)
        if args.reference_frame is not None:
            parser.error("--smoke 不接受 --reference-frame")
    evidence_dir = (
        args.evidence_dir
        if args.evidence_dir is not None
        else ROOT / "outputs" / "evidence" / "f01_ope"
    )
    evidence_dir = evidence_dir if evidence_dir.is_absolute() else ROOT / evidence_dir
    args.out_dir.mkdir(parents=True, exist_ok=True)

    total_started = time.perf_counter()
    protocol = load_v3_protocol()
    cfg = protocol.config
    f01.check_family_registered(cfg)
    primary = float(
        cfg.require("evaluation.independent_validation.primary_budget_cny_per_user")
    )
    budgets = _budget_list(args, cfg, primary)

    _say(
        f"重建 D03 rep={args.rep_id} scenario={args.scenario} n={args.n} "
        f"（5 模型链路）"
    )
    started = time.perf_counter()
    models = None if not args.models else tuple(
        item.strip() for item in args.models.split(",") if item.strip()
    )
    rep = _d03_rep_artifacts(
        scenario=args.scenario,
        n=int(args.n),
        rep_id=int(args.rep_id),
        models=models,
        time_mode=args.time_mode,
    )
    rebuild_seconds = time.perf_counter() - started
    _say(
        f"D03 重建完成：chosen={rep.chosen_model}，test={len(rep.selection)}，"
        f"{rebuild_seconds:.1f}s"
    )

    # 只碰 7 列选人表与设计概率；此时不构造任何结局表。
    selection = rep.selection.copy()
    if tuple(selection.columns) != f01.FREEZE_COLUMNS:
        raise ValueError("D03 选人表列与 F01 冻结契约不一致")
    test_keys = rep.data.test.keys
    user_id = test_keys["user_id"].to_numpy()
    design = pd.Series(
        np.asarray(rep.data.test.design_probability, dtype=float),
        index=pd.Index(user_id),
        name="design_probability",
    )
    if set(selection["user_id"]) != set(user_id):
        raise ValueError("选人表与 test 切分的用户集合不一致")

    reference_meta: dict[str, object] | None = None
    if args.reference_frame is not None:
        reference_path = (
            args.reference_frame
            if args.reference_frame.is_absolute()
            else ROOT / args.reference_frame
        )
        reference_meta = _check_reference_frame(reference_path, selection)
        _say(f"参考帧 7 列一致：{reference_meta['frame_sha256']}")

    policy_frames: dict[float, pd.DataFrame] = {}
    policy_meta: list[pd.DataFrame] = []
    for per_user in budgets:
        policy_frame, meta = f01.build_policies(
            selection, cfg, budget_per_user=per_user, seed_index=int(args.rep_id)
        )
        policy_frames[per_user] = policy_frame
        policy_meta.append(meta)
    policy_meta_frame = pd.concat(policy_meta, ignore_index=True)
    _say(
        "名单已构造："
        + ", ".join(
            f"{_key:g}元/" + ",".join(
                f"{name}={int(policy_frames[_key][name].sum())}"
                for name in f01.CANDIDATE_POLICIES
            )
            for _key in budgets
        )
    )

    source_hashes = pipeline_source_hashes()
    source_hash_combined = hashlib.sha256(
        json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest = f01.build_freeze_manifest(
        selection,
        policy_frames,
        design,
        scenario=args.scenario,
        n_dgp=int(args.n),
        n_users=len(selection),
        rep_id=int(args.rep_id),
        chosen_model=rep.chosen_model,
        config_hash=cfg.hash(64),
        source_hashes=source_hashes,
        created_at=_now(),
    )
    freeze_path = args.out_dir / "freeze.json"
    _write_json(freeze_path, manifest)
    freeze_file_sha256 = file_sha256(freeze_path)
    with freeze_path.open("r", encoding="utf-8") as handle:
        manifest_reread = json.load(handle)
    freeze_id = f01.verify_freeze_manifest(
        manifest_reread,
        selection,
        policy_frames,
        design,
        scenario=args.scenario,
        n_dgp=int(args.n),
        n_users=len(selection),
        rep_id=int(args.rep_id),
        chosen_model=rep.chosen_model,
        config_hash=cfg.hash(64),
        source_hashes=source_hashes,
    )
    if freeze_id != manifest["freeze_id"]:
        raise RuntimeError("重读后的 freeze_id 与写入值不一致")
    _say(
        f"冻结已落盘并复算通过：freeze_id={freeze_id[:16]}…，"
        f"file_sha256={freeze_file_sha256[:16]}…"
    )

    # 冻结之后才允许构造观测结局表。
    started = time.perf_counter()
    cost_refund = _observations_for_keys(
        rep.dataset, test_keys, ("coupon_cost", "any_refund_30d")
    )
    observed, features = f01.build_observed_frame(
        user_id=user_id,
        treatment=rep.data.test.treatment,
        net_profit=rep.data.test.y,
        coupon_cost=cost_refund["coupon_cost"].to_numpy(),
        any_refund_30d=cost_refund["any_refund_30d"].to_numpy(),
        design_probability=rep.data.test.design_probability,
        features=rep.data.test.X,
    )
    observed_seconds = time.perf_counter() - started
    if set(observed["user_id"]) != set(selection["user_id"]):
        raise ValueError("观测表与冻结名单的用户集合不一致")

    started = time.perf_counter()
    bundle = f01.ope_bundle(
        observed, features, policy_frames, cfg, seed_index=int(args.rep_id)
    )
    ope_seconds = time.perf_counter() - started
    _say(
        f"OPE 完成：nuisance={bundle.nuisance_diagnostics}，"
        f"{ope_seconds:.1f}s；nuisance_sha256={bundle.nuisance_sha256[:16]}…"
    )

    # 冻结校验已通过，且 OPE 已落定，才读取真值做审计。
    truth = rep.frame.loc[:, ["user_id", "tau_true", "cost_true"]]
    audit_table = f01.truth_audit_table(
        selection,
        policy_frames,
        truth,
        freeze_id=freeze_id,
        manifest=manifest_reread,
    )
    recon = f01.ope_vs_audit_table(bundle, audit_table, cfg)
    targeting = f01.targeting_decomposition_table(
        audit_table, n_users=len(selection)
    )
    started = time.perf_counter()
    random_seeds, random_summary = f01.random_policy_distribution(
        bundle,
        observed,
        selection,
        policy_frames,
        truth,
        cfg,
        freeze_id=freeze_id,
        seed_index=int(args.rep_id),
        manifest=manifest_reread,
        n_seeds=int(args.random_seeds),
        seed_offset=int(args.random_seed_offset),
    )
    random_seconds = time.perf_counter() - started
    _say(
        f"随机策略分布完成：{args.random_seeds} 条 × {len(budgets)} 预算，"
        f"{random_seconds:.1f}s"
    )

    artifacts: dict[str, dict[str, object]] = {}
    tables = {
        "policy_meta": (args.tables_dir / "v3_phase_F01_policy_meta.csv", policy_meta_frame),
        "value": (args.tables_dir / "v3_phase_F01_value.csv", bundle.value_table),
        "increment": (args.tables_dir / "v3_phase_F01_increment.csv", bundle.increment_table),
        "contrast": (args.tables_dir / "v3_phase_F01_contrast.csv", bundle.contrast_table),
        "cost": (args.tables_dir / "v3_phase_F01_cost.csv", bundle.cost_table),
        "family": (args.tables_dir / "v3_phase_F01_family.csv", bundle.family),
        "audit": (args.tables_dir / "v3_phase_F01_audit.csv", audit_table),
        "ope_vs_audit": (args.tables_dir / "v3_phase_F01_ope_vs_audit.csv", recon),
        "targeting": (args.tables_dir / "v3_phase_F01_targeting.csv", targeting),
        "random_seeds": (args.tables_dir / "v3_phase_F01_random_seeds.csv", random_seeds),
        "random_summary": (args.tables_dir / "v3_phase_F01_random_summary.csv", random_summary),
    }
    for name, (path, frame) in tables.items():
        artifacts[name] = _write_table(path, frame)
        _say(f"写出 {name}: {path}（{len(frame)} 行）")

    truth_sha_values = audit_table["audit_truth_sha256"].unique()
    if len(truth_sha_values) != 1:
        raise RuntimeError("审计表内的 truth_sha256 不唯一")
    truth_sha = str(truth_sha_values[0])
    meta = {
        "source_label": SOURCE_LABEL,
        "phase": "F01",
        "status": "smoke" if args.smoke else "evidence_pending_independent_review",
        "formal_repetitions": 0,
        "single_rep_evidence": True,
        "note": (
            "单 rep 历史留出 OPE；不是正式 R>0 重复实验，也不构成策略部署建议。"
            "观测估计不读取真值；真值只在 freeze.json 落盘并复算通过后用于 audit_ 对账。"
        ),
        "scenario": args.scenario,
        "n": int(args.n),
        "rep_id": int(args.rep_id),
        "chosen_model": rep.chosen_model,
        "primary_budget_cny_per_user": primary,
        "primary_policy": f01.PRIMARY_POLICY,
        "primary_estimator": f01.PRIMARY_ESTIMATOR,
        "primary_estimator_frozen_by": "source_hashes（源码哈希；该估计量无 YAML 字段）",
        "budgets_cny_per_user": budgets,
        "family": f01.config_family(cfg),
        "family_alpha_one_sided": float(
            cfg.require("evaluation.decision.benefit_evidence.family_alpha_one_sided")
        ),
        "config_hash": cfg.hash(64),
        "source_hashes": source_hashes,
        "source_hash_combined": source_hash_combined,
        "git_commit": _git_commit(),
        "reference_frame": reference_meta,
        "truth_sha256": truth_sha,
        "random_policy_distribution": {
            "n_seeds": int(args.random_seeds),
            "seed_offset": int(args.random_seed_offset),
            "frozen_seed_index": int(args.rep_id),
            "stream": "f01.policy.random",
            "rule": "random_same_budget（同预测预算规则）",
            "seconds": random_seconds,
        },
        "frame_hashes": {
            "selection_dataframe_sha256": dataframe_sha256(
                selection.loc[:, list(f01.FREEZE_COLUMNS)]
            ),
            "observed_dataframe_sha256": dataframe_sha256(observed),
            "features_dataframe_sha256": dataframe_sha256(pd.DataFrame(
                np.asarray(features, dtype=float),
                columns=[f"x{index}" for index in range(np.asarray(features).shape[1])],
            )),
            "truth_dataframe_sha256": truth_sha,
        },
        "freeze": {
            "path": str(freeze_path),
            "file_sha256": freeze_file_sha256,
            "freeze_id": freeze_id,
            "selection_sha256": manifest["selection_sha256"],
            "user_id_sha256": manifest["user_id_sha256"],
            "design_probability_sha256": manifest["design_probability_sha256"],
        },
        "nuisance": bundle.nuisance_diagnostics,
        "nuisance_sha256": bundle.nuisance_sha256,
        "gates": {
            f01.budget_key(per_user): {
                name: {
                    "passed": bool(gate["passed"]),
                    "reasons": list(gate["reasons"]),
                    "ess_treated": gate["ess_treated"],
                    "ess_control": gate["ess_control"],
                }
                for name, gate in gates.items()
            }
            for per_user, gates in bundle.gates.items()
        },
        "stage_seconds": {
            "d03_rebuild": rebuild_seconds,
            "observed_frame": observed_seconds,
            "ope": ope_seconds,
            "random_policy_distribution": random_seconds,
            "total": time.perf_counter() - total_started,
        },
        "artifacts": artifacts,
    }
    meta_path = args.out_dir / "meta.json"
    _write_json(meta_path, meta)
    coverage_path = _export_evidence(
        evidence_dir,
        out_dir=args.out_dir,
        selection=selection,
        policy_frames=policy_frames,
        observed=observed,
        features=features,
        truth=truth,
        freeze_path=freeze_path,
        meta_path=meta_path,
        table_paths={name: path for name, (path, _) in tables.items()},
    )
    _say(
        f"meta 写出：{meta_path}；证据包 {coverage_path}；"
        f"总耗时 {meta['stage_seconds']['total']:.1f}s"
    )

    family = bundle.family
    print("\nF01 主预算确证性家族（DR，单侧 Holm）：")
    print(
        family.loc[
            :, ["contrast", "diff_cny_per_user", "se_diff", "one_sided_p_value",
                "adjusted_alpha", "holm_adjusted_p_value", "holm_alpha",
                "holm_rejected"]
        ].to_string(index=False)
    )
    primary_recon = recon.loc[
        np.isclose(
            recon["per_user_budget_cny"], primary, rtol=0.0, atol=1e-12
        )
    ]
    print("\n主预算 OPE vs 冻结后真值审计：")
    print(
        primary_recon.loc[
            :, ["comparison", "name", "ope_value_cny_per_user",
                "audit_value_cny_per_user", "value_error_cny_per_user"]
        ].to_string(index=False)
    )
    if args.smoke:
        print("\n注意：--smoke 产物只是工程冒烟，不是证据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
