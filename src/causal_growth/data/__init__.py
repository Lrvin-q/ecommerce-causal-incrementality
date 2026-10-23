"""data 子包：五表 schema、利润核算、脏数据层、数据质量检查、清洗。

模块分工（顺序即管线顺序）：

==================  ==========================================================
``profit``          利润核算的**唯一实现**（方案 §2.3，R1/R2/R3）
``tables``          五张关系表 + 分析框架 + 真值卷（数据交付物）
``dirt``            脏数据注入：MNAR 缺失 / 刷单异常值 / 重复上报 / 上报延迟
``quality``         数据质量检查清单 + 门禁（``assert_no_errors``）
``cleaning``        去重 / 渠道中位数填补 + 缺失指示列 / 分位截尾
==================  ==========================================================

这里只做 re-export，不放任何业务逻辑——口径改动必须回到上面五个模块，
避免出现"第二份实现"。
"""

from causal_growth.data import cleaning, dirt, profit, quality, tables
from causal_growth.data.cleaning import (
    EVENT_BUSINESS_KEY,
    clean_analysis_frame,
    deduplicate_events,
    impute_cart_value,
    winsorize,
)
from causal_growth.data.dirt import (
    STREAM_DELAY,
    STREAM_DUPLICATE,
    STREAM_FRAUD,
    STREAM_MISSING,
    USERS_CART_COLUMN,
    add_fraud_outliers,
    add_missing_cart_value,
    apply_dirty_layer,
    apply_dirty_to_frame,
    delay_ingestion,
    duplicate_events,
)
from causal_growth.data.profit import (
    COMPONENT_COLUMNS,
    ORDERS_REQUIRED_COLUMNS,
    ProfitComponents,
    aggregate_user_profit,
    build_user_outcomes,
    compute_order_components,
    expected_order_net_profit,
    validate_orders_schema,
)
from causal_growth.data.quality import (
    SEVERITIES,
    QualityCheck,
    QualityError,
    assert_no_errors,
    check_analysis_frame,
    check_tables,
    summarize,
)
from causal_growth.data.tables import (
    FIVE_TABLE_NAMES,
    analysis_arrays,
    build_analysis_frame,
    build_five_tables,
    build_truth_frame,
    cross_check_profit,
)

__all__ = [
    # 子模块
    "cleaning",
    "dirt",
    "profit",
    "quality",
    "tables",
    # 利润核算
    "COMPONENT_COLUMNS",
    "ORDERS_REQUIRED_COLUMNS",
    "ProfitComponents",
    "aggregate_user_profit",
    "build_user_outcomes",
    "compute_order_components",
    "expected_order_net_profit",
    "validate_orders_schema",
    # 表构造
    "FIVE_TABLE_NAMES",
    "analysis_arrays",
    "build_analysis_frame",
    "build_five_tables",
    "build_truth_frame",
    "cross_check_profit",
    # 脏数据层
    "STREAM_DELAY",
    "STREAM_DUPLICATE",
    "STREAM_FRAUD",
    "STREAM_MISSING",
    "USERS_CART_COLUMN",
    "add_fraud_outliers",
    "add_missing_cart_value",
    "apply_dirty_layer",
    "apply_dirty_to_frame",
    "delay_ingestion",
    "duplicate_events",
    # 数据质量
    "SEVERITIES",
    "QualityCheck",
    "QualityError",
    "assert_no_errors",
    "check_analysis_frame",
    "check_tables",
    "summarize",
    # 清洗
    "EVENT_BUSINESS_KEY",
    "clean_analysis_frame",
    "deduplicate_events",
    "impute_cart_value",
    "winsorize",
]
