# H01 三方法图：原生 PPTX + SVG/PNG + 元素清单

维护时间：2026-10-31 20:14（北京时间）
状态：**第三次独立复审 PASS WITH CONDITIONS（针对 20:09:34 工作树快照 S2）**；两条硬条件
（① 先提交 S2 再改判 ② 本文指纹时间改为实际落盘 20:09）中 ② 已修，① 随本次提交闭合。
第二轮复审（20:06）判 FAIL 的 P1-1（20 个盒内标签被误改左对齐）已修复并复检。

---

## 1. 交付什么

| 文件 | 内容 | 规模 |
|---|---|---|
| `outputs/figures/h01/v3_h01_three_methods.pptx` | 3 页原生形状（非截图），可编辑 | 98 380 B |
| `outputs/figures/h01/slide1_itt.png` | 方法一：随机实验口径（全臂 ITT） | 2000×1125，166 584 B |
| `outputs/figures/h01/slide2_observational.png` | 方法二：观测因果与学习 | 2000×1125，179 458 B |
| `outputs/figures/h01/slide3_policy.png` | 方法三：预算策略 | 2000×1125，183 514 B |
| `outputs/figures/h01/slide{1,2,3}_*.svg` | 与 PPTX 同一几何定义的矢量版 | 3 份 |
| `outputs/figures/h01/v3_h01_elements.csv` | 元素清单（页/形状/文本/坐标） | 50 数据行 / 51 物理行，UTF-8-sig |
| `scripts/64_h01_method_figures.py` | 生成器（单一事实源：`SPEC`） | ~400 行 |

产物指纹（2026-10-31 20:09，`sha256` 直读；P1-1 修复后 8 个文件于 20:09:32–34 全部重生成）：

| 文件 | sha256 |
|---|---|
| `v3_h01_three_methods.pptx` | `f11997b7305f1b805011e901c43cca1aa880807040b1f4e173940d364bf6cfd0` |
| `slide1_itt.png` | `b4592f49da6f38bf7c4792ce00ab578a1d9bb0242ad10ba90b61abe052afd7b7` |
| `slide2_observational.png` | `561fbfae6c8cbd7d141406915b2b3dc8f80a20c1156d0152efb0a7bded9ce1bf` |
| `slide3_policy.png` | `76d9682bbecf63efb207a9c52fff9a3356bc21abb94bd9f26d7cbbffc636c7cf` |
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

**处置状态（2026-10-31 20:09 更新）**：C1 两轮复审均 CLOSED；C2 原条件 CLOSED，但其对齐修法在
第二轮复审中触发新 P1-1（20 个盒内标签误左对齐），已按 §1.7 重做并重生成；C3–C6 属口径/文档建议，
其中 C3（三口径命名）与 C4（两臂 vs 三臂）需在论文正文或图上文案另议，本轮未动图。

### 1.6 C1 / C2 的修复证据（2026-10-31 19:53–20:09）

**C1（事实更正）— CLOSED**

- 生成器 docstring 与 §2 统一改为「WPS 演示 COM：ProgID 借用 `PowerPoint.Application`，
  CLSID `{91493441-…}` 的 LocalServer32 指向 `wpp.exe`」；不再声称“本机有 PowerPoint”。
- 三页页脚改为「演示文稿原生形状（WPS 演示 COM 生成，可编辑，非截图）」；PPTX 内逐页拼接
  `<a:t>` 后整串命中该文案（`文本框 10/11/11`）。
- 换真 PowerPoint 重建时坐标可能变化，本轮不承诺像素级一致（已在 §4 边界重申）。

**C2（结构不一致）— 原条件 CLOSED；对齐策略已被第二轮复审推翻并重做（见 §1.7）**

- 对齐（19:53 版，已作废）：PS1 曾对**每个**文本形状设 `ParagraphFormat.Alignment = 1`（左对齐），
  并全局禁 `<a:pPr … algn="ctr">`。第二轮复审查明这把 20 个盒内标签也改成了左对齐，而 SVG
  仍居中，属于同一类不一致的扩大（P1-1）。
