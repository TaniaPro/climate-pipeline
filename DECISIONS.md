# Decisions

## 2026-07-24

**Python 3.11.9, not 3.12**
Airflow lags behind the newest Python. Pinned with pyenv local so only
this folder uses it.

**Postgres, not Snowflake**
Free and never expires. A trial account would kill the project in 30 days.
> UPDATED 2026-08-07: reasoning revised — the primary case for Postgres over
> a cloud warehouse is scale-fit and ops overhead, not cost. See "No cloud
> warehouse (Redshift/Snowflake)" under 2026-08-07.

**data/ is gitignored**
Raw files are re-downloadable. Repos should hold code, not data.
> SUPERSEDED 2026-08-07: ingestion no longer lands raw files on disk at all —
> it fetches from S3 into memory and loads straight to Postgres. No data/ dir
> of raw CSVs exists in the current design. Kept for history. See "Target
> architecture" and "Source: read from public S3 bucket" under 2026-08-07.

**Forced IPv4 in fetch_observations.py**
requests hung forever on NOAA. curl worked. getaddrinfo showed IPv6
addresses listed first — Python tried them and stalled, curl fell back
to IPv4 automatically. Fixed by setting allowed_gai_family to AF_INET.
> SUPERSEDED 2026-08-07: source moved from the NOAA HTTP endpoint to the public
> S3 bucket (noaa-ghcn-pds), which doesn't have the IPv6-hang problem. The IPv4
> workaround is no longer the ingestion path. Kept for history — it's the reason
> S3's reliability was a deciding factor. See "Source: read from public S3
> bucket" under 2026-08-07.

## 2026-07-31

**Eight countries: SP, PO, FR, IT, GM, UK, GR, IS**
Chose European + Mediterranean + Israel stations for the project. These
regions had the strongest recent heat anomalies (2023-2026 heat domes) and
have long, reliable station records — which matters because the project
shows a long-term trend, not single hot days.
> SUPERSEDED 2026-08-01: switched to 7 data-rich countries across 4 continents
> (see "Went global instead of Europe-only"). Kept for history.

**FIPS codes, not ISO**
NOAA uses FIPS country codes, which differ from ISO. E.g. UK is "UK" in
FIPS but "GB" in ISO; Germany is "GM" not "DE". Using ISO codes would have
silently returned zero stations for those countries. Got codes from NOAA's
ghcnd-countries.txt.

**Filter by first 2 characters of station ID**
Station IDs are fixed-width; chars 0-1 are the FIPS country code. Filter
with line[:2] in the country list — checked "starts with", not "contains",
to avoid matching the code elsewhere in the ID.

## 2026-08-01

**Went global instead of Europe-only**
Switched from 8 European/Mediterranean countries to 7 data-rich countries
across 4 continents: US, Japan, Australia, Canada, Germany, Spain, France.
A global warming story is stronger than a regional one, and the European
set had too few long-record stations in small countries (Israel 4, Greece 8).
Chose countries for both warming signal and data availability.

**Require BOTH TMAX and PRCP, not either**
A station qualifies only if it has long records (1990-2025) for both
temperature and precipitation. Lets me study temp and rainfall at the same
place over the same period. Built via two sets (tmax_ok, prcp_ok) and their
intersection.

**Cap at 75 stations per country**
US and Australia had thousands of qualifying stations (5369, 2756) and would
dominate an uncapped dataset. Capping at 75 keeps it balanced and global.
Final result: 491 stations (US/SP/AS/JA/GM at 75, FR 68, CA 48).

**Inventory file lives at a different path than the CSVs**
Station CSVs: /data/global-historical-climatology-network-daily/access/
Metadata (inventory, stations): /pub/data/ghcn/daily/
Wrong path returns an HTML error page with status 200 — so check content,
not just status code.

## 2026-08-07

**Target architecture (end-to-end shape)**
NOAA public S3 (noaa-ghcn-pds)
  -> Python ingestion (fetch + parse in memory, no disk landing)
  -> Postgres `raw` schema (long/EAV observations + normalized stations)
  -> dbt (staging -> marts: typed, pivoted, aggregated wide tables)
  -> PySpark for heavy analytical aggregation
  -> LangGraph/Ollama agent layer (later stage)
All orchestrated by Airflow on a schedule (recurring incremental, not one-shot).
One storage system (Postgres); raw/staging/marts are schemas inside it, not
separate tiers. The stack is cloud-shaped: Postgres maps to Redshift/Snowflake
and local execution to managed Airflow as a substrate swap if scale later
demands it — no redesign.

**No Kafka**
Kafka is for unbounded, real-time streams. GHCN is finite, batch, historical
(491 files, 1990-2025). Streaming transport solves a problem this data doesn't
have — at real streaming volume it would earn its place, but here it's pure
overhead. (Also rejected topic-per-station: high-cardinality dimensions belong
as a message key, not as topics — moot since no Kafka.)

