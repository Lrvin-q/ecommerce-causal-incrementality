# TODO — v3 执行真相源

> 合成数据 / 已知 DGP。维护时间：2026-10-27 15:05（北京时间）。[ ]未开始；[~]进行中；[x]有证据完成；[!]阻碍。旧数字和进度保留在Git历史。

## 当前状态

**2026-10-27 18:44 更新。A/B/C/D02 通过。D03 正式 R 已完成（200/200，12:54–17:14，stderr 全空），合并与证据导出通过（1 000 行 per-rep / 72 000 行网格，`coverage.json` 10 文件）；**D03 仍标未证实，待独立评审**。F02 决策层（单侧 Holm + 退款率护栏）已完成、11 项测试绿；全量串行 1 228 项两次 exit=0（18:12–18:20 决策层改动前、18:24–18:31 改动后）；**F02 n=200k 单 rep 已跑通（18:32–18:39，exit=0）**，证据在 `outputs/evidence/f02_n200k_rep0/`；新发现预算只约束预测成本、定向臂实际支出 +29.1%，裁决为保留规则并逐 rep 报告（见 F02 预算裁决项）。**

**D02 通过**，闭环为：独立评审 PASS WITH CONDITIONS → 3 项文档 P0 修正（4×MDE→4.93×、34%→0.729、相对差 2.3%→7.84% 并改归因为层水平偏移）+ P0-1/E-1~E-3 修复 → **独立复核 PASS**（`docs/reviews/v3_phase_D_recheck.md`）→ 复核抓出的 2 处再修。详见 `docs/v3_phase_D_aa_formal.md` §8。证据包在 `outputs/evidence/`（1.79 MB，仅凭它可重建 FPR 46/1000 与 CP [0.0339,0.0609]）。

**两个未证实项，其中一个是硬前置**：
- **D03 未证实（provisional 导出已通 11:30；20 rep 诊断已完成 12:00）**：D.3 有完整实现与设计文档；逐用户 9 列导出已实现并跑通（n=20 000、单 rep、test 6 000 人），CSV 已喂 E 生成 72 行。**20 rep 诊断**（n=20 000，L1_main）已跑完：5 个模型都当过第一名（constant 9/20、causal_forest 4/20、dr/s 各 3/20、t 1/20）；除 causal_forest 外个体校准斜率中位数 0.02–0.18；冻结选模规则在 0.20 预算比同 rep 事后最优少 0.101 元/人。**这是诊断，不是正式 R**，D03 不能标"通过"。
- **D01 未证实**：20pilot 三粒度实测与资源计划。

**E 的进度**：组件层已完成（成本模型 / 5 个求解器 / 预算三口径 / 误差分解 / 排序组件，41 项测试绿）；编排层已抽成可复用模块 `v3_policy_grid.py` 并跑通三次（`scripts/21_e_policy_run.py`，9 策略 × 8 预算 = 72 行）：合成数据、真实 D.3 provisional 预测、**20 rep × 5 模型配对网格（7 200 行）**。关键现象：受约束策略按 `cost_hat` 全部 160/160 合规，但 greedy 按 `cost_true` 在 0.04 档只有 0–2/20 rep 全合规（实际支出 1.82–3.59 倍预算）——期望成本口径不等于硬上限。**没有一次是正式 R，不能下策略结论。**
**E 证据层（13:05 新增，13:51 审计修复）**：`v3_policy_evidence.py` + `scripts/24_e_evidence.py` 已实现成本校准、小池 5 求解器互证、桶宽收敛、200 种子随机基线、误差分解、规模扫描、三预算口径共 7 张表；10 项新测试绿，策略全套 54 项绿。n=900 冒烟跑通（2.8 秒），产物隔离在 `out/e_evidence_smoke/`，meta 记录实际使用的池/桶宽/种子；正式数据待 D03 R 结束后用 `--from-d03` 跑。**冒烟数字不是证据。** 独立审计修掉 4 个高危：LP 上界在“容差内超支后剩余预算变负”时会低于真实最优；MILP 无解向量时可能被标 `optimal`；`width=0.01` 的桶权重未走分币 half-up；真值 MILP 的界被误当成 raw 问题的界（已改名 `truth_milp_*` 并标注 `truth_cost_floored_at_cost_floor_cny`）。另加随机/保守种子 ≥2、求解器 `error` 状态硬门禁、网格按 `user_id` 排序与唯一性校验、严格 JSON/相对路径。

**三个值得记住的观察**：
- `local_swap` 在 0.60 预算的真值比 greedy 低 0.00008（合成数据）；20 rep × 5 模型网格里也有 26/800 格为负、最大绝对差 0.0052——它保证的是**预测目标**不降，**真值可以降**。
- 选模不是"报告一个获胜模型"那么简单：20 rep 里 5 个模型都当过第一，冻结规则选中的模型在 0.20 档比同 rep 事后最优少 0.101 元/人（事后上界）。
- `purchase_propensity_rank` 在 0.04 档真实价值 −0.0023（低于不发券）——按购买倾向选人是反向选择，propensity ≠ uplift。