- 现行对齐（20:09 版）：**仅 `textbox` 节点左对齐（`Alignment=1`），盒内标签显式居中
  （`Alignment=2`）**；`verify()` 按元素类型分别断言，不再全局禁 `ctr`。
- 几何：WPS 保存时会把文本框收缩为单行高（29 pt），故改为**写完文字后强制回写 SPEC 的
  Left/Top/Width/Height**，并在保存后把 `<a:spAutoFit/>` 归一化为 `<a:noAutofit/>`
  （`normalize_pptx()`，重打包时其余 zip 条目原样保留）；`verify()` 逐 `<p:sp>` 断言
  `<a:off>/<a:ext>` 与 SPEC 偏差 ≤ 0.6 pt。
- 效果：三件套（PPTX / SVG / CSV）重新全部由同一 `SPEC` 生成，PPTX 实测几何与 CSV/SVG 一致；
  12 个文本框不再有 y +3.0～+5.4 pt / h −1.0～−11.1 pt 的漂移。页脚实测
  `off=(508000, 6350000)` EMU=`(40, 500)` pt、`ext=(11176000, 330200)` EMU=`(880, 26)` pt，与 SPEC 相同。
- 目检：主负责 2026-10-31 20:09 重看 3 张 PNG——标题左对齐、盒内标签居中、页脚单行无溢出、中文无乱码。

### 1.7 第二轮独立复审与 P1-1 修复（2026-10-31 20:06–20:09）

**复审结论（`docs/reviews/v3_phase_H01_recheck.md`）：FAIL。** 独立复算确认：
C1 CLOSED；C2 原条件（12 个文本框几何、4 个文本框对齐）CLOSED；但 19:53 版把
`Alignment=1` 施加到全部 32 个文本形状，20 个盒内标签由“PPTX 居中 / SVG 居中”变成
“PPTX 左对齐 / SVG 仍居中”，实测左移 44.6 / 80.2 / 49.9 pt，故新增阻断项 **P1-1**。
同时提出 P2-1（`verify()` 不覆盖 18 条 `cxnSp`）与 P2-2（文本检查是整页集合而非逐形状映射）。

**修复内容：**

1. PS1 对齐改为按节点类型分流：`$n.textbox` → `Alignment=1`（左），其余 → `Alignment=2`（居中）。
   实测每页 `algn="l"` 4 个（title/subtitle/tag/footer）、`algn="ctr"` 6/7/7 个（盒内标签），
   与 SVG 的 20 个起点锚 + 49 行居中锚一一对应。
2. `verify()` 重写为 `verify_pptx()` + `verify_svg()` + `verify_pngs()`：
   - 逐 `p:sp` 绑定文本（`_shape_text == SPEC 文本`），不再用整页拼接串包含关系；
   - 逐 `p:sp` 断言段落对齐：文本框只允许 `l`（或缺省），盒内标签必须全部 `ctr`；
   - 逐 `p:cxnSp` 还原包围盒与 `flipH/flipV`，断言端点 ≤ 0.6 pt、端点方向、`tailEnd type="arrow"`、
     线宽；
   - 逐页解析 SVG `<text>`，断言文本框起点锚（无 `text-anchor`）与盒内标签 `text-anchor="middle"`
     且 x = 盒中心；
   - 保留 3 页、PNG 2000×1125、无 `ppt/media/`、无 `spAutoFit` 断言。
3. 新增反例夹具 `tests/test_h01_figure_verify.py`（9 例，1 正例 + 8 反例）：
   交换两个标签、连接线端点偏移、删 `flipV`、盒标签左对齐、文本框居中、插 `spAutoFit`、
   删箭头、SVG 锚点错配，均断言校验抛错。结果 **9/9 通过**。
4. 重生成 8 件套，`RC=0`；`verify()` 在真实产物上通过；主负责逐张目检 3 张 PNG。

