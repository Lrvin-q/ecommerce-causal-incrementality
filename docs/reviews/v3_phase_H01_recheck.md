# H01「三方法图」C1/C2 闭环复审（第三轮）

维护时间：2026-10-31 20:12（北京时间，Asia/Shanghai）
复审人：独立 H01 复审代理（未参与 H01 生成，也未参与 2026-10-31 19:53 的 C1/C2 修复与 20:06 的第二轮复审）
复审方式：**只读**。未改 `outputs/figures/h01/`、未改 `scripts/64_*`、未装包、未跑 COM 生成、未 `git commit`、未跑 `run_all`。
写盘仅限：本文件 + `out/scratch/`（探针脚本、旧版对照图、第二轮报告备份）。

> **审计链说明**：本路径此前存放的是第二轮复审（2026-10-31 20:06，针对 19:53 版，判 FAIL）的原文，
> 已由主负责写入 H01 文档 §1.7。为不破坏审计链，本轮报告置于前部，**第二轮原文原样保留在文末「附录 A」**，
> 另有逐字节备份 `out/scratch/h01_recheck_round2_2006.md`（34 640 B）。

---

## 结论

**PASS WITH CONDITIONS —— 建议改判，但改判对象必须是"提交后的 S2"，不是现在的 HEAD。**

| 判据 | 状态 | 一句话依据（全部本轮自算） |
|---|---|---|
| C1 工具链口径 | **CLOSED** | `app.xml` = `WPS 演示`；`ppt/media/` 空、`p:pic`=0、`a:blip`=0；生成器 docstring/NOTE/PS1 与 H01 文档 §2/§4 均写 WPS 演示 COM（ProgID 借名）；仓库内已无"仍然有效"的错误表述 |
| C2 几何同源 | **CLOSED（对 S2）** | 32 个 `<p:sp>` 与 SPEC 偏差 **0.000 pt**（0 EMU）；18 条 `<p:cxnSp>` 最大 **0.050 pt**（635 EMU，WPS 零长度轴最小值）；`spAutoFit` **0**；页脚 `(40,500,880,26)` pt |
| C2 对齐一致 | **CLOSED（对 S2）** | 12 个文本框 `algn="l"` + SVG 无 `text-anchor`（起点锚）；20 个盒内标签 `algn="ctr"` + SVG `text-anchor="middle"` 且 x = 盒中心（0 错配）；PNG 墨迹实测盒标签居中偏差 **≤ 0.9 pt** |
| C2（对 HEAD `401d4f8` 的 19:53 产物） | **OPEN** | 该版把 `Alignment=1` 施加到全部 32 个形状，20 个盒标签左对齐而 SVG 仍居中，实测最大偏移 **82.4 pt**、均值 47.2 pt |
| 指纹可核 | **8/8 一致** | 与 20:10 版文档指纹表逐条相同（PPTX 98 380 B、PNG 166 584 / 179 458 / 183 514 B） |
| C3–C6 | 不在本轮 C1/C2 范围 | 见 §3：属"图面文案 vs 论文正文"的口径待办，按 GOAL H01 判据（结构与视觉）不阻断，但需点名 |

**为什么不是无条件 PASS**：S2 的 8 个产物、生成器、文档、新门禁测试**全部处于未提交状态**（`git status` 6 个 `M` + 2 个 `??`）。
我复核的是一个工作树快照，不是一个 commit；HEAD 仍是含 20 盒标签缺陷的 `401d4f8`。在 S2 提交之前改 GOAL，
等于把"未入库的工作树"记成"已验收版本"。**条件只有 2 条**（§4 的 Q-1、Q-2），都不需要重跑 COM。

**关于"无 `<a:pPr … algn="ctr">`"这条判据的口径**（重要，避免机械误判）：
20:09 版 PPTX 里**仍存在 20 处** `algn="ctr"`——它们全部是盒内标签，且与 SVG 的 `text-anchor="middle"` 一一对应，
**不构成不一致**。12 个文本框则全部 `algn="l"`，SVG 对应行全部无 `text-anchor`（左起 x=40）。
即"逐元素对齐一致"成立；"全页不得出现 ctr"这个字面来自 19:53 首版（全局左对齐），已被 20:09 版按类型分流取代，
H01 文档 §1.6 也已改写该口径。

---

## 0. 范围与未覆盖

### 0.1 两个快照

| 快照 | 定义 | 我的测量时间 | 结论 |
|---|---|---|---|
| **S1** | commit `401d4f8`（19:54:54）的 19:53 产物 + 19:55 文档 | 20:06–20:08 | C1 CLOSED；**C2 不闭合**（20/32 锚点与 SVG 相反） |
| **S2** | 工作树 20:09:32–34 重生成的 8 件套 + 20:10:14 更新的文档 + 未提交生成器/测试 | 20:09–20:12 | C1/C2 均 CLOSED，待提交 |

S1 与 S2 的差异只有 **PPTX + 3 张 PNG**（SVG、CSV 逐字节相同，故这两组指纹不变）；
`git diff --stat` = PPTX `98 337→98 380 B`、三张 PNG 换指纹、生成器 110 行改动、文档 95 行改动（`--stat` 只给合计行数，未拆增删）。

### 0.2 未覆盖 / 不可从磁盘复算的项

1. **未用 WPS GUI 或真 PowerPoint 打开 PPTX**：只做 OOXML 解析、PNG 目检、SVG XML 解析；"打开后可编辑、无修复提示"未验。
2. **未渲染 SVG**：本机无 cairosvg / LibreOffice，"SVG 视觉与 PNG 一致"只能由**坐标与锚点代数和**推出，不是像素比对。
3. **未跑生成器**：源码**没有 argparse**，`main()` 无条件调用 COM 重建 8 件套（并写 `C:\cg_h01_tmp`），**不存在 `--check` 干跑路径**；
   按纪律未运行。因此"19:53/20:09 两次 RC=0"只有文档自述，未被我复现。
4. **视觉判断**：3 张 PNG 直读（模型目检）+ 白/黑墨迹像素 bbox 测量；抗锯齿带来的边界不确定约 ±0.3 pt。
5. **换真 PowerPoint 的等价性**：未测。S2 的坐标是 WPS 渲染器下回写的，换渲染器须重跑（文档 §4 已写明）。

### 0.3 复审期间对象被替换（已记录，未规避）

我在 20:06 测得的 8 个 sha256 与当时文档（19:55 版）**8/8 一致**；20:09:32–34 有第三方作业重生成 4 个文件，
20:10:14 文档被改写为 20:09 版。本轮结论以 **20:11 的磁盘状态（S2）**为准，S1 的测量结果是独立留存的（§2.2 左列）。
这不是本次结论的减分项，但属"审核对象未冻结"的流程风险，见 §4 N1。

---

## 1. C1 / C2 逐条状态

### 1.1 C1（工具链口径）

| 子项 | 要求 | 我做的核查 | 结果 |
|---|---|---|---|
| C1-a | docstring/NOTE/PS1 明确写 WPS 演示、ProgID 借名、不装包 | 读 `scripts/64_h01_method_figures.py` L2–10、L70（NOTE）、L165（`New-Object -ComObject PowerPoint.Application`） | **CLOSED**：docstring 写"用 WPS 演示 COM 生成 PPTX：ProgID 借用 `PowerPoint.Application`，但 CLSID `{91493441-…}` 的 LocalServer32 指向 wpp.exe"；NOTE = "演示文稿原生形状（WPS 演示 COM 生成，可编辑，非截图）"；PS1 只用 ProgID 起服务（API 调用，不是身份声明） |
| C1-b | `docProps/app.xml` 应用名为「WPS 演示」 | `zipfile` 直读 | **CLOSED**：`<Application>WPS 演示</Application>`、`<PresentationFormat>宽屏</PresentationFormat>`、`<Slides>3</Slides>` |
| C1-c | PPTX 内无 `ppt/media/`、非截图 | 条目清单 + 全包 `a:blip`/`p:pic` 计数 | **CLOSED**：`ppt/media/` 为空（116 条目中无此目录）；3 页 `p:pic`=0、`a:blip`=0。附注：整包仍有 `docProps/thumbnail.jpeg` 43 133 B（首页缩略图，无 slide 引用），故"媒体目录空"是窄证据，见 §4 N4 |
| C1-d | 仓库内无仍生效的"PowerPoint 原生元素 / PowerPoint COM"错误表述 | 全仓 `grep -rn "PowerPoint"`（排除 `out/`、`.venv`）逐处判定 | **CLOSED**：有效表述全部为 WPS；残留 4 处均属历史条目（逐条列于 §2.5） |

### 1.2 C2（几何与对齐）

