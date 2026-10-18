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
    '/zones?symbol=NIFTY50',
    '/candles/NIFTY50?interval=5m',
    '/indian/option-chain/NIFTY50',
    '/indian/index-constituents?index=NIFTY50',
    '/performance',
    '/scan-results',
    '/config'
]

results = {}
for ep in endpoints:
    try:
        req = urllib.request.Request(f'{base}{ep}', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
            results[ep] = data
    except Exception as e:
        results[ep] = f'Error: {e}'

with open('preview_api_dump.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)

print('Dumped', len(results), 'endpoints to preview_api_dump.json')
