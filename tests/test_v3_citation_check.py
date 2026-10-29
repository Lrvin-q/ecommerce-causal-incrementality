# -*- coding: utf-8 -*-
"""脚本 44 的引用核验单测（合成夹具，不含真实文献）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "44_citation_check.py"
spec = importlib.util.spec_from_file_location("cite44", SCRIPT)
cite44 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cite44)

EXPECTED = cite44.EXPECTED


def _bib(path: Path, keys: list[str]) -> Path:
    body = "".join(f"@article{{{k},\n  title = {{T}},\n}}\n\n" for k in keys)
    path.write_text(body, encoding="utf-8")
    return path


def _fixture(tmp_path: Path, keys: list[str], cites: list[str], bbl: list[str],
             escaped: bool = False) -> tuple[Path, Path, Path]:
    bib = _bib(tmp_path / "refs.bib", keys)
    body = "正文\n" + "".join(f"\\autocite{{{c}}}\n" for c in cites)
    if escaped:
        body += "字面量 {[}@s1{]}\n"
    body_tex = tmp_path / "body.tex"
    body_tex.write_text(body, encoding="utf-8")
    bbl_path = tmp_path / "main.bbl"
    bbl_path.write_text("".join(f"\\entry{{{k}}}{{article}}{{}}\n" for k in bbl), encoding="utf-8")
    return bib, body_tex, bbl_path


def test_clean_full_set_passes(tmp_path: Path):
    bib, body, bbl = _fixture(tmp_path, EXPECTED, EXPECTED, EXPECTED)
    report, problems = cite44.check(bib, body, bbl, EXPECTED)
    assert problems == []
    assert report["bib_keys"] == 12


def test_missing_entry_in_bib_is_caught(tmp_path: Path):
    keys = [k for k in EXPECTED if k != "s7"]
    bib, body, bbl = _fixture(tmp_path, keys, keys, keys)
    _, problems = cite44.check(bib, body, bbl, EXPECTED)
    assert any("少 ['s7']" in p for p in problems)


def test_uncited_entry_is_caught(tmp_path: Path):
    cites = [k for k in EXPECTED if k != "s12"]
    bib, body, bbl = _fixture(tmp_path, EXPECTED, cites, cites)
    _, problems = cite44.check(bib, body, bbl, EXPECTED)
    assert any("未引用" in p and "s12" in p for p in problems)


def test_escaped_literal_citation_is_caught(tmp_path: Path):
    bib, body, bbl = _fixture(tmp_path, EXPECTED, EXPECTED, EXPECTED, escaped=True)
    _, problems = cite44.check(bib, body, bbl, EXPECTED)
    assert any("字面量" in p for p in problems)


def test_bbl_mismatch_is_caught(tmp_path: Path):
    bib, body, bbl = _fixture(tmp_path, EXPECTED, EXPECTED, EXPECTED[:-1])
    _, problems = cite44.check(bib, body, bbl, EXPECTED)
    assert any(".bbl 条目与正文引用不一致" in p for p in problems)


def test_unknown_key_in_body_is_caught(tmp_path: Path):
    bib, body, bbl = _fixture(tmp_path, EXPECTED, EXPECTED + ["s99"], EXPECTED + ["s99"])
    _, problems = cite44.check(bib, body, bbl, EXPECTED)
    assert any("refs.bib 之外" in p for p in problems)


def test_empty_bib_is_an_error(tmp_path: Path):
    bib = tmp_path / "empty.bib"
    bib.write_text("% 空\n", encoding="utf-8")
    body = tmp_path / "body.tex"
    body.write_text("无引用\n", encoding="utf-8")
    bbl = tmp_path / "main.bbl"
    bbl.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="没有解析出任何条目"):
        cite44.check(bib, body, bbl, EXPECTED)
