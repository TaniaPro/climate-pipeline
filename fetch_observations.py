import requests
import socket
import urllib3.util.connection

# NOAA advertises IPv6 addresses that hang on this network — force IPv4
urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

def download_station(station_id):
    url = f"https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/{station_id}.csv"
    response = requests.get(url, timeout=30)

    if response.status_code==200:
        with open(f"data/raw/{station_id}.csv", "w") as file:
            file.write(response.text)
        return True
    else:
        print(f"Failed: status {response.status_code}")
        return False


def download_station_inventory():
    # Station ID is chars 0-10; its first 2 chars double as the FIPS country code.
    url = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-inventory.txt"
    response = requests.get(url, timeout=30)

    if response.status_code == 200:
        with open("data/raw/ghcnd-inventory.txt", "w") as file:
            file.write(response.text)

        return response.text.splitlines()

    else:
        print(f"Failed: status {response.status_code}")
        return None


lines = download_station_inventory()

# FIPS country codes: data-rich countries across 4 continents (North America,
# Asia, Oceania, Europe), chosen for strong warming signal and long records.
fips_country_code = ["US", "JA", "AS", "CA", "GM", "SP", "FR"]
firstyear=1990
lastyear=2025


station_ids=[]
tmax_ok=set()
prcp_ok=set()


for line in lines:
    # ghcnd-inventory.txt is fixed-width: [0:11] station id, [31:35] element
    # (TMAX/PRCP/...), [36:40] record first year, [41:45] record last year.
    # Keep only stations with unbroken coverage across the whole target range
    # (record start <= firstyear and record end >= lastyear).
    if (line[:2] in fips_country_code
            and int(line[36:40]) <= firstyear
            and int(line[41:45]) >= lastyear):
        if line[31:35].strip() == "TMAX":
            tmax_ok.add(line[:11])
        elif line[31:35].strip() == "PRCP":
            prcp_ok.add(line[:11])


tmax_and_prcp = tmax_ok & prcp_ok
tmax_and_prcp_cap=[]
per_country = {}

for station in tmax_and_prcp:
    country=station[:2]
    if country not in per_country:
        per_country[country]=1
    else:
        per_country[country]+=1
    # Cap (limit) per country so no single country dominates the dataset
    if per_country[country]<=75:
        tmax_and_prcp_cap.append(station)


# Verification
from collections import Counter
print(len(tmax_and_prcp_cap))
print(Counter(s[:2] for s in tmax_and_prcp_cap))


# Disabled until the station selection above is finalized — uncomment to
# actually fetch the capped station list.
#for station_id in tmax_and_prcp_cap:
#    download_station(station_id)