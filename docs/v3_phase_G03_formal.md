# G03 正式报告 —— Tier1 core 四格 + Tier2 二十格矩阵

> **合成数据 / 已知 DGP**。本报告只回答"在注册的 24 个机制场景下，策略价值与决策通过率如何"，
> 不表示任何真实业务效果。维护时间：2026-10-31 20:05（北京时间）。
> 当前状态：**24 格全部跑完**——Phase 2 于 **2026-10-31 19:33:21** 完成（Tier2 600/600、core ATE
> 1 600/1 600、复合 merge `duplicates=0`），收尾链 **19:36:47** 全绿；19:44 独立评审发现证据登记 P0
> （分片导出命名塌陷），19:48 修复并重导出（**357 条记录、0 条不符**）后再次全绿；20:01 按独立复核
> N1 再导出一次，证据包内 finalize 日志与状态**已闭合**。§3/§4 已填，
> **§3.0 的 D1-A 披露按裁决原样保留**（空转格不构成机制证据）。

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
**Phase 1 实测（20:16 更正，撤回 19:50 的 6.3 min/rep）**：19:50 那个数是用"运行 14 min 落 8 rep"
除以 6 路得到的，但 8 个 rep 是 6 个分片各自的首个 rep 加零头，启动开销把斜率压扁了。
按 6 个 worker 的 `rep<k>/row.json` 目录 mtime 量 21 个连续间隔（19:42–20:15）：mean **8.5**、
median **9 min/rep**，与单跑 8.6 min/rep 一致 ⇒ 6 路是**近线性吞吐**（6 份算力并行），不是"每 rep 变快"。
旁证：6 个 worker 进程各占满一核，39 min 墙钟内 CPU 2336 s ≈ 100%。
据此 400 rep ≈ **9.5 h**，ETA **10-30 04:45–05:45，点估计 ~05:10**；
Phase 2 的 Tier2 600 rep（20 格 × 30，同样走学习+验证）≈ 14.2 h、
core rep100–499（400 rep × 1.9 min/rep）≈ 2.1 h，合计 **16–17 h**（原记 13–15 h 同样偏乐观）。

## 2. 执行记录

