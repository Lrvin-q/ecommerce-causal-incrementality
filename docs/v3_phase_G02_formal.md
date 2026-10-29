# G02 正式报告 —— 再训练 bootstrap（200 次）与固定策略 bootstrap（1000 次）

> **合成数据 / 已知 DGP**。本报告只回答"策略价值与决策通过率在 DGP 重抽下是否稳定"，
> 不表示任何真实业务效果。维护时间：2026-10-29 11:12（北京时间）。
> 当前状态：**正式跑进行中**（10:39 起）；本文件的 §3/§4 数字待收尾后填入，占位符一律写「待填」。

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

失败现场保留：`out/g02_retrain_failed_20261029_1026/`（4 格 b=0 表 + 日志）与
`out/g02_snapshot_failed_20261029_1026/`。事故根因与反思见 `docs/v3_决策与反思日志.md` 10:26、10:46 两条。

## 3. 再训练 bootstrap 结果（待填）

数据源：`outputs/tables/v3_phase_G02_retrain_bootstrap.csv`（39 号合并表）与
`outputs/evidence/g02_formal/`（逐 b 表）。取数脚本：`out/scratch/g02_report_numbers.py`。

待填内容：
- 4 格 × 50 b 的 `policy_value` 均值 / sd / 95% CI / MC SE；
- `decision_all_pass` 与 `guardrail_pass` 的通过率；
- 选模频率（逐格）；
- 每格 CPU·h 与合计。

**解读纪律**：50 b 的 MC SE 只够判断"量级与方向是否稳定"，不得把 4 格的点估计当作
总体参数的无偏估计；不同格之间不得按"独立证据"平均（AGENTS §12.5）。

## 4. 固定策略 bootstrap 结果（待填）

数据源：`out/g02_fixed/shards/<cell>_s0000/<cell>/rep0/validation/fixed_bootstrap.csv`（24 格）；
导出后为 `outputs/evidence/g03_formal/fixed_bootstrap.csv`。

待填内容：
- 24 格的预算（应恒为 0.2）、`resamples`（应恒为 1000）、点差、95% CI、CI 是否覆盖 0；
- 点差 = 定向臂 − 随机臂的净利润差（同 rep、同批用户、同预算，按模型配对）。

## 5. 证据与复现（待填）

- 证据区：`outputs/evidence/g02_formal/`（40 号导出）、`outputs/evidence/g03_formal/`（41 号，含固定 bootstrap）；
- 校验：`scripts/40_export_g02_evidence.py --check`、`scripts/41_export_g03_evidence.py --check`；
- 顶层登记：`scripts/33_register_evidence_top.py --dirs g02_formal g03_formal`（人工复核后执行）。

## 6. 局限与结论失效条件

1. **合成 DGP**：所有数字只对该参数化数据生成过程成立，不外推到真实营销。
2. **策略与预算**：只评 `greedy_incremental_profit_per_cost` 在 0.2 元/人档；换策略或预算档不保证。
3. **再训练 b 的样本量**：每格 50 b，MC SE 见 §3；不能据此做逐格显著性判定。
4. **Tier2 的固定 bootstrap**：n 与 R 小于 core 格，精度更低，只判方向与量级，**不得与 Tier1 并列**。
5. **验证帧固定**：只覆盖"历史总体重抽"，不覆盖"验证人群换一批"。
6. **结论失效条件**：若 DGP 主参数（转化率、成本分布、效应异质性）超出注册范围，或验证队列被重抽（两指纹变化），本报告结论作废。

## 7. 判定边界

本报告"通过"只表示：**记录准确、断言范围正确**（200 b / 4 core 格 / 固定验证帧 / 200 次按任务书口径 /
固定 bootstrap 仅主预算档）。不表示"定向策略有效"、不表示可上线、不表示 Tier2 已跑满 65 格。
