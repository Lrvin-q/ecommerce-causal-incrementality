# Phase D 修复复核（独立复核人）

> 复核对象：HEAD `9c4f684`（含 `d270cae` P0-1/E-1/E-2、`4b07766` 19 号加固、`9c4f684` 17 号加固）
> 复核范围：上一轮评审 `v3_phase_D_review_science.md` 的 P0-1 与 `v3_phase_D_review_eng.md` 的 E-1/E-2/E-3
> 复核方式：**全部自跑复算，不采信修复者陈述**。只在 `C:/Users/26382/AppData/Local/Temp/recheck` 下建沙箱，
> 源码与产物零修改（收尾 `git status --porcelain` 为空）；未跑全量 pytest。
> 数字均以 `./.venv/Scripts/python.exe` + `PYTHONUTF8=1` 实跑得到。

## 1. 总判定

**PASS** —— 四项（P0-1 的 σ/MDE、E-1 证据自足、E-2 保护名单、E-3 两脚本校验）全部经独立复算成立，
且修复的副作用（改动范围、幂等性、`_provisional` 机制）也逐条验过；遗留问题均不改变 D02 的结论。

## 2. 逐项复核

### R1. P0-1｜MDE 表 448 行 σ 修复 —— **成立**

**(a) σ 公式（容差 1e-12）**

| 检查 | 结果 |
|---|---|
| `metric=='paid_purchase_7d'` 行数 | 448（全部 `record_type=design_mde`），无空值 |
| `sigma_control − sqrt(p0(1−p0))` | 最大绝对偏差 **0.000e+00** |
| `sigma_treatment − sqrt(p1(1−p1))` | 最大绝对偏差 **0.000e+00** |
| 修复后取值范围 | control `0.287043–0.302216`；treatment `0.291578–0.324895` |
| 修复前同列（`7771d7b`） | control `8.457–10.322`、treatment `9.283–12.105`（= 利润 σ） |

即 σ 列确实由利润 σ 换成了 Bernoulli σ，且与行内 `p0_baseline` / `p1_at_mde` 逐行自洽。

**(b) MDE 复算（`causal_growth.design.v3_power.purchase_mde`）**

| treatment_share | 行数 | 最大绝对差 | 最大相对差 | 超 1e-8 行数 |
|---|---|---|---|---|
| 50/50 | 160 | **0.000e+00** | **0.000e+00** | 0 |
| 30/70 | 128 | **0.000e+00** | **0.000e+00** | 0 |
| 10/90 | 128 | **0.000e+00** | **0.000e+00** | 0 |

（用表内 `alpha_per_test` / `power_target` / `sides`、`tolerance=1e-10`（= `configs/v3/design.yaml:72` 的
`numerical.root_tolerance`）重算，448 行全部**逐位相等**。改用 `tolerance=1e-12` 时最大相对差 4.9e-9，
即残差来自根求解容差，不是表错。）

**(c) 关键：MDE 列没有因修 σ 而改变**

```
git rev-parse HEAD~5:outputs/tables/v3_phase_D_mde.csv  -> 488c3e0d…（= 7771d7b 的 blob，修复前）
git rev-parse HEAD:outputs/tables/v3_phase_D_mde.csv     -> ba45027f…（= 工作树，git status 干净）
```

逐列对比修复前/后：**唯一变化的列是 `sigma_treatment` 与 `sigma_control`，各 448 行，全部落在
`paid_purchase_7d`**；`mde`、`mde_pp`、`mde_relative_pct`、`control_mean`、`p0_baseline`、`p1_at_mde`、
`alpha_per_test`、`n_treatment/n_control`、`target_effect`、`noninferiority_margin` 的最大差**全部为 0.000e+00**；
利润/护栏 284 行的 σ 也零改动。整表只有这 448 行 × 2 列不同（其余 284 行逐字节相同）。

**(d) 源码分支**

`src/causal_growth/design/v3_power.py:1979-1982` 已按 `is_proportion` 分支：

