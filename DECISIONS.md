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

## 2026-10-17

**No missing-value sentinels (-9999) — verified, nothing to clean**
GHCN's -9999 "no data" code belongs to the fixed-width .dly distribution. Checked
stg_observations: 0 rows with value = -9999. The by_station CSVs simply OMIT days
with no data — a missing day is a missing row, not a fake value. Recorded as a
finding rather than skipped. Consequence that matters later: missing days are
invisible, so completeness has to be measured by counting rows against the
calendar, never by looking for a sentinel.

**No extra plausibility filter on top of NOAA's QC**
Checked the extremes in clean data (values in tenths): TMAX -52.1C to 52.2C,
PRCP 0 to 806.0 mm/day. All plausible: 52C occurs in Australian/US deserts; a
daily HIGH of -52C occurs in Canada's far north in deep winter; the 806 mm day is
Owase, Japan, 1968-09-26 — one of Japan's wettest places, peak typhoon season,
and its q_flag is empty (passed every NOAA check). Its `I` is in s_flag, the
SOURCE flag, not a quality flag.
Decided against a custom range filter: (1) it would catch nothing today; (2)
NOAA's QC already runs a bounds check (q_flag = X), which staging already drops;
(3) badly chosen limits would silently delete real extremes — and in a climate
analysis extremes are signal, not noise.

**Completeness rule for yearly aggregation (WMO-based)**
Problem: a station-year with gaps produces a biased "yearly average" — e.g. a year
missing all of winter averages fake-hot, faking a warming signal.

Measured before deciding (TMAX, 1990–2025):
  - 17,303 station-years exist (vs 491 x 36 = 17,676 — ~370 station-years have no
    TMAX at all; invisible as rows).
  - Under a simple "fewer than 300 days" test, 2,600 (15%) are thin — MORE common
    in the analysis period than overall (11%), because station selection only
    checked that records START by 1990 and END by 2025, never completeness in
    between.
  - Thin years spread: 318 at 290–299 days, 1,194 at 200–289, 729 at 100–199,
    359 under 100.

Why not a total-days threshold: two years with 250 days can differ completely —
gaps scattered across the year (average roughly fine) vs. one whole season
missing (average biased). A day count can't tell them apart; checking coverage
per MONTH can.

Why not a per-station rule (keep stations with a good AVERAGE of days/year): a
station with 35 full years and one 40-day summer-only year averages ~356 days and
passes, yet that one year shows a fake spike in its trend. The problem is a
specific year, not the station — so the rule applies per station-year: drop the
bad year, keep the station's good years.

Rule adopted (domain standard, WMO "3/5 rule" — simpler half first):
  1. A month is valid if it is missing at most 5 days
     (days_in_month - observed_days <= 5).
  2. A year is valid only if all 12 months are valid. A month with zero data has
     no rows at all, so it never counts toward the 12 — the rule catches it
     automatically.
  3. The yearly value will be the average of the 12 monthly averages, so every
     month weighs equally.
  4. The current, unfinished year is always excluded (it is partial by
     definition, even with daily refresh).

Impact: ~70–75% of station-years pass (about 320–370 valid of ~470–487 each
year). Accepted: ~340 valid stations per year is ample for a trend, the rule is
defensible as the WMO standard, and fewer trustworthy values beat more biased
ones. The pass rate is steady across years — no decade disproportionately cut —
so the rule doesn't itself shift the trend.

Where: this needs grouping (station/year/month), so it belongs in the marts layer,
not staging (staging works row by row). Built and measured today as an ad-hoc
query (CTEs: per station-month counts -> per station-year valid months -> totals);
not yet a dbt model.
UPDATED 2026-10-25: implemented as dbt models — two intermediate steps plus one
mart (see 2026-10-25).

Source for the WMO rule: Utah Climate Center, Calculation of Normals
(climate.usu.edu/help/normals.php).

## 2026-10-25

**dbt layering: staging -> intermediate -> marts, named by grain**
Turned the completeness query into dbt models. Split it into one model per step
instead of one big model, so each step can be checked on its own (a wrong count is
traced to the step that produced it) and reused later (e.g. the monthly step for
PRCP).

