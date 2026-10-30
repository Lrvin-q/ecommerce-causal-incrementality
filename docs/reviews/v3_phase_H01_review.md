# H01「三方法图」独立评审

维护时间：2026-10-30 18:36（北京时间，Asia/Shanghai）
评审人：独立评审代理（只读手段，未装包、未改 `outputs/figures/h01/` 任何字节、未跑 `run_all` / `pytest`）
评审对象版本：`outputs/figures/h01/*`（mtime 2026-10-30 18:21:46–18:21:47 +0800）

## 0. 结论

**PASS WITH CONDITIONS**（6 条条件，其中 C1、C2 必须在 H01 关闭前修）

产物本身可用：3 页原生 OOXML 形状（`a:blip` 计数 0）、文本全串一致、PNG 规格正确、SVG 与形状/连线几何逐值相等。
但**文档对工具链的陈述与包内元数据矛盾**（实际由 WPS 演示的 COM 生成，不是 Microsoft PowerPoint），
且 **12 个文本框在 PPTX 里被 `spAutoFit` 改过尺寸，CSV/SVG 写的仍是建页前的规格值**，
SVG 的正文对齐又与 PPTX/PNG 相反（左对齐 vs 居中）。这三点使文档"SVG 与 PPTX 同一几何"的说法不成立。

本报告没有 FAIL 项，也没有"读不懂的输入"（见 §6 声明）。

## 1. 效力边界

本报告**只对 2026-10-30 18:23 这一版产物成立**：具体是 `docs/v3_phase_H01_method_figures.md`
在 commit `930afbd`（18:27）追加 sha256 指纹的那一版，对应磁盘上 18:21:46–18:21:47 落盘的 8 个文件。
8 个文件的 sha256 我已独立复算，与文档 §1 指纹表 **8/8 完全一致**（见 §3 表）。任一文件被重新生成、
手工编辑或替换后，本报告即失效，必须复评。

评审开始后 `docs/v3_phase_H01_method_figures.md` 又被改动过一次（mtime 18:27，文件内仍写"维护时间 18:23"），
这一处时间不一致本身列入 C6（§5）。

## 2. 核查项逐条

工具：`./.venv/Scripts/python.exe`（`PYTHONUTF8=1`）、标准库 `zipfile` / `xml.etree` / `hashlib` / `csv`、
`Pillow 13.0.0`（读图裁切，只读）、`winreg`（读注册表）、`reg query`、`Read` 工具目检。