```python
"sigma_treatment": (math.sqrt(p1 * (1.0 - p1)) if is_proportion else profile.profit_sd_treatment),
"sigma_control":   (math.sqrt(p0 * (1.0 - p0)) if is_proportion else profile.profit_sd_control),
```

`git diff 7771d7b d270cae -- src/.../v3_power.py` 只改这 2 个字段（6 行），无其他改动。
语义也自洽：`purchase_power` 的 `se_alt = sqrt(p1(1−p1)/n1 + p0(1−p0)/n0)`（`:608`），
两个 σ 列正是该式中两臂的分量，不再与 MDE 口径脱节。

**判定：成立。** 限制照旧（表是"旧画像 + 定点补数"，非当前代码整表重生成），已由 §8.2 如实披露。

---

### R2. E-1｜证据自足 —— **成立（含 1 处不影响结论的瑕疵）**

**只用 `outputs/evidence/` 重建**（未打开 `out/`）：

| 项 | 重建值 | 文档 §1 | 差异 |
|---|---|---|---|
| 原始行数 → 去重后 | 1384 → **1000**（按 `[level, rep]`） | 1384→1000（E-1 条目） | 一致 |
| 逐层行数 | L0/L1/L2/L3 = **250/250/250/250** | 250×4 | 一致 |
| `net_profit` FPR | **46/1000 = 0.0460** | 46/1000, 0.046 | 一致 |
| `net_profit` CP95 | **[0.0339, 0.0609]** | [0.0339, 0.0609] | 一致 |
| `net_profit` MC SE | 0.0066 | 0.0066 | 一致 |
| 逐层拒绝数 / CP | 14 [0.0310,0.0922]；11 [0.0222,0.0774]；10 [0.0193,0.0723]；11 [0.0222,0.0774] | 同 | 一致 |
| `paid_purchase_7d` / `any_refund_30d` | 40/1000=0.040 [0.0287,0.0541]；52/1000=0.052 [0.0391,0.0676] | 0.040 / 0.052（§1.1） | 一致 |
| SE 校准（净利） | 0.987/0.994/0.988/0.995，合并 **0.995** | 同 | 一致 |
| 四层异质性 | χ²=0.820, df=3, p=**0.845** | 同 | 一致 |
| p 值均匀性 | KS D=**0.0191**, p=**0.854** | 同 | 一致 |
| CI 与 p 一致性 | 46 vs 46，**0 例不一致** | 同 | 一致 |

去重本身无歧义：384 个重复组内 `net_profit` / `paid_purchase_7d` 的 p 值 **0 组冲突**（重复来自续跑复制行）。

**sha256 核对**：`coverage.json` 的 11 条记录逐条比对实际文件，**11/11 的 `sha256` 与 `bytes` 全部相符**，
`total_bytes` 1829631 与实测一致。

**瑕疵（不影响 AA 结论）**：`outputs/evidence/negctl/aa_repetitions.csv` 有 101 行，其中 1 行是
`run_id=aa:true_aa:L0_AA:rep0:n200000`（`block=true_aa`）混进了负对照导出；直接按 `rep` 去重或按
`block != true_aa` 过滤后为 100 行，才得到文档 §4 的 8/100、100/100、7/100（CP 也逐位对上）。
`coverage.json` 对该文件只记了字节数与 sha，没有 `rows_raw/rows_deduped`，读者需自己判断要先过滤 block。
属导出脚本的卫生问题，不是数字问题。

**判定：成立。** 四项 D02 证据的统计量均可仅凭 `outputs/evidence/` 独立重建，且与正文逐位一致。

---

### R3. E-2｜清理脚本保护 —— **成立（副作用：一条清理规则被永久遮蔽）**

`scripts/16_cleanup_scratch.py::is_obsolete` 实跑（importlib 直接导入，不执行删除）：

| 名字 | 期望 | 实测 |
|---|---|---|
| `v3_phase_d_aa_formal_r2` | False | **False** |
| `v3_phase_d_aa_formal_r2_det` | False | **False** |
| `v3_phase_d_aa_nc20w` | False | **False** |
| `v3_phase_d_aa_nc20w_r2` | False | **False** |
| `v3_phase_d_aa_nc` | False | **False** |
| `v3_phase_d_local_power` | False | **False** |
| `c3_snapshot` | False | **False** |
| `pytest_tmp` | True | **True** |
| `probe_x` | True | **True** |

