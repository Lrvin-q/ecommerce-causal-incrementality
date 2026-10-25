# Phase D.3：五个主模型 + L1/L3 DR-learner 的统一实现

> **合成数据 / 已知 DGP。非真实企业数据。**
> 维护时间：2026-10-25 11:18（北京时间，Asia/Shanghai）。
> 增补时间：2026-10-25 11:38（北京时间）：§2.2 增加随机化层 DR 的保守性说明，
> §7.1 增加"配置口径与实际行为的差异"。
> 本文只记录**接口、冒烟量与实现口径**，不构成任何科学结果：正式重复 R 仍为 0，未做任何真值对比。

---

## 0. 一句话结论

`src/causal_growth/estimate/v3_models.py` 用一个 `fit_predict(model_name, dataset, cfg)` 同时支持
`constant / t_learner / s_learner / causal_forest / dr_learner`；五个模型消费**同一个**
`LearningData`（同一拆分、同一冻结预处理状态），于是"同批重复数据配对比较"不再依赖纪律，
而是由 `preprocessor_hash + 三个切分用户键指纹 + observed_hash` 三个可核对指纹强制保证。
`pytest tests/test_v3_models.py` = **52 passed**（23.9 s）；全量 `pytest tests` 在写盘安静时
通过 **1026 passed, 2 skipped**（331.9 s），最终复跑出现 1 个并发写盘导致的 CLI 假红
（单独复跑该测试 2 passed，详见 §10）。

---

## 1. 接口契约

```python
MODEL_NAMES = ("constant", "t_learner", "s_learner", "causal_forest", "dr_learner")

class FeatureBoundaryError(ValueError)      # 白名单/禁用特征越界 → 抛异常
class ModelNotApplicableError(ValueError)   # 层不适用该模型（L0/L2 调 dr_learner）

prepare_learning_data(dataset: ObservedDataset, cfg, *, time_mode="static") -> LearningData
fit_predict(model_name, dataset: LearningData | ObservedDataset, cfg, *,
            time_mode="static", seed_index=0) -> Predictions

Predictions: .model_name .tau_test .tau_validation .ate .test_keys .info(dict)
    info 关键键：n_features / feature_names / preprocessor_hash / config_hash / observed_hash /
                 train_n,validation_n,test_n / train|validation|test_user_key_hash /
                 train_cpu_seconds / train_wall_seconds / predict_cpu_seconds / total_cpu_seconds /
                 level / identification_mode / 模型专属诊断（crossfit_folds、propensity 范围、
                 pseudo_outcome_sd、constant_source、hyperparameters …）

fit_validation_scorer(data, cfg, *, seed_index=0) -> ValidationScorer
ValidationScorer.score(tau_validation, cfg, *, budget_per_user_cny=None, cost_per_user_cny=None) -> dict
ValidationScorer.score_grid(tau_validation, cfg) -> list[dict]
rank_models(predictions: Mapping[str, Predictions], scorer, cfg, *, budget_per_user_cny=None) -> list[dict]
learning_curve(model_name, dataset, cfg, *, counts=None, time_mode="static", seed_index=0, scorer=None)
    -> list[dict]

# 低层可复用（单测 / F 阶段复算）
crossfit_nuisance(X, y, t, cfg, *, seed_index=0, folds=None, seed_prefix="dr") -> NuisanceFit
aipw_pseudo_outcome(y, t, mu1, mu0, propensity) -> ndarray
crossfit_dr_ate(X, y, t, cfg, *, seed_index=0) -> CrossfitDrAte(.ate .se .folds .psi_sd …)
dr_learner_cate(X, y, t, X_eval, cfg, *, seed_index=0) -> (tau_eval, info)
causal_forest_estimator(cfg, *, seed) -> econml.CausalForestDML
constant_source(cfg) -> "training_itt" | "training_crossfit_dr_ate"
identification_mode(cfg) -> "randomized" | "observational"
require_model_applicable(model_name, cfg) -> None
require_feature_boundary(frame_or_feature_names, cfg, time_mode="static") -> None
require_whitelisted_feature_names(names, cfg, time_mode="static") -> None
reject_forbidden_frame_columns(frame, cfg) -> None
allowed_feature_names(cfg, time_mode="static") -> frozenset[str]
```

