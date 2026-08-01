# Decisions

## 2026-07-24

**Python 3.11.9, not 3.12**
Airflow lags behind the newest Python. Pinned with pyenv local so only
this folder uses it.

**Postgres, not Snowflake**
Free and never expires. A trial account would kill the project in 30 days.

**data/ is gitignored**
Raw files are re-downloadable. Repos should hold code, not data.

**Forced IPv4 in fetch_observations.py**
requests hung forever on NOAA. curl worked. getaddrinfo showed IPv6
addresses listed first — Python tried them and stalled, curl fell back
to IPv4 automatically. Fixed by setting allowed_gai_family to AF_INET.

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