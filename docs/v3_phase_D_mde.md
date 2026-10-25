# v3 Phase D.1：固定 20 万人反算 MDE 与 20 个功效格校准

> **合成数据 / 已知 DGP**，非真实企业数据。
> 维护时间：2026-10-25 11:27（北京时间，Asia/Shanghai）。维护人：D.1 子代理（资深数据科学家）。
> 状态：**设计期算量（design-time）**。正式重复次数 **R = 0**；本文不含任何"检出率 / 达成效应 / 拒绝率 / 覆盖率 / MC_SE"结论。
> 对应代码：`src/causal_growth/design/v3_power.py`；测试：`tests/test_v3_power.py`；数据表：`outputs/tables/v3_phase_D_mde.csv`。
> 依据：HITL《完整修订建议》§0 决策表、§7「从固定 20 万人出发评估检测能力」；`docs/v3_协议.md` §5；`configs/v3/design.yaml` 的 `mde_direction: fixed_n_inverse_power`。

---

## 0. 一页结论

**主叙述已经从"先算需要多少人"改成"固定 20 万人，反算能检测多小的效应"。** 以下是这个反算的结果。

| 问题 | 答案（20 万人、50/50、双侧 α=0.05、80% 功效） |
|---|---|
| 利润能检测多小的增量？ | **0.113 – 0.131 元/合格用户**，占对照均值的 **5.0% – 6.4%**（四层各自不同） |
| 购买率能检测多小的增量？ | **0.363 – 0.382 个百分点**，占基准购买率的 **3.8% – 4.0%** |
| 分流改成 30/70 会更差多少？ | MDE 变成 **1.09 – 1.16 倍** |
| 分流改成 10/90 会更差多少？ | MDE 变成 **1.68 – 1.88 倍** |
| 功效要求提到 90%？ | MDE 变成 **1.157 倍**（纯 z 比值，与机制无关） |
| 改成单侧 α=0.05？ | MDE 降到 **0.888 倍**（1/1.1267） |
| 辅助指标家族 Holm(m=2)？ | 购买率 MDE 放大 **10.1%** |
| 6 万测试集能检测多小？ | 利润 **0.2378** 元/人 = 20 万队列的 **1.83 倍**；购买率 **0.697 pp** |
| 额外 20 万三臂验证队列？ | 每臂约 66,667，利润 **0.1595** 元/人 = 20 万队列的 **1.22 倍**；购买率 **0.465 pp** |

三条最该被记住的结构性结论：

1. **总 20 万 ≠ 训练 10 万 ≠ 验证 4 万 ≠ 测试 6 万。** 同一份数据、同一个机制，仅因为能用于检验的人数不同，利润 MDE 从 0.1303 涨到 0.2913（2.24 倍）。任何"20 万能检测 X"的说法都不能挪用到 6 万测试集上。
2. **20 个功效格里，8 个"目标效应 < MDE"，在 80% 功效下验不出**：倍数 0 与 0.5 的 8 个格（4 层 × 2）。若把标准提高到 90%，再增加 4 个倍数 1.0 的格，**共 12 个格验不出**（点名见 §8）。
3. **功效格的通过/不通过只由倍数决定，与层级机制无关。** 20 个格都注册为 n=200000、p=0.5，共享同一个 α 与参考功效，因此"目标效应 / 设计 MDE"这个比值是唯一的自由量。机制（σ、基准购买率）只决定"1 倍 MDE 折算成多少元"，不决定能不能检出。

---

## 1. 本文回答什么、不回答什么

| 本文回答 | 落点 |
|---|---|
| 固定 n 与分流下利润/购买率的检测下限 | §4、§5 |
| 子样本（训练/验证/测试）与独立验证队列各自的检测下限 | §7 |
| 单侧与双侧、单项与 Holm 校正后联合检测能力的差别 | §6 |
| 20 个功效格需要多大的 `active_mde_multiplier` 才够 | §8 |
| 方差从哪来、为什么可以信 | §2.6、§3 |

**本文明确不回答**（属 D 的其它子任务与 Phase G，不得用本文数字顶替）：

- 实际检出率、达成效应（`achieved_effect`）、`rejection_rate`、`MC_SE`、二项置信区间；
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

`configs/v3/design.yaml` **只有一个 α**：`alpha_two_sided: 0.05`，没有独立的单侧 α。本表的处理是：