**当前状态**：自评闭合 + 门禁通过 + 目检通过；第三次独立复审结果见 §1.8。

## 1.8 第三次独立复审（2026-10-31 20:12，报告 `docs/reviews/v3_phase_H01_recheck.md`）

**结论：PASS WITH CONDITIONS —— 针对 20:09:34 工作树快照 S2；建议改判，但改判对象必须是提交后的 S2。**
复审只读、未跑 COM、未改产物；几何/对齐/文本/指纹全部由复审方独立解析器复算（实现方 `verify()` 仅作交叉）。

| 判据 | 状态 | 关键实测 |
|---|---|---|
| C1 工具链口径 | **CLOSED** | `app.xml`=「WPS 演示」；slide 内 `p:pic`=0、`a:blip`=0；生成器/文档/页脚均为 WPS 口径 |
| C2 几何同源 | **CLOSED（对 S2）** | 32 个 `<p:sp>` 偏差 **0.000 pt**；18 条连接线最大 0.050 pt；`spAutoFit`=0；页脚 (40,500,880,26) pt |
| C2 对齐一致 | **CLOSED（对 S2）** | 12 文本框 `algn="l"` ↔ SVG 起点锚；20 盒标签 `algn="ctr"` ↔ `text-anchor="middle"`；PNG 墨迹偏差 ≤ 0.9 pt |
| C2（对 HEAD 旧版） | OPEN | 旧版 20 盒标签左对齐，最大偏移 82.4 pt —— 这是第二轮 FAIL 的对象 |
| 指纹 | **8/8** | 与本节指纹表逐条一致；字节数亦一致 |

**两条硬条件：**

- **Q-1（先提交再改判）**：S2 的 8 个产物、生成器、文档、新测试当时全部未提交，HEAD 仍是判 FAIL 的 S1。
  本条随本次提交闭合；GOAL 改判只对提交后的版本生效。
- **Q-2（时间戳）**：指纹段原写「20:08」，而产物落盘为 20:09:32–34。已改为「2026-10-31 20:09」并注明落盘时刻。

**新发现与处置：**

| 编号 | 级别 | 内容 | 处置 |
|---|---|---|---|
| N1 | P2（流程） | 复审期间产物被替换（20:06 测 8/8 → 20:09 重生成 → 20:10 文档更新），审核对象未冻结 | 已采纳：H01 产物冻结，后续复核期间不再重生成；任何重跑须先声明并重走评审 |
| N2 | P3 | SVG 未建模文本框 4 pt 左内边距，矢量版文本整体左移 4.4–4.8 pt | 本条按建议写入边界（§4），不改产物 |
| N3 | P3 | 「无位图」证据偏窄（只查 `ppt/media/`，整包仍有缩略图） | 已加强：`verify_pptx()` 增查每页 `p:pic`=0、`a:blip`=0；对现有产物只读复跑通过（未重生成、指纹不变） |
| N4 | P3 | `app.xml` 三个默认页标题仍为「PowerPoint 演示文稿」 | 元数据残留，不影响原生形状结论；记入 §4 |
| N5 | P3 | `verify_pptx()` 按文档顺序配对形状（不按 `cNvPr@name`） | 顺序错位会安全失败；同名互换风险记为已知局限（§4） |
| N6 | P3 | 新门禁测试未入库 | 随本次提交入库（`tests/test_h01_figure_verify.py`，9 例） |
| N7 | P3 | 反思日志 18:23 条「PowerPoint 拆 run」归因错误 | 已在原条目追加行内更正（保留历史原文与时间） |

