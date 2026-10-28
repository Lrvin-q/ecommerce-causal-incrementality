# Phase F01 窄口径确认复审（第四环 recheck）

> 合成数据 / 已知 DGP。评审时间：**2026-10-28 07:18（北京时间，`date` 命令实读）**。
> 评审人：独立评审代理（第四环窄口径确认）。
> 任务边界：只确认复审 `docs/reviews/v3_phase_F01_rereview.md`（05:58）提出的 **3 条新 P1**
> （N-1/N-2/N-3）与 **9 条 P2**（N-4…N-12）在修复批次（06:05 / 06:28–06:32，commit `a9249d7`，
> 已推 origin/codex/d03）后是否**真关闭**，并按任务书重点**搜捕修复新引入的错误**（R3）、
> 横扫同类缺陷第 4/5 处残留（R4）、四方核对登记表与 test_runs 证据（R5）、行尾/字节保真（R6）。
> 不重开原 11 项条目，不重跑任何作业。**F02 正式 200 rep 正在飞行**（03:39 启动），
> 本评审全程未运行 pytest / 任何 `scripts/` / 任何拟合，未写任何冻结 glob
> （`src/causal_growth/**/v3*.py`、`sql/v3*.sql`、`configs/v3*.yaml`、`configs/v3/*.yaml`）
> 与 f02 脚本，git 只读（log/show/diff/ls-files/status/check-ignore），唯一写入的文件是本文。
> **所有数字由本评审独立复算**：不采信主负责自述，也不采信复审者的任何未复算数字。

## §0 判定

**PASS WITH CONDITIONS。**

- **R1：3 条新 P1 全部真关闭。** N-1 的机制新句逐句被数据与源码支撑（本评审独立重建贪心
  0.2 档名单，n=23 437、预测 11 999.505475、真实 15 410、比值 1.284220 逐一复现）；
  N-2 的收窄披露如实且充分（`observed.csv.gz` 实测恰 6 列、无 mu1/mu0/IF）；N-3 的跨档合并
  OLS 本评审从 `random_seeds.csv` 独立重算，slope/se/t/intercept/r²/x 范围/预测值/差值
  **9 个数字全部逐位一致**，且 §4.7、§0.6、§0.9、§6.7 四处口径一致。
- **R2：9 条 P2 全部真关闭**（N-12 实质关闭，但其修复句本身引入新错 RC-1，见下）。
  N-4 三种分母中位数、N-5 全 16 格、N-6 两个哈希归属、N-11 键数与键名清单、N-7/N-8/N-9/N-10
  的披露与登记，全部经本评审独立复算/实读确认。
- **R5/R6：登记表与测试凭据干净。** 顶层 44 条 + 目录级 18 条四方核对（存在/sha256/bytes/
  入库）**0 不符**，两张表 `total_bytes` 均等于逐条之和；1264 个进度点 + 0 失败标记 +
  EXIT=0 的日志与 sidecar、`pyproject.toml:39`、已安装 pytest 源码 `terminal.py:1252-1253`
  三方互证；`.log` 与 `out/logs` 源逐字节相同。
- **但修复批次新引入 3 处错误（RC-1/RC-2/RC-3，按任务书"修复新引入的错误按 P1 对待"口径），
  另有 2 处卫生项（RC-4/RC-5）。** 全部是**文档/元数据措辞层**，无一需要重跑任何作业，
  无一触及冻结路径，可在 F02 飞行期间由主负责安全修掉。

**条件**：主负责在改写 GOAL.md 状态之前（或同批）修正 RC-1、RC-2、RC-4；RC-3 修 sidecar 时
须同步重算其 sha256 并刷新顶层登记（登记表可变、允许）；RC-5 建议改为锚文本引用。

**GOAL.md 的 F01 行可以由"未证实"改为"通过"**，含义边界与文档 line 28-30 自述一致且本评审
确认该边界恰当："通过"只表示**记录准确、断言范围正确**（单 rep / rep 0、
`formal_repetitions=0`、D03 在本 rep 选中 `constant` 模型、主预算 0.2 元/人档、
一次性历史留出评估而非重复实验分布），**绝不表示"定向有效"**，也不构成部署建议。
DR 主口径的两条 Holm 拒绝结论在算术层面自洽（本评审用表内全精度值重算
p=0.016715320 / 0.030906167、Holm 调整 p=0.033430639075，与文档 0.033430639074922386
差 0.0），但其实质含金量受 §0.6 约束：**+0.031873 表观优势的 96.58% 来自多花 30.9% 的钱，
等实际支出下优势只剩 +0.001091**。状态改写须由主负责执行（本评审按任务书不写 GOAL.md）。

