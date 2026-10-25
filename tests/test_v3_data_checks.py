"""Engineering evidence must come from execution, with honest scope and recovery."""

from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import pytest

from causal_growth.data.v3_dirt import inject_dirt
from causal_growth.data.v3_tables import build_raw_tables
from causal_growth.evaluation import v3_data_checks as checks
from causal_growth.v3_config import load_v3_protocol
from causal_growth.v3_data_config import load_v3_data_config


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def hist_fraud_case() -> dict:
    cfg = load_v3_protocol().scenario("L1_main").with_overrides({"data.dirty.fraud_user_rate": 0.5})
    rep_id = load_v3_data_config().require("validation.representative_rep")
    population = checks.generate_v3_population(cfg, n=load_v3_data_config().require("validation.smoke_n"), rep_id=rep_id)
    stream_prefix = population.metadata["stream_prefix"]
    raw = build_raw_tables(*population.observation_bundle(), cfg, run_id="hist_fraud_case",
                           rep_id=rep_id, stream_prefix=stream_prefix)
    selected = checks.child_rng(int(cfg.require("project.master_seed")),
        f"{stream_prefix}.dirty.hist_fraud", rep_id).random(len(raw["users"])) < cfg.require("data.dirty.fraud_user_rate")
    selected_indexes, unselected_indexes = np.flatnonzero(selected), np.flatnonzero(~selected)
    assert len(selected_indexes) >= 2 and len(unselected_indexes)
    raw["users"]["hist_gmv"] = np.arange(len(raw["users"]), dtype=float) + 1
    raw["users"].loc[selected_indexes[0], "hist_gmv"] = 0
    dirty = inject_dirt(raw, cfg, rep_id=rep_id, stream_prefix=stream_prefix)
    return {"cfg": cfg, "raw": raw["users"], "dirty": dirty.tables["users"], "selected": selected,
            "selected_zero": selected_indexes[0], "selected_nonzero": selected_indexes[1],
            "unselected": unselected_indexes[0], "recorded_selected_count": dirty.counts["hist_fraud_injected"],
            "stream_prefix": stream_prefix, "rep_id": rep_id}


def run_hist_fraud_check(case: dict, *, dirty: pd.DataFrame | None = None,
                         recorded_selected_count: int | None = None) -> tuple[dict, checks.CheckRecorder]:
    recorder = checks.CheckRecorder("hist_fraud_case", "L1_main", [])
    result = checks._check_hist_fraud(case["raw"], case["dirty"] if dirty is None else dirty, case["cfg"],
        recorder=recorder, stream_prefix=case["stream_prefix"], rep_id=case["rep_id"],
        recorded_selected_count=case["recorded_selected_count"] if recorded_selected_count is None else recorded_selected_count)
    return result, recorder


def test_hist_fraud_replay_distinguishes_selected_zero_nonzero_and_unchanged_users(hist_fraud_case: dict) -> None:
    case = hist_fraud_case
    result, recorder = run_hist_fraud_check(case)
    assert case["dirty"].loc[case["selected_zero"], "hist_gmv"] == 0
    assert case["dirty"].loc[case["selected_nonzero"], "hist_gmv"] == (
        case["raw"].loc[case["selected_nonzero"], "hist_gmv"] * case["cfg"].require("data.dirty.fraud_hist_gmv_multiplier"))
    assert case["dirty"].loc[~case["selected"], "hist_gmv"].equals(case["raw"].loc[~case["selected"], "hist_gmv"])
    assert result == {"hist_fraud_selected": int(case["selected"].sum()),
                      "hist_fraud_changed": int(case["selected"].sum()) - 1}
    assert all(row["passed"] for row in recorder.records)
    details = json.loads(next(row["details"] for row in recorder.records if row["check"] == "anomaly_values_match_replay"))
    assert details["selected_count"] == result["hist_fraud_selected"]
    assert details["changed_count"] == details["expected_changed_count"] == result["hist_fraud_changed"]


