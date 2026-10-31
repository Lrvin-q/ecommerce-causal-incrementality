# v3 G04 独立评审：失败重试 / 资源 / 真实进程记录 / 全入口可恢复

- 评审时间：2026-10-31 20:35（北京时间；下文时间均取自日志内部时间戳，不看文件 mtime）
- 评审基线：`codex/d03`，起点 HEAD `2519b11`；评审期间 H04 代理于 20:30:42 提交 `f52d663`，20:32:21 在 `f52d663` 上重跑 49 仍 RC=0 READY（290 claim）。工作目录 `C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目`
- 评审性质：独立评审。未参与 G04 实现，未参与 G03 运行，未重跑 G03。
- **结论：PASS WITH CONDITIONS**（0 P0 / 1 P1 / 4 P2 / 5 P3；5 条关闭条件 C1–C5）

> 读法：本文每个"成立"都给出本次复算命令与输出；文档只用于定位，不作为证据。
> `scripts/63`、`scripts/66` 会改写证据/产物，本次未重跑，改用"日志内部时间 + 字节同一性 + 全表复算"核验。
> 本次评审期间有另一 H02/H04 代理在并发改 `paper/` 与 `outputs/tables/`，已在 §5 披露。

## 1. 结论与判据表

| # | 待核验断言 | 判定 | 独立证据（本次复算） |
|---|---|---|---|
| 1 | `49` RC=0 READY；是否覆盖证据登记双向校验 | **部分成立** | 20:21:54 与 20:32:21 两次 RC=0 READY（均 290 claim，后者在 `f52d663`）；目录级双向校验成立，顶层"磁盘有、索引无"只报"新增"不失败（P2-3） |
| 2 | `62` 篡改→复原演练是真的 | **成立** | 本次重跑 RC=0：基线 41 EXIT=0 → 注入重复 rep → 41 EXIT=2 → 复原 → 通过 |
| 3 | `63` 六步全 0，且取日志内部时间 | **成立** | `finalize.status` 六个 `*_exit=0` + OK 19:48:27；`finalize.log:199-239` 内部时间 19:48:04–19:48:27 |
| 4 | `66` 重导出字节一致；coverage 357 / 5,254,002 | **成立** | `finalize.log/status` 与证据包副本 sha256 完全相同；357 条独立复算 0 不符、总字节 5,254,002 |
| 5 | 失败/重试记录（G03 阶段 A 17:51、Phase 2 2a/2b/复合） | **成立** | 阶段 A 归档 `run_summary.json` 记 17:51:26 `NotImplementedError`；复合 summary 三源哈希全 MATCH |
| 6 | 资源 2,600 rep / 201.86 CPU·h / 磁盘 69 G / 内存监控 | **成立，但口径受限** | 复算 2,600 行、201.8558 h、均值 279.49 s、最大 1,318.12 s；磁盘 13G/41M/491M、余 69G；监控只到 10-30 14:21（无 Phase 2 连续采样） |
| 7 | 全入口可恢复（run_all、G01/G02/G03、finalize、证据、论文、pytest） | **部分成立** | 49/62/63/66/41/33/40 均可重跑；未做从零端到端；最终编辑后无全量 pytest；`run_all` 只覆盖第 1–3 轮 |
| 8 | 校验器只加强、未删检查/未放阈值/未 raise→warn；16 例夹具 | **基本成立** | `1b50641` 中 41 自检仅抽函数、33 增 `abs_path`、49 仅改文案；25 例相关测试全过；但两处门禁缺口无夹具 |
| 9 | 真实进程记录 vs 叙述 | **部分成立** | phase2/finalize 日志与状态真实；PID 1507、`[auto] 63 exit=0` 属叙述/日志陷阱（P3-1、P3-2） |

## 2. 独立核验

### 2.1 `49` 收尾体检：READY 可复现，但不等于"收尾完成"

本次命令：

```bash
.venv/Scripts/python.exe scripts/49_g04_closeout_precheck.py \
  --with-check --with-register --with-claims
```

输出（`out/scratch/g04_review_49_rerun.log`，内部时间 2026-10-31 20:21:54，RC=0）：