| 子项 | 要求 | S1（19:53 / HEAD） | S2（20:09 工作树） |
|---|---|---|---|
| C2-a | 无 `<a:spAutoFit/>` | 通过（`normalize_pptx()` 已归一化） | **CLOSED**：3 页 `spAutoFit` = 0，文本框 `noAutofit` 4/页 |
| C2-b | 文本框不得居中 | 通过（全部 `algn="l"`，但把 20 个盒子也带成左对齐） | **CLOSED**：12 个文本框全 `l`，20 个盒标签全 `ctr` |
| C2-c | 逐形状 `off/ext` 与 SPEC 偏差 ≤ 0.6 pt | 通过（0.000 pt） | **CLOSED**：32/32 形状 **0.000 pt**（0 EMU） |
| C2-d | 页脚 `(40,500)` / `(880,26)` pt | 通过 | **CLOSED**：`off=(508000,6350000)`、`ext=(11176000,330200)` EMU，三页相同 |
| C2-e | 形状数 16/17/17、文本整串命中 | 通过 | **CLOSED**：16（sp10+cxn6）/17（11+6）/17（11+6）；32 个形状逐形状文本**相等**（不是包含关系），0 缺失 |
| C2-f | SVG 与 PPTX 对齐一致 | **未通过**：20 个盒标签 PPTX 左 / SVG 居中，最大 82.4 pt | **CLOSED**：SVG 4/4/4 行起点锚 + 16/15/18 行居中标；x 与盒中心逐值相等（0 错配）；PNG 墨迹偏差 ≤ 0.9 pt |
| C2-g | PNG 2000×1125 | 通过 | **CLOSED**：IHDR 直读 2000×1125、bit depth 8、color type 6 |

**判断**：C2 的**原条件**（12 个文本框被 `spAutoFit` 改写、4 个文本框与 SVG 反向）在 S1 已闭合；
但 S1 的修法（全局 `Alignment=1`）把同类缺陷转移到 20 个盒标签上——这就是第二轮判 FAIL 的 P1-1。
**S2 已按元素类型分流并重生成，C2 在我能复算的全部维度上闭合。**

---

## 2. 实测证据（自算为主；实现方 `verify()` 仅作交叉，见 §2.6）

### 2.1 几何偏差（S2）

| 对象 | n | 最大偏差 | 位置 | 说明 |
|---|---|---|---|---|
| `<p:sp>` 对 SPEC `x/y/w/h` | 32 | **0.000 pt（0 EMU）** | — | 32 个形状全部精确相等，无 0.1 pt 级舍入 |
| `<p:cxnSp>` 还原端点对 SPEC 端点 | 18 | **0.050 pt（635 EMU）** | s2/e1（水平线） | 635 EMU 是 WPS 对"零长度轴"写的最小厚度，不是坐标错 |
| CSV 对 SPEC | 50 行 | 0 | — | 帧坐标与连线端点文本逐行相等 |
| SVG `<text>` x 对期望锚点 | 61 行 | **0** | — | 盒标签 x = 盒中心精确相等；文本框 x = 40 |

形状数：页1 = 16（`sp`10 + `cxnSp`6）、页2/3 = 17（11 + 6）；`p:pic`=0、`p:graphicFrame`=0、`a:tbl`=0。

### 2.2 对齐：三层证据（XML → SVG → PNG 像素）

**第 1 层（PPTX 段落属性）**

| 页 | `algn="l"` | `algn="ctr"` | 期望（按 SPEC 类型） |
|---|---|---|---|
| 1 | 4（title/subtitle/tag/footer） | 6（A–F） | 一致 |
| 2 | 4 | 7（A–G） | 一致 |
| 3 | 4 | 7（A–G） | 一致 |

**第 2 层（SVG 锚点）**：页1 `<text>` 20 行 = 4 起点锚 + 16 中文锚；页2 19 = 4 + 15；页3 22 = 4 + 18。
起点锚 12 行全部 x=40 且无 `text-anchor`；居中锚全部 `x = 盒x + 盒宽/2`，与 SPEC 逐值相等。

**第 3 层（PNG 墨迹，避圆角背景的中央条带 y+12…y+h−12）**

| 快照 | 盒标签 `ink中心 − 盒中心` | 计数 | 左右留白 |
|---|---|---|---|
| **S1（19:53）** | 最大 **−82.4 pt**（s2/E）、均值 47.2 pt | 18/20 > 20 pt，9/20 > 50 pt | 左 8.2–8.7 pt / 右最高 173.6 pt（明显左贴） |
| **S2（20:09）** | 最大 **−0.9 pt**（s2/D，抗锯齿边界），其余 ≤0.6 | 0/20 > 5 pt | 左右对称（如 s2/C：88.8 / 88.4 pt） |

S1 的这组数字就是第二轮 P1-1 的量化：修 C2 的那次改动让 20 个盒标签整体左移，SVG 仍居中，
"三件套同一几何"在 20/32 个文本块上不成立。**S2 的同一测量回到 0.9 pt 以内，说明重生成真的落到了 PNG 上**（不是只改 XML）。

> 我也直读了 S1 与 S2 的 PNG：S1 的盒内文字贴左、右侧大片空白（如页2 深色大盒、页3「支出与利润」）；
> S2 的盒内文字居中、页眉左对齐、页脚单行无溢出、中文无乱码、箭头落在目标盒边。与像素测量一致。

### 2.3 8 个指纹（逐字节，含字节数）

| 文件 | 字节 | sha256（前 16） | 文档表 |
|---|---|---|---|
| `v3_h01_three_methods.pptx` | 98 380 | `f11997b7305f1b80…` | MATCH |
| `slide1_itt.png` | 166 584 | `b4592f49da6f38bf…` | MATCH |
| `slide2_observational.png` | 179 458 | `561fbfae6c8cbd7d…` | MATCH |
| `slide3_policy.png` | 183 514 | `76d9682bbecf63ef…` | MATCH |
| `slide1_itt.svg` | 4 774 | `816005a6490aa8ed…` | MATCH |
| `slide2_observational.svg` | 4 779 | `db6cbff9c65b8614…` | MATCH |
| `slide3_policy.svg` | 5 244 | `e442e56d36c17b21…` | MATCH |
| `v3_h01_elements.csv` | 5 025 | `ad035d3698ae0ddb…` | MATCH |

-> **8/8**。时间线必须记清：同一检查在 20:06（对应 19:55 文档）也是 8/8；
20:09:32–34 重生成后一度只有 4/8（PPTX + 3 PNG 不符），20:10:14 文档更新后恢复 8/8。
**"文档表格与磁盘不符"的 FAIL 风险只存在于 20:09:34–20:10:14 这 40 秒窗口。**

### 2.4 `docProps/app.xml` 摘录（S2）

```
<Application>WPS 演示</Application><PresentationFormat>宽屏</PresentationFormat>
<Paragraphs>64</Paragraphs><Slides>3</Slides><Notes>4</Notes><HiddenSlides>0</HiddenSlides>
<HeadingPairs>… 已用的字体 5 / 主题 1 / 幻灯片标题 3 …</HeadingPairs>
<TitlesOfParts>… 微软雅黑, WPS, PowerPoint 演示文稿, PowerPoint 演示文稿, PowerPoint 演示文稿 …</TitlesOfParts>
```

- `Notes=4` 与包内 `notesSlides`=0 矛盾（WPS 模板写死），不可当备注数证据（首轮已记录）。
- `<TitlesOfParts>` 里的三个 "PowerPoint 演示文稿" 是 WPS 默认页标题（本图没有标题占位符），见 §4 N5。
- 全包唯一含 `PowerPoint` 的条目就是 `docProps/app.xml`（上述默认标题 + 主题名），**3 页 slide XML 内 `PowerPoint` 计数 = 0**，
  旧串"形状为 PowerPoint 原生元素"计数 = 0；三页页脚整串为
  「合成数据 / 已知 DGP · 演示文稿原生形状（WPS 演示 COM 生成，可编辑，非截图）· 口径与论文第 2–3 章一致」。

### 2.5 C1 的"残留表述"逐处判定（共 4 处，均历史）

| 位置 | 原文要点 | 判定 |
|---|---|---|
| `TODO.md:552-553`（18:18 条） | "本机**有 PowerPoint COM**（`New-Object -ComObject PowerPoint.Application` 成功）" | 历史日志；同文件 564-565 写"表述**不成立**"、19:55 条写"旧表述以本条为准"。**下游已显式否定，无行内作废标记**（P3） |
| `TODO.md:556-557`（18:23 条） | "驱动 PowerPoint COM，生成 3 页原生形状 PPTX" | 同上，历史日志（P3） |
| `AGENT_HANDOFF.md:72-78` | 节标题已写"其中"PowerPoint COM"口径已由 20:00 交接更正"，正文仍留旧句 | **可接受**（节标题显式作废） |
| `docs/v3_决策与反思日志.md:4705` | "PowerPoint 会把一行拆成多个 `<a:t>` run" | 历史条目 + **事实归因错误**（拆分 run 的是 WPS）；19:53 条更正了工具身份但未逐句改这一行（P3） |

`GOAL.md`、`docs/v3_G04_收尾审计.md:75`、H01 文档 §2/§4、生成器 docstring 均为**正确的 WPS 口径**，无残留。

### 2.6 与实现方自检的交叉（不作为唯一证据）

