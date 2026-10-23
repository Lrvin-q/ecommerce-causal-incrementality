import sys
sys.path.insert(0, "src")
import numpy as np
import pandas as pd
from pathlib import Path

T = Path("outputs/tables")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", lambda v: f"{v:,.6f}")


def show(name, cols=None, nrows=20):
    p = T / name
    if not p.exists():
        print(f"--- {name}: MISSING")
        return
    df = pd.read_csv(p)
    if cols:
        df = df[[c for c in cols if c in df.columns]]
    print(f"--- {name}  ({len(df)} rows)")
    print(df.head(nrows).to_string(index=False))
    print()


show("r1_sample_size.csv")
show("r1_itt.csv")
show("r1_auxiliary.csv")
show("r1_guardrail.csv")
show("r1_guardrail_power.csv")
show("r1_guardrail_sensitivity.csv")
show("r1_srm.csv")
show("r1_multiplicity.csv")
show("r1_repeats_summary.csv")
show("r1_profit_crosscheck.csv")
show("r1_aa_summary.csv")
show("r1_quality_clean.csv")
show("r1_sql_qc_treatment_share.csv")
show("r1_sql_qc_refund_retention.csv")
