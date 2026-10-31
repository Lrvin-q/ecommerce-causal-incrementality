# G03 修复窄口径复核（P0-1 / P1×3 / P2×3 / P3 关闭核验）

> **复核时间：2026-10-31 19:56（北京时间；`date '+%F %H:%M:%S %z'` 读数 `2026-10-31 19:55:52 +0800`，本机时区即 UTC+8）**。
> 身份：**窄口径独立复核代理**，未参与 2026-10-31 19:44 的上一轮评审，也未参与 `c04dce7` 的修复。
> 被审 commit：`c04dce7 2026-10-31 19:50:04  G03|fix: 分片导出命名塌陷（P0-1）；41 自检 + 33 全表核对；§3.5 指标敏感性披露`。
> 工作树：`git status --short` 对 `scripts/41_export_g03_evidence.py`、`scripts/33_register_evidence_top.py`、
> `docs/v3_phase_G03_formal.md`、`outputs/evidence/` 均无输出（被审对象字节等于 HEAD）；另有的未提交改动属 H01
> （`docs/v3_phase_H01_method_figures.md`、`outputs/figures/h01/*`、`scripts/64_*` 等），不在本次范围。
> 纪律：只读被审文件；**唯一写入本文件**；反例只在 `out/scratch/` 做副本；未跑 34/51/63 等作业、未装包、未跑 pytest、
> 未 `git commit`、未改 `outputs/evidence/`。
> **本复核只看记录准确、断言范围与证据可复算，不判断机制在真实业务是否成立，也不重做全量评审。**

**结论：`PASS WITH CONDITIONS`。**
P0-1 **已真闭**（357 条记录全表逐条 sha/bytes 与磁盘一致，264 个分片原件同名冲突消失，旧塌陷命名 0 条）；
§3/§4 的 96 + 24 个数字经我复算**仍 0 误差**；33 的门禁加强**实测会拦**（两个反例 rc=2，复原 rc=0）。
但仍有 **1 项新 P1**（导出层把"正在写"的 `finalize.log/status` 一并快照，证据包里收尾状态停在 3/5，报告却引用其 OK 行）、
**1 项新 P2**（33 默认全目录 dry-run 因一条 `in_repository:false` 的绝对路径记录误报 rc=2）、
**1 项残留 P2**（§3.5 选模表的"rep0–29"口径对 4 个 core 行不成立）、**1 项未修未说明 P3**（binding `git_commit=null`），
另有 5 项 P3 级措辞/枚举瑕疵。修完 N1/N2 后建议改判"通过"。

---

## §0 范围与未覆盖项

**覆盖**：`scripts/41_export_g03_evidence.py`、`scripts/33_register_evidence_top.py`（读码 + 实测）；
`docs/v3_phase_G03_formal.md` 头部/§2 的 19:44、19:47、19:48 行/§3.0/§3.5/§4 注/§5/§6 第 8 条/§7；
`outputs/evidence/g03_formal/`（coverage.json、per_cell/shards、per_cell/rep0_fixed、logs、runs）；顶层 `outputs/evidence/coverage.json`；
`outputs/tables/v3_g_g_{core,tier2}.csv`；`out/g03_logs/`（只读，用于比对导出副本是否完整）。

**未覆盖（不作判断）**：
1. 业务有效性、估计量统计正确性、覆盖率口径；2. 其余 41 格、H04 claim、长稿；
3. 旧索引"216 条 sha 不符"这一历史数字**已无法原样复算**（旧 48 个塌陷文件在 19:48 重导出时被替换；`out/` 下存在
   4 个 `out/g03_evidence_bak_2026103119*` 目录，我未展开逐条重算）；我只结构性复核了"48 个重名 target"
   （旧索引 323 条 → 107 个唯一 target，`count>1` 的 target 恰 48 个、冗余记录 216 条）与 19:44 评审的实测读数；
4. 19:48 那次 finalize 的完成**只能靠 `out/`**（证据副本被截断，见 N1）；5. 未演练 `51/63` 的续跑。

---

## §1 逐条状态表