| # | 核查项 | 方法 / 命令 | 结果 |
|---|---|---|---|
| 1 | PPTX 页数 | `zipfile` 列 `ppt/slides/slide*.xml`；`docProps/app.xml` 的 `<Slides>` | **PASS**：3 份 slide XML，`Slides=3`、`HiddenSlides=0`；`ppt/slides/` 下无多余页 |
| 2 | 每页形状数与类型 | `ElementTree` 遍历 `p:spTree` 直接子元素，按 `sp` / `cxnSp` 计数，并统计 `a:prstGeom@prst` | **PASS**：页1 = `sp`10 + `cxnSp`6 = **16**（rect 4 + roundRect 6 + straightConnector1 6）；页2、页3 = `sp`11 + `cxnSp`6 = **17**（rect 4 + roundRect 7 + connector 6）。与文档 16/17/17 一致 |
| 3 | 原生形状（非截图）证据 | 全 slide 内 `p:pic` 与 `a:blip` 计数；`ppt/media/` 名单；整包位图名单 | **PASS（强于文档的证据）**：`p:pic`=0、`a:blip`=0；`ppt/media/` 为空。**但**整包仍有 `docProps/thumbnail.jpeg`（42 340 B，首页缩略图，无任何 slide 引用）。文档"无位图依赖"的结论成立，"媒体目录为空"是较窄的证据，建议改用 blip 计数 |
| 4 | 文本落地（逐页全串比对） | 拼接每页全部 `<a:t>`（`&#10;` 解成换行），去空白后与 `SPEC` 每个文本节点**整串**比对，而非 12 字符前缀 | **PASS**：32 个文本元素（页1 10、页2 11、页3 11）全部整串命中；页1 76 个 run、页2 54 个、页3 79 个。无缺失节点、无串页（每页文本集合与 SPEC 该页节点一一对应） |
| 5 | 关键节点文本在位 | 逐条读拼接串 | **PASS**：页1「随机分流 / 处理臂 发 10 元券 / 对照臂 不发券 / 结果观测 7 天支付窗口 30 天退款窗口 退款单留在样本 / 主指标 净贡献利润 ITT E[Π(1) − Π(0)] / 校准与护栏 AA 1000 次 + 退款率 非劣效检验」；页2「历史观测数据（五表 / SQL）/ 六字段白名单 / 五类估计器 常数 / T / S / 因果森林 / DR / 验证集选模 测试集不参与学习 / 条件效应 τ̂(X) / 交叉拟合 OPE IPW / DR / SNIPS / 冻结帧审计」；页3「τ̂(X) + 成本模型 / 预算档 0.04–1.00 元 / 人 / 求解器 贪心 / DP / MILP / LP / 局部交换 / 名单 每人至多 1 张券 / 支出与利润 预期 / 实际 / 硬预算三口径 / 不确定度 固定 bootstrap 1000 重训 200 / 真值审计 每 rep 20 万随机验证」；三页页脚均为「合成数据 / 已知 DGP · 形状为 PowerPoint 原生元素（可编辑，非截图）· 口径与论文第 2–3 章一致」 |
| 6 | PNG 规格 | 只读 IHDR（偏移 16–24）+ `file` | **PASS**：3 张均 2000×1125、bit depth 8、color type 6（RGBA）、PNG 签名正确；字节 164 576 / 178 801 / 182 982，与文档一致 |
| 7 | PNG 目检 | `Read` 直读三张图 + Pillow 局部放大（标题 τ̂ 6×，盒内 τ̂ 3–6×） | **PASS（含 1 条可读性瑕疵）**：中文无乱码、无缺字（无豆腐块）、无文字溢出盒子、页脚完整、箭头均落在目标盒边。瑕疵：**13 pt 下 `τ̂`（U+03C4 + U+0302）的帽子偏向 τ 左上且倾斜，观感更像尖音符**（页2「条件效应 τ̂(X)」、页3「τ̂(X) + 成本模型」）；24 pt 标题「从 τ̂ 到」帽子位置正常。**说明**：2× 放大时我一度疑心标题的帽子丢失，6× 复查确认存在——此处不记为缺陷，仅记录以防误判 |
| 8 | SVG XML 合法性 | `xml.etree.ElementTree.fromstring` 解析 3 份 | **PASS**：3 份均可解析；`width=960 height=540 viewBox="0 0 960 540"`；无 BOM；行尾 CRLF（35/35/38 个），对 SVG 消费方无影响 |
| 9 | SVG 节点数 vs PPTX 形状数 | 按类型计数 | **PASS（需按映射读）**：页1 rect 7 = 底板 1 + 形状 6，line 6，text 20；页2 rect 8 = 底板 1 + 形状 7，line 6，text 19；页3 rect 8 = 底板 1 + 形状 7，line 6，text 22。`rect + line = 12/13/13` 只对应 PPTX 的「形状 + 连线」；PPTX 的 4 个文本框在 SVG 里是 `<text>` 而无 `<rect>`（故 text 数 20/19/22 = 每条文本行一个 `<text>`，含 4 个文本框的 1 行标题/副标/标签/页脚）。三页 `rect + line + 文本框` 均与 PPTX 的 16/17/17 对齐 |
| 10 | SVG 与 CSV 几何 | 逐元素比对 rect/line 数值 | **PASS**：6/6、7/6、7/6 的 rect/line 坐标与 CSV **完全相等（0 差）**，无舍入误差 |
| 11 | SVG 与 PPTX 是否同一几何 | 从 slide XML 提 `a:off`/`a:ext`（EMU ÷ 12700 转 pt）与 CSV/SVG 对照 | **CONDITION（C2）**：**20 个形状 + 18 条连线逐值一致**（差 < 0.6 pt，实为 0）；但 **12 个文本框全部不同源**——`title` y 16→12.4、h 34→33.0；`subtitle` y 52→55.0、h 24→19.8；`tag` y 78→82.2、h 22→17.3；`footer` y 500→505.4、h 26→14.9（三页同样）。原因是文本框带 `<a:spAutoFit/>`，落盘时按文本实际高度重算了框体；生成器把建页前的 SPEC 值直接写进 CSV/SVG，没有回读 as-built。**另有对齐差异**：PPTX 四个文本框 `algn="ctr"`，SVG 的这四行 `<text>` 无 `text-anchor`（即左对齐，x=40 起排），标题在矢量版里会整体左移约 260 pt |
| 12 | 元素清单 | 逐行读 `v3_h01_elements.csv` | **PASS（含口径说明）**：51 个物理行 = 表头 1 + 数据 **50**；12 列；UTF-8-sig（BOM `EF BB BF`）、CRLF；页1 16 行、页2 17 行、页3 17 行；`kind` 分布 shape5 20 / connector 18 / textbox 12。文档"50 行"若指物理行会少算 1 行，指数据行则正确——建议文档写"50 数据行（文件 51 行）" |
| 13 | 清单与 PPTX 坐标吻合 | 按文本匹配每个元素，比较 x/y/w/h | **PASS（形状与连线）/ CONDITION（文本框）**：18 条连线端点（含 `flipH`/`flipV` 还原方向）全部命中，误差 < 0.6 pt；20 个形状的 x/y/w/h 全等；12 个文本框见第 11 项 |
| 14 | CSV 可被 Excel 打开 | 读首 3 字节与行尾 | **PASS**：UTF-8-sig + CRLF，Excel 直接打开不乱码；文本内换行已转成 ` / `，不会撑破单元格 |
| 15 | 文档声称的 5 个数字独立复算 | 见 §3 | **PASS 4 项 / 1 项需改口径**（"50 行"、"无位图"两处在措辞上偏窄，已在 §3 注明） |
| 16 | 与论文口径对照 | `grep` `paper/v3/body/02_method.md`、`03_results.md` | **CONDITION**：8 处一致、5 处需改（C3–C5），逐条见 §4 |
| 17 | 产物入库与指纹 | `git check-ignore`、`git log`、独立 `hashlib.sha256` | **PASS**：8 个文件均未被 `.gitignore` 排除；`930afbd` 记录的 8 条 sha256 与本地复算 8/8 相同 |

