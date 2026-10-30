# G 阶段运行注册表（2026-10-29 20:12，北京时间）

> 合成数据 / 已知 DGP。本表对应 GOAL G04「失败重试 / 资源 / 真实进程记录，全入口可恢复」。
> **状态：进行中**——G01 已通过（11:00 改判）；**G02 已跑完**（200 b，`merge_exit=0` 17:17:51）；
> **G03 阶段 A 已完成**（24 格，18:37 `fixed_exit=0`），**阶段 B 拆批**：首跑 18:37–19:36 按用户决定叫停并入档，
> **Phase 1（core rep0–99）19:36 起跑**，Phase 2（Tier2 + core ATE 尾巴）待用户另约时间（§2.6）。
> 每次改动都要写清时间与依据；不得用"应该没问题"代替实测记录。

## 1. 运行清单

| 编号 | 运行 | 批准号 | 状态 | 快照 | 起跑（北京时间） | 预计/实际结束 |
|---|---|---|---|---|---|---|
| G01 | AA 臂 4 层 × 250 = 1 000 rep，n=200 000 | `G01-AA250-20261028` | **跑完；评审 PASS WITH CONDITIONS（0 P0/4 P1/9 P2），条件 10:10 全关，待复评确认改判** | `out/g01_snapshot`，49 文件 `526ff53d56a54c75…` | 2026-10-28 22:42:39 | 实际 **2026-10-29 05:15:38（末片）/ 05:15:45（编排器）**，墙钟 6 h 33 m |
| G02 | 重训 200（4 格 × 50）+ 固定 bootstrap 1 000（主预算） | `G02-FORMAL-20261029`（用户 10-29 批准；预算方案 A） | **跑完且已评审通过**：4 格 × 50 b 全满，17:17:51 merge `merge_exit=0`；独立评审 23:08 PASS WITH CONDITIONS → 条件 23:15 修完 → 窄口径复评 23:30 **PASS（9 项全 CLOSED、无新问题）** → 23:32 改判「通过」（含义仅记录准确、断言范围正确，`docs/reviews/v3_phase_G02_recheck.md`） | `out/g02_snapshot`，49 文件 `abaa338a…`（首轮 10:09 失败现场 `f39ec0a3…` 已留档） | 2026-10-29 10:09:04 | 实际 **2026-10-29 17:17:51** |
| G03 | Tier2 20 格 × 30 + 4 core 格（core `R_ate=500`，学习/验证前缀 100） | `G03-FORMAL-20261029`（矩阵）／`G02-FORMAL-20261029`（阶段 A 固定 bootstrap） | **阶段 A 完成**（24 格 × rep0，18:37 `fixed_exit=0`）；**阶段 B 拆批**：Phase 1（core rep0–99）19:36 起跑（10-30 00:00 落 **163/400**），Phase 2 待跑 | `out/g03_snapshot`，49 文件 `6fdaf7bb…` | 阶段 A 18:05:46；Phase 1 19:36:30 | 阶段 A 18:37:03（31 m 17 s）；Phase 1 ETA 10-30 **05:30–07:00**（23:44–00:00 实测 0.56–0.70 rep/min，替代 19:50 的 02:30–03:30） |
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
- **快照（重开后）**：`out/g02_snapshot` 49 文件 `abaa338a…`（10:39 重建；首轮 10:09 用的
  `f39ec0a3…` 已随失败现场留档）。39 号运行前用 `_verify_snapshot` 与真树逐文件比对。
- **日志与产物**：`out/g02_logs/<cell>.log`；每格 `out/g02_retrain/<cell>/repetitions.csv`（逐 b 追加）；
  `run_state.json` 只在该格全部 b 跑完后写出（39 号 397–405 行），属摘要而非断点——
  `run` 的续跑按 `repetitions.csv` 已有 b 跳过（39 号 370–371 行），中途缺 `run_state.json` 属正常。