| 阶段 | 状态 | 进入/退出门槛 |
|---|---|---|
| A 协议冻结 | [x] | 配置/矩阵校验，独立业务复审通过 |
| B 机制真值 | [x] | A通过后实施，独立科学评审 |
| C 五表SQL隔离 | [x] | 101作业/6977检查、四库与CLI补验，独立工程评审通过 |
| D 检测估计 | [~] | **D02 通过**；D01/D03 未证实。**D03 20 rep 诊断 + 3 rep × n=200k 试点已完成；正式 R（200 rep）12:52 启动** |
| E 策略优化 | [ ] | D通过，科学+业务评审 |
| F 观测闭环 | [~] | E通过，科学评审。**F01 单 rep 历史留出 OPE 已落盘（R=0，未证实，待评审）；F02 机制/决策层就绪，n=200k 单 rep 已跑通（工程）；F02 正式 200 rep 待批准** |
| G 正式重复 | [ ] | F通过，逐格R和工程评审 |
| H 图与长稿 | [ ] | G通过，三视角评审 |
| Z 最终审计清理 | [ ] | H通过，全项复核、单独清理提交 |

## A 工作清单

- [x] 阅读更新HITL、交接、纲领口径、工程规范与复盘。
- [x] 建立codex/v3-rebuild，保留master/v2.0。
- [x] 写协议草案，重建GOAL/TODO和决策反思日志。
- [x] 基线核查：原pytest25权限错误；隔离目录404通过；数字门禁1个版本文字问题；图门禁7图零错误。
- [x] humanizer全局安装与完整备份，逐hash/官方格式复核，见安装记录。
- [x] configs/v3全矩阵与参数依据（独立作者），73场景+20功效格。
- [x] 配置加载、矩阵导出、覆盖核验、源文件hash冻结，418项测试通过。
- [x] 独立电商业务专家评审、11项累计修复和复审通过。
- [x] A阶段汇报、交接/状态更新，里程碑提交以Git日志为准。

## D 阶段独立科学评审结论（2026-10-25 13:40 北京时间）

**实现层通过（D.1/D.2/D.3），D02 证据层不通过。** 评审独立复算 704 行 MDE（最大差 2.47e-11）、
AA 标签翻转端到端反例、206 项测试，未发现公式错误或泄漏；但指出八项必须补的证据/标注。

| 条件 | 内容 | 状态 |
|---|---|---|
| C1 | 正式 AA 按注册 n=200k + 授权 R 实跑；GOAL/G01/YAML 与 overlay 对齐；R=50/n=1万 只能叫 pilot | GOAL 已改；4 层 ×250 次正在跑 |
| C2 | 补 `any_refund_30d` 非劣效 MDE/功效（margin=0.005、单侧 0.05、80/90%） | 子代理进行中 |
| C3 | 补 20 功效格 `achieved_effect/rejection_rate/MC_SE`，实现 local-power 入口 | 子代理进行中 |
| C4 | σ 抽样 SE 由 0.32% 改为 ~1.0–1.6%（按峰度），`mde100` 真实功效约 0.79 | 子代理进行中 |
| C5 | CSV 编码 `mde100` 边界属性与单侧 α 标注（机器可读，不能只在散文） | 子代理进行中 |
| C6 | AA 报告补 SE 校准（合并经验 SD/平均 SE=1.020）与本 R 的实际功效 | 待补 |
| C7 | DR 补设计概率敏感性（`known_design_ipw`）、`propensity.primary` 关系、raw 诊断落地 | 待派 |
| C8 | 小修：行号 184→185；CF ConfigError 只覆盖 5 个超参；`<1e-9` 是自同义反复 | 子代理进行中 |

**评审确认的三处做得好**：AA 虚拟标签的机制惰性（翻转试验逐位验证）、方差来源隔离与逐位复现、
三道泄漏闸 + 五模型共享数据 + 真正折外 AIPW。

**主控误读已更正**：GOAL G01 的「AA1000」是每层 1000，不是总数 1000；已在 GOAL 正文标注修订与代价。

## D02 收口（2026-10-27 09:45）

- [x] 15 格 ×100 次 = **1500 次**功效实测（`outputs/tables/v3_phase_D_local_power_formal.csv`，15×62）
- [x] 独立评审（科学 + 工程）**PASS WITH CONDITIONS**：核心数字逐位复现，但 4 个 P0 + 4 个 E 项
- [x] 3 项文档 P0 修正：4×MDE→**4.93×**、34%→**0.729**、相对差 2.3%→**7.84%** 并改归因为**层水平偏移**
- [x] P0-1：MDE 表 448 行 σ 按 √p(1−p) 定点修正（与公式偏差 0.00e+00，`mde` 零改动）
- [x] E-1：证据导出 `outputs/evidence/`（1.79 MB，可独立重建 FPR 46/1000）；E-2：清理脚本前缀保护；E-3：17/19 校验加固
- [x] **独立复核 PASS**（`docs/reviews/v3_phase_D_recheck.md`）
- [x] 复核抓出的 2 处再修：§6 残留"≈4 倍"、负对照剔除混入的 1 行 `true_aa`（重建 8/100）
- [~] **D03 正式模型跑 + 逐用户 τ̂ 导出** ← E 的硬前置；20 rep 诊断已完成（2026-10-27 12:00），正式 R 待裁决
- [ ] D01 20pilot 三粒度实测与资源计划（正式 R 前先做 3 rep × n=200 000 试点）
  - [x] 3 rep 试点已完成：`docs/v3_phase_D_pilot.md`，单 rep ≈ 276 s、峰值 1.88–2.47 GB
  - [x] 20 rep 执行计划与算术已写入 `docs/v3_phase_D_pilot.md` §10（20:33）：3 进程 × 7 批 ≈ 32 分钟，CPU ≈ 1.6 h
  - [ ] **正式 20 rep 未跑**：`R=20 > 0`，须用户显式批准；另按 §8.4 补 L0/L3 各 1 rep

## D03 逐用户导出（2026-10-27 11:30，北京时间）