| 时刻 | 事件 |
|---|---|
| 11:14 | 开跑前冒烟发现：34 号不带 `--models` 时把 `dr_learner` 也交给 L0，抛 `ModelNotApplicableError`——阶段 A/B 都会在 L0 立即失败。修 `_worker` 按层解析；L0+L1 两格 n=2000 × rep0 × 1000 次重抽 **EXIT=0**（`out/smoke_g03b.log`），41 `--check` 对半成品报缺格并 **EXIT=2**（符合预期） |
| 17:17:51 | G02 收尾 `merge_exit=0`，链条解除 14 h 等待 |
| 17:51 | **阶段 A 首跑失败**：`L1_cost_prediction_under`（成本预测乘子 0.8）按设计抛 `NotImplementedError`，23/24 格完成；旧产物归档 `out/g02_fixed_attempt1_20261029_1751`、`out/g03_snapshot_attempt1_20261029_1751` |
| 18:05–18:37 | 实现预测端乘子（真实成本不变，对数噪声仍拒绝）+ 补测试，提交 `d2d1423`；快照重建（49 文件，`6fdaf7bb…`）；重跑阶段 A **`fixed_exit=0`**（24 格 × rep0 × 1000 次，约 31 min） |
| 18:37:06 | 阶段 B 首跑启动：24 格 / 60 分片 / 6 路（`--shard-size 50`） |
| 19:36 | 按用户决定停链（`taskkill /T`），半成品归档 `out/g03_formal_interrupted_20261029_1935`；`g03_post` 停止，`chain.status` 记 paused |
| 19:36:30 | **Phase 1 启动**：core 4 格 × rep0–99，40 分片 × 10 rep、6 路，`--out-root out/g03_core_prefix`；快照校验通过（`6fdaf7bb…`） |
| 20:06 | Phase 1 进行中：25/400 rep 落盘（6 个 L0 分片并行，分片内 10 rep 跑完才写 `repetitions.csv`），最新写入 20:04，`phase1.log` 无 error/traceback；按 6–7 min/rep 外推 ETA 仍为 02:30–03:30 |
| 20:16 | Phase 1 进度 27/400 rep（6 分片各 4–5 rep，最新写入 20:15）；按 rep 目录 mtime 重测 **8.5–9 min/rep·worker**，ETA 更正为 10-30 04:45–05:45（点估计 ~05:10）；6 个 worker 各占满一核（2336 s CPU / 2340 s 墙钟），`phase1.log` 无 error |
| 23:58 | Phase 2 入口加固（脚本从未运行过，先只读复核）：复合根 `out/g03_formal/shards` 残留非空直接 exit 10（否则 `cp -r` 回退会把分片套进自身，`merge_roots` 对这种根静默 continue）、建链后逐分片核对 `<分片>/<cell>/repetitions*.csv` 缺则 exit 11；提交 `ecb0407`，注册表 §2.6 已记 |
| 00:02 | Phase 1 进度 **164/400**（`L0_P_main` 100/100 已完成，`L1_main` 6 个分片在跑）；23:44–00:12 三个读数 154→163→164，折 0.56–0.70 rep/min，ETA 顺延 **10-30 05:30–07:00**；`phase1.log` 无 error |
| 00:34 | Phase 1 进度 **182/400**（L0 100/100、L1 81/100、L2 1）；L1 批次耗时 5–15 min/10 rep，6 个 spawn worker 均在；`phase1.log` 无 error/traceback；ETA 维持 10-30 05:30–07:00 |
| 00:40 | Phase 1 **整分片完成 170/400**（`repetitions.csv` 数据行口径：L0 100/100、L1 70/100；在跑分片 `L1_main_s0006/s0008/s0009` 已开 10/4/3 个 rep 目录，未计入）。**口径变更**：00:02/00:32/00:34 的 164/181/182 数的是 rep 目录（含在跑分片已开始的 rep），此后一律用整分片口径。同刻 `phase1.log` 无 error |
| 05:55:41 | **Phase 1 完成并合并**：`phase1.status` 记 `phase1_exit=0` / `merge_exit=0` / `OK: G03 Phase1 core prefix 完成`；4 格各 100 rep（`_final` 四份均 `repetitions_provisional.csv`，`all_complete=false` 属预期 R=100/500），`duplicates_removed=0`；`run_summary.json` = `status=formal` / `failures=[]` / `bootstrap_resamples=0` |
| 17:36 | 复核 Phase 2 状态：`out/g03_tier2`、`out/g03_core_ate`、`out/g03_formal` 均不存在（**Phase 2 一步未跑**）；无 python 进程，机器空闲；磁盘 76 G 可用，Phase 1 产物 8.1 G（≈20 MB/rep，据此估 Phase 2 约 20 G） |
| 17:37:55 | **Phase 2a 启动**（用户批准，`nohup bash scripts/51_g03_phase2.sh`，bash 包装 PID 1507）：快照绑定 `6fdaf7bb…` 通过；`20 格 / 60 个分片；workers=6 status=formal`；60 s 内 6 个分片目录已建、8 个 python 进程在跑；预计约 16 h（Tier2 ~14 h + core 尾巴 ~2 h） |
| 17:45 | Phase 2 在跑：Tier2 6 个分片已建（`L0_Pi_heterogeneous_cost` / `L0_zero_purchase_effect` 各 3 分片），`rep10`–`rep20` 目录已开、`row.json` 尚未落，`phase2.log` 无 error；8 个 python 进程在跑。**更正 17:38 的 ETA**：Phase 2b 是 core 4 格 × rep100–499 = **1 600 rep（不是 400）**；按 Phase 1 实测 ATE 段 ~1.9 min/rep、6 路 ≈ 8.5 h，Tier2 600 rep 按 ~8 min/rep、6 路 ≈ 13 h，加 merge ≈ **22 h ⇒ ETA 10-31 15:30–16:30**。磁盘按 20 MB/rep 上界估 ~44 G（实际 ATE 段更小），当前可用 76 G |
| 17:48 | 自动收尾挂后台：轮询到 `phase2.status` 的 OK 行后自动执行 `63_g03_finalize.sh`（41 `--check` → 62 演练 → 41 导出 → 33 dry-run → 48 取数）并跑 `49 --with-check`（只读）；日志 `out/g03_logs/auto_finalize.log`，状态仍看 `finalize.status`。33 实登记与 §3 填数保持人工 |
| 18:08 | ~~ETA 49–61 h（11-01 22:00 – 11-02 06:00）~~ **18:10 判定此行为误算并作废**：当时误以为 2a/2b 同价，忽略了 `tier1_learning_reps=100` |
| 18:10 | **ETA 更正（18:08 行作废）**：分段实测——rep0–99 学习段 7.3–11.0 min/rep（约 21 MB/rep），rep≥100 只跑 ATE，`out/g03_formal_interrupted_20261029_1935` 的 rep100–280 实测 **1.87–1.88 min/rep**（每 rep 2 个文件、约 1 MB）。故 2a Tier2 600 rep ≈ 12–18 h、2b core ATE 1 600 rep ≈ 8–10 h，**总计 20–28 h，ETA 10-31 16:00–23:00**；磁盘约 14 G。18:06 Tier2 实测 14 rep / 28 min（≈0.5 rep/min，早期批次含启动开销） |
| 18:28 | Phase 2a 进度 **Tier2 30/600 rep**（`row.json` 口径；18:23→18:28 稳定增长，最近 3 分钟 24 个文件）；8 个 python 进程（6 spawn worker + 2 父）在跑。自动收尾（17:48 起）与 watchdog（17:44 起）均存活。**看护口径更正**：`auto_finalize.log` 的 `[auto] 63 exit=` 取的是管道中 `tee` 的退出码，**不能**作为 63 成功的证据；复核一律以 `out/g03_logs/finalize.status` 与 `auto_finalize.out` 为准 |
| 09:41:22 | **Phase 2a Tier2 完成**：600/600 rep（20 格 × 30）；`out/g03_tier2/run_summary.json` = `status=formal` / `failures=[]` / `duplicates=0`；09:41:23 自动转入 2b |
| 09:41:35–19:32:34 | Phase 2b core ATE rep100–499 跑完：**4 格 × 400 rep = 1 600**（32 个分片 × 50 行，逐分片 `provisional=False`）；`out/g03_core_ate/run_summary.json` = `status=formal` / `failures=[]` |
| 19:32:34 | 建复合根 `out/g03_formal/shards`（junction，失败回退 `cp -r`），19:33:04 记 **132 个分片** |
| 19:33:05–19:33:20 | 多根 merge 完成（`merge_exit=0`，`duplicates=0`）；`_final` 24 格行数核对 OK（core 500 / Tier2 30）；合成复合 `run_summary.json`（`composite=true`，`derived_from` 三份源 summary 的 sha256） |
| 19:33:21 | **Phase 2 完成**：`phase2.status` 末行 `OK: G03 Phase2 完成 2026-10-31 19:33:21`（`tier2/core_ate/merge/final_check/composite_summary` 五步 exit 全 0） |
| 19:34:07–19:34:26 | 自动收尾链触发：41 `--check` 与 62 演练通过，**33 dry-run rc=2**（只报 2 条，均指 `binding/snapshot_binding.json`）。进一步核对发现 `coverage.json` 的 **323 条 target 全部指向 `out/g03_evidence_staging/…`**（41 号用 staging 根登记），换名后整份索引失效；33 的 dry-run 当时只核身份类 JSON，所以只露出 2 条 |
| 19:35 | **修 41 号 target 重挂**（`_record` 增 `write_root/public_root`：写盘在 staging、登记用最终路径），重导出 323 条记录、0 缺失、0 staging 前缀；33 dry-run rc=0 |
| 19:36:47 | **收尾链全绿并实登记**：`63 --with-register` 的 `check/drill/export/register_dry_run/report48/register` exit 全 0；`out/g03_logs/finalize.log` 的 19:36:46/19:36:47 行记录「33 实登记（records 92 → 93）」与「收尾链通过」（`finalize.status` 每次启动被 `rm -f`，19:48 那次已覆盖该行，**不可再引 19:36:47 的 status 末行**）；顶层登记 **93 条 / 16 975 748 B**（幂等复算一致；**其中 G03 只占 1 条** `g03_snapshot_binding`，其余 322 条在目录级索引） |
| 19:37 | `49 --with-check --with-register --with-claims` **RC=0**：24 格达 R、49 文件快照一致、overlay 一致、42 门禁 274 条 Tier1 claim 全回指、40/41 检查 0、33 dry-run 0、顶层 93 条幂等 → `[VERDICT] READY` |
| 19:44 | **G03 独立评审返回 `PASS WITH CONDITIONS`**（`docs/reviews/v3_phase_G03_review.md`）：96 个汇总值与 24 个 bootstrap 值独立复算 **0 误差**、R/完整性成立、D1-A 披露成立；但查出 **P0-1**——分片导出用 `run.name`（恒等于格名）命名，**264 条分片记录塌陷到 48 个文件、216 条 sha/bytes 与磁盘不符**；另 3 项 P1、3 项 P2、5 项 P3 |
| 19:47 | 按 P0 修 41：分片名改用 `run.parent.name`，导出后自检（target 全局唯一、逐条 sha/bytes、文件数=记录数）；按评审建议加强 33：**全表逐条核 sha/bytes + 同 target 重复登记即失败**。反例实测：对旧台账跑 33 → **RC=2（48 个重名 target + 216 条不符）**，证明门禁真的会拦 |
| 19:48 | 重跑 `63 --with-register`：check/drill/export/dry_run/report48/register exit 全 0；证据包 **357 条记录**（264 个分片原件 + 24 合并表 + 24 manifest + 24 rep0 固定 bootstrap + 11 日志 + 3 源 summary 等）、**357/357 sha 与磁盘一致**、**0 条重名**；`finalize.status` `OK: G03 finalize 完成 2026-10-31 19:48:27`（20:01 重导出后，证据包 `logs/finalize.status` 140 B 与 `out/g03_logs/` 逐字节相同） |

