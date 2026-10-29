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
  **21:42 口径更正**：69 格是**冻结矩阵**的格数；`configs/budget/tier2_overlay.yaml` 的执行矩阵
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
- **21:45 口径更正（重要）**：协议原文是「**每层** Tier1 代表场景另做 **200** 次」
  （`docs/v3_协议.md:105`），每层 1 个 core 格 ⇒ **800 才是协议忠实值**；
  任务书 §3 与 GOAL G02 的"200"是把"每层 200"读成了总数。207.2 h 因此**少算 40 h**。
  维持 210 上限的唯一合规做法是**同时改协议与 GOAL**，不能只在任务书里写 200。
- **接线点（21:44 核查后作废）**：原文"给 `build_history_dataset` 加 `resample=` 参数"**不可实施**：
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

## 6. 裁决后的实现规格（2026-10-28 22:47，北京时间）

用户已裁决 A=200 / B=仅主预算 / C=20 格 / D=按推荐 DR；E 已批准并已开跑 G01。
本节把裁决翻成"可写代码"的规格，G01 冻结窗口结束后按此实现，**不改** `configs/v3/*.yaml`。

### 6.1 A：再训练 bootstrap 200 次（每 core 格 50）

- **覆盖文件**：`configs/budget/g02_bootstrap_overlay.yaml`（新文件，落在允许目录）：
  ```yaml
  source_label: 合成数据 / 已知 DGP
  retraining_bootstrap_total: 200        # 4 个代表场景合计（裁决 A）
  retraining_bootstrap_per_cell: 50      # = total / len(core)，执行器须自校验
  retraining_bootstrap_label: 参数化重复抽样（已知 DGP 重抽）
  fixed_bootstrap_resamples: 1000        # 不重拟合，只重抽样
  fixed_bootstrap_budget_scope: primary_0.2   # 裁决 B
  ```
- **语义（必须先写清再写代码）**：本项目的"再训练 bootstrap"落在**已知 DGP 上重抽历史总体**
  （`stream="dgp.retrain_bootstrap"`、`index=b`），每个 b 走完整链路：建历史五表 → SQL → 清洗 →
  重训策略 → 在**冻结验证帧**上评估。这**不是**对已观测历史的非参数 resample——
  `ObservedDataset` 只允许 `from_sql_result`/`from_manifest` 构造、且 `analysis_sha256` 与 SQL 输出逐字节绑定
  （`src/causal_growth/data/v3_observed.py:124-148`），对观测表重抽会立刻打破校验。
  报告与表头一律写**参数化 bootstrap（已知 DGP 重抽）**，不得写"非参数 bootstrap"，也不得与 Tier1 数字并列。
- **执行器**：`scripts/39_g_retrain_bootstrap_run.py`（`plan|run|merge` 三模式，仿 34/36）。
  **38 号已被 `38_export_d01_evidence.py` 占用**，22:47 草案里的"scripts/38_g_bootstrap_run.py"作废。
  **不能直接复用 34 号**：`run_g_cell` 会连带生成独立验证队列（打分 → 三臂 → 真值），
  单 rep 实测随选模 365–670 s；A 的链路只需"建历史五表 → SQL → 清洗 → 重训 → 在**冻结验证帧**上评估"，
  不含验证队列。门禁：`--status formal` 必须带批准号 + 快照；overlay 缺任一键或
  `per_cell × len(core) != total` 直接拒绝；运行清单显式回写 `retraining_bootstrap_total: 200`，
  **不得**回落到冻结配置算出的 800。
- **配套第二个 overlay（必须是合法 budget_overlay）**：A 的 rep 数走 34 的 `plan_cell` 契约，
  需要 `configs/budget/g02_reps50_overlay.yaml`：`tier1_learning_reps: 50`、`tier1_validation_reps: 50`、
  `tier2_cells` 非空且合法、`tier2_reps: 30`。`g02_bootstrap_overlay.yaml` 不是 BudgetPlan
  （`kind: bootstrap_overlay`，缺 tier1/tier2 键），只作文档与报告口径，**不得**传给 `--overlay`。
  **实现核对（2026-10-29 05:52）**：39 号不消费 budget overlay——A 臂每格 b 数与总数由
  `g02_bootstrap_overlay.yaml` 的 `retraining_bootstrap_per_cell/total` 提供，并由
  `check_counts`（per_cell × len(core) == total）自检；`plan_cell` 只用来取 `n`/`block`。
  因此 **不创建** `g02_reps50_overlay.yaml`（无消费者的配置等于死配置），本条前半段作废。