- 我**没有**把 `verify()` 当证据用；上表的几何/对齐/文本/指纹全部由我自己的解析器算出（见 §5 的探针脚本）。
- 交叉项：在 S2 上调了一次**只读**的 `verify_pptx()`（工作树版），返回 PASS；对 S1 的 PPTX 调同一函数会因
  "盒标签必须 `ctr`" 而抛 `AssertionError`——这与我独立测出的 S1 缺陷一致，可视为该门禁**真的能红**。
- 新门禁夹具 `tests/test_h01_figure_verify.py`（未入库，143 行）：我以 `-p no:cacheprovider`、`PYTHONDONTWRITEBYTECODE=1`
  实跑 **9 passed**（1 正例 + 8 反例：换标签 / 移端点 / 删 flipV / 盒标签左对齐 / 文本框居中 / 插 spAutoFit / 删箭头 / SVG 锚点错配）。
  形状是"从被消费脚本 import SPEC 现场造 PPTX"，不是手抄常量，符合 AGENTS §12.7。

---

## 3. C3–C6 的范围判定（点名，不作为 H01 判据）

| 条件 | 内容 | 我的归类 | 当前状态 |
|---|---|---|---|
| **C3** | 图上「预期 / 实际 / 硬预算三口径」与正文表 3-14「期望 / 缓冲 / 面值」两套命名 | **跨文档口径**（图面文案 ↔ 正文术语；改任一侧都可，需答辩口径统一） | **OPEN**，S2 图面未动；属主负责登记的正文/图注待办 |
| **C4** | 方法一画两臂，正文 F02 是三臂 ITT | **图面内容省略**（不是结构缺陷；tag 已写"三臂 ITT"，图内只示意两臂） | **OPEN**，需补第三臂或改 tag 措辞 |
| **C5** | 方法二 OPE 缺"名单 × 预算档"输入；页3「真值审计 每 rep 20 万随机验证」把 F02 的复核手段挂到 F01 的审计节点 | **图面口径混写**（同上，非管线结构问题） | **OPEN**，S2 仍是"每 rep 20 万随机验证" |
| **C6** | 净贡献利润 → 净增量贡献利润；τ̂ 下标 Π；13 pt `τ̂` 帽子观感；页1 下半留白；页3 A→B 箭头把"预算档"画成模型下游；文档"50 行"、"无位图"措辞 | **混合**：措辞/版式建议 + 文档卫生 | **OPEN**（"50 数据行/51 物理行"已在 20:09 文档改；其余未动；页1 留白仍在） |

**判定**：C3–C6 **不是 H01 产物缺陷**（不是管线、不是几何、不是可编辑性），而是"图面文案与论文正文/图注的口径待办"。
按 GOAL 的 H01 判据（"结构与视觉验收"）它们**不构成阻断**，我已按任务要求**点名、不据此判 FAIL**。
但有一条必须提醒：页脚整串写着"口径与论文第 2–3 章一致"，C3 与 C5 的 20 万/6 万项**削弱这句话的字面真实性**。
若改判 H01 为"通过"，建议同时二选一：① 在图注或文档里注明"三口径命名沿用 E02、与表 3-14 的期望/缓冲/面值同义"；
② 把页脚改为"口径与论文第 2–3 章对应（差异见图注）"。这是**正文侧**的决策，不归本轮。

---

## 4. 新发现问题（S2）

| 编号 | 级别 | 问题 | 证据 | 建议 |
|---|---|---|---|---|
| **N1** | **P2（流程）** | **复审期间产物被替换，审核对象未冻结**：20:06 我测到 8/8 匹配 19:55 文档；20:09:32–34 四个文件被重生成且文档尚未更新（4/8），20:10:14 文档才补上 | 两次 `sha256` 采样 + mtime 19:53:01→20:09:32 | 复核/验收期间冻结 `outputs/figures/h01/`（AGENTS §11 的精神：只读窗口）；否则任何"8/8 指纹一致"的结论都可能在几分钟后失效 |
| **Q-1** | **条件（阻断改判）** | **S2 全部未提交**：`M` 生成器 / PPTX / 3 PNG / 文档 / TODO，`??` 新测试 | `git status --porcelain`（6 M + 2 ??）；HEAD 仍是 `401d4f8` | 提交后再改判。**不提交则 HEAD 仍是被判 FAIL 的 S1 产物** |
| **Q-2** | **条件（文档）** | 文档时间戳与实际落盘不符：指纹段写"2026-10-31 20:08"，而 4 个文件 mtime 为 20:09:32–34；"维护时间 20:09" vs 文档 mtime 20:10:14 | mtime + 文档 §1 | 按 §10 改为实际时间（20:09 可留给"运行开始"，另记"落盘 20:09:32、文档定稿 20:10"） |
| **N2** | P3 | **SVG 未建模 4 pt 文本左内边距**：PPTX 文本框 `lIns=50800`（4 pt），墨迹起点实测 44.4–44.8 pt，SVG 写 `x=40` → 12 行文本在矢量版里整体左移 4.4–4.8 pt | `a:bodyPr lIns="50800"` + PNG 墨迹 + SVG x | SVG 文本 x 用 `n["x"]+4`，或在文档写明"SVG 复刻不含文本内边距（±5 pt）" |
| **N3** | P3 | 「无位图依赖」仍是窄证据：`assert not media` 只覆盖 `ppt/media/`，整包仍有 `docProps/thumbnail.jpeg`（43 133 B）；首轮建议改用 `a:blip` 计数未采纳 | zip 条目 + `a:blip`=0 | 把断言与措辞改成"slide 内 `a:blip`=0（0 张位图引用）；整包仅首页缩略图" |
| **N4** | P3 | `app.xml` 的 `<TitlesOfParts>` 仍是三个 "PowerPoint 演示文稿"（WPS 默认页标题） | §2.4 摘录 | 属元数据残留，不影响"原生形状"结论；若在意 grep，可给每页补真标题 |
| **N5** | P3 | `verify_pptx()` 以**文档顺序**把 `<p:sp>` 与 SPEC 节点配对（不按 `cNvPr@name`） | 源码 L~32；SPEC id 未写入 XML 的 name（现为"文本框 1""圆角矩形 4"） | WPS 改顺序会整体错位并抛错（安全失败），但两个同几何形状可能互换而不报；建议把 `n['id']` 写进 `cNvPr@name` 并按 name 绑定 |
| **N6** | P3 | 新门禁测试未入库（`?? tests/test_h01_figure_verify.py`） | git status | 与 Q-1 一并提交 |
| **N7** | P3 | `docs/v3_决策与反思日志.md:4705` 的 "PowerPoint 会把一行拆成多个 run" 仍无行内更正 | grep | 追加一句"（2026-10-31 19:53 更正：拆 run 的是 WPS 演示）" |

**没有发现 S2 的结构性新伤**：几何 0.000 pt、连线 0.050 pt、文本逐形状相等、CSV 50 行全等、无位图、无 autofit、PNG 规格正确。

---

## 5. 实际运行过的命令（全部只读，除注明处）

```bash
# 时间与状态
date '+%F %H:%M:%S %z'
ls -l --time-style=full-iso outputs/figures/h01/
git log --oneline -5; git show --stat 401d4f8; git show 401d4f8 -- scripts/64_h01_method_figures.py
git status --porcelain; git diff --stat; git diff -- scripts/64_h01_method_figures.py

# 探针（我自写，只读；落在 out/scratch/）
./.venv/Scripts/python.exe out/scratch/h01_recheck_probe.py     # 指纹/结构/几何/autofit/对齐/文本/CSV/PNG IHDR
./.venv/Scripts/python.exe out/scratch/h01_recheck_probe2.py    # 连线端点(flipH/V 还原)、逐形状 algn、旧版对照、SVG 锚点
./.venv/Scripts/python.exe out/scratch/h01_recheck_probe3.py    # 墨迹/页脚 EMU（首版阈值被圆角背景干扰，已弃用其数字）
./.venv/Scripts/python.exe out/scratch/h01_recheck_probe4.py    # 避圆角的墨迹测量（S1/S2 的盒标签偏移表）

# 旧版对照（只读 git blob，写 out/scratch）
git show c04dce7:outputs/figures/h01/v3_h01_three_methods.pptx > out/scratch/h01_old_pptx
git show c04dce7:outputs/figures/h01/slide3_policy.png       > out/scratch/h01_old_slide3.png

# 交叉：只读调用工作树版门禁（不生成产物）
./.venv/Scripts/python.exe -c "…import scripts/64…; verify_pptx(Path('outputs/figures/h01/v3_h01_three_methods.pptx'))"

# 新门禁夹具（不写仓库缓存）
PYTHONDONTWRITEBYTECODE=1 ./.venv/Scripts/python.exe -m pytest tests/test_h01_figure_verify.py -q -p no:cacheprovider
# -> 9 passed

# grep（PowerPoint 残留）
grep -rn "PowerPoint" --include=*.md --include=*.py . | grep -v "^./out/"
```

