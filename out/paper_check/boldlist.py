import re, pathlib
md = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
body = md[md.index("## 1 引言"):]
for m in re.finditer(r"\*\*(.+?)\*\*", body, re.S):
    s = m.group(1).replace("\n", " ")
    print(repr(s[:90]))
