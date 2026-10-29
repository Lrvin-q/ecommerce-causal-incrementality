# Phase G01 正式 AA（4 层 × 250 = 1 000 次）独立评审

> 合成数据 / 已知 DGP。评审时间：**2026-10-29 06:40（北京时间）**。
> 被评对象：`docs/v3_phase_G01_formal.md`（维护时间 2026-10-29 05:30）、运行注册表 `docs/v3_phase_G_run_registry.md`（06:26）。
> 评审身份：独立评审（非产出者）。**未改** `GOAL.md` / `TODO.md` / 报告正文 / `outputs/evidence/**` / `src` / `sql` / `configs`；
> 临时脚本与复算产物只落 `out/review_g01/`（`recompute_g01.py`、`recompute_out.json`、
> `recomputed_by_metric_layer.csv`、`merged_cell_diff.csv`）。
> 复算手段：`.venv/Scripts/python.exe`（PYTHONUTF8=1），只读 pandas/scipy/hashlib；
> **未复用** 17/37 号脚本的任何函数，CP 区间与 mc_se 由本评审自行实现；未重跑管线、未运行 pytest、未写任何受冻结文件。

---

## §1 结论

**PASS WITH CONDITIONS —— 0 P0 / 4 P1 / 9 P2。**

数值层面**零不符**：报告 §1–§7 中每一个可从证据复算的数字（46/1 000、CP、mc_se、SE 校准、逐层、两个次级指标、
与 17 号表的差、45 个登记文件的 sha256/bytes、顶层 89 条）都被本评审独立重算复现，最大绝对差为 **0.0**。

判为"有条件通过"的全部是**证据包可复算性 / 文档口径**问题，不是数据问题，且每条的修法都只需导出几个文件或补几行字：

1. **P1-1** `out/g01_snapshot/snapshot_binding.json`（49 文件绑定 `526ff53d…`）与 12 个 `g_aa_run_summary.json`
   （唯一记录 `failures=[]`、真起止时刻）**没有导出进 `outputs/evidence/`**，而 `out/` 不入库（`git ls-files out` = 0），
   `grep -rl 526ff53d outputs/evidence/` = **0 命中**。AGENTS §12.1 把"binding json"点名为必须导出的材料。
2. **P1-2** 12/12 分片 manifest 的 `started_at_utc` **实际写的是完成时刻**（s01 写 01:58:43，而它 22:42:39 起跑），
   导出件里没有任何字段记录 `22:42:39 → 05:15:45`，§2 的"起止 / 墙钟 6 h 33 m"无法从证据包重建，且按字面读会得出"每片跑 0 秒"。
3. **P1-3** GOAL G01 行的判据是"**计划/成功/失败/有效与哈希**"，报告没有把这四项计数逐项作答（无"失败 0"、无"有效"定义）。
4. **P1-4** §5.1 "D02 的逐 rep 表当时未归档……因此无法在 rep 级做交叉比对"**与证据包事实相反**：
   `outputs/evidence/aa/all_repetitions.csv`（顶层登记 `kind=aa_repetitions_merged`，1 384 行 → 去重 1 000 行，`77a2a386…`）
   就在 `outputs/evidence/` 内，按 `(level,rep)` 与 G01 的 1 000 行连接得 **1 000/1 000、21 个统计列 max|Δ| = 0.0**。

**关于"是否把确定性复现说成独立验证"（本任务的 P0 触发器）：没有。** 报告 §5.1 明写"这不构成新增的统计证据""不能把'逐字节相同'当成'独立重复的第二个样本'"，
§6.4 也承认"本次无法回答 AA 在新源码上是否变化"。本评审进一步做了报告认为做不到的 rep 级比对（见 §4，且该比对**只用 `outputs/evidence/` 内的文件就能完成**），
结果 **1 000 rep × 21 个统计列 max|Δ| = 0.0**——这使"不是第二个独立样本"的披露**更成立**，不构成 P0；错的是"做不到"这句，方向偏保守而非夸大。

**改判建议**：条件关闭后，`GOAL.md` G01 行可由"未证实"改为"通过"，含义**仅限**"合并 1 000 次的 FPR 与 0.05 相容、
逐层只作描述、记录与哈希可复算"，**不含**"新增 1 000 次独立 AA 证据"，也不含"定向有效"。改写由主负责执行（本评审不改 GOAL）。

---

## §2 P0 / P1 / P2 清单

### P0（0 条）

