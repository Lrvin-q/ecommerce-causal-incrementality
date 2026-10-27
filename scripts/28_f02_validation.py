"""F02 独立三臂随机验证入口（默认 provisional，不改变正式计数）。

用法::

    python scripts/28_f02_validation.py --n 20000 --rep 0 \
        --policy incremental_profit_rank --models constant \
        --out-dir out/f02_validation

正式状态必须显式给出用户批准的登记号::

    python scripts/28_f02_validation.py ... --status formal --formal-approval <id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from causal_growth.evaluation.v3_f02 import run_f02_rep  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F02 三臂随机验证（provisional 默认）")
    parser.add_argument("--scenario", default="L1_main")
    parser.add_argument("--n", type=int, default=20_000)
    parser.add_argument("--rep", type=int, default=0)
    parser.add_argument("--policy", default="incremental_profit_rank")
    parser.add_argument("--models", default=None, help="逗号分隔的模型子集；缺省全部 5 个")
    parser.add_argument("--time-mode", default="static")
    parser.add_argument("--out-dir", default="out/f02_validation")
    parser.add_argument("--status", default="provisional",
                        choices=("provisional", "engineering", "formal"))
    parser.add_argument("--formal-approval", default=None)
    args = parser.parse_args(argv)

    models = None if not args.models else tuple(
        piece.strip() for piece in args.models.split(",") if piece.strip()
    )
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    result = run_f02_rep(
        scenario=args.scenario,
        n=args.n,
        rep_id=args.rep,
        policy=args.policy,
        models=models,
        time_mode=args.time_mode,
        out_dir=out_dir,
        status=args.status,
        formal_approval=args.formal_approval,
    )
    print(json.dumps({
        "status": result.manifest["status"],
        "scenario": result.scenario,
        "rep_id": result.rep_id,
        "n": result.n,
        "selected_model": result.model,
        "selected_policy": result.policy,
        "freeze_hash": result.freeze_hash,
        "arm_summary": result.arm_summary.to_dict(orient="records"),
        "itt_contrasts": result.contrasts.to_dict(orient="records"),
        "audit_policy_values": result.audit_policy.to_dict(orient="records"),
        "out_dir": str(out_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
