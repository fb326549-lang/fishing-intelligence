# Fishing Intelligence P1 Foundation

P1 collector and validation code is developed on `p1-foundation` and merged to `main` through reviewed pull requests. The public GitHub Pages site is kept separate from the collector outputs; data collection artifacts are not automatically exposed as website content.

## P1 goals
- Build a verifiable East Taiwan environmental-data foundation.
- Keep raw observations, forecasts, and estimates distinguishable.
- Never convert missing values into normal/zero values.
- Keep provider credentials out of browser code and Git.
- Use free tiers only; no paid service is required to run the local collector.

## Initial regions
Region identifiers are planning zones, not official marine forecast boundaries:
- yilan_suao
- hualien_north
- hualien_south
- fengbin_shitiping
- chenggong_donghe
- taitung_south

Exact station-to-region mapping must be verified against provider station metadata before automated ingestion is enabled.

## Data-source policy
1. CWA OpenData: use documented dataset IDs and a user-supplied API key held in an environment variable. Verify each dataset's fields, update cadence, station coverage, and terms before production ingestion.
2. Open-Meteo Marine and Forecast: suitable for model/grid data, not in-situ observations. Store provider/model metadata and mark records as forecast or model-derived.
3. Water quality and river flow: do not infer real-time turbidity, salinity, dissolved oxygen, or river discharge where no suitable station observation exists. Store null + missing status instead.
4. Fish ecology: retain scientific name, source citation, study region, evidence type, and confidence for every nontrivial biological parameter. Unverified preferences remain null.

## Files
- `database/schema.sql`: initial PostgreSQL schema.
- `collector/requirements.txt`: local Python dependencies.
- `collector/config.example.json`: East Taiwan planning locations.
- `collector/collect_open_meteo.py`: optional local collector; writes raw JSON snapshots and normalized CSV. No database writes and no credentials required.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r collector/requirements.txt
python collector/collect_open_meteo.py --config collector/config.example.json --out data
```

The collector calls Open-Meteo Marine and Forecast endpoints for each configured coordinate. Respect provider limits and terms. Start with one or two locations, not all coordinates at high frequency.

## P1 acceptance tests
- Raw response is preserved.
- Each normalized record includes source, fetched time, valid time, unit, and data quality.
- Missing provider fields remain null.
- Forecast/model data is never labelled as an in-situ observation.
- Duplicate requests are avoided by scheduled caching in the eventual backend.
- No secrets or paid credentials are committed.
- Nothing in this branch is merged to `main` until reviewed and tested.


## CWA station inventory (metadata only)
The official CWA dataset O-B0076-001 provides buoy/tide station IDs, names,
coordinates, station types, area names, and observation-element status. Its
metadata page states hourly updates and free access. The live feed may have
different stations or statuses over time; never hardcode the seed CSV as the
complete station inventory.

Set the API token in the shell, then run:
```powershell
$env:CWA_AUTHORIZATION="YOUR_CWA_TOKEN"
python collector/fetch_cwa_stations.py --out data/cwa_stations
```
The script preserves the raw JSON and exports a CSV. Review each station's
`station_status` and `observed_properties` before mapping it to a fishing
region. A station can exist but have no active transmission or no observation
for a particular variable. Do not interpret status 0, 2, or blank as a valid
measurement.

Official dataset: https://opendata.cwa.gov.tw/dataset/forecast/O-B0076-001


## Important CWA dataset distinction
- `O-B0076-001`: buoy/tide-station metadata and observation-element status. Use it to discover stations and determine which variables each station reports.
- `O-B0075-001`: 48-hour real-time buoy/tide-station marine observations.
- `O-B0075-002`: 30-day buoy/tide-station marine observations.
- `O-MMC-0001`: real-time marine-condition display product; useful as a cross-check, but do not confuse it with the station metadata dataset.

The CWA Swagger lists O-B0075-001 and O-B0075-002 under observations. The dataset metadata page for O-B0076-001 includes an example of the O-MMC-0001 real-time marine-condition XML. Keep these product IDs separate in the source registry and ingestion code.

## Automated CWA ingestion status (reviewed 2026-11-09)
The GitHub Actions workflow uses the repository secret `CWA_AUTHORIZATION`; the credential is not stored in source files and does not need to be sent in chat.

The daily workflow now:
1. Refreshes O-B0076-001 station metadata.
2. Fetches O-B0075-001 (48-hour) and O-B0075-002 (30-day) marine observations.
3. Normalizes both datasets while keeping missing values blank.
4. Builds separate six-region outputs: `output/east_region/` for the rolling 48-hour feed and `output/east_region_30d/` for the rolling 30-day historical context.
5. Fetches and maps F-A0021-001 tide events, compares only forecasts issued before their target events, and appends observed tide / forecast vintages to the dedicated `tide-history` branch.

The regional 48-hour and 30-day time series are persisted append-only on the `tide-history` branch as `regional_marine_observations_48h.jsonl` and `regional_marine_observations_30d.jsonl`. Identical region/time/value records are deduplicated and changed values are retained as revisions. Raw CWA JSON and station-level normalized CSV are still uploaded as workflow artifacts with 3-day retention.

The 30-day endpoint is a rolling window. Repeated daily snapshots are not independent samples; downstream training must deduplicate by region, valid time, and revision. CWA currently has no mapped station in 花蓮南段; this remains a known coverage gap. Do not fill it with interpolated observations.


## Evidence-gated species/environment context engine

The first species-engine stage is deliberately a context layer, not a bite forecast:

```bash
python P1/species/build_species_environment_context.py \
  --species-dir P1/species \
  --regional-forecast path/to/regional_forecast_conditions_6_12_24.csv \
  --out path/to/species_environment_context.csv
