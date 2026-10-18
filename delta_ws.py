
import json
import threading
from datetime import datetime

import websocket

WS_URL = "wss://public-socket.india.delta.exchange"
SYMBOLS = ["BTC_INR", "ETH_INR", "SOL_INR", "XRP_INR"]

message_count = 0
stop_timer = None


def on_open(ws):
    print("Connected to Delta Exchange WebSocket.")
    print("Subscribing to:", ", ".join(SYMBOLS))

    # Keep the connection alive and detect connection problems.
    ws.send(json.dumps({"type": "enable_heartbeat"}))

    # Subscribe to ticker updates.
    subscription = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {
                    "name": "ticker",
                    "symbols": SYMBOLS,
                }
            ]
        },
    }

    ws.send(json.dumps(subscription))
    print("Subscription request sent.")
    print("Listening for 60 seconds...\n")


def on_message(ws, message):
    global message_count

    message_count += 1
    timestamp = datetime.now().strftime("%H:%M:%S")

    try:
        data = json.loads(message)
        print(f"[{timestamp}] {json.dumps(data, ensure_ascii=False)}")
    except json.JSONDecodeError:
        print(f"[{timestamp}] {message}")


def on_error(ws, error):
    print("WebSocket error:", error)


def on_close(ws, status_code, message):
    print("\nWebSocket connection closed.")
    print("Status:", status_code)
    print("Message:", message)


def stop_connection(ws):
    print("\n60-second test completed.")
    ws.close()


if __name__ == "__main__":
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    stop_timer = threading.Timer(60, stop_connection, args=[ws])
    stop_timer.daemon = True
    stop_timer.start()

    try:
        ws.run_forever()
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        ws.close()
    finally:
        stop_timer.cancel()
        print("Total WebSocket messages received:", message_count)
