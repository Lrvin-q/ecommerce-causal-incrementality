"""Phase D 整改第 4 项：按 C 清单重放四代表库与跨层 matrix 作业（第三种做法）。

合成数据 / 已知 DGP。维护时间：2026-10-25 14:33（北京时间）。

这个脚本回答什么问题
--------------------
D.4 把 ``run_sql_pipeline`` 的装载器换成 ``load_facts_fast`` 之后，**C 阶段冻结的
3015 个产物在新指纹下不再通过 ``sql_sha256`` 读取守卫**。评审裁决：不必重跑 C 的
101 个作业，但必须用当前源码按 C manifest 记录的 ``run_id`` / ``stream_prefix`` /
``rep_id`` 重放**代表库与跨层 matrix 作业**，证明 ``observed.sqlite`` 字节相同、
parquet 的 ``dataframe_sha256`` 相同，并把重放结果绑定到新指纹。

为什么必须复用 C 的 ``run_id``
------------------------------
``run_id`` 是观测表里的一列（``ANALYSIS_COLUMNS`` 第一列），也写进每一张 parquet。
换一个 ``run_id`` 重放，数据必然不同——那是比对设计错误，不是装载差异（教训见
``docs/v3_phase_D_loader_switch.md`` §3.2）。因此本脚本**只读** C manifest 里的
``run_id`` / ``stream_prefix`` / ``rep_id`` / ``n``，不改写。

源码快照（应对并发写盘）
------------------------
``pipeline_source_hashes()`` 与 ``sql_source_hash()`` 都会哈希 ``src/causal_growth/**/v3*.py``
等文件；其他代理在我跑重放的 20 分钟里写任何一个 ``v3*.py``，``build_observed_pipeline``
的"运行前后源码不变"门禁都会判伪。本脚本因此支持 ``--source-root``：把 ``src/``、``sql/``、
``configs/`` 字节复制到 ``out/`` 下做**不可变快照**，用快照跑重放；并且要求
快照与仓库当前字节**逐文件相同**（否则拒绝执行）。等价于"在无并发写盘窗口里跑"，
但不牺牲溯源：快照哈希表原样记录在 summary.json 里。

用法
----
    # 1) 做快照（字节复制；可用 robocopy / Copy-Item）
    # 2) 串行重放（最多一个进程，避免与 4 个正式 AA 作业抢 CPU）
    python scripts/15_replay_c_representatives.py --source-root out/d4_replay_snapshot/<stamp>

    # 工作树被切走（或与快照不同）时，把快照钉在某个提交上做溯源比对
    python scripts/15_replay_c_representatives.py --source-root out/<snap> --expect-source-commit <rev>

    # 只跑 4 个代表库 / 只跑某个作业 / 只列清单不重放
    python scripts/15_replay_c_representatives.py --categories representative
    python scripts/15_replay_c_representatives.py --jobs representative__L0_P_main
    python scripts/15_replay_c_representatives.py --dry-run

    # 单个作业因 Windows 文件锁失败后：只重放它，并把它并回既有 CSV/summary
    python scripts/15_replay_c_representatives.py --jobs representative__L1_main --merge-existing

    # 判定逻辑变了但重放产物没变：只重算比对（秒级，不重跑流水线）
    python scripts/15_replay_c_representatives.py --compare-only

输出
----
- ``outputs/tables/v3_phase_D_c_replay.csv``：逐文件比对明细（每行一个产物）；
- ``outputs/v3/phase_d_c_replay/summary.json``：逐作业汇总 + 新指纹绑定 + 源码快照哈希表；
- ``data/v3/phase_d_replay/<job_id>/<attempt>/``：重放产物本身（含新 manifest）。

判定口径（三档，互不混淆）
--------------------------
- ``identical``：字节相同；
- ``identical_content``：parquet 字节不同，但 ``dataframe_sha256`` 相同、且 footer 里除
  ``pandas.attributes.source_path`` 外**没有任何元数据差异**（落库作业必然如此，因为路径变了）；
- ``expected_drift``：``lineage/source_hashes_after.json``，它记录生产时源码表，按设计不同。

只有 ``DIFFERS`` / ``MISSING`` 会判失败；``identical_content`` 与 ``expected_drift``
都会在 CSV 的 ``verdict``/``note`` 列里显式标注，不做静默归类。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable, Sequence

# One core per replay process: four formal AA jobs are already using four cores.
for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_variable] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

REPO_ROOT = Path(__file__).resolve().parents[1]

#: C 清单里要重放的作业：四个代表库 + 三个跨层 history matrix + 一个 validation matrix。
DEFAULT_JOBS: tuple[str, ...] = (
    "representative__L0_P_main",
    "representative__L1_main",
    "representative__L2_n200000_p050",
    "representative__L3_fixed_lt000",
    "matrix__L1_main",
    "matrix__L2_n200000_p050",
    "matrix__L3_fixed_lt000",
    "matrix_validation__L1_main",
)

#: 允许的字节差异之一：这是"源码哈希表"产物，绑定的是**生产时的**源码快照。
#: 重放绑定的是新指纹，所以它按设计不同（C 34 个 key → D 40 个 key）。
EXPECTED_DRIFT: frozenset[str] = frozenset({"lineage/source_hashes_after.json"})

#: 允许的字节差异之二：**落库作业**的 parquet footer 里 pandas ``attrs["source_path"]``
#: 记录本 run 的 ``observed.sqlite`` 绝对路径。重放写到另一个目录，因此该字段必然不同；
#: 内容等价由 ``dataframe_sha256``（以及 footer 里其余全部元数据）证明。矩阵作业不落库时
#: 该字段是常量 ``<cwd>/data/v3/in_memory_sql``，所以它们的 parquet 逐字节相同。

#: 新绑定的 SQL 语义指纹（D.4 切换后）。C 阶段为 18fe1968…。
NEW_SQL_SHA256_PREFIX = "4cbf830621ac7ed4"
C_SQL_SHA256_PREFIX = "18fe196809535533"

#: CSV 列顺序逐文件证据（一行一个产物）。
CSV_COLUMNS: tuple[str, ...] = (
    "level", "job_id", "category", "artifact", "verdict", "note",
    "c_sha256", "replay_sha256", "bytes_equal", "c_bytes", "replay_bytes", "c_file_intact",
    "c_dataframe_sha256", "replay_dataframe_sha256", "dataframe_equal", "metadata_diff",
)

#: parquet footer 里唯一允许不同的字段：pandas ``attrs["source_path"]`` 记录**本 run 的**
#: 观测库绝对路径。重放必然写到另一个目录，所以这个字段按设计不同；矩阵作业不落库时
#: 它取常量 ``<cwd>/data/v3/in_memory_sql``，因此同一矩阵作业的 parquet 是逐字节相同的。
PATH_ATTRIBUTE = "source_path"


def _early_source_root() -> Path:
    """Read ``--source-root`` before importing ``causal_growth`` so imports come from it."""
    tokens = sys.argv[1:]
    for index, token in enumerate(tokens):
        if token == "--source-root" and index + 1 < len(tokens):
            return Path(tokens[index + 1]).resolve()
        if token.startswith("--source-root="):
            return Path(token.split("=", 1)[1]).resolve()
    return REPO_ROOT


SOURCE_ROOT = _early_source_root()
sys.path.insert(0, str(SOURCE_ROOT / "src"))

import pandas as pd  # noqa: E402  (import order is intentional: source root first)
import pyarrow.parquet as pq  # noqa: E402

from causal_growth.data.v3_pipeline import build_observed_pipeline, pipeline_source_hashes  # noqa: E402
from causal_growth.data.v3_preprocessing import FrozenPreprocessor  # noqa: E402
from causal_growth.data.v3_sql import sql_source_hash  # noqa: E402
from causal_growth.data.v3_storage import dataframe_sha256  # noqa: E402
from causal_growth.dgp.v3_engine import generate_v3_population  # noqa: E402
from causal_growth.evaluation.v3_data_checks import engineering_validation_assignment  # noqa: E402
from causal_growth.v3_config import load_v3_protocol  # noqa: E402


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _bound_sources(root: Path) -> dict[str, str]:
    """Reproduce ``pipeline_source_hashes()`` for an arbitrary root (repo or snapshot)."""
    files = sorted(set((root / "src" / "causal_growth").rglob("v3*.py"))
                   | set((root / "sql").glob("v3*.sql"))
                   | set((root / "configs").glob("v3*.yaml"))
                   | set((root / "configs" / "v3").glob("*.yaml")))
    return {path.relative_to(root).as_posix(): _sha256(path) for path in files}


def _is_bound_name(name: str) -> bool:
    """Match the same globs as ``pipeline_source_hashes()`` against a repository path."""
    parts = name.split("/")
    if name.startswith("src/causal_growth/") and name.endswith(".py"):
        return parts[-1].startswith("v3")
    if name.startswith("sql/") and name.endswith(".sql"):
        return parts[-1].startswith("v3")
    if name.startswith("configs/") and name.endswith(".yaml"):
        return parts[-1].startswith("v3") or (len(parts) == 3 and parts[1] == "v3")
    return False


def _commit_bound_sources(commit: str) -> dict[str, str]:
    """Hash the bound files exactly as a git commit records them.

    The working tree cannot always be the reference: a branch switch (or a parallel agent)
    can move it away from the sources that produced a snapshot. Pinning the snapshot to a
    commit keeps the same strength of evidence — every bound file's sha256 must equal the
    blob in that commit — while staying independent of the current checkout.
    """
    listing = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-tree", "-r", "-z", "--name-only", "--full-tree", commit],
                             capture_output=True, check=True).stdout.decode("utf-8")
    hashes: dict[str, str] = {}
    for name in (entry for entry in listing.split("\0") if entry):
        if not _is_bound_name(name):
            continue
        blob = subprocess.run(["git", "-C", str(REPO_ROOT), "cat-file", "blob", f"{commit}:{name}"],
                              capture_output=True, check=True).stdout
        hashes[name] = hashlib.sha256(blob).hexdigest()
    return hashes


def _verify_source_root(expect_commit: str | None = None) -> dict[str, Any]:
    """Refuse a snapshot that is not byte-identical to its declared source state."""
    snapshot_hashes = _bound_sources(SOURCE_ROOT)
    imported = pipeline_source_hashes()
    if expect_commit:
        recorded = _commit_bound_sources(expect_commit)
        drift = sorted(name for name in set(recorded) | set(snapshot_hashes)
                       if recorded.get(name) != snapshot_hashes.get(name))
        if drift:
            raise SystemExit(f"source snapshot differs from commit {expect_commit}: {drift}")
        mode = f"snapshot_vs_commit:{expect_commit}"
    elif SOURCE_ROOT == REPO_ROOT:
        mode = "repo"
    else:
        repo_hashes = _bound_sources(REPO_ROOT)
        drift = sorted(name for name in set(repo_hashes) | set(snapshot_hashes)
                       if repo_hashes.get(name) != snapshot_hashes.get(name))
        if drift:
            raise SystemExit(f"source snapshot differs from the repository: {drift}")
        mode = "snapshot_verified_identical"
    if imported != snapshot_hashes:
        raise SystemExit("imported causal_growth does not match the requested source root")
    return {"mode": mode, "source_root": str(SOURCE_ROOT), "file_count": len(snapshot_hashes),
            "files": snapshot_hashes,
            "set_sha256": hashlib.sha256(json.dumps(snapshot_hashes, sort_keys=True).encode("utf-8")).hexdigest()}


def _resolve_c_attempt(explicit: str | None) -> Path:
    """Find the Phase C attempt directory (default: newest passed ``--scope all``)."""
    root = REPO_ROOT / "outputs" / "v3" / "data_validation"
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_absolute():
            candidate = root / explicit if (root / explicit).exists() else Path(explicit).resolve()
        if not (candidate / "manifest.json").is_file():
            raise SystemExit(f"not a Phase C attempt directory: {candidate}")
        return candidate
    passed = []
    for path in sorted(root.glob("phase_c_*")):
        manifest = _read_json(path / "manifest.json")
        if manifest.get("status") == "passed" and manifest.get("scope") == "all":
            passed.append(path)
    if not passed:
        raise SystemExit("no passed '--scope all' Phase C attempt found")
    return passed[-1]


def _job_plan(attempt: Path, wanted: Sequence[str], categories: Iterable[str] | None,
              include_validation: bool) -> list[dict[str, Any]]:
    """Read each C receipt and keep only jobs that really ran and passed."""
    allowed = set(categories) if categories else None
    plan: list[dict[str, Any]] = []
    for job_id in wanted:
        receipt_path = attempt / "jobs" / f"{job_id}.json"
        if not receipt_path.is_file():
            raise SystemExit(f"C receipt missing: {receipt_path}")
        receipt = _read_json(receipt_path)
        job = receipt["binding"]["job"]
        if allowed is not None and job["category"] not in allowed:
            continue
        if job["category"] != "power_contract" and job["population_kind"] == "validation" and not include_validation:
            continue
        if receipt.get("status") != "passed":
            raise SystemExit(f"C receipt is not passed: {job_id} ({receipt.get('status')})")
        manifest_path = Path(receipt["summary"]["pipeline_manifest"])
        manifest = _read_json(manifest_path)
        plan.append({"job_id": job_id, "receipt": receipt, "job": job,
                     "c_manifest_path": manifest_path, "c_manifest": manifest,
                     "c_directory": manifest_path.parent})
    return plan


def _check_binding(plan_entry: dict[str, Any]) -> None:
    """The receipt's declared job and the produced manifest must agree."""
    job, manifest = plan_entry["job"], plan_entry["c_manifest"]
    checks = {
        "n_actual": (manifest["n_actual"], job["n"]),
        "population_kind": (manifest["population_kind"], job["population_kind"]),
        "database_persisted": (manifest["database_persisted"], job["persist_database"]),
    }
    for name, (left, right) in checks.items():
        if left != right:
            raise SystemExit(f"{plan_entry['job_id']}: C receipt/manifest disagree on {name}: {left} != {right}")
    if manifest.get("sql_sha256", "")[:16] != C_SQL_SHA256_PREFIX:
        raise SystemExit(f"{plan_entry['job_id']}: unexpected C sql_sha256 {manifest.get('sql_sha256')!r}")