**续跑纪律（失败时）**：`--resume` 只救"跑到一半被杀、有 `repetitions_provisional.csv`"的分片；
已完成分片会整片重跑，且 `run_cell` 的 `existing` 只来自 `resume_from` ⇒ **重跑不是追加，会用本次 reps
覆盖 `repetitions.csv`**（旧 `rep<k>/row.json` 仍在盘上，但逐 rep 表会少行，11:42 读码确认）。
正确做法：先 `34 merge` 收已完成 → 缺口另起 `--out-root out/g03_repairN` → 多根 `merge` 且确认
`duplicates=0`。见 `AGENT_HANDOFF.md` 第 6 条、注册表 §3 与日志 2026-10-29 11:15/11:42 条。

**分批跑法（19:36 起）**：Stage B 拆成 Phase 1（core rep0–99 → `out/g03_core_prefix`）与
Phase 2（Tier2 → `out/g03_tier2`；core rep100–499 → `out/g03_core_ate`）。每批都是独立 out-root、
分片编号互不覆盖，最后多根 `merge` 合并去重；`_final` 仍按 `R_ate=500` 判完整。
这是唯一安全的断点续跑方式——**不要**在原 out-root 上 `--resume`（已完成分片会被整片重算）。

## 3. 矩阵结果

数据源：`outputs/tables/v3_g_g_core.csv`、`v3_g_g_tier2.csv`（34 号 `_finalize`），
逐 rep 原件在**多根**：Phase 1 `out/g03_core_prefix/shards/<cell>_s####/`；
Phase 2 `out/g03_tier2/shards/…` 与 `out/g03_core_ate/shards/…`。
合并用 `34_g_matrix_run.py merge <各分片根…>`，按 `[scenario_id, block, rep]` 去重
（`duplicates` 必须为 0）；`_final` 只在 24 格都覆盖 `R_ate` 时才写正式表。
导出后为 `outputs/evidence/g03_formal/per_cell/`。

每格均跑满注册 R（core 500、Tier2 30），`provisional=False`；24 格 × 4 指标 = 96 行，与 41 号复算汇总一致。下表由 `outputs/tables/v3_g_g_core.csv` / `v3_g_g_tier2.csv` 直接排版，未手工改数；CI = mean ± 1.96×MC SE（与 39 号同口径，**不是**覆盖率）。


#### 3.1 主指标：人均净利润效应（Π 差）（`ate`）

**Tier1 core（4 格，R=500）**

| 格 | R | mean | sd | MC SE | 95% CI（±1.96×MC SE） |
|---|---:|---:|---:|---:|---|
| `L0_P_main` | 500 | 0.2434 | 0.0386 | 0.0017 | [0.2400, 0.2468] |
| `L1_main` | 500 | 0.2831 | 0.0455 | 0.0020 | [0.2792, 0.2871] |
| `L2_n200000_p050` | 500 | 0.2878 | 0.0441 | 0.0020 | [0.2839, 0.2916] |
| `L3_fixed_lt000` | 500 | 1.6641 | 0.0458 | 0.0020 | [1.6601, 1.6681] |

**Tier2 选中格（20 格，R=30；不与 Tier1 并列排序）**

