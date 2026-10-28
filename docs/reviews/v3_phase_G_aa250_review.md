# G 阶段 AA250 修订门禁评审（独立评审）

> **合成数据 / 已知 DGP。**

- **评审时间**：2026-10-28 19:09（北京时间，Asia/Shanghai）
- **评审人**：独立评审代理（只读评审；本次未运行任何 R>0 作业，未修改 configs/、src/、tests/、GOAL.md、TODO.md、outputs/ 下任何既有文件）
- **评审对象**：`df12f57`（12 行 AA 对齐落盘）与 `1b64b3b`（预评审 P1/P2 修复、reason sha 重绑）；工作树 HEAD `1b64b3b`，`git status` 除未跟踪的 `.workbuddy/` 外干净
- **评审依据**：`AGENTS.md` §3/§4/§5/§7/§11/§12；`GOAL.md` G01 行；`docs/v3_phase_G_protocol_change_aa250.md`；`outputs/v3/protocol_aa250/*`
- **总体结论**：**PASS WITH CONDITIONS**（0 项 P0 / 1 项 P1 / 3 项 P2）

---

## 0. 评审方法

逐条实读 + 本机复算，不采信文档自述：

1. `git diff 193ff48..df12f57`（及 `..HEAD`）核对改动范围与行数；`git diff 5020c56..HEAD` 核对 Phase A 是否逐字节保留。
2. 用 `.venv/Scripts/python.exe`（`PYTHONUTF8=1`）调用 `causal_growth.v3_config.load_v3_protocol()`，实读 `config_hash`、7 份 `source_sha256`、`planned_counts`、AA 四格 `R`/`complete_aa`。
3. 对 `outputs/v3/protocol_aa250/` 的 `experiment_matrix.csv` 与 `protocol_manifest.json` **在内存中重算并逐格比对**（不写盘）：`protocol_rows()` 93 行 0 差、`planned_counts()` 0 drift、manifest 五个关键字段全部 MATCH。
4. 逐文件 `sha256`/`bytes` 复算：12 个关键产物、登记表 54 条记录、4 份新测试凭据。
5. 解析两轮全量测试日志的进度条字符数（不是数句点，避免被 traceback 里的 `.py` 污染）。
6. 只额外跑了两条守卫测试（R=0）：`tests/test_v3_aa.py::test_registered_aa_cells_...` 与 `tests/test_v3_power.py::test_config_canonical_hash_is_still_frozen`，结果 `..`（2 passed）。

---

## 1. 逐项结论

### 1.1 授权链 — PASS

| 核验点 | 实读结果 |
|---|---|
| GOAL.md 是否有 2026-10-25 的 250/层授权 | **有**。`GOAL.md:27`（G01 行）：「**2026-10-25 13:45 修订** … 按用户 2026-10-25"放宽要求、可砍批数"的授权，改为每层 250（合计 1000，约 33 CPU·h）」 |
| 理由文档 §1 是否与之一致 | **一致**。§1 首行同为 `2026-10-25 13:45`、出处写「`GOAL.md` G01 行与 `configs/budget/repetition_overlay.yaml`」；overlay 实读 `complete_aa_reps_per_level: 250`、`complete_aa_total_jobs: 1000`（`configs/budget/repetition_overlay.yaml:31-35`） |
| 2026-10-28 11:05 裁决是否落地 | **落地**。`approval_revision_20261028.json` 的 `authorized_by.user_decision_at = 2026-10-28 11:05`，`decision_text` 与用户原话一致 |
| 范围是否严格限于 AA | **是**。`git diff 193ff48..df12f57 -- configs/` 只出现 AA 四格的 `R`/`complete_aa`、`tier1_aa_per_layer`、`design.aa.repeats_per_layer` 与两个计划计数；`formal_repeats` 其余项实读仍是 ATE 500 / 学习 200 / 独立验证 200 / Tier2 100 / 再训练 200 / 固定 bootstrap 1000 / 随机名单种子 200，逐项未动 |

