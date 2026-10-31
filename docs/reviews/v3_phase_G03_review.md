# G03 正式结果（Tier2 20 格 + Tier1 core 4 格）—— 独立评审

> **评审时间：2026-10-31 19:44（北京时间；`date '+%F %T %z'` 读数 `2026-10-31 19:44:17 +0800`，本机时区即 UTC+8）**。
> 身份：**独立评审代理**，此前未参与 G03 任何设计与产出，也未参与本轮 §2/§3 填报。
> 被审 commit：`5f7f9fd 2026-10-31 19:38:32  G03|fix: 41 导出 target 重挂最终路径；33 实登记 93 条；§2/§3/§5 收口`
> （工作树另有 3 个未提交改动：`AGENT_HANDOFF.md`、`TODO.md`、`docs/v3_决策与反思日志.md`；**不含**被审报告，被审报告字节等于 HEAD）。
> 纪律：全程只读；除本文件外未写任何文件；未修改源码/配置/证据/报告；未运行 34/39/41/51/63 等作业模式；
> 未装包、未跑 pytest、未 `git commit`。`out/` 下**只读**了日志、`*.status` 与三份源 `run_summary.json`（为核 `derived_from` 的 sha256，见 §6），未读分片数据、未改任何字节。
> 本文件 UTF-8、LF 行尾。

**结论：`PASS WITH CONDITIONS`**（0 项结果层错误；1 项 P0 证据登记错误、3 项 P1、3 项 P2、5 项 P3）。
含义：§3/§4 的 **全部 96 + 24 个数字经我独立复算 0 误差**、R 与完整性成立、D1-A 披露成立；
但**证据登记表 323 条记录里有 216 条的内容与磁盘不符**（§7 P0-1），该问题不使任何数字作废，却使
`outputs/evidence/` 的"分片原件可核"这一层证据失效，且当前所有门禁都放行了它。修完 P0-1 与 P1 后建议改判"通过"。

**本评审只看记录准确、断言范围与证据可复算；不判断机制在真实业务是否成立、不判断估计量本身的统计正确性。**

---

## §0 范围与未覆盖项

**覆盖**：`docs/v3_phase_G03_formal.md` 全文（§1–§7）；`outputs/evidence/g03_formal/`（coverage/per_cell/summary/fixed_bootstrap/recomputed_summary/runs/manifests/binding/logs）；
`outputs/tables/v3_g_g_{core,tier2}.csv`、`outputs/tables/v3_g03_fixed_bootstrap_summary.csv`；顶层 `outputs/evidence/coverage.json`；
`out/g03_logs/{phase1,phase2,finalize}.{log,status}`（只读）；`scripts/41`、`scripts/33` 的读码（只读，定位 P0-1 根因）。

**未覆盖（不作判断）**：
1. DGP 机制语义是否实现正确、`include_immature` 之外是否还有未接线的键（只核实了报告已披露的那一个）；
2. 估计量本身的正确性（`ate` / `ate_test` 的定义与实现、协变量调整方式）——我只按报告的公式（样本 sd、`MC_SE=sd/√R`、`mean±1.96×MC_SE`）复算了**同一组逐 rep 数**；
3. 覆盖率（本轮未注册，报告也明确不作此类断言）；
4. 真实业务效果、可部署性；
5. 其余 45 个未跑格、H04 claim 注册、长稿引用；
6. 不可从证据包核实的项：§3.0 的 rep0 `fixed_bootstrap.csv` md5/sha256 字符串（`69da7f4a…`/`4f7a7b79…`，见 P2-3）、11:14 冒烟的 `EXIT=2`、§5 提到的"7 例夹具演练"（日志未导出，见 P1-3）、49 号的**退出码**（只有日志文本 `[VERDICT] READY`）。

---

## §1 独立复算表（任务要求 ≥6 格，实际全查 24 格 × 4 指标 = 96 行）

主指标 `ate`；"我的"列由 `per_cell/*__repetitions.csv` 原始列直接算（pandas `std(ddof=1)`、`MC_SE=sd/√R`），
"表内"列取自 `outputs/tables/v3_g_g_{core,tier2}.csv`，"报告"列是 `docs/v3_phase_G03_formal.md` §3.1 的 4 位小数排版。

