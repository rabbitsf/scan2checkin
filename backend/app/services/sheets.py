"""
Google Sheets checkin log.
All Sheets interaction lives here — never in routes.
"""
from __future__ import annotations
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from app import config

logger = logging.getLogger(__name__)

# Column headers written to row 1 on first use
_HEADERS = [
    "Timestamp",
    "Full Name",
    "Date of Birth",
    "License Number",
    "State",
    "Address",
    "Visiting Whom",
    "Purpose",
    "Visit Date",
]


def _get_sheet():
    """Return a gspread Worksheet, or None if not configured."""
    if not config.GOOGLE_SHEET_ID:
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
        ]
        creds = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE, scopes=scopes
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(config.GOOGLE_SHEET_ID)
        worksheet = sh.sheet1

        # Ensure headers exist
        existing = worksheet.row_values(1)
        if existing != _HEADERS:
            worksheet.insert_row(_HEADERS, 1)

        return worksheet
    except Exception as exc:
        logger.warning("Google Sheets unavailable: %s", exc)
        return None


def log_checkin(visit: dict[str, Any]) -> None:
    """Append a visit record row to the configured Google Sheet."""
    sheet = _get_sheet()
    if sheet is None:
        logger.info("Google Sheets not configured — skipping log")
        return

    try:
        row = [
            datetime.now(tz=ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M:%S %Z"),
            visit.get("full_name", ""),
            visit.get("dob", ""),
            visit.get("license_number", ""),
            visit.get("state", ""),
            visit.get("address", ""),
            visit.get("visiting_whom", ""),
            visit.get("purpose", ""),
            visit.get("visit_date", ""),
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info("Logged checkin to Google Sheets for %s", visit.get("full_name"))
    except Exception as exc:
        logger.warning("Failed to log to Google Sheets: %s", exc)