- **ETA 依据（11:32 用重开后的实测墙钟改写）**：b=0/1 的墙钟为 L0 6.5/6.6 min、L1 9.1/6.9、
  L2 7.1/9.2、L3 9.5 min（4 路并行互相抢核；CPU 386–562 s/b）。按均值 ~7.8 min/b ⇒ 50 b ≈ 6.5 h/格，
  **ETA 16:40–18:40（中心 ~17:10）**。旧的 19:20–20:30 是按 11 min/b 的偏保守外推，作废但保留于 Git 历史。
- **合并/导出门禁预核（11:40，只读）**：`check_counts` 给出 4 格 × 50 = 200（与 overlay 一致）；
  当前逐格表已含 merge 所需全部列，`check_merge_frame` 的两个指纹逐格唯一、b 不重复；
  40 号复算列名（`b_count`/`policy_value_mean`/`policy_value_sd`/`ci95_low`/`ci95_high`/
  `decision_pass_rate`/`guardrail_pass_rate`）与 39 号 summary **完全对应**；
  33 号 `--dirs g01_aa250 f02_formal --dry-run` 91 条一致、幂等、EXIT=0。⇒ 17:10 的 merge → 40 → 33 链路已预核。
- **overlay 身份（11:12 补记，只读核验）**：`configs/budget/g02_bootstrap_overlay.yaml` 1 847 B，
  sha256 `c58d5a905ea75de5f67cb7b5e9e8d3eae85615bb8009d6b49ebb0bb329ec810b`，
  `retraining_bootstrap_total: 200` / `retraining_bootstrap_per_cell: 50`；自 `24582f4`
  （2026-10-29 00:13:54）起未改，`git status --short configs/budget/` 为空。
  **它不在 `pipeline_source_hashes()` 的 glob 内**（`configs/budget/` 是刻意的覆盖目录），
  快照绑定哈希（49 文件）不含它——快照目录虽整树复制了 `configs/`，但 `source_hashes` 只记 v3 集；
  且 39 号不填逐行 `overlay_sha256`（全空，40 号也不读）。
  ⇒ 审阅者核 overlay 只能以本 sha256 为准，空列不得当"未绑定"之外的任何结论。
- **中途体检（11:32，只读）**：10 行（b 0–2）、0 重复、0 空值；`policy_value` 2.2061–3.0176；
  `validation_frame_hash` 4 个值（= 每格 1 个）；`validation_arm_hash` 全局 1 个值——四格
  `n_history = n_validation = 200000`、用户编号同为 0..n−1、臂随机化与格无关，故臂表逐字节相同，
  格间差异由 `validation_frame_hash` 承担；`validation_observed_hash` 10 个值（逐 b 变，符合设计）；
  `guardrail_pass` 全 True；`decision_all_pass` L0 全 False、其余全 True。**不作验收结论**。
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
  成本按 §H.2 为 **159.2 CPU·h**；但 `plan` 的 26.5 h 墙钟未用运行期实测。**11:38 更正**：
  G02 每 rep 墙钟中位 **8.0 min**（4 路并发，24 个间隔），2 600 rep / 6 路 ≈ **58 h**（下界，
  6 路争用可能 60–70 h）；`g03_post` 看护窗口已由 40 h 改为 **120 h**（PID 3883，
  旧 40 h 会在阶段 B 完成前必然超时）。
- **34 号补丁（10:16）**：`--bootstrap-budget-scope` 贯通 CLI → task → `_worker` → `run_cell`；
  `formal + resamples>0 + scope≠primary_0.2` 在 argparse 层直接失败（不新建目录）；
  `run_summary.json` 回写 `bootstrap_resamples`/`bootstrap_budget_scope`。守卫本身未改。
- **模型解析修复（11:14，开跑前冒烟）**：链的 A/B 两段都没给 `--models`，而 34 号 `_worker`
  把 `None` 原样传给 `fit_history_models`——它会试全部模型，L0/L2 的 `dr_learner` 直接抛
  `ModelNotApplicableError`。**阶段 A 一启动就会在 L0 失败并停链**。修法：34 号新增
  `_applicable_models`（`common ∪ additional_by_level[level]`，与 39 号同口径），`--models` 缺省时
  按格解析。冒烟 `out/smoke_g03b`（L0 + L1_heterogeneity_000，n=2000，rep0，1000 次重抽）**EXIT=0**，
  `fixed_bootstrap.csv` 预算 0.2、resamples 1000、点差在 CI 内；41 `--check` 对该半成品
  报缺格并 **EXIT=2**。改动在 `scripts/`，不进 `pipeline_source_hashes`，不影响运行中的 G02。
