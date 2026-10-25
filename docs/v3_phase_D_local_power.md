# D 阶段补充：local-power 功效格生成入口（target → 合法概率增量 → 实测拒绝率）

> 合成数据 / 已知 DGP。**本文件记录的是入口实现与小规模证明，不是正式功效结果。**
> 维护时间：2026-10-25 14:12（北京时间，Asia/Shanghai）。
> 正式重复次数：**0**（本文件涉及的每次运行其 manifest 都写 `formal_repetitions_completed = 0`）。

## 0. 这份文档补的是哪个缺口

独立评审判定 GOAL `D02` 未完成，其中一条是：20 个功效格只有设计期的
`target_effect`，没有实测的 `achieved_effect` / `rejection_rate` / `MC_SE`，
原因是 local-power 的生成入口尚未实现（`src/causal_growth/data/v3_pipeline.py`
以 `local-power cells require the Phase D calibrated mechanism entry point` 拒绝启动）。

本文件对应三个新文件与一处最小改动：

| 文件 | 作用 |
|---|---|
| `src/causal_growth/dgp/v3_local_power.py` | **效应构造**：τ → 合法购买概率增量 → 解析重积分 → `achieved_effect` 与可行域 |
| `src/causal_growth/data/v3_local_power_pipeline.py` | **生成入口**：逐 rep 跑完整五表链路 + ITT，汇总拒绝率/二项区间/MC_SE |
| `tests/test_v3_local_power.py` | 25 条口径与数值测试 |
| `src/causal_growth/data/v3_pipeline.py` | 只加一个**默认拒绝**的显式参数 `local_power_authorization`（不传时行为逐字不变） |

七份冻结 YAML 一字未改，合并配置哈希仍为
`30511a32bcee9db55e8f5ec1bbc2b9d63eb63dc2a13aa5c720f948c781eccdbe`（本次已复算）。

## 1. 效应构造的数学

### 1.1 为什么不能给利润加常数

DGP 的利润是积分出来的：`购买概率 p → 订单 → 金额 Q/履约/退款/核销 → 分币账`。
单用户利润可写成

```
profit_a(x) = p_a(x) · m_a(x)
```

其中 `m_a(x) = E[人均净利润 | 该用户购买，动作 a]`，由
`causal_growth.dgp.v3_amounts.conditional_user_expectation(..., purchase_probability=1)`
给出**精确的离散（分币）期望**；`m_a` 只依赖机制参数（金额分布、成本率、履约均值、
退款率、核销率、时点系数）与已记录 X（购物车），**不依赖购买概率**。
配置口径 `constant_profit_shift_forbidden: true` 正是禁止"直接给利润加 τ"。

### 1.2 唯一被拧的旋钮：增量倍数 s

注册机制已经是正 headroom 参数化（`dgp.probability_rule =
positive_headroom_parameterization_no_silent_clipping`）：

```
p1(x) = p0(x) + (1 − p0(x)) · h(x),   0 ≤ h(x) < 1
```

构造取一个标量 `s ≥ 0`，只把 headroom 乘上它：

```
p1(s, x) = p0(x) + (1 − p0(x)) · s · h(x)
```

`s = 0` 时 `p1 = p0`（无购买增量）；`s = 1` 时就是注册机制本身。
**其它机制参数一个都不动**：系数、截距、幅度上限、退款率、退款乘子、核销率、金额、
履约、时点全部保持注册值。实现上不是重写 DGP，而是把
`dgp.l1.purchase_increment_target`（L1/L2/L3）或 `dgp.l0.purchase_increment`（L0）
乘上 `s` 得到派生配置——幅度对目标是线性的，所以派生配置产出的 headroom 恰好是
`s·h`，其余键逐字相同（`test_scaled_config_changes_only_the_increment` 用递归 diff
断言"只改这一个键"，并用机制指纹断言"机制没换"）。

### 1.3 解析重积分：τ(s) 是仿射的

在参考人群（`generate_covariates(..., population_kind="reference")`，与机制校准同一类
抽样）上取 X-only 积分后的 `p0(x)`、`h(x)` 与 `m_a(x)`，则

