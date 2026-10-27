# E01/E02 证据层独立复审（re-review）

> **合成数据 / 已知 DGP**｜scenario `L1_main`｜D03 正式 rep 0（n=200 000；test 60 000）
> 复审对象：`docs/v3_phase_E_evidence.md`（709 行，维护 2026-10-28 02:46，下称"正文"）、
> `docs/v3_phase_E_coverage.md`（维护 2026-10-27 19:50）、`docs/v3_phase_E_interface.md`（冻结版，维护 2026-10-26 13:20）、
> 证据包 `outputs/evidence/e_evidence_rep0_a/`（A/constant）与 `outputs/evidence/e_evidence_rep0_b/`（B/causal_forest）、
> 顶层 `outputs/evidence/coverage.json`。
> 原审：`docs/reviews/v3_phase_E_review.md`（2026-10-27 21:27，PASS WITH CONDITIONS，0 P0 / 6 P1 / 9 P2）。
> 复审时间：2026-10-28 05:15 – 05:40（北京时间）。
> 复审人：独立评审，未参与 E 的实现、运行与文档写作。
> 复审环境约束：F02 正式 200 rep 数据作业在跑（2 worker），**未跑 pytest、未跑任何重计算**（无模型拟合、无 MILP/DP 重解、无 n=200 000 生成）；全部复算为对已落盘聚合表与两份 60 000 行帧的只读 pandas/numpy 运算，单进程内存远低于 400 MB；未写任何哈希绑定路径（`src/**/v3*.py`、`sql/v3*.sql`、`configs/v3*.yaml`、`configs/v3/*.yaml`、`scripts/30_merge_f02_formal.py`、`out/scratch/f02_*.sh`）；本文件是唯一写入的仓库文件。
> 复算方式：Git Bash + `./.venv/Scripts/python.exe`，`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`，stdin heredoc 只读执行，未落任何临时脚本。

---

## §0 结论

**PASS WITH CONDITIONS（0 新 P0、3 新/残留 P1、约 10 项 P2）。**
数字层这次的复现率是 100%：本复审抽核的 60 余个头条数字（小池分离差值、分解学习误差两种口径、校准 13+8 个统计量、随机汇总 8 档、三口径 0.20 档 9 行与全档均值、规模表 MILP 状态/墙钟/NaN 契约/claim 计数、桶宽 5 档相对 gap 与分母、恒等式残差、帧退化事实、A/B 配对性、证据包双向 sha256、顶层登记 41 条）**全部与正文一致，无一失配**；5 份源码哈希与 7 份 YAML 哈希对 live 文件逐一 MATCH。原 6 项 P1 中 **4 项已修**（P1-1、P1-4、P1-5、P1-6），**2 项部分修**（P1-2、P1-3）。

不能给无条件 PASS 的原因是三处**非数值**缺陷，且都属于本项目已有明文红线：
① 正文 §6 开头（`docs/v3_phase_E_evidence.md:419-421`）仍写"两者的真值最优都来自 `truth_milp_cost_basis=truth_cost_floored_at_cost_floor_cny`"——这正是原审 §3.2 第 2 条**否定过**的句式（真值最优实际来自 `cent_exact_dp`，MILP 只是审计复核，见 `src/causal_growth/policy/v3_policy_evidence.py:851-870` 与同节 :449-451 的正确表述，正文自相矛盾），违反 AGENTS §12.4；
② 正文 §8.1（:561-562）"greedy_local_swap 在本表的 24 个格子上与 greedy 完全相同（A 与 B 都是）"对 B **为假**（B 真值 21/24 相同、预测成本 19/24 相同，差 3 格真值、5 格预测成本），与其给出的理由（"0.20 档的交换没有可改进移动"，只覆盖 3 格）也不匹配——这是与原审 P1-5 同类"一句话与落库表直接矛盾"；
③ A 证据包里的 `run_constant.log` 是**10-27 19:17–19:42 旧运行**的日志（内容含旧 small_pool 表写盘、总耗时 1217.4 s、8 产物），与同包 meta（created_at 2026-10-28T01:12:03）直接矛盾；B 证据包则**没有任何日志**。证据包的存在意义就是 §12.1"仅凭 evidence 可复算"，包内自带矛盾溯源使"§1.3 混合溯源已消除"的声明在证据包层面不成立。

**GOAL.md 建议：E01/E02 暂不转"通过"，维持"未证实"。** 剩余条件全部是文档/导出修复，**不需要重跑任何计算**：
1. 改正文 :419-421（真值最优来源改为"分币 DP：主口径 `cent_exact_dp(tau_true, cost_hat)`，raw `cost_true` 为敏感性；`truth_milp_*` 是审计复核"）；
2. 改正文 :561-562（A 24/24 相同；B 21/24 相同，列出 3 个差异格）；
3. 重新导出 A 的运行日志（源 `out/logs/e_r2_A_20261028_0112.log`）、补 B 的日志，刷新两级 coverage 记录，并给导出器加一条"日志时间戳必须落在 meta created_at/finished_at 区间内，否则报错"的检查（§12.7）；
4. 同步 `docs/v3_phase_E_coverage.md`（:79、:137、:141-142 仍描述 10-27 单家族旧运行为"the"结果，违反 §12.4，见 §5/§8）。

`cfg.hash(64)`（`e1aa4314…`）缺失**可接受、不阻断**：正文 :118-126 与 :667-668 已如实登记，该值可从已导出的 `outputs/evidence/d03_formal/shard0_summary.json` 交叉读到（本复审已核到原值），且 meta 里 7 份 YAML 的逐文件哈希（`protocol_source_hashes`）对 live 全部 MATCH，绑定实质等效；建议下次 E 运行时顺手补进 meta。
`status=evidence_not_formal_R` 是正确且应保留的：这是单 rep 证据，不是正式 R；正文头部与 §9.1 均未让读者误以为它是正式结果（唯一措疵：:6 "尚未独立评审"在原审已存在的情况下表述含混，建议改为"初审 PASS WITH CONDITIONS（10-27 21:27），本稿为重审对象"）。

---

## §1 逐条核对表（原 6 项 P1）