```
[OK ] g02_post.status 含 OK：OK: G02 merge 完成 2026-10-29T17:17:51+08:00
[OK ] phase1.status 含 OK：OK: G03 Phase1 core prefix 完成 2026-10-30 05:55:41
[OK ] phase2.status 含 OK：OK: G03 Phase2 完成 2026-10-31 19:33:21
[OK ] g03 24 格 repetitions.csv 全部达 R
[OK ] 源码 49 文件与 g03 快照逐文件一致
[OK ] 42 claim gate EXIT=0
OK：290 条 claim 全部回指且与源表复算一致（Tier1 290 / Tier2 0）
[OK ] 41_export_g03_evidence.py --check EXIT=0
[INFO] 33 --dry-run EXIT=0（全表复算一致；实登记已于 19:48 完成）
[top-reg] 候选身份类文件 2 个：新增 0，已登记 2
[top-reg] 顶层全表复算一致：93 条
[VERDICT] READY：可进入 33 登记与报告填数
```

- 该次运行前后，`v3_h04_claim_registry.csv` / `03_results.md` / 顶层 `coverage.json` 的 sha256 完全不变（`out/scratch/g04_review_hashes_{before,after}.txt`）；49 本身只读。
- 证据包内权威日志 `outputs/evidence/g03_formal/logs/g49_full.log` 为 20:01:41、274 claim、READY；本次 20:21:54 为 290 claim（H04 新增 C275–C290 后的工作树），20:32:21 在 H04 提交 `f52d663` 上再跑一次仍为 290 claim、READY（`out/scratch/g04_review_49_rerun_postcommit.log`）。三次均 RC=0。
- **但** 49 的 `check_statuses()` 只读 `g02_post` / `phase1` / `phase2` 三个文件（`scripts/49_g04_closeout_precheck.py:44-46`），**不读 `finalize.status`**。实测 19:34:26 的 49 在 `33 dry-run 失败 rc=2`、63 实际 ABORT 之后仍判 READY（`out/g03_logs/auto_finalize.out` 末段；`auto_finalize.log:8` 的 `[auto] 63 exit=0` 是 tee 退出码，非 63 真实 RC）。因此"49 READY"只能证明 Phase 门与证据门，不证明收尾链完成，见 P2-1。

### 2.2 `62` 篡改→复原演练：真实三步，RC=0

本次重跑 `scripts/62_g04_tamper_drill.py`（只写 `out/scratch/g04_tamper_drill`，结束即删）输出：

```
[OK ] 演练根已建：out\scratch\g04_tamper_drill（24 格逐 rep 表副本）
[OK ] 基线 41 --check EXIT=0
[INFO] 注入篡改：shards\L0_P_main_s0000\L0_P_main\repetitions.csv 两行 rep 相同
[OK ] 篡改被拒：41 EXIT=2（('L0_P_main','ate_any_refund_30d')/sd: 复算 0.0004638733... != 汇总 0.0004628650...）
[PASS] 失败被发现、复原后重新通过（G04 演练完成）
RC=0
```

日志：`out/scratch/g04_review_62_rerun.log`；19:48 正式链内的同款演练见 `finalize.log:204-210`。判定成立。唯一瑕疵是断言用 `"rep" not in out`（`scripts/62_g04_tamper_drill.py:128`），路径/文本只要含 rep 就可能误放行，见 P3-4。

### 2.3 `63` 收尾链：六步全 0，内部时间自洽

`out/g03_logs/finalize.status`（140 B）：

```
check_exit=0
drill_exit=0
export_exit=0
register_dry_run_exit=0
report48_exit=0
register_exit=0
OK: G03 finalize 完成 2026-10-31 19:48:27
```

`out/g03_logs/finalize.log:199-239` 的内部时间：19:48:04 第 1 步 → 19:48:06 62 演练 → 19:48:15 导出 357 文件/5,252,227 B → 19:48:23 33 dry-run → 19:48:24 48 取数 → 19:48:26 33 实登记 → 19:48:27 通过。该文件同时保留三轮失败/重试记录：19:34（33 rc=2）、19:35（重试）、19:36（实登记 92→93），是"失败要响 + 重跑可恢复"的直接证据。判定成立；本次未重跑 63。

