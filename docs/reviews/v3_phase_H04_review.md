# H04 独立复核：§3.11 冻结重复证据与 C275–C290

## 0. 对象与效力

- 复核对象 commit：`f52d6636a482eda3613407bda85f59dd8a68efb8`（H04，2026-10-31 20:30:42 +0800）。
- 复核完成时间：2026-10-31 20:46（Asia/Shanghai）。
- 复核方式：只读；未改 `outputs/tables/*`、`paper/**`、`scripts/**`、`configs/**`、`out/scratch/v3_paper_build/**` 或任何既有评审文件；未重编译、未跑正式 R>0 作业、未装包、未 commit。写入仅限本文件与 `out/scratch/h04_review/`。

以下 sha/规模均为复核时 `f52d663` 的字节；工作树 20:47 后已变化，见 §0.1。

| 对象 | 位置 | sha256 / 规模 | 备注 |
|---|---|---|---|
| 主张登记表 | `outputs/tables/v3_h04_claim_registry.csv` | `181e21a0879af128f55633af5d08480ddef233c4fc8da5d9a8800f1c5a29dc68`；72 079 B；表头+290 数据行；291 个 CRLF 行尾；BOM=true | mtime 2026-10-31 20:18:49；未重写 |
| 结果章 §3.11 | `paper/v3/body/03_results.md` | `314551763c46d3567783a71fa1e90839463833abfab7f4547fbc550c97a74596`；1531 行 | §3.11 起 L1473；表 3-27 L1483–L1490 |
| 方法章记号范围 | `paper/v3/body/02_method.md` | `79cde5fa611c119959c222e8808ac28a3b96806845b3e857ac71712a88639fa4`；721 行 | L28：`C01` 到 `C290` |
| 摘要 | `paper/v3/abstract.md` | `a442c632adb9447e8f2bc64818aa0190840d60fb0436721bd86041e587599cbf`；7 行 | 数字集中在 L3 |
| 构建 PDF | `out/scratch/v3_paper_build/main.pdf` | `51a2e68783db04fe44ef68ed1267235fd021cc159f2e472e448f8179f7c63bd0`；1 097 524 B；51 页 | mtime 2026-10-31 20:27:01；第 45 页含表 3-27 数值 |
| LaTeX 正文 | `out/scratch/v3_paper_build/body.tex` | `a0c4ad6e157bc5de455913f786d04c3e471bbc40dc8d4796a42e834dc5649786` | L231 记号范围；表 3-27 在 L3338–L3342 |
| core 源表 | `outputs/tables/v3_g_g_core.csv` | `aa19561ee28a2ee635b6364d34d2822ea90b6156c6ea9e7980990fa7bc828ff2`；16 数据行（+表头） | R=500；`provisional=False`；`block=g_core`；`tier=1` |
| Tier2 源表 | `outputs/tables/v3_g_g_tier2.csv` | `8854cd8ac2f1f9d61a8c7880e7d99248b1eb7498c8827190681e647ddad08543`；80 数据行（+表头） | 20 格 × 4 指标；R=30 |
| G03 正式报告 | `docs/v3_phase_G03_formal.md` | `b48f67726b73969249f12212f5782d6f6b44cb10c2f7f187acc2842b18b23571` | mtime 20:11:54；§3.0、§6.2 |
| G03 证据清单 | `outputs/evidence/g03_formal/coverage.json` | `0d1f9db33ed4d3b3a5436949e7992c56b33d42823da408a08b2281668beb0a61` | 16 个 per-cell 文件的 sha/bytes |
| G03 汇总 | `outputs/evidence/g03_formal/recomputed_summary.csv` | `fe28d9c5256f8df984ecab57fd640c0f63aadf86c9142624226e5b201d6dd456` | 16 行被抽验 |
| 42 号门禁 | `scripts/42_claim_number_gate.py` | `013b78593d235a004e1feee760f714062455e882528f5ade1be4074a83f8d24c` | 只读审计 |
| 52 号串联 | `scripts/52_paper_gates.sh` | `82abb32d28947040d599dffe86e4ca48257c70b2481753fde3adc03cb13fef24` | 未重跑；引用 20:27:07 的 `summary.txt` |

**效力范围**：本报告只对上述 commit 与上述 PDF sha256 成立。复核期间仓库有其他任务（G04）并行推进：工作树存在与本任务无关的未提交修改/未跟踪文件，且 HEAD 在复核末尾前进到 `08cce2b81e4477cbeb948d478b246f0179a8fa8c`（G04 C1 收口提交）。这些改动不是本次复核所写。已核对 `git diff --stat f52d663 HEAD --` 对 H04 审阅对象（登记表、03_results、02_method、abstract、main.pdf、body.tex、42/52、G03 报告、core 表）为空，即**提交历史**中的字节仍与 `f52d663` 相同；本报告不评价 G04 提交本身。

