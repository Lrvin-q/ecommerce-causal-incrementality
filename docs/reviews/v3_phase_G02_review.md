# G02 独立评审结论
**结论：PASS WITH CONDITIONS** —— 送审包 §3 的 8 项数字逐项复现（数值无一算错），但"断言范围处处一致"这一条不成立：报告表 3-1 自带一个跨层"合计 143/200"，直接违反送审包 §4.1；另有 3 处记录性错误（长稿把四格写成共用同一验证队列、92 条归因、运行注册表快照哈希）。改完 P1 与指定的 P2 后可判 PASS。

> 被评对象：G02 再训练 bootstrap 200 次（4 个 core 格 × 50 b）正式运行、40 号证据导出、33 号顶层登记，批准号 `G02-FORMAL-20261029`。
> 评审时间：**2026-10-29 23:08（北京时间，`date -u` 读数 + 8 h）**。身份：独立评审子代理，此前未参与 G02 任何产出。
> 纪律：未修改任何现有文件（本文件是唯一写入）；未触碰 `src/`、`sql/`、`configs/`；未调用 34/39 号脚本的运行模式，未重跑任何正式实验；
> 只读 + 单进程 pandas 复算。40 号 `--check`、33 号 `--dry-run`、42 号门禁属只读校验，按送审包 §6 执行。
> 复算基准：`outputs/evidence/g02_formal/per_cell/*__repetitions.csv`（4 份 × 50 行），**不采信**报告里抄好的汇总值；
> `outputs/tables/v3_phase_G02_retrain_bootstrap.csv` 只作对照，不作输入。

---

## §1 复算表（送审包 §3 的 8 项）

| # | 口径 | 报告值 | 复算值 | 判定 |
|---|---|---|---|---|
| 1 | 各层 50 b 的 `policy_value` 均值（元/人） | 2.3556 / 2.8573 / 2.8514 / 2.9839 | 2.355626 / 2.857321 / 2.851376 / 2.983932 | **一致**（差 ≤ 3.2e-5，纯四位舍入） |
| 2 | 两条单侧 Holm 主张同时通过的比例 | 0.04 / 0.98 / 0.94 / 0.90 | 2/50、49/50、47/50、45/50 = 0.04 / 0.98 / 0.94 / 0.90 | **一致**；且 200/200 行满足 `decision_all_pass == (decision_lower_min > 0)` |
| 3 | 退款率护栏通过率（非劣界 0.005，单侧 0.05） | 1.00（200/200） | 每格 50/50，合计 200/200；`guardrail_upper` 最大 0.002131 / 0.002435 / 0.002350 / 0.002085，均 < 0.005 | **一致**；`guardrail_pass == (guardrail_upper < 0.005)` 在 200 行全部成立 |
| 4 | 行数 4 格 × 50 = 200 | 200 | 逐格 50 行，b 连续 0–49，合计 200 行（`wc -l` 为 204，含 4 行表头） | **一致** |
| 5 | `merge_exit=0`（17:17:51） | 0 / 17:17:51 | 现场 `out/g02_logs/post.status` 两行原文：`merge_exit=0`、`OK: G02 merge 完成 2026-10-29T17:17:51+08:00`；**但该文件未导出**，证据区 `logs/post.log` 末行只有"merge 完成"，无退出码 | **数值一致，证据内不可复算**（P2-6） |
| 6 | 40 号导出 18 文件 / 33 号登记 92 条 | 18 / 92 | 证据区实有 18 个文件 + `coverage.json`，18/18 的 sha256 与字节数吻合；**92 是顶层累计条数**，G02 只新增 1 条（91→92，`registry_repairs` 第 17 条），33 号 `--dry-run` 原文"候选身份类文件 1 个：新增 0，已登记 1""顶层全表复算一致：92 条" | **18 一致；92 归因错误**（P2-2） |
| 7 | 长稿 C12–C19 显示值与源表一致（42 号 `--draft`） | EXIT=0 | 42 号无参 EXIT=0（Tier1 274 / Tier2 0 条全过）；`C12=2.3556`、`C13=2.8573`、`C14=2.8514`、`C15=2.9839`、`C16=0.04`、`C17=0.98`、`C18=0.94`、`C19=0.90`，源列 `policy_value_mean` / `decision_pass_rate`，`filter` 均为单行命中，与 `outputs/tables/v3_phase_G02_retrain_bootstrap.csv` 四位舍入一致；带 `--draft out/scratch/draft_concat.md` 亦 EXIT=0 | **一致** |
| 8 | 四层同族、不得相加（送审包 §4.1） | 报告声称遵守 | 报告正文 :89 与长稿 :1001–1002、:1007 都写对了，**但报告表 3-1 第 :70 行给出"合计 143/200"**，正是送审包禁止的跨层总通过率 | **不一致**（P1-1） |