**未通过的子项（P2，文档层）**：`GOAL.md:7`（交接段）与 `GOAL.md:27`（G01 行）至今仍写「共 **11 行**配置改动」。GOAL 最后一次修改是 `5f1d7b8`（2026-10-28 11:26），早于 18:36 的第 12 行补正，故该数字已过期。这属于验收文档与实况不一致，不是范围越权（12 行全部是 AA 批数的不同副本）。

### 1.2 改动范围 — PASS

```
git diff --numstat 193ff48..df12f57 -- configs/
1  1  configs/v3/design.yaml
1  1  configs/v3/execution.yaml
10 10 configs/v3/scenarios.yaml
```

- 合计 **12 行**（design 1 / execution 1 / scenarios 10），与任务描述、理由文档 §2、修订档 `changed_lines_total=12` 三方一致。
- 同一区间 `src/` 无任何改动；`git diff --name-status df12f57..HEAD -- src/ configs/ sql/` 为空，即落盘后无人再动配置与源码。
- 字节增量与语义改动自洽：scenarios `80 082 → 80 073`（−9 = 8 处 `1000→250` 各 −1 + `12500→9500` −1 + `4000→1000` 0），execution −1，design −1。若混入第 13 处改动，字节数会对不上。
- 行尾未被重写：scenarios 变更前后均为 3 407 行 / 3 407 个 CRLF；execution、design 均为 LF（66 / 75 行）。与理由文档 §2「按各自终止符写回」相符。
- tests 同区间 5 行变更（`test_v3_aa.py` 3 行、`test_v3_power.py` 2 行），属守卫冻结值，见 1.7。

### 1.3 绑定值 — PASS

`load_v3_protocol()` 实读（当前 HEAD 树）：

```
config_hash      : 00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3
formal_repeats   : tier1_aa_per_layer=250（其余 9 项与 1.1 所述冻结值一致）
AA 四格          : L0/L1/L2/L3_AA → R=250, complete_aa=250, models=[]
planned_counts   : complete_aa_jobs=1000, historical_dgp_jobs=9500
```

| 核验点 | 实读/复算 | 结论 |
|---|---|---|
| `config_hash` | `00723dc2…` 与任务要求、修订档、`protocol_manifest.json`、两个测试文件一致 | MATCH |
| 7 份 `source_sha256` | 加载器实读 = manifest = 磁盘逐文件 sha256（`business d1259d23…`、`design 8890d25b…`、`evaluation 5f6dfcb2…`、`execution 58623f85…`、`models 19ce3bf5…`、`policy 57ff5721…`、`scenarios b8fa1480…`） | 7/7 MATCH |
| 修订档 `changed_files` 3 个 sha | `execution 58623f85…`、`scenarios b8fa1480…`、`design 8890d25b…` 与磁盘一致 | 3/3 MATCH |
| `experiment_matrix.csv` | sha256 `30645842ea4928975ab99f2ce9f8e83f7a75da4d19c2bae920b1f30dd8881409`，48 796 B | MATCH |
| 矩阵内容可重算 | 用当前配置在内存中跑 `protocol_rows()`，93 行逐格与 CSV 比对 **0 差**（含 `config_hash` 列全为 `00723dc2…`） | 可重建 |
| manifest 可重算 | `config_hash` / `source_sha256` / `protocol_sha256` / `parameter_rationale_sha256`（`350fed09…`）/ `planned_counts` 五项全部 MATCH | 可重建 |
| `protocol_sha256` | `eb85a3284a01a4f428c29d4cd84098a123ae629d44ceb6b1ac9fcd11f107e6fc` = `docs/v3_协议.md` 当前 sha256；该文件最后一次提交为 `5020c56`（Phase A），未再编辑 | MATCH |

### 1.4 Phase A 保全 — PASS

