# v3 Phase D.1：固定 20 万人反算 MDE、护栏非劣效 MDE 与 20 个功效格校准

> **合成数据 / 已知 DGP**，非真实企业数据。
> 维护时间：2026-10-25 14:17（北京时间，Asia/Shanghai）。维护人：D.1 修订子代理（资深数据科学家，未参与 D.1 原产出）。
> 状态：**设计期算量（design-time）**。正式重复次数 **R = 0**；本文不含任何"检出率 / 达成效应 / 拒绝率 / 覆盖率 / MC_SE"的**实测**结论。
> 本版修订：**C4**（σ 抽样不确定性按实测峰度重算）、**C5**（`mde100` 边界格编码进表）、**C2**（护栏 `any_refund_30d` 非劣效 MDE）、**C3-部分**（实测列的汇总入口与 `pending` 标注）。
> 对应代码：`src/causal_growth/design/v3_power.py`；测试：`tests/test_v3_power.py`；数据表：`outputs/tables/v3_phase_D_mde.csv`。
> 依据：HITL《完整修订建议》§0 决策表、§7「从固定 20 万人出发评估检测能力」；`docs/v3_协议.md` §5；`configs/v3/design.yaml` 的 `mde_direction: fixed_n_inverse_power`。

---

## 0. 一页结论

**主叙述是"固定 20 万人，反算能检测多小的效应"，不是"先算需要多少人"。** 以下是反算结果。

| 问题 | 答案（20 万人、50/50、双侧 α=0.05、80% 功效，除注明外） |
|---|---|
| 利润能检测多小的增量？ | **0.113 – 0.131 元/合格用户**，占对照均值的 **5.0% – 6.4%**（四层各自不同） |
| 购买率能检测多小的增量？ | **0.363 – 0.382 个百分点**，占基准购买率的 **3.8% – 4.0%** |
| 分流改成 30/70 会更差多少？ | MDE 变成 **1.09 – 1.16 倍** |
| 分流改成 10/90 会更差多少？ | MDE 变成 **1.68 – 1.88 倍** |
| 功效要求提到 90%？ | MDE 变成 **1.157 倍**（纯 z 比值，与机制无关） |
| 改成单侧 α=0.05？ | MDE 降到 **0.888 倍**（1/1.1267）；该单侧口径沿用 α=0.05，**不是 0.025**（§2.3） |
| 辅助指标家族 Holm(m=2)？ | 购买率 MDE 放大 **10.1%** |
| 6 万测试集能检测多小？ | 利润 **0.2378** 元/人 = 20 万队列的 **1.83 倍**；购买率 **0.697 pp** |
| 额外 20 万三臂验证队列？ | 每臂约 66,667，利润 **0.1595** 元/人 = 20 万队列的 **1.22 倍**；购买率 **0.465 pp** |
| 护栏退款率（0.5pp 非劣效界值）的检测下限？ | 到界值的可检测距离 **e = 0.107–0.113 pp**（80%）/ **0.125–0.132 pp**（90%）；等价地，可检测的真实恶化 **Δ = 0.387–0.393 pp**（80%）/ **0.368–0.375 pp**（90%）（四层不同；§2.8） |
| 护栏在"train split 观测到的处理组退款率"上还有多少功效？ | **28% / 45% / 60% / ≈0%**（L0/L1/L2/L3；**以先导点估计为情景**，不是对真实功效的保证）——**重要警告，见 §2.8** |

四条最该被记住的结构性结论：

1. **总 20 万 ≠ 训练 10 万 ≠ 验证 4 万 ≠ 测试 6 万。** 同一份数据、同一个机制，仅因为能用于检验的人数不同，利润 MDE 从 0.1303 涨到 0.2913（2.24 倍）。任何"20 万能检测 X"的说法都不能挪用到 6 万测试集上。
2. **20 个功效格不是"8 个通过、12 个不通过"的二值划分，而是 8 个验不出 + 4 个边界 + 8 个有余量。** 倍数 0 与 0.5 的 8 个格在 80% 功效下验不出；倍数 1.0 的 4 个格解析功效恰为 0.8000 但**零余量**（σ 上行一个抽样误差后约 0.79），必须标为边界格；只有倍数 1.5 与 2.0 的 8 个格是"通过且有余量"。下游 gate 若只看 `detectable_at_80=True` 会把 12 个格当通过，比实际多 4 个（§8.3）。
3. **功效格的通过/不通过只由倍数决定，与层级机制无关。** 20 个格都注册为 n=200000、p=0.5，共享同一个 α 与参考功效，因此"目标效应 / 设计 MDE"这个比值是唯一的自由量。机制（σ、基准购买率、峰度）只决定"1 倍 MDE 折算成多少元"，不决定能不能检出。
4. **σ 的抽样不确定性不是"远小于 1%"。** 按实测峰度，单臂 `SE(σ̂)/σ` 为 **0.85% – 1.23%**，是正态公式 `1/√(2n)` 的 **2.7 – 3.9 倍**；`mde100` 在 σ 上行一个保守误差后的解析功效为 **0.7904 – 0.7913**，不是 0.8000（§2.7）。原稿"0.32%、远小于 1%"的表述已删除。

---

## 1. 本文回答什么、不回答什么

| 本文回答 | 落点 |
|---|---|
| 固定 n 与分流下利润/购买率的检测下限 | §4、§5 |
| 子样本（训练/验证/测试）与独立验证队列各自的检测下限 | §7 |
| 单侧与双侧、单项与 Holm 校正后联合检测能力的差别 | §6 |
| 20 个功效格需要多大的 `active_mde_multiplier` 才够、哪些是边界格 | §8 |
| 方差/峰度从哪来、为什么可以信 | §2.6、§3.4 |
| 护栏退款率对 0.5pp 非劣效界值的检测下限 | §2.8 |
| 拿到逐 rep 实测结果后，如何汇总 `achieved_effect / rejection_rate / MC_SE / 二项区间` | §8.4（入口已实现） |

**本文明确不回答**（属 D 的其它子任务与 Phase G，不得用本文数字顶替）：

- 实际检出率、达成效应（`achieved_effect`）、`rejection_rate`、`MC_SE`、二项置信区间——**CSV 里这些列全部为空，`notes` 写 `pending_local_power_entry_point`**；本文的 `analytic_power` 是设计期解析值，不是实测拒绝率；
- 覆盖率、假阳性率（那是完整 AA 的任务，走五表 + SQL + 估计流程）；
- 真值效应是多少、哪一层"应该"被检出——**本模块不读真值**，所以它无法（也不应）判断某层真实效应是否超过 MDE；
- 把目标效应翻译成"合法的购买概率增量"（`design.local_power.effect_construction` 要求先改购买概率再重新积分利润；这一步需要 DGP 积分器，见 §11）。

---

## 2. 方法与口径

### 2.1 利润 MDE（近似式）

$$\mathrm{MDE}_\Pi=(z_{1-\alpha/2}+z_{1-\beta})\sqrt{\frac{\sigma_1^2}{n_1}+\frac{\sigma_0^2}{n_0}}$$

- 实现：`profit_mde(sigma_treatment, sigma_control, n_treatment, n_control, *, alpha, power, sides)`。
- z 值用 `scipy.stats.norm.ppf` **现算**，不写 1.96 / 0.8416——手写取整在 10 万人量级上会变成可观测的 MDE 偏差。
- 这是两独立样本均值差的正态近似。利润是**零膨胀、右偏**变量（九成用户为 0，少数大额），近似是否够用不靠断言，靠蒙特卡洛核查（§2.5）。
- 逆函数 `profit_power(effect, ...)` 给出"给定效应量有多少功效"；`effect = 0` 时它返回 α/2（双侧）或 α（单侧），这正是零效应下的名义拒绝率。
- **σ 本身的抽样误差**由 §2.7 单独处理；本表的 MDE 是**点估计**，不把 σ 误差塞进 MDE 公式（那会把"估计不确定性"与"设计检测下限"混为一谈）。

### 2.2 购买率 MDE（两比例功效关系数值反解）

```
H0 标准误: se0 = sqrt(p̄(1-p̄)(1/n1 + 1/n0)),  p̄ = (n1·p1 + n0·p0)/(n1+n0)
H1 标准误: se1 = sqrt(p1(1-p1)/n1 + p0(1-p0)/n0)
功效:      power(Δ) = Φ( (Δ − z_α·se0) / se1 )
反解:      find Δ ∈ [0, 1−p0]  s.t.  power(Δ) = 目标功效   （scipy.optimize.brentq）
```

- 区间下端点 Δ=0 处功效恰为 α/2（双侧）/ α（单侧），上端点 p1=1 是概率尺度物理上界；两端点必须跨过目标功效，否则**抛错**，绝不返回 clamp 过的假值。
- 反解后回代检查功效误差（阈值随 brentq 的 `xtol` 与局部斜率缩放），不满足即抛 `RuntimeError`——根不可信时不允许静默返回。
- 落盘时记录：基准购买率 `p0`、两臂人数 `n_treatment`/`n_control`、单/双侧 `sides`、是否多重校正 `multiplicity`/`family_size`/`alpha_per_test`、反解容差（写在 `notes`）。
- 对照核查：对同一 (p0, Δ)，本模块反解出的 MDE 与既有 `sample_size_proportion` 人工反推的样本量一致到 10% 以内（单测 `test_purchase_mde_agrees_with_existing_proportion_inversion`）。

