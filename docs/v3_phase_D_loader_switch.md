# Phase D 装载器切换与 C 级等价性重绑

> 合成数据 / 已知 DGP。维护时间：2026-10-25 13:12（北京时间）。
> 本文记录一次**触及 C 阶段已冻结源码**的优化，以及为保持验收有效所做的重绑证据。

## 1. 改了什么

`src/causal_growth/data/v3_sql.py` 两处：

| 位置 | 改动 |
|---|---|
| 导入区 | 新增 `from causal_growth.data.v3_sql_fast import load_facts_fast` |
| `run_sql_pipeline`（原第 201 行） | `_load_facts(...)` → `load_facts_fast(...)` |

`src/causal_growth/data/v3_sql_fast.py` 一处：

| 位置 | 改动 |
|---|---|
| `LOAD_PRAGMAS` | 四项批量 PRAGMA → **空元组 `()`** |

旧实现 `_load_facts` / `_scalar` **原样保留**，作为 `test_frozen_reference_matches_v3_sql` 的漂移守护。

## 2. 为什么置空 PRAGMA

D.4 实测：文件库 227 MiB，旧 26.28→25.36 s、新 12.51→12.39 s，**差异均在噪声内**。原因是整批装载本来就在一个大事务里、回滚日志页数极少、只发生一次 fsync。

而 `journal_mode=OFF` 期间若进程崩溃，可能留下**不可回滚**的库。**零收益的风险不承担**，故置空。恢复办法与恢复机制（读原值→登记→try/finally→读回校验）都保留在模块里，改回四项即可。

对应测试调整：`test_pragmas_take_effect_during_loading_and_are_restored_afterwards` 加 `skipif(not LOAD_PRAGMAS)`；新增 `test_empty_pragma_tuple_touches_nothing` 断言置空时连接状态逐项不变。

## 3. 等价性证据（三层，逐层加强）

### 3.1 逐表六维度（D.4，n=200,000）

行数 / `PRAGMA table_info` / `typeof()` 分布 / 规范内容哈希 / `rowid` 插入序 / `sqlite_master` 全量文本，全部 `identical=True`。含 **1,398,380 行 `user_events`**。

### 3.2 同一 `run_id` 下的全链路 A/B（主控，n=200,000）

同一进程、同一输入、**同一 `run_id`** 跑两遍（A 路临时把 `load_facts_fast` 换回旧 `_load_facts`）：

| 项 | 旧装载器 | 新装载器 | 一致 |
|---|---|---|---|
| `sql_sha256` | `4cbf830621ac7ed4…` | `4cbf830621ac7ed4…` | ✅ |
| `analysis_sha256` | `0eb2bf04ea82829d…` | `0eb2bf04ea82829d…` | ✅ |
| 观测表 `dataframe_sha256` | `0eb2bf04ea82829d…` | `0eb2bf04ea82829d…` | ✅ |

**为什么必须同一 `run_id`**：观测表的 `dataframe_sha256` 含 `run_id` 列。主控第一次比对用了不同的 `run_id`（`switch_check`），哈希自然不同——那是**比对设计错误**，不是装载器差异。此条留作教训：跨运行比对哈希前，先确认哈希输入里有没有运行标识列。

### 3.3 套件内的双装载器一致性

`tests/test_v3_sql_fast.py::test_sql_pipeline_output_is_identical_under_both_loaders` 在同进程内互换装载器比对整条 SQL 链路产出，已随全量回归通过。

## 4. 源码指纹变化与重绑（关键）

| 指纹 | 旧值 | 新值 |
|---|---|---|
| `sql_source_hash()` | `18fe196809535533…` | **`4cbf830621ac7ed4…`** |

`sql_source_hash()` 覆盖 `sql/v3_schema.sql`、`sql/v3_analytics.sql`、`v3_sql.py` 自身。改了 `v3_sql.py`，指纹必然变化。

**后果与处置**：

1. `ObservedDataset.from_manifest` 会校验 `manifest["sql_sha256"] == sql_source_hash()`。因此 **C 阶段现存 3015 个产物在"当前源码"下不再可通过该守卫读取**——这是守卫的正确行为，不是缺陷。
2. 它们负载的证据仍然有效，因为 3.1 与 3.2 已证明**新旧装载器产出的产物逐位一致**。也就是说：产物内容没变，变的只是"生产它的源码指纹"。
3. 正式重复（G）会生成全新产物并绑定新指纹，不存在混用。
4. **本文件即是重绑记录**：`4cbf8306…` 为当前源码指纹，等效于旧 `18fe1968…` 在数据层面的全部承诺。

**装载器为什么不在 `sql_source_hash()` 覆盖范围内**：该哈希的语义是"SQL 语义指纹"（DDL + analytics + 执行胶水）；`v3_sql_fast.py` 是工程实现，已由 `pipeline_source_hashes()` 的 `src/causal_growth/**/v3*.py` glob 覆盖。两套哈希分工不同，不重复。

## 5. 验收凭据

| 项 | 结果 |
|---|---|
| 全量串行 pytest（无并发写盘） | **1033 passed, 1 skipped, 325.56 s**，日志见 `outputs/v3/pytest_gate.json` |
| 跳过项 | 仅 `test_pragmas_take_effect_...`（按裁决关闭 PRAGMA），另有 `test_empty_pragma_tuple_touches_nothing` 顶替 |
| 保留告警 | 1 条 B 阶段 `IntegrationWarning`（时间积分舍入），如实保留不隐去 |
| 定向回归（fast+sql+quality+observed+tables+dirt+pipeline） | 151 passed, 1 skipped, 119.71 s |

## 6. 未做

1. **未重跑 C 的完整 101 作业矩阵**。理由是 3.2 已在 20 万全规模上证明逐位一致，重跑 101 作业只能重复同一结论。若后续评审要求，可按 `scripts/12_validate_v3_data.py --scope all` 重跑。
2. **未重跑四代表库的逐行审计**。同上，等价性已由 `analysis_sha256` 与观测表哈希的逐位相同覆盖。
3. **未启用多行 `INSERT ... VALUES (...),(...)`**（可再省 4.7 s/批，全矩阵约 19.6 CPU·h）。它改变 INSERT 语句形态，需重新证明等价，收益不足。
4. **`sql.insert_chunk_size` 保持 10000**。改 50000 约省 6 CPU·h，但会改 `data_config_hash`，而 C 验收绑定了它。

## 7. 新性能基线（切换后实测，2026-10-25 13:14 北京时间）

`scripts/13_v3_pilot.py --reps 2 --n 200000 --scenario L1_main`，同一机器、无其他负载：

| 阶段 | 切换前 | 切换后 | 变化 |
|---|---|---|---|
| 五表 + 污染/清洗 + SQL | 143.7 s | **117.2 s** | −18.4%（**1.23×**） |
| Causal Forest | 116.6 s | 112.0 s | 基本不变（与装载器无关） |
| **G3 完整流程（含 DGP）** | 266.7 s | **235.4 s** | −11.7% |
| 峰值工作集 | 1,878 MB（单 rep 独占进程） | 2,439 MB（同进程 2 rep 累积） | 单 rep 仍按 1.88 GB 计 |

比 D.4 文档里估的 120 s 略好。**修订预算随之从 151 → ≈131 CPU·h**（4 路并行 ≈33 h ≈1.4 天）。

剩余成本结构：learning 批 235 s 里 **CF 占 112 s（48%）**、pipeline 117 s（50%）、其余 2%。要再显著提速只能动 CF 规格（冻结超参，需重走 A 评审），数据工程这一侧已到地板。