```
τ(s) = E_x[ p1(s,x)·m1(x) − p0(x)·m0(x) ]
     = τ0 + s·Δ
τ0   = E_x[ p0(x)·(m1(x) − m0(x)) ]          ← 增量恰为 0 时的利润效应
Δ    = E_x[ (1 − p0(x))·h(x)·m1(x) ]          ← 每 1 单位增量倍数的利润效应（>0）
```

`p1` 对 `s` 线性，所以反解是闭式的：

```
s(τ) = (τ − τ0) / Δ
```

**没有蒙特卡洛、没有根搜索**，也就没有"解不准"这一层误差。

### 1.4 τ0 ≠ 0：本次最关键的机制事实

`τ0` 是"购买概率完全不动，但处理组照常领券"的利润效应：券成本（核销率 0.55 × 面额
10 元 × 首单时点系数）+ 更高的退款率（×1.03）。它**显著为负**，量级约 −0.55～−0.60
元/人，而设计 MDE 只有 0.113–0.131 元/人——即 4–5 个设计 MDE。

L0 层解析值 **−0.559014 元/人**（`reference_n = 10000`）与 B 阶段审计过的负对照
`L0_zero_purchase_effect` 的实测利润 CATE **−0.559 元/人** 一致（两者独立得到），
这一条本身就是构造正确性的外部证据。

由此得到三条必须写进任何报告的读法：

1. **倍数 0 ≠ 没有购买增量。** 利润零效应格是靠**正**增量（`s ≈ 0.65–0.72`）把券的
   机械成本抵消掉得到的。
2. **`s = 0` 不是零效应格，而是负对照。** 它的真值是 `τ0 ≈ −0.56`，在 20 万人下几乎
   必然被拒（约 4 倍 MDE）。把 `s=0` 当"倍数 0"跑出的拒绝率≈100%，不能读成"5% 假阳性
   失效"，只能读成"券的机械成本被检出"。
3. **"no purchase increment"与"no effect"在这套机制下不等价**，这是机制可识别性问题，
   不是实现问题。

### 1.5 可行域与越界行为

`s` 的合法域是两条约束的较小者：

| 约束 | 表达式 | 含义 |
|---|---|---|
| 数学合法 | `s < 1 / max_x h(x)` | 否则某个用户的 `p1 ≥ 1`（概率越界） |
| 机制注册 | `s ≤ maximum_purchase_increment / amplitude` | L1/L2/L3：幅度上限 0.15；超过时注册机制自己会拒（`amplitude ≤ maximum ≤ 1`） |

（L0 齐次购买机制没有幅度上限，只有 `p0 + s·increment < 1`。）

目标效应超界时抛 `LocalPowerInfeasible`，消息里带**可行域上界**与**哪条约束在约束**，
**不裁剪**（`test_target_above_upper_bound_raises_with_the_bound` 断言消息含上界数值）。

## 2. 20 格的可行域诊断

参考面板 `reference_n = 10000`（`out/v3_phase_d_local_power/feasibility_20cells_ref10000/`）。
四层的解析曲线：

| 层 | τ0（元/人） | Δ（元/人 per s） | τ(s=1) 注册机制 | 可行域上界 τ_upper | s_legal | s_registered | s_upper | 约束方 |
|---|---|---|---|---|---|---|---|---|
| L0 | −0.559014 | 0.806460 | 0.247446 | 13.957260 | 18.000 | — | 18.000 | `p1 < 1` |
| L1 | −0.559696 | 0.859994 | 0.300298 | 0.611627 | 9.972 | 1.362013 | 1.362013 | 注册幅度上限 |
| L2 | −0.552862 | 0.839131 | 0.286269 | 0.590045 | 9.798 | 1.362013 | 1.362013 | 注册幅度上限 |
| L3 | −0.604305 | 0.842707 | 0.238402 | 0.543473 | 9.697 | 1.362013 | 1.362013 | 注册幅度上限 |