| 格 | R | 我的 mean | 表内 mean | 报告 §3.1 | 差 | 我的 sd | 表内 sd | 我的 MC_SE | 表内 MC_SE | 一致 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `L0_P_main` | 500 | 0.2434178407 | 0.2434178407 | 0.2434 | **0.0** | 0.0386246326 | 0.0386246326 | 0.0017273461 | 0.0017273461 | 是 |
| `L1_main` | 500 | 0.2831491913 | 0.2831491913 | 0.2831 | **0.0** | 0.0455119195 | 0.0455119195 | 0.0020353549 | 0.0020353549 | 是 |
| `L2_n200000_p050` | 500 | 0.2877580333 | 0.2877580333 | 0.2878 | **0.0** | 0.0441488593 | 0.0441488593 | 0.0019743970 | 0.0019743970 | 是 |
| `L3_fixed_lt000` | 500 | 1.6641251572 | 1.6641251572 | 1.6641 | **0.0** | 0.0458243624 | 0.0458243624 | 0.0020493278 | 0.0020493278 | 是 |
| `L3_joint_lam150`（抽） | 30 | 3.9435722920 | 3.9435722920 | 3.9436 | **0.0** | 0.0477015641 | 0.0477015641 | 0.0087090742 | 0.0087090742 | 是 |
| `L2_immature_negative_control`（抽） | 30 | 0.2816586413 | 0.2816586413 | 0.2817 | **0.0** | 0.0383201570 | 0.0383201570 | 0.0069962715 | 0.0069962715 | 是 |

**全量结果**（96 行 = 24 格 × 4 指标：`ate` / `ate_test` / `ate_paid_purchase_7d` / `ate_any_refund_30d`）：

- `max |Δmean| = 0.0`、`max |Δsd| = 0.0`、`max |ΔMC_SE| = 0.0`；R 全部相符；无 NaN；`provisional` 全 `False`；
- 报告 §3 四张表的 **96 行 × 6 个字段**（R / mean / sd / MC_SE / CI 下限 / CI 上限）逐行比对：**96/96 通过**
  （容差 5e-5 于 mean/sd/SE、1.05e-4 于 CI，仅吸收 4 位小数排版；CI 复算式 `mean ± 1.96×MC_SE` 与报告口径一致）；
- `outputs/evidence/g03_formal/recomputed_summary.csv` 与我的复算 **96/96 行完全相同**（`max |Δ| = 0`）；
- `outputs/evidence/g03_formal/summary/v3_g_g_{core,tier2}.csv` 与 `outputs/tables/` 同名文件 **sha256 相同**（逐字节）。

---

## §2 R 与完整性（逐格独立统计）

| 项 | 我的统计 | 报告声明 | 判定 |
|---|---|---|---|
| core 4 格 | 各 500 行，rep = 0..499，无重复、无缺号 | 500（§1、§3） | 相符 |
| Tier2 20 格 | 各 30 行，rep = 0..29，无重复、无缺号 | 30（§1、§3） | 相符 |
| 总行数 | 2 600（2 000 + 600） | 24 格、96 指标行 | 相符 |
| `provisional` | 24 格全部 `False` | `provisional=False`（§3） | 相符 |
| `status` / `block` / `tier` | 逐格唯一，`formal` / `g_core|g_tier2` / 1|2 | 正式、tier 1/2 | 相符 |
| `n_treated + n_control == n` | 24 格残差最大 **0.0** | 41 号契约列断言（§5） | 相符 |
| `n` | core 与多数 Tier2 = 200 000；`L2_n100000_p050` = 100 000；`L2_n30000_p050` = 30 000 | 与格名一致 | 相符 |
| 学习/验证前缀 | core `rep 0–99` 的 `learning_prefix=True`、`validation_pipeline_builds=1`；`rep 100–499` 为 `False`/`0`；Tier2 30 行全 `True` | §1「core R_ate=500（学习/验证 100）」、§2「rep100–499 只出 ATE」 | 相符 |
| 固定流一致性 | 24 格 `protocol_config_hash` 均 `00723dc2…`；`overlay_sha256` 均 `02644767…` | §1 快照/overlay | 相符 |

---

## §3 固定 bootstrap（§4）

- `fixed_bootstrap.csv`：**24 行 = 24 格**，`rep` 恒 0，`resamples` 恒 **1 000**，`budget_cny_per_user` 恒 **0.2**，无重复格；
- 报告 §4.1/§4.2 的 **24 行 × 6 字段**（n_targeted / n_random / 点差 / SE / CI 上下限）与 CSV 逐行比对：**24/24 通过**（容差 6e-5，吸收 4 位小数）；
  "CI 跨零"列 24/24 与复算一致；`ci_width`（表 25 行）与 `ci_high-ci_low` 最大误差 **0.0**；
- 小计复算：core 跨零 **2/4**（`L0_P_main`、`L3_fixed_lt000`）、Tier2 跨零 **4/20**（`L0_zero_purchase_effect`、`L1_heterogeneity_000`、`L2_n100000_p050`、`L2_n30000_p050`）、
  点差为正 **23/24**（唯一负值 `L0_Pi_heterogeneous_cost`）、core 中位半宽 **0.105822 → 0.1058**、`L2_n100000`/`L2_n30000` 半宽 **0.1499 / 0.2925 → 0.150 / 0.293** —— 与报告 §4 的每一句相符；
