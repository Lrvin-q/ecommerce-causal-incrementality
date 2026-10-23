import re, pathlib
h = pathlib.Path("out/paper_check/bbox.html").read_text(encoding="utf-8")
pages = h.split("<page")
p = pages[2]  # page 16
words = re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', p)
for w in words:
    if any(k in w[4] for k in ["本表","附录","C1","表B1","表 B1","数据来源汇总"]):
        print(w)
# print all words with y between 550 and 700
print("--- y 550-720 ---")
for w in words:
    y=float(w[1])
    if 550 <= y <= 720:
        print(w)
