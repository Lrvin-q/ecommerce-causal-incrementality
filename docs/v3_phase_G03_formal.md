# G03 正式报告 —— Tier1 core 四格 + Tier2 二十格矩阵（G03 骨架）

> **合成数据 / 已知 DGP**。本报告只回答"在注册的 24 个机制场景下，策略价值与决策通过率如何"，
> 不表示任何真实业务效果。维护时间：2026-10-29 19:46（北京时间）。
> 当前状态：**阶段 A 已完成，§4 已填（24 格固定 bootstrap）**；阶段 B 拆批，Phase 1（core rep0–99）19:36 起跑中；
> Phase 2（Tier2 20 格 + core rep100–499）待用户另约时间。§3 仍待填。

## 1. 设计

| 项 | 取值 | 依据 |
|---|---|---|
| 格数 | **24 = 4 个 Tier1 core + 20 个 Tier2 选中格** | `GOAL.md` G03 行的 20 格指 Tier2 子集；core 格同批跑以对齐 Tier1 口径 |
| 重复数 | core `R_ate=500`（学习/验证 100）；Tier2 `R=30` | `configs/budget/tier2_overlay.yaml`（`02644767…`）与协议注册值 |
| 策略 | `greedy_incremental_profit_per_cost` | 与 E/F/G 主口径一致 |
| 模型 | 各层适用集合 `common ∪ additional_by_level[level]`（L0/L2 四项；L1/L3 另加 `dr_learner`），按验证选模 | `configs/v3/models.yaml`（冻结集内）；34 号未给 `--models` 时按格解析（11:14 冒烟修复） |
| 固定 bootstrap | **仅主预算 0.2 元档，1 000 次，24 格 × rep 0**（阶段 A） | 用户 2026-10-28 22:26 裁决② |
| 批准号 | `G03-FORMAL-20261029`（矩阵）／`G02-FORMAL-20261029`（固定 bootstrap） | 用户 2026-10-29 批准 |
| 快照 | `out/g03_snapshot`，49 文件，`6fdaf7bb7ee3c63ef8af7e77eea39c34157af71c7fd9e6d70bcce8ff2d3b60a3`（18:05 重建） | AGENTS §11 冻结窗口 + 哈希绑定校验 |
| 并发 | 6 workers；单跑时 `--shard-size 50`；**Phase 1 用 `--shard-size 10`**（40 片 × 10 rep，按 8.6 min/rep 均摊） | 决策单 §H.2 + 19:40 实测 |

**预算口径**：决策单 §H.2 的 159.2 CPU·h = 95.9（core）+ 63.3（Tier2）；链条两个阶段串行，
阶段 A 约 3.3 CPU·h。**阶段 B 墙钟（19:40 更正）**：11:38 记的"2 600 rep × 8 min / 6 路 ≈ 58 h"
把全部 rep 都当成完整流程，只是**上界**。实际只有 core 的 rep0–99 走学习+选模+验证
（`tier1_learning_reps/validation_reps=100`），rep100–499 只出 ATE；运行期实测
**8.6 min/rep（rep0–99）vs 1.9 min/rep（rep≥100）**，整批一次跑完约 28–35 h。
58 h 不再作为 ETA 引用（看护窗口仍留 120 h 覆盖最坏情况）。
**Phase 1 实测（19:50）**：6 路并行下活跃分片 6.3 min/rep，400 rep / 6 路 ≈ 7 h，
ETA **10-30 02:30–03:30**；Phase 2 的 Tier2 600 rep（20 格 × 30，同样走学习+验证）≈ 10.5 h、
core rep100–499（400 rep × 1.9 min/rep）≈ 2.1 h，合计 **13–15 h**。

## 2. 执行记录（待填）

