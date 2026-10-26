# Phase E 策略接口（冻结版）

> 合成数据 / 已知 DGP。维护时间：**2026-10-26 13:20（北京时间）**。
> **本文件只定义接口，不含实现。** 实现与验收在 E 阶段正文。
> 口径唯一来源：`configs/v3/policy.yaml`（A 阶段冻结）。本文件不新增任何业务参数，
> 代码里也不许出现该 YAML 之外的业务常数。

## 0. 这份接口要回答什么

给定观测数据学出的 $\hat\tau(X)$ 与 $\hat c(X)$，在预算 $B$ 下选哪些用户发券，
能拿到多少**净增量利润**；以及这个选择离真值最优有多远，**误差来自学习还是优化**。

两个问题必须分开回答——这是 E 阶段最容易出错的地方：

| 问题 | 对应量 | 数据依赖 |
|---|---|---|
| 我的策略有多好？（与真值最优的差距） | **truth regret** | 需要真值，只在输出冻结后 |
| 我的求解器有多好？（与预测目标最优的差距） | **predicted gap** | 只需预测值 |

**`predicted_objective_gap_separate_from_truth_regret: true`**（policy.yaml）。把两者合成一个数，
等于用"求解器够好"冒充"策略够好"，本项目明令禁止。

## 1. 冻结的口径（摘自 policy.yaml，不得改）

| 项 | 值 | 含义 |
|---|---|---|
| 动作空间 | `{0, 1}` | 二元：发 / 不发。**不做多面额**（决策 Q2） |
| 券面额 | 10.0 元 | 唯一档位 |
| 价值目标 | `net_incremental_profit_relative_to_no_coupon` | 相对"不发券"的净增量利润 |
| 预算基准 | `expected_redemption_cost` | 预算约束作用在**期望核销成本**上，不是面额 |
| 预算网格 | 0.04 / 0.1 / 0.2 / 0.3 / 0.4 / 0.6 / 0.8 / 1.0 元/人 | 8 个点，扫描用 |
| 预算总额 | `per_user_budget_times_all_target_users` | 每人预算 × 目标用户数 |
| 硬上限声明 | **`hard_cap_claim_allowed: false`** | 用期望成本约束时，**不得**声称实际支出不会超 |
| 目标函数 | `sum_predicted_net_incremental_profit` | 最大化预测净增量 |
| 成本函数 | `sum_frozen_predicted_coupon_cost` | 约束用的是冻结的成本预测 |
| 负增量处理 | `no_negative_predicted_increment_for_targeting: true` | 预测为负的人不发券（不是排序后截断） |
| 平手规则 | `deterministic_tie_break: user_id_ascending` | 任何排序都必须有确定的 tie-break |

## 2. 接口清单

### 2.1 成本模型 `v3_cost.py`

```python
@dataclass(frozen=True)
class CostModel:
    """两阶段成本模型：P(购买) × E[核销金额 | 购买]，再加辅助直接回归作对照。"""
    stage_purchase: Any        # 购买倾向模型（分类）
    stage_redemption: Any      # 条件核销金额模型（回归）
    auxiliary_direct: Any      # 直接对成本回归的辅助模型
    target: str                # 必须等于 "expected_coupon_cost_given_assigned_coupon_and_observable_features"

def fit_cost_model(learning: LearningData, cfg: Config) -> CostModel:
    """只在 training 上拟合；validation 只用于校准，不参与拟合。"""

def predict_expected_cost(model: CostModel, frame: pd.DataFrame, cfg: Config) -> NDArray[np.float64]:
    """返回逐用户的 ĉ(X)，下界 cost_floor_cny（1e-6），不得为 0 或负。"""
```

**为什么成本必须是 $\hat c = 10 \times \hat P(\text{核销})$ 而不是面额。**
用面额做预算约束会把预算高估 10 倍以上（核销率约 0.55，且只有部分人购买），
策略会选得过少、看起来"保守"，实际是口径错。这一点 v2 已经踩过，写进过复盘。

### 2.2 选择器族 `v3_select.py`

