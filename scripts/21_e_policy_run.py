"""E 阶段策略编排：9 个候选策略 × 8 个预算点（薄入口）。

网格逻辑在 :mod:`causal_growth.policy.v3_policy_grid`，本脚本只负责
读入契约 CSV / 生成合成链路数据、落盘并打印摘要。

输入契约（CSV，``utf-8-sig``，列名固定）
----------------------------------------
``user_id, is_new, cart_value, purchase_propensity, predicted_profit,
tau_hat, cost_hat, tau_true, cost_true``

- **选人只用** ``tau_hat`` / ``cost_hat`` / ``purchase_propensity`` / ``predicted_profit``；
- **评估只用** ``tau_true`` / ``cost_true``；
- 预算合规同时报两件事：按 ``cost_hat`` 是否超预算、按 ``cost_true`` 实际支出了多少。

``--synthetic`` 时按已知 DGP 生成，用于在没有 D 阶段导出表时验证编排链路。
生成的数据**不能**用来下策略结论——它只证明代码能跑通。

用法
----
    $env:PYTHONUTF8='1'
    .\\venv\\Scripts\\python.exe scripts\\21_e_policy_run.py --synthetic --synthetic-n 50000 --out out/e_smoke
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.config import Config  # noqa: E402
from causal_growth.policy.v3_policy_grid import (  # noqa: E402
    evaluate_policy_grid,
    require_grid_frame,
)
from causal_growth.rng import child_rng  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402


def _synthetic(n: int, cfg: Config) -> pd.DataFrame:
    """已知 DGP 的合成表；只用于打通链路，不用于结论。"""
    rng = child_rng(int(cfg.require("project.master_seed")), "e.synthetic", 0)
    propensity = rng.beta(2.0, 5.0, size=n)
    is_new = (rng.random(n) < 0.35).astype(np.int64)
    cart_value = np.round(rng.lognormal(3.8, 0.7, size=n), 2)
    # 真值增量：新客与高意向更敏感，加上异质项
    tau_true = 0.35 * is_new + 0.9 * propensity + 0.02 * np.log1p(cart_value) + rng.normal(0, 0.15, n)
    face = float(cfg.require("policy.face_value_cny"))
    p_redeem = np.clip(0.25 + 0.55 * propensity, 0.02, 0.95)
    cost_true = face * (rng.random(n) < p_redeem)
    # 预测：τ̂ 带噪声；ĉ 是期望核销成本（不是面额）
    tau_hat = tau_true + rng.normal(0, 0.35, n)
    cost_hat = np.maximum(face * propensity ** 0.5 * 0.8, float(cfg.require("policy.cost_model.cost_floor_cny")))
    return pd.DataFrame({
        "user_id": np.arange(n, dtype=np.int64),
        "is_new": is_new,
        "cart_value": cart_value,
        "purchase_propensity": propensity,
        "predicted_profit": propensity * np.maximum(cart_value * 0.08, 0.0),
        "tau_hat": tau_hat,
        "cost_hat": cost_hat,
        "tau_true": tau_true,
        "cost_true": cost_true,
    })


def _load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    require_grid_frame(frame)
    return frame


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E 阶段：9 策略 × 8 预算点的编排与评估")
    parser.add_argument("--input", type=Path, default=None, help="输入 CSV；不给则用 --synthetic")
    parser.add_argument("--synthetic", action="store_true", help="用已知 DGP 生成（仅打通链路）")
    parser.add_argument("--synthetic-n", type=int, default=50_000)
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "e_policy")
    args = parser.parse_args(argv)

    cfg = load_v3_protocol().config
    if args.input is not None:
        frame = _load(args.input)
        source = f"csv:{args.input}"
    else:
        if not args.synthetic:
            parser.error("必须给 --input 或 --synthetic")
        frame = _synthetic(args.synthetic_n, cfg)
        source = f"synthetic:{args.synthetic_n}"
    print(f"[数据] {source}  n={len(frame)}")

    summary = evaluate_policy_grid(frame, cfg)
    grid = [float(value) for value in cfg.require("policy.budget.per_user_grid_cny")]

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "e_policy_grid.csv"
    summary.to_csv(target, index=False, encoding="utf-8-sig")

    print(f"\n[完成] {len(summary)} 行 = {len(grid)} 预算 × {summary['policy'].nunique()} 策略 → {target}")
    pivot = summary.pivot(index="policy", columns="per_user_budget_cny", values="true_value_per_user")
    print("\n真实人均增量价值（元/人）：")
    print(pivot.round(4).to_string())
    violations = summary[~summary["within_budget_by_hat"] & (summary["policy"] != "all_coupon_unconstrained_reference")]
    if not violations.empty:
        print(f"\n[警告] 按预测成本超预算的组合：{len(violations)} 个")
        print(violations[["per_user_budget_cny", "policy"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
