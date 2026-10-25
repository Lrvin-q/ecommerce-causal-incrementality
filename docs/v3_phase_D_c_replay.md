# Phase D 整改：四处必修 + C 代表库重放

> 合成数据 / 已知 DGP。维护时间：2026-10-25 15:01（北京时间）。
> 本文记录**未参与 D.4 原产出**的独立工程评审给出的"有条件通过"里那四处必修。
> 评审结论：数据等价性成立（C 代表库 `observed.sqlite` 字节级相同），但有 4 处缺口，
> 其中 2 处是主控造成的**静默降级**（测试变成空断言），1 处是**溯源缺口**，1 处是**重放凭据**。

## 0. 一页结论

| # | 缺口 | 状态 | 证据 |
|---|---|---|---|
| 1 | 两条全链路测试 monkeypatch 了已死的 `v3_sql._load_facts`，实为 fast-vs-fast 空断言 | **已修** | 改换活调用点 + `calls == ["legacy","fast"]` 反空洞断言；"改坏会红"双向实验：新版 FAILED、旧版照旧通过 |
| 2 | `LOAD_PRAGMAS=()` 使 PRAGMA 恢复机制零覆盖 | **已修** | `monkeypatch` 注入 `journal_mode=WAL` + `temp_store=2`，覆盖"装载期间生效/逐项恢复/异常路径/跨连接复查" |
| 3 | `from_manifest` 不校验 `source_hashes_before`，篡改装载器哈希仍 ACCEPTED | **已修** | 读时逐项校验 40 个绑定文件；篡改任一 key → 抛错并点名文件；新增 10 条测试 |
| 4 | 未用当前源码重放 C 代表库，新指纹 `4cbf8306…` 缺验收凭据 | **已完成** | 4 代表库 + 4 个 matrix 类作业、8×31/29 个产物：**236 字节相同 + 4 内容相同（仅 footer 路径）+ 8 预期差异 + 0 不一致** |

新绑定指纹：**`sql_source_hash() = 4cbf830621ac7ed4728e92cee1dbadf41698d0b871c83dd3af2846870a931795`**
（C 阶段为 `18fe1968…`）。重放产物的 `sql_sha256`、`source_hashes_before` 全部绑定到它。

---

## 1. 第 1 项：两条全链路测试从"自比较"改为真 A/B

### 1.1 问题

`run_sql_pipeline` 的调用点在 D.4 已切到 `load_facts_fast`，但两条测试仍在 monkeypatch
`v3_sql._load_facts`——该属性已无任何调用方。于是：

```python
monkeypatch.setattr(v3_sql, "_load_facts", _legacy_load_facts)   # 死代码
legacy = run_sql_pipeline(tables, cfg)                          # 实际走 fast
monkeypatch.setattr(v3_sql, "_load_facts", load_facts_fast)     # 死代码
fast_result = run_sql_pipeline(tables, cfg)                      # 也走 fast
```

两次运行是同一个函数，断言必然成立——**测试绿，但零信息量**。这是主控切换调用点时
没有同步测试造成的静默降级。

### 1.2 改法（`tests/test_v3_sql_fast.py`）

1. `test_sql_pipeline_output_is_identical_under_both_loaders`
   - 改为替换**活调用点** `v3_sql.load_facts_fast`：先换成 `v3_sql._load_facts`（旧逐行实现，
     带包装器记录调用），再换回 `load_facts_fast`；
   - **反空洞断言**：`assert calls == ["legacy", "fast"]`。谁把调用点改回 `_load_facts`、
     或让两路都走快路径，这条会先红，不会退化成自比较；
   - 比对口径保持原样：`analysis_sha256`、`user_outcomes`/`analysis`/`quality` 的
     `dataframe_sha256`、六张汇总视图逐帧相等、`sql_sha256`、分母数。
2. 新增 `test_the_two_loaders_write_byte_identical_sqlite_files`：同一 `run_id`、同一输入，
   两条装载路径各落一个持久库，比对**文件字节**（`file_sha256` 与大小）。这是 D.4 承诺
   最强形式——不是"帧相等"，而是落盘逐字节相等。
