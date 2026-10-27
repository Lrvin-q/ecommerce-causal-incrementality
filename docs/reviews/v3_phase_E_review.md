# E01/E02 证据层独立评审

> **合成数据 / 已知 DGP**｜scenario `L1_main`｜D03 正式 rep 0（`n=200 000`；test 60 000）｜`chosen=constant`
> 评审对象：`docs/v3_phase_E_evidence.md`（385 行，文档时间 2026-10-27 19:44:50）、`docs/v3_phase_E_coverage.md`（19:55:09）、`docs/v3_phase_E_interface.md`、`outputs/tables/v3_phase_E_*`（9 个产物）、`out/e_evidence_formal/frame_rep0.csv` 与 `run.log`。
> 对象提交：E 文档与 9 个产物最后落库于 `8617b68`（2026-10-27 19:55:15）。评审时 HEAD `906767d8`（21:13:04，只含 D03 测试提交，未改 E 产物）；D03 正式快照为 `130a3091`（12:53:50）。
> 评审时间：2026-10-27 21:13（北京时间）。
> 评审人：独立评审，未参与 E01/E02 的实现、运行与文档写作。
> 复算环境：Windows Git Bash；`PYTHONUTF8=1`；全部 Python 走 `./.venv/Scripts/python.exe`；复算均通过 stdin heredoc 只读执行，未在仓库内写临时脚本。
> 约束：未改源码/配置/数据/表格/TODO/GOAL；未写 `out/` 或 `outputs/`；未 git commit/push；未跑正式 R；未跑 pytest。

## 0. 结论与一页纸判定

**PASS WITH CONDITIONS**——数字层可逐项复现，真值隔离成立；但 E01 的"求解器互证"在 `τ̂` 恒定下退化，E02 的"真值最优"口径与正文描述不符，证据包/源码绑定缺失，且有 1 处预算事实陈述与落库表直接矛盾。修正 6 项 P1 之前，`GOAL.md:23-24` 的 E01/E02 仍应保持"未证实"，不能记为正式通过。

| 维度 | 判定 | 边界与依据 |
|---|---|---|
| 关键数字复算（§2/§3/§4/§5/§6/§7/§8） | **通过** | 校准 13 个数、随机 8 档、保守 72 行、分解 16 行、规模 96 行均与报告末位一致；见 §1 复算表 |
| E01 求解器名实相符/互证 | **不通过（P1-1）** | 60 000 个 test 用户的 `tau_hat` 只有 1 个取值；24/24 相等、local swap 24/24 无动作、求解误差≈0 都是"全等值背包"的必然结果，不能检验价值排序 |
| E01 桶宽收敛 | 数值通过，口径说明有误（P2-1） | 48 行、均值/最大 gap/丢弃数全部复现；但 `gap_per_user` 的分母是池人数 500，不是"分币 DP 的精确目标值" |
| E02 学习/求解误差分解 | **不通过（P1-2、P1-6）** | 真值 oracle 用 `cost_true`（0/10 实现成本）做可行性，策略预算用 `cost_hat`（期望成本）；低预算档学习误差被低估；且只跑 `chosen=constant` |
| E02 三种预算口径 | 数值通过，一句事实错误（P1-5） | expected/buffered/worst 的 0.20 行与全档均值全部复现；但 `:187` "1.00 档实际支出等于预算上限"与表矛盾（50 570 vs 60 000） |
| 真值隔离 | **通过（有来源保留）** | 9 列帧、`user_id` 唯一；`v3_models.py:2066-2067` 先冻结 7 列选人字段再合并真值；策略函数只用 `tau_hat/cost_hat`；但正式路径是"重建 D03"而非读取冻结 CSV（P1-3） |
| 可比性 | 部分通过 | 同 rep、同用户、同预算网格；无"按选模频率替代"；但只有 `chosen=constant`，无跨模型对照；未给按实际支出的每元价值（P1-6、P2-8） |
| 证据链/coverage | **不通过（P1-3）** | `outputs/evidence/coverage.json` 13 条记录中无 E；E meta 无 `git_commit`/`source_sha256`/`cfg_hash`/`protocol_source_hash`；帧与 `run.log` 只在被忽略的 `out/` |
| 解释边界 | 部分通过（P1-4、P1-6） | 单 rep、constant、DGP 真值、observed_value 延后均已披露；但校准的"个体不排序/严重欠离散"是对 0/10 实现的误读，学习误差主导被写成一般结论 |
| 范围覆盖 | **未覆盖** | 仅 rep 0；无非 constant 模型；只有池级表、无 200 rep 合并；无真实观测价值；无跨场景；见 §4 |
| **总判定** | **PASS WITH CONDITIONS** | 0 P0、6 P1、9 P2；E01/E02 仍为"未证实"，修 P1 后重审 |

**为什么不是 FAIL**：没有发现真值进入选人/聚合/播种，也没有发现表被整表复制或跨 run root 混块；10 张表的每个头条数字都能从已落库 CSV/JSON 复算，且与 D03 正式 rep 0 的 constant 贪心 8 档逐格 0.0 差异。缺陷集中在"退化实例被当成互证"、"真值 oracle 口径写错"、"证据包没导出"和"解释越界"，不是结果被污染。

**为什么不是 PASS**：E01 的核心卖点是"DP/MILP/LP 名实相符、枚举互证"，而当前 24 个实例的价值向量全等；E02 的核心卖点是"学习误差 vs 求解误差"，而真值 oracle 与策略预算不在同一成本口径上。这两点不修，E01/E02 不能从"未证实"转为"已证实"。

## 1. 复算表

### 1.1 复算方法与口径

- 只读取 `outputs/tables/v3_phase_E_*.csv/json`、`out/e_evidence_formal/frame_rep0.csv`、`out/e_evidence_formal/run.log`、`outputs/evidence/coverage.json`、`outputs/evidence/d03_formal/coverage.json`、`outputs/tables/v3_phase_D03_formal_policy_grid.csv` 及源码；未调用 E 脚本重跑，未写任何仓库文件。
- 复算脚本全部为 `python - <<'PY' ... PY` 的 stdin heredoc；pandas 3.x 下只做只读 `read_csv`/`groupby`/`pivot_table`。没有把任何表写回 `outputs/` 或 `out/`。
- 差异列 `0` 表示报告值与落库值在报告展示精度内一致；`—` 表示报告未给该数，由本评审补算。

### 1.2 关键数字

