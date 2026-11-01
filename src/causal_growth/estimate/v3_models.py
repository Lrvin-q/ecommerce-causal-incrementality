"""合成数据 / 已知 DGP：Phase D 五个主模型的统一学习接口。

本模块回答的问题
----------------
在同一批已拆分的观测数据上，常数 / T-learner / S-learner / Causal Forest / DR-learner
如何给出**同口径**的个体增量利润效应 ``τ̂(X)=E[Π(1)−Π(0)|X]``，并只用观测数据
完成拟合、验证集打分与模型选择（真值对比留给最终审计）。

三条不可违反的规矩
------------------
1. **同一拆分、同一特征状态。** 所有模型消费同一个 :class:`LearningData`；
   预处理器只在训练切分上拟合一次并冻结，``preprocessor_hash`` 与三个切分的
   用户键指纹写进 :class:`Predictions`，作为"同拆分配对"的可核对证据。
2. **特征只走白名单。** 模型看到的列必须**恰好**是 ``models.feature_whitelist``
   的派生列（数值特征 / 缺失指示 / 渠道 one-hot / 已注册时间特征）；
   ``U``、``true_propensity``、``true_cate``、``potential_*`` 等禁用列在接口层
   直接抛 :class:`FeatureBoundaryError`，不靠注释提醒。
3. **不读真值。** 本模块不 import ``audit/``、不在估计路径 import DGP 生成器，
   也不接受携带潜在结果的 frame。学习曲线只报"训练规模 vs 预测稳定性 / 验证集
   指标"，不报 RMSE-vs-truth。

随机性
------
只用 ``causal_growth.rng`` 的种子派生：交叉拟合折号来自 :func:`child_rng`，
LightGBM / CausalForest 的 ``random_state`` 来自 :func:`child_seed`（后者在
``rng.py`` 中被明确设计为"给 sklearn ``random_state`` 用"）。没有裸
``np.random.*``。学习曲线子样本的 stream **不含模型名**，以保证
``models.yaml → data_selection_seed_scope: shared_across_models_within_rep``：
同一 rep 内所有模型看到同一批训练行。

口径来源
--------
模型清单、特征白名单、超参、常数模型两条路径、学习曲线规模、选择规则全部来自
冻结的 ``configs/v3/models.yaml``；随机化 / 观察性识别模式与
``data/v3_sql.py`` 的 ``observational_history`` 保持同一条判定规则
（``dgp.profile == "l3" and not dgp.virtual_aa_labels``）。

配置缺项
--------
本模块不修改七份冻结配置。若某项在配置中缺失，就在这里给显式默认值并抛错说明，
不做静默兜底；当前已确认 ``models.yaml`` 覆盖了本模块用到的全部超参。

倾向得分来源与截断诊断（C7 增补）
--------------------------------
DR 的倾向得分有两个来源，由 ``propensity_source`` 显式选择：

* ``"estimated"``（**默认，D.3 已验收口径**）：交叉拟合 ``models.dr_learner.propensity_model``
  估计 e，并按 ``models.propensity.estimated_probability_clip`` 截断；
* ``"known_design"``（**只能显式开启**）：随机化层直接用观测表的 ``design_probability``
  真值作 e，**不截断**；观察性层（L3）没有已知设计概率，传它直接抛
  :class:`PropensitySourceError`。该来源对应 ``models.ate.randomized`` 已注册的
  ``known_design_ipw`` 口径，但**不得成为默认**——默认一改，52 项已验收契约就换了口径。

:class:`NuisanceFit` 同时保存截断前的 raw 范围（``propensity_raw_min/max``）、被截断的
样本数（``propensity_clipped_count``）与实际生效的截断边界（``propensity_clip_low/high``），
这是 ``models.propensity.raw_probability_diagnostics_required`` 的落地：截断一旦触发，
DR 的偏倚不可忽略，该 rep 必须单独标注。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import NormalDist
from typing import Any, Callable

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from causal_growth.config import Config, ConfigError
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.data.v3_preprocessing import FrozenPreprocessor, fit_preprocessor
from causal_growth.data.v3_split import user_key_hash
from causal_growth.policy.selection import greedy_by_ratio
from causal_growth.policy.v3_policy import fit_cost_model, predict_expected_cost
from causal_growth.rng import child_rng, child_seed
from causal_growth.v3_data_config import load_v3_data_config

__all__ = [
    "D03_EXPORT_COLUMNS",
    "MODEL_NAMES",
    "PROPENSITY_SOURCES",
    "CrossfitDrAte",
    "FeatureBoundaryError",
    "LearningData",
    "ModelNotApplicableError",
    "NuisanceFit",
    "Predictions",
    "PropensitySourceError",
    "SplitBlock",
    "ValidationScorer",
    "aipw_pseudo_outcome",
    "allowed_feature_names",
    "causal_forest_estimator",
    "constant_source",
    "crossfit_dr_ate",
    "crossfit_nuisance",
    "dr_learner_cate",
    "export_d03_predictions",
    "fit_predict",
    "fit_validation_scorer",
    "identification_mode",
    "itt_estimate",
    "learning_curve",
    "prepare_learning_data",
    "rank_models",
    "reject_forbidden_frame_columns",
    "require_feature_boundary",
    "require_model_applicable",
    "require_whitelisted_feature_names",
    "resolve_propensity_source",
    "run_d03_diagnostic",
    "run_propensity_sensitivity",
    "run_smoke",
]

#: D03 交付物：E 阶段编排脚本 ``scripts/21_e_policy_run.py`` 的固定 9 列输入契约。
#: 前 7 列只由观测表与模型预测构成；后 2 列是 **audit-only** 真值，只供评估。
D03_EXPORT_COLUMNS: tuple[str, ...] = (
    "user_id",
    "is_new",
    "cart_value",
    "purchase_propensity",
    "predicted_profit",
    "tau_hat",
    "cost_hat",
    "tau_true",
    "cost_true",
)

#: 全部主模型名。顺序与 ``selection.tie_break_order`` 无关，后者才是排序口径。
MODEL_NAMES: tuple[str, ...] = ("constant", "t_learner", "s_learner", "causal_forest", "dr_learner")

#: ``models.yaml → constant`` 的两条口径。名称写死在这里，是为了在配置被改写时**报错**
#: 而不是悄悄换一条路径。
_CONSTANT_PATHS: dict[str, str] = {
    "randomized": "training_itt",
    "observational": "training_crossfit_dr_ate",
}

#: DR 倾向得分的两个可注册来源。默认 ``estimated`` 是 D.3 已验收口径；
#: ``known_design`` 只作显式敏感性对照，**不得成为默认**。
PROPENSITY_SOURCES: tuple[str, ...] = ("estimated", "known_design")

#: ``models.yaml → models.ate.randomized`` 里"已知设计概率 IPW"的注册名。
#: ``known_design`` 路径必须确认该口径确实被冻结配置注册，否则抛 ``ConfigError``。
_KNOWN_DESIGN_ATE_NAME = "known_design_ipw"

#: 截断真的发生时写进 ``info`` 的告警原文（与文档同一句话，便于审计检索）。
_CLIPPING_NOTE = (
    "estimated propensity 触发截断：截断引入的偏倚不可忽略，该 rep 的 DR 结果必须单独标注"
)

_SCORING_NAME = "validation_crossfit_dr_policy_value_lower_confidence_bound"
_DR_CROSSFIT_STREAM = "v3.models.dr.crossfit"
_LEARNING_CURVE_STREAM = "v3.models.learning_curve.subsample"
_POTENTIAL_PREFIX = "potential_"

#: C7 敏感性对照的资源上限。机器上还有正式 AA 作业（每层 250 次 × 20 万人）在跑，
#: 本对照一律 n≤20,000、R≤5；超限直接抛错，不静默降规模。
_SENSITIVITY_MAX_N = 20_000
_SENSITIVITY_MAX_REPS = 5
#: 默认对照场景：L1_main（设计概率 0.5）与一个非 0.5 的随机化场景（设计概率 0.1）。
_SENSITIVITY_SCENARIOS: tuple[str, ...] = ("L1_main", "L2_n30000_p010")


class PropensitySourceError(ValueError):
    """倾向得分来源非法：未知来源、观察性层要求 known_design、或设计概率不可用。"""


class FeatureBoundaryError(ValueError):
    """特征越过白名单或命中禁用列（真值 / 潜在结果 / 审计列）。"""


class ModelNotApplicableError(ValueError):
    """模型不适用于当前层级（由 ``models.yaml → additional_by_level`` 决定）。"""


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _master_seed(cfg: Config) -> int:
    return int(cfg.require("project.master_seed"))


def _seed(cfg: Config, name: str, index: int) -> int:
    """派生 ``random_state``：语义化 stream + rep 索引，跨进程稳定。"""
    return child_seed(_master_seed(cfg), f"v3.models.{name}", index)


def _feature_matrix(X: Any, *, label: str = "X") -> NDArray[np.float64]:
    array = np.asarray(X, dtype=float)
    if array.ndim != 2 or array.shape[1] == 0:
        raise ValueError(f"{label} 必须是列数非零的二维矩阵，收到 {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{label} 含非有限值")
    return array


def _binary_treatment(t: Any, n: int, *, require_both_arms: bool) -> NDArray[np.int64]:
    array = np.asarray(t)
    if array.shape != (n,):
        raise ValueError(f"处理标签长度应为 {n}，收到 {array.shape}")
    if array.dtype == bool:
        array = array.astype(int)
    if not np.isin(array, (0, 1)).all():
        raise ValueError("处理标签只能取 0/1")
    result = array.astype(np.int64)
    if require_both_arms and (int((result == 1).sum()) < 2 or int((result == 0).sum()) < 2):
        raise ValueError("处理组或对照组样本不足 2 个，无法拟合")
    return result


def _outcome(y: Any, n: int) -> NDArray[np.float64]:
    array = np.asarray(y, dtype=float).reshape(-1)
    if array.shape != (n,):
        raise ValueError(f"结果变量长度应为 {n}，收到 {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError("结果变量含非有限值（未处理用户的净利润应记 0，不是 NaN）")
    return array


def _sd(values: Any) -> float:
    """标准差；常数向量直接返回 0.0，避免浮点求和残差污染报告。"""
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.size < 2:
        return 0.0
    if float(np.ptp(array)) == 0.0:
        return 0.0
    return float(np.std(array, ddof=1))


# --------------------------------------------------------------------------- #
# 特征边界：白名单 + 禁用列硬拒绝
# --------------------------------------------------------------------------- #
def _forbidden_matchers(cfg: Config) -> tuple[frozenset[str], tuple[re.Pattern[str], ...]]:
    explicit = frozenset(str(name) for name in cfg.require("models.forbidden_features"))
    patterns = tuple(
        re.compile(str(pattern))
        for pattern in load_v3_data_config().require("isolation.forbidden_column_patterns")
    )
    return explicit, patterns


def _forbidden_hits(names: Iterable[Any], cfg: Config) -> list[str]:
    explicit, patterns = _forbidden_matchers(cfg)
    hits: set[str] = set()
    for name in names:
        text = str(name)
        if text in explicit or text.startswith(_POTENTIAL_PREFIX):
            hits.add(text)
        elif any(pattern.search(text) for pattern in patterns):
            hits.add(text)
    return sorted(hits)


def reject_forbidden_frame_columns(frame: pd.DataFrame, cfg: Config) -> None:
    """接口层硬拒绝：只要 frame 出现真值 / 潜在结果 / 审计列就抛异常。

    这是 :class:`ObservedDataset` 之外的第二道闸。即便将来某个上游入口放宽了列白名单，
    学习接口也不会把 ``U``、``true_cate`` 或 ``potential_*`` 当作特征消费。
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("禁用列检查需要 DataFrame")
    hits = _forbidden_hits(frame.columns, cfg)
    if hits:
        raise FeatureBoundaryError(f"学习接口拒绝禁用特征列（真值/潜在结果/审计）：{hits}")


def allowed_feature_names(cfg: Config, time_mode: str = "static") -> frozenset[str]:
    """返回当前配置下**允许**进入模型的特征列集合（白名单的派生列）。"""
    whitelist = {str(name) for name in cfg.require("models.feature_whitelist")}
    data_cfg = load_v3_data_config()
    numeric = [
        str(name)
        for name in data_cfg.require("preprocessing.numeric_columns")
        if str(name) in whitelist
    ]
    specification = str(cfg.require("models.feature_specification"))
    if specification == "omit_new_user_and_channel":
        numeric = [name for name in numeric if name != "is_new"]
    elif specification != "full_observed":
        raise ConfigError(f"未注册的学习特征错设：{specification}")
    allowed = set(numeric)
    if bool(cfg.require("data.cleaning.missing_indicators")) and "missing_indicators" in whitelist:
        allowed |= {f"{name}_missing" for name in numeric}
    if specification != "omit_new_user_and_channel" and "channel" in whitelist:
        allowed |= {f"channel_{category}" for category in cfg.require("business.channels")}
    if time_mode != "static":
        modes = cfg.section("models.time_feature_whitelist_by_mode")
        if time_mode not in modes:
            raise ConfigError(f"未注册的时间特征模式：{time_mode}")
        allowed |= {str(name) for name in modes[time_mode]}
    return frozenset(allowed)


def require_whitelisted_feature_names(
    names: Iterable[Any], cfg: Config, time_mode: str = "static"
) -> None:
    """特征名必须**恰好**是白名单派生列：多一列（越界）或少一列（漏特征）都报错。"""
    columns = tuple(str(name) for name in names)
    if not columns:
        raise FeatureBoundaryError("特征块为空，模型无法学习")
    hits = _forbidden_hits(columns, cfg)
    if hits:
        raise FeatureBoundaryError(f"特征块包含禁用列：{hits}")
    allowed = allowed_feature_names(cfg, time_mode)
    missing = sorted(allowed - set(columns))
    extra = sorted(set(columns) - allowed)
    if missing or extra:
        raise FeatureBoundaryError(
            f"特征块必须恰为白名单派生列；缺少={missing} 越界={extra}"
        )


def require_feature_boundary(
    frame_or_names: pd.DataFrame | Iterable[Any], cfg: Config, time_mode: str = "static"
) -> None:
    """统一入口：frame 只查禁用列，特征名块再查白名单完整性。"""
    if isinstance(frame_or_names, pd.DataFrame):
        reject_forbidden_frame_columns(frame_or_names, cfg)
    else:
        require_whitelisted_feature_names(frame_or_names, cfg, time_mode)


# --------------------------------------------------------------------------- #
# 识别模式与层级适用性
# --------------------------------------------------------------------------- #
def identification_mode(cfg: Config) -> str:
    """返回 ``randomized`` 或 ``observational``。

    与 ``data/v3_sql.py`` 的 ``observational_history`` 参数使用同一条规则：
    只有 ``dgp.profile == "l3"`` 且非虚拟 AA 标签才是观察性历史；虚拟标签的 AA
    单元仍是随机化日志。观察性模式只允许出现在 L3。
    """
    profile = str(cfg.require("dgp.profile"))
    virtual = bool(cfg.require("dgp.virtual_aa_labels"))
    mode = "observational" if profile == "l3" and not virtual else "randomized"
    if mode == "observational" and str(cfg.require("active_scenario.level")) != "L3":
        raise ConfigError("观察性识别模式只适用于 L3")
    return mode


