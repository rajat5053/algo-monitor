
import os
from dotenv import load_dotenv
import requests

load_dotenv()  # Reads variables from .env file into os.environ

token = os.getenv("UPSTOX_ACCESS_TOKEN")


if not token:
    raise SystemExit("Missing UPSTOX_ACCESS_TOKEN environment variable.")

url = "https://api.upstox.com/v3/market-quote/ltp"

response = requests.get(
    url,
    params={"instrument_key": "NSE_INDEX|Nifty 50"},
    headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    },
    timeout=15,
)

print("HTTP status:", response.status_code)

if response.ok:
    data = response.json()
    print("API response:")
    print(data)
else:
    print("Request failed. Check the status and error message.")
    print(response.text[:1000])
