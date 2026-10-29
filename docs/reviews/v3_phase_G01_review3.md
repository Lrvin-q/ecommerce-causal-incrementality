# Phase G01 第三轮窄复评：5 条 P2 关闭确认（独立复评）

> 合成数据 / 已知 DGP。复评时间：**2026-10-29 10:56（北京时间）**。
> 被评对象：提交 `daf9d80`（2026-10-29 10:44:36，标题「G|g02: 冻结帧改用模型无关指纹；导出改原子换名；G01 复评 5 条 P2 全关」）。
> 复评期间 HEAD 已前移到 `deab211`；经 `git diff daf9d80..HEAD -- <五个被评文件>` 确认
> `scripts/33|37|40|41`、`src/.../v3_g_matrix.py`、`docs/v3_phase_G01_formal.md`、`docs/v3_phase_G_run_registry.md` 在 `daf9d80` 之后**未被再改**，
> 唯一变动的是 `scripts/39` 与 `tests/test_v3_g02_frozen_frame.py`（`f5a3e52`，见 §3.3）。
>
> **范围**：只确认上一轮 `docs/reviews/v3_phase_G01_review2.md` 之后主控自列的 5 条 P2 是否真关闭，
> 以及修复本身有没有引入新错误（尤其是否削弱了校验器）。**没有**重新评审整个 G01，不提新的大范围需求。
>
> **身份与纪律**：独立复评（非产出者）。未改任何 `src/`、`sql/`、`configs/`、`scripts/`、`outputs/evidence/**`、`GOAL.md`、`TODO.md`、被评报告；
> 未跑任何 R>0 的数据作业（本机 G02 正式重跑在跑，刻意避让）。读取 + 单进程 pandas + 小型 pytest；
> 所有临时产物只落 `out/review3_tmp/`（自建夹具、模拟脚本、复算脚本），报告是唯一写入的仓库文件。
>
> **口径**（本评审自定，不照抄实现）：带外概率 `Φ((lo−p)/se)+1−Φ((hi−p)/se)`，`se=√(p(1−p)/R)`；
> 「可比数值/布尔列」= 两表共有列去掉 `level`/`rep` 与 8 个字符串列（含 D02 侧为 `str` 的 `retry_attempt_dirs`）。

---

## §1 结论

**5 条 P2：5/5 关闭。新增 P0/P1：0。新增 P3：4 条（全是文字/标签级，不改任何数字结论，也不需要重跑）。**

| 编号 | 内容 | 判定 | 一句话依据 |
|---|---|---|---|
| P2-1 | 33 号反向校验覆盖目录级白名单 | **CLOSED** | 未登记 `runs_summary.json` 时新代码 exit 2、旧代码 exit 0（同一夹具对照）；真树 `--dry-run` exit 0、91 条全表复算一致、不写盘 |
| P2-2 | 37/40/41 导出「暂存 → 校验 → 备份 → 原子换名」 | **CLOSED** | 3 例回滚测试通过；自建模拟复现 37/40 四种路径（失败保旧/原异常、成功留时间戳备份、坏 JSON 不换名）；41 静态核对同构 |
| P2-3 | §3 功效带与值、GOAL 91%/60% 来源 | **CLOSED** | 表头改 `[0.035,0.065]`、值改 0.81；merged 列实值 0.813364/0.959807 与我独立重算逐位相同；`[0.037,0.065]` 的 0.8151/0.9598 已明写「不属于表中任何列」 |
| P2-4 | §5.1 `config_hash` 与统计列措辞 | **CLOSED** | 两侧 4 个逐层 `config_hash` 全部逐字符复现；60/69、8+1 运行期列、3 个字符串列、`source_root` 仅 D02 全部复现 |
| P2-5 | 注册表/TODO 旧数 | **CLOSED** | 59 登记 / 60 磁盘 / 1 275 048 B、91 条 / 16 964 194 B、耗时五分位与极值全部从证据文件复算命中；旧数只以「时点补记」形式保留 |

