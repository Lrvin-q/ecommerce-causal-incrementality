# F02 正式 200 rep：独立三臂随机验证

> **正式结果（2026-10-28 16:37 合并完成，200/200 rep）。** 四片各 50 rep，合并 exit 0；
> 本文 §4 数字由 `scripts/32_aggregate_f02_formal.py` 在全部 200 个 rep 上重算（R=200，无 `--allow-incomplete`）。
> **阶段状态仍为“未证实”**：结果已生成、口径已自检；独立评审 19:17 判 **PASS WITH CONDITIONS**
> （`docs/reviews/v3_phase_F02_review.md`），收尾窄口径复核 21:43 再判 **PASS WITH CONDITIONS**
> （`docs/reviews/v3_phase_F02_closeout.md`，C1–C6）。条件 21:48 已落地，但**尚待窄口径确认**，
> 因此不得把本文当作已通过的验收；引用须同时引用 §6 的局限。

## 1. 状态

| 项 | 状态 | 证据 |
|---|---|---|
| 独立验证模块 | 完成 | `src/causal_growth/evaluation/v3_f02.py` |
| CLI | 完成 | `scripts/29_f02_formal.py` |
| 合并与证据导出 | 完成 | `scripts/30_merge_f02_formal.py`；合并 exit 0，`outputs/evidence/f02_formal/coverage.json` |
| 测试 | 完成：**1 275 项**，exit 0，16:42:18–16:51:00（522 s，单进程串行；日志 1 275 个进度点、0 个 F/E/s/x/X） | `outputs/evidence/test_runs/pytest_full_20261028_1642.log` |
| 正式 R=200（四片 × 50） | 完成（16:39 集齐 200/200；四片退出 0） | `out/f02_formal/shard{0,1,2,3}/` |
| 代表 rep 五表 + SQL | 完成（rep 0，26/26 产物 sha256 一致（`bytes` 未在 manifest 记录，未按 manifest 复核）） | `out/f02_formal/shard0/rep0/five_tables/manifest.json` |
| 顶层证据登记 | F02 合并时 records **48** / `total_bytes` 15 903 166；独立评审 19:17 时 54 / 15 916 738；19:30 补 7 张 aggregate + 逐 rep 支出/绑定/分片/snapshot 后 65 / 16 746 236；21:34 补 4 条聚合、21:38 新增 600 行支出表、21:48 重导出该表（补 `budget_cny`/`budget_note`）后 **77 / 16 924 056**（21:48 实读；`coverage.json` 为准） | `outputs/evidence/coverage.json` |
| 独立科学评审 | 已做：19:17 **PASS WITH CONDITIONS**（`docs/reviews/v3_phase_F02_review.md`，结果层全复现，P1-1/P1-2/P1-3 已关闭或移交）；21:43 收尾窄口径复核 **PASS WITH CONDITIONS**（`docs/reviews/v3_phase_F02_closeout.md`，C1–C6） | 两份评审文件 |

## 2. 回答的问题与口径

F01 用历史留出数据估计了冻结策略的价值，但那是**观测**估计（OPE），且只跑单 rep。
F02 回答：**冻结策略在一个从未参与训练的新用户总体上，按随机三臂试验运行一次，
其收益是否可被观测数据本身证明？**

- 每个 rep 额外生成 **200 000** 名新用户（`independent_validation.n_users_per_rep`），
  以**新用户**为随机化单位，按冻结概率分入三臂：
  `no_coupon` / `random_same_budget` / `selected_targeted_policy`（各约 1/3）。
- **分母 = 被分配到该臂的全部用户**（全臂 ITT），不是支付/核销用户。
- **预算口径**：每个活跃臂的预算 = `primary_budget_cny_per_user`（**0.2 元**）× **该臂分配人数**，
  约束的是**预测期望成本**；`budget_basis = same_per_assigned_user_in_each_active_arm`。
  随机臂在臂内按成本随机装填，定向臂按冻结策略规则选人；两臂的**真实**核销支出另报
  （真实支出不受预测上限约束，见 §6）。