## 3. 复算到的关键数字（不采信文档自检输出）

| 项 | 文档声称 | 我的独立复算 | 判定 |
|---|---|---|---|
| slide XML 页数 | 3 | 3（且 `HiddenSlides=0`） | 一致 |
| 每页形状数 | 16 / 17 / 17 | 16（sp 10 + cxnSp 6）/ 17（11+6）/ 17（11+6） | 一致 |
| PNG 尺寸 | 2000×1125 | 3 张均 2000×1125（IHDR 直读） | 一致 |
| 元素清单行数 | 50 行 | 50 数据行 / 51 物理行 | 口径需注明 |
| 无位图媒体 | `ppt/media/` 为空 | `ppt/media/` 空 且 `a:blip`=0；但 `docProps/thumbnail.jpeg` = 42 340 B | 结论成立，措辞偏窄 |
| 文件字节 | pptx 102 345；PNG 164 576 / 178 801 / 182 982 | 完全相同 | 一致 |
| slide 尺寸 | 未提 | `sldSz` = 12 192 000 × 6 858 000 EMU = 960 × 540 pt | 与 SVG/CSV 同坐标系 |
| SVG 节点 | 未提 | rect（含底板）7/8/8、line 6/6/6、text 20/19/22 | 见第 9 项 |
| 文本 run 数 | 未提 | 76 / 54 / 79 | — |
| 第 1 页留白 | "下半部留白偏多，属可接受" | 图体下沿 **281.8 pt**，页2/3 为 **477.6 pt**；差 195.8 pt（页高 36%） | 属实，见 C6 |
| 形状最小/最大边界 | 未提 | x ∈ [40, 920]、y ∈ [12.4, 520.3]，无越界、无重叠遮挡 | — |
| 圆角 | 未提 | PPTX roundRect 的 `<a:avLst/>` 为空 → 默认 adj 16667，半径 = 0.16667×短边（10.3–13.7 pt）；SVG 固定 `rx="10"` | 矢量版圆角略紧 0.3–3.7 pt，肉眼几乎不可辨 |