评审原文 §9 标题写"5 项 P3"，但实际列了 **P3-1…P3-6 共 6 条**（原文计数少 1）。下表按**条目标签**逐条给状态
（13 个 P0/P1/P2/P3 标签），另加 2 项横切检查（门禁反例、无新伤）。

| # | 条目 | 状态 | 复核证据（我自己复算的） |
|---|---|---|---|
| 1 | **P0-1** 分片导出命名塌陷 | **CLOSED** | `per_cell/shards/` 恰 264 个文件（132 repetitions + 132 telemetry）；`coverage.json` 357 条 target **全局唯一**（357 = 357 个不同 target = 磁盘 357 个文件），逐条 sha256/bytes **357/357 与磁盘一致（0 条不符）**；264 条分片记录 264 个不同 target（旧版 264→48）；旧签名 `<cell>__<cell>__repetitions.csv` **0 条**；导出副本与 `out/` 源文件 sha **264/264 相同** |
| 2 | **P1-1** 头部过期/维护时间 | **CLOSED** | 标题不含"骨架"；全文无"待填"；`维护时间：2026-10-31 19:50`（到分钟）；状态块写"24 格全部跑完…19:33:21…19:36:47" |
| 3 | **P1-2** §5 "留人工复核后再执行" | **CLOSED** | §5 第 424 行改为"顶层登记已于 **2026-10-31 19:36:46** 执行（93 条 / 16 975 748 B…）"；全文 grep"人工复核"**0 命中** |
| 4 | **P1-3** 日志与三份源 summary | **PARTIAL** | 形式达标：`logs/` 有 phase1/2/finalize 的 log+status 与 `g49_full.log`（共 11 件），`runs/` 有三份源 summary；三个 sha256 与 `derived_from` **逐字符相同**（见 §3）。**但** `finalize.log/finalize.status` 是 63 收尾链跑到 3/5 时的快照，缺 4/5、5/5 与 OK 行，而报告 §2 第 74 行引用的正是那行（**N1**） |
| 5 | **P2-1** 等价组披露 | **CLOSED** | 我对 rep0–29 的四指标向量做 sha256 分组，得到 3 组 `ate` 相等、4 组 `ate_paid_purchase_7d`/`ate_any_refund_30d` 相等，**与 §3.5 完全一致**（见 §4.1）；`L3_missing_confounders` vs `L3_fixed_lt000` 的 `max|Δate_test| = 0.1930545175098326 → 0.1931`（rep 25）。瑕疵：§3.5 第 284 行"上述 5 个 L1 格"只点名 4 个（**N4**） |
| 6 | **P2-2** 选模分布/退化策略 | **PARTIAL** | 表格 24 行数字**全部能对上**：20 个 Tier2 行 = rep0–29 计数（逐格一致）；`L0_zero_purchase_effect` = **30/30 `constant`**。**但** 4 个 core 行是 **rep0–99** 计数（`chosen_model` 在 core rep≥100 为 NaN），标题却写"rep0–29"（**N3**） |
| 7 | **P2-3** §3.0 措辞与 rep0 摘要入证 | **CLOSED** | 已改为"30 个 rep 的四个指标与验证数值**逐位相同**…逐 rep 行**并非逐字节相同**"；`per_cell/rep0_fixed/` 两格都在，md5 `69da7f4a93c3d1af006d873358f0d891`、sha256 `4f7a7b790c8a38efe9f637fcfa84d86b084a0f7ccb50ba5f6365f50be34a65b2`（242 B，两文件字节相同），与 §3.0 写的 `69da7f4a…`/`4f7a7b79…` 一致。瑕疵：字段名应为 `validation_freeze_hash` 而非 `freeze_hash`（**N6**） |
| 8 | **P3-1** 93 条 ≠ G03 条数 | **CLOSED** | 顶层 93 条 / 16 975 748 B（我全查 93/93 sha+bytes 相符、target 唯一）；G03 只占 1 条 `g03_snapshot_binding`，§2 第 70 行已写"其中 G03 只占 1 条" |
| 9 | **P3-2** 时间窗与"全 staging" | **CLOSED** | §2 第 68 行时间窗改为 `19:34:07–19:34:26`，已含 41 `--check`（19:34:07）与 62 演练（19:34:09–17）；"全部指向 staging"由 pre-fix 代码证明（`git show 5f7f9fd^:scripts/41…:206-209/289/308`：`_record` 以 staging 为 `dest_root`），并有 19:34:26 的报错旁证 `g03_formal/out/g03_evidence_staging/binding/snapshot_binding.json: 文件缺失` |
| 10 | **P3-3** "4 格 × 100 分片行" | **CLOSED** | 现写"4 格 × 400 rep = 1 600（32 个分片 × 50 行）"；我复算 core 每格 8 个 ATE 分片 × 50 行 = 400，4 格 32 片 = 1 600 |
| 11 | **P3-4** binding `git_commit=null` | **OPEN** | `binding/snapshot_binding.json` 仍 `git_commit: null`；报告全文 grep `commit` **0 命中**——既未修，也未如实说明（不要求修，但本项要求"保留/说明"） |
| 12 | **P3-5** `all_complete=false` 未说明 | **CLOSED** | §4 第 330–331 行已写"属预期：每格只跑 rep 0，而 `R_ate=500`" |
| 13 | **P3-6** overlay 移交 G04 | **CLOSED** | §5 第 422 行"本次保护 = 冻结窗口 + 两文件运行期未改（…记入 G04）" |
| 14 | **门禁加强 + 反例**（任务项 9） | **CLOSED** | 33 对目录级索引**全表**核文件存在/sha/bytes 并拒绝重复 target（`:319-341`）；我自造反例：篡改非身份类 CSV → **rc=2**；复制一条记录造重复 target → **rc=2**；两次复原后 → **rc=0**（§5） |
| 15 | **无新伤**（任务项 10） | **PARTIAL** | 96 行 mean/sd/MC_SE 与两张表 **max|Δ|=0**；§3.1 的 24 行排版 24/24 一致；`41 --check` **RC=0**、`49 --with-check --with-register --with-claims` **RC=0**、顶层 **93 条幂等**。但新发现 N1（P1）与 N2（P2，33 默认调用 rc=2） |