| 项目 | 报告值 | 复算值 | 差异 | 证据 |
|---|---:|---:|---:|---|
| §2 校准 n / 预测均值 / 观测均值 | 19 987 / 0.819481 / 0.818532 | 19 987 / 0.819480866 / 0.818532046 | 0 | `v3_phase_E_calibration.json` |
| §2 偏差 / 相对偏差 / 总和比 | −0.000949 / −0.1158% / 0.998842 | −0.000948820 / −0.001157831 / 0.998842169 | 0 | 同上 |
| §2 MAE / RMSE | 1.48614 / 2.73529 | 1.486140082 / 2.735292950 | 0 | 同上 |
| §2 Pearson / OLS 斜率 / 截距 | 0.08525 / 0.61657 / 0.31326 | 0.085254357 / 0.616570211 / 0.313264555 | 0 | 同上 |
| §2 预测 sd / 观测 sd | 0.37907 / 2.74148 | 0.379069477 / 2.741478028 | 0 | 同上 |
| §3 greedy/local/milp/brute 对 exact 最大绝对差 | 0.0（24/24；brute 8/8） | 0.0 | 0 | `v3_phase_E_small_pool.csv` |
| §3 LP 对 exact 的最大高出 | 报告未给 | +0.287538（LP 是上界，不是可行解） | — | 同上 |
| §3 MILP 状态 | 23 `optimal` + 1 `time_limit` | 23 + 1；时限行 gap=0.004341、incumbent=57.879227、bound=58.130456、`may_claim_optimal=False` | 0 | 同上 |
| §3 LP−exact 最小值 | −1.1e-12 | −1.136868e-12（2 格为负） | 0 | 同上 |
| §3 可行性 | 104 True、24 LP NaN | 104 True、24 NaN，无 False | 0 | 同上 |
| §4 五档平均 gap（0.01/0.05/0.10/0.50/1.00） | 0 / 0.00022 / 0.00022 / 0.00610 / 0.01278 | 0 / 0.000220 / 0.000220 / 0.006096 / 0.012780 | 0 | `v3_phase_E_bucket_convergence.csv` |
| §4 五档最大 gap | 0 / 0.00059 / 0.00059 / 0.01587 / 0.02233 | 0 / 0.000588 / 0.000588 / 0.015865 / 0.022329 | 0 | 同上 |
| §4 丢弃数（0.01/0.05/0.10/0.50/1.00） | 0 / 2 / 5 / 72 / 124 | 0 / 2 / 5 / 72 / 124 | 0 | 同上 |
| §4 `gap_per_user` 分母 | 报告称"分币 DP 精确目标值" | 500（池人数）；`gap_to_exact/500` | **口径错误（P2-1）** | 同上 + `v3_policy_evidence.py:603-604` |
| §5 8 档随机均值 / sd / 分位数 / 超支概率 | 8 行全表 | 8 行全表一致 | 0 | `v3_phase_E_random_summary.csv` |
| §5 `mean_se` 范围 | 0.000441–0.000852 | 0.000441/0.000541/0.000754/0.000818/0.000852/0.000835/**0.000270**/**0.000000** | 区间漏项（P2-3） | 同上 |
| §5 1.00 档实际支出 | "等于预算上限" | 50 570.00；预测 49 190.15；预算 60 000 | **−9 430 / −15.72%（P1-5）** | 同上 |
| §6 学习误差（0.04–1.00） | 0.73162 / 0.88758 / 0.91780 / 0.86774 / 0.73040 / 0.79188 / 0.58674 / 0.58674 | 同左（raw `cost_true` 口径） | 0 | `v3_phase_E_decomposition.csv` |
| §6 求解误差 / 恒等式残差 | 0–0.02 / 最大 0.0 | 0–0.02 / 最大 3.469e-17 | 0 | 同上 |
| §6 真值最优值（0.04/0.10/0.20+） | 0.76556 / 0.91304 / 1.01830 | 同左（20 个正 τ 用户；池 500） | 0 | 同上 + 池复算 |
| §6 同预算口径下的学习误差（本评审补算） | 报告未给 | 0.04：**0.98436**；0.10：**0.99284**；0.20：0.91780 | **+0.25274 / +0.10526（P1-2）** | 同上；`sum(cost_hat)=16.5343<20` |
| §7 规模状态（1000/5000/60000） | 4+4 / 8 / 1+7 | 4 `optimal`+4 `time_limit` / 8 `optimal` / 1 `optimal`+7 `time_limit_no_incumbent` | 0 | `v3_phase_E_scale.csv` |
| §7 60k 无解 MILP 墙钟 | 86.8–103.7 s | 86.791775–103.727140 s（7 行） | 0 | 同上 |
| §7 greedy/LP 最小值（1000/5000/60000） | 0.991991 / 0.998985 / 0.999897 | 同左 | 0 | 同上 |
| §7 local swap 与 greedy | 24/24 相同 | 24/24，价值差 0.0、人数差 0 | 0 | 同上 |
| §7 greedy 超支 | 21/24，最坏 1.90 | 21/24；最坏 1000@0.10，190/100=1.90 | 0 | 同上 |
| §7 MILP `optimal` 超支 | 13 个 `optimal` 中 11 个超支 | 13/11；若含 4 个 `time_limit` incumbent，则 **17 个有限 incumbent 中 14 个超支** | 报告少算 3 行（P2-6） | 同上 |
| §7 LP−incumbent 最小值 | −7.0e-11 | −7.003109e-11（5000@1.00） | 0 | 同上 |
| §8 0.20 六行（expected/buffered/worst） | 12 339.35/0.870/0.066756/14 640.79 等 | 六行逐项一致 | 0 | `v3_phase_E_conservative.csv` |
| §8 全档均值 | 0.8419 / 0.7240 / 0 / 0.150683 / 0.168388 / 0.010796 | 0.841875 / 0.723958 / 0 / 0.150683 / 0.168388 / 0.010796 | 0 | 同上 |
| §8 buffered 对原 expected 超支 | 0.875 | 0.875（21/24 格） | 0 | 同上 |
| §8 "3 策略均值" | 0.8419 / 0.150683 | 3 行均值确为 0.841875/0.150683；但两条贪心完全相同，按 2 条不同策略等权为 **0.8253125/0.147632** | 权重口径（P2-2） | 同上 |
| D03 正式 rep0 constant greedy 交叉核对 | 报告未给 | 8 档 `n_selected`/`predicted_cost`/`true_value_per_user`/`actual_spend` **最大绝对差 0.0** | — | `v3_phase_D03_formal_policy_grid.csv` |
| 行数/键唯一性 | §10 9 个产物 | 128/128、48/48、1 600/1 600、72/72、96/96、16/16、8/8；无重复键 | 0 | 各表 |

### 1.3 行数与键唯一性（对应评审问题 1 的 policy-grid 部分）

| 表 | 行数 | 唯一键 | 重复 |
|---|---:|---|---:|
| `small_pool` | 128 = 3 池 × 8 预算 × 5 求解器 + 8 浮点穷举 | `(pool_size, per_user_budget_cny, solver)` 128 | 0 |
| `bucket_convergence` | 48 = 8 预算 × (1 精确 + 5 宽度) | `(method, width_cny, per_user_budget_cny)` 48 | 0 |
| `random_long` | 1 600 = 8 预算 × 200 种子 | `(per_user_budget_cny, seed)` 1 600 | 0 |
| `random_summary` | 8 | `per_user_budget_cny` 8 | 0 |
| `decomposition` | 16 = 8 预算 × 2 策略 | `(per_user_budget_cny, actual_solver)` 16 | 0 |
| `conservative` | 72 = 3 口径 × 3 策略 × 8 预算 | `(mode, policy, per_user_budget_cny)` 72 | 0 |
| `scale` | 96 = 3 池 × 8 预算 × 4 求解器 | `(pool_size, per_user_budget_cny, solver)` 96 | 0 |
| D03 正式 policy grid（交叉核对用） | 72 000 = 200 × 5 × 9 × 8 | `(rep_id, model, policy, per_user_budget_cny)` 72 000 | 0 |