---

## §1 R1：3 条新 P1 的关闭确认

### N-1（机制措辞与数据矛盾）—— **真关闭**

修复后的两处句子（§0.12 line 59、§4.8 line 430-443）声称的**每一个数字**，本评审从证据包
`selection_7cols.csv.gz` + `truth_audit_only.csv.gz` 独立复算：

| 文档声称 | 本评审复算 | 一致 |
|---|---|---|
| `cost_hat` 最小 0.048402 | 0.048402 | ✓ |
| `cost_hat ≤ 0` 人数 0、`< 0.01` 0、`< 0.1` 15 | 0 / 0 / 15 | ✓ |
| τ̂ 唯一值（nunique=1） | 0.29380318488356094，nunique=1 | ✓ |
| corr(cost_hat, cost_true) = 0.081482 | 0.08148161 | ✓ |
| 入选者 cost_hat 均值 0.511990 vs 全体 0.819836 | 0.511990 / 0.819836 | ✓ |
| 入选者 cost_true 人均 0.657507 **低于** 全体 0.842833 | 0.657507 / 0.842833（cost_true=10 占比 0.065751 vs 0.084283） | ✓ |
| 0.657507/0.511990 = 1.28422（真值比预测高 28.42%） | 1.284220 | ✓ |
| 预测支出 11 999.51 → 真实 15 410，`within_budget_by_true=False` | 11 999.505475 → 15 410，audit.csv 同值 | ✓ |
| 人数多 60.7%（23 437 vs 14 589） | 23437/14589 = +60.65% | ✓ |

- **贪心名单独立重建**：本评审不使用任何落盘 mask，按"`cost_hat` 升序、累计预测支出
  ≤ 0.2×60 000=12 000"从选人帧重建 0.2 档名单 → **n=23 437、预测支出 11 999.505475、
  真实支出 15 410**，与 `policy_meta.csv` / `audit.csv` 逐位一致 ⇒ "τ̂ 恒定时按 τ̂/cost_hat
  排序 ≡ 按 cost_hat 升序"的机制句成立。
- **源码核对**：`src/causal_growth/evaluation/v3_f01.py:193-194` 与
  `src/causal_growth/policy/v3_policy_grid.py:70-71` 均对 `cost_hat ≤ 0` 直接
  `raise ValueError` ⇒ 被删除的旧句"把预测成本为 0 的人当免费"在架构上不可能，删除正确。
- 新句的方向性（超预算来自**被选中的低 `cost_hat` 子人群上 `cost_hat` 系统性低估**，
  入选者真值成本反而更低）与复算一致，无复审指出的反向暗示残留。

### N-2（DR 不可从证据包重建，声明过强）—— **真关闭**（取修法 (b)，披露充分）

- 事实复核：`outputs/evidence/f01_ope/observed.csv.gz` 实测**恰 6 列**
  （`user_id, treatment, net_profit, coupon_cost, any_refund_30d, design_probability`），
  无 mu1/mu0/影响函数 ⇒ 复审的"DR 一个数都重建不了"成立。
- 文档 line 32-40 现明确划定"可复算范围"：IPW/SNIPS 全族、名单与预测、真值审计格、
  分解格、1 600 行随机分布可由证据包重建；**DR 一族不能**，须重跑 `fit_ope_nuisances`
  （`meta.stage_seconds.ope = 10.53` 实测在案）；补落盘 nuisance 帧列入 F02 合并后待办；
  DR 数字的第一手来源标注为 `outputs/tables/v3_phase_F01_{family,contrast,value,increment}.csv`。
- 全文 grep 无"每个数字都可复算"式旧口径残留；line 17 的 Holm 数字在表层面可交叉复算
  （见 §0）。本评审对 DR 的**原始数据级**重建同样不可能（任务书禁止拟合 + F02 飞行），
  这一点已被修复句如实披露而非掩盖 ⇒ 按窄口径判真关闭。