- `outputs/v3/protocol/approval.json` sha256 = `8f8a7e21537430250f9ab195adbd0c84cf968ab33816dbb8b8000e3cd6866f31`，与修订档 `approval_unchanged.sha256`、任务要求一致。
- `outputs/v3/protocol/experiment_matrix.csv` sha256 = `c3c7a63a…`，等于 `approval.json` 的 `matrix_sha256`。
- `git diff --stat 5020c56..HEAD -- outputs/v3/protocol/ docs/v3_协议.md` **输出为空** ⇒ 相对 Phase A 提交逐字节未变；`git log -- outputs/v3/protocol/` 只有 `5020c56` 一条提交。
- `git status --porcelain outputs/v3/protocol/ docs/v3_协议.md` 为空 ⇒ 相对 HEAD 无改动。

### 1.5 理由文档一致性 — PASS（含 3 项 P2）

| 核验点 | 实读结果 |
|---|---|
| `reason_doc.sha256` | 磁盘 `docs/v3_phase_G_protocol_change_aa250.md` = `4f44b0a0e73cd3361c4e233adf66535f02f3ff3f1e0b51ce2939f27ea9fd6bd2`，等于修订档登记值 | MATCH |
| §2 的 12 行清单 | 行号逐条实读命中：`execution.yaml:25`、`design.yaml:38`、`scenarios.yaml:261/264/411/429/1296/1314/1925/1943/2942/2960`；每行值均为 250 / 9500 / 1000 | 一致 |
| §3 的改后值 | `config_hash 00723dc2…`、三份改动文件 sha、四份未动 yaml sha、`matrix 30645842…`（48 796 B）、`protocol_sha256` 不变、两个计划计数，逐项与实读一致；`6b672610…` 被正确标注为「只改前 11 行」的中间值（18:24 失败日志里实际就是该值） | 一致 |
| §5 第 7 条 | 原文「**独立评审**：对本修订单独评审，返回 PASS 后才允许把 G01 记为"按新契约开跑"。**当前未做。**」；文档头也写明「独立评审返回 PASS 之前，不得把 G01 记为"按新契约开跑"」 | 明确保留 |
| 历史绑定 | `df12f57` 版本的理由文档 sha = `9b685880…`，与当时修订档登记值一致 ⇒ 变更记录里 18:47 那条「重算 reason_doc.sha256」属实 | 可追溯 |

**P2-1（数字过期）**：§5 第 5 条写修订档为「（3 708 B）」。3 708 B 是 `df12f57` 版本的大小（`git show df12f57:… | wc -c` = 3708）；当前文件为 **4 204 B**，因为 19:03 同批编辑给它加了 `updated_at` 与 4 条 `revision_history`，而 §5.5 的字节数没跟着改。TODO.md 的 19:05 段同样沿用 3 708 B。

**P2-2（描述过宽）**：§5.5 称修订档「含…逐文件 `source_sha256`」。实读修订档只有 `changed_files` 里的 **3 份**改动文件 sha；其余 4 份未动 yaml 的 sha 只出现在 `protocol_manifest.json` 与本文 §3，不在修订档里。

**P2-3（未执行的文档指针）**：§5.8 计划「README / GOAL 的 G01 行改为指向新修订文件」。实读 `grep -n "protocol_change_aa250\|protocol_aa250" GOAL.md README.md` 无命中 ⇒ GOAL G01 行既未指向修订文件，也仍写 11 行。该项在 §5 中标为计划而非「已完成」，但与「已执行」的文档状态不完全一致。

（另有 P3 级瑕疵，见 §4。）

### 1.6 计划计数 — PASS

- `configs/v3/scenarios.yaml` 实读 `complete_aa_jobs: 1000`（第 264 行）、`historical_dgp_jobs: 9500`（第 261 行）。
- 独立调 `planned_counts(data)` 复算：`complete_aa_jobs=1000`、`historical_dgp_jobs=9500`，与声明值**逐项相等，0 drift**；`load_v3_protocol()` 全程无 `ConfigError`。
- 校验代码实读确认这两项是真校验而非摆设：`validate_v3_config()` 里 `Planned count drift {name}: declared=…, derived=…` 会在不等时抛异常；AA 契约另有 `fr["complete_aa"] == reps["tier1_aa_per_layer"]` 与 `s["R"] == max(fr.values())` 两条硬断言。
- 场景总数 73 + 设计功效格 20 未变。

