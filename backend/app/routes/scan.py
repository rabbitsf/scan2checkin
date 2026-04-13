"""
POST /api/scan — decode PDF417 barcode from the back of a DL, return parsed fields.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import config
from app.services.id_parser import parse_dl_fields

router = APIRouter()
logger = logging.getLogger(__name__)


class ScanRequest(BaseModel):
    image: str  # base64-encoded JPEG or PNG (data URI or raw base64)


class ScanResponse(BaseModel):
    fields: dict[str, Any]
    raw: dict[str, Any]


@router.post("/scan", response_model=ScanResponse)
async def scan_id(req: ScanRequest) -> ScanResponse:
    """Decode PDF417 barcode from the back of a DL, return structured fields."""
    if config.OCR_MOCK_MODE:
        aamva_text = _mock_aamva()
    else:
        aamva_text = await _decode_barcode(req.image)

    fields = parse_dl_fields(aamva_text)
    logger.info("Parsed fields: %s", {k: v for k, v in fields.items() if k != "photo_b64"})
    return ScanResponse(fields=fields, raw={"aamva": aamva_text})


@router.get("/scan/debug")
async def scan_debug() -> dict[str, Any]:
    """Confirm the barcode service is operational. GET /api/scan/debug"""
    if config.OCR_MOCK_MODE:
        return {"mode": "mock", "sample_fields": parse_dl_fields(_mock_aamva())}
    return {
        "mode": "live",
        "note": "Barcode service ready. POST a base64 image of the DL back to /api/scan.",
    }


async def _decode_barcode(image_b64: str) -> str:
    """Run zxing-cpp PDF417 decode in a thread so the event loop stays free."""
    from app.services.barcode import decode_pdf417

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, decode_pdf417, image_b64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Barcode decode error: %s", exc)
        raise HTTPException(status_code=503, detail=f"Barcode decode failed: {exc}")


def _mock_aamva() -> str:
    """Return a plausible AAMVA string for development/testing."""
    return (
        "@\n\x1e\rANSI 636014040002DL00410278ZC03260028DLDAQ D2829121\n"
        "DCSSMITH\n"
        "DACJANE\n"
        "DADA\n"
        "DBB06151985\n"
        "DBA06152027\n"
        "DAG123 MAIN STREET\n"
        "DAISPRINGFIELD\n"
        "DAJCA\n"
        "DAK90210    \n"
        "DBC2\n"
        "DAU506 in\n"
        "DAYBRO\n"
    )
