# F02 独立三臂随机验证：设计与验收

> 合成数据 / 已知 DGP。维护时间：2026-10-27 18:24（北京时间）。
> 本文只描述机制与验收口径；**n=200 000 单 rep 与正式 200 rep 尚未运行**，文中任何
> 冒烟数字都不是证据，不得据此下策略结论。

## 0. 状态

| 项 | 状态 | 证据 |
|---|---|---|
| 三臂机制、预算、冻结/审计顺序 | 完成 | `src/causal_growth/evaluation/v3_f02.py` |
| 决策层（单侧 Holm 两比较 + 退款率护栏） | 完成 | 同上；`decision.csv / guardrail.csv / decision.json` |
| 测试 | 11 项绿 | `tests/test_v3_f02.py` |
| CLI | 完成 | `scripts/28_f02_validation.py` |
| n=2 000 冒烟（含决策层） | 完成（仅工程） | `out/f02_decision_smoke/`（不入库） |
| 全量串行测试 | 1 228 项 exit=0（18:12:54–18:20:00） | `outputs/runs/f02_tests/full_suite.log` |
| n=200 000 单 rep | **未跑** | — |
| 正式 200 rep | **未跑，需用户批准** | — |
| 独立科学评审 | **未做** | — |

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
- 测试：`tests/test_v3_f02.py`（11 项）

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

### 5.2 n=200 000 单 rep（未跑）

- [ ] 三臂各约 66 667 人，无空臂；
- [ ] 每臂预测支出 ≤ 0.2 × 臂人数 + 容差；
- [ ] 观测表行数 = 200 000 且 `user_id` 唯一；
- [ ] `freeze.json / decision.json` 先于 `audit_*` 生成，manifest 记录解锁顺序；
- [ ] `decision.csv` 恰两行、`guardrail.csv` 恰一行，α=0.05、界值=0.005 与配置一致；
- [ ] 用 `per_user.csv` 手工复算两主张的单侧 p 与 Holm 调整 p，和 `decision.csv` 一致；
- [ ] 用 `per_user.csv` 手工复算护栏的 `diff/se/上界`，和 `guardrail.csv` 一致；
- [ ] `five_tables/manifest.json` 通过且 `population_kind=validation`、split 全为 test；
- [ ] 把冻结文件与 manifest 导出到 `outputs/evidence/` 前，确认不含真值。

### 5.3 正式 200 rep（未跑，需用户批准）

- [ ] 200 个 rep 全部完成，无空臂、无缺失文件；
- [ ] 代表 rep 0 五表齐全；其他 rep 至少有名单/汇总/manifest；
- [ ] 每个 rep 内的两条主张都各自给出单侧 p、Holm 调整 p 与通过标记；聚合层报告
      每个主张的**rep 级通过率**与三条 ITT 的配对均值/SE/CI，不把 200 个 rep 的 p 值
      当作 200 份独立确证证据；
- [ ] 护栏在每个 rep 内单独判定，聚合层报告通过率与差值的 MC 分布；
- [ ] 先冻结 OPE/随机验证结果，再解封审计；审计数字不反流选模/选策略。

## 6. 已知局限

- 仍是合成数据与已知 DGP，结论不能外推到真实业务；
- ITT 区间用正态近似；样本量足够大，但极端重尾下应改用 bootstrap 复核；
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

# n=200 000 单 rep（D03 正式 R 结束后执行）
python scripts/28_f02_validation.py --scenario L1_main --n 200000 --rep 0 `
  --policy greedy_incremental_profit_per_cost `
  --out-dir out/f02_n200k_rep0 --status engineering
# 产物含 per_user/arm_summary/itt_contrasts/decision/guardrail/decision.json/freeze.json
# 与 audit_*；代表 rep 0 另有 five_tables/。

# 正式 200 rep 必须带用户批准的登记号
python scripts/28_f02_validation.py --scenario L1_main --n 200000 --rep 0 `
  --policy greedy_incremental_profit_per_cost `
  --out-dir out/f02_formal/rep0 --status formal --formal-approval "<登记号>"
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
