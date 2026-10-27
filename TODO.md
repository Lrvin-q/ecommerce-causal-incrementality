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
| F 观测闭环 | [~] | E通过，科学评审。**F01 单 rep 历史留出 OPE 已落盘并与 E 同源重跑（R=0，`freeze_id=b8402f30…`，未证实，待评审）；F02 机制/决策层就绪，n=200k 单 rep 已跑通（工程）；F02 正式 200 rep 已批准待跑** |
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
- [~] D01 20pilot 三粒度实测与资源计划（用户 2026-10-28 01:10 已批准 20 rep；G1 纯估计 / G2 五表+SQL / G3 含 CF，约 276 s/rep ⇒ **单进程串行约 92 min**，**须独占机器跑**，否则墙钟失真）
  - [x] 3 rep 试点已完成：`docs/v3_phase_D_pilot.md`，单 rep ≈ 276 s、峰值 1.88–2.47 GB
  - [x] **04:05 核验入口与产物路径（读源码，未跑）**：`scripts/13_v3_pilot.py` 只有 4 个参数（`--scenario` 默认 L1_main、`--n` 默认 200 000、`--reps` 默认 1、`--start-rep` 默认 0），**没有粒度参数**（三粒度是 `run_rep` 内部一次跑完的）；输出固定为 `out/v3_phase_d/pilot_raw_{scenario}_n{n}.csv`（`:307`），且**每 rep 增量落盘**（`:327`），中断不丢已完成 rep；`out/v3_phase_d/` 当前**不存在**，所以既不会覆盖 R=3 的原始表，入库的 `outputs/tables/v3_phase_D_pilot_raw.csv`（2 322 B，09:57）也不在脚本的写入路径上。跑完后再**另存**为 `outputs/tables/v3_phase_D_pilot_raw_r20.csv` 入库，不动旧表
  - [x] **否决 §10 的"3 进程 × 7 批 ≈ 32 分钟"并行方案（04:05）**：与本项"须独占机器跑"直接冲突——pilot 的用途是**资源外推**，R=3 基线（276 s/rep、峰值 1.88–2.47 GB）是独占测的，3 进程并发会让墙钟被竞争抬高、与基线不可比；且 3 × 2.47 GB ≈ 7.4 GB 峰值，F02 双分片已占约 4.8 GB，物理上也不成立。**改为单进程串行 20 rep，接受 92 min**（§10 的算术保留为"若只看 CPU 总量"的参考，不得用于墙钟口径）
  - [ ] **正式 20 rep 未跑**：批准已取得（01:10），但**必须等 F02 200 rep 集齐并合并之后独占机器再跑**（F02 按 04:26 实测投影 **15:30–17:45** 集齐、点估计 ~16:30，合并约 5 min，故 D01 最早 **~18:00** 起；若落到原 11–15 h 区间上界则 19:00 之后。D01 本身约 92 min）；命令 `.\.venv\Scripts\python.exe scripts\13_v3_pilot.py --scenario L1_main --n 200000 --reps 20 --start-rep 0`；另按 §8.4 补 L0/L3 各 1 rep

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
- [x] **E 独立评审（21:24 落盘）**：`docs/reviews/v3_phase_E_review.md`，**PASS WITH CONDITIONS，0 P0 / 6 P1 / 9 P2**；E01/E02 仍“未证实”
  - [~] **P1-1**：`chosen=constant` 使 `tau_hat` 恒定（60 000 行 unique=1），24/24 求解器相等是必然结果；须用非退化价值向量重跑小池/规模表，入口断言 `nunique(tau_hat)>1`
  - [~] **P1-2**：真值 oracle 用 raw `cost_true`（0/10）而策略预算用 `cost_hat`，0.04/0.10 档学习误差被低估 0.25274/0.10526；须同口径重算并加 `truth_oracle_cost_basis`
  - [~] **P1-3**：E 无 `outputs/evidence/e_*`，meta 缺 `git_commit/source_sha256/cfg_hash`；帧与 `run.log` 只在 `out/`；`--from-d03` 重建而非读冻结 CSV
  - [~] **P1-4**：校准个体指标被 0/10 伯努利噪声主导，“不排序/欠离散 1/7”是误读；须改常数基准相对改进并改写正文
  - [~] **P1-5**：1.00 档“实际支出等于预算上限”与表矛盾（实际 50 570 vs 预算 60 000）
  - [~] **P1-6**：误差分解只跑 `chosen=constant`；须补第二个模型（CF/t）配对分解，或全面降级表述
  - > 以上 6 项由主负责自证已修（详见下方 2026-10-28 02:38 条目）；按 AGENTS §7.4，**只有独立复审通过才能记为关闭**，故标 `[~]` 不标 `[x]`
  - [~] **修复进展（2026-10-27 21:44）**：P1-1 入口断言 + `--frame-model causal_forest`（n=20k 冒烟 unique=5 978、sd=0.8974）；P1-2 同 `cost_hat` 口径真值 oracle（constant 帧 0.04/0.10/0.20 = 0.98436/0.99284/0.91780，恒等式残差 ≤3.5e-17）；P1-3 meta 增加 `git_commit/source_sha256/protocol_*`，新增 `--evidence-dir` 导出与顶层 coverage；P1-4 校准增加零模型/Brier/信号 sd 诊断；P2-1/P2-4/P2-8 补相对 gap、拆分 file/dataframe 哈希、每元价值列
  - [x] **全量 CF 重跑（2026-10-27 21:43:56–22:11:07，exit=0，1 360 秒）**：`--from-d03 --models causal_forest --frame-model causal_forest --n 200000 --tag cf`；chosen=CF，帧 60 000 行、`tau_hat` unique=59 861、sd=0.7816；8 产物 + 证据包 `outputs/evidence/e_evidence_rep0/`（11 条记录 6.08 MB：帧、校准逐用户、7 表、meta、coverage）。**该目录已于 2026-10-28 02:38 移至 `out/attic/e_evidence_rep0_stale/`**（守卫加入前的旧产物，其 11 条顶层 coverage 记录同步删除；6 个文件与 `_a`/`_b` 现行证据逐字节相同，另 5 个是过期版本，仅作历史留存）
  - [x] **CF 结果核验（2026-10-27 22:30）**：① 小池 24/24 分币精确 DP；局部交换最大低于精确解 0.3055 元（pool100@0.10），贪心最大低 0.3110 元；MILP“optimal”因解浮点问题可高于分币精确解最多 0.0809 元，**不能再说 24/24 求解器相等**；LP 上界行按设计整行 NaN；② 桶宽 1.00→0.05 元在 0.04 档把相对 gap 从 12.99% 降到 0.48%，0.01 档因可行性丢弃回升到 0.61%，曲线非单调；③ 校准 MAE/RMSE/Brier 相对常数基准仅改进 1.13%/0.22%/0.45%，Pearson 0.085（校准信号上限 0.109，占 78.5%）；④ **1.00 档随机基线实际支出 50 570 vs 预算 60 000，超支概率 0，P1-5 原表述确认错误**；⑤ 分解恒等式残差 ≤2.8e-17，`truth_oracle_cost_basis=cost_hat_primary`，`truth_feasible_under_cost_hat` 全 True；⑥ 60k 规模扫描 MILP 0.21 秒“optimal”且与贪心同集，需在正文说明这是该帧成本高度离散导致的退化
