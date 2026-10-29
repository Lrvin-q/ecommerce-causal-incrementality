# G 阶段运行注册表（2026-10-29 10:24，北京时间）

> 合成数据 / 已知 DGP。本表对应 GOAL G04「失败重试 / 资源 / 真实进程记录，全入口可恢复」。
> **状态：进行中**——G01 独立评审有条件通过、**条件已全关**（复评代理 10:21 起飞，产物 `docs/reviews/v3_phase_G01_review2.md`）；
> 用户已裁决预算 **A 保持范围**（222.6 h）并**批准 G02 + G03 正式跑**；
> **G02 已于 10:09:04 开跑**（首 b 实测 11 min/格，ETA 19:20–20:30），其后由 `out/g03_chain.sh`
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
- **实测成本**：6 路并发下 132–135 s/rep（4 路 127–129 s/rep），即 6 路比 4 路慢约 5%。
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

## 3. 失败重试与可恢复入口

| 入口 | 重试参数 | 断点续跑 | 备注 |
|---|---|---|---|
| `scripts/34_g_matrix_run.py` | `max_source_retries`（数据作业内） | `--resume` | 网格 / 单格；`plan|run|merge` |
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
- [x] 证据导出 + 顶层登记（`scripts/33`）exit 0（`export.exit=0`、`register_dry.exit=0`、`register.exit=0`；顶层 77 → **89** 条，`total_bytes` 16.92 MB）
- [x] G01 报告 `docs/v3_phase_G01_formal.md` 的每个数字都能从 `outputs/evidence/g01_aa250/` 重建（45 文件 / 1.3 MB / 1 000 行逐 rep）

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
