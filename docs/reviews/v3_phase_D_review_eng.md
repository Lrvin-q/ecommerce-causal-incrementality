# Phase D 工程评审（可复现性 / 门禁 / 性能 / 代码质量）

> 评审对象：D02 四项证据（AA 1000 次、15 格功效实测 1500 次、合并脚本、快照绑定）。
> 评审方式：只读 + 复算。未修改任何源码或数据；19 号脚本重跑前已备份 `v3_phase_D_local_power_formal.csv`
> 的 sha256（`cbb48822…`），重跑后逐字节相同、工作树保持干净；所有负面探针都在临时目录里执行
> （17 号脚本的 `ROOT` 与 19 号的 `OUT_CSV/OUT_JSON` 均被重定向到临时路径，未触碰 `outputs/tables/`）。
> 评审环境：本机 `.venv`（Python 3.13.7 / pandas 3.1.0 / numpy 2.5.4 / scipy 1.18.1），同机复算。

## 1. 结论

**PASS WITH CONDITIONS。**

数字本身站得住：AA 的 46/1000、CP [0.0339, 0.0609]、SE 校准 0.9948 我用原始逐 rep 表独立复算，
与 `outputs/tables/v3_phase_D_aa_formal_merged.csv` 完全一致；15 格的 1500 次 rep 齐全、无缺口、
`csv_sha256` 可复现；两条"快照运行"的声明有**决定性运行证据**（不是只写了个 hash）。

但在"换一台机器、换一个人"这个口径上，D 阶段现在**不可交接**：

1. 全部门禁所需证据（两个快照、逐 rep 表、manifest、binding json）都在 `out/` 下，而 `.gitignore:66` 忽略了整个 `out/`；
2. `scripts/16_cleanup_scratch.py` 的清理规则**会把合并所依赖的 4 个 AA run-root 判为可删**（实测 `is_obsolete=True`）；
3. 两个门禁脚本（17 / 19）的校验可以被 8 类篡改静默绕过——我逐条构造过，其中 5 条完全放行、2 条 fail-open；
4. 正式文档给不出能复现 15 格的命令。

这些都属于"下一次有人维护时才会炸"的问题，不影响已产出的数字，因此不是 FAIL。

## 2. 逐项结论

### E1 源码绑定是否真的生效 —— **成立（机制与运行都真；跨机可验证不成立）**

**机制**：根目录由 `__file__` 反推，不看 CWD、不看环境变量——

- `src/causal_growth/data/v3_local_power_pipeline.py:121` `PROJECT_ROOT = Path(__file__).resolve().parents[3]`
- `src/causal_growth/evaluation/v3_aa.py:130` 同式；`src/causal_growth/data/v3_pipeline.py:40`（`pipeline_source_hashes`）同式。

**实测（我跑的）**：`PYTHONPATH=<repo>/out/c3_snapshot/src` 下导入模块，得到

```
pkg    : ...\out\c3_snapshot\src\causal_growth\__init__.py
module : ...\out\c3_snapshot\src\causal_growth\data\v3_local_power_pipeline.py
ROOT   : ...\out\c3_snapshot
MDE    : ...\out\c3_snapshot\outputs\tables\v3_phase_D_mde.csv  (exists=True)
pipeline_source_hashes(): 40 项，与 out/c3_snapshot_binding.json 的 files 字典 **完全相等**
```

**运行证据（决定性，不是"写了 hash 但用实仓代码"）**：15 个保留的 rep-0 产物
`out/v3_phase_d_local_power/formal_{L0,L1,L2}/representative/*_rep0_n200000/manifest.json`
里 `source_hashes_before` 各有 40 项，逐项等于 c3 binding。关键区分点：

- 仓内 `src/causal_growth/evaluation/v3_data_checks.py` 现在是 `f823f385…`，快照里是 `f3580ece…`（多出 `_output_registry_lock` 的 OSError 翻译，见 `873ffab`）；
- 这 15 份 manifest 记的全是 `f3580ece…`。若真的从实仓导入，这里必然是 `f823f385…`。

