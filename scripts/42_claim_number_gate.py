"""H04 数字门禁：claim 注册表逐条回指 source_csv，并检查 Tier/摘要纪律。

回答方案里的问题：长稿里的每个数字能不能只用 `outputs/` 重建？
用法：
    python scripts/42_claim_number_gate.py                 # 校验注册表
    python scripts/42_claim_number_gate.py --draft draft.md # 再查长稿引用（[Cxx] + 数字字面）
    python scripts/42_claim_number_gate.py --abstract paper/v3/abstract.md  # 摘要只准 Tier1 注册值
    python scripts/42_claim_number_gate.py --self-test      # 反例夹具：证明门禁会拦
退出码：0 全过；1 有问题；2 注册表结构错误。
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "outputs/tables/v3_h04_claim_registry.csv"
REQUIRED = ["claim_id", "chapter", "statement", "display_value", "decimals", "tier",
            "in_abstract", "source_csv", "filter", "column", "precision_note"]


def validate(registry: Path) -> list[str]:
    if not registry.is_file():
        return [f"注册表不存在：{registry}"]
    frame = pd.read_csv(registry, encoding="utf-8-sig", keep_default_na=False, dtype=str)
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        return [f"注册表缺列：{missing}"]
    problems: list[str] = []
    if frame["claim_id"].duplicated().any():
        dup = frame.loc[frame["claim_id"].duplicated(), "claim_id"].tolist()
        problems.append(f"claim_id 重复：{dup}")
    for idx, row in frame.iterrows():
        cid = row["claim_id"] or f"row{idx}"
        tier, in_abs = str(row["tier"]).strip(), str(row["in_abstract"]).strip().lower()
        if tier not in {"Tier1", "Tier2"}:
            problems.append(f"{cid}: tier={tier!r} 不是 Tier1/Tier2")
        if in_abs not in {"yes", "no"}:
            problems.append(f"{cid}: in_abstract={in_abs!r} 不是 yes/no")
        if in_abs == "yes" and tier != "Tier1":
            problems.append(f"{cid}: 摘要只允许 Tier1 结论，这里是 {tier}")
        if tier == "Tier2":
            note = str(row["precision_note"])
            if not note.strip() or ("R=30" not in note and "精度" not in note):
                problems.append(f"{cid}: Tier2 必须写精度说明（含 R=30 或 精度）")
        source = ROOT / str(row["source_csv"])
        if not source.is_file():
            problems.append(f"{cid}: source_csv 不存在 {row['source_csv']}")
            continue
        table = pd.read_csv(source, encoding="utf-8-sig")
        if str(row["column"]) not in table.columns:
            problems.append(f"{cid}: 列 {row['column']!r} 不在 {row['source_csv']}")
            continue
        try:
            picked = table.query(str(row["filter"]))
        except Exception as exc:  # 过滤器写法错误本身就是缺陷
            problems.append(f"{cid}: filter 无法执行（{exc}）")
            continue
        if len(picked) != 1:
            problems.append(f"{cid}: filter 命中 {len(picked)} 行，必须恰好 1 行")
            continue
        try:
            value = float(picked.iloc[0][str(row["column"])])
            decimals = int(row["decimals"])
        except (TypeError, ValueError) as exc:
            problems.append(f"{cid}: 取值/精度不可解析（{exc}）")
            continue
        rendered = f"{value:.{decimals}f}"
        if rendered != str(row["display_value"]).strip():
            problems.append(
                f"{cid}: 显示值 {row['display_value']!r} != 复算 {rendered}（源 {value!r}）")
    return problems


def check_draft(registry: Path, draft: Path) -> list[str]:
    if not draft.is_file():
        return [f"长稿不存在：{draft}"]
    text = draft.read_text(encoding="utf-8")
    frame = pd.read_csv(registry, encoding="utf-8-sig", keep_default_na=False, dtype=str)
    problems: list[str] = []
    for _, row in frame.iterrows():
        cid = row["claim_id"]
        if f"[{cid}]" not in text:
            problems.append(f"{cid}: 长稿未引用（缺 [{cid}] 标记）")
        if str(row["display_value"]).strip() not in text:
            problems.append(f"{cid}: 长稿没有数字 {row['display_value']}")
    return problems


def check_abstract(registry: Path, abstract: Path) -> list[str]:
    if not abstract.is_file():
        return [f"摘要不存在：{abstract}"]
    text = abstract.read_text(encoding="utf-8")
    frame = pd.read_csv(registry, encoding="utf-8-sig", keep_default_na=False, dtype=str)
    problems: list[str] = []
    for _, row in frame.iterrows():
        cid = row["claim_id"]
        value = str(row["display_value"]).strip()
        if str(row["in_abstract"]).strip().lower() == "yes" and value not in text:
            problems.append(f"{cid}: 摘要未包含注册值 {value}（in_abstract=yes）")
        if str(row["tier"]).strip() == "Tier2" and value in text:
            problems.append(f"{cid}: Tier2 数值 {value} 不得出现在摘要")
    return problems


def _write_registry(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REQUIRED)
        writer.writerows([[row.get(col, "") for col in REQUIRED] for row in rows])
    return path


def self_test() -> int:
    base = {
        "claim_id": "T01", "chapter": "9.9", "statement": "夹具", "display_value": "0.046",
        "decimals": "3", "tier": "Tier1", "in_abstract": "no",
        "source_csv": "outputs/evidence/g01_aa250/recomputed_fpr.csv",
        "filter": "metric == 'net_profit' and layer == 'POOLED'", "column": "fpr",
        "precision_note": "夹具",
    }
    cases = {
        "正例": [base],
        "改一位数字": [dict(base, display_value="0.047")],
        "源文件不存在": [dict(base, source_csv="outputs/tables/nope.csv")],
        "Tier2 缺精度": [dict(base, tier="Tier2", precision_note="")],
        "Tier2 进摘要": [dict(base, tier="Tier2", in_abstract="yes",
                             precision_note="R=30 精度")],
        "claim_id 重复": [base, base],
        "filter 空命中": [dict(base, filter="layer == 'NOPE'")],
        "列不存在": [dict(base, column="nope")],
    }
    expected_fail = {name for name in cases if name != "正例"}
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, rows in cases.items():
            path = _write_registry(Path(tmp) / "reg.csv", rows)
            problems = validate(path)
            failed = bool(problems)
            ok = failed if name in expected_fail else not failed
            print(f"[{'PASS' if ok else 'FAIL'}] {name}：{problems or '无问题'}")
            bad += 0 if ok else 1
        reg = _write_registry(Path(tmp) / "reg_abs.csv", [
            dict(base, in_abstract="yes"),
            dict(base, claim_id="T02", tier="Tier2", display_value="0.123456",
                 precision_note="R=30 精度"),
        ])
        abstract_cases = {
            "摘要缺注册值": ("正文没有数字", True),
            "摘要混入 Tier2": ("0.046 与 0.123456", True),
            "摘要正例": ("0.046 只写 Tier1", False),
        }
        for name, (text, expect_fail) in abstract_cases.items():
            ap = Path(tmp) / f"abs_{name}.md"
            ap.write_text(text, encoding="utf-8")
            problems = check_abstract(reg, ap)
            ok = bool(problems) if expect_fail else not problems
            print(f"[{'PASS' if ok else 'FAIL'}] {name}：{problems or '无问题'}")
            bad += 0 if ok else 1
    total = len(cases) + len(abstract_cases)
    print(f"自检 {total - bad}/{total} 通过")
    return 0 if bad == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--abstract", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    problems = validate(args.registry)
    if args.draft:
        problems += check_draft(args.registry, args.draft)
    if args.abstract:
        problems += check_abstract(args.registry, args.abstract)
    if problems:
        print(f"FAIL：{len(problems)} 个问题")
        for item in problems:
            print(" !", item)
        return 1
    frame = pd.read_csv(args.registry, encoding="utf-8-sig", keep_default_na=False, dtype=str)
    print(f"OK：{len(frame)} 条 claim 全部回指且与源表复算一致"
          f"（Tier1 {sum(frame.tier == 'Tier1')} / Tier2 {sum(frame.tier == 'Tier2')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
