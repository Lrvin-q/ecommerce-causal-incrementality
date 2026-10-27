# Phase E 窄口径确认复审（第三环 recheck）

> 合成数据 / 已知 DGP。评审时间：**2026-10-28 06:05（北京时间）**。
> 任务边界：只确认复审 `docs/reviews/v3_phase_E_rereview.md`（05:34）提出的 3 项新 P1（N1/N2/N3）
> 与 3 项 P2 的 4 项廉价修复（05:40–05:48）是否真落地；不重开原 6 P1，不重跑任何作业。
> 所有数字由本评审独立复算：只读文件 + 对已入库 CSV/JSON 的短时 pandas/json 计算
> （`./.venv/Scripts/python.exe`，PYTHONUTF8=1），未运行 pytest / 管线 / 拟合，未写任何受冻结文件。

## §0 判定

**PASS。**
`GOAL.md` 的 E01/E02 行**可以由"未证实"改为"通过"**：复审 05:34 明言"4 项廉价修复落地后通过即成立、证据本身可靠"，本 recheck 逐项确认 3 项新 P1（N1/N2/N3）与 3 项 P2 全部真实关闭、主负责给出的每一个数字都被独立复算复现（无一不符）；状态改写本身须由主负责执行（本评审按任务书不得写 GOAL.md/TODO.md），且残留的代码级子项（meta 缺 `cfg.hash(64)`、日志↔meta 断言未进 `scripts/24_e_evidence.py`）已按 §11.2 合规地推迟到 F02 之后并登记在案，不构成阻塞。

---

## §1 N3（P1-2 残留）：§6 真值 oracle 来源表述 —— **closed**

**文档**（`docs/v3_phase_E_evidence.md:430-440`，修复后行号；复审所指旧 419-421 内容已替换）：
现文写"**两个口径的真值最优都由分币精确 DP 求出**（`cent_exact_dp`：主口径喂 `cost_hat`、
敏感性口径喂 raw `cost_true`，价值都用带符号分币的 `tau_true`）"，并明写
"`truth_milp_*` 列**不是真值最优的来源，只是审计复核**"、MILP 求的是"0 成本抬到
`cost_floor` 后的**收紧问题**"、只能读 status/gap/`truth_feasible_under_original_cost`，
附 05:40 更正注记。

**源码核对**（`src/causal_growth/policy/v3_policy_evidence.py`，逐行读过 820-932）：
- (a) 主口径：`:858-862` `truth_exact_cost_hat = pol.cent_exact_dp(to_signed_cents_half_up(tau_true), to_cents_half_up(cost_hat), …)` ✓；且 `:911-913` 行内字段 `truth_oracle_cost_basis="cost_hat_primary; raw_realized_cost_true_sensitivity"` ✓。
- (b) 敏感性口径：`:851-855` `truth_exact = pol.cent_exact_dp(to_signed_cents_half_up(tau_true), to_cents_half_up(cost_true), …)` ✓。
- (c) MILP 仅复核：`:863-864` 与 `:920-921` 注释逐字为"MILP 只用于复核界与 gap""它的 bound/incumbent 不是 raw truth 问题的界，只能看 status/gap" ✓。文档引用的行号（`:851-870`、`:856-857`、`:920-921`）与当前源码逐行吻合。
- (d) 全文 grep `truth_milp`：命中 `:431/434/436/438`（即本次改正段与更正注记）、`:545-546`、`:637`、`:755`（后三处讲 §9.9 未修的 sentinel 分支，与 oracle 来源无关）。grep `真值最优`：命中 `:431/434/438/460`，`:460` 是分解恒等式定义（真值最优 − 实际策略真值），与 DP oracle 口径一致。**全文再无第二处把 oracle 归给 MILP。**