### 2.4 `66` 收尾后重导出：字节同一，coverage 全表 0 不符

```bash
sha256sum out/g03_logs/finalize.log outputs/evidence/g03_formal/logs/finalize.log
sha256sum out/g03_logs/finalize.status outputs/evidence/g03_formal/logs/finalize.status
```

```
40b23e1d7089b06580b929982165af85f003f051d4afb7f73ee6e4b468d05415  out/g03_logs/finalize.log
40b23e1d7089b06580b929982165af85f003f051d4afb7f73ee6e4b468d05415  outputs/evidence/g03_formal/logs/finalize.log
35be47c6416fb0f83018d5c7a053c0f097e45836e0419c605196193ea32861ce  out/g03_logs/finalize.status
35be47c6416fb0f83018d5c7a053c0f097e45836e0419c605196193ea32861ce  outputs/evidence/g03_formal/logs/finalize.status
```

证据包日志 240 行 / 12,900 B，末行含 `[2026-10-31 20:01:53] 6/6 收尾后重导出`；`out/g03_logs/post_finalize_export.status` = `post_finalize_export_exit=0`。coverage 独立复算（不调 41）：

```
outputs/evidence/g03_formal/coverage.json records 357 declared_total 5254002 sum_disk 5254002 bad 0
outputs/evidence/coverage.json          records 93  declared_total 16975748 sum_disk 16975748 bad 0
```

日志：`out/scratch/g04_review_coverage_recompute.log`。另 `41 --check`、`40 --check` 本次均 RC=0（`out/scratch/g04_review_41_check_g03_utf8.log`）。判定成立。

### 2.5 失败/重试记录：阶段 A 与 Phase 2 均可复算

- **G03 阶段 A 17:51 失败**：`out/g02_fixed_attempt1_20261029_1751/run_summary.json` 记 `status=formal`、`all_complete=false`、`at=2026-10-29T17:51:26+08:00`，`failures[0]` = `L1_cost_prediction_under` / rep 0 / `NotImplementedError`（成本乘子 0.8 未实现）。归档目录 `out/g02_fixed_attempt1_20261029_1751`、`out/g03_snapshot_attempt1_20261029_1751` 均在；18:05–18:37 修复后重跑 `fixed_exit=0`（`docs/v3_phase_G03_formal.md:45-46`）。
- **Phase 2 2a/2b/复合**：`out/g03_formal/run_summary.json` 记 `composite=true`、`status=formal`、`failures=[]`、`all_complete=true`，`derived_from` 三份源 summary 的 sha256 与磁盘逐一 MATCH：

```
out/g03_core_prefix/run_summary.json  declared 6a928a88f68545c3  disk 6a928a88f68545c3  MATCH
out/g03_tier2/run_summary.json        declared 4d2c53347375bdb6  disk 4d2c53347375bdb6  MATCH
out/g03_core_ate/run_summary.json     declared 6923a32b8db123fb  disk 6923a32b8db123fb  MATCH
```

`shard_rows` 逐格为 core 500 / Tier2 30，24 格合计 2,600。`phase2.status` 五个退出码全 0 + OK 19:33:21。判定成立。

### 2.6 资源：2,600 rep / 201.8558 CPU·h 可精确复算，但非峰值

从 24 个 `out/g03_formal/_final/*/repetitions_telemetry.csv`（**不要用 rglob**：`out/g03_formal/shards/` 是 junction，rglob 会把 132 个分片再走一遍，得到 5,200 行的双计数）：

```
telemetry rows 2600 total_h 201.8558 mean_s 279.49 max_s 1318.12
repetitions rows 2600 files 24
```

`201.8558 = pipeline 87.9152 + estimate 0.3196 + models 113.6211`（与注册表 §2.7 "pipeline + estimate + models" 口径一致）。磁盘：

```
13G  out/g03_tier2
41M  out/g03_core_ate
491M out/g02_fixed
C: 401G 332G 69G 83% /c
```

