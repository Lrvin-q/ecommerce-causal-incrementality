import re, pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
nb = new[new.index("## 1 引言"):]
for tok in ["-0.32","0.20","01","02","03","04","05","06","20240101,","256","404","5","8","85"]:
    print("="*40, tok)
    print("OLD:")
    for m in list(re.finditer(re.escape(tok), ob))[:6]:
        print("  ...", ob[max(0,m.start()-50):m.end()+50].replace("\n"," "))
    print("NEW:")
    for m in list(re.finditer(re.escape(tok), nb))[:6]:
        print("  ...", nb[max(0,m.start()-50):m.end()+50].replace("\n"," "))