**为什么把"准备数据"和"拟合模型"分开**：预处理器只能在训练切分上拟合（`FrozenPreprocessor`），
一个 rep 只该拟合一次。`prepare_learning_data` 一次产出三个 `SplitBlock`，五个模型共享；
若每次 `fit_predict` 都重新 prepare，虽因确定性会得到同一个 hash，但白花算力，也失去
"同一份特征矩阵"的直接证据。

---

## 2. 各模型实现要点

| 模型 | 目标 | 实现 |
|---|---|---|
| `constant` | 常数 τ̂ | 随机化层：`training_itt` = 训练集 `mean(y|T=1) − mean(y|T=0)`；观察性层：`training_crossfit_dr_ate` = 训练集 3 折交叉拟合 AIPW 的 ATE，再把该常数推给每个用户 |
| `t_learner` | `E[Y|X,T=1] − E[Y|X,T=0]` | 两个 LightGBM 回归器（处理组 / 对照组各自拟合） |
| `s_learner` | `E[Y|X,T]` 差 | 一个 LightGBM 回归器，`T` 作为普通特征；预测时分别置 1/0 作差（正则化会收缩处理效应） |
| `causal_forest` | 局部中心化 CATE | `econml.CausalForestDML`（`model_y`=LGBM 回归、`model_t`=LGBM 分类），冻结超参见 §2.1 |
| `dr_learner` | `E[ψ|X]` | 3 折交叉拟合 nuisance → AIPW 伪结局 ψ → 在 `(X, ψ)` 上拟合 LightGBM 回归，预测个体 τ̂ |

LightGBM 超参一律走 `models.lightgbm`（300 棵 / lr 0.05 / leaves 31 / min_child 40 /
colsample 0.8 / `n_jobs=1` / `verbosity=-1`）。装配方式与已跑通的 `scripts/13_v3_pilot.py` 一致；
本模块额外传入 `random_state`（由 `child_seed` 派生），因为 pilot 没传、而正式重复必须可复现。

### 2.1 Causal Forest 冻结口径

`causal_forest_estimator` 从 `models.causal_forest` 读取并**逐项校验**，任何漂移直接 `ConfigError`：
`n_estimators=300`、`min_samples_leaf=60`、`max_depth=null`、`cv=3`、`discrete_treatment=true`、
`treatment_nuisance_model=classifier`、`n_jobs=1`、`inference=false`。
测试 `test_causal_forest_estimator_uses_frozen_hyperparameters` 直接检查装配后的估计器属性，
而不是只检查配置字符串。

### 2.2 DR-learner：交叉拟合与伪结局

对训练集 `(X_i, T_i, Y_i)`，3 折（`models.dr_learner.crossfit_folds`）：

1. 折号来自 `child_rng(master_seed, "v3.models.dr.crossfit", seed_index)` 的 `permutation`，
   不引入裸随机数；同一 `(seed, rep)` 永远同一批折。
2. 对每一折 k：用**其余折**拟合 `m̂1`（处理组 LightGBM 回归）、`m̂0`（对照组 LightGBM 回归）、
   `ê`（LightGBM 分类），只对第 k 折预测，得到**折外** `m1_i, m0_i, e_i`。
   `ê` 按 `models.propensity.estimated_probability_clip = [0.01, 0.99]` 截断。
3. 伪结局（AIPW）：
   `ψ_i = m1_i − m0_i + T_i (Y_i − m1_i)/e_i − (1−T_i)(Y_i − m0_i)/(1−e_i)`
   其均值是 ATE 的双稳健估计，把它当回归目标即得 `τ̂(X)=E[ψ|X]`。
4. 最终模型 `lightgbm_regressor` 在 `(X_i, ψ_i)` 上拟合，对验证/测试集预测。

