import pathlib, re
t = pathlib.Path("out/paper_check/final.txt").read_text(encoding="utf-8")
print("emdash ——:", t.count("——"))
print("ascii dquote:", t.count('"'))
print("open curly:", t.count("“"), "close:", t.count("”"))
# balance per line
bad = []
for i, line in enumerate(t.splitlines(), 1):
    if line.count("“") != line.count("”"):
        bad.append((i, line.strip()[:120]))
print("unbalanced lines:", len(bad))
for b in bad[:10]: print(b)
# quoted spans
spans = re.findall(r"“([^”]{0,30})”", t)
print("spans:", len(spans))
for s in spans:
    if any(c in s for c in "。；，、") and len(s) > 18:
        print("LONG/ODD:", s)
# data source occurrences
for i, line in enumerate(t.splitlines(), 1):
    if "数据来源" in line:
        print("数据来源", i, line.strip()[:100])
