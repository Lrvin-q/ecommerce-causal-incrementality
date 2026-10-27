# Phase E 配置覆盖矩阵

> 合成数据 / 已知 DGP。维护时间：**2026-10-28 05:48（北京时间）**（19:50 首版；05:48 按 E 独立复审修正 4 处过期陈述：小池表的家族归属、19:17 运行已被 01:12 / 01:35 两家族取代、"local swap 24/24 完全相同"只在 A 成立、评审状态）。
> 目的：把 `configs/v3/policy.yaml` 的**每一个键**与实现逐条对上，暴露"配了但没实现"
> 或"实现了但没测"的缺口。这是 E 阶段的自查表，不是成绩单——缺口必须留在表上。

## 状态图例

| 标记 | 含义 |
|---|---|
| ✅ | 已实现，且有 pytest 覆盖 |
| ⏳ | 有实现组件，但需要真实观测数据才能接线（属 E 正文/编排层） |
| 🚫 | 显式拒绝：配置若偏离默认值会抛错，不静默忽略 |
| ❌ | 尚未实现，附理由与归属阶段 |

## 1. 顶层口径

| 键 | 语义 | 实现 | 状态 |
|---|---|---|---|
| `action_space` | `{0,1}` 二元 | `Selection.mask` 布尔数组 | ✅ |
| `face_value_cny` | 10.0 | 成本模型与预算计划均从此读 | ✅ |
| `value_target` | 相对不发券的净增量 | `policy_value` 分母为全部目标用户 | ✅ |

## 2. `budget`

| 键 | 实现 | 状态 |
|---|---|---|
| `basis: expected_redemption_cost` | `predict_expected_cost` 输出期望核销成本 | ✅ |
| `base_per_user_cny` | `build_budget_plan` 的 `expected = base × n` | ✅ |
| `per_user_grid_cny`（8 点） | 预算扫描循环 | ✅ 代表 rep 全 8 档；小池/桶宽/随机/三口径/规模五张表 |
| `total_rule` | `expected = base × n_target` | ✅ |
| `freeze_using_observed_data_only` | 文档约束；`CostModel.fitted_on` 标 `training_only` | ⏳ 需运行期断言 |
| `actual_spend_overrun_reported` | `audit_budget.within_expected` | ✅ |
| `hard_cap_claim_allowed: false` | `audit_budget` 返回 `hard_cap_claim_allowed: False`，编码进返回值 | ✅ |
| `conservative_comparison.modes.buffered_expected` | `BudgetPlan.buffered = expected × multiplier` | ✅ |
| `conservative_comparison.modes.worst_case_face` | `BudgetPlan.worst_case` + `max_recipients_face` | ✅ |
| `conservative_comparison.policies` | 三策略组合 | ✅ `v3_phase_E_conservative.csv` 72 行 |
| `random_seeds_per_dataset_budget_mode: 200` | 种子循环 | ✅ `v3_phase_E_random_long.csv` 1 600 行 |
| `report`（6 项） | 已有 `selected_count` / `predicted_cost` / `observed_cost_total` / `within_expected` / `within_buffered` / `face_bound_respected` | ⏳ 已补 `actual_spend_overrun_probability`（多次随机）；`observed_value` 留 F |

## 3. `cost_model`

| 键 | 实现 | 状态 |
|---|---|---|
| `target` | `CostModel.target` 构造时校验字符串 | ✅ |
| `primary: two_stage_purchase_and_conditional_redemption_amount` | `fit_cost_model` 两阶段 | ✅ |
| `auxiliary: direct_cost_regression` | `CostModel.auxiliary_direct` | ✅ |
| `trained_only_on: training_observed_logs` | `fitted_on="training_only"` + 只用 `treatment=1` | ✅ |
| `calibration_only_on: validation_observed_logs` | `calibrate_cost_predictions`（只吃 validation 处理组） | ✅ `v3_phase_E_calibration.json`（n=19 987） |
| `prediction_bias_multiplier: 1.0` | `_require_supported_cost_options` | 🚫 非 1.0 即抛 `NotImplementedError` |
| `multiplicative_noise_log_sd: 0.0` | 同上 | 🚫 非 0.0 即抛 |
| `noise_expectation_normalized_to_one` | 噪声为 0 时无意义 | 🚫 与上一条绑定 |
| `cost_floor_cny` | `np.maximum(expected, floor)` | ✅ |

## 4. `candidates`（9 个策略）

| 策略 | 实现组件 | 状态 |
|---|---|---|
| `no_coupon` | 全 False 的 `Selection` | ⏳ 组装 |
| `all_coupon_unconstrained_reference` | 全 True 的 `Selection` | ⏳ 组装 |
| `random_same_budget` | `random_under_budget`（child_rng 可复现） | ✅ 组件 |
| `business_rule_new_user_then_cart` | `rank_and_select` + 多级排序 | ⏳ 组装（需 `is_new`/`cart_value`） |
| `purchase_propensity_rank` | `rank_and_select` | ✅ 组件 |
| `predicted_profit_rank` | `rank_and_select` | ✅ 组件 |
| `incremental_profit_rank` | `rank_and_select` | ✅ 组件 |
| `greedy_incremental_profit_per_cost` | `greedy_by_ratio` | ✅ |
| `greedy_local_swap` | `local_swap` | ✅ |