**新增 P3（不影响关闭判定）**：

- **N-1（P3，文字）** §3 脚注「60% 对应**单侧** z 近似……的 **0.5855**」：0.5855 只与**双侧** z 近似相符（我算 0.58570，`n=250`、`se=√(0.05·0.95/250)`、`z_{α/2}=1.96`）。
  真正的**单侧**近似是 0.7024（用 `z=1.645`）或 0.5413（`se` 取 0.08）。建议把「单侧」改为「双侧」，数值 0.5855→0.5857 或注明舍入。
- **N-2（P3，文字）** 同一脚注把 GOAL 的「检出 FPR≥0.09 的把握约 **91%**（**合并**）」映射到 merged 列 **R=250** 的 0.9176。
  按 GOAL 原文「合并」= 1000 次，对应值是 **0.9971**。报告已把两个值都印在同一句里（不构成误导），但「91%↔R=250」这一步与 GOAL 的限定词冲突，建议写成条件句（「若 91% 指每层 250 次则 0.9176；若指合并 1000 次则 0.9971」）。
- **N-3（P3，文字）** `docs/v3_phase_G01_formal.md:105` 仍写「`all_repetitions.csv` **1 000 行**唯一」。该文件实为 **1 384 行**（按 `(level,rep)` 去重后 1 000）；`protocol_config_hash` 在全 1 384 行上恒为 1 个值，「行数」写错但不影响「唯一」结论。
- **N-4（P3，工程）** 三份导出脚本的备份命名不统一：37 号 `g01_evidence_bak_20261029104739`（`%Y%m%d%H%M%S`），40/41 号 `g02_evidence_bak_20261029T104739+0800`（ISO 派生，带 `T` 与 `+0800`）。
  另：失败时 `out/g0X_evidence_staging` 会留下（下次运行先 `rmtree`，属有意保留现场），但没有任何文档说明，建议在脚本 docstring 里点一句。

---

## §2 逐条核验

### P2-1　33 号反向校验覆盖 `DIR_EXTRA_IDENTITY` —— **CLOSED**

**代码事实**（`scripts/33_register_evidence_top.py:305-314`）：

```python
indexed = {rec["rel"] for rec in normalized}
extra_names = set(DIR_EXTRA_IDENTITY.get(subdir, {}))
on_disk = sorted(
    rel for rel in (p.relative_to(d).as_posix() for p in d.rglob("*.json"))
    if (_is_identity(rel) or rel in extra_names) and rel not in indexed
)
for rel in on_disk:
    bad.append(f"{subdir}/{rel}: 磁盘上存在身份类文件，但目录级 coverage.json 未登记")
```

只加不减：`_is_identity(rel)` 的条件保留，`or rel in extra_names` 与 `DIR_EXTRA_IDENTITY` 的键（现仅 `g01_aa250 → runs_summary.json`）对齐。

**自建夹具（不碰真树）**：把 `outputs/evidence/g01_aa250` 整目录（60 文件 / 59 条目录级记录）复制到 `out/review3_tmp/fixture_ev/`，顶层用空表 `out/review3_tmp/top.json`。

| 场景 | 命令（`PYTHONUTF8=1 .venv/Scripts/python.exe`） | 结果 |
|---|---|---|
| 正例 dry-run | `scripts/33 … --evidence-root out/review3_tmp/fixture_ev --top out/review3_tmp/top.json --dirs g01_aa250 --dry-run` | **exit 0**；候选 **14** 个（12 manifest + binding + `g01_runs_summary`），`total_bytes_after=40138` |
| 正例写盘 | 同上去掉 `--dry-run` | exit 0；`records 0 → 14`，`total_bytes 0 → 40138`；重跑「无新增、无字段补齐，不写盘（幂等）」 |
| **反例 A（本轮重点）** | 复制真目录后删掉目录级记录里的 `runs_summary.json`（**磁盘文件仍在**） | **新代码 exit 2**：`g01_aa250/runs_summary.json: 磁盘上存在身份类文件，但目录级 coverage.json 未登记` |
| 反例 A 对照（旧代码） | `git show daf9d80^:scripts/33… > out/review3_tmp/33_old.py`，同一夹具同一参数 | **旧代码 exit 0**，只报 13 个候选（`runs_summary.json` 被静默漏掉） |
| 反例 B（存量检查） | 删 `per_rep/s09__L2__aa_manifest.json` 记录 | exit 2（manifest 命中 `*manifest*.json`） |
| 反例 C（反向的另一半） | 删磁盘上的 `runs_summary.json`、保留记录 | exit 2：`文件缺失，目录级索引已过期` |