- [ ] **E 正文改写（P1-1~P1-6 + P2）**：按 CF 数字重写 `docs/v3_phase_E_evidence.md` §0/§1/§2/§3/§5/§6/§10/§11；明确 constant 旧表只作配对对照，主张只用 CF 帧
- [ ] **E 修复后复审**：P1 全修并重跑/重写后再次独立评审，才可把 E01/E02 转“已证实”
- [x] `--from-d03` 正式路径小规模验证（14:01，n=2 000、rep=0、600 行 test）：8 个产物 61.1 秒，校准走 validation 处理组 201/400，分解表 `truth_milp_status=optimal`、`truth_milp_cost_basis=truth_cost_floored_at_cost_floor_cny`；产物隔离 `out/e_evidence_fromd03_smoke/`
- [x] **正式数据**：2026-10-27 19:17:51–19:42:28 用 `--from-d03 --rep-id 0 --n 200000` 跑完（D03 正式 rep 0，`chosen=constant`），9 个产物齐：7 张表 + `v3_phase_E_calibration.json` + `v3_phase_E_evidence_meta.json`；帧 60 000 行、sha256 `c8fd698e…c54e0`；阶段耗时 87.7/1.2/42.3/1.0/117.9/967.3 秒。**规模扫描 60k 有 7 档 `time_limit_no_incumbent`（NaN，非 0）**
- [x] E 正文报告 `docs/v3_phase_E_evidence.md`：2026-10-27 19:45 落盘（§2 校准、§7 规模扫描已补实数），明确"桶宽阈值由曲线定、不预设"；observed_value 留给 F01；**文首仍标"尚未独立评审、E01/E02 未证实"**
- [x] 小池表 `time_limit_no_incumbent` 契约补强（2026-10-27 19:45）：原先空 mask 会写 0 花费/0 价值，现整行 NaN；新增 `test_small_pool_no_incumbent_rows_are_nan_not_zero`，策略两文件 57 项绿（`--basetemp C:/cg_t`）；全量单进程串行 1 238 项 exit=0（19:46:59–19:53:48，日志 `out/pytest_full_20261027_1947.log`）
- [x] **A/B 两家族按当前源码重跑（2026-10-28 01:12 / 01:35，各单进程，exit=0）**：A=`constant`（D03 选模，01:12:03–01:35:23，1 149 秒，`--skip-small-pool` 因退化守卫）、B=`causal_forest`（01:35:26–02:04:28，1 742 秒）；两家族 `git_commit=e0048100233b4c6df5cef1931eda0c2704e63815`、`source_sha256` 逐值相同 ⇒ **AGENTS §12.6 的"跨源码版本配对"缺陷已消除**；证据 `outputs/evidence/e_evidence_rep0_{a,b}/`（各 11 条记录），日志 `out/logs/e_r2_{A,B}_20261028_0112.log`
  - [x] **数值零漂移复核（NaN 感知、忽略 `seconds` 列）**：A 与 `out/scratch/e_A_preguard_1917` 只差 4 个新增列（`relative_gap_to_exact`/`mean_value_per_actual_spend`/`true_value_per_actual_spend`/`true_value_per_actual_spend_mean`）+ 7 行 `relative_gap` 由 1.0 改 NaN；B 与 `out/scratch/e_backup_0100` 只差同样 7 行 NaN，`random_long_cf` 零差异、`calibration_cf.json` 逐字节相同；`calibration.json` 新增 23 键、**改动 0 键** ⇒ 正文已引用的每个 A/B 数字继续成立
  - [x] **正文复核发现并更正 4 处文档缺陷**：① §3.4 把规模表的统计量（17 行 incumbent 有限、−4.366e-11）写进了小池小节，小池实况是 24/24 有限、`bound_cny − incumbent_cny` 最小值恰为 0.0、最大 9.660891e-02；② §3.4 把 MILP 行的 `bound_cny`（`v3_policy.py:517` 的 `-mip_dual_bound`，**MILP 对偶界**）当成 LP 松弛界，两种上界已列表分开，并补出 LP 口径的负值行数是 **A 1 行 / B 4 行**（原写"各 1 行"），另补此前未写的事实：小池 `lp_relaxation.bound_cny` 相对分币 DP 有 3/24 格为负、最小 −1.421085e-14 元；③ §6 恒等式残差"5.551e-17"在任何一份留存表里都复现不出来，实况 A=3.469e-17 / B=8.327e-17，属转写错误；④ §7.1 举例"B 的 5 000 @0.30 gap=0.0000152"无此值，实况 1.4616250426002066e-05
  - [x] **新发现并写入正文**：B 的桶宽表有 **15 行负 gap**（恰为 0.60/0.80/1.00 三个非绑定预算 × 5 档桶宽，各 −0.000865 元 / −0.000395%），原因是"精确参照"只对**分币整数化**问题精确；A 无负 gap。桶宽阈值仍未预设
  - [x] **顶层证据登记表修复（2026-10-28 02:38）**：`outputs/evidence/coverage.json` 46 → **35 条**、`total_bytes` 22 788 510 → **15 811 356**，复算全条一致。两类根因：24 号脚本的顶层合并**只清理自身前缀**，`e_evidence_rep0/` 的 11 条旧记录长期滞留（已随目录移至 attic 一并删除）；31 号脚本**只写目录级 coverage.json**，F01 于 00:47/00:49 重新导出后顶层登记的 `freeze.json`（sha `e2c8e5cb…`→`19af2dbd…`、freeze_id `3ab44dcb…`→`bfb26807…`）与 `meta.json`（15 084→17 333 B）未跟随更新。修复动作已写进登记表 `registry_repairs` 字段