### N-3（"等支出比较做不了"过强；跨档是插值）—— **真关闭**

本评审从 `outputs/tables/v3_phase_F01_random_seeds.csv`（1 600 行 = 8 档 × 200 种子）
剔除零方差 1.00 档后独立重跑合并 OLS（n=1 400）：

| 量 | 文档 §4.7/§0.6/§0.9/§6.7 | 本评审复算 | 一致 |
|---|---|---|---|
| slope | 0.332073451 | 0.332073451 | ✓ |
| slope se | 0.001013720 | 0.001013720 | ✓ |
| t | 327.579 | 327.579 | ✓ |
| intercept | −0.000740668 | −0.000740668 | ✓ |
| r² | 0.987140 | 0.987140 | ✓ |
| x 范围 | [0.035333, 0.827000] | [0.035333, 0.827000] | ✓ |
| 定向臂 x = 15 410/60 000 | 0.256833（**范围内，插值**） | 0.256833 | ✓ |
| 预测等实际支出随机增量 | 0.084547 | 0.084547 | ✓ |
| 优势残差 | +0.001091（vs 定向 0.085638） | +0.001091 | ✓ |
| 96.58% 来自多花钱 | 1 − 0.001091/0.031873 | 96.58% | ✓ |

- 档内表 8 档数字（定向真实支出 4 020…50 570、随机范围、预测随机、差、斜率、SE、t、r²）
  与 `random_summary.csv` 的 `equal_spend_*` 列复算**逐格一致**；`slope_t == slope/slope_se`
  全表偏差 0.0；1.00 档全 NaN（零方差、回归无定义）如实标注。
- 各档 200 种子支出 sd 复算 = 149.67 / 211.37 / 296.39 / 330.76 / 346.83 / 312.76 / 105.75 /
  0.00 ⇒ §0.9 的"105–347 元"成立。
- **四处口径一致性**（复审特别要求）：§4.7 标题"档内全部是外推，跨档合并是插值"、
  §0.6 第 6 句、§0.9 第 9 句、§6.7 第 7 条，措辞与数字完全同调，无一处残留
  "等支出比较做不了"或"跨档也是外推"的旧断言；旧句处留有带时间戳的更正注记（§12.4 合规）。

---

## §2 R2：9 条 P2 逐项确认

- **N-4 —— 真关闭。** 从 `ope_vs_audit.csv`（48 行）复算三种分母：
  16 条 `policy_vs_no_coupon` 行中 15 条有限，|误差|/SE 中位 **0.608254**；剔除 1.00 退化档后
  14 行中位 **0.631856**；全部 48 行（39 条有限）中位 **0.654755**；max **2.079634** @
  （0.04 档、contrast、`selected_targeted_minus_same_budget_random`）。文档 §4.5 修复句
  三个中位数与分母说明逐字相符；`ope_z == value/se` 全表偏差 0.0；spend_error 全域
  [−0.024623, +0.001486]、sign_agrees=False 恰为文档所列 5 行、reliability_passed=False
  7 行（0.8 档 5 + 0.04 档 2）均复核一致。
- **N-5 —— 真关闭。** 从 `random_seeds.csv`（frozen = seed 0 名单）+ `contrast.csv` DR 值
  独立重算全 16 格（8 档 × audit/DR 两口径的 `n_at_least` 与 `rank_low`）：DR 口径
  **50/57/68/36/89/54/79/200**，rank_low **0.075/0.060/0.015/0.130/0.310/0.750/0.385/0.000**；
  audit 口径 0.2 档 0/1/0 一族与 §4.6 新表**逐格一致**；0.2 档 audit 与 DR 的分布统计
  （mean/sd/q10/q50/q90/mcse/diff/z）逐行复现。0.2 档两个比值 1.173（定向−随机）与
  1.856（随机−no_coupon，se 0.039873）复核一致。
  *微瑕（不计 finding）*："DR `rank_low=0.015` 全表最低"一句忽略 1.00 档的 0.000，
  但同段已注明 1.00 档 200/200 属退化、不构成证据，读者不会被误导。