### 2.3 单侧与双侧：一个必须写明的口径缺口

`configs/v3/design.yaml` **只有主检验的 α**：`alpha_two_sided: 0.05`，没有独立的单侧 α。本表的处理是：

> **主检验的单侧行沿用同一个数值 α = 0.05**（即临界值 z₀.₉₅ = 1.6449），而不是常用的"单侧也取 0.025"。

这意味着本表的单侧 MDE 是**偏保守**的：若按严格单侧 α=0.025（z=1.9600）计算，单侧 MDE 会与双侧几乎相同，本表给出的 0.888 倍折扣就不成立。要让单侧 α 有独立取值，**必须新增配置项并重走 A 阶段评审**；本轮不擅自加参数。

**C5 要求在表里可识别这个缺口**：所有单侧 `design_mde` 行的 `alpha_one_sided = 0.05`，`sides_note = one_sided_uses_alpha_two_sided_value`。护栏行是例外：它的单侧 α 有独立配置（`design.guardrail.alpha_one_sided: 0.05`），`sides_note = guardrail_alpha_one_sided_from_config`。

同理，功效目标 80% / 90% 都来自 `design.power_targets`；配置里没有的其它功效（例如 95%）只能作为函数参数传入，且必须在报告里注明来源。本文所有数字只用配置内的两档。

### 2.4 多重校正与"联合检测能力"

| 检验族 | 成员（来自配置） | 族大小 m | 调整方式 |
|---|---|---|---|
| 确证性指标 | `multiplicity.confirmatory_metrics` = `[net_profit_30d_per_assigned_user]` | 1 | 无 |
| 辅助指标 | `multiplicity.auxiliary_family` = `[paid_purchase_7d, any_refund_30d_per_assigned_user]` | 2 | Holm |
| 策略对比 | `multiplicity.policy_comparisons` = `[targeted_vs_same_budget_random, targeted_vs_no_coupon]` | 2 | Holm |

Holm 的逐步临界值是 α/m, α/(m−1), …, α/1，**每一项都 ≥ α/m**，因此"每个 p 都 ≤ α/m"是"全部拒绝"的充分条件。设计期用 α/m 反解 MDE，得到的是 Holm **联合检测能力的下界**：不依赖任何效应排序假设，只会偏保守，不会高估。

`holm_per_test_alpha(alpha, family_size)` 就返回这个 α/m。实证含义：**m=2 时购买率 MDE 放大 10.1%**（§6.2）。注意这不是"Holm 的全部能力"——当各效应不相等时真实 Holm 更强，本表给出的数字是下界。

**护栏非劣效检验不并入 Holm**：`design.guardrail` 给了它独立的单侧 α=0.05 与界值，它是一个方向明确的非劣效检验；把同一个指标再塞进辅助 Holm 族是另一个（优势性）检验，二者不能混算。表里护栏行的 `multiplicity = none`，`alpha_per_test = design.guardrail.alpha_one_sided`，并在 `notes` 写明口径。

### 2.5 正态近似在零膨胀利润上够不够用

不靠断言，靠蒙特卡洛（`tests/test_v3_power.py`）：

| 核查 | 参数 | 结果 |
|---|---|---|
| 正态数据下 MDE 处的拒绝率 | σ=20，n=300/臂，800 次重复 | 与 0.80 的差 < 0.05 |
| 零膨胀利润（p_pay=0.10、购买者均值 26、SD 22.2，偏度 5.71、超额峰度 45.0） | n=5,000/臂，600 次重复 | 实测 **0.747**（正态近似略偏乐观） |
| 同上 | n=10,000/臂，600 次重复 | 实测 **0.780** |

结论：**偏度越高、n 越小，解析 MDE 越乐观**。正式设计每臂 3–10 万人，按渐近性该偏差应可忽略，但本文不把它当成已验证事实——n ≥ 20,000 的逐点核查留待 Phase G 的完整 DGP 功效跑（HITL §7.2）。**按上表的收敛趋势外推，L2 的 3 万人格（每臂 1.5 万）的实际功效可能比名义低 1–2 个百分点，这正是 Tier 2 必须报 MC_SE 的原因之一。** 注意：上表是**压力测试**用的合成分布（κ=48），比 §2.7 实测的每用户净利 κ=15–31 更重尾；它说明"正态近似在更坏情况下会偏乐观"，不能反过来当作实测 κ。

### 2.6 方差来源红线（这是本模块最关键的一条）

- 方差/峰度/退款率 **只能**来自 `ObservedDataset` 的 **train split**（`design_sample_profile` 内部先 `select_split("train")` 再取 `observations`），或独立先导模拟。
- 传入裸 `DataFrame`、模拟器或任何含真值列的帧 → **抛错**（`test_design_sample_profile_refuses_non_observed_dataset`、`test_profile_rejects_truth_columns`）。
- 本模块**只读五列**：`treatment`、`net_profit`、`paid_purchase_7d`、`any_refund_30d`、`split`（`OBSERVED_COLUMNS`）。第五列是 C2 护栏非劣效 MDE 的基线来源，仍是**可观测结果列**；多读一列都算越界。
- 模块**导入期不会加载 `causal_growth.dgp`**（子进程断言 `'causal_growth.dgp' in sys.modules == False`），DGP 只在 `_generate_design_sample` 内部延迟导入，且只取 `population.observation_bundle()` 的三张观测表。AST 检查保证这是全模块唯一一处 DGP 导入。
- 因此"用测试集定检测目标"在这条路径上不是靠纪律，而是**物理不可达**。

### 2.7 σ 的抽样不确定性：按实测峰度，不用正态公式（C4）

利润的峰度远高于正态（正态 κ=3）。样本方差满足

$$\operatorname{Var}(s^2)=\frac{\mu_4-\sigma^4}{n}+O(n^{-2})=\frac{\sigma^4(\kappa-1)}{n}+O(n^{-2}),\qquad \kappa=\frac{\mu_4}{\sigma^4},$$

由 delta 法得

$$\frac{\mathrm{SE}(\hat\sigma)}{\sigma}\approx\sqrt{\frac{\kappa-1}{4\,n_{\text{arm}}}}.$$

**关键口径**：`n_arm` 是**提供 σ 的那份样本的每臂人数**，即 train split 的 49,822–50,250，而不是设计队列的 100,000。原稿用正态公式 `1/√(2·n_arm) ≈ 0.32%`（n_arm=50,000），把误差低估了 2.7–3.9 倍。

实测（与 MDE 表**同一份 train split** 的 `net_profit`；κ 为非超额峰度，四阶中心矩/方差²）：

| 层 | n_train 处理/对照 | κ_treatment | κ_control | SE(σ̂)/σ 处理臂 | SE(σ̂)/σ 对照臂 | MDE 相对 SE（合成） | `mde100` σ 压力功效 |
|---|---|---|---|---|---|---|---|
| L0 | 49,750 / 50,250 | 22.626 | 26.258 | 1.0425% | 1.1210% | 0.7635% | **0.7912** |
| L1 | 50,000 / 50,000 | 19.392 | 31.141 | 0.9590% | 1.2276% | 0.7763% | **0.7904** |
| L2 | 49,955 / 50,045 | 19.763 | 25.429 | 0.9690% | 1.1047% | 0.7312% | **0.7913** |
| L3 | 50,178 / 49,822 | 15.350 | 29.028 | 0.8455% | 1.1859% | 0.6886% | **0.7907** |

读法（三条）：

1. **κ 按臂实测，两臂可以很不对称**（L1 处理臂 19.39、对照臂 31.14）。σ 相对 SE 必须逐臂算，不能用一个 pooled κ。
2. **MDE 相对 SE** 按 `sqrt(w_1²r_1² + w_0²r_0²)` 合成（`w_i` 用设计队列两臂方差项、`r_i` 用 train split 每臂人数），得 0.689%–0.776%；它比单臂的较大值小，因为两臂独立误差会部分抵消。
3. **`mde100` 的 σ 压力功效**用保守口径：把两臂 σ 同时按**较大的单臂相对 SE** 上浮（机制层面的同向尺度漂移），于是 MDE 同比例上浮、同一绝对目标效应更难检出：

$$\text{power}=\Phi\!\left(\frac{z_{1-\alpha/2}+z_{1-\beta}}{1+r_{\text{stress}}}-z_{1-\alpha/2}\right),\qquad r_{\text{stress}}=\max(r_1,r_0).$$

结果 **0.7904–0.7913**，即"约 0.79"，不是 0.8000。这个数是**解析压力值，不是实测拒绝率**；实测拒绝率必须由 §8.4 的入口从真实重复汇总。对评审给出的 1.0%–1.6% stress 区间，同一公式给 **0.788–0.792**；本次实测的 1.05%–1.23% 落在其中，所以"约 0.79"不依赖某一个具体的 κ 估值。