**No HDFS**
HDFS exists to store datasets too large for a single disk, spread across a
cluster of nodes. This data is tens of millions of rows — it fits on one
ordinary disk with room to spare, so there's nothing to distribute, no matter
how many nodes could be provisioned. Standing up and maintaining a NameNode/
DataNode cluster is cost and ops burden with no benefit at this size. And it
wouldn't be the choice even at large scale: modern "distributed storage" is
object storage (S3/GCS) queried by Spark/Trino, not a self-managed HDFS
cluster. Wrong tool at both ends — unnecessary here, legacy at scale.

**No cloud warehouse (Redshift/Snowflake) — Postgres**
Redshift is an MPP warehouse built and priced for hundreds of GB to petabytes
with heavy concurrent scans. This workload is tens of millions of rows —
Postgres handles it single-node for years before hitting a ceiling. Running
Redshift now means paying monthly for a cluster, plus the ops time to tune,
vacuum, and manage IAM/VPC/node sizing, to store a fraction of the data it's
designed for: cost and operational overhead with no matching benefit at this
scale. Postgres is one service with near-zero admin. There's no downside to
starting here — the whole stack (raw/staging/marts schemas, dbt, SQL) lifts to
Redshift or Snowflake as a substrate swap if data volume later forces the
upgrade. Right tool for the actual scale; upgrade when the data demands it.

**Single tier: Postgres only (no separate file-lake tier)**
A two-tier lake-then-warehouse split exists for reasons that don't apply here:
(1) schema-on-read — a lake lands raw files of any/unknown structure before
modeling, letting you re-model without re-ingesting; (2) one raw source feeding
many consumers — warehouse plus ML plus other teams reading the same files;
(3) replay — immutable raw files let you rebuild the warehouse differently
without re-fetching. This project has one uniform format (GHCN CSVs), one
consumer (this analysis), and cheap replay (re-fetch from NOAA's public S3, or
reload from the immutable raw schema). None of the three benefits are needed, so
the lake tier is cut. One storage system; raw/staging/marts are schemas (layers)
inside Postgres, not separate tiers. If a second consumer or mixed-format
sources appear later, a file lake in front becomes justified — a clean addition,
not a rework.

**Raw stored in Postgres, not Parquet files**
Parquet is a plain file: no keys, no constraints, no transaction if a load
half-fails. Raw is loaded incrementally and must be idempotent and safe on
partial failure — that wants a database. Parquet's advantage (cheap columnar
scans at massive scale) doesn't apply at this volume. Parquet still used later,
for the PySpark aggregation stage — right tool, different layer.

**Source: read from public S3 bucket (noaa-ghcn-pds), not the HTTP endpoint**
S3 wins on four points: (1) sidesteps the IPv6 hang that forced the IPv4 fix on
the HTTP endpoint; (2) built for bulk programmatic access, not occasional web
downloads; (3) exposes per-file Last-Modified + ETag metadata for cheap change-
detection without downloading the file; (4) supports listing the bucket
programmatically. Cost: needs boto3 + anonymous access (--no-sign-request).

**No SNS/SQS push ingestion — scheduled polling instead**
NOAA offers an SNS topic (NewGHCNObject) for event-driven new-data pushes.
Rejected for three reasons:
  1. No latency need — long-term trend data (1990-2025); minutes-fresh vs
     day-fresh is irrelevant to a decades-long signal.
  2. No need for push — the source updates ~daily; a scheduled poll catches
     every update without an AWS account, an SQS queue, and credentials.
  3. The data isn't final when it lands — GHCN revises recent observations for
     ~45-60 days after month-end. Reacting to pushes means reprocessing dates
     still settling. A scheduled poll + trailing-window upsert absorbs
     revisions naturally.
Cost note: SQS would have stayed within the permanent 1M-request/month free
tier — but only by polling the queue from the scheduler, NOT via Lambda (a
Lambda-triggered queue idle-polls ~130k-1.7M requests/month and can exhaust
the free tier while doing nothing). Cost wasn't decisive; fit was.

**File model: one file per station, rewritten in place**
NOAA does NOT publish a new file per day. Each station has ONE file holding its
full history; updates rewrite that same file (new recent rows + revised older
rows). Nothing inside the file marks what changed — no update/version column.
So "did it change" is answered by file-level signals (S3 Last-Modified / ETag /
content hash), and "what changed" is handled by upsert on load.

**raw.observations is long (EAV), not wide**
GHCN access files are wide (a column pair per element) and the element set
varies by station. Mirroring wide means the raw schema changes every time a new
element (AWND, TAVG, WTxx...) appears. Long — (station_id, obs_date, element,
value, attributes) — makes the element name data instead of structure, so the
table shape is frozen and absorbs any element as rows. Cost is more rows per
station/day; acceptable for a raw landing layer whose job is to swallow
anything without schema churn. Wide/split comes back later, built by dbt in
staging/marts (long to land, wide to analyze — layer determines shape).