结论：E 自身没有 200 rep 的 policy grid；E 的表都是池级/预算级聚合，行数与键唯一性都正确。D03 的 72 000 行网格键唯一，E 的 rep0 交叉核对落在该网格上。

## 2. 问题清单

### P0（阻断）

**无 P0。** 没有发现：真值进入选人/聚合/播种；整表复制或跨 run root 混块；`outputs/tables` 与报告数字不一致；把 `time_limit_no_incumbent` 当 0；把 LP 上界当可行名单。报告中的错误属于"退化实例被当成互证、真值 oracle 口径写错、证据包未导出、解释越界"，不是数据污染。

> 但 P1-3 若按 AGENTS §12.1 作为硬门禁执行，应在正式通过前视为 gate-blocking；本评审把它记为 P1，而不是 P0，因为 9 张表已入库且可复算，缺的是 E 的 evidence package 与源码绑定。

### P1（必须在 E01/E02 转"已证实"前修复）

#### P1-1 恒定的 `τ̂` 使"五求解器互证"失去区分力

- **证据**：`out/e_evidence_formal/frame_rep0.csv` 的 `tau_hat` 在 60 000 行上 **unique=1**，取值 `0.29380318488356094`，sd=1.11e-16；`outputs/tables/v3_phase_E_small_pool.csv` 的 24 个 (池,预算) 格上 greedy/local_swap/milp 与 cent_exact_dp 的预测目标最大绝对差 0.0（brute_force 8/8 亦 0.0）；`scale` 的 local swap 24/24 与 greedy 同值同人数。
- **机理**：`τ̂` 全等时，价值/成本比排序退化为"按成本从低到高选"，背包变成最大基数/最小成本问题；任何正确实现都会给出同一组最优值。`local_swap` 只在 `value[unselected] > value[out_index]` 严格上升时接受（`src/causal_growth/policy/v3_policy.py:416-417`），全等值时不可能有改进。于是：
  - 24/24 相等不能检验 DP 的价值维度、MILP 的分支/排序、LP 的分数解；
  - local swap 24/24 无动作不是"贪心已贴 LP 上界"的经验证据，而是数学必然；
  - 求解误差 0–0.02 是"全等值 + 500 池"的必然结果，不是"这个池子上贪心恰好等于精确解"的一般经验。
- **报告已披露的部分**：§0 第 1 条说"这是一致性检查，不是贪心最优证据"，§3.2 说"小池太容易，不能区分算法"；但把原因归为"池太小"，没有指出真正原因是 `chosen=constant` 导致 `τ̂` 恒定。500 人池如果有变化的价值向量，是能区分算法的。
- **影响**：E01 的"DP/MILP/LP 名实相符、枚举互证"没有被证明；冻结反例 `test_frozen_counterexample_greedy_loses_a_third` 仍然是唯一硬证据。`GOAL.md:23` 的 E01 不能转"已证实"。
- **修复**：用非退化价值向量重跑 §3/§7：至少一个非 constant 模型 rep，或在同一 500 池上注入确定性的 `τ` 变化（保留 `user_id` 与成本向量），并加入已知答案实例（例如两个价值档、一个必须 1-for-2 交换的构造）。在脚本入口加断言：`nunique(tau_hat) > 1` 且 `sd(tau_hat) > 0`；否则拒绝输出"互证"表。若短期不能重跑，把 §3 标题改为"状态/契约检查"，删去"互证"与"名实相符已证"的措辞。

#### P1-2 真值 oracle 的成本口径与正文描述不符，低预算档学习误差被低估

- **证据**：报告 `:219-220` 写"真值最优使用**真值成本按下限截断**的 MILP 解（`truth_milp_cost_basis=truth_cost_floored_at_cost_floor_cny`，status=`optimal`）"。源码不是这样：
  - `src/causal_growth/policy/v3_policy_evidence.py:775-779` 的 `truth_exact = cent_exact_dp(to_signed_cents_half_up(tau_true), to_cents_half_up(cost_true), budget_cents)`，用的是 **raw `cost_true`**（0/10 实现成本，允许 0）；
  - `:781` 注释明确"MILP 只用于复核界与 gap"；
  - `:786` `truth_value = policy_value(truth_exact.mask, tau_true)`，真值最优值来自 raw cost 的 DP，不是 MILP；
  - `:813` `truth_solver=cent_exact_dp+MILP`，`:821` `truth_milp_cost_basis=truth_cost_floored_at_cost_floor_cny`；这两列描述的是复核，不是 `truth_value` 的基。
- **复算**：500 池有 20 个 `tau_true>0` 用户，31 个负值；20 个正 τ 用户的 `sum(cost_hat)=16.5342776646`，`sum(cost_true)=100.0`。
  - 0.04 档预算=20 元：按 `cost_hat`（策略预算口径）20 个正 τ 用户全部可行（16.53<20），真值最优应为 `1.01830` 元/人；按 raw `cost_true` 只能选到 12 个正 τ 用户（0.10 为 15 个），`0.76556`。报告的学习误差 `0.73162` 对应后者；同预算口径应为 `1.01830 − 0.03394 = 0.98436`，**低估 0.25274（34.5%）**。
  - 0.10 档：同口径真值最优仍 `1.01830`；`τ̂` 下精确解的真值为 `0.02546`，学习误差 `0.99284`；报告 `0.88758`，**低估 0.10526（11.9%）**。
  - 0.20 档起，raw 与期望口径都能覆盖全部 20 个正 τ 用户，两者同为 `1.01830`，报告 `0.91780` 不受影响。
- **影响**：E02 的"学习误差主导"方向仍成立，但低预算档的数值被系统性低估，且"学习误差 vs 求解误差"不是同一预算口径下的分解；报告对真值 oracle 的描述是错的。`truth_milp_status=optimal`、`gap=0` 不能救这一点，因为 MILP 求的是"把 0 成本抬到 cost_floor 后的收紧问题"，不是策略预算的期望成本问题。
- **修复**：把真值 oracle 改成与策略相同的预算口径（`cost_hat`；若 DGP 有真实期望成本，再用真实期望成本做第二列），raw `cost_true` 只作为"实现成本敏感性"另列。表增加 `truth_oracle_cost_basis`（`cost_hat` / `true_expected_cost` / `realized_cost`），并报告三种口径的 `truth_value` 与 `learning_error`。正文把 `truth_milp_*` 明确为"审计复核"，不再说"真值最优使用该 MILP 解"。

#### P1-3 证据链缺 E 记录/源码绑定；`out/` 帧与日志未导出