## 4. 与论文口径的逐条对照

一致（PASS）：

1. `E[Π(1) − Π(0)]`：正文 02_method L55–58 用 $\Pi$ 与 $\tau=E[\Pi(1)-\Pi(0)]$，符号相同（`grep "Π"` 为 0 是因为正文写 LaTeX 的 `\Pi`）。
2. 「五类估计器 常数 / T / S / 因果森林 / DR」：02_method L225、L273 的五类一致。
3. 「六字段白名单」：02_method L34、L186 一致。
4. 「验证集选模 / 测试集不参与学习」：02_method L235、L275「验证队列选模，测试队列与审计区只报不选」方向一致（用词"测试集"vs"测试队列"可接受）。
5. 「求解器 贪心 / DP / MILP / LP / 局部交换」：02_method L350–363 的五个求解器逐一对上。
6. 「预算档 0.04–1.00 元 / 人」：02_method L397 八档 0.04–1.00 元/人。
7. 「固定 bootstrap 1000 / 重训 bootstrap 200」：03_results L995（200 次再训练 = 4 格 × 50 b）、L509/L1136（固定策略 1000 次）。**数字对**，但"200"是总数不是每格。
8. 「AA 1000 次 + 退款率非劣效」「每 rep 20 万新用户三臂 ITT」：03_results L15、L129 一致。

需改（均见 §5 条件）：

9. 「预期 / 实际 / 硬预算三口径」与正文表 3-14 的三口径（**期望 / 缓冲 / 面值**）不同名（C3）。
10. 「超支概率双分母」正文无此语，正文用「超支名单占比」，表 3-13 未列两个分母（C6）。
11. 方法一画两臂，正文 F02 是三臂（不发券 / 同预算随机 / 定向，03_results L129–139）（C4）。
12. 「交叉拟合 OPE」无"名单 × 预算档"输入，正文 F01 的 OPE 建在 4 策略 × 8 档名单上（表 3-21）（C5）。
13. 「真值审计 每 rep 20 万随机验证」：20 万随机三臂是 F02 的复核手段，F01 冻结帧审计是 **6 万人、R=0**（03_results L1246）（C5）。
14. 「净贡献利润 ITT」vs 正文「净增量贡献利润」；τ 的下标：正文目标量 τ_Π(X) / τ̂_Π(X)，图用 τ̂(X)（C6）。

## 5. 条件清单

### C1（必须修）文档把生成器说成 Microsoft PowerPoint，实际是 WPS 演示

- 证据 1（包内元数据）：`ppt/v3_h01_three_methods.pptx` → `docProps/app.xml`：`<Application>WPS 演示</Application>`、`<PresentationFormat>宽屏</PresentationFormat>`。
- 证据 2（注册表，`winreg` 32 位视图只读查询）：`HKCR\PowerPoint.Application\CLSID` = `{91493441-5A91-11CF-8700-00AA0060263B}`，该 CLSID 的 `LocalServer32` = `C:\Users\26382\AppData\Local\Kingsoft\WPSOFF~1\1210~1.296\office6\wpp.exe /Automation`（WPS 演示主程序）。
- 结论：`New-Object -ComObject PowerPoint.Application` 起的是 **WPS 的兼容 COM 服务**，不是 Microsoft PowerPoint。文档 §2「18:18 实测本机有 PowerPoint COM」、§4「生成依赖本机 PowerPoint（COM）」、页脚「形状为 PowerPoint 原生元素」都需要改口径。
- 影响面：产物仍是 OOXML 原生形状（`a:blip`=0，可编辑，"非截图"成立）；但**换到真 PowerPoint 时字体度量与 `spAutoFit` 结果会变**，C2 里的文本框偏移会换一套数值，必须重跑并复核，不能只声明"COM 可用"。
- 建议改法：§2/§4 与页脚改为「OOXML 原生形状；本次由 WPS 演示 12.x 的 PowerPoint 兼容 COM 生成」，并把"换机器需重新确认 COM 可用性"改成"确认该 ProgID 实际指向哪个应用（`reg query HKCR\PowerPoint.Application\CLSID`）"。

