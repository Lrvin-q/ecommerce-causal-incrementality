# AGENTS.md — 工程与协作规范

> 本文件约束**所有参与本项目的人与代理**（包括主负责与任何子代理）。
> 文件优先级：**`项目方案思路.md`（业务纲领） > `GOAL.md`（验收裁判） > `TODO.md`（进度真相） > 本文件（执行规范）**。
> 冲突时向上服从；本文件只规定"怎么做"，不定义"做什么"。

---

## 0. 十秒上手

```powershell
# 每次开工先做这两件事
$env:PYTHONUTF8 = '1'                       # 必须：Windows 默认 GBK，中文/图表会炸
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\Activate.ps1                # 项目虚拟环境（勿用全局 Python）

# 一条命令复现全部产物
python scripts\run_all.py --round 1         # 第一轮；--round all 全量
```

**禁止**：直接调用 `D:\L\Document\Code\Python\python.exe` 跑项目代码（那是建 venv 用的基础解释器，没有项目依赖）；省略 `PYTHONUTF8=1`（中文路径与图表字体会出乱码）。

---

## 1. 环境事实（已核实，勿再猜）

| 项 | 值 |
|---|---|
| 基础解释器 | `D:\L\Document\Code\Python\python.exe` — Python 3.13.7 |
| 项目虚拟环境 | `.venv\Scripts\python.exe`（**项目代码一律用这个**） |
| 依赖安装 | 用 `.venv` 内 pip；pip 已配清华源 `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple` |
| 可用性 | 全部依赖在 py3.13 有 cp313 官方轮子（numpy/pandas/scipy/sklearn/statsmodels/matplotlib/seaborn/pyarrow/econml 0.17.0/lightgbm 4.7.0） |
| 版本锁定 | 以 `requirements.txt` 为准；改依赖必须同步更新该文件 |
| 平台 | Windows；路径含中文，**所有路径用 `pathlib.Path` + 引号包裹** |

---

## 2. 目录职责

```
项目方案思路.md      # 业务纲领，只读，不改
GOAL.md / TODO.md / AGENTS.md
requirements.txt
configs/            # 所有可调参数（YAML），代码里不许出现业务 magic number
src/causal_growth/  # 库代码，纯函数优先，可被 scripts 与 tests 复用
  config.py rng.py io_utils.py viz.py
  dgp/              # L0–L4 数据生成 + 真值
  data/             # 五表 schema、脏数据层、质量校验、利润核算
  design/           # 样本量 / AA / 护栏非劣效 / 多重比较
  estimate/         # ITT / CATE / 观察性因果
  policy/           # 贪心 / 背包 / 六策略
  evaluation/       # 四指标 / 敏感性扫描
scripts/            # 薄入口，只做编排，不写业务逻辑
tests/              # pytest；口径类断言必须有
data/               # 生成数据（gitignore）
outputs/            # figures/ tables/ runs/（runs 下按 seed 分目录）
reports/            # 中文报告（Markdown）
```

---

## 3. 代码规范

1. **类型注解 + 文档字符串**：公开函数必须有 type hints 和说明"这个函数回答方案里哪个问题"。
2. **参数零硬编码**：业务参数（转化率、券面额、成本率、λ、预算、R）一律来自 `configs/*.yaml`；代码里只允许出现数学常数（0、1、2）。
3. **随机性可复现**：**禁止**裸 `np.random.*` / `random.*`。统一用 `rng.py` 的种子派生：
   ```python
   from causal_growth.rng import child_rng
   rng = child_rng(master_seed=20240101, stream="dgp.l1", index=rep)
   ```
   要求：同一 `(master_seed, stream, index)` 永远产出同一串随机数；新增随机流不得扰动已有流。
4. **I/O 显式编码**：读写文本一律 `encoding="utf-8"`；CSV 用 `utf-8-sig`（Excel 打开中文不乱码）。
5. **纯函数优先**：DGP、利润核算、指标计算应为"输入 → 输出"的纯函数，便于单测与重复实验。
6. **失败要响**：口径校验不通过时**抛异常**，不 print 警告后继续跑。

---

## 4. 口径红线（违反 = 结果作废）

对照 `GOAL.md` 第三部分。写代码时把这些做成**断言**：