- [x] `export_d03_predictions()`：固定 9 列 CSV（E 契约），`status=provisional`
- [x] 真值物理隔离：`_audit_truth_for_test()` 是唯一出口，选人 7 列冻结后才合并 `tau_true/cost_true`；有"毒化真值不改变选人列"的测试
- [x] n=20 000、L1_main、单 rep、5 模型全跑：选模 `causal_forest`（验证集 LCB 均值 −0.1159），test 6 000 人
- [x] CSV 喂 `scripts/21_e_policy_run.py --input` → **72 行 = 8 预算 × 9 策略**；受约束策略按 `cost_hat` 全部 8/8 合规
- [ ] **正式 R 未启动**：跑几次、选模指标（当前只用 `models.selection.scoring` 一条）、评估量清单三件事未裁决
- [ ] 注意：本次 provisional 的 `tau_hat` 均值 0.514 vs `tau_true` 均值 0.202（高估约 2.5 倍）；`greedy` 两策略按 `cost_true` 只有 3/8 预算合规（期望成本口径，不是硬上限）。这两条只作 provisional 观察，不能写进结论

## D03 20 rep 诊断（2026-10-27 12:00，北京时间）

> 完整报告：`docs/v3_phase_D03_diagnostic.md`。**诊断，不是正式 R。**

- [x] 实现 `run_d03_diagnostic()`：20 rep × 5 模型；选模仍只用验证集 LCB，真值在选模后合并，五个候选全部评估
- [x] 策略网格改为**按模型配对**（同一 rep、同一批用户，5 个模型各跑 9 × 8）：首版只跑选中模型，会把模型差异误当策略差异
- [x] 产物：`outputs/tables/v3_phase_D03_diagnostic_{per_rep.csv, policy_grid.csv, summary.json}`（100 / 7 200 行 / 118 KB）；运行 8 分 43 秒
- [x] 选模稳定性：constant 9/20、causal_forest 4/20、dr 3/20、s 3/20、t 1/20；第一名与第二名分差中位数 0.0532，最小 0.0014
- [x] 个体校准：斜率中位数 t 0.042 / s 0.179 / causal_forest 0.689 / dr 0.018；Pearson 中位数 0.019–0.084；constant 无定义
- [x] 策略层（0.20 档，20 rep 配对）：business − greedy 为 constant +0.153、t +0.119、dr +0.137、s +0.059、causal_forest −0.002（10/20 rep greedy 胜）
- [x] 选模后悔值（0.20 档）：chosen − 同 rep 最优 = **−0.1007** 元/人；只有 38/160 格选到最优（事后上界）
- [x] 双口径合规：按 `cost_hat` 全部 160/160；按 `cost_true` 在 0.04 档只有 0–2/20 rep 全合规，greedy 实际支出 1.82–3.59 倍预算
- [x] **正式 R 裁决**：3 rep × n=200 000 试点已完成（12:49，≈276 秒/rep）；正式 R = 200 rep（`tier1_full_learning_per_model: 200`），4 分片 × 50，预计 ≈3.9 小时
- [ ] 若正式规模下选模仍频繁切换，走协议评审提出修订；不得在汇总里偷换成"固定 causal_forest"或"事后最优"

## D03 正式 R（2026-10-27 12:52 启动）

> 试点报告：`docs/v3_phase_D03_pilot_n200k.md`。**正式 R 完成并复核前，D03 仍标未证实。**

