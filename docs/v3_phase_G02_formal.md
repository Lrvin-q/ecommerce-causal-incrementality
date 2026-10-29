# G02 正式报告 —— 再训练 bootstrap（200 次）与固定策略 bootstrap（1000 次）

> **合成数据 / 已知 DGP**。本报告只回答"策略价值与决策通过率在 DGP 重抽下是否稳定"，
> 不表示任何真实业务效果。维护时间：2026-10-29 23:15（北京时间）。
> 当前状态：**再训练 200 b 已完成**（17:17:51，`merge_exit=0`），§3 已填；
> §4 固定 bootstrap 已填 4 个 core 格（24 格全表见 G03 §4，取数脚本 `scripts/47_g03_fixed_report.py`）；
> §5 待 41 号在 G03 矩阵跑完后复检。
> **独立评审 23:08 返回 PASS WITH CONDITIONS**（`docs/reviews/v3_phase_G02_review.md`）：
> 8 项数字逐项复现一致，P1-1（跨层"合计通过率"）与 P2-1…P2-7 已按本节 23:15 版修完，
> 关闭确认待复评。

## 1. 设计

| 项 | 取值 | 依据 |
|---|---|---|
| 再训练 bootstrap 次数 | **200**（4 个 core 格 × 50 b） | 用户 2026-10-28 22:26 裁决（任务书口径）；`docs/v3_协议.md` 已同步"合计 200 次" |
| bootstrap 类型 | **参数化 DGP 重抽**（`parametric_dgp_redraw`） | 每个 b 重抽历史总体并重训模型；验证队列固定 |
| 历史 rep 编号 | `1 000 000 + b`（`RETRAIN_OFFSET`） | 与 D 阶段 AA 的 rep 空间隔离 |
| 验证 rep | **0**（固定） | `VALIDATION_REP=0`；验证用户协变量跨 b 逐字节相同 |
| 冻结指纹 | `validation_frame_hash`（用户协变量）、`validation_arm_hash`（臂标签 + 概率） | 均与模型无关；观测哈希含 `issued_action`，**不得**当冻结证据 |
| 固定策略 bootstrap | **1 000 次 × 24 格**，仅主预算档 **0.2 元/人** | 用户 2026-10-28 22:26 裁决② |
| 策略 | `greedy_incremental_profit_per_cost` | 与 E/F/G 主口径一致 |
| 模型 | 各层适用集合中按验证选模 | 选模频率逐格报告（§3） |
| 批准号 | `G02-FORMAL-20261029` | 用户 2026-10-29 批准 |
| 快照 | `out/g02_snapshot`（49 文件，`abaa338a…`） | `v3_g_matrix.py` `6ec009b6…` |
| 预算 overlay | `configs/budget/g02_bootstrap_overlay.yaml`，1 847 B，sha256 `c58d5a905ea75de5f67cb7b5e9e8d3eae85615bb8009d6b49ebb0bb329ec810b`（total 200 / per_cell 50，自 `24582f4` 未改） | `configs/budget/` 不在 `pipeline_source_hashes()`、也不在快照 `source_hashes`（49 文件）内，只能以 sha256 绑定；快照目录有字节副本可人工比对；逐行 `overlay_sha256` 列为空（39 号不填、40 号不读） |

**冻结配置的 800 与实跑的 200**：冻结的 `configs/v3/scenarios.yaml` 中
`retraining_bootstrap_jobs: 800`（4 格 × 200）**没有被执行**——run 由
`configs/budget/g02_bootstrap_overlay.yaml`（total 200 / per_cell 50）与 39 号 runner 参数覆盖，
这是 2026-10-28 22:26 的用户裁决（任务书口径）。`configs/v3/*.yaml` **未改动**，
七文件 hash 仍为 `00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3`。

**冻结帧契约**：验证队列（用户协变量）与随机化臂（`assigned_policy_arm` / `policy_arm_probability`）
必须跨 b 恒定；每个 b 只允许"重训模型 → 重新打分 → 重新发券"这条链变化。
因此 `validation_observed_hash`（整张观测表）**逐 b 变化是设计使然**，不是漂移。

**证据边界**：`create_snapshot` 会把整棵 `configs/`（含 `configs/budget/`）复制进快照目录，但
`snapshot_binding.source_hashes` 的 49 个文件只含 v3 集，**不给 overlay 记账**；因此 overlay 的身份
只以表中 sha256 绑定（快照树里有字节副本，可人工比对）；
`run_state.json` 在该格 50 b 全部跑完后才写出，是摘要而非运行期凭据（续跑按 `repetitions.csv` 已有 b）。