- **N-6 —— 真关闭。** 本评审按 `v3_storage.py:29-35` 算法（JSON header {columns,dtypes} +
  `hash_pandas_object(index=False, categorize=True)`）对入库副本
  `outputs/evidence/e_evidence_rep0_a/frame_rep0_constant.csv` 重算 `dataframe_sha256`：
  **全 9 列帧 = `372a1bcc1345d552a01fcca77c2ac7cb83a4ef82027e0d8fc74bba74007cddb3`**、
  **7 列选人投影 = `3ef75e0ff76477bbbead946cf85ed9f1acda3a9a4622e257cb3ff9a8a5fb9b8b`**。
  文档 line 78 与 §8 检查单（line 450 一族）现两处归属均正确（"全 9 列帧 = 372a1bcc…，
  7 列选人投影 = 3ef75e0f…，两者不可互换"），与 `meta.json` 的
  `frame_sha256=372a1bcc…` / `selection_sha256=3ef75e0f…` 交叉一致。
- **N-7 —— 真关闭。** `meta.json.reference_frame.path` 确为机器相关绝对路径
  （`C:\Users\26382\…\out\e_evidence_formal\frame_rep0.csv`）；§7 披露复现应使用入库副本
  `outputs/evidence/e_evidence_rep0_a/frame_rep0_constant.csv`，且 meta 同时存有
  selection/frame 两个内容哈希，路径失效不影响可验证性。披露如实。
- **N-8 —— 真关闭（但同段新句引入 RC-2）。** F01 §7（line 520-531）已把验收对象明确为
  **目录级 18 条**（total_bytes=9 490 785、in_repository_bytes=4 185 712，本评审复算均等于
  逐条之和），顶层计数器降级为"写作时点快照，只作参照不作验收"且**不写 total_bytes 与
  last_refreshed_at**；`docs/v3_phase_E_evidence.md:738-746` 同类缺陷（钉死"42 条/15 861 713"）
  已同步解耦。§8 检查单不再钉"42 条中"与"repairs 现有 3 条"。
- **N-9 —— 真关闭。** §3.2 表把 `policy_masks_long.csv.gz`（5 305 073 B / 1 920 000 行，
  18 条中最大）标"入库=否"，正文明说"刻意选择而不是缺件"；目录级 `coverage.json` 的
  `excluded`（理由）与 `rebuild`（四步配方）字段实测存在；该文件在
  `outputs/evidence/f01_ope/` 下确实不存在、只在 `out/`，与登记一致。
  复审已证明它可从 `selection.csv.gz`+`freeze.budgets` 完全派生，不影响 §12.1。
- **N-10 —— 真关闭。** 03:21 全量串行测试日志 + sidecar 提升为入库证据
  （顶层 42→44，`registry_repairs` 第 5 条如实记载）；证据本体核验见本文 §5。
- **N-11 —— 真关闭。** `freeze.json` 实测顶层**恰 16 键**，与文档 line 114 列举逐名一致；
  `source_hash_combined` 实测**不在** freeze.json、只在 `meta.json`（顶层 **31 键**）；
  §3 表前新增"所在文件"对照段，`truth_sha256/frame_hashes.*/reference_frame.*/
  stage_seconds/gates` 归属 meta.json 的说明与实测一致。
- **N-12 —— 实质真关闭，但修复句引入 RC-1。** 实测：`tau_hat` nunique=1
  （0.29380318488356094）；`predicted_value = τ̂ × n_selected` 对**全部 32 行**成立
  （max 偏差 7.3e-12）；比值 `predicted_value/n_selected` 对 **n_selected>0 的 24 行**
  恒等于 0.29380318（对全精度 τ̂ 的 max 偏差 1.1e-16）。文档 §4.1 的"不含任何异质性、
  只反映名单规模、不得当成定向能力证据"警示实质正确且必要；但"**全部 32 行**都等于同一个
  常数"与数据不符——8 行 `no_coupon` 是 0/0 = **NaN**（复审 N-12 原文同错，主负责照抄，
  见 RC-1）。

---

## §3 R3：修复是否引入新错误（本环节重点）

方法：`git diff 6782e1d~1..a9249d7 -- docs/v3_phase_F01_ope.md` 全文 278 行逐句读完，
对**每一句新写的机制句**（尤其不带数字的）找数据/源码支撑；对新写数字全部复算。结果：