**计数**：13 个条件标签中 **CLOSED 10 / PARTIAL 2（P1-3、P2-2）/ OPEN 1（P3-4）**；
加上 2 项横切检查共 15 行：**CLOSED 11 / PARTIAL 3 / OPEN 1**。

---

## §2 P0-1 全量复算（不是抽样）

```
kind=g03_evidence_coverage cells=24 fixed_cells=24
records=357  unique_targets=357  total_bytes=5 252 227 = Σbytes（每条 1 个不同文件）
kinds: g03_repetitions_shard 132 / g03_telemetry_shard 132 / g03_repetitions_merged 24 /
       g02_fixed_bootstrap_merged 1 / g03_fixed_manifest 24 / g03_fixed_rep0_bootstrap 24 /
       g03_summary 2 / g03_run_summary 2 / g03_source_run_summary 3 / g03_snapshot_binding 1 /
       g03_log 11 / g03_recomputed_summary 1
逐条 ∃文件 + sha256 + bytes：bad = 0
staging 前缀记录 = 0；非 outputs/ 前缀记录 = 0
磁盘（除 coverage.json 自身）文件 357 = 登记 357；未登记 0；登记未落地 0
旧塌陷签名 /([^/]+)__\1__ 命中 = 0
```

- 分片结构：core 每格 **18 个分片**（10 个 prefix 分片各 10 行 + 8 个 ATE 分片各 50 行）→ 500 行、36 个文件；
  Tier2 每格 **3 个分片 × 10 行** → 30 行、6 个文件。合计 72 + 60 = 132 个分片、264 个文件。
- **溯源一致性**（比"记录 vs 导出副本"更强的一层）：264 条分片记录各自的 sha256 与其 `source`（`out/…` 原件）
  逐条相同 → **264/264**，说明导出副本没有串格/串片。
- 命名说明：文件名形如 `L0_P_main__L0_P_main_s0000__repetitions.csv`，第二个 `L0_P_main_` 是分片目录名前缀
  （分片目录 `L0_P_main_s0000` 以格名开头），**不是**旧版的 `run.name == cell` 塌陷；`<cell>__<cell>__<suffix>`
  这种"无分片号"的旧签名已 0 条，且 264 条 target 互不相同。

