"""Values -> bytes. One entry point for every template format (guideline sections 7, 10)."""
from __future__ import annotations

import socket
from dataclasses import dataclass, field

from ..layout.sheet import LayoutOptions, impose, merge_native
from . import engine
from .bundle import Bundle
from .docx_render import docx_to_pdf
from .html_pdf import html_pages_to_pdfs
from .overlay import overlay_to_pdf


@dataclass
class RenderOutput:
    content: bytes
    mimetype: str
    ext: str
    warnings: list[str] = field(default_factory=list)
    label_count: int = 0
    info: dict = field(default_factory=dict)


def render_labels(bundle: Bundle, size: str, orientation: str, label_values: list[dict[str, dict]], *,
                  copies: int = 1, layout: dict | None = None) -> RenderOutput:
    """`label_values` is one {placeholder: value} dict per label. Reprints pass the stored snapshot here."""
    opts = LayoutOptions.from_dict(layout)
    copies = max(1, min(int(copies), 500))
    warnings: list[str] = []

    if bundle.format == "zpl":
        src = bundle.files[bundle.main].decode("utf-8", "replace")
        parts = []
        for vals in label_values:
            txt, w = engine.render(src, vals, mode="zpl")
            warnings += w
            parts.append(txt.strip())
        text = "\n".join(p for p in parts for _ in range(copies)) + "\n"
        return RenderOutput(text.encode("utf-8"), "text/plain; charset=utf-8", "zpl", warnings,
                            len(label_values) * copies, {"sheets": 0})

    if bundle.format == "html":
        src = bundle.files[bundle.main].decode("utf-8")
        src = engine.inline_assets(engine.inline_bundle_css(src, bundle.files), bundle.files)
        pages = []
        for vals in label_values:
            html, w = engine.render(src, vals, bundle.files, mode="html")
            warnings += w
            pages.append(html)
        pdfs, report = html_pages_to_pdfs(pages, size, orientation)
        if report.blocked_requests:
            warnings.append(f"{len(report.blocked_requests)} external resource request(s) were blocked")
    elif bundle.format == "docx":
        pdfs = [_first_page(docx_to_pdf(bundle.files[bundle.main], vals)) for vals in label_values]
    elif bundle.format == "pdf_overlay":
        pdfs = []
        for vals in label_values:
            pdf, w = overlay_to_pdf(bundle.files, bundle.main, vals)
            warnings += w
            pdfs.append(pdf)
    else:  # pragma: no cover
        raise ValueError(f"Unsupported template format {bundle.format}")

    expanded = [p for p in pdfs for _ in range(copies)]  # same bytes object per copy: parsed once
    pdf, lw, info = impose(expanded, opts)
    warnings += lw
    return RenderOutput(pdf, "application/pdf", "pdf", list(dict.fromkeys(warnings)), len(expanded), info)


def _first_page(pdf: bytes) -> bytes:
    import io

    from pypdf import PdfReader, PdfWriter

    r = PdfReader(io.BytesIO(pdf))
    if len(r.pages) == 1:
        return pdf
    w = PdfWriter()
    w.add_page(r.pages[0])
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def send_zpl(host_port: str, data: bytes, timeout: float = 5.0) -> None:
    """Raw TCP (port 9100) to a network label printer. host_port like '192.168.1.50:9100'."""
    host, _, port = host_port.partition(":")
    with socket.create_connection((host, int(port or 9100)), timeout=timeout) as s:
        s.sendall(data)


__all__ = ["RenderOutput", "render_labels", "send_zpl", "merge_native"]
