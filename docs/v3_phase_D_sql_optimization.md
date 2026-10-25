# Phase D.4：五表装入 SQLite 的批量优化

> **合成数据 / 已知 DGP。** 维护时间：2026-10-25 11:55（北京时间）。
> 代码：`src/causal_growth/data/v3_sql_fast.py`　测试：`tests/test_v3_sql_fast.py`
> 基准：`outputs/tables/v3_phase_D_sql_bench.csv`　被优化对象：`v3_sql.py:97-118 _load_facts`（**未改动**）
> `v3_sql.py`、`configs/v3/*.yaml`、`sql/v3_*.sql` 一个字都没改；本模块是新增文件，等待主控切换调用点。

---

## 0. 一句话结论

| 指标 | 旧路径 | 新路径 | 比值 |
|---|---|---|---|
| `_load_facts` 单批（n=200,000 五表，:memory:） | **21.40 s** | **9.17 s** | **2.33×** |
| 其中纯 Python 拆箱 | 14.0 s | 1.5 s | **9.3×** |
| 其中 SQLite 引擎（绑定 + B 树 + 2 个索引 + FK 检查） | 7.4 s | 7.7 s | 1.0×（去不掉） |
| `run_sql_pipeline(clean)` CPU | 40.84 s | 28.56 s | 1.43× |
| **完整链路 `build_observed_pipeline` CPU** | **187.70 s**（本机当日负载） | **162.30 s** | **1.16×** |
| 折算到 pilot 空载基线 143.7 s | 143.7 s | **≈120 s**（区间 110–124） | 1.16–1.22× |

**目标"pipeline 144 s → ≤60 s"没有达成，我不粉饰。** 原因不是装载没优化好，而是任务书里
"43% 花在逐行搬数据"这个份额来自 `cProfile` 的插桩份额；在**未插桩**的真实 CPU 时间里，
`_load_facts` 只占 33%（61.91 / 187.70，见 `I_decomposition`）。装载省下的 33.9 s 无法把
一条 144 s 的链路压到 60 s——那需要再省 84 s，而旧路径两次装载一共只有 61.9 s。要把 pipeline
打到 60 s，必须同时动质量校验（profile 里 59.7 s）、污染/去重（36 s）和两次 SQL 分析与回读
（约 40 s），这些都不在本任务的文件域内（见第 6 节）。

**等价性方面没有任何妥协**：n=200,000 的真实五表（含 1,398,380 行 `user_events`）在新旧两条
装载路径下**逐表内容哈希相同、typeof 分布相同、DDL 相同**，整条 SQL 链路与完整链路的观测表
哈希也相同（第 2 节）。

---

## 1. 优化前后的差异

### 1.1 旧实现（`v3_sql.py:97-118`，冻结不动，作为等价性基准）

```python
for start in range(0, len(frame), chunk_size):
    block = frame.iloc[start:start + chunk_size].loc[:, columns]
    rows = (tuple(_scalar(value) for value in row)
            for row in block.itertuples(index=False, name=None))   # 逐行
    connection.executemany(statement, rows)

def _scalar(value):                       # 逐格
    if pd.isna(value):                    #   每格一次 pd.isna（27M 次/批）
        return None
    return value.item() if isinstance(value, np.generic) else value   # 每格一次 isinstance+item
```

pandas 3 的字符串列是 Arrow 后端，`itertuples` 取值会走 `ArrowArray.__iter__`，因此每批
2,000 万级单元格全部落在 Python 解释器里（profile：`_scalar` 27,137,276 次、`ArrowArray.__iter__`
10,655,466 次）。**本机实测每批 13,568,638 个单元格，`_load_facts` 每批调用一次共两次
= 27,137,276 —— 与 profile 的 `_scalar` 次数完全对上**，说明份额分析与本机复现一致。

### 1.2 新实现（`v3_sql_fast.py`）

```python
for start in range(0, len(frame), chunk_size):
    block = frame.iloc[start:start + chunk_size]
    parts = []
    for column in columns:                       # 按列，不按行
        series = block[column]
        values = series.to_numpy(dtype=object, na_value=None)   # C 层拆箱
        if series.hasnans:                       # 只有真有缺失的列才付这个成本
            missing = series.isna().to_numpy()
            if missing.any():
                values = values if values.flags.writeable else values.copy()
                values[missing] = None           # 整块向量化置 None
        parts.append(values)
    yield from zip(*parts)                       # C 层拼行，直接喂 executemany
```

四处关键变化，一一对应旧实现的成本：

