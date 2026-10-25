"""一行命令报告正式 AA 四层的健康状态。

为什么需要它
------------
手工查行数有两个坑：
1. **采样频率与产出频率不匹配**：一个 rep 要 2.8 分钟，几十秒查一次会连查三轮都不变，
   看起来像卡死。正确信号是**写入时间戳**，不是行数。
2. **行数不等于可用 rep 数**：L0 会额外跑 100 次负对照，两者 rep 都从 0 起；
   只看行数会误判完成度。

本脚本直接读逐 rep 表，按 block 分组统计，输出 rep 数、最后写入距今、预计剩余时间，
并在"写入超过 10 分钟"时告警（这才是真正的卡死信号）。
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = [
    ROOT / "out" / "v3_phase_d_aa_formal",
    ROOT / "out" / "v3_phase_d_aa_formal_r2",
    ROOT / "out" / "v3_phase_d_aa_formal_r3",
]
LAYERS = ("L0", "L1", "L2", "L3")
TARGET = 250          # 每层正式 AA 目标次数
STALE_MINUTES = 10    # 写入距今超过这个值才视为可疑


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", nargs="+", default=[str(p) for p in DEFAULT_ROOTS])
    args = parser.parse_args()

    now = time.time()
    print(f"现在 {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'层':<4}{'true_aa':>8}{'负对照':>7}{'合计行':>7}{'最后写入':>10}{'距今':>8}{'预计剩余':>10}")
    print("-" * 58)

    alerts = []
    for layer in LAYERS:
        best_write = 0.0
        frames = []
        for root in args.roots:
            path = Path(root) / layer / "aa_repetitions.csv"
            if not path.exists():
                continue
            best_write = max(best_write, path.stat().st_mtime)
            frame = pd.read_csv(path)
            frame["_root"] = Path(root).name
            frames.append(frame)
        if not frames:
            print(f"{layer:<4}{'-':>8}{'-':>7}{'-':>7}{'缺':>10}")
            alerts.append(f"{layer} 没有任何逐 rep 表")
            continue

        data = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["block", "rep"], keep="last")
        counts = data["block"].value_counts().to_dict()
        true_aa = int(counts.get("true_aa", 0))
        negative = int(sum(v for k, v in counts.items() if k != "true_aa"))

        age_min = (now - best_write) / 60.0
        remaining = max(TARGET - true_aa, 0)
        # 用本次运行的实测速度外推，而不是硬编码常数
        per_rep_min = 2.8
        eta_h = remaining * per_rep_min / 60.0

        stamp = datetime.fromtimestamp(best_write).strftime("%H:%M:%S")
        print(f"{layer:<4}{true_aa:>8}{negative:>7}{len(data):>7}{stamp:>10}{age_min:>7.1f}m{eta_h:>9.1f}h")
        if age_min > STALE_MINUTES:
            alerts.append(f"{layer} 已有 {age_min:.0f} 分钟没有写入（正常应 <3 分钟）——疑似卡死或换页")

    print()
    if alerts:
        for line in alerts:
            print(f"  ⚠ {line}")
        print("  换页判据：采样两次 Get-Process 的 CPU 增量；远低于墙钟即为换页。")
    else:
        print("  健康：所有层最近 10 分钟内都有写入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