- `outputs/tables/v3_g03_fixed_bootstrap_summary.csv`（25 行）与证据 CSV **24/24 行完全对得上**（`tier` 4/20，`ci_covers_zero`、`ci_width` 自洽）；
- 证据边界：`fixed_run_summary.json` 的 `all_complete=false` 属预期（每格只有 rep 0、`R_ate=500`），报告未写这句，但不构成错误（见 P3-5）。

---

## §4 D1-A 披露（任务重点项）

**我的核实（不引用报告数字）**：

1. 对 `per_cell/L2_immature_negative_control__repetitions.csv`（30 行）与 `L2_n200000_p050__repetitions.csv` 前 30 行逐列比较：
   **40 个数值列中 39 列 `max|Δ| = 0`**，唯一非零是 `tier`（1 vs 2）。即 `ate` / `ate_test` / `ate_paid_purchase_7d` / `ate_any_refund_30d`
   及全部 `model_*_tau_*`、`validation_*` 数值**逐位相同**，覆盖全部 30 个 rep（不只 rep 0）。
2. `observed_hash_without_run_id` 在两格内 30 行同值、跨格也相同 = `fa2e993a6dc2754884bb75a96ef4e8cf0c7afe37bb12f61f79877404409dba08`（与报告 §4.2 写的 `fa2e993a…` 一致）。
3. 两份 rep0 manifest 的 `fixed_bootstrap` 子字典**逐字段相同**（n 66 594 / 66 713、点差 0.17878778118700245、SE 0.054888298408759646、CI [0.07404316980434475, 0.28516629073003014]）。
4. 例外：`observed_hash`、`config_hash`、`freeze_hash`、`preprocessor_hash`、`split_fingerprint` 两格**不同**（都含 cell/run 身份）。
5. 报告 §3.0（第 251–266 行）与 §6 第 6 条（第 365–368 行）**两处都披露**，§4.2（第 322–328 行）另有一处；三处口径一致，
   且明确"不计入有效机制证据 / 不得进摘要 / 不得与 `L2_n200000_p050` 并列 / 须另立注册分析"。**§3.1 表尾也有 † 注**（第 133 行）。

**判定**：D1-A 披露**成立**，没有把它当有效机制证据。唯一措辞问题见 **P2-3**（"验证产物逐字节相同"只在 `fixed_bootstrap.csv` 这个文件上成立，
逐 rep 行并不逐字节相同——5 个哈希字段不同；建议改成"数值逐位相同"）。

---

## §5 复合 `run_summary.json`（`runs/matrix_run_summary.json`）

| 检查项 | 我的读数 | 判定 |
|---|---|---|
| `status` / `composite` / `all_complete` / `failures` | `formal` / `true` / `true` / `[]` | 相符 |
| `bootstrap_resamples` / `bootstrap_budget_scope` | `0` / `null` | 相符（矩阵臂不重抽） |
| `shard_rows` | 24 键：core 4 格 = 500、Tier2 20 格 = 30 | 相符 |
| `derived_from[0]` phase1_core_prefix | `6a928a88f68545c362f1c6d579d6264b65facf2377806089e386d5e6d3049d97` | 与 `out/g03_core_prefix/run_summary.json` **sha256 逐字符相同** |
| `derived_from[1]` phase2a_tier2 | `4d2c53347375bdb6d4a3a3e5c8310e4efbbdfe0a92d8c04998238cf9a6eadead` | 与 `out/g03_tier2/run_summary.json` **相同** |
| `derived_from[2]` phase2b_core_ate | `6923a32b8db123fb67e00aeaef4fd8fec5a4f5e68e32e242691b54e6f2a0702a` | 与 `out/g03_core_ate/run_summary.json` **相同** |
| 三份源 summary 自述 | 均 `status=formal`、`failures=[]`、`bootstrap_resamples=0` | 相符 |
| 分片计数 | 132 = 40（core prefix）+ 32（core ATE）+ 60（Tier2），与 `phase2.log` 19:33:04 的 132 一致 | 相符 |
| 合并去重 | `phase2.log`：`rows_raw 2600 / rows_deduped 2600`（composite 段） | 相符 |

**但**：三份源 `run_summary.json` **不在 `outputs/evidence/`**（证据包里只有合成后的 `runs/matrix_run_summary.json` 与 `runs/fixed_run_summary.json`），
所以 `derived_from` 这 3 个 sha256 **只能靠读 `out/` 才能核**——见 **P1-3**。

---

## §6 登记一致性（P0 主项）

### 6.1 目录级 `outputs/evidence/g03_formal/coverage.json`

- 结构：`kind=g03_evidence_coverage`、`cells=24`、`fixed_cells=24`、`records=323`、`total_bytes=5 162 542`；
- 全部 323 条 `target` 都在 `outputs/…` 下、**0 条含 `staging`**（19:35 的 target 重挂确实生效）；
- 双向核对（AGENTS §12.7）：磁盘 108 个文件、登记 107 个 target，**未登记 1 个 = `coverage.json` 自身**（可接受，索引不自指），**登记了但磁盘缺失 0 个**；
- **按条核对 sha256/bytes：323 条中 216 条与它指向的文件不符**（107 个 target 各至少有 1 条相符记录，所以"缺档"为 0，掩盖了下面的问题）。

