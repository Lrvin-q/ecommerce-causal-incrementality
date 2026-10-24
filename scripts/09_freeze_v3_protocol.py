"""Validate and export the v3 protocol; this command runs no experiments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from causal_growth.v3_config import load_v3_protocol, planned_counts, protocol_rows

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Make the Phase A plan reviewable, with no fabricated result or MC error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, default=ROOT / "configs" / "v3")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "v3" / "protocol")
    args = parser.parse_args()
    protocol = load_v3_protocol(args.config_root)
    data = protocol.config.to_dict()
    rows = protocol_rows(protocol)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "experiment_matrix.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    doc = ROOT / "docs" / "v3_协议.md"
    record = {
        "data_source": data["project"]["data_source_label"],
        "status": data["execution"]["config_status"],
        "config_hash": protocol.config_hash,
        "source_sha256": protocol.source_hashes,
        "protocol_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
        "parameter_rationale_sha256": hashlib.sha256((ROOT / "docs" / "v3_参数依据.md").read_bytes()).hexdigest(),
        "planned_counts": planned_counts(data),
        "experiment_results_exist": False,
    }
    (args.output / "protocol_manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "protocol_validated", "config_hash": protocol.config_hash, "planned_counts": record["planned_counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