- **决策层**（冻结先于审计）：
  - 主张一 `coupon_worth_issuing`：定向 − 不发券，单侧，阈值 0 元/人；
  - 主张二 `targeting_better_than_random`：定向 − 同预算随机，单侧，阈值 0 元/人；
  - 两主张组成一个 Holm step-down 家族，家族单侧 α = 0.05；置信下限由**同一 Holm 家族反演**得出，
    不用未调整的单侧区间替代；
  - 护栏：定向 − 不发券的 30 天退款率，非劣效界值 **0.5pp**、单侧 α = 0.05，
    以 `require_guardrail_noninferiority = true` 作为收益主张成立的前提。
- **冻结与审计顺序**：拟合并冻结新用户上的 `tau_hat/cost_hat` → 冻结三臂动作 →
  生成订单与五表/SQL → 写观测汇总与逐用户记录的 `freeze_hash` → **之后**才读真值账本。
  `audit_unlock_order = freeze_files_written_then_audit_realized_worlds`；
  每个 rep 的 `freeze.json` 实测 `truth_columns_present = false`。

## 3. 设计与运行绑定

| 项 | 值 |
|---|---|
| 场景 | `L1_main`（核心 Tier1） |
| rep 数 | 200（rep 0–199，四分片各 50） |
| 每 rep 新用户 | 200 000 |
| 代表 rep | **0**（唯一保留完整五表 + SQL 的 rep，`representative_five_tables = true`） |
| 选模 | 每 rep 独立选模（`selected_model` 逐 rep 不同） |
| 选策略 | 固定 `greedy_incremental_profit_per_cost` |
| 预算 | 0.2 元/人（预测期望成本）× 各臂分配人数 |
| 运行登记 | `F02-FORMAL-20261028-R200` |
| `config_hash` | `e1aa4314b8d84b04a26150cb8ccea5a35dbe9b2d514fee724c56570d5b586d75` |
| 源码绑定 | 48 个文件的 `source_hashes`（见每 rep `manifest.json`） |

## 4. 结果

来源：`scripts/32_aggregate_f02_formal.py --root out/f02_formal --expect-reps 200`
（无 `--allow-incomplete`；200 个 rep 全部通过逐 rep 绑定校验：`manifest.status=formal`、`truth_columns_present=false`、
`config_hash` 全为 `e1aa4314…`、`source_digest` 全为 `d8327ae0…`、每 rep 三臂 `n_assigned` 合计恰为 200 000）。
逐 rep 表 `out/scratch/f02_agg_200_by_rep.csv`，分层表 `out/scratch/f02_agg_200_by_model.csv`（`out/` 不入库，正式副本见 §7 的复现命令）。

**先说判定单位**：正式判定是**每个 rep 内**的单侧 Holm 检验（α=0.05，两项主张一个家族）；
下面的“通过比例 k/200”是跨 rep 的**描述性**统计，不是验收阈值。

### 4.1 决策层（每 rep 两项收益主张 + 一项护栏）

| 主张 | 通过 | 通过率（Clopper–Pearson 95%） | 逐 rep 差均值 ± MC SE（元/人） | 差均值 95% t 区间 | 逐 rep 单侧 p 均值 | Holm p 中位 / 95 分位 / 最大 | 反演置信下限最小值 |
|---|---|---|---|---|---|---|---|
| `coupon_worth_issuing`（定向 − 不发券） | 196/200 | 0.980（0.9496–0.9945） | 0.281630 ± 0.005072 | [0.271627, 0.291632] | 0.005557 | 3.62e-7 / 0.002239 / 0.598019 | −0.072489 |
| `targeting_better_than_random`（定向 − 同预算随机） | 190/200 | 0.950（0.9100–0.9758） | 0.214167 ± 0.005015 | [0.204278, 0.224056] | 0.012922 | 7.34e-5 / 0.031755 / 0.598019 | −0.088656 |
| 两项同时通过 | 190/200 | 0.950 | — | — | — | — | — |
| 护栏（退款率非劣效，界值 0.005） | 200/200 | 1.000（0.9817–1.000） | 0.001374 ± 0.000039 | 单侧上界均值 0.002197；**最大上界 0.003946 < 0.005** | — | — | — |

两项主张 + 护栏同时通过 **190/200**。未通过的 10 个 rep 里，`coupon_worth_issuing` 失败 4 个、
`targeting_better_than_random` 失败 10 个（有重叠）；最大 Holm p = 0.598019 的那一个 rep 两项都未过，
其调整后置信下限为 −0.0725 / −0.0887。**结论只能写成“多数 rep 内成立”，不能写成 200/200 全胜。**

