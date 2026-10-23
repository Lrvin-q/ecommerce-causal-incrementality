import re, pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
nb = new[new.index("## 1 引言"):new.index("## 附录 B")]
pat = re.compile(r"(?<![户事件配单果据])表\s*([0-9]+[a-z]?)")
a = pat.findall(ob); b = pat.findall(nb)
print("old", a)
print("new", b)
print("same:", a == b)
