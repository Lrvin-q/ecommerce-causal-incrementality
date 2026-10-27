# F01 阶段（历史留出 OPE）独立科学评审

评审对象：`docs/v3_phase_F01_ope.md`（205 行）、`src/causal_growth/evaluation/v3_f01.py`（984 行）、`scripts/31_f01_ope.py`（422 行）、`tests/test_v3_f01.py`（362 行）、`outputs/tables/v3_phase_F01_*.csv`（7 张表）、`outputs/evidence/f01_ope/{freeze.json,meta.json}`、`outputs/evidence/coverage.json`，以及上游 D03 rep0 逐用户导出与 E 阶段单 rep 证据。
评审方式：只读审查 + 轻量只读复算（`.venv/Scripts/python.exe`，`PYTHONUTF8=1`），未写任何 `outputs/`、`out/`，未运行任何 R>0 作业。
评审时间：2026-10-27 21:35（北京时间）。

---

## ① 总裁决

**PASS WITH CONDITIONS（有条件通过）。**

F01 的**计算正确性**经得起独立复算：0.2 档可由现有表/帧复核的数字（`policy_meta` 选人与预测成本、`audit`、水平值之差、单侧 p、Holm 调整 p 与下界、`ope_vs_audit`）在 1e-9～1e-6 内一致；SE 本身因缺逐用户 IF 帧只能采信表值并做代数一致性检查；7 张表的行数/唯一键/预算覆盖正确；`coverage.json` 的 F01 2 条记录哈希与字节数与实际文件一致；冻结清单在 F01 提交 `1ac6c30` 上可通过 `verify_freeze_manifest`；口径红线（分母 60,000、退款保留、7 日购买/30 日利润不混用、券成本只扣一次）在 F01 的使用方式上成立（`net_profit` 的 DGP 构造未回溯，见 ⑥）。

但**结论层**存在 3 项 P0：把"定向优于同预算随机"的显著结论建立在单次随机抽样（位于 200 次抽样的第 10 百分位）与一个约为真实效应 4.5～4.8 倍的 OPE 估计之上；把"定向"表述为人群定向，而 `tau_hat` 是常数（效应 102% 来自覆盖人数，单位人群效应为负）；证据包不足以按 AGENTS §12.1 重建审计数字。这三项不影响已发布的点估计，但影响"该结论能否作为对外结论"。修正后可转为 PASS。

---

## ② P0 阻断项

### P0-1 "定向（targeting）优于随机"的机制被误述：`tau_hat` 为常数，优势 100% 来自"覆盖更多人"，不含任何人群定向

- 证据：`out/e_evidence_formal/frame_rep0.csv` 的 `tau_hat` 只有 1 个唯一值 `0.29380318488356094`；`outputs/tables/v3_phase_F01_policy_meta.csv` 中 greedy 与 local_swap 的 `predicted_value / n_selected` 均等于 0.293803，即策略价值 = 常数 × 覆盖人数。
- 复核：按 `cost_hat` 升序装填 12,000 元得到的"最便宜 23,437 人"掩码，可逐位复现 greedy 行的 `n_selected=23,437`、`predicted_cost=11,999.505475`、`audit_increment=0.085638`、`audit_actual_spend=15,410`，说明策略本质是"先发最便宜的券、最大化覆盖人数"，不是 CATE 定向。0.2 档被选中人群的真实效应均值 0.219238，反而**低于**全体 0.279134；随机组为 0.221118。
- 分解：greedy−random 的真实增量 0.031873 = 覆盖效应 +0.032608（占 102.3%）+ 单位人群效应 −0.000735（−2.3%）。即定向项是**负的**。
- 影响：`docs/v3_phase_F01_ope.md` §3.5 与 §4 使用"定向优于同预算随机"的措辞，读者会理解为"模型挑人更准"。实际可支持的表述是"在预测成本口径下，低价券优先可覆盖更多用户，从而提升总增量；单位人群效应略低于随机"。这不是数值错误，是**结论口径错误**，且直接决定该阶段能否声称"定向能力"。
- 相关：`docs/v3_phase_F01_ope.md` §5 未把"chosen=constant ⇒ 无 CATE 异质性 ⇒ 本阶段不能检验定向"列为限制。

