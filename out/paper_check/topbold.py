import re, pathlib
t = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
top = t[:t.index("## 1 引言")]
for m in re.finditer(r"\*\*(.+?)\*\*", top, re.S):
    print(repr(m.group(1)))
