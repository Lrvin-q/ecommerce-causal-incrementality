# v3 R01 总评审：A–H 独立评审闭环与最终交付状态

> 合成数据 / 已知 DGP。评审时间：**2026-10-31 22:58（北京时间，Asia/Shanghai）**；审计起点 22:23。
> HEAD：`e1a78c0`（`Z02|audit: 全入口覆盖表；清理后全量 pytest 1432 点 exit=0`），分支 `codex/d03`。
> 被审对象：GOAL.md 验收表（`:15`–`:40`）、A–H 各阶段评审/复核文件（`docs/reviews/`）、终构建 PDF 与三件绑定产物、冻结配置、证据登记、门禁日志、Z01 清理提交、交付卫生。
> 审计范围声明：**只读**。未改 `src/ scripts/ configs/ outputs/ paper/ tests/`；未 commit / push / checkout；未装包；**未重建 PDF**（未跑 `scripts/52_paper_gates.sh --build`）；**未运行 62/63/66/51/49/33/40/41/42 任何写状态或重算脚本**（第 6 项只读既有日志）。本次写入仅本文件与临时目录 `out/scratch/r01_review/`（`pgm/` 为 43 号同口径重渲染的 PGM，另有并发报告备份，见 §3 P2-4）。
> 审计开始时 `git status --porcelain` 为 0 行；当前 HEAD 未变。

## 0. 结论

**`PASS WITH CONDITIONS`。**

A–H 每个阶段都能找到支撑其 GOAL 判定的独立评审/复核文件，且抽查内容与判定一致；H02 两项机械判据经我独立重算均为 **PASS**（有效字 **56.28%**；实质页按代码口径 70.21%、按真实结果章边界 **55.32%**，均 ≥50%）；三件产物 sha256、51 页、CreationDate、冻结配置 hash、证据 93/357 条全部逐字吻合。条件为：43 号 `res_end` 口径缺陷须修并同步 GOAL/H03 §9 的 70.21%（P1-1）、GOAL 的 Z01/Z02 行仍写"未证实"须随证据改判（P2-1）、本轮同一报告路径被并发进程写入（P2-4）。

## 1. 九项逐项证据与判定

### 1.1 验收表闭环（R01 核心）

`docs/reviews/` 共 **42 份**已入库（`git ls-files docs/reviews | wc -l` = 42），本轮新增本文件后 43 份。逐行核对下表（"文件:行"为本次实读位置，不是只看文件名）。

