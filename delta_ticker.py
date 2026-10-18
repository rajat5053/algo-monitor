
import requests

BASE_URL = "https://api.india.delta.exchange/v2/tickers"

symbols = [
    "BTC_INR",
    "ETH_INR",
    "SOL_INR",
    "XRP_INR",
]

for symbol in symbols:
    print(f"\n{'=' * 40}")
    print(f"Checking: {symbol}")

    try:
        response = requests.get(
            f"{BASE_URL}/{symbol}",
            headers={"Accept": "application/json"},
            timeout=15,
        )

        print("HTTP status:", response.status_code)
        response.raise_for_status()

        payload = response.json()

        if not payload.get("success"):
            print("API returned an unsuccessful response:", payload)
            continue

        ticker = payload.get("result", {})
        print("Symbol:", ticker.get("symbol", symbol))
        print("Last price:", ticker.get("close"))
        print("Mark price:", ticker.get("mark_price"))
        print("24h volume:", ticker.get("volume"))
        print("24h high:", ticker.get("high"))
        print("24h low:", ticker.get("low"))

    except requests.RequestException as exc:
        print("Request failed:", exc)
    except ValueError as exc:
        print("Could not parse JSON:", exc)