### P0-2 家族第二条（定向 vs 随机）的显著性不可外推：单次随机抽样处于 200 次抽样的第 10 百分位，OPE 估计约为 200 次抽样真实均值的 4.5～4.8 倍

- 证据：`outputs/tables/v3_phase_F01_contrast.csv` 中 `targeted_minus_random` 的 DR 点估计 0.085714，单侧 p=0.030906（`family.csv` 调整 p=0.033431）。
- 复核：`outputs/tables/v3_phase_E_random_long.csv` 的 0.2 档 200 次随机抽样：真实增量均值 0.067745、sd 0.010664；本次 F01 随机组为 0.053765，**恰有 20/200 次更低**（第 10 百分位）。greedy 真实增量 0.085638，200 次中仅 14 次随机抽样超过它；真实期望差 0.085638−0.067745=0.017893（若用 conservative 表的 0.066756 则为 0.018882），而 OPE 报 0.085714（4.5～4.8 倍），审计口径报 0.031873（1.7～1.8 倍）。
- 含义：F01 的"随机组"是一次抽样实现的策略，其真实值本身偏低；把它当作"同预算随机策略的期望"来比较，会把"随机抽样运气差"计入"定向优势"。按 200 次抽样的期望口径，效应量约 0.018，远小于 F01 报的 0.086；若仅把随机组换成 200 次均值、其余不变（即假定 OPE 对随机策略无偏），0.0179/0.046 对应单侧 p≈0.35，不会通过 Holm。
- 影响：`docs/v3_phase_F01_ope.md` §4 虽写了"随机基线是一次冻结抽样……不能与 E 表 200 个随机种子的均值直接比对"，但 §3.2/§5.2 只把"不稳健"归因于 IPW/SNIPS 不显著，未给出"第 10 百分位 + 效应量 4.5～4.8 倍"这两个量化事实；决策层 `claim_passed=True` 也未加限定。这属于结论边界问题（评审要点 6），构成 P0。
- 建议的最小修正：在同一冻结策略集合上补做"随机策略分布"（复用 E 的 200 seed 机制）或在文中明确"该结论仅针对本次抽到的这一条随机策略，不外推到随机策略期望"。

### P0-3 证据包不能按 AGENTS §12.1 重建关键数字：`coverage.json` 的 F01 记录只有 freeze/meta 两条，无逐用户观测、无策略掩码、无真值审计表，审计与 OPE 数字无法从证据目录复算

- 证据：`outputs/evidence/coverage.json` 共 12 条记录，其中 F01 只有 `f01_freeze`、`f01_meta` 两条；`outputs/evidence/f01_ope/` 仅 `freeze.json`（12,151 B）与 `meta.json`（15,084 B）。`freeze.json` 的 `budgets.<档>.policy_sha256`/`n_selected` 只存**掩码哈希与人数**，不存掩码；7 张表均未登记进 `coverage.json`。
- 复核：`verify_freeze_manifest` 能校验策略哈希，但无法重建 `audit` 表（需要 `mask`、`tau_true`、`cost_true`）与 `contrast`/`family`（需要逐用户 `pi/e/y`）。本次复算必须借助仓库外的 `out/e_evidence_formal/frame_rep0.csv`（60,000×9，6 MB）；该文件被 `.gitignore` 排除，交付后只能靠重跑 D03（254.7 s）再生，不是证据目录内的可复算输入。`meta.json` 只记录它的路径与哈希，不提供内容。
- 影响：AGENTS §12.1 要求"证据目录能重建关键数字"、§12.5 要求"报告最差相对差异"。当前证据包只能证明"策略没被改过"，不能证明"数字是这么算出来的"。这属于证据门禁的硬性缺口。
- 说明：`outputs/evidence/f01_ope/meta.json` 记录了表哈希与行数，可防篡改，但**不是**可重建输入。

---

## ③ P1 应改项

