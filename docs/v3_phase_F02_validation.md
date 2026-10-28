# F02 独立三臂随机验证：设计与验收

> 合成数据 / 已知 DGP。维护时间：2026-10-27 18:42；状态表 20:36 更新（北京时间）。
> 本文描述机制与验收口径；n=200 000 单 rep 已于 18:32–18:39 跑通（工程状态），
> **正式 200 rep 已于 2026-10-28 16:37 完成**（结果见 §5.3 与 `docs/v3_phase_F02_formal.md`）。
> 单 rep 与冒烟数字不是证据，不得据此下策略结论。

## 0. 状态

| 项 | 状态 | 证据 |
|---|---|---|
| 三臂机制、预算、冻结/审计顺序 | 完成 | `src/causal_growth/evaluation/v3_f02.py` |
| 决策层（单侧 Holm 两比较 + 退款率护栏） | 完成 | 同上；`decision.csv / guardrail.csv / decision.json` |
| 测试 | 11 项（决策层）+ 8 项（正式编排）= 19 项绿 | `tests/test_v3_f02.py`、`tests/test_v3_f02_formal.py` |
| CLI | 完成 | `scripts/28_f02_validation.py`、`scripts/29_f02_formal.py`、`scripts/30_merge_f02_formal.py` |
| n=2 000 冒烟（含决策层） | 完成（仅工程） | `out/f02_decision_smoke/`（不入库） |
| 全量串行测试 | 1 228 项 exit=0（18:12:54–18:20:00）；F01 改动后 1 248 项 exit=0（20:20:35–20:28:04，单进程） | `outputs/runs/f02_tests/full_suite.log`、`outputs/runs/f01_tests/full_suite.log` |
| n=200 000 单 rep（工程状态） | 完成，18:32:41–18:39:21，exit=0 | `outputs/evidence/f02_n200k_rep0/` |
| 正式 200 rep | 已完成（2026-10-28 03:39 起跑、16:37 合并，四片各 50、exit 0；登记号 `F02-FORMAL-20261028-R200`） | `out/f02_formal/shard{0,1,2,3}/`；`docs/v3_phase_F02_formal.md` |
| 正式前置：源码冻结 | 评审驱动的改动全部落地并复跑后，才可建快照；`source_hashes` 逐 rep 绑定，`--resume` 拒绝漂移 | `v3_f02_formal.py::plan_formal_shard` |
| 独立科学评审 | **已做**：19:17 初审与 21:43 收尾复核均判 PASS WITH CONDITIONS，21:55 第三次窄口径复核只核 C1–C6 | `docs/reviews/v3_phase_F02_review.md`、`…_closeout.md`、`…_c1c6_recheck.md` |

## 1. 回答的问题

D03 在历史数据上按冻结规则选出一个模型，E 在这个模型上评估候选策略。F02 要回答：
**这个候选策略在从未参与训练的新用户上，是否比不发券、以及比同预算随机发券创造更多
净贡献利润？**

估计量是三条全臂 ITT 对照（分母 = 被分配到该臂的全部用户，不是支付/核销用户）：

- `selected_targeted_policy − no_coupon`：定向策略的净增量；
- `selected_targeted_policy − random_same_budget`：定向相对同预算随机的净增量；
- `random_same_budget − no_coupon`：随机发券相对不发券的净增量。

### 1.1 决策层：两条分开陈述的主张 + 退款率护栏

三条 ITT 是对照描述；**确证性判定**另按冻结配置分两层：

- `coupon_worth_issuing` = 定向 − 不发券，单侧 H0: 差 ≤ 0；
- `targeting_better_than_random` = 定向 − 同预算随机，单侧 H0: 差 ≤ 0；
- 两者构成预声明 Holm 家族（`evaluation.decision.benefit_evidence`，单侧 α=0.05），
  step-down 后各报 `passes_adjusted_test`；下界按同一 step-down 阈值反演，
  **不用未调整 95% CI 冒充族内证据**；
- 护栏：`any_refund_30d_per_assigned_user`（定向 − 不发券），界值 0.005、
  单侧 α=0.05、非合并方差 Wald 上界（`design/guardrail.py`）；"差异不显著"不算通过。

