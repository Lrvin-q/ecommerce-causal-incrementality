# v3 分币账务与时间积分内核

> 合成数据 / 已知 DGP。Phase B 实现说明；本文件不构成正式重复实验结果或阶段独立验收。

## 1 输入、输出及耦合

`dgp/v3_amounts.py` 接受已向下取整的整数分购物车，参数来自已审批的 `Config`。
`sample_amounts` 使用四层引擎提供的 `CovariateBatch.stream_prefix`，另派生
`.amounts.fraction` 与 `.amounts.fulfillment` 两条随机流。同一用户的两潜在动作共享金额比例和履约成本。
`v3_timing.sample_order_timing` 再派生首单、复购、两笔退款各自的时间流，追加用户不会扰动原有用户。
金额样本不包含购买、核销、退款的 Bernoulli 判断；引擎在此之上施加事件存在指示。

公开接口如下：

| 接口 | 输出及单位 |
|---|---|
| `sample_fraction(uniform,cfg)` | 截断正态比例 Q |
| `sample_amounts(cart_cent,cfg,master_seed=...,stream=...,index=...)` | `first_gross_cent`、`repeat_gross_cent`、`fulfill_cent`（分）与 `fraction` |
| `posted_components(gross_cent,fulfill_cent,redeemed,refunded,cfg,goods_cost_ratio=...,coupon_eligible=...)` | 逐笔已记账组件与利润，全部整数分 |
| `amount_distribution(cart_cent,cfg)` | 首单分币金额全部支持及概率，只读数组 |
| `conditional_order_expectation(cart_cent,cfg,goods_cost_ratio=...)` | 首单/复购金额、商品成本、商品回收、手续费、首单封顶券及履约的期望；全部元 |
| `conditional_user_expectation(cart_cent,cfg,purchase_probability=...,refund_probability=...,redemption_probability=...,goods_cost_ratio=...)` | 全体分配用户的30天组件、净利润、券成本（元）、任一单退款概率、7天购买概率和订单数 |
| `conditional_expectation_numerical_error(...)` | 与上一行同参；独立返回每用户净利润的数值误差分项，全部元，不混入业务组件 |
| `paired_conditional_expectation_numerical_error(...,purchase_probability0/1=...,refund_probability0/1=...,redemption_probability0/1=...)` | 先合并两动作共享金额/时间系数，再求CATE及误差；`net_profit_difference_cny`为直接求和的CATE |
| `sample_order_timing(n,cfg,master_seed=...,stream=...,index=...)` | 首单/复购/两退款相对分配时间，天；尚未筛掉窗外事件 |
| `timing_coefficients(cfg,profit_days=...)` | 六个时间截窗系数及积分器误差估计 |
| `fulfillment_calibration(cfg)` | 正态位置、分币后均值/标准差、截断无穷和尾误差界 |

两种账务接口都保留字段 `gross_order_amount`、`gross_refund_reversal`、`goods_cost`、
`goods_cost_recovered`、`fulfill_cost`、`coupon_discount`、`coupon_cost`、
`refund_processing_fee`、`consumer_paid`、`consumer_refund`、`net_transaction_amount`、`net_profit`。
实际记账为分，期望为元。引擎须显式转换单位，不能把两个接口返回值直接相减。
`posted_components` 的 refunded 表示已入分析窗口的退款；窗外退款须作为事件保留后再截窗，不能提前冲回。

## 2 首单分币分布与精确期望

设截断正态的CDF为 F，整数购物车金额为 C，首单分币金额 K=floor(CQ)。
对于全部非空区间，

`P(K=k) = F(min((k+1)/C, q_upper)) - F(max(k/C, q_lower))`。

实现使用正态两尾中稳定的一侧计算区间质量，右尾不以两个极接近1的数直接相减。
C=0时质量全部位于零。默认 Q 区间(0,1]没有点质量，故 C>0 时整数支持为0至C−1；
逆CDF的机器端点修正只处理浮点误差，不把原始超限正态压到1。

第二单金额 R=half_up(.55K)，商品成本为 A=half_up(gK)，回收成本为
B=half_up(hA)，手续费为 H=half_up(fK)，券上限为 D=min(face,K)。
每个函数都先应用到整数支持，再用上式的完整概率求和；例如
`E[B|C] = sum_k P(K=k) half_up(h half_up(gk))`。
这样明确保留了回收成本依赖已舍入商品成本的顺序，不以 `hg E[K]` 替代。

