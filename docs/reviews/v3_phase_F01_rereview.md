# F01（历史留出 OPE）独立复审报告

- 复审对象：`docs/v3_phase_F01_ope.md`（481 行）+ `outputs/evidence/f01_ope/` + `outputs/tables/v3_phase_F01_*.csv`
- 被复审的前次意见：`docs/reviews/v3_phase_F01_review.md`（2026-10-27 21:35，PASS WITH CONDITIONS，3 P0 + 8 P1 + 10 P2）
- 复审时间：2026-10-28 05:10 – 06:05（北京时间）
- 复审方式：只读 + 轻量 pandas/numpy 复算（未跑 pytest、未做任何模型拟合、未生成 n=200000 数据、单进程 RSS 远低于 300 MB）
- 复审人身份：独立子代理，非作者。按 AGENTS §7.4，作者与主负责的陈述一律视为草稿，逐条自行核。

---

## §0 结论

**判定：PASS WITH CONDITIONS（有条件通过）。**

11 条原意见中：**已修 6 条**（P0-2、P0-3、P1-2、P1-3、P1-5、P1-6）、**部分修 4 条**（P0-1、P1-1、P1-4、P1-7）、**未修 0 条**、**无法核 0 条**（条目级）；子项级有 **1 处【无法核】**——DR 主估计量的全部数值。

之所以不是 PASS：修复的**工程与证据层几乎全部到位且可复算**（32/32 名单哈希、256/256 审计格、160/160 targeting 格、64/64 IPW+SNIPS 行、32/32 配对 SE、1600 行随机分布的全部 16×13 个汇总量、48/48 源码哈希、4 个 gzip 帧的 `dataframe_sha256`，全部仅凭证据包重建，最大绝对差 0.0），但**结论层出现了三处新的口径问题**：

1. **N-1（P1）**：为替换 P0-1 而新写的机制解释——"贪心把大量**预测成本为 0** 的人当免费"（line 27、line 361-362）——**与数据直接矛盾**。逐用户复算：`cost_hat` 最小值 = 0.0484，`cost_hat ≤ 0` 的人数 = **0**，`< 0.01` = **0**，`< 0.1` = **15**；且 `v3_f01.py:193-194` 与 `v3_policy_grid.py:70-71` 两处硬性 `raise` 禁止 `cost_hat ≤ 0`。真实机制是 `cost_hat` 的**水平标定偏差**（入选者 `cost_hat` 均值 0.512 vs 全体 0.820，但真值支出反而高 28.42%；`corr(cost_hat, cost_true)` 只有 0.0815）。P0-1 要求的是"改正措辞"，结果改出来的新措辞是错的。
2. **N-2（P1）**：line 10 "每个数字都可由 `outputs/tables/` 与 `outputs/evidence/f01_ope/` 复算"对 **DR 不成立**。证据包的 `observed.csv.gz` 只有 6 列（`user_id,treatment,net_profit,coupon_cost,any_refund_30d,design_probability`），**没有 mu1/mu0/影响函数**；DR 是交叉拟合产物，只能重跑 `fit_ope_nuisances`（`meta.stage_seconds.ope = 10.53 s`，属模型拟合）。DR 是本文的**主口径**（`family.csv` 两行、`contrast.csv` 0.2 档、line 17/412 的全部结论都建立在 DR 上），而主口径恰好是唯一不能从证据包重建的一族。这正好撞在 AGENTS §12.1 的硬门禁上。
3. **N-3（P1）**：P1-7 只按"同预测预算规则"补了档内回归（7 档 `within_range` 全为 0），但**没有做跨档合并的"等实际支出"插值**，于是 line 336 "等支出比较做不了"过强。我用证据包自己的 1400 行（7 个非退化档 × 200 种子）做跨档合并 OLS：`r² = 0.987140`，定向臂真实支出 15 410 元对应 `x = 0.256833`，**落在 x 范围 [0.035333, 0.827000] 之内**（是插值，不是外推），预测"等实际支出的随机名单"= **0.084547**，vs 定向 0.085638 ⇒ 优势只剩 **+0.001091**。三种口径（合并 OLS / 档均值拟合 / 相邻档插值）一致落在 0.0841–0.0845，独立复现了原评审的 ≈0.0851。也就是说 §4.2 的 +0.031873 里约 **96% 来自"多花 30.9% 的钱"**，而这一点本文没有量化。

这三条都**不需要重跑**：N-1 与 N-3 是改文字 + 补一个已有数据的派生数字，N-2 要么补落盘 nuance（约 1 MB gz）要么改 line 10 的措辞。

**对 GOAL.md 的建议：F01 保持"未证实"，本轮不要改成"通过"。** 理由：(a) 三条 P1 都在结论层，未修完就改状态等于让一条错误机制解释（N-1）和一条过强断言（N-3）进入验收记录；(b) 主口径不可复算（N-2）是 §12.1 的硬缺口，按该条最低也是 P1；(c) 即便这三条修完，"通过"也只能表示"**记录准确、断言范围正确**"，即严格限定在 **单 rep / R=0 / D03 选中 `constant` 模型 / 主预算 0.2 档**，绝不表示"定向有效"——本文 §0.6/§0.8/§0.12/§6.6 自己已经写清了这一点，改状态时不能把它丢掉。

---

## §1 逐条核对表