- **阶段 A 的文件形态**：每格只有 rep0（1/R_ate），但 `status=formal` 且分片计划 rep 全部完成，
  34 号按 `provisional = completed < target_reps or status != "formal"` 写正式 `repetitions.csv`；
  `out/g02_fixed/summaries/` 的汇总表因未覆盖 R_ate 带 `_provisional` 后缀（41 不读）。
  冒烟里的 `_provisional` 是 engineering 状态所致，勿据此推断正式跑。
- **41 号列契约修复（11:20）**：41 的 `check_cell` 原取 `n_total`，而矩阵逐 rep 表只有
  `n / n_treated / n_control`（56 列 schema 无 `n_total`）——首格完整帧会直接 `KeyError`，
  即"跑满 26.5 h 后在导出阶段才炸"。改为取 `n`，加缺列守卫（缺一列即报 `缺列 [...]`），
  并新增 `n_treated + n_control == n` 断言；原有 `rep=0..R-1`、`status/block/tier/n` 唯一、
  矩阵 `resamples==0` 检查全部保留。`tests/test_v3_g41_checks.py` 6 例已绿（含满 R 正例与阶段 A
  真实目录布局的 24 格固定 bootstrap 装载），连同 34 号 2 例共 8 passed。
  此前冒烟没暴露它，是因为根目录无完整帧、`check_cell` 根本没被调用。
- **收尾链静态契约复核（11:33）**：① 40 号 `check_cell/summarize/compare` 用到的列名与
  G02 逐 b **实表表头**逐一对照（24 列）全部存在；39 号 merge 输出的键
  `b_count/policy_value_mean/sd/ci95_*/decision_pass_rate/guardrail_pass_rate/decision_lower_min_min/guardrail_upper_max/total_cpu_seconds`
  与 40 的 `compare` 完全同名。② 34 号阶段 A 的 CLI（`--bootstrap-resamples
  --bootstrap-budget-scope primary_0.2 --rep-start 0 --rep-stop 0 --shard-size 1`）均在 argparse 中；
  "正式跑缺快照必须 `CG_G_ALLOW_LIVE_FORMAL=1`" 的守卫只在 `snapshot is None` 时触发，链传
  `--snapshot` 不受影响；批准号只做非空校验。③ 34 号把 `fixed_bootstrap.csv` 写到
  `<out>/shards/<cell>_s0000/<cell>/rep0/validation/`，键含 41 号所需的
  `resamples/point_diff/ci_low/ci_high`（另有 n_targeted/n_random 等）。④ `g02_post.sh` 逐格等
  `rows==50` 后才 merge，merge 退出码写入 `merge_exit=`，与 `g03_chain.sh` 的 STOP 正则一致。
  结论：本轮未再发现"跑满后才炸"的契约缺口。
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

## 2.6 G03 阶段 B 拆批与 Phase 1 进程记录（2026-10-29 19:36 起）

- **为什么拆**：core 只有 rep0–99 走学习/选模/验证（`tier1_learning_reps/validation_reps=100`），
  rep100–499 只出 ATE。运行期实测 **8.6 min/rep（rep0–99）**、**1.9 min/rep（rep≥100）**，
  所以"2 600 rep × 8 min ≈ 58 h"只是上界；整批一次跑完约 28–35 h。
- **停旧链（19:36）**：`taskkill /T` 杀 18504→22592→18676→4648→6 worker，确认无残留 python；
  `g03_post`（11852）同时停止（否则会等一条已不存在的链 120 h）；半成品归档
  `out/g03_formal_interrupted_20261029_1935`（6 个分片、124 个 `row.json`，未写分片 CSV，不可用于合并）。