- 新写的头部块、§0.6/§0.9/§0.12、§3 N-11 段、§4.5、§4.6 表、§4.7 两段、§4.8 机制段、
  §6.7、§7 披露段、§8 检查单改动——除下列 3 处外**全部有逐一支撑**，未发现第二处数字不符。
- **RC-1（新，P1 口径）**：§4.1 line 210 "对**全部 32 行**都等于同一个常数 0.29380318"——
  8 行 no_coupon 的比值为 0/0=NaN（`r.isna().sum()=8`）。正确表述："对 n_selected>0 的
  24 行恒等；`predicted_value = τ̂ × n_selected` 对全部 32 行成立"。
- **RC-2（新，P1 口径）**：§7 line 530 "E 在顶层拿到 **22 条**逐文件记录"——实测顶层
  `e_evidence_rep0_a` 11 条 + `e_evidence_rep0_b` 12 条 = **23 条**；E 文档 :747 自述
  "E 的 23 条逐条未变"。22 是 05:44 修复（补 `run_cf.log`）**之前**的旧值；该句写于
  06:28–06:32，落笔即错，而且错在**同段刚刚声明"不钉会变的计数器"（N-8）之后**，
  属同一缺陷类的新实例，并与 E 文档跨文档矛盾。
- **RC-3（新，P1 口径对待）**：sidecar `line_ending_note` 断言"仓库里的 *.md 一律 LF"——
  实测 70 个 tracked `.md` 中 **18 个含 CRLF**（`AGENTS.md` CRLF=223/LF=23、`README.md`、
  `docs/v3_phase_D03_formal.md`、`项目方案思路.md` 等）。该文件是 sha256 登记在案的证据，
  修正须同步重算 sidecar 哈希并刷新顶层登记（登记表可变、允许；无需动任何数据产物）。
- 微瑕（不计 finding）：(a) "DR rank_low=0.015 全表最低"见 §2 N-5；(b) §4.7 合并回归
  w=0.493060 与精确值 0.493063 之差来自输入舍入，两种取值预测结果一致。

## §4 R4：同类缺陷横扫（第 4/5 处残留）

对 `GOAL.md`、`TODO.md`、`AGENT_HANDOFF.md`、`docs/**`（含 E/D/F02 各文档）按三类特征
grep：钉住可变计数器、标题与正文自相矛盾、被推翻的强断言未同步。命中项逐一读上下文：

- 绝大多数命中是**更正注记**（"原文写…"形态）、**带时间戳的历史条目**（反思日志/TODO）
  或 `docs/reviews/*.md`（不可变评审证据，按任务书不计缺陷）✓。
- F01 §4.7 标题已改"档内全部是外推，跨档合并是插值"、§7/§8 已与顶层计数器解耦 ✓；
  `docs/v3_phase_E_evidence.md:738-746` 已解耦 ✓。
- **唯一新残留（RC-4，P2）**：`GOAL.md:25` 同一行**首尾自相矛盾**——行首写
  "9 条 P2 **已于 06:28–06:32 修完**，待窄口径确认"，行尾仍残留"**9 条 P2 待修**"。
  属"改了头没改尾"的同步遗漏；本评审无权编辑 GOAL.md，移交主负责。
- RC-2 亦属本类（钉过期计数器），已在 §3 计入。

## §5 R5：登记表四方核对 + test_runs 证据

**顶层 `outputs/evidence/coverage.json`（44 条）**：逐条重算文件存在 + sha256（流式分块）+
bytes，**0 不符**；`sum(bytes) = 15 865 811 == total_bytes` ✓；`git ls-files` 比对
**44/44 全部入库** ✓；`last_refreshed_at = 2026-10-28T06:45:24+08:00`；
`registry_repairs` 5 条（02:38 46→35、03:06、04:24 35→41、05:44 →42、06:28 42→44）
与 E/F01 文档叙述一致；F01 名下 freeze.json（12 151 B，`9973376b…`）、meta.json
（17 335 B，`1c89ca9f0b58…`）与 test_runs 两条均在其中且逐字节相符。
`a9249d7` 中该文件的 diff = 24 增 + 2 删 = **26 行**，与文档"diff 从 932 行降回 26 行"一致。