@pytest.mark.parametrize("target", ["selected_zero", "selected_nonzero", "unselected"])
def test_hist_fraud_replay_rejects_any_tampered_dirty_value(hist_fraud_case: dict, target: str) -> None:
    dirty = hist_fraud_case["dirty"].copy(deep=True)
    dirty.loc[hist_fraud_case[target], "hist_gmv"] += 1
    with pytest.raises(checks.DataCheckFailure, match="anomaly_values_match_replay"):
        run_hist_fraud_check(hist_fraud_case, dirty=dirty)


def test_hist_fraud_replay_rejects_tampered_selected_count(hist_fraud_case: dict) -> None:
    with pytest.raises(checks.DataCheckFailure, match="anomaly_injection_count"):
        run_hist_fraud_check(hist_fraud_case, recorded_selected_count=hist_fraud_case["recorded_selected_count"] + 1)


@pytest.mark.parametrize("overrides", [{"data.dirty.enabled": False}, {"data.dirty.fraud_hist_gmv_multiplier": 1}])
def test_hist_fraud_replay_allows_zero_changes_only_when_mechanism_requires_it(hist_fraud_case: dict, overrides: dict) -> None:
    case = dict(hist_fraud_case)
    case["cfg"] = case["cfg"].with_overrides(overrides)
    case["dirty"] = case["raw"].copy(deep=True)
    if not case["cfg"].require("data.dirty.enabled"):
        case["recorded_selected_count"] = 0
    result, recorder = run_hist_fraud_check(case)
    assert result["hist_fraud_changed"] == 0
    assert result["hist_fraud_selected"] == case["recorded_selected_count"]
    assert all(row["passed"] for row in recorder.records)


def test_plan_covers_registry_sizes_database_and_validation_without_changing_formal_n() -> None:
    protocol, settings = load_v3_protocol(), load_v3_data_config()
    before = protocol.config_hash
    jobs = checks.plan_data_checks(protocol, scope="all")
    counts = Counter(job.category for job in jobs)
    assert counts == {"matrix": 73, "representative": 4, "matrix_validation": 4, "power_contract": 20}
    assert len({job.job_id for job in jobs}) == len(jobs)
    scenarios = protocol.config.require("scenarios")
    assert {job.scenario_id for job in jobs if job.category == "matrix"} == {cell["id"] for cell in scenarios}
    assert all(job.n == settings.require("validation.per_scenario_n") for job in jobs if job.category == "matrix")
    assert all(job.n == settings.require("validation.representative_n") and job.persist_database
               for job in jobs if job.category == "representative")
    assert all(job.n == settings.require("validation.independent_validation_n") and job.population_kind == "validation"
               and job.historical_job_id in {other.job_id for other in jobs}
               for job in jobs if job.category == "matrix_validation")
    assert all(job.n == 0 for job in jobs if job.category == "power_contract")
    assert protocol.config_hash == before
    assert all(protocol.scenario(cell["id"]).require("design.n_total") == cell["n"] for cell in scenarios)
    with pytest.raises(ValueError, match="registered"):
        checks.plan_data_checks(protocol, scenario_ids=["typo"])