def _frozen_preprocessor_for(attempt: Path, plan_entry: dict[str, Any]) -> FrozenPreprocessor | None:
    """Validation jobs consume the frozen transform fitted by their historical job."""
    historical_id = plan_entry["job"].get("historical_job_id")
    if not historical_id:
        return None
    receipt = _read_json(attempt / "jobs" / f"{historical_id}.json")
    directory = Path(receipt["summary"]["pipeline_manifest"]).parent
    return FrozenPreprocessor.from_dict(_read_json(directory / "preprocessing" / "state.json"))


def _replay_one(plan_entry: dict[str, Any], attempt: Path, replay_root: Path, stamp: str) -> dict[str, Any]:
    """Rerun one C job from its recorded identity and return the job-level record."""
    cfg = load_v3_protocol().scenario(plan_entry["job"]["scenario_id"])
    manifest = plan_entry["c_manifest"]
    run_id, stream_prefix = str(manifest["run_id"]), str(manifest["stream_prefix"])
    rep_id, n = int(manifest["rep_id"]), int(manifest["n_actual"])
    population_kind = str(manifest["population_kind"])
    validation_rows = engineering_validation_assignment(cfg, n=n, rep_id=rep_id) if population_kind == "validation" else None
    frozen = _frozen_preprocessor_for(attempt, plan_entry)
    started = time.perf_counter()
    population = generate_v3_population(cfg, rep_id, n, population_kind=population_kind,
                                        validation_assignment=validation_rows)
    if population.metadata["stream_prefix"] != stream_prefix:
        raise SystemExit(f"{plan_entry['job_id']}: stream_prefix mismatch {population.metadata['stream_prefix']} != {stream_prefix}")
    directory = replay_root / plan_entry["job_id"] / stamp
    result = build_observed_pipeline(*population.observation_bundle(), cfg, directory=directory, run_id=run_id,
                                     rep_id=rep_id, stream_prefix=stream_prefix, population_kind=population_kind,
                                     persist_database=bool(manifest["database_persisted"]),
                                     frozen_preprocessor=frozen)
    elapsed = time.perf_counter() - started
    del population
    gc.collect()
    return {"manifest_path": result.manifest_path, "elapsed_seconds": elapsed, "run_id": run_id,
            "stream_prefix": stream_prefix, "rep_id": rep_id, "n": n, "population_kind": population_kind}


