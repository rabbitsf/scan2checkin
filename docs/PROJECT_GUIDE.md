# PROJECT_GUIDE.md — AI External Memory

> This file is the **living system map** for AI assistance.
> Update it whenever the system structure or behavior changes.

---

## 1. Project Overview

**scan2checkin** is a self-hosted visitor check-in web app designed to run on an iPad browser (Safari). Visitors scan their driver's license using the iPad camera, fill in visit details (who they're visiting, purpose), and automatically receive a printed name badge from a Brother QL-810W label printer on the LAN — with no manual printer selection required.

---

## 2. High-Level Architecture

```
iPad Browser (Safari)
  |
  | HTTP/HTTPS
  v
FastAPI Backend (Python, Docker)
  |-- /api/scan     → runs PaddleOCR in-process → parses DL fields
  |-- /api/checkin  → saves visit record (in-memory) + logs to Google Sheets
  |-- /api/print    → discovers printer (mDNS/port-9100 sweep) → print job
  |-- /api/printer  → printer discovery status / force rediscover
  |-- /static/*     → serves frontend HTML/JS/CSS
  |
  |-- PaddleOCR (in-process, no sidecar — models pre-warmed in Docker image)
  |-- Label Printer (LAN, auto-discovered via mDNS or subnet scan, any brand port 9100)
  |-- Google Sheets (visit log via gspread + service account)
```

**Key constraints:**
- iPad Safari requires HTTPS (or localhost) for camera access via `getUserMedia`
- Backend uses `network_mode: host` (or equivalent) so mDNS/Bonjour and raw TCP port 9100 reach LAN devices
- No database — visit records stored in-memory dict (MVP); SQLite can be added later

---

## 3. End-to-End Workflows

### Visitor Check-In Flow
1. iPad opens `http://<server>:8000/` → camera capture page (`index.html`)
2. Visitor taps "Scan License" → rear camera opens via `getUserMedia`
3. Visitor taps "Capture" → frame grabbed as base64 JPEG → `POST /api/scan`
4. Backend decodes image, runs PaddleOCR in-process, parses DL text blocks via `id_parser.py`
5. Structured DL data returned to browser → stored in `sessionStorage`
6. Browser redirects to `form.html` — form pre-filled with DL data
7. Visitor fills in host name, purpose → submits → `POST /api/checkin` → `visit_id` returned
8. Browser redirects to `badge.html?visit_id=<id>` → "Printing your badge..." shown
9. Browser calls `POST /api/print` with `visit_id`
10. Backend: looks up record → renders badge (Pillow) → discovers printer (mDNS → ARP fallback) → sends via brother_ql
11. Badge prints on Brother QL-810W

---

## 4. Canonical Implementations (Single Source of Truth)

| Behavior | Canonical Location | Notes |
|----------|-------------------|-------|
| DL field extraction from OCR text blocks | `backend/app/services/id_parser.py:parse_dl_fields` | Regex-based; maps raw text → snake_case |
| PaddleOCR image-to-blocks | `backend/app/services/ocr.py:run_ocr` | In-process; returns sorted text blocks |
| Printer auto-discovery (mDNS + ARP fallback) | `backend/app/services/printer.py:discover_printer` | 5-min TTL cache; mDNS primary |
| Badge image generation | `backend/app/services/badge.py:render_badge` | Pillow, 720px wide, 62mm tape |
| ID scan endpoint | `backend/app/routes/scan.py:scan_id` | Runs OCR in thread executor, returns fields |
| Check-in record storage | `backend/app/routes/checkin.py` | In-memory dict, keyed by UUID |
| Print job dispatch | `backend/app/routes/print.py:print_badge` | Calls badge + printer services |
| Printer discovery status | `backend/app/routes/print.py` GET/POST `/api/printer` | Status chip + force-rediscover |
| Google Sheets log | `backend/app/services/sheets.py:log_checkin` | gspread service account |
| Camera capture UI | `backend/app/static/index.html` + `backend/app/static/js/camera.js` | iPad rear camera, no build step |
| Visitor form UI | `backend/app/static/form.html` + `backend/app/static/js/form.js` | Pre-fills from sessionStorage |

---

## 5. Generated Artifacts vs. Canonical Sources

| Artifact | Generator/Template | Regenerate Command |
|----------|-------------------|-------------------|
| Docker images | `backend/Dockerfile` + `docker-compose.yml` | `docker compose build` |
| PaddleOCR models | pre-downloaded during `docker compose build` | included in backend image layer |

---

## 6. Duplication Hotspots

- **DL field mapping**: Only `id_parser.py:parse_dl_fields` should contain regex patterns for DL text parsing. Do not re-map fields in routes or frontend JS.
- **Printer IP resolution**: Only `printer.py:discover_printer` should perform discovery. Routes must not implement their own discovery logic.
- **Badge layout**: Only `badge.py:render_badge` should construct the Pillow image. Do not build label images inline in the print route.
- **Visit record lookup**: Centralise in a `get_visit(visit_id)` helper — do not duplicate the dict lookup in multiple routes.

---

## 7. Safe Change Playbook

### Adding a new DL field to the badge
1. Add field to `id_parser.py:parse_dl_fields` return dict
2. Add field to `badge.py:render_badge` layout
3. Add field to `checkin.py` record schema if it needs to be persisted
4. Update `form.html` pre-fill logic if visitor should see/confirm it

### Changing the label printer model
1. Check `brother_ql` supported models list
2. Update `printer.py` — change the `model` constant
3. Update badge dimensions in `badge.py` if tape width changes

### Adding a new visit purpose option
1. Update the `<select>` in `form.html` only — no backend changes needed for MVP

### Switching from in-memory to SQLite storage
1. Add `databases` or `sqlmodel` dependency to `requirements.txt`
2. Replace in-memory dict in `checkin.py` with DB calls
3. Keep the `get_visit(visit_id)` interface unchanged so print route needs no update