**未运行**：`scripts/64_h01_method_figures.py`（无 `--check`，`main()` 会重建 8 件套并起 COM）、`run_all.py`、全量 `pytest`、任何 pip 安装。
（说明：唯一可能的仓库外写盘是 pytest 自身的临时目录；已用 `-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1`，仓库内无新增缓存文件。）

---

## 6. 我的建议（窄口径）

1. **现在就做**：把 S2（生成器 + 4 个换指纹产物 + 文档 + 新测试）作为一个 commit 提交；顺手改 Q-2 的两个时间戳（N2/N6 可选）。
2. **然后**：GOAL 的 H01 可记为"通过（结构验收）"，含义限定为"3 页原生形状、三件套同一几何（形状 0.000 pt、锚点逐元素一致）、8 个指纹可核、无位图"；
   **明确排除** C3–C5 的口径问题与"定向有效"之类内容性主张。
3. **不要**在 S2 提交前改判：HEAD 仍是 S1，而 S1 的 C2 有 20 个盒标签的实测 82.4 pt 偏移。
4. 若主负责选择"不提交、直接在 HEAD 上改判"，则本报告判 **FAIL**（依据：被审对象 = S1，C2 的"三件套同一几何"在 20/32 文本块上不成立）。

> 本报告只是草稿，主负责须复核关键数字与口径后再改 GOAL（AGENTS §7.4）。我不对改判本身负责，只提供可复算的证据与两个快照的边界。

---

## 附录 A：第二轮复审原文（2026-10-31 20:06，针对 19:53 版产物；判 FAIL）

> 以下内容为原样保留（逐字节备份：`out/scratch/h01_recheck_round2_2006.md`，34 640 B），
> 不是我本轮的计算结果；其中"S1 = 19:53 版"的缺陷结论我已独立复现（§2.2 左列）。

---

# H01 C1/C2 修复独立复核（复审）

维护时间：2026-10-31 20:06（北京时间，Asia/Shanghai）
复核对象：commit `401d4f8a54f7dde04d9af7ea08bd5c0bfb44bfbf`（2026-10-31 19:54:54 +0800）
产物：`outputs/figures/h01/*`（mtime 2026-10-31 19:53:01–19:53:03 +0800，8 个文件）
复核方式：只读。未改任何代码/产物/文档（本文件除外），未跑 `scripts/64`、`run_all`、`pytest`，未安装包，未提交。
复核人：独立复核代理（不是实现者；结论不受实现方自述约束）。

---

## 0. 结论

**总体：FAIL。**

| 条件 | 状态 | 一句话依据 |
|---|---|---|
| C1（工具链口径） | **CLOSED** | `app.xml` = `WPS 演示`；CLSID `{91493441-…}` 的 `LocalServer32` = `wpp.exe /Automation`；三页页脚全文已换为 WPS 文案；仓库内已无“仍然有效”的“PowerPoint 原生元素 / 本机有 PowerPoint COM”表述。 |
| C2（原条件：12 个文本框几何 + 4 个文本框对齐） | **CLOSED** | 12 个文本框的 `<a:off>/<a:ext>` 与 SPEC/CSV 偏差 **0.000 pt**（旧版 y 偏 +3.0～+5.4、h 偏 −1.0～−11.1 已消失）；4 个文本框在 PPTX 与 SVG 中均为左对齐。 |
| C2 的目标（PPTX/SVG 文本对齐一致） | **NOT CLOSED（新增 P1-1）** | 修复把 `ParagraphFormat.Alignment=1` 施加到**全部 32 个文本形状**；20 个盒子标签由“PPTX 居中 / SVG 居中”变成“**PPTX 左对齐 / SVG 仍居中**”。三件套的不一致元素从 12 个变成 **20 个**（12/32 → 20/32），实测标签左移 **44.6 / 80.2 / 49.9 pt**。 |

**为什么判 FAIL 而不是 PASS WITH CONDITIONS**：本轮复审的对象就是“C1/C2 是否修好”。C1 已闭合，C2 原缺陷已闭合，但修复**新引入**的 P1-1 是同一类错误（PPTX 与 SVG 文本对齐相反），且影响面从 12 个扩大到 20 个文本形状；H01 文档却已写“C2 — CLOSED”“三件套一致”。在 P1-1 修复并重生成、再经一次独立复核之前，H01 不能放行。

**关键数字（全部本轮独立复算）**：

- 8 个 sha256 与文档指纹表 **8/8 一致**；PPTX 98 337 B；PNG 166 495 / 179 233 / 183 618 B。
- 形状数 **16 / 17 / 17**（`sp` 10/11/11 + `cxnSp` 6/6/6）；`a:blip`=0、`p:pic`=0、`ppt/media/` 空。
- PPTX 的 32 个 `sp` 对 CSV：**最大偏差 0.000 pt（0 EMU）**；18 条 `cxnSp` 对 CSV：**最大 0.050 pt（635 EMU，WPS 零长度轴最小值）**；SVG 的 rect/line 对 CSV：**0.000 pt**。
- `spAutoFit` **0**；`<a:pPr … algn="ctr">` **0**；32/32 段落实际 `algn="l"`；PNG **2000×1125**（8 bit、color type 6）。
- **P1-1**：20 个盒子标签文字在 PNG/PPTX 中左对齐（盒左 + ~4 pt），在 SVG 中仍 `text-anchor="middle"`（盒中心）；实测旧→新 PNG 标签左移 44.6 / 80.2 / 49.9 pt；宽盒右侧留白最大 **168.8 pt**（左侧仅 8.5 pt），SVG 同盒为 88.7/88.7 pt。

---

## 1. 复核环境

| 项 | 值 |
|---|---|
| 时间 | 2026-10-31 19:55–20:06（北京时间） |
| worktree | `C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目` |
| commit | `401d4f8a54f7dde04d9af7ea08bd5c0bfb44bfbf`；H01 的 8 个产物与 H01 文档、生成器在该 commit 中，`git status` 对这 10 个路径为空 |
| Python | `.venv\Scripts\python.exe`，3.13.7（MSC v.1944 **64 bit AMD64**）；Pillow 13.0.0 |
| 其他 | `reg query`、`winreg`（只读）、`zipfile`、`xml.etree.ElementTree`、`hashlib`、`csv`、Pillow 像素 bbox；`Read` 工具逐张目检 |
| 工作树其他改动 | `docs/v3_G04_收尾审计.md`、`docs/v3_phase_G03_formal.md`、`docs/v3_phase_G_run_registry.md`、`scripts/33…`、`scripts/49…` 等为 G03 轨的未提交改动，**不涉及 H01**；本报告未触碰 |

复核开始前已确认 `outputs/figures/h01/*` 的 8 个 mtime 为 19:53:01–19:53:03，H01 文档 mtime 19:53:54，生成器 mtime 19:52:56。

---

## 2. C1 检查表

### 2.1 旧表述 grep：命中、判断、证据

命令（等价于本轮使用的 Grep 工具）：

```bash
rg -n --glob '!out/**' --glob '!.venv/**' \
  -e 'PowerPoint 原生|PowerPoint原生|本机有 PowerPoint|本机 PowerPoint|形状为 PowerPoint|PowerPoint COM|PowerPoint（COM）|PowerPoint 元素|PowerPoint 生成|原生元素' .
```

共 41 处 `PowerPoint`，分布在 7 个文件；逐处判断如下。