- **成本两笔账**：13.3 CPU·h = 200 × 240 s。但单 rep 若落在 365–670 s（F02 实测区间），
  200 次就是 **20–37 CPU·h**，是决策单 13.3 的 1.5–2.8 倍。**开跑前必须先 R=1 实测这条轻量链**，
  实测超 320 s/次就回来重报预算，不得按 240 s 直接外推。


### 6.1.a 落地决定：不新增随机流，验证帧固定（2026-10-29 00:10，写代码前先定）

写 39 号之前先把两处"会做错"的地方钉死：

1. **"重抽历史总体"用 rep_id 偏移，不新增 DGP 流**。`generate_v3_population` 的每个 `rep_id`
   本来就是一次独立抽签（covariates/outcomes/timing/amounts 的子流全部以 `rep_id` 为 index，
   `src/causal_growth/dgp/v3_*.py` 逐处可核）。39 号令 `history_rep_id = RETRAIN_OFFSET + b`
   （`RETRAIN_OFFSET = 1_000_000`，与正式 rep 0–199、AA 的 0–249 均不相交），
   语义就是"已知 DGP 重抽"，**不动 `src/`、不扰动任何既有随机流**。
   报告与 manifest 写 `bootstrap_kind: parametric_dgp_redraw` 并记 `history_rep_id`，
   不得写"非参数 bootstrap"，也不得与 Tier1 数字并列（§6.1 原文要求）。
   若将来真要 `dgp.retrain_bootstrap` 专用流，那是 src 改动 → 全量测试 + 源码重绑，不在 G02 窗口做。
2. **验证帧固定在一个 rep**。`run_validation_arm` 的 `rep_id` 同时决定验证队列与 bootstrap 种子
   （内部 `run_id=...validation:rep{rep_id}`）。39 号对 4 个 core 格 × 50 个 b **一律传同一个
   `VALIDATION_REP`**（取该格正式 rep 0），只让 `history_rep_id` 随 b 变。
   **修正（2026-10-29 10:26，正式跑炸过 4 格后）**：原定用 `validation_observed_hash` 断言
   逐字节相同是错的——该哈希覆盖整张观测表，含由本次 b 的打分决定的 `issued_action`，
   50 个 b 必然不同。改为两个与模型无关的指纹：`validation_frame_hash`（用户协变量）与
   `validation_arm_hash`（`user_id`/`assigned_policy_arm`/`policy_arm_probability`），
   任一漂移即失败。`validation_observed_hash` 仍逐 b 记录，只作"这一次实际评估了什么"的证据。
3. **每格次数自校验**：core 格 = `cell_meta(...)["tier"] == 1` 且 `"core" in roles`；
   `per_cell × len(core_cells) != total` 或 `per_cell != retraining_bootstrap_total // len(core)`
   一律拒绝，不得回落到冻结配置的 800。
4. **门禁**：`--status formal` 需批准号 + 快照；当前只有 R=1 实测权限。
   实测 > 320 s/次就回来重报预算（决策单 §H.1），不得按 240 s 外推。

### 6.2 B：固定策略 bootstrap 仅主预算档 0.2

- 现状守卫在 `status="formal"` 且 `bootstrap_resamples>0` 时**硬拒绝**（防半套产物）。这是保护机制，
  **不能删**。改法：守卫接受 `budget_scope`，只有显式 `budget_scope="primary_0.2"` 且运行清单里
  `budget_scopes: {"0.2": 1000, ...其余显式 none}` 时才放行；缺声明仍拒绝。
- 输出表必须带 `budget_scope` 列，"其余预算档未重抽样"写进报告 §局限，不得让读者以为覆盖了全预算。

### 6.3 C：G03 20 格（措辞已改）

- 不改代码、不改矩阵；GOAL G03 行已改"L2 两端 + 代表格 / L3 三类机制各取端点 / L1 6 个代表格"。
- 45 个未跑格的同类判定依据在 `docs/v3_tier2_selection.md`；报告不得声称"已跑满 65 格"。

