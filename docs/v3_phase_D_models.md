# Phase D.3：五个主模型 + L1/L3 DR-learner 的统一实现

> **合成数据 / 已知 DGP。非真实企业数据。**
> 维护时间：2026-10-25 11:18（北京时间，Asia/Shanghai）。
> 增补时间：2026-10-25 11:38（北京时间）：§2.2 增加随机化层 DR 的保守性说明，
> §7.1 增加"配置口径与实际行为的差异"。
> 增补时间：2026-10-25 15:20（北京时间）：落地独立评审 C7——§1 接口、§2.4 倾向来源开关与
> raw 截断诊断、§7.1.2 `propensity.primary` 披露、§9 未做到清单、§12 复现命令、§13 效率对照表。
> 本文只记录**接口、冒烟量与实现口径**，不构成任何科学结果：正式重复 R 仍为 0，未做任何真值对比。
> §13 的敏感性对照是 R=3 的小规模效率对照，也不是正式结果。

---

## 0. 一句话结论

`src/causal_growth/estimate/v3_models.py` 用一个 `fit_predict(model_name, dataset, cfg)` 同时支持
`constant / t_learner / s_learner / causal_forest / dr_learner`；五个模型消费**同一个**
`LearningData`（同一拆分、同一冻结预处理状态），于是"同批重复数据配对比较"不再依赖纪律，
而是由 `preprocessor_hash + 三个切分用户键指纹 + observed_hash` 三个可核对指纹强制保证。
C7 增补后，DR 的倾向得分多了**显式**的 `known_design` 来源（默认仍是 `estimated`），并把
截断前的 raw 概率范围与截断计数变成可审计字段（§2.4）；`known_design` 与 `estimated` 的
效率差见 §13。
`pytest tests/test_v3_models.py` = **61 passed**（机器有正式作业时单轮约 30–60 s）；
全量 `pytest tests` 在写盘安静时通过 **1026 passed, 2 skipped**（331.9 s），最终复跑曾出现
1 个并发写盘导致的 CLI 假红（单独复跑该测试 2 passed），详见 §10。

---

## 1. 接口契约

```python
MODEL_NAMES = ("constant", "t_learner", "s_learner", "causal_forest", "dr_learner")
PROPENSITY_SOURCES = ("estimated", "known_design")   # C7：默认必须是 estimated

class FeatureBoundaryError(ValueError)      # 白名单/禁用特征越界 → 抛异常
class ModelNotApplicableError(ValueError)   # 层不适用该模型（L0/L2 调 dr_learner）
class PropensitySourceError(ValueError)     # C7：倾向来源非法/观察性层要 known_design

prepare_learning_data(dataset: ObservedDataset, cfg, *, time_mode="static") -> LearningData
fit_predict(model_name, dataset: LearningData | ObservedDataset, cfg, *,
            time_mode="static", seed_index=0,
            propensity_source="estimated", design_probability=None) -> Predictions

Predictions: .model_name .tau_test .tau_validation .ate .test_keys .info(dict)
    info 关键键：n_features / feature_names / preprocessor_hash / config_hash / observed_hash /
                 train_n,validation_n,test_n / train|validation|test_user_key_hash /
                 train_cpu_seconds / train_wall_seconds / predict_cpu_seconds / total_cpu_seconds /
                 level / identification_mode / 模型专属诊断（crossfit_folds、
                 propensity_source、propensity_min/max/mean、propensity_raw_min/max、
                 propensity_clipped_count、propensity_clip_low/high、
                 propensity_clipping_detected（+触发时 propensity_clipping_note）、
                 pseudo_outcome_sd、constant_source、hyperparameters …）

fit_validation_scorer(data, cfg, *, seed_index=0) -> ValidationScorer
ValidationScorer.score(tau_validation, cfg, *, budget_per_user_cny=None, cost_per_user_cny=None) -> dict
ValidationScorer.score_grid(tau_validation, cfg) -> list[dict]
rank_models(predictions: Mapping[str, Predictions], scorer, cfg, *, budget_per_user_cny=None) -> list[dict]
learning_curve(model_name, dataset, cfg, *, counts=None, time_mode="static", seed_index=0, scorer=None)
    -> list[dict]

# 低层可复用（单测 / F 阶段复算）
crossfit_nuisance(X, y, t, cfg, *, seed_index=0, folds=None, seed_prefix="dr",
                  propensity_source="estimated", design_probability=None) -> NuisanceFit
aipw_pseudo_outcome(y, t, mu1, mu0, propensity) -> ndarray
crossfit_dr_ate(X, y, t, cfg, *, seed_index=0,
                propensity_source="estimated", design_probability=None)
    -> CrossfitDrAte(.ate .se .folds .psi_sd .propensity_source .propensity_clipped_count …)
dr_learner_cate(X, y, t, X_eval, cfg, *, seed_index=0,
                propensity_source="estimated", design_probability=None) -> (tau_eval, info)
causal_forest_estimator(cfg, *, seed) -> econml.CausalForestDML
constant_source(cfg) -> "training_itt" | "training_crossfit_dr_ate"
identification_mode(cfg) -> "randomized" | "observational"
resolve_propensity_source(cfg, source) -> "estimated" | "known_design"   # C7
itt_estimate(y, t) -> (ate, se)                                          # C7 基准估计量
run_propensity_sensitivity(*, scenarios=..., n=20000, reps=3, out_path=None) -> DataFrame  # C7
require_model_applicable(model_name, cfg) -> None
require_feature_boundary(frame_or_feature_names, cfg, time_mode="static") -> None
require_whitelisted_feature_names(names, cfg, time_mode="static") -> None
reject_forbidden_frame_columns(frame, cfg) -> None
allowed_feature_names(cfg, time_mode="static") -> frozenset[str]
```

