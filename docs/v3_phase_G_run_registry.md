# G 阶段运行注册表（2026-10-29 11:20，北京时间）

> 合成数据 / 已知 DGP。本表对应 GOAL G04「失败重试 / 资源 / 真实进程记录，全入口可恢复」。
> **状态：进行中**——**G01 已于 2026-10-29 11:00 改判"通过"**（第三轮窄复评 5/5 P2 关闭、0 新增 P0/P1，§2.5）；
> 用户已裁决预算 **A 保持范围**（222.6 h）并**批准 G02 + G03 正式跑**；
> **G02 首轮（10:09）在第 2 个 b 全灭，已修并在 10:39 用新快照重开**（10:53 越过 b=1；ETA 16:15–17:30，§2.5），其后由 `out/g03_chain.sh`
> 串行接 G02 固定 bootstrap（§2.4 阶段 A）与 G03 矩阵（阶段 B，24 格）。
> 每次改动都要写清时间与依据；不得用"应该没问题"代替实测记录。

## 1. 运行清单

| 编号 | 运行 | 批准号 | 状态 | 快照 | 起跑（北京时间） | 预计/实际结束 |
|---|---|---|---|---|---|---|
| G01 | AA 臂 4 层 × 250 = 1 000 rep，n=200 000 | `G01-AA250-20261028` | **跑完；评审 PASS WITH CONDITIONS（0 P0/4 P1/9 P2），条件 10:10 全关，待复评确认改判** | `out/g01_snapshot`，49 文件 `526ff53d56a54c75…` | 2026-10-28 22:42:39 | 实际 **2026-10-29 05:15:38（末片）/ 05:15:45（编排器）**，墙钟 6 h 33 m |
| G02 | 重训 200（4 格 × 50）+ 固定 bootstrap 1 000（主预算） | `G02-FORMAL-20261029`（用户 10-29 批准；预算方案 A） | **正式跑进行中**（10:09:04 起，4 格并行，每格 50 b） | `out/g02_snapshot`，49 文件 `f39ec0a3…` | 2026-10-29 10:09:04 | 预计 15:30–17:00（按 411 s/b） |
| G03 | Tier2 20 格 × 30 + 4 core 格 | 待批（正式）；R=1 实测无需批准 | **R=1 完成**（engineering，L1_main + L3_overlap_extreme，`out/g03_r1`）；正式未启动 | 未建 | 2026-10-29 06:10:55 | 06:23:39（12 m 44 s） |
| G04 | 本注册表本身 | — | 进行中 | — | — | — |

## 2. 真实进程与资源（G01）

- **并行方式**：`--workers` 上限 = 层数（一层一进程），故 6 路采用 **rep 区间分片 + 独立 out-root**：
  `s01:L0[0,83) s02:L1[0,83) s03:L0[83,166) s04:L1[83,166) s05:L0[166,250) s06:L1[166,250)`
  `s07:L2[0,83) s08:L3[0,83) s09:L2[83,166) s10:L3[83,166) s11:L2[166,250) s12:L3[166,250)`
- **每条 lane 顺序跑 2 个分片**，共 6 lane / 12 分片；编排 `out/g01_runner.sh`（日志 `out/g01_logs/`）。
- **实测成本（10:38 复评更正）**：正式跑 1 000 rep 的 `total_cpu_s` 中位 **136.594 s**、p5–p95 **134.324–141.815**、
  min–max **128.672–181.375**，仅 **67.4%** 落在 [132,137]；此前写的「132–135 s/rep」是 6 路前的估计，不是实测分布。
- **实测资源**：6 路压力测试峰值 **10.69 GB**（全部 python 进程 RSS 之和），单进程最大 **2 003 MB**，
  同期空闲 8.82 GB；未出现 OOM 或进程被杀。
- **进程级证据**：每个分片的退出码落在 `out/g01_logs/<shard>.exit`（缺失即视为未完成），
  分片的 Python 日志带北京时间时间戳。**已知缺陷**：runner 里 `date` 落盘是 UTC（少 8 h），
  故引用时刻只用 Python 日志。
- **跑中健康检查（23:00）**：12 个 python 进程、合计 3.82 GB、单进程峰值 815 MB、空闲 14.76 GB；
  6 条 lane 进度一致（各完成 5 rep）；`grep` 全部分片日志**无** Traceback / 源码漂移 / 重试记录。

## 2.1 G02 A 臂 R=1 实测（2026-10-29 05:41:21–06:09:16，engineering，EXIT=0）

