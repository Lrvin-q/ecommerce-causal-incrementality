"""文档数字一致性检查：以 ``outputs/tables/*.csv`` 为单一事实源，校验全部中文文档。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\07_check_consistency.py
    .\\.venv\\Scripts\\python.exe scripts\\07_check_consistency.py -v   # 打印每个关键数字的命中位置

它回答方案里的哪个问题："报告里的每个数字都能追溯到某张 CSV"这件事，由谁来保证？
答案是脚本，不是人眼复查——**DGP 一改，8 份手写文档里的数字就会漂移**（见复盘 §7.1）。

三类检查
--------
1. **关键数字**：从 CSV 读出权威值，检查它出现在**该出现的文档**里（不是"全文随便哪里"——
   否则论文更新了、README 没更新也能通过）。
2. **旧值黑名单**：v1（无复购）的数字一旦在文档里复活，立刻报错并打印 ``文件:行号``。
   例外只有一处：论文附录 D 的 v1→v2 映射表，用 ``<!-- old-values-ok:start/end -->`` 显式豁免。
3. **版本说明**：每份文档顶部必须有一行统一的"数据版本：v2"说明。

退出码：0 = 通过；1 = 发现旧值 / 缺关键数字 / 缺版本说明。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
REPORTS = ROOT / "reports"

#: 需要带"数据版本"说明的文档（README + reports/*.md）
DOCS: list[Path] = [ROOT / "README.md"] + sorted(REPORTS.glob("*.md"))

#: 旧值豁免标记：只有论文附录 D 的映射表用它（那里必须保留旧值才说得清"变了什么"）
EXEMPT_START = "<!-- old-values-ok:start"
EXEMPT_END = "<!-- old-values-ok:end -->"


# ---------------------------------------------------------------------------
# CSV 读取
# ---------------------------------------------------------------------------
def _load(name: str) -> list[dict[str, str]]:
    """读一张结果表（utf-8-sig，Excel 友好编码）。"""
    path = TABLES / name
    if not path.exists():
        raise SystemExit(f"找不到结果表 {path}；请先跑 scripts/run_all.py --round all")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _same(cell: str, want: str) -> bool:
    """单元格与期望值比较：先按数值比，再按字符串比（容忍 1e-9 相对误差）。"""
    try:
        return abs(float(cell) - float(want)) <= 1e-9 * max(1.0, abs(float(want)))
    except (TypeError, ValueError):
        return str(cell).strip() == str(want).strip()


def pick(name: str, col: str, **where: str) -> float:
    """按 ``列=值`` 选出唯一一行，返回 ``col`` 列的浮点值。"""
    rows = _load(name)
    for key, want in where.items():
        rows = [r for r in rows if _same(r[key], want)]
    if len(rows) != 1:
        raise SystemExit(f"{name}: 按 {where} 选到 {len(rows)} 行（应为 1 行）")
    return float(rows[0][col])


def ratio(name: str, col: str, key_col: str, num: str, den: str) -> float:
    """同一张表里两个 key 的 ``col`` 之比（如 定向/随机）。"""
    rows = {r[key_col]: r for r in _load(name)}
    return float(rows[num][col]) / float(rows[den][col])


# ---------------------------------------------------------------------------
# 第 1 类：关键数字（至少 12 个；值全部来自 CSV，不允许手写）
# ---------------------------------------------------------------------------
def key_numbers() -> list[dict]:
    """从 CSV 读出权威值，并声明"哪些文档必须出现它"。"""
    return [
        {
            "name": "真值 ATE 利润（L1，元/人）",
            "value": pick("r1_itt.csv", "真值", 层级="L1", 指标="net_profit_per_user"),
            "source": "r1_itt.csv",
            "tokens": ["0.668"],
            "must_in": ["README.md", "02_随机实验报告.md"],
        },
        {
            "name": "ITT 利润估计（L1，元/人）",
            "value": pick("r1_itt.csv", "ITT估计", 层级="L1", 指标="net_profit_per_user"),
            "source": "r1_itt.csv",
            "tokens": ["0.724"],
            "must_in": ["README.md", "02_随机实验报告.md"],
        },
        {
            "name": "ITT 利润估计（L0，元/人）",
            "value": pick("r1_itt.csv", "ITT估计", 层级="L0", 指标="net_profit_per_user"),
            "source": "r1_itt.csv",
            "tokens": ["0.622"],
            "must_in": ["02_随机实验报告.md"],
        },
        {
            "name": "转化率 ITT（L1，pp）",
            "value": 100 * pick("r1_itt.csv", "ITT估计", 层级="L1", 指标="conversion"),
            "source": "r1_itt.csv",
            "tokens": ["5.01pp"],
            "must_in": ["README.md", "02_随机实验报告.md"],
        },
        {
            "name": "每元回报（定向-贪心，元）",
            "value": pick("r3_six_strategies.csv", "value_per_yuan", strategy_key="target_greedy"),
            "source": "r3_six_strategies.csv",
            "tokens": ["2.085"],
            "must_in": ["README.md", "04_策略优化报告.md", "05_业务决策摘要.md", "06_面试讲解材料.md"],
        },
        {
            "name": "每元回报（随机，元）",
            "value": pick("r3_six_strategies.csv", "value_per_yuan", strategy_key="random"),
            "source": "r3_six_strategies.csv",
            "tokens": ["0.730"],
            "must_in": ["README.md", "05_业务决策摘要.md"],
        },
        {
            "name": "定向/随机（倍）",
            "value": ratio("r3_six_strategies.csv", "incremental_value", "strategy_key", "target_greedy", "random"),
            "source": "r3_six_strategies.csv",
            "tokens": ["2.86"],
            "must_in": ["README.md", "04_策略优化报告.md", "05_业务决策摘要.md"],
        },
        {
            "name": "达真值贪心解（%）",
            "value": pick("r3_six_strategies.csv", "pct_of_oracle", strategy_key="target_greedy"),
            "source": "r3_six_strategies.csv",
            "tokens": ["86.1"],
            "must_in": ["README.md", "04_策略优化报告.md"],
        },
        {
            "name": "策略价值（定向-贪心，元/人）",
            "value": pick("r3_six_strategies.csv", "incremental_value", strategy_key="target_greedy"),
            "source": "r3_six_strategies.csv",
            "tokens": ["0.349", "0.3489"],
            "must_in": ["04_策略优化报告.md"],
        },
        {
            "name": "真值贪心解价值（元/人）",
            "value": pick("r3_six_strategies.csv", "incremental_value", strategy_key="oracle"),
            "source": "r3_six_strategies.csv",
            "tokens": ["0.405"],
            "must_in": ["04_策略优化报告.md"],
        },
        {
            "name": "利润 σ（元/人）",
            "value": pick("r1_sample_size_inputs.csv", "取值", 参数="profit_sd_assumed"),
            "source": "r1_sample_size_inputs.csv",
            "tokens": ["11.08"],
            "must_in": ["README.md", "02_随机实验报告.md"],
        },
        {
            "name": "利润支 n_per_group",
            "value": pick("r1_sample_size.csv", "n_per_group_profit"),
            "source": "r1_sample_size.csv",
            "tokens": ["7,709"],
            "must_in": ["02_随机实验报告.md"],
        },
        {
            "name": "AA 假阳性率（转化率）",
            "value": pick("r1_aa_summary.csv", "假阳性率", 指标="转化率（二元）"),
            "source": "r1_aa_summary.csv",
            "tokens": ["0.059"],
            "must_in": ["README.md", "02_随机实验报告.md"],
        },
        {
            "name": "AA 假阳性率（利润）",
            "value": pick("r1_aa_summary.csv", "假阳性率", 指标="人均净贡献利润（连续）"),
            "source": "r1_aa_summary.csv",
            "tokens": ["0.040"],
            "must_in": ["README.md", "02_随机实验报告.md"],
        },
        {
            "name": "护栏非劣效检验功效（条件分母）",
            "value": pick("r1_guardrail_power.csv", "当前功效",
                          **{"情景": "真实小幅恶化（0.225pp，DGP 设定）",
                             "分母": "已下单用户"}),
            "source": "r1_guardrail_power.csv",
            "tokens": ["0.194"],
            "must_in": ["README.md", "02_随机实验报告.md", "05_业务决策摘要.md"],
        },
        {
            "name": "重复 200 次利润覆盖率（L1）",
            "value": pick("r1_repeats_summary.csv", "利润_覆盖真值率", level="L1"),
            "source": "r1_repeats_summary.csv",
            "tokens": ["0.950"],
            "must_in": ["README.md", "02_随机实验报告.md"],
        },
        {
            "name": "CATE R²（Causal Forest）",
            "value": pick("r2_cate_comparison.csv", "R2", 方法="Causal Forest"),
            "source": "r2_cate_comparison.csv",
            "tokens": ["0.307"],
            "must_in": ["README.md", "03_异质性与观察性因果.md"],
        },
        {
            "name": "CATE RMSE（T-learner）",
            "value": pick("r2_cate_comparison.csv", "CATE_RMSE", 方法="T-learner"),
            "source": "r2_cate_comparison.csv",
            "tokens": ["1.625"],
            "must_in": ["03_异质性与观察性因果.md"],
        },
        {
            "name": "λ=0.25 覆盖率（IPW）",
            "value": pick("r2_lambda_summary.csv", "覆盖率", **{"method": "ipw", "lambda": "0.25"}),
            "source": "r2_lambda_summary.csv",
            "tokens": ["0.82"],
            "must_in": ["03_异质性与观察性因果.md"],
        },
        {
            "name": "λ=0.25 覆盖率（DR）",
            "value": pick("r2_lambda_summary.csv", "覆盖率", **{"method": "dr", "lambda": "0.25"}),
            "source": "r2_lambda_summary.csv",
            "tokens": ["0.79"],
            "must_in": ["03_异质性与观察性因果.md"],
        },
        {
            "name": "λ=0.5 偏差（IPW，元/人）",
            "value": pick("r2_lambda_summary.csv", "偏差", **{"method": "ipw", "lambda": "0.5"}),
            "source": "r2_lambda_summary.csv",
            "tokens": ["0.542"],
            "must_in": ["03_异质性与观察性因果.md"],
        },
        {
            "name": "PSM 加权后最大 |SMD|（λ=0.5）",
            "value": max(abs(float(r["IPW加权后SMD"])) for r in _load("r2_psm_balance.csv")
                         if float(r["lambda"]) == 0.5),
            "source": "r2_psm_balance.csv",
            "tokens": ["0.004", "0.0038"],
            "must_in": ["03_异质性与观察性因果.md"],
        },
        {
            "name": "贪心/ LP 上界（全规模）",
            "value": pick("r3_greedy_gap.csv", "贪心/上界", 项="全规模（n=60000）"),
            "source": "r3_greedy_gap.csv",
            "tokens": ["99.9999", "0.999999"],
            "must_in": ["04_策略优化报告.md", "06_面试讲解材料.md"],
        },
        {
            "name": "贪心反例（背包 18 vs 贪心 12）",
            "value": pick("r3_greedy_gap.csv", "精确DP", 项="方案反例（3 件）"),
            "source": "r3_greedy_gap.csv",
            "tokens": ["12 vs 18", "33%"],
            "must_in": ["04_策略优化报告.md", "06_面试讲解材料.md"],
        },
    ]


# ---------------------------------------------------------------------------
# 第 2 类：v1 旧值黑名单
# ---------------------------------------------------------------------------
#: (正则, 说明)。正则都带数字边界，避免把 10.79 误判成 110.79。
BLACKLIST: list[tuple[str, str]] = [
    # 注意：v1 的真值 0.633 与 v2 Causal Forest 的 Top20% 重合度 0.633 撞值，
    # 裸数字无法区分，因此这里只匹配"真值 0.633"这种带上下文的写法 + 四位小数 0.6331。
    (r"真值[^。\n]{0,8}0\.633|0\.6331", "v1 真值 ATE 利润 0.633"),
    (r"(?<![\d.])0\.678\d?(?![\d])", "v1 ITT 利润 0.678"),
    (r"(?<![\d.])1\.97(?![\d])", "v1 定向每元回报 1.97"),
    (r"(?<![\d.])2\.56(?![\d])", "v1 定向/随机 2.56 倍"),
    (r"84\.9(?=\s*%)", "v1 达真值贪心解 84.9%"),
    (r"(?<![\d.])10\.79(?![\d])", "v1 利润 σ 10.79"),
    (r"7,324", "v1 利润支 n_per_group 7,324"),
    (r"(?<![\d.])2\.33(?![\d])", "v1 真值最优每元回报 2.33"),
    (r"0\.3892", "v1 真值贪心解价值 0.3892"),
    (r"0\.5747", "v1 全量发券价值 0.5747"),
    (r"0\.1290", "v1 随机策略价值 0.1290"),
    (r"3\.0458|3\.5803|3\.6427|3\.6563|3\.6928", "v1 CATE 策略价值（绝对口径 3.0×）"),
    (r"23,853", "v1 贪心/LP 金额 23,853"),
    (r"462\.97|461\.36", "v1 降规模贪心/DP 金额"),
    (r"147\.7(?=\s*%)", "v1 全量发券占真值比 147.7%"),
    (r"(?<![\d.])[−-]?4\.82(?![\d])", "v1 T-learner R² = −4.82"),
    (r"(?<![\d.])0\.333(?![\d])", "v1 Causal Forest R² 0.333"),
    (r"(?<![\d.])0\.178(?![\d])", "v1 S-learner R² 0.178"),
    (r"(?<![\d.])1\.586(?![\d])", "v1 T-learner RMSE 1.586"),
    (r"(?<![\d.])0\.537(?![\d])", "v1 Causal Forest RMSE 0.537"),
    (r"82\.6(?=\s*%)", "v1 策略价值达最优 82.6%"),
    (r"94\.4(?=\s*%)", "v1 策略价值达最优 94.4%"),
    (r"(?<![\d.])0\.465(?![\d])", "v1 λ=0.5 IPW 偏差 0.465"),
    (r"(?<![\d.])0\.828(?![\d])", "v1 λ=0 Naive 偏差 0.828"),
    (r"85\.2(?=\s*%)", "v1 真值非负比例 85.2%"),
    (r"75\.8(?=\s*%)", "v1 T-learner 选中比例 75.8%"),
    (r"12,001|15,896|16,955", "v1 三策略选中人数"),
    (r"(?<![\d.])4\.96(?![\d])", "v1 预算最紧时的相对优势 4.96 倍"),
    (r"(?<![\d.])2\.88(?![\d])", "v1 核销率 ×0.8 的每元回报 2.88"),
    (r"(?<![\d.])1\.53(?![\d])", "v1 核销率 ×1.2 的每元回报 1.53"),
    (r"0\.945\s*[-–—]\s*0\.955|0\.955", "v1 重复实验覆盖率区间 0.945–0.955"),
    # 25,215 在 v2 里同时是"下单用户数"（合法），只有写成 orders 行数时才是旧值，
    # 故不把裸数字列入黑名单，改由 r1_quality_clean.csv 校验行数。
    (r"0\.5027|0\.4973", "v1 分组比例 0.5027/0.4973"),
    (r"12\.07|18\.11", "v1 人均 GMV 12.07 / 18.11"),
    (r"(?<![\d.])6\.04(?![\d])", "v1 人均 GMV 增量 6.04"),
    (r"0\.0146", "v1 两条利润路径最大差 0.0146"),
    (r"(?:380|400) 项测试", "旧测试数 380 / 400 项（v2 为 404）"),
]


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------
def read_without_exempt(path: Path) -> list[tuple[int, str]]:
    """读文档，返回 (行号, 文本)；豁免标记之间的行被替换为空行（行号不变）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[tuple[int, str]] = []
    inside = False
    for i, line in enumerate(lines, start=1):
        if EXEMPT_START in line:
            inside = True
        if not inside:
            out.append((i, line))
        if EXEMPT_END in line and inside:
            inside = False
    return out