| 编号 | 原意见要求 | 作者声称的修复位置（文件:行） | 我实际核到的内容 | 判定 | 证据 |
|---|---|---|---|---|---|
| **P0-1** | "定向优于随机"的机制被误述（τ̂ 为常数，优势 100% 来自"覆盖更多人"）；要求改正措辞，并把 `chosen=constant ⇒ 无 CATE 异质性 ⇒ 本阶段不能检验定向` 列为局限 | `docs/v3_phase_F01_ope.md` §0.6/§0.8/§0.12、§4.8、§6.6；新增 `v3_phase_F01_targeting.csv`；机制解释写在 line 27 与 line 361-362 | **分解表本身完全正确**：我从证据包逐用户重建 `targeting.csv` 全 16 行，160/160 格匹配，恒等式残差 1.73e-17、share 之和残差 1.78e-15。0.2 档 vs random：diff +0.031873 = 覆盖效应 +0.032608（share 1.023046）+ 单位效应 −0.000735（share −0.023046），入选者真值 τ̄ 0.219238 反而**低于**随机臂 0.221118，n 23 437 vs 14 589。**"不能检验定向"的局限也确实写进了 §0.12/§4.8/§6.6**。**但替换用的机制句是错的**（见 §3 N-1）：line 27/361-362 称贪心"把大量预测成本为 0 的人当免费"，实测 `cost_hat ≤ 0` 人数 = 0 | **部分修** | `c_out.txt` C4/C5 段；`d_out.txt` D4 段 |
| **P0-2** | 单条随机抽样落在第 10 百分位、OPE 0.085714 约为真值期望差的 4.5–4.8 倍；要求补做"随机策略分布"（复用 E 的 200 seed 机制）**或**明确"仅针对本次抽到的这一条随机策略，不外推" | `v3_phase_F01_random_seeds.csv`（新增）、`v3_phase_F01_random_summary.csv`（新增）、`v3_f01.py:1124 random_policy_masks` / `:1157 random_policy_distribution`；正文 §4.6/§4.7、§8 | **两个补救都做了**。`random_seeds.csv` = 1600 行（8 档 × 200 种子，seed 0–199）。`random_summary.csv` 16 行 × 13 个汇总量我全部独立复算，**最大绝对差 = 0.0**（mean/sd/q10/q50/q90/frozen/rank_low/targeted/diff/mc_se/z/p/n_at_least）。0.2/audit：mean 0.067280、sd 0.011802、q10 0.053296、q50 0.066650、q90 0.082572、冻结种子 0.053765、rank_low 0.1100、targeted 0.085638、diff +0.018358、mc_se 0.000835、z 21.997、p 0.000e+00、**n_at_least = 15**。0.2/DR：mean 0.053702、sd 0.035933、frozen −0.020251、rank_low **0.015**、diff +0.011761、z 4.629、p 1.838e-06、**n_at_least = 68**。§8 声称的 audit 档级 n_at_least 165/77/15/0/0/1/0/200 逐档相符。`seed=0` 的 mask 与冻结随机名单逐位相同 | **已修** | `b_out.txt` §8 段；`c_out.txt` C6 段 |
| **P0-3** | 证据包只有 freeze.json+meta.json，7 张表未登记；重建需要仓库外的 `out/e_evidence_formal/frame_rep0.csv`；属 §12.1 硬性缺口 | `outputs/evidence/f01_ope/`（4 个 gzip 帧 + 11 张表副本 + freeze/meta + coverage.json）；正文 §3、§7、line 428-429 | **包结构到位**：18/18 条目录级记录的 sha256+bytes 全部匹配，`sum(bytes)=9 490 785` = 声明值，`in_repository_bytes=4 185 712` = 声明值，磁盘上唯一未登记的文件是 `coverage.json` 自身；`meta.artifacts` 11/11 行+sha 匹配；11 张证据副本与 `outputs/tables/` 正本**逐字节相同**（0 张不同）。4 个帧的 `dataframe_sha256` 全部 MATCH（selection `3ef75e0f…`、observed `54aef882…`、truth `da000c1f…`、features 去 `user_id` 后 `d15cf24d…`）。`freeze.json` 文件 sha `9973376b…` = `meta.freeze.file_sha256`，`freeze_id` 从 payload 复算 = `b8402f30d82c96af…`。**仅凭该包我重建了**：32/32 mask（sha256 对上 `freeze.budgets[*].policy_sha256`）、32/32 n_selected、32/32 predicted_value、32/32 predicted_cost、256/256 审计格、160/160 targeting 格、64/64 IPW+SNIPS 值行（value/SE/ESS/ess_fraction）、32/32 IPW+SNIPS 配对对比行、30/30 随机种子审计格。**参考帧已入库**：`outputs/evidence/e_evidence_rep0_a/frame_rep0_constant.csv` 与 `out/e_evidence_formal/frame_rep0.csv` 逐字节相同（都是 sha256 `c8fd698ed05b47a6…`、6 093 781 B），§7 的命令指向的是入库副本。**残留**：DR 不能从该包重建（见 N-2） | **已修**（但派生新 P1 N-2） | `a_out.txt` 全篇；`c_out.txt` C2–C7；`d_out.txt` D3 |
| **P1-1** | `configs/v3/evaluation.yaml` 无 `primary_estimator` 键，DR 是硬编码，"预声明"三字不成立；要求加 YAML 键**或**改措辞为"本阶段以 DR 为主口径（理由：…），IPW/SNIPS 为敏感性分析" | `v3_f01.py:92 PRIMARY_ESTIMATOR`、模块 docstring :25；正文 line 56-57；`meta.primary_estimator_frozen_by`；`tests/test_v3_f01.py::test_primary_estimator_is_registered_and_drives_family_table`；`scripts/31_f01_ope.py:645` | 走的是"披露而非加键"这条路，且**披露是充分的**：`grep -rn "primary_estimator" configs/` 为空（确认无 YAML 键）；`v3_f01.py` docstring line 25 明写"**'主估计量 = DR' 没有对应的 YAML 字段**"；正文 line 56-57 明写"由源码哈希冻结，无 YAML 字段"；`meta.primary_estimator_frozen_by = "source_hashes（源码哈希；该估计量无 YAML 字段）"`；有专门测试把它钉住。**残留**：line 17 与 line 412 仍然写"**按预声明口径**"/"**按预声明 DR 口径**"——正是原评审判为不成立的那个措辞，没有被换掉 | **部分修** | `e_out.txt` E5；正文 line 17/56-57/412 |
| **P1-2** | "1.28 SE" 用的是水平 SE 0.057925 而不是配对增量 SE；要求 `ope_vs_audit.csv` 带 `paired_se`/`z` | 新增 `v3_phase_F01_increment.csv`（96 行）；`ope_vs_audit.csv` 的 `ope_se_cny_per_user`/`ope_z` 改为配对 SE；正文 §4.5 | **完全到位**。`increment.csv` 96 行（8 档 × 4 策略 × 3 估计量，列 `increment_cny_per_user, se_increment, z, one_sided_p_value, n`）代数一致性 0 处不符；0.2 档 DR：no_coupon se=0.000000、random se=**0.039872688**、greedy/local_swap se=**0.030779164**。`ope_vs_audit.csv` 0.2 档 `random−no_coupon` 的 `ope_se = 0.039873`（= `increment.se_increment`，不是旧稿的 0.057925），`|−0.074016|/0.039873 = **1.856**`；对比行带 0.030779 / 0.045895 = `contrast.se_diff`。48 行 `ope_z == ope_value/ope_se`、`p == 1−Φ(z)` 全部成立（0 处失败）。SE 三元组 (0.030779, 0.045895, 0.039873) 反推 ρ≈0.518，落在原评审给的容许区间 [0.0151, 0.0767] 内 | **已修** | `b_out.txt` §2/§6 段 |
| **P1-3** | ESS 权重缺 `T/(1−T)`（`v3_ope.py:358-359`），导致 `ess_fraction > 1`；正确值约 709(0.0236)/212(0.0071) | `v3_ope.py:355-368` | **完全到位**。源码现为 `w1 = pi*t/e`、`w0 = (1-pi)*(1-t)/(1-e)`、`ess_t_frac = ess_t/n_treated`、`ess_c_frac = ess_c/n_control`。`value.csv` 96 行中 `ess_fraction > 1` 的行数 = **0**，两列最大值都是 1.0。64 行 IPW/SNIPS 的 ESS 我用重建 mask + `observed.csv.gz` 逐行复算，**全对**。§0.11/§6.8 引用的数字逐一核到：0.04 random ess_t 1445(0.048199)、0.8 random ess_c 708(0.023584)、0.8 greedy 与 local_swap ess_c **215**(0.007162)（原评审写的 212 是估计值，215 是实测值，文档用的 215 正确）。0.2 档 greedy 11 791(0.393296)/18 374(0.612059)、random 7 305(0.243662)。4 个失败门禁格 → 12 行 value → 7 行 `ope_vs_audit`（0.04: 2，0.8: 5），与正文 line 275 一致；`support_violation_fraction` 全 0；32 行 DR 的 ESS/passed 与 `meta.gates` 不一致数 = 0 | **已修** | `b_out.txt` §1；`e_out.txt` E2 |
| **P1-4** | 真值在冻结之前就已物化，§3.4 措辞过强；要求审计表带 `truth_sha256`，并把措辞改为"真值列在 D03 产物中已存在，但 F01 的接口层拒绝真值列、且冻结清单不含真值" | `v3_f01.py:534 truth_audit_table`（发 `audit_truth_sha256`）、`:496-507 require_truth_frame`；`scripts/31_f01_ope.py:574`；正文 line 61、line 234 | **接口层与绑定层到位**：`audit.csv` 32 行 `audit_truth_sha256` 唯一值 = `da000c1f481ea7a7…` = `meta.truth_sha256` = 我从 `truth_audit_only.csv.gz` 复算的 `dataframe_sha256`，三者全等；`tests/test_v3_f01.py:215` 钉住该等式，`:201-202` 钉住"第 4 列起全部以 `audit_` 开头"；`require_truth_frame:506-507` 现在会比较 `manifest.get("freeze_id") != freeze_id`（同时修掉原 P2-10）；脚本里真值读取（`:574`）已移到 verify（`:525`）之后。**残留（实质未变）**：`v3_models.py:2067` 在 `_d03_rep_artifacts`（`:1990`）内部调用 `_audit_truth_for_test`（`:1932`），即 `tau_true`/`cost_true` **在冻结写盘之前就已物化**；而正文 line 61 仍写"真值只在冻结落盘并复算通过后**才解封**"、line 234 仍写"且在冻结复算通过之后**才生成**"——原评审要求改的那句话，一个字没改 | **部分修** | `b_out.txt` §5；`v3_models.py:1932/1990/2067` |
| **P1-5** | `verify_freeze_manifest` 在活体工作树上失败（活体合并哈希 a8453cdc… vs 记录 7012a17b…） | `freeze.json.source_hashes`（48 份）；`meta.source_hash_combined`；正文 line 93-98 | **完全到位**。48/48 条记录哈希与活体工作树匹配，**缺失 0、不符 0**；按同一组 glob 活体重新枚举得到的仍是**同样 48 个文件**（新增 0、消失 0）；活体合并哈希 = 由记录字典重算的合并哈希 = `meta.source_hash_combined` = `d3e169f1bd3d782226d2216faa63d3a8ef69d39a8d47e270814aab79eb037bc9`。目录分布 `src 37 / configs/v3 7 / configs 2 / sql 2`，`scripts/` 正确地未被绑定。`meta.git_commit = e0048100…` vs 活体 HEAD `0765a0a6…` 不同属**设计使然**（绑定的是内容哈希不是提交号），正文 line 93-98 把这点解释对了 | **已修** | `d_out.txt` D1/D2 |
| **P1-6** | 两个不一致的 E 随机均值（0.067745 vs 0.066756）被混在一处引用；要求统一为同一张表并注明抽样口径 | 正文 §5（line 375-382） | **完全到位**。我逐个数字定位到第一手来源：0.06675596 / 14640.79 / 12339.35 → `v3_phase_E_conservative.csv` 第 18 行（`mode=expected`、`policy=random_same_budget`、预算 0.2、seeds 200、`evidence_basis=random_sweep`）的 `true_value_per_user_mean` / `selected_count_mean` / `actual_spend_mean`；0.06774463 / 14638.56 / 12335.40 → `v3_phase_E_random_summary.csv` 第 2 行（预算 0.2、seeds 200）的 `mean_true_value_per_user` / `mean_n_selected` / `mean_actual_spend_cny`。两套值在 `e_evidence_rep0_a`（constant）与 `e_evidence_rep0_b`（cf）中完全一致。正文 §5 现在把每个数各归各表、并说明是三条不同的随机流；F01 自己的 0.067280 在 §0.5/§4.6/§4.7 中一致使用，**混引已消除**。（小瑕疵：把三条流区分开的"口径"没有任何 E 表的列来绑定，见 N-13/P2） | **已修** | `d_out.txt` D6 |
| **P1-7** | 缺"等**实际**支出"对照（贪心 15 410 vs 随机 11 770，+30.9%）；原评审自己用 `v3_phase_E_random_long.csv` 跨档回归预测随机在 15 410 处 ≈0.0851（档均值插值 ≈0.0849），优势会消失 | `random_summary.csv` 的 10 个 `equal_spend_*` 列；正文 §4.6、line 336 | **档内那一半到位、跨档那一半没做**。10 个 `equal_spend_*` 列在 7 个可定义档上逐位复现（0.2 档：slope −7.170236642e-06、se 2.783669070e-06、t −2.5758、intercept 0.155870691、r² 0.032422922、pred 0.045377、diff +0.040260）；`slope_t == slope/slope_se` 最大偏差 0.0；`within_range` 在 0.04–0.80 全为 0、在 1.00 档为 NaN（支出 sd=0，退化）；DR 行 `equal_spend_*` 全 NaN。**但**：档内回归的 x 只是同档 200 个种子的支出（0.2 档范围 [11 570, 13 050]，sd 仅 296.4 元），根本覆盖不到 15 410，所以 `within_range=0` 是必然的、不构成"等支出比较做不了"的证据。我用**同一个证据包**的 1400 行（7 个非退化档 × 200 种子，x=`audit_actual_spend`/60000，y=`audit_increment`）做跨档合并 OLS：slope 0.332073451、se 0.001013720、t 327.579、intercept −0.000740668、**r² 0.987140**、x 范围 [0.035333, 0.827000]；定向臂 x = 0.256833 **在范围内 ⇒ 插值**，预测 = **0.084547**，vs 定向 0.085638 ⇒ 优势 **+0.001091**。档均值拟合（7 点）给 0.084528（+0.001110），相邻档线性插值（0.2 档 12 355/0.067280 → 0.3 档 18 551/0.101500，w=0.493063）给 0.084153（+0.001485）。原评审的 ≈0.0851/≈0.0849 被独立复现 | **部分修**（派生新 P1 N-3） | `b_out.txt` §9/§10；`d_out.txt` D5 |
| **P2 组（10 条，抽核 4 条与结论相关者）** | P2-5 pytest 日志缺 "1248 passed" 汇总行与命令行；P2-8 `policy_meta.predicted_value ≡ 0.293803×n_selected` 应注明"本阶段预测价值不含异质性"；P2-9 `372a1bcc` 是 9 列帧哈希不是 7 列选人哈希；P2-10 `require_truth_frame` 未比对 manifest 的 `freeze_id` | 正文 line 37/39/443-444；`v3_f01.py:506-507` | **P2-10 已修**：`require_truth_frame:506-507` 现在 `raise "审计 freeze_id 与 manifest 不一致"`，并有 `test_require_truth_frame_rejects_mismatch_and_missing_freeze_id` 覆盖。**P2-5 部分修**：`outputs/runs/f01_tests/full_suite.log`（2 066 B）时间戳是 2026-10-27 20:20:35–20:28:04、1248 个进度点、`[run] exit=0`，**仍无 pytest 汇总行、仍无命令行**，且它**早于** ESS 修复与新表落盘（过期）；修复后的日志 `out/logs/pytest_full_20261028_0321.log`（1 527 B，03:21:18–03:27:42，1264 点，`EXIT=0`）**同样没有汇总行**，而且它在 `out/` 里、不入库。**P2-9 未修**：line 78 与 line 450 仍把 `372a1bcc…` 称作"7 列选人哈希"，实测它是**全 9 列帧**的哈希，7 列投影是 `3ef75e0f…`（line 89 写对了，自相矛盾）。**P2-8 未修**：`policy_meta.predicted_value / n_selected = 0.29380318` 对所有 32 行成立，正文始终未注明"本阶段预测价值不含异质性" | **P2-10 已修 / P2-5 部分修 / P2-9 未修 / P2-8 未修** | `e_out.txt` E1/E5；正文 line 37/78/89/443-450 |