**复算命令**（全部只读；逐格重算脚本见本节末）：

```bash
wc -l outputs/evidence/g02_formal/per_cell/*.csv
PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/40_export_g02_evidence.py --check
PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/42_claim_number_gate.py --draft out/scratch/draft_concat.md
PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g02_formal --dry-run
cat out/g02_logs/post.status
```

逐格复算（评审实际执行的方式，按格分组求均值/比例，并与 `decision_lower_min`、`guardrail_upper` 的判据做等价性核验）：

```bash
PYTHONUTF8=1 ./.venv/Scripts/python.exe - <<'PY'
import pandas as pd, glob, os
for f in sorted(glob.glob("outputs/evidence/g02_formal/per_cell/*__repetitions.csv")):
    d = pd.read_csv(f); c = os.path.basename(f).replace("__repetitions.csv", "")
    print(c, len(d), round(d.policy_value.mean(), 6),
          int(d.decision_all_pass.sum()), round(d.decision_all_pass.mean(), 2),
          int(d.guardrail_pass.sum()), round(d.guardrail_pass.mean(), 2),
          round(d.decision_lower_min.min(), 6), round(d.guardrail_upper.max(), 6),
          bool(((d.decision_lower_min > 0) == d.decision_all_pass).all()),
          bool(((d.guardrail_upper < 0.005) == d.guardrail_pass).all()))
PY
```

**表 3-1 其余列的附带核对**（不属于 8 项，但同表同源，一并复算）：
sd 0.049674 / 0.041680 / 0.059796 / 0.066165，MC SE 0.007025 / 0.005894 / 0.008456 / 0.009357，
CI 由 `mean ± 1.96·SE` 复现（如 L3 为 [2.965592, 3.002271]，报告 [2.9656, 3.0023]），
CPU·h 为三列 CPU 之和除以 3 600（6.0318 / 6.4951 / 6.3588 / 6.4811，合计 25.3668 → 报告 25.37），全部一致。
选模频率也与逐 b 的 `chosen_model` 逐格吻合（L0：CF 21 / S 15 / T 9 / const 5 / DR 0；L1：30/14/3/2/1；L2：28/16/3/3/0；L3：21/16/2/5/6）。
L0 通过的 2 个 b 是 b=16、b=26，模型均为 `causal_forest`；全部 200 个 b 的 `policy_value` 均为正（最小 2.200350）。

---

## §2 边界措辞核对（送审包 §4，4 条）

结论速览：第 2、4 条全篇干净；第 3 条长稿写足、报告缺一句；**第 1 条被报告表 3-1 自己违反（P1），长稿另有一句事实性反写（P2）**。

### 2.1 边界 1：四层是一个 DGP 家族的层水平偏移，不是四份独立证据，不给跨层总通过率

**写对的**：

- `docs/v3_phase_G02_formal.md:89`：「**不同格之间不得按"独立证据"平均**（AGENTS §12.5）。guardrail 200/200 只说明退款率护栏未报警，不说明策略最优。」
- `paper/v3/body/03_results.md:1001-1002`：「四层同属一个 DGP 家族的层水平偏移，不能当作四份独立证据平均。」
- `paper/v3/body/03_results.md:1007`：「本节的报告方式因此是先给逐层数值、再明确它是同一族的展开，**不给出跨层合并的"总通过率"**。」
- `paper/v3/body/03_results.md:1048-1049`：「把它们当作同一实验的四份独立证据，会同时忽略层水平偏移与选模差异；正确读法仍是"一族 DGP 的四个侧面"。」

**写错的**：

