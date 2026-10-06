import io
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4


def make_pdf(path: Path, text: str, pages: int = 1, size=A4) -> bytes:
    """A small label-like PDF whose text identifies it, written to `path` (folders are created)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    for i in range(pages):
        c.setFont("Helvetica-Bold", 28)
        c.drawString(60, size[1] - 120, text if pages == 1 else f"{text} p{i + 1}")
        c.showPage()
    c.save()
    data = buf.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def pdf_text(content: bytes) -> str:
    r = PdfReader(io.BytesIO(content))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def pages_text(content: bytes) -> list[str]:
    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(content)).pages]


def page_count(content: bytes) -> int:
    return len(PdfReader(io.BytesIO(content)).pages)
