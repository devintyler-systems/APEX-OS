# In-Season Perplexity Handoff v1.2

Status: one compact 2026 regular-season Week 2 player export passed the local v1.2 gates. This is not a runtime Perplexity integration and does not validate any other week or future corrected release.

## Evidence boundary

Perplexity project analysis may use only the compact attached `player_week.csv` together with its passing `manifest.json`. The attachment must identify the exact run ID, source/release metadata, input/output hashes, repository SHA, week-completeness result, official-record reconciliation result, and export-validation result. A live loader response, source-probe `PASS`, documentation text, GitHub page, or unaccompanied CSV is not sufficient evidence.

The accepted v1 output is game-granular and preserves source `game_id`, `player_id`, team abbreviation, opponent abbreviation, and selected raw box-score counts. It contains no availability inference, recommendations, projections, betting outputs, routes, charting, pressure attribution, DraftOS priors, EPA, fantasy points, share metrics, or derived formulas. `team_week.csv` is intentionally blocked because no approved complete team-stat source was established.

The retained Week 2 run passed exact coverage of 16 scheduled games, 16 official NFL `FINAL` records, and 16 weekly-player-data games. Two scores and three player lines were independently reconciled against official NFL Game Books. The evidence file is `docs/evidence/issue_1_2026_week2_reconciliation_v1.json`.

Source publication/update metadata is distinct from retrieval time. nflverse release asset update times are recorded from the release API; the official NFL scoreboard publication/update time remains `UNKNOWN` because the page did not independently expose one. `UNKNOWN` is never replaced with retrieval time.

## Research and documentation references

These links remain research/documentation references only. They are not vendored content, scraped sources, or Perplexity runtime integrations:

- [https://nflverse.nflverse.com/articles/dictionary.html](https://nflverse.nflverse.com/articles/dictionary.html)
- [https://github.com/nflverse/nflverse-data/releases](https://github.com/nflverse/nflverse-data/releases)
- [https://github.com/nflverse/nflreadpy](https://github.com/nflverse/nflreadpy)
- [https://support.nfl.com/hc/en-us/articles/35869678028180-Game-Books](https://support.nfl.com/hc/en-us/articles/35869678028180-Game-Books)

GitHub is methodology, version history, and provenance—not a live data service or proof that a requested week is complete. The local Python loader retrieves named release assets, and the gate separately records their exact asset URLs, tags, digests, and update times. A GitHub release page alone never passes availability, freshness, or completeness.

## Attachment and correction handling

Attach only the compact export and its matching manifest. Do not attach raw Parquet, scoreboard HTML, or Game Book PDFs. Verify the CSV byte hash against the manifest before analysis. If upstream data changes, use the new versioned run and correction lineage; never silently replace a prior attachment. An outage, missing official record, missing release metadata, partial weekly publication, checksum conflict, or unresolved official discrepancy must remain `BLOCKED` and must not degrade into a stale or inferred PASS.

## Remaining scope boundary

No future week becomes validated automatically. Each run must repeat the live source metadata check, full official-final coverage check, frozen replay, and official Game Book reconciliation. New fields, derived metrics, team outputs, alternate identifiers, or joins require a new contract decision before implementation.
