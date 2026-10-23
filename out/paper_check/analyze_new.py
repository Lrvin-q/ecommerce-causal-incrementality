import pathlib
p = pathlib.Path("reports/00_项目总报告.md")
t = p.read_text(encoding="utf-8")
print("ascii", t.count('"'), "curly", t.count("“"), t.count("”"))
for i, line in enumerate(t.splitlines(), 1):
    n = line.count('"')
    if n % 2:
        print("ODD", i, n, line[:200])
print("emdash", t.count("——"))
body = t[t.index("## 1 引言"):]
print("body emdash", body.count("——"))
import re
print("bold pairs body", len(re.findall(r"\*\*[^*\r\n]+\*\*", body)))
print("qiyi", body.count("其一"), body.count("其二"), body.count("其三"))
print("benwen body", body.count("本文"), "total", t.count("本文"))
