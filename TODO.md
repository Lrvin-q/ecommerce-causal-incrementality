# TODO — v3 执行真相源

> 合成数据 / 已知 DGP。维护时间：2026-10-29 11:15（北京时间）。[ ]未开始；[~]进行中；[x]有证据完成；[!]阻碍。旧数字和进度保留在Git历史。

## 当前状态

**2026-10-29 11:15 更新。G02 稳定推进（4 格均已越过 b=0，3 格已在 b=1）；无人值守链与 G03 续跑预案已核**：

- **进度**：10:39 重开 → 11:15 时 L0_P_main/L1_main/L2_n200000_p050 各 2 b、L3_fixed_lt000 1 b 完、正在 b=1；
  b=0 每格 CPU 386–562 s。**ETA 16:15–17:30**。
- **越过失火点**：10:53 起 b=1 行正常落盘——`validation_frame_hash`/`validation_arm_hash` 各 1 值、
  `validation_observed_hash` 2 值，正是首轮全灭的场景，现按设计放行。
- **三个后台进程**：`out/g02_post.sh`（PID 1457，校验+merge）→ `out/g03_chain.sh`（PID 1493，14 h 期限，
  阶段 A 固定 bootstrap 24 格 × rep0 → 阶段 B G03 24 格 ~26.5 h）→ `out/g03_post.sh`（PID 1952，40/41
  `--check` + 导出；**33 登记留人工**）。
- **G03 续跑陷阱（11:15 读码确认）**：`--resume` 只救"半途被杀、有 `repetitions_provisional.csv`"的分片；
  已完成分片无论带不带 `--resume` 都会整片重跑。预案：先 `34 merge` 收已完成 → 缺口 `--cells/--rep-start/
  --rep-stop --out-root out/g03_repairN` 另起根 → 多根 `merge` 且确认 `duplicates=0`。
  已写入 `AGENT_HANDOFF.md` 第 6 条与 `docs/v3_决策与反思日志.md` 11:15 条。
- **轮次**：目标 41/60 轮；后台链不受暂停影响，恢复时按现场状态判断。

**2026-10-29 10:40 更新。G02 首轮正式跑 4 格全灭（冻结帧指纹选错），已修并在 10:39 重开；全量测试绿灯**：

- **事故（10:15–10:26）**：4 个 core 格都在 b=1 抛 `验证帧哈希与 b=0 不同`。根因不是 DGP，
  是 `validation_observed_hash` 覆盖含 `issued_action` 的观测表，而 `issued_action` 由该 b 的打分决定。
  验证队列本身确定（同 rep 协变量两次生成逐字节相同）。守卫在写 b 行之前抛——没写出任何坏行。
- **修法（10:26–10:28）**：`run_validation_arm` 新增与模型无关的 `validation_frame_hash`
  （用户协变量）与 `validation_arm_hash`（臂标签 + 概率）；39 号改为断言这两个，观测哈希仍逐 b 记录；
  续跑遇旧表缺列直接 `SystemExit`。设计档 §6.1.a 第 2 条同步更正。新测试 `tests/test_v3_g02_frozen_frame.py`（6 例）。
- **10:46 补修同一坏指纹的第二处**：`39 … merge` 仍在断言 `validation_observed_hash` 唯一，会在 19:30
  收尾合并时必败并停链。已抽 `check_merge_frame` 只断言 b 不重复 + 两个新指纹唯一，缺列即拒；
  3 例新测试 + 用失败现场实跑 `39 merge` 验证被拒（exit=1）。与导出测试合计 **9 passed**。
- **验证**：n=2000 × 4 格 × 2 b 冒烟通过（`L0_P_main` b=1 选模从 constant 变 causal_forest，正是旧指纹误报的场景）；
  全量单进程串行 pytest **EXIT=0**（`out/pytest_g02fix_20261029_1029.log`，10:29–10:38）。
- **重开（10:39）**：新快照 `out/g02_snapshot` 49 文件 `abaa338a…`（`v3_g_matrix.py` `6ec009b6…`）；
  4 格重新从 b=0 跑。**10:53 已越过首轮失败点**：L0_P_main 写出 b=1，`validation_frame_hash` 与
  `validation_arm_hash` 跨 b 唯一（各 1 个值），`validation_observed_hash` 如实变为 2 个值。
  实测 b=0 每格 386–562 s CPU、b=1 约 6.5 min wall ⇒ 50 b 约 **5.5–6 h**，ETA **16:15–17:30**。
  失败现场保留在 `out/g02_retrain_failed_20261029_1026/`
  （4 格 b=0 表 + failure_logs）。`out/g02_post.sh` 改为断言两个新指纹 + 停滞 3 h 即失败；
  `out/g03_chain.sh` 改为识别 `STALL/TIMEOUT/VERIFY FAIL/merge_exit≠0` 即停（10:39:57 重启，PID 1493）。
- **10:48 补收尾看护**：`out/g03_post.sh`（PID 1952）等 `chain.status` 的 `OK:`，先跑 40/41 `--check`
  再自动导出 `outputs/evidence/g02_formal` 与 `g03_formal`；**顶层登记（33 号）不自动跑**，留人工复核。
  另确认 34 号 `run` 结束时会自动 `_finalize`，写出 `outputs/tables/v3_g_g_core.csv` / `v3_g_g_tier2.csv`
  与 `out/g03_formal/_final`，这正是 41 号校验所要求的汇总表。
- **G01 复评（两轮并行，结论一致）**：`docs/reviews/v3_phase_G01_review2.md`——PASS WITH CONDITIONS，
  P1 4/4 全关、数据零不符。复评提的 5 条 P2 **已全部关闭**：
  ① 33 号反向校验补上目录级白名单（反例 `out/review_g01_round2/fixture_ev` 当场 exit 2，真树 91 条 dry-run 仍 exit 0）；
  ② 37/40/41 号导出改"暂存目录 + 原子换名 + 旧目录带时间戳备份"，40 号 3 个回滚测试通过；
  ③ §3 功效列改标"解析功效"并注明带外手算值；④ §5.1 `config_hash` 改为逐层四值、统计列逐比特相同的准确表述；
  ⑤ 注册表/TODO 旧数改为 59 登记/60 磁盘/1 275 048 B、91 条/16 964 194 B。
  **第三轮窄复评（10:56）**：`docs/reviews/v3_phase_G01_review3.md` 判 **5/5 P2 关闭、0 新增 P0/P1**，
  校验器只加强未削弱；新增 4 条文字级 P3 已当场修完（"单侧"→"双侧" 0.5855→0.5857；GOAL「合并」
  映射改为条件句；`all_repetitions.csv` 改 1 384 行/去重 1 000；40/41 备份命名统一为 `%Y%m%d%H%M%S`）。
  **GOAL G01 已于 11:00 改判"通过"**，边界写明：非新的独立 AA 样本、CP 下界低于预设带、
  0.81/0.96 是解析功效、不表示策略有效。

**2026-10-29 10:22 更新。34 号补上 bootstrap scope 贯通；G03 范围澄清为 24 格；G02→固定 bootstrap→G03 已串成无人值守链**：

- **34 号补丁（10:16）**：新增 `--bootstrap-budget-scope`，贯通 task 字典 → `_worker` → `g.run_cell`；
  `formal` 且 `resamples>0` 而 scope≠`primary_0.2` 时 **argparse 直接失败**（在 mkdir 之前，实测不落目录）；
  `run_summary.json` 回写 `bootstrap_resamples` / `bootstrap_budget_scope`。
  验证：`py_compile`；`require_bootstrap_scope` 三例（`primary_0.2` 过、`None`/`all` 拒）；engineering 不受限；
  **n=2000 冒烟**跑通并产出 `fixed_bootstrap.csv`（`budget=0.2`、`resamples=1000`、CI 覆盖 0）。
  这不是"放松守卫"：34 此前根本不传 scope，正式跑必被 `v3_g_matrix.py:963` 拒绝。
- **G03 范围澄清（与已批 159.2 CPU·h 对齐）**：G03 正式跑 **24 格**——4 个 Tier1 core（`R_ate=500`，
  学习/验证 100）+ 20 个 Tier2 选中格（`R=30`）。GOAL G03 行写的"20 格"是 Tier2 子集；
  决策单 §H.2 的 159.2 h = 95.9（core）+ 63.3（Tier2）。**不是**只跑 20 格。
- **固定 bootstrap 必须单列 rep 0**：`v3_g_matrix.py:959` 在 `resamples>0` 且 `rep!=0` 时抛错，
  所以"一条分片含 0..R-1 且带 1000 次 bootstrap"会在 rep 1 就失败。G02 的固定 bootstrap 臂因此
  独立成一次 formal 跑（24 格 × rep 0，`--shard-size 1`，`out/g02_fixed`，约 3.3 CPU·h / 6 路 ~40 min）。
- **无人值守链 `out/g03_chain.sh`（10:19 起，PID 1291）**：等 `post.status` 出现 `OK:` → 建快照
  `out/g03_snapshot` → 阶段 A（固定 bootstrap，24 格 × rep 0）→ 阶段 B（G03 24 格 × 注册 R，
  `--workers 6 --shard-size 50`，`out/g03_formal`）。任一阶段非零即停，状态写 `out/g03_logs/chain.status`。
  阶段 B 按 159.2 h / 6 路 ≈ **26.5 h**；按 G02 修正后的 ETA（20:30 收尾）推，
  链条整体约 **10-30 23:30–01:00** 结束（±3 h；6 路并行效率尚未实测，决策单 §H.2 给的是 159–184 h 区间）。
- **环境事实**：本机 Git Bash 的 `TZ=Asia/Shanghai date` 输出 **UTC**（实测 10:18 → 02:18），裸 `date`
  已是北京时间；链条改用裸 `date`。G01 的 `started_at.txt` 记为 UTC 正是此故。

**2026-10-29 10:10 更新。G01 评审条件已全关（待复评确认改判）；G02 正式跑 10:09 开跑**：

- **G01 独立评审**：`docs/reviews/v3_phase_G01_review.md`，**PASS WITH CONDITIONS，0 P0 / 4 P1 / 9 P2**；
  数值零不符（46/1 000、CP [0.033871, 0.060884]、逐层 14/11/10/11、与 17 号表 max|Δ| = 0.0）。
- **条件关闭（10:10）**：证据区补 `binding/snapshot_binding.json` + `runs/` 12 份运行汇总 + `runs_summary.json`
  （窗口 22:42:39 → 05:15:38、failures 0）；manifest 的 `started_at_utc` 实为完成时刻，逐条 note；
  33 号加逐条白名单把 `runs_summary.json` 提到顶层（89→91、16 964 194 B）；报告加"计划/成功/失败/有效/哈希"表，
  §5.1 改为逐 rep 比对（1 000/1 000，69 可比列中 60 列 max|Δ|=0.0），9 条 P2 全修。提交 `e01e5e0`。
- **P1-4 主负责复核**：`aa/all_repetitions.csv` 1 384→1 000 行，与 G01 1 000 行 both=1000/0/0；
  9 个非零列 = 8 个计时列 + `file_lock_retries`（≤1），比评审口径更严。
- **事故**：37 号首次重跑因 `record()` 参数重复抛错，而 `export()` 先删目录——45 个已登记文件被删空，
  `git checkout` 复原后改为"旧目录改名备份→成功才删/失败还原"。已写入反思日志。
- **用户裁决**：预算 **A 保持范围**（222.6 h，超自设上限 6%）；**G02 + G03 都批**
  （`G02-FORMAL-20261029` / `G03-FORMAL-20261029`）。
- [~] **G02 正式跑（10:09:04 起）**：4 格并行（`L0_P_main` / `L1_main` / `L2_n200000_p050` / `L3_fixed_lt000`），
  每格 50 b、n=200 000；快照 `out/g02_snapshot` 49 文件绑定 `f39ec0a3…`；日志 `out/g02_logs/<cell>.log`。
  **首个 b 实测**（10:20 四格各 1 行）：CPU 369–532 s/b（t/s_learner 369/379，causal_forest 514/532），
  4 路并行下墙钟约 **11 min/b** ⇒ 单格 50 b ≈ **9.2 h**，ETA 约 **19:20–20:30**（R=1 顺序实测的
  15:30–17:00 偏乐观，§12.5 记下这次外推偏差）。完成后 `39 merge` → 40 号导出 → 33 登记。
- [ ] **G01 复评代理**：第二轮窄范围复核 **10:21 重新起飞**（上一轮代理随上下文重置失联、无产物）；
  产物 `docs/reviews/v3_phase_G01_review2.md`，只判 4 P1 / 9 P2 是否关闭、只读、禁跑数据作业。
  通过后由主负责改 GOAL G01 状态（含义仅限合并 FPR 与 0.05 相容，不含"新增独立证据"）。

**2026-10-29 05:40 更新。G01 已跑完待评审；G02 补丁已落真树、全量测试绿灯；下一步 R=1 实测**：
- **G02 补丁落真树（05:19）**：`v3_g_matrix.py` `fd3ca127…` → `3f4d677f…`（+66/−6）。新增
  `require_bootstrap_scope` / `bootstrap_budget_scopes` / `require_primary_budget`；
  `run_g_rep`/`run_cell` 加 `bootstrap_budget_scope` 并在建目录前拒绝；两份清单加
  `fixed_bootstrap_budget_scopes`；`run_validation_arm(with_policy_value=…)` 增三个出口键。
- **测试契约更新**：首次全量串行（05:20:31–05:28:42）唯一红项是
  `test_formal_run_refuses_incomplete_bootstrap_scope` 断言旧文案"全预算"；守卫仍拒绝，改的是断言。
  反例扩到 `None`/空串/`all_budgets`/`primary_0.5` 四个，另补 3 条正例（scope 接受主档、
  scopes 只主档非 None、预算断言接受主档）。**未削弱守卫**。
- **全量串行绿灯**：05:31:20→05:39:30（8 m 10 s），**1 313 点、0 F/E、EXIT=0**
  （`outputs/evidence/test_runs/pytest_g02_20261029_053120.log`）。
- **G01 报告两处措辞**：补"05:19 补丁后真树哈希变 `3f4d677f`，G01 以快照/manifest 绑定为准"；
  "45 文件"改为"登记 45、磁盘 46（含 `coverage.json`）"。
- **G02 A 臂 R=1 实测（05:41:21–06:09:16，EXIT=0）**：4 格 × 1 b × n=200 000，
  CPU 340/471/350/483 s（均值 **411 s/b**），200 b 外推 **22.8 h**（预算 13.3 h，超 1.7 倍）。
  **已越过 >320 s/次硬门禁 ⇒ 正式跑前必须重报预算**（决策单 §H.2）。验证臂在 causal_forest 下
  234–236 s，是成本方差的主因。产物 `out/g02_retrain_r1`（engineering，不作正式凭据）。
- **G03 R=1 完成（06:10:55–06:23:39，EXIT=0）**：`L1_main`（core，dr_learner）单 rep 362.22 s、
  `L3_overlap_extreme`（Tier2，t_learner）379.78 s（pipeline 均 ~100 s）。外推 core 23.97 h/格 × 4 = 95.9 h、
  Tier2 3.16 h/格 × 20 = 63.3 h，矩阵 **159.2 h**（原 149.4）。首试因 `--cells` 逗号写法整串被当成
  一个 id 而 5 s 内 EXIT=1（`ConfigError`），改空格分隔成功。
- **预算重报（决策单 §H.2）**：40.6 + 22.8 + 159.2 = **222.6 h vs 上限 210（+6.0%）**；
  已向用户提出 A/B/C/D 四方案（A 保持范围接受 ~223 h，建议）。
- **下一步**：用户裁决预算后，建快照 → G02 正式 200 b / G03 正式 24 格；G01 独立评审并行进行。

**2026-10-28 20:52 更新。G 阶段前置（包 A/包 B）完成并留证；G01–G04 正式跑仍未启动**：
- **包 A（A1 语义）**：`job_semantics.full_learning_reuses_first_ate_repetitions` 已实现并接线到新驱动
  `src/causal_growth/evaluation/v3_g_matrix.py` + 薄入口 `scripts/34_g_matrix_run.py`（plan/run/merge、分片、快照、provisional 门禁）。
  一个 rep 只建一次历史数据（`history_pipeline_builds=1`），ATE 与学习共用；验证另建总体（`validation_pipeline_builds=1`）。
  `tests/test_v3_g_matrix.py` 12 项全绿（A1–A10）；两处变异均落红并已复原（学习路径重建 → `assert 2 == 1`；
  真值篡改 → `policy_list.csv` 第 254 字节起不同），源文件 sha256 复原为 `ab836691…`。
- **包 B（Tier2 收缩）**：`configs/budget/tier2_overlay.yaml`（sha256 `02644767…`）把 65 格×100 收缩为 20 格×30，
  Tier1 取 ATE 500 / 学习 100 / 验证 100；七份冻结配置 canonical hash 仍 `00723dc2…`。8 键检查通过：
  `tier1_ate`/`fixed_policy_bootstrap`/`retraining_bootstrap` 未变，三个 `tier2_*` 全 30（含 `tier2_independent_validation`）。
  选格与 45 个被砍格的同类对应见 `docs/v3_tier2_selection.md`。
- **A10 工程跑**：49 文件字节快照 + PYTHONPATH 绑定；2 格×R=3（n=2000、constant、2 worker）；
  `rows_raw 6 / rows_deduped 6 / duplicates 0 / failures []`；`_final/*/repetitions_provisional.csv` 不含计时列，
  计时单列 `repetitions_telemetry.csv`（A2 逐字节复现要求）。
- **证据**：`outputs/evidence/g_smoke/` 28 个文件、433 501 B；`scripts/35_export_g_smoke_evidence.py` 导出并反算关键数字
  （R 500/100/100 与 30/30/30、builds 1/1、`truth_columns_present=False`、`budget_plan.source=overlay`、`freeze_written_before_truth=True`）；
  顶层登记 **65 → 70**、全表复算 PASS、幂等；反例：源缺失 exit 2、目录级漏登记 exit 2。
- **全量测试**：20:44:34–20:52:46 串行 **1 287 项、EXIT=0**（`outputs/evidence/test_runs/pytest_g_prework_20261028_2045.log`）；含 17/19 号校验器既有用例，本次未改动两脚本，门禁未削弱。
- **全量测试（G AA 执行器后）**：21:05–21:13 串行 **1 303 项、EXIT=0**（`outputs/evidence/test_runs/pytest_g_aa_20261028_2105.log`）；新增 `tests/test_v3_g_aa_executor.py` 16 项，含 6 类 gate 拒绝与 3 类 `split_layer_table` 拒绝。
- **成本口径自纠（20:47）**：初稿"192.8 CPU·h"含 30 h 未列明余量且漏掉 AA250。逐项重算：G 矩阵 **162.8** + AA250 **44.4** = **207.2**，
  上限 210、余量 **2.8 h**；固定 bootstrap 1000 次不重拟合、未计入，跑前须实测。已改 `docs/v3_repetition_budget_revision.md` §7.2 与 GOAL G02。
- **G 阶段四项裁决（22:26，用户逐字）**：再训练 bootstrap **200 次（任务书口径）**；固定策略 bootstrap **仅主预算档 0.2 元**；
  G03 **20 格 + 改 GOAL 措辞（走法 1）**；**批准 G01 正式跑**（并问能否 6 路）。随机名单口径未单独裁决，按决策单推荐接受 DR 估值。
  落地含义、必须同步改的文字、以及 6 路能力的实测见 `docs/v3_G开跑决策单.md` §裁决记录 / §F。
- [x] **G01 AA250 正式跑（已跑完 2026-10-29 05:15:45，北京时间；22:42:39 起，墙钟 6 h 33 m）**：批准号 `G01-AA250-20261028`；
  快照 `out/g01_snapshot` 49 文件 `526ff53d56a54c75`；`status=formal`、`n=200 000`、4 层 × 250 = 1 000 rep；
  **12 分片 / 6 lane**（s01–s12 → L0/L1/L2/L3 的 `[0,83)/[83,166)/[166,250)`，每 lane 顺序 2 片）。
  编排 `out/g01_runner.sh`，跑完自动 `out/g01_verify.py`（每层 rep 恰 0..249、无重复缺口、n_total/alpha/protocol 唯一）
  再交 17 号多根合并（`outputs/tables/v3_phase_D_aa_formal_merged.*` 会被覆盖——D 阶段原字节已归档到
  `outputs/evidence/d02_aa_phase_d_20261027/`，8 文件 + manifest）。
  实测 6 路每 rep 132–147 s、峰值 10.69 GB；**23:53 实测：首片 29/83，146 s/rep，每 lane 余 137 rep ⇒ ETA 2026-10-29 05:00–06:00（约 05:30）**。
  跑前全量串行绿灯：`outputs/evidence/test_runs/pytest_g01_20261028_2234.log`（1 310 进度点、0 F/E、EXIT=0）。
  **运行期冻结窗口生效**：不写 `src/ sql/ configs/`。已知缺陷：`out/g01_logs/*` 里 `date` 落盘是 UTC（少 8 h，
  Git Bash 的 `TZ=Asia/Shanghai date` 不生效，Python `zoneinfo` 正常；分片日志里的时刻可信）。

**23:55 收尾链修正（第四次路径类错误）**：分片表优先读归一化副本 `<shard>/<layer>/aa_repetitions.csv`
（36 号收尾时由 `split_layer_table` 写出：筛 `true_aa` + 重排索引），缺失才回退
`<shard>/layer_runs/<layer>_<stamp>/aa_repetitions.csv`；**两张表哈希不同**（`62e19c7c…` vs `2c4df6c3…`），
17 号合并读的是前者，校验/导出必须同源，否则"复算与合并表不一致"是假故障。已提交 `268a9b6`，
并用当前部分产物验证取数：6 个已开 lane 解析到 `layer_runs` 原始表（归一化副本尚未生成），未开跑的 s02/s04/s06/s08/s10/s12 如实报缺。

**00:00 收尾链已在夹具上整段跑通（`out/scratch/dryrun_37.py`，DRYRUN PASS）**：
17 号合并（12 个单层根 → 15 行 / POOLED 1000、无 `_provisional`）→ 37 号导出（45 文件、与 17 表 **0 不一致**、`coverage.json` CRLF）
→ 33 号提升（12 条 `g01_shard_manifest`、`status=formal_aa250`）。夹具里 6 份原始表被故意写成 p=1.0，
证明 37 号确实读归一化表。第五处修复 `645e904`：导出记录的 `path` 改为**相对证据目录**（33 号按 `d / rel` 取文件），
并补 `kind`/`source`/`status` —— 原样会在登记环节对 12 条全部报"索引过期/无法确定 kind"。
另记：**17 号对归一化表没有回退**，这是设计选择；缺表时它写 `_provisional` 副本，而 verify 会先拦缺 rep。
  **22:48 进度与收尾链**：s01 已完成 rep 0–1（133.2/133.4 s），分片表落在
  `out/g01_aa250/s01/layer_runs/L0_224239/aa_repetitions.csv`（**不是** `s01/L0_AA/`，早期记录已更正）；
  收尾链已做成无人值守 `out/g01_post.sh`（21:48 UTC 启动，pid 1870）：等 `finished_at.txt` → 校验
  `verify.exit`/`merge.exit` 均为 0 → `scripts/37_export_g01_evidence.py` → `scripts/33 --dirs g01_aa250`
  （先 `--dry-run` 再写盘）；任一步非零即停在 `out/g01_logs/post.status` 并**不登记**。
  **推送已恢复**：2026-10-29 00:00 `git push origin codex/d03` 成功（`3c1d37e..5a1681d`），
  此前 3 次 443 超时的积压提交（`b920519`、`4c2ba14`、`268a9b6`、`645e904` 等）已一并上云。
  **22:53 收尾链自查（已修 3 处，均已提交）**：① 分片产物真实布局是
  `<shard>/layer_runs/<layer>_<stamp>/aa_repetitions.csv`，校验器与导出器原先按 `<shard>/<layer>/` 找，
  会在跑完后把 12 片全判失败并中止导出——已改并**用当前半成品实跑校验器验证**（读到 L0/L2 各 12 行、
  L1/L3 尚未开始、exit 1，行为正确）；② 导出器按 12×4 笛卡尔积取 48 张表（实际 12 张），已改按
  分片→层映射；③ `aa_manifest.json` 由 36 号写到 `<root>/<layer>/`（不在 layer_runs），已改。
  另记：GOAL G03 的 57.0 与 `34 plan` 的 149.4 需对账（后者含 4 个 core 格），已记入决策单 §H；
  G02 查出两处硬缺口（验证臂不回传策略价值、A 的轻量链未实测），已记入设计文档 §6.1/§6.7。
  **G02 补丁已在影子树全绿（10-29 00:07）**：10 处改动 + 幂等 + `py_compile` + 守卫矩阵 6 例 + 预算断言 3 例
  + `run_cell` 早失败不落盘；真树 hash 仍 `fd3ca1279b40…` 未动，**等 G01 退场后执行 `out/scratch/g02_patch.py .`**。
  **39 号执行器已写完并冒烟（10-29 00:13）**：`scripts/39_g_retrain_bootstrap_run.py`（plan|run|merge），
  影子树 4 格 × 1 b（n=2000）~35 s 跑通、merge 正确写 `_provisional`；复用了**已存在**的
  `configs/budget/g02_bootstrap_overlay.yaml`（`cc5a22d`，曾被误覆盖为 6 键简版，已 `git show` 恢复原字节；
  39 号解析改为 5 必需键 + 6 可选元数据键）。冒烟抓到真 bug：
  `fit_history_models(models=None)` 会试全部模型 → L0 的 dr_learner 直接抛不适用，
  已改为按 `common ∪ additional_by_level[level]` 解析。**尚未在真树/正式 n 跑过**。
  **00:17 报告取数口径定死（"15 行"不是重复）**：17 号表按 `METRICS=("net_profit","paid_purchase_7d","any_refund_30d")`
  × (L0..L3+POOLED) = **15 行**，`population` 恒为 `full`；所以"三个 POOLED"是三个指标、不是三次运行。
  `out/scratch/g01_report_numbers.py` 改为：主表只取 `net_profit`（G01 注册口径），另两个指标单列并标注
  "未做多重比较校正"；新增 `check_shape()` 结构校验（缺列 / 缺层 / 多层 / 重复 `(metric,layer)` /
  `population≠full` / 缺主指标 = 非零退出），反例夹具 `out/scratch/g01_report_negcheck.py`
  当场跑出 **5/6** —— "缺 `mc_se`"被放行（只查 5 列，漏了渲染实际用到的另 4 列），补进必需列后 **6/6**，
  正例在 dryrun 夹具上 exit 0。**00:15 进度**：6 片各 38 行（=228/1000 层·rep），仍 ~142 s/rep，ETA 维持 ~05:30。
  **00:18 两道补强**：① `provisional != False` 时报告脚本 **exit 3** 并写明"不得作为验收凭据"（已用改 `provisional=True`、
  `L2=249` 的副本实测 exit 3）；② 用**当前真树字节**在 `out/scratch/g02_rehearsal/` 里预演 G02 补丁：10 处全落、
  `fd3ca1279b40 → 3f4d677fe1ec`、`py_compile` OK，真树 hash 未变（`g02_patch.py .` 可等 G01 退场后直接执行）。
  **00:20 半程结构体检（6 片 × 40 行，只读）**：rep 区间与分片契约逐一吻合（0–39 / 83–122 / 166–205）、
  `block` 仅 `true_aa`、`alpha` 仅 0.05、`n_total` 仅 200 000、**7 个 p 值列全在 [0,1] 且无 NaN**、
  `full_net_profit_se` 全有限；净利差均值 L0 −0.0031 / −0.0063 / −0.0012，L2 +0.0048 / −0.0018 / −0.0109
  （SE 均值 0.0384 / 0.0451）——真 AA 下效应 ≈0，与设计一致；40 rep 尺度的 `<0.05` 比例 0.000–0.100
  （s07 0/40、s11 4/40，CP 都盖住 0.05）。**只作早期体检，不作任何验收结论**；磁盘余量 91 GB。
  盘面复核 `out/g01_runner.sh`：6 lane 各 2 片顺序跑，单片失败只记 `.exit` 不中断同 lane，`wait` 后仍会
  跑 verify+merge 并写 `finished_at.txt`；verify 会拦缺 rep，故不会把缺片的结果当正式产物导出。