### 4.2 按 `selected_model` 分层

| `selected_model` | R | 主张一通过 | 主张二通过 | 三项同时 | 主张一差均值（MC SE） | 主张二差均值（MC SE） | 护栏最大上界 | 真实/预测支出（定向） |
|---|---|---|---|---|---|---|---|---|
| `causal_forest` | 105 | 105/105 | 105/105 | 105/105 | 0.302109（0.005796） | 0.232561（0.005647） | 0.003353 | 1.0533 |
| `s_learner` | 71 | 71/71 | 69/71 | 69/71 | 0.282564（0.007074） | 0.215782（0.007801） | 0.003302 | 1.0501 |
| `dr_learner` | 12 | 12/12 | 12/12 | 12/12 | 0.236153（0.012931） | 0.175136（0.010230） | 0.002804 | 1.0268 |
| `t_learner` | 5 | 5/5 | 4/5 | 4/5 | 0.201725（0.026444） | 0.147861（0.041706） | 0.002630 | 0.9951 |
| `constant` | 7 | **3/7** | **0/7** | **0/7** | 0.100005（0.031121） | 0.036145（0.009617） | 0.003946 | **1.2602** |
| 合计 | **200** | 196 | 190 | 190 | — | — | — | — |

分层计数之和 = 200，与总 R 一致。`constant` 层 7 个 rep 的 targeting **0/7**、coupon **3/7**；
但其 targeting 点估计仍为 **+0.036145（MC SE 0.009617）**、coupon 为 **+0.100005（0.031121）**，
**不能据此断言零效应**（0/7 是低 power 下的决策结果，不是效应为 0 的证明）。其真实/预测支出比 **1.2602** 为五层最高，
提示该层的额外花费没有转化为可判定的 targeting 收益，而非“只是花更多钱、选不出更好的人”。
结构事实：**10 个 targeting 失败全部在非 CF 层**（constant 7、s_learner 2、t_learner 1），CF 105/105、dr_learner 12/12。
按 AGENTS §12.6，正文不得把 `constant` 与其余模型合并成“定向普遍优于随机”的单一结论。

### 4.3 全臂 ITT 与预算

三臂的人均净利润（跨 200 rep 的均值，元/被分配用户；MC SE 为 rep 间标准误）：

| 臂 | 均值 | MC SE | 说明 |
|---|---|---|---|
| `no_coupon` | 2.583457 | 0.002776 | 不发券基线 |
| `random_same_budget` | 2.650919 | 0.003012 | 同计划预算随机发券 |
| `selected_targeted_policy` | 2.865086 | 0.004052 | 冻结策略定向发券 |

跨 rep 差值（元/人，95% t 区间用 R−1）：

| 对比 | 均值 ± MC SE | 95% 区间 | 逐 rep 为正 |
|---|---|---|---|
| 随机 − 不发券 | 0.067463 ± 0.004117 | [−0.041171, 0.176097] | 169/200 |
| 定向 − 不发券 | 0.281630 ± 0.005072 | [0.171350, 0.391910] | 200/200 |
| 定向 − 随机 | 0.214167 ± 0.005015 | [0.103434, 0.324900] | 200/200 |

**预算口径**：两活跃臂的**预测**支出/被分配用户在全 200 rep 的最大值恰为 **0.200000**。
预算偏差按**总额**看，最大幅度 **−0.6779 元**（targeted rep126，n=66 456，折 −1.020e-5 元/人）；
最接近 0 的一格是 random rep110（n=**66 325**，−1.1e-5 元，折 −1.7e-10 元/人）。
两种口径都远小于 1 元，且从未超过 0.2 元/人。
**逐 rep 实际/预测支出**见 `outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv`
（600 行，三臂；`budget_cny` = 0.2 × `n_assigned`，`no_coupon` 记 0.0 并注“无券预算”，
`budget_deviation_cny` = 预测 − 预算）。评审 P1-1 已由该表关闭（21:38 重建、21:48 补分母与注记）；
旧表 `…_per_rep_realized_spend.csv` 保留为历史，其 `predicted_note` 的“未落盘”表述**是错的**，引用以新表为准。
**真实**支出（不受预测上限约束）：定向人均 **0.211268**（max 0.261322），真实/预测均值 **1.056345**
（min 0.945840，max 1.306675）；随机人均 **0.200567**（max 0.217798），比值均值 **1.002839**
（0.938633–1.088988）。定向比随机实际人均多花 **0.010701 元**，约为效应 0.214167 的 **5.0%**。
因此“同预算”只能写成**计划支出同预算**，不能写成实付等支出。
发放量：200 rep 合计随机 **3 239 534** 张、定向 **3 302 253** 张（不发券 0）；rep 0 的发放率
随机 24.61%、定向 39.21%，可作量级参考，不作为总体估计。

