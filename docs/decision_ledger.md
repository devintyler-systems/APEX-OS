# Decision Ledger

## 2026-09-29 — SB-DUP-EXC-1 sparse scoreboard alias exception

- Status: approved structural design; implemented pending verification.
- Base: `origin/main` at `2e20a7e6680d3511623ee84eef0c8f0ce0a465a4`.
- Decision: distinguish one sparse presentation alias from a second authoritative official record only when the complete/sparse shape satisfies every v1.3.0 condition, including nonblank equal state, exact href/team agreement, selected-week complete-ID uniqueness, and DOM-order independence.
- Versions: contract `1.3.0`, parser `1.2.0`, CSV schema unchanged at `1.2.1`.
- Failure policy: all ten `SB-DUP-EXC-1` reason codes fail closed before persistence; degraded-mode and stale-banner behavior are unchanged.
- Scope: scoreboard contract addendum, parser, tests, minimal fixtures, and this entry only.