**G01 正式结果（2026-10-29 05:16 收尾链全绿）**：12 片全 exit 0，verify/merge/export/register **全 0**；
**POOLED 净利 FPR = 46/1 000 = 0.0460，CP95 [0.033871, 0.060884]（含 0.05）**，MC SE 0.0066；
逐层 0.056 / 0.044 / 0.040 / 0.044（描述性，半宽 ±0.026–0.031）；次级 `paid_purchase_7d` 0.0400 [0.028728, 0.054073]、
`any_refund_30d` 0.0520 [0.039077, 0.067635]（未校正）；SE 校准比 0.987–0.995；独立复算最大差 6.9e-18；
证据 `outputs/evidence/g01_aa250/` **59 登记 / 60 磁盘（含 `coverage.json`）/ 1 275 048 B / 1 000 行逐 rep**，
顶层登记 77→**91** 条 / **16 964 194 B**（10:06 补 `runs_summary.json` 后；05:16 时点是 89）。
报告 `docs/v3_phase_G01_formal.md`；**GOAL 状态仍"未证实"，待复评条件全关**。
**必须披露**：合并表 sha `2c6d6e91bf4b89ea…` 与 D02 归档件**逐字节相同**（同 `master_seed` ⇒ 确定性复现，
**不是第二个独立样本**；D02 逐 rep 表已归档为 `outputs/evidence/aa/all_repetitions.csv`，
按 `(level,rep)` 去重后与 G01 1 000/1 000 可逐 rep 比对，60/69 统计列 max|Δ|=0.0）。

**G01 退场后按序执行（恢复入口，2026-10-29 00:22 写）**：
1. 先读 `out/g01_logs/verify.exit`、`merge.exit`、`post.status`；任一非 0/非成功即**停在原地诊断**，不补跑、不改判。
2. `python out/scratch/g01_report_numbers.py`（`provisional` 非 False 会 exit 3）→ 三张指标表 + SE 校准 +
   37 号独立复算差；按 `out/scratch/g01_report_skeleton.md` 填 `docs/v3_phase_G01_formal.md`。
   注意：`outputs/tables/v3_phase_D_aa_formal_merged.*` 此刻内容是 **G01** 的，D 数字只从
   `outputs/evidence/d02_aa_phase_d_20261027/` 复算（两份 D 文档 00:22 已加注）。
3. 独立评审 → 通过后才改判 GOAL G01（"通过"只指记录准确、断言范围正确）。
4. `python out/scratch/g02_patch.py .`（真树字节已预演）→ 全量串行 pytest（`--basetemp C:/cg_t`）→
   `python scripts/39_g_retrain_bootstrap_run.py plan` → `run --reps 1` **测每 b 成本** → 报用户批准后才 formal。
5. G03：`python scripts/34_g_matrix_run.py plan`，按 §H.1 先对**最贵 Tier2 格**与**一个 core 格**各跑 R=1 定价。
  **仍未启动**：G02/G03/G04 需先落 200 次重训的执行器覆盖与 formal 守卫改造（不得改 `configs/v3/*.yaml`）。**F02 已于 22:04 改判"通过"**（第四次窄口径确认 CLOSED，
  `docs/reviews/v3_phase_F02_final_confirm.md`；含义仅"记录准确、断言范围正确"，不表示"定向有效"）。
- **登记管道修复（21:34）**：F02 目录级 coverage 补登记 19:30 的 4 条聚合文件（15→19，sha/bytes 现场重算、原有 15 条未动）；
  `scripts/33 --dry-run` 全量恢复 **exit 0**（默认 9 个有 coverage 的子目录、26 个身份类文件、顶层 76 条全表复算一致）。
  D01 首评/复评共同记录的 N9 关闭；不改任何 F02 结论。
- **D01 收尾（21:32–21:38）**：复评 6 条关闭条件全部落地并提交（`4e5d632`）；`source_binding.json` 入册 76 条；
  GOAL §交接与验收表已写入"复评 5 CLOSED / 1 PARTIAL + 6 条已落地"（`fb574e1`）。
  **第三轮独立复核 21:34 返回 PASS**（`docs/reviews/v3_phase_D01_closeout.md`）：6/6 关闭条件属实、关键数字独立复算一致、
  目录级 10/10 与顶层 76/76 条 sha/bytes 全 MATCH、manifest 与 HEAD 逐字节相同。主控独立复现下界 **1,003.0977**、
  `mean_dgp=0.4015625`、1.79/1.89 GiB、2,682.36 MiB=2.62 GiB ⇒ **D01 于 21:38 改判"通过"**（含义仅"记录准确、
  断言范围正确（20 rep / 单机 / L1_main / 三粒度）"）。
  残余处理：P3-1 精确值改 1,003.10/−182.57、P3-2 改"计划按 3 进程（实际单进程）"、P3-4 维护时间；
  P2-1 在正文注明 `source_binding.json` 的 `frozen_config_hash` 是导出时当前值（运行期按 git 推断 30511a32…，
  AA250 修订晚于运行、`L1_main` 场景块未变），并把 `scripts/38` 改为 `config_hash_current` +
  `config_hash_at_run_inferred_prefix`、git 取不到时 **RuntimeError 硬失败**（未重导出，证据字节与 76 条登记不变）。
- **F02 P1-1 关闭（21:38 建表 / 21:48 定稿）**：预测支出其实一直逐 rep 落在 `out/f02_formal/shard*/rep*/manifest.json` 的
  `arms.*.predicted_spend_*`；19:30 旧表把该列留空并注 `not_persisted_per_rep`，**注记是错的**。
  已新建 `outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv`（600 行 = 200 rep × 3 臂，
  含 predicted/realized/`realized_to_predicted`/`overspend_ratio`/`budget_cny`/`budget_deviation`/`budget_note`）并两级登记
  （目录级 **20 件**、顶层 **77 条 / 16,924,056 B**、全表复算一致）。合并实际/预测：定向 **1.056348**（逐 rep min −5.42% /
  中位 +5.09% / max +30.67%，**179/200** 为正）、随机 **1.002835**；正文 §5.2 已补。
  **收尾窄口径复核 21:43 判 PASS WITH CONDITIONS**（`docs/reviews/v3_phase_F02_closeout.md`；新发现 1 P1 + 4 P2 + 5 P3，
  另残留跨轮 2 条：P1-1 交付层、P2-2 bytes 断言）：P1-1 数据层已关闭、交付层仍开。**C1–C6 于 21:48 全部落地**：C1 改 formal §5.3/§6 的"未落盘"；C2 撤 bytes 断言；
  C3 表补 `budget_cny`+`budget_note`（119,025 B / `dbb8a869…`，600 行与汇总值不变）；C4 validation 写死"合并=Σ实际/Σ预测"并注 3e-6 口径差；
  C5 把 21:42 条目的 `refreshed` 字符串数组改为 `added` 并更正为实际写盘 21:38，另加 21:48 的 `refreshed` 对象条目；
  C6 formal 计数改 77 / 16,924,056、validation 抬头与 §5.3 标题改"已完成"。**22:04 第四次窄口径确认 CLOSED 后已改判"通过"。**
  **21:55 第三次窄口径复核**（`docs/reviews/v3_phase_F02_c1c6_recheck.md`）：C1–C6 六条逐条全关（自算 pooled 1.056347991 / 比值均值 1.056345050、
  `budget_cny` 400/400、77/77 与 20/20、`33 --dry-run` exit 0 未写盘），但因 **validation:21 的"独立科学评审"仍写"未做"（P2）** 判 NOT CLOSED。
  该 P2 与 5 条 P3（§5.4 标题仍"未运行"、21:48/21:45 时点、"未按 bytes"措辞、决策日志归属、"未重导出"表述）已于 **21:57 全部修完**。
  **22:04 第四次窄口径确认判 CLOSED（可改判）**（`docs/reviews/v3_phase_F02_final_confirm.md`）：6 条修复全部属实、C1–C6 无回归、
  pooled 1.056347991 / 1.002835123 复现、77/77 与 20/20、`33 --dry-run` exit 0 → **F02 据此由"未证实"改判"通过"**，
  含义仅"记录准确、断言范围正确（200 rep / 20 万新用户 / 三臂 ITT / 合成 DGP / 0.2 元档）"，**不表示"定向有效"或可部署**；
  审计价值未在本阶段交付（已声明移交 D01/G）。
- **推送**：20:54 首推失败（443 不可达）后 **21:26 成功**，远端 `a351ec3`；此后 `fb574e1`（D01 状态入册）、`d3b0082`（N9 补登记）待推。

**2026-10-28 19:25 更新。D01 完成；G 甲方案已执行并经独立评审（条件已关闭）；F02 评审条件正在关闭**：
- **D01**：20 rep × 3 粒度（L1_main，n=200 000）**16:51:36–18:20:43、exit 0、failed=0**。
  G1 131.051±11.198 s、G2 256.833±20.684 s、G3 256.859±20.686 s、G3+DGP 257.260±20.827 s、墙钟 267.119±21.741 s；
  CPU/墙钟 0.9617（0.9510–0.9717）；进程峰值 2,682.36 MB，rep 8 后平台化（12 rep 无增长）。
  外推（AA250 计数）：**≈991 CPU·h**；3 进程 ≈344 h ≈14.3 天（4 进程 10.7 天但 4×2.68 GB 超 8.4 GB）。
  跨层缺口已由下方 L0/L3 补测关闭。正文 `docs/v3_phase_D_pilot.md` §11。
- **G 甲方案已落盘**：**12 行**（11 行补丁 + 18:36 补正 `design.yaml:38` 的 AA 副本 1000→250）。
  新协议 `outputs/v3/protocol_aa250/`：`config_hash=00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3`、
  matrix `30645842…`、design `8890d25b…`、execution `58623f85…`、scenarios `b8fa1480…`、`protocol_sha256` 不变 `eb85a328…`。
  修订档 `approval_revision_20261028.json`；Phase A `approval.json` 原字节保留；`docs/v3_协议.md` 未编辑。
  **独立评审 19:09 判 PASS WITH CONDITIONS**（0 P0 / 1 P1 / 3 P2，`docs/reviews/v3_phase_G_aa250_review.md`）：
  12 行、7/7 源哈希、Phase A/F02 绑定不变、1 275 项/518 s 均独立复算通过。C1 回滚补 tests 4 行与 `--output`；
  C2 GOAL 11→12 行并指向理由文档；C3 §5.5 字节数与 source_sha 表述——已于 19:25 全部关闭，`reason_doc.sha256` 重绑 `21ea04fd…`。
  **G01 可按新契约开跑；G01–G04 尚未启动。**
- **测试**：18:24 首轮全量串行 **EXIT=1**，2 项失败均为旧契约硬编码（`test_v3_aa.py` 的 1000、`test_v3_power.py` 的 `FROZEN_CONFIG_HASH=30511a32…`）；
  已按新契约更新为 250 / `00723dc2…`（不是放宽校验，是更新冻结值）。最终干净全量串行 **1 275 项、EXIT=0、18:36:49–18:45:27（518 s）**，
  凭据 `outputs/evidence/test_runs/pytest_g_aa250_20261028_1836.{log,json}`；首轮失败日志保留为 pre-fix 凭据。
  顶层登记 **48 → 54**（补 16:42 F02 树那组此前漏登记 + 18:24/18:36 两组），`registry_repairs` 第 8 条，`total_bytes` 15 916 738。
- **L0/L3 资源补测（已完成）**：18:48:36–18:57:27、两 rep 均 exit 0。
  `L0_P_main` G3+DGP 253.922 s / 墙钟 266.865 s / 峰值 1,836 MB；`L3_fixed_lt000` 227.297 / 240.713 / 1,934 MB；
  与 L1 均值最大相对差 **11.65%** < 50% 阈值 ⇒ 跨层同量级由外推变为实测（各仅 1 rep，无层内方差）。
  四份明细/汇总已入 `outputs/tables/v3_phase_D_pilot_{raw,summary}_{L0,L3}_r1.*`。
- **F02**：正式 200 rep 完成；独立评审 19:17 **PASS WITH CONDITIONS**（结果层全部复现）。19:30 已导出逐 rep 实际支出（600 行）、
  200 rep 绑定表、4 分片、snapshot binding 并把 11 条新记录登记入 `coverage.json`（**54 → 65**、`total_bytes` 16 746 236，全表复算 PASS）；
  正文已修 Wilson→Clopper–Pearson、constant 过强表述、预算偏差分母、26 artifact bytes、审计价值移交 D01/G、局限 7 条。
  **仍未关闭**：逐 rep **预测**支出未在运行期落盘（P1-1 预测/超支倍数部分开放）；故 F02 仍记**未证实**，不改判"通过"。
  D01 的完成不改变这一点。**（22:04 追记：该判断已被推翻——预测支出一直逐 rep 在 manifest 里，是 19:30 的导出脚本没读；
  P1-1 于 21:38 关闭、C1–C6 于 21:48 落地、22:04 第四次窄口径确认 CLOSED 后改判"通过"。）**
- **推送**：19:26 `git push origin codex/d03` **成功**（`193ff48..1b2f5b3`），远端已同步到独立评审提交；
  此前 18:47–19:04 五次失败均为网络不可达，未做重试循环。

**2026-10-28 16:55 更新。F02 正式 200 rep 完成（阶段状态仍为“未证实”，独立评审未做）**：
四片于 16:39 集齐 200/200、各退出 0；合并与证据导出 **exit 0**（16:37）；官方聚合 `scripts/32` 在 200 rep 上 **exit 0**。
决策层：`coupon_worth_issuing` **196/200**（差 0.281630 ± 0.005072 元/人，Holm p 中位 3.62e-7）、
`targeting_better_than_random` **190/200**（差 0.214167 ± 0.005015，Holm p 中位 7.34e-5）、
两项+护栏同时 **190/200**；护栏 **200/200**（最大单侧上界 0.003946 < 0.005）。
分层（R 合计 200）：`causal_forest` 105/105+105/105、`s_learner` 71/71+**69/71**、`dr_learner` 12/12、`t_learner` 5/5+4/5、
**`constant` 3/7 + 0/7**（真实/预测支出比 1.2602，五层最高）⇒ 正文已按 §12.6 分层，不得合并成“定向普遍有效”。
**代表 rep 0 恰为 `constant` 零结果**（两项均不通过，Holm p 0.598），已在正文 §4.4 显式限定：它只证明交付链按契约工作，不能支撑或否证“定向有效”。
预算口径：预测支出/人全 200 rep 最大 **恰为 0.200000**；真实支出定向 0.211268、随机 0.200567（比值 1.0563 / 1.0028），
人均多花 0.010701 元 ≈ 效应的 5.0% ⇒ 只能写“计划同预算”。
全量串行测试 **1 275 项、exit 0、16:42:18–16:51:00（522 s）** 已入库；顶层登记 44 → **48** 条、全表复算一致。
**D01**（20 rep，已批准）于 **16:51:36** 起跑；**G 甲方案补丁必须等 D01 退出后再打**——D01 是 R>0 运行，`configs/v3*.yaml` 在绑定 glob 内，运行期改配置会让它抛 `source files changed during the data run`。详见下方「G 阶段前置阻塞」节末的用户裁决小节。

**2026-10-28 10:57 更新。A/B/C/D02/D03/E01/E02/F01 通过**（E 于 05:53 走完第三环窄口径确认；D03 于 05:15 经独立复审 PASS 关闭；**F01 于 10:52 改判"通过"**——第四环窄口径复核 07:21 PASS WITH CONDITIONS（`docs/reviews/v3_phase_F01_recheck.md`），5 项 RC 已 10:45–10:47 逐项复算修完、条件"在改写状态之前或同批"已满足；"通过"仅指记录准确、断言范围正确：单 rep / rep 0 / `formal_repetitions=0` / `constant` 模型 / 0.2 元档，**不表示"定向有效"**）。**F02** 正式 200 rep 于 **03:39** 起跑，**11:26 时 120/200**（shard0/1 已完成 0–99；shard2 完成 100–109、shard3 完成 150–159；rep 110 / 160 在跑），**两条 lane 均有独立内存看护**（lane 2 于 10:54:45 启动，PID 67048/65688；两 lane 峰值 2 436 / 2 207 MB，`low_streak=0`），两 lane 的 rep 间隔**随选中模型变化**（11:00 后实测：`s_learner` 365–472 s、`dr_learner` 373–483 s、`causal_forest` 484–670 s 且后段越来越慢），近 8 个 rep 的中位 475 / 441 s、最近两个 671 / 668 s ⇒ **ETA 区间 ~16:40–18:50，取 ~18:00**（11:16 的 ~229 s/rep 与 10:57 的 ~15:55 都偏乐观，§12.5）。这条"每 rep 成本由选模决定"的分布也要写进 F02 正文的耗时一节。等待期已用独立评审后的聚合器重写版跑通 **118 rep**（`out/scratch/f02_aggregate.py`）：合并 115/118 判"发券值得"、111/118 判"定向优于随机"，三层同时通过 111/118；分层后 **`constant` 2/5 与 0/5**、`s_learner` 41/41 与 39/41、`causal_forest` 66/66、`dr_learner` 5/5、`t_learner` 1/1 ⇒ 正式正文必须分层（§12.6）。另记一条限制：等预算匹配的是**冻结时刻的计划支出**，实际支出比定向 **1.0609**、随机 **1.0048**（各 rep 相对 0.2×分配人数）。**G 阶段前置阻塞：用户已于 11:05 裁决走甲方案**（只把 **AA 4 层对齐到 250/层**，共 11 行（含两个计划计数）；补丁 `out/scratch/g_route_jia_aa250.py` dry-run 已逐行通过、真跑安全阀已实测拦住 116/200；**等 F02 四片退出后**执行"改配置 → 09 号重算进**新目录** `outputs/v3/protocol_aa250` → 新建修订文件（`approval.json` 原字节保留）→ 版本化理由 → 独立评审"）。其余项保持冻结值，因 GOAL G01/G02 仍以冻结值为验收标准；详见「G 阶段前置阻塞」节末的用户裁决小节。**D01** 20 rep 已批准、排在 F02 之后（最早 ~16:05 起、92 分钟独占）。运行期冻结：四个绑定 glob 与 `scripts/30` 在四分片退出前不得改。详见下方 10:56 本轮与 `docs/v3_决策与反思日志.md` 10:56 条。

**2026-10-28 11:10–11:20 本轮（聚合器按独立评审重写并在 118 rep 上跑通；ETA 按中位重估）**：
- [x] **独立评审（只读）判 `out/scratch/f02_aggregate.py` 首版：0 P0 / 5 P1 / 8 P2**。5 条 P1 全部成立，已重写：
      (1) 预算分母取自**当前配置**而非**该 rep 运行时的 manifest** ⇒ 改为逐 rep 读 `manifest.budget_cny_per_user` 并断言与当前配置一致；
      (2) 用 1.96 而非 **t(R−1)** ⇒ 改 `scipy.stats.t.ppf(0.975, R−1)`（`constant` 层 R=5 时 2.776，CI 会明显变宽）；
      (3) claim→contrast **方向未钉死**（上游写反也能自洽）⇒ 加 `HARD_MAP` 同时校验 `contrast` 与 `configured_contrast`；
      (4) 分层结果**未落盘** ⇒ 新增 `f02_agg_by_model.csv`；
      (5) `groupby("selected_model")` 遇 NaN 会**静默丢 rep** ⇒ 先断言无 NaN 且 `by_model.R` 之和 == 总 R。
      另加：`manifest.json` 进必需文件、rep_id/status/formal_approval/scenario 一致、三臂 `n_assigned` 之和 == `manifest.n_users`、
      `diff == mean_net[targeted] − mean_net[对照]`、`n_left/n_right` 对上臂人数、护栏 `passed == (upper < margin)`、`config_hash`/`source_digest`/预算/`n_users` 逐 rep 唯一、写入前查 NaN。
- [x] **首跑即抓到我自己的两处缺陷**（都不是评审提的）：① `freeze.json` 只有 **7 个键**（`decision_hash/freeze_hash/guardrail_hash/per_user_hash/selected_model/selected_policy/truth_columns_present`），**没有 `rep_id`**，我新加的守卫去比较 `freeze["rep_id"]` 直接 `FAIL[4]` 在 rep0 崩掉；② 写了一段
      `if abs(predicted_spend − total_coupon_cost) > 1e-6: pass  # …` —— **一个永远什么都不做的"检查"**，形似校验、实为死代码，已删并改为把两个量各自记录。
- [x] **118 rep 跑通**（`--allow-incomplete`，11:16）：全体 发券值得 **115/118**、定向优于随机 **111/118**、三项同时 **111/118**、护栏 **118/118**（max upper 0.003946 < 0.005）；
      分层 `causal_forest` 66/66+66/66、`s_learner` 41/41+**39/41**、`dr_learner` 5/5+5/5、`t_learner` 1/1、**`constant` 2/5 + 0/5**。
      产物 `out/scratch/f02_agg_by_rep.csv` / `_by_model.csv` / `_summary.json`（不入库）。
- [x] **记一条正文必须写的限制**：等预算匹配的是**冻结时刻的计划支出**（`budget_basis=same_per_assigned_user_in_each_active_arm`，预测支出/人 ≤ 0.200000、rep 级预算偏差 ≤ 0.36 元），
      **实际**支出/计划支出 定向 **1.0609**（p05/p50/p95 = 0.9749/1.0569/1.1504）、随机 **1.0048**（0.9599/1.0016/1.0566）⇒ 定向实际人均多花约 0.011 元，而效应是 0.214 元/人；
      比较不是"实付等支出"，这条要与 F01 的 N-3 同类限制并列写。
- [x] **ETA 重估**：近 8 个 rep 的间隔中位 475 / 441 s（最近两个 610 / 594 s）⇒ 合并 ~229 s/rep、剩 82 rep ≈ 5.2 h ⇒ **投影 ~16:40**；D01 顺延到 ~16:45 起。
- [x] **补一条真缺口：缺 rep 不失败。** 原版只在"目录存在但缺件"时 `FAIL`，而 rep 目录尚未生成时**照常出口径、写产物、exit 0**
      ⇒ 200 rep 的正式聚合法可以在只有 118 个 rep 时"跑通"。已改为缺 rep 与缺件都默认 `FAIL[2]`，`--allow-incomplete` 仅供等待期诊断。
- [x] **无人值守收尾已挂上（11:24:50，PID 8374）**：`out/scratch/f02_postmerge_auto.sh` 等 200 个 `freeze.json`
      → 等 `outputs/evidence/f02_formal/coverage.json`（`f02_finalize.sh` 的合并产物）→ 以 **无 `--allow-incomplete`** 跑官方聚合
      → 证据登记 `--dry-run`；全程只写 `out/` 与 `out/logs/f02_postmerge_auto.log`，**不改文档、不登记证据**。
- [x] **11:30 证据登记工具提入入库区**：`out/scratch/register_evidence_top.py` → **`scripts/33_register_evidence_top.py`**
      （`ROOT` 改 `parents[1]`，用法行改 `scripts/`；§12.1：`out/` 不入库，放在那里的登记工具对评审者等于不存在）。
      等价性实测：新旧两份 `--dry-run` 输出 **diff 0 行**、两者 exit 0、顶层 44 条全表复算一致。
      scratch 旧路径**改为 exec 新文件的 8 行垫片**（不删，因为在跑的 `f02_postmerge_auto.sh` 第 42 行与 `post_f02_check.sh` 会调用它；
      直接编辑正在运行的 shell 脚本会让 bash 按字节偏移读错行，改被调用的 python 文件则安全）；`post_f02_check.sh` 已直接改指 `scripts/33`。
      待办：把 6 例演练夹具提成 `tests/` 下可跑用例（当前演练结果只记在 33 号 docstring 里）。
      加上既有的 `f02_chain.sh` 与 `f02_finalize.sh`，三个等待进程并存；恢复工作前先读该日志。
- [x] **顺手把 G 的落地链改对了（11:25）**：原计划"跑 09 号 → 更新 `approval.json`"会**就地覆盖 Phase A 快照**
      （`outputs/v3/protocol/` 的 `protocol_sha256` 绑定 `docs/v3_协议.md` 的字节，重跑等于改写"Phase A 批准了什么"）；
      且 09 号把 `experiment_results_exist` **硬编码 `false`**（第 39 行），今天已有 D02–F02 结果，直接采信会产出一条假陈述。
      改为：重算落 `outputs/v3/protocol_aa250/`、新建 `approval_revision_20261028.json`、`approval.json` 保留原字节；
      理由文档 §5 同步改写（含"不编辑 `docs/v3_协议.md`"这条约束）。
