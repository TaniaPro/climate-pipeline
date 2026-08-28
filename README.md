# Climate Pipeline

A data pipeline that collects decades of daily weather records from stations
across four continents and processes them to surface long-term warming trends.

## Overview

Individual hot days are weather; the trend underneath is climate. This project
ingests raw station data from NOAA's Global Historical Climatology Network
(GHCN-Daily), lands it in Postgres, and (in progress) models it into
temperature-and-precipitation metrics that make the warming signal visible over
time.

The seven countries tracked — **United States, Japan, Australia, Canada,
Germany, Spain, and France** — span four continents (North America, Asia,
Oceania, Europe). They were chosen deliberately for two reasons: a strong
warming signal, and deep, reliable station records. A global set tells a
stronger story than a single-region one, and avoids the thin coverage small
countries have in the long record.

Each station is kept only if it has **both** maximum temperature (TMAX) and
precipitation (PRCP) with continuous coverage from **1990 to 2025**, so
temperature and rainfall can be studied at the same place over the same period.
No single country is allowed to dominate: the set is capped at **75 stations per
country**, giving a balanced global sample of **491 stations**.

## Data source

NOAA GHCN-Daily, read from the public AWS S3 bucket `noaa-ghcn-pds` — a public
dataset of daily observations from ~127,000 weather stations worldwide. The
pipeline reads the per-station files (`csv.gz/by_station/`), decompresses them
in memory, and filters to the 491 selected stations. Reading the public bucket
requires no AWS account.

## Architecture

```
NOAA public S3 (noaa-ghcn-pds)
        │  fetch + parse in memory (no disk landing)
        ▼
   Postgres  raw schema        ← raw.observations (long/EAV), raw.stations
        │  dbt  (planned)
        ▼
   staging → marts             ← typed, pivoted, aggregated tables
        │
        ▼
   analysis / warming-trend metrics
```

One storage system (Postgres); `raw` / `staging` / `marts` are schemas
(layers) inside it, not separate tiers. The design is cloud-shaped — Postgres
maps to a cloud warehouse and local execution to managed orchestration as a
substrate swap if scale ever demands it, with no redesign.

## Ingestion

The ingestion layer is working end to end:

- **`select_stations()`** — reads the GHCN inventory and returns the 491 station
  IDs (7 countries, TMAX + PRCP, 1990–2025 coverage, capped at 75 per country).
- **`download_station(id)`** — fetches one station's full history from S3,
  decompresses gzip in memory, returns the text (or `None` on a failed fetch).
- **`parse_station(text, id)`** — stamps each row with its source file
  (provenance) before loading.
- **`load_station(text)`** — idempotent bulk load: `COPY` into a temporary
  staging table, then `INSERT … ON CONFLICT (station_id, obs_date, element) DO
  UPDATE`. New rows insert; existing rows update in place — re-running never
  duplicates.
- **`run_pipeline()`** — orchestrates the loop over all 491 stations, skipping
  any whose download fails so one bad station can't stop the run.

### Key properties

- **No disk landing** — files are fetched and processed in memory.
- **Idempotent** — re-running is safe; the upsert updates rather than duplicates.
- **Provenance** — every row carries `source_file`; `loaded_at` auto-fills (UTC).
- **Fault-tolerant** — a failed station download is skipped, not fatal.

## Raw table

`raw.observations` (all columns text except `loaded_at`):

```
station_id, obs_date, element, value,
m_flag, q_flag, s_flag, obs_time,
source_file, loaded_at (timestamptz DEFAULT now())
UNIQUE (station_id, obs_date, element)
```

Raw mirrors the source faithfully — no type conversion at this layer; casting,
unit conversion, and pivoting happen downstream in dbt.

## Tech stack

- **Python** — data ingestion (`requests`, `gzip`, `psycopg2`)
- **PostgreSQL** — storage / warehouse (raw schema live and loaded)
- **dbt** *(planned)* — staging and marts transformations
- **Airflow** *(planned)* — scheduled, recurring incremental orchestration
- **PySpark** *(planned)* — heavy analytical aggregation

## Status

- ✅ Station selection (491 stations, verified)
- ✅ S3 ingestion — fetch, parse, idempotent upsert load into Postgres
- ✅ Full backfill loaded (~52.5M rows across 491 stations)
- ⬜ Load manifest (resumability, backfill-vs-incremental switch)
- ⬜ `raw.stations` from `ghcnd-stations.txt`
- ⬜ Trailing-window incremental refresh (~90-day upsert)
- ⬜ dbt models (staging → marts)
- ⬜ Airflow scheduling
- ⬜ Analysis / warming-trend output

## Design decisions

Architectural choices — and the reasoning behind them, including tools
considered and rejected (Kafka, HDFS, a cloud warehouse, a separate file lake,
SNS/SQS push) — are documented in [DECISIONS.md](DECISIONS.md). The end-to-end
ingestion flow is in [PIPELINE.md](PIPELINE.md).