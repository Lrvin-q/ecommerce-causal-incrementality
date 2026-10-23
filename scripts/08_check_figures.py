r"""程序化版式检查：对论文组图做**墨迹级碰撞检测**。

为什么不能用"外接矩形"判遮挡
----------------------------
最初版本对每个 artist 取 ``get_window_extent()`` 当作"数据占据的区域"，这条
思路有三个致命缺陷，实测会产生数百处误报：

1. ``ax.patch``（坐标区底色）和 ``ax.spines``（边框）都是 ``Patch`` 子类，
   会被误当成数据。
2. 对数轴上柱子的 bbox 从 0 一直延伸到 ``-26260px``，若不裁剪到 ``ax.bbox``，
   页面里任何一行文字都会"覆盖柱子"。
3. ``Line2D.get_window_extent()`` 返回的是**整条序列的外接矩形**，不是笔迹。
   最典型的是 ``ax.bar(yerr=..., capsize=2)``：六根柱的误差棒帽会被画成**同一个**
   ``Line2D``，其 bbox 几乎等于整个面板，于是六个数值标签全部被判成"遮挡数据"。

因此本版改用**墨点集合**：把折线的顶点与中点、柱子的路径顶点、散点的偏移量
统统变换到显示坐标，得到一张二维点云；再看某段文字/图例的包围盒内落了多少个
点。这样"遮挡"变成"点落在框里"，与外接矩形无关。

检查项
------
C1 图例包围盒内落在数据点 → error
C2 图内文字包围盒内落在数据点 → error
C3 文字 / 图例两两相交 → error
C4 文字或图例超出画布（被裁切）→ error
C5 轴标签压刻度 → warning

约定
----
* 一个包围盒内落入 **≥ ``MIN_HITS`` 个墨点**才判为遮挡（单个顶点多为角点贴边）。
* 坐标为 ``ax.axison == False`` 的流程图/示意图跳过 C1、C2。
* 全部数据点先裁剪到 ``ax.bbox``，坐标区之外的不可见。

用法
----
    $env:PYTHONUTF8='1'
    .\.venv\Scripts\python.exe scripts\08_check_figures.py --strict
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import Collection
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.text import Text

FIGURE_SCRIPT = ROOT / "scripts" / "05_paper_figures.py"
REPORT = ROOT / "paper" / "_figure_lint.md"

#: 文字/图例包围盒内落入多少个墨点才算"遮挡"
MIN_HITS = 3
#: 文字之间允许的极小重叠（pt²），用于吸收抗锯齿与斜体字形外扩
TEXT_TOL = 6.0


# --------------------------------------------------------------------------- #
# 几何工具
# --------------------------------------------------------------------------- #
def _area(a: Any, b: Any) -> float:
    x0, x1 = max(a.x0, b.x0), min(a.x1, b.x1)
    y0, y1 = max(a.y0, b.y0), min(a.y1, b.y1)
    return 0.0 if (x1 <= x0 or y1 <= y0) else (x1 - x0) * (y1 - y0)


def _renderer(fig: plt.Figure):
    fig.canvas.draw()
    return fig.canvas.get_renderer()


def _to_display(ax: plt.Axes, xy: np.ndarray) -> np.ndarray:
    """数据坐标 → 显示坐标。"""
    arr = np.asarray(xy, dtype=float).reshape(-1, 2)
    if arr.size == 0:
        return np.empty((0, 2))
    with np.errstate(invalid="ignore", over="ignore"):
        return ax.transData.transform(arr)


def _data_ink_points(ax: plt.Axes) -> np.ndarray:
    """收集坐标区内所有"墨点"（显示坐标），并裁剪到 ax.bbox。"""
    chunks: list[np.ndarray] = []
    spines = {id(s) for s in ax.spines.values()}

    for ch in ax.get_children():
        if not ch.get_visible():
            continue
        # ① 坐标区底色与四条边框不是数据
        if ch is ax.patch or id(ch) in spines:
            continue
        if isinstance(ch, (Text, Legend)):
            continue

        try:
            if isinstance(ch, Line2D):
                xy = np.asarray(ch.get_xydata(), dtype=float)
                if xy.size == 0:
                    continue
                disp = _to_display(ax, xy)
                chunks.append(disp)
                # 折线：补中点，避免"文字压在长线段上但没有顶点落入"而漏判
                if len(disp) > 1:
                    chunks.append((disp[:-1] + disp[1:]) / 2.0)
            elif isinstance(ch, Patch):
                path = ch.get_path()
                verts = path.transformed(ch.get_patch_transform()).vertices
                if verts.size:
                    disp = _to_display(ax, verts)
                    chunks.append(disp)
                    # 柱子：补几何中心，代表柱体的"体"
                    finite = disp[np.isfinite(disp).all(axis=1)]
                    if len(finite):
                        chunks.append(np.array([[finite[:, 0].mean(),
                                                 finite[:, 1].mean()]]))
            elif isinstance(ch, Collection):
                off = ch.get_offsets()
                if off is not None and len(off):
                    chunks.append(_to_display(ax, np.asarray(off)))
        except Exception:
            # 某些 artist 的变换不可用（如空的 PathCollection），跳过即可
            continue

    if not chunks:
        return np.empty((0, 2))

    pts = np.vstack([c for c in chunks if c.size]).astype(float)
    pts = pts[np.isfinite(pts).all(axis=1)]
    # ② 裁剪到坐标区：对数轴上柱子会延伸到负无穷方向
    bb = ax.bbox
    keep = ((pts[:, 0] >= bb.x0) & (pts[:, 0] <= bb.x1)
            & (pts[:, 1] >= bb.y0) & (pts[:, 1] <= bb.y1))
    return pts[keep]


def _hits(pts: np.ndarray, bb: Any) -> int:
    """包围盒内落入的墨点数。"""
    if pts.size == 0:
        return 0
    inside = ((pts[:, 0] >= bb.x0) & (pts[:, 0] <= bb.x1)
              & (pts[:, 1] >= bb.y0) & (pts[:, 1] <= bb.y1))
    return int(inside.sum())


def _inner_texts(ax: plt.Axes) -> list[tuple[str, Text]]:
    """图内文字（排除标题、轴标签、刻度标签）。"""
    skip = {id(ax.title), id(ax.xaxis.label), id(ax.yaxis.label)}
    skip.update(id(t) for t in ax.get_xticklabels())
    skip.update(id(t) for t in ax.get_yticklabels())
    out: list[tuple[str, Text]] = []
    for t in ax.texts:
        if not t.get_visible() or id(t) in skip:
            continue
        s = t.get_text().strip()
        if not s:
            continue
        short = s[:16] + "…" if len(s) > 16 else s
        out.append((f"文字「{short}」", t))
    return out


# --------------------------------------------------------------------------- #
# 单图检查
# --------------------------------------------------------------------------- #
def check_figure(fig: plt.Figure, name: str) -> list[dict[str, Any]]:
    rend = _renderer(fig)
    issues: list[dict[str, Any]] = []
    fig_bb = fig.bbox

    def add(level: str, code: str, msg: str) -> None:
        issues.append({"figure": name, "level": level, "code": code, "message": msg})

    for ai, ax in enumerate(fig.axes):
        tag = f"子图{ai + 1}"
        # ③ 流程图/示意图没有数据轴，跳过墨迹比对
        if not ax.axison:
            continue

        pts = _data_ink_points(ax)
        leg = ax.get_legend()

        # ---- C1 图例 vs 数据 ----
        if leg is not None:
            lb = leg.get_window_extent(rend)
            h = _hits(pts, lb)
            if h >= MIN_HITS:
                add("error", "C1", f"{tag} 图例框内落入 {h} 个数据墨点（遮挡曲线/柱/点）")
            if lb.x0 < fig_bb.x0 - 1 or lb.x1 > fig_bb.x1 + 1 \
                    or lb.y0 < fig_bb.y0 - 1 or lb.y1 > fig_bb.y1 + 1:
                add("warning", "C4", f"{tag} 图例超出画布边界，可能被裁切")

        # ---- C2 图内文字 vs 数据 ----
        texts = _inner_texts(ax)
        for tname, t in texts:
            tb = t.get_window_extent(rend)
            h = _hits(pts, tb)
            if h >= MIN_HITS:
                add("error", "C2", f"{tname} 包围盒内落入 {h} 个数据墨点（遮挡）")
            if tb.x0 < fig_bb.x0 - 1 or tb.x1 > fig_bb.x1 + 1 \
                    or tb.y0 < fig_bb.y0 - 1 or tb.y1 > fig_bb.y1 + 1:
                add("error", "C4", f"{tname} 超出画布边界（被裁切）")

        # ---- C3 文字/图例互相重叠 ----
        objs: list[tuple[str, Any]] = list(texts)
        if leg is not None:
            objs.append(("图例", leg))
        for i in range(len(objs)):
            for j in range(i + 1, len(objs)):
                n1, o1 = objs[i]
                n2, o2 = objs[j]
                a = _area(o1.get_window_extent(rend), o2.get_window_extent(rend))
                if a > TEXT_TOL:
                    add("error", "C3", f"{n1} 与 {n2} 重叠（{a:.0f}pt²）")

        # ---- C5 轴标签压刻度 ----
        ticks = [t for t in ax.get_xticklabels() + ax.get_yticklabels()
                 if t.get_visible() and t.get_text().strip()]
        for lab, nm in ((ax.xaxis.label, "X 轴标签"), (ax.yaxis.label, "Y 轴标签")):
            if not lab.get_text().strip():
                continue
            lb2 = lab.get_window_extent(rend)
            for tk in ticks:
                a = _area(lb2, tk.get_window_extent(rend))
                if a > TEXT_TOL:
                    add("warning", "C5",
                        f"{nm} 与刻度「{tk.get_text()}」重叠（{a:.0f}pt²）")

    # 同一张图内子图编号对诊断没用，补上图名
    for it in issues:
        it["message"] = f"{it['figure']} {it['message']}"
    return issues


# --------------------------------------------------------------------------- #
# 驱动
# --------------------------------------------------------------------------- #
def load_figure_module() -> Any:
    spec = importlib.util.spec_from_file_location("paper_figures", FIGURE_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {FIGURE_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["paper_figures"] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="论文组图的程序化版式检查（墨迹级）")
    ap.add_argument("--strict", action="store_true", help="存在 error 时以非零退出码结束")
    args = ap.parse_args(argv)

    collected: list[dict[str, Any]] = []
    mod = load_figure_module()
    original: Callable[..., Any] = mod._finish

    def hooked(fig: plt.Figure, name: str, note: str):
        issues = check_figure(fig, name)
        collected.extend(issues)
        n_err = sum(1 for i in issues if i["level"] == "error")
        print(f"    [lint] {name:<22} " + ("OK" if n_err == 0 else f"{n_err} error"))
        return original(fig, name, note)

    mod._finish = hooked
    print("[1/2] 重新出图并逐张检查 ...")
    mod.main()
    mod._finish = original

    n_err = sum(1 for i in collected if i["level"] == "error")
    n_warn = len(collected) - n_err
    lines = ["# 组图程序化版式检查（墨迹级）", "",
             f"- 检查项：C1 图例遮数据 / C2 文字遮数据 / C3 文字互叠 / C4 出界裁切 / C5 轴标签压刻度",
             f"- 判定口径：包围盒内落入 ≥ {MIN_HITS} 个数据墨点才算遮挡；文字互叠容忍 {TEXT_TOL}pt²",
             f"- 结论：**error {n_err} 处，warning {n_warn} 处**", ""]
    if collected:
        lines += ["| 图 | 级别 | 项 | 说明 |", "|---|---|---|---|"]
        for it in collected:
            lines.append(f"| {it['figure']} | {it['level']} | {it['code']} | {it['message']} |")
    else:
        lines.append("未发现任何遮挡、重叠或裁切。")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[2/2] 报告 -> {REPORT.relative_to(ROOT)}   error={n_err} warning={n_warn}")
    return 1 if (args.strict and n_err) else 0


if __name__ == "__main__":
    raise SystemExit(main())