配置键名写的是 `holm_step_down_on_paired_one_sided_tests`，那是 F01 同用户配对的口径；
F02 三臂是**用户级独立随机**，两条差各用 `sqrt(se_l²+se_r²)`，不是配对差；Holm
过程本身不依赖配对。

## 2. 设计（来自冻结配置）

配置来源：`configs/v3/evaluation.yaml` 的 `evaluation.independent_validation`。

- 每个 rep **另生成 200 000 名新用户**（`n_users_per_rep`），与历史用户 `user_id` 不相交，
  时间口径与历史 test 场景相同；
- 三臂 `no_coupon / random_same_budget / selected_targeted_policy`，概率各 1/3；
- 预算口径 `same_per_assigned_user_in_each_active_arm`，**每个活跃臂 = 0.2 元 × 该臂分配人数**；
  对照臂不发券；
- 定向臂在臂内按 E 冻结的策略规则选人；随机臂在臂内按同预算随机装填；
- `policy_selection_stage: validation_before_test`：候选策略必须在进入独立验证前冻结。
  当前注册主策略是 `greedy_incremental_profit_per_cost`（`docs/v3_phase_E_interface.md` §3），
  CLI 默认值即它；正式运行必须由 E 的冻结结论传入，**不得看过 F02 结果后换策略**；
- `must_execute_five_tables_and_sql_every_rep: true`：每个 rep 都走五表 + 脏数据 + 去重 +
  SQL，观测表至少包含全部分配用户；
- 代表 rep（`validation.representative_rep = 0`）额外保存完整五表、SQL 产物与 manifest。

### 2.1 全队列审计名单是另一个估计量

除交付名单外，实现还冻结两张**全队列交付**名单（0.2 元 × 全部新用户），只用于冻结后的
真值审计，回答"策略部署到全部目标用户"的价值。它们不参与交付、不参与选择，也不得反流
到任何模型或策略决策。交付 ITT 与全队列审计价值回答的不是同一个问题，报告时必须分开写。

## 3. 冻结与审计顺序

`run_f02_rep` 的顺序是硬编码的：

1. `_d03_rep_artifacts`：在历史训练切分上重拟合 D03 选中模型（`seed_index=rep_id`）；
2. `score_validation_users`：只产出选人列 `tau_hat/cost_hat/...`，不读真值；
3. `build_validation_assignment`：冻结三臂标签、臂内发券名单、全队列审计名单；
4. 生成新用户事实订单 → 五表 → 脏数据 → 去重 → SQL → `ObservedDataset`；
5. 全臂 `arm_summary`（含退款率）/ `itt_contrasts` / `decision_summary` / `guardrail_summary`
   → 逐用户 `per_user` 与 `freeze_hash`；
6. **先把 `per_user.csv / arm_summary.csv / itt_contrasts.csv / decision.csv /
   guardrail.csv / decision.json / freeze.json` 写盘**；
7. **之后**才调用 `audit_realized_worlds` 读真值，写 `audit_truth.csv /
   audit_policy_values.csv / audit_arm_contrasts.csv`；
8. 最后写 `manifest.json`，记录 `audit_unlock_order =
   freeze_files_written_then_audit_realized_worlds` 与各产物哈希。

真值列只出现在第 7 步之后的 `audit_*` 文件里；`per_user`、`decision` 与冻结文件没有任何
`*_true` 列（测试 `test_freeze_observed_strips_truth_and_is_value_sensitive`、
`test_run_f02_rep_end_to_end`）。

## 4. 实现与产物

- 模块：`src/causal_growth/evaluation/v3_f02.py`
- CLI：`scripts/28_f02_validation.py`
- 测试：`tests/test_v3_f02.py`（11 项）+ `tests/test_v3_f02_formal.py`（8 项，分片门槛、恢复一致性、200 rep 聚合）

单 rep 输出（`--out-dir`）：