`NuisanceFit` 的字段（C7 后）：`mu1 / mu0 / propensity / folds / fold_sizes /
propensity_min / propensity_max / propensity_raw_min / propensity_raw_max /
propensity_clipped_count / propensity_clip_low / propensity_clip_high / propensity_source`，
另有属性 `propensity_mean` 与 `clipping_triggered`。
`known_design` 路径下 `propensity_clip_low/high` 为 `NaN`、`propensity_clipped_count` 恒为 0
（表示"没有施加截断"，不是"截断边界为 0"）。

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

**注意口径**：`causal_forest_estimator` 只对五项显式抛 `ConfigError`——`n_jobs` / `inference` / `discrete_treatment` / `cv` / `treatment_nuisance_model`；`n_estimators` / `min_samples_leaf` / `max_depth` 是**直接读配置传入**，改动它们不会在运行时抛错，而是由 `config_hash` 在产物绑定层面保护。因此「任何漂移都会立刻报错」的说法不准确：前者是运行时断言，后者是事后溯源。
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

> **口径更正**：`|差| < 1e-9` 只是**自洽性检查**——观察性常数模型与 DR-learner 共用同一套折外 nuisance、同一 seed，所以两者必然相等，这是**自同义反复，不是正确性证据**。真正的正确性证据是：AIPW 伪结局按折外预测构造（每折只在其余折拟合 m1/m0/e），以及 `ψ.mean()` 与 `crossfit_dr_ate.ate` 的**精确恒等**——即「ATE 确实是 ψ 的均值」这一定义关系被实现满足。

**随机化层的 DR 默认用估计倾向，报告的是效率保守下界（不是一致性问题）**：随机化层的设计概率
已知（L0/L1 为 0.5；L2 按场景 `treatment_probability` 取 0.1/0.3/0.5），理论上直接用设计概率
的 DR 更有效（少一层估计误差）。D.3 默认按 `models.dr_learner.propensity_model:
lightgbm_classifier` 估计倾向，**因此默认报告的 DR 效率是保守下界**，不是该方法在已知设计
概率下能达到的最好水平。该差异属**效率而非一致性**：交叉拟合下估计倾向仍一致，不引入系统性
偏倚。

