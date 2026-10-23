import sys
sys.path.insert(0, "src")
import numpy as np
import pandas as pd
from pathlib import Path

T = Path("outputs/tables")
pd.set_option("display.width", 260)
pd.set_option("display.max_columns", 80)


def show(name, nrows=40):
    p = T / name
    if not p.exists():
        print(f"--- {name}: MISSING")
        return
    df = pd.read_csv(p)
    print(f"--- {name}  ({len(df)} rows)")
    print(df.head(nrows).to_string(index=False))
    print()


for n in (
    "r3_six_strategies.csv",
    "r3_six_strategies_ci.csv",
    "r3_random_seeds.csv",
    "r3_oracle_bound.csv",
    "r3_greedy_gap.csv",
    "r3_budget_scan.csv",
    "r3_robustness.csv",
    "r1_data_dictionary.csv",
):
    show(n)

# 频数：多单用户 / 券核销
orders = pd.read_csv("data/orders.csv")
users = orders.groupby("user_id").size()
print("orders rows", len(orders), "users with orders", users.size, "multi-order users", int((users > 1).sum()))
print("repeat pay total", float(orders.loc[orders["order_id"].astype(str).str.endswith("-2"), "pay_amount"].sum()))
print("refund orders", int(orders["refunded"].sum()))
print("orders per multi:", float(users[users > 1].mean()))