### 4.4 代表 rep 0

rep 0 的 `selected_model` 是 **`constant`**，因此它的决策层结果是一个**零结果**：
`coupon_worth_issuing` 差 0.018504、Holm p 0.598019、调整后下限 −0.072489，不通过；
`targeting_better_than_random` 差 0.029111、Holm p 0.598019、调整后下限 −0.079104，不通过；
护栏通过（单侧上界 0.002620 < 0.005）。三臂人数 66 693 / 66 713 / 66 594，合计 200 000。

五表与 SQL 交付核对：`five_tables/manifest.json` 的 `artifacts` 共 **26 个文件**，
逐个重算 sha256 **全部一致**（`bytes` 未在 manifest 记录，见 §1 表，**未按 bytes 复核**）；`sql/` 下 8 个 parquet（analysis/channels/cost_ledger/funnel/
groups/new_users/quality/weeks），`sql_sha256` 前缀 `4cbf8306…`；`checks.full_denominator`、
`two_windows_per_user`、`source_hashes_unchanged`、`sql_quality_passed` 均为 true。

**明确边界**：rep 0 是 `constant` 层的零结果，**不得**用它单独支撑或否证“定向有效”；
它只能证明五表/SQL 交付链与决策层在单 rep 上按契约工作。定向是否有效看 §4.1–4.2 的分层聚合。

## 5. 结论边界

**全队列审计价值的归属（评审 P1-3）**：F02 只交付全臂 ITT；全队列审计价值是另一个估计量，
移交 D01/G 阶段，理由：D01 是审计试点（三粒度含策略与审计），G 才按冻结矩阵跑正式审计；
接口为 F02 的 `freeze.json`（策略冻结）+ `per_user.csv`（全臂分配与观测）+ `audit_*.csv`（真值解封后），
由 D01/G 在相同 `run_id` 上重放策略价值。GOAL F02 行“随后审计”的落点即在此；
本阶段不得给出任何审计价值结论，也不得把 ITT 与审计混写。

- 本文只对 `L1_main`、`n = 200 000`、0.2 元/人预算、冻结策略
  `greedy_incremental_profit_per_cost` 负责；不外推到其他场景、预算或券面额。
- 全部结果是**模拟**结果（合成数据、已知 DGP），不是线上部署证据；
  `recommendation_scope = candidate_for_simulated_randomized_policy_validation_not_actual_deployment`。
- 决策层的"通过"是**单 rep 内的单侧检验**；跨 rep 的合并只能以"通过比例"和
  "逐 rep 差的均值 ± MC SE"陈述，不构成对某一部署收益的点估计。
- 若 `constant` 层（单一 `tau_hat`）系统性判 null，这**不是**实验失败，
  而是"该模型没有异质性可定向"的机制性结果；必须与其余模型分层陈述，不得合并掩盖。

## 6. 局限与失效条件
- **正态近似**：p 值与区间均为正态近似，极端重尾下应改用 bootstrap 复核（预注册记录 §6）。
- **护栏 margin**：0.005 是假设的业务容忍度，不是经验事实；最大上界 0.003946 已消耗约 79% 的 margin。
- **审计价值**：与 ITT 是不同估计量，本阶段未报告、已声明移交 D01/G（见 §5）。
- **逐 rep 预测支出**：已由 `…_per_rep_spend_full.csv`（600 行）补全，P1-1 关闭（21:48）；边界是“同预算”
  只能写成“同预测预算规则”——定向实际支出比预测高 5.6%，逐 rep 可达 +30.7%。