**默认不换，只加显式开关（C7 增补）**：把默认改成设计概率会让"报告的模型"与"配置声明的模型"
不一致，并直接改写 52 项已验收契约的数字，是更严重的问题。C7 因此新增
`propensity_source="known_design"`（默认仍 `estimated`），把"设计概率 vs 估计倾向"从 E 阶段
议程变成现在可复算的对照：口径见 §2.4，实测数字见 §13 与
`outputs/tables/v3_phase_D_models_sensitivity.csv`。

### 2.3 识别模式与层级适用性

- `identification_mode` 复刻 `data/v3_sql.py:185` 的 `observational_history` 规则：
  `dgp.profile == "l3" and not dgp.virtual_aa_labels` → `observational`，否则 `randomized`。
  观察性模式出现在非 L3 会直接 `ConfigError`。
- `require_model_applicable` 读 `models.common + additional_by_level[level]`：
  L1/L3 允许 `dr_learner`，L0/L2 抛 `ModelNotApplicableError`。
  测试 `test_model_applicability_mirrors_frozen_config` 断言镜像关系与冻结配置一致。

### 2.4 倾向得分来源开关与 raw 截断诊断（C7 增补）

**开关**：`propensity_source` 取值 `"estimated"`（默认）或 `"known_design"`，贯穿
`crossfit_nuisance / crossfit_dr_ate / dr_learner_cate / fit_predict`。

| 来源 | e 从哪来 | 截断 | 允许的层 | 默认 |
|---|---|---|---|---|
| `estimated` | 3 折交叉拟合 LightGBM 分类器（`models.dr_learner.propensity_model`） | 按 `models.propensity.estimated_probability_clip` 截断 | 随机化 + 观察性 | ✅ |
| `known_design` | 观测表 `design_probability` 列（逐人设计真值） | **不截断** | 只有随机化识别模式（`identification_mode == "randomized"`；L3 观察性历史全部拒绝） | ❌ 必须显式开启 |

五条硬规则，全部是代码路径而不是注释：

1. **默认不变**：不传 `propensity_source` 时保持 D.3 已验收口径（同一折号、同一组
   `random_state`、同一截断边界）；52 项旧测试全绿是这一点的回归门禁。
2. **观察性层必须报错**：L3 传 `known_design` → `PropensitySourceError`
   （`test_known_design_is_rejected_on_observational_level`）。L3 的 `design_probability`
   全为 NaN，没有"已知设计概率"可言。
3. **配置须先注册**：`known_design` 要求 `models.ate.randomized` 含 `known_design_ipw`，
   否则 `ConfigError`——配置没登记的估计量不允许在代码里悄悄可用。
4. **只换 e，不换交叉拟合**：`known_design` 下 `m1/m0` 仍按同一 `seed_index` 与同一折号做
   折外拟合，`mu1/mu0` 与 `estimated` 路径**逐元素相同**
   （`test_known_design_swaps_only_propensity` 直接断言）。因此两条路径的差异只可能来自 e。
5. **非 DR 模型不许借道**：`t_learner / s_learner / causal_forest / constant` 传
   `known_design` 一律 `PropensitySourceError`；`estimated` 路径传 `design_probability`
   同样报错，防止默认路径被偷换成设计概率。

**raw 概率诊断（`models.propensity.raw_probability_diagnostics_required`）**：
`NuisanceFit` 不再只存截断后的 min/max，而是存四组审计量：

| 字段 | 含义 |
|---|---|
| `propensity_raw_min/max` | 截断**前**的 e 取值范围（估计倾向的真实极端程度） |
| `propensity_clipped_count` | 被截断改写的样本数；`0` 表示截断未触发 |
| `propensity_clip_low/high` | 实际生效的截断边界；`known_design` 不截断时为 NaN |
| `propensity_source` | `estimated` / `known_design`，防止两种口径的产物混读 |

`propensity_clipped_count > 0` 时，DR 的 `info` 里出现
`propensity_clipping_detected: True` 与 `propensity_clipping_note`，固定文案：
**"estimated propensity 触发截断：截断引入的偏倚不可忽略，该 rep 的 DR 结果必须单独标注"**。
截断等价于对极端逆概率权重的硬 winsorize，其方向与大小都随样本变化；**触发截断的 rep，
DR 点估计与 SE 都不能与未触发的 rep 直接合并**。