def test_power_contract_executes_no_population_and_preserves_pending_status(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("a power template is not an actual calibrated mechanism")

    monkeypatch.setattr(checks, "generate_v3_population", forbidden)
    output = checks.run_data_validation(scope="power", workspace_root=tmp_path)
    manifest = read_json(output / "manifest.json")
    summary = pd.read_csv(output / "scenario_summary.csv")
    assert manifest["status"] == "passed"
    assert manifest["full_required_engineering_coverage"] is False
    assert manifest["formal_repetitions_completed"] == 0
    assert manifest["power_mechanism_status"] == "pending_phase_d_actual_calibrated_mechanism"
    assert summary.status.eq("contract_passed_pending_phase_d").all()
    assert summary.n_actual.eq(0).all() and len(summary) == 20
    assert not (tmp_path / "data").exists()


def test_actual_smoke_independent_validation_and_resume_integrity(tmp_path: Path) -> None:
    kwargs = {"workspace_root": tmp_path, "scope": "smoke", "scenario_ids": ["L0_P_main"]}
    output = checks.run_data_validation(**kwargs)
    manifest = read_json(output / "manifest.json")
    evidence = pd.read_csv(output / "checks.csv")
    assert manifest["status"] == "passed" and manifest["passed_jobs"] == 2
    assert manifest["full_required_engineering_coverage"] is False
    assert manifest["formal_repetitions_completed"] == 0 and evidence.passed.all()
    assert any(evidence.check.str.contains("independent_B_ledger"))
    assert "validation_users_disjoint_from_history" in set(evidence.check)
    receipt = read_json(output / "jobs/smoke__L0_P_main.json")
    summary = receipt["summary"]
    assert summary["n_actual"] == load_v3_data_config().require("validation.smoke_n")
    assert summary["n_registered"] == load_v3_protocol().scenario("L0_P_main").require("design.n_total")
    sealed = read_json(Path(summary["sealed_manifest"]))
    assert sealed["artifact_namespace"] == "audit"
    assert sealed["checks"]["released_to_analysis"] is False
    assert "private_state.parquet" in sealed["artifacts"]
    resumed = checks.run_data_validation(resume=True, **kwargs)
    assert pd.read_csv(resumed / "scenario_summary.csv").reused.all()
    assert read_json(output / "manifest.json") == manifest

    # A modified observed artifact invalidates both its history job and the
    # validation transformer dependency. It cannot be accepted by a passed flag.
    artifact = Path(summary["pipeline_manifest"]).parent / "lineage/stages.json"
    artifact.write_text(artifact.read_text(encoding="utf-8") + " ", encoding="utf-8")
    rerun = checks.run_data_validation(resume=True, **kwargs)
    assert not pd.read_csv(rerun / "scenario_summary.csv").reused.any()
    assert read_json(output / "manifest.json")["status"] == "passed"
    assert checks.file_sha256(artifact) != read_json(Path(summary["pipeline_manifest"]))["artifacts"]["lineage/stages.json"]["sha256"]


def test_ledger_failure_is_loud_preserves_attempt_and_cannot_resume_as_passed(tmp_path: Path, monkeypatch) -> None:
    original = checks.audit_window_ledger

    def wrong_ledger(*args, **kwargs):
        ledger = original(*args, **kwargs)
        ledger.loc[ledger.index[0], "net_profit_cent"] += 1
        return ledger

    monkeypatch.setattr(checks, "audit_window_ledger", wrong_ledger)
    with pytest.raises(checks.DataCheckFailure, match="net_profit_cent"):
        checks.run_data_validation(workspace_root=tmp_path, scenario_ids=["L1_main"])
    output = next(path for path in (tmp_path / "outputs/v3/data_validation").iterdir() if path.is_dir())
    failed = read_json(output / "manifest.json")
    assert failed["status"] == "failed" and failed["failed_jobs"] == 1 and failed["failed_checks"] == 1
    assert failed["full_required_engineering_coverage"] is False and failed["formal_repetitions_completed"] == 0
    failed_receipt = read_json(output / "jobs/smoke__L1_main.json")
    assert failed_receipt["status"] == "failed"
    ledger_manifest = next((tmp_path / "audit").glob("**/ledger_checks/manifest.json"))
    assert read_json(ledger_manifest)["status"] == "failed"
    monkeypatch.setattr(checks, "audit_window_ledger", original)
    recovered = checks.run_data_validation(workspace_root=tmp_path, scenario_ids=["L1_main"], resume=True)
    assert not pd.read_csv(recovered / "scenario_summary.csv").reused.any()
    assert read_json(output / "manifest.json") == failed


def test_receipt_and_source_tampering_prevent_resume(tmp_path: Path, monkeypatch) -> None:
    kwargs = {"workspace_root": tmp_path, "scope": "power", "scenario_ids": ["L0_P_main"]}
    output = checks.run_data_validation(**kwargs)
    job = checks.plan_data_checks(load_v3_protocol(), scope="power", scenario_ids=["L0_P_main"])[0]
    path = output / "jobs" / f"{job.job_id}.json"
    receipt = read_json(path)
    assert checks._reusable_receipt(output.parent, job, receipt["binding"]) is not None
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert checks._reusable_receipt(output.parent, job, receipt["binding"]) is None
    source = checks.data_check_source_hashes()
    monkeypatch.setattr(checks, "data_check_source_hashes", lambda: {**source, "new_source.py": "changed"})
    updated = checks.run_data_validation(resume=True, **kwargs)
    assert not pd.read_csv(updated / "scenario_summary.csv").reused.any()


def test_persisted_sqlite_is_reopened_by_independent_checker(tmp_path: Path) -> None:
    cfg = load_v3_protocol().scenario("L1_main")
    settings = load_v3_data_config()
    population = checks.generate_v3_population(cfg, n=settings.require("validation.smoke_n"))
    facts = population.observation_bundle()
    result = checks.build_observed_pipeline(*facts, cfg, directory=tmp_path / "data", run_id="sqlite_check",
        rep_id=settings.require("validation.representative_rep"), stream_prefix=population.metadata["stream_prefix"],
        persist_database=True)
    recorder = checks.CheckRecorder("sqlite_check", "L1_main", [])
    summary = checks.check_pipeline_result(*facts, cfg, result, recorder=recorder, audit_directory=tmp_path / "audit",
                                          population_kind="history")
    assert summary["database_persisted"] is True
    assert "persistent_sqlite_reopens_and_matches" in {row["check"] for row in recorder.records}
    assert all(row["passed"] for row in recorder.records)


def child_environment() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(root / "src")}


