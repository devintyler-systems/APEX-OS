# In-Season Perplexity Handoff v1.2.1

Status: the earlier v1.2 Week 2 artifact is superseded because its cutoff preceded frozen retrieval. Only a corrected v1.2.1 export whose manifest passes the cutoff and immutable-replay rules may be attached. This is not a runtime Perplexity integration and does not validate any other week or future corrected release.

## Evidence boundary

Perplexity project analysis may use only the compact attached `player_week.csv` together with its passing `manifest.json`. The attachment must identify the exact run ID, source/release metadata, input/output hashes, repository SHA, week-completeness result, official-record reconciliation result, and export-validation result. A live loader response, source-probe `PASS`, documentation text, GitHub page, or unaccompanied CSV is not sufficient evidence.

The accepted v1 output is game-granular and preserves source `game_id`, `player_id`, team abbreviation, opponent abbreviation, and selected raw box-score counts. It contains no availability inference, recommendations, projections, betting outputs, routes, charting, pressure attribution, DraftOS priors, EPA, fantasy points, share metrics, or derived formulas. `team_week.csv` is intentionally blocked because no approved complete team-stat source was established.

The Week 2 data passed exact coverage of 16 scheduled games, 16 official NFL `FINAL` records, and 16 weekly-player-data games. Two scores and three player lines were manually reviewed against official NFL Game Books, then recorded in `docs/evidence/issue_1_2026_week2_reconciliation_v1.json`. The validator compares those recorded values with source rows. It does not fetch and hash every referenced PDF during replay, so the manual review and recorded PDF hashes remain explicit operational evidence rather than an automated independent PDF check.

Source publication/update metadata is distinct from retrieval time. nflverse release asset update times are recorded from the release API; the official NFL scoreboard and Game Book publication/update times remain `UNKNOWN` when not independently exposed. `UNKNOWN` is never replaced with retrieval or human-review time. A PASS cutoff must be valid UTC and at or after frozen retrieval and the recorded human review.

## Research and documentation references

These links remain research/documentation references only. They are not vendored content, scraped sources, or Perplexity runtime integrations:

- [https://nflverse.nflverse.com/articles/dictionary.html](https://nflverse.nflverse.com/articles/dictionary.html)
- [https://github.com/nflverse/nflverse-data/releases](https://github.com/nflverse/nflverse-data/releases)
- [https://github.com/nflverse/nflreadpy](https://github.com/nflverse/nflreadpy)
- [https://support.nfl.com/hc/en-us/articles/35869678028180-Game-Books](https://support.nfl.com/hc/en-us/articles/35869678028180-Game-Books)

GitHub is methodology, version history, and provenance—not a live data service or proof that a requested week is complete. The local Python loader retrieves named release assets, and the gate separately records their exact asset URLs, tags, digests, and update times. A GitHub release page alone never passes availability, freshness, or completeness.

## Attachment and correction handling

Attach only the compact export and its matching manifest. Do not attach raw Parquet, scoreboard HTML, or Game Book PDFs. Verify both file bytes against the exact run identity before analysis. Reconciliation evidence, cutoff, source publication metadata, and correction lineage are decision inputs: changing any of them requires a new run identity and cannot reuse an older PASS manifest. Existing run files are never overwritten. An outage, missing or repeated official record, missing release metadata, partial weekly publication, cutoff conflict, checksum conflict, immutable-manifest conflict, or unresolved official discrepancy must remain `BLOCKED`.

## Remaining scope boundary

No future week becomes validated automatically. Each run must repeat the live source metadata check, full official-final coverage check, frozen replay, and official Game Book reconciliation. New fields, derived metrics, team outputs, alternate identifiers, or joins require a new contract decision before implementation.
