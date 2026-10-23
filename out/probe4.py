import sys
sys.path.insert(0, "src")
import numpy as np
import pandas as pd
from pathlib import Path

T = Path("outputs/tables")

# ① 新老客分组的处理−对照差（报告 §3 的"设计意图"数字）
df = pd.read_csv(T / "r1_analysis_frame_clean.csv", usecols=["is_new", "treatment", "converted", "net_profit", "n_orders"])
for name, sub in (("新客", df[df.is_new == 1]), ("老客", df[df.is_new == 0])):
    t1 = sub[sub.treatment == 1]
    t0 = sub[sub.treatment == 0]
    print(
        f"{name}: n={len(sub):,} 利润差 {t1.net_profit.mean() - t0.net_profit.mean():+.4f} 元  "
        f"转化差 {(t1.converted.mean() - t0.converted.mean()) * 100:+.3f} pp"
    )

# ② 重复上报行数
dirty = pd.read_csv(T / "r1_quality_dirty.csv")
row = dirty[dirty["检查项"].astype(str).str.contains("重复上报", na=False)]
print("\n重复上报行：", row["详情"].iloc[0][:160])

# ③ 第二单利润规模
orders = pd.read_csv("data/orders.csv")
second = orders[orders["order_id"].astype(str).str.endswith("-2")]
sys.path.insert(0, "src")
from causal_growth.config import load_config
from causal_growth.data.profit import compute_order_components

cfg = load_config()
net = compute_order_components(second, cfg)["net_profit"]
allnet = compute_order_components(orders, cfg)["net_profit"]
print(f"\n第二单 {len(second):,} 笔：单均净贡献 {net.mean():.3f} 元，合计 {net.sum():,.1f} 元")
print(f"折算全体用户 {net.sum()/200000:.4f} 元/人 = ITT(0.6676) 的 {net.sum()/200000/0.667577*100:.1f}%")
print(f"订单总行数 {len(orders):,}，订单净贡献合计 {allnet.sum():,.1f} 元")
print("is_new 用户数", int((df.is_new == 1).sum()))
print("每100人 多转化增益", (0.151042-0.100943)*24.688*100)
print("全部策略占真值比", 0.610755/0.40498*100)
print("绝对口径常数 E[Pi0] =", pd.read_csv(T / "r2_cate_comparison.csv")["策略价值_绝对口径"].iloc[0] - pd.read_csv(T / "r2_cate_comparison.csv")["策略价值_元每人"].iloc[0])
