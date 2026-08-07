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

## Open / undecided (next session)

- **Change-detection**: whether to check S3 Last-Modified/ETag (or content
  hash) to skip unchanged station files, or just always pull the trailing
  window and let upsert absorb it. Trade: cheap skip vs. simpler always-pull.
- **Code structure / placement**: where manifest read/write, backfill-vs-
  incremental decision, and fetching live. Leaning toward splitting the current
  fetch script into fetcher / db(loader) / orchestration rather than one script
  doing everything — but needs a look at current repo layout to finalize.
