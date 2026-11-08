# Fishing Intelligence P1 Foundation

This branch is an isolated development area. The production `main` branch and GitHub Pages site are not changed.

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

## Next local verification step
Run the station metadata collector on your own Windows computer using the API key already held by you:
```powershell
$env:CWA_AUTHORIZATION="貼上你的授權碼"
python collector/fetch_cwa_stations.py --out data/cwa_stations
```
Do not send the authorization code in chat or add it to any file. After the run, share only:
- the printed station count;
- the first 10 lines of `stations.csv` (remove any personal/private fields if present);
- any HTTP error text, after confirming it contains no token.

Then we can map actual stations to the six regions and query O-B0075-001 for one station. Keep the raw API JSON local until its fields and redistribution terms have been reviewed.


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