- **Phase 1（19:36:30 起）**：core 4 格 × rep0–99，`--shard-size 10` → 40 分片 × 10 rep、6 路，
  `--out-root out/g03_core_prefix`；快照校验 `6fdaf7bb…` 通过。实测资源（19:39）：6 个 worker，
  每个累计 CPU 约 3 020 s / 50 min（接近饱和），单进程 RSS 0.7–2.0 GB。
  **19:50 吞吐实测**：14 min 落 8/400 rep，活跃分片 **6.3 min/rep**（6 路并行，当时全是 `L0_P_main` 分片），
  剩余约 6.9 h ⇒ ETA **10-30 02:30–03:30**；首片预计 20:40 前后写 `repetitions.csv`（片内 10 rep 跑完才写盘）。
- **Phase 2 入口**：`nohup bash scripts/51_g03_phase2.sh`（Tier2 → `out/g03_tier2`；core rep100–499 →
  `out/g03_core_ate`；再建 `out/g03_formal/shards` 复合根并合并）。脚本先查 `phase1.status` 的 OK 行。
  **20:07 加固**：merge 之后逐格核对 `_final` 行数（core 500 / Tier2 30，且必须是正式 `repetitions.csv`），
  不齐写 `ABORT: _final incomplete` 并 exit 9——此前它只打印行数就写 OK，缺口要等 41 号才暴露。
- **断点续跑口径**：34 号 `--resume` 只认未跑完分片的 `repetitions_provisional.csv`，已完成分片写正式
  `repetitions.csv`，在原 out-root 续跑会整片重算；因此一律换新 out-root 分批、最后多根合并去重。
- **10-30 00:00 实测**：163/400 rep（`row.json` 计数），最新写入 00:00 前后；23:44–00:00 两个读数
  154→163，折 0.56 rep/min；19:50 的 6.3 min/rep 是 `L0_P_main` 单层数字，`L1_main` 分片起跑后
  变慢（学习/验证更重），故 ETA 由 02:30–03:30 顺延为 **05:30–07:00**。6 个 worker 仍在满核跑，
  `phase1.log` 无 error/traceback。
- **10-29 23:58 Phase 2 脚本加固**（`scripts/51_g03_phase2.sh`，exec → 提交 `ecb0407`）：
  ① 复合根 `out/g03_formal/shards` 若**残留非空**直接 exit 10——否则 junction 失败回退的
  `cp -r src dst` 会静默套成 `dst/<分片名>/<分片名>`，merge 只少读、不报错；
  ② 建链后逐分片核对 `<分片>/<cell>/repetitions*.csv` 存在，缺则 exit 11（只数顶层条目数抓不到嵌套）。
  两处都只影响 Phase 2 入口，不触碰正在跑的 worker。
- **10-30 00:39 Phase 2 脚本再加固**（exit 12）：41 号要 `out/g03_formal/run_summary.json`
  （`status=formal`、`failures=[]`、`bootstrap_resamples=0`），而 `34 merge` 只写 `merge_report.json`
  且落在 `roots[0]`；不改则 Phase 2 跑完会在导出前判"缺 run_summary.json（未跑完）"。脚本末尾改为
  **合成复合 summary**（`composite=true`、`derived_from` 三份源 summary + sha256、`shard_rows`），
  并从复合根**原始分片**独立核对（24 格各 500/30 行、rep 恰 `0..R-1`、跨分片无重复、无未注册格、
  无 provisional、拒绝覆盖），任一不符 exit 12。**不读 `merge_report`**：junction 回退 `cp -r` 时
  会有多份。7 例夹具演练见反思日志 00:41 条。