**Station facts split into raw.stations (normalization)**
LATITUDE/LONGITUDE/ELEVATION/NAME are identical on every row for a station —
they depend on station_id alone, not on the observation key. Kept in
observations they'd be duplicated ~24k times per station and risk update
anomalies (a half-finished coordinate fix leaves contradictory values). Split
into raw.stations keyed by station_id (a fact lives in exactly one place);
station_id is the foreign key linking the tables.

**Pipeline is recurring incremental, not one-shot**
GHCN updates ~daily and reconstructs weekly, so this isn't a backfill-and-stop
job — it runs on a schedule. This is what justifies Airflow existing at all.

**Load strategy: per-station backfill-or-incremental via the load manifest**
Per station, each run: if the station has no successful load in the manifest ->
full-history backfill. If already loaded -> pull a trailing recent window and
upsert. Window padded to ~90 days to safely cover NOAA's 45-60 day revision
cycle (padding is nearly free — extra days are no-op overwrites; too small a
window would miss revisions). Upsert keyed on (station_id, obs_date, element):
new rows insert, revised rows overwrite. The load manifest (station_id, status,
row_count, loaded_at) is the backfill-vs-incremental switch — per-station,
survives crashes, auto-handles brand-new stations. Not a global "first run"
flag.

## 2026-08-08

**Source layout: csv.gz/by_station/, decompressed in-flight**
Verified against the live bucket (noaa-ghcn-pds), not just docs. The bucket
exposes data both by_station and by_year, in csv / csv.gz / parquet.

Chose by_station, not by_year: the project loads 491 specific stations' full
history. by_station lets me fetch exactly those files by ID (csv.gz/by_station/
{station_id}.csv.gz); by_year would download all ~133k global stations per year
and discard 99.6%. Year filtering happens at load time in code, so by_station's
lack of a year filter costs nothing. by_station also matches the per-station
architecture (per-station manifest, backfill-or-incremental, station_id key).

Chose csv.gz over csv: ~10x smaller over the wire (verified: ACW00011604 is
41 KB as .csv vs 4 KB as .csv.gz; AE000041196 is 2 MB vs 254 KB). Downloaded
gz is decompressed in memory and parsed — never written to disk (consistent
with no-disk-landing).

Path pattern: csv.gz/by_station/{station_id}.csv.gz

Note for change-detection (still open): the whole by_station set is regenerated
in bulk each refresh cycle (all files show near-identical Last-Modified
timestamps), so Last-Modified changes on nearly every file every cycle whether
or not its data changed — a weak "did the data change" signal. A content hash
would be needed to catch "regenerated but identical." Decide skip-strategy later.

**Dataset documentation reference**
Authoritative field/format definitions for GHCN-D come from the awslabs
open-data-docs README (github.com/awslabs/open-data-docs/tree/main/docs/noaa/
noaa-ghcn): observation row format (ID, DATE, ELEMENT, DATA_VALUE, M/Q/S flags,
OBS-TIME), full element definitions, source-flag priority order, and the fixed-
width specs for ghcnd-stations.txt and ghcnd-inventory.txt. Use it as the
reference for parsing positions and element meanings rather than guessing.

**raw.stations sourced from ghcnd-stations.txt, not the observation files**
Station metadata (lat/lon/elevation/name/state/WMO) is available two ways: (a)
repeated on every row of each observation CSV, or (b) as a dedicated one-row-
per-station file, ghcnd-stations.txt. Chose (b): it's the authoritative source
that treats station facts as station facts (matches the normalization decision
to keep them in raw.stations, not duplicated across observation rows), it has
fields the observation CSVs lack (STATE, GSN/HCN flags, WMO ID), and it's one
small file to load instead of parsing 491 observation files and de-duping their
repeated coordinate columns. Fixed-width (not CSV) — parse by column positions,
same style as ghcnd-inventory.txt:
  ID 1-11, LATITUDE 13-20, LONGITUDE 22-30, ELEVATION 32-37, STATE 39-40,
  NAME 42-71, GSN 73-75, HCN/CRN 77-79, WMO 81-85.
Lives on S3 at noaa-ghcn-pds/ghcnd-stations.txt (consistent with S3 source).
> Positions verified against a real line on 2026-08-29 (see that entry) — the
> Python slices are [0:11], [12:20], [21:30], [31:37], [38:40], [41:71].

**Considered and rejected: superghcnd_diff for change-detection**
superghcnd is a separate distribution of the same data as one merged file,
published daily as superghcnd_full (entire dataset, ~tens of GB) and
superghcnd_diff (only rows changed since the last run, across all stations).
The diff file directly states "what changed" — tempting for change-detection.
Rejected because it doesn't fit this project's scale or architecture:
  1. It's all-stations — using it means downloading every station on Earth's
     daily changes and filtering to our 491 (the by_year problem we already
     rejected).
  2. It overturns the load model — full+diff is "load the whole blob once, then
     apply daily deltas," vs. our per-station-file + trailing-window upsert.
  3. Our incremental strategy already handles revisions: re-pull the 491
     stations' trailing ~90-day window and upsert catches both new and revised
     rows, scoped to exactly our stations, no giant-file filtering.