> **与评审估值的差异（如实记录）**：评审给出的 L1≈20–24、L3≈35–50 与本次 train split 实测（L1 19.39/31.14、L3 15.35/29.03）并不完全一致。本表以**可复现的同一 train split 实测值**为准（内容哈希与 σ 均与 D.1 原画像逐位相同，见 §3.4），不用评审估值替代实测；差异保留供复核。口径上要注意：`SE(σ̂)` 公式里的 κ 必须是**每用户净利**（含约 90% 零）的峰度；若在"购买者金额"子集、全样本（含测试 split）或别的 rep 上算 κ，会得到不同的数，不能直接对比。结论方向不变：正态公式显著低估，`mde100` 真实功效约 0.79。

### 2.8 护栏退款率的非劣效 MDE（C2）

护栏指标 `any_refund_30d_per_assigned_user` 是逐用户 0/1 结果，检验是**单侧非劣效**：

$$H_0:\;p_1-p_0\ge \text{margin}\quad\text{vs}\quad H_1:\;p_1-p_0<\text{margin}.$$

检验统计量 `Z = (p̂1 − p̂0 − margin)/se0`，H0 下 `se0` 用 `p1=p0+margin` 与 `p0` 的合并比例；H1 真实差为 Δ 时用各自比例 `se1`。拒绝 H0（判非劣效）当 `Z < −z_{1−α}`，功效为

$$\text{power}(\Delta)=\Phi\!\left(\frac{\text{margin}-\Delta-z_{1-\alpha}\,se_0}{se_1}\right).$$

- **界值单位**：配置键名是 `noninferiority_margin_probability_points`，值是**概率单位** 0.005（=0.5 个百分点），不是"5 个百分点"。`guardrail_config()` 把它读成概率单位并校验 `<1`。
- **单侧 α 与功效目标**：`design.guardrail.alpha_one_sided = 0.05`、`design.guardrail.power_targets = [0.80, 0.90]`，全部来自配置，不在代码里写死。
- **MDE 的定义**：反解的是"**到界值的可检测距离**" `e = margin − Δ`。`e` 越小护栏越灵敏；`p1_at_mde = p0 + margin − e` 是该功效下仍能被判为非劣效的**最大真实处理组退款率**。业务上更直观的是**可检测的真实恶化** `Δ@MDE = margin − e`（表里 `treatment_control_delta_at_mde`）：L1 的 80% MDE 是 e=0.1095pp，等价于"能分辨 0.3905pp 的恶化"；不要把 e 误读成"只能分辨 0.11pp 的恶化"。
- **方差**：`se0/se1` 由 train split 的对照臂退款率 `p0` 与两臂人数决定（Bernoulli 方差 `p(1−p)`）；`p0` 逐层不同。方差由 `p0`/`p1` 唯一决定，因此表里只存 `p0_baseline` 与 `p1_at_mde`/`observed_treatment_control_delta`，不另设方差列。
- **界值的证据等级**：配置写明 `margin_evidence: hypothetical_business_tolerance_not_empirical_fact`。0.5pp 是**假设性的业务容忍度，不是实测事实**；本文只回答"在这个界值下检测能力是多少"，不回答"这个界值是否合理"。

20 万、50/50、单侧 α=0.05（四层）：

| 层 | p0（对照退款率） | p1,obs（处理组） | Δ_obs（pp） | e80（pp） | Δ@MDE80（pp） | e90（pp） | Δ@MDE90（pp） | p1@MDE80 | power@Δ_obs |
|---|---|---|---|---|---|---|---|---|---|
| L0 | 0.7602% | 1.2121% | +0.4519 | 0.1102 | 0.3898 | 0.1290 | 0.3710 | 1.1500% | 0.2825 |
| L1 | 0.7480% | 1.1800% | +0.4320 | 0.1095 | 0.3905 | 0.1282 | 0.3718 | 1.1385% | 0.4534 |
| L2 | 0.8053% | 1.2191% | +0.4138 | 0.1126 | 0.3874 | 0.1319 | 0.3681 | 1.1927% | 0.5972 |
| L3 | 0.6985% | 1.3711% | +0.6726 | 0.1067 | 0.3933 | 0.1250 | 0.3750 | 1.0917% | ≈0（2×10⁻⁶） |

（`e` = 到界值的可检测距离；`Δ@MDE = margin − e` = 可检测的真实恶化。二者都随功效目标变化。`power@Δ_obs` 是**情景值**：`Δ_obs` 来自 50k/臂的 train split，其抽样 SE 约 0.062pp；若真实差在 95% 区间内变动，功效会大幅变化，不能把表中的百分比当已知功效。）

**必须与 MDE 一起读的警告（这是 C2 最重要的发现）**：

1. 护栏的**相对精度**不差：到界值的可检测距离只有 0.107–0.113pp（80%），即能分辨约 0.387–0.393pp 的真实恶化（约为 0.5pp 界值的 77%–79%）。但这个精度是相对**界值**而言的，不是相对**实际处理效应**而言的。
2. 但**真实处理组退款率已经用掉了大部分界值**：train split 上处理-对照差为 **+0.41 到 +0.67pp**，相当于界值的 **83%–135%**。这不是抽样噪声（L1 的差约 7.0 个标准误、四层 6.5–10.5 个标准误），而是"处理组购买率更高 → 按人头计的退款率更高"的机制性结果。
3. 因此，**若真实差就是先导观测到的这个水平，护栏非劣效检验的功效只有约 28% / 45% / 60% / ≈0（L0/L1/L2/L3）**——L3 的观测差已经**超过** 0.5pp 界值，非劣效在原假设意义上几乎必然被拒绝。但必须强调：`Δ_obs` 本身是 50k/臂的估计，抽样 SE 约 0.062pp；若真实差在 95% 区间内变动，L2 的功效可从 ~0 到 ~1。**稳健的结论不是"护栏功效是 60%"，而是"观测差已在界值附近，护栏对真实差高度敏感；需要更大样本、更宽界值或条件口径，不能把点估计情景当已知功效"**。MDE 小 ≠ 护栏能通过：MDE 只描述"能分辨多小的恶化"，不描述"真实恶化有多大"。
4. 这是**设计层的证据，不是代码缺陷**：本模块不得改界值、不得改 DGP、不得为了让护栏好看而换指标。若业务确实要求 0.5pp 的非劣效结论，需要（a）重新论证界值（把购买率上升导致的机械退款上升排除，或改用 `refunded_orders_per_paid_order` 的条件口径），或（b）把护栏改成"不劣于某个相对比例"；两者都属设计变更，须重走 A 阶段评审。本文只把证据摆出来。

---

## 3. 数据：独立先导模拟

### 3.1 为什么非要跑一次先导

利润 MDE 需要 σ，护栏 MDE 需要退款率，C4 需要峰度。三者都不能来自真值（那是 DGP 解析式），也不能来自测试集（那是"看着答案定考卷"）。所以只能：生成一次数据 → 走完整五表 + 污染/清洗 + SQL → 只在 **train split** 上取 `net_profit` 与 `any_refund_30d` 的汇总 → 立刻删掉数据，只留画像。

`design.yaml` 已经写明这条路径：`variance_source: independent_design_pilot_observed_sql_outcomes`。

