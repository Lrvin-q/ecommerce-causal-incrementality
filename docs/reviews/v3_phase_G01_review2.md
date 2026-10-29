# Phase G01 13 项条件关闭复评（第二轮独立评审）

> 合成数据 / 已知 DGP。复评时间：**2026-10-29 10:45（北京时间）**。
> 被评对象：`docs/v3_phase_G01_formal.md`（维护时间 2026-10-29 10:10）、证据包 `outputs/evidence/g01_aa250/`、
> 顶层 `outputs/evidence/coverage.json`；对照上一轮 `docs/reviews/v3_phase_G01_review.md`（2026-10-29 06:40，PASS WITH CONDITIONS，0 P0 / 4 P1 / 9 P2）。
> 评审身份：独立评审（非产出者）。**未改** `src/`、`sql/`、`configs/`、`outputs/evidence/**`、`GOAL.md`、`TODO.md`、被评报告；
> 只做只读文件读取与单进程轻量 pandas 复算；**未跑** pytest / `scripts/34|36|37|39` / 任何数据作业（本机 4 个 G02 正式进程在跑）。
> 临时产物只落 `out/review_g01_2/`（`recompute.py`、`recompute_out.json`、`residual_checks.json`）。
> 口径（本评审自定，不读 17/37 的实现来定口径）：拒绝 := `full_<metric>_p_value < 0.05`；
> CP = 等尾 Clopper–Pearson（`scipy.stats.beta.ppf(α/2,k,n−k+1)` / `ppf(1−α/2,k+1,n−k)`，α=0.05）；
> `mc_se=√(p(1−p)/n)`；SE 校准 = `std(diff,ddof=1)/mean(full_*_se)`；**输入只用 `per_rep/` 24 张分片表（1 000 行）**，不读合并表下结论。

---

## §1 结论

**P1 4/4 关闭 / P2 8/9 关闭。判定：不可改判（差 3 组纯文字更正 + 1 处可延后的校验器补丁，修完即可改判，无需重跑）。**

数据层再次**零不符**：本评审只用 24 张分片表独立重算，46/1 000、CP [0.033871, 0.060884]、逐层 14/11/10/11、
mc_se 0.006624、SE 校准 0.987215/0.993645/0.987572/0.995208/0.994819 与报告逐位一致；与 17 号合并表逐格最大绝对差
**6.9389e-18**（只在 `net_profit/POOLED/cp_low`，成因为 `1−0.95` 的浮点 α），与证据内 `recomputed_fpr.csv` 差 0.0。
证据链、runs_summary、§5 五行表、§5.1 逐 rep 连接（both=1 000 / left_only=0 / right_only=0，69 列中 60 列 `max|Δ|=0.0`）
全部复现。**没有数字造假，没有把确定性复现写成独立验证，状态字段未被越权改动**，故无 P0。

未关闭/未清干净的是 3 组**文字** + 1 处代码校验缺口，都不影响 FPR 结论，也不需要重跑：

1. **P2-3（PARTIAL）**：§3 表头写「带 [0.037, 0.065]」、值写 0.82，与表头带一致（0.815105）；但第 45 行称
   「即 merged 表 `detect_power_if_true_0_08` 列」，而 merged 列实际是 **0.813364**（17 号默认带 [0.035, 0.065]）。
   同一节里 0.81 与 0.82 并存，出处的句子为假。
2. **N-2（新 P2）**：§5.1 第 100 行「`outputs/evidence/aa/all_repetitions.csv` 的这两列 1 000 行唯一」为假——
   该文件 1 384 行，`protocol_config_hash` 只有 **1** 个值、`config_hash` 只有 **4** 个值（每层 1 个）。
3. **N-3（新 P2）**：运行注册表 §2/§4 与 `TODO.md` 的 **G01 现状块**仍是旧数（132–135 s/rep、45 文件 / 1.3 MB、77→89 / 16.92 MB），
   且 TODO 现状块仍写「D02 逐 rep 未归档，rep 级无法交叉比对」——正是首轮 P1-4 已证伪的那句。
4. **N-1（新 P2，代码级）**：`scripts/33` 的反向校验（磁盘有、索引无 → 硬失败）没有覆盖新增的 `DIR_EXTRA_IDENTITY`，
   将来的 `runs_summary.json` 漏登记不会被拦住（本次已登记，不影响本批判定）。