The diff is built for mirroring the ENTIRE GHCN dataset, where re-pulling
everything daily is infeasible so a delta is essential. At 491 stations,
re-pulling a small window is trivial — the delta solves a problem we don't have,
at the cost of an all-stations download and an architecture rewrite. Same
scale-fit logic as the other rejections.

**by_station file format: long/EAV, no header, 8 comma fields**
Confirmed by fetching a real station (ACW00011604). The by_station CSV is
already long/EAV — one row per station/date/element — NOT the wide format the
older access/ CSVs used. So no wide->long pivot is needed in parsing; the source
arrives in the target shape. No header row. Fields, in order:
  station_id, date (YYYYMMDD), element, value, m_flag, q_flag, s_flag, obs_time
Example: ACW00011604,19490101,TMAX,289,,,X,

**Fetch rewritten to S3, IPv4 hack removed, verified working**
download_station now fetches csv.gz/by_station/{id}.csv.gz from S3, decompresses
in memory (gzip.decompress on response.content — bytes, not .text), returns text,
no disk write. The old NOAA HTTP endpoint and the IPv4/allowed_gai_family hack
are gone — S3 doesn't have the IPv6 hang. Tested against ACW00011604: fetched,
decompressed, printed readable rows. download_station_inventory likewise moved to
the S3 URL and no longer writes to disk.

**raw.observations stored fully as text (raw = as-is)**
Every field from the source file is stored as text, no conversion at the raw
layer (dates stay YYYYMMDD strings, values stay integer-tenths strings). Raw
mirrors source; casting/typing happens later in dbt. Columns:
  station_id, obs_date, element, value, m_flag, q_flag, s_flag, obs_time (from
  the file), plus source_file (provenance) and loaded_at (timestamptz DEFAULT
  now()). Table created in the raw schema.
M/Q/S flags kept as three separate columns (the by_station format supplies them
separately), reversing the earlier "packed attributes" idea, which was based on
the wide access/ format.

**Database timezone set to UTC**
ALTER DATABASE climate SET timezone = 'UTC'. timestamptz already stores UTC
internally; this makes display UTC too, so stored and shown match. Removes
session-dependent display confusion for loaded_at.

**No index on raw.observations (yet)**
Raw is a bulk-load landing table, not queried directly for analysis (dbt reads
it once and builds indexed marts downstream). Indexes slow bulk loads, so none
now. A UNIQUE (station_id, obs_date, element) constraint will be added later —
required for the incremental upsert (ON CONFLICT) — which brings its own index
for correctness, not query speed.
> DONE 2026-08-27: the UNIQUE constraint was added and the loader now upserts.

**Code structure: nothing runs on import**
fetch_observations.py was a script with loose top-level code that ran (and hung)
on import. Refactored to only define functions — download_station,
download_station_inventory, parse_station, select_stations (selection logic
wrapped, returns the station IDs) — with a __main__ block that runs the selection
count only when executed directly.

## 2026-08-22

**Loader: COPY into raw.observations, with source_file provenance**
load_station bulk-loads a station's parsed text into raw.observations via
Postgres COPY (FROM STDIN, FORMAT csv), not row-by-row INSERT — COPY is built
for bulk and the source grows over time (daily updates + revisions), so bulk is
the right fit. psycopg2 (already installed) is the driver; copy_expert feeds the
text through a cursor.

parse_station stamps each line with source_file (the station id) before loading,
so COPY fills 9 columns: the 8 from the file (station_id, obs_date, element,
value, m_flag, q_flag, s_flag, obs_time) + source_file. loaded_at is not in the
COPY list — it auto-fills from the table's DEFAULT now(). source_file is kept for
future issue investigation (which file a row came from).

Note COPY does the field-splitting itself, so parse_station does NOT split lines
into fields — it only appends provenance. The line already ends in a trailing
comma (empty obs_time), so appending ",{id}" lands the id in source_file and
leaves obs_time empty: ...,X, -> ...,X,,ACW00011604 (9 fields).

Verified end-to-end on ACW00011604: 1231 rows loaded, all columns correct,
source_file populated, loaded_at stamped in UTC.
> SUPERSEDED 2026-08-27: the append-only COPY-straight-into-raw.observations was
> replaced by the idempotent COPY-to-staging + upsert (see 2026-08-27). The
> provenance / column-mapping details above still hold.

## 2026-08-27

