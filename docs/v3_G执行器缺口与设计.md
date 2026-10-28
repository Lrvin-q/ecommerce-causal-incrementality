# G 阶段执行器缺口与设计（2026-10-28 21:05，北京时间）

> 合成数据 / 已知 DGP。本文不是验收凭据，而是**未实现臂的合同说明书**：
> 补齐前 G01–G04 不得开跑，否则产物看起来完整、实际缺臂（见 `docs/v3_决策与反思日志.md` 20:59 条）。

## 0. 现状一览

| 臂 | 状态 | 执行器 | 工程证据 |
|---|---|---|---|
| ATE + 学习 + 独立验证 + 单一预算名单 | 已实现 | `scripts/34_g_matrix_run.py` + `evaluation/v3_g_matrix.py` | `outputs/evidence/g_smoke/`（28 件） |
| 完整链路 AA（四层 × R） | 已实现（21:00） | `scripts/36_g_aa_run.py`（复用 `v3_aa.run_full_chain_aa`） | `outputs/evidence/g_aa_smoke/`（9 件） |
| 固定策略 bootstrap 1000 | **部分实现**（代表 rep × 主预算；全预算编排未实现） | `run_validation_arm(bootstrap_resamples=…)` + `scripts/34 --bootstrap-resamples` | `tests/test_v3_g_fixed_bootstrap.py`（7 项）；CLI 冒烟在 `out/g_bootstrap_smoke/`（未导出登记，可复跑） |
| 再训练 bootstrap | **未实现** | — | — |
| 随机名单（每预算 200 种子） | **未实现** | — | — |
| G03 的 L2 交叉 / L3 三分支专项 | **未实现** | — | — |

## 1. 固定策略 bootstrap（1000 次）

- **口径**（`docs/v3_协议.md:105`）：在每个**非 AA 场景的代表 rep、所有预算**上，对
  「已选策略 − 随机策略」的差做 1000 次重抽样；其他 rep 用预设影响函数区间。
  **不得**把代表 rep 的 bootstrap 说成"每 rep 重训"。
- **接线点**：`v3_g_matrix.run_validation_arm`（`src/causal_growth/evaluation/v3_g_matrix.py:618`）
  在真值阶段之后已有 `per_user`（`freeze_observed` 产物，`policy_list.csv`）与 `arm_summary`。
  bootstrap 需要逐用户的实现利润，因此必须在 `freeze` **之后**执行（冻结先于真值不可逆）。
- **注意**：`metrics.bootstrap_se` 只支持单样本均值/中位数，**不能**直接用于"两臂差"；
  需要独立的双样本重抽样函数（各自有放回重抽，差 = 均值差），并写入 `repetitions_telemetry.csv`
  之外的独立产物（重抽样耗时可省略，但 resample 数与预算档必须落盘）。
- **成本**：不重拟合；冻结配置 `planned_counts["fixed_bootstrap_resamples"]=552 000`
  （69 学习格 × 8 预算 × 1000）。必须在代表 rep 上实测一次再乘。
- **验收**：每个（代表格，预算）一组 1000 次差的分布；报告给均值差、SE 与 95% 百分位区间；
  与 `arm_summary` 的点估计一致（差 = 两臂均值差，误差 < 1e-12）。
- **已实现（2026-10-28 21:30）**：
  - `two_sample_bootstrap_diff` 做两臂各自有放回重抽，RNG 流 `child_rng(master_seed, "g.fixed_bootstrap", rep)`；
  - `run_validation_arm` 在真值审计之后、用 `assigned_policy_arm` 与 `net_profit` 重抽，写
    `validation/fixed_bootstrap.csv`（含 `budget_cny_per_user`、`resamples`、`point_diff`、`bootstrap_se`、`ci_low/high`）；
  - 逐 rep 表新增 5 列 `validation_bootstrap_{resamples,point_diff,se,ci_low,ci_high}`；
    manifest 记 `fixed_bootstrap_resamples`、`fixed_bootstrap_scope`、`fixed_bootstrap`；
  - 守卫：`rep != 0` 拒绝（代表 rep 固定为 0）；`status="formal"` 且要跑 bootstrap 时**直接拒绝**，
    因为全预算编排尚未实现——正式 G01 不得以“只跑主预算”开跑。