- [x] **聚合器提为 `scripts/32_aggregate_f02_formal.py`**（`out/` 不入库，留在 scratch 等于别人无法复算），删掉 scratch 副本并把 `post_f02_check.sh` 改指新路径；
      配 **11 个反例夹具** `tests/test_v32_aggregate_f02_formal.py`（复制真实 `rep0/rep1` 再篡改，不手抄表头），**11/11 通过、约 60 s**。

**2026-10-28 07:13 本轮（给 G 定价时查出重复预算契约冲突；推送再失败 1 次）**：
- [!] **G 阶段前置阻塞（新发现，需用户裁决）**：`configs/v3/`（代码实读、绑定 `approval.json`）与
      `configs/budget/repetition_overlay.yaml`（用户 2026-10-25 授权）是**规模差 12.2 倍的两个实验**：
      冻结侧 **55 100** 作业（Tier1 核心 6 400 + Tier2 43 500 + AA 4 000 + 再训练 200 + 固定 bootstrap 1 000），
      overlay 侧 **4 513** 作业。分项倍数 Tier2 **120.8×** / 功效格 **10×** / Tier1 **8.0×** / AA 与独立验证各 **4.0×** /
      再训练 bootstrap **2.5×**，另有固定策略 bootstrap 1 000 与随机名单种子 200 两项 overlay **未提**。
      **overlay 无任何代码读取**（`grep -rn "overlay"` 在 `src configs scripts` 的 `.py`/`.yaml` 返回 **0** 行），
      其第 2 行自述"不修改 configs/v3/ 下七份冻结配置" ⇒ 真跑一律按 55 100 那一版。
      TODO:142 的评审条件 C1 要求"GOAL/G01/YAML 与 overlay 对齐"、状态记"GOAL 已改"——**GOAL 与 overlay 对齐了，YAML 从未对齐**。
      详见下方「G 阶段前置阻塞」节与反思日志 2026-10-28 07:11 条。
- [x] **AA 单 rep 成本改为实测定价**：`outputs/evidence/aa/all_repetitions.csv`（1 384 行、4 格 × 250 个不同 rep、n=200 000）
      `total_wall_s` 均值 **160.00 s**、sd 19.82、max 186.80，`total_cpu_s/total_wall_s = 0.975`（单线程、无并发争用虚高），
      `file_lock_retries` 仅 **8/1 384** 行非零；旁证 `outputs/evidence/negctl/aa_repetitions.csv` 100 行均值 **160.98 s**（差 0.6%）。
      ⇒ overlay 路线 1 000 次 = **44.4 CPU·h**、冻结路线 4 000 次 = **177.8 CPU·h**，差 **133.3 CPU·h**。
      按 §12.5 报最差口径并写明分母：**实测比 GOAL.md G01 隐含的 117.9 s/rep 高 35.7%**（反向说 GOAL 低 26.3%，两个方向都记）。
- [x] **否证 overlay 的并行度假设**：overlay 写 `parallel_workers_max: 4`、理由"单 rep 峰值 1.88 GB"；
      F02 现场 memwatch（07:12）两条 lane 峰值 RSS 实为 **3 168 / 2 914 MB**、free 2 783 MB。
      1.88 GB 只对"不拟合模型的 AA 形 rep"成立，而冻结计划 **34 100 / 55 100 = 62%** 是完整学习（必拟合模型）
      ⇒ 墙钟一律按 **2 workers** 重算：overlay 路线约 **2.8 天**、冻结路线约 **33.5 天**（1 610 CPU·h ÷ 2）。
- [x] **否证我自己对 manifest 戳的误读**：AA manifest 的 `purpose=engineering_or_downstream_input_not_formal_completion`、
      `formal_repetitions_completed=0` **不是**"D02 那 1000 次不正式"的证据——它是全项目所有写 manifest 入口的**统一戳**
      （`v3_pipeline.py:120/214`、`v3_power.py:1181/2237`、`v3_local_power_pipeline.py:976`、`v3_data_checks.py:206/418`、`v3_aa.py:1038`），
      `v3_aa.py:67` 明写"本入口不改变任何正式计数器"，`v3_data_checks.py:407` 甚至**断言** `no_formal_repetitions_claimed`。
      ⇒ 正式与否由验收记录判定。这是 06:13 那条"写进证据前先验证机制"规则**第二次**拦住我。
- [x] **核实既有 AA 证据不可复用于 G01**：其 `source_hashes_before` 与当前工作区相比，**9 份 `configs/` 逐份未变**
      （`execution.yaml` 当时与现在都是 `dc1c8e9a…`、`scenarios.yaml` 都是 `29a158b0…`）⇒ 那 250/层是在**配置已写着 1000/层**时跑的；
      但 **6 份源码已漂移**（`v3_local_power_pipeline.py`、`v3_observed.py`、`v3_power.py`、`v3_local_power.py`、`v3_models.py`、`v3_data_checks.py`）
      ⇒ 按 §12.6 不得跨源码版本配对，**G01 的 AA 无论选哪条路线都要在当前树上重跑**。
- [!] **机制上现在改不了冻结配置**：`src/causal_growth/data/v3_pipeline.py:41-44` 的绑定 glob **含 `configs/v3/*.yaml`**，
      F02 四分片未退出前改它会让作业抛 `RuntimeError: source files changed during the data run`（AGENTS §11）⇒ 最早在 F02 合并后。
      改它要动 **11 处**（`execution.yaml:25` + 4 格 `complete_aa` + 同 4 格 `R` + `scenarios.yaml:261/264` 两个计划计数；`historical_dgp_jobs` 是模拟运行抓出来的），
      且 `execution.yaml` 自带 `change_matrix_requires_versioned_reason_and_review: true` ⇒ **须版本化理由 + 评审**。
- [ ] **推送又失败 1 次**：提交 `ada408c`（清除三份文档里过期的"推送失败"状态）于 **06:56** 推送失败
      （`Failed to connect to github.com port 443 after 21062 ms`，exit=128），本地 `[ahead 1]`，提交安全。
      **仍不装无人值守重试循环**，下个检查点再试。

**2026-10-28 10:56–10:57 本轮（F01 第四环 5 项 RC 落地并改判"通过"；F02 114/200 + lane 2 看护 + 聚合器预演）**：
- [x] **F01 第四环窄口径复核 07:21 返回 PASS WITH CONDITIONS**（`docs/reviews/v3_phase_F01_recheck.md`，27 765 B）：
      R1 判 3 条 P1 **真实关闭**并独立重建贪心名单（n=23 437、预测 11 999.505475、真值 15 410、比 1.284220）；
      R2 判 9 条 P2 **逐条关闭**（N-12 属实，但**原表述引入 RC-1**）；
      R5/R6 判登记 44 条 + 18 条四向核对 **0 不符**、1 264 进度点 / 0 标记 / `EXIT=0`；
      新提 **RC-1/RC-2/RC-3 + RC-4/RC-5**，并**明确授权**把 GOAL.md 的 F01 行由"未证实"改为"通过"（条件：RC-1/2/4 在改写之前或同批修完）。
- [x] **5 项 RC 逐项本机复算后 10:45–10:47 修完**：
      RC-1 复核原文"32 行同常数"为假——实测 8 行为 `no_coupon`（`n_selected=0`、`predicted_value=0.0`），比值是 0/0=`NaN`；改为"恒等式 `predicted_value = τ̂·n_selected` 对 32 行成立、比值仅 24 行有限（4 个浮点值跨度 1.7e-16）、8 行 NaN"（`docs/v3_phase_F01_ope.md` §4.1）；
      RC-2 顶层 E 记录 **22 → 23**（`e_evidence_rep0_a` 11 + `e_evidence_rep0_b` 12），并改为按复核时点实读、不保证以后不变；
      RC-3 sidecar 行尾断言"仓库里的 `.md` 一律 LF"为假——实读 **70 个入库 `.md` 中 18 个含 CR**（AGENTS.md 223 CR / 246 LF），已改实测表述；sidecar **2 571 → 2 891 B**、sha256 `7c50c11e…` → `b163b159…`，顶层登记刷新并新增**第 6 条 repair**，四向核对 44 条全绿（`total_bytes` 以实读文件为准）；
      RC-4 GOAL.md 尾部"9 条 P2 待修"随 F01 行改写消除；RC-5 `command_line_source` 由 `TODO.md:262` 行号改为锚文本引用。
- [x] **F01 改判"通过"（10:52）**：GOAL.md（L3 维护时间、L7 交接节点、F01 行、R01 行）、`docs/v3_phase_F01_ope.md`（页首状态 + 第四环段 + §1 评审行 + §6 结论句）、本文件、AGENT_HANDOFF.md 同步。
      **含义边界写进每一处**：只表示"记录准确、断言范围正确"（单 rep / rep 0 / `formal_repetitions=0` / `constant` 模型 / 0.2 元档），**不表示"定向有效"、不表示策略可部署**。
- [~] **F02 进度**：10:57 时 **114/200**，合并 ~208 s/rep ⇒ **投影 ~15:55**（详见上方 F02 条目）。
- [x] **已完成 112 个 rep 的只读结构审计（10:51）**：唯一 `rep_id`；`config_hash` 全为 `e1aa4314…`；
      `source_hashes` 摘要全为 `d8327ae0…`（与快照绑定一致）；`formal_approval` 全同；
      `n_users` 全为 200 000；rep0 是唯一 `representative_five_tables=true`（其余 rep 按设计不落五表，
      首版审计脚本把它误报成缺件，已按设计修正预期）；11 个顶层文件 0 缺件；`status` 全 `formal`、`failures` 0 —— **0 项异常**。
      收尾等待进程 `out/scratch/f02_finalize.sh`（PID 1656，04:04:41 起）与 `f02_chain.sh` 均在运行。
- [~] **F02 决策层只读诊断（10:55，n=112/200，仅诊断、不作正式结论）**：护栏 **112/112 通过**，
      最大退款率差 **0.003134 < margin 0.005**（余量约 63%）；"发券值得"119→**109/112 通过**、
      "定向优于随机"**106/112 通过**；两对比的效应**无一为负**（worth 均值 0.281387 / 中位 0.286910；
      better 均值 0.214574 / 中位 0.217605）。
      **关键分层信号**：6 个失败 rep 集中在 `constant` 模型（5 个 constant rep 里 0 个通过 better、
      2 个通过 worth；另 1 个 `s_learner` rep50 仅 better 未过），而 `causal_forest` 63/63 两对比全过、
      `dr_learner` 4/4、`t_learner` 1/1。
      ⇒ **正式正文必须按 `selected_model` 分层报告通过率并给出各层构成**，否则聚合会被选模构成改变（AGENTS §12.6）；
      该现象与 F01 的"`constant` 时 τ̂ 退化、定向退化为按成本排序"机制一致。
      产物 `out/scratch/f02_partial_diag_1055.csv`（不入库；合并后用正式 200 rep 重算）。

**2026-10-28 11:00–11:08 本轮（用户裁决 G 走甲方案；AA 补丁在副本上预演，抓出第 11 行与一个死代码缺陷）**：
- [x] **用户 11:05 给出裁决**：「G阶段按甲方案。按照你的思考和建议的方式推进。」
      ⇒ 范围为 **AA 4 层 × 250**（2026-10-25 授权值），共 **11 行**配置改动（11:08 模拟运行补出第 11 行 `historical_dgp_jobs`）；**不照搬 overlay 的其余削减**
      （ATE 500 / 学习 200 / 独立验证 200 / Tier2 100 / 再训练 200 / 固定 bootstrap 1000 仍是 GOAL G01/G02 的验收值），
      理由：TODO:142 的评审条件 C1 只点名 AA，其余项一旦同步下调等于**同时改验收标准**。决策与落地链见「G 阶段前置阻塞」节末。
- [x] **补丁工具 `out/scratch/g_route_jia_aa250.py` 就绪**（`out/` 不入库）。`--dry-run` 逐行输出 11 处旧值→新值：
      `execution.yaml:25`、`scenarios.yaml:261/264/411/429/1296/1314/1925/1943/2942/2960`，断言恰 1 + 10 = 11 行；
      写后 `load_v3_protocol()` 复核 `tier1_aa_per_layer=250`、四格 `(R, complete_aa)=(250,250)`。
- [x] **安全阀实测有效（不是装饰）**：真跑模式在 F02 未集齐时 `exit=5`：
      `FAIL[5] F02 只有 116/200 个 rep manifest，冻结窗口未结束，拒绝改冻结配置（AGENTS §11）`。
- [x] **两处反例当场被自己的工具拦住**：① `scenarios.yaml` 是 **CRLF**（CR 3407 / LF 3407）、`execution.yaml` 是 LF，
      按 `"\n"` 切行后行锚点 0 命中 → `FAIL[4]`；改为按**每个文件自身终止符**切行/写回，并拒绝混合行尾。
      ② `replace_once` 就地改列表，`changed_exec` 拿同一对象比较**恒为 0** → `FAIL[7]`；改为先留原列表副本。
      ⇒ 同一类坑（行尾、别名共享）在本项目已各出现两次，写盘类工具一律"先留副本、再按文件自身格式写回"。
- [x] **核实 `R` 的绑定约束**：四格 `formal_repetitions` 只有 `complete_aa` 一个键，`R=250` 满足
      `v3_config.py:189` 的 `R == max(values)` 与 `v3_aa.py:316-318` 的 `complete_aa == tier1_aa_per_layer == R`。
- [x] **在配置副本上预演，抓出第 11 行（11:08）**：把 `configs/v3/` 复制到 `out/scratch/sim_v3_aa250/`，
      用工具的 `--root` 走**同一条代码路径**真改再完整加载，立即抛
      `ConfigError: Planned count drift historical_dgp_jobs: declared=12500, derived=9500`——
      `v3_config.py:207-210` 会把 `planned_counts` 的 17 个计数逐项与推导值比对，而 `historical_dgp_jobs = Σ max(formal_repetitions.values())`，
      AA 四格各降 750 ⇒ 总量 −3 000。**正确改动是 11 行**（补 `scenarios.yaml:261 historical_dgp_jobs: 12500→9500`）。
      补上后副本**完整加载通过**：四格 `(R, complete_aa)=(250,250)`、`historical_dgp_jobs=9500`、`complete_aa_jobs=1000`，
      新 `config_hash=6b672610…`（当前真实 `config_hash=30511a32…`，与 `approval.json` 一致；`e1aa4314…` 是另一层级的 `protocol_config_hash`）。
      **同轮还暴露一个死代码缺陷**：写后校验用 `scenario(cell).require("R")`，正确路径是 `active_scenario.R`；
      这段校验此前从未执行过（真跑一直被安全阀挡住），第一次执行就报错。⇒ 若直接真跑，会留下"配置已改、加载器不通过"的中间态。
- [x] **收尾编排脚本（11:12）**：`out/scratch/post_f02_check.sh`——先断言 200 个 `freeze.json`、再断言
      `outputs/evidence/f02_formal/coverage.json` 已由合并生成，然后跑正式聚合（无 `--allow-incomplete`）与证据登记**预演**。
      安全阀已实测（11:12 时 116/200 → `FAIL: F02 未集齐`，exit=3）。
- [x] **版本化理由文档草稿（11:10）**：`docs/v3_phase_G_protocol_change_aa250.md`，86 行；§3 的前后绑定值保留 `<待填>`，执行时实测填入。
- [!] **仍未执行的边界**：这次只是"补丁就绪 + 文档记录"，**配置一个字节都没改**；真跑必须等 F02 四分片退出（AGENTS §11）。
      push `514495e` 上次失败（网络重置），本轮再试一次。

**2026-10-28 06:37 本轮（F01 复审 9 条 P2 落地 + 一次"同类缺陷"横向清扫 + §11.4 测试凭据入库）**：
- [x] **F01 复审 9 条 P2 全部逐项本机复算后修完**（`docs/v3_phase_F01_ope.md` 481 → 573 行）：
      先复算、后改字，每条数字都从 `outputs/evidence/f01_ope/` 与 `outputs/tables/v3_phase_F01_*.csv` 重算通过——
      **N-4** 中位数补齐三种分母（16 行里有限值 15 行 → 中位 **0.608254**；再剔 1.00 退化档 14 行 → **0.631856**；
      全 48 行 → **0.654755**；max **2.079634** 在 0.04 档 定向−随机），原文"中位约 0.63"对应 14 行口径但没写分母（§12.5）；
      **N-5** 补 8 档 × 2 口径全 16 格（DR n_at_least 50/57/**68**/36/**89**/54/79/200，真值 165/77/15/0/0/1/0/200），
      并点名原文只引的 0.2 档（DR `rank_low=0.015`）**恰是全表最有利于定向的一档**，0.40 档有 89/200 = 44.5% 随机不劣于定向；
      **N-6** 更正哈希标注错位：`372a1bcc…` 是 E 的**全 9 列帧** `dataframe_sha256`，7 列选人投影是 `3ef75e0f…`，两者不可互换；
      **N-11** §3 字段表加"所在文件"对照（`freeze.json` 顶层 **16** 键、**不含** `source_hash_combined`；
      `source_hash_combined`/`truth_sha256`/`frame_hashes.*`/`reference_frame.*`/`stage_seconds`/`gates` 只在 `meta.json`，顶层 **31** 键）；
      **N-12** §4.1 加显著告示：`predicted_value/n_selected` 对**全部 32 行**同为常数 **0.29380318**（`tau_hat` 唯一值个数 = 1），
      故它只反映名单规模、**不反映选人精度**，不得被下游当模型质量证据；
      **N-7** 披露 `meta.reference_frame.path` 是本机绝对路径（含用户名与 worktree 哈希，`out/` 不入库），
      可验证性不受影响（另有 `selection_sha256`/`frame_sha256`），改存仓库相对路径需重跑、受 §11.2 限制 ⇒ 列 F02 后待办；
      **N-8** 正文不再钉可变计数器：F01 的验收对象改为**目录级 18 条记录**（`total_bytes=9 490 785`），
      顶层索引只登记 freeze/meta 两条、其条数随其他阶段变，**不作 F01 验收对象**；
      **N-9** 点名掩码长表是 18 条里最大的一条（5 305 073 B / 1 920 000 行），`in_repository=false` 是刻意选择不是缺件；
      **措辞残留** line 35 / 459 的"按预声明口径"改为"按本阶段主口径（DR，见 §2.1）"，
      并注明 `configs/` 里**没有** `primary_estimator` 之类的 YAML 预声明字段，该选择由源码哈希冻结。
- [x] **§12.4 的"grep 旧值"升级为"grep 同类"，横向扫出 3 处此前没发现的同类缺陷**：
      ① `docs/v3_phase_F01_ope.md` §4.7 **标题**仍写"可定义的 7 档全部是外推"，与本轮 N-3 已改正的正文自相矛盾 ⇒ 改为"档内全部是外推，跨档合并是插值"，
      并把该节"三个必须一起读的事实"第 1 条限定为**档内**回归；
      ② 同文 §8 检查单仍钉"（**42 条中**）"与"`registry_repairs` 现有 **3 条**……35 → 41 条"（实际已 5 条 / 44 条）⇒ 改为"筛出 `f01_ope` 前缀那两条后逐条核 sha256/bytes"，验收与总条数解耦；
      ③ `docs/v3_phase_E_evidence.md` §检查单同一处也钉死"**42 条记录、`total_bytes` 15 861 713**"⇒ 同样解耦，并补全 5 条 repairs 的时间线。
      三份文档的 `docs/reviews/*.md` 里的同类数字**一律不改**：那是评审在其观测时点的不可变凭据（AGENTS §10）。
- [x] **N-10：AGENTS §11.4 的全量串行测试凭据入库**（此前两份 pytest 日志**都不在仓库里**）：
      复制 `out/logs/pytest_full_20261028_0321.log`（1 527 B）到 `outputs/evidence/test_runs/`，
      配 sidecar JSON 记全命令行 `.venv/Scripts/python.exe -m pytest -q -p no:warnings --basetemp C:/cg_t`
      （**来源标注 `TODO.md:262`，逐字照抄，不是凭记忆写的**）、起止 03:21:18–03:27:42 / 384 s / `exit=0`、
      进度点 **1 264** 个与 `F/E/s/x/X` 标记 **0** 个、`collected_tests=1264`（由 `--collect-only` 独立确认）、
      以及**冻结树检查**：`find src sql configs -newermt "2026-10-28 03:21:18"` 覆盖四个绑定 glob 返回空 ⇒ 该日志描述的正是 F02 绑定的那棵树。
      sidecar 还记了"末行为何没有 `N passed` 汇总"的机制：`pyproject.toml:39` 的 `addopts` 已含一个 `-q`（verbosity=-1），
      命令行再给一个 `-q` ⇒ verbosity=-2，而 `.venv` 内 `_pytest/terminal.py:1253` 的 `summary_stats()` 开头是
      `if self.verbosity < -1: return`——**该阈值是直接读已安装 pytest 源码确认的，不是推测**（正是 N-1 那类教训）。
      顶层登记表 42 → **44** 条、`registry_repairs` 第 **5** 条（`total_bytes` **不写进正文**：本轮它就变过两次，详见反思日志 2026-10-28 06:44 条 §八）；
      `.gitignore:54` 的 `!/outputs/evidence/**/*.log` 使该 `.log` 可入库（`git ls-files --others --exclude-standard` 已列出两个新文件）。
- [x] **四向登记表核对**（`out/scratch/sweep_registry.py`，新增第 4 向"**是否入库**"）：44 条记录
      存在 **0** 缺、sha256 **0** 不符、bytes **0** 不符、`sum(record.bytes)` == `total_bytes` **OK**；
      "未入库"精确报出 **2** 条，即本轮刚生成尚未 `git add` 的那两个文件 ⇒ 第 4 向确有牙齿。
      顺带纠正上轮扫描的口径缺陷：F01 目录级登记表的 `target` 存的是**绝对 Windows 路径**，
      与 `git ls-files` 的仓库相对路径直接比会假报"未入库"，故 `norm()` 先剥 cwd 前缀再比。
- [~] **F02 正式 200 rep**：**11:10 时 116/200**（shard0/1 已于 10:00/10:02 完成 rep 0–99；shard2 完成 rep 100–107、rep 108 在跑；shard3 完成 rep 150–157、rep 158 在跑），
      **两条 lane 都有独立内存看护**：lane 1 ALARM 0、lane 2 看护于 10:54:45 启动（PID 67048/65688，日志 `out/logs/f02_memwatch_lane2_20261028_1055.log`），
      前三行 `free` 3 334 / 2 166 / 4 247 MB、两 lane 峰值 **2 436 / 2 207 MB**、`low_streak=0`、`reps_done=114`。
      两 lane 当前 **426.3 / 414.7 s/rep**（7 rep 累计 2 984.2 s、6 rep 累计 2 488.1 s），合并 **~208 s/rep**，剩 **86 rep** ⇒ 约 5.0 h ⇒ **投影 ~15:55 集齐**。
      更早的 ~17:00 投影按 lane 1 的 474.7 / 470.1 s/rep 给出，现提前约 65 分钟。
      D01 最早起跑 **~16:05**（F02 收尾合并 + 证据导出之后，92 分钟独占）。
- [x] **F02 等待期预演聚合器**（`out/scratch/f02_aggregate.py`，`--allow-incomplete` 在 114 rep 上跑通；**仅预演、不得引用为正式结果**）：
      逐 rep 校验 6 类结构不变量（truth 列必须缺席、claims/arms/guardrail 唯一、`passes_*` 与 `holm p ≤ alpha` 一致、decision 与 itt 逐值一致、三臂 `n_assigned` 合计唯一、`selected_policy` 唯一），
      **当场拦下两个我自己的错误假设**：① `itt_contrasts.csv` 有第三行 `random_same_budget_minus_no_coupon`（我原先要求集合相等）；② 定向与随机臂的真实支出**本就不等**——预算口径是"每人 0.2 元**期望**成本 × 各臂人数"，真实支出比 `mean 1.0608 / min 0.9458 / max 1.2914`、`>1.0` **103/114**、`>1.25` **3/114**（3 个全在 `constant`，该层均值 **1.2567**，与 F01 的 +28.42% 水平标定偏差同源）；随机臂 `>1.0` 61/114、`>1.25` 0/114。
      预演分层（**114 rep**）：`worth_issuing` 111/114、`better_than_random` **108/114**、护栏 114/114、三项同时 **108/114**；
      按 `selected_model`：`causal_forest` 64/64、`s_learner` 38/39、`dr_learner` 5/5、`t_learner` 1/1、**`constant` 0/5**。
      6 个 `better_than_random` 失败**指名**：rep 0/27/87/89/100（全为 constant，Holm p 0.5980/0.2688/0.3535/0.3737/0.1006）+ rep 50（s_learner，p=0.0675，差 0.0836 元/人，只是没过 0.05）；
      3 个 `worth_issuing` 失败也全在 constant ⇒ AGENTS §12.6：正式正文必须按模型分层报，不得只报合并 108/114。
      另记：**rep 0 正是代表五表 rep**，其 `better_than_random` 判 null（p=0.598）——与 F01 单 rep 的"不得声称定向优于随机"结论同向，正式正文不得用 rep 0 单独支撑定向有效。
- [x] **推送已恢复**：连续 **7** 次失败（`Recv failure: Connection was reset` / 443 超时）之后，
      本轮提交 `a9249d7` 的第 8 次尝试**成功**（`1da7780..a9249d7`，exit=0，**2026-10-28 06:46**），分支与 origin 齐平。
      全程**未装无人值守重试循环**（push 是网络可见动作，只在确有提交要推时人工试一次）。
      **推上后仍等用户 review，不自行合并。**

**2026-10-28 06:10 本轮（E 三环闭合 + F01 复审落地 + 一次登记表全仓扫描）**：
- [x] **E01/E02 改判"通过"**：第三环窄口径确认 05:53 PASS。GOAL.md（L3/L7/E01/E02/R01）、
      `docs/v3_phase_E_evidence.md`、`docs/v3_phase_E_coverage.md`、AGENT_HANDOFF.md 四处同步。
