"""D.4 等价性测试：``load_facts_fast`` 必须与 ``v3_sql._load_facts`` 逐表同内容。

合成数据 / 已知 DGP。维护时间：2026-10-25 14:31（北京时间）。

证明方式不是"看起来一样"，而是把同一份输入分别喂给两条装载路径，然后逐表比对：

1. 行数；
2. 列名、声明类型、NOT NULL 与主键顺序（``PRAGMA table_info``）；
3. 每张表的 ``typeof()`` 组合分布（覆盖 ``label ANY`` 这类混合类型列）；
4. 按主键排序后的整表**规范哈希**（值的 Python 类型 + repr，逐行分隔）；
5. 插入顺序（``SELECT rowid, * ORDER BY rowid``）——两条路径都按帧内行序装载；
6. 整条 SQL 链路的产物：``analysis_sha256``、``user_outcomes``、六张汇总视图、
   ``v3_quality``。

旧实现以**冻结副本** ``_legacy_load_facts`` 的形式留在本文件里：主控把
``v3_sql.py`` 的调用点切到 ``load_facts_fast`` 之后，``v3_sql._load_facts`` 可能
被删除，但本文件的等价性证明不依赖它的存续。``test_frozen_reference_matches_v3_sql``
在旧实现仍然存在时逐字校验冻结副本没有漂移，切换后自动 skip。

**2026-10-25 14:20（北京时间）独立评审的四处整改**（详见 ``docs/v3_phase_D_c_replay.md``）：

- §6 的两条全链路测试原先 monkeypatch 的是切换后**已无调用方**的
  ``v3_sql._load_facts``，实际变成 fast-vs-fast 的空洞断言。现在显式替换**活调用点**
  ``v3_sql.load_facts_fast``，并用调用记录反证"两条路径各真跑了一次"。
- §5 的 PRAGMA 恢复机制在 ``LOAD_PRAGMAS=()`` 下退化为"断言空集合"。现在用
  monkeypatch 注入 ``journal_mode=WAL`` / ``temp_store=2``（刻意不用 ``journal_mode=OFF``），
  在不改生产配置的前提下重新覆盖：装载期间生效、装载后逐项恢复、异常路径也恢复、跨连接复查。
- §9 新增 ``ObservedDataset.from_manifest`` 的 ``source_hashes_before`` 溯源守卫测试。
"""

from __future__ import annotations

import hashlib
import inspect
import sqlite3
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
import pytest

from causal_growth.config import Config
from causal_growth.data import v3_sql
from causal_growth.data import v3_sql_fast
from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_pipeline import pipeline_source_hashes
from causal_growth.data.v3_sql import BUSINESS_TABLES, run_sql_pipeline
from causal_growth.data.v3_sql_fast import (
    DEFAULT_CHUNK_SIZE,
    LOAD_PRAGMAS,
    fast_fact_loading,
    iter_fact_rows,
    load_facts_fast,
    read_pragmas,
    relaxed_pragmas,
)
from causal_growth.data.v3_storage import RunArtifactWriter, dataframe_sha256, file_sha256
from causal_growth.data.v3_tables import build_raw_tables
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.v3_config import load_v3_protocol

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = (ROOT / "sql" / "v3_schema.sql").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 冻结的旧实现（v3_sql.py:91-118 的逐字副本）
# --------------------------------------------------------------------------- #
def _legacy_scalar(value: object) -> object:
    if pd.isna(value):
        return None
    return value.item() if isinstance(value, np.generic) else value


def _legacy_load_facts(connection: sqlite3.Connection, tables: Mapping[str, pd.DataFrame], chunk_size: int) -> None:
    """Frozen copy of the pre-optimisation loader; the equivalence oracle."""
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
            continue
        column_sql = ",".join(f'"{column}"' for column in columns)
        placeholders = ",".join("?" for _ in columns)
        statement = f'INSERT INTO "{name}" ({column_sql}) VALUES ({placeholders})'
        for start in range(0, len(frame), chunk_size):
            block = frame.iloc[start:start + chunk_size].loc[:, columns]
            rows = (tuple(_legacy_scalar(value) for value in row) for row in block.itertuples(index=False, name=None))
            connection.executemany(statement, rows)


# --------------------------------------------------------------------------- #
# 数据库指纹：行数 + 列定义 + typeof 分布 + 规范内容哈希 + 插入顺序
# --------------------------------------------------------------------------- #
def _table_info(connection: sqlite3.Connection, name: str) -> list[tuple]:
    return list(connection.execute(f'PRAGMA table_info("{name}")'))


def _primary_key(connection: sqlite3.Connection, name: str) -> tuple[str, ...]:
    keys = sorted((row[5], row[1]) for row in _table_info(connection, name) if row[5])
    return tuple(column for _, column in keys)


def _content_sha256(connection: sqlite3.Connection, name: str) -> str:
    """Hash the whole table after ordering by primary key, keeping Python value types."""
    order = ",".join(f'"{column}"' for column in _primary_key(connection, name))
    digest = hashlib.sha256()
    for row in connection.execute(f'SELECT * FROM "{name}" ORDER BY {order}'):
        digest.update(b"\x1f".join(b"None" if value is None else
                                   f"{type(value).__name__}:{value!r}".encode("utf-8") for value in row))
        digest.update(b"\x1e")
    return digest.hexdigest()


