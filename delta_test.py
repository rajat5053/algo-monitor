
import requests

url = "https://api.india.delta.exchange/v2/products"

params = {
    "contract_types": "spot",
    "states": "live",
    "page_size": 100,
}

try:
    response = requests.get(url, params=params, timeout=20)
    print("HTTP status:", response.status_code)
    response.raise_for_status()

    payload = response.json()
    products = payload.get("result", [])

    print("API success:", payload.get("success"))
    print("Products returned:", len(products))

    for product in products[:15]:
        print(
            product.get("symbol"),
            "|",
            product.get("contract_type"),
            "|",
            product.get("state"),
        )

except requests.RequestException as exc:
    print("Request failed:", exc)


