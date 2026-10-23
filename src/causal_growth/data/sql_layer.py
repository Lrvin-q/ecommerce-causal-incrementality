"""SQL 数据层：以 SQLite 承载五张关系表，并用 SQL 完成口径敏感的复杂处理。

为什么要有这一层
----------------
营销数分的真实工作里，口径不是靠某个 Python 函数保证的，而是靠**库表约束 + 视图**
保证的：谁能保证"退款单不剔除""券成本只扣一次"？如果只写在 pandas 里，
换一个分析师、换一次重构就可能悄悄改掉；写成 DDL 的 CHECK 与视图的 JOIN 结构，
则是**结构上不可能错**。

本层承担三件事
--------------
1. **落库**：把五张关系表按业务系统的形态建表（含主键、外键、CHECK、索引）。
2. **固化口径**：三条红线（R1 分母为全部被分配用户、R2 双窗口分离、R3 券成本只扣一次）
   分别落到视图的驱动表选择、CHECK 约束与"每项只减一次"的表达式里。
3. **复杂取数**：去重、窗口归属、分渠道漏斗、新老客四象限、日粒度汇总，
   以及一组可用于门禁的质量检查查询。

对外接口
--------
``SQLStore`` 是一个上下文管理器；``build_database`` 负责建库；
``run_query`` 按名字执行 ``sql/analytics.sql`` 中的命名查询。
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from causal_growth.io_utils import PROJECT_ROOT, data_dir, ensure_dir

__all__ = [
    "SQL_DIR",
    "SQLStore",
    "build_database",
    "list_queries",
    "load_query_sql",
]

SQL_DIR: Path = PROJECT_ROOT / "sql"

#: `coupon_assignment.group` 是 SQL 保留字，落库时改名为 `grp`
_COLUMN_RENAME: dict[str, dict[str, str]] = {
    "coupon_assignment": {"group": "grp"},
}

_QUERY_HEADER = re.compile(r"^-- >>> name:\s*(\w+)\s*$", re.MULTILINE)


def _read(name: str) -> str:
    path = SQL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"缺少 SQL 文件：{path}")
    return path.read_text(encoding="utf-8")


def _split_queries(text: str) -> dict[str, str]:
    """把 ``-- >>> name: xxx`` 分隔的 SQL 切成 ``{名字: SQL}``。"""
    marks = list(_QUERY_HEADER.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end() : end].strip().rstrip(";").strip()
        if not body:
            raise ValueError(f"查询 {m.group(1)!r} 为空")
        out[m.group(1)] = body
    if not out:
        raise ValueError("未解析到任何命名查询")
    return out


def _views_sql(cfg: Any) -> str:
    """实例化视图 DDL：把三条红线所需的业务参数写死进去。"""
    text = _read("analytics.sql")
    marker = "-- [B] 命名查询"
    if marker not in text:
        raise ValueError("analytics.sql 缺少 '[B] 命名查询' 分段标记")
    views = text.split(marker, 1)[0]
    coupon_returned = 1 if bool(cfg.require("business.coupon_returned_on_refund")) else 0
    return views.format(
        fee_rate=float(cfg.require("business.refund_handling_fee_rate")),
        refundable_ratio=float(cfg.require("business.refundable_goods_ratio")),
        coupon_returned=coupon_returned,
        convert_days=int(cfg.require("windows.convert_days")),
        profit_days=int(cfg.require("windows.profit_days")),
    )


def load_query_sql() -> dict[str, str]:
    """返回 ``{查询名: SQL}``。供审计与测试使用。"""
    text = _read("analytics.sql")
    marker = "-- [B] 命名查询"
    body = text.split(marker, 1)[1] if marker in text else text
    return _split_queries(body)


def list_queries() -> list[str]:
    return sorted(load_query_sql())


def build_database(
    tables: dict[str, pd.DataFrame],
    cfg: Any,
    *,
    path: Path | str | None = None,
    verbose: bool = False,
) -> Path:
    """建库：DDL → 灌数 → 建视图。

    参数
    ----
    tables : ``build_five_tables`` 产出的五张表（键为表名）。
    cfg    : 配置对象，用于实例化视图中的业务参数。
    path   : 数据库路径，默认 ``data/marketing.db``。
    """
    db = Path(path) if path is not None else data_dir("marketing.db")
    ensure_dir(db.parent)
    if db.exists():
        db.unlink()

    conn = sqlite3.connect(db)
    try:
        conn.executescript(_read("schema.sql"))
        for name, frame in tables.items():
            if name not in ("users", "user_events", "coupon_assignment", "orders", "user_outcomes"):
                continue
            df = frame.copy()
            rename = _COLUMN_RENAME.get(name, {})
            if rename:
                df = df.rename(columns=rename)
            # 分类列 → 字符串；布尔列 → 0/1 整数（SQLite 无原生布尔）
            for col in df.columns:
                if str(df[col].dtype) == "category":
                    df[col] = df[col].astype(str)
                elif str(df[col].dtype) == "bool":
                    df[col] = df[col].astype(int)
            df.to_sql(name, conn, if_exists="append", index=False)
            if verbose:
                print(f"      灌入 {name:<20} {len(df):>9,} 行")
        conn.executescript(_views_sql(cfg))
        conn.commit()
    finally:
        conn.close()
    return db


@dataclass
class SQLStore:
    """SQLite 连接的轻量封装，便于按查询名取 DataFrame。"""

    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.path.exists():
            raise FileNotFoundError(f"数据库不存在：{self.path}；请先 build_database()")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            conn.close()

    def run(self, name: str, *, limit: int | None = None) -> pd.DataFrame:
        queries = load_query_sql()
        if name not in queries:
            raise KeyError(f"未知查询 {name!r}；可用：{sorted(queries)}")
        sql = queries[name]
        if limit is not None:
            sql = f"SELECT * FROM (\n{sql}\n) LIMIT {int(limit)}"
        with self.connect() as conn:
            return pd.read_sql_query(sql, conn)

    def scalar(self, name: str) -> float:
        df = self.run(name)
        if df.size != 1:
            raise ValueError(f"查询 {name!r} 返回 {df.size} 个值，不是标量")
        return float(df.iloc[0, 0])

    def tables(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        return [r[0] for r in rows]

    def views(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
            ).fetchall()
        return [r[0] for r in rows]
