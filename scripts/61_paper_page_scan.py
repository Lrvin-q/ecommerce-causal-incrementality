"""逐页版面扫描：把 H03「逐页视觉」里能脚本判的部分落成凭据。

回答的问题：有没有空白页、正文版心是否一致、哪些页以整幅横线起页（`longtable` 续页的表头重复）。
用法：
    PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/61_paper_page_scan.py [main.pdf]

输出：逐页 top/bottom/left/right 墨迹边界（100 dpi 像素）、墨迹占比、是否以横线起页。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "out/scratch/v3_paper_build/main.pdf"
DPI = 100
WIDE_RULE_SHARE = 0.60
HEADER_ROWS = 12


def rasterize(pdf: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("p-*.png"):
        old.unlink()
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", str(pdf), str(out_dir / "p")],
                   check=True)
    return sorted(out_dir.glob("p-*.png"))


def scan(page: Path) -> dict:
    arr = np.asarray(Image.open(page).convert("L"))
    ink = arr < 200
    if not ink.any():
        return {"page": page.name, "blank": True}
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    top = int(rows[0])
    head = ink[top:top + HEADER_ROWS]
    return {
        "page": page.name,
        "blank": False,
        "width": int(arr.shape[1]),
        "top": top,
        "bottom": int(rows[-1]),
        "left": int(cols[0]),
        "right": int(cols[-1]),
        "dark": float(ink.mean()),
        "starts_rule": bool((head.sum(axis=1) > WIDE_RULE_SHARE * arr.shape[1]).any()),
    }


def main() -> int:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf.exists():
        print(f"PDF 不存在：{pdf}（先跑 bash scripts/52_paper_gates.sh --build）")
        return 2
    pages = rasterize(pdf, ROOT / "out/scratch/h03_pages/scan")
    rows = [scan(p) for p in pages]
    blanks = [r["page"] for r in rows if r["blank"]]
    rows = [r for r in rows if not r["blank"]]

    print(f"{pdf} 共 {len(pages)} 页；空白页：{blanks or '无'}")
    print("页   宽   顶    底    左   右    墨迹   横线起页")
    for r in rows:
        print(f"{r['page'][-6:-4]} {r['width']:4d} {r['top']:4d} {r['bottom']:5d} "
              f"{r['left']:4d} {r['right']:4d} {r['dark']:.4f} "
              f"{'RULE' if r['starts_rule'] else ''}")
    rule_pages = [r["page"][-6:-4] for r in rows if r["starts_rule"]]
    print(f"以整幅横线起页（longtable 续页）：{rule_pages}")
    print(f"左界取值：{sorted({r['left'] for r in rows})}；"
          f"右界取值：{sorted({r['right'] for r in rows})}")
    print(f"顶界取值：{sorted({r['top'] for r in rows})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