**Idempotent loader via upsert (COPY to staging, then INSERT ON CONFLICT)**
Reworked load_station so re-running is safe (no duplicate rows). COPY can only
append and can't do ON CONFLICT, so the loader now: (1) CREATE TEMP TABLE staging
with the 9 loaded columns; (2) COPY the text into staging (fast bulk load); (3)
INSERT INTO raw.observations SELECT ... FROM staging ON CONFLICT (station_id,
obs_date, element) DO UPDATE SET value/flags/obs_time/source_file = EXCLUDED.*.
New rows insert; rows matching an existing key update in place. Temp table is
auto-dropped at session end (no cleanup, no cross-run collision). loaded_at is
not overwritten on update — keeps its original insert time.

Prerequisite done first: TRUNCATEd the one-station test data (clean slate), then
added UNIQUE (station_id, obs_date, element) on raw.observations — the constraint
the upsert keys on.

Verified idempotent: loaded ACW00011604 (1231 rows), loaded the exact same data
again, count stayed 1231 — the second load updated in place instead of
duplicating.

**Content hash considered and rejected (for now)**
Considered hashing rows/files to detect changes. Rejected: the upsert already
makes re-loads correct (a revised value overwrites via DO UPDATE), so a per-row
hash is redundant. A file-level hash would only help SKIP unchanged files (an
optimization, not correctness) and belongs in the load manifest, not in
parse_station — deferred to the change-detection decision.

**run_pipeline() orchestrates the full loop**
New file ingestion_pipeline_run.py imports the functions from fetch_observations
and runs the chain for every station: select_stations() -> for each id ->
download_station -> parse_station -> load_station. Orchestration kept separate
from the piece functions so the pieces stay reusable/testable. A None guard skips
any station whose download failed (if text is None: continue), so one bad fetch
doesn't kill the whole run. Progress is printed per station (i/total).

**Full backfill loaded**
Ran run_pipeline over all 491 stations. Result: 52,454,918 rows in
raw.observations across 495 distinct stations. This is the whole ingestion layer
working end to end at full scale.

**Raw holds 495 stations (491 + 4 test leftovers) — filter in dbt, don't delete**
The backfill table has 495 distinct stations, but the selected set is 491. The
extra 4 are leftovers from earlier test loads (e.g. ACW00011604 and slice-test
stations not in the 7-country set). Decided NOT to delete them from raw: a DELETE
against 52M rows is riskier than the problem, and filtering belongs in dbt
staging anyway. The staging model will restrict observations to the 491 (by
joining against raw.stations / the selected list). Consistent with the
raw-absorbs-everything principle — raw lands faithfully; curation happens
downstream. A clean truncate + reload would also give exactly 491 if ever wanted.
> SUPERSEDED 2026-10-11: orphans grew to 245 stations / 28.7M rows after the
> selection change; deleted from raw instead. See 2026-10-11.

**Docs: README + PIPELINE.md**
Added PIPELINE.md (end-to-end ingestion flow) and rewrote README.md, which was
stale (still described the abandoned 8-country European set and marked Postgres
"planned"). README now reflects the real 7-country global set, the working
Postgres ingestion, accurate architecture, and a status checklist. Keep both
current as later stages land.

## 2026-08-29

**raw.stations loaded from ghcnd-stations.txt (491 stations)**
Built the station-metadata side of the raw layer, in a new file fetch_stations.py:
  1. download_station_meta_data() — fetches ghcnd-stations.txt from S3 (plain
     .txt, not gzipped), returns lines. Same S3-source pattern as the inventory.
  2. parse_stations_meta_data() — fixed-width parse (slice by column position,
     strip padding), filtered to our 491 via set(select_stations()) for O(1)
     membership against ~127k lines. Returns (station_id, latitude, longitude,
     elevation, state, name) tuples.
  3. load_stations() — upserts into raw.stations.
Column positions verified against a real line (repr), not just docs:
  [0:11] id, [12:20] lat, [21:30] lon, [31:37] elev, [38:40] state, [41:71] name.
Verified: 491 rows in raw.stations, all fields clean, loaded_at stamped UTC.

**station_id is the PRIMARY KEY on raw.stations**
Unlike raw.observations (a station has thousands of rows, so the key is the
composite station_id+obs_date+element), each station appears exactly once here,
so station_id is a natural primary key — enforces uniqueness, indexes the join
column dbt will use, and enables the upsert.

**Simple upsert load (execute_values + ON CONFLICT), not COPY-to-staging**
raw.stations is tiny (491 rows), so the bulk COPY-to-staging machinery used for
the 52M-row observations isn't needed. Used psycopg2 execute_values to insert all
rows in one statement with ON CONFLICT (station_id) DO UPDATE. Right tool for the
scale — bulk COPY for millions of rows, single-statement upsert for hundreds.

**Orchestrator split into two named pipelines**
ingestion_pipeline_run.py now has run_observations_pipeline() (loops 491 stations:
download -> parse -> load, with None-skip + progress) and run_stations_pipeline()
(one file, all stations at once: parse -> load — no loop needed). Renamed from the
old generic run_pipeline.

