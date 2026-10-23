import re, pathlib
m = pathlib.Path("paper/main.log").read_text(encoding="utf-8", errors="replace")
print("Missing character:", len(re.findall(r"Missing character", m)))
print("Bang lines:", len(re.findall(r"(?m)^!", m)))
print("Overfull hbox:", len(re.findall(r"Overfull \\hbox", m)))
print("Overfull vbox:", len(re.findall(r"Overfull \\vbox", m)))
pm = re.search(r"Output written on .*?\((\d+) pages?", m)
print("Pages:", pm.group(1) if pm else "?")
print("PDF KB:", pathlib.Path("paper/main.pdf").stat().st_size // 1024)