| 文件 | 内容 |
|---|---|
| `per_user.csv` | 逐用户 `run_id,user_id,assigned_policy_arm,issued_action,selected_policy_id,observed_net_profit,observed_coupon_cost,observed_any_refund_30d` |
| `arm_summary.csv` | 三臂全分母 n、发券数、均值/SE、券成本、退款人数与退款率 |
| `itt_contrasts.csv` | 三条 ITT 对照、SE、正态 CI、双侧 p（描述性） |
| `decision.csv` | 两条确证主张：单侧 p、Holm 调整阈值/调整 p、通过标记、反演下界 |
| `guardrail.csv` | 定向−不发券的退款率非劣效：界值、单侧 α、上界、通过标记、计数 |
| `decision.json` | 决策规则回显、两主张与护栏结果、`truth_columns_present=false` |
| `freeze.json` | `freeze_hash`、`per_user_hash`、`decision_hash`、`guardrail_hash`、模型、策略、无真值声明 |
| `audit_truth.csv` | 冻结后逐用户 `tau_true,cost_true`（审计专用） |
| `audit_policy_values.csv` | 全队列审计策略价值与 `n_selected` |
| `audit_arm_contrasts.csv` | 真值世界下的全臂对照 |
| `manifest.json` | 配置/预处理/名单/观测 SQL/源码哈希、预算、决策规则、解锁顺序 |
| `five_tables/` | 仅代表 rep：原始/脏/净五表、SQL 结果、质量与 lineage、manifest |

### 4.1 与配置字段的一处显式差异

配置的 `per_user_records_retained` 列了 `observed_outcome_summary`。实现用三个数值列
`observed_net_profit`、`observed_coupon_cost` 与 `observed_any_refund_30d` 代替单个摘要
字符串：信息不减少，且避免 20 万行 × 200 rep 的 JSON 重复膨胀。**这是有意的契约差异，
需评审确认**；如评审要求逐字匹配，再补一个紧凑摘要列。

`selected_policy_id` 按臂记录实际交付的策略：定向臂 = 候选策略 id，随机臂 =
`random_same_budget`，对照臂 = `no_coupon`。候选策略本身另由 `freeze_hash` 与 manifest
绑定，不会因按臂取值而丢失。

## 5. 验收清单

### 5.1 机制层（已过）

- [x] 每用户恰一个臂，对照臂发券数恒 0；
- [x] 定向/随机臂支出 ≤ 0.2 × 臂内人数（容差内），冒烟实测偏差 −0.003/−0.002 元；
- [x] 同一 rep 重跑名单逐元素一致；
- [x] 全臂分母 = n，`user_id` 唯一；
- [x] ITT 对照 = 全臂均值差，SE 为两臂独立 SE（`sqrt(se_left² + se_right²)`，正态近似）；
- [x] 冻结文件无真值列，`freeze_hash` 对观测值敏感（含退款列）；
- [x] 审计名单按 `user_id` 对齐，行序反转不改变价值；
- [x] `status="formal"` 无批准号直接拒绝；
- [x] 代表 rep 落盘完整五表与 SQL，manifest 绑定其路径与 sha256；
- [x] 决策层：两主张按预声明家族做单侧 Holm（α=0.05），调整阈值/调整 p/通过标记入表；
      未调整单侧 p=0.03/0.04 的构造数据在 Holm 下两条都不通过（`test_decision_uses_one_sided_holm_family`）；
- [x] 护栏：定向−不发券退款率、0.005 界、单侧 0.05、非合并方差上界，手工公式逐项对齐
      （`test_guardrail_matches_one_sided_noninferiority_formula`）；
- [x] `decision.csv / guardrail.csv / decision.json` 与冻结文件同批**先**落盘，
      `decision.json` 无真值列，`freeze.json` 绑定其哈希；
- [x] 全量串行 1 228 项 **exit=0**（2026-10-27 18:12:54–18:20:00，单进程、无并发写盘），
      日志 `outputs/runs/f02_tests/full_suite.log`。

### 5.2 n=200 000 单 rep（已完成，工程状态）

命令：`python scripts/28_f02_validation.py --scenario L1_main --n 200000 --rep 0
--policy greedy_incremental_profit_per_cost --out-dir out/f02_n200k_rep0 --status engineering`
（18:32:41–18:39:21，exit=0）。选中模型 `constant`，策略 `greedy_incremental_profit_per_cost`。

