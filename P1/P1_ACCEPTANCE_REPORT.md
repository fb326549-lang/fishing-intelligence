# P1 Foundation Acceptance Report

**Review date:** 2026-11-09  
**Status:** P1 data foundation and PWA observation integration accepted, with the limitations below carried forward.

This acceptance means the data collection, normalization, history, evidence-linked species context, and existing PWA display foundation are operational. It does **not** mean the system has a validated fish-activity model or reliable catch-probability forecast.

## 1. Completed scope

- Open-Meteo marine and weather forecast collection for six East Taiwan planning regions, with 6 / 12 / 24-hour horizons.
- CWA O-B0075-001 48-hour and O-B0075-002 30-day marine observation collection, normalization, and separate six-region aggregation.
- CWA F-A0021-001 monthly high/low tide event collection, explicit location mapping, and separate vertical datums.
- Append-only history for tide observations, tide forecast vintages, and regional 48-hour / 30-day marine observations.
- Revision-aware deduplication: repeated region/time/value rows are not counted as new independent observations; changed values are preserved as revisions.
- Compact six-region CWA snapshot published on the `tide-history` branch and consumed by the existing PWA.
- Species candidate, evidence, and ecology registers with evidence-gated context generation.
- Fishing-log import template and guide that retain zero-catch sessions and effort.
- Protected-species exclusion from target-fishing context.
- Existing PWA retained; CWA observed values are displayed separately from Open-Meteo forecasts.

## 2. Verified data state

Latest archived CWA history summary reviewed at 2026-11-09 04:51 UTC:

| Dataset / output | Verified count |
|---|---:|
| CWA observed tide records | 324 |
| CWA tide forecast vintage records | 67,532 |
| CWA collection runs | 18 |
| 48-hour regional marine revision records | 480 |
| 48-hour unique region/time records | 240 |
| 30-day regional marine revision records | 7,190 |
| 30-day unique region/time records | 3,595 |
| Tide forecast snapshots | 18 |
| Matched tide forecast events | 12 |

Regional history revision counts include earlier rows that were re-appended once to correct source-dataset provenance. The unique region/time counts are the distinct time slots and should be used for coverage reporting, not the revision totals.

### CWA regional station coverage

| P1 region | 48-hour stations with observations | 30-day stations with observations |
|---|---:|---:|
| 宜蘭、蘇澳 | 4 | 5 |
| 花蓮北段 | 2 | 3 |
| 花蓮南段 | 0 | 0 |
| 豐濱、石梯坪 | 2 | 2 |
| 成功、東河 | 3 | 3 |
| 台東南段 | 2 | 3 |

花蓮南段目前沒有映射的 CWA 測站，故標示為 `no_cwa_station_coverage`。不以鄰區數值或插值補齊。

## 3. Species data and model boundary

The latest successful species database validation reported:

- 38 candidates
- 46 evidence records
- 122 ecology records
- 0 structural validation errors

The validator checks register structure, references, source URLs, confidence vocabulary, and scientific-name consistency. It does not independently validate every taxonomic determination, source claim, or ecological threshold.

The species/environment context engine intentionally leaves `environment_score`, `activity_score`, `feeding_score`, and `catch_probability` blank. Broad habitat descriptions and distribution evidence are not converted into invented hourly thresholds. Protected species are excluded from target-fishing context.

## 4. Verification results

- Marine pipeline regression suite: 22 tests passed.
- PWA inline JavaScript syntax: `node --check` passed.
- Open-Meteo marine forecast workflow: success.
- CWA live collection, regional aggregation, history archive, and compact snapshot workflow: success.
- Species database validation and context-engine test: success.
- GitHub Pages deployment after PWA integration: success.
- `main` and `p1-foundation` synchronized; no open pull requests at acceptance review.

## 5. Known limitations carried into P2

1. **Tide forecast verification is still insufficient.** There are 12 matched event samples across 18 forecast snapshots, below the 30-sample minimum used for even a preliminary descriptive report. Do not treat the current result as calibrated accuracy.
2. **Hualien South has no CWA station coverage.** Open-Meteo model forecasts can still cover the planning area, but they must remain labelled as modelled forecasts, not observations.
3. **Species-specific response parameters are incomplete.** Do not generate numerical fish activity or catch probabilities until reliable species-specific evidence and local fishing-effort/catch records exist.
4. **The PWA's existing fish score remains heuristic.** The new CWA observed values are displayed separately and are not blended into the score.
5. **Local fishing logs are not yet sufficient for training.** Continue collecting successful and zero-catch sessions with effort, method, time, region, and reliable species identification.
6. **Bathymetry, substrate, water quality, and other local habitat layers remain future data-source work.**

## 6. P1 exit decision

P1 is accepted as the **data foundation and observation-display stage**. The next phase is P2: evidence-backed species/environment response modelling, hourly activity-window analysis, and eventual local catch-rate calibration. These are intentionally not claimed as completed by P1.
