# Phase F02 正式 200 rep 独立科学评审（门禁）

> 评审时间：**2026-10-28 19:17（北京时间，`date` 实读）**。
> 评审人：独立评审代理（科学门禁，非主负责团队）。
> 任务边界：只读；唯一写入的文件是本文；未修改 `configs/`、`src/`、`tests/`、`GOAL.md`、`TODO.md`、`outputs/` 下任何既有文件；未运行 pytest、任何 `scripts/` 或任何 R>0 作业；未写冻结 glob。
> 核验原则：不采信主负责自述。§2 的全部数字由本评审从 `outputs/evidence/f02_formal/` 与 `out/f02_formal/` 独立重算；先读 `GOAL.md`、`AGENTS.md` §12、`configs/v3/evaluation.yaml`、`configs/v3/design.yaml`、`docs/v3_phase_F02_validation.md`，再对照 `docs/v3_phase_F02_formal.md`。

## §0 判定

**PASS WITH CONDITIONS。**

核心结果层是干净的：200 个 rep、4×50 分片、全 200 个 manifest 绑定同一 `config_hash=e1aa4314…` 与同一 48 文件 `source_hashes`（`d8327ae0…`）；`coupon_worth_issuing` 196/200、`targeting_better_than_random` 190/200、两项+护栏同时 190/200；护栏 200/200、最大单侧上界 0.003946 < 0.005；分层计数、rep 0 两项 Holm p=0.598019、支出统计均逐位复现。未发现需要重跑的数据错误。

但本评审不能判无条件 PASS，原因集中在**证据导出层与正文表述层**，不是结果层：

1. **P1-1**：`docs/v3_phase_F02_validation.md:186-189` 的 18:46 裁决明确要求“正式 200 rep 必须逐 rep 报告实际支出与超支倍数”；正文只给三臂汇总、min/max 和按模型均值，证据包 `aggregate/v3_phase_F02_formal_spend.csv` 只有 3 行。逐 rep 支出表缺失。
2. **P1-2**：`outputs/evidence/f02_formal/aggregate/` 的 7 张表（含本评审复算所用的逐 rep claims/guardrail/ITT/spend）均未登记进 `outputs/evidence/coverage.json`；200 个逐 rep manifest、4 个分片 summary、`snapshot_binding.json` 也未导出。仅凭 `outputs/evidence/` 可以重建决策层关键数字，但**不能**重建“200/200 都绑 `e1aa4314`/`d8327ae0`”“4×50”“逐 rep 预测支出最大值”。按 AGENTS §12.1 的严格口径，这是证据包不完整。
3. **P1-3**：GOAL F02 的核心描述含“随后审计”，`docs/v3_phase_F02_validation.md:67-71` 要求 ITT 与全队列审计价值“报告时必须分开写”；正文没有审计价值章节，证据包也显式排除了 `audit_truth.csv`、`audit_policy_values.csv`、`audit_arm_contrasts.csv`。需要明确：审计价值是 F02 交付的一部分（补报告），还是移交 D01/G（写明移交与理由）。当前是范围悬空，不是“已证明审计无问题”。

另有 P2 级文档错误（§7 条件清单）：`Wilson` 标签与 Clopper–Pearson 数值错配、五表 `bytes` 声明不成立、预算偏差分母未写、`constant` 叙述过强、局限章节漏项、顶层登记计数过期、`paired` 配置名与独立臂实现不一致、运行后配置漂移未在正文记录。

**条件性质**：以上全部可在不重跑任何 rep 的前提下由主负责修完（补导出、补表、改措辞）。在 P1 条件落地前，F02 不应从“未证实”改为“通过”。

### 六项判定一览

| 项 | 判定 | 一句话理由 |
|---|---|---|
| 1. 预注册规则与验收口径 | PASS | 两项单侧 Holm + 护栏 0.005、全臂 ITT 分母、CP/不合并 p 的规则实读一致 |
| 2. 关键数字复算 | PASS | 196/200、190/200、190/200、Holm 中位、护栏最大上界、分层、rep0、支出全部复现 |
| 3. 统计口径 | PASS | 分母、两 30 天窗口、券成本只扣一次、单侧上界、两项家族逐 rep 校正均正确 |
| 4. 正文表述 | PARTIAL | 异质性与 5.6% 限定已写，但 constant“最强信号/只是花更多钱”过强，s/t 失败未在散文点明 |
| 5. 证据可重建性 | PARTIAL | 决策数字可重建，coverage 自洽且无 block 混算；但 aggregate 未登记、200 manifest/分片/snapshot/逐 rep 支出未入证据包 |
| 6. 源码绑定与漂移 | PASS | 200/200 绑同一快照；运行后 AA250 配置改动不影响 F02，但正文未记录该漂移 |

---

## §1 验收口径与预注册规则（第 1 项）—— PASS

### 1.1 预注册规则实读