| 旧 | 新 | 效果 |
|---|---|---|
| `itertuples` 逐行取 Arrow 标量 | `Series.to_numpy(dtype=object, na_value=None)` | 去掉 1,065 万次 `ArrowArray.__iter__` |
| 每格 `pd.isna` | 每列一次 `isna()` + 布尔掩码整块赋值 | 去掉 2,714 万次 `pd.isna` |
| 每格 `isinstance` + `.item()` | 由 numpy/pandas 在 C 层拆箱 | 去掉 2,714 万次 `np.generic` 判断 |
| 生成器逐行 yield 元组 | `zip(*列数组)` | 行元组在 C 层组装 |

**没有改变的**：五表校验与报错文案、表装载顺序（users→coupon_assignment→user_events→orders）、
`INSERT INTO "t" (cols) VALUES (?,…)` 语句与占位符数量、`user_outcomes` 被 `continue` 跳过
（派生输入永不装载）、`sqlite3.IntegrityError` 从中断处原样抛出、行插入顺序。

**唯一一处有意的差异**：`chunk_size < 1` 直接抛 `ValueError`。旧实现对 0 抛 `range()` 的
`ValueError`，对负数则**静默少装全部行**（`range` 为空 → 空表），是会毁数据的隐式行为，没有复制。

---

## 2. 等价性证明

### 2.1 方法：六个维度，逐表比

同一份输入分别用 `v3_sql._load_facts`（**冻结副本**，见下）与 `load_facts_fast` 建两个库，
然后逐表比对：

1. **行数**；
2. **列名/声明类型/NOT NULL/主键顺序**（`PRAGMA table_info`）；
3. **`typeof()` 组合分布**（一条 `GROUP BY` 扫一遍表；能覆盖 `label ANY` 这类混合类型列）；
4. **按主键排序后的整表规范哈希**（每个值写成 `类型名:repr`，行间 `\x1e` 分隔）——
   整数 `1`、浮点 `1.0`、字符串 `'1'` 哈希不同，避免"值看起来一样但存储类型变了"混过去；
5. **插入顺序哈希**（`SELECT rowid,* ORDER BY rowid`）——防止"内容对但物理顺序被换掉"；
6. **`sqlite_master` 全量比对**（DDL、两个索引的定义文本）。

旧实现以**冻结副本** `_legacy_load_facts` 的形式写进测试文件（`v3_sql.py:91-118` 的逐字副本）。
测试 `test_frozen_reference_matches_v3_sql` 会在旧实现仍存在时**逐行校验**两份源码一致（漂移即红），
主控把调用点切换走之后自动 skip。这样等价性证明不依赖 `v3_sql._load_facts` 的存续。

### 2.2 n=200,000 真实五表：逐表指纹（`H_evidence_tables`）

数据：`generate_v3_population(L1_main, n=200000)` → `build_raw_tables` → `inject_dirt` → `deduplicate_events`。
两库均为 `sqlite3.connect(":memory:")` + 同一份 `sql/v3_schema.sql`。

| 表 | 行数 | 内容规范哈希（新旧**相同**） | 说明 |
|---|---|---|---|
| `users` | 200,000 | `a63e5ee3ae6270925e75d3a037b324d32b66818b351b4d703a0449ec0728cf87` | 含 11,100 个 `cart_value_cent` NULL |
| `coupon_assignment` | 200,000 | `8c2bf1e55655dfee1965ed74c45e27b5ca9a39990d24d9272cf7342efc09bd64` | 20 万个 NULL 的 `assigned_policy_arm` / `policy_arm_probability` |
| `user_events` | **1,398,380** | `bc166914261c9367e8284cb4de782fdb9d71f1a113e5910098abb20a275e3f66` | 百万行大表 |
| `orders` | 26,289 | `d138b65f200f245e581b2da9097053d7ba4bd049ce27f36c88c2b1f4828727da` | 24,324 个 `refund_day` / `refund_ingested_day` NULL |
| `user_outcomes` | **0** | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 空输入的 SHA-256；派生输入被跳过 |
| `sqlite_master` | — | 全量文本相同 | DDL 与两个索引定义未变 |

`typeof()` 分布（新库；旧库逐位相同）：

```
users.cart_value_cent                 : integer 188900 | null  11100
orders.refund_day                     : null    24324 | real   1965
orders.refund_ingested_day            : null    24324 | real   1965
coupon_assignment.assigned_policy_arm : null   200000
coupon_assignment.policy_arm_probability : null 200000
```

即：**NaN / `pd.NA` / `None` 一律落成 SQL NULL（`typeof='null'`），没有变成字符串 `'nan'`、
没有变成 IEEE NaN 的 REAL、也没有在 NOT NULL 列上被吞成 0。**