| 时刻 | 事件 |
|---|---|
| 11:14 | 开跑前冒烟发现：34 号不带 `--models` 时把 `dr_learner` 也交给 L0，抛 `ModelNotApplicableError`——阶段 A/B 都会在 L0 立即失败。修 `_worker` 按层解析；L0+L1 两格 n=2000 × rep0 × 1000 次重抽 **EXIT=0**（`out/smoke_g03b.log`），41 `--check` 对半成品报缺格并 **EXIT=2**（符合预期） |
| 17:17:51 | G02 收尾 `merge_exit=0`，链条解除 14 h 等待 |
| 17:51 | **阶段 A 首跑失败**：`L1_cost_prediction_under`（成本预测乘子 0.8）按设计抛 `NotImplementedError`，23/24 格完成；旧产物归档 `out/g02_fixed_attempt1_20261029_1751`、`out/g03_snapshot_attempt1_20261029_1751` |
| 18:05–18:37 | 实现预测端乘子（真实成本不变，对数噪声仍拒绝）+ 补测试，提交 `d2d1423`；快照重建（49 文件，`6fdaf7bb…`）；重跑阶段 A **`fixed_exit=0`**（24 格 × rep0 × 1000 次，约 31 min） |
| 18:37:06 | 阶段 B 首跑启动：24 格 / 60 分片 / 6 路（`--shard-size 50`） |
| 19:36 | 按用户决定停链（`taskkill /T`），半成品归档 `out/g03_formal_interrupted_20261029_1935`；`g03_post` 停止，`chain.status` 记 paused |
| 19:36:30 | **Phase 1 启动**：core 4 格 × rep0–99，40 分片 × 10 rep、6 路，`--out-root out/g03_core_prefix`；快照校验通过（`6fdaf7bb…`） |
| 待填 | Phase 1 完成（`out/g03_logs/phase1.status` 出现 `OK: G03 Phase1 core prefix 完成`） |
| 待填 | Phase 2（Tier2 + core ATE 尾巴）与多根 merge（`g03_exit=0`） |

**续跑纪律（失败时）**：`--resume` 只救"跑到一半被杀、有 `repetitions_provisional.csv`"的分片；
已完成分片会整片重跑，且 `run_cell` 的 `existing` 只来自 `resume_from` ⇒ **重跑不是追加，会用本次 reps
覆盖 `repetitions.csv`**（旧 `rep<k>/row.json` 仍在盘上，但逐 rep 表会少行，11:42 读码确认）。
正确做法：先 `34 merge` 收已完成 → 缺口另起 `--out-root out/g03_repairN` → 多根 `merge` 且确认
`duplicates=0`。见 `AGENT_HANDOFF.md` 第 6 条、注册表 §3 与日志 2026-10-29 11:15/11:42 条。

**分批跑法（19:36 起）**：Stage B 拆成 Phase 1（core rep0–99 → `out/g03_core_prefix`）与
Phase 2（Tier2 → `out/g03_tier2`；core rep100–499 → `out/g03_core_ate`）。每批都是独立 out-root、
分片编号互不覆盖，最后多根 `merge` 合并去重；`_final` 仍按 `R_ate=500` 判完整。
这是唯一安全的断点续跑方式——**不要**在原 out-root 上 `--resume`（已完成分片会被整片重算）。

## 3. 矩阵结果（待填）

数据源：`outputs/tables/v3_g_g_core.csv`、`v3_g_g_tier2.csv`（34 号 `_finalize`），
逐 rep 原件在**多根**：Phase 1 `out/g03_core_prefix/shards/<cell>_s####/`；
Phase 2 `out/g03_tier2/shards/…` 与 `out/g03_core_ate/shards/…`。
合并用 `34_g_matrix_run.py merge <各分片根…>`，按 `[scenario_id, block, rep]` 去重
（`duplicates` 必须为 0）；`_final` 只在 24 格都覆盖 `R_ate` 时才写正式表。
导出后为 `outputs/evidence/g03_formal/per_cell/`。

待填内容：
- 24 格逐格：`ate` / `ate_test` / `ate_paid_purchase_7d` / `ate_any_refund_30d` 的均值、sd、MC SE、
  95% CI（1.96×MC SE，与 39 号同口径）；
