# G 阶段执行器缺口与设计（2026-10-28 21:05，北京时间）

> 合成数据 / 已知 DGP。本文不是验收凭据，而是**未实现臂的合同说明书**：
> 补齐前 G01–G04 不得开跑，否则产物看起来完整、实际缺臂（见 `docs/v3_决策与反思日志.md` 20:59 条）。

## 0. 现状一览

| 臂 | 状态 | 执行器 | 工程证据 |
|---|---|---|---|
| ATE + 学习 + 独立验证 + 单一预算名单 | 已实现 | `scripts/34_g_matrix_run.py` + `evaluation/v3_g_matrix.py` | `outputs/evidence/g_smoke/`（28 件） |
| 完整链路 AA（四层 × R） | 已实现（21:00） | `scripts/36_g_aa_run.py`（复用 `v3_aa.run_full_chain_aa`） | `outputs/evidence/g_aa_smoke/`（9 件） |
| 固定策略 bootstrap 1000 | **未实现** | — | — |
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

## 2. 再训练 bootstrap

- **口径**（`docs/v3_协议.md:105`）：每层 Tier1 **代表场景**另做完整再训练 bootstrap。
- **数量冲突（P1，未解决）**：
  - 冻结配置 + 代码计数：`planned_counts["retraining_bootstrap_jobs"] = len(core) × 200 = **800**`
    （`src/causal_growth/v3_config.py:140`），按 240 s/rep ≈ **53.3 CPU·h**；
  - 任务书 §3 表：`重训 bootstrap 200` 行按 **200 次**计 ≈ 13.3 CPU·h；
  - `configs/budget/repetition_overlay.yaml`：`retraining_bootstrap_total_jobs: 80`（无代码读取）。
- **影响**：G 阶段合计 207.2 h 只含 200 次（13.3 h）。若按冻结配置的 800 次，仅此一项 **+40 h**，
  直接越过 210 h 上限。**必须先由用户裁决 80 / 200 / 800**，裁决前不得开 G02。
- **接线点**：与矩阵学习的 `run_cell` 共用"一 rep 一次建数据 → 学习 → 验证"链路，
  区别只在重抽样的单位是用户、且要重新拟合；建议复用 `v3_g_matrix.run_cell` 的
  `build_history_dataset` + `fit_history_models`，新增 `resample=` 参数，避免另写一套。

## 3. 随机名单（`random_list_seeds_per_budget = 200`）

- **口径**：每个（冻结数据, 预算）抽 200 个随机名单作为"随机定向"基准分布。
- **成本风险**：冻结配置 `planned_counts["random_baseline_lists"] = **11 680 000**`
  （7 300 学习 rep-模型集 × 8 预算 × 200）；即使按覆盖后的 1 000 学习集 × 4 预算 × 200
  也有 **800 000** 个名单。每个名单要抽 ~预算/券面额 个用户并汇总利润，
  按 200 000 用户、`argpartition` 约 5 ms 估，800 000 个 ≈ 1.1 h，11.68 M ≈ 16 h。
  **这是估算，不是实测**；必须先在 n=2 000 上测单名单耗时再外推。
- **接线点**：`v3_g_matrix.select_policy_list` 已有选人逻辑，随机名单只需把打分列
  换成随机流（`child_rng(master_seed, "g.random_list", index=(rep, budget, seed))`），
  不得复用同一随机流，也不得扰动既有流。
- **验收**：随机名单的利润分布 vs 已选名单；报告必须写"随机基准"而不是"对照组"
  （两者在验证队列上的含义不同）。

## 4. G03 的 L2 交叉 / L3 三分支

- **口径**：GOAL G03 要求"L2 完整交叉/时间，L3 三分支，L1 与业务敏感性"，且
  验收为"冻结矩阵逐格正式结果"。L2/L3 的"交叉"与"分支"具体是哪几格、按什么拆分，
  必须从 `configs/v3/scenarios.yaml` 的 `roles`/`overrides` 与 `matrix_contract` 读出，
  **不得按常识发明**（AGENTS §4）。
- **现状**：`34` 的 `planned_cells` 只取 Tier1 四个 core + overlay 选中的 Tier2 20 格；
  L2 交叉 / L3 三分支若不在其中，则 G03 无论跑多久都不会产出。
- **下一步**：先做一张"G03 要求格 → 冻结矩阵格 ID"的映射表，缺哪格补哪格；
  映射表落盘后再决定是否扩 overlay（扩 overlay 会改预算，需重新核算并报用户）。

## 5. 开跑前的最小检查单

1. 用户对 R>0 的明确开跑确认 + 本文 §2 的 80/200/800 裁决；
2. 机器独占、内存看护（含模型 rep 峰值 2.9–3.2 GB；4 worker 安全、6 worker 先释放内存）；
3. 快照 `src/ sql/ configs/` 并以 `--snapshot` 绑定（36 与 34 共用同一校验）；
4. 每条臂各跑一次 R=1 工程冒烟并落证据，再启动正式 R；
5. 全量 pytest 单进程串行跑出绿灯，日志入库（AGENTS §11.4）。