## 5. `optimization`

| 键 | 实现 | 状态 |
|---|---|---|
| `no_negative_predicted_increment_for_targeting` | `rank_and_select` / `greedy_by_ratio` 只对正分排序 | ✅ |
| `deterministic_tie_break: user_id_ascending` | `np.lexsort((user_id, -score))` | ✅ |
| `objective` / `cost` | `Selection.predicted_value` / `predicted_cost` | ✅ |
| `small_exact.algorithms`（5 个） | 全部实现 | ✅ |
| `small_exact.cost_integerization: decimal_half_up_to_cent` | `cent_exact_dp` 接收整数分 | ✅ |
| `small_exact.exactness_claim_target` | 文档与 docstring 明确"仅整数化问题" | ✅ |
| `small_exact.pool_sizes` | 20 / 100 / 500 | ✅ **有效证据是 B 家族** `v3_phase_E_small_pool_cf.csv` 128 行（01:40）。A 家族**无有效小池表**：`v3_phase_E_small_pool.csv`（128 行、10-27 **19:23**）是加退化守卫**之前**那次运行的产物，已被 A 的证据包显式排除并标 `stale_pre_guard`——τ̂ 全等时 5 个求解器必然同解，留着会被当成"互证"（初审 P1-1） |
| `bucket_convergence`（5 档宽度） | `bucket_convergence_table`（近似桶 DP + 原成本复核回退） | ✅ `v3_phase_E_bucket_convergence.csv` 48 行；**阈值仍由评审看曲线后定** |
| `large.algorithms` | greedy / local_swap / MILP / LP 全有 | ✅ |
| `large.milp_time_limit_seconds: 60` | `milp_select` 参数 | ✅ |
| `large.milp_relative_gap_tolerance: 0.001` | 同上 | ✅ |
| `large.require_incumbent_bound_gap_and_status` | `MilpResult` 四个字段 | ✅ |
| `large.pool_sizes` | 1000 / 5000 / full_test | ✅ `v3_phase_E_scale.csv` 96 行 |
| `local_swap.max_passes: 10` | 参数透传 | ✅ |
| `local_swap.exchange_candidate_limit: 500` | 未选者按价值降序截断 | ✅ |
| `exact_counterexample` | `test_frozen_counterexample_greedy_loses_a_third` | ✅ |
| `comparison_frequency` / `every_full_rep_required` | 代表 rep 全预算已实现；greedy/local_swap 每 rep 已有，LP 仅代表 rep | ⏳ **LP 每 rep 仍缺，G 阶段补齐** |

## 6. `oracle_audit`

| 键 | 实现 | 状态 |
|---|---|---|
| `heuristic_optimality_claim_forbidden` | `MilpResult.may_claim_optimal` 只在 gap=0 时为真 | ✅ |
| `predicted_objective_gap_separate_from_truth_regret` | `truth_regret` 与 `predicted_value` 两个独立量 | ✅ |
| `stage: after_all_observed_outputs_frozen` | — | ❌ 需 F 阶段的冻结 manifest 才谈得上强制 |
| `candidates`（4 个真值策略） | — | ❌ 属 F 阶段（真值解封后） |

## 7. `random_baseline`

| 键 | 实现 | 状态 |
|---|---|---|
| `seeds_per_frozen_dataset_and_budget: 200` | 种子循环 | ✅ `v3_phase_E_random_long.csv` 1 600 行 |
| `summary`（mean / sd / 分位数） | `summarize_random_baseline` | ✅ |
| `quantiles: [0.025, 0.5, 0.975]` | 参数化传入 | ✅ |
| `interpretation: variability_not_CI_for_mean` | 返回值里同时给 `mean_se`，并在 `interpretation` 字段写明 | ✅ |

## 8. 缺口汇总

| 类别 | 数量 | 处理 |
|---|---|---|
| ✅ 已实现 + 有测试 | 47 | 其中 8 行已补代表 rep 真实数据 |
| ⏳ 需真实数据 / 运行期断言 / 编排层 | 6 | 见下 |
| 🚫 显式拒绝非默认值 | 3 | 已生效，不会静默 |
| ❌ 真缺口 | 2 | 均属 F（`oracle_audit.stage` / `candidates`） |

> 计数口径：按表格逐行的**状态列**重数（2026-10-27 19:50）。此前汇总的 27/12/3/4
> 与表内实际标记不符，已按当前表更正；如再改状态必须同步重数。

**缺口与归属（2026-10-27 19:50 更新）**：