### P1-1 `family` 的"预声明 DR 主口径"在配置层无据：`configs/v3/evaluation.yaml` 只预声明了家族与 α，没有"主估计量为 DR"的键；DR 是 `v3_f01.py` 里硬编码的

- 证据：`configs/v3/evaluation.yaml` 的 `benefit_evidence` 只有 `family`（两条对比）与 `family_alpha_one_sided: 0.05`、`adjustment: holm_step_down_on_paired_one_sided_tests`；全文无 `primary_estimator` 键，`estimators` 只是 `[ipw_increment, dr_increment, snips_increment]` 的三元列表（IPW 还排在第一位），未标注主口径。`src/causal_growth/evaluation/v3_f01.py` 的 `family_table` 直接写死 `estimator == "dr_increment"`。
- 复核：`outputs/tables/v3_phase_F01_family.csv` 的两个对比均只列 DR；同表的 `contrast.csv` 显示 IPW p=0.063065、SNIPS p=0.087814，均不显著。
- 影响：`docs/v3_phase_F01_ope.md` §1/§3.2 称"预声明 DR 主口径"，实际是"运行时选定 DR"。虽然 DR 作为主口径在方法学上合理（双稳健、协变量调整），但"预声明"三字不成立。若审稿人按 IPW/SNIPS 读，结论反转。建议在配置中显式加 `primary_estimator: dr_increment` 并重签哈希，或在文中改为"本阶段以 DR 为主口径（理由：…），IPW/SNIPS 为敏感性分析"。

### P1-2 §3.5 的"1.28 SE"不是配对尺子：0.057925 是水平值的 SE，被拿来衡量增量误差，且该配对 SE 在任何表中都缺失

- 证据：`docs/v3_phase_F01_ope.md:145-146` 写"随机基线自身的价值误差 −0.074016，约其价值 SE（0.057925）的 1.28 倍"。1.28 的算术成立（0.074016/0.057925=1.2778），但 0.057925 是 `value.csv` 中 random 策略**水平值 2.614926** 的 SE；−0.074016 是**增量**（random−no_coupon：OPE −0.020251 vs 审计 +0.053765）的误差。水平 SE 含基线利润的跨用户方差，不能当作增量误差的尺子。
- 复核：文档同一段对两条家族对比用的是配对差 SE（−0.020174/0.030779≈0.66、+0.053841/0.045895≈1.17）。对 random−no_coupon 也应用配对 SE，但该值不在 `contrast.csv`（只列 targeted 的两条）也不在 `ope_vs_audit.csv`。由 C=A−B（A=targeted−no_coupon，SE 0.030779；B=targeted−random，SE 0.045895）只能得到 SE_C∈[0.0151, 0.0767]，对应 z∈[0.97, 4.90]；"1.28" 落在区间内但无任何计算依据，既不能证明一致也不能证明不一致。
- 影响：这是"OPE 与真值一致性"的核心论据；用水平 SE 替代配对 SE 会使对账偏差看起来比实际更接近抽样噪声。建议在 `ope_vs_audit.csv` 增加 `paired_se` 与 `z` 两列并统一口径。

### P1-3 可靠性门（ESS）的权重公式漏掉处理指示变量（估计量本身正确），控制臂 ESS 被高估约 2 倍，`ess_fraction` 出现 >1 的非法值

- 证据：`src/causal_growth/evaluation/v3_ope.py:358-359` 中 `w1=pi/e`、`w0=(1.0-pi)/(1.0-e)`，**未乘 T/(1−T)**；`_ess`（同文件 333-339）对全样本求和；而 `ess_fraction_control = ess_c / max(1, n_control)`（361-368）的分母只取对照臂人数。分子跨两臂、分母单臂，两者口径不一致。
- 复核：`outputs/tables/v3_phase_F01_value.csv` 的 `ess_fraction_control` 出现 1.998668（no_coupon）、1.512692（0.2 random）、1.217955（0.2 greedy）等 >1 的值；`ess_fraction_treated` 在 0.3 档 greedy 为 1.056938、1.0 档为 2.001334。理论上按臂计算的 ESS 占比应 ∈(0,1]。0.8 档表中为 1,418（0.047235）/424（0.014124），文档写 0.047/0.014（`docs/v3_phase_F01_ope.md:46-47`）；按正确公式（权重乘 T）控制臂约 709（0.0236）/212（0.0071）。
- 影响：门限判定（200 / 0.05 / 0.01）在报告预算上**未翻转**（0.8 档修正后仍低于 0.05，1.0 档满选不影响），但裕度被高估约 2 倍；若未来预算更极端会漏报支撑不足。属于实现缺陷，需修公式并重跑该表。