- **Phase 2 启动（2026-10-30 17:37:55，用户批准）**：`nohup bash scripts/51_g03_phase2.sh`，bash 包装
  进程 PID 1507；`phase2.log` 记快照绑定 `6fdaf7bb…` 通过、`20 格 / 60 个分片；workers=6 status=formal`；
  60 s 内 6 个分片目录已建、8 个 python 进程在跑。ETA ≈ 16 h（Tier2 ~14 h + core 尾巴 ~2 h）。
  状态文件 `out/g03_logs/phase2.status`（`tier2_exit=` / `core_ate_exit=` / `merge_exit=` /
  `final_check_exit=` / `composite_summary_exit=`，末行 `OK:` 或 `ABORT:`）；进程用
  PowerShell `Get-CimInstance Win32_Process` 查（Git Bash `ps` 看不到 nohup 子进程属正常）。

## 3. 失败重试与可恢复入口

| 入口 | 重试参数 | 断点续跑 | 备注 |
|---|---|---|---|
| `scripts/34_g_matrix_run.py` | `max_source_retries`（数据作业内） | `--resume` | 网格 / 单格；`plan|run|merge`。**限制（2026-10-29 10:26 只读核实）**：`--resume` 只认分片目录里的 `repetitions_provisional.csv`；**已写正式 `repetitions.csv` 的分片会被整片重跑**（正确但浪费）。G04 要么让 `--resume` 也认正式表并校验 `(rep, config_hash)`，要么在文档里明确"已完整分片重跑" |
| `scripts/36_g_aa_run.py` | 同上 | `--resume`（`_resume_source` 按 mtime 取该层最近的完整表） | AA 专用；`plan|run|merge` |
| `scripts/17_merge_aa_layers.py` | 无（纯合并） | 幂等：重跑覆盖同名产物 | 多根合并 + `(block, rep)` 去重 |
| `scripts/37_export_g01_evidence.py` | 无 | 幂等：重跑覆盖证据目录 | `--check` 只复算不写盘 |
| `scripts/39_g_retrain_bootstrap_run.py` | 无（读已落盘逐 b 表） | `run` **按 `repetitions.csv` 已有 b 跳过**（append-only，遇重复 b 抛错）；`merge` 重跑覆盖合并表 | **G02 中断可直接重跑同一条 `run` 命令**（11:48 读码确认）。缺 b 只写 `_provisional`；b 重复/冻结指纹多于 1 值/缺列**硬拒**。`run_state.json` 只在该格循环结束后写，重跑会刷新 |
| `scripts/40_export_g02_evidence.py` | 无 | `--check` 只复算；导出为 staging + 原子换名，旧目录留时间戳备份 | 要求每格 `run_state.json` + 50 行 + b 0–49；不满足即非零退出，**不得绕过** |
| `scripts/41_export_g03_evidence.py` | 无 | 同上 | 缺格/未跑满/非 formal/矩阵 resamples≠0 一律 exit 2（11:20 列契约修复后，见 §2.4） |
| `scripts/33_register_evidence_top.py` | 无 | 幂等：已登记同 sha 跳过 | **先 `--dry-run` 人工复核**；读不懂的记录硬失败（AGENTS §12.7） |
| `scripts/62_g04_tamper_drill.py` | 无（演练可重复） | 幂等：每次重建 `out/scratch/g04_tamper_drill` | **G04 失败→恢复演练**：只用正式矩阵的逐 rep 表副本（含 `run_summary.json`），41 基线 EXIT=0 → 注入重复 rep → 必须 EXIT≠0 且输出指向 rep → 复原 → 重新 EXIT=0；三步任一不符即非零。矩阵未 merge 时以 exit 3 拒绝空演 |
| `out/g02_post.sh` | 整脚本可重跑 | 状态机看 `out/g02_logs/post.status`（`OK:` / `STOP`） | 重跑会重做 40/39 校验，幂等；不跑 33 |
| `out/g03_chain.sh` | 整脚本可重跑 | 状态看 `out/g03_logs/chain.status`（`fixed_exit=` / `g03_exit=` / `OK:`） | **重跑不是追加（11:42 读码确认）**：`run_cell` 的 `existing` 只来自 `resume_from`，而 `--resume` 只认 `repetitions_provisional.csv`；不带 `--resume`（或只有正式表）时 `existing=[]`，本次跑完**用本次 reps 重写** `repetitions.csv`，早先 rep 的 `row.json` 还在但表里没了。修复走"另起根 + 多根 merge"，不要原地重跑（§2.4 预案同） |
| `out/g03_post.sh` | 整脚本可重跑 | 状态看 `out/g03_logs/post.status`（`OK:` / `ABORT` / `TIMEOUT`） | 120 h 窗口（11:38 起，PID 3883）；超时只会漏自动导出，手动按 §6 执行等价 |