### §1 附：额外自行核到、原意见未列但影响可信度的项

- **§3.1 第二次 freeze_id 变更（line 39、line 133-134）**：把 `out/f01_ope_formal_20261028_0043/freeze.json`（`bfb26807b9972685…`，created 00:47:52）与当前 `outputs/evidence/f01_ope/freeze.json`（`b8402f30d82c96af…`，created 02:57:03）逐字段对比：48 → 48 条哈希，**恰好 1 个文件变了**（`src/causal_growth/policy/v3_policy_evidence.py`：`18ac6f40014af47a` → `ca29cdbcc57728e1`），其余 12 个关键字段（`selection_sha256`/`user_id_sha256`/`design_probability_sha256`/`config_hash`/`budgets`/`family_contrasts`/`scenario`/`n_dgp`/`n_users`/`rep_id`/`chosen_model`/`selection_columns`）**全部逐字节相同，差异字段 0 个**。11 张当前表与 `out/scratch/f01_tables_backup_0049` 逐字节比对：**10 张 IDENT、只有 `v3_phase_F01_audit.csv` DIFFER**。正文 line 39/133-134 的陈述准确。
- **§12.6 同源配对**：`v3_policy_evidence` 在 `v3_f01.py`、`scripts/31_f01_ope.py`、`v3_ope.py` 中出现 **0 次**（F01 链路不 import 它）；`freeze.source_hashes` 里它是 `ca29cdbcc57728e1…`，与 `e_evidence_rep0_a/meta_constant.json` 和 `e_evidence_rep0_b/meta_cf.json` 的 `source_sha256` **完全相同** ⇒ 跨源码版本配对问题确实消除。
- **Holm 家族（`family.csv` 2 行）**：表内 `holm_adjusted_p` 两行都是 0.033430639074922386，我独立复算 Holm step-down 得 0.033430639075，**最大绝对差 0.0**。同族单侧下界用 `z = NormalDist().inv_cdf(conf)` 反演：`selected_targeted_minus_no_coupon` conf 0.975 / adj_alpha 0.025 / z 1.959964 → lb 表内 0.005137319 = 复算 0.005137319（diff 0.00e+00）；`selected_targeted_minus_same_budget_random` conf 0.95 / adj_alpha 0.05 / z 1.644854 → lb 0.010224658 = 0.010224658（diff 0.00e+00）。`conf == 1 − adj_alpha` 两行都成立 ⇒ **没有用未校正 CI 顶替**，符合 `evaluation.yaml:47` 的 `confidence_limits` 预声明。
- **超预算事实**：审计贪心 **7/8 档超预算**、最大 ratio **1.675**（0.04 档：4 020/2 400）；随机 4/8 超、最大 ratio 1.0275；24 个非 `no_coupon` 行里 18 行超预算。贪心与 local_swap 在 8 档所有数值列**全等**（因 τ̂ 恒定、`local_swap` 只在严格更大时才接受 ⇒ 必然退化）。0.2 档贪心 n=23 437、inc 0.085637833、真实支出 15 410、预算 12 000、ratio 1.2842。
- **`sign_agrees=False` 恰好 5 行**（0.04 random、0.04 contrast、0.10 random、0.20 random、0.60 contrast），与正文一致。
- **对比行 |误差|/SE 最大值 2.079634**，出现在 0.04 档 `selected_targeted_minus_same_budget_random`，与正文 line 275 的"最大 2.080"一致。
- **τ̂ 退化程度**：`tau_hat` 唯一值个数 = **1**，值 = 0.29380318488356094；`policy_meta.predicted_value / n_selected` 对全部行 = 0.29380318。`tau_true` 均值 0.27913433333333332（即 τ̂ 与真值均值差 +5.25%）；`cost_true ∈ {0.0, 10.0}`，均值 0.84283333（核销率 8.43%）；`design_probability` 唯一值 = [0.5]（与"e ≡ 0.5、不估计不裁剪"一致）。
- **`contrast.csv` 0.2 档三估计量**：DR/IPW/SNIPS 对 `no_coupon` = 0.065463/0.080212/0.067724，对 `same_budget_random` = 0.085714/0.074849/0.064207；p = 0.016715/0.005876/0.015828 与 0.030906/0.063065/0.087814。48 行 diff/p 不符数 = 0。
- **§4.3 成本表**：0.2 档 `coupon_cost_total_per_assigned_user` 与 `refund_rate_30d` 的 value/se/ci_low/ci_high/n 全部与正文一致（no_coupon 0.000000/0.007912，random 0.186453/0.008724，greedy 与 local_swap 均 0.243164/0.008818）。
- **顶层登记表在评审期间发生漂移**：我开始时读到 41 条 / `total_bytes` 15 858 444 / `last_refreshed_at` 2026-10-28T04:24:36+08:00 / `registry_repairs` 3 条（**正是正文 line 437 与 line 469-475 所钉住的值**），复审中途变成 **42 条 / 15 861 713 / 05:44:00 / 4 条**。两个时点上"全表逐条复算不一致 = **0**"、`sum(bytes)` = 声明值都成立，f01 的两条记录（`f01_freeze` `9973376bbddf`/12 151 B、`f01_meta` `1c89ca9f0b58`/17 335 B）**逐字节稳定**。所以正文那两个计数器不是写错，而是**钉住了可变量、落笔即过期**（见 N-8）。

---

## §2 复算留痕

所有脚本在 `out/scratch/f01_rereview/`，全部 `EXIT=0`。运行方式统一为：

```
cd "C:/Users/26382/.qoder-cn/worktrees/app/c509bd/营销数分项目"
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe "out/scratch/f01_rereview/<脚本>" > "out/scratch/f01_rereview/<输出>" 2>&1
```

