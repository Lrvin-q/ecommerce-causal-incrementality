from pathlib import Path

p = Path(r"D:\L\practice_project\营销数分项目\reports\00_项目总报告.md")
text = p.read_text(encoding="utf-8")

out_lines = []
fixed_lines = 0
skipped = 0
for line in text.split("\n"):
    # 统计反引号代码段之外的 " 数量
    in_code = False
    positions = []
    for idx, ch in enumerate(line):
        if ch == "`":
            in_code = not in_code
        elif ch == '"' and not in_code:
            positions.append(idx)
    if not positions:
        out_lines.append(line)
        continue
    if len(positions) % 2 != 0:
        skipped += 1
        out_lines.append(line)
        continue
    chars = list(line)
    for k, pos in enumerate(positions):
        chars[pos] = "“" if k % 2 == 0 else "”"
    out_lines.append("".join(chars))
    fixed_lines += 1

p.write_text("\n".join(out_lines), encoding="utf-8")
print(f"fixed lines: {fixed_lines}, skipped(odd quotes): {skipped}")
