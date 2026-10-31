"""把证据子目录里的"身份类"登记文件提升进顶层 outputs/evidence/coverage.json。

为什么需要这个脚本（2026-10-28 04:16，北京时间）
------------------------------------------------
顶层索引原本只被 20/24/31 号脚本刷新，27 号（D03 正式）与 30 号（F02 正式）
只写自己目录级 coverage.json，于是：

    outputs/evidence/d03_formal/        有 snapshot_binding.json + run_manifest.json，顶层 0 条
    outputs/evidence/f02_n200k_rep0/    有 freeze/manifest/decision，顶层 0 条

AGENTS §12.1 的验收口径是"只用 outputs/evidence/ 就能重建文档里的关键数字"，
而评审者的入口是顶层索引；索引里没有 D03 正式的源码绑定，等于该证据不可发现。

提升规则（可陈述、可复算，不逐个手挑）
------------------------------------
只提升**身份类 JSON**：文件名匹配 `*binding*.json` / `*manifest*.json` /
`freeze.json` / `meta*.json` / `decision.json`。
不提升 CSV、日志、逐用户帧、以及 D03 那 4 个 135 KB 的 shard summary——
它们由各目录级 coverage.json 负责（顶层 purpose 与 31 号脚本 docstring 的既有约定）。

三道校验（只准加强，不准削弱；AGENTS §12.3）
------------------------------------------
1. 提升前对每个候选文件**重算 sha256 与 bytes**，与目录级 coverage.json 记录不符就抛错，
   不允许拿过期的目录级哈希充当登记依据；
2. 提升后对顶层**全表**逐条复算（不只校验本次新增），任何缺失/不符都抛错；
3. 变更写进 `registry_repairs`（追加，不覆盖历史），含 records/total_bytes 前后值与理由。

目录级 coverage.json 有**四种**历史 schema（files 列表带 target / records 列表带 target /
files 字典 / files 列表带 path），全部由 `_normalize_dir_files` 吃下；读不懂的记录一律进
失败清单并**硬失败**，不静默跳过。另有一条反向校验：磁盘上存在、目录级索引却没登记的
身份类 JSON 也算失败——否则"少提升几条"不会有任何声响。

用法
----
默认（扫全部证据子目录，提升进真登记表）::

    .venv/Scripts/python.exe scripts/33_register_evidence_top.py --dry-run
    .venv/Scripts/python.exe scripts/33_register_evidence_top.py

F02 正式合并后::

    .venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs f02_formal --dry-run
    .venv/Scripts/python.exe scripts/33_register_evidence_top.py --dirs f02_formal

演练（夹具在 out/ 下，不碰真登记表；--top 必须同时指向副本）::

    .venv/Scripts/python.exe out/scratch/fixture_f02_formal_shape.py            # 正例
    .venv/Scripts/python.exe out/scratch/fixture_f02_formal_shape.py --break-index  # 反例
    .venv/Scripts/python.exe scripts/33_register_evidence_top.py \
        --evidence-root out/scratch/fixture_ev \
        --top out/scratch/fixture_ev/top_coverage.json --dirs f02_formal

2026-10-28 04:49 的演练结果（6 例全过，夹具已删）
------------------------------------------------
- 正例 dry-run：30 号脚本形状被吃下，提升 4 条（decision/freeze/manifest/five_tables-manifest），
  kind=f02_formal_*、status=formal_r200、note 齐；``aggregate/*.csv`` 与
  ``aggregate/v3_phase_F02_formal_summary.json`` **不**提升（非身份类，符合规则）；
- 正例写盘：既有 41 条与真登记表**逐条相同**（追加式，未重排），41 → 45，
  sum(bytes) == total_bytes；
- 幂等：第二次跑"无新增、无字段补齐，不写盘"；
- 反例 1 磁盘有未登记的身份类 JSON → exit 2；
- 反例 2 三条坏记录（无 target/path、缺 sha256、元素非对象）→ exit 2，按 files[i] 逐条报；
- 反例 3 磁盘文件被篡改 → exit 2，同时打印目录级与磁盘的 sha/bytes；
- 护栏：``--evidence-root`` 指夹具而 ``--top`` 仍是真登记表且非 dry-run → 拒绝写盘。

2026-10-28 11:30 从 ``out/scratch/`` 提入 ``scripts/33_``：``out/`` 不入库（AGENTS §12.1），
放在那里的登记工具对评审者等于不存在。scratch 旧路径改为 exec 本文件的垫片，避免两份实现分叉。
长期形态仍是待做 ⑤（让 27/30 号脚本自带顶层刷新，复用 31 号 ``_refresh_top_registry`` 的口径）。

只写 outputs/evidence/coverage.json 一个文件；不动 src/ configs/ scripts/，
因此与正在运行的 F02 正式 200 rep 无冲突（pipeline_source_hashes() 不覆盖 scripts/，
且 F02 不做 snapshot_vs_live 漂移比对）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import fnmatch
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_EVIDENCE = ROOT / "outputs" / "evidence"
TOP = REAL_EVIDENCE / "coverage.json"

IDENTITY_PATTERNS = (
    "*binding*.json",
    "*manifest*.json",
    "freeze.json",
    "meta*.json",
    "decision.json",
)

# 每个目录的 kind 词汇沿用其目录级 coverage.json；f02_n200k_rep0 的目录级用
# dict（无 kind），这里给出显式 kind，并强制携带 status 以免工程证据被当成正式证据。
DIR_STATUS = {
    "f02_n200k_rep0": "engineering_single_rep_not_formal_evidence",
    "f02_formal": "formal_r200",
}
# 本脚本添加的注记（不是从源产物抄来的字段，所以单列，避免与目录级 coverage.json 混淆）。
# 目的：顶层索引里出现 "d03_formal" 不等于 D03 已证实；出现 rep0 目录不等于正式证据。
DIR_NOTE = {
    "d03_formal": (
        "D03 正式 200 rep 的运行身份文件（源码快照绑定 + run manifest）。"
        "运行已完成并合并，但阶段状态为**未证实**，待独立评审（AGENTS §7.4）；"
        "逐 rep 表与分片 summary 由本目录 coverage.json 登记，顶层只收身份类文件。"
    ),
    "f02_n200k_rep0": (
        "F02 **工程验证**单 rep（n=200 000，R=0）的身份文件，"
        "status=engineering_single_rep_not_formal_evidence，**不是**正式证据；"
        "正式证据在 outputs/evidence/f02_formal/（200 rep，登记号 F02-FORMAL-20261028-R200）。"
    ),
    "f02_formal": (
        "F02 正式 200 rep 的代表 rep 0 证据包与聚合表身份文件"
        "（登记号 F02-FORMAL-20261028-R200）。逐用户观测 per_user.csv 与冻结后生成的"
        "真值文件被 30 号脚本显式排除，排除项与理由见本目录 coverage.json 的 excluded；"
        "运行已完成，但阶段状态为**未证实**，待独立评审（AGENTS §7.4）。"
    ),
}
# 非身份类命名、但按先例必须顶层可发现的证据：**逐条白名单**，不做通配。
# G01 的 runs_summary.json 是 12 个分片权威起止与 failures=[] 的唯一来源
# （manifest 的 started_at_utc 实为完成时刻，评审 P1-2），必须让第三方在顶层找得到。
DIR_EXTRA_IDENTITY = {
    "g01_aa250": {"runs_summary.json": "g01_runs_summary"},
}
DIR_KIND_FALLBACK = {
    "f02_n200k_rep0": {
        "freeze.json": "f02_freeze",
        "manifest.json": "f02_manifest",
        "decision.json": "f02_decision",
        "five_tables/manifest.json": "f02_five_tables_manifest",
    },
    # 30 号脚本（scripts/30_merge_f02_formal.py:158-163）写的 coverage.json 形状是
    # files=[{path, source, sha256, bytes}]：**没有 target、没有 kind**，
    # 所以这里按相对文件名补 kind；相对名与 rep0 工程包同名，故表结构一致。
    "f02_formal": {
        "freeze.json": "f02_formal_freeze",
        "manifest.json": "f02_formal_manifest",
        "decision.json": "f02_formal_decision",
        "five_tables/manifest.json": "f02_formal_five_tables_manifest",
    },
}


# 在既有审计条目里发现的字段缺陷。**不改写历史条目**（那是带时间戳的审计轨迹），
# 只把缺陷登记在本次条目里，让读到 repairs[1] 的人知道哪个字段不可信。
# 证据：out/scratch/fix_evidence_registry.py:100 把 "total_bytes_before": 22788510
# 写成常量、:102 把 reason 写成常量；该脚本于 02:38 与 03:06 各跑一次，于是第二次的
# before 值是第一次的旧值（03:06 的真实前值应为 15 811 356 = repairs[0].total_bytes_after）。
PRIOR_ENTRY_DEFECTS = [
    {
        "entry_index": 1,
        "entry_at": "2026-10-28 03:06",
        "untrustworthy_fields": ["total_bytes_before", "reason"],
        "recorded_value": {"total_bytes_before": 22788510},
        "correct_value": {"total_bytes_before": 15811356},
        "evidence": (
            "out/scratch/fix_evidence_registry.py:100 将 total_bytes_before 硬编码为 22788510、"
            ":102 将 reason 硬编码；该脚本于 02:38 与 03:06 各运行一次，"
            "故 03:06 条目的 before 值实为 02:38 的旧前值。"
            "03:06 的真实前值 = repairs[0].total_bytes_after = 15 811 356；"
            "03:06 的后值 15 811 358 = 15 811 356 + 2（f01_ope/meta.json 17 333 → 17 335 B）。"
            "out/scratch/coverage_backup_before_31patch_20261028_031329.json 佐证 03:13 前"
            "磁盘上 records=35、total_bytes=15 811 358、repairs=2。"
        ),
        "action": "仅登记缺陷，未改写 repairs[1]；其 refreshed/records_before/records_after 字段仍可信",
    }
]


def _now_beijing() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_identity(rel_name: str) -> bool:
    base = rel_name.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(base, pat) for pat in IDENTITY_PATTERNS)


def _root_rel(path: Path) -> str:
    """仓内路径给相对 posix（登记表的 target 一律是这种）；仓外（如临时夹具）退回绝对 posix。"""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _rel_name(target: str, subdir: str, evidence_root: Path) -> str:
    """把目录级记录里的 target 归一成相对该证据目录的 posix 名。

    三种历史写法都要吃下：
      d03_formal        相对 posix，如 outputs/evidence/d03_formal/shard0_summary.json
      e_evidence_rep0_a 相对 posix，同上
      f01_ope           **绝对 Windows 路径**，如 C:\\Users\\...\\outputs\\evidence\\f01_ope\\freeze.json
    """
    base = (evidence_root / subdir).resolve()
    p = Path(target)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(base).as_posix()
        except ValueError:
            return p.name
    posix = p.as_posix()
    for marker in (f"{_root_rel(base.parent)}/{subdir}/", f"{subdir}/"):
        if marker in posix:
            return posix.split(marker, 1)[-1]
    return posix


def _normalize_dir_files(payload: dict, subdir: str, evidence_root: Path
                         ) -> tuple[list[dict], list[str]]:
    """把四种目录级 schema 统一成 [{rel, kind, source, sha256, bytes}]，同时返回问题清单。

    d03_formal        files 是 list，元素含 kind/source/target/bytes/sha256
    e_*/f01_ope       records 是 list，同形状（f01 的 target 是绝对路径）
    f02_n200k_rep0    files 是 dict，键为相对文件名，值含 sha256/bytes，无 kind/source
    f02_formal        files 是 list，元素含 **path**/source/sha256/bytes，无 kind（30 号脚本）

    任何"这条记录读不懂"的情况都进 problems（由调用方硬失败），**不静默跳过**——
    静默跳过会让"提升 0 条"看起来像"这个目录本来就没有身份类文件"（AGENTS §3.6 失败要响）。
    """
    raw = payload.get("files")
    if raw is None:
        raw = payload.get("records")
    kinds = DIR_KIND_FALLBACK.get(subdir, {})
    extra_kinds = DIR_EXTRA_IDENTITY.get(subdir, {})
    out: list[dict] = []
    problems: list[str] = []
    if isinstance(raw, list):
        for i, rec in enumerate(raw):
            if not isinstance(rec, dict):
                problems.append(f"{subdir}: files[{i}] 不是对象，无法解析")
                continue
            if "sha256" not in rec or "bytes" not in rec:
                problems.append(
                    f"{subdir}: files[{i}] 缺 sha256/bytes，无法作为登记依据"
                )
                continue
            if "target" in rec:
                rel = _rel_name(str(rec["target"]), subdir, evidence_root)
            elif "path" in rec:
                rel = str(rec["path"]).replace("\\", "/")
            else:
                problems.append(f"{subdir}: files[{i}] 既无 target 也无 path，无法定位文件")
                continue
            out.append({
                "rel": rel,
                "kind": rec.get("kind") or kinds.get(rel) or extra_kinds.get(rel),
                "source": rec.get("source"),
                "sha256": rec["sha256"],
                "bytes": int(rec["bytes"]),
            })
    elif isinstance(raw, dict):
        for rel, info in raw.items():
            if not isinstance(info, dict) or "sha256" not in info or "bytes" not in info:
                problems.append(f"{subdir}: files[{rel}] 缺 sha256/bytes，无法作为登记依据")
                continue
            out.append({
                "rel": rel,
                "kind": info.get("kind") or kinds.get(rel) or extra_kinds.get(rel),
                "source": info.get("source"),
                "sha256": info["sha256"],
                "bytes": int(info["bytes"]),
            })
    else:
        raise SystemExit(
            f"{subdir}: 目录级 coverage.json 既无 files 也无 records 列表（schema 未知）"
        )
    return out, problems


def collect(subdirs: list[str], evidence_root: Path) -> tuple[list[dict], list[str]]:
    """返回 (待提升记录, 校验失败清单)。"""
    candidates: list[dict] = []
    bad: list[str] = []
    prefix = _root_rel(evidence_root)
    for subdir in subdirs:
        d = evidence_root / subdir
        cov = d / "coverage.json"
        if not cov.is_file():
            bad.append(f"{subdir}: 缺目录级 coverage.json")
            continue
        payload = json.loads(cov.read_text(encoding="utf-8"))
        status = DIR_STATUS.get(subdir) or payload.get("status")
        normalized, problems = _normalize_dir_files(payload, subdir, evidence_root)
        bad.extend(problems)

        # 磁盘上有、目录级索引里没有的身份类 JSON = 索引漏登记，硬失败。
        # 没有这一条，"读不懂的记录"只会让候选数悄悄变少。
        indexed = {rec["rel"] for rec in normalized}
        extra_names = set(DIR_EXTRA_IDENTITY.get(subdir, {}))
        on_disk = sorted(
            rel for rel in (p.relative_to(d).as_posix() for p in d.rglob("*.json"))
            if (_is_identity(rel) or rel in extra_names) and rel not in indexed
        )
        for rel in on_disk:
            bad.append(f"{subdir}/{rel}: 磁盘上存在身份类文件，但目录级 coverage.json 未登记")

        extra_identity = DIR_EXTRA_IDENTITY.get(subdir, {})
        # 全表逐条核 sha/bytes + target 唯一性。只核身份类时，导出器把 264 条分片
        # 写成 48 个同名文件也会全绿（G03 P0-1，2026-10-31 19:44 独立评审）。
        counts: dict[str, int] = {}
        for rec in normalized:
            counts[rec["rel"]] = counts.get(rec["rel"], 0) + 1
        for rel, count in sorted(counts.items()):
            if count > 1:
                bad.append(
                    f"{subdir}/{rel}: 同一 target 被 {count} 条记录登记（命名冲突或索引重复）"
                )
        verified: dict[str, tuple[str, int]] = {}
        for rec in normalized:
            path = d / rec["rel"]
            if not path.is_file():
                bad.append(f"{subdir}/{rec['rel']}: 文件缺失，目录级索引已过期")
                continue
            actual_sha = file_sha256(path)
            actual_bytes = path.stat().st_size
            verified[rec["rel"]] = (actual_sha, actual_bytes)
            if actual_sha != rec["sha256"] or actual_bytes != rec["bytes"]:
                bad.append(
                    f"{subdir}/{rec['rel']}: 磁盘 sha256/bytes 与目录级 coverage.json 不符"
                    f"（目录级 {rec['sha256'][:12]}…/{rec['bytes']} vs "
                    f"磁盘 {actual_sha[:12]}…/{actual_bytes}）"
                )
        for rec in normalized:
            if not _is_identity(rec["rel"]) and rec["rel"] not in extra_identity:
                continue
            if rec["rel"] not in verified:
                continue
            actual_sha, actual_bytes = verified[rec["rel"]]
            kind = rec["kind"]
            if kind is None:
                bad.append(f"{subdir}/{rec['rel']}: 无法确定 kind")
                continue
            entry: dict = {
                "kind": kind,
                "target": f"{prefix}/{subdir}/{rec['rel']}",
                "bytes": actual_bytes,
                "sha256": actual_sha,
            }
            if rec["source"]:
                entry["source"] = rec["source"]
            if status:
                entry["status"] = status
            if subdir in DIR_NOTE:
                entry["note"] = DIR_NOTE[subdir]
            candidates.append(entry)
    return candidates, bad


def verify_whole_table(records: list[dict]) -> list[str]:
    bad: list[str] = []
    for rec in records:
        path = ROOT / str(rec["target"])
        if not path.is_file():
            bad.append(f"{rec['target']}: 文件缺失")
        elif file_sha256(path) != rec["sha256"]:
            bad.append(f"{rec['target']}: sha256 不符")
        elif int(rec["bytes"]) != path.stat().st_size:
            bad.append(f"{rec['target']}: bytes 不符")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="*", default=None,
                    help="要提升的证据子目录名；默认扫描所有含 coverage.json 的子目录")
    ap.add_argument("--evidence-root", default=None,
                    help="证据根目录，默认 outputs/evidence；只在用夹具演练时才改")
    ap.add_argument("--top", default=None,
                    help="顶层登记表路径，默认 outputs/evidence/coverage.json；演练时指向副本")
    ap.add_argument("--dry-run", action="store_true", help="只校验与打印计划，不写盘")
    ap.add_argument("--reason", default=None)
    args = ap.parse_args()

    evidence = (Path(args.evidence_root) if args.evidence_root else REAL_EVIDENCE)
    evidence = evidence if evidence.is_absolute() else ROOT / evidence
    top_path = Path(args.top) if args.top else TOP
    top_path = top_path if top_path.is_absolute() else ROOT / top_path
    if not args.dry_run and top_path == TOP and evidence != REAL_EVIDENCE:
        raise SystemExit(
            "拒绝写盘：--evidence-root 指向夹具而 --top 仍是真登记表，"
            "那会把夹具路径写进 outputs/evidence/coverage.json"
        )
    if args.dirs:
        subdirs = list(args.dirs)
    else:
        subdirs = sorted(p.parent.name for p in evidence.glob("*/coverage.json"))
    print(f"[top-reg] 证据根 {_root_rel(evidence)}；扫描 {len(subdirs)} 个子目录：{', '.join(subdirs)}")

    top = json.loads(top_path.read_text(encoding="utf-8"))
    records: list[dict] = list(top["records"])
    by_target = {str(r["target"]): r for r in records}

    candidates, bad = collect(subdirs, evidence)
    if bad:
        print("[top-reg] 候选校验未过，禁止提升：")
        for line in bad:
            print(f"  - {line}")
        return 2

    added, unchanged = [], []
    for cand in candidates:
        old = by_target.get(cand["target"])
        if old is None:
            added.append(cand)
        elif (old.get("sha256"), int(old.get("bytes", -1))) == (cand["sha256"], cand["bytes"]):
            # 已登记且一致：只补缺失的 status/source，不改哈希
            merged = dict(old)
            for key in ("status", "source", "note"):
                if key in cand and key not in merged:
                    merged[key] = cand[key]
            if merged != old:
                by_target[cand["target"]] = merged
                unchanged.append(f"{cand['target']}（补 {sorted(set(merged) - set(old))}）")
            else:
                unchanged.append(cand["target"])
        else:
            print(f"[top-reg] 已登记但哈希不同，拒绝静默覆盖：{cand['target']}")
            print(f"    顶层 {old.get('sha256')} / {old.get('bytes')}")
            print(f"    磁盘 {cand['sha256']} / {cand['bytes']}")
            return 3

    print(f"[top-reg] 候选身份类文件 {len(candidates)} 个：新增 {len(added)}，已登记 {len(unchanged)}")
    for rec in added:
        print(f"    + {rec['kind']:28s} {rec['target']}  {rec['bytes']} B")
    for line in unchanged:
        print(f"    = {line}")

    merged_records = list(by_target.values()) + added
    # **不排序**：顶层表原本是插入序（aa/negctl/local_power/bindings/…），按 target 排序会
    # 重排 32/35 条既有记录，把"新增 6 条"变成 217/139 行的 diff，评审者无法一眼确认
    # "其余记录未被动过"。追加到末尾才能让 diff 纯增量。

    whole_bad = verify_whole_table(merged_records)
    if whole_bad:
        print("[top-reg] 顶层全表复算未过（改登记表必须全表复算）：")
        for line in whole_bad:
            print(f"  - {line}")
        return 4
    print(f"[top-reg] 顶层全表复算一致：{len(merged_records)} 条")

    new_total = sum(int(r["bytes"]) for r in merged_records)
    reason = args.reason or (
        "27 号（D03 正式）与 30 号（F02 正式）脚本只写目录级 coverage.json、不刷顶层索引，"
        "导致 d03_formal / f02_n200k_rep0 的源码绑定与冻结清单在顶层不可发现（AGENTS §12.1）。"
        "按身份类 JSON 规则提升，提升前逐文件重算 sha256/bytes，提升后全表复算。"
    )
    repair = {
        "at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
        "dropped_missing_target": [],
        "added": [r["target"] for r in added],
        "enriched": unchanged,
        "records_before": len(records),
        "records_after": len(merged_records),
        "total_bytes_before": top.get("total_bytes"),
        "total_bytes_after": new_total,
        "identity_patterns": list(IDENTITY_PATTERNS),
        "extra_identity": {k: sorted(v) for k, v in DIR_EXTRA_IDENTITY.items()},
        "ordering_policy": "append_only_preserve_existing_order",
        "prior_entry_defects": PRIOR_ENTRY_DEFECTS,
        "reason": reason,
    }

    # before 值一律**现读现算**，不写常量：fix_evidence_registry.py 把 before 硬编码，
    # 重跑一次就在审计轨迹里留下一条假的前值（见 PRIOR_ENTRY_DEFECTS）。
    actual_before = sum(int(r["bytes"]) for r in records)
    if actual_before != top.get("total_bytes"):
        raise SystemExit(
            f"顶层 total_bytes 字段 {top.get('total_bytes')} 与逐条求和 {actual_before} 不符，"
            "先查清登记表再动它"
        )

    if not added and all("（补" not in u for u in unchanged):
        print("[top-reg] 无新增、无字段补齐，不写盘（幂等）")
        return 0

    if args.dry_run:
        print("[top-reg] DRY-RUN：不写盘。计划变更如下")
        print(json.dumps({k: v for k, v in repair.items() if k != "reason"},
                         ensure_ascii=False, indent=2))
        return 0

    top["records"] = merged_records
    top["total_bytes"] = new_total
    top.setdefault("registry_repairs", []).append(repair)
    top["last_refreshed_at"] = _now_beijing()
    top_path.write_text(json.dumps(top, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[top-reg] 写入 {_root_rel(top_path)}")
    print(f"[top-reg] records {repair['records_before']} → {repair['records_after']}，"
          f"total_bytes {repair['total_bytes_before']} → {new_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