**Raw layer complete**
Both raw tables are now loaded: raw.observations (52.5M rows) and raw.stations
(491). This is the full raw ingestion layer — the foundation for dbt
staging/marts.

## 2026-09-12

**Load manifest (meta._load_manifest) — resumability + per-station status**
Added a dedicated `meta` schema (operational bookkeeping, kept separate from
`raw` data) with a load-manifest table: station_id (PK), status, error,
row_count, updated_at (timestamptz DEFAULT now()). One row per station recording
its load outcome. Statuses tracked: 'success' and 'failed' (skipped 'in_progress'
— idempotent upserts make a half-load safe to redo, so absence-of-success already
signals "not done"; in_progress would only add live-run visibility, not
correctness).

Three helper functions (record_manifest.py):
  - record_manifest(station_id, status, error, row_count) — upserts the outcome
    (ON CONFLICT (station_id) DO UPDATE, so a retry overwrites the prior attempt;
    updated_at = now() on update, not EXCLUDED, to stamp the latest attempt).
  - is_loaded(station_id) — SELECT 1 ... WHERE status='success'; returns True/False.
    Only 'success' counts, so failed stations are retried, not skipped.
  - load_observations now returns cursor.rowcount (rows upserted) so the loop can
    record row_count.

Wired into run_observations_pipeline: per station — skip if is_loaded (resumability),
record 'failed' if download returns None, else load + record 'success' with row_count.
Verified: loaded a slice, manifest populated with real row counts; is_loaded returns
True for a recorded station (would skip it) and False for failed/unrecorded ones.

**Deterministic station selection (sorted)**
select_stations() built the list from a set (unordered), so both the selected 491
AND their order varied run to run — which made slice-testing misleading and
weakened resumable ordering. Fixed by iterating sorted(both) in the cap loop
(makes WHICH 75-per-country survive deterministic) and returning sorted(station_ids).
Now the same 491 in the same order every run. Verified: 491, same per-country
counts (AS/GM/JA/SP/US=75, FR 68, CA 48), first IDs stable (ASM00094299...).
> NOTE 2026-09-25: this change is what caused the roster/data drift bug — the
> selection changed after raw.stations had already been loaded from the old one.
> See "BUG: roster/data drift" under 2026-09-25.

**Function rename for clarity**
load_station -> load_observations (loads observation rows) and load_stations ->
load_station_metadata (loads the stations table). The one-letter singular/plural
difference was a footgun. Pure rename across definitions, imports, call sites,
and docs; DECISIONS.md left unchanged (records the names as they were at each
dated decision).

## 2026-09-25

**dbt set up and connected (climate_dbt project)**
Installed dbt-core 1.12.5 + dbt-postgres 1.11.0 in the project venv. `dbt init`
scaffolded climate_dbt/ but its interactive password prompt looped (the local
Postgres had no password to give), so the connection profile was written by hand
in ~/.dbt/profiles.yml — which lives outside the repo, so credentials never reach
git. The profile block name must match `profile:` in dbt_project.yml.

Key thing to remember: the `schema: analytics` line in profiles.yml is what
directs where dbt builds EVERY model — nothing in the SQL says it. dbt wraps your
SELECT as `CREATE VIEW <target_schema>.<filename>`, taking the schema from the
profile and the object name from the .sql filename.

**First staging models: stg_stations, stg_observations**
Declared raw.observations and raw.stations as dbt sources (_sources.yml), then:
  - stg_stations — casts latitude/longitude/elevation text->numeric, NULLIF('')
    on state.
  - stg_observations — to_date(obs_date,'YYYYMMDD') (a plain ::date cast FAILS on
    the no-dashes format), value::integer, NULLIF('') on the flags, and filters to
    the 491 with `WHERE station_id IN (SELECT station_id FROM {{ ref('stg_stations') }})`.
Both default to views. {{ source() }} references a raw table; {{ ref() }} references
another dbt model (and gives dbt the dependency order).

Why filter in staging when ingestion already selects 491: ingestion controls what
gets FETCHED, but raw accumulates strays (test loads, older selections). Staging
enforces "exactly the 491" rather than trusting upstream — each layer defends its
own correctness instead of assuming the one above is clean.

**BUG: roster/data drift after changing select_stations() — stg_observations
showed only 312 of 491**
Symptom: stg_stations = 491, raw.observations = 736 distinct stations, but
stg_observations = 312; the manifest claimed 500 successes and zero failures.

Root cause: the 2026-09-12 sorting change. Adding sorted(both) before the
per-country cap changed WHICH 75 stations survive per country, so select_stations()
began returning a different 491. raw.stations (loaded 08-29, pre-sort) still held
the OLD roster, while later pipeline runs loaded observations for the NEW 491. The
dbt filter matched new data against the stale roster, leaving only the overlap.
Counts decomposed exactly (491 + 9 + 236 = 736), confirming a selection/temporal
mismatch — not an ID-format problem and not a load failure.

