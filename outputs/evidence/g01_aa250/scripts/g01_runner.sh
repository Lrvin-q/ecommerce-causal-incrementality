#!/usr/bin/env bash
# G01 AA250 正式跑：12 分片 / 6 lane，跑完自动合并 + 独立核对。
# 分片规则：4 层各切 83/83/84，rep 区间互不相交（17 号按 (block, rep) 去重，重叠会被静默吞掉）。
set -u
cd "$(dirname "$0")/.." || exit 1
PY=".venv/Scripts/python.exe"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
APPROVAL="G01-AA250-20261028"
SNAP="out/g01_snapshot"
ROOT="out/g01_aa250"
LOGS="out/g01_logs"
mkdir -p "$ROOT" "$LOGS"

TZ=Asia/Shanghai date "+%Y-%m-%d %H:%M:%S" > "$LOGS/started_at.txt"

run_shard() {
  tag="$1"; layer="$2"; start="$3"; reps="$4"
  "$PY" scripts/36_g_aa_run.py run --status formal --formal-approval "$APPROVAL" \
    --snapshot "$SNAP" --workers 1 --layers "$layer" --rep-start "$start" --reps "$reps" \
    --out-root "$ROOT/$tag" > "$LOGS/${tag}.log" 2>&1
  echo "$?" > "$LOGS/${tag}.exit"
}

lane() {
  n="$1"; shift
  TZ=Asia/Shanghai date "+%Y-%m-%d %H:%M:%S" > "$LOGS/lane${n}.start"
  for spec in "$@"; do
    IFS=: read -r tag layer st rp <<< "$spec"
    run_shard "$tag" "$layer" "$st" "$rp"
  done
  TZ=Asia/Shanghai date "+%Y-%m-%d %H:%M:%S" > "$LOGS/lane${n}.done"
}

lane 1 s01:L0:0:83   s02:L1:0:83   &
lane 2 s03:L0:83:83  s04:L1:83:83  &
lane 3 s05:L0:166:84 s06:L1:166:84 &
lane 4 s07:L2:0:83   s08:L3:0:83   &
lane 5 s09:L2:83:83  s10:L3:83:83  &
lane 6 s11:L2:166:84 s12:L3:166:84 &
wait
TZ=Asia/Shanghai date "+%Y-%m-%d %H:%M:%S" > "$LOGS/lanes_all_done.txt"

"$PY" out/g01_verify.py > "$LOGS/verify.log" 2>&1
echo "$?" > "$LOGS/verify.exit"

"$PY" scripts/36_g_aa_run.py merge \
  "$ROOT/s01" "$ROOT/s02" "$ROOT/s03" "$ROOT/s04" "$ROOT/s05" "$ROOT/s06" \
  "$ROOT/s07" "$ROOT/s08" "$ROOT/s09" "$ROOT/s10" "$ROOT/s11" "$ROOT/s12" \
  > "$LOGS/merge.log" 2>&1
echo "$?" > "$LOGS/merge.exit"
TZ=Asia/Shanghai date "+%Y-%m-%d %H:%M:%S" > "$LOGS/finished_at.txt"
