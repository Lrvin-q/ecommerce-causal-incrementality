"""把 D 阶段的门禁证据从 ``out/`` 导出到 ``outputs/evidence/``（可入库）。

为什么需要它
------------
``.gitignore`` 忽略了整个 ``out/``，而 AA 的去重、15 格的合并、快照绑定所依赖的
逐 rep 表、manifest 与 binding json 全在 ``out/`` 下。结果是：**换一台机器克隆仓库，
拿不到任何可复算的原始证据**——工程评审判定 D 阶段"不可交接"（E-1）。

``out/`` 里真正大的只有 tmp 中间产物（负对照目录 52 MB），而**证据本身不到 1 MB**：
逐 rep 表 5 个（每个约 50 KB）、代表性 manifest 4 个（每个 6 KB）、binding 2 个。

导出什么
--------
- AA 四层的 ``aa_repetitions.csv``（去重前的原始 338/338/338/370 行）
- 负对照的 ``aa_repetitions.csv``（101 行：1 真 AA + 100 负对照）
- 三路功效格的 ``local_power_summary.csv``
- 每层一个代表性 ``manifest.json``（记录 DGP 参数与产物哈希）
- 两个快照的 binding json（``aa_snapshot`` / ``c3_snapshot``）
- 一份 ``coverage.json``：每条证据的来源路径与 sha256，供下游核对

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\20_export_evidence.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "outputs" / "evidence"

#: (源路径, 目标相对路径)。源不存在时**抛错**——静默跳过会让"证据缺失"看不出来。
PLAN: tuple[tuple[str, str], ...] = (
    ("out/v3_phase_d_aa_nc20w_r2/aa_repetitions.csv", "negctl/aa_repetitions.csv"),
    ("out/v3_phase_d_local_power/formal_L0/local_power_summary.csv", "local_power/L0_summary.csv"),
    ("out/v3_phase_d_local_power/formal_L1/local_power_summary.csv", "local_power/L1_summary.csv"),
    ("out/v3_phase_d_local_power/formal_L2/local_power_summary.csv", "local_power/L2_summary.csv"),
    ("out/aa_snapshot_binding.json", "bindings/aa_snapshot_binding.json"),
    ("out/c3_snapshot_binding.json", "bindings/c3_snapshot_binding.json"),
)

#: 正式 AA 的逐 rep 表**分散在 5 个 run-root**（换页重启所致，各含部分 rep）。
#: 只导其中一个会得到 48/250 行的残缺证据——这是评审 E-1 的要害，必须合并导出。
AA_RUN_ROOTS: tuple[str, ...] = (
    "v3_phase_d_aa_formal",
    "v3_phase_d_aa_formal_r2",
    "v3_phase_d_aa_formal_r2_det",
    "v3_phase_d_aa_formal_r3",
    "v3_phase_d_aa_formal_r3_det",
)
AA_LEVELS: tuple[str, ...] = ("L0", "L1", "L2", "L3")

#: 代表性 manifest：每层取该层最后一个 rep 的 manifest。
MANIFEST_GLOBS: dict[str, str] = {
    "L0": "out/v3_phase_d_aa_formal_r2/L0/tmp/*/manifest.json",
    "L1": "out/v3_phase_d_aa_formal_r2/L1/tmp/*/manifest.json",
    "L2": "out/v3_phase_d_aa_formal_r2/L2/tmp/*/manifest.json",
    "L3": "out/v3_phase_d_aa_formal_r2/L3/tmp/*/manifest.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []

    # 1) AA 逐 rep 表：跨 5 个 run-root 合并成一个自足文件
    import pandas as pd

    aa_frames: list[pd.DataFrame] = []
    for run_root in AA_RUN_ROOTS:
        for level in AA_LEVELS:
            path = ROOT / "out" / run_root / level / "aa_repetitions.csv"
            if not path.is_file():
                continue
            frame = pd.read_csv(path)
            frame["source_root"] = run_root
            aa_frames.append(frame)
    if not aa_frames:
        raise FileNotFoundError("没有找到任何 AA 逐 rep 表")
    merged_aa = pd.concat(aa_frames, ignore_index=True)
    aa_destination = TARGET / "aa" / "all_repetitions.csv"
    aa_destination.parent.mkdir(parents=True, exist_ok=True)
    merged_aa.to_csv(aa_destination, index=False, encoding="utf-8-sig")
    # 去重键必须带 level：``block`` 的值只有 "true_aa"，不含层号，
    # 用 [block, rep] 会把四层的同一 rep 号误判为重复，1000 行被压成 250 行。
    key_columns = [c for c in ("level", "block", "rep") if c in merged_aa.columns]
    deduped = merged_aa.drop_duplicates(subset=key_columns) if key_columns else merged_aa
    records.append({
        "kind": "aa_repetitions_merged",
        "source": " + ".join(AA_RUN_ROOTS),
        "target": aa_destination.relative_to(ROOT).as_posix(),
        "bytes": aa_destination.stat().st_size,
        "sha256": _sha256(aa_destination),
        "rows_raw": int(len(merged_aa)),
        "rows_deduped": int(len(deduped)),
    })

    # 2) 其余单文件证据
    for source_rel, target_rel in PLAN:
        source = ROOT / source_rel
        if not source.is_file():
            raise FileNotFoundError(f"缺少证据文件：{source_rel}（不静默跳过）")
        destination = TARGET / target_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        records.append({
            "kind": "raw",
            "source": source_rel,
            "target": destination.relative_to(ROOT).as_posix(),
            "bytes": destination.stat().st_size,
            "sha256": _sha256(destination),
        })

    for level, pattern in MANIFEST_GLOBS.items():
        candidates = sorted(ROOT.glob(pattern))
        if not candidates:
            raise FileNotFoundError(f"{level} 没有找到 manifest：{pattern}")
        source = candidates[-1]
        destination = TARGET / "aa" / f"manifest_{level}.json"
        shutil.copy2(source, destination)
        records.append({
            "kind": "manifest",
            "source": source.relative_to(ROOT).as_posix(),
            "target": destination.relative_to(ROOT).as_posix(),
            "bytes": destination.stat().st_size,
            "sha256": _sha256(destination),
        })

    coverage = {
        "source_label": "合成数据 / 已知 DGP",
        "purpose": "D 阶段门禁证据的可交接副本（原始证据在 out/，被 .gitignore 排除）",
        "note": "逐 rep 表用于独立重建 FPR/CP/SE；manifest 记录 DGP 参数与产物哈希；binding 记录源码快照指纹。",
        "records": records,
        "total_bytes": sum(int(r["bytes"]) for r in records),
    }
    (TARGET / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[完成] 导出 {len(records)} 个文件，合计 {coverage['total_bytes'] / 1024:.0f} KB → {TARGET.relative_to(ROOT)}")
    for record in records:
        print(f"  {record['target']}  {record['bytes']} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
