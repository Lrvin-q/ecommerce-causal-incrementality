"""合成数据 / 已知 DGP：五张事实表装入 SQLite 的批量实现（Phase D.4）。

这个模块回答方案里的哪个问题
---------------------------
"五表 → SQLite"这一步能否在**不改变任何数据内容与 SQL 语义**的前提下，把装载
时间压到原来的 1/3 以下？本模块给出与 ``v3_sql._load_facts`` 行为等价的
``load_facts_fast``：同样的五表校验、同样的表装载顺序、同样的 INSERT 语句与
占位符数量、同样的 ``user_outcomes`` 跳过规则，只把"逐单元格转换"换成分块
向量化拆箱。

为什么快
--------
旧实现逐行 ``itertuples`` 再逐格 ``_scalar``（``pd.isna`` + ``np.generic.item()``）。
pandas 3 的字符串列是 Arrow 后端，逐格取值会触发 ``ArrowArray.__iter__``：
20 万人五表合计 2,700 万个单元格、1,070 万次 Arrow 迭代，全部落在 Python 层。
本实现按列 ``Series.to_numpy(dtype=object, na_value=None)`` 让 pandas/numpy 在 C
层完成 numpy→Python 拆箱，缺失值用布尔掩码**整块**置 ``None``，最后 ``zip``
在 C 层把列拼成行元组直接交给 ``executemany``。

PRAGMA 显式声明（降低崩溃安全性，换取装载速度）
---------------------------------------------
装载期间设置 ``journal_mode=OFF``、``synchronous=OFF``、``temp_store=MEMORY``、
``cache_size=-131072``（128 MiB），并在装载结束——**包括异常路径**——后恢复
装载前的原值（见 ``relaxed_pragmas``）。风险：装载中途进程崩溃/断电可能留下
无法回滚的库文件。本项目接受该风险，因为观测库是**可重建的中间件**（同一
config hash / data config hash / 源码 hash 重跑即可逐字节复现），且
``run_sql_pipeline`` 在装载后仍强制跑 ``PRAGMA foreign_key_check`` 与
``v3_quality`` 全量质量审计；库文件永远不是唯一副本，正式产物是 SQL 物化的
``v3_analysis`` parquet 与清单哈希。

与旧实现的唯一允许差异
---------------------
``chunk_size < 1`` 时直接抛 ``ValueError``。旧实现对 0 抛 ``range()`` 的
``ValueError``、对负数**静默少装所有行**（range 为空 → 空表），属于会毁数据的
隐式行为，不复制。
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from typing import Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

# v3_sql._load_facts 装载的四张事实表（user_outcomes 是不信任的派生输入，永不装载）。
# 这里显式复制常量而不是 import v3_sql：调用方切换后 v3_sql 会 import 本模块，
# 模块级反向 import 会形成循环依赖；tests 里有等价性断言守着两份常量不漂移。
BUSINESS_TABLES: tuple[str, ...] = ("users", "coupon_assignment", "user_events", "orders", "user_outcomes")
LOADED_TABLES: tuple[str, ...] = tuple(name for name in BUSINESS_TABLES if name != "user_outcomes")

#: 分块大小的默认值 = 实测甜点。n=200,000 五表单批装载（各自独立进程、同机同负载）：
#: 10,000→14.8 s、50,000→13.0 s、100,000→13.0 s；:memory: 扫描 2,000→11.8 s、
#: 10,000→10.8 s、50,000→10.5 s、200,000→10.5 s、不分块→10.2 s。10k 以后是
#: 平台期，差异落在重复运行噪声内；分块越大只抬高瞬时内存（峰值 +6 MB@10k、+14 MB@50k、
#: +25 MB@100k）。50,000 在"最慢一趟少 1.5–1.8 s / 峰值只多 8 MB"之间取平衡。
DEFAULT_CHUNK_SIZE = 50_000

#: 装载期间使用的批量 PRAGMA（顺序即应用顺序）。装载后逐项恢复原值。
LOAD_PRAGMAS: tuple[tuple[str, object], ...] = (
    ("journal_mode", "OFF"),
    ("synchronous", 0),          # 0 = OFF, 2 = FULL (SQLite default)
    ("temp_store", 2),           # 2 = MEMORY, 0 = DEFAULT
    ("cache_size", -131072),     # negative = KiB, so 128 MiB of page cache
)
_PRAGMA_NAMES: tuple[str, ...] = tuple(name for name, _ in LOAD_PRAGMAS)


def _pragma_literal(value: object) -> str:
    """Render a PRAGMA argument so that numbers stay numeric and modes stay quoted."""
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"unsupported PRAGMA value: {value!r}")
    return repr(int(value))


def _pragma_value(connection: sqlite3.Connection, name: str) -> object:
    row = connection.execute(f"PRAGMA {name}").fetchone()
    return None if row is None else row[0]


def _same_pragma(left: object, right: object) -> bool:
    if isinstance(left, str) or isinstance(right, str):
        return str(left).casefold() == str(right).casefold()
    return left == right


def read_pragmas(connection: sqlite3.Connection, names: Sequence[str] = _PRAGMA_NAMES) -> dict[str, object]:
    """Return the current values of the load-time PRAGMAs (for restoration audits)."""
    return {name: _pragma_value(connection, name) for name in names}


@contextmanager
def relaxed_pragmas(connection: sqlite3.Connection) -> Iterator[dict[str, object]]:
    """Apply bulk-load PRAGMAs and restore every previous value on exit.

    Yields the PRAGMAs that actually took effect. ``journal_mode`` can only be
    switched outside a transaction, so a caller that already has one open keeps
    its journal mode (nothing to restore) and keeps ownership of its transaction.
    When this context opened the write transaction itself, it commits on success
    and rolls back on failure — not to change the observable rows (a failed load
    is discarded by ``run_sql_pipeline`` either way) but because restoring the
    journal mode is impossible inside an open transaction. Every switch that did
    take effect is verified after restoration and a mismatch raises
    ``RuntimeError``.
    """
    started_in_transaction = connection.in_transaction
    saved: dict[str, object] = {}
    applied: dict[str, object] = {}
    try:
        for name, target in LOAD_PRAGMAS:
            if name == "journal_mode" and connection.in_transaction:
                continue
            before = _pragma_value(connection, name)
            connection.execute(f"PRAGMA {name}={_pragma_literal(target)}")
            current = _pragma_value(connection, name)
            if _same_pragma(current, target):
                saved[name] = before
                applied[name] = current
            elif not _same_pragma(current, before):
                # Silent partial application would leak an unrestorable setting.
                raise RuntimeError(f"unsupported PRAGMA target {name}={target!r}: {before!r} -> {current!r}")
        yield applied
    finally:
        failure = sys.exc_info()[0] is not None
        # journal_mode cannot be restored inside the write transaction that the
        # INSERTs opened. Committing it on success (or rolling the failed load
        # back) is the price of restoring the journal; a caller that already had
        # a transaction open keeps ownership of it and of its journal mode.
        if not started_in_transaction and connection.in_transaction and "journal_mode" in saved:
            connection.rollback() if failure else connection.commit()
        for name, before in saved.items():
            connection.execute(f"PRAGMA {name}={_pragma_literal(before)}")
        mismatched = [name for name, before in saved.items() if not _same_pragma(_pragma_value(connection, name), before)]
        if mismatched and not failure:
            raise RuntimeError(f"failed to restore SQLite PRAGMAs: {mismatched}")


def iter_fact_rows(frame: pd.DataFrame, columns: Sequence[str], chunk_size: int = DEFAULT_CHUNK_SIZE,
                   ) -> Iterator[tuple[object, ...]]:
    """Yield row tuples in ``columns`` order with missing values as ``None``.

    This is the whole optimisation in one place: per-column ``to_numpy(dtype=object)``
    does the numpy→Python unboxing in C, a boolean mask replaces NaNs/NA in bulk,
    and ``zip`` assembles the rows in C. Every value is a plain ``str``/``int``/
    ``float``/``None``, which is exactly what ``sqlite3`` binds.
    """
    if chunk_size < 1:
        raise ValueError(f"chunk_size must be a positive integer; received {chunk_size!r}")
    if not columns:
        raise ValueError("at least one column is required")
    for start in range(0, len(frame), chunk_size):
        block = frame.iloc[start:start + chunk_size]
        parts: list[np.ndarray] = []
        for column in columns:
            series = block[column]
            values = series.to_numpy(dtype=object, na_value=None)
            if series.hasnans:
                missing = series.isna().to_numpy()
                if missing.any():
                    # Arrow-backed columns may hand back a read-only view.
                    values = values if values.flags.writeable else values.copy()
                    values[missing] = None
            parts.append(values)
        yield from zip(*parts)


def _table_columns(connection: sqlite3.Connection, name: str) -> tuple[str, ...]:
    return tuple(row[1] for row in connection.execute(f'PRAGMA table_info("{name}")'))


def _validate_table(connection: sqlite3.Connection, name: str, frame: object) -> tuple[str, ...]:
    """Reproduce ``v3_sql._load_facts`` validation byte for byte, including messages."""
    if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
        raise ValueError(f"{name} requires a DataFrame with unique column names")
    columns = _table_columns(connection, name)
    unexpected = set(frame.columns) - set(columns)
    missing = set(columns) - set(frame.columns)
    if unexpected or (missing and (name != "user_outcomes" or len(frame))):
        raise ValueError(f"{name} schema mismatch: unknown={sorted(unexpected)}, missing={sorted(missing)}")
    return columns


def load_facts_fast(connection: sqlite3.Connection, tables: Mapping[str, pd.DataFrame],
                    chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
    """Load the five business tables exactly like ``v3_sql._load_facts``, only faster.

    Same contract as the original: exactly five tables, identical schema checks and
    messages, ``users``→``coupon_assignment``→``user_events``→``orders`` order,
    identical ``INSERT INTO ... VALUES (?,...)`` statement, and ``user_outcomes``
    never loaded because derived inputs are not trusted. Missing values become SQL
    ``NULL``; ``sqlite3.IntegrityError`` still propagates from the STRICT/CHECK
    constraints unchanged.
    """
    if set(tables) != set(BUSINESS_TABLES):
        raise ValueError(f"Exactly five business tables required; received {sorted(tables)}")
    with relaxed_pragmas(connection):
        for name in BUSINESS_TABLES:
            frame = tables[name]
            columns = _validate_table(connection, name, frame)
            if name == "user_outcomes":
                # Derived inputs are never trusted; a new snapshot recomputes them.
                continue
            column_sql = ",".join(f'"{column}"' for column in columns)
            placeholders = ",".join("?" for _ in columns)
            statement = f'INSERT INTO "{name}" ({column_sql}) VALUES ({placeholders})'
            connection.executemany(statement, iter_fact_rows(frame, columns, chunk_size))


@contextmanager
def fast_fact_loading() -> Iterator[None]:
    """Route ``v3_sql.run_sql_pipeline`` through ``load_facts_fast`` for A/B checks.

    Only the module attribute is swapped; ``v3_sql.py`` itself is never modified.
    Once the call site is switched permanently the old hook may be gone, in which
    case there is nothing left to route and the context is a no-op.
    """
    from causal_growth.data import v3_sql

    original = getattr(v3_sql, "_load_facts", None)
    if original is None:
        yield
        return
    v3_sql._load_facts = load_facts_fast
    try:
        yield
    finally:
        v3_sql._load_facts = original


__all__ = [
    "BUSINESS_TABLES", "DEFAULT_CHUNK_SIZE", "LOADED_TABLES", "LOAD_PRAGMAS",
    "fast_fact_loading", "iter_fact_rows", "load_facts_fast", "read_pragmas", "relaxed_pragmas",
]