数值未受影响的旁证：文档引 A 学习误差 0.98436@0.04、0.99284@0.10，本评审从
`outputs/tables/v3_phase_E_decomposition.csv`（`learning_error_cost_hat_basis_cny_per_user`，
greedy 行）复算得 **0.98436 / 0.99284**，B 的 0.72032@0.04 亦复现（`…_cf.csv`）。

## §2 N1：§8.1 greedy vs greedy_local_swap 两家族分述 —— **closed**

文档新表（`docs/v3_phase_E_evidence.md:580-592`）声称的每个数字，本评审从落库表
`outputs/tables/v3_phase_E_conservative.csv`（A）与 `…_cf.csv`（B）独立复算
（24 格 = 3 mode × 8 档，policy 取 `greedy_incremental_profit_per_cost` vs `greedy_local_swap`，
按 mode+per_user_budget 配对，索引完全对齐）：

| 列 | A（文档：24/24 全同） | B（文档声称） | 本评审复算 B |
|---|---|---|---|
| selected_count_mean | 24/24，max diff 0.0 ✓ | 24/24 | 24/24，max 0.0 ✓ |
| predicted_cost_mean | 24/24 ✓ | 19/24，max \|差\| 0.107 | **19/24，max 0.10700029** ✓，差格 (buffered, 0.04/0.2/0.3)+(expected, 0.1/0.4) 与文档逐格一致 ✓ |
| actual_spend_mean | 24/24 ✓ | 21/24，max 10 | **21/24，max 10.0** ✓，差格 (buffered, 0.04/0.3)+(expected, 0.4) ✓ |
| true_value_per_user_mean | 24/24 ✓ | 21/24，max 0.000303 | **21/24，max 0.00030333** ✓，差格同上 ✓ |
| overrun_probability | 24/24 ✓ | 24/24 | 24/24，max 0.0 ✓ |

复算与文档表**逐格、逐最大值完全一致，无一不符**。文档同时删除了"A 与 B 都是完全相同"的
旧句并保留更正注记（`:591`），符合 §12.4。§7.2（`:514-516`）的规模表同题陈述也复核为真：
B 的 `predicted_value_cny` swap−greedy **min=0.0、11 格严格更大、0 格更差**（"swap 从不更差"✓），
max \|差\| **0.300311 @ (1000 池, 0.04)** ✓，按池 4/8、5/8、2/8 ✓；A 全 24 格 max 0.0 ✓。

## §3 N2：运行日志重导出与登记一致性 —— **closed**

1. **文件存在**：`outputs/evidence/e_evidence_rep0_a/run_constant.log`（磁盘 2 597 B）、
   `outputs/evidence/e_evidence_rep0_b/run_cf.log`（磁盘 2 881 B）✓。
2. **时间戳↔meta 一致性**：A 日志首行 `[E evidence 01:12:03]` = `meta_constant.json`
   `created_at=2026-10-28T01:12:03+08:00` 的时分秒 ✓；B 日志首行 `[E evidence 01:35:26]` =
   `meta_cf.json` `created_at=2026-10-28T01:35:26+08:00` ✓。（复审 R11 抓到的旧日志
   `6ac1ea95…`/2 209 B/19:17 形态已被替换，现 sha 为 `0a32c7f9…`。）
3. **哈希/字节三方一致**：两条日志在 A/B 目录级 `coverage.json` 与顶层
   `outputs/evidence/coverage.json` 中的 bytes+sha256（A `0a32c7f90cbedca1…`/2597，
   B `dbf0001d7b9e6904…`/2881，source 分别为 `out/logs/e_r2_A_20261028_0112.log`、
   `out/logs/e_r2_B_20261028_0112.log`）与磁盘逐一相符 ✓；A 包 11 条、B 包 12 条记录中
   均含各自日志，A 包不再含任何旧运行日志 ✓。
4. **顶层登记表**：records **42** 条 ✓、`total_bytes=15 861 713` 且与 42 条 bytes 之和相等 ✓、
   `registry_repairs` 第 **4** 条（at 05:44）如实描述 N2 缺口、重导出动作、时间戳断言、
   `records_after=42`、`total_bytes_after=15861713` ✓。
