"""
Barcode service: decode PDF417 from a base64-encoded image using zxing-cpp.
Canonical location for image → AAMVA string conversion.
"""
from __future__ import annotations

import base64
import io
import logging

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

_READ_OPTS = dict(try_rotate=True, try_downscale=True, try_invert=True)


def decode_pdf417(image_b64: str) -> str:
    """
    Decode the first PDF417 barcode found in the image.
    Returns raw AAMVA text, or raises ValueError if none found.
    """
    import zxingcpp

    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    img = Image.open(io.BytesIO(base64.b64decode(image_b64)))

    def _read(pil_img: Image.Image) -> str | None:
        rgb = pil_img.convert("RGB")

        # Try PDF417 specifically
        results = zxingcpp.read_barcodes(
            rgb, formats=zxingcpp.BarcodeFormat.PDF417, **_READ_OPTS
        )
        for r in results:
            logger.warning("PDF417 decoded — repr: %s", repr(r.text[:500]))
            return r.text

        # Log whatever else was found (diagnostic)
        all_results = zxingcpp.read_barcodes(rgb, **_READ_OPTS)
        for r in all_results:
            logger.warning("Non-PDF417 barcode: format=%s content=%s", r.format, repr(r.text[:120]))
        return None

    for processor in [
        lambda i: i,
        lambda i: ImageEnhance.Contrast(i.convert("L")).enhance(2.0),
        lambda i: i.filter(ImageFilter.SHARPEN),
    ]:
        text = _read(processor(img))
        if text:
            return text

    raise ValueError(
        "No PDF417 barcode found. Hold the back of the license steady "
        "and make sure the entire barcode fills the frame."
    )