- [x] **F01 复审 3 条新 P1 逐项本机复算，全部为真，06:05 修完**（`docs/v3_phase_F01_ope.md`）：
      **N-1** 超预算机制不是"预测成本为 0 的人"——`cost_hat` 最小 **0.048402**、`≤0` 人数 **0**、
      `<0.01` **0**、`<0.1` **15**，`v3_f01.py:193-194` 与 `v3_policy_grid.py:70-71` 两处硬性 `raise`
      本就禁止；真实机制是**水平标定偏差**：`corr(cost_hat,cost_true)=0.081482`，
      入选 23 437 人 `cost_hat` 均值 0.511990 < 全体 0.819836，其 `cost_true` 人均 **0.657507** <
      全体 **0.842833**（贪心确实挑到更便宜的人），但真值比预测高 **28.42%**
      （0.657507/0.511990=1.28422）⇒ 真实支出 15 410 vs 预测 11 999.51。
      顺带独立重建了贪心名单：按 `cost_hat` 升序 + `user_id` 断平取到预算，得 **23 437 人，
      与 `policy_meta` 逐位相同**。
      **N-2** `observed.csv.gz` 实测只有 6 列（无 `mu1/mu0/IF`）⇒ DR 主口径不可从证据包重建，
      line 10 声明已收窄；补落盘 nuance 帧（约 1 MB gz）列入 F02 合并后待办。
      **N-3** 跨档合并 OLS（1 400 行 = 7 非退化档 × 200 种子）：截距 −0.000740668、
      斜率 **0.332073451**（se 0.001013720、t 327.579）、**r² 0.987140**、
      x∈[0.035333,0.827000] 含定向臂 x=0.256833（插值非外推）⇒ 等实际支出随机 **0.084547**
      vs 定向 0.085638，优势 **+0.001091**；交叉核对 0.084528（档均值）/ 0.084153（相邻档）。
      ⇒ +0.031873 的 **96.58%** 来自"多花 30.9% 的钱"（15 410/11 770=1.309261）。已同步进 §0 摘要第 6 条。
- [x] **F01 的 9 条 P2 待修（06:28–06:32 已修完；10:52 随第四环条件落地改判"通过"）**（§4.5 中位数分母是 14 不是 16、DR 全档 `n_at_least` 未报（0.40 档 89/200）、`372a1bcc` 标注错位、正文钉死会变的登记表计数、缺 pytest 汇总行、
      §3 混列 freeze/meta 字段、`predicted_value ≡ 0.29380318 × n` 未注明）；
      修完再走 F01 的窄口径确认（第四环）。
- [x] **登记表全仓扫描（06:00）**：6 份 coverage.json、**97 个登记目标**，sha256/bytes
      **0 不符、0 缺失**；发现并入库 **4 个被 `.gitignore` 的 `*.log` 吞掉的 D03 分片日志**
      （`outputs/evidence/d03_formal/shard{0,1,2,3}_run.log`，共 14 403 B；登记表里的 sha256
      一直是对的，文件却从没进过仓库）。扫描口径同时查"存在 / 哈希 / 字节 / **是否入库**"，
      唯一在 `outputs/` 之外的目标是 F01 的 `policy_masks_long.csv.gz`
      （该登记表 `excluded` 已写明可重建理由与哈希）。
- [x] **F02 进度 06:05：35/200**（shard0 18 rep、shard1 17 rep；shard2/3 待链式起跑），
      内存 ALARM **0** 次。每 lane 实测 **470.9 s/rep**（shard0 累计 8 476.9 s / 18）与
      **471.7 s/rep**（shard1 8 018.2 s / 17）⇒ 整体 3.93 min/rep，剩 165 rep ⇒ 约 10.8 h
      ⇒ **投影 ~16:53 集齐**（比 05:27 的 n=25 投影 ~18:04 提前 71 分钟；仍按承诺在 n=100 复推）。
      D01 最早起跑 ~17:05。
- [x] ~~**推送仍失败**：连续 6 次 443 超时，本地 `[ahead 4]`~~ ⇒ **已解除**：见上方 **06:37 本轮**的推送条目（第 8 次尝试于 **06:46** 成功，`1da7780..a9249d7`），分支与 origin 齐平。

**（以下为 2026-10-27 18:44 的历史快照，保留原文不改写）A/B/C/D02 通过。D03 正式 R 已完成（200/200，12:54–17:14，stderr 全空），合并与证据导出通过（1 000 行 per-rep / 72 000 行网格，`coverage.json` 10 文件）；**D03 仍标未证实，待独立评审**。F02 决策层（单侧 Holm + 退款率护栏）已完成、11 项测试绿；全量串行 1 228 项两次 exit=0（18:12–18:20 决策层改动前、18:24–18:31 改动后）；**F02 n=200k 单 rep 已跑通（18:32–18:39，exit=0）**，证据在 `outputs/evidence/f02_n200k_rep0/`；新发现预算只约束预测成本、定向臂实际支出 +29.1%，裁决为保留规则并逐 rep 报告（见 F02 预算裁决项）。**

**D02 通过**，闭环为：独立评审 PASS WITH CONDITIONS → 3 项文档 P0 修正（4×MDE→4.93×、34%→0.729、相对差 2.3%→7.84% 并改归因为层水平偏移）+ P0-1/E-1~E-3 修复 → **独立复核 PASS**（`docs/reviews/v3_phase_D_recheck.md`）→ 复核抓出的 2 处再修。详见 `docs/v3_phase_D_aa_formal.md` §8。证据包在 `outputs/evidence/`（1.79 MB，仅凭它可重建 FPR 46/1000 与 CP [0.0339,0.0609]）。

**D 层三项已全部通过**（D03 于 2026-10-28 05:15 关闭、D01 于 21:38 关闭，见下）：
- **D03 通过（2026-10-28 05:15 独立复审 PASS，`docs/reviews/v3_phase_D03_rereview.md`）**：走完"评审判定（10-27 20:53 PASS WITH CONDITIONS）→ 主负责修复（P0-1 + P1-1~P1-6，21:02）→ 独立复核 PASS"三环，另有复审新提的 4 项 P2 已核实修正（`docs/v3_phase_D03_formal.md` §11.2）。程序豁免经用户 01:10 批准。**以下为关闭前的历史描述，保留原文不改写**：D.3 有完整实现与设计文档；逐用户 9 列导出已实现并跑通（n=20 000、单 rep、test 6 000 人），CSV 已喂 E 生成 72 行。**20 rep 诊断**（n=20 000，L1_main）：5 个模型都当过第一名（constant 9/20、causal_forest 4/20、dr/s 各 3/20、t 1/20）；除 causal_forest 外个体校准斜率中位数 0.02–0.18；冻结选模规则在 0.20 预算比同 rep 事后最优少 0.101 元/人——**这是诊断、不是正式 R**；正式 R = 200 rep × n=200 000（12:54–17:14）才是通过的证据。
- **D01 通过（2026-10-28 21:38，第三轮独立复核 PASS，`docs/reviews/v3_phase_D01_closeout.md`）**：20pilot 三粒度实测与资源计划。用户 01:10 批准，16:51:36–18:20:43 单进程跑完 20 rep，L0/L3 补测 18:48–18:57；证据包 `outputs/evidence/d01_pilot/`（10 件 25,733 B）与顶层 76 条登记经两轮评审 + 主控复算全 MATCH。含义仅"记录准确、断言范围正确（20 rep / 单机 / L1_main / 三粒度）"。**以下为关闭前的历史排期描述，保留原文**：须等 F02 集齐合并后独占机器跑（10:57 复推最早 ~16:05，约 92 min；F02 按 114/200 与 426.3/414.7 s/rep 复推 ~15:55 集齐）。

**E 的进度**：组件层已完成（成本模型 / 5 个求解器 / 预算三口径 / 误差分解 / 排序组件，41 项测试绿）；编排层已抽成可复用模块 `v3_policy_grid.py` 并跑通三次（`scripts/21_e_policy_run.py`，9 策略 × 8 预算 = 72 行）：合成数据、真实 D.3 provisional 预测、**20 rep × 5 模型配对网格（7 200 行）**。关键现象：受约束策略按 `cost_hat` 全部 160/160 合规，但 greedy 按 `cost_true` 在 0.04 档只有 0–2/20 rep 全合规（实际支出 1.82–3.59 倍预算）——期望成本口径不等于硬上限。**没有一次是正式 R，不能下策略结论。**
**E 证据层（13:05 新增，13:51 审计修复）**：`v3_policy_evidence.py` + `scripts/24_e_evidence.py` 已实现成本校准、小池 5 求解器互证、桶宽收敛、200 种子随机基线、误差分解、规模扫描、三预算口径共 7 张表；10 项新测试绿，策略全套 54 项绿。n=900 冒烟跑通（2.8 秒），产物隔离在 `out/e_evidence_smoke/`，meta 记录实际使用的池/桶宽/种子；正式数据待 D03 R 结束后用 `--from-d03` 跑。**冒烟数字不是证据。** 独立审计修掉 4 个高危：LP 上界在“容差内超支后剩余预算变负”时会低于真实最优；MILP 无解向量时可能被标 `optimal`；`width=0.01` 的桶权重未走分币 half-up；真值 MILP 的界被误当成 raw 问题的界（已改名 `truth_milp_*` 并标注 `truth_cost_floored_at_cost_floor_cny`）。另加随机/保守种子 ≥2、求解器 `error` 状态硬门禁、网格按 `user_id` 排序与唯一性校验、严格 JSON/相对路径。

**三个值得记住的观察**：
- `local_swap` 在 0.60 预算的真值比 greedy 低 0.00008（合成数据）；20 rep × 5 模型网格里也有 26/800 格为负、最大绝对差 0.0052——它保证的是**预测目标**不降，**真值可以降**。
- 选模不是"报告一个获胜模型"那么简单：20 rep 里 5 个模型都当过第一，冻结规则选中的模型在 0.20 档比同 rep 事后最优少 0.101 元/人（事后上界）。
- `purchase_propensity_rank` 在 0.04 档真实价值 −0.0023（低于不发券）——按购买倾向选人是反向选择，propensity ≠ uplift。

| 阶段 | 状态 | 进入/退出门槛 |
|---|---|---|
| A 协议冻结 | [x] | 配置/矩阵校验，独立业务复审通过 |
| B 机制真值 | [x] | A通过后实施，独立科学评审 |
| C 五表SQL隔离 | [x] | 101作业/6977检查、四库与CLI补验，独立工程评审通过 |
| D 检测估计 | [x] | **D01、D02、D03 全通过**（D02 复核 PASS；D03 2026-10-28 05:15 独立复审 PASS；D01 21:38 第三轮复核 PASS，20 rep × 3 粒度已完成） |
| E 策略优化 | [ ] | D通过，科学+业务评审 |
| F 观测闭环 | [~] | E通过，科学评审。**F01 单 rep 历史留出 OPE 已落盘并与 E 同源重跑（R=0，`freeze_id=b8402f30…`，10-28 10:52 起为通过，含义仅"记录准确"）；F02 机制/决策层就绪，n=200k 单 rep 已跑通（工程）；F02 正式 200 rep 在跑（10:57 时 114/200；两 lane 均有内存看护）** |
| G 正式重复 | [ ] | F通过，逐格R和工程评审 |
| H 图与长稿 | [ ] | G通过，三视角评审 |
| Z 最终审计清理 | [ ] | H通过，全项复核、单独清理提交 |

## A 工作清单

- [x] 阅读更新HITL、交接、纲领口径、工程规范与复盘。
- [x] 建立codex/v3-rebuild，保留master/v2.0。
- [x] 写协议草案，重建GOAL/TODO和决策反思日志。
- [x] 基线核查：原pytest25权限错误；隔离目录404通过；数字门禁1个版本文字问题；图门禁7图零错误。
- [x] humanizer全局安装与完整备份，逐hash/官方格式复核，见安装记录。
- [x] configs/v3全矩阵与参数依据（独立作者），73场景+20功效格。
- [x] 配置加载、矩阵导出、覆盖核验、源文件hash冻结，418项测试通过。
- [x] 独立电商业务专家评审、11项累计修复和复审通过。
- [x] A阶段汇报、交接/状态更新，里程碑提交以Git日志为准。

## D 阶段独立科学评审结论（2026-10-25 13:40 北京时间）

**实现层通过（D.1/D.2/D.3），D02 证据层不通过。** 评审独立复算 704 行 MDE（最大差 2.47e-11）、
AA 标签翻转端到端反例、206 项测试，未发现公式错误或泄漏；但指出八项必须补的证据/标注。

| 条件 | 内容 | 状态 |
|---|---|---|
| C1 | 正式 AA 按注册 n=200k + 授权 R 实跑；GOAL/G01/YAML 与 overlay 对齐；R=50/n=1万 只能叫 pilot | GOAL 已改；4 层 ×250 次正在跑 |
| C2 | 补 `any_refund_30d` 非劣效 MDE/功效（margin=0.005、单侧 0.05、80/90%） | 子代理进行中 |
| C3 | 补 20 功效格 `achieved_effect/rejection_rate/MC_SE`，实现 local-power 入口 | 子代理进行中 |
| C4 | σ 抽样 SE 由 0.32% 改为 ~1.0–1.6%（按峰度），`mde100` 真实功效约 0.79 | 子代理进行中 |
| C5 | CSV 编码 `mde100` 边界属性与单侧 α 标注（机器可读，不能只在散文） | 子代理进行中 |
| C6 | AA 报告补 SE 校准（合并经验 SD/平均 SE=1.020）与本 R 的实际功效 | 待补 |
| C7 | DR 补设计概率敏感性（`known_design_ipw`）、`propensity.primary` 关系、raw 诊断落地 | 待派 |
| C8 | 小修：行号 184→185；CF ConfigError 只覆盖 5 个超参；`<1e-9` 是自同义反复 | 子代理进行中 |

**评审确认的三处做得好**：AA 虚拟标签的机制惰性（翻转试验逐位验证）、方差来源隔离与逐位复现、
三道泄漏闸 + 五模型共享数据 + 真正折外 AIPW。

**主控误读已更正**：GOAL G01 的「AA1000」是每层 1000，不是总数 1000；已在 GOAL 正文标注修订与代价。

## D02 收口（2026-10-27 09:45）

- [x] 15 格 ×100 次 = **1500 次**功效实测（`outputs/tables/v3_phase_D_local_power_formal.csv`，15×62）
- [x] 独立评审（科学 + 工程）**PASS WITH CONDITIONS**：核心数字逐位复现，但 4 个 P0 + 4 个 E 项
- [x] 3 项文档 P0 修正：4×MDE→**4.93×**、34%→**0.729**、相对差 2.3%→**7.84%** 并改归因为**层水平偏移**
- [x] P0-1：MDE 表 448 行 σ 按 √p(1−p) 定点修正（与公式偏差 0.00e+00，`mde` 零改动）
- [x] E-1：证据导出 `outputs/evidence/`（1.79 MB，可独立重建 FPR 46/1000）；E-2：清理脚本前缀保护；E-3：17/19 校验加固
- [x] **独立复核 PASS**（`docs/reviews/v3_phase_D_recheck.md`）
- [x] 复核抓出的 2 处再修：§6 残留"≈4 倍"、负对照剔除混入的 1 行 `true_aa`（重建 8/100）
- [x] **D03 正式模型跑 + 逐用户 τ̂ 导出**（E 的硬前置，已交付）：正式 R = 200 rep × n=200 000，12:54–17:14 跑完；**2026-10-28 05:15 独立复审 PASS，D03 关闭**。此前的 20 rep 诊断（2026-10-27 12:00）只作诊断口径保留
- [~] D01 20pilot 三粒度实测与资源计划（用户 2026-10-28 01:10 已批准 20 rep；G1 纯估计 / G2 五表+SQL / G3 含 CF，约 276 s/rep ⇒ **单进程串行约 92 min**，**须独占机器跑**，否则墙钟失真）
  - [x] 3 rep 试点已完成：`docs/v3_phase_D_pilot.md`，单 rep ≈ 276 s、峰值 1.88–2.47 GB
  - [x] **04:05 核验入口与产物路径（读源码，未跑）**：`scripts/13_v3_pilot.py` 只有 4 个参数（`--scenario` 默认 L1_main、`--n` 默认 200 000、`--reps` 默认 1、`--start-rep` 默认 0），**没有粒度参数**（三粒度是 `run_rep` 内部一次跑完的）；输出固定为 `out/v3_phase_d/pilot_raw_{scenario}_n{n}.csv`（`:307`），且**每 rep 增量落盘**（`:327`），中断不丢已完成 rep；`out/v3_phase_d/` 当前**不存在**，所以既不会覆盖 R=3 的原始表，入库的 `outputs/tables/v3_phase_D_pilot_raw.csv`（2 322 B，09:57）也不在脚本的写入路径上。跑完后再**另存**为 `outputs/tables/v3_phase_D_pilot_raw_r20.csv` 入库，不动旧表
  - [x] **否决 §10 的"3 进程 × 7 批 ≈ 32 分钟"并行方案（04:05）**：与本项"须独占机器跑"直接冲突——pilot 的用途是**资源外推**，R=3 基线（276 s/rep、峰值 1.88–2.47 GB）是独占测的，3 进程并发会让墙钟被竞争抬高、与基线不可比；且 3 × 2.47 GB ≈ 7.4 GB 峰值，F02 双分片已占约 4.8 GB，物理上也不成立。**改为单进程串行 20 rep，接受 92 min**（§10 的算术保留为"若只看 CPU 总量"的参考，不得用于墙钟口径）
  - [ ] **正式 20 rep 未跑**：批准已取得（01:10），但**必须等 F02 200 rep 集齐并合并之后独占机器再跑**（F02 按 04:26 实测投影 **15:30–17:45** 集齐、点估计 ~16:30，合并约 5 min，故 D01 最早 **~18:00** 起；若落到原 11–15 h 区间上界则 19:00 之后。D01 本身约 92 min）；命令 `.\.venv\Scripts\python.exe scripts\13_v3_pilot.py --scenario L1_main --n 200000 --reps 20 --start-rep 0`；另按 §8.4 补 L0/L3 各 1 rep

## D03 逐用户导出（2026-10-27 11:30，北京时间）

- [x] `export_d03_predictions()`：固定 9 列 CSV（E 契约），`status=provisional`
- [x] 真值物理隔离：`_audit_truth_for_test()` 是唯一出口，选人 7 列冻结后才合并 `tau_true/cost_true`；有"毒化真值不改变选人列"的测试
- [x] n=20 000、L1_main、单 rep、5 模型全跑：选模 `causal_forest`（验证集 LCB 均值 −0.1159），test 6 000 人
- [x] CSV 喂 `scripts/21_e_policy_run.py --input` → **72 行 = 8 预算 × 9 策略**；受约束策略按 `cost_hat` 全部 8/8 合规
- [ ] **正式 R 未启动**：跑几次、选模指标（当前只用 `models.selection.scoring` 一条）、评估量清单三件事未裁决
- [ ] 注意：本次 provisional 的 `tau_hat` 均值 0.514 vs `tau_true` 均值 0.202（高估约 2.5 倍）；`greedy` 两策略按 `cost_true` 只有 3/8 预算合规（期望成本口径，不是硬上限）。这两条只作 provisional 观察，不能写进结论

## D03 20 rep 诊断（2026-10-27 12:00，北京时间）

> 完整报告：`docs/v3_phase_D03_diagnostic.md`。**诊断，不是正式 R。**

- [x] 实现 `run_d03_diagnostic()`：20 rep × 5 模型；选模仍只用验证集 LCB，真值在选模后合并，五个候选全部评估
- [x] 策略网格改为**按模型配对**（同一 rep、同一批用户，5 个模型各跑 9 × 8）：首版只跑选中模型，会把模型差异误当策略差异
- [x] 产物：`outputs/tables/v3_phase_D03_diagnostic_{per_rep.csv, policy_grid.csv, summary.json}`（100 / 7 200 行 / 118 KB）；运行 8 分 43 秒
- [x] 选模稳定性：constant 9/20、causal_forest 4/20、dr 3/20、s 3/20、t 1/20；第一名与第二名分差中位数 0.0532，最小 0.0014
- [x] 个体校准：斜率中位数 t 0.042 / s 0.179 / causal_forest 0.689 / dr 0.018；Pearson 中位数 0.019–0.084；constant 无定义
- [x] 策略层（0.20 档，20 rep 配对）：business − greedy 为 constant +0.153、t +0.119、dr +0.137、s +0.059、causal_forest −0.002（10/20 rep greedy 胜）
- [x] 选模后悔值（0.20 档）：chosen − 同 rep 最优 = **−0.1007** 元/人；只有 38/160 格选到最优（事后上界）
- [x] 双口径合规：按 `cost_hat` 全部 160/160；按 `cost_true` 在 0.04 档只有 0–2/20 rep 全合规，greedy 实际支出 1.82–3.59 倍预算
- [x] **正式 R 裁决**：3 rep × n=200 000 试点已完成（12:49，≈276 秒/rep）；正式 R = 200 rep（`tier1_full_learning_per_model: 200`），4 分片 × 50，预计 ≈3.9 小时
- [ ] 若正式规模下选模仍频繁切换，走协议评审提出修订；不得在汇总里偷换成"固定 causal_forest"或"事后最优"

## D03 正式 R（2026-10-27 12:52 启动）

> 试点报告：`docs/v3_phase_D03_pilot_n200k.md`。~~**正式 R 完成并复核前，D03 仍标未证实。**~~
> **（2026-10-28 05:25 追注）正式 R 已完成（200/200）、独立评审 PASS WITH CONDITIONS 的 P0/P1 已修、
> 独立复审于 05:15 返回 PASS ⇒ D03 已关闭为"通过"。**本节以下条目为运行期记录，原文不改写。

- [x] 3 rep × n=200 000 试点（`out/d03_pilot/`，快照 `67d842ae…`）：墙钟 13 分 49 秒，≈276 秒/rep（5 模型 + 5 份 9×8 网格）
- [x] 试点关键值：选模 constant 1 / causal_forest 2；cf 校准斜率 0.79–0.84；0.20 档 business − greedy 在 cf 上 −0.0189 ± 0.0075、s 打平、constant/t/dr 仍 business 更好；greedy 实际支出 0.04 档 1.31 倍预算；local_swap 120 格中 4 格真值为负（最小 −0.00075）
- [x] 分片与可观测性：`--rep-start/--rep-stop/--formal-r`、逐 rep 耗时日志；分片只切 `rep_id`，随机流不变
- [x] 正式 R：200 rep × n=200 000 × 5 模型，L1_main；快照 `out/d03_formal_snapshot/`，4 个独立进程写 `out/d03_formal/shard{0..3}/`；**17:13–17:14 四分片各 50 rep 完成，12:54 启动、墙钟约 4 小时 20 分；run.err 全空；每分片 summary `status=formal_r`、reps=50**
- [x] 合并脚本 `scripts/25_merge_d03_formal.py`：写盘前校验 rep 覆盖/去重、5 模型×8 预算×9 策略、chosen 恰好覆盖一个模型、双口径合规标记与数值一致；用 3 rep 试点产物演练通过（15 / 1 080 行）
- [x] 合并门禁 7 项合成用例（`tests/test_v3_d03_merge.py`）：缺 rep / 重复 rep / 篡改合规标记 / chosen 计数错 / config_hash 不一致 / 非正式分片全拒
- [x] 报告聚合层 `src/causal_growth/evaluation/v3_d03_formal.py` + `scripts/26_d03_formal_tables.py`：选模频率、模型校准（all/chosen，含**最大绝对相对偏差**）、真值价值、**按 (rep, model, budget) 配对的策略差**、oracle 后悔、双口径合规；缺格/重复格/覆盖不足/网格 chosen 行不完整即抛错。12 项测试绿；用 3 rep 试点表端到端演练产出 7 张表（policy_value/paired_diff/compliance 各 360 行，oracle 320 行——**全发券参考不参与事后最优**，chosen 配对 144 行）
- [x] 证据导出 `scripts/27_export_d03_evidence.py`：导出 manifest、快照绑定（83 文件）、4 份分片 summary 与 run.log；校验 rep 并集恰为 0..199、config_hash 四分片一致、run.err 全空、合并表哈希与行数（1 000 / 72 000）后再写 `coverage.json`
- [x] 合并分片 → `outputs/tables/v3_phase_D03_formal_*`；跑 26 报告表与 27 导出证据（17:15；21:00 重导出后 15 文件 = 14 导出件 + `coverage.json`，`config_hash=e1aa4314…`）；校验 200 rep / 1 000 行 per-rep / 72 000 行网格 / 每 rep 恰一个 chosen 全过
- [x] 报告表 7 张 + meta：`selection/calibration/policy_value/paired_diff/paired_diff_chosen/oracle/compliance`
- [x] **写 `docs/v3_phase_D03_formal.md` 正文数字**（选模 105/71/12/7/5；校准斜率 CF 0.754、S 0.467、T 0.114、DR 0.098；greedy−business 按模型符号分裂；0.2 档真实支出合规率 CF 11%/S 13%/T 39%/DR 26.5%/constant 0%）；2026-10-27 19:25 落盘，文首明确 **D03 仍未证实，等待独立评审**
- [x] **独立评审（20:53）返回 PASS WITH CONDITIONS**：数字层全部复现（选模、校准、40 个配对差、合规、oracle、证据哈希、83/83 快照、合并行数、7 表重建），**无算术错误**；P0-1（"运行期间未改 src"为假，窗口内 3 次 live 提交）、P1-1～P1-6 已按评审修正（21:02），并修源码斜率 docstring 与诊断 §111
- [x] **评审修改后全量串行测试（21:04:16–21:11:28）**：1 248 项 `exit=0`，单进程、无并发写盘，432 秒；`--collect-only` 计数 1 248；日志 `out/logs/pytest_d03_final_2105.log`（`-q` 未打印 passed 汇总行，以 exit 码与收集数计）
- [x] **用户确认 D03 程序豁免（2026-10-28 01:10 批准）**：正式 R 用 12:53:57 快照执行（83/83 哈希 + `snapshot_vs_live` 证明 3 个 live 改动未进入），但违反 AGENTS §11.2"不得与开发写盘并行"的字面规定；主负责书面豁免 + 用户批准 ⇒ 无需重跑（原备选为重跑约 4.3 h）。豁免记录见 `docs/v3_phase_D03_formal.md` §11.1
- [x] **独立评审 → D03 判定：PASS WITH CONDITIONS（2026-10-27 20:53）→ 修复（21:02）→ 独立复审 PASS（2026-10-28 05:15）**，覆盖方法对照、选模频率、按模型配对网格、双口径合规；复审另提 4 项 P2（均为标签/分母问题，无算术错），已全部核实并当场修正

## E 证据层（2026-10-27 13:05，北京时间）

