# H05 来源底表 —— 12 篇文献与"支持 / 不支持"范围

> **合成数据 / 已知 DGP**。本表是 H05 验收（12 篇来源 + 支持范围 + 合成属性/局限/失败条件）
> 的工作底表；最终长稿的引用必须逐条回指本表编号。维护时间：**2026-10-30 00:16（北京时间）**
> （前版 00:05；本节按二评 `docs/reviews/v3_phase_H05_review.md` 的 P2-1 与 P3-1…P3-6 修订）。
>
> 纪律：每条只写它能支持的方法学结论；**任何来源都不支持"本项目合成 DGP 结论可外推到真实业务"**。
> 标注 `Crossref ✓` 的元数据已在线核验；标 `canonical` 的含义是**未在线核验**、按通行版本记录
> （P3-3：旧版把它写成"领域内标准引用"，容易被读成"已核"，而 S1/S2 两条错正是在标 canonical 的行里）。

| # | 来源 | 支持什么（本项目中的用法） | **不支持**什么（越界即违规） | 核验 |
|---|---|---|---|---|
| S1 | Künzel S R, Sekhon J S, Bickel P J, Yu B. Metalearners for estimating heterogeneous treatment effects using machine learning. *PNAS*, 2019, 116(10): 4156–4165. | S/T/X 学习器的定义与适用条件；本项目 CATE 模型族的来源 | 不支持"某个学习器在真实营销中更优"；论文的多臂实验设定与本项目单臂二值处理不同 | **Crossref ✓**（2026-10-30 00:03 实测 `10.1073/pnas.1804597116`：volume 116 / **issue 10** / 4156-4165；旧版写 116(11) 是错的，评审 P1-2） |
| S2 | Wager S, Athey S. Estimation and inference of heterogeneous treatment effects using random forests. *JASA*, 2018, 113(523): 1228–1242. | `causal_forest` 的渐近正态性与诚实分箱机制；AIPW 型得分 | 不支持把森林的点估计当无偏个体效应；不支持在合成 DGP 外推 | **Crossref ✓**（2026-10-30 00:03 实测 `10.1080/01621459.2017.1319839`：113(523) **1228-1242**；旧版 1223–1232 是错的，评审 P1-1） |
| S3 | Athey S, Tibshirani J, Wager S. Generalized random forests. *Annals of Statistics*, 2019, 47(2): 1148–1178. | GRF 框架（局部矩估计、诚实性）；causal_forest 的实现基础 | 不支持高维/弱重叠下的有效性（论文有明确正则条件） | canonical |
| S4 | Nie X, Wager S. Quasi-oracle estimation of heterogeneous treatment effects. *Biometrika*, 2021, 108(2): 299–319. | R-learner（`r_learner`）的目标函数与准 oracle 性质 | 不支持倾向得分或结局模型严重误设时仍有效（需交叉拟合与 nuisance 质量） | canonical |
| S5 | Kennedy E H. Towards optimal doubly robust estimation of heterogeneous causal effects. *Electronic Journal of Statistics*, 2023, 17(2): 3008–3049. | DR-learner（`dr_learner`）的伪结局构造与一阶最优性 | 不支持小样本/重尾伪结局下的稳定性；不支持与本项目不同的损失 | **Crossref ✓**（2026-10-29 11:31 实测 `api.crossref.org` 精确命中：DOI `10.1214/23-EJS2157`，volume 17 / issue 2 / pages 3008-3049） |
| S6 | Chernozhukov V, Chetverikov D, Demirer M, Duflo E, Hansen C, Newey W, Robins J. Double/debiased machine learning for treatment and structural parameters. *The Econometrics Journal*, 2018, 21(1): C1–C68. | 交叉拟合 + Neyman 正交的 DML 框架；本项目 nuisance 估计的纪律来源 | 不支持"任意 ML 模型 + 任意样本量都近似无偏"；正则条件不满足时失效 | canonical |
| S7 | Dudík M, Langford J, Li L. Doubly robust policy evaluation and learning. *ICML*, 2011: 1097–1104. | 策略价值的 DR 估计（本项目 DR 估值口径的来源） | 不支持重叠性失败时的策略比较；不支持把 off-policy 估值当在线 A/B 结论 | canonical；**页码 1097–1104 未能在线核验**（ICML 2011 官方索引不带页码、PDF 内无页码；评审 P3-4） |
| S8 | Athey S, Wager S. Policy learning with observational data. *Econometrica*, 2021, 89(1): 133–161. | 观察性数据下的策略学习与 regret 界；策略评估的目标量定义 | 不支持无重叠/强混淆下的策略最优性；不支持预算约束场景（**本项目贪心与背包为自建规则，不引用外部来源**，评审 P2-2） | canonical |
| S9 | Kitagawa T, Tetenov A. Who should be treated? Empirical welfare maximization methods for treatment choice. *Econometrica*, 2018, 86(2): 591–616. | 经验福利最大化（EWM）与策略 regret 的统计框架 | 不支持连续处理/预算约束扩展；不支持本项目特定 DGP 的结论 | canonical |
| S10 | Holm S. A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 1979, 6(2): 65–70. | F02 单侧 Holm 两比较的多重性控制 | **在任意依赖结构下都控制 FWER（free step-down），但正相依时偏保守、损失功效**；不支持把 p 值当效应大小（评审 P2-3：旧版写成"不支持任意依赖"，与事实相反） | canonical；**未能在线核验**（Crossref 无 1979 记录、JSTOR 反爬；评审 P3-4） |
| S11 | Kohavi R, Tang D, Xu Y. *Trustworthy Online Controlled Experiments: A Practical Guide to A/B Testing*. Cambridge University Press, 2020. | AA 校准、样本比例失配、护栏指标、实验平台口径（E/G01 的实践依据） | 不支持把 AA 通过当作策略有效；不支持合成实验替代真实流量 | canonical |
| S12 | Curth A, Svensson D, Weatherall J, van der Schaar M. Really doing great at estimating CATE? A critical look at ML benchmarking practices in treatment effect estimation. *NeurIPS 2021 Datasets and Benchmarks Track (round 2)*. | 合成/半合成 CATE 基准的评价陷阱（本项目"合成 DGP→不外推"的方法学依据） | 不支持对任何具体估计器优劣的结论；不支持替代真实数据验证 | **官方 proceedings ✓（2026-10-29 11:54）**：官方摘要页 `datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/2a79ea27c279e471f4d180b08d62b00a-Abstract-round2.html` 与 PDF `…/file/…-Paper-round2.pdf` 均可达；题名/venue（"Proceedings of the NeurIPS Track on Datasets and Benchmarks 1"，D&B 2021）与条目一致，四位作者姓名一致——**给名以官方 `Jim` 为准**（bib 原写 `James` 已改，评审 P2-5；官方 `citation_author` 为 `Weatherall, Jim`）。该轨道**无 DOI**（同日 11:36 Crossref 精确查无记录），故不标 Crossref ✓、只标 official ✓ |