### 1.7 守卫测试 — PASS

`git diff 193ff48..df12f57 -- tests/` 全文只有 5 行：

- `test_v3_aa.py`：docstring 的「1000 次」→「250 次」、`registered_reps == 1000` → `== 250`、`repeats_per_layer == 1000` → `== 250`；
- `test_v3_power.py`：`FROZEN_CONFIG_HASH = "30511a32…"` → `"00723dc2…"`（含注释一行）。

两处断言仍是**硬相等**，没有改成 `in`、`approx`、`or` 或跳过。本机只跑这两条（R=0）：`..` 2 passed。

`design.yaml` 的 `repeats_per_layer` 全仓 grep：除 `configs/v3/design.yaml:38` 与 `tests/test_v3_aa.py:242` 外，只剩文档与 `out/` 下的旧快照（`out/*_snapshot`、`out/scratch/sim_v3_aa250`）。**`src/` 与 `scripts/` 无任何读取** ⇒ 它确实是「注册表副本 + 守卫」，实际批数由 `formal_repetitions.complete_aa` 驱动。把它对齐到 250 是保持契约内部一致所必需（否则 18:24 那条守卫会一直红），不是扩大范围。

### 1.8 测试凭据 — PASS

| 凭据 | 实读 |
|---|---|
| `pytest_g_aa250_20261028_1824.{log,json}` | 存在、已入库。日志进度条 1 275 个字符、其中 **2 个 F**；`EXIT=1`；`18:24:48–18:34:50`（602 s）；失败两项正是 `test_v3_aa.py`（`registered_reps==1000`）与 `test_v3_power.py`（`FROZEN_CONFIG_HASH` 仍为 `30511a32…`，实际 `6b672610…`），与文档描述一致 |
| `pytest_g_aa250_20261028_1836.{log,json}` | 存在、已入库。进度条 **1 275** 个字符、0 个 F/E；`EXIT=0`；`18:36:49–18:45:27` = **518 s**；与文档「1 275 项、EXIT=0、518 s」一致 |
| sha 自洽 | 1836 json 的 `sha256=f8df46b0…`、`bytes=1527` 与日志实算一致；1824 json 的 `sha256=e773cb2c…` 与日志实算一致；四条记录在 `outputs/evidence/coverage.json` 中的 sha/bytes 亦一致 |
| 「描述的是修订后树」 | 绑定 glob 内最新 mtime 为 `configs/v3/design.yaml 18:35:40`，早于 `START 18:36:49`；`src/` 最新 v3 文件为 `18:35:40` 之前的 `00:55:55`。无任何绑定文件在测试开始后被写过 |

关于日志末行没有 `N passed`：`pyproject.toml:39` 的 `addopts = "-q …"` 叠加命令行的 `-q` 使 verbosity 为 −2，pytest 会省略汇总行，json 里的解释成立；条数以进度条字符数独立复核为 1 275。

### 1.9 历史证据 — PASS

- F02 绑定：`outputs/v3/f02_formal/approval.json:33` 与 `snapshot_binding.json:73` 均为 `protocol_config_hash = e1aa4314b8d84b04a26150cb8ccea5a35dbe9b2d514fee724c56570d5b586d75`。
- `snapshot_binding.json` 的 7 份配置哈希仍是**修订前**的值（design `d2fd51a1…`、execution `dc1c8e9a…`、scenarios `29a158b0…`），证明它记录的是运行当时，没有被本次修订回写。
- `git log 193ff48..HEAD -- outputs/v3/f02_formal` 为空；`git diff --name-status 193ff48..HEAD -- outputs/` 只有：`M outputs/evidence/coverage.json` + 4 个新测试日志 + 6 个 D01 表 + 3 个 `protocol_aa250/` 新文件。**没有任何既有 manifest 或既有证据内容被改写。**
- `coverage.json` 的变更形态：59 行新增 + 1 行替换（`total_bytes` 15 903 166 → 15 916 738），即追加登记。全表 **54 条记录、0 条 sha 不符、0 条 bytes 不符、0 条目标缺失**，`sum_bytes` 与 `total_bytes` 相等。故「未改写既有证据」成立，准确表述应为「既有证据内容未改写，索引表追加登记」。