**已知事故与修复（G02/G03 相关，均不改冻结配置）**：

| 时间 | 现象 | 根因 | 修复/判据 |
|---|---|---|---|
| 10:15–10:26 | 4 core 格 b=1 全部 `验证帧哈希与 b=0 不同` | 39 断言用 `validation_observed_hash`（含 `issued_action`，逐 b 必变） | 改用 `validation_frame_hash`/`validation_arm_hash`（模型无关）；`tests/test_v3_g02_frozen_frame.py` 6 例（§2.5） |
| 10:46 | 合并必 `SystemExit` 同源缺陷 | 同上，`command_merge` 残留旧断言 | `check_merge_frame`：b 不重 + 两指纹各 1 值 + 缺列硬拒 |
| 11:14 | 阶段 A 一启动 L0 必停链 | 34 `--models` 缺省传 `None` = 试全部模型，L0 的 `dr_learner` 抛 `ModelNotApplicableError` | 按层解析 `common ∪ additional_by_level`；2 例单测 + 冒烟 EXIT=0 |
| 11:20 | 跑满后在导出阶段必 `KeyError: n_total` | 41 取矩阵逐 rep 表不存在的列 | 改取 `n` + 缺列守卫 + `n_treated+n_control==n`；6 例单测 |
| 11:37 | `g03_post` 必在阶段 B 结束前超时 | 40 h 窗口基于未经运行期验证的 26.5 h 估算 | 按 G02 实测 8.0 min/rep 改 120 h（PID 3883）；旧 1952 已停（§2.4） |
| 00:39 | Phase 2 跑完会在 41 号处判"缺 run_summary.json（未跑完）" | 41 要矩阵根 `run_summary.json`；`34 merge` 只写 `merge_report.json` 且落 `roots[0]`，正式矩阵根是临时复合根 | 51 号末尾 exit 12 合成复合 summary（三份源 summary + 原始分片独立核对），7 例夹具演练（§2.6） |
| 17:41 | 49 体检器会永久判 G04 NOT READY | 它等 `chain.status`（19:36 已改 `paused_…`）与 `out/g03_logs/post.status`（已改名 `.stale`）——两个都不再会有 `OK:` | 49 只对 `g02_post`/`phase1`/`phase2` 判门，旧两件降 INFO；`tier2_exit=1` 这类非零退出也判 failure（4 例夹具，见日志 17:41） |
| 11:44 | 40 `--check` 在**完整正确**的格上必报"validation_rep 在 b 间重复" | `check_cell` 把"50 个 b 共用 VALIDATION_REP=0"的**设计**当成重复缺陷（11:33 静态复核只看列名，没看判据） | 改为 `history_rep_id` 查唯一、`validation_rep` 查**恒定**；`tests/test_v3_g02_export_rollback.py` 新增 3 例（正例 / rep 漂移 / history 重复），6 passed；真数据半成品复跑 `--check` 只剩"未跑完"类问题，EXIT=1 |
| 10:18 | 本机 `TZ=Asia/Shanghai date` 输出 UTC | Git Bash 环境 | 链条与状态文件一律用裸 `date`/`zoneinfo` |

**源码只读复核（2026-10-29 11:49，跑中）**：现场重算 `pipeline_source_hashes()` 与
`out/g02_snapshot/snapshot_binding.json` 逐键比对：**49 文件、`source_hashes_sha256=abaa338a0c7705ae…`、
差异 0**；同时 `load_v3_protocol().config_hash = 00723dc2…`（与冻结值一致），`git status --porcelain` 为空。
即 G02 开跑至今未发生 AGENTS §11 的源码绑定漂移。收尾时须再算一次（阶段 B 跑期间同样可能被踩）。

