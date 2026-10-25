-- 合成数据 / 已知 DGP。Only this SQL produces the analysis outcomes.
-- Payment and refund postings are independently gated by event and arrival time.
-- This gate runs before any outcome materialization. Subtraction is deliberately
-- avoided: (event + maximum_delay) - event need not equal maximum_delay in binary64.
CREATE VIEW v3_time_quality AS
SELECT 'configured_assignment_delay_bound' AS check_name,COUNT(*) AS violations
FROM coupon_assignment CROSS JOIN v3_parameters AS p
WHERE ingested_day>assignment_day+p.maximum_ingestion_delay_days
UNION ALL
SELECT 'configured_event_delay_bound',COUNT(*) FROM user_events CROSS JOIN v3_parameters AS p
WHERE ingested_day>event_day+p.maximum_ingestion_delay_days
UNION ALL
SELECT 'configured_order_delay_bound',COUNT(*) FROM orders CROSS JOIN v3_parameters AS p
WHERE paid_ingested_day>paid_day+p.maximum_ingestion_delay_days
   OR refund_ingested_day>refund_day+p.maximum_ingestion_delay_days;

-- V3_OUTCOME_MATERIALIZATION
CREATE VIEW v3_visible_assignments AS
SELECT u.run_id,u.user_id,u.assignment_day,a.ingested_day AS assignment_ingested_day,
       COALESCE(p.relative_snapshot_days+u.assignment_day,p.asof_day) AS effective_asof_day
FROM users AS u
LEFT JOIN coupon_assignment AS a ON a.run_id=u.run_id AND a.user_id=u.user_id
CROSS JOIN v3_parameters AS p
WHERE a.assignment_day<=COALESCE(p.relative_snapshot_days+u.assignment_day,p.asof_day)
  AND (a.ingested_day<=COALESCE(p.relative_snapshot_days+u.assignment_day,p.asof_day)
       OR COALESCE(p.relative_snapshot_days+u.assignment_day,p.asof_day)
          >=u.assignment_day+(p.profit_days+p.maximum_ingestion_delay_days));

CREATE VIEW v3_windows AS
SELECT convert_window_name AS window_type,convert_days AS window_days FROM v3_parameters
UNION ALL
SELECT profit_window_name,profit_days FROM v3_parameters;

CREATE VIEW v3_window_clocks AS
SELECT b.run_id,b.user_id,w.window_type,w.window_days,
       b.assignment_day+w.window_days AS window_end_day,b.effective_asof_day AS asof_day,
       b.assignment_day+(w.window_days+p.maximum_ingestion_delay_days) AS complete_after_day,
       b.assignment_day,b.assignment_ingested_day
FROM v3_visible_assignments AS b CROSS JOIN v3_windows AS w CROSS JOIN v3_parameters AS p;

CREATE VIEW v3_window_postings AS
SELECT b.run_id,b.user_id,b.window_type,b.window_days,b.window_end_day,b.asof_day,b.complete_after_day,
       MIN(b.assignment_ingested_day,b.complete_after_day) AS assignment_available_day,
       o.order_id,o.paid_ingested_day,o.refund_ingested_day,
       MIN(o.paid_ingested_day,b.complete_after_day) AS paid_available_day,
       MIN(o.refund_ingested_day,b.complete_after_day) AS refund_available_day,
       CASE WHEN o.paid_day>=b.assignment_day AND o.paid_day<=b.window_end_day
                  AND o.paid_day<=b.asof_day
                  AND (b.asof_day>=b.complete_after_day OR o.paid_ingested_day<=b.asof_day)
            THEN 1 ELSE 0 END AS paid_visible,
       CASE WHEN o.refunded=1 AND o.refund_day>=b.assignment_day
                  AND o.refund_day<=b.window_end_day AND o.refund_day<=b.asof_day
                  AND (b.asof_day>=b.complete_after_day OR o.refund_ingested_day<=b.asof_day)
            THEN 1 ELSE 0 END AS refund_visible,
       o.gross_order_amount_cent,o.goods_cost_cent,o.fulfill_cost_cent,
       o.coupon_cost_initial_cent,o.consumer_paid_cent,
       o.gross_refund_reversal_cent,o.goods_cost_recovered_cent,
       o.refund_processing_fee_cent,o.consumer_refund_cent,o.coupon_return_cent
FROM v3_window_clocks AS b
LEFT JOIN orders AS o ON o.run_id=b.run_id AND o.user_id=b.user_id;