3. 原 `test_fast_fact_loading_context_manager_only_swaps_the_hook` 改写为
   `test_fast_fact_loading_context_manager_only_swaps_the_dead_hook`：显式钉住
   `fast_fact_loading()` **只交换已死的 `_load_facts`、不碰活调用点**，并证明真 A/B 手段
   （替换 `load_facts_fast`）确实可用。这是"反静默降级"的第二道锁。

### 1.3 "改坏会红"实验（做了一次，未改任何仓库文件）

评审要求：故意把旧实现改坏，测试必须失败。实现的 sabotage **不进仓库**：
`out/engfix_scratch/red_plugin.py` 作为 pytest 插件，在 `pytest_configure` 里把
`v3_sql._load_facts` 替换成"把第一个用户 `hist_gmv` +1"的版本（行数不变、不触发
质量审计，因此差异必然来自装载内容本身）。这样比改文件更安全：**进程结束即恢复，没有
"忘了恢复"的风险**。

| 运行对象 | 命令要点 | 结果 |
|---|---|---|
| **修好后的测试** | `pytest tests/test_v3_sql_fast.py -k test_sql_pipeline_output_is_identical_under_both_loaders -p red_plugin` | **FAILED** |
| **修好前的测试（复刻）** | `pytest out/engfix_scratch/test_old_vacuous_ab.py -p red_plugin`（与旧版测试体逐字相同） | **PASSED** |

失败信息（节选）：

```
E       AssertionError: assert 'd1875b43bec2...d255274b98ec3' == '4510c6877622...994aa8bd67470'
FAILED tests/test_v3_sql_fast.py::test_sql_pipeline_output_is_identical_under_both_loaders
```

同一 sabotage 下旧版测试照旧通过——这就是"空洞测试"的直接证明。日志：
`out/engfix_scratch/red_new_test.log`、`out/engfix_scratch/red_old_test.log`。

---

## 2. 第 2 项：PRAGMA 恢复机制重新纳入覆盖

### 2.1 问题

主控裁决把 `LOAD_PRAGMAS` 置空（零收益、`journal_mode=OFF` 有崩溃风险），于是
`_PRAGMA_NAMES=()` ⇒ `read_pragmas()` 恒 `{}`。原来那两条测试变成
"`{} == {}`"与"恢复前后都是 `{}`"，**恢复机制（读原值→登记→try/finally→读回校验→异常
路径回滚）零覆盖**。

### 2.2 改法（不改生产配置）

用 `monkeypatch` 把 `LOAD_PRAGMAS` 与 `_PRAGMA_NAMES` 临时换成
`(("journal_mode", "WAL"), ("temp_store", 2))`——**刻意不用 `journal_mode=OFF`**，避免评审
指出的"崩溃后留下不可回滚的库"。四条断言：

| 测试 | 证明什么 |
|---|---|
| `test_probe_pragmas_take_effect_and_are_restored_item_by_item` | 装载期间 `journal_mode=wal`、`temp_store=2`（且 `applied` 登记了两项）；退出后**逐项**恢复成装载前的原值（`delete`/`1`） |
| `test_probe_pragmas_are_restored_when_the_load_raises` | 违反 `CHECK(hist_gmv>=0)` 抛 `IntegrityError` 后仍恢复，且失败装载没留下半张表 |
| `test_the_loader_applies_the_probe_pragmas_around_the_inserts` | 用 `iter_fact_rows` 探针在**插入过程中**读 PRAGMA，证明"生效"不是只在边界上 |
| `test_empty_pragma_tuple_touches_nothing`（保留） | 生产配置 `LOAD_PRAGMAS == ()` 时**不触碰任何 PRAGMA**；现在先断言 `LOAD_PRAGMAS == ()`，再对 `journal_mode/temp_store/synchronous/cache_size` 逐个比对前后值（不再对空集合断言） |

### 2.3 两个实现陷阱（写进测试注释，避免后人再踩）

1. **`read_pragmas()` 的默认参数在函数定义时绑定**成 `_PRAGMA_NAMES`（当时为空元组），
   monkeypatch 模块属性**不会**改默认值。测试必须显式传名字：`read_pragmas(conn, names)`。
2. **`temp_store` 是 per-connection**，不写入文件：跨连接复查只能对 `journal_mode` 做
   （它是数据库文件属性）；新连接读到 `temp_store=0` 是正常现象，因此"原值复位"必须在
   **同一连接**上验证。原实现里我第一版把 `temp_store=1` 设完就关连接，结果新连接读到 0
   ——测试直接红，正好证明这条断言是有牙齿的。

