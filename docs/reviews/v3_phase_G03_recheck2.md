# G03 窄口径二次复验（N1/N2/N3/P3-4 关闭条件 + N4–N9 + 无新伤）

> **复验时间：2026-10-31 20:10（北京时间；`date '+%F %H:%M:%S %z'` 读数 `2026-10-31 20:10:13 +0800`，本机时区 UTC+8）**。
> 身份：**独立窄口径复验代理**——未参与 19:44 的 G03 评审（`docs/reviews/v3_phase_G03_review.md`）、
> 19:56 的窄复核（`docs/reviews/v3_phase_G03_recheck.md`，下称"前一轮"）、也未参与 20:01 的修复。
> 被验对象：`1b50641 G03|fix: 窄复核 N1/N2/N3/P3-4 闭环；20:01 证据重导出；16 例门禁夹具`（2026-10-31 20:05:12 +0800），
> 其父 `401d4f8`（H01），前一个 G03 提交 `c04dce7`（19:50:04）。
> 纪律：**只读**被验文件；除本文件与 `out/scratch/g03_recheck2_ev*` 夹具外未写任何文件；未跑 41 导出、66、34/49/63、
> 未装包、未跑全量 pytest、未 `git commit`、未改 `outputs/evidence/`。
> **本复验只判"关闭条件是否真闭环 + 证据能否从证据包复算"，不重做全量评审，也不判断机制在真实业务是否成立。**

---

## 结论

**`PASS WITH CONDITIONS`。**

前一轮点名的 4 条关闭条件（N1 / N2 / N3 / P3-4）**全部 CLOSED**，我全部用自己跑出的读数复算，不是读文档采信：

- **N1**：证据包 `logs/finalize.log` **240 行 / 12 900 B**、`logs/finalize.status` **7 行 / 140 B**，
  与 `out/g03_logs/` 同名文件 **`cmp` 逐字节相同**（两侧 sha256 亦相同）；内容含 19:48 那次的 4/5、5/5、
  6 个 exit 与 `OK: G03 finalize 完成 2026-10-31 19:48:27`；`coverage.json` 两条记录的 sha/bytes 与磁盘一致。
- **N2**：`scripts/33` 现在按**原绝对路径**核 `in_repository:false` 记录。我在 `out/scratch/` 自造夹具实测 7 步
  （基线 0 → 篡改绝对路径 2 → 复原 0 → 篡改本地 2 → 复原 0 → 重复 target 2 → 复原 0）；
  真实证据根上**默认全目录** `--dry-run` **RC=0**（12 子目录 / 42 候选全已登记 / 顶层 93 条幂等，跑前跑后 md5 不变）。
- **N3**：§3.5 标题已写「`chosen_model`：Tier2 = rep0–29；core = rep0–99 学习段」；我从 24 个逐 rep 表复算
  `chosen_model`，**24/24 行与文档逐格一致**，4 个 core 行计数总和各 **100**。
- **P3-4**：§5 已如实写明 `git_commit` 为 null 且"无法从 binding 回到 commit"；`binding/snapshot_binding.json`
  未被回填（sha256 与 `c04dce7` 版**完全相同**）。

建议项 N4–N9 亦**全部 CLOSED**（N9 的 `tests/test_v3_evidence_registry_guards.py` 实测 **16 passed**）。

**是否建议改判「通过」：建议改判，但请先处理下面 5 条 P3 记录类瑕疵（或由主负责书面接受）。**
理由：4 条关闭条件与前一轮遗留的 P3-4 都已真闭、无 P0/P1/P2 新伤；剩下的 5 条全是**文字/时间标注**
层面（1 条在新脚本注释里、2 条在新加的 G04 注册表 §2.8 里、2 条在 G03 报告 §2/§5 的措辞里），
不动任何 G03 数字、也不影响证据包复算——但它们正好落在"引用要对准可复算文件"这条 N1 精神的延长线上，
所以我不自封"PASS"，留给主负责一个明确的收尾动作。

---

## §0 范围与未覆盖

