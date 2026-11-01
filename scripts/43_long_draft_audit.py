# -*- coding: utf-8 -*-
"""长稿篇幅审计（协议 §8）。

回答方案里的三个问题：
1. 结果与分析章有效字数是否 >= 正文 50%？
2. 结果与分析章实质页是否 >= 正文实质页 50%？
3. 结果与分析章实质页是否 >= 全稿实质页 50%？

实质页 = 渲染后墨迹占比超过阈值的页（顶/底留白带不计，避免页码与页眉充数）。
封面/摘要/目录属格式页（正文起始页之前），单独计数、不计入实质页分母；
否则一张只有标题的封面会以"低墨迹"混进分母、或反过来被阈值误判成内容页。
本脚本只读，不构建 PDF；构建由 paper/v3/build.sh 负责。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ALLOWED = ["引言", "研究方法", "结果与分析", "结论与展望"]
LABEL_KEYS = ["ch-intro", "ch-method", "ch-results", "ch-conclusion"]
RESULTS = "结果与分析"

MD_NOISE = re.compile(r"[#*_`\[\]{}|>~]")


def effective_chars(text: str) -> int:
    """去掉标题行、表格分隔行、图片语法与 Markdown 记号后的非空白字符数。"""
    total = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.fullmatch(r"\|?[\s:|-]+\|?", stripped):
            continue
        stripped = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", stripped)
        stripped = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", stripped)
        stripped = MD_NOISE.sub("", stripped)
        total += len(re.sub(r"\s+", "", stripped))
    return total


def split_chapters(body_md: str) -> dict[str, str]:
    """按一级标题切章；标题允许带 pandoc 属性 {#ch-xxx}。"""
    chapters: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None
    for line in body_md.splitlines():
        m = re.match(r"^#\s+(.+?)\s*(\{#[^}]*\})?\s*$", line)
        if m:
            current = m.group(1).strip()
            if current in chapters:
                raise ValueError(f"一级标题重复：{current}")
            chapters[current] = []
            order.append(current)
            continue
        if current is not None:
            chapters[current].append(line)
    for name in chapters:
        chapters[name] = "\n".join(chapters[name])
    if order != ALLOWED:
        raise ValueError(f"一级标题必须恰为 {ALLOWED} 且按序，实际 {order}")
    return chapters  # type: ignore[return-value]


def parse_aux_pages(aux_path: Path) -> dict[str, int]:
    """从 main.aux 的 \\newlabel{ch-xxx}{{n}{page}} 取各章起始页。"""
    pattern = re.compile(r"\\newlabel\{(ch-[a-z]+)\}\{\{[^}]*\}\{(\d+)\}")
    found: dict[str, int] = {}
    text = aux_path.read_text(encoding="utf-8", errors="replace")
    for key, page in pattern.findall(text):
        found.setdefault(key, int(page))
    return found


def parse_pagemap(pagemap: Path) -> dict[int, int]:
    """读 LaTeX 写出的“物理页|印刷页码”映射，返回 {印刷页码: 物理页}。

    前置页可能无号（封面）或使用罗马数字；这些行跳过，但阿拉伯数字必须连续。
    """
    text = pagemap.read_text(encoding="utf-8", errors="replace")
    pairs: list[tuple[int, int]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != 2 or not parts[0].strip().isdigit():
            raise ValueError(f"{pagemap.name}:{lineno} 读不懂 {line!r}")
        printed = parts[1].strip()
        if not printed.isdigit():
            continue
        pairs.append((int(parts[0]), int(printed)))
    if not pairs:
        raise ValueError(f"{pagemap} 里没有阿拉伯页码")
    mapping = {printed: physical for physical, printed in pairs}
    ordered = sorted(mapping)
    for a, b in zip(ordered, ordered[1:]):
        if b != a + 1:
            raise ValueError(f"印刷页码不连续：{a} -> {b}")
    # 封面与摘要都可能印“1”，重复印刷页号取最后一次出现（正文侧）。
    return mapping


def read_pgm_dark_fraction(path: Path, top_skip: float, bottom_skip: float) -> float:
    """读 P5 PGM，返回去顶底留白后的暗像素占比。"""
    data = path.read_bytes()
    if not data.startswith(b"P5"):
        raise ValueError(f"{path} 不是 P5 PGM")
    tokens: list[int] = []
    pos = 2
    while len(tokens) < 3:
        while pos < len(data) and data[pos : pos + 1].isspace():
            pos += 1
        if data[pos : pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        start = pos
        while pos < len(data) and not data[pos : pos + 1].isspace():
            pos += 1
        tokens.append(int(data[start:pos]))
    pos += 1
    width, height, maxval = tokens
    if maxval != 255:
        raise ValueError(f"{path} 的 maxval={maxval}，仅支持 255")
    y0 = int(height * top_skip)
    y1 = int(height * (1.0 - bottom_skip))
    dark = 0
    total = 0
    stride = width
    for y in range(y0, y1):
        row = data[pos + y * stride : pos + (y + 1) * stride]
        dark += sum(1 for v in row if v < 200)
        total += width
    return dark / total if total else 0.0


def render_pgm(pdf: Path, dpi: int, outdir: Path) -> list[Path]:
    subprocess.run(
        ["pdftoppm", "-gray", "-r", str(dpi), str(pdf), str(outdir / "pg")],
        check=True, capture_output=True,
    )
    pages = sorted(outdir.glob("pg-*.pgm"))
    if not pages:
        raise RuntimeError("pdftoppm 未产出任何页面")
    return pages


def audit(body: Path, pdf: Path, aux: Path, dpi: int, ink: float,
          top_skip: float, bottom_skip: float,
          min_pages: int | None, max_pages: int | None) -> tuple[dict, list[str]]:
    chapters = split_chapters(body.read_text(encoding="utf-8"))
    chars = {name: effective_chars(text) for name, text in chapters.items()}
    body_chars = sum(chars.values())
    printed = parse_aux_pages(aux)
    missing = [k for k in LABEL_KEYS if k not in printed]
    if missing:
        raise ValueError(f"main.aux 缺章标签 {missing}；正文一级标题需带 {{#ch-xxx}} 属性")
    pagemap_path = pdf.with_suffix(".pagemap")
    if not pagemap_path.exists():
        raise ValueError(f"缺页码映射 {pagemap_path}（由 paper/v3/preamble.tex 写出）")
    pagemap = parse_pagemap(pagemap_path)
    total_text_pages = max(pagemap.values())
    def phys(q: int) -> int:
        if q not in pagemap:
            raise ValueError(f"印刷页码 {q} 不在 {pagemap_path.name} 中")
        return pagemap[q]
    starts = [phys(printed[k]) for k in LABEL_KEYS]
    if starts != sorted(starts):
        raise ValueError(f"章节起始页不单调：{starts}")

    with tempfile.TemporaryDirectory() as tmp:
        imgs = render_pgm(pdf, dpi, Path(tmp))
        dark = [read_pgm_dark_fraction(p, top_skip, bottom_skip) for p in imgs]

    total_pages = len(dark)
    if total_pages != total_text_pages:
        raise ValueError(f"渲染页数 {total_pages} != 文本页数 {total_text_pages}")
    front_pages = list(range(1, starts[0]))
    substantive = [i + 1 for i, v in enumerate(dark)
                   if v >= ink and (i + 1) >= starts[0]]
    body_range = range(starts[0], total_pages + 1)
    body_sub = [p for p in substantive if p in body_range]
    res_end = starts[3] - 1
    res_sub = [p for p in substantive if starts[2] <= p <= res_end]

    report = {
        "total_pages": total_pages,
        "dark_fraction": [round(v, 4) for v in dark],
        "substantive_pages": substantive,
        "front_pages": front_pages,
        "chapters": {
            name: {"start_page": starts[i], "chars": chars[name],
                   "char_share": round(chars[name] / body_chars, 4) if body_chars else 0.0}
            for i, name in enumerate(ALLOWED)
        },
        "body_chars": body_chars,
        "results_char_share": round(chars[RESULTS] / body_chars, 4) if body_chars else 0.0,
        "body_substantive": len(body_sub),
        "results_substantive": len(res_sub),
        "results_share_of_body_pages": round(len(res_sub) / len(body_sub), 4) if body_sub else 0.0,
        "results_share_of_all_pages": round(len(res_sub) / len(substantive), 4) if substantive else 0.0,
        "ink_threshold": ink,
        "dpi": dpi,
    }
    problems: list[str] = []
    if report["results_char_share"] < 0.5:
        problems.append(f"结果有效字数占比 {report['results_char_share']:.2%} < 50%")
    if report["results_share_of_body_pages"] < 0.5:
        problems.append(f"结果实质页占正文 {report['results_share_of_body_pages']:.2%} < 50%")
    if report["results_share_of_all_pages"] < 0.5:
        problems.append(f"结果实质页占全稿 {report['results_share_of_all_pages']:.2%} < 50%")
    if min_pages is not None and total_pages < min_pages:
        problems.append(f"总页数 {total_pages} < {min_pages}")
    if max_pages is not None and total_pages > max_pages:
        problems.append(f"总页数 {total_pages} > {max_pages}")
    return report, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, type=Path)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--aux", required=True, type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--dpi", type=int, default=50)
    ap.add_argument("--ink", type=float, default=0.015)
    ap.add_argument("--top-skip", type=float, default=0.05)
    ap.add_argument("--bottom-skip", type=float, default=0.08)
    ap.add_argument("--min-pages", type=int)
    ap.add_argument("--max-pages", type=int)
    args = ap.parse_args(argv)
    for p in (args.body, args.pdf, args.aux):
        if not p.exists():
            print(f"[FAIL] 缺输入 {p}", file=sys.stderr)
            return 3
    try:
        report, problems = audit(args.body, args.pdf, args.aux, args.dpi, args.ink,
                                 args.top_skip, args.bottom_skip,
                                 args.min_pages, args.max_pages)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 3
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if problems:
        for item in problems:
            print(f"[FAIL] {item}", file=sys.stderr)
        return 2
    print("OK：长稿篇幅四项判据全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
