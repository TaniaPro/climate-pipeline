import requests
import psycopg2
from psycopg2.extras import execute_values

# step 1: fetches countries metadata lines (FIPS + country name)
def download_countries_meta_data():
    #   [0:2]   country code (first 2 chars = FIPS country code)
    #   [3:]    country name
    url = "https://noaa-ghcn-pds.s3.amazonaws.com/ghcnd-countries.txt"
    response = requests.get(url, timeout=30)

    if response.status_code == 200:
        return response.text.splitlines()
    else:
        print(f"Failed: status {response.status_code}")
        return None

# step 2: slice each fixed-width line into fields, and build one clean (stripped) row per country.
def parse_countries_meta_data():
    
    lines = download_countries_meta_data()

    rows = []
    for line in lines:
        if line:
            fips_code = line[0:2].strip()
            country_name = line[3:].strip()
            rows.append((fips_code, country_name))
    return rows

# step 3: upsert the countries rows into raw.countries. New countries insert;
# existing ones (same fips_code primary key) update in place — idempotent.
def load_countries_metadata(rows):
    conn = psycopg2.connect(dbname="climate")
    cursor = conn.cursor()

    # execute_values inserts all rows in one statement.
    # ON CONFLICT (fips_code) makes a re-run update instead of erroring on the duplicate primary key. 
    execute_values(cursor, """
        INSERT INTO raw.countries
            (fips_code, country_name)
        VALUES %s
        ON CONFLICT (fips_code) DO UPDATE SET
            country_name  = EXCLUDED.country_name
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()