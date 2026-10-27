# D03 正式 R：200 rep × n=200 000（L1_main）

> 合成数据 / 已知 DGP。**状态：正式 R 运行期间起草（2026-10-27 14:15，北京时间）；
> 数字待合并后填入，D03 在独立评审通过前仍标"未证实"。**

本文件回答 GOAL D03 的三件事：五类估计器的方法对照是否成立、选模在 rep 间是否稳定、
策略层的比较是否按同一 rep/同一批用户/同一预算配对。所有数字必须能从
`outputs/tables/v3_phase_D03_formal_*.csv` 复算；运行证据在
`outputs/evidence/d03_formal/`。

## 0. 一句话结论

`<待填：正式 R 完成、独立评审通过后写；在此之前不写结论>`

## 1. 运行事实

| 项 | 值 |
|---|---|
| 设计 | 200 rep × n=200 000（test 60 000）× 5 模型 × 8 预算 × 9 策略 |
| 场景 | L1_main，`time_mode=static` |
| 选模规则（冻结） | `validation_crossfit_dr_policy_value_lower_confidence_bound` |
| 快照 | `out/d03_formal_snapshot/`，combined sha256 `be0d48f4…`，83 文件 |
| 启动 | 2026-10-27 12:54（北京时间），4 个独立进程，每分片 50 rep |
| 完成 | `<待填：最后 rep 时间 + 墙钟>` |
| 证据 | `outputs/evidence/d03_formal/coverage.json`；合并 summary 见 `v3_phase_D03_formal_summary.json` |

复现顺序：`scripts/25_merge_d03_formal.py` → `scripts/26_d03_formal_tables.py` →
`scripts/27_export_d03_evidence.py`。25 在写盘前校验 rep 覆盖/去重、网格形状、
chosen 覆盖与合规标记；27 在校验 rep 并集、四分片 `config_hash`、`run.err` 全空、
合并表哈希后才写 coverage。

## 2. 选模频率

来源：`v3_phase_D03_formal_selection.csv`（分母 = 200 rep）。

`<待填：表格 + 解读。重点不是"谁赢"，而是冻结规则在 200 rep 上的切换频率与
平均排名；若某模型占绝对多数，后续策略结论必须按模型配对呈现，不能只报 chosen。>`

## 3. 偏差与校准

来源：`v3_phase_D03_formal_calibration.csv`（`scope=all_models` 与 `chosen_only` 两段）。

`<待填：ATE 偏差均值 ± SE、相对偏差中位数、校准斜率中位数、Pearson r、RMSE。
必须同时给 all 与 chosen：chosen_only 是线上口径，不能替代方法对照。>`

## 4. 策略层：按模型配对

来源：`v3_phase_D03_formal_policy_value.csv`、`_paired_diff.csv`、
`_paired_diff_chosen.csv`、`_oracle.csv`。

口径（AGENTS §12.6）：

1. 每条配对差都在同一 `(rep_id, model, per_user_budget_cny)` 内计算策略 − baseline，
   baseline = `business_rule_new_user_then_cart`；
2. 跨 rep 聚合只出现在配对差之上，同时给 `n_pairs`、SE、胜/负/平；
3. `chosen_only` 只作线上口径子集；任何"策略 A 优于 B"的表述必须说明模型构成。

`<待填：greedy vs business 在 5 个模型 × 8 预算上的配对差表；重点检查
"聚合结论是否被选模频率驱动"——用 all_models 的配对差与 chosen_only 对照，
若两者符号不同，必须如实报告。>`

事后上界（`_oracle.csv`）只用于解释选模/策略损失，**不可当线上可得收益**。

## 5. 双口径预算合规

来源：`v3_phase_D03_formal_compliance.csv`。

`<待填：within_budget_by_hat 与 within_budget_by_true 分别在 5 模型 × 8 预算上
的合规率、实际支出/预算的均值与最大值。greedy 在低预算档的按真实成本超支必须
单列，不能用心口径合规率掩盖。>`

## 6. 判定门槛与检查项

正式 R 结束时必须逐条全绿，才能进入独立评审：

- [ ] 200 rep 恰好各出现一次（rep 0..199，无缺无重）；
- [ ] 每 rep 5 模型，per-rep 表 1 000 行；
- [ ] 网格 200 × 5 × 8 × 9 = 72 000 行，每 `(rep, model, budget)` 恰 9 策略；
- [ ] 每 rep 恰一个 chosen，且 chosen 覆盖该模型整张网格；
- [ ] 四分片 `config_hash` 一致，快照哈希与 manifest/绑定一致；
- [ ] 4 个 `run.err` 全空；
- [ ] 合并表 sha256 与 summary 一致；`outputs/evidence/d03_formal/coverage.json` 写入成功；
- [ ] 至少一项独立评审复核：方法对照、选模频率、配对网格、双口径合规。

## 7. 局限与结论失效条件

- 合成数据、单一场景（L1_main）、单一时间模式（static）；结论不外推到真实业务或
  其他 DGP 层。
- 选模规则是冻结的单一规则；换规则会改变 chosen 分布，进而改变线上口径的策略结论。
- 真值只用于评估；`tau_true/cost_true` 不参与训练、选模与种子派生。
- 策略结论以 8 档预算为限；预算档之间的最优策略可能切换，不能线性外推。
- 行为结论文本一旦与 `outputs/tables/` 中的数字不一致，以表为准并重修文档。

## 8. 产物与复现

| 产物 | 路径 |
|---|---|
| 合并逐 rep | `outputs/tables/v3_phase_D03_formal_per_rep.csv` |
| 合并网格 | `outputs/tables/v3_phase_D03_formal_policy_grid.csv` |
| 合并 summary | `outputs/tables/v3_phase_D03_formal_summary.json` |
| 报告表（7 张 + meta） | `outputs/tables/v3_phase_D03_formal_{selection,calibration,policy_value,paired_diff,paired_diff_chosen,oracle,compliance}.csv` / `_report_meta.json` |
| 运行证据 | `outputs/evidence/d03_formal/`（manifest、快照绑定、4 分片 summary/log、coverage.json） |