**改判路径**：把上述 1–3 的句子按本评审给出的复算值改准（P2-3 一句 + N-2 一句 + N-3 的注册表 3 行/TODO 2 行，约十几分钟），
N-1 的一行校验可延后单独做，
即可把 `GOAL.md:27` 的 G01 行由「未证实」改为「通过」；含义仍**仅限**「合并 1 000 次的 FPR 与 0.05 相容、
逐层只作描述、记录与哈希可复算」，不含「新增 1 000 次独立 AA 证据」，也不含「定向有效」。改判由主负责执行，本评审不动 GOAL。

**结论句：P1 4/4 关闭 / P2 8/9 关闭；不可改判（差 3 组纯文字更正，修完即可改判，无需重跑）。**

---

## §2 P1-1 ～ P1-4 逐条核验

### P1-1　证据包缺「源码绑定 / 运行汇总」两类身份文件 —— **CLOSED**

首轮条件：`snapshot_binding.json`（49 文件 `526ff53d…`）与 12 个 `g_aa_run_summary.json` 必须导出并登记。

本评审实算：

- `outputs/evidence/g01_aa250/binding/snapshot_binding.json`（5 777 B）：`n_files=49`，`git_commit=null`；
  用 `sha256(json.dumps(source_hashes,sort_keys=True,separators=(",",":")))` 从文件自身 49 条哈希**重算 = 526ff53d56a54c756030965486be86194352828fbf7af29cfd4f8c32ca1ab60b**，
  与声明的 `source_hashes_sha256` **逐字符相同**；49 个路径**全部存在**；`git show 7d598fa:<path>` 逐个哈希 **49/49 相同**
  （提交 `7d598fa`，2026-10-29 05:19:30）；当前真树 **48/49**，唯一差异 `src/causal_growth/evaluation/v3_g_matrix.py`
  （绑定值 `fd3ca127…`，现为 `6ec009b6…`，见 §6）。
- `runs/` 12 份 `sNN__g_aa_run_summary.json` + `runs_summary.json`（5 825 B，`dd6a0471…`）已随包导出；
  `grep -rl 526ff53d56a54c75 outputs/evidence/` = **14 个文件**（12 份 run summary + binding + runs_summary），首轮的「0 命中」已消除。
- 目录级 `coverage.json` 59 条中含 12 条 `kind=g01_run_summary`；顶层 91 条中 G01 新增 **14** 条（12 manifest + binding + runs_summary）。
- `git ls-files out` 仍为 **0**（`out/` 不入库），但 `outputs/evidence/g01_aa250/` 下 **60 个文件全部已跟踪**（59 登记 + `coverage.json`）。

判定：**CLOSED**。首轮要求的「可定位、可校验、可登记」三点均满足；`git_commit=null` 由 49 条 source_hashes 自校验 + `7d598fa` 锚点补足。

### P1-2　12/12 分片 manifest 的 `started_at_utc` 实为完成时刻 —— **CLOSED**

首轮条件：不得改写既有证据件，须在索引注明该字段语义，并把权威起止指向 `runs_summary.json`。

本评审实算：

- 逐片比对：12/12 分片 manifest 的 `started_at_utc` 与 `runs/sNN__g_aa_run_summary.json` 的 `finished_at` **秒级相等**
  （s01 `2026-10-28T17:58:43.044054+00:00` = `2026-10-29T01:58:43+08:00`；s02 `21:11:03.149397Z` = `05:11:03+08:00`；…；12/12 成立）。
- 目录级 `coverage.json`：12 条 manifest 记录**逐条**带 note「本 manifest 的 started_at_utc 实为分片**完成**时刻（缺陷，见评审 P1-2）；
  权威起止与 failures 以 `runs/sNN__g_aa_run_summary.json` 为准」；另有 2 条全局 note。
- `runs_summary.json` 带 `started_at_utc_semantics` 字段，正文同义；报告 §5 第 86–87 行显式披露，并把权威起止指到 `runs_summary.json` 与 `runs/`。

判定：**CLOSED**。读者只看证据包即可知道该字段不能当起点用，真起止可从 `runs_summary.json` 重建（22:42:39 → 05:15:38，23 579 s）。

### P1-3　GOAL 判据「计划/成功/失败/有效与哈希」未逐项作答 —— **CLOSED**

