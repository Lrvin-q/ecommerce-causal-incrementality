"""E 层预算口径扫描的对齐表：8 个预算档 × 3 口径 × 2 个帧向量。

回答的问题：保守口径的代价随预算档如何变化；以及把帧价值向量从常数换成
因果森林，同一份名单、同一套策略规则能多拿回多少价值。论文 3.5 两张表的
唯一数据来源。两个源表共用同一批用户，随机臂在两表里应逐位相同（断言检查），
因此贪心与随机、常数帧与因果森林帧的比较都是同名单配对。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "constant": ROOT / "outputs/tables/v3_phase_E_conservative.csv",
    "causal_forest": ROOT / "outputs/tables/v3_phase_E_conservative_cf.csv",
}
OUT = ROOT / "outputs/tables/v3_phase_E_budget_sweep.csv"
POLICIES = ("greedy_incremental_profit_per_cost", "random_same_budget")


def main() -> int:
    frames = []
    for name, path in SOURCES.items():
        d = pd.read_csv(path, encoding="utf-8-sig")
        d = d[d.policy.isin(POLICIES)].copy()
        d["frame_model"] = name
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["budget"] = df.per_user_budget_cny.round(2)

    rnd = df[df.policy == "random_same_budget"].pivot_table(
        index=["mode", "budget"], columns="frame_model", values="true_value_per_user_mean"
    )
    assert np.allclose(rnd["constant"], rnd["causal_forest"], rtol=0.0, atol=1e-12), (
        "随机臂不读帧向量，两个帧下的取值应逐位相同"
    )
    assert (df[df.policy == POLICIES[0]].groupby("frame_model").size() == 24).all()

    const = df[df.frame_model == "constant"][
        ["mode", "budget", "policy", "true_value_per_user_mean"]
    ].rename(columns={"true_value_per_user_mean": "constant_value"})
    df = df.merge(const, on=["mode", "budget", "policy"], how="left")
    rnd_val = df[df.policy == "random_same_budget"][
        ["frame_model", "mode", "budget", "true_value_per_user_mean"]
    ].rename(columns={"true_value_per_user_mean": "random_value"})
    df = df.merge(rnd_val, on=["frame_model", "mode", "budget"], how="left")

    df["value_ratio_vs_constant"] = df.true_value_per_user_mean / df.constant_value
    df["value_ratio_vs_random"] = df.true_value_per_user_mean / df.random_value

    out = df[[
        "frame_model", "mode", "policy", "per_user_budget_cny", "budget_cny", "seeds",
        "selected_count_mean", "actual_spend_mean", "true_value_per_user_mean",
        "true_value_per_actual_spend_mean", "overrun_probability",
        "value_ratio_vs_constant", "value_ratio_vs_random",
    ]].rename(columns={
        "per_user_budget_cny": "per_user_budget_cny",
        "selected_count_mean": "selected_count",
        "actual_spend_mean": "actual_spend_cny",
        "true_value_per_user_mean": "true_value_per_user",
        "true_value_per_actual_spend_mean": "true_value_per_cny_spend",
    }).sort_values(["frame_model", "mode", "policy", "per_user_budget_cny"])
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"rows {len(out)} -> {OUT.relative_to(ROOT)}")

    g = out[out.policy == POLICIES[0]]
    for frame in SOURCES:
        for mode in ("expected", "buffered_expected", "worst_case_face"):
            s = g[(g.frame_model == frame) & (g["mode"] == mode)].sort_values("per_user_budget_cny")
            print(frame, mode)
            print("  budget ", [round(v, 2) for v in s.per_user_budget_cny])
            print("  value  ", [f"{v:.4f}" for v in s.true_value_per_user])
            print("  per_cny", [f"{v:.4f}" for v in s.true_value_per_cny_spend])
            print("  sel    ", [int(v) for v in s.selected_count])
    return 0


if __name__ == "__main__":
    sys.exit(main())
