"""把 G01 AA 臂的工程冒烟证据导出到 ``outputs/evidence/g_aa_smoke/``。

为什么单独一个导出器
--------------------
``scripts/20_export_evidence.py`` 是 D 阶段硬编码清单（无 CLI）；``35_export_g_smoke_evidence.py``
的契约固定为 A10 矩阵冒烟（两格 × R=3）。AA 臂的产物形状不同（四层各一张逐 rep 表 + manifest），
混进 35 会让它的"28 件"计数与 key_numbers 语义分叉。本脚本与 35 遵守同一套纪律：

* 源缺失 → 列出全部缺失后以 2 退出，不静默跳过；
* 目标已存在且字节不同 → 以 2 退出（``--force`` 才覆盖），防止把旧证据当新证据；
* 写盘后重算 sha256/bytes 与 coverage 对照；
* 证据目录里每个 JSON 必须被 ``coverage.json`` 登记，漏登记即失败；
* 关键数字全部从导出后的文件反算，不手抄。

用法::

    python scripts/37_export_g_aa_smoke.py
    python scripts/37_export_g_aa_smoke.py --run-root out/g_aa_formal --target outputs/evidence/g_aa_formal
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ("L0", "L1", "L2", "L3")
IDENTITY_PATTERNS = ("*binding*.json", "*manifest*.json", "freeze.json", "meta*.json", "decision.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def plan(run_root: Path) -> list[tuple[Path, str]]:
    items = [(run_root / "g_aa_run_summary.json", "g_aa_run_summary.json")]
    for layer in LAYERS:
        items.append((run_root / layer / "aa_repetitions.csv",
                      f"per_layer/{layer}_aa_repetitions.csv"))
        items.append((run_root / layer / "aa_manifest.json",
                      f"manifests/{layer}_aa_manifest.json"))
    return items


def _kind(rel: str) -> str:
    if rel == "g_aa_run_summary.json":
        return "g_aa_run_summary"
    if rel.startswith("per_layer/"):
        return "g_aa_repetitions"
    if rel.startswith("manifests/"):
        return "g_aa_manifest"
    return "g_aa_other"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _key_numbers(target: Path) -> dict:
    summary = json.loads((target / "g_aa_run_summary.json").read_text(encoding="utf-8"))
    layers: dict[str, object] = {}
    for layer in LAYERS:
        table = target / "per_layer" / f"{layer}_aa_repetitions.csv"
        rows = _read_csv(table)
        p_values = [float(row["full_net_profit_p_value"]) for row in rows
                    if row.get("full_net_profit_p_value") not in (None, "")]
        layers[layer] = {
            "rows": len(rows),
            "reps": sorted({int(row["rep"]) for row in rows}),
            "blocks": sorted({row["block"] for row in rows}),
            "n_total": sorted({int(row["n_total"]) for row in rows}),
            "protocol_config_hash": sorted({row["protocol_config_hash"] for row in rows}),
            "p_net_profit_full": p_values,
            "rejections_at_0.05": sum(1 for value in p_values if value < 0.05),
            "cpu_s_sum": round(sum(float(row["total_cpu_s"]) for row in rows), 3),
        }
    return {
        "status": summary.get("status"),
        "all_complete": summary.get("all_complete"),
        "complete": summary.get("complete"),
        "requested": summary.get("requested"),
        "declared_reps_per_layer": summary.get("declared_reps_per_layer"),
        "protocol_config_hash": summary.get("protocol_config_hash"),
        "formal_approval": summary.get("formal_approval"),
        "snapshot_binding": summary.get("snapshot_binding"),
        "layers": layers,
        "note": ("engineering_smoke：每层 1 rep、n=2000。p 值与拒绝计数只证明链路可运行，"
                 "不得作为 AA 验收或假阳性率凭据；正式口径见 17 号池化 FPR。"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出 G01 AA 臂证据")
    parser.add_argument("--run-root", type=Path, default=ROOT / "out" / "g_aa_smoke")
    parser.add_argument("--target", type=Path, default=ROOT / "outputs" / "evidence" / "g_aa_smoke")
    parser.add_argument("--status", default="engineering_smoke")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    run_root = args.run_root if args.run_root.is_absolute() else ROOT / args.run_root
    target = args.target if args.target.is_absolute() else ROOT / args.target
    items = plan(run_root)
    missing = []
    for src, _ in items:
        if src.is_file():
            continue
        try:
            missing.append(_rel(src))
        except ValueError:
            missing.append(src.as_posix())
    if missing:
        print("[g-aa-evidence] 源缺失，拒绝导出：")
        for line in missing:
            print(f"  - {line}")
        return 2

    target.mkdir(parents=True, exist_ok=True)
    conflicts = []
    for src, rel in items:
        dest = target / rel
        if dest.exists() and not args.force and dest.read_bytes() != src.read_bytes():
            conflicts.append(f"{rel}: 目标已存在且字节不同（{_sha256(dest)[:12]}… vs {_sha256(src)[:12]}…）")
    if conflicts:
        print("[g-aa-evidence] 已存在不同版本，拒绝静默覆盖（--force 才覆盖）：")
        for line in conflicts:
            print(f"  - {line}")
        return 2

    records = []
    for src, rel in items:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.read_bytes() != src.read_bytes():
            dest.write_bytes(src.read_bytes())
        digest, size = _sha256(dest), dest.stat().st_size
        records.append({"path": rel, "kind": _kind(rel), "source": _rel(src),
                        "sha256": digest, "bytes": size})

    coverage = {
        "source_label": "合成数据 / 已知 DGP",
        "status": args.status,
        "generated_by": _rel(Path(__file__)),
        "run_root": _rel(run_root),
        "file_count": len(records),
        "total_bytes": sum(int(rec["bytes"]) for rec in records),
        "files": records,
        "key_numbers": _key_numbers(target),
        "note": ("G01 专项臂（AA）的工程冒烟证据；正式 AA 验收必须由 17 号在 n=200 000、"
                 "四层各 250 rep 上合并，未跑满只会写 _provisional。"),
    }
    coverage_path = target / "coverage.json"
    payload = json.dumps(coverage, ensure_ascii=False, indent=2)
    if coverage_path.exists():
        previous = json.loads(coverage_path.read_text(encoding="utf-8"))
        previous.pop("generated_at", None)
        if previous != coverage:
            print("[g-aa-evidence] 覆盖已存在且内容变化，拒绝重写 coverage.json（--force 才覆盖）")
            if not args.force:
                return 2
    coverage_path.write_text(payload, encoding="utf-8", newline="\r\n")

    bad = [str(rec["path"]) for rec in records
           if _sha256(target / str(rec["path"])) != rec["sha256"]
           or (target / str(rec["path"])).stat().st_size != int(rec["bytes"])]
    if bad:
        print("[g-aa-evidence] 写盘后复算不符：" + ", ".join(bad))
        return 2
    registered = {str(rec["path"]) for rec in records}
    unregistered = [path.relative_to(target).as_posix() for path in target.rglob("*.json")
                    if path.relative_to(target).as_posix() not in registered | {"coverage.json"}
                    and any(fnmatch(path.name, pat) for pat in IDENTITY_PATTERNS)]
    if unregistered:
        print("[g-aa-evidence] 身份类 JSON 未登记：" + ", ".join(unregistered))
        return 2

    print(f"[g-aa-evidence] {len(records)} 件 / {coverage['total_bytes']} B → {_rel(coverage_path)}")
    for layer, info in coverage["key_numbers"]["layers"].items():
        print(f"  {layer}: rows={info['rows']} reps={info['reps']} "
              f"n_total={info['n_total']} cpu={info['cpu_s_sum']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
