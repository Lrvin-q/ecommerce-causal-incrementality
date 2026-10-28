# F02 收尾窄口径复核（2026-10-28 21:45，北京时间）

> 合成数据 / 已知 DGP。独立子代理复核；全程只读，唯一写盘是本报告。
> 一句话：**P1-1 的数据层主张为真**——600 行逐格等于逐 rep manifest，承诺的六个统计量全部复现；
> 但 F02 的正式报告仍写"预测支出未落盘、P1-1 只部分关闭"，因此本包**不能整包 PASS**。

## 1. 复核对象与快照

- 工作树 `C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目`，分支 `codex/d03`。
- **HEAD 在复核期间前移**：开工时 `882b684`；21:43:28 读到 `a91a6ef`（21:42:58，只动 G 文档）。
  `git diff --stat 882b684 a91a6ef` 不含任何 F02 路径，故本复核的所有 F02 读数对两个 commit 同值。
- 唯一运行：`scripts/33_register_evidence_top.py --dry-run`（exit 0）。运行后两个 `coverage.json`
  的 mtime 未变（21:38:18 / 21:38:25），确认未写盘；`git status --porcelain` 为空。

| 对象 | sha256 | bytes | mtime |
|---|---|---|---|
| `outputs/evidence/f02_formal/aggregate/v3_phase_F02_formal_per_rep_spend_full.csv` | `8219660498fe927798aad306bfbb97353c0f7d1c65a7e271a56263cc3cafd33e` | 101,666 | 21:38:09 |
| 同上目录 `..._per_rep_realized_spend.csv`（19:30 旧表） | `239eac3062a5d09b…` | 76,270 | 19:24:02 |
| `outputs/evidence/f02_formal/coverage.json` | `f041c1e2a95ebbad…` | 7,395 | 21:38:18 |
| `outputs/evidence/coverage.json` | `9df0d719c3989173…` | 51,505 | 21:38:25 |
| `docs/v3_phase_F02_validation.md` | `08fc53d5552b64b6…` | 27,183 | 21:38:34 |
| `docs/v3_phase_F02_formal.md` | `c0813059478ad0f0…` | 17,333 | 19:24:17 |
| `docs/reviews/v3_phase_F02_review.md`（19:20） | `1629e9588b08a4db…` | 43,123 | 19:20:58 |
| `scripts/33_register_evidence_top.py` | `82ff7b999508ac9c…` | 23,150 | 11:28:20 |

## 2. 逐条判定表

| 项 | 判定 | 依据（我的复核，不采信脚本自报） |
|---|---|---|
| **P1-1（数据层）** | **已关闭** | 200 份 manifest × 3 臂 = 600 行，表内 600/600 逐格等于 `arms.<arm>.*`（≤1e-9 相对差）；六统计量全部复现（§3） |
| **P1-1（交付层）** | **仍开（P1）** | `docs/v3_phase_F02_formal.md:124-126,169` 仍写"预测支出未落盘、P1-1 只部分关闭"并指向旧表；与 validation:191 / GOAL:26 / TODO:42-45 相反 |
| P1-2 证据补登记 | 已关闭（残余 P3） | 目录级 20 条与磁盘 20/20 双向一致；200 行绑定表 200/200 `manifest_sha256` 与磁盘逐字节相同；4 分片 summary、snapshot binding 均在包内。残余：`rows` 字段只新表有（目录级 1/20，顶层 12/77） |
| P1-3 审计价值范围 | 已关闭（声明移交） | `formal:151-155` 明确 F02 只交付 ITT、审计价值移交 D01/G；证据包 excluded 三个 audit 表与该声明自洽。这是范围声明，不是审计结论 |
| P2-1 Wilson→CP | 已关闭 | 两文全文无 "Wilson"；`formal:74` 表头为 Clopper–Pearson |
| P2-2 26 artifact bytes | **仍开（P2）** | `formal:142` 仍写"逐个重算 sha256 与 bytes 全部一致"；`five_tables/manifest.json` 26 个 artifact 实读键为 `role/sha256/rows/columns/dataframe_sha256`，**含 bytes 的 0 个**；同文 `:17` 又承认"bytes 未记录" |
| P2-3 预算偏差分母 | 正文已关闭；**新表重现** | `formal:122` 已写"元（某臂总额，不是每人）"；但新表 `budget_cny` 整列为空（见 P2-C） |
| P2-4 constant 叙述 | 已关闭 | `formal:96-101` 改为描述性表述，含 0/7 ≠ 零效应与结构事实 |
| P2-5 局限章节 | 部分 | §6 条款齐（正态近似/margin/审计/0-7），但 `formal:169` 仍是错误的"未落盘"一条 |
| P2-6 登记计数过期 | 部分（P3） | `formal:18` 写 65 / 16 746 236，实读 77 / 16 906 697；有"以 coverage.json 实读为准"兜底 |
| P2-7 `paired` 键名 | 已关闭 | `validation:46`、`formal:179` 均解释为 rep 级配对、SE 仍两臂独立 |
| P2-8 运行后配置漂移 | 已关闭 | `formal:174-176`；`validation` §6 同 |