| 要素 | 实读值 | 证据 |
|---|---|---|
| 判定单位 | 每个 rep 内独立判定；跨 rep 的 k/200 是描述性统计，不是验收阈值 | `docs/v3_phase_F02_formal.md:66`、`docs/v3_phase_F02_validation.md:265-267` |
| 收益主张数 | 2 项：`coupon_worth_issuing`（定向−不发券）、`targeting_better_than_random`（定向−同预算随机） | `configs/v3/evaluation.yaml`（benefit_evidence 族）；`src/causal_growth/evaluation/v3_f02.py` `decision_summary` |
| 检验方向/阈值 | 单侧，H0: diff ≤ 0，阈值 0.0 元/被分配用户 | `configs/v3/evaluation.yaml` decision threshold 0.0 |
| 多重性 | 两项一个 Holm step-down 家族，家族单侧 α=0.05；按 rep 独立校正 | `configs/v3/evaluation.yaml` `family_alpha_one_sided: 0.05`、`holm_step_down_on_paired_one_sided_tests` |
| 置信下限 | 由同一 Holm 家族反演；不得用未调整单侧区间替代 | `configs/v3/evaluation.yaml` `invert_same_holm_family_tests_no_unadjusted_ci_substitution` |
| 护栏 | `any_refund_30d_per_assigned_user`，定向−不发券，非劣效 margin=0.005，单侧 α=0.05，单侧上界 < 0.005 才算通过 | `configs/v3/design.yaml:40-41`；`configs/v3/evaluation.yaml` `require_guardrail_noninferiority: true` |
| 护栏界值性质 | `margin_evidence: hypothetical_business_tolerance_not_empirical_fact` | `configs/v3/design.yaml` |
| 分母 | 被分配到该臂的全部用户（全臂 ITT），不是支付/核销用户 | `configs/v3/evaluation.yaml` `denominator: every_user_assigned_to_policy_arm`；`docs/v3_phase_F02_formal.md:33` |
| 预算 | 三臂各 1/3；每活跃臂 0.2 元/人 × 该臂分配人数，约束**预测**期望成本 | `configs/v3/evaluation.yaml` `independent_validation`；`docs/v3_phase_F02_formal.md:35-38` |
| 跨 rep 汇总 | 通过率 + Clopper–Pearson 95%；差值均值 ± MC SE（sd/√R）；不把 200 个 p 合并成“总显著” | `docs/v3_phase_F02_validation.md:265-267` |
| 决策同时性 | 两项收益主张 + 护栏三者同时通过才记为“三项同时通过” | `configs/v3/evaluation.yaml` `require_guardrail_noninferiority`；正文 §4.1 |
| 冻结顺序 | 先冻结 `tau_hat/cost_hat` 与三臂动作，再生成订单/观测，之后才读真值 | `docs/v3_phase_F02_formal.md:42-45`；`docs/v3_phase_F02_validation.md:73-80` |

**结论**：预注册规则与正文口径一致；“每个 rep 是一次独立决策、k/200 只作描述”这一层没有被写成“200 次重复检验的合并显著性”。第 1 项 PASS。

### 1.2 验收定义中的缺口

- GOAL F02 行（`GOAL.md:26`）的交付列是“名单/汇总/manifest/代表五表”，核心描述含“全臂 ITT、随后审计”。正文的 ITT 完整，但“审计价值”没有单独报告（见 §7 P1-3）。
- `docs/v3_phase_F02_formal.md:1-8` 明确写“阶段状态仍未证实、独立评审未做”，这个自我限定是准确的；本评审不改写 GOAL 状态。

---

## §2 关键数字复算（第 2 项）—— PASS（结果层）

### 2.1 样本、分片与绑定

| 核验项 | 正文/主负责值 | 本评审复算 | 结论 |
|---|---|---|---|
| rep 数 | 200 | `aggregate/v3_phase_F02_formal_per_rep_claims.csv` 200 个唯一 `rep_id`；`out/f02_formal` 200 个 rep 目录；400 行 claims = 2×200 | 一致 |
| 分片 | 4×50 | `out/f02_formal/shard0..3/summary.json` 各 50 个 rep id（0–49、50–99、100–149、150–199），`failures=[]` | 一致 |
| 每 rep 用户数 | 200 000 | 600 行 ITT 的每 rep 对比人数与 manifest 三臂 `n_assigned` 对齐（rep0：targeted 66 594 / no_coupon 66 693 / random 66 713），三臂合计 200 000；rep0 `per_user.csv` 200 000 唯一 user | 一致 |
| `config_hash` | `e1aa4314b8d84b04a26150cb8ccea5a35dbe9b2d514fee724c56570d5b586d75` | 200/200 个 `manifest.json` 全部等于该值；4 个 shard summary、`snapshot_binding.json`、rep0 `manifest.json` 同值 | 一致 |
| 源码绑定 | 48 文件，`d8327ae0…` | 200/200 个 manifest 的 48 条 `source_hashes` 与 snapshot 逐值相同，`source_hashes_sha256=d8327ae0a190a5c2…`；`git_commit=7870b9a` | 一致 |
| 正式状态 | formal | 200/200 manifest `status=formal`、`truth_columns_present=false`、`failures` 空；4 个 shard `status=formal` | 一致 |

**注意**：上表的 200 个 manifest、4 个 shard summary、`snapshot_binding.json` 都在 `out/`，不在 `outputs/evidence/`。`outputs/evidence/f02_formal/manifest.json` 只是 rep0 一份；它能证明 rep0 的绑定，不能单独证明其余 199 个 rep（见 §5 P1-2）。

### 2.2 决策层逐项复算

从 `aggregate/v3_phase_F02_formal_per_rep_claims.csv`（400 行）重算，全部用表内全精度值，不读正文：

| 项 | 正文/主负责 | 独立复算 | 差异 |
|---|---|---|---|
| `coupon_worth_issuing` 通过 | 196/200 | 196/200；失败 rep = {0, 27, 89, 160} | 0 |
| `targeting_better_than_random` 通过 | 190/200 | 190/200；失败 rep = {0, 27, 50, 87, 89, 100, 107, 126, 160, 162} | 0 |
| 两项同时通过 | 190/200 | 190/200（coupon 失败集合是 targeting 失败集合的子集） | 0 |
| 三项（+护栏）同时 | 190/200 | 190/200 | 0 |
| 差均值（coupon） | 0.281630 | 0.281629889，sd 0.071734209，MC SE 0.005072375 | <1e-9 |
| 差均值（targeting） | 0.214167 | 0.214167067，sd 0.070922385，MC SE 0.005014970 | <1e-9 |
| 逐 rep 单侧 p 均值 | 0.005557 / 0.012922 | 0.005556732 / 0.012922123 | 0 |
| Holm p 中位 | 3.62e-7 / 7.34e-5 | 3.61844e-7 / 7.33973e-5 | 0 |
| Holm p 95 分位 | 0.002239 / 0.031755 | 0.0022388 / 0.0317548 | 0 |
| Holm p 最大 | 0.598019 | 0.598019（rep 0，两项同值） | 0 |
| 反演下限最小 | −0.072489 / −0.088656 | −0.072489 / −0.088656 | 0 |
| 调整 α 集合 | {0.025, 0.05} | 400 行只有 {0.025, 0.05}；逐 rep 先 0.05 后 0.025 | 0 |
| 单侧 p 公式 | 1−Φ(diff/se) | 逐行重算，最大绝对差 1.1e-16 | 0 |
| Holm 调整 p | cummax((m−i)p_(i)) | 400 行重算 0 不符 | 0 |
| 下限反演 | diff − z(1−α_adj)·se | 400 行重算 0 不符 | 0 |
| 策略 | greedy | 400 行 `selected_policy` 唯一值 `greedy_incremental_profit_per_cost` | 0 |