---

## 3. 第 3 项：`from_manifest` 的 `source_hashes_before` 读取守卫

### 3.1 问题（评审的篡改实验）

`ObservedDataset.from_manifest` 只校验 `sql_sha256`，而 `sql_source_hash()` 只覆盖
`sql/v3_schema.sql`、`sql/v3_analytics.sql`、`v3_sql.py`。**装载器 `v3_sql_fast.py` 不在其中**。
把 manifest 里装载器哈希改成假值，`from_manifest` 照样 ACCEPTED——"装载器已由
`pipeline_source_hashes()` 覆盖"**只在写时成立，读时不成立**。

### 3.2 改法（`src/causal_growth/data/v3_observed.py`）

新增 `_drifted_sources()` 与 `_check_source_binding()`，并在 `from_manifest` 的
`sql_sha256` 校验之后调用：

- 重算 `pipeline_source_hashes()`（40 个绑定文件：`src/causal_growth/**/v3*.py`、
  `sql/v3*.sql`、`configs/v3*.yaml`、`configs/v3/*.yaml`），**逐项**比对 manifest 的
  `source_hashes_before`；
- manifest 里出现、但当前 glob 不覆盖的 key（例如 `requirements.txt`），按记录路径
  **直接哈希文件自身**，因此"至少覆盖 manifest 里出现的全部 key"成立；
- 路径逃出仓库、文件不存在、摘要非字符串，一律计为漂移；
- 有漂移 → `ValueError: persisted dataset source files drifted since materialization: [...]`，
  **点名是哪几个文件**；
- 校验结果写进 `lineage["source_binding"] = "verified" | "absent"`，读取方可以区分
  "校验过"与"这份 manifest 没有绑定信息"。

严格性边界（显式而非默认）：

- manifest **有** `source_hashes_before` → 必须全部一致（C/D 阶段流水线产物都属此类）；
- manifest **没有** `source_hashes_before` 但**带 `source_observation_hashes`**（即由
  `build_observed_pipeline` 生成）→ 直接拒绝：机器产物不允许丢掉绑定；
- 两者都没有（`tests/test_v3_observed.py` 的 `_persist` 手工 fixture、早期手工 manifest）
  → 接受，但在 lineage 记为 `absent`。**这是本项唯一的让步**，原因见 §6。

`pipeline_source_hashes()` 的 glob 是 `v3*.py`，**确实**匹配 `v3_observed.py` 本身，所以
本文件一改，旧 manifest 全部被判漂移——这是守卫的正确行为，不是缺陷。

### 3.3 旧 manifest 的处置与"如何重新生成"

**所有旧 manifest 现在都会被拒**（`sql_sha256` 先拒，`source_hashes_before` 再拒）。
重新生成的**一句话**：

> 用当前源码重跑产出它的那条流水线即可——C 工程校验用
> `python scripts/12_validate_v3_data.py --scope <scope>`，下游用 `build_observed_pipeline`（或
> `scripts/13_v3_pilot.py`）；新 manifest 会绑定新指纹。

### 3.4 新增测试（均在 `tests/test_v3_sql_fast.py` §9）

| 测试 | 断言 |
|---|---|
| `test_pipeline_source_hashes_cover_the_loader_and_the_observed_guard_module` | 绑定集合确实含 `v3_sql_fast.py` 与 `v3_observed.py` |
| `test_untampered_source_binding_is_accepted` | 未篡改 → `from_manifest` 通过，`content_hash == analysis_sha256` |
| `test_tampered_source_hash_is_rejected_and_names_the_file`（4 个参数） | 篡改装载器 / 守卫模块自身 / `sql/v3_analytics.sql` / glob 外的 `requirements.txt` → 抛错且**报错信息里出现该文件名** |
| `test_missing_recorded_file_counts_as_drift` | 记录的文件不存在 → 计为漂移 |
| `test_path_escape_in_a_recorded_key_is_refused` | `../outside.py` 这类逃逸路径被拒 |
| `test_pipeline_manifest_without_source_binding_is_rejected` | 有 `source_observation_hashes` 却无绑定 → 拒绝 |
| `test_hand_built_manifest_without_binding_stays_readable_but_marked_unbound` | 手工 manifest 可读，但 `lineage["source_binding"] == "absent"`；有绑定则为 `"verified"` |