> 覆盖 `docs/v3_phase_E_coverage.md` §8 的编排层缺口；**代表 rep 的正式证据已产生**，
> ~~但 **E01/E02 仍标"未证实"**，等待独立评审。~~ **2026-10-28 06:10 更新：E01/E02 已改判"通过"**（三环闭合；第三环 `docs/reviews/v3_phase_E_recheck.md` 05:53 PASS）。

- [x] `src/causal_growth/policy/v3_policy_evidence.py`：成本校准（validation 处理组）/ 小池 20·100·500 的 5 求解器互证 + 浮点穷举参照 / 桶宽 5 档收敛 / 200 种子随机基线 / learning-optimization 误差分解 / 规模 1000·5000·full_test / 三预算口径
- [x] 真值隔离：所有 mask 先冻结，`tau_true/cost_true` 只进 `true_*` / `actual_*` 列；毒化测试覆盖 5 张表
- [x] 修复 `lp_upper_bound` 的免费券除零缺口（真值成本有大量 0；共享校验仍要求成本严格为正，故真值 MILP 先按 `cost_floor=1e-6` 抬高并单列 `truth_milp_cost_floor_cny`）
- [x] 10 项新测试（`tests/test_v3_policy_evidence.py`）+ 既有策略 54 项全绿
- [x] n=900 CSV 冒烟：7 张表 + 校准 JSON，2.7 秒；产物隔离 `out/e_evidence_smoke/`，已清掉误写进 `outputs/tables/` 的冒烟副本
- [x] **E 独立评审（21:24 落盘）**：`docs/reviews/v3_phase_E_review.md`，**PASS WITH CONDITIONS，0 P0 / 6 P1 / 9 P2**；E01/E02 仍“未证实”
  - [~] **P1-1**：`chosen=constant` 使 `tau_hat` 恒定（60 000 行 unique=1），24/24 求解器相等是必然结果；须用非退化价值向量重跑小池/规模表，入口断言 `nunique(tau_hat)>1`
  - [~] **P1-2**：真值 oracle 用 raw `cost_true`（0/10）而策略预算用 `cost_hat`，0.04/0.10 档学习误差被低估 0.25274/0.10526；须同口径重算并加 `truth_oracle_cost_basis`
  - [~] **P1-3**：E 无 `outputs/evidence/e_*`，meta 缺 `git_commit/source_sha256/cfg_hash`；帧与 `run.log` 只在 `out/`；`--from-d03` 重建而非读冻结 CSV
  - [~] **P1-4**：校准个体指标被 0/10 伯努利噪声主导，“不排序/欠离散 1/7”是误读；须改常数基准相对改进并改写正文
  - [~] **P1-5**：1.00 档“实际支出等于预算上限”与表矛盾（实际 50 570 vs 预算 60 000）
  - [~] **P1-6**：误差分解只跑 `chosen=constant`；须补第二个模型（CF/t）配对分解，或全面降级表述
  - > 以上 6 项由主负责自证已修（详见下方 2026-10-28 02:38 条目）；按 AGENTS §7.4，**只有独立复审通过才能记为关闭**，故标 `[~]` 不标 `[x]`
  - [~] **修复进展（2026-10-27 21:44）**：P1-1 入口断言 + `--frame-model causal_forest`（n=20k 冒烟 unique=5 978、sd=0.8974）；P1-2 同 `cost_hat` 口径真值 oracle（constant 帧 0.04/0.10/0.20 = 0.98436/0.99284/0.91780，恒等式残差 ≤3.5e-17）；P1-3 meta 增加 `git_commit/source_sha256/protocol_*`，新增 `--evidence-dir` 导出与顶层 coverage；P1-4 校准增加零模型/Brier/信号 sd 诊断；P2-1/P2-4/P2-8 补相对 gap、拆分 file/dataframe 哈希、每元价值列
  - [x] **全量 CF 重跑（2026-10-27 21:43:56–22:11:07，exit=0，1 360 秒）**：`--from-d03 --models causal_forest --frame-model causal_forest --n 200000 --tag cf`；chosen=CF，帧 60 000 行、`tau_hat` unique=59 861、sd=0.7816；8 产物 + 证据包 `outputs/evidence/e_evidence_rep0/`（11 条记录 6.08 MB：帧、校准逐用户、7 表、meta、coverage）。**该目录已于 2026-10-28 02:38 移至 `out/attic/e_evidence_rep0_stale/`**（守卫加入前的旧产物，其 11 条顶层 coverage 记录同步删除；6 个文件与 `_a`/`_b` 现行证据逐字节相同，另 5 个是过期版本，仅作历史留存）
  - [x] **CF 结果核验（2026-10-27 22:30）**：① 小池 24/24 分币精确 DP；局部交换最大低于精确解 0.3055 元（pool100@0.10），贪心最大低 0.3110 元；MILP“optimal”因解浮点问题可高于分币精确解最多 0.0809 元，**不能再说 24/24 求解器相等**；LP 上界行按设计整行 NaN；② 桶宽 1.00→0.05 元在 0.04 档把相对 gap 从 12.99% 降到 0.48%，0.01 档因可行性丢弃回升到 0.61%，曲线非单调；③ 校准 MAE/RMSE/Brier 相对常数基准仅改进 1.13%/0.22%/0.45%，Pearson 0.085（校准信号上限 0.109，占 78.5%）；④ **1.00 档随机基线实际支出 50 570 vs 预算 60 000，超支概率 0，P1-5 原表述确认错误**；⑤ 分解恒等式残差 ≤2.8e-17，`truth_oracle_cost_basis=cost_hat_primary`，`truth_feasible_under_cost_hat` 全 True；⑥ 60k 规模扫描 MILP 0.21 秒“optimal”且与贪心同集，需在正文说明这是该帧成本高度离散导致的退化
- [x] **E 正文改写（P1-1~P1-6 + P2）已完成（`docs/v3_phase_E_evidence.md` 维护时间 2026-10-28 02:46）**：正文现为 **A/B 双家族**结构（A=`constant` 主口径、与 D03 正式选模一致；B=`causal_forest` 非退化敏感性），§1 明确 A 的"逐格完全相等"是**任务退化到无法区分算法**、不是求解器一致性的胜利。与评审 P1-6 的"2×8 表"要求的差别：不是只留 CF 帧，而是**两家族并列**——A 保留是因为它是 D03 的选模结果，删掉它会切断与 D03 正式 R 的口径连续性
- [~] **E 修复后复审**：P1 全修并重跑/重写后再次独立评审，才可把 E01/E02 转“已证实”。**独立复审已于 2026-10-28 05:13 启动**（后台代理，产出 `docs/reviews/v3_phase_E_rereview.md`），任务书要求逐条核 6 项 P1、复算小池求解器是否真的分离、按 §12.5 报最差相对差、并按 §12.6 验 A/B 是否构成同 rep/同用户/同池/同预算的有效配对
- [x] `--from-d03` 正式路径小规模验证（14:01，n=2 000、rep=0、600 行 test）：8 个产物 61.1 秒，校准走 validation 处理组 201/400，分解表 `truth_milp_status=optimal`、`truth_milp_cost_basis=truth_cost_floored_at_cost_floor_cny`；产物隔离 `out/e_evidence_fromd03_smoke/`
- [x] **正式数据**：2026-10-27 19:17:51–19:42:28 用 `--from-d03 --rep-id 0 --n 200000` 跑完（D03 正式 rep 0，`chosen=constant`），9 个产物齐：7 张表 + `v3_phase_E_calibration.json` + `v3_phase_E_evidence_meta.json`；帧 60 000 行、sha256 `c8fd698e…c54e0`；阶段耗时 87.7/1.2/42.3/1.0/117.9/967.3 秒。**规模扫描 60k 有 7 档 `time_limit_no_incumbent`（NaN，非 0）**
- [x] E 正文报告 `docs/v3_phase_E_evidence.md`：2026-10-27 19:45 落盘（§2 校准、§7 规模扫描已补实数），明确"桶宽阈值由曲线定、不预设"；observed_value 留给 F01；**文首仍标"尚未独立评审、E01/E02 未证实"**
- [x] 小池表 `time_limit_no_incumbent` 契约补强（2026-10-27 19:45）：原先空 mask 会写 0 花费/0 价值，现整行 NaN；新增 `test_small_pool_no_incumbent_rows_are_nan_not_zero`，策略两文件 57 项绿（`--basetemp C:/cg_t`）；全量单进程串行 1 238 项 exit=0（19:46:59–19:53:48，日志 `out/pytest_full_20261027_1947.log`）
- [x] **A/B 两家族按当前源码重跑（2026-10-28 01:12 / 01:35，各单进程，exit=0）**：A=`constant`（D03 选模，01:12:03–01:35:23，1 149 秒，`--skip-small-pool` 因退化守卫）、B=`causal_forest`（01:35:26–02:04:28，1 742 秒）；两家族 `git_commit=e0048100233b4c6df5cef1931eda0c2704e63815`、`source_sha256` 逐值相同 ⇒ **AGENTS §12.6 的"跨源码版本配对"缺陷已消除**；证据 `outputs/evidence/e_evidence_rep0_{a,b}/`（各 11 条记录），日志 `out/logs/e_r2_{A,B}_20261028_0112.log`
  - [x] **数值零漂移复核（NaN 感知、忽略 `seconds` 列）**：A 与 `out/scratch/e_A_preguard_1917` 只差 4 个新增列（`relative_gap_to_exact`/`mean_value_per_actual_spend`/`true_value_per_actual_spend`/`true_value_per_actual_spend_mean`）+ 7 行 `relative_gap` 由 1.0 改 NaN；B 与 `out/scratch/e_backup_0100` 只差同样 7 行 NaN，`random_long_cf` 零差异、`calibration_cf.json` 逐字节相同；`calibration.json` 新增 23 键、**改动 0 键** ⇒ 正文已引用的每个 A/B 数字继续成立
  - [x] **正文复核发现并更正 4 处文档缺陷**：① §3.4 把规模表的统计量（17 行 incumbent 有限、−4.366e-11）写进了小池小节，小池实况是 24/24 有限、`bound_cny − incumbent_cny` 最小值恰为 0.0、最大 9.660891e-02；② §3.4 把 MILP 行的 `bound_cny`（`v3_policy.py:517` 的 `-mip_dual_bound`，**MILP 对偶界**）当成 LP 松弛界，两种上界已列表分开，并补出 LP 口径的负值行数是 **A 1 行 / B 4 行**（原写"各 1 行"），另补此前未写的事实：小池 `lp_relaxation.bound_cny` 相对分币 DP 有 3/24 格为负、最小 −1.421085e-14 元；③ §6 恒等式残差"5.551e-17"在任何一份留存表里都复现不出来，实况 A=3.469e-17 / B=8.327e-17，属转写错误；④ §7.1 举例"B 的 5 000 @0.30 gap=0.0000152"无此值，实况 1.4616250426002066e-05
  - [x] **新发现并写入正文**：B 的桶宽表有 **15 行负 gap**（恰为 0.60/0.80/1.00 三个非绑定预算 × 5 档桶宽，各 −0.000865 元 / −0.000395%），原因是"精确参照"只对**分币整数化**问题精确；A 无负 gap。桶宽阈值仍未预设
  - [x] **顶层证据登记表修复（2026-10-28 02:38）**：`outputs/evidence/coverage.json` 46 → **35 条**、`total_bytes` 22 788 510 → **15 811 356**，复算全条一致。两类根因：24 号脚本的顶层合并**只清理自身前缀**，`e_evidence_rep0/` 的 11 条旧记录长期滞留（已随目录移至 attic 一并删除）；31 号脚本**只写目录级 coverage.json**，F01 于 00:47/00:49 重新导出后顶层登记的 `freeze.json`（sha `e2c8e5cb…`→`19af2dbd…`、freeze_id `3ab44dcb…`→`bfb26807…`）与 `meta.json`（15 084→17 333 B）未跟随更新。修复动作已写进登记表 `registry_repairs` 字段
- [~] **登记的代码级缺口**：① E 的 meta 没有 `cfg.hash(64)`（=`e1aa4314b8d84b04a26150cb8ccea5a35dbe9b2d514fee724c56570d5b586d75`，只有 `protocol_config_hash`），须从 `outputs/evidence/d03_formal/shard*_summary.json` 交叉读取；补齐要改 `scripts/24_e_evidence.py` 并重跑约 50 分钟，与 F02 正式关键路径冲突，故留待 F02 之后。② ~~顶层登记表的刷新应由 31 号脚本负责~~ **已于 2026-10-28 03:13 修复**（`scripts/31_f01_ope.py:_refresh_top_registry` + 5 项篡改测试，详见 F 段）；24 号脚本因被 E 的 `source_sha256` 绑定，本轮刻意未改
- [x] **P1-1~P1-6 已由独立复审核实（2026-10-28 05:34）：4 已修 + 2 部分修 + 0 未修**，两处残留（N3 = P1-2 的正文表述、N2 = P1-3 的日志导出）已于 05:40–05:48 补齐；**E01/E02 仍"未证实"，待窄口径确认复审返回**：P1-1 非退化 B 家族 + 入口断言；P1-2 同 `cost_hat` 口径真值 oracle（残差 A 3.469e-17 / B 8.327e-17；复审复现学习误差与正文最大相对差 1.76e-16）；P1-3 meta 含 `git_commit/source_sha256/protocol_*` + `--evidence-dir` 导出（**复审抓到日志导出错源，已修**）；P1-4 校准含零模型/Brier/信号 sd（两版本各 40 键、**34 键逐值相同、6 个溯源/模型标签键不同**，05:40 复算更正原写的 39/1）；P1-5 1.00 档表述已按表更正；P1-6 A/B 双模型配对分解（A 学习误差 0.58674–0.99284、B 0.63156–0.80158；复审核实两家族 60 000 个 `user_id` 同序、除 `tau_hat` 外逐列字节相同）
- [!] **LP 每 rep 上界缺口**：`policy.optimization.every_full_rep_required` 要求 `lp_relaxation` 在每个 full rep 上都有，但 D03 的 200 rep 网格只有 9 个策略、没有 LP 行；E 证据层只在代表 rep 上补。**G 阶段必须每 rep 补 LP 上界**，否则"规模对照覆盖所有 rep"不成立

## F 观测闭环（2026-10-27 14:39，北京时间）

> F 只允许用观测表 `(T, Y, C, R)`；真值只作评估后的审计列，不得进入任何选择/拟合。

- [x] `src/causal_growth/evaluation/v3_ope.py`：交叉拟合 IPW（HT）/ SNIPS（两臂分别归一化）/ DR（AIPW）策略价值，影响函数 SE；配对差 `sd(IF_A−IF_B)/√n`（含协方差）；成本 DR（对照臂成本 0）；30 天退款率 DR 护栏；ESS/支持违规可靠性门禁；Holm step-down
- [x] 折划分复用：`crossfit_nuisance` 新增 `fold_id`，`crossfit_two_arm_outcome` 在同一折上拟合成本/退款模型，杜绝跨折泄漏
- [x] 真值隔离入口：观测表若含 `*_true` / `audit_*` / `truth_*` / `potential_*` 列直接拒收；`actual_action` 放行
- [x] 9 项测试（`tests/test_v3_ope.py`）：SNIPS 手算公式、单臂退化、n=4 000 恢复已知策略值、no_coupon 跳过处理臂门禁、ESS/支持拒收、配对差用协方差而非独立 SE、成本/护栏恢复、真值列拒收、Holm 阈值
- [x] **F02 独立验证机制**（16:00 更新）：`evaluation/v3_f02.py` 从 D03 选中模型冻结三臂（`no_coupon / random_same_budget / selected_targeted_policy`，1/3 各臂），**每个活跃臂按臂内分配人数 × 0.2 元冻结名单**（配置 `same_per_assigned_user_in_each_active_arm`）；新一批验证用户走五表+SQL 出观测，全臂 ITT 对照；**先落盘冻结策略名单与 per_user，再解封真值**；全队列交付名单只用于审计且按 `user_id` 对齐；**代表 rep（0）额外落盘完整五表与 SQL，manifest 绑定其路径与 sha256**；11 项测试绿，n=2 000 CLI 冒烟产出 11 个文件 + `five_tables/`
- [x] **F02 n=200 000 单 rep（18:39 完成，工程状态）**：三臂 66,594/66,713/66,693，无空臂；预测支出 13,318.53/13,342.56 均在 0.2×臂人数内；冻结先于审计，manifest 记录解锁顺序；两主张单侧 p=0.3690/0.2990、Holm 调整 p 均 0.5980、均不通过；护栏 0.958% vs 0.780%，差值 +0.1784pp、单侧上界 0.2620pp < 0.5pp，通过；per_user/decision/guardrail 哈希复核一致；证据 `outputs/evidence/f02_n200k_rep0/`（不含逐用户真值；manifest 仅含冻结后聚合审计真值）
- [x] **F02 预算口径裁决（18:46）**：保留预测成本口径。实际成本发券时不可知，按实际成本约束不可实现；三臂共用同一规则、分配随机，ITT 有效；实际券成本已进入净贡献利润。正式 200 rep 逐 rep 报告实际支出/超支倍数，"同预算"限定为"同预测预算规则"。单 rep 定向臂实际 17,200 vs 预测 13,318.53（+29.1%），随机臂 13,300 vs 13,342.56（−0.3%）
- [~] **F02 正式 200 rep（用户 2026-10-28 01:10 会话内批准；登记号 `F02-FORMAL-20261028-R200`）**：
      4 分片 × 50 rep，从 `out/f02_formal_snapshot/`（含 `scripts/`）运行、`--out-root` 用绝对路径，
      合并用主仓库 `scripts/30_merge_f02_formal.py --expected-reps 200`；聚合按 rep 配对报告通过率，
      不合并 p 值。启动前置：最终源码 n=20 000 双跑一致（见下"评审后源码复验"）+ `snapshot_binding.json`
      + `outputs/v3/f02_formal/approval.json`（记批准原文/时间/config 与 source 哈希/rep 范围）。
      **内存约束（01:19 实测）**：总 30.8 GB、可用仅 4.8 GB，4 分片并发不成立；先起 1 个分片测单 rep
      峰值 RSS 再决定并发（上限 2）。单进程约 7 min/rep ⇒ 200 rep ≈ 23 h，双分片 ≈ 11.6 h
  - [x] **正式前置：两次独立拟合一致性（20:37）**：n=20 000、rep 0 两个独立进程；`freeze.json` 七字段逐位一致（含 `freeze_hash/per_user_hash/decision_hash/guardrail_hash`），五表 manifest 仅时间戳不同
  - [x] **快照运行口径（20:38）**：写入 `docs/v3_phase_F02_validation.md` §5.5——必须连 `scripts/` 一起快照并从快照运行；只设 `PYTHONPATH` 会被脚本的 `sys.path.insert` 绕过
  - [x] **n=200 000 同口径双跑复核（20:52 完成）**：A 20:44、B 20:51:59 各完成一次；`freeze.json` 七字段逐位一致（freeze `5a101174…52cc` / per_user `a6c100e3…2901` / decision `368c1d89…ee42` / guardrail `f6b1bd3c…4d45`）；六个汇总表逐字节相同；`five_tables/` 27 文件中 26 个逐字节相同，仅 manifest 时间戳不同；manifest 仅代表五表路径与其 sha 不同
  - [x] **快照机制实测（20:48）**：`out/snap_test/` 复制 `src/sql/configs/scripts`，快照内脚本以 n=2 000、rep 0、`--status engineering` 跑通；manifest 48 个 `source_hashes` 与主仓库逐项相同（字典 sha256 `0605947…71bd`），路径字段均指向快照；**相对 `--out-root` 会落到快照根**，正式运行必须绝对路径。冒烟产物不作证据
  - [x] **合并门禁补强（21:18）**：库层 `selected_policy` 必填且跨 rep 唯一；脚本层校验分片 summary 的 `completed_rep_ids` 与 rep 目录一致，并把 `config_hash/source_hashes_sha256/formal_approval/policy/n_per_rep` 与 rep 清单聚合值比对；新增 `tests/test_v3_f02_merge.py` 5 项、formal 2 项，F02 26 项测试全绿
  - [x] **门禁补强后全量串行测试（21:19:21–21:27:19）**：1 248 项 `exit=0`，478 秒，单进程、无并发写盘；日志 `out/logs/pytest_f02_merge_2119.log`（加 `-p no:warnings`）
  - [x] **评审后源码复验（2026-10-28 03:35 完成）**：D03 评审已改 `v3_models.py` 的斜率 docstring（行为不变，但 `source_hashes` 已变）；E/F01 评审未再改源码。用最终源码（commit `7870b9a`）做 n=20 000 双跑 `out/f02_pre_final_A|_B`，两次 exit=0、各 49 s；`out/scratch/compare_f02_prerun.py` 把 `freeze.json` 展平成 7 个叶子键逐位比对（不一致 0），再对 rep0 的 38 个文件逐个字节比：36 个完全相同，2 个 manifest 只差登记字段——`five_tables/manifest.json` 差 `started_at_utc/finished_at_utc`，`manifest.json` 差 `representative_tables_manifest`（含 run 目录名的绝对路径）与其 sha256（已核验 = 各自 `five_tables/manifest.json` 的实算 sha256，A `830e35ea…` / B `0dd150ea…`），即差异全部由时间戳派生，结论"一致（可建快照）"
  - [x] **正式快照与登记（03:39）**：`bash out/scratch/f02_snapshot.sh` → `out/f02_formal_snapshot/`（118 文件，`src/sql/configs/scripts` 四目录，`robocopy /XD __pycache__`）；`out/scratch/f02_prep.py` 核验子进程确实从快照导入（断言 `m.__file__` 前缀 + 解析 root == 快照，避开 venv 的 `__editable__` .pth），`pipeline_source_hashes()` 主仓库 vs 快照 48 文件逐项一致（字典 sha256 `d8327ae0a190a5c2…`，与双跑 summary 同值），`protocol_config_hash=e1aa4314b8d84b04…`，`git_commit=7870b9a191c5`；写出 `snapshot_binding.json` 与 `outputs/v3/f02_formal/approval.json`（含批准原文与时间、口径、rep 范围、冻结裁决规则）。**踩坑**：`f02_prep.py` 首版把 `load_v3_protocol` 从 `causal_growth.config` 导入（凭印象写的），实际在 `causal_growth.v3_config`，ImportError 后才改对
  - [~] **分片执行（03:39 起）**：shard 0（rep 0–49）03:39:18 起、shard 1（rep 50–99）03:51:13 起，均 `--status formal --formal-approval F02-FORMAL-20261028-R200 --resume`、`--out-root` 绝对路径、从快照运行，日志 `out/logs/f02_formal_shard{0,1}_*.log`。**实测（10 min × 20 s，`out/logs/f02_rss_shard0.log`）**：rep 0 独占 366.4 s、选模 `constant`；单进程峰值 RSS **2 337 MB**、常态 1.4–1.9 GB，采样期系统可用最低 3 735 MB（总 30.8 GB、16 核）⇒ 双分片峰值合计约 4.8 GB、最坏可用约 1.7 GB，**只并 2 个分片**。看护 `out/scratch/mem_watch.py` → `out/logs/f02_memwatch_20261028_0351.log`（每分钟一行，可用 <1 024 MB 打 ALARM 并累计 low_streak）。shard2/shard3 由接力脚本自动起（见下）
  - [x] **并发降速实测与排期（04:01 首估、04:08 按模型构成修正）**：单 rep 耗时**由被选中的模型主导**——`constant` 366.4 s（独占）/ `s_learner` 394.9 s / `dr_learner` 402.0 s / `causal_forest` 478.5 s、512.1 s（后四个都是双分片并发时测的）。首估用两分片均值 437 s 得出"有效吞吐 218 s/rep ⇒ ≈12.1 h、~15:45 集齐"，**这是点估计、偏乐观**：按 03:51:13–04:04:30 窗口实测有效吞吐 266 s/rep 算是 14.8 h；按 D03 200 rep 的选模频率（constant 105 / causal_forest 71 / s 12 / dr 7 / t 5）加权 ≈420 s/rep/流算是 11.7 h。**改为区间：11–15 h，即 2026-10-28 15:00–19:00 之间集齐 200 rep，不承诺具体时刻**。三分片需 3 × 2.4 GB ≈ 7.2 GB 峰值 > 可用 4.2–5.3 GB，**不采纳**
  - [x] **无人值守接力（04:02 起）**：`out/scratch/f02_chain.sh 37612 21460` 每 5 min 用 `Get-Process` 判两个分片 PID 是否存活（**判活/判死都先单独验过**：37612/21460 判活、999999 判死），两者都退出后自动 `bash out/scratch/f02_shard.sh 2` 与 `3` 并 wait，日志 `out/logs/f02_formal_shard{2,3}_*.log`
  - [x] **自动收尾（04:04 起）**：`out/scratch/f02_finalize.sh` 每 5 min 数四个分片目录下 `rep*/freeze.json`（`count` 函数已用真目录验过：shard0=3 / shard1=2 / 未建目录=0），四者各满 50 后自动跑 `scripts/30_merge_f02_formal.py --shard-root ×4 --expected-reps 200 --tables-dir outputs/tables --evidence-dir outputs/evidence/f02_formal`，日志 `out/logs/f02_merge_*.log`，最长等 22 h 后放弃并留话
  - [x] **合并门禁"失败要响"实测（04:03）**：拿当前只有 4 个 rep 的状态跑一次合并，输出重定向到 `out/scratch/merge_gate_test/`（**不碰 `outputs/`**），如预期抛 `ValueError: rep 目录数 4 与 expected_reps=200 不符`（`v3_f02_formal.aggregate_f02:359`），临时目录零文件写入、`git status` 干净 ⇒ 自动收尾即使提前触发也只会留下一条失败记录，不会产出半成品聚合表
  - [x] **ETA 改为实测投影（04:26，n=10 rep）**：不再用假设的选模频率加权，直接用已完成 10 个 rep 的实测耗时——mean **460.8 s**、sd 64.8 s、min 366.4（constant）、max 524.2（causal_forest）；选中模型 6 causal_forest / 2 s_learner / 1 dr_learner / 1 constant。按 2 并发投影 200 rep = **12.80 h**，mean 的标准误 20.5 s ⇒ 95% 区间 **11.68–13.92 h**，自 03:45 起即 **15:30–17:45 集齐，点估计 ~16:30**（**05:22 更正**：起跑实为 **03:39:18**，凭据 `snapshot_binding.json` 的 `created_at=2026-10-28T03:39:04+08:00` 与日志名 `f02_formal_shard0_20261028_0339.log`；窗口应为 **15:20–17:35、点估计 ~16:27**，工期投影 12.80 h 本身未变。原值保留在此不改写，见 `docs/v3_phase_D03_formal.md` §11.2 P2-1。**05:29 再更正：15:20–17:35 这个窗口也已被观测否证**——05:27 时 `reps_done=25`、自 03:39:18 起 108.1 min ⇒ 实测 **4.32 min/rep**，外推 **~18:04 集齐**；每 rep 计算时间 518.6 s 已超出 n=10 均值 460.8 s 的 95% 区间 [420.6, 501.0]，即 **n=10 投影偏乐观且偏出其自身标准误**（但 108.1 min 含启动开销，该除法略高估稳态速率）。**教训：平移外推值时只改了锚点、没重算斜率**，与 §12.5 同病，详见决策日志 05:29 条。n=100 复推承诺不变；D01 最早起跑顺延至 **~18:15**）。原记的 11–15 h 区间仍成立、收窄为上值；区间下界 11.68 h 与 04:08 那次"D03 选模频率加权 ⇒ 11.7 h"几乎重合，两条独立路径互证。**注意**：n=10 的选模构成（causal_forest 60%）高于 D03 200 rep 的 35.5%（71/200），但按二项 sd 1.51 算只差 +1.6 sd，**不足以断言选模构成变了**；将在第一波 100 rep 完成时用 n=100 重推一次
  - [x] **顶层证据登记表的同类缺口修复（04:24，即下面 ① 的工具化）**：按 04:07 自记的规则"修机制缺口要 grep 同类脚本"，查出缺口比原记的更宽——`scripts/27_export_d03_evidence.py:255` 与 `scripts/30_merge_f02_formal.py:186` **都只写目录级 coverage.json**，于是 `outputs/evidence/d03_formal/`（含 D03 正式的 `snapshot_binding.json` + `run_manifest.json`）与 `outputs/evidence/f02_n200k_rep0/` 在顶层索引里 **0 条**，而 AA/C3 的 binding 却是登记在案的 ⇒ 评审者从顶层入口找不到 D03 正式的源码绑定，违反 AGENTS §12.1"只用 outputs/evidence/ 就能重建关键数字"。写了 `out/scratch/register_evidence_top.py`：按**可陈述规则**（身份类 JSON = `*binding*.json` / `*manifest*.json` / `freeze.json` / `meta*.json` / `decision.json`，不收 CSV/日志/逐 rep summary）提升，提升前对每个候选**重算 sha256/bytes 并与目录级记录比对**（不符即抛，不拿过期哈希登记），提升后对顶层**全表 41 条**逐条复算，结果 **35 → 41 条、`total_bytes` 15 811 358 → 15 858 444、既有 35 条逐条与顺序均未变（diff 99 增 / 2 删）**，幂等已实测（第二次运行不写盘）。附带白捡一道交叉核验：E 的两个 `meta`、F01 的 freeze/meta 顶层记录与其目录级 coverage.json **哈希逐值相符**。**踩坑两处**：① 目录级 schema 有三种（`files` 是 list / `files` 是 dict / `records` 是 list，且 f01 的 `target` 是**绝对 Windows 路径**），首版只吃两种，靠 `--dry-run` 当场炸出来；② 首版按 target 排序，把 32/35 条既有记录重排成 217/139 行的 diff，改为**只追加**才让 diff 纯增量、评审者能一眼确认其余记录未被动过
  - [x] **查出审计条目里的硬编码"前值"（04:23）**：`registry_repairs[1]`（03:06）的 `total_bytes_before=22 788 510` 与 `reason` 与 `registry_repairs[0]`（02:38）**逐字相同**，而 02:38 之后磁盘上的值已是 15 811 356 ⇒ 该"前值"是假的。根因定位到 `out/scratch/fix_evidence_registry.py:100` 把 `"total_bytes_before": 22788510` 写成常量、`:102` 把 reason 写成常量，脚本跑两次就在审计轨迹里留下一条假前值（`records_before` 用的是 `len(records)`，是真测的，所以只有这两个字段不可信）。处置：**不改写历史条目**（那是带时间戳的审计轨迹），把缺陷连同证据登记进 04:24 条目的 `prior_entry_defects`（记 `recorded_value` / `correct_value=15 811 356` / 佐证文件），并让新脚本的 before 值**一律现读现算 + 与逐条求和交叉校验**，不符就拒绝写盘。新规则：**审计产物里的任何 `*_before` 字段必须是实测，不能是常量；一次性修复脚本一旦被重跑，硬编码的前值就变成假证据**
  - [ ] **合并后待做（不可自动化的部分）**：① 把 **F02 正式证据**登记进顶层 `outputs/evidence/coverage.json`——工具已就绪且**已按 30 号脚本的真实输出形状演练过**（见下条），合并后 `.venv/Scripts/python.exe out/scratch/register_evidence_top.py --dirs f02_formal --dry-run` 再实跑；`scripts/30_merge_f02_formal.py:186` 本身仍**不刷顶层索引**，与 27 号脚本同缺口 ② `snapshot_binding.json` 已复制入库（`outputs/v3/f02_formal/`，sha `2988d069…`、6 920 B）③ 写 `docs/v3_phase_F02_formal.md` 正文与 §11.2 程序豁免记录（**11:00 已起稿骨架**：§1–3 协议/绑定、§5–9 边界/复现/检查单，137 行；§4 与 §1 结果行共 7 处 `待填`，合并后替换——草稿正文已写明"不得引用为结果"） ④ 全量串行测试复跑 ⑤ 改完顶层索引后同步 3 处引用（`docs/v3_phase_E_evidence.md:675`、`docs/v3_phase_F01_ope.md:437/468`、本文件 P0-3 条）——**历史记录保留原值、只改现状断言**（04:24 已按此改过一轮）⑥ **机制修复**：让 27/30 号脚本自带顶层刷新（复用 31 号 `_refresh_top_registry` 口径），并把 30 号 evidence `coverage.json` 的记录键从 `{path, source, sha256, bytes}` 补上 `kind`/`target`，同时给 `source` 一个**不指向 `out/`** 的可复算来源（现在 `source` 是 `out/f02_formal/shardX/rep0/...`，`out/` 不入库，评审者跟着它会扑空）——运行期不改脚本，合并后连着 ④ 一起做
  - [x] **合并链路预演与自研工具纠错（04:44–04:50）**：先通读 `scripts/30_merge_f02_formal.py` 全 331 行，确认它比我在交接单里假设的更严——跨分片 `config_hash`/`source_hashes_sha256`/`formal_approval`/`policy`/`n_per_rep` 已在 `:231-251` 强制一致，`_read_shard_summary`（`:112-120`）在任何写盘**之前**跑，缺 `summary.json`、`status != formal`、`failures` 非空都会抛错 ⇒ 自动收尾即使提前触发也只留一条失败记录、不产半成品（与 04:03 的门禁实测同结论）。**同时查出我自己那个提升工具的缺陷**：30 号写的目录级 coverage 是第四种 schema（`files=[{path, source, sha256, bytes}]`，无 `target`、无 `kind`），旧 `_normalize_dir_files` 遇到它会**静默 `continue`**——"提升 0 条"看起来像"这目录本来没有身份类文件"，违反 §3.6 失败要响，且会在 ~16:30 收尾最忙时炸。已修：吃下四种 schema、`path` 作为 `target` 的别名、kind 按相对文件名补（`DIR_KIND_FALLBACK` 改成按子目录分层，`f02_formal_*` 与 `f02_*` 分开），并**新增反向校验**（磁盘上有、目录级索引没有的身份类 JSON 一律硬失败）。演练用 `out/scratch/fixture_f02_formal_shape.py` 从 30 号**源码 AST** 取形状（不 import，避免 pandas+sklearn 挤占此刻最低 2 716 MB 的空闲内存；源码改了它会报错，比手抄更强），夹具落在 `out/scratch/fixture_ev/`、顶层用副本，**6 例全过**：正例提升 4 条（kind/status/note 齐，`aggregate/*` 不提升）、写盘后既有 41 条与真登记表逐条相同且 sum(bytes)==total_bytes、二次跑幂等、反例①未登记身份类文件 exit 2、反例②三条坏记录按 `files[i]` 逐条报 exit 2、反例③篡改文件 exit 2 并打印两侧 sha、护栏（夹具证据根 + 真登记表 + 非 dry-run）拒绝写盘。夹具已删，真登记表复核仍为 41 条 / 15 858 444 B / 3 条 repairs / `last_refreshed_at=04:24:36`，`git status` 干净
  - [x] **`3457f85` 推送成功（04:50）**：`111f19b..3457f85`，`codex/d03` 与 `origin/codex/d03` 齐平（此前 04:44/04:46/04:47 三次 `Connection reset` / `port 443` 超时）。**等用户 review，不自行合并**
  - [x] **跨源码版本数值复现（03:52，比双跑更强的核验）**：正式 `shard0/rep0`（快照源码，绑 48 个 v3 文件）vs 18:39 工程跑 `outputs/evidence/f02_n200k_rep0/`（当时源码，绑 46 个）——`freeze.json` 四哈希逐位相同（`5a101174…52cc`/`a6c100e3…2901`/`368c1d89…ee42`/`f6b1bd3c…4d45`）、选模选策同、六个汇总表**全部逐字节相同**、`five_tables` 26 个 artifact 中 **25 个 sha256 一致**（含全部 parquet），唯一不同的是 `lineage/source_hashes_after.json` 自身；差异归因于新增 `evaluation/v3_f01.py`、`evaluation/v3_f02_formal.py` 与 6 个文件内容变更（`v3_models.py 7d31518b→7de5a364`、`v3_ope.py 40010896→f620b369`、`v3_policy.py b8edd3cf→ba058f9b`、`v3_policy_evidence.py 2e6131b3→ca29cdbcc`）。即评审期那 6 处改动对 F02 数值路径**行为保持**，正面回答 AGENTS §12.6 的跨版本配对问题；同一组数字已在 18:39 / 20:44 / 20:51 / 03:39 四次独立运行中复现
