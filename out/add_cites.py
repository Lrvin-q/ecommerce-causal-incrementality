from pathlib import Path

p = Path(r"D:\L\practice_project\营销数分项目\reports\00_项目总报告.md")
t = p.read_text(encoding="utf-8")

subs = [
    # [11] 外部验证
    ("模拟器把真值变成可计算量[12]。全部业务参数见附录 A",
     "模拟器把真值变成可计算量[12]；外部效度只能靠公开营销实验数据（如 Hillstrom 的 MineThatData 数据集[11]）另行检验，本文不做。全部业务参数见附录 A"),
    # [2] ITT 口径
    ("**（1）双指标样本量与随机化。** 1:1 随机分流，两窗口等长（转化 7 天、利润 30 天）。",
     "**（1）双指标样本量与随机化。** 估计目标是意向处理效应（ITT）：按随机分组建样本，未领券、未核销者仍留在实验组，不报告“领券用户的效果”，否则会把随机实验偷换为观察性比较[2]。1:1 随机分流，两窗口等长（转化 7 天、利润 30 天）。"),
    # [8] policy learning
    ("**（5）预算约束优化。** 目标是（式 7）",
     "**（5）预算约束优化。** 这属于带资源约束的策略学习（policy learning）问题[8]，目标是（式 7）"),
    # [4][5] 双稳健前提
    ("**平衡性诊断全绿与无偏无关。**",
     "**平衡性诊断全绿与无偏无关。** 这一发现与“双稳健需要至少一个模型正确”的前提直接相关[5]。"),
]

for old, new in subs:
    if old not in t:
        raise SystemExit(f"NOT FOUND: {old[:40]}")
    t = t.replace(old, new, 1)

p.write_text(t, encoding="utf-8")

body = t[t.index("## 1 引言"): t.index("## 参考文献")]
import re
cites = re.findall(r"\[(\d{1,2})\]", body)
print("citation count:", len(cites))
print("unique:", sorted({int(c) for c in cites}))