- **证据**：
  - `outputs/evidence/coverage.json` 只有 13 条记录，kinds 为 `raw`/`manifest`/`negative_control`/`aa_repetitions_merged`/`f01_freeze`/`f01_meta`，**没有任何 E 记录**；`outputs/evidence/` 下也没有 `e_*` 目录。
  - `outputs/tables/v3_phase_E_evidence_meta.json` 有 `frame_sha256`、`created_at`、`finished_at`、`timings_seconds`，但**没有** `git_commit`、`source_sha256`、`cfg_hash`、`protocol_source_hash`、`snapshot`；报告 `:378` 的评审清单第 1 项要求"三个哈希都写进 meta"，实际只有帧文件哈希。
  - `out/e_evidence_formal/frame_rep0.csv` 与 `run.log` 位于 `out/`，`.gitignore:66` 明确忽略 `out/`；报告 `:372` 说"本文件数字只依赖 `outputs/tables/`"，但校准 JSON 只有聚合值，没有逐用户 `predicted/observed`，离开 `out/` 帧无法独立重算校准、也无法验证 `tau_hat` 恒定。
  - `outputs/evidence/d03_formal/coverage.json:7-8` 有 `snapshot_combined_sha256=be0d48f4…`、`git_commit=130a3091…`；`:30-36` 的 `snapshot_vs_live.live_different` 列出 3 个 live 源码文件与 D03 快照不同：`v3_models.py`、`v3_policy.py`、`v3_policy_grid.py`。E 在 19:17–19:42 用的是 live 代码，不是 D03 快照。
  - `git show 8617b68` 在 E 运行结束（19:42）后的 19:55 提交里，仍修改了 `src/causal_growth/policy/v3_policy.py`（新增 `time_limit_no_incumbent` 状态、LP 上界 free items）与 `v3_policy_evidence.py`（tlni 的选人/成本/真值列 NaN 契约）。E 的 `scale`/`small_pool` 表恰恰依赖这个新状态与 NaN 契约；没有源码哈希，无法证明表由哪个版本产生。
  - 报告的正式路径是 `--from-d03`（在进程内重建 D03 5 模型链），不是读取 D03 的 9 列冻结 CSV；`--input` 模式虽存在，但正式运行没用。D03 交叉核对 8 档 greedy 全 0.0，说明 greedy 路径一致；MILP/LP 路径没有同等绑定。
- **影响**：E 的 9 张表可读可复算，但"由哪份源码、哪次运行产生"不可审计；`out/` 一旦清理，校准和 `tau_hat` 恒定证据消失；`coverage.json` 无法独立重建 E；AGENTS §12.1/§11 不满足。F01 的 `reference_frame.path` 也指向这个被忽略的 `out/e_evidence_formal/frame_rep0.csv`，问题会传导到 F01。
- **修复**：在 E meta 写入 `git_commit`、7 份源码文件逐文件 sha256、`cfg_hash`、`protocol_source_hash`、D03 `snapshot_combined_sha256`；把 `frame_rep0.csv`（或至少 `user_id/predicted/observed/tau_hat/cost_hat` 的校准抽取）、`run.log`、各表 sha256 复制到 `outputs/evidence/e_evidence_rep0/`，并在 `coverage.json` 增加 E 记录；正式运行从 D03 快照或 `--input` 冻结 9 列 CSV 启动，并断言 `frame_sha256` 与 D03 记录一致；若必须用 live 代码，显式记录 3 个 live diff 及理由。

#### P1-4 校准的个体指标被 0/10 伯努利噪声主导，"不排序/严重欠离散"读法不成立

- **证据**：报告 `:90-92` 用 `r=0.08525`、`slope=0.61657`、`pred sd=0.37907 / obs sd=2.74148` 得出"个体排序能力接近 0"；`:98-100` 进一步说"几乎没有个体排序能力""预测严重欠离散（约 1/7）"。校准观测是 `coupon_cost`（0/10 实现值，`scripts/24_e_evidence.py:155-161`），不是平滑的期望成本。
- **复算**：设 `Y∈{0,10}`，`p=0.0818532`。即使预测器完全校准（`pred=p`），`cov(p,Y)=Var(p)`，于是：
  - 由观测 `r`、`sd_pred`、`sd_obs` 反推 `cov = 0.085254×0.379069×2.741478 = 0.08857`，信号 sd `= sqrt(cov) = 0.2976`；
  - 二元实现下 `r` 的上限 `= 0.2976/2.74148 = 0.1086`；观测 `0.08525` 是上限的 **78.5%**，不是"接近 0"；
  - 预测 sd `0.37907` 比信号 sd `0.2976` **大 27%**，说明预测相对信号是**过离散**，不是报告说的"欠离散 1/7"；"1/7"是拿预测 sd 去比 0/10 实现的 sd，后者是伯努利方差，任何概率型预测都不可能匹配；
  - 常数预测器 `p` 的 MAE `= 2×10×p(1−p)=1.503`、RMSE `=10×sqrt(p(1−p))=2.7414`；报告 MAE `1.48614`、RMSE `2.73529` 只比常数好 **1.1%/0.2%**。个体绝对误差几乎全是不可约噪声。
- **影响**：均值校准（偏差 −0.12%、总和比 0.9988）仍然成立，E01 的"成本模型可用于预算会计"可以保留；但"个体排序能力接近 0/严重欠离散"是对二元实现的误读，不能作为成本模型个体质量的证据。报告的正确结论应是"实现成本个体不可预测，期望成本只用于预算会计，不用于个体排序"；而不是"模型排序能力差/欠离散"。
- **修复**：以常数 `p`/伯努利零模型为基准，报告 MAE/RMSE 的相对改进、Brier/log-loss（若 `p` 可导出）、按预测分位的校准曲线；若 DGP 有真实核销概率，直接把 `cost_hat` 对真实期望成本做校准，而不是对 0/10 实现做 Pearson/OLS。正文改写 `:90-100`，保留均值结论，删去"欠离散 1/7/接近 0"的推断。

#### P1-5 "1.00 档实际支出等于预算上限"与落库表矛盾

- **证据**：报告 `:187` 写"1.00 档所有人入选、实际支出等于预算上限"；`outputs/tables/v3_phase_E_random_summary.csv` 的 1.00 行为：`budget=60 000`、`mean_predicted_cost=49 190.152298`、`mean_actual_spend=50 570.00`、`overrun_probability=0.000`。
- **复算**：50 570 − 60 000 = **−9 430（−15.72%）**；预测成本也低于预算 10 809.85（−18.02%）。1.00 档预算根本不 binding，实际支出没有"等于上限"。
- **影响**：这是 E02"预期/实际/硬预算分开"段落里的事实错误；虽然"超支概率 0"的结论不受影响，但读者会误以为 1.00 档刚好花满 60 000。报告 `:195-196` 的"1.00 档两者相等"仍正确（同一全体用户），但要用 50 570 的实际支出解释，不能用 60 000 预算。
- **修复**：改为"1.00 档所有人入选；预测成本 49 190、实际支出 50 570，均低于 60 000，预算不 binding，超支概率 0"；并在 §5 表加 `mean_actual_spend` 列，避免只给概率不给支出。

