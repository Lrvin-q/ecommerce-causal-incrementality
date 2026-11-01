"""D03 选模质量的两张表：各模型被选中频率与测试集命中率、选模边际与秩相关。

回答的问题：选模频率能不能当成"哪个模型更好"的证据；验证集上的 DR 分数
与测试集上的误差/偏差是否指向同一件事。只做聚合与秩相关，不改任何估计。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
PER_REP = ROOT / "outputs/tables/v3_phase_D03_formal_per_rep.csv"
OUT_MODEL = ROOT / "outputs/tables/v3_phase_D03_selection_quality.csv"
OUT_MARGIN = ROOT / "outputs/tables/v3_phase_D03_selection_margin.csv"
MARGIN_CUT = 0.005


def main() -> int:
    per_rep = pd.read_csv(PER_REP, encoding="utf-8-sig")
    n_reps = per_rep.rep_id.nunique()
    assert len(per_rep) == n_reps * per_rep.model.nunique(), "per_rep 不是满网格"

    best_rmse = per_rep.groupby("rep_id").rmse.idxmin()
    best_mae = per_rep.groupby("rep_id").mae.idxmin()
    share_best_rmse = per_rep.loc[best_rmse].model.value_counts(normalize=True)
    share_best_mae = per_rep.loc[best_mae].model.value_counts(normalize=True)

    chosen = per_rep[per_rep.chosen]
    summary = per_rep.groupby("model").agg(
        mean_rank=("rank", "mean"),
        median_selection_score=("selection_score", "median"),
        mean_rmse=("rmse", "mean"),
        median_rmse=("rmse", "median"),
        mean_abs_bias=("bias_mean", lambda s: float(np.abs(s).mean())),
    )
    summary["times_chosen"] = chosen.groupby("model").size().reindex(summary.index).fillna(0).astype(int)
    summary["share_chosen"] = summary.times_chosen / n_reps
    summary["share_best_rmse"] = share_best_rmse.reindex(summary.index).fillna(0.0)
    summary["share_best_mae"] = share_best_mae.reindex(summary.index).fillna(0.0)
    summary = summary.reset_index().sort_values("times_chosen", ascending=False)
    assert summary.times_chosen.sum() == n_reps, summary.times_chosen.sum()
    official = pd.read_csv(ROOT / "outputs/tables/v3_phase_D03_formal_selection.csv", encoding="utf-8-sig")
    merged = summary.merge(official, on="model", how="outer", validate="one_to_one")
    assert merged.times_chosen_x.tolist() == merged.times_chosen_y.tolist(), "选中次数与官方表不一致"
    assert np.allclose(merged.mean_rank_x, merged.mean_rank_y, atol=1e-9), "平均名次与官方表不一致"
    summary.to_csv(OUT_MODEL, index=False, encoding="utf-8-sig")
    print(summary.round(4).to_string(index=False))

    margins = []
    spearman_rmse: list[float] = []
    spearman_bias: list[float] = []
    for rep, frame in per_rep.groupby("rep_id"):
        ordered = frame.sort_values("rank")
        scores = ordered.selection_score.to_numpy(dtype=float)
        margins.append(float(scores[0] - scores[1]))
        clean = frame.dropna(subset=["rmse", "bias_mean", "selection_score"])
        if clean.shape[0] >= 3 and clean.selection_score.nunique() > 1:
            spearman_rmse.append(float(spearmanr(clean.selection_score, clean.rmse).statistic))
            spearman_bias.append(
                float(spearmanr(clean.selection_score, clean.bias_mean.abs()).statistic)
            )
    margin = np.asarray(margins, dtype=float)
    hit_rmse = float(
        (per_rep.loc[best_rmse, "model"].to_numpy() == chosen.sort_values("rep_id").model.to_numpy()).mean()
    )
    hit_mae = float(
        (per_rep.loc[best_mae, "model"].to_numpy() == chosen.sort_values("rep_id").model.to_numpy()).mean()
    )
    out = pd.DataFrame([{
        "n_reps": n_reps,
        "margin_mean": float(margin.mean()),
        "margin_q25": float(np.quantile(margin, 0.25)),
        "margin_median": float(np.median(margin)),
        "margin_q75": float(np.quantile(margin, 0.75)),
        "margin_max": float(margin.max()),
        "share_margin_below_cut": float((margin < MARGIN_CUT).mean()),
        "margin_cut": MARGIN_CUT,
        "hit_rate_best_rmse": hit_rmse,
        "hit_rate_best_mae": hit_mae,
        "mean_spearman_score_rmse": float(np.mean(spearman_rmse)),
        "mean_spearman_score_abs_bias": float(np.mean(spearman_bias)),
        "n_spearman": len(spearman_rmse),
    }])
    out.to_csv(OUT_MARGIN, index=False, encoding="utf-8-sig")
    print(out.round(4).T.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
