# H05 来源底表 —— 12 篇文献与"支持 / 不支持"范围

> **合成数据 / 已知 DGP**。本表是 H05 验收（12 篇来源 + 支持范围 + 合成属性/局限/失败条件）
> 的工作底表；最终长稿的引用必须逐条回指本表编号。维护时间：2026-10-29 11:36（北京时间）。
>
> 纪律：每条只写它能支持的方法学结论；**任何来源都不支持"本项目合成 DGP 结论可外推到真实业务"**。
> 标注 `Crossref ✓` 的元数据已在线核验；标 `canonical` 的是领域内标准引用，元数据按通行版本记录。

| # | 来源 | 支持什么（本项目中的用法） | **不支持**什么（越界即违规） | 核验 |
|---|---|---|---|---|
| S1 | Künzel S R, Sekhon J S, Bickel P J, Yu B. Metalearners for estimating heterogeneous treatment effects using machine learning. *PNAS*, 2019, 116(11): 4156–4165. | S/T/X 学习器的定义与适用条件；本项目 CATE 模型族的来源 | 不支持"某个学习器在真实营销中更优"；论文的多臂实验设定与本项目单臂二值处理不同 | canonical |
| S2 | Wager S, Athey S. Estimation and inference of heterogeneous treatment effects using random forests. *JASA*, 2018, 113(523): 1223–1232. | `causal_forest` 的渐近正态性与诚实分箱机制；AIPW 型得分 | 不支持把森林的点估计当无偏个体效应；不支持在合成 DGP 外推 | canonical |
| S3 | Athey S, Tibshirani J, Wager S. Generalized random forests. *Annals of Statistics*, 2019, 47(2): 1148–1178. | GRF 框架（局部矩估计、诚实性）；causal_forest 的实现基础 | 不支持高维/弱重叠下的有效性（论文有明确正则条件） | canonical |
| S4 | Nie X, Wager S. Quasi-oracle estimation of heterogeneous treatment effects. *Biometrika*, 2021, 108(2): 299–319. | R-learner（`r_learner`）的目标函数与准 oracle 性质 | 不支持倾向得分或结局模型严重误设时仍有效（需交叉拟合与 nuisance 质量） | canonical |
| S5 | Kennedy E H. Towards optimal doubly robust estimation of heterogeneous causal effects. *Electronic Journal of Statistics*, 2023, 17(2): 3008–3049. | DR-learner（`dr_learner`）的伪结局构造与一阶最优性 | 不支持小样本/重尾伪结局下的稳定性；不支持与本项目不同的损失 | **Crossref ✓**（2026-10-29 11:31 实测 `api.crossref.org` 精确命中：DOI `10.1214/23-EJS2157`，volume 17 / issue 2 / pages 3008-3049） |
| S6 | Chernozhukov V, Chetverikov D, Demirer M, Duflo E, Hansen C, Newey W, Robins J. Double/debiased machine learning for treatment and structural parameters. *The Econometrics Journal*, 2018, 21(1): C1–C68. | 交叉拟合 + Neyman 正交的 DML 框架；本项目 nuisance 估计的纪律来源 | 不支持"任意 ML 模型 + 任意样本量都近似无偏"；正则条件不满足时失效 | canonical |
| S7 | Dudík M, Langford J, Li L. Doubly robust policy evaluation and learning. *ICML*, 2011: 1097–1104. | 策略价值的 DR 估计（本项目 DR 估值口径的来源） | 不支持重叠性失败时的策略比较；不支持把 off-policy 估值当在线 A/B 结论 | canonical |
| S8 | Athey S, Wager S. Policy learning with observational data. *Econometrica*, 2021, 89(1): 133–161. | 观察性数据下的策略学习与 regret 界；策略评估的目标量定义 | 不支持无重叠/强混淆下的策略最优性；不支持预算约束场景（本项目贪心另有来源） | canonical |
| S9 | Kitagawa T, Tetenov A. Who should be treated? Empirical welfare maximization methods for treatment choice. *Econometrica*, 2018, 86(2): 591–616. | 经验福利最大化（EWM）与策略 regret 的统计框架 | 不支持连续处理/预算约束扩展；不支持本项目特定 DGP 的结论 | canonical |
| S10 | Holm S. A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 1979, 6(2): 65–70. | F02 单侧 Holm 两比较的多重性控制 | 不支持任意依赖结构下的 FWER 控制（论文假设为一般情形但保守）；不支持把 p 值当效应大小 | canonical |
| S11 | Kohavi R, Tang D, Xu Y. *Trustworthy Online Controlled Experiments: A Practical Guide to A/B Testing*. Cambridge University Press, 2020. | AA 校准、样本比例失配、护栏指标、实验平台口径（E/G01 的实践依据） | 不支持把 AA 通过当作策略有效；不支持合成实验替代真实流量 | canonical |
| S12 | Curth A, Svensson D, Weatherall J, van der Schaar M. Really doing great at estimating CATE? A critical look at ML benchmarking practices in treatment effect estimation. *NeurIPS 2021 Datasets and Benchmarks Track (round 2)*. | 合成/半合成 CATE 基准的评价陷阱（本项目"合成 DGP→不外推"的方法学依据） | 不支持对任何具体估计器优劣的结论；不支持替代真实数据验证 | **官方 proceedings ✓（2026-10-29 11:54）**：官方摘要页 `datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/2a79ea27c279e471f4d180b08d62b00a-Abstract-round2.html` 与 PDF `…/file/…-Paper-round2.pdf` 均可达；题名/四位作者/venue（"Proceedings of the NeurIPS Track on Datasets and Benchmarks 1"，D&B 2021）与条目一字不差。该轨道**无 DOI**（同日 11:36 Crossref 精确查无记录），故不标 Crossref ✓、只标 official ✓ |