def _insertion_order_sha256(connection: sqlite3.Connection, name: str) -> str:
    """Hash ``rowid`` order so a reordered bulk insert cannot hide behind a sorted hash."""
    digest = hashlib.sha256()
    for row in connection.execute(f'SELECT rowid, * FROM "{name}" ORDER BY rowid'):
        digest.update(b"\x1f".join(b"None" if value is None else
                                   f"{type(value).__name__}:{value!r}".encode("utf-8") for value in row))
        digest.update(b"\x1e")
    return digest.hexdigest()


def _typeof_distribution(connection: sqlite3.Connection, name: str) -> tuple[tuple[str, ...], ...]:
    """One scan per table: the combined distribution over all columns' ``typeof``.

    The combined tuples imply every per-column marginal and stay cheap on the
    million-row event table.
    """
    columns = [row[1] for row in _table_info(connection, name)]
    projection = ",".join(f'typeof("{column}")' for column in columns)
    groups = list(range(1, len(columns) + 1))
    rows = connection.execute(
        f'SELECT {projection},COUNT(*) FROM "{name}" '
        f'GROUP BY {",".join(map(str, groups))} ORDER BY {",".join(map(str, groups))}'
    ).fetchall()
    return tuple(tuple(str(value) for value in row) for row in rows)


def _table_fingerprint(connection: sqlite3.Connection, name: str, *, insertion: bool = True) -> dict[str, object]:
    fingerprint: dict[str, object] = {
        "rows": connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0],
        "columns": tuple((row[1], row[2], row[3], row[5]) for row in _table_info(connection, name)),
        "typeof": _typeof_distribution(connection, name),
        "content_sha256": _content_sha256(connection, name),
    }
    if insertion:
        fingerprint["insertion_sha256"] = _insertion_order_sha256(connection, name)
    return fingerprint


