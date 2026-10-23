import sys
sys.path.insert(0, "src")
import numpy as np
import pandas as pd
from pathlib import Path

T = Path("outputs/tables")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)


def show(name, nrows=30):
    p = T / name
    if not p.exists():
        print(f"--- {name}: MISSING")
        return
    df = pd.read_csv(p)
    print(f"--- {name}  ({len(df)} rows)")
    print(df.head(nrows).to_string(index=False))
    print()


for n in (
    "r2_cate_comparison.csv",
    "r2_cate_repeats_summary.csv",
    "r2_cate_repeats_raw.csv",
    "r2_lambda_summary.csv",
    "r2_lambda_threshold.csv",
    "r2_lambda_anchor.csv",
    "r2_psm_balance.csv",
):
    show(n)