- [x] 3 rep × n=200 000 试点（`out/d03_pilot/`，快照 `67d842ae…`）：墙钟 13 分 49 秒，≈276 秒/rep（5 模型 + 5 份 9×8 网格）
- [x] 试点关键值：选模 constant 1 / causal_forest 2；cf 校准斜率 0.79–0.84；0.20 档 business − greedy 在 cf 上 −0.0189 ± 0.0075、s 打平、constant/t/dr 仍 business 更好；greedy 实际支出 0.04 档 1.31 倍预算；local_swap 120 格中 4 格真值为负（最小 −0.00075）
- [x] 分片与可观测性：`--rep-start/--rep-stop/--formal-r`、逐 rep 耗时日志；分片只切 `rep_id`，随机流不变
- [x] 正式 R：200 rep × n=200 000 × 5 模型，L1_main；快照 `out/d03_formal_snapshot/`，4 个独立进程写 `out/d03_formal/shard{0..3}/`；**17:13–17:14 四分片各 50 rep 完成，12:54 启动、墙钟约 4 小时 20 分；run.err 全空；每分片 summary `status=formal_r`、reps=50**
- [x] 合并脚本 `scripts/25_merge_d03_formal.py`：写盘前校验 rep 覆盖/去重、5 模型×8 预算×9 策略、chosen 恰好覆盖一个模型、双口径合规标记与数值一致；用 3 rep 试点产物演练通过（15 / 1 080 行）
- [x] 合并门禁 7 项合成用例（`tests/test_v3_d03_merge.py`）：缺 rep / 重复 rep / 篡改合规标记 / chosen 计数错 / config_hash 不一致 / 非正式分片全拒
- [x] 报告聚合层 `src/causal_growth/evaluation/v3_d03_formal.py` + `scripts/26_d03_formal_tables.py`：选模频率、模型校准（all/chosen，含**最大绝对相对偏差**）、真值价值、**按 (rep, model, budget) 配对的策略差**、oracle 后悔、双口径合规；缺格/重复格/覆盖不足/网格 chosen 行不完整即抛错。12 项测试绿；用 3 rep 试点表端到端演练产出 7 张表（policy_value/paired_diff/compliance 各 360 行，oracle 320 行——**全发券参考不参与事后最优**，chosen 配对 144 行）
- [x] 证据导出 `scripts/27_export_d03_evidence.py`：导出 manifest、快照绑定（83 文件）、4 份分片 summary 与 run.log；校验 rep 并集恰为 0..199、config_hash 四分片一致、run.err 全空、合并表哈希与行数（1 000 / 72 000）后再写 `coverage.json`
- [x] 合并分片 → `outputs/tables/v3_phase_D03_formal_*`；跑 26 报告表与 27 导出证据（17:15；21:00 重导出后 15 文件 = 14 导出件 + `coverage.json`，`config_hash=e1aa4314…`）；校验 200 rep / 1 000 行 per-rep / 72 000 行网格 / 每 rep 恰一个 chosen 全过
- [x] 报告表 7 张 + meta：`selection/calibration/policy_value/paired_diff/paired_diff_chosen/oracle/compliance`
- [x] **写 `docs/v3_phase_D03_formal.md` 正文数字**（选模 105/71/12/7/5；校准斜率 CF 0.754、S 0.467、T 0.114、DR 0.098；greedy−business 按模型符号分裂；0.2 档真实支出合规率 CF 11%/S 13%/T 39%/DR 26.5%/constant 0%）；2026-10-27 19:25 落盘，文首明确 **D03 仍未证实，等待独立评审**
- [x] **独立评审（20:53）返回 PASS WITH CONDITIONS**：数字层全部复现（选模、校准、40 个配对差、合规、oracle、证据哈希、83/83 快照、合并行数、7 表重建），**无算术错误**；P0-1（"运行期间未改 src"为假，窗口内 3 次 live 提交）、P1-1～P1-6 已按评审修正（21:02），并修源码斜率 docstring 与诊断 §111
- [x] **评审修改后全量串行测试（21:04:16–21:11:28）**：1 248 项 `exit=0`，单进程、无并发写盘，432 秒；`--collect-only` 计数 1 248；日志 `out/logs/pytest_d03_final_2105.log`（`-q` 未打印 passed 汇总行，以 exit 码与收集数计）
- [ ] **用户确认 D03 程序豁免**：正式 R 用 12:53:57 快照执行（83/83 哈希 + `snapshot_vs_live` 证明 3 个 live 改动未进入），但违反 AGENTS §11.2"不得与开发写盘并行"的字面规定；主负责已书面豁免，需用户确认后才把 D03 记入 GOAL 通过；不接受则需重跑约 4.3 h
- [ ] 独立评审（方法对照、选模频率、配对网格、双口径合规）→ D03 判定

## E 证据层（2026-10-27 13:05，北京时间）

> 覆盖 `docs/v3_phase_E_coverage.md` §8 的编排层缺口；**代表 rep 的正式证据已产生**，
> 但 **E01/E02 仍标"未证实"**，等待独立评审。

- [x] `src/causal_growth/policy/v3_policy_evidence.py`：成本校准（validation 处理组）/ 小池 20·100·500 的 5 求解器互证 + 浮点穷举参照 / 桶宽 5 档收敛 / 200 种子随机基线 / learning-optimization 误差分解 / 规模 1000·5000·full_test / 三预算口径
- [x] 真值隔离：所有 mask 先冻结，`tau_true/cost_true` 只进 `true_*` / `actual_*` 列；毒化测试覆盖 5 张表
- [x] 修复 `lp_upper_bound` 的免费券除零缺口（真值成本有大量 0；共享校验仍要求成本严格为正，故真值 MILP 先按 `cost_floor=1e-6` 抬高并单列 `truth_milp_cost_floor_cny`）
- [x] 10 项新测试（`tests/test_v3_policy_evidence.py`）+ 既有策略 54 项全绿
- [x] n=900 CSV 冒烟：7 张表 + 校准 JSON，2.7 秒；产物隔离 `out/e_evidence_smoke/`，已清掉误写进 `outputs/tables/` 的冒烟副本
- [x] `--from-d03` 正式路径小规模验证（14:01，n=2 000、rep=0、600 行 test）：8 个产物 61.1 秒，校准走 validation 处理组 201/400，分解表 `truth_milp_status=optimal`、`truth_milp_cost_basis=truth_cost_floored_at_cost_floor_cny`；产物隔离 `out/e_evidence_fromd03_smoke/`
- [x] **正式数据**：2026-10-27 19:17:51–19:42:28 用 `--from-d03 --rep-id 0 --n 200000` 跑完（D03 正式 rep 0，`chosen=constant`），9 个产物齐：7 张表 + `v3_phase_E_calibration.json` + `v3_phase_E_evidence_meta.json`；帧 60 000 行、sha256 `c8fd698e…c54e0`；阶段耗时 87.7/1.2/42.3/1.0/117.9/967.3 秒。**规模扫描 60k 有 7 档 `time_limit_no_incumbent`（NaN，非 0）**
- [x] E 正文报告 `docs/v3_phase_E_evidence.md`：2026-10-27 19:45 落盘（§2 校准、§7 规模扫描已补实数），明确"桶宽阈值由曲线定、不预设"；observed_value 留给 F01；**文首仍标"尚未独立评审、E01/E02 未证实"**
- [x] 小池表 `time_limit_no_incumbent` 契约补强（2026-10-27 19:45）：原先空 mask 会写 0 花费/0 价值，现整行 NaN；新增 `test_small_pool_no_incumbent_rows_are_nan_not_zero`，策略两文件 57 项绿（`--basetemp C:/cg_t`）；全量单进程串行 1 238 项 exit=0（19:46:59–19:53:48，日志 `out/pytest_full_20261027_1947.log`）
- [!] **LP 每 rep 上界缺口**：`policy.optimization.every_full_rep_required` 要求 `lp_relaxation` 在每个 full rep 上都有，但 D03 的 200 rep 网格只有 9 个策略、没有 LP 行；E 证据层只在代表 rep 上补。**G 阶段必须每 rep 补 LP 上界**，否则"规模对照覆盖所有 rep"不成立