| 格 | R | mean | sd | MC SE | 95% CI（±1.96×MC SE） |
|---|---:|---:|---:|---:|---|
| `L0_Pi_heterogeneous_cost` | 30 | 0.4362 | 0.0372 | 0.0068 | [0.4229, 0.4496] |
| `L0_zero_purchase_effect` | 30 | -0.5657 | 0.0351 | 0.0064 | [-0.5783, -0.5531] |
| `L1_cost_prediction_under` | 30 | 0.2779 | 0.0361 | 0.0066 | [0.2650, 0.2909] |
| `L1_heterogeneity_000` | 30 | 0.2138 | 0.0340 | 0.0062 | [0.2016, 0.2259] |
| `L1_heterogeneity_150` | 30 | 0.2967 | 0.0369 | 0.0067 | [0.2835, 0.3099] |
| `L1_mar_double` | 30 | 0.2779 | 0.0361 | 0.0066 | [0.2650, 0.2909] |
| `L1_misspec_omit_new_channel` | 30 | 0.2779 | 0.0361 | 0.0066 | [0.2650, 0.2909] |
| `L1_signal_weak` | 30 | 0.2775 | 0.0363 | 0.0066 | [0.2645, 0.2905] |
| `L2_composition_shift` | 30 | 0.3981 | 0.0379 | 0.0069 | [0.3845, 0.4117] |
| `L2_drift_smooth` | 30 | 0.3413 | 0.0406 | 0.0074 | [0.3268, 0.3558] |
| `L2_immature_negative_control` † | 30 | 0.2817 | 0.0383 | 0.0070 | [0.2679, 0.2954] |
| `L2_n100000_p050` | 30 | 0.2897 | 0.0440 | 0.0080 | [0.2740, 0.3055] |
| `L2_n30000_p050` | 30 | 0.2721 | 0.0759 | 0.0138 | [0.2449, 0.2992] |
| `L3_fixed_lt025` | 30 | 1.8451 | 0.0445 | 0.0081 | [1.8292, 1.8610] |
| `L3_fixed_lt075` | 30 | 2.0932 | 0.0456 | 0.0083 | [2.0769, 2.1096] |
| `L3_fixed_lt150` | 30 | 2.2291 | 0.0421 | 0.0077 | [2.2140, 2.2442] |
| `L3_joint_lam000` | 30 | 1.6681 | 0.0519 | 0.0095 | [1.6495, 1.6867] |
| `L3_joint_lam150` | 30 | 3.9436 | 0.0477 | 0.0087 | [3.9265, 3.9606] |
| `L3_missing_confounders` | 30 | 1.6600 | 0.0412 | 0.0075 | [1.6453, 1.6748] |
| `L3_overlap_extreme` | 30 | 3.1372 | 0.0507 | 0.0093 | [3.1190, 3.1553] |

† `L2_immature_negative_control`：机制键未接线，不构成有效机制证据（见 §3.0）。

#### 3.2 检验统计量（同 rep 配对）（`ate_test`）

**Tier1 core（4 格，R=500）**

| 格 | R | mean | sd | MC SE | 95% CI（±1.96×MC SE） |
|---|---:|---:|---:|---:|---|
| `L0_P_main` | 500 | 0.2434 | 0.0737 | 0.0033 | [0.2369, 0.2498] |
| `L1_main` | 500 | 0.2851 | 0.0848 | 0.0038 | [0.2777, 0.2926] |
| `L2_n200000_p050` | 500 | 0.2877 | 0.0841 | 0.0038 | [0.2803, 0.2950] |
| `L3_fixed_lt000` | 500 | 1.6638 | 0.0848 | 0.0038 | [1.6564, 1.6712] |

**Tier2 选中格（20 格，R=30；不与 Tier1 并列排序）**

| 格 | R | mean | sd | MC SE | 95% CI（±1.96×MC SE） |
|---|---:|---:|---:|---:|---|
| `L0_Pi_heterogeneous_cost` | 30 | 0.4371 | 0.0624 | 0.0114 | [0.4148, 0.4594] |
| `L0_zero_purchase_effect` | 30 | -0.5737 | 0.0762 | 0.0139 | [-0.6010, -0.5464] |
| `L1_cost_prediction_under` | 30 | 0.2797 | 0.0884 | 0.0161 | [0.2481, 0.3114] |
| `L1_heterogeneity_000` | 30 | 0.2031 | 0.0809 | 0.0148 | [0.1741, 0.2321] |
| `L1_heterogeneity_150` | 30 | 0.2696 | 0.0807 | 0.0147 | [0.2407, 0.2984] |
| `L1_mar_double` | 30 | 0.2758 | 0.0750 | 0.0137 | [0.2490, 0.3027] |
| `L1_misspec_omit_new_channel` | 30 | 0.2633 | 0.0828 | 0.0151 | [0.2336, 0.2929] |
| `L1_signal_weak` | 30 | 0.2898 | 0.0847 | 0.0155 | [0.2595, 0.3201] |
| `L2_composition_shift` | 30 | 0.5867 | 0.0841 | 0.0153 | [0.5566, 0.6168] |
| `L2_drift_smooth` | 30 | -0.0489 | 0.0889 | 0.0162 | [-0.0807, -0.0171] |
| `L2_immature_negative_control` | 30 | 0.2920 | 0.0896 | 0.0164 | [0.2599, 0.3240] |
| `L2_n100000_p050` | 30 | 0.2883 | 0.1274 | 0.0233 | [0.2427, 0.3339] |
| `L2_n30000_p050` | 30 | 0.3040 | 0.2260 | 0.0413 | [0.2231, 0.3848] |
| `L3_fixed_lt025` | 30 | 1.8428 | 0.0739 | 0.0135 | [1.8164, 1.8693] |
| `L3_fixed_lt075` | 30 | 2.0860 | 0.0684 | 0.0125 | [2.0615, 2.1104] |
| `L3_fixed_lt150` | 30 | 2.2121 | 0.0855 | 0.0156 | [2.1815, 2.2427] |
| `L3_joint_lam000` | 30 | 1.6964 | 0.0914 | 0.0167 | [1.6637, 1.7291] |
| `L3_joint_lam150` | 30 | 3.9471 | 0.1126 | 0.0206 | [3.9068, 3.9873] |
| `L3_missing_confounders` | 30 | 1.6515 | 0.0672 | 0.0123 | [1.6275, 1.6756] |
| `L3_overlap_extreme` | 30 | 3.1458 | 0.1020 | 0.0186 | [3.1092, 3.1823] |

#### 3.3 7 日付费购买率效应（`ate_paid_purchase_7d`）

**Tier1 core（4 格，R=500）**