- **未实现的全预算部分与成本**：每层代表格 × 8 个预算需要**各自构建一次验证总体**（分配不同 → 结果不同）。
  552 = 69 学习格 × 8 预算；扣除已计入的 69 个主预算验证 rep，仍多 **483 次验证构建**；
  按 D01 的 G2−CF = 131.2 s/次，约 **17.6 CPU·h**（不含 552,000 次重抽样本身）。
  该成本尚未进任何上限表，必须在 G02 排期前与用户裁决。
  **21:52 口径更正**：69 格是**冻结矩阵**的格数；`configs/budget/tier2_overlay.yaml` 的执行矩阵
  只有 **28 个学习格**（Tier1 8 + Tier2 20），按 8 档全跑只多 **196 次构建 ≈ 7.1 CPU·h**
  （G 阶段合计 214.3）。两个数分别对应"冻结 552,000 次"与"执行矩阵"两种口径，引用时必须写明。

## 2. 再训练 bootstrap

- **口径**（`docs/v3_协议.md:105`）：每层 Tier1 **代表场景**另做完整再训练 bootstrap。
- **数量冲突（P1，未解决）**：
  - 冻结配置 + 代码计数：`planned_counts["retraining_bootstrap_jobs"] = len(core) × 200 = **800**`
    （`src/causal_growth/v3_config.py:140`），按 240 s/rep ≈ **53.3 CPU·h**；
  - 任务书 §3 表：`重训 bootstrap 200` 行按 **200 次**计 ≈ 13.3 CPU·h；
  - `configs/budget/repetition_overlay.yaml`：`retraining_bootstrap_total_jobs: 80`（无代码读取）。
- **影响**：G 阶段合计 207.2 h 只含 200 次（13.3 h）。若按冻结配置的 800 次，仅此一项 **+40 h**，
  直接越过 210 h 上限。**必须先由用户裁决 80 / 200 / 800**，裁决前不得开 G02。
- **21:56 口径更正（重要）**：协议原文是「**每层** Tier1 代表场景另做 **200** 次」
  （`docs/v3_协议.md:105`），每层 1 个 core 格 ⇒ **800 才是协议忠实值**；
  任务书 §3 与 GOAL G02 的"200"是把"每层 200"读成了总数。207.2 h 因此**少算 40 h**。
  维持 210 上限的唯一合规做法是**同时改协议与 GOAL**，不能只在任务书里写 200。
- **接线点（21:55 核查后作废）**：原文"给 `build_history_dataset` 加 `resample=` 参数"**不可实施**：
  `ObservedDataset` 只允许 `from_sql_result` / `from_manifest` 构造
  （`src/causal_growth/data/v3_observed.py:124-148`：`_SQL_TOKEN` 守卫 + `sql_sha256` /
  `analysis_sha256` 与 SQL 输出逐字节绑定），对观测表有放回重抽会立刻破坏校验；
  `generate_v3_population` 也没有用户级重抽参数。可行路径只有两条：
  ① 扩 DGP：新增"按已有 population 的用户索引有放回重抽 → 重发新 `user_id` → 重走订单/五表/SQL"
  （真实 user bootstrap，工程量最大，需同步重写审计账本）；
  ② 改口径：用"新 rep 抽样"充当重训重复（**这是 MC 重复，不是 bootstrap**，措辞必须改）。
  两条都需用户裁决，且必须与 800/200/80 的次数裁决一起定。

## 3. 随机名单（`random_list_seeds_per_budget = 200`）

- **口径**：每个（冻结数据, 预算）抽 200 个随机名单作为"随机定向"基准分布。
- **成本风险**：冻结配置 `planned_counts["random_baseline_lists"] = **11 680 000**`
  （7 300 学习 rep-模型集 × 8 预算 × 200）；按 **Tier2 overlay 执行矩阵**（学习 rep-集
  = Tier1 8×100 + Tier2 20×30 = **1 400**）则为 **112 万**（4 预算）～**224 万**（8 预算）个名单，
  旧的"1 000 学习集 × 4 预算 × 200 = 800 000"是更早的估计。每个名单要抽 ~预算/券面额 个用户并汇总利润，
  按 200 000 用户、`argpartition` 约 5 ms 估，112 万 ≈ 1.6 h，224 万 ≈ 3.2 h，11.68 M ≈ 16 h。
  **这是估算，不是实测**；必须先在 n=2 000 上测单名单耗时再外推。
- **接线点**：`v3_g_matrix.select_policy_list` 已有选人逻辑，随机名单只需把打分列
  换成随机流（`child_rng(master_seed, "g.random_list", index=(rep, budget, seed))`），
  不得复用同一随机流，也不得扰动既有流。