Layers, following the dbt convention:
  - staging/ (stg_): 1:1 with the source, row-level cleaning only (casts, renames,
    filters, unit conversion). No GROUP BY.
  - intermediate/ (int_): middle steps, not queried directly.
  - marts/ (fct_ / dim_): final tables people query. fct_ = measurements,
    dim_ = descriptive entities (e.g. stations).
Aggregation is business logic, so it starts in intermediate, never in staging.

Models are named by their GRAIN — the columns that make a row unique:
  - int_station_monthly: one row = station + month
  - int_station_yearly_validity: one row = station + year
  - fct_station_yearly: one row = station + year, valid years only
Pipeline:
  stg_observations -> int_station_monthly -> int_station_yearly_validity
  -> fct_station_yearly

**Unit conversion in staging (tenths -> real units)**
GHCN stores TMAX/TMIN in tenths of a degree C and PRCP in tenths of a mm; SNOW and
SNWD are in whole mm. The first monthly averages came out as ~323 — i.e. 32.3C.

Decided: convert in stg_observations, so every downstream model gets real units
and none has to REMEMBER to divide by 10 (same "fix it once upstream" reasoning as
the q_flag filter). Implemented with CASE: TMAX/TMIN/PRCP divided by 10.0, other
elements left as is — a blanket /10 would corrupt SNOW/SNWD.
Trap: `value::integer / 10` is integer division in Postgres (323 / 10 = 32, the
decimal is lost). Dividing by 10.0 makes the result numeric (32.3).
After this change, `value` in stg_observations is in C (temperatures) and mm (PRCP).

**int_station_monthly**
TMAX only, 1990–2025. Per station-month: observed days, days_in_month,
missing_days, and tmax_avg (monthly mean, rounded to 2 decimals). month is cast to
date (date_trunc returns a timestamp).
Trap: after adding ::date to month, `GROUP BY 1` grouped by
date_trunc(...)::date while days_in_month used date_trunc(...) without the cast —
Postgres treats those as different expressions and errors ("obs_date must appear
in the GROUP BY clause"). Fixed by grouping on the expression itself,
date_trunc('month', obs_date); both SELECT columns are built from it.

Current-year cutoff: first written as a hard-coded `obs_date < '2026-01-01'`,
which would exclude 2026 forever once 2027 arrives. Replaced with
`obs_date < date_trunc('year', current_date)` — always "before January 1st of the
year the model runs". Verified: fct_station_yearly still 12,012 rows (same result
in 2026, as expected).

**int_station_yearly_validity**
Per station-year: valid_months (COUNT(*) FILTER (WHERE missing_days <= 5)) and the
yearly tmax_avg = AVG of the monthly averages, so every month weighs equally
regardless of its number of days observed.
Put the yearly average here rather than JOINing the two intermediate models in
the mart: both values share the same grain (station + year) and the same GROUP BY,
so one model is simpler. Trade-off: the name now under-describes the model
(int_station_yearly would fit) — rename left open.
The average here also includes invalid months; that's harmless because the mart
drops every year with fewer than 12 valid months.

**fct_station_yearly — first mart**
`SELECT year, station_id, tmax_avg ... WHERE valid_months = 12`. No GROUP BY (input
is already one row per station-year) and no ORDER BY (a view doesn't keep order;
whoever queries sorts).
Result: 12,012 of 17,303 station-years (69.4%) — matches the ~70% pass rate
measured on 2026-10-17, so the dbt implementation reproduces the ad-hoc analysis.

**Tooling notes**
  - The editor's SQL formatter rewrote `{{` as `{ {`, which breaks Jinja. Fix:
    disable format-on-save for .sql, or use a dbt-aware extension.
  - git push failed: GitHub doesn't accept passwords for git operations. Fix: the
    GitHub CLI (`gh auth login`, HTTPS, browser login), which configures git's
    credentials.

## 2026-10-26