#### P1-6 只用 `chosen=constant` 一个模型，"学习误差主导"不能外推

- **证据**：报告 `:35-37` 把"学习误差主导、求解误差≈0"写成 E02 的结论；`:217-218` 才补"本 rep `chosen=constant`"；`:193-194` 也只说"该结论只适用于本 rep 的 constant 模型"。D03 正式 §4 的 0.20 档策略值：constant greedy `0.0767`，causal forest `0.2934`，constant 是最弱模型。E 的误差分解只跑 constant，没有第二个模型。
- **影响**：在 constant 模型下，`τ̂` 恒定、学习误差必然大、求解误差必然≈0；这不能说明"估计误差是管道的瓶颈"，只能说明"常数基线很差"。把它写成 E02 的一般结论，会让读者误以为换成 CF/t-learner 后学习误差仍主导；D03 的数据恰恰显示 constant 与 CF 差近 4 倍。
- **修复**：至少对一个非 constant 模型（CF 或 t-learner）重复同一 500 池/8 预算的分解，报告 2×8 表；若短期只能跑 constant，把 §0 第 5 条改为"constant 基线的学习误差主导"，并在标题/摘要中明示不可外推。加一行 paired 模型对照（同 rep、同池、同预算），否则不满足 AGENTS §12.6 的"配对比较"精神。

### P2（应在下一轮文档/脚本中修正）

#### P2-1 桶宽 gap 的分母说明错误

- **证据**：报告 `:157` 说"gap 的分母是分币 DP 的精确目标值"；`v3_phase_E_bucket_convergence.csv` 的 `gap_per_user_cny` 实际是 `gap_to_exact_cny / 500`（`gap_to_exact/gap_per_user=500` 对所有非零行成立；代码 `v3_policy_evidence.py:603-604`）。例：0.50 宽 @0.04，`gap_to_exact=5.582261`，`gap_per_user=0.011165`；精确目标 `18.215797`，相对 gap 是 **30.65%**；`0.011165` 只是绝对元/人。
- **影响**：读者会把"元/人"误读成相对精确目标的百分比；阈值评审时口径不清。
- **修复**：把 `:157` 改为"`gap_per_user = gap_to_exact / 池人数 500`；相对 gap 另算 `gap_to_exact / 精确目标`"，并在表里加 `relative_gap_to_exact` 列。

#### P2-2 §8.2 "3 策略均值"重复计入完全相同的 local swap

- **证据**：报告 `:309-313` 的"8 档 × 3 策略均值"；`conservative` 表里 `greedy_incremental_profit_per_cost` 与 `greedy_local_swap` 在 24/24 格完全相同（P1-1 的必然结果）。3 行等权均值 = 0.841875/0.150683；按 2 条不同策略等权 = **0.8253125/0.147632**；buffered 为 **0.7109375/0.165547**；worst 为 **0.011111**（报告 0.010796）。
- **影响**：均值被两条相同贪心拉高，读者会以为是三个独立策略的平均。
- **修复**：标题改为"3 条策略行（其中 2 条相同）"，或按不同策略等权；至少加脚注给出 2 条不同策略的均值。

#### P2-3 `mean_se` 区间漏掉 0.80 与 1.00

- **证据**：报告 `:182` 写"0.000441–0.000852"；`random_summary` 的 `mean_se` 全列为 0.000441、0.000541、0.000754、0.000818、0.000852、0.000835、**0.000270**、**0.000000**。
- **影响**：区间不是全 8 档的范围；0.80 的 SE 比 0.60 小，1.00 为 0，读者会误以为 0.80 仍有 0.0008 量级的均值误差。
- **修复**：写"0.04–0.60 为 0.000441–0.000852；0.80 为 0.000270；1.00 为 0（全员入选）"。

#### P2-4 `frame_sha256` 在 E 与 F01 中语义不同

- **证据**：E meta 的 `frame_sha256=c8fd698e…` 是 `frame_rep0.csv` 的**文件字节**哈希（`sha256sum` 一致）；F01 `outputs/evidence/f01_ope/meta.json` 的 `reference_frame.frame_sha256=372a1bcc…` 是 `dataframe_sha256(reference)` 的**数据帧**哈希（`scripts/31_f01_ope.py:125-126`；`src/causal_growth/data/v3_storage.py:29-35` 按列/dtype/值序列化）；决策日志还把它叫"7 列哈希"。同一个字段名，三种对象。
- **影响**：跨产物校验会拿文件哈希去比 dataframe 哈希，必然不相等；评审无法用同一个字段追帧。
- **修复**：拆成 `frame_file_sha256` 与 `frame_dataframe_sha256`（注明列序/dtype/是否含真值列），F01/E 双方都写两个；决策日志改称"7 列 dataframe 哈希"。

#### P2-5 MILP 的 "60 s 时限" 与 86.8–103.7 s 墙钟需要一句解释

- **证据**：报告 `:45` 与 `:280` 已如实给出 7 个 `time_limit_no_incumbent` 的墙钟 86.8–103.7 s；`scale` 表 1000 的 4 个 `time_limit` 为 60.02–60.09 s，5000 全 optimal 为 0.017–21.70 s。报告没有解释为什么 60 s 限制会跑出 103.7 s（可能是 HiGHS 预处理/模型构建/两次求解/计时口径）。
- **影响**：读者会怀疑 `seconds` 不是求解时间，或时限配置没生效；这正是评审问题 1 要求核对的 "no-incumbent wall clock"。
- **修复**：在 §7 说明 `seconds` 是 `milp_select` 的墙钟，60 s 是 HiGHS 内部时限，预处理/模型装配可能超出；若 `seconds` 还含 LP 或第二次求解，拆成 `milp_seconds` 与 `total_seconds`。记录 HiGHS 版本。

#### P2-6 "13 个 optimal 11 个超支"漏掉 4 个 time-limit incumbent

- **证据**：报告 `:271`；`scale` 表 24 个 MILP 行中 17 个 incumbent 有限（13 optimal + 4 time_limit），实际超支 14 个：1000@0.10/0.20/0.40 的 3 个 time_limit incumbent 也超支，只有 1000@0.04 的 40=40 不超。13 个 optimal 里 11 个超支（5000@1.00 与 60000@1.00 不超）。
- **影响**："MILP 解也超支"的方向不变，但 11/13（84.6%）与 14/17（82.4%）不是同一个分母；报告少算了 3 行。
- **修复**：写"17 个有限 incumbent 中 14 个超支；其中 13 个 optimal 中 11 个超支"。

#### P2-7 负的真值没有解释

