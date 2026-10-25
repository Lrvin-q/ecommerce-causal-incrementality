"""Build one versioned engineering five-table run; formal repetition counts stay zero."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from causal_growth.data.v3_pipeline import build_observed_pipeline
from causal_growth.dgp.v3_archive import archive_sealed_population
from causal_growth.dgp.v3_engine import generate_v3_population
from causal_growth.v3_config import load_v3_protocol
from causal_growth.v3_data_config import load_v3_data_config


def main() -> None:
    """Orchestrate a named scenario without interpreting a power template as a mechanism."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--rep", type=int, default=0)
    parser.add_argument("--n", type=int, help="Engineering sample size; default is the registered scenario N")
    parser.add_argument("--sqlite", action="store_true", help="Retain the full representative SQLite database")
    args = parser.parse_args()
    protocol = load_v3_protocol()
    cfg = protocol.scenario(args.scenario)
    if cfg.require("design.local_power.active_mde_multiplier") is not None:
        parser.error("Power templates need independent Phase D MDE calibration before generation")
    root = Path(__file__).resolve().parents[1]
    namespace = load_v3_data_config().require("io.engineering_namespace")
    attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    relative = Path(namespace) / args.scenario / f"rep_{args.rep}" / attempt
    population = generate_v3_population(cfg, rep_id=args.rep, n=args.n)
    result = build_observed_pipeline(*population.observation_bundle(), cfg,
                                    directory=root / "data" / "v3" / relative,
                                    run_id=f"{args.scenario}:history:{args.rep}", rep_id=args.rep,
                                    stream_prefix=population.metadata["stream_prefix"], persist_database=args.sqlite)
    sealed = archive_sealed_population(population, cfg, directory=root / "audit" / "v3" / relative,
                                       observed_manifest=result.manifest_path)
    print(f"合成数据 / 已知 DGP；工程产物；正式 R=0\n观测：{result.manifest_path}\n封存审计：{sealed}")


if __name__ == "__main__":
    main()