- [x] 三臂 66,594（定向）/ 66,713（随机）/ 66,693（对照），无空臂；
- [x] **预测**支出 13,318.53 / 13,342.56 ≤ 0.2 × 臂人数，偏差 −0.27 / −0.04 CNY；
- [x] 观测表 200,000 行、`user_id` 唯一，split 全为 test，`population_kind=validation`；
- [x] `freeze.json / decision.json` 先于 `audit_*` 生成，`audit_unlock_order=freeze_files_written_then_audit_realized_worlds`；
- [x] `decision.csv` 恰两行、`guardrail.csv` 恰一行，α=0.05、界值=0.005 与配置一致；
- [x] 用 `per_user.csv` 复算两主张单侧 p 与 Holm 调整 p、护栏 `diff/se/上界`，与落盘表逐位一致；
- [x] `five_tables/manifest.json` 五项检查全过，manifest sha256 与 `freeze.json` 一致；
- [x] 导出包不含**逐用户**真值（`audit_truth.csv` 与 15.4 MB 的 `per_user.csv` 留在
  gitignored `out/`）；`manifest.json` 保留冻结后生成的**聚合**审计真值
  `audit_true_arm_means`，仅作审计对照，不可能反向污染已落盘的冻结/决策文件。

**决策层（单 rep，仅工程核验，不是证据）**

| 主张 | 差值（CNY/人） | SE | 单侧 p | Holm α | 调整 p | 通过 | 调整下界 |
|---|---|---|---|---|---|---|---|
| `coupon_worth_issuing`（定向−不发） | +0.01850 | 0.05532 | 0.3690 | 0.05 | 0.5980 | 否 | −0.07249 |
| `targeting_better_than_random`（定向−随机） | +0.02911 | 0.05521 | 0.2990 | 0.025 | 0.5980 | 否 | −0.07910 |

两条主张点估计为正，但 SE≈0.055 远大于效应本身，单 rep 无法区分于 0；第三条
`random_same_budget − no_coupon` = −0.01061（SE 0.05491，双侧 p 0.8468）。正式结论只能来自
200 rep 的配对聚合，且需另行批准。

**护栏（单 rep）**：定向 638/66,594 = 0.9580%，对照 520/66,693 = 0.7797%，
差 +0.1784pp，SE 0.0508pp，单侧上界 0.2620pp < 0.5pp，**通过**。这是单 rep 的
机制核验，不构成正式非劣效结论。

**预算口径缺口与裁决（18:42 核对，18:46 裁决）**：预算只约束**预测**支出。实际券成本
定向臂 17,200 CNY（预测 13,318.53，+29.1%），随机臂 13,300 CNY（预测 13,342.56，−0.3%）。
按预测成本挑人会系统性低估所选人群的实际支出，"同预算"在实现层面不严格成立。

裁决：**保留预测成本口径，不改配置、不阻断正式 R**。理由：① 发券时实际成本不可知，
按实际成本约束在部署上不可实现；② 三臂共用同一规则，处理分配仍随机，ITT 对照有效；
③ 实际券成本已进入 `observed_net_profit`，超支已被结果变量吸收。正式 200 rep 必须逐
rep 报告实际支出与超支倍数，并把"同预算"限定为"同预测预算规则"，不得声称实际支出相等。

**逐 rep 支出与超支倍数（2026-10-28 21:38 重建、21:45 补分母、21:48 重登记，关闭评审 P1-1）**：预测支出其实一直逐 rep 落在 `out/f02_formal/shard*/rep*/manifest.json` 的 `arms.*.predicted_spend_*`，19:30 导出的 `v3_phase_F02_formal_per_rep_realized_spend.csv` 只是**没有再读它**，其 `predicted_note="not_persisted_per_rep"` 的表述不正确。现从 manifest + `arm_summary.csv` 重建 **600 行**（200 rep × 3 臂）全表：
`outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv`（列含 `predicted_spend_cny`、`predicted_per_assigned_cny`、`realized_coupon_cost_total_cny`、`realized_per_assigned_cny`、`realized_to_predicted`、`overspend_ratio`、`budget_cny`、`budget_deviation_cny`、`budget_note`；`budget_cny` = 0.2 × `n_assigned`，`no_coupon` 记 0.0 并注“无券预算”），已登记进目录级 `coverage.json`（20 件）与顶层（**77 条**）。