### 1.10 09 号脚本硬编码偏差 — PASS（含 1 项 P2 提示）

- 源码实读：`scripts/09_freeze_v3_protocol.py:39` `"experiment_results_exist": False`，确为硬编码。
- `outputs/v3/protocol_aa250/protocol_manifest.json` 该字段为 `false`（脚本原样产物，未手改）。
- 修订档 `experiment_results_exist: true`，并附 `experiment_results_note` 说明「F02 的 200 rep 是在旧协议（`30511a32…` / `e1aa4314…`）下产生的，本次修订不改其绑定」——把「结果存在」与「本协议下尚未跑」两件事分开了，属实。
- 理由文档 §5 第 4 条同样如实记录该偏差及处理方式。

提示（P2 级观察，不影响结论）：单看 `protocol_manifest.json` 会读到 `status: "phase_a_draft_pending_independent_review"`（这是 `configs/v3/execution.yaml:3` 的 `config_status` 原值，随新协议一起被复制）与 `experiment_results_exist: false`。目录里同放修订档可解，但 manifest 本身不自带任何指向修订档的注记；若后续有人只读 manifest，可能误判为「Phase A 草稿、无结果」。

### 1.11 回滚可执行性 — FAIL（1 项 P1）

§6 现文（19:03 已由 11 行改为 12 行）：

> 把 §2 的 12 行改回原值 → 重跑 `scripts/09_freeze_v3_protocol.py` → 在 `approval.json` 追加一条回滚 revision。

三处不成立：

1. **只回滚 12 行配置，测试会红。** 18:24 的 pre-fix 日志已经证明：配置回 1000 后，`test_v3_aa.py` 的 `registered_reps == 250` 与 `repeats_per_layer == 250`、`test_v3_power.py` 的 `FROZEN_CONFIG_HASH == 00723dc2…` 必然失败（当时是镜像情形）。回滚清单必须包含 **tests 的 4 行**（`test_v3_aa.py` 2 条断言 + docstring 可选，`test_v3_power.py` 1 条哈希），否则「回滚后跑 pytest」不可能绿。
2. **「重跑 09」未给 `--output`。** 该脚本默认 `--output outputs/v3/protocol`（`scripts/09_freeze_v3_protocol.py:20`），即直接覆盖 Phase A 目录，与本文 §5 第 3 条「就地重跑等于把 Phase A 批准改写成今天」以及 AGENTS 的字节保全要求直接冲突；若不覆盖而是写回 `protocol_aa250/`，又会毁掉本次修订的档案。必须显式指定新目录，并在写盘后复核 `outputs/v3/protocol/approval.json` 仍为 `8f8a7e21…`、`experiment_matrix.csv` 仍为 `c3c7a63a…`。
3. **「在 `approval.json` 追加回滚 revision」指向不明。** 仓库里有两个同名对象：Phase A 的 `outputs/v3/protocol/approval.json`（必须保持 `8f8a7e21…` 字节不变）与 `outputs/v3/protocol_aa250/approval_revision_20261028.json`。按字面执行会破坏 Phase A 保全这条本修订自己立下的不变量。

结论：**回滚步骤方向正确（12 行 + 重算 + 追加 revision），但按现文执行不可行**。这是流程/应急路径缺陷，不改变已落盘配置的正确性，也不要求任何重跑。

---

## 2. 复算清单（本次评审的实读摘要）