def _pandas_metadata_without_path(raw: bytes) -> dict[str, Any]:
    """Pandas footer metadata with the recorded run path dropped."""
    parsed = json.loads(raw.decode("utf-8"))
    parsed["attributes"] = {name: value for name, value in (parsed.get("attributes") or {}).items()
                            if name != PATH_ATTRIBUTE}
    return parsed


def _schema_signature(path: Path) -> tuple[Any, ...]:
    """Parsed Arrow schema signature: fields, field metadata and pandas metadata.

    ``pyarrow`` stores the pandas metadata twice — as the file-level ``pandas`` key and
    inside the serialised ``ARROW:schema`` blob. Comparing that blob byte for byte would
    therefore flag the recorded run path twice; parsing it and normalising the pandas
    ``attributes`` compares what actually matters: field names, types, nullability and
    every other attribute.
    """
    schema = pq.read_schema(path)
    metadata = dict(schema.metadata or {})
    pandas_raw = metadata.pop(b"pandas", None)
    fields = tuple((field.name, str(field.type), bool(field.nullable)) for field in schema)
    extra = {key.decode("utf-8", "replace"): value for key, value in metadata.items()}
    return fields, extra, _pandas_metadata_without_path(pandas_raw) if pandas_raw else None


def _parquet_metadata_difference(c_path: Path, r_path: Path) -> list[str]:
    """Metadata differences that are *not* the recorded run path.

    The pandas metadata of an observed frame embeds ``attrs`` (pandas 3 writes them into
    the parquet footer through ``pyarrow``). ``attrs["source_path"]`` is the absolute path
    of the run's own ``observed.sqlite``, so a replay into a different directory always
    changes it. Everything else — column schema, dtypes, ``observed_dataset_hash``,
    ``config_hash``, ``artifact_role`` — must match, and this function proves that rather
    than assuming it.
    """
    left = dict(pq.read_metadata(c_path).metadata or {})
    right = dict(pq.read_metadata(r_path).metadata or {})
    differences: list[str] = []
    for key in sorted(set(left) | set(right)):
        if key in (b"pandas", b"ARROW:schema"):
            continue  # compared semantically below
        if left.get(key) != right.get(key):
            differences.append(key.decode("utf-8", "replace"))
    if left.get(b"pandas") and right.get(b"pandas"):
        if _pandas_metadata_without_path(left[b"pandas"]) != _pandas_metadata_without_path(right[b"pandas"]):
            differences.append("pandas")
    if _schema_signature(c_path) != _schema_signature(r_path):
        differences.append("ARROW:schema")
    return differences


