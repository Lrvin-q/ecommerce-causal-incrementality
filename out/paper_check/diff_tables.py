import re, pathlib
def tables(path):
    t = pathlib.Path(path).read_text(encoding="utf-8")
    lines = t.splitlines()
    out = {}
    i = 0
    while i < len(lines):
        m = re.match(r"\*\*表 ([0-9A-Z]+)　", lines[i])
        if m:
            key = m.group(1)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            rows = []
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(lines[j].strip())
                j += 1
            out[key] = rows
            i = j
        else:
            i += 1
    return out
old = tables("out/paper_check/orig_report.md")
new = tables("reports/00_项目总报告.md")
def norm(rows):
    res = []
    for r in rows:
        r = r.replace("**", "").replace("“", '"').replace("”", '"')
        cells = [c.strip() for c in r.strip("|").split("|")]
        res.append(cells)
    return res
for k in sorted(set(old) & set(new)):
    a, b = norm(old[k]), norm(new[k])
    if a == b:
        print(f"表 {k}: OK ({len(a)} rows, {len(a[0]) if a else 0} cols)")
    else:
        print(f"表 {k}: DIFF")
        for idx, (ra, rb) in enumerate(zip(a, b)):
            if ra != rb:
                print("  row", idx, "old=", ra)
                print("         new=", rb)
        if len(a) != len(b):
            print("  row count", len(a), len(b))
print("old only:", sorted(set(old)-set(new)))
print("new only:", sorted(set(new)-set(old)))
