# F02 收尾复核条件 C1–C6 落地复核（2026-10-28 21:55，北京时间）

> 合成数据 / 已知 DGP。独立子代理复核；**全程只读**，唯一写盘是本报告。
> 一句话：**C1–C6 六条全部按字面落地，所有正文数字与磁盘重算逐条相符**；
> 但本次修复在 `validation` 里留下一处**新造的自相矛盾**（§0 仍写"独立科学评审未做"，与 `formal:21` 的"已做：19:17 + 21:43"直接对立），
> 故最终判 **NOT CLOSED**，最小修复是改一格 + 两个同类残留（详见 §4）。

## 1. 复核对象与快照

- 工作树 `C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目`，分支 `codex/d03`。
- **HEAD = `c13a8cd`（2026-10-28 21:50:39 +0800）**，复核全程未前移（开工与收尾两次 `git log -1` 同值）；
  `git status --porcelain` 复核前后均为空（工作树 = HEAD，无未提交改动）。
- `git diff --stat c13a8cd~1 c13a8cd` 涉及 12 个文件，**全部为文档 / 两份 coverage.json / 支出表 CSV / 本轮上一份复核报告**，
  无 `src/`、`sql/`、`configs/` 改动 ⇒ 不触发 AGENTS §11 的绑定 glob，也不需要任何 R>0 作业。
- 复核时刻：`date` = 2026-10-28 21:54；本报告落盘 **21:55:28**（`stat` 实测，北京时间）。
- 唯一运行过的可执行命令是 `scripts/33_register_evidence_top.py --dry-run`，**exit 0**；运行前后两个 `coverage.json`
  的 mtime / 字节数完全未变（21:48:21.442 / 52 865 B、21:48:21.441 / 7 745 B），确认 `--dry-run` 未写盘。

| 对象 | sha256 | bytes | mtime |
|---|---|---|---|
| `outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv` | `dbb8a8696ffe67d7c1d8cb2aaae24d77b2309f1256b5f5555a1d52561401171a` | 119 025 | 21:45:40 |
| `outputs/evidence/coverage.json` | `fe80b7079f1b95d7…` | 52 865 | 21:48:21 |
| `outputs/evidence/f02_formal/coverage.json` | `c60f2cb4a41f4344…` | 7 745 | 21:48:21 |
| `docs/v3_phase_F02_formal.md` | `a4e6967b743abcd2…` | 18 259 | — |
| `docs/v3_phase_F02_validation.md` | `16a2d017a0c13a4f…` | 27 811 | — |

## 2. C1–C6 逐条判定