- **口径**：4 个 core 格 × 1 b × n=200 000；`out/g02_retrain_r1`；`status=engineering`，**不得**作为正式凭据。
- **每 b 成本（CPU s，history / fit / validation）**：

  | 格 | 选中模型 | history | fit | validation | 合计 |
  |---|---|---|---|---|---|
  | L0_P_main | t_learner | 101 | 117 | 122 | **340** |
  | L1_main | causal_forest | 101 | 136 | 234 | **471** |
  | L2_n200000_p050 | s_learner | 101 | 123 | 126 | **350** |
  | L3_fixed_lt000 | causal_forest | 101 | 146 | 236 | **483** |

- **均值 411 s/b**；按 200 b 外推 **≈22.8 h**（预算口径 13.3 h = 240 s/b，**超 1.7 倍**）。
  单 b 每格只 1 次，选中模型不同会让单次成本在 340–483 s 间波动；区间外推 18.9–26.8 h。
- **门槛结论**：实测已超 §6.1 的 320 s/次 硬门禁 ⇒ 正式跑前必须重报预算（见 §2.2 与决策单 §H.2）。
- 墙钟 27 m 55 s（4 格串行），无重试、无源码漂移；`validation_observed_hash` 每格独立。
- 亲历缺陷：无（39 号首次在真树以注册 n 运行）。

## 2.2 G03 R=1 实测（2026-10-29 06:10:55–06:23:39，engineering，EXIT=0）

- 口径：`L1_main`（Tier1 core）+ `L3_overlap_extreme`（Tier2）各 1 rep，n=200 000，`out/g03_r1`。
- 每 rep 遥测（pipeline / estimate / models，秒）：L1_main（dr_learner）99.72 / 0.39 / 262.11；
  L3_overlap_extreme（t_learner）102.36 / 0.36 / 277.06。
- 外推：core **23.97 h/格** × 4 = 95.9 h；Tier2 **3.16 h/格** × 20 = 63.3 h；矩阵 **159.2 h**（原 149.4，+6.5%）。
- 总账：40.6 + 22.8 + 159.2 = **222.6 h vs 上限 210（+6.0%）**；方案见决策单 §H.2。
- **失败记录**：首次调用把两格写成逗号分隔（`--cells L1_main,L3_overlap_extreme`），
  34 号 `--cells` 是 `nargs="*"`，整串被当成一个 id，5 s 内 `ConfigError` + EXIT=1；
  改空格分隔后成功。失败方向正确（坏输入不静默）。


## 2.3 G02 正式跑真实进程（2026-10-29 10:09:04 起，进行中）

- **并行方式**：4 个 python 进程 = 4 个 core 格（`L0_P_main` / `L1_main` / `L2_n200000_p050` / `L3_fixed_lt000`），
  一进程一格、每格 50 b 顺序跑；39 号本身单线程，没有 `--workers`。
- **命令（每格一份，仅 `--cells` 不同）**：
  `scripts/39_g_retrain_bootstrap_run.py run --status formal --formal-approval G02-FORMAL-20261029 --snapshot out/g02_snapshot --out-root out/g02_retrain --cells <cell>`
- **快照**：`out/g02_snapshot` 49 文件 `f39ec0a3…`；39 号运行前用 `_verify_snapshot` 与真树逐文件比对。
- **日志与产物**：`out/g02_logs/<cell>.log`；每格 `out/g02_retrain/<cell>/repetitions.csv` + `run_state.json`；
  断点入口 `--resume`（按 `run_state.json` 的 b 列表续跑）。
- **ETA 依据**：R=1 顺序实测 340/471/350/483 s/b × 50 ⇒ 4.7–6.7 h/格；但 **10:20 首个 b 的实测墙钟约 11 min**
  （CPU 369–532 s/b，4 路并行互相抢核）⇒ 实际 **~9.2 h/格**，ETA **19:20–20:30**。
  两种口径都留着：前者是顺序成本，后者是并行墙钟；排期用后者。
- **内存纪律**：G03 不与之并行启动，避免 8 进程同时逼近 19.5 GB。
  串行由 `out/g03_chain.sh` 强制：它先等 `out/g02_logs/post.status` 出现 `OK:`，再建快照并开下一段。

## 2.4 G02 固定 bootstrap + G03 矩阵（串行链 `out/g03_chain.sh`，2026-10-29 10:19 起）