**目录级 `outputs/evidence/f01_ope/coverage.json`（18 条）**：sha/bytes 逐条复算 **0 不符**；
`total_bytes = 9 490 785 == sum` ✓；`in_repository_bytes = 4 185 712` ✓；
`target` 为绝对 Windows 路径，**剥去 cwd 前缀后**与 `git ls-files` 比对 =
**17 条入库 + 1 条（`policy_masks_long.csv.gz`，`in_repository=false`）确实未入库**，
与登记字段一致 ✓（若不做前缀剥离会误判"全部未入库"，此陷阱已避开）。

**test_runs 证据**：
- `pytest_full_20261028_0321.log`（1 527 B，sha256 `dd241c18e5c02a76…`）与
  `out/logs/pytest_full_20261028_0321.log` **逐字节相同** ✓；CR=18 / LF=21 / CRLF=18 /
  裸 LF=3（pytest 进度行 CRLF + bash START/EXIT/END 行 LF 的自然混合）✓；
  进度字符**恰 1 264 个 '.'，F/E/s/x/X 计 0** ✓；START 2026-10-28 03:21:18 +0800 /
  **EXIT=0** / END 03:27:42（384 秒），与 sidecar 及 TODO.md:312 叙述一致 ✓。
- sidecar 的机制解释经**已安装源码**验证：`pyproject.toml:39`
  `addopts = "-q --strict-markers -p no:cacheprovider"` ✓；
  `.venv/Lib/site-packages/_pytest/terminal.py:1252-1253`
  `def summary_stats(self)` → `if self.verbosity < -1: return` ✓ ——
  "两个 -q ⇒ verbosity=−2 ⇒ 无 'N passed' 汇总行"的引用（sidecar 写 :1253）**属实**。
- `collected_tests=1264` 的内部一致性成立：verbosity=−2 下每测试恰 1 字符，
  1 264 个 '.' + 0 失败/跳过标记 + EXIT=0 ⇒ 1 264 项执行且通过；
  "由 `--collect-only` 独立确认"这一**来源声明**无法从产物字面证实（见 §10）。
- `frozen_tree_check`（find -newermt 逻辑）叙述与四个绑定 glob 的冻结纪律一致；
  `superseded_evidence` 对 `outputs/runs/f01_tests/full_suite.log` 的处置见本文 §7。

## §6 R6：行尾与字节保真

- `core.autocrlf = false` ✓；`.gitattributes` 只对 *.pdf/png/pptx/docx/xlsx/db 设 `-diff`，
  无任何行尾规则 ⇒ 入库字节 = 磁盘字节，比对有效 ✓。
- 证据 JSON 约定：`meta.json` / `freeze.json` / `run_manifest.json` / sidecar 实测均 CRLF ✓
  （sidecar 约定陈述的前半句成立）；`.log` 与源逐字节相同、不做行尾归一 ✓。
- 工作区相对 HEAD `a9249d7` 干净（仅未跟踪 `.workbuddy/`），HEAD 提交时间
  2026-10-28 06:46:01 +0800 ✓。
- **sidecar "仓库里的 *.md 一律 LF" 为假**（18/70 tracked `.md` 含 CRLF）→ RC-3。

## §7 对"主负责更正复审"的裁决 —— **更正成立**

复审 N-10 把 `outputs/runs/f01_tests/full_suite.log` 称为"**入库那份**"（并据此批评
"入库证据过期"）。本评审实测：`.gitignore:29` = `/outputs/runs/`；
`git ls-files outputs/runs` = **0 条**；git 历史中该路径下无任何文件曾被跟踪。
⇒ 该日志**从未入库**，复审此句事实错误；主负责的更正（"它连'入库的过期证据'都不是，
真正的缺口是 03:21 那份有效日志当时**不在库内**"）正确，sidecar 的
`superseded_evidence.reason` 字段已如实记载此裁决依据。本评审对复审该句不予采信。
（复审其余被本评审复算过的数字——N-1/N-3/N-4/N-5 各值——独立复现，无误。）

## §8 findings

