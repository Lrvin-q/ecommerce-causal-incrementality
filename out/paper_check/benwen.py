import pathlib, re
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
oldb = old[old.index("## 1 引言"):old.index("## 附录 D")]
newb = new[new.index("## 1 引言"):]
for name, t, b in [("old", old, oldb), ("new", new, newb)]:
    print(name, "total 本文", t.count("本文"), "body 本文", b.count("本文"))
    for line in b.splitlines():
        if "本文" in line:
            print("   ", line.strip()[:120])
print("main.tex 本文", pathlib.Path("paper/main.tex").read_text(encoding="utf-8").count("本文"))