→ 「改前漏、改后拦」在同一夹具上被直接对照出来，**不是**只看声明。

**`--dry-run` 不写盘（实测）**：`out/review3_tmp/top.json` 在「建表 → dry-run → 写盘」三段 sha256 为
`1db18ef2…`（建表后 = dry-run 后，用同内容重建文件复算得同一 sha）→ `238e14f1…`（写盘后）→ 幂等复跑不变。

**真树 dry-run**：

```
[top-reg] 证据根 outputs/evidence；扫描 10 个子目录：d01_pilot, d03_formal, …, g01_aa250, g_aa_smoke, g_smoke
[top-reg] 候选身份类文件 40 个：新增 0，已登记 40
[top-reg] 顶层全表复算一致：91 条
[top-reg] 无新增、无字段补齐，不写盘（幂等）
EXIT=0
```

`outputs/evidence/coverage.json` 前后 sha256 均 `f3e8b0db50561ce3…`、mtime 均 `2026-10-29 10:06:20`、大小 64 208 B → **零误报、零写盘**。

备注：上一轮的旧夹具 `out/review_g01_round2/fixture_ev`（58 条记录、缺 `runs_summary.json` 那条）在新代码下 exit 2，原因正确；
它与 `TODO.md:31` 记的「反例当场 exit 2」一致，不是回归。

### P2-2　37/40/41 导出回滚 —— **CLOSED**

**实现（三份同构）**：`staging 目录 → _write_evidence → json.loads(coverage.json) → （旧 DEST 改名为 *_bak_<时间戳>）→ staging.rename(DEST)`。

- `scripts/37:156-183`：`global DEST` 临时指向 `out/g01_evidence_staging`；`except BaseException: DEST = real; raise`（**先还原全局再原样抛**，不再有「清理异常掩盖原异常」）。
- `scripts/40:132-157`：逐行同构（`out/g02_evidence_staging`）。
- `scripts/41:272-281`：不换 `DEST`，把 `dest` 当参数传给 `_write_evidence`（其首行 `dest.mkdir(parents=True, exist_ok=True)`），
  校验 `coverage.json` 后再改名；没有 `try`，失败时 `dest` 根本未被触碰、异常直接冒泡。**行为与 37/40 等价，写法更简。**

**测试**：`.venv/Scripts/python.exe -m pytest tests/test_v3_g02_export_rollback.py tests/test_v3_g02_frozen_frame.py --basetemp C:/cg_t -q` → **9 passed**（回滚 3 例 + 冻结帧 6 例）；
另加 `tests/test_v3_g_matrix.py tests/test_v3_f01_registry.py` 一起跑 **26 passed**。

**自建模拟**（`out/review3_tmp/sim_rollback_37_40.py`，把 `ROOT`/`DEST` 指到 `out/review3_tmp/sim_rollback/*`，只替身 `_write_evidence`）：