### C2（必须修）SVG/CSV 与 PPTX 的文本框不同源，且对齐相反

- 数字：12 个文本框 y 偏 +3.0～+5.4 pt、h 偏 −1.0～−11.1 pt（页脚 h 26→14.9）；PPTX `algn="ctr"`，SVG 无 `text-anchor`（左对齐）。
- 后果：若论文/答辩用 SVG（矢量）而评审/定稿看 PNG（位图），标题的横向位置会差约 260 pt，版式观感两台不一致；"同一几何"这句话在 12/50 个元素上不成立。
- 建议改法（二选一或并用）：
  1. SVG 的四个文本块写 `text-anchor="middle"` 且 `x = 480`（居中带仍是 40–920），与 PPTX 的 `algn="ctr"` 对齐；
  2. 生成器在建完 PPTX 后**回读** `ppt/slides/slide*.xml` 的 `a:off`/`a:ext`，用 as-built 坐标写 CSV 与 SVG（顺带把 `rx` 从固定 10 改成按 0.16667×短边算）。
- 门禁（§12.3 只准加强）：`verify()` 现在只比 12 字符前缀，建议加两条断言——文本**整串**相等；回读 as-built 坐标与 CSV 逐元素差 ≤ 0.6 pt。两条都必须能在旧产物上复现出红（C2 的 12 个文本框正好是天然反例夹具）。

### C3（应修）「三口径」两套命名

图上「预期 / 实际 / 硬预算三口径」沿用 GOAL/E02 的措辞，但正文表 3-14 的三口径是**期望 / 缓冲 / 面值**（expected / buffered / worst_case_face）。同一篇材料里两套"三口径"会被答辩追问。
建议：图上写「期望 / 缓冲 / 面值（三口径）」，或在括号里注「即正文 3.4 三口径」。

### C4（应修）方法一的两臂 vs 正文的三臂

正文 F02（03_results L129–139）是「不发券 / 同预算随机 / 定向策略」三臂 ITT，页 1 的 tag 也写了「三臂 ITT」，但图上只有处理臂/对照臂。
建议：补第三臂（同预算随机），或把 tag 改成「三臂（图中示意为两臂）」。当前形态不算错，但会被读成"图与引用自相矛盾"。

### C5（应修）方法二的 OPE 输入与"真值审计"的帧

- OPE 节点接在 τ̂(X) 之后，没有"名单 × 预算档"输入；正文 F01 的 OPE 是对 4 策略 × 8 档名单做的（表 3-21）。建议补一个小节点或一条来自第 3 页的箭头。
- 「真值审计 每 rep 20 万随机验证」把两件事并成一句：F02 是每 rep 20 万新用户随机三臂复核，F01 的冻结帧审计是 6 万人（R=0）。建议改成「真值审计（F01 6 万帧逐档对账；F02 20 万随机三臂复核）」。

### C6（记录项，合并处理）

