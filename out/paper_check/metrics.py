import re, pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
nb = new[new.index("## 1 引言"):]
words = ["值得注意的是","此外","深入","至关重要","凸显","赋能","全面","进一步","标志着","里程碑","奠定基础","体现了","彰显","反映了","从而说明","本质上","真正的","核心在于","背后的逻辑","在一定程度上","或许","其一","其二","其三"]
for w in words:
    a, b = ob.count(w), nb.count(w)
    if a or b:
        print(f"{w:10s} {a:3d} -> {b:3d}")
print("dash", ob.count("——"), "->", nb.count("——"))
print("bold spans", len(re.findall(r"\*\*.+?\*\*", ob)), "->", len(re.findall(r"\*\*.+?\*\*", nb)))
print("benwen", ob.count("本文"), "->", nb.count("本文"))
print("bushi...ershi", len(re.findall(r"不是.{0,20}而是", ob)), "->", len(re.findall(r"不是.{0,20}而是", nb)))
print("erfei", ob.count("而非"), "->", nb.count("而非"))
print("erbushi", ob.count("而不是"), "->", nb.count("而不是"))
print("budengyu", ob.count("不等于"), "->", nb.count("不等于"))
