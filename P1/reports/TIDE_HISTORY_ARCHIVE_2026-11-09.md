# CWA tide history archive — 2026-11-09

## Status
- Main branch remains unchanged.
- Development branch: p1-foundation.
- Persistent append-only storage branch: tide-history.
- Three history snapshots were successfully committed; the latest archive write completed successfully.
- Latest successful CWA collection with concurrent-push retry: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42533737664
- Offline regression suite: 16 tests passed: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42533647202

## Storage design
The CWA workflow checks out the dedicated tide-history branch, runs the CWA collectors, and appends data under data/:
- observed_tides.jsonl: O-B0075-001 TideHeight records for the six explicitly paired mainland stations.
- forecast_vintages.jsonl: F-A0021-001 forecast event vintages for all mapped six-region locations (not only the six verification stations).
- collection_runs.jsonl: per-run ingestion counts and snapshot identifiers.
- history_summary.json: current record counts, paired stations, and archived forecast location IDs.

Observation records are deduplicated by station ID, valid time and TideHeight value. If CWA later corrects an observation value, the changed value is appended as a separate revision; old values are never overwritten. Forecast events are retained by unique GitHub Actions snapshot ID, so every fetch is a distinct forecast vintage even when the valid time is unchanged.

All vertical height datums are stored separately. No conversion is performed during archival. No interpolation, regional averaging, or fishing/catch score is produced.

## First two successful snapshots
Latest verified history summary at the time of this report:
- Successful collection runs: 3
- Unique observed TideHeight records/revisions: 288
- Forecast vintage event records: 8,597
- Matched mainland tide stations: 6
- Matched verification forecast locations: 6
- Archived six-region forecast locations: 32
- Forecast events in each complete run: 3,929
- New forecast vintage records in the latest run: 3,929
- New observed revisions in the latest run: 0 (the rolling observation window overlapped prior snapshots with unchanged values)

History files:
- data/observed_tides.jsonl
- data/forecast_vintages.jsonl
- data/collection_runs.jsonl
- data/history_summary.json

History branch: https://github.com/fb326549-lang/fishing-intelligence/tree/tide-history/data

## Reliability fixes
Two concurrent workflow runs initially attempted to push to tide-history from the same old branch head. The first write succeeded and the other push was rejected as non-fast-forward. The workflow was updated to:
1. serialize future CWA history writes with a GitHub Actions concurrency group;
2. on a non-fast-forward push, fetch the latest tide-history head, reset the worktree, rebuild the same append-only snapshot from the already-fetched source files, and retry up to three times.

The history JSONL archive remains idempotent for repeated observation values and keeps forecast vintages distinct by run ID.

## Automation boundary
The workflow supports workflow_dispatch and relevant pushes on p1-foundation. It is not yet a daily scheduled job. GitHub scheduled workflows are evaluated from the repository's default branch; enabling a real daily schedule requires an approved workflow merge to the default branch. No such merge has been performed, so main remains untouched.

## Next steps
1. Accumulate more daily or manually dispatched snapshots.
2. Once a longer overlap history exists, compute MAE, median absolute error, timing error, and sample counts separately by station, tide type and forecast lead time.
3. Do not use the first few matched events to tune species/catch scores.