- **P1-1**　`docs/v3_phase_G02_formal.md:70`：

  `| **合计** | **200** | — | — | — | — | **143/200** | **200/200** | **25.37** |`

  这是把四层在 b 上直接相加得到的跨层总通过率（143 = 2+49+47+45），与本节引用的三处正文、以及长稿 :1007 的明文承诺直接冲突。b=200、CPU·h=25.37 作为工作量汇总无害，**决策通过率与护栏通过率两格必须删掉或改"—"**。
- **P2-1**　`paper/v3/body/03_results.md:1100`：「这里是 G02 四格各自的 50 次重训，层设定与验证队列都不同；**四格共用同一份验证队列**，……」
  前半句与后半句自相矛盾；后半句与证据相反：四格的 `validation_frame_hash` 是 4 个不同值（每格内部恒定，格间不同，源于 `scenarios.yaml` 各 core 格 `pairing_group` 不同），只有 `validation_arm_hash` 是四格共享的 1 个值。这句是"四格属于同一实验"的措辞源头，须改写。
- **P3-6**　`paper/v3/body/04_conclusion.md:56-57`：「两类重采样都保持方向……四层的策略价值保持为正（2.3556 [C12] 至 2.9839 [C15]）」
  数值全部为真是事实，但"保持方向"以四层作四路复现来支撑一个稳健性结论，读起来接近把四层计数；建议改成"四层的点估计均为正，但它们是同一 DGP 家族的四个侧面，不构成四次独立复现"。

### 2.2 边界 2：L0 的低通过率不是"策略价值为负"

**通过**。没有任何一处把 L0 读成价值为负：

- 报告 :79–85 专段：「**L0 的低通过率不是"策略价值低"，而是"决策口径是两条比较的合取"**……策略价值本身（2.3556，MC SE 0.0070）与另三格同量级；两者不矛盾」。
- 长稿 :999–1001：「L0 的低通过率与策略价值无关……L0 卡住的是后者，方向与 3.2 一致。」
- 长稿 :1037 与结论 :58-59 同向；`04_conclusion.md` 中不存在"价值为负/负值"字样（grep 无命中）；全部 200 个 b 的价值均为正（最小 2.200350），与文字不冲突。
- 唯一瑕疵是归因精度（**P2-5**）：长稿 :1037 把 **-0.2156** 明确归给"定向 vs 同预算随机"这一条，但证据里 `decision_lower_min` 是两条主张校正下界的**较小值**，逐 b 的两条下界未留存（`scripts/39_g_retrain_bootstrap_run.py:250` 以 `target_dir=None` 调用验证臂），该归属在证据内不可重建。结论方向（"卡在后一条"）可由 F02 与固定 bootstrap 旁证，但报告应注明或改述为"两条主张中较小的校正下界"。

### 2.3 边界 3：通过率是跨 b 的描述性统计，不是验收阈值

**长稿通过，报告缺句**：

- `paper/v3/body/03_results.md:181`：「通过率是跨 rep 的描述性统计；正式判定单位是每个 rep 内的单侧 Holm 检验。」
- `paper/v3/body/03_results.md:232` 与 `:1467` 重申「不是验收阈值」。
- **P2-4**　报告里没有等价句：`grep -n "阈值" docs/v3_phase_G02_formal.md` 零命中；报告 :87–90「解读纪律」只写了不平均、护栏 200/200 不等于策略最优。全文也没有把通过率当阈值用的句子（因此不升 P1），但送审包要求"处处一致"，这句必须在报告 §3 落地。
- **P3-7**　`paper/v3/body/04_conclusion.md:227` 失效条件表把「重训 bootstrap 的逐层通过率」列为"结论翻面"的观测量，建议加"仅作描述性线索、不作判据"的限定。

### 2.4 边界 4：不声称"定向有效"，不声称可部署

**通过，无越界句**：

- 报告 :135–138：「不表示"定向策略有效"、不表示可上线、不表示 Tier2 已跑满 65 格。」
- 长稿 :1467：「两者都不回答'策略可以部署'。」
- 结论章 :24 只出现"不是'上线后不会出现新退款渠道'的保证"这类否定式，:293 反而在拆解"策略有效"这句话；未发现任何肯定式"定向有效/可部署"表述。

---