- [~] **登记的代码级缺口**：① E 的 meta 没有 `cfg.hash(64)`（=`e1aa4314b8d84b04a26150cb8ccea5a35dbe9b2d514fee724c56570d5b586d75`，只有 `protocol_config_hash`），须从 `outputs/evidence/d03_formal/shard*_summary.json` 交叉读取；补齐要改 `scripts/24_e_evidence.py` 并重跑约 50 分钟，与 F02 正式关键路径冲突，故留待 F02 之后。② ~~顶层登记表的刷新应由 31 号脚本负责~~ **已于 2026-10-28 03:13 修复**（`scripts/31_f01_ope.py:_refresh_top_registry` + 5 项篡改测试，详见 F 段）；24 号脚本因被 E 的 `source_sha256` 绑定，本轮刻意未改
- [~] **P1-1~P1-6 主负责自证已修（待独立复审确认，E01/E02 仍"未证实"）**：P1-1 非退化 B 家族 + 入口断言；P1-2 同 `cost_hat` 口径真值 oracle（残差 A 3.469e-17 / B 8.327e-17）；P1-3 meta 含 `git_commit/source_sha256/protocol_*` + `--evidence-dir` 导出；P1-4 校准含零模型/Brier/信号 sd（两版本各 40 键、39 键逐值相同）；P1-5 1.00 档表述已按表更正；P1-6 A/B 双模型配对分解（A 学习误差 0.58674–0.99284、B 0.63156–0.80158）
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
- [~] **F02 正式 200 rep（用户 2026-10-28 01:10 会话内批准；登记号 `F02-FORMAL-20261028-R200`）**：
      4 分片 × 50 rep，从 `out/f02_formal_snapshot/`（含 `scripts/`）运行、`--out-root` 用绝对路径，
      合并用主仓库 `scripts/30_merge_f02_formal.py --expected-reps 200`；聚合按 rep 配对报告通过率，
      不合并 p 值。启动前置：最终源码 n=20 000 双跑一致（见下"评审后源码复验"）+ `snapshot_binding.json`
      + `outputs/v3/f02_formal/approval.json`（记批准原文/时间/config 与 source 哈希/rep 范围）。
      **内存约束（01:19 实测）**：总 30.8 GB、可用仅 4.8 GB，4 分片并发不成立；先起 1 个分片测单 rep
      峰值 RSS 再决定并发（上限 2）。单进程约 7 min/rep ⇒ 200 rep ≈ 23 h，双分片 ≈ 11.6 h
  - [x] **正式前置：两次独立拟合一致性（20:37）**：n=20 000、rep 0 两个独立进程；`freeze.json` 七字段逐位一致（含 `freeze_hash/per_user_hash/decision_hash/guardrail_hash`），五表 manifest 仅时间戳不同
  - [x] **快照运行口径（20:38）**：写入 `docs/v3_phase_F02_validation.md` §5.5——必须连 `scripts/` 一起快照并从快照运行；只设 `PYTHONPATH` 会被脚本的 `sys.path.insert` 绕过
  - [x] **n=200 000 同口径双跑复核（20:52 完成）**：A 20:44、B 20:51:59 各完成一次；`freeze.json` 七字段逐位一致（freeze `5a101174…52cc` / per_user `a6c100e3…2901` / decision `368c1d89…ee42` / guardrail `f6b1bd3c…4d45`）；六个汇总表逐字节相同；`five_tables/` 27 文件中 26 个逐字节相同，仅 manifest 时间戳不同；manifest 仅代表五表路径与其 sha 不同
  - [x] **快照机制实测（20:48）**：`out/snap_test/` 复制 `src/sql/configs/scripts`，快照内脚本以 n=2 000、rep 0、`--status engineering` 跑通；manifest 48 个 `source_hashes` 与主仓库逐项相同（字典 sha256 `0605947…71bd`），路径字段均指向快照；**相对 `--out-root` 会落到快照根**，正式运行必须绝对路径。冒烟产物不作证据
  - [x] **合并门禁补强（21:18）**：库层 `selected_policy` 必填且跨 rep 唯一；脚本层校验分片 summary 的 `completed_rep_ids` 与 rep 目录一致，并把 `config_hash/source_hashes_sha256/formal_approval/policy/n_per_rep` 与 rep 清单聚合值比对；新增 `tests/test_v3_f02_merge.py` 5 项、formal 2 项，F02 26 项测试全绿
  - [x] **门禁补强后全量串行测试（21:19:21–21:27:19）**：1 248 项 `exit=0`，478 秒，单进程、无并发写盘；日志 `out/logs/pytest_f02_merge_2119.log`（加 `-p no:warnings`）
  - [x] **评审后源码复验（2026-10-28 03:35 完成）**：D03 评审已改 `v3_models.py` 的斜率 docstring（行为不变，但 `source_hashes` 已变）；E/F01 评审未再改源码。用最终源码（commit `7870b9a`）做 n=20 000 双跑 `out/f02_pre_final_A|_B`，两次 exit=0、各 49 s；`out/scratch/compare_f02_prerun.py` 把 `freeze.json` 展平成 7 个叶子键逐位比对（不一致 0），再对 rep0 的 38 个文件逐个字节比：36 个完全相同，2 个 manifest 只差登记字段——`five_tables/manifest.json` 差 `started_at_utc/finished_at_utc`，`manifest.json` 差 `representative_tables_manifest`（含 run 目录名的绝对路径）与其 sha256（已核验 = 各自 `five_tables/manifest.json` 的实算 sha256，A `830e35ea…` / B `0dd150ea…`），即差异全部由时间戳派生，结论"一致（可建快照）"
  - [x] **正式快照与登记（03:39）**：`bash out/scratch/f02_snapshot.sh` → `out/f02_formal_snapshot/`（118 文件，`src/sql/configs/scripts` 四目录，`robocopy /XD __pycache__`）；`out/scratch/f02_prep.py` 核验子进程确实从快照导入（断言 `m.__file__` 前缀 + 解析 root == 快照，避开 venv 的 `__editable__` .pth），`pipeline_source_hashes()` 主仓库 vs 快照 48 文件逐项一致（字典 sha256 `d8327ae0a190a5c2…`，与双跑 summary 同值），`protocol_config_hash=e1aa4314b8d84b04…`，`git_commit=7870b9a191c5`；写出 `snapshot_binding.json` 与 `outputs/v3/f02_formal/approval.json`（含批准原文与时间、口径、rep 范围、冻结裁决规则）。**踩坑**：`f02_prep.py` 首版把 `load_v3_protocol` 从 `causal_growth.config` 导入（凭印象写的），实际在 `causal_growth.v3_config`，ImportError 后才改对
  - [~] **分片执行（03:39 起）**：shard 0（rep 0–49）03:39:18 起、shard 1（rep 50–99）03:51:13 起，均 `--status formal --formal-approval F02-FORMAL-20261028-R200 --resume`、`--out-root` 绝对路径、从快照运行，日志 `out/logs/f02_formal_shard{0,1}_*.log`。**实测（10 min × 20 s，`out/logs/f02_rss_shard0.log`）**：rep 0 独占 366.4 s、选模 `constant`；单进程峰值 RSS **2 337 MB**、常态 1.4–1.9 GB，采样期系统可用最低 3 735 MB（总 30.8 GB、16 核）⇒ 双分片峰值合计约 4.8 GB、最坏可用约 1.7 GB，**只并 2 个分片**。看护 `out/scratch/mem_watch.py` → `out/logs/f02_memwatch_20261028_0351.log`（每分钟一行，可用 <1 024 MB 打 ALARM 并累计 low_streak）。shard2/shard3 由接力脚本自动起（见下）
  - [x] **并发降速实测与排期（04:01 首估、04:08 按模型构成修正）**：单 rep 耗时**由被选中的模型主导**——`constant` 366.4 s（独占）/ `s_learner` 394.9 s / `dr_learner` 402.0 s / `causal_forest` 478.5 s、512.1 s（后四个都是双分片并发时测的）。首估用两分片均值 437 s 得出"有效吞吐 218 s/rep ⇒ ≈12.1 h、~15:45 集齐"，**这是点估计、偏乐观**：按 03:51:13–04:04:30 窗口实测有效吞吐 266 s/rep 算是 14.8 h；按 D03 200 rep 的选模频率（constant 105 / causal_forest 71 / s 12 / dr 7 / t 5）加权 ≈420 s/rep/流算是 11.7 h。**改为区间：11–15 h，即 2026-10-28 15:00–19:00 之间集齐 200 rep，不承诺具体时刻**。三分片需 3 × 2.4 GB ≈ 7.2 GB 峰值 > 可用 4.2–5.3 GB，**不采纳**
  - [x] **无人值守接力（04:02 起）**：`out/scratch/f02_chain.sh 37612 21460` 每 5 min 用 `Get-Process` 判两个分片 PID 是否存活（**判活/判死都先单独验过**：37612/21460 判活、999999 判死），两者都退出后自动 `bash out/scratch/f02_shard.sh 2` 与 `3` 并 wait，日志 `out/logs/f02_formal_shard{2,3}_*.log`
  - [x] **自动收尾（04:04 起）**：`out/scratch/f02_finalize.sh` 每 5 min 数四个分片目录下 `rep*/freeze.json`（`count` 函数已用真目录验过：shard0=3 / shard1=2 / 未建目录=0），四者各满 50 后自动跑 `scripts/30_merge_f02_formal.py --shard-root ×4 --expected-reps 200 --tables-dir outputs/tables --evidence-dir outputs/evidence/f02_formal`，日志 `out/logs/f02_merge_*.log`，最长等 22 h 后放弃并留话
  - [x] **合并门禁"失败要响"实测（04:03）**：拿当前只有 4 个 rep 的状态跑一次合并，输出重定向到 `out/scratch/merge_gate_test/`（**不碰 `outputs/`**），如预期抛 `ValueError: rep 目录数 4 与 expected_reps=200 不符`（`v3_f02_formal.aggregate_f02:359`），临时目录零文件写入、`git status` 干净 ⇒ 自动收尾即使提前触发也只会留下一条失败记录，不会产出半成品聚合表
  - [x] **ETA 改为实测投影（04:26，n=10 rep）**：不再用假设的选模频率加权，直接用已完成 10 个 rep 的实测耗时——mean **460.8 s**、sd 64.8 s、min 366.4（constant）、max 524.2（causal_forest）；选中模型 6 causal_forest / 2 s_learner / 1 dr_learner / 1 constant。按 2 并发投影 200 rep = **12.80 h**，mean 的标准误 20.5 s ⇒ 95% 区间 **11.68–13.92 h**，自 03:45 起即 **15:30–17:45 集齐，点估计 ~16:30**。原记的 11–15 h 区间仍成立、收窄为上值；区间下界 11.68 h 与 04:08 那次"D03 选模频率加权 ⇒ 11.7 h"几乎重合，两条独立路径互证。**注意**：n=10 的选模构成（causal_forest 60%）高于 D03 200 rep 的 35.5%（71/200），但按二项 sd 1.51 算只差 +1.6 sd，**不足以断言选模构成变了**；将在第一波 100 rep 完成时用 n=100 重推一次
  - [x] **顶层证据登记表的同类缺口修复（04:24，即下面 ① 的工具化）**：按 04:07 自记的规则"修机制缺口要 grep 同类脚本"，查出缺口比原记的更宽——`scripts/27_export_d03_evidence.py:255` 与 `scripts/30_merge_f02_formal.py:186` **都只写目录级 coverage.json**，于是 `outputs/evidence/d03_formal/`（含 D03 正式的 `snapshot_binding.json` + `run_manifest.json`）与 `outputs/evidence/f02_n200k_rep0/` 在顶层索引里 **0 条**，而 AA/C3 的 binding 却是登记在案的 ⇒ 评审者从顶层入口找不到 D03 正式的源码绑定，违反 AGENTS §12.1"只用 outputs/evidence/ 就能重建关键数字"。写了 `out/scratch/register_evidence_top.py`：按**可陈述规则**（身份类 JSON = `*binding*.json` / `*manifest*.json` / `freeze.json` / `meta*.json` / `decision.json`，不收 CSV/日志/逐 rep summary）提升，提升前对每个候选**重算 sha256/bytes 并与目录级记录比对**（不符即抛，不拿过期哈希登记），提升后对顶层**全表 41 条**逐条复算，结果 **35 → 41 条、`total_bytes` 15 811 358 → 15 858 444、既有 35 条逐条与顺序均未变（diff 99 增 / 2 删）**，幂等已实测（第二次运行不写盘）。附带白捡一道交叉核验：E 的两个 `meta`、F01 的 freeze/meta 顶层记录与其目录级 coverage.json **哈希逐值相符**。**踩坑两处**：① 目录级 schema 有三种（`files` 是 list / `files` 是 dict / `records` 是 list，且 f01 的 `target` 是**绝对 Windows 路径**），首版只吃两种，靠 `--dry-run` 当场炸出来；② 首版按 target 排序，把 32/35 条既有记录重排成 217/139 行的 diff，改为**只追加**才让 diff 纯增量、评审者能一眼确认其余记录未被动过
  - [x] **查出审计条目里的硬编码"前值"（04:23）**：`registry_repairs[1]`（03:06）的 `total_bytes_before=22 788 510` 与 `reason` 与 `registry_repairs[0]`（02:38）**逐字相同**，而 02:38 之后磁盘上的值已是 15 811 356 ⇒ 该"前值"是假的。根因定位到 `out/scratch/fix_evidence_registry.py:100` 把 `"total_bytes_before": 22788510` 写成常量、`:102` 把 reason 写成常量，脚本跑两次就在审计轨迹里留下一条假前值（`records_before` 用的是 `len(records)`，是真测的，所以只有这两个字段不可信）。处置：**不改写历史条目**（那是带时间戳的审计轨迹），把缺陷连同证据登记进 04:24 条目的 `prior_entry_defects`（记 `recorded_value` / `correct_value=15 811 356` / 佐证文件），并让新脚本的 before 值**一律现读现算 + 与逐条求和交叉校验**，不符就拒绝写盘。新规则：**审计产物里的任何 `*_before` 字段必须是实测，不能是常量；一次性修复脚本一旦被重跑，硬编码的前值就变成假证据**
  - [ ] **合并后待做（不可自动化的部分）**：① 把 **F02 正式证据**登记进顶层 `outputs/evidence/coverage.json`——工具已就绪（`out/scratch/register_evidence_top.py`，同一套身份类规则），合并后直接跑即可；`scripts/30_merge_f02_formal.py:186` 本身仍**不刷顶层索引**，与 27 号脚本同缺口，**机制修复（让 27/30 自带刷新）留到合并后连着全量测试一起做**，运行期不改脚本 ② `snapshot_binding.json` 已复制入库（`outputs/v3/f02_formal/`，sha `2988d069…`、6 920 B）③ 写 `docs/v3_phase_F02_formal.md` 正文与 §11.2 程序豁免记录 ④ 全量串行测试复跑 ⑤ 改完顶层索引后同步 3 处引用（`docs/v3_phase_E_evidence.md:675`、`docs/v3_phase_F01_ope.md:437/468`、本文件 P0-3 条）——**历史记录保留原值、只改现状断言**（04:24 已按此改过一轮）
  - [x] **跨源码版本数值复现（03:52，比双跑更强的核验）**：正式 `shard0/rep0`（快照源码，绑 48 个 v3 文件）vs 18:39 工程跑 `outputs/evidence/f02_n200k_rep0/`（当时源码，绑 46 个）——`freeze.json` 四哈希逐位相同（`5a101174…52cc`/`a6c100e3…2901`/`368c1d89…ee42`/`f6b1bd3c…4d45`）、选模选策同、六个汇总表**全部逐字节相同**、`five_tables` 26 个 artifact 中 **25 个 sha256 一致**（含全部 parquet），唯一不同的是 `lineage/source_hashes_after.json` 自身；差异归因于新增 `evaluation/v3_f01.py`、`evaluation/v3_f02_formal.py` 与 6 个文件内容变更（`v3_models.py 7d31518b→7de5a364`、`v3_ope.py 40010896→f620b369`、`v3_policy.py b8edd3cf→ba058f9b`、`v3_policy_evidence.py 2e6131b3→ca29cdbcc`）。即评审期那 6 处改动对 F02 数值路径**行为保持**，正面回答 AGENTS §12.6 的跨版本配对问题；同一组数字已在 18:39 / 20:44 / 20:51 / 03:39 四次独立运行中复现
