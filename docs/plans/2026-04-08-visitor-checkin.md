# Visitor Check-In Web App — Implementation Plan
# Progress: 10/10 tasks complete. DONE.
# Last updated: 2026-04-08
# Project: scan2checkin

## Tasks
- [x] Task 1: Project scaffold — directory structure, tech stack, Docker Compose skeleton
- [x] Task 2: Backend — Flask/FastAPI server with health endpoint and config
- [x] Task 3: ID scanning integration — proxy endpoint to kby-ai IDCardRecognition-Docker API
- [x] Task 4: DL field parser — extract name, DOB, address, license number from API response
- [x] Task 5: Frontend — iPad-optimised camera capture page (getUserMedia, capture-to-base64)
- [x] Task 6: Frontend — visitor form page (who are you visiting, purpose of visit, pre-filled DL data)
- [x] Task 7: Printer auto-discovery — mDNS/Bonjour scan for Brother QL-810W on LAN subnet
- [x] Task 8: Badge renderer — generate label image (name, company, date, visitor type)
- [x] Task 9: Print endpoint — send badge to discovered printer via brother_ql or HTTP
- [x] Task 10: End-to-end wiring + Docker Compose with all services + README

---

## Task 1: Project Scaffold

### Goal
Establish directory layout, choose tech stack, and create a runnable Docker Compose skeleton.

### Tech stack decisions
- **Backend:** Python + FastAPI (async-friendly, easy file/binary handling, good ecosystem)
- **Frontend:** Vanilla HTML/CSS/JS — no build step, runs directly from backend static files; works on iPad Safari without any native app install
- **ID OCR service:** kby-ai/IDCardRecognition-Docker — run as a sidecar container, called via HTTP from backend
- **Label printing:** `brother_ql` Python library (supports QL-810W) + `python-zeroconf` for mDNS printer discovery
- **Label image generation:** Pillow (PIL)

### Directory layout
```
scan2checkin/
  backend/
    app/
      main.py           # FastAPI app entrypoint
      config.py         # env-based config
      routes/
        scan.py         # /api/scan  — proxies to OCR service
        checkin.py      # /api/checkin — saves visit record
        print.py        # /api/print  — discovers printer + sends badge
      services/
        id_parser.py    # extracts structured fields from OCR JSON
        printer.py      # mDNS discovery + brother_ql print
        badge.py        # Pillow badge image generator
      static/           # frontend files served by FastAPI
        index.html      # camera capture page
        form.html       # visitor form page
        badge.html      # confirmation/badge preview page
        js/
          camera.js
          form.js
        css/
          style.css
    requirements.txt
    Dockerfile
  docker-compose.yml
  docs/
    PROJECT_GUIDE.md
    CHANGELOG_AI.md
    plans/
      2026-04-08-visitor-checkin.md
  CLAUDE.md
```

### Files to create
- `docker-compose.yml`
- `backend/Dockerfile`
- `backend/requirements.txt`
- `backend/app/main.py` (skeleton)
- `backend/app/config.py`

---

## Task 2: Backend — FastAPI Server

### Goal
Runnable FastAPI server that serves static files and exposes `/api/*` routes.

### Files
- `backend/app/main.py` — mounts static files at `/`, includes routers
- `backend/app/config.py` — reads env vars: `OCR_SERVICE_URL`, `PRINTER_SUBNET`, `BADGE_TEMPLATE`

### Key design
- Static files served from `app/static/` at path `/`
- All API routes under `/api/`
- CORS permissive (iPad on same LAN, different port possible)
- Visit records stored in-memory dict (keyed by UUID) — no database needed for MVP; can add SQLite later

---

## Task 3: ID Scanning Integration

### Goal
Backend endpoint `POST /api/scan` accepts a base64-encoded JPEG image from the browser, forwards it to the kby-ai OCR service, and returns raw parsed JSON.

### Reference
- kby-ai/IDCardRecognition-Docker exposes `POST /idcard/recognition` with `multipart/form-data` or JSON body containing the image
- We run it as `ocr-service` container in Docker Compose on internal network port 8080

### Canonical location
`backend/app/routes/scan.py:scan_id`

### Files
- `backend/app/routes/scan.py`

### Flow
1. Receive `{ "image": "<base64>" }` from browser
2. Decode base64 → bytes
3. POST to `http://ocr-service:8080/idcard/recognition` as multipart
4. Return raw JSON response to frontend

---

## Task 4: DL Field Parser

### Goal
Given the raw OCR JSON from kby-ai service, extract a standardised dict of DL fields: first_name, last_name, dob, address, license_number, expiry_date, state.

### Canonical location
`backend/app/services/id_parser.py:parse_dl_fields`

### Notes
- kby-ai returns fields with keys like `firstName`, `lastName`, `dateOfBirth`, `address`, `licenseNumber`, `expiryDate` — map these to snake_case canonical keys
- Handle missing/null fields gracefully (return empty string, not error)
- Called from `scan.py` before returning response to frontend so browser always gets structured data

---

## Task 5: Frontend — Camera Capture Page

