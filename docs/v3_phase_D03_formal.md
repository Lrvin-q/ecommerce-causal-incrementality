# D03 正式重复（200 rep）：模型比较、选模与策略价值

> **合成数据 / 已知 DGP**｜scenario `L1_main`（L1，randomized，static）｜R = 200｜n = 200 000/rep
> （train 100 000 / validation 40 000 / test 60 000）｜config_hash `e1aa4314b8d84b04a26150cb8ccea5a35dbe9b2d514fee724c56570d5b586d75`
> 维护时间：2026-10-27 19:25；20:45 更正 §0 的 `cost_hat` 合规格数（160→320，按落盘表重数）
> （北京时间）。
> **状态：正式 R 已跑完、证据已导出；D03 仍未证实，等待独立评审。** 本文件只陈述数字，
> 不代替评审结论。

## 0. 结论先行

1. **选模高度不稳定**：5 个候选模型都当过第一名。200 个 rep 的分布是
   `causal_forest` 105、`s_learner` 71、`dr_learner` 12、`constant` 7、`t_learner` 5。
   任何"固定用某个模型"的写法都会与冻结规则不一致。
2. **群体平均无偏，但个体排序能力弱**：五个模型的均值偏差都在 ±0.005 元/人以内，
   但个体 Pearson 相关系数中位数只有 0.039–0.103，`causal_forest` 的校准斜率中位数
   0.754，`t_learner`/`dr_learner` 只有 0.114/0.098。**"平均无偏"不能替代"个体可用"。**
3. **策略结论按模型分裂**：0.20 元/人档位、同一 rep 同一批用户配对比较，
   `greedy_incremental_profit_per_cost − business_rule` 在 `causal_forest` 上
   +0.0216 元/人（183/200 rep 胜）、`s_learner` +0.0079（146/200 胜）；
   在 `dr_learner` −0.0462、`t_learner` −0.0588、`constant` −0.1951。
4. **选模后悔远小于"事后最优"**：同一 rep 上"选中模型 − 5 模型事后最优"的贪心策略，
   0.20 档为 −0.0193 元/人（SE 0.0030，n=200）。诊断阶段（20 rep × n=20 000）的
   −0.1007 不能外推到正式 R。
5. **"同预测预算"不等于"同实际支出"**：按 `cost_hat`，除无约束全发券参照外的
   **320/320 格**全部合规（8 个预算内策略 × 5 模型 × 8 档）；
   按 `cost_true` 在 0.20 档的 rep 级合规率：`t_learner` 39.0%、`dr_learner` 26.5%、
   `s_learner` 13.0%、`causal_forest` 11.0%、`constant` 0%。

## 1. 运行事实

| 项 | 值 |
|---|---|
| 分片 | 4 个独立进程，各 50 rep（rep 0–49 / 50–99 / 100–149 / 150–199） |
| 状态 | 每片 `status=formal_r`、`reps=50`、`config_hash` 一致 |
| 起止 | 2026-10-27 12:54 启动；四分片 17:13–17:14 写完（北京时间），墙钟约 4 小时 20 分 |
| 单 rep 耗时 | rep 0 为 308.1 s，rep 199 为 303.2 s |
| 产物 | `v3_phase_D03_formal_per_rep.csv` 1 000 行 = 200×5；`v3_phase_D03_formal_policy_grid.csv` 72 000 行 = 200×5×9×8 |
| 绑定 | 快照 `out/d03_formal_snapshot/`（83 文件）；证据包 `outputs/evidence/d03_formal/`（10 文件，含四分片 run.log/summary 与 snapshot_binding） |
| 源码只读 | 四个 `run.err` 全空；运行期间未改 `src/`、`sql/`、`configs/v3*` |

选模规则（A 阶段冻结）：在 validation 上用交叉拟合 DR 策略价值下置信界排序，
每个 rep 独立选出 `chosen=True` 的模型；真值只在选模完成后用于评估。

## 2. 选模频率与分差

`outputs/tables/v3_phase_D03_formal_selection.csv`

