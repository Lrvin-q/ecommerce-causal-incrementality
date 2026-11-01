"""合并 D03 正式 R 的四个分片，并做完整性/一致性校验后落 `outputs/tables/`。

为什么必须单独合并
------------------
正式 R 按 `--rep-start/--rep-stop` 切成 4 个独立进程，每个分片各自写一张逐 rep 表、
一张策略网格和一份 summary。GOAL 的正式口径是**合计 200 rep**；分片 summary 的
`n_reps=50` 只能描述分片，不能拿来判定。合并时必须回答三个问题：

1. 200 个 rep 是否恰好各出现一次（缺 rep、重 rep 都要报错）；
2. 每个 rep 是否 5 个模型 × 8 预算 × 9 策略齐全，且 `chosen` 恰好覆盖一个模型的整张网格；
3. 四个分片是否跑的是同一份协议（config_hash / selection_rule / 快照哈希一致）。

纪律
----
- 只读分片 CSV 与 summary，不重跑模型、不读逐用户表。
- 合并结果只写 `outputs/tables/`（聚合表，可入库）；逐用户帧仍留在 `out/`，不入库。
- 任一校验失败即抛异常，不写任何合并产物。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from causal_growth.estimate.v3_models import (
    _aggregate_metrics,
    _aggregate_policy_grid,
)
from causal_growth.policy.v3_policy_grid import POLICIES as E_POLICIES

ROOT = Path(__file__).resolve().parents[1]
BEIJING = timezone(timedelta(hours=8))
BUDGET_TOLERANCE = 1e-9

PER_REP_FILE = "v3_phase_D03_diagnostic_per_rep.csv"
GRID_FILE = "v3_phase_D03_diagnostic_policy_grid.csv"
SUMMARY_FILE = "v3_phase_D03_diagnostic_summary.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _beijing_now() -> str:
    return datetime.now(BEIJING).isoformat(timespec="minutes")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_shard(shard_dir: Path, n_per_rep: int) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """读一个分片的三份产物，并做分片内校验。"""
    for name in (PER_REP_FILE, GRID_FILE, SUMMARY_FILE):
        _require((shard_dir / name).is_file(), f"{shard_dir} 缺 {name}")
    per_rep = pd.read_csv(shard_dir / PER_REP_FILE, encoding="utf-8-sig")
    grid = pd.read_csv(shard_dir / GRID_FILE, encoding="utf-8-sig")
    summary = json.loads((shard_dir / SUMMARY_FILE).read_text(encoding="utf-8"))

    _require(bool(summary.get("formal_r")), f"{shard_dir} 不是正式 R 产物")
    _require(summary.get("status") == "formal_r", f"{shard_dir} status 不是 formal_r")
    _require(int(summary["n_per_rep"]) == n_per_rep,
             f"{shard_dir} n_per_rep={summary['n_per_rep']} 与期望 {n_per_rep} 不符")

    rep_ids = sorted(int(value) for value in per_rep["rep_id"].unique())
    _require(rep_ids == sorted(int(value) for value in summary["rep_ids"]),
             f"{shard_dir} summary.rep_ids 与逐 rep 表不一致")
    _require(len(per_rep) == len(rep_ids) * 5,
             f"{shard_dir} 逐 rep 行数 {len(per_rep)} != reps×5")
    _require(len(grid) == len(rep_ids) * 5 * 8 * len(E_POLICIES),
             f"{shard_dir} 网格行数 {len(grid)} != reps×5×8×9")

    for rep_id, block in per_rep.groupby("rep_id"):
        _require(sorted(block["model"].astype(str)) == sorted(["constant", "t_learner",
                 "s_learner", "causal_forest", "dr_learner"]),
                 f"rep {rep_id} 模型不齐")
        _require(int(block["chosen"].sum()) == 1, f"rep {rep_id} chosen 模型数 != 1")
        _require(block["tau_true_mean"].nunique(dropna=False) == 1,
                 f"rep {rep_id} 各模型 tau_true_mean 不一致（应同测试集）")
        _require(block["n_test"].nunique(dropna=False) == 1,
                 f"rep {rep_id} 各模型 n_test 不一致")

    for rep_id, block in grid.groupby("rep_id"):
        _require(len(block) == 5 * 8 * len(E_POLICIES), f"rep {rep_id} 网格不齐")
        _require(block.groupby("model").size().eq(8 * len(E_POLICIES)).all(),
                 f"rep {rep_id} 每模型网格数不对")
        chosen_models = block.loc[block["chosen"].astype(bool), "model"].unique()
        _require(len(chosen_models) == 1, f"rep {rep_id} chosen 模型数 != 1")
        chosen_block = block.loc[block["model"] == chosen_models[0]]
        _require(len(chosen_block) == 8 * len(E_POLICIES)
                 and bool(chosen_block["chosen"].all()),
                 f"rep {rep_id} chosen 未覆盖该模型整张网格")
        # 合规标记必须与数值一致，防止表格被手工改坏
        by_hat = block["predicted_cost"] <= block["budget_cny"] + BUDGET_TOLERANCE
        by_true = block["actual_spend_cny"] <= block["budget_cny"] + BUDGET_TOLERANCE
        _require((by_hat.to_numpy() == block["within_budget_by_hat"].astype(bool).to_numpy()).all(),
                 f"rep {rep_id} within_budget_by_hat 与数值不符")
        _require((by_true.to_numpy() == block["within_budget_by_true"].astype(bool).to_numpy()).all(),
                 f"rep {rep_id} within_budget_by_true 与数值不符")

    finite_columns = ("predicted_value", "predicted_cost", "true_value_per_user",
                      "true_total_value", "actual_spend_cny")
    _require(np.isfinite(grid.loc[:, finite_columns].to_numpy(dtype=float)).all(),
             f"{shard_dir} 网格含非有限值")
    return per_rep, grid, summary


def merge(shards: list[Path], expected_reps: int, n_per_rep: int,
          allow_partial: bool) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """合并分片并在**写盘前**完成全部校验。"""
    per_reps: list[pd.DataFrame] = []
    grids: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for shard_dir in shards:
        per_rep, grid, summary = load_shard(shard_dir, n_per_rep)
        per_reps.append(per_rep)
        grids.append(grid)
        summaries.append(summary)
        provenance.append({
            "shard": str(shard_dir),
            "per_rep_sha256": _sha256(shard_dir / PER_REP_FILE),
            "policy_grid_sha256": _sha256(shard_dir / GRID_FILE),
            "summary_sha256": _sha256(shard_dir / SUMMARY_FILE),
            "reps": int(summary["reps"]),
            "written_at_beijing": summary.get("written_at_beijing"),
        })

    merged_per_rep = pd.concat(per_reps, ignore_index=True).sort_values(
        ["rep_id", "model"], kind="stable").reset_index(drop=True)
    merged_grid = pd.concat(grids, ignore_index=True).sort_values(
        ["rep_id", "model", "per_user_budget_cny", "policy"], kind="stable").reset_index(drop=True)

    rep_ids = sorted(int(value) for value in merged_per_rep["rep_id"].unique())
    counts = merged_per_rep.groupby("rep_id").size()
    _require(bool((counts == 5).all()), f"rep 行数异常（重复 rep？）：{counts[counts != 5].to_dict()}")
    expected_ids = list(range(expected_reps))
    if allow_partial:
        _require(set(rep_ids) <= set(expected_ids), "rep_id 超出 0..expected-1")
    else:
        missing = sorted(set(expected_ids) - set(rep_ids))
        extra = sorted(set(rep_ids) - set(expected_ids))
        _require(not missing, f"缺少 rep: {missing[:10]}（共 {len(missing)} 个）")
        _require(not extra, f"多出 rep: {extra[:10]}")
        _require(len(rep_ids) == expected_reps, "rep 数不等于注册值")

    for column in ("config_hash", "selection_rule"):
        values = {summary.get(column) for summary in summaries}
        _require(len(values) == 1, f"各分片 {column} 不一致：{values}")
    truth = [json.dumps(summary.get("truth_isolation"), sort_keys=True) for summary in summaries]
    _require(len(set(truth)) == 1, "各分片 truth_isolation 不一致")

    reps_meta = [row for summary in summaries for row in summary.get("reps_meta", [])]
    _require(len(reps_meta) == len(rep_ids), "reps_meta 条数与 rep 数不一致")
    _require({int(row["rep_id"]) for row in reps_meta} == set(rep_ids), "reps_meta 的 rep 覆盖不全")
    for row in reps_meta:
        _require(int(row["n_total"]) == n_per_rep,
                 f"rep {row['rep_id']} n_total={row['n_total']} != {n_per_rep}")
        _require(bool(row["observed_hash"]) and bool(row["split_fingerprint"]),
                 f"rep {row['rep_id']} 缺观测/拆分指纹")
    _require(len({row["observed_hash"] for row in reps_meta}) == len(reps_meta),
             "观测表哈希在 rep 间重复（rep 可能被复制）")

    chosen_counts = {str(key): int(value) for key, value in
                     summaries[0].get("chosen_model_counts", {}).items()}
    for summary in summaries[1:]:
        for key, value in summary.get("chosen_model_counts", {}).items():
            chosen_counts[str(key)] = chosen_counts.get(str(key), 0) + int(value)
    _require(sum(chosen_counts.values()) == len(rep_ids), "chosen 计数之和 != rep 数")

    merged_summary: dict[str, Any] = {
        "status": "formal_r",
        "formal_r": True,
        "purpose": "D03 正式 R：200 rep × 5 模型 × 9 策略 × 8 预算；真值仅用于评估",
        "source_label": summaries[0].get("source_label"),
        "scenario": summaries[0].get("scenario"),
        "level": summaries[0].get("level"),
        "identification_mode": summaries[0].get("identification_mode"),
        "time_mode": summaries[0].get("time_mode"),
        "n_per_rep": n_per_rep,
        "reps": len(rep_ids),
        "expected_reps": expected_reps,
        "rep_ids": rep_ids,
        "selection_rule": summaries[0].get("selection_rule"),
        "truth_isolation": summaries[0].get("truth_isolation"),
        "chosen_model_counts": chosen_counts,
        "models": _aggregate_metrics(merged_per_rep),
        "chosen_model_rows": _aggregate_metrics(
            merged_per_rep.loc[merged_per_rep["chosen"].astype(bool)]
        ),
        "policy_grid": _aggregate_policy_grid(
            merged_grid.loc[merged_grid["chosen"].astype(bool)], E_POLICIES
        ),
        "policy_grid_by_model": {
            str(model): _aggregate_policy_grid(block, E_POLICIES)
            for model, block in merged_grid.groupby("model", sort=False)
        },
        "reps_meta": sorted(reps_meta, key=lambda row: int(row["rep_id"])),
        "config_hash": summaries[0].get("config_hash"),
        "merge_provenance": {
            "shards": provenance,
            "merged_at_beijing": _beijing_now(),
            "expected_per_rep_rows": expected_reps * 5,
            "expected_policy_grid_rows": expected_reps * 5 * 8 * len(E_POLICIES),
            "per_rep_rows": int(len(merged_per_rep)),
            "policy_grid_rows": int(len(merged_grid)),
            "policy_order": list(E_POLICIES),
        },
    }
    return merged_per_rep, merged_grid, merged_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", nargs="+", default=[str(ROOT / "out" / "d03_formal" / f"shard{i}")
                                                       for i in range(4)])
    parser.add_argument("--out-dir", default=str(ROOT / "outputs" / "tables"))
    parser.add_argument("--expected-reps", type=int, default=200)
    parser.add_argument("--n-per-rep", type=int, default=200_000)
    parser.add_argument("--allow-partial", action="store_true",
                        help="只用于演练：允许 rep 不齐，但仍做全部一致性校验")
    args = parser.parse_args()

    shards = [Path(value).resolve() for value in args.shard]
    merged_per_rep, merged_grid, merged_summary = merge(
        shards, args.expected_reps, args.n_per_rep, args.allow_partial
    )

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    per_rep_path = out_dir / "v3_phase_D03_formal_per_rep.csv"
    grid_path = out_dir / "v3_phase_D03_formal_policy_grid.csv"
    summary_path = out_dir / "v3_phase_D03_formal_summary.json"
    merged_per_rep.to_csv(per_rep_path, index=False, encoding="utf-8-sig")
    merged_grid.to_csv(grid_path, index=False, encoding="utf-8-sig")
    merged_summary["outputs"] = {
        "per_rep": per_rep_path.relative_to(ROOT).as_posix(),
        "policy_grid": grid_path.relative_to(ROOT).as_posix(),
        "summary": summary_path.relative_to(ROOT).as_posix(),
    }
    merged_summary["output_sha256"] = {
        "per_rep": _sha256(per_rep_path),
        "policy_grid": _sha256(grid_path),
    }
    summary_path.write_text(
        json.dumps(merged_summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(json.dumps({
        "reps": merged_summary["reps"],
        "per_rep_rows": len(merged_per_rep),
        "policy_grid_rows": len(merged_grid),
        "chosen_model_counts": merged_summary["chosen_model_counts"],
        "out_dir": str(out_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