| 脚本 | 输出 | 落盘时间 | 覆盖内容 |
|---|---|---|---|
| `a_hashes.py` | `a_out.txt`（3 990 B） | 05:16，05:47 重跑 | 目录级/顶层 coverage.json 逐条 sha+bytes、`meta.artifacts` 11 张、证据副本 vs 正本、4 个 gzip 帧的 `dataframe_sha256`、`freeze.json` 文件 sha 与 `freeze_id` |
| `b_tables.py` | `b_out.txt`（13 055 B） | 05:21 | 11 张表的行数、ESS（P1-3）、`increment` 代数一致性（P1-2）、`contrast` 48 行、`family` Holm 独立复算、`audit` 超预算与真值绑定（P1-4）、`ope_vs_audit` 48 行、`targeting` 恒等式、`random_seeds → random_summary` 全量复算（P0-2）、`equal_spend_*` 复算 + 跨档回归（P1-7）、`policy_meta` |
| `c_frames.py` | `c_out.txt`（16 593 B） | 05:33–05:34 | **逐用户重建**：自行重实现 `child_rng`/`greedy_by_ratio`/`random_under_budget`/`local_swap`/`_mask_sha256`/`truth_audit_table`/`targeting_decomposition_table`/`policy_value_ipw`/`policy_value_snips`/分臂 ESS，**故意不 import** `v3_f01`/`v3_policy`（避免拉起 sklearn/pyarrow，把 RSS 压在限内）；32 个 mask、256 个审计格、160 个 targeting 格、64 个 IPW/SNIPS 行、32 个配对对比行、10 个随机种子抽查、DR 可重建性判定 |
| `d_sources.py` | `d_out.txt`（8 336 B） | 05:37 | P1-5 源码哈希活体复算、`freeze_id` canonical JSON 复算、逐用户帧哈希、**超预算机制裁决（D4）**、**跨档等实际支出合并回归（D5）**、P1-6 的 E 表数字定位（D6） |
| `e_final.py` | `e_out.txt`（10 274 B） | 05:42 | 参考帧哈希标注（P2-9）、门禁 ESS 数字、§4.5 中位数、DR 全 8 档 `n_random_at_least_targeted`、测试函数计数与日志存在性、`v3_policy_evidence` 是否被 import、§4.3 成本表 |
| （内联命令） | 见下 | 05:52 | 两次 freeze 清单逐字段对比 + 11 张表逐字节对比 |
| （内联命令） | 见下 | 05:54 | 两份 pytest 日志的头尾与"是否含汇总行/命令行"判定 |

### 2.1 P0-3：仅凭证据包重建（`c_frames.py`，`c_out.txt` C8 段）

```
  mask 哈希不一致      : 0/32
  n_selected 不一致    : 0/32
  predicted_value 不一致: 0/32
  predicted_cost 不一致 : 0/32
  审计表失败项         : 0/256
  IPW+SNIPS 失败行     : 0/64
  random_seeds 抽查失败: 0
>> contrast(IPW/SNIPS) 重建：检查 32 行，失败 0 行
>> targeting: 160/160 匹配；恒等式残差 1.734723475976807e-17；share 之和残差 1.7763568394002505e-15
```

`a_out.txt` 关键行：

```
records: 18 total_bytes: 9490785 in_repository_bytes: 4185712
[OK ] dir f01_selection   bytes=2094525/2094525 sha_match=True   （其余 17 条同为 OK）
sum(bytes)=9490785  declared total_bytes=9490785  match=True
sum(in_repository bytes)=4185712 declared=4185712 match=True
磁盘有但未登记: ['coverage.json']
副本与正本不一致张数: 0 （共 11 张）
selection_7cols  rows=60000  MATCH got=3ef75e0ff76477bb declared=3ef75e0ff76477bb
observed         rows=60000  MATCH got=54aef8829db5723b declared=54aef8829db5723b
truth_audit_only rows=60000  MATCH got=da000c1f481ea7a7 declared=da000c1f481ea7a7
freeze.json sha256 = meta.freeze.file_sha256 = 9973376bbddf4719e9eddbf868b736d446cb1f3b73a3306cdc51b4ef4b69bcde  match True
freeze_id in file = meta.freeze.freeze_id = b8402f30d82c96af4c0809d25522635c022988fdd817c9956a4ab445706d66f9   match True
source_hashes 份数: 48 ；freeze 内 source_hash_combined: None（只在 meta 里，= d3e169f1…）
meta.artifacts 不一致条数: 0（policy_meta 32 / value 96 / increment 96 / contrast 48 / cost 64 / family 2 / audit 32 / ope_vs_audit 48 / targeting 16 / random_seeds 1600 / random_summary 16）
```

### 2.2 DR 主估计量 —— 【无法核】

这是本报告唯一一处【无法核】，理由必须写全：

```
（c_out.txt C7 段）
observed.csv.gz 列 = ['user_id', 'treatment', 'net_profit', 'coupon_cost', 'any_refund_30d', 'design_probability']
  -> 是否含 mu1/mu0/influence 列: 无
features.csv.gz 存在于证据包: True (1,471,449 B)
meta.stage_seconds = {'d03_rebuild': 242.286, 'observed_frame': 0.423, 'ope': 10.530,
                      'random_policy_distribution': 39.794, 'total': 296.913}
value.csv 中 dr_increment 行数 = 32（0.2 档）：
  no_coupon                          value=2.635177564304 se=0.057862696132
  random_same_budget                 value=2.614926462946 se=0.057925328361
  greedy_incremental_profit_per_cost value=2.700640935421 se=0.058497850735
  greedy_local_swap                  value=2.700640935421 se=0.058497850735
```

**判定：DR 的全部数值（32 行 `value` 的 DR 部分、96 行 `increment` 的 32 行 DR、48 行 `contrast` 的 16 行 DR、`family.csv` 两行、`ope_vs_audit` 的 DR 行、`random_seeds.dr_increment`/`dr_se` 共 1600 行、`random_summary` 的 8 行 DR）= 【无法核】。**
理由：DR/AIPW 需要交叉拟合的 `mu1`/`mu0`（以及影响函数），证据包**没有落盘**这些中间量；`features.csv.gz` 只是输入特征，不含拟合结果。要重建只能重跑 `fit_ope_nuisances`，而 `meta.stage_seconds.ope = 10.53 s` 表明这一步是**模型拟合**，本次复审被明确禁止启动任何模型拟合（且 F02 正式作业正在占 2 个 worker、空闲内存 2.7–4.7 GB）。
**能核的部分**：DR 各行之间的**代数关系**是可核的，且全部通过——`increment.se_increment` 与 `contrast.se_diff` 一致、`z = value/se`、`p = 1−Φ(z)`、Holm 校正、同族下界反演，96+48+2 行不符数 = 0。**不能核的是 DR 的数值本身对不对。**
对照：IPW/SNIPS 只需 `treatment`/`net_profit`/`coupon_cost`/`design_probability` + 名单 mask，**全部可从证据包重建**（64/64 值行 + 32/32 配对行，0 失败）。所以缺口是 DR 独有的，而这恰好是主口径 ⇒ 构成 N-2。

### 2.3 P0-2：随机策略分布（`b_out.txt` §8）

```
random_seeds 行数: 1600  档数: 8  每档 seed 数: [200]  seed 范围: 0 199
0.2/audit: mean=0.067280 sd=0.011802 q10=0.053296 q50=0.066650 q90=0.082572
           frozen=0.053765 rank_low=0.1100 targeted=0.085638 diff=0.018358
           mcse=0.000835 z=21.997 p=0.000e+00 n_at_least=15   支出范围=[11570,13050] sd=296.3851
0.2/dr_increment: mean=0.053702 sd=0.035933 q10=0.008081 q50=0.053660 q90=0.100050
           frozen=-0.020251 rank_low=0.0150 targeted=0.065463 diff=0.011761
           mcse=0.002541 z=4.629 p=1.838e-06 n_at_least=68
16 行汇总复算最大绝对差: {mean:0.0, sd:0.0, q10:0.0, q50:0.0, q90:0.0, frozen:0.0,
                          rank_low:0.0, targeted:0.0, diff:0.0, mc_se:0.0, z:0.0, p:0.0, n_at_least:0.0}
audit n_random_at_least_targeted 按档: {0.04:165, 0.1:77, 0.2:15, 0.3:0, 0.4:0, 0.6:1, 0.8:0, 1.0:200}
dr    n_random_at_least_targeted 按档: {0.04:50,  0.1:57, 0.2:68, 0.3:36, 0.4:89, 0.6:54, 0.8:79, 1.0:200}
```

（DR 全档值见 `e_out.txt` E4；正文只报了 0.2 档的 68/200 ⇒ 见 N-5。）

### 2.4 P1-2：配对 SE（`b_out.txt` §2/§6）

```
96 行代数一致性（increment=level差、z=inc/se、p=1-Φ(z)）不符数: 0
  DR 0.2 no_coupon                          inc=0.000000000 se=0.000000000 p=nan
  DR 0.2 random_same_budget                 inc=-0.020251101 se=0.039872688 p=0.694236
  DR 0.2 greedy_incremental_profit_per_cost inc= 0.065463371 se=0.030779164 p=0.016715
  DR 0.2 greedy_local_swap                  inc= 0.065463371 se=0.030779164 p=0.016715
文档 §4.5 用的 0.039873 是否为 random 的配对增量 SE: 0.03987268763521187   ← 是
no_coupon 水平 SE（旧稿误用的尺子）: 0.05792532836119538                   ← 已不再被使用
48 行 error/z/sign 不符数: 0
0.2 随机−不发券: err=-0.074016 ope_se=0.039873 |err|/se=1.856（正文写 1.856 / 0.039873）
```

### 2.5 P1-3：ESS（`b_out.txt` §1、`e_out.txt` E2）

