# v3 五表事实字典与污染边界

> 合成数据 / 已知 DGP。Phase C 实现契约；主分析从五表SQL物化结果读取，本文不报告正式估计结果。

## 1 表与隔离

构造器只接受 `observation_bundle()` 的三个DataFrame：用户、实际分配、事实订单，另加配置、运行ID、重复ID与随机流前缀。拒绝未知输入列；不接收模拟population对象，也不读取U、潜在订单、解析CATE或真实观察性倾向。

| 表 | 粒度与主键 | 字段含义 |
|---|---|---|
| `users` | 每个分配用户；`run_id,user_id` | 新老客、历史GMV、购物车整数分、真实浏览次数、渠道、分配周/日、初始拆分及日志保留/截断数量 |
| `user_events` | 每条行为事件；`run_id,event_id` | 所属用户、事件类型、事件日和入库日；污染版本允许同一事件重复上报 |
| `coupon_assignment` | 每个分配用户；`run_id,user_id` | 实际动作、分析标签、合法设计概率、分配日、券面额及可选随机验证政策臂 |
| `orders` | 每笔事实订单；`run_id,order_id` | 首单/复购序号、实际动作、支付/退款事件与分别入库时间、整数分账务组件 |
| `user_outcomes` | 每用户每窗口；`run_id,user_id,window_type` | 由SQL按7天购买窗、30天利润窗分别物化；初始仅为空schema |

每个连接都同时使用 `run_id` 与实体ID；不同层/重复的同名user_id不是同一用户。
验证队列负user_id是合法ID，不能据此丢弃。退款订单和零金额订单保留，用户表及分配表包含所有分配者。

## 2 金额与时间

购物车唯一观测来源为 `users.cart_value_cent`。构造时删除输入中等价的 `cart_value`；MAR发生后没有另一份金额副本可恢复缺失真值。SQL分析侧可把该列除以配置分币倍数生成 `cart_value`，缺失必须继续缺失。
历史GMV保留元单位，已由上游分币；不与订单整数分组件混算。

订单组件均以 `_cent` 结尾：`gross_order_amount`、`goods_cost`、`fulfill_cost`、`coupon_discount`、`coupon_cost_initial`、`consumer_paid`、`goods_cost_recovered`、`refund_processing_fee`、`gross_refund_reversal`、`consumer_refund`、`coupon_return`。
这些是事件事实，退款组件尚未按分析窗口过滤。构造器不另算主分析利润。
SQL在支付事件入窗时计收入/成本，在退款事件入窗时计退款/回收/手续费/退券，且分别检查事件是否已经入库。

`paid_day`、`refund_day` 为相对项目日历原点的绝对天数；窗口终点为该用户 `assignment_day` 加窗口长度。`paid_ingested_day`、`refund_ingested_day` 为对应记录实际可见时间，不改变事件日。
退款入库可以早于支付记录入库；只要两条记录都不早于各自事件，这种入库异序就是合法的未成熟快照。不能人为删掉退款使快照更好看。

未退款订单的退款日、退款入库日缺失，全部退款组件为零；已退款订单时间完整，退款总额冲减等于订单商品总额，消费者退款等于消费者实付。券只在实际发券动作的首单使用；退券开关决定对应退款时是否冲回券成本。

## 3 标签、概率与可见性

`actual_action` 控制业务发券，`label` 控制分析分组。真正AA的两个标签对应同一实际动作，不能把label当订单动作。
随机实验保留设计概率；L3历史数据的依赖U真实倾向不会进入五表，`design_probability` 必须为空。L3真正AA可以保留其虚拟标签的已知随机概率。
独立验证使用 `assigned_policy_arm`、`policy_arm_probability`，历史数据两列为空。

初始 `split` 由上游机制提供；需要根据观测分配进行重新分层或时间切分时由专门的观测拆分流程执行。填补、winsor和标准化由训练拟合变换处理，不由本层污染修复函数执行。

## 4 日志、污染及修复

事件预窗、时间单位及资格加购事件属于补充数据技术配置，统一由 `configs/v3_data.yaml` 给出。
浏览次数是未受日志上限影响的分配时快照，日志仅保留上限内的早期事件。`event_retained_count` 和 `event_truncated_count` 明示日志保留与截断，不宣称日志行数恒等于真实浏览次数。