**合并探针（2026-10-29 11:42，真数据半成品）**：把四格 `repetitions.csv` 复制到
`out/scratch/g02_merge_probe/<cell>/` 后跑 `39 … merge`：**EXIT=0**，四格帧校验全过，
输出 `rows=29`、`provisional=true`（8/7/7/7），`b_count` 无 NaN。探针产物
（`outputs/tables/v3_phase_G02_retrain_bootstrap_provisional.{csv,json}`）**已当场删除**，
以免以后被误当证据或与正式同名件混淆；复制件留在 `out/scratch/g02_merge_probe/`。
顺带看到（**只是观察，不作结论**）：`decision_pass_rate` L0=0.000、L1=1.000、L2=0.857（6/7）、L3=1.000，
`guardrail_pass_rate` 四格全 1.000。L0 的 0 与 11:32 体检"L0 `decision_all_pass` 全 False"一致，
写 G02 报告时必须按该格的零效应边界解释，不能当成运行失败。

**运行期取样（2026-10-29 11:41 起；11:46 重启为 PID 4246）**：`out/g04_monitor.sh`（10 min/次，120 h 窗口）
把磁盘余量、四格逐 b 行数、python 进程数与总 RSS + top3、空闲物理内存、三个状态文件末行追加到
`out/g04_logs/monitor.log`。G04 的"真实进程/资源记录"以该日志为运行期原件，不得用事后回忆替代。
**两个自查**：① 首版 `df` 用 1K 块除以 1024 当 GB，实际是 MB（`disk_free_gb=95198`），11:46 改为
`/1024/1024`；② 11:46 样本（G02 四路并发）实测 python 总 RSS **6 937 MB**、top3 **2 023/1 940/1 734 MB**、
空闲内存 **12.3 GB / 30.8 GB**。据此，阶段 A/B 六路并发预计占用 12–19 GB（峰值按 3.2 GB/路），
在 G02 退出后释放约 8 GB 的前提下**可以跑但接近上限**；若 monitor 出现 `mem_free_gb < 3`，
下一轮人工降到 4–5 路（不得改运行中的脚本，须先停链再改）。

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

### 4.2 收尾一致性预检（2026-10-29 19:42，G02 已完成 / G03 Phase 1 运行中）

命令：`PYTHONUTF8=1 ./.venv/Scripts/python.exe out/scratch/g04_closeout_precheck.py
--with-check --with-register --with-claims`，日志 `out/scratch/g04_precheck_1942_full.log`，**EXIT=3**——
唯一失败项是预期的"G03 矩阵未跑完"，其余全绿：
（**20:17 起改引用已提交的 `scripts/49_g04_closeout_precheck.py`**：`out/scratch/` 不入库，
换个 checkout 就没有；49 号与旧版判据相同，另修三处——`ROOT` 由 `parents[2]` 改 `parents[1]`、
`33 --dry-run` 的非零退出码不再被吞、`os.environ` 提到顶部。9 例测试见
`tests/test_g04_closeout_precheck.py`。20:18 在实时树上跑出 **EXIT=2**：
g02 四项全绿、源码 49 文件与 g03 快照逐文件一致、overlay `c58d5a90…` 未变、
`src/ sql/ configs/` git 干净，待完成项 = `chain` / `g03_post` / `g03 _final`。）

| 检查 | 结果 |
|---|---|
| `out/g02_logs/post.status` | `[OK]` 含 `OK: G02 merge 完成 2026-10-29T17:17:51+08:00` |
| G02 四格行数 | `[OK]` L0/L1/L2/L3 = 50/50/50/50 |
| 源码 ↔ 快照 | `[OK]` 49 文件逐文件一致（快照 `6fdaf7bb…`） |
| overlay sha256 | `[OK]` `c58d5a905ea75de5…`（1847 B，运行期未改） |
| 受绑路径 git | `[OK]` `src/ sql/ configs/` 洁净 |
| 42 号 H04 数字门禁 | `[OK]` EXIT=0，19 条 claim 全部回指且与源表复算一致（Tier1 19 / Tier2 0） |
| 40 号 G02 证据导出 `--check` | `[OK]` EXIT=0 |
| 33 号顶层登记 `--dry-run` | `[INFO]` EXIT=2（登记仍需人工复核，非失败） |
| 41 号 G03 证据导出 `--check` | `[FAIL]` EXIT=2：`matrix: 缺 run_summary.json（未跑完）`——预期 |
| `chain.status` / `g03_post.status` | `[WAIT]` 尚无 OK（Phase 1 于 19:36:30 起跑） |