## 3. 独立复算表（口径：定向=selected_targeted_policy，随机=random_same_budget）

| 项 | 正文 | 我的复算 | 判定 |
|---|---|---|---|
| 表行数 / rep 覆盖 / 重复缺失 | 600 行（200×3） | 600 行；rep 0–199 齐全；`(rep_id,arm)` 无重复、无缺失；4 分片各 50 rep | 一致 |
| 逐格 vs manifest（n_assigned / predicted / predicted_per / budget_deviation / shard） | 未逐格声明 | 600/600 全部一致，最大相对差 <1e-9 | 一致 |
| realized 列来源 | 未写 | 600/600 等于 `arm_summary.csv` 的 `total_coupon_cost_cny`（总额）与 `mean_coupon_cost_cny`（per-assigned） | 来源正确，正文未写 |
| 定向 合并 实际/预测 | **1.056348** | `Σ实际/Σ预测` = **1.056347991** | 一致（pooled） |
| 定向 min / 中位 / max | −5.42% / +5.09% / +30.67% | −5.4160% / +5.0860% / +30.6675%（比值 0.945840 / 1.050860 / 1.306675） | 一致 |
| 定向 为正 rep 数 | 179/200 | 179/200（分母=全部 200 个定向 rep） | 一致 |
| 随机 合并 实际/预测 | **1.002835** | **1.002835123** | 一致（pooled） |
| 随机 min / 中位 / max | −6.14% / +0.11% / +8.90% | −6.1367% / +0.1147% / +8.8988% | 一致 |
| 随机 为正 rep 数 | 104/200 | 104/200 | 一致 |
| 不发券臂 | 0/0 | 预测与实际均恒 0（200/200） | 一致 |
| 逐 rep 比值均值（formal:128 的 1.056345 / 1.002839） | 1.056345 / 1.002839 | **1.056345050 / 1.002839140** | 一致，但口径与 §194 的 pooled 差 3e-6 |
| 目录级 20 件 | 20 件 | 20 条；20/20 sha256+bytes 与磁盘一致；磁盘无多余文件 | 一致 |
| 顶层 77 条 / 16,906,697 B | 77 / 16,906,697 | 77 条；16 906 697 B；77/77 sha+bytes 一致；无重复 target | 一致 |
| `33 --dry-run` | 全表一致、exit 0 | exit 0；26 个身份类 JSON 全部已登记；未写盘 | 一致 |
| 旧表 `predicted_note` | 表述不正确 | 600 行全部为 `not_persisted_per_rep; run-time budget check only, see review P1-1`，predicted 两列全空 | 属实（注记确实错） |

## 4. 新发现

- **P1-A｜正式报告与收尾声明相反**：`docs/v3_phase_F02_formal.md:124-126`（指向旧表、"未落盘"、"只部分关闭"）、
  `:169`（局限里再写一次）、`:18`（65 条 / 16 746 236 B 过期）。validation:199 已写"旧表保留为历史、以新表为准"，
  但 F02 的正式报告没有这句，且断言相反。读者只看 `v3_phase_F02_formal.md` 会得到"P1-1 未关闭"的结论。
- **P2-B｜repair 条目字段误用**：`outputs/evidence/coverage.json:1020-1031` 的 21:42 条目把新增表写进
  `refreshed: ["…spend_full.csv"]`（字符串数组），而同文件 `:646/:743` 的 `refreshed` 是对象数组
  （`target/old_sha256/…`），33 号脚本对新增写的是 `added`。records 76→77 是新增不是刷新；
  按 `added` 统计会漏掉本表，按对象解析会 TypeError。
