# D03 正式 200 rep 独立复审：P0/P1 修正核验

> **合成数据 / 已知 DGP**｜scenario `L1_main`（randomized、`time_mode=static`）｜R = 200
> 复审对象：`docs/v3_phase_D03_formal.md`（20:58–21:02 修正稿 + 2026-10-28 04:56 补 §11.1，commit `c98ff35`）
> 原评审：`docs/reviews/v3_phase_D03_review.md`（2026-10-27 20:53，PASS WITH CONDITIONS，1 P0 + 6 P1）
> 复审时间：2026-10-28 05:13（北京时间）
> 复审人：独立复审代理，未参与 D03 实现、正式运行与原评审，也未参与 20:58–21:02 的修正。
> 范围：**只核验修正是否真实、完整、推导正确**；数字层由原评审逐项复现，本次不重复全量核验，
> 但对修正新增/改写的每个数字都从已入库 CSV 独立重算。
> 约束：本次复审只新增本文件；未写 `src/`、`sql/`、`configs/`、`outputs/`、`GOAL.md`、`TODO.md`；
> 未跑 pytest；未跑任何正式 R；复算全部经 stdin heredoc 走 `./.venv/Scripts/python.exe`（`PYTHONUTF8=1`），
> 只读 `outputs/tables/v3_phase_D03_formal_*.csv` 与 JSON 证据，未加载任何逐用户帧。
> **F02 正式 200 rep 正在本机运行**（shard0 日志 05:08:37 显示 rep 12 进行中）；本次复审全程未触碰绑定路径。

## 0. 结论

**PASS**。

原评审的 P0-1 与 P1-1～P1-6（报告 §11 编号）的修正**全部真实落地、数字全部独立复现、无残留旧口径**；
新增 §11.1 的事实锚点逐项核验为真（3 处分钟级小误差列 P2，不影响结论）。
**`GOAL.md` 的 D03 行可以从"未证实"改为"通过"**：原评审设定的两个前置条件——
①"P0 修正与 P1 改写完成"（本复审逐项核验成立）、②程序豁免经用户确认（§11.1 记录 2026-10-28 01:10 确认，
主负责与用户之间的对话不在仓库内，本复审按任务边界采信该记录、不重新裁决豁免本身）——均已满足。
§3 新发现的 4 项均为 P2（措辞/交叉引用精度），不构成阻塞，建议在下次维护窗口顺手改掉。

编号对照（避免混淆）：报告 §11 响应表把原评审的问题编为 P1-1～P1-6，其中主负责的
"P1-3（160/160 口径）"对应原评审 §1.5/§3-被否定-2（20:45 已改 320，本次复核正文无残留）；
主负责的 P1-4/P1-5/P1-6 分别对应原评审文件的 P1-3/P1-4/P1-5（+§3-被否定-6）。
下表按**报告 §11 的编号**逐项核对。

## 1. 逐项核对表

复算输入：`outputs/tables/v3_phase_D03_formal_per_rep.csv`（1 000 行）、
`…_policy_grid.csv`（72 000 行）、`…_compliance.csv`、`…_oracle.csv`、`…_policy_value.csv`、
`…_paired_diff.csv`、`outputs/evidence/d03_formal/*`。"复算值"全部为本次独立重算，非转抄原评审。