- 4 个 core 格与 20 个 Tier2 格**分区呈现**（禁止同表并列排序）；
- 每格是否跑满注册 R、`provisional` 必须为 `False`。

**不做覆盖率（但真值文件其实在盘上）**：逐 rep 的 `freeze.json` 写 `truth_columns_present: false`，
含义是**冻结决策表（policy_list/decision/guardrail）在写盘时不含真值**，不是"真值未落盘"——
freeze 之后 `run_validation_arm` 确实写出 `truth_users.csv`（`user_id/tau_true/cost_true`）、
`truth_policy_values.csv`、`truth_arm_means.csv`、`truth_arm_contrasts.csv`。
G03 的注册分析（`repetitions.csv` 四指标 + 汇总）**没有**覆盖率的统计量与校验，
因此报告**不得**声称"95% CI 覆盖真值 X%"；若要做覆盖率，必须把它作为**新增注册分析**，
基于 `truth_*` 逐 rep 重算并单列，不得混入本轮已注册的四个指标。

## 4. 固定 bootstrap 结果（Stage A 已于 18:37 完成；19:46 填表）

数据源：`out/g02_fixed/shards/<cell>_s0000/<cell>/rep0/validation/fixed_bootstrap.csv`（24 格）；
本文数字的唯一来源是 `outputs/tables/v3_g03_fixed_bootstrap_summary.csv`（`scripts/47_g03_fixed_report.py` 生成，
逐格断言"单行 / 预算 0.2 / 重抽 1 000"，实际预算恒 0.2、`resamples` 恒 1 000）；
Stage A 完成后由 41 号导出为 `outputs/evidence/g03_formal/fixed_bootstrap.csv`。

**口径**：点差 = 定向贪心臂 − 随机同预算臂（同 rep、同批用户、同预算 0.2 元/人，按选中模型配对，AGENTS §12.6）；
CI 为 1 000 次用户级 bootstrap 的 2.5%/97.5% 分位。"CI 跨零"只表示**该 rep 内**两臂差无法与零区分，
既不是覆盖率（§6 第 5 条），也不是 30 次重复下的显著性。

### 4.1 Tier1 core（4 格）

| 格 | n_targeted | n_random | 点差 | bootstrap SE | 95% CI | CI 跨零 |
|---|---|---|---|---|---|---|
| `L0_P_main` | 66,594 | 66,713 | +0.0538 | 0.0487 | [−0.0402, +0.1458] | 是 |
| `L1_main` | 66,594 | 66,713 | +0.2022 | 0.0560 | [+0.1009, +0.3131] | 否 |
| `L2_n200000_p050` | 66,594 | 66,713 | +0.1788 | 0.0549 | [+0.0740, +0.2852] | 否 |
| `L3_fixed_lt000` | 66,594 | 66,713 | +0.0128 | 0.0552 | [−0.1000, +0.1205] | 是 |

Tier1 小计：CI 跨零 2/4（`L0_P_main`、`L3_fixed_lt000`）；点差为正 4/4；中位半宽 0.1058。
`L1_main` 与 `L2_n200000_p050` 的区间完全在 0 上方；`L0`/`L3` 跨零，含义只是"单个 rep 内两臂差不可分辨"，
不能据此说定向在该格无效（每格只有 1 个 rep，没有跨 rep 的重复证据）。

### 4.2 Tier2 选中格（20 格；不与 Tier1 并列排序）