污染仅包括冻结配置中的渠道相关购物车缺失、历史GMV倍率异常、事件重复和入库延迟。每个污染使用独立命名随机流，修改一类污染不会扰动其他流。
不修改订单金额、退款事实、分配标签或用户分母。L3主扫描依照场景配置保留完整购物车和历史GMV；不会在清洗时重新加入缺失或异常。

唯一确定性修复是按 `run_id,event_id` 去重：先验证重复行的业务载荷一致，再保留最早入库的一行。若同一事件ID对应不同用户、类型或事件时间，抛异常，不挑一行掩盖冲突。缺失与异常不在这里填补或删用户。
原始、污染、清洗各阶段均返回独立DataFrame；污染与去重计数进入manifest，不靠打印警告代替结果。

## 5 硬校验

原始与清洗表必须满足实体主键、所有外键、完整分配分母、有限合法时间和整数分金额。污染表仅放行明确声明的日志重复及购物车缺失；外键和金额错误仍须失败。
raw购物车已知时校验首单不超过购物车；MAR后的缺失行记为无法作此观测断言，不能读取隐藏真值补检。
复购须有首单，金额对首单配置比例逐分half-up；不强求两单合计小于购物车。
SQL物化后另校验两个窗口全体用户覆盖、等长终点、整分账务恒等式以及零订单用户零组件。成熟与否由SQL可见性口径定义，不能用一个全局数据截止日冒称所有窗口已成熟。

## 6 逐字段字典

字段集合以 `v3_tables.OUTPUT_COLUMNS` 为构造接口，以 `sql/v3_schema.sql` 为SQLite存储类型约束。下表的 INTEGER、REAL、TEXT、ANY 是SQL逻辑类型；DataFrame中整数分使用int64，唯一可缺失购物车使用pandas Int64，时间与概率使用float64，文本使用object。历史整数标签与验证政策臂文本共用ANY列。所有 `_day` 均以合成日历原点计天，允许小数；不是自然日期字符串。

键列中的“组合PK”表示与同表其他PK列共同组成主键；“用户FK”统一指向 `users(run_id,user_id)`，“分配FK”指向 `coupon_assignment(run_id,user_id)`。订单另有唯一键 `(run_id,user_id,order_number)`。缺失标记“否”禁止NULL；“条件”后的说明规定何时可缺失。输出schema中没有审计真值列。

### 6.1 users

| 列名 | 类型 | 可空 | 单位 | 键 | 来源与语义 |
|---|---|---|---|---|---|
| run_id | TEXT | 否 | 标识 | 组合PK | 编排器传入；区分场景、队列与重复运行 |
| user_id | INTEGER | 否 | 标识 | 组合PK | 上游观测用户ID；允许独立验证队列的负ID |
| is_new | INTEGER | 否 | 0/1 | — | 分配时观测新客标记 |
| hist_gmv | REAL | 否 | 元 | — | 上游历史GMV；污染层可按配置乘异常倍率，清洗不删改 |
| cart_value_cent | INTEGER | 条件：dirty/clean可缺失，raw不可 | 分 | — | 分配时唯一购物车金额来源；渠道相关MAR将其置NULL |
| browse_depth | INTEGER | 否 | 次 | — | 分配时浏览次数快照，非截断后日志行数 |
| channel | TEXT | 否 | 类别 | — | 上游观测渠道；取值由business.channels约束 |
| assignment_week | INTEGER | 否 | 周序号 | — | 上游分配日所属周，从1开始 |
| assignment_day | REAL | 否 | 天 | — | 上游用户实际分配时刻，定义各用户窗口起点 |
| assignment_elapsed_days | REAL | 否 | 天 | — | 上游日历特征；当前定义与assignment_day一致 |
| split | TEXT | 否 | 类别 | — | 初始拆分；train/validation/test或等待观测分层的pending_stratified |
| event_retained_count | INTEGER | 否 | 条 | — | 构造器按cap保留的唯一预分配事件数，不含污染重复 |
| event_truncated_count | INTEGER | 否 | 条 | — | 浏览事件加配置资格事件总数减保留数；明示cap造成的截断 |

