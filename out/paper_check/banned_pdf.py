import re, pathlib
t = pathlib.Path("out/paper_check/final.txt").read_text(encoding="utf-8")
checks = {
    "D:\\": r"D:\\", "C:\\": r"C:\\", "reports/": r"reports/", "outputs/": r"outputs/",
    "scripts/": r"scripts/", ".py": r"\.py\b", ".csv": r"\.csv\b", ".md": r"\.md\b",
    "run_all": r"run_all", "pytest": r"pytest",
    "v1": r"(?<![A-Za-z0-9])v1(?![A-Za-z0-9])", "v2": r"(?<![A-Za-z0-9])v2(?![A-Za-z0-9])",
    "commit": r"(?<![A-Za-z])commit(?![A-Za-z])", "git": r"(?<![A-Za-z])git(?![A-Za-z])",
}
for name, pat in checks.items():
    hits = re.findall(pat, t, re.I)
    print(f"{name:10s} {len(hits)}")
print("emdash", t.count("——"))
print("figure-source pattern:", len(re.findall(r"图\s*\d+\s*[^\n]{0,20}数据来源", t)))