| 编号 | 原意见要求 | 作者声称的修复位置（文件:行） | 本复审实际核到的内容 | 判定 | 证据 |
|---|---|---|---|---|---|
| **P1-1** | 恒定 τ̂ 使五求解器互证退化；用非退化价值向量重跑 §3/§7；脚本入口对 `nunique(tau_hat)>1` 加断言；已知答案实例；短期不能重跑则删"互证"措辞 | 正文 :32-40（§0.1）、:227-240（§3.0）、:455-500（§7.2）；`src/causal_growth/policy/v3_policy_evidence.py:453-457` 守卫；`outputs/evidence/e_evidence_rep0_b/v3_phase_E_small_pool_cf.csv` | **B 上求解器真实分离**（对 `cent_exact_dp` 的预测目标差）：greedy 16/24 格不等（8 格为负，min **−0.310996** @(100,0.1)，max +0.003020）；local_swap 15/24 不等（min −0.305452，且 24/24 ≥ greedy，7 格严格改进，max +0.143282）；milp 14/24 不等（−0.066506 / **+0.080928**，24 行 status=optimal、16 行 may_claim、8 行 gap>1e-12 max 9.663e-04）；brute_force_float 5/8 不等（+0.000510）；lp_relaxation 24/24 非严格等（max +1.523250，3 格 −1.421e-14 噪声）。容差 1e-12/1e-9 下计数不变（3/8、8/24、9/24、10/24），与正文 §3.2 完全一致。守卫在 live 源码存在（对池内恒定 τ̂ 抛 ValueError）；A 的 meta `small_pools_used=null`、A 证据目录无小池表；旧表 `outputs/tables/v3_phase_E_small_pool.csv`（mtime 10-27 19:23）被正文三处标 `stale_pre_guard` 且明令"不得当作求解器一致性证据引用"，正文 §0.1 明确"那不是求解器一致性的胜利"。**残留**：已知答案构造实例（两价值档 / 1-for-2 交换）未进 E 产物，仍只有冻结单测反例 → 记 P2（§4 P2-N6） | **已修** | §2 复算 R1；`v3_phase_E_small_pool_cf.csv` 128 行 |
| **P1-2** | 真值 oracle 改为与策略同预算口径（cost_hat）；表加 `truth_oracle_cost_basis`；raw cost_true 只作敏感性另列；**正文把 `truth_milp_*` 明确为审计复核，不再说"真值最优使用该 MILP 解"** | 正文 :415-451（§6）、:74-77（§0.9）；`v3_policy_evidence.py:851-870`（cost_hat 基准 DP + 注释"MILP 只用于复核界与 gap"）；分解表新列 | **数值/代码层已修**：`truth_oracle_cost_basis='cost_hat_primary; raw_realized_cost_true_sensitivity'`；`true_value_truth_cost_hat_basis=1.01830`（A、B 全 8 档）；A 主口径学习误差 0.04 档 **0.98436** = 1.01830−0.03394、0.10 档 **0.99284** = 1.01830−0.02546，与原审补算期望值**逐位一致**；raw 口径 0.73162/0.88758 保留为敏感性；口径切换在 0.04 档 = +0.25274（相对 raw 口径 +34.5%，分母 raw 0.73162）、0.10 档 = +0.10526（+11.9%，分母 raw 0.88758），与原审数字一致；恒等式 `learning = truth − oracle_under_hat` 在两口径 32 行上最大残差 0（严格闭合），identity_residual 最大 A 3.469e-17 / B 8.327e-17 ✓。**文档层未修完**：:419-421 仍写"两者的真值最优都来自 `truth_milp_cost_basis=truth_cost_floored_at_cost_floor_cny`、status=optimal"——源码里真值最优来自 `cent_exact_dp`（raw 与 cost_hat 两个基准都是 DP），floored-cost MILP 只是复核；同节 :449-451 又正确写了"两个参照都是分币整数化 DP"，一句之内自相矛盾。这正是原审否定过的句式（原审 §3.2 第 2 条），修复要求"正文把 truth_milp_* 明确为审计复核"未落实 | **部分修** | §2 复算 R2；`v3_phase_E_decomposition{,_cf}.csv` 各 16 行 |
| **P1-3** | meta 写 git_commit/逐文件源码 sha/cfg_hash/protocol_source_hash/D03 快照哈希；帧/校准行/run.log/表 sha 导出到 `outputs/evidence/e_evidence_rep0*/` 并进 coverage.json；仅凭 evidence 可重建关键数字 | 正文 :96-127（§1.1）、:152-177（§1.3）、:665-683（§11）；`outputs/evidence/e_evidence_rep0_{a,b}/coverage.json`；顶层 `outputs/evidence/coverage.json` | **大部分已修**：两份 meta 均含 `git_commit=e0048100…`、5 份源码逐文件 sha256、`protocol_config_hash=30511a32…` + 7 份 YAML 逐文件 sha、`d03_snapshot_combined_sha256=be0d48f4…`、`frame_file_sha256` 与 `frame_dataframe_sha256` 分列（P2-4 同步修）；**12 项哈希对 live 文件全部 MATCH**（5 源码 + 7 YAML）。两证据包各 11 条记录，逐条 sha256+bytes 与磁盘一致，且双向无缺漏（磁盘 11 文件全登记、登记全在盘）；顶层 coverage 41 条 / total_bytes 15 858 444 / E 记录 22 条，全部 E 记录 sha 复算一致，3 条 registry_repairs（02:38/03:06/04:24）与正文 §11 相符。**仅凭 evidence 重建头条数字成立**（§2 R6 给出 6 例，含帧、校准逐用户行、小池、分解、随机汇总、三口径）。`cfg.hash(64)` 缺失已披露且可从 `d03_formal` 证据交叉读到原值 `e1aa4314b8d84b04…`（本复审核到）→ 可接受不阻断。**缺陷**：A 包内 `run_constant.log`（sha 6ac1ea95…，= live `out/e_evidence_formal/run.log`）内容是 **10-27 19:17:51–19:42:28 旧运行**（"8 个产物；总耗时 1217.4s"，含 19:23:38 写 stale `v3_phase_E_small_pool.csv`），与同包 meta `created_at=2026-10-28T01:12:03`/`finished_at=01:35:23` 矛盾；当前运行的真日志在 `out/logs/e_r2_A_20261028_0112.log`（首行 01:12:03，exit=0），未导出。B 包**无日志**（`out/e_evidence_formal_cf/run*.log` 不存在，B coverage 无 e_log 记录） | **部分修** | §2 复算 R3/R4/R5/R6 |
| **P1-4** | 校准个体指标按二值观测读；以常数/伯努利零模型为基准报 MAE/RMSE 相对改进、Brier；正文删"欠离散 1/7 / 排序接近 0"，保留均值校准结论 | 正文 :181-221（§2）；`v3_phase_E_calibration{,_cf}.json`（各 40 键）；`calibration_validation_treated_{constant,cf}.csv`（各 19 987 行，两份字节相同 sha 906a5f77… ✓） | **全部复现**（从逐用户 CSV 独立重算）：n=19 987、mean_pred 0.819480866、mean_obs 0.818532046、bias −0.000948820、相对 −0.115783%、总和比 0.998842169、MAE 1.486140082、RMSE 2.735292950、r 0.085254357、slope 0.616570211、intercept 0.313264555、sd_pred 0.379069477、sd_obs 2.741478028、观测取值 {0,10}；常数基准 MAE 2·10·p(1−p)=**1.503065**、RMSE 10·√(p(1−p))=**2.741409**（p=0.0818532）→ 模型相对改进 **1.126% / 0.223%**；cov=r·sd_p·sd_o=0.088597、signal_sd=√cov=**0.297653**、r 可达上限=signal_sd/sd_obs=**0.108574**、实测占上限 **78.52%**、pred_sd/signal_sd=**1.2735**（过离散，非"欠离散 1/7"）；Brier(10 元尺度) 0.074818 vs 空模型 0.075153（+0.446% 相对改进）。以上与原审推导逐项一致，且 JSON 已内置 `null_constant_mae_cny`/`brier_*`/`signal_sd_cny`/`pearson_share_of_calibrated_signal` 等键。**正文措辞已按要求改写**：:203-207 按二值观测解读、:213-215 明令"不得写成个体成本预测准确，也不得把 r=0.085 读成毫无排序能力"、:211-212 保留均值校准结论；"欠离散/接近 0"字样已不存在 | **已修** | §2 复算 R7 |
| **P1-5** | "1.00 档实际支出等于预算上限"改为"低于上限、不 binding"；§5 表加 `mean_actual_spend` 列 | 正文 :65-68（§0.7）、:374-383（§5 表）、:401-402 | 新表述："A 上 1.00 档确实选中全部 60 000 人，但实际支出是 **50 570 元**，低于 60 000 元预算上限，因此超支概率为 0"，并显式标注"（旧稿写'实际支出等于预算上限'，已更正：50 570 ≠ 60 000）"。§5 表含"平均实际支出（元）"整列（2 469.30 … 50 570.00，与 `random_summary` 逐值一致），并有 mean_predicted 49 190.15229782 ✓；"1.00 档贪心=随机=0.279134"保留为正确性检查且注明 B 不适用 ✓。全文 grep"等于预算上限"仅存在于两处"已更正"的引述里，无残留旧断言 | **已修** | §2 复算 R8 |
| **P1-6** | 至少对一个非 constant 模型重复同一 500 池/8 预算分解（2×8 表）；配对（同 rep/同池/同预算）；"学习误差主导"不得外推 | 正文 :9-27（家族定义）、:74-77（§0.9）、:415-451（§6 双家族 2×8 表）、:585-618（§9）；`v3_phase_E_decomposition_cf.csv` | **配对性成立**（本复审直接比帧）：A/B 同为 rep 0、60 000 个 `user_id` **同序全等**；除 `tau_hat` 外 8 列（is_new/cart_value/purchase_propensity/predicted_profit/cost_hat/tau_true/cost_true）**逐字节相等**；预算 8 档、pool（分解/桶宽 500、规模 1000/5000/60000）、种子数 200、`git_commit` 与 5 份 `source_sha256` 两家族逐值相同；两次运行单进程串行（01:12→01:35→02:04）。B 的 2×8 分解表已报（学习误差 0.63156–0.80158，求解误差 0.20 档 +0.02/−0.00036，负值有解释且恒等式闭合）。**外推已约束**：§0.9 只给两家族各自区间；§0.8 明写"两个方向都只对本 rep 的这条 τ̂ 成立"；§9.1-9.3 单 rep/B 非选模/A 是 constant 后果；失效条件明列"换价值向量需重跑"；meta 增 `frame_model_is_chosen_in_full_fit=false` 防误读。B 的 τ̂ 与 D03 正式 per_rep 表交叉一致（sd 0.7816467079081016、1.00 档真值 0.2791343333… 逐位同 `v3_phase_D03_formal_per_rep.csv` rep0/cf 行；chosen=constant 亦见 `shard0_summary.json:/reps_meta[0]`） | **已修** | §2 复算 R9；§3 |