**为什么必须折外**：ψ 里含 `(Y−m_T(X))/e` 的残差修正项。若 `m_T` 见过该行，残差被系统性压小，
修正项失效，DR 退化为纯结果模型回归。测试
`test_crossfit_nuisance_is_deterministic_and_clipped` 检查两次调用逐元素相等、换 `seed_index` 会变、
倾向得分落在截断区间内。

**常数模型与 DR-learner 共享同一套 nuisance**：两者都用 stream `v3.models.dr.crossfit` 与同一组
折内种子，因此观察性常数模型的 ATE 与 DR-learner 的 `dr_ate_training` 逐位相同。
测试 `test_constant_observational_shares_nuisance_with_dr_learner` 断言 `|差| < 1e-9`。

**随机化层的 DR 是保守口径（效率下界，不是一致性问题）**：在随机化层（L0/L1/L2）设计概率
已知且为 0.5，理论上直接用设计概率的 DR 更有效（少一层估计误差）。当前实现按
`models.dr_learner.propensity_model: lightgbm_classifier` 估计倾向，**因此报告的 DR 效率是保守
下界**，不是该方法在已知设计概率下能达到的最好水平。这一差异属**效率而非一致性**：交叉拟合下
估计倾向仍一致，不引入系统性偏倚。**不改成用设计概率**——那会让"报告的模型"与"配置声明的
模型"不一致，是更严重的问题。该敏感性分析（设计概率 vs 估计倾向）列入 E 阶段议程，用证据
回答，而不是现在替换实现。

### 2.3 识别模式与层级适用性

- `identification_mode` 复刻 `data/v3_sql.py:184` 的 `observational_history` 规则：
  `dgp.profile == "l3" and not dgp.virtual_aa_labels` → `observational`，否则 `randomized`。
  观察性模式出现在非 L3 会直接 `ConfigError`。
- `require_model_applicable` 读 `models.common + additional_by_level[level]`：
  L1/L3 允许 `dr_learner`，L0/L2 抛 `ModelNotApplicableError`。
  测试 `test_model_applicability_mirrors_frozen_config` 断言镜像关系与冻结配置一致。

---

## 3. 特征边界：白名单 + 禁用列硬拒绝

三道闸，全部是**代码路径**而不是注释：

1. **frame 级**：`prepare_learning_data` 拿到 `ObservedDataset.observations` 后第一件事调用
   `require_feature_boundary(frame, cfg, time_mode)` → `reject_forbidden_frame_columns`。
   命中即抛 `FeatureBoundaryError`。判定用三层：`models.forbidden_features` 精确名
   （`U / true_propensity / true_cate / potential_profit0 / potential_profit1 /
   potential_purchase0 / potential_purchase1`）、`potential_` 前缀、以及
   `configs/v3_data.yaml → isolation.forbidden_column_patterns` 的正则
   （额外覆盖 `audit/latent/oracle/true_*/control_feasible/common_feasible/knob`）。
2. **特征名级**：`_split_block` 对每个切分调用 `require_whitelisted_feature_names`。
   允许集合由 `models.feature_whitelist` 派生：数值 4 列 + `*_missing` 4 列 + `channel_*` 4 列
   （+ 已注册时间特征）。要求**恰好相等**：多一列（越界）或少一列（漏特征）都抛异常。
3. **模型级**：模型只看到 `FrozenPreprocessor.transform(...).matrix`，从不接触观测表的其余列
   （`net_profit / treatment / design_probability / run_id / user_id` 只作为标签或键使用）。

对应测试（`tests/test_v3_models.py`）：