```python
@dataclass(frozen=True)
class Selection:
    mask: NDArray[np.bool_]     # 选中谁
    predicted_value: float      # 预测净增量之和
    predicted_cost: float       # 预测成本之和
    algorithm: str              # 必须是下表的合法名

def greedy_by_ratio(value, cost, budget, tie_break="user_id_ascending") -> Selection
def local_swap(initial, value, cost, budget, max_passes, exchange_candidate_limit) -> Selection
def cent_exact_dp(value_cents, cost_cents, budget_cents) -> Selection
def milp_select(value, cost, budget, time_limit_seconds, relative_gap) -> MilpResult
def lp_upper_bound(value, cost, budget) -> float
```

**名实相符（HITL 明确要求，违反即结果作废）**：

| 名称 | 允许的说法 | 禁止的说法 |
|---|---|---|
| `greedy_by_ratio` | 贪心、比值排序 | 背包、最优 |
| `local_swap` | 贪心后局部交换、局部改进 | 背包 DP、最优 |
| `cent_exact_dp` | **在分币整数化问题上**精确 | 原问题最优（浮点原问题不等价） |
| `milp_select` | 带 gap 的可行解 / 证明最优（仅当 gap=0 且 status=optimal） | "最优"（gap>0 时） |
| `lp_upper_bound` | 上界 | 可行解、策略 |

**`cent_exact_dp` 的精确性只针对分币整数化问题**（`exactness_claim_target: cent_integerized_problem_only`），
成本用 `decimal_half_up_to_cent` 取整。浮点原问题与整数化问题可能不同最优，这一句必须写进结果表脚注。

### 2.3 预算 `v3_budget.py`

```python
@dataclass(frozen=True)
class BudgetPlan:
    expected: float      # 期望核销成本预算（主口径）
    buffered: float      # expected × 1.25（显式风险缓冲，不是硬上限）
    worst_case: float    # 面额口径的紧预算（保证实际券支出不超）

def build_budget_plan(budget_cfg, n_target) -> BudgetPlan
def audit_budget(selection, observed_cost, plan) -> BudgetAudit
```

**三种预算必须分开报**（`E02`）：预期预算、实际支出、硬上限。
`hard_cap_claim_allowed: false` 意味着主口径下**只能说"期望不超"，不能说"实际不超"**；
要声称实际不超，只能用 `worst_case_face`（每人最多 10 元、人数 ≤ B/10）。

### 2.4 评估与审计 `v3_audit.py`

```python
@dataclass(frozen=True)
class ErrorDecomposition:
    learning_error: float       # 用真值策略 vs 用学到的 τ̂ 的差
    optimization_error: float   # 同一 τ̂ 下，求解器 vs 该 τ̂ 的最优
    total_regret: float         # 与真值最优的总差
    identity_residual: float    # 三者是否对得上（应接近 0）

def policy_value(mask, profit_true, baseline="no_coupon") -> float
def truth_regret(mask, truth_optimal_mask, profit_true) -> float
def decompose_error(mask, tau_hat, profit_true, truth_optimal_mask) -> ErrorDecomposition
```

**误差分解的恒等式**（实现时必须逐 rep 校验残差）：

```
total_regret = learning_error + optimization_error
```

- `learning_error`：拿学到的 $\hat\tau$ 去求**该 $\hat\tau$ 的最优**，再与真值最优比 → 纯学习误差
- `optimization_error`：同一 $\hat\tau$ 下，求解器解与最优解比 → 纯求解误差

**真值只在最后解封**（`oracle_audit.stage: after_all_observed_outputs_frozen`）。
审计模块是唯一允许读 `truth_*` 字段的入口，且必须在所有观测侧输出落盘并哈希冻结之后调用。

## 3. 候选策略（9 个，policy.yaml `candidates`）