| 格 | n_targeted | n_random | 点差 | bootstrap SE | 95% CI | CI 跨零 |
|---|---|---|---|---|---|---|
| `L0_Pi_heterogeneous_cost` | 66,594 | 66,713 | −0.1684 | 0.0479 | [−0.2664, −0.0767] | 否 |
| `L0_zero_purchase_effect` | 66,594 | 66,713 | +0.0765 | 0.0451 | [−0.0172, +0.1584] | 是 |
| `L1_cost_prediction_under` | 66,594 | 66,713 | +0.2769 | 0.0568 | [+0.1711, +0.3870] | 否 |
| `L1_heterogeneity_000` | 66,594 | 66,713 | +0.0732 | 0.0563 | [−0.0315, +0.1860] | 是 |
| `L1_heterogeneity_150` | 66,594 | 66,713 | +0.2847 | 0.0563 | [+0.1792, +0.3939] | 否 |
| `L1_mar_double` | 66,594 | 66,713 | +0.2615 | 0.0564 | [+0.1582, +0.3720] | 否 |
| `L1_misspec_omit_new_channel` | 66,594 | 66,713 | +0.1710 | 0.0560 | [+0.0676, +0.2792] | 否 |
| `L1_signal_weak` | 66,594 | 66,713 | +0.2561 | 0.0564 | [+0.1483, +0.3668] | 否 |
| `L2_composition_shift` | 66,594 | 66,713 | +0.2008 | 0.0522 | [+0.1017, +0.3019] | 否 |
| `L2_drift_smooth` | 66,594 | 66,713 | +0.1126 | 0.0538 | [+0.0108, +0.2159] | 否 |
| `L2_immature_negative_control` | 66,594 | 66,713 | +0.1788 | 0.0549 | [+0.0740, +0.2852] | 否 |
| `L2_n100000_p050` | 33,312 | 33,473 | +0.0256 | 0.0780 | [−0.1227, +0.1770] | 是 |
| `L2_n30000_p050` | 10,086 | 9,955 | +0.0122 | 0.1459 | [−0.2740, +0.3111] | 是 |
| `L3_fixed_lt025` | 66,594 | 66,713 | +0.2043 | 0.0560 | [+0.0889, +0.3128] | 否 |
| `L3_fixed_lt075` | 66,594 | 66,713 | +0.1386 | 0.0561 | [+0.0258, +0.2474] | 否 |
| `L3_fixed_lt150` | 66,594 | 66,713 | +0.2105 | 0.0574 | [+0.0910, +0.3206] | 否 |
| `L3_joint_lam000` | 66,594 | 66,713 | +0.1438 | 0.0556 | [+0.0326, +0.2504] | 否 |
| `L3_joint_lam150` | 66,594 | 66,713 | +0.1294 | 0.0632 | [+0.0076, +0.2437] | 否 |
| `L3_missing_confounders` | 66,594 | 66,713 | +0.2153 | 0.0561 | [+0.0952, +0.3198] | 否 |
| `L3_overlap_extreme` | 66,594 | 66,713 | +0.1280 | 0.0558 | [+0.0165, +0.2347] | 否 |

Tier2 小计：CI 跨零 4/20（`L0_zero_purchase_effect`、`L1_heterogeneity_000`、`L2_n100000_p050`、`L2_n30000_p050`）；
点差为正 19/20，唯一为负的是 `L0_Pi_heterogeneous_cost`（−0.1684，CI [−0.2664, −0.0767]），
是否稳健要看 §3 的 30 次重复，单 rep 不下结论。`L2_n100000_p050` / `L2_n30000_p050` 的区间更宽
（半宽 0.150 / 0.293），源于更小的 n（进入定向臂 33 312 / 10 086 人），仍只作方向判断。

**必须披露（19:46 发现）**：`L2_immature_negative_control` 的 fixed bootstrap 与 `L2_n200000_p050`
**逐字节相同**（`md5 69da7f4a…`；`n_targeted/n_random`、点差、SE、CI 全同；两格 `row.json` 的
`observed_hash_without_run_id` 同为 `fa2e993a…`，ATE 四项亦全同）。原因：该格注册的机制键
`dgp.l2.include_immature_analysis_control: true`（`configs/v3/scenarios.yaml:1895`）**在源码中从未被读取**
（`grep -rn include_immature src/` 无命中；SQL 层 `allow_immature=True` 的诊断路径存在，但 G 矩阵未接线）。
⇒ 该格实际是 `L2_n200000_p050` 的同数据复制，**不得把它的数字当作"未成熟快照产生假增益"的证据**；
若要评估该机制，须另立注册分析。已记入反思日志 19:46 条与 §6 第 7 条。