> **单侧行沿用同一个数值 α = 0.05**（即临界值 z₀.₉₅ = 1.6449），而不是常用的"单侧也取 0.025"。

这意味着本表的单侧 MDE 是**偏保守**的：若按严格单侧 α=0.025（z=1.9600）计算，单侧 MDE 会与双侧几乎相同，本表给出的 0.888 倍折扣就不成立。要让单侧 α 有独立取值，**必须新增配置项并重走 A 阶段评审**；本轮不擅自加参数。

同理，功效目标 80% / 90% 都来自 `design.power_targets`；配置里没有的其它功效（例如 95%）只能作为函数参数传入，且必须在报告里注明来源。本文所有数字只用配置内的两档。

### 2.4 多重校正与"联合检测能力"

| 检验族 | 成员（来自配置） | 族大小 m | 调整方式 |
|---|---|---|---|
| 确证性指标 | `multiplicity.confirmatory_metrics` = `[net_profit_30d_per_assigned_user]` | 1 | 无 |
| 辅助指标 | `multiplicity.auxiliary_family` = `[paid_purchase_7d, any_refund_30d_per_assigned_user]` | 2 | Holm |
| 策略对比 | `multiplicity.policy_comparisons` = `[targeted_vs_same_budget_random, targeted_vs_no_coupon]` | 2 | Holm |

Holm 的逐步临界值是 α/m, α/(m−1), …, α/1，**每一项都 ≥ α/m**，因此"每个 p 都 ≤ α/m"是"全部拒绝"的充分条件。设计期用 α/m 反解 MDE，得到的是 Holm **联合检测能力的下界**：不依赖任何效应排序假设，只会偏保守，不会高估。

`holm_per_test_alpha(alpha, family_size)` 就返回这个 α/m。实证含义：**m=2 时购买率 MDE 放大 10.1%**（§6.2）。注意这不是"Holm 的全部能力"——当各效应不相等时真实 Holm 更强，本表给出的数字是下界。

### 2.5 正态近似在零膨胀利润上够不够用

不靠断言，靠蒙特卡洛（`tests/test_v3_power.py`）：

| 核查 | 参数 | 结果 |
|---|---|---|
| 正态数据下 MDE 处的拒绝率 | σ=20，n=300/臂，800 次重复 | 与 0.80 的差 < 0.05 |
| 零膨胀利润（p_pay=0.10、购买者均值 26、SD 22.2，偏度 5.71、超额峰度 45.0） | n=5,000/臂，600 次重复 | 实测 **0.747**（正态近似略偏乐观） |
| 同上 | n=10,000/臂，600 次重复 | 实测 **0.780** |

结论：**偏度越高、n 越小，解析 MDE 越乐观**。正式设计每臂 3–10 万人，按渐近性该偏差应可忽略，但本文不把它当成已验证事实——n ≥ 20,000 的逐点核查留待 Phase G 的完整 DGP 功效跑（HITL §7.2）。**按上表的收敛趋势外推，L2 的 3 万人格（每臂 1.5 万）的实际功效可能比名义低 1–2 个百分点，这正是 Tier 2 必须报 MC_SE 的原因之一。**

### 2.6 方差来源红线（这是本模块最关键的一条）

- 方差 **只能**来自 `ObservedDataset` 的 **train split**（`design_sample_profile` 内部先 `select_split("train")` 再取 `observations`），或独立先导模拟。
- 传入裸 `DataFrame`、模拟器或任何含真值列的帧 → **抛错**（`test_design_sample_profile_refuses_non_observed_dataset`、`test_profile_rejects_truth_columns`）。
- 本模块**只读四列**：`treatment`、`net_profit`、`paid_purchase_7d`、`split`（`OBSERVED_COLUMNS`）。多读一列都算越界。
- 模块**导入期不会加载 `causal_growth.dgp`**（子进程断言 `'causal_growth.dgp' in sys.modules == False`），DGP 只在 `_generate_design_sample` 内部延迟导入，且只取 `population.observation_bundle()` 的三张观测表。AST 检查保证这是全模块唯一一处 DGP 导入。
- 因此"用测试集定检测目标"在这条路径上不是靠纪律，而是**物理不可达**。

---

## 3. 数据：独立先导模拟

### 3.1 为什么非要跑一次先导

