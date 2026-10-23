from pathlib import Path

p = Path(r"D:\L\practice_project\营销数分项目\reports\00_项目总报告.md")
text = p.read_text(encoding="utf-8")

# ---------- 附录 A：压到 13 行、去掉配置段前缀 ----------
start = text.index("## 附录 A　关键参数表")
end = text.index("## 附录 B　复现方式与可复现性等级")
new_a = """## 附录 A　关键参数表

（参数名省略配置段前缀：`business.` / `windows.` / `experiment.` / `budget.` / `dgp.`）

| 参数 | 取值 | 业务依据 |
|-------------------------|--------------------------|--------------------------------------------------------|
| `baseline_conversion` | 0.10 | 加购未支付用户历史首单转化率（行业 8%～12% 的中值） |
| `coupon_max_effect` | 0.15 | 券对转化率的最大提升（概率尺度上限，硬约束 $p_0+\\tau\\le1$） |
| `coupon_face_values` | 5 / 10 / 15 / 20 元 | 平台现行券档位；参考面额取 10 元，饱和曲线尺度 12.0 |
| `redemption_rate` | 0.55 | 券核销率（同类券历史核销率 40%～70%） |
| `refund_rate` | 0.075 | 类目历史退款率（5%～10%），同时是护栏指标基线 |
| `goods_cost_ratio` | 0.68 | 商品成本率（毛利率 25%～40% 对应成本率 60%～75%） |
| `fulfill_cost_mean` | 5.0 元/单 | 配送+仓储+包材；**不可回收**，退款后仍发生 |
| `aov_mean` | 120 元 | 加购未支付用户首单客单价 |
| `refundable_goods_ratio` | 0.85 | 退款后可回收商品成本比例；退款手续费率 0.01 |
| `convert_days / profit_days` | 7 / 30 天 | 转化观察窗与利润成熟窗；两窗口必须分开且等长（R2） |
| `mde.conversion_abs` | 1 个百分点 | 0.10→0.11 的相对提升 10%，低于此不足以支撑一次改版 |
| `mde.profit_per_user` | 0.5 元/人 | = 总预算 100,000 元 / 20 万合格用户的盈亏平衡尺度 |
| `mde.profit_sd_assumed` | 11.08 元 | **实测** sd(人均净贡献利润)（含复购路径，87% 为 0） |
| `coverage_target` | 0.20 | 试点投放覆盖 20% 合格用户；实际预算 $B=0.20\\sum_ic_i$ |
| `repeat.prob / value_ratio` | 0.05 / 0.55 | 30 天窗口内复购率 4%～6% 的中值；复购客单价为首单的 55% |

"""
text = text[:start] + new_a + text[end:]

# ---------- 附录 C：把两张表压成一张 ----------
start = text.index("## 附录 C　数据字典与 SQL 对象清单")
new_c = """## 附录 C　数据字典与 SQL 对象清单

**五张关系表**

| 表（行数） | 关键字段与口径 |
|------------------|--------------------------------------------------------------------------|
| `users`（200,000） | user_id 主键、is_new、reg_date、channel、hist_gmv、cart_value_at_assign（脏数据层注入 MNAR 缺失）、browse_depth_7d |
| `user_events`（1,201,121） | user_id、event_type（page_view / add_to_cart）、**event_time（统计口径）**、sku_id、ts_ingested（受上报延迟影响，不作统计） |
| `coupon_assignment`（200,000） | exp_id、user_id（**每用户仅一行**）、group、coupon_value、assign_time（两窗口共同起点） |
| `orders`（26,471） | order_id、user_id、order_time、pay_amount、refund_amount、goods_cost、fulfill_cost、coupon_used、coupon_value、refunded、refund_time；**退款单保留** 2,053 行、复购第二单 1,256 行 |
| `user_outcomes`（400,000） | user_id、window_type（convert_7d / profit_30d）、converted、gmv、net_profit（7 天为 NULL）、refunded |

**6 个视图**：`v_order_profit`（逐单五项成本分列：收入冲减、退款手续费 1%、商品成本按 85% 可回收率冲减、履约成本刚性、券成本仅核销未退券时计入）、`v_order_net`（逐单净贡献利润，券成本只减一次，**R3**）、`v_user_profit`（以分配表为驱动表 LEFT JOIN，未下单记 0，多单按 `SUM` 聚合，**R1**）、`v_order_window`（按各自分配时点算 `elapsed_days`，**R2**）、`v_outcome_convert`（7 天转化窗，利润列强制 NULL，**R2**）、`v_outcome_profit`（30 天利润成熟窗，覆盖支付/退款/成本结算，**R2**）。

**19 条命名查询**：口径派生 5（事件去重、浏览深度、逐单利润、用户级利润、双窗口合并）、业务看板 5（分组 ITT、ITT 差值、渠道漏斗、新老客对比、日汇总）、**质量闸门 9**（重复上报、孤儿订单、重复分配、窗口完整性、转化窗口利润为空、退款单保留、对照组持券、事件越界、分流比例）。闸门与 SQL 单测跑同一批数据，违反即抛错。
"""
text = text[:start] + new_c
p.write_text(text, encoding="utf-8")
print("ok")