```
ess_fraction_treated  max = 1.0   >1 的行数 = 0
ess_fraction_control  max = 1.0   >1 的行数 = 0
value(DR 32 行) 与 meta.gates 的 ESS/passed 不一致数: 0
0.04 random_same_budget                 ess_t= 1445.0(0.048199) ess_c=28540.0(0.950700) passed=False
0.8  random_same_budget                 ess_t=29270.0(0.976318) ess_c=  708.0(0.023584) passed=False
0.8  greedy_incremental_profit_per_cost ess_t=29771.0(0.993029) ess_c=  215.0(0.007162) passed=False
0.8  greedy_local_swap                  ess_t=29771.0(0.993029) ess_c=  215.0(0.007162) passed=False
value.csv 96 行中 reliability_passed=False 行数 = 12
meta.gates 中 passed=False 的格子数 = 4（文档称 4）
ope_vs_audit.csv 48 行中 reliability_passed=False 行数 = 7（文档称 7），分布 {0.04: 2, 0.8: 5}
（c_out.txt C3 另核到 0.2 档 greedy ess_t 11791(0.393296) / ess_c 18374(0.612059)、random ess_t 7305(0.243662)，全对）
```

### 2.6 P1-5：源码哈希（`d_out.txt` D1/D2）

```
freeze.source_hashes 记录条数 = 48    按目录分布 = {'configs/v3': 7, 'configs': 2, 'sql': 2, 'src': 37}
文件缺失 = 0    哈希不一致 = 0
由记录字典重算 combined = d3e169f1bd3d782226d2216faa63d3a8ef69d39a8d47e270814aab79eb037bc9
meta.source_hash_combined = d3e169f1bd3d782226d2216faa63d3a8ef69d39a8d47e270814aab79eb037bc9   一致: True
活体枚举条数 = 48（记录 48）；活体新增 = 0；记录中已消失 = 0
活体 combined = d3e169f1…  与记录相同: True
scripts/ 是否被绑定: 否
meta.git_commit = e0048100233b4c6df5cef1931eda0c2704e63815（活体 HEAD = 0765a0a6…，属设计使然）
复算 freeze_id = b8402f30d82c96af4c0809d25522635c022988fdd817c9956a4ab445706d66f9 = 记录值  一致: True
freeze.json 是否含 source_hash_combined 字段: False ；是否含 truth/nuisance 哈希字段: 无
```

### 2.7 N-1 裁决：超预算的真实机制（`d_out.txt` D4）

```
cost_hat: min=0.0484018994911  <=0 人数=0  <0.01 人数=0  <0.1 人数=15
源码 v3_f01.py:193-194 与 v3_policy_grid.py:70-71 都强制 cost_hat>0，
因此"预测成本为 0 的人"在本 rep 的人数 = 0（措辞与数据矛盾）
corr(cost_hat, cost_true) = 0.081482      全体 cost_true=10 的比例 = 0.084283
0.2 档贪心：n=23437 预测支出=11999.505 真实支出=15410.0
  入选者 cost_hat 均值 = 0.511990（全体 0.819836）
  入选者 cost_true=10 比例 = 0.065751（全体 0.084283）   ← 反而更低
  入选者 cost_true 均值 = 0.657507（全体 0.842833）      ← 反而更低
  入选者 tau_true 均值 = 0.219238（全体 0.279134）
  预测支出/真实支出 = 0.778683 → 真实支出比预测高 28.42%
>> 正确机制：贪心按 cost_hat 升序取人（τ̂ 恒定），把预测成本最低的人先拿完；
   cost_true∈{0,10} 与 cost_hat 相关性弱（0.0815），入选者人头真值成本反而更低，
   但人数多 60.7%（23437 vs 14589），于是总真值支出超过预测预算。
   不是"预测成本为 0 当免费"。
```

### 2.8 N-3 裁决：等实际支出的跨档插值（`d_out.txt` D5）

```
样本 = 1400 行（8 档去掉退化的 1.00 档 → 7 档 × 200 种子）
x = audit_actual_spend/60000   范围 [0.035333, 0.827000]
合并 OLS: slope=0.332073451 se=0.001013720 t=327.579 intercept=-0.000740668 r2=0.987140
定向臂 0.2 档真实支出 = 15410.0 元 → x=0.256833
是否落在合并 x 范围内（插值）: True
预测"等实际支出的随机名单"增量 = 0.084547
定向真值增量 = 0.085638 → 差 = +0.001091
对比：§4.6"定向 − 随机分布均值" = +0.018358；§4.2 确证性差（同预测预算规则） = +0.031873
档均值插值（7 点）: slope=0.332256564 intercept=-0.000806336 预测=0.084528 差=+0.001110
相邻档线性插值（0.2 档 12355/0.067280 → 0.3 档 18551/0.101500，w=0.493063）: 预测=0.084153 差=+0.001485
>> 三种口径都落在 0.0841–0.0845，与定向 0.085638 只差 0.0011–0.0015；
   原评审 P1-7 预测的 ≈0.0851 被独立复现，文档 line 336"等支出比较做不了"过强。
（含 1.00 档的 1600 行变体给同样的 0.084547，r²=0.9910）
```

对照 §4.6 档内回归（`b_out.txt` §9）：0.2 档 `slope=-7.170236642e-06 se=2.783669070e-06 t=-2.5758 intercept=0.155870691 r2=0.032422922 pred=0.045377 diff=0.040260 target=15410`，随机支出范围 `[11570, 13050]`，`落在范围内=False`。档内 r² 仅 0.0324 且 x 覆盖不到 15 410 ⇒ `within_range=0` 是结构性必然，不能当成"等支出比较做不了"的证据。

### 2.9 §3.1 第二次 freeze_id 变更（内联命令，05:52）

```
old freeze_id bfb26807b9972685e467b863b11a0c30ca9cc76c398fd4ec62b9d2436d418614 created 2026-10-28T00:47:52+08:00
new freeze_id b8402f30d82c96af4c0809d25522635c022988fdd817c9956a4ab445706d66f9 created 2026-10-28T02:57:03+08:00
hashes 48 48
changed files 1 ['src/causal_growth/policy/v3_policy_evidence.py']
   src/causal_growth/policy/v3_policy_evidence.py 18ac6f40014af47a -> ca29cdbcc57728e1
identical keys 12 ['selection_sha256','user_id_sha256','design_probability_sha256','config_hash',
                   'budgets','family_contrasts','scenario','n_dgp','n_users','rep_id',
                   'chosen_model','selection_columns']
differing keys 0 []
backup tables 11
DIFFER v3_phase_F01_audit.csv
IDENT  v3_phase_F01_contrast.csv / cost / family / increment / ope_vs_audit / policy_meta /
       random_seeds / random_summary / targeting / value        （共 10 张 IDENT）
```

### 2.10 P2-5：pytest 日志（内联命令，05:54）

```
=== outputs/runs/f01_tests/full_suite.log  2066 B
  head: '........................................................................ [  5%]\n...'
  tail: '...[run] exit=0 start=2026-10-27 20:20:35 +0800 end=2026-10-27 20:28:04 +0800\n'
  has "passed": False    has command line: False
=== out/logs/pytest_full_20261028_0321.log  1527 B
  head: 'START 2026-10-28 03:21:18 +0800\n...'
  tail: '...[100%]\nEXIT=0\nEND 2026-10-28 03:27:42 +0800\n'
  has "passed": False    has command line: False
```

函数计数（`e_out.txt` E5，只读文件、不运行 pytest）：`tests/test_v3_f01.py` = **12** 个 test 函数、`tests/test_v3_f01_registry.py` = **5** 个，与正文 line 37 / line 443-444 的"12 项 / 12 + 5 项"数量相符。

**"12 项绿 / 5 项绿"= 【无法核】**：本次复审被明确禁止运行 pytest（全量约 6 分钟且与 F02 争内存）。可核的只有：函数个数 12 与 5、两份日志的 `exit=0`/`EXIT=0`、以及入库那份日志的时间戳（2026-10-27 20:20–20:28）**早于** ESS 修复与新表落盘 ⇒ 入库日志是修复前的、已过期。

### 2.11 §4.5 中位数（`e_out.txt` E3）

```
非 policy_vs_no_coupon 行数 = 16（文档称 16 条对比行）
|误差|/SE：有限值 15 行（NaN 1 行）
  中位数 = 0.608254   最大 = 2.079634（档 0.04 / selected_targeted_minus_same_budget_random）
  再排除 1.00 退化档：中位数 = 0.631856（14 行）
  全部 48 行（含 policy_vs_no_coupon）：中位数 = 0.654755
```

⇒ 正文 line 275 的"中位约 0.63"对应的是 **14 行**（剔除了 1.00 退化档），而不是它自己写的"16 条对比行"。最大值 2.080 与档号正确。见 N-4。

### 2.12 P2-9：参考帧哈希标注（`e_out.txt` E1）

```
参考帧列（9）= ['user_id','is_new','cart_value','purchase_propensity','predicted_profit',
                'tau_hat','cost_hat','tau_true','cost_true']
dataframe_sha256(全 9 列)      = 372a1bcc1345d552a01fcca77c2ac7cb83a4ef82027e0d8fc74bba74007cddb3
dataframe_sha256(7 列选人投影) = 3ef75e0ff76477bbbead946cf85ed9f1acda3a9a4622e257cb3ff9a8a5fb9b8b
meta.reference_frame.frame_sha256     = 372a1bcc…
meta.reference_frame.selection_sha256 = 3ef75e0f…
>> 372a1bcc… 对应的是【全 9 列帧】: True
>> 与证据包 selection_7cols 的哈希相同（=3ef75e0f…）: True
参考帧文件: out/e_evidence_formal/frame_rep0.csv 存在=True size=6,093,781
            sha256=c8fd698ed05b47a62f0bc21883ef3520821fc3e66e14893fc0cf7665b69c54e0
            （= outputs/evidence/e_evidence_rep0_a/frame_rep0_constant.csv，逐字节相同）
```