- **为什么要拆两段**：`v3_g_matrix.py:959` 在 `bootstrap_resamples>0` 且 `rep != 0` 时抛错，
  而 34 号的任务粒度是"一格 × 一段 rep"。所以带 1 000 次 bootstrap 的分片只能是 rep 0 单点，
  不能与 30/500 个 rep 混在一条任务里。
- **阶段 A（G02 固定 bootstrap 臂）**：24 格 × rep 0，`--bootstrap-resamples 1000
  --bootstrap-budget-scope primary_0.2 --shard-size 1 --workers 6 --out-root out/g02_fixed
  --summary-dir out/g02_fixed/summaries`，批准号 `G02-FORMAL-20261029`。
  产物：`out/g02_fixed/shards/<cell>_s0000/<cell>/rep0/validation/fixed_bootstrap.csv`
  （列：`rep,budget_cny_per_user,resamples,…`，budget 恒为 0.2）。成本约 3.3 CPU·h / 6 路 ≈ 40 min。
- **阶段 B（G03 矩阵臂）**：24 格 × 注册 R（core `R_ate=500` / Tier2 `R=30`），
  `--workers 6 --shard-size 50 --out-root out/g03_formal --summary-dir outputs/tables`，
  批准号 `G03-FORMAL-20261029`，`bootstrap_resamples=0`（bootstrap 已在阶段 A 交付）。
  成本按 §H.2 实测外推 **159.2 CPU·h** ⇒ 6 路约 **26.5 h**。
- **34 号补丁（10:16）**：`--bootstrap-budget-scope` 贯通 CLI → task → `_worker` → `run_cell`；
  `formal + resamples>0 + scope≠primary_0.2` 在 argparse 层直接失败（不新建目录）；
  `run_summary.json` 回写 `bootstrap_resamples`/`bootstrap_budget_scope`。守卫本身未改。
- **快照**：链内 `create_snapshot("out/g03_snapshot")` 于阶段 A 前生成；A/B 共用同一绑定。
- **状态文件**：`out/g03_logs/chain.status`（`fixed_exit=` / `g03_exit=` / 末行 `OK:`）；
  日志 `out/g03_logs/chain.log`、`g02_fixed.log`、`g03.log`。
- **环境事实**：本机 Git Bash `TZ=Asia/Shanghai date` 输出 UTC（实测 10:18→02:18），裸 `date` 才是北京时间；
  链条与状态文件一律用裸 `date`/`zoneinfo`。

## 2.5 G02 首轮全灭与重开（2026-10-29 10:15–10:39）

- **事实**：10:09:04 起的 4 个 core 格，10:15–10:26 依次在 b=1 抛
  `RuntimeError: <cell> b=1 的验证帧哈希与 b=0 不同：验证帧被重抽了`；每格只写出 b=0（4 行），b=1 行未落盘。
- **根因**：39 号的冻结断言用 `validation_observed_hash`（= 整张观测表 `content_hash`），
  而观测表含 `issued_action`——它由该 b 重训出的模型打分决定，跨 b 必然不同。
  验证队列本身确定：同一 rep 的 `generate_covariates(..., population_kind="validation")` 两次生成逐字节相同。
  即：**守卫的失败方向正确（没写出坏行），但断言的指纹对象选错了**（设计档 §6.1.a 第 2 条同步更正）。
- **修法**：`run_validation_arm` 增 `validation_frame_hash`（用户协变量）与 `validation_arm_hash`
  （`user_id`/`assigned_policy_arm`/`policy_arm_probability`）；39 号断言这两个，观测哈希仅逐 b 记录；
  续跑遇旧表缺列 `SystemExit`。新测试 `tests/test_v3_g02_frozen_frame.py`（10:46 扩到 6 例，含合并守卫）；
  **全量单进程串行 pytest EXIT=0**（10:29–10:38，`out/pytest_g02fix_20261029_1029.log`），修 merge 后
  定向测试 9 passed。
- **10:46 补修同一坏指纹的第二处**：`command_merge` 仍断言 `validation_observed_hash` 唯一，会在收尾合并时必败。
  已改 `check_merge_frame`（b 不重复 + 两个新指纹唯一 + 缺列即拒），并用失败现场实跑验证被拒（exit=1）。
- **10:53 越过失火点**：L0_P_main 写出 b=1；两个新指纹跨 b 唯一（各 1 个值），观测哈希 2 个值。
  实测 b=0 每格 386–562 s CPU、b=1 约 6.5 min ⇒ ETA **16:15–17:30**。
