# Ingestion Pipeline

Fetches NOAA GHCN-Daily weather observations from the public S3 bucket and
loads them into Postgres (raw.observations), idempotently.

## Flow

    select_stations()
        └─ downloads ghcnd-inventory.txt from S3
        └─ keeps stations in 7 target countries with BOTH TMAX and PRCP
           covering 1990–2025, capped at 75 per country
        └─ returns 491 station IDs

    for each station_id:

        download_station(station_id)
            └─ fetches csv.gz/by_station/{id}.csv.gz from S3
            └─ decompresses gzip in memory (no disk)
            └─ returns raw CSV text  (or None if the fetch failed → skipped)

        parse_station(text, station_id)
            └─ appends source_file (the station id) to each line
            └─ returns CSV text with 9 fields per line

        load_observations(text)
            └─ CREATE TEMP TABLE staging (9 columns)
            └─ COPY the text into staging  (fast bulk load)
            └─ INSERT INTO raw.observations SELECT ... FROM staging
               ON CONFLICT (station_id, obs_date, element) DO UPDATE
               (new rows insert; existing rows update in place — no duplicates)

    run_pipeline()  orchestrates the loop over all 491 stations.

## Key properties

- No disk landing: files are fetched and processed in memory.
- Idempotent: re-running is safe — the upsert updates rather than duplicates.
- Provenance: every row carries source_file; loaded_at auto-fills (UTC).
- Fault-tolerant loop: a failed station download is skipped, not fatal.

## Target table

raw.observations (all text except loaded_at):
  station_id, obs_date, element, value, m_flag, q_flag, s_flag, obs_time,
  source_file, loaded_at (timestamptz DEFAULT now())
  UNIQUE (station_id, obs_date, element)