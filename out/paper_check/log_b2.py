import pathlib, re
m = pathlib.Path("paper/main.log").read_text(encoding="utf-8", errors="replace")
idx = m.find("B.2")
print("idx", idx)
print(m[idx-3000:idx+3000] if idx>0 else "not found")
