-- =============================================================================
--  analytics.sql —— 视图层与分析查询
--
--  分两段：
--    [A] 视图（VIEW）：把三条口径红线固化成**可复用的关系**，而不是散落在
--        pandas 代码里的 if/else。视图在入库时用业务参数实例化一次，
--        之后所有查询都自动继承同一套口径。
--    [B] 命名查询：每个查询前有 `-- >>> name: xxx` 标记，
--        由 Python 侧按名加载。这是"基于业务需求的复杂数据处理"的主要载体。
--
--  占位符（{fee_rate} 等）在 build_database() 时用配置值替换。
-- =============================================================================

-- ===========================================================================
-- [A] 视图层
-- ===========================================================================

DROP VIEW IF EXISTS v_order_profit;
DROP VIEW IF EXISTS v_order_net;
DROP VIEW IF EXISTS v_user_profit;
DROP VIEW IF EXISTS v_order_window;
DROP VIEW IF EXISTS v_outcome_convert;
DROP VIEW IF EXISTS v_outcome_profit;

-- A1 逐单利润构成：退款四项分别处理（方案 §2.3.3）
CREATE VIEW v_order_profit AS
SELECT
    o.order_id,
    o.user_id,
    o.order_time,
    o.pay_amount,
    o.refunded,
    o.coupon_used,
    -- ① 收入：退款冲减（refund_amount 已含全额退款）
    (o.pay_amount - o.refund_amount)                                                  AS revenue_net,
    -- ② 退款手续费：仅退款单发生
    CASE WHEN o.refunded = 1 THEN o.pay_amount * {fee_rate} ELSE 0.0 END               AS refund_handling_fee,
    -- ③ 商品成本：可回收部分冲减，不可回收部分保留
    o.goods_cost
      - CASE WHEN o.refunded = 1 THEN o.goods_cost * {refundable_ratio} ELSE 0.0 END   AS goods_cost_net,
    -- ④ 履约成本：已发生，不回收
    o.fulfill_cost                                                                     AS fulfill_cost,
    -- ⑤ 券核销成本：已核销才计入；退款且券退回则冲减
    CASE WHEN o.coupon_used = 1 AND (o.refunded = 0 OR {coupon_returned} = 0)
         THEN o.coupon_value ELSE 0.0 END                                              AS coupon_cost_net
FROM orders o;

-- A2 逐单净贡献利润：每一项只减一次（R3：券成本不重复扣减）
CREATE VIEW v_order_net AS
SELECT
    p.*,
    p.revenue_net - p.goods_cost_net - p.fulfill_cost
      - p.coupon_cost_net - p.refund_handling_fee                                       AS net_profit
FROM v_order_profit p;

-- A3 用户级利润：以 coupon_assignment 为驱动表，未下单用户记 0（R1：分母为全部被分配用户）
CREATE VIEW v_user_profit AS
SELECT
    a.user_id,
    a.grp,
    COALESCE(SUM(n.net_profit), 0.0)                                AS net_profit,
    COALESCE(SUM(n.pay_amount), 0.0)                                AS gmv,
    COUNT(n.order_id)                                               AS n_orders,
    COALESCE(MAX(CASE WHEN n.refunded = 1 THEN 1 ELSE 0 END), 0)     AS any_refund,
    COALESCE(MAX(n.coupon_used), 0)                                 AS coupon_used,
    COALESCE(SUM(n.coupon_cost_net), 0.0)                           AS coupon_cost
FROM coupon_assignment a
LEFT JOIN v_order_net n ON n.user_id = a.user_id
GROUP BY a.user_id, a.grp;

-- A4 订单的时间窗口归属：以各自分配时间为起点计算间隔天数
CREATE VIEW v_order_window AS
SELECT
    n.*,
    a.assign_time,
    a.grp,
    julianday(n.order_time) - julianday(a.assign_time)              AS elapsed_days
FROM v_order_net n
JOIN coupon_assignment a ON a.user_id = n.user_id;

-- A5 转化观察窗口（{convert_days} 天）：利润未成熟，故置 NULL
CREATE VIEW v_outcome_convert AS
SELECT
    a.user_id,
    'convert_7d'                                                    AS window_type,
    CASE WHEN COALESCE(SUM(CASE WHEN w.elapsed_days <= {convert_days} THEN 1 ELSE 0 END), 0) > 0
         THEN 1 ELSE 0 END                                          AS converted,
    COALESCE(SUM(CASE WHEN w.elapsed_days <= {convert_days} THEN w.pay_amount ELSE 0.0 END), 0.0)
                                                                    AS gmv,
    NULL                                                            AS net_profit,
    NULL                                                            AS refunded
FROM coupon_assignment a
LEFT JOIN v_order_window w ON w.user_id = a.user_id
GROUP BY a.user_id;