| ID | GOAL 当前状态 | 对应评审文件（实读） | 我的判定 |
|---|---|---|---|
| A01 | 通过（仅协议） | `v3_phase_A_review.md:7` "复审通过。允许进入 Phase B" | 支持 |
| B01/B02 | 通过（机制验收） | `v3_phase_B_review.md:7` "复审通过：B01/B02 机制验收成立"；`:24` 750/750 | 支持 |
| C01/C02 | 通过（工程范围） | `v3_phase_C_review.md:214` §5.8 最终判定通过；`:216` 维护时间 2026-10-25 10:05 | 支持 |
| D01 | 通过 21:38 | `v3_phase_D01_closeout.md:60` "PASS（可改判 D01 通过）"；`:14` 6/6 | 支持 |
| D02 | 通过 10-27 09:45 | `v3_phase_D_recheck.md:11` "PASS"；`docs/v3_phase_D_aa_formal.md:258/275` | 支持 |
| D03 | 通过 10-28 05:15 | `v3_phase_D03_rereview.md:17` "PASS"；`:21` "可以从未证实改为通过" | 支持 |
| E01/E02 | 通过 05:53 | `v3_phase_E_recheck.md:11` "PASS。"（三环） | 支持 |
| F01 | 通过 10:52 | `v3_phase_F01_recheck.md:24–36` 判 PASS WITH CONDITIONS 并给出"修 RC-1/RC-2/RC-4 后改判"条件；修复实文见 `docs/v3_phase_F01_ope.md:224–230`（32 行恒等 / 24 行有限 / 8 行 NaN）与 `:550`（22→23 条） | 基本支持，缺"修后 CLOSED"独立文件（P3-2） |
| F02 | 通过 22:04 | `v3_phase_F02_final_confirm.md:146` "CLOSED（可改判）" | 支持 |
| G01 | 通过 10-29 11:00 | `v3_phase_G01_review3.md:263` 5 条 P2 关闭、0 新增 P0/P1 | 支持 |
| G02 | 通过 10-29 23:30 | `v3_phase_G02_recheck.md:8` "9 项核查全部 CLOSED" | 支持 |
| G03 | 通过 20:16 | `v3_phase_G03_recheck2.md:16` PASS WITH CONDITIONS、`:37` 条件全关；`:343` 新问题全 P3 | 支持 |
| G04 | 通过 21:49 | `v3_phase_G04_recheck.md:154` "PASS"、`:19–23` C1–C5 CLOSED | 支持（但点数 1424≠1432，见 P2-2） |
| H01 | 通过 20:18 | `v3_phase_H01_recheck.md` C1/C2 CLOSED + 8/8 指纹 | 支持 |
| **H02** | **未证实（机械判据已过）** | 无独立评审文件（`ls docs/reviews` 无 H02）；本轮补齐，见 §2 | **可改判**（判据过，但 70.21% 须改，P1-1） |
| H03 | 通过 21:16 | `v3_phase_H03_visual_recheck.md:73` "PASS"（P1 清零、无新伤） | 支持 |
| H04 | 通过 20:55 / 21:01 重绑 | `v3_phase_H04_recheck2.md:10–12` 三产物 sha 逐字一致、`:45` C1–C4 CLOSED | 支持 |
| H05 | 通过 10-30 00:32 | `v3_phase_H05_recheck.md:33` R-1 已更正为 2/11；`docs/v3_H05_sources.md:33` 已是 2/11 | 支持，缺修后独立复核（P3-2） |
| R01 | 未证实（整体） | 本文件 | **建议改判，附条件** |
| Z01 | 未证实 | 无 `docs/reviews/` 文件；证据为 `cac1d7b` + `fac3558` + `docs/v3_Z01_v2清理记录.md` | 证据成立，但**表内状态过期**（P2-1） |
| Z02 | 未证实 | 无评审文件；证据 `docs/v3_Z02_全入口覆盖.md`（97 行）+ `out/scratch/pytest_full_20261031_2159.status`（`exit=0`，`start=21:59:14 end=22:08:50`） | 证据成立但状态过期；且"Git 干净"与 74 个未推送提交并存（P2-3） |

另核：GOAL 顶部"最新状态"与表内不一致——顶部写"**Z01 完成**"（`:5`），表 `:39` 仍为"未证实"；`Z01` 行 `:39` 与 `R01` 行 `:38`（"H02 待 R01 总评审核"）在 G04 改判（21:49）后未再刷新。**R01 能否改判**：其断言是"A–H 独立评审与返工闭环"，本轮已逐行确认 21 个阶段行均有最终 PASS/CLOSED 依据，H02 机械判据也已独立复算通过，故具备改判条件，条件是先清 P1-1 与 P2-1。

### 1.2 H02 独立机械核验

见 §2（专节）。

### 1.3 终构建 PDF 与绑定哈希

| 项 | 期望 | 实测命令与结果 |
|---|---|---|
| PDF sha256 | `415d59fe1e28…24da0` | `sha256sum out/scratch/v3_paper_build/main.pdf` → `415d59fe1e282b6ad203db17576faca5bb073e87ebdf4b914dffb9bef8924da0` 一致 |
| 页数 | 51 | `pdfinfo` → `Pages: 51`；A4 595.28×841.89 |
| CreationDate | 2026-10-31 20:58:32 | `pdfinfo` → `CreationDate: Sat Oct 31 20:58:32 2026 中国标准时间` 一致 |
| 登记表 | `5e921a92…` | `sha256sum outputs/tables/v3_h04_claim_registry.csv` → `5e921a92ef8b94bac51915cb2d33cc860b78fbbdd1c02ba0bed9c96cc3388833`；与 `v3_phase_H04_recheck2.md:12` 全值一致 |
| 结果章 md | `6d7b2634…` | `sha256sum paper/v3/body/03_results.md` → `6d7b26347a0aa5e371dcc491dffb230eeb6989edf20f067b9f91f7efc954c469` 一致 |

