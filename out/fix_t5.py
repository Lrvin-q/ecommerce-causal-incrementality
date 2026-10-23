from pathlib import Path

p = Path(r"D:\L\practice_project\营销数分项目\reports\00_项目总报告.md")
lines = p.read_text(encoding="utf-8").split("\n")

for i, l in enumerate(lines):
    if l.startswith("| 学习器 | RMSE |"):
        lines[i + 1] = "|------------|----------|--------------|------------------|---------------------|------------|--------------|--------------|--------------|"
    if l.startswith("| T-learner | 1.625 |"):
        lines[i] = "| T | 1.625 | **−4.90** | 0.335 | 0.374 | 0.571 | 0.109 | +0.137 | 76.2% |"
    if l.startswith("| S-learner | 0.595 |"):
        lines[i] = "| S | 0.595 | 0.208 | 0.637 | 0.597 | 0.629 | 0.051 | +0.104 | 89.5% |"
    if l.startswith("| CF\\* | **0.557**"):
        lines[i] = "| CF\\* | **0.557** | **0.307** | **0.647** | **0.633** | **0.644** | **0.036** | +0.134 | 89.6% |"

# 表 5 标题里说明缩写
for i, l in enumerate(lines):
    if l.startswith("**表 5　三种异质性效应学习器"):
        lines[i] = (
            "**表 5　三种异质性效应学习器的测试集表现（L1，测试集 6 万人；T = T-learner、"
            "S = S-learner、CF = Causal Forest；RMSE / 增量价值 / regret / 偏差单位均为元/人，"
            "选中比例 = 非负策略选中用户占比；\\*CF 只跑 2 次，T/S 各 20 次）**"
        )

p.write_text("\n".join(lines), encoding="utf-8")
print("ok")