**覆盖**：`1b50641` 的全部改动（17 文件）+ 其产出物：`outputs/evidence/g03_formal/`（`coverage.json`、`logs/`、
`per_cell/`、`runs/`、`fixed_bootstrap.csv`、`recomputed_summary.csv`）、顶层 `outputs/evidence/coverage.json`、
`scripts/{33,41,49,66}`、`tests/test_v3_evidence_registry_guards.py`、`docs/v3_phase_G03_formal.md`、
`docs/v3_phase_G_run_registry.md`、`docs/v3_G04_收尾审计.md`、`TODO.md`；`out/g03_logs/`、`out/g04_logs/`、
`out/scratch/g49_full.log`（只读，用于比对导出副本是否完整）。

**未覆盖（不作判断）**：
1. 业务有效性、估计量统计正确性、覆盖率口径（本轮与前一轮一致：未重做科学性评审）；
2. 其余 41 格、H04 claim 登记、长稿并入；
3. **未运行** 34 / 49 / 63 / 66 与 41 的**导出**分支（纪律所限），因此 49/62 的 RC=0、66 的 rc=0 只做
   "日志与产物自洽性"核验，不作独立运行验证（N1 的闭合不依赖于此，见 §2.1）；
4. N2 我只测了"仓外绝对路径"与"相对 target"两类；33 的 `files` 为 **dict** 形态（`f02_n200k_rep0`）与
   `path` 字段形态（`f02_formal`）我没造单独反例，仅由"默认全目录 dry-run RC=0（含这两个目录）"间接覆盖；
5. 时间线中 19:36:47 那次的 `finalize.status` 原样已不可复算（63 每次 `rm -f "$STATUS"`，19:48 覆盖），
   只能从 `logs/finalize.log` 的 19:36:46/19:36:47 行重建（见 §3 P3-4）。

---

## §1 逐条状态表（我自己复算）