结论：196/200、190/200、190/200 与 Holm 中位、最大值、下限全部复现。正文 §4.1 的“不能写成 200/200 全胜”与数据一致：10 个 rep 至少一项失败，4 个 rep coupon 失败，且这 4 个全在 targeting 失败集合内。

### 2.3 护栏

从 `aggregate/v3_phase_F02_formal_per_rep_guardrail.csv`（200 行）：

- 200/200 通过；margin 0.005；α=0.05；单侧上界 = diff + z(0.95)·se，复算与表内 `ci_one_sided_upper` 0 不符。
- 最大上界 **0.003946489**（正文 0.003946），小于 0.005；均值上界 0.002196716；差均值 0.001374319（MC SE 3.9369e-5）。
- 分层最大上界：CF 0.003353、s_learner 0.003302、dr_learner 0.002804、t_learner 0.002630、constant 0.003946；正文表逐格一致。
- 复算 200/200 `passed=true` 与 `ci_one_sided_upper<margin` 完全一致；无一行“差异不显著被当作通过”。

### 2.4 分层计数与均值

从 `per_rep_claims.csv` 按 `selected_model` 分组：

| 模型 | R | coupon 通过 | targeting 通过 | 两项同时 | coupon 均值（MC SE） | targeting 均值（MC SE） | 护栏最大上界 | 定向真实/预测 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| causal_forest | 105 | 105/105 | 105/105 | 105/105 | 0.302109（0.005796） | 0.232561（0.005647） | 0.003353 | 1.053295 |
| s_learner | 71 | 71/71 | 69/71 | 69/71 | 0.282564（0.007074） | 0.215782（0.007801） | 0.003302 | 1.050059 |
| dr_learner | 12 | 12/12 | 12/12 | 12/12 | 0.236153（0.012931） | 0.175136（0.010230） | 0.002804 | 1.026797 |
| t_learner | 5 | 5/5 | 4/5 | 4/5 | 0.201725（0.026444） | 0.147861（0.041706） | 0.002630 | 0.995133 |
| constant | 7 | 3/7 | 0/7 | 0/7 | 0.100005（0.031121） | 0.036145（0.009617） | 0.003946 | 1.260221 |
| 合计 | 200 | 196 | 190 | 190 | — | — | — | — |

逐格与正文 §4.2 一致。表中的计数与均值来自 `per_rep_claims.csv`；最后一列“定向真实/预测”来自 `out/scratch/f02_agg_200_by_model.csv`，**不在证据包**（见 §5.2）。补充两个正文未明说的结构事实：

- **10 个 targeting 失败全部落在非 CF 层**：constant 7、s_learner 2（rep 50、107）、t_learner 1（rep 162）；CF 105/105、dr 12/12。
- **4 个 coupon 失败全部落在 constant 层**（rep 0、27、89、160）；constant 的 coupon 均值仍为 +0.100005（MC SE 0.031121），3/7 通过。
- s_learner 的 2 个失败差值为 +0.083625（原始单侧 p=0.067464，rep 50）与 +0.082286（原始单侧 p=0.075319，rep 107）；t_learner 的 1 个失败差值为 +0.058100（原始单侧 p=0.149623，rep 162）。它们不是“负效应”，是未达到单侧 Holm 门槛。

### 2.5 rep 0

从 `outputs/evidence/f02_formal/decision.json` / `decision.csv` / `guardrail.csv` 复算：

- `selected_model=constant`；`coupon_worth_issuing` diff=0.018504、原始单侧 p=0.369004、Holm p=0.598019、调整后下限=−0.072489，不通过。
- `targeting_better_than_random` diff=0.029111、原始单侧 p=0.299009、Holm p=0.598019、调整后下限=−0.079104，不通过。
- 护栏 diff=0.001784、se=0.0005084、上界 0.002620 < 0.005，通过；`method=wald_1sided_ci_unpooled_se`。
- 三臂 n=66 693 / 66 713 / 66 594，合计 200 000；与 `manifest.json` 的 `arms.n_assigned` 一致。
- rep0 `per_user.csv` 200 000 唯一 user；三臂 `observed_net_profit` 均值 2.611182 / 2.600575 / 2.629686；`observed_coupon_cost` 均值 0 / 0.199361 / 0.258282；退款率 0.007797 / 0.008799 / 0.009580；发放 0 / 16 416 / 26 110。这些与 rep0 汇总逐项一致。

### 2.6 支出

正文 §4.3 的支出数字均可复算；但**只有汇总/按模型均值在证据包，逐 rep 支出不在**：

- 预测支出/人 200 rep 最大值：`0.199999999833`（四舍五入到 6 位为 0.200000）；每臂总预算偏差最大 `−1.1043e-5` 元（random 臂 rep110，n=66 713，折合约 −1.7e-10 元/人）；全 200 rep 中每人预测支出最小 `0.199989799568`（targeted 臂 rep126，短额 −1.020e-5 元/人）。正文 line 119 的 `−1.1e-5` 是**某臂总偏差**，不是每人偏差（见 §7 P2-3）。
- 真实支出/人：定向 0.211268（max 0.261322），随机 0.200567（max 0.217798）；真实/预测均值 1.056345（定向，min 0.945840、max 1.306675）与 1.002839（随机，min 0.938633、max 1.088988）。
- 定向比随机实际多花 0.010701 元/人，等于 targeting 效应 0.214167 的 5.0%；定向相对**预测**高 5.6345%。
- 按模型定向真实/预测：CF 1.053295、s 1.050059、dr 1.026797、t 0.995133、constant 1.260221；与正文表一致。
- 发放总量：随机 3 239 534 张、定向 3 302 253 张；no_coupon 0。

**第 2 项结论**：结果层 PASS。196/200、190/200、190/200、Holm 中位、护栏最大上界、分层计数、rep0 p、支出统计均由本评审独立复算复现；未发现数值错误。证据来源完整性另见 §5。

---

## §3 统计口径（第 3 项）—— PASS（一处命名瑕疵为 P2）

### 3.1 分母