### 2.3 整条 SQL 链路与完整链路

| 对象 | 旧路径 | 新路径 | 是否相同 |
|---|---|---|---|
| `run_sql_pipeline(clean).analysis_sha256` | `e6e5e6b2…` | `e6e5e6b2…` | ✅ 逐字节相同 |
| `run_sql_pipeline(clean)` 的 `user_outcomes` / `quality` / 六张汇总视图 | — | — | ✅ `assert_frame_equal` |
| `run_sql_pipeline` 的 `sql_sha256` | `18fe1968…` | `18fe1968…` | ✅ SQL/DDL 源码未动 |
| `build_observed_pipeline` 最终观测表哈希 | `c2fafcdc…` | `c2fafcdc…` | ✅ 200,000 行 × 46 列全等 |

`sql_sha256` 不变是刻意的：`sql_source_hash()` 只哈希 `sql/v3_schema.sql`、`sql/v3_analytics.sql`、
`v3_sql.py` 三个文件，本模块**不在**其中——装载实现变了而 SQL 语义哈希不变，正是我们想要的区分
（但这也带来一个需要主控决定的事项，见 7.4）。

### 2.4 测试清单（`pytest tests/test_v3_sql_fast.py -q` → **17 passed**，约 58 s）

| # | 测试 | 覆盖的硬要求 |
|---|---|---|
| 1 | `test_frozen_reference_matches_v3_sql` | 冻结副本 = 优化前实现（漂移守卫，切换后 skip） |
| 2 | `test_business_table_constant_matches_v3_sql` | 五表常量不漂移 |
| 3 | `test_every_table_is_identical_to_the_legacy_loader` | **逐表等价**（6 维度） |
| 4 | `test_user_outcomes_payload_is_never_loaded_but_still_validated` | **`user_outcomes` 被跳过**、但非空时仍校验列 |
| 5 | `test_missing_values_become_sql_null_with_the_same_typeof_distribution` | **NaN/NA → NULL**，逐列 NULL 计数 + typeof |
| 6–9 | `test_iter_fact_rows_unboxes_and_maps_missing_to_none[float64/Int64/object/str]` | 四种 dtype 的拆箱语义 |
| 10 | `test_chunk_boundaries_keep_every_row_in_order` | **chunk 边界**（1/7/rows-1/rows+1/非整除）不丢不重、插入顺序不变 |
| 11 | `test_default_chunk_size_loads_everything_and_rejects_non_positive` | 默认 chunk 全覆盖；<1 报错 |
| 12 | `test_pragmas_take_effect_during_loading_and_are_restored_afterwards` | **PRAGMA 生效 + 恢复**（含文件库、跨连接复查） |
| 13 | `test_pragmas_are_restored_when_the_load_raises` | **异常路径也恢复**，且失败装载不落半张表 |
| 14 | `test_sql_pipeline_output_is_identical_under_both_loaders` | 整条 SQL 链路逐帧相同 |
| 15 | `test_fast_fact_loading_context_manager_only_swaps_the_hook` | 切换钩子只换实现、可还原 |
| 16 | `test_schema_validation_matches_the_legacy_loader` | 6 类非法输入的**报错文案逐字相同** |
| 17 | `test_million_row_event_table_is_identical` | **1,000,000 行** `user_events` 内容哈希相同 |

**既有测试回归（我把 fast loader 装上后跑的，不改任何文件）**：
`test_v3_sql.py + test_v3_quality.py + test_v3_observed.py + test_v3_tables.py + test_v3_dirt.py` = **127 项全绿**；
`test_v3_pipeline.py` = **7 项全绿**。方法是用一个 pytest 插件在 `pytest_configure` 里
`v3_sql._load_facts = load_facts_fast`，跑完即弃（见 8.2）。全量 803 项由主控在所有代理停写后串行跑。

---

## 3. 基准（n=200,000，`outputs/tables/v3_phase_D_sql_bench.csv`）

> 环境：Windows / Python 3.13.7 / pandas 3.1.0 / numpy 2.5.4 / pyarrow 26.0.0 / SQLite 3.50.4。
> **重要前提**：本次基准与另外三个写 `v3*.py` 的代理**同机并发**，绝对秒数比 pilot 的空载基线高约 30%
> （wall 甚至更高）。因此**只使用同进程、同表的 A/B 比值**，绝对数字也照实列出，不做"择优选数"。

### 3.1 完整链路 A/B（`E_pipeline`）

