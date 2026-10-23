import re, pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
nb = new[new.index("## 1 引言"):]
words = ["值得注意的是","此外","深入","至关重要","凸显","赋能","全面","进一步","标志着","里程碑","奠定基础","体现了","彰显","反映了","从而说明","本质上","真正的","核心在于","背后的逻辑","在一定程度上","或许","可能","三条","三项","三处","三组","三部分"]
for w in words:
    a,b = ob.count(w), nb.count(w)
    if a or b: print(f"{w:8s} {a:3d} -> {b:3d}")
print("--- 本文 total (md+tex) ---")
print("old md body", ob.count("本文"), "old md total", old.count("本文"))
print("new md body", nb.count("本文"), "new md total", new.count("本文"))
tex_old = pathlib.Path("out/paper_check/orig_main.tex").read_text(encoding="utf-8")
tex_new = pathlib.Path("paper/main.tex").read_text(encoding="utf-8")
print("old tex 本文", tex_old.count("本文"), "new tex 本文", tex_new.count("本文"))