首轮条件：把五项集中成表并给出定义。

本评审从证据包逐项重建（报告 §5 第 73–79 行）：

| 判定项 | 本评审批 | 与报告 |
|---|---|---|
| 计划 | `runs_summary.shards[].rows` 合计 **1 000**（83×8 + 84×4），每层 3 片；`declared_reps_per_layer=250` | 一致 |
| 成功 | 1 000 行；12 个 `shards/*.exit` 全 `0`；12 份 `failures=[]`、`all_complete=true` | 一致（14/14 见 N-4） |
| 失败 | `failures_total=0`；`source_retries` 合计 **0**；`file_lock_retries` 合计 **0**（1 000 行）；`retry_attempt_dirs` 全空 | 一致 |
| 有效 | `block=true_aa` 1 000/1 000；`n_total` 唯一 {200 000}；full 人群 `n_treated` **99 407–100 768**；test 人群 **29 693–30 372**；主键（block/level/rep/run_id）0 个 NaN | 一致 |
| 哈希 | protocol `00723dc2…`（`coverage_check.json`）；merged CSV 2 779 B `2c6d6e91…`；binding `526ff53d…`；`v3_aa.py` `95edd77c…`（在 binding 的 source_hashes 内） | 一致 |

判定：**CLOSED**。五项均可从包内重建；唯一不能整表重建的是「14/14 exit」里的 merge/verify 两个（见 N-4，P3）。

### P1-4　§5.1「D02 逐 rep 未归档、无法在 rep 级比对」为假 —— **CLOSED**

首轮条件：把「无法比对」改成真实的逐 rep 比对。

本评审自写 join（`outputs/evidence/aa/all_repetitions.csv` 1 384 行 → 按 `(level,rep)` 去重 1 000 行，sha `77a2a386…`，1 650 065 B；
G01 1 000 行来自 24 张分片表）：

- **both = 1 000 / left_only = 0 / right_only = 0**；`run_id` 1 000/1 000 相同。
- 69 个可比数值/布尔列中 **60 列 max|Δ| = 0.0**；9 列非零，全部是运行期计量：
  `dgp_cpu_s` 1.484、`dgp_wall_s` 1.468、`pipeline_cpu_s` 60.203、`pipeline_wall_s` 60.375、`itt_cpu_s` 0.047、
  `itt_wall_s` 0.037、`total_cpu_s` 60.359、`total_wall_s` 60.535、`file_lock_retries` 1.0（最大差 1 次）。
- 字符串列：`source_label/block/scenario_id/run_id/stream_prefix` 全同；`config_hash`、`protocol_config_hash` **1 000/1 000 不同**
  （D02 协议 `30511a32…`，G01 `00723dc2…`；两侧 config_hash 各 4 个值，见 P2-7）。

判定：**CLOSED**。报告第 90–98 行的写法与实测一致；「逐字节相同」限定在统计列上成立，且 9 个运行期列已如实标出。

---

## §3 P2-1 ～ P2-9 逐条核验

### P2-1　单 rep 成本「132–137 s」 —— **CLOSED**

本评审对 1 000 行 `total_cpu_s` 实算：min **128.672**、p5 **134.324**、p25 136.031、中位 **136.594**、p75 137.332、
p95 **141.815**、max **181.375**（L0/rep26，`pipeline_cpu_s=180.969`）；落在 [132,137] 的占 **67.4%**；
合计 **137 931.21875 CPU·s = 38.3142 CPU·h**；`total_wall_s` 中位 138.301。
报告第 26 行改为「中位 136.6 s、p5–p95 134.3–141.8、极值 128.7–181.4、67.4%、38.31 CPU·h」，逐项一致。

### P2-2　「6 路并行峰值 10.69 GB」不是本次实跑遥测 —— **CLOSED**

报告第 27 行已把 10.69 GB 标为「开跑前 6 路**压力测试**峰值（**不是**本次实跑遥测，来源见运行注册表 §2）」，
并补「实跑期 23:00 健康检查：12 进程合计 3.82 GB、单进程峰值 815 MB、空闲 14.76 GB」。
核对注册表：第 26 行确为压力测试 10.69 GB / 单进程最大 2 003 MB；第 31 行确为 23:00 的 3.82 GB / 815 MB / 14.76 GB。归因正确。

