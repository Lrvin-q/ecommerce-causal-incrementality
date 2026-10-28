# G 阶段协议修订：AA 批数 1000/层 → 250/层

> **合成数据 / 已知 DGP。**
> **状态：已执行；独立评审 2026-10-28 19:09 判 PASS WITH CONDITIONS（0 P0 / 1 P1 / 3 P2），C1–C3 已于 19:25 关闭（2026-10-28 19:25，北京时间）。**
> 本文是 `configs/v3/execution.yaml` 的 `change_matrix_requires_versioned_reason_and_review: true`
> 所要求的版本化理由。**12 行**改动已于 2026-10-28 18:24–18:36 落盘（§3 改后值全部实读填入），
> 新协议绑定在 `outputs/v3/protocol_aa250/`（18:36 重算）。**独立评审返回 PASS 之前，不得把 G01 记为"按新契约开跑"。**
> 改动执行时机：F02 四个分片全部退出之后（AGENTS §11：`configs/v3/*.yaml` 在 F02 的绑定 glob 内）。

## 1. 授权链与范围

| 时间 | 出处 | 授权内容 |
|---|---|---|
| 2026-10-25 13:45 | 用户决策，已写入 `GOAL.md` G01 行与 `configs/budget/repetition_overlay.yaml` | 完整 AA 降为 **250/层（合计 1 000）**，原为 1 000/层（合计 4 000） |
| 2026-10-28 11:05 | 用户原话「G阶段按甲方案。按照你的思考和建议的方式推进。」 | 走**甲方案**：把上述已授权的批数**写进冻结配置**（而不是只在入口传参），并配版本化理由与独立评审 |
| 2026-10-28 11:05 | 主负责据授权收窄范围 | **只对齐 AA**。overlay 的其余削减（Tier1 800、Tier2 360、独立验证 200、功效格 200、再训练 80）**不落地**，因为 `GOAL.md` G01/G02 对它们仍写冻结值，同步下调等于改验收标准 |

**范围边界**：本修订只改 AA 的批数与两个受其影响的计划计数。ATE / 完整学习 / 独立验证 / Tier2 / 再训练 bootstrap /
固定策略 bootstrap / 随机名单种子**一律不变**。

**对计划总量的影响**（副本预演实测，`planned_counts()` 逐项比对只有这两项变化）：
`complete_aa_jobs` 4 000 → 1 000、`historical_dgp_jobs` 12 500 → 9 500（**后者是同一批批数的另一种计法，
不与前者重复相加**）。按 `TODO.md` 的作业总数口径（Tier1 6 400 + Tier2 43 500 + AA 4 000 + 再训练 200 + 固定 bootstrap 1 000 = 55 100），
改后为 **52 100**。

## 2. 改动清单（12 行）

行号以 2026-10-28 11:04 实读为准；`execution.yaml` 为 LF、`scenarios.yaml` 为 CRLF，写回时按各自终止符。

| # | 文件:行 | 键 | 改前 | 改后 | 依据 |
|---|---|---|---|---|---|
| 1 | `execution.yaml:25` | `formal_repeats.tier1_aa_per_layer` | 1000 | 250 | 2026-10-25 授权 |
| 2 | `scenarios.yaml:411` | `L0_AA.R` | 1000 | 250 | `v3_config.py:188` `R == max(formal_repetitions.values())` |
| 3 | `scenarios.yaml:429` | `L0_AA.formal_repetitions.complete_aa` | 1000 | 250 | `v3_config.py:190`、`v3_aa.py:316-318` |
| 4 | `scenarios.yaml:1296` | `L1_AA.R` | 1000 | 250 | 同上 |
| 5 | `scenarios.yaml:1314` | `L1_AA.formal_repetitions.complete_aa` | 1000 | 250 | 同上 |
| 6 | `scenarios.yaml:1925` | `L2_AA.R` | 1000 | 250 | 同上 |
| 7 | `scenarios.yaml:1943` | `L2_AA.formal_repetitions.complete_aa` | 1000 | 250 | 同上 |
| 8 | `scenarios.yaml:2942` | `L3_AA.R` | 1000 | 250 | 同上 |
| 9 | `scenarios.yaml:2960` | `L3_AA.formal_repetitions.complete_aa` | 1000 | 250 | 同上 |
| 10 | `scenarios.yaml:264` | `planned_counts.complete_aa_jobs` | 4000 | 1000 | `v3_config.py:207-210` 声明值必须等于推导值 |
| 11 | `scenarios.yaml:261` | `planned_counts.historical_dgp_jobs` | 12500 | 9500 | 同上；推导式 `Σ max(formal_repetitions.values())`，AA 四格各 −750 |
| 12 | `design.yaml:38` | `design.aa.repeats_per_layer` | 1000 | 250 | **范围补正（18:36）**：这是同一个 AA 批数在注册表里的第二份副本，初版 11 行清单漏了它；无代码读取，但 `tests/test_v3_aa.py:242` 会抓注册表内部不一致 |