### 0.1 复核后的并行变更（不在本报告范围）

复核收尾的 20:47–20:49，另一个并行任务在**工作树**中修改了本报告的三个审阅对象并重建了 PDF/body.tex；改动内容与本报告 C1–C4 逐条对应（C01 备注改为 Clopper–Pearson、C05 改为 `in_abstract=yes`、§3.11 改为“合计 600 次”/2026-10-29、表头改为“检验集 ATE”并补注）。截至 20:49 观察到的快照：

| 对象 | 20:49 工作树 sha256 | 与复核时（§0 表）的关系 |
|---|---|---|
| `outputs/tables/v3_h04_claim_registry.csv` | `5e921a92ef8b94bac51915cb2d33cc860b78fbbdd1c02ba0bed9c96cc3388833` | 已改；旧字节可从 `f52d663` 恢复 |
| `paper/v3/body/03_results.md` | `0b747ec0a006d4af4fc6acd698afd0e6136296d791eb1068a7325558afa314ec` | 已改（20:47–20:49 间至少两次）；旧字节可从 `f52d663` 恢复 |
| `out/scratch/v3_paper_build/main.pdf` | `40c7c48a3e31d2e7fb68d0487d7f233f910e8a633b63308577f803225016c48c`（1 097 571 B，20:48:30） | **旧 PDF 未跟踪、已被覆盖**；旧 sha `51a2…3bd0` 已不在磁盘 |
| `out/scratch/v3_paper_build/body.tex` | `43ed40609b20b52f7998095e341535ac3ea8b845f7481c9599f4c6bdac189bf4` | 旧 body.tex 未跟踪、已被覆盖 |

因此：本报告 §0 的 sha/规模、§3 的 PDF 页级检查、§5 的 397 上标计数，均指 **`f52d663` 的旧字节**（20:27 构建）。旧 PDF/body.tex 无法从当前磁盘重放（未跟踪且已覆盖），旧登记表/03_results 可由 `git show f52d663:…` 恢复；16 条 core 值、290 行结构与摘要映射不依赖这些被改文件（登记表 C275–C290 未变，abstract 未变），但**工作树的 C1–C4 修复未在本报告中复核**。若要把这些修复视为关闭条件，必须以新 commit + 新 PDF sha 重新走 H04 复核。

## 1. 方法

独立复算脚本为 `out/scratch/h04_review/recompute.py`，不调用 42 号门禁的校验函数；所有断言、比较和计数均在该脚本内重新实现。步骤：

1. **290 行结构**：以 `utf-8-sig` 读登记表；检查 BOM/CRLF、291 行、字段名、ID 唯一与连续性、11 个必填字段空值、`tier`/`in_abstract` 取值、`decimals` 集合、章分布。
2. **290 行逐条复算**：对每行确认 `source_csv` 存在、`column` 存在、`filter` 恰好命中 1 行；用源值按 `decimals` 做 f-string 舍入，与 `display_value` 严格比较；另用 `Decimal` 量化对比，记录两种舍入的差异；检查是否存在重复的 `(source_csv, filter, column)` 组。
3. **C275–C290 专项**：按 `cell_id` + `metric` 从 `v3_g_g_core.csv` 重取，比较 `mean` 的舍入值与登记值；读取 `outputs/evidence/g03_formal/per_cell/{cell}__repetitions.csv`，确认 500 行、rep 0–499 唯一、指标无空值、逐 rep 均值与 core 均值在 1e-12 内一致；核对 `recomputed_summary.csv` 的同格同指标均值；用 `coverage.json` 核对每个 per-cell 文件的 sha256。
4. **表 3-27 与正文**：解析 Markdown 表 4×4 单元格，核对数字、claim ID、cell、metric；解析 §3.11 正文中所有“数字 [C…]”对；确认 §3.11 只引用 C275–C290。
5. **摘要**：抽取摘要全部数字 token，分别查登记表的 `display_value`、`statement`、`precision_note`；扫描 Tier2 的 4 位小数值与 20 个格名是否出现在论文/摘要。
6. **上标**：在 `body.tex` 上以 `\\textsuperscript\{C(\d+)\}` 计数，检查 ID 集合与登记表相等、字面 `[Cxx]` 残留；用独立 `grep | sort | uniq -c` 复核 397 与每 ID 次数。
7. **门禁探针**：在 `out/scratch/h04_review/` 的副本上运行真实的 42 号 `--abstract`/`--draft`，记录 RC；不修改 `scripts/**`，不修改原始摘要/长稿。
8. **PDF**：用 `pdftotext -layout -enc UTF-8` 抽取，确认 51 页、表 3-27 的 16 个数值出现在第 45 页、§3.11 出现在第 4/44 页。
9. **未重编译、未重跑 52、未跑 R>0**；52 的结论只引用既有 `out/scratch/paper_gates/summary.txt`（20:27:07）。