## §3 限制声明核对（送审包 §5，3 条）

| # | 限制 | 报告是否写明 | 位置与判定 |
|---|---|---|---|
| 1 | 预算只覆盖主档 0.2 元/人 | **是** | `docs/v3_phase_G02_formal.md:18`（固定策略 bootstrap 仅 0.2 元/人）与 `:129`「**策略与预算**：只评 `greedy_incremental_profit_per_cost` 在 0.2 元/人档；换策略或预算档不保证」。✓ |
| 2 | 重训按总数 200（每格 50）执行；冻结配置算出的 800 由 overlay 与 runner 覆盖；`configs/v3/*.yaml` 未改（hash `00723dc2…`） | **只写了一半** | `:13` 写了 200 与"任务书口径"，`:23` 写了 overlay 1 847 B / sha256 `c58d5a90…` / total 200 / per_cell 50；**但全文没有出现"800"与 `00723dc2`**（grep 零命中），"冻结配置的 800 被覆盖、configs 未改"这一层缺失。见 **P2-3**。 |
| 3 | 每格 50 b，精度有限；只给点值与离散程度，不做逐格覆盖率断言 | **基本写明** | `:130`「**再训练 b 的样本量**：每格 50 b，MC SE 见 §3；不能据此做逐格显著性判定」；覆盖率句在 `:112-113`「本轮没有注册覆盖率统计量」（写在 §4 G03 语境）。建议在 §3 再补一句"不做逐格覆盖率断言"，属 **P3**。 |

---

## §4 证据可复算性

**能重建的（数值层）**：把 `outputs/evidence/g02_formal/per_cell/*__repetitions.csv` 当唯一输入，§1 的 1–4、7、8 项全部可逐位重建；逐格 24 列齐全（`b`、`history_rep_id`、`validation_rep`、`chosen_model`、`policy_value`、`decision_all_pass`、`decision_lower_min`、`guardrail_pass`、`guardrail_upper`、三个指纹、`freeze_hash`、`status`、`config_hash`、`protocol_config_hash`、`overlay_sha256`、`retraining_bootstrap_total`、三列 CPU），b=0–49 连续，`history_rep_id == 1_000_000 + b` 全部成立，`validation_rep` 恒为 0。

**哈希链**：

- 18 个导出文件的 sha256 与字节数与 `outputs/evidence/g02_formal/coverage.json` **18/18 吻合**；逐格 50 行、合并 200 行、`provisional=false`、`merged_at 17:17:50`。
- `merged/v3_phase_G02_retrain_bootstrap.csv`（780 B，sha256 `837db0c8…`）与 `outputs/tables/v3_phase_G02_retrain_bootstrap.csv` **字节相同**；`recomputed_bootstrap.csv` 与之数值全等（10 个数值列 max|Δ| = 0），仅浮点格式/行尾不同（非字节相等，引用时需说明）。
- `binding/snapshot_binding.json`：49 个源文件哈希齐全，按 `sha256(json.dumps(hashes, sort_keys=True, separators=(',',':')))` 复算得到 `abaa338a0c7705ae…`，与报告、`docs/v3_phase_G_run_registry.md:70-71` 一致；`v3_g_matrix.py` = `6ec009b6…`；与当前工作树逐文件比对，49 个中仅 `src/causal_growth/policy/v3_policy.py` 已变（快照 `ba058f9b…` → 当前 `382503c2…`，G03 Stage A 18:05 修复所致），9 个 `configs/` 文件全部逐字节相同。
- overlay 不在 49 文件清单内（报告 :23 已披露），但 `out/g02_snapshot/configs/budget/g02_bootstrap_overlay.yaml` 字节副本存在，1 847 B、sha256 `c58d5a90…`，与报告一致。
- 冻结帧：每格内 `validation_frame_hash` / `validation_arm_hash` 恒定；四格之间 **4 个不同 frame 指纹、1 个共享 arm 指纹**；每格 `validation_observed_hash` 50 个不同值（设计使然，含 `issued_action`）。
- 顶层 `outputs/evidence/coverage.json` 92 条记录、18 条 `registry_repairs`，G02 只有 1 条顶层记录（`snapshot_binding.json`）。

