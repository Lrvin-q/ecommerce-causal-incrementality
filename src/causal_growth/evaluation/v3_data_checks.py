"""Phase C engineering evidence from actual five-table/SQL executions.

Synthetic / known DGP. This outer audit harness may read the independent B
ledger; the production observed pipeline cannot. Engineering runs never count
as formal repetitions or as a learned-policy randomized validation in Phase F.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sqlite3
import time
import traceback
from typing import Any, Iterator, Sequence

import numpy as np
import pandas as pd

from causal_growth.config import Config
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_pipeline import DataPipelineResult, build_observed_pipeline, pipeline_source_hashes
from causal_growth.data.v3_preprocessing import FrozenPreprocessor
from causal_growth.data.v3_split import user_key_hash
from causal_growth.data.v3_sql import CENT_COLUMNS
from causal_growth.data.v3_storage import RunArtifactWriter, dataframe_sha256, file_sha256
from causal_growth.dgp.v3_covariates import generate_covariates
from causal_growth.dgp.v3_archive import archive_sealed_population
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.dgp.v3_ledger import audit_window_ledger
from causal_growth.rng import child_rng
from causal_growth.v3_config import V3Protocol, load_v3_protocol
from causal_growth.v3_data_config import load_v3_data_config


@dataclass(frozen=True)
class DataCheckJob:
    """One explicitly sized engineering execution or one design-only contract."""

    job_id: str
    scenario_id: str
    category: str
    n: int
    population_kind: str = "history"
    persist_database: bool = False
    historical_job_id: str | None = None


class DataCheckFailure(AssertionError):
    """An engineering invariant failed; the caller retains the failed attempt."""


class ActiveValidationError(RuntimeError):
    """An overlapping live or unverifiable process prevents a new attempt."""


def process_identity(pid: int) -> dict[str, Any] | None:
    """Query a real process and its creation identity without signaling it.

    None means verified exit, not access denied. Windows creation FILETIME
    distinguishes a reused PID from the process registered in an old manifest.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ActiveValidationError("cannot verify an invalid recorded PID")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        query_limited_information = 0x1000
        error_invalid_parameter, still_active = 87, 259
        handle = kernel.OpenProcess(query_limited_information, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == error_invalid_parameter:
                return None
            raise ActiveValidationError(f"cannot inspect PID {pid}: Windows error {error}; refusing uncertain ownership")
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                raise ActiveValidationError(f"cannot query exit state of PID {pid}: Windows error {ctypes.get_last_error()}")
            if exit_code.value != still_active:
                return None
            created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                          ctypes.byref(kernel_time), ctypes.byref(user_time)):
                raise ActiveValidationError(f"cannot query creation identity of PID {pid}: Windows error {ctypes.get_last_error()}")
            stamp = (created.dwHighDateTime << 32) | created.dwLowDateTime
            return {"pid": pid, "kind": "windows_creation_filetime_100ns", "created": str(stamp)}
        finally:
            kernel.CloseHandle(handle)
    if os.name == "posix" and Path("/proc").is_dir():
        try:
            content = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            fields = content[content.rfind(")") + 1:].split()
            if fields[0] in {"Z", "X"}:
                return None
            boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
            return {"pid": pid, "kind": "linux_boot_and_start_ticks", "created": f"{boot}:{fields[19]}"}
        except FileNotFoundError:
            return None
        except (OSError, IndexError) as exc:
            raise ActiveValidationError(f"cannot inspect PID {pid}; refusing uncertain ownership") from exc
    raise ActiveValidationError("this platform has no verified process-identity implementation")


@contextmanager
def _output_registry_lock(output_root: Path) -> Iterator[None]:
    """Hold an OS-released cross-process lock over scan AND attempt registration."""
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / ".registry.lock").open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ActiveValidationError("another process is registering an engineering attempt; retry after registration") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _assert_no_active_overlap(output_root: Path, job_ids: set[str]) -> None:
    """Reject an overlapping live owner; confirmed stale records remain untouched.

    The same job ID is exclusive within one output root even across protocol
    hashes. Different nonoverlapping scopes may execute concurrently.
    """
    for path in sorted(output_root.glob("*/manifest.json")):
        try:
            manifest = _read_json(path)
        except (OSError, ValueError) as exc:
            raise ActiveValidationError(f"cannot inspect existing attempt manifest {path}") from exc
        if manifest.get("status") in {"passed", "failed"}:
            continue
        registered = manifest.get("planned_job_ids")
        if not isinstance(registered, list) or not all(isinstance(value, str) for value in registered):
            raise ActiveValidationError(f"running attempt has unknown job ownership: {path}")
        overlap = job_ids & set(registered)
        if not overlap:
            continue
        actual = process_identity(manifest.get("pid"))
        if actual is None:
            continue
        recorded = manifest.get("process_identity")
        if recorded is None or not isinstance(recorded, dict) or recorded.get("pid") != manifest.get("pid"):
            raise ActiveValidationError(f"live PID with unknown creation identity owns overlapping jobs: {path}")
        if set(recorded) != {"pid", "kind", "created"} or recorded["kind"] != actual["kind"]:
            raise ActiveValidationError(f"cannot compare recorded process creation identity: {path}")
        if (not isinstance(recorded["created"], str) or not recorded["created"]
                or (os.name == "nt" and (not recorded["created"].isdigit() or int(recorded["created"]) <= 0))):
            raise ActiveValidationError(f"invalid recorded process creation identity: {path}")
        if recorded == actual:
            raise ActiveValidationError(f"active PID {actual['pid']} owns overlapping jobs {sorted(overlap)}: {path}")


