import json

with open('preview_api_dump.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

for k, v in d.items():
    print(f'=== {k} ===')
    if isinstance(v, dict):
        for sub_k, sub_v in list(v.items())[:6]:
            if isinstance(sub_v, list):
                print(f'  {sub_k}: list of {len(sub_v)} items, first: {sub_v[0] if sub_v else None}')
            elif isinstance(sub_v, dict):
                print(f'  {sub_k}: dict with keys {list(sub_v.keys())}')
            else:
                print(f'  {sub_k}: {sub_v}')
    elif isinstance(v, list):
        print(f'  list of {len(v)} items: {v[0] if v else None}')
    else:
        print(f'  {v}')
