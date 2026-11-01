-- =============================================================================
--  schema.sql —— 营销因果评估项目的物理数据模型（SQLite）
--
--  设计原则
--    1. 五张表严格对应业务系统的落库形态（用户 / 行为日志 / 分配 / 订单 / 结果），
--       而不是直接落一张宽表——宽表是分析产物，不是数据资产。
--    2. 所有口径约束尽量下沉到 DDL（主键、外键、CHECK），让脏数据在入库或查询阶段
--       就失败，而不是靠下游 pandas 代码自觉。
--    3. 金额单位统一为「元」，浮点；标记位统一为 INTEGER 0/1（SQLite 无原生布尔）。
--    4. 时间统一存 TEXT（ISO-8601，形如 2024-03-01 00:00:00），
--       便于 julianday() 计算两个窗口的间隔天数。
-- =============================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS user_outcomes;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS coupon_assignment;
DROP TABLE IF EXISTS user_events;
DROP TABLE IF EXISTS users;

-- ---------------------------------------------------------------------------
-- 用户维表：随机分配时点的特征快照
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    user_id             INTEGER PRIMARY KEY,          -- 主键：同一用户全局唯一
    is_new              INTEGER NOT NULL CHECK (is_new IN (0, 1)),
    reg_date            TEXT    NOT NULL,
    channel             TEXT    NOT NULL
                                CHECK (channel IN ('search', 'feed', 'xhs', 'other')),
    hist_gmv            REAL    NOT NULL CHECK (hist_gmv >= 0),
    cart_value_at_assign REAL,                         -- 允许 NULL：脏数据层注入 MNAR 缺失
    browse_depth_7d     INTEGER NOT NULL CHECK (browse_depth_7d >= 0)
);

-- ---------------------------------------------------------------------------
-- 行为日志：每次行为一行
--   注意 event_time（事件发生）与 ts_ingested（入库）必须分开，
--   所有统计口径一律使用 event_time。
-- ---------------------------------------------------------------------------
CREATE TABLE user_events (
    user_id     INTEGER NOT NULL REFERENCES users(user_id),
    event_type  TEXT    NOT NULL CHECK (event_type IN ('page_view', 'add_to_cart')),
    event_time  TEXT    NOT NULL,
    sku_id      INTEGER NOT NULL,
    ts_ingested TEXT    NOT NULL,
    CHECK (ts_ingested >= event_time)                  -- 入库不得早于发生
);

-- 业务键唯一索引：用于识别并去除重复上报
CREATE INDEX idx_events_business_key
    ON user_events (user_id, event_type, event_time, sku_id);
CREATE INDEX idx_events_user ON user_events (user_id);

-- ---------------------------------------------------------------------------
-- 随机分配：分析的基本单位
--   UNIQUE(user_id) 在库层面保证「同一用户只被分配一次」，
--   这是方案中「同一用户多次曝光只算一个样本」的口径红线。
-- ---------------------------------------------------------------------------
CREATE TABLE coupon_assignment (
    exp_id       TEXT    NOT NULL,
    user_id      INTEGER NOT NULL UNIQUE REFERENCES users(user_id),
    grp          TEXT    NOT NULL CHECK (grp IN ('treatment', 'control')),
    coupon_value REAL    NOT NULL CHECK (coupon_value >= 0),
    assign_time  TEXT    NOT NULL,
    -- 对照组不得持有券面额
    CHECK ((grp = 'control' AND coupon_value = 0) OR grp = 'treatment')
);
CREATE INDEX idx_assign_group ON coupon_assignment (grp);

-- ---------------------------------------------------------------------------
-- 订单：每笔订单一行，退款单一律保留
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
    order_id       TEXT    PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(user_id),
    order_time     TEXT    NOT NULL,
    pay_amount     REAL    NOT NULL CHECK (pay_amount >= 0),
    refund_amount  REAL    NOT NULL CHECK (refund_amount >= 0),
    goods_cost     REAL    NOT NULL CHECK (goods_cost >= 0),
    fulfill_cost   REAL    NOT NULL CHECK (fulfill_cost >= 0),
    coupon_used    INTEGER NOT NULL CHECK (coupon_used IN (0, 1)),
    coupon_value   REAL    NOT NULL CHECK (coupon_value >= 0),
    refunded       INTEGER NOT NULL CHECK (refunded IN (0, 1)),
    refund_time    TEXT,
    -- 退款金额不得超过支付金额
    CHECK (refund_amount <= pay_amount + 1e-6),
    -- 未核销则不得有券面额
    CHECK (coupon_used = 1 OR coupon_value = 0)
);
CREATE INDEX idx_orders_user ON orders (user_id);

-- ---------------------------------------------------------------------------
-- 结果表：每用户每窗口一行（转化窗口 7 天 / 利润成熟窗口 30 天）
-- ---------------------------------------------------------------------------
CREATE TABLE user_outcomes (
    user_id     INTEGER NOT NULL REFERENCES users(user_id),
    window_type TEXT    NOT NULL CHECK (window_type IN ('convert_7d', 'profit_30d')),
    converted   INTEGER NOT NULL CHECK (converted IN (0, 1)),
    gmv         REAL    NOT NULL CHECK (gmv >= 0),
    net_profit  REAL,                                  -- 转化窗口内为 NULL（利润未成熟）
    refunded    INTEGER,
    PRIMARY KEY (user_id, window_type),
    -- 口径红线：转化窗口的利润必须为空，利润窗口的利润不得为空
    CHECK ((window_type = 'convert_7d'  AND net_profit IS NULL)
        OR (window_type = 'profit_30d'  AND net_profit IS NOT NULL))
);