无。三个 P0 触发器逐个排除：
(a) 数字造假/口径错误——未发现，全部复算一致（§3）；
(b) 把确定性复现写成独立验证——**未发生**，§5.1 的表述是反向的（主动否认独立性）；
(c) 越权改判/擅自改状态——**未发生**，报告头"状态：未证实"，§7 明写"状态改判需独立评审通过后由主负责执行"；
`GOAL.md:27` 末列仍为"未证实"（本评审核对过，未改）。

### P1（4 条，改判前须关闭）

**P1-1　证据包缺"源码绑定 / 运行汇总"两类身份文件（撞 AGENTS §12.1 原文）**

- 证据路径：报告头部"运行快照 49 文件（`out/g01_snapshot`，绑定见 `snapshot_binding.json`）"、
  §2 表"快照 49 文件绑定""真树 `v3_g_matrix.py` 全程 `fd3ca127…`"。
- 复算值：
  - `out/g01_snapshot/snapshot_binding.json`：`kind=byte_snapshot, n_files=49, source_hashes_sha256=526ff53d56a54c756030965486be86194352828fbf7af29cfd4f8c32ca1ab60b`；
    本评审用脚本按 `v3_g_matrix.create_snapshot` 的规则（`sha256(json.dumps(hashes, sort_keys=True, separators=(",",":")))`）
    从该文件自身的 `source_hashes` **重算得同一哈希**（自洽 ✓）；`git show 7d598fa:<path>` 对 49 个文件逐个哈希，**49/49 全同**；
    当前真树 **48/49 相同**，唯一差异 `src/causal_growth/evaluation/v3_g_matrix.py`（`fd3ca127…`→`3f4d677f…`，mtime 2026-10-29 05:19:40）。
  - **但**：`find outputs/evidence -name "*binding*"` 有 `d03_formal/snapshot_binding.json`、`g_smoke/snapshot_binding.json` 等，
    **独缺 G01**；`grep -rl 526ff53d outputs/evidence/` = 0；`git ls-files out` = 0（`out/` 被 `.gitignore` 整目录忽略）。
  - 12 个 `out/g01_aa250/sNN/g_aa_run_summary.json`（含 `failures: []`、`all_complete: true`、`started_at/finished_at`、
    `snapshot_binding.n_files=49`）同样未导出。
  - 该 binding 的 `git_commit` 字段为 **null**，第三方即使拿到 `526ff53d…` 也无法定位到哪棵源码树（49 个路径的清单本身也只在这个未入库文件里）。
- 影响：§2 中"快照绑定 / 运行期未写源码 / 失败 0"三句在仓库内**不可复现**；报告头"本文所有数字可由 `outputs/evidence/g01_aa250/` 重建"应限定为"§1/§3/§4 的 FPR/CP/SE 数字"。
- 建议：导出 `snapshot_binding.json` 与 12 个 `g_aa_run_summary.json`（可合并成一个 `runs_summary.json`），登记进目录级与顶层。
  注意 33 号的身份类规则（`*binding*.json` / `*manifest*.json` / `freeze.json` / `meta*.json` / `decision.json`）**收不到**
  `g_aa_run_summary.json`，需按 F02 逐 rep 支出表的既有先例手工登记并在 `registry_repairs` 留痕。

**P1-2　12/12 分片 manifest 的 `started_at_utc` 实为"完成时刻"，导出件内无真起止**

- 证据路径：`outputs/evidence/g01_aa250/per_rep/sNN__Lx__aa_manifest.json`；`out/g01_logs/sNN.log`；`out/g01_logs/lane*.done`。
- 复算值（逐片对照日志最后一行）：s01 `2026-10-28T17:58:43.044Z` = 北京 01:58:43，而 `s01.log` 首行是 `[G-AA 22:42:39]`、
  末行是 `[G-AA 01:58:43] 完成 1/1 层`；s02 `21:11:03.149Z` = 05:11:03 = `lane1.done`（21:11:03Z）。**12 片全部如此**：
  `17:58:42/43、17:58:51/52、18:01:06/10、21:11:03/11/12、21:15:34/38` 逐一对上各自日志的**结束**时刻。
- 影响：证据包里唯一的"运行时间"字段是错的；报告的"起止 22:42:39 → 05:15:45 / 墙钟 6 h 33 m"只能从 `out/g01_logs`
  与未导出的 `g_aa_run_summary.json` 得到，第三方只看 `outputs/evidence/` 会读成"12 个分片各跑 0 秒"。
