# In-Season Source Contract v1.2.1

Status: corrected validation contract. The earlier v1.2 Week 2 run is superseded because its claimed cutoff preceded frozen retrieval. A passing v1.2.1 artifact must satisfy the cutoff and immutable-replay rules below; validation never transfers to another retrieval, week, season, schema/parser version, or corrected upstream release.

## Boundary and authority

The analytical inputs are schedules and weekly player statistics loaded through `nflreadpy==0.1.5` from nflverse release assets. Official NFL score pages provide the independent final-state signal, and official NFL Game Books provide the acceptance reconciliation. Injury/news, routes, charting, pressure attribution, inferred availability, projections, betting outputs, DraftOS priors, and recommendations remain out of scope.

The pipeline is read-only upstream. Raw Parquet, HTML, and PDF inputs are retained only in ignored local `output/` paths. It does not modify DraftOS, existing scoring/projection semantics, or platform write behavior.

## Observed source facts

The retained live retrieval occurred at `2026-09-25T20:52:44.257459Z`:

| Dataset | Loader/reference | Frame/rows | Publication metadata | Normalized SHA-256 |
|---|---|---:|---|---|
| schedules | `nflreadpy.load_schedules(seasons=2026)` | Polars / 272 | tag `schedules`; asset updated `2026-09-25T20:46:50Z`; asset digest `sha256:19005e44ad9eb4bfeafb5b4ebccebb1134075cdfd584cf2f3b87ee2c2141f93a` | `740e9f28fd680319611652ae1b2f49d2a399fab5d1f7642247b8d9aeea449589` |
| weekly player data | `nflreadpy.load_player_stats(seasons=2026, summary_level='week')` | Polars / 2,294 | tag `stats_player`; asset updated `2026-09-25T14:37:31Z`; asset digest `sha256:301ff65217abd67d6eb20c3514ce640ac17d4f3eddebd5d7c356fb6aa21834ed` | `46c370d1bb2df3e5fbc34403e78cb85cf8a19c12329672076cd9c3542f2da845` |
| official scoreboard | `https://www.nfl.com/scores/2026/week-2` | HTML / 16 distinct game cards | source publication/update time `UNKNOWN`; retrieval time is not substituted | `62a29f7e8f859218b32c754cf6ed712e0532f35a2325c48d3b0247805953549a` |

The frozen input byte hashes are `6e3269ae6228f9e925cc28b02ac5b118cc727f8218b6b04f7b282daa13ef9005` (schedules Parquet), `ce4f3ff04053ce43969132683755b1ad8c5812b80519dca3827e57a24c086e8a` (weekly Parquet), and the official HTML hash above.

Observed schedule fields include `season`, `week`, `game_type`, `game_id`, `away_team`, `home_team`, `away_score`, and `home_score`, but no trustworthy explicit final-status field. For all 272 schedule rows, `nfl_detail_id` was null. A non-null score is therefore not accepted as proof of a final game.

Observed weekly rows include `season`, `week`, `season_type`, `game_id`, `player_id`, `team`, and `opponent_team`. For 2026 Week 2, all 16 weekly `game_id` values joined exactly to the 16 scheduled games, and both scheduled teams were represented for every game. One Week 2 source row had a null `player_id`; it contained mixed team-level values and was excluded rather than assigned to a player.

## V1 player output contract

`player_week.csv` is game-granular despite its historical table name. Its unique key is:

```text
(season, season_type, week, game_id, source_player_id, team_abbr)
```

- `season_type` must be the literal `REG`.
- `game_id` is the observed weekly source value and must match one schedule row.
- `source_player_id` preserves `player_id`; null IDs are excluded and counted in the manifest.
- `team_abbr` and `opponent_team_abbr` preserve observed source abbreviations. No numeric team ID or guessed canonical mapping is emitted.
- A player appearing for different teams or games in one week remains in separate rows; no cross-game aggregation is performed.
- Key fields may not be null. Non-key raw nulls serialize as empty CSV cells and are never coerced to zero.
- Ordering is deterministic by the full key, encoded as UTF-8 with LF line endings.

The compact schema contains identity fields followed by source counting fields:

```text
season, week, season_type, game_id, source_player_id, player_name,
player_display_name, position, position_group, team_abbr, opponent_team_abbr,
completions, attempts, passing_yards, passing_tds, passing_interceptions,
sacks_suffered, sack_yards_lost, carries, rushing_yards, rushing_tds,
receptions, targets, receiving_yards, receiving_tds, special_teams_tds,
def_tackles_solo, def_tackle_assists, def_tackles_for_loss,
def_fumbles_forced, def_sacks, def_qb_hits, def_interceptions,
def_interception_yards, def_pass_defended, def_tds, def_safeties,
fumbles_total, fumbles_lost_total, punt_returns, punt_return_yards,
kickoff_returns, kickoff_return_yards, fg_made, fg_att, fg_missed,
fg_blocked, fg_long, pat_made, pat_att, pat_missed, pat_blocked, pt_att,
pt_blocked, pt_long, pt_yards, pt_inside_20
```

