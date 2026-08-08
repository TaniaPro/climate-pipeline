import requests
import gzip

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

