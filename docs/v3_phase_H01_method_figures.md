# H01 三方法图：原生 PPTX + SVG/PNG + 元素清单

维护时间：2026-10-31 19:55（北京时间）
状态：**C1/C2 已修并重生成，待独立复审**（首轮评审 2026-10-30 18:32 判 PASS WITH CONDITIONS，
C1 事实更正与 C2 结构不一致均已关闭；结构自检 + 主负责逐张目检通过，尚非独立验收）

---

## 1. 交付什么

| 文件 | 内容 | 规模 |
|---|---|---|
| `outputs/figures/h01/v3_h01_three_methods.pptx` | 3 页原生形状（非截图），可编辑 | 98 337 B |
| `outputs/figures/h01/slide1_itt.png` | 方法一：随机实验口径（全臂 ITT） | 2000×1125，166 495 B |
| `outputs/figures/h01/slide2_observational.png` | 方法二：观测因果与学习 | 2000×1125，179 233 B |
| `outputs/figures/h01/slide3_policy.png` | 方法三：预算策略 | 2000×1125，183 618 B |
| `outputs/figures/h01/slide{1,2,3}_*.svg` | 与 PPTX 同一几何定义的矢量版 | 3 份 |
| `outputs/figures/h01/v3_h01_elements.csv` | 元素清单（页/形状/文本/坐标） | 50 行，UTF-8-sig |
| `scripts/64_h01_method_figures.py` | 生成器（单一事实源：`SPEC`） | ~330 行 |

产物指纹（2026-10-31 19:53，`sha256sum outputs/figures/h01/*`；C1/C2 修复后 8 个文件全部重生成）：

| 文件 | sha256 |
|---|---|
| `v3_h01_three_methods.pptx` | `b204f3927192239f57facec885052bd98c032800fe2d17e6efb0d8f666841202` |
| `slide1_itt.png` | `daf5fd2bbd0c524feb3a85747bc60860dae8c14b3f2767553851b30898853632` |
| `slide2_observational.png` | `9c8b4a9cdf66af6ca292c3361fc2c93cbcacf7ea2bdb637ca01757269473bcd1` |
| `slide3_policy.png` | `6a42ae992a462bca2405208ff6a356f459a5c5fe29c6514388f6244e5e6a020b` |
| `slide1_itt.svg` | `816005a6490aa8ed9b54a1872263f9cc94c35d725d93e0ee9e182599634c6c02` |
| `slide2_observational.svg` | `db6cbff9c65b86146fafcc32906da66f66e84661762ebc2fa4498e6ff987a92e` |
| `slide3_policy.svg` | `e442e56d36c17b2132a400475ec016784dd0fb793a78514749d4144cb33ad168` |
| `v3_h01_elements.csv` | `ad035d3698ae0ddb36ad0a2fd0fc45713365c7a36372792e08bcba330e8a1c77` |

三图与论文第 2–3 章口径一一对应：

1. **方法一 ITT**：随机分流 → 处理/对照两臂 → 结果观测 → 主指标 `E[Π(1)−Π(0)]` → 校准与护栏（对应 D01/D02、F02、G01、G02）。
2. **方法二 观测因果与学习**：历史观测数据 → 六字段白名单（禁泄漏特征）→ 五类估计器 → 验证集选模（测试集不参与学习）→ `τ̂(X)` → 交叉拟合 OPE → 冻结帧审计（对应 D03、F01）。
3. **方法三 预算策略**：`τ̂(X)` + 成本模型 → 预算档 0.04–1.00 元/人 → 求解器五选一 → 名单（每人至多 1 张券）→ 支出与利润三口径 → 不确定度 1000/200 与真值审计（对应 E01/E02、F01、G02）。

页脚统一标注「合成数据 / 已知 DGP · 演示文稿原生形状（WPS 演示 COM 生成，可编辑，非截图）· 口径与论文第 2–3 章一致」。