AA 侧同构：`out/v3_phase_d_aa_formal_r{2,3}_det/*/aa_manifest.json` 的
`v3_aa_source_sha256 = 95edd77c18f6d33f…`，与 `out/aa_snapshot/src/causal_growth/evaluation/v3_aa.py`
字节哈希相同，而 `aa_snapshot` 与实仓有 6 个文件不同（`v3_observed.py`、`v3_models.py`、
`design/v3_power.py`、`data/v3_local_power*.py`、`v3_data_checks.py`）。

**弱点（这三点要修）**：

1. `out/aa_snapshot_binding.json` 只登记文件名清单 + 一个集合哈希 `0a087a1b…`，**没有逐文件哈希**（c3 的有）。集合哈希无法回答"哪个文件变了"。
2. 两个 binding 都在 `out/` → 未入库（`git ls-files out/c3_snapshot_binding.json` 为空；`.gitignore:66 out/`）。`aa_snapshot` 的 6 个差异文件中，`src/causal_growth/dgp/v3_local_power.py` 与 `src/causal_growth/data/v3_local_power_pipeline.py` 的 blob **不在 git 对象库**（`git cat-file -e` 失败），即历史版本也找不回来。AA 路径不 import 这两个模块，所以不影响 AA 数字，但它说明"快照不可从版本库重建"。
3. AGENTS §11 要求"把快照的绑定哈希写进产物的 manifest"。逐 rep 产物做到了；但**聚合层没有**——`out/v3_phase_d_local_power/formal_LX/local_power_manifest.json` 只有 `protocol_config_hash`，`outputs/tables/v3_phase_D_local_power_formal.json` 只有三路 summary 的 sha256，都没有源码指纹。

### E2 去重与合并的正确性 —— **结果正确，门禁部分成立（"逐位一致"是事实，但不是脚本保证的）**

**数量复现**：`L0/L1/L2` 各读 338 行→250，`L3` 370→250；合计 1384 行→1000 个 `(block,rep)`，与文档 §5/§6 一致。

**p 值是否真的一致**：一致，而且远不止 p 值。我按 `(block,rep)` 分组比较**全部列**：

- L0：48 个重复组，**没有任何列**不同（含全部 `*_p_value`、`*_diff`、`*_se`、CPU/墙钟）；
- L3：43 个重复组，数据列全同，只有 8 个计时列不同（`dgp/pipeline/itt/total` 的 cpu 与 wall）。
  例：L3 `rep=38` 在 `_r2` 与 `_r3` 各有一次独立执行，`p=0.327031`、`diff=-0.045608` 完全相同，`total_cpu_s` 168.72 vs 162.98。

**但要澄清两点**（文档的说法比事实强）：

1. 绝大多数"重复"不是"重跑得到同样结果"，而是 `--resume-from` 的**复制行**：`_r2_det` 的 250 行 = `_r2` 的 48 行原样拼接 + 202 行新算（`out/v3_phase_D_aa_formal_r2_det/L0/aa_manifest.json` 的 `resume_from` 即 `_r2/L0/aa_repetitions.csv`）。所以"一致"在很大程度上是构造使然，真正的独立重算证据只有 L3 rep38 这一类少数行。
2. **合并脚本本身不检查一致性**：`scripts/17_merge_aa_layers.py:91` 直接 `drop_duplicates(..., keep="last")`。我构造了"同 rep、p 值不同"的用例（5 个 rep 注入 p=0.001，其余 0.2），脚本无任何告警，静默取 last，合并 FPR 从 0.0 变成 0.020。

**顺序鲁棒性（补充验证）**：`keep="first"` 与 `keep="last"` 都得到 46/1000 —— 交付数据上去重顺序不影响结论。

**`protocol_config_hash` 校验的实际强度**（用临时目录构造 5 个用例跑 17）：

| 用例 | 结果 |
|---|---|
| A 四层同协议 | 通过（正确） |
| B L2 的 hash 不同 | `SystemExit`，列出两个 hash（**拦得住**） |
| C L2 缺 `protocol_config_hash` 列 | **通过**，并打印"协议指纹一致：HHHH…"（误导） |
| D L2 某行 hash 为 NaN | **通过**（`dropna()` 把该行排除在检查之外） |
| E 同 rep 不同 p | **通过**，静默 keep last |