### Goal
iPad-optimised single HTML page that:
1. Opens rear camera via `getUserMedia({ video: { facingMode: "environment" } })`
2. Displays live video preview
3. On "Capture" button tap: grabs frame to canvas, converts to base64 JPEG
4. POSTs to `/api/scan`
5. On success: stores parsed DL fields in `sessionStorage`, redirects to form page
6. Shows loading state and error messages

### Canonical location
`backend/app/static/index.html` + `backend/app/static/js/camera.js`

### iPad Safari considerations
- `getUserMedia` requires HTTPS or localhost — backend must be on HTTPS or accessed via `http://localhost` (if run on the iPad itself) or via a local IP with a self-signed cert (handled in Task 10 notes)
- Avoid Flash/WebRTC polyfills; use standard MediaDevices API
- Large tap targets (min 44px), no hover states

---

## Task 6: Frontend — Visitor Form Page

### Goal
Form page pre-filled with DL data (read from `sessionStorage`) where visitor completes:
- Name (pre-filled, editable)
- Date of birth (pre-filled, read-only display)
- Who they are visiting (free text or dropdown — configurable)
- Purpose of visit (dropdown: Meeting, Delivery, Interview, Contractor, Other)
- Host employee name (free text)

On submit: POST `{ dl_fields, visiting, purpose, host }` to `/api/checkin`, which returns a `visit_id`. Then redirect to badge preview page with `?visit_id=<id>`.

### Canonical location
`backend/app/static/form.html` + `backend/app/static/js/form.js`

---

## Task 7: Printer Auto-Discovery

### Goal
Backend discovers the Brother QL-810W on the local subnet automatically at print time — visitor never sees a printer selection UI.

### Discovery strategy (two-level fallback)
1. **Primary: mDNS/Bonjour** — use `python-zeroconf` to browse `_pdl-datastream._tcp.local.` and `_printer._tcp.local.` services; Brother printers broadcast both. Timeout: 5 seconds.
2. **Fallback: subnet ARP scan** — if mDNS yields nothing, read the server's own IP, derive the /24 subnet, and attempt TCP port 9100 (raw print port) on each host with a 200ms timeout. Return first responding host.
3. **Cache:** Store discovered printer IP in module-level variable with a 5-minute TTL so repeated print calls don't re-scan.

### Canonical location
`backend/app/services/printer.py:discover_printer`

### Files
- `backend/app/services/printer.py`

---

## Task 8: Badge Renderer

### Goal
Generate a label image (PNG) sized for Brother QL-810W 62mm continuous tape (720px wide) containing:
- "VISITOR" header in large bold text
- Full name
- Date (today)
- Visiting: [host name]
- Purpose: [purpose]
- Optional: company logo (read from `static/logo.png` if present, skip if missing)

### Canonical location
`backend/app/services/badge.py:render_badge`

### Notes
- Output: PNG bytes at 300 DPI, width 720px (62mm at 300dpi), height auto-fit to content (~400px)
- Font: use bundled DejaVu Sans (available in most Linux containers) or bundle a TTF in `backend/app/assets/`
- brother_ql expects a PIL Image object or PNG bytes — badge.py returns PIL Image

---

## Task 9: Print Endpoint

### Goal
`POST /api/print` accepts `{ visit_id }`, looks up visit record, calls badge renderer, discovers printer, sends print job.

### Canonical location
`backend/app/routes/print.py:print_badge`

### Flow
1. Look up visit record by `visit_id`
2. Call `badge.render_badge(visit_data)` → PIL Image
3. Call `printer.discover_printer()` → IP string
4. Use `brother_ql` to send: `BrotherQLRaster` → convert image → send to `tcp://<ip>:9100`
5. Return `{ "status": "printed", "printer_ip": "<ip>" }` or error

### Error handling
- Printer not found → 503 with message "No printer found on network"
- Print job failed → 500 with brother_ql error detail
- Visit not found → 404

---

## Task 10: End-to-End Wiring + Docker Compose + README

### Goal
Full `docker-compose.yml` that starts all services; end-to-end smoke test checklist; README with setup instructions.

### Docker Compose services
```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      OCR_SERVICE_URL: http://ocr-service:8080
    depends_on: [ocr-service]
    network_mode: host   # REQUIRED for mDNS/printer discovery on LAN
    # OR use: extra_hosts + host networking for printer reach

  ocr-service:
    image: kbyai/idcard-recognition:latest
    ports: ["8080:8080"]
```

### HTTPS note
iPad Safari requires HTTPS for camera access when not on `localhost`. Options:
1. Run backend on the iPad itself (PWA/localhost) — no HTTPS needed
2. Use a self-signed cert + trust it on the iPad (documented in README)
3. Use `mkcert` on the server host for a trusted local cert

### README sections
- Prerequisites (Docker, same LAN as printer)
- Quick start (`docker compose up`)
- iPad setup (navigate to `http://<server-ip>:8000`, HTTPS options)
- Printer requirements (Brother QL-810W on same LAN, powered on)
- Configuration (env vars)

### Files
- `docker-compose.yml`
- `README.md`
- End-to-end wiring review of all routes and services