| 格 | R | mean | sd | MC SE | 95% CI（±1.96×MC SE） |
|---|---:|---:|---:|---:|---|
| `L0_P_main` | 500 | 0.0500 | 0.0014 | 0.0001 | [0.0499, 0.0501] |
| `L1_main` | 500 | 0.0501 | 0.0014 | 0.0001 | [0.0499, 0.0502] |
| `L2_n200000_p050` | 500 | 0.0501 | 0.0014 | 0.0001 | [0.0500, 0.0502] |
| `L3_fixed_lt000` | 500 | 0.0822 | 0.0015 | 0.0001 | [0.0821, 0.0823] |

**Tier2 选中格（20 格，R=30；不与 Tier1 并列排序）**

| 格 | R | mean | sd | MC SE | 95% CI（±1.96×MC SE） |
|---|---:|---:|---:|---:|---|
| `L0_Pi_heterogeneous_cost` | 30 | 0.0502 | 0.0014 | 0.0003 | [0.0497, 0.0506] |
| `L0_zero_purchase_effect` | 30 | 0.0001 | 0.0014 | 0.0003 | [-0.0004, 0.0006] |
| `L1_cost_prediction_under` | 30 | 0.0501 | 0.0015 | 0.0003 | [0.0496, 0.0507] |
| `L1_heterogeneity_000` | 30 | 0.0501 | 0.0015 | 0.0003 | [0.0495, 0.0506] |
| `L1_heterogeneity_150` | 30 | 0.0501 | 0.0015 | 0.0003 | [0.0496, 0.0507] |
| `L1_mar_double` | 30 | 0.0501 | 0.0015 | 0.0003 | [0.0496, 0.0507] |
| `L1_misspec_omit_new_channel` | 30 | 0.0501 | 0.0015 | 0.0003 | [0.0496, 0.0507] |
| `L1_signal_weak` | 30 | 0.0501 | 0.0015 | 0.0003 | [0.0496, 0.0507] |
| `L2_composition_shift` | 30 | 0.0547 | 0.0015 | 0.0003 | [0.0541, 0.0552] |
| `L2_drift_smooth` | 30 | 0.0533 | 0.0018 | 0.0003 | [0.0526, 0.0539] |
| `L2_immature_negative_control` | 30 | 0.0498 | 0.0017 | 0.0003 | [0.0493, 0.0504] |
| `L2_n100000_p050` | 30 | 0.0500 | 0.0022 | 0.0004 | [0.0492, 0.0508] |
| `L2_n30000_p050` | 30 | 0.0497 | 0.0036 | 0.0007 | [0.0484, 0.0510] |
| `L3_fixed_lt025` | 30 | 0.0912 | 0.0015 | 0.0003 | [0.0906, 0.0917] |
| `L3_fixed_lt075` | 30 | 0.1052 | 0.0013 | 0.0002 | [0.1048, 0.1057] |
| `L3_fixed_lt150` | 30 | 0.1159 | 0.0014 | 0.0003 | [0.1154, 0.1164] |
| `L3_joint_lam000` | 30 | 0.0816 | 0.0015 | 0.0003 | [0.0811, 0.0821] |
| `L3_joint_lam150` | 30 | 0.2115 | 0.0015 | 0.0003 | [0.2110, 0.2120] |
| `L3_missing_confounders` | 30 | 0.0821 | 0.0014 | 0.0002 | [0.0816, 0.0826] |
| `L3_overlap_extreme` | 30 | 0.1167 | 0.0014 | 0.0003 | [0.1162, 0.1172] |

#### 3.4 30 日任一退款率效应（`ate_any_refund_30d`）

**Tier1 core（4 格，R=500）**

| 格 | R | mean | sd | MC SE | 95% CI（±1.96×MC SE） |
|---|---:|---:|---:|---:|---|
| `L0_P_main` | 500 | 0.0042 | 0.0005 | 0.0000 | [0.0042, 0.0042] |
| `L1_main` | 500 | 0.0042 | 0.0005 | 0.0000 | [0.0042, 0.0043] |
| `L2_n200000_p050` | 500 | 0.0042 | 0.0005 | 0.0000 | [0.0042, 0.0043] |
| `L3_fixed_lt000` | 500 | 0.0068 | 0.0004 | 0.0000 | [0.0067, 0.0068] |

**Tier2 选中格（20 格，R=30；不与 Tier1 并列排序）**

| 格 | R | mean | sd | MC SE | 95% CI（±1.96×MC SE） |
|---|---:|---:|---:|---:|---|
| `L0_Pi_heterogeneous_cost` | 30 | 0.0043 | 0.0005 | 0.0001 | [0.0042, 0.0045] |
| `L0_zero_purchase_effect` | 30 | 0.0003 | 0.0004 | 0.0001 | [0.0002, 0.0005] |
| `L1_cost_prediction_under` | 30 | 0.0041 | 0.0004 | 0.0001 | [0.0040, 0.0043] |
| `L1_heterogeneity_000` | 30 | 0.0042 | 0.0004 | 0.0001 | [0.0040, 0.0043] |
| `L1_heterogeneity_150` | 30 | 0.0041 | 0.0004 | 0.0001 | [0.0040, 0.0043] |
| `L1_mar_double` | 30 | 0.0041 | 0.0004 | 0.0001 | [0.0040, 0.0043] |
| `L1_misspec_omit_new_channel` | 30 | 0.0041 | 0.0004 | 0.0001 | [0.0040, 0.0043] |
| `L1_signal_weak` | 30 | 0.0041 | 0.0004 | 0.0001 | [0.0040, 0.0043] |
| `L2_composition_shift` | 30 | 0.0046 | 0.0004 | 0.0001 | [0.0044, 0.0047] |
| `L2_drift_smooth` | 30 | 0.0045 | 0.0004 | 0.0001 | [0.0043, 0.0046] |
| `L2_immature_negative_control` | 30 | 0.0042 | 0.0004 | 0.0001 | [0.0041, 0.0044] |
| `L2_n100000_p050` | 30 | 0.0043 | 0.0005 | 0.0001 | [0.0041, 0.0045] |
| `L2_n30000_p050` | 30 | 0.0044 | 0.0011 | 0.0002 | [0.0040, 0.0048] |
| `L3_fixed_lt025` | 30 | 0.0075 | 0.0005 | 0.0001 | [0.0073, 0.0077] |
| `L3_fixed_lt075` | 30 | 0.0086 | 0.0005 | 0.0001 | [0.0084, 0.0088] |
| `L3_fixed_lt150` | 30 | 0.0094 | 0.0006 | 0.0001 | [0.0092, 0.0096] |
| `L3_joint_lam000` | 30 | 0.0066 | 0.0005 | 0.0001 | [0.0065, 0.0068] |
| `L3_joint_lam150` | 30 | 0.0170 | 0.0005 | 0.0001 | [0.0168, 0.0171] |
| `L3_missing_confounders` | 30 | 0.0068 | 0.0006 | 0.0001 | [0.0066, 0.0070] |
| `L3_overlap_extreme` | 30 | 0.0095 | 0.0005 | 0.0001 | [0.0093, 0.0097] |