- 正文定义分母为“被分配到该臂的全部用户”（`docs/v3_phase_F02_formal.md:33`），配置 `denominator: every_user_assigned_to_policy_arm`。
- rep0 `per_user.csv` 200 000 行、200 000 唯一 user；三臂 `n_assigned` 之和 200 000；三臂 `observed_net_profit` 均值按全部分配用户计算，不是按支付/核销用户。
- no_coupon 臂 `observed_coupon_cost` 恒 0；定向/随机臂的成本只在该用户行出现一次。
- 结论：分母口径正确，没有“按核销用户”或“按发券用户”偷换。

### 3.2 两窗口等长

- 收益主指标 `net_profit_30d_per_assigned_user` 与护栏 `any_refund_30d_per_assigned_user` 都是 **30 天**窗口（`configs/v3/design.yaml:3,40`）。
- `convert_7d` 是辅助转化指标，不进入两项收益主张或护栏；`two_windows_per_user` 在 rep0 五表 check 中为 true（`docs/v3_phase_F02_formal.md:137`）。
- 结论：决策层两窗口等长；7 天转化不是决策窗口，不构成“窗口不等长”。

### 3.3 券成本只扣一次

`sql/v3_analytics.sql:91`：

```sql
gross_order_amount_cent - gross_refund_reversal_cent - goods_cost_cent
+ goods_cost_recovered_cent - fulfill_cost_cent
- (coupon_cost_initial_cent - coupon_return_cent) - refund_processing_fee_cent AS net_profit_cent
```

`coupon_cost_cent` 在 schema 中定义为 `coupon_cost_initial_cent - coupon_return_cent`（净券成本），在净利润中只减一次；`observed_coupon_cost` 是这一净额。rep0 的 no_coupon 成本恒 0、定向/随机臂成本非负且只在各自用户行出现，与“只扣一次”一致。结论：PASS。

### 3.4 护栏

- 指标：`any_refund_30d_per_assigned_user`；定向−不发券；margin=0.005；单侧 α=0.05；单侧上界 = diff + z(0.95)·se；未通过不得改界值/换指标/改看“差异不显著”（`docs/v3_phase_F02_validation.md:328-329`）。
- 本评审用逐行 `diff`、`se` 重算上界，200/200 与表内值一致，最大 0.003946489 < 0.005。
- 护栏是**设计层**的非劣效结论；margin 是假设的业务容忍度，不是经验事实（`configs/v3/design.yaml` `hypothetical_business_tolerance_not_empirical_fact`）。正文没有把 0.003946 写成“普遍安全”（这一点正确），但局限章节未引这条性质（见 §7 P2-5）。

### 3.5 Holm 族

- 400 行 claims，每 rep 恰 2 行，claim 仅 `coupon_worth_issuing` 与 `targeting_better_than_random`；没有第三项进入家族，也没有把护栏放进收益家族。
- 每 rep 独立：每 rep 的 `adjusted_alpha` 按该 rep 两项 p 排序后取 0.05/0.025；本评审按 `cummax((m−i)p_(i))` 逐 rep 重算，0 不符。
- 调整后下限用同一 Holm 的 `adjusted_alpha` 反演；本评审 400 行重算 0 不符。
- 未把 200 个 p 合并成一个“总显著”；`outputs/tables/v3_phase_F02_formal_summary.json` 的 aggregation 明确写 `rep_level_paired_pass_rate_and_mc_se_no_pooled_p_value`。
- 结论：Holm 族范围与逐 rep 独立性正确。

### 3.6 一处命名瑕疵（P2）

`configs/v3/evaluation.yaml` 的键名是 `holm_step_down_on_paired_one_sided_tests`，但实现用的是独立两臂标准误 `sqrt(se_left² + se_right²)`（`src/causal_growth/evaluation/v3_f02.py` `_contrast`），不是配对差的标准误。三臂随机化下两臂用户独立，独立 SE 在统计上是正确的；问题只是“paired”这个键名会误导读者以为用了配对检验。`docs/v3_phase_F02_validation.md:1.1` 已说明 F02 用独立 sqrt(se²+se²)，但配置键名未改。建议改键名/注释，或至少在正文写明“paired 指 rep 级配对汇总，不是用户级配对 SE”。这不影响数值。

### 3.7 正态近似

- p 值与置信界均为正态近似（单侧 p=1−Φ，Wald 上界）；没有 bootstrap。
- `docs/v3_phase_F02_validation.md:319` 已写“ITT 区间用正态近似；极端重尾下应改用 bootstrap 复核”。正文 §6 没有把这条列为局限（见 P2-5）。
- 结论：口径与预注册一致；局限披露不完整。

---

## §4 正文表述（第 4 项）—— PARTIAL

### 4.1 明确展示的异质性：PASS

正文 §4.2 表（`docs/v3_phase_F02_formal.md:88-98`）逐格列出：

- `constant`：coupon 3/7、targeting **0/7**、两项同时 0/7；
- `s_learner`：71/71、**69/71**、69/71；
- `t_learner`：5/5、**4/5**、4/5；
- `dr_learner` 12/12、`causal_forest` 105/105。

表下明确写“按 AGENTS §12.6，正文不得把 constant 与其余模型合并成‘定向普遍优于随机’的单一结论”（line 98）。§4.1 也写“结论只能写成‘多数 rep 内成立’，不能写成 200/200 全胜”（line 85）。这两点是正确的防过度表述。

### 4.2 但叙述仍有两处过强：PARTIAL

1. **“constant 层是最强信号”**（line 96）。0/7 是一个**决策结果**，不是“constant 无效应”的证明；constant 的 targeting 点估计是 **+0.036145（MC SE 0.009617）**，coupon 是 **+0.100005（0.031121）**、3/7 通过。7 个 rep 的 0/7 完全可能是低 power + 单侧 Holm 门槛，而不是“零效应”。正文没有给出 constant 的点估计与区间，只用“最强信号”概括，容易被读成“constant 已证明无价值”。
2. **“定向臂只是‘花更多钱、选不出更好的人’”**（line 96-97）。这句话把 0/7、1.2602 的支出比和“无 heterogeneity 可定向”连成一个机制结论；但 7 个 rep 的 targeting 差值仍为正，且 constant 的 coupon 仍有 3/7 通过。应改为“在 7 个 constant rep 的描述性结果中，targeting 未达到单侧 Holm 门槛；点估计仍为正，不能据此断言零效应；支出比 1.2602 提示该层的额外花费没有转化为可判定的 targeting 收益”。这是措辞层，不影响 190/200 的总数。