| | 旧路径（`_load_facts`） | 新路径（`load_facts_fast`） | 差 |
|---|---|---|---|
| `build_observed_pipeline` 墙钟 | 193.67 s | 166.56 s | −27.1 s |
| `build_observed_pipeline` CPU | **187.70 s** | **162.30 s** | **−25.4 s（1.16×）** |
| 其中两次 `_load_facts` 合计 | **61.91 s** | **28.00 s** | **−33.9 s（2.21×）** |
| 最终观测表哈希 | `c2fafcdc…` | `c2fafcdc…` | 0 |
| 进程峰值工作集 | 2,566 MB | 2,918 MB | 见 3.4 |

链路 CPU 只降了 25.4 s 而不是装载差值的 33.9 s：第二次运行还享受了进程内的页缓存与分配器预热
（单次 `run_sql_pipeline` 的 A/B 里，差值 12.28 s 与装载差值 11.77 s 是对得上的）。

**折算到 pilot 基线 143.7 s**（2026-10-25 11:02 的 3 rep 均值）：
按比例 `143.7 × 162.30/187.70 = 124.2 s`；按差值 `143.7 − 25.4 = 118.3 s`。
取区间 **110–124 s，报告用 ≈120 s**。这个折算必须在空载机器上用 pilot 重测才能定稿。

### 3.2 时间去哪了：拆解（`I_decomposition`）

单批 `_load_facts`（13,568,638 单元格）：

| 组成 | 旧 | 新 |
|---|---|---|
| 纯 Python 拆箱（生成行元组） | 14.0 s | **1.5 s** |
| SQLite 引擎（executemany 绑定、B 树插入、`orders_by_user`/`events_by_user` 两个索引、FK 检查） | 7.4 s | 7.7 s |
| 合计 | 21.4 s | 9.2 s |

**这就是 3× 目标达不到的物理原因**：新路径已经只剩引擎成本，而引擎成本与 DataFrame 怎么拆箱无关。
进一步压它只有三条路，我实测了但都**没有采用**（`G_rejected_variants`）：

| 变体 | 耗时 | 相对基线 | 为什么否决 |
|---|---|---|---|
| 装载期间 `PRAGMA foreign_keys=OFF` | 11.11 s | −1.9 s | 绕过外键完整性检查 = 语义变更，且会把外键错误从"装载时立刻炸"推迟到事后审计 |
| 先 `DROP INDEX` 两个索引、装完按原文本重建 | 11.91 s | −1.1 s | 最终 DDL 文本相同，但改变了 DDL 执行次序，收益太小、审计解释成本太高 |
| 多行 `INSERT … VALUES (…),(…),…`（500 行/语句） | **8.38 s** | **−4.7 s** | **会改变 INSERT 语句形态**，超出"不得改变任何 SQL 语句"的授权，报给主控定夺 |
| 基线（`load_facts_fast`，chunk=100k） | 13.04 s | — | 同一探针进程形状 |

> 若主控批准"多行 VALUES"这一条，装载还能再降约 1/3（13.0 → 8.4 s），但它改的是语句而不是拆箱，
> 属于要单独评审的语义相邻改动，我没有擅自做。

### 3.3 chunk_size：10k 以后是平台期（`D_chunk` / `F_chunk_probe`）

| chunk_size | 同进程扫描（:memory:） | 独立进程（同机同负载） | 相对峰值内存 |
|---|---|---|---|
| 2,000 | 11.77 s | — | — |
| 10,000（**当前 config 值**） | 10.79 s | 14.83 s | +6 MB |
| **50,000（推荐）** | **10.54 s** | **12.98 s** | +14 MB |
| 100,000 | 10.69 s | 13.04 s | +25 MB |
| 200,000 | 10.48 s | — | — |
| 不分块（1,398,381） | 10.21 s | — | 更高 |

**结论**：10k 以后差异都在重复运行噪声内（≤5%）；**推荐 50,000**——比 10k 每批快 1.5–1.8 s，
峰值只多 8 MB。模块默认 `DEFAULT_CHUNK_SIZE = 50_000`。当前 `configs/v3_data.yaml` 的
`sql.insert_chunk_size: 10000` 不改也行，代价是每批慢约 1.5 s（每链路 2 批 ≈ 3 s）。

### 3.4 内存

- 独立进程装载 clean 五表：旧 623 MB、新 629 MB（chunk 10k）/ 637 MB（50k）/ 648 MB（100k）——
  新装载器**几乎不增加内存**（每个分块是一批 object 数组 + 行元组，随 chunk 线性增长）。