- 建议：不要改写既有证据件（证据不可变），在 `coverage.json` 的 note 里注明该字段实为完成时刻，并把权威的
  `g_aa_run_summary.json`（P1-1 同一批导出）作为时间与 `failures` 的唯一来源。

**P1-3　GOAL G01 判据"计划/成功/失败/有效与哈希"未逐项作答（AGENTS §9 要求逐条对照）**

- 证据路径：`GOAL.md:27` 末列"计划/成功/失败/有效与哈希 | 未证实"；报告 §2/§5 只有零散信息。
- 现状：计划 1 000、成功（1 000 行）与"12 个 exit 0"都写了，但**"失败 0"与"有效"的定义、以及"哈希"三件套没有集中成一行**。
- 材料其实齐（本评审复算）：计划 1 000（4×250）；成功 1 000；失败 0（`out/g01_logs/*.exit` 12+2 个全 0；
  12 个 run summary `failures=[]`；逐 rep 表 `source_retries=0`、`file_lock_retries=0` 合计 0）；
  有效 1 000（`block=true_aa` 1 000/1 000、`n_total=200000` 唯一、full 人群 `n_treated` 最小 99 407、
  test 人群最小 29 693、三列主键无 NaN）；哈希（`protocol_config_hash=00723dc2…`、merged `2c6d6e91…`、
  binding `526ff53d…`、`v3_aa_source_sha256=95edd77c…`）。
- 建议：在 §5 前加一张四行表，直接把上面这串数抄进去即可关闭。

**P1-4　§5.1 "无法在 rep 级做交叉比对"被证据包自身推翻**

- 证据路径：报告 §5.1 末段原句"D02 的逐 rep 表当时未归档（只归档了层汇总与合并表），因此无法在 rep 级做交叉比对"；
  `outputs/evidence/aa/all_repetitions.csv`；`outputs/evidence/coverage.json` 中 `kind=aa_repetitions_merged` 记录。
- 复算值：
  - 顶层 `outputs/evidence/coverage.json` 有记录 `{"kind":"aa_repetitions_merged","target":"outputs/evidence/aa/all_repetitions.csv",
    "bytes":1650065,"sha256":"77a2a386bcdd6be52052530a605ca52395e05180ba5747df0c726144bdb5ae29","rows_raw":1384,"rows_deduped":1000}`，
    磁盘文件 1 650 065 B、sha256 自算相同，mtime **2026-10-27 09:57**；该记录属 05:16 登记前**既有 77 条**之一
    （`registry_repairs` 的 77→89 只新增 12 个 manifest），即报告写作时它已在包内且已登记。
  - 该表 80 列，`level` 计数 L0/L1/L2/L3 = 338/338/338/370，按 `(level,rep)` 去重后 **250/250/250/250 = 1 000**。
  - 与 G01 的 24 张逐 rep 表合并（1 000 行）按 `(level,rep)` 内连接：**1 000/1 000**，`run_id` 1 000/1 000 相同；
    `n_total/label_share/n_orders/srm_p_value/alpha`、`full_/test_` 两套 `net_profit` 的 diff/se/ci/p、
    `paid_purchase_7d`/`any_refund_30d` 的 diff/se，共 **21 个统计列 max|Δ| = 0.0**；仅 `total_cpu_s` 不同（max 60.36 s，属机器负载）。
- 影响：这不是数据问题，是**报告对可复算性的自我低估**。第三方完全可以只用 `outputs/evidence/` 复现"同一样本"，
  报告却写成"无法"，会让读者误以为 §5.1 的结论只能靠"同 seed 推断"。同时它反过来说明 P0 触发器 (b) 确实不成立：
  证据包内有逐 rep 原件，任何"独立重复"的读法都会被立刻证伪。
- 建议：§5.1 改为"D02 的逐 rep 合并在 `outputs/evidence/aa/all_repetitions.csv`（1 384→1 000 行），按 `(level,rep)` 与本次 1 000 行
  21 列逐格比对 max|Δ| = 0.0（仅 CPU 计时列不同），故为同一 1 000 次抽样"。这一句比"无法比对"更有力，也不改变结论。

### P2（9 条，建议同批修，不阻塞改判）