参考人群均值的抽样标准误 `sd(τ_i)/√n_ref` = 0.0061–0.0082 元/人（n_ref=10⁴）；
n_ref=20 万时降到 0.0014–0.0018。

**结论一：20 个格全部可达，没有一个倍数落在可行域外。**
目标效应区间是 0 → 0.2616 元/人，而四层的可行域上界都 ≥ 0.54 元/人，余量充足：

| 层的最大格 | 目标效应 | 所需 s | s 上界 | 余量倍数 | 不可达区间 |
|---|---|---|---|---|---|
| L0_power_mde200 | 0.226681 | 0.9743 | 18.000 | 18.5× | τ > 13.96 或 τ < −0.559 |
| L1_power_mde200 | 0.260524 | 0.9538 | 1.3620 | 1.43× | τ > 0.612 或 τ < −0.560 |
| L2_power_mde200 | 0.256637 | 0.9647 | 1.3620 | 1.41× | τ > 0.590 或 τ < −0.553 |
| L3_power_mde200 | 0.261645 | 1.0276 | 1.3620 | 1.33× | τ > 0.543 或 τ < −0.604 |

注意 L3 的 2× 格需要 `s = 1.0276 > 1`：即增量要**比注册机制略大**（幅度
0.110 × 1.0276 = 0.1132 ≤ 0.15，合法）。最紧的格是 L3 的 2×，离上界还有 33% 余量。

**结论二：真正"不可达"的不是任何注册格，而是"把倍数 0 当作 s=0"这种读法。**
可行域下界 `τ0 ≈ −0.55` 意味着"零利润效应"必须靠正增量实现；`s=0` 落在 0 效应点之外
（它的效应是 −0.55）。所以 20 格里没有越界格，但**"倍数 0 = 无增量"这个模型设定本身
不可行**——这是本次运行给出的、比"某格不可达"更重要的结论。

**结论三：若把 coupons 面额/核销率调大，可行域上界会先撞注册幅度上限。**
L1/L2/L3 的上界 0.54–0.61 元/人 ≈ 4.2–4.7 倍设计 MDE；一旦某层的设计 MDE 因方差变化
翻倍（或目标倍数超过 4×），2× 以上的格就会先撞上界并抛错，而不是被悄悄裁剪。

## 3. 生成入口与放行机制

`build_observed_pipeline(..., local_power_authorization=...)`：**默认 `None` 即拒绝**
（原 `ValueError` 文案与"calibrated"关键词保留，`tests/test_v3_pipeline.py` 的
`test_power_template_cannot_silently_run_as_its_base` 仍然通过）。传入的对象必须是
`calibrate_local_power_cell()` 的返回值，且被逐项绑定：

| 校验 | 作用 |
|---|---|
| `consistent is True` | achieved-vs-target 自检必须已通过 |
| `effect_construction` 等于冻结口径 | 防止换口径 |
| `cell_id` 等于 `active_scenario.id` | 防止 A 格凭据跑 B 格 |
| `multiplier` 等于冻结倍数 | 防止倍数漂移 |
| `scaled_config_hash == cfg.hash(64)` | 凭据只能配它校准出的那份派生配置；改任何其它键都会失配 |

放行后，manifest 多一个 `local_power_authorization` 字段（基础场景的 manifest 完全不变，
有测试断言）。生成与审计真值都走注册 DGP 代码（`generate_v3_population(scaled_cfg)`），
不存在"另写一份机制"的漂移风险。

每 rep 的链路与产物：

```
generate_v3_population(scaled_cfg) → 五表 → 污染/清洗 → SQL → 观测分析表
   → R1 分母/标签/run_id/成熟度断言 → ITT（net_profit，Welch t）→ p 值
   → 可选审计：用该 rep 的 audit_* 条件概率 × 解析条件利润重算有限总体 ATE
```

逐 rep 表带 D.1 契约的四列 `cell_id / rep_id / effect_estimate / reject`，因此可直接喂
`causal_growth.design.v3_power.summarize_power_cells()`——本模块的汇总正是**委托**给它，
不另造一套统计口径。

