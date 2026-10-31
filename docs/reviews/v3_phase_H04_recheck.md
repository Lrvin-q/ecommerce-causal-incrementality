# H04 条件窄口径复核：C1–C4 是否真实关闭（2026-10-31 20:53，北京时间）

## 0. 对象、时间与方式

- 复核时间：2026-10-31 20:53（Asia/Shanghai）。复核对象是**工作树当前字节**，不是某个 commit。
- 复核方式：只读。未改 `paper/**`、`outputs/**`、`scripts/**`、`configs/**`、`GOAL.md`、`TODO.md`；未重编译、未跑 R>0 作业、未 commit、未改 42/52。写入仅本文件与 `out/scratch/h04_recheck/`。
- 前置评审：`docs/reviews/v3_phase_H04_review.md`（对 `f52d663` 判 `PASS WITH CONDITIONS`，C1–C4）。本次只回答"这 4 条是否关闭、是否引入新问题"，**不重做 H04 全文审计**。

| 对象 | 位置 | 实测 sha256 / 规模 | 与期望 |
|---|---|---|---|
| 新 PDF | `out/scratch/v3_paper_build/main.pdf` | `40c7c48a3e31d2e7fb68d0487d7f233f910e8a633b63308577f803225016c48c`；1 097 571 B；**51 页**；CreationDate 2026-10-31 20:48:30 +08 | 与指定 sha、页数**一致** |
| 主张登记表 | `outputs/tables/v3_h04_claim_registry.csv` | `5e921a92ef8b94bac51915cb2d33cc860b78fbbdd1c02ba0bed9c96cc3388833`；**72 099 B**；BOM=true；**291 个 CRLF**、0 个裸 LF/CR；**290 数据行**；ID `C01`–`C290` 连续无重；Tier1 290 / Tier2 0 | 与指定形态一致 |
| 结果章 | `paper/v3/body/03_results.md` | `0b747ec0a006d4af4fc6acd698afd0e6136296d791eb1068a7325558afa314ec`；1 532 行 | 旧 `f52d663` 为 1 531 行 |
| 摘要 | `paper/v3/abstract.md` | `a442c632adb9447e8f2bc64818aa0190840d60fb0436721bd86041e587599cbf`；7 行 | **未改**（与 H04 复核时同一 sha） |
| LaTeX 正文 | `out/scratch/v3_paper_build/body.tex` | `43ed40609b20b52f7998095e341535ac3ea8b845f7481c9599f4c6bdac189bf4` | 20:48 构建 |
| 42 号门禁 | `scripts/42_claim_number_gate.py` | `013b78593d235a004e1feee760f714062455e882528f5ade1be4074a83f8d24c` | 未改 |
| core 源表 | `outputs/tables/v3_g_g_core.csv` | `aa19561ee28a2ee635b6364d34d2822ea90b6156c6ea9e7980990fa7bc828ff2` | 未改 |

**改动范围（`git diff f52d663 -- paper/ outputs/`，逐行核对）**：仅 2 个文件、8 增 7 删。登记表只改 `C01.precision_note`（CSV 第 2 行）与 `C05.in_abstract`（CSV 第 6 行）；`03_results.md` 只改 L1479–1480、L1485、L1495（新增表注行）、L1507–1509。**没有超范围改动，C275–C290 十六行逐字节未动。**

**命令清单**（Windows Git Bash，项目根目录）：

