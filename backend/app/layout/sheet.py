"""Sheet imposition (guideline section 10): one rendered label PDF is placed on 1-up / 2-up / 4-up A4 sheets.

Applied AFTER rendering so one label design works in every layout. `start_slot` lets a partly used sheet be
reused; a partial last sheet simply leaves its remaining slots empty.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas

from ..render.sizes import MM_TO_PT, parse_size

GRID = {"1up": (1, 1), "2up": (2, 1), "4up": (2, 2)}  # (columns, rows)
KINDS = ("native", *GRID)


@dataclass
class LayoutOptions:
    kind: str = "native"  # native = no imposition, pages stay label-sized
    sheet: str = "A4"
    orientation: str = "portrait"
    crop_marks: bool = False
    margin_mm: float = 0.0
    gap_mm: float = 0.0
    start_slot: int = 0

    @classmethod
    def from_dict(cls, d: dict | None) -> "LayoutOptions":
        d = d or {}
        o = cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d and d[k] is not None})
        if o.kind not in KINDS:
            raise ValueError(f"layout kind must be one of {', '.join(KINDS)}")
        if not (0 <= o.margin_mm <= 40 and 0 <= o.gap_mm <= 40):
            raise ValueError("margin and gap must be between 0 and 40 mm")
        if o.kind != "native":
            per = GRID[o.kind][0] * GRID[o.kind][1]
            if not (0 <= int(o.start_slot) < per):
                raise ValueError(f"start_slot must be between 0 and {per - 1} for {o.kind}")
        return o

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @property
    def slots_per_sheet(self) -> int:
        return 1 if self.kind == "native" else GRID[self.kind][0] * GRID[self.kind][1]


def merge_native(label_pdfs: list[bytes]) -> bytes:
    w = PdfWriter()
    cache: dict[int, PdfReader] = {}
    for b in label_pdfs:
        r = cache.setdefault(id(b), PdfReader(io.BytesIO(b)))
        w.add_page(r.pages[0])
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def impose(label_pdfs: list[bytes], opts: LayoutOptions) -> tuple[bytes, list[str], dict]:
    """-> (pdf bytes, warnings, info{sheets, slots_per_sheet, empty_slots})."""
    if opts.kind == "native":
        return merge_native(label_pdfs), [], {"sheets": len(label_pdfs), "slots_per_sheet": 1, "empty_slots": 0}
    cols, rows = GRID[opts.kind]
    per = cols * rows
    sw_mm, sh_mm = parse_size(opts.sheet, opts.orientation)
    sw, sh = sw_mm * MM_TO_PT, sh_mm * MM_TO_PT
    m, g = opts.margin_mm * MM_TO_PT, opts.gap_mm * MM_TO_PT
    slot_w = (sw - 2 * m - g * (cols - 1)) / cols
    slot_h = (sh - 2 * m - g * (rows - 1)) / rows
    start = int(opts.start_slot)
    total_slots = start + len(label_pdfs)
    n_sheets = max(1, -(-total_slots // per))
    sheets = [PageObject.create_blank_page(width=sw, height=sh) for _ in range(n_sheets)]
    rects: list[list[tuple[float, float, float, float]]] = [[] for _ in range(n_sheets)]
    cache: dict[int, PdfReader] = {}
    warnings: list[str] = []
    min_scale = 1.0
    for i, b in enumerate(label_pdfs):
        slot = start + i
        sheet_i, s = divmod(slot, per)
        row, col = divmod(s, cols)
        src = cache.setdefault(id(b), PdfReader(io.BytesIO(b))).pages[0]
        lw, lh = float(src.mediabox.width), float(src.mediabox.height)
        scale = min(1.0, slot_w / lw, slot_h / lh)
        min_scale = min(min_scale, scale)
        x = m + col * (slot_w + g) + (slot_w - lw * scale) / 2
        y_top = m + row * (slot_h + g) + (slot_h - lh * scale) / 2
        y = sh - y_top - lh * scale
        sheets[sheet_i].merge_transformed_page(src, Transformation().scale(scale).translate(x, y))
        rects[sheet_i].append((x, y, lw * scale, lh * scale))
    if min_scale < 0.999:
        warnings.append(f"Label is larger than the {opts.kind} slot and was scaled to {round(min_scale * 100)}% to fit")
    if opts.crop_marks:
        for sheet, rs in zip(sheets, rects):
            sheet.merge_page(_marks_page(sw, sh, rs))
    out = PdfWriter()
    for s in sheets:
        out.add_page(s)
    buf = io.BytesIO()
    out.write(buf)
    return buf.getvalue(), warnings, {"sheets": n_sheets, "slots_per_sheet": per,
                                      "empty_slots": n_sheets * per - total_slots}


def _marks_page(sw: float, sh: float, rects) -> PageObject:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(sw, sh))
    c.setLineWidth(0.4)
    tick, off = 3 * MM_TO_PT, 1 * MM_TO_PT
    for x, y, w, h in rects:
        for cx, cy, dx, dy in ((x, y, -1, -1), (x + w, y, 1, -1), (x, y + h, -1, 1), (x + w, y + h, 1, 1)):
            c.line(cx + dx * off, cy, cx + dx * (off + tick), cy)
            c.line(cx, cy + dy * off, cx, cy + dy * (off + tick))
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]