**不做覆盖率（但真值文件其实在盘上）**：逐 rep 的 `freeze.json` 写 `truth_columns_present: false`，
含义是**冻结决策表（policy_list/decision/guardrail）在写盘时不含真值**，不是"真值未落盘"——
freeze 之后 `run_validation_arm` 确实写出 `truth_users.csv`（`user_id/tau_true/cost_true`）、
`truth_policy_values.csv`、`truth_arm_means.csv`、`truth_arm_contrasts.csv`。
G03 的注册分析（`repetitions.csv` 四指标 + 汇总）**没有**覆盖率的统计量与校验，
因此报告**不得**声称"95% CI 覆盖真值 X%"；若要做覆盖率，必须把它作为**新增注册分析**，
基于 `truth_*` 逐 rep 重算并单列，不得混入本轮已注册的四个指标。

### 3.0 必须随表发布的披露（D1-A，2026-10-29 22:52 裁决）

`L2_immature_negative_control` 的开关 `dgp.l2.include_immature_analysis_control`
**没有被源码读取**，因此该格实际跑的 DGP 与 `L2_n200000_p050` 相同：**30 个 rep 的四个指标与验证数值
逐位相同**（只有 `config_hash` / `observed_hash` / `validation_freeze_hash` / `preprocessor_hash` /
`split_fingerprint` 这类 cell/run 身份字段不同，逐 rep 行并非逐字节相同）。rep 0 的
`fixed_bootstrap.csv` 在两格目录下是同一份文件：md5 同为 `69da7f4a…`、sha256 同为
`4f7a7b790c8a38efe9f637fcfa84d86b084a0f7ccb50ba5f6365f50be34a65b2`；该文件现已作为
`per_cell/rep0_fixed/<cell>__fixed_bootstrap.csv` 导出，摘要可复算。
**该格不构成有效机制证据**，不得作为"年幼用户分析控制"这一机制的检验结果引用；
它只保留在 20 格矩阵里充当"重复跑一致"的完整性检查。

三条纪律，随表一起发布：

1. 不得进摘要（H04 摘要只准 Tier1 注册值）；
2. 不得与 `L2_n200000_p050` 并列当作两条独立证据（同一 DGP）；
3. 若要让它真正生效，属**新增注册分析**（改绑定源码 + 重跑），不在本轮已批准的 20 格范围内；
   同理 `models.train_fraction_of_training_pool` 在 3 个 `L1_learning_*` 格上同样空转（不在 24 格内），
   将来启用前必须先接线。

### 3.5 指标敏感性披露与选模分布（2026-10-31 19:44 评审核实后补）

四个注册汇总指标（`ate` / `ate_test` / `ate_paid_purchase_7d` / `ate_any_refund_30d`）都是
**设计型 ITT 对比**（`v3_g_matrix.estimate_ate`：全样本均值差、test 子集均值差、两个比例差），
不经过任何学习模型。因此**只改协变量、缺失/清洗或模型输入的机制，在这四个指标上构造不变**。
对 rep0–29 的逐 rep 向量做哈希核对，存在以下等价组：

- `ate` 完全相同：{`L1_cost_prediction_under`, `L1_main`, `L1_mar_double`,
  `L1_misspec_omit_new_channel`}；{`L3_fixed_lt000`, `L3_missing_confounders`}；
  {`L2_immature_negative_control`, `L2_n200000_p050`}（后者即 §3.0 的 D1-A）；
- `ate_paid_purchase_7d` 与 `ate_any_refund_30d` 完全相同：{`L0_P_main`, `L0_Pi_heterogeneous_cost`}；
  上述 4 个 L1 格 + `L1_signal_weak`（共 5 个 L1 格）；{`L3_fixed_lt000`, `L3_missing_confounders`}；D1-A 两格。

这些机制的差异出现在 `ate_test`（验证划分/子集随清洗变化）、`model_*_tau_*`、`chosen_model`
与 fixed bootstrap。例：`L3_missing_confounders` 与 `L3_fixed_lt000` 的 `ate` 相同，但 rep0–29 的 `ate_test`
最大差 **0.1931**，选模分布也不同（见下表）。
**读法**：§3.1 的 20 行不是"20 个机制对 ITT 的独立效应"；对建模层机制，判别信息在 §3.2、
选模分布与 §4，不得用 §3.1 的行间差异论证机制效应。

**选模分布（`chosen_model`：Tier2 = rep0–29；core = rep0–99 学习段）**

> core 4 格的 R 为 500，但 `chosen_model` 只在 rep0–99 的学习/验证段有值，故这 4 行计数总和为 100；
> Tier2 行计数总和为 30。不要把本表的计数总和与 §3.1 的 R=500/30 混读。

