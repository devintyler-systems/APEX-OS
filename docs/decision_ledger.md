# Decision Ledger

## 2026-09-29 — SB-DUP-EXC-1 sparse scoreboard alias exception

- Status: approved structural design; implemented pending verification.
- Base: `origin/main` at `2e20a7e6680d3511623ee84eef0c8f0ce0a465a4`.
- Decision: distinguish one sparse presentation alias from a second authoritative official record only when the complete/sparse shape satisfies every v1.3.0 condition, including nonblank equal state, exact href/team agreement, selected-week complete-ID uniqueness, and DOM-order independence.
- Versions: contract `1.3.0`, parser `1.2.0`, CSV schema unchanged at `1.2.1`.
- Failure policy: all ten `SB-DUP-EXC-1` reason codes fail closed before persistence; degraded-mode and stale-banner behavior are unchanged.
- Scope: scoreboard contract addendum, parser, tests, minimal fixtures, and this entry only.

## 2026-09-30 — SB-DUP-EXC-1 manifest provenance boundary

- Status: approved bounded correction; implemented pending verification.
- Parent implementation: `62b7360ad73b3dd4c2b719e7d05fe44769d11900`.
- Decision: carry the selected scoreboard-contract mode into run identity and manifest construction. Contract `1.3.0` emits manifest schema `1.3.0` plus rule/applied-alias attribution; legacy `1.2.1` emits manifest schema `1.2.1` without those fields.
- Versions: contract remains `1.3.0`, parser `1.2.1`, manifest schema `1.3.0`, CSV schema unchanged at `1.2.1`.
- Reconciliation boundary: the unchanged JSON is a sampled official-PDF reconciliation of schedule/player assets, not a scoreboard reconciliation; `validate_reconciliation` continues to re-check its two game and three player observations on every export.
