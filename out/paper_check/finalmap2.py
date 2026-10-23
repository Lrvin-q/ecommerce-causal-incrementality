import pathlib
t = pathlib.Path("out/paper_check/final2.txt").read_text(encoding="utf-8")
pages = t.split("\f")
for i,p in enumerate(pages,1):
    lines=[l.strip() for l in p.splitlines() if l.strip()]
    print(i, len(lines), lines[0][:70] if lines else "")
print("last page:")
print(pages[14][-500:])
