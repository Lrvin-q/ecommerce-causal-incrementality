# v3 G04 关闭条件窄口径复核（C1–C5）

> 合成数据 / 已知 DGP。复核完成时间：2026-10-31 21:42（北京时间；下文时间均取自日志内部字段或文件系统时间，均写全时分）。
> 本文件是复核产物，不是交付结论的替代：每条判定都给出本次实测命令与输出片段。

## 0. 对象与方式

- 复核对象：`docs/reviews/v3_phase_G04_review.md`（20:35）§6 的 5 条关闭条件 C1–C5。
- 基线：HEAD = `0d4d61a3a2155cd920898f64637ca623c261bd33`（`f92557d` G04 包 + `0d4d61a` H03/H04 复核文档）；评审基线 `f52d663` 用于 diff。
- 只读声明：未改 `paper/ scripts/ src/ configs/ outputs/ tests/`，未 commit/push，未装包，未重跑全量 pytest 与 R>0 正式作业。
- 本次写入：仅本文件与 `out/scratch/g04_recheck/`（`49.log`、`pytest_targeted.log`、`62.log`、`probe.py`、`probe.log`、`probe_*/`、`top_missing_g03.json`）。
- 环境：`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`，解释器 `.venv/Scripts/python.exe`；退出码单独取，不接管道。
- 工作树现状：`git status` 仅有 `AGENT_HANDOFF.md / GOAL.md / TODO.md` 三个由他人维护的未提交改动（mtime 20:55 / 21:23），不属本次范围，未触碰。

## 1. C1–C5 逐条判定

| 条件 | 判定 | 核心证据 |
|---|---|---|
| C1（P2-1/P2-2/P2-3） | **CLOSED** | 49 增读 finalize 六零+完成行、非零先于 OK；33 增 `--expect-complete`（新增即 rc=5）；5 类夹具全在且全过；真实树 49 RC=0 READY |
| C2（P1-1） | **CLOSED** | 手册内部时间 20:47、93/16 975 748 B、290 claim、`_final` 24 格、六条命令均有 `[跑过]` 时间与路径、两句限制保留 |
| C3（P2-4） | **CLOSED** | 全量日志 21:02:15–21:10:28、exit=0、1424 点=收集数、窗口内无并发写；缺 pytest 末尾 summary 行记为 P3 |
| C4（P3-2/3/4/5） | **CLOSED** | 事故表补 17:51/19:34；"28 行"与 `wc -l` 一致；66 成功后才写 6/6、失败写 FAILED 透传 rc；62 拒因必须含"分片间 rep 重叠" |
| C5（P3-1） | **CLOSED** | 注册表 §2.7 明写 PID 1507 为人工记录、无机器快照；`monitor.log` 中 `1507` 零命中、无命令行/父 PID 字段 |

### 1.1 C1：49/33 的 finalize 与双向登记门

代码（`scripts/49_g04_closeout_precheck.py`）：

- 第 41-47 行新增 `FINALIZE_EXITS` 六键与 `_bad_exits()`；第 62-66 行**先判非零**并 `continue`，第 67-78 行才判 finalize 六零 + `OK: G03 finalize 完成`，缺失/不完整进 `problems`。
- 第 198-204 行把 33 dry-run 改为 `--dry-run --expect-complete`，非零即 problem。
- 33（`scripts/33_register_evidence_top.py`）第 417-418 行新增参数，第 476-479 行 `if args.expect_complete and added: return 5`。

测试实跑（41 例，RC=0，日志 `out/scratch/g04_recheck/pytest_targeted.log`）：

```
pytest tests/test_g04_closeout_precheck.py tests/test_v3_evidence_registry_guards.py tests/test_g04_recovery_scripts.py -q --basetemp C:/cg_t
.........................................                                [100%]   RC=0
```

分布：`test_g04_closeout_precheck.py` 17 例、`test_v3_evidence_registry_guards.py` 18 例、`test_g04_recovery_scripts.py` 6 例，合计 41；无 skip（41 点全过即 17+18+6）。C1 要求的 5 类夹具逐条落位：

| 夹具 | 位置 | 本次结果 |
|---|---|---|
| finalize 缺失 | `tests/test_g04_closeout_precheck.py:127-131` | 过（problem `finalize.status 缺失`） |
| finalize ABORT | 同上 `:134-140`（`drill_exit=1` + ABORT） | 过（problem 非零退出） |
| OK + 非零 | 同上 `:163-169` | 过（`phase2.status 非零退出`，OK 不覆盖） |
| 仅非零无 OK | 同上 `:172-176` | 过 |
| 顶层少一条 | `tests/test_v3_evidence_registry_guards.py:179-186`（33 rc=5）+ `test_g04_closeout_precheck.py:179-184`（49 映射为 problem） | 过 |

