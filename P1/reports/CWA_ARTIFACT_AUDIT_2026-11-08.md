# CWA Artifact Audit — 2026-11-08

## Scope

Inspected the downloaded GitHub Actions artifact from workflow run
[42483447277](https://github.com/fb326549-lang/fishing-intelligence/actions/runs/42483447277).
This is an audit of the artifact produced by the earlier collector version, not
a claim that the newly revised regional engine has already processed a fresh
live API response.

## Download and normalization evidence

The artifact contains:
- `cwa_stations/O-B0076-001_raw_response.txt`
- `cwa_stations/stations.csv`
- `cwa_marine/O-B0075-001.json`
- `cwa_marine/O-B0075-002.json`
- `cwa_marine/manifest.json`
- `normalized/O-B0075-001.csv`
- `normalized/O-B0075-002.csv`
- `normalized/summary.json`
- `east_region/east_region_conditions.csv`
- `east_region/east_region_summary.json`

Manifest reports both O-B0075 datasets as downloaded:
- O-B0075-001: 3,742,580 raw bytes
- O-B0075-002: 54,823,674 raw bytes

Normalization summary:
- O-B0075-001: 85 source locations, 4,165 observation rows,
  1,519 observations with current layers, 1,519 layer records.
- O-B0075-002: 85 source locations, 61,285 observation rows,
  22,351 observations with current layers, 22,351 layer records.

Station inventory CSV contains 84 unique station records. The raw marine
responses and normalized CSVs are both present in the artifact.

## Regional snapshot in the artifact

The prior regional summary's latest timestamp is
2026-11-08 20:00 (Taiwan local time).

| Planning region | Stations with observations | Latest observation |
|---|---:|---|
| 宜蘭、蘇澳 | 5 | 20:00 |
| 花蓮北段 | 3 | 20:00 |
| 花蓮南段 | 0 | No mapped observations |
| 豐濱、石梯坪 | 2 | 20:00 |
| 成功、東河 | 3 | 20:00 |
| 台東南段 | 3 | 20:00 |

These counts are from the earlier artifact's mapping logic and should not be
interpreted as a validated spatial-coverage percentage.

## Verified issues and limitations

1. The previous regional engine used a static station mapping status. Live
   station inventory reports that status can change; station metadata must be
   authoritative at each collection.
2. A station can transmit while not reporting a particular variable. Element
   availability must be checked separately from station transmission status.
3. Hualien South has no mapped station with observations in this artifact.
   Do not copy Hualien North readings into that region.
4. The previous engine's regional averages and coverage ratios need to be
   recomputed using live station and element status.
5. Normalization preserves layer number, direction, speed and knots. The
   current regional summary uses first-layer compatibility fields; it must
   not imply that the value represents all depths.
6. The artifact is a historical snapshot. It does not prove current conditions
   after its collection time.

## Follow-up implementation

The P1 regional builder has been revised to:
- read current station transmission status from the live station inventory;
- check the station's reported-element status before including a variable;
- calculate variable coverage against eligible active stations;
- report inactive/unknown mapped station IDs separately;
- retain nulls instead of zero-filling missing observations;
- state explicitly that the current regional current summary uses the first
  reported layer.

Offline regression tests cover status parsing and the existing marine parser.
A fresh CWA Actions run is still required before claiming that this revised
builder has been verified against a newly collected live artifact.