| 条件 | 判定 | 证据（文件:行） | 我的实测读数 |
|---|---|---|---|
| **C1** 删"未落盘/只部分关闭"，指向新表，保留"旧表=历史"；同步 TODO | **已关闭** | `docs/v3_phase_F02_formal.md:127-130`、`:174-175`；`TODO.md:27-28`、`:42-52` | 正文 127-130 已改为指向 `…_per_rep_spend_full.csv` 并写 "`budget_cny` = 0.2 × `n_assigned`"、"旧表保留为历史，其 `predicted_note` 的'未落盘'表述**是错的**"；`:174` 局限条改为"已补全，P1-1 关闭（21:48）"。全文 grep `只部分关闭`/`部分关闭` = 0 命中（仅 `docs/reviews/*` 历史评审文件保留原文，属正确用法）。TODO:27 旧句"（P1-1 预测支出运行期未落盘）"已换成"C1–C6 已 21:48 落地，待窄口径复核确认后才改判" |
| **C2** 撤"sha256 与 bytes 全部一致"断言 | **已关闭** | `docs/v3_phase_F02_formal.md:146`（另 `:19` 同步） | `:146` 现为"逐个重算 sha256 **全部一致**（`bytes` 未在 manifest 记录，见 §1 表，**未按 bytes 复核**）"。我实读 `out/f02_formal/shard0/rep0/five_tables/manifest.json`：`artifacts` 为 **26 键字典**，键频 `role`26/`sha256`26/`rows`23/`columns`23/`dataframe_sha256`23，**含 `bytes` 的 0 个**；26/26 个文件的 sha256 **与磁盘逐个相符**（ok 26 / missing 0 / bad 0）⇒ 新表述准确，P2-2 不会复发。全文 grep "bytes 全部一致" = 0 命中 |
| **C3** 新表补 `budget_cny`，标注 `no_coupon` 的 0.0 语义 | **已关闭** | `…per_rep_spend_full.csv` 第 12–15 列；`docs/v3_phase_F02_validation.md:193`；`formal:128-129` | 400/400 活跃臂行 `budget_cny` **逐行等于 0.2×`n_assigned`**（最大绝对差 **0.0**）；`no_coupon` 200 行：`budget_cny=0.0`、`budget_deviation_cny=0.0`、`budget_note="no_coupon 臂无券预算；budget_deviation 按 0 定义"`（200/200 同值）、`within_budget=True`。`budget_deviation_cny` 对活跃臂确为 `predicted − budget`（最大差 **0.0**）；`dev>0` 行数 **0**、`within_budget=False` 行数 **0**。列名实测 16 列，新增唯一列是 `budget_note`（旧 15 列全同，见 §3） |
| **C4** validation 写死"合并=按 rep 加总的总量比"并注明 3e-6 | **已关闭** | `docs/v3_phase_F02_validation.md:195`、`:198-199` | `:195` 现为"**合并 = Σ实际 / Σ预测** = **1.056348**"；`:198-199` 单列一条"**口径差 3e-6**：formal §5.3 的 1.056345 / 1.002839 是逐 rep 比值的算术均值，与本段总量比不同；两者都对，不得并置成一个数"。我复算 pooled 定向 **1.056347991**、随机 **1.002835123**；比值均值 定向 **1.056345050**、随机 **1.002839140** ⇒ 两处数字各自都对，差值 2.9e-6 / 4.0e-6，正文"3e-6"量级正确 |
| **C5** repair 条目改 `added`（形状同 33 号）+ 时刻更正 + 补 `refreshed` 对象条目 | **已关闭** | `outputs/evidence/coverage.json` `registry_repairs[13]`、`[14]`（15 条 repair，最后两条） | `[13]`：`"added": ["outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv"]`（**字符串数组**）、`at="2026-10-28 21:38"`、新增 `corrected_at="2026-10-28 21:48"` 与 `correction` 说明"原条目 at=21:42（计划时刻，实际写盘 21:38:25），且把新增文件放进字符串数组 refreshed"。`[14]`：`refreshed` 为**对象数组**，键序 `target/old_sha256/old_bytes/new_sha256/new_bytes`，值 `8219660498fe…`/101 666 → `dbb8a8696ffe…`/119 025，**与 git 里旧表字节完全一致**（见 §3）。源码比对：`scripts/33_register_evidence_top.py:445` 写 `"added": [r["target"] for r in added]` ⇒ 字符串数组一致；33 号本身不产出 `refreshed`，而既有 `[1]`/`[5]` 的 5 键对象形状与 `[14]` 逐键相同 ⇒ 形状一致。目录级 `f02_formal/coverage.json` 的 `repaired_at=2026-10-28 21:48` 与 `repair_note` 已把"21:42"改成"实际写盘 21:38:25"的说明写入 |
| **C6** formal 计数改 77 / 16 924 056；validation 抬头与 §5.3 标题更新 | **已关闭** | `docs/v3_phase_F02_formal.md:20`；`docs/v3_phase_F02_validation.md:4-6`、`:19`、`:232` | `formal:20` 实读"…21:48 重导出该表（补 `budget_cny`/`budget_note`）后 **77 / 16 924 056**（21:48 实读）"；我实读 77 条、`total_bytes` **16 924 056**、逐条求和 **16 924 056**（相等）。`validation:4-6` 现为"**正式 200 rep 已于 2026-10-28 16:37 完成**"；`:19` 状态行"已完成（03:39 起跑、16:37 合并…登记号 `F02-FORMAL-20261028-R200`）"；`:232` §5.3 标题"正式 200 rep（2026-10-28 16:37 完成，200/200）"。全文 grep `16,906,697`/`16 906 697` = 0 命中（仅历史评审文件与 coverage.json 审计轨迹保留旧值，属正确用法） |