- 完整链路里同一进程先跑旧路径（峰值 2,566 MB）再跑新路径（2,918 MB），峰值 +352 MB **主要不是装载器造成的**，
  而是同一进程连续跑两次流水线的累积（pilot 已记录过这种累积：rep0 独占 1,878 MB，3 rep 同进程升到 2,471 MB）。
  正式编排仍应"一 rep 一进程"，分块用 10k/50k 可把这一项控制在 +10 MB 量级。

### 3.5 对全矩阵外推的影响（若 120 s 成立）

pilot 的矩阵外推用的是 143.7 s/批。装载优化后按 120 s/批：

| 作业类型 | 批数 | 旧单批 | 新单批 | 新合计 CPU·h |
|---|---|---|---|---|
| `full_learning_data_jobs` | 7,300 | 266.7 s | 243.0 s | 492.7 |
| `independent_validation_jobs` | 7,300 | 144.6 s | 120.9 s | 244.9 |
| `complete_aa_jobs` | 4,000 | 145.6 s | 121.9 s | 135.4 |
| `additional_design_power_jobs` | 2,000 | 146.0 s | 122.3 s | 67.9 |
| `retraining_bootstrap_jobs` | 800 | 476.1 s | 452.4 s | 100.5 |
| `historical_dgp_jobs` | 12,500 | 0.85 s | 0.85 s | 3.0 |
| **合计** | | **≈1,186** | | **≈1,044**（−12%） |

4 路并行墙钟 ≈ 1,044/4 ≈ **261 h ≈ 10.9 天**（原 297 h ≈ 12.4 天）。
**这是估算，必须用 `scripts/13_v3_pilot.py --reps 3 --n 200000` 重测后替换**，pilot 的 143.7 s 也要一起更新。

---

## 4. PRAGMA：用了什么、怎么恢复、风险，以及一个不好看的实测

### 4.1 用了什么

| PRAGMA | 值 | 目的 |
|---|---|---|
| `journal_mode` | `OFF` | 不写回滚日志（只对文件库有意义） |
| `synchronous` | `0`（OFF） | 不在提交点 fsync |
| `temp_store` | `2`（MEMORY） | 临时 B 树/排序走内存 |
| `cache_size` | `-131072`（128 MiB） | 加大页缓存 |

### 4.2 怎么恢复（实现见 `relaxed_pragmas`）

1. **改动前先读原值**（`PRAGMA x` 的返回值），逐项存入 `saved`；只有"读回来的值确实等于目标值"
   才登记为"改过"，否则不登记——这样既不会误报，也不会漏恢复。
2. `try/finally` 包住整个装载，**异常路径也恢复**。
3. `journal_mode` 不能在事务里改：进入时若已有未提交事务就**跳过它**（不动调用方的事务，
   也就没有需要恢复的东西）；装载期间为了恢复它，在**我们自己的**事务上成功时 `commit()`、
   失败时 `rollback()`，然后再写回原值。
4. 写完逐个再读一遍；任何一项没回到原值就 `RuntimeError`（"失败要响"，不静默降级）。
5. 校验过：文件库 `before={'journal_mode':'delete','synchronous':2,'temp_store':0,'cache_size':-2000}`
   → `after` 完全相同（重新打开连接复查也相同）；`:memory:` 库 `journal_mode` 恒为 `memory`，
   不进"已改"集合。

### 4.3 风险（显式声明）

- `journal_mode=OFF` + `synchronous=OFF` 意味着**装载中途断电/崩溃可能留下无法回滚的库文件**。
- 本项目接受该风险的理由：观测库是**可重建的中间件**（同一 config hash / data config hash / 源码 hash
  重跑可逐字节复现），正式产物是 SQL 物化的 parquet + 清单哈希，库文件从不是唯一副本；
  装载后仍强制跑 `PRAGMA foreign_key_check` 与 `v3_quality` 全量审计。
- 附带的一条行为差异：文件库场景下我们在装载成功时**提前 commit**（为了恢复 journal_mode）。
  数据内容不变，但失败发生在装载之后时，磁盘上会留下已提交的行（失败运行本来就会被标 failed 并保留现场）。

### 4.4 实测收益：≈0（这条必须写下来）

文件库、227 MiB、同样五表：

| | 不开 PRAGMA | 开 PRAGMA | 差 |
|---|---|---|---|
| 旧装载器 | 26.28 s | 25.36 s | −3.5%（噪声内） |
| 新装载器 | 12.51 s | 12.39 s | −1.0%（噪声内） |

原因：整个装载是一个大事务，回滚日志只记录被改写的既有页（新页不需要日志），
提交点也只有一次 fsync，所以 `journal_mode=OFF` 在这类"批量灌新数据"的负载上几乎不省时间。

