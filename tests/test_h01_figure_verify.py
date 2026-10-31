"""64 号 H01 图门禁的反例夹具：交换标签、改连接线端点/翻转、对齐错位、autofit 必须让校验红。"""
from __future__ import annotations

import importlib.util
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "h01_figures", ROOT / "scripts" / "64_h01_method_figures.py")
h01 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(h01)
h01.normalize()


def _emu(value: float) -> int:
    return int(round(value * 12700))


def _sp_xml(n: dict, shape_id: int) -> str:
    txbox = ' txBox="1"' if n.get("textbox") else ""
    algn = "l" if n.get("textbox") else "ctr"
    paras = "".join(
        f'<a:p><a:pPr algn="{algn}"/><a:r><a:t>{escape(line)}</a:t></a:r></a:p>'
        for line in n["text"].split("\n"))
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{n["id"]}"/>'
        f'<p:cNvSpPr{txbox}/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm>'
        f'<a:off x="{_emu(n["x"])}" y="{_emu(n["y"])}"/>'
        f'<a:ext cx="{_emu(n["w"])}" cy="{_emu(n["h"])}"/></a:xfrm></p:spPr>'
        f'<p:txBody><a:bodyPr/><a:lstStyle/>{paras}</p:txBody></p:sp>')


def _cxn_xml(e: dict, shape_id: int) -> str:
    x1, y1, x2, y2 = e["x1"], e["y1"], e["x2"], e["y2"]
    flips = (' flipH="1"' if x2 < x1 else '') + (' flipV="1"' if y2 < y1 else '')
    return (
        f'<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="{shape_id}" name="{e["id"]}"/>'
        f'<p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr><p:spPr>'
        f'<a:xfrm{flips}><a:off x="{_emu(min(x1, x2))}" y="{_emu(min(y1, y2))}"/>'
        f'<a:ext cx="{_emu(abs(x2 - x1))}" cy="{_emu(abs(y2 - y1))}"/></a:xfrm>'
        f'<a:prstGeom prst="straightConnector1"><a:avLst/></a:prstGeom>'
        f'<a:ln w="{_emu(e["width"])}"><a:tailEnd type="arrow"/></a:ln>'
        f'</p:spPr></p:cxnSp>')


def _slide_xml(index: int) -> str:
    slide = h01.SPEC["slides"][index - 1]
    body = "".join(_sp_xml(n, i + 1) for i, n in enumerate(slide["nodes"]))
    body += "".join(_cxn_xml(e, 100 + i) for i, e in enumerate(slide["edges"]))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f'<p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sld>')


def _build_pptx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for i in (1, 2, 3):
            z.writestr(f"ppt/slides/slide{i}.xml", _slide_xml(i))
    return path


def _mutated_copy(tmp_path: Path, mutate) -> Path:
    path = _build_pptx(tmp_path / "bad.pptx")
    with zipfile.ZipFile(path) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    xml = parts["ppt/slides/slide1.xml"].decode("utf-8")
    parts["ppt/slides/slide1.xml"] = mutate(xml).encode("utf-8")
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


@pytest.fixture()
def good_pptx(tmp_path: Path) -> Path:
    return _build_pptx(tmp_path / "good.pptx")


def test_synthetic_fixture_passes(good_pptx: Path):
    h01.verify_pptx(good_pptx)


def test_swapped_labels_fail(tmp_path: Path):
    def swap(xml: str) -> str:
        assert "随机分流" in xml and "处理臂" in xml
        return xml.replace("随机分流", "__TMP__").replace("处理臂", "随机分流").replace("__TMP__", "处理臂")

    with pytest.raises(AssertionError):
        h01.verify_pptx(_mutated_copy(tmp_path, swap))


def test_connector_endpoint_shift_fails(tmp_path: Path):
    def shift(xml: str) -> str:
        match = re.search(r'(<p:cxnSp>.*?<a:off x=")(-?\d+)(")', xml, flags=re.S)
        assert match
        return xml[:match.start(2)] + str(int(match.group(2)) + 127000) + xml[match.end(2):]

    with pytest.raises(AssertionError):
        h01.verify_pptx(_mutated_copy(tmp_path, shift))


def test_connector_flip_removed_fails(tmp_path: Path):
    with pytest.raises(AssertionError):
        h01.verify_pptx(_mutated_copy(tmp_path, lambda xml: xml.replace('flipV="1"', "", 1)))


def test_box_label_left_aligned_fails(tmp_path: Path):
    with pytest.raises(AssertionError):
        h01.verify_pptx(_mutated_copy(tmp_path, lambda xml: xml.replace('algn="ctr"', 'algn="l"', 1)))


def test_textbox_centered_fails(tmp_path: Path):
    with pytest.raises(AssertionError):
        h01.verify_pptx(_mutated_copy(tmp_path, lambda xml: xml.replace('algn="l"', 'algn="ctr"', 1)))


def test_autofit_fails(tmp_path: Path):
    with pytest.raises(AssertionError):
        h01.verify_pptx(_mutated_copy(
            tmp_path, lambda xml: xml.replace("<a:bodyPr/>", "<a:bodyPr><a:spAutoFit/></a:bodyPr>", 1)))


def test_missing_arrowhead_fails(tmp_path: Path):
    with pytest.raises(AssertionError):
        h01.verify_pptx(_mutated_copy(
            tmp_path, lambda xml: xml.replace('<a:tailEnd type="arrow"/>', "", 1)))


def test_svg_anchors_must_match_shape_kind(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(h01, "OUT", tmp_path)
    slide = h01.SPEC["slides"][0]
    svg = tmp_path / Path(slide["png"]).with_suffix(".svg").name
    svg.write_text(h01.svg_slide(slide), encoding="utf-8")
    h01.verify_svg(slide)
    svg.write_text(h01.svg_slide(slide).replace('text-anchor="middle"', "", 1), encoding="utf-8")
    with pytest.raises(AssertionError):
        h01.verify_svg(slide)
