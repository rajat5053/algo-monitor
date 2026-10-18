
import requests

BASE_URL = "https://api.india.delta.exchange/v2/products"

contract_types = [
    "perpetual_futures",
    "futures",
    "call_options",
    "put_options",
]

for contract_type in contract_types:
    params = {
        "contract_types": contract_type,
        "states": "live",
        "page_size": 100,
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        products = payload.get("result", [])

        print(f"\n{contract_type}: {len(products)} products")
        for product in products[:5]:
            print(
                " ",
                product.get("symbol"),
                "|",
                product.get("state"),
                "|",
                product.get("description"),
            )

        meta = payload.get("meta", {})
        if meta.get("after"):
            print("More pages available; pagination is required.")

    except requests.RequestException as exc:
        print(f"\n{contract_type}: request failed: {exc}")