1. `cost_model.calibration_only_on_validation` → **已补**：`v3_phase_E_calibration.json`（n=19 987）。
2. `optimization.bucket_convergence` → **已补曲线**（48 行）；**通过阈值仍不能先拍**，留给评审。
3. `oracle_audit.stage`（冻结门禁）→ 依赖 F 阶段的 manifest，属 F。
4. `oracle_audit.candidates`（真值策略）→ 只能在真值解封后，属 F。
5. `freeze_using_observed_data_only` → 仍需运行期断言；目前只有 `fitted_on="training_only"` 的构造期标注。
6. `report.observed_value` → 观测价值属 F01 的 OPE，E 阶段只给 `dgp_truth_tau` 审计值。

**2026-10-27 13:05（北京时间）更新**：第 1、2 项已由
`src/causal_growth/policy/v3_policy_evidence.py` / `scripts/24_e_evidence.py` 实现并有测试，
状态由 ❌ 降为 ⏳，正式数据等 D03 R 结束后的 n=200 000 代表 rep；第 3、4 项仍属 F。
**新暴露的缺口**：`every_full_rep_required` 要求 LP 上界在每个 full rep 上都有，
但 D03 的 200 rep 网格只含 9 个策略，没有 LP 行；E 证据层只在代表 rep 上补 LP，
G 阶段必须每 rep 补 LP 上界，否则不能声称"规模对照已覆盖所有全额 rep"。
**2026-10-27 19:50（北京时间）更新**：E 证据链已用 D03 正式 rep 0 跑完
（19:17:51–19:42:28，9 个产物齐），正文见 `docs/v3_phase_E_evidence.md`。
~~**E01/E02 仍标"未证实"**，等待独立评审，不因"表已生成"改状态。~~

**2026-10-28 05:48（北京时间）更新**：上面那次 19:17 运行**已被取代**——A（`constant`）于
01:12:03–01:35:23、B（`causal_forest`）于 01:35:26–02:04:28 按当前源码各重跑一次
（两家族同 `git_commit=e0048100…`、`source_sha256` 逐值相同 ⇒ AGENTS §12.6 的跨版本配对缺陷已消除），
证据在 `outputs/evidence/e_evidence_rep0_{a,b}/`。评审状态：独立评审 PASS WITH CONDITIONS（6 P1）
→ 主负责修复 → **独立复审 PASS WITH CONDITIONS（05:34，0 P0 + 3 新 P1，无一需要重跑）**。
3 项新 P1 的修复已于 05:46 落地，但按 AGENTS §7.4 主负责不单方改状态：
**E01/E02 仍标"未证实"，待复审确认新 P1 已关闭**，不因"表已生成"改状态。

- **规模扫描**（96 行）暴露：60 000 人池 8 档预算中 7 档 `time_limit_no_incumbent`
  （60 s 时限、墙钟 86.8–103.7 s）；唯一 `optimal` 是"全选"的 1.00 档。
  启发式始终贴 LP 上界 0.8% 以内，`greedy_local_swap` 与贪心 24/24 格完全相同。
  **（05:48 追注）上一条只对 A 家族成立**：A 的 24 格（3 池 × 8 档）在 `n_selected` /
  `predicted_value_cny` / `predicted_cost_cny` / `lp_upper_bound_cny` / `true_value_per_user` /
  `actual_spend_cny` / `true_value_per_actual_spend` 七列上逐格相同（只有墙钟 `seconds` 不同，那不是结果）。
  **B（非退化 τ̂）上 local swap 确实会动**：`predicted_value_cny` 与 `predicted_cost_cny` 各
  **11/24** 格不同（最大 |差| 0.300311 / 0.164791 元），`true_value_per_user` 与
  `true_value_per_actual_spend` 各 **5/24**（最大 0.029170 / 0.057792），`actual_spend_cny` **2/24**
  （最大 10 元）；`n_selected` 与 `lp_upper_bound_cny` 仍 24/24 相同。这正是 P1-1 修复要显示的分离，
  **不能把 A 的退化结果写成一般结论**（复审 N1 同类问题在正文 §8.1 也已分别陈述）。
- **契约补强**：`small_pool_solver_table` 原先对 `time_limit_no_incumbent` 会走空 mask，
  产出 0 花费/0 价值的"合法空名单"假象；2026-10-27 19:45 改为整行写 NaN，
  由 `test_small_pool_no_incumbent_rows_are_nan_not_zero` 锁定。规模表原本已是 NaN。
- **仍未关闭**：LP 每 rep 缺口（G 阶段）、`freeze_using_observed_data_only` 的运行期断言、
  `report.observed_value`（F01）。

## 9. 这套矩阵怎么用

- 评审时逐行问"这行的证据在哪"，答不上来的就是缺口；
- E 正文每完成一项，把 ⏳ 改成 ✅ 并把测试名填进去；
- **不要删掉 ❌ 行**——它们标明了 E 阶段结束时必须交接给 F 的东西。