### 3.2 怎么跑（rep 编号在正式网格之外）

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m causal_growth.design.v3_power --pilot --out-dir out\v3_phase_d_mde
```

- 场景取 `design.local_power.base_scenarios`（L0_P_main / L1_main / L2_n200000_p050 / L3_fixed_lt000），n 取 `design.n_total` = 200,000。
- rep 编号由 `design_pilot_rep_ids()` 给出：**从注册的最大 R（1000）之后开始**，即 1000–1003。正式 rep 索引范围是 [0, R−1]，先导采样因此与任何正式 rep 的数据都不重叠——"看先导数据定检测目标"没有偷看正式 rep。
- 每个场景跑完立即 `shutil.rmtree` 流水线目录；不写 `data/v3`、不写 `audit/v3`；`formal_repetitions_completed` 恒为 0。

### 3.3 并发开发期如何安全跑先导（快照机制）

C 阶段的门禁 `build_observed_pipeline` 会在跑数据前后各哈希一次 `src/causal_growth/**/v3*.py`、`sql/v3*.sql`、`configs/v3*.yaml`，期间有变化就抛 `RuntimeError: source files changed during the data run`。并发开发期它会因别人写盘而随机变红。

**处置原则**：这是并发假红，**不得**去改 `v3_pipeline.py`、不得放宽哈希、不得删改别人正在写的文件。做法是把 `src`、`sql`、`configs` 复制成字节快照，在快照里跑（快照只读；跑完可删，或保留哈希清单作为"当时跑的是哪份字节"的凭据）。

**C4/C2 的复测**（2026-10-25 13:54–14:01，北京时间）在 4 个 AA 作业并行的内存紧张条件下进行，因此**每个场景单独起一个进程**（跑完即退出、释放内存），而不是一个进程连跑四层：

```powershell
$snap = 'out\v3_phase_d_mde_kappa\snapshot'
Copy-Item src $snap -Recurse -Force; Copy-Item sql $snap -Recurse -Force; Copy-Item configs $snap -Recurse -Force
$env:PYTHONPATH = (Resolve-Path (Join-Path $snap 'src')).Path   # 快照优先于可编辑安装
# 按场景逐个起进程，并显式指定先导 rep（1000/1001/1002/1003；CLI 的 --scenarios 会统一给 1000，不能用）：
.\.venv\Scripts\python.exe -c "from causal_growth.design.v3_power import run_design_pilot; \
run_design_pilot(['L0_P_main'], work_root='out/v3_phase_d_mde_kappa/probe', rep_ids=[1000])"
# …… 依次对 L1_main/1001、L2_n200000_p050/1002、L3_fixed_lt000/1003 重复，work_root 各自独立
```

运行前核验快照的 `load_v3_protocol().config_hash` 仍为 `30511a32…`（本轮通过）。四层墙钟 **141.8 / 142.9 / 142.4 / 144.5 秒**，合计约 **9.5 分钟**（单 rep、单线程、含完整五表 + 污染/清洗 + SQL，不含 CF 拟合）；每层峰值内存约 1.8 GB。

### 3.4 设计样本画像（方差、峰度与退款率的实际来源）

train split，n = 100,000（200,000 × `design.split.train` = 0.50）。**四个场景的 σ、内容哈希与 D.1 原画像逐位相同**（`sd_match=True`、`hash_match=True`），证明 C4/C2 的 κ/退款率是在**同一份 train split** 上实测的，不是另一份重抽样：

| 设计场景 | 层 | n_t | n_c | σ_t（元/人） | σ_c（元/人） | κ_t | κ_c | 对照退款率 p0 | 处理退款率 p1 | 内容哈希前 12 位 |
|---|---|---|---|---|---|---|---|---|---|---|
| L0_P_main | L0 | 49,750 | 50,250 | 9.2825 | 8.8035 | 22.626 | 26.258 | 0.007602 | 0.012121 | `0a0dc2d8ed13` |
| L1_main | L1 | 50,000 | 50,000 | 10.4709 | 10.3222 | 19.392 | 31.141 | 0.007480 | 0.011800 | `0c42a615e411` |
| L2_n200000_p050 | L2 | 49,955 | 50,045 | 10.4690 | 10.0092 | 19.763 | 25.429 | 0.008053 | 0.012191 | `85902c91be4c` |
| L3_fixed_lt000 | L3 | 50,178 | 49,822 | 12.1047 | 8.4574 | 15.350 | 29.028 | 0.006985 | 0.013711 | `34646a24cec9` |

读法（四条都要注意）：

1. **L3 的两臂 σ 明显不对称**（12.10 vs 8.46），而 L1/L2 两臂接近（10.47 vs 10.32、10.47 vs 10.01）。L3 的基线购买概率依赖隐藏变量 U（`dgp.l3.lambda_y = 0.5`），且分配依赖可观测 X（`lambda_t = 0` 时不含 U），两臂购买概率的跨用户分布因此不同、利润方差也就不同。MDE 公式对两臂分别用 σ_1²/n_1 与 σ_0²/n_0，正是为这种不对称准备的——**不能用一个 pooled σ 顶替两臂**。
2. **实际臂人数略微偏离 50/50**（如 49,750/50,250）：处理分配是逐用户独立伯努利抽样（`assign_treatment` 对非 L3 profile 用固定 propensity = 0.5），不是精确对半。本表的 MDE 按**注册分流**（50/50 → 100,000/100,000）计算，与实际臂人数的差异 < 1%，对 MDE 的影响 < 0.1%。
3. **σ 的抽样相对标准误不是 0.32%，而是 0.85%–1.23%**（单臂；按实测峰度）。MDE 合成相对 SE 为 0.689%–0.776%。原稿"σ 的抽样不确定性远小于 1%"的表述**已删除**：它只对正态成立，而利润的 κ 是 15–31，不是 3。σ 不确定性虽然仍小于 MDE 的点估计，但足以把 `mde100` 的真实功效从 0.8000 拉到约 0.79。
4. **两臂退款率差不是噪声**：处理组退款率比对照高 0.41–0.67pp（约 6.5–10.5 个标准误），来源是处理组更高的购买率（`any_refund_30d` 的分母是"全部被分配用户"，不是"支付用户"）。这直接决定了护栏的可用性（§2.8）。

---

## 4. 结果：固定 20 万人的利润 MDE（元/合格用户）

双侧 α = 0.05，`multiplicity = none`，取 `outputs/tables/v3_phase_D_mde.csv` 中 `record_type=design_mde`、`cohort_id=full_history` 的行。**数值与 D.1 原表逐位相同**（σ 与 p0 未变）。

| 层 | 50/50 80% | 50/50 90% | 30/70 80% | 30/70 90% | 10/90 80% | 10/90 90% |
|---|---|---|---|---|---|---|
| L0 | 0.1133 | 0.1311 | 0.1250 | 0.1446 | 0.1929 | 0.2231 |
| L1 | 0.1303 | 0.1507 | 0.1425 | 0.1649 | 0.2183 | 0.2526 |
| L2 | 0.1283 | 0.1485 | 0.1413 | 0.1634 | 0.2177 | 0.2519 |
| L3 | 0.1308 | 0.1514 | 0.1522 | 0.1761 | 0.2462 | 0.2849 |

换成"占对照均值的百分比"（更容易和业务口径对齐）：

| 层 | 50/50 80% | 30/70 80% | 10/90 80% |
|---|---|---|---|
| L0 | 5.05% | 5.56% | 8.59% |
| L1 | 4.97% | 5.43% | 8.32% |
| L2 | 5.03% | 5.54% | 8.54% |
| L3 | 6.38% | 7.42% | 12.00% |

**怎么读**：在 20 万人、对半分流的条件下，这个实验只能检测到"每人净增量利润 ≥ 0.11–0.13 元"的效应，相当于对照人均利润的 **5.0%–6.4%**。分流一旦偏到 10/90，同样的人数只能检测 1.7–1.9 倍大的效应——把 control 臂做到 90% 看起来"更稳"，代价是处理臂太小，检测能力反而更差。

## 5. 结果：固定 20 万人的购买率 MDE（百分点，pp）

| 层 | 50/50 80% | 50/50 90% | 30/70 80% | 30/70 90% | 10/90 80% | 10/90 90% |
|---|---|---|---|---|---|---|
| L0 | 0.382 | 0.442 | 0.416 | 0.483 | 0.637 | 0.740 |
| L1 | 0.379 | 0.439 | 0.413 | 0.479 | 0.633 | 0.735 |
| L2 | 0.379 | 0.439 | 0.413 | 0.479 | 0.632 | 0.734 |
| L3 | 0.363 | 0.420 | 0.396 | 0.459 | 0.605 | 0.703 |

相对基准购买率（p0 ≈ 0.09–0.10）：**3.76% – 4.00%** 的相对提升即可检出。

**购买率比利润"好检测"吗？** 不能这么比。两者单位不同（元 vs 概率），可比的只有"相对提升"：20 万人对半分之下，购买率能看见 **3.8%** 的相对变化，而利润要 **5.0%–6.4%** 的相对变化才能检出——按相对口径购买率确实更灵敏。但购买率在协议里是**辅助指标**（`design.auxiliary_metric`），唯一主指标是利润（`design.primary_metric`）；不得因为购买率更灵敏就把它当结论，也不得把两者混称共同主指标。

---

## 6. 单侧/双侧、单项/Holm 的差别

### 6.1 单侧 vs 双侧（20 万人、50/50、80% 功效）

| 层 | 利润双侧 | 利润单侧 | 双侧/单侧 | 购买率双侧 pp | 购买率单侧 pp |
|---|---|---|---|---|---|
| L0 | 0.1133 | 0.1006 | 1.1267 | 0.382 | 0.339 |
| L1 | 0.1303 | 0.1156 | 1.1267 | 0.379 | 0.336 |
| L2 | 0.1283 | 0.1139 | 1.1267 | 0.379 | 0.336 |
| L3 | 0.1308 | 0.1161 | 1.1267 | 0.363 | 0.322 |

比值 1.1267 = (z₀.₉₇₅+z₀.₈)/(z₀.₉₅+z₀.₈)，与机制无关。**重申 §2.3**：这里的单侧仍用 α=0.05，若改成严格的单侧 α=0.025，这个折扣不成立；CSV 用 `alpha_one_sided=0.05`、`sides_note=one_sided_uses_alpha_two_sided_value` 把这个缺口编码进表。

### 6.2 Holm 校正后的联合检测能力（20 万人、50/50、80%）

辅助家族 `[paid_purchase_7d, any_refund_30d_per_assigned_user]`，m = 2，每项 α/2 = 0.025：

| 层 | 单检验 pp | Holm(m=2) pp | 比值 | 膨胀 |
|---|---|---|---|---|
| L0 | 0.382 | 0.420 | 1.101 | +10.1% |
| L1 | 0.379 | 0.418 | 1.101 | +10.1% |
| L2 | 0.379 | 0.417 | 1.101 | +10.1% |
| L3 | 0.363 | 0.400 | 1.101 | +10.1% |

策略对比家族（`targeted_vs_same_budget_random`、`targeted_vs_no_coupon`，m = 2）对独立验证队列的利润 MDE 同样放大 10.1%：L1 的 0.15954 → 0.17556 元/人（`alpha_per_test` 0.05 → 0.025）。

**确证性家族只有 1 个成员**（利润），所以主指标的 MDE **不需要**任何校正；需要校正的只有辅助指标与策略对比。这一点容易被误读成"利润也要乘校正因子"，此处明确：不乘。**护栏非劣效检验也不乘**（§2.4）。

---

## 7. 子样本能力：总 20 万 ≠ 训练 10 万 ≠ 验证 4 万 ≠ 测试 6 万

**这是本文最容易被误用的地方。** 同一份数据、同一个机制（L1_main），只是"能用来做检验的人数"不同：

| 队列 | n_total | n_t | n_c | 利润 80% | 利润 90% | 购买率 80% pp | 购买率 90% pp | 相对 20 万队列的倍数 |
|---|---|---|---|---|---|---|---|---|
| `full_history`（全部历史随机实验） | 200,000 | 100,000 | 100,000 | **0.1303** | 0.1507 | 0.379 | 0.439 | 1.000 |
| `training`（训练集） | 100,000 | 50,000 | 50,000 | 0.1842 | 0.2131 | 0.538 | 0.624 | 1.414 |
| `split_validation`（验证集，派生行） | 40,000 | 20,000 | 20,000 | 0.2913 | 0.3370 | 0.857 | 0.994 | 2.236 |
| `heldout_test`（留出测试集） | 60,000 | 30,000 | 30,000 | **0.2378** | 0.2752 | **0.697** | 0.808 | **1.826** |
| `independent_validation`（额外 20 万三臂，取 `targeted_vs_same_budget_random`） | 200,000 | 66,667 | 66,666 | **0.1595** | 0.1846 | **0.465** | 0.539 | **1.225** |

三条必须写进正文的读法：

1. **不能用 20 万的 MDE 代表 6 万测试集。** 测试集只有 3 万/臂，利润 MDE 是 0.2378（1.83 倍），购买率 MDE 是 0.697 pp。
2. **训练集不是检验样本。** 训练集 10 万人给出 0.1842，但它用于**学习**，不是用来做确证性检验的；把它的 MDE 当"实验能力"是符号混用。
3. **额外的 20 万独立验证队列很强，但仍弱于 20 万历史队列。** 三臂各约 1/3：主对比（定向 vs 不发券）为 66,667 vs 66,667，另一对比（定向 vs 同预算随机）为 66,667 vs 66,666（最大余数法分配，两对比 MDE 差在第 7 位有效数字）。利润 MDE 0.1595（1.22 倍）。它的价值不在"更灵敏"，而在**另一个随机化来源**（HITL §6.3）：它检验的是"冻结策略是否真的创造收益"，与历史实验的识别假设不同。

**分流对子样本的加倍伤害**（L1_main，80% 双侧）：

| 队列 | 50/50 | 30/70 | 10/90 |
|---|---|---|---|
| `full_history` 利润 | 0.1303 | 0.1425 | 0.2183 |
| `heldout_test` 利润 | 0.2378 | 0.2602 | 0.3986 |
| `heldout_test` 购买率 pp | 0.697 | 0.760 | 1.164 |

即：**6 万测试集 + 10/90 分流的组合，利润 MDE 已经到 0.3986 元/人（3.06 倍于 20 万/50-50）**，购买率 MDE 到 1.16 pp。任何"在测试集上做 10/90 分流还能看见小效应"的计划都不成立。

---

## 8. 20 个功效格的校准：8 个验不出、4 个边界、8 个有余量

机制：每个格的目标效应 = `active_mde_multiplier × 该格设计队列的利润 MDE`（`design.local_power.relative_to_observed_design_mde` = 0 / 0.5 / 1 / 1.5 / 2）。设计 MDE 用该格**自己继承的层级机制**的 σ（§3.4），队列取该格注册的 n=200,000、p=0.5。

| 层 | 倍数 | 设计 MDE（元/人） | 目标效应（元/人） | 解析功效 | 区间类别（C5） | ≥80%？ | ≥90%？ |
|---|---|---|---|---|---|---|---|
| L0 | 0 | 0.1133 | 0.0000 | 0.0250 | below_design_mde | **否** | **否** |
| L0 | 0.5 | 0.1133 | 0.0567 | 0.2880 | below_design_mde | **否** | **否** |
| L0 | 1 | 0.1133 | 0.1133 | 0.8000 | **boundary_zero_margin** | **边界（零余量）** | **否** |
| L0 | 1.5 | 0.1133 | 0.1700 | 0.9875 | above_design_mde | 是（有余量） | 是 |
| L0 | 2 | 0.1133 | 0.2267 | 0.9999 | above_design_mde | 是（有余量） | 是 |
| L1 | 0 | 0.1303 | 0.0000 | 0.0250 | below_design_mde | **否** | **否** |
| L1 | 0.5 | 0.1303 | 0.0651 | 0.2880 | below_design_mde | **否** | **否** |
| L1 | 1 | 0.1303 | 0.1303 | 0.8000 | **boundary_zero_margin** | **边界（零余量）** | **否** |
| L1 | 1.5 | 0.1303 | 0.1954 | 0.9875 | above_design_mde | 是（有余量） | 是 |
| L1 | 2 | 0.1303 | 0.2605 | 0.9999 | above_design_mde | 是（有余量） | 是 |
| L2 | 0 | 0.1283 | 0.0000 | 0.0250 | below_design_mde | **否** | **否** |
| L2 | 0.5 | 0.1283 | 0.0642 | 0.2880 | below_design_mde | **否** | **否** |
| L2 | 1 | 0.1283 | 0.1283 | 0.8000 | **boundary_zero_margin** | **边界（零余量）** | **否** |
| L2 | 1.5 | 0.1283 | 0.1925 | 0.9875 | above_design_mde | 是（有余量） | 是 |
| L2 | 2 | 0.1283 | 0.2566 | 0.9999 | above_design_mde | 是（有余量） | 是 |
| L3 | 0 | 0.1308 | 0.0000 | 0.0250 | below_design_mde | **否** | **否** |
| L3 | 0.5 | 0.1308 | 0.0654 | 0.2880 | below_design_mde | **否** | **否** |
| L3 | 1 | 0.1308 | 0.1308 | 0.8000 | **boundary_zero_margin** | **边界（零余量）** | **否** |
| L3 | 1.5 | 0.1308 | 0.1962 | 0.9875 | above_design_mde | 是（有余量） | 是 |
| L3 | 2 | 0.1308 | 0.2616 | 0.9999 | above_design_mde | 是（有余量） | 是 |

### 8.1 验不出的格（必须点名）

**在 80% 功效标准下，"目标效应 < MDE" 的 8 个格**：

```
L0_power_mde000  L0_power_mde050
L1_power_mde000  L1_power_mde050
L2_power_mde000  L2_power_mde050
L3_power_mde000  L3_power_mde050
```

这 8 格的**解析功效**是 **0.025（倍数 0）与 0.288（倍数 0.5）**——这是设计期预期，不是实测拒绝率；把它们的结果写进"目标效应可被检测"的结论里就是口径错误。倍数 0 的格另有用途：它是"零利润效应但不是 AA"的对照（购买效应为 0 而仍发券时利润未必为 0，见 `docs/v3_参数依据.md` §8），不能拿来冒充 AA。

**若把标准提高到 90% 功效，再增加 4 个格，共 12 个验不出**：

```
L0_power_mde100  L1_power_mde100  L2_power_mde100  L3_power_mde100
```

但倍数 1.0 的格在 80% 口径下不是"验不出"，而是**边界格**：解析功效 = 0.8000 逐位对齐，零余量。按 C5 的裁决，它们必须与"通过格"分开表述——见 §8.3。

### 8.2 90% 功效需要多大倍数（校准入口）

`multiplier_for_power(0.90, alpha=0.05, reference_power=0.80)` = **1.15703**，四层**完全相同**（纯 z 比值）。要 95% 功效则是 1.28671（同一个函数可算；配置里没有 95% 功效，属函数参数）。

反过来的校准入口（"给定目标效应，反解 `active_mde_multiplier`"）：

```python
m = vp.multiplier_for_target_effect(target_effect=0.20, design_mde=0.13026)   # -> 1.5354
vp.calibrate_power_cell("L1_power_mde150", profile, level="L1", n_total=200000,
                        treatment_probability=0.5, alpha=0.05, reference_power=0.80,
                        configured_multiplier=1.5, target_effect=0.20)