## 5. 证据与复现（待填）

- `scripts/41_export_g03_evidence.py --check`：24 格逐 rep 表齐全、逐格契约列、固定 bootstrap 24 格
  （预算恒 0.2 / 次数恒 1000）、复算汇总 4 指标 × 24 格 = 96 行并与 `outputs/tables/v3_g_g_{core,tier2}.csv`
  对账、两个根的 `run_summary.json` 均 `status=formal` 且 `failures=[]`、`bootstrap_resamples` 分别为
  0（矩阵）与 1000（固定）→ 全过后才导出 → `scripts/33_register_evidence_top.py --dirs g03_formal`；
- **逐 rep 表契约列**（41 号 `check_cell`，2026-10-29 11:20 修）：`rep / status / protocol_config_hash /
  block / tier / n / n_treated / n_control / validation_bootstrap_resamples` 缺一即失败；列名是 `n`
  **不是** `n_total`（矩阵行 schema 无后者，旧写法在首格完整帧上必 `KeyError`）；另断言
  `n_treated + n_control == n`、`rep` 为 `0..R-1` 的排列、`status/block/tier/n` 逐格唯一。
  该修复**不触及源码哈希**（`scripts/` 不在 `pipeline_source_hashes` 内），可在运行期落地；
- **overlay 不在哈希账上**：`configs/budget/tier2_overlay.yaml`（`02644767…`）与 G02 的
  `g02_bootstrap_overlay.yaml` 都会被 `create_snapshot` 整树复制进快照目录，但
  `snapshot_binding.source_hashes`（49 文件）只记 v3 集；`34 --snapshot` 也只校验"绑定 vs live 相等"，
  不切换运行根。本次保护 = 冻结窗口 + 两文件运行期未改（收尾以 sha256/mtime 复核，记入 G04）；
- 导出为 staging + 原子换名，旧目录保留时间戳备份（`%Y%m%d%H%M%S`）；
- 顶层登记**留人工复核**后再执行。

## 6. 局限与结论失效条件

1. **合成 DGP**：全部数字只对注册的参数化数据生成过程成立。
2. **Tier2 精度**：`R=30` 时覆盖率 SE≈0.040，只能判方向与量级，**不得与 Tier1 数字并列**，
   也不得据此宣称某机制"稳健"或"失效"。
3. **单策略单预算**：只评贪心增量利润/成本策略在 0.2 元档；fixed bootstrap 也只覆盖该档。
4. **core 四格不是新证据**：它们与 G02 共享同设计，结论一致是预期，不构成独立复现。
5. **无覆盖率口径**：`truth_columns_present: false` 只表示冻结决策表不含真值；逐 rep 的
   `truth_*` 文件在 freeze 之后落盘，但本轮**没有注册覆盖率统计量/校验**。报告只报估计精度，
   不得出现"95% CI 覆盖真值 X%"这类未经注册分析支持的表述。
6. **一格机制未实现（19:46 披露）**：`L2_immature_negative_control` 的注册键
   `dgp.l2.include_immature_analysis_control` 在源码中从未被读取，该格与 `L2_n200000_p050`
   数据与结果逐字节相同（§4.2 披露段）。因此 24 格里实质只有 23 个不同机制；该格不能作为
   未成熟快照假增益的证据。修实或补做该诊断都需另立注册分析，不属本轮。
7. **结论失效条件**：若快照哈希与实际运行源码不符、任一格 `provisional=True`、或 Tier2 出现
   rep 缺失/重复，本报告作废并重跑缺口（按 §2 续跑纪律）。

## 7. 判定边界

"通过"只表示：**24 格跑满注册 R、记录准确、断言范围正确、证据可复算**。
不表示定向策略在真实业务有效、不表示 Tier2 全 65 格已覆盖、不表示结果可部署。
