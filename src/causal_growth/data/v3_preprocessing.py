"""合成数据 / 已知 DGP：训练独享拟合、可序列化冻结及白名单特征转换。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from causal_growth.config import Config, ConfigError
from causal_growth.data.v3_split import require_historical_training_input, user_key_hash
from causal_growth.v3_data_config import load_v3_data_config


_LEGAL_NUMERIC = {"is_new", "hist_gmv", "cart_value", "browse_depth", "assignment_week", "assignment_elapsed_days"}


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _reject_leakage(frame: pd.DataFrame, patterns: list[str], path_segments: list[str]) -> None:
    forbidden = [name for name in frame.columns if any(re.search(pattern, str(name)) for pattern in patterns)]
    if forbidden:
        raise ValueError(f"观察预处理拒绝审计/潜在结果列：{forbidden}")
    source = str(frame.attrs.get("source_path", "")).replace("\\", "/").casefold().split("/")
    if set(source) & {part.casefold() for part in path_segments}:
        raise ValueError("观察预处理拒绝 audit/truth 来源路径")


def _features(cfg: Config, data_cfg: Config, time_mode: str) -> tuple[list[str], bool, bool]:
    base = list(cfg.require("models.feature_whitelist"))
    legal = set(data_cfg.require("preprocessing.numeric_columns")) | {"channel", "missing_indicators"}
    if set(base) - legal:
        raise ConfigError("特征白名单包含处理后变量或未注册字段")
    if not set(data_cfg.require("preprocessing.numeric_columns")).issubset(_LEGAL_NUMERIC):
        raise ConfigError("工程 numeric_columns 越过分配前特征白名单")
    modes = cfg.section("models.time_feature_whitelist_by_mode")
    if time_mode not in modes or (time_mode != "static" and cfg.require("active_scenario.level") != "L2"):
        raise ConfigError("时间特征模式未注册或不适用于该层级")
    if not set(modes[time_mode]).issubset({"assignment_week", "assignment_elapsed_days"}):
        raise ConfigError("时间特征只能来自分配时已知周次和相对天数")
    numeric = [name for name in data_cfg.require("preprocessing.numeric_columns") if name in base]
    categorical = "channel" in base
    specification = cfg.require("models.feature_specification")
    if specification == "omit_new_user_and_channel":
        numeric = [name for name in numeric if name != "is_new"]
        categorical = False
    elif specification != "full_observed":
        raise ConfigError("未知学习特征错设配置")
    numeric.extend(name for name in modes[time_mode] if name not in numeric)
    indicators = bool(cfg.require("data.cleaning.missing_indicators")) and "missing_indicators" in base
    return numeric, categorical, indicators


def _input_values(frame: pd.DataFrame, numeric: list[str], channels: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    if "channel" not in frame or frame.channel.isna().any():
        raise ValueError("渠道是训练分组填补所需的已观测字段，不能为空")
    channel = frame.channel.astype(str)
    unknown = set(channel) - set(channels)
    if unknown:
        raise ValueError(f"出现冻结渠道字典之外的类别：{sorted(unknown)}")
    values = pd.DataFrame(index=frame.index)
    for name in numeric:
        if name == "assignment_elapsed_days" and name not in frame and "assignment_day" in frame:
            values[name] = pd.to_numeric(frame.assignment_day, errors="raise")
        elif name not in frame:
            raise ValueError(f"缺少分配前特征 {name}")
        else:
            values[name] = pd.to_numeric(frame[name], errors="raise")
        if np.isinf(values[name].to_numpy(dtype=float)).any():
            raise ValueError(f"特征 {name} 包含无穷值")
    return values.astype(float), channel


@dataclass(frozen=True)
class FeatureMatrix:
    """明确列顺序、预处理指纹与变换计数的纯特征矩阵。"""

    matrix: NDArray[np.float64]
    feature_names: tuple[str, ...]
    preprocessor_hash: str
    log: dict[str, Any]


@dataclass(frozen=True)
class FrozenPreprocessor:
    """参数以不可变 JSON 保存；transform 不更新中位数、阈值、类别或尺度。"""

    _state_json: str

    @property
    def hash(self) -> str:
        """返回训练状态的完整内容指纹，用于模型/策略冻结 manifest。"""
        return hashlib.sha256(self._state_json.encode("utf-8")).hexdigest()

    @property
    def feature_names(self) -> tuple[str, ...]:
        """返回冻结顺序，所有模型在同一状态下共享该顺序。"""
        return tuple(self.to_dict()["feature_names"])

    def to_dict(self) -> dict[str, Any]:
        """返回可直接写 JSON 的独立字典副本。"""
        return json.loads(self._state_json)

    @classmethod
    def from_dict(cls, state: Mapping[str, Any]) -> FrozenPreprocessor:
        """恢复状态且校验特征边界，拒绝把结果列混入持久化白名单。"""
        snapshot = json.loads(_canonical(state))
        if not set(snapshot["numeric_columns"]).issubset(_LEGAL_NUMERIC):
            raise ValueError("预处理状态越过合法数值特征边界")
        names = list(snapshot["numeric_columns"])
        if snapshot["missing_indicators"]:
            names += [f"{name}_missing" for name in snapshot["numeric_columns"]]
        if snapshot["encode_channel"]:
            names += [f"channel_{channel}" for channel in snapshot["channel_categories"]]
        if names != snapshot["feature_names"]:
            raise ValueError("序列化特征名称和状态内容不一致")
        for parameter in snapshot["numeric_state"].values():
            if not np.isfinite(parameter["scale"]) or parameter["scale"] <= 0:
                raise ValueError("序列化标准化尺度非法")
        return cls(_canonical(snapshot))

    def transform(self, observed: pd.DataFrame) -> FeatureMatrix:
        """仅按训练状态转换观察用户，记录填补、截尾及裁剪但不重新拟合。"""
        state = self.to_dict()
        _reject_leakage(observed, state["forbidden_column_patterns"], state["forbidden_path_segments"])
        values, channel = _input_values(observed, state["numeric_columns"], state["channel_categories"])
        missing = values.isna()
        columns: list[NDArray[np.float64]] = []
        counts: dict[str, Any] = {}
        for name in state["numeric_columns"]:
            parameter = state["numeric_state"][name]
            imputed = values[name].fillna(channel.map(parameter["channel_medians"]).fillna(parameter["global_median"]))
            raw = imputed.to_numpy(dtype=float)
            lower, upper = parameter["winsor_lower"], parameter["winsor_upper"]
            winsor = raw.copy()
            if lower is not None:
                winsor = np.maximum(winsor, lower)
            if upper is not None:
                winsor = np.minimum(winsor, upper)
            transformed = (winsor - parameter["mean"]) / parameter["scale"]
            clip = parameter["standardized_clip"]
            clipped = np.clip(transformed, -clip, clip) if clip is not None else transformed
            columns.append(clipped)
            counts[name] = {"imputed_n": int(missing[name].sum()), "winsorized_n": int((winsor != raw).sum()),
                            "standardized_clipped_n": int((clipped != transformed).sum())}
        if state["missing_indicators"]:
            columns.extend(missing[name].to_numpy(dtype=float) for name in state["numeric_columns"])
        if state["encode_channel"]:
            columns.extend((channel == category).to_numpy(dtype=float) for category in state["channel_categories"])
        matrix = np.column_stack(columns) if columns else np.empty((len(observed), 0))
        if not np.isfinite(matrix).all():
            raise ArithmeticError("冻结转换仍出现非有限特征")
        return FeatureMatrix(matrix, self.feature_names, self.hash,
                             {"n_users": len(observed), "by_feature": counts, "parameters_updated": False})


def fit_preprocessor(
    training: pd.DataFrame, cfg: Config, *, role: str, time_mode: str = "static",
    selection_receipt: Mapping[str, Any] | None = None,
) -> FrozenPreprocessor:
    """只拟合显式 train 角色或经成熟/入库核验的滚动候选，禁止默认全表 fit。

    数据输入必须是观测 SQL 表或其明确训练切片；标签/结果不参与任何参数。
    原验证用户不能加入滚动训练，当前和未来测试用户也不能借角色改名进入。
    """
    data_cfg = load_v3_data_config()
    require_historical_training_input(training)
    patterns = list(data_cfg.require("isolation.forbidden_column_patterns"))
    paths = list(data_cfg.require("isolation.forbidden_path_segments"))
    _reject_leakage(training, patterns, paths)
    if len(training) == 0 or "split" not in training:
        raise ValueError("fit 需要非空、带明确 split 的训练用户切片")
    keys_hash = user_key_hash(training)
    if role == "train":
        if not training.split.eq("train").all():
            raise ValueError("train fit 不接受验证/测试用户或全表")
        receipt = None
    elif role == "rolling_train":
        if cfg.require("active_scenario.level") != "L2" or not selection_receipt:
            raise ValueError("rolling_train 必须附 L2 成熟入库选择凭据")
        receipt = dict(selection_receipt)
        if (receipt.get("selection_method") != "past_mature_ingested_train_or_prior_test_validation_held_out"
                or receipt.get("source_kind") != "sql_observed" or receipt.get("config_hash") != cfg.hash(length=64)
                or receipt.get("train_user_key_hash") != keys_hash):
            raise ValueError("滚动选择凭据与当前训练用户/配置不符")
        origin = receipt.get("origin_week")
        if origin not in cfg.require("design.temporal.rolling_origin_weeks"):
            raise ValueError("凭据起点未注册")
        cutoff = (origin - 1) * cfg.require("design.temporal.days_per_week")
        ingestion = receipt.get("ingestion_day_column")
        completeness = receipt.get("completeness_day_column")
        if (cutoff != receipt.get("cutoff_day") or not ingestion or ingestion not in training
                or not completeness or completeness not in training):
            raise ValueError("滚动凭据缺少一致的截止/入库时点")
        if not {"assignment_day", "assignment_week"}.issubset(training):
            raise ValueError("滚动训练缺少入组时间")
        finite = np.isfinite(training[["assignment_day", "assignment_week", ingestion, completeness]].to_numpy(dtype=float)).all()
        legal = (training.split.isin(["train", "test"])
                 & (training.assignment_day < cutoff) & (training.assignment_week < origin)
                 & (training.assignment_day + cfg.require("windows.profit_days") <= cutoff)
                 & (training[ingestion] <= cutoff) & (training[completeness] <= cutoff))
        if not finite or not legal.all():
            raise ValueError("滚动训练包含验证、未来、未成熟或未入库用户")
    else:
        raise ValueError("fit role 只能显式为 train 或有凭据的 rolling_train")
    numeric, encode_channel, indicators = _features(cfg, data_cfg, time_mode)
    if data_cfg.require("preprocessing.time_feature_transform") != "standardize_without_winsor_or_clip":
        raise ConfigError("未注册的时间字段变换")
    channels = list(cfg.section("business.channels"))
    ordered = training.sort_values(["run_id", "user_id"], kind="stable")
    values, channel = _input_values(ordered, numeric, channels)
    quantiles = tuple(cfg.require("data.cleaning.numeric_winsor_quantiles"))
    if len(quantiles) != 2 or not 0 <= quantiles[0] < quantiles[1] <= 1:
        raise ConfigError("winsor 分位数边界非法")
    clip = cfg.require("data.cleaning.standardized_feature_clip")
    if clip is not None and (not np.isfinite(clip) or clip <= 0):
        raise ConfigError("标准化裁剪值必须正且有限，或为 null")
    if cfg.require("data.cleaning.numeric_imputation") != "training_channel_median_with_global_training_fallback":
        raise ConfigError("不支持未注册填补机制")
    if cfg.require("data.cleaning.standardization") != "training_mean_and_sd":
        raise ConfigError("不支持未注册标准化机制")
    parameters: dict[str, Any] = {}
    for name in numeric:
        if values[name].isna().all():
            raise ValueError(f"训练特征 {name} 全缺失，不能借用验证/测试值或编造全局中位数")
        global_median = float(values[name].median())
        grouped = values[name].groupby(channel).median()
        medians = {category: float(grouped[category]) for category in channels
                   if category in grouped and pd.notna(grouped[category])}
        filled = values[name].fillna(channel.map(medians).fillna(global_median)).to_numpy(dtype=float)
        # q=0/1 means genuinely disabled bounds, not training extrema. This is
        # essential for invertible L3 confounders under out-of-range test values.
        is_time = name in {"assignment_week", "assignment_elapsed_days"}
        lower = float(np.quantile(filled, quantiles[0], method=data_cfg.require("preprocessing.quantile_method"))) if quantiles[0] > 0 and not is_time else None
        upper = float(np.quantile(filled, quantiles[1], method=data_cfg.require("preprocessing.quantile_method"))) if quantiles[1] < 1 and not is_time else None
        winsor = filled.copy()
        if lower is not None:
            winsor = np.maximum(winsor, lower)
        if upper is not None:
            winsor = np.minimum(winsor, upper)
        mean = float(winsor.mean())
        scale = float(winsor.std(ddof=int(data_cfg.require("preprocessing.std_ddof"))))
        if scale == 0:
            scale = float(data_cfg.require("preprocessing.zero_variance_scale"))
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("训练标准化尺度不能为非正或非有限值")
        parameters[name] = {"global_median": global_median, "channel_medians": medians,
                            "winsor_lower": lower, "winsor_upper": upper, "mean": mean, "scale": scale,
                            "standardized_clip": None if is_time else clip,
                            "training_missing_n": int(values[name].isna().sum())}
    feature_names = list(numeric)
    if indicators:
        feature_names += [f"{name}_missing" for name in numeric]
    if encode_channel:
        feature_names += [f"channel_{channel}" for channel in channels]
    state = {
        "source": "合成数据 / 已知 DGP", "serialization_version": data_cfg.require("preprocessing.serialization_version"),
        "config_hash": cfg.hash(length=64), "engineering_config_hash": data_cfg.hash(length=64),
        "fit_role": role, "time_mode": time_mode, "training_n": len(training), "training_user_key_hash": keys_hash,
        "selection_receipt": receipt, "numeric_columns": numeric, "numeric_state": parameters,
        "encode_channel": encode_channel, "channel_categories": channels,
        "unknown_channel_policy": data_cfg.require("preprocessing.unknown_channel_policy"),
        "time_feature_transform": data_cfg.require("preprocessing.time_feature_transform"),
        "missing_indicators": indicators, "standardized_feature_clip": clip, "feature_names": feature_names,
        "forbidden_column_patterns": patterns, "forbidden_path_segments": paths,
    }
    return FrozenPreprocessor.from_dict(state)
