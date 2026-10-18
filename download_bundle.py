import urllib.request
import os

bundle_url = 'https://quant-terminal-23.preview.emergentagent.com/static/js/bundle.js'
print('Downloading bundle.js...')
req = urllib.request.Request(bundle_url, headers={'User-Agent': 'Mozilla/5.0'})
content = urllib.request.urlopen(req, timeout=60).read().decode('utf-8')
print('Downloaded size:', len(content))

old_url = 'https://quant-terminal-23.preview.emergentagent.com'
new_url = ''

if old_url in content:
    content = content.replace(f'"{old_url}"', '""')
    print('Successfully patched API base URL to relative ""')
else:
    print('WARNING: old_url not found in content!')

out_dir = os.path.join('algo_monitor', 'dashboard', 'static', 'js')
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, 'bundle.js')

with open(out_file, 'w', encoding='utf-8') as f:
    f.write(content)

print('Saved patched bundle to:', out_file)
print('File size:', os.path.getsize(out_file))