- [x] **F02 决策层（18:24 完成）**：两条预声明主张（定向−不发券、定向−同预算随机）各做单侧检验，按 `evaluation.decision.benefit_evidence` 组成 Holm 家族（单侧 α=0.05），输出原始 p/调整阈值/调整 p/通过标记/反演下界；护栏复用 `design/guardrail.py` 的 0.005 非劣效、单侧 0.05，指标 `any_refund_30d_per_assigned_user`；`per_user` 新增 `observed_any_refund_30d`，`arm_summary` 新增退款人数/退款率；`decision.csv / guardrail.csv / decision.json` 与 `freeze.json` 同批先落盘，之后才读真值；F02 11 项测试绿
- [x] **F01 单 rep 历史留出 OPE（20:17 完成，R=0，未证实）**：`v3_f01.py` + `scripts/31_f01_ope.py`，冻结先于审计（freeze_id `3ab44dcb…`，源码哈希 `7012a17b…`）；D03 rep0 n=200k、chosen=`constant`、test 60k，与 E 的 7 列选人哈希及 0.2 档三项数字逐位一致（23 437 人 / 预测成本 11 999.505475 / 审计 0.085638）；DR 主口径两条家族对比 Holm 均拒绝（调整 p 均 0.033431，下界 +0.005137 / +0.010225），但“定向优于同预算随机”只有 DR 显著（IPW p=0.063、SNIPS p=0.088）；真值审计误差 −0.020174 / −0.074016，随机基线符号相反；实际支出超预测预算 28.4%；证据 `outputs/evidence/f01_ope/`、七表 `outputs/tables/v3_phase_F01_*.csv`、正文 `docs/v3_phase_F01_ope.md`，10 项测试绿
- [x] **F01 独立科学评审**：按 `docs/v3_phase_F01_ope.md` §7 检查单；已于 21:28 落盘（见下条），评审前后 F01 均为“未证实”
  - [x] **主负责数值预复核（21:15）**：`family` 两条 DR 调整 p 均 0.033431、下界 +0.005137/+0.010225；0.2 档 IPW 0.063065、SNIPS 0.087814；`audit` 定向 0.085638、误差 −0.020174，随机误差 −0.074016 且符号相反；`policy_meta` 23 437 人、预测成本 11 999.505475，`audit` 实际支出 15 410（+28.4%）；与 E 的 0.2 档贪心逐位一致
  - [x] **评审代理（21:15 重启 → 21:28 返回）**：写入 `docs/reviews/v3_phase_F01_review.md`；P0/P1 已逐条复核并落地（见下）
