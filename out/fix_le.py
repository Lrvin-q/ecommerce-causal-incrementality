from pathlib import Path

p = Path(r"D:\L\practice_project\营销数分项目\reports\00_项目总报告.md")
text = p.read_text(encoding="utf-8")

text = text.replace("区间上界  $\\le$ 0.04", "区间上界 $\\le$0.04")
for cell in ["0.00 ($\\\\le$0.04)", "0.00 ( $\\le$ 0.04)"]:
    text = text.replace(cell, "0.00 ($\\le$0.04)")
text = text.replace("0.00 ($\\\\le$0.04)", "0.00 ($\\le$0.04)")
p.write_text(text, encoding="utf-8")

for i, l in enumerate(text.split("\n")):
    if "\\le" in l:
        print(i + 1, l[:110])