| 文件:行 | 原文（摘要） | 判断 |
|---|---|---|
| `AGENT_HANDOFF.md:5-8` | “C1＝本机 COM 实为 **WPS 演示（wpp.exe）**…**此前 18:26/19:52 交接里的‘PowerPoint COM / PowerPoint 原生元素’表述作废**” | **有效且正确**（显式作废旧说法） |
| `AGENT_HANDOFF.md:15-17` | “WPS COM 保存会把文本框高度压成单行高…换真 PowerPoint 重建时坐标可能不同” | **有效且正确**（换工具的真实风险） |
| `AGENT_HANDOFF.md:44` | 节标题“交接（2026-10-30 18:26…；其中‘PowerPoint COM’口径已由 20:00 交接更正）” | **历史条目，节标题显式标注作废** |
| `AGENT_HANDOFF.md:47` | “…**纯 ASCII PS1** 驱动 PowerPoint COM（不装包），产出…102 345 B” | **历史条目**：所在节标题已写明口径被 20:00 更正；正文未逐句改写。属 **P3 文档卫生**，不构成有效错误表述 |
| `TODO.md:7-8` | “最新动作（19:55）…C1：实际 COM 是 **WPS 演示（wpp.exe）**，ProgID 只是借名…” | **有效且正确** |
| `TODO.md:552-553` | “**18:18 更正**：本机**有 PowerPoint COM**（PowerShell `New-Object -ComObject PowerPoint.Application` 成功）…” | **历史日志条目**；同文件 18:32 条（564-565）明确写“表述**不成立**”，19:55 条（568）写“旧表述以本条为准”。**已被下游显式更正**，但 552 行本身无行内“作废”标记，属 **P3** |
| `TODO.md:556-557` | “…驱动 PowerPoint COM，生成 3 页原生形状 PPTX（102 345 B）” | **历史日志条目**（18:23），同上；P3 |
| `TODO.md:564-565` | “C1＝所谓 PowerPoint.Application 的 CLSID 实际是 WPS 演示…‘本机有 PowerPoint COM / PowerPoint 原生元素’的表述**不成立**” | **评审引用 + 明确否定**，正确 |
| `TODO.md:568-569` | “19:55 C1/C2 已修（旧表述以本条为准）…LocalServer32 指向 wpp.exe” | **有效且正确** |
| `docs/reviews/v3_phase_H01_review.md:12, 39, 94-100, 140, 153` | 首轮评审的缺陷描述与证据命令 | **历史评审引用**，不是产品声明 |
| `docs/v3_phase_H01_method_figures.md:49-54` | C1 更正段：引用“本机有 PowerPoint COM”“形状为 PowerPoint 原生元素”并写“**不成立**”“需改” | **引用旧说法以宣布作废**，不是有效错误表述 |
| `docs/v3_phase_H01_method_figures.md:70-74` | “生成器 docstring 与 §2 统一改为 WPS 演示 COM…不再声称‘本机有 PowerPoint’” | **有效且正确** |
| `docs/v3_phase_H01_method_figures.md:91-94` | “18:18 实测 `PowerPoint.Application` ProgID 能创建 COM 实例；18:32 评审查明…wpp.exe…实际工具链是 WPS 演示 COM（ProgID 借名），不是 Microsoft PowerPoint” | **有效且正确**（“ProgID 能创建实例”是事实，紧接否定 Microsoft 身份） |
| `docs/v3_phase_H01_method_figures.md:147-148` | “生成依赖本机 WPS 演示（COM，ProgID 借用 `PowerPoint.Application`）…真 PowerPoint 下坐标可能不同” | **有效且正确** |
| `docs/v3_G04_收尾审计.md:73` | “H01（PPTX）实走 **WPS 演示 COM**（ProgID 借名 `PowerPoint.Application`…）” | **有效且正确** |
| `docs/v3_决策与反思日志.md:4694` | “…用一行 `New-Object -ComObject PowerPoint.Application` 就推翻了它——COM 建出来的演示文稿本身就是原生 PPTX” | **历史叙述**：说的是“能创建”，未声称 Microsoft 身份；下游 4769-4773 已更正 |
| `docs/v3_决策与反思日志.md:4705` | “…再加逐页文本前缀命中（**PowerPoint 会把一行拆成多个 `<a:t>` run**…” | **历史条目中的事实归因错误**：实际拆分 run 的是 WPS，不是 PowerPoint。19:53 条（4769-4773）更正了工具身份，但未逐句改这一行。判 **P3**（不影响 C1 的有效产物） |
| `docs/v3_决策与反思日志.md:4769-4773` | “C1：`PowerPoint.Application` 这个 ProgID 不代表 Microsoft PowerPoint…判断工具身份要查三处…” | **有效且正确** |
| `scripts/64_h01_method_figures.py:5-6` | docstring：“用 WPS 演示 COM 生成 PPTX：ProgID 借用 `PowerPoint.Application`，但 CLSID … 指向 wpp.exe” | **有效且正确** |
| `scripts/64_h01_method_figures.py:165` | `$app = New-Object -ComObject PowerPoint.Application` | **API 调用本身**，不是身份声明；正确（借名 ProgID） |

**判断**：仓库内**没有“仍然有效”的“PowerPoint 原生元素 / 本机有 PowerPoint COM / 形状为 PowerPoint”表述**。所有命中要么是有效更正，要么是历史评审/引用/明确作废，要么是借名 ProgID 的 API。C1 的口径修复成立。
残留的 P3：`TODO.md:552/557`、`AGENT_HANDOFF.md:47`、`docs/v3_决策与反思日志.md:4705` 是历史日志，没有逐行“作废”标记；若按 AGENTS §12.4 的严格口径，可加“（已作废，见 2026-10-31 19:55 条）”，但不影响结论。

### 2.2 COM 身份：注册表 + 包内元数据（不只读文档）

命令与实测：

```text
reg query 'HKCR\PowerPoint.Application\CLSID'
  -> {91493441-5A91-11CF-8700-00AA0060263B}

reg query 'HKCR\CLSID\{91493441-5A91-11CF-8700-00AA0060263B}\LocalServer32' /reg:32
  (默认) REG_SZ  C:\Users\26382\AppData\Local\Kingsoft\WPSOFF~1\1210~1.296\office6\wpp.exe /Automation
  LocalServer32  REG_MULTI_SZ  同上

reg query 'HKCR\CLSID\{91493441-5A91-11CF-8700-00AA0060263B}' /reg:64
  -> 系统找不到指定的注册表项或值（exit 1；64 位视图无此键）

Python zipfile 读 pptx/docProps/app.xml：
  Application = WPS 演示
  AppVersion  = 14.0000
  PresentationFormat = 宽屏
  Slides = 3
```

补充：`winreg` 的 32 位视图还显示 `ProgID = PowerPoint.Application.12`、`VersionIndependentProgID = Powerpoint.Application`、`InprocHandler32 = ole32.dll`。CLSID 键的默认描述是“Microsoft PowerPoint 应用程序”（WPS 兼容层的借名），但**真正被激活的 LocalServer32 是 wpp.exe**。

**结论**：`New-Object -ComObject PowerPoint.Application` 激活的是 **WPS 演示**，不是 Microsoft PowerPoint。C1 的根因判断正确。

**一个需要记录的注册表事实**：该 CLSID 只在 **32 位注册表视图**可见；`/reg:64` 无此键，本机 `powershell` 是 64 位（`Is64BitProcess=True`）。19:53 的重建确实成功（rebuild4 日志 + 产物），说明实际链路可用；我**没有**再做 COM 激活实验（避免启动 WPS），因此无法独立断言 64 位 COM 是否跨视图解析。换机器重建时，应同时确认目标位数的视图里有该 CLSID；这不影响本轮 C1 结论。

### 2.3 逐页页脚全文

命令：解压 `ppt/slides/slide{1,2,3}.xml`，按 `<a:p>/<a:r>/<a:t>` 拼接每个 `sp` 的全文（`<a:br/>` 转换行），取该页最后一个 `sp`。

实测三页页脚全文（逐字）：

```text
合成数据 / 已知 DGP · 演示文稿原生形状（WPS 演示 COM 生成，可编辑，非截图）· 口径与论文第 2–3 章一致
```

- 三页 **3/3** 完全一致；页脚在 slide XML 中为**单个段落、单行**（无 `<a:br/>`）。
- slide XML 中 `PowerPoint` 出现次数：**0**；旧串“形状为 PowerPoint 原生元素”出现次数：**0**。
- 页脚盒几何 `(40, 500, 880, 26) pt`；PNG 像素 bbox 为 x 44.2–490.1、y 507.8–517.4 pt，**未溢出**（右边界 920 pt 远未触及）。

**C1 结论：CLOSED。** 依据是包内元数据 + 注册表 + 逐页页脚全文，不依赖实现方文档自述。

---

## 3. C2 检查表

### 3.1 8 个 sha256 对照

命令：

```bash
./.venv/Scripts/python.exe -c "import hashlib,pathlib; [print(hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_size, p.name) for p in sorted(pathlib.Path('outputs/figures/h01').iterdir())]"
```

| 文件 | 本轮 sha256 | 文档 §1 指纹 | 字节 | 对照 |
|---|---|---|---|---|
| `v3_h01_three_methods.pptx` | `b204f3927192239f57facec885052bd98c032800fe2d17e6efb0d8f666841202` | 同 | 98 337 | **一致** |
| `slide1_itt.png` | `daf5fd2bbd0c524feb3a85747bc60860dae8c14b3f2767553851b30898853632` | 同 | 166 495 | **一致** |
| `slide2_observational.png` | `9c8b4a9cdf66af6ca292c3361fc2c93cbcacf7ea2bdb637ca01757269473bcd1` | 同 | 179 233 | **一致** |
| `slide3_policy.png` | `6a42ae992a462bca2405208ff6a356f459a5c5fe29c6514388f6244e5e6a020b` | 同 | 183 618 | **一致** |
| `slide1_itt.svg` | `816005a6490aa8ed9b54a1872263f9cc94c35d725d93e0ee9e182599634c6c02` | 同 | 4 774 | **一致** |
| `slide2_observational.svg` | `db6cbff9c65b86146fafcc32906da66f66e84661762ebc2fa4498e6ff987a92e` | 同 | 4 779 | **一致** |
| `slide3_policy.svg` | `e442e56d36c17b2132a400475ec016784dd0fb793a78514749d4144cb33ad168` | 同 | 5 244 | **一致** |
| `v3_h01_elements.csv` | `ad035d3698ae0ddb36ad0a2fd0fc45713365c7a36372792e08bcba330e8a1c77` | 同 | 5 025 | **一致** |

