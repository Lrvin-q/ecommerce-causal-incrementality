"""合并四层正式 AA，输出合并假阳性率、Clopper–Pearson 区间与 SE 校准。

为什么需要这个脚本
------------------
正式 AA 按层并行跑（4 个进程各 250 次），每层各自落一张逐 rep 表。
GOAL G01 的正式口径是**合计 1000 次**，所以必须合并后再算 FPR——
逐层 250 次的 CP 半宽约 ±0.03，只能描述不能判定；合并 1000 次约 ±0.014，才够判"FPR≈0.05"。

同时补上独立科学评审要求的 C6 两项：
  1. **SE 校准**：逐 rep 效应估计的经验标准差 / 平均估计标准误。比值显著偏离 1 说明 SE 不可信。
     注意这**不是**独立于 FPR 的证据——对 Welch t，"CI 含 0"等价于"p≥α"，覆盖率 ≡ 1−FPR。
     SE 校准是另一个维度：它检验"点估计的波动是否与声称的精度相符"。
  2. **本 R 下的实际功效**：给定真实的 FPR 偏离量，这个 R 有多大概率把它判出来。
     不做这一步就会把"没检出"误读成"没问题"。

纪律
----
- **只汇总 `block == "true_aa"`**。负对照（`purchase_null_negative_control`）的购买率行虽然
  名义上也服从 size 0.05，但它是另一个 block，混进来会污染 AA 计数。评审明确要求过滤。
- 不读真值；只读逐 rep 表的 p 值与效应列。
- 缺层或缺 rep 要报清楚，不许用现有层外推。
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ("L0", "L1", "L2", "L3")
METRICS = ("net_profit", "paid_purchase_7d", "any_refund_30d")


def clopper_pearson(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    """精确二项区间（等尾），与 AA 模块内部实现同一定义。"""
    if trials <= 0:
        return float("nan"), float("nan")
    alpha = 1.0 - confidence
    lower = 0.0 if successes == 0 else float(stats.beta.ppf(alpha / 2, successes, trials - successes + 1))
    upper = 1.0 if successes == trials else float(stats.beta.ppf(1 - alpha / 2, successes + 1, trials - successes))
    return lower, upper


def detect_power(true_rate: float, reps: int, alpha: float, band: tuple[float, float]) -> float:
    """给定真实 FPR 与 R，估出"点估计落在验收带之外"的概率（正态近似）。"""
    if reps <= 0:
        return float("nan")
    se = math.sqrt(max(true_rate * (1 - true_rate), 1e-12) / reps)
    low = stats.norm.cdf((band[0] - true_rate) / se)
    high = 1.0 - stats.norm.cdf((band[1] - true_rate) / se)
    return float(low + high)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", nargs="+",
                        default=[str(ROOT / "out" / "v3_phase_d_aa_formal"),
                                 str(ROOT / "out" / "v3_phase_d_aa_formal_r2"),
                                 str(ROOT / "out" / "v3_phase_d_aa_formal_r3"),
                                 str(ROOT / "out" / "v3_phase_d_aa_formal_r2_det"),
                                 str(ROOT / "out" / "v3_phase_d_aa_formal_r3_det")],
                        help="可给多个运行根；同名层会合并并按 (层, rep) 去重")
    parser.add_argument("--band-low", type=float, default=0.035)
    parser.add_argument("--band-high", type=float, default=0.065)
    args = parser.parse_args()

    frames = []
    missing = []
    # 一次正式跑会因内存复位而分成多个 run-root（_r2、_r3 …）。
    # 必须读入所有根目录里同名的逐 rep 表并按 rep 去重，
    # 否则会漏掉复位前已完成的 rep，得出错误的池化 FPR。
    for layer in LAYERS:
        parts = []
        for root in args.root:
            path = Path(root) / layer / "aa_repetitions.csv"
            if path.exists():
                frame = pd.read_csv(path)
                frame["_source_root"] = Path(root).name
                parts.append(frame)
        if not parts:
            missing.append(layer)
            continue
        layer_data = pd.concat(parts, ignore_index=True)
        read_rows = len(layer_data)
        layer_data = layer_data.drop_duplicates(subset=["block", "rep"], keep="last")
        layer_data["_layer_dir"] = layer
        frames.append(layer_data)
        print(f"  {layer}: 读入 {read_rows} 行，去重后 {len(layer_data)} 行"
              f"（重复 {read_rows - len(layer_data)}）")
    if not frames:
        print("没有任何层的逐 rep 表；AA 可能还没落盘")
        return 1
    data = pd.concat(frames, ignore_index=True)

    # 跨 run-root 合并前必须确认协议一致：不同协议版本的 rep 不能混进同一个池化 FPR。
    # 这条不会自己暴露——混进来的 rep 行看起来完全正常，只会让池化结果悄悄失效。
    if "protocol_config_hash" in data.columns:
        protocol_hashes = sorted(data["protocol_config_hash"].dropna().unique())
        if len(protocol_hashes) > 1:
            raise SystemExit(
                "拒绝合并：不同 run-root 的 protocol_config_hash 不一致 "
                f"{protocol_hashes}；这些 rep 不属同一协议，池化结果无效"
            )
        if protocol_hashes:
            print(f"  协议指纹一致：{protocol_hashes[0][:16]}…")

    total_rows = len(data)
    data = data[data["block"] == "true_aa"].copy()
    excluded = total_rows - len(data)
    alpha = float(data["alpha"].iloc[0]) if "alpha" in data.columns else 0.05

    rows = []
    for metric in METRICS:
        p_col = f"full_{metric}_p_value"
        if p_col not in data.columns:
            continue
        for layer in list(LAYERS) + ["POOLED"]:
            subset = data if layer == "POOLED" else data[data["_layer_dir"] == layer]
            values = subset[p_col].dropna()
            n = int(len(values))
            if n == 0:
                continue
            hits = int((values < alpha).sum())
            low, high = clopper_pearson(hits, n)
            rows.append({
                "source_label": "合成数据 / 已知 DGP",
                "block": "true_aa",
                "metric": metric,
                "population": "full",
                "layer": layer,
                "reps": n,
                "rejections": hits,
                "fpr": hits / n,
                "cp_low": low,
                "cp_high": high,
                "mc_se": math.sqrt(hits / n * (1 - hits / n) / n),
                "alpha": alpha,
                "detect_power_if_true_0_08": detect_power(0.08, n, alpha, (args.band_low, args.band_high)),
                "detect_power_if_true_0_09": detect_power(0.09, n, alpha, (args.band_low, args.band_high)),
            })

    summary = pd.DataFrame(rows)
    tables = ROOT / "outputs" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    # 每层目标 250 次；未跑满时**不得**写进正式证据路径，
    # 否则半成品会被后续的人当成最终结果引用（数字对、但样本量不够）。
    target_reps = 250
    reps_by_layer = {layer: int((data["_layer_dir"] == layer).sum()) for layer in LAYERS}
    incomplete = {k: v for k, v in reps_by_layer.items() if v < target_reps}
    suffix = "_provisional" if incomplete else ""
    if incomplete:
        print(f"  ⚠ 未跑满：{incomplete}（目标 {target_reps}/层）；"
              f"本次写入 {suffix} 副本，不得作为验收凭据")
    csv_path = tables / f"v3_phase_D_aa_formal_merged{suffix}.csv"
    summary.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # SE 校准：经验 SD / 平均估计 SE
    calibration = []
    for layer in list(LAYERS) + ["POOLED"]:
        subset = data if layer == "POOLED" else data[data["_layer_dir"] == layer]
        diff = subset["full_net_profit_diff"].dropna()
        se = subset["full_net_profit_se"].dropna()
        if len(diff) < 2 or len(se) == 0:
            continue
        calibration.append({
            "layer": layer,
            "reps": int(len(diff)),
            "empirical_sd": float(diff.std(ddof=1)),
            "mean_estimated_se": float(se.mean()),
            "ratio": float(diff.std(ddof=1) / se.mean()) if se.mean() > 0 else float("nan"),
            "mean_effect": float(diff.mean()),
        })

    result = {
        "source_label": "合成数据 / 已知 DGP",
        "roots": [str(path) for path in args.root],
        "layers_found": [x for x in LAYERS if x not in missing],
        "layers_missing": missing,
        "rows_excluded_non_true_aa": int(excluded),
        "target_reps_per_layer": target_reps,
        "reps_by_layer": reps_by_layer,
        "provisional": bool(incomplete),
        "alpha": alpha,
        "summary_csv": csv_path.relative_to(ROOT).as_posix(),
        "se_calibration": calibration,
        "note": "只汇总 block=true_aa；负对照（purchase_null_negative_control）不计入 AA。"
                "覆盖率与 FPR 在 Welch t 下机械互补，SE 校准是另一个独立维度。",
    }
    json_path = tables / f"v3_phase_D_aa_formal_merged{suffix}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(summary.to_string(index=False))
    print()
    for item in calibration:
        print(f"  SE 校准 {item['layer']:<7} 经验SD/平均SE = {item['ratio']:.3f}  (reps={item['reps']})")
    print()
    if missing:
        print(f"  缺层：{missing}（不得用现有层外推）")
    print(f"  已排除非 true_aa 行：{excluded}")
    print(f"  输出：{csv_path.relative_to(ROOT)} 与 {json_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