完整输出：`out/scratch/h04_review/console.txt`、`recompute.log`、`recompute_summary.json`；16 条明细：`out/scratch/h04_review/c275_c290_recompute.csv`。

## 2. 结论

**PASS WITH CONDITIONS**（4 条关闭条件，针对 `f52d663`）。数值核心通过：290/290 登记值可复算、16/16 新 claim 与 core/逐 rep/汇总/sha 全部一致、表 3-27 的 16 格与正文 14 处引用全部一致、摘要结果数字均为 Tier1、正文未混列 Tier2、上标 ID 集合与登记表相等。条件集中在 §3.11 的描述文字与两处登记/标注，均不被 42/52 的绿色覆盖。**截至 20:49 工作树已出现与 C1–C4 对应的未提交修复（§0.1），但不在 `f52d663` 内、本报告未复核，故不视为条件已关闭。**

### C1（P1）§3.11 的 Tier2 重复数算错，D1=A 日期与源记录不符

- 位置：`paper/v3/body/03_results.md` L1479–L1480。
- 原文：“另有 20 个 Tier2 机制格 × 30 次（合计 2 600 次重复）……按 2026-10-30 的 D1=A 裁决……”。
- 事实：20×30=**600**；**2 600** 是 24 格总数（4×500 + 20×30 = 2 600），其中 core 已在 L1492 写明“共 2 000 次”。G03 报告 L36 也写“Phase 2 的 Tier2 600 rep（20 格 × 30）”。把 2 600 挂在 Tier2 的括号里，读者会得到“Tier2 2 600 + core 2 000 = 4 600”的错误总量。
- 事实：D1=A 的用户裁决记录为 **2026-10-29 20:41**（`GOAL.md` L31；`docs/v3_决策与反思日志.md` L4332–L4334，所在日为 2026-10-29），G03 报告 §3.0 写 **2026-10-29 22:52**（L254）。在 `docs/`、`GOAL.md`、`AGENT_HANDOFF.md` 的 Markdown 记录中没有找到“2026-10-30 的 D1=A 裁决”；L1480 的 2026-10-30 与两处源记录均不符。
- 要求：把括号改为“合计 600 次”，或改为“连同 core 合计 2 600 次”；日期改为 2026-10-29（并统一 20:41/22:52 的口径）。改后重建 PDF、重跑 52；新 PDF 的 sha256 会变化，本报告的 PDF 效力不自动延伸到新构建。

### C2（P2）C05 的 `in_abstract=no` 与摘要实际引用 1.00 不一致

- 位置：登记表 C05；摘要 L3“退款率护栏通过率为 1.00”。
- 事实：C05 是 Tier1，`display_value=1.00`，`statement=F02 退款率护栏通过率`，但 `in_abstract=no`。摘要确实写了 1.00，且该 1.00 只能对应 C05（C03 是 0.98，C04 是 0.2816）。
- 后果：42 号 `check_abstract` 只对 `in_abstract=yes` 的行要求出现，因此这个 1.00 **没有被门禁绑定**；删掉摘要里的 1.00 门禁仍为 RC=0（探针见 §5）。
- 要求：把 C05 的 `in_abstract` 改为 `yes`（或从摘要删去 1.00，并说明护栏通过率不再进摘要）。登记表 sha 会变化，改后重跑 42 `--abstract`。

### C3（P2）表 3-27 的“检验统计量”实际是检验集 ATE（`ate_test`）

