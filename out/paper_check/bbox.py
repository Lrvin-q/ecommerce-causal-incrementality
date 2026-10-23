import re, pathlib
h = pathlib.Path("out/paper_check/bbox.html").read_text(encoding="utf-8")
pages = h.split("<page")
for pi, p in enumerate(pages[1:], 15):
    words = re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', p)
    if not words: continue
    print("page", pi, "nwords", len(words), "yMin", min(float(w[1]) for w in words), "yMax", max(float(w[3]) for w in words))
    for w in words[:5]: print("  ", w)
    print("  last:", words[-5:])
