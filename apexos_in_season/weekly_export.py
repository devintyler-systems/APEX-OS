"""Fail-closed validation and deterministic export for one NFL regular-season week.

The module keeps retrieval, normalization, validation, and persistence as separate
operations.  It only exports observed nflverse fields and requires an independent
official NFL final-state record plus explicit reconciliation evidence.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import polars as pl
import requests

from .source_probe import deterministic_frame_digest


SCHEMA_VERSION = "1.2.0"
PARSER_VERSION = "1.0.0"
UNKNOWN = "UNKNOWN"

SCHEDULE_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"
)
WEEKLY_URL_TEMPLATE = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.parquet"
)
OFFICIAL_SCORES_URL_TEMPLATE = "https://www.nfl.com/scores/{season}/week-{week}"

# Versioned bridge between official Game Center slugs and the observed nflverse
# abbreviation values.  It is used only to associate official final-state cards;
# it does not manufacture numeric team IDs or alter source abbreviations.
TEAM_SLUG_TO_ABBR = {
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF",
    "panthers": "CAR", "bears": "CHI", "bengals": "CIN", "browns": "CLE",
    "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
    "texans": "HOU", "colts": "IND", "jaguars": "JAX", "chiefs": "KC",
    "rams": "LA", "chargers": "LAC", "raiders": "LV", "dolphins": "MIA",
    "vikings": "MIN", "patriots": "NE", "saints": "NO", "giants": "NYG",
    "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "seahawks": "SEA",
    "49ers": "SF", "buccaneers": "TB", "titans": "TEN", "commanders": "WAS",
}

PLAYER_WEEK_COLUMNS = [
    "season", "week", "season_type", "game_id", "source_player_id",
    "player_name", "player_display_name", "position", "position_group",
    "team_abbr", "opponent_team_abbr",
    "completions", "attempts", "passing_yards", "passing_tds",
    "passing_interceptions", "sacks_suffered", "sack_yards_lost",
    "carries", "rushing_yards", "rushing_tds", "receptions", "targets",
    "receiving_yards", "receiving_tds", "special_teams_tds",
    "def_tackles_solo", "def_tackle_assists", "def_tackles_for_loss",
    "def_fumbles_forced", "def_sacks", "def_qb_hits", "def_interceptions",
    "def_interception_yards", "def_pass_defended", "def_tds", "def_safeties",
    "fumbles_total", "fumbles_lost_total", "punt_returns", "punt_return_yards",
    "kickoff_returns", "kickoff_return_yards", "fg_made", "fg_att", "fg_missed",
    "fg_blocked", "fg_long", "pat_made", "pat_att", "pat_missed", "pat_blocked",
    "pt_att", "pt_blocked", "pt_long", "pt_yards", "pt_inside_20",
]

SOURCE_TO_OUTPUT = {
    "player_id": "source_player_id",
    "team": "team_abbr",
    "opponent_team": "opponent_team_abbr",
}

REQUIRED_SCHEDULE_COLUMNS = {
    "season", "week", "game_type", "game_id", "away_team", "home_team",
    "away_score", "home_score",
}
REQUIRED_PLAYER_COLUMNS = {
    key for key in PLAYER_WEEK_COLUMNS if key not in SOURCE_TO_OUTPUT.values()
} | set(SOURCE_TO_OUTPUT)
PLAYER_KEY = ["season", "season_type", "week", "game_id", "source_player_id", "team_abbr"]


class ValidationBlocked(RuntimeError):
    """Raised with stable reason codes when an acceptance gate fails closed."""

    def __init__(self, reason_code: str, detail: str):
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class RetrievedSources:
    schedules: pl.DataFrame
    weekly: pl.DataFrame
    official_html: str
    source_metadata: Mapping[str, Any]
    retrieval_utc: str
    input_references: Mapping[str, str]
    selected_week: int
    selection_evidence: Mapping[str, Any]


class _OfficialLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = {key: value for key, value in attrs if value is not None}
        href = values.get("href", "")
        analytics = values.get("data-analytics", "")
        if "/games/" in href and analytics:
            self.links.append({"href": href, "data_analytics": analytics})


def utc_text(value: datetime | None = None) -> str:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_columns(frame: pl.DataFrame, expected: set[str], dataset: str) -> None:
    missing = sorted(expected - set(frame.columns))
    if missing:
        raise ValidationBlocked(
            "MISSING_REQUIRED_COLUMNS",
            f"{dataset} is missing required columns: {', '.join(missing)}",
        )


def parse_official_scoreboard(document: str, season: int, week: int) -> list[dict[str, str]]:
    """Parse official NFL Game Center links and their explicit gameState values."""

    parser = _OfficialLinkParser()
    parser.feed(document)
    suffix = f"-{season}-reg-{week}"
    pattern = re.compile(rf"^/games/([a-z0-9-]+)-at-([a-z0-9-]+){re.escape(suffix)}$")
    games: dict[tuple[str, str], dict[str, str]] = {}
    for link in parser.links:
        match = pattern.match(link["href"])
        if not match:
            continue
        away_slug, home_slug = match.groups()
        if away_slug not in TEAM_SLUG_TO_ABBR or home_slug not in TEAM_SLUG_TO_ABBR:
            raise ValidationBlocked(
                "UNKNOWN_OFFICIAL_TEAM_SLUG",
                f"unmapped official Game Center slug: {away_slug}-at-{home_slug}",
            )
        try:
            analytics = json.loads(html.unescape(link["data_analytics"]))
        except (TypeError, ValueError) as exc:
            raise ValidationBlocked(
                "OFFICIAL_RECORD_PARSE_ERROR", f"invalid data-analytics JSON: {exc}"
            ) from exc
        state = analytics.get("gameState")
        if not isinstance(state, str) or not state:
            raise ValidationBlocked(
                "OFFICIAL_STATUS_MISSING", f"gameState missing for {link['href']}"
            )
        key = (TEAM_SLUG_TO_ABBR[away_slug], TEAM_SLUG_TO_ABBR[home_slug])
        item = {
            "away_team": key[0],
            "home_team": key[1],
            "state": state.upper(),
            "official_game_id": str(analytics.get("gameId") or UNKNOWN),
            "game_center_url": f"https://www.nfl.com{link['href']}",
        }
        prior = games.get(key)
        if prior is not None and prior != item:
            raise ValidationBlocked(
                "CONFLICTING_OFFICIAL_RECORDS",
                f"conflicting official records for {key[0]} at {key[1]}",
            )
        games[key] = item
    if not games:
        raise ValidationBlocked(
            "OFFICIAL_RECORDS_UNAVAILABLE",
            f"no official regular-season week {week} game records were parsed",
        )
    return [games[key] for key in sorted(games)]


def normalize_player_week(weekly: pl.DataFrame, season: int, week: int) -> tuple[pl.DataFrame, int]:
    _require_columns(weekly, REQUIRED_PLAYER_COLUMNS, "weekly player data")
    scoped = weekly.filter(
        (pl.col("season") == season)
        & (pl.col("week") == week)
        & (pl.col("season_type") == "REG")
    )
    excluded_null_ids = scoped.filter(pl.col("player_id").is_null()).height
    scoped = scoped.filter(pl.col("player_id").is_not_null())
    expressions = []
    for output_name in PLAYER_WEEK_COLUMNS:
        source_name = next(
            (source for source, output in SOURCE_TO_OUTPUT.items() if output == output_name),
            output_name,
        )
        expressions.append(pl.col(source_name).alias(output_name))
    normalized = scoped.select(expressions).sort(PLAYER_KEY)
    return normalized, excluded_null_ids


def _duplicate_count(frame: pl.DataFrame, key: Sequence[str]) -> int:
    return frame.group_by(list(key)).len().filter(pl.col("len") > 1).height


def validate_complete_week(
    schedules: pl.DataFrame,
    weekly: pl.DataFrame,
    official_games: Sequence[Mapping[str, str]],
    season: int,
    week: int,
) -> dict[str, Any]:
    """Require exact schedule, official-final, and published-player-game coverage."""

    _require_columns(schedules, REQUIRED_SCHEDULE_COLUMNS, "schedules")
    schedule_week = schedules.filter(
        (pl.col("season") == season)
        & (pl.col("week") == week)
        & (pl.col("game_type") == "REG")
    )
    if schedule_week.height == 0:
        raise ValidationBlocked("NO_SCHEDULED_GAMES", "no regular-season games are scheduled")
    if schedule_week.select(pl.col("game_id").n_unique()).item() != schedule_week.height:
        raise ValidationBlocked("DUPLICATE_GAME_KEYS", "schedule game_id values are not unique")
    if schedule_week.filter(
        pl.col("game_id").is_null()
        | pl.col("away_team").is_null()
        | pl.col("home_team").is_null()
    ).height:
        raise ValidationBlocked("NULL_GAME_KEY", "schedule contains a null game key/team")

    schedule_pairs = {
        (row["away_team"], row["home_team"]): row["game_id"]
        for row in schedule_week.iter_rows(named=True)
    }
    official_by_pair = {
        (item["away_team"], item["home_team"]): item for item in official_games
    }
    if set(official_by_pair) != set(schedule_pairs):
        missing = sorted(set(schedule_pairs) - set(official_by_pair))
        extra = sorted(set(official_by_pair) - set(schedule_pairs))
        raise ValidationBlocked(
            "OFFICIAL_GAME_COVERAGE_MISMATCH",
            f"official/schedule mismatch; missing={missing}; extra={extra}",
        )
    non_final = sorted(
        f"{away}@{home}:{official_by_pair[(away, home)]['state']}"
        for away, home in schedule_pairs
        if official_by_pair[(away, home)]["state"] != "FINAL"
    )
    if non_final:
        raise ValidationBlocked(
            "OFFICIAL_GAME_NOT_FINAL", "non-final official records: " + ", ".join(non_final)
        )

    normalized, excluded_null_ids = normalize_player_week(weekly, season, week)
    if normalized.height == 0:
        raise ValidationBlocked("PLAYER_WEEK_UNPUBLISHED", "no identified weekly player rows")
    if _duplicate_count(normalized, PLAYER_KEY):
        raise ValidationBlocked("DUPLICATE_PLAYER_KEYS", "normalized player keys are not unique")
    if normalized.filter(
        pl.any_horizontal([pl.col(column).is_null() for column in PLAYER_KEY])
    ).height:
        raise ValidationBlocked("NULL_PLAYER_KEY", "normalized player key contains nulls")

    schedule_game_ids = set(schedule_week.get_column("game_id").to_list())
    player_game_ids = set(normalized.get_column("game_id").to_list())
    if player_game_ids != schedule_game_ids:
        raise ValidationBlocked(
            "PLAYER_GAME_COVERAGE_MISMATCH",
            f"weekly/schedule game mismatch; missing={sorted(schedule_game_ids-player_game_ids)}; "
            f"extra={sorted(player_game_ids-schedule_game_ids)}",
        )
    schedule_teams_by_game = {
        row["game_id"]: {row["away_team"], row["home_team"]}
        for row in schedule_week.iter_rows(named=True)
    }
    player_teams_by_game = {
        game_id: set(group.get_column("team_abbr").to_list())
        for (game_id,), group in normalized.group_by("game_id")
    }
    mismatches = {
        game_id: {
            "scheduled": sorted(schedule_teams_by_game[game_id]),
            "published": sorted(player_teams_by_game.get(game_id, set())),
        }
        for game_id in sorted(schedule_game_ids)
        if player_teams_by_game.get(game_id, set()) != schedule_teams_by_game[game_id]
    }
    if mismatches:
        raise ValidationBlocked(
            "PLAYER_TEAM_COVERAGE_MISMATCH", json.dumps(mismatches, sort_keys=True)
        )
    bad_opponents = normalized.filter(
        ~pl.struct(["game_id", "team_abbr", "opponent_team_abbr"]).map_elements(
            lambda row: {
                row["team_abbr"], row["opponent_team_abbr"]
            } == schedule_teams_by_game.get(row["game_id"], set()),
            return_dtype=pl.Boolean,
        )
    )
    if bad_opponents.height:
        raise ValidationBlocked(
            "PLAYER_TEAM_ASSOCIATION_CONFLICT",
            f"{bad_opponents.height} player rows conflict with scheduled teams",
        )
    return {
        "schedule": schedule_week.sort("game_id"),
        "player_week": normalized,
        "scheduled_game_count": schedule_week.height,
        "official_final_game_count": len(official_games),
        "published_player_game_count": len(player_game_ids),
        "excluded_null_player_id_rows": excluded_null_ids,
        "bye_policy": "NO_SYNTHETIC_GAMES",
    }


def select_latest_published_week(
    schedules: pl.DataFrame,
    weekly: pl.DataFrame,
    season: int,
    official_document_loader: Callable[[int], str],
) -> tuple[int, str, dict[str, Any]]:
    """Select the newest source-complete week whose official records are all final."""

    _require_columns(schedules, REQUIRED_SCHEDULE_COLUMNS, "schedules")
    _require_columns(weekly, REQUIRED_PLAYER_COLUMNS, "weekly player data")
    season_schedule = schedules.filter(
        (pl.col("season") == season) & (pl.col("game_type") == "REG")
    )
    weeks = sorted(set(season_schedule.get_column("week").to_list()), reverse=True)
    rejected: list[dict[str, Any]] = []
    for week in weeks:
        schedule_week = season_schedule.filter(pl.col("week") == week)
        weekly_week = weekly.filter(
            (pl.col("season") == season)
            & (pl.col("season_type") == "REG")
            & (pl.col("week") == week)
            & pl.col("player_id").is_not_null()
        )
        scheduled_ids = set(schedule_week.get_column("game_id").drop_nulls().to_list())
        published_ids = set(weekly_week.get_column("game_id").drop_nulls().to_list())
        if not scheduled_ids or scheduled_ids != published_ids:
            rejected.append({
                "week": week,
                "reason_code": "PLAYER_GAME_COVERAGE_MISMATCH",
                "scheduled_games": len(scheduled_ids),
                "published_games": len(published_ids),
            })
            continue
        scheduled_teams = {
            row["game_id"]: {row["away_team"], row["home_team"]}
            for row in schedule_week.iter_rows(named=True)
        }
        published_teams = {
            game_id: set(group.get_column("team").to_list())
            for (game_id,), group in weekly_week.group_by("game_id")
        }
        if any(published_teams.get(game_id, set()) != teams for game_id, teams in scheduled_teams.items()):
            rejected.append({
                "week": week,
                "reason_code": "PLAYER_TEAM_COVERAGE_MISMATCH",
                "scheduled_games": len(scheduled_ids),
                "published_games": len(published_ids),
            })
            continue
        try:
            document = official_document_loader(week)
            official = parse_official_scoreboard(document, season, week)
            validate_complete_week(schedules, weekly, official, season, week)
        except ValidationBlocked as exc:
            if exc.reason_code != "OFFICIAL_GAME_NOT_FINAL":
                raise
            rejected.append({
                "week": week,
                "reason_code": exc.reason_code,
                "detail": exc.detail,
            })
            continue
        return week, document, {
            "mode": "LATEST_ELIGIBLE",
            "selected_week": week,
            "rejected_newer_weeks": rejected,
        }
    raise ValidationBlocked(
        "NO_ELIGIBLE_WEEK",
        json.dumps({"season": season, "rejected_weeks": rejected}, sort_keys=True),
    )


def validate_reconciliation(
    evidence: Mapping[str, Any], schedule_week: pl.DataFrame, player_week: pl.DataFrame
) -> dict[str, Any]:
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        raise ValidationBlocked("RECONCILIATION_EVIDENCE_INVALID", "checks must be a list")
    game_ids: set[str] = set()
    player_ids: set[str] = set()
    failures: list[str] = []
    for index, check in enumerate(checks):
        if not isinstance(check, Mapping) or not check.get("official_reference"):
            failures.append(f"check[{index}] missing official_reference")
            continue
        kind = check.get("kind")
        game_id = str(check.get("game_id", ""))
        fields = check.get("fields")
        if not game_id or not isinstance(fields, Mapping):
            failures.append(f"check[{index}] missing game_id/fields")
            continue
        if kind == "game":
            rows = schedule_week.filter(pl.col("game_id") == game_id)
            game_ids.add(game_id)
        elif kind == "player":
            player_id = str(check.get("source_player_id", ""))
            rows = player_week.filter(
                (pl.col("game_id") == game_id)
                & (pl.col("source_player_id") == player_id)
            )
            player_ids.add(player_id)
        else:
            failures.append(f"check[{index}] has unsupported kind {kind!r}")
            continue
        if rows.height != 1:
            failures.append(f"check[{index}] selected {rows.height} source rows")
            continue
        row = rows.row(0, named=True)
        for field, official_value in fields.items():
            if field not in row:
                failures.append(f"check[{index}] field {field!r} is not exported")
            elif row[field] != official_value:
                failures.append(
                    f"check[{index}] {field}: source={row[field]!r} official={official_value!r}"
                )
    if len(game_ids) < 2 or len(player_ids) < 3:
        failures.append(
            f"minimum not met: distinct games={len(game_ids)}, distinct players={len(player_ids)}"
        )
    if failures:
        raise ValidationBlocked("OFFICIAL_RECONCILIATION_FAILED", "; ".join(failures))
    return {
        "status": "PASS",
        "checked_at_utc": evidence.get("checked_at_utc", UNKNOWN),
        "game_checks": len(game_ids),
        "player_checks": len(player_ids),
        "evidence_version": evidence.get("evidence_version", UNKNOWN),
        "references": sorted(
            {str(check["official_reference"]) for check in checks if check.get("official_reference")}
        ),
    }


def validate_source_publication_metadata(
    metadata: Mapping[str, Any], retrieval_utc: str
) -> dict[str, Any]:
    """Require independently obtained release identity and non-future update times."""

    try:
        retrieval = datetime.fromisoformat(retrieval_utc.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValidationBlocked(
            "INVALID_RETRIEVAL_TIMESTAMP", f"invalid retrieval UTC: {retrieval_utc!r}"
        ) from exc
    checked: dict[str, Any] = {}
    for dataset in ("schedules", "weekly_player_data"):
        item = metadata.get(dataset)
        if not isinstance(item, Mapping):
            raise ValidationBlocked(
                "SOURCE_PUBLICATION_METADATA_UNAVAILABLE",
                f"{dataset} publication metadata is missing",
            )
        missing = [
            field for field in ("release_tag", "asset_name", "asset_updated_at", "asset_url")
            if item.get(field) in (None, "", UNKNOWN)
        ]
        if missing:
            raise ValidationBlocked(
                "SOURCE_PUBLICATION_METADATA_UNAVAILABLE",
                f"{dataset} metadata missing: {', '.join(missing)}",
            )
        try:
            updated = datetime.fromisoformat(
                str(item["asset_updated_at"]).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValidationBlocked(
                "SOURCE_PUBLICATION_METADATA_INVALID",
                f"{dataset} invalid asset_updated_at: {item['asset_updated_at']!r}",
            ) from exc
        if updated > retrieval:
            raise ValidationBlocked(
                "SOURCE_PUBLICATION_TIME_CONFLICT",
                f"{dataset} asset update {utc_text(updated)} is after retrieval {retrieval_utc}",
            )
        checked[dataset] = {
            "asset_updated_at": utc_text(updated),
            "age_seconds_at_retrieval": int((retrieval - updated).total_seconds()),
        }
    return checked


def _csv_bytes(frame: pl.DataFrame, columns: Sequence[str]) -> bytes:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in frame.select(list(columns)).iter_rows():
        writer.writerow(["" if value is None else value for value in row])
    return buffer.getvalue().encode("utf-8")


def repository_sha(root: str | Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(root), check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return UNKNOWN


def build_manifest(
    *,
    season: int,
    week: int,
    sources: RetrievedSources,
    validation: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    player_csv: bytes,
    repository_head: str,
    run_id: str,
    cutoff_utc: str,
    supersedes_run_id: str | None = None,
    correction_reason: str | None = None,
    publication_freshness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    schedule = validation["schedule"]
    players = validation["player_week"]
    return {
        "contract_version": "1.2",
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "run_id": run_id,
        "season": season,
        "week": week,
        "season_type": "REG",
        "cutoff_utc": cutoff_utc,
        "retrieval_utc": sources.retrieval_utc,
        "repository_sha": repository_head,
        "source_availability_status": "AVAILABLE",
        "week_completeness_status": "PASS",
        "official_record_reconciliation_status": reconciliation["status"],
        "export_validation_status": "PASS",
        "source_metadata": sources.source_metadata,
        "week_selection": dict(sources.selection_evidence),
        "source_evidence": {
            "schedules": {
                "reference": sources.input_references["schedules"],
                "row_count": sources.schedules.height,
                "normalized_sha256": deterministic_frame_digest(sources.schedules),
            },
            "weekly_player_data": {
                "reference": sources.input_references["weekly_player_data"],
                "row_count": sources.weekly.height,
                "normalized_sha256": deterministic_frame_digest(sources.weekly),
            },
            "official_scoreboard": {
                "reference": sources.input_references["official_scoreboard"],
                "sha256": sha256_bytes(sources.official_html.encode("utf-8")),
            },
        },
        "game_coverage": {
            "scheduled": validation["scheduled_game_count"],
            "official_final": validation["official_final_game_count"],
            "weekly_player_data": validation["published_player_game_count"],
            "bye_policy": validation["bye_policy"],
        },
        "tables": {
            "player_week": {
                "status": "PASS",
                "row_count": players.height,
                "sha256": sha256_bytes(player_csv),
                "key": PLAYER_KEY,
                "columns": PLAYER_WEEK_COLUMNS,
                "excluded_source_rows": {
                    "null_source_player_id": validation["excluded_null_player_id_rows"]
                },
            },
            "team_week": {
                "status": "BLOCKED",
                "reason_code": "NO_APPROVED_COMPLETE_TEAM_STAT_SOURCE",
                "row_count": 0,
                "sha256": None,
            },
        },
        "derived_fields": [],
        "denominator_policy": "NOT_APPLICABLE_NO_DERIVED_FIELDS",
        "freshness": {
            "status": "PASS",
            "rule": "asset update metadata present and complete game/team publication coverage",
            "datasets": dict(publication_freshness or {}),
        },
        "official_reconciliation": reconciliation,
        "limitations": [
            "No inferred availability, routes, charting, pressure attribution, projections, betting outputs, or DraftOS priors.",
            "Team abbreviations are preserved source values; no numeric team ID is invented.",
            "The compact v1 schema omits source-derived rates, EPA, fantasy points, and share metrics.",
            "team_week is not emitted because no approved complete team-stat source is in scope.",
        ],
        "correction_lineage": {
            "supersedes_run_id": supersedes_run_id,
            "reason": correction_reason,
        },
        "reason_codes": [],
    }


def persist_validated_export(
    output_root: str | Path,
    manifest: Mapping[str, Any],
    player_csv: bytes,
) -> tuple[Path, bool]:
    root = Path(output_root)
    destination = (
        root / f"season={manifest['season']}" / f"week={manifest['week']}"
        / f"run={manifest['run_id']}"
    )
    player_path = destination / "player_week.csv"
    manifest_path = destination / "manifest.json"
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if destination.exists():
        if not player_path.is_file() or not manifest_path.is_file():
            raise ValidationBlocked(
                "IMMUTABLE_RUN_CONFLICT", f"incomplete existing run directory: {destination}"
            )
        if player_path.read_bytes() != player_csv:
            raise ValidationBlocked(
                "IMMUTABLE_RUN_CONFLICT", f"existing player export differs: {player_path}"
            )
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing_manifest.get("tables", {}).get("player_week", {}).get("sha256") != sha256_bytes(player_csv):
            raise ValidationBlocked(
                "IMMUTABLE_RUN_CONFLICT", f"existing manifest checksum differs: {manifest_path}"
            )
        return manifest_path, True
    destination.mkdir(parents=True, exist_ok=False)
    player_path.write_bytes(player_csv)
    manifest_path.write_bytes(manifest_bytes)
    return manifest_path, False


def execute_export(
    *,
    sources: RetrievedSources,
    reconciliation_evidence: Mapping[str, Any],
    season: int,
    week: int,
    output_root: str | Path,
    repository_root: str | Path,
    cutoff_utc: str,
    supersedes_run_id: str | None = None,
    correction_reason: str | None = None,
) -> tuple[dict[str, Any], Path, bool]:
    if sources.selected_week != week:
        raise ValidationBlocked(
            "SELECTED_WEEK_MISMATCH",
            f"retrieval selected week {sources.selected_week}, export requested week {week}",
        )
    publication_freshness = validate_source_publication_metadata(
        sources.source_metadata, sources.retrieval_utc
    )
    official_games = parse_official_scoreboard(sources.official_html, season, week)
    validation = validate_complete_week(
        sources.schedules, sources.weekly, official_games, season, week
    )
    reconciliation = validate_reconciliation(
        reconciliation_evidence, validation["schedule"], validation["player_week"]
    )
    player_csv = _csv_bytes(validation["player_week"], PLAYER_WEEK_COLUMNS)
    repository_head = repository_sha(repository_root)
    fingerprint = sha256_bytes(
        (
            deterministic_frame_digest(sources.schedules)
            + deterministic_frame_digest(sources.weekly)
            + sha256_bytes(sources.official_html.encode("utf-8"))
            + SCHEMA_VERSION
            + PARSER_VERSION
            + repository_head
        ).encode("ascii")
    )
    run_id = f"v1-{fingerprint[:16]}"
    manifest = build_manifest(
        season=season,
        week=week,
        sources=sources,
        validation=validation,
        reconciliation=reconciliation,
        player_csv=player_csv,
        repository_head=repository_head,
        run_id=run_id,
        cutoff_utc=cutoff_utc,
        supersedes_run_id=supersedes_run_id,
        correction_reason=correction_reason,
        publication_freshness=publication_freshness,
    )
    manifest_path, replay = persist_validated_export(output_root, manifest, player_csv)
    return manifest, manifest_path, replay


def _release_asset_metadata(tag: str, asset_name: str, session: Any = requests) -> dict[str, Any]:
    url = f"https://api.github.com/repos/nflverse/nflverse-data/releases/tags/{tag}"
    response = session.get(url, timeout=30)
    response.raise_for_status()
    release = response.json()
    matches = [asset for asset in release.get("assets", []) if asset.get("name") == asset_name]
    if len(matches) != 1:
        raise ValidationBlocked(
            "SOURCE_PUBLICATION_METADATA_UNAVAILABLE",
            f"expected one {asset_name!r} asset in release {tag!r}, found {len(matches)}",
        )
    asset = matches[0]
    if not asset.get("updated_at") or not asset.get("browser_download_url"):
        raise ValidationBlocked(
            "SOURCE_PUBLICATION_METADATA_UNAVAILABLE",
            f"release asset {asset_name!r} lacks required publication metadata",
        )
    return {
        "release_tag": tag,
        "release_published_at": release.get("published_at", UNKNOWN),
        "asset_name": asset_name,
        "asset_updated_at": asset["updated_at"],
        "asset_url": asset["browser_download_url"],
        "asset_size": asset.get("size", UNKNOWN),
        "asset_digest": asset.get("digest", UNKNOWN),
    }


def retrieve_live_sources(
    season: int,
    week: int | None,
    *,
    nfl_module: Any,
    session: Any = requests,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RetrievedSources:
    try:
        schedules = nfl_module.load_schedules(seasons=season)
        weekly = nfl_module.load_player_stats(seasons=season, summary_level="week")
    except Exception as exc:
        raise ValidationBlocked(
            "SOURCE_RETRIEVAL_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(schedules, pl.DataFrame) or not isinstance(weekly, pl.DataFrame):
        raise ValidationBlocked("UNSUPPORTED_FRAME_TYPE", "live loaders must return Polars DataFrames")
    def load_official(candidate_week: int) -> str:
        official_url = OFFICIAL_SCORES_URL_TEMPLATE.format(
            season=season, week=candidate_week
        )
        try:
            response = session.get(official_url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            raise ValidationBlocked(
                "OFFICIAL_RECORD_RETRIEVAL_FAILED", f"{type(exc).__name__}: {exc}"
            ) from exc

    if week is None:
        selected_week, official_document, selection_evidence = select_latest_published_week(
            schedules, weekly, season, load_official
        )
    else:
        selected_week = week
        official_document = load_official(week)
        selection_evidence = {
            "mode": "EXPLICIT_WEEK",
            "selected_week": week,
            "rejected_newer_weeks": [],
        }
    official_url = OFFICIAL_SCORES_URL_TEMPLATE.format(
        season=season, week=selected_week
    )
    retrieval = utc_text(clock())
    metadata = {
        "schedules": _release_asset_metadata("schedules", "games.parquet", session),
        "weekly_player_data": _release_asset_metadata(
            "stats_player", f"stats_player_week_{season}.parquet", session
        ),
    }
    return RetrievedSources(
        schedules=schedules,
        weekly=weekly,
        official_html=official_document,
        source_metadata=metadata,
        retrieval_utc=retrieval,
        input_references={
            "schedules": SCHEDULE_URL,
            "weekly_player_data": WEEKLY_URL_TEMPLATE.format(season=season),
            "official_scoreboard": official_url,
        },
        selected_week=selected_week,
        selection_evidence=selection_evidence,
    )


def freeze_sources(sources: RetrievedSources, directory: str | Path) -> Path:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=False)
    sources.schedules.write_parquet(destination / "schedules.parquet")
    sources.weekly.write_parquet(destination / "weekly_player_data.parquet")
    (destination / "official_scoreboard.html").write_text(
        sources.official_html, encoding="utf-8", newline="\n"
    )
    metadata = {
        "retrieval_utc": sources.retrieval_utc,
        "source_metadata": sources.source_metadata,
        "input_references": sources.input_references,
        "selected_week": sources.selected_week,
        "selection_evidence": sources.selection_evidence,
        "files": {
            name: sha256_file(destination / name)
            for name in (
                "schedules.parquet", "weekly_player_data.parquet", "official_scoreboard.html"
            )
        },
    }
    (destination / "frozen_manifest.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


def load_frozen_sources(directory: str | Path) -> RetrievedSources:
    source = Path(directory)
    metadata = json.loads((source / "frozen_manifest.json").read_text(encoding="utf-8"))
    for name, expected in metadata.get("files", {}).items():
        actual = sha256_file(source / name)
        if actual != expected:
            raise ValidationBlocked(
                "FROZEN_INPUT_CHECKSUM_MISMATCH",
                f"{name}: expected {expected}, observed {actual}",
            )
    return RetrievedSources(
        schedules=pl.read_parquet(source / "schedules.parquet"),
        weekly=pl.read_parquet(source / "weekly_player_data.parquet"),
        official_html=(source / "official_scoreboard.html").read_text(encoding="utf-8"),
        source_metadata=metadata["source_metadata"],
        retrieval_utc=metadata["retrieval_utc"],
        input_references=metadata["input_references"],
        selected_week=int(metadata["selected_week"]),
        selection_evidence=metadata["selection_evidence"],
    )
