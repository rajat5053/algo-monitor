
import requests

BASE_URL = "https://api.india.delta.exchange/v2/products"

contract_types = [
    "spot",
    "perpetual_futures",
    "call_options",
    "put_options",
]

for contract_type in contract_types:
    print(f"\n{'=' * 50}")
    print(f"Contract type: {contract_type}")

    all_products = []
    cursor = None

    while True:
        params = {
            "contract_types": contract_type,
            "states": "live",
            "page_size": 100,
        }

        if cursor:
            params["after"] = cursor

        response = requests.get(
            BASE_URL,
            params=params,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()

        if not payload.get("success"):
            print("API returned an unsuccessful response:", payload)
            break

        products = payload.get("result", [])
        all_products.extend(products)

        meta = payload.get("meta") or {}
        next_cursor = meta.get("after")

        print(
            f"Fetched {len(products)} products; "
            f"total so far: {len(all_products)}"
        )

        if not next_cursor or not products:
            break

        cursor = next_cursor

    print(f"TOTAL {contract_type}: {len(all_products)}")

    # Show a few examples
    for product in all_products[:10]:
        print(
            product.get("symbol"),
            "|",
            product.get("contract_type"),
            "|",
            product.get("underlying_asset", {}).get("symbol")
            if isinstance(product.get("underlying_asset"), dict)
            else product.get("underlying_asset"),
        )
