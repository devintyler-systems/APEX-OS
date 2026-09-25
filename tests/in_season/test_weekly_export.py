from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from apexos_in_season.weekly_export import (
    PLAYER_WEEK_COLUMNS,
    RetrievedSources,
    ValidationBlocked,
    _csv_bytes,
    _release_asset_metadata,
    execute_export,
    freeze_sources,
    load_frozen_sources,
    normalize_player_week,
    parse_official_scoreboard,
    retrieve_live_sources,
    select_latest_published_week,
    validate_complete_week,
    validate_reconciliation,
    validate_source_publication_metadata,
)


NOW = "2026-09-25T20:12:26Z"


def _schedule(rows=None):
    rows = rows or [
        {
            "season": 2026, "week": 2, "game_type": "REG", "game_id": "g1",
            "away_team": "DET", "home_team": "BUF", "away_score": 31, "home_score": 41,
        },
        {
            "season": 2026, "week": 2, "game_type": "REG", "game_id": "g2",
            "away_team": "IND", "home_team": "KC", "away_score": 30, "home_score": 33,
        },
    ]
    return pl.DataFrame(rows)


def _player_row(player_id, game_id, team, opponent, **updates):
    source_names = {
        "source_player_id": "player_id",
        "team_abbr": "team",
        "opponent_team_abbr": "opponent_team",
    }
    row = {}
    for name in PLAYER_WEEK_COLUMNS:
        source = source_names.get(name, name)
        if name in {"season", "week"}:
            row[source] = 2026 if name == "season" else 2
        elif name == "season_type":
            row[source] = "REG"
        elif name == "game_id":
            row[source] = game_id
        elif name == "source_player_id":
            row[source] = player_id
        elif name == "team_abbr":
            row[source] = team
        elif name == "opponent_team_abbr":
            row[source] = opponent
        elif name in {"player_name", "player_display_name"}:
            row[source] = f"Player {player_id}" if player_id else None
        elif name == "position":
            row[source] = "QB"
        elif name == "position_group":
            row[source] = "QB"
        else:
            row[source] = 0
    row.update(updates)
    return row


def _weekly(extra=None):
    rows = [
        _player_row("p1", "g1", "DET", "BUF", attempts=38, completions=26),
        _player_row("p2", "g1", "BUF", "DET", attempts=31, completions=20),
        _player_row("p3", "g2", "IND", "KC", attempts=31, completions=22),
        _player_row("p4", "g2", "KC", "IND", attempts=47, completions=32),
    ]
    rows.extend(extra or [])
    return pl.DataFrame(rows)


def _official_html(states=("FINAL", "FINAL")):
    games = [
        ("lions", "bills", "official-1", states[0]),
        ("colts", "chiefs", "official-2", states[1]),
    ]
    return "".join(
        '<a href="/games/{away}-at-{home}-2026-reg-2" '
        'data-analytics="{{&quot;gameId&quot;:&quot;{game_id}&quot;,'
        '&quot;gameState&quot;:&quot;{state}&quot;}}">game</a>'.format(
            away=away, home=home, game_id=game_id, state=state
        )
        for away, home, game_id, state in games
    )


def _official_games(states=("FINAL", "FINAL")):
    return parse_official_scoreboard(_official_html(states), 2026, 2)


def _evidence():
    return {
        "evidence_version": "test",
        "checked_at_utc": NOW,
        "checks": [
            {
                "kind": "game", "game_id": "g1", "official_reference": "https://nfl/g1",
                "fields": {"away_score": 31, "home_score": 41},
            },
            {
                "kind": "game", "game_id": "g2", "official_reference": "https://nfl/g2",
                "fields": {"away_score": 30, "home_score": 33},
            },
            {
                "kind": "player", "game_id": "g1", "source_player_id": "p1",
                "official_reference": "https://nfl/g1", "fields": {"attempts": 38},
            },
            {
                "kind": "player", "game_id": "g1", "source_player_id": "p2",
                "official_reference": "https://nfl/g1", "fields": {"attempts": 31},
            },
            {
                "kind": "player", "game_id": "g2", "source_player_id": "p4",
                "official_reference": "https://nfl/g2", "fields": {"attempts": 47},
            },
        ],
    }