## 使用规则（写进长稿时必须遵守）

1. **支持范围是上界**：引用只能落在"支持什么"列；跨列使用视为越界。
2. **合成属性必须同段出现**：凡引用本项目数字，同段必须出现"合成数据 / 已知 DGP"与失效条件。
3. **Tier1/Tier2 不并列**：S2/S3 的推断性质只适用于 Tier1 的 R=250/500 口径；Tier2（R=30）只能判方向，
   引用 S12 说明其精度局限。
4. **AA 不等于有效**：引用 S11 时不得推出"策略有效"或"可上线"。
5. **数字溯源**：长稿里每个数字回指 `outputs/tables/` 或 `outputs/evidence/` 的具体文件（H04 claim 注册表）。

## 待办（H05 收尾前）

- [x] 核验 S5、S12 的卷期/页码。**11:36**：S5 精确命中（DOI `10.1214/23-EJS2157`，
  17(2): 3008–3049）→ **Crossref ✓**。**11:54**：S12 拿到官方 proceedings 直链与 PDF
  （hash `2a79ea27…b00a`，round 2），题名/作者/venue 与条目一字不差 → **官方 proceedings ✓**；
  该轨道无 DOI，长稿引用**不得**写"Crossref 已核"，只能写官方 proceedings 链接；
- [~] 逐条检查长稿引用编号与本表一致（12 篇，不多不少）。**12:20 机制就位**：`paper/v3/refs.bib`
  恰 12 条（`s1`–`s12`，字段逐条照抄本表，未核验的 DOI 一律不写），biblatex `style=numeric,
  sorting=none` + biber；探针稿 4 处引用印成 `[1]`–`[12]` 且顺序=首次引用顺序，参考文献独立成页、
  标题"参考文献"。**待办**：长稿成文后逐条核对"哪句话引了哪篇"，并确认没有表外条目；
- [ ] 检查"无面额外推"：全文搜索"真实业务/上线/推广"等词，确认每处都带合成属性限定。