| 编号 | 问题 | 位置 | 证据 | 严重度 | 是否需重跑 |
|---|---|---|---|---|---|
| RC-1 | 修复句写"`predicted_value/n_selected` 对**全部 32 行**都等于 0.29380318"；实际 8 行 `no_coupon` 为 0/0=NaN，恒等只对 n_selected>0 的 24 行成立（`predicted_value=τ̂×n_selected` 才对全部 32 行成立）。复审 N-12 原文同错，主负责照抄未复算 | `docs/v3_phase_F01_ope.md:210` | `policy_meta.csv` 复算：比值 NaN 计 8；24 行对全精度 τ̂ max 偏差 1.1e-16；32 行 pv=τ̂×n max 偏差 7.3e-12 | **P1**（修复新引入，措辞层） | 否 |
| RC-2 | 修复句写"E 在顶层拿到 **22 条**逐文件记录"；实测 23 条（rep0_a 11 + rep0_b 12），E 文档 :747 自述 23；22 为 05:44 修复前旧值，新句再钉过期计数器，与同段"不钉计数"主旨自相矛盾 | `docs/v3_phase_F01_ope.md:530`；对照 `docs/v3_phase_E_evidence.md:747`、`outputs/evidence/coverage.json` | 本评审按前缀逐条计数 = 23 | **P1**（修复新引入） | 否 |
| RC-3 | sidecar 断言"仓库里的 *.md 一律 LF"；实测 70 个 tracked `.md` 中 18 个含 CRLF（AGENTS.md CRLF=223/LF=23、README.md 等）。该文件为哈希登记证据，修正须重算 sidecar sha256 并刷新顶层登记 | `outputs/evidence/test_runs/pytest_full_20261028_0321.json`（`line_ending_note`） | 逐文件 CRLF 计数 18/70 | **P1 口径对待**（修复新引入，元数据措辞） | 否 |
| RC-4 | `GOAL.md:25` 同一行首尾矛盾：行首"9 条 P2 已于 06:28–06:32 修完，待窄口径确认"，行尾残留"9 条 P2 待修" | `GOAL.md:25` | grep "待修" 命中该行行尾 | P2（R4 残留；本评审无权编辑） | 否 |
| RC-5 | sidecar `command_line_source="TODO.md:262"`：写作时点（06:28，树态≈`6782e1d`）第 262 行确为复现命令行（`git show 6782e1d:TODO.md` 验证），但 `a9249d7` 后该行已漂移至 :311/:312 —— 行号引用属"钉可变指针"类，建议改为锚文本引用 | sidecar；`TODO.md:36/:312` | git show 对比 | P2（建议） | 否 |

## §9 复算日志

| 时间（北京） | 做了什么 | 得到什么 |
|---|---|---|
| ≈06:46–06:48 | `date` 实读时间；读 AGENTS.md / 项目方案思路.md 主线五 / GOAL.md F01+R01 行 / 主文档 573 行全文 / 复审 461 行全文 / E-recheck 模板全文 | 建立窄口径范围；发现 GOAL.md:25 行尾"9 条 P2 待修"残留（后确认为 RC-4） |
| ≈06:48–06:52 | git：HEAD=a9249d7（06:46:01）、worktree 状态、`.gitignore:29`、`git ls-files outputs/runs`、`a9249d7` 中 coverage.json diff 行数、`core.autocrlf`、`.gitattributes` | 工作区干净；outputs/runs 从未入库（§7 裁决依据）；diff=26 行；autocrlf=false |
| ≈06:52–06:58 | 顶层 44 条四方核对（存在/sha256/bytes/git 跟踪）+ sum(bytes)；目录级 18 条同法（剥绝对路径前缀） | 0 不符；15 865 811==total_bytes；44/44 入库；目录级 17 入库+1 正确未入库 |
| ≈06:58–07:02 | test_runs 日志与 out/logs 源逐字节比对；CR/LF/CRLF 计数；进度点/失败标记计数；sidecar 全字段 vs `pyproject.toml:39` 与 `.venv` 内 `terminal.py:1252-1253` | 字节相同；1264 点/0 标记/EXIT=0；verbosity 机制引用属实；"*.md 一律 LF"为假（18/70，后确认为 RC-3） |
| ≈07:02–07:08（跨压缩边界） | N-1：帧统计、cost_hat/cost_true 分布、corr、贪心 0.2 档名单独立重建；两处 raise 的源码行核对 | 全部命中；n=23 437 / 11 999.505475 / 15 410 / 1.284220 |
| ≈07:02–07:08 | N-2/N-6/N-11/N-12：observed 6 列、meta 31 键、freeze 16 键、dataframe_sha256 重实现重算两个哈希、policy_meta 比值 | 6 列确认；键数键名逐一吻合；372a1bcc…=9 列帧、3ef75e0f…=7 列投影；比值 24 行恒等+8 行 NaN（RC-1 依据） |
| ≈07:05–07:10 | N-4：48 行三分母中位数+max；N-5：16 格重算+0.2 档分布统计；targeting 表分解核对 | 0.608254/0.631856/0.654755、max 2.079634；16 格逐格一致；+0.031873=+0.032608−0.000735 一致 |
| ≈07:08–07:12 | N-3：档内 equal_spend 列复算、各档支出 sd、跨档合并 OLS（1 400 行）全套重跑；Holm/p 用表内全精度值重算 | 9 个合并回归数字逐位一致；sd 105–347；p=0.016715320/0.030906167、Holm=0.033430639075 差 0.0 |
| 07:07 | 读 `TODO.md:255-270` + grep 命令行 + `git show 6782e1d/a9249d7:TODO.md` 行号对比 | sidecar 的 :262 引用在写作时点为真、现已漂移（RC-5） |
| 07:08–07:14 | R3：`git diff 6782e1d~1..a9249d7` 278 行逐句读；R4：GOAL/TODO/docs grep 三类特征；E 记录数按前缀计数；`registry_repairs` 05:44 条目全读 | RC-1/RC-2 定案（22 vs 23 由 05:44 补 run_cf.log 所致）；R4 唯一残留 RC-4 |
| 07:15–07:18 | `date` 复读；撰写本文 | 本报告 |