另外，正文表虽然列出 s 69/71、t 4/5，但**散文没有点明“10 个 targeting 失败全部在非 CF 层（constant 7、s 2、t 1），CF 105/105、dr 12/12）”**。这是比“constant 最强信号”更准确、也更能防止“定向普遍有效”误读的结构事实，建议补一句。

### 4.3 “计划同预算 vs 真实支出高 5.6%”：PASS

正文 §4.3（line 118-123）明确：

- 预测支出/人最大 0.200000；真实定向 0.211268、随机 0.200567；
- 真实/预测 1.056345（即高 5.6345%）、随机 1.002839；
- 定向比随机实际多花 0.010701 元/人，约为效应 0.214167 的 5.0%；
- “同预算”只能写成“计划支出同预算”，不能写成实付等支出。

§6.1 又写“预测成本 ≠ 真实成本”“不得只报前者”。这一限定是充分的。唯一要修的是 line 119 的偏差分母（P2-3），不是结论本身。

### 4.4 局限性/失效条件：PARTIAL

正文 §6 有 5 条（line 153-164）：预测 vs 真实成本、选模不稳定、代表 rep 只有 1 个、真值隔离、重训 bootstrap 属 G 阶段。方向正确，但漏了：

- 正态近似/重尾 bootstrap 复核（validation §6 line 319）；
- 护栏 margin 0.005 是假设的业务容忍度，不是经验事实（design.yaml `margin_evidence`）；
- 全队列审计价值是另一个估计量，不得与 ITT 混写（validation §2.1 line 67-71）；
- 逐 rep 实际支出/超支倍数尚未报告（validation line 188-189）；
- 五表 sha 已核但 bytes 未记录（见 P2-2）。

### 4.5 第 4 项结论

**PARTIAL**：异质性表、5.6% 限定、局限性章节都存在，且没有写“定向普遍有效”或“200/200 全胜”；但 constant 的“最强信号/只是花更多钱”属于过强解释，s/t 的失败没有在散文中点明，局限章节漏了 4 项。需要改措辞，不需要重算。

---

## §5 证据可重建性（第 5 项）—— PARTIAL（结果可重建，证据登记不完整）

### 5.1 仅凭 `outputs/evidence/` 能重建什么

本评审只用 `outputs/evidence/f02_formal/` 的以下文件就复现了 §2 的决策层：

- `aggregate/v3_phase_F02_formal_per_rep_claims.csv`（400 行，2/rep）；
- `aggregate/v3_phase_F02_formal_per_rep_guardrail.csv`（200 行，1/rep）；
- `aggregate/v3_phase_F02_formal_per_rep_itt.csv`（600 行，3/rep）；
- `aggregate/v3_phase_F02_formal_claims.csv` / `_guardrail.csv` / `_itt.csv` / `_spend.csv`（聚合）；
- `decision.json` / `decision.csv` / `arm_summary.csv` / `guardrail.csv` / `itt_contrasts.csv` / `manifest.json`（rep0）；
- `five_tables/manifest.json`（26 个 artifact 的 sha）。

可重建：196/200、190/200、190/200、Holm 中位/最大/下限、护栏 200/200 与最大上界、分层计数/均值、rep0 p、三臂均值、逐 rep 差为正的比例、支出均值/比值/发放总量。**这部分是可重建的，而且本评审已经逐项复现。**

### 5.2 不能仅凭证据包重建的部分（P1-2）

- **200 个逐 rep manifest 不在证据包**：`outputs/evidence/f02_formal/manifest.json` 只有 rep0 一份。正文 §3 line 60 写“48 个文件的 source_hashes（见每 rep manifest.json）”，读者在证据包中看不到其余 199 份，无法独立确认“200/200 都绑 `e1aa4314`/`d8327ae0`”。本评审是从 `out/f02_formal/shard*/rep*/manifest.json` 逐份读的，不是从证据包。
- **4 个分片 summary 不在证据包**：无法仅凭证据包确认 4×50、每个 shard 的 `protocol_config_hash` 与 `failures=[]`。
- **`snapshot_binding.json` 不在证据包**：无法仅凭证据包确认 `git_commit=7870b9a`、快照创建时间 03:39:04、48 文件与 `d8327ae0` 的绑定。
- **逐 rep 预测支出/超支倍数不在证据包**：`_spend.csv` 只有 3 行（三臂 200-rep 汇总），没有 200 行逐 rep 预测/真实/比值；正文的“预测最大 0.200000”与按模型支出比（constant 1.2602 等）来自 `out/scratch`，不在证据包。
- **审计表与全队列表被显式排除**：`coverage.json` 的 excluded 列了 `per_user.csv`、`audit_truth.csv`、`audit_policy_values.csv`、`audit_arm_contrasts.csv` 与五表本体。这是按 validation §5.4 的设计排除，不是偷表；但因此审计价值不可从证据包重建（P1-3）。
- **五表 bytes 不可核**：`five_tables/manifest.json` 的 26 个 artifact 只有 `role/sha256/rows/columns/dataframe_sha256`，没有 `bytes`；五表本体也不在证据包。正文 line 134-135 “逐个重算 sha256 与 bytes 全部一致”中的 bytes 无法按 manifest 复核（见 P2-2）。

### 5.3 `coverage.json` 自洽性

实读 `outputs/evidence/coverage.json`（截至评审时）：

