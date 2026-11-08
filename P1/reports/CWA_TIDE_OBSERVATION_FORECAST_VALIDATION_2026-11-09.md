# CWA tide forecast vs observed tide diagnostic — 2026-11-09

## Branch and safety
- Repository: fb326549-lang/fishing-intelligence
- Development branch: p1-foundation
- Main branch was not modified.
- Latest verified full CWA workflow for the TWVD comparison implementation: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42532875126
- Latest verified offline test run: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42532881134

## Important vertical-datum correction

An initial diagnostic incorrectly compared observed TideHeight with forecast AboveChartDatum. The resulting 1.02 m difference was a datum mismatch and must not be interpreted as forecast error.

The CWA O-B0076-001 metadata describes mainland tide-station observations as referenced to Taiwan Vertical Datum 2001 (TWVD2001). The F-A0021-001 forecast provides AboveTWVD in centimetres. Therefore mainland comparisons must use:
- Observed O-B0075-001 TideHeight: metres, TWVD2001
- Forecast F-A0021-001 AboveTWVD: centimetres, TWVD2001, converted to metres

The CWA metadata also states that offshore-island tide stations may use local mean sea level rather than the mainland TWVD2001 reference. Island stations are therefore excluded from this mainland comparison.

Official CWA references:
- O-B0076-001 station metadata: https://opendata.cwa.gov.tw/dataset/forecast/O-B0076-001
- O-B0075-001 observations: https://opendata.cwa.gov.tw/dataset/all/O-B0075-001
- F-A0021-001 tide forecast: https://opendata.cwa.gov.tw/dataset/forecast/F-A0021-001
- CWA tide-station vertical reference explanation: https://cwa.venj.me/Data/service/notice/download/Publish_20210419100208.pdf

## Implementation

New files:
- P1/stations/cwa_tide_observation_forecast_pairing.csv
- P1/collector/compare_cwa_tide_observed_forecast.py

The pairing file explicitly links six mainland tide stations to CWA tide-forecast locations within 500 m. It records station/location IDs, region, distance, and comparison datum. A station/location pair is not inferred automatically at runtime. Stations over 500 m away and offshore-island stations are excluded.

The comparator:
1. Reads normalized O-B0075-001 tide observations.
2. Detects local observed high/low extrema from the sampled series.
3. Selects F-A0021-001 events for the paired location within the observed time window.
4. Converts AboveTWVD cm to metres.
5. Matches same-type extrema to forecast events within 120 minutes, without reusing a forecast or observed extremum.
6. Outputs event-level signed/absolute height and timing differences plus station-level sample/coverage summaries.

The CWA workflow now creates:
- output/cwa_tides/tide_observed_forecast_comparison.csv
- output/cwa_tides/tide_forecast_observation_comparison_summary.json

## Actual CWA run result

Workflow: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42532875126
Artifact: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42532875126/artifacts/13637913087

- Six mainland station/location pairs evaluated.
- Each station contributed 48 observed tide-height samples in the downloaded 48-hour window.
- Median observed sampling interval: 60 minutes.
- One forecast event fell within the observed window and was matched.
- Matched event: 烏石潮位站 C4U02 ↔ CWA location 10002040 宜蘭縣頭城鎮.
- Pair distance: 263 m.
- Forecast low tide: 2026-11-09 00:16, AboveTWVD = -0.71 m.
- Observed sampled low: 2026-11-09 01:00, TideHeight = -0.71 m.
- Absolute height difference: 0.00 m for this single matched event.
- Timing difference: 44 minutes; observed series was sampled hourly.

This is only one matched event. It is not a statistically meaningful forecast-accuracy estimate and must not be presented as proof of high accuracy. Five other pairs had no matched event in this short overlap window; one had a forecast event but no observed extremum match within the 120-minute tolerance.

## Automated tests

Latest offline tests: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42532881134
- 14 tests passed.
- Tests cover TWVD unit conversion, observed high/low extrema matching, maximum station-pair distance, six-region tide mapping, duplicate IDs, mismatched location names, null values and malformed CWA payloads.

## Remaining limitations

1. The current 48-hour rolling observation window yields too few overlapping high/low events for meaningful forecast verification.
2. Hourly observations limit event timing precision; the CWA dataset metadata may describe a higher nominal update frequency, but the actual downloaded station samples in this run were hourly.
3. A 500 m horizontal pairing is an explicit proximity rule, not proof that two locations share an identical local tidal response. Keep pair distance visible in all outputs.
4. The TWVD2001 datum rule applies to mainland stations described by O-B0076-001. Do not apply it to offshore-island stations without checking their local vertical reference.
5. Continue accumulating event matches over time before computing accuracy statistics or using them to calibrate fishing recommendations.
6. No fish activity score, bite score or catch probability is generated.
