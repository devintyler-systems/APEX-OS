# In-Season Official Scoreboard Source Contract v1.3.0 Addendum

Artifact: `in-season-official-scoreboard-source-contract`  
Type: structural  
Rule ID: `SB-DUP-EXC-1`  
Base contract: `docs/in_season_source_contract_v1.md` (`v1.2.1`)  
Parser version: `1.2.0`  
Schema version: `1.2.1` (unchanged)

This addendum narrows what constitutes a repeated official record. It does not weaken final-state, schedule-coverage, reconciliation, freshness, immutable-run, degraded-mode, or stale-banner gates. All v1.2.1 rules remain effective except the repeated-link interpretation replaced below.

## Decision

Official NFL score pages may present one game through one complete Game Center link and one sparse presentation alias. A presentation alias is not a second official game when every condition in `SB-DUP-EXC-1` passes. Resolution is set-based over the entire selected week and must not depend on DOM link order.

### Accepted shape

For one away/home pair:

- Exactly one complete link has a nonblank, exact-case `gameId` and a nonblank `gameState`.
- Zero or one sparse link omits exact-case `gameId` and has a nonblank `gameState` equal to the complete link after normalization.
- Complete and sparse links have identical href values and identical mapped away/home teams.
- Both mapped teams must be present. A selected-week link whose href cannot supply both teams blocks.
- Optional analytics team fields do not create missing values. Every team field present on either link must agree with the href and with the corresponding field on the other link when both carry it.
- The complete link's `gameId` is unique across all complete links in the selected week. Week-wide uniqueness is evaluated before pair emission, including links outside the pair.
- A complete link without an alias remains the accepted baseline.

The differently cased presentation field `gameID` does not satisfy the complete-link `gameId` requirement and does not participate in complete-ID uniqueness. It may be retained as parser evidence for a sparse alias.

### Emission

- Emit exactly one `official_games` record per accepted away/home pair.
- Emit deterministic parser evidence for the complete record and, when present, the sparse record with `role=alias_of:<gameId>`.
- Set `alias_counted_as_game=false` on sparse evidence.
- Do not emit a sparse alias as an official game.
- Evidence ordering and the emitted official game must be identical when complete and sparse DOM order is reversed.

### Fail-closed reason codes

- `DUP_TWO_COMPLETE`: two complete links exist for one pair, even if identical.
- `DUP_DISTINCT_NONNULL_IDS`: complete links for one pair assert distinct nonblank IDs.
- `DUP_STATE_MISMATCH`: complete and sparse states differ.
- `DUP_HREF_OR_TEAM_MISMATCH`: href, mapped teams, or corresponding analytics team fields disagree.
- `DUP_ALIAS_ONLY`: a sparse link has no complete link.
- `DUP_ALIAS_STATE_BLANK`: a sparse link has a blank or missing state.
- `DUP_GAMEID_NOT_WEEK_UNIQUE`: one complete `gameId` occurs in more than one selected-week pair.
- `DUP_TWO_SPARSE`: more than one sparse alias exists for a pair.
- `ANALYTICS_MALFORMED`: selected analytics are invalid JSON, not an object, or contain invalid required values.
- `UNEXPECTED_EXTRA_LINK`: an exact selected-week sparse link carries an alternate identity that cannot resolve to its pair's complete record.

Every reason blocks before persistence and leaves no export. Existing degraded-mode and stale-banner behavior is unchanged.

## Version and replay boundary

This structural interpretation increments the contract from `1.2.1` to `1.3.0` and the parser from `1.1.0` to `1.2.0`. It does not change the `1.2.1` CSV schema. Contract and parser versions remain run-identity inputs, so a v1.3.0 run cannot reuse a v1.2.1 run identity or manifest.