⇒ 正文 line 78 / line 450 把 `372a1bcc…` 称作"7 列选人哈希"是**错的**（line 89 写对了 `3ef75e0f…`）。原 P2-9 **未修**。

---

## §3 新发现的问题

### P1（3 条，均不需重跑）

**N-1（P1）｜为修 P0-1 而新写的机制解释与数据矛盾**
- 位置：`docs/v3_phase_F01_ope.md` line 27（§0.12）、line 361-362（§4.8）
- 原文：line 27 "所以贪心实际上是按 `cost_hat` 升序取人（**把大量预测成本为 0 的人当免费**）"；line 361-362 "按 `τ̂/cost_hat` 排序等价于按 `cost_hat` 升序取人，**优先拿走预测成本为 0 的人；这些人真值成本并不为 0**，于是既超预算、又不是真值效应最高的人。"
- 实测（§2.7）：`cost_hat` 最小值 0.0484，`cost_hat ≤ 0` 人数 **0**、`< 0.01` 人数 **0**、`< 0.1` 人数 **15**（占 0.025%）。而且 `v3_f01.py:193-194`（`require_freeze_frame`）与 `v3_policy_grid.py:70-71` 两处都会对 `cost_hat ≤ 0` 直接 `raise`——"预测成本为 0 的人"在架构上不可能进入名单。
- 更严重的方向性错误：line 362 说"这些人真值成本并不为 0"暗示入选者真值成本偏高；实测**入选者的真值人均成本反而更低**（`cost_true` 均值 0.657507 vs 全体 0.842833，`cost_true=10` 比例 0.065751 vs 0.084283）。超预算的真实原因是**人数多 60.7%**（23 437 vs 14 589）叠加 `cost_hat` 在低成本尾部的**水平标定偏差**（`corr(cost_hat, cost_true) = 0.0815`，预测总支出 11 999.5 vs 真实 15 410，低 28.42%）。
- 为什么是 P1：P0-1 的要求就是"改正机制措辞"。改出来的句子仍然是错的，而且这次错在一个可被一行 `describe()` 否证的事实上；这条句子还承担着解释 7/8 档超预算的功能（§4.8 是护栏小节），会被下游 F02/G 直接继承。
- 修法（无需重跑）：把两处改成"贪心按 `cost_hat` **升序**取人（τ̂ 恒定），因此优先吃满预测成本最低的那一段人群；`cost_hat` 与 `cost_true` 相关性仅 0.0815、且在低成本段系统性**低估**，入选人数比随机臂多 60.7%，两者叠加使真实支出比预测预算高 28.42%"。数字全部已在 `audit.csv`/`policy_meta.csv` 里，不需要新算。

**N-2（P1）｜主口径 DR 无法从证据包重建，line 10 的可复算声明过强（AGENTS §12.1）**
- 位置：`docs/v3_phase_F01_ope.md` line 10；`outputs/evidence/f01_ope/observed.csv.gz`（6 列，无 mu1/mu0/IF）
- 事实：见 §2.2。证据包能重建 IPW/SNIPS 的**全部**数值（64/64 值行 + 32/32 配对行，0 失败），但 DR 一个数都重建不了——DR 需要交叉拟合的 `mu1`/`mu0`，包里没有，`features.csv.gz` 只是输入。重建 DR 必须重跑 `fit_ope_nuisances`（`meta.stage_seconds.ope = 10.53 s`，模型拟合）。
- 为什么是 P1：AGENTS §12.1 的验收口径是"**只用 `outputs/evidence/` 就能重建文档里的关键数字**"。本文的**关键数字恰恰全是 DR**——line 17 的两条 Holm 结论（+0.065463 / +0.085714）、`family.csv` 两行、`contrast.csv` 0.2 档、`random_summary` 的 DR 行、§4.6 的 68/200。主口径落在门禁外，按 §12.1 最低即 P1。line 10 那句"每个数字都可由 …… 复算"因此是**过度声明**。
- 修法（二选一，都不需重跑主链路）：(a) 把 3 折交叉拟合的 `mu1`/`mu0`（或每用户影响函数）落盘进证据包并登记——60 000 行 × 2 列 float，gz 后约 1 MB，且它是确定性产物、可由 `d03_rebuild` 复现；(b) 若不愿落盘，把 line 10 改成"IPW/SNIPS/审计/targeting/名单哈希/ESS 可仅凭 `outputs/evidence/f01_ope/` 重建；**DR 需要 `mu1/mu0`（交叉拟合中间量，未落盘），其数值只能由 `scripts/31_f01_ope.py` 全链路重跑复现**"，并在 §3 表里显式标注哪一族数字属"重跑才能核"。推荐 (a)，因为它同时让 §12.1 对主口径成立。

**N-3（P1）｜"等支出比较做不了"过强；跨档等实际支出插值显示优势只剩 ~0.001**
- 位置：`docs/v3_phase_F01_ope.md` line 336（§4.6）、§0.9、§6.7
- 原文：line 336 "它们存在的意义恰恰是把'**等支出比较做不了**'这件事量化出来。"
- 事实（§2.8）：`equal_spend_*` 那 10 列本身复算全对，但它们是**档内**回归，x 只覆盖同档 200 个种子的支出（0.2 档 [11 570, 13 050]，sd 仅 296.4 元），15 410 远在范围外 ⇒ `within_range=0` 是结构性必然，不是"比不了"的证据。跨档合并（1 400 行，7 个非退化档 × 200 种子）给出 `r²=0.987140`、x 范围 [0.035333, 0.827000]，定向臂 x=0.256833 **在范围内**，预测等实际支出的随机增量 = **0.084547** vs 定向 **0.085638** ⇒ 差 **+0.001091**。档均值拟合 0.084528（+0.001110）、相邻档插值 0.084153（+0.001485），三口径一致。
- 影响：§4.2 的确证性差 +0.031873 中约 **96%** 可归因于"定向臂多花了 30.9% 的钱"（15 410 vs 11 770）。原文把这一层完全交给了"做不了"，等于把一个**可算的**混杂留成了空白。这也正是原评审 P1-7 的核心关切（它当时用 E 的 `random_long` 表得到 ≈0.0851/≈0.0849），本次只用 F01 自己的证据包就复现了。
- 为什么是 P1：属结论层。§0.9 与 §6.7 是"限制"小节，读者会据它判断 +0.085714 的含金量；把一个 0.001 量级的残差说成"无法比较"，方向上是**放大**了结论。
- 修法（无需重跑）：在 §4.6 补一行跨档合并回归（slope 0.332073451、se 0.001013720、t 327.579、intercept −0.000740668、r² 0.987140、n=1400、x 范围、定向 x=0.256833 属插值、预测 0.084547、差 +0.001091），并把 line 336 改成"**档内**等支出比较做不了（同档 200 个种子的支出 sd 仅 296 元，覆盖不到定向臂的 15 410 元）；**跨档**合并插值可以做，结果是等实际支出下优势从 +0.031873 缩到 +0.001091，即约 96% 的表观优势来自多花 30.9% 的预算"。§0.9/§6.7 同步。

### P2（9 条）

**N-4（P2）｜§4.5 中位数的分母与自述不符**
`docs/v3_phase_F01_ope.md` line 275："16 条对比行的 |误差|/SE：最大 2.080（0.04 档 定向−随机），中位约 0.63"。实测：16 行里有限值只有 **15** 行（1.00 退化档 NaN），15 行中位 = **0.608254**；再排除 1.00 档得 14 行中位 = **0.631856**；全部 48 行中位 = 0.654755。"约 0.63"对应 14 行。AGENTS §12.5 要求"报相对差时必须跑 max，并说明分母"——这里分母没说清。改法：写成"16 条对比行中 15 条有限（1.00 档退化），|误差|/SE 中位 0.608、最大 2.080（0.04 档 定向−随机）；若再剔除 1.00 退化档，14 行中位 0.632"。

**N-5（P2）｜DR 口径的 `n_random_at_least_targeted` 只报了 1 档，且漏掉了对结论最不利的 0.40 档**
正文 §4.6/§8 只给 0.2 档的 68/200。实测 DR 全 8 档 = 50/57/**68**/36/**89**/54/79/200（对应 rank_low 0.075/0.060/0.015/0.130/**0.310**/0.750/0.385/0.000）。0.40 档 DR 有 **89/200 = 44.5%** 的随机名单不劣于定向，0.60 档 54/200、0.80 档 79/200 也都过半或接近。audit 口径同档是 0/1/0。只报 0.2 档（DR 里最有利的一档，rank_low 0.015）会让读者以为 DR 口径下"随机几乎追不上定向"。数据已在 `random_summary.csv` 里，只是正文没引。建议补一张 8 档 × 2 口径的小表。

**N-6（P2）｜= 原 P2-9，未修**
line 78 与 line 450 仍把 `372a1bcc…` 称作"7 列选人哈希"，实测它是**全 9 列帧**的 `dataframe_sha256`；7 列选人投影是 `3ef75e0f…`（line 89 写对了）。line 450 是验收清单里的勾选项，照它去勾会核错对象。见 §2.12。

**N-7（P2）｜`meta.reference_frame.path` 是机器相关的 `out/` 绝对路径**
`meta.json` 里存的是 `C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目\out\e_evidence_formal\frame_rep0.csv`——一个**不入库**的运行目录绝对路径（含用户名与 worktree 哈希）。虽然 §7 的复现命令已改指入库副本 `outputs/evidence/e_evidence_rep0_a/frame_rep0_constant.csv`（两者逐字节相同，sha256 `c8fd698ed05b47a6…`，6 093 781 B，我已核），且 `meta` 里同时存了 `selection_sha256`/`frame_sha256` 所以不影响可验证性，但这条路径在别的机器上必然失效，属证据元数据的卫生问题。建议改存仓库相对路径或至少加一个 `in_repository: true` 的别名。

