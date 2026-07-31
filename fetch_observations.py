import requests
import socket
import urllib3.util.connection

# NOAA advertises IPv6 addresses that hang on this network — force IPv4
urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

def download_station(station_id):
    # build the url using station_id
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
    



stations = ["ACW00011604", "AF000040930", "AGE00147704"]

for station in stations:
    download_station(station)