| 模型 | 被选次数 | 占比 | 平均名次 | 选择分数中位数 |
|---|---:|---:|---:|---:|
| causal_forest | 105 | 0.525 | 1.710 | 0.0605 |
| s_learner | 71 | 0.355 | 1.855 | 0.0490 |
| dr_learner | 12 | 0.060 | 3.385 | 0.0164 |
| constant | 7 | 0.035 | 4.505 | −0.0183 |
| t_learner | 5 | 0.025 | 3.545 | 0.0140 |

诊断阶段（20 rep、n=20 000）是 constant 9/20、CF 4/20；正式规模下 constant 只赢 7/200。
**规模改变选模频率**，把诊断频率当正式结论会直接错。

## 3. 模型校准

`outputs/tables/v3_phase_D03_formal_calibration.csv`。相对偏差的分母是**同一 rep 的
`mean(tau_true)`**；`max_abs_relative_bias` 是 200 个 rep 里最差的那一个，不是均值。

### 3.1 全部 200 rep（每模型都评估）

| 模型 | 均值偏差（元/人） | SE | 相对偏差中位数 | 最差绝对相对偏差 | 校准斜率中位数 | Pearson 中位数 | RMSE 中位数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| constant | −0.0043 | 0.0044 | −0.0189 | 0.7022 | — | — | 6.178 |
| t_learner | −0.0010 | 0.0046 | −0.0054 | 0.8034 | 0.1141 | 0.0426 | 6.496 |
| s_learner | +0.0022 | 0.0044 | −0.0119 | 0.8456 | 0.4666 | 0.0778 | 6.184 |
| causal_forest | −0.0002 | 0.0045 | −0.0111 | 0.8014 | 0.7541 | 0.1029 | 6.149 |
| dr_learner | −0.0008 | 0.0047 | −0.0109 | 0.8167 | 0.0976 | 0.0392 | 6.561 |

### 3.2 仅被选中时（chosen_only）

| 模型 | n | 均值偏差 | SE | 相对偏差中位数 | 最差绝对相对偏差 | 斜率中位数 |
|---|---:|---:|---:|---:|---:|---:|
| constant | 7 | −0.0170 | 0.0303 | +0.0526 | 0.5178 | — |
| t_learner | 5 | −0.0205 | 0.0244 | −0.0539 | 0.2799 | 0.1215 |
| s_learner | 71 | +0.0101 | 0.0080 | +0.0146 | 0.8456 | 0.4509 |
| causal_forest | 105 | −0.0060 | 0.0060 | −0.0325 | 0.5953 | 0.7621 |
| dr_learner | 12 | −0.0067 | 0.0174 | −0.0699 | 0.3359 | 0.1008 |

读法：`causal_forest` 被选中时斜率中位数 0.762，是五个模型里最接近 1 的；
但"最差 rep"仍可到 0.595 的绝对相对偏差。**不要只报中位数。**

## 4. 真值策略价值（0.20 元/人档）

`outputs/tables/v3_phase_D03_formal_policy_value.csv`（200 rep 的均值，元/人；
`no_coupon` 恒为 0）。

| 模型 | random | business_rule | greedy | local_swap | predicted_profit_rank | all_coupon（无预算参考） |
|---|---:|---:|---:|---:|---:|---:|
| causal_forest | 0.0680 | 0.2718 | **0.2934** | 0.2934 | 0.0934 | 0.2841 |
| s_learner | 0.0680 | 0.2718 | 0.2796 | 0.2796 | 0.0934 | 0.2841 |
| dr_learner | 0.0680 | 0.2718 | 0.2256 | 0.2256 | 0.0934 | 0.2841 |
| t_learner | 0.0680 | 0.2718 | 0.2129 | 0.2129 | 0.0934 | 0.2841 |
| constant | 0.0680 | 0.2718 | 0.0767 | 0.0767 | 0.0934 | 0.2841 |

- `business_rule`、`random`、`predicted_profit_rank`、`all_coupon` 不依赖 CATE 模型，
  所以跨模型同值；`greedy`/`local_swap` 依赖模型。
- 0.20 档 `all_coupon`（0.2841）低于 `causal_forest` 的贪心（0.2934）：定向避开了
  负效应用户，而无预算参考给所有人发券会包含负值。
