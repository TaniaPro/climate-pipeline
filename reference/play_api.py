import requests
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()
print("DB_URL =", os.environ["DB_URL"])


url = "https://api.coingecko.com/api/v3/coins/markets"
params = {
    "vs_currency": "usd",
    "order": "market_cap_desc",
    "per_page": 5,
    "page": 1,
    "sparkline": "false",
}

response = requests.get(url, params=params, timeout=30)
response.raise_for_status()

data = response.json()

print(type(data))
print(len(data))
print(data[0]["id"], data[0]["current_price"])

engine = create_engine(os.environ["DB_URL"])

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1")).scalar()

print("DB OK:", result)

from datetime import datetime, timezone
import json
snapshot_ts = datetime.now(timezone.utc)
endpoint = "/coins/markets"

with engine.begin() as conn:
    conn.execute(
        text("""
            INSERT INTO raw.market_snapshots
            (snapshot_ts, endpoint, params, payload)
            VALUES (:snapshot_ts, :endpoint, :params, :payload)
        """),
        {
            "snapshot_ts": snapshot_ts,
            "endpoint": endpoint,
            "params": json.dumps(params),
            "payload": json.dumps(data),
        }
    )

print("Inserted snapshot with", len(data), "coins")