### 6.4 D：随机名单按 DR 估值

- 开跑前**必须**先在 n=2 000 上测单名单耗时（估 ~5 ms/名单，未实测），再外推；
  报告写"随机基准（DR 估计）"，不得称"对照组"；全预算 200/档的口径保持字面，执行时在冻结验证帧上估值。

### 6.5 并行协议（G01 已验证，G02/G03 复用）

- `--workers` 上限 = 层数（一层一进程）；>4 路必须按 **rep 区间分片** + 多 out-root，再交 17 号多根合并。
- **同层分片 rep 区间必须不相交**：17 按 `(block, rep)` 去重 `keep="last"`，重叠会被**静默**吞掉。
  每个分片跑完必须用独立脚本核对"每层 rep 集合恰为 0..R-1"（G01 用 `out/g01_verify.py`）。
- 实测（2026-10-28 22:25–22:34）：6 路每 rep 132–135 s、峰值内存 10.69 GB、单进程最大 2 003 MB；
  8 物理核下 6 路比 4 路只慢约 5%。**每条 lane 必须是独立 out-root**，否则 `layer_runs` 与
  `<layer>/aa_repetitions.csv` 会互相覆盖。
- 每次正式跑前重新生成快照（源码一改，旧快照的 `_verify_snapshot` 会拒绝启动）。

### 6.6 G02 补丁锚点（2026-10-28 22:50 只读核实，冻结窗口结束后按此落地）

三处事实，决定 B 的补丁**只是把守卫换成登记**，不是新增"全预算编排"：

1. `src/causal_growth/evaluation/v3_f02.py:282-283`：验证臂的预算取自冻结配置
   `evaluation.independent_validation.primary_budget_cny_per_user`，**不存在预算参数**。
   即当前 bootstrap 天然只在主预算档上做，与裁决 B 完全一致。
2. `src/causal_growth/evaluation/v3_g_matrix.py:900-903`：`bootstrap_resamples>0` 只允许 `rep==0`。
3. 同文件 `:904-908`：`status=="formal"` 且 `bootstrap_resamples>0` **硬拒绝**；`:1043-1046`
   的 manifest 已经把该情形标成 `representative_rep_primary_budget_only`。

补丁内容（改 `src/`，必须在 G01 退出后、重跑全量绿灯前完成）：

- `run_g_cell` / `run_g_rep` 增加参数 `bootstrap_budget_scope: str = "primary_0.2"`；
- 把 `:904-908` 的拒绝改为：`formal` 且 `bootstrap_resamples>0` 时，**要求**
  `bootstrap_budget_scope == "primary_0.2"`，否则照旧抛错；同时把 scope 写进行/manifest；
- 断言 `fixed_bootstrap.csv` 的 `budget_cny_per_user` 唯一且等于配置主预算（`0.2`）；
- 不得删掉 `rep==0` 守卫，也不得允许未声明 scope 的 formal 跑。

**报告口径**：`src/causal_growth/v3_config.py:143` 的 `fixed_bootstrap_resamples` 是
"学习格 × 8 预算 × 1000"的计划数（全预算口径）。G02 实际执行 1 000 次（主预算），
报告必须同时写计划数与执行数，并引用 `budget_scope=primary_0.2`，不得让读者以为 8 档都跑了。


### 6.7 A 的第二个硬缺口：`run_validation_arm` 不回传策略价值（2026-10-28 22:55，只读核实）

`run_validation_arm` 内部算了 `decision`、`guardrail` 与真值审计，但返回值只有
`validation_n / targeted_n / random_n / predicted_spend_per_user / budget_per_user /
freeze_hash / observed_hash / source_hashes / build_info / fixed_bootstrap`
（`src/causal_growth/evaluation/v3_g_matrix.py:764-779`）。**策略价值与决策结论没有出口**，
所以 A 的"评估"拿不到被评估量。补丁必须**新增**返回键（不改既有键，避免动 34/36 与既有测试）：
`validation_decision`、`validation_guardrail`、`validation_truth_policy_value`；
新键只在调用方显式要时才算。A 的执行器（39 号）据此逐 b 落一行：`cell_id, b, history_rep_id,
chosen_model, policy_value, decision, guardrail`，再按 4 格 × 50 汇总。
