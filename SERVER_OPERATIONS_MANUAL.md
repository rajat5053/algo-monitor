# Algo Monitor — Complete Server Operations & Command Reference Manual

This document is your master cheat-sheet containing **every command** needed to operate, monitor, debug, update, and maintain Algo Monitor on your Linux VPS.

---

## Table of Contents
1. [Core Service Management (systemd)](#1-core-service-management-systemd)
2. [Live Logs & Monitoring](#2-live-logs--monitoring)
3. [Configuration & Environment (.env)](#3-configuration--environment-env)
4. [Manual CLI Run Modes & Utilities](#4-manual-cli-run-modes--utilities)
5. [Diagnostics & Connectivity Tests](#5-diagnostics--connectivity-tests)
6. [Database Management & Capital Resets](#6-database-management--capital-resets)
7. [Updating Code & Dependencies](#7-updating-code--dependencies)
8. [Firewall & Network Security](#8-firewall--network-security)
9. [Database Backups & Download to Local PC](#9-database-backups--download-to-local-pc)
10. [Optional: Password Protection via Nginx](#10-optional-password-protection-via-nginx)

---

## 1. Core Service Management (systemd)

Algo Monitor runs 24/7 as a background service managed by `systemd`.

| Action | Command |
| :--- | :--- |
| **Check service status** | `systemctl status algo-monitor` |
| **Start service** | `systemctl start algo-monitor` |
| **Stop service** | `systemctl stop algo-monitor` |
| **Restart service** | `systemctl restart algo-monitor` |
| **Enable autostart on boot** | `systemctl enable algo-monitor` |
| **Disable autostart on boot** | `systemctl disable algo-monitor` |
| **Reload systemd config** (after editing `.service` file) | `systemctl daemon-reload` |

---

## 2. Live Logs & Monitoring

Monitor live strategy scans, paper trades, WebSocket feeds, and potential errors:

### Watch Live Real-Time Logs
```bash
journalctl -u algo-monitor -f
```
*(Press `Ctrl + C` anytime to exit log streaming)*

### View Recent 100 Lines of Logs
```bash
journalctl -u algo-monitor -n 100 --no-pager
```

### View Only Errors or Warnings
```bash
journalctl -u algo-monitor -p err --no-pager
```

### View Logs from Today Only
```bash
journalctl -u algo-monitor --since today
```

---

## 3. Configuration & Environment (.env)

Application settings and API credentials live in the `.env` file.

### Edit Environment Variables
```bash
nano /opt/algo-monitor/algo-monitor/.env
```
*(After editing: `Ctrl + O`, `Enter` to save, `Ctrl + X` to exit)*

### Apply Changes After Editing `.env`
Whenever you edit `.env`, restart the service to apply changes:
```bash
systemctl restart algo-monitor
```

### Important Settings Quick Reference:
```ini
# Network Binding
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8501

# Paper Trading & Risk
PAPER_TRADING_BALANCE=1000000
MAX_POSITIONS=5
RISK_PER_TRADE=0.02
MAX_DAILY_LOSS=0.05
MIN_REWARD_RISK=1.5

# Upstox 2FA (Auto-login at 08:45 AM weekdays)
UPSTOX_API_KEY=your_key
UPSTOX_API_SECRET=your_secret
UPSTOX_USERNAME=your_mobile
UPSTOX_USER_PIN=your_pin
UPSTOX_TOTP_KEY=your_totp_secret

# Delta Exchange India
DELTA_API_KEY=your_delta_key
DELTA_API_SECRET=your_delta_secret

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## 4. Manual CLI Run Modes & Utilities

You can run individual modules or test modes manually using the Python virtual environment:

```bash
cd /opt/algo-monitor/algo-monitor
```

### Run Full Application in Foreground (for interactive debugging)
```bash
# Note: Stop the systemd service first to avoid port collision
systemctl stop algo-monitor
.venv/bin/python run.py
```

### Run Dashboard Only (no data ingestion or strategy scans)
```bash
.venv/bin/python run.py --dashboard
```

### Run Backend Scanner Only (no web dashboard)
```bash
.venv/bin/python run.py --backend-only
```

### Run a Single Immediate Market Scan Cycle & Exit
```bash
.venv/bin/python run.py --scan-once
```

### Run Historical Backtest on Stored Candles
```bash
.venv/bin/python run.py --backtest
```

### Reset Paper Trading Capital
Reset your paper balance to ₹1,000,000 (or custom amount) and clear past closed trades:
```bash
.venv/bin/python reset_capital.py --capital 1000000 --clear-trades
```

---

## 5. Diagnostics & Connectivity Tests

Run these quick one-liner tests to verify connections, feeds, and alerts.

### A. Test Telegram Alerts to Your Phone
```bash
cd /opt/algo-monitor/algo-monitor
.venv/bin/python -c "
from algo_monitor.alerts.notifier import TelegramNotifier
from algo_monitor.config.settings import get_settings
s = get_settings()
tg = TelegramNotifier(s.telegram.bot_token, s.telegram.chat_id)
tg.send_text('🔔 Algo Monitor Test: Telegram connection is active!')
print('Telegram test message sent!')
"
```

### B. Test Upstox 2FA Auto-Login & TOTP Generation
```bash
cd /opt/algo-monitor/algo-monitor
.venv/bin/python -c "
from algo_monitor.data.upstox_auth import UpstoxAuthManager
auth = UpstoxAuthManager()
token = auth.fetch_new_token()
print('Upstox Token Success:' if token else 'Upstox Token Failed!', token[:15] if token else '')
"
```

### C. Test Delta Exchange API & Live WebSocket Feed
```bash
cd /opt/algo-monitor/algo-monitor
.venv/bin/python delta_test.py
```

### D. Check if Port 8501 is Open and Listening
```bash
ss -tulpn | grep 8501
```

### E. Test Local HTTP Response on Server
```bash
curl -I http://127.0.0.1:8501
```

### F. Run the Full Unit & Signal Test Suite
```bash
cd /opt/algo-monitor/algo-monitor
.venv/bin/pytest tests/ -v
```

---

## 6. Database Management & Capital Resets

Algo Monitor stores all candles, active zones, signals, and paper trade history in SQLite at `/opt/algo-monitor/algo-monitor/algo_monitor.db`.

### Check Database File Size
```bash
ls -lh /opt/algo-monitor/algo-monitor/algo_monitor.db*
```

### Inspect Database Tables Directly via SQLite CLI
```bash
apt install -y sqlite3
sqlite3 /opt/algo-monitor/algo-monitor/algo_monitor.db
```

*Inside SQLite shell:*
```sql
-- See table row counts
SELECT count(*) FROM trades;
SELECT count(*) FROM signals;
SELECT count(*) FROM candles;

-- View recent paper trades
SELECT id, symbol, direction, entry_price, status, pnl FROM trades ORDER BY id DESC LIMIT 5;

-- Exit sqlite shell
.exit
```

### Optimize / Vacuum SQLite Database
```bash
sqlite3 /opt/algo-monitor/algo-monitor/algo_monitor.db "VACUUM;"
```

---

## 7. Updating Code & Dependencies

When you modify code on your local PC and want to push the updates to your VPS:

### If Using Git:
```bash
cd /opt/algo-monitor/algo-monitor
git pull
.venv/bin/pip install -r requirements.txt
systemctl restart algo-monitor
```

### If Uploading from Windows PowerShell via SCP:
On your **Windows PowerShell**:
```powershell
cd "d:\Projects\Algo Monitor"
tar -a -c -f update.zip --exclude=.venv --exclude=algo_monitor.db* *
scp update.zip root@145.79.134.60:/opt/algo-monitor/algo-monitor/
Remove-Item update.zip
```
Then on your **VPS**:
```bash
cd /opt/algo-monitor/algo-monitor
unzip -o update.zip
rm update.zip
.venv/bin/pip install -r requirements.txt
systemctl restart algo-monitor
```

---

## 8. Firewall & Network Security

### Ubuntu Firewall (UFW) Commands:
```bash
# Check firewall status and active rules
ufw status verbose

# Allow web dashboard port
ufw allow 8501/tcp

# Allow SSH port (CRITICAL - never disable port 22!)
ufw allow 22/tcp

# Delete a rule if needed
ufw delete allow 8501/tcp

# Reload firewall
ufw reload
```

### Virtualizor Control Panel Firewall:
Always maintain these 2 rules in your Virtualizor Firewall Plan:
1. `IN` | `IPv4` | `ACCEPT` | `TCP` | Port `22` | `0.0.0.0/0` (SSH access)
2. `IN` | `IPv4` | `ACCEPT` | `TCP` | Port `8501` | `0.0.0.0/0` (Dashboard access)

---

## 9. Database Backups & Download to Local PC

### Create a Timestamped Backup on the VPS:
```bash
cd /opt/algo-monitor/algo-monitor
cp algo_monitor.db "algo_monitor_backup_$(date +%Y%m%d_%H%M%S).db"
```

### Download the Database to Your Windows PC:
Run this on your **Windows PowerShell**:
```powershell
scp root@145.79.134.60:/opt/algo-monitor/algo-monitor/algo_monitor.db "d:\Projects\Algo Monitor\algo_monitor_vps_backup.db"
```

---

## 10. Optional: Password Protection via Nginx

To add HTTP Basic Auth password protection (prompts for username & password on phone):

```bash
# 1. Install Nginx and auth utilities
apt install -y nginx apache2-utils

# 2. Create your login credentials (replace 'myusername' with your desired username)
htpasswd -c /etc/nginx/.htpasswd myusername

# 3. Configure Nginx reverse proxy
cp /opt/algo-monitor/algo-monitor/nginx.conf.example /etc/nginx/sites-available/algo-monitor
ln -s /etc/nginx/sites-available/algo-monitor /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 4. Restart Nginx and allow port 80
nginx -t && systemctl restart nginx
ufw allow 80/tcp
```
Then access on your phone via: `http://145.79.134.60` (without needing `:8501`).
