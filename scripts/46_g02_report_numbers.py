"""G02 报告取数：只读 outputs/tables 与 outputs/evidence，不写证据区。

回答方案里的问题：4 格 × 50 b 的再训练 bootstrap 结果能否被报告逐字复算。
用法：.venv/Scripts/python.exe scripts/46_g02_report_numbers.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MERGED = ROOT / "outputs/tables/v3_phase_G02_retrain_bootstrap.csv"
PER_CELL = ROOT / "outputs/evidence/g02_formal/per_cell"


def main() -> int:
    merged = pd.read_csv(MERGED, encoding="utf-8-sig")
    rows = []
    for _, r in merged.iterrows():
        cell = str(r["cell_id"])
        d = pd.read_csv(PER_CELL / f"{cell}__repetitions.csv", encoding="utf-8-sig")
        n = len(d)
        rows.append({
            "cell": cell,
            "b": n,
            "mean": float(r["policy_value_mean"]),
            "sd": float(r["policy_value_sd"]),
            "mc_se": float(d["policy_value"].std(ddof=1) / np.sqrt(n)),
            "ci95": [float(r["ci95_low"]), float(r["ci95_high"])],
            "decision_pass": int(d["decision_all_pass"].sum()),
            "decision_rate": float(r["decision_pass_rate"]),
            "guardrail_pass": int(d["guardrail_pass"].sum()),
            "guardrail_rate": float(r["guardrail_pass_rate"]),
            "decision_lower_min": float(r["decision_lower_min_min"]),
            "guardrail_upper_max": float(r["guardrail_upper_max"]),
            "cpu_hours": float(r["total_cpu_seconds"]) / 3600.0,
            "chosen_models": {str(k): int(v) for k, v in
                              d["chosen_model"].value_counts().items()},
        })
    payload = {"rows": rows,
               "total_cpu_hours": sum(x["cpu_hours"] for x in rows),
               "total_b": sum(x["b"] for x in rows)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
