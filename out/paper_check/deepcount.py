import pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
nb = new[new.index("## 1 引言"):]
for w in ["照妖镜","使然","核心","本质","真正","背后","值得读","更深","恰是","这就是","由此可见","不难发现"]:
    a,b = ob.count(w), nb.count(w)
    if a or b: print(f"{w:6s} {a} -> {b}")