⇒ 结论：**G02 证据链已端到端自洽**（导出/登记/数字门禁全过）；G03 只差时间。Phase 2 收尾后
重跑同一命令，41 转绿、33 由 INFO 转可执行，才算 READY（EXIT=0）。

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

> **论文四门禁不要再手打**：`bash scripts/52_paper_gates.sh [--build]`（20:25 入库）。
> 它按顺序跑 42 数字（先拼 `01→04` 为单文件）、42 摘要、44 引用、43 长稿，每步独立日志与退出码，
> 末行给 PASS/FAIL；反例已验证（缺 `body.md` ⇒ `long_draft rc=3`、整体 EXIT=1）。

```bash
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
# 0) 先看三个状态文件（OK / STOP / VERIFY FAIL / TIMEOUT）
cat out/g02_logs/post.status out/g03_logs/chain.status out/g03_logs/post.status

# 1) G02 证据：先 --check 再导出（staging + 原子换名，旧目录留时间戳备份）
.venv/Scripts/python.exe scripts/40_export_g02_evidence.py --check
.venv/Scripts/python.exe scripts/40_export_g02_evidence.py

# 2) G03 证据：先 --check 再导出（20:11 更正：g03_post 已于 19:36 停，必须手动跑；
#    分批执行后矩阵根就是 41 号的默认根 out/g03_formal（复合根），此处显式写出以防默认值变动）
.venv/Scripts/python.exe scripts/41_export_g03_evidence.py --check --matrix-root out/g03_formal
.venv/Scripts/python.exe scripts/41_export_g03_evidence.py --matrix-root out/g03_formal

# 3) 报告数字（只读）
.venv/Scripts/python.exe out/scratch/g02_report_numbers.py
# G03：24 格 × 4 指标的均值/sd/MC SE 与 mean±1.96·MC_SE，core 与 Tier2 分区，附 CI；
# 未跑满默认 exit 3（中间态加 --allow-partial）；缺格/非 formal/块与注册不符即 exit 2
.venv/Scripts/python.exe scripts/48_g03_matrix_report.py
# 交叉核对（非必须）：out/scratch/g03_report_numbers.py 用 sd/√R 口径算 CI，与 48 号的 MC_SE 口径可互验

# 4) 填 docs/v3_phase_G02_formal.md §3/§4、docs/v3_phase_G03_formal.md §2–§4
# 5) 顶层登记：先 dry-run，人工复核 coverage.json 的 sha/bytes 后再正式执行
.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g02_formal g03_formal --dry-run
.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g02_formal g03_formal

# 6) 翻 GOAL G02/G03 行，刷新 TODO / 决策日志 / AGENT_HANDOFF / 本注册表，提交推送
```

**读退出码的坑（20:12 实测）**：`python x.py | tail -3; echo $?` 拿到的是 `tail` 的退出码，
不是脚本的。本次 41/48 在未跑完状态都打印了失败清单，接管道后却显示 `=0`；
去掉管道（或看 `${PIPESTATUS[0]}`）后分别为 **2 / 2**，与预期一致。

**续跑（任何阶段失败时）**：`--resume` 只救"半途被杀、留下 `repetitions_provisional.csv`"的分片；
已完成分片会整片重跑。正确做法：先 `34 merge` 收已完成 → 缺口另起根重跑 → 多根 `merge` 且 `duplicates=0`。
见 `AGENT_HANDOFF.md` 第 6 条与决策日志 2026-10-29 11:15 条。
