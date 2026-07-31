import requests
import socket
import urllib3.util.connection

# NOAA advertises IPv6 addresses that hang on this network — force IPv4
urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

def download_station(station_id):
    # Fetches one station's daily CSV from NOAA and saves it to data/raw/.
    # Returns True on success, False on any HTTP error.
    url = f"https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/{station_id}.csv"

    # response = what the server sent back. Inspect it with dir(response).
    # Useful attributes:
    #   status_code -> number, 200 means OK
    #   text        -> body as text (the CSV)
    #   content     -> body as raw bytes
    #   headers     -> server info (type, size, date)
    #   url         -> the address fetched
    #   ok          -> True if status under 400
    #   encoding    -> text encoding, e.g. utf-8
    response = requests.get(url, timeout=30)

    if response.status_code==200:
        with open(f"data/raw/{station_id}.csv", "w") as file:
            file.write(response.text)
        return True
    else:
        print(f"Failed: status {response.status_code}")
        return False
    
def download_stationids():
    # Downloads the GHCN-D station inventory (fixed-width text) and returns it as a list of lines.
    # Each line's columns: 0-1 = FIPS country code, 0-10 = 11-char station ID.
    url = "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/doc/ghcnd-stations.txt"
    response = requests.get(url, timeout=30)

    if response.status_code == 200:
        with open("data/raw/ghcnd-stations.txt", "w") as file:
            file.write(response.text)

        return response.text.splitlines()

    else:
        print(f"Failed: status {response.status_code}")
        return None


lines = download_stationids()

# FIPS country codes selected for the project: European and Mediterranean
# countries with strong recent heat anomalies and long station records.
fips_country_code = ["SP", "PO", "FR", "IT", "GM", "UK", "GR", "IS"]


station_ids=[]

for line in lines:
    if  line[:2] in fips_country_code:
        station_ids.append(line[:11])  # cols 0-10 are the station ID in the fixed-width format


# Uncomment to run the actual downloads (slow — one HTTP request per station).
# for station_id in station_ids:
#     download_station(station_id)