- **10:48 收尾看护**：`out/g03_post.sh` 等 `chain.status` 的 `OK:`，自动跑 40/41 `--check` + 导出；
  顶层登记（33 号）留人工。
- **重开**：新快照 `out/g02_snapshot` **49 文件 `abaa338a0c7705ae…`**（`v3_g_matrix.py` `6ec009b6…`），
  10:39:20 四格从 b=0 重跑，ETA **19:20–20:40**。旧快照与旧产物保留为
  `out/g02_snapshot_failed_20261029_1026/`、`out/g02_retrain_failed_20261029_1026/`（含 `failure_logs/`）。
- **收尾链更新**：`out/g02_post.sh` 改为断言两个新指纹、b 唯一、status=formal，停滞 3 h 即 `STALL:`；
  `out/g03_chain.sh` 把 `STALL/TIMEOUT/VERIFY FAIL/merge_exit≠0` 都当失败（10:39:57 重启，PID 1493）。
- **复评记录（G01，三环闭合）**：两轮独立复评**并行**落到同一路径
  （`docs/reviews/v3_phase_G01_review2.md`），结论一致——P1 4/4 关闭、数据零不符、P2 未清零，当时不改判；
  落盘为准的是 10:38 版（364 行），另一版备份在 `out/review_g01_2/parallel_draft_backup_1029.md`（不入证据区）。
  随后 5 条 P2 于 10:44 前全部落地（`daf9d80`）；**第三轮窄复评 10:56 判 5/5 关闭、0 新增 P0/P1**
  （`docs/reviews/v3_phase_G01_review3.md`），4 条文字级 P3 同日修完。据此 **GOAL G01 于 11:00 改判"通过"**，
  边界：非新的独立 AA 样本、CP 下界低于预设带、0.81/0.96 为解析功效、不表示策略有效。

## 3. 失败重试与可恢复入口

| 入口 | 重试参数 | 断点续跑 | 备注 |
|---|---|---|---|
| `scripts/34_g_matrix_run.py` | `max_source_retries`（数据作业内） | `--resume` | 网格 / 单格；`plan|run|merge`。**限制（2026-10-29 10:26 只读核实）**：`--resume` 只认分片目录里的 `repetitions_provisional.csv`；**已写正式 `repetitions.csv` 的分片会被整片重跑**（正确但浪费）。G04 要么让 `--resume` 也认正式表并校验 `(rep, config_hash)`，要么在文档里明确"已完整分片重跑" |
| `scripts/36_g_aa_run.py` | 同上 | `--resume`（`_resume_source` 按 mtime 取该层最近的完整表） | AA 专用；`plan|run|merge` |
| `scripts/17_merge_aa_layers.py` | 无（纯合并） | 幂等：重跑覆盖同名产物 | 多根合并 + `(block, rep)` 去重 |
| `scripts/37_export_g01_evidence.py` | 无 | 幂等：重跑覆盖证据目录 | `--check` 只复算不写盘 |

**重跑纪律**：17 号合并会覆盖 `outputs/tables/v3_phase_D_aa_formal_merged.*`（D 阶段同名产物）；
D 阶段原字节已归档到 `outputs/evidence/d02_aa_phase_d_20261027/`（8 文件 + manifest.json，含 sha256/bytes），
任何重跑后都必须先确认该归档仍在，再引用 D 阶段数字。

## 4. 复现验证（G01 完成后回填，2026-10-29 05:35 全部通过）

- [x] `out/g01_verify.py`：12 分片拼成 4 层 × 250、无重复/缺口、`n_total`/`alpha`/`protocol_config_hash` 唯一（`verify.exit=0`，`verify.log` 逐层 `rows=250 unique_reps=250`）
- [x] `scripts/17` 合并表与 `scripts/37` 独立复算逐格差 ≤ 1e-12（实测最大绝对差 **6.939e-18**）
- [x] 12 个 `.exit` 全 0（s01–s12 逐片 0；`merge.exit=0`）
- [x] 证据导出 + 顶层登记（`scripts/33`）exit 0（`export.exit=0`、`register_dry.exit=0`、`register.exit=0`；
  **10:06 补记**：05:16 时点顶层 77→89、16.92 MB；10:06 增登 `runs_summary.json` 后为 **91 条 / 16 964 194 B**）
