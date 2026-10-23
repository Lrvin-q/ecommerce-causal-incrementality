import pathlib, re
m = pathlib.Path("paper/main.log").read_text(encoding="utf-8", errors="replace")
print("pages", re.search(r"Output written on .*?\((\d+) pages?", m).group(1))
t = pathlib.Path("out/paper_check/new5.txt").read_text(encoding="utf-8")
pages = t.split("\f")
for i,p in enumerate(pages,1):
    lines=[l.strip() for l in p.splitlines() if l.strip()]
    print(i, len(lines), lines[0][:60] if lines else "")
