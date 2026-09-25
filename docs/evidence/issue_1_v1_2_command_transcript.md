# Issue #1 v1.2 command transcript

Captured 2026-09-25 UTC. Exit codes and output are literal unless explicitly summarized. No secrets or raw source rows are included.

## Starting state

```text
> git branch --show-current
issue-1-in-season-source-contract
exit 0

> git rev-parse HEAD
b4414b25860913284a66ac93574825acd92c4a61
exit 0

> git rev-parse origin/main
1b775e9b474245cd9571213d1a4440f7cc85e735
exit 0

> git rev-parse origin/issue-1-in-season-source-contract
b4414b25860913284a66ac93574825acd92c4a61
exit 0
```

`git status --short` was empty. PR #2 was draft/open, base `main`, head `issue-1-in-season-source-contract`, head SHA `b4414b25860913284a66ac93574825acd92c4a61`, URL `https://github.com/devintyler-systems/APEX-OS/pull/2`. Issue #1, the full existing probe/tests/docs, requirements, ignore rules, exports, and `scripts/run_weekly_update.py` were inspected before edits.

## Runtime

```text
> python --version
Python 3.12.10
exit 0

> python -m pip --version
pip 26.2.1 from C:\Users\burly\AppData\Local\Programs\Python\Python312\Lib\site-packages\pip (python 3.12)
exit 0

> python -c "import importlib.metadata as m; print('nflreadpy='+m.version('nflreadpy')); print('polars='+m.version('polars')); print('requests='+m.version('requests'))"
nflreadpy=0.1.5
polars=1.38.1
requests=2.32.5
exit 0

> python -m pip install -r requirements-in-season.txt
Requirement already satisfied: nflreadpy==0.1.5 in C:\Users\burly\AppData\Local\Programs\Python\Python312\Lib\site-packages (from -r requirements-in-season.txt (line 1)) (0.1.5)
Requirement already satisfied: polars==1.38.1 in C:\Users\burly\AppData\Local\Programs\Python\Python312\Lib\site-packages (from -r requirements-in-season.txt (line 2)) (1.38.1)
Requirement already satisfied: requests==2.32.5 in C:\Users\burly\AppData\Local\Programs\Python\Python312\Lib\site-packages (from -r requirements-in-season.txt (line 3)) (2.32.5)
[transitive packages also reported Requirement already satisfied]
exit 0
```

## Existing source probe

```text
> python -m pytest tests/in_season/test_source_probe.py -q
..........                                                               [100%]
10 passed in 0.14s
exit 0

> python scripts/probe_in_season_sources.py --season 2026
manifest_path=C:\APEX-OS\output\in_season\source_probe_2026.json
probe_status=PASS; source_availability_status=AVAILABLE
schedules=AVAILABLE; weekly_player_data=AVAILABLE
week_completeness_status=NOT_EVALUATED
export_validation_status=NOT_EVALUATED
exit 0
```

Probe manifest SHA-256: `5CF4BE8C57147E02C2439B5615314E79DB72E00997E24E91117B07539C0212C2`. It observed 272 schedule rows and 2,294 weekly rows, both Polars frames. Loader-exposed source/update metadata remained `null`/`UNKNOWN`.

## Frozen and official evidence

Retained ignored capture: `output/in_season/frozen/2026/retrieval_20260925T210500Z/`.

```text
frozen_manifest.json: 90A64DCF36D6A4B962762B8DB94275C3694FD0B313D998AFEEEDB332DD2B50E2
schedules.parquet: 6e3269ae6228f9e925cc28b02ac5b118cc727f8218b6b04f7b282daa13ef9005
weekly_player_data.parquet: ce4f3ff04053ce43969132683755b1ad8c5812b80519dca3827e57a24c086e8a
official_scoreboard.html: 925727bcde66c4beb856227ab4210c658d8aa7244909b5c155097615e9964a58
retrieval UTC: 2026-09-25T21:00:50.602044Z
```

Publication metadata: schedules tag `schedules`, updated `2026-09-25T20:46:50Z`, digest `sha256:19005e44ad9eb4bfeafb5b4ebccebb1134075cdfd584cf2f3b87ee2c2141f93a`; weekly tag `stats_player`, updated `2026-09-25T14:37:31Z`, digest `sha256:301ff65217abd67d6eb20c3514ce640ac17d4f3eddebd5d7c356fb6aa21834ed`. Official scoreboard publication/update time: `UNKNOWN`.

`gh api repos/nflverse/nflverse-data/license` reported `CC-BY-4.0`. Official PDFs visibly carried restrictive copyright text. `pdfinfo` was unavailable (`pdfinfo: The term 'pdfinfo' is not recognized...`), so installed `pdfplumber` and `pypdfium2` were used for extraction/rendering.