Fix: truncate raw.stations, reload from the current select_stations(). Truncate was
required because load_station_metadata upserts and never deletes — a plain re-run
would have left the old stations in place. After the reload, stg_observations = 491.
No observation re-fetch was needed: the data was already there; only the roster was
stale.

**Jinja typo in stg_stations.sql**
`{ { source('raw','stations') } }` (spaces inside the braces) — invalid Jinja that
would have broken the next dbt run. The live Postgres view still worked because it
had compiled before the edit. Fixed to `{{ source(...) }}`.

**Fixed: 0-row loads were being recorded as "success"**
load_observations returns cursor.rowcount, but the pipeline recorded "success"
regardless of the value. A station whose download returned HTTP 200 with an empty
body would load 0 rows, be marked success, and then be skipped forever by
is_loaded — a silent, permanent gap (only the status code was checked, never the
content). Exactly the class of confusion that caused the roster-drift debugging
above, so fixed rather than deferred: a 0-row load is now recorded as failed
("loaded 0 rows") and the station is retried on the next run.

**Credentials: removed the DB password entirely**
The Postgres password had been exposed, so it was retired. Rather than rotating it,
removed it altogether (ALTER USER ... WITH PASSWORD NULL) — the database is
local-only, listening on localhost, holding public NOAA data, and uses trust auth,
so a password guarded only against an attacker already on the machine.
profiles.yml now has `user: "{{ env_var('DBT_USER') }}"` and `pass: ""`.
Note: dbt-postgres REQUIRES the `pass` key to exist — omitting it fails with
"'password' is a required property" — so it's present but empty. No secrets in
profiles.yml at all.

## 2026-10-11

**Frozen roster: raw.stations is the single source of truth**
The roster-drift fix on 09-25 (rebuild raw.stations) was not hermetic — it relied
on remembering to rebuild whenever selection criteria changed. That discipline had
already failed once. Worse, NOAA adding stations upstream could shift which 75
survive the per-country cap, changing the 491 with no code change at all.

Decided the roster should be STABLE, not live: a warming-trend analysis compares
the same places across years, so a moving station set would muddy the signal.
Changing the population should be a deliberate act, not a side effect of an
upstream refresh.

Implementation: added get_roster() (SELECT station_id FROM raw.stations ORDER BY
station_id, flattened to a list of strings). run_observations_pipeline() now calls
get_roster() instead of select_stations(). select_stations() stays as the one-time
roster-BUILDING tool, documented as such, called only via run_stations_pipeline().

This removes the two-sources-of-truth (computed vs. stored) that caused the drift
bug. There is now only one list, so there is nothing to drift against — structural,
not disciplinary.

**Ops note: stale postmaster.pid blocked Postgres startup**
After a reboot, Postgres refused to start: "lock file postmaster.pid already
exists ... Is another postmaster (PID 726) running?". PID 726 turned out to be
BTLEServerAgent — the OS had recycled the PID from an old Postgres run, so the
stale lock pointed at an unrelated process. Verified with `ps -p 726` BEFORE
deleting (removing a live server's lock file can corrupt data), then removed the
lock and restarted; automatic WAL recovery ran cleanly. Also had to `brew update`
first — `brew services` was broken by a formula/Homebrew version mismatch
("undefined method 'stop_timeout'").

**Deleted orphan observations from raw (28.7M rows, 245 stations)**
After the roster-drift fix, raw.observations still held data for 245 stations
not in the roster — residue from abandoned selections (pre-sort runs, test loads).
That was 28,713,506 rows, roughly a third of the table. The staging filter hid
them from analysis, but every stg_observations read still scanned and discarded
them.

Reversed the 2026-08-27 "filter in dbt, don't delete" decision: that was made for
4 test leftovers, where a DELETE wasn't worth the risk. At 245 stations / 28.7M
rows the trade flipped — these aren't source data for this project, they're
artifacts of a selection no longer in use, and deleting is safe because raw is
fully re-fetchable from S3.

Process: counted first, then deleted inside a transaction (BEGIN), confirmed the
DELETE count matched the pre-count exactly and distinct stations = 491, then
COMMIT. Ran VACUUM FULL afterwards: DELETE only marks rows dead (MVCC keeps old
versions for open transactions); VACUUM FULL rewrites the table without them and
returns the disk space. A one-off for a mass delete; routine cleanup is left to
autovacuum.

Also removed 9 stale manifest rows (stations no longer in the roster), same
count-then-transaction pattern. Result: raw.stations, raw.observations,
meta._load_manifest and stg_observations all agree on the same 491 stations.

**Drop QC-flagged observations in staging (q_flag)**
GHCN sets q_flag on a value that FAILED one of NOAA's quality checks (e.g. I =
internal consistency, D = duplicate, O = climatological outlier, S = spatial
consistency vs. neighbours, X = bounds check). Measured on TMAX/PRCP: 25,960,621
clean values vs ~30,300 flagged — about 0.1%.