**第 11 行不是手算猜出来的**：`--dry-run` 只改前 10 行时，在配置副本上完整加载立即抛
`ConfigError: Planned count drift historical_dgp_jobs: declared=12500, derived=9500`。
只改 10 行会在加载期失败——这条已经用副本演练确认（2026-10-28 11:08）。

## 3. 变更前后的绑定值

> **以下两栏由执行时实测填入；未填的项一律视为"尚未修订"。**

| 项 | 改前（实读 2026-10-28 11:06） | 改后（实读 2026-10-28 18:26） |
|---|---|---|
| `load_v3_protocol().config_hash` | `30511a32bcee9db55e8f5ec1bbc2b9d63eb63dc2a13aa5c720f948c781eccdbe` | `00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3`（18:36 含 design.yaml 补正后的最终值；只改前 11 行时为 `6b67261009b8a5ff…`） |
| `source_sha256["execution.yaml"]` | `dc1c8e9ab147e58d95e1367c2abcd90ba02acf05ca27da11e3dfb84da8631733` | `58623f8523ff29cd58352da82c82dac1663047cb34cb938cdd8947eb11e9ca61` |
| `source_sha256["scenarios.yaml"]` | `29a158b046cb91661f2327cc5acbc1dc868a57c17dc0783cfe9d6d41058e9ddb` | `b8fa1480ea39ad7f9d2f2098d4ec957c7ed011865085054090db2bfbe54269e7` |
| `source_sha256["design.yaml"]` | `d2fd51a1156457257cf7977b32bd5aeb1c9745a10e528d029a877ef1b531fa99` | `8890d25b40fbc01888f63ada093adb45cf2106016a798bdeb73a6139ac80ab6f` |
| 其余 4 份 yaml 的 `source_sha256` | 见 `outputs/v3/protocol/approval.json` | **逐一不变**：`business d1259d23…` / `models 19ce3bf5…` / `policy 57ff5721…` / `evaluation 5f6dfcb2…`（2026-10-28 18:36 复算与 Phase A 完全相同） |
| `experiment_matrix.csv` 的 `matrix_sha256` | `c3c7a63ad99fb921698ebbc638db50c18f5c0b672aad09d0a67c37c1dba9a8c7`（`outputs/v3/protocol/approval.json`） | `30645842ea4928975ab99f2ce9f8e83f7a75da4d19c2bae920b1f30dd8881409`（`outputs/v3/protocol_aa250/experiment_matrix.csv`，48 796 B，18:36 重算） |
| `protocol_manifest.json.protocol_sha256` | `eb85a3284a01a4f428c29d4cd84098a123ae629d44ceb6b1ac9fcd11f107e6fc` | `eb85a3284a01a4f428c29d4cd84098a123ae629d44ceb6b1ac9fcd11f107e6fc`（**不变**：`docs/v3_协议.md` 未编辑） |
| `planned_counts.complete_aa_jobs` | 4000 | 1000 |
| `planned_counts.historical_dgp_jobs` | 12500 | 9500 |
| F02 证据里的 `protocol_config_hash` | `e1aa4314b8d84b04…` | **未改**：它是 F02 运行期的绑定值，属历史记录；本修订未改写任何既有 manifest |

**改后值的出处**：`config_hash` 与 7 份 `source_sha256` 来自 `outputs/v3/protocol_aa250/protocol_manifest.json`
（由 `scripts/09_freeze_v3_protocol.py --output outputs/v3/protocol_aa250` 于 2026-10-28 18:36 重新生成，exit 0）；
`matrix_sha256` 为对该目录 `experiment_matrix.csv` 直接 `sha256sum`。
只改前 11 行时的 `config_hash` 为 `6b67261009b8a5ff…`（与 11:08 的副本预演一致）；
补第 12 行 `design.yaml` 后必然变化，**以最终值 `00723dc2…` 为准**。
`design.aa.repeats_per_layer` 无任何 `src/` 或 `scripts/` 代码读取（18:35 全仓 grep 为空），
所以它只影响注册表自洽与 `config_hash`，不影响任何作业的实际批数；实际批数由 `formal_repetitions.complete_aa` 驱动。

**为什么 11 行变 12 行**：首轮全量测试在 18:34 抓出两处硬编码守卫，其中
`tests/test_v3_aa.py` 断言 `design.aa.repeats_per_layer == 1000` 失败——同一个 AA 批数在 `design.yaml` 里还有一份副本，
初版清单没列。把它对齐到 250 是同一授权的直接结果，不是扩大范围；若保留 1000，契约内部就会同时存在两个 AA 批数。

