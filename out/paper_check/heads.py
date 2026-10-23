import re, pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
def heads(t): return [l.strip() for l in t.splitlines() if l.startswith("## ") or l.startswith("### ")]
a, b = heads(old), heads(new)
print("OLD:"); [print(" ", h) for h in a]
print("NEW:"); [print(" ", h) for h in b]