-- A6 利润成熟窗口（{profit_days} 天）：覆盖支付、退款、成本结算
CREATE VIEW v_outcome_profit AS
SELECT
    a.user_id,
    'profit_30d'                                                    AS window_type,
    CASE WHEN COALESCE(COUNT(w.order_id), 0) > 0 THEN 1 ELSE 0 END   AS converted,
    COALESCE(SUM(w.pay_amount), 0.0)                                AS gmv,
    COALESCE(SUM(w.net_profit), 0.0)                                AS net_profit,
    COALESCE(MAX(CASE WHEN w.refunded = 1 THEN 1 ELSE 0 END), 0)     AS refunded
FROM coupon_assignment a
LEFT JOIN v_order_window w
       ON w.user_id = a.user_id AND w.elapsed_days <= {profit_days}
GROUP BY a.user_id;

-- ===========================================================================
-- [B] 命名查询
-- ===========================================================================

-- >>> name: dedup_events
-- 去重后再计数：业务键重复即视为「同一次入库批次的重放」，保留最早入库的那条
WITH ranked AS (
    SELECT
        user_id, event_type, event_time, sku_id, ts_ingested,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, event_type, event_time, sku_id
            ORDER BY ts_ingested ASC
        ) AS rn
    FROM user_events
)
SELECT user_id, event_type, event_time, sku_id, ts_ingested
FROM ranked
WHERE rn = 1;

-- >>> name: browse_depth_by_events
-- 从行为日志重算浏览深度，并与 users.browse_depth_7d 交叉校验
-- （users 表的上限截断会导致重度用户不相等，故统计"差值非零"的用户数）
WITH dedup AS (
    SELECT user_id, COUNT(*) AS n_events
    FROM (
        SELECT user_id, event_type, event_time, sku_id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, event_type, event_time, sku_id
                   ORDER BY ts_ingested ASC) AS rn
        FROM user_events
    )
    WHERE rn = 1
    GROUP BY user_id
)
SELECT
    u.user_id,
    u.browse_depth_7d,
    COALESCE(d.n_events, 0)                              AS n_events_dedup,
    COALESCE(d.n_events, 0) - u.browse_depth_7d          AS depth_gap
FROM users u
LEFT JOIN dedup d ON d.user_id = u.user_id
WHERE COALESCE(d.n_events, 0) <> u.browse_depth_7d;

-- >>> name: order_profit
-- 逐单利润构成 + 净额（审计用）
SELECT order_id, user_id, order_time, revenue_net, refund_handling_fee,
       goods_cost_net, fulfill_cost, coupon_cost_net, net_profit
FROM v_order_net
ORDER BY order_id;

-- >>> name: profit_by_user
-- 用户级利润（分母为全部被分配用户）
SELECT user_id, grp, net_profit, gmv, n_orders, any_refund, coupon_used, coupon_cost
FROM v_user_profit
ORDER BY user_id;

-- >>> name: outcomes_both_windows
-- 两个窗口的结果表（每用户 2 行）
SELECT user_id, window_type, converted, gmv, net_profit, refunded FROM v_outcome_convert
UNION ALL
SELECT user_id, window_type, converted, gmv, net_profit, refunded FROM v_outcome_profit
ORDER BY user_id, window_type DESC;

-- >>> name: itt_group_summary
-- ITT 核心：分组均值、方差、样本量（利润与转化率一次算出）
-- 注意：退款率的分母是**已下单用户**，不是全部用户
SELECT
    grp,
    COUNT(*)                                    AS n,
    AVG(converted)                              AS conversion_rate,
    AVG(net_profit)                             AS mean_net_profit,
    AVG(net_profit * net_profit) - AVG(net_profit) * AVG(net_profit)  AS var_net_profit,
    AVG(gmv)                                    AS mean_gmv,
    AVG(CASE WHEN converted = 1 THEN refunded END)  AS refund_rate_among_converted
FROM (
    SELECT a.grp, o.converted, o.net_profit, o.gmv, o.refunded
    FROM coupon_assignment a
    JOIN v_outcome_profit o ON o.user_id = a.user_id
) t
GROUP BY grp;

-- >>> name: itt_difference
-- 一行给出 ITT 差值（利润 / 转化率 / GMV），供与 pandas 路径交叉校验
WITH g AS (
    SELECT a.grp, o.converted, o.net_profit, o.gmv
    FROM coupon_assignment a
    JOIN v_outcome_profit o ON o.user_id = a.user_id
)
SELECT
    (SELECT AVG(net_profit) FROM g WHERE grp = 'treatment')
      - (SELECT AVG(net_profit) FROM g WHERE grp = 'control')      AS itt_net_profit,
    (SELECT AVG(converted)  FROM g WHERE grp = 'treatment')
      - (SELECT AVG(converted)  FROM g WHERE grp = 'control')      AS itt_conversion,
    (SELECT AVG(gmv)        FROM g WHERE grp = 'treatment')
      - (SELECT AVG(gmv)        FROM g WHERE grp = 'control')      AS itt_gmv;