INSERT INTO user_outcomes
WITH aggregated AS (
SELECT run_id,user_id,window_type,window_days,window_end_day,asof_day,complete_after_day,
       MAX(paid_visible) AS converted,MAX(refund_visible) AS refunded,
       SUM(paid_visible) AS paid_orders,SUM(refund_visible) AS refunded_orders,
       SUM(CASE WHEN paid_visible=1 THEN gross_order_amount_cent ELSE 0 END) AS gross_order_amount_cent,
       SUM(CASE WHEN refund_visible=1 THEN gross_refund_reversal_cent ELSE 0 END) AS gross_refund_reversal_cent,
       SUM(CASE WHEN paid_visible=1 THEN goods_cost_cent ELSE 0 END) AS goods_cost_cent,
       SUM(CASE WHEN refund_visible=1 THEN goods_cost_recovered_cent ELSE 0 END) AS goods_cost_recovered_cent,
       SUM(CASE WHEN paid_visible=1 THEN fulfill_cost_cent ELSE 0 END) AS fulfill_cost_cent,
       SUM(CASE WHEN paid_visible=1 THEN coupon_cost_initial_cent ELSE 0 END) AS coupon_cost_initial_cent,
       SUM(CASE WHEN refund_visible=1 THEN coupon_return_cent ELSE 0 END) AS coupon_return_cent,
       SUM(CASE WHEN refund_visible=1 THEN refund_processing_fee_cent ELSE 0 END) AS refund_processing_fee_cent,
       SUM(CASE WHEN paid_visible=1 THEN consumer_paid_cent ELSE 0 END) AS consumer_paid_cent,
       SUM(CASE WHEN refund_visible=1 THEN consumer_refund_cent ELSE 0 END) AS consumer_refund_cent,
       MAX(MAX(assignment_available_day,
               CASE WHEN paid_visible=1 THEN paid_available_day ELSE assignment_available_day END,
               CASE WHEN refund_visible=1 THEN refund_available_day ELSE assignment_available_day END)) AS required_ingestion_day
FROM v3_window_postings
GROUP BY run_id,user_id,window_type,window_days,window_end_day,asof_day,complete_after_day
)
SELECT run_id,user_id,window_type,window_days,window_end_day,asof_day,
       CASE WHEN asof_day>=complete_after_day THEN 1 ELSE 0 END AS mature,
       converted,refunded,paid_orders,refunded_orders,
       gross_order_amount_cent,gross_refund_reversal_cent,goods_cost_cent,goods_cost_recovered_cent,
       fulfill_cost_cent,coupon_cost_initial_cent,coupon_return_cent,
       coupon_cost_initial_cent-coupon_return_cent AS coupon_cost_cent,
       refund_processing_fee_cent,consumer_paid_cent,consumer_refund_cent,
       gross_order_amount_cent-gross_refund_reversal_cent-goods_cost_cent+goods_cost_recovered_cent
         -fulfill_cost_cent-(coupon_cost_initial_cent-coupon_return_cent)-refund_processing_fee_cent AS net_profit_cent,
       gross_order_amount_cent-gross_refund_reversal_cent AS net_transaction_amount_cent,
       required_ingestion_day,complete_after_day
FROM aggregated;

CREATE VIEW v3_analysis AS
SELECT u.run_id,u.user_id,a.label AS treatment,a.label,a.actual_action,a.design_probability,
       a.assigned_policy_arm,a.policy_arm_probability,
       u.assignment_day,a.ingested_day AS assignment_ingested_day,u.assignment_week,u.assignment_elapsed_days,
       u.split,u.is_new,u.hist_gmv,u.cart_value_cent,u.cart_value_cent*1.0/k.cents_per_yuan AS cart_value,
       u.browse_depth,u.channel,u.event_retained_count,u.event_truncated_count,
       p.asof_day,c.window_end_day AS conversion_window_end_day,p.window_end_day AS profit_window_end_day,
       p.complete_after_day,p.required_ingestion_day,c.mature AS convert_mature,p.mature,
       k.diagnostic_snapshot,
       c.converted AS paid_purchase_7d,p.refunded AS any_refund_30d,p.refunded,
       p.paid_orders AS paid_orders_30d,p.refunded_orders AS refunded_orders_30d,
       p.gross_order_amount_cent,p.gross_refund_reversal_cent,p.goods_cost_cent,p.goods_cost_recovered_cent,
       p.fulfill_cost_cent,p.coupon_cost_initial_cent,p.coupon_return_cent,p.coupon_cost_cent,
       p.refund_processing_fee_cent,p.consumer_paid_cent,p.consumer_refund_cent,
       p.net_profit_cent,p.net_transaction_amount_cent,
       p.net_profit_cent*1.0/k.cents_per_yuan AS net_profit,
       p.coupon_cost_cent*1.0/k.cents_per_yuan AS coupon_cost,
       p.gross_order_amount_cent*1.0/k.cents_per_yuan AS gross_order_amount,
       p.net_transaction_amount_cent*1.0/k.cents_per_yuan AS net_transaction_amount,
       p.gross_order_amount_cent*1.0/k.cents_per_yuan AS gmv
