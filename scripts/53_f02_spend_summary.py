"""F02 支出执行汇总：把逐 rep 逐臂表聚成一张一行一臂的表。

回答方案里的问题：F02 的"同预算"在计划口径与真实口径下分别意味着什么。
用法：.venv/Scripts/python.exe scripts/53_f02_spend_summary.py
输入：outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv
输出：outputs/tables/v3_phase_F02_spend_summary.csv（只读证据区，不改它）
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PER_REP = ROOT / "outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv"
OUT = ROOT / "outputs/tables/v3_phase_F02_spend_summary.csv"
ARMS = ["no_coupon", "random_same_budget", "selected_targeted_policy"]


def main() -> int:
    frame = pd.read_csv(PER_REP, encoding="utf-8-sig")
    assert sorted(frame["arm"].unique()) == sorted(ARMS), frame["arm"].unique()
    counts = frame.groupby("arm").size()
    assert (counts == 200).all(), counts
    rows = []
    for arm in ARMS:
        g = frame[frame["arm"] == arm]
        planned = g["budget_cny_per_user"].astype(float)
        realized = g["realized_per_assigned_cny"].astype(float)
        ratio = g["realized_to_predicted"].dropna().astype(float)
        rows.append({
            "arm": arm,
            "reps": int(len(g)),
            "predicted_per_assigned_cny_mean": float(g["predicted_per_assigned_cny"].mean()),
            "realized_per_assigned_cny_mean": float(realized.mean()),
            "realized_per_assigned_cny_median": float(realized.median()),
            "realized_to_predicted_mean": float(ratio.mean()) if len(ratio) else float("nan"),
            "realized_to_predicted_median": float(ratio.median()) if len(ratio) else float("nan"),
            "realized_to_predicted_max": float(ratio.max()) if len(ratio) else float("nan"),
            "reps_over_planned_budget": int((realized > planned).sum()),
            "reps_over_planned_budget_share": float((realized > planned).mean()),
            "within_budget_by_predicted_share": float(g["within_budget"].mean()),
        })
    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(out.to_string(index=False))
    print(f"WROTE {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