def _schema_fingerprint(connection: sqlite3.Connection) -> tuple[tuple[str, str], ...]:
    return tuple(connection.execute(
        "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall())


def _build_database(tables: Mapping[str, pd.DataFrame], loader, chunk_size: int) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA_SQL)
    try:
        loader(connection, tables, chunk_size)
    except BaseException:
        connection.close()
        raise
    connection.commit()
    return connection


def _assert_same_database(left: sqlite3.Connection, right: sqlite3.Connection, *, insertion: bool = True) -> None:
    assert _schema_fingerprint(left) == _schema_fingerprint(right)
    for name in BUSINESS_TABLES:
        expected = _table_fingerprint(left, name, insertion=insertion)
        actual = _table_fingerprint(right, name, insertion=insertion)
        assert actual == expected, name


# --------------------------------------------------------------------------- #
# 输入夹具
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


@pytest.fixture(scope="module")
def clean_tables(protocol) -> tuple[Config, dict[str, pd.DataFrame]]:
    """Real DGP five tables after pollution + dedup (NaN cart, null refunds, ~20k events)."""
    cfg = protocol.scenario("L1_main")
    population = generate_v3_population(cfg, 0, n=2000)
    raw = build_raw_tables(*population.observation_bundle(), cfg, run_id="d4:test", rep_id=0,
                           stream_prefix=population.metadata["stream_prefix"])
    dirty = inject_dirt(raw, cfg, rep_id=0, stream_prefix=population.metadata["stream_prefix"]).tables
    return cfg, deduplicate_events(dirty, cfg).tables


def _synthetic_tables(n_users: int, events_per_user: int = 1) -> dict[str, pd.DataFrame]:
    """Minimal valid five tables, with a configurable million-row event log."""
    user_id = np.arange(n_users, dtype=np.int64)
    users = pd.DataFrame({
        "run_id": "synthetic", "user_id": user_id,
        "is_new": (user_id % 2).astype(np.int8),
        "hist_gmv": (user_id % 17).astype(np.float64) * 10.0,
        "cart_value_cent": pd.array(np.where(user_id % 5 == 0, np.nan, (user_id % 1000) * 100), dtype="Int64"),
        "browse_depth": (user_id % 4).astype(np.int64),
        "channel": np.where(user_id % 2 == 0, "search", "feed"),
        "assignment_week": (user_id % 8 + 1).astype(np.int64),
        "assignment_day": (user_id % 50).astype(np.float64),
        "assignment_elapsed_days": (user_id % 50).astype(np.float64),
        "split": "test",
        "event_retained_count": events_per_user, "event_truncated_count": 0,
    })
    assignment = pd.DataFrame({
        "run_id": "synthetic", "user_id": user_id,
        "actual_action": (user_id % 2).astype(np.int64),
        "label": (user_id % 2).astype(np.int8),
        "design_probability": np.full(n_users, 0.5),
        "assigned_policy_arm": None,
        "policy_arm_probability": np.nan,
        "assignment_day": (user_id % 50).astype(np.float64),
        "ingested_day": (user_id % 50).astype(np.float64),
        "coupon_face_cent": (user_id % 2).astype(np.int64) * 1000,
    })
    owner = np.repeat(user_id, events_per_user)
    sequence = np.tile(np.arange(events_per_user, dtype=np.int64), n_users)
    day = users.assignment_day.to_numpy()[owner] - (sequence % 3) * 0.25
    events = pd.DataFrame({
        "run_id": "synthetic",
        "event_id": [f"{int(user)}:{int(step)}" for user, step in zip(owner, sequence, strict=True)],
        "user_id": owner, "event_type": np.where(sequence % 2 == 0, "browse", "cart"),
        "event_day": day, "ingested_day": day,
    })
    empty = {
        "orders": pd.DataFrame({column: pd.Series(dtype="float64") for column in (
            "run_id", "user_id", "order_id", "order_number", "action", "assignment_day", "paid_day",
            "refund_day", "refunded", "gross_order_amount_cent", "goods_cost_cent", "fulfill_cost_cent",
            "coupon_discount_cent", "coupon_cost_initial_cent", "consumer_paid_cent",
            "goods_cost_recovered_cent", "refund_processing_fee_cent", "gross_refund_reversal_cent",
            "consumer_refund_cent", "coupon_return_cent", "paid_ingested_day", "refund_ingested_day")}),
        "user_outcomes": pd.DataFrame({column: pd.Series(dtype="float64") for column in (
            "run_id", "user_id", "window_type", "window_days", "window_end_day", "asof_day", "mature",
            "converted", "refunded", "paid_orders", "refunded_orders", "gross_order_amount_cent",
            "gross_refund_reversal_cent", "goods_cost_cent", "goods_cost_recovered_cent", "fulfill_cost_cent",
            "coupon_cost_initial_cent", "coupon_return_cent", "coupon_cost_cent", "refund_processing_fee_cent",
            "consumer_paid_cent", "consumer_refund_cent", "net_profit_cent", "net_transaction_amount_cent",
            "required_ingestion_day", "complete_after_day")}),
    }
    return {"users": users, "coupon_assignment": assignment, "user_events": events, **empty}


def _non_divisor(rows: int, target: int) -> int:
    """Return a positive chunk size that does not divide ``rows`` (exercises the tail block)."""
    chunk = max(1, target)
    while rows % chunk == 0:
        chunk += 1
    return chunk


# --------------------------------------------------------------------------- #
# 1. 冻结副本与旧实现的逐字一致性
# --------------------------------------------------------------------------- #
def _normalised_source(function) -> list[str]:
    return [line.strip().replace("_legacy_scalar", "_scalar")
            for line in inspect.getsource(function).splitlines()
            if line.strip() and not line.strip().startswith(("#", '"""'))]


def test_frozen_reference_matches_v3_sql():
    """The oracle must be the real pre-optimisation code, not a convenient rewrite.

    Skips (never fails) once ``v3_sql`` no longer carries the row-by-row loader:
    the frozen copy is then the only pre-optimisation implementation left, which
    is exactly why it is frozen here instead of imported.
    """
    installed = getattr(v3_sql, "_load_facts", None)
    if installed is None:
        pytest.skip("v3_sql._load_facts 已被切换移除；冻结副本即为优化前实现")
    frozen, live = _normalised_source(_legacy_load_facts), _normalised_source(installed)
    joined = "\n".join(live)
    if "itertuples(index=False, name=None)" not in joined or "executemany" not in joined:
        pytest.skip("v3_sql._load_facts 已不再是逐行实现（调用点已切换）；冻结副本即为优化前实现")
    frozen[0] = live[0] = "def _load_facts(...)"
    assert frozen == live, "v3_sql._load_facts 与测试用的冻结副本不一致：等价性证明失效"


def test_business_table_constant_matches_v3_sql():
    from causal_growth.data.v3_sql_fast import BUSINESS_TABLES as FAST_TABLES

    assert FAST_TABLES == BUSINESS_TABLES


# --------------------------------------------------------------------------- #
# 2. 逐表等价（真实 DGP 五表：含 NaN 可空列、可空 Int64、user_outcomes 被跳过）
# --------------------------------------------------------------------------- #
def test_every_table_is_identical_to_the_legacy_loader(clean_tables):
    _, tables = clean_tables
    assert len(tables["user_outcomes"]) == 0
    assert tables["users"].cart_value_cent.isna().any()
    assert tables["orders"].refund_day.isna().any()
    assert tables["coupon_assignment"].assigned_policy_arm.isna().all()
    legacy = _build_database(tables, _legacy_load_facts, 10_000)
    fast = _build_database(tables, load_facts_fast, 10_000)
    try:
        _assert_same_database(legacy, fast)
        for connection in (legacy, fast):
            assert connection.execute("SELECT COUNT(*) FROM user_outcomes").fetchone()[0] == 0
    finally:
        legacy.close()
        fast.close()


def test_user_outcomes_payload_is_never_loaded_but_still_validated(clean_tables):
    _, tables = clean_tables
    untrusted = tables["user_outcomes"]
    polluted = {**tables, "user_outcomes": untrusted.assign(
        **{column: np.arange(len(untrusted) + 1, dtype=np.int64)[:len(untrusted)]
           for column in untrusted.columns[3:]})}
    legacy = _build_database(polluted, _legacy_load_facts, 1_000)
    fast = _build_database(polluted, load_facts_fast, 1_000)
    try:
        assert fast.execute("SELECT COUNT(*) FROM user_outcomes").fetchone()[0] == 0
        _assert_same_database(legacy, fast)
    finally:
        fast.close()
        legacy.close()
    # An empty outcome frame may omit derived columns; a non-empty one may not.
    truncated = {**tables, "user_outcomes": tables["user_outcomes"].drop(columns=list(tables["user_outcomes"].columns[3:]))}
    _build_database(truncated, load_facts_fast, 1_000).close()
    non_empty = truncated["user_outcomes"].reindex(range(1)).fillna(0)
    with pytest.raises(ValueError, match="user_outcomes schema mismatch"):
        _build_database({**truncated, "user_outcomes": non_empty}, load_facts_fast, 1_000)


# --------------------------------------------------------------------------- #
# 3. NaN / pd.NA / None 的处理逐格等价
# --------------------------------------------------------------------------- #
def test_missing_values_become_sql_null_with_the_same_typeof_distribution(clean_tables):
    _, tables = clean_tables
    legacy = _build_database(tables, _legacy_load_facts, 517)
    fast = _build_database(tables, load_facts_fast, 517)
    try:
        nulls: dict[str, dict[str, int]] = {}
        for name in BUSINESS_TABLES:
            nulls[name] = {}
            for row in _table_info(fast, name):
                column = row[1]
                count = fast.execute(f'SELECT COUNT(*) FROM "{name}" WHERE "{column}" IS NULL').fetchone()[0]
                expected = legacy.execute(f'SELECT COUNT(*) FROM "{name}" WHERE "{column}" IS NULL').fetchone()[0]
                assert count == expected, f"{name}.{column}"
                if count:
                    nulls[name][column] = count
            assert _table_fingerprint(fast, name)["typeof"] == _table_fingerprint(legacy, name)["typeof"], name
        assert nulls["users"]["cart_value_cent"] > 0
        assert nulls["orders"]["refund_day"] > 0
        assert nulls["orders"]["refund_ingested_day"] > 0
        assert nulls["coupon_assignment"]["assigned_policy_arm"] > 0
        assert nulls["coupon_assignment"]["policy_arm_probability"] > 0
    finally:
        legacy.close()
        fast.close()


@pytest.mark.parametrize("dtype", ["float64", "Int64", "object", "str"])
def test_iter_fact_rows_unboxes_and_maps_missing_to_none(dtype):
    if dtype == "float64":
        series, expected = pd.Series([1.5, np.nan, 2.5], dtype="float64"), [(1.5,), (None,), (2.5,)]
    elif dtype == "Int64":
        series, expected = pd.Series([1, pd.NA, 3], dtype="Int64"), [(1,), (None,), (3,)]
    elif dtype == "object":
        series, expected = pd.Series([{"a": 1}, None, "x"], dtype="object"), [({"a": 1},), (None,), ("x",)]
    else:
        series, expected = pd.Series(["a", None, "c"], dtype="str"), [("a",), (None,), ("c",)]
    rows = list(iter_fact_rows(pd.DataFrame({"only": series}), ("only",), 2))
    assert rows == expected
    assert rows[1][0] is None
    assert all(not isinstance(value, np.generic) for row in rows for value in row if value is not None)


# --------------------------------------------------------------------------- #
# 4. chunk 边界：行数不是 chunk 整数倍时不丢行、不重行、不改插入顺序
# --------------------------------------------------------------------------- #
def test_chunk_boundaries_keep_every_row_in_order(clean_tables):
    _, tables = clean_tables
    rows = len(tables["user_events"])
    chunk_sizes = sorted({1, 7, _non_divisor(rows, rows // 2 + 1), rows - 1, rows + 1})
    assert all(rows % chunk for chunk in chunk_sizes if chunk not in (1, 7))
    legacy = _build_database(tables, _legacy_load_facts, 10_000)
    try:
        expected = {name: _table_fingerprint(legacy, name) for name in BUSINESS_TABLES}
        for chunk_size in chunk_sizes:
            fast = _build_database(tables, load_facts_fast, chunk_size)
            try:
                assert _schema_fingerprint(fast) == _schema_fingerprint(legacy)
                for name in BUSINESS_TABLES:
                    assert _table_fingerprint(fast, name) == expected[name], (chunk_size, name)
            finally:
                fast.close()
    finally:
        legacy.close()


def test_default_chunk_size_loads_everything_and_rejects_non_positive(clean_tables):
    _, tables = clean_tables
    connection = _build_database(tables, load_facts_fast, DEFAULT_CHUNK_SIZE)
    try:
        assert connection.execute("SELECT COUNT(*) FROM user_events").fetchone()[0] == len(tables["user_events"])
    finally:
        connection.close()
    for bad in (0, -1, -10_000):
        with pytest.raises(ValueError, match="chunk_size"):
            list(iter_fact_rows(tables["users"], ("user_id",), bad))


# --------------------------------------------------------------------------- #
# 5. PRAGMA：装载期间生效、结束后恢复、异常路径也恢复、跨连接复查
# --------------------------------------------------------------------------- #
# 2026-10-25 主控裁决：生产配置 LOAD_PRAGMAS 置空（实测零收益、崩溃风险真实）。
# 但"置空"不等于"恢复机制可以不测"：置空后 read_pragmas() 恒为 {}，任何围绕空集合
# 的断言都是空洞的。这里用 monkeypatch 注入一组非空 PRAGMA——journal_mode=WAL 与
# temp_store=2，**刻意不用 journal_mode=OFF**（评审已确认 OFF 期间崩溃可能留下不可回滚
# 的库）——在不改生产配置的前提下把恢复机制重新纳入覆盖。
PRAGMA_PROBE: tuple[tuple[str, object], ...] = (("journal_mode", "WAL"), ("temp_store", 2))
PRAGMA_PROBE_NAMES: tuple[str, ...] = tuple(name for name, _ in PRAGMA_PROBE)


@pytest.fixture
def probe_pragmas(monkeypatch) -> tuple[str, ...]:
    """Temporarily install a non-empty PRAGMA set; production config stays untouched."""
    monkeypatch.setattr(v3_sql_fast, "LOAD_PRAGMAS", PRAGMA_PROBE)
    monkeypatch.setattr(v3_sql_fast, "_PRAGMA_NAMES", PRAGMA_PROBE_NAMES)
    assert v3_sql_fast.LOAD_PRAGMAS is PRAGMA_PROBE
    return PRAGMA_PROBE_NAMES


def _prepared_connection(database: Path) -> sqlite3.Connection:
    """Open ``database``, apply the schema and park ``temp_store`` at 1.

    ``temp_store`` is per-connection (it is not stored in the file), so the "prior
    value" used to prove restoration must be set on the very connection that runs the
    load. 1 differs from both the probe value (2) and the default (0), so a restore
    step that writes back a default instead of the recorded value is still caught.
    """
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA_SQL)
    connection.execute("PRAGMA temp_store=1")
    connection.commit()
    return connection


def test_probe_pragmas_take_effect_and_are_restored_item_by_item(probe_pragmas, tmp_path):
    """Injected PRAGMAs must be live inside the context and restored key by key."""
    database = tmp_path / "probe_pragmas.sqlite"
    connection = _prepared_connection(database)
    try:
        before = read_pragmas(connection, probe_pragmas)
        assert before == {"journal_mode": "delete", "temp_store": 1}
        with relaxed_pragmas(connection) as applied:
            during = read_pragmas(connection, probe_pragmas)
            assert during["journal_mode"].casefold() == "wal"
            assert during["temp_store"] == 2
            # Both switches were registered, so both are restored below.
            assert set(applied) == set(probe_pragmas)
            assert applied["journal_mode"].casefold() == "wal"
            assert applied["temp_store"] == 2
        assert read_pragmas(connection, probe_pragmas) == before
    finally:
        connection.close()
    # Cross-connection recheck: journal_mode is a property of the database file, so a
    # fresh connection must see the restored value. temp_store is per-connection and
    # therefore *cannot* be compared across connections (it reports the new default).
    probe = sqlite3.connect(database)
    try:
        assert probe.execute("PRAGMA journal_mode").fetchone()[0].casefold() == before["journal_mode"]
        assert probe.execute("PRAGMA temp_store").fetchone()[0] != 2
    finally:
        probe.close()


def test_probe_pragmas_are_restored_when_the_load_raises(probe_pragmas, tmp_path):
    """The failure path must restore every PRAGMA *and* leave no half-committed table."""
    database = tmp_path / "probe_pragma_failure.sqlite"
    connection = _prepared_connection(database)
    try:
        before = read_pragmas(connection, probe_pragmas)
        assert before == {"journal_mode": "delete", "temp_store": 1}
        broken = _synthetic_tables(50, 1)
        broken["users"] = broken["users"].copy()
        broken["users"].loc[0, "hist_gmv"] = -1.0  # CHECK(hist_gmv>=0) violation
        with pytest.raises(sqlite3.IntegrityError):
            load_facts_fast(connection, broken, 8)
        assert read_pragmas(connection, probe_pragmas) == before
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    finally:
        connection.close()
    probe = sqlite3.connect(database)
    try:
        assert probe.execute("PRAGMA journal_mode").fetchone()[0].casefold() == before["journal_mode"]
    finally:
        probe.close()


def test_the_loader_applies_the_probe_pragmas_around_the_inserts(probe_pragmas, monkeypatch, tmp_path):
    """Prove the PRAGMAs are live **while rows are being inserted**, not only at the edges."""
    database = tmp_path / "loader_probe_pragmas.sqlite"
    connection = _prepared_connection(database)
    before = read_pragmas(connection, probe_pragmas)
    assert before == {"journal_mode": "delete", "temp_store": 1}
    observed: list[dict[str, object]] = []
    real_iter_fact_rows = v3_sql_fast.iter_fact_rows

    def spy(frame, columns, chunk_size):
        observed.append(read_pragmas(connection, probe_pragmas))
        yield from real_iter_fact_rows(frame, columns, chunk_size)

    monkeypatch.setattr(v3_sql_fast, "iter_fact_rows", spy)
    try:
        load_facts_fast(connection, _synthetic_tables(200, 2), 64)
        assert observed, "装载器没有调用 iter_fact_rows，装载期间状态未被观测到"
        assert all(state["journal_mode"].casefold() == "wal" and state["temp_store"] == 2 for state in observed)
        assert read_pragmas(connection, probe_pragmas) == before
        assert connection.execute("SELECT COUNT(*) FROM user_events").fetchone()[0] == 400
    finally:
        connection.close()


def test_empty_pragma_tuple_touches_nothing(tmp_path):
    """Production config ``LOAD_PRAGMAS=()`` 的正确性凭据（配置裁决，不是恢复机制）。

    ``read_pragmas()`` 的默认参数在函数定义时就绑定成空元组，所以这里必须显式传
    探测名，否则 ``before`` 与 ``after`` 都是 ``{}``，断言又会退化成空集合比较。
    """
    assert LOAD_PRAGMAS == v3_sql_fast.LOAD_PRAGMAS == ()
    assert v3_sql_fast._PRAGMA_NAMES == ()
    assert read_pragmas(sqlite3.connect(":memory:")) == {}
    names = ("journal_mode", "temp_store", "synchronous", "cache_size")
    database = tmp_path / "no_pragma.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA_SQL)
    try:
        before = read_pragmas(connection, names)
        with relaxed_pragmas(connection) as applied:
            assert applied == {}
            assert read_pragmas(connection, names) == before
        assert read_pragmas(connection, names) == before
    finally:
        connection.close()
    # And through the public loader, which opens the write transaction itself.
    connection = sqlite3.connect(database)
    try:
        before = read_pragmas(connection, names)
        load_facts_fast(connection, _synthetic_tables(200, 2), 64)
        assert read_pragmas(connection, names) == before
        assert connection.execute("SELECT COUNT(*) FROM user_events").fetchone()[0] == 400
    finally:
        connection.close()
    probe = sqlite3.connect(database)
    try:
        assert probe.execute("PRAGMA journal_mode").fetchone()[0].casefold() == "delete"
    finally:
        probe.close()


# --------------------------------------------------------------------------- #
# 6. 整条 SQL 链路：新旧装载产出的观测表逐字节同一
# --------------------------------------------------------------------------- #
def test_sql_pipeline_output_is_identical_under_both_loaders(clean_tables, monkeypatch):
    """Swap the **live** call site (``v3_sql.load_facts_fast``), not the dead hook.

    主控把 ``run_sql_pipeline`` 的调用点切到 ``load_facts_fast`` 之后，如果本测试继续
    monkeypatch ``v3_sql._load_facts``（已无任何调用方），两路都会走快路径，测试就退化成
    fast-vs-fast 的空洞断言。这里显式替换活调用点，并用 ``calls`` 记录反证"两条路径各
    真跑了一次"——这才是这条测试唯一的价值所在。
    """
    cfg, tables = clean_tables
    legacy_loader = getattr(v3_sql, "_load_facts", None)
    assert legacy_loader is not None, "旧逐行实现必须仍留在 v3_sql 内，否则本测试没有对照物"
    calls: list[str] = []

    def slow(connection, payload, chunk_size):
        calls.append("legacy")
        return legacy_loader(connection, payload, chunk_size)

    def fast(connection, payload, chunk_size):
        calls.append("fast")
        return load_facts_fast(connection, payload, chunk_size)

    monkeypatch.setattr(v3_sql, "load_facts_fast", slow)
    legacy = run_sql_pipeline(tables, cfg)
    monkeypatch.setattr(v3_sql, "load_facts_fast", fast)
    fast_result = run_sql_pipeline(tables, cfg)
    assert calls == ["legacy", "fast"], f"两条装载路径没有各被调用一次，比对无效：{calls}"
    assert fast_result.analysis_sha256 == legacy.analysis_sha256
    assert dataframe_sha256(fast_result.analysis) == dataframe_sha256(legacy.analysis)
    assert dataframe_sha256(fast_result.user_outcomes) == dataframe_sha256(legacy.user_outcomes)
    assert dataframe_sha256(fast_result.quality) == dataframe_sha256(legacy.quality)
    pd.testing.assert_frame_equal(fast_result.analysis, legacy.analysis)
    pd.testing.assert_frame_equal(fast_result.user_outcomes, legacy.user_outcomes)
    for name in legacy.summaries:
        pd.testing.assert_frame_equal(fast_result.summaries[name], legacy.summaries[name], obj=name)
    assert fast_result.sql_sha256 == legacy.sql_sha256
    assert fast_result.input_users_n == legacy.input_users_n == len(tables["users"])
    assert fast_result.visible_assigned_n == legacy.visible_assigned_n
    assert len(fast_result.user_outcomes) == 2 * len(tables["users"])


def test_the_two_loaders_write_byte_identical_sqlite_files(clean_tables, monkeypatch, tmp_path):
    """Same ``run_id``, same inputs: the persistent database bytes must match exactly.

    这是 D.4 承诺的**最强形式**：不是"帧相等"，而是落盘文件逐字节相等（C 代表库
    614,727,680 字节的重放证据即建立在这一性质上）。
    """
    cfg, tables = clean_tables
    legacy_loader = getattr(v3_sql, "_load_facts", None)
    assert legacy_loader is not None
    monkeypatch.setattr(v3_sql, "load_facts_fast", legacy_loader)
    legacy = run_sql_pipeline(tables, cfg, database_path=tmp_path / "legacy.sqlite")
    monkeypatch.setattr(v3_sql, "load_facts_fast", load_facts_fast)
    fast = run_sql_pipeline(tables, cfg, database_path=tmp_path / "fast.sqlite")
    assert fast.analysis_sha256 == legacy.analysis_sha256
    assert file_sha256(tmp_path / "legacy.sqlite") == file_sha256(tmp_path / "fast.sqlite")
    assert (tmp_path / "legacy.sqlite").stat().st_size == (tmp_path / "fast.sqlite").stat().st_size


def test_fast_fact_loading_context_manager_only_swaps_the_dead_hook(clean_tables, monkeypatch):
    """``fast_fact_loading()`` 只交换已无调用方的 ``_load_facts``，对活调用点无影响。

    这条断言是"反静默降级"的第二道锁：谁把上下文管理器当成 A/B 开关（或反过来把
    活调用点换回 ``_load_facts`` 而以为受它控制），都会在这里被拦住。真正的 A/B 手段
    是替换 ``v3_sql.load_facts_fast`` 本身，本测试同时验证那条路径确实走得通。
    """
    cfg, tables = clean_tables
    installed = getattr(v3_sql, "_load_facts", None)
    assert installed is not None
    with fast_fact_loading():
        assert v3_sql._load_facts is load_facts_fast  # 死钩子被换
        assert v3_sql.load_facts_fast is load_facts_fast  # 活调用点未被上下文管理器改写
        during = run_sql_pipeline(tables, cfg)
    assert v3_sql._load_facts is installed
    assert v3_sql.load_facts_fast is load_facts_fast
    monkeypatch.setattr(v3_sql, "load_facts_fast", installed)
    assert v3_sql.load_facts_fast is installed
    swapped = run_sql_pipeline(tables, cfg)
    assert swapped.analysis_sha256 == during.analysis_sha256
    assert dataframe_sha256(swapped.user_outcomes) == dataframe_sha256(during.user_outcomes)


# --------------------------------------------------------------------------- #
# 7. schema 校验与旧实现同文案
# --------------------------------------------------------------------------- #
def test_schema_validation_matches_the_legacy_loader(clean_tables):
    _, tables = clean_tables
    duplicated = tables["users"].copy()
    duplicated.columns = [*duplicated.columns[:-1], duplicated.columns[-2]]
    cases: dict[str, dict[str, pd.DataFrame]] = {
        "missing_table": {name: value for name, value in tables.items() if name != "orders"},
        "extra_table": {**tables, "audit": pd.DataFrame({"a": [1]})},
        "duplicate_columns": {**tables, "users": duplicated},
        "unknown_column": {**tables, "users": tables["users"].assign(true_cate=0.0)},
        "missing_column": {**tables, "users": tables["users"].drop(columns=["channel"])},
        "not_a_frame": {**tables, "orders": tables["orders"].to_dict("list")},
    }
    for name, payload in cases.items():
        with pytest.raises(ValueError) as legacy:
            _build_database(payload, _legacy_load_facts, 1000)
        with pytest.raises(ValueError) as fast:
            _build_database(payload, load_facts_fast, 1000)
        assert str(fast.value) == str(legacy.value), name


# --------------------------------------------------------------------------- #
# 8. 百万行 user_events
# --------------------------------------------------------------------------- #
def test_million_row_event_table_is_identical():
    tables = _synthetic_tables(100_000, 10)
    assert len(tables["user_events"]) == 1_000_000
    legacy = _build_database(tables, _legacy_load_facts, 10_000)
    fast = _build_database(tables, load_facts_fast, 50_000)
    try:
        expected = _table_fingerprint(legacy, "user_events", insertion=False)
        actual = _table_fingerprint(fast, "user_events", insertion=False)
        assert actual["rows"] == expected["rows"] == 1_000_000
        assert actual == expected
    finally:
        legacy.close()
        fast.close()


# --------------------------------------------------------------------------- #
# 9. 读取守卫：manifest 的 source_hashes_before 必须逐项校验（装载器溯源缺口）
# --------------------------------------------------------------------------- #
# 独立评审的篡改实验：把 manifest 里 v3_sql_fast.py 的哈希改成假值，from_manifest
# 照样 ACCEPTED。原因是它只比对 sql_sha256，而 sql_source_hash() 只覆盖
# sql/v3_schema.sql、sql/v3_analytics.sql 与 v3_sql.py（语义指纹），装载器由
# pipeline_source_hashes() 的 src/causal_growth/**/v3*.py glob 覆盖——写时绑定、
# 读时不校验。下面把"读时也校验"钉住。
LOADER_KEY = "src/causal_growth/data/v3_sql_fast.py"
OBSERVED_KEY = "src/causal_growth/data/v3_observed.py"


def _persist_manifest(directory: Path, result, cfg, *, source_hashes: dict[str, str] | None,
                      pipeline_provenance: bool = False) -> Path:
    """Write a minimal but genuine observed run directory around ``result.analysis``."""
    metadata = {"config_hash": cfg.hash(64), "data_config_hash": result.data_config_hash,
                "sql_sha256": result.sql_sha256, "analysis_producer": "v3_sql",
                "analysis_lineage": {"producer": "v3_sql"}}
    if source_hashes is not None:
        metadata["source_hashes_before"] = source_hashes
    if pipeline_provenance:
        metadata["source_observation_hashes"] = {"users": "0" * 64, "assignments": "0" * 64,
                                                 "factual_orders": "0" * 64}
    writer = RunArtifactWriter(directory, metadata)
    writer.write_frame("sql/analysis.parquet", result.analysis, role="observed_sql")
    return writer.finish(passed=True, checks={"test": True})


def test_pipeline_source_hashes_cover_the_loader_and_the_observed_guard_module():
    """The binding set must contain both files this guard depends on."""
    recorded = pipeline_source_hashes()
    assert LOADER_KEY in recorded
    assert OBSERVED_KEY in recorded


def test_untampered_source_binding_is_accepted(clean_tables, tmp_path):
    cfg, tables = clean_tables
    result = run_sql_pipeline(tables, cfg)
    recorded = pipeline_source_hashes()
    manifest = _persist_manifest(tmp_path / "bound", result, cfg, source_hashes=recorded,
                                 pipeline_provenance=True)
    restored = ObservedDataset.from_manifest(manifest, cfg)
    assert restored.content_hash == result.analysis_sha256


@pytest.mark.parametrize("key", [LOADER_KEY, OBSERVED_KEY, "sql/v3_analytics.sql", "requirements.txt"])
def test_tampered_source_hash_is_rejected_and_names_the_file(clean_tables, tmp_path, key):
    """Tampering **any** recorded key must fail and say which file drifted.

    ``requirements.txt`` is deliberately outside the ``v3*.py`` glob: the guard must
    still verify every key the manifest actually records, by hashing the file itself.
    """
    cfg, tables = clean_tables
    result = run_sql_pipeline(tables, cfg)
    recorded = dict(pipeline_source_hashes())
    recorded[key] = "0" * 64
    manifest = _persist_manifest(tmp_path / f"tampered_{key.replace('/', '_')}", result, cfg,
                                 source_hashes=recorded, pipeline_provenance=True)
    with pytest.raises(ValueError, match=key):
        ObservedDataset.from_manifest(manifest, cfg)


def test_missing_recorded_file_counts_as_drift(clean_tables, tmp_path):
    """A recorded key whose file no longer exists is drift, not silence."""
    cfg, tables = clean_tables
    result = run_sql_pipeline(tables, cfg)
    recorded = dict(pipeline_source_hashes())
    recorded["src/causal_growth/data/v3_loader_that_never_existed.py"] = "0" * 64
    manifest = _persist_manifest(tmp_path / "missing_file", result, cfg, source_hashes=recorded,
                                 pipeline_provenance=True)
    with pytest.raises(ValueError, match="v3_loader_that_never_existed"):
        ObservedDataset.from_manifest(manifest, cfg)


def test_path_escape_in_a_recorded_key_is_refused(clean_tables, tmp_path):
    """A manifest cannot talk the guard into hashing files outside the repository."""
    cfg, tables = clean_tables
    result = run_sql_pipeline(tables, cfg)
    recorded = dict(pipeline_source_hashes())
    recorded["../outside.py"] = "0" * 64
    manifest = _persist_manifest(tmp_path / "escape", result, cfg, source_hashes=recorded,
                                 pipeline_provenance=True)
    with pytest.raises(ValueError, match="outside"):
        ObservedDataset.from_manifest(manifest, cfg)


def test_pipeline_manifest_without_source_binding_is_rejected(clean_tables, tmp_path):
    """A machine-produced manifest must not drop the binding to become unverifiable."""
    cfg, tables = clean_tables
    result = run_sql_pipeline(tables, cfg)
    manifest = _persist_manifest(tmp_path / "unbound", result, cfg, source_hashes=None,
                                 pipeline_provenance=True)
    with pytest.raises(ValueError, match="source binding"):
        ObservedDataset.from_manifest(manifest, cfg)


def test_hand_built_manifest_without_binding_stays_readable_but_marked_unbound(clean_tables, tmp_path):
    """Legacy/unit-test manifests carry no binding; the dataset records that fact."""
    cfg, tables = clean_tables
    result = run_sql_pipeline(tables, cfg)
    manifest = _persist_manifest(tmp_path / "legacy", result, cfg, source_hashes=None)
    restored = ObservedDataset.from_manifest(manifest, cfg)
    assert restored.lineage["source_binding"] == "absent"
    bound = _persist_manifest(tmp_path / "legacy_bound", result, cfg, source_hashes=pipeline_source_hashes(),
                              pipeline_provenance=True)
    assert ObservedDataset.from_manifest(bound, cfg).lineage["source_binding"] == "verified"

