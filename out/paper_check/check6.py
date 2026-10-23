import pathlib, re
m = pathlib.Path("paper/main.log").read_text(encoding="utf-8", errors="replace")
print("pages", re.search(r"Output written on .*?\((\d+) pages?", m).group(1))
print("overfull hbox", len(re.findall(r"Overfull \\hbox", m)))
print("missing", len(re.findall(r"Missing character", m)))
