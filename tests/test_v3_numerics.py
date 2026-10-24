"""Numerical accuracy controls cannot silently become invalid."""

from pathlib import Path

import pytest
import yaml

from causal_growth.config import ConfigError
from causal_growth.v3_numerics import load_v3_numerics


@pytest.mark.parametrize("path,value", [
    ("integration.absolute_tolerance", 0),
    ("integration.relative_tolerance", -1),
    ("integration.u_initial_nodes", 1024),
    ("validation.mc_chunk_size", 3000000),
])
def test_numerical_control_rejects_invalid_requests(tmp_path: Path, path: str, value: float) -> None:
    raw = load_v3_numerics().to_dict()
    section, field = path.split(".")
    raw[section][field] = value
    target = tmp_path / "numerics.yaml"
    target.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_v3_numerics(target)