内存监控确有：`out/g04_logs/monitor.log` 151 个采样块，首 2026-10-29 11:41:42，末 **2026-10-30 14:21:22**，末块 `python procs=8 rss_mb=6,937 top3_mb=2,023,1,940,1,734`、`mem_free_gb=12.3`。但 Phase 2 于 10-30 17:37:55 才启动，监控**没有** Phase 2 的连续采样；上述资源是收尾后遥测聚合与磁盘实测，不是运行期峰值。注册表 §2.7 与审计 G04 行（当前第 48 行）已如实披露，评审不得把它升级为"峰值证据"。判定"成立但口径受限"。

### 2.7 `run_all` 与论文入口：存在，但"一键"名不副实

```
.venv/Scripts/python.exe scripts/run_all.py --round all --dry-run
计划 (4 步)：01_build_data.py / 02_run_experiment.py / 03_cate_obs.py / 04_policy.py   RC=0
```

`run_all.py` 的 `PIPELINE` 只有第 1–3 轮（`scripts/run_all.py:30-34`），不含 G01/G02/G03、finalize、证据导出、论文 43/52/61；后者的入口分别是 `51/63/66/41/33/40/43/52/61`，本次用 `bash -n` 验证 51/52/63/66 语法通过。G03 的 `--resume` 只识别 `repetitions_provisional.csv`（`scripts/34_g_matrix_run.py:316-319`），已完成的正式分片整片重跑，不做 rep 级续跑。判定"部分成立"，见 P3-5。

### 2.8 校验器只加强：diff 未见削弱，25 例测试通过

`git show 1b50641 -- scripts/41... scripts/33... scripts/49...` 显示：

- 41 的导出后自检只是从内联抽成 `_post_export_self_check()`，重名/缺失/sha/bytes/文件数五项检查**一条未删**；
- 33 新增仓外绝对路径 `abs_path` 处理与"无法映射为顶层 target"硬失败，属加强；
- 49 仅改了一行 INFO 文案。

本次跑 `tests/test_v3_evidence_registry_guards.py` + `tests/test_g04_closeout_precheck.py`：25 个测试点全过（`25 dots / 100%`），RC=0（`out/scratch/g04_review_pytest_targeted.log`）。但 16 例夹具是手工拼的，不是从源码产物派生；且 49 的"OK + 非零 exit"和顶层漏登记两处缺口没有反例夹具，见 P2-2、P2-3。

## 3. 新问题

### P1-1 `docs/v3_复现手册.md` 整体停留在 2026-10-29 20:27，与当前状态矛盾

- 证据：手册第 3 行"维护时间 2026-10-29 20:27"；第 57 行"`coverage.json` 20:27 实读 66 692 B"（现为 93 条 / 16,975,748 B）；第 58 行"claim 注册表 20:27 实读 23 条"（现为 290 条）；第 61 行"33 --dry-run [未跑·本次]，当前 `_final` 未生成"（现 `_final` 24 格齐全、33 dry-run RC=0）；第 89 行"20:18 实时树 EXIT=2"（指 10-29，现 49 为 READY）。`git log -- docs/v3_复现手册.md` 只有 `6c85fde`（10-29 20:27）一次提交。
- 影响：G04 的验收材料就是"运行注册表、复现验证"，手册是唯一的复现操作入口；按现文操作会以为收尾未完成，且 49/62/63/66 的最终验证记录全部缺失。审计 P4 写"手册已如实标注"，但标注的是 10-29 的状态，不是 10-31 的收尾状态。
- 建议/关闭条件 C2：刷新到 2026-10-31 收尾后状态；更新 coverage/claim 计数与 `_final` 状态；为 49/62/63/66/41/33 每条命令补 `[跑过]` 时间与日志路径或 `[未跑]` 原因；保留"未做从零端到端"和"无 Phase 2 连续监控"两句限制。

### P2-1 `49` READY 不含 `finalize.status`，可在 63 已失败时判 READY

