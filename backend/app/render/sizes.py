from __future__ import annotations

import re

PAPER_MM = {
    "A3": (297, 420), "A4": (210, 297), "A5": (148, 210), "A6": (105, 148), "A7": (74, 105),
}


def parse_size(size: str, orientation: str = "portrait") -> tuple[float, float]:
    """'A6' | '100x150' | '100 x 150 mm' -> (width_mm, height_mm) honouring orientation."""
    s = (size or "A6").strip().upper().replace("MM", "").strip()
    if s in PAPER_MM:
        w, h = PAPER_MM[s]
    else:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[X*]\s*(\d+(?:\.\d+)?)", s)
        if not m:
            raise ValueError(f"Unknown label size {size!r}; use A6, A5, ... or e.g. 100x150")
        w, h = float(m.group(1)), float(m.group(2))
    if not (10 <= w <= 600 and 10 <= h <= 600):
        raise ValueError("Label size must be between 10 and 600 mm")
    if orientation == "landscape" and w < h:
        w, h = h, w
    if orientation == "portrait" and w > h:
        w, h = h, w
    return float(w), float(h)


MM_TO_PT = 72 / 25.4
