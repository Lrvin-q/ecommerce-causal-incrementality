import pathlib
t = pathlib.Path("out/paper_check/new5.txt").read_text(encoding="utf-8")
pages = t.split("\f")
print(pages[15])
