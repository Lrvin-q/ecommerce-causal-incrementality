# G 阶段运行注册表（2026-10-28 23:02，北京时间）

> 合成数据 / 已知 DGP。本表对应 GOAL G04「失败重试 / 资源 / 真实进程记录，全入口可恢复」。
> **状态：进行中**——G01 尚未结束，表中标"运行中"的字段在跑完后回填；G02–G04 未启动。
> 每次改动都要写清时间与依据；不得用"应该没问题"代替实测记录。

## 1. 运行清单

| 编号 | 运行 | 批准号 | 状态 | 快照 | 起跑（北京时间） | 预计/实际结束 |
|---|---|---|---|---|---|---|
| G01 | AA 臂 4 层 × 250 = 1 000 rep，n=200 000 | `G01-AA250-20261028` | 运行中 | `out/g01_snapshot`，49 文件 `526ff53d56a54c75…` | 2026-10-28 22:42:39 | 预计 2026-10-29 05:00–07:30 |
| G02 | 重训 200（4 格 × 50）+ 固定 bootstrap 1 000（主预算） | 待批 | 未启动 | — | — | — |
| G03 | Tier2 20 格 × 30 | 待批 | 未启动 | — | — | — |
| G04 | 本注册表本身 | — | 进行中 | — | — | — |

## 2. 真实进程与资源（G01）

- **并行方式**：`--workers` 上限 = 层数（一层一进程），故 6 路采用 **rep 区间分片 + 独立 out-root**：
  `s01:L0[0,83) s02:L1[0,83) s03:L0[83,166) s04:L1[83,166) s05:L0[166,250) s06:L1[166,250)`
  `s07:L2[0,83) s08:L3[0,83) s09:L2[83,166) s10:L3[83,166) s11:L2[166,250) s12:L3[166,250)`
- **每条 lane 顺序跑 2 个分片**，共 6 lane / 12 分片；编排 `out/g01_runner.sh`（日志 `out/g01_logs/`）。
- **实测成本**：6 路并发下 132–135 s/rep（4 路 127–129 s/rep），即 6 路比 4 路慢约 5%。
- **实测资源**：6 路压力测试峰值 **10.69 GB**（全部 python 进程 RSS 之和），单进程最大 **2 003 MB**，
  同期空闲 8.82 GB；未出现 OOM 或进程被杀。
- **进程级证据**：每个分片的退出码落在 `out/g01_logs/<shard>.exit`（缺失即视为未完成），
  分片的 Python 日志带北京时间时间戳。**已知缺陷**：runner 里 `date` 落盘是 UTC（少 8 h），
  故引用时刻只用 Python 日志。
- **跑中健康检查（23:00）**：12 个 python 进程、合计 3.82 GB、单进程峰值 815 MB、空闲 14.76 GB；
  6 条 lane 进度一致（各完成 5 rep）；`grep` 全部分片日志**无** Traceback / 源码漂移 / 重试记录。

## 3. 失败重试与可恢复入口

| 入口 | 重试参数 | 断点续跑 | 备注 |
|---|---|---|---|
| `scripts/34_g_matrix_run.py` | `max_source_retries`（数据作业内） | `--resume` | 网格 / 单格；`plan|run|merge` |
| `scripts/36_g_aa_run.py` | 同上 | `--resume`（`_resume_source` 按 mtime 取该层最近的完整表） | AA 专用；`plan|run|merge` |
| `scripts/17_merge_aa_layers.py` | 无（纯合并） | 幂等：重跑覆盖同名产物 | 多根合并 + `(block, rep)` 去重 |
| `scripts/37_export_g01_evidence.py` | 无 | 幂等：重跑覆盖证据目录 | `--check` 只复算不写盘 |

**重跑纪律**：17 号合并会覆盖 `outputs/tables/v3_phase_D_aa_formal_merged.*`（D 阶段同名产物）；
D 阶段原字节已归档到 `outputs/evidence/d02_aa_phase_d_20261027/`（8 文件 + manifest.json，含 sha256/bytes），
任何重跑后都必须先确认该归档仍在，再引用 D 阶段数字。

## 4. 复现验证（G01 完成后回填）

- [ ] `out/g01_verify.py`：12 分片拼成 4 层 × 250、无重复/缺口、`n_total`/`alpha`/`protocol_config_hash` 唯一
- [ ] `scripts/17` 合并表与 `scripts/37` 独立复算逐格差 ≤ 1e-12
- [ ] 12 个 `.exit` 全 0
- [ ] 证据导出 + 顶层登记（`scripts/33`）exit 0，且 `--dry-run` 与写盘后的记录数一致
- [ ] G01 报告 `docs/v3_phase_G01_formal.md` 的每个数字都能从 `outputs/evidence/g01_aa250/` 重建

## 5. 跑完后的命令序列（照抄即可，全部在项目根目录执行）

```bash
# 0) 看收尾链是否已自动完成（OK / ABORT）
cat out/g01_logs/post.status

# 1) 若 post 链 ABORT 在导出步，手动顺序执行（先看日志再重跑，幂等）
.venv/Scripts/python.exe scripts/37_export_g01_evidence.py
.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g01_aa250 --dry-run
.venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs g01_aa250

# 2) 出报告数字（只读；末行给出"复算 vs 17 号表"的最大绝对差，必须 ≤1e-12）
.venv/Scripts/python.exe out/scratch/g01_report_numbers.py

# 3) 用数字填 out/scratch/g01_report_skeleton.md 的两张表，写成 docs/v3_phase_G01_formal.md
# 4) 翻 GOAL G01 行（"未证实"→"通过"，并写明合并判定与逐层只作描述）
# 5) 刷新 TODO.md / docs/v3_决策与反思日志.md / AGENT_HANDOFF.md / 本注册表 §4 清单
# 6) 提交并推送（推送此前连续 3 次 443 超时，网络恢复后重试）
git add -A && git commit -m "G|g01: 正式 AA 1000 次完成，报告与证据入库"
git push origin codex/d03
```

**禁止**：在导出/登记未成功前把 G01 记成"通过"；在 `out/g01_logs/*.exit` 未齐 12 个 0 之前做合并结论。