All statistical values are raw source fields. V1 defines no derived fields, formulas, ratios, rates, shares, EPA, fantasy points, or denominators. Those fields are unsupported until separately approved and reconciled.

`team_week.csv` is not emitted. The weekly player input is not an approved complete team-stat source, and null-player rows are not a defensible substitute. Its manifest table status is `BLOCKED` with `NO_APPROVED_COMPLETE_TEAM_STAT_SOURCE`.

## Week completeness rule

The default gate evaluates regular-season weeks newest-first. Weeks without exact weekly game/team publication coverage are rejected without an official request; a source-complete week is selected only after its official records pass. An explicit week can be requested for audit/replay. Either mode fails closed unless all conditions hold:

1. At least one schedule row exists, every `game_id` is non-null and unique, and only `game_type == REG` is included.
2. The official NFL score page yields exactly the same away/home pairs as the schedule and every distinct record has explicit `gameState == FINAL`.
3. Missing, extra, repeated (even byte-for-byte identical), conflicting, in-progress, postponed, or cancelled official records block the week. Scores alone never establish finality.
4. Weekly player data contains exactly the scheduled `game_id` set, both scheduled teams for each game, and valid team/opponent associations.
5. Identified player keys are unique and non-null. A bye creates no schedule row and no synthetic game/player row.
6. nflverse release tag, asset URL, asset name, and asset update timestamp are present and the update timestamp is not after retrieval. `UNKNOWN` publication metadata blocks export rather than being inferred from retrieval time.
7. Official reconciliation evidence selects exactly one source row per check, has direct official references, matches every listed value, and covers at least two games plus three players.
8. `cutoff_utc`, frozen `retrieval_utc`, and reconciliation `checked_at_utc` must be well-formed, timezone-aware UTC values. The cutoff must be at or after both retrieval and human review. A missing timezone, malformed value, or evidence after the cutoff blocks before persistence.

An official-record retrieval/parsing outage or conflict blocks the run and never falls back to an older week. A source-complete but explicitly non-final week is rejected as incomplete, allowing evaluation of the preceding week. The retained run rejected partially published Week 3 (1 of 16 game IDs) and selected Week 2.

For the retained Week 2 run, the counts were 16 scheduled games, 16 official final records, 16 weekly-data games, 1,106 exported identified-player rows, and one excluded null-player-ID row.

## Manifest and immutable runs

The manifest reports separate `source_availability_status`, `week_completeness_status`, `official_record_reconciliation_status`, and `export_validation_status`. It also includes cutoff/retrieval/review UTC, repository SHA, schema/parser versions, source references/version/update metadata, source and output row counts/checksums, freshness evidence, game coverage, limitations, reason codes, and correction lineage.

The knowledge cutoff is an as-of claim, not a run label. It must be no earlier than every input retrieval whose earlier state cannot be independently proven. nflverse asset update timestamps remain separate publication metadata and are never substituted for retrieval time. Game Book `checked_at_utc` records when a human reviewed the document. The official document publication time remains `UNKNOWN` unless independently exposed; neither review time nor retrieval time is relabeled as publication time.

Outputs live at:

```text
data/exports/in_season/season=<season>/week=<week>/run=<content-and-code-id>/
  player_week.csv
  manifest.json
```

The run ID covers frozen source content, official final-state content, the canonical reconciliation-evidence digest, claimed cutoff, full source publication metadata, correction lineage, output checksum, schema/parser versions, and repository SHA. Reconciliation evidence uses sorted-key compact UTF-8 JSON (`JSON_SORT_KEYS_COMPACT_UTF8_V1`); its digest therefore binds evidence version, review time, official references, PDF hashes, and reviewed values.

Existing run directories are immutable. `replay_identical=true` is permitted only when both `player_week.csv` and the complete newly constructed `manifest.json` are byte-identical to stored files. Any difference blocks with `IMMUTABLE_RUN_CONFLICT`; files are never overwritten. Changed evidence, cutoff, source metadata, correction lineage, source data, or code produces a distinct run identity.

The prior `v1-542491788447b31f` run and its earlier-cutoff predecessors are historical artifacts, not valid v1.2.1 PASS evidence. They must not be edited in place. The corrected run names the former run in `supersedes_run_id`. Reconciliation details remain versioned in `docs/evidence/issue_1_2026_week2_reconciliation_v1.json`.

The validator compares the manually reviewed values stored in that versioned evidence file against schedule/player source rows. On replay it validates the recorded references and PDF SHA-256 strings and binds them into the evidence digest; it does not fetch or independently hash every referenced Game Book PDF. Human review and custody of the recorded PDF hashes remain an operational acceptance step.

## Source rights and storage decision

The nflverse-data repository declares CC-BY-4.0. The compact export manifest preserves source references and provenance. Official Game Books carry restrictive NFL copyright language, so PDFs and extracted bulk content remain local and uncommitted; only limited comparison facts, URLs, page references, and hashes are retained as acceptance evidence. Bulk raw source inputs and generated exports remain ignored. The repository stores code, tests, contract documentation, and compact reconciliation metadata only.