# 返回 required_multiplier = 1.5354、analytic_power = 0.9904、两个 detectable 均为 True
# （显式 target_effect 会覆盖注册倍数的反推，但 configured_multiplier 仍如实记录）
```

`calibrate_power_cell(..., target_effect=...)` 会同时给出 `required_multiplier`、`analytic_power`、`detectable_at_reference`、`detectable_at_90` 四个判定量；不给 `target_effect` 时按注册倍数反推目标效应。

### 8.3 边界格如何编码进表（C5 的硬要求）

`mde100` 不能只靠散文说"它是边界格"。CSV 为每个功效格给出七个可机读字段：

| 字段 | `mde000/050` | `mde100` | `mde150/200` |
|---|---|---|---|
| `power_cell_class` | `below_design_mde` | **`boundary_zero_margin`** | `above_design_mde` |
| `boundary_flag` | `False` | **`True`** | `False` |
| `margin_ratio`（= 目标效应 / 设计 MDE） | 0.0 / 0.5 | **1.0** | 1.5 / 2.0 |
| `effect_margin`（= 目标效应 − 设计 MDE，元/人） | 负 | **0.0** | 正 |
| `power_margin`（= 解析功效 − 参考功效） | 负 | **0.0** | 正 |
| `power_at_sigma_plus_1se` | 0.025 / 0.283 | **0.7904–0.7913** | 0.986 / 0.9998 |
| `boundary_note` | "验不出格…" | "边界格…不得只看 detectable_at_80=True" | "通过格且有余量…" |

**下游 gate 的唯一正确写法**：

```python
pass_cells = frame[(frame.record_type == "power_cell")
                   & frame.detectable_at_80
                   & ~frame.boundary_flag]