利润 MDE 需要 σ。σ 不能来自真值（那是 DGP 解析式），也不能来自测试集（那是"看着答案定考卷"）。所以只能：生成一次数据 → 走完整五表 + 污染/清洗 + SQL → 只在 **train split** 上取 `net_profit` 与 `paid_purchase_7d` 的标准差/均值 → 立刻删掉数据，只留画像。

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

C 阶段的门禁 `build_observed_pipeline` 会在跑数据前后各哈希一次 `src/causal_growth/**/v3*.py`、`sql/v3*.sql`、`configs/v3*.yaml`，期间有变化就抛 `RuntimeError: source files changed during the data run`。单人开发时这是对的；**并发开发期它会因别人写盘而随机变红**（本轮实测撞到过一次：期间有代理新建了 `design/v3_aa.py` 与 `configs/v3_repetition_overlay.yaml`）。

**处置原则**：这是并发假红，**不得**去改 `v3_pipeline.py`、不得放宽哈希、不得删改别人正在写的文件。做法是把 `src`、`sql`、`configs` 复制成字节快照，在快照里跑：

```powershell
$snap = 'out\v3_phase_d_mde\snapshot'
Copy-Item src     (Join-Path $snap 'src')     -Recurse -Force
Copy-Item sql     (Join-Path $snap 'sql')     -Recurse -Force
Copy-Item configs (Join-Path $snap 'configs') -Recurse -Force
$env:PYTHONPATH = (Resolve-Path (Join-Path $snap 'src')).Path   # 快照优先于可编辑安装
.\.venv\Scripts\python.exe -m causal_growth.design.v3_power --pilot --out-dir out\v3_phase_d_mde
```

运行前先核验快照自身的 `load_v3_protocol().config_hash` 仍为 `30511a32…`（本轮实际核验通过）。快照为只读字节副本，**跑完即删**（`out/v3_phase_d_mde/snapshot/` 已清理，只保留 `snapshot_hashes.json` 作为"当时跑的是哪份字节"的凭据）；G 阶段编排器可以直接复用这个机制实现"运行期间源码只读"。

**运行期的两件副产品**（`out/` 不入库，仅作当次证据）：

- `out/v3_phase_d_mde/design_pilot_profiles.json`：四个场景的 σ / p0 / 内容哈希（**同样的数字已内联进 `outputs/tables/v3_phase_D_mde.csv` 的 `sigma_*`、`p0_baseline`、`observed_dataset_hash` 列**，故即使 `out/` 被清理，本表仍可自证）。
- `out/v3_phase_d_mde/design_pilot_timings.json`：单场景墙钟 148.3 / 149.2 / 152.0 / 161.0 秒，合计约 **10.2 分钟**（单 rep、单线程、含完整五表 + 污染/清洗 + SQL，不含 CF 拟合）。

### 3.4 设计样本画像（方差的实际来源）

train split，n = 100,000（200,000 × `design.split.train` = 0.50）：

| 设计场景 | 层 | n_train | n_t | n_c | σ_t（元/人） | σ_c（元/人） | 对照均值（元/人） | p0（基准购买率） | rep | 内容哈希前 12 位 |
|---|---|---|---|---|---|---|---|---|---|---|
| L0_P_main | L0 | 100,000 | 49,750 | 50,250 | 9.2825 | 8.8035 | 2.2463 | 0.101672 | 1000 | `0a0dc2d8ed13` |
| L1_main | L1 | 100,000 | 50,000 | 50,000 | 10.4709 | 10.3222 | 2.6236 | 0.100100 | 1001 | `0c42a615e411` |
| L2_n200000_p050 | L2 | 100,000 | 49,955 | 50,045 | 10.4690 | 10.0092 | 2.5498 | 0.099830 | 1002 | `85902c91be4c` |
| L3_fixed_lt000 | L3 | 100,000 | 50,178 | 49,822 | 12.1047 | 8.4574 | 2.0520 | 0.090603 | 1003 | `34646a24cec9` |

读法（三条都要注意）：