- [x] **F01 独立科学评审（21:28 落盘）**：`docs/reviews/v3_phase_F01_review.md`，**PASS WITH CONDITIONS，3 P0 / 8 P1**；F01 仍“未证实”
  - [~] **P0-1（已实现，待独立复审关闭）**：`tau_hat` 恒定、"定向优于随机"的机制是"低价券覆盖更多人"⇒ 新增 `v3_phase_F01_targeting.csv`（16 行 × 14 列，覆盖效应/单位人群效应/两个 share），正文 §0.1 第 6 条与 §4.8 改写为"真值优势 100% 来自多覆盖人，不是选对人"（0.2 档 +0.031873 = 覆盖 +0.032608 + 单位 −0.000735；被选人平均真值 τ 定向 0.219238 **低于** 随机 0.221118）。**03:55 独立复算**：16 行"覆盖+单位−增量差"最大残差 1.7e-17、两 share 之和−1 最大残差 1.8e-15
  - [~] **P0-2（已实现，待独立复审关闭）**：随机组不再当单次抽样 ⇒ 新增 `v3_phase_F01_random_seeds.csv`（**1 600 行 = 8 档 × 200 seed**，列含 `audit_n_selected/audit_increment/audit_actual_spend/dr_increment/dr_se`）与 `v3_phase_F01_random_summary.csv`（16 行 × 27 列：均值/sd/q10/q50/q90/`frozen_seed_value`/`frozen_seed_rank_low`/`targeted_minus_mean`/`mc_se`/`z`/单侧 p/`n_random_at_least_targeted` + 7 个 `equal_spend_*` + `note`），正文 §0.1 第 5、8 条与 §4.6 明确"不得写成定向优于随机"。**03:55 独立复算**：8 档各 200 seed；audit 行 `n_random_at_least_targeted` 165/77/15/0/0/1/0/200 与表逐值相同；0.2 档 `frozen_seed_rank_low` audit 0.110 / dr 0.015 相符
  - [~] **P0-3（已实现，待独立复审关闭）**：`outputs/evidence/f01_ope/` 不再只有 freeze/meta ⇒ 现为 **18 条记录、9 490 785 字节**（入库 4 185 712），含 selection/masks/observed/features/truth 五个 gzip 帧 + 11 张正文表副本 + freeze/meta/coverage；顶层 `outputs/evidence/coverage.json` **41 条、15 858 444 字节**（04:24 起；此前 35 条 / 15 811 358），逐条 sha256/bytes 复算一致（03:13 起由 `scripts/31_f01_ope.py:_refresh_top_registry` 自动维护；04:24 由 `out/scratch/register_evidence_top.py` 补登记 `d03_formal` 与 `f02_n200k_rep0` 的 6 个身份类 JSON，既有 35 条逐条与顺序均未变）
  - [~] **P1-1~P1-8（已实现，待独立复审关闭）**：DR "预声明"改为引配置 `evaluation.decision.benefit_evidence`；1.28 SE 尺子改为配对增量 SE（新 `v3_phase_F01_increment.csv` 96 行）；ESS 权重乘 `T/(1−T)`；真值改为冻结后物化并要求 `require_truth_frame(manifest=…)` 比对 `freeze_id`（审计表新增 `audit_truth_sha256`）；HEAD `verify_freeze_manifest` 通过（02:53 重跑绑 live 源码，48 份哈希逐份复算 0 处不符）；E 随机均值口径统一引 CF 表；9 列 vs 7 列哈希分别标注；补等实际支出对照（7 个 `equal_spend_*` 列）
  - [x] **P1-5/P1-8 复验（02:53 重跑 + 03:55 独立复算）**：HEAD `verify_freeze_manifest` 通过、选人帧 7 列哈希与 D03/E 交接一致（`372a1bcc…`）；等支出回归用 200 行逐种子支出行独立 OLS 复算——0.2 档 audit 的斜率 −0.000007170、SE 0.000002784、截距 0.155870691、r² 0.032422922 **全部差 0.000e+00**；`slope_t = slope/slope_se` 16 行最大偏差 0.0；`reliability_passed=False` 在 `ope_vs_audit.csv` 48 行中 7 行（0.04 档 2 行 / 0.8 档 5 行，与正文 §4.5 一致），在 `value.csv` 96 行中 12 行 = **4 个（档,策略）格子 × 3 个估计量**；`sign_agrees=False` 5 行、`holm_rejected=True` 2 行均与正文相符
  - [x] **F01 修复实现（2026-10-27 22:31 起于隔离副本 `out/f01_dev/`，已回写 live 并重跑）**：ESS 权重乘 `T/(1−T)`（`v3_ope.reliability_gate`）；`_value_table` 增每策略相对 no_coupon 的配对增量/SE/z/单侧 p（新 `increment_table`）；`ope_vs_audit` 填 `ope_se/ope_z/ope_one_sided_p`；审计表增 `audit_truth_sha256` 并要求 `require_truth_frame(manifest=...)` 比对 freeze_id；新增 `targeting_decomposition_table` 与 `random_policy_distribution`（200 seed 同预算随机名单、冻结 seed 复现校验、定向 vs 随机均值单侧 p、等实际支出回归）；`scripts/31_f01_ope.py` 增 3 张表、帧双哈希、git commit、truth_sha 与完整证据包。n=200k 单 rep 已按此重跑两次（00:47、02:53），第二次绑 live 源码
