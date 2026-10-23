import pathlib, re
p = pathlib.Path("reports/00_项目总报告.md")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
out = []
bad = []
for i, line in enumerate(lines, 1):
    n = line.count('"')
    if n % 2:
        bad.append((i, n, line[:120]))
        out.append(line); continue
    state = 0
    chars = []
    for ch in line:
        if ch == '"':
            chars.append("“" if state == 0 else "”")
            state ^= 1
        else:
            chars.append(ch)
    out.append("".join(chars))
if bad:
    print("ODD LINES:", bad)
    raise SystemExit(1)
text = "".join(out)
p.write_text(text, encoding="utf-8", newline="")
print("converted; open", text.count("“"), "close", text.count("”"), "ascii", text.count('"'))
for i, line in enumerate(text.splitlines(), 1):
    for m in re.finditer(r"“([^”]{1,40})”", line):
        print(i, repr(m.group(0)))