| # | 条目 | 状态 | 我的证据（全部自跑） |
|---|---|---|---|
| 1 | **N1** 证据包内 finalize 日志/状态闭合、引用对准 | **CLOSED** | `cmp` 两文件均相同；`finalize.log` 240 行 / 12 900 B / sha `40b23e1d…`，`finalize.status` 7 行 / 140 B / sha `35be47c6…`，与 `out/g03_logs/` 两侧 sha 一致；status 含 `check/drill/export/register_dry_run/report48/register` 6 个 exit + `OK: … 19:48:27`；log 含 19:48 的 `4/5`、`5/5`、`33 实登记`、`收尾链通过 19:48:27`；`coverage.json` 中该两条记录 `bytes=12900/140`、sha 与磁盘相同。§2 第 75 行与 §5 已引证据包内文件（§3 P3-3、P3-4、P3-5 为措辞残留） |
| 2 | **N2** 33 对仓外绝对路径记录误报 | **CLOSED** | 夹具 7 步全符预期（§2.2）；真实根默认全目录 dry-run **RC=0**、12 子目录 / 42 候选全已登记 / 顶层 93 条幂等、跑前跑后 `outputs/evidence/coverage.json` md5 均为 `92a7a529…`（只读） |
| 3 | **N3** §3.5 选模表 rep 窗口标注 | **CLOSED** | 标题第 293 行为「Tier2 = rep0–29；core = rep0–99 学习段」+ 第 295–296 行加了口径注；我从 24 个 `per_cell/*__repetitions.csv` 复算 `chosen_model`，**24/24 行一致**；4 个 core 行总和 5+26+31+38=100 / 2+6+25+62+5=100 / 0+1+33+66=100 / 8+15+25+45+7=100 |
| 4 | **P3-4** binding `git_commit=null` 未说明 | **CLOSED** | `binding/snapshot_binding.json` 仍 `git_commit: null`（`n_files=49`、`source_hashes_sha256 6fdaf7bb…`），文件 sha256 `022099c7…` 与 `git show c04dce7:` **相同**（未回填）；§5 第 444–447 行明写 null、且"引用请用 `source_hashes`，不要假定 `git_commit` 可用" |
| 5 | **N4** §3.5 第 5 个 L1 格未点名 | **CLOSED** | 我对 rep0–29 四指标向量做 sha256 分组：`ate_paid_purchase_7d` / `ate_any_refund_30d` 均有 5 格一组 `{L1_cost_prediction_under, L1_main, L1_mar_double, L1_misspec_omit_new_channel, **L1_signal_weak**}`；文档第 285 行已写「上述 4 个 L1 格 + `L1_signal_weak`（共 5 个 L1 格）」 |
| 6 | **N5** §5 清单合计 356≠357 | **CLOSED** | 文档第 395–399 行逐项相加 264+24+24+24+**1**+11+3+2+2+2 = **357**（新增 fixed_bootstrap.csv 一项），与 `coverage.json` 的 kind 计数（132+132 / 24 / 24 / 24 / 1 / 11 / 3 / 2 / 2 / 1 / 1）逐项吻合 |
| 7 | **N6** 字段名 `freeze_hash` | **CLOSED** | 逐 rep 表实际列名 `validation_freeze_hash`（无裸 `freeze_hash` 列）；文档第 258 行已改；全文 `grep freeze_hash` 仅 1 处且为新名 |
| 8 | **N7** 证据包 49 日志是修复前那次 | **CLOSED** | `logs/g49_full.log` 首行 `[TIME] 2026-10-31 20:01:41`（晚于 19:48）；1 569 B；含 `[VERDICT] READY` 与新 INFO 文案；导出副本与 `out/scratch/g49_full.log` 同 sha（`d22630a4…`） |
| 9 | **N8** 49 的 INFO 文案 | **CLOSED** | `scripts/49:178` 已改「33 --dry-run EXIT=0（全表复算一致；实登记已于 19:48 完成）」，与 `logs/g49_full.log` 内该行一致 |
| 10 | **N9** 新增校验器缺反例夹具 | **CLOSED** | `tests/test_v3_evidence_registry_guards.py` 存在（213 行、16 用例）；`pytest … --basetemp C:/cg_t` → **16 passed / rc=0**（2.02 s）；夹具对 33 的绝对路径"正例 + 反例"各一，41 自检 4 类反例各一 |
| 11 | **无新伤**（横切） | **CLOSED** | `git diff --name-status c04dce7 1b50641 -- outputs/evidence/g03_formal` **只有 4 个文件**：`coverage.json` + 3 个日志；分片/合并表/rep0_fixed/runs **零字节变化**；96 行 `mean/sd/MC_SE` 与我独立复算 **max\|Δ\|=0.0**；24 格 bootstrap（point_diff/SE/CI 上下界/n_targeted/n_random）与 `v3_g03_fixed_bootstrap_summary.csv` **max\|Δ\|=0**；`41 --check` **RC=0**；顶层 **93 条 / 16 975 748 B**（自行求和，逐条 sha/bytes 0 不符） |

**计数**：关闭条件 4/4 CLOSED；建议项 6/6 CLOSED；横切"无新伤" CLOSED。**无 P0/P1/P2 新问题**；
5 条 P3 记录类瑕疵见 §3。

---

## §2 实测证据（命令与输出）

### 2.1 N1：finalize 日志闭合

```
$ cmp out/g03_logs/finalize.log outputs/evidence/g03_formal/logs/finalize.log   → 相同
$ cmp out/g03_logs/finalize.status outputs/evidence/g03_formal/logs/finalize.status → 相同
 240 12900 out/g03_logs/finalize.log
 240 12900 outputs/evidence/g03_formal/logs/finalize.log
  7   140 out/g03_logs/finalize.status
  7   140 outputs/evidence/g03_formal/logs/finalize.status
 40b23e1d7089b06580b929982165af85f003f051d4afb7f73ee6e4b468d05415  （两侧相同）
 35be47c6416fb0f83018d5c7a053c0f097e45836e0419c605196193ea32861ce  （两侧相同）
```

`finalize.status` 全文（140 B，6 个 exit + OK）：