def check_version_banner(problems: list[str]) -> None:
    """内部文档顶部必须有统一的"数据版本：v2"说明。

    **论文本身（``00_项目总报告.md``）除外**：它是对外交付物，按体例不应出现
    内部版本迭代痕迹（版本、变更记录、旧值映射都属于内部文档的职责）。
    论文的数字一致性由关键数字校验与旧值黑名单守住，不依赖版本横幅。
    """
    for doc in DOCS:
        if doc.name.startswith("00_"):
            if "数据版本" in doc.read_text(encoding="utf-8"):
                problems.append(
                    f"{doc.relative_to(ROOT)} 出现内部版本标记：论文不应携带版本横幅"
                )
            continue
        head = "\n".join(doc.read_text(encoding="utf-8").splitlines()[:12])
        if "数据版本：v2" not in head:
            problems.append(f"{doc.relative_to(ROOT)}:1 缺少版本说明行（应含“数据版本：v2”）")


def check_internal_consistency(problems: list[str]) -> None:
    """表内自洽：``pct_of_oracle`` 与 ``regret`` 必须满足它们自己的定义式。

    这条检查来自一次真实事故：随机策略行的 ``incremental_value`` 被替换成
    "200 个种子的均值"，但同一行的 ``pct_of_oracle`` / ``regret`` 还停留在单次实现上，
    于是 0.1222/0.4050 = 30.2% 的位置写着 34.3%。**跨列自洽必须由脚本守。**
    """
    for row in _load("r3_six_strategies.csv"):
        if str(row.get("over_budget")).strip() == "True":
            continue  # 超预算策略的占比/regret 按定义置 NaN
        name = row["strategy"]
        value = float(row["incremental_value"])
        oracle = float(row["oracle_value"])
        pct = float(row["pct_of_oracle"])
        regret = float(row["regret"])
        if abs(pct - 100.0 * value / oracle) > 1e-6:
            problems.append(
                f"r3_six_strategies.csv[{name}]: pct_of_oracle={pct:.6f} 与 "
                f"100·V/V_oracle={100.0 * value / oracle:.6f} 不一致"
            )
        if abs(regret - (oracle - value)) > 1e-9:
            problems.append(
                f"r3_six_strategies.csv[{name}]: regret={regret:.9f} 与 "
                f"V_oracle−V={oracle - value:.9f} 不一致"
            )