- 定向臂：**合并 = Σ实际 / Σ预测** = **1.056348**（逐 rep 超支倍数 min **−5.42%** / 中位 **+5.09%** / max **+30.67%**，**179/200** 为正）；
- 随机臂：合并 **1.002835**（min −6.14% / 中位 +0.11% / max +8.90%，104/200 为正）；
- 不发券臂：0 / 0（无预测支出）。
- **口径差 3e-6**：`docs/v3_phase_F02_formal.md` §4.3 另给的 **1.056345 / 1.002839** 是**逐 rep 比值的算术均值**，
  与本段的**总量比**（pooled）不同；两者都对，引用时必须写明是哪一种，不得并置成一个数。

结论口径与评审 §8.2 第 4 条一致："同预算"只能写成"同预测预算规则"；定向臂实际支出比其预测高约 **5.6%**（合并口径），且逐 rep 波动可达 +30.7%。旧表（`..._per_rep_realized_spend.csv`）保留为历史产物，但引用超支倍数时以本表为准。

### 5.2.1 两次独立拟合一致性（正式前置，2026-10-27 20:37，北京时间）

§6 要求"若 learner 内部随机性不完全受种子控制，需在正式 R 前用两次独立拟合哈希核验"。
2026-10-27 20:36–20:37 用两个独立进程、同一参数（`--scenario L1_main --n 20000 --rep 0
--policy greedy_incremental_profit_per_cost --status provisional`）各跑一次，
输出到 `out/f02_determinism_a` 与 `out/f02_determinism_b`（均不入库）：

- `freeze.json` **7 个字段逐位一致**：`freeze_hash`、`per_user_hash`、`decision_hash`、
  `guardrail_hash`、`selected_model`、`selected_policy`、`truth_columns_present=false`；
- `manifest.json` 只有 `representative_tables_manifest` 的路径与文件 sha256 不同（路径不同导致）；
- `five_tables/manifest.json` 的内容除 `started_at_utc / finished_at_utc` 外**完全一致**。

结论：同一 rep 的选模、名单、观测、决策与护栏在独立进程间可复现，正式分片不必担心
"隐式随机性导致 200 个 rep 不可比"。这是 **n=20 000 的工程核验**，不是科学证据。

**n=200 000 同口径双跑（2026-10-27 20:38–20:52，北京时间）**：A 于 20:44 完成、
B 于 20:44:59–20:51:59 完成，均 `--status engineering`、单 rep 0，产物
`out/f02_det200k_{a,b}/`（不入库）。比对结果：

| 对象 | 结果 |
|---|---|
| `freeze.json` 七字段 | 逐位一致；`freeze_hash` `5a101174…52cc`、`per_user_hash` `a6c100e3…2901`、`decision_hash` `368c1d89…ee42`、`guardrail_hash` `f6b1bd3c…4d45` |
| `manifest.json` | 仅 `representative_tables_manifest` 路径及其 sha256 不同（目录名 a/b 不同导致），其余字段全同 |
| `arm_summary / decision / guardrail / itt_contrasts / audit_*` 六表 | 逐字节相同 |
| `five_tables/` 27 个文件 | 26 个逐字节相同；仅 `manifest.json` 的 `started_at_utc / finished_at_utc` 不同 |

两次运行的两条主张均不通过（调整 p 均 0.5980），与单 rep 主结果一致。该双跑仍是
**工程核验**：固定单一 rep、无重复，不构成 F02 的 200 rep 证据。

### 5.3 正式 200 rep（2026-10-28 16:37 完成，200/200）