```bash
sha256sum out/scratch/v3_paper_build/main.pdf outputs/tables/v3_h04_claim_registry.csv \
  paper/v3/body/03_results.md paper/v3/abstract.md out/scratch/v3_paper_build/body.tex \
  scripts/42_claim_number_gate.py outputs/tables/v3_g_g_core.csv
pdfinfo out/scratch/v3_paper_build/main.pdf | head -12
pdftotext -layout -enc UTF-8 out/scratch/v3_paper_build/main.pdf out/scratch/h04_recheck/main.txt
pdftoppm -f 45 -l 45 -r 150 -png out/scratch/v3_paper_build/main.pdf out/scratch/h04_recheck/p45
git show f52d663:outputs/tables/v3_h04_claim_registry.csv > out/scratch/h04_recheck/registry_old.csv
git show f52d663:paper/v3/body/03_results.md > out/scratch/h04_recheck/results_old.md
diff out/scratch/h04_recheck/registry_old.csv outputs/tables/v3_h04_claim_registry.csv
diff out/scratch/h04_recheck/results_old.md paper/v3/body/03_results.md
.venv/Scripts/python.exe scripts/42_claim_number_gate.py                       # 默认
.venv/Scripts/python.exe scripts/42_claim_number_gate.py --abstract paper/v3/abstract.md
cat paper/v3/body/0[1-4]_*.md > out/scratch/h04_recheck/draft.md
.venv/Scripts/python.exe scripts/42_claim_number_gate.py --draft out/scratch/h04_recheck/draft.md
.venv/Scripts/python.exe scripts/42_claim_number_gate.py --abstract out/scratch/h04_recheck/abs_no_100.md
.venv/Scripts/python.exe scripts/42_claim_number_gate.py --abstract out/scratch/h04_recheck/abs_change_100.md
.venv/Scripts/python.exe scripts/42_claim_number_gate.py --self-test
.venv/Scripts/python.exe -X utf8 out/scratch/h04_recheck/recompute16.py    # 16 条独立复算
grep -c "2026-10-30\|2 600\|检验统计量\|合计 600\|检验集 ATE" out/scratch/h04_recheck/main.txt
.venv/Scripts/python.exe -X utf8 -c "from scipy.stats import beta; ..."     # CP vs Wilson
```

---

## C1（原 P1）§3.11 的 Tier2 重复数与 D1=A 日期 — **CLOSED**

**原问题**：`03_results.md` L1479–1480 写"20 个 Tier2 机制格 × 30 次（合计 **2 600** 次重复）"，把 24 格总数挂在 Tier2 上（20×30=600）；D1=A 日期写 **2026-10-30**，与源记录不符。

**修复位置**：
- `paper/v3/body/03_results.md` L1479–1480："另有 20 个 Tier2 机制格 × 30 次（合计 **600** 次重复），按 **2026-10-29** 的 D1=A 裁决……"
- `out/scratch/v3_paper_build/body.tex` L3308–3309（同一句，pandoc 输出）。
- PDF 印刷页 **43**（PDF 第 44 页）同一句。

**独立证据**（三处一致 + 独立 grep 计数）：

| 检查 | 命令 / 位置 | 结果 |
|---|---|---|
| md 内 `2 600` / `2600` | `grep -rn "2 600\|2600" paper/v3/` | **0 处**（全论文、摘要、latex） |
| md 内 `600` 与 Tier2 同行 | L1479 | 1 处，`× 30 次（合计 600` |
| PDF 抽文 `合计 600` | `grep -c` | **1 处**，位于 PDF p44（印刷 43） |
| PDF 抽文 `2 600` | `grep -c` | **0 处** |
| PDF 抽文 `2026-10-30` | `grep -c` | **0 处** |
| PDF 抽文 `2026-10-29` | `grep -c` + 按页定位 | 2 处：p44（§3.11"按 2026-10-29 的 D1=A 裁决"）、p25（3.10 表注"2026-10-29 12:30 复算"，属另一事实） |
| 算术 | 20 × 30 | 600 ✓；core 仍写"共 2 000 次"（L1492），两者相加 2 600 与 24 格总数自洽 |
| 源记录 | `GOAL.md` L31"2026-10-29 20:41 用户裁决 D1=A"；`docs/v3_决策与反思日志.md` L4332"## 20:41 裁决落地：D1 披露、D2 50 页"，其所在日为 2026-10-29（L4252 起 `### 2026-10-29 …`） | 日期一致 |

**反例（不接受"改了一处"）**：上述 grep 是对**全论文目录 + LaTeX + PDF 抽文**三处分别计数，不是只看 L1479。若 md 改而 PDF 未重建，p44 计数会为 0 且仍是"2 600"——实测 p44 已是 600，说明 PDF 由改后 md 重建。

**判定：CLOSED**。唯一遗留（非 C1 缺陷）：`docs/v3_phase_G03_formal.md` §3.0 仍写"D1-A，2026-10-29 **22:52** 裁决"，与 GOAL/日志的 **20:41** 不一致；论文只写日期、规避了冲突，但三份文档的时分口径仍未统一，见 P3-2。

