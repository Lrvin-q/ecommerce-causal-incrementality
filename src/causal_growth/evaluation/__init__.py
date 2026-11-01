"""evaluation 子包 —— 四指标并列报告（方案 §2.4 主线五）。

| 模块 | 回答方案里的哪个问题 |
|---|---|
| :mod:`causal_growth.evaluation.metrics` | 估计准不准 / 排序好不好 / 策略值多少 / 离最优多远 |

``metrics`` 里有四个**互不替代**的入口，对应方案 §2.4 主线五的四行：

- :func:`cate_accuracy` —— 效应估计**是否准确**（RMSE / MAE / 偏差 / 相关 / R²）
- :func:`ranking_metrics` —— 高增量用户**能否排前面**（top-k 重合度 / Spearman / Kendall）
- :func:`policy_value` / :func:`policy_value_observed` —— 实际决策**创造多少净增量利润**
- :func:`regret` —— **距真值最优损失多少**

本子包**不提供**任何"综合评分/加权总分"函数：方案 §2.4 明确要求四个指标并列、
互不替代，把它们压成一个数恰好会抹掉"RMSE 差但排序好"这类关键信息。
需要并排成表时在 ``scripts/`` 编排层拼，不在评估层聚合。

口径红线见 :mod:`causal_growth.evaluation.metrics` 模块文档：
Π 已含券成本（R3，不重复扣减）、CATE 真值只来自 DGP 解析式、学习与评估不同 split。
"""

from __future__ import annotations

from causal_growth.evaluation.metrics import (
    CALIBRATION_COLUMNS,
    CateAccuracy,
    RankingMetrics,
    bootstrap_se,
    calibration_table,
    cate_accuracy,
    nonneg_policy,
    oracle_policy,
    policy_value,
    policy_value_observed,
    ranking_metrics,
    regret,
    top_k_policy,
)

__all__ = [
    "CALIBRATION_COLUMNS",
    "CateAccuracy",
    "RankingMetrics",
    "bootstrap_se",
    "calibration_table",
    "cate_accuracy",
    "nonneg_policy",
    "oracle_policy",
    "policy_value",
    "policy_value_observed",
    "ranking_metrics",
    "regret",
    "top_k_policy",
]