1. **L3 的两臂 σ 明显不对称**（12.10 vs 8.46），而 L1/L2 两臂接近（10.47 vs 10.32、10.47 vs 10.01）。L3 的基线购买概率依赖隐藏变量 U（`dgp.l3.lambda_y = 0.5`），且分配依赖可观测 X（`lambda_t = 0` 时不含 U），两臂购买概率的跨用户分布因此不同、利润方差也就不同。MDE 公式对两臂分别用 σ_1²/n_1 与 σ_0²/n_0，正是为这种不对称准备的——**不能用一个 pooled σ 顶替两臂**。
2. **实际臂人数略微偏离 50/50**（如 49,750/50,250）：处理分配是逐用户独立伯努利抽样（`assign_treatment` 对非 L3 profile 用固定 propensity = 0.5），不是精确对半。本表的 MDE 按**注册分流**（50/50 → 100,000/100,000）计算，与实际臂人数的差异 < 1%，对 MDE 的影响 < 0.1%。
3. σ 的抽样相对标准误约 1/√(2·n_arm) ≈ 0.32%，所以 MDE 的抽样不确定性远小于 1%；本表的主要不确定性来自**正态近似本身**（§2.5），不是 σ 的估计误差。

---

## 4. 结果：固定 20 万人的利润 MDE（元/合格用户）

双侧 α = 0.05，`multiplicity = none`，取 `outputs/tables/v3_phase_D_mde.csv` 中 `record_type=design_mde`、`cohort_id=full_history` 的行。

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

**购买率比利润"好检测"吗？** 不能这么比。两者单位不同（元 vs 概率），可比的只有"相对提升"：20 万人对半分之下，购买率能看见 **3.8%** 的相对变化，而利润要 **5.0%–6.4%** 的相对变化才能检出——按相对口径购买率确实更灵敏。但购买率在协议里是**诊断指标**（`design.auxiliary_metric`），唯一主指标是利润（`design.primary_metric`）；不得因为购买率更灵敏就把它当结论，也不得把两者混称共同主指标。

---

## 6. 单侧/双侧、单项/Holm 的差别

### 6.1 单侧 vs 双侧（20 万人、50/50、80% 功效）

| 层 | 利润双侧 | 利润单侧 | 双侧/单侧 | 购买率双侧 pp | 购买率单侧 pp |
|---|---|---|---|---|---|
| L0 | 0.1133 | 0.1006 | 1.1267 | 0.382 | 0.339 |
| L1 | 0.1303 | 0.1156 | 1.1267 | 0.379 | 0.336 |
| L2 | 0.1283 | 0.1139 | 1.1267 | 0.379 | 0.336 |
| L3 | 0.1308 | 0.1161 | 1.1267 | 0.363 | 0.322 |

比值 1.1267 = (z₀.₉₇₅+z₀.₈)/(z₀.₉₅+z₀.₈)，与机制无关。**重申 §2.3**：这里的单侧仍用 α=0.05，若改成严格的单侧 α=0.025，这个折扣不成立。

### 6.2 Holm 校正后的联合检测能力（20 万人、50/50、80%）

辅助家族 `[paid_purchase_7d, any_refund_30d_per_assigned_user]`，m = 2，每项 α/2 = 0.025：

| 层 | 单检验 pp | Holm(m=2) pp | 比值 | 膨胀 |
|---|---|---|---|---|
| L0 | 0.382 | 0.420 | 1.101 | +10.1% |
| L1 | 0.379 | 0.418 | 1.101 | +10.1% |
| L2 | 0.379 | 0.417 | 1.101 | +10.1% |
| L3 | 0.363 | 0.400 | 1.101 | +10.1% |

策略对比家族（`targeted_vs_same_budget_random`、`targeted_vs_no_coupon`，m = 2）对独立验证队列的利润 MDE 同样放大 10.1%：L1 的 0.15954 → 0.17556 元/人（`alpha_per_test` 0.05 → 0.025）。

**确证性家族只有 1 个成员**（利润），所以主指标的 MDE **不需要**任何校正；需要校正的只有辅助指标与策略对比。这一点容易被误读成"利润也要乘校正因子"，此处明确：不乘。

---

## 7. 子样本能力：总 20 万 ≠ 训练 10 万 ≠ 验证 4 万 ≠ 测试 6 万

**这是本文最容易被误用的地方。** 同一份数据、同一个机制（L1_main），只是"能用来做检验的人数"不同：