独立探针（不依赖 pytest；`out/scratch/g04_recheck/probe.log`）——把 `49.ROOT` 指向夹具树后调用 `check_statuses()+verdict()`：

```
[49-ok]           verdict=0 problems=[]
[49-abort]        verdict=3 problems=["finalize.status 非零退出：['drill_exit=1']"]
[49-missing]      verdict=3 problems=['finalize.status 缺失（收尾链未完成或未留证）']
[49-five_only]    verdict=3 problems=["finalize.status 不完整：缺 ['report48_exit']"]
[49-ok_row_removed] verdict=3 problems=["finalize.status 不完整：缺 ['完成行']"]
```

33 的顶层漏登记（删掉一条**真候选** `outputs/evidence/g03_formal/binding/snapshot_binding.json` 后，用副本 `--top` 跑 dry-run）：

```
候选身份类文件 2 个：新增 1，已登记 1
[top-reg] expect-complete：磁盘有、索引无 1 条，拒绝判完备（AGENTS §12.7 双向校验）   rc=5
```

（旁注：首版探针误删了 `outputs/evidence/bindings/aa_snapshot_binding.json`，该记录不在 `--dirs g02_formal g03_formal` 的候选集内，rc=0 属正常；换成 scanned 目录内的记录后 rc=5。此差异不是缺口。）

真实树：`scripts/49_g04_closeout_precheck.py --with-check --with-register --with-claims` → **RC=0**，日志 `out/scratch/g04_recheck/49.log`，关键行：

```
[OK ] finalize.status 六步全 0 + 完成行
[OK ] 33 --dry-run --expect-complete EXIT=0… 新增 0
[top-reg] 顶层全表复算一致：93 条
[VERDICT] READY：可进入 33 登记与报告填数
```

当前树与评审时相比没有多/缺受绑文件（49 自检"源码 49 文件与 g03 快照逐文件一致"），故 RC=0 不是环境漂移造成的假通过。

### 1.2 C2：复现手册

`docs/v3_复现手册.md`：

- 第 3 行"维护时间：2026-10-31 20:47"；全文无 10-29 的旧状态残留（唯一 `20:27` 在第 88 行，指 10-31 20:27 的论文构建，非旧状态）。
- 数字与实读一致（本次 `outputs/evidence/coverage.json`：`records=93, total_bytes=16975748`，逐条求和同为 16 975 748；`g03_formal/coverage.json` 357 条；`v3_h04_claim_registry.csv` 290 条；`out/g03_formal/_final` 24 个目录）。手册第 64-66、49 行所记与此一致。
- 六条命令均有 `[跑过]` 时间 + 路径：40/41 第 48-49 行（20:43:01 / 20:01:53）、48 第 50 行（19:48）、47 第 51 行、33 第 69 行（20:43:01，`out/scratch/g04_precheck_2046.log`）、49 第 101 行（20:43:01 同日志）、63 第 108 行（19:48:27）、66 第 109 行（20:01:53）、62 第 110 行（19:48:06 / 20:59）。
- 两句限制保留：第 34-36 行"本工程从未做过从零端到端重放"，第 128-129 行"没有 Phase 2 连续监控 … 不能当峰值证据"。
- 复算锚点：`out/scratch/g04_precheck_2046.log` 首行 `[TIME] 2026-10-31 20:43:01`、末行 `[VERDICT] READY`，与手册第 101 行一致；`out/g03_logs/post_finalize_export.status` = `post_finalize_export_exit=0`，与第 109 行一致。
- 边界已写：第 38-39 行（run_all 只编排 01–04，G03 后手工分步）、第 53-55 行（`--resume` 只救 provisional、正式分片整片重算）、第 108 行（"人工复核后 33 实登记"）。

### 1.3 C3：全量串行 pytest 凭证

`out/scratch/pytest_full_20261031_2101.status`：

```
start=2026-10-31 21:02:15
end=2026-10-31 21:10:28
exit=0
```

`out/scratch/pytest_full_20261031_2101.log`：28 行、2152 B、20 个进度行、**1424 个点**，末段只有 `warnings summary`（`test_v3_timing.py` 的 `IntegrationWarning: roundoff error`）与 `-- Docs:` 行。

独立可信度判断（未重跑全量）：