def check_stale(problems: list[str]) -> int:
    """扫旧值黑名单，返回命中数。"""
    hits = 0
    for doc in DOCS:
        rel = doc.relative_to(ROOT).as_posix()
        for lineno, line in read_without_exempt(doc):
            for pattern, why in BLACKLIST:
                if re.search(pattern, line):
                    problems.append(f"{rel}:{lineno} 残留旧值：{why} → {line.strip()[:90]}")
                    hits += 1
    return hits


def check_key_numbers(problems: list[str], verbose: bool) -> None:
    """关键数字必须出现在"该出现的文档"里。"""
    keys = key_numbers()
    cache: dict[str, str] = {}
    for doc in DOCS:
        cache[doc.name] = "\n".join(text for _, text in read_without_exempt(doc))

    print("\n权威数字（读自 outputs/tables/*.csv）")
    print("-" * 104)
    print(f"{'指标':<34}{'v2 值':>14}  {'出处':<28}{'必须出现于':<24}")
    for k in keys:
        where = "、".join(k["must_in"])
        print(f"{k['name']:<34}{k['value']:>14.6g}  {k['source']:<28}{where:<24}")
        for doc_name in k["must_in"]:
            if doc_name not in cache:
                problems.append(f"缺失文档 {doc_name}")
                continue
            if not any(tok in cache[doc_name] for tok in k["tokens"]):
                problems.append(
                    f"reports/{doc_name}: 缺少关键数字 {k['name']} = {k['value']:.6g}"
                    f"（可接受写法：{' 或 '.join(k['tokens'])}）"
                )
    print("-" * 104)

    if verbose:
        print("\n命中位置（-v）")
        for k in keys:
            hit = [d for d in k["must_in"] if any(t in cache.get(d, "") for t in k["tokens"])]
            print(f"  {k['name']}: {', '.join(hit) if hit else '未命中'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档数字一致性检查（事实源：outputs/tables/*.csv）")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印关键数字的命中位置")
    args = parser.parse_args(argv)

    problems: list[str] = []
    check_version_banner(problems)
    check_key_numbers(problems, args.verbose)
    check_internal_consistency(problems)
    n_stale = check_stale(problems)

    print(f"\n扫描文档 {len(DOCS)} 份：{', '.join(d.name for d in DOCS)}")
    print(f"关键数字 {len(key_numbers())} 个；旧值黑名单 {len(BLACKLIST)} 条；命中旧值 {n_stale} 处")

    if problems:
        print(f"\n[未通过] 共 {len(problems)} 处问题：")
        for p in problems:
            print("  -", p)
        return 1

    print("\n[通过] 文档数字与 outputs/tables/*.csv 一致，未发现 v1 旧值。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
