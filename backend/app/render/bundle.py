"""Template upload handling: type detection, safe unzip, placeholder scan (guideline 7.1 - 7.2)."""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field

from . import engine

ALLOWED_ZIP_EXT = {"html", "htm", "css", "png", "jpg", "jpeg", "gif", "svg", "webp", "woff", "woff2", "ttf", "otf",
                   "json", "pdf"}
MAX_ZIP_FILES = 200
MAX_UNZIPPED = 40 * 1024 * 1024


class UploadError(ValueError):
    pass


@dataclass
class Bundle:
    format: str  # html | docx | pdf_overlay | zpl
    main: str  # name of the primary file inside `files`
    files: dict[str, bytes]
    meta: dict = field(default_factory=dict)  # e.g. size from fields.json


def _safe_name(n: str) -> str:
    n = n.replace("\\", "/")
    if n.startswith("/") or ".." in n.split("/") or re.match(r"^[A-Za-z]:", n):
        raise UploadError(f"Unsafe path in archive: {n}")
    return n


def parse_upload(filename: str, data: bytes, max_bytes: int) -> Bundle:
    if len(data) > max_bytes:
        raise UploadError(f"File is larger than the {max_bytes // (1024 * 1024)} MB limit")
    if not data:
        raise UploadError("Empty file")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("html", "htm"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadError("HTML templates must be UTF-8")
        return Bundle("html", "template.html", {"template.html": data})
    if ext == "zpl":
        return Bundle("zpl", "template.zpl", {"template.zpl": data})
    if ext == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "word/document.xml" not in z.namelist():
                    raise UploadError("Not a valid .docx file")
        except zipfile.BadZipFile:
            raise UploadError("Not a valid .docx file")
        return Bundle("docx", "template.docx", {"template.docx": data})
    if ext == "zip":
        return _parse_zip(data)
    if ext in ("pdf", "png", "jpg", "jpeg"):
        raise UploadError("A PDF/image background needs placement data: upload a .zip containing the background "
                          "(background.pdf/.png/.jpg) and fields.json")
    raise UploadError("Unsupported file type. Use .html, .zip (html + assets, or background + fields.json), .docx or .zpl")


def _parse_zip(data: bytes) -> Bundle:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UploadError("Not a valid zip file")
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > MAX_ZIP_FILES:
        raise UploadError("Too many files in archive")
    if sum(i.file_size for i in infos) > MAX_UNZIPPED:
        raise UploadError("Archive is too large when unpacked")
    files: dict[str, bytes] = {}
    for i in infos:
        name = _safe_name(i.filename)
        if name.startswith("__MACOSX/") or name.endswith(".DS_Store"):
            continue
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED_ZIP_EXT:
            raise UploadError(f"File type .{ext} is not allowed in a template archive ({name})")
        files[name] = z.read(i)
    if "fields.json" in files:
        bg = next((n for n in files if re.fullmatch(r"background\.(pdf|png|jpe?g)", n, re.I)), None)
        if not bg:
            raise UploadError("fields.json found but no background.pdf / background.png / background.jpg")
        try:
            spec = json.loads(files["fields.json"])
            assert isinstance(spec.get("fields"), list)
        except Exception:
            raise UploadError('fields.json must be {"size": "A6", "fields": [...]}')
        return Bundle("pdf_overlay", bg, files, {"size": spec.get("size")})
    htmls = [n for n in files if n.lower().endswith((".html", ".htm"))]
    if not htmls:
        raise UploadError("Archive has neither an HTML file nor fields.json + background")
    main = "index.html" if "index.html" in files else sorted(htmls)[0]
    return Bundle("html", main, files)


# ---- placeholder scan ---------------------------------------------------------------------------

def scan_bundle(b: Bundle) -> dict:
    """-> {'placeholders': {name: {kinds, overflow, max, optional}}, 'assets_missing': [...], 'findings': [...]}"""
    findings: list[str] = []
    missing: list[str] = []
    if b.format == "html":
        src = b.files[b.main].decode("utf-8")
        ph, assets = engine.scan(src)
        _, findings = engine.sanitize_html(src)
        missing = [a for a in assets if a not in b.files]
    elif b.format == "zpl":
        ph, _ = engine.scan(b.files[b.main].decode("utf-8", "replace"))
    elif b.format == "docx":
        ph = _scan_docx(b.files[b.main])
    elif b.format == "pdf_overlay":
        spec = json.loads(b.files["fields.json"])
        ph = {}
        for f in spec["fields"]:
            name = f.get("placeholder")
            if name:
                e = ph.setdefault(name, {"kinds": [], "overflow": f.get("overflow"), "max": None, "optional": bool(f.get("optional"))})
                kind = f.get("kind", "text")
                if kind not in e["kinds"]:
                    e["kinds"].append(kind)
    else:  # pragma: no cover
        ph = {}
    return {"placeholders": ph, "assets_missing": missing, "findings": findings}


def _scan_docx(data: bytes) -> dict[str, dict]:
    ph: dict[str, dict] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if re.fullmatch(r"word/(document|header\d*|footer\d*)\.xml", name):
                xml = z.read(name).decode("utf-8", "replace")
                # Word splits text into runs; strip tags so '{{ so_number }}' is contiguous again.
                text = re.sub(r"<[^>]+>", "", xml)
                for m in re.finditer(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}", text):
                    ph.setdefault(m.group(1), {"kinds": ["text"], "overflow": None, "max": None, "optional": False})
    return ph