---

## §3 P1-3：日志与源 summary（形式达标，内容截断）

`outputs/evidence/g03_formal/logs/`：`chain.log`、`chain.status`、`g02_fixed.log`、`g03.log`、`phase1.log`、
`phase1.status`、`phase2.log`、`phase2.status`、`finalize.log`、`finalize.status`、`g49_full.log`（11 件）；
phase1/phase2 四件与 `out/g03_logs/` **逐字节相同**（cmp 通过）。

`runs/` 三份源 summary 的 sha256 与 `matrix_run_summary.json` 的 `derived_from` 及 `out/` 原件**逐字符相同**：

| derived_from | 证据文件 | sha256（三处相同） |
|---|---|---|
| phase1_core_prefix | `runs/phase1_core_prefix_run_summary.json`（3 695 B） | `6a928a88f68545c362f1c6d579d6264b65facf2377806089e386d5e6d3049d97` |
| phase2a_tier2 | `runs/phase2a_tier2_run_summary.json`（8 508 B） | `4d2c53347375bdb6d4a3a3e5c8310e4efbbdfe0a92d8c04998238cf9a6eadead` |
| phase2b_core_ate | `runs/phase2b_core_ate_run_summary.json`（3 141 B） | `6923a32b8db123fb67e00aeaef4fd8fec5a4f5e68e32e242691b54e6f2a0702a` |

**但**（N1）：`finalize.log` 导出副本 **211 行 / 11 258 B**，`out/g03_logs/finalize.log` 是 **239 行 / 12 802 B**；
`finalize.status` 导出副本 **26 B（2 行）**，`out/` 是 **140 B（7 行）**。导出副本停在
`[2026-10-31 19:48:15] 3/5 41 导出证据`，缺 `4/5 33 --dry-run`、`5/5`、`export_exit…register_exit` 与
`OK: G03 finalize 完成 2026-10-31 19:48:27`。

---

## §4 P2 复核

### 4.1 P2-1 等价组（我对 rep0–29 逐 rep 向量做 sha256 分组）

- `ate` 相等：{`L1_cost_prediction_under`, `L1_main`, `L1_mar_double`, `L1_misspec_omit_new_channel`}；
  {`L3_fixed_lt000`, `L3_missing_confounders`}；{`L2_immature_negative_control`, `L2_n200000_p050`}。
- `ate_paid_purchase_7d` 与 `ate_any_refund_30d` 相等（两指标分组相同）：{`L0_P_main`, `L0_Pi_heterogeneous_cost`}；
  {`L1_cost_prediction_under`, `L1_main`, `L1_mar_double`, `L1_misspec_omit_new_channel`, **`L1_signal_weak`**}；
  {`L3_fixed_lt000`, `L3_missing_confounders`}；{`L2_immature_negative_control`, `L2_n200000_p050`}。
- `ate_test` 只有 D1-A 两格相等（其余 22 格各自独立）；`L3_missing_confounders` vs `L3_fixed_lt000` 的
  `max|Δate_test| = 0.1930545175098326`（rep 25：1.5943 vs 1.7874）→ 报告写 **0.1931** 正确。

结论与 §3.5 文字一致；唯一瑕疵是"上述 5 个 L1 格"没有把第 5 个（`L1_signal_weak`）点出来（N4）。

### 4.2 P2-2 选模分布（逐格复算）

`chosen_model` 在 core 格只有 rep0–99 非空（学习/验证 100 rep），Tier2 全 30 行非空。报告表格：

- **20/20 个 Tier2 行**与"rep0–29 计数"逐格相同（例如 `L1_cost_prediction_under` 1/1/9/19/0、
  `L3_overlap_extreme` 11/6/4/5/4、`L2_n100000_p050` 4/4/7/15/0 等）；
- **4 个 core 行**与"rep0–99 计数"相同、与"rep0–29 计数"**不同**：