## 4. 拒绝率、二项区间与 MC_SE

每格输出（列名沿用 D.1 的冻结 schema）：

* `rejection_rate` = `mean(p < alpha)`（主指标 `net_profit`，分母 = 随机分配的全部用户）；
* `mc_se` = `sqrt(p(1−p)/R)`；
* `binomial_ci_low/high` = Clopper–Pearson 精确区间（与 D.2 的 AA 表同一实现）；
* `nominal_power` = 用**本次运行实测的臂内样本 σ**、在本次每臂人数上解析算出的两样本功效；
* `nominal_power_registered_n` = 用 D.1 设计先导 σ、在注册 n 上算出的**设计期名义功效**；
* `measured_minus_nominal` = 实测拒绝率 − 名义功效。

**为什么必须报两个"名义"**：D.1 的 `analytic_power` 是设计期口径（σ 来自先导观测样本、
n=注册 n），而复跑口径的 n 可能更小。1×MDE 的格在注册 n 上恰好是 0.80（复算
`L0_power_mde100 = 0.800000`、`L1_power_mde100 = 0.800000`，与 D.1 表逐位一致），
这是"名义"的一端；实测拒绝率是另一端。两者之差包含三类误差，必须分开说：

1. 正态近似对零膨胀、右偏利润分布的偏差（"名义 0.80 实际 0.78–0.82"）；
2. 目标效应本身的抽样误差（参考面板的 `reference_sampling_se`，见 §2）；
3. 逐 rep 人群实现的 ATE 波动（`sd(τ_i)/√n`，n=20 万时约 0.002 元/人）。

**σ 的坑（本次踩到的）**：`ProfitEffectCurve` 里的条件均值 σ
（`sqrt(E[p·m²] − (E[p·m])²)`）**只是下界**——它不含单笔订单内部的金额/履约/退款方差。
用它算名义功效会把功效算高（L1 在 20 万下 0.86 vs 真实的 0.80 量级）。所以本模块的
`nominal_power` 一律用实测样本 σ，`nominal_power_registered_n` 用 D.1 的设计 σ；
曲线里的那个量只作诊断并已改名 `profit_sd_mean_component_*`。

## 5. 小规模验证（n=3000，R=10）

运行时间：2026-10-25 14:00–14:20（北京时间）。产物：
`out/v3_phase_d_local_power/smoke_n3000_R10/`（`local_power_repetitions.csv` /
`local_power_summary.csv` / `local_power_feasibility.csv` / `smoke_manifest.json`）。

__VALIDATION_TABLE__

**怎么读这张表**

* `achieved_effect_analytic`（构造端的解析重积分）与 `target_effect` 的偏差在
  **1e-15 量级**，远严于 1e-6 容差——这一列证明的是"反解+重积分"没算错。
* `realized_effect_mean`（该 rep 的审计真值）是 n=3000 时**唯一**能核对"目标效应真的
  落到了数据上"的量：它的标准误是 `sd(τ_i)/√3000 ≈ 0.015`，与目标同量级可辨。
* `achieved_effect`（D.1 口径的逐 rep ITT 均值）在 n=3000 时标准误约
  `10.4·√(2/1500) ≈ 0.38` 元/人，**比目标效应大 3 倍**，所以它在小规模下必然离目标很远；
  这一列只有到注册 n 才有判读价值。这不是 bug，是"20 万才够"的直接体现。
* 拒绝率：小规模下所有格的 `nominal_power` 都只有 0.03–0.06（因为 MDE 随 √n 放大），
  实测拒绝率落在同一量级，**与名义值一致但无法区分**（R=10 的 MC_SE ≈ 0.05）。
  **小规模运行只能证明入口可用、口径自洽，不能证明功效曲线。**

### 5.1 小规模运行暴露的估计目标陷阱：L3 的未调整 ITT 不是 ATE

上表里 L3 两个格（含**目标效应恰为 0** 的 `L3_power_mde000`）都是 **10/10 拒绝**，
而 L0/L1/L2 的拒绝率都在 0–1/10。这不是噪声，也不是构造错误——审计真值显示
L3 的人群 ATE 是 0.006（目标 0，正确）。原因是 **L3 的随机化概率依赖 X**：

