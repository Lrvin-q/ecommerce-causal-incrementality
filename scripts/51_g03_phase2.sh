#!/usr/bin/env bash
# 入库副本（2026-10-29 20:19 从 out/g03_phase2.sh 逐字节复制）。
# 2026-10-30 00:39 变更：末尾新增"复合 run_summary"步骤（exit 12）——41 号要 `out/g03_formal/run_summary.json`，
# 而 34 merge 只写 merge_report.json；该步自三份源 summary + 原始分片独立核对，不依赖 merge_report 落点。
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
# 残留的复合根会让 `cp -r src dst` 静默套成 dst/<分片名>/<分片名>，merge 只会少读而不报错
if [ -d out/g03_formal/shards ] && [ -n "$(ls -A out/g03_formal/shards 2>/dev/null)" ]; then
  say "out/g03_formal/shards 已存在且非空，拒绝重复链接"
  echo "ABORT: composite root not empty" > "$STATUS"
  exit 10
fi
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
# 逐个分片确认结构仍是 <分片>/<cell>/repetitions*.csv；junction 失败回退复制时若套了一层，
# 这里会把它抓出来（只数顶层条目数抓不到嵌套）
bad_link=""
for d in out/g03_formal/shards/*; do
  if ! compgen -G "$d/*/repetitions.csv" >/dev/null && ! compgen -G "$d/*/repetitions_provisional.csv" >/dev/null; then
    bad_link="$bad_link $(basename "$d")"
  fi
done
if [ -n "$bad_link" ]; then
  say "复合根结构异常（缺 <cell>/repetitions*.csv）：$bad_link"
  echo "ABORT: composite root layout" > "$STATUS"
  exit 11
fi

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

# 41 号读 out/g03_formal/run_summary.json，但 34 merge 只写 merge_report.json（且落在 roots[0]，
# 不在根目录）。这里把三份源 summary 合成一份复合 summary，并直接从**原始分片**核对 24 格
# 各 R 行、rep 恰为 0..R-1、跨分片无重复 rep——不依赖 merge_report 的落点（junction 回退成
# 复制时会出现多份）。任何一项不符即非零退出，不凭日志口头保证。
say "生成复合 run_summary（供 41 号校验）"
"$PY" - >> "$LOGS/phase2.log" 2>&1 <<'PY'
import csv
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

CORE = {"L0_P_main", "L1_main", "L2_n200000_p050", "L3_fixed_lt000"}
TIER2 = {
    "L0_Pi_heterogeneous_cost", "L0_zero_purchase_effect",
    "L1_heterogeneity_000", "L1_heterogeneity_150", "L1_signal_weak",
    "L1_misspec_omit_new_channel", "L1_mar_double", "L1_cost_prediction_under",
    "L2_n30000_p050", "L2_n100000_p050", "L2_drift_smooth",
    "L2_composition_shift", "L2_immature_negative_control",
    "L3_fixed_lt025", "L3_fixed_lt075", "L3_fixed_lt150",
    "L3_joint_lam000", "L3_joint_lam150", "L3_overlap_extreme",
    "L3_missing_confounders",
}
WANT = {**{c: 500 for c in CORE}, **{c: 30 for c in TIER2}}

roots = {
    "phase1_core_prefix": pathlib.Path("out/g03_core_prefix"),
    "phase2a_tier2": pathlib.Path("out/g03_tier2"),
    "phase2b_core_ate": pathlib.Path("out/g03_core_ate"),
}
problems, sources = [], []
for tag, root in roots.items():
    path = root / "run_summary.json"
    if not path.is_file():
        problems.append(f"{tag}: 缺 {path}")
        continue
    blob = path.read_bytes()
    payload = json.loads(blob.decode("utf-8"))
    if payload.get("status") != "formal":
        problems.append(f"{tag}: status={payload.get('status')!r} != formal")
    if payload.get("failures"):
        problems.append(f"{tag}: failures={payload['failures'][:3]}")
    if int(payload.get("bootstrap_resamples") or 0) != 0:
        problems.append(f"{tag}: bootstrap_resamples={payload.get('bootstrap_resamples')!r} != 0")
    sources.append({
        "tag": tag, "root": root.as_posix(), "status": payload.get("status"),
        "failures": payload.get("failures"),
        "bootstrap_resamples": payload.get("bootstrap_resamples"),
        "sha256": hashlib.sha256(blob).hexdigest(),
    })

per_cell = {}
for shard in sorted(pathlib.Path("out/g03_formal/shards").iterdir()):
    if not shard.is_dir():
        continue
    for cell_dir in sorted(p for p in shard.iterdir() if p.is_dir()):
        cell = cell_dir.name
        formal = cell_dir / "repetitions.csv"
        provisional = cell_dir / "repetitions_provisional.csv"
        if formal.is_file():
            path = formal
        elif provisional.is_file():
            problems.append(f"{shard.name}: 只有 provisional（未跑满）")
            path = provisional
        else:
            problems.append(f"{shard.name}/{cell}: 没有 repetitions*.csv")
            continue
        with path.open(encoding="utf-8-sig") as handle:
            reps = [int(row["rep"]) for row in csv.DictReader(handle)]
        per_cell.setdefault(cell, []).extend(reps)
for cell, want in sorted(WANT.items()):
    reps = per_cell.get(cell, [])
    if len(reps) != want:
        problems.append(f"{cell}: 分片合计 rows={len(reps)} != R={want}")
    elif sorted(reps) != list(range(want)):
        seen, dups = set(), []
        for rep in reps:
            if rep in seen:
                dups.append(rep)
            seen.add(rep)
        problems.append(f"{cell}: rep 不是 0..{want - 1}（跨分片重复 {sorted(dups)[:5]}）")
extra = sorted(set(per_cell) - set(WANT))
if extra:
    problems.append(f"多出未注册格：{extra}")

if problems:
    print("FAIL: 复合 run_summary 不能生成：")
    for line in problems:
        print("  -", line)
    sys.exit(1)

out = pathlib.Path("out/g03_formal/run_summary.json")
if out.exists():
    print(f"FAIL: {out} 已存在，拒绝覆盖")
    sys.exit(1)
payload = {
    "status": "formal",
    "failures": [],
    "bootstrap_resamples": 0,
    "bootstrap_budget_scope": None,
    "composite": True,
    "derived_from": sources,
    "shard_rows": {cell: len(reps) for cell, reps in sorted(per_cell.items())},
    "all_complete": True,
    "at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
}
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK: 复合 run_summary 已写 {out}（{len(sources)} 份源 summary；{len(WANT)} 格分片合计已满）")
PY
rc=$?
echo "composite_summary_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then
  say "复合 run_summary 生成失败（见上），不写 OK"
  echo "ABORT: composite run_summary failed" >> "$STATUS"
  exit 12
fi

say "Phase 2 完成；下一步：41 号 --check 后导出"
echo "OK: G03 Phase2 完成 $(date '+%Y-%m-%d %H:%M:%S')" >> "$STATUS"