| 格 | 表格（= rep0–99） | rep0–29 实测 |
|---|---|---|
| `L0_P_main` | 5 / 26 / 31 / 38 / 0 | 3 / 8 / 8 / 11 / 0 |
| `L1_main` | 2 / 6 / 25 / 62 / 5 | 1 / 1 / 10 / 17 / 1 |
| `L2_n200000_p050` | 0 / 1 / 33 / 66 / 0 | 0 / 0 / 5 / 25 / 0 |
| `L3_fixed_lt000` | 8 / 15 / 25 / 45 / 7 | 5 / 7 / 6 / 9 / 3 |

表头"（`chosen_model`，rep0–29）"对 4 个 core 行不成立（且 core 行的 R 列写 500、计数总和 100）。
`L0_zero_purchase_effect` **30/30 `constant`** 已核实。

### 4.3 P2-3 rep0 摘要

两格 `per_cell/rep0_fixed/*__fixed_bootstrap.csv` 各 242 B，md5 `69da7f4a93c3d1af006d873358f0d891`、
sha256 `4f7a7b790c8a38efe9f637fcfa84d86b084a0f7ccb50ba5f6365f50be34a65b2`，两文件**字节相同**；
与 §3.0 的串一致，摘要从此可只用证据包复算。
D1-A 两格 rep0–29 的 56 列中，只有 10 列不同：`cell_id`、`scenario_id`、`tier`、`block`、`preprocessor_hash`、
`split_fingerprint`、`config_hash`、`observed_hash`、`validation_freeze_hash`、`validation_observed_hash`；
四个指标与其余验证数值逐位相同 → "逐位相同、非逐字节相同"的措辞成立（字段名瑕疵见 N6）。

---

## §5 门禁反例演练（我自己造、自己跑；只在 `out/scratch/`）

夹具：`out/scratch/g03_recheck_ev/g03_fixture/`，复制 3 个真实分片 CSV（696/730/724 B）+ 一份 3 条记录的
`coverage.json`；顶层用空副本 `out/scratch/g03_recheck_ev/top_coverage.json`。CSV 均**非身份类**（不匹配
`*binding*/*manifest*/freeze/meta*/decision`）。

```bash
./.venv/Scripts/python.exe scripts/33_register_evidence_top.py \
  --evidence-root out/scratch/g03_recheck_ev \
  --top out/scratch/g03_recheck_ev/top_coverage.json --dirs g03_fixture --dry-run
```

**A) 基线（应 rc=0）**
```
[top-reg] 证据根 out/scratch/g03_recheck_ev；扫描 1 个子目录：g03_fixture
[top-reg] 候选身份类文件 0 个：新增 0，已登记 0
[top-reg] 顶层全表复算一致：0 条
[top-reg] 无新增、无字段补齐，不写盘（幂等）
RC_BASELINE=0
```

**B) 篡改非身份类 CSV（追加 1 字节，应 rc≠0）**
```
[top-reg] 候选校验未过，禁止提升：
  - g03_fixture/L0_Pi_heterogeneous_cost__L0_Pi_heterogeneous_cost_s0000__telemetry.csv:
    磁盘 sha256/bytes 与目录级 coverage.json 不符（目录级 61982ca3118b…/696 vs 磁盘 47a2e059eff6…/697）
RC_TAMPER=2
```

**C) 从 `outputs/evidence/g03_formal/per_cell/shards/` 原件复原（应 rc=0）** → `RC_RESTORED=0`

**D) 复制一条记录造重复 target（sha 完全正确，应 rc≠0）**
```
[top-reg] 候选校验未过，禁止提升：
  - g03_fixture/L0_Pi_heterogeneous_cost__L0_Pi_heterogeneous_cost_s0001__telemetry.csv:
    同一 target 被 2 条记录登记（命名冲突或索引重复）
RC_DUPTARGET=2
```

**E) 索引复原（应 rc=0）** → `RC_RESTORED2=0`

**附加：41 的导出后自检也会拦**（该自检是本轮新增，未随附夹具，属 N9）。我用 importlib 加载 41、
把 `cell_runs` 打成"同一分片返回两次"（复现旧塌陷），直接调 `_write_evidence` 到 `out/scratch/`：
```
SELFCHECK 41 RAISED RuntimeError: 导出目标重名，会互相覆盖：2 个，例
['out/scratch/g03_recheck_export/per_cell/shards/L0_P_main__L0_P_main_s0000__repetitions.csv',
 'out/scratch/g03_recheck_export/per_cell/shards/L0_P_main__L0_P_main_s0000__telemetry.csv']
```
（该实验目录已删除，命令可复现。）