| 测试名 | 验证什么 |
|---|---|
| `test_forbidden_feature_columns_are_rejected_at_interface[U/true_propensity/true_cate/potential_*]` | 6 个禁用列名逐个注入观测 frame → `FeatureBoundaryError` |
| `test_audit_and_latent_patterns_are_rejected_even_if_not_in_models_yaml[audit_flag/latent_quality/oracle_effect/true_effect]` | 不在 `models.yaml` 名单、但命中 `v3_data.yaml` 正则的列同样被拒 |
| `test_feature_block_must_match_whitelist_exactly` | 多一列 `net_profit`、少一列 `channel_other`、含 `true_cate` 三种越界都抛 |
| `test_fit_predict_runs_frame_boundary_gate_and_propagates_failure` | monkeypatch 证明 `fit_predict` 真的调用该闸（`calls == ["DataFrame"]`），且闸抛错会原样传出 |
| `test_allowed_feature_names_equal_fitted_preprocessor` | 允许集合与预处理器实际输出的 12 列完全一致 |

---

## 4. 验证集打分与模型选择（只用观测数据）

`fit_validation_scorer` 只在**验证集**上拟合一次 AIPW 伪结局 `ψ`，之后对任意 `τ̂` 复用：

- 随机化层：倾向得分用**记录的设计概率**（`evaluation.randomized_propensity`），结果模型仍交叉拟合；
- 观察性层：倾向得分只用已观测特征估计（`evaluation.observational_propensity`），按冻结边界截断；
- `evaluation.crossfit_folds = 3`；支持越界比例超过
  `evaluation.reliability_gate.maximum_observed_support_violation_fraction` 时抛"无法可靠评估"。

`ValidationScorer.score(τ̂, cfg, budget_per_user_cny=…)`：

1. 成本用冻结口径 `policy.face_value_cny × business.redemption_rate`（= 10 × 0.55 = 5.5 元/人），
   有 `policy.cost_model.cost_floor_cny` 兜底；也允许传入学到的成本向量（Phase E 用）。
2. 预算 `= 人均预算 × 验证集人数`，用 `policy.selection.greedy_by_ratio` 选人
   （只取正 τ̂，符合 `no_negative_predicted_increment_for_targeting`）。
3. 策略价值 `V = mean(π_i ψ_i)`，**95% 单侧下界** `LCB = V − z·sd(πψ)/√n`
   （`z = NormalDist().inv_cdf(0.95)`，置信水平取 `evaluation.confidence_level`）。
   打分明细里的 `scoring` 字段固定为 `validation_crossfit_dr_policy_value_lower_confidence_bound`。

`rank_models` 按冻结预算网格上 LCB 的算术平均排序（`selection.budgets_from:
policy.budget.per_user_grid_cny`），并列时用 `selection.tie_break_order`。
`_require_truth_free_selection` 每次打分都重新校验
`selection.scoring` 未改、`true_effect_tuning_forbidden: true` 未改；改了就 `ConfigError`。

---

## 5. 学习曲线：只报规模 vs 稳定性 / 验证集指标

`learning_curve` 在 `models.learning_curve_training_counts`（10k/25k/50k/100k）上重训：

- 子样本 stream 是 `v3.models.learning_curve.subsample`，**不含模型名**，因此同一 rep 内所有模型
  在每个规模上拿到同一批训练行（`data_selection_seed_scope: shared_across_models_within_rep`）；
- 预处理状态保持训练切分冻结的那一份不变，规模效应不与预处理器重估混在一起；
- 每行只输出：`n_train`、`tau_sd_validation`、`validation_policy_value(_lcb)`、
  `stability_rmse_vs_largest`、`stability_corr_vs_largest`、`train_cpu_seconds`、
  `subsample_key_hash` 等——**没有**任何真值误差列。测试
  `test_learning_curve_reports_only_truth_free_columns` 断言返回字典的键集合恰为这 16 个。
- 超过可用训练人数的规模会被丢弃（并在行里给出 `n_train_available`）；一个都不剩则抛异常。
- 测试 `test_learning_curve_subsample_is_shared_and_reproducible` 用 `child_rng` 重算下标，
  断言子样本指纹与实现一致、且 `constant` 与 `t_learner` 在同一规模上看到同一批行。

---

## 6. 冒烟结果（n = 20,000，L1_main，rep 0）

命令与产物：

```powershell
$env:PYTHONUTF8='1'; $env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m causal_growth.estimate.v3_models
# 产物：outputs/tables/v3_phase_D_models_smoke.csv（5 行 × 30 列，无真值列）
```

