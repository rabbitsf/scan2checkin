"""
Canonical DL field extractor.
Parses AAMVA PDF417 barcode data — the structured data on the back of US DLs.
All field-code-to-snake_case mapping lives here — nowhere else.

Separator handling:
  - Modern decoders (zxing-cpp) return literal "<LF>", "<CR>", "<RS>"
    instead of actual control characters.
  - We handle both formats.
"""
from __future__ import annotations

import re
from typing import Any

# AAMVA 3-letter element codes → our canonical field names.
_AAMVA_MAP: dict[str, str] = {
    "DCS": "last_name",       # Family name (v5+)
    "DAB": "last_name",       # Last name (v1–4 fallback)
    "DAC": "first_name",      # First name
    "DAD": "middle_name",     # Middle name/initial
    "DAA": "_full_name_raw",  # Full legal name (some states)
    "DBB": "dob",             # Date of birth
    "DBA": "expiry_date",     # Document expiry date
    "DAQ": "license_number",  # Driver license number
    "DAG": "address",         # Street address
    "DAI": "city",            # City
    "DAJ": "state",           # State abbreviation
    "DAK": "zip_code",        # Zip code (9 chars, zero-padded)
    "DBC": "_sex_code",       # Sex (1=M, 2=F)
    "DAU": "height",          # Height
    "DAY": "eye_color",       # Eye color
}

_NAME_FIELDS = {"first_name", "last_name", "middle_name", "city"}

# Values that should be treated as absent
_EMPTY_VALUES = {"NONE", "N/A", "", "UNK", "UNKNOWN"}


def parse_dl_fields(aamva_text: str) -> dict[str, Any]:
    """
    Parse an AAMVA PDF417 barcode string into structured DL fields.
    Returns a dict with canonical snake_case keys; missing fields are empty strings.
    """
    fields: dict[str, Any] = {
        "first_name": "",
        "last_name": "",
        "middle_name": "",
        "dob": "",
        "expiry_date": "",
        "license_number": "",
        "address": "",
        "city": "",
        "state": "",
        "zip_code": "",
        "gender": "",
        "height": "",
        "eye_color": "",
        "full_name": "",
        "photo_b64": "",
    }

    elements = _extract_elements(aamva_text)

    for code, field_key in _AAMVA_MAP.items():
        val = elements.get(code, "").strip()
        if not val or val.upper() in _EMPTY_VALUES:
            continue

        if field_key == "_full_name_raw":
            _parse_full_name(val, fields)

        elif field_key == "_sex_code":
            fields["gender"] = {"1": "M", "2": "F"}.get(val, "")

        elif field_key in ("dob", "expiry_date"):
            if not fields[field_key]:
                fields[field_key] = _parse_date(val)

        elif field_key == "zip_code":
            if not fields["zip_code"]:
                z = val.strip()
                fields["zip_code"] = z[:5] if len(z) >= 5 else z

        else:
            if not fields.get(field_key):
                fields[field_key] = _title(val) if field_key in _NAME_FIELDS else val

    # Build full_name convenience field
    parts = [fields["first_name"], fields["middle_name"], fields["last_name"]]
    fields["full_name"] = " ".join(p for p in parts if p).strip()

    return fields


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_elements(aamva_text: str) -> dict[str, str]:
    """
    Extract {code: value} from an AAMVA barcode string.

    Handles two separator formats:
      • Actual control chars: \\n, \\r, \\x1e, \\x1c
      • Literal text tokens:  <LF>, <CR>, <RS>, <FS>  (produced by zxing-cpp)
    """
    elements: dict[str, str] = {}

    # Normalise separators: replace literal tokens with actual \\n so the rest
    # of the code only needs to handle one format.
    text = aamva_text
    text = text.replace("<LF>", "\n").replace("<CR>", "\r")
    text = text.replace("<RS>", "\x1e").replace("<FS>", "\x1c")

    # Split into lines on any combination of control-char separators
    for line in re.split(r"[\r\n\x1e\x1c]+", text):
        line = line.strip()
        # Each element line starts with a 3-char code ([A-Z]{2}[A-Z0-9])
        if len(line) >= 4 and re.match(r"^[A-Z]{2}[A-Z0-9]", line):
            code = line[:3]
            value = line[3:].strip()
            if value and code not in elements:
                elements[code] = value

    # Special case: DAQ (license number) is often embedded in the header as
    # "...DLDAQVALUE\n" rather than on its own line.
    if "DAQ" not in elements:
        m = re.search(r"DLDAQ([A-Z0-9 ]+?)(?=\n|[A-Z]{2}[A-Z0-9]|$)", text)
        if m:
            val = m.group(1).strip()
            if val:
                elements["DAQ"] = val

    return elements


def _parse_full_name(val: str, fields: dict[str, Any]) -> None:
    """Parse DAA (full legal name). Format: 'LAST$FIRST$MIDDLE' or 'LAST, FIRST'."""
    if "$" in val:
        parts = [p.strip() for p in val.split("$")]
        if len(parts) >= 1 and not fields["last_name"]:
            fields["last_name"] = _title(parts[0])
        if len(parts) >= 2 and not fields["first_name"]:
            fields["first_name"] = _title(parts[1])
        if len(parts) >= 3 and not fields["middle_name"]:
            mn = parts[2].strip()
            if mn.upper() not in _EMPTY_VALUES:
                fields["middle_name"] = _title(mn)
    elif "," in val:
        last, _, rest = val.partition(",")
        if not fields["last_name"]:
            fields["last_name"] = _title(last.strip())
        rest_parts = rest.strip().split()
        if rest_parts and not fields["first_name"]:
            fields["first_name"] = _title(rest_parts[0])
        if len(rest_parts) > 1 and not fields["middle_name"]:
            fields["middle_name"] = _title(" ".join(rest_parts[1:]))


def _parse_date(raw: str) -> str:
    """Normalise AAMVA date → MM/DD/YYYY."""
    raw = raw.strip()
    if re.match(r"^\d{8}$", raw):
        if 1 <= int(raw[:2]) <= 12:
            return f"{raw[0:2]}/{raw[2:4]}/{raw[4:8]}"   # MMDDYYYY
        else:
            return f"{raw[4:6]}/{raw[6:8]}/{raw[0:4]}"   # YYYYMMDD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        y, mo, d = raw.split("-")
        return f"{mo}/{d}/{y}"
    return raw


def _title(s: str) -> str:
    """Title-case a name, preserving hyphens."""
    return "-".join(w.capitalize() for w in s.split("-"))