def timeout_seconds() -> int:
    return int(load_v3_data_config().require("sql.busy_timeout_seconds"))


def start_identity_holder() -> tuple[subprocess.Popen, dict]:
    source = """import json, os, sys
from causal_growth.evaluation.v3_data_checks import process_identity
print(json.dumps(process_identity(os.getpid())), flush=True)
sys.stdin.readline()
"""
    process = subprocess.Popen([sys.executable, "-c", source], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8", env=child_environment())
    line = process.stdout.readline()
    assert line, process.stderr.read()
    return process, json.loads(line)


def fake_running(output_root: Path, identity: dict | None, pid: int, jobs: list[str], *, name: str = "old") -> Path:
    path = output_root / name / "manifest.json"
    checks._write_json(path, {"status": "running", "pid": pid, "process_identity": identity, "planned_job_ids": jobs,
                              "protocol_hash": "older_protocol_still_conflicts", "data_config_hash": "older_data_config"})
    return path


def test_actual_live_process_blocks_overlap_including_resume_but_allows_nonoverlap_then_exit(tmp_path: Path) -> None:
    owner, identity = start_identity_holder()
    actual_pid = identity["pid"]
    output_root = tmp_path / "reports"
    jobs = checks.plan_data_checks(load_v3_protocol(), scope="power", scenario_ids=["L0_P_main"])
    original = fake_running(output_root, identity, actual_pid, [job.job_id for job in jobs])
    original_text = original.read_text(encoding="utf-8")
    try:
        assert checks.process_identity(actual_pid) == identity
        for resume in (False, True):
            with pytest.raises(checks.ActiveValidationError, match="active PID"):
                checks.run_data_validation(output_root, workspace_root=tmp_path, scope="power",
                                           scenario_ids=["L0_P_main"], resume=resume)
        assert len([path for path in output_root.iterdir() if path.is_dir()]) == 1
        independent = checks.run_data_validation(output_root, workspace_root=tmp_path, scope="power", scenario_ids=["L1_main"])
        assert read_json(independent / "manifest.json")["status"] == "passed"
    finally:
        owner.communicate("finish\n", timeout=timeout_seconds())
    assert checks.process_identity(actual_pid) is None
    # The stale running manifest is retained. Verified exit, rather than its
    # status flag, is what permits this new execution.
    retried = checks.run_data_validation(output_root, workspace_root=tmp_path, scope="power", scenario_ids=["L0_P_main"])
    assert read_json(retried / "manifest.json")["status"] == "passed"
    assert original.read_text(encoding="utf-8") == original_text


def test_creation_identity_distinguishes_reused_pid_and_refuses_unknown(tmp_path: Path, monkeypatch) -> None:
    owner, identity = start_identity_holder()
    actual_pid = identity["pid"]
    job_id = "power_contract__example"
    try:
        prior = dict(identity)
        if os.name == "nt":
            prior["created"] = str(int(identity["created"]) - 1)
        else:
            boot, stamp = identity["created"].split(":")
            prior["created"] = f"{boot}:{int(stamp) - 1}"
        record = fake_running(tmp_path, prior, actual_pid, [job_id])
        checks._assert_no_active_overlap(tmp_path, {job_id})
        assert checks.process_identity(actual_pid) == identity
        fake_running(tmp_path, None, actual_pid, [job_id])
        with pytest.raises(checks.ActiveValidationError, match="unknown creation identity"):
            checks._assert_no_active_overlap(tmp_path, {job_id})
        fake_running(tmp_path, {**identity, "created": None}, actual_pid, [job_id])
        with pytest.raises(checks.ActiveValidationError, match="invalid recorded"):
            checks._assert_no_active_overlap(tmp_path, {job_id})

        def inaccessible(pid):
            raise checks.ActiveValidationError("access denied; cannot inspect")

        monkeypatch.setattr(checks, "process_identity", inaccessible)
        with pytest.raises(checks.ActiveValidationError, match="access denied"):
            checks._assert_no_active_overlap(tmp_path, {job_id})
        assert record.is_file()
    finally:
        owner.communicate("finish\n", timeout=timeout_seconds())


def test_two_real_processes_race_only_one_registers_and_enters_job(tmp_path: Path) -> None:
    source = """import os, sys
from pathlib import Path
from causal_growth.evaluation import v3_data_checks as checks
root = Path(sys.argv[1])
original = checks._power_contract
paused = False
def held_contract(*args, **kwargs):
    global paused
    if not paused:
        paused = True
        (root / ('entered_' + str(os.getpid()))).write_text('entered', encoding='utf-8')
        sys.stdin.readline()
    return original(*args, **kwargs)
checks._power_contract = held_contract
print('READY', flush=True)
sys.stdin.readline()
try:
    checks.run_data_validation(root, workspace_root=root.parent, scope='power', scenario_ids=['L0_P_main'])
except checks.ActiveValidationError as exc:
    (root / ('blocked_' + str(os.getpid()))).write_text(str(exc), encoding='utf-8')
"""
    output_root = tmp_path / "reports"
    output_root.mkdir()
    children = [subprocess.Popen([sys.executable, "-c", source, str(output_root)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=child_environment())
                for _ in range(2)]
    try:
        for child in children:
            assert child.stdout.readline().strip() == "READY"
        for child in children:
            child.stdin.write("start\n")
            child.stdin.flush()
        deadline = time.monotonic() + timeout_seconds()
        while time.monotonic() < deadline:
            if len(list(output_root.glob("entered_*"))) == 1 and len(list(output_root.glob("blocked_*"))) == 1:
                break
            time.sleep(1)
        assert len(list(output_root.glob("entered_*"))) == 1
        assert len(list(output_root.glob("blocked_*"))) == 1
        manifests = list(output_root.glob("*/manifest.json"))
        assert len(manifests) == 1
        manifest = read_json(manifests[0])
        assert manifest["status"] == "running" and manifest["process_identity"] == checks.process_identity(manifest["pid"])
        assert set(manifest["planned_job_ids"]) == {job.job_id for job in checks.plan_data_checks(
            load_v3_protocol(), scope="power", scenario_ids=["L0_P_main"])}
    finally:
        for child in children:
            stdout, stderr = child.communicate("finish\n", timeout=timeout_seconds())
            assert child.returncode == 0, (stdout, stderr)
    assert read_json(manifests[0])["status"] == "passed"


def test_os_registry_lock_is_released_after_actual_abnormal_process_exit(tmp_path: Path) -> None:
    source = """import os, sys
from pathlib import Path
from causal_growth.evaluation.v3_data_checks import _output_registry_lock
with _output_registry_lock(Path(sys.argv[1])):
    print(str(os.getpid()), flush=True)
    sys.stdin.readline()
    os._exit(1)
"""
    owner = subprocess.Popen([sys.executable, "-c", source, str(tmp_path)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=child_environment())
    try:
        actual_pid = int(owner.stdout.readline().strip())
        with pytest.raises(checks.ActiveValidationError, match="registering"):
            with checks._output_registry_lock(tmp_path):
                pytest.fail("lock admitted a competing process")
    finally:
        owner.communicate("crash\n", timeout=timeout_seconds())
    assert owner.returncode != 0
    with checks._output_registry_lock(tmp_path):
        assert checks.process_identity(actual_pid) is None