### 1.4 冻结配置未被改动

- `git log -1 --date=iso -- configs/v3` → `df12f57 2026-10-28 18:47:13 +0800 G|aa250: 12 行 AA 对齐落盘…`；`git log --oneline -- configs/v3` 仅两条（`5020c56` 冻结、`df12f57` AA250），冻结后无新提交。
- `git diff df12f57..HEAD --stat -- configs/v3` → **空**；`git status configs/v3` → 空。
- 复合 hash **可复算**：`causal_growth.v3_config.load_v3_protocol().config_hash`（`src/causal_growth/v3_config.py:107`，算法 = 七份 YAML 合并后 `json.dumps(sort_keys, separators=(",",":"))` 的 sha256）实测 = `00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3`，与 GOAL/G01 行引用逐字符相同。逐文件 sha：`business d1259d23…`、`design 8890d25b…`、`evaluation 5f6dfcb2…`、`execution 58623f85…`、`models 19ce3bf5…`、`policy 57ff5721…`、`scenarios b8fa1480…`。
- **纠正**：`out/scratch/r01_review/R01_report_concurrent_2243.md:94/146`（本轮并发写入的同名报告）称"仓库中没有可复算 00723dc2 的脚本/算法"——不成立，见上。

### 1.5 证据登记数与体积

- `outputs/evidence/coverage.json`：`records` = **93**、`total_bytes` = **16 975 748**、`source_label` = "合成数据 / 已知 DGP"、`last_refreshed_at` = `2026-10-31T19:36:47+08:00`；93 条 `bytes` 求和 = 16 975 748（自洽）。
- `outputs/evidence/g03_formal/coverage.json`：`records` = **357**、`total_bytes` = 5 254 002。
- 随机 5 条（`random.seed(20261031)`）：`f02_n200k_rep0/five_tables/manifest.json` 25 016 B `b3a61c2e…`、`e_evidence_rep0_b/v3_phase_E_random_summary_cf.csv` 2 522 B `799fa959…`、`test_runs/pytest_full_20261028_1642.json` 2 455 B `94aa5b1e…`、`aa/manifest_L2.json` 5 834 B `070b379a…`、`g_smoke/snapshot_binding.json` 5 781 B `583ebeb5…` → **5/5 MATCH**。
- 顺带全量复算 93 条：**0 不符**（sha256 + bytes 双比）。
- 口径说明（P3-1）：93 条 / 16 975 748 B 是**顶层登记子集**，磁盘 `outputs/evidence/` 实为 **608 个文件 / 30 MB**（`du -sh` 30M），另有 502 个文件不在顶层索引（各目录 `coverage.json` 另计）。GOAL 写"顶层 93 条"是准确的，但不可读作"证据包总量"。

### 1.6 门禁可跑（只读核查，未重跑）

`out/scratch/paper_gates/summary.txt`（2026-10-31 20:58）：

```
build=0
concat_chars=96416
claim_draft=0
claim_abstract=0
citations=0
long_draft=0
```

各 log 末尾：`claim_draft.log` "OK：290 条 claim 全部回指…（Tier1 290 / Tier2 0）"；`claim_abstract.log` 同句；`citations.log` "bib=12 引用键=12 引用次数=36 bbl=12 … OK"；`long_draft.log` 末行 "OK：长稿篇幅四项判据全部通过"；`build.log` "BUILD OK"。**RC 全 0，我未重跑 42/43/44**（§2 只以 43 源码函数在我进程内重算字数、并用 `pdftoppm` 自行渲染 PGM，属只读复算）。
补充（P3-3）：52 号链条里 42 只跑了 `claim_draft` 与 `claim_abstract` 两种模式（`scripts/52_paper_gates.sh:47–53`），"三态"的默认模式由 49 号 `--with-claims` 与 `v3_phase_H04_recheck2.md:27` 的复核覆盖，不在本日志里。

### 1.7 校验器未被削弱