即：`17_merge_aa_layers.py:103-111` 是**条件门禁**，fail-open。另外续跑端 `src/causal_growth/evaluation/v3_aa.py:958` 把 `config_hash` 列入"必需列"，但 964-967 只比较 `alpha` 与 `n_total`，**`config_hash` 从未被使用**——跨协议续跑会在续跑处静默通过，只靠 17 兜底。

### E3 15 格合并脚本的校验强度 —— **主体成立，但有 5 类篡改放行；退出码可用；无"失败仍写文件"路径**

**实测有效**（直接调用 `validate()`）：

| 篡改 | 结果 |
|---|---|
| 14 格（丢 L2 mde200） | 拒：`缺格: [('L2', 2.0)]` |
| 注入 L3 行 | 拒：`多余格（含 L3…）` |
| `n_reps=99` | 拒 |
| `achieved_effect_analytic` 偏 2e-6 | 拒 |
| `mc_se=NaN` | 拒 |
| 重复 `cell_id` | 拒 |

**实测放行**（这 5 条是缺口）：

| 篡改 | `validate()` 返回 |
|---|---|
| `n_total=1`（注册规模被换掉） | 0 问题 |
| `alpha=0.5` | 0 问题 |
| `rejection_rate = 1 - rate`（结论反向） | 0 问题 |
| `rejections=0` 与 rate 不一致 | 0 问题 |
| 同 `(level,multiplier)` 但不同 `cell_id` 的重复格 | 0 问题（`cell_id` 去重拦不住，格数按 `(level,mult)` 集合比对，不校验行数=15） |

**退出码**：`main` 返回 0/1，缺文件抛 `FileNotFoundError`（进程退出码 1）。可用于 CI。

**失败是否落盘**：我把 `OUT_CSV/OUT_JSON` 重定向到临时路径后喂 14 格 → `exit 1`，两个文件**都没有被创建**（校验在写入之前，`scripts/19_finalize_local_power.py:113-130`）。唯一的非原子点是 `to_csv`（:130）先于 `csv_sha256` 与 JSON（:146-149）：若 JSON 写失败，会留下"新 CSV + 旧 JSON"的不一致组合。

### E4 可复现指纹 —— **本机成立，跨机不完整**

- `provenance` 三路 `summary_sha256` 我逐一复算，全部匹配 `local_power_summary.csv` 现状；
  `csv_sha256 = cbb48822…` 与文件一致；`relative_deviation` 最大 `1.959e-15`（文档 §7.2 的 1.96e-15 准确）。
- **幂等**：重跑 `scripts/19_finalize_local_power.py` → 退出 0，CSV 与 JSON 的 `csv_sha256` 逐字节不变（`cbb48822…`），`git status` 干净。
- **17 的幂等**：CSV 逐字节相同；JSON 只在 `roots` 字段不同（交付件是绝对路径 `D:\…`，我以相对路径调用就变成 `out/…`）。→ 指纹随"怎么敲命令"变化，应统一成相对路径。
- **缺什么**：`provenance` 没有 run manifest 哈希、没有 Python/pandas/numpy 版本、没有源码哈希；去重记录（"读 338→250"）只在 stdout，**没有落进任何产物**——文档 §5 说的"去重记录"其实无法从产物核验，只能重跑。`local_power_manifest.json` 也没有 start/finish 时间。

### E5 性能与资源 —— **CPU 数字可信；墙钟被低估；三个本地资源项未记录**

实测（从 1000 行 AA 逐 rep 表与 1500 行功效格逐 rep 表直接统计）：

