# Fishing log data collection guide

Use `fishing_log_import_template.csv` to collect local ground-truth records for later model calibration.

## Required fields
- `started_at_local`: local date/time in ISO 8601 form, including `+08:00` (example `2026-11-08T16:30:00+08:00`).
- `region_id`: one of the six P1 planning-region IDs.
- `method`: consistent fishing method label (for example, `磯釣`, `港口`, `船釣`, `路亞`).
- `effort_minutes`: actual fishing time. A zero-catch session is still a valid record when effort is greater than zero.
- `catch_count`: enter `0` when fishing occurred but no fish were caught. Leave blank only when unknown/not recorded.
- `candidate_id` or `common_name_reported`: record the reported fish identity. Prefer the candidate ID when known.

## Quality rules
1. Record unsuccessful sessions. Without zero-catch effort records, catch-rate modelling will be biased.
2. Do not guess a scientific name. Fill `scientific_name_confirmed` only when identification is reliable; otherwise leave it blank and describe the local name.
3. Use `species_identification_confidence` values `high`, `medium`, `low`, or `unconfirmed`.
4. Record actual fishing effort, not just the time spent at the location.
5. Keep location labels specific enough for later matching, but do not publish private access details.
6. Do not backfill tide, wave, wind, or water clarity from memory as if measured. If estimated, identify it in `notes`.
7. `photo_reference` may be a local filename or a stable private reference. Do not upload private coordinates or identifying information unnecessarily.

## Why these logs matter
Environmental forecasts describe conditions, not fish activity. To estimate catch rates responsibly, the project needs paired sessions containing both successful and unsuccessful effort, species identification, method, time, location, and matching environmental snapshots.

Until sufficient records exist, the engine must not output a numeric bite probability. A catch count is not itself a probability; effort and zero-catch sessions are essential denominators.
