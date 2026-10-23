import re, pathlib, collections
old = pathlib.Path("out/paper_check/orig_report.md").read_text(encoding="utf-8")
new = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
def body(t):
    return t[t.index("## 1 引言"):]
ob, nb = body(old), body(new)
ob_cut = ob[:ob.index("## 附录 D")]

num_re = re.compile(r"[−-]?\d[\d,]*(?:\.\d+)?")
def nums(t):
    # ignore LaTeX tag numbers \tag{1}; keep everything else
    t = re.sub(r"\\tag\{\d+\}", " ", t)
    return collections.Counter(num_re.findall(t))
co, cn = nums(ob_cut), nums(nb)
print("=== numbers only in OLD (excluding appendix D) ===")
for k, v in sorted((co - cn).items()):
    print(repr(k), v)
print("=== numbers only in NEW ===")
for k, v in sorted((cn - co).items()):
    print(repr(k), v)
print("counts", sum(co.values()), sum(cn.values()))