| 项 | 实测 | 文档 |
|---|---|---|
| AA 单 rep CPU | 均值 **155.4 s**、中位 166.7、p95 171.6（pipeline 占 154.9） | "约 3.0 分钟/rep"（偏高 ~15%） |
| AA 1000 rep 总 CPU | **43.2 CPU·h** | 未给 |
| AA 四层墙钟 | 快照 13:54 建立 → 最后一层 01:09 收口 ≈ **11.3 h**（250×2.6 min ≈ 10.8 h） | "四层并行约 9.4 小时"（与 3.0 min/rep 自相矛盾） |
| 功效格单 rep | 127–152 s CPU / 130–152 s wall（均值 135.7 / 138.2） | "约 2.3 分钟"（符合） |
| 三路墙钟 | 00:31 → 20:14 UTC ≈ **19.7 h** | "约 20 小时"（符合） |

**内存**：AA 侧的换页经历记录得相当细（`docs/v3_决策与反思日志.md:239-281`、`AGENT_HANDOFF.md:540-572`：RSS 0.96→2.2 GB、占空比 17%、四进程 8.5 GB、按 40 rep 复位），但**正式文档 `docs/v3_phase_D_aa_formal.md` 只有 §5 一句"因内存复位而分段"和 §6 局限 5**，没有峰值内存、没有并行度、没有"靠换页硬撑"的披露。

**功效格三路并行的内存**：**没有任何记录**。manifest 只有 CPU 秒；`docs/v3_phase_D_local_power.md:302` 只写"内存占用与 AA 正式作业同量级"。`out/c3_L*.log` 里没有 RSS/占空比采样，因此"三路并行期间是否也发生换页"**无法验证**——只能从"单 rep wall ≈ CPU、无明显膨胀"间接推断没有严重换页。

### E6 失败与重试的可见性 —— **不成立（跳过 rep 的风险可排除，但失败史不可重建，且有错误时间戳）**

**能验证的**：

- 每层 rep 集合 = {0..249}，**无缺口、无重复**（我按 `(level, rep)` 核对）；功效格 15×100 同样齐全。
- 环境重试在逐 rep 表里可见：AA 1000 行中 2 行 `file_lock_retries>0`、`source_retries` 全 0；功效格 `environment_retries` 合计 2（`L2_power_mde000`、`L2_power_mde050` 各 1），日志 `out/c3_L2.log:29` / `:230` 有对应行。
- `run_aa_rep` 只在成功后落 row（`v3_aa.py:984-985` flush），失败/被杀的 rep 不会留下"半条"结果，所以不会出现"跳过一个 rep 但还是 250"。

**不能验证的**：

- **AA 没有任何运行日志**（`out/` 下只有 `c3_L*.log` 是功效格的）；三次重启的 stdout 全部丢失。
- `v3_phase_d_aa_formal`、`_r2`、`_r3` 三个 root **没有 `aa_manifest.json`**（进程被杀时没走到 `write_outputs`），只有两个 `_det` 有。因此除最后一次重启外的参数（n / reps / 是否带负对照 / 起始 rep）只能靠文档叙述。
- 抖动期"丢了几个 rep 的开始"无法重建：没有 `*_attempt*` 目录、没有 manifest、没有日志。

**关于"384 次报废 / 1240 次"**：产物支持的是 **1384 行写入 = 1000 个不同 `(block,rep)` + 384 行重复**，且重复行绝大多数是 resume 复制（见 E2）。仓库里 `grep -rn "1240\|384"` 在文档中查不到任何出处。所以"1240 次里报废 384 次执行"这个表述**既不成立也无法追溯**；能确证的只是"写入 1384 行、逻辑上 1000 次"。

**另有一处会误导时间线重建的缺陷**：`v3_aa.py:1039` 的 `"started_at_utc"` 是在**全部 rep 跑完、构造 manifest 时**取的 `datetime.now()`。证据：`_r2_det/L0` 记 `2026-10-25T17:09:43Z`，而该 root 的 `aa_repetitions.csv` 最后写入时间正是北京时间 01:09（=17:09Z）。它是"结束时间"。按它算 D 阶段时长会得出荒谬结果。

### E7 测试覆盖的实质 —— **主体成立；门禁脚本零覆盖是实质缺口**

**关键不变量都覆盖了**，且断言非空：