### P1-4 真值在冻结之前已被物化，文档 §3.4"在冻结复算通过之后才生成"与对象层事实不符；审计表只绑定 `audit_freeze_id`，无真值帧哈希

- 证据：`src/causal_growth/estimate/v3_models.py` `_d03_rep_artifacts` 先构造 7 列选择帧，随即调用 `_audit_truth_for_test` 并返回含 `tau_true`/`cost_true` 的 `frame`；`scripts/31_f01_ope.py` 的顺序是"重建 D03 → 选择 → 建策略 → 写 freeze → 复读校验 → 观测帧 → `ope_bundle` → 取 `truth = rep.frame[[...]]` → 审计"。即 `truth` 列在写 freeze 之前就存在于内存对象中，只是**没有被传给**拟合/选择。
- 复核：`v3_f01.py` 的 `_forbidden_columns` 拒绝 `_true`/`audit_`/`truth_`/`potential_`，`require_freeze_frame` 强制 7 列，`build_policies` 只用 `cost_hat`/`user_id`，`ope_bundle` 只用观测列；`tests/test_v3_f01.py` 有"含真值列被拒"的测试。**运行期隔离成立**，但"物理上未生成"不成立。
- 影响：文档表述过强，审计师会以为有"先冻结后解密"的硬隔离。建议改为"真值列在 D03 产物中已存在，但 F01 的接口层拒绝真值列、且冻结清单不含真值"，并给 `audit` 表加 `truth_sha256`（对 `user_id,tau_true,cost_true` 排序后哈希）以绑定审计输入。

### P1-5 在当前工作树上 `verify_freeze_manifest` 失败：`source_hashes` 与当前源码不一致（运行后源码被改）

- 证据：用当前工作树（HEAD `3332c9d` + 未提交改动）复算 `pipeline_source_hashes()` 得合并哈希 `a8453cdc…`，而 `outputs/evidence/f01_ope/freeze.json` 记录 `7012a17b…`。逐文件差异只有 `src/causal_growth/estimate/v3_models.py`（现 `7de5a364…`，运行时 `7d31518b…`）与 `src/causal_growth/evaluation/v3_f02_formal.py`（现 `79422c8a…`，运行时 `a1329c10…`）；`v3_f01.py` 本身仍为 `dec258da…`，与 meta 一致。
- 复核：在 F01 提交 `1ac6c30` 上，`v3_models.py` 哈希与运行记录一致，`verify_freeze_manifest` 通过；HEAD 的改动来自提交 `829f670`（`_calibration_stats` 的 docstring 改动）与未提交的 `v3_f02_formal.py` 修改。选择/设计/`user_id` 哈希均匹配。
- 影响：AGENTS §11 要求正式运行期间源码只读；运行后改动导致冻结清单在当前工作树上不可验证。虽不影响历史数字，但破坏"可复现"。建议：把 F01 运行固定在 `1ac6c30`，或在 freeze 中记录 `git_commit` 并在校验时允许"源码哈希仅在同一 commit 上比对"。

### P1-6 E 阶段的 200 次随机均值有两个不一致的版本，文档引用混用

