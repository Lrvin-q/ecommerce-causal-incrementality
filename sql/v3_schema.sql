-- 合成数据 / 已知 DGP。Five factual business tables; parameters are a view.
PRAGMA foreign_keys = ON;

CREATE TABLE users (
    run_id TEXT NOT NULL CHECK(length(run_id)>0),
    user_id INTEGER NOT NULL,
    is_new INTEGER NOT NULL CHECK(is_new IN (0,1)),
    hist_gmv REAL NOT NULL CHECK(hist_gmv>=0),
    cart_value_cent INTEGER CHECK(cart_value_cent>=0),
    browse_depth INTEGER NOT NULL CHECK(browse_depth>=0),
    channel TEXT NOT NULL,
    assignment_week INTEGER NOT NULL CHECK(assignment_week>=1),
    assignment_day REAL NOT NULL,
    assignment_elapsed_days REAL NOT NULL,
    split TEXT NOT NULL,
    event_retained_count INTEGER NOT NULL CHECK(event_retained_count>=0),
    event_truncated_count INTEGER NOT NULL CHECK(event_truncated_count>=0),
    PRIMARY KEY(run_id,user_id)
) STRICT;

CREATE TABLE coupon_assignment (
    run_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    actual_action INTEGER NOT NULL CHECK(actual_action IN (0,1)),
    label ANY NOT NULL,
    design_probability REAL CHECK(design_probability>0 AND design_probability<1),
    assigned_policy_arm TEXT,
    policy_arm_probability REAL CHECK(policy_arm_probability>0 AND policy_arm_probability<1),
    assignment_day REAL NOT NULL,
    ingested_day REAL NOT NULL CHECK(ingested_day>=assignment_day),
    coupon_face_cent INTEGER NOT NULL CHECK(coupon_face_cent>=0),
    CHECK((actual_action=0 AND coupon_face_cent=0) OR actual_action=1),
    CHECK((assigned_policy_arm IS NULL AND typeof(label)='integer' AND label IN (0,1)
           AND policy_arm_probability IS NULL)
       OR (assigned_policy_arm IS NOT NULL AND typeof(label)='text'
           AND label=assigned_policy_arm AND policy_arm_probability IS NOT NULL)),
    PRIMARY KEY(run_id,user_id),
    FOREIGN KEY(run_id,user_id) REFERENCES users(run_id,user_id)
) STRICT;

CREATE TABLE user_events (
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_day REAL NOT NULL,
    ingested_day REAL NOT NULL CHECK(ingested_day>=event_day),
    PRIMARY KEY(run_id,event_id),
    FOREIGN KEY(run_id,user_id) REFERENCES users(run_id,user_id)
) STRICT;

CREATE TABLE orders (
    run_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    order_number INTEGER NOT NULL CHECK(order_number IN (1,2)),
    action INTEGER NOT NULL CHECK(action IN (0,1)),
    assignment_day REAL NOT NULL,
    paid_day REAL NOT NULL CHECK(paid_day>=assignment_day),
    refund_day REAL,
    refunded INTEGER NOT NULL CHECK(refunded IN (0,1)),
    gross_order_amount_cent INTEGER NOT NULL CHECK(gross_order_amount_cent>=0),
    goods_cost_cent INTEGER NOT NULL CHECK(goods_cost_cent>=0 AND goods_cost_cent<=gross_order_amount_cent),
    fulfill_cost_cent INTEGER NOT NULL CHECK(fulfill_cost_cent>=0),
    coupon_discount_cent INTEGER NOT NULL CHECK(coupon_discount_cent>=0 AND coupon_discount_cent<=gross_order_amount_cent),
    coupon_cost_initial_cent INTEGER NOT NULL CHECK(coupon_cost_initial_cent=coupon_discount_cent),
    consumer_paid_cent INTEGER NOT NULL CHECK(consumer_paid_cent=gross_order_amount_cent-coupon_discount_cent),
    goods_cost_recovered_cent INTEGER NOT NULL CHECK(goods_cost_recovered_cent>=0 AND goods_cost_recovered_cent<=goods_cost_cent),
    refund_processing_fee_cent INTEGER NOT NULL CHECK(refund_processing_fee_cent>=0),
    gross_refund_reversal_cent INTEGER NOT NULL CHECK(gross_refund_reversal_cent>=0),
    consumer_refund_cent INTEGER NOT NULL CHECK(consumer_refund_cent>=0),
    coupon_return_cent INTEGER NOT NULL CHECK(coupon_return_cent>=0 AND coupon_return_cent<=coupon_cost_initial_cent),
    paid_ingested_day REAL NOT NULL CHECK(paid_ingested_day>=paid_day),
    refund_ingested_day REAL,
    CHECK((refunded=0 AND refund_day IS NULL AND refund_ingested_day IS NULL
           AND goods_cost_recovered_cent=0 AND refund_processing_fee_cent=0
           AND gross_refund_reversal_cent=0 AND consumer_refund_cent=0 AND coupon_return_cent=0)
       OR (refunded=1 AND refund_day IS NOT NULL AND refund_day>=paid_day
           AND refund_ingested_day IS NOT NULL AND refund_ingested_day>=refund_day
           AND gross_refund_reversal_cent=gross_order_amount_cent
           AND consumer_refund_cent=consumer_paid_cent)),
    CHECK(action=1 OR coupon_cost_initial_cent=0),
    CHECK(order_number=1 OR coupon_cost_initial_cent=0),
    PRIMARY KEY(run_id,order_id),
    UNIQUE(run_id,user_id,order_number),
    FOREIGN KEY(run_id,user_id) REFERENCES coupon_assignment(run_id,user_id)
) STRICT;