| 不变量 | 位置 |
|---|---|
| 券成本恒 0 | `tests/test_v3_aa.py:267`（`coupon_cost_total == 0.0`），并有反例 `:306-317`（注入 `coupon_cost=5.5` → 抛"实际动作"） |
| 标签翻转 | `tests/test_v3_aa.py:319-335`（`treatment = 1 - label` → 抛"treatment 不等于输入的标签"） |
| R<2 时 MC_SE 报错 | `tests/test_v3_local_power.py:433-445`（`pytest.raises(ValueError, match="MC_SE")`） |
| 逐位可复现 | `tests/test_v3_aa.py:285-292`（比对 diff/p/se/n_label1/coupon_cost） |
| 续跑拒绝混批 | `tests/test_v3_aa.py:489-508`（**只测 n 与 alpha，没测 config_hash**） |
| 授权/错配拒绝 | `tests/test_v3_local_power.py:299-352` |
| estimator_warning | `tests/test_v3_local_power.py:533-557` |

**我定向跑了这两个文件**（`--basetemp` 指到仓库外）：**53 passed, 0 skipped, 61 s**，无空断言。

**缺口**：

1. **`scripts/17_merge_aa_layers.py`、`18_aa_status.py`、`19_finalize_local_power.py` 没有任何测试**（`grep -rln "19_finalize\|17_merge" tests/` 为空）。提交 `c2ebce9` 声称的"负面用例：缺格/L3/rep 数不符均被拒且不落盘"是**手工验证**，没有沉淀成回归测试——我这次探出的 5 条放行用例，正是这类测试应该拦住的。
2. `test_consistency_tolerance_is_enforced`（`tests/test_v3_local_power.py:195`）用 `pytest.raises(Exception)`，过宽，重构后可能永远绿。
3. 没有测试锁定"合并/汇总层的数值契约"（例如 `local_power_formal.csv` 的 sha256、行数、`cells=15`），所以门禁被削弱时无人报警。

### E8 可交接性 —— **不成立（照文档复现不出 15 格）**

一个没参与过的人按现有文档走，会在下面几处卡住：

1. **正式 AA 只有"怎么看结果"，没有"怎么产生结果"**。`docs/v3_phase_D_aa_formal.md:74` 只给 `python scripts/18_aa_status.py` 与 `17_merge_aa_layers.py`。产生这 1000 次的命令（`--layers` / `--reps 250` / `--n 200000` / `--run-root` / `--resume-from` / `--no-negative-control` / `PYTHONPATH` 指向快照）只在 `AGENT_HANDOFF.md:33-36, 601` 的片段里，且那是"续跑"片段，不是"从零起跑"。
2. **15 格只有一条会跑错的命令**。`docs/v3_phase_D_local_power.md:411-412`：

   ```
   python -m causal_growth.data.v3_local_power_pipeline --reps 100 --n 200000 --reference-n 200000 --out out\v3_phase_d_local_power\formal
   ```

   照它跑：**20 格全跑（含 L3 的 5 格）**、**单进程串行（≈78 CPU·h，不是 20 h）**、**不在快照上（没有 `PYTHONPATH`）**。实际执行是 3 个进程 `--layers L0|L1|L2 --out .../formal_LX`，这个分路方式在正式文档 §7 里只写了一句"三路按层并行"，没有命令。
3. **快照本身不在版本库**（E1-2）。新机器拿不到 `463b624c…` 的字节；39/40 与 HEAD 相同，但决定结果的那 1 个（`v3_data_checks.py` 的锁语义）与 AA 的 6 个差异无法完整重建。
4. **环境变量纪律分散**：`OMP_NUM_THREADS/OPENBLAS/MKL` 只写在 `docs/v3_phase_D_local_power.md` 的复现小节，正式文档没有；`--basetemp`、`PYTHONUTF8` 同理。
5. **19 的默认 roots 是硬编码**（`scripts/19_finalize_local_power.py:44` `formal_L0/L1/L2`），文档没说"必须与运行时的 `--out` 对齐"，也没说换目录要传 `--roots`。

## 3. 必须修复的问题（按严重度）

