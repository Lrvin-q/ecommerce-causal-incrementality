# -*- coding: utf-8 -*-
"""引用核验（协议 §8：12 篇现有文献，不扩充装饰引用）。

回答四个问题：
1. refs.bib 是否恰为底表 S1–S12（不多不少、键名对应）？
2. 正文是否真的引用了它们（而不是把 [@s1] 原样印出来）？
3. 生成的 .bbl 条目是否与正文引用一一对应？
4. refs.bib 的题名/年/卷/期/页是否与 `docs/v3_H05_sources.md` 的
   「机器可读字段」表逐字段一致？（2026-10-30 00:05 新增，H05 评审 P1-4）
   —— 前三项只比键集合，S1 期号与 S2 页码两条硬错就是这样一路全绿的；
   第 4 项把字段核对变成门禁的一部分，`--self-test` 自带反例夹具（AGENTS §12.3/§12.7）。

任何一项读不懂都按失败退出，不静默跳过（AGENTS §12.7）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES_DEFAULT = ROOT / "docs" / "v3_H05_sources.md"
EXPECTED = [f"s{i}" for i in range(1, 13)]
BIB_KEY = re.compile(r"@\w+\{\s*([^,\s]+)\s*,")
CITE = re.compile(r"\\(?:auto|text|paren|foot)?cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}")
BBL_ENTRY = re.compile(r"\\entry\{([^}]*)\}")
ESCAPED = re.compile(r"\{\[\}@")
ENTRY_START = re.compile(r"@(\w+)\{")
FIELD_START = re.compile(r"(\w+)\s*=\s*\{")
SOURCE_ROW = re.compile(r"^\|\s*S(\d+)\s*\|(.*)$")
NUM_FIELDS = ("year", "volume", "number", "pages")


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


def parse_bib_entries(text: str) -> dict[str, dict[str, str]]:
    """花括号配平地取出每条目的字段值（题名里含 `{CATE}` 这类嵌套）。"""
    entries: dict[str, dict[str, str]] = {}
    pos = 0
    for match in ENTRY_START.finditer(text):
        if match.start() < pos:
            continue
        head_end = text.find(",", match.end())
        if head_end < 0:
            raise ValueError("bib 条目缺键名后的逗号")
        key = text[match.end():head_end].strip()
        depth, cursor = 1, head_end + 1
        while cursor < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[cursor], 0)
            cursor += 1
        if depth:
            raise ValueError(f"bib 条目 {key} 花括号不配对")
        body = text[head_end + 1:cursor - 1]
        pos = cursor
        fields: dict[str, str] = {}
        for field in FIELD_START.finditer(body):
            name = field.group(1).lower()
            depth, probe = 1, field.end()
            while probe < len(body) and depth:
                depth += {"{": 1, "}": -1}.get(body[probe], 0)
                probe += 1
            fields[name] = body[field.end():probe - 1]
        entries[key] = fields
    if not entries:
        raise ValueError("bib 里没有解析出任何字段")
    return entries


def parse_machine_block(text: str, path: Path) -> dict[str, dict[str, str]]:
    lines = text.splitlines()
    header_at = None
    for index, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[:2] == ["key", "year"] and "volume" in cells:
            header_at = index
            break
    if header_at is None:
        raise ValueError(f"{path} 缺少「机器可读字段」表（| key | year | volume | …）")
    header = [c.strip() for c in lines[header_at].strip().strip("|").split("|")]
    records: dict[str, dict[str, str]] = {}
    index = header_at + 2
    while index < len(lines) and lines[index].strip().startswith("|"):
        cells = [c.strip() for c in lines[index].strip().strip("|").split("|")]
        if len(cells) != len(header):
            raise ValueError(f"机器可读字段表第 {index + 1} 行列数 {len(cells)} != 表头 {len(header)}")
        record = dict(zip(header, cells))
        records[record["key"]] = record
        index += 1
    if not records:
        raise ValueError(f"{path} 的机器可读字段表是空的")
    return records


def normalise_text(value: str) -> str:
    text = value.replace("--", " ").replace("–", " ").lower()
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return " ".join(text.split())


def normalise_number(value: str) -> str:
    return value.strip().replace("–", "-").replace("--", "-").replace(" ", "").lower()


def check_sources(
    sources: Path, bib_entries: dict[str, dict[str, str]], expected: list[str]
) -> list[str]:
    """底表机器块 ↔ bib 字段；题名另对底表的人类可读行做子串核对。"""
    text = sources.read_text(encoding="utf-8")
    block = parse_machine_block(text, sources)
    problems: list[str] = []
    extra = sorted(set(block) - set(expected))
    missing = sorted(set(expected) - set(block))
    if extra or missing:
        problems.append(f"底表机器块与 S1–S12 不一致：多 {extra} / 少 {missing}")
    human_rows: dict[str, str] = {}
    for line in text.splitlines():
        match = SOURCE_ROW.match(line)
        if match:
            human_rows[f"s{int(match.group(1))}"] = match.group(2)
    for key in expected:
        if key not in block or key not in bib_entries:
            continue
        record, entry = block[key], bib_entries[key]
        for field in NUM_FIELDS:
            want = record.get(field, "")
            if want in ("", "-"):
                continue
            got = entry.get(field, "")
            if normalise_number(got) != normalise_number(want):
                problems.append(f"{key}.{field} 不符：底表 {want!r} vs refs.bib {got!r}")
        title = entry.get("title", "")
        if not title:
            problems.append(f"{key} 在 refs.bib 里没有 title 字段")
            continue
        row = human_rows.get(key)
        if row is None:
            problems.append(f"底表缺 S{key[1:]} 的人类可读行")
            continue
        if normalise_text(title) not in normalise_text(row):
            problems.append(f"{key}.title 与底表行不符：{title!r}")
    return problems


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


def self_test(sources: Path, bib: Path) -> int:
    """反例夹具：正确的必须过，四类篡改必须各被抓到（AGENTS §12.3）。"""
    source_text = sources.read_text(encoding="utf-8")
    bib_text = bib.read_text(encoding="utf-8")
    scratch = ROOT / "out" / "scratch" / "h05_gate_fixture"
    scratch.mkdir(parents=True, exist_ok=True)
    cases = [
        ("correct", source_text, bib_text, None),
        ("pages", source_text, bib_text.replace("1228--1242", "1223--1232"), "s2.pages"),
        ("number", source_text, bib_text.replace("number  = {10}", "number  = {11}"), "s1.number"),
        (
            "title",
            source_text,
            bib_text.replace("Metalearners for estimating", "Metalearners for measuring"),
            "s1.title",
        ),
        ("source", source_text.replace("| 4156-4165 |", "| 4155-4165 |"), bib_text, "s1.pages"),
    ]
    failures = 0
    for name, src_text, bib_case, expect in cases:
        src_path = scratch / f"{name}.md"
        bib_path = scratch / f"{name}.bib"
        src_path.write_text(src_text, encoding="utf-8", newline="\n")
        bib_path.write_text(bib_case, encoding="utf-8", newline="\n")
        entries = parse_bib_entries(bib_case)
        problems = check_sources(src_path, entries, EXPECTED)
        hit = " ".join(problems)
        if expect is None:
            ok = not problems
        else:
            ok = any(expect in item for item in problems)
        print(f"[{'OK' if ok else 'FAIL'}] 夹具 {name}: " + (hit or "无问题"))
        failures += 0 if ok else 1
    if failures:
        print(f"[FAIL] 自检 {failures} 例不符预期", file=sys.stderr)
        return 2
    print("OK：底表↔bib 字段核对自检 5 例全部符合预期（1 正例 + 4 反例）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bib", required=True, type=Path)
    ap.add_argument("--body-tex", required=True, type=Path)
    ap.add_argument("--bbl", required=True, type=Path)
    ap.add_argument("--sources", type=Path, default=SOURCES_DEFAULT,
                    help="H05 底表（含机器可读字段表），默认 docs/v3_H05_sources.md")
    ap.add_argument("--self-test", action="store_true", help="跑底表↔bib 字段核对的 5 个夹具")
    args = ap.parse_args(argv)
    for p in (args.bib, args.body_tex, args.bbl):
        if not p.exists():
            print(f"[FAIL] 缺输入 {p}", file=sys.stderr)
            return 3
    if args.self_test:
        if not args.sources.exists():
            print(f"[FAIL] 缺底表 {args.sources}", file=sys.stderr)
            return 3
        return self_test(args.sources, args.bib)
    try:
        report, problems = check(args.bib, args.body_tex, args.bbl, EXPECTED)
        if not args.sources.exists():
            problems.append(f"缺 H05 底表 {args.sources}，无法做字段核对")
        else:
            entries = parse_bib_entries(args.bib.read_text(encoding="utf-8"))
            problems.extend(check_sources(args.sources, entries, EXPECTED))
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 3
    print(f"bib={report['bib_keys']} 引用键={report['cited_unique']} "
          f"引用次数={report['cite_occurrences']} bbl={report['bbl_entries']}")
    if problems:
        for item in problems:
            print(f"[FAIL] {item}", file=sys.stderr)
        return 2
    print("OK：12 篇引用齐全、无表外条目、正文与 .bbl 一致、字段与底表逐条相符")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