触发实验（`test_extreme_propensity_triggers_clipping_and_info_marker`）：构造"处理几乎由 X
完全决定"的极端样本（n=1,600，818 个处理；折外 e 的 raw 范围 2.13e-04 ~ 0.999981），
`propensity_clipped_count = 1245/1600 > 0`、`propensity_clipping_detected is True`、note 出现；
同一份数据改用 `known_design`（e 恒 0.5）时计数回到 0，证明"诊断跟着来源走"。

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

**7.1.1 LightGBM `subsample: 0.8` 未生效**

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

**7.1.2 倾向模型：配置声明 `primary: logistic`，D.3 实现一律 LightGBM（必须披露）**

`models.yaml → propensity` 同时声明了两套倾向设定：

| 键 | 声明值 | D.3 是否使用 |
|---|---|---|
| `propensity.primary` | `logistic` | **否**——估计路径里没有任何 logistic 倾向 |
| `propensity.sensitivity` | `lightgbm_classifier` | **是**——`dr_learner`、观察性常数模型、观察性验证集打分全部用它 |
| `propensity.estimated_probability_clip` | `[0.01, 0.99]` | 是（`estimated` 路径；`known_design` 不截断） |
| `propensity.raw_probability_diagnostics_required` | `true` | 是（C7 落地，见 §2.4） |

**披露口径**：按配置语义，`primary` 是**声明的主口径**、`sensitivity` 是**敏感性备选**；
而 D.3 的**全部已交付数字**（冒烟表、DR 的 `dr_ate_training`、验证集 DR 打分）都来自
**`sensitivity` 那一档的 LightGBM**。这是一个**配置声明与实际实现的差距**，
**必须披露，不能读成"D.3 按 primary 口径交付"**：

- **不是 bug**：LightGBM 与 logistic 都是合法的倾向估计器；D.3 从 pilot 起就用 LightGBM
  （`scripts/13_v3_pilot.py`），实现的是**一条固定路径**，没有按样本随机切换、没有静默回退；
- **后果**：如果评审要求"主分析必须是 logistic 倾向"，D.3 的 DR 数字需要重跑一版 logistic
  倾向才能对应 `primary`；当前数字只能声称是 **LightGBM 倾向口径**；
- **处置**：本轮**不改配置**（七份 YAML 冻结，`config_hash` 必须保持 `30511a32…`），也
  **不实现** logistic 分支——新增/切换倾向估计器属于 A 阶段配置变更，不能由 D 阶段代码
  单方面决定。这里只把差距写清，并把"换 primary 口径要重跑哪些数字"列为 E 阶段待办：
  `dr_ate_training`、DR-learner 的 τ̂ 与验证集 LCB、观察性常数模型的 ATE、
  以及 §13 的 `dr_estimated_*` 三列。

### 7.2 其余口径选择

1. **没有 early stopping。** `models.yaml` 只给固定 `n_estimators=300`，本模块不使用验证集早停
   （也避免把验证集用于拟合）。
2. **DR 的倾向模型在随机化层默认也按配置估计**（`propensity_model: lightgbm_classifier`），
   默认口径没有替换成已知设计概率——这是对冻结配置的忠实执行，其"效率保守下界"的含义见
   §2.2；设计概率在默认路径只用于验证集 DR 打分（`evaluation.randomized_propensity`），
   只有显式 `known_design` 敏感性路径才把它交给 DR 的 e（§2.4）。默认仍走 LightGBM，也意味着
   §7.1.2 的 `primary: logistic` 差距依旧存在。
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
| 失败要响 | 未知模型 / 层不适用 / 特征越界 / 配置口径漂移 / 预算为负 / 倾向得分越界 / 倾向来源非法 全部抛异常 |

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
8. **C7 的敏感性对照不是正式效率结论。** 受"机器上同时有 4 个正式 AA 作业、可用内存约 4 GB"
   约束，只做了 2 个随机化场景 × R=3 × n=20,000（训练池 10,000）；没有跑正式 R（200–500），
   也没有换 L0/L2 的其他分流比例。§13 的比值只能读成"这个规模下的点估计对照"。