**因此给主控的建议**：这项 PRAGMA 保留或删除都可以，**速度上没有区别**。若不愿承担 4.3 的崩溃
安全性下降，把 `v3_sql_fast.LOAD_PRAGMAS` 置为 `()` 即可（`relaxed_pragmas` 会退化成空操作，
所有恢复与断言逻辑自动短路），不需要改任何其他代码。任务书要求实现它，我实现了并做了恢复保证；
但把"收益≈0、风险非 0"如实报上来，由主控决定是否保留。

---

## 5. 局限与结论失效条件

1. **只测了 L1_main + n=200,000**（与 pilot 同口径）。L0/L2/L3 未复测；事件量差异会改变
   `user_events` 的装载占比，但不会改变"引擎成本 ≈ 拆箱成本的 4 倍"这个结构。
2. **绝对秒数受同机并发影响**：本次有另外三个代理在跑（进程级 CPU 700+ s），wall 与 CPU 都偏高约 30%。
   所有结论只用同进程 A/B 比值；折算到 pilot 基线给的是区间而不是点值。
3. **折算 120 s 依赖"各阶段按比例退化"的假设**。若某些阶段对 CPU 争抢更敏感，折算会偏。
   唯一可靠的做法是空载重跑 pilot。
4. **chunk 差异在噪声内**：10k–200k 的差别 ≤5%，不要把它当显著优化；选 50k 只是因为方向一致且内存代价小。
5. **PRAGMA 收益≈0 的结论**只在"单连接、:memory: 或本地 NTFS 文件库、单一大事务"的条件下成立。
   若将来装载改成多次 commit，或库在慢盘/网络盘上，结论可能反转。
6. 未覆盖：WAL 模式数据库（`journal_mode` 在 WAL 下切换到 OFF 需要无其他连接）、只读连接、
   多连接并发写、`pandas` 2.x 后端（本机 pandas 3.1.0 的 `str` 是 Arrow 后端，换回 object 后端时
   新实现仍然正确、但相对收益会缩小，因为旧实现的 Arrow 迭代成本会消失）。

---

## 6. 未做到的部分与原因（不静默降级）

| 目标 | 结果 | 原因 |
|---|---|---|
| `_load_facts` 时间压到 1/3 以下 | **达成**：21.4 → 9.17 s（2.33×）；拆箱部分 9.3× | — |
| pipeline 144 s → **≤60 s** | **未达成**，只到 ≈120 s（1.16–1.22×） | 装载只占旧链路 33%；省不到本身不存在的 84 s。要 ≤60 s 需要同时优化：质量校验（profile 59.7 s，跑 3 次）、污染/去重（36 s）、两次 SQL 分析与 `read_sql` 回读（约 40 s）、`parquet` 落盘。这些都在别人/其他文件域里，我不越界。 |
| "装载时间占 43%"这一前提 | **证伪（在未插桩口径下）** | 43% 是 `cProfile` 的插桩份额：27M 次 Python 调用每次都被记账，装载被放大；真实 CPU 份额 33%。建议主控在后续 profile 里用 `perf`/`py-spy` 抽样而非 `cProfile` 计数来定份额。 |
| 多行 VALUES 再省 4.7 s/批 | 未实施 | 需要改 INSERT 语句形态，超出"不得改变任何 SQL 语句"的授权 |
| 关 FK / 先删索引后建 | 未实施 | 分别是语义变更 / DDL 次序变更，收益仅 1–2 s，不值得 |
| 空载重跑 pilot 定稿 120 s | 未做 | 同机有 3 个代理在跑，此刻测不出空载数；留给主控串行阶段 |
| 把 loader 纳入 `sql_source_hash()` | 未做 | 需要改 `v3_sql.py`（我的文件域之外），列在 7.4 交主控决定 |

---

## 7. 给主控的切换说明

### 7.1 改哪一行

`src/causal_growth/data/v3_sql.py`：

1. **第 21 行之前**（`from causal_growth.data.v3_storage …` 之上，保持字母序）加一行 import：
   ```python
   from causal_growth.data.v3_sql_fast import load_facts_fast
   ```
   （注意方向是 `v3_sql → v3_sql_fast`，本模块内部**不在模块级 import `v3_sql`**，只在一个
   显式的 `fast_fact_loading()` 上下文里延迟 import，所以不会形成循环导入。已实测两种 import
   顺序都能正常导入。）