**C3–C6（图面文案 vs 论文正文）**：复审判定**不阻断 H01**（H01 判据是结构与视觉），但全部 OPEN，
其中 C4（两臂 vs 正文三臂）、C5（20 万 vs 6 万审计帧）需在论文阶段处理。页脚「口径与论文第 2–3 章一致」
因 C3/C5 被削弱字面真实性，复审给出二选一（图注注明同义命名 / 页脚改「对应（差异见图注）」），
本阶段未动图，交由正文侧决定。**H01「通过」的含义因此限定为：三件套同源、几何/对齐/连接线一致、
工具链口径准确、结构自检与反例门禁成立**，不含图面文案与正文术语的最终对齐。

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
| 每页形状数 | 16 / 17 / 17（`p:sp` 10/11/11 + `p:cxnSp` 6/6/6） |
| 文本落地 | 逐 `<p:sp>` 绑定：该形状 `<a:t>` 拼接后必须等于 SPEC 对应节点的整串文本（交换标签会红） |
| 文本框几何 | 逐 `<p:sp>` 的 `<a:off>/<a:ext>` 与 SPEC 偏差 ≤ 0.6 pt；页脚实测 40/500/880/26 pt |
| 段首对齐 | 4 个文本框 `algn="l"`；盒内标签必须 `algn="ctr"`（6/7/7 个）；不再全局禁 `ctr` |
| 连接线 | 18 条 `p:cxnSp`：包围盒端点 ≤ 0.6 pt、`flipH/flipV` 方向、`tailEnd type="arrow"`、线宽 |
| SVG 锚点 | 文本框 20 个起点锚；盒内标签 49 行 `text-anchor="middle"` 且 x = 盒中心 |
| 自动缩放 | XML 无 `spAutoFit`（WPS 保存后由 `normalize_pptx()` 统一改为 `noAutofit`） |
| PNG 规格 | 3 张，均 2000×1125 |
| 无位图依赖 | 逐页 `p:pic`=0、`a:blip`=0，且 `ppt/media/` 为空（证明是原生形状而非截图）；整包仍有 WPS 模板自带的 `docProps/thumbnail.jpeg`，不被 slide 引用（N3 后由断言覆盖，不只靠目录名） |
| 反例夹具 | `tests/test_h01_figure_verify.py` 9 例（1 正 + 8 反）全过，证明上述门禁会红 |
| 元素清单 | 50 数据行 / 51 物理行，页/形状/文本/坐标齐全 |

运行输出（2026-10-31 20:09，P1-1 修复后重跑，`RC=0`）：

```
slides=3 shapes=16,17,17
pptx=True
verify: 3 slides, 3 PNG at 2000x1125, per-shape text/alignment + 18 connectors checked
written: outputs\figures\h01 (3 slides, 3 PNG, 3 SVG, 50 inventory rows)
```

视觉：主负责 2026-10-31 20:09 重看 3 张 PNG——标题/副标题/页脚左对齐，盒内标签恢复居中
（“处理臂”“五类估计器”“求解器”等宽盒左右留白对称），页脚单行无溢出，中文无乱码，
箭头指向正确。第 1 页下半部留白偏多，属可接受（未遮挡信息）。

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
- **SVG 文本内边距**：PPTX 文本框 `lIns=4 pt`，SVG 复刻从 `x=n.x` 起排、不含这 4 pt 内边距，
  矢量版文本相对 PNG 左移约 4.4–4.8 pt（第三次复审 N2）。若要像素级一致，需在 SVG 生成处加 `+4`。
- **元数据残留**：`docProps/app.xml` 的 `<TitlesOfParts>` 仍含三个 WPS 默认页标题「PowerPoint 演示文稿」
  （本图无标题占位符，N4）；不影响「原生形状、非截图」结论，但全文 grep `PowerPoint` 时会命中。
- **形状配对方式**：`verify_pptx()` 按文档顺序把 `<p:sp>` 与 `SPEC` 节点配对，未按 `cNvPr@name` 绑定（N5）；
  顺序整体错位会抛错，两个几何相同的形状互换则不会报。改图结构时应同时目检。
- **C3–C6 图面文案待办**：三口径命名、两臂 vs 三臂、OPE 输入与「20 万审计帧」措辞仍在图面，
  属论文正文阶段的口径统一事项（见 §1.8），修图时须重跑生成器并重走评审。
