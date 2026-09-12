import requests
import gzip
import psycopg2
import io
from psycopg2.extras import execute_values
from fetch_observations import select_stations


# step 1: fetches station metadata lines (location + name for every station)
def download_station_meta_data():
    # ghcnd-stations.txt is the station master list — one row per station
    # (NOT per element, unlike the inventory). Fixed-width:
    #   [0:11]  station id (first 2 chars = FIPS country code)
    #   [12:20] latitude
    #   [21:30] longitude
    #   [31:37] elevation (metres; -999.9 = missing)
    #   [38:40] state (2-char, mostly US/CA; often blank)
    #   [41:71] station name
    # Loaded into raw.stations. Provides the location/name facts that are the
    # same on every observation row, so they live here once, keyed by station id.
    url = "https://noaa-ghcn-pds.s3.amazonaws.com/ghcnd-stations.txt"
    response = requests.get(url, timeout=30)

    if response.status_code == 200:
        return response.text.splitlines()
    else:
        print(f"Failed: status {response.status_code}")
        return None


# step 2: keep only the selected 491 stations, slice each fixed-width line into
# fields, and build one clean (stripped) row per station.
def parse_stations_meta_data():
    # set() for O(1) membership checks — this runs against ~127k metadata lines.
    selected_stations = set(select_stations())
    lines = download_station_meta_data()

    rows = []
    for line in lines:
        # filter: keep the line only if this station is one of our 491.
        if line[0:11] in selected_stations:
            # slice by fixed-width position, strip padding spaces.
            station_id = line[0:11].strip()
            latitude = line[12:20].strip()
            longitude = line[21:30].strip()
            elevation = line[31:37].strip()
            state = line[38:40].strip()
            name = line[41:71].strip()
            rows.append((station_id, latitude, longitude, elevation, state, name))
    return rows


# step 3: upsert the station rows into raw.stations. New stations insert;
# existing ones (same station_id primary key) update in place — idempotent.
def load_station_metadata(rows):
    conn = psycopg2.connect(dbname="climate")
    cursor = conn.cursor()

    # execute_values inserts all rows in one statement (not 491 separate INSERTs).
    # ON CONFLICT (station_id) makes a re-run update instead of erroring on the
    # duplicate primary key. loaded_at is omitted — it auto-fills (DEFAULT now()).
    execute_values(cursor, """
        INSERT INTO raw.stations
            (station_id, latitude, longitude, elevation, state, name)
        VALUES %s
        ON CONFLICT (station_id) DO UPDATE SET
            latitude  = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            elevation = EXCLUDED.elevation,
            state     = EXCLUDED.state,
            name      = EXCLUDED.name
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()