**判定汇总：已修 4（P1-1、P1-4、P1-5、P1-6）；部分修 2（P1-2、P1-3）；未修 0；无法核 0。**

---

## §2 复算留痕

全部命令形如 `cd "C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目" && PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe - <<'PY' … PY`（只读；未写任何仓库文件）。以下按编号给出输入、关键输出。

**R1（P1-1，小池分离）** 输入 `outputs/evidence/e_evidence_rep0_b/v3_phase_E_small_pool_cf.csv`（128 行，键唯一）。以 `(pool_size, per_user_budget_cny)` 为格、`predicted_value_cny` 对 `cent_exact_dp` 求差：
```
brute_force_float: n=8  eq0=3 min=0            max=+0.000509654
greedy:            n=24 eq0=8 min=-0.310996    max=+0.00302034
greedy_local_swap: n=24 eq0=9 min=-0.305452    max=+0.00302034
lp_relaxation:     n=24 eq0=0 min=-1.42109e-14 max=+1.52325
milp:              n=24 eq0=10 min=-0.0665063  max=+0.0809283
greedy<0 的 8 格: (20,0.04) −0.101220 / (100,0.1) −0.310996 / (100,0.2) −0.053866 /
 (500,0.04) −0.094740 / (500,0.1) −0.012246 / (500,0.2) −0.204597 / (500,0.3) −0.212900 / (500,0.4) −0.000925
swap−greedy: 24/24 ≥ 0，严格改进 7 格，max +0.143282
milp: 24 optimal；may_claim_optimal=16；gap>1e-12 共 8 行，max 0.00096632；
 bound−incumbent min 0.0 / max 0.09660891 / 负 0 行 / 24 行有限
feasible_under_original_cost: True 103 / False 1 / NaN 24(全 LP)；
 唯一 False = cent_exact_dp @(100,0.2)，n_selected 27，predicted_cost 20.017834（超 0.0178，0.089%）
容差敏感性: eq@1e-12 与 eq@1e-9 下计数不变(3/8,8/24,9/24,10/24)；lp eq@1e-12=3
```
与正文 §0.1/§3.1/§3.2/§3.3 逐值一致。A 证据目录 `ls` 确认无小池表；A meta `small_pools_used=null`。