- `purchase_propensity_rank` 在 0.20 档为 −0.0005（低于不发券），与诊断一致：
  **propensity 不是 uplift。**

## 5. 配对差（同一 rep、同一批用户）

基线 = `business_rule_new_user_then_cart`；`outputs/tables/v3_phase_D03_formal_paired_diff.csv`。
`wins/losses` 是 200 个 rep 中该策略优于/劣于基线的次数。

### 5.1 0.20 元/人档，贪心 − 业务规则

| 模型 | 差值（元/人） | SE | 胜/负（rep） |
|---|---:|---:|---:|
| causal_forest | +0.0216 | 0.0011 | 183 / 17 |
| s_learner | +0.0079 | 0.0011 | 146 / 54 |
| dr_learner | −0.0462 | 0.0011 | 0 / 200 |
| t_learner | −0.0588 | 0.0011 | 0 / 200 |
| constant | −0.1951 | 0.0013 | 0 / 200 |

### 5.2 跨预算档的符号

贪心 − 业务规则（元/人）：

| 模型 | 0.04 | 0.10 | 0.20 | 0.30 | 0.40 | 0.60 | 0.80 | 1.00 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| causal_forest | +0.0007 | −0.0111 | +0.0216 | +0.0381 | +0.0351 | +0.0335 | +0.1131 | +0.1138 |
| s_learner | −0.0129 | −0.0245 | +0.0079 | +0.0228 | +0.0176 | +0.0115 | +0.0910 | +0.0918 |
| dr_learner | −0.0388 | −0.0699 | −0.0462 | −0.0335 | −0.0380 | −0.0398 | +0.0398 | +0.0406 |
| t_learner | −0.0378 | −0.0747 | −0.0588 | −0.0482 | −0.0532 | −0.0542 | +0.0254 | +0.0261 |
| constant | −0.0892 | −0.1687 | −0.1951 | −0.1944 | −0.1838 | −0.1118 | +0.0033 | 0.0000 |

**结论只能按模型说**：`causal_forest` 在 0.30 以上稳定胜出；`s_learner` 在 0.20 以上胜出；
`dr_learner`/`t_learner` 直到 0.80 才转正；`constant` 只有 0.80 以上不输。
这正是 AGENTS §12.6 要求"按模型配对"的原因：只评"被选中模型"会被选模频率带偏。

## 6. 事后最优与选模后悔

`outputs/tables/v3_phase_D03_formal_oracle.csv`（每模型 × 预算 × 策略的 rep 均值）：

| 模型 | 平均后悔（元/人） | SE | 0.20 档 share_optimal |
|---|---:|---:|---:|
| causal_forest | 0.1143 | 0.0009 | 0.212 |
| s_learner | 0.1066 | 0.0009 | 0.192 |
| t_learner | 0.1047 | 0.0009 | 0.125 |
| dr_learner | 0.1037 | 0.0009 | 0.125 |
| constant | 0.1317 | 0.0009 | 0.125 |

"选模后悔"（同一 rep，选中模型的贪心价值 − 5 个模型事后最优）：
0.04 档 −0.0114（SE 0.0014）、0.10 −0.0162（0.0023）、0.20 −0.0193（0.0030）、
0.40 −0.0205（0.0031）、0.80 −0.0188（0.0022），n=200。

这是**事后上界**：真实部署不可能知道哪个模型最好。它说明的只是"冻结选模规则离事后
最优有多远"，不能反过来指导选模。

## 7. 双口径预算合规

`outputs/tables/v3_phase_D03_formal_compliance.csv`，`greedy_incremental_profit_per_cost`。
`share_within_budget_by_hat` 按预测成本判定，`share_within_budget_by_true` 按真值成本判定；
数值是 200 个 rep 的均值（0–1）。

