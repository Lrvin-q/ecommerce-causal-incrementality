import pathlib
t = pathlib.Path("out/paper_check/new3.txt").read_text(encoding="utf-8")
pages = t.split("\f")
for i, p in enumerate(pages, 1):
    lines = [l.strip() for l in p.splitlines() if l.strip()]
    print(f"p{i}: lines={len(lines)} head={' | '.join(lines[:2])[:100]}")