## 2. 执行与事故记录

| 时刻 | 事件 |
|---|---|
| 10:09–10:15 | 第一轮正式跑启动（旧快照）；4 格各写出 b=0 |
| 10:15–10:26 | 4 格在 b=1 全部 `RuntimeError`：旧指纹 `validation_observed_hash` 含 `issued_action`，跨 b 必变。守卫在写 b 行前抛出，**无坏行入库** |
| 10:26–10:28 | 修复：`run_validation_arm` 新增两个模型无关指纹；39 号改断言新指纹；续跑遇旧表缺列直接拒绝 |
| 10:29–10:38 | 全量单进程串行 pytest **EXIT=0**（`out/pytest_g02fix_20261029_1029.log`）；n=2000 × 4 格 × 2 b 冒烟通过 |
| 10:39 | 新快照 `out/g02_snapshot`，4 格从 b=0 重开 |
| 10:46 | 补修 `command_merge` 里**同一坏指纹的第二次出现**（原会在收尾合并时必败）；新增 3 例合并守卫测试 |
| 10:53 | 越过首轮失败点：b=1 写出，两新指纹跨 b 唯一，观测哈希 2 个值 |
| 11:37 | 按运行期实测每 b 墙钟中位 **8.0 min**（24 个间隔，4 路），把 `g03_post` 看护窗口从 40 h 改为 **120 h** 并重启（PID 3883）——原窗口必然在阶段 B 结束前超时 |
| 11:41 | 启动只读取样器 `out/g04_monitor.sh`（10 min/次，120 h）：磁盘、四格行数、python 进程数与总 RSS、三个状态文件末行 → `out/g04_logs/monitor.log`（G04 运行期证据） |
| 11:42 | 用真数据半成品跑 `39 merge` 探针：**EXIT=0**、帧校验全过、`rows=29`、`provisional=true`；写到 `outputs/tables` 的 `_provisional` 件当场删除，防止误当证据 |
| 11:44 | 修 40 `--check` 判据错误：原把"50 个 b 共用 `VALIDATION_REP=0`"报成 `validation_rep` 重复——完整正确格必被误判、尾链必 ABORT。改为 `history_rep_id` 查唯一、`validation_rep` 查恒定；新增 3 例测试（6 passed），真数据半成品复跑只剩"未跑完"类问题 |
| 17:17:51 | **4 格 × 50 b 全部完成，39 号合并成功**（`out/g02_logs/post.status` 两行原文：`merge_exit=0` / `OK: G02 merge 完成 2026-10-29T17:17:51+08:00`；该文件**未随证据导出**，只在现场） |
| 18:04:39 | 40 号复算一致（200 行，max\|Δ\| ≤ 1e-12，`provisional=false`）并导出 18 个文件到 `outputs/evidence/g02_formal/`（`coverage.json` 的 `exported_at`）；33 号登记 G02 的 **1 条**身份记录（`snapshot_binding.json`），顶层累计 **92 条**（幂等、CRLF 保留） |
| 17:20–17:51 | 固定策略 bootstrap（Stage A，24 格 × rep 0）首跑：23 格成功，`L1_cost_prediction_under` 因成本预测乘子 0.8 未实现而 `NotImplementedError`，`fixed_exit=1` |
| 18:05–18:37 | 实现乘子（预测端生效、真实成本不变；对数噪声仍拒绝）并补测试后重跑；新快照 `6fdaf7bb…`（旧尝试归档 `out/g02_fixed_attempt1_20261029_1751`），24 格全过（`fixed_exit=0`），18:37:06 进入阶段 B |

失败现场保留：`out/g02_retrain_failed_20261029_1026/`（4 格 b=0 表 + 日志）与
`out/g02_snapshot_failed_20261029_1026/`。事故根因与反思见 `docs/v3_决策与反思日志.md` 10:26、10:46 两条。

## 3. 再训练 bootstrap 结果

数据源：`outputs/tables/v3_phase_G02_retrain_bootstrap.csv`（39 号合并表）与
`outputs/evidence/g02_formal/`（逐 b 表）。取数脚本：`scripts/46_g02_report_numbers.py`
（只读上述两处，不写证据区；2026-10-29 19:22 运行）。

**表 3-1　再训练 bootstrap：4 格 × 50 b（`policy_value` 单位：元/人）**

