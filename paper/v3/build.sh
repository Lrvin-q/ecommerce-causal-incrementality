#!/usr/bin/env bash
# 编译 v3 长稿：bash paper/v3/build.sh <body.md>
# 产物全部落在 out/scratch/v3_paper_build/（不入库），不改 paper/v3 源码目录。
set -euo pipefail
BODY=${1:?用法: bash paper/v3/build.sh <body.md>}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
BUILD="$ROOT/out/scratch/v3_paper_build"
mkdir -p "$BUILD"
cp "$HERE/main.tex" "$HERE/preamble.tex" "$HERE/refs.bib" "$BUILD/"

pandoc "$BODY" -f markdown+pipe_tables+tex_math_dollars -t latex --biblatex --wrap=preserve \
  -o "$BUILD/body.tex"
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