```
check_exit=0 / drill_exit=0 / export_exit=0 / register_dry_run_exit=0 / report48_exit=0 / register_exit=0
OK: G03 finalize 完成 2026-10-31 19:48:27
```
（`scripts/63_g03_finalize.sh` 实读：确实只写这 6 个 exit 键 + OK 行，故"6 个 exit"口径成立。）

`finalize.log` 的 19:48 段含 `[19:48:15] 3/5 41 导出证据`、`[19:48:23] 4/5 33 --dry-run`、
`[19:48:24] 5/5 48 取数`、`[19:48:26] 33 实登记`、`[19:48:27] 收尾链通过`；末行为
`[2026-10-31 20:01:53] 6/6 收尾后重导出（闭合 finalize.log/status；不改状态文件）`（20:01 那次重导出自己留下的标记行）。

`coverage.json` 两条日志记录：`finalize.log bytes=12900 / sha 40b23e1d…`、`finalize.status bytes=140 / sha 35be47c6…`，
与磁盘一致（含在我做的 357 条全表复算里，`bad=0`）。

### 2.2 N2：33 对 `in_repository:false` 绝对路径记录

夹具（`out/scratch/g03_recheck2_ev/`，未碰 `outputs/evidence`）：`evroot/fx/coverage.json` 内 2 条记录——
① 本地相对 target（复制真实分片 564 B）；② 仓外绝对路径 target（`…/abs_source/ext_policy_masks.csv`，`in_repository:false`）；
顶层用空登记表副本。命令固定为：

```bash
./.venv/Scripts/python.exe scripts/33_register_evidence_top.py \
  --evidence-root out/scratch/g03_recheck2_ev/evroot \
  --top out/scratch/g03_recheck2_ev/top_coverage.json --dirs fx --dry-run
```

| 步骤 | 操作 | 结果 |
|---|---|---|
| A | 基线 | `RC_BASELINE=0`（候选 0、顶层 0 条、不写盘） |
| B | 绝对路径文件追加 1 字节 | **`RC_ABS_TAMPER=2`**，报文 `fx/C:\…\ext_policy_masks.csv: 磁盘 sha256/bytes 与目录级 coverage.json 不符（目录级 29ea003c…/564 vs 磁盘 5ec18227…/565）` |
| C | 复原（字节回到备份） | `RC_RESTORED_ABS=0`，`cmp` 确认字节相同 |
| D | 本地 CSV 追加 1 字节 | **`RC_LOCAL_TAMPER=2`**（`…/564 vs …/565`） |
| E | 复原 | `RC_RESTORED_LOCAL=0` |
| F | 复制一条记录（sha 完全正确、同 target） | **`RC_DUP=2`**：`fx/local_telemetry.csv: 同一 target 被 2 条记录登记` |
| G | 复原 coverage.json | `RC_RESTORED2=0`，三个文件 `cmp` 均字节相同 |

真实证据根（只读）：

```
$ ./.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dry-run
[top-reg] 证据根 outputs/evidence；扫描 12 个子目录：d01_pilot, d03_formal, e_evidence_rep0_a,
          e_evidence_rep0_b, f01_ope, f02_formal, f02_n200k_rep0, g01_aa250, g02_formal,
          g03_formal, g_aa_smoke, g_smoke
[top-reg] 候选身份类文件 42 个：新增 0，已登记 42
[top-reg] 顶层全表复算一致：93 条
[top-reg] 无新增、无字段补齐，不写盘（幂等）
RC_33_ALL_DRYRUN=0          # 跑前跑后 outputs/evidence/coverage.json md5 = 92a7a529b09568db0fefc824754a3bbe
```

### 2.3 N3：`chosen_model` 逐格复算（24 格）

> **口径更正（对我自己的任务说明）**：`outputs/tables/v3_g_g_core.csv` 是**汇总表**（16 行 = 4 指标 × 4 格，
> 列为 `cell_id/block/level/tier/metric/R/MC_SE/sd/mean/provisional`），**没有 `chosen_model` 列**。
> 我用真正的逐 rep 表 `outputs/evidence/g03_formal/per_cell/*__repetitions.csv`（24 个）复算。