1. 文件创建时刻 21:02:15.883 = status 的 `start`；mtime 21:10:27.511 ≈ `end` 21:10:28；status 创建于 21:10:28.274。三者自洽，排除"事后补抄"。
2. 点阵 1424 = 本次 `pytest --collect-only -q` 统计的 1424 例（64 个文件）；进度行里除 `.`、百分比、`]` 外无 `F/E/s` 字符，失败词只出现在 warning 文本（"roundoff error"）。
3. 对照组：`out/scratch/pytest_full_2031.log`（20:40）为 1408 点。1408 + 16 = 1424，而 `f92557d`/`08cce2b` 新增测试恰为 16 例（closeout +8、registry guards +2、recovery scripts +6）。两次日志的差值与被测代码改动一一对应，伪造需要同时伪造这层算术关系。
4. 并发写：21:02:15–21:10:28 窗口内，`docs/ paper/ outputs/tables/ outputs/evidence/ src/ scripts/ tests/ configs/` 无任何文件被写。窗口外邻近的三处为 21:01:47、21:02:04（start 之前）与 21:11:40（end 之后）。
5. 文件末尾**缺** pytest 的 `1424 passed in …s` summary 行——如实记录为 P3-1；`exit=0` 只存在于旁路 `.status`，日志本身不含退出码。结合 1–3，仍足以判定"全量单进程串行跑完且无失败"，不影响 C3 的验收口径（起止连续 / exit=0 / 无并发写）。

### 1.4 C4：事故表、行数、66 写盘序、62 拒因、边界

- (a) `docs/v3_phase_G_run_registry.md:346` 新增 17:51 行、`:347` 新增 19:34 行；`:274` 把 `closeout_precheck_20261031_2005.log` 更正为"**28 行**（`wc -l` 实测）"。本次 `wc -l out/g04_logs/closeout_precheck_20261031_2005.log` = **28**，一致。
- (b) `scripts/66_g03_refresh_evidence_logs.sh:17-29`：先跑 `$EXPORT` 取 `rc`，`rc=0` 才追加 `6/6 收尾后重导出`，否则追加 `6/6 FAILED rc=…`，最后 `echo post_finalize_export_exit=$rc` 并 `exit $rc`。测试 `tests/test_g04_recovery_scripts.py:53-82` 三例（失败不写 6/6、成功只写一次、无 OK 行 ABORT rc=3）本次全过。
- (c) `scripts/62_g04_tamper_drill.py:94-104` `judge_tamper()`：`rc==0` 判失败；输出不含 **`分片间 rep 重叠`** 判失败；`main` 在 `:136-143` 用它。测试三例（未篡改通过 / 无关失败 / rep 重叠）全过。真跑 `scripts/62_g04_tamper_drill.py` → **RC=0 PASS**（`out/scratch/g04_recheck/62.log`）；探针抓取 41 的**完整**输出，确认拒因确实含该字样：
  ```
  [62] tamper rc=2 contains_overlap=True judge=None
  [62] overlap lines: ['  - L0_P_main: 分片间 rep 重叠 [1]']
  ```
  （`tail -2` 只显示后面的 sd/MC_SE 复算不符行，故单看末尾会误以为拒因不是重叠；实际重叠行在前。）
- (d) 手册边界：`run_all` 只覆盖 01–04（第 38-39 行）、`--resume` 语义（第 53-55 行）、"人工复核后 33 实登记"（第 108 行）。

### 1.5 C5：PID 1507 与 monitor.log

- `docs/v3_phase_G_run_registry.md:246-247`："**PID 1507 是人工记录，无机器快照**（G04 C5）：`out/g04_logs/monitor.log` 只记 `python procs=N` 计数，不含 PID/命令行/父 PID；下次正式运行须在启动与结束各留一份进程表。"
- `out/g04_logs/monitor.log`：`1507` 零命中；无 `cmd/command/parent/ppid/Win32` 字段；首个采样块的时间行只含监控自身 PID（`monitor start pid=4019`），每块正文为 `python procs=N rss_mb=… top3_mb=…` 与磁盘/内存。`out/g04_logs/` 下也没有任何进程表文件（仅 4 个日志/状态件）。

## 2. 门禁是否被削弱的独立判断

基线 `f52d663` → HEAD 的 diff（`git diff f52d663 HEAD -- <文件>`）：

| 脚本 | 改动 | 判断 |
|---|---|---|
| `scripts/49_g04_closeout_precheck.py` | 新增 finalize 六零+完成行门；非零 `*_exit` 从"OK 之后 elif"提前为"OK 之前 continue"；33 调用加 `--expect-complete` 并把非零映射为 problem | **只加强**：删除了旧的 `elif bad_exit`（被更强的顺序取代），未改 `raise`→warn，未放宽阈值，未删检查 |
| `scripts/33_register_evidence_top.py` | 新增 `--expect-complete`，`added>0` 时 `return 5` | **只加强**；旧 `verify_whole_table`（索引→磁盘）与 `返回 3/4` 全部保留 |
| `scripts/62_g04_tamper_drill.py` | 新增 `judge_tamper()`，拒因从"不含 `重叠` 且不含 `rep`"收紧为"必须含 `分片间 rep 重叠`"；rc=0 与错因分别返回 5/6 | **只加强**：旧断言换成更窄的白名单，不会把无关失败放行 |
| `scripts/66_g03_refresh_evidence_logs.sh` | 6/6 标记从导出前移到导出成功后；失败写 `6/6 FAILED rc=…`；新增 `G66_*` 注入变量；`exit $rc` 透传 | **只加强**（写盘序与失败可见性）。唯一非加强项：删掉了自带的 `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`（见 P3-3），不影响门禁判据 |