### 6.2 问题本体（P0-1）

`per_cell/shards/` 下只有 **48 个文件**（24 格 × `repetitions` + `telemetry`），但登记了 **264 条分片记录**：
每个 core 格 18 条记录（10 个 prefix 分片 + 8 个 ATE 分片）、每个 Tier2 格 3 条，**全部指向同一个文件名** `<cell>__<cell>__…csv`。
例：`L0_P_main` 的 18 条记录分别写着 `bytes=11850/11816/11821/…/33629`、`sha256=7c42…/20d6…/a4a3…/17ce…`、
`source=out/g03_formal/shards/L0_P_main_s0000…s10007/…`，而磁盘上那个文件只有**最后一个写入者**（`s10007`，33 629 B、`17ce304a…`）的内容。
⇒ **264 条分片记录里 216 条断言的内容并不存在**（48 条即"每个 target 的最后一次写入"相符）。

**根因（读码定位，未改）**：`scripts/41_export_g03_evidence.py:74` 的 `cell_runs()` 返回 `shards/{cell}_s*/{cell}`，
即元素是**格目录**而不是分片目录；`:322` 与 `:327` 用 `f"{cell}__{run.name}__repetitions.csv"` 拼名，`run.name` 恒等于 `cell`
⇒ 同一格的所有分片写到同一个文件（`:323` 的 `note` 用的却是正确的 `run.parent.name`，所以 note 与 target 自相矛盾）。

**旁证**：
- `out/g03_logs/finalize.log` 的 `[g03-ev] 导出 323 个文件 → out\g03_evidence_staging，共 5162542 B` —— 323 是记录数，不是文件数；
  `total_bytes` 也是**按记录累加**（= `sum(r['bytes'])`，5 162 542），而 107 个不同文件的真实字节和是 **3 130 533 B**。
- 两道门禁都拦不住：`41 --check` 根本不走导出分支（只重算帧与汇总）；`scripts/33:318` 只对**身份类 JSON** 做"磁盘 sha vs 目录级索引"核对
  （`manifests/*.json` 不匹配 `*manifest*` 模式，CSV 更不在其列），所以 `33 dry-run=0` 与事实无关。

**影响面（务必区分）**：**结论层数字不受影响**——24 份合并逐 rep 表 0 错误、96 个汇总数字 0 误差（§1），
所以"只看数字"的部分仍然可重建；受影响的是 §5 里"分片原件同在 `per_cell/shards/`（只导合并件会让'合并是否忠实'不可核）"这句话：
**分片原件事实上不在证据区**（每格只剩 1 个分片），"合并是否忠实"仍然不可核。§2 第 70 行"重导出 323 条记录、0 缺失、0 staging 前缀"里的"0 缺失"只对"文件存在"成立。

**修法建议**：`:322`/`:327` 改用 `run.parent.name`（并加一条"目标文件名全局唯一"的断言）；重导出 → 33 重新 dry-run/登记 →
在 41 的 `--check` 或 33 里增加"非身份类记录也要逐条核 sha/bytes"（§12.3：只准加强）。**不需要重跑任何 rep**。

### 6.3 顶层 `outputs/evidence/coverage.json`

- 93 条记录，`total_bytes=16 975 748`（= 逐条求和，实数相符）；**93/93 条 sha256 与 bytes 与磁盘一致**（我全查，不是抽 10 条）；
- 其中 g03 相关只有 **1 条**：`g03_snapshot_binding`（5 777 B、`022099c7…`），与目录级索引里同名记录一致；
- 与目录级索引的关系：33 号按"身份类 JSON"提升，所以 323 条里的 322 条只存在于目录级索引——这是既有设计，不算缺陷；
  但 §2 第 71 行"顶层登记 **93 条**"紧跟在 G03 收尾语境里，容易被读成"G03 登记了 93 条"，建议补一句"其中 G03 = 1 条"（P3-1）。

---

## §7 措辞与边界

| GOAL 要求 | 落实情况 | 判定 |
|---|---|---|
| 20 格逐格正式结果 | §3 四张表各 20 行 Tier2，逐格 mean/sd/SE/CI | 满足 |
| 不得声称跑满 65 格 | 全文只有 §7 的否定句"不表示 Tier2 全 65 格已覆盖" | 满足（无正向声称） |
| Tier2 不得与 Tier1 并列 | 4 处 Tier2 表头均带"不与 Tier1 并列排序"；§4.2 标题同；§6 第 2 条明写"不得与 Tier1 数字并列"；两组合计/排序均未出现 | 满足 |
| R=30 只判方向与量级 | §6 第 2 条、§4.2 末段、§4.1 末段（"每格只有 1 个 rep，没有跨 rep 的重复证据"） | 满足 |
| 不得出现"95% CI 覆盖真值 X%" | 全文仅 §3 末与 §6 第 5 条的否定式表述 | 满足 |
| 数字可追溯到 `outputs/tables/*.csv` | §3 → `v3_g_g_{core,tier2}.csv`（逐字节等于证据副本）；§4 → `v3_g03_fixed_bootstrap_summary.csv`（24/24 行相符） | 满足 |