@dataclass
class CheckRecorder:
    """Accumulate exact, named checks before raising on the first mismatch."""

    job_id: str
    scenario_id: str
    records: list[dict[str, Any]]

    def require(self, name: str, condition: bool, **details: Any) -> None:
        """Record a denominator, ledger, provenance or isolation assertion."""
        row = {"job_id": self.job_id, "scenario_id": self.scenario_id,
               "check": name, "passed": bool(condition), "formal_repetitions_completed": 0,
               "details": json.dumps(details, ensure_ascii=False, sort_keys=True, default=str)}
        self.records.append(row)
        if not condition:
            raise DataCheckFailure(f"{self.job_id}: {name}; {row['details']}")


def plan_data_checks(protocol: V3Protocol, *, scope: str = "smoke",
                     scenario_ids: Sequence[str] | None = None) -> list[DataCheckJob]:
    """Enumerate all required C01/C02 executions without mutating frozen n/R."""
    settings = load_v3_data_config()
    data = protocol.config.to_dict()
    cells = data["scenarios"]
    known = {row["id"] for row in cells}
    selected = set(scenario_ids) if scenario_ids is not None else None
    if selected is not None and (not selected or selected - known):
        raise ValueError("scenario filter must contain registered full scenario IDs")
    if scope not in {"smoke", "matrix", "representatives", "validation", "power", "all"}:
        raise ValueError("unknown engineering scope")
    core = [row for row in cells if "core" in row["roles"]]
    jobs: list[DataCheckJob] = []

    def add_history(row: dict, category: str, n: int, database: bool = False) -> str:
        job_id = f"{category}__{row['id']}"
        if not any(job.job_id == job_id for job in jobs):
            jobs.append(DataCheckJob(job_id, row["id"], category, n, persist_database=database))
        return job_id

    if scope in {"smoke", "matrix", "all"}:
        candidates = core if scope == "smoke" and selected is None else cells
        for row in candidates:
            if selected is None or row["id"] in selected:
                add_history(row, "smoke" if scope == "smoke" else "matrix",
                            int(settings.require("validation.smoke_n" if scope == "smoke" else "validation.per_scenario_n")))
    if scope in {"representatives", "all"}:
        for row in core:
            if selected is None or row["id"] in selected:
                add_history(row, "representative", int(settings.require("validation.representative_n")), True)
    if scope in {"smoke", "validation", "all"}:
        for row in core:
            if selected is not None and row["id"] not in selected:
                continue
            category = "smoke" if scope == "smoke" else "matrix"
            history_id = add_history(row, category, int(settings.require(
                "validation.smoke_n" if scope == "smoke" else "validation.per_scenario_n")))
            jobs.append(DataCheckJob(f"{category}_validation__{row['id']}", row["id"],
                                     f"{category}_validation", int(settings.require(
                                         "validation.smoke_n" if scope == "smoke" else "validation.independent_validation_n")),
                                     "validation", historical_job_id=history_id))
    if scope in {"power", "all"}:
        for row in data["design_power_jobs"]:
            if selected is None or row["base_scenario_id"] in selected:
                jobs.append(DataCheckJob(f"power_contract__{row['id']}", row["id"], "power_contract", 0))
    if not jobs:
        raise ValueError("selection contains no jobs in the requested scope")
    return jobs


def data_check_source_hashes() -> dict[str, str]:
    """Bind all execution sources, configuration, SQL and dependency declarations."""
    root = Path(__file__).resolve().parents[3]
    result = pipeline_source_hashes()
    paths = list((root / "src" / "causal_growth").rglob("*.py"))
    paths += [root / "scripts" / "12_validate_v3_data.py", root / "requirements.txt"]
    for path in paths:
        result[path.relative_to(root).as_posix()] = file_sha256(path)
    return dict(sorted(result.items()))