| 队列 | n_total | n_t | n_c | 利润 80% | 利润 90% | 购买率 80% pp | 购买率 90% pp | 相对 20 万队列的倍数 |
|---|---|---|---|---|---|---|---|---|
| `full_history`（全部历史随机实验） | 200,000 | 100,000 | 100,000 | **0.1303** | 0.1507 | 0.379 | 0.439 | 1.000 |
| `training`（训练集） | 100,000 | 50,000 | 50,000 | 0.1842 | 0.2131 | 0.538 | 0.624 | 1.414 |
| `split_validation`（验证集，派生行） | 40,000 | 20,000 | 20,000 | 0.2913 | 0.3370 | 0.857 | 0.994 | 2.236 |
| `heldout_test`（留出测试集） | 60,000 | 30,000 | 30,000 | **0.2378** | 0.2752 | **0.697** | 0.808 | **1.826** |
| `independent_validation`（额外 20 万三臂，此处取 `targeted_vs_same_budget_random` 对比） | 200,000 | 66,667 | 66,666 | **0.1595** | 0.1846 | **0.465** | 0.539 | **1.225** |

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

## 8. 20 个功效格的校准：**点名 8 个（80%）/ 12 个（90%）验不出的格**

机制：每个格的目标效应 = `active_mde_multiplier × 该格设计队列的利润 MDE`（`design.local_power.relative_to_observed_design_mde` = 0 / 0.5 / 1 / 1.5 / 2）。设计 MDE 用该格**自己继承的层级机制**的 σ（§3.4），队列取该格注册的 n=200,000、p=0.5。

| 层 | 倍数 | 设计 MDE（元/人） | 目标效应（元/人） | 解析功效 | 目标效应 ≥ MDE(80%) | ≥ 90% 功效 |
|---|---|---|---|---|---|---|
| L0 | 0 | 0.1133 | 0.0000 | 0.0250 | **否** | **否** |
| L0 | 0.5 | 0.1133 | 0.0567 | 0.2880 | **否** | **否** |
| L0 | 1 | 0.1133 | 0.1133 | 0.8000 | 是（刚好） | **否** |
| L0 | 1.5 | 0.1133 | 0.1700 | 0.9875 | 是 | 是 |
| L0 | 2 | 0.1133 | 0.2267 | 0.9999 | 是 | 是 |
| L1 | 0 | 0.1303 | 0.0000 | 0.0250 | **否** | **否** |
| L1 | 0.5 | 0.1303 | 0.0651 | 0.2880 | **否** | **否** |
| L1 | 1 | 0.1303 | 0.1303 | 0.8000 | 是（刚好） | **否** |
| L1 | 1.5 | 0.1303 | 0.1954 | 0.9875 | 是 | 是 |
| L1 | 2 | 0.1303 | 0.2605 | 0.9999 | 是 | 是 |
| L2 | 0 | 0.1283 | 0.0000 | 0.0250 | **否** | **否** |
| L2 | 0.5 | 0.1283 | 0.0642 | 0.2880 | **否** | **否** |
| L2 | 1 | 0.1283 | 0.1283 | 0.8000 | 是（刚好） | **否** |
| L2 | 1.5 | 0.1283 | 0.1925 | 0.9875 | 是 | 是 |
| L2 | 2 | 0.1283 | 0.2566 | 0.9999 | 是 | 是 |
| L3 | 0 | 0.1308 | 0.0000 | 0.0250 | **否** | **否** |
| L3 | 0.5 | 0.1308 | 0.0654 | 0.2880 | **否** | **否** |
| L3 | 1 | 0.1308 | 0.1308 | 0.8000 | 是（刚好） | **否** |
| L3 | 1.5 | 0.1308 | 0.1962 | 0.9875 | 是 | 是 |
| L3 | 2 | 0.1308 | 0.2616 | 0.9999 | 是 | 是 |

### 8.1 验不出的格（必须点名）

**在 80% 功效标准下，"目标效应 < MDE" 的 8 个格**：

```
L0_power_mde000  L0_power_mde050
L1_power_mde000  L1_power_mde050
L2_power_mde000  L2_power_mde050
L3_power_mde000  L3_power_mde050
```

这 8 格跑出来的拒绝率预期是 **0.025（倍数 0）与 0.288（倍数 0.5）**，都不是"检出"；把它们的结果写进"目标效应可被检测"的结论里就是口径错误。倍数 0 的格另有用途：它是"零利润效应但不是 AA"的对照（购买效应为 0 而仍发券时利润未必为 0，见 `docs/v3_参数依据.md` §8），不能拿来冒充 AA。

