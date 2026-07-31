# Climate Pipeline

A data pipeline that collects decades of daily temperature records from
weather stations across Europe, the Mediterranean, and Israel, and processes
them to surface long-term warming trends.

## Overview

Individual hot days are weather; the trend underneath is climate. This
project ingests raw station data from NOAA's Global Historical Climatology
Network (GHCN-Daily), cleans and models it, and produces temperature-anomaly
metrics that make the warming signal visible over time.

The eight countries tracked (Spain, Portugal, France, Italy, Germany, the UK,
Greece, and Israel) were chosen for their strong recent heat anomalies and
their long, reliable station records.

## Data source

NOAA GHCN-Daily — a public dataset of daily observations from ~127,000
weather stations worldwide. This pipeline filters to stations in eight
selected countries.

## Tech stack

- **Python** — data ingestion
- *(planned)* PostgreSQL, dbt, Airflow — storage, transformation, orchestration

## Status

Early development. Ingestion layer in progress.