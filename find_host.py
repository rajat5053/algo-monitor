import urllib.request
import re

req = urllib.request.Request('https://quant-terminal-23.preview.emergentagent.com/static/js/bundle.js', headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
target = 'quant-terminal-23.preview.emergentagent.com'
matches = [m.start() for m in re.finditer(re.escape(target), resp)]
print(f"Occurrences of '{target}': {len(matches)}")
for idx in matches:
    print(f"Match at {idx}:")
    print(resp[max(0, idx-50):min(len(resp), idx+100)])
