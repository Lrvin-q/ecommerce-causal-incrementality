# -*- coding: utf-8 -*-
"""引用核验（协议 §8：12 篇现有文献，不扩充装饰引用）。

回答三个问题：
1. refs.bib 是否恰为底表 S1–S12（不多不少、键名对应）？
2. 正文是否真的引用了它们（而不是把 [@s1] 原样印出来）？
3. 生成的 .bbl 条目是否与正文引用一一对应？

任何一项读不懂都按失败退出，不静默跳过（AGENTS §12.7）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXPECTED = [f"s{i}" for i in range(1, 13)]
BIB_KEY = re.compile(r"@\w+\{\s*([^,\s]+)\s*,")
CITE = re.compile(r"\\(?:auto|text|paren|foot)?cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}")
BBL_ENTRY = re.compile(r"\\entry\{([^}]*)\}")
ESCAPED = re.compile(r"\{\[\}@")


def parse_bib_keys(path: Path) -> list[str]:
    keys = BIB_KEY.findall(path.read_text(encoding="utf-8"))
    if not keys:
        raise ValueError(f"{path} 里没有解析出任何条目")
    return keys


def parse_cites(body_tex: Path) -> list[str]:
    found: list[str] = []
    for group in CITE.findall(body_tex.read_text(encoding="utf-8")):
        found.extend(k.strip() for k in group.split(",") if k.strip())
    return found


def check(bib: Path, body_tex: Path, bbl: Path, expected: list[str]) -> tuple[dict, list[str]]:
    problems: list[str] = []
    keys = parse_bib_keys(bib)
    if sorted(keys) != sorted(expected):
        extra = sorted(set(keys) - set(expected))
        missing = sorted(set(expected) - set(keys))
        problems.append(f"refs.bib 键集合与底表不一致：多 {extra} / 少 {missing}")

    text = body_tex.read_text(encoding="utf-8")
    if ESCAPED.search(text):
        problems.append("正文里出现字面量 {[}@：pandoc 未开 --biblatex，引用没有生效")

    cites = parse_cites(body_tex)
    unknown = sorted(set(cites) - set(keys))
    if unknown:
        problems.append(f"正文引用了 refs.bib 之外的键：{unknown}")
    uncited = sorted(set(keys) - set(cites))
    if uncited:
        problems.append(f"有未引用的条目（违反“不多不少”）：{uncited}")

    entries = BBL_ENTRY.findall(bbl.read_text(encoding="utf-8", errors="replace"))
    if sorted(entries) != sorted(set(cites)):
        problems.append(f".bbl 条目与正文引用不一致：bbl={sorted(entries)} cites={sorted(set(cites))}")

    report = {
        "bib_keys": len(keys),
        "cited_unique": len(set(cites)),
        "cite_occurrences": len(cites),
        "bbl_entries": len(entries),
    }
    return report, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bib", required=True, type=Path)
    ap.add_argument("--body-tex", required=True, type=Path)
    ap.add_argument("--bbl", required=True, type=Path)
    args = ap.parse_args(argv)
    for p in (args.bib, args.body_tex, args.bbl):
        if not p.exists():
            print(f"[FAIL] 缺输入 {p}", file=sys.stderr)
            return 3
    try:
        report, problems = check(args.bib, args.body_tex, args.bbl, EXPECTED)
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 3
    print(f"bib={report['bib_keys']} 引用键={report['cited_unique']} "
          f"引用次数={report['cite_occurrences']} bbl={report['bbl_entries']}")
    if problems:
        for item in problems:
            print(f"[FAIL] {item}", file=sys.stderr)
        return 2
    print("OK：12 篇引用齐全、无表外条目、正文与 .bbl 一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