# -> 8 行（倍数 1.5 / 2.0）；若漏掉 ~boundary_flag 会得到 12 行，多算 4 个边界格
```

如果 gate 只读 `detectable_at_80=True`，它会把 4 个边界格当通过格；这正是独立评审指出的"最接近静默放松"的一处。表本身现在能区分，**不需要依赖下游读散文**。

**单侧 α 标注**：`alpha_one_sided` 列在单侧 `design_mde` 行填 0.05（并非 0.025），`sides_note` 写 `one_sided_uses_alpha_two_sided_value`；护栏行填配置里的 `design.guardrail.alpha_one_sided`。这样"单侧口径缺口"也是可查的，不只在 §2.3 的散文里。

### 8.4 实测列仍是 `pending`（C3-部分）

**当前状态：没有数据。** `design.local_power.report` 要求的 `achieved_effect` / `rejection_rate` / `MC_SE` / `binomial_interval` 需要真实跑"20 格 × R 次"的完整五表 + SQL + 估计流程；正式 R 仍为 0。CSV 里这六列（`achieved_effect`、`rejection_rate`、`mc_se`、`binomial_ci_low`、`binomial_ci_high`、`empirical_n_reps`）**全部为空**，每一行的 `notes` 都写 `pending_local_power_entry_point`。

**本模块提供的是可执行入口，不是数据**：local-power 入口产出逐 rep 结果（至少四列 `cell_id / rep_id / effect_estimate / reject`）后，调用

```python
summary = vp.summarize_power_cells(per_rep_rows)   # DataFrame 或行字典序列
# 列: cell_id, n_reps, achieved_effect, achieved_effect_mc_se,
#     rejection_rate, mc_se, binomial_ci_low, binomial_ci_high, ci_confidence
```

它会逐格计算：达成效应均值及其 `sd/√R`、实测拒绝率、`mc_se = sqrt(p(1−p)/R)`、Clopper–Pearson 精确二项区间（默认 95%），并拒绝重复 `(cell_id, rep_id)`、非 0/1 拒绝标记、单 rep 格（MC_SE 无定义）等非法输入。

**绝对禁止**把 `analytic_power` 复制进 `rejection_rate`，或用 `profit_power` 的结果冒充"实测拒绝率"。两者的口径不同：解析功效是设计期正态近似，实测拒绝率必须来自完整链路的 R 次重复。

---

## 9. `outputs/tables/v3_phase_D_mde.csv` 的列说明与前几行

**732 行 = 704 行 `design_mde` + 8 行 `guardrail_mde` + 20 行 `power_cell`；66 列；557,714 字节。**

- 704 行 `design_mde` 的构成不变：**4 个常规队列 × 3 种分流 = 12 个设计点**，每点 2 档功效 × 2 种单/双侧 × (利润 1 种 + 购买率 2 种 = 3 种行) = 144 行；再加**独立验证队列的 2 个对比 × 1 种分流**，每点 2 × 2 × 4 = 32 行；合计 176 行/层 × 4 层。
- 8 行 `guardrail_mde` = 4 层 × 2 档功效（80%/90%），队列固定为 20 万/50-50、单侧 α=0.05、界值 0.005。
- 20 行 `power_cell` = 4 层 × 5 个倍数。

**本版新增的 27 列**（其余列含义不变；表中把同族的两列合并为一行，合计 27 列）：

| 列 | 触发意见 | 含义 |
|---|---|---|
| `cell_id` | C5 | 功效格的稳定 ID（如 `L1_power_mde100`）；其余行为空。下游 join / gate 用这个而不是拼 scenario+倍数字符串 |
| `alpha_one_sided` | C5 | 单侧行的实际单侧 α（主检验为 0.05，护栏为配置值）；双侧行为空 |
| `sides_note` | C5 | 单侧口径说明：主检验 `one_sided_uses_alpha_two_sided_value`，护栏 `guardrail_alpha_one_sided_from_config` |
| `margin_ratio` | C5 | 功效格：目标效应 / 设计 MDE；1.0 = 零余量边界 |
| `effect_margin` | C5 | 功效格：目标效应 − 设计 MDE（元/人）；边界格为 0 |
| `power_margin` | C5 | 功效格：解析功效 − 参考功效；边界格为 0 |
| `power_cell_class` | C5 | `below_design_mde` / `boundary_zero_margin` / `above_design_mde` |
| `boundary_flag` | C5 | 是否边界格（只有 `mde100` 为 True） |
| `boundary_note` | C5 | 边界/验不出/通过的中文说明 + σ 压力功效 |
| `profit_kurtosis_treatment` / `_control` | C4 | 各臂实测非超额峰度 κ |
| `sigma_relative_se_treatment` / `_control` | C4 | `sqrt((κ−1)/(4·n_train_arm))`：σ̂ 的相对标准误 |
| `mde_relative_se` | C4 | 设计 MDE 的相对标准误（两臂合成） |
| `power_at_sigma_plus_1se` | C4 | 两臂 σ 同时上行 1 个保守相对 SE 后、目标效应处的解析功效（**压力口径，非实测**） |
| `noninferiority_margin` | C2 | 护栏非劣效界值（概率单位 0.005 = 0.5pp） |
| `treatment_control_delta_at_mde` | C2 | 护栏 MDE 对应的**真实处理-对照差** `Δ@MDE = margin − e`；与 `mde`（到界值的距离）区分 |
| `mde_relative_to_margin_pct` | C2 | 护栏 MDE 占界值的百分比 |
| `power_at_zero_effect` | C2 | 真实差为 0 时判非劣效的功效 |
| `observed_treatment_control_delta` | C2 | train split 观测到的处理-对照退款率差（概率单位） |
| `power_at_observed_delta` | C2 | 以该观测差为情景时的非劣效功效（**设计情景，不是实测拒绝率**） |
| `achieved_effect` / `rejection_rate` | C3 | 实测列，**当前全空** |
| `mc_se` / `binomial_ci_low` / `binomial_ci_high` / `empirical_n_reps` | C3 | 实测列，**当前全空**；由 `summarize_power_cells` 填充 |

**原有列的关键口径**（未变）：

| 列 | 含义 |
|---|---|
| `data_source` | 恒为「合成数据 / 已知 DGP（非真实企业数据）」 |
| `record_type` | `design_mde` / `guardrail_mde` / `power_cell` |
| `scenario_id` / `level` / `base_scenario_id` | 提供方差/峰度/退款率的参考机制与层 |
| `cohort_id` | `full_history` / `training` / `split_validation` / `heldout_test` / `independent_validation` / `power_cell` |
| `cohort_provenance` | 队列来源：`design.mde_cohorts` / `design.split.validation（派生）` / `design.guardrail` / `scenarios.design_power_jobs` |
| `contrast` | `treatment_vs_control` / `targeted_vs_same_budget_random` / `targeted_vs_no_coupon` |
| `metric` | `net_profit_30d_per_assigned_user` / `paid_purchase_7d` / `any_refund_30d_per_assigned_user` |
| `n_total` / `n_treatment` / `n_control` | 总样本与各臂样本（**三列分列，禁止互相顶替**） |
| `alpha` / `alpha_per_test` / `sides` / `power_target` | 名义 α、实际用于该行的 α、单/双侧、目标功效 |
| `multiplicity` / `family_size` | `none` 或 `holm`；族大小 |
| `mde` / `mde_unit` | 检测下限；利润 `CNY_per_assigned_user`、购买率/护栏 `probability`；护栏的 `mde` 是**到界值的距离** `e`，不是处理-对照差 |
| `mde_pp` | 仅概率单位行：`mde × 100` |
| `control_mean` / `mde_relative_pct` | 相对口径基线（利润=对照均值；购买率=p0；护栏=p0，但 `mde_relative_pct` 留空，改用 `mde_relative_to_margin_pct`） |
| `sigma_treatment` / `sigma_control` | 该机制 train split 的两臂 σ（元/人） |
| `p0_baseline` / `p1_at_mde` | 购买率：基准率与 MDE 处处理率；护栏：对照退款率与"仍可判非劣效的最大处理退款率" |
| `target_effect` / `required_multiplier` / `configured_multiplier` | 功效格：目标效应、所需倍数、注册冻结倍数 |
| `analytic_power` | `design_mde` 行 = MDE 处功效（== `power_target`，自校验）；`power_cell` 行 = 目标效应处功效；`guardrail_mde` 行 = MDE 处非劣效功效（== `power_target`） |
| `required_multiplier_90` | 功效格：拿到 90% 功效所需的最小倍数（1.15703） |
| `detectable_at_80` / `detectable_at_90` | 功效格：目标效应 ≥ MDE(80%) / 足以拿到 90%；**必须与 `boundary_flag` 联读** |
| `primary_row` | 正文直接引用的行（主设计场景 L1、双侧、80%、无校正、50/50 或验证队列主对比；功效格行全为 True） |
| `variance_source` | `design_pilot_train_split:<scenario>:rep<id>` |
| `observed_dataset_hash` | 设计样本 train split 的内容哈希（SHA-256） |
| `notes` | 近似方式、根容差、口径与 `pending_local_power_entry_point` |

**三条示例行**（原样，未四舍五入；非连续行）：

```text
### 表头
data_source,record_type,scenario_id,level,base_scenario_id,cell_id,cohort_id,cohort_provenance,contrast,metric,n_total,n_treatment,n_control,treatment_share,alpha,alpha_per_test,alpha_one_sided,sides,sides_note,power_target,multiplicity,family_size,mde,mde_unit,mde_pp,mde_relative_pct,mde_relative_to_margin_pct,noninferiority_margin,treatment_control_delta_at_mde,control_mean,sigma_treatment,sigma_control,profit_kurtosis_treatment,profit_kurtosis_control,sigma_relative_se_treatment,sigma_relative_se_control,mde_relative_se,p0_baseline,p1_at_mde,target_effect,analytic_power,power_at_sigma_plus_1se,power_at_zero_effect,observed_treatment_control_delta,power_at_observed_delta,required_multiplier,configured_multiplier,required_multiplier_90,margin_ratio,effect_margin,power_margin,power_cell_class,boundary_flag,boundary_note,detectable_at_80,detectable_at_90,achieved_effect,rejection_rate,mc_se,binomial_ci_low,binomial_ci_high,empirical_n_reps,primary_row,variance_source,observed_dataset_hash,notes