- 证据：`scripts/49_g04_closeout_precheck.py:44-46` 只列 `g02_post/phase1/phase2`；19:34:26 的 49 输出 READY（`out/g03_logs/auto_finalize.out` 末段），而同一时刻 `auto_finalize.out` 上方是 `33 dry-run 失败 rc=2`、`auto_finalize.log:8` 是 `[auto] 63 exit=0`（tee 码；63 实际 ABORT）。`finalize.status` 根本不在 49 的读取列表里。
- 影响：49 被审计行当作 G04 收口证据之一。当前最终状态 63 六步全 0，结论不受影响；但门禁本身不能阻止"收尾链失败 + 49 READY"的组合，下一次收尾可能被误判为可发布。
- 建议/关闭条件 C1：49 增读 `out/g03_logs/finalize.status`，要求六个 `*_exit=0` 且含 `OK: G03 finalize 完成`，文件缺失/ABORT/非零即 problem；补"finalize 缺失"与"finalize ABORT"两例夹具（与 P2-2、P2-3 的夹具合并进 C1），并重跑 49 留日志。

### P2-2 `49` 状态解析"OK 优先于非零 exit"，提交说明的"4 例夹具"不存在

- 证据：`scripts/49_g04_closeout_precheck.py:48-53` 先判 `if "OK:" in text`，`elif bad_exit`；只要含 OK，`tier2_exit=1` 也不会进 problems。用夹具 `out/scratch/g04_status_probe/out/g03_logs/phase2.status`（内容 `tier2_exit=1` + `OK: forged success line`）调用 `check_statuses()`，输出 `problems=[]`、`pending=[]`、`[VERDICT] READY`、`verdict=0`（`out/scratch/g04_review_49_status_bypass.log`）。测试只覆盖 ABORT（`tests/test_g04_closeout_precheck.py:90-103`），没有非零 `*_exit` 用例；提交 `7fae20e` 标题称"非零 *_exit 判 failure（4 例夹具）"，与测试文件不符。
- 影响：状态文件是纯文本、可人工拼接；任何"旧 OK + 新非零"的状态都会被判 READY。当前三个真实 status 均全 0 + OK，无现实误判，但门禁语义与其说明不一致，属可绕过。
- 建议/关闭条件 C1（与 P2-1 合并落地）：把 `bad_exit` 判断移到 `OK` 之前，任何非零 `*_exit` 一律 problem；补"OK + 非零"和"仅非零无 OK"两例夹具。

### P2-3 顶层登记表"磁盘有、索引无"只报"新增"，49 不会失败

- 证据：`scripts/33_register_evidence_top.py:468` 把磁盘多出的记录计入 `added` 并打印"新增 N"；`verify_whole_table()`（:395-407）只做索引→磁盘；dry-run 在 :522 直接 `return 0`。用顶层副本（92 条，删掉 `g03_snapshot_binding`）跑 `33 --dirs g02_formal g03_formal --dry-run --top out/scratch/g04_review_top_missing_g03.json`，输出"新增 1 / 顶层全表复算一致 93 条 / DRY-RUN"且 **RC=0**（`out/scratch/g04_review_33_missing_rerun.log`）。反向（索引有、磁盘无）则 RC=4（`out/scratch/g04_review_33_extra.log`）。手册第 54 行声称"两向都失败"；AGENTS §12.7 第 240-242 行明确要求"磁盘有而索引没有 = 漏登记，两种都必须失败"。
- 影响：删掉/截断顶层 `coverage.json` 的一条记录后，49 仍 READY；"少登记几条"不会响。当前 93 条全登记，无实际漏项，但门禁与规范不一致。
- 建议/关闭条件 C1（与 P2-1 合并）：33 增 `--expect-complete`（有 added 即非零）或 49 要求 33 dry-run 输出"新增 0"；补"顶层少一条 → 非零"夹具。

### P2-4 最终编辑后没有全量串行 pytest 绿灯

- 证据：最后一次全量日志是 `out/pytest_g02fix_20261029_1029.log`（mtime 10-29 10:37）；之后 10-31 19:58–20:04 又改了 `scripts/33`、`scripts/41`、`scripts/49`、`tests/test_g04_closeout_precheck.py`、`tests/test_v3_evidence_registry_guards.py`。本次只跑了相关 25 例（全过），未跑全量；AGENTS §11.4 要求全量绿灯必须"单一进程、串行、无并发写盘，并保留日志、exitcode 与起止时间"（`AGENTS.md:177`）。评审开始时另一代理正在改 `paper/`，20:30 其提交 `f52d663` 后工作树已干净，但全量 pytest 仍未跑。
- 影响：`src/` 未改动，G03 数字不受影响；但 G04 要证明"全入口可恢复"，缺少一次覆盖全部测试的收尾绿灯，且两处门禁缺口没有回归测试兜底。
- 建议/关闭条件 C3：在当前已干净的 `f52d663` 上，单进程串行跑全量 `pytest --basetemp C:/cg_t`（无并发写），保存日志、exit code、起止时间；若失败先分类是并发写造成还是真实回归。

