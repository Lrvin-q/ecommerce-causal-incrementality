"""design 子包 —— 随机实验设计四件套（方案 §2.4 主线二）。

| 模块 | 回答方案里的哪个问题 |
|---|---|
| :mod:`causal_growth.design.power` | **实验要多大？** 转化率与利润分别算样本量、取较大值 |
| :mod:`causal_growth.design.aa` | **分流与检验流程可信吗？** p 值是否近似 Uniform、假阳性率是否 ≈ α |
| :mod:`causal_growth.design.guardrail` | **增长有没有踩护栏？** 用单侧 CI 对预设界值判断非劣效（"不显著" ≠ "安全"） |
| :mod:`causal_growth.design.multiplicity` | **多指标/多切片时 α 有没有被吃掉？** Bonferroni / Holm / BH |

口径红线（AGENTS.md §4）：样本量一律区分 ``n_per_group``（每组）与 ``n_total``（总），
1:1 分流时 ``n_total = 2 * n_per_group``；本子包所有结果对象都用这两个字段名承载。
"""

from __future__ import annotations

from causal_growth.design.aa import (
    AAResult,
    aa_test_binary,
    aa_test_continuous,
    summarize_pvalues,
)
from causal_growth.design.guardrail import NonInferiorityResult, noninferiority_binary
from causal_growth.design.multiplicity import (
    MultiplicityResult,
    adjust,
    benjamini_hochberg,
    bonferroni,
    holm,
)
from causal_growth.design.power import (
    SampleSizeResult,
    design_sample_size,
    sample_size_mean,
    sample_size_proportion,
    sample_size_unequal,
)

__all__ = [
    "AAResult",
    "MultiplicityResult",
    "NonInferiorityResult",
    "SampleSizeResult",
    "aa_test_binary",
    "aa_test_continuous",
    "adjust",
    "benjamini_hochberg",
    "bonferroni",
    "design_sample_size",
    "holm",
    "noninferiority_binary",
    "sample_size_mean",
    "sample_size_proportion",
    "sample_size_unequal",
    "summarize_pvalues",
]