```

It includes only single-taxon candidates with verified taxonomy and documented East Taiwan distribution, links each record to its evidence IDs, and carries habitat context and environmental-data completeness. It does not claim that a species occurs at every planning region or fishing spot.

Activity scores and catch probabilities remain blank until species-specific response parameters and local fishing-effort/catch records have been collected and validated. Broad habitat and reported depth descriptions are not converted into arbitrary hourly wave/current/SST thresholds. The forecast workflow runs this context stage and uploads its output with the other artifacts.


## Historical CWA tide forecast verification

The append-only history is stored on the dedicated `tide-history` branch. The historical verifier reads archived CWA observation and forecast vintages and writes:
- `data/analysis/event_matches.csv`
- `data/analysis/accuracy_by_lead.csv`
- `data/analysis/analysis_summary.json`

Run locally from the repository root:
```bash
python P1/collector/analyze_cwa_tide_forecast_history.py --history-dir path/to/tide-history/data --out-dir output/tide-analysis
```

The history branch also stores regional 48-hour and 30-day marine observation series with append-only revision tracking. The verifier uses only reviewed mainland station/location pairs and TWVD2001 heights. Forecast lead time is calculated from the original CWA fetch timestamp. Forecasts fetched at or after the target event are excluded. It reports descriptive MAE and timing errors only after valid matches exist; no fish activity score or catch probability is inferred from a small or empty sample.

The CWA workflow is configured for 07:00 Taiwan-time daily collection. It is now present on the repository default branch, so the schedule is enabled. The workflow checks out `p1-foundation` for its collector code; keep that branch synchronized with the reviewed `main` version.


## PWA CWA observation panel

The existing PWA now reads the compact public snapshot at:

`https://raw.githubusercontent.com/fb326549-lang/fishing-intelligence/tide-history/data/latest_regional_marine_conditions.json`

The panel shows O-B0075-001 48-hour observations and O-B0075-002 rolling 30-day latest observations separately from Open-Meteo model forecasts. It displays observation time, station coverage, wave height/period, sea temperature, current speed, wind speed, and tide height.

The PWA can estimate a P1 planning region from the selected coordinate or allow manual region selection. This automatic mapping is approximate and is not an official CWA marine boundary. Hualien South is explicitly marked as having no CWA station coverage; the UI does not substitute another region's values.

CWA observed values are currently displayed as a separate evidence layer. They are not blended into the existing heuristic fish score. The existing score is not a calibrated catch probability or a trained local fish-activity model.