## 4. 哪些既有证据仍然成立

- **A 阶段协议评审**（`docs/reviews/v3_phase_A_review.md`，`approval.json` 的 `review_sha256`）：评审对象是**改前**矩阵，
  作为历史记录成立；本修订需要**新的独立评审**（见 §6），不能拿 A 的评审覆盖。
- **D02 / D03 / E / F01 / F02**：各自 manifest 绑定的是**运行当时**的 `config_hash` / `protocol_config_hash` / 源码哈希。
  本次改动只影响**之后**新跑的作业，不使这些证据失效；但也不得把它们的哈希与本修订后的配置混用（AGENTS §12.6）。
- **既有 1 384 行 AA 证据**（`outputs/evidence/aa/all_repetitions.csv`）：其运行期 9 份 `configs/` 与当前一致，
  但 **6 份源码已漂移** ⇒ 无论走哪条路线，G01 的正式 AA 都要在当前树上重跑，这 1 384 行只能作为成本与方差的实测定价。
- **不得**把"改了配置"读成"旧结论作废"：本修订的唯一效果是让**代码实读的契约**与 **2026-10-25 的授权**一致。

## 5. 验证计划（执行时逐项留证）

1. **预演（已完成，2026-10-28 11:08）**：`out/scratch/sim_v3_aa250/` 副本上走同一入口，
   `load_v3_protocol(root=副本)` 完整通过（含 `planned_counts` 逐项比对），预览 `config_hash=6b67261009b8a5ff…`。
2. **真跑（已完成，2026-10-28 18:24；18:36 补第 12 行）**：`out/scratch/g_route_jia_aa250.py`，先核 200 个 F02 manifest（安全阀）；
   工具断言"恰 1 行 execution + 10 行 scenarios"变了（`patch_exit=0`），否则 `exit=7`。
   改后副本立即由 `load_v3_protocol` 复读：`tier1_aa_per_layer=250`、四个 AA 格 `R == complete_aa == 250`、
   `complete_aa_jobs=1000`、`historical_dgp_jobs=9500`。落盘 mtime：`execution.yaml`/`scenarios.yaml` 均为 18:24:25。
   18:36 直接补 `design.yaml:38` 一行（见 §2 第 12 行），配置随即重新加载通过，`config_hash=00723dc2…`。
3. **重算（已完成，2026-10-28 18:36，exit 0），未就地覆盖 Phase A 目录**：
   ```bash
   .venv/Scripts/python.exe scripts/09_freeze_v3_protocol.py --output outputs/v3/protocol_aa250
   ```
   `outputs/v3/protocol/` 是 Phase A 的快照——它的 `protocol_sha256` 绑定 `docs/v3_协议.md` 的字节，
   就地重跑等于把"Phase A 批准了什么"改写成"今天是什么"。**原目录逐字节保留。**
4. **口径偏差已按声明处理（2026-10-28 18:26）**：09 号脚本把 `experiment_results_exist` **硬编码为 `false`**
   （`scripts/09_freeze_v3_protocol.py:39`），而今天 D02/D03/E/F01/F02 的结果都已存在。
   修订目录里 `protocol_manifest.json` 的该字段仍是脚本输出 `false`（不改脚本产物），
   由第 5 步的 `revision.json` 声明 `experiment_results_exist: true` 并注明来源；
   `experiment_matrix.csv`、`config_hash`、`source_sha256`、`planned_counts` 照用脚本输出。
5. **档案（已完成，2026-10-28 18:26；18:37/18:47 两次补正）**：`outputs/v3/protocol_aa250/approval_revision_20261028.json`（18:47 版 3 708 B；19:03 版 4 204 B；后续以 git 实读为准），含
   `supersedes_config_hash`（`30511a32…`）、`config_hash`（`00723dc2…`；`6b672610…` 只是十一行中间值，不再作为最终值）、`changed_files` 的 3 份改动文件 `source_sha256` + manifest 中完整 7 份、
   `reason_doc` 与其 sha256、`authorized_by`（2026-10-28 11:05 用户裁决）、`scope`（AA 4 格 250/层，其余不变）、
   `experiment_results_exist: true`、`review.status = pending_independent_review`。
   `outputs/v3/protocol/approval.json` **保留原字节**（sha256 `8f8a7e21…`，已记录在修订文件里）。