**残留的过期文本（P1-1，见下）**：标题仍写"（G03 骨架）"、状态块仍写"§3 仍待填 / Phase 2 已于 2026-10-30 17:37:55 启动 / 预计约 16 h"、
维护时间仍是 `2026-10-30 17:37`——与本文件 §2/§3 已填的事实、与 `finalize.status`（19:36:47）直接冲突。

---

## §8 执行记录与恢复纪律（对照 `out/g03_logs/`，只读）

| 报告 §2 的断言 | 现场 | 判定 |
|---|---|---|
| 05:55:41 Phase 1 完成 | `phase1.status`：`phase1_exit=0` / `merge_exit=0` / `OK: G03 Phase1 core prefix 完成 2026-10-30 05:55:41` | 相符 |
| 09:41:22 Tier2 600/600、09:41:23 转 2b | `phase2.log:306,314`：`finished_at 2026-10-31T09:41:22+08:00`、`rows_raw=600 / deduped=600`、`all_complete=true`；`[2026-10-31 09:41:23] Phase 2b` | 相符 |
| 09:41:35–19:32:34 2b 跑完 1 600 | `phase2.log`：`09:41:35 4 格 / 32 个分片`，`rows_raw=1600 / rows_deduped=1600`，`finished_at 2026-10-31T19:32:34+08:00` | 相符（措辞见 P3-2） |
| 19:33:04 记 132 个分片 | `phase2.log:443` 起建复合根；分片列表 132 项（40+32+60） | 相符 |
| **19:33:21 完成行** | `phase2.status` 末行 `OK: G03 Phase2 完成 2026-10-31 19:33:21`；五步 exit 全 0（`tier2/core_ate/merge/final_check/composite_summary`） | **相符** |
| 19:34:17–19:34:26 自动收尾触发、33 dry-run rc=2 | `finalize.log`：1/5 `19:34:07`、2/5 演练 → `19:34:17` 3/5 导出 → `19:34:25` 4/5 33 → `19:34:26` rc=2（2 条错误，均指 `binding/snapshot_binding.json`） | 相符（时间窗与"全指向"措辞见 P3-1） |
| 19:35 修 target 重挂、重导出、33 rc=0 | `finalize.log`：`19:35:50` 第二轮 → `19:36:09` 33 dry-run 候选 2 个、**新增 1 已登记 1** | 相符 |
| **19:36:47 收尾全绿 + 实登记 93 条** | `finalize.status` 末行 `OK: G03 finalize 完成 2026-10-31 19:36:47`，6 步 exit 全 0；`19:36:46` `records 92 → 93，total_bytes 16969971 → 16975748` | **相符** |
| 19:37 `49 … RC=0 → [VERDICT] READY` | `out/scratch/g49_full.log`（mtime `10-31 19:37`）末行 `[VERDICT] READY`，含 `24 格达 R` / `49 文件与快照一致` / `274 条 claim（Tier1 274 / Tier2 0）` / `33dry-run EXIT=0` / `顶层全表复算一致：93 条（幂等）` | 相符（退出码本身不可见，见 §0.6） |
| 日志无异常 | `phase1.log` / `phase2.log` / `finalize.log` 的 `error|traceback` 计数均 **0** | 相符 |
| 续跑纪律（§2 末两段） | 与 `51`/`63` 的实现描述一致；本轮未触发续跑 | 相符（未演练） |

---

## §9 问题清单

### P0（1 项）

**P0-1 证据登记表 216/323 条内容与磁盘不符：分片导出文件名塌陷（每格只剩 1 个分片）**
- 位置：`outputs/evidence/g03_formal/coverage.json`（`kind=g03_repetitions_shard` 与 `g03_telemetry_shard` 共 264 条中的 216 条）；
  根因 `scripts/41_export_g03_evidence.py:322`、`:327`（`run.name` 应为 `run.parent.name`）；
  相关表述 `docs/v3_phase_G03_formal.md:70`（"323 条记录、0 缺失"）、`:339-340`（"分片原件同在 per_cell/shards/"）。
- 复算证据：`323 records → 107 unique targets`；逐条核 sha/bytes **216 条不符**；`per_cell/shards/` 只有 48 个文件；
  `L0_P_main` 的 18 条记录共用 1 个 target、其中只有 `s10007` 那条（33 629 B / `17ce304a…`）与磁盘一致；
  `total_bytes` 5 162 542 = 记录累加，真实不同文件合计 **3 130 533 B**；`finalize.log` 的"导出 323 个文件"同源失真。