### P2-3　§3「解析功效」的定义、带与出处 —— **PARTIAL**

本评审独立实现 `Φ((lo−p)/se) + 1−Φ((hi−p)/se)`，`se=√(p(1−p)/R)`（与 `scripts/17_merge_aa_layers.py:54-61` 同式）：

| 带 | R=250 | R=1 000 |
|---|---|---|
| [0.035, 0.065]（17 号默认，merged 列实际值） | **0.813364** | **0.959807** |
| [0.037, 0.065]（GOAL 带，报告表头声明） | **0.815105** | **0.959807** |

- 表头写 GOAL 带、值写 0.82/0.96 ⇒ **与表头带一致**（0.815105→0.82；0.959807→0.96）。首轮「用了错带、无定义」两点已解决。
- **未解决**：第 45 行「『解析功效』即 merged 表 `detect_power_if_true_0_08` 列」为假——merged 表该列是 **0.813364**（0.81）。
  第三方拿 merged CSV 对照本表会得到 0.813364 ≠ 0.82；第 47 行虽已解释两种带，但第 45 行的「即」仍把两个不同带的值说成同一个。
- 改法（一行）：「与 merged 表 `detect_power_if_true_0_08` 同一定义；merged 列用 17 号默认带 [0.035,0.065]，值为 0.813364；
  本表按 GOAL 带 [0.037,0.065] 重算为 0.815105，故显示 0.82。」

### P2-4　§3/§4 未写 `population=full` —— **CLOSED**

报告第 34–35 行表头写明「主口径 `full_net_profit_*`（随机分配的全部用户，R1）」，并给 test 列对照 **45/1 000 [0.033010, 0.059753]**。
本评审实算 test 列：45/1 000 = 0.0450，CP **[0.0330096, 0.0597528]**，一致。

### P2-5　两处体量 —— **CLOSED**

- 目录级：登记 **59** 条；磁盘 **60**（多出的只有 `coverage.json`）；字节和 **1 275 048 B**（= 磁盘总和 1 299 121 − 索引 24 073）；sha256/bytes **0 不符、0 缺失**。
- 顶层：**91** 条，`total_bytes` **16 964 194** = 逐条 bytes 之和；**0 不符、0 缺失**；末条 `registry_repairs` 为 10:06 的 89→91（新增 binding + runs_summary，回填 12 个 manifest）；首轮记录的 77→89 为 05:16 那次。
报告第 81、84 行与上述逐个数字一致。（注册表/TODO 的旧数见 N-3。）

### P2-6　把四项断言都归给 `verify.log` —— **CLOSED**

- `verify.log` 实读：逐层 `rows=250 unique_reps=250 shards=[…]`（L0 s01/s03/s05 …L3 s08/s10/s12），只有这一项。
- `coverage_check.json` 实读：`total_true_aa_rows=1000`、`per_layer.*.n_total=[200000]`、`protocol_config_hash=[00723dc2…]`、
  `problems=[]`、`passed=true`；`alpha` 确实**未**单列，而逐 rep 表 `alpha` 唯一值 {0.05}。
报告第 66–68 行的归因与上述一致。

### P2-7　「指纹变了、数据没变」未写出 —— **CLOSED**

报告第 99–103 行已明写「协议指纹变了、数据逐比特没变」。本评审实算：
D02 `protocol_config_hash=30511a32…`（全列 **1** 个值）；D02 `config_hash` **4** 个值
（L0 `1d0d83c5…` / L1 `7ab83d75…` / L2 `d5266240…` / L3 `2671bded…`）；
G01 协议 `00723dc2…`（1 个值）、`config_hash` 4 个值（`a0eb214e…` / `8a36a14b…` / `c07d2f02…` / `59958e1d…`）。
指纹确实变了、统计列确实逐比特相同 ⇒ 结论成立。
**但同一句的括号证据为假**（「这两列 1 000 行唯一」），见 N-2。

### P2-8　§7 「⇒ 支持 FPR≈0.05」的自证口吻 —— **CLOSED**

报告 §7 现为条件句：「若按该口径，则本 CP 包含 0.05 ⇒ 与『FPR≈0.05』相容；是否改判由独立复评确认后、由主负责执行（本报告不自证通过）」，
并保留「不表示定向有效」「不表示新增独立证据」两条边界。无自证通过。

### P2-9　补 D02 协议号 —— **CLOSED**