9. **C7 的比值没有区间。** `SE_DR/SE_ITT` 是点比值，未做 bootstrap 或 delta-method 置信区间；
   `crossfit_dr_ate` 的 SE 本身仍是 `sd(ψ)/√n` 的影响函数近似、未校正 nuisance 二阶项，
   因此 §13 的比值不应当作"效率差的显著与否"，只能当作方向与量级的证据。
10. **`propensity.primary: logistic` 仍未实现**（§7.1.2）。这是配置声明与实现的差距：本轮
    按边界只披露，不改冻结配置、不新增未注册的 logistic 分支；因此 D.3 的 DR 数字全部是
    **LightGBM 倾向口径**。
11. **L3 不存在 `known_design` 对照，也不该有。** 观察性层没有已知设计概率，任何"L3 用设计
    概率"的对照都是错的；本模块用 `PropensitySourceError` 把它堵死，而不是造一个假对照。
12. **C7 没有测"截断触发对 DR 偏倚的实际大小"。** 只落地了诊断字段 + 触发实验（证明计数与
    标记会响），没有在同一份极端数据上量化"截断前后 ATE 差多少"——那需要一个专门的偏倚
    蒙特卡洛，属 E 阶段。

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
   61 项可独立作为本模块回归门禁。`known_design` 只能显式开启，且只在随机化层有效。

---