- [x] **F01 正文改写（03:16 同步、03:59 再修）**：按 P0-1（定向机制=覆盖+单位效应分解）、P0-2（200 seed 分布与冻结 seed 排名）、P0-3（证据包）重写 `docs/v3_phase_F01_ope.md`。**03:59 主负责自查又抓出两类错并全文改正**：① 5 处把等支出外推写成"8 档全部/8 档全为 0"，实际是 **0.04–0.80 七档为 0、1.00 档 NaN**（该档 200 seed 真实支出零方差、回归不可定义；§4.7 表格本来是对的，错的是 §0.1 第 9 条、§4.7 标题与三条要点、§6 局限性第 7 条、§8 检查单）；② §6 局限性第 8 条把 ESS 门禁写成"5 行未过"，实际是 **4 个格子未过**（`value.csv` 12 行 = 4 格 × 3 估计量；`ope_vs_audit.csv` 7 行）。§8 检查单同时补上可复算的具体值（1 600 行表结构、8 档 `n_random_at_least_targeted`、1.7e-17 残差、slope_t 偏差 0.0）
- [x] F01 改动后全量串行测试 1 248 项 exit=0（20:20:35–20:28:04，单进程，无并发写盘），日志 `outputs/runs/f01_tests/full_suite.log`
- [x] **F01 与 E 同源重跑（2026-10-28 02:52:56–02:58:05，单进程 exit=0，296.9 秒，日志 `out/logs/f01_rerun_20261028_0253.log`）**：`freeze_id` `bfb26807…` → **`b8402f30d82c96af…`**，`source_hash_combined` `71ec6104…` → **`d3e169f1bd3d7822…`**；48 份源码哈希里**只有 1 份变**（`policy/v3_policy_evidence.py` `18ac6f40…`→`ca29cdbc…`，正是 E 绑定的那份），而 F01 链路不 import 该模块（grep 为空）⇒ 数字不可能动。动机：00:47 的 F01 与 E 的 A 家族**不同源**，属 AGENTS §12.6 禁止的跨版本配对，现已消除
  - [x] **零漂移复核（`out/scratch/verify_f01_rerun.py` → `out/scratch/verify_f01_r3.txt`，exit=0）**：11 张正文表 **10 张逐字节相同**，唯一不同的 `v3_phase_F01_audit.csv` 只有 `audit_freeze_id` 一列 32 行随 freeze_id 变；4 个 gzip 帧 + `tables/` 11 张副本与 00:49 备份逐字节相同；`meta.json` 键数 31→31、无增无删，共同键只 6 个变（`stage_seconds` / `random_policy_distribution.seconds` / `artifacts.audit.sha256` / `freeze.*` / `source_hashes` / `source_hash_combined`），**没有一个是结果数字**；`selection/user_id/design_probability/nuisance/真值帧` 哈希、`budgets`、`family_contrasts` 全逐位相同；目录级 coverage 18 条复算一致（`total_bytes` 9 490 783 → **9 490 785**，差 2 字节来自 freeze/meta 两个 JSON 长度）；DR 主数字复现 +0.065463 / +0.085714（Holm 均 0.033431、均拒绝）、审计误差 −0.074016 / −0.020174 / +0.053841