## 使用规则（写进长稿时必须遵守）

1. **支持范围是上界**：引用只能落在"支持什么"列；跨列使用视为越界。
2. **合成属性必须就近出现**：凡引用本项目数字，所在小节（表注、章首或章末）必须出现
   "合成数据 / 已知 DGP"与失效条件。**P2-4 修订**：旧版写"同段"，实现是"逐节/逐注"——
   按字面机检结果章 82 个含 `[C编号]` 的段落只有 3 个同段出现，两级口径必须选一个；
   选"小节级"，因为它比逐段重复更可读：结果章 11 节（3.1–3.11）按该口径 11/11 达标，
   其中仅 3.6 在节首段即出现限定词（见 P2-4；节数口径由二评 P3-1 更正，旧版"12 节里 11 节"是把它数错了）。
3. **Tier1/Tier2 不并列**：S2/S3 的推断性质只适用于 Tier1 的 R=250/500 口径；Tier2（R=30）只能判方向，
   引用 S12 说明其精度局限。
4. **AA 不等于有效**：引用 S11 时不得推出"策略有效"或"可上线"。
5. **数字溯源**：长稿里每个数字回指 `outputs/tables/` 或 `outputs/evidence/` 的具体文件（H04 claim 注册表）。

## 待办（H05 收尾前）

- [x] 核验 S5、S12 的卷期/页码。**11:36**：S5 精确命中（DOI `10.1214/23-EJS2157`，
  17(2): 3008–3049）→ **Crossref ✓**。**11:54**：S12 拿到官方 proceedings 直链与 PDF
  （hash `2a79ea27…b00a`，round 2），题名/作者/venue 与条目一字不差 → **官方 proceedings ✓**；
  该轨道无 DOI，长稿引用**不得**写"Crossref 已核"，只能写官方 proceedings 链接；
- [x] 逐条检查长稿引用编号与本表一致（12 篇，不多不少）。**12:20 机制就位**：`paper/v3/refs.bib`
  恰 12 条（`s1`–`s12`，字段逐条照抄本表，未核验的 DOI 一律不写），biblatex `style=numeric,
  sorting=none` + biber；探针稿 4 处引用印成 `[1]`–`[12]` 且顺序=首次引用顺序，参考文献独立成页、
  标题"参考文献"。**10-30 00:06 关闭**：44 号实测 `bib=12 引用键=12 引用次数=35 bbl=12` EXIT=0；
  独立评审 §0 只读复跑逐字一致，并在 §2 给出 **30 处标记 / 35 个键**的逐点支持范围审计
  （29 在范围内、1 处术语借用、2 处用途记录过度——后两类已改）；机器可读字段见下一节，
  44 号自本轮起逐字段比对（评审 P1-4）；