---

## 4. 第 4 项：按"第三种做法"重放 C 代表库与跨层作业

### 4.1 方法与三个不可省的细节

评审裁决：不必重跑 C 的 101 个作业，但必须用当前源码按 C manifest 记录的
`run_id` / `stream_prefix` / `rep` 重放代表库与跨层作业。脚本：
`scripts/15_replay_c_representatives.py`（sha256 `9ef2ece1a7c79de2…`）。

1. **必须复用 C 的 `run_id`**：`run_id` 是观测表的第一列，写进每个 parquet。换
   `run_id` 重放数据必然不同——那是比对设计错误（`docs/v3_phase_D_loader_switch.md` §3.2
   的教训），不是装载差异。脚本只**读** C manifest 的 `run_id`/`stream_prefix`/`rep_id`/`n`。
2. **源码快照**：4 个正式 AA 作业正在跑，且其他代理会写 `v3*.py`；`build_observed_pipeline`
   运行前后各哈希一次源码，任何并发写盘都会让作业判伪。因此把 `src/ sql/ configs/` 字节
   复制成快照，用 `--source-root` 从快照导入并运行（`sys.path` 指向快照，库内
   `Path(__file__).parents[3]` 自然解析到快照根），并用 `--expect-source-commit` 把快照钉在
   一个 git 提交上逐文件校验。
3. **判定三档，互不混淆**：
   - `identical`：字节相同；
   - `identical_content`：parquet 字节不同，但 `dataframe_sha256` 相同**且** footer 里除
     `pandas.attributes.source_path` 外没有任何元数据差异（见 4.4）；
   - `expected_drift`：`lineage/source_hashes_after.json`，它记录**生产时**的源码表，重放
     必然绑定新指纹，按设计不同。
   只有 `DIFFERS`/`MISSING` 判失败；每一行的 `verdict`/`note` 都落在 CSV 里，不做静默归类。

### 4.2 执行过程中的两个真实事故（一并记录）

- **14:32:01 仓库被切分支**（`codex/v3-rebuild` → `master`，reflog 有
  `[Checkout-checkpoint]`）。工作树一度不含任何 v3 源码。应对：源码快照不再从磁盘复制，
  而是用 `git cat-file` 从提交 **`0204747`**（切换瞬间的 checkpoint，含我 14:31 的最终版本）
  逐 blob 重建，并用 `--expect-source-commit 0204747` 校验 40 个文件逐字节相等。事后核对：
  `git diff 0204747 <HEAD> -- src sql configs` 为空，说明**快照就等于当前源码**。
- **`representative__L1_main` 首次重放失败**：流水线跑完（202 s）后在
  `manifest.json.tmp → manifest.json` 上抛 `PermissionError: [WinError 5] 拒绝访问`
  （Windows 文件锁，非代码问题）。应对：只重放该作业并 `--merge-existing` 并回既有
  CSV/summary，然后用 `--compare-only` 统一重算判定（重放产物没动，manifest 哈希逐作业记录）。
  因此 **L1 的重放产物来自另一个 stamp**，其余 7 个来自同一 stamp——CSV 的
  `jobs[].replay_manifest` 路径可逐条核对。

### 4.3 重放结果（`outputs/tables/v3_phase_D_c_replay.csv`，248 行）

| 作业 | 类别 | n | `observed.sqlite` 字节（C = 重放） | identical | identical_content | expected_drift | DIFFERS | 判定 |
|---|---|---|---|---|---|---|---|---|
| `representative__L0_P_main` | representative | 200000 | 614,727,680 / 相同 | 31 | 1 | 1 | 0 | passed |
| `representative__L1_main` | representative | 200000 | 602,640,384 / 相同 | 31 | 1 | 1 | 0 | passed |
| `representative__L2_n200000_p050` | representative | 200000 | 653,320,192 / 相同 | 31 | 1 | 1 | 0 | passed |
| `representative__L3_fixed_lt000` | representative | 200000 | 648,769,536 / 相同 | 31 | 1 | 1 | 0 | passed |
| `matrix__L1_main` | matrix | 5000 | 不落库 | 28 | 0 | 1 | 0 | passed |
| `matrix__L2_n200000_p050` | matrix | 5000 | 不落库 | 28 | 0 | 1 | 0 | passed |
| `matrix__L3_fixed_lt000` | matrix | 5000 | 不落库 | 28 | 0 | 1 | 0 | passed |
| `matrix_validation__L1_main` | matrix_validation | 5000 | 不落库 | 28 | 0 | 1 | 0 | passed |