---

## C2（原 P2）C05 的 `in_abstract` 与摘要 1.00 — **CLOSED**

**原问题**：摘要 L3 写"退款率护栏通过率为 1.00"，但 C05 `in_abstract=no`，该 1.00 不在门禁绑定内。

**修复位置**：`outputs/tables/v3_h04_claim_registry.csv` 第 6 行（C05）`in_abstract` 由 `no` 改 `yes`；其余 10 个字段逐字节未变。摘要**未改**（sha 与 H04 复核时相同），即"改元数据、不改正文"。

**独立证据**：

| 检查 | 结果 |
|---|---|
| CSV 第 6 行字段 | `C05,3.6,F02 退款率护栏通过率,1.00,2,Tier1,**yes**,…,pass_rate,200 rep；单侧 alpha=0.05；margin 0.005` |
| `in_abstract=yes` 的集合 | `C01,C02,C03,C04,C05`（5 条，全部 Tier1） |
| 摘要 `1.00` 出现次数 | 1 次（`退款率护栏通过率为 1.00；`），语义正是 C05 的 statement |
| 42 默认模式 | **RC=0**，"290 条 claim 全部回指且与源表复算一致（Tier1 290 / Tier2 0）" |
| `--abstract paper/v3/abstract.md` | **RC=0**（同上） |
| `--draft <拼接稿>`（`cat 0[1-4]_*.md`，208 971 B） | **RC=0** |
| `--self-test` | **RC=0**，11/11 PASS（登记表改动未破坏已有反例夹具） |

**反例（当场跑）**：
- 副本 `abs_no_100.md`（把摘要唯一一个 `1.00` 换成 `100%`，原文件未动，sha `0e93a7cc…`）→ **RC=1**，`! C05: 摘要未包含注册值 1.00（in_abstract=yes）`。
- 副本 `abs_change_100.md`（`1.00`→`1.01`）→ **RC=1**，同一报错。

结论：摘要里的 1.00 **现在确实被 C05 绑定**；H04 复核 §5 里"删 1.00 仍 RC=0"的盲区在本条上已关闭。

**判定：CLOSED**。残留（P3-3）：绑定仍是**子串级**——`1.00` 同时是 C172/C173 的 `display_value`（`in_abstract=no`）。反例只证明"删掉字符串会拦"，不证明门禁能辨"这个 1.00 语义上是 C05"。这是 42 号 `check_abstract` 的既有设计限制（H04 复核 §4.2 已记录），非本次修复引入。

---

## C3（原 P2）表 3-27 表头"检验统计量" → "检验集 ATE" — **CLOSED**

**原问题**：表头与两处正文把 `ate_test` 叫"检验统计量"，实为检验子样本上的 ATE 均值。

**修复位置**：
- `03_results.md` L1485 表头：`| 格 | 净利润 ATE | **检验集 ATE** | 7 日付费率 | 30 日退款率 |`
- L1495 新增表注：`> 检验集 ATE 是检验子样本上的 ATE 均值（ate_test），不是 z/t 检验统计量。`
- L1508–1509 正文两处改述："检验集 ATE 的均值与全样本 ATE 均值几乎重合……检验子样本的 ATE 与全样本 ATE 没有系统位移"。
- `body.tex` L3338–3342（表体）、L3350（表注，`\texttt{ate\_\allowbreak{}test}` 折行处理）。
- PDF 印刷页 **44**（PDF p45）。

**与源码一致性**（`src/causal_growth/evaluation/v3_g_matrix.py` L506–522）：

```
test_frame = observations.loc[observations.split == "test"]
test = itt_difference_means(test_frame, "net_profit", …)
…  "ate_test": float(test.diff),   # 取的是 diff（均值差），不是 t/z 统计量
```

`itt_difference_means`（`src/causal_growth/estimate/itt.py` L117）返回 `diff = mean(T=1) − mean(T=0)`。故"\*\*检验子样本上的 ATE\*\*、不是 z/t 检验统计量"与源码逐字相符；`v3_models.py` L1854 的 `"ate_test": prediction.ate`（同文件 L2185 记作 `tau_hat_mean_test`）也是检验集预测均值，口径同向。

