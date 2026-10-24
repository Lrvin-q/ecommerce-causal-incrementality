"""Thin entry point for independently sampled Phase B mechanism evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from causal_growth.evaluation.v3_mechanism_checks import run_mechanism_validation


def main() -> int:
    """Build B01/B02 evidence without advancing formal repetition counters."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs" / "v3" / "validation")
    args = parser.parse_args()
    output = run_mechanism_validation(args.output_root)
    print(output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