---

## §6 新发现的问题

### N1（P1）导出层把"正在写"的 finalize 日志/状态一并快照，证据包里的收尾证据停在 3/5；报告引用了其中的 OK 行

- 位置：`scripts/63_g03_finalize.sh:35`（3/5 步调用 41 导出）→ `scripts/41_export_g03_evidence.py:408-409`（复制
  `finalize.log/finalize.status`）→ 63 的 `:44`、`:57`（4/5、5/5 才写 `register_dry_run_exit`、`register_exit`）。
  **导出发生在日志闭合之前**，所以证据副本天生是半截。
- 证据：`outputs/evidence/g03_formal/logs/finalize.log` 211 行 / 11 258 B，末行 `[2026-10-31 19:48:15] 3/5 41 导出证据`；
  `out/g03_logs/finalize.log` 239 行 / 12 802 B（含 4/5、5/5、`OK … 19:48:27`）。
  `outputs/evidence/g03_formal/logs/finalize.status` 26 B = `check_exit=0\ndrill_exit=0`；
  `out/g03_logs/finalize.status` 140 B = 6 个 exit + `OK: G03 finalize 完成 2026-10-31 19:48:27`。
- 与报告冲突处：`docs/v3_phase_G03_formal.md:74` 写"`finalize.status` `OK: G03 finalize 完成 2026-10-31 19:48:27`"；
  `:425` 写"19:48 重导出后 33 dry-run rc=0…顶层保持 93 条幂等"——这三句的证据（`register_dry_run_exit`/
  `register_exit`/OK 行）**都不在证据包里**，只在 `out/`（gitignore）。
  同理 `:70`（19:36:47 的 `finalize.status` 末行）也已被 19:48 的运行覆盖，无法从证据复核。
- 影响：不使任何数字作废；但**"只用 `outputs/evidence/` 重建 §2 时间线"**（P1-3 的目的）对 19:48 那次收尾不成立，
  且读者会把停在 3/5 的日志读成"收尾中断"。这也正是本次修复新引入的一层。
- 建议：导出 63 的日志放到收尾链**最后一次**（例如 63 末尾加一个"再次导出日志"步骤，或用 6/6 步重取），
  或让 41 只导出"已闭合"的日志并在 `coverage.json` 里标注快照时刻；再把 §2 的引用改指可复算的文件。

### N2（P2）33 的"全表核 sha/bytes"把 `in_repository:false` 的绝对路径记录误判为"文件缺失"，默认调用（不带 `--dirs`）现在 rc=2

- 位置：`scripts/33_register_evidence_top.py:205-224`（`_rel_name` 对仓外绝对路径 `return p.name`）+
  `:328-341`（新增的"每条记录都要在 `d/rel` 下存在"）。
- 证据：默认 `33 --dry-run`（扫 12 个子目录）：
  ```
  [top-reg] 候选校验未过，禁止提升：
    - f01_ope/policy_masks_long.csv.gz: 文件缺失，目录级索引已过期
  RC_33_ALL_DRYRUN=2
  ```
  但 `outputs/evidence/f01_ope/coverage.json` 的这条记录是
  `kind=f01_masks_derivable, in_repository=false, target=C:\…\out\f01_ope_formal_20261028_0253\policy_masks_long.csv.gz`，
  该文件**真实存在**：5 305 073 B、sha256 `7f7099d21961b12e88a1cf5ba4d1617e39e7f4af967345757a8f31fd1047d541`，与登记值**完全一致**。
- 影响：G03 自己的 `33 --dirs g03_formal`（RC=0）与 49 的 `--dirs g02_formal g03_formal`（RC=0）不受影响；
  但工具**默认用法**与以后任何"提升全部目录"的调用都会被一条合法的旧记录挡住——§12.3 说的"不要为了更严而破坏既有保护机制"。
