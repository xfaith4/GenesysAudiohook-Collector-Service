# Genesys AudioHook Collector → Elastic (Service Install)

This package runs a small Python service that:
- Authenticates to **Genesys Cloud** (OAuth2 client credentials)
- Auto-discovers **AudioHook** operational topics (or uses `topics.json`)
- Opens a **Notifications WebSocket**, auto-reconnects & resubscribes
- Ships events to **Elastic** via the **Bulk API**
- Exposes local **/health** and **/stats** (default port 8077)

## What you need
- A **Genesys OAuth client** (client credentials) with permissions to create/manage notifications channels.
- **Elastic** URL + auth (user/pass, ApiKey, or Bearer token).
- On Windows: PowerShell 5.1+ or 7+, any standard user with rights to create a service.
- On Linux: systemd host (Ubuntu/Debian/RHEL etc.), sudo.

## Files in this folder
- `collector.py`              # the service app (your updated AudioHook collector)
- `.env.example`              # template for environment variables
- `topics.json`               # optional topic list (auto-discovery works without it)
- `install-windows.ps1`       # installs Windows service
- `uninstall-windows.ps1`     # removes Windows service
- `run-collector.ps1`         # service entry script (loads .env, runs Python)
- `install-linux.sh`          # installs systemd service on Linux
- `genesys-audiohook-collector.service`  # systemd unit file (used by the installer)

## Windows Install (PowerShell)
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\install-windows.ps1
# Then check:
Get-Service GenesysAudioHookCollector
Start-Service GenesysAudioHookCollector
# Health:
Invoke-RestMethod http://localhost:8077/health

### END: README.md

---

### BEGIN: .env.example
```ini
# --- Genesys ---
GENESYS_ENV=usw2.pure.cloud
GENESYS_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
GENESYS_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# --- Topic selection (optional; auto-discovery works if omitted) ---
AUTO_DISCOVER_AUDIOHOOK=true
TOPICS_FILE=/opt/genesys-audiohook/topics.json
TOPIC_INCLUDE_REGEX=audiohook
TOPIC_EXCLUDE_REGEX=
FALLBACK_TOPICS=channel.metadata,v2.users.me.presence

# --- Elastic sink ---
ELASTIC_URL=https://elastic.example.com:9200
# One of:
ELASTIC_AUTH=elastic:YourPassword
# OR:
# ELASTIC_AUTH=ApiKey base64IdColonSecret
# OR:
# ELASTIC_AUTH=Bearer eyJhbGciOi...

ELASTIC_DATASTREAM=false
ELASTIC_INDEX=genesys-audiohook

# --- Bulk behavior ---
BULK_MAX_DOCS=200
BULK_MAX_SECONDS=5
BULK_CONCURRENCY=2
RETRY_BASE_SLEEP=1.5
RETRY_MAX_SLEEP=30

# --- Status server ---
HTTP_STATUS_ENABLED=true
HTTP_STATUS_HOST=0.0.0.0
HTTP_STATUS_PORT=8077
### END: .env.example