- 影响：**不影响 §3/§4 任何数字**（合并逐 rep 表 0 误差，已全查）；影响"分片 → 合并"这一层可核性，以及 §5 的可复算声明。
- 建议：改 `:322/:327` 用分片名 → 加"target 唯一"断言 → 重导出/重登记 → 加"非身份类记录逐条核 sha"的门禁；**无需重跑**。

### P1（3 项）

**P1-1 报告头部状态块过期，与 §2/§3 直接冲突（含维护时间违反 AGENTS §10）**
- 位置：`docs/v3_phase_G03_formal.md:1`（"（G03 骨架）"）、`:4`（维护时间 `2026-10-30 17:37`）、`:5-9`（"Phase 2 已于 2026-10-30 17:37:55 启动，预计约 16 h"、"**§3 仍待填**"）。
- 证据：`phase2.status` 19:33:21 完成、`finalize.status` 19:36:47 完成；`:38-72` 的 §2 已记录全部完成事件；§3 已填 96 行；文件 mtime 19:38:22。
- 建议：标题去掉"骨架"，状态块改成"24 格全部完成（Phase 2 19:33:21 / finalize 19:36:47），§3/§4 已填"，
  维护时间改到本次定稿时刻（≥ `2026-10-31 19:38`，精确到分钟）。

**P1-2 §5 仍写"顶层登记留人工复核后再执行"，但登记早已执行**
- 位置：`docs/v3_phase_G03_formal.md:353`；与同文 `:71`（"实登记 93 条"）自相矛盾。
- 证据：`finalize.status` 的 `register_exit=0`；`finalize.log` `19:36:46 写入 outputs/evidence/coverage.json`；顶层 93 条与磁盘 93/93 一致。
- 建议：改成"已于 2026-10-31 19:36:46 实登记（93 条，幂等）"。

**P1-3 证据包里没有本次矩阵的运行日志与三份源 `run_summary.json`，§2 时间线与 `derived_from` 不能只靠 `outputs/evidence/` 重建**
- 位置：`docs/v3_phase_G03_formal.md:41-72`（§2 时间线）、`:337-342`（`derived_from` 与"7 例夹具演练见日志"）、`:333-346`。
- 证据：`outputs/evidence/g03_formal/logs/` 只有 4 件、全部是 **10-29 阶段 A** 的 `chain.log / g02_fixed.log / g03.log / chain.status`
  （`chain.status` 内容仍是 `paused_20261029_1936=…`）；`runs/` 只有合并后的 2 份；`out/g03_core_prefix|g03_tier2|g03_core_ate/run_summary.json` 未导出。
  我为核 `derived_from` 三个 sha256，只能读 `out/`（gitignore，AGENTS §12.1 的"别人需要复算的材料"）。
- 建议：把 `phase1.{log,status}`、`phase2.{log,status}`、`finalize.{log,status}`、`49` 的日志与三份源 summary 一并导出并登记（41 加一个文件列表即可），
  同时把 `chain.status` 标注为"阶段 A 历史，已退役"（49 号自己也这么判）。

### P2（3 项）

**P2-1 多格四指标"逐位相同"未披露：20 格里有些格对注册指标没有独立信息**
- 位置：报告 §3.1 表（`:108-131`）与 §3.2 表（`:146-169`）整体；D1-A 只覆盖了 `L2_immature_negative_control` 一格。
- 我的复算（rep 0–29 的向量做 sha256 分组）：
  - `ate` 完全相同：{`L1_cost_prediction_under`, `L1_main`, `L1_mar_double`, `L1_misspec_omit_new_channel`}、
    {`L3_missing_confounders`, `L3_fixed_lt000`（前 30 rep）}、{`L2_immature_negative_control`, `L2_n200000_p050`（前 30 rep）}；
  - `ate_paid_purchase_7d` 与 `ate_any_refund_30d` 完全相同：{`L0_P_main`, `L0_Pi_heterogeneous_cost`}、
    {5 个 L1 格：`L1_main` + cost_prediction_under / mar_double / misspec_omit_new_channel / signal_weak}、
    {`L2_immature`, `L2_n200000`}、{`L3_fixed_lt000`, `L3_missing_confounders`}；
  - 这些格的 `ate_test` 与 `model_*_tau_*`、`validation_targeted_n` 则**确有差异**（例：`L3_missing_confounders` vs `L3_fixed_lt000` 的 `ate_test` 差异最大 0.1931、选模分布也不同）。
- 我的判读（**推断，需主控从源码确认**）：`ate` 是随机化均值差，对"只改协变量/观测层"的机制（漏渠道、缺失双倍、成本预测乘子、共同原因缺失）**构造上不敏感**；
  所以 §3.1 的 20 行里有 5 行与 `L1_main`（或 `L3_fixed_lt000`）是同一串数。
