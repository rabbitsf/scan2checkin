"""
POST /api/checkin — save visit record in-memory and log to Google Sheets.
GET  /api/checkin/{visit_id} — retrieve a visit record.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import sheets

router = APIRouter()

# In-memory visit store — keyed by visit_id (UUID string).
# Used for badge printing within the same session.
# Persistent log is in Google Sheets.
_visits: dict[str, dict[str, Any]] = {}


class CheckinRequest(BaseModel):
    # DL fields (from sessionStorage / scan response)
    first_name: str = ""
    last_name: str = ""
    middle_name: str = ""
    full_name: str = ""
    dob: str = ""
    license_number: str = ""
    state: str = ""
    address: str = ""
    photo_b64: str = ""

    # Visit details (filled in by visitor on form page)
    visiting_whom: str
    purpose: str


class CheckinResponse(BaseModel):
    visit_id: str


@router.post("/checkin", response_model=CheckinResponse)
async def create_checkin(req: CheckinRequest) -> CheckinResponse:
    visit_id = str(uuid.uuid4())

    # Derive full_name if not provided
    full_name = req.full_name or " ".join(
        p for p in [req.first_name, req.middle_name, req.last_name] if p
    ).strip()

    visit: dict[str, Any] = {
        **req.model_dump(),
        "full_name": full_name,
        "visit_date": datetime.now(tz=ZoneInfo("America/Los_Angeles")).strftime("%B %d, %Y"),
        "visit_id": visit_id,
    }
    _visits[visit_id] = visit

    # Log to Google Sheets (best-effort, non-blocking errors)
    sheets.log_checkin(visit)

    return CheckinResponse(visit_id=visit_id)


@router.get("/checkin/{visit_id}")
async def get_checkin(visit_id: str) -> dict[str, Any]:
    visit = _visits.get(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    return visit


def get_visit(visit_id: str) -> dict[str, Any]:
    """Internal helper — canonical single place to look up a visit record."""
    visit = _visits.get(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    return visit
