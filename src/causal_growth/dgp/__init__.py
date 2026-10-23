"""DGP 子包：L0–L4 分层数据生成与真值。

对外只暴露 ``build`` 与少数工具函数；层级实现细节留在 ``levels`` 里。
"""

from __future__ import annotations

from typing import Any, Callable

from causal_growth.config import Config
from causal_growth.contracts import (
    CONVERT_WINDOW,
    FEATURE_ORDER,
    PROFIT_WINDOW,
    Covariates,
    GroundTruth,
    Population,
    PotentialOutcomes,
)
from causal_growth.dgp.assign import assign_observational, assign_random, propensity_scores
from causal_growth.dgp.base import (
    OrderDraws,
    build_population_from_curves,
    calibrate_intercept,
    face_response,
    generate_covariates,
    linear_predictor,
    realized_order_net,
    sample_order_draws,
)
from causal_growth.dgp.levels import build_l0, build_l1, build_l2, build_l3, reference_face

__all__ = [
    "CONVERT_WINDOW",
    "FEATURE_ORDER",
    "LEVELS",
    "PROFIT_WINDOW",
    "Covariates",
    "GroundTruth",
    "OrderDraws",
    "Population",
    "PotentialOutcomes",
    "assign_observational",
    "assign_random",
    "build",
    "build_l0",
    "build_l1",
    "build_l2",
    "build_l3",
    "build_population_from_curves",
    "calibrate_intercept",
    "face_response",
    "generate_covariates",
    "linear_predictor",
    "propensity_scores",
    "realized_order_net",
    "reference_face",
    "sample_order_draws",
]

LEVELS: dict[str, Callable[..., Population]] = {
    "L0": build_l0,
    "L1": build_l1,
    "L2": build_l2,
    "L3": build_l3,
}


def build(level: str, cfg: Config, index: int = 0, **kwargs: Any) -> Population:
    """按层级名构造总体。``level`` ∈ {L0, L1, L2, L3}。"""
    key = level.upper()
    if key not in LEVELS:
        raise ValueError(f"未知层级 {level!r}；可用：{sorted(LEVELS)}")
    return LEVELS[key](cfg, index, **kwargs)