| 格 | b | 均值 | sd | MC SE | 95% CI | decision 通过 | guardrail 通过 | CPU·h |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| L0_P_main | 50 | 2.3556 | 0.0497 | 0.0070 | [2.3419, 2.3694] | 2/50（0.04） | 50/50 | 6.03 |
| L1_main | 50 | 2.8573 | 0.0417 | 0.0059 | [2.8458, 2.8689] | 49/50（0.98） | 50/50 | 6.50 |
| L2_n200000_p050 | 50 | 2.8514 | 0.0598 | 0.0085 | [2.8348, 2.8680] | 47/50（0.94） | 50/50 | 6.36 |
| L3_fixed_lt000 | 50 | 2.9839 | 0.0662 | 0.0094 | [2.9656, 3.0023] | 45/50（0.90） | 50/50 | 6.48 |
| **合计（仅工作量）** | **200** | — | — | — | — | **不设合计** | **不设合计** | **25.37** |

**合计行只汇总工作量**（b 数与 CPU·h），**不给 decision / guardrail 的跨层通过率**：
四格是一个 DGP 家族的层水平偏移，把四格相加得到的比例不是任何总体的通过率（送审包 §4.1、AGENTS §12.5）。

选模频率（逐格，50 b）：

- L0_P_main：causal_forest 21、s_learner 15、t_learner 9、constant 5、dr_learner 0；
- L1_main：causal_forest 30、s_learner 14、t_learner 3、dr_learner 2、constant 1；
- L2_n200000_p050：causal_forest 28、s_learner 16、constant 3、t_learner 3、dr_learner 0；
- L3_fixed_lt000：causal_forest 21、s_learner 16、dr_learner 6、constant 5、t_learner 2。

**L0 的低通过率不是"策略价值低"，而是"决策口径是两条比较的合取"。**
`decision_all_pass` 要求两个 Holm 校正比较同时拒绝（定向 vs 不发券、定向 vs 同预算随机），
`decision_lower_min` 取两者校正后下界的较小值：L0 的最小值为 **-0.2156**，
说明多数 b 里决定合取的那条下界仍在 0 以下。
**证据边界**：把这一支归给"定向 vs 同预算随机"，依据是运行期 decision 表与 F02 的同向结果；
逐 b 的两条子主张下界**未随证据导出**（39 号以 `target_dir=None` 调验证臂，
`scripts/39_g_retrain_bootstrap_run.py:250`），因此 `outputs/evidence/` 只能复算这个较小值，
不能独立重建归属。
策略价值本身（2.3556，MC SE 0.0070）与另三格同量级；两者不矛盾——
"发券比不发券值钱"与"定向比随机发券更值钱"是两句话，决策通过率只回答后者的合取。
这与 F02 的结果方向一致（定向 vs 同预算随机的区间跨零），不是新结论。

**解读纪律**：50 b 的 MC SE 只有 0.006–0.009，只够判断"量级与方向是否稳定"，
不得把 4 格的点估计当作总体参数的无偏估计；四格同属一个 DGP 家族的层水平偏移，
**不同格之间不得按"独立证据"平均**（AGENTS §12.5）。guardrail 200/200 只说明退款率护栏未报警，
不说明策略最优。**通过率（0.04 / 0.98 / 0.94 / 0.90）是跨 b 的描述性统计，不是验收阈值**；
正式判定单位是每个 b 内的单侧 Holm 检验，与长稿 3.1、3.7 的写法一致。

## 4. 固定策略 bootstrap 结果（2026-10-29 19:50 填；Stage A 18:37 完成）

**状态**：Stage A 于 18:37 完成，24 格 × rep 0、`resamples=1000`、预算档 0.2 元/人，`fixed_exit=0`。
本文数字的唯一来源是 `outputs/tables/v3_g03_fixed_bootstrap_summary.csv`（`scripts/47_g03_fixed_report.py`
从 `out/g02_fixed/shards/<cell>_s0000/<cell>/rep0/validation/fixed_bootstrap.csv` 生成，逐格断言
"单行 / 预算 0.2 / 重抽 1 000"），不是手工从 `out/` 抄写；41 号收尾时会把 24 行原件导出到
`outputs/evidence/g03_formal/fixed_bootstrap.csv` 并再做一次同口径校验。**24 格全表见 G03 报告 §4**
（Tier1 4 格 + Tier2 20 格分区呈现，Tier2 不得与本表并列）。本节只列 4 个 core 格：

