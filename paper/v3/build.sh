#!/usr/bin/env bash
# 编译 v3 长稿：bash paper/v3/build.sh <body.md>
# 产物全部落在 out/scratch/v3_paper_build/（不入库），不改 paper/v3 源码目录。
set -euo pipefail
BODY=${1:?用法: bash paper/v3/build.sh <body.md|body目录>}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
BUILD="$ROOT/out/scratch/v3_paper_build"
mkdir -p "$BUILD"
cp "$HERE/main.tex" "$HERE/preamble.tex" "$HERE/refs.bib" "$BUILD/"

# 目录模式：按文件名顺序拼接各章，落盘成 body.md，供 build 与 43/44 共用同一份正文。
if [ -d "$BODY" ]; then
  : > "$BUILD/body.md"
  for part in "$BODY"/*.md; do
    [ -e "$part" ] || continue
    cat "$part" >> "$BUILD/body.md"
    printf '\n\n' >> "$BUILD/body.md"
  done
  BODY="$BUILD/body.md"
fi

pandoc "$BODY" -f markdown+pipe_tables+tex_math_dollars -t latex --biblatex --wrap=preserve \
  -o "$BUILD/body.tex"

# 长路径（\texttt{...}）默认无法断行，会把块引用撑出版心（H03「无裁切」）。
# 在每个 "/" 后插入 \allowbreak{}，让路径可以续行；不改内容，只加断行点。
PY="$ROOT/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY=python
"$PY" - "$BUILD/body.tex" <<'PYEOF'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
t = p.read_text(encoding="utf-8")

def brk(m):
    inner = m.group(1)
    return m.group(0) if "/" not in inner else "\\texttt{" + inner.replace("/", "/\\allowbreak{}") + "}"

out, n = re.subn(r"\\texttt\{([^{}]*)\}", brk, t)
p.write_text(out, encoding="utf-8")
print(f"tex path breaks: {n} inline spans scanned")
PYEOF
{
  printf '\\begin{abstract}\n\\linespread{1.04}\\selectfont\\small\n'
  pandoc "$HERE/abstract.md" -f markdown -t latex --wrap=preserve
  printf '\n\\end{abstract}\n'
} > "$BUILD/abstract.tex"

cd "$BUILD"
xelatex --disable-installer -interaction=nonstopmode -halt-on-error main.tex > pass1.log 2>&1 || {
  echo "PASS1 FAILED"; tail -30 pass1.log; exit 1; }
biber main > biber.log 2>&1 || { echo "BIBER FAILED"; tail -30 biber.log; exit 1; }
for pass in pass2 pass3; do
  xelatex --disable-installer -interaction=nonstopmode -halt-on-error main.tex > "$pass.log" 2>&1 || {
    echo "${pass^^} FAILED"; tail -30 "$pass.log"; exit 1; }
done
echo "BUILD OK: $BUILD/main.pdf"
