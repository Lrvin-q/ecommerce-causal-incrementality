#!/usr/bin/env bash
# 论文四门禁一条命令：构建（可选）→ 42 数字 → 42 摘要 → 44 引用 → 43 长稿审计。
# 每步都写独立日志、单独取退出码——绝不接管道（`python x.py | tail; echo $?` 拿到的是 tail 的码）。
# 用法：bash scripts/52_paper_gates.sh [--build] [--keep-going]
set -u
cd "$(dirname "$0")/.."
PY=".venv/Scripts/python.exe"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
LOGS=out/scratch/paper_gates
BUILD_LOG=out/scratch/v3_paper_build
BUILD=0
KEEP=0
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --keep-going) KEEP=1 ;;
    *) echo "未知参数 $arg"; exit 64 ;;
  esac
done
mkdir -p "$LOGS"
SUMMARY=$LOGS/summary.txt
: > "$SUMMARY"

fail=0
step() {  # step <名字> <命令...>
  name=$1; shift
  "$@" > "$LOGS/$name.log" 2>&1
  rc=$?
  echo "$name=$rc" >> "$SUMMARY"
  if [ $rc -eq 0 ]; then
    printf '[OK  ] %s\n' "$name"
  else
    printf '[FAIL] %s rc=%s 日志 %s\n' "$name" "$rc" "$LOGS/$name.log"
    tail -3 "$LOGS/$name.log" | sed 's/^/       /'
    fail=1
    [ $KEEP -eq 1 ] || return 1
  fi
  return 0
}

if [ $BUILD -eq 1 ]; then
  step build bash paper/v3/build.sh paper/v3/body || exit 1
fi

# 42 的 --draft 只认单个文件：按 build.sh 的顺序拼 01→04
cat paper/v3/body/0[1-4]_*.md > out/scratch/draft_concat.md
echo "concat_chars=$(wc -m < out/scratch/draft_concat.md)" >> "$SUMMARY"

step claim_draft "$PY" scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --draft out/scratch/draft_concat.md || exit 1
step claim_abstract "$PY" scripts/42_claim_number_gate.py \
  --registry outputs/tables/v3_h04_claim_registry.csv --abstract paper/v3/abstract.md || exit 1
step citations "$PY" scripts/44_citation_check.py \
  --bib paper/v3/refs.bib --body-tex out/scratch/v3_paper_build/body.tex \
  --bbl out/scratch/v3_paper_build/main.bbl || exit 1
step long_draft "$PY" scripts/43_long_draft_audit.py \
  --body out/scratch/v3_paper_build/body.md --pdf out/scratch/v3_paper_build/main.pdf \
  --aux out/scratch/v3_paper_build/main.aux || exit 1

echo
if [ $fail -eq 0 ]; then
  echo "PASS：四门禁全绿（$SUMMARY）"
  exit 0
fi
echo "FAIL：见 $SUMMARY"
exit 1
