import re, pathlib
md = pathlib.Path("reports/00_项目总报告.md").read_text(encoding="utf-8")
body = md[md.index("## 1 引言"):]
tex = pathlib.Path("paper/main.tex").read_text(encoding="utf-8")
# strip image include lines for path check, but report them separately
body_no_img = "\n".join(l for l in body.splitlines() if not l.startswith("!["))
checks = {
    "D:\\": r"D:\\",
    "C:\\": r"C:\\",
    "reports/": r"reports/",
    "outputs/": r"outputs/",
    "scripts/": r"scripts/",
    ".py": r"\.py\b",
    ".csv": r"\.csv\b",
    ".md": r"\.md\b",
    "run_all": r"run_all",
    "pytest": r"pytest",
    "v1": r"(?<![A-Za-z0-9])v1(?![A-Za-z0-9])",
    "v2": r"(?<![A-Za-z0-9])v2(?![A-Za-z0-9])",
    "commit": r"(?<![A-Za-z])commit(?![A-Za-z])",
    "git": r"(?<![A-Za-z])git(?![A-Za-z])",
}
for name, pat in checks.items():
    hits = [(i, l.strip()[:120]) for i, l in enumerate(body.splitlines(), 1) if re.search(pat, l, re.I)]
    print(f"{name:10s} body_no_img={len(hits)}")
    for h in hits[:5]: print("   ", h)
print("image lines with outputs/:", sum(1 for l in body.splitlines() if l.startswith("![") and "outputs/" in l))
print("--- main.tex ---")
for name, pat in checks.items():
    hits = [l.strip()[:120] for l in tex.splitlines() if re.search(pat, l, re.I)]
    if hits: print(name, len(hits), hits[:3])
print("--- counts ---")
print("emdash body", body.count("——"), "md", md.count("——"))
print("bold pairs body", len(re.findall(r"\*\*[^*\r\n]+\*\*", body)))
print("qiyi", body.count("其一"), body.count("其二"), body.count("其三"))
print("benwen body", body.count("本文"))
