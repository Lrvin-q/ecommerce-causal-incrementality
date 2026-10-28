# G 阶段任务书 v2：矩阵驱动 + Tier2 覆盖收缩

> 合成数据 / 已知 DGP。维护时间：2026-10-28 20:20（北京时间）。
> **v2 修订说明**：v1 写于主树（`codex/v3-rebuild`），当时误以为 D03/E/F 未证实。
> 实际工作线在 **`codex/d03` 工作树**，D03/E01/E02/F01 已通过，配置 hash 也已合法变更。
> 本版按 d03 的真实状态重写；**执行以本版为准，v1（git `a927e00`）作废。**
>
> 交给当前 agent 实现。**主控不参与实现，只做独立复核。**

---

## 0. 工作树与环境（先看这一节）

| 项 | 值 |
|---|---|
| **工作树** | `C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目` |
| **分支** | `codex/d03` |
| Python | 该工作树内的 `.venv\Scripts\python.exe` |
| 产物根 | `out/`（5.6 GB 已有）、`outputs/`（137 MB 已有） |
| **注意** | 该工作树**没有 `data/`**，产物落 `out/`；不要假设 `data/` 存在 |

**不要在主树 `D:\L\practice_project\营销数分项目`（`codex/v3-rebuild`）上做本任务**：
它落后 77 个提交，只有本任务书这一个提交是它独有的。

**当前冻结配置的 canonical hash（本版唯一正确值）**：

```
00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3
```

（2026-10-28 经正式协议变更把 `tier1_aa_per_layer` 从 1000 改为 250，
见 `docs/v3_phase_G_protocol_change_aa250.md`。源码绑定文件数为 **48**。）

---

## 1. 真实进度（不要重新判断）

| 阶段 | 状态 |
|---|---|
| A / B / C | 通过 |
| D01 pilot（20 rep × 三粒度） | **20 rep 已完成**（10-28 18:20），独立评审未做 |
| D02 完整 AA | **通过**（10-27 09:45） |
| **D03 模型正式对照** | **通过**（10-28 05:15，正式 R=200，L1_main n=20 万，5 模型） |
| **E01 / E02 策略与预算** | **通过**（10-28 05:53 第三环确认） |
| **F01 OPE** | **通过**（10-28 10:52） |
| F02 独立随机验证 | 200 rep 已完成；评审 PASS WITH CONDITIONS，证据 19:30 已补 |
| **G01–G04 正式重复** | **未证实；矩阵驱动尚不存在** |
| H / Z | 未开始 |

**结论：G 的所有前置（模型、策略、OPE、验证）都已在 d03 上验证过。缺的只是"把矩阵真正跑起来"的那一层编排。**

---

## 2. 一句话目标

建一个 **G 阶段矩阵驱动**，把 `execution.yaml` 里已冻结但**从未实现**的 `job_semantics` 真正落地
（一个 rep 只建一次数据，同时服务 ATE 与模型学习），并把 Tier2 从「65 格 × 100 次」收缩到
「20 格 × 30 次」——**把剩余正式跑从约 780 CPU·h 压到约 193 CPU·h，且不降低任何结论强度**。

---

## 3. 为什么现在做这件事

`configs/v3/execution.yaml` 的 `job_semantics` 已经定死三件事：

```
full_learning_reuses_first_ate_repetitions: True    # 学习复用前 R_learn 个 ATE rep，不另建数据
independent_validation_is_extra_population: True    # 验证是额外 20 万队列，必须单独生成
all_models_share_repetition_data_and_split: True    # 同 rep 内所有模型共享数据与拆分
```

**"共用 rep"不是本任务的新设计，而是已冻结、但仓库里没有任何代码实现的语义。**
`planned_counts` 里 `full_learning_data_jobs: 7300` 与 ATE 批仍分开计数——若实现者按字面各跑一遍，
等于把同一份数据建两遍，**多花约 191 CPU·h**。这正是 A1 要防的。

按该语义，剩余正式跑算力（`formal_repeats` 各项值未变，本表成立）：