def engineering_validation_assignment(cfg: Config, *, n: int, rep_id: int) -> pd.DataFrame:
    """Randomize engineering arms using the frozen probabilities, without learning a policy.

    Active arms use an explicitly artificial face-bound rule only to exercise
    assignment/order/SQL schemas. This is not Phase F strategy evidence.
    """
    batch = generate_covariates(cfg, rep_id, n, population_kind="validation")
    users = batch.users
    arms = list(cfg.require("evaluation.independent_validation.arms"))
    probabilities = np.asarray(cfg.require("evaluation.independent_validation.arm_probabilities"), dtype=float)
    seed = int(cfg.require("project.master_seed"))
    labels = child_rng(seed, f"{batch.stream_prefix}.engineering.policy_arm", rep_id).choice(arms, n, p=probabilities)
    frame = pd.DataFrame({"user_id": users.user_id, "assigned_policy_arm": labels,
                          "issued_action": np.zeros(n, dtype=np.int64)})
    frame["policy_arm_probability"] = frame.assigned_policy_arm.map(dict(zip(arms, probabilities, strict=True)))
    budget = float(cfg.require("evaluation.independent_validation.primary_budget_cny_per_user"))
    face = float(cfg.require("business.coupon_reference_face"))
    for arm in arms:
        if arm == "no_coupon":
            continue
        indexes = np.flatnonzero(labels == arm)
        recipients = min(len(indexes), int(np.floor(len(indexes) * budget / face)))
        if arm == "random_same_budget":
            chosen = child_rng(seed, f"{batch.stream_prefix}.engineering.random_list", rep_id).permutation(indexes)[:recipients]
        elif arm == "selected_targeted_policy":
            chosen = users.iloc[indexes].sort_values(["is_new", "cart_value", "user_id"], ascending=[False, False, True]).index[:recipients]
        else:
            raise ValueError("engineering placeholder rule is undefined for a new policy arm")
        frame.loc[chosen, "issued_action"] = 1
    return frame


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_artifact_manifest(manifest_path: Path, *, config_hash: str, data_config_hash: str | None) -> bool:
    """Recheck every persisted artifact, not just the existence of a passed flag."""
    manifest = _read_json(manifest_path)
    if (manifest.get("status") != "passed" or manifest.get("config_hash") != config_hash
            or (data_config_hash is not None and manifest.get("data_config_hash") != data_config_hash)
            or manifest.get("formal_repetitions_completed") != 0):
        return False
    for relative, entry in manifest.get("artifacts", {}).items():
        path = (manifest_path.parent / relative).resolve()
        if not path.is_relative_to(manifest_path.parent.resolve()) or not path.is_file() or file_sha256(path) != entry["sha256"]:
            return False
    return bool(manifest.get("artifacts"))


def _window_reference(users: pd.DataFrame, orders: pd.DataFrame, cfg: Config, days: float) -> pd.DataFrame:
    """Extend B's independent ledger with the two separately posted coupon accounts."""
    local = cfg.with_overrides({"windows.profit_days": days, "windows.convert_days": days})
    reference = audit_window_ledger(users, orders, local).set_index("user_id")
    pay = orders.paid_day <= orders.assignment_day + days
    refund = orders.refunded.astype(bool) & (orders.refund_day <= orders.assignment_day + days)
    for name, mask in (("coupon_cost_initial_cent", pay), ("coupon_return_cent", refund)):
        totals = orders.loc[mask].groupby("user_id")[name].sum()
        reference[name] = totals.reindex(reference.index, fill_value=0).astype(np.int64)
    return reference