| 格 | n_targeted | n_random | 点差 | bootstrap SE | 95% CI | CI 跨零 |
|---|---|---|---|---|---|---|
| `L0_P_main` | 66,594 | 66,713 | +0.0538 | 0.0487 | [−0.0402, +0.1458] | 是 |
| `L1_main` | 66,594 | 66,713 | +0.2022 | 0.0560 | [+0.1009, +0.3131] | 否 |
| `L2_n200000_p050` | 66,594 | 66,713 | +0.1788 | 0.0549 | [+0.0740, +0.2852] | 否 |
| `L3_fixed_lt000` | 66,594 | 66,713 | +0.0128 | 0.0552 | [−0.1000, +0.1205] | 是 |

**口径**：点差 = 定向臂 − 随机臂的净利润差（同 rep、同批用户、同预算，按选中模型配对，AGENTS §12.6）；
CI 为 1 000 次用户级 bootstrap 的 2.5%/97.5% 分位。预算恒 0.2、`resamples` 恒 1 000（脚本断言通过）。

**解读**：`L1_main`、`L2_n200000_p050` 的区间完全在 0 上方；`L0_P_main`、`L3_fixed_lt000` 的区间跨零——
后者只表示"rep 0 这一批用户里两臂差不可分辨"，**不是**"定向无效"，也不构成覆盖率证据（§6 第 5 条口径
同 G03 报告：本轮没有注册覆盖率统计量）。这与 §3 的再训练 bootstrap 是两种不同的不确定性口径，
不能混为一谈：§3 每个 b 重抽历史总体并**重训模型**（验证队列固定），本节固定已验证策略、**只重抽用户**。


## 5. 证据与复现（2026-10-29 19:50 状态）

- 证据区：`outputs/evidence/g02_formal/`（40 号导出；**19:42 复检 `--check` EXIT=0**）、
  `outputs/evidence/g03_formal/`（41 号，含固定 bootstrap；**待 G03 矩阵跑完**，当前 `--check` 报
  `matrix: 缺 run_summary.json`，属预期）；
- 校验：`scripts/40_export_g02_evidence.py --check`（已过）、`scripts/41_export_g03_evidence.py --check`（待跑完）；
- 顶层登记：`scripts/33_register_evidence_top.py --dirs g02_formal g03_formal`（人工复核后执行；
  19:42 `--dry-run` 返回 EXIT=2 表示"仍有未完成目录"，不是错误）。

**证据边界（独立评审 P2-6 / P3-4 记录）**：

- `merge_exit=0` 的凭据是现场文件 `out/g02_logs/post.status`（两行原文见 §2），**未纳入 18 件导出**，
  不可迁移；证据区 `logs/post.log` 末行只有"merge 完成"，无退出码。
- 报告 §2 引用的 `out/pytest_g02fix_20261029_1029.log` 同样不在证据区；
- `outputs/evidence/g02_formal/recomputed_bootstrap.csv` 与 `outputs/tables/v3_phase_G02_retrain_bootstrap.csv`
  数值全等（10 个数值列 max\|Δ\| = 0），但**非字节相等**（浮点格式与行尾不同），引用时须注明。

## 6. 局限与结论失效条件

1. **合成 DGP**：所有数字只对该参数化数据生成过程成立，不外推到真实营销。
2. **策略与预算**：只评 `greedy_incremental_profit_per_cost` 在 0.2 元/人档；换策略或预算档不保证。
3. **再训练 b 的样本量**：每格 50 b，MC SE 见 §3；不能据此做逐格显著性判定，
   也**不做逐格覆盖率断言**（本轮没有注册覆盖率统计量）。
4. **Tier2 的固定 bootstrap**：n 与 R 小于 core 格，精度更低，只判方向与量级，**不得与 Tier1 并列**。
5. **验证帧固定**：只覆盖"历史总体重抽"，不覆盖"验证人群换一批"。
6. **结论失效条件**：若 DGP 主参数（转化率、成本分布、效应异质性）超出注册范围，或验证队列被重抽（两指纹变化），本报告结论作废。

## 7. 判定边界

本报告"通过"只表示：**记录准确、断言范围正确**（200 b / 4 core 格 / 固定验证帧 / 200 次按任务书口径 /
固定 bootstrap 仅主预算档）。不表示"定向策略有效"、不表示可上线、不表示 Tier2 已跑满 65 格。
