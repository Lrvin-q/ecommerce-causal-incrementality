"""``scripts/32_aggregate_f02_formal.py`` 的反例夹具（AGENTS §12.7）。

新写的校验器必须自带反例，并当场跑一遍证明它真的会拦。夹具直接复制本机
``out/f02_formal/shard0/rep{0,1}`` 的真实产物，不手抄 CSV 表头——手抄的夹具
在产物 schema 改动后会继续演旧戏（§12.7 的教训）。

``out/`` 不入库，所以在没有现场产物的机器上整组跳过；跳过时打印原因，
不允许静默变成"0 项通过"。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "32_aggregate_f02_formal.py"
LIVE = ROOT / "out" / "f02_formal" / "shard0"
FILES = ("manifest.json", "freeze.json", "decision.csv", "guardrail.csv",
         "arm_summary.csv", "itt_contrasts.csv")


def _live_ready() -> bool:
    return all((LIVE / f"rep{rep}" / f).exists() for rep in (0, 1) for f in FILES)


def build_tree(tmp_path: Path) -> Path:
    """把两个真实 rep 复制成一份可篡改的聚合根。"""
    if not _live_ready():
        pytest.skip(f"缺少本机现场产物 {LIVE}/rep{{0,1}}（out/ 不入库），无法构造夹具")
    root = tmp_path / "root"
    for rep in (0, 1):
        shutil.copytree(LIVE / f"rep{rep}", root / "shard0" / f"rep{rep}")
    return root


def run(root: Path, out_prefix: Path, expect: int = 2, allow_incomplete: bool = False):
    cmd = [sys.executable, str(SCRIPT), "--root", str(root), "--expect-reps", str(expect),
           "--out-prefix", str(out_prefix)]
    if allow_incomplete:
        cmd.append("--allow-incomplete")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT), env=env)


def _edit_csv(path: Path, mutate) -> None:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = mutate(df)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _edit_json(path: Path, mutate) -> None:
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec = mutate(rec)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")


def test_accepts_untampered_tree(tmp_path):
    """正例：未篡改的 2 个 rep 必须 exit 0，且三份产物齐全、分层 R 之和等于总 R。"""
    root = build_tree(tmp_path)
    out = tmp_path / "agg"
    p = run(root, out)
    assert p.returncode == 0, p.stderr[-3000:]
    by_rep = pd.read_csv(Path(f"{out}_by_rep.csv"), encoding="utf-8-sig")
    by_model = pd.read_csv(Path(f"{out}_by_model.csv"), encoding="utf-8-sig")
    summary = json.loads(Path(f"{out}_summary.json").read_text(encoding="utf-8"))
    assert len(by_rep) == 2 and summary["R"] == 2
    assert int(by_model["R"].sum()) == 2 == sum(summary["models"].values())
    assert summary["missing_reps"] == []


def test_rejects_swapped_claim_contrast(tmp_path):
    """claim 与 contrast 互换：两个名字都还在，但映射错了，必须失败。"""
    root = build_tree(tmp_path)
    _edit_csv(root / "shard0" / "rep0" / "decision.csv",
              lambda d: d.assign(contrast=d["contrast"].iloc[::-1].to_numpy()))
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "contrast" in p.stderr


def test_rejects_itt_diff_mismatch(tmp_path):
    """decision 与 itt 逐值必须一致（§12.6 同一 rep 同一预算）。"""
    root = build_tree(tmp_path)
    _edit_csv(root / "shard0" / "rep1" / "itt_contrasts.csv",
              lambda d: d.assign(diff_cny_per_user=d["diff_cny_per_user"] + 1e-3))
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "itt" in p.stderr


def test_rejects_arm_mean_inconsistency(tmp_path):
    """diff 必须等于两臂均值差：改臂均值而不改 diff，必须失败。"""
    root = build_tree(tmp_path)
    _edit_csv(root / "shard0" / "rep0" / "arm_summary.csv",
              lambda d: d.assign(mean_net_profit_cny=d["mean_net_profit_cny"]
                                 + d["arm"].eq("selected_targeted_policy") * 0.01))
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "均值差" in p.stderr


def test_rejects_run_budget_drift(tmp_path):
    """预算分母取自每个 rep 的 manifest：两个 rep 一起改成 0.3 仍必须被当前配置挡住。"""
    root = build_tree(tmp_path)
    for rep in (0, 1):
        _edit_json(root / "shard0" / f"rep{rep}" / "manifest.json",
                   lambda r: {**r, "budget_cny_per_user": 0.3})
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "预算" in p.stderr


def test_rejects_missing_rep_id(tmp_path):
    """manifest 是作业身份的唯一权威，缺 rep_id 不得默认等于目录名。"""
    root = build_tree(tmp_path)
    _edit_json(root / "shard0" / "rep1" / "manifest.json",
               lambda r: {k: v for k, v in r.items() if k != "rep_id"})
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "rep_id" in p.stderr


def test_rejects_guardrail_pass_inconsistent(tmp_path):
    """护栏契约是严格上界 < margin；passed 与上界矛盾必须失败。"""
    root = build_tree(tmp_path)
    _edit_csv(root / "shard0" / "rep0" / "guardrail.csv",
              lambda d: d.assign(ci_one_sided_upper=0.0099, passed=True))
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "guardrail" in p.stderr or "护栏" in p.stderr


def test_rejects_truth_columns_present(tmp_path):
    """冻结时真值列必须不存在；出现即证据链断裂。"""
    root = build_tree(tmp_path)
    _edit_json(root / "shard0" / "rep0" / "freeze.json",
               lambda r: {**r, "truth_columns_present": True})
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "truth" in p.stderr


def test_rejects_nan_selected_model(tmp_path):
    """selected_model 为 null 会让 groupby 静默丢 rep，必须先失败。"""
    root = build_tree(tmp_path)
    for rep in (0, 1):
        for name in ("manifest.json", "freeze.json"):
            _edit_json(root / "shard0" / f"rep{rep}" / name,
                       lambda r: {**r, "selected_model": None})
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "NaN" in p.stderr or "selected_model" in p.stderr


def test_rejects_incomplete_tree_without_flag(tmp_path):
    """缺 rep 默认失败：否则会把 1/2 当正式结果印出来；带 --allow-incomplete 才放行。"""
    root = build_tree(tmp_path)
    shutil.rmtree(root / "shard0" / "rep1")
    strict = run(root, tmp_path / "agg_strict")
    assert strict.returncode != 0
    assert "缺" in strict.stderr
    relaxed = run(root, tmp_path / "agg_relaxed", allow_incomplete=True)
    assert relaxed.returncode == 0, relaxed.stderr[-2000:]


def test_rejects_missing_required_file(tmp_path):
    """目录存在但缺件（缺 itt_contrasts.csv）也不得静默当作完整 rep。"""
    root = build_tree(tmp_path)
    (root / "shard0" / "rep1" / "itt_contrasts.csv").unlink()
    p = run(root, tmp_path / "agg")
    assert p.returncode != 0
    assert "不完整" in p.stderr
