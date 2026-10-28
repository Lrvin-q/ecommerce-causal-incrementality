"""G01（AA250 正式跑）证据导出与独立复算。

回答方案里的哪个问题："这套五表 + 清洗 + SQL + ITT 的流程，在真的没有效应时，
会不会以 alpha 的概率误报？" —— 本脚本不重跑任何 rep，只做两件事：

1. 把 12 个分片的逐 rep 表、manifest、退出码、合并结果、测试日志**按字节**复制进
   ``outputs/evidence/g01_aa250/``，让"只用证据区就能重建关键数字"成立（AGENTS §12.1）；
2. 用本文件自带的 Clopper–Pearson 与拒绝计数**独立重算**池化 FPR，并与
   ``scripts/17`` 的合并表逐格比对；不一致即非零退出（不静默跳过，§12.7）。

用法::

    python scripts/37_export_g01_evidence.py            # 导出并复算
    python scripts/37_export_g01_evidence.py --check    # 只复算，不写盘
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "out" / "g01_aa250"
LOG_ROOT = ROOT / "out" / "g01_logs"
DEST = ROOT / "outputs" / "evidence" / "g01_aa250"
TABLES = ROOT / "outputs" / "tables"
MERGE_CSV = TABLES / "v3_phase_D_aa_formal_merged.csv"
MERGE_JSON = TABLES / "v3_phase_D_aa_formal_merged.json"
PYTEST_LOG = ROOT / "outputs" / "evidence" / "test_runs" / "pytest_g01_20261028_2234.log"
BEIJING = ZoneInfo("Asia/Shanghai")
SHARDS = [f"s{i:02d}" for i in range(1, 13)]
# 每个分片只跑一层；按"分片→层"映射取表，不能用 12×4 的笛卡尔积。
SHARD_LAYER = {
    "s01": "L0", "s02": "L1", "s03": "L0", "s04": "L1", "s05": "L0", "s06": "L1",
    "s07": "L2", "s08": "L3", "s09": "L2", "s10": "L3", "s11": "L2", "s12": "L3",
}
LAYERS = ("L0", "L1", "L2", "L3")
METRICS = ("net_profit", "paid_purchase_7d", "any_refund_30d")
ALPHA = 0.05
DECLARED_REPS = 250


def clopper_pearson(hits: int, n: int, alpha: float) -> tuple[float, float]:
    low = 0.0 if hits == 0 else float(stats.beta.ppf(alpha / 2, hits, n - hits + 1))
    high = 1.0 if hits == n else float(stats.beta.ppf(1 - alpha / 2, hits + 1, n - hits))
    return low, high


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shard_dir(tag: str, layer: str) -> Path:
    """分片原始产物目录 ``<tag>/layer_runs/<layer>_<stamp>/``；多份就拒绝猜。"""
    matches = sorted((RUN_ROOT / tag / "layer_runs").glob(f"{layer}_*"))
    if len(matches) != 1:
        raise SystemExit(f"{tag}/{layer}: layer_runs 下应恰有一份，实际 {matches}")
    return matches[0]


def shard_table(tag: str, layer: str) -> Path:
    """与 17 号合并读同一份：优先归一化表 ``<root>/<layer>/``，缺失才回退原始表。

    两张表内容不完全相同（36 号收尾会筛 true_aa 并重排索引），
    导出与复算必须对齐合并口径，否则"复算与 17 号表不一致"会变成假故障。
    """
    normalized = RUN_ROOT / tag / layer / "aa_repetitions.csv"
    if normalized.is_file():
        return normalized
    return shard_dir(tag, layer) / "aa_repetitions.csv"


def load_per_rep() -> pd.DataFrame:
    parts = []
    for tag, layer in SHARD_LAYER.items():
        path = shard_table(tag, layer)
        if not path.is_file():
            raise SystemExit(f"缺分片表：{path}")
        frame = pd.read_csv(path)
        frame["_shard"] = tag
        parts.append(frame)
    data = pd.concat(parts, ignore_index=True)
    if "block" in data.columns:
        data = data[data["block"] == "true_aa"].reset_index(drop=True)
    return data


def check_coverage(data: pd.DataFrame) -> list[str]:
    problems = []
    for layer in LAYERS:
        reps = data.loc[data["level"] == layer, "rep"].astype(int)
        got = set(reps.tolist())
        if len(reps) != reps.nunique():
            problems.append(f"{layer}: 逐 rep 行重复 {len(reps) - reps.nunique()} 行")
        missing = sorted(set(range(DECLARED_REPS)) - got)
        if missing:
            problems.append(f"{layer}: 缺 rep {missing[:10]}")
        extra = sorted(got - set(range(DECLARED_REPS)))
        if extra:
            problems.append(f"{layer}: 越界 rep {extra[:10]}")
    return problems


def recompute(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric in METRICS:
        p_col = f"full_{metric}_p_value"
        if p_col not in data.columns:
            raise SystemExit(f"逐 rep 表缺列 {p_col}")
        for layer in list(LAYERS) + ["POOLED"]:
            subset = data if layer == "POOLED" else data[data["level"] == layer]
            values = subset[p_col].dropna()
            n = int(len(values))
            hits = int((values < ALPHA).sum())
            low, high = clopper_pearson(hits, n, ALPHA)
            rows.append({
                "metric": metric, "layer": layer, "reps": n, "rejections": hits,
                "fpr": hits / n if n else float("nan"),
                "cp_low": low, "cp_high": high,
            })
    return pd.DataFrame(rows)


def compare(recomputed: pd.DataFrame) -> list[str]:
    merged = pd.read_csv(MERGE_CSV)
    mismatches = []
    for _, row in recomputed.iterrows():
        hit = merged[(merged["metric"] == row["metric"]) & (merged["layer"] == row["layer"])]
        if hit.empty:
            mismatches.append(f"{row['metric']}/{row['layer']}: 合并表缺该行")
            continue
        ref = hit.iloc[0]
        if int(ref["reps"]) != int(row["reps"]) or int(ref["rejections"]) != int(row["rejections"]):
            mismatches.append(
                f"{row['metric']}/{row['layer']}: 重算 {int(row['rejections'])}/{int(row['reps'])} "
                f"!= 合并 {int(ref['rejections'])}/{int(ref['reps'])}"
            )
        for key in ("fpr", "cp_low", "cp_high"):
            if abs(float(ref[key]) - float(row[key])) > 1e-12:
                mismatches.append(
                    f"{row['metric']}/{row['layer']}: {key} {row[key]} != 合并 {ref[key]}"
                )
    return mismatches


def export(data: pd.DataFrame, recomputed: pd.DataFrame) -> dict:
    if DEST.exists():
        shutil.rmtree(DEST)
    (DEST / "per_rep").mkdir(parents=True)
    (DEST / "shards").mkdir()
    (DEST / "logs").mkdir()
    (DEST / "merged").mkdir()
    (DEST / "scripts").mkdir()

    records: list[dict] = []

    def record(path: Path, note: str = "") -> None:
        rel = path.relative_to(ROOT).as_posix()
        entry = {"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)}
        if path.suffix == ".csv":
            try:
                entry["rows"] = int(len(pd.read_csv(path)))
            except Exception:  # noqa: BLE001 - 非数据表不该在这里冒出来
                entry["rows"] = None
        if note:
            entry["note"] = note
        records.append(entry)

    for tag, layer in SHARD_LAYER.items():
        # 表优先归一化副本（与 17 号合并同源）；manifest 只由 36 号写到 <root>/<layer>/
        for src in (shard_table(tag, layer),
                    RUN_ROOT / tag / layer / "aa_manifest.json"):
            if not src.is_file():
                raise SystemExit(f"缺产物：{src}")
            target = DEST / "per_rep" / f"{tag}__{layer}__{src.name}"
            shutil.copy2(src, target)
            record(target, f"分片 {tag} / {layer}")
        exit_file = LOG_ROOT / f"{tag}.exit"
        if not exit_file.is_file():
            raise SystemExit(f"缺退出码：{exit_file}")
        shutil.copy2(exit_file, DEST / "shards" / f"{tag}.exit")
        record(DEST / "shards" / f"{tag}.exit")

    for src, name in (
        (RUN_ROOT / "coverage.json", "coverage_check.json"),
        (MERGE_CSV, "merged/v3_phase_D_aa_formal_merged.csv"),
        (MERGE_JSON, "merged/v3_phase_D_aa_formal_merged.json"),
        (PYTEST_LOG, "logs/pytest_g01_20261028_2234.log"),
        (LOG_ROOT / "merge.log", "logs/merge.log"),
        (LOG_ROOT / "verify.log", "logs/verify.log"),
        (ROOT / "out" / "g01_runner.sh", "scripts/g01_runner.sh"),
        (ROOT / "out" / "g01_verify.py", "scripts/g01_verify.py"),
    ):
        if not src.is_file():
            raise SystemExit(f"缺产物：{src}")
        target = DEST / name
        shutil.copy2(src, target)
        record(target)

    recomputed.to_csv(DEST / "recomputed_fpr.csv", index=False, encoding="utf-8-sig",
                      lineterminator="\n")
    record(DEST / "recomputed_fpr.csv", "本脚本独立重算（不读 17 的公式）")

    pooled = recomputed[recomputed["layer"] == "POOLED"].set_index("metric")
    payload = {
        "source_label": "合成数据 / 已知 DGP",
        "purpose": "g01_aa250_formal_evidence",
        "exported_at": datetime.now(BEIJING).isoformat(timespec="seconds"),
        "approval": "G01-AA250-20261028",
        "protocol_config_hash": sorted(data["protocol_config_hash"].dropna().unique().tolist())
        if "protocol_config_hash" in data.columns else [],
        "declared_reps_per_layer": DECLARED_REPS,
        "total_true_aa_rows": int(len(data)),
        "pooled": {
            metric: {
                "reps": int(pooled.loc[metric, "reps"]),
                "rejections": int(pooled.loc[metric, "rejections"]),
                "fpr": float(pooled.loc[metric, "fpr"]),
                "cp_low": float(pooled.loc[metric, "cp_low"]),
                "cp_high": float(pooled.loc[metric, "cp_high"]),
            }
            for metric in METRICS
        },
        "files": records,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    (DEST / "coverage.json").write_text(text, encoding="utf-8", newline="")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G01 证据导出与独立复算")
    parser.add_argument("--check", action="store_true", help="只复算并比对，不写盘")
    args = parser.parse_args(argv)

    data = load_per_rep()
    problems = check_coverage(data)
    recomputed = recompute(data)
    mismatches = compare(recomputed)
    fatal = problems + mismatches
    for line in fatal:
        print("  ! " + line)
    print(f"逐 rep 行={len(data)}；重算 {len(recomputed)} 格；不一致 {len(mismatches)}")
    print(recomputed[recomputed["layer"] == "POOLED"].to_string(index=False))
    if fatal:
        return 1
    if args.check:
        print("check 模式：未写盘")
        return 0
    payload = export(data, recomputed)
    print(f"导出 {len(payload['files'])} 个文件 -> {DEST}")
    print(f"池化 FPR：" + json.dumps(payload["pooled"]["net_profit"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