| 场景 | 37 号 | 40 号 |
|---|---|---|
| A 旧 DEST 存在 + 写失败 | `Boom: write failed` 原样抛出；DEST 只剩 `old.txt`；无备份；无半写 | 同 37 |
| B DEST 不存在 + 写失败 | 异常仍是 `Boom`（**不再被 `FileNotFoundError` 掩盖**）；DEST 仍不存在 | 同 37 |
| C 成功 | DEST = 新内容；旧目录存为 `out/g01_evidence_bak_20261029104739/`（含 `old.txt`），**未删** | 同 37，备份名 `out/g02_evidence_bak_20261029T104739+0800/` |
| D `coverage.json` 不可解析 | `JSONDecodeError`；DEST 原样保留 | 同 37 |

**回归**：`scripts/37 … --check` → `逐 rep 行=1000；重算 15 格；不一致 0`，exit 0（证明这次改写没破坏 37 号的复算通道）。
`py_compile` 五个脚本（33/37/39/40/41）全通过。

### P2-3　§3 功效带与值 —— **CLOSED**（脚注里有两处新 P3，见 N-1/N-2）

**报告现状**（`docs/v3_phase_G01_formal.md:37-51`）：表头「解析功效（真值 0.08，带 [0.035, 0.065]）」，四层 0.81、POOLED 0.96；
脚注写明该列 = merged 的 `detect_power_if_true_0_08`（17 号默认带 `[0.035,0.065]`），R=250 **0.813364**、R=1000 **0.959807**；
GOAL 带 `[0.037,0.065]` 手算 **0.8151 / 0.9598**「**都不是表里的列**」；并交代 GOAL 的 91%（`detect_power_if_true_0_09` 0.9176 / 0.9971）与 60%（0.5855）。

**我自算（`scipy.stats.norm`，公式同上）**：

| 带 | R=250 | R=1 000 |
|---|---|---|
| `[0.035,0.065]`（表头/列） | **0.813364** | **0.959807** |
| `[0.037,0.065]`（GOAL 带，脚注手算） | **0.815105** | 0.959807 |
| `[0.035,0.065]`、真值 0.09 | **0.917585** | **0.997132** |

**证据文件对照**：`outputs/evidence/g01_aa250/merged/v3_phase_D_aa_formal_merged.csv` 15 行中，
`detect_power_if_true_0_08` = 0.813364（L0/L1/L2/L3 四行）、0.959807（POOLED 行）；
`detect_power_if_true_0_09` = 0.917585 / 0.997132。**逐位相同，无一处需要舍入解释。**

上一轮被指为假的那句「即 merged 表…列」已被替换为「该列用…带…，R=250 值…R=1 000 值…」，且把「0.8151 不是表里的列」显式写出 —— 报告里不再有 0.81/0.82 并存的矛盾。

残留问题只有标签（N-1「单侧」应为「双侧」、0.5855 vs 0.5857）与 GOAL「（合并）」的映射歧义（N-2）。

### P2-4　§5.1 `config_hash` 措辞 —— **CLOSED**

**报告现状**（`:100-107`）：60/69 统计列逐比特相同；9 个运行期列（8 个 `*_cpu_s`/`*_wall_s` 最大差 60.5 s + `file_lock_retries` 最大差 1）；
3 个字符串列不同；`source_root` 仅 D02 有；两侧 `config_hash` **各 4 个值、每层 1 个**并逐层列名。

**我的复算**（`out/review3_tmp/recompute_51.py`：G01 = 12 张 `per_rep/*__aa_repetitions.csv` 共 1 000 行；D02 = `outputs/evidence/aa/all_repetitions.csv` 1 384 行按 `(level,rep)` 去重 1 000 行）：