def require_model_applicable(model_name: str, cfg: Config) -> None:
    """未知模型 / 层不适用（如 L0、L2 调 DR-learner）都必须抛异常。"""
    if model_name not in MODEL_NAMES:
        raise ValueError(f"未知模型 {model_name!r}；可用：{MODEL_NAMES}")
    level = str(cfg.require("active_scenario.level"))
    additional = cfg.section("models.additional_by_level")
    if level not in additional:
        raise ConfigError(f"未注册层级 {level!r}；additional_by_level={sorted(additional)}")
    allowed = {str(name) for name in cfg.require("models.common")}
    allowed |= {str(name) for name in additional[level]}
    if model_name not in allowed:
        raise ModelNotApplicableError(
            f"{model_name} 不适用于 {level}：models.yaml additional_by_level[{level}]="
            f"{list(additional[level])}"
        )


# --------------------------------------------------------------------------- #
# 倾向得分来源：默认 estimated，known_design 只能显式开启
# --------------------------------------------------------------------------- #
def resolve_propensity_source(cfg: Config, source: str) -> str:
    """校验 DR 倾向得分来源，返回规范化后的字符串。

    ``"estimated"`` 是默认路径（估计 e + 截断）；``"known_design"`` 是显式敏感性开关：

    * 只适用于随机化层——L3 观察性层没有已知设计概率，传它就抛
      :class:`PropensitySourceError`（不是 warning，也不是悄悄退回估计）；
    * 必须确认 ``models.ate.randomized`` 注册了 ``known_design_ipw``，否则抛
      ``ConfigError``——配置没登记的估计量不允许在代码里悄悄可用。
    """
    text = str(source)
    if text not in PROPENSITY_SOURCES:
        raise PropensitySourceError(
            f"未知倾向得分来源 {text!r}；可用：{PROPENSITY_SOURCES}"
        )
    if text == "estimated":
        return text
    mode = identification_mode(cfg)
    if mode != "randomized":
        raise PropensitySourceError(
            f"known_design 倾向只适用于随机化层；当前识别模式为 {mode!r}"
            "（观察性层没有已知设计概率，只能用 estimated）"
        )
    registered = [str(name) for name in cfg.require("models.ate.randomized")]
    if _KNOWN_DESIGN_ATE_NAME not in registered:
        raise ConfigError(
            "known_design 倾向对应的 ATE 口径未在 models.ate.randomized 注册："
            f"{registered}"
        )
    return text


def _design_probability_vector(design: Any, n: int) -> NDArray[np.float64]:
    """把观测表的 ``design_probability`` 列校验成逐人向量。

    已知设计概率是**真值**，不参与截断；但必须逐人有限且严格落在 (0,1)，否则重叠
    假设不成立，硬算伪结局只会得到一个看似正常的结果。
    """
    array = np.asarray(design, dtype=float).reshape(-1)
    if array.shape != (n,):
        raise PropensitySourceError(f"design_probability 长度应为 {n}，收到 {array.shape}")
    if not np.isfinite(array).all():
        raise PropensitySourceError(
            "known_design 要求每个用户都有有限的 design_probability（观察性层没有该列）"
        )
    if not ((array > 0.0) & (array < 1.0)).all():
        raise PropensitySourceError("design_probability 必须严格落在 (0,1)")
    return array


def _estimated_probability_clip(cfg: Config) -> tuple[float, float]:
    """读取并校验 ``models.propensity.estimated_probability_clip``。"""
    clip = cfg.require("models.propensity.estimated_probability_clip")
    if len(clip) != 2 or not 0 < float(clip[0]) < float(clip[1]) < 1:
        raise ConfigError("倾向得分截断边界非法")
    return float(clip[0]), float(clip[1])


# --------------------------------------------------------------------------- #
# 学习数据：一次准备，所有模型共享
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SplitBlock:
    """一个拆分角色的冻结特征块与标签；行序与源观测表一致。"""

    role: str
    X: NDArray[np.float64]
    y: NDArray[np.float64]
    treatment: NDArray[np.int64]
    keys: pd.DataFrame = field(repr=False)
    design_probability: NDArray[np.float64] = field(repr=False)
    feature_names: tuple[str, ...] = ()
    key_hash: str = ""

    @property
    def n(self) -> int:
        """该切分的用户数。"""
        return int(self.X.shape[0])

    @property
    def has_design_probability(self) -> bool:
        """是否每个用户都记录了随机化设计概率（观察性日志为 False）。"""
        return bool(np.isfinite(self.design_probability).all())


@dataclass(frozen=True)
class LearningData:
    """同一拆分、同一冻结预处理状态下的三个切分；模型间配对比较的载体。"""

    train: SplitBlock
    validation: SplitBlock
    test: SplitBlock
    feature_names: tuple[str, ...]
    preprocessor_hash: str
    preprocessor: FrozenPreprocessor = field(repr=False)
    config_hash: str = ""
    observed_hash: str = ""
    level: str = ""
    identification_mode: str = "randomized"
    time_mode: str = "static"
    split_fingerprint: str = ""

    def block(self, role: str) -> SplitBlock:
        """按角色取切分，避免调用方自己拼 ``train/validation/test``。"""
        if role == "train":
            return self.train
        if role == "validation":
            return self.validation
        if role == "test":
            return self.test
        raise ValueError(f"未知拆分角色 {role!r}")


