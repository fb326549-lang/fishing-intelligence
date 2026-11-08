# Historical CWA tide forecast verification engine — 2026-11-09

## Branch safety
- Repository: fb326549-lang/fishing-intelligence
- Development branch: p1-foundation
- Persistent tide data branch: tide-history
- Production main branch was not modified.
- Latest CWA collection and analysis run: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42534205544
- Latest offline regression run: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42534205579

## Implementation
New collector:
- P1/collector/analyze_cwa_tide_forecast_history.py

The analyzer reads:
- tide-history/data/observed_tides.jsonl
- tide-history/data/forecast_vintages.jsonl
- P1/stations/cwa_tide_observation_forecast_pairing.csv

It produces persistent outputs on the tide-history branch:
- data/analysis/event_matches.csv
- data/analysis/accuracy_by_lead.csv
- data/analysis/analysis_summary.json

Only six explicitly paired mainland tide stations are evaluated. Observed TideHeight metres and forecast AboveTWVD centimetres are compared in TWVD2001. The issue time is taken from the archived CWA fetch timestamp, not the later observation collection time. Forecasts issued at or after the target event are excluded.

Lead-time groups:
- 00-06h
- 06-12h
- 12-24h
- 24-48h
- 48h+

For every valid match, the engine records signed and absolute height error, signed and absolute timing error, forecast issue time, target event time, observed extremum time, station, region, pairing distance, tide type, and snapshot ID. It aggregates MAE and median absolute error by station, region, tide type and lead-time group.

The same observed extremum may verify multiple forecast vintages intentionally, because each vintage represents a different forecast lead time. Forecasts issued after the target event are never used as historical predictions.

## Latest real-data result
Latest analysis summary:
- Observation history records: 288 (48 samples at each of six stations).
- Forecast vintage records: 16,455.
- Forecast snapshots: 5.
- Median observed sampling interval: 60 minutes at all six stations.
- Matched forecast/observed extrema: 0.
- Eligible forecast events issued before their target event in the current overlap window: 0.
- Accuracy summary groups: 0.

This does NOT mean forecast accuracy is zero or that the CWA forecast is inaccurate. The available observations cover a recent past window, while the forecasts currently available for those target times were fetched at or after the target events. They cannot be treated as advance forecasts. The engine correctly rejects these retrospective records rather than creating a false accuracy score.

Consequently, event_matches.csv and accuracy_by_lead.csv currently contain headers only. No MAE or timing-accuracy claim is published.

## Test coverage
Latest offline regression suite: 18 tests passed.
- Synthetic test verifies a forecast issued 12–24 hours before a high-tide event.
- Confirms TWVD height conversion and 0.20 m absolute height error.
- Confirms a forecast fetched after the target event is excluded.
- Confirms empty history files fail safely.
- Existing marine parsing, tide mapping, archive idempotency, and datum tests remain passing.

## Daily collection readiness
The CWA workflow now includes a daily cron trigger at 23:00 UTC (07:00 Taiwan time), as well as manual workflow_dispatch and development-branch path triggers.

Important GitHub limitation: scheduled workflows run only from the repository's default branch. The schedule is prepared in p1-foundation but will not execute daily until the workflow is reviewed and merged to the default branch. No merge or change to main has been performed.

## Next validation gate
1. Review and approve the workflow merge to the default branch when ready, so daily snapshots can accumulate.
2. Allow forecast vintages to be collected before their target events and observed records to arrive afterward.
3. Wait for a meaningful sample count across multiple days before publishing MAE or timing error.
4. Keep the analysis descriptive; do not feed these early results into fish activity or catch-probability scores.
