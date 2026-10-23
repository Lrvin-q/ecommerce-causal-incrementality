import pathlib
p = pathlib.Path("paper/build.ps1")
raw = p.read_bytes()
print("BOM before:", raw[:3] == b"\xef\xbb\xbf")
with open(p, "r", encoding="utf-8-sig", newline="") as fh:
    text = fh.read()
old = "$tex = [regex]::Replace($tex, '(?m)^\\\\textbf\\{表 ', '\\needspace{11\\baselineskip}\\textbf{表 ')"
# locate the actual line robustly
lines = text.splitlines(keepends=True)
idx = [i for i, l in enumerate(lines) if "regex]::Replace($tex" in l and "needspace" in l]
print("match lines:", idx)
assert len(idx) == 1
i = idx[0]
insert = (
    "# 表 B1 是附录里的整表；若在页底再插 needspace，会把整表推到下一页并留下近空白页。\r\n"
    "# 其余表仍在题注前预留 11 行，防止“题注在页底、表体翻页”。\r\n"
    "$tex = $tex.Replace('\\needspace{11\\baselineskip}\\textbf{表 B1', '\\textbf{表 B1')\r\n"
)
if "表 B1" not in text:
    lines.insert(i + 1, insert)
    text = "".join(lines)
with open(p, "w", encoding="utf-8-sig", newline="") as fh:
    fh.write(text)
raw2 = p.read_bytes()
print("BOM after:", raw2[:3] == b"\xef\xbb\xbf")
print("inserted:", "表 B1" in p.read_text(encoding="utf-8-sig"))