报告第 99 行给出 `30511a32bcee9db5…`，并指明证据包内可查（`all_repetitions.csv`）。本评审在该文件实读该值（全列 1 个）。
首轮此条自身引用的 `out/v3_phase_d_aa_formal_r2_det/L0/aa_manifest.json` **在本 worktree 不存在**（`out/v3_phase_d_aa_formal*` 均不存在），
报告改引包内文件、方向正确（见 §4 N-8）。

---

## §4 新发现

### N-1（P2，代码级）`scripts/33` 的反向校验没有覆盖 `DIR_EXTRA_IDENTITY`

- 正向：`DIR_EXTRA_IDENTITY = {"g01_aa250": {"runs_summary.json": "g01_runs_summary"}}` 让 `runs_summary.json` 能被登记。
- 反向（磁盘有、索引无 → 硬失败）：`on_disk` 过滤只用 `_is_identity(rel)`（`IDENTITY_PATTERNS = *binding*.json / *manifest*.json /
  freeze.json / meta*.json / decision.json`），**不认** `runs_summary.json`。即：删掉索引里的这条记录，校验仍 exit 0。
- 影响：本次已登记，不影响本批判定；但它违反 AGENTS §12.7「双向索引校验必须硬失败」的精神，属校验器缺口。建议反向过滤也走 `_is_identity` 的扩展版。

### N-2（P2）§5.1「这两列 1 000 行唯一」为假

- 原文（第 100 行）：「证据包内可查：`outputs/evidence/aa/all_repetitions.csv` 的这两列 1 000 行唯一」。
- 实读：该文件 **1 384 行**（去重后 1 000）；`protocol_config_hash` 唯一值 **1** 个（`30511a32…`）；`config_hash` 唯一值 **4** 个（每层 1 个）。
  「唯一」对两列都不成立（对 protocol 列是「恒定」，不是「唯一」）。
- 附带：报告第 100 行「本次为 `00723dc2…` / `a0eb214e…`」只给了 L0 的 config_hash；G01 实为 4 个（见 P2-7）。
- 建议改为：「去重后 1 000 行；`protocol_config_hash` 全列恒为 `30511a32…`，`config_hash` 每层一个共 4 个（L0 `1d0d83c5…`）；
  本次对应 `00723dc2…` 与 4 个 config_hash（L0 `a0eb214e…`）」。定级 P2：证据事实陈述错误，不影响 FPR 结论。

### N-3（P2）注册表与 TODO 的 G01 现状块仍是旧数，且保留已被推翻的结论

- `docs/v3_phase_G_run_registry.md:25`：「6 路并发下 132–135 s/rep」→ 实测中位 136.594、p5–p95 134.324–141.815。
- `docs/v3_phase_G_run_registry.md:120`：「顶层 77 → **89** 条，`total_bytes` 16.92 MB」→ 现为 **91** 条 / **16 964 194 B**。
- `docs/v3_phase_G_run_registry.md:121`：「45 文件 / 1.3 MB」→ 现为 **59** 文件 / **1 275 048 B**。
- `TODO.md:167`（「**G01 正式结果**」现状块）：「45 文件 / 1.3 MB … 顶层登记 77→**89** 条」→ 同上。
- `TODO.md:170`（同一现状块）：「D02 逐 rep 未归档，rep 级无法交叉比对」→ 与报告 §5.1 及证据包**直接矛盾**，是首轮 P1-4 已证伪的原句。
- 这正是 AGENTS §12.4「改一处必须 grep 全文」要求清掉的残留；报告正文已干净，旧数集中在注册表与 TODO。定级 P2（文档一致性，不改数据结论，但改判前应清）。

### N-4（P3）§5「成功」行的「14/14 exit」只有 12 个在包内

- 包内 `shards/` 只有 s01–s12 共 **12** 个 `.exit`（全 `0`）；`merge.exit`、`verify.exit` 在 `out/g01_logs/`（未导出，`out/` 不入库）。
- 实质可由包内 `logs/merge.log`（写出 merged 表）与 `logs/verify.log`（逐层 rows=250 unique_reps=250）+ `coverage_check.json`（`passed=true`）佐证。
- 建议把「14/14」改成「12 个分片 exit 0 + merge/verify 见 `logs/`」，或把两个 exit 一并导出。定级 P3。

