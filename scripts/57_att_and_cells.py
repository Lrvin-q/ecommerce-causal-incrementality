"""把三处"可算但未算"的量算出来。

1. L3 核心格的解析 ATT：λ_T=0 时朴素差估的是 ATT 而不是 ATE，
   ATT = Σ e_i τ_i / Σ e_i（e 为真倾向，τ 为对 U 积分的逐用户效应）。
2. 确认核心格所用的估计量（从矩阵实现的 import 读出）。
3. 核对三个数值完全相同的 L1 格是否"机制未接线"（比对场景覆盖项）。
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.dgp.v3_engine import audit_conditional_truth, generate_v3_population  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402


def part1_att() -> None:
    protocol = load_v3_protocol()
    cfg = protocol.scenario("L3_fixed_lt000")
    n = 40000
    print(f"[1] L3 核心格 ATT（n={n}）…", flush=True)
    pop = generate_v3_population(cfg, 0, n)
    tr = audit_conditional_truth(pop, cfg)
    tau = tr["expected_net_profit_1"].to_numpy() - tr["expected_net_profit_0"].to_numpy()
    e = tr["true_propensity"].to_numpy()
    ate = float(tau.mean())
    att = float((e * tau).sum() / e.sum())
    print(f"    ATE（对 U 积分）= {ate:.4f}")
    print(f"    ATT（按真倾向加权）= {att:.4f}")
    print(f"    ATT − ATE = {att - ate:+.4f}")
    print(f"    矩阵估计（未调整均值差）= 1.6641，与 ATT 相差 {1.6641 - att:+.4f}")
    print(f"    e 的均值 {e.mean():.4f}、标准差 {e.std():.4f}")


def part2_estimator() -> None:
    print("\n[2] 核心格估计量")
    src = (ROOT / "src/causal_growth/evaluation/v3_g_matrix.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        if "itt_difference" in line and "import" in line:
            print(f"    {line.strip()}")
    hits = [l.strip() for l in src.splitlines() if "itt_difference_means(" in l or "itt_difference_proportions(" in l]
    for h in hits[:4]:
        print(f"    调用: {h[:100]}")


def part3_cells() -> None:
    print("\n[3] 三个数值完全相同的 L1 格")
    cfg = yaml.safe_load((ROOT / "configs/v3/scenarios.yaml").read_text(encoding="utf-8"))
    sc = {x["id"]: x for x in cfg["scenarios"]}
    base = sc["L1_main"].get("overrides", {})
    for cid in ("L1_cost_prediction_under", "L1_mar_double", "L1_misspec_omit_new_channel", "L1_signal_weak"):
        ov = sc[cid].get("overrides", {})
        diff = {k: v for k, v in ov.items() if base.get(k) != v}
        print(f"    {cid}: purpose={sc[cid].get('purpose','')[:40]}")
        for k, v in diff.items():
            print(f"        {k} = {json.dumps(v, ensure_ascii=False)}")


if __name__ == "__main__":
    part2_estimator()
    part3_cells()
    part1_att()