### 6.2 user_events

| 列名 | 类型 | 可空 | 单位 | 键 | 来源与语义 |
|---|---|---|---|---|---|
| run_id | TEXT | 否 | 标识 | 组合PK、用户FK组成列 | 从所属用户复制 |
| event_id | TEXT | 否 | 标识 | 组合PK | 构造为用户ID与事件时间排序后序号；dirty可同键重复上报 |
| user_id | INTEGER | 否 | 标识 | 用户FK组成列 | 所属分配用户 |
| event_type | TEXT | 否 | 类别 | — | 技术配置中的browse/cart；资格事件可因cap被截断 |
| event_day | REAL | 否 | 天 | — | 浏览日志在配置预窗内生成，cart按配置相对分配偏移；均不晚于分配 |
| ingested_day | REAL | 否 | 天 | — | raw等于event_day；dirty增加独立配置范围内延迟；去重取最早入库 |

### 6.3 coupon_assignment

| 列名 | 类型 | 可空 | 单位 | 键 | 来源与语义 |
|---|---|---|---|---|---|
| run_id | TEXT | 否 | 标识 | 组合PK、用户FK组成列 | 编排器运行ID |
| user_id | INTEGER | 否 | 标识 | 组合PK、用户FK组成列 | 每个上游分配者恰有一行 |
| actual_action | INTEGER | 否 | 0/1 | — | 上游实际业务动作；1发券、0不发券；AA按配置固定 |
| label | ANY | 否 | 分析组 | — | 历史数据为整数0/1；AA为随机虚拟标签；验证队列为政策臂文本 |
| design_probability | REAL | 条件：L3非AA历史及政策验证为空 | 概率 | — | 合法已知的历史随机设计概率；不得写入依赖U的真实倾向 |
| assigned_policy_arm | TEXT | 条件：历史为空 | 政策臂 | — | 上游独立验证随机政策臂；取值由evaluation配置约束 |
| policy_arm_probability | REAL | 条件：历史为空 | 概率 | — | 对应随机验证政策臂的已知概率，不等同于逐人发券概率 |
| assignment_day | REAL | 否 | 天 | — | 由users映射，与用户窗口起点严格一致 |
| ingested_day | REAL | 否 | 天 | — | raw等于分配日；dirty增加独立延迟，快照分母仅在分配可见后纳入 |
| coupon_face_cent | INTEGER | 否 | 分 | — | actual_action乘配置参考券面额；无券动作及当前AA均为0 |

### 6.4 orders

所有订单金额来自上游事实订单，构造器只校验并复制，不调用独立账本作生产核算。付款组件归属于支付事件，退款组件归属于退款事件；跨窗事件仍留在此表。