def check_pipeline_result(users: pd.DataFrame, assignments: pd.DataFrame, factual_orders: pd.DataFrame,
                          cfg: Config, result: DataPipelineResult, *, recorder: CheckRecorder,
                          audit_directory: Path, population_kind: str,
                          expected_preprocessor: FrozenPreprocessor | None = None) -> dict[str, Any]:
    """Answer C01/C02 by comparing actual SQL inputs, each cent and training lineage."""
    settings = load_v3_data_config()
    observed = result.dataset.observations
    manifest = _read_json(result.manifest_path)
    audit_writer = RunArtifactWriter(audit_directory, {
        "purpose": "engineering_independent_ledger_not_policy_audit_release", "config_hash": cfg.hash(64),
        "data_config_hash": settings.hash(64), "observed_manifest": str(result.manifest_path.resolve()),
    }, role="audit")
    try:
        recorder.require("all_artifacts_byte_hashes", verify_artifact_manifest(result.manifest_path,
                         config_hash=cfg.hash(64), data_config_hash=settings.hash(64)))
        recorder.require("all_assigned_users_retained", len(observed) == len(users) == len(assignments)
                         and set(observed.user_id) == set(users.user_id), n_expected=len(users), n_observed=len(observed))
        recorder.require("registered_and_actual_sizes_recorded", manifest["n_registered"] == cfg.require("design.n_total")
                         and manifest["n_actual"] == len(users), n_registered=manifest["n_registered"], n_actual=len(users))
        recorder.require("unique_user_keys", not observed.duplicated(["run_id", "user_id"]).any())
        recorder.require("learning_input_is_sql", result.dataset.lineage.get("producer") == "v3_sql"
                         and dataframe_sha256(observed) == result.sql.analysis_sha256
                         and manifest.get("analysis_producer") == "v3_sql")
        restored = ObservedDataset.from_manifest(result.manifest_path, cfg)
        recorder.require("verified_sql_restore_matches", restored.content_hash == result.dataset.content_hash)
        recorder.require("sql_quality_all_zero", bool(result.sql.quality.violations.eq(0).all()))
        windows = {str(settings.require("sql.convert_window_name")): float(cfg.require("windows.convert_days")),
                   str(settings.require("sql.profit_window_name")): float(cfg.require("windows.profit_days"))}
        outcomes = result.sql.user_outcomes
        recorder.require("two_prespecified_windows_per_user", set(outcomes.window_type) == set(windows)
                         and len(outcomes) == len(users) * len(windows)
                         and outcomes.groupby("user_id").window_type.nunique().eq(len(windows)).all())
        tolerance = int(cfg.require("business.money.profit_identity_tolerance_cent"))
        for name, days in windows.items():
            reference = _window_reference(users, factual_orders, cfg, days)
            audit_writer.write_frame(f"{name}_independent_ledger.parquet", reference.reset_index(), role="audit")
            actual = outcomes.loc[outcomes.window_type == name].set_index("user_id").reindex(reference.index)
            recorder.require(f"{name}:window_days", bool(actual.window_days.eq(days).all()))
            for column in CENT_COLUMNS:
                delta = np.abs(actual[column].to_numpy(dtype=np.int64) - reference[column].to_numpy(dtype=np.int64))
                recorder.require(f"{name}:{column}:independent_B_ledger", bool((delta <= tolerance).all()),
                                 maximum_absolute_error_cent=int(delta.max(initial=0)), tolerance_cent=tolerance)
            for sql_name, audit_name in (("converted", "paid_purchase_7d"), ("refunded", "any_refund_30d"),
                                         ("paid_orders", "paid_orders_30d"), ("refunded_orders", "refunded_orders_30d")):
                recorder.require(f"{name}:{sql_name}:independent_B_ledger",
                                 np.array_equal(actual[sql_name].to_numpy(), reference[audit_name].to_numpy()))
            recorder.require(f"{name}:mature", bool(actual.mature.eq(1).all()
                             and (actual.required_ingestion_day <= actual.asof_day).all()))
        indexed = observed.set_index("user_id")
        reference = _window_reference(users, factual_orders, cfg, float(cfg.require("windows.profit_days")))
        for column in CENT_COLUMNS:
            recorder.require(f"analysis:{column}:profit_window", np.array_equal(
                indexed.reindex(reference.index)[column].to_numpy(), reference[column].to_numpy()))
        group_n = int(result.sql.summaries["groups"].n_total.sum())
        recorder.require("group_denominators_sum_to_all_users", group_n == len(users), grouped_n=group_n)
        pollution_audit = _check_pollution_and_splits(result, cfg, recorder, population_kind, expected_preprocessor)
        if result.sql.database_path is not None:
            with sqlite3.connect(f"file:{result.sql.database_path.as_posix()}?mode=ro", uri=True) as connection:
                actual_n = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                total_profit = connection.execute("SELECT SUM(net_profit_cent) FROM v3_analysis").fetchone()[0]
                foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
            recorder.require("persistent_sqlite_reopens_and_matches", actual_n == len(users)
                             and total_profit == int(observed.net_profit_cent.sum()) and not foreign)
        recorder.require("no_formal_repetitions_claimed", manifest["formal_repetitions_completed"] == 0)
        audit_manifest = audit_writer.finish(passed=True, checks={"all_independent_ledger_checks_passed": True})
    except BaseException as exc:
        audit_writer.finish(passed=False, checks={"formal_repetitions_completed": 0}, error=f"{type(exc).__name__}: {exc}")
        raise
    return {"n_registered": cfg.require("design.n_total"), "n_actual": len(users), "orders": len(factual_orders), "population_kind": population_kind,
            "database_persisted": result.sql.database_path is not None,
            "pipeline_manifest": str(result.manifest_path.resolve()), "audit_manifest": str(audit_manifest.resolve()),
            "split_counts": observed.split.value_counts().to_dict(),
            "pollution": result.stage_counts["pollution"], "pollution_audit": pollution_audit,
            "repair": result.stage_counts["repair"],
            "formal_repetitions_completed": 0}


