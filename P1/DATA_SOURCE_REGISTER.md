# P1 Data Source Register (verification notes)

Status meanings:
- VERIFIED_METADATA: official provider page identifies the dataset, fields, cadence, and access terms.
- NEEDS_API_TEST: endpoint response, exact field paths, station coverage, and reliability still need a live test.
- CONDITIONAL: usable only for records explicitly marked open/public; controlled data requires approval.
- NOT_APPROVED: do not bulk-copy or redistribute until rights are clarified.

| Provider / dataset | What it can contribute | Known metadata | Status / implementation rule |
|---|---|---|---|
| CWA O-B0076-001 (buoy + tide station metadata) | Station ID, coordinates, type, location, observation elements | Official dataset page describes buoy/tide stations and available observation elements; hourly update; free; CWA platform terms | VERIFIED_METADATA. Use first to build the real station inventory; test exact JSON response and availability. |
| CWA O-MMC-0001 (real-time marine conditions) | Tide height, wave height/direction/period, wind, sea temperature, pressure, current direction/speed | Identified in CWA dataset example as real-time marine conditions | NEEDS_API_TEST. Confirm current dataset code, endpoint, and schema against live Swagger before relying on it. |
| CWA weather station metadata | Weather station coordinates, elevation, status, start/end dates | Government open-data listing describes station metadata and Open Government Data License 1.0 | VERIFIED_METADATA. Match station IDs and coordinates, then test observation datasets separately. |
| CWA O-A0001 / O-A0002 weather observations | Weather, rainfall and related observations | API platform requires membership and a valid authorization key; free access described by CWA | NEEDS_API_TEST. Never put the key in browser JavaScript or commit it to Git. |
| NODASS API and downloads | Marine observations, satellite-derived water products, spatial data | API is documented; portal separates open and controlled datasets; open data follows Open Government Data License 1.0 | CONDITIONAL. Inspect each dataset's access label and metadata. Controlled data is excluded unless formally approved. |
| Taiwan Fish Database (Academia Sinica) | Taxonomy, Chinese/scientific names, ecology descriptions, distribution, specimen/media references | Publicly browsable resource; separate technology-transfer listing states licensing discussions are available | NOT_APPROVED for bulk reuse. Use as a taxonomic research/reference source; do not scrape or copy descriptions/images without explicit permission or a clearly applicable license. |
| TBIA API | Biodiversity occurrence / taxon discovery across listed rights holders, including Taiwan Fish Database | API docs state terms follow the website's terms; sources/rights holders vary | NEEDS_API_TEST. Check per-record rights holder and license before reuse; do not treat all records as one license. |
| Open-Meteo Marine / Forecast | Gridded/modelled sea temperature, currents, waves and weather forecast | Model/grid product rather than local buoy observation | NEEDS_API_TEST. Mark as modelled/forecast, retain model metadata and resolution; never display as measured station data. |

## Priority decision
1. Obtain the CWA buoy/tide station metadata dataset first and map verified stations to the six planning regions by coordinates.
2. Query CWA real-time marine observations for those station IDs; compare its observed wave/current/sea-temperature values with Open-Meteo model outputs.
3. Add NODASS products only after each individual dataset's open/controlled status, spatial resolution, timestamp and license are reviewed.
4. Create the first fish taxon list from verified scientific names and documented distribution evidence. Do not use broad fish groups as if they were individual species.

## Official references
- CWA OpenData API documentation: https://opendata.cwa.gov.tw/dist/opendata-swagger.html
- CWA API access guide: https://opendata.cwa.gov.tw/devManual/description
- CWA buoy/tide station metadata dataset: https://opendata.cwa.gov.tw/dataset/forecast/O-B0076-001
- NODASS API service: https://nodass.namr.gov.tw/api-service
- NODASS downloads and data classification: https://nodass.namr.gov.tw/downloads
- NODASS data catalog: https://nodass.namr.gov.tw/data/
- Taiwan Fish Database: https://fishdb.sinica.edu.tw/
- Academia Sinica technology-transfer listing: https://ticket.apps.sinica.edu.tw/tech/30T-991105
- TBIA API documentation: https://tbiadata.tw/zh-hant/api/doc

The initial rows above record source discovery. The CWA integration status below records live API ingestion tests and generated regional outputs. Dataset schemas, quotas, and terms still require periodic rechecking; successful ingestion does not grant unrestricted redistribution rights.

## CWA live integration verification (reviewed 2026-11-09)

The following official CWA products are now implemented in the P1 collector workflow:

