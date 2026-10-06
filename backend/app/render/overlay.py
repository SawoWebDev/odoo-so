"""PDF / image background + coordinate overlay (guideline 7.2).

fields.json:
  {"size": "A6", "orientation": "portrait",
   "fields": [
     {"placeholder": "so_number", "kind": "text", "x": 10, "y": 20, "w": 60, "h": 8,
      "size": 11, "font": "Helvetica-Bold", "align": "left", "overflow": "shrink"},
     {"placeholder": "barcode", "kind": "barcode", "x": 10, "y": 100, "w": 60, "h": 20},
     {"placeholder": "photo", "kind": "image", "x": 10, "y": 30, "w": 60, "h": 50}]}
Units are millimetres measured from the TOP-LEFT of the label.
"""
from __future__ import annotations

import base64
import io
import json

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from .barcodes import barcode_png, qr_png
from .sizes import MM_TO_PT, parse_size

STD_FONTS = {"Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Times-Roman", "Times-Bold", "Courier", "Courier-Bold"}


def _draw_text(c: canvas.Canvas, f: dict, text: str, page_h: float) -> None:
    font = f.get("font", "Helvetica")
    font = font if font in STD_FONTS else "Helvetica"
    size = float(f.get("size", 10))
    x, y_top = f["x"] * MM_TO_PT, page_h - f["y"] * MM_TO_PT
    w = f.get("w")
    h = f.get("h")
    rule = f.get("overflow", "wrap")
    if w:
        wpt = w * MM_TO_PT
        if rule == "shrink":
            while size > 5 and c.stringWidth(text, font, size) > wpt:
                size -= 0.5
            lines = [text]
        elif rule == "truncate":
            t = text
            if c.stringWidth(t, font, size) > wpt:
                while len(t) > 1 and c.stringWidth(t + "…", font, size) > wpt:
                    t = t[:-1]
                t += "…"
            lines = [t]
        else:
            lines = simpleSplit(text, font, size, wpt)
            if h:  # keep wrapped text inside its box: shrink font until it fits
                while size > 5 and len(lines) * size * 1.15 > h * MM_TO_PT:
                    size -= 0.5
                    lines = simpleSplit(text, font, size, wpt)
    else:
        lines = [text]
    c.setFont(font, size)
    for i, line in enumerate(lines):
        yy = y_top - size - i * size * 1.15
        lw = c.stringWidth(line, font, size)
        xx = x
        if w and f.get("align") == "center":
            xx = x + (w * MM_TO_PT - lw) / 2
        elif w and f.get("align") == "right":
            xx = x + w * MM_TO_PT - lw
        c.drawString(xx, yy, line)


def _draw_image(c: canvas.Canvas, f: dict, png_or_img: bytes, page_h: float) -> None:
    if not png_or_img:
        return
    w, h = f["w"] * MM_TO_PT, f["h"] * MM_TO_PT
    x, y = f["x"] * MM_TO_PT, page_h - (f["y"] * MM_TO_PT) - h
    c.drawImage(ImageReader(io.BytesIO(png_or_img)), x, y, width=w, height=h, preserveAspectRatio=True, anchor="c", mask="auto")


def overlay_to_pdf(files: dict[str, bytes], bg_name: str, values: dict[str, dict]) -> tuple[bytes, list[str]]:
    spec = json.loads(files["fields.json"])
    w_mm, h_mm = parse_size(spec.get("size", "A6"), spec.get("orientation", "portrait"))
    pw, ph = w_mm * MM_TO_PT, h_mm * MM_TO_PT
    warnings: list[str] = []
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    is_pdf = bg_name.lower().endswith(".pdf")
    if not is_pdf:  # raster background fills the page
        c.drawImage(ImageReader(io.BytesIO(files[bg_name])), 0, 0, width=pw, height=ph)
    for f in spec["fields"]:
        v = values.get(f.get("placeholder", ""), {})
        kind = f.get("kind", "text")
        if kind == "text":
            text = str(v.get("display") or "")
            if text:
                f = {**f, "overflow": f.get("overflow") or v.get("overflow") or "wrap"}
                _draw_text(c, f, text, ph)
        elif kind == "barcode":
            png, warn = barcode_png(str(v.get("raw") or v.get("display") or ""))
            if warn:
                warnings.append(warn)
            _draw_image(c, f, png, ph)
        elif kind == "qr":
            _draw_image(c, f, qr_png(str(v.get("raw") or v.get("display") or "")), ph)
        elif kind == "image":
            b64 = v.get("raw") if isinstance(v.get("raw"), str) else ""
            if b64:
                _draw_image(c, f, base64.b64decode(b64), ph)
    c.showPage()
    c.save()
    buf.seek(0)
    overlay_page = PdfReader(buf).pages[0]
    if not is_pdf:
        out = PdfWriter()
        out.add_page(overlay_page)
    else:
        bg = PdfReader(io.BytesIO(files[bg_name])).pages[0]
        bg.scale_to(pw, ph)
        bg.merge_page(overlay_page)
        out = PdfWriter()
        out.add_page(bg)
    res = io.BytesIO()
    out.write(res)
    return res.getvalue(), warnings