- 建议：对 `in_repository:false` 或"绝对 target 落在 `out/` 下"的记录，按**原绝对路径**核 sha/bytes（而不是按
  `evidence_dir/<basename>`），或在 `_normalize_dir_files` 里保留 `abs_path` 字段并在校验时优先使用它；
  该分支同样需要反例（应拦"absolute target 的 sha 不符"，不应拦"文件在 out/ 且 sha 正确"）。

### N3（P2）§3.5 选模表标题的"rep0–29"对 4 个 core 行不成立

- 位置：`docs/v3_phase_G03_formal.md:292`（标题）+ `:296`、`:302`、`:310`、`:312`（4 个 core 行，计数总和 100）。
- 证据：见 §4.2 表。数字本身正确（是 rep0–99 的真实计数），只是**口径标签与本文件其余各表的 R=500 / 30 混读**，
  读者若按标题去复算会得到完全不同的一组数。
- 建议：标题改为"（`chosen_model`，Tier2 = rep0–29；core = rep0–99 的学习段）"，或在 4 个 core 行的 R 列标注"100（学习段）"。

### N4（P3）§3.5"上述 5 个 L1 格"只点名 4 个

- 位置：`docs/v3_phase_G03_formal.md:284`；上文（`:280-282`）的 `ate` 等价组只列了 4 个 L1 格，第 5 个是
  `L1_signal_weak`。建议补名，或写成"上述 4 个 L1 格 + `L1_signal_weak`"。

### N5（P3）§5 的 357 条清单逐项相加 = 356，漏列合并的 `fixed_bootstrap.csv`

- 位置：`docs/v3_phase_G03_formal.md:391-394`。264+24+24+24+11+3+2+2+2 = **356**，实际 357；未列出
  `fixed_bootstrap.csv`（`kind=g02_fixed_bootstrap_merged`，24 格合并表，§4 第 329 行提到过）。建议在清单里加一项。

### N6（P3）§3.0 的字段名不精确

- 位置：`docs/v3_phase_G03_formal.md:257` 写 `freeze_hash`；逐 rep 表实际列名是 `validation_freeze_hash`
  （另有 `validation_observed_hash`）。"这类"已兜底，但读者按名 grep 会 0 命中。

### N7（P3）证据包里的 49 日志是修复前（19:37）那一次

- `logs/g49_full.log`（1 550 B，`[TIME] 2026-10-31 19:37:10`，mtime 19:37）内容对应**323 条**旧索引那次全绿；
  报告头部 `:7` 写"19:48 … 后再次全绿"、§5 `:425` 写"19:48 重导出后 33 dry-run rc=0"，证据包里**没有** 19:48 之后的 49 日志。
  我此刻重跑 49 得 **RC=0**（见 §8），所以事实成立，只是"证据包可自证"这一层缺一环。建议在收尾后重跑 49 并重导出该日志。

### N8（P3）`scripts/49` 的 INFO 文案仍说"登记本身仍需人工复核"

- 位置：`scripts/49_g04_closeout_precheck.py:178`。与"19:36:46 已实登记、19:48 后 93 条幂等"冲突（不影响判定，
  但会让人以为尚未登记）。属被审范围外的陈旧文案，建议顺手改。

### N9（P3）新增校验器缺随附反例夹具

- 41 的导出后自检（`:429-448`）与 33 的全表核对（`:319-341`）都是本轮新增；`docs/v3_phase_G03_formal.md:73` 只记了
  33 的一次性反例（旧台账），仓库里没有可重跑的夹具（AGENTS §12.7 要求"新写的校验器必须自带反例夹具"）。
  我已临时造夹具证明两者都会拦（§5），但建议把 `out/scratch/g03_recheck_ev` 这类夹具提进 `tests/` 或 `scripts/`。

---

## §7 结论

**`PASS WITH CONDITIONS`。**

- **P0-1 真闭**：这是本轮修复的核心，我用全表（非抽样）复核通过——357/357 条记录的 sha/bytes 与磁盘一致、
  264 个分片原件互不覆盖且与 `out/` 源逐条同哈希、旧塌陷命名 0 条；96/24 个数字仍 0 误差。