- [x] **顶层登记表刷新的根因修复（03:13，即上面缺口 ②）**：`scripts/31_f01_ope.py` 新增 `_rel_posix`（`:132`）与 `_refresh_top_registry`（`:140`），导出证据后自动刷新顶层 `outputs/evidence/coverage.json` 里自身前缀的记录（sha256 / bytes / `freeze_id` / `created_at_in_file` / **`source`**），清掉该前缀下已消失的记录，再对**全表**逐条复算——文件缺失、sha256 或 bytes 不符、证据副本与运行产物不一致，一律抛错（只加强不削弱，AGENTS §12.3）。真实数据实跑：35 条全表一致、他前缀 33 条逐条未变、`source` 由旧 `out/f01_ope/` 纠正为 `out/f01_ope_formal_20261028_0253/`、`total_bytes=15 811 358`；备份 `out/scratch/coverage_backup_before_31patch_20261028_031329.json`，可重跑脚本 `out/scratch/run_top_registry_refresh.py`
  - [x] 5 项篡改/边界测试 `tests/test_v3_f01_registry.py` 全绿：他前缀记录原位保留 + 失效记录被清 + `note` 不丢；篡改他前缀 sha → 抛"全表复算"；删他前缀文件 → 抛"文件缺失"；证据副本与运行产物不一致 → 抛错；顶层登记表缺失 → 抛 `FileNotFoundError`
  - [!] **刻意未改 `scripts/24_e_evidence.py`**：它被 E 的 `source_sha256` 逐文件绑定（`6453db227c0349c0…`），改它就必须重跑 E 两家族（约 50 分钟/家族）才能让文档哈希与 live 文件一致；E 侧仍用其内联的"只清自身前缀"逻辑，与缺口 ① 一并留待 F02 之后
