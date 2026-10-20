#!/usr/bin/env bash
# ==============================================================================
# Algo Monitor — Automated VPS Deployment Script (Ubuntu / Debian)
# ==============================================================================
set -e

echo "=========================================================="
echo "         Algo Monitor — VPS Setup & Deployment            "
echo "=========================================================="

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="$(whoami)"

echo "[1/6] Installing Python 3.12 and prerequisites..."
sudo apt update -y
sudo apt install -y software-properties-common curl git ufw build-essential

# Ensure Python 3.12 is installed (required by upstox-totp and modern packages)
if ! command -v python3.12 &> /dev/null; then
    echo "--> Adding deadsnakes PPA to install Python 3.12..."
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt update -y
    sudo apt install -y python3.12 python3.12-venv python3.12-dev
fi

echo "[2/6] Setting up Python 3.12 virtual environment in ${APP_DIR}/.venv..."
# If .venv exists but is using an older python version, recreate it with 3.12
if [ -d "${APP_DIR}/.venv" ]; then
    VENV_PY_VER="$("${APP_DIR}/.venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")"
    if [ "${VENV_PY_VER}" != "3.12" ]; then
        echo "--> Existing .venv is on Python ${VENV_PY_VER}, recreating with Python 3.12..."
        rm -rf "${APP_DIR}/.venv"
    fi
fi

if [ ! -d "${APP_DIR}/.venv" ]; then
    python3.12 -m venv "${APP_DIR}/.venv"
fi

echo "[3/6] Installing Python dependencies..."
"${APP_DIR}/.venv/bin/pip" install --upgrade pip setuptools wheel
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "[4/6] Checking configuration (.env)..."
if [ ! -f "${APP_DIR}/.env" ]; then
    if [ -f "${APP_DIR}/.env.example" ]; then
        cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
        echo "--> Created .env from .env.example."
        echo "--> IMPORTANT: Please edit ${APP_DIR}/.env with your real API keys!"
    fi
else
    echo "--> Existing .env found."
fi

echo "[5/6] Configuring systemd service (algo-monitor.service)..."
SERVICE_FILE="/etc/systemd/system/algo-monitor.service"

cat <<EOF | sudo tee "${SERVICE_FILE}" > /dev/null
[Unit]
Description=Algo Monitor Trading Engine & Web Terminal
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python run.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable algo-monitor

echo "[6/6] Setup complete!"
echo "=========================================================="
echo " Next Steps:"
echo " 1. Edit your .env file: nano ${APP_DIR}/.env"
echo " 2. Start the service:   sudo systemctl start algo-monitor"
echo " 3. View live logs:      sudo journalctl -u algo-monitor -f"
echo " 4. Check status:        sudo systemctl status algo-monitor"
echo "=========================================================="