数据用**生产 SQL 与拆分链路**（`build_raw_tables → inject_dirt → deduplicate_events →
run_sql_pipeline → assign_user_splits`），只跳过全链路 manifest 写入与源码前后哈希门禁——
后者会在多代理并发写 `v3*.py` 时假红，且全链路本身由 `tests/test_v3_pipeline.py` 覆盖。
拆分：train 10,000 / validation 4,000 / test 6,000，12 个特征。
整条命令墙钟 **33 s**（含 DGP、五表清洗、两次 SQL、特征变换、五个模型、验证集打分）。

| 模型 | 训练 CPU s | 预测 CPU s | 合计 CPU s | ATE（测试集均值） | τ̂ sd（测试集） | τ̂ sd（验证集） | 验证集策略价值 | 95% 单侧 LCB |
|---|---|---|---|---|---|---|---|---|
| constant | 0.000 | 0.000 | 0.000 | 0.4009 | 0.0000 | 0.0000 | −0.0083 | −0.1062 |
| t_learner | 0.297 | 0.484 | 0.781 | 0.3792 | 4.6755 | 4.6096 | −0.0017 | −0.2439 |
| s_learner | 0.219 | 0.375 | 0.594 | 0.4135 | 2.0975 | 2.0896 | 0.1002 | −0.1485 |
| causal_forest | 7.641 | 0.266 | 7.906 | 0.5141 | 0.8974 | 0.8882 | 0.0113 | −0.2133 |
| dr_learner | 2.406 | 0.188 | 2.594 | 0.3247 | 6.0372 | 6.3168 | 0.0303 | −0.1638 |

**同拆分配对证据**（5 行完全相同，可从 CSV 直接核对）：

| 指纹 | 值（前 12 位） | 说明 |
|---|---|---|
| `preprocessor_hash` | `68fa36b856f5…` | 预处理状态只在训练切分拟合一次，五模型共享 |
| `config_hash` | `e1aa4314b8d8…` | 同一场景配置 |
| `observed_hash` | `4dd06f4de01c…` | 同一份 SQL 观测表 |
| `split_fingerprint` | `7345510f8cd7…` | 三个切分用户键指纹的派生哈希 |
| `train_user_key_hash` | `9defdce3b358…` | 同一批训练用户 |
| `validation_user_key_hash` | `cefcb6d45730…` | 同一批验证用户 |
| `test_user_key_hash` | `2ba4b0cf04d7…` | 同一批测试用户（τ̂ 行序与之一一对应） |

**这 5 行不是科学结果**：验证集 LCB 全为负只说明这套"单 rep、4,000 验证用户、未经调参"的
冒烟管道跑通了，既不能读成"五个模型都不赚钱"，也不能读成模型排名。正式结论必须等 Phase E/F：
正式 R、独立随机验证、真值审计。

**确定性已验证、CPU 秒不可当基准**：同一命令复跑一次，除三个 CPU 列外**所有列逐元素相同**
（`ate_test`、`tau_sd_test`、`validation_policy_value(_lcb)`、七个指纹的差全为 0.0），
但 CF 的训练 CPU 从 7.64 s 变成 11.06 s——当时机器上还有其他代理在跑。
表里的 CPU 秒只用于确认量级，资源外推请用 D.1 的 pilot 或串行复测。

---

## 7. 冻结配置的缺口与我的处理（未改配置）

### 7.1 配置口径与实际行为的差异

**结论：`models.yaml → lightgbm.subsample: 0.8` 在当前 LightGBM 下不生效；实际生效的随机性
来源只有 `colsample_bytree: 0.8`。**

- **机制**：LightGBM 的 `bagging_fraction`（sklearn 参数名 `subsample`）只有在 `bagging_freq`
  （`subsample_freq`）`> 0` 时才参与训练；`models.yaml` 没有 `subsample_freq`，其默认值为 0，
  因此 `subsample: 0.8` 被静默忽略。