| 块 | rep 数 | 是否另建数据 | 单次 | CPU·h |
|---|---|---|---|---|
| Tier1 ATE 500/层（学习复用前 200） | 2,000 | 是 | ~117 s | 65 |
| Tier1 模型（在复用 rep 上） | 800 rep-模型集 | 否 | ~130 s | 29 |
| Tier1 验证 200/层（额外队列） | 800 | 是 | ~117 s | 26 |
| 重训 bootstrap 200 | 200 | 是 | ~240 s | 13 |
| **Tier2 ATE 100/格**（学习复用） | 6,500 | 是 | ~106 s | **191** |
| **Tier2 模型（在复用 rep 上）** | 6,500 rep-模型集 | 否 | ~130 s | **235** |
| **Tier2 验证 100/格**（额外队列） | 6,500 | 是 | ~106 s | **191** |
| 其他（D01 剩余 / E/F 收尾） | | | | ~30 |
| **合计** | | | | **≈ 780** |

**Tier2 占 79%**，而它只产出"边界方向"证据。这是本次要解决的问题。

---

## 4. 交付包 A：共用 rep 的矩阵驱动

### 4.1 核心设计

```
对每个 (cell, rep)：
    1) build_observed_pipeline(...)         # 只建一次
    2) ATE 估计（ITT，来自同一份观测数据）
    3) 若 rep < R_learn：prepare_learning_data → fit_predict(各模型) → 验证集打分
    4) 若 rep < R_validation：独立 20 万队列 → 策略名单 + 汇总
    5) 产物写盘，记录全部指纹
```

学习子集是 ATE reps 的**前缀子集**，不是另跑一批。这样同一 rep 的 ATE 与该 rep 的 CATE 来自同一批数据，pairing 更强。

### 4.2 必须复用而不是重写

| 已有件（均在 d03 工作树） | 用途 |
|---|---|
| `scripts/25_merge_d03_formal.py` / `26_d03_formal_tables.py` / `27_export_d03_evidence.py` | **D03 正式跑的"合并 / 出表 / 导出证据"三件套**，形态照抄 |
| `scripts/28_f02_validation.py` / `29_f02_formal.py` / `30_merge_f02_formal.py` / `32_aggregate_f02_formal.py` | F02 的 rep 循环、断点续跑、聚合形态 |
| `scripts/33_register_evidence_top.py` | 证据顶层登记（新产物必须走它） |
| `src/causal_growth/estimate/v3_models.py` | `prepare_learning_data` / `fit_predict` / `fit_validation_scorer` / `rank_models`（接口已冻结） |
| `scripts/17_merge_aa_layers.py` | 多根合并、去重、`_provisional` 约定、协议指纹校验（**不要削弱其校验**） |
| `scripts/20_export_evidence.py` | 证据导出 + `coverage.json`（含 sha256 与 `rows_raw/rows_deduped`） |
| `scripts/13_v3_pilot.py` | "一次 pipeline + 多模型"的最小原型、超参装配方式 |

### 4.3 产物契约

每格一个目录，含：

- `repetitions.csv`，列至少含
  `cell_id, level, scenario_id, rep, block, n, treatment_share,`
  `ate, ate_se, ate_p_value,`
  `model_<name>_tau_mean, model_<name>_tau_sd`（仅学习子集内）、
  `preprocessor_hash, config_hash, observed_hash, split_fingerprint,`
  `cpu_seconds_pipeline, cpu_seconds_estimate, cpu_seconds_models`
- `manifest.json`：`run_id, scenario_id, rep_range, n, R_ate, R_learn, R_validation,`
  `source_hashes_before, sql_sha256, config_hash, data_config_hash, protocol_config_hash, snapshot_binding`
- 汇总表写 `outputs/tables/v3_g_<block>.csv`（`utf-8-sig`）

**去重键必须是 `[scenario_id, block, rep]`**（不是只有 `rep`），理由见 §6.1。

### 4.4 断点续跑