6. **测试（已完成）**：最终树全量串行 **1 275 项、EXIT=0、18:36:49–18:45:27（518 s）**，
   凭据 `outputs/evidence/test_runs/pytest_g_aa250_20261028_1836.{log,json}`；
   `find src sql configs -newermt "2026-10-28 18:36:41"` 返回空。18:24 首轮 **EXIT=1**（2 项旧契约守卫）保留为
   `pytest_g_aa250_20261028_1824.{log,json}`，它直接促成 §2 第 12 行补正。
7. **独立评审**：对本修订单独评审，返回 PASS 后才允许把 G01 记为"按新契约开跑"。**当前未做。**
8. **文档指针**：README / GOAL 的 G01 行改为指向新修订文件；**不编辑** `docs/v3_协议.md`
   （一改，Phase A 记录的 `protocol_sha256 = eb85a328…` 就再也复算不出来）。

## 6. 回滚

把 §2 的 12 行改回原值，并把守卫测试的冻结值一并回滚（`tests/test_v3_aa.py` 两条断言 250→1000、`tests/test_v3_power.py` 的 `FROZEN_CONFIG_HASH` `00723dc2…`→`30511a32…`；18:24 的 pre-fix 日志已证明只回配置会让这两条变红）→ 重跑 `scripts/09_freeze_v3_protocol.py --output <新目录>`（**必须显式给 `--output`**：脚本默认写 `outputs/v3/protocol`，会覆盖 Phase A 目录）→ 写盘后复核 `outputs/v3/protocol/approval.json` 仍为 `8f8a7e21…`、`experiment_matrix.csv` 仍为 `c3c7a63a…` → 回滚记录追加到**本修订档案**（或新的 `approval_revision_*.json`），**不得写入 Phase A 的 `approval.json`**。
无需改动任何数据产物：本修订不改变已落盘作业的绑定值。

## 7. 变更记录

| 时间 | 变更 |
|---|---|
| 2026-10-28 11:10 | 建立草稿：授权链、11 行清单、绑定值待填表、既有证据口径、验证与回滚 |
| 2026-10-28 11:25 | §5 改写：修订落 `outputs/v3/protocol_aa250/`，Phase A 目录逐字节保留；记 09 号 `experiment_results_exist` 硬编码 `false`（第 39 行）与`docs/v3_协议.md` 不可编辑两条约束 |
| 2026-10-28 18:26 | 执行完成：11 行落盘（18:24:25，`patch_exit=0`）、09 重算入新目录（18:24:27，exit 0）、修订档落盘（18:26）；§3 改后值全部实读填入（config_hash `6b672610…`、execution `58623f85…`、scenarios `b8fa1480…`、matrix `d268b727…`、protocol_sha256 不变）；其余 5 份 yaml 逐一复算不变；新树全量串行测试 18:24 起跑。独立评审仍未做 |
| 2026-10-28 18:37 | **范围补正**：全量测试 18:34 结束（EXIT=1，2 项失败），抓到 `design.yaml:38` 的 AA 批数副本仍为 1000、`tests/test_v3_power.py` 的 `FROZEN_CONFIG_HASH` 仍钉旧值。按同一授权改 `design.yaml` 为 250（第 12 行）、更新两处守卫测试；18:36 重跑 09，最终 `config_hash=00723dc2…`、matrix `30645842…`、design `8890d25b…`。**11 行 → 12 行** |
| 2026-10-28 18:37 | 修正 §4 的一处指针：独立评审在 §5 第 7 条，不在 §6（§6 是回滚） |
| 2026-10-28 18:46 | 最终全量串行测试 **1 275 项、EXIT=0、18:36:49–18:45:27（518 s）**，日志与 JSON 凭据入库；18:24 首轮 EXIT=1 的两项失败与处置保留在 pre-fix 凭据里 |
| 2026-10-28 19:03 | 预评审 2 项 P1 修复：§6 回滚改 **12 行**、§5.5 档案改为 **3 708 B / `config_hash 00723dc2…`**（`6b672610…` 标注为十一行中间值）；`approval_revision_20261028.json` 补 `updated_at` 与 `revision_history`，并在本条登记后重算本文件 sha 回填修订档（前值 `6417c059…`）。预评审为草稿复核，不替代 §5 第 7 条的独立评审 |
| 2026-10-28 19:25 | **独立评审返回 PASS WITH CONDITIONS**（`docs/reviews/v3_phase_G_aa250_review.md`，0 P0 / 1 P1 / 3 P2；12 行、7/7 源哈希、Phase A 字节不变、F02 绑定不变、1 275 项/518 s 均独立复算通过）。C1 回滚补 tests 4 行与 `--output` 及回滚记录落点；C2 GOAL 11 行→12 行并指向本文；C3 §5.5 字节数与 source_sha 表述修正。修完重算本文件 sha 回填修订档 |