| 列名 | 类型 | 可空 | 单位 | 键 | 来源与语义 |
|---|---|---|---|---|---|
| run_id | TEXT | 否 | 标识 | 组合PK、分配FK组成列 | 编排器运行ID |
| user_id | INTEGER | 否 | 标识 | 分配FK、用户订单序号唯一键组成列 | 事实订单所属分配者 |
| order_id | INTEGER | 否 | 标识 | 组合PK | 上游事实订单ID；允许负ID |
| order_number | INTEGER | 否 | 单序号 | 用户订单序号唯一键组成列 | 1首单、2复购；复购必须有首单 |
| action | INTEGER | 否 | 0/1 | — | 上游事实动作；必须与对应actual_action一致 |
| assignment_day | REAL | 否 | 天 | — | 上游订单所属用户分配时刻，校验与分配表一致 |
| paid_day | REAL | 否 | 天 | — | 事实支付事件日，不早于分配；零金额购买仍有支付事件 |
| refund_day | REAL | 条件：未退款为空 | 天 | — | 事实退款事件日，不早于支付；跨窗不删除 |
| refunded | INTEGER | 否 | 0/1 | — | 该订单是否有退款事实；不表示退款已进入某窗口或快照 |
| gross_order_amount_cent | INTEGER | 否 | 分 | — | 订单商品总额；首单不超过已知购物车，复购按配置比例half-up |
| goods_cost_cent | INTEGER | 否 | 分 | — | 支付时商品成本，按上游实际成本参数逐分舍入 |
| fulfill_cost_cent | INTEGER | 否 | 分 | — | 支付时履约成本；退款不冲回，零金额订单亦可有成本 |
| coupon_discount_cent | INTEGER | 否 | 分 | — | 首单券核销抵扣；零或min(券面额,商品总额) |
| coupon_cost_initial_cent | INTEGER | 否 | 分 | — | 支付时初始券成本，严格等于coupon_discount_cent |
| consumer_paid_cent | INTEGER | 否 | 分 | — | 商品总额减券抵扣；允许为0 |
| goods_cost_recovered_cent | INTEGER | 否 | 分 | — | 退款时按商品成本乘回收率后half-up；未退款为0 |
| refund_processing_fee_cent | INTEGER | 否 | 分 | — | 退款时按商品总额乘手续费率后half-up；未退款为0 |
| gross_refund_reversal_cent | INTEGER | 否 | 分 | — | 退款时冲减商品总额；已退款等于商品总额，未退款为0 |
| consumer_refund_cent | INTEGER | 否 | 分 | — | 退款给消费者的实付金额；已退款等于consumer_paid_cent |
| coupon_return_cent | INTEGER | 否 | 分 | — | 配置允许退券时于退款事件冲回初始券成本，否则为0 |
| paid_ingested_day | REAL | 否 | 天 | — | 支付记录可见时刻；raw等于paid_day，dirty独立延迟 |
| refund_ingested_day | REAL | 条件：未退款为空 | 天 | — | 退款记录可见时刻；独立于支付入库，可先于支付记录入库 |

### 6.5 user_outcomes

本表全部由SQL物化。下表“付款可见”指付款事件在用户对应闭区间窗口内且已发生，未成熟快照要求原始入库日不晚于asof，规范成熟时刻后由已验证的入库上界保证窗内记录完整；“退款可见”独立对退款事件执行同样判断，不以付款已可见为前提。两个窗口均保留各自完整组件；主分析从7天窗口取购买指标，从30天窗口取利润、退款与费用。正式成熟结果覆盖全部输入分配者的两个窗口；绝对asof诊断可只覆盖当时已分配且分配记录可见者，须使用SQL的visible_assigned_n元数据，不能误用全N成熟验收。

| 列名 | 类型 | 可空 | 单位 | 键 | 来源与语义 |
|---|---|---|---|---|---|
| run_id | TEXT | 否 | 标识 | 组合PK、分配FK组成列 | SQL从分配表读取 |
| user_id | INTEGER | 否 | 标识 | 组合PK、分配FK组成列 | SQL覆盖当前可见分配者，正式结果覆盖全部分配者 |
| window_type | TEXT | 否 | 窗口类别 | 组合PK | 配置convert_7d或profit_30d |
| window_days | REAL | 否 | 天 | — | 对应配置窗口长度；同一window_type用户间相同 |
| window_end_day | REAL | 否 | 天 | — | assignment_day + window_days；端点当天事件计入 |
| asof_day | REAL | 否 | 天 | — | 该行快照截止时刻；相对快照按用户分配日平移 |
| mature | INTEGER | 否 | 0/1 | — | asof_day达到complete_after_day时为1；保守等候最大入库延迟 |
| converted | INTEGER | 否 | 0/1 | — | 此窗口至少一笔付款可见；零金额订单也计购买 |
| refunded | INTEGER | 否 | 0/1 | — | 此窗口至少一笔退款可见，与订单表全期refunded区分 |
| paid_orders | INTEGER | 否 | 笔 | — | 此窗口付款可见的订单数 |
| refunded_orders | INTEGER | 否 | 笔 | — | 此窗口退款可见的订单数；未成熟异序快照可大于paid_orders |
| gross_order_amount_cent | INTEGER | 否 | 分 | — | 付款可见订单商品总额之和 |
| gross_refund_reversal_cent | INTEGER | 否 | 分 | — | 退款可见订单商品总额冲减之和 |
| goods_cost_cent | INTEGER | 否 | 分 | — | 付款可见订单商品成本之和 |
| goods_cost_recovered_cent | INTEGER | 否 | 分 | — | 退款可见订单商品成本回收之和 |
| fulfill_cost_cent | INTEGER | 否 | 分 | — | 付款可见订单履约成本之和 |
| coupon_cost_initial_cent | INTEGER | 否 | 分 | — | 付款可见订单初始券成本之和 |
| coupon_return_cent | INTEGER | 否 | 分 | — | 退款可见订单退券冲回之和 |
| coupon_cost_cent | INTEGER | 否 | 分 | — | 初始券成本减退券冲回；异序快照可负，不能在策略价值中再次扣减 |
| refund_processing_fee_cent | INTEGER | 否 | 分 | — | 退款可见订单手续费之和 |
| consumer_paid_cent | INTEGER | 否 | 分 | — | 付款可见消费者实付之和 |
| consumer_refund_cent | INTEGER | 否 | 分 | — | 退款可见消费者退款之和 |
| net_profit_cent | INTEGER | 否 | 分 | — | 商品总额−退款总额−商品成本+回收成本−履约成本−净券成本−退款手续费；允许负值 |
| net_transaction_amount_cent | INTEGER | 否 | 分 | — | 商品总额减退款总额冲减；异序快照可负 |
| required_ingestion_day | REAL | 否 | 天 | — | 分配记录与本窗口当前可见付/退事件的规范可用时刻最大值；事件规范可用时刻为min(原始入库日,canonical complete_after_day)，不查看未来退款 |
| complete_after_day | REAL | 否 | 天 | — | assignment_day + (window_days + 最大入库延迟)；先合并持续时间再加分配日，SQL、质量门禁与相对快照使用同一浮点运算顺序；与当前是否观察到订单无关 |

