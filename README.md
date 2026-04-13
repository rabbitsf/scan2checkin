# scan2checkin

Self-hosted visitor check-in kiosk for iPad. Visitors scan the **back** of their driver's license (PDF417 barcode), fill in visit details, and receive a printed name badge — automatically sent to a label printer on your local network.

No paid license required. No external OCR service. Works fully offline.

## How it works

1. Visitor opens the web app on an iPad
2. Rear camera opens — visitor holds up the **back** of their driver's license
3. PDF417 barcode is decoded via [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) and parsed using the AAMVA standard
4. Visitor confirms their name, enters who they're visiting and why
5. Badge prints on the selected label printer
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
git clone git@github.com:rabbitsf/scan2checkin.git
cd scan2checkin
cp .env.example .env
```

Edit `.env`:

```env
# Set to true to use mock data (no camera needed, for testing)
OCR_MOCK_MODE=false

# Printer model — any Brother QL model, e.g. QL-810W, QL-820NWB, QL-1110NWB
# Use "generic" for non-Brother printers that accept raw data on port 9100
PRINTER_MODEL=QL-810W

# Optional: force the subnet to scan for the printer (auto-detected if blank)
# Examples: "192.168.1"  or  "10.100.0.0/16"
# PRINTER_SUBNET=

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
# Creates <ip>.pem and <ip>-key.pem
```

Then put a reverse proxy (nginx or Caddy) in front of uvicorn:

```bash
# Caddy example
caddy reverse-proxy --from https://<your-server-ip>:443 --to localhost:8000 \
  --tls-cert <ip>.pem --tls-key <ip>-key.pem
```

Trust the mkcert CA on your iPad: `mkcert -CAROOT` → copy `rootCA.pem` to iPad via AirDrop → tap to install → Settings → General → About → Certificate Trust Settings → enable.

**Option B — self-signed cert (quick, requires one-time trust on iPad):**

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=<your-server-ip>" -addext "subjectAltName=IP:<your-server-ip>"
```

---

## Printer Setup

At the "You're Checked In!" page, the app scans your network and shows a dropdown of all printers found with port 9100 open. Select the printer and click **Print Badge**.

Discovery strategy:
1. **`host.docker.internal`** — on Docker Desktop (macOS/Windows), resolves to the host machine's LAN IP so the correct /24 is scanned automatically
2. **mDNS/Bonjour** — detects `_pdl-datastream._tcp.local.` and `_printer._tcp.local.` services
3. **TCP port 9100 sweep** — scans up to 5 /24 blocks starting from the host machine's subnet

**Brother QL printers:** Make sure the printer is connected to the same Wi-Fi. The `brother_ql` library handles the QL-specific raster format automatically.

**Other label printers:** Set `PRINTER_MODEL=generic` in `.env`. The app sends PNG data raw over TCP port 9100.

If your printer isn't found, set `PRINTER_SUBNET` to your network's range (e.g. `10.100.0.0/16`) in `.env` and restart.

---

## Mock / Development Mode

To test without a camera or printer:

```env
OCR_MOCK_MODE=true
```

The scan endpoint returns a fake "Jane Smith" record so you can test the full form and print flow.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OCR_MOCK_MODE` | `false` | Return mock scan data (no camera needed) |
| `PRINTER_MODEL` | `QL-810W` | Brother QL model or `generic` |
| `PRINTER_SUBNET` | *(auto)* | Subnet to scan, e.g. `192.168.1` or `10.100.0.0/16` |
| `GOOGLE_SHEET_ID` | *(empty)* | Google Sheet ID for check-in log |
| `GOOGLE_CREDENTIALS_FILE` | `/app/credentials/google_service_account.json` | Path to service account JSON |

---

## Badge Contents

- **VISITOR** header
- Full name (from license barcode)
- Date of visit
- Visiting: [host name]
- Purpose: [reason]
- Optional company logo: place a `logo.png` in `backend/app/static/logo.png`

Badge is sized for **62mm continuous tape** (720px wide).

---

## Architecture

```
iPad Safari → FastAPI backend → zxing-cpp PDF417 decode → AAMVA parser
                              → Google Sheets (check-in log)
                              → Label Printer (LAN TCP port 9100)
```

All frontend files are plain HTML/CSS/JS — no build step, works on iPad Safari without any native app.