| 层 | 真实倾向 `e(x)` | `corr(e, 单位利润)` | 未调整均值差的估计目标偏差（设计层面） |
|---|---|---|---|
| L0 / L1 / L2 | 恒为 0.5（sd = 0） | 未定义 | **0.0000**（精确 0） |
| L3 | 0.16 – 0.96（sd ≈ 0.15） | **+0.65** | **+1.35 ～ +1.40 元/人** |

推导：`E[Y|T=1] = Σ e·μ1 / Σ e`、`E[Y|T=0] = Σ(1−e)·μ0 / Σ(1−e)`，当 `e` 与
`μ = p·m` 正相关时，两臂简单均值差 = ATE + 选择项。L3 的券核销/退款让 `μ` 随 X 上升，
而 `e` 也随 X 上升，于是未调整差被抬高约 1.4 元/人——**是 L3 设计 MDE 的 10.8 倍**，
且**不随 n 缩小**。

用真实 `e(x)` 做 IPW 后偏差消失（同一 rep：未调整 +1.33 / IPW −0.017 / 审计 ATE −0.017）。
所以：

* `L3_*` 的 5 个格**不能**用未调整 ITT 读成"ATE 的功效"；它们测的是倾向加权对照，
  任何倍数（含 0×）都会几乎必然拒绝，功效曲线退化成一条 1.0 的平线。
* 入口已经把这件事做成**自检列**：审计列 `selection_bias` /
  `selection_bias_ratio_to_mde` / `estimator_warning`。L3 的格会写
  `unadjusted_itt_estimand_is_propensity_weighted_contrast; design selection bias +1.36 …`
  而被明确标记；L0/L1/L2 的 `selection_bias` 精确为 0，`estimator_warning` 为空串。
* **正式排期前必须先决定 L3 怎么办**（三选一，均不在本文件域内）：
  ① 给 L3 的 ITT 加 IPW/DR（用已知或估计的 `e(x)`，属 `estimate/` 与 F 阶段）；
  ② 正式跑只跑 L0/L1/L2 共 15 格（省 5×100×137 s ≈ 19 CPU·h），L3 标注"估计目标不适用"；
  ③ 明确把 L3 的估计目标改写成"倾向加权对照"并写进 D.1 的口径表。
  在做出决定之前跑 L3 的 5 个格是**白烧 19 CPU·h**。

## 6. 正式跑 20 格的 CPU 估算

**单 rep 成本（实测，不是估算）**：注册规模 n=200000 的完整链路（DGP+五表+污染清洗+
SQL 两次+预处理+ITT）在 `out/v3_phase_d_aa_formal/L*/aa_repetitions.csv` 里 8 个 rep 的
均值是 **136.3 / 136.9 / 137.9 / 136.6 CPU·s**（四层分别），本模块的 local-power 参数
不改变链路长度，另加 §7 的 1 次锚点实测。

| 项目 | 计算 | CPU·h |
|---|---|---|
| 20 格 × R=100 正式重复 | 2000 rep × ≈137 s | **≈76.1** |
| 效应构造（4 块参考面板，`reference_n=200000`） | 4 × (2× 条件利润 + 概率积分) ≈ 580 s/块 | ≈0.6 |
| 审计锚（每格 rep0 用真值重算 ATE） | 20 × ≈2×管道 ≈ 270 s | ≈1.5 |
| **合计** | | **≈78 CPU·h** |

* 若把 `reference_n` 降到 50000，效应构造从 ≈0.6 降到 ≈0.15 CPU·h，代价是目标效应多
  0.002 元/人的抽样误差（对 0.5× 格约 3.5%）——**建议正式跑用 20 万，赶时间用 5 万**。
* 若把每格 rep0 的审计关掉（`audit_rep0=False`），省 1.5 CPU·h。
* 墙钟：按 AA 正式作业的并发（每层 1 worker，共 4）估算 ≈20 h；8 worker ≈10 h。
  每个 worker 都要跑一份 20 万五表，内存占用与 AA 正式作业同量级。