## F 观测闭环（2026-10-27 14:39，北京时间）

> F 只允许用观测表 `(T, Y, C, R)`；真值只作评估后的审计列，不得进入任何选择/拟合。

- [x] `src/causal_growth/evaluation/v3_ope.py`：交叉拟合 IPW（HT）/ SNIPS（两臂分别归一化）/ DR（AIPW）策略价值，影响函数 SE；配对差 `sd(IF_A−IF_B)/√n`（含协方差）；成本 DR（对照臂成本 0）；30 天退款率 DR 护栏；ESS/支持违规可靠性门禁；Holm step-down
- [x] 折划分复用：`crossfit_nuisance` 新增 `fold_id`，`crossfit_two_arm_outcome` 在同一折上拟合成本/退款模型，杜绝跨折泄漏
- [x] 真值隔离入口：观测表若含 `*_true` / `audit_*` / `truth_*` / `potential_*` 列直接拒收；`actual_action` 放行
- [x] 9 项测试（`tests/test_v3_ope.py`）：SNIPS 手算公式、单臂退化、n=4 000 恢复已知策略值、no_coupon 跳过处理臂门禁、ESS/支持拒收、配对差用协方差而非独立 SE、成本/护栏恢复、真值列拒收、Holm 阈值
- [x] **F02 独立验证机制**（16:00 更新）：`evaluation/v3_f02.py` 从 D03 选中模型冻结三臂（`no_coupon / random_same_budget / selected_targeted_policy`，1/3 各臂），**每个活跃臂按臂内分配人数 × 0.2 元冻结名单**（配置 `same_per_assigned_user_in_each_active_arm`）；新一批验证用户走五表+SQL 出观测，全臂 ITT 对照；**先落盘冻结策略名单与 per_user，再解封真值**；全队列交付名单只用于审计且按 `user_id` 对齐；**代表 rep（0）额外落盘完整五表与 SQL，manifest 绑定其路径与 sha256**；11 项测试绿，n=2 000 CLI 冒烟产出 11 个文件 + `five_tables/`
- [x] **F02 n=200 000 单 rep（18:39 完成，工程状态）**：三臂 66,594/66,713/66,693，无空臂；预测支出 13,318.53/13,342.56 均在 0.2×臂人数内；冻结先于审计，manifest 记录解锁顺序；两主张单侧 p=0.3690/0.2990、Holm 调整 p 均 0.5980、均不通过；护栏 0.958% vs 0.780%，差值 +0.1784pp、单侧上界 0.2620pp < 0.5pp，通过；per_user/decision/guardrail 哈希复核一致；证据 `outputs/evidence/f02_n200k_rep0/`（不含逐用户真值；manifest 仅含冻结后聚合审计真值）
- [x] **F02 预算口径裁决（18:46）**：保留预测成本口径。实际成本发券时不可知，按实际成本约束不可实现；三臂共用同一规则、分配随机，ITT 有效；实际券成本已进入净贡献利润。正式 200 rep 逐 rep 报告实际支出/超支倍数，"同预算"限定为"同预测预算规则"。单 rep 定向臂实际 17,200 vs 预测 13,318.53（+29.1%），随机臂 13,300 vs 13,342.56（−0.3%）
- [ ] **F02 正式 200 rep**：`--status formal` 需用户显式授权与登记号；聚合按 rep 配对报告通过率，不合并 p 值
  - [x] **正式前置：两次独立拟合一致性（20:37）**：n=20 000、rep 0 两个独立进程；`freeze.json` 七字段逐位一致（含 `freeze_hash/per_user_hash/decision_hash/guardrail_hash`），五表 manifest 仅时间戳不同
  - [x] **快照运行口径（20:38）**：写入 `docs/v3_phase_F02_validation.md` §5.5——必须连 `scripts/` 一起快照并从快照运行；只设 `PYTHONPATH` 会被脚本的 `sys.path.insert` 绕过
  - [x] **n=200 000 同口径双跑复核（20:52 完成）**：A 20:44、B 20:51:59 各完成一次；`freeze.json` 七字段逐位一致（freeze `5a101174…52cc` / per_user `a6c100e3…2901` / decision `368c1d89…ee42` / guardrail `f6b1bd3c…4d45`）；六个汇总表逐字节相同；`five_tables/` 27 文件中 26 个逐字节相同，仅 manifest 时间戳不同；manifest 仅代表五表路径与其 sha 不同
  - [x] **快照机制实测（20:48）**：`out/snap_test/` 复制 `src/sql/configs/scripts`，快照内脚本以 n=2 000、rep 0、`--status engineering` 跑通；manifest 48 个 `source_hashes` 与主仓库逐项相同（字典 sha256 `0605947…71bd`），路径字段均指向快照；**相对 `--out-root` 会落到快照根**，正式运行必须绝对路径。冒烟产物不作证据
  - [ ] **评审后源码复验**：D03 评审已改 `v3_models.py` 的斜率 docstring（行为不变，但 `source_hashes` 已变）；E/F01 评审可能继续改源码。**所有评审修改落地后、建正式快照前，用最终源码再做一次 n=20 000 双跑**，确认 `freeze.json` 七字段一致，再建快照
