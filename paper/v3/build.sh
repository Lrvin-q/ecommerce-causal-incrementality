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
# 正文插图以相对路径 figures/*.png 引用，xelatex 在 BUILD 目录下运行，需同目录可见。
rm -rf "$BUILD/figures"
cp -r "$HERE/figures" "$BUILD/figures"

# 目录模式：按文件名顺序拼接各章，落盘成 body.md，供 build 与 43/44 共用同一份正文。
PY="$ROOT/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY=python
if [ -d "$BODY" ]; then
  : > "$BUILD/body.md"
  for part in "$BODY"/*.md; do
    [ -e "$part" ] || continue
    cat "$part" >> "$BUILD/body.md"
    printf '\n\n' >> "$BUILD/body.md"
  done
  BODY="$BUILD/body.md"
else
  cp "$BODY" "$BUILD/body.md"
  BODY="$BUILD/body.md"
fi

# H03 视觉审计 2026-10-30：中文语境下 pandoc 的 smart 把绝大多数 ASCII " 判成右引号
# （body.tex 实测 `` : '' = 62 : 1044，PDF 上开引号全变右引号）。改为在 md 阶段按顺序
# 成对翻转 "→“/”，行内代码跨度（`...`）原样保留；各章 " 个数均为偶数，配对不会跨章漂移。
cat > "$BUILD/normalize_quotes.py" <<'PYEOF'
import pathlib, re, sys
src = pathlib.Path(sys.argv[1])
dst = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else src
t = src.read_text(encoding="utf-8")
parts = re.split(r"(`[^`\n]*`)", t)
open_q = True
out = []
for i, seg in enumerate(parts):
    if i % 2:
        out.append(seg)
        continue
    buf = []
    for ch in seg:
        if ch == '"':
            buf.append("\u201c" if open_q else "\u201d")
            open_q = not open_q
        else:
            buf.append(ch)
    out.append("".join(buf))
dst.write_text("".join(out), encoding="utf-8")
print(f"quote-normalize {src.name}: {t.count(chr(34))} ascii quotes -> curly, balanced={open_q}")
PYEOF
"$PY" "$BUILD/normalize_quotes.py" "$BODY"

pandoc "$BODY" -f markdown+pipe_tables+tex_math_dollars -t latex --biblatex --wrap=preserve \
  -o "$BUILD/body.tex"

# 长路径（\texttt{...}）默认无法断行，会把块引用撑出版心（H03「无裁切」）。
# 在每个 "/" 与 "\_" 之后插入 \allowbreak{}，让路径可以续行；不改内容，只加断行点。
"$PY" - "$BUILD/body.tex" <<'PYEOF'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
t = p.read_text(encoding="utf-8")

def brk(m):
    inner = m.group(1)
    if "/" not in inner and r"\_" not in inner:
        return m.group(0)
    inner = inner.replace("/", "/\\allowbreak{}")
    inner = inner.replace("\\_", "\\_\\allowbreak{}")
    return "\\texttt{" + inner + "}"

out, n = re.subn(r"\\texttt\{([^{}]*)\}", brk, t)
# 表题注前要求最小剩余竖直空间：不够就先分页，避免题注孤零零留在页底（H03 逐页目检）。
# 只对表生效——图题注在图片之后，往前推会把图与题注分开。
out, n_cap = re.subn(r"(?m)^(\\textbf\{表 \d+-\d+[^\n]*\})$",
                     lambda m: "\\needspace{6\\baselineskip}\n" + m.group(1), out)

# 主张登记号 [C123] 与文献引用 [1] 同形，且方括号撑宽窄列（H03 P1-5）。
# 只改排版：md 保留 [C123] 供 42 号门禁逐条回指，PDF 印成小号上标 C123。
out, n_claim = re.subn(r"(?:\{\[\}|\[)C(?P<n>\d+)(?:\{\]\}|\])",
                       r"\\textsuperscript{C\g<n>}", out)

# 数据来源注里路径多、可断点少，两端对齐会把整行拉出大空隙（badness 10000）。
# 这类块引用改成左对齐：断行位置不变，只是不再拉伸字距。
def ragged(m):
    block = m.group(0)
    if "数据来源" in block or "源表" in block:
        ragged.done += 1
        return "{\\raggedright\n" + block + "\n\\par}"
    return block

ragged.done = 0
out, n_quote = re.subn(r"\\begin\{quote\}.*?\\end\{quote\}", ragged, out, flags=re.S)
p.write_text(out, encoding="utf-8")
print(f"tex path breaks: {n} inline spans scanned; caption orphans guarded: {n_cap}; "
      f"claim ids as superscript: {n_claim}; "
      f"quotes scanned: {n_quote}, source notes set ragged: {ragged.done}")
PYEOF
"$PY" "$BUILD/normalize_quotes.py" "$HERE/abstract.md" "$BUILD/abstract.md"
{
  printf '\\begin{abstract}\n\\linespread{1.04}\\selectfont\\small\n'
  pandoc "$BUILD/abstract.md" -f markdown -t latex --wrap=preserve
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