- **P2-1　§2"单 rep 成本 CPU 132–137 s"与证据不符**。1 000 行 `total_cpu_s`：min **128.672**（L1/rep249）、
  p5 **134.324**、p25 136.031、中位 **136.594**、p75 137.332、p95 **141.815**、max **181.375**（L0/rep26，其中 pipeline 180.969）；
  落在 [132,137] 的只有 **67.4%**。合计 **137 931.22 CPU·s = 38.31 CPU·h**（GOAL 预算口径 44.4 CPU·h，未在报告中提及）。
  建议改为"中位 136.6 s、p5–p95 134.3–141.8 s、极值 128.7–181.4 s"。
- **P2-2　§2"6 路并行峰值内存 10.69 GB"不是本次实跑遥测**。该数是注册表 §2 的**开跑前压力测试**值；
  实跑期唯一记录是 23:00 健康检查的"12 进程合计 3.82 GB / 单进程峰值 815 MB"。报告把它放在"这次跑了什么"一栏，
  读者会理解为 G01 运行期峰值。建议标注来源。
- **P2-3　§3 的"检出率(真值 0.08)"无定义，且用的是 [0.035, 0.065] 带，不是 GOAL 的 [0.037, 0.065]**。
  该列即 merged 表 `detect_power_if_true_0_08`，解析计算（`stats.norm`），不是实测。复算：R=250 时
  带 (.035,.065) → **0.813364**（报告写 0.81）；带 (.037,.065) → **0.815105**（应写 0.82）。R=1 000 两者同为 **0.959807**。
  报告 §1/§7 引用的是 GOAL 的 [0.037,0.065]，同一文档内两套带并存且未说明（§12.4 的"改一处 grep 全文"问题）。
- **P2-4　§3/§4 未写 `population=full`**。merged 表 `population` 列是 `full`；用 `test_*` 列复算 net_profit 是
  **45/1 000 [0.033010, 0.059753]**（不是 46）。报告只说"net_profit"，第三方从逐 rep 表复算时无法判断该用哪套列。
  建议在 §3 表头写"主口径 `net_profit` / `population=full`（随机分配的全部用户）"。
- **P2-5　两处体量与实测不符**。§5"登记 45 个文件 / 1.3 MB"：45 个文件字节和 **1 232 623 B = 1.23 MB**；
  §5"顶层 77 → 89 条（`total_bytes` 16.92 MB）"：**16 924 056 B 是登记前值**，登记后为 **16 952 592 B = 16.95 MB**
  （`registry_repairs` 末条 `records_before=77 / records_after=89 / total_bytes_after=16952592`）。
- **P2-6　§5 把四项断言都归给 `verify.log`，归因不准**。`out/g01_logs/verify.log` 只打印 `rows=250 unique_reps=250 shards=[…]`；
  `n_total/alpha/protocol_config_hash` 三项的判定结果在 **`coverage_check.json`**（`n_total:[200000]`、`alpha` 未单列、
  `protocol_config_hash:[00723dc2…]`、`problems: []`、`passed: true`）。
- **P2-7　§5.1 的成因说明不完整："指纹变了、数据逐比特没变"没有写出来**。
  "无法在 rep 级做交叉比对"一句已单列为 **P1-4**（证据包内有 `all_repetitions.csv`，可以比对）。
  这里只保留成因部分：§5.1 只说"`master_seed` 相同 + 逐 rep 派生 + AA 路径未变"，但本次与 D02 的 `protocol_config_hash` 其实是
  **00723dc2… vs 30511a32…**、层内 `config_hash` 也不同（L0：`a0eb214e…` vs `1d0d83c5…`），
  而 `design.yaml / execution.yaml / scenarios.yaml` 三份协议文件的哈希都变过。报告应明写"**协议指纹变了、数据逐比特没变**"，
  否则读者会以为连指纹都一样。
- **P2-8　§7 "⇒ 支持 'FPR ≈ 0.05'" 带判定口吻**。§1 标题已写"判定待评审"，两处口径不完全一致。建议改为条件句
  （"若按 GOAL G01 口径，则该 CP 包含 0.05；是否改判由评审与主负责决定"），避免报告自证通过。
- **P2-9　§5.1 建议补一句 D02 的协议号**（`30511a32…`，来自 `out/v3_phase_d_aa_formal_r2_det/L0/aa_manifest.json`
  的 `protocol_config_hash`），否则"当前冻结协议（00723dc2）能复现 D02 一致结果"缺少对照物。

---

## §3 独立复算表