汇总：**236 identical + 4 identical_content + 8 expected_drift + 0 DIFFERS + 0 MISSING**，`verdict: passed`。

四个代表库的关键哈希（C 与重放相同）：

| 作业 | `observed.sqlite` sha256 | `sql/analysis.parquet` `dataframe_sha256` |
|---|---|---|
| `representative__L0_P_main` | `02eabc29f9423b49…` | `feee79487ea541af…` |
| `representative__L1_main` | `d134a500bc6d4cac…` | `0fc7c8ddc7650674…` |
| `representative__L2_n200000_p050` | `aa47d83abf9d9f9b…` | `90b64de98403b3b7…` |
| `representative__L3_fixed_lt000` | `1c24a131979456fb…` | `f437df58caa972aa…` |

`run_id`（C 记录，重放原样复用）：

```
phase_c_20261025T013445468783Z_pid18708__representative__L0_P_main
phase_c_20261025T013445468783Z_pid18708__representative__L1_main
phase_c_20261025T013445468783Z_pid18708__representative__L2_n200000_p050
phase_c_20261025T013445468783Z_pid18708__representative__L3_fixed_lt000
```

C 阶段 4 个代表库 `observed.sqlite` 字节数（614,727,680 / 602,640,384 / 653,320,192 /
648,769,536）与本次重放**逐一相同**；其中 L0_P_main 的 614,727,680 与评审字节级重放的结论一致。

### 4.4 两类"允许的差异"必须解释清楚，否则就是糊弄

**（a）`lineage/source_hashes_after.json`（8/8 作业）**：它记录运行结束时的源码哈希表。
C 阶段 34 个 key（3640 B），现在 40 个 key（4327 B），内容必然不同。这是**溯源产物**，
不同才是正确。

**（b）4 个代表库的 `sql/analysis.parquet`：字节差 2 B，内容相同**。
诊断（`pq.read_metadata` 逐 key 比对）：唯一差异是 pandas `attrs["source_path"]` ——
`ObservedDataset.observations` 把 `source_path` 设成本 run 的 `observed.sqlite` 绝对路径，
pandas 3 / pyarrow 26 会把它写进 parquet footer（文件级 `pandas` 元数据与 `ARROW:schema`
里各一份）。重放必然写到另一个目录，所以：
- `dataframe_sha256` 相同；footer 里 `observed_dataset_hash`（`feee7948…` 等）、
  `config_hash`、`artifact_role` 也相同；把 `attributes.source_path` 归一化后**两份元数据
  完全相等**，字段名/类型/可空性/其余 schema 元数据全等；
- **矩阵作业不落库**，此时 `source_path` 是常量 `<cwd>/data/v3/in_memory_sql`，所以它们的
  `analysis.parquet` 是**逐字节相同**的（28/28 identical）——这反过来证明差异来源就是
  "落库路径"这一项，而不是数据。

脚本把这种情形记为 `identical_content` 并附 note，**不并入 `identical`**，也不隐藏。

### 4.5 新绑定指纹

| 项 | 值 |
|---|---|
| `sql_source_hash()`（`sql_sha256`，SQL 语义指纹） | **`4cbf830621ac7ed4728e92cee1dbadf41698d0b871c83dd3af2846870a931795`** |
| C 阶段对应值 | `18fe196809535533c6380e3cc4f9ea2b538126507b52495399ff687cea598c80` |
| `pipeline_source_hashes()` 40 文件集合哈希 | `052b43dfbf86fe5fe3b9c5e505a177a3c74cda105d107362356435ac9d280a95` |
| 快照来源提交 | `0204747`（含我 14:31 的最终源码；与当前 HEAD 的 `src/ sql/ configs/` 无差异） |
| 重放脚本 sha256 | `9ef2ece1a7c79de2254b15ef7a21b18950483c0e335503e96ee8fa09d1a5b1c7` |

