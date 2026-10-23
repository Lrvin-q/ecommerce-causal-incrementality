import re, pathlib
m = pathlib.Path("paper/main.log").read_text(encoding="utf-8", errors="replace")
print("Missing character:", len(re.findall(r"Missing character", m)))
print("Bang lines:", len(re.findall(r"(?m)^!", m)))
print("Overfull hbox:", len(re.findall(r"Overfull \\hbox", m)))
print("Overfull vbox:", len(re.findall(r"Overfull \\vbox", m)))
print("Pages:", re.search(r"Output written on .*?\((\d+) pages?", m).group(1))
print("PDF KB:", pathlib.Path("paper/main.pdf").stat().st_size // 1024)