## 3. 独立复算表

口径：定向 = `selected_targeted_policy`，随机 = `random_same_budget`，分母 200 个 rep。

| 项 | 正文 | 我的复算（从 CSV 重算） | 判定 |
|---|---|---|---|
| 表结构 | 600 行 / 三臂 | 600 行 × 16 列；rep 0–199 × 3 臂，`(rep_id,arm)` 重复 0、缺失 0；四片各 150 行 | 一致 |
| 定向 **pooled**（Σ实际/Σ预测） | 1.056348 | **1.056347991** | 一致（validation:195） |
| 定向 **逐 rep 比值均值** | 1.056345 | **1.056345050** | 一致（formal:131） |
| 定向 min / 中位 / max（比值） | 0.945840 / — / 1.306675；超支 −5.42% / +5.09% / +30.67% | 0.945840 / 1.050860 / 1.306675；−5.4160% / +5.0860% / +30.6675% | 一致 |
| 定向 为正 rep 数 | 179/200 | **179/200**（负 21、等于 1 的 0） | 一致 |
| 随机 **pooled** | 1.002835 | **1.002835123** | 一致 |
| 随机 **比值均值** | 1.002839 | **1.002839140** | 一致（formal:132） |
| 随机 min / 中位 / max | 0.938633 / — / 1.088988；−6.14% / +0.11% / +8.90% | 0.938633 / 1.001147 / 1.088988；−6.1367% / +0.1147% / +8.8988% | 一致 |
| 随机 为正 rep 数 | 104/200 | **104/200**（负 96、等于 1 的 0） | 一致 |
| 定向真实人均 / max | 0.211268 / 0.261322 | 0.211268 / 0.261322 | 一致 |
| 随机真实人均 / max | 0.200567 / 0.217798 | 0.200567 / 0.217798 | 一致 |
| 预测/人 ≤ 0.2 | 最大值"恰为 0.200000" | 定向 max 0.199999997469、随机 max 0.199999999833（均 <0.2）；定向 min 0.199989799568 | 一致 |
| 最大预算偏差（总额） | −0.6779 元（targeted rep126，n=66 456，−1.020e-5/人） | rep126 n=66 456、dev **−0.6778799**、人均 −1.0200e-5 | 一致 |
| 最接近 0 的偏差 | random rep110，n=66 325，−1.1e-5 元 | rep110 n=**66 325**、dev −1.1043e-5、人均 −1.665e-10 | 一致（旧文"n=66 713"已改正，66 713 是 rep 0 随机臂） |
| `budget_cny` = 0.2×`n_assigned` | 正文声明 | 活跃臂 400/400 精确相等（最大差 0.0）；`no_coupon` 200/200 = 0.0 且有 `budget_note` | 一致 |
| 旧表 → 新表"表内数字未变" | 日志 21:50 声明 | 从 git `c13a8cd~1` 取旧表：101 666 B / `8219660498fe…`（= 登记里的 old 值）；15 个共有列 **0 处差异**，仅新增 `budget_note` 并把 `budget_cny` 由 600/600 空值填满 | 属实 |
| 顶层登记 | 77 条 / 16 924 056 B | 77 条；逐条 sha256+bytes 对磁盘 **77/77 相符**、0 缺失；`total_bytes` = 逐条求和 = **16 924 056**；新表记录 `bytes 119 025` / `sha dbb8a869…` / `rows 600` 与磁盘一致；`注册有而磁盘无` 0 条 | 一致 |
| 目录级登记 | 20 件 | 20 条；**20/20** sha+bytes 相符；磁盘 20 个文件与索引 **双向无差** | 一致 |
| `33 --dry-run` | 全表复算一致、未写盘 | exit **0**；"候选身份类文件 26 个：新增 0，已登记 26"；"**顶层全表复算一致：77 条**"；"无新增、无字段补齐，不写盘（幂等）"；两份 coverage.json mtime 未变 | 一致 |
| 26 个五表 artifact | "sha256 全部一致，bytes 未记录" | 26/26 sha256 对磁盘相符；artifacts 键中无 `bytes` | 一致 |
| 行尾/编码卫生 | — | `.md` 五件 + 决策日志：`i/lf w/lf`；两份 `coverage.json`：`i/crlf w/crlf` 且无 BOM（首字节非 EF BB BF）；支出表：UTF-8 **BOM**、`\n` 601 个、`\r\n` **0** 个 | 一致 |

