# D03 正式 R：200 rep × n=200 000（L1_main）

> 合成数据 / 已知 DGP。**状态：正式 R 已跑完、合并与证据已导出（2026-10-27 17:15，北京时间）；D03 在独立评审通过前仍标“未证实”，本文只陈述证据，不写“通过”。**

本文件回答 GOAL D03 的三件事：五类估计器的方法对照是否成立、选模在 rep 间是否稳定、
策略层的比较是否按同一 rep/同一批用户/同一预算配对。所有数字必须能从
`outputs/tables/v3_phase_D03_formal_*.csv` 复算；运行证据在
`outputs/evidence/d03_formal/`。

## 0. 一句话结论

正式 R 的 200 个 rep 全部跑完且内部校验全过：平均 ATE 偏差小且不显著，但**个体校准
普遍很弱**（除 causal_forest 外斜率中位数 0.10–0.47）；策略层“greedy 对 business”的
符号**按模型分裂**（CF/S 为正，constant/T/DR 为负），聚合结论会被选模构成决定；
按真实支出的预算合规率远低于按预测成本的合规率。**这些是“未证实”阶段的结果陈述，
不是 D03 通过判定。**

## 1. 运行事实

| 项 | 值 |
|---|---|
| 设计 | 200 rep × n=200 000（test 60 000）× 5 模型 × 8 预算 × 9 策略 |
| 场景 | L1_main，`time_mode=static` |
| 选模规则（冻结） | `validation_crossfit_dr_policy_value_lower_confidence_bound` |
| 快照 | `out/d03_formal_snapshot/`，combined sha256 `be0d48f4a10d…`，83 文件，git commit `130a309` |
| 启动 | 2026-10-27 12:54:18（北京时间），4 个独立进程，每分片 50 rep |
| 完成 | 2026-10-27 17:13:36–17:14:48（四分片），墙钟约 **4 小时 20 分**；4 个 `run.err` 均为 0 字节 |
| 合并 | 200 rep / 1 000 行 per-rep / 72 000 行网格；`config_hash=e1aa4314…` 四分片一致 |
| 证据 | `outputs/evidence/d03_formal/coverage.json`（10 个文件，含 manifest、快照绑定、分片 summary/log） |

复现顺序：`scripts/25_merge_d03_formal.py` → `scripts/26_d03_formal_tables.py` →
`scripts/27_export_d03_evidence.py`。25 在写盘前校验 rep 覆盖/去重、网格形状、
chosen 覆盖与合规标记；27 在校验 rep 并集、四分片 `config_hash`、`run.err` 全空、
合并表哈希后才写 coverage。

## 2. 选模频率

来源：`v3_phase_D03_formal_selection.csv`（分母 = 200 rep）。

| 模型 | 被选次数 | 占比 | 平均排名 | 选模分数中位数 |
|---|---:|---:|---:|---:|
| causal_forest | 105 | 0.525 | 1.710 | +0.0605 |
| s_learner | 71 | 0.355 | 1.855 | +0.0490 |
| dr_learner | 12 | 0.060 | 3.385 | +0.0164 |
| constant | 7 | 0.035 | 4.505 | −0.0183 |
| t_learner | 5 | 0.025 | 3.545 | +0.0140 |

20 rep 诊断里 constant 被选 9/20，正式 R 只有 7/200（3.5%），说明那主要是小样本波动；
但“五个模型都当过第一名”仍成立，且 88% 的 rep 由 CF/S 两个模型包揽。**后续策略结论
必须按模型配对呈现，不能只报 chosen 或全模型平均。**

## 3. 偏差与校准

来源：`v3_phase_D03_formal_calibration.csv`。`mean_bias_cny` 是 ATE 估计减真值的
rep 均值，SE 是 rep 间 SE；`median_calibration_slope` 是个体 τ̂ 对 τ_true 的回归斜率，
1 表示个体排序与幅度都可信。