**Warming measured as anomalies against a fixed 1991–2020 baseline**
Looked up how the domain measures warming before building. Two standard tools:
  1. Anomaly = a station's yearly value minus its own "normal" (its average over a
     reference period). Needed because stations can't be averaged directly — a
     34C Australian station and a 5C Canadian one would mix climate with location.
     Anomalies put every station on the same scale ("+0.8 = 0.8C warmer than usual
     for that station").
  2. Trend = slope of a straight line through the anomalies, reported in C per
     decade (how NOAA and the IPCC report it). Next step.

Baseline: the fixed WMO standard period 1991–2020, not all available years.
  - Stability: a baseline over "all years" changes every time a new year is
    loaded, silently shifting every anomaly ever computed. A fixed period never
    moves.
  - Comparability: 1991–2020 is the official WMO normal, so results line up with
    published figures.

**A station's normal needs at least 24 of 30 baseline years (WMO 80% rule)**
First measurement without a rule showed normals built from as little as 1 year —
one unusually hot year would become that station's "normal". Adopted the WMO
criterion: data for at least 80% of the years in the period (24 of 30), no extra
consecutive-years criterion. Implemented with HAVING COUNT(*) >= 24 (HAVING, not
WHERE — it filters groups, so it must come after GROUP BY).
Known difference from WMO: WMO builds the annual normal from 12 monthly normals,
not from yearly values. Ours averages complete years only (all 12 months valid),
which gives nearly the same result and is simpler.
Source: WMO Guidelines on the Calculation of Climate Normals (WMO-No. 1203),
sec. 4.4.2.

Result: 244 of 491 stations (50%) have a valid normal.

**Coverage is uneven by country — investigated, accepted, reported per country**
Stations with a valid normal: GM 71, SP 68, FR 40, AS 34, US 24, CA 5, JA 2.
An all-station average would be ~75% Europe, and Japan/Canada have too few
stations for a trustworthy trend.

Investigated where Japan loses its stations before accepting it:
  - The Japanese stations exist in fct_station_yearly but with only 1–21 valid
    baseline years — so the cut happens at the MONTHLY completeness rule; the
    24-year rule only finishes it.
  - Example JA000047412: 1991–2013 months fail by just 6–8 missing days (one such
    month discards the whole year); from Oct 2013 the TMAX record nearly stops
    (1–2 observations per month).
  - Ruled out a pipeline cause: TMAX rows for that station in 2014 = 5 in raw and
    5 in stg_observations. Nothing is lost in loading or staging — NOAA's file is
    thin at the source.

Options considered:
  1. Accept, report trends per country, state the coverage gap openly — CHOSEN.
  2. Relax the rules for thin countries — rejected: breaks the WMO standard just
     adopted and makes countries incomparable.
  3. Rebuild the roster with completeness in mind (selection only checked that
     records start by 1990 and end by 2025, never the gaps between) — deferred:
     means changing the frozen roster and reloading.

**int_station_normals and fct_station_anomalies**
  - int_station_normals: one row per station — normal_temp (rounded to 2 dp),
    baseline_years. 1991–2020, HAVING >= 24. Reads from fct_station_yearly.
  - fct_station_anomalies: one row per station-year — station_id, year, tmax_avg,
    normal_temp, anomaly = tmax_avg - normal_temp. INNER JOIN on station_id only
    (normals have no year; every year of a station uses the same normal). INNER
    because a station without a normal can't have an anomaly. Columns listed
    explicitly instead of fsy.* so an upstream column change can't silently
    alter the mart.
  - Sanity check: mean anomaly over 1991–2020 = -0.0001 — ~0 by construction
    (each station is measured against its own 1991–2020 average); the residue is
    from rounding normals to 2 dp. Confirms the join and the math.

**Tooling notes**
  - Formatter kept rewriting `{{` as `{ {`. Fix: VS Code user settings,
    "[sql]": { "editor.formatOnSave": false }.
  - psql only runs a statement at `;` — typing `q` at a `-#` prompt just adds to
    the unfinished buffer. Clear with `\r`.

## 2026-10-27

**Warming trend = slope of the yearly country anomaly, in C per decade**
Two levels of aggregation, because a slope needs many points:
  1. Per country per year: average anomaly of that country's stations (also the
     series a dashboard will chart).
  2. Per country: regr_slope(avg_anomaly, year) over those ~36 yearly points
     (least-squares straight line), x 10 to turn C/year into C/decade.
