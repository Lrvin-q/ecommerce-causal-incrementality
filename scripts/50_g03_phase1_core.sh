#!/usr/bin/env bash
# 入库副本（2026-10-29 20:19 从 out/g03_phase1_core.sh 逐字节复制，逻辑未改）。
# out/ 不入库，故此后以本文件为准；本次运行的实例是 out/ 下那份（19:36:30 启动）。
# G03 Phase 1：core 4 格 × rep0–99（学习/验证前缀），产出 core 全部策略/决策结果。
# Tier2 20 格与 core rep100–499（仅 ATE）留待 Phase 2；分批各用独立 out-root，
# 最后 merge 多根合并去重（_final 仍按 R_ate=500 判完整）。
set -u
cd "$(dirname "$0")/.."
PY=".venv/Scripts/python.exe"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
LOGS=out/g03_logs
mkdir -p "$LOGS"
STATUS=$LOGS/phase1.status
rm -f "$STATUS"
say() { date "+[%Y-%m-%d %H:%M:%S] $*" | tee -a "$LOGS/phase1.log"; }

if [ -e out/g03_core_prefix/shards ]; then
  say "out/g03_core_prefix/shards 已存在，拒绝重复写"
  echo "ABORT: out-root exists" > "$STATUS"
  exit 4
fi

say "Phase 1 开始：core 4 格 × rep0–99，shard-size 10，6 路"
"$PY" scripts/34_g_matrix_run.py run --status formal --formal-approval G03-FORMAL-20261029 \
  --snapshot out/g03_snapshot \
  --cells L0_P_main L1_main L2_n200000_p050 L3_fixed_lt000 \
  --rep-start 0 --rep-stop 99 --workers 6 --shard-size 10 \
  --out-root out/g03_core_prefix --summary-dir out/g03_core_prefix/summaries \
  >> "$LOGS/phase1.log" 2>&1
rc=$?
echo "phase1_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "Phase 1 失败 rc=$rc"; exit 5; fi
say "Phase 1 跑完，开始合并 40 个分片"

"$PY" scripts/34_g_matrix_run.py merge out/g03_core_prefix/shards/* \
  --summary-dir out/g03_core_prefix/summaries --final-parent out/g03_core_prefix \
  >> "$LOGS/phase1.log" 2>&1
rc=$?
echo "merge_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "合并失败 rc=$rc"; exit 6; fi

"$PY" - >> "$LOGS/phase1.log" 2>&1 <<'PY'
import collections
import csv
import pathlib

root = pathlib.Path("out/g03_core_prefix/_final")
for cell in sorted(p for p in root.iterdir() if p.is_dir()):
    path = cell / "repetitions_provisional.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    models = collections.Counter(row["chosen_model"] for row in rows)
    print(f"{cell.name}: rows={len(rows)} models={dict(models)}")
PY

say "Phase 1 完成并合并（provisional：R=100/500，Tier2 未跑）"
echo "OK: G03 Phase1 core prefix 完成 $(date '+%Y-%m-%d %H:%M:%S')" >> "$STATUS"
