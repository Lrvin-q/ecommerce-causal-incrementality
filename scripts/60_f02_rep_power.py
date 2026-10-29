"""F02 逐重复的检验特征：SE 的离散度、80% 功效 MDE、差超过 MDE 的占比与中位 t。

回答的问题：200 个重复里少数失败，是"这次精度差"还是"这次效应小"。
只做逐 rep 表的聚合，不重算 p 值、不改判定口径。
输出 outputs/tables/v3_phase_F02_rep_power.csv。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_claims.csv"
OUT = ROOT / "outputs/tables/v3_phase_F02_rep_power.csv"
ALPHA = 0.05
POWER = 0.80


def main() -> int:
    frame = pd.read_csv(SRC, encoding="utf-8-sig")
    z = float(norm.ppf(1 - ALPHA / 2) + norm.ppf(POWER))
    rows = []
    for claim, group in frame.groupby("claim", sort=False):
        se = group.se.astype(float)
        mde = z * se
        diff = group.diff_cny_per_user.astype(float)
        failed = ~group.passes_adjusted_test.astype(bool)
        rows.append({
            "claim": claim,
            "n_reps": int(len(group)),
            "se_median": float(se.median()),
            "se_q25": float(se.quantile(0.25)),
            "se_q75": float(se.quantile(0.75)),
            "se_range": float(se.max() - se.min()),
            "mde80_median": float(mde.median()),
            "share_diff_above_mde": float((diff > mde).mean()),
            "t_median": float((diff / se).median()),
            "diff_mean": float(diff.mean()),
            "diff_mean_over_mde": float(diff.mean() / mde.median()),
            "n_fail": int(failed.sum()),
            "fail_diff_min": float(diff[failed].min()) if failed.any() else float("nan"),
            "fail_diff_max": float(diff[failed].max()) if failed.any() else float("nan"),
            "fail_se_median": float(se[failed].median()) if failed.any() else float("nan"),
        })
    out = pd.DataFrame(rows)
    print(out.round(4).T.to_string())
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print("WROTE", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