**R2（P1-2，分解）** 输入两包 `v3_phase_E_decomposition{,_cf}.csv`（各 16 行）。关键输出：
```
truth_oracle_cost_basis = 'cost_hat_primary; raw_realized_cost_true_sensitivity'（A、B 全行）
truth_milp_cost_basis = 'truth_cost_floored_at_cost_floor_cny'，status 全 optimal，gap 全 0，
 bound=incumbent ∈ {382.78, 456.52, 508.03, 509.15}
A greedy 学习误差(cost_hat 基准) 8 档: 0.98436 0.99284 0.91780 0.86774 0.73040 0.79188 0.58674 0.58674
A raw 口径:                          0.73162 0.88758 0.91780 0.86774 0.73040 0.79188 0.58674 0.58674
B greedy 学习误差(cost_hat 基准):     0.72032 0.78032 0.80158 0.79476 0.72198 0.63156 0.63156 0.63156
B raw 口径:                          0.46758 0.67506 0.80158 0.79476 0.72198 0.63156 0.63156 0.63156
true_value_truth_cost_hat_basis = 1.01830（A、B 全 8 档）；A oracle_under_hat: 0.04→0.03394, 0.10→0.02546
恒等式 learning == truth_hat − oracle_hat：32 行最大绝对差 0.0
identity_residual(_cost_hat_basis) 最大: A 3.469e-17 / B 8.327e-17
求解误差: A 仅 0.10 档 +0.02（两策略）；B 仅 0.20 档 greedy +0.02、swap −0.00036
```
**§12.5 口径**：复算值对正文 §6 表值的最大相对差 = **1.76e-16**（B 档；A 为 1.52e-16；**分母 = 正文表值**，即浮点精度内零差）。对原审期望值：0.04 档 1.01830−0.03394=0.98436、0.10 档 0.99284 **逐位复现**；口径切换差 +0.25274（34.5%，分母 raw 0.73162）/+0.10526（11.9%，分母 raw 0.88758），与原审一致。

**R3（P1-3，源码/配置绑定）** 对 meta `source_sha256`（5 文件）与 `protocol_source_hashes`（7 YAML）逐一对 live 文件重算 sha256：**12/12 MATCH**（`v3_models.py 7de5a364…`、`v3_policy.py ba058f9b…`、`v3_policy_grid.py 53205262…`、`v3_policy_evidence.py ca29cdbc…`、`24_e_evidence.py 6453db22…`；YAML 7 份全对）。A/B 两 meta 的该 12 项逐值相同 ✓（正文 §11 第 2 条成立）。

**R4（P1-3，证据包双向核验）** 两包 coverage.json 各 11 条：逐条重算 sha256+bytes 全对；盘上文件（除 coverage.json）与记录一一对应，无未登记文件；total_bytes A 6 974 049 / B 6 979 358 与记录求和一致。帧文件 sha：A `c8fd698e…` = meta `frame_file_sha256` ✓，B `81866efa…` ✓。校准逐用户文件两份字节相同（sha `906a5f77…`，608 786 B）✓（正文 :116、:220-221）。

**R5（P1-3，顶层登记）** `outputs/evidence/coverage.json`：**41 条记录、total_bytes 15 858 444**、E 类记录 **22 条**（e_frame/e_calibration_rows/e_small_pool/…/e_log 计数与两包一致；e_log 仅 1 条=A）；22 条 E 记录 sha256+bytes 全部复算一致；`registry_repairs` 3 条（2026-10-28 02:38 / 03:06 / 04:24）与正文 §11 相符。`cfg.hash(64)=e1aa4314b8d84b04a26150cb8ccea5a35dbe9b2d514fee724c56570d5b586d75` 在 `outputs/evidence/d03_formal/shard0_summary.json`（及 shard1-3、d03 coverage.json）中原值核到。

**R6（P1-3，仅凭 evidence 重建头条数字，6 例）**
1. §3.2 三个头条差值 −0.310996 / −0.305452 / +0.080928 ← `e_evidence_rep0_b/v3_phase_E_small_pool_cf.csv`（R1 命令）；
2. §6 A 主口径学习误差 0.98436/0.99284 ← `e_evidence_rep0_a/v3_phase_E_decomposition.csv`（R2 命令）；
3. §2 校准 13 数 + 78.52% + Brier ← `e_evidence_rep0_a/calibration_validation_treated_constant.csv`（R7 命令）；
4. §5 1.00 档 50 570/49 190.15/超支 0 ← `e_evidence_rep0_a/v3_phase_E_random_summary.csv`（R8 命令）；
5. §8.1 0.20 档 9 行 ← `e_evidence_rep0_{a,b}/v3_phase_E_conservative{,_cf}.csv`（R10 命令）；
6. τ̂ 退化/非退化事实（A nunique=1 sd 1.11e-16；B nunique=59 861 sd 0.781647；B τ̂≤0 共 27 188 人）← 两包 `frame_rep0_*.csv`（R9 命令）。
全部只用 `outputs/evidence/` 即可完成，未触碰 `out/`（日志核验除外，见 R11）与 `outputs/tables/`。

**R7（P1-4，校准）** 见 §1 表 P1-4 行的完整数字；命令为对 19 987 行逐用户 CSV 的 numpy 重算（均值/偏差/MAE/RMSE/Pearson/OLS/sd/常数基准/信号分解/Brier）。观测取值 `np.unique=[0,10]` 确认二值。与 JSON 40 键逐值对照一致（`pearson_share_of_calibrated_signal=0.7852198…`、`predicted_sd_over_signal_sd=1.2735287…`、`binary_p_hat=0.08185320…`）。

**R8（P1-5，随机汇总）** `v3_phase_E_random_summary.csv`（A 包）：1.00 行 budget 60 000 / mean_actual 50 570.00 / mean_predicted 49 190.15229782 / overrun_p 0.0；mean_se 全列 [0.000441, 0.000541, 0.000754, 0.000818, 0.000852, 0.000835, 0.000270, 0.0]；overrun_p 全列 [0.640, 0.730, 0.895, 0.955, 0.985, 1.000, 1.000, 0.000]；mean_actual 全列 [2469.30, 6143.10, 12335.40, 18547.75, 24692.75, 36989.30, 49341.15, 50570.00]；mean_true_value 全列与正文 §5 表逐值一致。**A、B 两份 random_summary 列集合相同且整表逐值相等**（`a.equals(b)=True`）——正文 §5"逐值相同"✓，但"（B 多一列 mean_value_per_actual_spend）"✗（见 §4 P2-N2）。