- **P2-C｜新表再次缺分母**：`…per_rep_spend_full.csv` 第 12 列 `budget_cny` **600/600 为空**，
  而 `budget_deviation_cny` 实为 `predicted − 0.2×n_assigned`（如 rep0 随机臂 13342.5588−13342.6）；
  正文 `validation:192` 的列清单也漏了 `budget_cny`。另：`no_coupon` 行 `budget_deviation_cny=0.0`，
  但按同一式子应为 −13 338.6，manifest 同样写 0.0——"无预算"语义未标注。这正是评审 P2-3 的同类缺陷在新产物里复发。
- **P2-D｜"合并 实际/预测"未写分母**：`validation:194-195` 只写"合并"，实为 `Σ实际/Σ预测`
  （1.056348），与逐 rep 比值均值（1.056345，`formal:128` 用的就是这个）差 3e-6。
  GOAL:26 引 1.056348、formal 引 1.056345，两个六位小数并置且无说明。
- **P2-E｜时间声明晚于写盘**：`outputs/evidence/coverage.json:1032` 写 `last_refreshed_at=21:42:00`、
  `:1020` 写 `at: 21:42`，`f02_formal/coverage.json:156-157` 写 `repaired_at=21:42`，`validation:191` 写"21:42 补齐"；
  但两文件 mtime 为 21:38:25 / 21:38:18，所在 commit `882b684` 的时间是 **21:40:30**。
  即"21:42 完成"在写盘前 3–4 分钟就被写进文件，无法作为完成时刻的凭据（AGENTS §10 要求精确到分钟且不得猜写）。
- **P3-F｜登记字段不全**：目录级 20 条中只有新表带 `rows`，顶层 77 条中 12 条带 `rows`；
  评审 P1-2 明确要求"sha256、bytes、rows"。
- **P3-G｜TODO 内部矛盾**：`TODO.md:27` 仍写"F02 仍'未证实'（P1-1 预测支出运行期未落盘）"，
  与 `TODO.md:42-45` 的"注记是错的/已关闭"同文件打架（21:45 交接块刷新时漏改）。
- **P3-H｜validation 抬头未随 F02 正式结果更新**：`validation:5-6` 仍写"正式 200 rep 尚未运行"，
  而 §5.2 已放正式 200 rep 的结论段；同文 §5.3 标题也是"未跑"。
- **P3-I｜CSV 无"磁盘有、索引无"门禁**：`scripts/33:296-304` 只对身份类 JSON 做磁盘→索引比对，
  `:344-356` 只做索引→磁盘。CSV 漏登记（19:30 的 4 条即此类）仍不会被 33 拦下，本次靠手工补。
- **P3-J｜新表不可从证据包回溯核对**：表内 `predicted_source` 只是字符串指针；
  200 份 manifest 与 `arm_summary.csv` 均未入包，包内只能复算汇总值（可做），不能验证表值本身（不可做）。

## 5. 最终判定：**PASS WITH CONDITIONS**

P1-1 的**数据主张成立且可复算**，按"证据与数字"口径可以关闭；但交付物内部自相矛盾，故不能判 PASS。

条件（全部可在不重跑任何 rep 的前提下完成）：

1. **C1**：改 `formal:124-126,169`——删"未落盘/只部分关闭"，改为指向 `…_per_rep_spend_full.csv`，
   并保留 validation:199 的"旧表=历史、新表为准"；同步 `TODO.md:27`。
2. **C2**：改 `formal:142`（或给 26 个 artifact 补 `bytes`），使 P2-2 不再复发。
3. **C3**：新表补 `budget_cny`（= 0.2×n_assigned）或删列并在正文写死分母；标注 `no_coupon` 的 0.0 语义。
4. **C4**：在 `validation:194` 写明"合并=按 rep 加总的总量比"，并注明与 `formal:128` 的 1.056345（比值均值）差 3e-6。
5. **C5**：把 21:42 的 repair 条目改成 `added`（对象形状与 33 号脚本一致），并把 21:42 改为实际写盘时刻（≤21:38）或加"计划时刻"标注。
6. **C6**：`formal:18` 计数改 77 / 16 906 697；`validation:5-6`、§5.3 的"未运行"要么更新，要么注明"§5.2 段为 21:38 后补"。

**"PASS"是否等于可改判 F02 通过：不等于。** 本轮只覆盖 P1-1 与 `v3_phase_F02_review.md` 的证据/数字项；
即使 C1–C6 全落地，F02 改判仍需（a）那轮"第三轮窄口径复核"对 P1-3 移交与结论边界的整体接受，
（b）按 `GOAL.md:26` 现行口径显式改状态。本轮 PASS WITH CONDITIONS 只说明"P1-1 可以关闭"。
