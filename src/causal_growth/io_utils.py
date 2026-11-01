"""路径解析与落盘工具。

约定
----
* 项目根目录由本文件位置反推，**不依赖当前工作目录**，因此脚本可以从任意目录调用。
* 文本一律 UTF-8；需要 Excel 直接打开的中文 CSV 用 ``utf-8-sig``。
* 所有产物路径都由本模块函数生成，**禁止在业务代码里手写相对路径**。
* 每次运行（run）的产物落在 ``outputs/runs/<run_id>/``，便于重复实验的隔离与追溯。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

__all__ = [
    "PROJECT_ROOT",
    "RunPaths",
    "configs_dir",
    "data_dir",
    "ensure_dir",
    "file_sha256",
    "figures_dir",
    "outputs_dir",
    "project_root",
    "read_csv",
    "read_json",
    "reports_dir",
    "runs_dir",
    "save_json",
    "save_table",
    "tables_dir",
    "write_csv",
    "write_text",
]

#: ``<root>/src/causal_growth/io_utils.py`` -> parents[2] == ``<root>``
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    return PROJECT_ROOT


def _sub(base: Path, parts: tuple[str, ...]) -> Path:
    return base.joinpath(*parts) if parts else base


def configs_dir(*parts: str) -> Path:
    return _sub(PROJECT_ROOT / "configs", parts)


def data_dir(*parts: str) -> Path:
    return _sub(PROJECT_ROOT / "data", parts)


def outputs_dir(*parts: str) -> Path:
    return _sub(PROJECT_ROOT / "outputs", parts)


def figures_dir(*parts: str) -> Path:
    return _sub(PROJECT_ROOT / "outputs" / "figures", parts)


def tables_dir(*parts: str) -> Path:
    return _sub(PROJECT_ROOT / "outputs" / "tables", parts)


def runs_dir(*parts: str) -> Path:
    return _sub(PROJECT_ROOT / "outputs" / "runs", parts)


def reports_dir(*parts: str) -> Path:
    return _sub(PROJECT_ROOT / "reports", parts)


def ensure_dir(path: Path | str) -> Path:
    """建目录（含父目录）并返回 Path。"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class RunPaths:
    """一次运行的产物根目录，保证重复实验互不覆盖。"""

    run_id: str

    @property
    def root(self) -> Path:
        return ensure_dir(runs_dir(self.run_id))

    def path(self, *parts: str) -> Path:
        return ensure_dir(self.root.joinpath(*parts).parent) / Path(*parts).name

    def table(self, name: str) -> Path:
        return self.path("tables", name if name.endswith(".csv") else f"{name}.csv")

    def figure(self, name: str) -> Path:
        return self.path("figures", name if name.endswith(".png") else f"{name}.png")

    def artifact(self, *parts: str) -> Path:
        return self.path(*parts)

    def meta_json(self) -> Path:
        return self.path("meta.json")


# --------------------------------------------------------------------------- #
# 读写
# --------------------------------------------------------------------------- #
def read_csv(path: Path | str, **kwargs: Any) -> pd.DataFrame:
    """读 CSV。默认 UTF-8（兼容带 BOM 的 utf-8-sig）。"""
    return pd.read_csv(Path(path), encoding=kwargs.pop("encoding", "utf-8-sig"), **kwargs)


def write_csv(
    df: pd.DataFrame,
    path: Path | str,
    *,
    index: bool = False,
    encoding: str = "utf-8-sig",
) -> Path:
    """写 CSV。默认 ``utf-8-sig``，保证 Excel 打开中文不乱码。"""
    p = Path(path)
    ensure_dir(p.parent)
    df.to_csv(p, index=index, encoding=encoding)
    return p


def save_table(df: pd.DataFrame, name: str, *, index: bool = False) -> Path:
    """把分析结果表落盘到 ``outputs/tables/``（报告里的数字都追溯到这里）。"""
    filename = name if name.endswith(".csv") else f"{name}.csv"
    return write_csv(df, tables_dir(filename), index=index)


def write_text(text: str, path: Path | str, *, encoding: str = "utf-8") -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(text, encoding=encoding)
    return p


def save_json(obj: Any, path: Path | str, *, indent: int = 2) -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=indent, sort_keys=False, default=str),
        encoding="utf-8",
    )
    return p


def read_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_sha256(path: Path | str, *, chunk: int = 1 << 20) -> str:
    """文件内容哈希，用于"两次运行结果逐字节一致"的可复现性断言。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()