| 编号 | 原意见 | 修正落在正文哪一节 | 是否成立 | 复算值 vs 正文值 | 残留 |
|---|---|---|---|---|---|
| P0-1 | "运行期间未改 `src/`"为假；`run.err` 空被误当源码只读证据 | §1"执行路径"“stderr”两行、§10 第 7/8 条、§11.1 | **成立** | §1 现文："live `src/` 在 12:54–17:14 窗口内有 3 次提交（`df66a3c` 13:23、`06d4740` 13:58、`f2c6dab` 14:39）…均未进入快照"。`git show --stat` 复核：三提交触及文件与 §11.1 表**逐一相符**（含 `v3_policy_evidence.py` 新建于 `df66a3c`、`v3_ope.py` 新建于 `f2c6dab`）；4 个 `shard*_run.err` 已进证据包并在 `coverage.json.files` 登记（bytes=0，sha256=`e3b0c442…`=空文件哈希）；§1 明写"不构成源码只读证明" | grep `未改`/`未改动`：正文命中仅 2 处，均为 §11/§11.1 **引用原句并标注"为假"**，无残留 |
| P1-1 | "群体平均无偏"会被读成单 rep 无偏 | §0.2 改写；新增 §3.3 | **成立** | §3.3 表 20 个数**全部复现**：sd(bias) CF 0.0633/S 0.0617/T 0.0649/DR 0.0661/const 0.0622；mean\|bias\| 0.0500/0.0488/0.0521/0.0529/0.0484；>20% 占 34.5/33.5/38.5/40.0/37.5%；corr 0.047/0.052/0.031/0.039/0.009；sd(tau_true_mean)=0.0246；均值 SE=0.0044–0.0047；max\|均值偏差\|=0.0043（"±0.005 以内"成立） | grep `无偏`/`±0.005`：仅 §0.2、§3.3、§11 表，均已带"均值的 SE"限定，无残留 |
| P1-2 | 0.80/1.00 转正与 0.20 档 S 胜出被实际支出混杂 | §5.2 支出比表+每元价值；§0.3；§8 失效条件 | **成立** | 支出比 5×8 全表复现（greedy CF 1.260/1.129/1.054/1.021/1.002/0.796/0.597/0.478；business 1.004…0.999/0.824 等，逐格一致）。每元价值 0.20 档：S 1.3357→正文 1.336、business 1.3543→1.354、CF 1.3936→1.394；0.80 档：CF 0.8359→0.836、S 0.7288→0.729、DR 0.6923→0.692、T 0.6713→0.671、business 0.3566→0.357，**全部复现**（口径=逐 rep 比值再平均；见 §3-P2-4 说明）。§8 已加"高预算档符号依赖支出比"失效条件 | 无残留："转正"句均带支出限定；诊断 caveat 已恢复（§5.2 第一条） |
| P1-3 | "160/160"是 20 rep 诊断口径 | §0.5、§7 | **成立** | 从 `policy_grid` 复现：greedy `hat` 8 000/8 000 行=True、40/40 个 model×budget 格；chosen-only 1 600/1 600；除 all_coupon 外 8 策略 320/320 格、64 000 行全 True——与正文 §0.5/§7 完全一致 | grep `160`：正文命中仅 2 处（文首维护记录"160→320"、§11 响应表），均为历史记载，无口径残留 |
| P1-4 | §6 的 0.1143 是混合平均，与"选模后悔"不同量 | §6 拆 6.1/6.2/6.3；§0.4 | **成立** | 6.1：64 格平均后悔 0.1143/0.1066/0.1047/0.1037/0.1317、SE 均值 0.0009、rep 级 SE 0.00047/0.00042/0.00039/0.00037/0.00046 **全部复现**（从网格重算 regret 再按 rep 聚合）。6.2：greedy@0.20 后悔 0.0007/0.0027/0.0588/0.0462/0.1951、share_optimal 0.815/0.600/0/0/0 与 `oracle.csv` 一致（重算注意：oracle 的 share_optimal 用 ~1e-9 容差，严格相等为 0.790/0.590，正文引用表值无误）。6.3：8 档均值 −0.0114…−0.0189、SE 0.0014…0.0032、命中 52.5/52.0/48.5/53.0/52.5/52.0/52.0/52.0% **24+8 个数全部复现**。§0.4 已写明"不是同一量，不能比较成远小于" | grep `0.1143`：仅 §6.1（正确标注"混合平均"）与 §11 表；grep `远小于`：仅 2 处否定句，无残留 |
| P1-5 | 斜率 `b<1` 被误读为"τ̂ 过离散" | §3.2 新增"斜率不是过离散证据"段；§8；源码 docstring 与诊断文档 | **成立** | σ_hat 中位数 0.838/1.021/2.311/2.473 复现（constant=0）；由 `b·σ_hat/r` 反推 σ_true=6.14/6.12/6.19/6.15，正文"约 6.12–6.19"成立；r 中位数 0.0392–0.1029 与正文"0.039–0.103"一致。`src/causal_growth/estimate/v3_models.py`（现 :2233-2235）docstring 已改为"b = r·σ_true/σ_hat…单看 b 不能判定过离散"；`docs/v3_phase_D03_diagnostic.md`（:111 附近）同句已改 | grep `被放大`：正式文档 0 命中；`过离散` 4 处均为否定/响应表语境，无残留 |
| P1-6 | "个体排序能力弱"缺噪声基线与选择力证据 | §0.1、§0.2、§8 | **成立** | 命中率范围 48.5%–53.0%（§6.3 复算同值）；per-rep Spearman(selection_score, greedy 真值@0.20) 均值 **0.727**（n=200，scipy `spearmanr`）；chosen−5模型均值@0.20 = **+0.0572（SE 0.0031）**——三个新增指标全部复现。§8 已声明"噪声上限不可识别" | grep `排序能力弱`：仅 §11 响应表引用；正文结论已改为"逐用户相关低但头部选择有效，两者不矛盾"，无残留 |