**口径**（本评审自定，未读 17/37 源码后照抄）：`rejection := full_<metric>_p_value < 0.05`；
CP = 等尾 Clopper–Pearson（`scipy.stats.beta.ppf(α/2, k, n−k+1)` / `ppf(1−α/2, k+1, n−k)`，`α=0.05`）；
`mc_se = sqrt(p(1−p)/n)`；SE 校准 = `std(diff, ddof=1) / mean(full_*_se)`；
输入 = `outputs/evidence/g01_aa250/per_rep/` 24 张分片表（1 000 行），**不读合并表**。

### 3.1 主口径 `net_profit`（population=full）

| 层 | reps | 拒绝数 | FPR | Clopper–Pearson 95% | mc_se | SE 校准（经验SD/平均估计SE） | 平均效应 | 与 17 号合并表 max\|Δ\| |
|---|---|---|---|---|---|---|---|---|
| L0 | 250 | **14** | 0.0560 | [0.030950, 0.092174] | 0.014542 | **0.987215** | −0.001871 | **0.0** |
| L1 | 250 | **11** | 0.0440 | [0.022166, 0.077363] | 0.012971 | **0.993645** | +0.000837 | **0.0** |
| L2 | 250 | **10** | 0.0400 | [0.019345, 0.072329] | 0.012394 | **0.987572** | −0.003842 | **0.0** |
| L3 | 250 | **11** | 0.0440 | [0.022166, 0.077363] | 0.012971 | **0.995208** | +0.004390 | **0.0** |
| **POOLED** | **1 000** | **46** | **0.0460** | **[0.033871, 0.060884]** | **0.006624** | **0.994819** | −0.000121 | **0.0** |

- 报告 §1 的 0.987 / 0.994 / 0.988 / 0.995 / 0.995 与上表逐位一致（四位小数舍入后）。
- 与 17 号合并表 15 行 × 6 列（reps/rejections/fpr/cp_low/cp_high/mc_se）**逐格比较，最大绝对差 = 0.0**（不是"≤1e-12"，是精确相等）。
- 与证据内 `recomputed_fpr.csv` 比较：最大绝对差 **6.9389e-18**，落在 `net_profit/POOLED/cp_low`。
  成因可解释：17 号用 `clopper_pearson(..., confidence=0.95)` → `α = 1−0.95 = 0.050000000000000044`，
  37 号用字面 `alpha=0.05`；`beta.ppf` 在同一格给出 `0.033871498547677924` 与 `0.03387149854767792`。两边都对。
- CP 半宽：L0 0.030612 / L1 0.027598 / L2 0.026492 / L3 0.027598 → 报告"±0.026～0.031" ✓。
- CP(50,1000) = **[0.037335, 0.065390]**，与 GOAL 的"约 [0.037, 0.065]"一致；4 次差 = 0.004，除以 mc_se 0.006624 = **0.604 个 MC SE**，报告"约 0.6" ✓。

### 3.2 次级指标（同样逐格对上，未做多重比较校正）

| 指标 | 层 | 拒绝数/rep | FPR | CP 95% |
|---|---|---|---|---|
| `paid_purchase_7d` | L0/L1/L2/L3 | 7 / 7 / 12 / 14 | .028/.028/.048/.056 | 与报告 §4 全同 |
| `paid_purchase_7d` | POOLED | **40**/1 000 | 0.0400 | [0.028728, 0.054073] |
| `any_refund_30d` | L0/L1/L2/L3 | 16 / 17 / 8 / 11 | .064/.068/.032/.044 | 与报告 §4 全同 |
| `any_refund_30d` | POOLED | **52**/1 000 | 0.0520 | [0.039077, 0.067635] |

### 3.3 完整性与一致性（本评审自算，不复用 verify 脚本）