def _compare(plan_entry: dict[str, Any], replay: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare every artifact the C manifest recorded against the replayed file."""
    c_manifest, c_directory = plan_entry["c_manifest"], plan_entry["c_directory"]
    replay_directory = replay["manifest_path"].parent
    replay_manifest = _read_json(replay["manifest_path"])
    c_artifacts, r_artifacts = c_manifest["artifacts"], replay_manifest["artifacts"]
    rows: list[dict[str, Any]] = []
    for relative in sorted(set(c_artifacts) | set(r_artifacts)):
        expected, actual = c_artifacts.get(relative), r_artifacts.get(relative)
        c_path, r_path = c_directory / relative, replay_directory / relative
        row: dict[str, Any] = {
            "level": "artifact", "job_id": plan_entry["job_id"], "category": plan_entry["job"]["category"],
            "artifact": relative, "c_sha256": "", "replay_sha256": "", "bytes_equal": "",
            "c_dataframe_sha256": "", "replay_dataframe_sha256": "", "dataframe_equal": "",
            "metadata_diff": "", "c_bytes": c_path.stat().st_size if c_path.is_file() else "",
            "replay_bytes": "", "c_file_intact": "", "verdict": "", "note": "",
        }
        if expected is None or actual is None:
            row.update(verdict="MISSING", note="产物只在一侧存在")
            rows.append(row)
            continue
        row["c_sha256"], row["replay_sha256"] = expected["sha256"], actual["sha256"]
        row["c_file_intact"] = _sha256(c_path) == expected["sha256"] if c_path.is_file() else "missing"
        row["replay_bytes"] = r_path.stat().st_size if r_path.is_file() else ""
        row["bytes_equal"] = row["replay_sha256"] == row["c_sha256"]
        if relative.endswith(".parquet"):
            recorded = expected["dataframe_sha256"]
            row["c_dataframe_sha256"], row["replay_dataframe_sha256"] = recorded, actual["dataframe_sha256"]
            recomputed = dataframe_sha256(pd.read_parquet(r_path)) if r_path.is_file() else "missing"
            row["dataframe_equal"] = recomputed == recorded
            metadata_diff = _parquet_metadata_difference(c_path, r_path) if c_path.is_file() and r_path.is_file() else ["missing"]
            row["metadata_diff"] = ";".join(metadata_diff)
        if relative in EXPECTED_DRIFT:
            row["verdict"] = "expected_drift"
            row["note"] = "源码哈希表绑定生产时源码，重放必然绑定新指纹"
        elif row["bytes_equal"]:
            row["verdict"] = "identical"
        elif (relative.endswith(".parquet") and row["dataframe_equal"] is True
              and not row["metadata_diff"]):
            row["verdict"] = "identical_content"
            row["note"] = f"parquet footer 仅差 pandas attributes.{PATH_ATTRIBUTE}（本 run 观测库绝对路径）"
        else:
            row["verdict"] = "DIFFERS"
        rows.append(row)
    return rows


def _write_csv(rows: Sequence[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(list(rows), columns=list(CSV_COLUMNS))
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def _counts(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Count verdicts; ``identical_content`` is a pass, ``DIFFERS``/``MISSING`` are not."""
    return {verdict: sum(row["verdict"] == verdict for row in rows)
            for verdict in ("identical", "identical_content", "expected_drift", "DIFFERS", "MISSING")}


def _job_verdict(record: dict[str, Any], counts: dict[str, int]) -> str:
    passed = (record.get("status") == "passed" and record.get("c_files_intact")
              and not counts["DIFFERS"] and not counts["MISSING"])
    return "passed" if passed else "failed"


def _load_previous(csv_path: Path, summary_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the existing evidence *before* this invocation overwrites it.

    Values are read back as strings so a re-write does not reformat numbers.
    """
    rows: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    if csv_path.is_file():
        rows = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False).to_dict("records")
    if summary_path.is_file():
        jobs = list(_read_json(summary_path).get("jobs", []))
    return rows, jobs


def _merge_previous(previous_rows: Sequence[dict[str, Any]], previous_jobs: Sequence[dict[str, Any]],
                    rows: list[dict[str, Any]], jobs: list[dict[str, Any]], plan_ids: set[str],
                    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep the evidence of jobs that this invocation did not re-run."""
    kept_rows = [row for row in previous_rows if row["job_id"] not in plan_ids]
    kept_jobs = [job for job in previous_jobs if job["job_id"] not in plan_ids]
    return [*kept_rows, *rows], [*kept_jobs, *jobs]


def _finalize(rows: list[dict[str, Any]], jobs: list[dict[str, Any]], summary: dict[str, Any],
              args: argparse.Namespace) -> None:
    """Recompute the totals from the rows and write the two deliverables."""
    summary["jobs"] = jobs
    summary["artifact_rows"] = len(rows)
    counts = _counts(rows)
    summary["identical"] = counts["identical"]
    summary["identical_content"] = counts["identical_content"]
    summary["expected_drift"] = counts["expected_drift"]
    summary["mismatched"] = counts["DIFFERS"] + counts["MISSING"]
    summary["verdict"] = ("passed" if summary["mismatched"] == 0 and jobs
                          and all(job["verdict"] == "passed" for job in jobs) else "failed")
    summary["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_csv(rows, args.csv)
    _write_json(args.summary, summary)
    print(f"verdict: {summary['verdict']} | identical={summary['identical']} "
          f"identical_content={summary['identical_content']} expected_drift={summary['expected_drift']} "
          f"mismatched={summary['mismatched']}", flush=True)
    print(f"csv    : {args.csv}", flush=True)
    print(f"summary: {args.summary}", flush=True)


def _resolve_replay_manifest(entry: dict[str, Any], replay_root: Path,
                             recorded: dict[str, dict[str, Any]]) -> tuple[Path, str]:
    """Find the replay manifest for one job: summary record first, then on disk.

    Disk discovery exists because a job can fail *after* writing its artifacts (a Windows
    file lock on ``manifest.json`` aborted one 200 s replay). A later re-run of that single
    job leaves a fresh passed manifest next to the failed one; matching ``run_id`` and
    ``status == passed`` makes the choice unambiguous and it is recorded either way.
    """
    record = recorded.get(entry["job_id"])
    if record and record.get("replay_manifest") and Path(record["replay_manifest"]).is_file():
        return Path(record["replay_manifest"]), "summary_record"
    expected = str(entry["c_manifest"]["run_id"])
    candidates = []
    for manifest_path in sorted((replay_root / entry["job_id"]).glob("*/manifest.json")):
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError):
            continue
        if manifest.get("status") == "passed" and manifest.get("run_id") == expected:
            candidates.append(manifest_path)
    if not candidates:
        raise SystemExit(f"{entry['job_id']}: no passed replay manifest found under {replay_root / entry['job_id']}")
    return max(candidates, key=lambda path: path.stat().st_mtime), "discovered_on_disk"


def _compare_only(plan: list[dict[str, Any]], args: argparse.Namespace, summary: dict[str, Any]) -> int:
    """Re-run the comparison against replay artifacts already on disk (no replay).

    Used after the verdict logic itself changes: the replay artifacts are immutable and
    each job's manifest hash is recorded, so re-deriving the comparison is honest and
    costs seconds instead of another twenty minutes of competing CPU.
    """
    previous = _read_json(args.summary)
    if previous.get("source_root", {}).get("set_sha256") != summary["source_root"]["set_sha256"]:
        raise SystemExit("existing summary was produced from a different source set")
    if previous.get("new_sql_sha256") != summary["new_sql_sha256"]:
        raise SystemExit("existing summary was produced under a different sql_source_hash")
    recorded = {job["job_id"]: job for job in previous.get("jobs", [])}
    rows: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    for entry in plan:
        manifest_path, source = _resolve_replay_manifest(entry, args.replay_root, recorded)
        if not manifest_path.is_file():
            raise SystemExit(f"{entry['job_id']}: replay manifest missing: {manifest_path}")
        artifact_rows = _compare(entry, {"manifest_path": manifest_path})
        counts = _counts(artifact_rows)
        record = {**recorded.get(entry["job_id"], {}), "job_id": entry["job_id"],
                  "category": entry["job"]["category"], "status": "passed",
                  "run_id": str(entry["c_manifest"]["run_id"]),
                  "stream_prefix": str(entry["c_manifest"]["stream_prefix"]),
                  "rep_id": int(entry["c_manifest"]["rep_id"]),
                  "n": int(entry["c_manifest"]["n_actual"]),
                  "population_kind": str(entry["c_manifest"]["population_kind"]),
                  "replay_manifest": str(manifest_path), "replay_source": source,
                  "replay_manifest_sha256": _sha256(manifest_path),
                  "artifacts": len(artifact_rows), **counts,
                  "c_files_intact": bool(artifact_rows) and all(row["c_file_intact"] is True for row in artifact_rows)}
        record["verdict"] = _job_verdict(record, counts)
        rows.extend(artifact_rows)
        jobs.append(record)
        print(f"[{entry['job_id']}] {record['verdict']} ({source}) identical={counts['identical']} "
              f"identical_content={counts['identical_content']} expected_drift={counts['expected_drift']} "
              f"differs={counts['DIFFERS']} missing={counts['MISSING']}", flush=True)
    merged = {**previous,
              "compare": {"mode": "compare_only", "script_sha256": _sha256(Path(__file__).resolve()),
                          "at_utc": datetime.now(timezone.utc).isoformat(),
                          "note": "比对重算；重放产物未改动，manifest 哈希见各 job 记录"},
              "source_root": summary["source_root"], "new_sql_sha256": summary["new_sql_sha256"]}
    _finalize(rows, jobs, merged, args)
    return 0 if merged["verdict"] == "passed" else 1


def main() -> int:
    """Replay the requested C jobs and write the comparison evidence."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--c-attempt", help="Phase C attempt directory (default: newest passed '--scope all')")
    parser.add_argument("--jobs", nargs="+", default=list(DEFAULT_JOBS), help="C job IDs to replay")
    parser.add_argument("--categories", nargs="+", choices=["representative", "matrix", "matrix_validation"],
                        help="Restrict to these receipt categories")
    parser.add_argument("--skip-validation", action="store_true", help="Skip the independent-validation matrix job")
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT,
                        help="Byte-identical source snapshot to run from (default: this repository)")
    parser.add_argument("--expect-source-commit",
                        help="Verify the snapshot against this git commit instead of the working tree")
    parser.add_argument("--replay-root", type=Path, default=REPO_ROOT / "data/v3/phase_d_replay")
    parser.add_argument("--csv", type=Path, default=REPO_ROOT / "outputs/tables/v3_phase_D_c_replay.csv")
    parser.add_argument("--summary", type=Path, default=REPO_ROOT / "outputs/v3/phase_d_c_replay/summary.json")
    parser.add_argument("--dry-run", action="store_true", help="List the plan without replaying")
    parser.add_argument("--compare-only", action="store_true",
                        help="Re-derive the comparison from recorded replay manifests; does not replay")
    parser.add_argument("--merge-existing", action="store_true",
                        help="Keep other jobs' rows when replaying a subset into the same CSV/summary")
    args = parser.parse_args()

    sources = _verify_source_root(args.expect_source_commit)
    attempt = _resolve_c_attempt(args.c_attempt)
    sql_hash = sql_source_hash()
    if not sql_hash.startswith(NEW_SQL_SHA256_PREFIX):
        raise SystemExit(f"unexpected current sql_source_hash: {sql_hash}")
    plan = _job_plan(attempt, args.jobs, args.categories, include_validation=not args.skip_validation)
    if not plan:
        raise SystemExit("no job selected")
    for entry in plan:
        _check_binding(entry)

    stamp = f"d4_replay_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_pid{os.getpid()}"
    protocol = load_v3_protocol()
    summary: dict[str, Any] = {
        "source_label": "合成数据 / 已知 DGP",
        "purpose": "Phase D.4 loader switch: replay C representatives under the new sql_source_hash",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "script_sha256": _sha256(Path(__file__).resolve()),
        "python_version": sys.version.split()[0],
        "c_attempt": str(attempt),
        "c_attempt_manifest_sha256": _sha256(attempt / "manifest.json"),
        "c_sql_sha256": plan[0]["c_manifest"]["sql_sha256"],
        "new_sql_sha256": sql_hash,
        "protocol_hash": protocol.config_hash,
        "data_config_hash": plan[0]["c_manifest"]["data_config_hash"],
        "source_root": sources,
        "replay_stamp": stamp,
        "jobs": [],
        "artifact_rows": 0,
        "identical": 0,
        "identical_content": 0,
        "expected_drift": 0,
        "mismatched": 0,
        "formal_repetitions_completed": 0,
    }
    print(f"Phase C attempt : {attempt.name}", flush=True)
    print(f"source root     : {sources['mode']} ({sources['file_count']} files)", flush=True)
    print(f"new sql sha256  : {sql_hash}", flush=True)
    print(f"jobs            : {[entry['job_id'] for entry in plan]}", flush=True)
    if args.dry_run:
        for entry in plan:
            manifest = entry["c_manifest"]
            print(f"  {entry['job_id']:44s} n={manifest['n_actual']:>7d} rep={manifest['rep_id']} "
                  f"db={manifest['database_persisted']} run_id={manifest['run_id']}", flush=True)
        # No file is written: a dry run must never overwrite the recorded evidence.
        print("dry run: nothing written", flush=True)
        return 0

    rows: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    plan_ids = {entry["job_id"] for entry in plan}
    if args.compare_only:
        return _compare_only(plan, args, summary)
    previous_rows, previous_jobs = _load_previous(args.csv, args.summary) if args.merge_existing else ([], [])

    for entry in plan:
        print(f"[{entry['job_id']}] replaying …", flush=True)
        job_record: dict[str, Any] = {"job_id": entry["job_id"], "category": entry["job"]["category"]}
        try:
            replay = _replay_one(entry, attempt, args.replay_root, stamp)
            job_record.update({"status": "passed", "replay_manifest": str(replay["manifest_path"]),
                               "replay_manifest_sha256": _sha256(replay["manifest_path"]),
                               "run_id": replay["run_id"], "stream_prefix": replay["stream_prefix"],
                               "rep_id": replay["rep_id"], "n": replay["n"],
                               "population_kind": replay["population_kind"],
                               "elapsed_seconds": round(replay["elapsed_seconds"], 3)})
            artifact_rows = _compare(entry, replay)
        except Exception as exc:  # a failed replay is evidence, never a silent skip
            job_record.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            artifact_rows = []
            print(f"[{entry['job_id']}] FAILED: {type(exc).__name__}: {exc}", flush=True)
        counts = _counts(artifact_rows)
        job_record.update({"artifacts": len(artifact_rows), **counts})
        job_record["c_files_intact"] = bool(artifact_rows) and all(row["c_file_intact"] is True for row in artifact_rows)
        job_record["verdict"] = _job_verdict(job_record, counts)
        jobs.append(job_record)
        rows.extend(artifact_rows)
        print(f"[{entry['job_id']}] {job_record['verdict']} in {job_record.get('elapsed_seconds')}s "
              f"identical={counts['identical']} identical_content={counts['identical_content']} "
              f"expected_drift={counts['expected_drift']} differs={counts['DIFFERS']} missing={counts['MISSING']}",
              flush=True)
        summary["jobs"] = list(jobs)
        _write_csv(rows, args.csv)
        _write_json(args.summary, summary)

    if args.merge_existing:
        rows, jobs = _merge_previous(previous_rows, previous_jobs, rows, jobs, plan_ids)
        if len(jobs) > len(plan):
            summary["merged_previous_jobs"] = sorted({job["job_id"] for job in jobs} - plan_ids)
            summary["merged_note"] = ("部分作业的重放产物来自更早的 stamp；每个作业的实际产出自 "
                                      "jobs[].replay_manifest 路径可见")
    summary["pipeline_source_hashes"] = pipeline_source_hashes()
    _finalize(rows, jobs, summary, args)
    return 0 if summary["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