## 4. 新发现

### P2-1｜`validation` 的"独立科学评审 未做"与 `formal` 的"已做"直接对立（**本次修复新造**）

- `docs/v3_phase_F02_validation.md:21` 仍是 `| 独立科学评审 | **未做** | — |`。
- 同一次提交把 `docs/v3_phase_F02_formal.md:21` 改成了"已做：19:17 **PASS WITH CONDITIONS** …；21:43 收尾窄口径复核 **PASS WITH CONDITIONS**"，
  而 `GOAL.md` F02 行、`TODO.md:52`、`AGENT_HANDOFF.md:15-16` 也都写"已返回评审/条件已落地"。
- 定性：单看 `validation` 会得出"该阶段从未被独立评审"的结论，与主结果文档互斥；这正是 AGENTS §12.4
  "改完一处要全文 grep 旧值"要防的形态（本次 grep 了 `未落盘`/`65 条`/`16,906,697`，但没 grep 评审状态）。
- 最小修复：把 `:21` 改成"已做：19:17 PASS WITH CONDITIONS（`v3_phase_F02_review.md`）、21:43 收尾复核 PASS WITH CONDITIONS（`v3_phase_F02_closeout.md`）；
  C1–C6 已落地，**仍待窄口径确认**"，与 `formal:5-8` 同话术。**不需任何数据作业**。

### P3-1｜`validation:242` §5.4 标题仍写"（工具已就绪，未运行）"

§5.4 讲的是分片/合并/聚合三件工具，实况是 03:39 起跑、16:37 合并、200/200 完成，`§0:19` 与 `§5.3` 都已改，
唯独这个标题没改，同文自相矛盾（与 C6 要处理的"未运行"同类，属漏 grep）。建议改"（已运行：四片各 50、16:37 合并完成）"。

### P3-2｜"21:48 重导出该表"与实测 mtime 21:45:40 差 2 分半

`formal:20/129/174`、`validation:192`、`AGENT_HANDOFF.md:15`、`GOAL.md` F02 行、`TODO.md:42/49`、
`f02_formal/coverage.json` 的 `repair_note` 都把"重导出/补分母"记在 **21:48**；磁盘 mtime 是 **21:45:40**，
21:48:21 是两级 `coverage.json` 的登记时刻。决策日志 21:50 条自己也写了"实际写盘是 21:45:40（CSV）与 21:48:21（coverage）"。
与 P2-E 的差别方向相反（这次是"声明晚于写盘"，不会伪造未来时刻），但 AGENTS §10 要求写实测分钟。
建议全库改成"21:45 导出、21:48 登记"，或在此类句子后统一加"（登记时刻）"。

### P3-3｜`formal:19` 措辞错位："未按 manifest 复核"

原句"26/26 产物 sha256 一致（`bytes` 未在 manifest 记录，**未按 manifest 复核**）"——sha256 恰恰就是按 manifest 复核的，
要表达的是"未按 `bytes` 复核"（`:146` 写的才是正确版本）。建议按 `:146` 统一。

### P3-4｜决策日志 21:50 把两处旧数字错记成"复核报告说的"

`docs/v3_决策与反思日志.md:2810-2812` 写"**复核报告里有一处数字经我核为错**：它说 `formal:122` 的随机 rep110 是 n=66 713 …
同处的'最大预算偏差 −1.1e-5 元'…"。实测 `docs/reviews/v3_phase_F02_closeout.md` 全文 grep `66 713`/`66713`/`1.1e-5` **均 0 命中**：
这两处数字来自 **c13a8cd 之前的 formal 旧文本**，不是复核报告的意见。结论（66 325、−0.6779 元）为真，但归属写错了，建议改为"formal 旧文本"。