**N-8（P2）｜正文钉住了可变的顶层登记表计数器，落笔即过期；F01 在顶层的登记粒度远低于 E**
line 437 "当前顶层索引 **41 条、`total_bytes=15 858 444`**"、line 469 "**41 条中**"、line 472-475 "`registry_repairs` 现有 **3 条**……35 → 41 条"。我在复审期间亲眼看到它变成 **42 条 / 15 861 713 / `last_refreshed_at` 2026-10-28T05:44:00+08:00 / 4 条 repairs**（E 的复审收尾所致）。两个时点上"全表逐条复算不一致 = **0**"都成立，f01 的两条记录（`f01_freeze` `9973376bbddf`/12 151 B、`f01_meta` `1c89ca9f0b58`/17 335 B）逐字节稳定 ⇒ 数字不是错的，是**钉错了对象**。另外：E 在顶层拿到 **22** 条逐文件记录，而 F01 的 4 个帧 + 11 张表副本只出现在**目录级**索引里，顶层只有 2 条（freeze/meta）。建议正文改成"以 `outputs/evidence/f01_ope/coverage.json` 的 18 条为准（逐条 sha+bytes 可复算），顶层索引只登记 freeze/meta 两条、其条数与 `total_bytes` 会随其他阶段刷新而变，不作为 F01 的验收对象"，并考虑把 F01 的帧也提升到顶层以对齐 E 的粒度。

**N-9（P2）｜`policy_masks_long.csv.gz` 标 `in_repository: false`**
5 305 073 B / 1 920 000 行，是 18 条记录里最大的一条，却标为不入库。它**完全可派生**（我已从 `selection.csv.gz` + `freeze.budgets[*]` 独立重建全部 32 个 mask，sha256 逐一匹配 `policy_sha256`），所以不影响 §12.1；但"目录级索引里最大的一条不在库内"这件事应当在正文里说一句，否则读者会以为证据包缺件。

**N-10（P2）｜= 原 P2-5，部分修**
两份 pytest 日志都**没有** `N passed` 汇总行、也**没有**命令行；入库那份（`outputs/runs/f01_tests/full_suite.log`，2026-10-27 20:20:35–20:28:04，1248 点，`[run] exit=0`）**早于** ESS 修复与 4 张新表，属过期证据；修复后那份（`out/logs/pytest_full_20261028_0321.log`，03:21:18–03:27:42，1264 点，`EXIT=0`）**不入库**。见 §2.10。建议把 03:21 那份连同 `pytest … -q --basetemp … -p no:warnings` 的完整命令行与末行汇总一起收进 `outputs/runs/f01_tests/`，并在正文 line 37 注明日志时间戳必须晚于最后一次源码/表变更。

**N-11（P2）｜§3 的"字段/值"单表把 `freeze.json` 与 `meta.json` 的字段混在一起，未注明各属哪个文件**
line 82-91 是一张表，但 `source_hash_combined`、`truth_sha256`、`frame_hashes.*`、`reference_frame.*`、`stage_seconds`、`gates` 只在 `meta.json` 里，`freeze.json` 的顶层键只有 16 个（`budgets, chosen_model, config_hash, created_at, design_probability_sha256, family_contrasts, freeze_id, n_dgp, n_users, rep_id, scenario, schema, selection_columns, selection_sha256, source_hashes, user_id_sha256`）——实测 `freeze.json` **不含** `source_hash_combined`（值为 None）、**不含**任何 truth/nuisance/frame 哈希。读者按 §3 去 `freeze.json` 里找 `source_hash_combined` 会找不到。line 93-101 的补充说明写得很好（48 份逐文件哈希才是绑定、`meta.git_commit` 是过期标签、`d15cf24d…` vs `6a4289ef…` 的区别），但表格本身该加一列"所在文件"。

**N-12（P2）｜= 原 P2-8，未修**
`policy_meta.predicted_value / n_selected = 0.29380318` 对全部 32 行成立（`tau_hat` 唯一值个数 = 1），即"预测价值 = 常数 τ̂ × 人数"。正文从头到尾没有注明"本阶段预测价值不含异质性"，而 `predicted_value` 是 §4.1 表里最像业务指标的一列，极易被下游当成模型质量证据。

### 措辞类残留（并入 P1-1 / P1-4 的部分修，不单列编号）

- line 17 "**按预声明口径**"、line 412 "**按预声明 DR 口径**"：`configs/` 里确实没有 `primary_estimator` 键，"预声明"三字仍不成立。line 56-57 已经诚实披露"由源码哈希冻结，无 YAML 字段"，把 line 17/412 改成"按本阶段主口径（DR，见 §2.1；该选择由源码哈希冻结、无 YAML 预声明字段）"即可自洽。
- line 61 "真值只在冻结落盘并复算通过后**才解封**"、line 234 "且在冻结复算通过之后**才生成**"：`v3_models.py:2067` 在 `_d03_rep_artifacts` 内就把 `tau_true`/`cost_true` 物化了，早于冻结写盘。改成原评审给的那句"真值列在 D03 产物中已存在，但 F01 的接口层拒绝真值列、且冻结清单不含真值；审计表通过 `audit_truth_sha256` 绑定所用真值输入"。

---

## §4 未覆盖范围

本次复审**没有**覆盖以下内容，判定不建立在它们之上：

1. **DR 的全部数值**（32 行 value / 32 行 increment / 16 行 contrast / 2 行 family / 1600 行 `random_seeds.dr_*` / 8 行 `random_summary` DR）——证据包未落盘 `mu1`/`mu0`/影响函数，重建需模型拟合，被本次约束禁止。只核了 DR 各行之间的代数关系（全对）。详见 §2.2。
2. **pytest 是否真的绿**——被明确禁止运行 pytest。只核了两个测试文件的函数个数（12 / 5）与两份日志的 `exit=0`。
3. **`net_profit` / `coupon_cost` / `any_refund_30d` 的 DGP 构造是否正确**——属 D 阶段范围，本次只核了它们被 OPE 消费时的口径（`design_probability` 唯一值 0.5、e ≡ 0.5 不估计不裁剪）与 §4.3 成本表的算术。
4. **`greedy_local_swap` 的交换逻辑本身**——只核到它在 8 档所有数值列与 `greedy_incremental_profit_per_cost` **全等**，并从源码（`v3_policy.py:594-616`，`max_passes=10`、`exchange_candidate_limit=500`、只在**严格**更大时接受）+ τ̂ 恒定推出这是必然退化。没有构造非退化 τ̂ 来正向验证交换逻辑（那需要重跑）。
5. **E 阶段 200 种子流与 F01 200 种子流是否同一条**——只核了 F01 自己的 `child_rng(master_seed=20240101, stream="f01.policy.random", index=seed)` 复现了冻结名单（`seed=0` 逐位相同）以及 §5 引用的 E 表数字各自归位（P1-6）。没有去比 E 与 F01 的随机名单是否相同（正文也没这么声称）。
6. **`d03_rebuild`（242.3 s）与 `random_policy_distribution`（39.8 s）两个阶段的复现**——属重跑，被禁止。只核了它们的**输出**（选择帧哈希、`chosen_model=constant`、1600 行随机分布）。
7. **F02 正式 200 rep 作业**——正在运行，未触碰；本次所有写入仅限本报告与 `out/scratch/f01_rereview/`。四个绑定 glob、`scripts/30_merge_f02_formal.py`、三个 `f02_*.sh` 全程只读（P1-5 的哈希复算本身就是只读的，且 48/48 匹配说明运行期冻结未被破坏）。
8. **原评审的 10 条 P2 中除 P2-5/P2-8/P2-9/P2-10 之外的 6 条**——未逐条核（任务只要求核 3 P0 + 8 P1；这 4 条因与结论或验收清单直接相关才抽核）。
9. **文档的中文表述质量、章节顺序、图表可读性**——非科学性问题，不在范围内。

---

## §5 评审留痕

### 5.1 读过的文件（全部只读）

规范与目标：
- `AGENTS.md`（§4 口径红线、§7.4 子代理结论视为草稿、§11 源码只读纪律、§11.2 运行期冻结、§12.1–§12.7 证据与门禁）
- `GOAL.md`（line 7 交接节点、line 25 F01 验收行"未证实"、line 36 R01 闭环行）

评审与正文：
- `docs/reviews/v3_phase_F01_review.md`（163 行，全文；提取 3 P0 + 8 P1 + 10 P2 的逐条要求）
- `docs/v3_phase_F01_ope.md`（481 行，全文；重点行 10/17/27/37/39/56-57/61/78/82-101/133-134/234/275/336/361-362/375-382/412/422/428-429/437/443-444/450/469-475）
- 命名先例参考：`docs/reviews/v3_phase_D03_rereview.md`、`docs/reviews/v3_phase_E_rereview.md`

