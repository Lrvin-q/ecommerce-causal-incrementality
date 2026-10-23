import pathlib
t = pathlib.Path("out/paper_check/final4.txt").read_text(encoding="utf-8")
pages = t.split("\f")
print("pages", len(pages)-1)
for i,p in enumerate(pages[:15],1):
    lines=[l.strip() for l in p.splitlines() if l.strip()]
    print(i, len(lines), lines[0][:60] if lines else "")
