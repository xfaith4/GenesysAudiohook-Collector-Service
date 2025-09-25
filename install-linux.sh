#!/usr/bin/env bash
set -euo pipefail

# Install Genesys AudioHook Collector as a systemd service
APP_ROOT="/opt/genesys-audiohook"
UNIT="/etc/systemd/system/genesys-audiohook-collector.service"

sudo mkdir -p "$APP_ROOT"
sudo cp -f collector.py "$APP_ROOT/"
[ -f topics.json ] && sudo cp -f topics.json "$APP_ROOT/"
[ -f .env ] && sudo cp -f .env "$APP_ROOT/" || true

# Python venv + deps
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.9+."; exit 1
fi
if [ ! -d "$APP_ROOT/venv" ]; then
  sudo python3 -m venv "$APP_ROOT/venv"
fi
sudo "$APP_ROOT/venv/bin/pip" install --upgrade pip
sudo "$APP_ROOT/venv/bin/pip" install aiohttp

# Unit file
sudo tee "$UNIT" >/dev/null <<'SERVICE'
[Unit]
Description=Genesys AudioHook Collector
After=network.target

[Service]
Type=simple
EnvironmentFile=-/opt/genesys-audiohook/.env
WorkingDirectory=/opt/genesys-audiohook
ExecStart=/opt/genesys-audiohook/venv/bin/python -u /opt/genesys-audiohook/collector.py
Restart=on-failure
RestartSec=5
# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
# If you bind to 8077:
ExecStartPre=/bin/sh -c 'echo "Starting Genesys AudioHook Collector"'

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable --now genesys-audiohook-collector

echo "Service installed. Check status:"
echo "  sudo systemctl status genesys-audiohook-collector"
echo "Health endpoint (if enabled in .env): http://localhost:8077/health"
