# F02 正式 200 rep：独立三臂随机验证

> **草稿（2026-10-28 11:00 起稿）。** 200 rep 正式运行仍在进行（10:57 时 114/200，投影 ~15:55 集齐）。
> 本文 §1 的"正式结果"行与 §4 全部数字**尚未填写**，以 `（待填：…）` 标注；合并完成后用同一套脚本重算并替换。
> **草稿不得被引用为结果**；此前 114 rep 的预演数字只在 `TODO.md` 与反思日志中作为诊断，不进本文。

## 1. 状态

| 项 | 状态 | 证据 |
|---|---|---|
| 独立验证模块 | 完成 | `src/causal_growth/evaluation/v3_f02.py` |
| CLI | 完成 | `scripts/29_f02_formal.py` |
| 合并与证据导出 | 完成（待本次运行检验） | `scripts/30_merge_f02_formal.py`、`out/scratch/f02_finalize.sh` |
| 测试 | （待填：合并后全量串行复跑的条数与 exitcode） | `outputs/evidence/test_runs/` |
| 正式 R=200（四片 × 50） | 进行中 | `out/f02_formal/shard{0,1,2,3}/` |
| 代表 rep 五表 + SQL | 完成（rep 0） | `out/f02_formal/shard0/rep0/five_tables/manifest.json` |
| 顶层证据登记 | 未做（合并后） | `outputs/evidence/coverage.json` |
| 独立科学评审 | 未做 | — |

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

（待填：合并 200 rep 后由 `scripts/32_aggregate_f02_formal.py` 生成；
必须**按 `selected_model` 分层**、每个聚合列带分母，并单列 `constant` 层的零通过现象。）

### 4.1 决策层（每 rep 两项收益主张 + 一项护栏）

（待填：各主张的通过计数/R、逐 rep 差的均值与 MC SE、Holm p 的分布、护栏通过计数/R。）

### 4.2 按 `selected_model` 分层

（待填：各模型的 R、两项主张通过计数、护栏通过计数；`constant` 层单列。）

### 4.3 全臂 ITT 与预算

（待填：三臂观测均值、差值与置信区间；预测支出/预算、真实支出/预算的分布与超支计数。）

### 4.4 代表 rep 0

（待填：rep 0 的五表/SQL 交付核对、决策层判定；**注意 rep 0 的判定不得单独支撑"定向有效"**。）

## 5. 结论边界

- 本文只对 `L1_main`、`n = 200 000`、0.2 元/人预算、冻结策略
  `greedy_incremental_profit_per_cost` 负责；不外推到其他场景、预算或券面额。
- 全部结果是**模拟**结果（合成数据、已知 DGP），不是线上部署证据；
  `recommendation_scope = candidate_for_simulated_randomized_policy_validation_not_actual_deployment`。
- 决策层的"通过"是**单 rep 内的单侧检验**；跨 rep 的合并只能以"通过比例"和
  "逐 rep 差的均值 ± MC SE"陈述，不构成对某一部署收益的点估计。
- 若 `constant` 层（单一 `tau_hat`）系统性判 null，这**不是**实验失败，
  而是"该模型没有异质性可定向"的机制性结果；必须与其余模型分层陈述，不得合并掩盖。

## 6. 局限与失效条件

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

- [ ] 200 个 rep 的 `manifest.status` 全为 `formal`、`failures` 为空
- [ ] 跨分片 `config_hash` / `source_hashes` / `formal_approval` / `policy` / `n_per_rep` 一致
- [ ] 每 rep `truth_columns_present = false`（冻结先于审计）
- [ ] 每 rep `decision.csv` 两项主张的 `passes_*` 与 `holm p ≤ alpha` 一致
- [ ] 每 rep 三臂 `n_assigned` 合计 = 200 000
- [ ] 两活跃臂 `predicted_spend_per_assigned_cny ≤ 0.2 + 容差`
- [ ] 按 `selected_model` 分层计数之和 = 200
- [ ] 代表 rep 0 的五表 manifest sha256 与文件一致
- [ ] 顶层证据登记完成、四向核对 0 不符
- [ ] 全量串行测试（单进程、日志 + exitcode + 起止时间）入库

## 9. 变更记录

| 时间（北京时间） | 变更 |
|---|---|
| 2026-10-28 11:00 | 起稿：协议、绑定、检查单；§1 与 §4 留占位 |
| 2026-10-28 11:22 | 聚合入口提为 `scripts/32_aggregate_f02_formal.py`（11 个反例夹具见 `tests/test_v32_aggregate_f02_formal.py`）；缺 rep 默认失败 |