1. 「净贡献利润 ITT」建议统一为正文的「净增量贡献利润」；「超支概率双分母」正文无对应语（正文是"超支名单占比"，且表 3-13 未列两个分母），要么改词要么在正文补一句"两个分母都报"。
2. τ̂ 在下标上丢了 Π：正文目标量是 τ_Π(X) / τ̂_Π(X)。若图面空间允许，写成 τ̂_Π(X) 更贴正文；若不改，图注里说明一句。
3. 13 pt 的 `τ̂`（U+0302 组合符）观感接近尖音符，建议这两处改成「τ̂(X)」用单独字号的文本块或改写成 `τhat(X)` 之类不易误读的记法（若保留组字符号，至少在答辩时口头澄清）。
4. 第 1 页图体下沿 281.8 pt，页 2/3 为 477.6 pt，差 195.8 pt（页高 36%），三页版式不齐；文档已自认"留白偏多"。改成与其他两页等高（下移或加一行注释）成本很低。
5. 页 3 的 A→B 箭头（τ̂+成本模型 → 预算档）把"预算档"画成了模型的下游；正文 L397 的八档是**设计网格**，不是 τ̂ 的输出。同一处 A 右下角的斜箭头起点落在 A、B 之间的空隙，读作 A→求解器或 B→求解器都说得通。建议：预算档与 τ̂ 并列为求解器的两个输入（两条箭头汇到求解器）。
6. `docs/v3_phase_H01_method_figures.md` 文件内写"维护时间 2026-10-30 18:23"，但 mtime 为 18:27（commit `930afbd` 追加 sha256 段）。按 AGENTS §10 应另记 18:27；不能用一个更早的时间覆盖后来的改动。
7. 文档"50 行"建议写作"50 数据行（文件 51 行）"；"无位图依赖"建议写成"slide 内 0 个 `a:blip`；整包仅 `docProps/thumbnail.jpeg` 一张首页缩略图"。

## 6. 「读不懂的输入」声明（§12.7）

本次解析的全部输入都读懂了，没有跳过任何记录：

- PPTX：116 个 zip 条目逐一列出，未识别项只有 `ppt/tags/tag1..62.xml`，其内容为 PowerPoint/WPS 的形状标签部件（526/631/697 B），与本次核查无关，不构成"读不懂"。
- `v3_h01_elements.csv`：`kind` 列出现 `shape5`，是 COM 的自动形状类型码（`msoShapeRoundedRectangle` = 5），已按映射读作圆角矩形；`connector` 行的 `text_or_endpoints` 是 `(x1,y1)->(x2,y2)` 文本，已按正则解析。两者都不属于"读不懂"，但建议 CSV 里把 `shape5` 写成 `roundRect(mso 5)`，省掉下一次评审的映射猜测。
- `app.xml` 的 `<Notes>4</Notes>` 与包内 `notesSlides` 为 0 相矛盾：这是 WPS 写死的模板计数，我按"无备注页"处理，不作为缺陷，只记录该字段不可作为页数/备注数证据。
- `docProps/core.xml` 的 `created 2019-06-19`、`revision 157` 来自 WPS 默认模板，与本次生成时间无关，不能当"编辑历史"读。

## 7. 复核这份报告的最小代价

```bash
# 8 个指纹（应与 §3 表一致）
./.venv/Scripts/python.exe -c "import hashlib,pathlib;[print(hashlib.sha256(p.read_bytes()).hexdigest(),p.name) for p in sorted(pathlib.Path('outputs/figures/h01').iterdir())]"
# 形状数 / blip 数
./.venv/Scripts/python.exe -c "import zipfile,re;z=zipfile.ZipFile('outputs/figures/h01/v3_h01_three_methods.pptx');[print(i,z.read(f'ppt/slides/slide{i}.xml').decode().count('<p:sp>'),z.read(f'ppt/slides/slide{i}.xml').decode().count('<p:cxnSp>'),z.read(f'ppt/slides/slide{i}.xml').decode().count('<a:blip')) for i in (1,2,3)]"
# C1 证据
reg query "HKCR\PowerPoint.Application\CLSID"
```

## 8. 建议的处置顺序

1. 修 C1（文档 ×3 处 + 页脚文案）与 C2（SVG 对齐 + 回读 as-built + 两条新断言），重跑 `scripts/64_h01_method_figures.py`，重出 8 个文件并更新指纹。
2. 修 C3/C4/C5 的措辞与节点（同样走重跑，不手改 PPTX——文档 §4 自己也这么要求）。
3. C6 随同一次重跑一起处理；第 1 页留白与页 3 箭头汇合点可以一并在 SPEC 里调坐标。
4. 重跑后**重新评审**：本报告的效力只到 2026-10-30 18:23 这一版。
