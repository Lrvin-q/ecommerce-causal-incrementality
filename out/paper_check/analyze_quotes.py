import re, pathlib
p = pathlib.Path("reports/00_项目总报告.md")
t = p.read_text(encoding="utf-8")
body = t[t.index("## 1 引言"):]
print("=== quote counts ===")
print("ascii dquote", t.count('"'), "curly open", t.count("“"), "curly close", t.count("”"))
print("=== lines with odd ascii quotes ===")
for i, line in enumerate(t.splitlines(), 1):
    n = line.count('"')
    if n % 2:
        print(i, n, line[:160])
print("=== lines with ascii quotes ===")
for i, line in enumerate(t.splitlines(), 1):
    if '"' in line:
        print(i, line.count('"'), line[:200])
