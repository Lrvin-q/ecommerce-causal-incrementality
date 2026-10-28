"""G01 正式跑的独立完整性核对：不依赖 17 号，直接读 12 个分片表。

回答的问题：12 个 rep 区间真的拼成 4 层 × 250 次、无重叠、无缺口、同一协议吗？
17 号按 (block, rep) 去重 keep="last"，重叠区间会被**静默**吞掉；本脚本显式查重。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "g01_aa250"
LOGS = ROOT / "out" / "g01_logs"
SHARDS = [f"s{i:02d}" for i in range(1, 13)]
SHARD_LAYER = {
    "s01": "L0", "s02": "L1", "s03": "L0", "s04": "L1", "s05": "L0", "s06": "L1",
    "s07": "L2", "s08": "L3", "s09": "L2", "s10": "L3", "s11": "L2", "s12": "L3",
}
LAYERS = ("L0", "L1", "L2", "L3")
DECLARED_REPS = 250
EXPECTED_N = 200_000
ALPHA = 0.05
BEIJING = ZoneInfo("Asia/Shanghai")


def _shard_table(tag: str, layer: str) -> Path | None:
    """优先读合并所读的归一化表（``<root>/<layer>/``），缺失再回退 layer_runs 原始表。

    两者内容不完全相同（36 号 ``split_layer_table`` 会筛 true_aa 并重排索引），
    校验必须与 17 号合并读同一份，否则"校验通过但合并结果不同"。
    """
    normalized = OUT / tag / layer / "aa_repetitions.csv"
    if normalized.is_file():
        return normalized
    matches = sorted((OUT / tag / "layer_runs").glob(f"{layer}_*/aa_repetitions.csv"))
    if len(matches) > 1:
        raise SystemExit(f"{tag}/{layer}: layer_runs 下有多份表 {matches}，拒绝猜测")
    return matches[0] if matches else None


def main() -> int:
    problems: list[str] = []
    shard_exit = {}
    for tag in SHARDS:
        path = LOGS / f"{tag}.exit"
        if not path.is_file():
            problems.append(f"{tag}: 缺 exit 文件（未跑或未收尾）")
            shard_exit[tag] = None
            continue
        code = int(path.read_text().strip())
        shard_exit[tag] = code
        if code != 0:
            problems.append(f"{tag}: exit={code}")

    per_layer: dict[str, dict] = {}
    hashes: set[str] = set()
    for layer in LAYERS:
        parts, sources = [], []
        for tag in SHARDS:
            csv = _shard_table(tag, layer)
            if csv is not None:
                frame = pd.read_csv(csv)
                frame["_shard"] = tag
                parts.append(frame)
                sources.append(tag)
        if not parts:
            problems.append(f"{layer}: 没有任何分片表")
            continue
        data = pd.concat(parts, ignore_index=True)
        true_aa = data[data["block"] == "true_aa"] if "block" in data.columns else data
        reps = true_aa["rep"].astype(int)
        duplicated = sorted(reps[reps.duplicated()].unique().tolist())
        got = set(reps.tolist())
        missing = sorted(set(range(DECLARED_REPS)) - got)
        extra = sorted(got - set(range(DECLARED_REPS)))
        if duplicated:
            problems.append(f"{layer}: rep 跨分片重复 {duplicated[:10]}")
        if missing:
            problems.append(f"{layer}: 缺 rep {missing[:10]}")
        if extra:
            problems.append(f"{layer}: 越界 rep {extra[:10]}")
        n_values = sorted(set(int(v) for v in true_aa["n_total"].dropna().unique())) \
            if "n_total" in true_aa.columns else []
        if n_values != [EXPECTED_N]:
            problems.append(f"{layer}: n_total={n_values} != {EXPECTED_N}")
        if "alpha" in true_aa.columns:
            alphas = sorted({round(float(v), 12) for v in true_aa["alpha"].dropna().unique()})
            if len(alphas) != 1 or abs(alphas[0] - ALPHA) > 1e-12:
                problems.append(f"{layer}: alpha={alphas}")
        if "protocol_config_hash" in true_aa.columns:
            hashes |= set(true_aa["protocol_config_hash"].dropna().astype(str))
        per_layer[layer] = {
            "shards": sources,
            "rows_true_aa": int(len(true_aa)),
            "reps_unique": int(reps.nunique()),
            "missing_reps": missing,
            "duplicated_reps": duplicated,
            "n_total": n_values,
        }

    if len(hashes) != 1:
        problems.append(f"protocol_config_hash 不唯一：{sorted(hashes)}")

    payload = {
        "source_label": "合成数据 / 已知 DGP",
        "purpose": "g01_aa_arm_coverage_check",
        "checked_at": datetime.now(BEIJING).isoformat(timespec="seconds"),
        "approval": "G01-AA250-20261028",
        "declared_reps_per_layer": DECLARED_REPS,
        "shards": {tag: {"layer": SHARD_LAYER[tag], "exit": shard_exit[tag]} for tag in SHARDS},
        "per_layer": per_layer,
        "total_true_aa_rows": int(sum(v["rows_true_aa"] for v in per_layer.values())),
        "protocol_config_hash": sorted(hashes),
        "problems": problems,
        "passed": not problems,
    }
    target = OUT / "coverage.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(("PASS" if not problems else "FAIL") + f" -> {target}")
    for layer, info in per_layer.items():
        print(f"  {layer}: rows={info['rows_true_aa']} unique_reps={info['reps_unique']} "
              f"shards={info['shards']}")
    for problem in problems:
        print("  ! " + problem)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
