# In-Season Perplexity Handoff v1.1

Status: research/documentation handoff only; not a runtime integration and not a validated weekly export.

## Evidence boundary

Perplexity project analysis may use only a compact attached export accompanied by a future manifest that passes the not-yet-implemented week-completeness, schema, provenance, and export-validation gates. A live loader response, a source-probe `PASS`, documentation text, or a repository link is not a substitute for that attached evidence.

The current probe records observed frame columns, types, row counts, checksums, invocations, timestamps, and directly exposed metadata. Those observed values are discovery evidence only. Proposed downstream fields must remain labeled proposed until their actual upstream columns and semantics are inspected and accepted. Metadata not exposed by the loader/result remains `UNKNOWN`.

Official NFL Game Book reconciliation remains an open Issue #1 acceptance gate. Until that gate and the later export gates pass, no weekly export and no week may be described as validated.

## Research and documentation references

The following links are research/documentation references only. They are not software dependencies, vendored content, scraped sources, or runtime integrations:

- [https://nflverse.nflverse.com/articles/dictionary.html](https://nflverse.nflverse.com/articles/dictionary.html)
- [https://github.com/nflverse/nflverse-data/releases](https://github.com/nflverse/nflverse-data/releases)
- [https://github.com/nflverse/nflreadpy](https://github.com/nflverse/nflreadpy)
- [https://support.nfl.com/hc/en-us/articles/35869678028180-Game-Books](https://support.nfl.com/hc/en-us/articles/35869678028180-Game-Books)

GitHub is used for methodology, version history, and provenance. It is not a live data service. No workflow should treat a GitHub page or release listing as proof that a season/week dataset is available, current, complete, or reconciled.

## Out of scope

This handoff does not authorize Perplexity or the local probe to infer injury availability, incorporate news, use routes/charting/pressure attribution, generate projections or betting outputs, consult DraftOS priors, define player-week mappings, or make recommendations.
