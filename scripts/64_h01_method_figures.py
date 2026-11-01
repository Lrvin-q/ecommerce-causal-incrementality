#!/usr/bin/env python
"""H01：三方法图的原生 PPTX / SVG / PNG / 元素清单同源生成。

设计约束：
- 用 WPS 演示 COM 生成 PPTX：ProgID 借用 `PowerPoint.Application`，但 CLSID {91493441-…}
  的 LocalServer32 指向 wpp.exe（本机无 python-pptx / LibreOffice），不装任何包。
- 形状规格只写一份（SPEC），PPTX、SVG、元素清单都从它派生，保证三份产物元素一致。
- PowerShell 脚本保持纯 ASCII（PS 5.1 按 ANSI 读 .ps1，中文字面量会乱码）；
  文字全部走 UTF-8 JSON，由 PS 端 `Get-Content -Encoding UTF8` 读入。
- 临时目录用 ASCII 路径 C:\\cg_h01_tmp，结束后把产物复制回 outputs/figures/h01/。
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
import zipfile
from html import unescape
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figures" / "h01"
TMP = Path(r"C:\cg_h01_tmp")
SPEC_JSON = ROOT / "out" / "scratch" / "h01_spec.json"
SPEC_JSON_ASCII = Path(r"C:\cg_h01_tmp\h01_spec.json")
PS1 = Path(r"C:\cg_h01_tmp\h01_build.ps1")

W, H = 960, 540
FONT = "Microsoft YaHei"
BLUE, DEEP = "#2F5597", "#1F3864"
GREEN, ORANGE = "#2E7D5B", "#B05A1E"
PURPLE, GRAY = "#5B3E8E", "#595959"
LIGHT = "#F2F2F2"
WHITE = "#FFFFFF"


def node(i: str, shape: int, x: float, y: float, w: float, h: float,
         text: str, fill: str = BLUE, size: int = 14, fg: str = WHITE,
         bold: bool = False, line: str | None = None) -> dict:
    return {"id": i, "shape": shape, "x": x, "y": y, "w": w, "h": h, "text": text,
            "fill": fill, "size": size, "fg": fg, "bold": bold, "line": line}


def edge(i: str, x1: float, y1: float, x2: float, y2: float,
         color: str = GRAY, width: float = 2.0) -> dict:
    return {"id": i, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "color": color, "width": width}


def header(title: str, sub: str, tag: str) -> list[dict]:
    return [
        {"id": "title", "textbox": True, "x": 40, "y": 16, "w": 880, "h": 34,
         "text": title, "size": 24, "fg": DEEP, "bold": True},
        {"id": "subtitle", "textbox": True, "x": 40, "y": 52, "w": 880, "h": 24,
         "text": sub, "size": 13, "fg": GRAY, "bold": False},
        {"id": "tag", "textbox": True, "x": 40, "y": 78, "w": 880, "h": 22,
         "text": tag, "size": 11, "fg": PURPLE, "bold": True},
    ]


def footer(text: str) -> list[dict]:
    return [{"id": "footer", "textbox": True, "x": 40, "y": 500, "w": 880, "h": 26,
             "text": text, "size": 9, "fg": GRAY, "bold": False}]


NOTE = "合成数据 / 已知 DGP · 演示文稿原生形状（WPS 演示 COM 生成，可编辑，非截图）· 口径与论文第 2–3 章一致"

SPEC = {
    "slides": [
        {
            "index": 1,
            "png": "slide1_itt.png",
            "nodes": header(
                "方法一　随机实验口径：全臂 ITT",
                "把“发券—不发券”做成真随机，再用分配用户做分母，回答“这套流程本身有没有因果效应”。",
                "对应：D01 / D02（AA 与 MDE）· F02（每 rep 20 万新用户三臂 ITT）· G01（AA 1000 次）· G02（重训 bootstrap）",
            ) + [
                node("A", 5, 40, 150, 140, 64, "随机分流\n（分配单位 = 用户）", BLUE, 14),
                node("B", 5, 230, 100, 170, 62, "处理臂\n发 10 元券", BLUE, 14),
                node("C", 5, 230, 220, 170, 62, "对照臂\n不发券", BLUE, 14),
                node("D", 5, 450, 100, 200, 182, "结果观测\n7 天支付窗口\n30 天退款窗口\n退款单留在样本", BLUE, 13),
                node("E", 5, 700, 100, 220, 82, "主指标\n净贡献利润 ITT\nE[Π(1) − Π(0)]", DEEP, 13),
                node("F", 5, 700, 210, 220, 72, "校准与护栏\nAA 1000 次 + 退款率\n非劣效检验", GREEN, 13),
                edge("e1", 180, 182, 230, 131),
                edge("e2", 180, 182, 230, 251),
                edge("e3", 400, 131, 450, 170),
                edge("e4", 400, 251, 450, 212),
                edge("e5", 650, 191, 700, 141),
                edge("e6", 810, 182, 810, 210),
            ] + footer(NOTE),
        },
        {
            "index": 2,
            "png": "slide2_observational.png",
            "nodes": header(
                "方法二　观测因果与学习：从历史数据到异质效应",
                "用历史观测数据学条件平均效应，靠特征白名单与独立验证集挡住泄漏，再用交叉拟合 OPE 做审计。",
                "对应：D03（常数 / T / S / 因果森林 / DR 五类估计器）· F01（IPW / DR / SNIPS 与拒绝规则）",
            ) + [
                node("A", 5, 40, 150, 150, 70, "历史观测数据\n（五表 / SQL）", BLUE, 13),
                node("B", 5, 230, 150, 150, 70, "六字段白名单\n（禁泄漏特征）", BLUE, 13),
                node("C", 5, 40, 270, 340, 82, "五类估计器\n常数 / T / S / 因果森林 / DR\n同 rep、同用户配对", DEEP, 13),
                node("D", 5, 420, 270, 190, 82, "验证集选模\n测试集不参与学习", ORANGE, 13),
                node("E", 5, 660, 270, 260, 82, "条件效应 τ̂(X)\n按用户排序", PURPLE, 13),
                node("F", 5, 420, 396, 190, 82, "交叉拟合 OPE\nIPW / DR / SNIPS", GREEN, 13),
                node("G", 5, 660, 396, 260, 82, "冻结帧审计\n名单与真值逐档对照", GREEN, 13),
                edge("e1", 190, 185, 230, 185),
                edge("e2", 305, 220, 305, 270),
                edge("e3", 380, 311, 420, 311),
                edge("e4", 610, 311, 660, 311),
                edge("e5", 790, 352, 610, 396),
                edge("e6", 610, 437, 660, 437),
            ] + footer(NOTE),
        },
        {
            "index": 3,
            "png": "slide3_policy.png",
            "nodes": header(
                "方法三　预算策略：从 τ̂ 到名单与支出",
                "在预算约束下把排序变成名单，分开报“预期 / 实际 / 硬预算”，再用真值审计与两种 bootstrap 定不确定度。",
                "对应：E01 / E02（求解器与三口径支出）· F01（策略价值与护栏）· G02（固定 1000 / 重训 200）",
            ) + [
                node("A", 5, 40, 150, 270, 70, "τ̂(X) + 成本模型\n（两阶段乘式）", PURPLE, 13),
                node("B", 5, 350, 150, 220, 70, "预算档 0.04–1.00\n元 / 人", BLUE, 13),
                node("C", 5, 40, 270, 310, 82, "求解器\n贪心 / DP / MILP / LP / 局部交换\n各自能主张什么", DEEP, 13),
                node("D", 5, 390, 270, 200, 82, "名单\n每人至多 1 张券", ORANGE, 13),
                node("E", 5, 630, 270, 290, 82, "支出与利润\n预期 / 实际 / 硬预算三口径\n超支概率双分母", GREEN, 13),
                node("F", 5, 390, 396, 200, 82, "不确定度\n固定 bootstrap 1000\n重训 bootstrap 200", GREEN, 13),
                node("G", 5, 630, 396, 290, 82, "真值审计\n每 rep 20 万随机验证\n护栏上界", GREEN, 13),
                edge("e1", 310, 185, 350, 185),
                edge("e2", 310, 220, 195, 270),
                edge("e3", 350, 311, 390, 311),
                edge("e4", 590, 311, 630, 311),
                edge("e5", 490, 352, 490, 396),
                edge("e6", 590, 437, 630, 437),
            ] + footer(NOTE),
        },
    ]
}


def normalize() -> None:
    for s in SPEC["slides"]:
        s["edges"] = [x for x in s["nodes"] if "x1" in x]
        s["nodes"] = [x for x in s["nodes"] if "x1" not in x]


def write_ps1() -> None:
    ps = r'''$ErrorActionPreference = 'Stop'
$specPath = '__SPEC__'
$outDir = '__TMP__'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$spec = Get-Content -Raw -Encoding UTF8 $specPath | ConvertFrom-Json
function HexToOle($hex) {
  $h = $hex.TrimStart('#')
  $r = [Convert]::ToInt32($h.Substring(0,2),16)
  $g = [Convert]::ToInt32($h.Substring(2,2),16)
  $b = [Convert]::ToInt32($h.Substring(4,2),16)
  return [int]($b*65536 + $g*256 + $r)
}
$app = New-Object -ComObject PowerPoint.Application
$app.DisplayAlerts = 1
$pres = $app.Presentations.Add(0)
$pres.PageSetup.SlideWidth = 960
$pres.PageSetup.SlideHeight = 540
foreach ($s in $spec.slides) {
  $slide = $pres.Slides.Add([int]$s.index, 12)
  foreach ($n in $s.nodes) {
    if ($n.textbox) {
      $shp = $slide.Shapes.AddTextbox(1, [double]$n.x, [double]$n.y, [double]$n.w, [double]$n.h)
      $shp.Line.Visible = 0
      $shp.Fill.Visible = 0
    } else {
      $shp = $slide.Shapes.AddShape([int]$n.shape, [double]$n.x, [double]$n.y, [double]$n.w, [double]$n.h)
      $shp.Fill.ForeColor.RGB = HexToOle $n.fill
      if ($n.line) { $shp.Line.ForeColor.RGB = HexToOle $n.line; $shp.Line.Weight = 1.25 }
      else { $shp.Line.Visible = 0 }
    }
    $tf = $shp.TextFrame
    $tf.WordWrap = -1
    $tf.MarginLeft = 4; $tf.MarginRight = 4; $tf.MarginTop = 2; $tf.MarginBottom = 2
    $tf.VerticalAnchor = 3
    $tr = $tf.TextRange
    $tr.Text = [string]$n.text
    $tr.Font.Name = 'Microsoft YaHei'
    $tr.Font.Size = [int]$n.size
    $tr.Font.Bold = [int]$n.bold
    $tr.Font.Color.RGB = HexToOle $n.fg
    # Textboxes are left-aligned (matches SVG start anchor); box labels stay centered
    # (matches SVG text-anchor="middle"). Setting 1 for every shape broke the 20 boxes.
    if ($n.textbox) { $tr.ParagraphFormat.Alignment = 1 }
    else { $tr.ParagraphFormat.Alignment = 2 }
    # WPS shrinks textbox height to one line (34/24/22 -> 29); restore SPEC geometry.
    # The spAutoFit tag is rewritten to noAutofit after save (normalize_pptx).
    $shp.Left = [double]$n.x
    $shp.Top = [double]$n.y
    $shp.Width = [double]$n.w
    $shp.Height = [double]$n.h
  }
  foreach ($e in $s.edges) {
    $con = $slide.Shapes.AddConnector(1, [double]$e.x1, [double]$e.y1, [double]$e.x2, [double]$e.y2)
    $con.Line.ForeColor.RGB = HexToOle $e.color
    $con.Line.Weight = [double]$e.width
    $con.Line.EndArrowheadStyle = 3
  }
  $slide.Export((Join-Path $outDir $s.png), 'PNG', 2000, 1125)
}
$pptx = Join-Path $outDir 'v3_h01_three_methods.pptx'
$pres.SaveAs($pptx, 24)
$counts = @()
foreach ($s in $pres.Slides) { $counts += [string]$s.Shapes.Count }
$nSlides = $pres.Slides.Count
$pres.Close()
$app.Quit()
Write-Output ('slides=' + $nSlides + ' shapes=' + ($counts -join ','))
Write-Output ('pptx=' + (Test-Path $pptx))
'''
    ps = ps.replace("__SPEC__", str(SPEC_JSON_ASCII)).replace("__TMP__", str(TMP))
    PS1.write_text(ps, encoding="ascii")


def svg_slide(slide: dict) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>',
             '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">'
             '<path d="M0,0 L10,4 L0,8 z" fill="#595959"/></marker></defs>']
    for e in slide["nodes"]:
        if e.get("textbox"):
            lines = e["text"].split("\n")
            weight = "bold" if e["bold"] else "normal"
            for k, ln in enumerate(lines):
                ty = e["y"] + e["size"] * 1.15 * (k + 1)
                parts.append(f'<text x="{e["x"]}" y="{ty:.1f}" font-family="{FONT}" font-size="{e["size"]}" '
                             f'font-weight="{weight}" fill="{e["fg"]}">{escape(ln)}</text>')
        else:
            rx = 10 if e["shape"] == 5 else 0
            stroke = e.get("line") or "none"
            parts.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" rx="{rx}" '
                         f'fill="{e["fill"]}" stroke="{stroke}"/>')
            lines = e["text"].split("\n")
            lh = e["size"] * 1.25
            y0 = e["y"] + e["h"] / 2 - lh * (len(lines) - 1) / 2 + e["size"] * 0.35
            weight = "bold" if e["bold"] else "normal"
            for k, ln in enumerate(lines):
                parts.append(f'<text x="{e["x"] + e["w"] / 2:.1f}" y="{y0 + k * lh:.1f}" text-anchor="middle" '
                             f'font-family="{FONT}" font-size="{e["size"]}" font-weight="{weight}" '
                             f'fill="{e["fg"]}">{escape(ln)}</text>')
    for e in slide["edges"]:
        parts.append(f'<line x1="{e["x1"]}" y1="{e["y1"]}" x2="{e["x2"]}" y2="{e["y2"]}" '
                     f'stroke="{e["color"]}" stroke-width="{e["width"]}" marker-end="url(#arrow)"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def write_inventory() -> int:
    rows = []
    for s in SPEC["slides"]:
        for z, n in enumerate(s["nodes"] + s["edges"], start=1):
            if "text" in n:
                rows.append([s["index"], n["id"], "textbox" if n.get("textbox") else f"shape{n['shape']}",
                             n["text"].replace("\n", " / "), n["x"], n["y"], n["w"], n["h"],
                             n.get("fill", ""), n.get("fg", ""), n.get("size", ""), z])
            else:
                rows.append([s["index"], n["id"], "connector", f"({n['x1']},{n['y1']})->({n['x2']},{n['y2']})",
                             "", "", "", "", n["color"], "", n["width"], z])
    with open(OUT / "v3_h01_elements.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slide", "element_id", "kind", "text_or_endpoints", "x_pt", "y_pt", "w_pt", "h_pt",
                    "fill_or_stroke", "font_color", "size_or_width", "z_order"])
        w.writerows(rows)
    return len(rows)


def normalize_pptx() -> None:
    """WPS 保存时给文本框写 spAutoFit；统一改 noAutofit，防止再次打开时几何被二次改写。"""
    pptx = OUT / "v3_h01_three_methods.pptx"
    tmp = pptx.with_suffix(".tmp.pptx")
    with zipfile.ZipFile(pptx) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.startswith("ppt/slides/slide") and item.filename.endswith(".xml"):
                data = data.replace(b"<a:spAutoFit/>", b"<a:noAutofit/>")
            dst.writestr(item, data)
    tmp.replace(pptx)


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _shape_text(sp: str) -> str:
    runs = re.findall(r"<a:t>(.*?)</a:t>", sp, flags=re.S)
    return _flat(unescape("".join(runs)))


def _off_ext(fragment: str) -> tuple[float, float, float, float]:
    off = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"/>', fragment)
    ext = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>', fragment)
    assert off and ext, "missing a:off/a:ext"
    return tuple(int(v) / 12700 for v in off.groups() + ext.groups())


def _paragraph_alignments(sp: str) -> list[str | None]:
    attrs = re.findall(r"<a:pPr\b([^>]*)>", sp)
    assert len(attrs) == len(re.findall(r"<a:p>", sp)), "paragraph/pPr count mismatch"
    out: list[str | None] = []
    for item in attrs:
        found = re.search(r'algn="([^"]+)"', item)
        out.append(found.group(1) if found else None)
    return out


def verify_pptx(pptx: Path) -> None:
    """逐形状校验几何、文本、段落对齐，并覆盖 18 条连接线（2026-10-31 20:06 复审 P1-1/P2-1/P2-2）。"""
    with zipfile.ZipFile(pptx) as z:
        slides = sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        assert len(slides) == 3, slides
        for i, name in enumerate(slides, 1):
            xml = z.read(name).decode("utf-8")
            assert "<p:pic>" not in xml, (name, "picture shape")
            assert "<a:blip" not in xml, (name, "bitmap reference")
            nodes = SPEC["slides"][i - 1]["nodes"]
            edges = SPEC["slides"][i - 1]["edges"]
            sps = re.findall(r"<p:sp>.*?</p:sp>", xml, flags=re.S)
            assert len(sps) == len(nodes), (name, len(sps), len(nodes))
            for sp, n in zip(sps, nodes):
                got = _off_ext(sp)
                want = (n["x"], n["y"], n["w"], n["h"])
                assert all(abs(a - b) <= 0.6 for a, b in zip(got, want)), (name, n["id"], got, want)
                assert _shape_text(sp) == _flat(n["text"]), (name, n["id"], _shape_text(sp)[:40])
                is_tb = 'txBox="1"' in sp
                assert is_tb == bool(n.get("textbox")), (name, n["id"], "txBox flag")
                algns = _paragraph_alignments(sp)
                assert algns, (name, n["id"], "no paragraphs")
                if n.get("textbox"):
                    assert all(a in (None, "l") for a in algns), (name, n["id"], algns)
                else:
                    assert all(a == "ctr" for a in algns), (name, n["id"], algns)
                assert "spAutoFit" not in sp, (name, n["id"], "spAutoFit")
            cxns = re.findall(r"<p:cxnSp>.*?</p:cxnSp>", xml, flags=re.S)
            assert len(cxns) == len(edges), (name, len(cxns), len(edges))
            for cs, e in zip(cxns, edges):
                got = _off_ext(cs)
                x1, y1, x2, y2 = e["x1"], e["y1"], e["x2"], e["y2"]
                want = (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                assert all(abs(a - b) <= 0.6 for a, b in zip(got, want)), (name, e["id"], got, want)
                xfrm = re.search(r"<a:xfrm([^>]*)>", cs)
                assert xfrm, (name, e["id"], "no xfrm")
                flips = xfrm.group(1)
                assert ('flipH="1"' in flips) == (x2 < x1), (name, e["id"], "flipH")
                assert ('flipV="1"' in flips) == (y2 < y1), (name, e["id"], "flipV")
                assert '<a:tailEnd type="arrow"/>' in cs, (name, e["id"], "arrowhead")
                ln = re.search(r'<a:ln w="(\d+)"', cs)
                assert ln and abs(int(ln.group(1)) / 12700 - e["width"]) <= 0.05, (
                    name, e["id"], "line width")
        media = [n for n in z.namelist() if n.startswith("ppt/media/")]
        assert not media, f"unexpected raster media: {media}"


def verify_svg(slide: dict) -> None:
    """SVG 锚点必须与 PPTX 对齐方式一一对应：文本框起点锚、盒内标签居中锚。"""
    path = OUT / Path(slide["png"]).with_suffix(".svg").name
    text = path.read_text(encoding="utf-8")
    items = re.findall(r'<text x="([\d.]+)" y="([\d.]+)"([^>]*)>(.*?)</text>', text)
    expected: list[tuple[float, bool, str]] = []
    for n in slide["nodes"]:
        for line in n["text"].split("\n"):
            if n.get("textbox"):
                expected.append((n["x"], False, line))
            else:
                expected.append((n["x"] + n["w"] / 2, True, line))
    assert len(items) == len(expected), (path.name, len(items), len(expected))
    for (x, _y, attrs, body), (want_x, centered, line) in zip(items, expected):
        assert abs(float(x) - want_x) <= 0.11, (path.name, x, want_x)
        assert ('text-anchor="middle"' in attrs) == centered, (path.name, line, attrs)
        assert unescape(body) == line, (path.name, body, line)


def verify_pngs() -> None:
    for s in SPEC["slides"]:
        png = OUT / s["png"]
        assert png.stat().st_size > 20_000, png
        data = png.read_bytes()[:24]
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        assert (width, height) == (2000, 1125), (png, width, height)


def verify() -> None:
    verify_pptx(OUT / "v3_h01_three_methods.pptx")
    for s in SPEC["slides"]:
        verify_svg(s)
    verify_pngs()
    print(f"verify: 3 slides, {len(SPEC['slides'])} PNG at 2000x1125, "
          f"per-shape text/alignment + 18 connectors checked")


def main() -> int:
    normalize()
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    SPEC_JSON.parent.mkdir(parents=True, exist_ok=True)
    SPEC_JSON.write_text(json.dumps(SPEC, ensure_ascii=False, indent=1), encoding="utf-8")
    SPEC_JSON_ASCII.write_text(json.dumps(SPEC, ensure_ascii=False, indent=1), encoding="utf-8")
    write_ps1()
    rc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(rc.stdout.strip())
    if rc.returncode != 0:
        print(rc.stderr.strip(), file=sys.stderr)
        return rc.returncode
    shutil.copy2(TMP / "v3_h01_three_methods.pptx", OUT / "v3_h01_three_methods.pptx")
    normalize_pptx()
    for s in SPEC["slides"]:
        shutil.copy2(TMP / s["png"], OUT / s["png"])
        (OUT / s["png"].replace(".png", ".svg")).write_text(svg_slide(s), encoding="utf-8")
    rows = write_inventory()
    verify()
    print(f"written: {OUT} (3 slides, 3 PNG, 3 SVG, {rows} inventory rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
