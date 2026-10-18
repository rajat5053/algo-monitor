import urllib.request
req = urllib.request.Request('https://quant-terminal-23.preview.emergentagent.com/static/js/bundle.js', headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
pos = resp.find('baseURL: API')
print("Context around baseURL: API:")
print(resp[max(0, pos-200):pos+150])