| 格 | R | constant | t_learner | s_learner | causal_forest | dr_learner |
|---|---:|---:|---:|---:|---:|---:|
| `L0_P_main` | 500 | 5 | 26 | 31 | 38 | 0 |
| `L0_Pi_heterogeneous_cost` | 30 | 10 | 4 | 8 | 8 | 0 |
| `L0_zero_purchase_effect` | 30 | 30 | 0 | 0 | 0 | 0 |
| `L1_cost_prediction_under` | 30 | 1 | 1 | 9 | 19 | 0 |
| `L1_heterogeneity_000` | 30 | 8 | 2 | 7 | 9 | 4 |
| `L1_heterogeneity_150` | 30 | 0 | 1 | 8 | 20 | 1 |
| `L1_main` | 500 | 2 | 6 | 25 | 62 | 5 |
| `L1_mar_double` | 30 | 3 | 0 | 8 | 17 | 2 |
| `L1_misspec_omit_new_channel` | 30 | 1 | 2 | 7 | 18 | 2 |
| `L1_signal_weak` | 30 | 3 | 1 | 12 | 12 | 2 |
| `L2_composition_shift` | 30 | 0 | 2 | 6 | 22 | 0 |
| `L2_drift_smooth` | 30 | 1 | 0 | 8 | 21 | 0 |
| `L2_immature_negative_control` | 30 | 0 | 0 | 5 | 25 | 0 |
| `L2_n100000_p050` | 30 | 4 | 4 | 7 | 15 | 0 |
| `L2_n200000_p050` | 500 | 0 | 1 | 33 | 66 | 0 |
| `L2_n30000_p050` | 30 | 15 | 3 | 4 | 8 | 0 |
| `L3_fixed_lt000` | 500 | 8 | 15 | 25 | 45 | 7 |
| `L3_fixed_lt025` | 30 | 0 | 3 | 7 | 14 | 6 |
| `L3_fixed_lt075` | 30 | 2 | 4 | 9 | 11 | 4 |
| `L3_fixed_lt150` | 30 | 0 | 3 | 5 | 18 | 4 |
| `L3_joint_lam000` | 30 | 3 | 5 | 7 | 10 | 5 |
| `L3_joint_lam150` | 30 | 0 | 2 | 2 | 23 | 3 |
| `L3_missing_confounders` | 30 | 3 | 5 | 11 | 9 | 2 |
| `L3_overlap_extreme` | 30 | 11 | 6 | 4 | 5 | 4 |

`dr_learner` 在 L0 格为 0 属预期（该模型不适用于 L0，执行器按层过滤）；`L0_zero_purchase_effect`
**30/30 选 `constant`**，其 §4 点差 +0.0765（CI 跨零）是"不做差异化"的策略值，**不是定向能力证据**。

## 4. 固定 bootstrap 结果（Stage A 已于 18:37 完成；19:46 填表）

数据源：`out/g02_fixed/shards/<cell>_s0000/<cell>/rep0/validation/fixed_bootstrap.csv`（24 格）；
本文数字的唯一来源是 `outputs/tables/v3_g03_fixed_bootstrap_summary.csv`（`scripts/47_g03_fixed_report.py` 生成，
逐格断言"单行 / 预算 0.2 / 重抽 1 000"，实际预算恒 0.2、`resamples` 恒 1 000）；
Stage A 完成后由 41 号导出为 `outputs/evidence/g03_formal/fixed_bootstrap.csv`。
固定臂 `runs/fixed_run_summary.json` 的 `all_complete=false` **属预期**：每格只跑 rep 0，
而 `R_ate=500`；该 summary 只用于证明 `status=formal`、`failures=[]`。

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


## 5. 证据与复现

- **证据包内容（2026-10-31 20:01 收尾后重导出，357 条记录 / 5 254 002 B）**：264 个分片原件（132 个分片 ×
  repetitions + telemetry）、24 份合并逐 rep 表、24 份 rep0 manifest、24 份 rep0 固定 bootstrap
  （`per_cell/rep0_fixed/`）、1 份 24 格合并固定 bootstrap 表（`fixed_bootstrap.csv`，
  kind `g02_fixed_bootstrap_merged`）、11 份日志/状态（阶段 A 4 件 + Phase 1/2 + finalize + 49）、
  3 份源 `run_summary.json`、2 份汇总表、2 份臂 summary、快照绑定与复算汇总各 1 份；
  目录级索引 `outputs/evidence/g03_formal/coverage.json` 的 357 条 target **全部唯一**，
  逐条 sha256/bytes 与磁盘一致（**0 条不符**）。**2026-10-31 19:44 评审的 P0-1**：上一版用
  `run.name`（恒等于格名）命名分片，264 条记录塌陷到 48 个文件、216 条不符；现改为
  `run.parent.name`，并在导出结束时自检"target 唯一 / 逐条 sha / 文件数=记录数"；
- **门禁加强**（AGENTS §12.3）：`scripts/33_register_evidence_top.py` 原先只对身份类 JSON 重算
  sha/bytes，现对**目录级索引的全表**逐条核对，并把"同一 target 被多条记录登记"判为失败。
  反例实测（旧台账）：**RC=2，48 个重名 target + 216 条不符**；修复后 dry-run rc=0。
  仓外绝对路径记录（如 f01_ope 的 `in_repository:false` 派生件）按**原绝对路径**核 sha/bytes
  （2026-10-31 20:00 修独立复核 N2：旧实现按 `evidence_dir/<basename>` 误报"文件缺失"，默认全目录
  dry-run 曾 rc=2）；33 与 41 两道校验的 16 例反例夹具见
  `tests/test_v3_evidence_registry_guards.py`（AGENTS §12.7）；