P2 抽查（非阻塞项，仅核验响应表声称已做的那几项）：
- P2-1：`coverage.json` 已含 `snapshot_vs_live`、4 个 run.err、计算型 `checks`（`run_err_all_empty` 为逐分片字节数）、notes 写明"复算输入 = 证据包 + 已入库两张合并表"——**成立**。
- P2-3：all_coupon 支出倍数复现 0.20 档 4.12（正文"约 4.1 倍"）、0.04 档 20.6——**成立**；"避开负效应"因果句已删（grep 仅剩否定句与响应表）。
- P2-4：local_swap 与 greedy 差值均值 −1.3e-6 复现；"88.7% 的格完全相同"在 ~1e-9 容差下复现（严格逐位相等为 85.6%，`n_selected` 相等为 100%；正文"选择完全相同"取容差口径可接受）。
- P2-5：`report_meta.json` 新增 `code` 块，`scripts/26_d03_formal_tables.py` 与 `src/causal_growth/evaluation/v3_d03_formal.py` 的 sha256 **与当前文件实测一致**。
- P2-7：§4 表已含 `incremental_profit_rank`（0.20 档 CF 0.2711/const 0.0685 等，从 `policy_value.csv` 复现）与 `propensity_rank`（−0.0005，复现）。

## 2. §11.1 事实锚点核对

| 锚点 | §11.1 声称 | 实测 | 判定 |
|---|---|---|---|
| `coverage.json.snapshot_vs_live` | n_bound=83、n_live_different=3、n_live_missing=0，恰为 `v3_models.py`/`v3_policy.py`/`v3_policy_grid.py` | 字段逐值相同；`live_different` 三文件名与路径完全一致 | **真** |
| 4 个 `run.err` 登记 | 已在证据包 `files` 里登记 | `files` 14 条中 4 条 `kind=shard_run_err`（shard0–3），bytes=0，sha256=空文件哈希 `e3b0c442…`；目录实际 15 文件=14 导出件+coverage.json，与 §9 一致 | **真** |
| D03 快照绑定 | n_bound=83、`combined_sha256=be0d48f4…`、`git_commit=130a309`、`created_at=12:53:57` | `snapshot_binding.json`：`n_files=83`、combined/git_commit/created_at 逐值相符 | **真** |
| F02 绑定 | `n_source_files=48`（src 37+configs 9+sql 2）、`source_hashes_sha256=d8327ae0a190a5c2…`、`protocol_config_hash=e1aa4314b8d84b04…`、`git_commit=7870b9a`、`snapshot_dirs` 含 `scripts` 但 48 件里 scripts 0 件 | `out/f02_formal_snapshot/snapshot_binding.json` 逐值相符；`source_hashes` 按顶层目录计数 = {src:37, configs:9, sql:2}，无 scripts 条目 | **真** |
| `out/scratch/f02_shard.sh:17` | 调 `$SNAP/scripts/29_f02_formal.py` | 第 17 行确为 `"$REPO/.venv/Scripts/python.exe" "$SNAP/scripts/29_f02_formal.py"` | **真** |
| `out/scratch/f02_finalize.sh:45` | 调 `$REPO/scripts/30_merge_f02_formal.py` | 第 45 行确为 `"$PY" "$REPO/scripts/30_merge_f02_formal.py"`；且 `git log` 显示 30 号脚本最后一次改动是 10-27 21:28（`e004810`），早于 F02 起跑，与"30 号改动推迟到合并之后"一致 | **真** |
| 快照不含窗口新建文件 | `out/d03_formal_snapshot/src/causal_growth/{policy,evaluation}/` 下无 `v3_policy_evidence.py`/`v3_ope.py` | 实测两目录均无该二文件（policy 只有 v3_policy.py/v3_policy_grid.py 等；evaluation 只有 v3_aa.py 等）；live `src/` 中两文件存在 | **真** |
| 三提交触及文件清单 | `df66a3c`：v3_policy.py + v3_policy_evidence.py(新建)；`06d4740`：v3_policy.py + v3_policy_evidence.py + v3_policy_grid.py；`f2c6dab`：v3_models.py + v3_ope.py(新建) | `git show --stat` 逐一相符（新文件行数 1061/609，均为纯新增） | **真** |
| F02 窗口提交未触绑定路径 | `3457f85`/`1da7780` 未触及任何绑定路径 | 两提交 stat 只含 AGENTS/AGENT_HANDOFF/TODO/docs/outputs(evidence)，无 src/sql/configs——**真**；但"03:45 之后的两个提交"计数不准，见 §3-P2-1/P2-2 | **部分真** |
| 运行事实 | F02 "2026-10-28 03:45 起" | shard0 日志首行 `[F02 formal 03:39:18] rep 0 开始`（文件名 stamp 0339；快照 created_at 03:39:04）；shard1 日志 stamp 0350 | **偏差 ~6 分钟**，见 §3-P2-1 |

## 3. 新发现的问题

均为 P2（措辞/引用精度），不影响 §0 结论：

