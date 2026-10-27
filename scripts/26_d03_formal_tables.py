"""D03 正式 R 的报告层入口：从合并后的两张表复算选模/校准/配对策略/合规。

输入（``scripts/25_merge_d03_formal.py`` 的产物）：
``outputs/tables/v3_phase_D03_formal_per_rep.csv``、
``outputs/tables/v3_phase_D03_formal_policy_grid.csv``。

输出（``outputs/tables/``，UTF-8-SIG）：
``v3_phase_D03_formal_selection.csv``、``_calibration.csv``、``_policy_value.csv``、
``_paired_diff.csv``、``_paired_diff_chosen.csv``、``_oracle.csv``、``_compliance.csv``、
``_report_meta.json``。

本脚本只做聚合，不重跑模型、不读逐用户表；所有数字可由上述两张表重建。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.evaluation import v3_d03_formal as formal  # noqa: E402
from causal_growth.policy.v3_policy_grid import POLICIES  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")
BASELINE = "business_rule_new_user_then_cart"


def _now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(frame: pd.DataFrame, path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[D03 formal] wrote {_rel(path)} ({len(frame)} rows)")
    return {
        "rows": int(len(frame)),
        "sha256": _sha256(path),
        "path": _rel(path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D03 正式 R 报告层聚合")
    parser.add_argument(
        "--per-rep",
        type=Path,
        default=ROOT / "outputs" / "tables" / "v3_phase_D03_formal_per_rep.csv",
    )
    parser.add_argument(
        "--grid",
        type=Path,
        default=ROOT / "outputs" / "tables" / "v3_phase_D03_formal_policy_grid.csv",
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "tables")
    parser.add_argument("--expected-reps", type=int, default=200)
    args = parser.parse_args(argv)
    args.per_rep = args.per_rep if args.per_rep.is_absolute() else ROOT / args.per_rep
    args.grid = args.grid if args.grid.is_absolute() else ROOT / args.grid
    args.out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir

    per_rep = pd.read_csv(args.per_rep, encoding="utf-8-sig")
    grid = pd.read_csv(args.grid, encoding="utf-8-sig")
    cfg = load_v3_protocol().config
    budgets = [float(value) for value in cfg.require("policy.budget.per_user_grid_cny")]
    formal.require_formal_tables(
        per_rep, grid,
        expected_reps=args.expected_reps,
        expected_budgets=budgets,
    )

    started = _now()
    outputs: dict[str, dict[str, object]] = {}
    selection = formal.selection_frequency(per_rep)
    outputs["selection"] = _write(selection, args.out_dir / "v3_phase_D03_formal_selection.csv")

    calibration = pd.concat(
        [
            formal.calibration_summary(per_rep, chosen_only=False),
            formal.calibration_summary(per_rep, chosen_only=True),
        ],
        ignore_index=True,
    )
    outputs["calibration"] = _write(
        calibration, args.out_dir / "v3_phase_D03_formal_calibration.csv"
    )

    policy_value = formal.policy_value_summary(grid)
    outputs["policy_value"] = _write(
        policy_value, args.out_dir / "v3_phase_D03_formal_policy_value.csv"
    )

    paired = formal.paired_policy_difference(grid, BASELINE, chosen_only=False)
    outputs["paired_diff"] = _write(
        paired, args.out_dir / "v3_phase_D03_formal_paired_diff.csv"
    )
    paired_chosen = formal.paired_policy_difference(grid, BASELINE, chosen_only=True)
    outputs["paired_diff_chosen"] = _write(
        paired_chosen, args.out_dir / "v3_phase_D03_formal_paired_diff_chosen.csv"
    )

    oracle = formal.oracle_regret_summary(grid)
    outputs["oracle"] = _write(oracle, args.out_dir / "v3_phase_D03_formal_oracle.csv")

    compliance = formal.compliance_summary(grid)
    outputs["compliance"] = _write(
        compliance, args.out_dir / "v3_phase_D03_formal_compliance.csv"
    )

    meta = {
        "phase": "D03_formal_report",
        "status": "aggregated_from_merged_tables",
        "created_at": started,
        "finished_at": _now(),
        "inputs": {
            "per_rep": {
                "path": _rel(args.per_rep),
                "rows": int(len(per_rep)),
                "sha256": _sha256(args.per_rep),
            },
            "policy_grid": {
                "path": _rel(args.grid),
                "rows": int(len(grid)),
                "sha256": _sha256(args.grid),
            },
        },
        "n_reps": int(per_rep["rep_id"].nunique()),
        "models": sorted(str(value) for value in per_rep["model"].unique()),
        "policies": list(POLICIES),
        "budgets_cny_per_user": budgets,
        "baseline_for_paired_diff": BASELINE,
        "chosen_model_counts": {
            str(key): int(value) for key, value in
            per_rep.groupby("model")["chosen"].sum().items()
        },
        "outputs": outputs,
        "notes": [
            "所有策略比较都在同一 rep、同一模型、同一预算上配对；chosen_only 是线上口径子集。",
            "预测成本口径与真实成本口径的合规率分别列示，不可互相替代。",
            "oracle 差距是事后上界，只用于解释选模/策略损失，不可当线上可得收益。",
        ],
    }
    meta_path = args.out_dir / "v3_phase_D03_formal_report_meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[D03 formal] wrote {_rel(meta_path)}")
    print(json.dumps({
        "selection": selection.to_dict("records"),
        "chosen_model_counts": meta["chosen_model_counts"],
        "files": {key: value["path"] for key, value in outputs.items()},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