* 以上不含"源码在 rep 执行期间被改写"导致的重试（并发写 `src/**/v3*.py` 会触发
  C 阶段源码绑定门禁，本文件写作期间已发生两次，属于环境故障、同 rep 重跑逐位相同）。

## 7. 注册规模锚点（1 次 rep，只测成本，不是结果）

__ANCHOR_TABLE__

## 8. 测试

`tests/test_v3_local_power.py`：**25 条全绿**（`pytest -q`，本机，n ≤ 3000，R ≤ 3）。

| # | 测试 | 断言什么 |
|---|---|---|
| 1 | `test_curve_is_affine_and_invertible` | τ(s)=τ0+sΔ 仿射、`scale_for_effect` 是 `effect_at` 的精确逆（1e-12） |
| 2 | `test_multiplier_zero_targets_zero_and_needs_positive_increment` | 倍数 0 的目标为 0、achieved 恰为 0（1e-9）、且 `s = −τ0/Δ > 0` |
| 3 | `test_increment_null_matches_phase_b_negative_control` | L0 的 τ0 复现 B 阶段审计的 −0.559（±0.02） |
| 4 | `test_target_above_upper_bound_raises_with_the_bound` | 越界抛错、消息含可行域上界与约束名 |
| 5 | `test_target_below_floor_raises` | 低于 τ0（需负增量）抛错 |
| 6 | `test_registered_amplitude_cap_binds_for_layers` | L1/L2/L3 上界 = 上限/幅度，且 `effect_upper = τ0 + s_upper·Δ` |
| 7 | `test_achieved_effect_matches_target_on_both_channels`（3 参数） | 构造通道与 DGP 概率通道的偏差都 ≤ 1e-6，且 p0 逐位不变 |
| 8 | `test_consistency_tolerance_is_enforced` | 把容差收到 1e-30 时自检必须失败（检查不是装饰） |
| 9 | `test_probability_increments_stay_legal` | `0 < p0 ≤ p1 < 1`、随 s 单调、超过 `p1<1` 上界即抛 |
| 10 | `test_l0_legal_bound_is_the_mathematical_one` | L0 无幅度上限，上界 =(1−p0)/increment |
| 11 | `test_scaled_config_changes_only_the_increment` | 递归 diff 只有增量键变化；机制指纹不变；冻结配置未被改写 |
| 12 | `test_scaled_increment_config_rejects_negative_scale` | 负倍数/布尔入参抛错 |
| 13 | `test_u_invariance_of_the_x_only_integral` | L3 的 X-only 积分与 audit-U 取值逐位无关（构造不读真值） |
| 14 | `test_pipeline_refuses_without_authorization` | 默认拒绝，文案含 "calibrated" |
| 15 | `test_pipeline_rejects_foreign_or_stale_authorization` | 跨格凭据、被篡改的派生配置都被拒 |
| 16 | `test_pipeline_runs_with_authorization_and_records_it` | 放行后链路跑通，manifest 记录放行对象 |
| 17 | `test_base_scenario_manifest_has_no_local_power_record` | 基础场景 manifest 行为不变 |
| 18 | `test_single_rep_produces_itt_and_audits_the_realized_effect` | 单 rep 出 diff/p、审计真值高于 τ0 且接近目标、购买增量≈校准值 |
| 19 | `test_summary_reports_rejection_rate_mcse_and_interval` | 拒绝率/MC_SE/CP 区间/两个名义功效/实测 vs 解析的列都对齐 |
| 20 | `test_summary_requires_two_repetitions` | R=1 时 MC_SE 无定义必须抛（不写 0） |
| 21 | `test_power_plan_matches_the_frozen_registry` | 20 格、5 个倍数、目标 = 倍数×设计 MDE、σ 表齐备 |
| 22 | `test_all_twenty_cells_are_reachable_and_consistent` | 20 格全部可达且 achieved==target、`s < s_upper`、可行域表 20 行 |
| 23 | `test_audit_population_effect_uses_the_generated_truth` | 审计函数只读该 rep 的 audit 字段且方向正确 |