- records = **54**，`total_bytes = 15 916 738`；逐条 bytes 求和 = 15 916 738，差 0。
- 54 条 target 全部存在；逐条 sha256 复算 **0 不符**；无 missing。AGENTS §12.7 的“读不懂必须响”在本表上没有被静默跳过。
- F02 正式记录只有 4 条（index 44–47）：`decision.json`、`freeze.json`、`manifest.json`、`five_tables/manifest.json`；4 条的 sha/bytes 均与文件一致。
- 但 `aggregate/` 下 7 张表（含本评审复算所依赖的逐 rep 表）**没有登记**，既无 sha 也无 rows。这与 AGENTS §12.1“别人需要复算的材料必须写进 coverage.json（含 sha256 与行数）”不符。
- 顶层 `last_refreshed_at = 2026-10-28T16:51:30+08:00`，但 `registry_repairs` 最后一条是 18:50 新增 6 条 test-log 记录；该时间戳没有随 18:50 修复更新。`total_bytes` 与 records 是 18:50 后的值（15 916 738 / 54），所以只是时间戳字段过期，不是字节错误。
- 正文 §1 line 17 仍写“records 44 → 48，total_bytes 15 866 131 → 15 903 166”；这在 16:51 写稿时是真的，但评审时已是 54 / 15 916 738（18:50 登记了 6 条测试日志）。这是“正文钉死登记计数”的过期，不是 F02 数据错误（P2-6）。

### 5.4 AGENTS §12.2 整表复制/block 混算

- 逐 rep claims 400 行 = 200×2，guardrail 200 行 = 200×1，ITT 600 行 = 200×3；无重复 `(rep_id, contrast)` 键，无额外 `true_aa`/其他 block 行。
- 证据包导出的是决策层表，不是“把 per_user/audit/五表整表复制进来”；`coverage.json.excluded` 逐项写明排除原因。没有发现 block 混算。
- 四个 shard 的逐 rep 表按 rep_id 合并，行数与 200 个 rep 对齐；没有“只导一个 shard 得到 50 行”的问题。
- 结论：§12.2 这一项 PASS。

### 5.5 第 5 项结论

**PARTIAL**：决策层关键数字**可以**仅凭证据包重建；`coverage.json` 的 54 条记录在存在性、sha、bytes 求和上自洽，且没有 block 混算。但证据包缺少 200 个逐 rep manifest、4 个 shard summary、snapshot binding、逐 rep 支出/审计表，且 7 张 aggregate 表未登记，因此“仅凭证据包完整重建所有关键断言”不成立。按 AGENTS §12.1 严格口径，这是 P1-2。

---

## §6 源码绑定与运行期漂移（第 6 项）—— PASS（附一条 P2 记录要求）

### 6.1 200 rep 绑定

- 200/200 `out/f02_formal/shard*/rep*/manifest.json`：`status=formal`、`config_hash=e1aa4314…`、48 条 `source_hashes` 逐值相同、`source_hashes_sha256=d8327ae0…`、`truth_columns_present=false`、`selected_policy` 非空、`failures` 空。
- 4 个 shard `summary.json`：`approval=F02-FORMAL-20261028-R200`、`scenario=L1_main`、`n_per_rep=200000`、`policy=greedy_incremental_profit_per_cost`、各 50 个 rep、`failures=[]`、起止时间在 03:39–16:39 之间。
- `out/f02_formal_snapshot/snapshot_binding.json`：`created_at=2026-10-28T03:39:04+08:00`、`git_commit=7870b9a`、48 文件、`source_hashes_sha256=d8327ae0…`、`protocol_config_hash=e1aa4314…`。
- `out/logs/f02_merge_20261028_1636.log`：4 shards、200 rep dirs、写 400/200/600/2/1/3/3 行、coverage written、exit=0（16:37）。
- 结论：200 个 rep 确实绑定到同一快照/同一 48 文件源码；没有运行期源码漂移。

### 6.2 运行后配置漂移

- 当前 `HEAD=1b64b3b`；`git diff --stat 7870b9a -- configs/v3` 显示 3 个文件、12 行改动：`configs/v3/design.yaml`（`repeats_per_layer` 1000→250）、`configs/v3/execution.yaml`（`tier1_aa_per_layer` 1000→250）、`configs/v3/scenarios.yaml`（4 个 `R`、4 个 `complete_aa`、2 个计划计数）。这是 GOAL 2026-10-28 11:05 用户裁决的 G 阶段 AA250 补丁，发生在 F02 四分片退出后。
- 当前 `src/` 与 `sql/` 与快照逐字节一致；变化只在 `configs/v3/*.yaml`。F02 的 200 个 manifest 仍绑定快照的 `e1aa4314`/`d8327ae0`，所以 F02 结果不受这次补丁影响。
- **风险记录**：正文没有写“运行后 configs 已被 G AA250 补丁改动；F02 仍以 `out/f02_formal_snapshot` 为准，不能用当前 live configs 直接复跑 F02 并期望同一 hash”。这应在 §3/§7 补一句（P2-8）。若不补，后续读者用当前 live 配置复跑会得到不同 `config_hash`，误以为 F02 绑定失效。
- 结论：绑定 PASS；漂移记录 PARTIAL（文档层）。

---

## §7 条件清单

### P1（改状态为“通过”前必须落地；均不需重跑）

**P1-1 逐 rep 实际支出/超支倍数表**
- 依据：`docs/v3_phase_F02_validation.md:186-189`（18:46 裁决）“正式 200 rep 必须逐 rep 报告实际支出与超支倍数”。
- 现状：正文只给三臂均值/min/max/按模型均值；`aggregate/v3_phase_F02_formal_spend.csv` 仅 3 行。
- 要求：从 `out/f02_formal/shard*/rep*/arm_summary.csv`（或 rep 级支出列）导出 200 行逐 rep 表，至少含 `rep_id, arm, predicted_per_assigned, realized_per_assigned, realized_to_predicted, overspend_ratio`；写入正文附表或证据包并在 `coverage.json` 登记 sha/rows。若逐 rep 表过大，至少给 200 行的紧凑 CSV；不能只给 min/max。

**P1-2 证据包补登记/补导出**
- 依据：AGENTS §12.1“只用 outputs/evidence/ 就能重建文档里的关键数字”；正文 §3 line 60“见每 rep manifest.json”但证据包只有 rep0。
- 要求（任选其一，建议全做）：
  1. 把 `aggregate/` 7 张表逐条登记进 `coverage.json`（sha256、bytes、rows）；这是本评审复算 196/200 等数字的直接输入，目前无登记。
  2. 导出 200 行 `per_rep_binding.csv`：`rep_id, shard, manifest_sha256, status, config_hash, source_hashes_sha256, truth_columns_present, selected_model`，并登记。
  3. 导出 4 个 `shard*_summary.json` 与 `snapshot_binding.json`（或将其关键字段汇总为一张 binding 表），登记。
  4. 若逐 rep 支出表（P1-1）生成，一并登记。