| 模型 | 口径 | 0.04 | 0.10 | 0.20 | 0.30 | 0.40 | 0.60 | 0.80 | 1.00 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| causal_forest | hat | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| causal_forest | true | 0.000 | 0.005 | 0.110 | 0.290 | 0.490 | 1.000 | 1.000 | 1.000 |
| s_learner | true | 0.045 | 0.050 | 0.130 | 0.230 | 0.415 | 1.000 | 1.000 | 1.000 |
| dr_learner | true | 0.200 | 0.200 | 0.265 | 0.430 | 0.640 | 1.000 | 1.000 | 1.000 |
| t_learner | true | 0.185 | 0.250 | 0.390 | 0.570 | 0.700 | 1.000 | 1.000 | 1.000 |
| constant | true | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.345 | 1.000 |

greedy 的 5 模型 × 8 档 = **40/40 格**在 `hat` 口径下都是 1.000；差异全部来自
"预测成本 ≠ 实际核销成本"。
0.80 以上真值成本也基本用不完预算，所以合规率自然到 1。
**正文只能写"期望预算合规"，不能写"实际支出不超预算"。**

## 8. 局限与结论失效条件

- 合成数据、已知 DGP；只跑了 `L1_main`（L0/L2/L3 未进入本表），结论不能外推到其他层。
- `time_mode=static`；时间成熟机制变化会改变订单与退款分布。
- 策略比较的预算档是**每用户期望成本**，实际支出可超；第 7 节已给出逐格合规率。
- `all_coupon_unconstrained_reference` 不参与事后最优（无预算约束），不能当"更优策略"。
- 每个 rep 只有一个 test split；rep 之间的用户批不同，配对只发生在同一 rep 内。
- `causal_forest` 的个体校准斜率仍显著小于 1；即使它在 0.20 档胜出，也不能说
  "CATE 已校准"。
- 选模规则是 A 阶段冻结的，不允许在看到正式结果后改成"固定 causal_forest"或
  "事后最优模型"。
- **D03 是否通过由独立评审判定**；本文件不写"通过"。

## 9. 产物与复现

| 件 | 路径 |
|---|---|
| 合并后逐 rep 表 | `outputs/tables/v3_phase_D03_formal_per_rep.csv`（1 000 行） |
| 策略网格 | `outputs/tables/v3_phase_D03_formal_policy_grid.csv`（72 000 行） |
| 报告表 | `selection / calibration / policy_value / paired_diff / paired_diff_chosen / oracle / compliance` 七张 CSV |
| 合并元数据 | `outputs/tables/v3_phase_D03_formal_summary.json`、`v3_phase_D03_formal_report_meta.json` |
| 证据包 | `outputs/evidence/d03_formal/`（`coverage.json` 10 文件） |

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
# 合并四分片（只读逐 rep 产物）
.\.venv\Scripts\python.exe scripts\25_merge_d03_formal.py `
  --shard-root out/d03_formal/shard0 --shard-root out/d03_formal/shard1 `
  --shard-root out/d03_formal/shard2 --shard-root out/d03_formal/shard3 `
  --expected-reps 200
# 报告表（依赖合并表）
.\.venv\Scripts\python.exe scripts\26_d03_formal_tables.py
# 证据导出（manifest/快照绑定/run.log）
.\.venv\Scripts\python.exe scripts\27_export_d03_evidence.py --out-dir outputs/evidence/d03_formal
```

## 10. 评审要点

1. 复算选模频率（105/71/12/7/5）与 `chosen_model_counts` 是否一致；
2. 用 `per_rep.csv` 复算校准斜率中位数与**最差绝对相对偏差**，分母必须是同 rep 的 `mean(tau_true)`；
3. 用 `policy_grid.csv` 复算 0.20 档按 `(rep, model, budget)` 配对的贪心 − 业务规则，
   检查 183/17 等胜负数；
4. 检查 `share_within_budget_by_hat` 是否恒为 1，且 `by_true` 与 `actual_spend_cny` 一致；
5. 检查 `oracle` 表是否排除了 `all_coupon_unconstrained_reference`；
6. 检查证据包 `coverage.json` 的 10 个文件哈希与 `outputs/evidence/d03_formal/` 实际文件一致；
7. 确认运行期间 `src/` 未改动（`snapshot_binding.json` 与四分片 run.err 为空）。