- 证据：`outputs/tables/v3_phase_E_random_summary.csv` 给 mean 0.067745、sd 0.010664、n 14,638.56、spend 12,335.40；`outputs/tables/v3_phase_E_conservative.csv` 给 0.066756、14,640.790、12,339.35。`docs/v3_phase_F01_ope.md` §4 引用 conservative 的 0.066756，却用 random_summary 的 sd 0.010664。
- 影响：跨阶段对比的基准不唯一，"真实期望差"会在 0.0179（random_summary）～0.0189（conservative）间变动。建议统一为同一张表并注明抽样口径。

### P1-7 未做"同实际支出"的对照：greedy 实际花 15,410，random 花 11,770（+30.9%），"同预算"只在预测成本口径成立

- 证据：`outputs/tables/v3_phase_F01_audit.csv` 的 `audit_actual_spend_cny`：greedy 15,410、random 11,770（+30.9%）；两者 `policy_meta.predicted_cost` 均约 11,999.5。每选中一人的预测成本：greedy 11,999.505475/23,437=0.51199、random 11,999.961679/14,589=0.82254。
- 复核：用 `outputs/tables/v3_phase_E_random_long.csv`（8 档 × 200 seed）以 `actual_spend_cny/60000` 对 `true_value_per_user` 做线性回归，在 15,410 元（0.256833 元/人）处预测随机策略真实增量 ≈0.0851；按 0.2 档（均值 12,335 元/0.067745）与 0.3 档（均值 18,548 元/0.102533）线性插值得 ≈0.0849。两者都与 greedy 的 0.085638 基本相等——即"定向优势"在等实际支出下**消失**。
- 影响：`docs/v3_phase_F01_ope.md` §1/§3.1 称"同预算"，未说明是预测成本口径。审计表显示：greedy 相对预测预算超 28.4%（15,410/11,999.5−1），相对 random 的实际支出高 30.9%（15,410/11,770−1），两个口径需说清。这是结论边界问题，建议补"等实际支出"敏感性分析。

---

## ④ P2 建议

1. **`ope_vs_audit` 符号不一致 5 处**：0.04 档 random−no_coupon、0.04 档 targeted−random、0.1 档 random−no_coupon、0.2 档 random−no_coupon、0.6 档 targeted−random 的 OPE 差与审计差符号相反。建议逐行加"符号一致性"列，并在文中解释小预算档噪声。
2. **`family` 的置信水平列**：0.975/0.95 与 Holm 步降的 α 对应正确，但 `lower_bound` 的构造（用步阈值反演）应在表头注明"单侧下界"，避免被读成双侧。
3. **`scripts/31_f01_ope.py` 顺序**：建议把 `truth = rep.frame[[...]]` 移到 freeze 校验通过之后（哪怕只是形式上的重新读取），使代码顺序与文档叙述一致。
4. **`tests/test_v3_f01.py`**：补三类测试——(a) 冻结前 truth 未进入 `build_policies`/`ope_bundle` 的调用图（可用 mock 断言参数列集合）；(b) `audit` 表对 `truth_sha256` 的绑定；(c) `reliability_gate` 的 ESS 分数 ∈(0,1]。
5. **`outputs/runs/f01_tests/full_suite.log`**：只有进度点与 `exit=0`、时间戳（20:20:35–20:28:04），没有 pytest 的 "1248 passed" 汇总行与命令行；1248 只能靠数点得出。建议补 `pytest -q` 的 summary 行与 `--basetemp` 路径。
6. **`coverage.json`**：建议把 7 张表与 `frame_rep0.csv` 的哈希/行数一并登记，或明确"表由 meta.json 管理、coverage 只管证据文件"的分工。
7. **文档 §1.1 的 ESS 数字**：0.8 档 1418（0.047）/424（0.014）在修正公式后应改为约 709（0.024）/212（0.007），并说明门限未翻转。
8. **`policy_meta` 的 `predicted_value`**：因 `tau_hat` 为常数，该列等价于 `0.293803×n_selected`，建议加注"本阶段预测价值不含异质性"，避免下游误用为 CATE 价值。
9. **§2 哈希表述易误读**：句子写成"9 列帧做 7 列选人哈希对账：`372a1bcc…`"，但 `372a1bcc` 是 `meta.json` 的 `frame_sha256`（9 列帧），7 列 selection 是 `3ef75e0f…`；建议把两个哈希的适用对象写清。
10. **`require_truth_frame` 只校验 `freeze_id` 是 64 位字符串，不校验它等于本次 manifest 的 `freeze_id`**（`v3_f01.py:463`）。脚本调用正确，但文档 §6 写"`audit_` 表只在 freeze_id 匹配时生成"过强；建议在函数内比对 manifest 或在调用处传入已验证的 id 并加断言。