- 位置：`03_results.md` 表头 L1485、正文 L1507–L1508；`body.tex` 表 3-27 同名列。
- 事实：表内第二列对应登记 `ate_test`。源码 `src/causal_growth/evaluation/v3_g_matrix.py` L506–L507 先取 `split == "test"`，L522 定义 `"ate_test": float(test.diff)`；`src/causal_growth/estimate/v3_models.py` L1854 也把 `ate_test` 直接赋为 `prediction.ate`。它是**检验子样本上的 ATE 均值**，不是假设检验的检验统计量（没有 z/t 值），单位仍是元/人。
- 后果：正文“检验统计量的均值与 ATE 均值几乎重合……同 rep 配对没有给检验统计量带来系统位移”把“检验集 ATE 对全样本 ATE”的差异说成了“检验统计量位移”，属于口径误标；数值本身不受影响。
- 要求：表头改为“检验集 ATE（`ate_test`）”，并在表注或正文首次出现处定义“检验子样本上的 ATE”；相应改写 L1507–L1508 的两处“检验统计量”。改后重建 PDF。

### C4（P3）C01 的 `precision_note` 把 Clopper–Pearson 写成了 Wilson

- 位置：登记表 C01 `precision_note`：“1000 rep 合并；Wilson CP [0.033871, 0.060884]”。
- 事实：以 x=46、n=1000 复算，Clopper–Pearson 精确区间为 `[0.0338714985, 0.0608835527]`，与登记的 0.033871/0.060884 一致；Wilson 区间为 `[0.0346624928, 0.0608122039]`，下界并不等于 0.033871。摘要 L3 也写的是 “Clopper–Pearson 95% 区间”。因此 “Wilson CP” 是错误的方法标签（“CP”与“Wilson”互相矛盾）。
- 要求：把备注改为“Clopper–Pearson 95% 区间 [0.033871, 0.060884]”。这是登记表文字修正，不改任何数值；改后重跑 42。

## 3. C275–C290 的 16 条独立复算

**结论：16/16 全部一致。** 每条均满足：`filter` 在 core 表恰好命中 1 行；`R=500`、`tier=1`、`block=g_core`、`provisional=False`；逐 rep 文件 500 行、rep 0–499 唯一、无空值；逐 rep 均值与 core `mean` 在 1e-12 内一致；`recomputed_summary.csv` 同格同指标均值一致；`coverage.json` 的 sha256 与磁盘文件一致；MC SE 用 `sd(ddof=1)/sqrt(500)` 复算一致。

源值来自 `outputs/tables/v3_g_g_core.csv` 的“core 行”（表头为第 1 行）；逐 rep 文件为 `outputs/evidence/g03_formal/per_cell/{cell}__repetitions.csv`；“复算”列为按 `decimals` 舍入后的字符串。

| claim | cell | metric | core 行 | 源均值（12 位） | dec | 登记/复算 | 一致 | 逐 rep 均值 | MC SE |
|---|---|---|---:|---:|---:|---|---|---|---:|
| C275 | L0_P_main | ate | 2 | 0.243417840748 | 4 | 0.2434 / 0.2434 | 是 | 0.243417840748 | 0.001727346 |
| C276 | L1_main | ate | 6 | 0.283149191278 | 4 | 0.2831 / 0.2831 | 是 | 0.283149191278 | 0.002035355 |
| C277 | L2_n200000_p050 | ate | 10 | 0.287758033303 | 4 | 0.2878 / 0.2878 | 是 | 0.287758033303 | 0.001974397 |
| C278 | L3_fixed_lt000 | ate | 14 | 1.664125157177 | 4 | 1.6641 / 1.6641 | 是 | 1.664125157177 | 0.002049328 |
| C279 | L0_P_main | ate_test | 3 | 0.243383778676 | 4 | 0.2434 / 0.2434 | 是 | 0.243383778676 | 0.003296473 |
| C280 | L1_main | ate_test | 7 | 0.285125774905 | 4 | 0.2851 / 0.2851 | 是 | 0.285125774905 | 0.003792421 |
| C281 | L2_n200000_p050 | ate_test | 11 | 0.287660845123 | 4 | 0.2877 / 0.2877 | 是 | 0.287660845123 | 0.003763198 |
| C282 | L3_fixed_lt000 | ate_test | 15 | 1.663793123933 | 4 | 1.6638 / 1.6638 | 是 | 1.663793123933 | 0.003791881 |
| C283 | L0_P_main | ate_paid_purchase_7d | 4 | 0.049986072911 | 4 | 0.0500 / 0.0500 | 是 | 0.049986072911 | 6.313207e-05 |
| C284 | L1_main | ate_paid_purchase_7d | 8 | 0.050074974216 | 4 | 0.0501 / 0.0501 | 是 | 0.050074974216 | 6.484245e-05 |
| C285 | L2_n200000_p050 | ate_paid_purchase_7d | 12 | 0.050095478416 | 4 | 0.0501 / 0.0501 | 是 | 0.050095478416 | 6.400265e-05 |
| C286 | L3_fixed_lt000 | ate_paid_purchase_7d | 16 | 0.082188293217 | 4 | 0.0822 / 0.0822 | 是 | 0.082188293217 | 6.615077e-05 |
| C287 | L0_P_main | ate_any_refund_30d | 5 | 0.004207490273 | 4 | 0.0042 / 0.0042 | 是 | 0.004207490273 | 2.069995e-05 |
| C288 | L1_main | ate_any_refund_30d | 9 | 0.004227581259 | 4 | 0.0042 / 0.0042 | 是 | 0.004227581259 | 2.077398e-05 |
| C289 | L2_n200000_p050 | ate_any_refund_30d | 13 | 0.004212045894 | 4 | 0.0042 / 0.0042 | 是 | 0.004212045894 | 2.045205e-05 |
| C290 | L3_fixed_lt000 | ate_any_refund_30d | 17 | 0.006769948496 | 4 | 0.0068 / 0.0068 | 是 | 0.006769948496 | 2.005606e-05 |

