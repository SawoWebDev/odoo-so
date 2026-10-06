"""Putting label PDFs together, and keeping a copy of what was printed."""
from __future__ import annotations

import hashlib
import io
import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..storage import _root
from .kinds import image_to_pdf, is_image


class TooLarge(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def assemble(parts: list[tuple[Path, int]], max_bytes: int) -> bytes:
    """One PDF with every page of every file, each repeated `copies` times, in the given order."""
    for p, _ in parts:
        if p.stat().st_size > max_bytes:
            raise TooLarge(f"{p.name} is larger than {max_bytes // (1024 * 1024)} MB and cannot be combined; "
                           "print it on its own with 1 copy")
    w = PdfWriter()
    readers: dict[Path, PdfReader] = {}
    for p, copies in parts:
        r = readers.get(p) or readers.setdefault(p, PdfReader(io.BytesIO(image_to_pdf(p))) if is_image(p) else PdfReader(str(p)))
        for _ in range(max(1, copies)):
            for page in r.pages:
                w.add_page(page)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


# ---- snapshot: a copy of every printed file, by hash ---------------------------------------------------------------

def _store_dir() -> Path:
    d = _root() / "label_store"
    d.mkdir(parents=True, exist_ok=True)
    return d


def snapshot_file(path: Path, max_bytes: int) -> tuple[str | None, int]:
    """Copy the file into the app's own storage (deduplicated by content). -> (sha256 or None if too large, size)."""
    size = path.stat().st_size
    if size > max_bytes:
        return None, size
    sha = sha256_file(path)
    dest = _store_dir() / f"{sha}.pdf"
    if not dest.exists():
        if is_image(path):  # kept as the PDF it prints as, so a reprint is identical
            dest.write_bytes(image_to_pdf(path))
        else:
            shutil.copyfile(path, dest)
    return sha, size


def snapshot_path(sha: str) -> Path | None:
    if not sha or not all(c in "0123456789abcdef" for c in sha):
        return None
    p = _store_dir() / f"{sha}.pdf"
    return p if p.is_file() else None
