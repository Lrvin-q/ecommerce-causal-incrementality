import re, pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
nb = new[new.index("## 1 引言"):new.index("## 附录 B")]
def seq(t, ch):
    # exclude bold table captions to focus on in-text references
    return re.findall(ch + r"\s*([0-9]+[a-z]?)", t)
for ch in ["表","图"]:
    a, b = seq(ob, ch), seq(nb, ch)
    print(ch, "old", a)
    print(ch, "new", b)
    print("same:", a == b)
