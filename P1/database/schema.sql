-- Fishing Intelligence P1 schema
-- PostgreSQL 14+. Optional PostGIS can be enabled later; coordinates are numeric now.
-- Apply only to a new development database. This file does not alter production.

CREATE TABLE IF NOT EXISTS regions (
  region_id text PRIMARY KEY,
  name_zh text NOT NULL,
  description text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS locations (
  location_id bigserial PRIMARY KEY,
  region_id text REFERENCES regions(region_id),
  name text NOT NULL,
  latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  habitat text,
  location_type text NOT NULL DEFAULT 'planning_point',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_locations_region ON locations(region_id);

CREATE TABLE IF NOT EXISTS data_sources (
  source_id bigserial PRIMARY KEY,
  provider text NOT NULL,
  dataset_code text,
  endpoint_host text,
  documentation_url text,
  license_or_terms text,
  intended_use text,
  update_interval_minutes integer CHECK (update_interval_minutes IS NULL OR update_interval_minutes > 0),
  enabled boolean NOT NULL DEFAULT false,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stations (
  station_id text PRIMARY KEY,
  source_id bigint REFERENCES data_sources(source_id),
  station_name text NOT NULL,
  latitude double precision CHECK (latitude BETWEEN -90 AND 90),
  longitude double precision CHECK (longitude BETWEEN -180 AND 180),
  region_id text REFERENCES regions(region_id),
  station_type text,
  active boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS environmental_observations (
  observation_id bigserial PRIMARY KEY,
  location_id bigint REFERENCES locations(location_id),
  station_id text REFERENCES stations(station_id),
  source_id bigint NOT NULL REFERENCES data_sources(source_id),
  variable_code text NOT NULL,
  value numeric,
  unit text,
  valid_time timestamptz NOT NULL,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  data_kind text NOT NULL CHECK (data_kind IN ('observed','forecast','modelled','estimated')),
  quality_status text NOT NULL DEFAULT 'unchecked'
    CHECK (quality_status IN ('unchecked','valid','suspect','missing','stale')),
  raw_payload_ref text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (value IS NOT NULL OR quality_status = 'missing')
);
CREATE INDEX IF NOT EXISTS idx_env_location_time ON environmental_observations(location_id, valid_time DESC);
CREATE INDEX IF NOT EXISTS idx_env_station_time ON environmental_observations(station_id, valid_time DESC);
CREATE INDEX IF NOT EXISTS idx_env_variable_time ON environmental_observations(variable_code, valid_time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_env_dedup
  ON environmental_observations(source_id, COALESCE(location_id, -1), COALESCE(station_id, ''), variable_code, valid_time, data_kind);

CREATE TABLE IF NOT EXISTS species (
  species_id text PRIMARY KEY,
  common_name_zh text NOT NULL,
  scientific_name text,
  family_name text,
  taxonomic_status text,
  description text,
  source_notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS species_behavior (
  behavior_id bigserial PRIMARY KEY,
  species_id text NOT NULL REFERENCES species(species_id),
  parameter_code text NOT NULL,
  numeric_value numeric,
  text_value text,
  unit text,
  valid_region_id text REFERENCES regions(region_id),
  season_months smallint[] CHECK (season_months IS NULL OR season_months <@ ARRAY[1,2,3,4,5,6,7,8,9,10,11,12]::smallint[]),
  evidence_type text NOT NULL CHECK (evidence_type IN ('peer_reviewed','government','field_observation','expert_hypothesis','unknown')),
  confidence_level text NOT NULL CHECK (confidence_level IN ('high','medium','low','unverified')),
  source_reference text,
  study_region text,
  notes text,
  reviewed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_species_behavior_species ON species_behavior(species_id, parameter_code);

CREATE TABLE IF NOT EXISTS fishing_logs (
  fishing_log_id bigserial PRIMARY KEY,
  user_ref text,
  location_id bigint REFERENCES locations(location_id),
  species_id text REFERENCES species(species_id),
  started_at timestamptz NOT NULL,
  ended_at timestamptz,
  method text,
  effort_minutes integer CHECK (effort_minutes IS NULL OR effort_minutes >= 0),
  catch_count integer NOT NULL DEFAULT 0 CHECK (catch_count >= 0),
  largest_length_cm numeric CHECK (largest_length_cm IS NULL OR largest_length_cm > 0),
  water_clarity text,
  notes text,
  environment_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE INDEX IF NOT EXISTS idx_fishing_logs_location_time ON fishing_logs(location_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_fishing_logs_species_time ON fishing_logs(species_id, started_at DESC);

CREATE TABLE IF NOT EXISTS model_predictions (
  prediction_id bigserial PRIMARY KEY,
  species_id text REFERENCES species(species_id),
  location_id bigint REFERENCES locations(location_id),
  prediction_time timestamptz NOT NULL,
  target_time timestamptz NOT NULL,
  environment_score numeric CHECK (environment_score BETWEEN 0 AND 100),
  activity_score numeric CHECK (activity_score BETWEEN 0 AND 100),
  feeding_score numeric CHECK (feeding_score BETWEEN 0 AND 100),
  catch_probability numeric CHECK (catch_probability BETWEEN 0 AND 1),
  confidence_level text CHECK (confidence_level IN ('high','medium','low','insufficient_data')),
  model_name text NOT NULL,
  model_version text NOT NULL,
  explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_predictions_target ON model_predictions(location_id, target_time DESC);

INSERT INTO regions(region_id,name_zh,description) VALUES
 ('yilan_suao','宜蘭、蘇澳','東北部優先研究區'),
 ('hualien_north','花蓮北段','規劃研究區，測站需核對'),
 ('hualien_south','花蓮南段','規劃研究區，測站需核對'),
 ('fengbin_shitiping','豐濱、石梯坪','規劃研究區，測站需核對'),
 ('chenggong_donghe','成功、東河','規劃研究區，測站需核對'),
 ('taitung_south','台東南段','規劃研究區，測站需核對')
ON CONFLICT (region_id) DO NOTHING;