- [x] `docs/v3_phase_F01_ope.md` 同步（03:16）：文首维护时间、§0.1 与 §3 的 `freeze_id`、§3 源码组合哈希、§1 表新增"与 E 同源重跑"行；更正证据包字节 4 185 713→**4 185 712**、9 490 786→**9 490 785**（原值与 00:47 和 02:53 两次运行都不符，属转写错）；§3.1 改写为"freeze_id 为什么变了两次"，附第二次变化的单文件归因与逐项复算清单；§3 补两个特征帧哈希口径（`d15cf24d…` 不含 `user_id`、`6a4289ef…` 含）以免被误判为矛盾；§7 复现命令改指**入库**参考帧 `outputs/evidence/e_evidence_rep0_a/frame_rep0_constant.csv`（与 `out/` 副本逐字节相同，sha `c8fd698e…`）并写明登记表自检；§8 检查单新增 3 条（顶层索引一致性、F01↔E 同源、单文件归因）
- [x] **全量串行测试（2026-10-28 03:21:18–03:27:42，单进程 384 秒，`--basetemp C:/cg_t -p no:warnings`，无并发写盘）**：**1 264 项全绿、exit=0**，日志 `out/logs/pytest_full_20261028_0321.log`（`out/` 不入库，复现命令一行：`pytest -q -p no:warnings --basetemp C:/cg_t`）。条数是用 `--collect-only` 独立确认的（collected=1264），与日志里 1264 个进度点、0 个 `F/E/s` 标记一致——**不是从日志末尾读的**：`pyproject.toml` 的 `addopts` 已含 `-q`，命令行再给一次会让 pytest 省掉末尾"N passed"汇总行
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