2. **第 201 行**：
   ```python
   # 改前
   _load_facts(connection, tables, int(data_cfg.require("sql.insert_chunk_size")))
   # 改后
   load_facts_fast(connection, tables, int(data_cfg.require("sql.insert_chunk_size")))
   ```
   到此为止即可工作。`_load_facts`（97–118 行）与 `_scalar`（91–94 行）**建议先留着**：
   测试里的漂移守卫会在它存在时继续校验冻结副本。

3. 可选（推荐）：`configs/v3_data.yaml` 的 `sql.insert_chunk_size: 10000 → 50000`
   （该文件不在冻结的七份 `configs/v3/*.yaml` 内），每批省约 1.5 s、每条链路省约 3 s。

4. 可选：不想承担 PRAGMA 崩溃安全风险就把 `v3_sql_fast.LOAD_PRAGMAS` 设为 `()`，速度不变。

### 7.2 改完必须重跑什么

| 重跑项 | 为什么 |
|---|---|
| `pytest tests -q`（全量，串行、无并发写盘） | 装载实现变了，任何 SQL 相关断言都要重新确认。我装的 fast loader 让 `test_v3_sql/quality/observed/tables/dirt` 127 项 + `test_v3_pipeline` 7 项全绿，但不能代替你的全量串行 |
| C 阶段四代表库逐行核对 + 质量审计 | 冻结验收要求；`v3_quality` 与 `foreign_key_check` 会一起跑 |
| 重新绑定 `sql_source_hash()` | 它哈希 `v3_sql.py` 自身，改了调用点它就变；所有引用 `sql_sha256` 的清单/产物需要重绑 |
| `scripts/13_v3_pilot.py --reps 3 --n 200000` | 用实测替换本文 3.5 的 120 s 估算，并更新 `docs/v3_phase_D_pilot.md` 的矩阵外推 |
| 检查 `pipeline_source_hashes()` / `data_check_source_hashes()` 的清单差异 | 它们会多出 `src/causal_growth/data/v3_sql_fast.py` 这一个 key，属"新增文件"，不是内容漂移 |
| 注意 | 我的新文件匹配 `v3*.py`，**在它落盘期间别人的 `build_observed_pipeline` 会报 `RuntimeError: source files changed during the data run`**——这是并发假红，不是装载坏了（D.3 已遇到过 3 次） |

### 7.3 建议的切换后核验顺序（10 分钟）

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests\test_v3_sql_fast.py tests\test_v3_sql.py -q
.\.venv\Scripts\python.exe -c "from causal_growth.data.v3_sql import load_facts_fast; print('switch ok')"
```
`load_facts_fast` 能从 `v3_sql` 名字空间取到，说明第 21 行的 import 生效且没有循环导入。

### 7.4 一个需要你决定的事：`sql_source_hash()` 要不要覆盖装载器

现在 `sql_source_hash()` 只哈希 `sql/v3_schema.sql`、`sql/v3_analytics.sql`、`v3_sql.py`。
切换后装载实现在 `v3_sql_fast.py` 里，**它的字节不会进 `sql_sha256`**——即"装载器被换了但 SQL 溯源哈希不变"。
这正好符合"SQL 语义未变"的叙事；但如果你希望"装载实现也是 SQL 产物溯源的一部分"，需要把
`Path(v3_sql_fast.__file__)` 加进 `sql_source_hash()` 的 paths（改 `v3_sql.py`，不在我的授权内）。
两条路我都能接受，默认走前者（不动 `sql_source_hash`），因为改动它会牵连所有已绑定 `sql_sha256` 的产物。

---

## 8. 复现

### 8.1 我自己用的脚本（都在临时目录，未入库）

| 脚本 | 作用 | 产物 |
|---|---|---|
| `bench_d4.py` | A–E 五段：单批装载、`run_sql_pipeline` 的 A/B、PRAGMA 2×2（文件库）、chunk 扫描、完整链路 A/B | `outputs/tables/v3_phase_D_sql_bench.csv` 的 `meta/tables/A–E` 行 |
| `probe.py` | 独立进程的 chunk/内存探针 + 三个被否决的变体 | CSV 的 `F_chunk_probe`、`G_rejected_variants` 行 |
| `evidence_tables.py` | n=200,000 逐表指纹（行数/typeof/内容哈希/DDL） | CSV 的 `H_evidence_tables` 行 |
| `bench_append.py` | 把上面两段的实测数字并入同一张 CSV，并加 `source_label` 列 | 最终 CSV |

CSV 各段是**不同批次实测**拼起来的（A–E 一次进程；F/G 独立进程；H 又一次），每行 `note` 里写了口径。
`outputs/tables/v3_phase_D_sql_bench.csv` 顶部有 `source_label` 列 = `合成数据 / 已知 DGP`。

### 8.2 最小复现（复制到临时文件即可跑，约 3 分钟 @n=200000）

```python
import shutil, sys, time
from pathlib import Path
import pandas as pd
ROOT = Path(r"D:\L\practice_project\营销数分项目")
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from causal_growth.data import v3_pipeline, v3_sql
from causal_growth.data.v3_dirt import deduplicate_events, inject_dirt
from causal_growth.data.v3_sql_fast import load_facts_fast
from causal_growth.data.v3_storage import dataframe_sha256
from causal_growth.data.v3_tables import build_raw_tables
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.v3_config import load_v3_protocol
from test_v3_sql_fast import _legacy_load_facts          # 冻结的旧实现