- **实测证据**（`colsample_bytree=1.0`、`subsample=0.8`、同一份 400×3 数据、只改 `random_state`）：
  `subsample_freq=0` 时两次预测**逐元素相同**（max|diff| = 0.0）；`subsample_freq=1` 时差异 0.32。
  即配置里真正带随机性的只有 `colsample_bytree=0.8`（它不受 `subsample_freq` 影响）。
- **定性**：这是**忠实执行冻结配置**的结果，**不是实现遗漏**——模块把 `subsample` 原样传给
  LightGBM，没有偷偷补 `subsample_freq`（那会改变冻结超参的实际行为，却仍声称"按配置执行"）。
- **处置**：要让 bagging 真正生效，需给 `models.yaml` 新增 `subsample_freq` 并重走 A 阶段评审
  （会改冻结 `config_hash`），**本轮不做，仅披露**。`subsample` 属**正则化选择**，不是识别假设
  或机制参数：它是否生效不改变结论方向，只改变模型的方差特性；现在改还会让 D 的冒烟与后续 R
  结果建立在刚改过的模型上，反而增加"结果与配置不一致"的风险。

### 7.2 其余口径选择

1. **没有 early stopping。** `models.yaml` 只给固定 `n_estimators=300`，本模块不使用验证集早停
   （也避免把验证集用于拟合）。
2. **DR 的倾向模型在随机化层也按配置估计**（`propensity_model: lightgbm_classifier`），
   没有替换成已知设计概率——这是对冻结配置的忠实执行，其"效率保守下界"的含义见 §2.2；
   设计概率只用在验证集 DR 打分（`evaluation.randomized_propensity`）。
3. **`models.causal_forest.treatment_nuisance_model: classifier`** 被显式校验：`model_t`
   必须是分类器，否则 `ConfigError`（二值处理用回归器拟合会让 DML 的残差正交化失准）。

---

## 8. 不可违反的纪律与落地方式

| 纪律 | 落地 |
|---|---|
| 只用 `child_rng` 派生随机流 | 折号：`child_rng(...).permutation`；`random_state`：`child_seed(...)`。模块内无裸 `np.random.*` |
| 同一拆分、同批数据配对比较 | 一个 `LearningData` + 七个指纹写入每行预测/冒烟表 |
| 训练/验证/测试按用户分离 | 拆分由 `assign_user_splits` 产生；本模块只消费 `split` 列，不重划 |
| 不得读真值 | 估计路径不 import `causal_growth.dgp`、不 import `audit/`；测试 `test_estimation_module_does_not_import_truth_or_dgp` 用子进程验证 |
| 失败要响 | 未知模型 / 层不适用 / 特征越界 / 配置口径漂移 / 预算为负 / 倾向得分越界 全部抛异常 |

---

## 9. 未做到的部分与原因

1. **没有跑正式 R。** 按任务边界只做 n=20,000 单 rep 冒烟；正式 R 在 Phase E/F。
2. **没有做任何真值对比。** 包括学习曲线在内，本模块与本文都不计算 RMSE-vs-truth；这是任务
   的硬约束（真值对比属最终审计）。所以本文不能回答"哪个模型更准"。
3. **观察性常数口径没进冒烟表。** 冒烟场景 L1 是随机化层，只走 `training_itt`；
   `training_crossfit_dr_ate` 由 L3 单测覆盖（`test_constant_observational_equals_crossfit_dr_ate`、
   `test_constant_observational_shares_nuisance_with_dr_learner`）。
4. **学习曲线的 25k/50k/100k 没在冒烟里跑。** n=20,000 时训练池只有 10,000，只有 10k 可用；
   能力本身由单测（200/400）与正式 rep（训练池 100,000）覆盖。
5. **未做区间推断。** `causal_forest` 固定 `inference=false`（冻结配置），本模块不提供 CF 的
   置信区间；不确定性口径留给 Phase E 的影响函数/bootstrap。
6. **未做嵌套调参。** 超参完全冻结，`selection.outcome_tuning_uses` 提到的
   `validation_factual_rmse_and_brier` 属 Phase E 的超参选择，本模块不实现（避免把验证集
   同时用于调参与选择）。