```python
# R1 分析分母 = 随机分配的全部用户（不是成功支付/核销用户）
assert (df.groupby("group").size().sum() == df.user_id.nunique())
assert "refunded" in df.columns  # 退款单必须在样本里
# R2 两个窗口等长、不混用
assert set(df.window_type) == {"convert_7d", "profit_30d"}
# R3 券成本只扣一次
assert "coupon_cost" in profit_components      # 在 Π^net 里出现
# 且 V(π) 计算中不得再次出现 coupon_cost 项
```

**另外四条高频自伤，代码里禁止**：
- 样本量符号混用（把 `n_per_group` 当 `N_total`）→ 变量名严格区分，报告同名字段。
- 训练集上评策略 → 学习与评估数据必须来自不同 split。
- 拿个体观测利润差当 CATE 真值 → 真值只来自 DGP 解析式。
- 剔除退款订单 / 只保留核销用户。

---

## 5. 验证规范

- **每个模块配 pytest**；口径类、DGP 一致性类断言**必须**有测试。
- **单测覆盖不到的，用校验脚本落盘报告**（如蒙特卡洛 ATE 误差），产物进 `outputs/tables/`。
- **数值阈值**：蒙特卡洛 vs 闭式误差 < 0.001；覆盖率目标 [0.93, 0.97]；假阳性率 ≈ 0.05。
- **重复实验**：正式数值 R = 200–500；调试可先 R = 20 跑通流程，**但报告里必须用正式 R**，且报告注明 R 值。
- **不预设结论**：任何"某方法在某条件下会失效"的表述，必须是脚本跑出来的结果，不能写在代码注释里当既定事实。

---

## 6. 图表与报告

- 图统一由 `viz.py` 出，`matplotlib` + `seaborn`，中文字体显式设置（否则 Windows 下乱码），`dpi=150`，落 `outputs/figures/`。
- 每张图必须有：标题（说结论）、坐标轴标签（带单位）、图例、数据来源注（层级 + seed + R）。
- 报告里每个数字都要能追溯到某个 `outputs/tables/*.csv`；报告写"见 `outputs/tables/xxx.csv`"。
- 报告必须写**局限性**与**结论失效条件**，单独成节。
- 所有产物顶部标注：**合成数据 / 已知 DGP**。

---

## 7. 子代理协作规则

主负责（本项目主控）可以向子代理分派**自包含**子任务。分派时：

1. **必须给出**：任务边界、输入文件路径、输出文件路径、验收标准、禁止事项。
2. **子代理必须先读** `项目方案思路.md` 相关章节 + `AGENTS.md`，禁止凭常识发明口径。
3. **子代理不写 `GOAL.md` / `TODO.md`**；进度由主负责统一更新。
4. **子代理的结论一律视为草稿**：主负责必须复核关键数字与口径后才能进入交付物。
5. **并行安全**：多个子代理不得同时改同一文件；按目录/模块划分归属。
6. **建议分工**（按模块天然低耦合）：
   - DGP 与校验 / 数据模型与利润核算 / 实验设计与 ITT / CATE 与观察性 / 策略优化 / 出图与报告

---

## 8. Git 规范

- 每轮完成一个里程碑 commit；提交前跑 `pytest` + `run_all.py --round N`。
- 提交信息格式：`轮次|模块: 做了什么`，例：`R1|dgp: 实现 L0-L3 与实现正确性校验`。
- **不提交**：`.venv/`、`data/`、`outputs/runs/`、`*.parquet`（见 `.gitignore`）。
- **提交**：源码、configs、tests、scripts、报告、图表 PNG、`outputs/tables/` 的结果 CSV。

---

## 9. 汇报规范（向用户）

每轮结束须报告：**① 产出物清单（路径）② GOAL.md 验收项逐条对照（过/没过/为什么）③ 关键数字 ④ 遇到的问题与我的判断 ⑤ 下一步**。
**不静默降级**：做不到的验收项必须显式说明，不得悄悄降低标准或换个指标糊弄。

---

## 10. 文件维护时间（2026-10-25 09:55，北京时间新增）

- 今后维护文件、记录进度、决策、验收及交接时，时间必须具体到分钟，格式为 `YYYY-MM-DD HH:mm`，并明确使用北京时间（Asia/Shanghai）；不得仅写年月日。
- 机器运行凭据可保留带时区的ISO 8601时间，须包含时、分，允许保留秒或更高精度。
- 历史记录与已冻结验收凭据保留原始时间。不得猜测缺失时分，也不得为补写时间而改动不可变证据；新维护时间另行标注。