Postgres can't nest one aggregate inside another in the same query, so step 1
is a CTE. The year must be a number for regr_slope: EXTRACT(year FROM year).

Why a slope and not a comparison of two years: year-to-year noise is +-1-2C
(Germany: 1996 and 2010 cold, 2014-15 record warm). Picking endpoints gives any
answer you want — 1996 vs 2014 looks like +3.4C, 1990 vs 2013 looks like cooling.
A fitted line uses every year and isn't driven by one extreme.

Result, TMAX 1990–2025 (C per decade): GM +0.56, FR +0.51, SP +0.47, AS +0.38,
US +0.16; CA +0.41 and JA +0.24 shown but not reportable (see below). Germany
+0.56/decade over 3.6 decades is ~+2C since 1990. Europe leading is consistent
with WMO/Copernicus reporting Europe as the fastest-warming continent.
Caveat when presenting: these are daily HIGHS (TMAX); published figures usually
use mean temperature, so they won't match exactly.

**A country's trend is reportable only with >= 10 stations — flagged, not
filtered**
Looked for a domain standard: there isn't one (no WMO-style rule like the 24/30
years). The literature instead says sampling error falls roughly with 1/N, that
spatial coverage matters as much as count (professional datasets grid and
area-weight stations), and that trends are reported with an uncertainty range
rather than a station cutoff.
Chose a simple cutoff anyway: stations with a valid normal are GM 71, SP 68,
FR 40, AS 34, US 24 | CA 5, JA 2 — a large natural gap between 24 and 5. Any
cutoff from 6 to 24 gives the identical result, so the exact value doesn't drive
the outcome; 10 sits clearly inside the gap. Showing an uncertainty range per
slope (the domain's way) is left open.
Flag vs filter: kept all 7 countries with is_reportable instead of dropping CA
and JA. Filtering would make them silently disappear; the flag lets the
dashboard state "Japan: insufficient data (2 stations)" — which is what the
2026-10-26 decision ("state the coverage gap openly") requires. It also keeps
the threshold changeable without losing rows.

**fct_country_trends (mart)**
One row per country: slope_c_per_decade, avg_stations (average per year), years,
station_dist_count, is_reportable.
  - CTE country_year: country + year -> avg anomaly (the slope input).
  - CTE stations_per_country: country -> COUNT(DISTINCT station_id). Needed as a
    separate CTE because country_year is already split by year, so it can't count
    stations across years; DISTINCT so a station isn't counted once per year.
  - JOIN on country; station_dist_count goes into the GROUP BY (one value per
    country, but Postgres still requires it).
Verified: slopes match the ad-hoc query; station counts match int_station_normals.

**Metrics live in dbt, not in the BI tool**
Tableau could compute slopes itself. Kept the logic in dbt: (1) one source of
truth — the slope and the >= 10 rule are definitions, versioned and reviewable in
Git, not hidden in a workbook that can't be diffed; (2) every consumer gets the
same numbers; (3) the dashboard stays a thin display layer. Tableau's own trend
line is fine as a visual; the reported numbers come from the model.

**Materialization: int_station_monthly as a table**
Querying the marts had become slow enough to look hung: every model was a view,
so each query recomputed the whole chain from ~26M staging rows.
View = stored query, computed at every read (always fresh, slow). Table = result
computed once at `dbt run` and stored (fast reads, a snapshot until the next
run). Snapshot is fine here: the pipeline already loads then rebuilds.
Only one model needed to change: int_station_monthly is where 26M rows collapse
to ~200k (about 130x). As a table, everything downstream starts from ~200k ready
rows. Set with {{ config(materialized='table') }} at the top of the model.
Result: SELECT * FROM fct_country_trends went to 0.64 s. The rest stays views.
Refresh is then an orchestration concern: ingestion -> dbt run -> dbt test, in
that order (Airflow later), so tables are never rebuilt from a half-loaded raw.

**Dashboard plan: three charts, three messages**
Decided what a viewer should understand in 30 seconds before opening Tableau:
  1. "All countries are warming" — line chart: year vs average anomaly, one line
     per country.
  2. "Which country warms fastest" — bar chart of slope_c_per_decade.
  3. "Where data is missing" — CA and JA shown greyed with "insufficient
     stations" (from is_reportable).
Started with chart 1.

**fct_country_yearly_anomalies — the country-year series as its own model**
The line chart needs one row per country + year. That data existed only as a
CTE inside fct_country_trends, and a CTE can't be exported.
Rejected exporting fct_station_anomalies and letting Tableau average it: the
chart's numbers would then be defined in Tableau while the slopes come from dbt
— two definitions of the same data that can drift apart (Tableau also defaults
to SUM, not AVG). Same principle as "metrics live in dbt".
Done: the CTE became fct_country_yearly_anomalies (country, year as integer,
avg_anomaly, station_count). fct_country_trends now reads from it instead of
keeping its own copy:
  fct_station_anomalies -> fct_country_yearly_anomalies -> fct_country_trends
avg_anomaly is NOT rounded here, because the slope is computed from it
(rounding before a calculation is the open "rounding too early" issue); the
dashboard rounds for display. Year cast ::integer so Tableau doesn't show
"2,016.00". Verified: slopes after the refactor are identical to before.

**CSV export for Tableau, kept out of Git**
Tableau Public can't connect to the local Postgres, so the marts go in as CSV:
  \copy (SELECT * FROM analytics.fct_country_yearly_anomalies)
    TO 'dashboard/data/country_yearly_anomalies.csv' WITH CSV HEADER
\copy writes on the client machine; the path is relative to where psql started
(run from the repo root). Files go to a dedicated dashboard/data/ folder.
dashboard/data/ is in .gitignore: the CSVs are generated and recreatable with one
command, so Git keeps the code that makes them (dbt models + export command), not
the outputs — generated files go stale and clutter history.
Loaded into Tableau Public: 245 rows (5 countries x 36 years + CA 35 + JA 30).

**Country codes are FIPS, not ISO — real names needed before charting**
Tableau auto-assigned the country column a geographic role, assuming ISO codes.
GHCN uses FIPS codes, which differ: in ISO, AS = American Samoa (not
Australia), GM = Gambia (not Germany), and JA / SP aren't valid codes at all. Left
as is, any map would place "Germany" in Africa.
Decided to fix it in the data, not patch it in Tableau (switching the role off
would only hide the problem for this one workbook).
Source: NOAA's ghcnd-countries.txt in the same bucket — "AS Australia": code in
the first 2 characters, a space, then the name. Some names have trailing spaces
(need strip) and some contain commas ("Bahamas, The").
Options: (1) ingest it like ghcnd-stations.txt (Python download -> raw table ->
stg_countries); (2) a dbt seed (small CSV in the repo, loaded by `dbt seed`,
could also carry ISO codes). CHOSE (1): same pattern as stations, and the names
come from NOAA's own file rather than a hand-maintained one.

---

## Open / undecided (current)

**Data quality / cleaning**
  - q_flag: DONE 2026-10-11 — flagged values dropped in stg_observations.
  - Missing-value sentinels: DONE 2026-10-17 — verified none exist.
  - Implausible values: DONE 2026-10-17 — no custom filter; NOAA QC covers it.
  - Completeness: DONE 2026-10-25 — WMO month rule implemented
    (int_station_monthly -> int_station_yearly_validity -> fct_station_yearly).
  - Rounding: monthly averages are rounded to 2 decimals before the yearly
    average. Tiny effect, but cleaner to round only in the final output.
  - WMO "no more than 3 CONSECUTIVE missing days" — the other half of the 3/5 rule.
    Deferred: needs gap detection (runs of missing dates). Add after measuring the
    simpler rule in practice.
  - PRCP completeness: precipitation TOTALS allow NO missing days (a missing day
    may be a missing storm). Needs its own rule — the TMAX rule doesn't transfer.
  - 2005 anomaly: only 421 station-years have TMAX in 2005 vs ~485 around it
    (~60 stations missing the entire year). Investigate.
  - Elements beyond TMAX/PRCP are present; marts must select explicitly.

- Change-detection skip strategy (file-level hash vs. always-pull window;
  Last-Modified already noted as weak).
- Trailing-window incremental load (re-pull ~90 days + upsert) now that backfill
  is done.
- Switch print -> logging in run_observations_pipeline (prod-grade: timestamps,
  levels, log-to-file; partly handled by Airflow later).
- Guard: download_station_inventory can return None on a failed fetch;
  select_stations would then crash on "for line in lines". Add a guard.
- Materialization: int_station_monthly is a table since 2026-10-27; the rest are
  views. Revisit if marts get slow again (e.g. marts as tables for the dashboard).
- dbt test to catch roster/data gaps loudly (e.g. no station marked success in the
  manifest with zero rows). Must run AFTER the observations load, or a legitimately
  new station would false-alarm.
- Rename int_station_yearly_validity -> int_station_yearly (it now also holds the
  yearly average).
- BI / dashboard layer. Options: Metabase (local, Docker, connects to Postgres
  directly — not shareable); Tableau Public (public link, but no live connection to
  local Postgres — needs a CSV export of the mart); Evidence (SQL + Markdown in the
  repo, deployable to a public link). Power BI Desktop ruled out: Windows only.
  Key question: does the portfolio need a public link, or are README screenshots
  enough?
  UPDATED 2026-10-27: Tableau Public (installed; chart 1 data loaded) — runs on Mac, gives a public link a
  reviewer can open, common in job postings, already studied it. Data goes in as
  a CSV export of the marts (no direct database connection). A paid
  certification judged unnecessary for a Data Engineer target; the dashboard on
  top of the dbt marts is the stronger evidence.
- Layering: int_station_normals reads from a mart (fct_station_yearly). dbt
  convention is that intermediate models don't depend on marts. Revisit (e.g.
  move the valid-year filter into an intermediate model both can use).