core 4 格（`chosen_model` 仅 rep0–99 非空）：

| 格 | 行数 | 非空 | rep0–99 | sum | rep0–29（对照，**不是**本表口径） |
|---|---:|---:|---|---:|---|
| `L0_P_main` | 500 | 100 | 5/26/31/38/0 | **100** | 3/8/8/11/0 |
| `L1_main` | 500 | 100 | 2/6/25/62/5 | **100** | 1/1/10/17/1 |
| `L2_n200000_p050` | 500 | 100 | 0/1/33/66/0 | **100** | 0/0/5/25/0 |
| `L3_fixed_lt000` | 500 | 100 | 8/15/25/45/7 | **100** | 5/7/6/9/3 |

Tier2 20 格（rep0–29，每格 30 行、30 非空）：我复算的 20 行与文档第 301–323 行**逐格相同**，
例 `L0_zero_purchase_effect` = 30/0/0/0/0（**30/30 constant**）、`L3_overlap_extreme` = 11/6/4/5/4、
`L2_n30000_p050` = 15/3/4/8/0、`L1_signal_weak` = 3/1/12/12/2。

### 2.4 P3-4：binding 未被回填

```
$ sha256sum outputs/evidence/g03_formal/binding/snapshot_binding.json      → 022099c7…acd147
$ git show c04dce7:outputs/evidence/g03_formal/binding/snapshot_binding.json | sha256sum → 022099c7…acd147
git_commit = None ；n_files = 49 ；source_hashes_sha256 = 6fdaf7bb7ee3c63ef8af7e77eea39c34157af71c7fd9e6d70bcce8ff2d3b60a3
（binding 里唯一 commit 类字段就是 git_commit 本身，值为 null）
```

### 2.5 证据包与数字（无新伤的正面证据）

```
records=357  unique_targets=357  Σbytes(磁盘)=5 254 002 = coverage.json 的 total_bytes
逐条 ∃文件 + sha256 + bytes：bad = 0
kinds: repetitions_shard 132 / telemetry_shard 132 / repetitions_merged 24 / fixed_manifest 24 /
       fixed_rep0_bootstrap 24 / g02_fixed_bootstrap_merged 1 / log 11 / source_run_summary 3 /
       summary 2 / run_summary 2 / snapshot_binding 1 / recomputed_summary 1  （Σ=357）
磁盘(除 coverage.json)357 文件 ↔ 登记 357：双向 0 差；staging 前缀 0；旧塌陷签名 /([^/]+)__\1__ 0 条
per_cell/shards 264 个文件、264 个互不相同名字；264 条分片记录的 sha 与其 source(out/ 原件) 264/264 相同
96 行复算：mean / sd / MC_SE 与 recomputed_summary.csv max|Δ| = 0.0（R 列与逐 rep 行数一致 96/96）
24 格 fixed bootstrap：point_diff / bootstrap_se / ci_low / ci_high / n_targeted / n_random
     与 outputs/tables/v3_g03_fixed_bootstrap_summary.csv max|Δ| = 0；budget 恒 0.2、resamples 恒 1000、rep 恒 0
顶层 outputs/evidence/coverage.json：93 条 / 16 975 748 B（逐条 sha+bytes 0 不符、target 唯一）；G03 只占 1 条
scripts/41_export_g03_evidence.py --check → RC=0（"校验全过"）
git diff --name-status c04dce7 1b50641 -- outputs/evidence/  → 只有 g03_formal/{coverage.json,logs/finalize.log,
      logs/finalize.status,logs/g49_full.log}；顶层 coverage.json 与所有数据文件零改动
```

`coverage.json` 的 diff 内容我逐行看过：**只改** `generated_at`（19:48:23 → 20:02:02）、3 条日志记录的
bytes/sha、`total_bytes`（5 252 227 → 5 254 002 = +1 642 +114 +19，正好等于三个日志的字节增量）。