**若把标准提高到 90% 功效，再增加 4 个格，共 12 个**：

```
L0_power_mde100  L1_power_mde100  L2_power_mde100  L3_power_mde100
```

倍数 1.0 的格恰好落在参考功效上（解析功效 = 0.8000，逐位对齐），因此**它只满足 80%、不满足 90%**；而且它没有任何余量——一旦实际 σ 比设计估计高 10%，该格的实际功效会降到约 0.72。若"倍数 1.0 必须稳过 80%"是设计意图，那就必须把 σ 的机制不确定性算进去，而不是把目标正好压在 MDE 上。建议把倍数 1.0 的格标注为**边界格**，而不是"通过格"。

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

---

## 9. `outputs/tables/v3_phase_D_mde.csv` 的列说明与前几行

724 行 = **704 行 `design_mde`**（4 个参考机制 × 176 组合）+ **20 行 `power_cell`**。

176 的构成：**4 个常规队列 × 3 种分流 = 12 个设计点**，每点 2 档功效 × 2 种单/双侧 × (利润 1 种 + 购买率 2 种 = 3 种行) = 144 行；再加**独立验证队列的 2 个对比 × 1 种分流**，每点 2 × 2 × (利润 2 种 + 购买率 2 种 = 4 种行) = 32 行；合计 176 行。独立验证队列的 2 个对比共享同一次分流（各臂约 1/3），所以不能再乘 3 种分流。

| 列 | 含义 |
|---|---|
| `data_source` | 恒为「合成数据 / 已知 DGP（非真实企业数据）」 |
| `record_type` | `design_mde`（设计 MDE）或 `power_cell`（功效格校准） |
| `scenario_id` / `level` / `base_scenario_id` | 提供方差的参考机制与层；功效格行里 `base_scenario_id` 即继承的机制 |
| `cohort_id` | `full_history` / `training` / `split_validation` / `heldout_test` / `independent_validation` / `power_cell` |
| `cohort_provenance` | 队列来源：`design.mde_cohorts` / `design.split.validation（派生）` / `scenarios.design_power_jobs` |
| `contrast` | `treatment_vs_control` / `targeted_vs_same_budget_random` / `targeted_vs_no_coupon` |
| `metric` | `net_profit_30d_per_assigned_user`（主指标）或 `paid_purchase_7d`（诊断） |
| `n_total` / `n_treatment` / `n_control` | 总样本与各臂样本（**三列分列，禁止互相顶替**） |
| `treatment_share` | 处理臂占该对比样本的比例 |
| `alpha` / `alpha_per_test` / `sides` / `power_target` | 名义 α、实际用于该行的 α（Holm 后）、单/双侧、目标功效 |
| `multiplicity` / `family_size` | `none` 或 `holm`；族大小（Holm 时 `alpha_per_test = alpha/family_size`） |
| `mde` / `mde_unit` | 检测下限；单位 `CNY_per_assigned_user` 或 `probability` |
| `mde_pp` | 仅购买率行：`mde × 100`（百分点） |
| `control_mean` | 相对口径的基线（利润=对照臂均值；购买率=p0） |
| `mde_relative_pct` | `mde / control_mean × 100`（%） |
| `sigma_treatment` / `sigma_control` | 该行用到的一对 σ（元/人，来自设计样本 train split） |
| `p0_baseline` / `p1_at_mde` | 仅购买率行：基准购买率与 MDE 处的处理组购买率 |
| `target_effect` / `required_multiplier` / `configured_multiplier` | 仅功效格行：目标效应、所需倍数、注册冻结倍数 |
| `analytic_power` | `design_mde` 行 = "MDE 处的功效"（== `power_target`，自校验）；`power_cell` 行 = "目标效应处的功效" |
| `required_multiplier_90` | 仅功效格行：拿到 90% 功效所需的最小倍数（1.15703） |
| `detectable_at_80` / `detectable_at_90` | 仅功效格行：目标效应 ≥ MDE(80%) / 足以拿到 90% |
| `primary_row` | 文档正文直接引用的行（主设计场景 L1、双侧、80%、无校正、50/50 或验证队列主对比；功效格行全为 True） |
| `variance_source` | `design_pilot_train_split:<scenario>:rep<id>` |
| `observed_dataset_hash` | 设计样本 train split 的内容哈希（SHA-256），保证方差可追溯 |
| `notes` | 近似方式、根容差、待补项（如 `achieved_effect/... pending D & G`） |