| 名 | 依赖 | 备注 |
|---|---|---|
| `no_coupon` | 无 | 基线，价值恒 0 |
| `all_coupon_unconstrained_reference` | 无 | 参考上界，不受预算约束 |
| `random_same_budget` | 随机数 | **200 个种子**，报 mean/sd/分位数；分位数是"名单抽样的变异"，**不是均值的置信区间** |
| `business_rule_new_user_then_cart` | 规则 | 优先级：新客 → 购物车金额降序 → user_id 升序 |
| `purchase_propensity_rank` | 购买倾向 | 只看会不会买，不看增量 |
| `predicted_profit_rank` | $\hat p \cdot \hat m$ | 水平量，不是增量 |
| `incremental_profit_rank` | $\hat\tau$ | 增量，但忽略成本 |
| `greedy_incremental_profit_per_cost` | $\hat\tau/\hat c$ | 主策略 |
| `greedy_local_swap` | 同上 + 交换 | 主策略的改进版 |

后六个必须用**同一份** $\hat\tau$、$\hat c$（`all_models_share_repetition_data_and_split`），
否则比较的是"模型 + 策略"的混合效应，不是策略本身。

## 4. 小规模互证与大规摸求解（`optimization`）

### 4.1 小规模（pool 20 / 100 / 500）

五种算法跑**完全相同的目标与成本**，用于互证：

1. `greedy` —— 下界
2. `greedy_local_swap` —— 仍可能次优
3. `cent_exact_dp` —— 分币整数问题的最优
4. `milp` —— 应与之相等
5. `lp_relaxation` —— 上界

**验收要求**：`cent_exact_dp == milp`（在同一整数化问题上）；
`greedy ≤ local_swap ≤ exact ≤ lp`；若出现 `greedy > exact`，**立刻触发口径审计**（几乎必然是目标或成本不一致）。

### 4.2 大规摸（1000 / 5000 / full_test）

`time_limited_milp`：60 秒、相对 gap 0.001，必须报 **incumbent（最好可行解）+ bound（上界）+ gap + solver status**。
`require_incumbent_bound_gap_and_status: true`——只报一个目标值不算交付。

### 4.3 桶宽收敛（pool 500）

宽度 `1.0 → 0.5 → 0.1 → 0.05 → 0.01` 逐级收敛，**必须执行并出表**。
标签固定为 `approximate_bucket_dp_with_original_cost_feasibility_check`：
桶化 DP 是**近似解**，且必须用原始成本回代检验可行性（桶内可能超预算）。

### 4.4 精确反例（冻结）

`budget = 10`，成本 `[6, 5, 5]`，利润 `[12, 9, 9]`：
- 贪心按比值：6/6=2.0 vs 9/5=1.8 → 选第一件，得 **12**
- 最优：选后两件，得 **18**
- **贪心损失 33%**

这个反例是 `greedy` 不能声称"近似最优"的硬证据，必须写进 E 阶段正文。

## 5. 与验收项的映射

| GOAL | 本接口对应的交付 |
|---|---|
| **E01** 成本预测及二元策略；DP/MILP/LP 名实相符 | §2.1 成本模型、§2.2 五个求解器、§4.1 枚举互证 |
| **E02** 预期/实际/硬预算分开；学习与求解误差分开 | §2.3 三种预算、§2.4 误差分解恒等式 |

## 6. 本文件明确**不**做的事

1. **不实现任何算法**。骨架代码抛 `NotImplementedError`，只锁签名与契约。
2 不新增业务参数。所有常数来自 `configs/v3/policy.yaml`。
3. 不做多面额、不做多臂（决策 Q2 已排除）。
4. 不读真值。审计入口是唯一例外，且必须在冻结后。
5. 不承诺"贪心近似最优"。反例已经写在 §4.4。

## 7. 留给实现阶段的决定（现在不定，但必须显式记录）

| 问题 | 为什么现在不定 |
|---|---|
| `local_swap` 的候选对如何采样（全枚举还是限 500） | 影响耗时与解质量，要看池子规模实测 |
| MILP 用哪个求解器（HiGHS / CBC / SCIP） | 依赖 venv 里有什么，且要报 gap，先测可用性 |
| 桶宽收敛的验收阈值（相邻两档差多少算收敛） | 需要先看到实际曲线，不能拍 |
| `learning_error` 用哪个"该 τ̂ 的最优"（精确 DP 还是 LP 上界） | 小规模用精确 DP，大规模只能用 LP 上界并标注 |

这些不是遗漏，是**故意留到有数据再定**——按项目规矩，阈值不能先写死再凑。
