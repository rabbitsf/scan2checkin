"""
OCR service using PaddleOCR 2.x — runs in-process, no sidecar container required.
Canonical location for image-to-text-blocks conversion.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Lazy singleton — PaddleOCR is expensive to initialise (~2–3 s first call)
_ocr: Any = None


def _get_ocr() -> Any:
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR  # deferred import so startup isn't blocked
        logging.getLogger("ppocr").setLevel(logging.WARNING)
        _ocr = PaddleOCR(use_angle_cls=True, lang="en")
    return _ocr


def run_ocr(image_b64: str) -> list[dict[str, Any]]:
    """
    Run PaddleOCR on a base64-encoded image (JPEG or PNG).

    Returns a list of text blocks, each:
        {
            "text": str,
            "confidence": float,
            "bbox": [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]  # top-left clockwise
        }
    Sorted top-to-bottom by the y-coordinate of the top-left corner.
    """
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    img_np = np.array(img)

    result = _get_ocr().ocr(img_np, cls=True)

    blocks: list[dict[str, Any]] = []
    if result and result[0]:
        for line in result[0]:
            bbox, (text, confidence) = line
            blocks.append(
                {
                    "text": text.strip(),
                    "confidence": round(float(confidence), 4),
                    "bbox": bbox,
                }
            )

    blocks.sort(key=lambda b: b["bbox"][0][1])
    logger.info("PaddleOCR returned %d text blocks", len(blocks))
    return blocks