- **关闭条件（下一轮必须满足，未见业务/统计口径争议）**：
  1. **N1**：让证据包里的 `finalize.log/status` 是**闭合**的（收尾后再导出一次），并把报告 `:74/:425` 的引用
     对准证据包内可复算的文件；
  2. **N2**：修 33 对 `in_repository:false` / 仓外绝对路径记录的误判，并补"absolute target sha 不符应拦、
     absolute target sha 正确不应拦"的两条反例；
  3. **N3**：修正 §3.5 选模表的 rep 窗口标注（P2-2 由 PARTIAL 转 CLOSED）；
  4. **P3-4**：在 §5 或 §1 如实写一句"binding 的 `git_commit` 为 null，无法从绑定文件回到 commit"。
- 不阻塞的建议：N4–N9。

---

## §8 实际运行过的命令（可复现）

```bash
# 0) 身份、时间、被审对象状态
git log -2 --oneline ; git show --stat c04dce7
git status --short scripts/33_register_evidence_top.py scripts/41_export_g03_evidence.py \
  docs/v3_phase_G03_formal.md outputs/evidence/g03_formal outputs/evidence/coverage.json
date '+%F %H:%M:%S %z'

# 1) P0-1：357 条全表重算 + 双向索引 + 264 分片 + 旧命名 + 溯源
./.venv/Scripts/python.exe -   # 见正文 §2：逐条 sha256/bytes、target 唯一、磁盘↔登记双向、shards 源/副本比对
ls -1 outputs/evidence/g03_formal/per_cell/shards | wc -l          # 264

# 2) 顶层 93 条 + G03=1 条 + 全表 sha/bytes
./.venv/Scripts/python.exe -   # 93 records / 16 975 748 B / bad=0 / g03 仅 snapshot_binding

# 3) P1-3：日志与 derived_from
cmp out/g03_logs/finalize.log outputs/evidence/g03_formal/logs/finalize.log        # 不同（N1）
cmp out/g03_logs/finalize.status outputs/evidence/g03_formal/logs/finalize.status  # 不同（N1）
sha256sum outputs/evidence/g03_formal/runs/phase{1_core_prefix,2a_tier2,2b_core_ate}_run_summary.json \
          out/g03_core_prefix/run_summary.json out/g03_tier2/run_summary.json out/g03_core_ate/run_summary.json

# 4) 96 行复算 + §3.1 排版 + P2-1 向量哈希分组 + P2-2 chosen_model 计数 + P2-3 摘要
./.venv/Scripts/python.exe -   # 结果见 §2/§4

# 5) 门禁
./.venv/Scripts/python.exe scripts/41_export_g03_evidence.py --check          # RC=0
./.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g03_formal --dry-run   # RC=0，93 条幂等
./.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dry-run      # RC=2（N2）
./.venv/Scripts/python.exe scripts/49_g04_closeout_precheck.py --with-check --with-register --with-claims  # RC=0

# 6) 反例演练（§5）：夹具 + 篡改 + 复原 + 重复 target + 复原
./.venv/Scripts/python.exe scripts/33_register_evidence_top.py \
  --evidence-root out/scratch/g03_recheck_ev \
  --top out/scratch/g03_recheck_ev/top_coverage.json --dirs g03_fixture --dry-run

# 7) 旧台账结构（48 重名 target / 216 冗余记录）与 pre-fix 41 的 staging 目标
git show 5f7f9fd:outputs/evidence/g03_formal/coverage.json > /tmp/old_cov.json
git show 5f7f9fd^:scripts/41_export_g03_evidence.py | grep -n "_record\|staging"
```

**未运行**：34 merge、51 phase2、63 finalize、62 drill 以外的任何作业；pytest；任何 `git commit` / 写 `outputs/`。

---

## §9 与上一轮评审的差异说明

- 上一轮 §9 写"P3（5 项）"但列出 **6 条**（P3-1…P3-6），本轮按 6 条标签逐条核（其中 P3-4 仍 OPEN）。
- 上一轮担心的"216 条 sha 不符"已随重导出消失（本轮实测 **0 条**），且 33 现在会自行发现这类问题（§5 反例）。
- 本轮新增的两条实质问题（N1 日志截断、N2 33 默认调用误报）**都不在上一轮的建议清单里**，是修复本身引入/暴露的。