- 为何算问题：§3.1 的排版本意是"20 格机制结果"，读者会把行间差异当作机制效应；而 `L3_missing_confounders` 与 core 格在四指标上**完全一致**，
  这与 D1-A 被否掉的理由（"逐位相同 → 不计入有效机制证据"）形式相同，只是成因不同（机制确实接线了，只是没作用在这四个指标上）。
- 建议：在 §3 表下补一段与 D1-A 同规格的披露（列出上述等价组，说明差异只出现在 `ate_test` / 选模 / fixed bootstrap），
  并在 §6 增加一条"注册指标对哪些机制不敏感"的局限；**不必重跑**。

**P2-2 `L0_zero_purchase_effect` 30/30 选中 `constant`，退化策略未披露**
- 位置：§3.1 该行（`:113`）、§4.2 该行（`:297`）。
- 证据：`chosen_model` = `constant` **30/30**（其余格均为混合选模；例如 `L0_P_main` 4 种、`L1_main` 5 种）。
- 影响：该格的 fixed bootstrap 点差 `+0.0765`（CI 跨零）实际是"不做差异化"的策略值，不是定向能力的证据；报告只给数字、未给选模分布，
  读者无法判断"零效应边界"格里的策略是否退化。建议像 E/F 阶段那样补"选模分布"或在表注写明。

**P2-3 §3.0 "验证产物逐字节相同"过宽；rep0 固定 bootstrap 的 md5/sha256 无法从证据包核**
- 位置：`:253-256`。
- 证据：逐 rep 行**并非逐字节相同**——`config_hash`（`de8c243e…` vs `ad1b76a0…`）、`observed_hash`、`validation_freeze_hash`、
  `preprocessor_hash`、`split_fingerprint` 两格全不同，只有 40 个数值列（除 `tier`）逐位相同；"逐字节"只对括号里那份 `fixed_bootstrap.csv` 成立。
  而证据包没有 rep0 级的 `fixed_bootstrap.csv`（只有合并成 24 行的 `fixed_bootstrap.csv`），所以 `69da7f4a…`/`4f7a7b79…` 这两个摘要串**当前不可复算**。
- 建议：改写为"30 个 rep 的四个指标与验证数值**逐位相同**（只有 cell/run 身份类哈希不同）"，并把这两份 rep0 文件（或它们的 sha256 sidecar）纳入导出。

### P3（5 项，建议顺带修，不阻塞）

1. **`:71` "顶层登记 93 条"易被读成 G03 的登记条数**——实际 G03 只占 1 条（`g03_snapshot_binding`），其余 322 条在目录级索引；建议加"其中 G03 = 1 条"。
2. **`:69` "target 全指向 `out/g03_evidence_staging/…`"**——`finalize.log` 里 33 只报了 2 条问题，都关于 `binding/snapshot_binding.json`；
   "全"是对未观测部分的推广。同行时间窗 `19:34:17–19:34:26` 不含 41 `--check`（`19:34:07`）与演练（`19:34:09–17`）。
3. **`:65` "1 600/1 600（4 格 × 100 分片行）"**——实际是 4 格 × 400 rep = 1 600，按 32 个分片 × 50 行落盘；"100 分片行"对不上任何量。
4. **`binding/snapshot_binding.json` 的 `git_commit` 为 `null`**（G02 有值）：快照与 49 文件哈希可核，但无法从绑定文件直接回到某个 commit。
5. **`fixed_run_summary.json` 的 `all_complete=false` 未说明**（每格只有 rep 0，属预期）；§4 可加半句以免读者误当作"未完成"。
6. **`per_cell/CSV` 的 `overlay_source=overlay`**：报告 §5 说 overlay 不在 `pipeline_source_hashes` 账上，数据侧与之相符（`overlay_sha256=02644767…` 恒定），
   但"运行期未改"目前只有人工复核；建议 G04 把两文件的 sha256/mtime 记成证据（报告 §5 已声明移交 G04，此处仅备忘）。

---

## §10 复算一致性汇总

| 对象 | 我的结果 | 报告/表 | 判定 |
|---|---|---|---|
| 24 格 R 与 rep 排列 | core 4×500、Tier2 20×30、rep 恰 0..R−1、重复 0、`provisional` 0 | 同 | 一致 |
| 96 行汇总（mean/sd/MC_SE） | max\|Δ\| = 0 | `v3_g_g_*.csv` | 一致 |
| 96 行报告排版 | 96/96（6 字段） | §3 四表 | 一致 |
| 24 行 fixed bootstrap | 24/24（6 字段）+ 跨零/正负/中位半宽全对 | §4 两表 | 一致 |
| D1-A 等价性 | 30/30 rep 数值逐位相同（除 `tier`） | §3.0/§4.2/§6 | 一致 |
| 复合 summary | 3 个 `derived_from` sha 与 `out/*/run_summary.json` 全等 | §2/§5 | 一致（但源文件未入证据，P1-3） |
| 目录级登记 | 323 条 / **216 条 sha 不符** / 107 target / 0 staging | §2 "323 条、0 缺失" | **不一致（P0-1）** |
| 顶层登记 | 93 条、93/93 相符、16 975 748 B | §2 | 一致 |