- [x] **F02 决策层（18:24 完成）**：两条预声明主张（定向−不发券、定向−同预算随机）各做单侧检验，按 `evaluation.decision.benefit_evidence` 组成 Holm 家族（单侧 α=0.05），输出原始 p/调整阈值/调整 p/通过标记/反演下界；护栏复用 `design/guardrail.py` 的 0.005 非劣效、单侧 0.05，指标 `any_refund_30d_per_assigned_user`；`per_user` 新增 `observed_any_refund_30d`，`arm_summary` 新增退款人数/退款率；`decision.csv / guardrail.csv / decision.json` 与 `freeze.json` 同批先落盘，之后才读真值；F02 11 项测试绿
- [x] **F01 单 rep 历史留出 OPE（20:17 完成，R=0，未证实）**：`v3_f01.py` + `scripts/31_f01_ope.py`，冻结先于审计（freeze_id `3ab44dcb…`，源码哈希 `7012a17b…`）；D03 rep0 n=200k、chosen=`constant`、test 60k，与 E 的 7 列选人哈希及 0.2 档三项数字逐位一致（23 437 人 / 预测成本 11 999.505475 / 审计 0.085638）；DR 主口径两条家族对比 Holm 均拒绝（调整 p 均 0.033431，下界 +0.005137 / +0.010225），但“定向优于同预算随机”只有 DR 显著（IPW p=0.063、SNIPS p=0.088）；真值审计误差 −0.020174 / −0.074016，随机基线符号相反；实际支出超预测预算 28.4%；证据 `outputs/evidence/f01_ope/`、七表 `outputs/tables/v3_phase_F01_*.csv`、正文 `docs/v3_phase_F01_ope.md`，10 项测试绿
- [ ] **F01 独立科学评审**：按 `docs/v3_phase_F01_ope.md` §7 检查单；评审前 F01 仍为“未证实”
  - [x] **主负责数值预复核（21:15）**：`family` 两条 DR 调整 p 均 0.033431、下界 +0.005137/+0.010225；0.2 档 IPW 0.063065、SNIPS 0.087814；`audit` 定向 0.085638、误差 −0.020174，随机误差 −0.074016 且符号相反；`policy_meta` 23 437 人、预测成本 11 999.505475，`audit` 实际支出 15 410（+28.4%）；与 E 的 0.2 档贪心逐位一致
  - [ ] **评审代理（21:15 重启）**：写入 `docs/reviews/v3_phase_F01_review.md`，若已有文件则追加、不覆盖；返回后逐条复核 P0/P1
- [x] F01 改动后全量串行测试 1 248 项 exit=0（20:20:35–20:28:04，单进程，无并发写盘），日志 `outputs/runs/f01_tests/full_suite.log`
- [x] **F01 小项（18:24 完成）**：`v3_ope.cost_and_guardrail` 的 `confidence` 默认改为 `None`，运行时读 `evaluation.confidence_level`，不再写死 0.95。
- [x] 全量串行测试（决策层改动后）1 228 项复跑 exit=0（18:24:43–18:31:47，单进程），日志 `outputs/runs/f02_tests/full_suite_after_decision.log`
- [ ] 独立科学评审 → F 判定

## 收尾交接（2026-10-25 14:40（北京时间））

**A/B/C 通过；D 实现层通过双评审，D02 未完成；正式 R=0（该时点）；E/F/G/H/Z 未开始。**
（**2026-10-26 08:35 更新：正式 R = 1000 已完成，AA 子项通过；见下方 D02 行。本行保留为 14:40 的历史状态**）

- [x] D.1 MDE（176 项，CSV 732×66，含护栏与边界格编码）
- [x] D.2 AA（24 项，pilot R=50/n=1 万）
- [x] D.3 模型+DR（52 项）
- [x] D.4 装载优化（17 项，已切换，字节级等价）
- [x] **D02 的 AA 子项**：四层各 250、合计 1000 跑完。池化 **FPR 0.046、CP [0.0339, 0.0609] 含 0.05**；
      15 格 CP 全含 0.05；SE 校准 0.987–0.995；本 R 功效 0.813/0.918（逐层）、0.960/0.997（合并）。
      文档 `docs/v3_phase_D_aa_formal.md`（机制部分在 `v3_phase_D_aa.md`，两份**不互引数字**）
- [x] C6：SE 校准 + 本 R 实际功效 —— 已完成，写入 formal 文档 §2
- [x] **D02 的负对照**（100 次 × n=20 万，4.37 CPU·h）：购买率 size **0.080**
      （CP [0.0352,0.1516] 含 0.05、二项 p=0.128；点估计偏高须披露）、利润功效 **1.000**
      （真值约 −0.56 元/人 ≈ 4×MDE，应全拒）。产物 `outputs/tables/v3_phase_D_aa_nc20w_L0.csv`
- [x] **D02 第④项（功效格）**：15 格 × 100 次 = **1500 次实测**完成，
      产物 `outputs/tables/v3_phase_D_local_power_formal.csv`（15×62）。
      功效曲线 0.04–0.08 → 0.28–0.33 → 0.78–0.87 → 0.97–1.00 → 1.00；
      `achieved_effect_analytic` 与 target 的相对偏差 **1.96e-15**（构造正确）；
      3 个 `boundary_zero_margin` 格（三层的 `mde100`）已单列，不得计入"可检出"。
      写入 `docs/v3_phase_D_aa_formal.md` §7。**D02 证据齐备，但仍待独立评审**
