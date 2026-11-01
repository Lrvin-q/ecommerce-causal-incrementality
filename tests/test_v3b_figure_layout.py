"""图形修订的反例：不能让美化改掉数值，也不能漏画定向臂。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def renderer():
    spec = importlib.util.spec_from_file_location("figure_refresh_test", ROOT / "scripts/refresh_v3b_figures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.configure()
    yield module
    plt.close("all")


def test_overflow_is_rejected_before_export(renderer):
    fig, ax = renderer.canvas(2)
    renderer.card(ax, .2, .2, .02, .02, "这段文字不能挤进一个窄框")
    with pytest.raises(ValueError, match="框内文字溢出"):
        renderer.save(fig, "negative_overflow", diagram=True)


def test_numeric_mutation_is_rejected(renderer, monkeypatch):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])

    def corrupt(fig, name):
        fig.axes[0].lines[0].set_ydata([0, 2])

    monkeypatch.setattr(renderer, "style_result", corrupt)
    with pytest.raises(AssertionError, match="排版改变了数据图元"):
        renderer.save(fig, "negative_numeric_mutation")


def test_formula_glyphs_render_without_missing_characters(renderer):
    fig, ax = renderer.canvas(2)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        renderer.card(ax, .1, .1, .8, .8, r"潜在响应 $p_0(X),p_1(X)$",
                      r"$G_1=\lfloor QV\rfloor$；复购金额 $G_2$")
        fig.canvas.draw()
    assert not [w for w in caught if "Glyph" in str(w.message)]


def test_cost_histogram_contains_random_and_targeted_arms(renderer, monkeypatch):
    module = renderer.load("54_v3b_figures_batch3.py")
    observed = []

    def capture(fig, name, note, caption):
        observed.extend(fig.axes[2].get_legend_handles_labels()[1])
        # 两个臂各有 30 个箱；原来的 targeted 拼写错误会只画 30 个。
        assert len(fig.axes[2].patches) == 60

    monkeypatch.setattr(module, "_finish", capture)
    module.fig12_ope()
    assert observed == ["同预算随机", "定向"]