def _sources():
    return RetrievedSources(
        schedules=_schedule(), weekly=_weekly(), official_html=_official_html(),
        source_metadata={
            "schedules": {
                "release_tag": "schedules", "asset_name": "games.parquet",
                "asset_updated_at": "2026-09-25T20:06:47Z",
                "asset_url": "https://source/schedules",
            },
            "weekly_player_data": {
                "release_tag": "stats_player", "asset_name": "stats_player_week_2026.parquet",
                "asset_updated_at": "2026-09-25T14:37:31Z",
                "asset_url": "https://source/weekly",
            },
        },
        retrieval_utc=NOW,
        input_references={
            "schedules": "https://source/schedules",
            "weekly_player_data": "https://source/weekly",
            "official_scoreboard": "https://nfl/scores",
        },
        selected_week=2,
        selection_evidence={
            "mode": "LATEST_ELIGIBLE", "selected_week": 2,
            "rejected_newer_weeks": [
                {"week": 3, "reason_code": "PLAYER_GAME_COVERAGE_MISMATCH"}
            ],
        },
    )


def test_official_parser_reads_explicit_final_state_and_game_id():
    parsed = _official_games()
    assert [(game["away_team"], game["home_team"], game["state"]) for game in parsed] == [
        ("DET", "BUF", "FINAL"), ("IND", "KC", "FINAL")
    ]
    assert {game["official_game_id"] for game in parsed} == {"official-1", "official-2"}


def test_complete_week_requires_exact_game_and_team_coverage():
    result = validate_complete_week(_schedule(), _weekly(), _official_games(), 2026, 2)
    assert result["scheduled_game_count"] == 2
    assert result["published_player_game_count"] == 2
    assert result["bye_policy"] == "NO_SYNTHETIC_GAMES"


def test_bye_does_not_create_synthetic_game():
    schedules = _schedule().filter(pl.col("game_id") == "g1")
    weekly = _weekly().filter(pl.col("game_id") == "g1")
    official = [game for game in _official_games() if game["away_team"] == "DET"]
    result = validate_complete_week(schedules, weekly, official, 2026, 2)
    assert result["scheduled_game_count"] == 1
    assert set(result["player_week"].get_column("team_abbr")) == {"DET", "BUF"}


def test_latest_selector_rejects_partial_newer_week_and_selects_week_two():
    week_three_schedule = _schedule([{
        "season": 2026, "week": 3, "game_type": "REG", "game_id": "g3",
        "away_team": "NYJ", "home_team": "MIA", "away_score": None,
        "home_score": None,
    }])
    week_three_partial = _player_row("p5", "g3", "NYJ", "MIA")
    week_three_partial["week"] = 3
    selected, document, evidence = select_latest_published_week(
        pl.concat([_schedule(), week_three_schedule], how="diagonal_relaxed"),
        pl.concat([_weekly(), pl.DataFrame([week_three_partial])], how="diagonal_relaxed"),
        2026,
        lambda week: _official_html() if week == 2 else pytest.fail("partial week fetched"),
    )
    assert selected == 2
    assert document == _official_html()
    assert evidence["rejected_newer_weeks"] == [{
        "week": 3,
        "reason_code": "PLAYER_TEAM_COVERAGE_MISMATCH",
        "scheduled_games": 1,
        "published_games": 1,
    }]


def test_latest_selector_does_not_fall_back_on_official_outage():
    def outage(_week):
        raise ValidationBlocked("OFFICIAL_RECORD_RETRIEVAL_FAILED", "offline")

    with pytest.raises(ValidationBlocked) as caught:
        select_latest_published_week(_schedule(), _weekly(), 2026, outage)
    assert caught.value.reason_code == "OFFICIAL_RECORD_RETRIEVAL_FAILED"


@pytest.mark.parametrize(
    ("states", "reason"),
    [(('IN_PROGRESS', 'FINAL'), "OFFICIAL_GAME_NOT_FINAL"),
     (('POSTPONED', 'FINAL'), "OFFICIAL_GAME_NOT_FINAL"),
     (('CANCELLED', 'FINAL'), "OFFICIAL_GAME_NOT_FINAL")],
)
def test_non_final_official_states_fail_closed(states, reason):
    with pytest.raises(ValidationBlocked, match="non-final") as caught:
        validate_complete_week(_schedule(), _weekly(), _official_games(states), 2026, 2)
    assert caught.value.reason_code == reason


