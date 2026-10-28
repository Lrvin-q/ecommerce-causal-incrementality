"""Phase D 资源 pilot：实测单 rep 在三种粒度下的 CPU / 墙钟 / 峰值内存。

三种粒度（**只用于资源外推，不构成任何科学结果**）
------------------------------------------------
- ``G1 纯估计``：在已建好的观测表上拟合四个模型（常数 / T / S / CF）并算 ITT。
- ``G2 五表SQL+估计``：``G1`` 加上「生成 → 污染/清洗 → SQL → 观测表」的工程成本。
- ``G3 含CF完整流程``：``G2`` 加上测试集预测与贪心+局部改进的策略选择。

为什么这样切
------------
冻结矩阵给出的工作量是按"批"计数的（7300 学习批、12500 DGP 批、4000 AA …），
要把它们换算成 CPU 小时，必须知道**每一批里各阶段各花多少**。一次 rep 里把
流水线只跑一遍、各阶段分别计时，比跑三遍完整流程更省，也避免重复 I/O 污染测量。

纪律
----
- 不读真值、不写正式 ``data/v3`` 或 ``audit/v3``；产物只落 ``out/v3_phase_d``。
- 不改变任何冻结配置；模型超参显式取自 ``configs/v3/models.yaml``。
- 每次 rep 后立即删除流水线目录，避免把 pilot 变成隐藏的数据集。
- 失败必须记录并继续下一个 rep，不允许静默跳过。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\13_v3_pilot.py --reps 1 --n 200000
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import shutil
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from causal_growth.data.v3_pipeline import build_observed_pipeline
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.policy.selection import greedy_by_ratio, local_improvement
from causal_growth.rng import child_rng
from causal_growth.v3_config import load_v3_protocol

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "v3_phase_d"
STAGES = ("dgp", "pipeline", "features", "itt", "constant", "t_learner", "s_learner",
          "causal_forest", "predict", "policy")


# --------------------------------------------------------------------------- #
# 峰值内存（Windows：psapi!GetProcessMemoryInfo → PeakWorkingSetSize）
# --------------------------------------------------------------------------- #
class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_working_set_mb() -> float:
    """返回当前进程的峰值工作集（MB）。不可用时返回 nan。

    注意：``GetCurrentProcess`` 返回 64 位 HANDLE，ctypes 默认按 c_int 解释会把句柄
    截断，导致 ``GetProcessMemoryInfo`` 直接失败（表现为恒为 nan）。必须显式设置
    ``restype``/``argtypes``。
    """
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        handle = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return float("nan")
        return counters.PeakWorkingSetSize / (1024.0 * 1024.0)
    except Exception:  # noqa: BLE001 - 计量失败不应中断 pilot
        return float("nan")


class Timer:
    """同时记录墙钟与进程 CPU 时间。"""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, float]] = {}

    def stage(self, name: str):
        timer = self

        class _Ctx:
            def __enter__(self) -> None:
                self.wall0 = time.perf_counter()
                self.cpu0 = time.process_time()

            def __exit__(self, exc_type, exc, tb) -> bool:
                timer.rows[name] = {
                    "wall_s": time.perf_counter() - self.wall0,
                    "cpu_s": time.process_time() - self.cpu0,
                    "peak_mb": peak_working_set_mb(),
                    "failed": 0.0 if exc_type is None else 1.0,
                }
                return False

        return _Ctx()


# --------------------------------------------------------------------------- #
# 模型（超参取自冻结配置）
# --------------------------------------------------------------------------- #
def _lgbm_regressor(spec: dict[str, Any]):
    import lightgbm as lgb

    return lgb.LGBMRegressor(
        n_estimators=int(spec["n_estimators"]),
        learning_rate=float(spec["learning_rate"]),
        num_leaves=int(spec["num_leaves"]),
        min_child_samples=int(spec["min_child_samples"]),
        subsample=float(spec["subsample"]),
        colsample_bytree=float(spec["colsample_bytree"]),
        n_jobs=int(spec["n_jobs"]),
        verbose=-1,
    )


def _lgbm_classifier(spec: dict[str, Any]):
    import lightgbm as lgb

    return lgb.LGBMClassifier(
        n_estimators=int(spec["n_estimators"]),
        learning_rate=float(spec["learning_rate"]),
        num_leaves=int(spec["num_leaves"]),
        min_child_samples=int(spec["min_child_samples"]),
        subsample=float(spec["subsample"]),
        colsample_bytree=float(spec["colsample_bytree"]),
        n_jobs=int(spec["n_jobs"]),
        verbose=-1,
    )


def _causal_forest(spec: dict[str, Any], lgbm: dict[str, Any], *, random_state: int):
    from econml.dml import CausalForestDML

    return CausalForestDML(
        model_y=_lgbm_regressor(lgbm),
        model_t=_lgbm_classifier(lgbm),
        discrete_treatment=bool(spec["discrete_treatment"]),
        n_estimators=int(spec["n_estimators"]),
        min_samples_leaf=int(spec["min_samples_leaf"]),
        cv=int(spec["cv"]),
        n_jobs=int(spec["n_jobs"]),
        inference=bool(spec["inference"]),
        random_state=random_state,
    )


def _pilot_master_seed() -> int:
    business = yaml.safe_load((ROOT / "configs" / "v3" / "business.yaml").read_text(encoding="utf-8"))
    return int(business["project"]["master_seed"])


def _pilot_base_budget_per_user() -> float:
    policy = yaml.safe_load((ROOT / "configs" / "v3" / "policy.yaml").read_text(encoding="utf-8"))
    return float(policy["policy"]["budget"]["base_per_user_cny"])


# --------------------------------------------------------------------------- #
# 单 rep
# --------------------------------------------------------------------------- #
def run_rep(rep: int, n: int, scenario: str, models: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    cfg = load_v3_protocol().scenario(scenario)
    timer = Timer()
    row: dict[str, Any] = {"rep": rep, "n": n, "scenario": scenario}

    with timer.stage("dgp"):
        population = generate_v3_population(cfg, rep_id=rep, n=n)
        users, assignments, orders = population.observation_bundle()

    work = out_dir / "tmp" / f"rep_{rep}"
    shutil.rmtree(work, ignore_errors=True)
    work.parent.mkdir(parents=True, exist_ok=True)
    try:
        with timer.stage("pipeline"):
            result = build_observed_pipeline(
                users, assignments, orders, cfg,
                directory=work, run_id=f"pilot:{scenario}:{rep}", rep_id=rep,
                stream_prefix=population.metadata["stream_prefix"],
                persist_database=False, retention_scope="engineering_full",
            )
        obs = result.dataset.observations
        prep = result.preprocessor
        if prep is None:
            raise RuntimeError("pipeline 未产出 FrozenPreprocessor，无法继续")

        train = obs[obs["split"] == "train"]
        test = obs[obs["split"] == "test"]
        if len(train) == 0 or len(test) == 0:
            raise RuntimeError(f"拆分异常：train={len(train)} test={len(test)}")

        with timer.stage("features"):
            x_train = prep.transform(train).matrix
            x_test = prep.transform(test).matrix
            y_train = train["net_profit"].to_numpy(dtype=float)
            t_train = train["treatment"].to_numpy(dtype=int)

        with timer.stage("itt"):
            y1 = y_train[t_train == 1]
            y0 = y_train[t_train == 0]
            itt = float(y1.mean() - y0.mean())

        with timer.stage("constant"):
            tau_constant = np.full(len(x_test), itt, dtype=float)

        lgbm = models["lightgbm"]
        with timer.stage("t_learner"):
            m1 = _lgbm_regressor(lgbm).fit(x_train[t_train == 1], y_train[t_train == 1])
            m0 = _lgbm_regressor(lgbm).fit(x_train[t_train == 0], y_train[t_train == 0])
            tau_t = m1.predict(x_test) - m0.predict(x_test)

        with timer.stage("s_learner"):
            xs = np.column_stack([x_train, t_train])
            m_s = _lgbm_regressor(lgbm).fit(xs, y_train)
            tau_s = (m_s.predict(np.column_stack([x_test, np.ones(len(x_test))]))
                     - m_s.predict(np.column_stack([x_test, np.zeros(len(x_test))])))

        with timer.stage("causal_forest"):
            cf_state = int(child_rng(_pilot_master_seed(), "v3.pilot.causal_forest", rep)
                           .integers(0, np.iinfo(np.int32).max))
            cf = _causal_forest(models["causal_forest"], lgbm, random_state=cf_state)
            cf.fit(y_train, t_train, X=x_train)
            tau_cf = cf.effect(x_test)

        with timer.stage("predict"):
            # 触发一次完整预测路径的拷贝，模拟下游要保存名单的量级
            tau_stack = np.vstack([tau_constant, tau_t, tau_s, tau_cf])
            _ = float(np.nanmean(tau_stack))

        business = yaml.safe_load((ROOT / "configs" / "v3" / "business.yaml").read_text(encoding="utf-8"))
        face = float(business["business"]["coupon_reference_face"])
        redemption = float(business["business"]["redemption_rate"])
        budget = _pilot_base_budget_per_user() * len(x_test) * face * redemption  # 计时用占位预算，不构成结果
        cost = np.full(len(x_test), max(face * redemption, 1e-9), dtype=float)
        with timer.stage("policy"):
            pick = greedy_by_ratio(tau_cf, cost, budget)
            improved = local_improvement(tau_cf, cost, budget, pick.policy)

        row.update({
            "train_rows": int(len(train)), "test_rows": int(len(test)),
            "features": int(x_train.shape[1]),
            "itt": itt,
            "n_selected": int(improved.policy.sum()),
            "budget_cny": budget,
        })
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for stage, payload in timer.rows.items():
        row[f"{stage}_wall_s"] = payload["wall_s"]
        row[f"{stage}_cpu_s"] = payload["cpu_s"]
        row[f"{stage}_peak_mb"] = payload["peak_mb"]
        if payload["failed"]:
            row.setdefault("failed_stage", stage)

    row["G1_estimation_s"] = sum(timer.rows.get(s, {}).get("cpu_s", 0.0)
                                 for s in ("features", "itt", "constant", "t_learner",
                                           "s_learner", "causal_forest", "predict"))
    row["G2_tables_sql_estimation_s"] = row["G1_estimation_s"] + timer.rows.get("pipeline", {}).get("cpu_s", 0.0)
    row["G3_full_with_cf_s"] = row["G2_tables_sql_estimation_s"] + timer.rows.get("policy", {}).get("cpu_s", 0.0)
    row["G1_plus_dgp_s"] = row["G1_estimation_s"] + timer.rows.get("dgp", {}).get("cpu_s", 0.0)
    row["G3_plus_dgp_s"] = row["G3_full_with_cf_s"] + timer.rows.get("dgp", {}).get("cpu_s", 0.0)
    row["peak_mb"] = max((timer.rows.get(s, {}).get("peak_mb", float("nan")) for s in STAGES),
                         default=float("nan"))
    return row


def _safe_mean(values: list[float]) -> float:
    """全 NaN 时返回 nan 而不告警。"""
    array = np.asarray(values, dtype=float)
    finite = array[~np.isnan(array)]
    return float(finite.mean()) if finite.size else float("nan")


def _safe_nanmax(values: list[float]) -> float:
    """全 NaN 时返回 nan 而不告警。"""
    array = np.asarray(values, dtype=float)
    finite = array[~np.isnan(array)]
    return float(finite.max()) if finite.size else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase D 资源 pilot（只产 out/ 证据）")
    parser.add_argument("--scenario", default="L1_main")
    parser.add_argument("--n", type=int, default=200_000)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--start-rep", type=int, default=0)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    models = yaml.safe_load((ROOT / "configs" / "v3" / "models.yaml").read_text(encoding="utf-8"))["models"]
    csv_path = OUT / f"pilot_raw_{args.scenario}_n{args.n}.csv"

    rows: list[dict[str, Any]] = []
    for rep in range(args.start_rep, args.start_rep + args.reps):
        print(f"[pilot] rep={rep} n={args.n} scenario={args.scenario}", flush=True)
        t0 = time.perf_counter()
        try:
            row = run_rep(rep, args.n, args.scenario, models, OUT)
        except Exception as exc:  # noqa: BLE001 - 失败要记录并继续
            row = {"rep": rep, "n": args.n, "scenario": args.scenario,
                   "error": f"{type(exc).__name__}: {exc}"}
            print(f"  FAILED: {row['error']}", flush=True)
        row["elapsed_wall_s"] = time.perf_counter() - t0
        rows.append(row)
        print("  " + "  ".join(f"{k}={v:.1f}s" for k, v in row.items()
                               if k.endswith("_cpu_s") and isinstance(v, (int, float))), flush=True)
        print(f"  peak={row.get('peak_mb', float('nan')):.0f}MB", flush=True)

        # 增量落盘，避免中断丢结果
        frame = pd.DataFrame(rows)
        frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    summary = {
        "scenario": args.scenario, "n": args.n, "reps": len(rows),
        "csv": csv_path.relative_to(ROOT).as_posix(),
        "failed": sum(1 for r in rows if "error" in r),
        "mean_G1_estimation_s": _safe_mean([r.get("G1_estimation_s", np.nan) for r in rows]),
        "mean_G2_tables_sql_estimation_s": _safe_mean([r.get("G2_tables_sql_estimation_s", np.nan) for r in rows]),
        "mean_G3_full_with_cf_s": _safe_mean([r.get("G3_full_with_cf_s", np.nan) for r in rows]),
        "mean_G1_plus_dgp_s": _safe_mean([r.get("G1_plus_dgp_s", np.nan) for r in rows]),
        "mean_G3_plus_dgp_s": _safe_mean([r.get("G3_plus_dgp_s", np.nan) for r in rows]),
        "mean_dgp_s": _safe_mean([r.get("dgp_cpu_s", np.nan) for r in rows]),
        "mean_pipeline_s": _safe_mean([r.get("pipeline_cpu_s", np.nan) for r in rows]),
        "mean_cf_s": _safe_mean([r.get("causal_forest_cpu_s", np.nan) for r in rows]),
        "mean_wall_s": _safe_mean([r.get("elapsed_wall_s", np.nan) for r in rows]),
        "max_peak_mb": _safe_nanmax([r.get("peak_mb", np.nan) for r in rows]),
    }
    (OUT / f"pilot_summary_{args.scenario}_n{args.n}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
