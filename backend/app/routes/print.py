"""
POST /api/print  — render badge and send to auto-discovered printer.
GET  /api/printer — return currently discovered printer (for status display).
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routes.checkin import get_visit
from app.services import badge as badge_svc, printer as printer_svc

router = APIRouter()
logger = logging.getLogger(__name__)


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


class PrintRequest(BaseModel):
    visit_id: str
    printer_addr: str = ""  # "ip:port" — if empty, auto-discover


@router.post("/print")
async def print_badge(req: PrintRequest) -> dict[str, Any]:
    visit = get_visit(req.visit_id)

    printer_addr = req.printer_addr or await _run(printer_svc.discover_printer)
    if not printer_addr:
        raise HTTPException(
            status_code=503,
            detail="No printer found on the network. Make sure your label printer is powered on and connected to the same Wi-Fi network.",
        )

    img = badge_svc.render_badge(visit)

    try:
        await _run(lambda: printer_svc.print_badge(printer_addr, img))
    except Exception as exc:
        logger.error("Print failed to %s: %s", printer_addr, exc)
        raise HTTPException(status_code=500, detail=f"Print failed: {exc}")

    host = printer_addr.split(":")[0]
    return {"status": "printed", "printer_ip": host}


@router.get("/printers")
async def list_printers() -> dict[str, Any]:
    """Scan the network and return all printers found with port 9100 open."""
    addrs = await _run(printer_svc.discover_all_printers)
    printers = [{"address": a, "host": a.split(":")[0]} for a in addrs]
    return {"printers": printers}


@router.get("/printer")
async def get_printer() -> dict[str, Any]:
    """Return cached single-printer discovery result (legacy)."""
    addr = await _run(printer_svc.discover_printer)
    if addr:
        return {"found": True, "address": addr, "host": addr.split(":")[0]}
    return {"found": False, "address": None}
