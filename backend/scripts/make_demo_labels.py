"""Creates a few A4 label PDFs for the demo (item codes of the mock Odoo orders).

    python -m scripts.make_demo_labels <folder>
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FILES = {
    "01 SAWO/P1/01 Individual/220-TD.pdf": "220-TD  Individual sticker",
    "01 SAWO/P1/02 Box Stickers/220-TD.pdf": "220-TD  Box sticker",
}


def make(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.rect(30, 30, A4[0] - 60, A4[1] - 60)
    c.setFont("Helvetica-Bold", 34)
    c.drawString(60, A4[1] - 160, text)
    c.setFont("Helvetica", 14)
    c.drawString(60, A4[1] - 200, "DEMO LABEL - replace with your real artwork")
    c.save()


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "demo-labels")
    for rel, text in FILES.items():
        make(root / rel, text)
    print(f"wrote {len(FILES)} demo labels to {root}")
