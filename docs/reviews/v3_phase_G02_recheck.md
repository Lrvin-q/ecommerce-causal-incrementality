# G02 再训练 bootstrap 正式报告 —— 评审条件关闭情况复核（窄口径）

> **复核时间：2026-10-29 23:30（北京时间，`date -u` 读数 15:30 UTC + 8 h）**。
> 身份：**独立复核子代理**，此前未参与 G02 任何产出，也未参与本轮修复。
> 范围：只判 `docs/reviews/v3_phase_G02_review.md` §5 的关闭条件是否满足（P1-1、P2-1…P2-7），
> 不重开全文评审、不重跑实验、不重新计算报告里的统计量（表 3-1 只做一致性抽查）。
> 纪律：全程只读；除本文件外未写任何文件；未运行 34/39/51 号运行模式，未运行
> `scripts/52_paper_gates.sh --build`；只执行了 40 号 `--check` 与 33 号 `--dry-run` 两个只读校验。
> 本文件 UTF-8、LF 行尾。

**结论速览：9 项核查全部 CLOSED；无 P0/P1/P2 级新问题，亦无 P3 级新问题；建议改判通过（§4）。**

---

## §1 逐条核查

| # | 条目 | 复核命令 / 证据 | 判定 | 说明 |
|---|---|---|---|---|
| 1 | **P1-1** 表 3-1 跨层合计通过率 | `sed -n '80p' docs/v3_phase_G02_formal.md` → `合计（仅工作量） … 不设合计 … 不设合计 … 25.37`；`sed -n '82,83p'` 有"合计行只汇总工作量、不给 decision / guardrail 的跨层通过率"及送审包 §4.1 / AGENTS §12.5 依据；`grep -rn "143/200" docs/ paper/ GOAL.md TODO.md` → 报告本体、GOAL、paper 均 0 命中 | **CLOSED** | 仅剩评审文件 5 处、`docs/v3_决策与反思日志.md:4478,4509`、`TODO.md:9` 的修复叙述（任务允许范围）。另核：`docs/v3_phase_G02_formal.md:106` 仍有"guardrail 200/200 只说明退款率护栏未报警"，属跨层护栏计数但带限定句，且初审 §2.1 原文将其列为"写对的"、送审包 §3 第 3 项本身以 200/200 送审，故不重开 |
| 2 | **P2-1** 四格"共用验证队列" | `sed -n '1104,1106p' paper/v3/body/03_results.md`（3.7 三条边界块 1100–1106）→ "验证队列在每格内部跨 b 固定，但四格之间是四份不同的验证用户协变量（`validation_frame_hash` 四格四值），只有随机化臂与概率（`validation_arm_hash`）四格共享"；逐格统计 `outputs/evidence/g02_formal/per_cell/*__repetitions.csv`：frame nunique = 1/1/1/1，arm nunique = 1/1/1/1；**跨格 frame 去重 = 4**（`b2b33848…`、`11fab0d2…`、`198dc634…`、`cb59d7d6…`），**跨格 arm 去重 = 1**（`7f7c9936…`） | **CLOSED** | 措辞与证据一致。另查残留"同一份验证队列"两处（`:1062`、`:1092`）均指单格内 50 b 共用，不构成反例 |
| 3 | **P2-2** "92 条"归因 | 报告 `:59` "33 号登记 G02 的 **1 条**身份记录（`snapshot_binding.json`），顶层累计 **92 条**"；`GOAL.md:28` 同句；`docs/v3_G02_送审包.md:33` 写"登记 G02 的 1 条（顶层累计 92 条）"；`scripts/33_register_evidence_top.py --dirs g02_formal --dry-run`（EXIT=0）原文："候选身份类文件 1 个：新增 0，已登记 1""顶层全表复算一致：92 条""无新增、无字段补齐，不写盘（幂等）" | **CLOSED** | 独立另核 `outputs/evidence/coverage.json`：`records` 长度 **92**，其中 G02 仅 **1** 条（`kind=g02_snapshot_binding`，`target=outputs/evidence/g02_formal/binding/snapshot_binding.json`，5 777 B），与"新增 1 条、累计 92 条"吻合 |
| 4 | **P2-3** 800 覆盖 / configs 未改 | 报告 `:28-32` 明写冻结 `configs/v3/scenarios.yaml` 的 `retraining_bootstrap_jobs: 800`（4 格 × 200）未被执行、由 `configs/budget/g02_bootstrap_overlay.yaml`（total 200 / per_cell 50）与 39 号 runner 覆盖、`configs/v3/*.yaml` 未改、七文件 hash `00723dc2…`。**独立复算**：`load_v3_protocol().config_hash` = `00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3`（口径为 7 份 YAML 合并后的 canonical JSON sha256，不是简单拼接）；`configs/v3/*.yaml` 7 份与 `out/g02_snapshot/configs/v3/` 逐字节 `cmp` 全部 SAME；overlay 1 847 B、sha256 `c58d5a90…`、`retraining_bootstrap_total: 200` / `per_cell: 50` | **CLOSED** | 口径与 `AGENT_HANDOFF.md:78`、`configs/budget/g02_bootstrap_overlay.yaml` 注释、G01/G 阶段既有记录一致。旁证：`scenarios.yaml:266` 为 800，`execution.yaml:30` `retraining_bootstrap: 200` ⇒ planned_counts 4 × 200 = 800；39 号 `read_bootstrap_overlay()`/`check_counts()` 从 overlay 取 per_cell 并强制跑满 |
| 5 | **P2-4** 通过率非阈值 | `sed -n '107p' docs/v3_phase_G02_formal.md` → "**通过率（0.04 / 0.98 / 0.94 / 0.90）是跨 b 的描述性统计，不是验收阈值**；正式判定单位是每个 b 内的单侧 Holm 检验" | **CLOSED** | 位于 §3「解读纪律」段内，与长稿 `:181`、`:232`、`:1467` 同向 |
| 6 | **P2-5** `-0.2156` 归属 | 报告 `:94-99`：`decision_lower_min` 为两者校正下界较小值，L0 最小 -0.2156，并落"证据边界"——归因依据运行期 decision 表，逐 b 两条子主张下界**未随证据导出**、只能复算较小值；`paper/v3/body/03_results.md:1039-1043` 同改法；源码 `scripts/39_g_retrain_bootstrap_run.py:250` 确为 `run_validation_arm(..., target_dir=None, ...)`。`outputs/evidence/g02_formal/per_cell/` 无 `decision.csv`（19 个文件中无此件） | **CLOSED** | 采用评审给出的"注明证据边界"路径（其"或"分支），未新增数字；42 号 `claim_draft` 门禁 23:18 仍 EXIT=0 |
| 7 | **P2-6** `merge_exit` 证据边界 | 报告 §5 `:144-150` 明写：`merge_exit=0` 凭据是现场 `out/g02_logs/post.status`（两行原文），**未纳入 18 件导出、不可迁移**；证据区 `logs/post.log` 末行只有"merge 完成"、无退出码。现场实读：`post.status` 两行 `merge_exit=0` / `OK: G02 merge 完成 2026-10-29T17:17:51+08:00`；`tail -3 outputs/evidence/g02_formal/logs/post.log` 末行 `[2026-10-29 17:17:51] merge 完成`；证据区实有 19 个文件 = 18 件导出 + `coverage.json`，无 `post.status` | **CLOSED** | 注记与磁盘状态逐字相符；`coverage.json` `exported_at=2026-10-29T18:04:39+08:00`、`files` 18 条 |
| 8 | **P2-7** 注册表快照哈希 | `docs/v3_phase_G_run_registry.md:14` 已为 `out/g02_snapshot`，49 文件 `abaa338a…`，并把 `f39ec0a3…` 标注为"首轮 10:09 失败现场…已留档"；**独立复算** `outputs/evidence/g02_formal/binding/snapshot_binding.json`：`sha256(json.dumps(source_hashes, sort_keys=True, separators=(',',':')))` = `abaa338a0c7705ae85fb2c420beeee3928263dad00ee18e324f65b761fa3f14c`，与文件内 `source_hashes_sha256`、报告 `:25`、注册表 `:70-71` 一致；`TODO.md:589` 已加"（**首轮失败快照**；…）" | **CLOSED** | 其余 `f39ec0a3` 命中（注册表 `:71`、`TODO.md:16-17`、反思日志 `:4495`）均为失败现场叙述，无未标注的当值引用 |
| 9 | **重建声明** | `out/scratch/paper_gates/summary.txt`：`build=0`、`claim_draft=0`、`claim_abstract=0`、`citations=0`、`long_draft=0`，另 `concat_chars=93872`（字数，不是门禁；**不存在非零门禁**，若按"六项全 0"字面说则不成立，但五项门禁 exit 全 0）；`out/scratch/v3_paper_build/pass3.log`：`Output written on main.pdf (50 pages)`、`Missing character` **0**、`undefined` **0**、`Overfull` 9（最大 0.12009pt）、`Underfull … badness 10000` **0**；`out/scratch/paper_gates/long_draft.log`：`total_pages=50`、`results_char_share=0.5537`、`results_substantive=32` / `body_substantive=46`；`docs/v3_H03_编译审计.md:26` 写"42 765 字 = 77 241 字的 **55.37%**；结果页 **32/46**"，§1 页数 50 | **CLOSED** | 构建产物时间 23:18 晚于 `paper/v3/body/03_results.md`（23:17:49）与 `04_conclusion.md`（23:10:57），重建覆盖了本轮改动；H03 §2.1 列的 5 处文字修改在正文中逐条可验（`03_results.md:1007`、`:1039-1043`、`:1104-1106`、`:1050-1051`，`04_conclusion.md:60`、`:229`） |