### P3-1 "真实进程记录"部分仍是叙述：PID 1507 无机器记录

- 证据：注册表 §2.7 写"bash 包装 PID 1507、6 个 python 进程"，但 `out/g04_logs/monitor.log` 只有 `python procs=8` 计数，没有 PID；`out/` 中未见 `Get-CimInstance Win32_Process` 的原始输出。Phase 2 的 `phase2.log`/`status` 可证明作业真实跑过，但"哪个进程"只能信文档。
- 影响：G04 判据含"真实进程记录"；当前证据足以证明作业发生，不足以独立复核进程谱系。
- 建议：下次正式运行在启动/结束各留一份进程表（PID、命令行、父 PID）到 `out/`；或在注册表把 1507 明确标注为"人工记录，无机器快照"。

### P3-2 `auto_finalize.log` 的 `[auto] 63 exit=0` 是 tee 退出码，且未进 G04 事故表

- 证据：`out/g03_logs/auto_finalize.log:8` 为 `[auto] 63 exit=0`，但第 7 行是 `33 dry-run 失败 rc=2`，63 实际 exit 7；同一文件 19:34:32 的 49 仍 READY（P2-1）。G03 正式报告 18:28 行已说明"取的是 tee 的退出码，不能作为 63 成功证据"，但 G04 运行注册表 §3 的事故表未收此条。
- 影响：单独看 `auto_finalize.log` 会误以为自动收尾成功；依赖者必须同时看 `finalize.status`。
- 建议：把该事故补进注册表 §3；自动收尾脚本改用 `PIPESTATUS[0]` 或在 63 后单独 `echo $?`，不再让 tee 码冒充。

### P3-3 `66` 先写"6/6"再跑导出，失败会留下假成功行

- 证据：`scripts/66_g03_refresh_evidence_logs.sh:16-19` 先向 `finalize.log` 追加 `6/6 收尾后重导出`，第 20 行才执行 41 导出；若导出失败，日志仍宣称 6/6，只有 `post_finalize_export.status` 记非零。
- 影响：本次导出 RC=0，无实际假成功；但日志作为证据包内容，顺序应反过来（成功后再写标记）。
- 建议：把追加动作移到 41 成功之后；失败时写 `6/6 FAILED rc=...` 或不写。

### P3-4 `62` 的拒绝断言过宽

- 证据：`scripts/62_g04_tamper_drill.py:128` 只要求 41 输出不含 `"重叠"` 且不含 `"rep"`；本次 41 实际报的是 `ate_any_refund_30d` 的 sd/MC_SE 复算不符（`finalize.log:208-209`），并不含"rep 重叠"字样，能通过纯属输出里没有 `rep` 子串。
- 影响：rc!=0 仍被强制，不会漏掉"41 没拒"；但"拒因必须是 rep 重叠"没有被真正验证，换一种无关的 41 失败也会 PASS。
- 建议：断言 41 输出含 `rep` 重复/`重叠` 的确切错误码或错误文本；补一例"41 因无关原因失败"的反例。

### P3-5 记录类小瑕疵

- 注册表 §2.8 称 `closeout_precheck_20261031_2005.log` "其 33 行"，实际 `wc -l` = **28 行**（`out/g04_logs/closeout_precheck_20261031_2005.log`）。
- 阶段 A 的 17:51 失败只有归档 `run_summary.json` 的 `failures` 字段，没有保留 traceback 日志；`g02_fixed.log` 已被成功重跑覆盖。
- `run_all.py` 名为"一键复现入口"，实际只编排 01–04（第 1–3 轮）；G03/收尾/论文需手工分步，手册应明确。
- G03 `--resume` 只认 provisional，正式分片整片重跑；恢复可行但代价高，手册应写明。
- 建议：随 C2 手册刷新时逐条改正；事故表补 17:51 与 19:34 两条。