5. **全表独立复算**：本评审对顶层 42 条 + A 目录 11 条 + B 目录 12 条 = **65 条记录**逐条重算
   文件存在 + bytes + sha256（流式哈希），**0 条不符** —— 主负责"65 条全表复算 0 不符"的声称
   独立复现 ✓。三个登记表的 `total_bytes` 字段亦与各自记录之和相等（TOP 15 861 713、
   A 6 974 437、B 6 982 239）。

## §4 三项 P2 —— **全部 closed**

**(a) 校准 JSON 键数**（`docs/v3_phase_E_evidence.md:189-197` 与产物表 `:664`）：
本评审复算 `outputs/tables/v3_phase_E_calibration.json` vs `…_cf.json`：各 **40** 键、键集合相同，
**34 键逐值相同、6 键不同**，不同键恰为 `calibration_rows_path`、`frame_model`、
`frame_model_is_chosen`、`frame_model_is_chosen_in_full_fit`、`tau_hat_nunique`（1 vs 59 861）、
`tau_hat_sd_cny`（1.1102e-16 vs 0.781647）——与文档两处（正文 :189 与产物表 :664）逐字一致 ✓。
文档保留"原文写 39 个"的更正注记，符合 §12.4。

**(b) 随机汇总表列数**（`:382-384`）：复算 `v3_phase_E_random_summary.csv` vs `…_cf.csv`：
各 **17 列、同名同序、列集合相同**，两表 `DataFrame.equals` 为 **True**（8×17 逐值相同，
含字符串列 `interpretation`）✓。`mean_value_per_actual_spend` 同时存在于两表，"B 多一列"旧句
已删并留更正注记 ✓。

**(c) `docs/v3_phase_E_coverage.md` 4 处过期陈述**：
1. **小池行**（:79）：现文写有效证据是 B 家族 `…_small_pool_cf.csv`（128 行、01:40），A 家族
   **无有效小池表**，`v3_phase_E_small_pool.csv` 标 `stale_pre_guard`。磁盘核实：该文件 mtime
   **10-27 19:23** ✓、不在 A 证据包 11 条记录内（已排除）✓；正文产物表（evidence.md:656-657）
   同口径 ✓。
2. **19:17 运行段**（:136-146）：旧"E01/E02 仍标未证实等待独立评审"句已划线，05:48 更新明写
   19:17 运行**已被取代**（A 01:12:03–01:35:23、B 01:35:26–02:04:28，同 `git_commit=e0048100…`）✓。
3. **规模扫描 scale 声称**（:148-158）：05:48 追注把"24/24 完全相同"限定为仅 A 成立，并给出 B
   的分列数字。本评审从 `outputs/tables/v3_phase_E_scale.csv` 与 `…_scale_cf.csv` 复算
   （24 格 = 3 池 × 8 档，solver=greedy vs greedy_local_swap，索引对齐）：
   **A**：`n_selected/predicted_value_cny/predicted_cost_cny/lp_upper_bound_cny/true_value_per_user/actual_spend_cny/true_value_per_actual_spend` 七列全 **24/24 相同（max diff 0.0）**，只有 `seconds` 不同 ✓；
   **B**：`predicted_value_cny` **11/24** 不同 max **0.3003108** ✓、`predicted_cost_cny` **11/24** max **0.1647912** ✓、`true_value_per_user` **5/24** max **0.029170** ✓、`true_value_per_actual_spend` **5/24** max **0.0577919** ✓、`actual_spend_cny` **2/24** max **10** ✓、`n_selected` 与 `lp_upper_bound_cny` **24/24 相同** ✓。追注数字与复算**逐一相符**。