| 脚本 | 最近改动 | 性质（实读 diff） |
|---|---|---|
| `17_merge_aa_layers.py` | `9c4f684`（+26/−1） | 删除行只有一句 `alpha = float(...) if "alpha" in ... else 0.05`（默认值兜底），改为强制要求列；新增 alpha/n_total/band 三类 raise。**只加强** |
| `19_finalize_local_power.py` | `4b07766`（+51/−9） | 唯一删除行是 docstring；新增 n_total/alpha/rate 与 rejections 自洽/唯一性检查。**只加强** |
| `33_register_evidence_top.py` | `08cce2b`（+7） | 新增 `--expect-complete`：磁盘有、索引无即 `return 5`（AGENTS §12.7 双向校验）。**只加强** |
| `41_export_g03_evidence.py` | `1b50641`（+47/−47） | 四处 `raise` 是抽成 `_post_export_self_check()` 函数（逐字保留判据），并新增 16 例夹具。**只加强**（重构，非删除） |
| `49_g04_closeout_precheck.py` | `08cce2b`（+48/−11） | 状态文件 3→4（加 `finalize.status`）、非零 `*_exit` 先于 `OK:` 判定、六个退出码全 0 + 完成行。**只加强** |
| `62_g04_tamper_drill.py` | `f92557d`（+25/−14） | 旧 `"重叠" not in out and "rep" not in out` → 必须命中 `分片间 rep 重叠`；`judge_tamper()` 可测。**只加强** |

未发现删检查、`raise`→`warn`、阈值放宽；删除行总数 6 处全部有等价或更强的替代。

### 1.8 Z01 清理影响

- `git show --stat cac1d7b`：**71 个文件**（70 个 v2 产物 + `docs/v3_Z01_v2清理记录.md` 50 行）。按目录：`outputs/tables` 49、`outputs/figures` 14、`outputs/figures/paper` 7、`docs` 1。按前缀：`r1_` 35、`r2_` 16、`r3_` 12、`fig0–fig6` 7、`v3_` 1（即记录本身）。**无任何 v3 表/证据被删**。
- 清理记录 `docs/v3_Z01_v2清理记录.md`：70 个 / 5 496 344 B、保留 100 个 v3 表、`paper/main.pdf` 3 895 224 B（`sha 3a2c08b8…`）、恢复命令、`40c7c48a…` 不可在盘上恢复但可 `git checkout 601f51d` 重建——如实披露，与实物一致。
- 现状：`ls outputs/tables | wc -l` = **100**，`grep -vc '^v3_'` = **0**；`ls outputs/figures` = **仅 `h01`**；`paper/main.pdf` 在（3 895 224 B，2026-10-27 09:57）。
- GOAL/文档引用抽查 3 条均存在：`outputs/evidence/g01_aa250/`（目录）、`outputs/evidence/d03_formal/shard0_summary.json`（glob 展开存在）、`outputs/evidence/test_runs/pytest_full_20261028_0321.{log,json}`（两文件均在）。GOAL 内 `outputs/...` 引用 9 处，除 2 处 glob/brace 写法外全部命中。
- 残留引用（可接受）：`scripts/01–05`（v2 管线生成端/画图端）仍写 `outputs/tables/r1_*.csv` 等；`tests/`、`paper/v3`、`src/` 零命中，v3 交付链不依赖被删产物。

### 1.9 交付卫生

- `git status --porcelain`：起始 0 行；当前仅 `?? docs/reviews/v3_phase_R01_review.md`（本报告）——但该文件在本轮审计中途被**另一进程**于 22:43 写入（见 P2-4）。
- `.workbuddy`：`git ls-files | grep -i workbuddy` → **空**。
- 分支：`* codex/d03 e1a78c0 [origin/codex/d03: ahead 74]`。
- 未推送：`git log origin/codex/d03..HEAD --oneline` → **74 条**（含 `cac1d7b`、`fac3558`、`e5b6d4b`、`601f51d`、`f92557d` 等全部收尾提交）。Z01/Z02 的交付物**目前只在本地**（P2-3）。

## 2. H02 独立机械核验（专节）