FROM users AS u
LEFT JOIN coupon_assignment AS a ON a.run_id=u.run_id AND a.user_id=u.user_id
CROSS JOIN v3_parameters AS k
JOIN user_outcomes AS c ON c.run_id=u.run_id AND c.user_id=u.user_id AND c.window_type=k.convert_window_name
JOIN user_outcomes AS p ON p.run_id=u.run_id AND p.user_id=u.user_id AND p.window_type=k.profit_window_name;

CREATE VIEW v3_quality AS
SELECT * FROM v3_time_quality
UNION ALL
SELECT 'assignment_covers_every_user' AS check_name,COUNT(*) AS violations
FROM users AS u LEFT JOIN coupon_assignment AS a USING(run_id,user_id) WHERE a.user_id IS NULL
UNION ALL
SELECT 'order_action_matches_assignment',COUNT(*) FROM orders AS o
JOIN coupon_assignment AS a USING(run_id,user_id) WHERE o.action<>a.actual_action
UNION ALL
SELECT 'assignment_time_consistent',COUNT(*) FROM users AS u JOIN coupon_assignment AS a USING(run_id,user_id)
WHERE u.assignment_day<>a.assignment_day
UNION ALL
SELECT 'order_assignment_time_consistent',COUNT(*) FROM orders AS o JOIN users AS u USING(run_id,user_id)
WHERE o.assignment_day<>u.assignment_day
UNION ALL
SELECT 'coupon_cap',COUNT(*) FROM orders AS o JOIN coupon_assignment AS a USING(run_id,user_id)
WHERE o.coupon_discount_cent>a.coupon_face_cent
UNION ALL
SELECT 'first_amount_within_known_cart',COUNT(*) FROM orders AS o JOIN users AS u USING(run_id,user_id)
WHERE o.order_number=1 AND u.cart_value_cent IS NOT NULL AND o.gross_order_amount_cent>u.cart_value_cent
UNION ALL
SELECT 'repeat_requires_first',COUNT(*) FROM orders AS o
LEFT JOIN orders AS first ON first.run_id=o.run_id AND first.user_id=o.user_id AND first.order_number=1
WHERE o.order_number=2 AND first.order_id IS NULL
UNION ALL
SELECT 'repeat_ratio',COUNT(*) FROM orders AS o
JOIN orders AS first ON first.run_id=o.run_id AND first.user_id=o.user_id AND first.order_number=1
CROSS JOIN v3_parameters AS p
WHERE o.order_number=2 AND o.gross_order_amount_cent<>
      ((first.gross_order_amount_cent*p.repeat_ratio_numerator*2+p.repeat_ratio_denominator)/(p.repeat_ratio_denominator*2))