| 检查 | 结果 |
|---|---|
| 总行数 / 分片行数 | 1 000；83×8 + 84×4 = 1 000 ✓ |
| 每层 | 250 行、`rep` 唯一、0..249 **无缺口无越界** ✓（4 层） |
| 重复 | `(block,level,rep)` 重复 0；整行重复 0；`run_id` 唯一 1 000 ✓ |
| 唯一性 | `block`={true_aa}、`n_total`={200000}、`alpha`={0.05}、`protocol_config_hash`={00723dc2…}；`config_hash` 每层各 1 个（L0 `a0eb214e…`/L1 `8a36a14b…`/L2 `c07d2f02…`/L3 `59958e1d…`）✓ |
| 结构恒等 | `n_label1+n_label0=n_total`、`split_train+val+test=n_total`、`n_treated+n_control=n_total`（3 指标 × 2 人群）全部成立 ✓ |
| 真 AA 性质 | `coupon_cost_total`=0、`actual_action_share`=0、`virtual_label_probability`=0.5 全 1 000 行 ✓ |
| p 值 ↔ CI 一致性 | 30 个（3 指标 × 5 层）格子中，"p<0.05" 与 "95% CI 不含 0" **完全等价**（逐 rep 比对，0 例分歧）✓ |
| SRM（额外） | `srm_p<0.05` 计数 L0 12 / L1 9 / L2 11 / L3 15 = **47/1 000 = 4.7%**，与 5% 相容（GOAL 未要求，仅作平衡性旁证） |
| 极端 p | min p = **0.000181**（L2/rep192）；p<0.01 共 9 个、p<0.001 共 1 个——无"p 塌到 0"的异常 |
| 原始表 ↔ 归一化表 | 12 个 `out/g01_aa250/sNN/layer_runs/Lx_*/aa_repetitions.csv` 与导出的归一化表 **rep 全同、p 值逐行全同**（无丢行、无挑选）✓ |
| 日志 ↔ 表 | `s01.log` 83 行 `p(net_profit/full)=` 与 CSV 逐 rep 比对，max\|Δ\| = 4.96e-5（日志只印 4 位小数），cpu 差 ≤ 0.005 s ✓ |

### 3.4 成本

`total_cpu_s` 合计 **137 931.22 s = 38.31 CPU·h**（L0 9.67 / L1 9.49 / L2 9.67 / L3 9.49）；
`total_wall_s` 中位 138.30 s；6 lane × 6 h 33 m ≈ 39.3 lane·h，与 38.3 CPU·h 自洽。

---

## §4 对"逐字节相同"披露的判断

**披露本身准确、无过度声明；但可以（也应该）写得更硬——本评审已把 rep 级证据补出来了。**

1. **sha256 自算**：`outputs/tables/v3_phase_D_aa_formal_merged.csv` 与
   `outputs/evidence/d02_aa_phase_d_20261027/v3_phase_D_aa_formal_merged.csv` **同为
   `2c6d6e91bf4b89ea225edd959ccf8629865b391844d3c53b9debcb47e5149fe4`（2 779 B）**，`read_bytes()` 直接相等。
   15 行（3 指标 × 5 层）`rejections` 全同（df.equals → True）。
   同名 `.json` **不同**（2 120 B `1706549921b5…` vs 2 223 B `cc8151487a…`），差异仅在 `roots`
   （`out/g01_aa250/s01..s12` vs `D:\L\practice_project\…\out\v3_phase_d_aa_formal*`）——与报告"只覆盖了 CSV、json 因 roots 不同而变"的隐含说法一致。
2. **rep 级交叉比对（报告称做不到，实际只用证据包就能做到）**：主用件是证据包内的
   `outputs/evidence/aa/all_repetitions.csv`（1 384 行，按 `(level,rep)` 去重后正 250/250/250/250）；
   评审另用 D02 的五个原始根 `D:\L\practice_project\营销数分项目\out\v3_phase_d_aa_formal{,_r2,_r3,_r2_det,_r3_det}` 交叉确认两者一致。
   与本次 1 000 行按 `(level,rep)` 连接：**both=1000, left_only=0, right_only=0**；`run_id` 1 000/1 000 相同；
   `n_total/label_share/n_orders/srm_p_value/alpha` 与 `full_/test_net_profit` 的 diff/se/ci/p、两个次级指标的 diff/se，
   共 **21 列 max|Δ| = 0.0**，仅 `total_cpu_s` 不同（max 60.36 s）。⇒ "同一样本"不是聚合层面的巧合，而是**逐 rep 逐比特相同**。
3. **指纹其实是不同的**：D02 的 `protocol_config_hash = 30511a32bcee9db55e8f5ec1bbc2b9d63eb63dc2a13aa5c720f948c781eccdbe`、
   L0 `config_hash = 1d0d83c5…`；本次 `00723dc2…` / `a0eb214e…`。D02 的 `protocol_source_hashes` 与本次逐份比较：
   `business / models / policy / evaluation` 四份相同，**`design / execution / scenarios` 三份不同**（AA250 修订所改）。
   报告 §5.1 的解释"同一 `master_seed` + 逐 rep 派生 + AA 路径未变"方向对，但**没有指出"指纹变了而结果没变"**
   这个必须解释的事实；`v3_aa.py` 源码哈希两边同为 `95edd77c…`、`config_hash` 是整份配置的哈希（并非数据参数子集），
   所以"变的是 R/计数类字段、数据生成参数未变"这句话需要写出来，否则第三方会怀疑是读错旧产物。