- 目的：让“200/200 绑 `e1aa4314`/`d8327ae0`”“4×50”“预测最大 0.200000”成为证据包内可核事实，而不是只能信 `out/` 或主负责自述。

**P1-3 审计价值的范围与报告**
- 依据：GOAL F02 核心描述“全臂 ITT、随后审计”；`docs/v3_phase_F02_validation.md:67-71`“交付 ITT 与全队列审计价值回答的不是同一个问题，报告时必须分开写”。
- 现状：正文无审计价值章节；证据包 excluded 了 3 张 audit 表和 `per_user.csv`；`docs/v3_phase_F02_formal.md:162-163` 只讲“真值隔离”，没有给审计结果。
- 要求：二选一并写清楚：
  1. 若审计价值属于 F02 交付：补一节“全队列审计价值（另一个估计量）”，与 ITT 分开，给审计口径、n_selected、价值/成本与限制；导出审计聚合表并登记（至少 aggregate 级，不必逐用户）。
  2. 若审计价值移交 D01/G：在 §5/§6 明确“F02 只交付 ITT；全队列审计价值移交 D01/G，理由/接口为……”，并解释 GOAL “随后审计”的落点。
- 不允许保持“既没报告也没声明移交”的悬空状态。

### P2（同批修；文档/元数据层）

**P2-1 把“Wilson 95%”改为“Clopper–Pearson 95%”**
- 正文 §4.1 表头写“Wilson 95%”，但报告数值实际是 CP：196/200 CP [0.949586, 0.994524]（Wilson 为 [0.949713, 0.992196]），190/200 CP [0.909972, 0.975766]（Wilson [0.910422, 0.972617]），200/200 CP [0.981725, 1.0]（Wilson [0.981155, 1.0]）。数值与 validation §5.4 的 CP 要求一致，只有标签错。改标签，不要改数。

**P2-2 修正“26 个 artifact sha256 与 bytes 全部一致”**
- `five_tables/manifest.json` 的 26 个 artifact 只有 `role/sha256/rows/columns/dataframe_sha256`，没有 `bytes`；五表本体不在证据包。本评审在 `out/` 对 26 个 sha 做了 26/26 一致核对，但 bytes 无法按 manifest 复核。改为“26/26 sha256 一致；bytes 未记录（或补写入 manifest/证据包）”。

**P2-3 预算偏差写分母**
- line 119 “预算偏差最大 −1.1e-5”是**某臂总预算偏差（元）**：random 臂 rep110，n=66 713，折合约 −1.7e-10 元/人；全 200 rep 中每人预测支出最小 0.199989799568（targeted 臂 rep126，短额 −1.020e-5 元/人）。预测/人最大 0.199999999833，四舍五入才是 0.200000。按 AGENTS §12.5 补分母，避免读者把 −1.1e-5 当成每人偏差。

**P2-4 constant 叙述收窄，并补 s/t 结构事实**
- 把“constant 层是最强信号”“定向臂只是‘花更多钱、选不出更好的人’”改为描述性表述：constant 7 个 rep 的 targeting 0/7、coupon 3/7；targeting 点估计 +0.036145（MC SE 0.009617），不能据此断言零效应；支出比 1.2602 提示额外花费未转化为可判定 targeting 收益。
- 补一句：“10 个 targeting 失败全部在非 CF 层（constant 7、s_learner 2、t_learner 1）；CF 105/105、dr 12/12。”这比“constant 最强信号”更准确，也直接回应“定向普遍有效”的风险。

**P2-5 补局限章节**
- 正态近似/重尾 bootstrap 复核（validation §6 line 319）；
- 护栏 margin 0.005 的假设性质（design.yaml `margin_evidence`）；
- 全队列审计价值与 ITT 是不同估计量（validation §2.1）；
- 逐 rep 支出/超支倍数的报告义务（P1-1）；
- 不把“0/7”当“零效应”证明。

**P2-6 顶层登记计数过期**
- 正文 §1 写 48 条 / 15 903 166 bytes；评审时实读 54 条 / 15 916 738 bytes（18:50 新增 6 条测试日志）。把计数改为“截至 F02 合并 16:51 为 48 条；截至评审 19:17 为 54 条（含 18:50 测试日志）”，或去掉钉死数字，改为“以 coverage.json 实读为准”。`coverage.json.last_refreshed_at` 仍是 16:51:30，与 18:50 修复不一致，建议刷新。

**P2-7 `paired` 键名**
- `holm_step_down_on_paired_one_sided_tests` 与实际独立两臂 SE 不一致。改键名/注释，或在正文说明“paired 指 rep 级配对，不是用户级配对”。不影响数值。

**P2-8 运行后配置漂移记录**
- 在 §3 或 §7 加一句：F02 绑定 `out/f02_formal_snapshot`（git 7870b9a，`e1aa4314`/`d8327ae0`）；运行后 `configs/v3/{design,execution,scenarios}.yaml` 已按 2026-10-28 11:05 用户裁决做 G AA250 补丁（3 文件 12 行），因此当前 live configs 不能直接复跑出同一 F02 hash；F02 结果不受影响。避免后续“复现失败”误判。

---

## §8 可支持的结论 / 不可支持的结论

### 8.1 可支持的结论（有证据、已独立复算）

