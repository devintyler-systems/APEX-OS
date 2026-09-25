"""Direct CLI for the bounded in-season source availability probe."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apexos_in_season.source_probe import probe_sources, write_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe nflverse schedules and weekly player-data availability."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Local evidence path (default: output/in_season/source_probe_<season>.json).",
    )
    args = parser.parse_args()

    manifest_path = args.manifest or (
        ROOT / "output" / "in_season" / f"source_probe_{args.season}.json"
    )
    manifest = probe_sources(args.season)
    written_path = write_manifest(manifest, manifest_path).resolve()

    print(f"manifest_path={written_path}")
    print(
        json.dumps(
            {
                "probe_status": manifest["probe_status"],
                "source_availability_status": manifest["source_availability_status"],
                "week_completeness_status": manifest["week_completeness_status"],
                "export_validation_status": manifest["export_validation_status"],
                "datasets": {
                    name: {
                        "status": evidence["status"],
                        "block_reason": evidence["block_reason"],
                        "error": evidence["error"],
                    }
                    for name, evidence in manifest["datasets"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if manifest["probe_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