**PDF 裁切检查**：`pdftotext -layout` 抽出完整表头 `格 / 净利润 ATE / 检验集 ATE / 7 日付费率 / 30 日退款率`，表注整句以"不是 z/t 检验统计量。"收尾、无截断；150 dpi 渲染目检（`out/scratch/h04_recheck/p45-45.png`）：表头、四行数据、表注与后文段落均无重叠、无出血/裁切。H03 审计 §8 记的表头 Overfull 0.120 09 pt（≈0.042 mm）在目检中不可见。

**独立证据**：PDF 抽文全篇 `检验统计量` 仅 **1** 处，且正是表注里的否定句；`检验集 ATE` 3 处（表头、表注、L1508 正文，均在 p45）。**没有残留的旧标签**。

**判定：CLOSED**。

---

## C4（原 P3）C01 的 `precision_note` 由 Wilson 改为 Clopper–Pearson — **CLOSED**

**原问题**：备注写"Wilson CP [0.033871, 0.060884]"，标签与数值方法矛盾。

**修复位置**：`outputs/tables/v3_h04_claim_registry.csv` 第 2 行（C01）`precision_note` → `1000 rep 合并；Clopper–Pearson 95% 区间 [0.033871, 0.060884]`；数值未变。

**独立复算**（x=46、n=1000，`scipy.stats.beta` 分位数，不调用项目函数）：

| 方法 | 下界 | 上界 | 6 位舍入 |
|---|---:|---:|---|
| Clopper–Pearson（beta 精确） | 0.03387149854767792 | 0.060883552713742635 | **0.033871 / 0.060884** |
| Wilson（正态近似） | 0.03466249276326499 | 0.06081220394161907 | 0.034662 / 0.060812 |

登记值与 CP 完全一致（差 0），与 Wilson 下界差 0.00079，故旧标签确属误标。源表 `outputs/evidence/g01_aa250/recomputed_fpr.csv` 的 POOLED 行 `cp_low=0.03387149854767792, cp_high=0.060883552713742635` 与本次复算逐位相同，且生成函数为 `v3_aa.py` 的 `clopper_pearson()`（L238–270）——备注与实现同源。

**反例/交叉检查**：全库 `Wilson` 在登记表、`paper/**` 中 **0** 处（`src/causal_growth/design/aa.py` 与 `evaluation/v3_aa.py` 里的 Wilson 是另一套玩具 AA 的注释，非本 claim 源）；摘要 L3 "Clopper–Pearson 95% 区间"与备注一致；42 默认/`--abstract` RC=0（C01 仍可复算为 0.046）。

**判定：CLOSED**。

---

## C275–C290 十六条数值不变性（新登记表重跑）— **16/16 一致**

独立脚本 `out/scratch/h04_recheck/recompute16.py`（自实现：读登记表→在 `v3_g_g_core.csv` 命中 1 行→按 `decimals` 舍入→对 per-rep 均值 / `recomputed_summary.csv` / `coverage.json` sha）。结果：

- 16/16 `display_value` 与 core `mean` 舍入值**逐一相等**，且与 H04 复核 §3 表**逐位相同**（C275 0.2434 … C290 0.0068）。
- 16/16 per-rep 文件 500 行、逐 rep 均值与 core 均值差 < 1e-12、`sd(ddof=1)/√500` 与 core `MC_SE` 差 < 1e-12、`coverage.json` sha256 与磁盘文件全部 `ok`。
- 登记表 diff 只涉及第 2、6 行，C275–C290 所在行**逐字节未动**（结构性证明，不依赖脚本）。
- 明细：`out/scratch/h04_recheck/c275_c290_recompute_new.csv`。

---

## 新问题

**P1：0 条。**

**P2：1 条。**

| 编号 | 问题 | 证据 | 建议 |
|---|---|---|---|
| P2-1 | C1–C4 的**修复字节尚未入库**：`outputs/tables/v3_h04_claim_registry.csv`、`paper/v3/body/03_results.md` 仍是工作树 `M` 状态；HEAD 为 `08cce2b`（G04），`f52d663` 里的登记表/结果章仍是旧值（`181e21a0…` / `3145517…`）。PDF 本来就不入库，但 md/CSV 若不提交，任何人 `git checkout` 即回退，C1/C2/C4 会"复活"。 | `git status --porcelain -- paper/ outputs/` 只有这 2 个 `M`；`git log -- outputs/tables/v3_h04_claim_registry.csv` 最后一条是 `f52d663` | 改判前把这两处与本复核报告一起提交，并在提交后重算 sha；若 sha 与本报告 §0 不符，需重新窄复核 |