- [x] DR 设计概率敏感性 + `propensity.primary` 关系 + raw 诊断（C7，`515b75a`）
      ——**主控复核通过**：61 项独立复跑全绿；真接入 `crossfit_dr_ate`、默认仍 `estimated`；
      敏感性表 `outputs/tables/v3_phase_D_models_sensitivity.csv`（R=3、非正式）
- [x] D.3 文档三处修正（C8，`9f3250c`）——**主控复核通过**（含"任何漂移都会报错"的错说法已纠正）
- [x] 工程评审四项（`568c447`）——**主控复核通过**：双装载器改活调用点并反证两条路径各跑一次 /
      PRAGMA 用 PROBE 注入恢复覆盖 / `from_manifest` 读时校验 `source_hashes_before` /
      C 代表库重放 248 产物 0 不一致（4 个 `identical_content` 仅差 `attrs.source_path`）
- [x] 可审计绿灯凭据（`outputs/v3/pytest_handoff/gate.json` + `junit_head*.xml`）
      ——**但 1123 项里 2 项在 AA 并行写盘时因文件锁失败，单独跑均通过**；
      正式绿灯须在 AA 结束后无并发窗口重跑一次。1008/1034 差额已解释：
      `7771d7b`=1098、`ef8f051`=1114、C7 后=1123，旧数字是旧时点
- [ ] 功效格实测拒绝率（C3）：入口已复核（29 项测试绿、20 格全可达、可达域余量 ≥33%），
      正式 15 格（L0/L1/L2，58.3 CPU·h）待 AA 结束后排期；L3 的 5 格按 14:45 裁决不跑
- [ ] 修 `_output_registry_lock` 未捕获 `OSError` 的健壮性缺口（Windows 共享冲突会抛
      `PermissionError` 而非 `ActiveValidationError`）；**AA 运行期间不改 `src/`**
- [ ] E 策略优化 → F 观测闭环 → G 正式重复 → H 长稿 → Z 清理

**纪律（两次踩坑换来的）**：正式重复必须"运行期间源码只读"，用快照或冻结仓库；
绝不允许正式跑与开发写盘并行。

## 后续范围，不可因上下文长度丢失

- [x] B：金额账务舍入、条件真值、L0控制/AA、L3双旋钮积分、独立高精度校验。
- [x] C：全场景五表污染清洗SQL、训练变换、时间成熟、真值隔离、代表DB。
- [ ] D：20pilot实测、MDE/完整AA、四主模型与适用DR、时间模型与PSM目标核验。
- [ ] E：成本和策略、精确求解互证、桶宽/规模扫描、预算超支。
- [ ] F：交叉拟合OPE、配对区间/拒绝规则、独立20万策略验证、最后审计。
- [ ] G：Tier1/Tier2全部正式作业、bootstrap/名单、失败恢复、MC精度/资源。
- [ ] H：12篇核查、三方法图原生PPT/SVG/PNG/清单、结果图、50–100页长稿和比例审计。
- [ ] Z：当前证据逐项验收、v2清理单独commit、最终完整汇报。

## 风险与反思

旧数字不得进入v3；旧README和TODO漂移证明需要机器来源。40–55 CPU小时及8–12小时墙钟仍为未验证估算，完整枚举可能更多格，不能擅自削减。详见docs/v3_决策与反思日志.md。

## B 实施与验收

- [x] 金额/时间、四层概率、L0人工控制、实际订单与审计账集成；首次全套515项测试通过。
- [x] 入口拒绝未支持的机制语义，防止改配置但生成逻辑不变。
- [x] 数值误差传播到元单位；实现稳定求和和坏行按需积分，近零测试通过且保留1e-6门槛及失败路径。
- [x] 独立拒绝抽样/整数账务MC、5000人L0可行域及配对校验落盘。
- [x] 修复后552测试通过，独立B复审通过；22源文件与最终验证hash一致。
- [x] B状态与精度/自然成本解释边界更新；里程碑commit以Git日志为准。A提交为5020c56。

## C 实施清单

- [x] 全73场景实际生成五表、污染/修复血缘、主外键与分币质量校验，完整工程范围通过。
- [x] SQL双窗口/退款/多单/时间快照；四个20万人代表库逐行独立复核，闭端点±1ULP与入库边界负例通过。
- [x] 训练专用预处理、分层/时间拆分、ObservedDataset白名单及隔离，803项全回归通过。
- [x] 工程入口、源哈希清单、封存审计及恢复读取；101清单通过，CLI四格另补验，独立C评审最终通过。
- [x] C-R09按原流重播mask并逐值校验，分别记录选中/改变；C-R10单场景CLI沿用生成器canonical前缀，旧失败证据保留。
- [x] 20功效模板仅继承合同核验通过，actual_n=0；实际机制不能记为C已执行。
- [ ] D：独立20×三粒度pilot后校准20个实际功效机制；禁止静默用原始效应代跑。
- [x] C批准/数字汇总、交接和分钟级维护时间要求已落盘；本轮按用户要求交接，不启动D。


## D 实施（2026-10-25 11:05 起）