| 项 | 实测 | 与报告 |
|---|---|---|
| 行数 / 连接 | G01 1 000、D02 1 384→1 000；both 1 000 / left_only 0 / right_only 0 | 一致 |
| 列集合 | 共有 79 列；仅 D02 有 `source_root`；G01 无独有列 | 一致 |
| 可比列 | 79 − 2（`level`/`rep`）− 8（字符串列，含 `retry_attempt_dirs`）= **69**；其中 **60 列 max\|Δ\|=0**、9 列非零 | 一致（60/69） |
| 9 个非零列 | `total_wall_s` 60.5349、`pipeline_wall_s` 60.3755、`total_cpu_s` 60.3594、`pipeline_cpu_s` 60.2031、`dgp_cpu_s` 1.4844、`dgp_wall_s` 1.4684、`itt_cpu_s` 0.046875、`itt_wall_s` 0.0368972、`file_lock_retries` 1 | 一致（最大 60.5 s、1 次） |
| 字符串列 | `source_label/block/scenario_id/run_id/stream_prefix` 1 000/1 000 相同；`config_hash`、`protocol_config_hash` 1 000/1 000 不同；`retry_attempt_dirs` D02 有 2 个非空、G01 全空 | 一致（3 个不同） |
| D02 指纹 | protocol `30511a32bcee9db5…`（1 个值）；`config_hash` L0 `1d0d83c5…`/L1 `7ab83d75…`/L2 `d5266240…`/L3 `2671bded…` | 一致 |
| G01 指纹 | protocol `00723dc26df517b2…`；`config_hash` L0 `a0eb214e…`/L1 `8a36a14b…`/L2 `c07d2f02…`/L3 `59958e1d…` | 一致 |

**「运行前后哈希」与「快照绑定值」的区别**：写在 §2「源码/配置」行（`:28`）与 §6.6（`:122-123`），不在 §5.1——
「快照 49 文件绑定 `526ff53d…`；运行期可核的 `v3_g_matrix.py` 值为 `fd3ca127…`（快照值）；**没有运行期前后 `pipeline_source_hashes()` 落盘**，故『全程未变』只能按快照与补丁时点推断」。
我实读 `binding/snapshot_binding.json`：`n_files=49`、`source_hashes["src/causal_growth/evaluation/v3_g_matrix.py"]` 前缀 `fd3ca127`、`git_commit=null`；
`runs/s01__g_aa_run_summary.json` 的 `snapshot_binding = {source_hashes_sha256: 526ff53d…, n_files: 49}` —— 说明「运行期可核」指的是分片运行时记录了绑定哈希，**不是**运行前后两次现算，措辞成立但建议在 §5.1 也加一句区分（`config_hash` 是逐层 YAML 配置哈希、`binding` 是源码文件哈希）。

残留：N-3（`:105`「1 000 行唯一」应为 1 384 行）。

### P2-5　注册表 / TODO 旧数 —— **CLOSED**

**证据文件实测**：

| 项 | 实测 | 出处 |
|---|---|---|
| 目录级登记 | **59** 条（其中 9 条非身份类记录——`coverage_check.json`、merged 两件、logs 三件、scripts 两件、`recomputed_fpr.csv`——无 `kind`，属增量导出时的存量写法，不影响身份类登记） | `outputs/evidence/g01_aa250/coverage.json` |
| 目录级磁盘 | **60** 个文件，合计 1 299 121 B；减 `coverage.json` 24 073 B = **1 275 048 B** | `find`/`stat` + 上述 json |
| 顶层 | **91** 条，`total_bytes` **16 964 194** = 逐条 bytes 之和 | `outputs/evidence/coverage.json` |
| `registry_repairs` | **17** 条，末条 `2026-10-29 10:06`，89→91 | 同上 |
| 成本 | `total_cpu_s` min **128.672** / p5 **134.324** / 中位 **136.594** / p95 **141.815** / max **181.375**；Σ 137 931.22 = 38.314 CPU·h；[132,137] 占 **67.40%** | G01 1 000 行逐 rep 表 |

**文档现状**：`docs/v3_phase_G_run_registry.md:25-26` 写「中位 136.594、p5–p95 134.324–141.815、min–max 128.672–181.375、67.4%」，
并把「132–135 s/rep」标成「此前写的…是 6 路前的估计，不是实测分布」；`:143` 写「05:16 时点 77→89、16.92 MB；10:06 后 91 条 / 16 964 194 B」；
`:145` 写「59 条登记 / 60 个磁盘 / 1 275 048 B」。`TODO.md:196-200` 现状块写「59 登记 / 60 磁盘 / 1 275 048 B」「91 条 / 16 964 194 B」，
并把上一轮被证伪的「D02 逐 rep 未归档」改为「已归档 `outputs/evidence/aa/all_repetitions.csv`，1 000/1 000 逐 rep 可比，60/69 max|Δ|=0」。