`round_ratio_cent` 将配置比例解释为该浮点数最短十进制字符串对应的有理数。
常数比例在不溢出时直接用整数商完成half-up。每用户不同成本率时先作向量乘法；
将浮点到最短十进制的表示误差与乘法误差包含在半分附近的四个float ULP包络内，
只有包络与半分相交的值才以 Python 任意精度整数重新计算。因此不对每个不同成本率扫描整个用户数组。
测试同时用独立 `Decimal(...).quantize(...,ROUND_HALF_UP)` 对照常数率和不同用户率。

## 3 无穷支持履约成本的均值校准

设 X~N(μ,σ²)，下限 L，分币倍数 m。履约 F_cent=half_up(m max(L,X))，最小分币值为 a。
利用非负整数尾和恒等式，

`E[F_cent] = a + sum_(k=a+1)^infinity P(mX >= k−.5)`；

`E[F_cent²] = a² + sum_(k=a+1)^infinity (2k−1)P(mX >= k−.5)`。

尾截点由 `v3_numerics.yaml` 的尾概率预算确定。在截点后的正态右尾，离散项单调下降，
以首项加尾积分界定遗漏量。尾积分使用正态正部矩；一阶积分为
`σ[φ(z)−z Φ(−z)]`，二阶正部矩为 `σ²[(1+z²)Φ(−z)−zφ(z)]`。
`FulfillmentCalibration` 返回一阶/二阶余项界。位置 μ 通过 Brent 括区求根，使上述分币均值命中配置目标。
这保证改变σ只改变结果噪声；下限导致的均值漂移不会冒充信噪比效应。

尾误差界只针对无穷和截断；浮点函数与求根另受数值参数控制。
实际标准差按分币后矩报告，不能把原始σ当成最终标准差。

## 4 事件窗口与任一单退款

令 S 为相对分配的首单延迟，D 为复购相对首单延迟，R1、R2 为相互独立的退款延迟；
S与D为配置规定的双侧clip Gamma，保留两端点质量。退款延迟为Uniform。
各个截窗系数均条件于对应潜在事件已发生，Bernoulli概率尚未相乘：

- `first_order` = P(S≤W)，`repeat_order` = P(S+D≤W)。
- `first_refund` = P(S+R1≤W)，`repeat_refund` = P(S+D+R2≤W)。
- `both_refunds` = E[F_R(W−S) F_R(W−S−D)]。
- `first_conversion` = P(S≤W_convert)。

记购买概率p、单笔退款概率r、首单后复购概率ρ。全体分配用户的任一单退款概率为

`p { r b1 + ρ r b2 − ρ r² b12 }`。

其中 b12 不能用 b1*b2 代替，因为两退款都含同一首单时间 S；只用首单退款率也会漏掉第二单。
各金额组件与时间独立，故可以分解，例如退款冲减期望为
`p r { E[G1]b1 + ρ E[G2]b2 }`。
净券成本期望为
`p red E[D] { a1 − returned*r*b1 }`，第二单不带券。
消费者退款另按支付时实际抵扣后的金额计算，不以退券开关重写消费者原始实付。

clip Gamma期望拆为下限原子、上限原子与内部连续密度积分；退款CDF的折点、
复购端点进入积分分段。`integration_error_bound` 保存外层误差估计加最大内层误差估计。
它是 QUADPACK 的数值误差估计，并非经区间算术认证的严格数学界；收紧容差的独立计算和
独立MC另外验证收敛。不能只凭积分器返回值宣称所有极端参数都已证明。

## 5 精度证据、缓存与计算边界

`tests/test_v3_amounts.py` 用独立十进制逐组件账核对，分币恒等式零误差；
用另一种尾和表示核对金额期望，并对小金额分段做独立连续积分。
履约各噪声强度使用配置规定的独立MC样本量核对，容限取 `max(0.001,4 MC_SE)`。
`tests/test_v3_timing.py` 包括可手算的固定支付时间/均匀退款例、闭区间边界、
独立Gamma/Uniform MC及按数值配置进一步收紧积分容差的收敛比较。
主控的机制验证入口还须输出逐组件误差、MC_SE与运行参数表；单元测试通过不替代该落盘证据。

精确单点需要枚举购物车支持的整数分数，计算复杂度随购物车金额增长。
批量调用先合并完全相同的 `(cart_cent,goods_cost_ratio)`，再使用配置控制的结果LRU；
PMF只保留小容量LRU，便于L0在同一cart上连续尝试成本率。
这些缓存与去重不会近似金额，也没有插值或未舍入替代。参数元组参与缓存键，
改变金额比例、回收率、手续费、券面额或复购比例不会误读旧表。