- **证据**：`scale` 表有 9 行 `true_value_per_user<0`：1000@0.04 三求解器 −0.02730、1000@0.20 −0.00693、1000@0.40 −0.03496；`small_pool` 的 500@0.20 `time_limit` 行也 `true_value_per_user=−0.1198`。`tau_true` 本身有负值（池 500 中 31 个负 τ），所以选中集合的真值可以为负。
- **影响**：读者可能把负值当成 NaN 契约或求解器错误；报告 §7 只讲超支，没有讲负价值。
- **修复**：在 §7/§9 加一句"`tau_true` 可为负，选中负 τ 用户会使真值审计值为负；这是 DGP 支持，不是求解器 bug"，并在表里保留负值/标注。

#### P2-8 缺少按实际支出归一化的每元价值

- **证据**：报告 `:31-34`、`:170-179` 比较 greedy 与 random 的 `true_value_per_user`，但没有除以实际支出；D03 §5.2 已明确"符号不能脱离支出读"。按 `random_summary`/`scale` 复算：0.04 档 greedy 每元 `0.008649×60 000/2 400=0.216`，random `0.013813×60 000/2 469.30=0.336`；0.20 档 greedy `0.428`，random `0.330`；1.00 档两者是同一全体名单，必须用同一个实际支出 50 570 作分母（均为 0.331），不能用 60 000 预算给 greedy 单独做分母。
- **影响**：0.04 档"greedy 更差"不仅是 constant 模型的排序问题，也是每元价值更差；0.20+ 档 greedy 在总价值和每元价值上都更好。报告只给总价值，读者无法区分"多花多得更差/更好"。
- **修复**：在 §5 与 §8 加 `true_value_per_actual_spend` 与边际每元价值；1.00 档用同一实际支出分母；明确"超支概率"与"均值超支率"是两件事。

#### P2-9 没有按 AGENTS §12.5 汇总"最差相对差异 + 分母"

- **证据**：报告散落着相对数：校准相对偏差 −0.1158%（分母平均预测 0.819481）、MILP gap 0.4341%（分母 bound 58.130456）、greedy expected 超支 28.4%（15 410/12 000）、greedy/LP 最小 0.991991（短差 0.8%）；桶宽只给绝对 `gap_per_user`，没有相对精确目标的 30.65%（0.50@0.04）与 12.9%（1.00@0.04）。没有一张"最差格 + 分母"的表。
- **影响**：评审无法一眼判断哪个口径的最差相对误差最大；桶宽阈值讨论缺相对尺度。
- **修复**：加一张"指标 / 最差格 / 相对差异 / 分母"表；桶宽加 `relative_gap_to_exact`；明确 `overrun_probability` 是概率不是均值超支率。

## 3. 被证实 / 被否定的报告陈述

### 3.1 被证实（逐项复算一致）

1. §2 校准 13 个数全部一致：n=19 987、预测均值 0.819481、观测均值 0.818532、偏差 −0.000949、相对 −0.1158%、总和比 0.998842、MAE 1.48614、RMSE 2.73529、r 0.08525、斜率 0.61657、截距 0.31326、预测/观测 sd 0.37907/2.74148。
2. §3 greedy/local_swap/milp 与 cent_exact_dp 在 24/24 格最大绝对差 0.0；浮点穷举 8/8 与分币 DP 相等；MILP 23 optimal + 1 time_limit（gap 0.4341%，`may_claim_optimal=False`）；LP−exact 最小 −1.136868e-12（2 格为负）；104 行可行、24 行 LP NaN、无 False。
3. §4 桶宽 48 行：五档均值/最大 gap/丢弃数全部一致；0.01 档 gap 0；0.50/1.00 分别丢弃 72/124 个物品；40 行 bucket 结果在原成本复核后均可行。
4. §5 随机基线 1 600 行 = 8 档 × 200 种子，8 档均值/sd/分位数/超支概率全部一致；1.00 档 sd=0；`mean_se` 单值一致（只是区间写法漏项）。
5. §6 分解 16 行：学习误差 0.58674–0.91780（raw 口径）、求解误差 0–0.02、恒等式残差最大 3.469e-17；`truth_milp_status=optimal`、gap=0、16/16 可行；真值最优 0.76556/0.91304/1.01830。
6. §7 规模 96 行：1000 4 optimal+4 time_limit、5000 8 optimal、60000 1 optimal+7 `time_limit_no_incumbent`；60k 无解墙钟 86.79–103.73 s；greedy/LP 最小 0.991991/0.998985/0.999897；local swap 24/24 同值同人数；greedy 21/24 超支、最坏 1.90；LP−incumbent 最小 −7.003e-11；7 个 tlni 行的选人/成本/真值列全 NaN，bound 仍有限。
7. §8 保守表 72 行：0.20 六行逐项一致；全档均值 0.841875/0.723958/0；真实价值 0.150683/0.168388/0.010796；buffered 对原 expected 超支 0.875；worst_case_face 的 0 超支与 1/14、1/23 的量级成立。
8. 真值隔离：`frame_rep0.csv` 恰好 9 列、60 000 行、`user_id` 唯一、数值有限、`cost_hat>0`、`cost_true≥0`；`v3_models.py:2066-2067` 先冻结 7 列选人字段再合并真值；`v3_policy_evidence.py:765-794` 的贪心/交换/DP 用 `tau_hat/cost_hat`，真值只进 `policy_value`/审计列；随机播种用 `child_rng`，未用真值。
9. 行数与键唯一性：E 的 7 张表 128/48/1 600/8/16/72/96 行，键均唯一；D03 正式 72 000 行网格键唯一。
10. D03 正式 rep0 交叉核对：E 的 expected constant greedy 与 `v3_phase_D03_formal_policy_grid.csv` 的 rep0/constant/greedy 在 8 档的 `n_selected`、`predicted_cost`、`true_value_per_user`、`actual_spend` **最大绝对差 0.0**。这是 E 与 D03 之间最强的正向证据链，报告应显式写出。

### 3.2 被否定 / 必须改写的陈述

1. **`:187` "1.00 档实际支出等于预算上限"**：否定。实际 50 570，预算 60 000，低 15.72%；预测 49 190，也低于预算。应改为"预算不 binding"。
2. **`:219-220` "真值最优使用真值成本按下限截断的 MILP 解"**：否定。`truth_value` 来自 raw `cost_true` 的分币 DP（`v3_policy_evidence.py:775-786`）；MILP 只是审计复核，且其成本被 `max(cost_true, cost_floor)` 收紧。应改为"真值精确解用 raw cost 的 DP；MILP 只复核界/gap"。
3. **`:157` "gap 的分母是分币 DP 的精确目标值"**：否定。`gap_per_user` 分母是池人数 500；相对精确目标的 gap 另算（0.50@0.04 为 30.65%）。
4. **`:90-100` "个体排序能力接近 0 / 预测严重欠离散 1/7"**：需改写。二元 0/10 实现下 r 的上限约 0.1086，观测 0.08525 是上限的 78.5%；由 cov 反推信号 sd 0.2976，预测 sd 0.3791 是**过离散**；MAE/RMSE 仅比常数预测器好 1.1%/0.2%。均值校准成立，个体指标不能这样读。
5. **`:309` "8 档 × 3 策略均值"**：需限定。两条贪心完全相同，3 行均值等价于 2:1 加权；按 2 条不同策略等权为 0.8253125/0.147632（expected）、0.7109375/0.165547（buffered）、0.011111（worst）。
6. **`:182` "mean_se 0.000441–0.000852"**：不完整。0.80 为 0.000270，1.00 为 0。
7. **`:271` "13 个 optimal 11 个超支"**：不完整。17 个有限 incumbent 中 14 个超支；13/11 只是 optimal 子集。
8. **`:378` 评审清单"三个哈希都写进 meta"**：当前未满足。meta 只有 `frame_sha256`；`cfg_hash` 与 `protocol_source_hash` 只在正文，没有进 JSON。
9. **`:372` "本文件数字只依赖 outputs/tables"**：需限定。读数可以只靠表，但校准的逐用户重算、`tau_hat` 恒定检查依赖被忽略的 `out/` 帧；校准 JSON 只有聚合值。应改为"报告展示值可由表读出；独立重算需要 evidence 包中的帧/抽取"。

