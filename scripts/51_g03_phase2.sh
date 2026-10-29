#!/usr/bin/env bash
# 入库副本（2026-10-29 20:19 从 out/g03_phase2.sh 逐字节复制，逻辑未改）。
# out/ 不入库，故此后以本文件为准；Phase 2 请用 `nohup bash scripts/51_g03_phase2.sh`。
# G03 Phase 2：Tier2 20 格（rep0–29）+ core rep100–499（仅 ATE），随后建复合根并三阶段合并。
# 前置：Phase 1 已完成（out/g03_logs/phase1.status 出现 OK）；共用快照 6fdaf7bb…。
# 为什么建复合根：41 号只认一个 matrix root 的 shards/<cell>_s*/<cell>，而三批分片分别在三个根。
# 分片名冲突用索引偏移解决：Phase 2b 的 s0000 链成 s10000，仍匹配 {cell}_s*。
set -u
cd "$(dirname "$0")/.."
PY=".venv/Scripts/python.exe"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
LOGS=out/g03_logs
STATUS=$LOGS/phase2.status
rm -f "$STATUS"
say() { date "+[%Y-%m-%d %H:%M:%S] $*" | tee -a "$LOGS/phase2.log"; }

CORE="L0_P_main L1_main L2_n200000_p050 L3_fixed_lt000"
TIER2="L0_Pi_heterogeneous_cost L0_zero_purchase_effect L1_heterogeneity_000 L1_heterogeneity_150 L1_signal_weak L1_misspec_omit_new_channel L1_mar_double L1_cost_prediction_under L2_n30000_p050 L2_n100000_p050 L2_drift_smooth L2_composition_shift L2_immature_negative_control L3_fixed_lt025 L3_fixed_lt075 L3_fixed_lt150 L3_joint_lam000 L3_joint_lam150 L3_overlap_extreme L3_missing_confounders"

if ! grep -q "^OK: G03 Phase1" "$LOGS/phase1.status" 2>/dev/null; then
  say "Phase 1 未完成（缺 $LOGS/phase1.status 的 OK 行），拒绝启动"
  echo "ABORT: phase1 not ok" > "$STATUS"
  exit 3
fi
for d in out/g03_tier2/shards out/g03_core_ate/shards; do
  if [ -e "$d" ]; then say "$d 已存在，拒绝重复写"; echo "ABORT: out-root exists" > "$STATUS"; exit 4; fi
done

say "Phase 2a：Tier2 20 格 × rep0–29（shard-size 10，6 路）"
"$PY" scripts/34_g_matrix_run.py run --status formal --formal-approval G03-FORMAL-20261029 \
  --snapshot out/g03_snapshot --cells $TIER2 --rep-start 0 --rep-stop 29 \
  --workers 6 --shard-size 10 --out-root out/g03_tier2 --summary-dir out/g03_tier2/summaries \
  >> "$LOGS/phase2.log" 2>&1
rc=$?
echo "tier2_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "Phase 2a 失败 rc=$rc"; exit 5; fi

say "Phase 2b：core rep100–499（仅 ATE，shard-size 50，6 路）"
"$PY" scripts/34_g_matrix_run.py run --status formal --formal-approval G03-FORMAL-20261029 \
  --snapshot out/g03_snapshot --cells $CORE --rep-start 100 --rep-stop 499 \
  --workers 6 --shard-size 50 --out-root out/g03_core_ate --summary-dir out/g03_core_ate/summaries \
  >> "$LOGS/phase2.log" 2>&1
rc=$?
echo "core_ate_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "Phase 2b 失败 rc=$rc"; exit 6; fi

say "建复合根 out/g03_formal/shards（junction；失败回退为复制）"
mkdir -p out/g03_formal/shards
link_or_copy() {
  src=$1; dst=$2
  cmd //c mklink //J "$(cygpath -w "$dst")" "$(cygpath -w "$src")" >/dev/null 2>&1 \
    || cp -r "$src" "$dst"
}
for src in out/g03_core_prefix/shards/*; do
  name=$(basename "$src")
  link_or_copy "$src" "out/g03_formal/shards/$name" || { say "链接失败 $name"; exit 7; }
done
for src in out/g03_tier2/shards/*; do
  name=$(basename "$src")
  link_or_copy "$src" "out/g03_formal/shards/$name" || { say "链接失败 $name"; exit 7; }
done
for src in out/g03_core_ate/shards/*; do
  name=$(basename "$src")
  cell=${name%_s*}
  idx=${name##*_s}
  dst="out/g03_formal/shards/${cell}_s1${idx}"
  link_or_copy "$src" "$dst" || { say "链接失败 $dst"; exit 7; }
done
say "复合根分片数：$(ls out/g03_formal/shards | wc -l)"

say "合并（多根去重应在复合根内一次性完成）"
"$PY" scripts/34_g_matrix_run.py merge out/g03_formal/shards/* \
  --summary-dir outputs/tables --final-parent out/g03_formal \
  >> "$LOGS/phase2.log" 2>&1
rc=$?
echo "merge_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "合并失败 rc=$rc"; exit 8; fi

"$PY" - >> "$LOGS/phase2.log" 2>&1 <<'PY'
import csv
import pathlib
import sys

core = {"L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"}
root = pathlib.Path("out/g03_formal/_final")
bad = []
for cell in sorted(p for p in root.iterdir() if p.is_dir()):
    formal = cell / "repetitions.csv"
    path = formal if formal.is_file() else cell / "repetitions_provisional.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    want = 500 if cell.name in core else 30
    print(f"{cell.name}: rows={len(rows)}/{want} file={path.name}")
    if len(rows) != want or not formal.is_file():
        bad.append(cell.name)
if bad:
    print(f"FAIL: _final 不完整 {bad}")
    sys.exit(1)
print(f"OK: _final 24 格行数齐全")
PY
rc=$?
echo "final_check_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then
  say "复合根合并后 _final 行数不齐（见上），不写 OK"
  echo "ABORT: _final incomplete" >> "$STATUS"
  exit 9
fi

say "Phase 2 完成；下一步：41 号 --check 后导出"
echo "OK: G03 Phase2 完成 $(date '+%Y-%m-%d %H:%M:%S')" >> "$STATUS"
