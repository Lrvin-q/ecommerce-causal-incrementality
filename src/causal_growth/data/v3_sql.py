"""SQLite-only observed v3 outcomes with arrival-aware snapshots and full denominators.

Synthetic / known DGP. No production import of the independent array ledger is
allowed here: every outcome below is materialized by the checked-in SQL source.
"""

from __future__ import annotations

import hashlib
import math
import sqlite3
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from causal_growth.config import Config
from causal_growth.data.v3_sql_fast import load_facts_fast
from causal_growth.data.v3_storage import dataframe_sha256, validate_artifact_path
from causal_growth.v3_data_config import load_v3_data_config


BUSINESS_TABLES = ("users", "coupon_assignment", "user_events", "orders", "user_outcomes")
CENT_COLUMNS = (
    "gross_order_amount_cent", "gross_refund_reversal_cent", "goods_cost_cent", "goods_cost_recovered_cent",
    "fulfill_cost_cent", "coupon_cost_initial_cent", "coupon_return_cent", "coupon_cost_cent",
    "refund_processing_fee_cent", "consumer_paid_cent", "consumer_refund_cent", "net_profit_cent",
    "net_transaction_amount_cent",
)
OUTCOME_COLUMNS = (
    "run_id", "user_id", "window_type", "window_days", "window_end_day", "asof_day", "mature",
    "converted", "refunded", "paid_orders", "refunded_orders", *CENT_COLUMNS,
    "required_ingestion_day", "complete_after_day",
)
ANALYSIS_COLUMNS = (
    "run_id", "user_id", "treatment", "label", "actual_action", "design_probability",
    "assigned_policy_arm", "policy_arm_probability", "assignment_day", "assignment_ingested_day",
    "assignment_week", "assignment_elapsed_days", "split", "is_new", "hist_gmv", "cart_value_cent",
    "cart_value", "browse_depth", "channel", "event_retained_count", "event_truncated_count", "asof_day",
    "conversion_window_end_day", "profit_window_end_day", "complete_after_day", "required_ingestion_day",
    "convert_mature", "mature", "diagnostic_snapshot", "paid_purchase_7d", "any_refund_30d", "refunded",
    "paid_orders_30d", "refunded_orders_30d", *CENT_COLUMNS,
    "net_profit", "coupon_cost", "gross_order_amount", "net_transaction_amount", "gmv",
)


@dataclass(frozen=True)
class SqlAnalysisResult:
    """Bind the exact SQL-produced frame to fixed source and content fingerprints."""

    user_outcomes: pd.DataFrame
    analysis: pd.DataFrame
    summaries: dict[str, pd.DataFrame]
    quality: pd.DataFrame
    asof_day: float | None
    relative_snapshot_days: float | None
    database_path: Path | None
    visible_assigned_n: int
    input_users_n: int
    config_hash: str
    data_config_hash: str
    analysis_sha256: str
    sql_sha256: str
    diagnostic_snapshot: bool
    recomputed_input_outcomes: bool