| 对象 | 实读值 | 判定 |
|---|---|---|
| `load_v3_protocol().config_hash` | `00723dc26df517b2ddb926f71d1425bb57713150a2d7abd4aebf417b9f7227b3` | MATCH |
| `docs/v3_协议.md` | `eb85a3284a01a4f428c29d4cd84098a123ae629d44ceb6b1ac9fcd11f107e6fc` | MATCH |
| `outputs/v3/protocol_aa250/experiment_matrix.csv` | `30645842ea4928975ab99f2ce9f8e83f7a75da4d19c2bae920b1f30dd8881409` / 48 796 B | MATCH |
| `outputs/v3/protocol/approval.json` | `8f8a7e21537430250f9ab195adbd0c84cf968ab33816dbb8b8000e3cd6866f31` | 未变 |
| `outputs/v3/protocol/experiment_matrix.csv` | `c3c7a63ad99fb921698ebbc638db50c18f5c0b672aad09d0a67c37c1dba9a8c7` | 未变 |
| `docs/v3_phase_G_protocol_change_aa250.md` | `4f44b0a0e73cd3361c4e233adf66535f02f3ff3f1e0b51ce2939f27ea9fd6bd2` / 13 895 B | MATCH |
| `outputs/v3/protocol_aa250/approval_revision_20261028.json` | `250f2afc…` / **4 204 B**（文档写 3 708 B） | 文件存在，字节数过期 |
| `configs/v3/execution.yaml` / `scenarios.yaml` / `design.yaml` | `58623f85…` / `b8fa1480…` / `8890d25b…` | MATCH |
| 计划计数（声明 vs 推导） | 1000 vs 1000；9500 vs 9500 | 0 drift |
| 矩阵（重算 vs 文件） | 93 行 / 93 行，单元格差 0 | 可重建 |
| 登记表 | 54 条，0 缺失，0 sha 不符，0 bytes 不符 | 全绿 |
| 测试 | 1 275 项 / EXIT=0 / 518 s；pre-fix 1 275 项 / EXIT=1 / 2 失败 / 602 s | 与文档一致 |
| 守卫测试（现跑） | 2 passed | 通过 |

---

## 3. 总体结论与条件

**总体结论：PASS WITH CONDITIONS（0 P0 / 1 P1 / 3 P2）。**

修订本身（12 行、绑定值、计划计数、Phase A 保全、F02 绑定不变、测试绿）经独立复算全部成立；没有发现伪造、静默降级或范围越权。阻塞项只有一项流程性缺陷（回滚不可按文执行），另有三项文档同步缺陷。

### 条件（须在把 G01 记为「按新契约开跑」之前关闭；均不需要重跑任何数据作业）

- **C1（P1，回滚）**：改写 §6，使其可执行——(a) 回滚清单补 tests 的 4 行冻结值（`test_v3_aa.py` 两条断言 + `test_v3_power.py` 的 `FROZEN_CONFIG_HASH`），并注明「回滚后必须重跑这两条守卫」；(b) 09 号显式 `--output` 到 Phase A 之外的新目录，写盘后校验 `outputs/v3/protocol/approval.json = 8f8a7e21…`、`experiment_matrix.csv = c3c7a63a…` 未变；(c) 明写回滚记录追加到**修订档**（或新的 `approval_revision_*.json`），不得写 Phase A 的 `approval.json`。
- **C2（P2，验收文档同步）**：把 `GOAL.md:7` 与 `GOAL.md:27` 的「11 行」改为「12 行」，并按 §5.8 的承诺让 G01 行指向 `docs/v3_phase_G_protocol_change_aa250.md`。G01 状态列保持「未证实」不动。
- **C3（P2，理由文档数字）**：§5.5 的「3 708 B」改为当前 4 204 B（或改为「3 708 B（18:47 版）→ 4 204 B（19:03 版）」）；同时把「逐文件 `source_sha256`」改为「3 份改动文件的 `source_sha256` + manifest 中的完整 7 份」，与实读一致。

> 注意：C2/C3 若落笔到理由文档，`reason_doc.sha256` 会再次失效（本次评审只对 `4f44b0a0…` 这个版本负责），必须按 19:05 反思日志的教训重算并回填修订档，且回填后需再核对一次该字段。

### 可选（P3，不影响门禁）