**不能重建的（记录层，均已列入 §5）**：`merge_exit=0` 的退出码（`post.status` 未导出）；逐 b 的两条子主张下界与各自通过状态（39 号未留 `decision.csv`）；`overlay_sha256` 列 200 行全空；报告 §2 引用的 `out/pytest_g02fix_20261029_1029.log` 未导出。

**总判**：数值复算自足，哈希自洽；记录链缺 3 处旁证（退出码、子主张、overlay 列），不阻断数字结论，但阻断"仅凭证据区独立重放全过程"。

---

## §5 遗留问题清单

### P1（阻塞：断言范围）

**P1-1　报告表 3-1 给出跨层"合计通过率"**
`docs/v3_phase_G02_formal.md:70`：`| **合计** | **200** | — | — | — | — | **143/200** | **200/200** | **25.37** |`
违反送审包 §4.1 与报告自身 :89、长稿 :1007。143 = 2+49+47+45，是把四层当同一实验相加的结果。
复现：
```bash
sed -n '70p' docs/v3_phase_G02_formal.md
sed -n '89p' docs/v3_phase_G02_formal.md
sed -n '1007p' paper/v3/body/03_results.md
```
改法：合计行的 decision / guardrail 两格改 `—`（或删整行），仅保留 b=200 与 CPU·h=25.37。

### P2（须在关闭前改；记录准确类）

**P2-1　长稿写"四格共用同一份验证队列"（与证据相反、与同句前半自相矛盾）**
`paper/v3/body/03_results.md:1100`。
复现：
```bash
PYTHONUTF8=1 ./.venv/Scripts/python.exe -c "import pandas as pd,glob;[print(f.split('/')[-1][:12], pd.read_csv(f).validation_frame_hash.nunique(), pd.read_csv(f).validation_arm_hash.nunique()) for f in sorted(glob.glob('outputs/evidence/g02_formal/per_cell/*__repetitions.csv'))]"
```
预期：4 个格各 1 个 frame 值，但四格之间 4 个不同值；arm 只有 1 个共享值。改法：改为"四格共用同一套随机化臂与概率（arm 指纹相同），但各自重抽了不同的验证用户协变量（frame 指纹不同）"。

**P2-2　"33 号登记 92 条"归因错误**
`docs/v3_phase_G02_formal.md:49`、`GOAL.md` G02 行、`docs/v3_G02_送审包.md:33`（§3 第 6 项）。92 是顶层累计条数，G02 新增 1 条（91→92）。
复现：
```bash
PYTHONUTF8=1 ./.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g02_formal --dry-run
```
输出"候选身份类文件 1 个：新增 0，已登记 1""顶层全表复算一致：92 条"。改法：写"33 号登记 G02 的 1 条身份记录（顶层累计 92 条）"。

**P2-3　限制 2 未写全：800 覆盖与 configs 未改**
`docs/v3_phase_G02_formal.md` 全文无"800"与 `00723dc2`。
复现：`grep -n "800\|00723dc2" docs/v3_phase_G02_formal.md`（无输出）。
改法：在 §1 或 §6 补一句"冻结 `configs/v3/scenarios.yaml:266` 的 `retraining_bootstrap_jobs: 800` 由 overlay（total 200 / per_cell 50）与 runner 参数覆盖；`configs/v3/*.yaml` 未改动，hash 仍 `00723dc2…`"。

**P2-4　报告缺"通过率不是验收阈值"的显式句**
复现：`grep -n "阈值" docs/v3_phase_G02_formal.md`（无输出）。
改法：§3「解读纪律」补一句，与长稿 :181、:232、:1467 对齐。

**P2-5　L0 的 -0.2156 归属不可从证据重建**
长稿 :1037 把它明确归给"定向 vs 同预算随机"；证据只存两条下界的较小值，逐 b 子主张未留（`scripts/39_g_retrain_bootstrap_run.py:250` `target_dir=None`）。
复现：
```bash
sed -n '245,268p' scripts/39_g_retrain_bootstrap_run.py
ls outputs/evidence/g02_formal/per_cell/
```
改法：报告与长稿注明该归属来自运行期 decision 表（未导出），或把措辞改为"两条主张中较小的校正下界为 -0.2156"。