当前内核缓存仅在进程内。首轮冷缓存与热缓存成本差异显著，正式pilot必须包含worker启动、
不同场景参数、独特购物车数与缓存复用情况。引擎若后续增加磁盘矩表，应以本函数参数完整哈希
标识，不能只按cart索引复用。长尾的大购物车和逐用户成本率仍会增加精确枚举成本，尚未声称
所有正式作业可在原先估时内完成。

## 6 未覆盖的业务扩展

此实现只覆盖冻结协议的首单券、单次复购、正延迟及共享履约成本耦合。
不声称支持多面额决策、门槛券、SKU集合约束、无限复购或合并现金流报表。
负利润与零分订单保留；不得通过正金额过滤改变全体分配用户分母。

## 7 将数值误差传播到利润单位

阶段评审后新增单动作与成对诊断接口。所有诊断字段使用 `_cny` 后缀；不能拿无量纲
时间概率误差或U积分概率误差直接与元单位阈值比较。

单动作的每用户利润写成四个时间系数的线性组合。每个系数的误差估计乘该系数对应的
条件金额组合的绝对值，最后乘购买概率。履约均值尾界乘期望入窗订单数；分币组件误差
乘相应金额组件的系数绝对值。金额误差权重也包含时间误差，以保留两者乘积交叉项。

分币金额同时计算两种等价表示：原来的完整PMF加权和，以及
`E[f(K)] = f(k_min) + sum_k [f(k+1)−f(k)] P(K≥k+1)`。
第二种表示改用 `log_ndtr` 与 `expm1` 计算稳定尾概率，记录两种表示的差及总概率质量残差。
这部分字段称 `cdf_crosscheck_estimate`，不能称CDF真值的严格数学界。
生产PMF期望、履约矩与交叉核验尾和均采用显式平衡pairwise求和；每轮相邻配对，奇数项
原样传入下一轮，最长加法路径为 `d=ceil(log2 n)`。用标准基本运算模型
`γ_j=jε/(1−jε)` 给出误差界，j取实际路径深度并加乘法、初值相加、单位换算的路径操作数。
不再以n项串行累加的粗界代替实际实现。该界不把SciPy特殊函数当成区间认证函数。
成对CATE的共享系数逐次追踪加/减/乘误差，最后各组件也用平衡树求和，单列真实组装运算界。

两个诊断接口均返回：

- `net_profit_time_error_estimate_cny`：QUADPACK误差估计传播。
- `net_profit_fulfillment_tail_bound_cny`、`net_profit_fulfillment_roundoff_bound_cny`、`net_profit_fulfillment_cdf_crosscheck_estimate_cny`：履约尾和、基本运算与CDF交叉核验。
- `net_profit_discrete_roundoff_bound_cny`、`net_profit_discrete_cdf_crosscheck_estimate_cny`：完整分币积分的基本运算界与另一表示的差异。
- `net_profit_assembly_roundoff_bound_cny`：最后的系数组装与线性组合。
- `net_profit_numerical_error_estimate_cny`：以上分项总和；整体仍是误差估计。
- `conditional_profit_absolute_envelope_cny`：条件利润绝对值的组件包络，可供上层传播概率误差。

成对接口先形成 `δp`、`δ(pr)`、`δ(p·red)`、`δ(p·r·red)`，在共享金额和时间系数上直接求差。
相同概率/动作的真正AA各差值与误差均为零。U积分误差需在审计层乘对应条件订单利润，
再加入金额/时间误差，不能被本层的零差声明掩盖。

门禁仍按已约定的绝对及相对精度分别判断，本模块不把二者改成OR，也不自行返回通过标志。
恰为零的真值没有相对误差，应由审计层明确记NA。近零CATE存在消去条件数问题：即使直接
传播共享系数误差，保守浮点界或积分误差估计也可能超过严格相对标准，需报告原值、绝对误差、
相对诊断与条件数，或启动更高精度/更紧容差复核，不能自动判通过。

`test_time_error_is_propagated_to_currency_and_not_merely_reported` 按绝对阈值反算放大倍率，
验证利润误差随之放大并跨过既定绝对阈值。`test_near_zero_cate_reports_absolute_diagnostics_without_defining_relative_zero`
已替换为 `test_near_zero_cate_meets_both_precision_gates_after_pairwise_refinement`，
构造合法购买概率使CATE分别接近1e−5和1e−7元；以当前默认时间容差1e−13、真实求和深度及
逐操作组装界核验，两种非零目标均须满足既定绝对和相对1e−6标准。
该测试不把更接近零的任意目标都当成通过；若诊断仍不满足，上层必须继续精化或明确失败。
