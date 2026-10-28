# AGENT 交接说明 —— v3 重建

> **最新交接时间：2026-10-28 21:49（北京时间）。当前分支：`codex/d03`；HEAD 见 `git log -1`。**
> **（2026-10-28 21:49 更新）D 层三项全部通过；F02 收尾复核条件 C1–C6 已落地，等窄口径复核确认。**
> - **D01 通过（21:38）**：第三轮复核 PASS（`docs/reviews/v3_phase_D01_closeout.md`），第四轮在 77 条登记上复核仍 **PASS（6/6）**：
>   下界 1,003.0977、上界 1,097.12–1,107.06、分项和 −182.5676、1.79/1.89 GiB；目录级 10/10、顶层 76/76（21:28 版）与 77/77（21:42 版）sha/bytes 全 MATCH。
>   残余仅 P3-1：`outputs/evidence/d01_pilot/source_binding.json` 仍是旧字段 `frozen_config_hash`（770 B、`8162110b…`）；
>   脚本已在 `f055883` 改为 `config_hash_current` + `config_hash_at_run_inferred_prefix: 30511a32` 并把 `_git_blob` 失败改为硬失败，但未重导出（重导出会改 sha，需 `--force` + 刷新两级登记）。语义已由 doc `:268` 注记覆盖，不改任何数字。
> - **F02 P1-1 关闭（21:38 建表 / 21:48 定稿）**：预测支出一直逐 rep 落在 `out/f02_formal/shard*/rep*/manifest.json` 的 `arms.*.predicted_spend_*`；
>   19:30 导出里的 `predicted_note="not_persisted_per_rep"` 是**没去读**，不是没落盘。已补 600 行全表
>   `outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv`（119,025 B / `dbb8a869…`，
>   21:45 重导出补 `budget_cny` 与 `budget_note`、21:48 重登记）并登记进目录级（20 件）与顶层（**77 条 / 16,924,056 B**，`registry_repairs` 15 条）。
>   定向臂 实际/预测 = **1.056348**（min −5.42% / 中位 +5.09% / max +30.67%，**179/200** 为正），随机臂 **1.002835**（104/200 为正）。
> - **F02 仍记"未证实"**：收尾窄口径复核 21:43 判 **PASS WITH CONDITIONS**（`docs/reviews/v3_phase_F02_closeout.md`，
>   新发现 1 P1 + 4 P2 + 5 P3，另有跨轮残留 P1-1 交付层与 P2-2）；**C1–C6 已于 21:48 全部落地**（formal 去"未落盘"与 bytes 断言、
>   表补分母、validation 写死合并口径、repair 条目改 `added` 并更正时刻、计数改 77 / 16,924,056）。
>   **21:55 第三次窄口径复核**（`docs/reviews/v3_phase_F02_c1c6_recheck.md`）判 C1–C6 六条全关，但因 validation 评审行仍写"未做"（P2）
>   与 5 条 P3 判 NOT CLOSED；**P2 与 5 条 P3 已于 21:56 修完，待第四次确认后才改判**。
> - **下一步**：F02 窄口径复核 PASS → 改判 → G01（AA 4 层 × 250 ≈ 44 CPU·h）需用户批准 R>0、独占机器与快照；
>   G02/G03 仍欠三项决策：再训练 bootstrap 次数（80/200/800，协议原文为"每层 200"⇒ 800）、G03 口径与 210 CPU·h 上限、
>   全预算固定 bootstrap（overlay 28 格口径 196 次额外验证构建 ≈7.1 CPU·h，冻结 69 格口径 483 次 ≈17.6）。
>
> ---
>
> **历史块（2026-10-28 10:57）**
>
> **最新交接时间：2026-10-28 10:57（北京时间）。当前分支：`codex/d03`（从 `codex/v3-rebuild` 的 `9d05bd6` 切出）。**
> **（2026-10-28 10:57 新增）F01 已改判"通过"；第四环 5 项 RC 全部落地。**
> 第四环窄口径复核 07:21 返回 **PASS WITH CONDITIONS**（`docs/reviews/v3_phase_F01_recheck.md`）：
> R1 判 3 条 P1 真实关闭（独立重建贪心名单 n=23 437 / 预测 11 999.505475 / 真值 15 410 / 比 1.284220），
> R2 判 9 条 P2 逐条关闭，R5/R6 判登记 44 条 + 18 条四向核对 0 不符、1 264 进度点 / 0 标记 / `EXIT=0`；
> 新提 RC-1/RC-2/RC-3 + RC-4/RC-5，并**明确授权**在条件同批落地后改判。主负责 10:45–10:47 逐项本机复算后修完：
> RC-1"32 行同常数"实为"24 行有限 + 8 个 `NaN`"、RC-2 22→23、RC-3 sidecar 行尾断言改为"70 个入库 `.md` 中 18 个含 CR"
> （sha256 `7c50c11e…`→`b163b159…`，顶层登记第 6 条 repair、四向 44 条全绿）、RC-4 随 GOAL 行改写消除、RC-5 改锚文本。
> **"通过"只表示记录准确、断言范围正确**（单 rep / rep 0 / `formal_repetitions=0` / `constant` / 0.2 元档），**不表示"定向有效"**。
> **F02**：11:26 时 **120/200**（shard0/1 完成 0–99；shard2 完成 100–109、shard3 完成 150–159），
> 每 rep 耗时由选中模型决定（`s_learner` 365–472 s、`dr_learner` 373–483 s、`causal_forest` 484–670 s 且后段变慢），近 8 rep 中位 475 / 441 s、最近两个 671 / 668 s ⇒ **ETA 区间 16:40–18:50，取 ~18:00**（此前 ~15:55 / ~16:40 两次都偏乐观）；
> 两 lane 均有内存看护（lane 2 于 10:54:45 启动、PID 67048/65688，峰值 2 436 / 2 207 MB，ALARM 0）。
> 等待期已把聚合器按独立评审（0 P0 / 5 P1 / 8 P2）重写、提为 `scripts/32_aggregate_f02_formal.py`（11 个反例夹具）并在 118 rep 上跑通：合并 115/118 与 111/118，
> 分层 `causal_forest` 66/66、`s_learner` 41/41 + 39/41、`constant` **2/5 + 0/5** ⇒ 正文必须分层（§12.6）。
> **推送**：已推到 `11af937`（`eec6959..11af937`，含聚合器重写/提升与 G 落地链修正），工作树干净（仅一个非本项目的 `.workbuddy/` 未跟踪目录）；仍不装无人值守重试循环。
> **无人值守收尾**：`out/scratch/f02_postmerge_auto.sh`（PID 8374，11:24:50 起）等 200 rep + 合并完成后自动跑官方聚合与登记预演，日志 `out/logs/f02_postmerge_auto.log`；它只写 `out/`，不改文档、不登记证据。
> **（2026-10-28 07:13 发现，11:05 用户裁决）G 阶段的重复预算契约冲突——用户已选甲方案。**
> 为了给 G 定价，第一次把 `configs/v3/execution.yaml` + `scenarios.yaml` 与 `configs/budget/repetition_overlay.yaml`
> **并排实读**，发现两者描述的是**规模差 12.2 倍的两个实验**：冻结配置（代码实读、绑定 `approval.json`）**55 100** 作业，
> overlay（用户 2026-10-25 授权）**4 513** 作业。分项倍数 Tier2 **120.8×** / 功效格 **10×** / Tier1 **8.0×** /
> AA 与独立验证各 **4.0×** / 再训练 bootstrap **2.5×**，另有固定策略 bootstrap 1 000 与随机名单种子 200 两项 overlay **未提**。
> **overlay 无任何代码读取**（`grep -rn "overlay"` 在 `src configs scripts` 的 `.py`/`.yaml` 返回 **0** 行），
> 其第 2 行自述"不修改 configs/v3/ 下七份冻结配置" ⇒ 真跑起来一律按 55 100 那一版。
> TODO:142 的评审条件 **C1** 要求"GOAL/G01/YAML 与 overlay 对齐"、状态记"GOAL 已改"——
> **GOAL 与 overlay 确实对齐了，YAML 从未对齐**，这一半漏在了 D02 的三环验收之外
> （评审核的是证据包：1 000 次 AA 与实跑一致、FPR/CP 全真，没有理由去质疑配置里写着 4 000）。
> **AA 用实测定价**：`outputs/evidence/aa/all_repetitions.csv` 1 384 行的 `total_wall_s` 均值 **160.00 s**
> （`cpu/wall = 0.975` ⇒ 单线程、无争用虚高）⇒ 1 000 次 **44.4 CPU·h**、4 000 次 **177.8 CPU·h**，差 **133.3 CPU·h**；
> GOAL.md G01 的"约 33 / 约 131"隐含 **117.9 s/rep**，**实测高 35.7%**（反向说 GOAL 低 26.3%，两个方向都记，§12.5）。
> **overlay 的并行度假设被现场遥测否掉**：它写"4 workers、单 rep 峰值 1.88 GB"，而 F02 两条 lane 实测峰值 RSS
> **3 168 / 2 914 MB**；1.88 GB 只对不拟合模型的 AA 形 rep 成立，而冻结计划 **62%** 的作业是完整学习
> ⇒ 墙钟按 **2 workers**：overlay 路线约 **2.8 天**、冻结路线约 **33.5 天**（1 610 CPU·h ÷ 2）。
> **既有 1 384 行 AA 证据不能直接当 G01 的正式 AA**：9 份 `configs/` 逐份未变（说明当时配置就写着 1000/层），
> 但 **6 份源码已漂移** ⇒ 按 §12.6 不得跨版本配对，G01 的 AA 两条路线都要在当前树上重跑。
> **用户 2026-10-28 11:05 裁决：走甲方案，且只对齐 AA。** 原话「G阶段按甲方案。按照你的思考和建议的方式推进。」
> 范围 = **AA 4 层 × 250**（2026-10-25 授权值），共 **11 行**：`execution.yaml:25`、`scenarios.yaml:411/1296/1925/2942`（`R`）、
> `scenarios.yaml:429/1314/1943/2960`（`complete_aa`）、`scenarios.yaml:261`（`historical_dgp_jobs: 12500→9500`）、
> `scenarios.yaml:264`（`complete_aa_jobs: 4000→1000`）。
> **其余项不动**（ATE 500 / 学习 200 / 独立验证 200 / Tier2 100 / 再训练 200 / 固定 bootstrap 1000）：
> GOAL G01/G02 仍以冻结值为验收标准，同步下调等于**同时改验收标准**，超出这次授权。
> **补丁已就绪**：`out/scratch/g_route_jia_aa250.py`（`out/` 不入库）。`--dry-run` 逐行核对 11 处、写后 `load_v3_protocol(root=…)` 全量校验；
> 真跑安全阀实测在 F02 116/200 时 `FAIL[5]` 拒绝。两处反例（CRLF 行锚点、就地改列表致计数恒 0）都被工具拦下。
> **机制上 11:05 仍不能改**：`v3_pipeline.py:41-44` 的绑定 glob 含 `configs/v3/*.yaml`，
> F02 未退出前改它会让作业抛 `source files changed during the data run`（AGENTS §11）。
> **落地链（F02 四片退出后按序）**：跑补丁 → `scripts/09_freeze_v3_protocol.py --output outputs/v3/protocol_aa250`
> （**不就地覆盖 Phase A 目录**；09 号把 `experiment_results_exist` 硬编码 `false`，修订文件改记 `true`）→
> 新建 `outputs/v3/protocol_aa250/approval_revision_20261028.json`（`approval.json` 保留原字节，它是 Phase A 记录）→
> 写 `docs/v3_phase_G_protocol_change_aa250.md`（含"哪些既有证据仍成立"：各阶段 manifest 绑的是运行当时的 `config_hash`）→
> **独立评审**后才能记 G 开跑。详见 TODO.md「G 阶段前置阻塞」节末的用户裁决小节。
> **顺带否证了自己一个误读**：AA manifest 的 `purpose=engineering_or_downstream_input_not_formal_completion`、
> `formal_repetitions_completed=0` **不是**"D02 那 1 000 次不正式"的证据，而是全项目所有 manifest 入口的**统一戳**
> （`v3_aa.py:67` 明写"不改变任何正式计数器"，`v3_data_checks.py:407` 断言 `no_formal_repetitions_claimed`）；
> 正式与否由验收记录判定。这是 06:13 那条"写进证据前先验证机制"规则**第二次**拦住我。
> **F02**：07:12 时 **51/200**、ALARM **0**、每 lane 474.7 / 470.1 s/rep ⇒ **投影 ~17:00**
> （n=35/41/51 三次复推 16:53 / 16:55 / 16:59，已收敛；n=100 复推时点按合并吞吐更正为 **~10:25**）。
> **推送**：`ada408c` 于 06:56 推送失败（443 连接超时 21 062 ms，exit=128），`[ahead 1]` 安全；仍不装无人值守重试。
> **（2026-10-28 06:37 更新）F01 复审 9 条 P2 已全部逐项本机复算后修完，F01 仍记"未证实"。**
> 复审（`docs/reviews/v3_phase_F01_rereview.md`）的 N-4…N-12 九条，每条涉及的数字都由主负责先从
> `outputs/evidence/f01_ope/` 与 `outputs/tables/v3_phase_F01_*.csv` 重算通过、再改正文（`docs/v3_phase_F01_ope.md` 481 → 573 行）。
> 其中 **N-5** 值得单独记住：原文只引 0.2 档（DR `rank_low=0.015`），而补齐 8 档 × 2 口径全 16 格后可见
> **0.2 档恰是全表最有利于定向的一档**，0.40 档有 **89/200 = 44.5%** 的随机名单不劣于定向。
> **N-10** 把 AGENTS §11.4 要求的全量串行测试凭据提升为入库证据：`outputs/evidence/test_runs/pytest_full_20261028_0321.{log,json}`
> （1 264 项、`exit=0`、03:21:18–03:27:42、进度点 1 264 / `F,E,s,x,X` 标记 0，配 sidecar 记全命令行与冻结树检查）。
> **顺带纠正复审自身一处误判**：复审称 `outputs/runs/f01_tests/full_suite.log` 是"入库那份"，实测 `.gitignore:29` 的
> `/outputs/runs/` 使整个 `outputs/runs/` **从不入库**（`git ls-files outputs/runs` = 0 个文件），所以两份日志此前都不在仓库里，
> 真因是 `*.log` 的忽略洞——与上一轮 E 的两个日志被吞是**同一个洞**。
> **横向清扫（§12.4 的"grep 旧值"升级为"grep 同类"）**另抓到 3 处此前没发现的同类缺陷：F01 §4.7 标题仍写
> "可定义的 7 档全部是外推"（与本轮 N-3 已改正的正文自相矛盾）、F01 §8 检查单仍钉"42 条中"与"repairs 现有 3 条"、
> `docs/v3_phase_E_evidence.md` 检查单同样钉死"42 条 / 15 861 713"。三处均已解耦为"筛出本阶段前缀后逐条核 sha256/bytes"。
> `docs/reviews/*.md` 里的同类数字**一律不改**（评审在其观测时点的不可变凭据，AGENTS §10）。
> 顶层登记表 42 → **44** 条 / **5** 条 `registry_repairs`（`total_bytes` 与 `last_refreshed_at` **一律不在正文钉死**，以实读文件为准）；四向核对（存在/sha256/bytes/**是否入库**）
> 除待提交的 2 个新文件外全绿。**F01 何时可改判"通过"**：待本轮 9 P2 + 3 P1 落地后走一次窄口径确认（照 E 的三环做法），
> 且届时"通过"只表示"记录准确、断言范围正确（单 rep / R=0 / `constant` 模型 / 0.2 档）"，**绝不表示"定向有效"**。
> **推送**：`git push origin codex/d03` 在连续 **7** 次失败（`Recv failure: Connection was reset`）之后，
> **已于 2026-10-28 06:46 第 8 次尝试成功**（`1da7780..a9249d7`，exit=0），分支与 origin 齐平。
> 期间**没有**装无人值守重试循环——push 是网络可见动作，只在有提交要推时人工试一次。
> **推上后仍等用户 review，不自行合并**（AGENTS §7、用户既有约束）。
> **（2026-10-28 06:10 更新）A/B/C/D02/D03/E01/E02 通过。** E 走完三环：评审 PASS WITH CONDITIONS（10-27 21:27）→ 两家族重跑 + 正文重写（01:12–02:46）→ 复审 PASS WITH CONDITIONS（05:34，0 P0 + 3 新 P1）→ 4 项修复（05:40–05:48）→ **第三环窄口径确认 PASS（05:53，`docs/reviews/v3_phase_E_recheck.md`）**，GOAL.md 06:08 改判。
> **F01 仍未证实**：独立复审 **05:58 返回 PASS WITH CONDITIONS**（`docs/reviews/v3_phase_F01_rereview.md`，63 KB；11 项原条目 6 已修 / 4 部分修），另提 3 条新 P1（N-1 机制措辞与数据矛盾、N-2 DR 主口径不可从证据包重建、N-3 "等支出比较做不了"过强）+ 9 条 P2；**3 条 P1 已由主负责 06:05 逐项本机复算确认为真并修完**，无一需重跑，复审明确要求本轮保持"未证实"、待窄口径确认后再判。
> **F02 正式 200 rep**：**07:12 时 51/200**、内存 ALARM **0** 次、每 lane 474.7 / 470.1 s/rep ⇒ **投影 ~17:00 集齐**（n=35→n=41→n=51 三次复推 16:53 / 16:55 / 16:59，已收敛；n=100 复推时点按合并吞吐 236.2 s/rep 更正为 **~10:25**，原写"约 09:00"）；D01 20 rep 最早 **~17:10**。
> **（2026-10-28 05:25 更新）A/B/C/D02/D03 通过。D03 于 05:15 经独立复审 PASS 关闭（`docs/reviews/v3_phase_D03_rereview.md`），走完"评审判定 → 主负责修复 → 独立复核"三环，GOAL.md 三处已同步。E01/E02 与 F01 的评审均为 PASS WITH CONDITIONS、修复已落地，独立复审分别于 05:13 / 05:10 起飞、尚未返回，故仍记"未证实"。F02 正式 200 rep 已于 03:39 起跑（05:07 时 20/200，ALARM 0 次），投影 15:20–17:35 集齐。D01 20 rep 已批准、排在 F02 之后。**
> 下文「最新交接」是当前事实；再往下的旧版交接保留施工约束与历史背景。

## 恢复工作从这里开始（2026-10-28 11:27 写，F02 未集齐时）

1. **先看三个等待进程与两份日志**（都不需要人盯，但恢复时要知道它们到哪了）：
   - `out/logs/f02_postmerge_auto.log`（PID 8374，11:24:50 起）：集齐 200 rep + `outputs/evidence/f02_formal/coverage.json`
     出现后**自动**跑 `scripts/32_aggregate_f02_formal.py --expect-reps 200` 与登记 `--dry-run`，产物 `out/scratch/f02_agg_200_*`；
   - `out/scratch/f02_finalize.sh`（PID 1656，04:04 起）：四片各满 50 后自动合并并导出证据；
   - `out/scratch/f02_chain.sh`：分片编排。
   若 `f02_postmerge_auto.log` 最后一行是 `聚合 exit=0`，直接读 `out/scratch/f02_agg_200_summary.json`。
2. **核对口径**（缺一不可）：200 个 rep、`config_hash` 全 `e1aa4314…`、三臂 `n_assigned` 合计 200 000、
   分层 R 之和 = 200、`constant` 层单列。
3. **填正文**：`docs/v3_phase_F02_formal.md` §1 与 §4 的 7 处 `（待填…）`，数字全部取自
   `f02_agg_200_by_model.csv` / `_summary.json`，并写清"计划等预算 ≠ 实付等预算"。
4. **全量串行测试**（§11.4）：单进程、日志 + exitcode + 起止时间，入 `outputs/evidence/test_runs/`；
   **不要**用 `cmd | tail` 取退出码。
5. **D01**（~92 分钟独占）：`scripts/13_v3_pilot.py --scenario L1_main --n 200000 --reps 20 --start-rep 0`；
   原始产物复制到 `outputs/tables/v3_phase_D_pilot_raw_r20.csv`，不覆盖既有文件。
6. **G 甲方案**：按「G 阶段前置阻塞」末尾的 6 步链执行（补丁 → 09 号落**新目录** → 新建 `approval_revision_20261028.json`
   → 理由文档 §3 填实 → 全量测试 → 独立评审）。**不要**就地重跑 `outputs/v3/protocol/`，**不要**编辑 `docs/v3_协议.md`。
7. **E 残留**：meta 缺 `cfg.hash(64)`（= `e1aa4314…`）。两轮评审均判**可接受、不阻断**，可从
   `outputs/evidence/d03_formal/shard0_summary…` 交叉读出；若要做，先确认 `Config` 上确有 `hash(n)` 访问器，
   再改 `scripts/24_e_evidence.py` 并重跑两家族（各约 50 分钟，须在 F02 与 D01 都退出后）。

## 最新交接：D02 通过，E 被 D03 挡住

### 一、权威状态（不要从旧叙述推断）

| 项 | 事实 | 证据位置 |
|---|---|---|
| A 协议冻结 | 通过 | `outputs/v3/protocol/approval.json` |
| B 机制与真值 | 通过 | `outputs/v3/validation/approval.json` |
| C 五表/SQL/隔离 | 通过 | `outputs/v3/data_validation/approval.json` |
| **D02** | **通过（09:45）**，走完「评审判定 → 修复 → 独立复核 PASS」三环 | `docs/v3_phase_D_aa_formal.md` §8；`docs/reviews/v3_phase_D_recheck.md` |
| D01 | **未证实**：20pilot 三粒度实测与资源计划未做 | — |
| **D03** | **通过（2026-10-28 05:15 独立复审 PASS）**，走完「评审判定（10-27 20:53 PASS WITH CONDITIONS）→ 修复（P0-1 + P1-1~P1-6，21:02）→ 独立复核 PASS」三环；程序豁免经用户 01:10 批准；复审另提 4 项 P2（全为标签/分母问题、无算术错）已当场修正。**证据是正式 R = 200 rep × n=200 000（12:54–17:14）**：选模 105/71/12/7/5，校准斜率 CF 0.754 / S 0.467 / T 0.114 / DR 0.098，greedy−business 按模型符号分裂。此前的 20 rep 诊断（选模 constant 9/20、cf 4/20、dr/s 各 3/20、t 1/20；0.20 档选模后悔 −0.101 元/人）**只是诊断口径，不是通过依据** | `docs/v3_phase_D03_formal.md`（含 §11 评审闭环、§11.2 复审）；`docs/reviews/v3_phase_D03_review.md`；`docs/reviews/v3_phase_D03_rereview.md`；`outputs/tables/v3_phase_D03_formal_*`（7 表 + meta）；`outputs/evidence/d03_formal/`（15 文件，83/83 快照绑定） |
| D04 装载优化 | 实现通过，调用点已切换 | `docs/v3_phase_D_loader_switch.md` |
| E 组件层 | 完成，41 项测试绿 | `src/causal_growth/policy/v3_policy.py`；`docs/v3_phase_E_coverage.md` |
| E 编排层 | 已抽成 `v3_policy_grid.py`，跑通三次：合成数据、真实 D.3 provisional、**20 rep × 5 模型配对网格（7 200 行）** | `scripts/21_e_policy_run.py`；`outputs/tables/v3_phase_D03_diagnostic_policy_grid.csv` |
| 推送 | `codex/d03` 已推送（`80c383d` + 本次文档提交）；`codex/v3-rebuild` 无积压 | `git log --oneline origin/codex/d03 -1` |

### 二、下一步（按优先级）

1. **D03 正式 R 的规模裁决** —— 20 rep 诊断已完成（`docs/v3_phase_D03_diagnostic.md`），结论是：
   - 选模不稳定：20 rep 里 5 个模型都当过第一（constant 9、causal_forest 4、dr 3、s 3、t 1）；
   - 个体校准差：除 causal_forest（斜率中位数 0.689）外，其余中位数 0.02–0.18；
   - 选模有真实代价：0.20 档 chosen 比同 rep 事后最优少 **0.101 元/人**（事后上界）；
   - 期望成本 ≠ 实际支出：按 `cost_hat` 全部 160/160 合规，按 `cost_true` 在 0.04 档只有 0–2/20 rep 全合规。
   **在排正式 R 之前，先跑 3 rep × n=200 000 的计时/选模试点**（同时补 D01 的实测）：
   ```powershell
   .\.venv\Scripts\python.exe -m causal_growth.estimate.v3_models `
     --scenario L1_main --n 200000 --diagnostic --diagnostic-reps 3 --diag-dir out/d03_diag_n200k
   ```
   不要用 26 秒/rep（n=20 000）直接外推正式 n=200 000 的耗时；正式 R 的次数/排期待试点后裁决。
2. **正式 R 的报告口径**（已在诊断报告 §5 写明）：五个候选全部报 bias/校准/误差分位，报选模频率，
   策略网格按模型配对，预算合规双口径；不得只报获胜模型，也不得偷换成"固定 causal_forest"。
3. **D01** 20pilot 三粒度实测与资源计划（可与第 1 步合并产出）。
4. `codex/d03` 已 push，待 review 后合入 `codex/v3-rebuild`。

### 三、接手须知（血泪版）

- **不要拿合成 τ̂ 下策略结论。** `out/e_smoke/` 的 72 行只证明代码能跑。20 rep 诊断里
  `business_rule` 在 4 个模型上赢 greedy、只在 causal_forest 上打平，这是真实 D.3 预测下
  的个体校准问题（除 CF 外 Pearson 0.02–0.05），不是合成数据独有；但仍是已知 DGP、非正式 R，
  不能当业务结论。
- **策略比较必须按模型配对。** 同一 rep、同一批用户，分别用每个候选模型的 τ̂ 重跑网格，
  否则会把"选中模型的好坏"误当成"策略的好坏"。首版诊断只跑了选中模型，causal_forest 被选中的
  4 个 rep 里 greedy 全面胜出，聚合后却因为 constant 被选中 9 次而得出相反结论。
- **`local_swap` 的真值可能低于 greedy**（0.60 预算 −0.00008）。它保证的是**预测目标**不降，
  真值可以降。这是"预测最优 ≠ 真值最优"，不是 bug。
- **证据包在 `outputs/evidence/`（1.79 MB）**，换机只需要它就能重建 FPR 46/1000 与 CP [0.0339,0.0609]。
- `out/` 仍被 `.gitignore` 忽略。任何需要别人复算的材料，必须先从 `out/` 导出到 `outputs/`，
  并且**按 block 过滤**——负对照表里就混着 1 行 `true_aa`，整表复制会算成 8/101。
- **校验器不是装饰**：17/19 号脚本的 `validate` 都被独立评测过"可绕过"，现已扩到能拦 8 类篡改。
  改动它们等于拆掉门禁。

## 历史交接：D 实现层已通过双评审，D02 未完成，正式 AA 在跑（2026-10-25 14:40）

> 以下为历史状态，保留施工约束与踩坑记录；当前状态以上一节为准。

### 一、权威状态（不要从旧叙述推断）

| 项 | 事实 | 证据位置 |
|---|---|---|
| A 协议冻结 | 通过 | `outputs/v3/protocol/approval.json`；七份配置 hash `30511a32…` |
| B 机制与真值 | 通过 | `outputs/v3/validation/approval.json` |
| C 五表/SQL/隔离 | 通过（3015 产物、3.67 GB、四代表库逐行核对） | `outputs/v3/data_validation/approval.json` |
| D.1 MDE | **实现通过**，176 项测试；CSV 732×66 | `outputs/tables/v3_phase_D_mde.csv` |
| D.2 AA | **实现通过**，24 项测试；但只跑了 R=50/n=1 万 pilot | `outputs/tables/v3_phase_D_aa.csv` |
| D.3 模型+DR | **实现通过**，52 项测试 | `outputs/tables/v3_phase_D_models_smoke.csv` |
| D.4 装载优化 | **实现通过**，17 项测试；已切换调用点 | `docs/v3_phase_D_loader_switch.md` |
| **D02（GOAL）** | **未完成，不要标通过** | 见下方"未完成清单" |
| 正式重复 R | **0**（AA 正在跑，跑完才有第一批） | `outputs/v3/pytest_gate.json` |

### 二、正在跑的东西

**正式 AA：4 层 × 250 次 × 20 万人**，四个后台进程，各层进度见
`out/v3_phase_d_aa_formal/<L0|L1|L2|L3>/aa_repetitions.csv` 的行数。
交接时约 14/250，单 rep 约 148 CPU 秒，预计剩余约 9 小时。

- **它跑在源码快照上**（`out/aa_snapshot/`，绑定 40 文件，hash `0a087a1b…`），
  所以**不会因仓库改动被打红**。这是刻意的：见下方"两次踩坑"。
- 续跑：`--resume-from out/v3_phase_d_aa_formal/<层>/aa_repetitions.csv`。
- 汇总表写到 `outputs/tables/v3_phase_D_aa_formal_<层>.csv`，四层跑完后需合并。
- 命令行模板（`PYTHONPATH` 必须指向快照，否则绑定会指向实仓）：
  ```powershell
  $env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
  $env:PYTHONPATH = "$PWD\out\aa_snapshot\src"
  .\.venv\Scripts\python.exe -m causal_growth.evaluation.v3_aa --reps 250 --n 200000 ^
      --layers L2 --no-negative-control --quiet ^
      --run-root "$PWD\out\v3_phase_d_aa_formal\L2" ^
      --summary-csv "$PWD\outputs\tables\v3_phase_D_aa_formal_L2.csv"
  ```

### 三、未完成清单（按优先级）

1. **D02 证据**：正式 AA 的 1000 次跑完后，要合并四层、算合并 FPR 与 CP，
   并写进 `docs/v3_phase_D_aa.md`。**合并 1000 次的 CP 约 [0.037, 0.065]**，这是能支撑
   "FPR≈0.05"的唯一口径；逐层 250 次半宽 ±0.03，**只能描述不能判定**。
2. **C6 AA 报告补两项**：SE 校准（评审算过合并经验 SD/平均 SE=1.020，逐层 0.92–1.08，通过）
   与本 R 下的实际功效（R=50/层对 0.08 只有 0.135）。
3. **C7 DR 设计概率敏感性**：配置已有 `known_design_ipw`，需加一组"用记录设计概率"的 DR 对比，
   否则"DR 不如谁"只是这个估计-e 实现的性质。另需解释 `models.propensity.primary: logistic`
   与 DR 实际用 `lightgbm_classifier` 的关系，并把 `raw_probability_diagnostics_required` 落地。
4. **C8 三处文档修正**：`docs/v3_phase_D_models.md:87`（CF 只对 5 项超参显式 ConfigError）、
   `:114`（`<1e-9` 是自同义反复）、`:126`（行号 184→185）。
5. **C3 功效格实测**：`achieved_effect/rejection_rate` 仍是 pending；
   `src/causal_growth/dgp/v3_local_power.py` 与 `data/v3_local_power_pipeline.py` 已由代理交付，
   **主控未复核**，需先跑测试再接线。
6. **工程评审四项**（代理交付，**主控未复核**）：两个空测试的修复、PRAGMA 恢复机制重新纳入测试、
   `from_manifest` 增加 `source_hashes_before` 校验、C 代表库重放（`scripts/15_replay_c_representatives.py`，
   结果在 `outputs/tables/v3_phase_D_c_replay.csv`）。
7. **可审计绿灯凭据**：现 `outputs/v3/pytest_gate.json` 只有汇总，无日志/exitcode/起止时间；
   且评审在隔离 worktree 收集到 1008 项 vs 声称 1034，**这个差额尚未解释**。
   需在干净树上重跑并产出 C 阶段那种级别的凭据（日志 + exitcode + SHA256）。
8. **E/F/G/H/Z 全部未开始**。

### 四、接手后建议的第一步

不要先动代码。先做三件核对：

1. 看 AA 是否跑完（`out/v3_phase_d_aa_formal/*/aa_repetitions.csv` 是否 250 行）。
2. 跑 `python -m pytest tests -q` 看当前是否绿；**如果代理交付的文件未复核，这里会暴露**。
3. 读 `docs/v3_决策与反思日志.md` 的最后五节——那里有全部裁决与已知问题。

### 五、两次踩坑（务必不要第三次）

**同一个坑踩了两次**：`pipeline_source_hashes()` 会哈希 `src/causal_growth/**/v3*.py` 全目录，
**任何人写盘都会让正在跑的数据作业判伪**。

- 第一次：四个开发代理互相踩，测试假红。
- 第二次：正式 AA 启动即全灭，因为同时派了代理改 `v3_power.py`、新建 `v3_local_power.py`。

**结论（写进纪律）**：正式重复必须满足"运行期间源码只读"——要么快照运行，要么冻结仓库。
**绝不允许把正式跑与开发写盘并行。**

**另一条**：跨运行比哈希前，先确认哈希输入里有没有运行标识列（观测表 `dataframe_sha256` 含 `run_id`，
我因此误判过一次"装载器不等价"）。

### 六、几条已经定死、不要重新讨论的裁决

| 决策 | 内容 | 依据 |
|---|---|---|
| AA 正式 R | **250/层（合计 1000）**，不是每层 1000 | GOAL G01 已改写并附代价；四层 4000 次约 131 CPU·h 等于全部预算 |
| 正文统计口径 | **只用双侧** | 配置无独立单侧 α；单侧沿用 0.05 属口径缺口，只在附录作敏感性 |
| `mde100` | **边界格**，不得计入"可检出" | 解析功效 0.8000 但零余量，真实约 0.79 |
| 护栏界值 | **0.5pp 不改** | 处理组退款率已比对照高 +0.41~+0.67pp，吃掉 83%–135% 界值——这是**结论**不是缺陷 |
| `lightgbm.subsample` | **不改配置，只披露** | 缺 `subsample_freq` 故不生效；改它要重走 A 评审 |
| 随机化层 DR | **保持估计倾向**，标为保守下界 | 改设计概率会让"报告的模型"与"配置"不一致 |
| PRAGMA | **置空** | 实测零收益、崩溃风险真实 |
| 装载器进 `sql_source_hash()` | **不进** | 它是 SQL 语义指纹；装载器由 `pipeline_source_hashes()` 覆盖（但**读取时校验已补**，见未完成第 6 项） |

### 七、环境与磁盘

- `$env:PYTHONUTF8='1'` 必设；`.venv\Scripts\python.exe`。
- 磁盘可用约 296 GB。清理用 `scripts/16_cleanup_scratch.py`（默认预演，`--apply` 才删，带白名单与保护名单）。
- AA 作业**不按 rep 累积**（只有 `representative` 与 `tmp` 两个子目录），不用担心跑出几十 GB。
- 单 rep 峰值内存约 1.88 GB，4 路并行约占 5–7 GB（可用 8.4 GB），**并行上限 4**。

### 八、AA 产物与源码快照的绑定（2026-10-25 15:06 补充，必读）

正式 AA 跑在 `out/aa_snapshot/`（13:54 建立），其 `v3_observed.py` 为 `0059ba16…`；
仓库当前是 `849d50ec…`（D.4 整改时加了读取守卫）。**因此用当前源码读 AA 的 manifest 会被守卫拒绝**——
这是正确语义，不是回退。

读取 AA 产物时：
```powershell
$env:PYTHONPATH = "$PWD\out\aa_snapshot\src"
```
或给重放/校验脚本传 `--source-root out\aa_snapshot`。**不要**为了能读而削弱守卫。

同理，C 阶段 3015 个产物绑定的是旧指纹 `18fe1968…`；已用字节级重放证明与当前源码等效
（248 产物 0 不一致，4 个代表库 `observed.sqlite` 逐字节相同），新凭据在
`outputs/v3/phase_d_c_replay/summary.json`。

---

## 历史交接（下方内容写于 2026-10-25 10:09，D 阶段之前）

> **最新交接时间：2026-10-25 10:09（北京时间，Asia/Shanghai）。当前分支：`codex/v3-rebuild`。A/B/C独立评审通过；正式实验R=0。** 用户要求完成当前C部分后先收尾，由另一个agent接替，本轮不启动D。以下最新节是当前事实；后文旧版交接保留施工约束与历史背景，其中“v3尚未动工”、旧测试数和资源数字不能当作当前进度。

## 历史交接：C 已验收，D 未开始（2026-10-25 10:09）

### 权威状态与证据

- 进度以`TODO.md`为准，验收以`GOAL.md`为准，业务范围继续服从只读`项目方案思路.md`及用户更新的`HITL/完整修订建议_L0-L3与观测评估闭环.md`。原D–H与Z完整目标未缩减。
- A：`outputs/v3/protocol/approval.json`与`docs/reviews/v3_phase_A_review.md`。七份冻结YAML的canonical hash仍为`30511a32bcee9db55e8f5ec1bbc2b9d63eb63dc2a13aa5c720f948c781eccdbe`。
- B：`outputs/v3/validation/approval.json`与`docs/reviews/v3_phase_B_review.md`，包含C集成时闭端点补审。750项机制检查通过；数值误差与自然成本解释边界仍有效。
- C：`outputs/v3/data_validation/approval.json`与`docs/reviews/v3_phase_C_review.md`。最终矩阵为`outputs/v3/data_validation/phase_c_20261025T013445468783Z_pid18708/`；101项作业、6977项检查全过，实际数据队列81批，累计队列行1185000（不是去重用户数）。20项功效合同actual_n=0，实际机制仍待D。
- C全部3015产物逐SHA验证，四个20万人SQLite逐行复核；主控双窗分币比对、独立三阶段账务/事件比对及CLI四格补验均通过。机器证据和来源见`outputs/tables/v3_phase_C_acceptance.csv`，不要从旧报告抄数字。
- 最终全回归803 passed、1条既有B时间积分roundoff告警，日志`out/v3_phase_c/pytest_final_delivery.log`；可提交凭据为`outputs/v3/data_validation/pytest_gate.json`。这不等于正式实验完成。

### 当前实现与入口

- 业务配置：`configs/v3/*.yaml`；数值配置：`configs/v3_numerics.yaml`；C工程配置：`configs/v3_data.yaml`。文件内审前状态标签未改，外部approval是验收依据；不要为改状态或补时间而改变冻结哈希。
- 机制：`src/causal_growth/dgp/v3_*.py`。`V3Population.observation_bundle()`仅返回用户、实际分配、事实订单三张DataFrame；训练不可接受生成器对象或审计字段。
- 五表/SQL/拆分/预处理/持久化：`src/causal_growth/data/v3_*.py`和`sql/v3_*.sql`。学习必须从`ObservedDataset`进入；验证队列不能重新fit或拆成训练，诊断未成熟快照不能进入主分析。
- 文档：`docs/v3_data_pipeline.md`、`docs/v3_data_dictionary.md`、`docs/v3_sql_contract.md`、`docs/v3_preprocessing.md`、`docs/v3_phase_C_validation.md`。
- 单场景工程：`.venv/Scripts/python.exe scripts/11_build_v3_data.py --scenario L1_main --n 200 --sqlite`；工程矩阵：同一解释器运行` scripts/12_validate_v3_data.py --scope smoke`或`--scope all`。先设置PYTHONUTF8=1、PYTHONIOENCODING=utf-8，数值线程OMP/OPENBLAS/MKL/NUMEXPR均为1。
- 当前` scripts/run_all.py --round ...`只编排v2流程；不可当作v3全复现入口。统一v3实验/图/论文入口仍属后续Z验收。
- 完整事实数据位于`data/v3/engineering_checks/`，封存位于`audit/v3/engineering_checks/`；二者按规则不入Git。代表库路径由最终矩阵的`jobs/representative__*.json`指向，不要读取旧失败attempt当作当前代表。

### 已解决问题与必须保留的边界

- 支付/退款与入库窗口统一按绝对闭端点比较，不用epsilon掩盖浮点问题。B独立账本补丁已重新验证并批准。
- C-R09：异常mask选中数与数值改变数分开。零值乘倍率或倍率1允许两数不同；按原命名流逐值验证，不放宽成不等式。
- C-R10：CLI11必须沿用生成器metadata里的canonical配对前缀。101矩阵的68源快照没有包含CLI11，因此其源码与真实CLI补验单独绑定，不能扩大矩阵的证明范围。
- 恢复凭据绑定配置、源码、产物和历史预处理；真实活跃进程按PID与创建FILETIME互斥，不能仅因有running文件就重启。Windows启动器PID可能与真实Python PID不同。
- 旧失败工程尝试和独立核验器的失败日志均保留。首次C批准早于最终评审文件冻结，中间批准已另存`approval_before_review_freeze.json`；现行批准重新绑定最终冻结评审，不覆盖历史。
- L0自然成本机制在共同可行域内几乎等成本，不能宣称识别了异质成本筛选。误差估计不冒称严格数值认证，既有积分告警不能隐去。
- C的独立三臂队列使用工程占位策略，只检验数据链，不是F的策略收益验证。封存只写未释放；F仍须实现模型/策略/OPE/决策/随机验证冻结后的真值读取门禁。
- 现有完整留存入口仅支持工程/代表范围。F/G必须实现非代表验证每rep全链执行、只保留名单/规定摘要/汇总/manifest的精简路径。

### 接替后从D开始

1. 先核验A/B/C批准与实际源码锚点，阅读当前GOAL/TODO和决策日志；无需无改动地重复全部C矩阵。当前所有C计算与核验已结束。
2. D前必须实际跑20次×三种粒度、每次20万人pilot：纯估计、五表SQL加估计、含CF完整流程。记录实际进程CPU、墙钟、峰值内存及失败，按冻结完整矩阵外推；C工程记录不能代替该pilot。
3. 原40–55 CPU小时未获验证，超过原估算50%必须与用户重商，未获回复不能减正式N/R。模型内单线程、并发与内存上限按协议；并行度须据实测决定。
4. D实现独立观测先导方差与MDE、实际功效微观机制、完整AA和常数/T/S/CF及适用DR；形式上的模型名或功效合同不算实际执行。
5. E/F/G/H/Z均未完成：成本/策略优化、交叉拟合OPE、额外20万随机验证、冻结后审计、全部正式重复、三张原生PPT方法图、50–100页长稿与最后清理仍按原协议执行。每阶段须独立评审，不能把C通过当作全项目完成。

### 维护与工具要求

用户新增要求已写入`AGENTS.md`§10：今后文件维护时间精确到分钟，采用北京时间`YYYY-MM-DD HH:mm`；机器凭据保留带时区ISO时间，历史冻结时间不猜补。humanizer已全局安装、旧入口可恢复，见`docs/v3_humanizer_install.md`，不需要重复安装。

本次C里程碑提交以Git日志为准；未推送远端。旧v2的data/outputs须等整个v3验收后按Z单独清理，包含本轮`outputs/tables/v3_phase_C_acceptance.csv`在内的新v3证据必须保留。

---

## 接管前保存的交接原文（历史背景，当前状态以上节为准）

> **读者**：接手 v3 重建的任何 agent（人或模型）。
> **写于**：2026-10-25，v2 已归档（git tag `v2.0`），v3 尚未动工。
> **状态**：本文件是**交接契约**。它与 `项目方案思路.md`、`HITL/完整修订建议_L0-L3与观测评估闭环.md` 一起构成 v3 的施工依据；冲突时优先级为
> **`项目方案思路.md`（业务纲领） > `HITL/…修订建议.md`（含 §0 决策表） > 本文件（执行细节） > `AGENTS.md`（工程规范）**。

---

## 1. 一句话任务

把现在这套「单层（L1）深度 + 四层浅尝」的 15 页论文与工程，重建成
**L0–L3 四层各自完整跑通「机制 → 五表 → SQL → 因果估计与机器学习 → 预算策略 → 不依赖真值的观测评估 → 独立随机验证 → 真值审计」的 50–100 页研究长稿**，且**金额链路改为「购物车 → 首单 → 复购」**——这一改动会让 v2 的**全部数值结论作废**。

---

## 2. 必读顺序（按这个顺序读，否则会做错）

| 顺序 | 文件 | 读它干什么 |
|---|---|---|
| 1 | [`项目方案思路.md`](项目方案思路.md) | 业务纲领。口径红线的原始出处。**只读，不许改** |
| 2 | [`HITL/完整修订建议_L0-L3与观测评估闭环.md`](HITL/完整修订建议_L0-L3与观测评估闭环.md) | v3 的施工图。**先读 §0 决策表**（八项已拍板的裁决），再读正文 |
| 3 | 本文件 | 环境、代码地图、陷阱、协作协议 |
| 4 | [`AGENTS.md`](AGENTS.md) | 工程规范（编码风格、随机数派生、测试要求、git 规范） |
| 5 | [`reports/07_执行复盘与踩坑记录.md`](reports/07_执行复盘与踩坑记录.md) | **25 条真实踩过的坑**。动手前必读，能省你两天 |
| 6 | [`GOAL.md`](GOAL.md) / [`TODO.md`](TODO.md) | v2 的验收标准与进度。v3 需要重写，但结构可参照 |

---

## 3. 当前状态（交接时的事实，已核实）

### 3.1 仓库与版本

| 项 | 值 |
|---|---|
| GitHub | `Lrvin-q/ecommerce-causal-incrementality`（**private**） |
| 分支 | `master` |
| 归档 tag | **`v2.0`**（15 页论文定稿；v3 若有问题可从这里取回 v2） |
| 跟踪文件 | 155 个；`.git` 约 109 MB |
| git 身份 | 仓库本地已设 `Lrvin / liliw@126.com` |

### 3.2 代码与产物规模

```
src/                6,397 行（10 个包：dgp / data / design / estimate / policy / evaluation …）
sql/                  344 行（五表 DDL + 6 视图 + 19 条命名查询）
tests/               10 个文件，404 项用例，全绿
outputs/tables/      52 张 CSV（其中 3 张逐用户中间表未入库）
outputs/figures/     7 张论文组图（600 dpi）
reports/             8 份 Markdown
configs/             1 个 base.yaml（单一事实源）
paper/               main.tex + build.ps1 + xref.py + main.pdf（15 页）
```

### 3.3 v2 的头条结论 —— **新 agent 一个字都不许复用**

金额链路一改，下面每个数都会变。若在 v3 稿里看到这些数字，说明有旧数泄漏：

| 指标 | v2 值 | 为什么失效 |
|---|---|---|
| 解析真值 ATE 利润 | 0.668 元/人 | 首单金额改为 $C_iQ_i$ 后，$\tau_\Pi(X)$ 变成 $X$ 的函数 |
| L1 ITT 利润 | 0.724 元/人 | 同上 |
| 定向每元回报 | 2.085 元 | 分子分母都变 |
| 占真值贪心解 | 86.15% | 同上 |
| 护栏主口径差值 | +0.361 pp | 退款事件率随金额机制变 |
| MDE / 样本量 | 0.3615 元；14,749 / 7,709 | 方差来源变了 |
| CATE RMSE（T/S/CF） | 1.625 / 0.595 / 0.557 | 真值变了 |
| λ=0.25 覆盖率（IPW/DR） | 0.82 / 0.79 | 同上 |

**这些东西留在 git 历史与 `v2.0` tag 里就够了。** 按决策 Q7，v3 验收后 v2 的 `data/` 与 `outputs/` 可以删除。

---

## 4. 八项决策（摘要，以 HITL 文档 §0 为准）

只列**会改变你做事方式**的部分：

| 决策 | 对你的直接影响 |
|---|---|
| **Q1 (b) 分层重复** | 你要按 §8.1.1 的 Tier 1 / Tier 2 清单执行。**Tier 2 每格必须落 `R` 与 `MC_SE` 两列**；正文引用 Tier 2 数字必须带精度；**摘要与结论的定量断言只许来自 Tier 1** |
| **Q2 (c) 不做多面额** | 只有一个 10 元券。全稿不得出现「最优面额」「面额选择」类结论。面额非线性写进展望 |
| **Q3 验证队列存储** | 每 rep 生成 20 万验证用户，但只存**策略名单 + 汇总指标 + manifest**；完整五表只在"代表 rep"留一套 |
| **Q4 (b) 同质化旋钮** | L0-Π 允许一个显式机制旋钮强制利润同质，**但必须标注为人造机制、报告取值分布与触发比例**。若需极端取值才对全部用户同质，就如实写"只在子集上同质" |
| **Q5 概念稿归用户** | 你不做文生图。只做**原生可编辑 PPT 重绘** + SVG/PNG + 图形元素清单。现有 [`HITL/技术路线图_可编辑.pptx`](HITL/技术路线图_可编辑.pptx) 是原生形状（79 形状 + 24 连接线 + 0 图片），可直接改 |
| **Q6 封面/文献** | 封面不写单位、机构、基金、致谢（**不许编造**）。参考文献维持 12 篇，不扩充，但**引文真实性不放松**——不得新增未核实条目 |
| **Q7 旧产物** | 验收通过后才能删 v2 的 `data/`、`outputs/`，且删除要**单独提交**便于回滚 |
| **Q8 阶段评审** | 每个 Phase 结束要过一次**独立子代理评审**（角色见 §11.1）。不通过不得进下一阶段 |

---

## 5. 执行计划（八个 Phase）

| Phase | 核心工作 | 必交产物 | 评审角色 |
|---|---|---|---|
| **A** 协议冻结 | 冻结场景、参数依据、重复矩阵、验收标准 | `docs/v3_协议.md`、`configs/v3/*.yaml` | 资深电商业务专家 |
| **B** 机制重构 | 金额链路、条件真值、L0-P/L0-Π/负对照、L3 双旋钮 | 新 DGP + 解析真值 + 机制单测 | 资深数据科学家 |
| **C** 四层数据工程 | 每层每场景：原始/污染/清洗五表、SQLite、SQL 分析表、拆分、manifest、真值隔离 | `data/v3/`、`audit/v3/` | 资深数据工程师 |
| **D** 检测能力与估计 | 20 万反算 MDE、完整 AA、ATE、CATE 四模型 ×200 | MDE 表、AA 分布、方法对照表 | 资深数据科学家 |
| **E** 策略与优化 | 成本预测、二元策略、贪心/局部改进/精确 DP/MILP/LP | 策略名单、预算表、求解对照 | 数据科学家 + 业务专家 |
| **F** 观测闭环 | OPE（IPW/DR/SNIPS + 交叉拟合）、独立验证队列、真值审计 | OPE vs 随机验证、错误上线率 | 资深数据科学家 |
| **G** 正式重复 | 按分层矩阵跑完、断点恢复、失败记录 | 完整矩阵 + 资源报告 | 资深数据工程师 |
| **H** 论文与图 | 三张方法图 + 分层结果图 + 四部分长稿 | PPTX/SVG/PNG、PDF | 三视角联审 |

**依赖关系**：A→B→C→D→E→F 串行；G 可按层并行；H 依赖全部。

**算力现实（本机实测）**：8 物理核 / 16 线程，30.8 GB 内存但**仅约 8.4 GB 可用**，D 盘剩 304 GB。分层方案下估算 **40–55 CPU·h**，4–6 并行约 **8–12 小时墙钟**。Phase D 启动前必须跑 **20 次 pilot** 实测单 rep 成本，实测高出估算 50% 以上就回来重商 Tier 2 格数——**不许悄悄削减**。

---

## 6. 环境与工具链

### 6.1 每次开工必做

```powershell
$env:PYTHONUTF8 = '1'          # 必须。Windows 默认 GBK，中文与图表会炸
$env:PYTHONIOENCODING = 'utf-8'
cd 'D:\L\practice_project\营销数分项目'
```

### 6.2 路径（已核实存在）

| 工具 | 路径 |
|---|---|
| Python（项目） | `.venv\Scripts\python.exe` |
| 基础解释器（只用于建 venv） | `D:\L\Document\Code\Python\python.exe` |
| xelatex | `D:\SelfDownloadSoftware\texlive\2025\bin\windows\xelatex.exe` |
| pandoc | `C:\Program Files\Pandoc\pandoc.exe` |
| pdftoppm | 已在 PATH |
| 视觉模型 | `node "C:\Users\26382\.dsh\skills\vision\vision.js" "<图片绝对路径>" "<问题>"` |

**注意**：视觉模型是 **qwen3.5-omni-plus（阿里云百炼）**，不是 DeepSeek。主模型不接受图像输入，只能用这个转发。

### 6.3 常用命令

```powershell
python scripts\run_all.py --round all        # 全流程（v2 约 12 分钟）
python -m pytest tests                       # 404 项
& .\paper\build.ps1                          # 重建 PDF（Markdown → pandoc → xelatex ×2）
python scripts\07_check_consistency.py       # 文档数字 ↔ 结果表 一致性门禁
python scripts\08_check_figures.py --strict  # 组图版式门禁（图例/文字是否遮数据）
git ls-files | ...                           # 核对哪些文件入库
```

---

## 7. 代码库地图：能复用什么，必须改什么

### 7.1 可直接复用（改参数即可）

| 模块 | 说明 |
|---|---|
| `src/causal_growth/rng.py` | 种子派生 `(master_seed, stream, index)`。**必须继续用**，禁止裸 `np.random.*` |
| `src/causal_growth/config.py` | 配置加载与 `require()`，无魔法数 |
| `src/causal_growth/io_utils.py` | 路径与落盘 |
| `sql/schema.sql` | 五表 DDL（含 CHECK 把口径红线变约束）。**要加字段**：运行标识、周次、处理动作、设计概率、入库时间 |
| `src/causal_growth/data/sql_layer.py` | 建库 / 视图实例化 / 命名查询加载。模式可复用，路径改为分层 |
| `src/causal_growth/design/power.py` | 功效计算。**要改方向**：从"算所需样本"改为"固定 N 反算 MDE" |
| `src/causal_growth/policy/selection.py` | 贪心 / 局部改进 / DP / LP。**要改名**（当前"背包"实为贪心+局部改进）并补 MILP |
| `paper/xref.py` | 表/图/公式/文献/章节的锚点与蓝色链接。**可直接复用** |
| `scripts/07_check_consistency.py` | 一致性门禁。**要扩展**：新数字黑名单 |
| `scripts/08_check_figures.py` | 图版式门禁（墨迹级碰撞检测）。**可直接复用** |

### 7.2 必须改

| 位置 | 改什么 |
|---|---|
| `src/causal_growth/dgp/` | 金额链路：$Q\sim\text{trunc}N(0.7,0.1^2)$、$G_1=CQ$、$G_2=0.55G_1$；条件真值 $\tau_\Pi(X)=p_1A_1-p_0A_0$ 变 $X$ 的函数；L0 拆 L0-P/L0-Π；L2 加时间与人群构成；L3 拆 $\lambda_T/\lambda_Y$ 双旋钮 |
| `src/causal_growth/data/tables.py` | 五表加字段；金额关联断言（首单 ≤ 购物车、复购 = 55%、券 ≤ 可抵扣） |
| `paper/main.tex` | **`\linespread` 与版式全部重设**；**必须撤掉 longtable→不可分页 minipage 的改造**（见陷阱 §8.2）；改为四部分结构 + 三级目录 + 封面/摘要独立页 |
| `configs/base.yaml` | 拆成 `configs/v3/`：口径 / 层级场景 / 检测能力 / 模型 / 预算 / 评估 / 重复 |
| `reports/` | 全部改为 v3 口径；v2 报告标注归档或删除 |

### 7.3 必须新建

- `src/causal_growth/evaluation/ope.py` —— 不依赖真值的策略价值估计（IPW / DR / SNIPS + 交叉拟合）
- 真值隔离机制 —— 用**路径白名单 + 接口约束 + 集成测试**实现，不靠注释提醒
- 独立随机验证队列的生成与比对
- 多臂？**不需要**（Q2=c，只有二元）
- `MILP` 求解（小规模精确对照，带 gap 报告）

---

## 8. 十二个必知陷阱（我踩过，别再踩）

### 8.1 `\needspace` 会吃掉正文

原实现往页面注入可伸缩胶水，TeX 于是容忍内容超高而**裁掉正文**——实测丢过整节。现在的实现是"剩余高度不足就换页"，但**改这个宏要极其小心**，改完必须核对段落数/字数。

### 8.2 当前 longtable 被改成了不可分页的盒子 —— 长稿必须改回去

`main.tex:34-45` 把 `longtable` 重定义成 `minipage + tabular`，整表不跨页。**这在 15 页稿里是对的**（消除续页重复表头与 overfull vbox），但在 50–100 页长稿里**必然裁表格**。v3 必须恢复真正的跨页 `longtable` 并设置重复表头。这是 HITL 文档 §10.3 明确要求的。

### 8.3 `\hyperref` 参数会被 pandoc 的转义大括号提前闭合

pandoc 把 `[10]` 转成 `{[}10{]}`。放进 `\hyperref{...}{[}10{]}` 时，`{[}` 里的 `{` 会**提前闭合参数**，只有 `[` 进链接。正确写法是再包一层：`\hyperref[ref:10]{{[}10{]}}`。

### 8.4 `build.ps1` 必须保持 UTF-8 BOM

PowerShell 5.1 读无 BOM 的 UTF-8 脚本会按 GBK 解析，报一堆语法错。**任何编辑工具改过 `build.ps1` 后都要校验**：

```powershell
$b = [System.IO.File]::ReadAllBytes('paper\build.ps1')
$b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF   # 必须是 True
```

### 8.5 摘要存在两份副本

摘要硬编码在 `paper/main.tex`，而 `build.ps1` 只截取 `reports/00_项目总报告.md` 里 `## 1 引言` 之后的内容。**改摘要必须改两处**。`07_check_consistency.py` 里有 `check_abstract_sync` 按数字 token 比对——保留它。

### 8.6 黑名单只覆盖"结果数字"是不够的

v2 曾出现**整张 4×3 稳健性表都是旧运行数据**，而黑名单只锁了头条数字，门禁没报。教训：**稳健性区间端点、敏感性表的每一格也要锁**。v3 维护新的黑名单时，把矩阵表的端点一并纳入。

### 8.7 中文全角引号必须从源头写

ASCII `"` 经 pandoc 在 CJK 上下文里判不出方向，会渲染成两端同向的 `”…”`。**源文件里直接用 `“”`**。改完用 `pdftotext` 抽查。

### 8.8 逐用户中间表未入库

`r1_truth_L1.csv`（31 MB）、`r1_analysis_frame_clean.csv`（27 MB）、`r2_cate_predictions.csv`（5 MB）**不在 git 里**，但 `05_paper_figures.py` 会读后两个。克隆后必须先跑 `run_all.py` 才能出图。v3 沿用这个策略，但路径要改到 `data/v3`、`outputs/v3`。

### 8.9 版式检查器不能用"外接矩形"判遮挡

曾用 artist 的 `get_window_extent()` 判遮挡，产生 **245 处误报**：`ax.patch`/spines 被当数据、对数轴柱子 bbox 延伸到 −26260px、`bar(yerr=)` 把 6 个误差帽画成同一个 Line2D。现在 `08_check_figures.py` 用**墨迹点云**（折线取顶点+中点、柱取路径顶点+中心、散点取 offsets，再裁剪到 `ax.bbox`）。**别改回矩形判定。**

### 8.10 视觉模型也会误读，必须程序化兜底

qwen 曾把"几何上距离 0.27in"的框判成遮挡，也曾漏掉真正的遮挡源（twin 右轴网格线映射到左轴 y≈1.805，正好落在标签 bbox 内）。**修完要复验，且要有一道不依赖视觉模型的几何检查。**

### 8.11 PowerShell 5.1 的坑

- 没有 `Join-String`（PS 7 才有）
- here-string 里嵌中文 + 引号容易解析失败 → **复杂逻辑写成 `.py` 文件再调用**，别硬塞进 `-Command`
- `pwsh` 命令不存在，用 `powershell` 或直接 `& script.ps1`

### 8.12 两层文档的漂移

v2 出现过四次"同一信息两个副本"：口径（两套实现）、数字版本（v1/v2）、稳健性端点、摘要双副本。**每次都是靠门禁拦住的，不是靠人记得。** v3 新增任何"同一事实写两处"的设计（配置 vs 文档、图注 vs 正文、报告 vs 论文），都要同时加一道校验。

---

## 9. 五道验收门禁（每次提交前都跑）

```powershell
python -m pytest tests                       # 必须全绿
python scripts\07_check_consistency.py       # 数字 vs 结果表；摘要双副本
python scripts\08_check_figures.py --strict  # 组图版式
& .\paper\build.ps1                          # 0 未定义引用 / 0 缺字 / 0 overfull / 0 错误
pdftotext -enc UTF-8 paper\main.pdf -        # 文本级扫描：无本机路径 / 脚本名 / 版本号 / 破折号
```

**PDF 文本级扫描是最后一道**，它能抓到渲染看不出、但读者会看见的东西。v2 的标准是：`0 盘符路径 / 0 目录文件 / 0 脚本命令 / 0 版本迭代痕迹 / 0 破折号`。

---

## 10. 纪律红线（违反 = 结果作废）

1. **真值只在最后解封。** 学习、调参、阈值、模型选择、策略评估都不许读真实 CATE、潜在结果、$U$、真实倾向得分。用**路径隔离 + 接口白名单 + 集成测试**保证，不靠自觉。
2. **不许静默降级。** 重复次数、样本量、场景、失败重跑，任何一项变化都要写进清单并报告理由。Tier 2 的每格必须带 `R` 与 `MC_SE`。
3. **算法名实相符。** 贪心+局部改进**不许叫背包 DP**；离散化 DP **不许叫原问题最优**；预测目标上的 gap 与真实利润 regret **不许混为一个数**。
4. **口径红线**：退款单不剔除；分母是随机分配的**全部用户**；双窗口分离；券成本只扣一次。
5. **"回报 < 1"不等于亏钱。** 若分子已是扣券后净增量，$R_{net}=0.73$ 表示"每投 1 元券带来 0.73 元**额外净贡献**"。必须区分：净增量为负 / 总利润为负 / 未达门槛 / 证据不足 / 预算不可行——五种判断不得互相替代。
6. **合成数据不许暗示真实业绩。** 全稿标注"合成数据 / 已知 DGP"，不得出现"上线""企业实践"等暗示。

---

## 11. 协作协议

### 11.1 提交规范

```
<阶段>|<模块>: 做了什么
例：C|data: 四层五表与 SQL 血缘，逐层对账通过
```

- 每完成一个 Phase 的交付物就提交一次，不要攒到最后
- **删除旧产物要单独提交**（Q7），便于回滚
- 不要提交：`.venv/`、`data/`、`outputs/runs/`、`*.parquet`、逐用户中间表、`out/` 脚手架

### 11.2 向用户汇报的格式

每个 Phase 结束时汇报五件事：

1. **产出物清单**（路径）
2. **验收项逐条对照**（过 / 没过 / 为什么）
3. **关键数字**（本期新产生的、会影响后续的）
4. **遇到的问题与判断**（含你做过的取舍和理由）
5. **下一步**

**不静默降级**：做不到的验收项必须显式说明，不得悄悄降低标准或换个指标糊弄。

### 11.3 用子代理时的规矩

- 一个子代理只改一个域（`dgp/` / `data/` / `paper/`），**并行安全**
- 子代理的结论**一律当草稿**，主负责必须复核关键数字与口径
- 给子代理的"标准答案"要先用代码复核（v2 曾因主控心算错误给错样本量，差点让正确实现被"修坏"）
- **子代理说你的检查器错了，先验证它的反例，不要让它绕过检查**

---

## 12. 接手第一天建议做的五件事

1. `python -m pytest tests` —— 确认 404 项全绿，说明环境是好的
2. 打开 `paper/main.pdf` 与 `reports/00_项目总报告.md` 对照读一遍 —— 知道 v2 长什么样
3. 跑一遍 `python scripts\07_check_consistency.py` 和 `08 --strict` —— 看门禁现在卡什么
4. 读 `reports/07_执行复盘与踩坑记录.md` 的 25 条 —— 这是最省时间的一步
5. 写 Phase A 的协议草案：**只定义，不实现**。定义完先自己走一遍"如果按这个矩阵跑，Tier 1 有几格、每格多久"，再交给业务专家评审

---

## 13. 风险清单（我知道但还没解决）

| 风险 | 说明 | 建议 |
|---|---|---|
| **内存** | 只有约 8.4 GB 可用，20 万用户 × 5 表 × 6 并行会紧张 | 每 rep 落盘后释放；CF 期间限 `n_jobs`；必要时降到 4 并行 |
| **磁盘** | 剩 304 GB，但 200 rep × 4 层 × 压缩五表仍在几十 GB 量级 | 用 Q3 的存储分级；定期清理 `data/v3` 下非代表 rep |
| **长表与长稿** | 当前 longtable 被改成不可分页，v3 必须改回 | 见 §8.2，改回真正的跨页表格并测长表 |
| **L0-Π 的可达性** | 同质化旋钮可能需要极端取值 | 先做可行域诊断，不可行就如实报"只在子集上同质" |
| **Tier 2 的结论强度** | R=100 只能判方向，不能判临界 | 摘要与结论只用 Tier 1；Tier 2 一律带精度 |
| **算力估算误差** | 40–55 CPU·h 是外推值 | Phase D 前跑 20 次 pilot 校准，别按估算硬排期 |

---

## 14. 一句话给接手的人

v2 的价值不在那些数字（它们即将作废），而在三样东西：**一套把口径做成 DDL 约束与门禁的工程习惯**、**一个承认"完整 ≠ 每层都有正收益"的研究态度**、**一份记录了 25 次翻车的复盘**。把这三点带过去，v3 的数字对不对只是时间问题；丢了这三点，跑得再快也会在某个地方静默错掉。

### 九、D 阶段最新进展（2026-10-25 15:35 补充，覆盖第二节的旧描述）

**C7 已完成**（`515b75a`）：新增 `propensity_source="estimated"|"known_design"`，默认不变；
61 项测试全绿。实测结论比预期更强——**在不等分流的随机化层里估计倾向是主动自伤**：

| 场景 | ITT SE | DR(estimated) SE 比 | DR(known_design) SE 比 |
|---|---|---|---|
| L1_main（p=0.5） | 0.2053 | 1.126 | 0.980 |
| L2（p=0.1） | 0.3689 | **3.083** | 1.017 |

p=0.1 时 raw e 低至 0.0018、68–147 个观测被截断，点估计被推到比 ITT 高 2.5 个 SE。
这条应作为论文的方法论点：**已知的随机化结构应当被用上，而不是用 ML 去重新发现它**。

**C3 已交付入口并开始真实规模验证**：`v3_local_power_pipeline` 支持 `--cells/--layers/--reps/--n`；
效应构造仿射可逆（`τ(s)=τ0+sΔ` 闭式），20 格全部可达（0/20 越界）。
当前正在跑 3 个格（`L0/L1/L2_power_mde200`）的 R=10、n=20 万验证，
输出在 `out/lp_validate_r10/`，预期约 70 分钟。**正式 15 格（R=100）需 58.3 CPU·h，等 AA 跑完再排。**

**已裁决不跑**：L3 的 5 个功效格（未调整 ITT 不是 ATE，选择偏差 = 10.9–11.0 倍 MDE）。
入口的 `estimator_warning` 会自动标记，误传也不会静默产出假曲线。

**合并脚本已就绪**：`scripts/17_merge_aa_layers.py`，只汇总 `block=true_aa`，
输出池化 FPR + Clopper–Pearson + **SE 校准** + 本 R 实际功效。
部分数据（池化 105 次）实测：`net_profit` FPR=3/105=0.0286，**SE 校准 0.989**（逐层 0.883–1.091）。

**仍未完成**：① 全量串行 pytest（等 AA 停）；② 池化 1000 次的 AA 结论；③ C8 三处文档小修；
④ `propensity.primary: logistic` 的实际实现（已披露，属 A 阶段变更）。

### 十、正式 AA 的运行纪律（2026-10-25 15:54，任何接手的人必读）

**当前状态**：L0/L1/L2 在 `out/v3_phase_d_aa_formal_r2/<层>/` 跑，L3 停在 39 次排队。
逐 rep 表在 `out/v3_phase_d_aa_formal_r2/<层>/aa_repetitions.csv`，**不在**旧目录。

**并行度：3–4 均可，以占空位为准（本节下方有 2026-10-25 15:58 的更正）。** 当时的实测（同机同时段）：

| 并行度 | 单进程 RSS | 可用内存 | 占空比 | 观测 |
|---|---|---|---|---|
| 4 路 | 2.0–2.2 GB | 3.5 GB | **17–27%** | 13 分钟零推进 |
| **3 路** | 0.9→2.2 GB 后平台 | 6.6 GB | 接近满速 | 2.5 分钟/rep |

本机标称 30.8 GB，但会话开始时只有约 8.4 GB 可用。**并行度必须由内存实测决定，不能按核数拍。**

**内存行为**：进程 RSS 会随 rep 增长到约 **2.2 GB 后平台化**，不是无界泄漏。
但若四进程同时到平台（8.8 GB），就会越过可用红线，表现为**持续换页而不是报错**——
即"跑得慢"，极易被误判为正常。判据是**占空比**：采样两次 `Get-Process` 的 CPU 增量，
若远低于墙钟（如 17%），就是换页，立刻处理。

**复位办法**（已验证，零丢失）：
```powershell
# 1) kill 该层进程；2) 用新 run-root + --resume-from 续跑
& .\.venv\Scripts\python.exe -m causal_growth.evaluation.v3_aa --reps 250 --n 200000 `
    --layers L2 --no-negative-control --quiet `
    --run-root   "$PWD\out\v3_phase_d_aa_formal_r3\L2" `
    --resume-from "$PWD\out\v3_phase_d_aa_formal_r2\L2\aa_repetitions.csv" `
    --summary-csv "$PWD\outputs\tables\v3_phase_D_aa_formal_L2.csv"
```
`PYTHONPATH` 必须指向 `out/aa_snapshot/src`。复位后 RSS 立刻回到约 1.26 GB。

**合并时必须多根**：`scripts/17_merge_aa_layers.py` 的 `--root` 接受多个目录并按 `(层, rep)` 去重，
默认已覆盖 `_formal`/`_r2`/`_r3`。**只读单一目录会静默漏掉复位前已完成的重复**，池化 FPR 就错了。

**L3 排队说明**：L3 的 39 次在 `out/v3_phase_d_aa_formal/L3/aa_repetitions.csv`；
续跑时 `--resume-from` 指那里，新 run-root 用 `_r3`，合并脚本会自动带上。
**L3 的 5 个功效格不跑**（未调整 ITT 不是 ATE，选择偏差 10.9–11.0 倍 MDE）。

> **15:58 更正**：上表结论"只能跑 3 路"是错的。进程 RSS **随内存压力伸缩**——有压力时滞留到 2.2 GB，压力解除后回落到 0.4–0.7 GB。因此 4 路在可用内存充足时完全可用（实测四层各满速、总内存约 3.4 GB）。
> **正确判据是占空比**：采样两次 CPU 增量，远低于墙钟才是换页。可用内存只是辅助信号。
> 不要把"RSS 增长"直接当成"必须降低并行度"。

#### 各层的完成时间不一样，L0 最慢——不要误判为卡死

| 层 | 正式 AA 次数 | 额外负对照 | 合计 rep | 相对完成时间 |
|---|---|---|---|---|
| L1 / L2 / L3 | 250 | 0 | 250 | 基准 |
| **L0** | 250 | **100**（`L0_zero_purchase_effect`） | **350** | **晚约 4.7 小时** |

L0 启动时带了 `--negative-control-reps 100`，负对照排在 250 次 `true_aa` **之后**。
所以当 L1/L2/L3 都到 250 时，L0 还会显示 250/250 但进程仍在跑——**这是正常的**。

- 判据仍然是**占空比**，不是行数。若 L0 进程 CPU 增量接近墙钟，它在跑负对照，正常。
- **不要削减负对照**：它是 D02 的明文要求（"零购买效应但照常发券"必须与"真 AA"机械分开，
  否则会把负对照当 AA）。`17_merge_aa_layers.py` 只汇总 `block=true_aa`，负对照不会污染 FPR。
- 负对照的产出在逐 rep 表的 `block=purchase_null_negative_control` 行，
  其 `truth` 列购买率为 0、利润列为空——这是刻意的机械分离。

#### 重要变更：AA 已改为「脱离会话的独立进程」（2026-10-25 16:14）

原来是会话后台作业，**会话结束就会全部被杀**。因为剩余 9.4 小时墙钟远超会话可覆盖的时间，
已改为 `Start-Process -WindowStyle Hidden` 启动的独立进程——**不随会话终止**。

- **当前跑在** `out/v3_phase_d_aa_formal_r2_det/<L0|L1|L2>/` 与 `out/v3_phase_d_aa_formal_r3_det/L3/`
- 历史数据在 `_formal`（最初 40 次）/`_r2`、`_r3`（内存复位后续跑）；**合并脚本已包含全部根**，
  并按 `[block, rep]` 去重
- 查看：`python scripts/18_aa_status.py`
- 若要停止：`Get-Process python | Where-Object { $_.WorkingSet64 -gt 200MB } | Stop-Process -Force`
  （先确认没有别的 python 大进程在跑）
- 续跑：`--resume-from <某层>/aa_repetitions.csv` + **新的** `--run-root`，`PYTHONPATH` 指向 `out/aa_snapshot/src`
- **重启有固定开销**：`--keep-representative` 会让新 run-root 重新生成代表 rep 0 的完整五表（约 140 s CPU）

**已知缺口（必须在正式池化前补）**：本次重启时四层统一带了 `--no-negative-control`，
**L0 的 100 次负对照没有跑**。补跑命令：

```powershell
.\.venv\Scripts\python.exe -m causal_growth.evaluation.v3_aa --layers L0 ^
    --reps 1 --negative-control-reps 100 --quiet ^
    --run-root out\v3_phase_d_aa_formal_nc\L0 ^
    --summary-csv outputs\tables\v3_phase_D_aa_formal_L0.csv
```
`--reps` 不能设 0（CLI 无"只跑负对照"模式），故设 1：多跑 1 次真 AA（按 `[block, rep]` 去重，无害），
负对照完整 100 次，约 **3.9 CPU·h**。

---

## 交接（2026-10-28 04:10，北京时间）：F02 正式 200 rep 无人值守运行中

### 此刻机器上正在跑什么（三个后台进程，全部已验过判据）

| 进程 | 作用 | 日志 |
|---|---|---|
| shard0 pid 37612（03:39:18 起） | rep 0–49，`--status formal` | `out/logs/f02_formal_shard0_20261028_0339.log` |
| shard1 pid 21460（03:51:13 起） | rep 50–99 | `out/logs/f02_formal_shard1_20261028_0351.log` |
| `f02_chain.sh`（04:01 起） | 两个 PID 都退出后自动起 shard2（rep 100–149）与 shard3（rep 150–199） | 后台任务 `b5451iofv` |
| `f02_finalize.sh`（04:04 起） | 四分片各满 50 rep 后自动跑合并 + 证据导出 | 后台任务 `bddn07d0v` |
| `mem_watch.py`（03:51 起） | 每分钟记可用内存/进程 RSS/已完成 rep 数，可用 <1 024 MB 打 ALARM | `out/logs/f02_memwatch_20261028_0351.log` |

04:08 状态：已完成 5/200（shard0 3、shard1 2），可用内存 4.2–5.3 GB，无 ALARM。
04:26 状态：已完成 **10/200**（shard0 6、shard1 4），可用内存 2.8–3.5 GB，ALARM **0 次**。
04:47 状态：已完成 **16/200**（shard0 到 rep 9、shard1 到 rep 57），free 最低 **2 716 MB**，ALARM **0 次**。

ETA 已从假设改为实测投影：10 个已完成 rep 的 mean **460.8 s**（sd 64.8，min 366.4 = constant，
max 524.2 = causal_forest），2 并发 ⇒ 200 rep = **12.80 h**，95% 区间 **11.68–13.92 h**
（mean 的标准误 20.5 s），自 **03:39** 起算，合并再加约 5 min。
（**05:22 更正**：此处原写"自 03:45 起"；起跑实为 03:39:18，
凭据是 `snapshot_binding.json` 的 `created_at=2026-10-28T03:39:04+08:00` 与日志名
`out/logs/f02_formal_shard0_20261028_0339.log`。见 `docs/v3_phase_D03_formal.md` §11.2 的 P2-1。）

**（05:28 再更正：上面的 15:30–17:45 / 15:20–17:35 两个窗口都已被观测否证。）**
05:27 时 `reps_done=25`、自 03:39:18 起 108.1 min ⇒ 实测 **4.32 min/rep**（2 并发），
而不是 n=10 推出的 3.84 min/rep（460.8 s ÷ 2）。按 4.32 外推剩余 175 rep = 12.61 h
⇒ **~18:04 集齐**，比我 05:22 刚写进 GOAL.md 的上界 17:35 还晚 29 分钟。
**n=10 的样本偏乐观**（当时 causal_forest 占 60%、mean 460.8 s，标准误 20.5 s，
但 n=25 的实测速率已超出该标准误能解释的范围）。GOAL.md 与本文件均已改为 ~18:04。
**承诺不变：第一波 100 rep 完成时用 n=100 再复推一次。**
下游影响：D01 20 rep（92 分钟独占）最早起跑时间由 ~18:00 顺延到 **~18:15**。 **（2026-10-28 06:10 更新：n=35 实测每 lane 470.9 / 471.7 s/rep ⇒ 投影提前到 ~16:53，D01 最早 ~17:05；仍按承诺在 n=100 复推。）**
原记的 11–15 h 仍成立、收窄为上值；下界 11.68 h 与"D03 选模频率加权 ⇒ 11.7 h"几乎重合，
两条独立路径互证。**第一波 100 rep 完成时用 n=100 重推一次**（当前 n=10 的 causal_forest
占 60%，高于 D03 的 35.5%，但只差 +1.6 个二项 sd，不足以断言构成变了）。

### 运行期间的硬纪律

- `src/causal_growth/**/v3*.py`、`sql/v3*.sql`、`configs/v3*.yaml` **只读**（AGENTS §11）。
  分片每个 rep 前后都会重算 `pipeline_source_hashes()`，写这些路径会让作业抛
  `RuntimeError: source files changed during the data run`，**几个小时的运行会报废**。
- 不要跑全量 pytest（抢内存、且 1 264 项要 6 分钟）；不要起第三个分片（3 × 2.4 GB > 可用）。
- **`scripts/` 不被哈希，但不等于运行期可以改**（05:01 从 `snapshot_binding.json` 复核）：
  `snapshot_dirs=['src','sql','configs','scripts']`，而 `source_hashes` 的 48 个文件是
  src 37 + configs 9 + sql 2，**`scripts` 下 0 个**。两条自动化走的是不同路径：

  | 自动化 | 实际执行 | 改仓库同名文件的后果 |
  |---|---|---|
  | 分片 `out/scratch/f02_shard.sh:17` | `$SNAP/scripts/29_f02_formal.py` | 无影响（快照副本） |
  | 收尾 `out/scratch/f02_finalize.sh:45` | `$REPO/scripts/30_merge_f02_formal.py` | **直接换掉无人值守合并要跑的代码** |

  ⇒ 运行期不改 30 号脚本（含 §12.7 那类加固），全部推迟到合并后待做 ⑥。
- 也不要动正在被后台复审代理读取的 `docs/v3_phase_D03_formal.md`（05:03 起有独立复审在跑，
  输出 `docs/reviews/v3_phase_D03_rereview.md`）。

### 合并完成后必须人工做的五件事（已登记在 TODO.md「合并后待做」）

1. **把 F02 证据登记进顶层 `outputs/evidence/coverage.json`**：30 号脚本只在自己的
   `--evidence-dir` 写 `coverage.json`（`:186`），**不刷顶层索引**——与 03:13 给 31 号脚本补的
   `_refresh_top_registry` 同类缺口。**04:24 做好工具、04:49 按 30 号的真实形状演练过**：
   `out/scratch/register_evidence_top.py`（身份类 JSON 规则提升 + 提升前逐文件重算 sha256/bytes
   + 提升后全表复算 + 幂等 + 只追加不重排 + 四种目录级 schema + 读不懂就硬失败），合并后跑
   `.venv/Scripts/python.exe out/scratch/register_evidence_top.py --dirs f02_formal --dry-run`
   再实跑即可，**期望新增 4 条**（decision/freeze/manifest/five_tables-manifest，
   kind=`f02_formal_*`、status=`formal_r200`）。
   该脚本已用它把 `d03_formal` 与 `f02_n200k_rep0` 补进顶层（35 → 41 条，既有 35 条逐条与顺序未变）。
   **注意它在 `out/` 下、不入库**；可入库的长期形态是下面第 5 条。
   演练细节与 6 例结果见 `docs/v3_决策与反思日志.md` 04:52 条。
2. **读回**合并产物（不是手工复核口径——30 号脚本已强制）：
   `outputs/tables/v3_phase_F02_formal_*.csv`（7 张）+ `_summary.json`，以及 `outputs/evidence/f02_formal/`；
   确认 `formal_approval=F02-FORMAL-20261028-R200`、`config_hash=e1aa4314b8d84b04…`、
   `source_hashes_sha256=d8327ae0a190a5c2…`。这三项跨分片一致性**已由 `:231-251` 强制**，
   不一致会在合并时抛错、根本产不出表；`:112-120` 的 `_read_shard_summary` 又在任何写盘之前跑
   （缺 `summary.json` / `status != formal` / `failures` 非空都抛），所以这一步只是把已落盘的数字读回来。
3. 写 `docs/v3_phase_F02_formal.md` 正文（聚合按 rep 配对报告通过率，**不合并 p 值**），
   并补 D03 §11.2 程序豁免记录。
4. **D01 20 rep**（独占机器，~92 min）：
   `.\.venv\Scripts\python.exe scripts\13_v3_pilot.py --scenario L1_main --n 200000 --reps 20 --start-rep 0`；
   产物 `out/v3_phase_d/pilot_raw_L1_main_n200000.csv`（每 rep 增量落盘），
   跑完另存 `outputs/tables/v3_phase_D_pilot_raw_r20.csv`，**不覆盖** R=3 旧表。
   并行方案已否决（理由见 `docs/v3_决策与反思日志.md` 04:07 条）。
   按 04:26 实测投影，最早 **~18:00** 可起（17:45 上界 + 合并约 5 min）。
5. **机制修复（合并后连全量测试一起做）**：让 `scripts/27_export_d03_evidence.py` 与
   `scripts/30_merge_f02_formal.py` 自带顶层刷新（复用 31 号 `_refresh_top_registry` 的口径），
   否则 G/H 阶段会第三次踩同一个坑。运行期不改脚本。
   顺带把 30 号的 evidence `coverage.json` 记录补三点（04:52 演练时查出）：
   ① 加 `kind`；② `path` 改名或并列 `target`（顶层惯用 `target`）；
   ③ `source` 现在指向 `out/f02_formal/shardX/rep0/...`，而 `out/` 不入库，
   评审者跟着它会扑空——应改成可复算来源（快照 + rep 0），与它自己 `excluded` 里的说法一致。
   补完这三点，第 1 条那个 `out/scratch/` 里的临时工具就可以退役。
   另记：`registry_repairs[1]`（03:06）的 `total_bytes_before` 与 `reason` 是
   `out/scratch/fix_evidence_registry.py:100/:102` 的**硬编码常量**、不是实测前值，
   缺陷已登记在 04:24 条目的 `prior_entry_defects`，历史条目未改写。

### 还欠着什么

- `git push origin codex/d03`：03:38 推上 `e004810..7870b9a`，04:09 推上 `7870b9a..111f19b`，
  04:50 推上 `111f19b..3457f85`（此前 04:44/04:46/04:47 三次 `Connection reset` / `port 443` 超时）；
  现在 `codex/d03` 与 `origin/codex/d03` **齐平**，无待推提交。
  **push 后等用户 review，不要自行合并。**
  仍**没有**装无人值守的后台 push 重试循环——那是网络可见动作，不该在无人看管时反复触发。
- E01/E02、F01 **仍标"未证实"**：用户 01:10 的"默认批准"按**批准运行**执行，
  不按"批准关闭缺陷"执行；这两项只能由独立复审关闭（AGENTS §7.4），复审 05:13 / 05:10 已起飞。
  **D03 已于 05:15 经独立复审 PASS 关闭**，GOAL.md 的验收表 / R01 / 交接节点三处已在 05:21–05:22 同步；
  复审另提的 4 项 P2 已由主负责逐项核实并修正（`docs/v3_phase_D03_formal.md` §11.2）。
- E 的 meta 缺 `cfg.hash(64)`（=`e1aa4314b8d84b04…`）：补齐要改 `scripts/24_e_evidence.py`
  并重跑约 50 min/家族，刻意留到 F02 之后。