补充核验：

- C275 的 MC SE 示例：`0.03862463257080765 / sqrt(500) = 0.0017273460806855672`，与 core 表 `MC_SE` 一致；16 条的 `sd_convention=ddof1`、`se_convention=ddof1`。
- 16 条的 `(source_csv, filter, column)` 无重复组；`filter` 均为 `cell_id == '…' and metric == '…'`，逐条唯一命中。
- 表 3-27 的 16 个单元格与登记值 16/16 一致；§3.11 正文的 14 个“数字 [C…]”对全部一致（表 16 + 正文 14 = 30 对，30/30）；§3.11 只引用 C275–C290，无越界。
- 表 3-27 的 16 个数值在 PDF 第 45 页可检出；§3.11 字样在第 4/44 页出现。
- **CI 语义正确**：正文 L1498–L1499 明确“CI 按均值 ± 1.96×MC SE 计算，不是对 DGP 真值的覆盖率”，并拒绝“95% 的区间盖住了真值”；C275–C290 的 `precision_note` 也写“CI 为 mean±1.96×MC SE，不是覆盖率”。未发现把 CI 说成覆盖率/覆盖真值的表述。

## 4. 摘要与 Tier2 核查

### 4.1 摘要中的数字

摘要 L3 的结果数字与登记表对应如下（`in_abstract` 为登记表原值）：

| 摘要字面 | 登记对应 | tier | in_abstract | 字面一致 | 说明 |
|---|---|---|---|---:|---|
| 1000 | C01 `statement`/`precision_note` | Tier1 | yes（C01） | 是 | 设计常数（1000 rep），无独立 display 行 |
| 0.046 | C01 `display_value` | Tier1 | yes | 是 | 合并 FPR |
| 95% | C02 `statement`（“95% 区间下界”） | Tier1 | yes（C02） | 是 | 区间置信水平，设计常数 |
| 0.033871 | C02 `display_value` | Tier1 | yes | 是 | CP 下界 |
| 0.060884 | C01 `precision_note` | Tier1 | yes（C01） | 是 | **无独立 claim 行**，只在上界备注中 |
| 0.05 | C05 `precision_note`（alpha=0.05） | Tier1 | no（C05） | 是 | 名义水平，设计常数 |
| 0.98 | C03 `display_value` | Tier1 | yes | 是 | F02 券值得发通过率 |
| 0.2816 | C04 `display_value` | Tier1 | yes | 是 | F02 净利差 |
| 1.00 | C05 `display_value` | Tier1 | **no（C05）** | 是 | 护栏通过率；元数据不一致，见 C2 |

结论：**摘要所有结果数字均能回到 Tier1**；没有 Tier2 的数值、格名或机制结论；`95%`、`1000`、`0.05` 是设计与名义水平常数，分别可在 C02 statement、C01 note、C05 note 找到字面依据。两个记录问题：(i) C05 的 `in_abstract=no` 与摘要 1.00 不一致（C2）；(ii) 0.060884 只有 C01 备注、没有独立 claim 行，42 号 `check_abstract` 不会检查它（见 §5）。二者都不构成 Tier2 泄漏。表中 `in_abstract` 为复核时 `f52d663` 的值；20:47 后工作树已把 C05 改为 `yes`（§0.1），本报告未复核该修复。

### 4.2 42 号 `--abstract` 的真实行为（读代码，不只看 RC）

`scripts/42_claim_number_gate.py` 的 `check_abstract`（L95–L108）只做两件事：

