# G 阶段协议修订：AA 批数 1000/层 → 250/层

> **合成数据 / 已知 DGP。**
> **状态：草稿，尚未执行（2026-10-28 11:10，北京时间）。**
> 本文是 `configs/v3/execution.yaml` 的 `change_matrix_requires_versioned_reason_and_review: true`
> 所要求的版本化理由。**在 §4 的前后绑定值全部填实、独立评审返回结论之前，不得把本文当作已生效的协议记录引用。**
> 改动执行时机：F02 四个分片全部退出之后（AGENTS §11：`configs/v3/*.yaml` 在 F02 的绑定 glob 内）。

## 1. 授权链与范围

| 时间 | 出处 | 授权内容 |
|---|---|---|
| 2026-10-25 13:45 | 用户决策，已写入 `GOAL.md` G01 行与 `configs/budget/repetition_overlay.yaml` | 完整 AA 降为 **250/层（合计 1 000）**，原为 1 000/层（合计 4 000） |
| 2026-10-28 11:05 | 用户原话「G阶段按甲方案。按照你的思考和建议的方式推进。」 | 走**甲方案**：把上述已授权的批数**写进冻结配置**（而不是只在入口传参），并配版本化理由与独立评审 |
| 2026-10-28 11:05 | 主负责据授权收窄范围 | **只对齐 AA**。overlay 的其余削减（Tier1 800、Tier2 360、独立验证 200、功效格 200、再训练 80）**不落地**，因为 `GOAL.md` G01/G02 对它们仍写冻结值，同步下调等于改验收标准 |

**范围边界**：本修订只改 AA 的批数与两个受其影响的计划计数。ATE / 完整学习 / 独立验证 / Tier2 / 再训练 bootstrap /
固定策略 bootstrap / 随机名单种子**一律不变**。

## 2. 改动清单（11 行）

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

**第 11 行不是手算猜出来的**：`--dry-run` 只改前 10 行时，在配置副本上完整加载立即抛
`ConfigError: Planned count drift historical_dgp_jobs: declared=12500, derived=9500`。
只改 10 行会在加载期失败——这条已经用副本演练确认（2026-10-28 11:08）。

## 3. 变更前后的绑定值

> **以下两栏由执行时实测填入；未填的项一律视为"尚未修订"。**

| 项 | 改前（实读 2026-10-28 11:06） | 改后（执行时填） |
|---|---|---|
| `load_v3_protocol().config_hash` | `30511a32bcee9db55e8f5ec1bbc2b9d63eb63dc2a13aa5c720f948c781eccdbe` | `<待填>`（副本预演值 `6b67261009b8a5ff…`，仅作预览） |
| `source_sha256["execution.yaml"]` | `dc1c8e9ab147e58d95e1367c2abcd90ba02acf05ca27da11e3dfb84da8631733` | `<待填>` |
| `source_sha256["scenarios.yaml"]` | `29a158b046cb91661f2327cc5acbc1dc868a57c17dc0783cfe9d6d41058e9ddb` | `<待填>` |
| 其余 5 份 yaml 的 `source_sha256` | 见 `outputs/v3/protocol/approval.json` | **应逐一不变**（执行后比对） |
| `outputs/v3/protocol/experiment_matrix.csv` 的 `matrix_sha256` | `c3c7a63ad99fb921698ebbc638db50c18f5c0b672aad09d0a67c37c1dba9a8c7`（`approval.json`） | `<待填>`（`scripts/09_freeze_v3_protocol.py` 重算后） |
| `protocol_manifest.json.protocol_sha256` | `eb85a3284a01a4f428c29d4cd84098a123ae629d44ceb6b1ac9fcd11f107e6fc` | `<待填>` |
| `planned_counts.complete_aa_jobs` | 4000 | 1000 |
| `planned_counts.historical_dgp_jobs` | 12500 | 9500 |
| F02 证据里的 `protocol_config_hash` | `e1aa4314b8d84b04…` | **不得改**：它是 F02 运行期的绑定值，属历史记录；本修订不改写任何既有 manifest |

## 4. 哪些既有证据仍然成立

- **A 阶段协议评审**（`docs/reviews/v3_phase_A_review.md`，`approval.json` 的 `review_sha256`）：评审对象是**改前**矩阵，
  作为历史记录成立；本修订需要**新的独立评审**（见 §6），不能拿 A 的评审覆盖。
- **D02 / D03 / E / F01 / F02**：各自 manifest 绑定的是**运行当时**的 `config_hash` / `protocol_config_hash` / 源码哈希。
  本次改动只影响**之后**新跑的作业，不使这些证据失效；但也不得把它们的哈希与本修订后的配置混用（AGENTS §12.6）。
- **既有 1 384 行 AA 证据**（`outputs/evidence/aa/all_repetitions.csv`）：其运行期 9 份 `configs/` 与当前一致，
  但 **6 份源码已漂移** ⇒ 无论走哪条路线，G01 的正式 AA 都要在当前树上重跑，这 1 384 行只能作为成本与方差的实测定价。
- **不得**把"改了配置"读成"旧结论作废"：本修订的唯一效果是让**代码实读的契约**与 **2026-10-25 的授权**一致。

## 5. 验证计划（执行时逐项留证）

1. 预演：`out/scratch/sim_v3_aa250/` 副本上走同一入口，`load_v3_protocol(root=副本)` 完整通过（含 `planned_counts` 逐项比对）；
2. 真跑：`out/scratch/g_route_jia_aa250.py`，须先满足 200 个 F02 manifest（安全阀，exit=5 若未满足）；
3. 重算：`scripts/09_freeze_v3_protocol.py`，比对 §3 全部行；
4. 档案：`outputs/v3/protocol/approval.json` 追加 `revision` 块（不改历史 `approved_on` 与 `status`）；
5. 测试：F02 解冻后跑全量串行测试（AGENTS §11.4），日志入库；
6. 独立评审：对本修订单独评审，返回 PASS 后才允许把 G01 记为"按新契约开跑"。

## 6. 回滚

把 §2 的 11 行改回原值 → 重跑 `scripts/09_freeze_v3_protocol.py` → 在 `approval.json` 追加一条回滚 revision。
无需改动任何数据产物：本修订不改变已落盘作业的绑定值。

## 7. 变更记录

| 时间 | 变更 |
|---|---|
| 2026-10-28 11:10 | 建立草稿：授权链、11 行清单、绑定值待填表、既有证据口径、验证与回滚 |