前两行（原样，未四舍五入）：

```text
data_source,record_type,scenario_id,level,base_scenario_id,cohort_id,cohort_provenance,contrast,metric,n_total,n_treatment,n_control,treatment_share,alpha,alpha_per_test,sides,power_target,multiplicity,family_size,mde,mde_unit,mde_pp,control_mean,mde_relative_pct,sigma_treatment,sigma_control,p0_baseline,p1_at_mde,target_effect,analytic_power,required_multiplier,configured_multiplier,required_multiplier_90,detectable_at_80,detectable_at_90,primary_row,variance_source,observed_dataset_hash,notes
合成数据 / 已知 DGP（非真实企业数据）,design_mde,L0_P_main,L0,L0_P_main,full_history,design.mde_cohorts,treatment_vs_control,net_profit_30d_per_assigned_user,200000,100000,100000,0.5,0.05,0.05,two_sided,0.8,none,1,0.11334062045536726,CNY_per_assigned_user,,2.2462618905472636,5.045743816975577,9.282545785591083,8.803535583819043,,,,0.8,,,,,,False,design_pilot_train_split:L0_P_main:rep1000,0a0dc2d8ed13813b03fef6a03c27ca787d4f7fbe6f25a05652c221a70271f6ce,normal_approximation; root_tolerance=1e-10; cohort_split=user_id_within_run; R=0
合成数据 / 已知 DGP（非真实企业数据）,design_mde,L0_P_main,L0,L0_P_main,full_history,design.mde_cohorts,treatment_vs_control,paid_purchase_7d,200000,100000,100000,0.5,0.05,0.05,two_sided,0.8,none,1,0.00381778075081048,probability,0.381778075081048,0.10167164179104478,3.7550104272504723,9.282545785591083,8.803535583819043,0.10167164179104478,0.10548942254185525,,0.8,,,,,,False,design_pilot_train_split:L0_P_main:rep1000,0a0dc2d8ed13813b03fef6a03c27ca787d4f7fbe6f25a05652c221a70271f6ce,normal_approximation; root_tolerance=1e-10; cohort_split=user_id_within_run; R=0
```

文件 429,200 字节，UTF-8 with BOM（`utf-8-sig`，Excel 打开中文不乱码），编码取自 `configs/v3_data.yaml` 的 `io.csv_encoding`。

---

## 10. 局限性与结论失效条件

1. **正态近似对零膨胀利润偏乐观**（§2.5）。n=5,000/臂、偏度≈5.7 时实测功效 0.747 而非 0.80。**失效条件**：若某格每臂人数落到 1–2 万且利润偏度维持在高位，本表 MDE 需按实测功效上调（功效低 5 个百分点 ≈ MDE 上调 6%，由 `multiplier_for_power(0.75)` = 0.9403 反推）。
2. **σ 来自一次先导 rep。** σ̂ 的抽样相对标准误 < 1%，但它绑定的是一次机制抽样。**失效条件**：若正式 rep 的机制波动显著大于先导 rep（例如 L2 的时间漂移落在极端周次），MDE 会随之漂移；正式跑应逐 rep 记录 σ 并报其分布，而不是沿用本文的单点值。
3. **单侧 α 是口径缺口**（§2.3）。单侧行沿用 α=0.05；若评审要求严格单侧 α=0.025，单侧 MDE 会与双侧几乎相同。
4. **Holm 数字是下界**（§2.4），不是 Holm 的真实能力；效应不等时真实能力更强。
5. **独立验证队列的 σ 借用历史设计样本。** 定向策略臂是"被选中的子人群"，其利润方差可能更大（购买率更高 → 零膨胀混合的方差更大）。**失效条件**：若定向子人群的 σ 比历史处理臂高 k 倍，该队列的 MDE 最多高 k 倍（MDE 里只有处理臂那一项被放大），本表给出的 0.1595 因此偏乐观；正式报告应在策略冻结后用该子人群重估 σ。
6. **本文的 MDE 都是"均值差"的检测下限**，不是"个体效应"的检测下限。CATE 异质性、策略价值差距的检测能力需要在同一 σ 口径下另行计算，不能直接套用本文数字。
7. **随机实验的 MDE 不代表 L3 的隐藏混淆可被识别。** L3 的 MDE 只描述"假如我们做随机实验"的能力；L3 的观察性分析另有有效样本量、方差与敏感性，见 `docs/v3_协议.md` §3.4 与 §5。
8. **没有跑正式重复。** 本文所有"功效"都是解析值，不是模拟拒绝率；Tier 2 的结论必须带 R 与 MC_SE，本文不具备该资格。