1. 对每一行，若 `in_abstract == "yes"` 且 `display_value` 不是摘要的子串，报错；
2. 对每一行，若 `tier == "Tier2"` 且 `display_value` 是摘要的子串，报错。

它**不**解析摘要里的数字，**不**要求摘要中出现的数字都能在登记表找到，**不**要求 `in_abstract=no` 的值不得出现，也**不**检查数字与 claim 的上下文对应。当前登记表 Tier1=290、Tier2=0，因此第 2 条分支是空集，整个 `--abstract` 实际等价于对 C01–C04 四个 `display_value` 的 4 次子串检查。RC=0 只能说明“C01–C04 的四个值都在摘要里”，不能说明“摘要所有数字都已登记且都是 Tier1”。真实运行的返回信息“290 条 claim 全部回指且与源表复算一致（Tier1 290 / Tier2 0）”混合了 `validate` 的全表复算与摘要的 4 条检查，容易被误读为后者覆盖了 290 条。

### 4.3 Tier2 是否混入论文

- `v3_g_g_tier2.csv`：80 行 = 20 格 × 4 指标，R 全为 30；20 个格名在论文正文/摘要中出现 **0** 次。
- 4 位小数层面，论文中有 13 个值与 Tier2 数值“字面碰撞”，但全部同时是 core/登记表已有的值；**Tier2 独有的 4 位值在论文中出现 0 个**。因此没有把 Tier2 数字当 Tier1 证据使用。
- G03 报告有 4 处 Tier2 表头“**Tier2 选中格（20 格，R=30；不与 Tier1 并列排序）**”（L111/149/185/221），§6.2 L471 明确“R=30 时覆盖率 SE≈0.040，只能判方向与量级，不得与 Tier1 数字并列”。精度披露满足要求。
- 论文 §3.11 L1480–L1481 也写“只在 G03 正式报告里呈现——那里精度更低，不与本文的 Tier1 数字并列”。就“数值不并列”而言合规；问题只在 L1479 的“2 600”算术与日期（C1）。

## 5. 上标一致性与门禁盲区

### 5.1 上标

- `body.tex` 中 `\textsuperscript{C…}` 出现 **397** 次，唯一 ID **290** 个；ID 集合与登记表 290 个 claim **完全相等**；`missing_from_registry=[]`、`registry_never_cited=[]`。
- 字面 `[Cxx]` 残留 **0** 处。
- 397 次是“出现次数”，不是“290 个 ID 各一次”：290 个 ID 中多数 1 次，最多 5 次（C177），共 107 次重复出现；方法章 L28 只声明“`C01` 到 `C290` 是主张登记号”，没有声称“一符一 ID”，所以这不构成文字矛盾。引用该数时应写“397 次上标、290 个 ID”，不要写“397 个一一对应”。
- `02_method.md` L28 的范围 `C01`–`C290` 与登记表一致；`body.tex` L231 同样为 `C01`–`C290`。

复核命令（独立于脚本）：
```bash
grep -o '\\textsuperscript{C[0-9]*}' out/scratch/v3_paper_build/body.tex \
  | sed 's/.*{C//;s/}//' | sort | uniq -c \
  | awk '{n++; s+=$1; if($1>m)m=$1} END{print "unique",n,"occ",s,"max",m}'
# unique 290 occ 397 max 5
```

### 5.2 42/52 的实际覆盖边界

| 函数/步骤 | 代码位置 | 实际检查 | 不检查 |
|---|---|---|---|
| `validate` | 42 L27–L77 | 必填列、ID 重复、tier/in_abstract 枚举、Tier2 精度备注、source/column 存在、filter 恰 1 行、f-string 舍入等于 display | ID 是否连续、chapter 是否存在于论文、statement 是否真实、Tier1 的 precision_note、正文/表格文字 |
| `check_draft` | 42 L80–L92 | 每个 claim 的 `[Cid]` 在长稿任意位置出现；`display_value` 在长稿任意位置出现 | 数字是否在对应表格单元格/对应句子、是否有未登记数字、描述性范围、算术一致性 |
| `check_abstract` | 42 L95–L108 | `in_abstract=yes` 的值必须出现；`tier=Tier2` 的值不得出现 | 摘要中未登记数字、`in_abstract=no` 的值、数字与 claim 的语义对应；Tier2 分支在当前 0 行下为空 |
| 52 串联 | 52 L42–L58 | build → 42 draft → 42 abstract → 44 引用 → 43 长稿 | 不额外做语义/算术/表格绑定检查 |