### N-5（P3）`scripts/37` 的 `export()` 在双重故障/陈旧备份路径上仍可半写并掩盖原异常

静态阅读 `scripts/37_export_g01_evidence.py:156-176`：新逻辑「先清陈旧 backup → 把旧产物 rename 成 backup → 写 → 删 backup」比旧的「先 rmtree 再写」好，
但首次导出失败（`DEST` 原本不存在、无 backup 可回滚）时，异常处理里的 `backup.rename(DEST)` 会抛 `FileNotFoundError`，**掩盖原始异常**；
若回滚 rename 本身再失败，则半写目录保留。属工程健壮性，不影响本次产物（本次导出成功且 0 不符）。定级 P3。

### N-6（P3）GOAL 的「91% / 60%」与 §3 的 0.82/0.96 未对账

GOAL G01 行写「检出 FPR≥0.09 的把握约 91%（合并），FPR≥0.08 约 60%」；报告 §3 列是「真值 0.08、带 [0.037,0.065] 的带外概率」0.82/0.96。
两者是不同量（0.09 vs 0.08；检出功效 vs 带外概率），报告未给映射。本评审试算：merged 列在真值 0.09 时为 0.917585（≈92%，与「91%」接近），
而 0.08 的常规双侧 z 检验功效约 0.59（与「60%」接近）——即 GOAL 的两个数很可能来自两套不同口径。
建议报告加一句「本列不等于 GOAL 的 91%/60%」，避免读者把 0.96 当成「检出 0.08 的把握 96%」。定级 P3。

### N-7（P3，存量）顶层索引覆盖 91/231，14 个文件无任何索引

`outputs/evidence/` 磁盘 **231** 个文件，顶层登记 **91**；未登记 140 个中，126 个落在自带 `coverage.json` 的子目录（d01/d03/g01/g_smoke 等），
**14 个无任何索引**：`outputs/evidence/coverage.json` 自身、D02 遗留 9 个（`d02_aa_phase_d_20261027/*`）、
`test_runs/pytest_*` 4 个。多为存量、且非身份类文件，不影响 G01；按双向校验要求在此列出。定级 P3。

### N-8（备注）首轮评审 P2-9 自身引用了不存在的路径

首轮 P2-9 写「来自 `out/v3_phase_d_aa_formal_r2_det/L0/aa_manifest.json`」，该目录在本 worktree **不存在**（`out/v3_phase_d_aa_formal*` 全部不存在；
D02 原始根在仓库外）。这是首轮评审自身的引用缺陷；报告改引 `outputs/evidence/aa/all_repetitions.csv` 是正确的，且本评审已复算通过。

### 环境观察（不列为缺陷）

- 10:26:48，工作树 `src/causal_growth/evaluation/v3_g_matrix.py` 再次变为 `6ec009b6…`（`git status` 为 `M`，未提交；HEAD `ea24198`），
  晚于报告 10:10 的截止。报告 §2 写的「补丁后 `3f4d677f…`」因此又已过期；G01 的字节绑定不受影响（binding = `fd3ca127…`，`7d598fa` 49/49）。
- 本轮开始时同一路径已存在一份并行评审草稿（10:29，387 行，§1–§9 结构）；已原样备份到
  `out/review_g01_2/parallel_draft_backup_1029.md`，再按本任务要求的结构重写。结论独立得出（关键处与草稿交叉核对，数字均由本评审自算）。

---

## §5 复算表

### 5.1 主口径 `net_profit`（population=full，α=0.05，Welch t；输入 = 24 张分片表）

| 层 | reps | 拒绝 | FPR | Clopper–Pearson 95% | mc_se | SE 校准 | 平均效应 | 与 merged 表 max\|Δ\| |
|---|---|---|---|---|---|---|---|---|
| L0 | 250 | 14 | 0.0560 | [0.030950, 0.092174] | 0.014542 | 0.987215 | −0.001871 | 0.0 |
| L1 | 250 | 11 | 0.0440 | [0.022166, 0.077363] | 0.012971 | 0.993645 | +0.000837 | 0.0 |
| L2 | 250 | 10 | 0.0400 | [0.019345, 0.072329] | 0.012394 | 0.987572 | −0.003842 | 0.0 |
| L3 | 250 | 11 | 0.0440 | [0.022166, 0.077363] | 0.012971 | 0.995208 | +0.004390 | 0.0 |
| **POOLED** | **1 000** | **46** | **0.0460** | **[0.033871, 0.060884]** | **0.006624** | **0.994819** | −0.000121 | **0.0** |