**R9（P1-6，配对）** 两帧各 60 000 行 9 列；`user_id` 同序全等、集合相等、唯一；`is_new/cart_value/purchase_propensity/predicted_profit/cost_hat/tau_true/cost_true` 七列 `np.array_equal` 全 True；A `tau_hat` nunique=1（sd0=1.1102e-16），B nunique=59 861（sd1=0.7816467079081016）、τ̂≤0 者 27 188 人；cost_hat>0、cost_true≥0、全数值列有限。两 meta budgets/pools/seed 数逐值相同（见 §1 P1-6 行）。

**R10（§7/§8 抽核）** 规模表（两包各 96 行）：
```
A: 1000 池 4 optimal+4 time_limit(claim 1, gap 0.001288–0.006488), 5000 池 8 optimal(claim 1),
   60000 池 1 optimal+7 tlni(claim 1)；tlni 墙钟 92.95–96.16 s；optimal@1.00: 60 000 人/49 190.15/0.221 s
B: 1000 池 8 optimal(claim 3), 5000 池 8 optimal(claim 3), 60000 同 A(claim 1)；
   tlni 墙钟 [61.82, 64.79, 229.33, 230.75, 230.83, 231.03, 232.34]；optimal@1.00: 32 812 人/27 643.89/0.216 s
may_claim 总数 A 3/96、B 7/96；"optimal 但 gap>1e-12" A、B 各 10 行
 （A gap 5.099e-05–1.000e-03；B 1.462e-05–8.440e-04，含 5000@0.30=1.4616e-05）
tlni 7 行 NaN 契约（含 relative_gap=NaN、bound 有限）A、B 均逐列核验通过
dual bound−incumbent: A min 0.0/max +2.915884e-01/0 负；B min 0.0/max +5.385563e-01/0 负
LP−incumbent: A min −7.003109e-11（1 行负）；B min −4.365575e-11（4 行负）
max|LP bound − dual bound|: A 5.171e-02 / B 2.795e-02
swap vs greedy（预测目标）: A 0/24 不同；B 11/24 不同，max 0.300311 @(1000,0.04)，swap 从不更差；n_selected 24/24 相同
greedy 账实超支(within_budget_by_true=False): A 21 行(每池 7/8)；B 13 行(1000:3, 5000:5, 60000:5)
MILP optimal 超支: A 13 行中 11（1000 池 4/4、5000 池 7/8）；B 17 行中 8（1000:3, 5000:5）
有限 incumbent 17 行中超支: A 14 / B 8
60000 池 greedy: A 0.04 档 6 907 人/预测 2 399.68/实际 4 020/真值 0.008649；
 B 0.04 档 3 562/2 399.99/3 050/0.094387（超 27.1%）；B 0.60+ 三档 32 812/27 643.89/27 820/0.435184
启发式墙钟: A greedy 0.0003–0.0453 s、swap ≤0.4831 s；B greedy 0.0002–0.0217 s、swap ≤0.4794 s
```
三口径表（各 72 行）：0.20 档 9 行与正文 §8.1 表逐值一致（A expected greedy 23 437/15 410/1.000/0.085638；B 14 763/12 870/1.000/0.290217；buffered A 27 692/18 610/0.116696、B 18 200/15 690/0.334226；worst A 1 200/930/0.003740、B 1 200/1 640/0.023890、random 1 200/1 011.50/0.005884；random 其余行 ✓）。全档均值：A expected 0.841875/0.841875/0.150683、buffered 0.723958/**0.875000**/0.168388、worst 0/0/0.010796；B 0.675208/0.675208/0.268731、0.557292/**0.708333**/0.286031、0/0/0.050801 —— 与 §8.2 表逐值一致。`value_basis=dgp_truth_tau`、`observed_value_status=deferred_to_F_ope` 72/72 行 ✓。**但 greedy vs local_swap：A 24/24 相同 ✓；B 仅 21/24 相同**（真值差 buffered@0.04 +0.000167、buffered@0.30 −0.000303、expected@0.40 +0.000111；predicted_cost_mean 差 5/24；actual_spend_mean 差 3/24，各 ±10 元）→ 正文 :561 为假（§4 P1-N1）。
桶宽表（各 48 行）：`relative_gap_to_exact` 两版本均有；A 相对 gap 均值/最大：0.01→0/0、0.05→0.2004%/0.8130%、0.10→0.2004%/0.8130%、0.50→8.2438%/30.6452%、1.00→9.1527%/14.2157%；B：0.1496%/0.6121%、0.0995%/0.4798%、0.2618%/1.5106%、1.3006%/6.3102%、3.4688%/12.9930%；每用户 gap 与丢弃数（A 0/2/5/72/124；B 4/4/2/25/90）与正文 §4 表逐值一致。分母（cent_exact_dp 目标）：A [18.2158, 36.1378, 59.9358, 79.6207, 97.8365, 127.2168, 146.9016, 146.9016]、B [52.0521, 102.7268, 161.9008, 197.5569, 216.6959, 218.9018, 218.9018, 218.9018] ✓。`gap_to_exact/gap_per_user ≡ 500` ✓；`relative_gap_to_exact ≡ gap_to_exact/精确目标` 逐行核到（allclose True）。bucket_dp 40 行 feasible 全 True（A、B）✓。B 负 gap 15 行 = {0.6,0.8,1.0}×5 宽度，每行 −0.00086486 元（相对 −3.9509e-06 = −0.000395%）✓。

**R11（证据包日志溯源）** `sha256sum out/e_evidence_formal/run.log outputs/evidence/e_evidence_rep0_a/run_constant.log` → 同为 `6ac1ea95…`；该文件内容为 `[E evidence 19:17:51] … 19:42:28 完成：8 个产物；总耗时 1217.4s`，含 `19:23:38 wrote outputs/tables/v3_phase_E_small_pool.csv (128 rows)`——即**旧运行**日志。当前 A 运行日志在 `out/logs/e_r2_A_20261028_0112.log`（首行 01:12:03，模型列表打印，末行 exit=0）；B 在 `out/logs/e_r2_B_20261028_0112.log`（01:35:26 起，exit=0）；`out/e_evidence_formal_cf/run*.log` 不存在。→ §4 P1-N2。

**R12（源码守卫与哨兵，只读）** `v3_policy_evidence.py:453-457`：`if np.unique(tau_hat).size <= 1 or float(np.std(tau_hat, ddof=1)) <= 0.0: raise ValueError("tau_hat 在池内恒定…")` ✓（P1-1 断言要求）。`tests/test_v3_policy.py:501`：`assert result.relative_gap == pytest.approx(1.0)` ✓（策略层哨兵保留，与正文 §7.3 陈述一致）。`v3_policy_evidence.py:851-870`：truth 两个基准均为 `cent_exact_dp`，MILP 注释"只用于复核界与 gap" ✓（支撑 P1-2 判定）。**未运行 pytest**（环境约束），仅静态读源码。

