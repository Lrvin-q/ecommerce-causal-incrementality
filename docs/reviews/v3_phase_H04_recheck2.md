# H04 条件窄复核 #2：重建后 C1–C4 重绑（2026-10-31 21:01，北京时间）

## 0. 对象与方式

- 复核时间：2026-10-31 21:01（Asia/Shanghai）。只读：未改 `paper/**`、`outputs/**`、`scripts/**`、`configs/**`；未 commit、未 push；写入仅 `out/scratch/h04_recheck2/` 与本报告。命令均设 `PYTHONUTF8=1`，退出码单独取、不接管道。
- 背景：H03 P1 修复（图 3-4 来源注分页）重建了 PDF，旧窄复核绑定的 PDF `40c7c48a…`、结果章 `0b747ec0…` 失效；本次只重绑 C1–C4 并确认修复未碰坏它们，不重做 H04 全文审计。

| 对象 | 实测 | 期望 | 结论 |
|---|---|---|---|
| `out/scratch/v3_paper_build/main.pdf` | `415d59fe1e282b6ad203db17576faca5bb073e87ebdf4b914dffb9bef8924da0`；51 页；CreationDate 2026-10-31 20:58:32 +08 | 同 | 一致 |
| `paper/v3/body/03_results.md` | `6d7b26347a0aa5e371dcc491dffb230eeb6989edf20f067b9f91f7efc954c469`；`e5b6d4b`，工作树干净 | 同 | 一致 |
| `outputs/tables/v3_h04_claim_registry.csv` | `5e921a92ef8b94bac51915cb2d33cc860b78fbbdd1c02ba0bed9c96cc3388833`；BOM=true；291 CRLF、0 裸 LF；290 数据行 | 同 | 一致 |

支撑文件未动（与旧复核同 sha）：`v3_g_g_core.csv` `aa19561e…`、`abstract.md` `a442c632…`、`42_claim_number_gate.py` `013b7859…`。

## 1. 改动范围（`git diff 601f51d e5b6d4b -- <两文件>`）

- `03_results.md`：仅 1 个 hunk（L1360–1379），14 增 10 删，全部落在图 3-4 块：`center` 环境 + `width=0.80` + 独立题注 + `>` 引用块 → `figure[H]`，图宽 **0.74**，题注与 `\footnotesize\raggedright` 来源注进同一浮动体。**无其他改动。**
- `v3_h04_claim_registry.csv`：**零改动**。两 commit 的 blob 同为 `97cbb846…`，`git diff --quiet` RC=0。
- `e5b6d4b` 另仅新增 `docs/v3_H03_编译审计.md`（非论文产物）。

## 2. C1–C4 逐条

| 条件 | 判定 | 证据 | 备注 |
|---|---|---|---|
| C1 §3.11 的 600 次与 D1=A 日期 | **CLOSED** | md L1483–1484、PDF p44（印刷 43）："20 个 Tier2 机制格 × 30 次（合计 600 次重复）" + "2026-10-29 的 D1=A 裁决"；`2 600`/`2600`/`2026-10-30` 在 paper 的 md/tex 与 PDF 抽文均 0 处 | 字面 grep `paper/v3` 有 1 处 `2026-10-30`，在 `build.sh:31` 维护注释（`601f51d` 已存在、不进 PDF），见 P3-1 |
| C2 C05 摘要绑定 | **CLOSED** | 登记表第 6 行 C05 `in_abstract=yes`；42 号默认 / `--abstract` / `--draft` 三态 **RC=0**；负例 `abs_no_100.md` **RC=1**，`! C05: 摘要未包含注册值 1.00（in_abstract=yes）` | 绑定仍是子串级（旧 P3-3 遗留），见 P3-2 |
| C3 表 3-27 表头/表注 | **CLOSED** | md L1489 表头"检验集 ATE"；L1499 表注含"检验子样本上的 ATE 均值（ate_test），不是 z/t 检验统计量"；PDF **p45**（印刷 44）抽文完整，120 dpi 目检表头、四行、表注无裁切；`v3_g_matrix.py:522` `ate_test=float(test.diff)`，`itt.py:117` `diff=mean(T=1)−mean(T=0)` | 全 PDF "检验统计量" 仅 1 处，即表注否定句 |
| C4 C01 方法标签 | **CLOSED** | C01 `precision_note` = "1000 rep 合并；Clopper–Pearson 95% 区间 [0.033871, 0.060884]"，数值未变 | — |

## 3. C275–C290 十六条不变性

- 登记表 sha 与旧复核一致，且 `601f51d`→`e5b6d4b` blob 相同，C275–C290 所在行**逐字节未动**（结构性证明）；290 行 ID 唯一，C275–C290 全在。
- 抽查：C275 `0.2434` 对 core `mean=0.2434178407…`；C290 `0.0068` 对 `mean=0.0067699485…`，按 decimals=4 舍入一致。

## 4. 新问题

- **P0：0；P1：0；P2：0。**
- **P3-1（记录）**：`paper/v3/build.sh:31` 注释含 `2026-10-30`（H03 审计日期），不渲染、不是 D1=A 日期，`601f51d` 即存在；若 C1 的"paper/v3 0 处"按字面递归含脚本则计 1 处，建议验收口径写明"论文内容 + PDF"。
- **P3-2（继承）**：42 号 `check_abstract` 仍为子串绑定，`1.00` 也出现在 C172/C173（`in_abstract=no`）；负例只证明删字符串会拦，不证明语义归属（旧复核 P3-3，无新增风险）。
- **P3-3（继承）**：论文未解释 D1=A 内容；`GOAL.md`/日志 20:41 与 G03 文档 22:52 的时分口径仍不一致（旧复核 P3-1/P3-2）。

## 5. 总判

**PASS**：C1–C4 全部 **CLOSED**；重建只动图 3-4 块，登记表与 16 条数值零变化。顺带目检 p42（印刷 41）：图 3-4、题注、来源注同页且完整，H03 P1 修复未引入可见裁切，也未碰坏 C1–C4。

**效力边界**：只覆盖 C1–C4 + C275–C290 十六值 + 图 3-4/表 3-27 两页目检；未重做 H04 全文 290 条逐条复算，未跑 52/53 号门禁，未跑 R>0 作业，未评字体/目录等排版项。

产物：`out/scratch/h04_recheck2/`（`paper.txt`、`p45.png`、`p42.png`、`draft.md`、`abs_no_100.md`、`gate_*.log`）。