**S1-1｜清理脚本会删掉合并所依赖的 4 个 run-root** — `scripts/16_cleanup_scratch.py:37`（`OBSOLETE_PREFIXES` 含 `"v3_phase_d_aa"`）+ `:42-48`（`PROTECTED_NAMES` 只保护 `v3_phase_d_aa_formal`）。
实测 `is_obsolete()`：`v3_phase_d_aa_formal_r2` / `_r3` / `_r2_det` / `_r3_det` 全部 `True`。而 `17` 的 `keep="last"` 恰好取 `_det` 的行——删掉后只剩每层 40/48/39 行，池化 FPR 直接不可重建。
修：把 5 个 root 全部加入 `PROTECTED_NAMES`（或改成"只删显式列出且不在证据清单里的目录"）。

**S1-2｜门禁证据全部未入库** — `.gitignore:66`（`out/`）。
`out/c3_snapshot_binding.json`、`out/aa_snapshot_binding.json`、`*_det/*/aa_manifest.json`、各级 `aa_repetitions.csv` / `local_power_repetitions.csv` 均 untracked。这意味着文档引用的 `463b624c…` / `0a087a1b…` 在一台干净机器上**不可获取**。
修：把两个 binding json 与逐 rep 表（或至少"文件→sha256"清单 + 行数 + 摘要统计）落到 `outputs/tables/` 下并提交；`aa_snapshot_binding.json` 补逐文件哈希（对齐 c3 的格式）。

**S2-3｜17 的去重没有任何一致性断言** — `scripts/17_merge_aa_layers.py:91`。
构造"同 rep 不同 p"即静默取 last（我实测把 FPR 从 0.0 改成 0.020）。文档 §5 的"逐位一致"目前靠运气，不靠代码。
修：`drop_duplicates` 之前按 `(block,rep)` 分组，对 `*_p_value` / `*_diff` / `*_se` / `n_*` 断言 `nunique()==1`，不一致直接 `SystemExit`（并保留两个 root 名）。

**S2-4｜17 的协议门禁 fail-open** — `scripts/17_merge_aa_layers.py:103-111`。
缺列 → 跳过检查；NaN → `dropna()` 把该行排除；两种情况都还会打印"协议指纹一致"（实测）。
修：`protocol_config_hash` 列不存在即拒绝；`isna().sum() > 0` 即拒绝；提示语仅在真的全量校验通过后打印。

**S2-5｜19 的校验缺 4 条，且有 5 类篡改可放行** — `scripts/19_finalize_local_power.py:72-101`。
建议补：`n_total` 必须为注册 200000；`alpha` 必须 0.05；`rejections == round(rejection_rate*n_reps)` 且 `n_reps==len(rep_id)`；`(level,multiplier)` 行数必须恰好 15（现在是集合比对，不同 `cell_id` 的重复格可通过）。

**S2-6｜续跑不校验配置指纹** — `src/causal_growth/evaluation/v3_aa.py:958`（`config_hash` 列入必需列）与 `:964-967`（只比 alpha / n_total）。
修：加 `if not resumed["config_hash"].eq(str(protocol...)).all(): raise`，或按 `scenario_id` 分组比对。

**S3-7｜`started_at_utc` 记的是结束时间** — `src/causal_growth/evaluation/v3_aa.py:1039`。
`_r2_det/L0` 记 `17:09:43Z` = 该 root 的 CSV 最后写入时刻。修：在 `run_root.mkdir` 处取一次时间，manifest 同时写 `started_at_utc` / `finished_at_utc`（`local_power_manifest.json` 两个都缺，一并补）。

**S3-8｜`nominal_power` 在零效应格给 α/2，与"名义拒绝率"的说法矛盾** — `src/causal_growth/design/v3_power.py:532`（docstring 称"α/2…正是完整 AA 要检验的量"）、经 `src/causal_growth/data/v3_local_power_pipeline.py:719-722` 写入 CSV。
实测 3 个 `mde000` 格的 `nominal_power = 0.025000`，而双侧 Welch t 在零效应下的拒绝率是 0.05。于是 CSV 的 `measured_minus_nominal` 给出 `0.04−0.025=+0.015`（看起来像 size 膨胀），而文档 §7.3 用的是 α=0.05（`0.04 vs 0.05`，看起来正常）。**表与文互相矛盾**，且这一列不在 19 的校验范围里。
修：要么把该列改名为 `nominal_power_one_sided`，要么在 δ=0 处返回 α，并在文档 §7 明确 `measured_minus_nominal` 的口径。

