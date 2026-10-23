import re, pathlib
old = pathlib.Path("out/paper_check/orig_main.tex").read_text(encoding="utf-8")
new = pathlib.Path("paper/main.tex").read_text(encoding="utf-8")
def abs(s):
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", s, re.S)
    return m.group(1)
a, b = abs(old), abs(new)
def cjk(s): return len(re.findall(r"[\u4e00-\u9fff]", s))
print("abstract CJK old/new:", cjk(a), cjk(b))
num = re.compile(r"(?<![\w.,])[−-]?\d+(?:,\d{3})*(?:\.\d+)?%?")
def nums(s):
    s = re.sub(r"\\tag\{\d+\}", " ", s)
    return sorted(num.findall(s))
print("old-only nums:", [x for x in nums(a) if x not in nums(b)])
print("new-only nums:", [x for x in nums(b) if x not in nums(a)])
print("main.tex emdash:", new.count("——"))
print("main.tex bold:", len(re.findall(r"\\textbf\{", new)))
print("abstract bold:", len(re.findall(r"\\textbf\{", b)))
# MD body counts
md = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
body = md[md.index("## 1 引言"):]
print("MD body emdash:", body.count("——"), "bold spans:", len(re.findall(r"\*\*.+?\*\*", body)))
print("MD body 本文:", body.count("本文"), "其一:", body.count("其一"))
print("MD ascii quotes:", md.count('"'), "curly:", md.count("“"), md.count("”"))
print("MD has 数据版本:", "数据版本" in md, "v1:", bool(re.search(r"(?<![A-Za-z0-9])v1(?![A-Za-z0-9])", md)), "v2:", bool(re.search(r"(?<![A-Za-z0-9])v2(?![A-Za-z0-9])", md)))