UNION ALL
SELECT 'repeat_time_order',COUNT(*) FROM orders AS o
JOIN orders AS first ON first.run_id=o.run_id AND first.user_id=o.user_id AND first.order_number=1
WHERE o.order_number=2 AND o.paid_day<first.paid_day
UNION ALL
SELECT 'two_windows_per_visible_user',COUNT(*) FROM (
SELECT b.run_id,b.user_id,COUNT(o.window_type) AS windows
FROM v3_visible_assignments AS b LEFT JOIN user_outcomes AS o USING(run_id,user_id)
GROUP BY b.run_id,b.user_id HAVING COUNT(o.window_type)<>2)
UNION ALL
SELECT 'all_visible_users_retained',ABS((SELECT COUNT(*) FROM v3_visible_assignments)-(SELECT COUNT(*) FROM v3_analysis))
UNION ALL
SELECT 'zero_posting_profit_identity',COUNT(*) FROM user_outcomes
WHERE paid_orders=0 AND refunded_orders=0 AND net_profit_cent<>0
UNION ALL
SELECT 'event_retained_count',COUNT(*) FROM users AS u
LEFT JOIN (SELECT run_id,user_id,COUNT(*) AS n FROM user_events GROUP BY run_id,user_id) AS e USING(run_id,user_id)
WHERE u.event_retained_count<>COALESCE(e.n,0)
UNION ALL
SELECT 'coupon_return_semantics',COUNT(*) FROM orders CROSS JOIN v3_parameters AS p
WHERE coupon_return_cent<>CASE WHEN p.coupon_returned_on_refund=1 AND refunded=1 THEN coupon_cost_initial_cent ELSE 0 END
UNION ALL
SELECT 'recorded_assignment_probability',COUNT(*) FROM coupon_assignment AS a CROSS JOIN v3_parameters AS p
WHERE a.assigned_policy_arm IS NULL AND
 ((p.observational_history=1 AND a.design_probability IS NOT NULL)
  OR (p.observational_history=0 AND (a.design_probability IS NULL OR ABS(a.design_probability-p.expected_design_probability)>p.probability_tolerance)))
UNION ALL
SELECT 'historical_action_label',COUNT(*) FROM coupon_assignment AS a CROSS JOIN v3_parameters AS p
WHERE a.assigned_policy_arm IS NULL AND
 ((p.virtual_aa_labels=1 AND a.actual_action<>p.aa_actual_action)
  OR (p.virtual_aa_labels=0 AND a.label<>a.actual_action))
UNION ALL
SELECT 'assigned_coupon_face',COUNT(*) FROM coupon_assignment AS a CROSS JOIN v3_parameters AS p
WHERE a.coupon_face_cent<>a.actual_action*p.reference_face_cent
UNION ALL
SELECT 'policy_arm_probability',COUNT(*) FROM coupon_assignment AS a
LEFT JOIN v3_policy_design AS d ON d.policy_arm=a.assigned_policy_arm CROSS JOIN v3_parameters AS p
WHERE a.assigned_policy_arm IS NOT NULL AND
 (d.policy_arm IS NULL OR a.design_probability IS NOT NULL OR ABS(a.policy_arm_probability-d.probability)>p.probability_tolerance
  OR (a.assigned_policy_arm='no_coupon' AND a.actual_action<>0))
UNION ALL
SELECT 'known_channel',COUNT(*) FROM users AS u LEFT JOIN v3_known_channels AS c ON c.channel=u.channel
WHERE c.channel IS NULL
UNION ALL
SELECT 'event_predates_assignment',COUNT(*) FROM user_events AS e JOIN users AS u USING(run_id,user_id)
WHERE e.event_day>u.assignment_day;

CREATE VIEW v3_cost_ledger AS
SELECT run_id,treatment,COUNT(*) AS n_total,
       SUM(gross_order_amount_cent) AS gross_order_amount_cent,
       SUM(gross_refund_reversal_cent) AS gross_refund_reversal_cent,
       SUM(goods_cost_cent) AS goods_cost_cent,SUM(goods_cost_recovered_cent) AS goods_cost_recovered_cent,
       SUM(fulfill_cost_cent) AS fulfill_cost_cent,SUM(coupon_cost_initial_cent) AS coupon_cost_initial_cent,
       SUM(coupon_return_cent) AS coupon_return_cent,SUM(coupon_cost_cent) AS coupon_cost_cent,
       SUM(refund_processing_fee_cent) AS refund_processing_fee_cent,
       SUM(consumer_paid_cent) AS consumer_paid_cent,SUM(consumer_refund_cent) AS consumer_refund_cent,
       SUM(net_profit_cent) AS net_profit_cent,SUM(net_transaction_amount_cent) AS net_transaction_amount_cent
FROM v3_analysis GROUP BY run_id,treatment;

CREATE VIEW v3_funnel AS
SELECT run_id,treatment,COUNT(*) AS assigned_users,SUM(actual_action) AS issued_users,
       SUM(paid_purchase_7d) AS paid_users_7d,SUM(paid_orders_30d) AS paid_orders_30d,
       SUM(CASE WHEN coupon_cost_initial_cent>0 THEN 1 ELSE 0 END) AS positive_coupon_posting_users,
       SUM(any_refund_30d) AS refunded_users_30d,SUM(refunded_orders_30d) AS refunded_orders_30d
FROM v3_analysis GROUP BY run_id,treatment;