**表 3-1 一致性抽查**（确认 P1-1 的改法没有动到数字；逐 b 表独立复算）：
均值 2.355626 / 2.857321 / 2.851376 / 2.983932；sd 0.049674 / 0.041680 / 0.059796 / 0.066165；
MC SE 0.007025 / 0.005894 / 0.008456 / 0.009357；decision 2/50、49/50、47/50、45/50；
guardrail 逐格 50/50；CPU·h 6.0318 / 6.4951 / 6.3588 / 6.4811，合计 25.3668 → 25.37。
`scripts/40_export_g02_evidence.py --check` 复跑 **EXIT=0**（"复算一致：4 格 × 50 b = 200 行；合并表逐格 max|Δ| ≤ 1e-12"，`CHECK ONLY：不写盘`）。

---

## §2 新发现

**无 P0 / P1 / P2 / P3 级新问题。**

两点非问题性说明（不参与分级，仅供主负责知悉，均不改判据）：

1. 初审在 §2.1 把报告原文"guardrail 200/200 只说明退款率护栏未报警"一句明确列为"写对的"；
   修订后该句仍在 `docs/v3_phase_G02_formal.md:106`，
   同义的跨层护栏计数亦见于 `paper/v3/body/03_results.md:997`（"退款率护栏在全部 200 个重复上通过"）。两处都带"不说明策略最优/不是擦线"的限定，
   且送审包 §3 第 3 项本身按 200/200 送审，故不按新问题计。
   若后续追求字面彻底，可把"200/200"换成"四格各 50/50"，属措辞级优化，不影响本结论。