4. **评审状态行**（:143-146）：现文如实记录"复审 05:34 PASS WITH CONDITIONS（0 P0 + 3 新 P1）→
   修复 05:46 落地 → E01/E02 仍未证实、待窄口径确认"，与 §7.4 纪律一致 ✓。

## §5 一致性清扫（§12.4：改完一处、全文无第二份残留）

对 `docs/v3_phase_E_evidence.md`、`docs/v3_phase_E_coverage.md`、`GOAL.md`、`TODO.md`、
`AGENT_HANDOFF.md` grep 了 `39 个逐值相同 / 39 键 / B 多一列 / 24/24 完全相同 / 真值最优都来自
truth_milp / run_constant.log→out/e_evidence_formal/run.log / 6ac1ea95` 等旧口径形态：

- 两份 E 文档与 `GOAL.md` 中所有命中均为**更正注记或对复审缺陷的如实转述**（"原文写…"形态），
  非未标注残留 ✓。`GOAL.md:23-24`（E01/E02 行）对 oracle 的描述已是修正后口径
  （`cent_exact_dp(带符号分币 tau_true, cost_hat)` 主口径、`truth_milp_*` 只是复核）✓，
  且 E01/E02 均仍标"未证实、只差第三环确认"✓；`GOAL.md:7/36` 与本 recheck 的存在一致 ✓。
- **唯一残留**：`TODO.md:165`（05:13 前的历史自证条目）仍写"两版本各 40 键、**39 键逐值相同**"，
  行内无更正标注；同文件 `:311` 已记录正确值"40 键中 34 同、6 异（原文写 39/1）"。按项目自身
  惯例（TODO.md:291"历史条目保留原值并标注更正"）应在 :165 补一处指向 :311 的行内标注。
  本评审无权写 TODO.md，登记为**不阻塞的遗留项**（见 §6）。
- `AGENT_HANDOFF.md` 无上述任何旧口径残留；其 :4 的"E 复审尚未返回"是 05:25 时间戳快照，
  早于 05:34 复审返回，属时间戳可辨的历史状态而非矛盾陈述（建议下次交接更新时顺带刷新，不阻塞）。

## §6 仍未关闭的事项（均不阻塞 E01/E02 转"通过"）

1. **TODO.md:165 的"39 键"历史条目缺行内更正标注**（§12.4 卫生项；正确值已记于 TODO.md:311）。主负责下次维护 TODO.md 时补标注即可。
2. **日志↔meta 时间戳断言尚未进 `scripts/24_e_evidence.py`**：本次修复中手工执行过并通过（A 01:12:03 / B 01:35:26），因该文件被 E 的 `source_sha256` 绑定、改动须重跑两家族，且重跑属数据作业不得与 F02 并行（AGENTS §11.2），已登记为 F02 合并后待办（evidence.md:683-686、顶层 `registry_repairs` 第 4 条 `consistency_check` 字段）。这是复审自己认可的推迟，不是缺口扩大。
3. **meta 缺 `cfg.hash(64)`**（= `e1aa4314b8d84b04…`，可从 D03 分片摘要交叉读出）：复审已判为残留代码级子项、排在 F02 之后（GOAL.md:23），维持原状。
4. F02 正式 200 rep 仍在飞行（投影 ~18:04），本 recheck 全程未触碰任何冻结路径；E 的全量串行测试复跑按 §11 纪律推迟至 F02 分片退出后。

## §7 方法与凭据

- 只读工具 + 6 次短生命周期 python 进程（pandas/json/hashlib），全部针对已入库
  `outputs/tables/v3_phase_E_*`、`outputs/evidence/**` 与两份 E 文档；65 条记录 sha256 用流式
  1 MiB 分块计算。未运行 pytest、未运行任何 `scripts/`、未写除本文件外的任何路径、未执行任何
  改变状态的 git 命令。
- 本文所有"✓"均对应本评审自己复算或与磁盘原件逐字比对的结果，不采信主负责自述。
