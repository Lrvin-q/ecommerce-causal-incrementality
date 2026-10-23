from pathlib import Path

p = Path(r"D:\L\practice_project\营销数分项目\reports\00_项目总报告.md")
lines = p.read_text(encoding="utf-8").split("\n")

anchor = next(i for i, l in enumerate(lines) if l.startswith("| T | 1.625 |"))
# anchor-1 是表 5 的分隔行；在它之前插入被误删的整段
restore = """人均 GMV 由 12.38 元升至 18.62 元（**+50%**），人均净利润却只由 3.00 元升至 3.73 元（**+24%**）。每 100 人可分解为（图 4b）：多转化 5.01 人 × 24.69 元 = **+123.7 元**，原购买者 54.8% 用券形成 **−55.3 元**券成本，订单经济差异 **+4.1 元**，合计 **+72.4 元**，与 ITT 一致——**这就是以利润而非 GMV 为主指标的理由**：按 GMV 决策会把价值高估一倍以上。核销率须并列两个口径：占已发券 **8.28%**（预算效率）与占已下单 **54.8%**（侵蚀程度），只报后者会误导。

![ITT 对真值的覆盖与利润侵蚀分解](../outputs/figures/paper/fig3_itt.png){width=\\linewidth}

## 6 异质性处理效应与四指标的不可替代性

在 L1（可忽略性成立，差异纯粹来自方法）上按用户切分 10 万/4 万/6 万（表 5 与图 5）。**策略价值的首个口径声明**：下文一切“策略价值”都是**增量口径** $V(\\pi)=\\mathbb{E}[\\pi(X)\\tau_\\Pi(X)]$，即

$$V_{\\text{inc}}(\\pi)=\\frac{1}{n}\\sum_i\\pi_i\\left(\\Pi_i(1)-\\Pi_i(0)\\right),\\qquad V_{\\text{inc}}(\\pi)=0\\ \\text{当}\\ \\pi\\equiv 0; \\tag{6}$$

它与“绝对口径”$V_{\\text{abs}}(\\pi)=n^{-1}\\sum_i[\\pi_i\\Pi_i(1)+(1-\\pi_i)\\Pi_i(0)]$ 只差一个与策略无关的常数 $\\mathbb{E}[\\Pi(0)]=3.12$ 元/人。这个常数会**稀释差距**：绝对口径下 T-learner 与 Causal Forest 只差 2.0%，增量口径下差 **12.7%**——把常数剥离才看得清模型的价值。

**表 5　三种异质性效应学习器的测试集表现（L1，测试集 6 万人；T = T-learner、S = S-learner、CF = Causal Forest；RMSE / 增量价值 / regret / 偏差单位均为元/人，选中比例 = 非负策略选中用户占比；\\*CF 只跑 2 次，T/S 各 20 次）**

| 学习器 | RMSE | $R^2$ | Spearman | Top-20% | 增量价值 | regret | 偏差 | 选中比例 |""".split("\n")

lines[anchor - 1:anchor - 1] = restore
p.write_text("\n".join(lines), encoding="utf-8")
print("inserted; total lines:", len(lines))