def _check_hist_fraud(raw_users: pd.DataFrame, dirty_users: pd.DataFrame, cfg: Config, *,
                      recorder: CheckRecorder, stream_prefix: str, rep_id: int,
                      recorded_selected_count: int) -> dict[str, int]:
    """Replay C01's named anomaly stream and verify selected users and every value."""
    recorder.require("anomaly_user_order_preserved", raw_users[["run_id", "user_id"]].equals(
        dirty_users[["run_id", "user_id"]]))
    selected = (child_rng(int(cfg.require("project.master_seed")), f"{stream_prefix}.dirty.hist_fraud", rep_id)
                .random(len(raw_users)) < float(cfg.require("data.dirty.fraud_user_rate")))
    selected &= bool(cfg.require("data.dirty.enabled"))
    expected = raw_users.hist_gmv.copy(deep=True)
    expected.loc[selected] = expected.loc[selected] * float(cfg.require("data.dirty.fraud_hist_gmv_multiplier"))
    selected_count = int(selected.sum())
    changed_count = int((raw_users.hist_gmv.to_numpy() != dirty_users.hist_gmv.to_numpy()).sum())
    expected_changed_count = int((raw_users.hist_gmv.to_numpy() != expected.to_numpy()).sum())
    details = {"selected_count": selected_count, "changed_count": changed_count,
               "expected_changed_count": expected_changed_count, "recorded_selected_count": recorded_selected_count}
    recorder.require("anomaly_injection_count", selected_count == recorded_selected_count, **details)
    recorder.require("anomaly_values_match_replay", np.array_equal(dirty_users.hist_gmv.to_numpy(), expected.to_numpy()),
                     **details)
    return {"hist_fraud_selected": selected_count, "hist_fraud_changed": changed_count}


def _check_pollution_and_splits(result: DataPipelineResult, cfg: Config, recorder: CheckRecorder,
                                population_kind: str, expected_preprocessor: FrozenPreprocessor | None) -> dict[str, int]:
    directory = result.manifest_path.parent
    manifest = _read_json(result.manifest_path)
    pollution, repair = result.stage_counts["pollution"], result.stage_counts["repair"]
    raw_users = pd.read_parquet(directory / "raw/users.parquet")
    dirty_users = pd.read_parquet(directory / "dirty/users.parquet")
    clean_users = pd.read_parquet(directory / "clean/users.parquet")
    recorder.require("missing_injection_count", int(dirty_users.cart_value_cent.isna().sum()) == pollution["cart_missing_injected"])
    recorder.require("pollution_master_seed_matches_config", manifest["master_seed"] == cfg.require("project.master_seed"))
    pollution_audit = _check_hist_fraud(raw_users, dirty_users, cfg, recorder=recorder,
        stream_prefix=manifest["stream_prefix"], rep_id=manifest["rep_id"],
        recorded_selected_count=pollution["hist_fraud_injected"])
    recorder.require("cleaning_retains_missing_and_users", len(raw_users) == len(dirty_users) == len(clean_users)
                     and int(clean_users.cart_value_cent.isna().sum()) == repair["cart_missing_retained"]
                     and repair["users_removed"] == 0 and repair["refund_orders_removed"] == 0)
    recorder.require("truncated_events_count_recorded", int(raw_users.event_truncated_count.sum()) == pollution["event_truncated"])
    dirty_assignments = pd.read_parquet(directory / "dirty/coupon_assignment.parquet")
    recorder.require("assignment_delay_count", int((dirty_assignments.ingested_day > dirty_assignments.assignment_day).sum())
                     == pollution["assignments_delayed"])
    raw_orders = pd.read_parquet(directory / "raw/orders.parquet").sort_values("order_id").reset_index(drop=True)
    money = [column for column in raw_orders if column.endswith("_cent")]
    for stage in ("dirty", "clean"):
        stage_orders = pd.read_parquet(directory / f"{stage}/orders.parquet").sort_values("order_id").reset_index(drop=True)
        recorder.require(f"{stage}:factual_money_and_refunds_unchanged", raw_orders[["order_id", "refunded", *money]].equals(
            stage_orders[["order_id", "refunded", *money]]))
        if stage == "dirty":
            recorder.require("payment_delay_count", int((stage_orders.paid_ingested_day > stage_orders.paid_day).sum())
                             == pollution["payments_delayed"])
            recorder.require("refund_delay_count", int((stage_orders.refund_ingested_day > stage_orders.refund_day).sum())
                             == pollution["refunds_delayed"])
    event_counts = {}
    for stage in ("raw", "dirty", "clean"):
        events = pd.read_parquet(directory / f"{stage}/user_events.parquet", columns=["run_id", "event_id", "event_day", "ingested_day"])
        event_counts[stage] = len(events)
        if stage == "clean":
            recorder.require("clean_event_keys_unique", not events.duplicated(["run_id", "event_id"]).any())
            recorder.require("event_delay_count", int((events.ingested_day > events.event_day).sum()) == pollution["events_delayed"])
        if stage == "raw":
            recorder.require("raw_events_unpolluted", bool(events.event_day.eq(events.ingested_day).all()))
    recorder.require("duplicate_injection_and_repair_exact", event_counts["dirty"] - event_counts["raw"]
                     == pollution["event_duplicates_injected"] == repair["duplicate_events_removed"]
                     == event_counts["dirty"] - event_counts["clean"])
    recorder.require("event_stage_counts_recorded", event_counts["raw"] == pollution["events_before"]
                     and event_counts["dirty"] == pollution["events_after"] == repair["events_before"]
                     and event_counts["clean"] == repair["events_after"])
    observations = result.dataset.observations
    recorder.require("all_users_have_one_split", observations.split.isin(["train", "validation", "test"]).all()
                     and not observations.duplicated(["run_id", "user_id"]).any())
    recorder.require("preprocessor_present", result.preprocessor is not None)
    state = result.preprocessor.to_dict()
    if population_kind == "history":
        training = result.dataset.select_split("train").observations
        recorder.require("preprocessor_fitted_on_train_keys_only", state["fit_role"] == "train"
                         and state["training_n"] == len(training) and state["training_user_key_hash"] == user_key_hash(training))
        recorder.require("all_three_splits_nonempty", set(observations.split) == {"train", "validation", "test"})
    else:
        recorder.require("validation_no_fit_all_heldout", bool(observations.split.eq("test").all())
                         and expected_preprocessor is not None and result.preprocessor.hash == expected_preprocessor.hash)
        arms = set(cfg.require("evaluation.independent_validation.arms"))
        recorder.require("validation_arms_and_denominator", set(observations.assigned_policy_arm) == arms
                         and observations.assigned_policy_arm.value_counts().sum() == len(observations))
        probability = dict(zip(cfg.require("evaluation.independent_validation.arms"),
                               cfg.require("evaluation.independent_validation.arm_probabilities"), strict=True))
        recorder.require("validation_recorded_probabilities", bool(np.allclose(observations.policy_arm_probability,
                         observations.assigned_policy_arm.map(probability), rtol=0,
                         atol=float(cfg.require("design.numerical.probability_tolerance")))))
    saved_features = pd.read_parquet(directory / "preprocessing/features.parquet")
    transformed = result.preprocessor.transform(observations)
    recorder.require("learning_features_from_frozen_sql_transform", len(saved_features) == len(observations)
                     and saved_features[["run_id", "user_id"]].equals(observations[["run_id", "user_id"]].reset_index(drop=True))
                     and np.array_equal(saved_features.loc[:, list(transformed.feature_names)].to_numpy(), transformed.matrix))
    return pollution_audit