## 4. 对六个评审问题的直接回答

### (1) 关键数字能否从落库表复算？报告/复算/差异

能。§1.2 的 30 余行全部给出报告值、复算值、差异；除 P1-2（同预算口径补算）、P1-5（1.00 支出）、P2-1（桶宽分母）、P2-2（3 策略均值）、P2-3（mean_se 区间）、P2-6（13/11 vs 17/14）外，差异均为 0。需要区分两类"能复算"：

- **表内可复算**：随机 8 档、保守 72 行、分解 16 行、规模 96 行、桶宽 48 行、小池 128 行，均可从 CSV 逐行重算均值/差值/状态计数；
- **需帧才能独立重算**：校准 13 个数只有 JSON 聚合，没有逐用户 `predicted/observed`；`tau_hat` 恒定只能从 `out/e_evidence_formal/frame_rep0.csv` 验证。这正是 P1-3 的证据包缺口。

policy-grid 行数/键唯一性：E 自身没有 200 rep 网格；D03 正式网格 72 000 = 200×5×9×8，键唯一；E 的 rep0 交叉核对 8 档与 D03 完全一致。E 的池级表 128/48/1 600/8/16/72/96 行，键均唯一（§1.3）。

MILP no-incumbent 墙钟：7 行 86.791775–103.727140 s（报告 86.8–103.7）；1000 的 4 个 time_limit 为 60.02–60.09 s。数字对；60 s 限制与墙钟的差异需要一句解释（P2-5）。

greedy 超支倍数/最坏格：21/24 行超支；最坏 1000@0.10，190/100=1.90（报告一致）；0.20 档 15 410/12 000=1.284（+28.4%）。

greedy/LP 比：1000/5000/60000 最小 0.991991/0.998985/0.999897，与报告一致；local swap 与 greedy 24/24 同值同人数。

calibration bias/ratio：偏差 −0.000948820、相对 −0.115783%、总和比 0.998842169，与报告一致。

### (2) 证据链与 coverage.json 能否独立重建？是否有整表复制/混块/漏 merge？

- **不能完整重建**：`outputs/evidence/coverage.json` 13 条记录无 E；`outputs/evidence/` 无 E 目录；E meta 无 commit/source/cfg/protocol/snapshot 绑定；帧与 run.log 在 `out/`（`.gitignore:66`）。因此只能从 9 张聚合表重建"报告展示值"，不能从 evidence 包重建"原始运行"。
- **未发现整表复制**：E 的表是从 `frame_rep0.csv` 计算出的聚合/池级表，不是把 D03 的 60k/72k 表整表复制；`random_long` 1 600 行是基线结果，不是原始用户表。
- **未发现块混用**：所有 E 表使用同一 `rep=0` 帧，池/种子/预算在 meta 中有记录；没有把不同 rep 或不同 run root 的行拼进同一表。
- **未发现漏 merge 的跨 run root**：E 只做一个 rep，不存在 200 rep 合并；D03 的 72k 网格是独立产物，仅用于交叉核对。反过来说，E 也没有做 200 rep 的 E01/E02 分布，这是范围缺口（§5），不是 merge 错误。
- **AGENTS §12.2 结论**：无整表复制/混块；但 §12.1 的 evidence export/coverage 不满足，§12.3 的哈希绑定不满足。

### (3) 真值隔离：E 是否只消费 D03 的 9 列 per-user CSV？真值是否只在冻结后用于评估？

- **列契约**：`frame_rep0.csv` 恰好 9 列（`user_id,is_new,cart_value,purchase_propensity,predicted_profit,tau_hat,cost_hat,tau_true,cost_true`），60 000 行，`user_id` 唯一，数值有限，`cost_hat>0`，`cost_true≥0`；`v3_policy_grid.py:56-73` 的 `require_grid_frame` 对 9 列/唯一键/有限值做校验。
- **冻结顺序**：`src/causal_growth/estimate/v3_models.py:2066-2067` 明确"选人列到此已冻结；真值只在下面这一次合并里出现"；`_audit_truth_for_test` 的 docstring 要求调用方在选人列冻结后合并。
- **选择/聚合/播种**：`v3_policy_evidence.py:765-794` 的 greedy/local swap/DP 只读 `tau_hat/cost_hat`；`_mask_metrics` 在 mask 冻结后才读 `tau_true/cost_true`；`_pool_frame` 只用 `child_rng` 抽行，不看真值；`random_baseline` 的 200 个种子也不含真值。未发现真值进入选人、聚合权重或播种。
- **保留**：正式路径是 `--from-d03` 在进程内重建 D03 链，不是读取 D03 的冻结 9 列 CSV；`--input` 模式存在但未用。因此"只消费 9 列 CSV"在**列契约**上成立，在**来源**上是"重建"，不是"读取冻结件"。这削弱了可审计性（P1-3），但不构成真值泄漏。

### (4) 可比性：是否同 rep/用户/预算配对？是否用"只选中的模型"或"选模频率"替代？

- **同 rep/用户/预算**：E 所有表基于同一个 rep 0 的 60 000 test 帧；greedy 与 random 在同一帧、同一 8 档 `per_user_budget` 上比较；保守表的 expected/buffered/worst 也是同一帧、同一预算数字（worst 另加人数上限）。这点成立。
- **未用选模频率替代**：E 没有把 D03 的 105/71/12/7/5 选模频率当作策略值；它确实重建了 rep0 的 5 模型链并取 chosen=constant，`chosen_model` 在 meta/报告中明示。
- **"只选中的模型"问题**：E 只跑 chosen=constant，没有跨模型对照；这不是"用选模频率替代"，但确实是"chosen-only"（P1-6）。D03 §4 显示 constant 是最弱模型，因此 E02 的学习误差结论不能外推。
- **支出归一化**：没有给每元价值；0.04 档 greedy 0.216 vs random 0.336，0.20 档 0.428 vs 0.330；1.00 档同一名单必须同分母（P2-8）。
- **结论**：配对结构成立；模型维度和支出维度的可比性不足，需补。