探针结果（全部在 `out/scratch/h04_review/` 的副本上运行；0=门禁放过，1=门禁拦截）。**以下 RC 以复核时旧登记表（C05 `in_abstract=no`）为准；工作树后续把 C05 改为 `yes` 后，`drop_100` 会变为 RC=1（正是修复生效的预期结果），其余探针不变。**

| 探针 | 修改 | RC | 说明 |
|---|---|---:|---|
| 真实摘要 | 原 `paper/v3/abstract.md` | 0 | C01–C04 四个值都在 |
| 真实长稿 | 拼接 01–04 的 `draft_concat.md` | 0 | 290 个 `[Cid]` 与 display 都在 |
| 未登记数字 | 摘要加入 `0.777777` | **0** | 门禁不扫描摘要未登记数字 |
| 删除 1.00 | 摘要 `1.00` → `100%` | **0** | C05 `in_abstract=no`，删了也不报 |
| 改已登记值 | 摘要 `0.2816` → `0.2817` | **1** | C04 `in_abstract=yes`，这是唯一被抓的类型 |
| 加 Tier2 值 | 摘要加入 `0.4362`（L0_Pi_heterogeneous_cost/ate，R=30） | **0** | 登记表 Tier2=0，Tier2 分支空转 |
| 改方法范围 | 长稿 `C290` → `C274` | **0** | 描述性范围不被校验 |
| 换表 3-27 单元格 | 长稿 L0/L1 的净利润两格互换（保留 `[C275]`/`[C276]`） | **0** | 只有子串存在性，没有单元格绑定 |

42 号自测 11/11 PASS；52 的既有 `summary.txt`（20:27:07）为 `build=0, concat_chars=96240, claim_draft=0, claim_abstract=0, citations=0, long_draft=0`。这些绿色结果**不能**证明 C1/C3/C4 的文字正确，也不能证明表格单元格绑定；它们只证明“登记值能在源表复算、在长稿/摘要出现”。因此 H04 的接受必须建立在本报告的独立复算上，而不是 42/52 的 RC。

**对 H04 结论的影响**：门禁盲区没有造成 C275–C290 的数值错误（16/16 独立复算通过）；它解释了三类问题为何能在“五门禁全绿”下存在：§3.11 的 2 600/日期（描述文字）、表头“检验统计量”（语义标签）、C05 的 `in_abstract`（元数据）。C1–C4 关闭后，42/52 仍不能替代对描述文字的复核，建议在 H04 收尾时保留本报告的独立复算作为证据。

## 6. 未覆盖与边界

1. **未重编译、未重跑 52**：PDF 的 51 页、第 45 页表值、sha256 均针对既有 `main.pdf`；没有验证“改动后重新构建仍 51 页/门禁全绿”。C1/C3 重建后必须重新复核新 PDF 与新 sha。
2. **未重跑 G03 的 R>0 作业**：逐 rep 证据按冻结产物处理，只核对了 sha256 与均值；没有重新生成 500 次重复，也没有验证 `coverage.json` 的导出脚本在另一台机器上的可复现性。
3. **290 行复算依赖当前源表**：所有 290 条都从 `source_csv` 当前文件重取，未重新生成上游结果；若源表在 commit 之后被替换，需以本报告记录的各对象 sha 重新核对。
4. **Tier2 未逐格复算**：只核对了 80 行/20 格/R=30 的结构、论文不混列、G03 的精度披露；G03 报告的 96+24 个格级值（24 格，含 core 4 格）不在本次范围内。
5. **C01 的 CP/Wilson 结论只针对该区间**：用 x=46、n=1000 的 beta 分位数复算；没有评估其他 claim 的区间方法。
6. **CI 的覆盖率未评估**：本报告只核对“CI=mean±1.96×MC SE”的表述与登记备注，没有把 CI 与 DGP 真值比较；论文也明确不做覆盖率。
7. **工作树不是干净状态，且复核后被并行修改**：复核期间有 G04 并行任务产生的未提交修改/未跟踪文件，HEAD 也已前进到 `08cce2b`；20:47–20:49 又有任务改了登记表、03_results、body.tex 并重建 PDF（§0.1）。这些都不在本报告范围内。H04 审阅对象在 `f52d663..HEAD` 的**提交历史**中无 diff，但工作树已不等于 `f52d663`；结论仍只对 `f52d663` 的字节与旧 PDF sha 成立。旧 PDF/body.tex 未跟踪且已覆盖，无法从当前磁盘重放。
8. **397 是出现次数**：不是 290 个 claim 各一次；最多 5 次。若后续把“397”写成“397 个一一对应”会与事实不符。
9. **MC SE 上界**：四条 `ate` 的 MC SE 最大为 0.0020493278，四舍五入到 4 位是 0.0020；L1497 的“0.0017–0.0020”在 4 位显示口径下成立，严格写区间上界应为 0.00205。未把它列为条件，因为论文全篇按 4 位显示，且该句没有声称更多精度。
10. **0.060884 的登记**：它是 C01 备注中的 CP 上界，不是独立 claim 行；若要求“摘要每个数字都有独立登记”，应新增一条 claim 或把 C02 的 statement 扩展为完整区间。当前按“Tier1 备注可回指”处理。