- `--resume-from <某格>/repetitions.csv`，已完成 rep 不重跑
- 续跑必须校验参数一致（`n`、`R_ate`、`R_learn`、`scenario`、`protocol_config_hash`），**不一致拒绝**
- 允许因内存复位拆成多个 run-root；合并时读**全部**根并按 `[scenario_id, block, rep]` 去重
- 未跑满目标 R 时，汇总只写 `_provisional` 副本，不占正式路径

---

## 5. 交付包 B：Tier2 覆盖收缩（用户已批准）

### 5.1 口径

| 项 | 现值 | 改为 | 依据 |
|---|---|---|---|
| Tier1 ATE/层 | 500 | **500（不动）** | 降到 250 就无法再声称覆盖率落在 [0.93,0.97]，只能报"与名义一致"——省 33 CPU·h 不值 |
| Tier1 学习/层 | 200 | **100** | 模型间差异明显（D03 已实测 5 模型区分度高），R=100 足以分辨 |
| Tier1 验证/层 | 200 | **100** | 策略值 SE 增至 1.41 倍，可接受 |
| **Tier2 格数** | 65 | **20** | 保留边界代表性，砍同类重复 |
| **Tier2 R/格** | 100 | **30** | Tier2 只作"方向与量级"判断 |
| 固定 bootstrap | 1000 | 1000（不动） | 便宜 |
| 重训 bootstrap | 200 | 200（不动） | 估再训练方差 |

### 5.2 怎么选那 20 个格

Tier2 现 65 格（L0 3 / L1 25 / L2 17 / L3 20；n=20 万 56 格，3/6/10 万各 3 格）。
**按机制维度各留代表，不是按编号顺序砍。** 必须覆盖：

- L2 样本量扫描（现 3 格）→ 留最小与最大 2 格
- L2 时间漂移 / 分周
- L3 的 λ_T 扫描 → 至少 3 点（含两端）
- L3 的 λ_Y 与 λ_T 联合变化
- L3 的重叠 / 极端倾向
- L1 的缺失共同原因压力格
- 人群构成 / 延迟成熟

**产出 `docs/v3_tier2_selection.md`**，逐一写明"为什么留这 20 个、砍掉的 45 个为什么属同类"。不要只给数字。

### 5.3 落盘方式（关键）

**不得修改 `configs/v3/*.yaml`**（七份配置 canonical hash 必须保持 §0 给出的 `00723dc2…`）。

新建 `configs/budget/tier2_overlay.yaml`——该目录**已存在**（`repetition_overlay.yaml` 在里面，是既有先例）。

- **必须放 `configs/budget/`**，不要放 `configs/` 根或 `configs/v3/`：否则会被
  `pipeline_source_hashes()` 的 `configs/v3*.yaml` / `configs/v3/*.yaml` 两个 glob 扫进源码绑定集，
  变成"改预算 = 改源码"（10-25 踩过，`repetition_overlay.yaml` 注释里留着记录）
- 覆盖文件自记 `maintained_at_beijing` 与 `supersedes`
- 驱动读 overlay；overlay 的 sha256 写进每个 manifest

### 5.4 必须同步的文本

- `GOAL.md`：G01/G02/G03 的 R 与格数，**写明代价**（Tier2 MC SE 增至 √(100/30)≈1.8 倍）
- `docs/v3_repetition_budget_revision.md`：更新为本次口径
- 论文局限：Tier2 结论只写方向与量级，**不得与 Tier1 数字并列比较**

---

## 6. 已知坑（我踩过，别重踩）

### 6.1 去重键漏了层级/场景 → 静默丢数据

各层 `rep` 都从 0 起。按 `["rep"]` 去重会让不同层/不同 block 的行互相顶掉。
10-25 我因此让 L0 负对照（rep 0–99）顶掉 `true_aa` 的 rep 0–99，**静默少 100 次**。
**必须用 `[scenario_id, block, rep]`。**

### 6.2 只读单一 run-root → 漏一半数据，行数看起来正常

内存复位会把一次跑拆到多个目录。只读一个根会得到"看起来合理"的少一半样本。
合并读全部根，并把 `rows_raw / rows_deduped` 写进证据清单。

