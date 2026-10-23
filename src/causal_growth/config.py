"""配置加载、点号访问与硬约束校验。

设计原则
--------
* **所有业务参数来自 YAML**，代码里不允许出现业务 magic number（见 AGENTS.md §3.2）。
* 校验分两级：
  - **硬约束**（违反即抛 ``ConfigError``）：数学上不可能或会让整个分析失效的取值，
    例如 ``p0 + tau_max > 1``、概率越界、``test_size + val_size >= 1``。
  - **软区间**（只收集 warning，写入 run meta）：方案附录 A.1 给出的"建议值范围"。
    敏感性扫描会**故意**越界，所以软区间不能抛异常，只能提示。

用法
----
>>> cfg = load_config("configs/base.yaml")
>>> cfg.require("dgp.l0.p0")          # 缺失即抛
>>> cfg.get("budget.total", 0.0)      # 带默认值
>>> cfg.hash()                        # 8 位短哈希，写进 run meta 做追溯
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "Config",
    "ConfigError",
    "ValidationReport",
    "load_config",
    "validate_config",
]


class ConfigError(ValueError):
    """配置缺失或违反硬约束。"""


class Config(Mapping[str, Any]):
    """只读配置树，支持点号路径访问。"""

    def __init__(self, data: Mapping[str, Any], *, name: str = "config") -> None:
        object.__setattr__(self, "_data", _freeze(dict(data)))
        object.__setattr__(self, "_name", name)

    # ---------------- 基本访问 ----------------
    @property
    def name(self) -> str:
        return self._name

    def __getitem__(self, key: str) -> Any:
        value = self._data[key]
        return Config(value, name=f"{self._name}.{key}") if isinstance(value, dict) else value

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"Config(name={self._name!r}, keys={list(self._data)})"

    # ---------------- 点号路径 ----------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return Config(node, name=dotted) if isinstance(node, dict) else node

    def require(self, dotted: str) -> Any:
        sentinel = object()
        value = self.get(dotted, sentinel)
        if value is sentinel:
            raise ConfigError(f"缺少必需配置项：{dotted!r}（在 {self._name} 中）")
        return value

    def section(self, dotted: str) -> dict[str, Any]:
        value = self.require(dotted)
        if not isinstance(value, Config):
            raise ConfigError(f"{dotted!r} 不是配置段（实际类型 {type(value).__name__}）")
        return _thaw(value.to_dict())

    # ---------------- 派生 ----------------
    def to_dict(self) -> dict[str, Any]:
        return _thaw(self._data)

    def hash(self, length: int = 8) -> str:
        """配置内容哈希（用于 run meta 追溯与可复现性核对）。"""
        blob = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:length]

    def with_overrides(self, overrides: Mapping[str, Any]) -> Config:
        """返回覆盖后的新配置；键支持点号路径（如 ``{"dgp.l0.p0": 0.12}``）。"""
        data = self.to_dict()
        for key, value in overrides.items():
            node = data
            parts = key.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
                if not isinstance(node, dict):
                    raise ConfigError(f"无法在非配置段上覆盖：{key!r}")
            node[parts[-1]] = value
        return Config(data, name=f"{self._name}+override")


def _freeze(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _freeze(v) for k, v in node.items()}
    if isinstance(node, list):
        return tuple(_freeze(v) for v in node)
    return node


def _thaw(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _thaw(v) for k, v in node.items()}
    if isinstance(node, tuple):
        return [_thaw(v) for v in node]
    return node


# --------------------------------------------------------------------------- #
# 加载
# --------------------------------------------------------------------------- #
def load_config(
    path: Path | str | None = None,
    *,
    overrides: Mapping[str, Any] | None = None,
    validate: bool = True,
) -> Config:
    """加载 YAML 配置。``path`` 为 None 时读取 ``configs/base.yaml``。"""
    if path is None:
        from causal_growth.io_utils import configs_dir

        path = configs_dir("base.yaml")
    p = Path(path)
    if not p.is_absolute():
        from causal_growth.io_utils import PROJECT_ROOT

        candidate = PROJECT_ROOT / p
        p = candidate if candidate.exists() else p
    if not p.exists():
        raise ConfigError(f"配置文件不存在：{p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"配置文件根节点必须是映射：{p}")
    cfg = Config(raw, name=p.stem)
    if overrides:
        cfg = cfg.with_overrides(overrides)
    if validate:
        validate_config(cfg)
    return cfg


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
@dataclass
class ValidationReport:
    """校验结果：硬约束全过，另附软区间提示。"""

    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return True  # 走到这里说明硬约束已通过

    def __bool__(self) -> bool:
        return True


#: 软区间提示：(点号路径, 建议下限, 建议上限, 业务含义)。见方案附录 A.1。
_SOFT_RANGES: tuple[tuple[str, float, float, str], ...] = (
    ("business.new_user_share", 0.2, 0.4, "新客比例"),
    ("business.baseline_conversion", 0.08, 0.12, "基线转化率 p0"),
    ("business.redemption_rate", 0.40, 0.70, "券核销率"),
    ("business.refund_rate", 0.05, 0.10, "退款率（护栏指标）"),
    ("business.goods_cost_ratio", 0.60, 0.75, "商品成本率"),
    ("business.fulfill_cost_mean", 3.0, 8.0, "履约成本（元/单）"),
    ("business.coupon_max_effect", 0.0, 0.15, "券最大效应 tau_max（概率尺度）"),
)

_REQUIRED_SECTIONS: tuple[str, ...] = (
    "project",
    "business",
    "windows",
    "experiment",
    "dgp",
    "dirty",
    "budget",
    "evaluation",
)


def validate_config(cfg: Config) -> ValidationReport:
    """校验硬约束（失败抛错），并收集软区间提示。"""
    report = ValidationReport()

    # ---- 结构 ----
    missing = [s for s in _REQUIRED_SECTIONS if cfg.get(s) is None]
    if missing:
        raise ConfigError(f"缺少必需配置段：{missing}")

    # ---- 概率类：必须严格落在 (0,1) ----
    for key in (
        "business.baseline_conversion",
        "business.new_user_share",
        "business.redemption_rate",
        "business.refund_rate",
        "business.goods_cost_ratio",
    ):
        value = float(cfg.require(key))
        if not 0.0 < value < 1.0:
            raise ConfigError(f"{key} 必须严格落在 (0,1) 内，当前 {value}")

    # ---- 券效应 + 基线转化率不得超过 1（否则 p0+tau 越界） ----
    p0 = float(cfg.require("business.baseline_conversion"))
    tau_max = float(cfg.require("business.coupon_max_effect"))
    if p0 + tau_max > 1.0:
        raise ConfigError(
            f"baseline_conversion({p0}) + coupon_max_effect({tau_max}) = {p0 + tau_max} > 1，"
            "概率尺度越界；请调低 tau_max 或 p0"
        )

    # ---- 券面额 ----
    faces = list(cfg.require("business.coupon_face_values"))
    if not faces or any(float(v) <= 0 for v in faces):
        raise ConfigError(f"coupon_face_values 必须是正数列表，当前 {faces}")

    # ---- 实验设计 ----
    alpha = float(cfg.require("experiment.alpha"))
    power = float(cfg.require("experiment.power"))
    if not 0.0 < alpha < 1.0:
        raise ConfigError(f"experiment.alpha 必须在 (0,1) 内，当前 {alpha}")
    if not 0.0 < power < 1.0:
        raise ConfigError(f"experiment.power 必须在 (0,1) 内，当前 {power}")
    t_share = float(cfg.require("experiment.treatment_share"))
    if not 0.0 < t_share < 1.0:
        raise ConfigError(f"experiment.treatment_share 必须在 (0,1) 内，当前 {t_share}")

    # ---- 两个窗口必须分开且为正 ----
    for key in ("windows.convert_days", "windows.profit_days"):
        if int(cfg.require(key)) <= 0:
            raise ConfigError(f"{key} 必须为正整数")
    if int(cfg.require("windows.profit_days")) < int(cfg.require("windows.convert_days")):
        raise ConfigError("利润成熟窗口必须 >= 转化观察窗口（方案 §2.3.2）")

    # ---- 数据切分 ----
    test_size = float(cfg.require("evaluation.test_size"))
    val_size = float(cfg.require("evaluation.val_size"))
    if not (0.0 < test_size < 1.0 and 0.0 <= val_size < 1.0):
        raise ConfigError(f"test_size/val_size 非法：{test_size}/{val_size}")
    if test_size + val_size >= 1.0:
        raise ConfigError(f"test_size({test_size}) + val_size({val_size}) 必须 < 1")

    # ---- 护栏非劣效界值方向 ----
    margin = float(cfg.require("experiment.guardrail.noninferiority_margin"))
    if margin <= 0:
        raise ConfigError("noninferiority_margin 必须为正，表示「允许恶化的最大幅度」")

    # ---- 软区间提示 ----
    for key, lo, hi, label in _SOFT_RANGES:
        value = cfg.get(key)
        if value is None:
            continue
        value = float(value)
        if not lo <= value <= hi:
            report.warnings.append(
                f"{label}（{key}={value}）超出方案建议区间 [{lo}, {hi}]；"
                "若为敏感性扫描请忽略，否则请在报告中说明依据"
            )

    return report