## 7. 复核命令

在项目根目录执行（Windows Git Bash，`PYTHONUTF8=1`）：

```bash
cd "C:/Users/26382/.qoder-cn/worktrees/app/c509bd/营销数分项目"

# 0) 对象哈希与构建产物
sha256sum outputs/tables/v3_h04_claim_registry.csv \
  paper/v3/body/03_results.md paper/v3/body/02_method.md paper/v3/abstract.md \
  out/scratch/v3_paper_build/main.pdf out/scratch/v3_paper_build/body.tex \
  outputs/tables/v3_g_g_core.csv docs/v3_phase_G03_formal.md \
  scripts/42_claim_number_gate.py scripts/52_paper_gates.sh

# 1) 全部独立复算（结构 + 290 行 + 16 条 + 表 3-27 + 摘要 + 上标 + Tier2 + PDF）
.venv/Scripts/python.exe -X utf8 out/scratch/h04_review/recompute.py

# 2) 16 条明细
cat out/scratch/h04_review/c275_c290_recompute.csv

# 3) 上标独立计数（应输出 unique 290 occ 397 max 5）
grep -o '\\textsuperscript{C[0-9]*}' out/scratch/v3_paper_build/body.tex \
  | sed 's/.*{C//;s/}//' | sort | uniq -c \
  | awk '{n++; s+=$1; if($1>m)m=$1} END{print "unique",n,"occ",s,"max",m}'

# 4) PDF 页数与表 3-27 页
pdftotext -layout -enc UTF-8 out/scratch/v3_paper_build/main.pdf - \
  | awk 'BEGIN{RS="\f"} {n++} END{print "pages",n}'
pdftotext -layout -enc UTF-8 out/scratch/v3_paper_build/main.pdf - \
  | awk 'BEGIN{RS="\f"} /0\.2434/ {print "page",NR}'

# 5) 42 号真实摘要/长稿（只读）
.venv/Scripts/python.exe scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --abstract paper/v3/abstract.md; echo "abstract_rc=$?"
.venv/Scripts/python.exe scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --draft out/scratch/h04_review/draft_concat.md; echo "draft_rc=$?"

# 6) 四个摘要探针（0=放过；change_registered 应为 1）
.venv/Scripts/python.exe scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --abstract out/scratch/h04_review/abs_unregistered.md; echo "unregistered_rc=$?"
.venv/Scripts/python.exe scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --abstract out/scratch/h04_review/abs_drop_100.md; echo "drop_100_rc=$?"
.venv/Scripts/python.exe scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --abstract out/scratch/h04_review/abs_change_registered.md; echo "change_registered_rc=$?"
.venv/Scripts/python.exe scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --abstract out/scratch/h04_review/abs_tier2.md; echo "tier2_rc=$?"

# 7) 两个长稿探针（均应为 0）
.venv/Scripts/python.exe scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --draft out/scratch/h04_review/draft_range_c274.md; echo "range_rc=$?"
.venv/Scripts/python.exe scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --draft out/scratch/h04_review/draft_swap_table.md; echo "swap_rc=$?"

# 8) CP 与 Wilson 对照（C01：CP 下界 0.033871、Wilson 下界 0.034662）
.venv/Scripts/python.exe -X utf8 -c "from scipy.stats import beta; import math; x=46; n=1000; p=x/n; z=1.959963984540054; d=1+z*z/n; c=p+z*z/(2*n); h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)); print('CP', beta.ppf(.025,x,n-x+1), beta.ppf(.975,x+1,n-x)); print('Wilson',(c-h)/d,(c+h)/d)"

# 9) 未跑（会重建/改产物，按只读纪律排除）
# bash scripts/52_paper_gates.sh --build
```

**报告结束**。本报告只对 `f52d663` + `main.pdf` sha256 `51a2e68783db04fe44ef68ed1267235fd021cc159f2e472e448f8179f7c63bd0` 有效；C1–C4 关闭并重建后，应以新 commit、新 PDF sha 重新复核。
