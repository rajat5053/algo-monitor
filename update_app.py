import re

with open('algo_monitor/dashboard/app.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Let's inspect create_app in app.py
print("Read", len(code), "bytes of app.py")