| Dataset | Product / fields | Official cadence and fee | P1 handling |
|---|---|---|---|
| O-B0075-001 | 48-hour buoy and tide-station marine observations: station ID, observation time, tide height, wave height/direction/period, sea temperature, air temperature/pressure, wind, gusts, current layer/direction/speed | 4 updates/hour; free; CWA OpenData platform usage rules | Integrated through fetch, normalization and reviewed station-to-region mapping. Values retain source time, units and missing status. |
| O-B0075-002 | 30-day buoy and tide-station marine observations | CWA REST API / Swagger; latest live fetch validated in P1 | Integrated into daily workflow as a separate rolling-30-day regional history output. Regional/time/value revisions are persisted append-only on `tide-history`; raw response and normalized station-level CSV remain 3-day workflow artifacts. Historical aggregation does not apply today's station-active status to past records. |
| F-A0021-001 | One-month tide forecast: location ID/name/coordinates, high/low event time, tide range and three separate height datums | Updated daily; free; CWA OpenData platform usage rules | Integrated as forecast events, not continuous observed tide. TWVD, local MSL and chart datum remain separate. |
| O-B0076-001 | Buoy/tide-station metadata and available observation elements | Hourly metadata update; free | Used to discover stations and their supported elements; metadata is not a measurement. |

### Access, quota and credential handling

- CWA API access requires a free CWA OpenData member account and its member authorization token. The token is supplied to the REST endpoint through the documented Authorization parameter or supported authentication method; it must not be embedded in browser code or committed to Git.
- CWA's FAQ lists a general-member allowance of 20,000 API requests and 2 GB per 24 hours, and recommends at least 10 seconds to 1 minute between repeated non-earthquake data requests, depending on the dataset. The P1 scheduled workflow makes a small number of daily dataset requests and does not poll continuously.
- The repository workflow reads `CWA_AUTHORIZATION` from GitHub Actions Secrets. Previous P1 CWA workflow runs completed successfully, confirming the secret was available to those runs; secret values are never logged.
- These products are free to access, but use remains subject to the CWA OpenData platform usage rules and dataset-specific conditions. Do not describe the data as unrestricted public-domain content.

### Data and verification status

- The `tide-history` branch currently contains 324 observed-tide records from six explicitly paired mainland stations and 32,171 forecast-vintage records across nine collection snapshots (latest archive summary: 2026-11-09 04:34 UTC).
- The historical verifier currently has 12 matched forecast-extremum samples across the six station/location pairs. This remains below the 30-sample reporting threshold; interpretation stays `Insufficient evidence`. Do not present these early samples as a calibrated accuracy score.
- The latest rolling 48-hour comparison had zero eligible forecast events because the tide forecast events within the observed window had been issued at or after their target times. They were correctly excluded. This is not a failed forecast result.
- The daily CWA workflow generates separate O-B0075-001 rolling-48-hour and O-B0075-002 rolling-30-day regional series. Both are persisted on `tide-history` as append-only region/time/value revisions in `regional_marine_observations_48h.jsonl` and `regional_marine_observations_30d.jsonl`. Identical repeats are deduplicated; changed values are preserved as revisions. Raw CWA JSON and station-level normalized CSV remain short-retention workflow artifacts.
- The 30-day API is a rolling window, not 30 days of independent new samples on every run. Historical analysis must deduplicate by region/time/revision and must not inflate sample counts by counting repeated snapshots as independent observations.
- The 48-hour region output had 240 region/time rows. CWA currently has no mapped station for 花蓮南段; this region must remain explicitly unobserved in CWA station data rather than being filled with interpolated or invented measurements.
- Continue daily append-only tide history collection. Do not overwrite forecast vintages, mix vertical datums, or interpret hourly observations as exact high/low event times.

### Official CWA references

- O-B0075-001 dataset metadata: https://opendata.cwa.gov.tw/dataset/all/O-B0075-001
- F-A0021-001 dataset metadata: https://opendata.cwa.gov.tw/dataset/forecast/F-A0021-001
- O-B0075-001 / O-B0075-002 / F-A0021-001 REST endpoints: https://opendata.cwa.gov.tw/dist/opendata-swagger.html
- API access guide: https://opendata.cwa.gov.tw/devManual/description
- API quota and credential FAQ: https://opendata.cwa.gov.tw/faq
- CWA usage rules: https://opendata.cwa.gov.tw/about/rules



## PWA consumption of regional observations

The deployed PWA reads `tide-history/data/latest_regional_marine_conditions.json` from the public repository branch. The compact snapshot contains the six P1 planning regions, separate 48-hour and 30-day observed summaries, valid observation times, station counts, per-variable coverage, and explicit no-coverage status. It contains no CWA authorization token.

Open-Meteo remains the modelled forecast source. CWA O-B0075 values are displayed separately as in-situ station observations. The PWA does not blend them into its heuristic fish score pending a validated environmental response model.