### (5) 解释边界：是否把合成/单场景/试点外推？失败/无解/超支是否诚实？最差相对差异是否有分母？

- **未外推场景**：报告反复说"本 rep/constant/DGP 真值/observed_value 延后"，§9 列了 8 条限制；没有把 L1_main 的结果写成真实业务结论。这一点做得好。
- **失败/无解/超支**：7 个 `time_limit_no_incumbent` 的选人/成本/真值列全 NaN、不当 0（bound 仍有限）；MILP 状态/gap/`may_claim_optimal` 透明；greedy 21/24 超支、1.90 最坏格；worst_case_face 的 0 超支明确说"人数上限换来的，不是成本模型变准"。这些是诚实报告。
- **越界**：校准的"个体不排序/严重欠离散"（P1-4）、"学习误差主导"的 unqualified 写法（P1-6）、"1.00 实际支出等于预算"（P1-5）是解释/事实越界。
- **最差相对差异**：报告有零散相对数（校准 −0.1158%、gap 0.4341%、expected 超支 28.4%、greedy/LP 短差 0.8%），但没有按 §12.5 汇总"最差格 + 分母"；桶宽只给绝对 per-user gap，最差相对 30.65%（0.50@0.04）未写（P2-9）。
- **结论**：方向性边界大体诚实，数值口径和"个体/一般"措辞需要收紧。

### (6) 判定

**PASS WITH CONDITIONS；0 P0、6 P1、9 P2。** E01/E02 仍为"未证实"；P1-1~P1-6 修复并重跑/重写后，才可提交正式通过评审。若项目把 AGENTS §12.1 视为硬门禁，P1-3 应在任何"通过"之前完成，不能以"表已入库"替代 evidence package。

## 5. 未覆盖范围

1. **单 rep**：只做 D03 正式 rep 0（chosen=constant）；没有 200 rep 的 E01/E02 分布、跨 rep 方差、选模频率对误差分解的影响。E 的"学习误差主导"不能当作 200 rep 的结论。
2. **单模型**：只跑 chosen=constant；没有 CF/t-learner 的误差分解，也没有同 rep/同池/同预算的配对模型比较（P1-6）。
3. **单场景**：只 `L1_main`、synthetic known DGP；没有 observational/time_mode/其他场景；不能外推到真实数据或别的 DGP。
4. **校准范围**：只在 validation 处理组 n=19 987 上做均值/个体诊断；没有 test 集校准，没有真实期望成本标签，没有按分位的校准曲线/Brier/log-loss（P1-4）。
5. **求解器范围**：小池 20/100/500；规模 1 000/5 000/60 000；60k 没有精确 DP 参照，MILP 7 档无 incumbent，启发式只有 LP 上界，没有 60k 最优性证明；LP 每 rep 仍缺（`docs/v3_phase_E_coverage.md:89`）。
6. **报告口径**：没有 200 rep policy grid；E 只有池级/预算级表；没有 worst-relative-difference 汇总；没有 per-actual-spend 每元价值/边际价值（P2-8/P2-9）。
7. **证据包**：没有 `outputs/evidence/e_evidence_rep0/`；没有 E 的 coverage 记录；没有源码/commit/快照绑定；帧和 run.log 只在 `out/`（P1-3）。
8. **观测价值**：所有价值列是 `dgp_truth_tau`；`observed_value_status=deferred_to_F_ope`，E 不做 OPE/观测价值；不能把真值审计值当线上可实现收益。
9. **硬预算**：`worst_case_face` 是 10 元券面额人数上限，不是"期望成本硬上限"；`hard_cap_claim_allowed=false`。E 没有证明在期望成本口径下存在硬上限策略。
10. **测试/门禁**：E 运行未跑 pytest；`test_frozen_counterexample_greedy_loses_a_third` 是单测反例，不在 E 产物内；没有 `tau_hat` 非退化断言（P1-1）。

## 6. 评审留痕

| 操作 | 命令/路径 | 用途 |
|---|---|---|
| 读报告 | `Read docs/v3_phase_E_evidence.md`（385 行）、`docs/v3_phase_E_coverage.md`、`docs/v3_phase_E_interface.md` | 口径、结论、限制 |
| 读元数据 | `outputs/tables/v3_phase_E_evidence_meta.json`、`outputs/evidence/coverage.json`、`outputs/evidence/d03_formal/coverage.json`、`outputs/evidence/f01_ope/meta.json` | 哈希/coverage/来源 |
| 读帧 | `out/e_evidence_formal/frame_rep0.csv`（60 000×9） | `tau_hat` 恒定、成本分布、9 列契约 |
| 读日志 | `out/e_evidence_formal/run.log` | 19:17:51–19:42:28（总约 1477 s / 24.6 min；meta 阶段合计 1217.4 s）、8 outputs、无 warning |
| 复算 Stats | `python - <<'PY'`：读 calibration/random/conservative/decomposition/scale/small_pool/bucket，算均值/差值/分位/状态计数 | §1 复算表 |
| 复算池 | `load_v3_protocol()` + `_pool_frame(...,500,...)` | 20 个正 τ、31 个负 τ、`sum(cost_hat)=16.5343`、`sum(cost_true)=100` |
| 交叉核对 | `v3_phase_D03_formal_policy_grid.csv` rep0/constant/greedy vs E expected greedy | 8 档最大绝对差 0.0 |
| 行数/键 | `drop_duplicates()`/`duplicated()` on 7 张 E 表 + D03 grid | 128/48/1600/72/96/16/8、72 000 均唯一 |
| 源码核对 | `v3_policy_evidence.py:291-345, 712-831`；`v3_policy.py:388-429`；`v3_models.py:1990-2081`；`v3_policy_grid.py:56-73` | 校准、真值 DP/MILP、local swap、冻结顺序、9 列校验 |
| Git 核对 | `git log -1`、`git log --oneline -- docs/v3_phase_E_* outputs/tables/v3_phase_E_*`、`git show 8617b68 -- src/...`、`git status --short` | 8617b68 落库、19:55 源码改动、HEAD 906767d8 |
| 哈希核对 | `sha256sum out/e_evidence_formal/frame_rep0.csv` = `c8fd698e…`；`dataframe_sha256` 语义见 `v3_storage.py:29-35` | E/F01 哈希口径 |
| 约束 | 未写 `out/`/`outputs/`；未改源码/配置/数据/表格；未 commit/push；未跑正式 R；未跑 pytest | — |

**评审结论复述**：数字可信、真值隔离成立、失败/无解/超支报告诚实；但 E01 的"互证"在恒定 `τ̂` 下退化，E02 的真值 oracle 口径写错且低预算学习误差被低估，证据包/源码绑定缺失，校准解释与 1.00 支出一句事实错误。**PASS WITH CONDITIONS；0 P0、6 P1、9 P2；E01/E02 仍为"未证实"。**

---

未改源码/配置/数据/表格，未 commit/push，未跑正式 R
