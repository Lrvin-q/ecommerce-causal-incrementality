# D03 正式 200 rep 独立评审

> **合成数据 / 已知 DGP**｜scenario `L1_main`（randomized、`time_mode=static`）｜R = 200｜n = 200 000/rep
> （train 100 000 / validation 40 000 / test 60 000）｜config_hash `e1aa4314b8d84b04…586d75`
> 评审对象：`docs/v3_phase_D03_formal.md` @ commit `d6add2e`（文档时间 2026-10-27 19:25；20:45 的 `3d61dfe` 把 §0 的 `cost_hat` 合规格数由 160 更正为 320）
> 评审时间：2026-10-27 20:56（北京时间）
> 评审人：独立评审，未参与 D03 的实现与正式运行。
> 复算环境：Windows Git Bash；`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`；全部 Python 走 `./.venv/Scripts/python.exe`；
> 只读复算脚本放在 `C:\tmp\d03_review\`，未写仓库内任何目录。
> 约束：未改源码/配置/数据/表格/TODO/GOAL；未写 `outputs/tables` 或 `out/`；未 git commit/push；未跑正式 R；未跑 pytest（本次不需要）。

## 0. 结论

**PASS WITH CONDITIONS**——数字层全部可复现，正文层必须修正后才能把 D03 记为"已由独立评审核验"。

| 维度 | 判定 | 边界 |
|---|---|---|
| 规模与完整性（200 rep × 5 模型、72 000 行网格） | 通过 | 1000 = 200×5、72 000 = 200×5×9×8 逐项核验；无缺格、无重复键、每 rep 恰好 1 个 `chosen=True` |
| 选模频率（105/71/12/7/5） | 通过 | 与四分片 `chosen_model_counts` 逐片相加一致 |
| 校准表（偏差、斜率、Pearson、最差相对偏差） | 通过 | 报告 §3 的 5×7 个数值全部复现，末位舍入一致 |
| 0.20 档策略值与 40 个配对差 | 通过 | 40 个差值、胜负数全部复现（差 0） |
| 双口径合规（hat/true） | 通过 | `hat` 8 000/8 000 条（40/40 个 model×budget 格）全合规；§0 的 320/320（20:45 更正）复核一致；`true` 0.20 档四个比例复现 |
| oracle 均值、share_optimal、选模后悔 | 数值通过、口径有问题 | 数值全对，但 §6 的 0.1143 是"8 策略 × 8 预算的混合平均"，与"选模后悔"不是同一量（P1-3） |
| 证据哈希、快照绑定、合并一致性 | 通过（有保留） | 10 件证据哈希/行数、83/83 快照哈希、1 000/72 000 合并一致；`run.err` 未进证据包（P2-1） |
| 正式报告陈述的真实性 | **不通过** | `docs/v3_phase_D03_formal.md:40`、`:223` 声称"运行期间未改 `src/`"，与 3 个窗口内提交矛盾（P0-1） |
| 结论解释与口径 | **不通过（需改）** | 5 项 P1：群体平均无偏、0.80 档支出混杂、§6 聚合、斜率方向、个体排序结论（`160/160` 已在 20:45 更正为 `320/320`，复核通过） |

边界说清楚：

- **不能判 FAIL 的理由**：分片确实按 12:53:57 的快照运行（83/83 哈希、`combined_sha256=be0d48f4…`、`git_commit=130a309` 全部核验），live `src/` 的后续改动**没有进入**执行路径；10 个关键数字与 7 张报告表都能从已入库的合并表逐字节重建。这是"报告说错了一句话 + 解释越界"，不是"结果被污染"。
- **不能判 PASS 的理由**：正式文档里有一句可被 git 直接证伪的事实陈述（`:40`、`:223`）；按 AGENTS §11.2"绝不允许把正式运行与开发写盘并行"，这属于程序违规。若项目把 §11.2 视为硬门禁，本 run 需要书面豁免或重跑；在完成 P0 修正与 P1 改写前，D03 仍应保持 GOAL.md 的"未证实、待评审"。
- **本评审不写"通过"**：结论是"数字可信、证据可用、正文必须修"。

## 1. 独立复算方法与数字表

### 1.1 复算脚本与口径

只读脚本（均在 `C:\tmp\d03_review\`，只读取仓库文件，不写仓库）：

| 脚本 | 作用 |
|---|---|
| `check_evidence.py` | `coverage.json` 10 件哈希/字节/行数；合并表哈希；快照 83 件哈希 |
| `check_git.py` | 快照与 commit `130a309` 的逐文件比对；live worktree 与快照的差异 |
| `check_grid_identities.py` | 网格规模、键唯一性、`budget=per_user×60000`、`true_total=per_user×60000`、`chosen` 一致性 |
| `check_calib.py` / `check_bias_decomp.py` | 校准斜率/截距恒等式；跨 rep 偏差分解；支出比 |
| `check_merge.py` | 四分片逐 rep 表与网格的 concat-vs-merge 全列比对 |
| `check_oracle.py` | 事后最优、share_optimal、选模后悔 |
| `check_selection_power.py` | 选模命中率、Spearman、chosen 与 5 模型均值的差 |

核心公式（与 `src/causal_growth/evaluation/v3_d03_formal.py`、快照 `v3_models.py` 一致）：

- 选模频率：`pr[pr.chosen].groupby("model").size()`。
- 校准斜率：`b = cov(τ̂, τ_true)/var(τ̂)`；截距 `a = mean(τ_true) − b·mean(τ̂)`（恒等式复算最大误差 0.0）。
- 配对差：同一 `(rep_id, model, per_user_budget_cny)` 上 `V_greedy − V_business`，`V = Σ_{选中} τ_true / 60 000`；`SE = sd(ddof=1)/√200`。
- 预算合规：`within_budget_by_hat/true` 的 rep 均值；`within_budget_by_true = 1[actual_spend_cny ≤ budget_cny]`（复算一致率 100%）。
- 事后最优：同一 `(rep, model, budget)` 在 8 个受约束策略里取最大；`regret = best − policy`；`all_coupon_unconstrained_reference` 不参与。
- 选模后悔：同一 `(rep, budget)` 上 `V_chosen_greedy − max_{5 模型} V_model_greedy`，对 200 rep 求均值与 SE。

### 1.2 规模、选模与网格完整性

来源：`outputs/tables/v3_phase_D03_formal_per_rep.csv`、`…_policy_grid.csv`、`outputs/tables/v3_phase_D03_formal_selection.csv`、`outputs/evidence/d03_formal/shard{0..3}_summary.json`。

| 检查 | 报告 | 复算 | 结果 |
|---|---|---|---|
| `per_rep` 行数 | 1 000 | 1 000（200 rep × 5 模型） | 一致 |
| 每 rep 的 `chosen=True` 个数 | 未写 | 200/200 个 rep 恰好 1 个 | 一致 |
| 每 rep 的 `rank` | 未写 | 每个 rep 都是 1..5 的一个排列 | 一致 |
| 选模频率 | CF 105 / S 71 / DR 12 / constant 7 / T 5 | 105 / 71 / 12 / 7 / 5 | 一致 |
| 四分片加总 | 未写 | shard0（constant 2、CF 32、S 15、DR 0、T 1）+ shard1（2/27/19/2/0）+ shard2（2/25/17/5/1）+ shard3（1/21/20/5/3）= 7/105/71/12/5 | 一致 |
| `policy_grid` 行数 | 72 000 | 72 000 = 200×5×9×8；每 `(rep, model)` 9 策略、每策略 8 预算 | 一致 |
| 重复键 | 未写 | `(rep_id, model, budget, policy)` 重复 0 行 | 一致 |
| `chosen` 跨表一致 | 未写 | `per_rep` 与 `policy_grid` 不一致 0 行 | 一致 |
| `budget_cny` | 未写 | `= per_user_budget_cny × 60 000`，最大误差 0 | 一致 |
| `true_value_per_user` 分母 | 未明写（R1：除以全部 60 000） | `true_total = per_user × 60 000`，最大误差 0 | 一致 |

### 1.3 校准（§3）

来源：`outputs/tables/v3_phase_D03_formal_calibration.csv`；独立从 `per_rep.csv` 复算。

**表 A：报告值 vs 复算值（200 rep，全部模型）**

| 模型 | 均值偏差 | SE | 相对偏差中位数 | 最差绝对相对偏差 | 斜率中位数 | Pearson 中位数 | RMSE 中位数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| constant | −0.0043 / −0.0043 | 0.0044 / 0.0044 | −0.0189 / −0.0189 | 0.7022 / 0.7022 | — | — | 6.178 / 6.178 |
| t_learner | −0.0010 / −0.0010 | 0.0046 / 0.0046 | −0.0054 / −0.0054 | 0.8034 / 0.8034 | 0.1141 / 0.1141 | 0.0426 / 0.0426 | 6.496 / 6.496 |
| s_learner | +0.0022 / +0.0022 | 0.0044 / 0.0044 | −0.0119 / −0.0119 | 0.8456 / 0.8456 | 0.4666 / 0.4666 | 0.0778 / 0.0778 | 6.184 / 6.184 |
| causal_forest | −0.0002 / −0.0002 | 0.0045 / 0.0045 | −0.0111 / −0.0111 | 0.8014 / 0.8014 | 0.7541 / 0.7541 | 0.1029 / 0.1029 | 6.149 / 6.149 |
| dr_learner | −0.0008 / −0.0008 | 0.0047 / 0.0047 | −0.0109 / −0.0109 | 0.8167 / 0.8167 | 0.0976 / 0.0976 | 0.0392 / 0.0392 | 6.561 / 6.561 |

（每格"报告 / 复算"；`relative_bias = bias_mean / tau_true_mean` 逐行恒等，最大误差 0.0。）

**表 B：报告没有报的"单 rep 偏差离散"**

| 模型 | sd(bias_mean) | mean\|bias\| | \|相对偏差\|>20% 占比 | corr(τ̂均值, τ_true均值) | τ̂ 逐用户 sd 中位数 | 反推 τ_true 逐用户 sd |
|---|---:|---:|---:|---:|---:|---:|
| causal_forest | 0.0633 | 0.0500 | 34.5% | 0.047 | 0.838 | ≈6.14 |
| s_learner | 0.0617 | 0.0488 | 33.5% | 0.052 | 1.021 | ≈6.12 |
| t_learner | 0.0649 | 0.0521 | 38.5% | 0.031 | 2.311 | ≈6.19 |
| dr_learner | 0.0661 | 0.0529 | 40.0% | 0.039 | 2.473 | ≈6.15 |
| constant | 0.0622 | 0.0484 | 37.5% | 0.009 | 0.000 | — |

参照：`tau_true_mean` 跨 200 rep 的 sd = **0.0246**。反推口径 `sd(τ_true) ≈ slope·sd(τ̂)/r`，与 `error_sd` 中位数 6.149–6.561 相互印证。

### 1.4 策略值与配对差（§4、§5）

来源：`outputs/tables/v3_phase_D03_formal_policy_value.csv`、`…_paired_diff.csv`；从 `policy_grid.csv` 重算。

**0.20 元/人档（元/人，200 rep 均值）**

| 模型 | random | business | greedy | local_swap | predicted_profit | incremental_profit | all_coupon（参考） |
|---|---:|---:|---:|---:|---:|---:|---:|
| causal_forest | 0.0680 | 0.2718 | 0.2934 | 0.2934 | 0.0934 | 0.2711 | 0.2841 |
| s_learner | 0.0680 | 0.2718 | 0.2796 | 0.2796 | 0.0934 | 0.2609 | 0.2841 |
| dr_learner | 0.0680 | 0.2718 | 0.2256 | 0.2256 | 0.0934 | 0.2040 | 0.2841 |
| t_learner | 0.0680 | 0.2718 | 0.2129 | 0.2129 | 0.0934 | 0.1904 | 0.2841 |
| constant | 0.0680 | 0.2718 | 0.0767 | 0.0767 | 0.0934 | 0.0685 | 0.2841 |

**greedy − business，0.20 档**

| 模型 | 差值 | SE | 胜/负 | 支出/预算（greedy vs business） | 每元价值（greedy vs business） |
|---|---:|---:|---:|---:|---:|
| causal_forest | +0.0216 | 0.0011 | 183 / 17 | 1.054 vs 1.005 | 1.392 vs 1.353 |
| s_learner | +0.0079 | 0.0011 | 146 / 54 | 1.048 vs 1.005 | **1.334 vs 1.353（反转）** |
| dr_learner | −0.0462 | 0.0011 | 0 / 200 | 1.026 vs 1.005 | 1.100 vs 1.353 |
| t_learner | −0.0588 | 0.0011 | 0 / 200 | 1.012 vs 1.005 | 1.052 vs 1.353 |
| constant | −0.1951 | 0.0013 | 0 / 200 | 1.272 vs 1.005 | 0.302 vs 1.353 |

40 个 `model × budget` 的配对差与报告 §5.2 逐格比对，**最大差 0**（报告按 4 位小数）；183/17、146/54、0/200 全部复现。

**支出比（greedy / business，均值）**

| 预算档 | 0.04 | 0.10 | 0.20 | 0.30 | 0.40 | 0.60 | 0.80 | 1.00 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| greedy（CF） | 1.260 | 1.129 | 1.054 | 1.021 | 1.002 | 0.796 | **0.597** | **0.478** |
| greedy（S） | 1.161 | 1.093 | 1.048 | 1.025 | 1.006 | 0.863 | **0.647** | **0.518** |
| greedy（T） | 1.073 | 1.037 | 1.012 | 0.995 | 0.984 | 0.771 | **0.578** | **0.463** |
| greedy（DR） | 1.076 | 1.051 | 1.026 | 1.005 | 0.990 | 0.783 | **0.587** | **0.470** |
| business | 1.004 | 1.004 | 1.005 | 1.005 | 1.003 | 1.000 | 0.999 | 0.824 |

**每元价值（0.80 档）**：greedy CF 0.833、S 0.726、DR 0.691、T 0.671，business 0.356。

说明：`local_swap` 与 `greedy` 的选择在 88.7% 的格完全相同，差值均值 −1.3e-6（`check_grid_identities.py`），两者不是两份独立证据。

### 1.5 双口径合规（§7）

来源：`…_compliance.csv`、`policy_grid.csv`。

| 口径 | 报告 | 复算 |
|---|---|---|
| 报告 §0.5 的 `hat` 合规 | 320/320 格（8 策略 × 5 模型 × 8 档，20:45 更正） | 320/320 行 `share_within_budget_by_hat=1.000`；其中 `no_coupon` 的 40 行是 0 支出平凡格 |
| greedy `hat`，0.20 档 | 1.000（全部模型） | 1.000；8 000/8 000 个 rep×格，40/40 个 model×budget 格 |
| greedy `hat`，chosen-only | 未写 | 1 600/1 600 |
| 8 个受约束策略 `hat` | 未写 | 全部 1.000；无约束的 `all_coupon` 为 0.1275（0.04 档平均 20.6 倍支出） |
| `by_true`，0.20：T / DR / S / CF / constant | 39.0% / 26.5% / 13.0% / 11.0% / 0% | 0.390 / 0.265 / 0.130 / 0.110 / 0.000 |
| `within_budget_by_true = 1[spend ≤ budget]` | 未写 | 一致率 100% |

20:45 的 `160→320` 更正（commit `3d61dfe`）复核通过：`compliance.csv` 中除 `all_coupon` 外的 320 行 `share_within_budget_by_hat` 全为 1.000。需要说明的是，320 里有 40 行是 `no_coupon`（选中 0 人、支出 0），属于恒合规格；若只数发券策略，写"280/280 + 40 个 no_coupon 平凡格"更准确。

### 1.6 事后最优、share_optimal、选模后悔（§6）

来源：`…_oracle.csv`；从网格重算。

| 模型 | 报告"平均后悔" | 复算（64 格均值） | 报告 SE | 64 格均值的 rep 级 SE | 报告 share_optimal（8 策略均值） | greedy-only share_optimal@0.2 | greedy-only regret@0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| causal_forest | 0.1143 | 0.1143 | 0.0009 | 0.00047 | 0.212 | **0.815** | 0.0007 |
| s_learner | 0.1066 | 0.1066 | 0.0009 | 0.00042 | 0.192 | **0.600** | 0.0027 |
| t_learner | 0.1047 | 0.1047 | 0.0009 | 0.00039 | 0.125 | 0.000 | 0.0588 |
| dr_learner | 0.1037 | 0.1037 | 0.0009 | 0.00037 | 0.125 | 0.000 | 0.0462 |
| constant | 0.1317 | 0.1317 | 0.0009 | 0.00046 | 0.125 | 0.000 | 0.1951 |

- 以 CF 的 0.1143 为例（五模型合计为 0.1122）：8 个策略 × 8 个预算共 64 格；其中 `business_rule`、`no_coupon`、`random`、`predicted_profit`、`propensity` 5 个策略与 CATE 模型无关（各模型同值）。CF 按策略拆开：greedy 0.0023、local_swap 0.0024、incremental 0.0141、business 0.0454、predicted_profit 0.1441、random 0.1768、propensity 0.2120、no_coupon 0.3174。
- `share_optimal` 的 0.125 = 1/8 的基线（5 个模型无关策略），不是"12.5% 的 rep 最优"。

**选模后悔（chosen greedy − 5 模型 best greedy）**

| 预算 | 0.04 | 0.10 | 0.20 | 0.30 | 0.40 | 0.60 | 0.80 | 1.00 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 均值 | −0.0114 | −0.0162 | −0.0193 | −0.0205 | −0.0205 | −0.0198 | −0.0188 | −0.0189 |
| SE | 0.0014 | 0.0023 | 0.0030 | 0.0032 | 0.0031 | 0.0025 | 0.0022 | 0.0022 |
| chosen 恰为最优 | 52.5% | 52.0% | 48.5% | 53.0% | 52.5% | 52.0% | 52.0% | 52.0% |

报告引用的 0.04/0.10/0.20/0.40/0.80 五个数全部复现；n=200。

### 1.7 证据、快照绑定、源码只读

| 检查 | 结果 |
|---|---|
| `coverage.json` 10 件文件 | 哈希/字节/行数全部一致；目录实际 11 件（多 `coverage.json` 自身） |
| 合并表哈希 | `per_rep` a0d338ba…、`policy_grid` c8cad782…，行数 1 000 / 72 000，与声明一致 |
| 合并表是否入库 | `git ls-files` 显示两张表已 tracked（10 MB），可作第三方复算输入 |
| 快照 83 文件 | 83/83 sha256 一致；`combined_sha256=be0d48f4…`；`git_commit=130a309…`；`created_at=2026-10-27T12:53:57+08:00` |
| 83 件与 commit 的关系 | 78 件与 `130a309` 一致；5 件是不在 commit 里的 `src/causal_growth.egg-info/*` |
| live `src/` 与快照 | 仅 3 个文件不同：`estimate/v3_models.py`、`policy/v3_policy.py`、`policy/v3_policy_grid.py` |
| 四分片 `run.err` | `out/d03_formal/shard{0..3}/run.err` 均为 0 字节（但未复制进证据包） |
| 四分片 summary | 均 `status=formal_r`、`reps=50`、config_hash `e1aa4314…` |
| 四分片 run.log | 各 50 行 `[D03 rep N]`；首行 elapsed 308.1 s / 307.2 s / 310.5 s，末行 303.2 s |
| 合并一致性 | 四分片 concat 与 merged 逐列数值差 0.0；字符串列全等 |
| 报告表重建 | 用 `scripts/26_d03_formal_tables.py` 重跑 7 张表，与 `outputs/tables/` 逐字节相同（`cmp` 全部 same） |

**窗口内提交（`git log --since="2026-10-27 12:54" --until="2026-10-27 17:14" --name-only`）**

| 时间 | commit | 窗口内改到的 `src/` 文件 |
|---|---|---|
| 13:23 | `df66a3c` | `src/causal_growth/policy/v3_policy.py` |
| 13:58 | `06d4740` | `src/causal_growth/policy/v3_policy.py`、`v3_policy_grid.py` |
| 14:39 | `f2c6dab` | `src/causal_growth/estimate/v3_models.py` |

`run_manifest.json` 的 `started_at=2026-10-27T12:54:18+08:00`；shard 产物 mtime 17:14。上述三个提交都落在窗口内，且改的正是快照里存在的文件。

### 1.8 旧数字 grep

`grep -rnE "0\.0193|0\.0216|105/200|160/160|0\.1007" docs/*.md README.md AGENT_HANDOFF.md TODO.md GOAL.md`：

- 正式文档已无 `160/160`：20:45 的 `3d61dfe` 已更正为 `320/320`，本评审复核 320/320 行合规（见 §1.5）。原先的旧数问题已关闭，不再列为 P1。
- 其余 `160/160` 出现在 `docs/v3_phase_D03_diagnostic.md:174`、`docs/v3_phase_D_models.md:646`、`AGENT_HANDOFF.md:30`、`TODO.md:15,103`，都是 20 rep 诊断，属正确用法。
- `0.1007` 在正式文档 `:22-24` 明确标为诊断、不可外推；`0.0216 / −0.0193 / 105` 的出现处都与复算一致，无其他残留。

## 2. 问题清单

### P0（必须改，否则不能把 D03 标为已核验）

**P0-1 报告声称"运行期间未改 `src/`"为假，且违反 AGENTS §11.2**

- 证据：`docs/v3_phase_D03_formal.md:40`（"四个 `run.err` 全空；运行期间未改 `src/`、`sql/`、`configs/v3*`"）、`:223`（"确认运行期间 `src/` 未改动"）；`outputs/evidence/d03_formal/run_manifest.json` 的 `started_at=12:54:18`；shard 产物 mtime 17:14；窗口内提交 `df66a3c`(13:23)、`06d4740`(13:58)、`f2c6dab`(14:39) 分别改了 `v3_policy.py`、`v3_policy_grid.py`、`v3_models.py`；`C:\tmp\d03_review\check_git.py` 显示 live 与快照的差异恰好是这 3 个文件。
- 影响：这是可被 git 直接证伪的陈述。`run.err` 为空只证明进程没有 stderr，不能证明源码只读；把两者并列作为"源码只读"的证据是逻辑错误。结果本身不受影响（83/83 快照哈希 + `combined_sha256` + `130a309` 已核验），但正式报告的可信度与 §11.2 纪律受损。
- 修复：把 `:40`、`:223` 改写为"分片以 12:53:57 快照运行；live `src/` 在窗口内有 3 次提交（`df66a3c`/`06d4740`/`f2c6dab`），均未进入快照"；把 4 个 `run.err` 复制进 `outputs/evidence/d03_formal/`；在决策日志记录本次 §11.2 违规与豁免/重跑决定。若项目把 §11.2 当硬门禁，则本 run 只能记为"程序违规的正式运行"，需负责人书面豁免或重跑。

### P1（结论/口径必须改，否则会误导下游 E）

**P1-1 "群体平均无偏"是 200 rep 误差抵消，不是单 rep 无偏**

- 证据：`docs/v3_phase_D03_formal.md:15-17`、`:69-73`；`check_bias_decomp.py`。
- 数字：`sd(bias_mean)` 0.0617–0.0661，`mean|bias|` 0.0484–0.0529，`|相对偏差|>20%` 的 rep 占 33.5%–40.0%，`corr(τ̂均值, τ_true均值)` 仅 0.0088–0.0518；而 `tau_true_mean` 跨 rep 的 sd 只有 0.0246。
- 影响：报告把"±0.005"写成均值偏差，读者容易把它读成"每个 rep 都无偏"。实际上单 rep 偏差的 sd 约为真值自身跨 rep 波动的 2.5 倍，模型连"rep 级平均效应"都没有跟随真值。
- 修复：在 §0/§3 增加表 B 的四列（sd、mean|bias|、>20% 占比、跨 rep corr）；把"±0.005"明确写成"200 rep 均值的 SE（0.0044–0.0047）"；结论改为"200 rep 平均无偏，单 rep 偏差 sd≈0.06，不能替代个体可用"。

**P1-2 0.80/1.00 档的"转正"与 0.20 档 S 的胜出被实际支出混杂**

- 证据：`docs/v3_phase_D03_formal.md:129-136`、`:166-171`；`check_bias_decomp.py` 的支出比。
- 数字：0.80 档 greedy 支出/预算 0.578–0.647，business 0.999；1.00 档 greedy 0.463–0.518，business 0.824。0.20 档 S 的 +0.0079 伴随约 4.3% 的额外支出，按每元价值为 1.334 vs business 1.353（**符号反转**）。
- 影响："dr/t 直到 0.80 才转正"与"S 在 0.20 以上胜出"的符号与支出比同向。0.80/1.00 的翻转主要是 business 把预算继续花在边际用户上、greedy 在正 τ 用户用尽后停止（快照 `policy/selection.py:119` 的 `eligible=(v>0)&(c>0)`），不是"模型在大预算下定向更好"。诊断文档 `:147` 原有这条 caveat，正式稿丢了。
- 修复：§5.2 加 `actual_spend/budget` 与每元价值两列；把 0.80/1.00 的结论改为"business 在高预算过度支出、greedy 因正 τ 用户上限未花完预算"；0.20 档注明 S 的增益小于其多花的约 4.3%；恢复诊断的 caveat。

**P1-3 §6 的"平均后悔"是 8 策略 × 8 预算的混合平均，与"选模后悔"不是同一量**

- 证据：`docs/v3_phase_D03_formal.md:139-156`；`src/causal_growth/evaluation/v3_d03_formal.py:240-267`（`best = wide[feasible].max(axis=1)`，逐格取最优）；`…_oracle.csv`。
- 数字：0.1143 的 64 格拆分见 §1.6；5/8 个策略与 CATE 模型无关；greedy-only 的 0.20 档 regret 是 0.0007/0.0027/0.0462/0.0588/0.1951，share_optimal 是 0.815/0.600/0/0/0；报告的 0.212 是 8 策略平均，下界 0.125。报告 SE 0.0009 是 64 个格 SE 的平均，而 64 格均值的 rep 级 SE 是 0.00037–0.00047。
- 影响：0.1143 在五个模型间几乎不变（0.1037–0.1317），主要反映"模型无关策略有多差"，不是模型质量；`share_optimal` 的 0.125 会被误读成"12.5% 的 rep 最优"；`§0.4`"选模后悔远小于事后最优"把"跨模型选模后悔（−0.0193）"与"模型内策略后悔（0.1143）"混在一起。
- 修复：拆成三块：(a) 每模型 greedy 的 within-model regret（8 个预算）；(b) share_optimal 只报 greedy（0.815/0.600/0/0/0）；(c) "选模后悔"单独一节，写清分母是 5 个模型、0.20 档、n=200，并给出 chosen 恰为最优的 48.5%。

**P1-4 校准斜率的方向解释反了：b<1 在本数据里是回归稀释，不是"τ̂ 被放大"**

- 证据：`out/d03_formal_snapshot/src/causal_growth/estimate/v3_models.py:2167`（"`b < 1` 表示 τ̂ 被放大（预测的离散度大于真值）"）；`docs/v3_phase_D03_diagnostic.md:111` 同句；报告 `:82`、`:85`、`:185-186` 沿用"斜率越接近 1 越校准"的读法。
- 数字：τ̂ 逐用户 sd 中位数 0.838（CF）/1.021（S）/2.311（T）/2.473（DR），反推 τ_true 逐用户 sd≈6.12–6.19；`b ≈ r·σ_true/σ_hat`，b<1 主要来自 r=0.039–0.103 的衰减。
- 影响：把"预测被压缩且相关性低"误读成"预测过离散"，会让读者以为校准问题可通过缩放修复；报告"CF 的 0.754 最接近 1"也因此不是"最校准"的证据。
- 修复：改 docstring 与诊断句为"b<1 是回归稀释，不能单独作为过离散证据"；报告加 `sd(τ̂)/sd(τ_true)/r` 三列或分箱校准；"CATE 是否校准"改用分箱均值或 `τ̂ ~ τ_true` 的斜率。

**P1-5 "个体排序能力弱"缺少噪声基线，且与同文的选模/策略证据冲突**

- 证据：`docs/v3_phase_D03_formal.md:15-17`、`:22`；`check_selection_power.py`。
- 数字：Pearson 0.039–0.103；但 chosen 恰为 5 模型事后最优的比例是 48.5%–53.0%（随机 20%），per-rep Spearman(selection_score, true greedy value) 均值 0.727，0.20 档 chosen − 5 模型均值 = +0.0572（SE 0.0031），CF 的 greedy 在 183/200 个 rep 胜 business。
- 影响：把"逐用户 CATE 相关系数低"直接写成"排序能力弱"，会让下游 E 认为策略不可用；但同一份证据显示"头部选择"是有效的。两者需要分开陈述。另一个方向也不能过度：现有导出没有逐用户真值/无噪声 CATE，噪声上限不可识别，"弱"不能全部归因于模型可修复的缺陷。
- 修复：§0/§3 增加命中率、Spearman、chosen−mean 三个选择力指标；把结论写成"逐用户 CATE 相关性低（0.04–0.10），但头部选择显著优于随机与 business；两者不矛盾"；明确噪声上限未识别。

### P2（应改，不阻塞）

**P2-1 证据包本身不能独立重建数字，`run.err` 未导出，checks 有字面 True**

- 证据：`outputs/evidence/d03_formal/` 共 580 KB、10 件；`coverage.json` 的 `notes` 明说"逐用户帧不进证据目录，72 000 行网格已在 outputs/tables/，此处只记哈希与行数"；`scripts/27_export_d03_evidence.py:123-125` 只检查 `run.err` 存在且为 0 字节，不复制；`:192-198` 的 `checks` 除 `run_err_all_empty` 外都是字面 `True`。
- 影响：AGENTS §12.1 的验收口径是"只用 `outputs/evidence/` 就能重建关键数字"；本包单独不满足。好在两张合并表已 tracked，第三方仍能复算，因此不是阻断项，但口径要写清。
- 修复：在 `coverage.json` 明确"复算输入 = evidence + 已入库的 outputs/tables 两表"；把 4 个 `run.err` 复制进证据包；`checks` 改为写出时重新计算的结果，而不是常量。

**P2-2 正式分片产物仍用 `v3_phase_D03_diagnostic_*` 文件名**

- 证据：`out/d03_formal/shard{0..3}/v3_phase_D03_diagnostic_{per_rep,policy_grid,summary}.json/csv`；`outputs/tables/v3_phase_D03_diagnostic_*` 是 20 rep 诊断。
- 影响：两套同名产物（20 rep 诊断 vs 200 rep 正式分片）容易在后续脚本里混用；本次行数与键唯一性检查证明没有混，但命名是脆弱点。
- 修复：正式入口把输出名改成 `v3_phase_D03_formal_*`；或在 manifest 里显式记录三张分片表的行数与 rep 范围。

**P2-3 §4 的 `all_coupon` 对比没有给支出比**

- 证据：`docs/v3_phase_D03_formal.md:103-104`；`policy_grid` 的 `all_coupon` 在 0.20 档实际支出约 4.1 倍预算，0.04 档 20.6 倍。
- 影响："0.20 档 all_coupon 0.2841 低于 CF greedy 0.2934：定向避开了负效应用户"是在 4 倍支出下比较，"避开负效应"没有被单独测量。
- 修复：加 `actual_spend/budget` 列，或把该句改为"在 4.1 倍支出下 all_coupon 仍略低于 greedy"；"避开负效应"需用选中/未选中用户的 τ_true 均值直接证明。

**P2-4 `local_swap` 与 `greedy` 近似同一策略，不是独立佐证**

- 证据：`check_grid_identities.py`：`local_swap − greedy` 均值 −1.3e-6，88.7% 的格完全相等，5.5% 略高。
- 影响：§4 表并列两列且数值相同，读者会以为两种算法互证。
- 修复：标注"local_swap 在 88.7% 的格与 greedy 选择相同，仅作稳健性检查"。

**P2-5 报告聚合层未绑定快照**

- 证据：`src/causal_growth/evaluation/v3_d03_formal.py` 在 14:12 创建（窗口内），不在 `snapshot_binding.json` 的 83 件里；`report_meta.json` 只绑输入/输出表哈希，无聚合代码哈希；`created_at=2026-10-27T18:06:34`（运行结束后）。
- 影响：分片原始表是快照绑定的，报告表是事后代码生成的；本次用同一代码重建 7 张表逐字节一致，所以当前可复现，但"报告表由哪版代码生成"没有哈希证据。
- 修复：把 `v3_d03_formal.py` 与 `scripts/26_d03_formal_tables.py` 的 sha256 写进 `report_meta.json`，或把聚合层也纳入下一版快照。

**P2-6 快照 83 件里有 5 件不在 commit `130a309`**

- 证据：`check_git.py`：78 件与 commit 一致，5 件 `src/causal_growth.egg-info/*` 在 commit 中不存在。
- 影响：绑定证明"快照自洽"，不完全证明"快照等于某个 git 树"；egg-info 是生成物，风险低。
- 修复：快照排除 `*.egg-info` 与 `__pycache__`（实际快照有 123 个文件，含 40 个 pycache 未绑定），并在 binding 里写明排除规则。

**P2-7 §4 表省略了最接近的竞争策略 `incremental_profit_rank`**

- 证据：`docs/v3_phase_D03_formal.md:95-99` 只列 random/business/greedy/local_swap/predicted_profit/all_coupon；`policy_value.csv` 里 0.20 档 `incremental_profit_rank` 为 0.2711/0.2609/0.2040/0.1904/0.0685（CF/S/DR/T/constant），CF 与 business（0.2718）基本持平。
- 影响：按 AGENTS §12.5"报最差的、不是最有利的"，省略最接近的竞争策略会让 greedy 的相对优势显得更干净。
- 修复：把 `incremental_profit_rank` 与 `purchase_propensity_rank` 一并入表，哪怕只是脚注。

**P2-8 §8 的失效条件没有覆盖"同支出/每元价值"**

- 证据：`docs/v3_phase_D03_formal.md:181-189` 列了 L1/time_mode/预算/参考策略/单 test split/校准/冻结规则，没有"高预算符号依赖支出比"这一条。
- 影响：读者无法知道什么情况下 §5.2 的符号会翻转。
- 修复：加一条"若按实际支出或每元价值重算，0.80/1.00 档的符号可能改变；本表的预算是期望成本，不是硬支出上限"。

**P2-9 `run.log` 没有时间戳，4 小时 20 分的墙钟只能由文件 mtime 与 manifest 推断**

- 证据：`outputs/evidence/d03_formal/shard*_run.log` 每行只有 `elapsed`，无 `started_at/finished_at`；`:36` 的"12:54–17:14"依赖 manifest 与产物 mtime。
- 影响：不影响数字，但"运行时长/窗口"不可从日志独立核验。
- 修复：每行加 ISO 时间戳，或在 summary 里写 `started_at/finished_at`。

## 3. 被证实 / 被否定的报告陈述

### 被证实（逐项复算一致）

1. 200 rep × 5 模型完整；`per_rep` 1 000 行；`policy_grid` 72 000 行 = 200×5×9×8；无缺格/重复键。
2. 选模 105/71/12/7/5；每 rep 恰好 1 个 `chosen=True`；四分片计数相加一致。
3. §3 的均值偏差、SE、相对偏差中位数、最差绝对相对偏差、斜率中位数、Pearson 中位数、RMSE 中位数全部一致（表 A）。
4. §4 的 0.20 档策略值全部一致（含 all_coupon 0.2841、business 0.2718、CF greedy 0.2934）。
5. §5 的 40 个配对差、183/17、146/54、0/200 全部一致；配对键是 `(rep_id, model, per_user_budget_cny)`，符合 §12.6。
6. §7 的 `hat` 1.000 与 `by_true` 0.20 档 39.0/26.5/13.0/11.0/0 一致；`by_true` 与 `actual_spend ≤ budget` 一致率 100%。
7. §6 的 0.1143/0.1066/0.1047/0.1037/0.1317、share_optimal 0.212/0.192/0.125、选模后悔 −0.0114/−0.0162/−0.0193/−0.0205/−0.0188 与 SE 全部一致。
8. 证据：10 件哈希/行数、83/83 快照哈希、`combined_sha256`、`git_commit 130a309`、四分片 `formal_r/50/config_hash` 全部一致；合并表 1 000/72 000 无混表；7 张报告表可逐字节重建。
9. 真值隔离：`chosen` 在 `per_rep` 与 `policy_grid` 一致；快照 `v3_policy_grid.py:15-16` 明确"选人只用 τ̂/cost_hat/propensity/predicted_profit，评估只用 τ_true/cost_true"；`run_policy` 与 `_audit_truth_for_test` 的调用顺序与报告一致。
10. `docs/v3_phase_D03_formal.md:6`、`:186` 明确写"未证实、等待独立评审"，没有自称"通过"。

### 被否定或必须改写

1. `:38`、`:220`"运行期间未改 `src/`"——假（P0-1）。
2. `:24`"160/160 格"——是 20 rep 诊断口径；正式是 8 000/8 000 个 rep×格、40/40 个 model×budget 格（P1-3）。
3. `:14-16` 的"群体平均无偏"若被读成单 rep 无偏——不成立；单 rep 偏差 sd 0.062–0.066，是真值跨 rep sd 0.0246 的约 2.5 倍（P1-1）。
4. `:21-23`"选模后悔远小于事后最优"——数字对，但"远小于"的比较对象与 §6 的 0.1143 不是同一量，需要定义（P1-4）。
5. `:133-134`"dr/t 直到 0.80 才转正"——作为同预算的数值比较成立，但归因于"模型/定向"不成立；0.80 档 greedy 只花了 58%–65% 的预算（P1-2）。
6. `:14-16`"个体排序能力弱"——作为 Pearson 的描述成立；作为"策略不可用/可大幅改进"的证据不成立，且与 48.5%–53% 的选模命中率、+0.0216（183/200）的策略胜出并列时会产生矛盾读法（P1-6）。
7. `:101-102`"定向避开了负效应用户"——未被测量；all_coupon 在 0.20 档花了约 4.1 倍预算（P2-3）。
8. 快照 `v3_models.py:2167` 与诊断 `:111`"b<1 表示 τ̂ 被放大/离散度大于真值"——与本数据相反（P1-5）。
9. `:49-55`"选模高度不稳定"——频率事实成立，但漏了选择力：chosen 命中事后最优 48.5%–53%（随机 20%），"不稳定"不等于"选择无效"。

## 4. 未覆盖范围

- 只评 `L1_main`、`time_mode=static`；L0/L2/L3、非静态时间模式、其他 heterogeneity multiplier 未覆盖，结论不能外推到这些层。
- 只有 200 rep、每 rep 一个 test split；rep 间用户批不同，配对只在同一 rep 内成立，跨 rep 的总体推断未做。
- 未重跑正式 R，未重跑 DGP，未独立实现真值；真值口径依赖快照代码阅读与 `tau_true/cost_true` 列的定义。
- 未导出逐用户 τ_true（证据包只有 rep 级汇总与网格），因此无法计算 AUC/top-k uplift、分箱校准、逐用户噪声上限；"个体排序能力弱"只能作描述，不能定量归因。
- 未跑 pytest（本次不需要）；未复核 E/F 阶段对 D03 下游的消费；未评估 F02 等并行改动。
- 未核验每个分片进程的 `PYTHONPATH` 实际值（只能从 manifest 的 command template 与 summary/config_hash 推断）；`run.err` 只核到 `out/` 里的 0 字节，未在证据包内核。
- 未评估 SQL/loader 路径、内存/耗时、以及 72 000 行网格之外的其他策略族。

## 5. 评审留痕

复算命令（全部只读，工作目录为仓库根）：

```bash
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe C:/tmp/d03_review/check_evidence.py
./.venv/Scripts/python.exe C:/tmp/d03_review/check_git.py
./.venv/Scripts/python.exe C:/tmp/d03_review/check_grid_identities.py
./.venv/Scripts/python.exe C:/tmp/d03_review/check_calib.py
./.venv/Scripts/python.exe C:/tmp/d03_review/check_bias_decomp.py
./.venv/Scripts/python.exe C:/tmp/d03_review/check_merge.py
./.venv/Scripts/python.exe C:/tmp/d03_review/check_oracle.py
./.venv/Scripts/python.exe C:/tmp/d03_review/check_selection_power.py
git log --since="2026-10-27 12:54" --until="2026-10-27 17:14" --date=format:'%Y-%m-%d %H:%M' --pretty='%h %ad %s' --name-only
```

报告表重建用 `scripts/26_d03_formal_tables.py` 输出到 `C:\tmp\d03_review\regen\`，与 `outputs/tables/` 的 7 张表 `cmp` 全部相同；未写 `outputs/tables` 或 `out/`。

本次评审只新增本文件；未改源码、配置、数据、表格、TODO/GOAL；未 commit/push；未跑正式 R。`git status --short` 中除本文件外，另有 5 个本次评审之前就存在的未提交修改（`TODO.md`、`docs/v3_phase_D_pilot.md`、`docs/v3_phase_F02_validation.md`、`docs/v3_决策与反思日志.md`、`scripts/30_merge_f02_formal.py`）和既有的 `.workbuddy/` 未跟踪目录，均不是本评审产生的，也未触碰。
