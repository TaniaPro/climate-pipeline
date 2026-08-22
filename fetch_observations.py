import requests
import gzip
import psycopg2
import io

# step 1: fetches inventory lines (all stations' coverage)
def download_station_inventory():
    # ghcnd-inventory.txt lists which elements each station records and the
    # year range of coverage. One row per station PER element, fixed-width:
    #   [0:11]  station id (first 2 chars = FIPS country code)
    #   [12:20] latitude
    #   [21:30] longitude
    #   [31:35] element (TMAX, PRCP, ...)
    #   [36:40] first year of record
    #   [41:45] last year of record
    # Used to select stations (e.g. those with both TMAX and PRCP over a
    # target year range) — not the observation data itself.
    url = "https://noaa-ghcn-pds.s3.amazonaws.com/ghcnd-inventory.txt"
    response = requests.get(url, timeout=30)

    if response.status_code == 200:
        return response.text.splitlines()
    else:
        print(f"Failed: status {response.status_code}")
        return None

# step 2: filters those lines to selected station IDs
def select_stations():
    # FIPS country codes: data-rich countries across 4 continents (North America,
    # Asia, Oceania, Europe), chosen for strong warming signal and long records.
    fips_country_code = ["US", "JA", "AS", "CA", "GM", "SP", "FR"]

    # parameters
    firstyear = 1990
    lastyear = 2025
    tmax_ok = set()
    prcp_ok = set()

    lines = download_station_inventory()
    
    for line in lines:
        # ghcnd-inventory.txt is fixed-width: [0:11] station id, [31:35] element
        # (TMAX/PRCP/...), [36:40] record first year, [41:45] record last year.
        fip = line[:2]
        if fip in fips_country_code and int(line[36:40]) <= firstyear and int(line[41:45]) >= lastyear:
            element = line[31:35].strip() # check for TMAX or PRCP
            if element == 'TMAX':
                tmax_ok.add(line[:11])
            elif element == "PRCP":
                prcp_ok.add(line[:11])

    # find stations that have both TMAX and PRCP
    both = tmax_ok & prcp_ok

    station_ids = []
    per_country = {} # count stations per country

    for station in both:
        country = station[:2]

        # First station seen:
        count = per_country.get(country, 0) # country not in dict → returns 0
        if count < 75: # threshold for evenly distributed data
            station_ids.append(station)
            per_country[country] = count + 1

    return station_ids

# step 3: fetches relevant station's observation text
# The output of this function is one giant string, e.g. "ACW00011604,19490101,TMAX,289,,,X,\nACW00011604,19490101,PRCP,0,,,X,\n..."
def download_station(station_id):
    # Fetches one station's full observation history from the NOAA GHCN-D
    # public S3 bucket (csv.gz/by_station/). The file is gzip-compressed and
    # has no header; each row is one station/date/element/value with M/Q/S
    # flags and obs-time. Decompressed in memory and returned as text, not
    # saved to disk.
    url = f"https://noaa-ghcn-pds.s3.amazonaws.com/csv.gz/by_station/{station_id}.csv.gz"
    response = requests.get(url, timeout=30)

    if response.status_code == 200:
        text = gzip.decompress(response.content).decode()
        return text
    else:
        print(f"Failed: status {response.status_code}")
        return None

# step 4: stamp each observation line with its source file (the station id)
def parse_station(text, station_id):
    # Appends source_file (the station id) to every line so COPY can load it
    # into raw.observations. Output stays CSV text — COPY splits the fields;
    # this only adds provenance. Example:
    #   ACW00011604,19490101,TMAX,289,,,X,   ->
    #   ACW00011604,19490101,TMAX,289,,,X,,ACW00011604
    result_lines = []
    for line in text.splitlines():   # split the text blob into individual lines
        if line:                     # skip blank lines (e.g. trailing newline)
            result_lines.append(line + "," + station_id)
    return "\n".join(result_lines)   # rejoin into one CSV text block


# step 5: bulk-load one station's parsed text into raw.observations via COPY
def load_station(text):
    conn = psycopg2.connect(dbname="climate")   # open a connection to the database
    cursor = conn.cursor()                      # get a cursor to run commands on it

    sql = """
        COPY raw.observations
            (station_id, obs_date, element, value,
             m_flag, q_flag, s_flag, obs_time, source_file)
        FROM STDIN WITH (FORMAT csv)
    """
    cursor.copy_expert(sql, io.StringIO(text)) # query execution

    conn.commit()   # save (commit is on the connection)
    cursor.close()  # done with the cursor
    conn.close()    # close connection