**口径取自源码，不抄文档**：`scripts/43_long_draft_audit.py:31–47` 的 `effective_chars()` —— 跳过空行与以 `#` 开头的标题行、跳过表格分隔行、删图片语法、`[text](url)` 保留 `text`、再删 `[#*_`\[\]{}|>~]` 等 Markdown 记号、最后 `len(re.sub(r"\s+","",line))`，即**非空白、去记号、含中文标点与行内公式字符**。我 `importlib` 载入该模块直接调用（保证逐字同口径），对 `paper/v3/body/01_intro.md`–`04_conclusion.md` 拼接后按 `#` 切章，另对构建输入 `out/scratch/v3_paper_build/body.md` 复算一次。

| 判据 | 我的独立计算 | 43 号 log（20:58） | 阈值 | 判定 |
|---|---|---|---|---|
| 引言 | 5 826 | 5 826 | — | 一致 |
| 研究方法 | 20 274 | 20 274 | — | 一致 |
| 结果与分析 | **44 617** | 44 617 | — | 一致 |
| 结论与展望 | 8 564 | 8 564 | — | 一致 |
| body 有效字 | **79 281** | 79 281 | — | 一致 |
| 结果占 body | **44 617 / 79 281 = 0.562770 → 56.28%** | 0.5628 | ≥50% | **PASS** |
| 实质页（墨迹 ≥0.015，去顶 5% / 底 8%） | 我 `pdftoppm -gray -r 50` 自行渲染 51 页后逐页算：body 页 5–51 中 **47 页全部达标**（最低 p51 0.0585，最高 p5 0.1805）；与 log 逐页 `dark_fraction` **max\|Δ\| = 4.9e-05**（渲染舍入） | body_substantive 47 | — | 一致 |
| 结果实质页（**代码口径**） | 19–51 共 **33** 页；33/47 = **0.702127 → 70.21%** | 33 / 0.7021 | ≥50% | PASS（但口径有缺陷） |
| 结果实质页（**真实结果章边界**） | 结果章 p19（含方法章尾部）到第 4 章标题所在 p45；整页计 **26** 页 → **55.32%**；把共享页 p45 计入 **27** 页 → **57.45%** | — | ≥50% | **PASS** |
| 总页数 | `pdfinfo` **51**；`main.pagemap` 物理 51 行（`51|50`） | 51 | 四部分 50–100 页 | PASS |
| 章起始页 | `main.aux`：`ch-intro{1}{4}`、`ch-method{2}{6}`、`ch-results{3}{18}`、`ch-conclusion{4}{44}`；经 `main.pagemap` 印刷→物理映射得 **5 / 7 / 19 / 45** | 5/7/19/45 | 一致 | PASS |
| 边界实读 | `pdftotext -f 19` 页首为 `2.7.2 / 2.8`、同页出现 `3.1`（章不另起页）；`-f 45` 页首为表 3-27（C278/C282/C286/C290）、同页出现 `4.1`；`-f 51` 为参考文献 [1]–[3] | — | 一致 | PASS |

**结论**：**有效字 56.28%（≥50%）与实质页 55.32%–70.21%（≥50%）均过，H02 两项机械判据成立。**

**必须同时说清的两处口径问题（P1-1）**：
1. `scripts/43_long_draft_audit.py:188` `res_end = total_pages`，`:189` 取 `starts[2] <= p <= res_end`，于是 `results_substantive` 实际是"结果章起点到**全文末页**"，把第 4 章 p45–50 与参考文献 p51 共 **7 页**算进了结果页。GOAL `:34`、`docs/v3_H03_编译审计.md:244` 引用的 33/47 = 70.21% 因此高估。
2. `:206` `results_share_of_all_pages` 的分母是 `len(substantive)`（47，已排除前置 4 页），与字段名"all pages"（51）不符；数值上又因前置页全部非实质而恰好等于 0.7021，进一步掩盖了问题。
3. 另一处非缺陷但需知情的现象：本次构建 47 个 body 页**无一被墨迹阈值排除**，因此"实质页占比"退化为"页数占比"（判据仍有效，但对"空页充数"不再有区分力）。

**`out/scratch/paper_gates/long_draft.json` 结论**：该文件 mtime **2026-10-30 00:07**，内容为 `results_char_share 0.5535`（结果章 42 818 / body 77 354）、`results_substantive 32` / `body_substantive 46`、p38 墨迹 0.0072——对应 `docs/v3_H03_编译审计.md:193`（§8）的**上一代构建**，**不是终构建**。52 号脚本不传 `--json`（`scripts/52_paper_gates.sh:56–58`），故终构建只有 stdout log。任何拿该 json 复核 H02 的人都会得到 55.35% / 69.57%（P2-5）。