## 4. 范围与未覆盖

- 未重跑 `scripts/63`、`scripts/66`（会改写 `outputs/evidence` 与 `out/g03_logs`），按日志内部时间、状态文件、sha256 与全表复算核验。
- 未重跑 G01/G02/G03 的正式作业（R>0），未重跑论文 43/52/61 门禁；只验证入口存在、语法与既有日志。未做"从零端到端"空跑（审计 P4 已披露，本次不将其算作成立）。
- 未跑全量 pytest（并发写盘，违反 AGENTS §11.4）；只跑相关 25 例。
- 未独立验证 17:51 之前的 G02 阶段 A 逐 rep 数值，只核验失败记录与归档存在；未复核 `out/g02_retrain_failed_20261029_1026` 的逐 rep 内容。
- 未审计 H02/H04 并发写入本身（不属于 G04），但其改动影响本次 49 的 claim 计数与 paper 状态，已在 §5 披露。
- 资源只到"收尾后遥测 + 磁盘实测"层级；无 Phase 2 运行期内存/进程连续采样，不能据此声称峰值。

## 5. 审计链

### 5.1 读过的文件（关键）

- 规则与目标：`AGENTS.md`（§7、§10、§11.4、§12.1、§12.3、§12.7）、`GOAL.md`（G04 行）、`docs/v3_G04_收尾审计.md`、`docs/v3_phase_G_run_registry.md`（§2.6–2.9、§3）、`docs/v3_复现手册.md`、`docs/v3_phase_G03_formal.md`（§2）、`docs/reviews/v3_phase_G03_recheck.md`、`docs/reviews/v3_phase_G03_recheck2.md`。
- 脚本：`scripts/49_g04_closeout_precheck.py`、`62_g04_tamper_drill.py`、`63_g03_finalize.sh`、`66_g03_refresh_evidence_logs.sh`、`33_register_evidence_top.py`、`41_export_g03_evidence.py`、`40_export_g02_evidence.py`、`34_g_matrix_run.py`、`51_g03_phase2.sh`、`52_paper_gates.sh`、`run_all.py`。
- 测试：`tests/test_v3_evidence_registry_guards.py`、`tests/test_g04_closeout_precheck.py`。
- 证据与状态：`outputs/evidence/g03_formal/coverage.json`、`outputs/evidence/coverage.json`、`outputs/evidence/g03_formal/logs/{finalize.log,finalize.status,g49_full.log}`、`out/g03_logs/{finalize.log,finalize.status,phase1.status,phase2.status,post_finalize_export.status,auto_finalize.log,auto_finalize.out}`、`out/g02_logs/post.status`、`out/g03_formal/run_summary.json` 及三份派生 summary、`out/g02_fixed_attempt1_20261029_1751/run_summary.json`、`out/g04_logs/{monitor.log,tamper_drill_20261031_2007.log,closeout_precheck_20261031_2005.log}`。

### 5.2 跑过的命令（均在本工作目录）

1. `49 --with-check --with-register --with-claims`（20:21:54，RC=0 READY，290 claim；另于 20:32:21 在 `f52d663` 上重跑，仍 RC=0 READY，日志 `out/scratch/g04_review_49_rerun_postcommit.log`）。
2. `62`（RC=0，日志 `out/scratch/g04_review_62_rerun.log`）。
3. `41 --check`、`40 --check`（均 RC=0）。
4. 独立 coverage 复算（357/93 条，sha256 + bytes + 总字节，bad=0）。
5. CPU/rep 复算（24 个 `_final/*/repetitions_telemetry.csv`，2,600 行，201.8558 h）。
6. 复合 `run_summary.json` 三源 sha256 对账（3/3 MATCH）。
7. `du -sh out/g03_tier2 out/g03_core_ate out/g02_fixed`、`df -h .`（13G/41M/491M/69G）。
8. `monitor.log` 采样统计（151 块，末 2026-10-30 14:21:22）。
9. 49 状态夹具复现（`check_statuses()` → READY/0，`out/scratch/g04_review_49_status_bypass.log`）。
10. 33 顶层漏登记复现（RC=0，"新增 1"）、索引过期复现（RC=4）。
11. 相关 pytest 25 例（RC=0）。
12. `run_all.py --round all --dry-run`（4 步）、`bash -n` 51/52/63/66（全过）。
13. `git show 1b50641` / `7fae20e` 校验器 diff；`git log` 手册；`sha256sum`、`wc -l`、逐条哈希复算。