2. 修订记录 §6 的 P1-1 复核栏写"`grep -rn "143/200" docs/ paper/` 只在评审文件自身命中"——
   现在还会命中 `docs/v3_决策与反思日志.md:4478,4509`（反思日志 mtime 23:18:42，晚于该检查）；
   报告本体仍为 0 命中，条件不受影响，仅该自检句的时点已过时。

---

## §3 结论

**PASS（全部关闭）。**

- 6 项"必须关闭"（P1-1、P2-1、P2-2、P2-3、P2-4、P2-7）逐项在磁盘上复现，措辞与证据一致；
- 2 项"如实注明证据边界"（P2-5、P2-6）已按评审允许的路径落地，注记与源码（`39 号:250` `target_dir=None`）、
  现场文件（`out/g02_logs/post.status`）、证据区（`logs/post.log` 无退出码、19 文件清单）逐字相符；
- 初审 §5 允许随同关闭的 P3 低成本项（P3-1…P3-4、P3-6、P3-7）也已落地，P3-5 为提醒、无需改动；
- 重建声明与 `out/scratch/paper_gates/`、`out/scratch/v3_paper_build/pass3.log`、`long_draft.log`、
  `docs/v3_H03_编译审计.md` §1 一致（50 页 / 55.37% / 32 of 46 / 缺字 0 / 未定义 0）。

---

## §4 允许 / 不允许改判的表述

**允许（建议）**：建议主负责**改判 G02 为"通过"**，其含义**仅**为"记录准确、断言范围正确"：
200 b / 4 个 core 格 / 固定验证帧（frame 四值、arm 共享）/ 任务书 200 次口径 /
固定 bootstrap 仅 0.2 元档 / 关键数字可由 `outputs/evidence/g02_formal/` 复算。

**不允许**（改判不授权以下任何读法，也与本复核无关）：

1. 不表示"定向策略有效"、不表示可上线或可部署；
2. 不表示四层是四份独立证据，不支持任何跨层合并的通过率；
3. 不表示通过率是验收阈值或覆盖率证据（每格 50 b，不做逐格覆盖率断言）；
4. 不表示冻结配置的 800 次已执行（实跑为 200 次，configs 未改）；
5. 不表示 Tier2 已跑满 65 格（本轮 Tier2 为 20 格 × 30），也不据此关闭 G03 / G04 / H01–H05；
6. 不改变 `merge_exit=0`、逐 b 子主张下界、`pytest_g02fix` 日志三处"仅现场、证据区不可迁移"的证据边界。

---

复核者：独立复核子代理（未参与 G02 产出与修复）
时间：2026-10-29 23:30（北京时间）