def _power_contract(protocol: V3Protocol, job: DataCheckJob, recorder: CheckRecorder) -> dict[str, Any]:
    cfg = protocol.scenario(job.scenario_id)
    cell = cfg.section("active_scenario")
    base = protocol.scenario(cell["base_scenario_id"]).to_dict()
    expected = Config(base).with_overrides(cell["overrides"]).to_dict()
    actual = cfg.to_dict()
    expected.pop("active_scenario")
    actual.pop("active_scenario")
    recorder.require("power_exact_base_inheritance", expected == actual)
    recorder.require("power_active_multiplier_registered", cfg.require("design.local_power.active_mde_multiplier")
                     in cfg.require("design.local_power.relative_to_observed_design_mde"))
    recorder.require("power_has_no_generated_population", job.n == 0)
    return {"n_registered": cfg.require("design.n_total"), "n_actual": 0, "population_kind": "none", "base_scenario_id": cell["base_scenario_id"],
            "mechanism_status": "pending_phase_d_actual_calibrated_mechanism", "formal_repetitions_completed": 0}


def _reusable_receipt(output_root: Path, job: DataCheckJob, binding: dict[str, Any]) -> dict[str, Any] | None:
    for receipt_path in sorted(output_root.glob(f"*/jobs/{job.job_id}.json"), reverse=True):
        try:
            receipt = _read_json(receipt_path)
            parent_manifest = _read_json(receipt_path.parents[1] / "manifest.json")
            expected_hash = parent_manifest.get("output_hashes", {}).get(f"jobs/{job.job_id}.json")
            if expected_hash != file_sha256(receipt_path):
                continue
            if receipt.get("status") != "passed" or receipt.get("binding") != binding or not receipt.get("checks"):
                continue
            if not all(row["passed"] for row in receipt["checks"]):
                continue
            if job.category != "power_contract":
                summary = receipt["summary"]
                if any(not verify_artifact_manifest(Path(summary[name]), config_hash=binding["scenario_hash"],
                           data_config_hash=binding["data_config_hash"]) for name in ("pipeline_manifest", "audit_manifest")):
                    continue
                if not verify_artifact_manifest(Path(summary["sealed_manifest"]), config_hash=binding["scenario_hash"],
                                                data_config_hash=None):
                    continue
                if any(file_sha256(summary[name]) != receipt["manifest_hashes"][name]
                       for name in ("pipeline_manifest", "audit_manifest", "sealed_manifest")):
                    continue
            return {**receipt, "reused_receipt": str(receipt_path.resolve())}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def run_data_validation(output_root: Path | None = None, *, scope: str = "smoke", resume: bool = False,
                        scenario_ids: Sequence[str] | None = None, workspace_root: Path | None = None) -> Path:
    """Run real C01/C02 engineering attempts; reuse only exact verified receipts.

    All output attempts are immutable once terminal. A failed or interrupted job
    remains recorded and receives a fresh directory on retry. Full coverage is
    separate from this command's selected-scope success; formal R always stays 0.
    """
    root = Path(workspace_root or Path(__file__).resolve().parents[3]).resolve()
    output_root = Path(output_root or root / "outputs/v3/data_validation").resolve()
    protocol, settings = load_v3_protocol(), load_v3_data_config()
    jobs = plan_data_checks(protocol, scope=scope, scenario_ids=scenario_ids)
    started = datetime.now(timezone.utc)
    attempt = f"phase_c_{started.strftime('%Y%m%dT%H%M%S%fZ')}_pid{os.getpid()}"
    output = output_root / attempt
    source_before = data_check_source_hashes()
    identity = process_identity(os.getpid())
    if identity is None:
        raise ActiveValidationError("current process creation identity could not be verified")
    all_checks: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    receipts: dict[str, dict[str, Any]] = {}
    manifest = {"source_label": settings.require("source_label"), "status": "running", "scope": scope,
                "started_at_utc": started.isoformat(), "pid": os.getpid(), "python_version": platform.python_version(),
                "process_identity": identity,
                "protocol_hash": protocol.config_hash, "data_config_hash": settings.hash(64), "source_hashes_before": source_before,
                "planned_job_ids": [job.job_id for job in jobs], "formal_repetitions_completed": 0,
                "full_required_engineering_coverage_requested": scope == "all" and scenario_ids is None,
                "full_required_engineering_coverage": False,
                "power_mechanism_status": "pending_phase_d_actual_calibrated_mechanism",
                "validation_queue_status": "engineering_placeholder_only_not_phase_f_policy_evidence"}

    def checkpoint() -> None:
        pd.DataFrame(all_checks, columns=["job_id", "scenario_id", "check", "passed", "formal_repetitions_completed", "details"]).to_csv(
            output / "checks.csv", index=False, encoding=str(settings.require("io.csv_encoding")))
        pd.DataFrame(summaries).to_csv(output / "scenario_summary.csv", index=False, encoding=str(settings.require("io.csv_encoding")))
        _write_json(output / "manifest.json", manifest)

    with _output_registry_lock(output_root):
        _assert_no_active_overlap(output_root, set(manifest["planned_job_ids"]))
        (output / "jobs").mkdir(parents=True, exist_ok=False)
        checkpoint()
    print(f"Phase C engineering output: {output}", flush=True)
    try:
        for job in jobs:
            if data_check_source_hashes() != source_before:
                raise RuntimeError("sources changed between engineering jobs; retain attempt and resume final source state")
            cfg = protocol.scenario(job.scenario_id)
            binding = {"job": job.__dict__, "scenario_hash": cfg.hash(64), "protocol_hash": protocol.config_hash,
                       "data_config_hash": settings.hash(64), "source_hashes": source_before}
            if job.historical_job_id:
                history = receipts[job.historical_job_id]
                binding["history_manifest_hash"] = history["manifest_hashes"]["pipeline_manifest"]
            receipt = _reusable_receipt(output_root, job, binding) if resume else None
            if receipt is None:
                recorder = CheckRecorder(job.job_id, job.scenario_id, [])
                receipt = {"status": "running", "binding": binding, "checks": recorder.records,
                           "started_at_utc": datetime.now(timezone.utc).isoformat()}
                _write_json(output / "jobs" / f"{job.job_id}.json", receipt)
                tick = time.perf_counter()
                print(f"[{job.job_id}] n={job.n} running", flush=True)
                try:
                    if job.category == "power_contract":
                        summary = _power_contract(protocol, job, recorder)
                    else:
                        rep_id = int(settings.require("validation.representative_rep"))
                        frozen = None
                        arm_rows = None
                        if job.historical_job_id:
                            historical_directory = Path(receipts[job.historical_job_id]["summary"]["pipeline_manifest"]).parent
                            frozen = FrozenPreprocessor.from_dict(_read_json(historical_directory / "preprocessing/state.json"))
                            arm_rows = engineering_validation_assignment(cfg, n=job.n, rep_id=rep_id)
                        population = generate_v3_population(cfg, rep_id, job.n, population_kind=job.population_kind,
                                                            validation_assignment=arm_rows)
                        facts = population.observation_bundle()
                        data_directory = root / "data/v3" / str(settings.require("io.engineering_namespace")) / job.job_id / attempt
                        result = build_observed_pipeline(*facts, cfg, directory=data_directory, run_id=f"{attempt}__{job.job_id}",
                            rep_id=rep_id, stream_prefix=population.metadata["stream_prefix"], population_kind=job.population_kind,
                            persist_database=job.persist_database, frozen_preprocessor=frozen)
                        audit_directory = root / "audit/v3" / str(settings.require("io.engineering_namespace")) / job.job_id / attempt
                        sealed_manifest = archive_sealed_population(population, cfg, directory=audit_directory / "sealed",
                                                                    observed_manifest=result.manifest_path)
                        recorder.require("sealed_private_state_hashes", verify_artifact_manifest(sealed_manifest,
                                         config_hash=cfg.hash(64), data_config_hash=None))
                        summary = check_pipeline_result(*facts, cfg, result, recorder=recorder, audit_directory=audit_directory / "ledger_checks",
                                                        population_kind=job.population_kind, expected_preprocessor=frozen)
                        summary["sealed_manifest"] = str(sealed_manifest.resolve())
                        if job.historical_job_id:
                            historical = ObservedDataset.from_manifest(Path(receipts[job.historical_job_id]["summary"]["pipeline_manifest"]), cfg)
                            recorder.require("validation_users_disjoint_from_history", set(result.dataset.observations.user_id).isdisjoint(
                                historical.observations.user_id))
                        receipt["manifest_hashes"] = {name: file_sha256(summary[name]) for name in ("pipeline_manifest", "audit_manifest", "sealed_manifest")}
                        del population, result, facts
                    recorder.require("source_hashes_unchanged_during_job", data_check_source_hashes() == source_before)
                    receipt.update(status="passed", summary=summary, elapsed_seconds=time.perf_counter() - tick)
                except BaseException as exc:
                    receipt.update(status="failed", error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc(),
                                   elapsed_seconds=time.perf_counter() - tick)
                    raise
                finally:
                    receipt["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
                    _write_json(output / "jobs" / f"{job.job_id}.json", receipt)
                    all_checks.extend(recorder.records)
                    if receipt["status"] == "failed":
                        summaries.append({"job_id": job.job_id, "scenario_id": job.scenario_id, "category": job.category,
                                          "n_actual_requested": job.n, "n_registered": cfg.require("design.n_total"),
                                          "status": "failed", "formal_repetitions_completed": 0})
                        checkpoint()
            else:
                all_checks.extend(receipt["checks"])
                _write_json(output / "jobs" / f"{job.job_id}.json", receipt)
                print(f"[{job.job_id}] reused verified passed receipt", flush=True)
            receipts[job.job_id] = receipt
            summaries.append({"job_id": job.job_id, "scenario_id": job.scenario_id, "category": job.category,
                              "n_actual_requested": job.n, "n_actual": receipt["summary"]["n_actual"],
                              "n_registered": cfg.require("design.n_total"),
                              "status": "contract_passed_pending_phase_d" if job.category == "power_contract" else "passed",
                              "reused": "reused_receipt" in receipt, "elapsed_seconds": receipt.get("elapsed_seconds"),
                              "formal_repetitions_completed": 0, "details": json.dumps(receipt["summary"], ensure_ascii=False)})
            checkpoint()
        manifest["source_hashes_after"] = data_check_source_hashes()
        if manifest["source_hashes_after"] != source_before:
            raise RuntimeError("sources changed during engineering validation")
        manifest["status"] = "passed"
        manifest["full_required_engineering_coverage"] = manifest["full_required_engineering_coverage_requested"]
    except BaseException as exc:
        manifest.update(status="failed", error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        manifest.update(ended_at_utc=datetime.now(timezone.utc).isoformat(), recorded_jobs=len(summaries),
                        passed_jobs=sum(row["status"] != "failed" for row in summaries),
                        failed_jobs=sum(row["status"] == "failed" for row in summaries),
                        checks=len(all_checks), failed_checks=sum(not row["passed"] for row in all_checks))
        manifest["category_counts"] = {category: {
            "planned": sum(job.category == category for job in jobs),
            "passed": sum(row["category"] == category and row["status"] != "failed" for row in summaries),
            "failed": sum(row["category"] == category and row["status"] == "failed" for row in summaries),
        } for category in sorted({job.category for job in jobs})}
        checkpoint()
        manifest["output_hashes"] = {path.relative_to(output).as_posix(): file_sha256(path)
                                     for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}
        _write_json(output / "manifest.json", manifest)
    return output