- [ ] 200 个 rep 全部完成，无空臂、无缺失文件；
- [ ] 代表 rep 0 五表齐全；其他 rep 至少有名单/汇总/manifest；
- [ ] 每个 rep 内的两条主张都各自给出单侧 p、Holm 调整 p 与通过标记；聚合层报告
      每个主张的**rep 级通过率**与三条 ITT 的配对均值/SE/CI，不把 200 个 rep 的 p 值
      当作 200 份独立确证证据；
- [ ] 护栏在每个 rep 内单独判定，聚合层报告通过率与差值的 MC 分布；
- [ ] 先冻结 OPE/随机验证结果，再解封审计；审计数字不反流选模/选策略。

### 5.4 正式 200 rep 的编排与聚合（2026-10-28 16:37 完成，200/200）

| 件 | 路径 | 职责 |
|---|---|---|
| 分片入口 | `scripts/29_f02_formal.py` | 按 `--rep-start/--rep-stop` 串行跑指定 rep，逐 rep 落盘并重写分片 `summary.json` |
| 合并入口 | `scripts/30_merge_f02_formal.py` | 合并多个分片根 → 逐 rep 表 + 聚合表 + 代表 rep 证据包 |
| 聚合层 | `src/causal_growth/evaluation/v3_f02_formal.py` | 只读逐 rep 产物，做 rep 级通过率/CP 区间/MC 标准误 |

**分片纪律**：`--status formal` 必须带用户批准的 `--formal-approval`，脚本不猜登记号；
分片只切 `rep_id`，不切 `n`、策略或模型；每完成一个 rep 重写一次 summary，进程崩溃
能定位到具体 rep；`--resume` 只在登记号、`config_hash`、`source_hashes`、`n_users`
全部一致时复用已有 rep，任一漂移抛错（防止 200 个 rep 混入不同协议）。

**合并门禁**（任何一条不过即抛错，不写"部分聚合"）：

1. 每个分片 summary 的 `phase=F02_formal_shard`、`status=formal`、`failures` 为空；
2. 分片 summary 的 `completed_rep_ids` 必须与该分片实际 `rep*/manifest.json` 目录
   逐一相等（防止"summary 说跑了 50 个、目录只有 49 个"这类证据错位）；
3. 全部 rep 目录的 `rep_id` 恰好覆盖 `0..R-1`，缺失、重复、越界都拒收；
4. `formal_approval`、`config_hash`、`source_hashes`、`n_users`、`selected_policy`
   跨 rep 唯一（运行期间改过 `src/` 或分片用了不同策略会在这里暴露）；分片 summary 的
   `config_hash` / `source_hashes_sha256` / `formal_approval` / `policy` / `n_per_rep`
   还必须与 rep 清单聚合出的同一组值一致；
5. 每个 rep 通过 `load_formal_rep` 六件套校验：`decision.csv` 恰两行且主张别名、
   左右臂人数与 `arm_summary.csv` 一致；`guardrail.csv` 恰一行且界值/α 合法；
   `itt_contrasts.csv` 恰三行；`decision.json` / `freeze.json` 均标记
   `truth_columns_present=false`；`freeze.json` 的 decision/guardrail 哈希与
   `manifest.json` 一致；
6. `manifest.json` 必须带非空 `selected_policy`，避免聚合表绑定列全空。

门禁用例：`tests/test_v3_f02_formal.py`（10 项，含策略漂移/缺策略）与
`tests/test_v3_f02_merge.py`（5 项：错误 phase/status/failures、summary 与 rep 数量
不符、summary 与 rep 配置不符、空分片、多分片一致时成功写表）。2026-10-27 21:18
实测 26 项 F02 测试全绿。

**聚合口径**：两条预声明主张各自报告 rep 级通过率与 Clopper–Pearson 95% 区间；
差值报均值与 MC 标准误（`sd/√R`）；逐 rep p 值只作描述统计（均值、中位调整 p），
**不把 200 个 p 值合并成一个"总显著"**。护栏同理单独报告通过率与差值分布。