**P3：3 条（均为记录/门禁边界，不阻断关闭）。**

| 编号 | 问题 | 证据 | 影响 |
|---|---|---|---|
| P3-1 | 论文只写"2026-10-29 的 **D1=A 裁决**"，未说明裁决内容（机制键无消费方、该格不计入有效机制证据、24 格有效 23 格）。GOAL G03 行要求"报告与论文写作时沿用同一句"。 | 全论文 `grep immature\|23 格\|24 格\|D1` 只命中 L1480 一处，且无内容解释 | 读者无法从论文自解"D1=A"；属**既有**问题（旧文本同样如此），不由本次修复引入 |
| P3-2 | D1 裁决时分口径未统一：`GOAL.md` L31 / 日志 L4332 = **20:41**；`docs/v3_phase_G03_formal.md` L254 = **22:52**。 | 两处原文 | 论文已只写日期，规避了冲突；文档层仍不一致，建议统一或在 G03 报告注明两个时刻各指什么 |
| P3-3 | 42 号 `check_abstract` 仍是子串绑定：`1.00` 同时是 C172/C173 的 display 值（`in_abstract=no`），门禁只验证"C05 的值出现在摘要"，不验证语义归属。另 `0.060884` 仍只挂在 C01 备注、无独立 claim 行（H04 复核 §6 第 10 条）。 | 登记表 `display_value==1.00` 的 3 行；`check_abstract` L95–L108 | 本次反例只到"字符串级"，门禁强度未提升；属既有设计边界 |

---

## 结论

**CLOSED（C1–C4 全关，可改判）**，附一条交付前置（P2-1）。

- C1 **CLOSED**：md / LaTeX / PDF 三处均为"合计 600 次重复"+"2026-10-29"；`2 600`（挂在 Tier2 上）与 `2026-10-30` 在论文与 PDF 抽文中均为 0 处；与 GOAL/日志的 2026-10-29 一致。
- C2 **CLOSED**：C05 `in_abstract=yes`；三模式 RC 全 0；反例"删 1.00 / 改 1.01"均 RC=1 且指名 C05，绑定真实生效。
- C3 **CLOSED**：表头改"检验集 ATE"，表注定义 `ate_test`，两处正文改述；与 `v3_g_matrix.py` L506–522 口径相符；PDF p45（印刷 44）表头与表注无裁切。
- C4 **CLOSED**：C01 备注改 Clopper–Pearson；x=46/n=1000 独立复算 CP=[0.033871, 0.060884] 与登记值一致，Wilson 下界 0.034662 与之不符，旧标签确系误标。
- 16 条数值不变性：**16/16 一致**，C275–C290 登记行逐字节未动。

**改判前置**：先提交 `outputs/tables/v3_h04_claim_registry.csv` 与 `paper/v3/body/03_results.md`（P2-1），并把改判绑定到本报告 §0 记录的 sha（PDF `40c7c48a…`、登记表 `5e921a92…`、结果章 `0b747ec0…`）。若提交后任何一个 sha 变化，本复核效力不延伸，需重新窄复核。

**效力边界**：本复核**只覆盖 C1–C4 与 C275–C290 十六条数值不变性**；未重做 H04 全文审计（290 条逐条复算、上标 397/290、摘要 Tier2 泄漏、52 号五门禁、53 号页面扫描等均沿用 H04 复核结论），未重编译，未重跑 52，未跑任何 R>0 作业，未评估 PDF 的字体/盒溢出/目录等排版项（只对表 3-27 页做目检）。周边 `scripts/62`、`scripts/66` 的未提交修改属 G04，不在本次范围。

复核产物：`out/scratch/h04_recheck/`（`main.txt`、`p45-45.png`、`registry_old.csv`、`results_old.md`、`draft.md`、`abs_no_100.md`、`abs_change_100.md`、`gate_*.txt`、`recompute16.py`、`c275_c290_recompute_new.csv`）。
