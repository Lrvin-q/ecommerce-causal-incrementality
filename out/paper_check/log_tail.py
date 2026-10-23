import pathlib
m = pathlib.Path("paper/main.log").read_text(encoding="utf-8", errors="replace")
print(m[-7000:])