- [x] 检查"无面额外推"。**10-30 00:06 关闭**：独立评审 §3.3 做了关键词机检 + 逐条定性——
  `真实业务` 13 次（12 处限定/否定 + 1 处方法学观察）、`上线` 2 次（均否定）、`推广`/`普适`/`可上线` 0 次、
  `外推` 10 次（全部否定）、`必然` 3 次（2 处 DGP 内数学陈述 + 1 处否定）、`证明` 13 次（10 否定 + 2 门禁自检 + 1 目标句）。
  **发现 3 处肯定式边界表述并已改**（P3-2：`01_intro.md:23`"必然低估"、`:45`"任何结论"、`04_conclusion.md:296`"方法可以迁移"）。
- [x] 二评 P2-1…P3-6 收口。**10-30 00:16**：二评（独立代理，`docs/reviews/v3_phase_H05_review.md`，
  00:13 快照）判 PASS WITH CONDITIONS，唯一实质条件是 P2-1（三处"附录"悬空、与 `03_results.md:1128` 矛盾）。
  本轮把三处改为"G03 正式报告"（`01_intro.md:84`、`04_conclusion.md:198`、`:279`），
  并处理 P3-3（删去 bib 里会印进 PDF 的 `note = {该轨道无 DOI}`）、P3-4（`02_method.md:76`
  改为"本项目的审计口径下"）、P3-5（`03_results.md:1128` 句末补 `[@s12]`）、
  P3-1/P3-2（本节两处计数）、P3-6（上节门禁边界）。**待**：重建后跑 44/52 并请小范围复核。

## 机器可读字段（44 号逐字段比对用；改这里必须同步改上面的表，反之亦然）

> `pages` 用 ASCII 连字符；`-` 表示该字段不存在或不适用（比对时跳过）。字段值由独立评审
> 2026-10-30 00:00–00:05 逐条实测（Crossref / PubMed / OpenAlex / NeurIPS D&B / ICML 官方索引），
> S1/S2 由主负责同日 00:03 二次复核；S7 页码、S10 全条未能在线核验，按通行版本记录。

| key | year | volume | number | pages | 核验入口 |
|---|---|---|---|---|---|
| s1 | 2019 | 116 | 10 | 4156-4165 | Crossref 10.1073/pnas.1804597116 |
| s2 | 2018 | 113 | 523 | 1228-1242 | Crossref 10.1080/01621459.2017.1319839 |
| s3 | 2019 | 47 | 2 | 1148-1178 | Crossref 10.1214/18-AOS1709 |
| s4 | 2021 | 108 | 2 | 299-319 | Crossref 10.1093/biomet/asaa076 |
| s5 | 2023 | 17 | 2 | 3008-3049 | Crossref 10.1214/23-EJS2157 |
| s6 | 2018 | 21 | 1 | C1-C68 | Crossref 10.1111/ectj.12097 |
| s7 | 2011 | - | - | 1097-1104 | ICML 2011 官方索引（不带页码，未能核） |
| s8 | 2021 | 89 | 1 | 133-161 | Crossref 10.3982/ecta15732 |
| s9 | 2018 | 86 | 2 | 591-616 | Crossref 10.3982/ecta13288 |
| s10 | 1979 | 6 | 2 | 65-70 | 未能在线核验（Crossref 无记录、JSTOR 反爬） |
| s11 | 2020 | - | - | - | Crossref 10.1017/9781108653985（专著） |
| s12 | 2021 | - | - | - | NeurIPS D&B 官方 proceedings 页（无 DOI、无卷期页） |

**门禁边界（P3-6）**：44 号只比对 `year`/`volume`/`number`/`pages` 与标题子串，
不校验作者名与 DOI——S12 的 `James→Jim` 这类错它拦不住，需靠人眼或本表。要扩到作者，
就得先给上表加 `author` 列并同步 bib，属于下一轮；本轮如实记为边界，不冒充全覆盖。

**复现命令**（P3-4；任一 DOI 打开后看 `volume` / `issue` / `page` 三字段）：

```bash
curl -s https://api.crossref.org/works/10.1073/pnas.1804597116 | jq '.message | {volume,issue,page}'
curl -s https://api.crossref.org/works/10.1080/01621459.2017.1319839 | jq '.message | {volume,issue,page}'
# S12：官方摘要页 datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/2a79ea27c279e471f4d180b08d62b00a-Abstract-round2.html
```