4. **是否写成"独立重复"**：没有。原文"这不构成新增的统计证据""不能把'逐字节相同'当成'独立重复的第二个样本'"
   与实测完全一致；§6.4"本次无法回答 AA 在新源码上是否变化"也守住了边界。
   唯一可挑剔的是 §5 小标题里的"**独立复算**"指的是 37 号脚本独立于 17 号（脚本口径），不是独立样本——
   在 §5.1 紧跟其后的语境下不会误读，但建议改称"**独立实现复算**"。

**结论**：披露方向正确、力度偏保守。P1-4 与 P2-7 给出补正后，这一节可以作为"确定性复现而非独立验证"的标准表述范本。

---

## §5 检查清单（做了什么 → 得到什么）

| # | 我跑的 | 得到 |
|---|---|---|
| 1 | `out/review_g01/recompute_g01.py`：读 24 张分片表，自实现 CP/mc_se/SE 校准，按层与 POOLED 重算 3 指标 × 5 层 | 46/1 000、CP [0.033871, 0.060884]、mc_se 0.006624；与 17 号表 **max\|Δ\|=0.0**；与 `recomputed_fpr.csv` **6.9389e-18**（见 §3.1） |
| 2 | 同上：逐层 250 行 / rep 0..249 无缺口 / `n_total`、`alpha`、`protocol_config_hash`、`config_hash` 唯一性 / 结构恒等 / 重复行 | 全部通过；`(block,level,rep)` 重复 0、整行重复 0、`run_id` 1 000 唯一 |
| 3 | `for f in out/g01_logs/*.exit` 逐个 cat；`cat post.status`、`verify.log`、`merge.log`、`export.log`、`register.log` | s01–s12 + merge + verify **14/14 = 0**；`verify.log` = `PASS`（4 层各 rows=250 unique_reps=250）；`post.status` 末行 `OK: 导出与登记完成`（export/register 的 exit 只出现在 post.status 文本里，无独立 `.exit` 文件——已在 P2 备注之外，不单列） |
| 4 | 脚本重算 `outputs/evidence/g01_aa250/coverage.json` 45 条的 sha256 与 bytes（逐条与磁盘比） | **45/45 全同，0 不符**；磁盘 46 个（多出的就是 `coverage.json` 本身）；字节和 1 232 623 B |
| 5 | 脚本重算顶层 `outputs/evidence/coverage.json` 89 条 | **89/89 全同，0 不符**；`sum(bytes) = total_bytes = 16 952 592`；其中 `kind=g01_shard_manifest` **12 条**（s01–s12）✓；另发现 `kind=aa_repetitions_merged` 指向 `outputs/evidence/aa/all_repetitions.csv`（1 650 065 B、1 384→1 000 行），即 **D02 逐 rep 原件在包内**（→ P1-4）；其余 G01 文件（24 张逐 rep 表、12 个 exit、3 份日志、2 个脚本、merged 两件）**不在顶层**——与 33 号"顶层只收身份类 JSON"的既定规则一致，非缺陷，但报告"77→89"容易被误读成"1 000 行表也进了顶层" |
| 6 | 逐条解析 12 个分片 manifest：`layer_table_sha256` 与导出 CSV 现算 sha256 比对 | 12/12 相同；`g_status=formal`、`g_formal_approval=G01-AA250-20261028`、`source_retries_total=0`、`file_lock_retries_total=0`；`formal_repetitions_completed` 仍为 **0**、`purpose` 仍是 `phase_d_complete_aa_not_formal_completion`（v3_aa 的 D 阶段固定标签；解释这条的 note 只在未导出的 run summary 里，已在 P1-1 覆盖） |
| 7 | 解析 `out/g01_logs/s01.log` 的 83 条 `p(net_profit/full)=` 与 CPU，对照 `s01__L0__aa_repetitions.csv` | p 最大差 4.96e-5（日志 4 位小数）、cpu 最大差 0.005 s ⇒ **表里的数就是这次跑出来的数**，不是从别处复制的汇总 |
| 8 | 12 个 `out/g01_aa250/sNN/layer_runs/Lx_*/aa_repetitions.csv`（原始）vs 导出的归一化表 | rep 序列全同、`full_net_profit_p_value` 逐行全同 ⇒ 归一化只做了筛选/重排，没有丢 rep |
| 9 | 重算 `out/g01_snapshot/snapshot_binding.json` 的 `source_hashes_sha256`；`git show 7d598fa:<49 个路径>` 逐个哈希；当前真树逐个哈希 | 自算 = **526ff53d…** = 记录值 ✓；commit 7d598fa **49/49** 同；当前真树 **48/49**（仅 `v3_g_matrix.py` 变 `3f4d677f…`，mtime **2026-10-29 05:19:40**） |
| 10 | `git log/show` 查 `v3_g_matrix.py` 与 `ade0571` | 补丁前 `fd3ca127…`（= 快照值，故"运行期真树 = 快照"可核）、补丁后 `3f4d677f…`、diffstat **+66 / −6**（与报告一致）；提交时刻 **2026-10-29 05:41:15**（报告写"05:19"，那是文件 mtime，提交晚了 22 分钟——两种说法都不算错，建议统一写"05:19 改盘 / 05:41 提交"） |
| 11 | `sha256sum` + `read_bytes()` 对比本次 merged 与 D02 归档（csv/json 两份） | csv **逐字节相同**（`2c6d6e91…`）、15 行全同；json 不同（roots 不同） |
| 12 | 读 `outputs/evidence/aa/all_repetitions.csv`（1 650 065 B，sha256 自算 `77a2a386…` 与登记一致）按 `(level,rep)` 去重后与本次 1 000 行内连接，比 21 个统计列；再用 D02 五个原始根独立复做一次 | `both=1000/left_only=0/right_only=0`；21 列 **max\|Δ\|=0.0**、`run_id` 全同，仅 `total_cpu_s` 差 ≤60.36 s（见 §4.2）；两次结果一致 |
| 13 | `grep -rl 526ff53d outputs/evidence/`、`git ls-files out \| wc -l`、`find outputs/evidence -name "*binding*"` | 0 命中 / 0 个文件入库 / 有 d03、g_smoke 等 binding、**独缺 G01** |
| 14 | 重算 12 个 manifest 的 `started_at_utc` 与各自日志首末行、`lane*.done` 对照 | **12/12 等于完成时刻**（见 P1-2） |
| 15 | 解析 12 个 `g_aa_run_summary.json` | `failures=[]`、`all_complete=True`、`n_files=49`、`22:42:39→01:58:43 / 01:58:47→05:11:03 / … / 02:01:11→05:15:34`，与 `out/g01_logs/started_at.txt`（UTC 14:42:35）与 `finished_at.txt`（UTC 21:15:45）换算后一致 |
| 16 | 用 `test_*` 列重算 net_profit FPR | **45/1 000** [0.033010, 0.059753] ≠ 46 ⇒ 报告必须写 `population=full`（P2-4） |
| 17 | 复算 `detect_power`（正态近似）在两种带下的值 | (.035,.065)：0.813364 / 0.917585 / 0.959807；(.037,.065)：**0.815105** / 0.918101 / 0.959807（P2-3） |
| 18 | `git status --short`、`git diff HEAD -- docs/v3_phase_G01_formal.md outputs/evidence/g01_aa250` | 工作区仅有 1 个未跟踪的 g02 日志；被评报告与证据**与 HEAD 一致**（评审对象确定） |
| 19 | `grep "G01" GOAL.md` / 读 `GOAL.md:27` 末列 | 仍为"未证实"；本评审**未改** GOAL/TODO/报告/证据/src/sql/configs |

---

## §6 本评审的局限

1. §4.2 的 rep 级比对**主件在证据包内**（`outputs/evidence/aa/all_repetitions.csv`，已登记），可入库引用；
   仓库外的 D02 原始根（`D:\L\practice_project\…`）只作第二遍旁证，该路径不受版本控制，**不能**作为入库证据。
   两遍结果一致（21 列 max|Δ| = 0.0）。
2. 内存（10.69 GB）与"运行期间真树只读"无法独立复核——前者来自开跑前压测，后者只能靠 git 快照反推（补丁前 = 快照值）。
   若当真要证明"运行期没被写"，需要一个运行期的 `pipeline_source_hashes()` 前后对比，本次证据里没有。
3. 本评审**未重跑**任何 AA rep、未跑 pytest（`logs/pytest_g01_20261028_2234.log` 显示 1 310 项全过、`EXIT=0`，只作旁证）。
4. 逐层数字只作描述；本评审**不**对任何一层下"通过/不通过"的判断（GOAL 口径）。
