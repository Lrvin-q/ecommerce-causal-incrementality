"""把 D03 正式 R 的运行证据从 ``out/`` 导出到 ``outputs/evidence/d03_formal/``。

为什么需要它
------------
``out/`` 被 gitignore，正式 R 的 manifest、快照绑定、四个分片的 summary 与运行日志
只存在于本机。合并后的两张结果表已入库 ``outputs/tables/``，但它们只能证明"算出了
什么"，不能证明"跑的是哪份源码、跑了多少 rep、有没有报错"。本脚本补齐后者，
并在 ``coverage.json`` 里记录每个文件的 sha256 与完整性校验结果。

导出什么
--------
- ``run_manifest.json``：正式 R 的设计（200 rep / 4 分片 / 快照哈希 / 启动时间）
- ``snapshot_binding.json``：83 个源码/配置文件的逐文件哈希与 combined hash
- ``shard{0..3}_summary.json``：各分片的 rep 覆盖、config_hash、耗时
- ``shard{0..3}_run.log``：逐 rep 日志（证明 rep 逐条跑完、无 stderr）
- 不复制 72 000 行策略网格；合并表在 ``outputs/tables/``，这里只记录其 sha256 与行数

校验（任一失败即抛错，不写 coverage）
------------------------------------
1. 四个分片都是 ``status=formal_r`` 且 ``n_per_rep`` 与 manifest 一致；
2. 四个分片的 ``rep_ids`` 并起来恰好是 ``0..expected_reps-1``，无缺无重；
3. 四个分片的 ``config_hash`` 完全一致，且与合并 summary 一致；
4. manifest 的 snapshot combined hash == 绑定文件的 combined hash，git commit 一致；
5. 四个 ``run.err`` 均为空；
6. 合并表的行数与 sha256 与合并 summary 的 ``outputs``/``output_sha256`` 一致。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\27_export_d03_evidence.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "out" / "d03_formal"
BINDING = ROOT / "out" / "d03_formal_snapshot_binding.json"
TARGET = ROOT / "outputs" / "evidence" / "d03_formal"
TABLES = ROOT / "outputs" / "tables"

EXPECTED_REPS = 200
N_PER_REP = 200_000
SHARDS = 4


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _copy(source: Path, target: Path) -> dict[str, object]:
    _require(source.is_file(), f"缺少证据文件：{source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return {
        "source": source.relative_to(ROOT).as_posix(),
        "target": target.relative_to(ROOT).as_posix(),
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
    }


def _load_json(path: Path) -> dict:
    _require(path.is_file(), f"缺少 JSON：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    manifest = _load_json(SOURCE / "manifest.json")
    binding = _load_json(BINDING)
    merged_summary = _load_json(TABLES / "v3_phase_D03_formal_summary.json")

    _require(
        manifest["design"]["reps"] == EXPECTED_REPS
        and manifest["design"]["n_per_rep"] == N_PER_REP,
        "manifest 的设计与 200×200000 不符",
    )
    _require(
        manifest["snapshot_combined_sha256"] == binding["combined_sha256"],
        "manifest 与绑定文件的快照哈希不一致",
    )
    _require(
        manifest["git_commit"] == binding["git_commit"],
        "manifest 与绑定文件的 git commit 不一致",
    )

    summaries: list[dict] = []
    rep_ids: list[int] = []
    config_hashes: set[str] = set()
    records: list[dict[str, object]] = []
    err_sizes: dict[str, int] = {}

    for shard in range(SHARDS):
        directory = SOURCE / f"shard{shard}"
        summary_path = directory / "v3_phase_D03_diagnostic_summary.json"
        summary = _load_json(summary_path)
        _require(
            bool(summary.get("formal_r")) and summary.get("status") == "formal_r",
            f"shard{shard} 不是正式 R 产物",
        )
        _require(
            int(summary["n_per_rep"]) == N_PER_REP,
            f"shard{shard} n_per_rep 不符",
        )
        ids = [int(value) for value in summary["rep_ids"]]
        _require(len(ids) == len(set(ids)), f"shard{shard} rep_ids 内部重复")
        rep_ids.extend(ids)
        summaries.append(summary)
        config_hashes.add(str(summary.get("config_hash")))

        err = directory / "run.err"
        _require(err.is_file(), f"shard{shard} 缺 run.err")
        _require(err.stat().st_size == 0, f"shard{shard} run.err 非空，不能当无错证据")
        err_sizes[f"shard{shard}"] = int(err.stat().st_size)

        records.append({
            "kind": "shard_summary",
            **_copy(summary_path, TARGET / f"shard{shard}_summary.json"),
            "rep_ids": ids,
        })
        records.append({
            "kind": "shard_run_log",
            **_copy(directory / "run.log", TARGET / f"shard{shard}_run.log"),
        })
        records.append({
            "kind": "shard_run_err",
            **_copy(err, TARGET / f"shard{shard}_run.err"),
            "bytes_checked_empty": int(err.stat().st_size),
        })

    _require(
        sorted(rep_ids) == list(range(EXPECTED_REPS)),
        f"四个分片的 rep 并集不是 0..{EXPECTED_REPS - 1}（{len(rep_ids)} 条）",
    )
    _require(len(config_hashes) == 1, f"分片 config_hash 不一致：{config_hashes}")
    _require(
        config_hashes == {str(merged_summary.get("config_hash"))},
        "分片 config_hash 与合并 summary 不一致",
    )

    records.append({
        "kind": "run_manifest",
        **_copy(SOURCE / "manifest.json", TARGET / "run_manifest.json"),
    })
    records.append({
        "kind": "snapshot_binding",
        **_copy(BINDING, TARGET / "snapshot_binding.json"),
    })

    merged_ok = True
    merged: dict[str, object] = {}
    for name, key in (("per_rep", "per_rep"), ("policy_grid", "policy_grid")):
        path = TABLES / f"v3_phase_D03_formal_{name}.csv"
        _require(path.is_file(), f"缺少合并表：{path}")
        sha = _sha256(path)
        merged_ok = merged_ok and sha == merged_summary["output_sha256"][key]
        _require(
            sha == merged_summary["output_sha256"][key],
            f"合并表 {name} 的 sha256 与合并 summary 不一致",
        )
        rows = sum(1 for _ in path.open("rb")) - 1
        merged[key] = {
            "path": path.relative_to(ROOT).as_posix(),
            "rows": int(rows),
            "sha256": sha,
            "copied": False,
        }
    rows_ok = (
        merged["per_rep"]["rows"] == EXPECTED_REPS * 5
        and merged["policy_grid"]["rows"] == EXPECTED_REPS * 5 * 8 * 9
    )
    _require(
        merged["per_rep"]["rows"] == EXPECTED_REPS * 5,
        f"逐 rep 表应为 {EXPECTED_REPS * 5} 行，实际 {merged['per_rep']['rows']}",
    )
    _require(
        merged["policy_grid"]["rows"] == EXPECTED_REPS * 5 * 8 * 9,
        f"策略网格应为 {EXPECTED_REPS * 5 * 8 * 9} 行，实际 {merged['policy_grid']['rows']}",
    )

    formal_flags = [bool(s.get("formal_r")) and s.get("status") == "formal_r" for s in summaries]
    rep_ids_ok = sorted(rep_ids) == list(range(EXPECTED_REPS))
    config_identical = len(config_hashes) == 1
    config_matches_merged = config_hashes == {str(merged_summary.get("config_hash"))}
    binding_ok = (
        manifest["snapshot_combined_sha256"] == binding["combined_sha256"]
        and manifest["git_commit"] == binding["git_commit"]
    )
    run_err_ok = all(size == 0 for size in err_sizes.values())

    live_drift: dict[str, object] = {
        "n_bound": len(binding["files"]),
        "n_live_different": 0,
        "n_live_missing": 0,
        "live_different": [],
        "live_missing": [],
    }
    for relative, expected in sorted(binding["files"].items()):
        live = ROOT / relative
        if not live.is_file():
            live_drift["n_live_missing"] += 1
            live_drift["live_missing"].append(relative)
        elif _sha256(live) != expected:
            live_drift["n_live_different"] += 1
            live_drift["live_different"].append(relative)

    coverage = {
        "phase": "D03_formal_evidence",
        "design": {
            "reps": EXPECTED_REPS,
            "n_per_rep": N_PER_REP,
            "shards": SHARDS,
            "snapshot_combined_sha256": binding["combined_sha256"],
            "git_commit": binding["git_commit"],
            "config_hash": sorted(config_hashes)[0],
        },
        "checks": {
            "all_shards_formal_r": all(formal_flags),
            "rep_ids_exactly_0_to_199": rep_ids_ok,
            "n_rep_ids": len(rep_ids),
            "config_hash_identical_across_shards": config_identical,
            "config_hash_matches_merged_summary": config_matches_merged,
            "manifest_matches_snapshot_binding": binding_ok,
            "run_err_all_empty": err_sizes,
            "run_err_all_empty_verified": run_err_ok,
            "merged_tables_match_summary_hashes": merged_ok,
            "merged_rows_expected": rows_ok,
        },
        "snapshot_vs_live": live_drift,
        "merged_tables": merged,
        "files": records,
        "notes": [
            "复算输入 = 本证据包 + 已入库的 outputs/tables/ 两张合并表"
            "（per_rep / policy_grid）；逐用户帧不进证据目录。",
            "live repo 在正式运行窗口内有 3 次提交（df66a3c / 06d4740 / f2c6dab），"
            "均未进入快照；snapshot_vs_live 记录当前 live 与快照的差异，"
            "用来证明执行路径是快照而不是 live。",
            "run.err 为空只证明进程无 stderr，不构成源码只读证明；"
            "源码只读由 83/83 快照哈希与 combined_sha256 证明。",
        ],
    }
    TARGET.mkdir(parents=True, exist_ok=True)
    coverage_path = TARGET / "coverage.json"
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[D03 evidence] wrote {coverage_path.relative_to(ROOT).as_posix()}")
    print(json.dumps({
        "files": len(records),
        "merged": merged,
        "config_hash": sorted(config_hashes)[0],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
