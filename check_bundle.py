import urllib.request
import re

req = urllib.request.Request('https://quant-terminal-23.preview.emergentagent.com/static/js/bundle.js', headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req).read().decode('utf-8')
print('Size:', len(resp))
apis = set(re.findall(r'https?://[^\s"\'\)]+/api', resp))
for a in apis:
    print('API:', a)