入库上界严格采用 `raw_arrival <= event_day + maximum_delay`，上界的下一个可表示浮点值也必须拒绝。合法窗末事件的原始入库日 `(assignment_day + window_days) + maximum_delay` 可能比规范成熟时刻 `assignment_day + (window_days + maximum_delay)` 大1 ULP。SQL在验证原始入库上界后，在规范成熟时刻依据完整性条件纳入全部窗内事件，并用上述min定义记录其规范可用时刻；原始orders时间列保持不变。未成熟快照仍严格按原始事件日、入库日与asof比较，不能提前读取未来退款。

## 7 阶段接口与审计计数

`build_raw_tables(users, assignments, factual_orders, cfg, *, run_id, rep_id, stream_prefix)`返回五表字典。`inject_dirt(tables, cfg, *, rep_id, stream_prefix)`与`deduplicate_events(tables, cfg)`返回`StageResult`，其中`tables`是深复制后的下一阶段，`counts`是污染/修复计数，`data_config_hash`是补充技术配置的64字符SHA256。三阶段不就地修改输入。

污染计数包括用户总数、注入购物车缺失数、历史GMV倍率异常数、重复事件数、污染前后事件数、行为/分配/付款/退款分别延迟的记录数、日志截断数。清洗计数包括清洗前后事件数、移除重复数、保留缺失数、移除用户数和移除退款订单数；后两项固定为0。事件重复和入库延迟使用独立命名流；付/退延迟按全部用户×潜在订单序号抽取后映射到事实订单，以保持分配比例变化下的潜在事件配对。

`hist_fraud_injected`表示异常mask选中人数；工程凭据中的`pollution_audit.hist_fraud_changed`表示历史GMV实际数值改变人数。选中零值或异常倍率为1时，两数允许不同。检查器按原命名随机流重播mask，分别核对选中计数与每行期望脏值，不以数值变化反推选中人数。

`validate_tables(tables, cfg, *, stage, require_outcomes=False)`对结构、外键、分母、观察事实、逐分账务及入库上界作硬校验，并返回行数、缺失、重复、截断与保留退款数。`require_outcomes=True`用于正式全体用户双窗物化结果。diagnostic快照的可见分母由SQL接口校验；不能将其当成全体成熟结果。主分析接口、分析宽表字段与SQL校验说明见[SQL观测核算契约](v3_sql_contract.md)，训练拟合变换边界见[观测预处理契约](v3_preprocessing.md)。