- Uncertainty per trend (standard error / confidence range of the slope) — the
  domain's way to show reliability; complements the >= 10 cutoff.
- Country-year averages use whichever stations are valid that year, so the
  station set varies slightly year to year. Anomalies limit the effect; check
  whether a fixed station set changes the slopes.
- Roster rebuild that checks completeness, not just start/end years (option 3 of
  2026-10-26) — deferred.
- Countries ingestion: load all countries or only the 7 in the roster — undecided.
- NEXT: ingest ghcnd-countries.txt (parse code [0:2] + name, strip) -> raw table
  -> stg_countries -> join country names into the marts -> re-export CSVs ->
  Tableau chart 1 (line chart); then charts 2 and 3; then PRCP.

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
- Missing-value sentinels checked (none) and plausibility filter rejected (NOAA QC
  suffices) — DONE (2026-10-17).
- Completeness rule decided: month valid if <=5 days missing, year needs all 12
  valid months, current year excluded — DECIDED (2026-10-17); implemented as
  first mart (2026-10-25).
- Unit conversion (tenths -> C / mm) in staging — DONE (2026-10-25).
- Current-year cutoff made dynamic (date_trunc('year', current_date)) instead of
  hard-coded — DONE (2026-10-25).
- Station normals (1991–2020, WMO >= 24 of 30 years) — DONE (2026-10-26),
  244 stations.
- Anomalies mart fct_station_anomalies — DONE (2026-10-26), mean ~0 over baseline.
- Country coverage gap investigated: source data, not pipeline; decided to report
  per country — DONE (2026-10-26).
- Warming trend mart fct_country_trends (C/decade per country) — DONE (2026-10-27).
- Minimum stations per country: >= 10, flagged via is_reportable — DECIDED
  (2026-10-27).
- int_station_monthly materialized as a table; marts queries ~0.6 s — DONE
  (2026-10-27).
- Country-year series split into fct_country_yearly_anomalies; fct_country_trends
  reads from it — DONE (2026-10-27).
- Dashboard tool: Tableau Public; CSV export to dashboard/data/ (gitignored) —
  DONE (2026-10-27).
- First mart fct_station_yearly built via two intermediate models; 12,012 valid
  station-years (69.4%) — DONE (2026-10-25).