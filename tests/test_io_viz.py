"""落盘与出图测试。

守两件事：
1. **中文不乱码**：Windows 下 CSV 用 utf-8-sig、图用 CJK 字体，否则交付物直接报废。
2. **产物可追溯**：路径必须由 io_utils 统一下发，RunPaths 必须隔离不同 run。
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from causal_growth import io_utils as io
from causal_growth.viz import (
    METHOD_COLORS,
    STRATEGY_COLORS,
    STRATEGY_LABELS,
    add_source_note,
    apply_style,
    available_cjk_font,
    save_fig,
)


class TestPaths:
    def test_project_root_is_repo_root(self) -> None:
        assert (io.PROJECT_ROOT / "pyproject.toml").exists()
        assert (io.PROJECT_ROOT / "项目方案思路.md").exists()

    def test_standard_dirs_resolve_under_root(self) -> None:
        for fn in (io.data_dir, io.outputs_dir, io.figures_dir, io.tables_dir, io.runs_dir):
            assert fn().is_relative_to(io.PROJECT_ROOT)
        assert io.reports_dir().name == "reports"
        assert io.configs_dir("base.yaml").name == "base.yaml"

    def test_ensure_dir_idempotent(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        assert io.ensure_dir(target) == target
        assert io.ensure_dir(target).is_dir()


class TestIO:
    def test_csv_roundtrip_with_chinese(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"策略": ["不发券", "定向-贪心"], "净增量利润": [0.0, 12.5]})
        path = io.write_csv(df, tmp_path / "t.csv")
        back = io.read_csv(path)
        assert list(back.columns) == list(df.columns)
        assert back["策略"].tolist() == ["不发券", "定向-贪心"]
        assert back["净增量利润"].tolist() == pytest.approx([0.0, 12.5])

    def test_csv_has_bom_for_excel(self, tmp_path: Path) -> None:
        path = io.write_csv(pd.DataFrame({"中文": [1]}), tmp_path / "t.csv")
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    def test_json_roundtrip_keeps_chinese(self, tmp_path: Path) -> None:
        obj = {"标注": "合成数据 / 已知 DGP", "n": 1, "nested": {"λ": 0.5}}
        path = io.save_json(obj, tmp_path / "m.json")
        assert "合成数据" in path.read_text(encoding="utf-8")  # 不是 \uXXXX 转义
        assert io.read_json(path) == obj

    def test_file_sha256_deterministic(self, tmp_path: Path) -> None:
        p = io.write_text("净增量贡献利润", tmp_path / "x.txt")
        assert io.file_sha256(p) == io.file_sha256(p)

    def test_file_sha256_detects_change(self, tmp_path: Path) -> None:
        p1 = io.write_text("a", tmp_path / "1.txt")
        p2 = io.write_text("b", tmp_path / "2.txt")
        assert io.file_sha256(p1) != io.file_sha256(p2)


class TestRunPaths:
    def test_run_dirs_are_isolated(self) -> None:
        r1, r2 = io.RunPaths("test_run_a"), io.RunPaths("test_run_b")
        assert r1.root != r2.root
        assert r1.table("x").parent.name == "tables"
        assert r1.figure("y").suffix == ".png"
        assert r1.meta_json().name == "meta.json"

    def test_table_and_figure_paths_inside_run_root(self) -> None:
        run = io.RunPaths("test_run_paths")
        assert run.table("t1").is_relative_to(run.root)
        assert run.figure("f1").is_relative_to(run.root)


class TestViz:
    def test_cjk_font_available(self) -> None:
        font = available_cjk_font()
        assert font is not None, "本机找不到中文字体，所有中文图表都会显示为方框"
        assert apply_style() == font

    def test_palette_covers_all_required_keys(self) -> None:
        expected = {"no_coupon", "all", "random", "target_greedy", "target_knapsack", "oracle"}
        assert set(STRATEGY_COLORS) == expected
        assert set(STRATEGY_LABELS) == expected
        assert set(METHOD_COLORS) == {"naive", "psm", "ipw", "dr", "itt"}

    def test_save_fig_writes_png(self) -> None:
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([1, 2, 3], [1, 4, 9])
        add_source_note(fig, "层级 L0 | seed 20240101 | R=1")
        path = save_fig(fig, "test_smoke_plot", subdir="_test")
        try:
            assert path.exists() and path.suffix == ".png"
            assert path.stat().st_size > 1000
            assert path.parent.name == "_test"
        finally:
            path.unlink(missing_ok=True)
            (path.parent).rmdir()

    def test_chinese_text_renders_without_missing_glyph(self) -> None:
        """这是最容易在交付前夜翻车的地方：中文标题变方框。"""
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.set_title("净增量贡献利润：定向-贪心 vs 真值最优")
        ax.set_xlabel("混淆强度 λ")
        ax.set_ylabel("偏差（元/人）")
        ax.legend(["背包"], loc="best")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig.canvas.draw()
        plt.close(fig)

        glyph_issues = [str(w.message) for w in caught if "missing from font" in str(w.message)]
        assert glyph_issues == [], f"中文渲染缺字：{glyph_issues}"