**P2-6　`merge_exit=0` 只在现场文件，证据区无退出码**
`out/g02_logs/post.status` 有 `merge_exit=0`，但 `outputs/evidence/g02_formal/` 没有它；`logs/post.log` 末行只有"merge 完成"。
复现：
```bash
cat out/g02_logs/post.status
tail -3 outputs/evidence/g02_formal/logs/post.log
ls outputs/evidence/g02_formal
```
改法：40 号把 `post.status` 纳入导出（或报告注明其现场路径及"不可迁移"）。

**P2-7　运行注册表 G02 行的快照哈希是失败现场的**
`docs/v3_phase_G_run_registry.md:14` 写 `out/g02_snapshot`，49 文件 `f39ec0a3…`；`binding/snapshot_binding.json` 与报告均为 `abaa338a…`，同文件 :70-71 也正确地把 `f39ec0a3…` 标为 10:09 首轮失败现场。
复现：`grep -n "f39ec0a3\|abaa338a" docs/v3_phase_G_run_registry.md`
改法：:14 改 `abaa338a…`。`TODO.md:568` 的同一哈希是历史时点记录，可保留但宜加"首轮失败快照"字样。

### P3（记录后可随 G04 收尾，不阻塞关闭）

**P3-1　报告 :49 把 18:04 的导出/登记与 17:17:51 的合并写进同一行**
coverage 的 `exported_at` 为 18:04:39，报告本章 §2 其它行也按"合并 → 导出"分时记录。复现：`grep -n exported_at outputs/evidence/g02_formal/coverage.json`。改法：拆成两行。

**P3-2　长稿 :1004-1006 的条件句前提对数据不成立且未点破**
原文「如果……层间离散程度远小于单层的蒙特卡洛标准误，那就说明……」。实际层间极差 2.9839−2.3556 = 0.6283，是 MC SE（0.0059–0.0094）的约 70–100 倍，前提为假。作为反事实条件句尚可，但未说明"本数据不满足"，易被读成已验证。复现：§1 的逐格脚本。改法：补一句"本数据层间差远大于 MC SE，故正确读法仍是四个侧面而非四次重复"。

**P3-3　长稿 :1046-1047 的选模构成漏项**
「L0 是因果森林 21/50、S-learner 15/50、常数 5/50、DR 0/50；L1 是 30/14/1」——L0 漏 T-learner 9、L1 漏 T 3 与 DR 2，分项和不等于 50。复现：
```bash
PYTHONUTF8=1 ./.venv/Scripts/python.exe -c "import pandas as pd,glob;[print(f, pd.read_csv(f).chosen_model.value_counts().to_dict()) for f in sorted(glob.glob('outputs/evidence/g02_formal/per_cell/*__repetitions.csv'))]"
```

**P3-4　两处引用物未导出**
报告 :41 引用的 `out/pytest_g02fix_20261029_1029.log` 不在证据区；`recomputed_bootstrap.csv` 与 `outputs/tables` 数值全等但非字节全等（浮点格式/行尾），引用时需注明。复现：`ls outputs/evidence/g02_formal`、`cmp outputs/evidence/g02_formal/recomputed_bootstrap.csv outputs/tables/v3_phase_G02_retrain_bootstrap.csv`。

**P3-5　现场源码已不等于跑数源码，重跑只能用快照**
`src/causal_growth/policy/v3_policy.py` 快照 `ba058f9b…`、当前 `382503c2…`（G03 Stage A 成本乘子修复）。G02 的数字不受影响，但任何 G02 重跑必须以 `out/g02_snapshot` 为准，不能用 HEAD。复现：`sha256sum out/g02_snapshot/src/causal_growth/policy/v3_policy.py src/causal_growth/policy/v3_policy.py`。

**P3-6　结论章"四层保持为正"的读法**（见 §2.1）与 **P3-7　失效条件表把逐层通过率列为观测量**（见 §2.3）同属措辞级。

**关闭条件（本评审的判定口径）**：必须关闭 P1-1、P2-1、P2-2、P2-3、P2-4、P2-7 后可判 PASS；P2-5、P2-6 需在报告中如实注明证据边界（可随同一次修订完成）；P3-1…P3-7 不阻塞关闭。按送审包 §7，"重跑一次看看"不作为条件——本评审也不以此要求。