### P3-5｜决策日志 21:50 "未重导出任何结果表"与同段 C3 表面冲突

同段紧接着写"表 101 666 → **119 025 B**、sha `82196604…` → `dbb8a869…`"。建议改为"未重跑任何 rep、未重算任何聚合数字，
仅重导出支出表以补列"（`formal:20` 用的正是"重导出该表"，两处措辞需统一）。

### P3-6｜`formal:20` 的"21:34 补 4 条聚合"是**目录级**动作，写在顶层登记句里易误读（历史遗留）

`TODO.md:29-31` 与目录级 `repair_note` 都写明 21:34 是"目录级 15→19"，顶层 `records` 当时仍为 76；
而 `formal:20` 这句话的主语是顶层登记（records / `total_bytes`），读起来像 21:34 也增了顶层记录。
另：19:30 那 11 条在 `registry_repairs` 里**没有对应条目**，链条从 `[7]` 的 54 条直接跳到 `[8]` 的 `records_before=65`
（数字自洽：54+11=65、16 746 236 与 `[8]` 的 before 值相同），但审计轨迹缺一环。属本提交之前就存在的 P3。

### P3-7｜顶层索引仍不覆盖非身份类 CSV（历史遗留，非新增）

`outputs/evidence/` 下 150 个文件中有 73 个不在顶层 `records`（多为子目录 `coverage.json` 覆盖的聚合表/日志，
如 `f02_formal/arm_summary.csv` 已由目录级 20/20 覆盖）；`scripts/33` 仍无"磁盘 CSV → 索引"门禁（上一轮 P3-I 未变）。
本次支出表靠手工登记，若再次漏登记，33 号不会响。

**没有发现 P0/P1。** 未发现任何"正文数字与磁盘重算不符"的情况。

## 5. 最终判定：**NOT CLOSED**

- **C1–C6 六条逐条落地、且每一条的我方读数与正文一致**（§2/§3 全部"一致"）；数据层、登记层、行尾编码层均无实质缺口。
- 但本次修复**新造了一处 P2 级自相矛盾**（§4 P2-1：`validation:21` vs `formal:21`），另有 5 条 P3（其中 2 条是本轮改动带出的、
  1 条是时间口径、2 条是历史遗留）。按本次任务的判定规则（"发现新的 P1/P2 自相矛盾 → NOT CLOSED"），改判为 **NOT CLOSED**。
- **最小修复动作（全部只改文档，不需重跑任何 rep、不需重导出任何表）**：
  1. `docs/v3_phase_F02_validation.md:21` 改为"已做（19:17 + 21:43，均 PASS WITH CONDITIONS），C1–C6 已落地、待窄口径确认"；
  2. 同文 `:242` §5.4 标题去掉"未运行"；
  3. 统一"21:45 导出 / 21:48 登记"，或注明 21:48 为登记时刻；
  4. `formal:19` 的"未按 manifest 复核"改"未按 bytes 复核"；
  5. 决策日志 21:50 条：修正 66 713/−1.1e-5 的归属、并把"未重导出任何结果表"改成"未重跑 rep、未重算聚合数字"。
  做完 1–2 即可重判；3–5 属同批应清的精度项。

**边界声明（必须与判定一起读）**：
- 本报告只核"**证据 / 数字 / 交付物是否自洽**"。C1–C6 落地、乃至本报告改判 CLOSED，都**只**说明 F02 的记录准确、
  断言范围与其证据一致；**不等于"定向有效"**，**不等于策略可部署**，也不对"审计价值移交 D01/G"这一范围声明背书。
- F02 的阶段状态由 `GOAL.md` / `TODO.md` 决定；按 §7.4，**改判动作由主控执行，本复核子代理不执行、也无权执行**。
- 本报告的全部读数只对 `c13a8cd` 成立；HEAD 之后再变动文档，需重新核对 §2 的行号锚点。