def _split_block(
    role: str, frame: pd.DataFrame, preprocessor: FrozenPreprocessor, time_mode: str, cfg: Config
) -> SplitBlock:
    required = {"run_id", "user_id", "treatment", "net_profit", "design_probability", "channel"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{role} 切分缺少学习必需列：{missing}")
    transformed = preprocessor.transform(frame)
    require_whitelisted_feature_names(transformed.feature_names, cfg, time_mode)
    matrix = np.ascontiguousarray(transformed.matrix, dtype=float)
    y = _outcome(frame["net_profit"].to_numpy(), len(frame))
    treatment = _binary_treatment(frame["treatment"].to_numpy(), len(frame), require_both_arms=True)
    keys = frame[["run_id", "user_id"]].reset_index(drop=True)
    raw_design = frame["design_probability"]
    design = pd.to_numeric(raw_design, errors="coerce").to_numpy(dtype=float)
    present = raw_design.notna().to_numpy()
    if not np.isfinite(design[present]).all():
        raise ValueError(f"{role} 切分的随机化设计概率含非法值")
    if present.any() and not ((design[present] > 0) & (design[present] < 1)).all():
        raise ValueError(f"{role} 切分的随机化设计概率必须严格落在 (0,1)")
    return SplitBlock(
        role=role,
        X=matrix,
        y=y,
        treatment=treatment,
        keys=keys,
        design_probability=design,
        feature_names=tuple(transformed.feature_names),
        key_hash=user_key_hash(keys),
    )


def prepare_learning_data(
    dataset: ObservedDataset, cfg: Config, *, time_mode: str = "static"
) -> LearningData:
    """把已拆分观测表冻结成一个 :class:`LearningData`。

    回答"这一 rep 的哪批用户、用哪个预处理状态、进入哪个模型"三个问题。
    预处理器**只在训练切分上拟合一次**；三个切分共享同一状态，因此后续所有模型看到的
    是同一份特征矩阵（同拆分配对）。本函数不读取任何真值列。
    """
    if not isinstance(dataset, ObservedDataset):
        raise TypeError("学习数据必须来自 ObservedDataset（SQL 观测表），不能是任意 frame")
    dataset.require_history()
    if dataset.config_hash != cfg.hash(64):
        raise ValueError("观测数据集与当前场景配置不一致，不能跨配置做配对比较")
    frame = dataset.observations
    require_feature_boundary(frame, cfg, time_mode)
    mode = identification_mode(cfg)
    if "split" not in frame:
        raise ValueError("观测表缺少拆分标记，不能用于学习")
    roles = ("train", "validation", "test")
    if not frame.split.isin(roles).all():
        raise ValueError("观测表存在未注册的拆分角色")
    counts = {role: int((frame.split == role).sum()) for role in roles}
    if any(value == 0 for value in counts.values()):
        raise ValueError(f"拆分角色不能为空：{counts}")
    train_frame = frame.loc[frame.split == "train"].reset_index(drop=True)
    preprocessor = fit_preprocessor(train_frame, cfg, role="train", time_mode=time_mode)
    blocks = {
        role: _split_block(
            role,
            frame.loc[frame.split == role].reset_index(drop=True),
            preprocessor,
            time_mode,
            cfg,
        )
        for role in roles
    }
    for role, block in blocks.items():
        if mode == "randomized" and not block.has_design_probability:
            raise ValueError(f"{role} 切分缺少随机化设计概率，与 randomized 识别模式不符")
        if mode == "observational" and block.has_design_probability:
            raise ValueError(f"{role} 切分带有设计概率，与 observational 识别模式不符")
    fingerprint = hashlib.sha256(
        json.dumps(
            {role: blocks[role].key_hash for role in roles},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return LearningData(
        train=blocks["train"],
        validation=blocks["validation"],
        test=blocks["test"],
        feature_names=tuple(preprocessor.feature_names),
        preprocessor_hash=preprocessor.hash,
        preprocessor=preprocessor,
        config_hash=dataset.config_hash,
        observed_hash=dataset.content_hash,
        level=str(cfg.require("active_scenario.level")),
        identification_mode=mode,
        time_mode=time_mode,
        split_fingerprint=fingerprint,
    )


# --------------------------------------------------------------------------- #
# 基学习器装配（超参严格取自冻结配置）
# --------------------------------------------------------------------------- #
def _lightgbm_spec(cfg: Config) -> dict[str, Any]:
    return cfg.section("models.lightgbm")


def _lightgbm_regressor(cfg: Config, *, seed: int) -> Any:
    import lightgbm as lgb

    spec = _lightgbm_spec(cfg)
    return lgb.LGBMRegressor(
        n_estimators=int(spec["n_estimators"]),
        learning_rate=float(spec["learning_rate"]),
        num_leaves=int(spec["num_leaves"]),
        min_child_samples=int(spec["min_child_samples"]),
        subsample=float(spec["subsample"]),
        colsample_bytree=float(spec["colsample_bytree"]),
        n_jobs=int(spec["n_jobs"]),
        verbose=int(spec["verbosity"]),
        random_state=int(seed),
    )


def _lightgbm_classifier(cfg: Config, *, seed: int) -> Any:
    import lightgbm as lgb

    spec = _lightgbm_spec(cfg)
    return lgb.LGBMClassifier(
        n_estimators=int(spec["n_estimators"]),
        learning_rate=float(spec["learning_rate"]),
        num_leaves=int(spec["num_leaves"]),
        min_child_samples=int(spec["min_child_samples"]),
        subsample=float(spec["subsample"]),
        colsample_bytree=float(spec["colsample_bytree"]),
        n_jobs=int(spec["n_jobs"]),
        verbose=int(spec["verbosity"]),
        random_state=int(seed),
    )


def causal_forest_estimator(cfg: Config, *, seed: int) -> Any:
    """装配冻结口径的 ``CausalForestDML`` 并校验资源/识别参数。

    ``n_jobs=1`` 与 ``inference=False`` 是资源协议的一部分（见
    ``execution.resources.model_internal_threads``），一旦配置漂移就报错而不是静默接受。
    """
    from econml.dml import CausalForestDML

    spec = cfg.section("models.causal_forest")
    if int(spec["n_jobs"]) != 1:
        raise ConfigError("Causal Forest 必须 n_jobs=1（禁止嵌套并行）")
    if bool(spec["inference"]):
        raise ConfigError("本阶段 Causal Forest 固定 inference=False（不做区间推断）")
    if not bool(spec["discrete_treatment"]):
        raise ConfigError("二值券动作要求 discrete_treatment=True")
    if int(spec["cv"]) < 2:
        raise ConfigError("Causal Forest 的 cv 至少为 2")
    if str(spec["treatment_nuisance_model"]) != "classifier":
        raise ConfigError("二值处理的第一阶段必须是分类器")
    return CausalForestDML(
        model_y=_lightgbm_regressor(cfg, seed=int(seed)),
        model_t=_lightgbm_classifier(cfg, seed=int(seed) + 1),
        discrete_treatment=True,
        n_estimators=int(spec["n_estimators"]),
        min_samples_leaf=int(spec["min_samples_leaf"]),
        max_depth=spec["max_depth"],
        cv=int(spec["cv"]),
        n_jobs=int(spec["n_jobs"]),
        inference=False,
        random_state=int(seed),
    )


# --------------------------------------------------------------------------- #
# 交叉拟合 nuisance 与 AIPW 伪结局
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NuisanceFit:
    """交叉拟合得到的折外结果模型与倾向得分（行序与训练矩阵一致）。

    ``propensity`` 是**最终进入伪结局**的 e；``propensity_raw_min/max`` 是截断前的
    原始范围，``propensity_clipped_count`` 是被截断的样本数。这是
    ``models.propensity.raw_probability_diagnostics_required`` 的落地：截断一旦触发，
    DR 的偏倚不可忽略，该 rep 必须单独标注。``known_design`` 路径不截断，因此
    ``propensity_clip_low/high`` 为 NaN 且计数恒为 0。
    """

    mu1: NDArray[np.float64]
    mu0: NDArray[np.float64]
    propensity: NDArray[np.float64]
    folds: int
    fold_sizes: tuple[int, ...]
    propensity_min: float
    propensity_max: float
    propensity_raw_min: float = float("nan")
    propensity_raw_max: float = float("nan")
    propensity_clipped_count: int = 0
    propensity_clip_low: float = float("nan")
    propensity_clip_high: float = float("nan")
    propensity_source: str = "estimated"
    fold_id: NDArray[np.int64] | None = None

    @property
    def n(self) -> int:
        """样本量。"""
        return int(self.mu1.shape[0])

    @property
    def propensity_mean(self) -> float:
        """最终 e 的均值（审计"估计的 e 是否整体偏离设计概率"）。"""
        return float(np.mean(self.propensity))

    @property
    def clipping_triggered(self) -> bool:
        """截断是否真的发生；True 时该 rep 的 DR 结果必须单独标注。"""
        return self.propensity_clipped_count > 0


@dataclass(frozen=True)
class CrossfitDrAte:
    """交叉拟合 AIPW 的总体 ATE 估计。"""

    ate: float
    se: float
    folds: int
    propensity_min: float
    propensity_max: float
    psi_sd: float
    n: int
    propensity_source: str = "estimated"
    propensity_mean: float = float("nan")
    propensity_raw_min: float = float("nan")
    propensity_raw_max: float = float("nan")
    propensity_clipped_count: int = 0
    propensity_clip_low: float = float("nan")
    propensity_clip_high: float = float("nan")

    @property
    def clipping_triggered(self) -> bool:
        """截断是否真的发生（与 :class:`NuisanceFit` 同一口径）。"""
        return self.propensity_clipped_count > 0


def _crossfit_indices(
    n: int, folds: int, cfg: Config, *, stream: str, seed_index: int
) -> tuple[NDArray[np.int64], ...]:
    if folds < 2:
        raise ConfigError("交叉拟合至少需要 2 折")
    if n < 4 * folds:
        raise ValueError(f"样本量 {n} 太小，无法做 {folds} 折交叉拟合")
    rng = child_rng(_master_seed(cfg), stream, seed_index)
    permuted = rng.permutation(n)
    bounds = np.linspace(0, n, folds + 1).astype(int)
    return tuple(
        np.asarray(permuted[bounds[k]: bounds[k + 1]], dtype=np.int64) for k in range(folds)
    )


def _fold_train_indices(held: NDArray[np.int64], n: int) -> NDArray[np.int64]:
    mask = np.ones(n, dtype=bool)
    mask[held] = False
    return np.flatnonzero(mask)


def _fold_id_vector(
    folds_idx: Sequence[NDArray[np.int64]], n: int
) -> NDArray[np.int64]:
    fold_id = np.full(n, -1, dtype=np.int64)
    for fold, held in enumerate(folds_idx):
        fold_id[held] = fold
    if (fold_id < 0).any():
        raise ValueError("交叉拟合折号未覆盖全部样本")
    return fold_id


def _crossfit_outcomes(
    X: NDArray[np.float64],
    y: NDArray[np.float64],
    t: NDArray[np.int64],
    cfg: Config,
    *,
    folds_idx: Sequence[NDArray[np.int64]],
    seed_index: int,
    seed_prefix: str,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    n = int(X.shape[0])
    mu1 = np.empty(n, dtype=float)
    mu0 = np.empty(n, dtype=float)
    for fold, held in enumerate(folds_idx):
        train_idx = _fold_train_indices(held, n)
        treated = train_idx[t[train_idx] == 1]
        control = train_idx[t[train_idx] == 0]
        if treated.size < 2 or control.size < 2:
            raise ValueError(f"第 {fold} 折训练部分处理组/对照组样本不足，无法交叉拟合")
        seed1 = _seed(cfg, f"{seed_prefix}.fold{fold}.mu1", seed_index)
        seed0 = _seed(cfg, f"{seed_prefix}.fold{fold}.mu0", seed_index)
        model1 = _lightgbm_regressor(cfg, seed=seed1)
        model0 = _lightgbm_regressor(cfg, seed=seed0)
        model1.fit(X[treated], y[treated])
        model0.fit(X[control], y[control])
        mu1[held] = np.asarray(model1.predict(X[held]), dtype=float).reshape(-1)
        mu0[held] = np.asarray(model0.predict(X[held]), dtype=float).reshape(-1)
    return mu1, mu0


def crossfit_two_arm_outcome(
    X: Any,
    y: Any,
    t: Any,
    cfg: Config,
    *,
    fold_id: Any,
    seed_index: int = 0,
    seed_prefix: str = "ope",
    classifier: bool = False,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """在给定折号上交叉拟合两臂结果模型（成本、退款等任意结局）。

    折号必须来自 ``crossfit_nuisance(...,).fold_id``：OPE 的成本/护栏模型要和主结局
    用同一折划分，否则伪结局的残差修正会跨折泄漏。本函数不重新抽折。
    """
    X = _feature_matrix(X)
    n = int(X.shape[0])
    y = _outcome(y, n)
    t = _binary_treatment(t, n, require_both_arms=True)
    fold_id = np.asarray(fold_id, dtype=np.int64).reshape(-1)
    if fold_id.shape != (n,):
        raise ValueError(f"fold_id 长度应为 {n}")
    if (fold_id < 0).any():
        raise ValueError("fold_id 必须是非负整数")
    fold_values = np.unique(fold_id)
    folds_idx = tuple(
        np.asarray(np.flatnonzero(fold_id == value), dtype=np.int64)
        for value in fold_values
    )
    mu1 = np.empty(n, dtype=float)
    mu0 = np.empty(n, dtype=float)
    for fold, held in enumerate(folds_idx):
        train_idx = _fold_train_indices(held, n)
        treated = train_idx[t[train_idx] == 1]
        control = train_idx[t[train_idx] == 0]
        if treated.size < 2 or control.size < 2:
            raise ValueError(f"第 {fold} 折训练部分处理组/对照组样本不足，无法交叉拟合")
        seed1 = _seed(cfg, f"{seed_prefix}.fold{fold}.mu1", seed_index)
        seed0 = _seed(cfg, f"{seed_prefix}.fold{fold}.mu0", seed_index)
        factory = _lightgbm_classifier if classifier else _lightgbm_regressor
        model1 = factory(cfg, seed=seed1)
        model0 = factory(cfg, seed=seed0)
        model1.fit(X[treated], y[treated])
        model0.fit(X[control], y[control])
        if classifier:
            mu1[held] = np.asarray(model1.predict_proba(X[held])[:, 1], dtype=float)
            mu0[held] = np.asarray(model0.predict_proba(X[held])[:, 1], dtype=float)
        else:
            mu1[held] = np.asarray(model1.predict(X[held]), dtype=float).reshape(-1)
            mu0[held] = np.asarray(model0.predict(X[held]), dtype=float).reshape(-1)
    return mu1, mu0


def _crossfit_propensity(
    X: NDArray[np.float64],
    t: NDArray[np.int64],
    cfg: Config,
    *,
    folds_idx: Sequence[NDArray[np.int64]],
    seed_index: int,
    seed_prefix: str,
) -> NDArray[np.float64]:
    """交叉拟合估计 e(X)，返回**未截断**的原始概率。

    截断放到 :func:`crossfit_nuisance`：只有拿到 raw 值才能同时记录截断前范围与被截断
    的样本数（``raw_probability_diagnostics_required``）。
    """
    n = int(X.shape[0])
    propensity = np.empty(n, dtype=float)
    for fold, held in enumerate(folds_idx):
        train_idx = _fold_train_indices(held, n)
        if int((t[train_idx] == 1).sum()) < 2 or int((t[train_idx] == 0).sum()) < 2:
            raise ValueError(f"第 {fold} 折训练部分处理组/对照组样本不足，无法估计倾向得分")
        seed = _seed(cfg, f"{seed_prefix}.fold{fold}.e", seed_index)
        model = _lightgbm_classifier(cfg, seed=seed)
        model.fit(X[train_idx], t[train_idx])
        propensity[held] = np.asarray(model.predict_proba(X[held])[:, 1], dtype=float)
    return propensity


def crossfit_nuisance(
    X: Any,
    y: Any,
    t: Any,
    cfg: Config,
    *,
    seed_index: int = 0,
    folds: int | None = None,
    seed_prefix: str = "dr",
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
) -> NuisanceFit:
    """3 折交叉拟合 ``m1(X)``、``m0(X)``、``e(X)``。

    为什么必须折外：伪结局里出现 ``(Y−m_T(X))/e`` 这一项，如果 ``m_T`` 见过该行，
    残差会被系统性压小，DR 的残差修正项失效。折外预测让每一行的修正项都由"没见过它"
    的模型产生。

    倾向得分来源由 ``propensity_source`` 决定：

    * ``"estimated"``（默认）：交叉拟合 LightGBM 分类器估计 e，按
      ``models.propensity.estimated_probability_clip`` 截断，并记录 raw 范围与截断计数
      （截断引入偏差，必须可审计）；
    * ``"known_design"``：用调用方传入的 ``design_probability`` 真值作 e，**不截断**。
      此时 ``m1/m0`` 仍是折外拟合——只换 e，交叉拟合结构不变。观察性层传这个来源会抛
      :class:`PropensitySourceError`（见 :func:`resolve_propensity_source`）。
    """
    X = _feature_matrix(X)
    n = int(X.shape[0])
    y = _outcome(y, n)
    t = _binary_treatment(t, n, require_both_arms=True)
    source = resolve_propensity_source(cfg, propensity_source)
    # 已知设计概率先校验：非法输入必须在开始拟合之前就报错，而不是算完九次 LightGBM 才报。
    known_design: NDArray[np.float64] | None = None
    if source == "known_design":
        if design_probability is None:
            raise PropensitySourceError(
                "known_design 必须显式传入观测表的 design_probability 列（本函数不猜）"
            )
        known_design = _design_probability_vector(design_probability, n)
    elif design_probability is not None:
        raise PropensitySourceError(
            "design_probability 只在 propensity_source='known_design' 时接受；"
            "默认 estimated 路径不得偷偷换成已知设计概率"
        )
    fold_count = int(cfg.require("models.dr_learner.crossfit_folds") if folds is None else folds)
    folds_idx = _crossfit_indices(
        n, fold_count, cfg, stream=_DR_CROSSFIT_STREAM, seed_index=seed_index
    )
    mu1, mu0 = _crossfit_outcomes(
        X, y, t, cfg, folds_idx=folds_idx, seed_index=seed_index, seed_prefix=seed_prefix
    )
    if known_design is not None:
        raw = known_design
        propensity = raw.copy()
        clip_low = float("nan")
        clip_high = float("nan")
        clipped_count = 0
    else:
        raw = _crossfit_propensity(
            X, t, cfg, folds_idx=folds_idx, seed_index=seed_index, seed_prefix=seed_prefix
        )
        clip_low, clip_high = _estimated_probability_clip(cfg)
        propensity = np.clip(raw, clip_low, clip_high)
        clipped_count = int(np.count_nonzero(propensity != raw))
    return NuisanceFit(
        mu1=mu1,
        mu0=mu0,
        propensity=propensity,
        folds=fold_count,
        fold_sizes=tuple(int(len(idx)) for idx in folds_idx),
        propensity_min=float(propensity.min()),
        propensity_max=float(propensity.max()),
        propensity_raw_min=float(raw.min()),
        propensity_raw_max=float(raw.max()),
        propensity_clipped_count=clipped_count,
        propensity_clip_low=clip_low,
        propensity_clip_high=clip_high,
        propensity_source=source,
        fold_id=_fold_id_vector(folds_idx, n),
    )


def aipw_pseudo_outcome(
    y: Any, t: Any, mu1: Any, mu0: Any, propensity: Any
) -> NDArray[np.float64]:
    """构造增量的 AIPW 伪结局。

    ``ψ = m1−m0 + T(Y−m1)/e − (1−T)(Y−m0)/(1−e)``

    它的均值是 ATE 的无偏（双稳健）估计；把它当作 DR-learner 的回归目标，就得到
    ``τ̂(X)=E[ψ|X]``。``ψ`` 的构造只需要观测到的 ``(T, Y)`` 与折外预测，不需要任何
    反事实。
    """
    y = np.asarray(y, dtype=float).reshape(-1)
    n = y.size
    t = _binary_treatment(t, n, require_both_arms=False)
    mu1 = np.asarray(mu1, dtype=float).reshape(-1)
    mu0 = np.asarray(mu0, dtype=float).reshape(-1)
    e = np.asarray(propensity, dtype=float).reshape(-1)
    for name, array in (("mu1", mu1), ("mu0", mu0), ("propensity", e)):
        if array.shape != (n,):
            raise ValueError(f"{name} 长度应为 {n}，收到 {array.shape}")
        if not np.isfinite(array).all():
            raise ValueError(f"{name} 含非有限值")
    if np.any(e <= 0.0) or np.any(e >= 1.0):
        raise ValueError("倾向得分必须严格落在 (0,1)，重叠假设不成立时不能硬算伪结局")
    return mu1 - mu0 + t * (y - mu1) / e - (1 - t) * (y - mu0) / (1.0 - e)


def crossfit_dr_ate(
    X: Any,
    y: Any,
    t: Any,
    cfg: Config,
    *,
    seed_index: int = 0,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
) -> CrossfitDrAte:
    """交叉拟合 AIPW 的总体 ATE（常数模型的观察性口径与 DR-learner 共享 nuisance）。

    ``se`` 用 ψ 的影响函数近似（``sd(ψ)/√n``），**不校正 nuisance 估计带来的二阶项**；
    正式的区间口径留给 Phase E 的 bootstrap / 影响函数评审。

    ``propensity_source="known_design"`` 时用 ``design_probability`` 真值作 e（不截断），
    只允许随机化层显式开启；默认 ``estimated`` 保持 D.3 已验收口径不变。
    """
    X = _feature_matrix(X)
    n = int(X.shape[0])
    y = _outcome(y, n)
    t = _binary_treatment(t, n, require_both_arms=True)
    nuisance = crossfit_nuisance(
        X,
        y,
        t,
        cfg,
        seed_index=seed_index,
        propensity_source=propensity_source,
        design_probability=design_probability,
    )
    psi = aipw_pseudo_outcome(y, t, nuisance.mu1, nuisance.mu0, nuisance.propensity)
    return CrossfitDrAte(
        ate=float(psi.mean()),
        se=float(psi.std(ddof=1) / np.sqrt(n)),
        folds=nuisance.folds,
        propensity_min=nuisance.propensity_min,
        propensity_max=nuisance.propensity_max,
        psi_sd=float(psi.std(ddof=1)),
        n=n,
        propensity_source=nuisance.propensity_source,
        propensity_mean=nuisance.propensity_mean,
        propensity_raw_min=nuisance.propensity_raw_min,
        propensity_raw_max=nuisance.propensity_raw_max,
        propensity_clipped_count=nuisance.propensity_clipped_count,
        propensity_clip_low=nuisance.propensity_clip_low,
        propensity_clip_high=nuisance.propensity_clip_high,
    )


def _fit_dr_learner(
    X: NDArray[np.float64],
    y: NDArray[np.float64],
    t: NDArray[np.int64],
    cfg: Config,
    *,
    seed_index: int,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
) -> tuple[Any, NDArray[np.float64], dict[str, Any]]:
    spec = cfg.section("models.dr_learner")
    if str(spec["final_model"]) != "lightgbm_regressor":
        raise ConfigError(f"未注册的 DR 最终模型：{spec['final_model']}")
    if str(spec["outcome_model"]) != "lightgbm_regressor":
        raise ConfigError(f"未注册的 DR 结果模型：{spec['outcome_model']}")
    if str(spec["propensity_model"]) != "lightgbm_classifier":
        raise ConfigError(f"未注册的 DR 倾向模型：{spec['propensity_model']}")
    nuisance = crossfit_nuisance(
        X,
        y,
        t,
        cfg,
        seed_index=seed_index,
        propensity_source=propensity_source,
        design_probability=design_probability,
    )
    psi = aipw_pseudo_outcome(y, t, nuisance.mu1, nuisance.mu0, nuisance.propensity)
    final = _lightgbm_regressor(cfg, seed=_seed(cfg, "dr.final", seed_index))
    final.fit(X, psi)
    info = {
        "learner": "dr_learner",
        "final_model": "lightgbm_regressor",
        "crossfit_folds": nuisance.folds,
        "fold_sizes": list(nuisance.fold_sizes),
        "n_train": int(X.shape[0]),
        "n_treated": int((t == 1).sum()),
        "n_control": int((t == 0).sum()),
        "propensity_source": nuisance.propensity_source,
        "propensity_min": nuisance.propensity_min,
        "propensity_max": nuisance.propensity_max,
        "propensity_mean": nuisance.propensity_mean,
        "propensity_raw_min": nuisance.propensity_raw_min,
        "propensity_raw_max": nuisance.propensity_raw_max,
        "propensity_clipped_count": int(nuisance.propensity_clipped_count),
        "propensity_clip_low": nuisance.propensity_clip_low,
        "propensity_clip_high": nuisance.propensity_clip_high,
        "propensity_clipping_detected": bool(nuisance.clipping_triggered),
        "pseudo_outcome_sd": float(psi.std(ddof=1)),
        "dr_ate_training": float(psi.mean()),
        "dr_ate_se_training": float(psi.std(ddof=1) / np.sqrt(psi.size)),
        "hyperparameters": {"lightgbm": _lightgbm_spec(cfg), "dr_learner": spec},
    }
    if nuisance.clipping_triggered:
        info["propensity_clipping_note"] = _CLIPPING_NOTE
    return final, psi, info


def dr_learner_cate(
    X: Any,
    y: Any,
    t: Any,
    X_eval: Any,
    cfg: Config,
    *,
    seed_index: int = 0,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
) -> tuple[NDArray[np.float64], dict[str, Any]]:
    """DR-learner：交叉拟合 nuisance → AIPW 伪结局 → 在 ``(X, ψ)`` 上回归得 CATE。

    ``propensity_source`` 默认 ``"estimated"``（D.3 已验收口径）；
    ``"known_design"`` 需同时传 ``design_probability``，只允许随机化层。
    """
    X = _feature_matrix(X)
    n = int(X.shape[0])
    y = _outcome(y, n)
    t = _binary_treatment(t, n, require_both_arms=True)
    final, _psi, info = _fit_dr_learner(
        X,
        y,
        t,
        cfg,
        seed_index=seed_index,
        propensity_source=propensity_source,
        design_probability=design_probability,
    )
    matrix = _feature_matrix(X_eval, label="X_eval")
    tau = np.asarray(final.predict(matrix), dtype=float).reshape(-1)
    return tau, info


# --------------------------------------------------------------------------- #
# 五个模型
# --------------------------------------------------------------------------- #
def _check_constant_path(cfg: Config, mode: str) -> str:
    path = str(cfg.require(f"models.constant.{mode}"))
    expected = _CONSTANT_PATHS[mode]
    if path != expected:
        raise ConfigError(f"未注册的常数模型 {mode} 口径：{path!r}（应为 {expected!r}）")
    return path


def constant_source(cfg: Config) -> str:
    """返回并校验常数模型在当前识别模式下的口径。

    随机化日志必须走 ``training_itt``，观察性日志必须走
    ``training_crossfit_dr_ate``；配置被改成别的字符串就抛错，不静默换路径。
    """
    return _check_constant_path(cfg, identification_mode(cfg))


def _fit_learner(
    model_name: str,
    X: NDArray[np.float64],
    y: NDArray[np.float64],
    t: NDArray[np.int64],
    cfg: Config,
    *,
    seed_index: int,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
) -> tuple[Callable[[NDArray[np.float64]], NDArray[np.float64]], dict[str, Any]]:
    mode = identification_mode(cfg)
    source = resolve_propensity_source(cfg, propensity_source)
    if source != "estimated" and model_name != "dr_learner":
        raise PropensitySourceError(
            f"{model_name} 不使用 DR 倾向得分，不能指定 propensity_source={source!r}"
        )
    if model_name == "constant":
        path = _check_constant_path(cfg, mode)
        if path == "training_itt":
            treated = y[t == 1]
            control = y[t == 0]
            tau = float(treated.mean() - control.mean())
            info = {
                "constant_source": path,
                "tau_constant": tau,
                "n_treated": int(treated.size),
                "n_control": int(control.size),
                "hyperparameters": {"constant": path},
            }
        else:
            estimate = crossfit_dr_ate(X, y, t, cfg, seed_index=seed_index)
            tau = float(estimate.ate)
            info = {
                "constant_source": path,
                "tau_constant": tau,
                "crossfit_folds": estimate.folds,
                "dr_ate_training": estimate.ate,
                "dr_ate_se_training": estimate.se,
                "propensity_source": estimate.propensity_source,
                "propensity_min": estimate.propensity_min,
                "propensity_max": estimate.propensity_max,
                "propensity_mean": estimate.propensity_mean,
                "propensity_raw_min": estimate.propensity_raw_min,
                "propensity_raw_max": estimate.propensity_raw_max,
                "propensity_clipped_count": int(estimate.propensity_clipped_count),
                "propensity_clip_low": estimate.propensity_clip_low,
                "propensity_clip_high": estimate.propensity_clip_high,
                "propensity_clipping_detected": bool(estimate.clipping_triggered),
                "pseudo_outcome_sd": estimate.psi_sd,
                "hyperparameters": {
                    "constant": path,
                    "lightgbm": _lightgbm_spec(cfg),
                    "dr_learner": cfg.section("models.dr_learner"),
                },
            }
            if estimate.clipping_triggered:
                info["propensity_clipping_note"] = _CLIPPING_NOTE

        def predict_constant(X_eval: NDArray[np.float64]) -> NDArray[np.float64]:
            rows = int(np.asarray(X_eval).shape[0])
            return np.full(rows, tau, dtype=float)

        return predict_constant, info

    if model_name == "t_learner":
        treated = t == 1
        model1 = _lightgbm_regressor(cfg, seed=_seed(cfg, "t_learner.treated", seed_index))
        model0 = _lightgbm_regressor(cfg, seed=_seed(cfg, "t_learner.control", seed_index))
        model1.fit(X[treated], y[treated])
        model0.fit(X[~treated], y[~treated])
        info = {
            "learner": "t_learner",
            "n_treated": int(treated.sum()),
            "n_control": int((~treated).sum()),
            "hyperparameters": {"lightgbm": _lightgbm_spec(cfg)},
        }

        def predict_t_learner(X_eval: NDArray[np.float64]) -> NDArray[np.float64]:
            return np.asarray(model1.predict(X_eval), dtype=float) - np.asarray(
                model0.predict(X_eval), dtype=float
            )

        return predict_t_learner, info

    if model_name == "s_learner":
        design = np.column_stack([X, t.astype(float)])
        model = _lightgbm_regressor(cfg, seed=_seed(cfg, "s_learner", seed_index))
        model.fit(design, y)
        info = {
            "learner": "s_learner",
            "n_treated": int((t == 1).sum()),
            "n_control": int((t == 0).sum()),
            "note": "处理指示作为普通特征进入模型，正则化会收缩处理效应",
            "hyperparameters": {"lightgbm": _lightgbm_spec(cfg)},
        }

        def predict_s_learner(X_eval: NDArray[np.float64]) -> NDArray[np.float64]:
            rows = int(X_eval.shape[0])
            with_one = np.column_stack([X_eval, np.ones(rows)])
            with_zero = np.column_stack([X_eval, np.zeros(rows)])
            return np.asarray(model.predict(with_one), dtype=float) - np.asarray(
                model.predict(with_zero), dtype=float
            )

        return predict_s_learner, info

    if model_name == "causal_forest":
        estimator = causal_forest_estimator(cfg, seed=_seed(cfg, "causal_forest", seed_index))
        estimator.fit(y, t, X=X)
        info = {
            "learner": "causal_forest",
            "engine": "econml.CausalForestDML",
            "hyperparameters": {"causal_forest": cfg.section("models.causal_forest"),
                                "lightgbm": _lightgbm_spec(cfg)},
        }

        def predict_causal_forest(X_eval: NDArray[np.float64]) -> NDArray[np.float64]:
            return np.asarray(estimator.effect(X_eval), dtype=float).reshape(-1)

        return predict_causal_forest, info

    if model_name == "dr_learner":
        final, _psi, info = _fit_dr_learner(
            X,
            y,
            t,
            cfg,
            seed_index=seed_index,
            propensity_source=source,
            design_probability=design_probability,
        )

        def predict_dr_learner(X_eval: NDArray[np.float64]) -> NDArray[np.float64]:
            return np.asarray(final.predict(X_eval), dtype=float).reshape(-1)

        return predict_dr_learner, info

    raise ValueError(f"未知模型 {model_name!r}；可用：{MODEL_NAMES}")


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Predictions:
    """一次模型拟合的个体效应与元信息。

    ``test_keys`` 与 ``tau_test`` 行序一一对应，只读；下游要改写请先 ``.copy()``。
    """

    model_name: str
    tau_test: NDArray[np.float64]
    tau_validation: NDArray[np.float64]
    ate: float
    test_keys: pd.DataFrame = field(repr=False, compare=False)
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def tau_sd_test(self) -> float:
        """测试集个体效应的标准差（异质性的描述，不是精度）。"""
        return _sd(self.tau_test)


def _as_tau(values: Any, n: int, *, label: str) -> NDArray[np.float64]:
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (n,):
        raise ValueError(f"{label} 的个体效应长度应为 {n}，收到 {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{label} 的个体效应含非有限值")
    return array


def fit_predict(
    model_name: str,
    dataset: LearningData | ObservedDataset,
    cfg: Config,
    *,
    time_mode: str = "static",
    seed_index: int = 0,
    propensity_source: str = "estimated",
    design_probability: Any | None = None,
) -> Predictions:
    """拟合一个主模型并返回测试集个体 ``τ̂``、ATE 与元信息。

    参数
    ----
    model_name : ``constant / t_learner / s_learner / causal_forest / dr_learner``。
    dataset    : 已拆分的 :class:`LearningData`（推荐：同 rep 只准备一次），或
                 :class:`ObservedDataset`（内部会按同样规则准备，预处理器确定性一致）。
    cfg        : 场景配置；必须与数据集的 ``config_hash`` 一致。
    time_mode  : 与 :func:`prepare_learning_data` 一致；已有 ``LearningData`` 时必须相同。
    seed_index : 重复编号，驱动 ``random_state`` 与交叉拟合折号。
    propensity_source : DR 倾向来源，默认 ``"estimated"``（D.3 已验收口径）。
                 ``"known_design"`` 是显式敏感性开关：随机化层用训练切分的
                 ``design_probability`` 真值作 e、不截断；未传 ``design_probability``
                 时自动取 ``data.train.design_probability``。观察性层传它直接抛
                 :class:`PropensitySourceError`。
    design_probability : 已知设计概率向量（仅 ``known_design`` 接受）。

    返回
    ----
    :class:`Predictions`；``info`` 内含超参、训练 CPU 秒、特征数、``preprocessor_hash``、
    ``config_hash``、``observed_hash`` 与三个切分的用户键指纹。
    """
    if model_name not in MODEL_NAMES:
        raise ValueError(f"未知模型 {model_name!r}；可用：{MODEL_NAMES}")
    require_model_applicable(model_name, cfg)
    if design_probability is not None and str(propensity_source) == "estimated":
        raise PropensitySourceError(
            "design_probability 只在 propensity_source='known_design' 时接受；"
            "默认 estimated 路径不得偷偷换成已知设计概率"
        )
    if isinstance(dataset, LearningData):
        data = dataset
        if data.time_mode != time_mode:
            raise ValueError(
                f"数据的时间特征模式为 {data.time_mode!r}，与调用参数 {time_mode!r} 不一致"
            )
    else:
        data = prepare_learning_data(dataset, cfg, time_mode=time_mode)
    if data.config_hash != cfg.hash(64):
        raise ValueError("学习数据与当前场景配置不一致，不能跨配置做配对比较")
    if data.level != str(cfg.require("active_scenario.level")):
        raise ValueError("学习数据的层级与当前场景配置不一致")
    if str(propensity_source) == "known_design" and design_probability is None:
        design_probability = data.train.design_probability

    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    predict_fn, model_info = _fit_learner(
        model_name,
        data.train.X,
        data.train.y,
        data.train.treatment,
        cfg,
        seed_index=seed_index,
        propensity_source=propensity_source,
        design_probability=design_probability,
    )
    train_cpu = time.process_time() - cpu_start
    train_wall = time.perf_counter() - wall_start

    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    tau_validation = _as_tau(predict_fn(data.validation.X), data.validation.n, label="validation")
    tau_test = _as_tau(predict_fn(data.test.X), data.test.n, label="test")
    predict_cpu = time.process_time() - cpu_start
    predict_wall = time.perf_counter() - wall_start

    info: dict[str, Any] = {
        "model": model_name,
        "level": data.level,
        "identification_mode": data.identification_mode,
        "time_mode": data.time_mode,
        "n_features": len(data.feature_names),
        "feature_names": list(data.feature_names),
        "preprocessor_hash": data.preprocessor_hash,
        "config_hash": data.config_hash,
        "observed_hash": data.observed_hash,
        "train_n": data.train.n,
        "validation_n": data.validation.n,
        "test_n": data.test.n,
        "train_user_key_hash": data.train.key_hash,
        "validation_user_key_hash": data.validation.key_hash,
        "test_user_key_hash": data.test.key_hash,
        "train_cpu_seconds": float(train_cpu),
        "train_wall_seconds": float(train_wall),
        "predict_cpu_seconds": float(predict_cpu),
        "predict_wall_seconds": float(predict_wall),
        "total_cpu_seconds": float(train_cpu + predict_cpu),
        "seed_index": int(seed_index),
    }
    info.update(model_info)
    return Predictions(
        model_name=model_name,
        tau_test=tau_test,
        tau_validation=tau_validation,
        ate=float(tau_test.mean()),
        test_keys=data.test.keys.copy(),
        info=info,
    )


# --------------------------------------------------------------------------- #
# 验证集打分：只用验证集观测数据
# --------------------------------------------------------------------------- #
def _require_truth_free_selection(cfg: Config) -> None:
    scoring = str(cfg.require("models.selection.scoring"))
    if scoring != _SCORING_NAME:
        raise ConfigError(f"未注册的模型选择打分：{scoring!r}")
    if not bool(cfg.require("models.selection.true_effect_tuning_forbidden")):
        raise ConfigError("模型选择必须禁止使用真值调参（true_effect_tuning_forbidden）")


def _default_cost_per_user(cfg: Config, n: int) -> NDArray[np.float64]:
    face = float(cfg.require("policy.face_value_cny"))
    redemption = float(cfg.require("business.redemption_rate"))
    floor = float(cfg.require("policy.cost_model.cost_floor_cny"))
    return np.full(n, max(face * redemption, floor), dtype=float)


@dataclass(frozen=True)
class ValidationScorer:
    """冻结在验证集上的交叉拟合 AIPW 伪结局；对任意 ``τ̂`` 都能打分。

    伪结局只依赖验证集的 ``(X, T, Y)`` 与折外 nuisance，与被评模型无关，所以同一次
    实验里所有模型共用同一个 scorer（既省算力，又保证"差异只来自模型"）。
    """

    psi: NDArray[np.float64] = field(repr=False)
    folds: int
    propensity_source: str
    propensity_min: float
    propensity_max: float
    ess_treated: float
    ess_control: float
    scoring: str = _SCORING_NAME

    @property
    def n(self) -> int:
        """验证集用户数。"""
        return int(self.psi.shape[0])

    def score(
        self,
        tau_validation: Any,
        cfg: Config,
        *,
        budget_per_user_cny: float | None = None,
        cost_per_user_cny: Any | None = None,
    ) -> dict[str, Any]:
        """在给定预算下把 ``τ̂`` 变成一条策略，并给出 DR 策略价值的 95% 单侧下界。

        下界用 ``sd(πψ)/√n`` 的影响函数近似，未校正"策略本身也是用同一批 τ̂ 选出来的"
        这一学习不确定性；跨模型的比较结论属 Phase E 的正式评估口径。
        """
        _require_truth_free_selection(cfg)
        values = np.asarray(tau_validation, dtype=float).reshape(-1)
        if values.shape != (self.n,):
            raise ValueError(f"验证集个体效应长度应为 {self.n}，收到 {values.shape}")
        if not np.isfinite(values).all():
            raise ValueError("验证集个体效应含非有限值")
        budget_per_user = float(
            cfg.require("policy.budget.base_per_user_cny")
            if budget_per_user_cny is None
            else budget_per_user_cny
        )
        if budget_per_user < 0:
            raise ValueError("人均预算不能为负")
        if cost_per_user_cny is None:
            cost = _default_cost_per_user(cfg, self.n)
        else:
            cost = np.broadcast_to(np.asarray(cost_per_user_cny, dtype=float), (self.n,)).copy()
            if not np.isfinite(cost).all() or (cost < 0).any():
                raise ValueError("每人成本必须非负且有限")
        budget = budget_per_user * self.n
        pick = greedy_by_ratio(values, cost, budget)
        selected = pick.policy.astype(float)
        contribution = selected * self.psi
        policy_value = float(contribution.mean())
        se = float(contribution.std(ddof=1) / np.sqrt(self.n))
        level = float(cfg.require("evaluation.confidence_level"))
        if not 0.5 < level < 1:
            raise ConfigError("置信水平必须落在 (0.5, 1)")
        z = float(NormalDist().inv_cdf(level))
        return {
            "scoring": self.scoring,
            "policy_value": policy_value,
            "policy_value_se": se,
            "policy_value_lcb": policy_value - z * se,
            "confidence_level": level,
            "z": z,
            "n_validation": self.n,
            "n_selected": int(pick.n_selected),
            "selected_fraction": float(pick.n_selected / self.n),
            "spend_cny": float(cost[selected.astype(bool)].sum()),
            "budget_cny": float(budget),
            "budget_per_user_cny": budget_per_user,
            "cost_per_user_mean_cny": float(cost.mean()),
            "mean_psi": float(self.psi.mean()),
            "tau_mean": float(values.mean()),
            "tau_positive_fraction": float((values > 0).mean()),
            "propensity_source": self.propensity_source,
            "crossfit_folds": self.folds,
            "ess_treated": self.ess_treated,
            "ess_control": self.ess_control,
        }

    def score_grid(self, tau_validation: Any, cfg: Config) -> list[dict[str, Any]]:
        """遍历冻结的 ``policy.budget.per_user_grid_cny`` 预算网格。"""
        budgets = [float(value) for value in cfg.require("policy.budget.per_user_grid_cny")]
        if not budgets:
            raise ConfigError("预算网格为空")
        return [self.score(tau_validation, cfg, budget_per_user_cny=budget) for budget in budgets]


def _effective_sample_size(weight: NDArray[np.float64]) -> float:
    total = float(weight.sum())
    if total <= 0:
        return 0.0
    return float(total * total / float(np.square(weight).sum()))


def fit_validation_scorer(
    data: LearningData, cfg: Config, *, seed_index: int = 0
) -> ValidationScorer:
    """只用验证集观测数据拟合打分器（交叉拟合结果模型 + 倾向得分）。

    随机化模式使用**记录的设计概率**（``evaluation.randomized_propensity``）；
    观察性模式只用已观测特征估计倾向得分（``evaluation.observational_propensity``），
    并按 ``models.propensity.estimated_probability_clip`` 截断。
    """
    block = data.validation
    if data.config_hash != cfg.hash(64):
        raise ValueError("学习数据与当前场景配置不一致")
    _require_truth_free_selection(cfg)
    folds = int(cfg.require("evaluation.crossfit_folds"))
    folds_idx = _crossfit_indices(
        block.n, folds, cfg, stream="v3.models.scorer.crossfit", seed_index=seed_index
    )
    mu1, mu0 = _crossfit_outcomes(
        block.X, block.y, block.treatment, cfg,
        folds_idx=folds_idx, seed_index=seed_index, seed_prefix="scorer",
    )
    if data.identification_mode == "randomized":
        if str(cfg.require("evaluation.randomized_propensity")) != "recorded_design_probability":
            raise ConfigError("随机化验证集必须使用记录的设计概率")
        if not block.has_design_probability:
            raise ValueError("随机化验证集缺少记录的设计概率")
        propensity = np.asarray(block.design_probability, dtype=float)
        source = "recorded_design_probability"
    else:
        mechanism = str(cfg.require("evaluation.observational_propensity"))
        if mechanism != "estimated_from_observed_features_only":
            raise ConfigError("观察性验证集的倾向得分只能用已观测特征估计")
        raw_propensity = _crossfit_propensity(
            block.X, block.treatment, cfg,
            folds_idx=folds_idx, seed_index=seed_index, seed_prefix="scorer",
        )
        clip_low, clip_high = _estimated_probability_clip(cfg)
        propensity = np.clip(raw_propensity, clip_low, clip_high)
        source = "estimated_lightgbm_classifier"
    bounds = [
        float(value)
        for value in cfg.require("evaluation.reliability_gate.probability_support_bounds")
    ]
    violation = float(np.mean((propensity < bounds[0]) | (propensity > bounds[1])))
    limit = float(
        cfg.require("evaluation.reliability_gate.maximum_observed_support_violation_fraction")
    )
    if violation > limit:
        raise ValueError(f"验证集倾向得分支持不足（越界比例 {violation:.4f}），无法可靠评估")
    psi = aipw_pseudo_outcome(block.y, block.treatment, mu1, mu0, propensity)
    treated = block.treatment == 1
    return ValidationScorer(
        psi=psi,
        folds=folds,
        propensity_source=source,
        propensity_min=float(propensity.min()),
        propensity_max=float(propensity.max()),
        ess_treated=_effective_sample_size(1.0 / propensity[treated]),
        ess_control=_effective_sample_size(1.0 / (1.0 - propensity[~treated])),
    )


def rank_models(
    predictions: Mapping[str, Predictions],
    scorer: ValidationScorer,
    cfg: Config,
    *,
    budget_per_user_cny: float | None = None,
) -> list[dict[str, Any]]:
    """只用验证集排序模型：冻结预算网格上 LCB 的算术平均为主键，并列按配置顺序。"""
    _require_truth_free_selection(cfg)
    if not predictions:
        raise ValueError("没有可排序的模型")
    tie_order = [str(name) for name in cfg.require("models.selection.tie_break_order")]
    if budget_per_user_cny is None:
        budgets = [float(value) for value in cfg.require("policy.budget.per_user_grid_cny")]
    else:
        budgets = [float(budget_per_user_cny)]
    if not budgets:
        raise ConfigError("预算网格为空")
    rows: list[dict[str, Any]] = []
    for name, prediction in predictions.items():
        if name != prediction.model_name:
            raise ValueError(f"键 {name!r} 与 Predictions.model_name={prediction.model_name!r} 不一致")
        per_budget = [
            scorer.score(prediction.tau_validation, cfg, budget_per_user_cny=budget)
            for budget in budgets
        ]
        lcbs = [row["policy_value_lcb"] for row in per_budget]
        rows.append(
            {
                "model": name,
                "selection_score": float(np.mean(lcbs)),
                "worst_budget_lcb": float(np.min(lcbs)),
                "budgets_cny_per_user": budgets,
                "policy_value_lcb_by_budget": lcbs,
                "validation_n": scorer.n,
                "tie_break_index": tie_order.index(name) if name in tie_order else len(tie_order),
            }
        )
    rows.sort(key=lambda row: (-row["selection_score"], row["tie_break_index"], row["model"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


# --------------------------------------------------------------------------- #
# 学习曲线：只报规模 vs 稳定性 / 验证集指标
# --------------------------------------------------------------------------- #
def _learning_subsample(n: int, count: int, cfg: Config, seed_index: int) -> NDArray[np.int64]:
    if count <= 0:
        raise ValueError("学习曲线的训练规模必须为正")
    if count > n:
        raise ValueError(f"训练规模 {count} 超过可用训练用户 {n}")
    rng = child_rng(_master_seed(cfg), _LEARNING_CURVE_STREAM, seed_index)
    permutation = rng.permutation(n)
    return np.sort(np.asarray(permutation[:count], dtype=np.int64))


def _stability_corr(left: NDArray[np.float64], right: NDArray[np.float64]) -> float:
    if left.size < 2 or float(np.ptp(left)) == 0.0 or float(np.ptp(right)) == 0.0:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def learning_curve(
    model_name: str,
    dataset: LearningData | ObservedDataset,
    cfg: Config,
    *,
    counts: Sequence[int] | None = None,
    time_mode: str = "static",
    seed_index: int = 0,
    scorer: ValidationScorer | None = None,
) -> list[dict[str, Any]]:
    """在 ``learning_curve_training_counts`` 指定的训练规模上重训，报告规模效应。

    **不使用真值**：每行只给训练规模、验证集个体效应的离散度、固定 scorer 下的策略价值
    下界，以及相对最大训练规模的预测稳定性（RMSE / 相关系数）。真值误差留给最终审计。

    子样本 stream 不含模型名，因此同一 rep 内所有模型在每个规模上看到**同一批训练行**
    （``models.yaml → data_selection_seed_scope: shared_across_models_within_rep``）。
    预处理状态保持训练切分上冻结的那一份不变，规模效应不会与预处理器重估混在一起。
    """
    if model_name not in MODEL_NAMES:
        raise ValueError(f"未知模型 {model_name!r}；可用：{MODEL_NAMES}")
    require_model_applicable(model_name, cfg)
    if isinstance(dataset, LearningData):
        data = dataset
        if data.time_mode != time_mode:
            raise ValueError(
                f"数据的时间特征模式为 {data.time_mode!r}，与调用参数 {time_mode!r} 不一致"
            )
    else:
        data = prepare_learning_data(dataset, cfg, time_mode=time_mode)
    requested = (
        [int(value) for value in cfg.require("models.learning_curve_training_counts")]
        if counts is None
        else [int(value) for value in counts]
    )
    usable = sorted({count for count in requested if 0 < count <= data.train.n})
    if not usable:
        raise ValueError(f"训练用户只有 {data.train.n} 个，没有任何可用的学习曲线规模：{requested}")
    selector = fit_validation_scorer(data, cfg, seed_index=seed_index) if scorer is None else scorer
    if selector.n != data.validation.n:
        raise ValueError("验证集打分器与当前学习数据的验证集规模不一致")

    rows: list[dict[str, Any]] = []
    tau_by_count: dict[int, NDArray[np.float64]] = {}
    for count in usable:
        indices = _learning_subsample(data.train.n, count, cfg, seed_index)
        cpu_start = time.process_time()
        predict_fn, _info = _fit_learner(
            model_name,
            data.train.X[indices],
            data.train.y[indices],
            data.train.treatment[indices],
            cfg,
            seed_index=seed_index,
        )
        train_cpu = time.process_time() - cpu_start
        tau_validation = _as_tau(
            predict_fn(data.validation.X), data.validation.n, label="validation"
        )
        score = selector.score(tau_validation, cfg)
        tau_by_count[count] = tau_validation
        rows.append(
            {
                "model": model_name,
                "n_train": int(count),
                "n_train_available": int(data.train.n),
                "n_features": len(data.feature_names),
                "tau_mean_validation": float(tau_validation.mean()),
                "tau_sd_validation": _sd(tau_validation),
                "validation_policy_value": score["policy_value"],
                "validation_policy_value_lcb": score["policy_value_lcb"],
                "validation_n_selected": score["n_selected"],
                "train_cpu_seconds": float(train_cpu),
                "subsample_key_hash": user_key_hash(data.train.keys.iloc[indices]),
                "preprocessor_hash": data.preprocessor_hash,
                "config_hash": data.config_hash,
            }
        )
    reference_count = max(usable)
    reference = tau_by_count[reference_count]
    for row in rows:
        tau = tau_by_count[row["n_train"]]
        row["stability_rmse_vs_largest"] = float(np.sqrt(np.mean(np.square(tau - reference))))
        row["stability_corr_vs_largest"] = _stability_corr(tau, reference)
        row["reference_n_train"] = int(reference_count)
    return rows


# --------------------------------------------------------------------------- #
# 冒烟：小规模实测 CPU 秒与 τ̂ 离散度（不是正式 R）
# --------------------------------------------------------------------------- #
_SMOKE_MODELS: tuple[str, ...] = MODEL_NAMES


def _prepare_dataset(
    scenario: str, n: int, *, rep_id: int
) -> tuple[Config, ObservedDataset, Any]:
    """生成 → 五表清洗 → SQL 观测表；同时返回**仅供审计**的种群对象。

    观测侧只用 ``dataset``；返回的 population 只允许交给
    :func:`_audit_truth_for_test`，不得进入特征构造或模型选择。
    """
    from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
    from causal_growth.data.v3_quality import validate_tables
    from causal_growth.data.v3_sql import run_sql_pipeline
    from causal_growth.data.v3_tables import build_raw_tables
    from causal_growth.dgp.v3_engine import generate_v3_population
    from causal_growth.v3_config import load_v3_protocol

    cfg = load_v3_protocol().scenario(scenario)
    population = generate_v3_population(cfg, rep_id=rep_id, n=n)
    users, assignments, orders = population.observation_bundle()
    stream = f"v3.models.smoke.{scenario}"
    raw = build_raw_tables(
        users, assignments, orders, cfg,
        run_id=f"smoke:{scenario}", rep_id=rep_id, stream_prefix=stream,
    )
    dirty = inject_dirt(raw, cfg, rep_id=rep_id, stream_prefix=stream)
    clean = deduplicate_events(dirty.tables, cfg)
    raw_sql = run_sql_pipeline(raw, cfg)
    raw_dataset = ObservedDataset.from_sql_result(raw_sql, cfg)
    split_dataset, _split_manifest = raw_dataset.assign_splits(
        cfg, stream=f"{stream}.split", index=rep_id
    )
    labels = split_dataset.observations.set_index(["run_id", "user_id"]).split
    for tables in (raw, dirty.tables, clean.tables):
        keys = pd.MultiIndex.from_frame(tables["users"][["run_id", "user_id"]])
        tables["users"]["split"] = labels.reindex(keys).to_numpy()
    clean_sql = run_sql_pipeline(clean.tables, cfg)
    dataset = ObservedDataset.from_sql_result(clean_sql, cfg)
    # 与 build_observed_pipeline 相同：结果表只来自 SQL，不在这里重算利润。
    raw["user_outcomes"] = raw_sql.user_outcomes.copy(deep=True)
    clean.tables["user_outcomes"] = clean_sql.user_outcomes.copy(deep=True)
    dirty.tables["user_outcomes"] = clean_sql.user_outcomes.copy(deep=True)
    validate_tables(clean.tables, cfg, stage="clean", require_outcomes=True)
    return cfg, dataset, population


def _smoke_observed_dataset(
    scenario: str, n: int, *, rep_id: int
) -> tuple[Config, ObservedDataset]:
    """冒烟专用包装：只返回观测侧，真值不进入冒烟链路。"""
    cfg, dataset, _population_audit = _prepare_dataset(scenario, n, rep_id=rep_id)
    return cfg, dataset


def run_smoke(
    *,
    scenario: str = "L1_main",
    n: int = 20_000,
    rep_id: int = 0,
    out_path: str | None = None,
) -> pd.DataFrame:
    """n=20,000、一个 L1 场景、五个模型各跑一次，落 CPU 秒 / τ̂ sd / ATE。

    冒烟表**不含任何真值列**，只用于确认接口可用与量级，不构成正式结果。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    target = Path(out_path) if out_path is not None else (
        root / "outputs" / "tables" / "v3_phase_D_models_smoke.csv"
    )
    cfg, dataset = _smoke_observed_dataset(scenario, n, rep_id=rep_id)
    data = prepare_learning_data(dataset, cfg)
    selector = fit_validation_scorer(data, cfg, seed_index=rep_id)
    split_hash = data.split_fingerprint
    rows: list[dict[str, Any]] = []
    for model_name in _SMOKE_MODELS:
        prediction = fit_predict(model_name, data, cfg, seed_index=rep_id)
        score = selector.score(prediction.tau_validation, cfg)
        rows.append(
            {
                "source_label": "合成数据 / 已知 DGP",
                "scenario": scenario,
                "level": data.level,
                "identification_mode": data.identification_mode,
                "model": model_name,
                "rep_id": rep_id,
                "n_total": int(len(dataset.observations)),
                "n_train": data.train.n,
                "n_validation": data.validation.n,
                "n_test": data.test.n,
                "n_features": prediction.info["n_features"],
                "train_cpu_seconds": prediction.info["train_cpu_seconds"],
                "predict_cpu_seconds": prediction.info["predict_cpu_seconds"],
                "total_cpu_seconds": prediction.info["total_cpu_seconds"],
                "ate_test": prediction.ate,
                "tau_sd_test": prediction.tau_sd_test,
                "tau_mean_validation": float(prediction.tau_validation.mean()),
                "tau_sd_validation": _sd(prediction.tau_validation),
                "validation_policy_value_lcb": score["policy_value_lcb"],
                "validation_policy_value": score["policy_value"],
                "validation_n_selected": score["n_selected"],
                "preprocessor_hash": data.preprocessor_hash,
                "config_hash": data.config_hash,
                "observed_hash": data.observed_hash,
                "split_fingerprint": split_hash,
                "train_user_key_hash": data.train.key_hash,
                "validation_user_key_hash": data.validation.key_hash,
                "test_user_key_hash": data.test.key_hash,
                "constant_source": prediction.info.get("constant_source", ""),
                "crossfit_folds": int(prediction.info.get("crossfit_folds", 0)),
            }
        )
    frame = pd.DataFrame(rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, encoding="utf-8-sig")
    return frame


# --------------------------------------------------------------------------- #
# D03 交付物：逐用户 9 列导出（provisional，供 E 编排消费）
# --------------------------------------------------------------------------- #
def _observations_for_keys(
    dataset: ObservedDataset, keys: pd.DataFrame, columns: Sequence[str]
) -> pd.DataFrame:
    """按 ``(run_id, user_id)`` 把观测表对齐到某个切分的行序。"""
    observations = dataset.observations
    key_columns = ["run_id", "user_id"]
    if observations.duplicated(key_columns).any():
        raise ValueError("观测表的 (run_id, user_id) 必须唯一")
    wanted = pd.MultiIndex.from_frame(keys.loc[:, key_columns])
    block = observations.set_index(key_columns).reindex(wanted)
    # 键没对上时整行为 NaN；列内缺失（例如未加购用户的 cart_value）留给调用方按口径处理。
    if block.isna().all(axis=1).any():
        raise ValueError("切分用户未能全部对齐到观测表")
    return block.loc[:, list(columns)].reset_index(drop=True)


def _fit_level_baselines(
    data: LearningData,
    train_observed: pd.DataFrame,
    test_X: NDArray[np.float64],
    cfg: Config,
    *,
    seed_index: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """两个**水平量**基线：购买倾向 ``p̂`` 与 ``p̂ × m̂``（不是增量）。

    - ``p̂``：训练集上 LightGBM 分类 ``paid_purchase_7d``；
    - ``m̂``：训练集**购买者**上回归 ``net_profit + coupon_cost``（券前利润），负值截 0；
    - ``predicted_profit = p̂ × m̂``，与 E 接口文档的 ``p̂·m̂`` 口径一致。
    """
    purchase_label = train_observed["paid_purchase_7d"].to_numpy(dtype=np.int64)
    if np.unique(purchase_label).size < 2:
        raise ValueError("训练集购买标签没有变异，无法拟合购买倾向基线")
    propensity_model = _lightgbm_classifier(
        cfg, seed=_seed(cfg, "v3.models.d03.purchase", seed_index)
    ).fit(data.train.X, purchase_label)
    propensity = np.asarray(propensity_model.predict_proba(test_X)[:, 1], dtype=np.float64)

    buyers = purchase_label == 1
    if int(buyers.sum()) < 10:
        raise ValueError(f"训练集购买者只有 {int(buyers.sum())} 人，无法拟合利润水平基线")
    pre_coupon_profit = data.train.y + train_observed["coupon_cost"].to_numpy(dtype=np.float64)
    margin_model = _lightgbm_regressor(
        cfg, seed=_seed(cfg, "v3.models.d03.margin", seed_index)
    ).fit(data.train.X[buyers], pre_coupon_profit[buyers])
    margin = np.maximum(np.asarray(margin_model.predict(test_X), dtype=np.float64), 0.0)
    if not np.isfinite(propensity).all():
        raise ValueError("购买倾向基线含非有限值")
    return propensity, propensity * margin


def _audit_truth_for_test(
    population_audit: Any, cfg: Config, test_keys: pd.DataFrame
) -> pd.DataFrame:
    """**audit-only**：读取两个潜在世界的已实现账本，返回测试用户的 ``tau_true`` 与 ``cost_true``。

    物理隔离约定：

    - 本函数是唯一允许把真值带出 population 的入口；
    - 输出只含 ``tau_true`` / ``cost_true``，不带任何特征或预测列；
    - 调用方必须在**选人列已冻结之后**才允许合并本函数的返回值。
    """
    from causal_growth.dgp.v3_engine import audit_realized_worlds

    audit_worlds = audit_realized_worlds(population_audit, cfg)
    if set(audit_worlds) != {0, 1}:
        raise ValueError(f"审计世界应恰为 {{0, 1}}，收到 {sorted(audit_worlds)}")
    audit_treated = audit_worlds[1].set_index("user_id")
    audit_control = audit_worlds[0].set_index("user_id")
    if not audit_treated.index.is_unique or not audit_control.index.is_unique:
        raise ValueError("审计账本的 user_id 必须唯一")
    audit_user_ids = test_keys["user_id"].to_numpy()
    missing = ~np.isin(audit_user_ids, audit_treated.index.to_numpy())
    if missing.any():
        raise ValueError(f"审计账本缺少 {int(missing.sum())} 个测试用户")
    tau_true_audit = (
        audit_treated.loc[audit_user_ids, "net_profit"].to_numpy(dtype=np.float64)
        - audit_control.loc[audit_user_ids, "net_profit"].to_numpy(dtype=np.float64)
    )
    cost_true_audit = audit_treated.loc[audit_user_ids, "coupon_cost"].to_numpy(dtype=np.float64)
    if not np.isfinite(tau_true_audit).all() or not np.isfinite(cost_true_audit).all():
        raise ValueError("审计真值含非有限值")
    return pd.DataFrame({"tau_true": tau_true_audit, "cost_true": cost_true_audit})


@dataclass(frozen=True)
class _D03Rep:
    """单 rep 的 D03 产物。

    ``truth`` / ``frame`` 里的真值两列只在 7 列选人字段冻结后才构造；
    其余字段与真值无关，不得反向引用。
    """

    cfg: Config
    dataset: ObservedDataset
    data: LearningData
    ranking: list[dict[str, Any]]
    predictions: dict[str, Predictions]
    chosen_model: str
    selection: pd.DataFrame
    truth: pd.DataFrame
    frame: pd.DataFrame
    cart_value_missing: int
    cost_model: Any
    cost_hat: NDArray[np.float64]
    propensity: NDArray[np.float64]
    predicted_profit: NDArray[np.float64]


def _d03_rep_artifacts(
    *,
    scenario: str,
    n: int,
    rep_id: int,
    models: Sequence[str] | None,
    time_mode: str,
) -> _D03Rep:
    """单 rep 的固定链路：观测表 → 学习数据 → 全模型 → 验证集选模 → 冻结 → 合并真值。

    导出与诊断共用本函数，保证两条路径的选模/冻结/真值隔离口径完全一致。
    """
    names = tuple(MODEL_NAMES if models is None else models)
    if not names:
        raise ValueError("至少需要一个模型")
    unknown = [name for name in names if name not in MODEL_NAMES]
    if unknown:
        raise ValueError(f"未知模型 {unknown}；可用：{MODEL_NAMES}")

    cfg, dataset, population_audit = _prepare_dataset(scenario, n, rep_id=rep_id)
    data = prepare_learning_data(dataset, cfg, time_mode=time_mode)
    scorer = fit_validation_scorer(data, cfg, seed_index=rep_id)
    predictions = {
        name: fit_predict(name, data, cfg, time_mode=time_mode, seed_index=rep_id)
        for name in names
    }
    ranking = rank_models(predictions, scorer, cfg)
    chosen_model = str(ranking[0]["model"])

    train_observed = _observations_for_keys(
        dataset, data.train.keys, ("paid_purchase_7d", "coupon_cost")
    )
    test_observed = _observations_for_keys(
        dataset, data.test.keys, ("is_new", "cart_value")
    )
    cart_value_missing = int(test_observed["cart_value"].isna().sum())
    propensity, predicted_profit = _fit_level_baselines(
        data, train_observed, data.test.X, cfg, seed_index=rep_id
    )
    cost_model = fit_cost_model(
        data.train.X,
        data.train.treatment,
        train_observed["paid_purchase_7d"].to_numpy(dtype=np.int64),
        train_observed["coupon_cost"].to_numpy(dtype=np.float64),
        cfg,
    )
    cost_hat = np.asarray(predict_expected_cost(cost_model, data.test.X, cfg), dtype=np.float64)

    selection = pd.DataFrame(
        {
            "user_id": data.test.keys["user_id"].to_numpy(),
            "is_new": test_observed["is_new"].to_numpy(dtype=np.int64),
            # 未加购用户的 cart_value 在观测表里为空；对 E 的规则与预算语义而言等价于 0。
            "cart_value": test_observed["cart_value"].fillna(0.0).to_numpy(dtype=np.float64),
            "purchase_propensity": propensity,
            "predicted_profit": predicted_profit,
            "tau_hat": predictions[chosen_model].tau_test,
            "cost_hat": cost_hat,
        }
    )
    selection_columns = list(D03_EXPORT_COLUMNS[:7])
    truth_columns = list(D03_EXPORT_COLUMNS[7:])
    if list(selection.columns) != selection_columns:
        raise ValueError("选人列顺序与 E 契约不一致")
    if not selection["user_id"].is_unique:
        raise ValueError("导出表的 user_id 必须唯一")
    numeric = selection.loc[
        :, ["cart_value", "purchase_propensity", "predicted_profit", "tau_hat", "cost_hat"]
    ]
    if not np.isfinite(numeric.to_numpy(dtype=np.float64)).all():
        raise ValueError("选人列含非有限值")
    if ((selection["purchase_propensity"] < 0) | (selection["purchase_propensity"] > 1)).any():
        raise ValueError("purchase_propensity 必须落在 [0, 1]")
    if (selection["cost_hat"] <= 0).any():
        raise ValueError("cost_hat 必须严格为正（成本下界失效）")

    # 选人列到此已冻结；真值只在下面这一次合并里出现。
    truth_audit = _audit_truth_for_test(population_audit, cfg, data.test.keys)
    frame = selection.copy()
    for column in truth_columns:
        frame[column] = truth_audit[column].to_numpy(dtype=np.float64)
    frame = frame.loc[:, list(D03_EXPORT_COLUMNS)]
    return _D03Rep(
        cfg=cfg,
        dataset=dataset,
        data=data,
        ranking=ranking,
        predictions=predictions,
        chosen_model=chosen_model,
        selection=selection,
        truth=truth_audit,
        frame=frame,
        cart_value_missing=cart_value_missing,
        cost_model=cost_model,
        cost_hat=cost_hat,
        propensity=propensity,
        predicted_profit=predicted_profit,
    )


def export_d03_predictions(
    *,
    scenario: str = "L1_main",
    n: int = 20_000,
    rep_id: int = 0,
    out_csv: str | None = None,
    meta_path: str | None = None,
    models: Sequence[str] | None = None,
    time_mode: str = "static",
) -> dict[str, Any]:
    """产出 E 阶段固定 9 列 CSV（**provisional**，不是正式 R 的结果）。

    回答"D03 的交付物到底是什么"：不是模型结果表，而是
    ``user_id, is_new, cart_value, purchase_propensity, predicted_profit,
    tau_hat, cost_hat, tau_true, cost_true`` 的逐用户表。

    流程固定为：观测表 → 学习数据 → 5 个模型 → 验证集打分选模 →
    **冻结 7 列选人字段** → 最后才合并 audit-only 真值两列。
    ``tau_true`` / ``cost_true`` 不参与任何拟合、选模或排序。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    target = (
        Path(out_csv)
        if out_csv is not None
        else root / "outputs" / "tables" / "v3_phase_D03_predictions_provisional.csv"
    )
    meta_target = (
        Path(meta_path) if meta_path is not None else target.with_name(f"{target.stem}_meta.json")
    )
    art = _d03_rep_artifacts(
        scenario=scenario, n=n, rep_id=rep_id, models=models, time_mode=time_mode
    )
    cfg, data, frame = art.cfg, art.data, art.frame
    ranking, chosen_model = art.ranking, art.chosen_model
    prediction = art.predictions[chosen_model]
    cost_model, cost_hat = art.cost_model, art.cost_hat
    selection_columns = list(D03_EXPORT_COLUMNS[:7])
    truth_columns = list(D03_EXPORT_COLUMNS[7:])

    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, encoding="utf-8-sig")

    def _label(path: Path) -> str:
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            return str(path)

    written_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="minutes")
    meta: dict[str, Any] = {
        "status": "provisional",
        "formal_r": False,
        "source_label": "合成数据 / 已知 DGP",
        "scenario": scenario,
        "level": data.level,
        "identification_mode": data.identification_mode,
        "time_mode": data.time_mode,
        "rep_id": rep_id,
        "n_total": int(len(art.dataset.observations)),
        "n_train": data.train.n,
        "n_validation": data.validation.n,
        "n_test": data.test.n,
        "csv": _label(target),
        "csv_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "columns": list(D03_EXPORT_COLUMNS),
        "selection_columns": selection_columns,
        "truth_columns": truth_columns,
        "truth_isolation": {
            "producer": "_audit_truth_for_test",
            "source": "V3Population.audit_potential_orders",
            "joined_after_selection_columns_frozen": True,
            "used_for_selection": False,
            "used_for_model_selection": False,
        },
        "model_selection": {
            "scoring": str(cfg.require("models.selection.scoring")),
            "chosen_model": chosen_model,
            "models_fitted": list(art.predictions),
            "ranking": ranking,
        },
        "level_baselines": {
            "purchase_propensity": "LightGBM P(paid_purchase_7d=1|X)，训练集全部用户",
            "predicted_profit": "purchase_propensity × LightGBM E[net_profit+coupon_cost|X,purchased=1]，负值截 0",
            "cart_value_missing_filled_zero": art.cart_value_missing,
        },
        "cost_model": {
            "target": str(cost_model.target),
            "fitted_on": str(cost_model.fitted_on),
            "cost_hat_min_cny": float(cost_hat.min()),
            "cost_hat_mean_cny": float(cost_hat.mean()),
            "cost_hat_max_cny": float(cost_hat.max()),
        },
        "predictions": {
            "tau_hat_mean_test": float(prediction.ate),
            "tau_hat_sd_test": float(prediction.tau_sd_test),
        },
        "truth": {
            "tau_true_mean_test": float(frame["tau_true"].mean()),
            "tau_true_sd_test": float(frame["tau_true"].std(ddof=1)),
            "cost_true_mean_test": float(frame["cost_true"].mean()),
        },
        "hashes": {
            "config_hash": data.config_hash,
            "observed_hash": data.observed_hash,
            "preprocessor_hash": data.preprocessor_hash,
            "split_fingerprint": data.split_fingerprint,
            "train_user_key_hash": data.train.key_hash,
            "validation_user_key_hash": data.validation.key_hash,
            "test_user_key_hash": data.test.key_hash,
        },
        "written_at_beijing": written_at,
    }
    meta_target.parent.mkdir(parents=True, exist_ok=True)
    meta_target.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    meta["meta_path"] = _label(meta_target)
    return meta


# --------------------------------------------------------------------------- #
# D03 诊断：多 rep 偏差、校准与策略网格（不是正式 R）
# --------------------------------------------------------------------------- #
_SUMMARY_STAT_COLUMNS: tuple[str, ...] = (
    "tau_hat_mean",
    "bias_mean",
    "relative_bias",
    "calibration_slope",
    "calibration_intercept",
    "pearson_r",
    "rmse",
    "mae",
    "error_q10",
    "error_q50",
    "error_q90",
)


def _calibration_stats(tau_hat: Any, tau_true: Any) -> dict[str, float]:
    """逐用户 τ̂ 对真值的偏差、校准斜率与误差分位。

    ``calibration_slope`` 是 ``tau_true ~ a + b·tau_hat`` 的 OLS 斜率 ``b``，
    满足 ``b = r·σ_true/σ_hat``。``b < 1`` 可能来自相关系数低（回归稀释），也可能来自
    σ̂ 大于 σ_true，**单看 b 不能判定过离散**；须同时报告 ``sd(τ̂)``、``sd(τ_true)`` 与 ``r``。
    τ̂ 无变异时斜率与相关系数无定义，返回 ``nan``。

    退化判定用相对极差，不用 ``var > 0``：常数列（如 ``constant`` 模型）
    的浮点求均值会残留 ~1e-16 的伪方差，直接相除会得到毫无意义的斜率。
    """
    hat = np.asarray(tau_hat, dtype=float).reshape(-1)
    truth = np.asarray(tau_true, dtype=float).reshape(-1)
    if hat.size != truth.size or hat.size == 0:
        raise ValueError("tau_hat 与 tau_true 必须等长且非空")
    if not (np.isfinite(hat).all() and np.isfinite(truth).all()):
        raise ValueError("校准统计输入含非有限值")
    error = hat - truth
    count = error.size
    mean_truth = float(truth.mean())

    def _degenerate(values: NDArray[np.float64]) -> bool:
        scale = max(float(np.abs(values).max()), 1.0)
        return float(np.ptp(values)) <= 1e-12 * scale

    slope = float("nan")
    intercept = float("nan")
    corr = float("nan")
    if not _degenerate(hat):
        var_hat = float(hat.var(ddof=0))
        slope = float(np.cov(hat, truth, ddof=0)[0, 1] / var_hat)
        intercept = float(mean_truth - slope * float(hat.mean()))
        if not _degenerate(truth):
            corr = float(np.corrcoef(hat, truth)[0, 1])
    q10, q50, q90 = (float(value) for value in np.quantile(error, [0.1, 0.5, 0.9]))
    return {
        "bias_mean": float(error.mean()),
        "bias_se": float(error.std(ddof=1) / np.sqrt(count)) if count > 1 else float("nan"),
        "relative_bias": float(error.mean() / mean_truth) if mean_truth != 0 else float("nan"),
        "calibration_slope": slope,
        "calibration_intercept": intercept,
        "pearson_r": corr,
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "mae": float(np.abs(error).mean()),
        "error_sd": float(error.std(ddof=1)) if count > 1 else float("nan"),
        "error_q10": q10,
        "error_q50": q50,
        "error_q90": q90,
    }


def _aggregate_metrics(per_rep: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """把逐 rep 指标聚合成按模型的均值/离散/最差值。

    相对偏差按 AGENTS §12.5 报 ``worst_abs_relative_bias``，分母是**同一 rep 的**
    ``mean(tau_true)``；跨 rep 的均值区间用 t(df = n-1)，因为 20 个 rep 是独立抽样。
    """
    from scipy import stats as scipy_stats

    summary: dict[str, dict[str, Any]] = {}
    for model, block in per_rep.groupby("model", sort=False):
        row: dict[str, Any] = {
            "n_reps": int(len(block)),
            "chosen_count": int(block["chosen"].sum()),
        }
        for column in _SUMMARY_STAT_COLUMNS:
            values = block[column].to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            row[f"{column}_mean"] = float(finite.mean()) if finite.size else None
            row[f"{column}_sd"] = float(finite.std(ddof=1)) if finite.size > 1 else None
            row[f"{column}_min"] = float(finite.min()) if finite.size else None
            row[f"{column}_max"] = float(finite.max()) if finite.size else None
        bias = block["bias_mean"].to_numpy(dtype=float)
        bias = bias[np.isfinite(bias)]
        if bias.size > 1:
            half = float(
                scipy_stats.t.ppf(0.975, bias.size - 1) * bias.std(ddof=1) / np.sqrt(bias.size)
            )
            row["bias_mean_ci95"] = [float(bias.mean() - half), float(bias.mean() + half)]
        else:
            row["bias_mean_ci95"] = None
        row["positive_bias_reps"] = int((bias > 0).sum())
        relative = block["relative_bias"].to_numpy(dtype=float)
        relative = relative[np.isfinite(relative)]
        row["worst_abs_relative_bias"] = float(np.abs(relative).max()) if relative.size else None
        row["relative_bias_denominator"] = "同一 rep 的 mean(tau_true)"
        slope = block["calibration_slope"].to_numpy(dtype=float)
        slope = slope[np.isfinite(slope)]
        row["slope_defined_reps"] = int(slope.size)
        row["calibration_slope_median"] = float(np.median(slope)) if slope.size else None
        row["slope_below_one_reps"] = int((slope < 1).sum())
        row["slope_denominator"] = "仅有限斜率 rep（τ̂ 有变异）"
        summary[str(model)] = row
    return summary


def _compliance_stats(counts: pd.Series, n_budgets: int) -> dict[str, Any]:
    """把"每个 rep 有多少预算点合规"压成均值/最差/全合规 rep 数。"""
    values = counts.to_numpy(dtype=int)
    return {
        "mean_compliant_budgets": float(values.mean()),
        "min_compliant_budgets": int(values.min()),
        "max_compliant_budgets": int(values.max()),
        "reps_all_compliant": int((values == n_budgets).sum()),
    }


def _aggregate_policy_grid(grid: pd.DataFrame, policies: Sequence[str]) -> dict[str, Any]:
    """策略 × 预算的跨 rep 汇总：真实人均价值与双口径预算合规。"""
    budgets = sorted(float(value) for value in grid["per_user_budget_cny"].unique())
    mean_value = grid.pivot_table(
        index="policy", columns="per_user_budget_cny", values="true_value_per_user",
        aggfunc="mean", dropna=False,
    )
    sd_value = grid.pivot_table(
        index="policy", columns="per_user_budget_cny", values="true_value_per_user",
        aggfunc="std", dropna=False,
    )
    mean_selected = grid.pivot_table(
        index="policy", columns="per_user_budget_cny", values="n_selected",
        aggfunc="mean", dropna=False,
    )
    mean_spend = grid.pivot_table(
        index="policy", columns="per_user_budget_cny", values="actual_spend_cny",
        aggfunc="mean", dropna=False,
    )
    compliance: dict[str, Any] = {}
    for policy in policies:
        block = grid.loc[grid["policy"] == policy]
        by_hat = block.groupby("rep_id")["within_budget_by_hat"].sum()
        by_true = block.groupby("rep_id")["within_budget_by_true"].sum()
        compliance[str(policy)] = {
            "n_budgets": len(budgets),
            "reps": int(block["rep_id"].nunique()),
            "by_hat": _compliance_stats(by_hat, len(budgets)),
            "by_true": _compliance_stats(by_true, len(budgets)),
        }

    def _table(source: pd.DataFrame) -> dict[str, list[float | None]]:
        return {
            str(policy): [
                None if pd.isna(source.loc[policy, budget]) else float(source.loc[policy, budget])
                for budget in budgets
            ]
            for policy in policies
        }

    return {
        "budgets_cny_per_user": budgets,
        "policies": [str(policy) for policy in policies],
        "mean_true_value_per_user": _table(mean_value),
        "sd_true_value_per_user": _table(sd_value),
        "mean_n_selected": _table(mean_selected),
        "mean_actual_spend_cny": _table(mean_spend),
        "compliance": compliance,
    }


def run_d03_diagnostic(
    *,
    scenario: str = "L1_main",
    n: int = 20_000,
    reps: int = 20,
    out_dir: str | None = None,
    models: Sequence[str] | None = None,
    time_mode: str = "static",
    rep_start: int = 0,
    rep_stop: int | None = None,
    formal: bool = False,
    progress: bool = True,
) -> dict[str, Any]:
    """多 rep 诊断/正式 R：τ̂ 偏差、校准与策略网格。

    回答"D03 正式 R 该怎么排"：同一场景、同一 n，rep 之间只换种子。每个 rep
    的选模仍只用冻结的验证集 LCB；真值只在**选模结束后**用于评估，且同时评估
    全部候选模型（选模不使用真值，评估使用真值是允许的）。

    产物三件：``per_rep``（rep × 模型指标）、``policy_grid``（rep × 模型 × 预算 ×
    策略；同一批用户分别用每个模型的 τ̂ 重跑策略，``chosen=True`` 的子集即"按冻结
    规则选中模型"的口径）、``summary``（跨 rep 聚合与哈希）。

    ``rep_start`` / ``rep_stop`` 用于把正式 R 切成互不重叠的分片；每个 rep 的
    随机流只由 ``rep_id`` 决定，因此分片结果与单进程全量跑逐位一致。``formal``
    只改变 summary 的状态标签，不改变任何计算路径。
    """
    from pathlib import Path

    from causal_growth.policy.v3_policy_grid import POLICIES as E_POLICIES
    from causal_growth.policy.v3_policy_grid import evaluate_policy_grid

    if reps <= 0:
        raise ValueError("reps 必须为正")
    if rep_stop is None:
        rep_stop = rep_start + reps
    if rep_start < 0 or rep_stop <= rep_start:
        raise ValueError(f"rep 区间无效：[{rep_start}, {rep_stop})")
    rep_ids = list(range(rep_start, rep_stop))
    root = Path(__file__).resolve().parents[3]
    target_dir = Path(out_dir) if out_dir is not None else root / "outputs" / "tables"
    target_dir.mkdir(parents=True, exist_ok=True)

    metric_rows: list[dict[str, Any]] = []
    grid_frames: list[pd.DataFrame] = []
    reps_meta: list[dict[str, Any]] = []
    chosen_counts: dict[str, int] = {}
    config_hash = ""
    level = ""
    identification = ""
    selection_rule = ""

    for rep_id in rep_ids:
        rep_started = time.perf_counter()
        art = _d03_rep_artifacts(
            scenario=scenario, n=n, rep_id=rep_id, models=models, time_mode=time_mode
        )
        if rep_id == rep_start:
            config_hash = art.data.config_hash
            level = art.data.level
            identification = art.data.identification_mode
            selection_rule = str(art.cfg.require("models.selection.scoring"))
        tau_true = art.frame["tau_true"].to_numpy(dtype=float)
        rank_by_model = {str(row["model"]): row for row in art.ranking}
        for name, prediction in art.predictions.items():
            rank_row = rank_by_model[str(name)]
            metric_rows.append(
                {
                    "rep_id": rep_id,
                    "model": str(name),
                    "chosen": name == art.chosen_model,
                    "rank": int(rank_row["rank"]),
                    "selection_score": float(rank_row["selection_score"]),
                    "validation_n": int(rank_row["validation_n"]),
                    "n_test": int(tau_true.size),
                    "tau_hat_mean": float(prediction.ate),
                    "tau_hat_sd": float(prediction.tau_sd_test),
                    "tau_true_mean": float(tau_true.mean()),
                    **_calibration_stats(prediction.tau_test, tau_true),
                }
            )
        for name, prediction in art.predictions.items():
            alternate = art.frame.copy()
            alternate["tau_hat"] = prediction.tau_test
            model_grid = evaluate_policy_grid(alternate, art.cfg)
            model_grid.insert(0, "chosen", name == art.chosen_model)
            model_grid.insert(0, "model", str(name))
            model_grid.insert(0, "rep_id", rep_id)
            grid_frames.append(model_grid)
        chosen_counts[art.chosen_model] = chosen_counts.get(art.chosen_model, 0) + 1
        elapsed = time.perf_counter() - rep_started
        if progress:
            print(
                f"[D03 rep {rep_id}] chosen={art.chosen_model} "
                f"score={float(rank_by_model[art.chosen_model]['selection_score']):.4f} "
                f"elapsed={elapsed:.1f}s",
                flush=True,
            )
        reps_meta.append(
            {
                "rep_id": rep_id,
                "n_total": int(len(art.dataset.observations)),
                "n_train": art.data.train.n,
                "n_validation": art.data.validation.n,
                "n_test": art.data.test.n,
                "chosen_model": art.chosen_model,
                "observed_hash": art.data.observed_hash,
                "split_fingerprint": art.data.split_fingerprint,
                "test_user_key_hash": art.data.test.key_hash,
                "elapsed_seconds": round(elapsed, 3),
            }
        )

    per_rep = pd.DataFrame(metric_rows)
    grid_frame = pd.concat(grid_frames, ignore_index=True)
    n_budgets = int(grid_frame["per_user_budget_cny"].nunique())
    n_models = int(grid_frame["model"].nunique())
    expected_grid_rows = len(rep_ids) * n_models * n_budgets * len(E_POLICIES)
    if len(grid_frame) != expected_grid_rows:
        raise ValueError(
            f"策略网格行数应为 {expected_grid_rows}，实际 {len(grid_frame)}"
        )
    chosen_per_rep = grid_frame.groupby("rep_id")["chosen"].sum()
    if not (chosen_per_rep == n_budgets * len(E_POLICIES)).all():
        raise ValueError("每个 rep 必须恰有一个模型的 chosen 标记覆盖整张网格")

    per_rep_path = target_dir / "v3_phase_D03_diagnostic_per_rep.csv"
    grid_path = target_dir / "v3_phase_D03_diagnostic_policy_grid.csv"
    summary_path = target_dir / "v3_phase_D03_diagnostic_summary.json"
    per_rep.to_csv(per_rep_path, index=False, encoding="utf-8-sig")
    grid_frame.to_csv(grid_path, index=False, encoding="utf-8-sig")

    def _label(path: Path) -> str:
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            return str(path)

    summary: dict[str, Any] = {
        "status": "formal_r" if formal else "diagnostic",
        "formal_r": bool(formal),
        "purpose": (
            "正式 R：同一场景逐 rep 拟合全部候选模型，验证集 LCB 选模，"
            "真值仅在选模后用于评估；策略网格按模型配对"
            if formal
            else "多 rep 诊断 τ̂ 偏差/校准/策略网格；不是正式 R，不作验收证据"
        ),
        "source_label": "合成数据 / 已知 DGP",
        "scenario": scenario,
        "level": level,
        "identification_mode": identification,
        "time_mode": time_mode,
        "n_per_rep": int(n),
        "reps": len(rep_ids),
        "rep_ids": rep_ids,
        "selection_rule": selection_rule,
        "truth_isolation": {
            "producer": "_audit_truth_for_test",
            "source": "V3Population.audit_potential_orders",
            "used_for_selection": False,
            "used_for_model_selection": False,
            "used_for_evaluation": True,
        },
        "chosen_model_counts": chosen_counts,
        "models": _aggregate_metrics(per_rep),
        "chosen_model_rows": _aggregate_metrics(per_rep.loc[per_rep["chosen"]]),
        "policy_grid": _aggregate_policy_grid(
            grid_frame.loc[grid_frame["chosen"]], E_POLICIES
        ),
        "policy_grid_by_model": {
            str(model): _aggregate_policy_grid(block, E_POLICIES)
            for model, block in grid_frame.groupby("model", sort=False)
        },
        "reps_meta": reps_meta,
        "config_hash": config_hash,
        "written_at_beijing": datetime.now(timezone(timedelta(hours=8))).isoformat(
            timespec="minutes"
        ),
        "outputs": {
            "per_rep": _label(per_rep_path),
            "policy_grid": _label(grid_path),
            "summary": _label(summary_path),
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return summary


# --------------------------------------------------------------------------- #
# C7 敏感性对照：未调整 ITT vs DR(估计倾向) vs DR(已知设计概率)
# --------------------------------------------------------------------------- #
def itt_estimate(y: Any, t: Any) -> tuple[float, float]:
    """未调整 ITT：两组均值差 + 两组独立方差和的平方根标准误。

    这是随机化层"不做任何调整"的基准估计量，也是 ``constant`` 在随机化层的口径
    （``models.constant.randomized: training_itt``）。这里只做总体 ATE，不做协变量调整。
    """
    values = np.asarray(y, dtype=float).reshape(-1)
    labels = _binary_treatment(t, values.size, require_both_arms=True)
    treated = values[labels == 1]
    control = values[labels == 0]
    ate = float(treated.mean() - control.mean())
    variance = treated.var(ddof=1) / treated.size + control.var(ddof=1) / control.size
    return ate, float(np.sqrt(variance))


def _sensitivity_row(
    *,
    scenario: str,
    rep_id: int,
    reps: int,
    data: LearningData,
    n_total: int,
    itt: tuple[float, float],
    estimated: CrossfitDrAte,
    known: CrossfitDrAte,
) -> dict[str, Any]:
    """一行 = 一个 (场景, rep) 的三个估计量与两个效率比值。"""
    itt_ate, itt_se = itt
    design = np.asarray(data.train.design_probability, dtype=float)
    if not np.isfinite(design).all():
        raise ValueError("敏感性对照的随机化层必须有逐人设计概率")
    return {
        "source_label": "合成数据 / 已知 DGP",
        "row_kind": "rep",
        "scenario": scenario,
        "level": data.level,
        "identification_mode": data.identification_mode,
        "rep_id": int(rep_id),
        "n_reps": int(reps),
        "n_total": int(n_total),
        "n_train": data.train.n,
        "n_treated": int((data.train.treatment == 1).sum()),
        "n_control": int((data.train.treatment == 0).sum()),
        "n_features": len(data.feature_names),
        "design_probability_min": float(design.min()),
        "design_probability_max": float(design.max()),
        "estimated_probability_clip_low": float(estimated.propensity_clip_low),
        "estimated_probability_clip_high": float(estimated.propensity_clip_high),
        "itt_ate": float(itt_ate),
        "itt_se": float(itt_se),
        "dr_estimated_ate": float(estimated.ate),
        "dr_estimated_se": float(estimated.se),
        "dr_estimated_propensity_mean": float(estimated.propensity_mean),
        "dr_estimated_propensity_min": float(estimated.propensity_min),
        "dr_estimated_propensity_max": float(estimated.propensity_max),
        "dr_estimated_propensity_raw_min": float(estimated.propensity_raw_min),
        "dr_estimated_propensity_raw_max": float(estimated.propensity_raw_max),
        "dr_estimated_propensity_clipped_count": int(estimated.propensity_clipped_count),
        "dr_estimated_clipping_detected": bool(estimated.clipping_triggered),
        "dr_known_ate": float(known.ate),
        "dr_known_se": float(known.se),
        "dr_known_propensity_mean": float(known.propensity_mean),
        "dr_known_propensity_min": float(known.propensity_min),
        "dr_known_propensity_max": float(known.propensity_max),
        "dr_known_propensity_clipped_count": int(known.propensity_clipped_count),
        "dr_known_clipping_detected": bool(known.clipping_triggered),
        "se_ratio_dr_estimated_over_itt": float(estimated.se / itt_se),
        "se_ratio_dr_known_over_itt": float(known.se / itt_se),
        "ate_diff_dr_estimated_minus_itt": float(estimated.ate - itt_ate),
        "ate_diff_dr_known_minus_itt": float(known.ate - itt_ate),
        "ate_diff_dr_known_minus_estimated": float(known.ate - estimated.ate),
        "config_hash": data.config_hash,
        "preprocessor_hash": data.preprocessor_hash,
        "observed_hash": data.observed_hash,
        "train_user_key_hash": data.train.key_hash,
        "split_fingerprint": data.split_fingerprint,
    }


def _sensitivity_mean_row(
    scenario: str, rows: Sequence[Mapping[str, Any]], *, reps: int
) -> dict[str, Any]:
    """把一个场景的逐 rep 行压成一行均值。

    比值取**逐 rep 比值的算术平均**（不是用均值 ATE/SE 重算的比值），与逐 rep 行同口径；
    这样某个 ATE/SE 特别大的 rep 不会因为先平均分子分母而改变比值的含义。
    """
    if not rows:
        raise ValueError("没有可汇总的敏感性行")
    first = rows[0]
    mean_row: dict[str, Any] = {}
    for key, value in first.items():
        if key in {"rep_id", "n_reps"}:
            continue
        if isinstance(value, bool):
            mean_row[key] = any(bool(row[key]) for row in rows)
        elif isinstance(value, (int, float)):
            mean_row[key] = float(np.mean([float(row[key]) for row in rows]))
        else:
            mean_row[key] = value
    for key in ("n_total", "n_train", "n_treated", "n_control", "n_features",
                "dr_estimated_propensity_clipped_count", "dr_known_propensity_clipped_count"):
        mean_row[key] = int(round(float(mean_row[key])))
    mean_row.update(
        row_kind="mean_over_reps",
        scenario=scenario,
        rep_id=-1,
        n_reps=int(reps),
        observed_hash="",
        train_user_key_hash="",
        split_fingerprint="",
    )
    return {key: mean_row[key] for key in first}


def run_propensity_sensitivity(
    *,
    scenarios: Sequence[str] = _SENSITIVITY_SCENARIOS,
    n: int = _SENSITIVITY_MAX_N,
    reps: int = 3,
    out_path: str | None = None,
) -> pd.DataFrame:
    """C7 效率对照：未调整 ITT vs DR(估计倾向) vs DR(已知设计概率)。

    回答"随机化层用估计倾向而不是已知设计概率，代价是多少效率"。三个估计量消费
    **同一个训练切分**；DR 的两个来源共享 ``m1/m0`` 的折外拟合（同一 ``seed_index``
    下逐元素相同），只有 e 不同，所以两条 DR 路径的差异只可能来自 e。具体是 SE 还是 ATE
    被推走、推走多少，由实测决定（本函数不预设结论，结果见文档 §13）。

    **这是效率对照，不是正确性对照**：脚本不读任何真值列，也不落真值列。

    资源纪律（机器上还有正式 AA 作业在跑）：``n`` 必须 ≤ ``_SENSITIVITY_MAX_N``，
    ``reps`` 必须 ≤ ``_SENSITIVITY_MAX_REPS``，超限直接抛错，不静默缩规模。
    每个场景除逐 rep 行外，额外落一行 ``row_kind="mean_over_reps"`` 的均值行。

    产物：``outputs/tables/v3_phase_D_models_sensitivity.csv``（utf-8-sig）。
    """
    from pathlib import Path

    if not scenarios:
        raise ValueError("C7 敏感性对照至少需要一个随机化场景")
    if not 0 < int(n) <= _SENSITIVITY_MAX_N:
        raise ValueError(
            f"C7 敏感性对照的 n 必须 ≤ {_SENSITIVITY_MAX_N}（当前机器有正式作业在跑）"
        )
    if not 0 < int(reps) <= _SENSITIVITY_MAX_REPS:
        raise ValueError(f"C7 敏感性对照的 R 必须 ≤ {_SENSITIVITY_MAX_REPS}")
    root = Path(__file__).resolve().parents[3]
    target = Path(out_path) if out_path is not None else (
        root / "outputs" / "tables" / "v3_phase_D_models_sensitivity.csv"
    )
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_rows: list[dict[str, Any]] = []
        for rep in range(int(reps)):
            cfg, dataset = _smoke_observed_dataset(scenario, int(n), rep_id=rep)
            data = prepare_learning_data(dataset, cfg)
            if data.identification_mode != "randomized":
                raise PropensitySourceError(
                    f"{scenario} 是 {data.identification_mode} 层，已知设计概率对照只适用于随机化层"
                )
            X, y, t = data.train.X, data.train.y, data.train.treatment
            itt = itt_estimate(y, t)
            estimated = crossfit_dr_ate(X, y, t, cfg, seed_index=rep)
            known = crossfit_dr_ate(
                X,
                y,
                t,
                cfg,
                seed_index=rep,
                propensity_source="known_design",
                design_probability=data.train.design_probability,
            )
            row = _sensitivity_row(
                scenario=scenario,
                rep_id=rep,
                reps=int(reps),
                data=data,
                n_total=int(len(dataset.observations)),
                itt=itt,
                estimated=estimated,
                known=known,
            )
            scenario_rows.append(row)
            rows.append(row)
        rows.append(_sensitivity_mean_row(scenario, scenario_rows, reps=int(reps)))
    frame = pd.DataFrame(rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, encoding="utf-8-sig")
    return frame


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="D.3 模型冒烟（小规模，不构成正式结果）")
    parser.add_argument("--scenario", default="L1_main")
    parser.add_argument("--n", type=int, default=20_000)
    parser.add_argument("--rep", type=int, default=0)
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="跑 C7 倾向来源效率对照（ITT / DR-estimated / DR-known_design），"
             f"n≤{_SENSITIVITY_MAX_N}、R≤{_SENSITIVITY_MAX_REPS}",
    )
    parser.add_argument(
        "--scenarios",
        default=",".join(_SENSITIVITY_SCENARIOS),
        help="敏感性对照的场景列表（逗号分隔，需为随机化层）",
    )
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument(
        "--export",
        action="store_true",
        help="导出 E 编排所需的 9 列逐用户 CSV（provisional，不是正式 R）",
    )
    parser.add_argument("--export-csv", default=None)
    parser.add_argument("--export-meta", default=None)
    parser.add_argument(
        "--model",
        default=None,
        help="导出时只用逗号分隔的模型子集（默认全部 5 个；选模仍走验证集打分）",
    )
    parser.add_argument("--time-mode", default="static")
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="跑多 rep D03 诊断（偏差/校准/策略网格；不是正式 R）",
    )
    parser.add_argument(
        "--diagnostic-reps",
        type=int,
        default=20,
        help="诊断 rep 数（默认 20，按 2026-10-27 的裁决）",
    )
    parser.add_argument("--diag-dir", default=None, help="诊断产物目录（默认 outputs/tables）")
    parser.add_argument("--rep-start", type=int, default=0, help="起始 rep（分片用，含）")
    parser.add_argument("--rep-stop", type=int, default=None, help="结束 rep（分片用，不含；缺省为 start+reps）")
    parser.add_argument(
        "--formal-r",
        action="store_true",
        help="把本次诊断运行标记为正式 R（计算路径不变，只改状态标签与 purpose）",
    )
    args = parser.parse_args(argv)
    models = (
        None
        if not args.model
        else tuple(piece.strip() for piece in args.model.split(",") if piece.strip())
    )
    if args.diagnostic:
        summary = run_d03_diagnostic(
            scenario=args.scenario,
            n=args.n,
            reps=args.diagnostic_reps,
            out_dir=args.diag_dir,
            models=models,
            time_mode=args.time_mode,
            rep_start=args.rep_start,
            rep_stop=args.rep_stop,
            formal=args.formal_r,
        )
        print(
            json.dumps(
                {
                    "status": summary["status"],
                    "scenario": summary["scenario"],
                    "reps": summary["reps"],
                    "chosen_model_counts": summary["chosen_model_counts"],
                    "bias_mean_by_model": {
                        name: row["bias_mean_mean"] for name, row in summary["models"].items()
                    },
                    "summary": summary["outputs"]["summary"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.export:
        meta = export_d03_predictions(
            scenario=args.scenario,
            n=args.n,
            rep_id=args.rep,
            out_csv=args.export_csv,
            meta_path=args.export_meta,
            models=models,
            time_mode=args.time_mode,
        )
        print(
            json.dumps(
                {
                    "status": meta["status"],
                    "scenario": meta["scenario"],
                    "chosen_model": meta["model_selection"]["chosen_model"],
                    "n_test": meta["n_test"],
                    "csv": meta["csv"],
                    "meta": meta["meta_path"],
                    "tau_hat_mean_test": meta["predictions"]["tau_hat_mean_test"],
                    "tau_true_mean_test": meta["truth"]["tau_true_mean_test"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.sensitivity:
        frame = run_propensity_sensitivity(
            scenarios=[piece.strip() for piece in args.scenarios.split(",") if piece.strip()],
            n=args.n,
            reps=args.reps,
            out_path=args.out,
        )
        with pd.option_context("display.width", 220, "display.max_columns", 60):
            print(
                frame[
                    [
                        "scenario",
                        "row_kind",
                        "rep_id",
                        "n_train",
                        "itt_ate",
                        "itt_se",
                        "dr_estimated_ate",
                        "dr_estimated_se",
                        "dr_known_ate",
                        "dr_known_se",
                        "se_ratio_dr_estimated_over_itt",
                        "se_ratio_dr_known_over_itt",
                    ]
                ].to_string(index=False)
            )
        return 0
    frame = run_smoke(scenario=args.scenario, n=args.n, rep_id=args.rep, out_path=args.out)
    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print(
            frame[
                [
                    "model",
                    "n_train",
                    "n_test",
                    "train_cpu_seconds",
                    "total_cpu_seconds",
                    "ate_test",
                    "tau_sd_test",
                    "validation_policy_value_lcb",
                ]
            ].to_string(index=False)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