---

## ⑤ 已复核并被证实的数字清单

| 项目 | 表/列 | 文档值 | 复算值 | 差异 |
|---|---|---|---|---|
| 0.2 档 random 选人数 | `policy_meta.n_selected` | 14,589 | 14,589 | 0 |
| 0.2 档 random 预测成本 | `policy_meta.predicted_cost` | 11,999.961679 | 11,999.961679 | <1e-9 |
| 0.2 档 greedy 选人数 | `policy_meta.n_selected` | 23,437 | 23,437 | 0 |
| 0.2 档 greedy 预测成本 | `policy_meta.predicted_cost` | 11,999.505475 | 11,999.505475 | <1e-9 |
| 0.2 档 greedy=local_swap | 全 8 档人数/成本/审计/支出 | 相等 | 8/8 相等 | 0 |
| 审计 random 增量 | `audit_increment_vs_no_coupon_cny_per_user` | 0.053765 | 0.0537648333 | <1e-6 |
| 审计 random 支出 | `audit_actual_spend_cny` | 11,770 | 11,770 | 0 |
| 审计 greedy 增量 | `audit_increment_vs_no_coupon_cny_per_user` | 0.085638 | 0.0856378333 | <1e-6 |
| 审计 greedy 支出 | `audit_actual_spend_cny` | 15,410 | 15,410 | 0 |
| 审计 greedy 超预算 | `audit_within_budget_by_true` | False | False | 0 |
| DR 对比 targeted−random | `contrast.diff` | 0.085714 | 2.700641−2.614926=0.085715 | 1e-6（水平值舍入） |
| DR 单侧 p | `contrast.one_sided_p` | 0.030906 | 1−Φ(0.085714/0.045895)=0.030906 | <1e-9（SE 取自表，未独立重算） |
| 家族调整 p（两条） | `family.p_adjusted` | 0.033431 | Holm：min(1,2×0.016715)=0.033430；max(…,0.030906)=0.033430 | 1e-6 |
| 家族下界 | `family.lower_bound` | +0.005137 / +0.010225 | 0.065463−1.95996×0.030779；0.085714−1.64485×0.045895 | <1e-6 |
| 家族置信水平 | `family.confidence` | 0.975 / 0.95 | 1−0.025 / 1−0.05 | 0 |
| `ope_vs_audit` 0.2 档 6 行 | 差值与成本误差 | 文档表 | 由 contrast−audit 复算 | <1e-6 |
| 7 张表行数 | 32/96/48/64/2/32/48 | 同 | 同 | 0 |
| 7 张表唯一键 | 无重复 | 无重复 | 无重复 | 0 |
| `meta.json` 哈希/行数 | 7 表 | 一致 | 一致 | 0 |
| `coverage.json` F01 2 条 | sha256/bytes | 一致 | 一致 | 0 |

补充复算（文档未列，但影响结论）：
- `tau_hat` 唯一值 0.29380318488356094（`frame_rep0.csv`）；`tau_true` 均值 0.279134、sd 6.21399；`cost_true ∈ {0,10}`。
- greedy 选中集：按 `cost_hat` 升序取最便宜 23,437 人的掩码可复现 greedy 的全部发布数字（人数/预测成本/审计增量/实际支出）。
- 覆盖效应 +0.032608（102.3%）、单位人群效应 −0.000735（−2.3%）。
- E 200 次随机：mean 0.067745、sd 0.010664、14/200 超过 greedy 0.085638；F01 random 0.053765 位于第 10 百分位（20/200 更低）。

---

## ⑥ 未能复核的范围与原因