- **0/7 不等于零效应**：constant 层点估计仍为正，7 个 rep 不足以证明零效应。
- **`paired` 命名**：`holm_step_down_on_paired_one_sided_tests` 中的 paired 指 rep 级配对汇总，
实际标准误为两臂独立的 `sqrt(se_left²+se_right²)`，不是用户级配对 SE。
- **运行后配置漂移**：F02 以 `out/f02_formal_snapshot`（git `7870b9a`、`e1aa4314…`/`d8327ae0…`）为准；
运行后 `configs/v3/{design,execution,scenarios}.yaml` 已按 2026-10-28 11:05 用户裁决做 G AA250 补丁（12 行），
当前 live configs 不能直接复跑出同一 F02 hash，F02 结果不受影响。

1. **预测成本 ≠ 真实成本**：预算按预测期望成本封顶，定向臂追逐高核销人群，
   真实支出可以显著高于预算（E02 已记录单侧超支；F01 同一机制的水平标定偏差 +28.42%）。
   报告必须同时给"预测支出/预算"与"真实支出/预算"，不得只报前者。
2. **选模不稳定**：200 rep 的 `selected_model` 分布本身是结果的一部分；
   任何跨 rep 聚合都要检查该分布是否被第三因素改变（AGENTS §12.6）。
3. **代表 rep 只有 1 个**：五表与 SQL 的完整性只在 rep 0 上被逐文件验证；
   其余 rep 只保留逐用户名单、汇总与 manifest。
4. **真值隔离**：审计值只经 `audit_policy_values` 入口读取；
   若该顺序被破坏，本文结论作废。
5. **重训 bootstrap 200 次**属 G 阶段范围，不在本文。

## 7. 复现

```bash
# 单 rep（工程冒烟）
.venv/Scripts/python.exe scripts/29_f02_formal.py --scenario L1_main --n 200000 --reps 1 --start-rep 0
# 合并 200 rep（四个分片跑完后）
.venv/Scripts/python.exe scripts/30_merge_f02_formal.py \
  --shard-root out/f02_formal/shard0 --shard-root out/f02_formal/shard1 \
  --shard-root out/f02_formal/shard2 --shard-root out/f02_formal/shard3 \
  --expected-reps 200 --tables-dir outputs/tables --evidence-dir outputs/evidence/f02_formal
# rep 配对聚合（分层）
.venv/Scripts/python.exe scripts/32_aggregate_f02_formal.py --root out/f02_formal --expect-reps 200
```

## 8. 检查单（合并后逐项打勾）

- [x] 200 个 rep 的 `manifest.status` 全为 `formal`、`failures` 为空（200/200，实测扫描）
- [x] 跨分片 `config_hash` / `source_hashes` / `formal_approval` / `policy` / `n_per_rep` 一致（聚合器逐 rep 断言：`config_hash` 1 种、`source_digest` 1 种、预算 0.2 一种、策略一种）
- [x] 每 rep `truth_columns_present = false`（冻结先于审计；聚合器逐 rep 校验 `freeze.json`）
- [x] 每 rep `decision.csv` 两项主张的 `passes_*` 与 `holm p ≤ alpha` 一致（聚合器逐 rep 复算；rep 0 双失败即其一例）
- [x] 每 rep 三臂 `n_assigned` 合计 = 200 000（200/200，min=max=200 000）
- [x] 两活跃臂 `predicted_spend_per_assigned_cny ≤ 0.2 + 容差`（全 200 rep 最大恰为 0.200000）
- [x] 按 `selected_model` 分层计数之和 = 200（105+71+12+5+7）
- [x] 代表 rep 0 的五表 manifest sha256 与文件一致（26 个 `artifacts` 逐个重算）
- [x] 顶层证据登记完成、全表复算 0 不符（48 条；登记前逐文件重算、登记后全表复算）
- [x] 全量串行测试（单进程、日志 + exitcode + 起止时间）入库（1 275 项，exit 0，522 s）

## 9. 变更记录

| 时间（北京时间） | 变更 |
|---|---|
| 2026-10-28 11:00 | 起稿：协议、绑定、检查单；§1 与 §4 留占位 |
| 2026-10-28 11:22 | 聚合入口提为 `scripts/32_aggregate_f02_formal.py`（11 个反例夹具见 `tests/test_v32_aggregate_f02_formal.py`）；缺 rep 默认失败 |
| 2026-10-28 16:52 | 200 rep 集齐（16:39）、合并与证据导出 exit 0；填 §1 测试/登记行、§4.1–4.4、§8 检查单全部勾选。阶段状态仍为**未证实**（独立评审未做）；rep 0 为 `constant` 零结果，已在 §4.4 显式限定 |
