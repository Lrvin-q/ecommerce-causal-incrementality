# Phase E 配置覆盖矩阵

> 合成数据 / 已知 DGP。维护时间：**2026-10-26 17:00（北京时间）**。
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
| `per_user_grid_cny`（8 点） | 预算扫描循环 | ⏳ 网格已跑通（72 行），正式 E 数据待 R 后 |
| `total_rule` | `expected = base × n_target` | ✅ |
| `freeze_using_observed_data_only` | 文档约束；`CostModel.fitted_on` 标 `training_only` | ⏳ 需运行期断言 |
| `actual_spend_overrun_reported` | `audit_budget.within_expected` | ✅ |
| `hard_cap_claim_allowed: false` | `audit_budget` 返回 `hard_cap_claim_allowed: False`，编码进返回值 | ✅ |
| `conservative_comparison.modes.buffered_expected` | `BudgetPlan.buffered = expected × multiplier` | ✅ |
| `conservative_comparison.modes.worst_case_face` | `BudgetPlan.worst_case` + `max_recipients_face` | ✅ |
| `conservative_comparison.policies` | 三策略组合 | ⏳ 已实现（`conservative_comparison_table`），待正式数据 |
| `random_seeds_per_dataset_budget_mode: 200` | 种子循环 | ⏳ 已实现，待正式数据 |
| `report`（6 项） | 已有 `selected_count` / `predicted_cost` / `observed_cost_total` / `within_expected` / `within_buffered` / `face_bound_respected` | ⏳ 已补 `actual_spend_overrun_probability`（多次随机）；`observed_value` 留 F |

## 3. `cost_model`

| 键 | 实现 | 状态 |
|---|---|---|
| `target` | `CostModel.target` 构造时校验字符串 | ✅ |
| `primary: two_stage_purchase_and_conditional_redemption_amount` | `fit_cost_model` 两阶段 | ✅ |
| `auxiliary: direct_cost_regression` | `CostModel.auxiliary_direct` | ✅ |
| `trained_only_on: training_observed_logs` | `fitted_on="training_only"` + 只用 `treatment=1` | ✅ |
| `calibration_only_on: validation_observed_logs` | `calibrate_cost_predictions`（只吃 validation 处理组） | ⏳ 已实现，待正式 rep |
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
| `small_exact.pool_sizes` | 20 / 100 / 500 | ⏳ 已实现，待正式数据 |
| `bucket_convergence`（5 档宽度） | `bucket_convergence_table`（近似桶 DP + 原成本复核回退） | ⏳ 已实现，待正式曲线；**阈值仍由评审看曲线后定** |
| `large.algorithms` | greedy / local_swap / MILP / LP 全有 | ✅ |
| `large.milp_time_limit_seconds: 60` | `milp_select` 参数 | ✅ |
| `large.milp_relative_gap_tolerance: 0.001` | 同上 | ✅ |
| `large.require_incumbent_bound_gap_and_status` | `MilpResult` 四个字段 | ✅ |
| `large.pool_sizes` | 1000 / 5000 / full_test | ⏳ 已实现，待正式数据 |
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
| `seeds_per_frozen_dataset_and_budget: 200` | 种子循环 | ⏳ 已实现，待正式数据 |
| `summary`（mean / sd / 分位数） | `summarize_random_baseline` | ✅ |
| `quantiles: [0.025, 0.5, 0.975]` | 参数化传入 | ✅ |
| `interpretation: variability_not_CI_for_mean` | 返回值里同时给 `mean_se`，并在 `interpretation` 字段写明 | ✅ |

## 8. 缺口汇总

| 类别 | 数量 | 处理 |
|---|---|---|
| ✅ 已实现 + 有测试 | 27 | — |
| ⏳ 需真实数据 / 编排层 | 12 | E 正文补齐 |
| 🚫 显式拒绝非默认值 | 3 | 已生效，不会静默 |
| ❌ 真缺口 | 4 | 见下 |

**四个真缺口与归属**：

1. `cost_model.calibration_only_on_validation` → 需要真实 validation 切分，E 正文做。
2. `optimization.bucket_convergence` → 需要真实数据画收敛曲线，**阈值不能先拍**。
3. `oracle_audit.stage`（冻结门禁）→ 依赖 F 阶段的 manifest，属 F。
4. `oracle_audit.candidates`（真值策略）→ 只能在真值解封后，属 F。

**2026-10-27 13:05（北京时间）更新**：第 1、2 项已由
`src/causal_growth/policy/v3_policy_evidence.py` / `scripts/24_e_evidence.py` 实现并有测试，
状态由 ❌ 降为 ⏳，正式数据等 D03 R 结束后的 n=200 000 代表 rep；第 3、4 项仍属 F。
**新暴露的缺口**：`every_full_rep_required` 要求 LP 上界在每个 full rep 上都有，
但 D03 的 200 rep 网格只含 9 个策略，没有 LP 行；E 证据层只在代表 rep 上补 LP，
G 阶段必须每 rep 补 LP 上界，否则不能声称"规模对照已覆盖所有全额 rep"。

## 9. 这套矩阵怎么用

- 评审时逐行问"这行的证据在哪"，答不上来的就是缺口；
- E 正文每完成一项，把 ⏳ 改成 ✅ 并把测试名填进去；
- **不要删掉 ❌ 行**——它们标明了 E 阶段结束时必须交接给 F 的东西。
