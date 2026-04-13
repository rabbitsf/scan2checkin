# scan2checkin

Self-hosted visitor check-in kiosk for iPad. Visitors scan their driver's license, fill in visit details, and receive a printed name badge — automatically sent to a label printer on your local network.

## How it works

1. Visitor opens the web app on an iPad
2. Rear camera opens — visitor holds up their driver's license
3. ID is scanned via [kby-ai IDCardRecognition](https://github.com/kby-ai/IDCardRecognition-Docker)
4. Visitor confirms their name, enters who they're visiting and why
5. Badge prints automatically on the label printer (no manual selection)
6. Visit is logged to a Google Sheet

---

## Prerequisites

- Docker + Docker Compose on a Mac or Linux machine on your local network
- A label printer (Brother QL-810W or any printer accessible on TCP port 9100) on the same Wi-Fi/LAN
- An iPad on the same network as the server
- (Optional) Google Sheet for visit logs

---

## Quick Start

### 1. Clone & configure

```bash
git clone <this-repo>
cd scan2checkin
cp .env.example .env
```

Edit `.env`:

```env
# Required for real ID scanning (leave blank to use mock/demo mode)
KBY_LICENSE_KEY=your_key_here

# Set to true to use mock data (no API key needed, for testing)
OCR_MOCK_MODE=false

# Printer model — any Brother QL model, e.g. QL-810W, QL-820NWB, QL-1110NWB
# Leave as default for generic port-9100 printers
PRINTER_MODEL=QL-810W

# Optional: force the subnet to scan (auto-detected if blank)
# PRINTER_SUBNET=192.168.1

# Google Sheets (optional — visits still work without this)
GOOGLE_SHEET_ID=your_sheet_id_here
GOOGLE_CREDENTIALS_FILE=/app/credentials/google_service_account.json
```

### 2. Google Sheets setup (optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Create project
2. Enable **Google Sheets API**
3. Create a **Service Account** → download the JSON key
4. Create a folder: `mkdir credentials`
5. Save the JSON key as `credentials/google_service_account.json`
6. Share your Google Sheet with the service account email (Editor access)
7. Copy the Sheet ID from its URL: `https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit`

### 3. Start

```bash
docker compose up -d
```

The app is available at `http://<your-server-ip>:8000`.

---

## iPad Camera Access (HTTPS)

Safari on iPad requires HTTPS for camera access when the site is not `localhost`.

**Option A — mkcert (recommended for LAN use):**

```bash
brew install mkcert
mkcert -install
mkcert <your-server-ip>
# Creates <ip>+1.pem and <ip>+1-key.pem
```

Then put a reverse proxy (nginx or Caddy) in front of uvicorn:

```bash
# Caddy example — add to docker-compose.yml or run separately
caddy reverse-proxy --from https://<your-server-ip>:443 --to localhost:8000 \
  --tls-cert <ip>.pem --tls-key <ip>-key.pem
```

Trust the mkcert CA on your iPad: `mkcert -CAROOT` → copy `rootCA.pem` to iPad via AirDrop → tap to install → Settings → General → About → Certificate Trust Settings → enable.

**Option B — self-signed cert (quick, requires one-time trust on iPad):**

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=<your-server-ip>" -addext "subjectAltName=IP:<your-server-ip>"
```

**Option C — run backend directly on the iPad** (using an iPad server app like `a-Shell`) — camera works over `localhost` without HTTPS.

---

## Printer Setup

The app auto-discovers your printer at print time using:
1. **mDNS/Bonjour** — detects `_pdl-datastream._tcp.local.` and `_printer._tcp.local.` services
2. **TCP port 9100 sweep** — scans your /24 subnet for hosts accepting connections on port 9100

**Brother QL printers:** Make sure the printer is in "wireless" mode and connected to the same network. The `brother_ql` library handles the QL-specific raster format automatically.

**Other label printers:** Set `PRINTER_MODEL=generic` in `.env`. The app will send PNG data raw over TCP port 9100. This works with many industrial label printers in passthrough/streaming mode.

To force re-scan the network (clears the 5-minute cache):

```
POST /api/printer/rediscover
```

---

## LAN Printer Discovery (network_mode: host)

If mDNS discovery doesn't find your printer, uncomment `network_mode: host` in `docker-compose.yml` and remove the `ports` mapping. This gives the container direct access to the host network interface, which is required for mDNS/Bonjour on some setups.

---

## Mock / Development Mode

To test without an ID scanner or printer:

```env
OCR_MOCK_MODE=true
```

The scan endpoint returns a fake "Jane Smith" record so you can test the full flow.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KBY_LICENSE_KEY` | *(empty)* | kby-ai license key for ID recognition |
| `OCR_MOCK_MODE` | `false` | Use mock OCR data (no key needed) |
| `OCR_SERVICE_URL` | `http://ocr-service:8080` | URL of the OCR sidecar |
| `PRINTER_MODEL` | `QL-810W` | Brother QL model or `generic` |
| `PRINTER_SUBNET` | *(auto)* | Force subnet prefix e.g. `192.168.1` |
| `GOOGLE_SHEET_ID` | *(empty)* | Google Sheet ID for checkin log |
| `GOOGLE_CREDENTIALS_FILE` | `/app/credentials/google_service_account.json` | Path to service account JSON |

---

## Badge Contents

- **VISITOR** header
- Full name (from license)
- Face photo (cropped from license by OCR service, if available)
- Date
- Visiting: [host name]
- Purpose: [reason]
- Optional company logo: place a `logo.png` in `backend/app/static/logo.png`

Badge is sized for **62mm continuous tape** (720px wide) at 300 DPI.

---

## Architecture

```
iPad Safari → FastAPI (backend) → kby-ai OCR (sidecar)
                               → Google Sheets (log)
                               → Label Printer (LAN port 9100)
```

All frontend files are plain HTML/CSS/JS — no build step, works on iPad Safari without any native app.