-- >>> name: channel_funnel
-- 分渠道漏斗：曝光 → 加购 → 转化 → 利润（业务方的日常看板口径）
SELECT
    u.channel,
    COUNT(*)                                                     AS n_users,
    AVG(u.is_new)                                                AS new_share,
    AVG(CASE WHEN p.n_orders > 0 THEN 1.0 ELSE 0.0 END)          AS conversion_rate,
    AVG(p.net_profit)                                            AS mean_net_profit,
    AVG(p.gmv)                                                   AS mean_gmv,
    AVG(CASE WHEN p.coupon_used = 1 THEN 1.0 ELSE 0.0 END)       AS coupon_used_rate
FROM users u
JOIN v_user_profit p ON p.user_id = u.user_id
GROUP BY u.channel
ORDER BY n_users DESC;

-- >>> name: new_vs_returning
-- 新老客 × 分组的四象限：这是"定向发券"的业务依据
SELECT
    CASE WHEN u.is_new = 1 THEN 'new' ELSE 'returning' END       AS segment,
    a.grp,
    COUNT(*)                                                     AS n,
    AVG(p.net_profit)                                            AS mean_net_profit,
    AVG(CASE WHEN p.n_orders > 0 THEN 1.0 ELSE 0.0 END)          AS conversion_rate
FROM users u
JOIN coupon_assignment a ON a.user_id = u.user_id
JOIN v_user_profit p   ON p.user_id = u.user_id
GROUP BY segment, a.grp
ORDER BY segment, a.grp;

-- >>> name: daily_rollup
-- 按分配日汇总：分配量、转化、成本、利润（时间维度聚合）
SELECT
    date(a.assign_time)                                          AS assign_day,
    COUNT(*)                                                     AS n_assigned,
    SUM(CASE WHEN p.n_orders > 0 THEN 1 ELSE 0 END)              AS n_converted,
    SUM(p.coupon_cost)                                           AS coupon_cost_total,
    SUM(p.net_profit)                                            AS net_profit_total
FROM coupon_assignment a
JOIN v_user_profit p ON p.user_id = a.user_id
GROUP BY assign_day
ORDER BY assign_day;

-- >>> name: qc_duplicate_events
SELECT COUNT(*) AS n_duplicate_rows FROM (
    SELECT user_id, event_type, event_time, sku_id, COUNT(*) AS c
    FROM user_events
    GROUP BY user_id, event_type, event_time, sku_id
    HAVING c > 1
);

-- >>> name: qc_orphan_orders
SELECT COUNT(*) AS n_orphans FROM orders o
LEFT JOIN users u ON u.user_id = o.user_id WHERE u.user_id IS NULL;

-- >>> name: qc_multi_assignment
SELECT COUNT(*) AS n_users_multi FROM (
    SELECT user_id FROM coupon_assignment GROUP BY user_id HAVING COUNT(*) > 1
);

-- >>> name: qc_window_integrity
SELECT
    SUM(CASE WHEN n_win <> 2 THEN 1 ELSE 0 END)                  AS n_bad_users,
    COUNT(*)                                                     AS n_users
FROM (
    SELECT o.user_id, COUNT(*) AS n_win
    FROM user_outcomes o GROUP BY o.user_id
) t;

-- >>> name: qc_convert_window_profit_must_be_null
SELECT COUNT(*) AS n_violations FROM user_outcomes
WHERE window_type = 'convert_7d' AND net_profit IS NOT NULL;

-- >>> name: qc_refund_retention
-- R1 的第二道闸：退款单必须仍在样本内，且其用户存在于 users
SELECT
    (SELECT COUNT(*) FROM orders WHERE refunded = 1)               AS n_refund_orders,
    (SELECT COUNT(*) FROM orders o
       JOIN users u ON u.user_id = o.user_id WHERE o.refunded = 1) AS n_refund_with_user;

-- >>> name: qc_coupon_only_in_treatment
SELECT COUNT(*) AS n_violations
FROM coupon_assignment
WHERE grp = 'control' AND coupon_value > 0;

-- >>> name: qc_event_after_assign
SELECT COUNT(*) AS n_violations
FROM user_events e
JOIN coupon_assignment a ON a.user_id = e.user_id
WHERE e.event_time > a.assign_time;

-- >>> name: qc_treatment_share
SELECT grp, COUNT(*) AS n,
       ROUND(COUNT(*) * 1.0 / (SELECT COUNT(*) FROM coupon_assignment), 6) AS share
FROM coupon_assignment GROUP BY grp;