### 5.3 写盘

- 本报告：`docs/reviews/v3_phase_G04_review.md`。
- 探针/临时文件（仅 `out/scratch/`）：`g04_review_hashes_{before,after}.txt`、`g04_review_49_rerun.log`、`g04_review_49_status_bypass.log`、`g04_review_62_rerun.log`、`g04_review_41_check_g03{,_utf8}.log`、`g04_review_40_check_g02.log`、`g04_review_coverage_recompute.log`、`g04_review_pytest_targeted.log`、`g04_review_pytest_tmp/`、`g04_review_run_all_dryrun.log`、`g04_review_top_missing_g03.json`、`g04_review_top_extra.json`、`g04_review_33_missing.log`、`g04_review_33_missing_rerun.log`、`g04_review_33_extra.log`、`g04_status_probe/`。
- 未修改 `src/`、`configs/`、`scripts/`、`outputs/`、`GOAL.md`、`TODO.md`、`AGENTS.md`、`docs/v3_*.md`。
- **并发写披露**：评审开始时 `git status` 干净；20:18 后 `outputs/tables/v3_h04_claim_registry.csv`、`paper/v3/body/03_results.md` 被另一 H02/H04 代理改动，20:27–20:28 又见 `docs/v3_H03_编译审计.md`、`paper/v3/body/02_method.md`、`GOAL.md`、`docs/v3_G04_收尾审计.md` 被改；这些改动于 20:30:42 提交为 `f52d663`（registry 290 条，与本次 49 所读哈希 `181e21a0…` 一致），此后工作树干净。49 在 20:21:54 与 20:32:21 两次 READY；其 `check_git` 只查 `src/ sql/ configs/`，不覆盖 paper/outputs/GOAL/审计文档，故这些并发改动能通过 49，但不影响 G03 证据哈希。全量 pytest 仍因此延后（P2-4），建议在 `f52d663` 干净树上补跑。

## 6. 关闭条件（可执行、可复核）

| 条件 | 对应 | 动作 | 验收证据 |
|---|---|---|---|
| C1 | P2-1/P2-2/P2-3 | 49 增读 `finalize.status`（六零 + OK）；非零 `*_exit` 优先于 OK；33 dry-run 有"新增"即失败（或 `--expect-complete`）。补 5 例夹具：finalize 缺失、finalize ABORT、OK+非零、仅非零无 OK、顶层少一条 | 新夹具全过；49 在 finalize ABORT 树上 RC=3/2；在顶层少一条树上非零；真实树仍 READY 且日志留档 |
| C2 | P1-1 | 刷新 `docs/v3_复现手册.md` 到 2026-10-31 收尾后状态；更新 93/16,975,748、290 claim、`_final` 齐全；为 49/62/63/66/41/33 标注 `[跑过]` 时间与日志；保留"无从零端到端""无 Phase 2 连续监控" | 手册内部时间戳 10-31；每条命令有日志路径或 `[未跑]` 原因；与 49 实际输出一致 |
| C3 | P2-4 | 并发写停止后单进程串行跑全量 pytest（`--basetemp C:/cg_t`），保存日志、exit code、起止时间 | 日志首尾时间连续、无并发写、exit=0 |
| C4 | P3-2/P3-3/P3-4/P3-5 | 注册表事故表补 17:51 与 19:34；66 改为导出成功后再写 6/6；62 断言收紧到重复 rep 的确切错误；改正"33 行"为 28 行；注明 manual/resume/run_all 边界 | 注册表 diff；66 失败注入测试；62 在无关失败时不 PASS；行数一致 |
| C5 | P3-1 | 下次正式运行留 PID/命令行/父 PID 进程表；或把 1507 标注为人工记录、无机器快照 | `out/` 有进程表，或注册表措辞已改 |