- 与 merged 表 15 行 × 5 列（reps/rejections/fpr/cp_low/cp_high）逐格比较：**max|Δ| = 6.9389e-18**，唯一格子 `net_profit/POOLED/cp_low`；
  与证据内 `recomputed_fpr.csv` 逐格差 **0.0**（该 CSV 存 6 位小数）。6.9389e-18 与报告第 69 行一致，成因即 `1−0.95` 的浮点 α。
- `CP(50,1000) = [0.037335, 0.065390]`；0.004 / 0.006624 = **0.604** 个 MC SE（报告「约 0.6」✓）。
- 次级：`paid_purchase_7d` 7/7/12/14 → **40/1 000 = 0.0400 [0.028728, 0.054073]**；
  `any_refund_30d` 16/17/8/11 → **52/1 000 = 0.0520 [0.039077, 0.067635]**；与报告 §4 十行全同。
- test 列对照：45/1 000 = 0.0450 [0.0330096, 0.0597528]。

### 5.2 完整性（只用逐 rep 表）

| 检查 | 本评审批 |
|---|---|
| 行数 / 分片 | 1 000；83×8 + 84×4；12 个 CSV |
| 每层 | 250 行、`rep` 0..249 无缺口无越界（4/4 `complete=true`） |
| 重复 | `(block,level,rep)` 0；整行 0；`run_id` 1 000 唯一 |
| 唯一性 | `n_total`={200000}、`alpha`={0.05}、`protocol_config_hash`={00723dc2…}；`config_hash` 每层 1 个（4 个值） |
| 结构恒等 | `n_label1+n_label0=n_total`、`split_train+val+test=n_total` 全成立 |
| 真 AA | `coupon_cost_total`=0、`actual_action_share`=0、`virtual_label_probability`=0.5（1 000 行） |
| 主键 NaN | 0（block/level/rep/run_id） |

### 5.3 证据链（双向）

| 层 | 登记 | 磁盘 | 缺失 | sha256/bytes 不符 | 字节 |
|---|---|---|---|---|---|
| 目录级 `g01_aa250` | 59 | 60（+`coverage.json`） | 0 | 0 | 1 275 048 = 磁盘和 − 24 073 |
| 顶层 `outputs/evidence` | 91 | 231 | 0 | 0 | 16 964 194 = Σbytes |

- 顶层 G01 新增 14 条：12 manifest + binding + runs_summary；`registry_repairs` 共 17 条，末条 10:06（89→91，`dropped_missing_target=[]`）。
- 未登记 140 个：126 个有子索引，14 个无索引（N-7）。
- 逐 rep 表与日志按 33 号规则只进目录级（G01 顶层无逐 rep 记录）——与报告第 85 行一致。

### 5.4 运行汇总

| 检查 | 本评审批 |
|---|---|
| 窗口 | 2026-10-28 22:42:39 → 2026-10-29 05:15:38（23 579.0 s） |
| 12 片起止 / `failures` / `all_complete` | 12/12 与 `runs/` 原件逐字段相同 |
| 行数 | `shards[].rows` 合计 1 000；`layers[0].rows` 与 CSV 行数 12/12 相同；每层 250 |
| 表哈希 | `layers[0].sha256` 与导出 CSV sha256 **12/12 相同** |
| `failures_total` | 0；`source_retries` 合计 0；`file_lock_retries` 合计 0 |

### 5.5 成本与解析功效

| 项 | 本评审批 |
|---|---|
| `total_cpu_s` | Σ 137 931.219 = 38.314 CPU·h；min 128.672 / p5 134.324 / 中位 136.594 / p95 141.815 / max 181.375；[132,137] 占 67.4% |
| `total_wall_s` 中位 | 138.301 |
| 带外概率（真值 0.08，[0.035,0.065]） | R=250 **0.813364**；R=1 000 **0.959807** |
| 带外概率（真值 0.08，[0.037,0.065]） | R=250 **0.815105**；R=1 000 **0.959807** |
| merged 列 `detect_power_if_true_0_09` | R=250 0.917585；R=1 000 0.997132 |