1. 在 `L1_main`、n=200 000、3 臂各 1/3、0.2 元/人**预测**预算、冻结策略 `greedy_incremental_profit_per_cost`、200 个 rep 的设置下，F02 的预注册决策规则被逐 rep 正确执行：两项收益主张同属一个单侧 Holm 家族，家族 α=0.05，护栏 margin=0.005、单侧 α=0.05，分母为全部被分配用户；没有把 200 个 p 合并成“总显著”。
2. 200 个 rep 全部完成并通过逐 rep 绑定校验：`status=formal`、`config_hash=e1aa4314…`、48 文件 `source_hashes` 同一、`d8327ae0…`、`git_commit=7870b9a`、`truth_columns_present=false`、无 failures；分片为 4×50。
3. `coupon_worth_issuing` 196/200 通过，差均值 +0.281630 元/人（MC SE 0.005072），Holm p 中位 3.61844e-7；`targeting_better_than_random` 190/200 通过，差均值 +0.214167（MC SE 0.005015），Holm p 中位 7.33973e-5；两项+护栏同时 190/200。这些是**逐 rep 决策的通过比例**，不是对部署收益的点估计。
4. 护栏 200/200 通过，最大单侧上界 0.003946489 < 0.005；这是设计层非劣效结论，margin 是假设的业务容忍度。
5. 分层描述：CF 105/105 + 105/105；s_learner 71/71 + 69/71；dr_learner 12/12 + 12/12；t_learner 5/5 + 4/5；constant 3/7 + 0/7。10 个 targeting 失败全部在 constant（7）、s（2）、t（1）；4 个 coupon 失败全部在 constant。CF 与 dr 无失败。
6. rep 0（constant）两项均不通过：coupon diff 0.018504、Holm p 0.598019、下限 −0.072489；targeting diff 0.029111、Holm p 0.598019、下限 −0.079104；护栏通过（上界 0.002620）。rep0 不能单独支撑或否证“定向有效”。
7. 全臂 ITT：no_coupon 2.583457、random 2.650919、targeted 2.865086 元/人；targeted−no_coupon +0.281630、targeted−random +0.214167、random−no_coupon +0.067463（95% t 区间 [−0.041171, 0.176097]，169/200 为正）。前两者逐 rep 为正 200/200；random−no_coupon 不是预注册主张，不能当作“发券普遍有效”。
8. 预测支出/人全 200 rep 最大 0.199999999833（即 0.200000，6 位）；真实支出定向 0.211268、随机 0.200567；定向/预测 1.056345（高 5.6345%），定向比随机实际多 0.010701 元/人（约为 targeting 效应的 5.0%）。因此只能支持“计划预测预算相同”，不能支持“实际支出相同”。
9. 仅凭 `outputs/evidence/f02_formal/` 的 aggregate 表可以重建第 3、4、5、6、7、8 条中的决策层与支出汇总数字；`coverage.json` 54 条记录存在性、sha256、bytes 求和自洽，0 missing、0 bad sha；没有整表复制/block 混算。
10. F02 运行期没有源码漂移：200 个 rep 的 48 文件 source hashes 与快照一致；运行后的 configs 变化是 GOAL 记录的 G AA250 补丁（3 文件 12 行），不影响 F02 绑定的快照。

### 8.2 不可支持的结论

1. **“定向普遍有效 / targeting 在所有模型和所有 rep 上都优于随机”**：constant 0/7、s 69/71、t 4/5，10 个 rep 未通过；CF 105/105 只是分层结果，不能外推到全部层。
2. **“constant 层零效应 / constant 没有价值”**：0/7 是决策结果；constant 的 targeting 点估计 +0.036145（MC SE 0.009617），coupon 点估计 +0.100005（0.031121）、3/7 通过。7 个 rep 不足以证明零效应。
3. **“200/200 全部通过 / 所有 rep 全胜”**：targeting 190/200、coupon 196/200、两项+护栏 190/200；10 个 rep 至少一项失败。
4. **“实际支出等于预算 / 两臂实际等支出”**：定向真实/预测 1.056345，比随机实际多 0.010701 元/人；只能写“计划预测预算相同”。
5. **“发券普遍值得（无论定向还是随机）”**：随机−不发券 +0.067463，95% t 区间跨 0（[−0.041171, 0.176097]），169/200 为正；预注册的 `coupon_worth_issuing` 是定向−不发券，不是随机−不发券。
6. **“200 个 p 合成一个总显著 / 跨 rep 的合并 p 值”**：F02 没有 pooled p；k/200 只作描述，不能当作重复检验的合并证据。
7. **“rep 0 可以代表 200 rep / rep0 的零结果否证定向”**：rep0 是 constant，正文已明确不得单独使用；定向是否有效看分层聚合，而不是 rep0。
8. **“护栏在真实业务普遍安全 / 0.003946 证明 margin 0.005 足够”**：margin 是假设的业务容忍度，不是经验事实；最大上界 0.003946 已消耗 79% 的 margin，且是合成 DGP/L1_main 单场景。
9. **“审计价值已证明 / 全队列部署价值等于 ITT”**：正文没有审计价值章节，证据包排除了审计表；ITT 与全队列审计是不同估计量。P1-3 落地前不能作任何审计价值结论。
10. **“可部署 / 可外推到真实用户、其他预算、其他券面额、其他场景”**：合成数据/已知 DGP、L1_main、0.2 元/人、单一冻结策略；正文 §5 已限定，本评审确认该限定必要。
11. **“逐 rep 支出/超支倍数已报告”**：目前只有三臂汇总/按模型均值；P1-1 落地前不能声称已满足 18:46 裁决。
12. **“26 个 artifact 的 bytes 已核对一致”**：manifest 无 bytes 字段、五表本体不在证据包；只能支持“26/26 sha256 一致”。

---

## §9 评审方法与限制

- 本评审只读；未运行任何 R>0 作业、pytest、`scripts/` 或拟合；未修改 `configs/`、`src/`、`tests/`、`GOAL.md`、`TODO.md`、`outputs/` 既有文件；唯一写入是本文。
- 复算工具：Python 3/pandas（`.venv`），从 evidence 与 `out/` 读 CSV/JSON；未使用 scipy 的 p 值函数做“拟合”，只用正态 CDF/分位数做公式核对。
- 不能从证据包核的五表 bytes：在 `out/` 对 26 个 artifact 做了 sha256 核对（26/26 一致），但 manifest 无 bytes，正文的 bytes 声明仍判 P2-2。
- 不能从证据包核的 200 个 manifest/4 个 shard/snapshot binding/逐 rep 支出：从 `out/` 实读并逐份核对；这暴露的是证据导出缺口（P1-2），不是结果错误。
- 本评审未对 DGP 生成器、learner 实现、SQL 全链路做代码级重跑；这些属于 F02 运行前的工程验证范围。本评审的对象是“200 rep 正式结果 + 证据 + 正文断言范围”。
- 评审时间 2026-10-28 19:17（北京时间）。若主负责在此时点之后又改了 `configs/`/`outputs/`，以本评审实读的快照/文件状态为准；本文不覆盖评审后的改动。