**判定：成立**（7/7 保护、2/2 仍可删）。

**副作用（记录在案，方向是"少删"，不是"错删"）**：`PROTECTED_NAMES` 含 `"v3_phase_d"` 且按**前缀**
生效，于是 `OBSOLETE_PREFIXES` 里的 `"v3_phase_d_aa"`（D.2 pilot）永远命中不到——实测
`v3_phase_d_aa_pilot → False`，该条清理规则已成死规则。当前 `out/` 预演结果只剩 `out/pytest`（176.9 MB）
一个目录可删。

---

### R4. E-3｜两脚本校验 —— **成立**

**(a) `scripts/19_finalize_local_power.py::validate`**（基线 = 已提交的 15 行正式表）

| 用例 | 结果 | 拒绝理由 |
|---|---|---|
| 正常表 | 0 问题 | — |
| `n_total=1` | **拒** | `n_total 与注册规模 200000 不符` |
| `alpha=0.5` | **拒** | `alpha 不等于 0.05: [15 个 cell_id]` |
| `rejection_rate = 1−rate` | **拒** | `rejection_rate 与 rejections/n_reps 不一致: [15 个]` |
| `rejections=0`（rate 不变） | **拒** | 同上（自洽性拦下） |
| 同 (level,mult) 复制一行、改 `cell_id`、使行数 16 | **拒** | `行数 16 ≠ 15` |

另核：`v3_phase_D_local_power_formal.json` 的 `csv_sha256 = cbb48822288ac184…` 与实际 CSV **相符**，
`validation=passed / cells=15 / total_reps=1500`，与文档 §8.3 的 `cbb48822…` 一致。

**(b) `scripts/17_merge_aa_layers.py`**

| 用例 | 结果 |
|---|---|
| L0 单行 `alpha=0.5` | **SystemExit**：`拒绝合并：alpha 不一致 [0.05, 0.5]` |
| L0 单行 `n_total=1` | **SystemExit**：`拒绝合并：n_total=[1, 200000] 与注册规模 200000 不符` |
| `--band-low 0.06 --band-high 0.08` | **SystemExit**：`拒绝：band [0.06, 0.08] 必须把 0.05 夹在中间` |
| 正常路径（真跑默认 5 个 run-root） | 退出 0，POOLED 46/40/52 = 0.046/0.040/0.052，逐层 250×4 |

**幂等**：真跑前后 `outputs/tables/v3_phase_D_aa_formal_merged.csv` 的 sha256 均为
`2c6d6e91bf4b89ea…`、json 均为 `cc8151487aff649a…`，`git status --porcelain` 为空。

**`_provisional` 机制未被破坏**（沙箱内用"未跑满"的真实 root 组合 40/48/48/43 行验证）：
退出 0、打印 `⚠ 未跑满：{'L0': 40, 'L1': 48, 'L2': 48, 'L3': 43}（目标 250/层）`，
**只写** `..._merged_provisional.csv/json`（POOLED reps=179，json `provisional=true`），
**没有**写正式路径；满 250 时才写非 provisional。加固确实没有把中途进度堵死。

**判定：成立。**

## 3. FAIL 项

无。

## 4. 结论与遗留项

**D02 的四项证据与四类修复均经独立复核，满足 R01 的签字条件。**

复核方式可复核性：本轮所有判据均为可重跑的命令（见附录），复算脚本落在临时目录，未写入仓库。

**仍未解决但不阻塞签字的遗留项**（按优先级）：

1. **负对照证据混入 1 行 AA**（`outputs/evidence/negctl/aa_repetitions.csv`：101 行含
   `true_aa/L0_AA/rep0`）。按 `block` 过滤后 100 行才复现 8/100、100/100、7/100；
   `coverage.json` 未记该文件的 `rows_raw/rows_deduped`。建议导出时按 block 过滤并补两个计数字段。
