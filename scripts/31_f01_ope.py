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
import hashlib
import json
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
    parser.add_argument("--smoke", action="store_true", help="缩小链路，只验证工程")
    args = parser.parse_args(argv)
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    args.tables_dir = (
        args.tables_dir if args.tables_dir.is_absolute() else ROOT / args.tables_dir
    )
    if args.smoke:
        args.tables_dir = args.out_dir / "tables"
        args.evidence_dir = args.out_dir / "evidence"
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
    )
    recon = f01.ope_vs_audit_table(bundle, audit_table, cfg)

    artifacts: dict[str, dict[str, object]] = {}
    tables = {
        "policy_meta": (args.tables_dir / "v3_phase_F01_policy_meta.csv", policy_meta_frame),
        "value": (args.tables_dir / "v3_phase_F01_value.csv", bundle.value_table),
        "contrast": (args.tables_dir / "v3_phase_F01_contrast.csv", bundle.contrast_table),
        "cost": (args.tables_dir / "v3_phase_F01_cost.csv", bundle.cost_table),
        "family": (args.tables_dir / "v3_phase_F01_family.csv", bundle.family),
        "audit": (args.tables_dir / "v3_phase_F01_audit.csv", audit_table),
        "ope_vs_audit": (args.tables_dir / "v3_phase_F01_ope_vs_audit.csv", recon),
    }
    for name, (path, frame) in tables.items():
        artifacts[name] = _write_table(path, frame)
        _say(f"写出 {name}: {path}（{len(frame)} 行）")

    if not args.smoke:
        _write_json(evidence_dir / "freeze.json", manifest)
        if file_sha256(evidence_dir / "freeze.json") != freeze_file_sha256:
            raise RuntimeError("导出到 outputs/evidence 的 freeze.json 字节不一致")

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
        "budgets_cny_per_user": budgets,
        "family": f01.config_family(cfg),
        "family_alpha_one_sided": float(
            cfg.require("evaluation.decision.benefit_evidence.family_alpha_one_sided")
        ),
        "config_hash": cfg.hash(64),
        "source_hashes": source_hashes,
        "source_hash_combined": source_hash_combined,
        "reference_frame": reference_meta,
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
            "total": time.perf_counter() - total_started,
        },
        "artifacts": artifacts,
    }
    meta_path = args.out_dir / "meta.json"
    _write_json(meta_path, meta)
    if not args.smoke:
        _write_json(evidence_dir / "meta.json", meta)
    _say(f"meta 写出：{meta_path}；总耗时 {meta['stage_seconds']['total']:.1f}s")

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
