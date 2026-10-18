"""
Test all FastAPI endpoints in Algo Monitor to ensure complete compatibility
with both the Quant Terminal preview UI expectations and legacy dashboard clients.
"""
from fastapi.testclient import TestClient
from algo_monitor.dashboard.app import create_app
from algo_monitor.database import get_database
from algo_monitor.config.settings import get_settings

def test_endpoints():
    settings = get_settings()
    db = get_database(settings.database_path)
    app = create_app(db)
    client = TestClient(app)

    print("--- 1. Testing HTML Shells ---")
    r = client.get("/")
    assert r.status_code == 200, f"Root / failed: {r.status_code}"
    assert "bundle.js" in r.text, "bundle.js missing in index.html"
    assert "style.css" in r.text, "style.css missing in index.html"
    print("[OK] / returns 200 with modern quant terminal shell")

    r_leg = client.get("/legacy")
    assert r_leg.status_code == 200, f"/legacy failed: {r_leg.status_code}"
    print("[OK] /legacy returns 200 with preserved legacy dashboard")

    print("\n--- 2. Testing Global Header & Telemetry Endpoints ---")
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data and "version" in data
    print("[OK] /api/status OK:", list(data.keys()))

    r = client.get("/api/market-toggle")
    assert r.status_code == 200
    data = r.json()
    assert "indian" in data and "crypto" in data
    print("[OK] GET /api/market-toggle OK:", data)

    r = client.post("/api/market-toggle", json={"indian": True, "crypto": True})
    assert r.status_code == 200
    print("[OK] POST /api/market-toggle OK:", r.json())

    r = client.get("/api/upstox/auth-status")
    assert r.status_code == 200
    data = r.json()
    assert "valid" in data or "has_active_token" in data
    print("[OK] /api/upstox/auth-status OK:", {k: data[k] for k in ["valid", "has_active_token", "status"] if k in data})

    r = client.get("/api/alerts")
    assert r.status_code == 200
    data = r.json()
    assert "alerts" in data
    print(f"[OK] /api/alerts OK: {len(data['alerts'])} alerts")

    print("\n--- 3. Testing Overview Tab Endpoints ---")
    r = client.get("/api/balance")
    assert r.status_code == 200
    data = r.json()
    assert "equity" in data and "available" in data and "daily_loss_used" in data
    print("[OK] /api/balance OK:", {k: data[k] for k in ["equity", "available", "daily_loss_limit"]})

    r = client.get("/api/scan-results")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    print(f"[OK] /api/scan-results OK: {len(data['results'])} scans")

    r = client.get("/api/zones?symbol=NIFTY50")
    assert r.status_code == 200
    data = r.json()
    assert "zones" in data
    print(f"[OK] /api/zones OK: {len(data['zones'])} zones")

    r = client.get("/api/signals")
    assert r.status_code == 200
    data = r.json()
    assert "signals" in data
    print(f"[OK] /api/signals OK: {len(data['signals'])} signals")

    print("\n--- 4. Testing Indian Market Endpoints ---")
    r = client.get("/api/indian/indices")
    assert r.status_code == 200
    data = r.json()
    assert "indices" in data or "items" in data
    print(f"[OK] /api/indian/indices OK: count = {len(data.get('items', data.get('indices', [])))}")

    r = client.get("/api/indian/fno-securities?index=ALL")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data or "securities" in data
    print(f"[OK] /api/indian/fno-securities OK: count = {len(data.get('items', data.get('securities', [])))}")

    r = client.get("/api/indian/index-constituents?index=NIFTY50")
    assert r.status_code == 200
    data = r.json()
    assert "constituents" in data
    print(f"[OK] /api/indian/index-constituents (NIFTY50) OK: {len(data['constituents'])} stocks")

    print("\n--- 5. Testing Crypto Market Endpoints ---")
    r = client.get("/api/crypto/market")
    assert r.status_code == 200
    data = r.json()
    assert "perpetuals" in data or "markets" in data
    print(f"[OK] /api/crypto/market OK: {len(data.get('perpetuals', data.get('markets', [])))} items")

    r = client.get("/api/crypto/futures-movers")
    assert r.status_code == 200
    data = r.json()
    assert "gainers" in data and "losers" in data
    print(f"[OK] /api/crypto/futures-movers OK: {len(data['gainers'])} gainers, {len(data['losers'])} losers")

    r = client.get("/api/crypto/options?symbol=BTC")
    assert r.status_code == 200
    data = r.json()
    assert "decks" in data or "strikes" in data
    print(f"[OK] /api/crypto/options (BTC) OK: count={len(data.get('decks', data.get('strikes', [])))}")

    print("\n--- 6. Testing Option Chain Endpoints ---")
    r = client.get("/api/indian/option-chain/NIFTY50")
    assert r.status_code == 200
    data = r.json()
    assert "strikes" in data and "spot" in data
    print(f"[OK] /api/indian/option-chain/NIFTY50 OK: spot={data.get('spot')}, strikes={len(data.get('strikes', []))}")

    print("\n--- 7. Testing Positions & Orders Endpoints ---")
    r = client.get("/api/positions")
    assert r.status_code == 200
    data = r.json()
    assert "open" in data and "closed" in data
    print(f"[OK] /api/positions OK: open={len(data['open'])}, closed={len(data['closed'])}")

    print("\n--- 8. Testing Performance & Settings Endpoints ---")
    r = client.get("/api/performance")
    assert r.status_code == 200
    data = r.json()
    assert "equity_curve" in data and "all" in data
    print("[OK] /api/performance OK: all keys =", list(data.get("all", {}).keys()))

    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "starting_balance" in data and "options" in data
    print(f"[OK] /api/config OK: starting_balance={data['starting_balance']}, options enabled={data['options']['enabled']}")

    print("\n--- 9. Testing Candles / Chart Endpoints ---")
    r = client.get("/api/candles/NIFTY50")
    assert r.status_code == 200
    data = r.json()
    assert "candles" in data
    if data["candles"]:
        first_candle = data["candles"][0]
        assert isinstance(first_candle["time"], (int, float)), f"Expected integer timestamp, got {type(first_candle['time'])}"
        print(f"[OK] /api/candles/NIFTY50 OK: {len(data['candles'])} candles, sample candle time={first_candle['time']} (int/float)")
    else:
        print("[OK] /api/candles/NIFTY50 OK (0 candles in DB)")

    print("\n=======================================================")
    print("ALL QUANT TERMINAL & BACKEND ENDPOINTS PASSED 100%!")
    print("=======================================================")

if __name__ == "__main__":
    test_endpoints()