Decision: drop them. One impossible value (say a 70C TMAX) skews a station's
yearly average upward — the worst kind of error in a warming-trend analysis —
while losing 0.1% of the data costs almost nothing.

Where: in staging (stg_observations), not in each mart. Filtering per mart would
make every future mart responsible for REMEMBERING `q_flag IS NULL`; forget it once
and that mart silently includes bad values. That's the same remember-to-do-X
pattern that caused the roster drift. Filtering once in staging makes every mart
clean by construction. Nothing is lost: raw still holds every flagged value for
audit.

Implementation: added `AND (q_flag IS NULL OR q_flag = '')` to the WHERE clause.
Two traps worth remembering:
  - WHERE reads the RAW column, not the SELECT's NULLIF(...) alias — so the check
    must treat both NULL and '' as "no flag".
  - The parentheses are required: SQL evaluates AND before OR, so without them
    `... AND q_flag IS NULL OR q_flag = ''` would let any empty-flag row through
    regardless of station, silently breaking the 491 filter.
Also: dbt models must NOT end with a semicolon — dbt wraps the SELECT in
CREATE VIEW ... AS ( ... ), and a `;` inside ends it early.

Verified: after rebuild, q_flag shows only NULL with 25,960,621 rows — exactly the
pre-filter clean count, so no clean row was lost — and distinct stations = 491.

---

## Open / undecided (current)

**Data quality / cleaning (not yet designed — next big staging decision)**
raw is deliberately unfiltered, so staging has to decide what "clean" means.
Known things to handle:
  - q_flag: DONE 2026-10-11 — flagged values dropped in stg_observations.
  - Missing-value sentinels: GHCN uses -9999 for missing in some distributions.
    Confirm whether the by_station CSVs contain them and strip if so, or a single
    bad row poisons any average.
  - Physically implausible values (e.g. TMAX of 60C, negative PRCP) that pass QC
    but shouldn't enter a trend.
  - Partial years / sparse stations: a station-year with only a handful of days
    shouldn't be averaged as if it were a full year. Decide a minimum-coverage
    threshold before yearly aggregation.
  - Elements beyond TMAX/PRCP are present in raw; marts should select explicitly
    rather than aggregate whatever is there.
Decide these as staging/marts rules, documented here, before the trend numbers
mean anything.

- Change-detection skip strategy (file-level hash vs. always-pull window;
  Last-Modified already noted as weak).
- Trailing-window incremental load (re-pull ~90 days + upsert) now that backfill
  is done.
- Switch print -> logging in run_observations_pipeline (prod-grade: timestamps,
  levels, log-to-file; partly handled by Airflow later).
- Guard: download_station_inventory can return None on a failed fetch;
  select_stations would then crash on "for line in lines". Add a guard.
- Materialization: stg_observations is a view over 52M rows. Consider switching to
  table if marts queries get slow.
- dbt test to catch roster/data gaps loudly (e.g. no station marked success in the
  manifest with zero rows). Must run AFTER the observations load, or a legitimately
  new station would false-alarm.
- Next phase: marts layer — pivot long->wide (TMAX/PRCP as columns), aggregate by
  year, compute the warming trend.

## Resolved (was open, now done)
- Full backfill: all 491 loaded — DONE (2026-08-27, 52.5M rows).
- Loop all 491 (fetch->parse->load) with per-station error handling — DONE
  (None guard + progress, 2026-08-27).
- Idempotency: UNIQUE (station_id, obs_date, element) + upsert — DONE (2026-08-27).
- Parser + loader — DONE (parse_station 2026-08-22; upsert loader 2026-08-27).
- raw.stations loaded from ghcnd-stations.txt (491, PK on station_id) — DONE
  (2026-08-29). Also serves as the authoritative project station list.
- Load manifest (meta._load_manifest) + wired into pipeline (skip/record) — DONE
  (2026-09-12). Also made station selection deterministic (sorted).
- dbt installed, connected, first staging models built — DONE (2026-09-25).
- Roster/data drift diagnosed and fixed by rebuilding raw.stations — DONE
  (2026-09-25).
- 0-row loads recorded as success (silent skip-forever gap) — FIXED (2026-09-25).
- dbt staging filters observations to the 491 — DONE (2026-09-25, the WHERE ...
  ref('stg_stations') clause).
- Roster made hermetic: pipeline reads the frozen roster via get_roster(), one
  source of truth — DONE (2026-10-11).
- Orphan observations removed from raw (28.7M rows, 245 stations) + stale manifest
  rows; all layers consistent at 491 — DONE (2026-10-11).
- QC-flagged values (q_flag) dropped in staging, not per mart — DONE (2026-10-11).