```text
IND at KC Game Book PDF: DDE28094FCB4837CDFA9B058E566CE50F0DACA43C74FF623C15A3DCA4980113E
DET at BUF Game Book PDF: 6E76C9AEE29A47ACC158691CC65C7AF0F5C8A12FCAFF688E887F4F67D9956E11
reconciliation evidence: C529925947C5FE4833E1829D5723454380269C5BF08A0E6D430B7C6EB3AE28D8
```

Compared values: DET 31–BUF 41; IND 30–KC 33; Patrick Mahomes 32/47, 382 passing yards, 3 TD, 0 INT, 2 carries/17 yards; Josh Allen 20/31, 248 passing yards, 3 TD, 0 INT, 14 carries/69 yards/2 TD; James Cook 21 carries/135 yards/1 TD and 3 targets/1 reception/4 yards. All matched. Exact references/pages/IDs are in `issue_1_2026_week2_reconciliation_v1.json`.

## Live latest-week command

```text
> python scripts/export_in_season_week.py --season 2026 --week latest --capture-dir output/in_season/frozen/2026/retrieval_20260925T210500Z --reconciliation-evidence docs/evidence/issue_1_2026_week2_reconciliation_v1.json --output-root output/in_season/latest_live --cutoff-utc 2026-09-25T20:51:49Z
mode=live
selected_week=2
manifest_path=C:\APEX-OS\output\in_season\latest_live\season=2026\week=2\run=v1-c70cb6fc51c57add\manifest.json
run_id=v1-c70cb6fc51c57add
replay_identical=false
player_week_rows=1106
player_week_sha256=a9b6bd7dd637651959888df96987040f6a6196333ccf441dfcf259fed632b475
week_completeness_status=PASS
official_record_reconciliation_status=PASS
export_validation_status=PASS
exit 0
```

Manifest evidence: 16 scheduled/official-final/weekly games; Week 3 rejected at 1/16 published games; one null-player-ID row excluded; `team_week` blocked by `NO_APPROVED_COMPLETE_TEAM_STAT_SOURCE`; no derived fields/denominators.

## Frozen replay

Both replay commands below exited 0 with `selected_week=2`, `run_id=v1-c70cb6fc51c57add`, 1,106 rows, all three gates `PASS`, and CSV SHA-256 `a9b6bd7dd637651959888df96987040f6a6196333ccf441dfcf259fed632b475`:

```text
python scripts/export_in_season_week.py --season 2026 --week latest --frozen-dir output/in_season/frozen/2026/retrieval_20260925T210500Z --reconciliation-evidence docs/evidence/issue_1_2026_week2_reconciliation_v1.json --output-root output/in_season/latest_replay_a --cutoff-utc 2026-09-25T20:51:49Z
python scripts/export_in_season_week.py --season 2026 --week latest --frozen-dir output/in_season/frozen/2026/retrieval_20260925T210500Z --reconciliation-evidence docs/evidence/issue_1_2026_week2_reconciliation_v1.json --output-root output/in_season/latest_replay_b --cutoff-utc 2026-09-25T20:51:49Z
```

```text
replay A player_week.csv: A9B6BD7DD637651959888DF96987040F6A6196333CCF441DFCF259FED632B475
replay B player_week.csv: A9B6BD7DD637651959888DF96987040F6A6196333CCF441DFCF259FED632B475
replay A manifest.json: 048147E28ADB6C75FF6E5953ED0165EE2E42F77983416CDF136D55F7389C27A4
replay B manifest.json: 048147E28ADB6C75FF6E5953ED0165EE2E42F77983416CDF136D55F7389C27A4
```

## Tests

```text
> python -B -m pytest tests/in_season/test_source_probe.py tests/in_season/test_weekly_export.py -q
....................................                                     [100%]
36 passed in 0.52s
exit 0

> python -B -m pytest -q
......................................................                   [100%]
54 passed in 0.64s
exit 0
```

`-B` prevents test imports from rewriting tracked bytecode. One earlier full-suite run rewrote `draftos/__pycache__/config.cpython-312.pyc`; it was restored exactly from `HEAD`, and no DraftOS path is staged.

## Supersession note — v1.2.1 correction

This transcript is retained as historical evidence and has not been rewritten to appear as output from the corrected validator. Its commands used `cutoff_utc=2026-09-25T20:51:49Z` with frozen `retrieval_utc=2026-09-25T21:00:50.602044Z`. That as-of claim is invalid under v1.2.1 and the referenced PASS runs are superseded, including `v1-542491788447b31f`. Do not attach or analyze them as passing exports. The corrected commands, failure evidence, new run identity, hashes, and explicit supersession lineage are retained separately in `docs/evidence/issue_1_v1_2_1_correction_transcript.md`.