def sql_source_hash() -> str:
    """Fingerprint DDL, analytics and the SQL execution glue used for provenance."""
    root = Path(__file__).resolve().parents[3]
    paths = (root / "sql" / "v3_schema.sql", root / "sql" / "v3_analytics.sql", Path(__file__).resolve())
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _sql_literal(value: str | float | int | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if not math.isfinite(value):
        raise ValueError("SQL parameters must be finite")
    return repr(int(value)) if isinstance(value, (int, np.integer)) else repr(float(value))


def _scalar(value: object) -> object:
    if pd.isna(value):
        return None
    return value.item() if isinstance(value, np.generic) else value


def _load_facts(connection: sqlite3.Connection, tables: Mapping[str, pd.DataFrame], chunk_size: int) -> None:
    if set(tables) != set(BUSINESS_TABLES):
        raise ValueError(f"Exactly five business tables required; received {sorted(tables)}")
    for name in BUSINESS_TABLES:
        frame = tables[name]
        if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
            raise ValueError(f"{name} requires a DataFrame with unique column names")
        columns = tuple(row[1] for row in connection.execute(f'PRAGMA table_info("{name}")'))
        unexpected = set(frame.columns) - set(columns)
        missing = set(columns) - set(frame.columns)
        if unexpected or (missing and (name != "user_outcomes" or len(frame))):
            raise ValueError(f"{name} schema mismatch: unknown={sorted(unexpected)}, missing={sorted(missing)}")
        if name == "user_outcomes":
            # Derived inputs are never trusted; a new snapshot recomputes them.
            continue
        column_sql = ",".join(f'"{column}"' for column in columns)
        placeholders = ",".join("?" for _ in columns)
        statement = f'INSERT INTO "{name}" ({column_sql}) VALUES ({placeholders})'
        for start in range(0, len(frame), chunk_size):
            block = frame.iloc[start:start + chunk_size].loc[:, columns]
            rows = (tuple(_scalar(value) for value in row) for row in block.itertuples(index=False, name=None))
            connection.executemany(statement, rows)


def _summary_views(connection: sqlite3.Connection) -> None:
    for name, extra in (("groups", ()), ("channels", ("channel",)), ("new_users", ("is_new",)), ("weeks", ("assignment_week",))):
        group = ",".join(("run_id", "treatment", *extra))
        connection.execute(f"""CREATE VIEW v3_{name} AS
        SELECT {group},COUNT(*) AS n_total,SUM(actual_action) AS issued_users,
               SUM(paid_purchase_7d) AS paid_users_7d,AVG(paid_purchase_7d) AS purchase_rate_7d,
               SUM(any_refund_30d) AS refunded_users_30d,AVG(any_refund_30d) AS refund_rate_30d,
               SUM(paid_orders_30d) AS paid_orders_30d,SUM(refunded_orders_30d) AS refunded_orders_30d,
               AVG(net_profit) AS net_profit_per_assigned_user,SUM(net_profit_cent) AS total_net_profit_cent,
               AVG(coupon_cost) AS coupon_cost_per_assigned_user,SUM(coupon_cost_cent) AS total_coupon_cost_cent,
               AVG(gross_order_amount) AS gross_order_amount_per_assigned_user,
               AVG(design_probability) AS mean_recorded_design_probability,
               MIN(mature) AS all_mature,MAX(diagnostic_snapshot) AS diagnostic_snapshot
        FROM v3_analysis GROUP BY {group}""")


def run_sql_pipeline(
    tables: Mapping[str, pd.DataFrame], cfg: Config, *, database_path: str | Path | None = None,
    asof_day: float | None = None, relative_snapshot_days: float | None = None,
    allow_immature: bool = False,
) -> SqlAnalysisResult:
    """Materialize both observed windows through identical memory/persistent SQL.

    Complete mode includes every supplied assigned user. Explicit diagnostic
    snapshots only include already-occurred and ingested assignments; original
    and visible denominators are both recorded. Relative snapshots use each
    user's assignment clock, as required by the immature-window negative control.
    """
    if asof_day is not None and relative_snapshot_days is not None:
        raise ValueError("absolute asof_day and relative_snapshot_days are mutually exclusive")
    if relative_snapshot_days is not None and not allow_immature:
        raise ValueError("relative snapshots require explicit allow_immature=True diagnostics")
    if not isinstance(allow_immature, bool):
        raise TypeError("allow_immature must be Boolean")
    data_cfg = load_v3_data_config()
    if "users" not in tables or not len(tables["users"]):
        raise ValueError("SQL population must contain assigned users")
    # Infinity cannot be used to bypass the explicit arrival/maturity rules.
    for value in (asof_day, relative_snapshot_days):
        if value is not None and not math.isfinite(value):
            raise ValueError("snapshot times must be finite")
    max_delay = float(cfg.require("data.dirty.ingestion_delay_max_hours")) / float(data_cfg.require("time.hours_per_day"))
    if max_delay < 0:
        raise ValueError("negative ingestion delay bound")
    if asof_day is None and relative_snapshot_days is None:
        # Sum durations before adding the clock, matching SQL and relative snapshots.
        asof_day = float(tables["users"].assignment_day.max()) + (float(cfg.require("windows.profit_days")) + max_delay)
    ratio = Fraction(str(float(cfg.require("business.repeat.gross_value_ratio"))))
    face_cent = float(cfg.require("business.coupon_reference_face")) * int(cfg.require("business.money.cents_per_yuan"))
    if not face_cent.is_integer():
        raise ValueError("reference coupon face must be an integer number of cents")
    parameters = {
        "asof_day": asof_day, "relative_snapshot_days": relative_snapshot_days,
        "convert_window_name": str(data_cfg.require("sql.convert_window_name")),
        "profit_window_name": str(data_cfg.require("sql.profit_window_name")),
        "convert_days": float(cfg.require("windows.convert_days")),
        "profit_days": float(cfg.require("windows.profit_days")),
        "maximum_ingestion_delay_days": max_delay,
        "cents_per_yuan": int(cfg.require("business.money.cents_per_yuan")),
        "repeat_ratio_numerator": ratio.numerator, "repeat_ratio_denominator": ratio.denominator,
        "coupon_returned_on_refund": int(cfg.require("business.coupon_returned_on_refund")),
        "virtual_aa_labels": int(cfg.require("dgp.virtual_aa_labels")),
        "aa_actual_action": int(cfg.require("design.aa.actual_action")),
        "observational_history": int(cfg.require("dgp.profile") == "l3" and not cfg.require("dgp.virtual_aa_labels")),
        "expected_design_probability": float(cfg.require("design.aa.virtual_label_probability") if cfg.require("dgp.virtual_aa_labels") else cfg.require("design.treatment_probability")),
        "reference_face_cent": int(face_cent),
        "probability_tolerance": float(cfg.require("design.numerical.probability_tolerance")),
        "diagnostic_snapshot": int(allow_immature), "config_hash": cfg.hash(64), "data_config_hash": data_cfg.hash(64),
    }
    if parameters["convert_window_name"] == parameters["profit_window_name"]:
        raise ValueError("conversion and profit windows must have distinct names")
    target = None if database_path is None else validate_artifact_path(database_path, role="observed_sql")
    if target is not None:
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite a prior database: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[3]
    connection = sqlite3.connect(":memory:" if target is None else str(target), timeout=float(data_cfg.require("sql.busy_timeout_seconds")))
    try:
        connection.executescript((root / "sql" / "v3_schema.sql").read_text(encoding="utf-8"))
        # Phase D.4：批量装载快路径（等价性见 tests/test_v3_sql_fast.py 六维度证明）。
        # 旧实现 _load_facts 保留在下方，供 test_frozen_reference 做漂移守护。
        load_facts_fast(connection, tables, int(data_cfg.require("sql.insert_chunk_size")))
        projection = ",".join(f'{_sql_literal(value)} AS "{name}"' for name, value in parameters.items())
        connection.execute(f"CREATE VIEW v3_parameters AS SELECT {projection}")
        policy_rows = " UNION ALL ".join(
            f"SELECT {_sql_literal(arm)} AS policy_arm,{_sql_literal(float(probability))} AS probability"
            for arm, probability in zip(cfg.require("evaluation.independent_validation.arms"), cfg.require("evaluation.independent_validation.arm_probabilities"), strict=True)
        )
        connection.execute(f"CREATE VIEW v3_policy_design AS {policy_rows}")
        channels = " UNION ALL ".join(f"SELECT {_sql_literal(channel)} AS channel" for channel in cfg.section("business.channels"))
        connection.execute(f"CREATE VIEW v3_known_channels AS {channels}")
        analytics_sql = (root / "sql" / "v3_analytics.sql").read_text(encoding="utf-8")
        time_checks, separator, outcome_sql = analytics_sql.partition("-- V3_OUTCOME_MATERIALIZATION")
        if not separator:
            raise ValueError("SQL source lacks its mandatory pre-materialization time gate")
        connection.executescript(time_checks)
        invalid_times = connection.execute("SELECT * FROM v3_time_quality WHERE violations<>0").fetchall()
        if invalid_times:
            raise ValueError(f"SQL arrival-time quality audit failed: {invalid_times}")
        connection.executescript(outcome_sql)
        _summary_views(connection)
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign:
            raise ValueError(f"SQLite foreign-key audit failed: {foreign}")
        quality = pd.read_sql_query("SELECT * FROM v3_quality", connection)
        failed = quality.loc[quality.violations != 0]
        if len(failed):
            raise ValueError(f"SQL business-quality audit failed: {failed.to_dict('records')}")
        analysis = pd.read_sql_query("SELECT * FROM v3_analysis ORDER BY run_id,user_id", connection)
        outcomes = pd.read_sql_query("SELECT * FROM user_outcomes ORDER BY run_id,user_id,window_type", connection)
        if tuple(analysis.columns) != ANALYSIS_COLUMNS or tuple(outcomes.columns) != OUTCOME_COLUMNS:
            raise AssertionError("SQL output columns differ from the explicit observation contract")
        input_n, visible_n = len(tables["users"]), len(analysis)
        if not allow_immature and (visible_n != input_n or not analysis.mature.eq(1).all()):
            raise ValueError("Primary analysis requires every assigned user with fully mature outcomes; use an explicit diagnostic snapshot")
        summaries = {
            name: pd.read_sql_query(f"SELECT * FROM v3_{name} ORDER BY run_id,treatment", connection)
            for name in ("groups", "channels", "new_users", "weeks", "cost_ledger", "funnel")
        }
        connection.commit()
        return SqlAnalysisResult(
            user_outcomes=outcomes, analysis=analysis, summaries=summaries, quality=quality,
            asof_day=asof_day, relative_snapshot_days=relative_snapshot_days, database_path=target,
            visible_assigned_n=visible_n, input_users_n=input_n, config_hash=cfg.hash(64),
            data_config_hash=data_cfg.hash(64), analysis_sha256=dataframe_sha256(analysis),
            sql_sha256=sql_source_hash(), diagnostic_snapshot=allow_immature,
            recomputed_input_outcomes=bool(len(tables["user_outcomes"])),
        )
    finally:
        connection.close()