---

## §11 实际运行过的命令（可复现）

```bash
# 0) 身份与时间（本机时区即 +0800）
git log -1 --oneline ; git status --short
date '+%F %T %S %z' ; date -u '+%F %T'
stat -c "%y %n" docs/v3_phase_G03_formal.md outputs/evidence/g03_formal/coverage.json

# 1) R 与完整性（逐格行数 / rep 集合 / provisional / n_treated+n_control==n）
./.venv/Scripts/python.exe - <<'PY'
import pandas as pd, glob, os
for f in sorted(glob.glob("outputs/evidence/g03_formal/per_cell/*__repetitions.csv")):
    d = pd.read_csv(f, encoding="utf-8-sig")
    assert len(d) == d.rep.nunique() and set(d.rep) == set(range(len(d)))
    assert (d.n_treated + d.n_control - d.n).abs().max() == 0
    assert (d.provisional == False).all() and d.status.unique().tolist() == ["formal"]
print("OK", sum(len(pd.read_csv(f, encoding='utf-8-sig')) for f in glob.glob("outputs/evidence/g03_formal/per_cell/*__repetitions.csv")))
PY

# 2) 96 行 mean/sd/MC_SE 与两张汇总表比对（另用 md 解析器复核报告 §3 的 96 行排版）
# 3) fixed bootstrap 24 行与 §4 两表比对 + 跨零/正负/中位半宽统计
# 4) D1-A：两格逐列 max|Δ|、observed_hash_without_run_id、两份 rep0 manifest 全键 diff
# 5) 跨格向量比对（检测"逐位相同"）：对每格 rep<30 的 ate/ate_test/ate_paid_purchase_7d/ate_any_refund_30d 取 sha256 分组
# 6) 复合 summary：json 解析 + sha256sum out/g03_{core_prefix,tier2,core_ate}/run_summary.json
sha256sum out/g03_core_prefix/run_summary.json out/g03_tier2/run_summary.json out/g03_core_ate/run_summary.json

# 7) 登记一致性：323 条逐条重算 sha256/bytes + 双向索引 + 顶层 93 条全表复算
./.venv/Scripts/python.exe - <<'PY'
import json, hashlib, collections
d = json.load(open("outputs/evidence/g03_formal/coverage.json", encoding="utf-8"))
recs = d["records"]; bad = 0
for r in recs:
    b = open(r["target"], "rb").read()
    if hashlib.sha256(b).hexdigest() != r["sha256"] or len(b) != r["bytes"]: bad += 1
print(len(recs), "records,", len({r['target'] for r in recs}), "targets,", bad, "mismatched")
PY

# 8) 日志与状态（只读）
cat out/g03_logs/{phase1,phase2,finalize}.status
grep -ci 'error\|traceback' out/g03_logs/{phase1,phase2,finalize}.log
grep -n "09:41\|19:32:34\|19:33:21\|132\|rows_raw\|rows_deduped\|all_complete" out/g03_logs/phase2.log
tail -25 out/scratch/g49_full.log

# 9) 读码定位根因（只读）
grep -n "run.name\|run.parent.name\|/  *\"shards\"" scripts/41_export_g03_evidence.py
sed -n '289,350p' scripts/33_register_evidence_top.py
```

---

## §12 给主控的关闭条件建议

1. **P0-1 关闭**：`41` 修 `:322/:327` → 重导出 → `per_cell/shards/` 文件数 = 264（或按设计去重后与记录数相等）、
   323 条记录逐条 sha/bytes 0 不符、`total_bytes` 改为"不同文件之和或明确标注为记录累加"；补一条 target 唯一性断言与对应用例
   （AGENTS §12.7：新校验器要自带反例夹具）；重登记后 `33` 全表复算应为 0 不符。
2. **P1-1/P1-2 关闭**：头部状态块与维护时间更新；§5 的"留人工复核后再执行"改为已完成。
3. **P1-3 关闭**：`phase1/phase2/finalize` 日志与 status、三份源 `run_summary.json` 导出并登记（`chain.status` 标注退役）。
4. **P2 可同批处理**：§3 增补"四指标逐位相同"披露（P2-1）、选模分布/退化策略说明（P2-2）、§3.0 措辞与 rep0 摘要入证（P2-3）。
5. 以上全部只需**导出层与文本层改动**，**不需要重跑任何 rep**；改完建议做一次窄口径复核（只核上述 5 条 + 96/24 行数字未变）。

**再次声明**：本评审只看记录准确、断言范围与证据可复算；不判断机制在真实业务是否成立。