def test_missing_official_game_fails_closed():
    with pytest.raises(ValidationBlocked) as caught:
        validate_complete_week(_schedule(), _weekly(), _official_games()[:1], 2026, 2)
    assert caught.value.reason_code == "OFFICIAL_GAME_COVERAGE_MISMATCH"


def test_partial_player_publication_fails_closed():
    partial = _weekly().filter(pl.col("game_id") == "g1")
    with pytest.raises(ValidationBlocked) as caught:
        validate_complete_week(_schedule(), partial, _official_games(), 2026, 2)
    assert caught.value.reason_code == "PLAYER_GAME_COVERAGE_MISMATCH"


def test_missing_team_publication_fails_closed():
    partial = _weekly().filter(~((pl.col("game_id") == "g1") & (pl.col("team") == "BUF")))
    with pytest.raises(ValidationBlocked) as caught:
        validate_complete_week(_schedule(), partial, _official_games(), 2026, 2)
    assert caught.value.reason_code == "PLAYER_TEAM_COVERAGE_MISMATCH"


def test_duplicate_player_game_team_key_fails_closed():
    duplicate = _weekly([_player_row("p1", "g1", "DET", "BUF")])
    with pytest.raises(ValidationBlocked) as caught:
        validate_complete_week(_schedule(), duplicate, _official_games(), 2026, 2)
    assert caught.value.reason_code == "DUPLICATE_PLAYER_KEYS"


def test_null_player_id_is_excluded_and_counted_without_fabrication():
    null_row = _player_row(None, "g1", "DET", "BUF", def_safeties=1)
    result = validate_complete_week(
        _schedule(), _weekly([null_row]), _official_games(), 2026, 2
    )
    assert result["excluded_null_player_id_rows"] == 1
    assert result["player_week"].get_column("source_player_id").null_count() == 0


def test_null_required_team_key_fails_closed():
    rows = _weekly().to_dicts()
    rows[0]["team"] = None
    with pytest.raises(ValidationBlocked) as caught:
        validate_complete_week(_schedule(), pl.DataFrame(rows), _official_games(), 2026, 2)
    assert caught.value.reason_code == "NULL_PLAYER_KEY"


def test_team_change_rows_are_preserved_by_game_and_team():
    schedules = pl.concat([
        _schedule(),
        _schedule([{
            "season": 2026, "week": 2, "game_type": "REG", "game_id": "g3",
            "away_team": "NYJ", "home_team": "MIA", "away_score": 1, "home_score": 2,
        }]),
    ])
    extra = [
        _player_row("p1", "g3", "NYJ", "MIA"),
        _player_row("p5", "g3", "MIA", "NYJ"),
    ]
    official = _official_games() + [{
        "away_team": "NYJ", "home_team": "MIA", "state": "FINAL",
        "official_game_id": "official-3", "game_center_url": "https://nfl/g3",
    }]
    result = validate_complete_week(schedules, _weekly(extra), official, 2026, 2)
    assert result["player_week"].filter(pl.col("source_player_id") == "p1").height == 2


def test_regular_season_and_requested_season_are_isolated():
    noise = _player_row("noise", "post", "DET", "BUF")
    noise["season_type"] = "POST"
    other = _player_row("other", "old", "DET", "BUF")
    other["season"] = 2025
    normalized, _ = normalize_player_week(_weekly([noise, other]), 2026, 2)
    assert normalized.get_column("source_player_id").to_list() == ["p1", "p2", "p3", "p4"]


def test_player_team_association_conflict_fails_closed():
    rows = _weekly().to_dicts()
    rows[0]["opponent_team"] = "KC"
    with pytest.raises(ValidationBlocked) as caught:
        validate_complete_week(_schedule(), pl.DataFrame(rows), _official_games(), 2026, 2)
    assert caught.value.reason_code == "PLAYER_TEAM_ASSOCIATION_CONFLICT"


def test_reconciliation_requires_two_games_three_players_and_matching_values():
    result = validate_complete_week(_schedule(), _weekly(), _official_games(), 2026, 2)
    reconciled = validate_reconciliation(
        _evidence(), result["schedule"], result["player_week"]
    )
    assert reconciled["status"] == "PASS"
    assert reconciled["game_checks"] == 2
    assert reconciled["player_checks"] == 3


def test_reconciliation_mismatch_prevents_false_pass():
    evidence = _evidence()
    evidence["checks"][2]["fields"]["attempts"] = 99
    result = validate_complete_week(_schedule(), _weekly(), _official_games(), 2026, 2)
    with pytest.raises(ValidationBlocked) as caught:
        validate_reconciliation(evidence, result["schedule"], result["player_week"])
    assert caught.value.reason_code == "OFFICIAL_RECONCILIATION_FAILED"


