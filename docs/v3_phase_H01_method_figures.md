# H01 三方法图：原生 PPTX + SVG/PNG + 元素清单

维护时间：2026-10-30 18:23（北京时间）
状态：**已交付，待独立评审**（结构自检通过，视觉为主负责目检，尚非独立验收）

---

## 1. 交付什么

| 文件 | 内容 | 规模 |
|---|---|---|
| `outputs/figures/h01/v3_h01_three_methods.pptx` | 3 页原生形状（非截图），可编辑 | 102 345 B |
| `outputs/figures/h01/slide1_itt.png` | 方法一：随机实验口径（全臂 ITT） | 2000×1125，164 576 B |
| `outputs/figures/h01/slide2_observational.png` | 方法二：观测因果与学习 | 2000×1125，178 801 B |
| `outputs/figures/h01/slide3_policy.png` | 方法三：预算策略 | 2000×1125，182 982 B |
| `outputs/figures/h01/slide{1,2,3}_*.svg` | 与 PPTX 同一几何定义的矢量版 | 3 份 |
| `outputs/figures/h01/v3_h01_elements.csv` | 元素清单（页/形状/文本/坐标） | 50 行，UTF-8-sig |
| `scripts/64_h01_method_figures.py` | 生成器（单一事实源：`SPEC`） | ~315 行 |

三图与论文第 2–3 章口径一一对应：

1. **方法一 ITT**：随机分流 → 处理/对照两臂 → 结果观测 → 主指标 `E[Π(1)−Π(0)]` → 校准与护栏（对应 D01/D02、F02、G01、G02）。
2. **方法二 观测因果与学习**：历史观测数据 → 六字段白名单（禁泄漏特征）→ 五类估计器 → 验证集选模（测试集不参与学习）→ `τ̂(X)` → 交叉拟合 OPE → 冻结帧审计（对应 D03、F01）。
3. **方法三 预算策略**：`τ̂(X)` + 成本模型 → 预算档 0.04–1.00 元/人 → 求解器五选一 → 名单（每人至多 1 张券）→ 支出与利润三口径 → 不确定度 1000/200 与真值审计（对应 E01/E02、F01、G02）。

页脚统一标注「合成数据 / 已知 DGP · 形状为 PowerPoint 原生元素（可编辑，非截图）· 口径与论文第 2–3 章一致」。

## 2. 工具链路线（不装包）

正式跑期间不得装包（AGENTS §11 的配套约束），本机也**没有 LibreOffice**。18:18 实测本机
**有 PowerPoint COM**，于是走：

```
SPEC（Python dict，单一事实源）
  ├─→ 写 C:\cg_h01_tmp\h01_spec.json（UTF-8）
  ├─→ 写 C:\cg_h01_tmp\h01_build.ps1（纯 ASCII）
  │     PowerShell 用 Get-Content -Raw -Encoding UTF8 读 JSON，
  │     AddShape/AddTextbox/AddConnector 建页，Export PNG 2000×1125，SaveAs 24 → PPTX
  ├─→ Python 按同一几何写 3 份 SVG（marker 箭头）
  └─→ Python 写元素清单 CSV
```

**为什么 PS1 必须纯 ASCII**：Windows PowerShell 5.1 按 ANSI 读 `.ps1`，含中文的脚本会把路径读成乱码
（本轮踩过：中文目录变成 `钀ラ攢鏁板垎椤圭洰`，探针 PNG 里文字全乱）。所以中文文本只走 UTF-8 JSON，
脚本本体与临时目录都用 ASCII（`C:\cg_h01_tmp`）。

**颜色记法坑**：COM 的 `Fill.ForeColor.RGB` 是 **BGR 整数**，不是 RGB；写错会整体换色。

## 3. 自检证据（全部由 `scripts/64_h01_method_figures.py` 的 `verify()` 落盘断言）

| 检查 | 结果 |
|---|---|
| PPTX 页数 | 3 页 slide XML |
| 每页形状数 | 16 / 17 / 17 |
| 文本落地 | 每页 slide XML 中按文本节点归一化后匹配 ≥12 字符前缀（PowerPoint 会把一行拆成多个 `<a:t>` run，需先拼接再比对） |
| PNG 规格 | 3 张，均 2000×1125 |
| 无位图依赖 | PPTX 媒体目录为空（`assert not media`）——证明是原生形状而非截图 |
| 元素清单 | 50 行，页/形状/文本/坐标齐全 |

运行输出（18:21）：

```
slides=3 shapes=16,17,17
pptx=True
verify: 3 slides, 3 PNG at 2000x1125, text present in slide XML
written: outputs\figures\h01 (3 slides, 3 PNG, 3 SVG, 50 inventory rows)
```

视觉：主负责 18:22–18:23 逐张 150 dpi 目检 1–3 页——中文无乱码、无文字溢出盒子、箭头指向正确、
页脚来源注在位；第 1 页下半部留白偏多，属可接受（未遮挡信息）。

## 4. 边界与遗留

- 本文件只证明「产物存在、结构自检通过、主负责目检通过」，**不等于独立验收**；H01 的验收仍须
  独立评审（结构 + 视觉）。
- 三图为**方法示意**，不含 G03 正式数值；G03 阶段 B 并入后若需在图上加数字，须重新生成而非手改。
- PPTX 原生可编辑：改文案后可重跑 `python scripts/64_h01_method_figures.py` 一键重建三件套；
  手工改 PPTX 后 SVG/CSV 将与之失配，请在文档里注明版本。
- 生成依赖本机 PowerPoint（COM）；换机器需重新确认 COM 可用性，否则只能出 SVG/PNG 两件套。
