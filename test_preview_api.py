import urllib.request
import json

base = 'https://quant-terminal-23.preview.emergentagent.com/api'
endpoints = [
    '/status',
    '/market-toggle',
    '/upstox/auth-status',
    '/balance',
    '/indian/indices',
    '/indian/fno-securities',
    '/crypto/market',
    '/crypto/options',
    '/crypto/futures-movers',
    '/positions',
    '/signals',
    '/zones',
    '/performance',
    '/scan-results',
    '/alerts',
    '/config'
]

for ep in endpoints:
    try:
        req = urllib.request.Request(f'{base}{ep}', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
            print(f'{ep} -> Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}')
    except Exception as e:
        print(f'{ep} -> Error: {e}')
