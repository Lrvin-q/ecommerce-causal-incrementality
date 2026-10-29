# G03 正式报告 —— Tier1 core 四格 + Tier2 二十格矩阵（G03 骨架）

> **合成数据 / 已知 DGP**。本报告只回答"在注册的 24 个机制场景下，策略价值与决策通过率如何"，
> 不表示任何真实业务效果。维护时间：2026-10-29 11:16（北京时间）。
> 当前状态：**未开跑**（由 `out/g03_chain.sh` 在 G02 收尾后自动启动）；§3/§4 待填。

## 1. 设计

| 项 | 取值 | 依据 |
|---|---|---|
| 格数 | **24 = 4 个 Tier1 core + 20 个 Tier2 选中格** | `GOAL.md` G03 行的 20 格指 Tier2 子集；core 格同批跑以对齐 Tier1 口径 |
| 重复数 | core `R_ate=500`（学习/验证 100）；Tier2 `R=30` | `configs/budget/tier2_overlay.yaml`（`02644767…`）与协议注册值 |
| 策略 | `greedy_incremental_profit_per_cost` | 与 E/F/G 主口径一致 |
| 模型 | 各层适用集合 `common ∪ additional_by_level[level]`（L0/L2 四项；L1/L3 另加 `dr_learner`），按验证选模 | `configs/v3/models.yaml`（冻结集内）；34 号未给 `--models` 时按格解析（11:14 冒烟修复） |
| 固定 bootstrap | **仅主预算 0.2 元档，1 000 次，24 格 × rep 0**（阶段 A） | 用户 2026-10-28 22:26 裁决② |
| 批准号 | `G03-FORMAL-20261029`（矩阵）／`G02-FORMAL-20261029`（固定 bootstrap） | 用户 2026-10-29 批准 |
| 快照 | `out/g03_snapshot`（链条启动时由 `create_snapshot` 生成，哈希待填） | AGENTS §11 冻结窗口 + 哈希绑定校验 |
| 并发 | 6 workers；阶段 B `--shard-size 50`（core 每格 10 片、Tier2 每格 1 片） | 决策单 §H.2 |

**预算口径**：决策单 §H.2 的 159.2 CPU·h = 95.9（core）+ 63.3（Tier2）；链条两个阶段串行，
阶段 A 约 3.3 CPU·h，阶段 B 约 26.5 h 墙钟（6 路）。

## 2. 执行记录（待填）

| 时刻 | 事件 |
|---|---|
| 11:14 | 开跑前冒烟发现：34 号不带 `--models` 时把 `dr_learner` 也交给 L0，抛 `ModelNotApplicableError`——阶段 A/B 都会在 L0 立即失败。修 `_worker` 按层解析；L0+L1 两格 n=2000 × rep0 × 1000 次重抽 **EXIT=0**（`out/smoke_g03b.log`），41 `--check` 对半成品报缺格并 **EXIT=2**（符合预期） |
| 待填 | 链条启动（等 `out/g02_logs/post.status` 出现 `OK:`） |
| 待填 | 快照生成（文件数 / `source_hashes_sha256`） |
| 待填 | 阶段 A 完成（`fixed_exit=0`） |
| 待填 | 阶段 B 完成（`g03_exit=0`） |

**续跑纪律（失败时）**：`--resume` 只救"跑到一半被杀、有 `repetitions_provisional.csv`"的分片；
已完成分片会整片重跑。正确做法见 `AGENT_HANDOFF.md` 第 6 条与日志 2026-10-29 11:15 条。

## 3. 矩阵结果（待填）

数据源：`outputs/tables/v3_g_g_core.csv`、`v3_g_g_tier2.csv`（34 号 `_finalize`），
逐 rep 原件在 `out/g03_formal/shards/<cell>_s####/`，导出后为 `outputs/evidence/g03_formal/per_cell/`。

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

## 4. 固定 bootstrap 结果（待填）

数据源：`out/g02_fixed/shards/<cell>_s0000/<cell>/rep0/validation/fixed_bootstrap.csv`（24 格）；
导出后为 `outputs/evidence/g03_formal/fixed_bootstrap.csv`。

**阶段 A 的文件形态**：每格只跑 rep 0（1/R_ate），但状态是 `formal` 且该分片计划 rep 已全部完成，
按 `provisional = completed < target_reps or status != "formal"`，34 号写的是正式 `repetitions.csv`
（冒烟里出现 `_provisional` 是因为那次是 engineering）。`out/g02_fixed/summaries/` 的汇总表因未覆盖
R_ate 带 `_provisional` 后缀，41 号不读它；41 的固定 bootstrap 校验只读 `fixed_bootstrap.csv`
与 `run_summary.json`。

待填内容：
- 每格预算（应恒为 0.2）、`resamples`（应恒为 1000）、点差、95% CI、CI 是否覆盖 0；
- 点差 = 定向臂 − 随机臂（同 rep、同批用户、同预算，按模型配对，AGENTS §12.6）。

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
6. **结论失效条件**：若快照哈希与实际运行源码不符、任一格 `provisional=True`、或 Tier2 出现
   rep 缺失/重复，本报告作废并重跑缺口（按 §2 续跑纪律）。

## 7. 判定边界

"通过"只表示：**24 格跑满注册 R、记录准确、断言范围正确、证据可复算**。
不表示定向策略在真实业务有效、不表示 Tier2 全 65 格已覆盖、不表示结果可部署。