- [x] **F02 决策层（18:24 完成）**：两条预声明主张（定向−不发券、定向−同预算随机）各做单侧检验，按 `evaluation.decision.benefit_evidence` 组成 Holm 家族（单侧 α=0.05），输出原始 p/调整阈值/调整 p/通过标记/反演下界；护栏复用 `design/guardrail.py` 的 0.005 非劣效、单侧 0.05，指标 `any_refund_30d_per_assigned_user`；`per_user` 新增 `observed_any_refund_30d`，`arm_summary` 新增退款人数/退款率；`decision.csv / guardrail.csv / decision.json` 与 `freeze.json` 同批先落盘，之后才读真值；F02 11 项测试绿
- [x] **F01 单 rep 历史留出 OPE（20:17 完成，R=0，未证实）**：`v3_f01.py` + `scripts/31_f01_ope.py`，冻结先于审计（freeze_id `3ab44dcb…`，源码哈希 `7012a17b…`）；D03 rep0 n=200k、chosen=`constant`、test 60k，与 E 的 7 列选人哈希及 0.2 档三项数字逐位一致（23 437 人 / 预测成本 11 999.505475 / 审计 0.085638）；DR 主口径两条家族对比 Holm 均拒绝（调整 p 均 0.033431，下界 +0.005137 / +0.010225），但“定向优于同预算随机”只有 DR 显著（IPW p=0.063、SNIPS p=0.088）；真值审计误差 −0.020174 / −0.074016，随机基线符号相反；实际支出超预测预算 28.4%；证据 `outputs/evidence/f01_ope/`、七表 `outputs/tables/v3_phase_F01_*.csv`、正文 `docs/v3_phase_F01_ope.md`，10 项测试绿
- [x] **F01 独立科学评审**：按 `docs/v3_phase_F01_ope.md` §7 检查单；已于 21:28 落盘（见下条），评审前后 F01 均为“未证实”
  - [x] **主负责数值预复核（21:15）**：`family` 两条 DR 调整 p 均 0.033431、下界 +0.005137/+0.010225；0.2 档 IPW 0.063065、SNIPS 0.087814；`audit` 定向 0.085638、误差 −0.020174，随机误差 −0.074016 且符号相反；`policy_meta` 23 437 人、预测成本 11 999.505475，`audit` 实际支出 15 410（+28.4%）；与 E 的 0.2 档贪心逐位一致
  - [x] **评审代理（21:15 重启 → 21:28 返回）**：写入 `docs/reviews/v3_phase_F01_review.md`；P0/P1 已逐条复核并落地（见下）
- [x] **F01 独立科学评审（21:28 落盘）**：`docs/reviews/v3_phase_F01_review.md`，**PASS WITH CONDITIONS，3 P0 / 8 P1**；F01 仍“未证实”
  - [~] **P0-1（复审 05:58 判"部分修"：分解表 160/160 格正确、恒等式残差 1.73e-17，但替换用的机制句与数据矛盾 ⇒ 新 P1 N-1，06:05 已改）**：`tau_hat` 恒定、"定向优于随机"的机制是"低价券覆盖更多人"⇒ 新增 `v3_phase_F01_targeting.csv`（16 行 × 14 列，覆盖效应/单位人群效应/两个 share），正文 §0.1 第 6 条与 §4.8 改写为"真值优势 100% 来自多覆盖人，不是选对人"（0.2 档 +0.031873 = 覆盖 +0.032608 + 单位 −0.000735；被选人平均真值 τ 定向 0.219238 **低于** 随机 0.221118）。**03:55 独立复算**：16 行"覆盖+单位−增量差"最大残差 1.7e-17、两 share 之和−1 最大残差 1.8e-15
  - [~] **P0-2（复审 05:58 判"已修"：1 600 行随机分布，16×13 个汇总量全部重算，最大绝对差 0.0）**：随机组不再当单次抽样 ⇒ 新增 `v3_phase_F01_random_seeds.csv`（**1 600 行 = 8 档 × 200 seed**，列含 `audit_n_selected/audit_increment/audit_actual_spend/dr_increment/dr_se`）与 `v3_phase_F01_random_summary.csv`（16 行 × 27 列：均值/sd/q10/q50/q90/`frozen_seed_value`/`frozen_seed_rank_low`/`targeted_minus_mean`/`mc_se`/`z`/单侧 p/`n_random_at_least_targeted` + 7 个 `equal_spend_*` + `note`），正文 §0.1 第 5、8 条与 §4.6 明确"不得写成定向优于随机"。**03:55 独立复算**：8 档各 200 seed；audit 行 `n_random_at_least_targeted` 165/77/15/0/0/1/0/200 与表逐值相同；0.2 档 `frozen_seed_rank_low` audit 0.110 / dr 0.015 相符
  - [~] **P0-3（复审 05:58 判"已修"，但派生新 P1 N-2：DR 主口径不可从证据包重建 ⇒ line 10 可复算声明 06:05 已收窄）**：`outputs/evidence/f01_ope/` 不再只有 freeze/meta ⇒ 现为 **18 条记录、9 490 785 字节**（入库 4 185 712），含 selection/masks/observed/features/truth 五个 gzip 帧 + 11 张正文表副本 + freeze/meta/coverage；顶层 `outputs/evidence/coverage.json` **41 条、15 858 444 字节**（04:24 起；此前 35 条 / 15 811 358），逐条 sha256/bytes 复算一致（03:13 起由 `scripts/31_f01_ope.py:_refresh_top_registry` 自动维护；04:24 由 `out/scratch/register_evidence_top.py` 补登记 `d03_formal` 与 `f02_n200k_rep0` 的 6 个身份类 JSON，既有 35 条逐条与顺序均未变）
  - [~] **P1-1~P1-8（复审 05:58：P1-2/3/5/6 已修，P1-1/4/7 部分修 ⇒ 新 P1 N-2/N-3，06:05 已改）**：DR "预声明"改为引配置 `evaluation.decision.benefit_evidence`；1.28 SE 尺子改为配对增量 SE（新 `v3_phase_F01_increment.csv` 96 行）；ESS 权重乘 `T/(1−T)`；真值改为冻结后物化并要求 `require_truth_frame(manifest=…)` 比对 `freeze_id`（审计表新增 `audit_truth_sha256`）；HEAD `verify_freeze_manifest` 通过（02:53 重跑绑 live 源码，48 份哈希逐份复算 0 处不符）；E 随机均值口径统一引 CF 表；9 列 vs 7 列哈希分别标注；补等实际支出对照（7 个 `equal_spend_*` 列）
  - [x] **P1-5/P1-8 复验（02:53 重跑 + 03:55 独立复算）**：HEAD `verify_freeze_manifest` 通过、选人帧 7 列哈希与 D03/E 交接一致（`372a1bcc…`）；等支出回归用 200 行逐种子支出行独立 OLS 复算——0.2 档 audit 的斜率 −0.000007170、SE 0.000002784、截距 0.155870691、r² 0.032422922 **全部差 0.000e+00**；`slope_t = slope/slope_se` 16 行最大偏差 0.0；`reliability_passed=False` 在 `ope_vs_audit.csv` 48 行中 7 行（0.04 档 2 行 / 0.8 档 5 行，与正文 §4.5 一致），在 `value.csv` 96 行中 12 行 = **4 个（档,策略）格子 × 3 个估计量**；`sign_agrees=False` 5 行、`holm_rejected=True` 2 行均与正文相符
  - [x] **F01 修复实现（2026-10-27 22:31 起于隔离副本 `out/f01_dev/`，已回写 live 并重跑）**：ESS 权重乘 `T/(1−T)`（`v3_ope.reliability_gate`）；`_value_table` 增每策略相对 no_coupon 的配对增量/SE/z/单侧 p（新 `increment_table`）；`ope_vs_audit` 填 `ope_se/ope_z/ope_one_sided_p`；审计表增 `audit_truth_sha256` 并要求 `require_truth_frame(manifest=...)` 比对 freeze_id；新增 `targeting_decomposition_table` 与 `random_policy_distribution`（200 seed 同预算随机名单、冻结 seed 复现校验、定向 vs 随机均值单侧 p、等实际支出回归）；`scripts/31_f01_ope.py` 增 3 张表、帧双哈希、git commit、truth_sha 与完整证据包。n=200k 单 rep 已按此重跑两次（00:47、02:53），第二次绑 live 源码
- [x] **F01 正文改写（03:16 同步、03:59 再修）**：按 P0-1（定向机制=覆盖+单位效应分解）、P0-2（200 seed 分布与冻结 seed 排名）、P0-3（证据包）重写 `docs/v3_phase_F01_ope.md`。**03:59 主负责自查又抓出两类错并全文改正**：① 5 处把等支出外推写成"8 档全部/8 档全为 0"，实际是 **0.04–0.80 七档为 0、1.00 档 NaN**（该档 200 seed 真实支出零方差、回归不可定义；§4.7 表格本来是对的，错的是 §0.1 第 9 条、§4.7 标题与三条要点、§6 局限性第 7 条、§8 检查单）；② §6 局限性第 8 条把 ESS 门禁写成"5 行未过"，实际是 **4 个格子未过**（`value.csv` 12 行 = 4 格 × 3 估计量；`ope_vs_audit.csv` 7 行）。§8 检查单同时补上可复算的具体值（1 600 行表结构、8 档 `n_random_at_least_targeted`、1.7e-17 残差、slope_t 偏差 0.0）
- [x] F01 改动后全量串行测试 1 248 项 exit=0（20:20:35–20:28:04，单进程，无并发写盘），日志 `outputs/runs/f01_tests/full_suite.log`
- [x] **F01 与 E 同源重跑（2026-10-28 02:52:56–02:58:05，单进程 exit=0，296.9 秒，日志 `out/logs/f01_rerun_20261028_0253.log`）**：`freeze_id` `bfb26807…` → **`b8402f30d82c96af…`**，`source_hash_combined` `71ec6104…` → **`d3e169f1bd3d7822…`**；48 份源码哈希里**只有 1 份变**（`policy/v3_policy_evidence.py` `18ac6f40…`→`ca29cdbc…`，正是 E 绑定的那份），而 F01 链路不 import 该模块（grep 为空）⇒ 数字不可能动。动机：00:47 的 F01 与 E 的 A 家族**不同源**，属 AGENTS §12.6 禁止的跨版本配对，现已消除
  - [x] **零漂移复核（`out/scratch/verify_f01_rerun.py` → `out/scratch/verify_f01_r3.txt`，exit=0）**：11 张正文表 **10 张逐字节相同**，唯一不同的 `v3_phase_F01_audit.csv` 只有 `audit_freeze_id` 一列 32 行随 freeze_id 变；4 个 gzip 帧 + `tables/` 11 张副本与 00:49 备份逐字节相同；`meta.json` 键数 31→31、无增无删，共同键只 6 个变（`stage_seconds` / `random_policy_distribution.seconds` / `artifacts.audit.sha256` / `freeze.*` / `source_hashes` / `source_hash_combined`），**没有一个是结果数字**；`selection/user_id/design_probability/nuisance/真值帧` 哈希、`budgets`、`family_contrasts` 全逐位相同；目录级 coverage 18 条复算一致（`total_bytes` 9 490 783 → **9 490 785**，差 2 字节来自 freeze/meta 两个 JSON 长度）；DR 主数字复现 +0.065463 / +0.085714（Holm 均 0.033431、均拒绝）、审计误差 −0.074016 / −0.020174 / +0.053841
- [x] **顶层登记表刷新的根因修复（03:13，即上面缺口 ②）**：`scripts/31_f01_ope.py` 新增 `_rel_posix`（`:132`）与 `_refresh_top_registry`（`:140`），导出证据后自动刷新顶层 `outputs/evidence/coverage.json` 里自身前缀的记录（sha256 / bytes / `freeze_id` / `created_at_in_file` / **`source`**），清掉该前缀下已消失的记录，再对**全表**逐条复算——文件缺失、sha256 或 bytes 不符、证据副本与运行产物不一致，一律抛错（只加强不削弱，AGENTS §12.3）。真实数据实跑：35 条全表一致、他前缀 33 条逐条未变、`source` 由旧 `out/f01_ope/` 纠正为 `out/f01_ope_formal_20261028_0253/`、`total_bytes=15 811 358`；备份 `out/scratch/coverage_backup_before_31patch_20261028_031329.json`，可重跑脚本 `out/scratch/run_top_registry_refresh.py`
  - [x] 5 项篡改/边界测试 `tests/test_v3_f01_registry.py` 全绿：他前缀记录原位保留 + 失效记录被清 + `note` 不丢；篡改他前缀 sha → 抛"全表复算"；删他前缀文件 → 抛"文件缺失"；证据副本与运行产物不一致 → 抛错；顶层登记表缺失 → 抛 `FileNotFoundError`
  - [!] **刻意未改 `scripts/24_e_evidence.py`**：它被 E 的 `source_sha256` 逐文件绑定（`6453db227c0349c0…`），改它就必须重跑 E 两家族（约 50 分钟/家族）才能让文档哈希与 live 文件一致；E 侧仍用其内联的"只清自身前缀"逻辑，与缺口 ① 一并留待 F02 之后
- [x] `docs/v3_phase_F01_ope.md` 同步（03:16）：文首维护时间、§0.1 与 §3 的 `freeze_id`、§3 源码组合哈希、§1 表新增"与 E 同源重跑"行；更正证据包字节 4 185 713→**4 185 712**、9 490 786→**9 490 785**（原值与 00:47 和 02:53 两次运行都不符，属转写错）；§3.1 改写为"freeze_id 为什么变了两次"，附第二次变化的单文件归因与逐项复算清单；§3 补两个特征帧哈希口径（`d15cf24d…` 不含 `user_id`、`6a4289ef…` 含）以免被误判为矛盾；§7 复现命令改指**入库**参考帧 `outputs/evidence/e_evidence_rep0_a/frame_rep0_constant.csv`（与 `out/` 副本逐字节相同，sha `c8fd698e…`）并写明登记表自检；§8 检查单新增 3 条（顶层索引一致性、F01↔E 同源、单文件归因）
- [x] **全量串行测试（2026-10-28 03:21:18–03:27:42，单进程 384 秒，`--basetemp C:/cg_t -p no:warnings`，无并发写盘）**：**1 264 项全绿、exit=0**，日志 `out/logs/pytest_full_20261028_0321.log`（`out/` 不入库，复现命令一行：`pytest -q -p no:warnings --basetemp C:/cg_t`）。条数是用 `--collect-only` 独立确认的（collected=1264），与日志里 1264 个进度点、0 个 `F/E/s` 标记一致——**不是从日志末尾读的**：`pyproject.toml` 的 `addopts` 已含 `-q`，命令行再给一次会让 pytest 省掉末尾"N passed"汇总行
- [x] **F01 小项（18:24 完成）**：`v3_ope.cost_and_guardrail` 的 `confidence` 默认改为 `None`，运行时读 `evaluation.confidence_level`，不再写死 0.95。
- [x] 全量串行测试（决策层改动后）1 228 项复跑 exit=0（18:24:43–18:31:47，单进程），日志 `outputs/runs/f02_tests/full_suite_after_decision.log`
- [ ] 独立科学评审 → F 判定

## G 阶段前置阻塞：重复预算存在两份互相矛盾的契约（2026-10-28 07:09，北京时间）

- [!] **这不是排期问题，是"按哪一份契约跑 G"的问题，必须由用户裁决；我不自行选择、也不自行改冻结配置。**
      `configs/v3/`（代码实际读取、哈希绑定 `approval.json` 的七份冻结配置）与
      `configs/budget/repetition_overlay.yaml`（用户 2026-10-25"放宽要求、可砍批数"授权的覆盖声明）
      描述的是**两个规模差 12.2 倍的实验**。而 **overlay 没有任何代码读取**：
      `grep -rn "overlay" --include=*.py --include=*.yaml src configs scripts` 返回 **0 行**；
      overlay 自己第 2 行也写明"**不修改 configs/v3/ 下七份冻结配置**"。
      ⇒ **overlay 目前只是一份文档，真跑起来一律按冻结配置。**
      TODO:142 的评审条件 C1 要求"GOAL/G01/YAML 与 overlay 对齐"，当时状态记为"GOAL 已改"——
      **GOAL.md 与 overlay 确实对齐了，YAML 没有**，这一半从未完成。

**逐项对照**（冻结侧 = `configs/v3/execution.yaml` + `scenarios.yaml` 本机实读并按格求和；overlay 侧 = 该文件实读）：

