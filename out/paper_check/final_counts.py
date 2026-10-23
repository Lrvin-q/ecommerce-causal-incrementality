import re, pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
nb = new[new.index("## 1 引言"):]
print("=== body counts old -> new ===")
print("emdash", ob.count("——"), "->", nb.count("——"))
print("bold pairs", ob.count("**")//2, "->", nb.count("**")//2)
print("bold total", old.count("**")//2, "->", new.count("**")//2)
print("qiyi", ob.count("其一")+ob.count("其二")+ob.count("其三"), "->", nb.count("其一")+nb.count("其二")+nb.count("其三"))
print("benwen body", ob.count("本文"), "->", nb.count("本文"), "total", old.count("本文"), "->", new.count("本文"))
for w in ["三条","三项","进一步","而非","而不是","不等于","可能","此外","值得注意","至关重要","凸显","赋能","全面","深入","标志着","里程碑","奠定基础","体现了","彰显","反映了","从而说明","本质上","真正的","核心在于","背后的逻辑","在一定程度上","或许"]:
    a,b=ob.count(w),nb.count(w)
    if a or b: print(f"{w} {a} -> {b}")
print("不是...而是", len(re.findall(r"不是.{0,25}而是", ob)), "->", len(re.findall(r"不是.{0,25}而是", nb)))
print("=== remaining 而非/而不是/不等于 contexts ===")
for line in nb.splitlines():
    if any(w in line for w in ["而非","而不是","不等于"]):
        for m in re.finditer(r".{0,25}(?:而非|而不是|不等于).{0,25}", line):
            print("  ", m.group(0))