def test_deterministic_csv_and_replay_checksums(tmp_path):
    kwargs = dict(
        sources=_sources(), reconciliation_evidence=_evidence(), season=2026, week=2,
        repository_root=tmp_path, cutoff_utc=NOW,
    )
    first, first_path, first_replay = execute_export(
        output_root=tmp_path / "first", **kwargs
    )
    second, second_path, second_replay = execute_export(
        output_root=tmp_path / "second", **kwargs
    )
    assert first_replay is False and second_replay is False
    assert first["tables"]["player_week"]["sha256"] == second["tables"]["player_week"]["sha256"]
    assert (first_path.parent / "player_week.csv").read_bytes() == (
        second_path.parent / "player_week.csv"
    ).read_bytes()
    _, same_path, replay = execute_export(output_root=tmp_path / "first", **kwargs)
    assert replay is True
    assert same_path == first_path


def test_manifest_has_separate_gates_no_derived_denominators_and_blocked_team_table(tmp_path):
    manifest, _, _ = execute_export(
        sources=_sources(), reconciliation_evidence=_evidence(), season=2026, week=2,
        output_root=tmp_path, repository_root=tmp_path, cutoff_utc=NOW,
    )
    assert manifest["source_availability_status"] == "AVAILABLE"
    assert manifest["week_completeness_status"] == "PASS"
    assert manifest["official_record_reconciliation_status"] == "PASS"
    assert manifest["export_validation_status"] == "PASS"
    assert manifest["derived_fields"] == []
    assert manifest["denominator_policy"] == "NOT_APPLICABLE_NO_DERIVED_FIELDS"
    assert manifest["tables"]["team_week"]["status"] == "BLOCKED"


def test_freeze_and_replay_detects_corrections_or_corruption(tmp_path):
    frozen = freeze_sources(_sources(), tmp_path / "frozen")
    loaded = load_frozen_sources(frozen)
    assert loaded.retrieval_utc == NOW
    weekly_path = frozen / "weekly_player_data.parquet"
    weekly_path.write_bytes(weekly_path.read_bytes() + b"corrupt")
    with pytest.raises(ValidationBlocked) as caught:
        load_frozen_sources(frozen)
    assert caught.value.reason_code == "FROZEN_INPUT_CHECKSUM_MISMATCH"


def test_missing_publication_metadata_fails_freshness_gate():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"published_at": NOW, "assets": [{"name": "games.parquet"}]}

    with pytest.raises(ValidationBlocked) as caught:
        _release_asset_metadata("schedules", "games.parquet", SimpleNamespace(get=lambda *a, **k: Response()))
    assert caught.value.reason_code == "SOURCE_PUBLICATION_METADATA_UNAVAILABLE"


def test_future_source_update_timestamp_fails_freshness_gate():
    metadata = dict(_sources().source_metadata)
    metadata["schedules"] = dict(metadata["schedules"])
    metadata["schedules"]["asset_updated_at"] = "2026-09-26T00:00:00Z"
    with pytest.raises(ValidationBlocked) as caught:
        validate_source_publication_metadata(metadata, NOW)
    assert caught.value.reason_code == "SOURCE_PUBLICATION_TIME_CONFLICT"


def test_source_outage_is_blocked_not_degraded_to_pass():
    module = SimpleNamespace(
        load_schedules=lambda **kwargs: (_ for _ in ()).throw(OSError("offline")),
        load_player_stats=lambda **kwargs: _weekly(),
    )
    with pytest.raises(ValidationBlocked) as caught:
        retrieve_live_sources(
            2026, 2, nfl_module=module,
            clock=lambda: datetime(2026, 9, 25, 20, 12, 26, tzinfo=timezone.utc),
        )
    assert caught.value.reason_code == "SOURCE_RETRIEVAL_FAILED"


def test_csv_null_policy_is_blank_and_never_zero_filled():
    normalized, _ = normalize_player_week(_weekly(), 2026, 2)
    normalized = normalized.with_columns(pl.lit(None).alias("player_name"))
    payload = _csv_bytes(normalized, PLAYER_WEEK_COLUMNS).decode("utf-8")
    assert ",," in payload
    assert "None" not in payload