**旧数残留检查**（`grep`）：`132–135`、`45 文件 / 1.3 MB`、`77→89`、`16.92 MB` 只出现在
① 注册表/导出的「此前写…」「05:16 时点」「05:35 时点」历史补记；② TODO 的历史条目（`:93`、`:147`，记的是 05:19/05:35 那次措辞修正）；③ 上一轮评审自身。
**现状块里已无旧数作为现值**。

一点说明：任务清单里的「耗时三分位」只落在注册表（与报告 §2），`TODO.md` 的 G01 现状块没有复述（TODO 是进度源，成本以注册表为准），不按未关闭处理。

---

## §3 附加检查

### 3.1 39 号的冻结指纹是否只含模型无关内容 —— **是**

- `validation_frame_hash = dataframe_sha256(users)`（`v3_g_matrix.py:747`），`users = generate_covariates(cfg, rep_id, n_validation, population_kind="validation").users` —— 只由 `(cfg, rep_id, n)` 决定。
- `validation_arm_hash = dataframe_sha256(assignment[["user_id","assigned_policy_arm","policy_arm_probability"]])`（`:748-750`）。
  逐来源核对：`user_id` 由 `score_validation_users` 用 `users["user_id"].to_numpy()` **按原顺序**构造（`v3_f02.py:247-255`，无排序/过滤）；
  `assigned_policy_arm = draw_policy_arms(n, cfg, rep_id)`（`v3_f02.py:285`）只读 `cfg` 的三臂名/概率与 `child_rng(master_seed,"f02.arms",rep_id)`；
  `policy_arm_probability` 是配置常量按臂查表（`:319-329`）。**三列都不含 `tau_hat/cost_hat/issued_action`。**
- `issued_action` 被刻意排除（注释 `:745-746`），它才是与模型相关的列。

**实测（`out/review3_tmp/fp_check.py`，n=400、R=0、内存作业，不写盘）**：同一 `rep_id=0` 的验证臂，用 `history_rep` 0/1 各建一次历史+拟合（`constant`）：

```
history_rep 0: frame b6b04a1eb1bae8d1  arm f7460c6cbd93f2d3  observed afcc9cd622b46066  freeze 8379458cac39187f
history_rep 1: frame b6b04a1eb1bae8d1  arm f7460c6cbd93f2d3  observed 9777b94d1acc2462  freeze 1d52b809deed921d
frame 相同: True | arm 相同: True | observed 相同（旧指纹）: False | freeze 相同: False
```

即：新指纹对模型不敏感，旧指纹（含 `issued_action` 的观测表哈希）**确实**会随模型变 —— 10:26 那次「4 格在 b=1 全灭」的根因诊断成立，改法正确。
`tests/test_v3_g02_frozen_frame.py` 现有 **6 例**（不是 3 例，`f5a3e52` 又加了 merge 的 3 例），全部通过。
现场核对：`out/g02_retrain/*/repetitions.csv` 四格已各有 1 行（b=0），均带 `validation_frame_hash`/`validation_arm_hash` 列，说明 10:39 重开的进程确实跑在新代码上。

> 一句风险提示（不构成缺陷）：守卫不再约束 `issued_action`，若将来出现「同一 b 的 `issued_action` 非确定性」的 bug，日志里只会看到 `validation_observed_hash` 逐 b 不同而不会被拦。
> 现有 `validation_observed_hash` 仍逐 b 落表，事后可审计；若要更严，可加「本 b 的 `observed` 与用本 b 模型重算的哈希一致」的自检。