**8/8 一致**；文档指纹表对应当前磁盘产物，不是旧版。

### 3.2 形状数、几何、CSV/SVG 三方对照

方法（本轮独立脚本，不是 `verify()`）：
- 解压 3 份 slide XML，遍历 `p:spTree` 的直接子元素，按 `p:sp` / `p:cxnSp` 计数；
- 逐 `p:sp` 读 `<a:off x y>`、`<a:ext cx cy>`（EMU ÷ 12700 = pt）；
- 用**拼接后的全文**在 CSV 中**唯一匹配**元素（不是按 XML 顺序猜），再比坐标；反向亦唯一；
- `cxnSp` 用 `<a:xfrm>` 的 `flipH/flipV` 还原端点；
- SVG 用 `xml.etree` 读 `rect/line/text`，rect/line 与 CSV 对应行比。

| 检查 | slide1 | slide2 | slide3 |
|---|---|---|---|
| `p:sp`（文本框 + 盒子） | 10 | 11 | 11 |
| `p:cxnSp`（连接线） | 6 | 6 | 6 |
| 合计 | **16** | **17** | **17** |
| PPTX `sp` vs CSV 最大偏差 | **0.000 pt（0 EMU）** | 0.000 pt | 0.000 pt |
| PPTX `cxnSp` vs CSV 最大偏差 | **0.050 pt（635 EMU）** | 0.050 pt | 0.050 pt |
| SVG rect vs CSV 最大偏差 | **0.000 pt** | 0.000 pt | 0.000 pt |
| SVG line vs CSV 最大偏差 | **0.000 pt** | 0.000 pt | 0.000 pt |
| 文本元素（sp）与 CSV 唯一匹配 | 10/10 | 11/11 | 11/11 |
| XML 顺序 vs CSV `z_order` | 1..16 完全一致 | 1..17 | 1..17 |

细节：
- **12 个文本框**（每页 4 个：title/subtitle/tag/footer）全部 **0.000 pt**。旧版（`401d4f8^`）的漂移在本轮复算中精确复现并已消除：

| 文本框 | 旧 PPTX `(x,y,w,h)` | SPEC/CSV `(x,y,w,h)` | 旧偏差 | 新偏差 |
|---|---|---|---|---|
| title | (40, 12.375, 880, 33.05) | (40, 16, 880, 34) | y −3.625、h −0.95 | **0.000** |
| subtitle | (40, 55.025, 880, 19.75) | (40, 52, 880, 24) | y +3.025、h −4.25 | **0.000** |
| tag | (40, 82.25, 880, 17.3) | (40, 78, 880, 22) | y +4.25、h −4.7 | **0.000** |
| footer | (40, 505.45, 880, 14.9) | (40, 500, 880, 26) | y +5.45、h −11.1 | **0.000** |

- **18 条连接线**端点全部命中：`flipH/flipV` 还原后与 CSV 的 `(x1,y1)->(x2,y2)` 最大差 **0.05 pt**（WPS 对零长度轴写 `ext=635 EMU`，如 slide2 e1 的终点 y=185.05 vs CSV 185.0；这是 WPS 的最小 extent，不是方向错误）。
- **形状顺序**：XML 中 `sp` 顺序 = `title, subtitle, tag, A…G, footer`，`cxnSp` 顺序 = `e1…e6`，与 CSV `z_order` 逐行一致；没有因重生成而重排。
- **颜色/字体/线宽**：20 个 `shape5` 的 `solidFill` 与 CSV `fill_or_stroke` 去 `#` 后 **0 不符**；字体全部 `微软雅黑`（`Microsoft YaHei` 的本地名）；字号 24/13/11/14/9 与 CSV 一致；18 条连接线 `595959`、2.0 pt、`tailEnd type="arrow"`，与 CSV **0 不符**。
- **PPTX 包完整性**：`zipfile.testzip() = None`，116 个条目，`[Content_Types].xml` 存在，3 份 slide XML，`notesSlides` 0，`sldSz = 12192000×6858000 EMU = 960×540 pt`。

**判定**：盒体几何、连接线、SVG rect/line、CSV 三方**逐值一致**；C2 的“12 个文本框几何”部分确实 CLOSED。

### 3.3 autofit / 段落对齐实测

命令：逐 slide 统计 `spAutoFit`、`<a:pPr … algn="ctr">`、每个 `a:p` 的 `pPr@algn`、`bodyPr@anchor`。

| 检查 | slide1 | slide2 | slide3 |
|---|---|---|---|
| `spAutoFit` | **0** | **0** | **0** |
| `<a:noAutofit/>`（4 个文本框） | 4 | 4 | 4 |
| `<a:pPr … algn="ctr">` | **0** | **0** | **0** |
| 段落实际 `algn` | 10/10 = `l` | 11/11 = `l` | 11/11 = `l` |
| `<a:ln … algn="ctr">`（线端对齐，非段落） | 6 | 6 | 6 |
| `bodyPr@anchor` | `ctr` | `ctr` | `ctr` |
| 文本内边距 | lIns 50800 / tIns 25400 / rIns 50800 / bIns 25400 EMU（4/2/4/2 pt） | 同 | 同 |

说明：`<a:ln … algn="ctr">` 是**连接线线端对齐**，不是段落居中；实现方把 verify 的匹配从 `algn="ctr"` 收窄到 `<a:pPr … algn="ctr">` 是正确的（rebuild3 日志显示旧宽匹配曾误伤它）。

**但**：32/32 段落全部为 `l`，包括 **20 个盒子标签**。这正是 P1-1 的根因（见 §5）。

### 3.4 位图媒体 / PNG 规格

| 检查 | 结果 |
|---|---|
| `ppt/media/` | **空**（0 个条目） |
| slide 内 `p:pic` | **0** |
| slide 内 `a:blip` | **0**（`<a:blip` 计数 0） |
| 整包位图 | 仅 `docProps/thumbnail.jpeg`（**43 133 B**，WPS 模板首页缩略图，无 slide 引用） |
| PNG 签名/尺寸 | 3 张均 PNG 签名正确、**2000×1125**、bit depth 8、color type 6（RGBA） |
| PNG 字节 | 166 495 / 179 233 / 183 618，与文档一致 |

**判定**：slide 内容是原生 OOXML 形状，不是截图；“无位图依赖”在 slide 范围内成立；整包仍有 1 张模板缩略图（P3 措辞，不影响 C2）。

### 3.5 C2 结论

- **原条件（12 个文本框几何 + 4 个文本框对齐）：CLOSED。** 证据是 0.000 pt、0 autofit、0 居中、8/8 指纹、PNG 2000×1125。
- **但 C2 的目标（PPTX/SVG 文本对齐一致）：NOT CLOSED。** 修复把 32/32 段落改为左对齐，而 SVG 只对 4 个文本框左对齐，20 个盒子标签仍居中。详见 §5 P1-1。

---

## 4. 视觉检查（逐张 `Read`，2000×1125 原图）

**slide1_itt.png（方法一）**：标题、副标题、tag、页脚均左对齐；页脚单行、无溢出；中文无乱码/豆腐块；盒内文字无溢出；箭头 A→B/C、B/C→D、D→E、E→F 指向正确。**盒内标签已变为左对齐**（“处理臂”“发 10 元券”紧贴盒左），与旧版/ SVG 的居中不同（P1-1）。第 1 页图体下沿 **281.8 pt**，页 2/3 为 **477.6 pt**，下半部约 36% 页高留白；**不遮挡信息**，但三页版式不齐（C6 #4 仍未处理）。

**slide2_observational.png（方法二）**：标题/副标/页脚左对齐；页脚单行；无乱码、无溢出；A→B、B↓C、C→D、D→E、E↘F（OPE）、F→G 方向正确。**“五类估计器”盒（340 pt 宽）文字左对齐后，右侧留白约 168.8 pt、左侧仅 8.5 pt**，视觉明显偏左；SVG 同盒为 88.7/88.7 pt 居中。该页是新旧版差异最明显的一页。

**slide3_policy.png（方法三）**：标题/副标/页脚左对齐；页脚单行；无乱码；箭头 A→B、A↘C、C→D、D→E、D↓F、F→G 方向正确；τ̂ 在 13 pt 下帽子仍偏左上（C6 #3，既有观感问题）；A→C 斜箭头起点在 A 的右下角（C6 #5 的歧义仍在，非本轮新增）。**“求解器”盒（310 pt）左对齐后右侧留白约 108.5 pt、左侧 8.5 pt**；SVG 同盒 58.5/58.5 pt。

**总体视觉**：无乱码、无溢出、页脚单行、箭头无明显错误、第 1 页留白不遮挡信息；标题/副标/页脚的左对齐修复在 PNG 上成立。**但 20 个盒内标签的左对齐是本次新引入的视觉变化，且与 SVG 不一致**（P1-1），不是 C1/C2 要求的“标题/副标/页脚左对齐”范围。

---

## 5. 新发现

### P0

无。