**产物**：7 张表（per-rep claims/guardrail/itt + 聚合 claims/guardrail/itt/spend，
均含 `freeze_hash` 等绑定列）、`v3_phase_F02_formal_summary.json`、代表 rep 证据包。
证据包复制冻结/决策/护栏/ITT/arm_summary/manifest 与**五表 manifest**；
`per_user.csv`、`audit_truth.csv`、两个审计聚合表与 `five_tables/` **本体**被显式排除，
原因逐项写进 `coverage.json.excluded`——五表可由快照 + rep 0 重建，其 manifest 哈希
已在包内。

### 5.5 源码快照运行（AGENTS §11，2026-10-27 20:38 补充）

`scripts/29_f02_formal.py` 在导入前执行 `sys.path.insert(0, ROOT / "src")`，`ROOT` 是
**脚本自身所在仓库**。因此只把 `PYTHONPATH` 指向快照**无效**——仓库 `src` 会抢先被导入，
`pipeline_source_hashes()` 也会哈希仓库文件。正确做法是**连 `scripts/` 一起快照**，
运行快照里的分片脚本，并用绝对 `--out-root` 把产物写回主仓库：

```powershell
$snap = "$PWD\out\f02_formal_snapshot"
robocopy src     "$snap\src"     /E /XD __pycache__
robocopy sql     "$snap\sql"     /E
robocopy configs "$snap\configs" /E
robocopy scripts "$snap\scripts" /E

# 正式运行期间：主仓库与快照的 v3*.py / v3*.sql / v3*.yaml 只读
python "$snap\scripts\29_f02_formal.py" --scenario L1_main --n 200000 `
  --rep-start 0 --rep-stop 49 --policy greedy_incremental_profit_per_cost `
  --out-root "$PWD\out\f02_formal\shard0" --status formal --formal-approval "<登记号>"
```

- 快照内 `pipeline_source_hashes()` 的 root 解析为快照根，每个 rep manifest 绑定的是
  **快照文件**哈希；`load_v3_protocol()` 也从快照 `configs/v3` 读七个冻结文件；
- 快照建立后写 `snapshot_binding.json`（`git rev-parse HEAD`、各文件 sha256、建立时间），
  与证据包同批导出；
- 合并脚本仍用主仓库的 `scripts/30_merge_f02_formal.py`（只读逐 rep 产物，不再生成新哈希）；
- 快照必须在**所有评审驱动的源码修改落地、测试复跑之后**建立；否则 `--resume` 会因
  `source_hashes` 漂移拒绝复用，或更糟——200 个 rep 绑定到不同源码。

- **快照机制已验证（2026-10-27 20:48，北京时间）**：把 `src/sql/configs/scripts` 复制到
  `out/snap_test/`，用快照内脚本以 `--status engineering`、n=2 000、rep 0 跑通；
  manifest 的 `source_hashes` 共 48 个文件，与主仓库 `pipeline_source_hashes()` 逐项相同
  （字典 sha256 `0605947…71bd`），`representative_tables_manifest` 等路径均指向快照内文件，
  证明确实由快照导入。**相对 `--out-root` 会解析到快照根**（本次落到
  `out/snap_test/out/snap_test_run/`），因此正式运行必须用绝对 `--out-root`。
  该次冒烟产物不作为证据。

**状态**：工具已在 n=2 000、2 rep 上用假登记号冒烟（冒烟产物已删除，不构成证据）；
快照机制已在 n=2 000、1 rep 验证；8 项聚合/分片测试绿；**正式 200 rep 已于 2026-10-28 16:37 完成**
（登记号 `F02-FORMAL-20261028-R200`，四片各 50、合并 exit 0，见 `docs/v3_phase_F02_formal.md`）；
阶段状态已由 2026-10-28 22:04 的第四次窄口径确认（`docs/reviews/v3_phase_F02_final_confirm.md`）改判"通过"，
含义仅"记录准确、断言范围正确"，不表示"定向有效"。

## 6. 已知局限

- 仍是合成数据与已知 DGP，结论不能外推到真实业务；
- ITT 区间用正态近似；样本量足够大，但极端重尾下应改用 bootstrap 复核；
- 预算约束作用于**预测**支出而非实际券成本：单 rep 定向臂实际支出比预测高 29.1%，
  随机臂基本吻合（−0.3%）。正式 200 rep 合并口径为定向 **+5.63%**（逐 rep 中位 +5.09%、最大 +30.67%）、
  随机 **+0.28%**；模型成本校准在全体上无偏、在"按增量利润/成本挑选"的子集上
  有系统性低估；这是期望成本预算的固有局限，不能承诺实际支出等于预算；
