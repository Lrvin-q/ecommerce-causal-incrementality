import pathlib
t = pathlib.Path("out/paper_check/new.txt").read_text(encoding="utf-8")
pages = t.split("\f")
print("pages", len(pages))
for i, p in enumerate(pages, 1):
    lines = [l.strip() for l in p.splitlines() if l.strip()]
    head = " | ".join(lines[:4]) if lines else "(empty)"
    tail = " | ".join(lines[-2:]) if lines else ""
    print(f"p{i}: {head[:150]}")
    print(f"     tail: {tail[:120]}")
print("last page nonempty:", bool(pages[-1].strip()))