- [x] D.0 资源 pilot：4 rep × 三种粒度实测，落 `docs/v3_phase_D_pilot.md` 与 `out/v3_phase_d/`。
- [!] **资源门槛**：外推 ≈1,186 CPU·h，超原估算 22–30 倍；按协议须重商，**未获裁决不启动 G、不擅自减 N/R**。
- [~] D.1 固定 N 反算 MDE 与 20 个功效格校准（子代理 A）。
- [~] D.2 完整 DGP AA 机制（子代理 B）。
- [~] D.3 四主模型 + L1/L3 适用 DR-learner 与统一重复（子代理 C）。
- [~] D.4 `_load_facts` 批量插入优化与 C 回归重绑（子代理 D）。
- [x] D.1 接口冻结（`src/causal_growth/design/v3_power.py`）：`profit_mde` / `profit_power` /
      `purchase_mde` / `purchase_power` / `split_counts` / `holm_per_test_alpha` /
      `multiplier_*` / `design_sample_profile` / `calibrate_power_cell(s)` / `build_mde_rows`。
      唯一口径近似：单侧 α 仍取 0.05（配置无独立单侧 α），须在文档标注。
- [x] D.3 接口冻结（`src/causal_growth/estimate/v3_models.py`）：`prepare_learning_data` /
      `fit_predict` / `Predictions` / `fit_validation_scorer` / `rank_models` / `learning_curve`；
      低层 `crossfit_nuisance` / `aipw_pseudo_outcome` / `crossfit_dr_ate` / `dr_learner_cate` /
      `causal_forest_estimator`。三条硬约束：禁用特征在接口层抛 `FeatureBoundaryError`；
      同一 rep 只调一次 `prepare_learning_data` 并共享 `LearningData`（pairing 载体）；
      L0/L2 调 `dr_learner` 抛 `ModelNotApplicableError`，不得 try/except 吞掉。
- [x] 修掉一个主控引入的副作用：预算覆盖文件原落在 `configs/v3*.yaml` 的源码绑定 glob 内，
      已移至 `configs/budget/repetition_overlay.yaml`；协议 `config_hash` 仍为 `30511a32…`。
- [ ] D.5 主控集成：四域合并、单独评审、D 阶段总验收。
## 下一位agent的启动顺序

1. 先读AGENT_HANDOFF.md最新节、GOAL.md与C批准/独立评审，确认正式R=0；无需凭旧v2正文重新判断当前阶段。
2. 保留七份冻结配置及现有批准哈希；补时间或改状态不能改写冻结文件，时间维护按AGENTS.md§10。
3. 从D开始：20次×三粒度、每次20万人的pilot，实测CPU/墙钟/峰值内存并按完整矩阵重估。超原估算50%须重商，未经回复不得减N/R。
4. D后依次E/F/G/H/Z；F/G精简留存与审计释放、正式重复、长稿和清理均未完成。旧run_all.py仍是v2入口。

## 运行态更新（2026-10-25 16:17，北京时间）

**正式 AA 已改为脱离会话的独立进程**（原为会话后台作业，会话结束即被杀）。

| 项 | 值 |
|---|---|
| 当前进度 | L0/L1/L2 = 49，L3 = 44（目标 250/层） |
| 数据目录 | 正在写 `_r2_det` / `_r3_det`；历史在 `_formal` / `_r2` / `_r3` |
| 合并脚本 | 已含全部根，按 `[block, rep]` 去重，未跑满只写 `_provisional` |
| 状态查询 | `python scripts/18_aa_status.py` |
| 预计完成 | 约 9.4 小时（北京时间约 01:40 前后） |

**未完成（按顺序）**：

- [ ] **L0 的 100 次负对照**（重启时统一带了 `--no-negative-control`，须补）
      命令：`--layers L0 --reps 1 --negative-control-reps 100`，约 3.9 CPU·h
- [ ] 四层跑满后合并池化（确认输出不带 `_provisional`）
- [ ] 无并发写盘窗口单进程串行跑全量 pytest，产出可审计凭据（日志 + exitcode + 起止时间）
- [ ] 池化 FPR + CP + SE 校准写进 `docs/v3_phase_D_aa.md`
- [ ] 以上完成后才可把 GOAL 的 **D02** 标记为通过
- [ ] 15 格功效跑（58.3 CPU·h，L3 的 5 格已裁决不跑）
- [ ] E 策略优化 → F 观测闭环 → G 正式重复 → H 长稿 → Z 清理

**本会话的局限**：轮次预算约 27 秒/轮，256 轮约 34 分钟，而 AA 需 9.4 小时墙钟——
**本会话看不到 AA 跑完**。因此作业已改为不随会话终止的独立进程，交接信息见 `AGENT_HANDOFF.md`。

## 正式 AA 完成（2026-10-26 01:50，北京时间）

- [x] 四层各 250 次、n=20 万全部跑满；**池化 1000 次 FPR = 0.046，CP [0.0339, 0.0609] 含 0.05**
- [x] SE 校准 0.987–0.995（池化 0.995），与独立评审的 1.020 互证
- [x] 全量串行回归 **1123 passed / 0 skipped / 322.76 s / exit 0**，凭据 `outputs/v3/pytest_gate.json`（含日志 SHA256）
- [x] 新增 `docs/v3_phase_D_aa_formal.md`（pilot 与 formal 分开）
- [ ] L0 负对照 100 次：01:47 那次**误用 `n=10000`**（`--n` 未覆盖默认值），产物作废；
      已按 `n=200000` 重跑（`out/v3_phase_d_aa_nc20w/`，约 4.5 CPU·h，预计 10-26 12:50）
- [ ] **20 功效格实测拒绝率仍 pending**（入口已交付，正式 R=100 需 58.3 CPU·h）→ **D02 未通过**
- [ ] 15 格功效正式跑 → E → F → G → H → Z

**D02 判定**：AA 与护栏已达，但负对照未回、功效格未实测，**不得标记通过**。