**未能复算的项（如实登记）**：① 正文 §1.2 关于 21:43/23:44 两次历史运行"7 张表逐格相同、仅 seconds 不同"的声明——旧备份在 `out/`（attic/旧目录），本复审未逐一打开比对（不在 evidence 包内，且属历史过程性声明）；② B 的 τ̂ 向量本身（causal_forest 预测值）未独立重拟合——重计算被禁止；只做了与 D03 正式 per_rep 表的交叉一致性核对（sd、1.00 档真值、chosen 记录，均逐位一致）；③ HiGHS 版本未在任何产物中记录，无法核。

---

## §3 A/B 两家族是否构成有效配对（问题 6）

**构成有效配对。** 依据（全部为本复审直接复算，见 R9/R3）：

1. **同 rep**：两 meta `source="d03:L1_main:n=200000:rep=0"`、`rep_id=0`；
2. **同用户**：60 000 个 `user_id` 同序全等、无重复；
3. **同数据**：除 `tau_hat` 外全部 8 列逐字节相等（含 `cost_hat`、`tau_true`、`cost_true`）——即两家族只差"价值向量"这一个因素，是干净的单因素对照；
4. **同预算/同池**：8 档预算、分解/桶宽 pool=500、规模 1000/5000/60 000、随机 200 种子，两 meta 逐值相同；
5. **同源码同配置**：`git_commit`、5 份 `source_sha256`、`protocol_config_hash`、7 份 YAML 哈希、`d03_snapshot_combined_sha256` 两家族逐值相同，且对 live 文件全部 MATCH；两次运行单进程串行（01:12→01:35、01:35→02:04），不违反 §11 只读纪律（运行在 D03 正式结束之后、F02 开始之前）；
6. **随机基线的一致性侧证**：A、B 的 random_summary 整表逐值相等（随机名单不依赖 τ̂），这既是配对正确性的检验，也被正文如实用作一致性检查。

**外推约束**：正文没有把"学习误差主导"写成模型无关的一般结论——§0.9 给两家族各自区间，§6 的"学习误差主导（0.59–0.99 元/人）"覆盖两条 τ̂ 的实测区间并紧跟"求解误差≈0 是 pool=500 的结果，不能外推到 60 000"的限定；§9.2/§9.3 明示 B 非选模结果（`frame_model_is_chosen_in_full_fit=false`，CF 在该 rep 选模打分 rank 5）、A 的退化是 constant 的后果；失效条件明列"换价值向量需重跑"。**未发现"从单模型子集写出一般结论"的 §12.6 模式**。需要提醒的一点：正文对 B 的定位措辞是准确的（敏感性对照，不是"CF 更好"的证据），评审通过时应保留这些限定语，不得在后续汇报中把 B 的数字单独抽出来当"causal_forest 的 E02 结论"。

一个**配对之外的口径提醒**（不影响配对有效性）：`v3_phase_E_interface.md` §4.1 的冻结验收式 `cent_exact_dp == milp`、`greedy ≤ local_swap ≤ exact ≤ lp` 在 B 上**按字面不成立**——MILP 在原始浮点成本上求解（14/24 格 ≠ 分币 DP，max +0.080928）、启发式在"整数化损失"格可高于 exact（+0.003020）、LP 有 3 格低 1.4e-14（浮点噪声）。正文 §0.2/§3.2/§3.4 已把机理讲清，但接口文档没有加"各求解器成本口径"的注记，文档集内部存在字面冲突（§4 P2-N4）。

---

## §4 新发现的问题

### P1（应在 E01/E02 转"通过"前修复；均不需要重跑计算）

**P1-N1 正文 §8.1 "swap 与 greedy 24 格完全相同（A 与 B 都是）"对 B 为假**
- 位置：`docs/v3_phase_E_evidence.md:561-562`。
- 事实（R10）：B 的 conservative 表上 greedy_local_swap 与 greedy 仅 **21/24** 格真值相同（差异格 buffered@0.04 +0.000167、buffered@0.30 −0.000303、expected@0.40 +0.000111 元/人），`predicted_cost_mean` 仅 **19/24** 相同，`actual_spend_mean` 3 格差 ±10 元；A 确为 24/24。句中给出的理由（"0.20 档的交换没有可改进移动"）只覆盖 3 个 0.20 格，与"24 个格子"的断言自不匹配。
- 影响：量级极小（≤3.03e-4 元/人），不改变 §8 任何结论方向；但这是与原审 P1-5 同类的"一句话与落库表直接矛盾"，且正文自己在 §7.2 已证明 B 的 swap 会动（11/24 格），§8.1 却写成完全不动——按原审同一标准必须改。
- 修复：改为"A 24/24 相同；B 21/24 相同（真值口径），差异集中在 buffered@0.04/0.30 与 expected@0.40，幅度 ≤0.00031 元/人"。

**P1-N2 A 证据包内日志为旧运行产物，B 证据包无日志（证据包内溯源自相矛盾）**
- 位置：`outputs/evidence/e_evidence_rep0_a/run_constant.log`（= `out/e_evidence_formal/run.log`，sha `6ac1ea95…`）；`e_evidence_rep0_a/coverage.json` e_log 记录；B 包无对应记录。
- 事实（R11）：该日志记录的是 **10-27 19:17:51–19:42:28** 的旧运行（含 19:23:38 写 stale 小池表、"8 个产物；总耗时 1217.4s"），而同包 meta 的 created_at/finished_at 是 **10-28 01:12:03/01:35:23**、timings 合计与产物集合都不同（A 本轮无小池表）。当前运行的真实日志在 `out/logs/e_r2_{A,B}_20261028_0112.log`（均 exit=0），未导出；B 包完全没有日志。
- 影响：证据包的宗旨是"离开 `out/` 可复算/可审计"（§12.1）；包内唯一的过程性文件却指向被 `stale_pre_guard` 否定的那次运行，审计者据此会得出"当前表由 19:17 运行产生"的错误溯源——这正是正文 §1.3 宣称"已消除"的混合溯源，在证据包层面复活。导出器对"日志时间戳 vs meta 运行区间"没有任何一致性检查，属 §12.7 所述"登记类代码遇到矛盾不响"的形态。
- 修复（廉价，无重跑）：把 `out/logs/e_r2_A_20261028_0112.log`、`e_r2_B_20261028_0112.log` 导出为两包的运行日志（替换/新增记录并刷新两级 coverage 的 sha/bytes），删除或明确改标旧 `run_constant.log` 为 `run_stale_1027.log`；给 `scripts/20_export_evidence.py`（或 E 的导出步骤）加断言：日志首末时间戳必须落在 meta `created_at`…`finished_at` 内，否则报错退出。

