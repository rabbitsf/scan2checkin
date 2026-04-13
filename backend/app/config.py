import os

OCR_MOCK_MODE = os.getenv("OCR_MOCK_MODE", "false").lower() == "true"

PRINTER_MODEL = os.getenv("PRINTER_MODEL", "QL-810W")
PRINTER_SUBNET = os.getenv("PRINTER_SUBNET", "")  # e.g. "192.168.1" — auto-detected if empty

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE", "/app/credentials/google_service_account.json"
)
