## [2026-04-12] - Replace kby-ai OCR with PaddleOCR (in-process)

### Changes
- Added `backend/app/services/ocr.py:run_ocr` — PaddleOCR wrapper; accepts a PIL Image, returns sorted text blocks; runs in thread executor to avoid blocking the event loop
- Rewrote `id_parser.py:parse_dl_fields` — now accepts raw PaddleOCR text blocks and uses regex matching instead of kby-ai JSON key mapping
- Updated `scan.py:scan_id` — calls `ocr.run_ocr()` directly; removed HTTP proxy to kby-ai sidecar
- Removed `KBY_LICENSE_KEY` and `OCR_SERVICE_URL` from `config.py`
- Added `numpy`, `paddlepaddle`, `paddleocr` to `backend/requirements.txt`
- Updated `backend/Dockerfile` — added OpenCV/OpenMP system deps; pre-warms PaddleOCR models at build time to avoid cold-start latency
- Removed `ocr-service` block and `KBY_LICENSE_KEY` env var from `docker-compose.yml`
- Updated `docs/PROJECT_GUIDE.md` to reflect PaddleOCR-based architecture

### Files Affected
- `backend/app/services/ocr.py` (new)
- `backend/app/services/id_parser.py`
- `backend/app/routes/scan.py`
- `backend/app/config.py`
- `backend/requirements.txt`
- `backend/Dockerfile`
- `docker-compose.yml`
- `docs/PROJECT_GUIDE.md`

### Canonical Implementations
- PaddleOCR image-to-blocks: `backend/app/services/ocr.py:run_ocr`
- DL field extraction: `backend/app/services/id_parser.py:parse_dl_fields`
- ID scan endpoint: `backend/app/routes/scan.py:scan_id`

---

## [2026-04-08] - Initial Build: scan2checkin Visitor Check-In App

### Changes
- Scaffolded full project structure: Docker Compose, backend Dockerfile, requirements.txt
- Built FastAPI backend with config, health endpoint, and static file serving
- Implemented `POST /api/scan` — proxies base64 image to kby-ai OCR service, returns parsed DL fields
- Implemented `id_parser.py:parse_dl_fields` — maps kby-ai JSON keys to snake_case canonical dict
- Implemented `POST /api/checkin` — stores visit record in-memory dict keyed by UUID; logs to Google Sheets via `sheets.py:log_checkin`
- Implemented `badge.py:render_badge` — Pillow-based label image, 720px wide (62mm tape), DejaVu Sans font
- Implemented `printer.py:discover_printer` — mDNS/Bonjour primary, subnet TCP-9100 sweep fallback, 5-minute TTL cache
- Implemented `POST /api/print` — full print pipeline: record lookup → badge render → printer discovery → brother_ql dispatch
- Built iPad-optimised camera capture page (`index.html` + `camera.js`) using `getUserMedia` rear camera
- Built visitor form page (`form.html` + `form.js`) pre-filled from sessionStorage DL data
- Built badge confirmation page (`badge.html`) with auto-print trigger
- Added `.env.example`, `README.md` with setup, HTTPS options, and printer requirements

### Files Affected
- `docker-compose.yml`
- `backend/Dockerfile`
- `backend/requirements.txt`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/routes/scan.py`
- `backend/app/routes/checkin.py`
- `backend/app/routes/print.py`
- `backend/app/services/id_parser.py`
- `backend/app/services/printer.py`
- `backend/app/services/badge.py`
- `backend/app/services/sheets.py`
- `backend/app/static/index.html`
- `backend/app/static/form.html`
- `backend/app/static/badge.html`
- `backend/app/static/js/camera.js`
- `backend/app/static/js/form.js`
- `backend/app/static/css/style.css`
- `README.md`
- `.env.example`

### Canonical Implementations
- DL field extraction: `backend/app/services/id_parser.py:parse_dl_fields`
- Printer auto-discovery: `backend/app/services/printer.py:discover_printer`
- Badge image generation: `backend/app/services/badge.py:render_badge`
- ID scan proxy: `backend/app/routes/scan.py:scan_id`
- Check-in record storage: `backend/app/routes/checkin.py`
- Print job dispatch: `backend/app/routes/print.py:print_badge`
- Google Sheets log: `backend/app/services/sheets.py:log_checkin`
- Camera capture UI: `backend/app/static/index.html` + `backend/app/static/js/camera.js`
- Visitor form UI: `backend/app/static/form.html` + `backend/app/static/js/form.js`

### Notes
- Pending: Docker build test and kby-ai IDCardRecognition-Docker license key
- iPad Safari requires HTTPS or localhost for camera access — see README for mkcert setup

---