CREATE TABLE user_outcomes (
    run_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    window_type TEXT NOT NULL,
    window_days REAL NOT NULL CHECK(window_days>0),
    window_end_day REAL NOT NULL,
    asof_day REAL NOT NULL,
    mature INTEGER NOT NULL CHECK(mature IN (0,1)),
    converted INTEGER NOT NULL CHECK(converted IN (0,1)),
    refunded INTEGER NOT NULL CHECK(refunded IN (0,1)),
    paid_orders INTEGER NOT NULL CHECK(paid_orders>=0),
    refunded_orders INTEGER NOT NULL CHECK(refunded_orders>=0),
    gross_order_amount_cent INTEGER NOT NULL CHECK(gross_order_amount_cent>=0),
    gross_refund_reversal_cent INTEGER NOT NULL CHECK(gross_refund_reversal_cent>=0),
    goods_cost_cent INTEGER NOT NULL CHECK(goods_cost_cent>=0),
    goods_cost_recovered_cent INTEGER NOT NULL CHECK(goods_cost_recovered_cent>=0),
    fulfill_cost_cent INTEGER NOT NULL CHECK(fulfill_cost_cent>=0),
    coupon_cost_initial_cent INTEGER NOT NULL CHECK(coupon_cost_initial_cent>=0),
    coupon_return_cent INTEGER NOT NULL CHECK(coupon_return_cent>=0),
    coupon_cost_cent INTEGER NOT NULL CHECK(coupon_cost_cent=coupon_cost_initial_cent-coupon_return_cent),
    refund_processing_fee_cent INTEGER NOT NULL CHECK(refund_processing_fee_cent>=0),
    consumer_paid_cent INTEGER NOT NULL CHECK(consumer_paid_cent>=0),
    consumer_refund_cent INTEGER NOT NULL CHECK(consumer_refund_cent>=0),
    net_profit_cent INTEGER NOT NULL CHECK(net_profit_cent=gross_order_amount_cent-gross_refund_reversal_cent-goods_cost_cent+goods_cost_recovered_cent-fulfill_cost_cent-coupon_cost_cent-refund_processing_fee_cent),
    net_transaction_amount_cent INTEGER NOT NULL CHECK(net_transaction_amount_cent=gross_order_amount_cent-gross_refund_reversal_cent),
    required_ingestion_day REAL NOT NULL CHECK(required_ingestion_day<=asof_day),
    complete_after_day REAL NOT NULL CHECK(complete_after_day>=window_end_day),
    PRIMARY KEY(run_id,user_id,window_type),
    FOREIGN KEY(run_id,user_id) REFERENCES coupon_assignment(run_id,user_id)
) STRICT;

CREATE INDEX orders_by_user ON orders(run_id,user_id);
CREATE INDEX events_by_user ON user_events(run_id,user_id);