## 1.5 独立评审结论（2026-10-30 18:32，报告 `docs/reviews/v3_phase_H01_review.md`）

**PASS WITH CONDITIONS**（6 条条件，C1/C2 必须修；无 FAIL）。评审独立复算：3 页 slide、形状 16/17/17
（sp 10/11/11 + cxnSp 6/6/6）、`a:blip`=0 且 `ppt/media/` 空、PNG 均 2000×1125（IHDR 直读）、
CSV 50 数据行/51 物理行、32 个文本元素**整串**一致（不是 12 字符前缀）、SVG rect/line 与 CSV 零误差、
8 个 sha256 与本文指纹表 8/8 相同。

**C1（事实更正，必须修）**：`PowerPoint.Application` 的 CLSID `{91493441-…}` 的 `LocalServer32`
指向 **wpp.exe（WPS 演示）**，PPTX 包内 `app.xml` 亦写 `WPS 演示`。因此：
- 本文 §2 与 18:18/18:23 记录里“本机有 PowerPoint COM”“PowerPoint 原生元素”的说法**不成立**，
  应改为“WPS 演示 COM（ProgID 借用了 `PowerPoint.Application`）”。
- 页脚“形状为 PowerPoint 原生元素”需改为“演示文稿原生形状（WPS 演示 COM 生成）”或等价表述。
- 换到真 PowerPoint 重建时**坐标可能变化**，不能假定与本次像素级一致。

**C2（结构不一致，必须修）**：12 个文本框在 PPTX 内被 `spAutoFit` 改写过（y +3.0～+5.4 pt、
h −1.0～−11.1 pt），而 CSV/SVG 仍是建页前规格；且 PPTX 段落 `algn="ctr"` 与 SVG 左对齐不一致
（标题视觉差约 260 pt）。即**三件套不是同一几何**，须以 PPTX 实测值为准回写 CSV/SVG，或关闭 autofit。

**C3–C5（口径建议）**：三口径命名与正文表 3-14（期望/缓冲/面值）冲突；方法一画两臂而正文 F02 是三臂；
OPE 缺“名单×预算档”输入；“每 rep 20 万”与 F01 的 6 万审计帧混写。C6 为文档建议。

**处置状态（2026-10-31 19:55 更新）**：C1、C2 已修并重生成三件套，等待独立复审；C3–C6 属口径/文档建议，
其中 C3（三口径命名）与 C4（两臂 vs 三臂）需在论文正文或图上文案另议，本轮未动图。

### 1.6 C1 / C2 的修复证据（2026-10-31 19:53–19:55）

**C1（事实更正）— CLOSED**

- 生成器 docstring 与 §2 统一改为「WPS 演示 COM：ProgID 借用 `PowerPoint.Application`，
  CLSID `{91493441-…}` 的 LocalServer32 指向 `wpp.exe`」；不再声称“本机有 PowerPoint”。
- 三页页脚改为「演示文稿原生形状（WPS 演示 COM 生成，可编辑，非截图）」；PPTX 内逐页拼接
  `<a:t>` 后整串命中该文案（`文本框 10/11/11`）。
- 换真 PowerPoint 重建时坐标可能变化，本轮不承诺像素级一致（已在 §4 边界重申）。

**C2（结构不一致）— CLOSED**

- 对齐：PS1 端每个文本框 `ParagraphFormat.Alignment = 1`（左对齐）；`verify()` 断言 slide XML
  中不存在 `<a:pPr … algn="ctr">`（此前误伤 `<a:ln algn="ctr">` 的宽松匹配已收窄）。
- 几何：WPS 保存时会把文本框收缩为单行高（29 pt），故改为**写完文字后强制回写 SPEC 的
  Left/Top/Width/Height**，并在保存后把 `<a:spAutoFit/>` 归一化为 `<a:noAutofit/>`
  （`normalize_pptx()`，重打包时其余 zip 条目原样保留）；`verify()` 逐 `<p:sp>` 断言
  `<a:off>/<a:ext>` 与 SPEC 偏差 ≤ 0.6 pt。
