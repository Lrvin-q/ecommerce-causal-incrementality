import re, pathlib
t = pathlib.Path("paper/main.tex").read_text(encoding="utf-8")
m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", t, re.S)
s = m.group(1)
s = re.sub(r"\\textbf\{([^}]*)\}", r"\1", s)
cjk = re.findall(r"[\u4e00-\u9fff]", s)
print("old abstract CJK chars:", len(cjk), "total chars:", len(s.strip()))
# new draft from md
md = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
new = md.split("**摘要**")[1].split("**关键词**")[0].strip()
cjk2 = re.findall(r"[\u4e00-\u9fff]", new)
print("new md abstract CJK chars:", len(cjk2), "total chars:", len(new))