### 2.6 N9：门禁夹具

```
$ PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest tests/test_v3_evidence_registry_guards.py --basetemp C:/cg_t -v
collected 16 items
tests\test_v3_evidence_registry_guards.py ................  [100%]
============================= 16 passed in 2.02s ==============================   (rc=0)
```
用例覆盖：33 的 clean / 篡改 / 缺文件 / 重复 target / 未登记身份类 / 坏记录 / **仓外绝对路径 sha 正确=通过** /
**仓外绝对路径 sha 错=失败** / 仓外身份类=失败 / CLI 拒写盘 / CLI 默认全目录 rc=0；41 自检 clean / 重名 /
缺文件 / 哈希不符 / 多余文件。这正是前一轮 N2/N9 要求的"两条绝对路径反例 + 两道校验反例"。

---

## §3 我新发现的问题（均 P3，无 P0–P2）

### P3-1 `scripts/66` 头注释的时间 `20:20` 不可能成立

`scripts/66_g03_refresh_evidence_logs.sh:2` 写「G03 收尾后刷新证据包（N1，**2026-10-31 20:20**）」。
但：该文件 mtime `19:59:10`、入库 commit 时间 `20:05:12`、它实际运行是 `20:01:53`（`finalize.log` 6/6 行与
`out/g03_logs/post_finalize_export.status` 均为此）。20:20 晚于文件创建、提交与实际运行，属 AGENTS §10
"时间必须真实到分钟"的记录瑕疵。建议改为 `2026-10-31 20:01`。

### P3-2 G04 注册表 §2.8 的时间标注与其引用日志的内部时钟差约 9–11 分钟

`docs/v3_phase_G_run_registry.md:266` 标题「（**2026-10-31 20:05–20:07**）」，`:271` 引用
`out/g04_logs/closeout_precheck_20261031_2005.log`，`:276` 引用 `tamper_drill_20261031_2007.log`。实测：

```
closeout_precheck_20261031_2005.log  mtime 19:55:55  首行 [TIME] 2026-10-31 19:55:45
tamper_drill_20261031_2007.log       mtime 19:56:09
```
且该 49 日志里的 33 行文案是**修复前**的旧句「（登记本身仍需人工复核）」——即它是 49 在 `19:58:41`
改文案**之前**那一次的输出，不能作为"修复后 49 全绿"的运行时凭证（修复后那一次是 `20:01:41`，
已在证据包 `logs/g49_full.log` 里，含新文案与 `[VERDICT] READY`）。本条在 G03 范围外（G04 文档），
但该 §2.8 是本 commit 新加的，属"新伤"的文档层，故记录。

### P3-3 §5「19:48 与 20:01 两次重导出后 33 dry-run 均 rc=0（含默认全目录扫描）」的历史读法不成立

`docs/v3_phase_G03_formal.md:434-435`。实测：19:48 那次收尾链调用的是
`33 --dry-run --dirs g02_formal g03_formal`（`finalize.log` 该段标题为"扫描 **2 个**子目录"），
**没有**默认全目录扫描；而当时（N2 修好前）默认扫描会 rc=2——这正是前一轮 N2 的实测。
20:01 那次（66 号脚本）**只调 41 导出、根本没调 33**。因此括号里的"含默认全目录扫描"若读作历史事实则不成立；
若读作"现在跑（含默认全目录）也 rc=0"则成立（我实测 RC=0）。建议拆成两句：
"19:48/20:01 两次重导出的收尾链 33 dry-run（`--dirs g02_formal g03_formal`）rc=0；N2 修复后**默认全目录**
扫描亦 rc=0（2026-10-31 20:09 复验，12 子目录 / 42 候选 / 93 条幂等）"。

### P3-4 §2 第 71 行仍引用已不存在的 `finalize.status` 末行（19:36:47）