## 3. 问题清单

### P0
无。未发现能推翻任一"通过"判定的证据问题；三件绑定产物、冻结配置、证据 93/357 条均逐字吻合。

### P1

**P1-1｜43 号"结果实质页"口径把第 4 章与参考文献计入结果页，GOAL/H03 §9 的 70.21% 高估 6–7 页**
- 位置：`scripts/43_long_draft_audit.py:188–189`、`GOAL.md:34`、`docs/v3_H03_编译审计.md:244`。
- 证据：见 §2；`res_end = total_pages`；p45 页首为结果表 3-27、同页才出现 `4.1`；p51 为参考文献。
- 影响：判据仍过（26/47 = 55.32%），**判定不变**；但验收证据里的数字与字段名不符，违反"报告每个数字要能追溯到口径"。
- 建议：`res_end = starts[3] - 1`（并把 p45 共享页的处理写进 docstring），同步改 GOAL `:34` 与 H03 §9 的 70.21% → 55.32%（或 57.45% 并注明共享页），再全文 grep `70.21` 确认无第二处残留（AGENTS §12.4）。

### P2

**P2-1｜GOAL 验收表 Z01/Z02 行仍为"未证实"，与顶部状态和实物冲突**
- 位置：`GOAL.md:39–40`（未证实）vs `GOAL.md:5`（"Z01 完成"）。
- 证据：§1.8、§1.9；Z01 有 `cac1d7b` + `fac3558` + 清理记录；Z02 有 97 行覆盖表 + 21:59–22:08 全量 pytest `exit=0` / 1432 点。
- 建议：R01 收尾时按证据改判，并把"未推送 74 条"写进 Z02 的剩余条件。

**P2-2｜G04 复核文件里的 pytest 点数 1424 与 GOAL 的 1432 冲突，只在 Z02 文档里被更正**
- 位置：`docs/reviews/v3_phase_G04_recheck.md:21/101/106/107/109/145`（1424）vs `GOAL.md:32`（1432）；更正说明只在 `docs/v3_Z02_全入口覆盖.md:80–82`（22:10）。
- 我的独立核验：三份全量日志进度点逐字符计数**均为 1432**（`pytest_full_20261031_2101/2142/2159.log`，`grep -o '\.'` = 1432，`lines=28`，F/E 标记 0），`2159.status` `exit=0`。**GOAL 正确，复核文件错**。
- 建议：不改被引用的复核报告原文可以，但 GOAL 指名的证据文件与 GOAL 数字不一致时应有可追溯的更正在场；建议在 G04 复核文件加一行更正注（与 Z02 同一句），并注意 `f92557d` 的提交信息里也写着 1424（提交信息不可改，需在文档中指认）。

**P2-3｜74 个提交未推送，交付物只在本地**
- 证据：`git log origin/codex/d03..HEAD --oneline | wc -l` = 74，含 Z01/Z02/H03/H04/G04 全部收尾。
- 影响：Z02「Git 干净」成立（工作树无改动），但"交付"未完成；远端 `origin/codex/d03` 落后 74 个提交。
- 建议：R01 结论提交后统一推送，并在 Z02 行记录推送后的远端 sha。

**P2-4｜同一报告路径被并发进程写入，工作树在审计期间非静止**
- 证据：审计起始（22:23）`git status --porcelain` 0 行；22:43:37 出现 `?? docs/reviews/v3_phase_R01_review.md`（17 733 B，206 行，署时 22:43），非我所写；我已原样备份到 `out/scratch/r01_review/R01_report_concurrent_2243.md` 并以本文件覆盖。
- 影响：违反 AGENTS §11「正式运行/评审期间不得并行写盘」的纪律；两份 R01 报告若都被提交会互相矛盾（该并发件 §4.1 的 P3-1 结论有误，见 §1.4 纠正；其 §2 "与 JSON 逐字相同"也不成立，见 P2-5）。
- 建议：由主负责裁定保留一份；若保留并发件，须先修其 P3-1 与 json 表述。

