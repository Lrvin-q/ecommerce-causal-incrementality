"""统一出图样式。

为什么需要这一层
----------------
1. **中文字体**：Windows 默认 matplotlib 无 CJK 字体，直接画中文标题会变成一堆方框。
2. **一致性**：六种策略、四种因果方法在全文用固定配色，读者不用反复查图例。
3. **可追溯**：每张图强制带"数据来源 + 层级 + seed + R"脚注（AGENTS.md §6）。

用法
----
>>> from causal_growth.viz import save_fig, STRATEGY_COLORS
>>> fig, ax = plt.subplots()
>>> ax.plot(...)
>>> save_fig(fig, "itt_forest")
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # 无界面渲染，脚本/CI 安全

from pathlib import Path
from typing import Any

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

from causal_growth.io_utils import figures_dir, ensure_dir

__all__ = [
    "METHOD_COLORS",
    "METHOD_LABELS",
    "STRATEGY_COLORS",
    "STRATEGY_LABELS",
    "DEFAULT_DPI",
    "add_source_note",
    "apply_style",
    "available_cjk_font",
    "save_fig",
]

DEFAULT_DPI: int = 150

#: Windows 常见中文字体，按优先级排列
_CJK_CANDIDATES: tuple[str, ...] = (
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "DengXian",
    "SimSun",
    "Arial Unicode MS",
)

#: 六种策略固定配色（方案 §2.4 主线四）
STRATEGY_COLORS: dict[str, str] = {
    "no_coupon": "#9E9E9E",       # 不发券 —— 灰
    "all": "#E53935",             # 全量发券 —— 红（浪费预算的极端）
    "random": "#FB8C00",          # 随机 B 预算 —— 橙
    "target_greedy": "#1E88E5",   # 定向-贪心 —— 蓝（基准）
    "target_knapsack": "#0D47A1", # 定向-背包 —— 深蓝（最优基准）
    "oracle": "#212121",          # 真值最优 —— 黑（上界）
}

STRATEGY_LABELS: dict[str, str] = {
    "no_coupon": "不发券",
    "all": "全量发券",
    "random": "随机（预算 B）",
    "target_greedy": "定向-贪心",
    "target_knapsack": "定向-背包",
    "oracle": "真值最优（上界）",
}

#: 四种观察性因果方法固定配色（方案 §2.4 主线三）
METHOD_COLORS: dict[str, str] = {
    "naive": "#E53935",
    "psm": "#FB8C00",
    "ipw": "#1E88E5",
    "dr": "#2E7D32",
    "itt": "#6A1B9A",
}

METHOD_LABELS: dict[str, str] = {
    "naive": "Naive 差分",
    "psm": "PSM 倾向得分匹配",
    "ipw": "IPW 逆概率加权",
    "dr": "DR 双稳健",
    "itt": "ITT（随机实验金标准）",
}

_STYLE_APPLIED = False


def available_cjk_font() -> str | None:
    """返回本机可用的第一个中文字体名；没有则返回 None（调用方应降级并告警）。"""
    installed = {f.name for f in fm.fontManager.ttflist}
    for name in _CJK_CANDIDATES:
        if name in installed:
            return name
    return None


def apply_style(*, force: bool = False) -> str | None:
    """设置全局绘图样式（幂等）。返回实际采用的中文字体名。"""
    global _STYLE_APPLIED
    if _STYLE_APPLIED and not force:
        return available_cjk_font()

    font = available_cjk_font()
    family = [font, "DejaVu Sans"] if font else ["DejaVu Sans"]

    plt.rcParams.update(
        {
            "font.sans-serif": family,
            "font.family": "sans-serif",
            "axes.unicode_minus": False,  # 负号显示为正常减号，否则中文环境下是方框
            "figure.dpi": 110,
            "savefig.dpi": DEFAULT_DPI,
            "savefig.bbox": "tight",
            "axes.grid": True,
            "grid.alpha": 0.3,
            "grid.linestyle": "--",
            "axes.axisbelow": True,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.autolayout": False,
        }
    )
    _STYLE_APPLIED = True
    return font


# 导入即生效：任何模块只要 import 了 viz，出图就不会乱码
apply_style()


def add_source_note(
    fig: Any,
    note: str,
    *,
    data_label: str = "合成数据 / 已知 DGP（非真实企业数据）",
    reserve_bottom: float = 0.19,
) -> None:
    """在图底部加来源脚注（AGENTS.md §6 强制要求）。

    两件事必须做对：
    1. **不要重复数据来源标注**——``note`` 传的是 seed/层级/R 等附加信息，
       来源标注由本函数统一加，脚本里不要再手打一遍。
    2. **给脚注留出底部空间**，否则它会压住 x 轴标签（这是最容易漏的排版 bug）。
       ``reserve_bottom`` 要同时容下"轴标签高度 + 脚注高度 + 间隙"。
    """
    fig.text(
        0.005,
        0.012,
        f"数据来源：{data_label}　|　{note}",
        fontsize=7,
        color="#666666",
        ha="left",
        va="bottom",
    )
    try:
        current = float(fig.subplotpars.bottom)
        if current < reserve_bottom:
            fig.subplots_adjust(bottom=reserve_bottom)
    except (AttributeError, ValueError):
        # 非 plt.subplots 构造的 Figure 没有 subplotpars，跳过即可
        pass


def save_fig(
    fig: Any,
    name: str,
    *,
    subdir: str | None = None,
    dpi: int = DEFAULT_DPI,
    close: bool = True,
) -> Path:
    """把图存到 ``outputs/figures/[subdir/]name.png`` 并返回路径。"""
    filename = name if name.lower().endswith(".png") else f"{name}.png"
    target_dir = figures_dir() if subdir is None else figures_dir(subdir)
    ensure_dir(target_dir)
    path = target_dir / filename
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    if close:
        plt.close(fig)
    return path


def label_ci(mean: float, lo: float, hi: float, *, fmt: str = "{:.3f}") -> str:
    """把"点估计 + 95% 区间"格式化成报告可用的一行文字。"""
    return f"{fmt.format(mean)} [{fmt.format(lo)}, {fmt.format(hi)}]"


def symlog_floor(values: np.ndarray) -> float:
    """给可能为 0 的数值列一个安全的对数坐标下限。"""
    positive = values[np.isfinite(values) & (values > 0)]
    return float(positive.min()) if positive.size else 1e-6