- [x] G01 报告 `docs/v3_phase_G01_formal.md` 的每个数字都能从 `outputs/evidence/g01_aa250/` 重建
  （**10:06 补记**：59 条登记 / 60 个磁盘文件（含 `coverage.json`）/ **1 275 048 B** / 1 000 行逐 rep；
  05:35 时点的「45 文件 / 1.3 MB」是补 `runs/` 与 binding 之前的数）

### 4.1 必须披露（05:30）

本次 17 号合并表 sha256 `2c6d6e91bf4b89ea…` 与 D02 归档件
`outputs/evidence/d02_aa_phase_d_20261027/v3_phase_D_aa_formal_merged.csv` **逐字节相同**，15 行拒绝数全同。
已证伪"读错旧产物"（37 号从本次 24 张分片表重算，差 6.9e-18；verify 逐层 250 unique reps）。
成因是确定性：同 `master_seed` + 逐 rep 种子派生 + AA 路径未变。
⇒ **本次不是第二个独立样本**；要检验源码漂移对 AA 的影响必须换种子（另立实验）。
另注：正因 CSV 逐字节相同，`git` 对该文件**无差异**，本次入库只改了 `.json`（含 roots 等元数据）。

## 5. 跑完后的命令序列（照抄即可，全部在项目根目录执行）

```bash
# 0) 看收尾链是否已自动完成（OK / ABORT）
cat out/g01_logs/post.status

# 1) 若 post 链 ABORT 在导出步，手动顺序执行（先看日志再重跑，幂等）
.venv/Scripts/python.exe scripts/37_export_g01_evidence.py
.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g01_aa250 --dry-run
.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g01_aa250

# 2) 出报告数字（只读；末行给出"复算 vs 17 号表"的最大绝对差，必须 ≤1e-12）
.venv/Scripts/python.exe out/scratch/g01_report_numbers.py

# 3) 用数字填 out/scratch/g01_report_skeleton.md 的两张表，写成 docs/v3_phase_G01_formal.md
# 4) 翻 GOAL G01 行（"未证实"→"通过"，并写明合并判定与逐层只作描述）
# 5) 刷新 TODO.md / docs/v3_决策与反思日志.md / AGENT_HANDOFF.md / 本注册表 §4 清单
# 6) 提交并推送（推送此前连续 3 次 443 超时，网络恢复后重试）
git add -A && git commit -m "G|g01: 正式 AA 1000 次完成，报告与证据入库"
git push origin codex/d03
```

**禁止**：在导出/登记未成功前把 G01 记成"通过"；在 `out/g01_logs/*.exit` 未齐 12 个 0 之前做合并结论。

## 6. G02/G03 收尾命令序列（2026-10-29 11:20 预置；链条结束后照抄）

```bash
# 0) 先看三个状态文件（OK / STOP / VERIFY FAIL / TIMEOUT）
cat out/g02_logs/post.status out/g03_logs/chain.status out/g03_logs/g03_post.status

# 1) G02 证据：先 --check 再导出（staging + 原子换名，旧目录留时间戳备份）
.venv/Scripts/python.exe scripts/40_export_g02_evidence.py --check
.venv/Scripts/python.exe scripts/40_export_g02_evidence.py

# 2) G03 + 固定 bootstrap：g03_post 已自动跑过这两步，幂等可重跑
.venv/Scripts/python.exe scripts/41_export_g03_evidence.py --check
.venv/Scripts/python.exe scripts/41_export_g03_evidence.py

# 3) 报告数字（只读；与 39 合并表 1e-9 对账，异常 exit 2）
.venv/Scripts/python.exe out/scratch/g02_report_numbers.py

# 4) 填 docs/v3_phase_G02_formal.md §3/§4、docs/v3_phase_G03_formal.md §2–§4
# 5) 顶层登记：先 dry-run，人工复核 coverage.json 的 sha/bytes 后再正式执行
.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g02_formal g03_formal --dry-run
.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g02_formal g03_formal

# 6) 翻 GOAL G02/G03 行，刷新 TODO / 决策日志 / AGENT_HANDOFF / 本注册表，提交推送
```

**续跑（任何阶段失败时）**：`--resume` 只救"半途被杀、留下 `repetitions_provisional.csv`"的分片；
已完成分片会整片重跑。正确做法：先 `34 merge` 收已完成 → 缺口另起根重跑 → 多根 `merge` 且 `duplicates=0`。
见 `AGENT_HANDOFF.md` 第 6 条与决策日志 2026-10-29 11:15 条。
