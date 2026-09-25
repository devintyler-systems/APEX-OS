"""Direct CLI for the fail-closed Issue #1 weekly export."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apexos_in_season.weekly_export import (  # noqa: E402
    ValidationBlocked,
    execute_export,
    freeze_sources,
    load_frozen_sources,
    retrieve_live_sources,
    utc_text,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and export one completed, published NFL regular-season week."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument(
        "--week", default="latest",
        help="Regular-season week number, or 'latest' (default) for fail-closed discovery.",
    )
    parser.add_argument(
        "--frozen-dir", type=Path, help="Replay a prior frozen retrieval without network calls."
    )
    parser.add_argument(
        "--capture-dir", type=Path,
        help="For a live run, persist raw inputs locally for immutable replay (must not exist).",
    )
    parser.add_argument(
        "--reconciliation-evidence", type=Path, required=True,
        help="Reviewed official Game Book comparison evidence.",
    )
    parser.add_argument(
        "--output-root", type=Path,
        default=ROOT / "data" / "exports" / "in_season",
    )
    parser.add_argument(
        "--cutoff-utc",
        help=(
            "Timezone-aware UTC knowledge cutoff; must not precede retrieval or "
            "human review (default: UTC after retrieval completes)."
        ),
    )
    parser.add_argument("--supersedes-run-id")
    parser.add_argument("--correction-reason")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if str(args.week).lower() == "latest":
            requested_week = None
        else:
            try:
                requested_week = int(args.week)
            except ValueError as exc:
                raise ValidationBlocked(
                    "INVALID_WEEK", "--week must be a positive integer or 'latest'"
                ) from exc
            if requested_week < 1:
                raise ValidationBlocked(
                    "INVALID_WEEK", "--week must be a positive integer or 'latest'"
                )
        if bool(args.supersedes_run_id) != bool(args.correction_reason):
            raise ValidationBlocked(
                "CORRECTION_LINEAGE_INCOMPLETE",
                "--supersedes-run-id and --correction-reason must be supplied together",
            )
        if args.frozen_dir:
            if args.capture_dir:
                raise ValidationBlocked(
                    "INVALID_ARGUMENTS", "--capture-dir cannot be combined with --frozen-dir"
                )
            sources = load_frozen_sources(args.frozen_dir)
            mode = "frozen_replay"
            selected_week = sources.selected_week
            if requested_week is not None and requested_week != selected_week:
                raise ValidationBlocked(
                    "SELECTED_WEEK_MISMATCH",
                    f"frozen input selected week {selected_week}, requested {requested_week}",
                )
        else:
            nflreadpy = importlib.import_module("nflreadpy")
            sources = retrieve_live_sources(
                args.season, requested_week, nfl_module=nflreadpy
            )
            mode = "live"
            selected_week = sources.selected_week
            if args.capture_dir:
                freeze_sources(sources, args.capture_dir)
        evidence = json.loads(
            args.reconciliation_evidence.read_text(encoding="utf-8")
        )
        cutoff = args.cutoff_utc or utc_text(datetime.now(timezone.utc))
        manifest, path, replay = execute_export(
            sources=sources,
            reconciliation_evidence=evidence,
            season=args.season,
            week=selected_week,
            output_root=args.output_root,
            repository_root=ROOT,
            cutoff_utc=cutoff,
            supersedes_run_id=args.supersedes_run_id,
            correction_reason=args.correction_reason,
        )
    except ValidationBlocked as exc:
        print(
            json.dumps(
                {
                    "export_validation_status": "BLOCKED",
                    "reason_code": exc.reason_code,
                    "detail": exc.detail,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "export_validation_status": "BLOCKED",
                    "reason_code": "SOURCE_OR_ENVIRONMENT_EXCEPTION",
                    "detail": f"{type(exc).__name__}: {exc}",
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(f"mode={mode}")
    print(f"selected_week={selected_week}")
    print(f"manifest_path={path.resolve()}")
    print(f"run_id={manifest['run_id']}")
    print(f"replay_identical={str(replay).lower()}")
    print(f"player_week_rows={manifest['tables']['player_week']['row_count']}")
    print(f"player_week_sha256={manifest['tables']['player_week']['sha256']}")
    print(f"week_completeness_status={manifest['week_completeness_status']}")
    print(
        "official_record_reconciliation_status="
        f"{manifest['official_record_reconciliation_status']}"
    )
    print(f"export_validation_status={manifest['export_validation_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
