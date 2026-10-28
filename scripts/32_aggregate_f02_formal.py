r"""F02 正式重复的 rep 配对聚合入口（按 ``selected_model`` 分层）。

只读 ``out/f02_formal/shard*/rep*/`` 下的六份产物（含 ``manifest.json``），
不触碰 ``data/v3`` 与源码。每一条聚合都打印分母（AGENTS §12.6：跨 rep 聚合前先看组间构成）。

绑定校验（不信任 rep 内自洽）：claim → contrast 用硬映射核对，``diff`` 必须等于
``arm_summary`` 两臂均值差，``n_left/n_right`` 必须等于对应臂 ``n_assigned``，
``manifest`` 的 ``config_hash``/``source_hashes``/``budget``/``n_users`` 必须全 rep 一致。

缺 rep 或 rep 目录缺件时**默认失败**：``--allow-incomplete`` 只用于等待期诊断，
用它跑出来的数字不得进正文。

用法::

    $env:PYTHONUTF8='1'
    .\.venv\Scripts\python.exe scripts_aggregate_f02_formal.py `
        --root out/f02_formal --expect-reps 200 `
        --out-prefix out/scratch/f02_agg
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[1]
SHARDS = (0, 1, 2, 3)
REQUIRED = ("manifest.json", "freeze.json", "decision.csv", "guardrail.csv",
            "arm_summary.csv", "itt_contrasts.csv")
GUARD_METRIC = "any_refund_30d_per_assigned_user"
ARMS = ("no_coupon", "random_same_budget", "selected_targeted_policy")
TARGETED = "selected_targeted_policy"
RANDOM = "random_same_budget"
CONTROL = "no_coupon"
# claim -> decision.csv 的 contrast / configured_contrast（方向不可反）
HARD_MAP = {
    "coupon_worth_issuing": (f"{TARGETED}_minus_{CONTROL}", "selected_targeted_minus_no_coupon"),
    "targeting_better_than_random": (f"{TARGETED}_minus_{RANDOM}", "selected_targeted_minus_same_budget_random"),
}
CLAIMS = tuple(HARD_MAP)


def fail(msg: str, code: int = 2) -> None:
    print(f"FAIL[{code}] {msg}", file=sys.stderr)
    raise SystemExit(code)


def read_rep(rep_dir: Path, rid: int) -> dict:
    manifest = json.loads((rep_dir / "manifest.json").read_text(encoding="utf-8"))
    freeze = json.loads((rep_dir / "freeze.json").read_text(encoding="utf-8"))
    dec = pd.read_csv(rep_dir / "decision.csv", encoding="utf-8-sig")
    grd = pd.read_csv(rep_dir / "guardrail.csv", encoding="utf-8-sig")
    arm = pd.read_csv(rep_dir / "arm_summary.csv", encoding="utf-8-sig")
    itt = pd.read_csv(rep_dir / "itt_contrasts.csv", encoding="utf-8-sig")

    if manifest.get("rep_id") != rid:
        fail(f"{rep_dir}: rep_id 不一致 manifest={manifest.get('rep_id')} dir={rid}", 4)
    if manifest.get("status") != "formal" or not manifest.get("formal_approval"):
        fail(f"{rep_dir}: status/approval={manifest.get('status')!r}/{manifest.get('formal_approval')!r}", 4)
    if manifest.get("scenario") != "L1_main":
        fail(f"{rep_dir}: scenario={manifest.get('scenario')!r}", 4)
    if freeze.get("truth_columns_present") is not False:
        fail(f"{rep_dir}: truth_columns_present={freeze.get('truth_columns_present')!r}", 5)
    if manifest.get("selected_model") != freeze.get("selected_model") or \
            manifest.get("selected_policy") != freeze.get("selected_policy"):
        fail(f"{rep_dir}: manifest 与 freeze 的选模/选策略不一致", 4)

    a = arm.set_index("arm")
    if sorted(a.index) != sorted(ARMS):
        fail(f"{rep_dir}: arms={sorted(a.index)}", 4)
    n_total = int(a["n_assigned"].sum())
    if n_total != int(manifest["n_users"]):
        fail(f"{rep_dir}: 三臂 n_assigned 合计 {n_total} != manifest n_users {manifest['n_users']}", 4)

    # manifest 的每臂人数/发券数必须与 arm_summary 一致；成本与预测支出是两回事，各自记录
    for arm_name in (TARGETED, RANDOM):
        m_arm = manifest["arms"][arm_name]
        if int(m_arm["n_assigned"]) != int(a.loc[arm_name, "n_assigned"]) or \
                int(m_arm["n_issued"]) != int(a.loc[arm_name, "n_issued"]):
            fail(f"{rep_dir}: {arm_name} manifest 与 arm_summary 的人数/发券数不一致", 4)

    # claim -> contrast 硬映射 + decision/itt 一致 + 与 arm 均值差一致
    if sorted(dec["claim"]) != sorted(CLAIMS) or dec["claim"].duplicated().any():
        fail(f"{rep_dir}: claims={sorted(dec['claim'])}", 4)
    d = dec.set_index("claim")
    itt_i = itt.set_index("contrast")
    for claim, (want_contrast, want_configured) in HARD_MAP.items():
        row = d.loc[claim]
        if row["contrast"] != want_contrast:
            fail(f"{rep_dir}: {claim} 的 contrast={row['contrast']!r}，期望 {want_contrast!r}", 4)
        if row["configured_contrast"] != want_configured:
            fail(f"{rep_dir}: {claim} 的 configured_contrast={row['configured_contrast']!r}，期望 {want_configured!r}", 4)
        if want_contrast not in itt_i.index:
            fail(f"{rep_dir}: itt_contrasts 缺 {want_contrast}", 4)
        v = float(itt_i.loc[want_contrast, "diff_cny_per_user"])
        if abs(v - float(row["diff_cny_per_user"])) > 1e-9:
            fail(f"{rep_dir}: itt diff {v} != decision diff {row['diff_cny_per_user']} for {claim}", 4)
        if int(row["n_left"]) != int(a.loc[TARGETED, "n_assigned"]):
            fail(f"{rep_dir}: {claim} n_left={row['n_left']} != targeted n_assigned", 4)
        implied = row["holm_adjusted_p_value"] <= row["adjusted_alpha"]
        if bool(row["passes_adjusted_test"]) != bool(implied):
            fail(f"{rep_dir}: {claim} passes 与 holm p/alpha 矛盾", 4)

    # diff 必须等于两臂均值差（防上游把方向写反但内部自洽）
    mean_net = {k: float(a.loc[k, "mean_net_profit_cny"]) for k in ARMS}
    for claim, right in (("coupon_worth_issuing", CONTROL), ("targeting_better_than_random", RANDOM)):
        want = mean_net[TARGETED] - mean_net[right]
        got = float(d.loc[claim, "diff_cny_per_user"])
        if abs(want - got) > 1e-9:
            fail(f"{rep_dir}: {claim} diff {got} != arm 均值差 {want}（{TARGETED} - {right}）", 4)
        if int(d.loc[claim, "n_right"]) != int(a.loc[right, "n_assigned"]):
            fail(f"{rep_dir}: {claim} n_right != {right} n_assigned", 4)

    if len(grd) != 1 or grd.iloc[0]["metric"] != GUARD_METRIC:
        fail(f"{rep_dir}: guardrail rows={len(grd)} metric={list(grd['metric'])}", 4)
    g = grd.iloc[0]
    rule = manifest["decision_rule"]
    if abs(float(g["margin"]) - float(rule["guardrail_margin"])) > 1e-12:
        fail(f"{rep_dir}: guardrail margin {g['margin']} != manifest {rule['guardrail_margin']}", 4)
    if abs(float(g["alpha_one_sided"]) - float(rule["guardrail_alpha_one_sided"])) > 1e-12:
        fail(f"{rep_dir}: guardrail alpha {g['alpha_one_sided']} != manifest", 4)
    if bool(g["passed"]) != (float(g["ci_one_sided_upper"]) < float(g["margin"])):
        fail(f"{rep_dir}: guardrail passed 与上界/margin 不一致（契约是严格 <）", 4)

    out = {
        "selected_model": freeze["selected_model"],
        "selected_policy": freeze["selected_policy"],
        "config_hash": manifest["config_hash"],
        "source_digest": hashlib.sha256(
            json.dumps(manifest["source_hashes"], sort_keys=True).encode("utf-8")).hexdigest(),
        "budget_per_user": float(manifest["budget_cny_per_user"]),
        "n_users": int(manifest["n_users"]),
        "guardrail_margin": float(g["margin"]),
        "guardrail_diff": float(g["diff"]),
        "guardrail_upper": float(g["ci_one_sided_upper"]),
        "guardrail_pass": bool(g["passed"]),
        "spend_targeted": float(a.loc[TARGETED, "total_coupon_cost_cny"]),
        "spend_random": float(a.loc[RANDOM, "total_coupon_cost_cny"]),
        "predicted_per_user_targeted": float(manifest["arms"][TARGETED]["predicted_spend_per_assigned_cny"]),
        "predicted_per_user_random": float(manifest["arms"][RANDOM]["predicted_spend_per_assigned_cny"]),
        "budget_dev_targeted": float(manifest["arms"][TARGETED]["budget_deviation_cny"]),
        "budget_dev_random": float(manifest["arms"][RANDOM]["budget_deviation_cny"]),
    }
    for c in CLAIMS:
        row = d.loc[c]
        out[f"{c}__diff"] = float(row["diff_cny_per_user"])
        out[f"{c}__se"] = float(row["se"])
        out[f"{c}__p_holm"] = float(row["holm_adjusted_p_value"])
        out[f"{c}__alpha"] = float(row["adjusted_alpha"])
        out[f"{c}__lower"] = float(row["adjusted_lower_confidence_limit"])
        out[f"{c}__pass"] = bool(row["passes_adjusted_test"])
    for arm_name in ARMS:
        out[f"mean_net_{arm_name}"] = mean_net[arm_name]
        out[f"n_assigned_{arm_name}"] = int(a.loc[arm_name, "n_assigned"])
        out[f"n_issued_{arm_name}"] = int(a.loc[arm_name, "n_issued"])
    return out


def mc_summary(values: list[float]) -> dict:
    r = len(values)
    mean = sum(values) / r
    if r < 2:
        return {"R": r, "mean": mean, "sd": float("nan"), "mc_se": float("nan"),
                "ci95_low": float("nan"), "ci95_high": float("nan"), "ci_halfwidth": float("nan")}
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (r - 1))
    se = sd / math.sqrt(r)
    crit = float(student_t.ppf(0.975, r - 1))  # R 小（分层后 5）时 1.96 会低估约 29%
    return {"R": r, "mean": mean, "sd": sd, "mc_se": se,
            "ci95_low": mean - crit * se, "ci95_high": mean + crit * se,
            "ci_halfwidth": crit * se, "t_crit": crit}


def describe(df: pd.DataFrame, label: str, lines: list[str]) -> None:
    lines.append(f"\n## {label}：R={len(df)}")
    for c in CLAIMS:
        s = mc_summary(df[f"{c}__diff"].tolist())
        k = int(df[f"{c}__pass"].sum())
        p_mean = df[f"{c}__p_holm"].mean()
        p_med = df[f"{c}__p_holm"].median()
        lines.append(
            f"- {c}: pass {k}/{len(df)} = {k / len(df):.4f}；mean diff {s['mean']:.6f} 元/人"
            f"（sd {s['sd']:.6f}、MC_SE {s['mc_se']:.6f}、t95%CI [{s['ci95_low']:.6f}, {s['ci95_high']:.6f}]）；"
            f"Holm p 均值 {p_mean:.6g} / 中位 {p_med:.6g}"
        )
    k = int(df["guardrail_pass"].sum())
    s = mc_summary(df["guardrail_diff"].tolist())
    margin = float(df["guardrail_margin"].unique()[0])
    lines.append(f"- guardrail(pass {k}/{len(df)})：mean diff {s['mean']:.6f}（MC_SE {s['mc_se']:.6f}）、"
                 f"max upper {df['guardrail_upper'].max():.6f}（margin {margin}，判定为严格上界 < margin）")
    k = int((df[[f"{c}__pass" for c in CLAIMS]].all(axis=1) & df["guardrail_pass"]).sum())
    lines.append(f"- 三项同时通过：{k}/{len(df)}")
    for arm_name in ARMS:
        n = df[f"n_assigned_{arm_name}"].sum()
        net = (df[f"mean_net_{arm_name}"] * df[f"n_assigned_{arm_name}"]).sum() / n
        lines.append(f"- arm {arm_name}: n_assigned 合计 {int(n):,}、按人数加权 mean net {net:.6f} 元/人")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "out" / "f02_formal"))
    ap.add_argument("--expect-reps", type=int, default=200)
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--out-prefix", default=str(ROOT / "out" / "scratch" / "f02_agg"))
    args = ap.parse_args()

    root = Path(args.root)
    reps: dict[int, Path] = {}
    skipped: list[str] = []
    for shard in SHARDS:
        for d in sorted((root / f"shard{shard}").glob("rep*")):
            suffix = d.name[3:]
            if not suffix.isdigit():
                fail(f"{d}: 目录名 {d.name!r} 不是 rep<数字>，拒绝静默跳过（AGENTS §12.7）", 3)
            rid = int(suffix)
            missing = [f for f in REQUIRED if not (d / f).exists()]
            if missing:
                skipped.append(f"shard{shard}/{d.name} missing={missing}")
                continue
            if rid in reps:
                fail(f"rep {rid} 同时出现在 {reps[rid]} 与 {d}", 3)
            reps[rid] = d
    if skipped and not args.allow_incomplete:
        fail("存在不完整的 rep 目录：" + "; ".join(skipped), 2)

    rows = []
    for rid in sorted(reps):
        rec = read_rep(reps[rid], rid)
        rec["rep"] = rid
        rows.append(rec)
    df = pd.DataFrame(rows).set_index("rep")

    # rep 间绑定一致性（不信任单 rep 内部自洽）
    for col in ("config_hash", "source_digest", "budget_per_user", "n_users", "selected_policy",
                "guardrail_margin"):
        vals = sorted(df[col].unique())
        if len(vals) != 1:
            fail(f"{col} 在 rep 间不唯一：{vals[:4]}", 4)
    if df["selected_model"].isna().any():
        fail(f"selected_model 存在 NaN：rep {df.index[df['selected_model'].isna()].tolist()}", 4)
    n_models = sum(len(g) for _, g in df.groupby("selected_model"))
    if n_models != len(df):
        fail(f"分层后 rep 数 {n_models} != 总 rep 数 {len(df)}（groupby 掉行）", 4)

    from causal_growth.v3_config import load_v3_protocol
    proto = load_v3_protocol()
    cfg = proto.scenario("L1_main")
    budget_cfg = float(cfg.require("evaluation.independent_validation.primary_budget_cny_per_user"))
    budget_run = float(df["budget_per_user"].iloc[0])
    if abs(budget_cfg - budget_run) > 1e-12:
        fail(f"运行期预算 {budget_run} != 当前配置 {budget_cfg}（配置被改过？）", 4)

    df["budget_targeted"] = budget_run * df[f"n_assigned_{TARGETED}"]
    df["budget_random"] = budget_run * df[f"n_assigned_{RANDOM}"]
    df["ratio_targeted"] = df["spend_targeted"] / df["budget_targeted"]
    df["ratio_random"] = df["spend_random"] / df["budget_random"]
    if (df[["ratio_targeted", "ratio_random"]] < 0).any().any():
        fail("出现负支出比", 4)

    missing = sorted(set(range(args.expect_reps)) - set(df.index))
    # 缺 rep 与"目录存在但缺件"是两种不完整；正式聚合两者都必须失败，否则会把 118/200 当正式结果印出来
    if missing and not args.allow_incomplete:
        fail(f"缺 {len(missing)}/{args.expect_reps} 个 rep（前几个 {missing[:5]}）；"
             f"未集齐不得当正式结果聚合（--allow-incomplete 仅供诊断）", 2)
    lines = [f"F02 rep 配对聚合（只读 {root}）",
             f"policy={df['selected_policy'].iloc[0]}；rep 数 {len(df)}；"
             f"config_hash={df['config_hash'].iloc[0][:16]}…；"
             f"缺 rep（0..{args.expect_reps - 1}）共 {len(missing)} 个"
             + (f"：{missing[:10]}{'…' if len(missing) > 10 else ''}" if missing else "（无）")
             + (f"；跳过未完成 {len(skipped)}" if skipped else "")]
    if skipped:
        lines += [f"  skip: {s}" for s in skipped]
    describe(df, "全体（按选模频率加权的混合量，仅供对照）", lines)
    for model, g in df.groupby("selected_model"):
        describe(g, f"selected_model={model}", lines)
    lines.append(f"\n## 每人期望预算 {budget_run} 元 × 各臂分配人数；三臂合计 n_users = {int(df['n_users'].iloc[0]):,}（R={len(df)}）")
    for arm_name, ratio_col, pred_col, dev_col in (
            (TARGETED, "ratio_targeted", "predicted_per_user_targeted", "budget_dev_targeted"),
            (RANDOM, "ratio_random", "predicted_per_user_random", "budget_dev_random")):
        r = df[ratio_col]
        q = r.quantile([0.05, 0.5, 0.95])
        lines.append(
            f"- {arm_name} 真实支出/期望预算：mean {r.mean():.4f}、min {r.min():.4f}、max {r.max():.4f}、"
            f"p05/p50/p95 {q.iloc[0]:.4f}/{q.iloc[1]:.4f}/{q.iloc[2]:.4f}；"
            f">1.0 的 rep {int((r > 1.0).sum())}/{len(df)}、>1.25 {int((r > 1.25).sum())}/{len(df)}")
        lines.append(
            f"- {arm_name} 冻结时刻的预测支出/人：max {df[pred_col].max():.6f}；"
            f"预算偏差 max |dev| {df[dev_col].abs().max():.6f} 元（合计口径，非每人）")
    for model, g in df.groupby("selected_model"):
        lines.append(f"- 按 selected_model={model}（R={len(g)}）：定向支出比 mean {g['ratio_targeted'].mean():.4f}"
                     f"（>1.0 {int((g['ratio_targeted'] > 1.0).sum())}/{len(g)}）、随机支出比 mean {g['ratio_random'].mean():.4f}"
                     f"（>1.0 {int((g['ratio_random'] > 1.0).sum())}/{len(g)}）")

    print("\n".join(lines))

    Path(f"{args.out_prefix}_by_rep.csv").parent.mkdir(parents=True, exist_ok=True)
    df.reset_index().to_csv(f"{args.out_prefix}_by_rep.csv", index=False, encoding="utf-8-sig")

    by_model = []
    for model, g in df.groupby("selected_model"):
        rec = {"selected_model": model, "R": len(g)}
        for c in CLAIMS:
            s = mc_summary(g[f"{c}__diff"].tolist())
            rec[f"{c}__pass"] = int(g[f"{c}__pass"].sum())
            rec[f"{c}__pass_rate"] = float(g[f"{c}__pass"].mean())
            rec[f"{c}__mean_diff"] = s["mean"]
            rec[f"{c}__mc_se"] = s["mc_se"]
            rec[f"{c}__ci95_low"] = s["ci95_low"]
            rec[f"{c}__ci95_high"] = s["ci95_high"]
        rec["guardrail_pass"] = int(g["guardrail_pass"].sum())
        rec["guardrail_max_upper"] = float(g["guardrail_upper"].max())
        rec["all_three_pass"] = int((g[[f"{c}__pass" for c in CLAIMS]].all(axis=1) & g["guardrail_pass"]).sum())
        rec["ratio_targeted_mean"] = float(g["ratio_targeted"].mean())
        rec["ratio_random_mean"] = float(g["ratio_random"].mean())
        by_model.append(rec)
    pd.DataFrame(by_model).to_csv(f"{args.out_prefix}_by_model.csv", index=False, encoding="utf-8-sig")

    summary = {"root": str(root), "policy": df["selected_policy"].iloc[0], "R": len(df),
               "config_hash": df["config_hash"].iloc[0], "source_digest": df["source_digest"].iloc[0],
               "budget_per_user": budget_run, "n_users_per_rep": int(df["n_users"].iloc[0]),
               "models": {m: int(n) for m, n in df["selected_model"].value_counts().items()},
               "missing_reps": missing, "skipped": skipped,
               "by_claim": {c: {**mc_summary(df[f"{c}__diff"].tolist()),
                                "pass": int(df[f"{c}__pass"].sum())} for c in CLAIMS},
               "guardrail": {**mc_summary(df["guardrail_diff"].tolist()),
                             "pass": int(df["guardrail_pass"].sum()),
                             "max_upper": float(df["guardrail_upper"].max()),
                             "margin": float(df["guardrail_margin"].iloc[0])},
               "by_model": by_model}
    Path(f"{args.out_prefix}_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