**S3-9｜写盘非原子 / 指纹随命令变化** — `scripts/19_finalize_local_power.py:130-149`（先写 CSV 再算 sha、再写 JSON，无 tmp+replace）；`scripts/17_merge_aa_layers.py:182`（`roots` 记原始入参字符串）。
修：两处都用 `*.tmp → os.replace`；`roots` 统一 `relative_to(ROOT).as_posix()`。

**S3-10｜文档数字自相矛盾** — `docs/v3_phase_D_aa_formal.md:73`（"约 3.0 分钟/rep" + "四层并行约 9.4 小时"）。
实测 155.4 s/rep（中位 166.7），250×2.6 min ≈ 10.8 h，快照 13:54 → 收口 01:09 ≈ 11.3 h。两者必有一错，建议改为"2.6–2.8 分钟/rep、四层墙钟约 11 小时（含换页抖动与两次重启的停机）"。

**S3-11｜正式文档缺"资源与失败"披露** — `docs/v3_phase_D_aa_formal.md` §5/§6。
建议补一小节：三路并行的内存未采样；AA 期间触发换页、按 40 rep 复位、两次重启；重启无日志、前三个 root 无 manifest；以及"384 行重复"的正确定义（等于 resume 复制行，不等于报废执行）。

## 4. 可放行的部分

以下结论我复算过，可以按现状引用：

1. **AA 1000 次**：`46/1000 = 0.0460`，CP95 `[0.0339, 0.0609]`，含 0.05；逐层 14/11/10/11；SE 校准 `0.9948`（逐层 0.987/0.994/0.988/0.995）。我用原始逐 rep 表独立重算，与 `v3_phase_D_aa_formal_merged.csv` 逐项一致；`keep=first` 与 `keep=last` 结果相同；`alpha`、`n_total`、`config_hash`（按场景）在 1000 行内唯一。
2. **逐 rep 完整性**：四层各 250 个 rep，`0..249` 无缺口无重复；功效格 15×100 齐全，`n_total=200000`，`n_reps=100`。
3. **15 格功效表的构造正确性**：`achieved_effect_analytic` 与 target 最大绝对偏差 `2.22e-16`、最大相对偏差 `1.96e-15`；`achieved_effect`（实测均值）与 target 最大绝对差 `0.0059`（L1 mde200，2.3%），属 MC 误差而非构造偏差，文档 §7.2 的读法正确。
4. **幂等**：19 重跑后 `csv_sha256` 不变；17 重跑后 CSV 字节相同（JSON 仅 `roots` 字段随调用方式变化）。
5. **provenance**：三路 `summary_sha256` 与 `csv_sha256` 全部复算通过。
6. **测试**：`tests/test_v3_aa.py` + `tests/test_v3_local_power.py` 共 53 项，定向运行 green、0 skipped、61 s；关键不变量（券成本恒 0、标签翻转、R<2 抛 MC_SE、逐位复现、续跑拒绝混批、授权错配拒绝）都有实质断言。
7. **统计读法**（不是数字本身）：边界格零余量单列、"覆盖率 ≡ 1−FPR 不是独立证据"、负对照不得当 AA、L3 的未调整 ITT 不是 ATE —— 这几条在 `docs/v3_phase_D_aa_formal.md` §2/§4/§7.4-7.5 里写得准确，与代码实现一致。

**明确无法验证的项**（缺证据，不是"没问题"）：

- 功效格三路并行期间的峰值内存与占空比（无采样、无日志）；
- AA 三次重启各自丢弃了多少未完成的执行（无日志、无 attempt 目录、前三个 root 无 manifest）；
- "1240 次里报废 384 次"的原始出处（仓库内无记录）；
- 跨机器数值可复现性（BLAS/线程数/pagefile 差异；快照未入库，无法在另一台机器上重建同一字节）。
