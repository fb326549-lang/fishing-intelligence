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

This register records metadata research, not successful live API ingestion. Dataset schemas and terms must be rechecked before production use.

## CWA live integration verification (reviewed 2026-11-09)

The following official CWA products are now implemented in the P1 collector workflow:

| Dataset | Product / fields | Official cadence and fee | P1 handling |
|---|---|---|---|
| O-B0075-001 | 48-hour buoy and tide-station marine observations: station ID, observation time, tide height, wave height/direction/period, sea temperature, air temperature/pressure, wind, gusts, current layer/direction/speed | 4 updates/hour; free; CWA OpenData platform usage rules | Integrated through fetch, normalization and reviewed station-to-region mapping. Values retain source time, units and missing status. |
| O-B0075-002 | 30-day buoy and tide-station marine observations | Available in the CWA REST API / Swagger; fee and cadence must be rechecked on its dataset page before routine use | Not currently used by the daily P1 ingestion; avoid adding unnecessary duplicate volume. |
| F-A0021-001 | One-month tide forecast: location ID/name/coordinates, high/low event time, tide range and three separate height datums | Updated daily; free; CWA OpenData platform usage rules | Integrated as forecast events, not continuous observed tide. TWVD, local MSL and chart datum remain separate. |
| O-B0076-001 | Buoy/tide-station metadata and available observation elements | Hourly metadata update; free | Used to discover stations and their supported elements; metadata is not a measurement. |

### Access, quota and credential handling

- CWA API access requires a free CWA OpenData member account and its member authorization token. The token is supplied to the REST endpoint through the documented Authorization parameter or supported authentication method; it must not be embedded in browser code or committed to Git.
- CWA's FAQ lists a general-member allowance of 20,000 API requests and 2 GB per 24 hours, and recommends at least 10 seconds to 1 minute between repeated non-earthquake data requests, depending on the dataset. The P1 scheduled workflow makes a small number of daily dataset requests and does not poll continuously.
- The repository workflow reads `CWA_AUTHORIZATION` from GitHub Actions Secrets. Previous P1 CWA workflow runs completed successfully, confirming the secret was available to those runs; secret values are never logged.
- These products are free to access, but use remains subject to the CWA OpenData platform usage rules and dataset-specific conditions. Do not describe the data as unrestricted public-domain content.

### Data and verification status

- The `tide-history` branch currently contains 288 observed-tide records from six explicitly paired mainland stations and 20,384 forecast-vintage records from six collection snapshots (latest archive summary: 2026-11-08 23:15 UTC).
- The current historical verification report has zero matched forecast-extremum events. Therefore no MAE or timing-accuracy statistic is reported yet. This is an insufficient-history result, not evidence that the CWA forecast is inaccurate.
- Continue daily append-only collection. Do not overwrite forecast vintages, mix vertical datums, or interpret hourly observations as exact high/low event times.

### Official CWA references

- O-B0075-001 dataset metadata: https://opendata.cwa.gov.tw/dataset/all/O-B0075-001
- F-A0021-001 dataset metadata: https://opendata.cwa.gov.tw/dataset/forecast/F-A0021-001
- O-B0075-001 / O-B0075-002 / F-A0021-001 REST endpoints: https://opendata.cwa.gov.tw/dist/opendata-swagger.html
- API access guide: https://opendata.cwa.gov.tw/devManual/description
- API quota and credential FAQ: https://opendata.cwa.gov.tw/faq
- CWA usage rules: https://opendata.cwa.gov.tw/about/rules

