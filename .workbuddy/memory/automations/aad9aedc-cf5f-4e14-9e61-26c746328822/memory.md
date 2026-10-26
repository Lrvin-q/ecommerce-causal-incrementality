# 自动化执行记录 — C3 功效格三路检查

## 2026-10-27 03:31（北京时间）
- 结论：**未跑完**，三路 `local_power_summary.csv` 全部缺失（L0/L1/L2）。未执行合并脚本，未做任何写操作。
- 进度（按 tmp 目录名数值解析，非字符串排序）：
  - L0 第 5 格 mde200 进行到 rep81；L1 rep80；L2 rep77（L2 tmp 另有 mde000 rep10、mde050 rep9 为 10-26 遗留的陈旧目录，非当前进度）
  - 每层 4/5 格（mde000/050/100/150 各 100 rep，合计 400 行）已完成，写入 `local_power_repetitions.csv`；第 5 格行数据只在格结束后批量落盘，故只能靠 tmp 目录名看进度
- 网格确认：`configs/v3/design.yaml` → `relative_to_observed_design_mde: [0.0,0.5,1.0,1.5,2.0]`，`repeats_per_point: 100` → 每层 5 格 × 100 rep，三层共 15 格
- 单次重复耗时约 136 秒（mde150 实测均值，三层一致）
- 三个 `.venv/Scripts/python` 进程（PID 488/489/492）存活，进度在推进（两次采样间 L0 rep80→81、L1 79→80）
- 预计完成：约 2026-10-27 04:15–04:25（北京时间）
- 下次运行建议：直接重跑本自动化；三文件齐备后执行 `19_finalize_local_power.py` 并汇报 15 格指标与 boundary_zero_margin 清单