## 12. 复现命令

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
cd 'D:\L\practice_project\营销数分项目'
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m pytest tests\test_v3_models.py --basetemp=out\c7_tmp   # 61 passed
.\.venv\Scripts\python.exe -m causal_growth.estimate.v3_models                       # 冒烟表（5 模型）
.\.venv\Scripts\python.exe -m causal_growth.estimate.v3_models --sensitivity --n 20000 --reps 3
# ↑ C7 效率对照；产物：outputs/tables/v3_phase_D_models_sensitivity.csv
```

数据来源：合成数据 / 已知 DGP，`L1_main`，`project.master_seed = 20240101`，rep 0，
**正式重复 R = 0**。冒烟数字见 `outputs/tables/v3_phase_D_models_smoke.csv`；
C7 敏感性对照见 `outputs/tables/v3_phase_D_models_sensitivity.csv`（R=3，n=20,000，非正式重复）。

---

## 13. C7 敏感性对照：估计倾向 vs 已知设计概率（效率对照，不是正确性对照）

**问题**：随机化层本来就知道设计概率，D.3 却用 LightGBM 估计 e。这个选择损失了多少效率？
差的是 SE 还是 ATE？

**口径**（`run_propensity_sensitivity`，命令见 §12）：

- 两个**随机化**场景：`L1_main`（设计概率 0.5）与 `L2_n30000_p010`（设计概率 0.1，
  故意选一个非 0.5 的分流比例）；
- 每场景 R=3、n=20,000（OOF 拆分后训练池 10,000），单线程（`n_jobs=1` +
  `OMP/OPENBLAS/MKL_NUM_THREADS=1`），折号与 `random_state` 由 `child_seed` 派生；
- 三个估计量消费**同一训练切分**：① 未调整 ITT（`itt_estimate`：两组均值差，
  `se = sqrt(s1²/n1+s0²/n0)`）；② DR（`estimated`，现状）；③ DR（`known_design`，新增）；
- ②③ 在同一次 `seed_index` 下共享折号与折外 `m1/m0`（§2.4 规则 4），**只有 e 不同**；
- **不读任何真值列**，表里也没有真值列；ITT 只作为随机化层的无偏基准，不是真值。

产物 `outputs/tables/v3_phase_D_models_sensitivity.csv`：**8 行 × 44 列**（2 场景 ×［3 个
逐 rep 行 + 1 个均值行］）；种子全部由 `child_seed` / `child_rng` 派生，本表不含 CPU 秒列。
**确定性实测**：同一命令独立重跑两次，CSV 的 SHA-256 都是
`2897ba589e8680ce5a9a7cf48430152a2a0e9b1b2f3e64309dce0ef6ddd02d63`（逐元素复现）。

### 13.1 均值行（R=3 的算术平均；逐 rep 行见 CSV）

| 场景 | 估计量 | ATE | SE | SE / SE_ITT | e 均值 | e raw 范围 | 截断数 |
|---|---|---|---|---|---|---|---|
| `L1_main`（p=0.5） | 未调整 ITT | 0.2836 | 0.2053 | 1.000 | — | — | — |
| `L1_main` | DR（estimated） | 0.4134 | 0.2312 | **1.126** | 0.4975 | 0.0912–0.9002 | 0 |
| `L1_main` | DR（known_design） | 0.3894 | 0.2012 | **0.980** | 0.5000 | 0.5000 | 0 |
| `L2_n30000_p010`（p=0.1） | 未调整 ITT | 0.3190 | 0.3689 | 1.000 | — | — | — |
| `L2_n30000_p010` | DR（estimated） | 1.2323 | 1.1371 | **3.083** | 0.0976 | 0.00185–0.6944 | 119（68–147/rep） |
| `L2_n30000_p010` | DR（known_design） | 0.2540 | 0.3751 | **1.017** | 0.1000 | 0.1000 | 0 |

ATE 差（均值行）：`L1` estimated **+0.1298**、known **+0.1058**（ITT SE 0.2053）；
`L2` estimated **+0.9133**、known **−0.0650**（ITT SE 0.3689）。

### 13.2 逐 rep 的 SE 比值（稳定性）

| rep | L1 estimated | L1 known | L2 estimated | L2 known |
|---|---|---|---|---|
| 0 | 1.101 | 0.973 | 3.046 | 1.003 |
| 1 | 1.138 | 0.989 | 3.195 | 1.048 |
| 2 | 1.138 | 0.979 | 3.008 | 0.999 |
| 3-rep 均值 | **1.126** | **0.980** | **3.083** | **1.017** |

### 13.3 读法

1. **known_design 贴着 ITT**：ATE 差 +0.106（L1，0.52 个 ITT SE）与 −0.065（L2，0.18 个
   ITT SE），SE 比 0.980 与 1.017。用真 e 时 DR 既不丢效率也不产生可见偏移——这正是
   "e 正确时 AIPW 是有效估计量"的预期表现，也说明本实现没有把设计概率用歪。
2. **estimated 的代价随分流比例急剧放大**：p=0.5 时 SE 只贵 12.6%（逐 rep 1.10–1.14），
   与独立评审报告"L1 的 DR ATE SE 是 ITT 的 1.10 倍"**同向、同量级**；p=0.1 时贵 3.08 倍。
   机制清楚：p 越小，estimated e 的 raw 下界越接近 0（本对照最低 0.0018），68–147 个观测
   被截断到 0.01，`1/e` 权重爆炸既放大方差，也让单 rep 的 ψ 重尾——L2 的 ATE 点估计被推到
   1.23（比 ITT 高 0.91 ≈ 2.5 个 ITT SE），不是一个可用的效率点。
3. **"两者都应接近 ITT"只在 known_design 上稳健成立**；estimated 在 p=0.5、训练池 10,000
   时大致成立（差 0.63 个 ITT SE），小分流比例下点估计也会跑偏。这是**效率问题在有限样本
   里的表现**，既不能读成"estimated DR 有系统偏倚"，也不能读成"known_design 更准"——本对照
   没有真值，不回答正确性。
4. **对默认口径的含义**：C7 没有改变任何默认行为；它把"随机化层报告 DR 效率是保守值"
   从一句话变成可复算的两个比值。E 阶段若要用 known_design 作为主口径，必须先改配置
   （注册与默认值）并同步处理 §7.1.2 的 `primary: logistic` 差距，否则就是第三次
   "配置声明与实现不一致"。

### 13.4 这张表不能回答什么

- **不是效率结论的正式凭据**：R=3、单训练池规模（10,000）、SE 为影响函数近似、比值没有
  置信区间（§9 第 8–9 条）；正式效率评估要在机器空闲时用正式 R 与 bootstrap 重跑。
- **不能外推到真实数据**：`known_design` 需要逐人设计概率真值，只有合成数据/随机化实验
  才有；真实观察性数据没有这个量，本对照只回答"如果 e 已知，DR 能好多少"。
- **不含 L3**：观察性层没有已知设计概率，传 `known_design` 会抛
  `PropensitySourceError`（§2.4 规则 2），所以这里没有也不该有 L3 的 known_design 对照。

> 增补时间：2026-10-25 15:42（北京时间）：按独立科学评审 C8 修正三处表述。

---

## 14. D03 provisional 逐用户导出（2026-10-27 11:30，北京时间）

本节回答"D03 的交付物到底是什么"：**不是模型结果表，而是 E 阶段固定 9 列 CSV**。

### 14.1 契约与真值隔离

`D03_EXPORT_COLUMNS` 与 `scripts/21_e_policy_run.py` 的 `REQUIRED_COLUMNS` 完全一致：

```
user_id, is_new, cart_value, purchase_propensity, predicted_profit,
tau_hat, cost_hat, tau_true, cost_true
```

- 前 7 列只由观测表与模型预测构成，**先冻结**；
- 后 2 列由 `_audit_truth_for_test()` 从 `V3Population.audit_potential_orders` 读取，
  **在选人列冻结之后才合并**；函数只返回真值两列，与特征/预测不共享对象。
- 有一条测试把真值函数替换成常数 999，断言前 7 列逐位不变（`test_d03_audit_truth_cannot_change_selection_columns`）。

`purchase_propensity` = LightGBM `P(paid_purchase_7d=1|X)`；`predicted_profit = p̂ × m̂`，
`m̂` 是训练集购买者上对 `net_profit + coupon_cost` 的回归并截 0；`cost_hat` 用 `fit_cost_model`
的期望核销成本口径（不是面额）。

### 14.2 已跑通的 provisional

命令：

```
python -m causal_growth.estimate.v3_models --export --scenario L1_main --n 20000 --rep 0
```

结果（**provisional，不是正式 R**）：

| 项 | 值 |
|---|---|
| 场景 / rep | L1_main / 0 |
| n_total / test | 20 000 / 6 000 |
| 拟合模型 | constant, t_learner, s_learner, causal_forest, dr_learner |
| 选模 | `causal_forest`（验证集预算网格 LCB 均值 −0.1159；5 个模型 LCB 全为负） |
| CSV | `outputs/tables/v3_phase_D03_predictions_provisional.csv`（逐用户表，不入库） |
| 元信息 | `outputs/tables/v3_phase_D03_predictions_provisional_meta.json`（含 sha256、选模排名、全哈希） |
| E 编排 | 72 行 = 8 预算 × 9 策略；受约束策略按 `cost_hat` 8/8 合规 |

### 14.3 这张 provisional 表不能回答什么

1. **不是正式 R**：单 rep、单场景，`status=provisional`，`formal_r=false`；不能据此写任何模型优劣或策略收益结论。
2. **τ̂ 有明显高估**：test 集 `tau_hat` 均值 0.514 vs `tau_true` 均值 0.202（约 2.5 倍）。这可能是选模/模型偏差或单 rep 噪声，**必须由正式 R 与多 rep 诊断回答**，不能在这里下判断。
3. **验证集 LCB 全为负**：说明在该 rep 的验证集上，5 个模型按预算选人的 DR 下界都不支持正收益；这不等于"发券一定亏"，但足以阻止把它写成正结果。
4. **期望成本不是硬上限**：`greedy` 两策略按 `cost_hat` 8/8 合规、按 `cost_true` 只有 3/8 合规。这正是 `policy.yaml` 里 `hard_cap_claim_allowed: false` 的现场表现，不能把"期望不超"改写成"实际不超"。
5. **逐用户 CSV 不入库**：按 `.gitignore` 的逐用户表规则只保留 meta（含 sha256）。复现只需上面的命令。