`scripts/41_export_g03_evidence.py` 与 `scripts/40_export_g02_evidence.py` 在本区间未改动（diff 为空）。

结论：四个脚本均未出现"删检查 / 放宽阈值 / raise 改 warn"；`f92557d` 的测试增量（16 例）与行为收紧方向一致。

## 3. 新发现问题

- **P3-1**：全量 pytest 日志缺末行 summary（无 `1424 passed in …s`），`exit=0` 只写在 `.status` 旁路文件，二者均无哈希绑定。缓解证据见 §1.3（创建时刻=start、点阵=收集数、增量 16 与新增测试数吻合、无 F/E）。建议下次在同一日志里追加 `echo exit=$?` 与 pytest 原始尾部。
- **P3-2**：62 的"20:59"这次运行无可锚定的内部时间：手册第 110 行写 20:59，审计 `docs/v3_G04_收尾审计.md:113` 写 21:00，而 `out/scratch/g04_62_tight_2100.log` 无时间戳、mtime 为 20:45。本次我重跑 RC=0 已独立确认判据生效，但该次运行的"何时跑"仍只能信叙述。
- **P3-3**：66 去掉了自带的 UTF-8 环境导出（原 `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`）。63（`scripts/63_g03_finalize.sh:8`）仍导出该变量，63→66 链内无影响；单独手工调用 66 且未设环境变量时，41 的中文输出在 GBK 控制台可能报编码错。建议恢复一行 export。
- **P3-4**：49 现在把 `finalize.status` 缺失判为 problem（RC=3），而手册第 96 行仍写"2 = 仍有未完成项（在跑／未合并）"。收尾之前的中间态从此一律 RC=3，退出码语义与文档不一致（属文案/语义问题，非门禁削弱）。

无 P0/P1/P2。

## 4. 总判

**PASS**。

- C1 CLOSED、C2 CLOSED、C3 CLOSED、C4 CLOSED、C5 CLOSED（5/5）。
- 无 P0/P1；新增 4 条 P3（记录/文档类，不阻断 G04 收口）。
- 建议（非关闭条件）：补全量 pytest 日志的 summary 与退出码；恢复 66 的 UTF-8 环境导出；统一 62 的 20:59/21:00 记录并把手册 §6 的退出码 2/3 语义改成与现实现一致。

## 5. 复核命令清单（可复算）

```bash
# 0) 基线
git rev-parse HEAD                       # 0d4d61a3a2155cd920898f64637ca623c261bd33
git diff f52d663 HEAD -- scripts/49_g04_closeout_precheck.py scripts/33_register_evidence_top.py \
  scripts/62_g04_tamper_drill.py scripts/66_g03_refresh_evidence_logs.sh

# 1) C1 夹具 + C4(b)(c) 夹具（41 例）
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest \
  tests/test_g04_closeout_precheck.py tests/test_v3_evidence_registry_guards.py \
  tests/test_g04_recovery_scripts.py -q --basetemp C:/cg_t          # RC=0，41 dots

# 2) C1 真实树
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
  scripts/49_g04_closeout_precheck.py --with-check --with-register --with-claims   # RC=0 READY

# 3) C1 独立探针（finalize 缺失/ABORT/五步/缺完成行；33 顶层漏一条；62 完整拒因）
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe out/scratch/g04_recheck/probe.py
# 以及单独复跑 33 漏登记探针（见 §1.1 代码块）

# 4) C4(c) 真跑演练
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe scripts/62_g04_tamper_drill.py  # RC=0

# 5) C2 数字
python -c "import json;d=json.load(open('outputs/evidence/coverage.json',encoding='utf-8'));print(len(d['records']),d['total_bytes'])"
wc -l out/g04_logs/closeout_precheck_20261031_2005.log      # 28

# 6) C3 凭证（不重跑全量）
cat out/scratch/pytest_full_20261031_2101.status            # start/end/exit=0
python -c "import pathlib;t=pathlib.Path('out/scratch/pytest_full_20261031_2101.log').read_text();print(sum(l.count('.') for l in t.splitlines() if '[' in l))"   # 1424
PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest --collect-only -q --basetemp C:/cg_t        # 合计 1424

# 7) C5
grep -c 1507 out/g04_logs/monitor.log                        # 0
grep -n "1507\|人工记录\|机器快照" docs/v3_phase_G_run_registry.md
```