- `scripts/41_export_g03_evidence.py --check`：24 格逐 rep 表齐全、逐格契约列、固定 bootstrap 24 格
  （预算恒 0.2 / 次数恒 1000）、复算汇总 4 指标 × 24 格 = 96 行并与 `outputs/tables/v3_g_g_{core,tier2}.csv`
  对账、两个根的 `run_summary.json` 均 `status=formal` 且 `failures=[]`、`bootstrap_resamples` 分别为
  0（矩阵）与 1000（固定）→ 全过后才导出 → `scripts/33_register_evidence_top.py --dirs g03_formal`；
  **矩阵根的 `run_summary.json` 是合成的**：`34 merge` 只写 `merge_report.json`（且落在 `roots[0]`），
  故 51 号末尾新增 exit 12 步，把三份源 summary（core_prefix / tier2 / core_ate，各自校验 formal、
  无 failures、resamples=0）与本复合根**原始分片**合成一份 `{status: formal, composite: true,
  derived_from: […sha256], shard_rows: …}`；分片侧独立核对 24 格各 500/30 行、rep 恰为 0..R-1、
  跨分片无重复、无未注册格、无 provisional，任一不符即非零退出。该步不读 `merge_report`——junction
  回退成 `cp -r` 时报告会出现多份，读它反而脆（2026-10-30 00:39 预检发现，7 例夹具演练见日志）；
  三份源 summary 现已随证据包导出（`runs/phase1_core_prefix_run_summary.json` 等），
  `derived_from` 的 sha256 可只用 `outputs/evidence/` 复算；
- **逐 rep 表契约列**（41 号 `check_cell`，2026-10-29 11:20 修）：`rep / status / protocol_config_hash /
  block / tier / n / n_treated / n_control / validation_bootstrap_resamples` 缺一即失败；列名是 `n`
  **不是** `n_total`（矩阵行 schema 无后者，旧写法在首格完整帧上必 `KeyError`）；另断言
  `n_treated + n_control == n`、`rep` 为 `0..R-1` 的排列、`status/block/tier/n` 逐格唯一。
  该修复**不触及源码哈希**（`scripts/` 不在 `pipeline_source_hashes` 内），可在运行期落地；
- **overlay 不在哈希账上**：`configs/budget/tier2_overlay.yaml`（`02644767…`）与 G02 的
  `g02_bootstrap_overlay.yaml` 都会被 `create_snapshot` 整树复制进快照目录，但
  `snapshot_binding.source_hashes`（49 文件）只记 v3 集；`34 --snapshot` 也只校验"绑定 vs live 相等"，
  不切换运行根。本次保护 = 冻结窗口 + 两文件运行期未改（收尾以 sha256/mtime 复核，记入 G04）；
- **导出与登记**：导出为 staging + 原子换名，旧目录保留时间戳备份（`%Y%m%d%H%M%S`）；
  顶层登记已于 **2026-10-31 19:36:46** 执行（93 条 / 16 975 748 B，其中 G03 只占 1 条
  `g03_snapshot_binding`，其余 G03 记录在目录级索引）。两次重导出的收尾链 33 dry-run 均为
  `--dirs g02_formal g03_formal`（19:48、20:01）rc=0；**默认全目录**扫描在 N2 修复后为 rc=0
  （2026-10-31 20:01 主负责实跑、20:11 独立复验复跑：12 子目录 / 42 候选全已登记 / 93 条幂等），
  无新增身份类文件，顶层保持 93 条幂等。注意历史陈述不能写成“19:48/20:01 的 dry-run 已含默认全目录”，
  那两次只扫了 2 个子目录；20:01 的 66 号脚本只调 41 导出、未调 33。

**finalize 日志的闭合时点（2026-10-31 20:01 修 N1）**：63 的 3/5 步调用 41 导出时，
`finalize.log/status` 尚未闭合，证据包里曾停在 3/5（211 行 / 26 B）。现改为收尾完成后运行
`scripts/66_g03_refresh_evidence_logs.sh`（2026-10-31 20:01:53 实跑 rc=0）：先在 `finalize.log`
末尾追加 6/6 行，再全量导出；证据包中的 `finalize.log/status` 与 `out/g03_logs/` 逐字节相同
（240 行 vs 240 行、140 B vs 140 B），含 6 个 exit 与
`OK: G03 finalize 完成 2026-10-31 19:48:27`。49 日志亦在收尾后重跑（RC=0 READY）并重导出。

**重导出 rc 的留痕边界（P3-5）**：20:01 重导出自身的 rc 只写在 `out/g03_logs/post_finalize_export.status`
（`out/` 不入库）；证据包内存的是 `finalize.log` 的 6/6 标记行与 `coverage.json`
（`generated_at 20:02:02`、357 条 / 5 254 002 B），足以用复算证明重导出成功且记录自洽。
N2 的“默认全目录 rc=0”在仓库内同样没有日志，由 2026-10-31 20:11 独立复验报告
`docs/reviews/v3_phase_G03_recheck2.md` §2.2 的实跑记录承担。若要求“连 rc 也可从证据包复算”，
需把 `post_finalize_export.log` 纳入第 12 份日志重导出（会换 coverage 指纹，本轮不做）。

**binding 的 `git_commit` 为 null（如实保留，P3-4）**：`binding/snapshot_binding.json` 建立快照时
未回填 commit；绑定身份以 49 文件 `source_hashes` 为准，**无法从 binding 回到 commit**。
不回填是因为回填会改变绑定文件哈希；引用时请用 `source_hashes` 与 git 树比对，不要假定
`git_commit` 可用。

**复现命令**（只读；不会重跑任何 rep）：

```bash
PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/41_export_g03_evidence.py --check
PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g03_formal --dry-run
PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/62_g04_tamper_drill.py
PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/49_g04_closeout_precheck.py --with-check --with-register --with-claims
```

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
8. **注册指标对建模层机制不敏感**：四个汇总指标都是设计型 ITT（全样本/test 子集均值差、两个比例差），
   不经过学习模型；只改协变量、缺失/清洗或模型输入的机制在 `ate` 与两个比例上**构造不变**
   （等价组见 §3.5）。对这些机制只能看 `ate_test`、`model_*`、选模分布与 fixed bootstrap，
   不能把 §3.1 的行间比较当作机制效应。

## 7. 判定边界

"通过"只表示：**24 格跑满注册 R、记录准确、断言范围正确、证据可复算**。
不表示定向策略在真实业务有效、不表示 Tier2 全 65 格已覆盖、不表示结果可部署；
也不表示 §3.1 的每个格子在四个 ITT 指标上提供了独立信息（见 §3.5 的等价组）。