### 3.2 `daf9d80` 的 diff 有没有削弱校验 —— **没有**

`git show daf9d80 | grep -E "^[-+].*(warn|raise|SystemExit|continue|pass$)"` 与逐文件通读的结论：

- 新增的 raise/SystemExit：`_frozen_seen`（旧表缺列 → `SystemExit`）、`check_frozen_validation`（指纹漂移 → `RuntimeError`）；**没有任何 `warn`**（全 diff 无 `warn` 字样）。
- 被删的断言只有两处，且都是**错的不变量**：39 号的 `validation_observed_hash` 逐 b 相等（`:833-834`）、40 号 `check_cell` 的同名列唯一性（`:852`）。
  每处都被**两条**正确断言替换（`validation_frame_hash` + `validation_arm_hash`，且 40 号还加了「缺列即 problem」）→ **净加强**。
- 阈值/门禁：`band-*`、`alpha`、`n_total`、`FPR/CP` 相关常量**未被触碰**（17/19 号脚本不在本次改动文件列表里）。
- 导出路径：删掉的是「`rmtree` 旧备份 + 失败时用备份覆盖」的编排，替换为 staging/原子换名；**证据文件校验一条没少**。
- 33 号：唯一一行改动是**扩大**反向过滤集合（见 P2-1 的旧/新对照）。

### 3.3 复评期间的新提交（不在 5 条范围，但与「G02 能否成立」直接相关）

- `f5a3e52`（10:47）修了 **39 号 `command_merge` 里同一处坏指纹**（原断言 `validation_observed_hash` 唯一，50 个 b 必不相同 ⇒ 19:30 合并不可能成功）。
  新 `check_merge_frame`：`b` 不重复 + 两个新指纹跨 b 唯一 + 缺列即 `SystemExit`，并补 3 个测试用例。**这是必须的**，否则 G02 收尾必败。
- 我核对了 `out/g02_post.sh`：合一是**独立进程**调用 `python scripts/39 … merge out/g02_retrain`，因此 10:39 起跑的那批进程会在收尾时用上新代码，不存在「旧代码已加载到进程里」的死结。
- `deab211`（10:48）只改 `AGENT_HANDOFF.md` / `TODO.md`，不涉及被评文件。

---

## §4 复算表（本轮全部实测值）

| 项 | 本评审批 | 报告/注册表 | 差 |
|---|---|---|---|
| 带外概率（0.08，[0.035,0.065]） | 0.813364 / 0.959807 | 0.813364 / 0.959807 | 0 |
| 带外概率（0.08，[0.037,0.065]） | 0.815105 / 0.959807 | 0.8151 / 0.9598（明写不在表中） | 4e-5（舍入） |
| `detect_power_if_true_0_09` | 0.917585 / 0.997132 | 0.9176 / 0.9971 | 1e-4（舍入） |
| GOAL 60% 的重算 | 双侧 0.58570；单侧 0.70249 | 「单侧…0.5855」 | 标签错 + 2e-4（N-1） |
| 逐 rep 连接 | both 1 000 / 0 / 0 | 同 | 0 |
| 统计列相同 | 60/69（9 个非零） | 60/69 | 0 |
| 最大运行期差 | `total_wall_s` 60.5349 | 60.5 s | 0.03（舍入） |
| `config_hash` 四值（D02/G01） | 与报告逐字符相同 | 同 | 0 |
| `source_root` | 仅 D02 | 同 | 0 |
| 目录级登记 / 磁盘 / 字节 | 59 / 60 / 1 275 048 | 59 / 60 / 1 275 048 | 0 |
| 顶层 条数 / `total_bytes` | 91 / 16 964 194 | 91 / 16 964 194 | 0 |
| `total_cpu_s` 中位 / p5 / p95 / min / max | 136.594 / 134.324 / 141.815 / 128.672 / 181.375 | 同 | 0 |
| [132,137] 占比 | 67.40% | 67.4% | 0 |
| `all_repetitions.csv` 行数 | **1 384**（去重 1 000） | 「1 000 行唯一」 | 行数写错（N-3） |