| 项 | 冻结配置（代码读的） | overlay 声明 | 倍数 |
|---|---|---|---|
| Tier1 核心格（4 格） | ate 2 000 + 完整学习 3 600（18 个模型位×200）+ 独立验证 800 = **6 400** | `tier1_total_jobs: 800` | **8.0×** |
| Tier2（65 格） | ate 6 500 + 完整学习 30 500（305 个模型位×100）+ 独立验证 6 500 = **43 500** | 12 格×30 = **360**，其余 53 格 0 | **120.8×** |
| 完整 AA | **1 000/层 × 4 层 = 4 000**（`execution.yaml:25`、`scenarios.yaml:429/1314/1943/2960`，且四格 `R` 同为 1000） | **250/层 × 4 = 1 000** | **4.0×** |
| Tier1 独立验证 | 200/格 × 4 = **800** | 50/格 × 4 = **200** | **4.0×** |
| 功效格 | `design.local_power.repeats_per_point: 100` × 20 格 = **2 000** | 10/格 × 20 = **200** | **10×** |
| 再训练 bootstrap | **200** | 20/层 × 4 = **80** | **2.5×** |
| 固定策略 bootstrap | **1 000** | overlay **未提** | — |
| 随机名单种子/预算 | **200** | overlay **未提** | — |
| **作业总数** | **55 100** | **4 513**（overlay 自报 `total_jobs`） | **12.2×** |

- **AA 一项用实测成本定价**（`outputs/evidence/aa/all_repetitions.csv`，1 384 行、4 格 × 250 个不同 rep、n=200 000）：
  `total_wall_s` 均值 **160.00 s**（sd 19.82、max 186.80），`total_cpu_s/total_wall_s = 0.975` ⇒ **单线程、无并发争用虚高**；
  `file_lock_retries` 全表只有 **8/1 384** 行非零。旁证：`outputs/evidence/negctl/aa_repetitions.csv` 100 行均值 **160.98 s**，两者差 0.6%。
  - overlay 路线 1 000 次 = **44.4 CPU·h**；冻结路线 4 000 次 = **177.8 CPU·h**；**差 133.3 CPU·h**。
  - **GOAL.md G01 的"约 33 / 约 131 CPU·h"隐含 117.9 s/rep，比实测低**；按 §12.5 报最差口径并说明分母：
    **实测 ÷ GOAL 隐含值 = +35.7%**（分母是 GOAL 的 117.9 s/rep）。等价地说 GOAL 的值比实测低 26.3%。两个方向都写，避免只引有利的那个。
- **两条路线的整机墙钟**（用 overlay 自己的 `cost_estimate`，再乘上面实测出来的 1.357 修正）：
  overlay 路线 `revised_cpu_hours_after_optimization: 132.4` CPU·h；
  冻结路线 `measured_cpu_hours_original: 1186` CPU·h，按同一 1.357 修正 ⇒ **约 1 610 CPU·h**。
- [!] **overlay 的并行度假设被 F02 现场遥测否掉**：overlay 写 `parallel_workers_max: 4`、理由"单 rep 峰值 **1.88 GB**，可用内存 8.4 GB"。
      但 F02 正在跑的 2 条 lane 实测峰值 RSS = **3 168 MB 与 2 914 MB**（`out/logs/f02_memwatch_20261028_0351.log`，07:08 时 free 3 769 MB），
      即**含模型拟合的 rep 峰值约 1.6× overlay 的假设值**。1.88 GB 大概只对"不拟合模型的 AA 形 rep"成立，
      而冻结计划的 **34 100 / 55 100 = 62%** 作业是完整学习（必拟合模型）。
      ⇒ 两条路线的墙钟都应按 **2 workers**（不是 4）重算：overlay 路线约 **2.8 天**，冻结路线约 **33.5 天**。
- [!] **机制上现在动不了**：`src/causal_growth/data/v3_pipeline.py:41-44` 的 `pipeline_source_hashes()`
      绑定 glob **包含 `configs/v3/*.yaml`**，F02 四分片未退出前改这些文件会让作业抛
      `RuntimeError: source files changed during the data run`（AGENTS §11）。所以本项**最早在 F02 合并后**处理。
- **改冻结配置要动 11 处、且触发评审**：`execution.yaml:25`（1000→250）、4 个 AA 格的 `complete_aa`（1000→250）、
      同 4 格的 `R`（1000→250，因为 `v3_config.py:189` 要求 `R == max(formal_repetitions.values())`、
      `v3_aa.py:316-318` 要求 `complete_aa == tier1_aa_per_layer == R`；已核四格 `formal_repetitions` 只有 `complete_aa` 一个键）、
      以及 `scenarios.yaml:261/264` 两个计划计数（`historical_dgp_jobs` 12500→9500、`complete_aa_jobs` 4000→1000）。合计 1 + 4 + 4 + 2 = **11** 行。
      `execution.yaml` 自带 `change_matrix_requires_versioned_reason_and_review: true` ⇒ **必须带版本化理由并过评审**，不能静默改。
- **顺带核实清楚、避免误判的两件事**：
  ① 现有 1 384 行 AA 证据**不能**直接当 G01 的正式 AA：它的 `source_hashes_before` 与当前工作区相比有 **6 份源码已漂移**
     （`v3_local_power_pipeline.py`、`v3_observed.py`、`v3_power.py`、`v3_local_power.py`、`v3_models.py`、`v3_data_checks.py`），
     9 份 `configs/` 则**逐份未变**（`execution.yaml` 当时与现在都是 `dc1c8e9a…`、`scenarios.yaml` 都是 `29a158b0…`）
     ⇒ 那 250/层是在**配置已经写着 1000/层**的情况下跑的，按 AGENTS §12.6"跨源码版本不得配对"，G01 的 AA 无论选哪条路线都要在当前树上重跑。
  ② 这些 manifest 的 `purpose = engineering_or_downstream_input_not_formal_completion`、`formal_repetitions_completed = 0`
     **不构成"非正式"的证据**：这是全项目所有写 manifest 入口的**统一戳**（`v3_pipeline.py:120/214`、`v3_power.py:1181/2237`、
     `v3_local_power_pipeline.py:976`、`v3_data_checks.py:206/418`、`v3_aa.py:1038`），`v3_aa.py:67` 明写"本入口不改变任何正式计数器"，
     `v3_data_checks.py:407` 甚至**断言** `no_formal_repetitions_claimed`。⇒ 正式与否由验收记录（GOAL.md + 独立评审）判定，不由 manifest 计数器判定。
     我一开始把这个戳读成"D02 的 AA 不是正式的"，查了源码才否掉自己的猜测——记下来避免下次再误读。
- **待用户裁决的三条路线**（我给出代价，不给结论）：
  - **甲：把 overlay 的批数写进冻结配置**（改上述 7 处 + 重算 `protocol_config_hash` 与 `approval.json` 绑定 + 版本化理由 + 独立评审）。
    代价：约 **2.8 天**整机；风险：动了已冻结、已被 D02/D03/E/F01 引用的配置哈希，需要重新说明"哪些既有证据仍成立"。
  - **乙：废弃 overlay，按冻结配置跑满**。代价：约 **33.5 天**整机（1 610 CPU·h ÷ 2 workers），其中 AA 一项就 177.8 CPU·h；
    好处：口径与代码契约完全一致，无需改冻结配置。
  - **丙：不改配置，跑的时候在入口显式传 overlay 的批数**（D02 实际就是这么做的），并在每张 G 结果表标注"R 取自 overlay、非 config"。
    代价：约 **2.8 天**；风险：**留下一份永久的契约与实跑不一致**，任何后续评审都可以按 AGENTS §4/§12 判"口径作废"。
  - 我的倾向是**甲**（契约与实跑一致，且用户 2026-10-25 已经授权过这个批数），但**甲要改冻结配置、且 `execution.yaml` 明写要评审**，
    所以我**不自行执行**，等用户一句话或独立评审签字。

### 用户裁决：走甲方案（2026-10-28 11:05，北京时间）

- **用户原话**：「G阶段按甲方案。按照你的思考和建议的方式推进。」⇒ **只解决 AA 一项，不是把 overlay 整表照搬**。
- **范围**：AA 4 层 × **250**/层（= 用户 2026-10-25 13:45 授权的批数）。其余项**保持冻结值**，因为
  GOAL G01/G02 仍写 500 ATE / 200 学习 / 200 独立验证 / 100 Tier2 / 200 再训练 / 1000 固定 bootstrap；
  **只有 AA 被 2026-10-25 的决策真正改过**（TODO:142 的 C1 条件也只点名 AA）。把 overlay 其余削减一并落地
  等于**同时改验收标准**，超出用户这次给的范围。
- **要改的 11 行**（已逐行实测，行尾按各文件自身：`execution.yaml` 为 LF、`scenarios.yaml` 为 CRLF）：
  `execution.yaml:25` `tier1_aa_per_layer: 1000→250`；`scenarios.yaml:411/1296/1925/2942` 四格 `R: 1000→250`；
  `scenarios.yaml:429/1314/1943/2960` 四格 `complete_aa: 1000→250`；`scenarios.yaml:264` `complete_aa_jobs: 4000→1000`；
  `scenarios.yaml:261` `historical_dgp_jobs: 12500→9500`（加载器要求它与 Σ`max(formal_repetitions.values())` 相等）。
- **补丁工具已就绪**：`out/scratch/g_route_jia_aa250.py`（`out/` gitignore，故不进库；F02 结束后按 §12.1 决定是否提升进 `scripts/`）。
  - `--dry-run` 已通过（2026-10-28 11:04，11:08 补第 11 行后复跑）：断言恰 **1 + 10 = 11** 行改动，逐行打印旧值→新值（含行号）。
  - 真跑安全阀已实测：F02 未集齐时 `FAIL[5] F02 只有 116/200 个 rep manifest，冻结窗口未结束，拒绝改冻结配置（AGENTS §11）`。
  - 写后自校验：`load_v3_protocol()` 读回 `tier1_aa_per_layer=250`、四格 `(R, complete_aa) == (250, 250)`。
  - 反例已演练：CRLF 未处理时 `FAIL[4]`（行锚点 0 命中）、就地改列表导致改动计数恒 0 时 `FAIL[7]`——两处都真实拦住过，不是装饰。
- **落地链（F02 四片退出后立即执行，顺序不可换）**：
  ① 预演：刷新 `out/scratch/sim_v3_aa250/` 副本 → `python out/scratch/g_route_jia_aa250.py --root out/scratch/sim_v3_aa250`
  （与真跑同一入口，含完整 `load_v3_protocol()` 校验）；
  ② `python out/scratch/g_route_jia_aa250.py`（真跑，需 200 manifest）；
  ③ `python scripts/09_freeze_v3_protocol.py --output outputs/v3/protocol_aa250` —— **落新目录，不就地覆盖**
  `outputs/v3/protocol/`（那是 Phase A 快照，其 `protocol_sha256` 绑定 `docs/v3_协议.md` 的字节，就地重跑等于改写历史）；
  另记一处口径偏差：09 号把 `experiment_results_exist` **硬编码为 `false`**（`scripts/09_freeze_v3_protocol.py:39`），
  今天已有 D02–F02 结果，故该字段不采信脚本输出，改由 ④ 的修订文件写 `true` 并注明来源（11:25 实读确认）；
  ④ **新建** `outputs/v3/protocol_aa250/approval_revision_20261028.json`（`supersedes_config_hash` 旧→新、逐文件 `source_sha256`、
  `reason_doc` + sha256、`authorized_by`=11:05 用户裁决、`scope`、`experiment_results_exist: true`、`review`）；
  `outputs/v3/protocol/approval.json` **保留原字节**（Phase A 的批准记录，不是"当前配置说明书"；无代码读取它，已 grep 核实）；
  ⑤ 版本化理由文档 **草稿已建**：`docs/v3_phase_G_protocol_change_aa250.md`（授权链、11 行清单、绑定值待填表、既有证据口径、验证与回滚；执行时把 §3 的 `<待填>` 填实）；
  ⑥ **独立评审**该改动后才能把 G01 记为"按新契约开跑"。
- **既有证据是否失效**：D02/D03/E/F01/F02 的 manifest 绑定的是**运行当时**的 `config_hash`，作为历史记录仍然成立；
  改配置只影响**之后**新跑的作业。须在理由文档里逐阶段列出其绑定哈希，避免"改了配置=旧证据作废"的误读。
- **代价**（按实测 160.00 s/rep、2 workers）：AA 1000 次 ≈ **44.4 CPU·h** ≈ **0.9 天**整机；加上其余冻结项，G 仍以"周"计。
  这次改动**只削 AA 的 3 000 次（≈ 133.3 CPU·h）**，不改变 G 的总量级判断。

## 三阶段复审与运行期冻结边界（2026-10-28 05:15，北京时间）

**D03、E、F01 三个阶段曾处在完全相同的状态**：独立评审均为 PASS WITH CONDITIONS，条件已由主负责实现，
按 AGENTS §7.4「只有独立复审通过才能记为关闭」，三者在 GOAL.md 里都必须保持"未证实"。
⇒ **复审、不是新工作，是这三项唯一的阻塞**。三份复审已全部在后台起飞；**D03 的已于 05:15 返回 PASS**：

| 阶段 | 原评审 | 原条件 | 复审启动 | 产出 | 复审结果 |
|---|---|---|---|---|---|
| D03 | 20:53 PASS WITH CONDITIONS | 1 P0 + 6 P1（已全部实现，见 `docs/v3_phase_D03_formal.md` §11） | 2026-10-28 04:55 | `docs/reviews/v3_phase_D03_rereview.md` | **PASS（05:15）→ GOAL 已改"通过"**；另提 4 项 P2，已全部核实并修正（见下） |
| F01 | 21:35 PASS WITH CONDITIONS | 3 P0 + 8 P1（`docs/v3_phase_F01_ope.md:6` 记为均已落地） | 2026-10-28 05:10 | `docs/reviews/v3_phase_F01_rereview.md` | 在飞，未返回 |
| E | 21:27 PASS WITH CONDITIONS | 0 P0 + 6 P1 + 9 P2（数据层已由 A/B 两家族重跑覆盖） | 2026-10-28 05:13 | `docs/reviews/v3_phase_E_rereview.md` | **PASS WITH CONDITIONS（05:34）**：0 P0 + 3 新 P1，全为文档/导出层、**无一需要重跑**；原 6 P1 = 4 已修 + 2 部分修 + 0 未修。4 项修复 05:46 落地，**GOAL 仍"未证实"待确认**（见下） |

三份复审回来之前，**不改 GOAL.md**（复审代理要读它的验收表，且宁愿带着结论一次写对，不写两遍）。
`TODO.md` 与 `docs/v3_决策与反思日志.md` 不是复审输入，故照常更新。

- [x] **核对 E 的 6 项 P1 在磁盘上的真实状态（05:11，不依赖正文自述）**：
      P1-1 **已闭**（B 家族 `frame_model=causal_forest`、`tau_hat_nunique=59 861`、`sd=0.781647`；A 家族 `nunique=1`、`sd=1.11e-16` 作为退化对照保留）；
      P1-2 **数据层已闭**（`v3_phase_E_decomposition.csv` 两家族均新增 `truth_oracle_cost_basis`、`learning_error_cost_hat_basis_cny_per_user`、`total_regret_cost_hat_basis_cny_per_user`、`identity_residual_cost_hat_basis`、`true_value_truth_cost_hat_basis`、`truth_feasible_under_cost_hat`，raw `cost_true` 口径另列作敏感性）；
      P1-3 **数据层已闭；导出层曾被复审判"部分修"，05:44 已补齐**（`outputs/evidence/e_evidence_rep0_{a,b}/` 各 11 → **A 11 / B 12** 条记录、顶层登记表 **42** 条中 **23** 条为 E；meta 含 `git_commit=e004810…`、逐文件 `source_sha256`、`protocol_config_hash=30511a32…`、`protocol_source_hashes`、`d03_snapshot_combined_sha256=be0d48f4…`、`frame_file_sha256`、`frame_dataframe_sha256`）。**复审 N2 抓到的真缺口**：A 导出的 `run_constant.log`（2 209 B、sha `6ac1ea95…`、mtime 10-27 19:42）是 **19:17 那次被取代运行**的日志，与 `meta_constant.json` 的 `created_at=01:12:03` 直接矛盾；B 家族**完全没有日志记录**。已按"日志首行 `[E evidence HH:MM:SS]` 必须与同家族 meta `created_at` 逐字相同、不符即中止"的断言重导出 A、新增 B（2 597 B `0a32c7f9…` / 2 881 B `dbf0001d…`），两级 coverage 与顶层登记表同步（41 → **42** 条、`total_bytes` **15 861 713**、`registry_repairs` 第 4 条），并对 **65 条记录全表复算**（存在 + bytes + sha256）**0 不符**；
      P1-6 **已闭**（A/B 同 rep、同 60 000 用户、同池、同 8 预算档）；
      P1-4 素材已导出（`calibration_validation_treated_{constant,cf}.csv`，列 `user_id,predicted_cost_cny,observed_coupon_cost_cny`），措辞是否已改由复审判定；
      P1-5 **原表述确认与表矛盾**：`v3_phase_E_random_summary.csv` 的 1.00 行 `budget_cny=60 000.0`、`mean_actual_spend_cny=50 570.0`、`mean_predicted_cost_cny=49 190.1523`、`overrun_probability=0.0` ⇒ 实际支出低于预算 **9 430 元（−15.72%）**，"等于预算上限"不成立
- [!] **运行期冻结边界（本轮新核实，此前没写清）**：`src/causal_growth/policy/v3_policy_evidence.py`
      **落在 F02 的绑定 glob `src/causal_growth/**/v3*.py` 内**。⇒ 任何 P1-2 那类"改真值 oracle 口径"
      的源码修改，在四个分片全部退出前都不能做，否则 `pipeline_source_hashes()` 前后不一致，
      作业抛 `RuntimeError: source files changed during the data run`，12 小时报废。
      `scripts/24_e_evidence.py` 不在绑定 glob 内（`scripts/` 不被哈希），改它不会炸作业，
      但改完必须重跑两家族才能让 meta 的 `source_sha256` 与 live 文件一致——**重跑是数据作业，
      与正式运行并行违反 AGENTS §11.2**，故同样推到 F02 之后。
- [ ] **E 唯一残留子项：meta 缺 `cfg.hash(64)`（=`e1aa4314b8d84b04…`）**。两条路，F02 之后二选一：
      - **甲（推荐）**：不改冻结的 `meta_*.json`（改它会让目录级 coverage 的 sha256 失配、被登记表校验器正确拒绝），
        而是往 `outputs/evidence/e_evidence_rep0_{a,b}/` 各加一份**明确标注为补充件**的绑定说明，
        记 `cfg_hash` 由 `outputs/evidence/d03_formal/shard*_summary.json` 交叉读出，并同步写进目录级 `coverage.json`
        （否则触发 §12.7 的反向检查："磁盘上有身份类文件、索引未登记"）。代价小、不动冻结证据，但强度弱于"在 meta 里"。
      - **乙**：改 `scripts/24_e_evidence.py` 并重跑两家族（约 50 分钟/家族）。强度最高，代价是 100 分钟独占机器。
      评审若判甲不够，再走乙。
- [ ] **F02 合并后的机器排队顺序（已定）**：① 合并 + 证据登记（自动 + 约 15 分钟人工）→
      ② **D01 20 rep（约 92 分钟，独占）** → ③ E 的甲/乙路线 → ④ 全量串行测试复跑。
      **理由**：D01 是 GOAL 的验收项（当前"未证实"），E 的残留只是**一个元数据字段**、
      且其值已可从 D03 分片摘要交叉读出；先做验收项，后补元数据。
- [x] `git push origin codex/d03`：**已于 2026-10-28 06:46 推送成功**（`1da7780..a9249d7`，exit=0）。
      历史：04:50 与 04:56 两次成功之后，05:08 起连续 **7** 次失败（443 超时 / `Connection was reset`），
      期间本地最多积到 `[ahead 6]`，提交始终安全；第 8 次尝试成功。
      全程**不装无人值守的自动重试循环**（网络可见动作 + 无人复核）。**推上后仍等用户 review，不自行合并。**
- [x] **D03 独立复审 PASS（2026-10-28 05:15，`docs/reviews/v3_phase_D03_rereview.md`）**：
      原评审 P0-1 与 P1-1～P1-6「全部真实落地、数字全部独立复现、无残留旧口径」；
      §11.1 事实锚点逐项为真。**GOAL.md 的 D03 行已于 05:21 改为"通过"**（验收表 + R01 + 交接节点三处），
      成为继 D02 之后第二个走完"评审判定 → 修复 → 独立复核 PASS"三环的阶段。
      主负责按 §7.4 复核了复审自身的断言（`snapshot_vs_live` 83/3/0、绑定 48=37+9+2、
      起跑时间、6 提交对四个 glob 命中 0、§6.1/§6.2 全部数字从 320 行 oracle 表重算），一致。
  - [x] **复审新提 4 项 P2 已全部核实并当场修正**（05:17–05:20，详见 `docs/v3_phase_D03_formal.md` §11.2）：
        ① F02 起跑 03:45→**03:39**（`snapshot_binding.json` 的 `created_at=03:39:04`、日志名 `..._0339.log`）
        ② "03:45 之后两个提交"→**6 个**（`c290b84`/`17a1011`/`111f19b`/`3457f85`/`1da7780`/`c98ff35`，
        `git log --name-only` 逐个比对四个绑定 glob，**命中 0**）
        ③ §11 响应表引"决策日志 21:00 条"→**21:02 条**（日志无 21:00 条）
        ④ **§6.1 混分母**：`share_optimal` 列填的是 0.20 档均值（0.2125/0.1919/0.1250/0.1250/0.1250），
        而邻列"64 格平均后悔"是 64 格均值；64 格的 share 实为 **0.2608/0.2396/0.1752/0.1854/0.1250**。
        已改为双列并各自标注分母。**这是 AGENTS §12.5 写成规则一天之后的同类复发**，
        反省与机制见决策日志 05:24 条
  - [x] ETA 锚点随 ① 一并更正：自 03:39 起 ⇒ **15:20–17:35 集齐、点估计 ~16:27**（工期 12.80 h 未变）；
        GOAL.md / AGENT_HANDOFF.md / 本文件三处已同步，历史条目保留原值并标注更正
- [x] **E 独立复审返回 PASS WITH CONDITIONS（2026-10-28 05:34，`docs/reviews/v3_phase_E_rereview.md`，43 501 B）**：
      **0 P0 + 3 新 P1 + 若干 P2，且无一需要重跑**——复审明确"证据本身是可靠的"。
      原 6 P1 的判定：P1-1 / P1-4 / P1-5 / P1-6 **已修**，P1-2 / P1-3 **部分修**（残留即下面的 N3 / N2）。
      复审独立复现的关键值：A 学习误差 0.98436@0.04、0.99284@0.10（与正文最大相对差 **1.76e-16**）、
      raw→hat 口径迁移 **+34.5% / +11.9%**；校准 n=19 987、MAE 1.486140、RMSE 2.735293、r 0.085254
      = 上界 0.108574 的 **78.5%**、常数预测器 MAE 1.503065 / RMSE 2.741409、Brier 0.074818 vs 0.075153；
      12/12 份 live 源码与 YAML 哈希 MATCH、两个证据包双向 sha 校验通过、6 个正文数字**仅凭证据包**重建。
      **B 家族确实把求解器分开了**（vs `cent_exact_dp`，小池 24 格）：greedy 16/24 不同（最大 −0.310996 元）、
      local_swap 15/24（−0.305452；24/24 ≥ greedy）、MILP 14/24（24 optimal、`may_claim_optimal` 16、
      8 个 gap>1e-12 最大 9.663e-04）、brute_force 5/8、LP 24/24 为上界（+1.523250，3 格 −1.421e-14）。
  - [x] **主负责按 §7.4 逐项复核复审的 3 项新 P1，全部为真，已当场修完（05:40–05:48）**：
        **N3 / P1-2 残留**——正文 §6 `:419-421` 写"两者的真值最优都来自 `truth_milp_cost_basis=…`"，
        源码实为 `cent_exact_dp(tau_true, cost_hat)` 主口径 + `cent_exact_dp(tau_true, cost_true)` 敏感性
        （`v3_policy_evidence.py:851-870`），MILP 只是复核（`:920-921` 注释明写"它的 bound/incumbent
        不是 raw truth 问题的界，只能看 status/gap"）。已改正并注明数值未变。
        **N1**——正文 §8.1 `:561-562` 写"local swap 24 格与贪心完全相同（A 与 B 都是）"：
        复算确认 **A 24/24 五列全同，B 不是**（预测成本 19/24 同、支出与真值 21/24 同，
        最大 |差| 0.107 元 / 10 元 / 0.000303 元/人）。已改为两家族分别陈述 + 差格清单。
        **N2**——运行日志重导出（详见上面 P1-3 条），并把"日志时间戳必须等于 meta `created_at`"做成断言。
  - [x] **P2 三项一并修**：① 校准 JSON 实为 **40 键中 34 同、6 异**（原文写 39/1），
        6 个异键全是溯源/模型标签（`calibration_rows_path`、`frame_model`、`frame_model_is_chosen`、
        `frame_model_is_chosen_in_full_fit`、`tau_hat_nunique` 1 vs 59 861、`tau_hat_sd_cny`），
        **没有一个校准统计量**，"校准与 τ̂ 无关"的结论不变；② 随机汇总表**两家族 17 列同名同序、
        8×17 逐值相同**（原文写"B 多一列 `mean_value_per_actual_spend`"是错的）；
        ③ `docs/v3_phase_E_coverage.md` 4 处过期陈述（小池表家族归属、19:17 运行已被取代、
        "local swap 24/24 完全相同"只对 A 成立并补 B 的 11/24 与 5/24、评审状态）。
  - [x] **E01/E02 转"通过"的前置**：复审要求这 4 项落地后即可判通过，但按 AGENTS §7.4
        主负责不单方改状态 ⇒ 需一次**窄口径确认**（只核这 4 项 + 3 项新 P1 是否真关闭），
        与 D02/D03 的第三环同构。**在此之前 GOAL.md 的 E01/E02 保持"未证实"**。
        确认复审 05:46 起飞、**05:53 返回 PASS**（`docs/reviews/v3_phase_E_recheck.md`）：
        3 项新 P1 与 3 项 P2 逐项确认真实关闭、主负责给出的每一个数字被独立复现、
        并独立重算全部 **65 条登记记录（顶层 42 + A 11 + B 12）sha256/bytes，0 不符**
        ⇒ GOAL.md 的 E01/E02 已于 **06:08** 改判"通过"。
  - [!] **同一次修复暴露的第二个 §12.1 口子（05:52，已当场堵住）**：`.gitignore:50` 的 `*.log`
        是全局规则，**把 `outputs/evidence/` 里的运行日志一起吞了**——登记表为 A/B 两份日志记了
        sha256，仓库里却从来没有这两个文件，新克隆上做全表复算必失败。这也解释了错源日志
        为什么能放几小时没人发现：**它从不出现在任何 git diff 里**。
        已加 `!/outputs/evidence/**/*.log` 并把两份日志（共 5 478 B）入库。
        **教训**：05:44 那次"65 条记录全表复算 0 不符"是在**工作树**上做的，
        它证明"磁盘 vs 登记表一致"，不证明"**仓库** vs 登记表一致"。
  - [ ] **合并后待做 ⑥ 的范围补充**：登记表校验除 sha256 / bytes 之外，再加一条
        `git ls-files --error-unmatch`——每个登记目标要么在仓库里，要么显式声明"不入库及原因"；
        并把"日志首行时间戳必须等于 meta `created_at`"永久化进 `scripts/24_e_evidence.py`
        （与 `cfg.hash(64)` 同批，因为改 script 24 就要重跑两家族）。
        **进展（2026-10-28 06:37）**：四向核对已有可跑原型 `out/scratch/sweep_registry.py`
        （存在 / sha256 / bytes / **是否入库**），本轮实测**有牙齿**——44 条记录里前 3 向 0 不符、
        第 4 向精确报出 2 条"未入库"，正是本轮刚生成尚未 `git add` 的那两个文件。
        原型里已解决一个会假报的坑：F01 目录级登记表的 `target` 存**绝对 Windows 路径**，
        与 `git ls-files` 的仓库相对路径直接比会全表假报未入库，故先 `norm()` 剥 cwd 前缀。
        **刻意不在本轮提升进 `scripts/`**：F02 正式运行期按 §11.2 收敛开发写盘，
        且新脚本必须配套篡改用例、而全量测试在四分片退出前不能跑（§11.4）⇒ 与 ⑥ 同批做。