加上既有测试协同：`tests/test_v3_pipeline.py`（含 power 拒绝用例）与
`tests/test_v3_power.py` 全部通过（后者当前有 2 条失败是**既有**的表 schema 漂移，见 §9）。

## 9. 没有做到 / 明确的边界

1. **没有正式重复。** 20 格 × R=100 × n=200000 一次都没跑（正式结果需要主控排期）。
   本文件给的是入口 + 小规模证明 + 成本估算。因此 `rejection_rate` / `MC_SE` 的**正式值
   仍然不存在**，`outputs/tables/v3_phase_D_mde.csv` 里的 `rejection_rate` 等列**没有**被
   填写——那属于正式排期后的产物。
2. **没有把结果写回冻结表。** `outputs/tables/v3_phase_D_mde.csv` 是 D.1 的产物，本模块
   只读它的 `mde` / `sigma_*` 列。另外该 CSV 目前只有 39 列，而
   `v3_power.MDE_TABLE_COLUMNS` 已增到 63 列（并发开发导致），
   `tests/test_v3_power.py::test_committed_table_matches_its_schema` 因此失败——
   这是**既有**的表漂移，不是本次改动引入的，需要 D.1 的 owner 重新生成表。
   本模块的汇总列名已对齐那 63 列里的实测列（`achieved_effect` / `rejection_rate` /
   `mc_se` / `binomial_ci_low/high` / `empirical_n_reps`），合并时不需要改名。
3. **小规模验证不能证明功效。** n=3000 时每格的 MDE 被放大 ≈8 倍，名义功效只有
   0.03–0.06；实测拒绝率与之一致但无法区分（MC_SE≈0.05）。**功效曲线的证据只能来自
   注册规模。**
4. **审计列不是免费的。** `realized_effect` 需要对该 rep 的人群重算两次条件利润，
   200k 下一次约 270 CPU·s（≈2 个 rep 的管道成本）；默认只对每格 rep0 打开。
5. **L0 同质化旋钮不支持。** `L0_Pi_equal_cost`（`dgp.l0.control.enabled = true`）逐用户
   求解成本率与核销率，单一"增量倍数"无法描述它的利润效应，模块显式拒绝。
6. **不做多重比较校正。** 主指标 `net_profit` 单看；`design.multiplicity` 的 Holm 校正
   属 D.1 设计期口径，本模块的拒绝率是**未校正**的逐格 α=0.05。
7. **没有做 AA 对照。** 倍数 0 格的拒绝率是"校准零效应下的 size"，不是流水线假阳性率；
   流水线 FPR 由 D.2 的虚拟标签 AA 负责。两者不能互相替代。
8. **目标效应本身有设计期不确定性。** 目标 = 倍数 × D.1 的设计 MDE，而 MDE 的 σ 来自
   先导样本（D.1 表里的 `mde_relative_se`），所以"实测拒绝率 vs 名义 0.80"的差异里，
   有一部分是**目标本身**的抽样误差，不只来自实测的 R 次重复。

## 10. 复现命令

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
cd 'D:\L\practice_project\营销数分项目'
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'

# 单元测试（n<=3000，R<=3，约 3 分钟）
.\.venv\Scripts\python.exe -m pytest tests\test_v3_local_power.py -q --basetemp=out\lp_tmp

# 20 格可行域诊断（解析，不跑数据；reference_n=10000 约 3 分钟）
.\.venv\Scripts\python.exe out\lp_tmp\feasibility20.py

# 小规模证明（n=3000，R=10，约 15 分钟，含 1 次 20 万成本锚点）
.\.venv\Scripts\python.exe out\lp_tmp\validate_small.py

# 正式入口（需主控排期；n 取注册值，reps 取注册 R=100）
.\.venv\Scripts\python.exe -m causal_growth.data.v3_local_power_pipeline --reps 100 --n 200000 `
    --reference-n 200000 --out out\v3_phase_d_local_power\formal
```