**P1-N3（= P1-2 残留）正文 §6 首段仍保留被否定的"真值最优来自 floored-cost MILP"句式**
- 位置：`docs/v3_phase_E_evidence.md:419-421`；对照源码 `v3_policy_evidence.py:851-870`（真值最优 = `cent_exact_dp`，raw 与 cost_hat 两基准；MILP 注释"只用于复核界与 gap"）与同节 :449-451 的正确表述。
- 影响：数值全部正确，但"真值最优的来源"这一 E02 核心口径在正文里仍有一句错述，且与两屏之内的另一句自相矛盾；原审 P1-2 的文档侧要求（"不再说真值最优使用该 MILP 解"）因此未闭环，也违反 §12.4"改完一处要全文 grep 旧值"。
- 修复：把 :419-421 改写为"两者的真值最优都来自分币 DP（主口径 `cent_exact_dp(tau_true, cost_hat)`，敏感性口径 `cent_exact_dp(tau_true, cost_true)`）；`truth_milp_*` 列是对 floored-cost 收紧问题的**审计复核**（16/16 行 status=optimal、gap=0），不是真值最优的来源"。

### P2

**P2-N1** 正文 :184"两者 40 个键里 39 个逐值相同，唯一不同的是 `calibration_rows_path`"——实测 **6 个键不同**（`frame_model`、`frame_model_is_chosen`、`frame_model_is_chosen_in_full_fit`、`tau_hat_nunique`、`tau_hat_sd_cny`、`calibration_rows_path`），相同的是 34 个；所有**统计量**键确实逐值相同，实质结论不受影响，但计数陈述为假。改为"39 个校准统计与口径键中 34 个逐值相同，另 5 个是家族溯源键（frame_model 等），唯一的路径差异是 calibration_rows_path"。

**P2-N2** 正文 :371"（B 多一列 `mean_value_per_actual_spend`）"——实测 A、B 的 random_summary **列集合相同且整表逐值相等**（A 重跑后同样新增了该列，正文 §1.3 自己也这么说）。删去括注即可。

**P2-N3（§12.4 扫旧）** `docs/v3_phase_E_coverage.md` 未随 A/B 重跑更新（维护时间仍为 10-27 19:50），至少 4 处描述旧单家族运行为"the"结果：
- :79 以 `v3_phase_E_small_pool.csv`（stale_pre_guard 表）作为 `small_exact.pool_sizes` 的 ✅ 证据——当前有效证据是 `_cf` 表；
- :137"E 证据链已用 D03 正式 rep 0 跑完（19:17:51–19:42:28，9 个产物齐）"——当前版本是 10-28 01:12/01:35 两家族、A 8 产物 + B 9 产物；
- :141"墙钟 86.8–103.7 s"——新 A 为 92.9–96.2 s、B 为 61.8–232.3 s；
- :141-142"唯一 optimal 是'全选'的 1.00 档"（B 的 1.00 档只选 32 812 人，非全选）与"`greedy_local_swap` 与贪心 24/24 格完全相同"（B 规模表 11/24 不同；B conservative 表 3/24 不同）。
这些正是任务书第 8 问要求抓的"仍以 constant 家族为唯一结果"的残留。coverage.md 属 E 文档集，转"通过"前应同步。

**P2-N4** `docs/v3_phase_E_interface.md:185-186` 的冻结验收式（`cent_exact_dp == milp`；`greedy ≤ local_swap ≤ exact ≤ lp`）未加成本口径注记，在 B 上按字面不成立（机理见 §3 末段与正文 §0.2/§3.2）。接口文档是"冻结版"，不必改验收值，但应加一行注记"MILP/启发式在原浮点成本上求解，等式仅在同一整数化问题内成立；跨口径差值见 E 正文 §3.2"，否则文档集内部字面冲突。

**P2-N5** `stale_pre_guard` 标记只存在于正文 prose：旧表 `outputs/tables/v3_phase_E_small_pool.csv` 本体无任何机器可读标记（文件名未改、无 sidecar、A 包 coverage.json 的 excluded 列表也没有它），而 coverage.md :79 还在引用它。防误引全靠读正文。建议：在 A 包 coverage.json 的 `excluded` 增加该文件条目（reason=stale_pre_guard），或将其移入 `out/attic/`。

**P2-N6** 原审 P1-1 修复建议中的"已知答案实例（两个价值档、必须 1-for-2 交换的构造）"未进入 E 产物；当前非退化证据完全依赖 CF τ̂ 的经验向量，硬构造仍只有单测 `test_frozen_counterexample_greedy_loses_a_third`。可留待 G 阶段，登记在此防止遗忘。

**P2-N7** 正文 :6"状态：证据已生成，尚未独立评审"——原审（10-27 21:27）已存在且本稿即为其整改后的重审对象，此句易误导时间线；建议改为"初审 PASS WITH CONDITIONS（2026-10-27 21:27）；本稿为重审对象（复审 2026-10-28）"。

---

## §5 P2 抽查结果（原 9 项）