---

## 11. 我没能做到的部分（显式声明，不静默降级）

1. **没有把目标效应翻译成"合法的购买概率增量"。** `design.local_power.effect_construction` 要求"先缩放合法的购买概率增量、再重新积分利润"。这一步需要 DGP 的解析利润积分器（`v3_engine` 的真值侧），属 D 的其它子任务；`build_observed_pipeline` 目前仍会以 `local-power cells require the Phase D calibrated mechanism entry point` 拒绝启动功效格，说明该入口尚未实现。**本文只交付到"目标效应（元/人）+ 所需倍数"这一步。**
2. **没有实现 `achieved_effect` / `rejection_rate` / `MC_SE` / `binomial_interval`。** 这四列需要真实跑 20 格 × R=100 的完整五表 + SQL + 估计流程（`additional_design_power_jobs = 2000` 批，按 Phase D pilot 实测约 146 秒/批 ≈ 81 CPU·h）。按用户裁决，正式 R 仍为 0，本文不越界。
3. **没有做 L0 的"利润同质化旋钮"可行域检查。** `L0_Pi_*` 两格的等期望成本/同质子集属 B 阶段议题，本模块只用 `L0_P_main` 的 σ。
4. **没有做 n ≥ 20,000 的逐点功效核查。** 只在 n=300 / 5,000 / 10,000 上验证了正态近似（§2.5）。
5. **没有跑 L2 时间漂移的分周 MDE。** L2 的 σ 是整段时期的混合方差；按周看，周内人数只有 2 万/周量级，MDE 会明显更大。这属 L2 的时间可见性分析，本文未覆盖。
6. **没有覆盖护栏指标（`any_refund_30d_per_assigned_user`）的非劣效 MDE。** 护栏用单侧非劣效界值（`design.guardrail`），其检测能力应按 `noninferiority_binary` 另行反算，本文的 Holm(m=2) 只是把它算进了**族大小**，没有算它自己的 MDE。

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

## 13. 复现与证据清单

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'
# 1) 先导（约 10 分钟，4 个场景 × 200,000 人；建议在 §3.3 的快照里跑）
.\.venv\Scripts\python.exe -m causal_growth.design.v3_power --pilot --out-dir out\v3_phase_d_mde
# 2) 出表（秒级，不再生成数据）
.\.venv\Scripts\python.exe -m causal_growth.design.v3_power --table `
    --out-dir out\v3_phase_d_mde --table-path outputs\tables\v3_phase_D_mde.csv
# 3) 本模块的测试
.\.venv\Scripts\python.exe -m pytest tests\test_v3_power.py -q --basetemp=out\pytest_v3power
```

| 证据 | 位置 | 是否入库 |
|---|---|---|
| 704 行设计 MDE 与 20 个功效格的全部数字 | `outputs/tables/v3_phase_D_mde.csv`（724 行 × 39 列） | 是 |
| 口径与公式的断言（137 项测试） | `tests/test_v3_power.py` | 是 |
| 实现 | `src/causal_growth/design/v3_power.py` | 是 |
| 先导画像（σ / p0 / 内容哈希） | `out/v3_phase_d_mde/design_pilot_profiles.json` | 否（`out/` 已 gitignore；关键数字已内联进 CSV） |
| 先导耗时 | `out/v3_phase_d_mde/design_pilot_timings.json` | 否（同上） |
| 字节快照的源文件哈希（快照本体已删） | `out/v3_phase_d_mde/snapshot_hashes.json` | 否（同上） |

**冻结配置校验**：本文所有数字都来自 `config_hash = 30511a32bcee9db55e8f5ec1bbc2b9d63eb63dc2a13aa5c720f948c781eccdbe`（七份 YAML 合并规范化 SHA-256），由 `test_config_canonical_hash_is_still_frozen` 每次 pytest 复核。本轮**没有修改任何 `configs/v3/*.yaml`**。
