"""Numerical controls for the v3 mechanism, separate from the approved business matrix."""

from pathlib import Path

from causal_growth.config import Config, ConfigError
from causal_growth.v3_config import _UniqueKeyLoader
import yaml


def load_v3_numerics(path: str | Path | None = None) -> Config:
    """Load the accuracy and resource controls used to verify Phase B truth calculations.

    These controls do not replace the seven-file Phase A experiment protocol. Both
    hashes must be recorded by subsequent experiment manifests.
    """
    source = Path(path) if path is not None else Path(__file__).resolve().parents[2] / "configs" / "v3_numerics.yaml"
    raw = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(raw, dict):
        raise ConfigError("v3 numerical controls must be a mapping")
    cfg = Config(raw, name="v3_numerics")
    for name in ("absolute_tolerance", "relative_tolerance", "quad_epsabs", "quad_epsrel"):
        if not 0 < float(cfg.require(f"integration.{name}")) < 1:
            raise ConfigError(f"invalid numerical tolerance {name}")
    if int(cfg.require("integration.u_initial_nodes")) > int(cfg.require("integration.u_max_nodes")):
        raise ConfigError("initial quadrature order exceeds maximum")
    if int(cfg.require("validation.mc_chunk_size")) > int(cfg.require("validation.independent_mc_n")):
        raise ConfigError("MC chunk size exceeds total")
    return cfg