### 6.3 未跑满写正式路径 → 半成品被当最终结果

46 次/层的表**列齐全、数字合理**，事后极易被引用。未达目标 R 只写 `_provisional`，JSON 记 `provisional: true`。

### 6.4 跨运行比哈希前先看哈希输入里有没有运行标识列

观测表 `dataframe_sha256` **含 `run_id` 列**。两次 `run_id` 不同 → 哈希必然不同 → 我一度误判"装载器不等价"。
比哈希必须用相同 `run_id`。

### 6.5 正式跑必须"运行期间源码只读"（AGENTS §11）

`pipeline_source_hashes()` 哈希 `src/causal_growth/**/v3*.py` 全目录。任何人写盘都会让正在跑的作业抛
`source files changed during the data run`。**本项目已因此报废两次**（测试假红一次，正式 AA 启动即全灭一次）。

做法：`src/ sql/ configs/` 字节复制到 `out/g_snapshot/`，`PYTHONPATH` 指向快照，快照绑定哈希写进 manifest。
**开发与正式跑不得并行。**

### 6.6 换页表现为"跑得慢"，不是报错

多进程 × 2.2 GB 会越过可用内存红线，表现为每 45 秒墙钟只消耗 7 秒 CPU（占空比 17%），
**进程还在、CSV 还在写、没有异常**。判据是**占空比**（采样两次 `Get-Process` 的 CPU 增量），
不是 RSS、不是可用内存、不是"进程活着"。低于 60% 就降并行或复位（`--resume-from` 续跑，零丢失）。

### 6.7 校验器只准加强，不准削弱

`scripts/17_merge_aa_layers.py` 与 `19_finalize_local_power.py` 的 `validate` 已被独立评测过可绕过性，
现已分别拦 8 类与 10 类篡改。**改它们时既有篡改用例必须仍被拒**；删检查、放宽阈值、把 `raise` 改成
`warn`，等于拆门禁。同时**不要为了"更严"破坏既有保护**——"未跑满写 `_provisional`"是保护，不是缺口。

---

## 7. 与 E 的接口（一个真值陷阱）

`scripts/21_e_policy_run.py` 的 `REQUIRED_COLUMNS` 是：

```
user_id, is_new, cart_value, purchase_propensity, predicted_profit,
tau_hat, cost_hat, tau_true, cost_true
```

**它同时要求预测列与真值列。**

- 策略选择（`policy/selection.py`）**只许读 `tau_hat` / `cost_hat`**
- `tau_true` / `cost_true` **只许用于打分**（`incremental_value` / `evaluate_policy`）
- **必须写测试**：把 `tau_true`/`cost_true` 篡改成随机值后，选出的名单**逐人相同**。
  这是"策略没有偷看真值"的机械证据；没有它，E 的全部结论都不可信。

G 的产物要能拼出这 9 列，但**预测与真值必须分文件或列名可区分**，不允许混进"给模型的输入"。

---

## 8. 验收标准（可机械检验）

| # | 验收项 | 判据 |
|---|---|---|
| A1 | 实现 `job_semantics` 且不改变估计 | 同格同 rep 的 ATE 与单独跑 ATE **逐位相同**（<1e-12）、`observed_hash` 相同；该 rep 的 pipeline **只建一次**（CPU 计数 + 实际调用次数双重证明） |
| A2 | 续跑幂等 | 中断后 `--resume-from` 续跑，最终 `repetitions.csv` 与不中断跑完**逐字节相同** |
| A3 | 参数不一致拒绝 | 改 `n`/`R`/`scenario` 后续跑必须报错，不得静默接受 |
| A4 | 多根合并正确 | 人为拆两个 run-root，合并后 `rows_raw − rows_deduped` 等于重复行数，结果与单根一致 |
| A5 | 未跑满只写 provisional | 目标 R 未达时输出带 `_provisional`，JSON 标 `provisional: true` |
| A6 | overlay 生效 | 改 overlay 的 R 后实际 rep 数随之变化；`execution.yaml` hash 仍为 `00723dc2…` |
| A7 | 逐格带精度 | Tier2 每行都有 `R` 与 `MC_SE` |
| A8 | 策略不偷看真值 | 篡改 `tau_true/cost_true` 后名单逐人相同（§7） |
| A9 | 快照绑定 | manifest 有 `snapshot_binding`，与实际运行的源码快照哈希一致 |
| A10 | 小规模验证 | R=3、2 个格跑通，产物结构符合 §4.3，且 A1 在真实数据上成立 |