| 原编号 | 要求 | 现状（本复审核实） | 判定 |
|---|---|---|---|
| P2-1 | 桶宽 gap 分母说明改正 + 加 `relative_gap_to_exact` | 两版本表均有该列；恒等式 `relative_gap=gap/精确目标`、`gap_per_user=gap/500` 逐行核到；正文 §4 明列 8 个分母（A 18.2158–146.9016、B 52.0521–218.9018）并要求"跨向量比相对 gap 先看分母" | **已修** |
| P2-2 | "3 策略均值"披露两条贪心相同 / 给 2 策略等权 | §8.1 有披露句但对 B 为假（P1-N1）；§8.2 均值仍是含重复行的 24 行均值，未给"A 按 2 条不同策略等权"的对照数（原审算过 0.8253125/0.147632） | **部分修** |
| P2-3 | mean_se 区间补 0.80/1.00 | §5 写法"0.000270–0.000852；1.00 档全员入选，sd 与 SE 都是 0"，与表列 [0.000441…0.000270, 0.0] 一致 | **已修** |
| P2-4 | frame_sha256 拆文件哈希/数据帧哈希 | 两 meta 均有 `frame_file_sha256` + `frame_dataframe_sha256`（+列清单）；A 文件哈希对盘上帧复算一致 | **已修** |
| P2-5 | 60 s 时限 vs 墙钟差异解释 + HiGHS 版本 | §7.1"时限只约束求解，建模与预处理不受控"+ 三次运行墙钟漂移实录；**HiGHS 版本仍未记录**（任何产物中均无） | **部分修** |
| P2-6 | "13 optimal 11 超支"补 4 个 time_limit incumbent（14/17） | 正文 §7.3 仍只报 optimal 口径（A 合计 11 行）；A 有限 incumbent 17 行中 14 行超支（本复审复算）未出现在正文；§3.4 提到"17 行 incumbent 有限"但只用于 bound 核验 | **未修**（现有陈述无误，但要求的分母仍缺） |
| P2-7 | 负真值行解释（tau_true 可为负） | A 规模表仍有 9 行负 `true_value_per_user`（1000@0.04 −0.02730、@0.20 −0.00693、@0.40 −0.03496，各 3 求解器；B 0 行）；正文 grep 无"tau_true 可为负/负真值"解释（"负"只出现在 gap/求解误差语境） | **未修** |
| P2-8 | 按实际支出归一的每元价值进 §5/§8 | 表列已加（random `mean_value_per_actual_spend`、conservative `true_value_per_actual_spend_mean`、scale `true_value_per_actual_spend`；本复审核到 conservative 的 per-spend 全档均值 A 0.321129/0.324529/0.335234、B 0.932587/0.883031/1.009173），但**正文 §5/§8 未引用任何每元数值**，"greedy vs random 每元"对照（原审 0.216 vs 0.336 等）仍缺 | **部分修** |
| P2-9 | "最差格 + 相对差 + 分母"汇总表 | 无汇总表；仅 §2（相对偏差分母）、§4（gap 分母）散点披露；正文 grep"最差"零命中 | **未修** |

小结：9 项 P2 中 3 已修、3 部分修、3 未修。P2 不阻断，但 P2-6/P2-7/P2-9 与本次新增的 P2-N3（coverage.md 扫旧）应合并进下一轮文档维护一次做完。

---

## §6 未覆盖范围

因 F02 正式 200 rep 作业占用机器（禁 pytest / 禁重计算），以下内容**未核**，判定时未计入正反任何一方：

1. **pytest 全量**：未运行。守卫（`ValueError`）、NaN 契约、`relative_gap=1.0` 哨兵、毒化测试（`test_*_does_not_read_truth`）只做了**源码静态阅读**（R12），未验证测试实际通过；正文 §7.3"测试补了断言"的说法未执行验证。
2. **B 的 τ̂ 向量独立重算**：causal_forest 在 rep 0 上的预测未重拟合（禁模型拟合）；只做了与 `outputs/tables/v3_phase_D03_formal_per_rep.csv` rep0/cf 行的统计量交叉核对（sd 0.7816467079081016、真值 0.2791343333… 逐位一致）与 `chosen=constant` 的 D03 记录核对。
3. **任何求解器重解**：MILP/DP/LP 均未重跑；"求解器输出正确"只能靠表内互证关系（bound≥incumbent、LP≥exact、swap≥greedy、brute force 参照）间接支持。60 000 池无精确参照，最优性缺口不可核（原审同）。
4. **历史运行一致性声明**：正文 §1.2 的 21:43/23:44 两次旧运行与当前"逐格相同（忽略 seconds）"的声明未从 `out/attic/` 备份逐一比对。
5. **D03→E 重建路径**：`--from-d03` 进程内重建未复跑；帧与 D03 正式网格的逐格交叉核对（原审做过 8 档 0.0 差）本轮未重复。
6. **F01/F02、D01**：不在本次范围。
7. **HiGHS 版本、机器负载对墙钟的影响**：无记录可核。

---

## §7 评审留痕

**读过的文件**（全部只读）：`AGENTS.md`（任务上下文）、`GOAL.md:7,23-24`、`docs/reviews/v3_phase_E_review.md`（338 行全文）、`docs/v3_phase_E_evidence.md`（709 行全文）、`docs/v3_phase_E_coverage.md`（154 行全文）、`docs/v3_phase_E_interface.md`（241 行全文）、`outputs/evidence/e_evidence_rep0_a/{meta_constant.json, coverage.json, run_constant.log}`、`outputs/evidence/e_evidence_rep0_b/{meta_cf.json, coverage.json}`、`outputs/evidence/coverage.json`、`outputs/evidence/d03_formal/shard0_summary.json`（程序化遍历）、`out/logs/e_r2_{A,B}_20261028_0112.log`、`out/e_evidence_formal/run.log`（哈希比对）、`src/causal_growth/policy/v3_policy_evidence.py:445-470, 838-935`（只读）、`tests/test_v3_policy.py`（grep relative_gap）、`outputs/tables/v3_phase_D03_formal_per_rep.csv`（grep rep0 行）、两包全部 CSV/JSON（程序化只读，含两份 60 000 行帧，逐次单表加载）。

**运行过的命令**（均在工作目录内，Git Bash）：`ls`/`grep`/`sed -n`/`sha256sum`/`tail`/`head`/`date`；11 段 `./.venv/Scripts/python.exe - <<'PY'` 只读复算脚本（内容即 §2 R1–R12：小池差值与容差计数、分解双口径与恒等式、校准 19 987 行全统计量、随机/规模/桶宽/三口径各表核对、帧配对比较、证据包与顶层 coverage 双向 sha 核验、live 源码/YAML 哈希比对、swap−greedy 排序、tlni 墙钟与 NaN 契约）。内存峰值远低于 400 MB（最大单表为 60 000×9 帧，约 6 MB）。

**写入**：仅本文件 `docs/reviews/v3_phase_E_rereview.md`。未写任何哈希绑定路径；未 commit/push；未跑 pytest；未跑正式 R；未动 `out/scratch/f02_*`。

**时间线（北京时间）**：2026-10-28 05:15 开始读文档；05:18–05:32 复算 R1–R12；05:35–05:40 撰写本报告。机器本地时间已核对（`date` = 2026-10-28 05:29 +0800；UTC 21:29）。

---

**复审结论复述**：数字层 100% 复现、真值隔离与 A/B 配对成立、P1-1/P1-4/P1-5/P1-6 已修、P1-2/P1-3 数值与代码已修但各余一处文档/导出缺陷，另有 §8.1 一句与落库表矛盾的新 P1。**PASS WITH CONDITIONS；E01/E02 暂维持"未证实"**；完成 §0 所列 4 项条件（均为文档/导出修复，无需重跑）并经一次快速核验后即可转"通过"。`cfg.hash(64)` 缺失按"已披露 + 可交叉读取"接受。
