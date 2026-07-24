import requests
import socket
import urllib3.util.connection

# NOAA advertises IPv6 addresses that hang on this network — force IPv4
urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

url = "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/ACW00011604.csv"

r = requests.get(url, timeout=30)

print(r.status_code)