- 效果：三件套（PPTX / SVG / CSV）重新全部由同一 `SPEC` 生成，PPTX 实测几何与 CSV/SVG 一致；
  12 个文本框不再有 y +3.0～+5.4 pt / h −1.0～−11.1 pt 的漂移。页脚实测
  `off=(508000, 6350000)` EMU=`(40, 500)` pt、`ext=(11176000, 330200)` EMU=`(880, 26)` pt，与 SPEC 相同。
- 目检：主负责 2026-10-31 19:54 重看 3 张 PNG——标题左对齐、页脚单行无溢出、中文无乱码。

## 2. 工具链路线（不装包）

正式跑期间不得装包（AGENTS §11 的配套约束），本机也**没有 LibreOffice**。18:18 实测
`PowerPoint.Application` ProgID 能创建 COM 实例；18:32 评审查明该 CLSID `{91493441-…}` 的
`LocalServer32` 指向 **wpp.exe（WPS 演示）**，PPTX 包内 `app.xml` 亦写「WPS 演示」。因此实际
工具链是 **WPS 演示 COM**（ProgID 借名），不是 Microsoft PowerPoint。于是走：

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
| 文本落地 | 每页 slide XML 按 `<a:t>` 拼接为整串后，SPEC 中每个文本节点**整串**匹配（WPS 会把一行拆成多个 run，故先拼接；不再用 12 字符前缀） |
| 文本框几何 | 逐 `<p:sp>` 的 `<a:off>/<a:ext>` 与 SPEC 偏差 ≤ 0.6 pt；页脚实测 40/500/880/26 pt |
| 段首对齐 | slide XML 无 `<a:pPr … algn="ctr">`（窄匹配，不误伤 `<a:ln algn="ctr">`） |
| 自动缩放 | XML 无 `spAutoFit`（WPS 保存后由 `normalize_pptx()` 统一改为 `noAutofit`） |
| PNG 规格 | 3 张，均 2000×1125 |
| 无位图依赖 | PPTX 媒体目录为空（`assert not media`）——证明是原生形状而非截图 |
| 元素清单 | 50 行，页/形状/文本/坐标齐全 |

运行输出（2026-10-31 19:53，C1/C2 修复后重跑，`RC=0`）：

```
slides=3 shapes=16,17,17
pptx=True
verify: 3 slides, 3 PNG at 2000x1125, text present in slide XML
written: outputs\figures\h01 (3 slides, 3 PNG, 3 SVG, 50 inventory rows)
```

视觉：主负责 2026-10-31 19:54 重看 3 张 PNG——标题/副标题/页脚左对齐，页脚单行无溢出，
中文无乱码，箭头指向正确。第 1 页下半部留白偏多，属可接受（未遮挡信息）。

> 首轮评审（18:32）核对的 8 个 sha256 是修复前版本，已被上表取代；旧值留在 Git 历史中。

## 4. 边界与遗留

- 本文件只证明「产物存在、结构自检通过、主负责目检通过」，**不等于独立验收**；H01 的验收仍须
  独立评审（结构 + 视觉）。
- 三图为**方法示意**，不含 G03 正式数值；G03 阶段 B 并入后若需在图上加数字，须重新生成而非手改。
- PPTX 原生可编辑：改文案后可重跑 `python scripts/64_h01_method_figures.py` 一键重建三件套；
  手工改 PPTX 后 SVG/CSV 将与之失配，请在文档里注明版本。
- 生成依赖本机 WPS 演示（COM，ProgID 借用 `PowerPoint.Application`）；换机器须先确认该 ProgID 的
  `LocalServer32` 指向，真 PowerPoint 下坐标可能不同，必须重跑 `verify()` 并重新目检 PNG。
- 本文件的 sha256 表对应当前版本；任何重跑都会改变 PNG/PPTX/SVG/CSV 至少之一，更新后须同步本表。