### design_mde：L0、20 万/50-50、利润、双侧 80%
合成数据 / 已知 DGP（非真实企业数据）,design_mde,L0_P_main,L0,L0_P_main,,full_history,design.mde_cohorts,treatment_vs_control,net_profit_30d_per_assigned_user,200000,100000,100000,0.5,0.05,0.05,,two_sided,,0.8,none,1,0.11334062045536726,CNY_per_assigned_user,,5.045743816975577,,,,2.2462618905472636,9.282545785591083,8.803535583819043,22.626030108877504,26.25798046790103,0.010424659137595955,0.011209888240641242,0.00763533296279257,,,,0.8,0.7911919297155223,,,,,,,,,,,,,,,,,,,,,False,design_pilot_train_split:L0_P_main:rep1000,0a0dc2d8ed13813b03fef6a03c27ca787d4f7fbe6f25a05652c221a70271f6ce,normal_approximation; root_tolerance=1e-10; cohort_split=user_id_within_run; R=0; local_power_empirics=pending_local_power_entry_point; sigma_relative_se=sqrt((kurtosis-1)/(4*n_train_arm))

### guardrail_mde：L1、80%
合成数据 / 已知 DGP（非真实企业数据）,guardrail_mde,L1_main,L1,L1_main,,full_history,design.guardrail,treatment_vs_control,any_refund_30d_per_assigned_user,200000,100000,100000,0.5,0.05,0.05,0.05,one_sided,guardrail_alpha_one_sided_from_config,0.8,none,1,0.0010949356145133014,probability,0.10949356145133013,,21.898712290266026,0.005,0.0039050643854866987,0.00748,,,,,,,,0.00748,0.011385064385486698,,0.8,,1.0,0.00432,0.45336114106895614,,,,,,,,,,,,,,,,,,False,design_pilot_train_split:L1_main:rep1001,0c42a615e411efa91bafa5d391848b790acdd9ffe9e67de42709e9a79b64c528,noninferiority; margin=design.guardrail.noninferiority_margin_probability_points (probability units: 0.005 = 0.5pp); one_sided_alpha=design.guardrail.alpha_one_sided; guardrail_column=any_refund_30d; train_split_refund_rate; R=0; local_power_empirics=pending_local_power_entry_point

