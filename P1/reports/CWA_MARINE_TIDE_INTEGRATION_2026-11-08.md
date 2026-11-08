# CWA Marine Observation and Tide Forecast Integration — 2026-11-08

## Scope and branch safety

- Repository: `fb326549-lang/fishing-intelligence`
- Development branch: `p1-foundation`
- Verified branch head at report time: `734c1ffdc361e51b9f1dd9f2980117f9c9ea762e`
- `main` was not modified.
- CWA data are free to use under the CWA Open Data Platform terms; API access requires a CWA member authorization key stored as the GitHub Actions secret `CWA_AUTHORIZATION`.

## Integrated CWA datasets

| Dataset | ID | Role | Cadence / coverage |
|---|---|---|---|
| Marine observations | O-B0075-001 | Buoy and tide-station observations | Rolling 48 hours |
| Marine observations | O-B0075-002 | Historical buoy and tide-station observations | Rolling 30 days |
| Tide forecast | F-A0021-001 | High/low tide event forecast | About one month; updated daily |

## New implementation

- `P1/collector/fetch_cwa_tide_forecast.py`
  - Fetches F-A0021-001 using the existing CWA secret.
  - Saves the raw JSON and normalized CSV.
  - Keeps the three height datums separate: AboveTWVD, AboveLocalMSL, AboveChartDatum.
  - Keeps provider units in centimetres.
  - Retains missing values as null.
  - Does not infer a P1 region until an explicit reviewed location mapping exists.
- `.github/workflows/cwa-station-inventory.yml`
  - Runs the CWA tide collector alongside the existing station, observation, normalization and regional aggregation steps.
  - Adds a push trigger for the tide collector/workflow changes and includes tide outputs in the artifact.
- `P1/collector/test_marine_pipeline.py`
  - Adds tests for the documented tide JSON structure, distinct height datums, missing-value handling and malformed responses.
  - Imports the tide parser without requiring the HTTP dependency for offline unit tests.

## Latest verification

- CWA Actions run: [42489057167](https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42489057167) — success.
- Offline test run: [42489057163](https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42489057163) — success; 9 tests passed.
- Open-Meteo forecast run: [42489057207](https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42489057207) — success.
- CWA artifact: [13620432385](https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42489057167/artifacts/13620432385).

Latest CWA artifact summary:
- 31,310 tide forecast events across 266 locations.
- O-B0075-001: 4,165 observation rows from 85 source locations.
- O-B0075-002: 61,285 observation rows from 85 source locations.
- Regional observation snapshot latest time: 2026-11-08 21:00 Taiwan time.

## Verified regional observation coverage

| P1 region | Stations with observations | Latest observation |
|---|---:|---|
| 宜蘭、蘇澳 | 4 | 21:00 |
| 花蓮北段 | 2 | 21:00 |
| 花蓮南段 | 0 | No mapped observations |
| 豐濱、石梯坪 | 2 | 21:00 |
| 成功、東河 | 3 | 21:00 |
| 台東南段 | 2 | 21:00 |

Tide-height observations were available in five of the six mapped regions. 花蓮南段 has no eligible mapped station in the current station mapping. Do not fill this gap with another region's values.

## Remaining limitations / next work

1. F-A0021-001 currently contains all 266 CWA forecast locations. The normalized file has 31,310 event rows, but `region_id` remains blank pending a reviewed CWA-location-to-P1-region mapping.
2. F-A0021-001 is a high/low event forecast, not continuous tide-level observation.
3. O-B0075-001 includes observed tide height at mapped tide stations. Current regional builder reports it in metres; verify provider field/unit metadata before any further conversion or cross-dataset merge.
4. Improve live station inventory and per-element status coverage, especially the no-station gap in 花蓮南段.
5. Next implementation should create and review an explicit tide-location mapping, then produce six-region tide forecast output without spatially guessing or interpolating.
6. Keep forecast and observed tide data in separate tables/fields and preserve valid time, source, data kind, quality and null status.

No fish activity score, bite score or catch probability is generated from these environmental data.