机器可读记录：`outputs/v3/phase_d_c_replay/summary.json`（含 40 个文件的逐文件哈希、
`source_root.set_sha256`、每个作业的 `replay_manifest` 与哈希、`new_sql_sha256`）。
更早两次重放（分类逻辑尚未区分 metadata-only）留档在
`outputs/v3/phase_d_c_replay/run1_superseded/`、`run2_superseded/`，作为**独立第二次重放**
的旁证；其 `observed.sqlite` 结论与本文一致。

---

## 5. pytest 条数与结果

| 范围 | 结果 | 备注 |
|---|---|---|
| `tests/test_v3_sql_fast.py`（单文件，最终状态） | **30 passed in 92.08 s** | 日志 `out/engfix_scratch/pytest_single_final.log` |
| `test_v3_sql_fast.py` + `test_v3_observed.py` + `test_v3_pipeline.py` | **74 passed in 136.77 s** | 覆盖 `from_manifest` 的所有既有调用点，确认第 3 项未回伤既有守卫 |
| 全量 pytest | **未跑** | 见 §6；需主控在无并发写盘窗口串行跑 |

重放与 pytest 没有同时跑；三次运行之间只改了文件头的维护时间（不触碰被测逻辑），
最终单文件运行即本文档所依据的状态。

---

## 6. 未做到 / 残余风险（显式列出，不静默降级）

1. **未重跑 C 的完整 101 作业**。评审裁决允许；本次是 4 代表库 + 4 个 matrix 类作业
   （3 个跨层 history + 1 个独立验证流程），共 8 作业 / 248 个产物。
2. **`source_hashes_before` 缺失未被硬性拒绝**（只在带 `source_observation_hashes` 时硬拒）。
   原因：`tests/test_v3_observed.py` 的 `_persist` 手工构造 manifest 且不含绑定，硬拒会让
   7 条既有测试变红，而该文件**不在我的文件域**。建议主控决定是否给那里补上
   `source_hashes_before`，然后把守卫改成"一律必须有"。
3. **未覆盖 `journal_mode=OFF`**：按评审要求用 WAL，避免"崩溃后不可回滚的库"这一真实风险。
4. **重放是单进程串行**：与 4 个正式 AA 作业并行，代表库耗时 157–202 s（C 时 179–206 s，
   同量级）。没有为了追速度开多进程——抢 CPU 会污染 AA 作业的计时基线。
5. **L1 的重放产物与其余 7 个作业不在同一 stamp**（Windows 文件锁，见 §4.2）。CSV/summary 里
   每个作业的 `replay_manifest` 路径与哈希可逐条核对，没有混用。
6. **全量 pytest 未跑**：`src/causal_growth/data/v3_observed.py` 已改（第 3 项），
   按 AGENTS.md §11 需要"单进程、串行、无并发写盘"的窗口；我这边 4 个 AA 作业仍在跑，
   且期间仓库被切过分支。本次只跑受影响的 3 个文件（74 passed）。
7. **守卫会让并行开发期的旧 manifest 立刻失效**：这是第 3 项要求的语义，但意味着
   "边开发边读旧产物"会红。正确做法是快照运行或冻结窗口（AGENTS.md §11）。
8. **CSV/summary 的产出方式**：重放产物来自 run 2（7 个作业）与 L1 的单作业重放；
   最终判定由 `--compare-only` 用最终版脚本重算（重放产物未改动，逐作业 manifest 哈希已记录）。
   `summary.json` 同时保留 `script_sha256`（首次运行版本）与 `compare.script_sha256`（最终版本），
   不做混淆。

## 7. 复现命令

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
cd 'D:\L\practice_project\营销数分项目'

# 1) 建立源码快照（必须与要绑定的源码逐字节相同）
#    当前仓库即源码时，可以直接 --source-root 省略；
#    需要钉提交时，用 git cat-file 从该提交重建快照并按下面第二种方式校验。
python scripts\15_replay_c_representatives.py --dry-run
python scripts\15_replay_c_representatives.py --source-root out\d4_replay_snapshot\from_0204747 `
    --expect-source-commit 0204747

# 2) 只重算比对（判定逻辑变化时用，不重放）
python scripts\15_replay_c_representatives.py --compare-only `
    --source-root out\d4_replay_snapshot\from_0204747 --expect-source-commit 0204747

# 3) 测试
python -m pytest tests\test_v3_sql_fast.py --basetemp=out\engfix_tmp
```