| 模型 | 范围 | n | mean_bias ± SE（元/人） | 相对偏差中位数 | **最大绝对相对偏差** | 校准斜率中位数 | Pearson r 中位数 | RMSE 中位数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| constant | all | 200 | −0.00431 ± 0.00440 | −0.0189 | **0.702** | — | — | 6.178 |
| t_learner | all | 200 | −0.00096 ± 0.00459 | −0.0054 | **0.803** | 0.114 | 0.043 | 6.496 |
| s_learner | all | 200 | +0.00224 ± 0.00436 | −0.0119 | **0.846** | 0.467 | 0.078 | 6.184 |
| causal_forest | all | 200 | −0.00017 ± 0.00447 | −0.0111 | **0.801** | 0.754 | 0.103 | 6.149 |
| dr_learner | all | 200 | −0.00081 ± 0.00468 | −0.0109 | **0.817** | 0.098 | 0.039 | 6.561 |
| causal_forest | chosen_only | 105 | −0.00600 ± 0.00603 | −0.0325 | 0.595 | 0.762 | 0.103 | 6.150 |
| s_learner | chosen_only | 71 | +0.01006 ± 0.00798 | +0.0146 | 0.846 | 0.451 | 0.076 | 6.177 |
| dr_learner | chosen_only | 12 | −0.00672 ± 0.01742 | −0.0699 | 0.336 | 0.101 | 0.042 | 6.551 |
| constant | chosen_only | 7 | +0.01701 ± 0.03035 | +0.0526 | 0.518 | — | — | 6.077 |
| t_learner | chosen_only | 5 | −0.02046 ± 0.02440 | −0.0539 | 0.280 | 0.121 | 0.044 | 6.497 |

解读：

1. **平均 ATE 没有显著偏差**：五个模型的 |mean_bias| ≤ 0.0044 元/人，均小于 1 个 SE；
   这是“平均处理效应估得准”，不是“个体 τ̂ 可信”。
2. **个体校准弱**：除 CF（0.754）外，斜率中位数只有 0.098–0.467，Pearson r 0.04–0.10；
   chosen_only 也没有改善。策略排序依赖个体预测，这是 F01 OPE 与 F02 验证的主要风险点。
3. **相对偏差要报最差**（AGENTS §12.5）：最大绝对相对偏差 0.70–0.85，出现在真值接近 0
   的 rep；不能只报 −0.005 到 −0.019 的中位数。分母是真值 ATE 的 rep 绝对值。

## 4. 策略层：按模型配对

来源：`v3_phase_D03_formal_policy_value.csv`、`_paired_diff.csv`、
`_paired_diff_chosen.csv`、`_oracle.csv`。每条配对差都在同一
`(rep_id, model, per_user_budget_cny)` 内计算策略 − `business_rule_new_user_then_cart`，
跨 rep 聚合给出 `n_pairs`、SE 与胜/负/平（AGENTS §12.6）。

**0.2 元档、all_models（每格 200 rep 配对）：**

| 模型 | greedy − business（元/人） | SE | 胜/负（rep 数） | 8 档中差值为正的档数 |
|---|---:|---:|---:|---:|
| causal_forest | **+0.0216** | 0.0011 | 183 / 17 | 7 |
| s_learner | **+0.0079** | 0.0011 | 146 / 54 | 6 |
| dr_learner | −0.0462 | 0.0011 | 0 / 200 | 2 |
| t_learner | −0.0588 | 0.0011 | 0 / 200 | 2 |
| constant | −0.1951 | 0.0013 | 0 / 200 | 1 |

**chosen_only 同档**（线上口径子集）：CF +0.0236（99/6）、S +0.0049（42/29）、
DR −0.0469（0/12）、T −0.0628（0/5）、constant −0.1900（0/7）。符号与 all_models 一致，
说明差异不是选模频率造成的；但**“greedy 更好”只在 CF/S 上成立**，在另外三个模型上
方向相反且幅度更大。任何跨模型聚合（例如“平均 +0.02”）都会被模型构成翻转，禁止使用。

**事后最优（oracle，0.2 元档，按模型等权平均 200 rep）：**

| 策略 | 平均后悔（元/人） | 夺魁率 |
|---|---:|---:|
| business_rule_new_user_then_cart | **0.0066** | 66.8% |
| greedy_incremental_profit_per_cost | 0.0607 | 28.3% |
| greedy_local_swap | 0.0607 | 29.3% |
| incremental_profit_rank | 0.0793 | 0.3% |
| predicted_profit_rank | 0.1850 | 0.0% |
| random_same_budget | 0.2103 | 0.0% |

