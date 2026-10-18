with open('check_bundle.py', 'w') as f:
    f.write('''import re
with open("bundle_sample.txt", "w") as out:
    pass
with open("quant_preview_src/lib/api.js", "r") as f:
    print("lib/api.js:")
    print(f.read())
''')
