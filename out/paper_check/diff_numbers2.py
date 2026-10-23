import re, pathlib, collections
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
ob = old[old.index("## 1 引言"):old.index("## 附录 D")]
nb = new[new.index("## 1 引言"):]
pat = re.compile(r"(?<![\w.,])[−-]?\d+(?:,\d{3})*(?:\.\d+)?%?")
def nums(t):
    t = re.sub(r"\\tag\{\d+\}", " ", t)
    return collections.Counter(pat.findall(t))
co, cn = nums(ob), nums(nb)
print("OLD-only:")
for k,v in sorted((co-cn).items()): print(f"  {k!r} x{v}")
print("NEW-only:")
for k,v in sorted((cn-co).items()): print(f"  {k!r} x{v}")