### P3

**P3-1｜"16 975 748 B"是顶层子集而非证据总量**：磁盘 608 文件 / 30 MB，顶层 93 条 / 17 MB；建议 GOAL/G03 行统一写"顶层登记 93 条 / 16 975 748 B（磁盘全量 608 文件）"。

**P3-2｜F01 与 H05 的"修后闭合"没有独立复核文件**：F01 的 RC-1/RC-2 修复文本我已实读（`docs/v3_phase_F01_ope.md:224–230/550`），H05 的 R-1 已是 2/11（`docs/v3_H05_sources.md:33`），实质可信，但闭合记录只存在于 GOAL 与被改文档。

**P3-3｜52 号链条只跑 42 的两种模式**：`claim_draft`、`claim_abstract`，默认模式不在 summary 中（由 49 `--with-claims` 与 H04 复核覆盖）。

**P3-4｜H01 复核文件标题仍为 PASS WITH CONDITIONS**：C1/C2 已 CLOSED，但文件本身没有"条件已闭合、可改判"的收尾行，与 GOAL 20:18 的改判之间靠 GOAL 单方衔接。

**P3-5｜旧 json 与旧 PDF 同名的中间产物易误用**：`out/scratch/paper_gates/long_draft.json`（10-30 00:07）与 `40c7c48a…` 旧 PDF 均已不在盘上/不可直接对应，建议 52 号加 `--json out/scratch/paper_gates/long_draft.json`，让门禁产物与终构建自洽。

## 4. 边界与未核项

1. **未重跑任何会写状态或重算的脚本**：62/63/66/51/49/33/40/41/42 一律未执行；第 6 项仅读 `summary.txt` 与 log 尾部。因此"门禁可跑"是"日志与 RC 自洽"层面的判定，不是本次重新跑出的绿。
2. **未重建 PDF**：51 页、CreationDate、sha 均取盘上终构建；未验证"从 `paper/v3` 源码可重建出同一 sha"（`xelatex` 会写新 CreationDate，本就不可字节复现）。
3. **未逐页视觉复核**：H03 的裁切/字体/缺字结论沿用 `v3_phase_H03_visual_recheck.md`，本轮只核 sha 与页数。
4. **未重算任何业务/统计数字**（FPR、CP、CATE、策略收益、claim 290 条的数值）：只核其登记完整性（sha）与门禁日志；这属于 H04/F02/G01 各自评审的范围。
5. **未验证 pytest 是否真的可复跑**：只读三份历史日志与 `.status`，未执行 `python -m pytest`。
6. **`out/` 不入库**：`out/scratch/paper_gates/*` 与 `out/scratch/v3_paper_build/*` 均为本地 scratch，其权威性依赖文档转述；§2 已用 PGM 重渲染独立复核了关键页。
7. **并发写入**：审计期间工作树被外部进程改动一次（P2-4），我无法保证 22:43 之后没有其他写盘；本报告的哈希/计数均在 22:23–22:58 之间逐项取。

## 5. 对改判的意见（独立评审身份，非替主负责决策）

- **H02：建议改判"通过"**，但**先修 P1-1**：正文证据应写"结果有效字 44 617 / body 79 281 = 56.28%；结果实质页 26/47 = 55.32%（代码口径 33/47 = 70.21% 含第 4 章，已更正）"。两项判据在两种页口径下都 ≥50%，结论不因修正而反转，因此"条件式改判"是稳的；若坚持引用 70.21%，等于把一个已知高估的数字留在验收表里，不符合本项目"证据先行"的标准。
- **R01：建议改判"通过"**，条件三条：① P1-1 落地并全文 grep 旧值；② GOAL `:39/:40` 按 §1.8/§1.9 改判 Z01/Z02（Z02 需写"74 提交未推送"的剩余项）；③ 裁定 P2-4 的两份 R01 报告保留哪一份。
- 不建议因 P2/P3 整体退回：A–H 的闭环链完整、条件闭合可查、绑定与证据逐字吻合，未发现任何"记录通过但无证据"或"数字反向"的实质缺陷。