N = 200_000
cfg = load_v3_protocol().scenario("L1_main")
pop = generate_v3_population(cfg, 0, n=N)
raw = build_raw_tables(*pop.observation_bundle(), cfg, run_id="bench", rep_id=0,
                       stream_prefix=pop.metadata["stream_prefix"])
dirty = inject_dirt(raw, cfg, rep_id=0, stream_prefix=pop.metadata["stream_prefix"]).tables
clean = deduplicate_events(dirty, cfg).tables

def measure(loader, chunk):
    v3_sql._load_facts = lambda connection, tables, _c: loader(connection, tables, chunk)
    started = time.perf_counter()
    result = v3_sql.run_sql_pipeline(clean, cfg)
    return time.perf_counter() - started, result.analysis_sha256

print("legacy", measure(_legacy_load_facts, 10_000))
print("fast  ", measure(load_facts_fast, 50_000))

# 完整链路 A/B（benchmark-only：中和并发写盘假红；正式运行不要这样做）
v3_pipeline.pipeline_source_hashes = lambda: {"neutralised": "benchmark"}
for label, loader, chunk in (("legacy", _legacy_load_facts, 10_000), ("fast", load_facts_fast, 50_000)):
    v3_sql._load_facts = lambda connection, tables, _c, l=loader, k=chunk: l(connection, tables, k)
    directory = Path.home() / "d4_bench" / label
    shutil.rmtree(directory, ignore_errors=True)
    started, cpu = time.perf_counter(), time.process_time()
    out = v3_pipeline.build_observed_pipeline(pop.users, pop.assignments, pop.observed_orders, cfg,
        directory=directory, run_id="d4bench", rep_id=0, stream_prefix=pop.metadata["stream_prefix"],
        persist_database=False, retention_scope="engineering_full")
    print(label, "wall", round(time.perf_counter() - started, 2), "cpu", round(time.process_time() - cpu, 2),
          dataframe_sha256(out.dataset.observations))
    shutil.rmtree(directory, ignore_errors=True)
```

### 8.3 用既有测试套件验证"切换后不红"（不改任何文件）

```powershell
$env:PYTHONPATH = '<把 d4plugin.py 所在目录放这里>'
.\.venv\Scripts\python.exe -m pytest tests\test_v3_sql.py tests\test_v3_quality.py `
    tests\test_v3_observed.py tests\test_v3_tables.py tests\test_v3_dirt.py -q -p d4plugin
.\.venv\Scripts\python.exe -m pytest tests\test_v3_pipeline.py -q -p d4plugin
```

`d4plugin.py` 只有 6 行：

```python
def pytest_configure(config):
    from causal_growth.data import v3_sql
    from causal_growth.data.v3_sql_fast import load_facts_fast
    v3_sql._load_facts = load_facts_fast
```

---

## 9. 附：本模块对外接口

| 名字 | 作用 |
|---|---|
| `load_facts_fast(connection, tables, chunk_size=50_000)` | 与 `_load_facts` 行为等价的批量装载（本模块唯一入口） |
| `iter_fact_rows(frame, columns, chunk_size)` | 行元组生成器；缺失值→`None`，公开以便单测直接验证拆箱语义 |
| `relaxed_pragmas(connection)` | 上下文管理器：应用装载 PRAGMA，退出（含异常）恢复原值，无法恢复则 `RuntimeError` |
| `read_pragmas(connection)` | 读四项 PRAGMA 的当前值（测试/审计用） |
| `fast_fact_loading()` | 上下文管理器：只把 `v3_sql._load_facts` 临时指向 `load_facts_fast`（A/B 与灰度用，跑完还原） |
| `BUSINESS_TABLES` / `LOADED_TABLES` / `LOAD_PRAGMAS` / `DEFAULT_CHUNK_SIZE` | 常量；测试有"不漂移"断言 |
