"""G02 再训练 bootstrap 的"冻结验证帧"契约。

2026-10-29 10:26 的真实翻车：39 号用 ``validation_observed_hash`` 断言 50 个 b
的验证帧逐字节相同，而该哈希覆盖整张观测表、含由本次打分决定的 ``issued_action``，
跨 b 必然变化——正式跑 4 格在第 2 个 b 全部 RuntimeError。

这里钉住两件事：
1. 与模型无关的两个指纹（用户协变量、随机化臂标签与概率）必须跨历史 rep 稳定；
2. 39 号的守卫只在这两个指纹漂移时响，旧表缺列时必须报错而不是静默退回坏指纹。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from causal_growth.evaluation import v3_g_matrix as g
from causal_growth.v3_config import load_v3_protocol

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "39_g_retrain_bootstrap_run.py"
CORE = "L0_P_main"
N_TINY = 400


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("g02_run_39", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def protocol():
    return load_v3_protocol()


def test_frozen_hashes_stable_across_history_reps(protocol):
    cfg = protocol.scenario(CORE)
    seen = []
    for history_rep in (0, 1):
        dataset, _, _ = g.build_history_dataset(
            cfg, rep_id=history_rep, n=N_TINY, run_id=f"test:g02:guard:{history_rep}"
        )
        fit = g.fit_history_models(
            dataset, cfg, rep_id=history_rep, models=("constant",), time_mode="static"
        )
        out = g.run_validation_arm(
            fit, cfg, rep_id=0, n_validation=N_TINY,
            policy="greedy_incremental_profit_per_cost",
        )
        seen.append((out["validation_frame_hash"], out["validation_arm_hash"]))
    assert seen[0] == seen[1], "验证队列与随机化臂必须与历史 rep 无关"


def test_guard_accepts_same_fingerprints_and_rejects_drift(mod):
    row = {"validation_frame_hash": "frame-a", "validation_arm_hash": "arm-b"}
    mod.check_frozen_validation(CORE, 1, ("frame-a", "arm-b"), row)

    with pytest.raises(RuntimeError, match="validation_frame_hash"):
        mod.check_frozen_validation(CORE, 1, ("frame-x", "arm-b"), row)
    with pytest.raises(RuntimeError, match="validation_arm_hash"):
        mod.check_frozen_validation(CORE, 1, ("frame-a", "arm-y"), row)


def test_resume_refuses_legacy_table_without_frozen_columns(mod):
    legacy = pd.DataFrame([{"b": 0, "validation_observed_hash": "old"}])
    with pytest.raises(SystemExit, match="validation_frame_hash"):
        mod._frozen_seen(legacy, CORE)


def _merge_frame(observed_per_b: bool) -> pd.DataFrame:
    return pd.DataFrame({
        "b": [0, 1],
        "validation_frame_hash": ["frame-a", "frame-a"],
        "validation_arm_hash": ["arm-b", "arm-b"],
        "validation_observed_hash": ["obs-0", "obs-1"] if observed_per_b else ["obs-0", "obs-0"],
    })


def test_merge_accepts_changing_observed_hash(mod):
    mod.check_merge_frame(CORE, _merge_frame(observed_per_b=True))


def test_merge_rejects_drifted_frozen_fingerprints(mod):
    frame = _merge_frame(observed_per_b=True)
    frame.loc[1, "validation_arm_hash"] = "arm-y"
    with pytest.raises(SystemExit, match="validation_arm_hash"):
        mod.check_merge_frame(CORE, frame)


def test_merge_rejects_duplicate_b(mod):
    frame = _merge_frame(observed_per_b=True)
    frame.loc[1, "b"] = 0
    with pytest.raises(SystemExit, match="b 重复"):
        mod.check_merge_frame(CORE, frame)
