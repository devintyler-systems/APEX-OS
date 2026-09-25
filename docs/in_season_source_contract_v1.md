# In-Season Source Contract v1.1

Status: approved for bounded implementation; not approved as a validated export.

## Boundary

This contract covers a read-only availability probe for two analytical inputs:

- schedules through the installed `nflreadpy`/nflverse public schedule loader;
- weekly player data through the installed `nflreadpy`/nflverse public player-stat loader at weekly summary level.

Official NFL Game Books or Game Center remain a later reconciliation gate. NFL injury/news, routes, charting, pressure attribution, inferred availability, projections, betting outputs, and DraftOS priors are outside this contract. The probe does not write upstream rows, produce player-week records, change DraftOS, or make recommendations.

## Proposed manifest fields

The manifest contract proposes top-level fields for `contract_version`, `season`, `generated_at_utc`, Python and installed package versions, introspected relevant loader symbols/signatures, `probe_status`, `source_availability_status`, `week_completeness_status`, `export_validation_status`, and per-dataset evidence.

Each dataset evidence object records:

- `status`: `AVAILABLE` only after a supported, non-empty frame is inspected; otherwise `BLOCKED`;
- the observed loader symbol and exact invocation, or `null` when no invocation was possible;
- actual fully qualified frame type, observed columns, observed row count, deterministic SHA-256, and retrieval UTC timestamp;
- `source_reference` only when directly exposed by the loader/result;
- `source_update_metadata`, with the literal value `UNKNOWN` when the loader/result exposes none;
- a structured block reason and error without preventing the other dataset attempt.

`probe_status` is `PASS` only when both approved datasets are available and inspectable. It is not an export-quality decision. `source_availability_status` is separate so inability to determine availability is not mislabeled as either success or proven upstream absence.

## Observed fields versus proposed downstream fields

Observed fields are only the column names and frame facts recorded in a live local manifest. They are evidence of what the loader returned at that retrieval time; they are not frozen schema commitments. The probe intentionally does not select, rename, map, or emit player-week keys, formulas, denominators, or derived availability fields.

The 2026 discovery run retrieved at `2026-09-25T19:50:25Z` observed `nflreadpy==0.1.5`, these public loaders, and these results:

| Dataset | Verified invocation | Observed frame | Rows | SHA-256 |
|---|---|---:|---:|---|
| schedules | `nflreadpy.load_schedules(seasons=2026)` | `polars.dataframe.frame.DataFrame` | 272 | `ab1f5f75296b49e2d8bb6647441e88ce47790dc86cf8a4a093b4f89b03ad8da1` |
| weekly player data | `nflreadpy.load_player_stats(seasons=2026, summary_level='week')` | `polars.dataframe.frame.DataFrame` | 2,294 | `46c370d1bb2df3e5fbc34403e78cb85cf8a19c12329672076cd9c3542f2da845` |

The observed schedule columns were:

```text
game_id, season, game_type, week, gameday, weekday, gametime, away_team,
away_score, home_team, home_score, location, result, total, overtime,
old_game_id, gsis, nfl_detail_id, pfr, pff, espn, ftn, away_rest, home_rest,
away_moneyline, home_moneyline, spread_line, away_spread_odds,
home_spread_odds, total_line, under_odds, over_odds, div_game, roof, surface,
temp, wind, away_qb_id, home_qb_id, away_qb_name, home_qb_name, away_coach,
home_coach, referee, stadium_id, stadium
```

The observed weekly player-data columns were:

```text
player_id, player_name, player_display_name, position, position_group,
headshot_url, season, week, season_type, game_id, team, opponent_team,
completions, attempts, passing_yards, passing_tds, passing_interceptions,
sacks_suffered, sack_yards_lost, sack_fumbles, sack_fumbles_lost,
passing_air_yards, passing_yards_after_catch, passing_first_downs, passing_epa,
passing_cpoe, passing_2pt_conversions, pacr, passing_10, passing_16, passing_20,
passing_40, carries, rushing_yards, rushing_tds, rushing_fumbles,
rushing_fumbles_lost, rushing_first_downs, rushing_epa,
rushing_2pt_conversions, rushing_10, rushing_12, rushing_20, rushing_40,
receptions, targets, receiving_yards, receiving_tds, receiving_fumbles,
receiving_fumbles_lost, receiving_air_yards, receiving_yards_after_catch,
receiving_first_downs, receiving_epa, receiving_2pt_conversions, receiving_10,
receiving_16, receiving_20, receiving_40, racr, target_share, air_yards_share,
wopr, special_teams_tds, def_tackles_solo, def_tackles_with_assist,
def_tackle_assists, def_tackles_for_loss, def_tackles_for_loss_yards,
def_fumbles_forced, def_sacks, def_sack_yards, def_qb_hits, def_interceptions,
def_interception_yards, def_pass_defended, def_tds, def_fumbles, def_safeties,
def_punt_blocks, def_pat_blocks, def_fg_blocks, def_2pt_atts, def_2pt_made,
misc_yards, fumble_recovery_own, fumble_recovery_yards_own,
fumble_recovery_opp, fumble_recovery_yards_opp, fumble_recovery_tds,
penalties, penalty_yards, fumbles_forced_by_opp, fumbles_not_forced,
fumbles_out_of_bounds, fumbles_total, fumbles_lost_total, punt_returns,
punt_return_yards, kickoff_returns, kickoff_return_yards, fg_made, fg_att,
fg_missed, fg_blocked, fg_long, fg_pct, fg_made_0_19, fg_made_20_29,
fg_made_30_39, fg_made_40_49, fg_made_50_59, fg_made_60_, fg_missed_0_19,
fg_missed_20_29, fg_missed_30_39, fg_missed_40_49, fg_missed_50_59,
fg_missed_60_, fg_made_list, fg_missed_list, fg_blocked_list,
fg_made_distance, fg_missed_distance, fg_blocked_distance, pat_made, pat_att,
pat_missed, pat_blocked, pat_pct, gwfg_made, gwfg_att, gwfg_missed,
gwfg_blocked, gwfg_distance, pt_att, pt_blocked, pt_long, pt_yards,
pt_inside_20, pt_out_of_bounds, pt_downed, pt_touchback, pt_fair_caught,
pt_returned, pt_return_yards, pt_return_tds, pt_net_yards, fantasy_points,
fantasy_points_ppr
```

For both results, the loader/result exposed no source or release URL (`source_reference: null`) and no source update/release metadata (`source_update_metadata: UNKNOWN`). Retrieval timestamps are probe evidence, not inferred source update times.

Any future compact export schema is proposed work until its source columns have been inspected and its definitions accepted. A future export-validation gate must separately establish schema mapping, identifiers, week coverage/completeness, value semantics, reproducibility, and official NFL Game Book reconciliation.

## Metadata truthfulness

Loader signatures are discovered from the installed module at runtime. A repository or documentation URL is not treated as release metadata. Source or release references are recorded only when directly attached to the loader/result. Missing update or release metadata stays `UNKNOWN`; it is never inferred from retrieval time, package version, GitHub history, or the season requested.

The generated manifest is local evidence under the ignored `output/` directory. Raw schedule or player-stat rows are never written to the repository.

## Acceptance boundary

A successful source probe means only that the two loaders returned supported, non-empty frames that could be described and hashed. Week completeness and export validation remain visibly `NOT_EVALUATED`. A successful source probe is not a validated weekly export and is not evidence that any particular NFL week is complete.
