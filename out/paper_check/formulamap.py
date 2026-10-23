import pathlib, re
t = pathlib.Path("out/paper_check/final.txt").read_text(encoding="utf-8")
pages = t.split("\f")
for i,p in enumerate(pages[:15],1):
    lines=[l.strip() for l in p.splitlines() if l.strip()]
    hits=[l for l in lines if "式(" in l or "式 (" in l]
    print(f"p{i}: {lines[1][:40] if len(lines)>1 else ''} | {lines[2][:40] if len(lines)>2 else ''}")
    for h in hits[:2]: print("    ", h[:100])
