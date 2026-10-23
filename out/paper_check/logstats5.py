import re, pathlib
m = pathlib.Path("paper/main.log").read_text(encoding="utf-8", errors="replace")
print("Missing:", len(re.findall(r"Missing character", m)), "Bang:", len(re.findall(r"(?m)^!", m)), "Overfull hbox:", len(re.findall(r"Overfull \\hbox", m)))
print("Pages:", re.search(r"Output written on .*?\((\d+) pages?", m).group(1))
print("KB:", pathlib.Path("paper/main.pdf").stat().st_size // 1024)