- [ ] **合并后待做 ⑦（本轮新增，来自 P2-4 的机制化）**：让**报告表格的每个聚合列自带分母**——
      改 `scripts/26_d03_formal_tables.py` 及后续 G/H 出表脚本，把"格子数/预算档/rep 数/策略数"
      由脚本写进列名，不再依赖写正文的人记得；禁止出现不指明范围的"平均""合计"。
      **理由**：复审找到的 4 项 P2 全是**标注/口径**问题、**无一是算术问题**，
      说明自查对"算得对不对"有效、对"标签说得对不对"有系统性盲点，只能靠结构性约束。
      运行期不改脚本，与 ⑥ 一起做。
- [ ] **合并后待做 ④ 的范围补充**：全量串行测试复跑时，把**日志与 exitcode 落到 `outputs/`（入库）而不是 `out/`**。
      起因：D03 复审明确声明"1 248 项测试 exit=0"**无法验证**——`out/logs/` 不入库，
      仓库里只有断言没有原件，这是 AGENTS §12.1 尚未堵上的口子。
      **进展（2026-10-28 06:37）：落点已打通并验证可用**——`outputs/evidence/test_runs/`，
      靠 `.gitignore:54` 的 `!/outputs/evidence/**/*.log` 覆盖 `.gitignore:50` 的 `*.log`
      （`git ls-files --others --exclude-standard` 已列出该 `.log`）。03:21 那份
      （1 264 项 / exit=0 / 03:21:18–03:27:42）已连同 sidecar 入库并登记（登记表 42 → 44 条）。
      **注意别再用 `outputs/runs/`**：`.gitignore:29` 的 `/outputs/runs/` 使它整目录从不入库
      （`git ls-files outputs/runs` = 0 个文件），F01 复审正是把那里的一份日志误称为"入库那份"。
      本条**仍未关闭**：F02 合并后要在冻结树之外重跑一次全量串行测试，
      并把**那一次**的日志与 exitcode 落到 `outputs/evidence/test_runs/`（03:21 那份描述的是当前绑定树，
      不能替代合并后源码若有变动时的重跑凭据）。

## 收尾交接（2026-10-25 14:40（北京时间））

**A/B/C 通过；D 实现层通过双评审，D02 未完成；正式 R=0（该时点）；E/F/G/H/Z 未开始。**
（**2026-10-26 08:35 更新：正式 R = 1000 已完成，AA 子项通过；见下方 D02 行。本行保留为 14:40 的历史状态**）

- [x] D.1 MDE（176 项，CSV 732×66，含护栏与边界格编码）
- [x] D.2 AA（24 项，pilot R=50/n=1 万）
- [x] D.3 模型+DR（52 项）
- [x] D.4 装载优化（17 项，已切换，字节级等价）
- [x] **D02 的 AA 子项**：四层各 250、合计 1000 跑完。池化 **FPR 0.046、CP [0.0339, 0.0609] 含 0.05**；
      15 格 CP 全含 0.05；SE 校准 0.987–0.995；本 R 功效 0.813/0.918（逐层）、0.960/0.997（合并）。
      文档 `docs/v3_phase_D_aa_formal.md`（机制部分在 `v3_phase_D_aa.md`，两份**不互引数字**）
- [x] C6：SE 校准 + 本 R 实际功效 —— 已完成，写入 formal 文档 §2
- [x] **D02 的负对照**（100 次 × n=20 万，4.37 CPU·h）：购买率 size **0.080**
      （CP [0.0352,0.1516] 含 0.05、二项 p=0.128；点估计偏高须披露）、利润功效 **1.000**
      （真值约 −0.56 元/人 ≈ 4×MDE，应全拒）。产物 `outputs/tables/v3_phase_D_aa_nc20w_L0.csv`
- [x] **D02 第④项（功效格）**：15 格 × 100 次 = **1500 次实测**完成，
      产物 `outputs/tables/v3_phase_D_local_power_formal.csv`（15×62）。
      功效曲线 0.04–0.08 → 0.28–0.33 → 0.78–0.87 → 0.97–1.00 → 1.00；
      `achieved_effect_analytic` 与 target 的相对偏差 **1.96e-15**（构造正确）；
      3 个 `boundary_zero_margin` 格（三层的 `mde100`）已单列，不得计入"可检出"。
      写入 `docs/v3_phase_D_aa_formal.md` §7。**D02 证据齐备，但仍待独立评审**
- [x] DR 设计概率敏感性 + `propensity.primary` 关系 + raw 诊断（C7，`515b75a`）
      ——**主控复核通过**：61 项独立复跑全绿；真接入 `crossfit_dr_ate`、默认仍 `estimated`；
      敏感性表 `outputs/tables/v3_phase_D_models_sensitivity.csv`（R=3、非正式）
- [x] D.3 文档三处修正（C8，`9f3250c`）——**主控复核通过**（含"任何漂移都会报错"的错说法已纠正）
- [x] 工程评审四项（`568c447`）——**主控复核通过**：双装载器改活调用点并反证两条路径各跑一次 /
      PRAGMA 用 PROBE 注入恢复覆盖 / `from_manifest` 读时校验 `source_hashes_before` /
      C 代表库重放 248 产物 0 不一致（4 个 `identical_content` 仅差 `attrs.source_path`）
- [x] 可审计绿灯凭据（`outputs/v3/pytest_handoff/gate.json` + `junit_head*.xml`）
      ——**但 1123 项里 2 项在 AA 并行写盘时因文件锁失败，单独跑均通过**；
      正式绿灯须在 AA 结束后无并发窗口重跑一次。1008/1034 差额已解释：
      `7771d7b`=1098、`ef8f051`=1114、C7 后=1123，旧数字是旧时点
- [ ] 功效格实测拒绝率（C3）：入口已复核（29 项测试绿、20 格全可达、可达域余量 ≥33%），
      正式 15 格（L0/L1/L2，58.3 CPU·h）待 AA 结束后排期；L3 的 5 格按 14:45 裁决不跑
- [ ] 修 `_output_registry_lock` 未捕获 `OSError` 的健壮性缺口（Windows 共享冲突会抛
      `PermissionError` 而非 `ActiveValidationError`）；**AA 运行期间不改 `src/`**
- [ ] E 策略优化 → F 观测闭环 → G 正式重复 → H 长稿 → Z 清理

**纪律（两次踩坑换来的）**：正式重复必须"运行期间源码只读"，用快照或冻结仓库；
绝不允许正式跑与开发写盘并行。

## 后续范围，不可因上下文长度丢失

- [x] B：金额账务舍入、条件真值、L0控制/AA、L3双旋钮积分、独立高精度校验。
- [x] C：全场景五表污染清洗SQL、训练变换、时间成熟、真值隔离、代表DB。
- [ ] D：20pilot实测、MDE/完整AA、四主模型与适用DR、时间模型与PSM目标核验。
- [ ] E：成本和策略、精确求解互证、桶宽/规模扫描、预算超支。
- [ ] F：交叉拟合OPE、配对区间/拒绝规则、独立20万策略验证、最后审计。
- [ ] G：Tier1/Tier2全部正式作业、bootstrap/名单、失败恢复、MC精度/资源。
- [ ] H：12篇核查、三方法图原生PPT/SVG/PNG/清单、结果图、50–100页长稿和比例审计。
- [ ] Z：当前证据逐项验收、v2清理单独commit、最终完整汇报。

## 风险与反思

旧数字不得进入v3；旧README和TODO漂移证明需要机器来源。40–55 CPU小时及8–12小时墙钟仍为未验证估算，完整枚举可能更多格，不能擅自削减。详见docs/v3_决策与反思日志.md。

## B 实施与验收

- [x] 金额/时间、四层概率、L0人工控制、实际订单与审计账集成；首次全套515项测试通过。
- [x] 入口拒绝未支持的机制语义，防止改配置但生成逻辑不变。
- [x] 数值误差传播到元单位；实现稳定求和和坏行按需积分，近零测试通过且保留1e-6门槛及失败路径。
- [x] 独立拒绝抽样/整数账务MC、5000人L0可行域及配对校验落盘。
- [x] 修复后552测试通过，独立B复审通过；22源文件与最终验证hash一致。
- [x] B状态与精度/自然成本解释边界更新；里程碑commit以Git日志为准。A提交为5020c56。

## C 实施清单

- [x] 全73场景实际生成五表、污染/修复血缘、主外键与分币质量校验，完整工程范围通过。
- [x] SQL双窗口/退款/多单/时间快照；四个20万人代表库逐行独立复核，闭端点±1ULP与入库边界负例通过。
- [x] 训练专用预处理、分层/时间拆分、ObservedDataset白名单及隔离，803项全回归通过。
- [x] 工程入口、源哈希清单、封存审计及恢复读取；101清单通过，CLI四格另补验，独立C评审最终通过。
- [x] C-R09按原流重播mask并逐值校验，分别记录选中/改变；C-R10单场景CLI沿用生成器canonical前缀，旧失败证据保留。
- [x] 20功效模板仅继承合同核验通过，actual_n=0；实际机制不能记为C已执行。
- [ ] D：独立20×三粒度pilot后校准20个实际功效机制；禁止静默用原始效应代跑。
- [x] C批准/数字汇总、交接和分钟级维护时间要求已落盘；本轮按用户要求交接，不启动D。


## D 实施（2026-10-25 11:05 起）

- [x] D.0 资源 pilot：4 rep × 三种粒度实测，落 `docs/v3_phase_D_pilot.md` 与 `out/v3_phase_d/`。
- [!] **资源门槛**：外推 ≈1,186 CPU·h，超原估算 22–30 倍；按协议须重商，**未获裁决不启动 G、不擅自减 N/R**。
- [~] D.1 固定 N 反算 MDE 与 20 个功效格校准（子代理 A）。
- [~] D.2 完整 DGP AA 机制（子代理 B）。
- [~] D.3 四主模型 + L1/L3 适用 DR-learner 与统一重复（子代理 C）。
- [~] D.4 `_load_facts` 批量插入优化与 C 回归重绑（子代理 D）。
- [x] D.1 接口冻结（`src/causal_growth/design/v3_power.py`）：`profit_mde` / `profit_power` /
      `purchase_mde` / `purchase_power` / `split_counts` / `holm_per_test_alpha` /
      `multiplier_*` / `design_sample_profile` / `calibrate_power_cell(s)` / `build_mde_rows`。
      唯一口径近似：单侧 α 仍取 0.05（配置无独立单侧 α），须在文档标注。
- [x] D.3 接口冻结（`src/causal_growth/estimate/v3_models.py`）：`prepare_learning_data` /
      `fit_predict` / `Predictions` / `fit_validation_scorer` / `rank_models` / `learning_curve`；
      低层 `crossfit_nuisance` / `aipw_pseudo_outcome` / `crossfit_dr_ate` / `dr_learner_cate` /
      `causal_forest_estimator`。三条硬约束：禁用特征在接口层抛 `FeatureBoundaryError`；
      同一 rep 只调一次 `prepare_learning_data` 并共享 `LearningData`（pairing 载体）；
      L0/L2 调 `dr_learner` 抛 `ModelNotApplicableError`，不得 try/except 吞掉。
- [x] 修掉一个主控引入的副作用：预算覆盖文件原落在 `configs/v3*.yaml` 的源码绑定 glob 内，
      已移至 `configs/budget/repetition_overlay.yaml`；协议 `config_hash` 仍为 `30511a32…`。
- [ ] D.5 主控集成：四域合并、单独评审、D 阶段总验收。
## 下一位agent的启动顺序

1. 先读AGENT_HANDOFF.md最新节、GOAL.md与C批准/独立评审，确认正式R=0；无需凭旧v2正文重新判断当前阶段。
2. 保留七份冻结配置及现有批准哈希；补时间或改状态不能改写冻结文件，时间维护按AGENTS.md§10。
3. 从D开始：20次×三粒度、每次20万人的pilot，实测CPU/墙钟/峰值内存并按完整矩阵重估。超原估算50%须重商，未经回复不得减N/R。
4. D后依次E/F/G/H/Z；F/G精简留存与审计释放、正式重复、长稿和清理均未完成。旧run_all.py仍是v2入口。

## 运行态更新（2026-10-25 16:17，北京时间）

**正式 AA 已改为脱离会话的独立进程**（原为会话后台作业，会话结束即被杀）。

| 项 | 值 |
|---|---|
| 当前进度 | L0/L1/L2 = 49，L3 = 44（目标 250/层） |
| 数据目录 | 正在写 `_r2_det` / `_r3_det`；历史在 `_formal` / `_r2` / `_r3` |
| 合并脚本 | 已含全部根，按 `[block, rep]` 去重，未跑满只写 `_provisional` |
| 状态查询 | `python scripts/18_aa_status.py` |
| 预计完成 | 约 9.4 小时（北京时间约 01:40 前后） |

**未完成（按顺序）**：

- [ ] **L0 的 100 次负对照**（重启时统一带了 `--no-negative-control`，须补）
      命令：`--layers L0 --reps 1 --negative-control-reps 100`，约 3.9 CPU·h
- [ ] 四层跑满后合并池化（确认输出不带 `_provisional`）
- [ ] 无并发写盘窗口单进程串行跑全量 pytest，产出可审计凭据（日志 + exitcode + 起止时间）
- [ ] 池化 FPR + CP + SE 校准写进 `docs/v3_phase_D_aa.md`
- [ ] 以上完成后才可把 GOAL 的 **D02** 标记为通过
- [ ] 15 格功效跑（58.3 CPU·h，L3 的 5 格已裁决不跑）
- [ ] E 策略优化 → F 观测闭环 → G 正式重复 → H 长稿 → Z 清理

**本会话的局限**：轮次预算约 27 秒/轮，256 轮约 34 分钟，而 AA 需 9.4 小时墙钟——
**本会话看不到 AA 跑完**。因此作业已改为不随会话终止的独立进程，交接信息见 `AGENT_HANDOFF.md`。

## 正式 AA 完成（2026-10-26 01:50，北京时间）

- [x] 四层各 250 次、n=20 万全部跑满；**池化 1000 次 FPR = 0.046，CP [0.0339, 0.0609] 含 0.05**
- [x] SE 校准 0.987–0.995（池化 0.995），与独立评审的 1.020 互证
- [x] 全量串行回归 **1123 passed / 0 skipped / 322.76 s / exit 0**，凭据 `outputs/v3/pytest_gate.json`（含日志 SHA256）
- [x] 新增 `docs/v3_phase_D_aa_formal.md`（pilot 与 formal 分开）
- [ ] L0 负对照 100 次：01:47 那次**误用 `n=10000`**（`--n` 未覆盖默认值），产物作废；
      已按 `n=200000` 重跑（`out/v3_phase_d_aa_nc20w/`，约 4.5 CPU·h，预计 10-26 12:50）
- [ ] **20 功效格实测拒绝率仍 pending**（入口已交付，正式 R=100 需 58.3 CPU·h）→ **D02 未通过**
- [ ] 15 格功效正式跑 → E → F → G → H → Z

**D02 判定**：AA 与护栏已达，但负对照未回、功效格未实测，**不得标记通过**。
## 下一步（G01 起的启动清单，2026-10-28 19:32）

- [x] **G01 编排入口已存在**（20:52）：`scripts/34_g_matrix_run.py`（plan/run/merge、分片、`--resume`、快照绑定、provisional 门禁）+ `src/causal_growth/evaluation/v3_g_matrix.py`；A10 工程跑 2 格×R=3 已通过，证据 28 件入册（`outputs/evidence/g_smoke/`）。
- [ ] **G01 启动前门禁（仍未满足）**：① 用户对 R>0 正式运行的开跑确认（全 G 阶段 **207.2 CPU·h** = G 矩阵 162.8 + AA250 44.4，上限 210、余量 2.8；固定 bootstrap 1000 次未计）；② 机器独占 + 内存看护（含模型 rep 峰值 2.9–3.2 GB，4 worker 安全、6 worker 需先释放内存）；③ 快照 `src/ sql/ configs/`（49 文件）并以 `--snapshot` 绑定，运行期只读。
- [x] **AA 臂已补齐并冒烟**（21:00）：`scripts/36_g_aa_run.py` 复用 `v3_aa.run_full_chain_aa`，把四层拆成 17 号可合并的 `<root>/<layer>/aa_repetitions.csv`；正式门禁（批准号 + 快照 + n=200 000）与工程上限（≤5 rep）内置。冒烟 4 层×1 rep×n=2000 exit 0；17 号读到四层、协议指纹一致后按设计以 n_total=2000 拒绝合并。证据 9 件 / 23 065 B（`outputs/evidence/g_aa_smoke/`），顶层登记 70→74；16 项单测 + 导出器 2 例反证（均 exit 2）。
- [ ] **四件待裁决事项已并成一张决策单（21:41）**：`docs/v3_G开跑决策单.md`（A 重训 80/200/800、B 固定 bootstrap 预算范围、C G03 65 格 vs 20 格、D 随机名单 DR 口径、E G01 单独开跑授权）。**21:42 成本口径更正**：固定 bootstrap 全预算的额外构建，冻结 69 格口径是 483 次 ≈17.6 h，Tier2 overlay 执行矩阵 28 格口径是 196 次 ≈7.1 h（合计 214.3，超上限 4.3）；两种口径都写进了决策单 B 节与 `docs/v3_G执行器缺口与设计.md` §1，引用时必须写明矩阵版本。随机名单同理由 800 000 更正为 112 万–224 万个（1.6–3.2 h，估算未实测）。
  **21:45 再更正（更重要）**：协议 `:105` 原文是「**每层** Tier1 代表场景另做 **200** 次」，每层 1 个 core 格 ⇒ 冻结配置的 **800** 才是协议忠实值，任务书/GOAL 的"200"是误读；207.2 h 因此**少算 40 h**。维持 210 上限必须同时改协议与 GOAL，不能只在任务书里写 200。**21:44 可实施性核查**：给 `build_history_dataset` 加 `resample=` 不可行——`ObservedDataset` 只允许 `from_sql_result`/`from_manifest` 构造（`v3_observed.py:124-148`），观测表重抽会破坏 `sql_sha256`/`analysis_sha256` 校验，DGP 也无用户级重抽 API；只能扩 DGP 做真 user bootstrap，或把"重训 bootstrap"改口径为"新 rep 抽样"（MC 重复）。两条都要与次数裁决一起定。
- [~] **其余专项臂（21:02；bootstrap 21:30 部分补齐 → 10-29 00:23 重新定档）**：~~固定 bootstrap 1000~~（主预算已实现，全预算按裁决 B 不做）、~~再训练 bootstrap~~（39 号已实现，待真树 R=1 测成本）、~~G03 的 L2 交叉 / L3 三分支~~（**不再是缺臂**：34 号 `planned_cells()` = Tier1 4 个 core + `configs/budget/tier2_overlay.yaml` 选中的 20 格，`out/g03_plan.log` 实打 **24 格**，与 `docs/v3_tier2_selection.md` 逐格一致；该"缺口"只属于字面 65 格口径，已被 22:26 裁决替代）、~~`random_list_seeds_per_budget`~~（裁决 D 接受 DR 估值，不作为臂）。**结论：真实待办只剩再训练 bootstrap 的正式跑**，G03 可直接用 34 号 plan/run/merge。162.8 h 只含矩阵四臂；AA 44.4 h 已由 36 号承接。
- [ ] **G02 预算口径冲突（21:05 新发现，P1，需用户裁决）**：冻结配置下 `planned_counts` 为 `retraining_bootstrap_jobs=800`（≈53.3 CPU·h）、`fixed_bootstrap_resamples=552 000`、`random_baseline_lists=11 680 000`；任务书 780 h 表只按 200 次重训（13.3 h）计、且完全未计后两项；`repetition_overlay.yaml` 另写 `retraining_bootstrap_total_jobs: 80`（无代码读取）。207.2 h 的合计**只含 200 次重训**，按冻结配置仅重训一项就 +40 h、越过 210 上限。**80 / 200 / 800 的裁决与两个基准臂的成本实测，必须早于 G02 开跑**；合同细节见 `docs/v3_G执行器缺口与设计.md`。
- [x] **F02 的两条未决**：P1-1 逐 rep 预测支出已关闭（21:38 建表 / 21:48 定稿，无需重跑，非 R>0）；P1-3 审计价值已声明移交 D01/G。收尾复核 C1–C6 已全部落地，待窄口径复核确认后改判。
- [x] **D01 独立评审**（2026-10-28 21:14 返回）：PASS WITH CONDITIONS，0 P0 / 6 P1 / 16 P2，报告 `docs/reviews/v3_phase_D01_review.md`。主控复算确认为真：991.387 分行、1,003.1（统一 CPU 口径）、5 模型参照 1,097–1,107 CPU·h、0.961671/0.963144、最差相对差 −13.71%（L3 G1）与 −31.53%（L0 峰值）、8.4 GB 为 2026-10-25 16:10 历史读数。
- [x] **D01 六项 P1 关闭**（21:25 落地；21:28 独立复评 5 CLOSED / 1 PARTIAL；21:35 修完 6 条关闭条件）：① §11.3 给 **1,003–1,107 CPU·h** 区间并标 1,003 为“4 模型暖态下界”；② 5 类未计入计数（fixed bootstrap 552k / 随机名单 11.68M / 预算重采样 7.3M / model_mode 49.3k / learner_fit 64.5k）逐项标“未计入”；③ 并行度改用内存实读与占空比判据、删除“4 进程不可行”，§5/§8/§9/§10.2 的 8.4 GB 全部标历史读数；④ §11.1 改 CPU 口径、127.124→131.221、合计→**1,003.12**；降幅分项按 −182.55 重算（AA −125.3 / IV −27.1 / FL −20.0 / DP −8.2 / DGP −1.9）；⑤ 新增 `scripts/38_export_d01_evidence.py`，导出 10 件 / 25 733 B，`run_manifest.json`（sha `2442a3a0…` 未变）+ `source_binding.json` 登记，顶层 75→76；⑥ “rep 8 饱和”改为“20 rep 内无新高水位”。P2 同步修：ddof、最差相对差、18–28 倍、冷/暖对比、12 行、EXIT=0 非成功证据（L0/L3 改 `REP_EXIT=0`）、MiB/GiB、§11.5 局限节、D03 上界标墙钟/含选模、3 个子计数说明、`random_state`/`budget` 从 configs 派生。
- [ ] **D01 第三轮独立复核（21:28 启动，进行中）**：只核 6 条关闭条件 + N1/N2 算术；报告 `docs/reviews/v3_phase_D01_closeout.md`。PASS 后才可把 GOAL 的 D01 改判“通过”。
- [x] **固定策略 bootstrap 执行器（部分实现，21:30）**：`two_sample_bootstrap_diff`（两臂各自有放回重抽）+ `run_validation_arm(bootstrap_resamples=…)` + `scripts/34 --bootstrap-resamples`；写 `validation/fixed_bootstrap.csv`、逐 rep 5 列、manifest 的 `fixed_bootstrap_{resamples,scope}`；`rep != 0` 拒绝；`status=formal` 且要 bootstrap 时直接拒绝（全预算编排未实现）。7 项单测 + CLI 冒烟（n=400/32 次）通过。**未实现**：代表格 × 8 预算各建一次验证总体（+483 次构建 ≈ 17.6 CPU·h，待裁决）。
- [x] **G03 字面要求与 20 格 overlay 互斥（21:07 冲突登记 → 22:26 用户裁决走法 1 → 2026-10-29 00:22 GOAL 措辞已改，`GOAL.md:29`）**：GOAL G03 要"L2 完整交叉 / L1 与业务敏感性 / L3 三分支"，但 overlay 只跑 L2 2/12、L1 6/25；`dgp.l3.branch` 仅 `fixed_truth`/`joint` 两个取值，"三分支"无定义。字面跑满 65 格 ≈ 335.5 CPU·h（含 AA，不含重训 800 与基准臂），超 210 上限。三条走法（改措辞 / 抬上限 / 砍子集）见 `docs/v3_G执行器缺口与设计.md` §4.4；**裁决前 G03 不得声称满足字面验收**。
- [ ] G01–G04 完成后再排 H01–H05 与 Z01/Z02；H 依赖 G 的正式数值。

> 注意：本轮曾尝试 `scripts/02_run_experiment.py --help` 探测接口，脚本无 argparse，直接执行了 R1 主线并超时被终止；事后 `git status` 干净（产物字节未变）、无残留进程。探测未知脚本前先读源码，不要靠执行。
