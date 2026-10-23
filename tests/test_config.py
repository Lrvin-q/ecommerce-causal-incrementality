"""配置层测试。

重点守两类错误：
1. **硬约束失效**：``p0 + tau_max > 1`` 这类会让整个 DGP 概率越界的配置必须抛错，
   不能"警告后继续跑"（AGENTS.md §3.6 失败要响）。
2. **点号路径与覆盖**：重复实验/敏感性扫描靠 ``with_overrides`` 生成变体配置，
   覆盖逻辑错了会导致扫描结果全部污染。
"""

from __future__ import annotations

import pytest

from causal_growth.config import Config, ConfigError, load_config, validate_config


@pytest.fixture(scope="module")
def cfg() -> Config:
    return load_config()


class TestLoad:
    def test_base_yaml_loads_and_validates(self, cfg: Config) -> None:
        assert cfg.get("project.master_seed") == 20240101
        assert cfg.get("business.baseline_conversion") == pytest.approx(0.10)
        assert cfg.get("dgp.n_users") == 200000

    def test_required_sections_present(self, cfg: Config) -> None:
        for section in (
            "project",
            "business",
            "windows",
            "experiment",
            "dgp",
            "dirty",
            "budget",
            "evaluation",
        ):
            assert cfg.get(section) is not None, f"缺少配置段 {section}"

    def test_missing_file_raises(self) -> None:
        with pytest.raises(ConfigError, match="不存在"):
            load_config("configs/definitely_not_here.yaml")


class TestAccess:
    def test_dotted_get(self, cfg: Config) -> None:
        assert cfg.get("windows.convert_days") == 7
        assert cfg.get("windows.profit_days") == 30

    def test_get_default(self, cfg: Config) -> None:
        assert cfg.get("no.such.key", "fallback") == "fallback"

    def test_require_raises_on_missing(self, cfg: Config) -> None:
        with pytest.raises(ConfigError, match="缺少必需配置项"):
            cfg.require("dgp.l9.imaginary")

    def test_section_returns_dict(self, cfg: Config) -> None:
        sec = cfg.section("experiment.guardrail")
        assert isinstance(sec, dict)
        assert sec["metric"] == "refund_rate"

    def test_section_on_scalar_raises(self, cfg: Config) -> None:
        with pytest.raises(ConfigError, match="不是配置段"):
            cfg.section("project.name")

    def test_config_is_mapping(self, cfg: Config) -> None:
        assert "project" in cfg
        assert len(cfg) > 0


class TestOverrides:
    def test_override_changes_value_only(self, cfg: Config) -> None:
        variant = cfg.with_overrides({"business.baseline_conversion": 0.12})
        assert variant.get("business.baseline_conversion") == pytest.approx(0.12)
        # 原配置不受影响（不可变语义）
        assert cfg.get("business.baseline_conversion") == pytest.approx(0.10)

    def test_nested_override_creates_path(self, cfg: Config) -> None:
        variant = cfg.with_overrides({"dgp.l3.new_key": 42})
        assert variant.get("dgp.l3.new_key") == 42

    def test_override_rejects_scalar_parent(self, cfg: Config) -> None:
        with pytest.raises(ConfigError, match="无法在非配置段上覆盖"):
            cfg.with_overrides({"project.name.deep": 1})

    def test_override_then_validate_catches_violation(self, cfg: Config) -> None:
        bad = cfg.with_overrides({"business.baseline_conversion": 0.95})
        with pytest.raises(ConfigError, match="概率尺度越界"):
            validate_config(bad)


class TestHash:
    def test_hash_is_stable_and_short(self, cfg: Config) -> None:
        assert cfg.hash() == cfg.hash()
        assert len(cfg.hash()) == 8
        assert all(c in "0123456789abcdef" for c in cfg.hash())

    def test_hash_changes_with_content(self, cfg: Config) -> None:
        variant = cfg.with_overrides({"business.baseline_conversion": 0.11})
        assert variant.hash() != cfg.hash()


class TestHardConstraints:
    """每一条都是一个真实的翻车方式，必须抛错而不是静默通过。"""

    def test_probability_must_be_strictly_inside_unit_interval(self, cfg: Config) -> None:
        for key, bad in (
            ("business.baseline_conversion", 0.0),
            ("business.redemption_rate", 1.0),
            ("business.refund_rate", -0.01),
        ):
            with pytest.raises(ConfigError):
                validate_config(cfg.with_overrides({key: bad}))

    def test_p0_plus_tau_cannot_exceed_one(self, cfg: Config) -> None:
        with pytest.raises(ConfigError, match="概率尺度越界"):
            validate_config(
                cfg.with_overrides(
                    {"business.baseline_conversion": 0.90, "business.coupon_max_effect": 0.15}
                )
            )

    def test_coupon_face_values_must_be_positive(self, cfg: Config) -> None:
        with pytest.raises(ConfigError, match="coupon_face_values"):
            validate_config(cfg.with_overrides({"business.coupon_face_values": [5, 0, 20]}))

    def test_alpha_and_power_bounds(self, cfg: Config) -> None:
        for key, bad in (("experiment.alpha", 0.0), ("experiment.power", 1.5)):
            with pytest.raises(ConfigError):
                validate_config(cfg.with_overrides({key: bad}))

    def test_windows_must_be_ordered(self, cfg: Config) -> None:
        """利润成熟窗口不能短于转化窗口，否则转化用户来不及成熟出利润。"""
        with pytest.raises(ConfigError, match="利润成熟窗口"):
            validate_config(
                cfg.with_overrides({"windows.convert_days": 30, "windows.profit_days": 7})
            )

    def test_split_sizes_cannot_overlap(self, cfg: Config) -> None:
        with pytest.raises(ConfigError, match="必须 < 1"):
            validate_config(
                cfg.with_overrides({"evaluation.test_size": 0.7, "evaluation.val_size": 0.4})
            )

    def test_guardrail_margin_must_be_positive(self, cfg: Config) -> None:
        with pytest.raises(ConfigError, match="noninferiority_margin"):
            validate_config(cfg.with_overrides({"experiment.guardrail.noninferiority_margin": 0.0}))

    def test_missing_section_raises(self, cfg: Config) -> None:
        stripped = Config(
            {k: v for k, v in cfg.to_dict().items() if k != "budget"}, name="stripped"
        )
        with pytest.raises(ConfigError, match="缺少必需配置段"):
            validate_config(stripped)


class TestSoftRanges:
    def test_in_range_produces_no_warning(self, cfg: Config) -> None:
        report = validate_config(cfg)
        assert report.warnings == []

    def test_out_of_range_warns_but_does_not_raise(self, cfg: Config) -> None:
        """敏感性扫描会故意越界，所以软区间只能提示，不能抛错。"""
        variant = cfg.with_overrides({"business.redemption_rate": 0.95})
        report = validate_config(variant)
        assert len(report.warnings) == 1
        assert "核销率" in report.warnings[0]

    def test_validation_report_is_truthy(self, cfg: Config) -> None:
        assert validate_config(cfg)
