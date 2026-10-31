#!/usr/bin/env bash
# G03 收尾后刷新证据包（N1，2026-10-31 20:01）：
# 63 在 3/5 步调用 41 导出时，finalize.log/status 尚未闭合；本脚本在 63 正常结束后再导出一次。
# 6/6 标记只在导出成功之后写；失败写 FAILED 行（G04 C4/P3-3）。
set -u
cd "$(dirname "$0")/.."
PY="${G66_PY:-.venv/Scripts/python.exe}"
EXPORT="${G66_EXPORT:-scripts/41_export_g03_evidence.py}"
LOG="${G66_LOG:-out/g03_logs/finalize.log}"
STATUS="${G66_STATUS:-out/g03_logs/finalize.status}"
OUT="${G66_OUT:-out/g03_logs/post_finalize_export.status}"

if ! grep -q "^OK: G03 finalize 完成" "$STATUS" 2>/dev/null; then
  echo "ABORT: finalize.status 无 OK 行，拒绝刷新" > "$OUT"
  exit 3
fi
"$PY" "$EXPORT" > out/g03_logs/post_finalize_export.log 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  if ! grep -q "6/6 收尾后重导出" "$LOG" 2>/dev/null; then
    printf '[%s] 6/6 收尾后重导出（闭合 finalize.log/status；不改状态文件）\n' \
      "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
  fi
else
  printf '[%s] 6/6 FAILED rc=%s（见 out/g03_logs/post_finalize_export.log）\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$rc" >> "$LOG"
fi
echo "post_finalize_export_exit=$rc" > "$OUT"
exit $rc