- 单 rep 的 p 值与护栏判定只用于核验机制，不能当作 1/200 的"证据"或提前预判正式结论；
- 一个 rep 只验证一个预算档（0.2 元/人）；其他预算只做历史 OPE 与真值审计；
- 定向臂只验证 E 冻结的单一策略，不验证策略选择过程本身；
- 全队列审计价值使用真值世界，不能当作可部署的决策依据；
- 护栏是**单一界值**的非劣效检验：若正式验证未通过，不得改界值、换指标或改看"差异不显著"；
  按 D.1 §2.8 把它记作设计层结论（界值已被 DGP 的处理效应用掉大部分）；
- 决策层是每个 rep 内独立的 Holm 家族；跨 rep 的"多数通过"不是同一假设的重复检验，
  报告时必须给配对差与通过率，不能把 200 个 p 值合并成一个"总显著"；
- 逐 rep 重新拟合模型假设确定性；若 learner 内部随机性不完全受种子控制，
  需在正式 R 前用两次独立拟合哈希核验。

## 7. 运行命令

```powershell
# 工程冒烟（不构成证据）
python scripts/28_f02_validation.py --scenario L1_main --n 2000 --rep 0 `
  --policy greedy_incremental_profit_per_cost --models constant `
  --out-dir out/f02_smoke --status provisional

# n=200 000 单 rep（已于 2026-10-27 18:32–18:39 执行，工程状态）
python scripts/28_f02_validation.py --scenario L1_main --n 200000 --rep 0 `
  --policy greedy_incremental_profit_per_cost `
  --out-dir out/f02_n200k_rep0 --status engineering
# 产物含 per_user/arm_summary/itt_contrasts/decision/guardrail/decision.json/freeze.json
# 与 audit_*；代表 rep 0 另有 five_tables/。

# 正式 200 rep 必须带用户批准的登记号
python scripts/28_f02_validation.py --scenario L1_main --n 200000 --rep 0 `
  --policy greedy_incremental_profit_per_cost `
  --out-dir out/f02_formal/rep0 --status formal --formal-approval "<登记号>"

# 正式 200 rep 分片（4 个独立进程，各写各的根；运行期间源码只读）
python scripts/29_f02_formal.py --scenario L1_main --n 200000 `
  --rep-start 0 --rep-stop 49 --out-root out/f02_formal/shard0 `
  --status formal --formal-approval "<登记号>"
# shard1: 50-99；shard2: 100-149；shard3: 150-199（同参数，仅换区间与 out-root）

# 合并 + 证据导出
python scripts/30_merge_f02_formal.py `
  --shard-root out/f02_formal/shard0 --shard-root out/f02_formal/shard1 `
  --shard-root out/f02_formal/shard2 --shard-root out/f02_formal/shard3 `
  --expected-reps 200 --evidence-dir outputs/evidence/f02_formal_rep0
```

## 8. 评审要点

1. 先看 `freeze.json` 与 `manifest.json` 的 `audit_unlock_order`，再看 `audit_*` 是否只含
   冻结后信息；
2. 用 `per_user.csv` 重算三臂均值与 ITT，必须与 `itt_contrasts.csv` 一致；
3. 检查定向/随机臂的 `issued_action` 是否只出现在对应臂，且支出不超过臂预算；
4. 检查 `selected_policy_id` 是否按臂取值，候选策略是否与 E 的冻结结论一致；
5. 检查 `audit_policy_values.csv` 的 `n_selected` 与全队列名单规模，不把全队列审计价值
   当成三臂 ITT；
6. 用 `per_user.csv` 复算 `decision.csv` 的单侧 p、Holm 调整 p 与 `guardrail.csv` 的
   `diff/se/上界`，并确认 `decision.json` 在 `audit_*` 之前落盘；
7. 检查代表 rep 五表 manifest 的 `population_kind`、split 与源码哈希。
