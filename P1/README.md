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
