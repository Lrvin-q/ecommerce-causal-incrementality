"""34 号未显式给 --models 时的按层模型解析（L0/L2 不得含 dr_learner）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load34():
    spec = importlib.util.spec_from_file_location(
        "g34_for_test", ROOT / "scripts" / "34_g_matrix_run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_applicable_models_follow_level_registration():
    module = _load34()
    protocol = module.load_v3_protocol()
    l0 = module._applicable_models(protocol, "L0_P_main")
    l1 = module._applicable_models(protocol, "L1_main")
    l2 = module._applicable_models(protocol, "L2_n200000_p050")
    l3 = module._applicable_models(protocol, "L3_fixed_lt000")
    assert l0 == ("constant", "t_learner", "s_learner", "causal_forest")
    assert l2 == l0
    assert "dr_learner" in l1 and "dr_learner" in l3
    assert "dr_learner" not in l0


def test_applicable_models_for_tier2_cell():
    module = _load34()
    protocol = module.load_v3_protocol()
    names = module._applicable_models(protocol, "L1_heterogeneity_000")
    assert "dr_learner" in names
    assert names == module._applicable_models(protocol, "L1_main")