---

评审者：独立评审子代理（未参与 G02 产出）
时间：2026-10-29 23:08（北京时间）

---

## §6 修订记录（主负责，2026-10-29 23:18，北京时间）

> 本节由主负责填写，§1–§5 的评审原文一字未改。逐条对应 §5 的关闭条件。

| 条目 | 处理 | 落点 | 复核 |
|---|---|---|---|
| P1-1 跨层合计通过率 | 合计行只保留 b 与 CPU·h；decision / guardrail 两格改"不设合计"，表下补一句禁止相加的依据 | `docs/v3_phase_G02_formal.md` §3 表 3-1 与其下说明 | `grep -rn "143/200" docs/ paper/` 只在评审文件自身命中 |
| P2-1 四格共用验证队列 | 改为"每格内部跨 b 固定，四格之间是四份不同的验证用户协变量（frame 四值），只有 arm 与概率共享" | `paper/v3/body/03_results.md` 3.7 三条边界 | 42 号 `--draft` EXIT=0 |
| P2-2 "92 条"归因 | 报告 / GOAL / 送审包统一为"登记 G02 的 1 条身份记录（顶层累计 92 条）" | 报告 §2 事故表、`GOAL.md` G02 行、`docs/v3_G02_送审包.md:33` | 33 号 `--dry-run` 原文 |
| P2-3 800 覆盖 / configs 未改 | §1 增段：冻结 `retraining_bootstrap_jobs: 800` 由 overlay 与 runner 覆盖，`configs/v3/*.yaml` 未改，hash 仍 `00723dc2…` | 报告 §1 | `grep -n "800\|00723dc2"` 命中 |
| P2-4 通过率非阈值 | 解读纪律补"通过率是跨 b 的描述性统计，不是验收阈值" | 报告 §3 | `grep -n "不是验收阈值"` 命中 |
| P2-5 `-0.2156` 归属 | 长稿与报告都改为"两条主张中较小的校正下界"，并注明逐 b 子主张下界未随证据导出 | `03_results.md` 3.7.1、报告 §3 | 未新增数字，42 号过 |
| P2-6 `merge_exit` 未导出 | 报告 §5 增"证据边界"：`post.status` 只在现场、`post.log` 无退出码 | 报告 §5 | `cat out/g02_logs/post.status` |
| P2-7 注册表快照哈希 | `:14` 改 `abaa338a…`，`f39ec0a3…` 标注为首轮失败现场；`TODO.md` 历史行同标注 | `docs/v3_phase_G_run_registry.md:14`、`TODO.md:568` | `grep -rn "f39ec0a3"` 只剩标注处 |

§5 的 P3 里可低成本关闭的，一并处理：P3-1 把 17:17:51 合并与 18:04:39 导出拆成两行；
P3-2 补"本数据与条件句前提相反"；P3-3 补齐 L0 / L1 的 T-learner 与 DR 分项；
P3-4 在报告 §5 注明 `recomputed_bootstrap.csv` 数值全等但非字节相等、`pytest_g02fix` 日志未导出；
P3-6 / P3-7 结论章补"不构成四次独立复现"与"描述性线索，不作判据"。
P3-5 属提醒（重跑须用 `out/g02_snapshot`），已由报告 §1 快照行覆盖，不另改。

改后重建与门禁（2026-10-29 23:18，`bash scripts/52_paper_gates.sh --build`）：
50 页、五门禁全绿、缺字 0、未定义 0、越界 9（最大 0.12009pt）、欠满 0；
长稿结果章 42 765 / 正文 77 241 字 = 55.37%，结果页 32/46。
H03 审计已同步（`docs/v3_H03_编译审计.md` §1、§2.1、§3.2）。

**状态**：请复评确认 P1-1、P2-1…P2-4、P2-7 是否关闭；
P2-5 / P2-6 已按"如实注明证据边界"处理，请确认注记是否足够。

**2026-10-29 23:30 复评结论**：窄口径复核返回 **PASS**（9 项全 CLOSED、无 P0–P3 新问题），复核文件 `docs/reviews/v3_phase_G02_recheck.md`；建议的改判已执行，G02 状态见 `GOAL.md` 与 `docs/v3_G04_收尾审计.md`。
