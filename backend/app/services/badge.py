"""
Canonical badge image generator.
All badge layout logic lives here — never inline in routes.
"""
from __future__ import annotations
import base64
import io
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# 62mm label tape at 300 dpi = 720px wide
BADGE_WIDTH = 720
PADDING = 30
ACCENT_COLOR = "#1a56db"  # blue accent bar
BG_COLOR = "#ffffff"
TEXT_COLOR = "#111111"
MUTED_COLOR = "#6b7280"
HEADER_BG = ACCENT_COLOR
HEADER_TEXT = "#ffffff"

_ASSETS = Path(__file__).parent.parent / "assets"
_STATIC = Path(__file__).parent.parent / "static"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load DejaVu Sans from system or assets, fall back to default."""
    candidates = [
        _ASSETS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def render_badge(visit: dict[str, Any]) -> Image.Image:
    """
    Render a visitor badge as a PIL Image.

    visit dict keys used:
      full_name, first_name, last_name, dob, photo_b64,
      visiting_whom, purpose, visit_date (defaults to today)
    """
    visit_date = visit.get("visit_date") or date.today().strftime("%B %d, %Y")
    full_name = visit.get("full_name") or f"{visit.get('first_name','')} {visit.get('last_name','')}".strip()
    visiting_whom = visit.get("visiting_whom", "")
    purpose = visit.get("purpose", "")

    # ── Layout constants ──────────────────────────────────────────────────────
    header_h = 80
    photo_size = 160
    photo_x = BADGE_WIDTH - PADDING - photo_size

    # Estimate total height
    total_h = header_h + PADDING + photo_size + PADDING * 2 + 60 * 3 + PADDING
    total_h = max(total_h, 460)

    img = Image.new("RGB", (BADGE_WIDTH, total_h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ── Header bar ────────────────────────────────────────────────────────────
    draw.rectangle([(0, 0), (BADGE_WIDTH, header_h)], fill=HEADER_BG)
    f_header = _font(44, bold=True)
    draw.text((PADDING, 18), "VISITOR", font=f_header, fill=HEADER_TEXT)

    # ── Date (top-right inside header) ────────────────────────────────────────
    f_small = _font(22)
    draw.text((BADGE_WIDTH - PADDING - 200, 28), visit_date, font=f_small, fill=HEADER_TEXT)

    # ── Face photo ────────────────────────────────────────────────────────────
    photo_y = header_h + PADDING
    photo_drawn = False
    if visit.get("photo_b64"):
        try:
            photo_bytes = base64.b64decode(visit["photo_b64"])
            photo_img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
            photo_img = photo_img.resize((photo_size, photo_size), Image.LANCZOS)
            img.paste(photo_img, (photo_x, photo_y))
            # thin border
            draw.rectangle(
                [(photo_x - 1, photo_y - 1), (photo_x + photo_size, photo_y + photo_size)],
                outline="#d1d5db",
                width=1,
            )
            photo_drawn = True
        except Exception:
            pass

    if not photo_drawn:
        # Placeholder box
        draw.rectangle(
            [(photo_x, photo_y), (photo_x + photo_size, photo_y + photo_size)],
            fill="#e5e7eb",
            outline="#d1d5db",
            width=1,
        )
        f_ph = _font(14)
        draw.text((photo_x + 30, photo_y + 68), "No Photo", font=f_ph, fill=MUTED_COLOR)

    # ── Name ─────────────────────────────────────────────────────────────────
    text_x = PADDING
    text_right = photo_x - PADDING
    y = header_h + PADDING + 6

    f_name = _font(48, bold=True)
    # Wrap name if too long for text area
    name_display = _fit_text(full_name, f_name, text_right - text_x)
    for line in name_display:
        draw.text((text_x, y), line, font=f_name, fill=TEXT_COLOR)
        y += 56

    y += 10

    # ── Visiting / Purpose fields ─────────────────────────────────────────────
    f_label = _font(20)
    f_value = _font(26, bold=True)

    if visiting_whom:
        draw.text((text_x, y), "VISITING", font=f_label, fill=MUTED_COLOR)
        y += 24
        for line in _fit_text(visiting_whom, f_value, text_right - text_x):
            draw.text((text_x, y), line, font=f_value, fill=TEXT_COLOR)
            y += 32
        y += 8

    if purpose:
        draw.text((text_x, y), "PURPOSE", font=f_label, fill=MUTED_COLOR)
        y += 24
        for line in _fit_text(purpose, f_value, text_right - text_x):
            draw.text((text_x, y), line, font=f_value, fill=TEXT_COLOR)
            y += 32
        y += 8

    # ── Bottom accent line ────────────────────────────────────────────────────
    draw.rectangle([(0, total_h - 8), (BADGE_WIDTH, total_h)], fill=ACCENT_COLOR)

    # ── Optional company logo ─────────────────────────────────────────────────
    logo_path = _STATIC / "logo.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            max_logo_w = 180
            ratio = min(max_logo_w / logo.width, 40 / logo.height)
            logo = logo.resize((int(logo.width * ratio), int(logo.height * ratio)), Image.LANCZOS)
            logo_x = BADGE_WIDTH - PADDING - logo.width
            logo_y = total_h - 8 - logo.height - 10
            # composite with alpha
            bg = img.crop((logo_x, logo_y, logo_x + logo.width, logo_y + logo.height)).convert("RGBA")
            bg = Image.alpha_composite(bg, logo)
            img.paste(bg.convert("RGB"), (logo_x, logo_y))
        except Exception:
            pass

    return img


def _fit_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Split text into lines that fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip() if current else word
        bbox = font.getbbox(trial)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]
