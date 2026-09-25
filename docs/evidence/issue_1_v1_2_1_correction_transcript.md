# Issue #1 v1.2.1 validation-correction transcript

This is new correction evidence. The original v1.2 transcript remains separately committed and explicitly marked superseded; its historical outputs were not rewritten.

## Starting state

```text
> git status --short
[no output]
exit 0

> git branch --show-current
issue-1-in-season-source-contract
exit 0

> git rev-parse HEAD
a80ae1b3522773621a963ee522fcd59d7459edd2
exit 0
```

## Observed timestamp defect

```text
former cutoff_utc:              2026-09-25T20:51:49Z
human review checked_at_utc:    2026-09-25T20:51:49Z
frozen retrieval_utc:           2026-09-25T21:00:50.602044Z
schedules asset_updated_at:     2026-09-25T20:46:50Z
weekly asset_updated_at:        2026-09-25T14:37:31Z
official scoreboard publication: UNKNOWN
official Game Book publication:  UNKNOWN
corrected cutoff_utc:           2026-09-25T21:00:50.602044Z
```

The corrected cutoff is the latest observed evidence time. Asset updates remain distinct from retrieval; human review remains distinct from unknown official-document publication.

## Frozen inputs

All four required files returned `True` from `Test-Path` under `output/in_season/frozen/2026/retrieval_20260925T210500Z/`.

```text
schedules.parquet:          6E3269AE6228F9E925CC28B02AC5B118CC727F8218B6B04F7B282DAA13EF9005
weekly_player_data.parquet: CE4F3FF04053CE43969132683755B1AD8C5812B80519DCA3827E57A24C086E8A
official_scoreboard.html:   925727BCDE66C4BEB856227AB4210C658D8AA7244909B5C155097615E9964A58
reconciliation JSON bytes:  C529925947C5FE4833E1829D5723454380269C5BF08A0E6D430B7C6EB3AE28D8
canonical evidence digest:  136c4f797fd959f9a958fd54cc36f9b6c1b21fdaf60186652da07abc0f853610
```

## Former cutoff negative execution

```text
> python scripts/export_in_season_week.py --season 2026 --week latest --frozen-dir output/in_season/frozen/2026/retrieval_20260925T210500Z --reconciliation-evidence docs/evidence/issue_1_2026_week2_reconciliation_v1.json --output-root output/in_season/correction_invalid_cutoff --cutoff-utc 2026-09-25T20:51:49Z --supersedes-run-id v1-542491788447b31f --correction-reason "Correct invalid pre-retrieval cutoff semantics"
{
  "detail": "cutoff_utc=2026-09-25T20:51:49Z precedes retrieval_utc=2026-09-25T21:00:50.602044Z",
  "export_validation_status": "BLOCKED",
  "reason_code": "KNOWLEDGE_CUTOFF_PRECEDES_EVIDENCE"
}
exit 1

> Test-Path -LiteralPath output/in_season/correction_invalid_cutoff
False
exit 0
```

No PASS artifact or parent output directory was written.

## Corrected pre-commit frozen replay

This exact command was run twice:

```text
python scripts/export_in_season_week.py --season 2026 --week latest --frozen-dir output/in_season/frozen/2026/retrieval_20260925T210500Z --reconciliation-evidence docs/evidence/issue_1_2026_week2_reconciliation_v1.json --output-root output/in_season/corrected_v121_precommit --cutoff-utc 2026-09-25T21:00:50.602044Z --supersedes-run-id v1-542491788447b31f --correction-reason "Correct invalid pre-retrieval cutoff semantics"
```

```text
mode=frozen_replay
selected_week=2
run_id=v1-cd491f2339e6f013
replay_identical=false / true
player_week_rows=1106
player_week_sha256=a9b6bd7dd637651959888df96987040f6a6196333ccf441dfcf259fed632b475
week_completeness_status=PASS
official_record_reconciliation_status=PASS
export_validation_status=PASS
exit 0 / 0

player_week.csv SHA-256: A9B6BD7DD637651959888DF96987040F6A6196333CCF441DFCF259FED632B475
manifest.json SHA-256:   B3CECE6507E4AE8E864FEA6027E46658DC524D214CF5F28F667C736D90F8E268
supersedes_run_id:        v1-542491788447b31f
```

This pre-commit run used starting repository SHA `a80ae1b3522773621a963ee522fcd59d7459edd2`. The final post-commit replay is executed without further repository edits so its manifest binds the corrective commit SHA; its run ID and hashes are reported in draft PR #2 and the handoff.

## Required verification

```text
> python -m pip install -r requirements-in-season.txt
Requirement already satisfied: nflreadpy==0.1.5 ...
Requirement already satisfied: polars==1.38.1 ...
Requirement already satisfied: requests==2.32.5 ...
exit 0

> python -B -m pytest tests/in_season/test_source_probe.py tests/in_season/test_weekly_export.py -q
...............................................                          [100%]
47 passed in 0.87s
exit 0

> python -B -m pytest -q
.................................................................        [100%]
65 passed in 0.94s
exit 0

> git diff --check
[line-ending conversion warnings only; no whitespace errors]
exit 0
```

Negative coverage includes early/malformed/naive cutoffs, inconsistent reviewed values, changed references/PDF hashes/review time/evidence version/cutoff/source metadata/correction lineage, identical and conflicting scoreboard duplicates, altered stored manifest bytes, and exact identical replay.
