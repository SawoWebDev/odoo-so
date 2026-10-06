"""Barcode / QR rendering. EAN-13 for valid product barcodes, Code128 otherwise, QR on request."""
from __future__ import annotations

import io
import re

import barcode
import qrcode
import qrcode.image.svg
from barcode.writer import ImageWriter, SVGWriter

_SVG_OPTS = {"module_width": 0.3, "module_height": 14.0, "font_size": 9, "text_distance": 3.5, "quiet_zone": 2.0,
             "write_text": True}


def ean13_check_digit(first12: str) -> int:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return (10 - total % 10) % 10


def classify(value: str) -> tuple[str, str, str | None]:
    """-> (symbology, payload, warning). symbology is 'ean13' or 'code128'."""
    v = (value or "").strip()
    if v.isdigit() and len(v) in (12, 13):
        if len(v) == 13 and ean13_check_digit(v[:12]) != int(v[12]):
            return "code128", v, f"'{v}' is not a valid EAN-13 (check digit); printed as Code 128"
        return "ean13", v[:12], None
    return "code128", v, None


MM_PX = 96 / 25.4  # CSS pixels per millimetre


def _fit_svg(svg: str) -> str:
    """Make the SVG scale to its container.

    python-barcode writes width/height AND every coordinate in `mm`. Replace the physical size with a viewBox in
    CSS px (1 mm = 3.78 px, which is how the mm coordinates are interpreted) and 100% sizing.
    """
    svg = svg[svg.index("<svg"):]
    m = re.search(r'<svg[^>]*?width="([\d.]+)mm"[^>]*?height="([\d.]+)mm"', svg, re.S)
    if m:
        w, h = float(m.group(1)) * MM_PX, float(m.group(2)) * MM_PX
        svg = re.sub(r'(<svg[^>]*?)width="[\d.]+mm"', r"\1", svg, count=1, flags=re.S)
        svg = re.sub(r'(<svg[^>]*?)height="[\d.]+mm"', r"\1", svg, count=1, flags=re.S)
        svg = svg.replace("<svg", f'<svg viewBox="0 0 {w:.2f} {h:.2f}" width="100%" height="100%" '
                                  'preserveAspectRatio="xMidYMid meet"', 1)
    return svg


def barcode_svg(value: str) -> tuple[str, str | None]:
    kind, payload, warn = classify(value)
    if not payload:
        return "", None
    bc = barcode.get(kind, payload, writer=SVGWriter())
    return _fit_svg(bc.render(_SVG_OPTS).decode("utf-8")), warn


def barcode_png(value: str) -> tuple[bytes, str | None]:
    kind, payload, warn = classify(value)
    if not payload:
        return b"", None
    bc = barcode.get(kind, payload, writer=ImageWriter())
    buf = io.BytesIO()
    bc.write(buf, {"module_width": 0.3, "module_height": 14.0, "quiet_zone": 2.0, "write_text": False, "dpi": 300})
    return buf.getvalue(), warn


def qr_svg(value: str) -> str:
    if not value:
        return ""
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(value)
    qr.make(fit=True)
    svg = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).to_string().decode("utf-8")
    svg = svg[svg.index("<svg"):]
    m = re.search(r'width="([\d.]+)mm" height="([\d.]+)mm"', svg)
    if m:
        svg = svg.replace(m.group(0), f'viewBox="0 0 {m.group(1)} {m.group(2)}" width="100%" height="100%"', 1)
    return svg


def qr_png(value: str) -> bytes:
    if not value:
        return b""
    img = qrcode.make(value, border=1, box_size=10)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