（"≈"表示该步骤的确切分钟未被逐条记录，顺序与区间依据会话内两次 `date` 实读
（06:48、07:07、07:15、07:18）与命令先后推定；不带"≈"的为实读时刻。）

## §10 未能核实的事项（如实列出）

1. **DR 一族的原始数据级重建**：证据包无 mu1/mu0/影响函数，重建须重跑
   `fit_ope_nuisances`（模型拟合）——任务书禁止且 F02 飞行中。本评审只做到：
   表层面全精度交叉复算（z=value/se 偏差 0.0、单侧 p 与 Holm 调整 p 复现差 0.0、
   配对差与 IPW/SNIPS 族内部一致、spend_error/sign_agrees/reliability 标志逐行核对）。
   **DR 点估计本身是否正确，本评审无法独立证实**——这正是 N-2 修复句如实披露的边界。
2. **pytest 是否真实全绿**：日志层面 EXIT=0 + 1 264 个 '.' + 0 失败标记是产物可证的
   最强形式，但本评审未复跑（禁止）；测试是否在当前冻结树上仍通过属推断而非实证
   （sidecar 的 frozen_tree_check 叙述与冻结纪律一致，但 find 输出本身未留档）。
3. **`--collect-only` 是否字面执行过**：无产物；只能确认 1 264 与日志内部一致。
4. **DGP 构造本身的正确性**（真值生成过程、R=0 设定是否被忠实执行）：超出本次窄口径。
5. **`verify_freeze_manifest` 复算与 48 份逐文件源码哈希**：须运行脚本（禁止）；
   本评审只静态核对了 freeze.json 16 键结构、source_hashes 形态与文档归属说明。
6. **F02 作业运行状态**：本评审未查询、未干扰其进程；只确认自身未触碰任何冻结路径。

## §11 方法与凭据

只读工具 + 短生命周期 python 进程（pandas/numpy/scipy/json/hashlib，
`.venv/Scripts/python.exe`，PYTHONUTF8=1），全部针对已入库产物
（`outputs/tables/v3_phase_F01_*.csv`、`outputs/evidence/**`）与文档/git 对象；
sha256 用流式分块计算。未运行 pytest、未运行任何 `scripts/`、未做任何模型拟合、
未写除本文外的任何路径、未执行任何改变状态的 git 命令（无 commit/push/merge）。
本文所有"✓"均对应本评审自己复算或与磁盘/git 原件逐字比对的结果；
主负责与复审者的自述一律先复算后采信，复算不能的（§10）明说不采信也不反驳。