### power_cell：L1、倍数 1.0（边界格）
合成数据 / 已知 DGP（非真实企业数据）,power_cell,L1_main,L1,L1_main,L1_power_mde100,power_cell,scenarios.design_power_jobs,treatment_vs_control,net_profit_30d_per_assigned_user,200000,100000,100000,0.5,0.05,0.05,,two_sided,,0.8,none,1,0.1302619037260518,CNY_per_assigned_user,,4.965075504790613,,,,2.6235634,10.47086366474816,10.32215169489834,19.392040699202067,31.141389480039063,0.009589588286053283,0.012276275795215555,0.007762671129435782,,,0.1302619037260518,0.8,0.7903525991269789,,,,1.0,1.0,1.1570290737998699,1.0,0.0,0.0,boundary_zero_margin,True,边界格(boundary_zero_margin)：target_effect 恰等于设计 MDE，解析功效=0.8000 但零余量；σ 上行 1.2276% 后解析功效约 0.7904（压力口径，非实测拒绝率）；下游 gate 不得只看 detectable_at_80=True,True,False,,,,,,,True,design_pilot_train_split:L1_main:rep1001,0c42a615e411efa91bafa5d391848b790acdd9ffe9e67de42709e9a79b64c528,power_job_design_only; achieved_effect/rejection_rate/MC_SE/binomial_interval=pending_local_power_entry_point; constant_profit_shift_forbidden
```

文件为 UTF-8 with BOM（`utf-8-sig`，Excel 打开中文不乱码），编码取自 `configs/v3_data.yaml` 的 `io.csv_encoding`。

---

## 10. 局限性与结论失效条件

1. **正态近似对零膨胀利润偏乐观**（§2.5）。n=5,000/臂、偏度≈5.7 时实测功效 0.747 而非 0.80。**失效条件**：若某格每臂人数落到 1–2 万且利润偏度维持在高位，本表 MDE 需按实测功效上调（功效低 5 个百分点 ≈ MDE 上调 6%，由 `multiplier_for_power(0.75)` = 0.9403 反推）。
2. **σ 来自一次先导 rep，且 σ̂ 本身有抽样误差**（C4）。按实测峰度，单臂 `SE(σ̂)/σ` 为 0.85%–1.23%，MDE 相对 SE 为 0.689%–0.776%；`mde100` 在 σ 上行 1 个保守误差后解析功效约 0.7904–0.7913。**失效条件**：若正式 rep 的机制波动显著大于先导 rep（例如 L2 的时间漂移落在极端周次），MDE 会随 σ 漂移；正式跑应逐 rep 记录 σ 与 κ 并报其分布，而不是沿用本文的单点值。κ 本身也是单次估计；重尾下 κ̂ 的抽样误差不可忽略（本文未把它传播进 σ 的相对 SE，属二阶但**未量化**的保守性缺口，不能声称"已量化"）。
3. **单侧 α 是口径缺口**（§2.3）。主检验单侧行沿用 α=0.05；若评审要求严格单侧 α=0.025，单侧 MDE 会与双侧几乎相同。表里用 `alpha_one_sided` / `sides_note` 标注，但**没有**新增配置项。
4. **Holm 数字是下界**（§2.4），不是 Holm 的真实能力；效应不等时真实能力更强。
5. **独立验证队列的 σ 借用历史设计样本。** 定向策略臂是"被选中的子人群"，其利润方差可能更大（购买率更高 → 零膨胀混合的方差更大）。**失效条件**：若定向子人群的 σ 比历史处理臂高 k 倍，该队列的 MDE 最多高 k 倍（MDE 里只有处理臂那一项被放大），本表给出的 0.1595 因此偏乐观；正式报告应在策略冻结后用该子人群重估 σ。
6. **本文的 MDE 都是"均值差"的检测下限**，不是"个体效应"的检测下限。CATE 异质性、策略价值差距的检测能力需要在同一 σ 口径下另行计算，不能直接套用本文数字。
7. **随机实验的 MDE 不代表 L3 的隐藏混淆可被识别。** L3 的 MDE 只描述"假如我们做随机实验"的能力；L3 的观察性分析另有有效样本量、方差与敏感性，见 `docs/v3_协议.md` §3.4 与 §5。
8. **没有跑正式重复，实测列全部 pending。** 本文所有"功效"都是解析值，不是模拟拒绝率；Tier 2 的结论必须带 R 与 MC_SE，本文不具备该资格。§8.4 的 `summarize_power_cells` 只是汇总入口，不产生数据。
9. **护栏的 0.5pp 界值是假设性业务容忍度，且已被 DGP 的处理效应用掉大部分**（§2.8）。train split 的处理-对照退款率差为 +0.41 到 +0.67pp（界值的 83%–135%）；以该点估计为情景，护栏非劣效检验的功效只有 28% / 45% / 60% / ≈0（L0/L1/L2/L3）。**但 Δ_obs 本身有约 0.062pp 的抽样 SE**，真实差在 95% 区间内变动时功效可从 ~0 到 ~1；因此稳健结论是"护栏对真实差高度敏感、当前界值/样本量不足以稳过"，不是"已知功效 = 60%"。**失效条件**：若业务界值改为更大（例如 1pp）、或改为"退款率/支付订单"的条件口径、或护栏只对"因券诱导的增量购买"计退款，本节数字全部需要重算。本文不改界值、不改指标、不改 DGP。
10. **`mde100` 是边界格，不是"已验证可检出"。** 解析 0.8000 是"目标效应恰好等于设计 MDE"的恒等结果；零余量意味着 σ 或机制的任何不利漂移都会把真实功效推到 0.79 以下。下游 gate 必须读 `boundary_flag`，不能只读 `detectable_at_80`。
11. **κ 的实测值与评审估值不完全一致**（§2.7）：L1 19.39/31.14、L3 15.35/29.03，而评审给的是 L1≈20–24、L3≈35–50。本文以同一 train split 的可复现实测为准；若复核者能提供评审所用样本与口径，应把两套 κ 并列重算，而不是二选一。

---

## 11. 我没能做到的部分（显式声明，不静默降级）

1. **没有把目标效应翻译成"合法的购买概率增量"。** `design.local_power.effect_construction` 要求"先缩放合法的购买概率增量、再重新积分利润"。这一步需要 DGP 的解析利润积分器（`v3_engine` 的真值侧），属 D 的其它子任务；本文只交付到"目标效应（元/人）+ 所需倍数"这一步。
2. **没有生成 `achieved_effect` / `rejection_rate` / `MC_SE` / 二项区间的数据。** 这些列需要真实跑 20 格 × R 的完整五表 + SQL + 估计流程；按用户裁决正式 R 仍为 0。本文只交付**可执行入口** `summarize_power_cells`，CSV 里这些列留空并写 `pending_local_power_entry_point`。
3. **没有做 L0 的"利润同质化旋钮"可行域检查。** `L0_Pi_*` 两格的等期望成本/同质子集属 B 阶段议题，本模块只用 `L0_P_main` 的 σ。
4. **没有做 n ≥ 20,000 的逐点功效核查。** 只在 n=300 / 5,000 / 10,000 上验证了正态近似（§2.5）。
5. **没有跑 L2 时间漂移的分周 MDE。** L2 的 σ 是整段时期的混合方差；按周看，周内人数只有 2 万/周量级，MDE 会明显更大。这属 L2 的时间可见性分析，本文未覆盖。
6. **没有裁决护栏界值是否合理。** 本文只算"在 0.5pp 界值下的检测能力"并报告"观测处理差已用掉 83%–135% 界值"；界值是配置里的假设性业务容忍度，改它必须重走 A 阶段评审。本文不改配置。
7. **没有修 C8 的三处 D.3 文档问题。** `docs/v3_phase_D_models.md` 的 `data/v3_sql.py:184`（实际在 185 行）、`causal_forest` 的"任何漂移都 ConfigError"（实际只校验 5 项）、`constant/DR` 的 `<1e-9` 自同义反复，均不在本文件的文件域内。已把准确位置与改法报给主控，由 D.3 负责人处理。

---

## 12. 集成说明（给主控与 E/G 阶段）

```python
from causal_growth.design import v3_power as vp
profile = vp.design_sample_profile(observed_dataset, scenario_id="L1_main", rep_id=0)  # 内部只取 train split
mde = vp.profit_mde(profile.profit_sd_treatment, profile.profit_sd_control, 100000, 100000, alpha=0.05, power=0.80)
```

- 需要"给定目标效应反解倍数"→ `vp.calibrate_power_cell(...)`；需要"整表重算"→ `vp.build_mde_rows(protocol, profiles)` + `vp.write_mde_csv(rows, path)`。
- 需要分臂人数 → **只能**用 `vp.split_counts(n_total, probabilities)`，不要自己 `round(n*p)`。
- 需要 Holm 的单检验 α → `vp.holm_per_test_alpha(alpha, family_size)`。
- 需要把 MDE 当阈值用（"这个效应能不能检出"）→ `vp.profit_power(effect, ...) >= power_target`，不要手工比 MDE 大小（浮点边界会出错）。
- 需要 σ 的抽样不确定度 → `vp.sigma_relative_se(kappa, n_arm)` / `vp.mde_relative_se(profile, n1, n0)`；需要压力功效 → `vp.profit_power_sigma_stress(effect, ..., relative_inflation=...)`。
- 需要护栏非劣效 MDE → `vp.noninferiority_mde(p0, n1, n0, margin=..., alpha=..., power=...)`；界值/α/功效目标请用 `vp.guardrail_config()` 从配置读，不要手写 0.005。
- 需要从逐 rep 结果汇总实测功效 → `vp.summarize_power_cells(rows_or_df)`；**不要**把 `analytic_power` 当 `rejection_rate`。
- 下游 gate 判定"可检出" → `detectable_at_80 & ~boundary_flag`（或 `power_cell_class == "above_design_mde"`）。

## 13. 复现与证据清单

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'
# 1) C4/C2 先导（约 10 分钟，4 个场景 × 200,000 人；低内存请按 §3.3 分场景起进程）
.\.venv\Scripts\python.exe -m causal_growth.design.v3_power --pilot --out-dir out\v3_phase_d_mde_kappa
# 2) 出表（秒级，不再生成数据）
.\.venv\Scripts\python.exe -m causal_growth.design.v3_power --table `
    --out-dir out\v3_phase_d_mde_kappa --table-path outputs\tables\v3_phase_D_mde.csv
# 3) 本模块的测试
.\.venv\Scripts\python.exe -m pytest tests\test_v3_power.py -q --basetemp=out\pytest_v3power
```

> **注意**：`out/v3_phase_d_mde/design_pilot_profiles.json` 是 D.1 原画像，**没有 κ 与退款率字段**；用它对当前代码跑 `--table` 会按"缺字段"抛错（这是有意的失败要响）。当前表的方差/峰度来源是 `out/v3_phase_d_mde_kappa/design_pilot_profiles.json`；旧画像只用于 §13 末尾的"同一 train split"哈希/σ 对照。

| 证据 | 位置 | 是否入库 |
|---|---|---|
| 704 行设计 MDE + 8 行护栏 MDE + 20 个功效格的全部数字（732 行 × 66 列） | `outputs/tables/v3_phase_D_mde.csv` | 是 |
| 口径与公式的断言（**176 项**测试；D.1 原为 137 项，只增不减） | `tests/test_v3_power.py` | 是 |
| 实现 | `src/causal_growth/design/v3_power.py` | 是 |
| 先导画像（σ / κ / p0 / 退款率 / 内容哈希） | `out/v3_phase_d_mde_kappa/design_pilot_profiles.json` | 否（`out/` 已 gitignore；关键数字已内联进 CSV） |
| C4 复测的四层墙钟（141.8 / 142.9 / 142.4 / 144.5 s） | `out/v3_phase_d_mde_kappa/design_pilot_timings.json` | 否（同上） |
| 原 D.1 先导画像（σ 与哈希对照） | `out/v3_phase_d_mde/design_pilot_profiles.json` | 否（同上） |
| 先导耗时（原 D.1） | `out/v3_phase_d_mde/design_pilot_timings.json` | 否（同上） |
| 字节快照的源文件哈希 | `out/v3_phase_d_mde_kappa/snapshot/`（运行期只读字节副本，跑完可删） | 否（同上） |

**冻结配置校验**：本文所有数字都来自 `config_hash = 30511a32bcee9db55e8f5ec1bbc2b9d63eb63dc2a13aa5c720f948c781eccdbe`（七份 YAML 合并规范化 SHA-256），由 `test_config_canonical_hash_is_still_frozen` 每次 pytest 复核。本轮**没有修改任何 `configs/v3/*.yaml`**。

**同一 train split 的证明**：C4/C2 复测得到的四个场景 `observed_dataset_hash` 与 D.1 原画像**逐位相同**（`0a0dc2d8…` / `0c42a615…` / `85902c91…` / `34646a24…`），σ 也逐位相同。因此 κ 与退款率不是另一份重抽样，而是 MDE 表所用的那份 train split。
