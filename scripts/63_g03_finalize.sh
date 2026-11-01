#!/usr/bin/env bash
# G03 收尾链（Phase 2 OK 之后跑）：41 --check → 62 篡改演练 → 41 导出 → 33 --dry-run → 48 取数
# 33 实登记默认不做：人工复核 dry-run 报告后，加 --with-register 重跑本脚本。
# 幂等：41 导出会先把旧证据目录改名备份；33 对已登记同 sha 跳过。
set -u
cd "$(dirname "$0")/.."
PY=".venv/Scripts/python.exe"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
LOGS=out/g03_logs
STATUS=$LOGS/finalize.status
REGISTER=0
[ "${1:-}" = "--with-register" ] && REGISTER=1
rm -f "$STATUS"
say() { date "+[%Y-%m-%d %H:%M:%S] $*" | tee -a "$LOGS/finalize.log"; }

if ! grep -q "^OK: G03 Phase2" "$LOGS/phase2.status" 2>/dev/null; then
  say "Phase 2 未完成（缺 $LOGS/phase2.status 的 OK 行），拒绝收尾"
  echo "ABORT: phase2 not ok" > "$STATUS"
  exit 3
fi

say "1/5 41 --check（24 格、契约列、复算对账、矩阵与固定两张 run_summary）"
"$PY" scripts/41_export_g03_evidence.py --check >> "$LOGS/finalize.log" 2>&1
rc=$?
echo "check_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "41 --check 失败 rc=$rc"; echo "ABORT: check failed" >> "$STATUS"; exit 4; fi

say "2/5 G04 失败→恢复演练（62：基线 0 → 注入重复 rep 必被拒 → 复原回 0）"
"$PY" scripts/62_g04_tamper_drill.py >> "$LOGS/finalize.log" 2>&1
rc=$?
echo "drill_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "62 演练失败 rc=$rc"; echo "ABORT: drill failed" >> "$STATUS"; exit 5; fi

say "3/5 41 导出证据（staging + 原子换名）"
"$PY" scripts/41_export_g03_evidence.py >> "$LOGS/finalize.log" 2>&1
rc=$?
echo "export_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "41 导出失败 rc=$rc"; echo "ABORT: export failed" >> "$STATUS"; exit 6; fi

say "4/5 33 --dry-run（只预览；实登记须人工复核后加 --with-register）"
"$PY" scripts/33_register_evidence_top.py --dirs g02_formal g03_formal --dry-run \
  >> "$LOGS/finalize.log" 2>&1
rc=$?
echo "register_dry_run_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "33 dry-run 失败 rc=$rc"; echo "ABORT: register dry-run failed" >> "$STATUS"; exit 7; fi

say "5/5 48 取数（只读；Tier1 与 Tier2 分区打印，禁止并列排序）"
"$PY" scripts/48_g03_matrix_report.py > "$LOGS/g03_matrix_report.txt" 2>&1
rc=$?
echo "report48_exit=$rc" >> "$STATUS"
if [ $rc -ne 0 ]; then say "48 取数失败 rc=$rc（见 $LOGS/g03_matrix_report.txt）"; echo "ABORT: report48 failed" >> "$STATUS"; exit 8; fi

if [ $REGISTER -eq 1 ]; then
  say "33 实登记"
  "$PY" scripts/33_register_evidence_top.py --dirs g02_formal g03_formal >> "$LOGS/finalize.log" 2>&1
  rc=$?
  echo "register_exit=$rc" >> "$STATUS"
  if [ $rc -ne 0 ]; then say "33 实登记失败 rc=$rc"; echo "ABORT: register failed" >> "$STATUS"; exit 9; fi
else
  say "33 仍为 dry-run；人工复核后加 --with-register 重跑本脚本"
fi

say "收尾链通过；下一步：填 G03 §3（带 §3.0 D1-A 披露）→ 49 全套 → G04 收口"
echo "OK: G03 finalize 完成 $(date '+%Y-%m-%d %H:%M:%S')" >> "$STATUS"