### P1-1（新引入，阻断放行）：20 个盒子标签的段落对齐被一并改为左对齐，SVG 仍居中

**事实链（全部独立复算）**：

1. **旧版 PPTX**（`git show 401d4f8^:outputs/figures/h01/v3_h01_three_methods.pptx`）的 **32/32** 个 `sp` 段落都是 `algn="ctr"`；其中 12 个文本框的几何有漂移（见 §3.2），20 个盒子标签（roundRect）几何本来正确。
2. **旧版 SVG**：4 个文本框 `<text x="40">` 无 `text-anchor`（左），20 个盒子标签的 49 行文字全部 `text-anchor="middle"`、`x = 盒中心`。所以旧版的不一致只有 **12 个文本框**（PPTX 居中 vs SVG 左），20 个盒子标签是**一致**的（居中/居中）。
3. **修复**在 PS1 循环里对**每个** `$shp.TextFrame` 设 `ParagraphFormat.Alignment = 1`（不是只对 `$n.textbox`），所以 **32/32** 段落变成 `algn="l"`；`verify()` 又加了全局“不得出现 `<a:pPr … algn="ctr">`”，把这一行为固化成门禁。
4. **新版 SVG** 在 commit 中只改了页脚字符串（`git show 401d4f8 -- outputs/figures/h01/slide1_itt.svg` 仅 1 行增删），**盒子标签的 `text-anchor="middle"` 与 x 完全没动**；CSV 也只改了 3 行 footer 文本，几何本来就是 SPEC 值。
5. 结果：**新版 PPTX/PNG 盒子标签左对齐（盒左 + ~4 pt），新版 SVG 盒子标签仍居中（盒中心）**。不一致元素从 **12/32 变成 20/32**；修复了 12 个文本框，却新破坏了 20 个盒子标签，净增 8 个不一致。

**量化（旧/新 PNG 像素 bbox，Pillow；pt = px × 0.48）**：

| 标签（盒） | 旧 PNG 文字左缘 | 新 PNG 文字左缘 | 左移 | 盒中心 | SVG 的 x/锚点 | 新 PNG 左/右留白 | SVG 左/右留白 |
|---|---|---|---|---|---|---|---|
| 处理臂（230–400，w=170） | 282.2 pt | **237.6 pt** | **−44.6 pt** | 315 | `x=315, middle` | 7.6 / 97.1 | 52.35 / 52.35 |
| 五类估计器（40–380，w=340） | 128.6 pt | **48.5 pt** | **−80.2 pt** | 210 | `x=210, middle` | 8.5 / 168.8 | 88.7 / 88.7 |
| 求解器（40–350，w=310） | 98.4 pt | **48.5 pt** | **−49.9 pt** | 195 | `x=195, middle` | 8.5 / 108.5 | 58.5 / 58.5 |
| 随机分流（40–180，w=140） | 53.8 pt | 48.0 pt | −5.8 pt | 110 | `x=110, middle` | 8 / 12 | 10 / 10 |
| 结果观测（450–650，w=200） | 455.5 pt | 455.5 pt | 0.0 pt | 550 | `x=550, middle` | 5.5 / 5.5 | 5.9 / 5.9 |

（随机分流/结果观测的偏移小，是因为文字几乎填满盒宽；宽盒的偏移最大，视觉最明显。旧 PNG 的 bbox 与 SVG 居中位置一致，证明 SVG 仍停在被修复前的居中版式。）

**为什么是 P1 而不是 P3**：

- 这是同一类错误（PPTX vs SVG 文本对齐相反），且影响 **20/32** 个文本形状、**49 行** SVG 文字；C2 的目标是消除这类不一致，修复后反而从 12 个扩大到 20 个。
- 宽盒的右留白 108–169 pt，左留白仅 8 pt，版式明显失衡；PNG/答辩版与 SVG/论文版会呈现两种观感。
- 文档 §1.6 已写“**C2 — CLOSED**”“三件套重新全部由同一 SPEC 生成，PPTX 实测几何与 CSV/SVG 一致”，与实测不符；`verify()` 的全局“无 ctr”断言还会把后续同错当成绿灯。

**最小修法（二选一，然后重生成 8 个产物）**：

1. **恢复盒子标签居中（推荐，回到旧版视觉）**：PS1 只对 `$n.textbox` 设 `Alignment=1`（或按 `id in {title,subtitle,tag,footer}`），盒子标签显式 `Alignment=2`（居中）；`verify()` 改为**按元素类型**断言：4 个文本框 `algn="l"`，20 个盒子标签 `algn="ctr"`（或显式居中值），并保留几何 ≤0.6 pt。
2. **若确实要左对齐盒子标签**：把 SVG 的盒子文字改为 `text-anchor="start"` 且 `x = 盒x + 4`（与 PPTX 的 lIns 一致），同步更新文档中的版式说明；`verify()` 增加“PPTX 盒子标签 algn=l ⇔ SVG text-anchor=start”的交叉断言。

无论选哪条，都必须重跑 `scripts/64_h01_method_figures.py`、更新 8 个 sha256、删掉文档里的“C2 CLOSED / 三件套一致”表述，再做第三次独立复核。

**复现命令（只读）**：

```bash
# 1) 旧版 vs 新版段落对齐
./.venv/Scripts/python.exe - <<'PY'
import subprocess, zipfile, io, re
for rev in ("401d4f8^","401d4f8"):
    data=subprocess.run(["git","show",f"{rev}:outputs/figures/h01/v3_h01_three_methods.pptx"],capture_output=True).stdout
    z=zipfile.ZipFile(io.BytesIO(data)); x=z.read("ppt/slides/slide1.xml").decode()
    print(rev, "pPr ctr:", len(re.findall(r'<a:pPr[^>]*algn="ctr"',x)),
          "pPr l:", len(re.findall(r'<a:pPr[^>]*algn="l"',x)))
PY
# 2) SVG 盒子标签仍居中
rg -n 'text-anchor="middle"' outputs/figures/h01/slide1_itt.svg | head
# 3) 新版 PNG 标签左移（Pillow 量 bbox）
#    取 slide1 “处理臂”盒 (230,100)-(400,162)pt → px (479,208)-(833,337)，内部白色像素 bbox
./.venv/Scripts/python.exe - <<'PY'
from PIL import Image
im=Image.open("outputs/figures/h01/slide1_itt.png").convert("RGB"); px=im.load()
xs=[x for y in range(220,325) for x in range(492,820) if px[x,y][0]>215 and px[x,y][1]>215 and px[x,y][2]>215]
print("new text left pt =", round(min(xs)*0.48,1))
PY
```

### P2-1（门禁盲区）：`verify()` 仍未覆盖 18 条 `cxnSp`

`scripts/64_h01_method_figures.py:302-313` 只对 `<p:sp>` 做 `a:off/a:ext` 与 SPEC 的 ≤0.6 pt 断言；`cxnSp` 的端点、`flipH/flipV`、线宽/颜色都不在门禁内。本轮独立实测 18 条连接线最大偏差 **0.05 pt**（无当前缺陷），但**未来改错一条边的端点或 flip，`verify()` 不会响**。按 AGENTS §12.3/§12.7，建议补：
- 逐 `cxnSp` 还原端点并与 CSV `(x1,y1)->(x2,y2)` 比 ≤0.6 pt；
- 反例夹具：在临时副本里改一条边的端点（或翻转 flip），断言 `verify()` 非零退出。

复现：`rg -n "p:sp|cxnSp" scripts/64_h01_method_figures.py`；本轮 18/18 端点对照见 §3.2。

### P2-2（门禁盲区）：文本检查是“全局集合”，不是“逐形状映射”

`verify()` 的文本断言是 `whole in flat`（整页拼接串包含 SPEC 文本），没有把文本绑定到具体形状；如果两个形状互换文字但几何序列仍与 SPEC 一致，几何断言和文本断言都可能过。本轮独立按文本唯一匹配 32/32，**当前产物没有这个问题**；建议在 `verify()` 里按 `(slide, element_id) -> shape` 绑定文本，并造“交换两个标签”的反例。

### P3（记录项）

