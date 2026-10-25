"""Execute Phase C data engineering checks without claiming formal repetitions."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.evaluation.v3_data_checks import run_data_validation


def main() -> int:
    """Run a declared engineering scope; formal n/R remain frozen and uncompleted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["smoke", "matrix", "representatives", "validation", "power", "all"], default="smoke")
    parser.add_argument("--scenario", action="append", dest="scenarios", help="Registered full scenario ID; repeat to select several")
    parser.add_argument("--resume", action="store_true", help="Reuse only source/config/artifact-matched passed receipts")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/v3/data_validation")
    args = parser.parse_args()
    output = run_data_validation(args.output_root, scope=args.scope, resume=args.resume, scenario_ids=args.scenarios)
    print(output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
