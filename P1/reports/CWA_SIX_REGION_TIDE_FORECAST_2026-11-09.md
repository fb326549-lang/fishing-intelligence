# Six-region CWA tide forecast integration — 2026-11-09

## Branch and safety
- Repository: fb326549-lang/fishing-intelligence
- Branch: p1-foundation
- Implementation commit containing the collector workflow: 558bda71bb3159ecf3b4a29907ee694674fb3d1d
- Latest test-fix commit: 0f174c87231655c9196ee205769e5e1b4e176516
- main was not modified.

## New files
- P1/stations/cwa_tide_region_mapping.csv
- P1/collector/build_cwa_regional_tide_forecast.py

The workflow now runs the tide collector and then builds:
- output/cwa_tides/regional_tide_forecast.csv
- output/cwa_tides/regional_tide_summary.json

## Mapping approach
32 named CWA tide-forecast locations are explicitly assigned to the six P1 mainland planning regions using CWA location IDs and matching location names/coordinates. Green Island and Orchid Island records are explicitly excluded from the six mainland regions and retained only in the full raw/normalized CWA tide dataset.

This is a P1 planning mapping, not an official CWA marine-zone boundary. Each event retains its original location ID, location name, coordinates, event time, tide type, and all three height datums. No averaging across locations, interpolation between high/low events, or extrapolation to unmapped places is performed.

## Real CWA run verification
Workflow: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42532554850
Artifact: https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42532554850/artifacts/13637433558

The real API workflow completed successfully and generated:
- 3,929 mapped tide event rows
- 32 mapped CWA locations
- 234 locations unmapped or explicitly excluded from the six mainland planning regions
- 0 mapped locations missing from the current CWA feed

Regional coverage:
| Region | Mapped locations | Forecast events |
|---|---:|---:|
| 宜蘭、蘇澳 | 6 | 741 |
| 花蓮北段 | 5 | 615 |
| 花蓮南段 | 3 | 369 |
| 豐濱、石梯坪 | 3 | 369 |
| 成功、東河 | 9 | 1,107 |
| 台東南段 | 6 | 728 |

Counts are event rows in the fetched forecast period; they are not counts of unique tide times across a region, because each location has its own event times.

## Automated tests
Latest offline regression workflow:
https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42532600201

Result: success. The suite ran 12 tests, including:
- documented CWA tide JSON parsing and separate height datums
- missing values remain null
- malformed responses rejected
- exact mapping preserves location-level events
- island locations excluded from mainland regions
- duplicate location IDs rejected
- location-name mismatches rejected

## Remaining limitations
1. Six-region mapping is a transparent P1 planning assignment and should be refined if the project later adopts surveyed fishing-zone polygons or more precise local site boundaries.
2. Tide dataset F-A0021-001 is high/low tide forecast events, not continuous observed tide levels.
3. This stage does not create regional mean tide heights or tide curves between events.
4. Flowering into PWA UI is not yet performed; this remains a P1 data-engineering output.
5. Do not infer fishing activity or catch probability from tide forecast alone.
6. Continue investigating actual CWA tide observations and verify units/datum metadata independently before comparing observed tide heights with forecasts.