7. **L2 的时间特征模式只实现、未在 D.3 里实测。** `time_mode="time_features"/"rolling_retrain"`
   的白名单与预处理路径已经接好（`allowed_feature_names` 会加入 `assignment_week`、
   `assignment_elapsed_days`，并校验与预处理器状态一致），但本模块只负责"特征模式"；
   滚动重训的候选选择与 `fit_preprocessor(role="rolling_train")` 凭据属上游编排职责。
   L2 的时间切分与滚动重训在 D/F 的其他格，本模块测试只覆盖 `static`。
   全量回归曾在写盘安静时串行通过（1026 passed / 2 skipped），最终复跑出现 1 个并发写盘
   导致的 CLI 假红；两次都见 §10。

---

## 10. 并发写盘与全量回归

2026-10-25 11:04（北京时间）首次跑 `pytest tests` 得到 3 个失败，全部是
`RuntimeError: source files changed during the data run; retain this attempt as failed`
（`src/causal_growth/data/v3_pipeline.py:168`），失败项为
`tests/test_v3_data_checks.py::test_ledger_failure_is_loud_preserves_attempt_and_cannot_resume_as_passed`
与 `tests/test_v3_pipeline.py::test_full_chain_has_materialized_five_tables_and_sql_roundtrip[L0_P_main/L1_main]`。
原因是 `pipeline_source_hashes()` 在 pipeline 前后各哈希一次 `src/causal_growth/**/v3*.py`，
而同一时间其他代理正在写 `design/v3_power.py`、`evaluation/v3_aa.py` 等文件。
这是**并发写盘的竞态**，不是本模块或数据链路的逻辑错误；门禁本身是 C 阶段评审过的属性，不应削弱。

2026-10-25 11:25–11:31（北京时间）在写盘安静时单进程串行复跑，结果
**1026 passed, 2 skipped, 1 warning, exit 0, 331.85 s**。2 个 skip 来自其他代理测试里的
条件守卫（并发写盘 / 中间产物未生成），都不是 D.3 的用例；D.3 的 52 项全部执行且通过。

2026-10-25 11:29–11:36（北京时间）最终复跑：**1029 passed, 1 failed**，
唯一失败是 `tests/test_v3_cli.py::test_real_cli_preserves_paired_canonical_streams[scenario_pair1]`
（子进程跑 `scripts/11_build_v3_data.py` 时返回码 1，错误仍是全链路 manifest 失败路径）。
单独复跑该测试：**2 passed in 38.82 s**，即又是并发写盘竞态，不是逻辑错误。
因此**全量绿灯的最终凭据必须由主控在所有代理停写后串行跑一次**；D.3 自己的 52 项与本次失败无关。

---

## 11. 给主控的集成说明（3 行）

1. 一个 rep 只调一次 `prepare_learning_data(ObservedDataset, cfg)`，把同一个 `LearningData`
   传给五个 `fit_predict`；把 `Predictions.info` 里的七个指纹写进该 rep 的 manifest。
2. 用 `fit_validation_scorer(data, cfg)` 建一次打分器，`rank_models({model: pred}, scorer, cfg)`
   拿 LCB 排名；`learning_curve(..., scorer=scorer)` 复用同一打分器。
3. L0/L2 不要传 `dr_learner`（会抛 `ModelNotApplicableError`）；`tests/test_v3_models.py` 的
   52 项可独立作为本模块回归门禁。

---

## 12. 复现命令

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
cd 'D:\L\practice_project\营销数分项目'
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m pytest tests\test_v3_models.py --basetemp=.pytest_basetemp   # 52 passed
.\.venv\Scripts\python.exe -m causal_growth.estimate.v3_models                              # 冒烟表
```

数据来源：合成数据 / 已知 DGP，`L1_main`，`project.master_seed = 20240101`，rep 0，
**正式重复 R = 0**。所有数字见 `outputs/tables/v3_phase_D_models_smoke.csv`。