---

## §5 局限

1. **只读 + 小作业**：全轮只有 pytest（`--basetemp C:/cg_t`）、33 号 dry-run/夹具演练、37 号 `--check`、以及 n=400 的两次 `run_validation_arm`（R=0、内存、不写盘）。
   未跑 `scripts/34|36|37|39|40|41` 的正式路径，未触发任何 R>0 数据作业；G02 正式重跑（10:39 起）全程避让。
2. **41 号只有静态核对**：它的替换块写在 `main()` 尾部，要动态复现需造齐 G03 的 24 格输入；本轮读代码确认与 37/40 同构（staging → 校验 → 改名 → 换名），未做运行时模拟。
3. **G02 的 b≥1 尚不可验**：重开仅写到 b=0（每 b ~11 min），「两个指纹 50 个 b 全同」目前只有单元级证据（6 例）+ 我的 n=400 双历史 rep 实测，真实 50 b 的等值要等收尾后才能核。
4. **未重审 G01 全量**：本轮按任务只验 5 条 P2 与修复副作用；FPR/CP/证据链的独立复算沿用 `review2` 已实测结论，本轮只抽查（37 号 `--check` 0 不一致、merged 列逐格）。
5. **未审 40/41 的 `check` 语义与 G03 收尾**（`deab211` 的「40/41 check+导出」不在本任务范围）。

---

## §6 一句话

**5 条 P2 全部真实关闭（其中 P2-1、P2-2 用「改前漏 / 改后拦」的同夹具对照与四种失败路径实测确认），没有新增 P0/P1，
校验器只被加强、未被削弱；新增 4 条 P3 全是文字标签级（0.5855 应标「双侧」、91% 与 GOAL「合并」的映射、`all_repetitions.csv` 行数 1 384、备份命名不统一），改一句话即可，不需要任何重跑。**

---

## §7 后记（评审定稿后同一工作区的他人改动，不改变上述结论）

本报告 §1–§6 针对 `daf9d80` 的只读快照（定稿 10:54）。收尾读树时（HEAD 已推进到 `8f6a316`，改动**未提交**）发现主代理已按本报告把 4 条 P3 修掉，逐条对照如下（均为只读核对，本代理未改任何代码/配置/数据）：

- **N-1**：`docs/v3_phase_G01_formal.md` §3 脚注（现 51 行）改为「**双侧** z 近似……**0.5857**（单侧 z 近似为 0.7024）」，与本报告重算 0.58570 / 0.70249 一致。
- **N-2**：同处（现 50–51 行）改为「GOAL 的『合并』指 1 000 次，对应 0.9971；若 91% 实指每层 250 次，则对应 0.9176」，映射歧义消除。
- **N-3**：§5.1 第 3 条改为「实为 **1 384 行**，按 `(level, rep)` 去重后 1 000 行」，与实测一致。
- **N-4**：`scripts/40_export_g02_evidence.py:154`、`scripts/41_export_g03_evidence.py:279` 的备份戳统一为 `datetime.now(BEIJING).strftime("%Y%m%d%H%M%S")`，与 37 号同格式；已确认两文件的 `datetime` 与 `BEIJING` 均已在文件头 import/定义，不会因该改动 `NameError`。

另：`GOAL.md` 的 G01 行已由「未证实」改为「通过（2026-10-29 11:00）」并引用本报告，其列出的 0.0460（46/1 000）、CP `[0.033871, 0.060884]`、60/69、59 登记/60 文件/1 275 048 B 与本轮实测一致；「非新样本、解析功效非实测、带下界不达标」三条边界也已写入，符合本报告 §5 的限定。

结论：**5 条 P2 关闭、0 新增 P0/P1 的判断不受上述改动影响**；截至本节写作时 4 条 P3 均已在工作区消除（待提交）。