1. **无法从证据目录重建 OPE/审计**：`outputs/evidence/f01_ope/` 只有 freeze/meta，不含逐用户帧、掩码、真值；复算依赖仓库外 `out/e_evidence_formal/frame_rep0.csv`（未入库，且只有 9 列、无 treatment/net_profit，连 contrast/family 都无法从零重算）。这是 P0-3 的直接原因。
2. **无法验证"正式运行当时"的源码状态**：当前工作树（`3332c9d` + 未提交改动）的 `v3_models.py`/`v3_f02_formal.py` 已与运行记录不同（P1-5），只能回到 `1ac6c30` 验证。
3. **未运行 R>0 作业**：按约束未重跑 D03/E，E 的 200 次分布直接引用现有表；若该表本身有误，P0-2 的 4.5～4.8 倍结论需重算。
4. **未做统计功效/样本量分析**：单侧 α=0.05、n=60,000 下 0.018 量级效应的功效未计算；这会影响"随机期望口径下是否仍显著"的判断。
5. **未审计 `local_swap` 实现细节**：仅验证其与 greedy 在 8 档上人数/成本/审计/支出相等，未逐行检查交换逻辑；因 chosen=constant 导致两者退化等价，无法借此检验 local_swap 本身。
6. **未复核 E 的 200 次抽样实现**：只读取长表/汇总表，未检查 seed 机制与 `child_rng` 的一致性。
7. **未复核 `net_profit` 的构造**（30 天利润、退款保留、券成本只扣一次）：需 DGP 层逐用户流水；本次只核对 F01 的使用方式（`net_profit` 作结局、`coupon_cost` 独立列、审计用 `cost_true`），未回到 DGP/SQL 重算。

---

## ⑦ 评审方法

1. **规范对齐**：通读 `AGENTS.md`（§4 口径红线、§5 验证、§11 源码只读、§12 证据门禁/§12.5/§12.6），逐条对照 `docs/v3_phase_F01_ope.md` §7 清单。
2. **代码走查**：逐行阅读 `v3_f01.py`（冻结、策略、OPE、家族、审计）、`scripts/31_f01_ope.py`（执行顺序）、`tests/test_v3_f01.py`（10 项测试）、`v3_ope.py`（IPW/SNIPS/DR/IF/ESS/Holm）、`v3_models.py`（`_d03_rep_artifacts`）、`v3_split.py` 与 `configs/v3/{design,evaluation}.yaml`。
3. **独立复算**：用 `.venv/Scripts/python.exe`（`PYTHONUTF8=1`）读取 `frame_rep0.csv` 与 7 张表，重建 0.2 档 `policy_meta`（cheapest-first 装填）与 `audit`（`mean(mask*tau_true)`、`sum(mask*cost_true)`）；对 `contrast` 用 `value` 表两个水平值之差复核 diff、用 `diff/SE` 复核单侧 p；对 `family` 复核 Holm 步降与下界反演；对 `ope_vs_audit` 用 contrast 与 audit 表互算。原始观测帧（含 treatment/net_profit/e）未入库，故 IF 与 SE 未能从零重算，只能核对表内代数一致性。
4. **哈希核验**：对 freeze/meta/coverage 逐文件 `sha256`；对 `pipeline_source_hashes()` 在当前工作树与 `1ac6c30` 分别比对；对 7 列/9 列帧分别计算 as-is 与排序后哈希。
5. **边界检查**：构造 `tau_hat` 唯一值、cheapest-first 掩码复现、覆盖/单位效应分解、实际支出比、E 的 200 seed 分布分位点与支出回归等"文档未列但决定结论"的量。
6. **只读约束**：全程未写 `outputs/`/`out/`，未启动正式运行；临时文件仅写入系统临时目录并在评审后清理。

---

**结论重申**：数值可信、口径红线守住、复现路径在 `1ac6c30` 上成立；但 P0-1（定向机制误述）、P0-2（单次随机抽样外推）、P0-3（证据不可重建）必须在对外发布前修正或降级表述。建议裁决 **PASS WITH CONDITIONS**。
