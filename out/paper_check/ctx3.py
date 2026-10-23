import pathlib
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
nb = new[new.index("## 1 引言"):]
for i, line in enumerate(nb.splitlines(), 1):
    if "三条" in line or "可能" in line:
        print(i, line.strip()[:180])