`docs/v3_phase_G03_formal.md:71`：「`finalize.status` 末行 `OK: G03 finalize 完成 2026-10-31 19:36:47`」。
`63_g03_finalize.sh:12` 每次启动 `rm -f "$STATUS"`，该行已被 19:48 那次覆盖，**证据包里不存在**。
同一事实可从 `logs/finalize.log` 的「`[19:36:46] 33 实登记`（records 92 → 93，16 969 971 → 16 975 748）」
与「`[19:36:47] 收尾链通过`」重建，故只需把主语从 `finalize.status` 改成 `logs/finalize.log`。
这与 N1 是同一类问题（引用指向不可复算的中间态），但前一轮的关闭条件只点名 `:74/:425`，故我判 N1 CLOSED、
本条单列 P3。

### P3-5 20:01 那次重导出自身的退出码只在 `out/`（不进库）

`out/g03_logs/post_finalize_export.{log,status}`（"导出 357 个文件 → … 共 5254002 B"、`post_finalize_export_exit=0`）
被 `.gitignore` 排除；证据包里只有 `finalize.log` 的 6/6 **标记行**和 `coverage.json`（`generated_at 20:02:02`、
357 条 / 5 254 002 B）——后者足以用复算证明"重导出成功且记录自洽"，所以我判 N1 CLOSED；
若追求"连 rc 也可复算"，可把 `post_finalize_export.log` 作为第 12 份日志纳入导出（可选）。
同理，N2 那次"默认全目录 rc=0"目前**仓库内没有任何日志**（`TODO.md` 只是叙述），建议留一份。

### 附：非缺陷的观察（不计入问题）

1. `scripts/33` 新增一条硬失败：「身份类记录在仓外绝对路径 → 判失败」。这是有意的收紧（顶层 target 无法表达仓外文件），
   当前 12 个子目录无一命中（默认 dry-run RC=0），但它是一条**未被 §5 记录的行为变更**，将来若有人把
   binding/manifest 注册到仓外会突然被拒。
2. 我工作期间工作树被**其他进程**改写（20:05 时 `git status` 只有 1 个未跟踪文件；20:10 时出现
   `docs/v3_phase_H01_method_figures.md`、`outputs/figures/h01/*`（4 件）、`scripts/64_*` 的修改与
   `tests/test_h01_figure_verify.py`），属 H01 范围、与 G03 无关；我的所有读操作在 `outputs/evidence/` 下
   前后一致（顶层 md5 `92a7a529…` 未变，g03 目录无写）。但这提醒：AGENTS §11 的"运行期间源码只读"
   需要主负责确认没有与 H01 的开发写盘并行。
3. 本机时钟与文件时间戳存在 ±10 分钟级的不一致（见 P3-1/P3-2，`TODO.md:3` 也自认有过"误标"），
   这不是本 commit 引入的，但会让"到分钟"的时间线难以互相校验，建议后续统一以日志内部 `[TIME]` 为准。

---

## §4 实际运行过的命令（可复现）

