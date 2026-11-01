"""causal_growth — 电商营销策略的因果评估与增量利润优化。

数据来源：**合成数据 / 已知 DGP**。本包不包含任何真实企业数据。

模块划分（对应《项目方案思路.md》主线）：
    dgp        主线一 Step3：L0–L4 分层数据生成与真值
    data       主线一：五表 schema、脏数据层、质量校验、利润核算
    design     主线二：样本量、AA 校验、护栏非劣效、多重比较
    estimate   主线二/三：ITT、CATE、观察性因果
    policy     主线四：预算约束下的贪心/背包策略与六策略对比
    evaluation 主线五：四指标、敏感性扫描
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__", "DATA_SOURCE_LABEL"]

#: 所有产物必须携带的诚实标注（见 AGENTS.md §6）
DATA_SOURCE_LABEL = "合成数据 / 已知 DGP（非真实企业数据）"