- 修订档 `authorized_by.scope` 只列「R / complete_aa / tier1_aa_per_layer + 两个计划计数」，未含 `design.yaml`；`changed_files` 已含并注明，建议 scope 也补一句。
- 理由文档头部「状态：…（2026-10-28 18:37）」未随 19:03 修改更新。
- `pytest_g_aa250_20261028_1824.json` 缺 `bytes` 字段（1836 那份有）。

---

## 4. 本次评审可支持 / 不可支持的说法

**可支持（有本次实读/复算证据）**

1. AA 四层批数已从 1000/层 改为 250/层，总计 1000；改动恰为 **12 行**（design 1 / execution 1 / scenarios 10），无 src 改动、无行尾重写、无第 13 处改动。
2. 当前树 `config_hash = 00723dc2…`，7 份 `source_sha256` 与磁盘、manifest、修订档三方可对齐；`planned_counts` 声明值 = 推导值（1000 / 9500，0 drift）。
3. `outputs/v3/protocol_aa250/` 的矩阵与 manifest **可由当前配置在内存中完整重建**（93 行 0 差）；矩阵 sha `30645842…` 与 `docs/v3_协议.md` 的 `eb85a328…` 均可复算。
4. Phase A 的 `approval.json`（`8f8a7e21…`）、Phase A 目录与 `docs/v3_协议.md` 相对 `5020c56` 逐字节未变。
5. F02 仍绑定 `e1aa4314…`，其快照里 7 份配置是修订前的值；本次修订未改写任何既有 manifest 或既有证据内容（只有登记表追加）。
6. 修订后的树跑过一轮全量串行测试：1 275 项、EXIT=0、18:36:49–18:45:27（518 s）；18:24 的 EXIT=1 与两项失败原因如实保留。两条守卫测试仍是硬相等，且现在通过。
7. 理由文档当前版本（`4f44b0a0…`）已绑定进修订档；§2 行号、§3 改后值逐项与实况一致；§5 第 7 条明确「独立评审未做、之前不得记为按新契约开跑」。
8. 09 号脚本 `experiment_results_exist` 硬编码 `false` 的偏差在修订档与 §5 第 4 条如实声明。

**不可支持**

1. **不能说「回滚只需把 12 行配置改回 + 重跑 09」**：按现文执行会让 tests 变红（18:24 已实证反向情形），且 09 默认输出会覆盖 Phase A 目录，「在 approval.json 追加」指向不明。见 C1。
2. **不能说「改动共 11 行」**（GOAL 目前仍这么写）：实况 12 行。
3. **不能说「修订档含逐文件 `source_sha256`」**（§5.5）：修订档只有 3 份改动文件的哈希。
4. **不能说「修订档 3 708 B」**：当前 4 204 B。
5. **不能由本次评审直接得出「G01 已可按新契约开跑」**：本评审只覆盖授权链、绑定值、范围与证据自洽；C1–C3 关闭前，G01 状态列应保持「未证实」，状态改写按 AGENTS §7.4 由主负责执行。
6. **不能把本次结论外推到 G01/G02 的实际数值**：AA 的真 FPR、逐层区间、G02 的任何结果都尚未产生；本评审不涉及任何 R>0 运行。
7. **不能说「F02 结果因本次改配置而失效」**：反证已列（绑定与快照均为旧哈希，且未回写）；但同样不能说「F02 已通过」——其独立科学评审仍未做。

---

## 5. 评审边界

- 只读评审：未运行任何 R>0 作业、未跑全量 pytest、未修改除本文件外的任何文件。
- `out/` 被 `.gitignore` 忽略，`out/scratch/g_route_jia_aa250.py` 与 18:24 补丁工具本身不在库内，本次只核验其**结果**（配置字节、行数、sha、测试日志），未审计补丁脚本实现。
- 未核验 18:26 初版修订档与 19:03 中间版 reason doc 的字节（未提交，无法回溯），只核验了 `df12f57` 与 HEAD 两个已提交版本之间的绑定关系。