```bash
cd "C:/Users/26382/.qoder-cn/worktrees/app/c509bd/营销数分项目"
date '+%F %H:%M:%S %z'
git log -6 --oneline ; git show --stat 1b50641 ; git status --short
git diff --name-status c04dce7 1b50641 -- outputs/evidence/
git show 1b50641 -- scripts/33_register_evidence_top.py scripts/41_export_g03_evidence.py \
  scripts/49_g04_closeout_precheck.py docs/v3_phase_G03_formal.md TODO.md \
  docs/v3_G04_收尾审计.md docs/v3_phase_G_run_registry.md

# N1
cmp out/g03_logs/finalize.log    outputs/evidence/g03_formal/logs/finalize.log
cmp out/g03_logs/finalize.status outputs/evidence/g03_formal/logs/finalize.status
wc -l -c out/g03_logs/finalize.{log,status} outputs/evidence/g03_formal/logs/finalize.{log,status}
sha256sum out/g03_logs/finalize.log out/g03_logs/finalize.status \
          outputs/evidence/g03_formal/logs/finalize.log outputs/evidence/g03_formal/logs/finalize.status
cat outputs/evidence/g03_formal/logs/finalize.status ; tail -5 outputs/evidence/g03_formal/logs/finalize.log
cat scripts/63_g03_finalize.sh ; cat scripts/66_g03_refresh_evidence_logs.sh
cat out/g03_logs/post_finalize_export.log out/g03_logs/post_finalize_export.status

# 357 条全表复算（逐条 sha/bytes、target 唯一、磁盘↔登记双向、分片 264 溯源）
./.venv/Scripts/python.exe -   # 见 §2.5 读数

# N2 夹具（自造自跑；全部在 out/scratch/g03_recheck2_ev/）
./.venv/Scripts/python.exe -   # 建夹具：evroot/fx/{coverage.json,local_telemetry.csv} + abs_source/ext_policy_masks.csv + 空顶层
./.venv/Scripts/python.exe scripts/33_register_evidence_top.py \
  --evidence-root out/scratch/g03_recheck2_ev/evroot \
  --top out/scratch/g03_recheck2_ev/top_coverage.json --dirs fx --dry-run     # A/G: 0
printf 'X' >> out/scratch/g03_recheck2_ev/abs_source/ext_policy_masks.csv      # B: 2
cp out/scratch/g03_recheck2_ev/ext_policy_masks.bak  out/scratch/g03_recheck2_ev/abs_source/ext_policy_masks.csv  # C: 0
printf 'Y' >> out/scratch/g03_recheck2_ev/evroot/fx/local_telemetry.csv        # D: 2
cp out/scratch/g03_recheck2_ev/local_telemetry.bak   out/scratch/g03_recheck2_ev/evroot/fx/local_telemetry.csv    # E: 0
# F：把 coverage.json 追加一条同样的本地记录 → 2；G：cp coverage.bak.json 复原 → 0

# 真实证据根默认全目录（只读）
md5sum outputs/evidence/coverage.json
./.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dry-run          # RC=0
md5sum outputs/evidence/coverage.json                                            # 不变

# N3/N4/数字复算
./.venv/Scripts/python.exe -   # chosen_model 24 格计数；rep0–29 四指标 sha256 分组；96 行 mean/sd/MC_SE；
                               # 24 格 bootstrap 对账；顶层 93 条求和
./.venv/Scripts/python.exe scripts/41_export_g03_evidence.py --check              # RC=0

# P3-4 / N6 / N7
sha256sum outputs/evidence/g03_formal/binding/snapshot_binding.json
git show c04dce7:outputs/evidence/g03_formal/binding/snapshot_binding.json | sha256sum
head -3 outputs/evidence/g03_formal/logs/g49_full.log ; tail -3 outputs/evidence/g03_formal/logs/g49_full.log
./.venv/Scripts/python.exe -c "import pandas as pd;print([c for c in pd.read_csv('outputs/evidence/g03_formal/per_cell/L2_immature_negative_control__repetitions.csv').columns if 'hash' in c])"

# N9
./.venv/Scripts/python.exe -m pytest tests/test_v3_evidence_registry_guards.py --basetemp C:/cg_t -v   # 16 passed
```

**未运行**：41 的导出分支、66、34、49、51/62/63、43/48、全量 pytest、任何 `git commit`、任何对
`outputs/` 与 `outputs/evidence/` 的写操作。

---

## §5 与前两轮的差异

- 前一轮判 `PARTIAL` 的 P1-3（日志截断）与 P2-2（选模表口径）本轮**均已转 CLOSED**；
  前一轮 `OPEN` 的 P3-4 亦 CLOSED。
- 前一轮 N1 建议"导出 63 的日志放到收尾链最后一次"，实现方式改成了**独立 66 号脚本 + 6/6 标记行 + 全量重导出**，
  与我上一轮建议不同但效果等价（证据包内的 log/status 已闭合、且与 `out/` 逐字节相同）；
  代价是"重导出自身的 rc"落在 `out/`（P3-5）。
- 本轮新发现的 5 条全部是 P3 记录/措辞层，没有一条改变 G03 的任何数字、任何 sha、任何门禁结论。