## 6. 我运行过的全部命令（便于复现）

只读命令，时间为 2026-10-28 21:45–21:55（北京时间）；除最后一条报告落盘外无任何写盘。

```bash
# 0 环境与快照
git status --short ; git log -3 --format="%h %cd %s" --date=format:"%Y-%m-%d %H:%M"
git log -1 --format='%h %H %cd' --date=format:'%Y-%m-%d %H:%M:%S %z'
git diff --stat c13a8cd~1 c13a8cd
git diff c13a8cd~1 c13a8cd -- docs/v3_phase_F02_formal.md docs/v3_phase_F02_validation.md
git diff c13a8cd~1 c13a8cd -- TODO.md AGENT_HANDOFF.md GOAL.md      # 输出转存后 Read 阅读

# 1 支出表字节与结构
ls -la --time-style=full-iso outputs/evidence/f02_formal/aggregate/
.venv/Scripts/python.exe -c "sha256/bytes/BOM/CRLF/行数"            # PYTHONUTF8=1
.venv/Scripts/python.exe -c "pandas.read_csv(..., encoding='utf-8-sig'); shape/columns/dtypes/arm 计数"

# 2 定向/随机两臂复算
.venv/Scripts/python.exe -c "pooled=Σrealized/Σpredicted; mean/min/median/max; >1 计数; budget_cny 校验; dev=pred-budget 校验; 极值行定位"

# 3 两级登记逐条重算 + 双向核对
.venv/Scripts/python.exe -c "coverage.json: 77 条逐条 sha256+bytes；total_bytes 求和；spend_full 记录打印"
.venv/Scripts/python.exe -c "f02_formal/coverage.json: 20 条逐条 sha256+bytes；磁盘↔索引双向差集"
.venv/Scripts/python.exe -c "outputs/evidence rglob：磁盘有而顶层索引无 / 索引有而磁盘无"
.venv/Scripts/python.exe -c "registry_repairs 15 条键集与 [13][14] 全文打印"

# 4 33 号脚本形状比对 + dry-run
grep -n "added\|refreshed\|dry.run\|全表复算" scripts/33_register_evidence_top.py
stat -c '%n %y %s' outputs/evidence/coverage.json outputs/evidence/f02_formal/coverage.json
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/33_register_evidence_top.py --dry-run   # exit 0
stat -c '%n %y %s' outputs/evidence/coverage.json outputs/evidence/f02_formal/coverage.json   # mtime 未变

# 5 旧表 vs 新表（不落临时文件，走管道）
git show c13a8cd~1:outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv \
  | PYTHONUTF8=1 .venv/Scripts/python.exe -c "stdin 读字节：bytes/sha；与工作树表逐列比对"

# 6 五表 manifest 的 bytes 断言
.venv/Scripts/python.exe -c "manifest['artifacts'] 键频统计；26 个 sha256 对磁盘重算"

# 7 文档一致性 grep（五个文件 + 全库）
grep -n -F "未落盘|只部分关闭|部分关闭|16,906,697|16 906 697|65 条|65 /|待窄口径|21:46" <docs/*.md TODO.md GOAL.md AGENT_HANDOFF.md>
grep -rn "16,906,697|16 906 697|16906697|只部分关闭|101,666" --include=*.md .      # 确认只剩历史记录
grep -n "bytes" docs/v3_phase_F02_formal.md docs/v3_phase_F02_validation.md
grep -n "^#\+ " docs/v3_phase_F02_validation.md        # 定位 §5.3 / §5.4 标题
grep -n "66 713|66713|1.1e-5" docs/reviews/v3_phase_F02_closeout.md   # 0 命中（P3-4 依据）

# 8 行尾/编码
git ls-files --eol docs/v3_phase_F02_formal.md docs/v3_phase_F02_validation.md TODO.md GOAL.md \
  AGENT_HANDOFF.md docs/v3_决策与反思日志.md outputs/evidence/coverage.json \
  outputs/evidence/f02_formal/coverage.json \
  outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv
```