oracle 只在受预算约束的策略中取最优（`all_coupon_unconstrained_reference` 不参与）。
这里 business 的平均后悔更低，是因为它在 constant/T/DR 这三个“greedy 会选错人”的模型上
接近最优；**不能据此说 business 全面优于 greedy**，也不能把 oracle 后悔当线上可得收益。

`greedy_local_swap` 与 greedy 的配对差在 8 档上逐档相同（表中未单列），说明本场景下
局部交换没有改变名单；这是结果，不是实现被跳过——两者 `n_selected` 与真实价值一致。

## 5. 双口径预算合规

来源：`v3_phase_D03_formal_compliance.csv`。`by_hat` 用冻结的预测成本判断，
`by_true` 用事后真实券成本判断；两者不可互相替代。

**0.2 元档：**

| 模型 | greedy by_hat | greedy by_true | business by_true | 随机 by_true |
|---|---:|---:|---:|---:|
| causal_forest | 1.000 | **0.110** | 0.680 | 0.640 |
| s_learner | 1.000 | **0.130** | 0.600 | 0.620 |
| dr_learner | 1.000 | 0.265 | 0.520 | 0.575 |
| t_learner | 1.000 | 0.390 | 0.545 | 0.600 |
| constant | 1.000 | **0.000** | 0.465 | 0.555 |

**0.04 元档**：greedy 的 by_true 合规率 0–20%，constant 的 `max_spend_to_budget_ratio`
达到 **1.92 倍**；business 为 41.5%–100%，随机为 50.5%–100%（全体模型/预算汇总范围）。
`all_coupon_unconstrained_reference` 不是可执行策略，其支出比约 20.6 倍只作参照。

结论：**预测成本口径的 100% 合规不能当支出上限**。F 阶段的“预算可行”建议必须同时
报告真实支出合规率与超支风险；不能承诺硬上限。

## 6. 判定门槛与检查项

正式 R 结束时必须逐条全绿，才能进入独立评审：

- [x] 200 rep 恰好各出现一次（rep 0..199，无缺无重）；
- [x] 每 rep 5 模型，per-rep 表 1 000 行；
- [x] 网格 200 × 5 × 8 × 9 = 72 000 行，每 `(rep, model, budget)` 恰 9 策略；
- [x] 每 rep 恰一个 chosen，且网格 chosen 行恰为该模型 × 8 预算 × 9 策略；
- [x] 四分片 `config_hash` 一致，快照哈希与 manifest/绑定一致；
- [x] 4 个 `run.err` 全空；
- [x] 合并表 sha256 与 summary 一致；`outputs/evidence/d03_formal/coverage.json` 写入成功；
- [ ] 至少一项独立评审复核：方法对照、选模频率、配对网格、双口径合规。

## 7. 局限与结论失效条件

- 合成数据、单一场景（L1_main）、单一时间模式（static）；结论不外推到真实业务或
  其他 DGP 层。
- 选模规则是冻结的单一规则；换规则会改变 chosen 分布，进而改变线上口径的策略结论。
- 真值只用于评估；`tau_true/cost_true` 不参与训练、选模与种子派生。
- 策略结论以 8 档预算为限；预算档之间的最优策略可能切换，不能线性外推。
- 平均 ATE 无偏不代表个体 τ̂ 可信；本文的策略结论只对应“用该模型打分后的名单”，
  不对应“真实个体增量”。
- 行为结论文本一旦与 `outputs/tables/` 中的数字不一致，以表为准并重修文档。

## 8. 产物与复现

| 产物 | 路径 |
|---|---|
| 合并逐 rep | `outputs/tables/v3_phase_D03_formal_per_rep.csv` |
| 合并网格 | `outputs/tables/v3_phase_D03_formal_policy_grid.csv` |
| 合并 summary | `outputs/tables/v3_phase_D03_formal_summary.json` |
| 报告表（7 张 + meta） | `outputs/tables/v3_phase_D03_formal_{selection,calibration,policy_value,paired_diff,paired_diff_chosen,oracle,compliance}.csv` / `_report_meta.json` |
| 运行证据 | `outputs/evidence/d03_formal/`（manifest、快照绑定、4 分片 summary/log、coverage.json） |

