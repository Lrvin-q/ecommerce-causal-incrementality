# -*- coding: utf-8 -*-
"""脚本 43 的解析与判据单测（不依赖真实 PDF）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "43_long_draft_audit.py"
spec = importlib.util.spec_from_file_location("audit43", SCRIPT)
audit43 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit43)


def _pgm(path: Path, width: int, height: int, rows: list[bytes]) -> Path:
    header = f"P5\n{width} {height}\n255\n".encode("ascii")
    path.write_bytes(header + b"".join(rows))
    return path


def test_effective_chars_ignores_markup_and_headings():
    text = "# 标题\n\n| a | b |\n|---|---|\n| 中文 | 2 |\n文字**加粗**与`代码`，见图 ![图](x.png)\n"
    # 表头 2 字 + 数据行 3 字 + “文字加粗与代码，见图” 10 字；分隔行与图片路径不计
    assert audit43.effective_chars(text) == 2 + 3 + 10


def test_split_chapters_requires_exact_four_in_order():
    good = "\n".join(
        f"# {name} {{#ch-x}}\n正文" for name in audit43.ALLOWED
    )
    chapters = audit43.split_chapters(good)
    assert list(chapters) == audit43.ALLOWED
    with pytest.raises(ValueError, match="恰为"):
        audit43.split_chapters("# 引言\n# 结果与分析\n")
    with pytest.raises(ValueError, match="重复"):
        audit43.split_chapters("# 引言\n# 引言\n")


def test_parse_aux_pages_reads_first_occurrence(tmp_path: Path):
    aux = tmp_path / "main.aux"
    aux.write_text(
        "\\newlabel{ch-intro}{{1}{3}}\n\\newlabel{ch-method}{{2}{3}}\n"
        "\\newlabel{ch-results}{{3}{12}}\n\\newlabel{ch-conclusion}{{4}{40}}\n",
        encoding="utf-8",
    )
    assert audit43.parse_aux_pages(aux) == {
        "ch-intro": 3, "ch-method": 3, "ch-results": 12, "ch-conclusion": 40
    }


def test_dark_fraction_detects_ink_and_skips_margins(tmp_path: Path):
    width, height = 20, 100
    blank = bytes([255]) * width
    ink = bytes([0]) * width
    # 前 50 行留白、后 50 行全黑；底部 8% 留白带应被跳过
    rows = [blank] * 50 + [ink] * 50
    path = _pgm(tmp_path / "p.pgm", width, height, rows)
    frac = audit43.read_pgm_dark_fraction(path, top_skip=0.05, bottom_skip=0.08)
    assert 0.4 < frac < 0.5
    white = _pgm(tmp_path / "w.pgm", width, height, [blank] * height)
    assert audit43.read_pgm_dark_fraction(white, 0.05, 0.08) == 0.0


def test_missing_label_is_an_error_not_a_zero(tmp_path: Path):
    body = tmp_path / "body.md"
    body.write_text("\n".join(f"# {n}\n内容" for n in audit43.ALLOWED), encoding="utf-8")
    aux = tmp_path / "main.aux"
    aux.write_text("\\newlabel{ch-intro}{{1}{3}}\n", encoding="utf-8")
    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(ValueError, match="缺章标签"):
        audit43.audit(body, pdf, aux, dpi=50, ink=0.015,
                      top_skip=0.05, bottom_skip=0.08,
                      min_pages=None, max_pages=None)