2. **`coverage.json` 无逐文件"用途→结论"映射**，读者需自行知道哪个文件支撑哪条断言（本轮已由复核人建立
   映射，但没落到文件里）。
3. **证据可"复算"但不可"重跑"**：`aa_snapshot` / `c3_snapshot` 目录未导出，`bindings/*.json` 只给
   文件名清单 + 一个聚合 `binding_sha256`，无逐文件哈希，换机只能校验"这些统计量"、无法校验"这些源码"。
   另 `manifest_*.json` 的 `source_hashes_before` 与当前 HEAD 有 **6/40 个文件**不一致
   （`v3_local_power_pipeline.py`、`v3_observed.py`、`v3_power.py`、`v3_local_power.py`、
   `v3_models.py`、`v3_data_checks.py`）——属快照运行后的正常漂移，AA 结论不受影响，但"快照绑定"这一项
   仍无法仅凭证据自证。
4. **16 号的 `v3_phase_d_aa` 清理规则已成死规则**（被 `v3_phase_d` 前缀保护遮蔽），`out/` 现在只有
   `out/pytest` 可释放。若要恢复"能清 pilot、不能清正式 run-root"，需把保护改成显式全名清单或正则。
5. **文档残留一处未同步**：`docs/v3_phase_D_aa_formal.md:80` 仍写"真值约 −0.56 元/人 **≈ 4 倍设计 MDE**"，
   与同节 `:73` 的 **4.93×** 及 §8.1 的修正表相互矛盾（P0-2 的修订漏改了正文这一句）。
6. **MDE 表与代码生成路径仍不一致**（已在 §8.2 披露）：当前代码重跑 pilot 才会端到端对齐；本次不重跑的理由
   （I/O 瓶颈）成立，但应挂一个"下次全量 pilot 后删除 §8.2 限制说明"的待办。
7. **17 号仍不做 rep 连续性校验**（只按 `(block,rep)` 去重后计数，不检查 rep 是否有洞/越界；
   `19` 号亦然）。与 E-3 要求无关，属下一轮可加项。

## 附录：本轮复核命令（可重跑）

```bash
# R1 σ 公式 + 448 行 MDE 复算（tolerance 取 configs/v3/design.yaml:72 的 1e-10）
./.venv/Scripts/python.exe - <<'PY'
import pandas as pd, sys; sys.path.insert(0,'src')
from causal_growth.design.v3_power import purchase_mde
p=pd.read_csv('outputs/tables/v3_phase_D_mde.csv'); p=p[p.metric=='paid_purchase_7d']
print(len(p), (p.sigma_control-(p.p0_baseline*(1-p.p0_baseline))**.5).abs().max())
print((p.sigma_treatment-(p.p1_at_mde*(1-p.p1_at_mde))**.5).abs().max())
for s in (0.5,0.3,0.1):
    q=p[(p.treatment_share-s).abs()<1e-9]
    print(s, max(abs(purchase_mde(r.p0_baseline,int(r.n_treatment),int(r.n_control),
        alpha=float(r.alpha_per_test),power=float(r.power_target),sides=str(r.sides),
        tolerance=1e-10)-r.mde) for _,r in q.iterrows()))
PY

# R1 mde 零改动
git rev-parse HEAD~5:outputs/tables/v3_phase_D_mde.csv   # 488c3e0d…
git show 7771d7b:outputs/tables/v3_phase_D_mde.csv > /tmp/old_mde.csv   # 再逐列比对

# R2 仅用证据重建
./.venv/Scripts/python.exe -c "..."   # drop_duplicates(['level','rep']) → 1000；p<0.05 计数 46；scipy beta CP

# R3 保护名单
./.venv/Scripts/python.exe -c "import importlib.util; ..."   # 7×False + 2×True

# R4 17 号三类篡改（沙箱，ROOT 重定向到临时目录）+ 正常路径幂等
./.venv/Scripts/python.exe scripts/17_merge_aa_layers.py
git status --porcelain outputs/tables/
```