### 5.6 §5 五行表可重建性

| 行 | 可否从包内重建 | 备注 |
|---|---|---|
| 计划 1 000 | 可 | `runs_summary.shards[].rows` 求和 |
| 成功 1 000 | 可 | 1 000 行逐 rep 表 |
| 成功「14/14 exit」 | **部分** | 包内仅 12 个 `.exit`；merge/verify 见 `logs/`（N-4） |
| 失败 0 | 可 | `failures_total`、逐 rep retries |
| 有效 1 000 | 可 | 见 5.2 |
| 哈希四件套 | 可 | 4 个哈希均实算命中 |

### 5.7 §5.1 逐 rep 连接

| 项 | 本评审批 |
|---|---|
| 行数 | D02 1 384 → 去重 1 000（250/层）；G01 1 000 |
| join | both 1 000 / left_only 0 / right_only 0 |
| 数值/布尔列 | 69 个；60 个 max\|Δ\|=0.0；9 个非零（8 个计时 + `file_lock_retries`，最大 1） |
| 字符串列 | 5 列全同；`config_hash`、`protocol_config_hash` 各 1 000/1 000 不同 |
| D02 指纹 | protocol `30511a32…`（1 值）；config 4 值（`1d0d83c5/7ab83d75/d5266240/2671bded`） |

### 5.8 绑定与关键文件哈希

| 文件 | bytes | sha256 |
|---|---|---|
| `binding/snapshot_binding.json` | 5 777 | `1c3a8b2a…`（自校验字段 `526ff53d…`，重算相同） |
| `merged/v3_phase_D_aa_formal_merged.csv` | 2 779 | `2c6d6e91…` |
| `runs_summary.json` | 5 825 | `dd6a0471…` |
| `aa/all_repetitions.csv` | 1 650 065 | `77a2a386…` |
| binding 内 `v3_aa.py` | — | `95edd77c…` |

---

## §6 局限

1. **只读、未重跑**：全程只读文件 + 单进程 pandas（24 张分片表、1.65 MB 的 `all_repetitions.csv`、2 779 B 的 merged 表）；
   未跑 pytest、未跑 `scripts/34|36|37|39`、未触发任何数据作业（本机 4 个 G02 正式进程在跑，刻意避让）。
2. **仓库外 D02 根未重开**：报告 §5.1 称「`business/models/policy/evaluation` 四份相同、`design/execution/scenarios` 三份不同」，
   本轮按约束未打开 `D:\L\practice_project\...`，该三文件差异只作旁证；protocol 指纹变了这一点已由包内 `all_repetitions.csv` 独立证实。
3. **内存/遥测只对文字**：10.69 GB、3.82 GB、815 MB、14.76 GB 只核对了注册表原文，未重测；报告已正确标注来源为压测与跑中健康检查。
4. **「运行期源码只读」仍只能推断**：证据包没有运行期前后的 `pipeline_source_hashes()` 落盘，只能由「binding 49 文件 = `7d598fa` 树」
   与「05:19 改盘」时间线反推；这与报告 §6.6 自认的局限一致，不额外扣分。
5. **实时树已再次变化**：复评时（10:26 之后）`v3_g_matrix.py` 为 `6ec009b6…`（未提交），晚于报告 10:10 截止；不影响 G01（绑定于 `fd3ca127…`），
   但报告 §2「补丁后 `3f4d677f…`」已过期，改判时可顺手改为「截至 10:10 为 `3f4d677f…`」。
6. **未审 40/41 号脚本**：本轮范围是 13 项条件与 G01 证据链；40/41 号（G02 导出）不在范围内。
7. **首轮评审的自身缺陷已记录**：P2-9 的路径 `out/v3_phase_d_aa_formal_r2_det/...` 不存在（N-8）；本复评不继承其引用。
8. **并行草稿**：本文件路径在 10:29 已有一份并行评审草稿，已备份到 `out/review_g01_2/parallel_draft_backup_1029.md`；
   本复评的结构与结论按本任务要求重写，所有数字由本评审自算，未复用草稿数字。

---

**一句话总结**：13 项里 **P1 4/4、P2 8/9 真实关闭**，剩下的全是「一句话说错/一处旧数」，数据与证据链本身经得起独立复算；
把这 3 组文字改准后，G01 可以由「未证实」改判为「通过」（含义限定见 §1）。