- **验收**：随机名单的利润分布 vs 已选名单；报告必须写"随机基准"而不是"对照组"
  （两者在验证队列上的含义不同）。

## 4. G03 的 L2 交叉 / L3 三分支（**口径与预算冲突，需用户裁决**）

### 4.1 冻结矩阵里实际有什么

`matrix_contract.cross_pairing_references` 只给了三条参照：
`L2_temporal → L2_n200000_p050`、`L3_overlap → L3_fixed_lt000`、`L3_u_shape → L3_fixed_lt050`。
`configs/v3/scenarios.yaml` 里 L3 的 `dgp.l3.branch` **只有两个取值**（`fixed_truth`、`joint`），
"三分支"在仓库任何配置/文档里都没有定义——GOAL G03 的这个词目前**不可执行**。

Tier2 65 格的实际构成（`by_level` 73 − Tier1 8）：L0 3 / L1 25 / L2 17 / L3 20。

### 4.2 GOAL G03 的字面要求 vs 20 格 overlay

| GOAL G03 字面要求 | 冻结矩阵对应 | overlay 实跑 | 字面是否满足 |
|---|---|---|---|
| L2 **完整**交叉/时间 | n∈{30k,60k,100k,200k} × p∈{.10,.30,.50} 共 12 格 + 漂移/构成/延迟 | 5 格（n 两端 p=.50 + 漂移 + 构成 + 延迟负对照） | **否**（9 格交叉未跑） |
| L3 三分支 | 只有 2 个 `branch` 取值，分组实际是 3 类：λ_T 扫描 / λ_T×λ_Y 联合 / 重叠与缺失混淆压力 | 7 格（覆盖三类，各取端点） | **词义未定义**；按三类解读则满足，按"每分支全扫描"则不满足 |
| L1 与业务敏感性 | L1 Tier2 25 格（异质性、信号、误设、缺失、成本、参数、学习量） | 6 格 | **否**（19 格未跑） |
| 验收"冻结矩阵逐格正式结果" | 65 格 | 20 格 | **否**（45 格按同类判定不跑） |

### 4.3 价格（同一 106/130/106 s 成本模型，估算非实测）

- 单格单 rep = ATE 106 + 学习 130 + 验证 106 = 342 s；R=30 ⇒ **2.85 CPU·h/格**。
- overlay 20 格 = 57.0 h；冻结 65 格 = 185.3 h，**差 +128.3 h**。
  其中 L2 完整交叉 12 格 = 34.2 h（overlay 5 格 14.25 h，+19.95）；
  L1 全敏感性 25 格 = 71.25 h（overlay 6 格 17.1 h，+54.15）。
- 若 G03 按字面跑满 65 格：162.8（含 overlay 20 格）−57.0 +185.3 = 291.1 h，
  加 AA 44.4 ⇒ **335.5 h**，已不含重训 800 与两个基准臂。

### 4.4 结论与需要用户裁决的三种走法

**GOAL G03 的字面要求与 210 h 上限不可同时满足。** 三条路只能选一条：

1. **改 G03 措辞**（推荐，代价最小）：把"L2 完整交叉"改为"交叉轴两端 + 漂移/构成代表格"、
   把"L3 三分支"改为"L3 三类机制各取端点"、把"L1 与业务敏感性"改为"6 个代表格"，
   并在 GOAL 写明 45 格不跑的同类判定依据（已有 `docs/v3_tier2_selection.md`）；
2. **抬高上限**：按字面跑满 65 格，G 阶段 ≈ 335.5 h（还不含重训/基准臂），需用户明确接受；
3. **砍到子集**：只补 L2 完整交叉（+19.95 h）或只补 L1（+54.15 h），其余写"不跑"。

裁决前 `34` 只跑 20 格 + Tier1 core，**G03 无法产出符合字面验收的结果**——这一条必须写在
G03 的验收状态里，不能等跑完再解释。

## 5. 开跑前的最小检查单

1. 用户对 R>0 的明确开跑确认 + 本文 §2 的 80/200/800 裁决；
2. 机器独占、内存看护（含模型 rep 峰值 2.9–3.2 GB；4 worker 安全、6 worker 先释放内存）；
3. 快照 `src/ sql/ configs/` 并以 `--snapshot` 绑定（36 与 34 共用同一校验）；
4. 每条臂各跑一次 R=1 工程冒烟并落证据，再启动正式 R；
5. 全量 pytest 单进程串行跑出绿灯，日志入库（AGENTS §11.4）。
