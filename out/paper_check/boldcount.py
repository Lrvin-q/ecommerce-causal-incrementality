import re, pathlib
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
for name, t in [("old", old), ("new", new)]:
    b = t[t.index("## 1 引言"):]
    print(name, "body ** delimiters", b.count("**"), "pairs", b.count("**")//2,
          "regex spans", len(re.findall(r"\*\*(.+?)\*\*", b, re.S)))
    print(name, "total ** delimiters", t.count("**"), "pairs", t.count("**")//2)