- **P2-1 §11.1"F02 正式 200 rep（03:45 起）"与日志不符**：shard0 实际 03:39:18 起跑（`out/logs/f02_formal_shard0_20261028_0339.log` 首行），shard1 约 03:50。建议改为"03:39 起（shard0）"。
- **P2-2 §11.1"03:45 之后的两个提交 `3457f85`/`1da7780`"计数不准**：截至今日 05:04，F02 起跑后已有 6 个提交（`c290b84` 04:02、`17a1011` 04:06、`111f19b` 04:09、`3457f85` 04:34、`1da7780` 04:54、`c98ff35` 05:04）。本次逐一 `git show --stat` 核验，**6 个均未触及 src/sql/configs 绑定路径**，结论不变，但"两个"应改为"截至 XX 的全部提交"。
- **P2-3 §11 响应表 P0-1 行"见决策日志 21:00 条"为失效引用**：`docs/v3_决策与反思日志.md` 无 21:00 条，书面豁免记录在 **21:02** 条（§11.1 引用正确）。按 AGENTS §12.4 应同步改掉这处旧值。
- **P2-4 两处口径未标注估计量**：①§6.1 列名"8 策略平均 share_optimal"（0.212/0.192/0.125）实为 **0.20 档**的 8 策略平均；64 格全平均是 0.261/0.240/0.175/0.185/0.125，两者不同，建议列名补"0.20 档"。②§5.2 每元价值（1.336/1.354 等）是"逐 rep 比值再平均"；若按"均值之比"则为 1.334/1.353（原评审 §1.4 用的后者）。两口径都成立、结论（符号反转）不变，但正文应写明用的是哪一个，避免与原评审数字表面不一致。
- **观察（不计问题）**：`GOAL.md:22` D03 行仍写"程序层豁免待用户确认"，而 §11.1 记录用户已于 01:10 确认——GOAL 该行整体本就待本次复审后由主负责更新，届时一并改掉即可。

## 4. 未能验证的内容

1. **用户 2026-10-28 01:10 的豁免确认**：属主负责与用户的对话，仓库内无凭据（§11.1 引用的"这些我都默认批准通过"无法从 git/文件核验）。按任务边界采信，不重新裁决。
2. **"21:11 全量 1 248 项测试 exit=0"**：决策日志 21:05 条内有该记载（21:04:16–21:11:28、432 秒），但本次被明令禁止跑 pytest，且 `out/logs/` 中未找到对应全量测试日志文件，无法独立复现；仅确认了日志文本存在。
3. **"重跑 `scripts/26_d03_formal_tables.py` 后七张表逐字节未变"**：重跑会写 `outputs/tables/`，越权；改为替代核验——`report_meta.json.code` 的两个 sha256 与当前文件实测一致，且本报告 §1 中全部表值直接从已入库 CSV 重算相符。
4. **原评审的数字层结论**（校准 5×7、40 个配对差全表、证据哈希 83/83 等）：按任务分工不重复全量复算；本次抽核了配对差 0.20/0.80/1.00 三档 15 格（与正文 §5.1/§5.2 全符）与 §4 策略值 0.20 档 7 策略×5 模型（全符）。
5. **F02 分片进程的 `PYTHONPATH` 实际值**：只能从 `f02_shard.sh` 的 `$SNAP/scripts/29_f02_formal.py` 调用路径与快照绑定间接推断，未读取运行中进程的环境。
6. **快照 `selection.py` 的 `eligible=(v>0)&(c>0)` 停止规则**（P1-2 的机理解释）：本次未重读快照源码，沿用原评审已核验的结论。

## 5. 复审留痕

复算命令（全部只读、stdin heredoc，工作目录为仓库根，未写任何仓库文件）：

```bash
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe - <<'PY'   # 共 8 段：
# ①per_rep：§3.3 离散表、SE、sd(tau_true_mean)、σ_hat/σ_true/r 反推
# ②policy_grid：支出比 5×8、每元价值（两种口径）、all_coupon 倍数、local_swap 一致性（含容差扫描）
# ③policy_grid：hat 合规计数 8000/40/1600/320/64000
# ④policy_value/oracle：§4 全值、§6.1 64 格平均+rep 级 SE、§6.2、share_optimal 口径定位
# ⑤policy_grid+per_rep：§6.3 选模后悔 8 档、Spearman 0.727、chosen−mean +0.0572
# ⑥paired_diff：0.20/0.80/1.00 抽查
# ⑦JSON：coverage.json/snapshot_binding.json(D03+F02)/report_meta.code sha256 实测
# ⑧grep：未改/160/0.1143/无偏/±0.005/远小于/被放大/避开负效应/排序能力弱/过离散
PY
git show --stat df66a3c 06d4740 f2c6dab 3457f85 1da7780 c290b84 17a1011 111f19b c98ff35
git log -- scripts/30_merge_f02_formal.py
```

本次复审只新增本文件；`git status --short` 除本文件外仅既有 `.workbuddy/` 未跟踪目录。