| 编号 | 问题 | 证据/影响 |
|---|---|---|
| P3-1 | SVG 文本框字形原点仍比 PPTX 左 ~4.2–4.6 pt，页脚基线约高 4.6–5.6 pt | SVG `<text x="40">`；PPTX `lIns=4 pt`，故 PNG 标题 bbox 左 44.6、页脚 44.2；页脚 SVG `y=510.4` vs PNG 文字 bbox y 507.8–517.4（基线约 515）。属矢量/位图文字排版差异，不是盒体几何；标题的纵向几乎重合，页脚差异最大 |
| P3-2 | SVG 圆角固定 `rx=10`，PPTX roundRect 默认 `adj=16667`（半径 0.16667×短边 = 10.3–13.7 pt） | 圆角略紧 0.3–3.7 pt；首轮 C2 的建议之一，未采纳；肉眼几乎不可辨 |
| P3-3 | H01 文档维护时间写 19:55，但文件 mtime 19:53:54、commit 19:54:54 | 时间超前 1 分钟，违反 AGENTS §10“具体到分钟且为实际维护时间”；建议改为实际写入时间，或在 19:55 后再落一版 |
| P3-4 | H01 文档 §1.6 在独立复核前就写“C1 — CLOSED / C2 — CLOSED” | 文档状态行同时写“待独立复审”，自评“CLOSED”与“不得自封通过”的流程口径有张力；建议写“自评闭合，待复审” |
| P3-5 | 文档措辞：“文本框 10/11/11”实际是 `sp` 总数（文本框每页 4 个，共 12 个）；“50 行”是 50 数据行/51 物理行；“无位图依赖”未提 `docProps/thumbnail.jpeg` 43 133 B | 首轮 C6 #7 的建议未采纳；不改变产物结论，但会误导下一次复核 |
| P3-6 | 历史日志仍有旧措辞：`TODO.md:552/557`、`AGENT_HANDOFF.md:47`、`docs/v3_决策与反思日志.md:4705` | 均为历史条目/节标题已标作废/下游已更正；若严格按 §12.4，建议加行内“（已作废，见 19:55 条）” |
| P3-7 | 第 1 页图体下沿 281.8 pt，页 2/3 为 477.6 pt，差 195.8 pt（页高 36%） | C6 #4 仍未处理；不遮挡信息，但三页版式不齐 |
| P3-8 | PPTX 箭头 `tailEnd type="arrow"`（开口箭头）vs SVG `marker` 实心三角 | 既有风格差异，不属几何；首轮未列，记录备查 |
| P3-9 | `docProps/thumbnail.jpeg` 43 133 B；`app.xml` 的 `<Notes>4</Notes>` 与 0 个 `notesSlides` 矛盾 | WPS 模板元数据；不能拿 `Notes` 当页数/备注数证据，缩略图不能当 slide 位图依赖 |

---

## 6. 不支持 / 无法验证的点

1. **未用真 PowerPoint / WPS GUI 打开 PPTX**：只做了 zip/OOXML 解析、PNG 目检、SVG XML 解析；未验证“打开后手动编辑”的交互体验，也未验证 Microsoft PowerPoint 是否提示修复。WPS 生成的 PPTX 在真 PowerPoint 下可能有细微兼容差异（本轮未测）。
2. **未栅格化 SVG**：P1-1 的依据是 SVG 的 `text-anchor="middle"`/`x=盒中心` 与 PNG 像素 bbox 的对照，不是浏览器渲染截图；但 SVG 的锚点语义是显式的，结论不依赖字体度量。
3. **未做 COM 激活实验**：为避免启动 WPS，未在 64 位 PowerShell 里 `New-Object`。注册表显示 CLSID 只在 32 位视图可见，而本机 `powershell` 是 64 位；19:53 重建成功说明实际链路可用，但“64 位 COM 是否跨视图解析”本轮无法断言。换机重建前应按文档 §4 查 `LocalServer32` 的目标位数视图。
4. **未捕获 19:53 运行的 shell RC**：`out/scratch/h01_rebuild4.log` 有 `verify: ...` 与 `written: ...`、无 traceback，但日志 mtime 为 19:51，产物 mtime 为 19:53，二者不完全对齐；文档的“RC=0”是自述，本轮只能确认 `verify()` 的成功输出与产物自洽，不能确认 shell 退出码。
5. **未运行 `scripts/64` / `run_all` / `pytest`**：任何重跑都会改写 8 个产物，违背“只读复核”；因此没有用生成器复现，而是直接解析现有产物。
6. **未确认论文/答辩最终嵌入 PNG 还是 SVG**：P1-1 的实际影响取决于使用哪种格式；两种都用则一定出现两套版式。

---

## 7. 复核限制

- 本报告只对 **commit 401d4f8、mtime 19:53:01–19:53:03 的 8 个产物** 有效；任一文件被重生成/替换后，本报告即失效，需重新复核。
- 几何结论来自 OOXML 的 `a:off/a:ext`（EMU→pt）与 CSV/SVG 数值比对，不是 PowerPoint 的渲染测量；PNG 文字位置来自 Pillow 像素 bbox（选中 5 个盒子 + 标题/页脚），有 ±0.5 pt 的抗锯齿误差，但 P1-1 的 44.6–80.2 pt 偏移远大于该误差。
- 未使用浏览器渲染 SVG，未使用 PowerPoint 的“比较/检查”功能；未对 PPTX 做 OOXML schema 全量校验（只做 `ElementTree` 解析与 `zipfile.testzip`）。
- 本轮只读；未修改 `.git`、未提交、未安装包、未触碰 `outputs/figures/h01/` 的任何字节。

---

## 8. 复现命令速查（只读）

```bash
cd "C:\Users\26382\.qoder-cn\worktrees\app\c509bd\营销数分项目"
export PYTHONUTF8=1

# 8 个 sha256
./.venv/Scripts/python.exe -c "import hashlib,pathlib; [print(hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_size, p.name) for p in sorted(pathlib.Path('outputs/figures/h01').iterdir())]"

# C1：注册表 + app.xml
reg query 'HKCR\PowerPoint.Application\CLSID'
reg query 'HKCR\CLSID\{91493441-5A91-11CF-8700-00AA0060263B}\LocalServer32' /reg:32
reg query 'HKCR\CLSID\{91493441-5A91-11CF-8700-00AA0060263B}' /reg:64
./.venv/Scripts/python.exe -c "import zipfile,re; z=zipfile.ZipFile('outputs/figures/h01/v3_h01_three_methods.pptx'); print(re.search(r'<Application>(.*?)</Application>', z.read('docProps/app.xml').decode()).group(1))"

# C2：形状数 / autofit / 居中
./.venv/Scripts/python.exe -c "import zipfile; z=zipfile.ZipFile('outputs/figures/h01/v3_h01_three_methods.pptx'); [print(i, z.read(f'ppt/slides/slide{i}.xml').decode().count('<p:sp>'), z.read(f'ppt/slides/slide{i}.xml').decode().count('<p:cxnSp>'), z.read(f'ppt/slides/slide{i}.xml').decode().count('spAutoFit')) for i in (1,2,3)]"

# C2：媒体 / PNG
./.venv/Scripts/python.exe -c "import zipfile; z=zipfile.ZipFile('outputs/figures/h01/v3_h01_three_methods.pptx'); print([n for n in z.namelist() if n.startswith('ppt/media/')]); print([n for n in z.namelist() if 'thumbnail' in n])"
./.venv/Scripts/python.exe -c "import struct,pathlib; [print(p.name, struct.unpack('>II', p.read_bytes()[16:24])) for p in sorted(pathlib.Path('outputs/figures/h01').glob('*.png'))]"

# C2：PPTX/CSV/SVG 逐元素对照（本轮 40 行脚本的等价核心）
# 见 §3.2 的方法：ElementTree 读 p:sp/cxnSp 的 a:off/a:ext，按拼接全文唯一匹配 CSV；
# cxnSp 用 flipH/flipV 还原端点；SVG 读 rect/line 与 CSV 比。
# P1-1：旧/新段落对齐
./.venv/Scripts/python.exe - <<'PY'
import subprocess, zipfile, io, re
for rev in ("401d4f8^","401d4f8"):
    d=subprocess.run(["git","show",f"{rev}:outputs/figures/h01/v3_h01_three_methods.pptx"],capture_output=True).stdout
    z=zipfile.ZipFile(io.BytesIO(d))
    for i in (1,2,3):
        x=z.read(f"ppt/slides/slide{i}.xml").decode()
        print(rev, i, "ctr:", len(re.findall(r'<a:pPr[^>]*algn="ctr"',x)), "l:", len(re.findall(r'<a:pPr[^>]*algn="l"',x)))
PY
# P1-1：SVG 盒子标签锚点
rg -n 'text-anchor="middle"' outputs/figures/h01/slide2_observational.svg | head
```

---

## 9. 给实现方的最小处置建议（按顺序）

1. **修 P1-1**：PS1 只对 `title/subtitle/tag/footer` 设 `Alignment=1`；盒子标签恢复居中（或明确改为左对齐并把 SVG 的盒子文字改为 `text-anchor="start"`、`x=盒x+4`）。二选一并写进文档，不要两头都改一半。
2. **加强 `verify()`**：按元素类型断言对齐；补 `cxnSp` 端点/翻转检查；补“交换两个标签”和“改一条边端点”的反例夹具，证明门禁会红。
3. **重跑 `scripts/64`**，更新 8 个 sha256 与 H01 文档；把 §1.6 的“C2 — CLOSED”“三件套一致”改成实测口径（或修好后再写）。
4. **再派独立复核**（第三轮），至少复算：8 指纹、32 段落对齐、20 盒子标签的 PNG/SVG 锚点、18 连接线、PNG 2000×1125。
5. P2-1/P2-2/P3 可同轮处理；P3-3（时间）、P3-4（自评 CLOSED）、P3-5（措辞）建议一并改，避免下一轮再被同一处卡住。
