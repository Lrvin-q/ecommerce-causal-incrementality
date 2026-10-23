import pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
nb = new[new.index("## 1 引言"):]
for w in ["体现了","彰显","反映了","从而说明","标志着","里程碑","奠定基础","进一步","此外","值得注意","至关重要","凸显","赋能","全面","深入","在一定程度上","或许"]:
    a,b = ob.count(w), nb.count(w)
    print(f"{w:8s} {a} -> {b}")