源码：
- `src/causal_growth/evaluation/v3_f01.py`（`:25` docstring、`:60 FREEZE_COLUMNS`、`:92 PRIMARY_ESTIMATOR`、`:174 require_freeze_frame`、`:193-194 cost_hat>0`、`:222 _array_sha256`、`:232 _mask_sha256`、`:274 build_policies`、`:325 _freeze_payload`、`:379 _freeze_id`、`:415 verify_freeze_manifest`、`:496-527 require_truth_frame/truth_frame_sha256`、`:534 truth_audit_table`、`:1058-1097 targeting_decomposition_table`、`:1124 random_policy_masks`、`:1157 random_policy_distribution`）
- `src/causal_growth/evaluation/v3_ope.py`（`:355-368` ESS 权重，P1-3）
- `src/causal_growth/policy/v3_policy.py`（`:359-429 greedy_by_ratio`、`:594-616 local_swap`、`random_under_budget`）
- `src/causal_growth/policy/v3_policy_grid.py`（`:70-71 cost_hat>0`、`:98 run_policy`）
- `src/causal_growth/estimate/v3_models.py`（`:1932 _audit_truth_for_test`、`:1990 _d03_rep_artifacts`、`:2067` 调用点，P1-4）
- `src/causal_growth/data/v3_pipeline.py`（`:38-45 pipeline_source_hashes` 的 4 个 glob）
- `scripts/31_f01_ope.py`（`:372-389 _check_reference_frame`、`:503-505 pipeline_source_hashes/source_hash_combined`、`:525 verify`、`:574` 真值读取、`:640-700` meta 组装、`:645 primary_estimator_frozen_by`、`:665-675 frame_hashes`）
- `configs/v3/evaluation.yaml`（`:40-51 benefit_evidence`；`grep -rn "primary_estimator" configs/` → 空）
- `tests/test_v3_f01.py`（12 个函数；`:201-202` 审计前缀断言、`:215` `audit_truth_sha256` 断言、`:288-290` ESS ∈ (0,1] 断言）
- `tests/test_v3_f01_registry.py`（5 个函数）

证据与产物：
- `outputs/evidence/f01_ope/`（`coverage.json`、`freeze.json`、`meta.json`、`selection_7cols.csv.gz`、`observed.csv.gz`、`features.csv.gz`、`truth_audit_only.csv.gz`、`policy_masks_long.csv.gz` + 11 张表副本）
- `outputs/evidence/coverage.json`（顶层，评审期间观测到 41 → 42 条）
- `outputs/evidence/e_evidence_rep0_a/`（`frame_rep0_constant.csv`、`meta_constant.json`、`v3_phase_E_random_summary.csv`、`v3_phase_E_conservative.csv`）
- `outputs/evidence/e_evidence_rep0_b/`（`meta_cf.json`、`v3_phase_E_random_summary_cf.csv`、`v3_phase_E_conservative_cf.csv`）
- `outputs/tables/v3_phase_F01_*.csv`（11 张正本）
- `out/f01_ope_formal_20261028_0043/freeze.json`（被取代的那次）、`out/scratch/f01_tables_backup_0049/`（11 张备份表）
- `out/e_evidence_formal/frame_rep0.csv`（只做哈希/字节比对，未作为复现依赖）
- `outputs/runs/f01_tests/full_suite.log`、`out/logs/pytest_full_20261028_0321.log`、`out/logs/f01_rerun_20261028_0253.log`、`out/scratch/verify_f01_rerun.py`、`out/scratch/verify_f01_r3.txt`

### 5.2 跑过的命令（时间均为 2026-10-28 北京时间）

| 时间 | 命令 | 输出 | 用途 |
|---|---|---|---|
| 05:16 | `.venv/Scripts/python.exe out/scratch/f01_rereview/a_hashes.py` | `a_out.txt` | 证据包完整性：coverage 逐条、meta.artifacts、副本 vs 正本、4 帧 `dataframe_sha256`、freeze 文件 sha 与 `freeze_id` |
| 05:21 | `.venv/Scripts/python.exe out/scratch/f01_rereview/b_tables.py` | `b_out.txt` | 11 张表的表级复算：ESS、increment、contrast、family Holm、audit、ope_vs_audit、targeting、random_summary、equal_spend、跨档回归、policy_meta |
| 05:33–05:34 | `.venv/Scripts/python.exe out/scratch/f01_rereview/c_frames.py` | `c_out.txt`（171 行） | 逐用户重建：32 mask、256 审计格、160 targeting 格、64 IPW/SNIPS 行、32 配对行、随机种子抽查、DR 可重建性判定 |
| 05:37 | `.venv/Scripts/python.exe out/scratch/f01_rereview/d_sources.py` | `d_out.txt`（102 行） | P1-5 源码哈希、`freeze_id` canonical JSON、逐用户帧哈希、D4 超预算机制裁决、D5 跨档等实际支出回归、D6 E 表数字定位 |
| 05:42 | `.venv/Scripts/python.exe out/scratch/f01_rereview/e_final.py` | `e_out.txt`（115 行） | P2-9 哈希标注、门禁 ESS、§4.5 中位、DR 全档 n_at_least、测试计数与日志、§12.6 import 检查、§4.3 成本表 |
| 05:47 | 重跑 `a_hashes.py` | `a_out.txt` 覆盖 | 确认评审期间证据包未漂移（18/18 仍 OK） |
| 05:48 | 内联：读顶层 `outputs/evidence/coverage.json` | 见 §1 附末条 | 观测到 41 → 42 条漂移、`registry_repairs` 3 → 4、f01 两条记录稳定 |
| 05:52 | 内联：`out/f01_ope_formal_20261028_0043/freeze.json` vs `outputs/evidence/f01_ope/freeze.json` 逐字段对比 + 11 张表 vs `out/scratch/f01_tables_backup_0049` 逐字节对比 | 见 §2.9 | 核 §3.1 的第二次 `freeze_id` 变更（1 个源码哈希变化、12 个关键字段不变、10 张表 IDENT、只有 `audit.csv` DIFFER） |
| 05:54 | 内联：两份 pytest 日志的头尾 + "是否含 passed / 命令行" | 见 §2.10 | P2-5 / N-10 |
| 05:56 | `grep -n "F01" GOAL.md` | line 7 / 25 / 36 | 确认 F01 当前状态"未证实"与验收行内容 |
| 06:00 | 逐行 `sed -n '<n>p' docs/v3_phase_F01_ope.md`（33 个行号） | 见 §1/§3 引用 | 确认所有被引用的行号与原文逐字一致 |

约束遵守情况：全程 `.venv/Scripts/python.exe` + `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`；工作目录始终为 `C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目`，未 `cd` 到别处；所有路径加引号；**未运行 pytest**；**未做任何模型拟合 / n=200000 生成 / causal forest**（`c_frames.py` 特意不 import `v3_f01`/`v3_policy` 以避免拉起 sklearn/pyarrow）；单进程 RSS 远低于 300 MB（最大的一次是读 60 000 行的 `selection_7cols.csv.gz` 与 `features.csv.gz`）；**未写入**四个绑定 glob（`src/causal_growth/**/v3*.py`、`sql/v3*.sql`、`configs/v3*.yaml`、`configs/v3/*.yaml`）、`scripts/30_merge_f02_formal.py`、`out/scratch/f02_finalize.sh`/`f02_shard.sh`/`f02_chain.sh`；本次写入仅两个位置——本报告 `docs/reviews/v3_phase_F01_rereview.md` 与 `out/scratch/f01_rereview/`。P1-5 的 48/48 源码哈希匹配也从侧面证明运行期冻结未被本次评审破坏。

### 5.3 复算总量

| 复算对象 | 规模 | 不符数 |
|---|---|---|
| 目录级 coverage 记录（sha256 + bytes） | 18 | 0 |
| `meta.artifacts`（行数 + sha256） | 11 | 0 |
| 证据副本 vs `outputs/tables/` 正本（逐字节） | 11 | 0 |
| gzip 帧 `dataframe_sha256` | 4 | 0 |
| 冻结源码哈希 vs 活体工作树 | 48 | 0（缺失 0、不符 0、新增 0、消失 0） |
| 名单 mask sha256（从选人帧重建） | 32 | 0 |
| `policy_meta` 的 n_selected / predicted_value / predicted_cost | 32 × 3 | 0 |
| 审计表格子（`truth_audit_table` 重建） | 256 | 0 |
| targeting 分解格子（含恒等式与 share 之和） | 160 | 0（残差 ≤1.8e-15） |
| IPW + SNIPS 值行（value / SE / ESS / ess_fraction） | 64 | 0 |
| IPW + SNIPS 配对对比行（diff / paired SE） | 32 | 0 |
| `increment.csv` 代数一致性 | 96 | 0 |
| `contrast.csv` diff / p | 48 | 0 |
| `family.csv` Holm adjusted p + 同族单侧下界 | 2 × 2 | 0（最大绝对差 0.0） |
| `ope_vs_audit.csv` error / z / sign | 48 | 0 |
| `random_summary.csv` 全部汇总量 | 16 行 × 13 量 | 0（最大绝对差 0.0） |
| `equal_spend_*` 列 | 7 档 × 10 列 | 0 |
| 随机种子审计格抽查（0.2 档 seed 0–9） | 30 | 0 |
| `freeze_id`（canonical JSON，排除 `created_at` 与自身） | 1 | 0 |
| DR 数值 | — | **【无法核】**（见 §2.2） |

---

**复审结束。** 结论：**PASS WITH CONDITIONS**；3 条新 P1（N-1 机制措辞与数据矛盾、N-2 主口径 DR 不可从证据包重建、N-3 跨档等实际支出插值未做且"做不了"过强）+ 9 条新/残留 P2；三条 P1 均**不需要重跑**。建议 `GOAL.md` 中 **F01 继续保持"未证实"**，待 N-1/N-2/N-3 落地后再走一次窄口径确认（照 E 的三环做法），届时"通过"的含义须严格限定为"记录准确、断言范围正确（单 rep / R=0 / `constant` 模型 / 主预算 0.2 档）"，不含"定向有效"。