**A1 与 A8 是本任务的灵魂**：前者保证"省掉的不是结论"，后者保证"闭环没有偷看答案"。

---

## 9. 禁止事项

1. 不得修改 `configs/v3/*.yaml`；hash 必须保持 `00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3`。
2. 覆盖文件只放 `configs/budget/`。
3. 不得删除或放宽既有校验；不得把 `raise` 改成 `warn`。
4. 不得在正式跑期间改任何 `v3*.py`（§6.5）。
5. 不得用"解析功效"冒充实测拒绝率；Tier2 数字不得与 Tier1 并列。
6. 不得为了让数字好看而改 `n`、R、界值或指标。
7. **不得在主树 `codex/v3-rebuild` 上做本任务**；把主树任务书合并进 d03 时不得改动 d03 历史。
8. 不得把 `.workbuddy/` 等工具运行痕迹提交进仓库（d03 里已有一个未跟踪的 automations 目录）。

---

## 10. 成本与排期（估算，非承诺）

| 包 | 内容 | agent 时间 |
|---|---|---|
| A 设计 | 产物契约 + 子集语义 | 0.3 天 |
| A 实现 | 循环 / 续跑 / 合并 / 快照 / 登记 | 1–1.5 天 |
| A 测试 | A1–A10 自动化 | 0.3 天 |
| B 选格 | 20 格 + 机制维度论证 | 0.3 天 |
| B 接线 | overlay + 驱动读取 + GOAL/文档 | 0.5 天 |
| **合计** | | **约 2.5–3.5 天** |

之后正式跑：**约 193 CPU·h ≈ 2 天**（4 核并行）。相对现行 780 CPU·h **省约 590 CPU·h（≈6 天）**。

**顺序**：A 做完并跑通 A1 之后才动 B——若 A1 发现共用会改变估计，整个收缩方案要重算。

---

## 11. 交付自检清单

- [ ] A1–A10 全部有自动化测试，并提供"故意破坏一处、测试会红"的证据
- [ ] `configs/v3/*.yaml` 七份 hash 仍为 `00723dc2…`
- [ ] `git status` 干净（`.workbuddy/` 已 gitignore 并移出）
- [ ] 小规模验证跑（R=3、2 格）产物落 `outputs/tables/`，并经 `scripts/33_register_evidence_top.py` 登记、
      `scripts/20_export_evidence.py` 导出（含 sha256 与 `rows_raw/rows_deduped`）
- [ ] `docs/v3_tier2_selection.md` 写明 20 格的机制理由
- [ ] GOAL G01–G03 与 `docs/v3_repetition_budget_revision.md` 同步，且写明 Tier2 精度代价
- [ ] 报告给出**实测** CPU·h，并与本文件的 193 对比

---

## 12. 主控会怎么复核

不看自述，只做这几件事：

1. **独立重建**：只用 `outputs/evidence/` 重算关键数字，与文档逐位比对
2. **A1 反例**：自建一个 rep，比较共用路径与独立路径的 ATE
3. **A8 反例**：把真值列换随机数，看名单是否不变
4. **A6 反证**：改 overlay 的 R=7，看是否真跑 7 次；再查 `execution.yaml` hash 未变
5. **门禁未削弱**：对 17/19 号跑既有篡改用例，确认仍被拒
6. **抽查 3 个 Tier2 格的 `MC_SE`**，核对是否与 `√(p(1−p)/R)` 一致

**A1 或 A8 达不到，判不通过**——这两条不是"最好有"。
