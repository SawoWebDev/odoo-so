"""DOCX templates: docxtpl in a Jinja *sandbox*, then LibreOffice headless -> PDF (guideline 7.2)."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile

from docxtpl import DocxTemplate
from jinja2.sandbox import SandboxedEnvironment

from ..config import get_settings
from .errors import TemplateRenderError


def _nest(flat: dict[str, str]) -> dict:
    """{'line.product.name': 'X'} -> {'line': {'product': {'name': 'X'}}} so Word can use dotted names."""
    root: dict = {}
    for k, v in flat.items():
        node = root
        parts = k.split(".")
        for p in parts[:-1]:
            nxt = node.get(p)
            if not isinstance(nxt, dict):
                nxt = node[p] = {}
            node = nxt
        node[parts[-1]] = v
    return root


def docx_to_pdf(template_bytes: bytes, values: dict[str, dict]) -> bytes:
    flat = {k: ("" if v.get("display") is None else str(v["display"])) for k, v in values.items()}
    for k, v in values.items():  # flags usable as {% if pefc %} in Word
        if v.get("type") == "bool":
            flat[k] = bool(v.get("raw"))
    doc = DocxTemplate(io.BytesIO(template_bytes))
    try:
        doc.render(_nest(flat), jinja_env=SandboxedEnvironment(), autoescape=True)
    except Exception as e:  # SecurityError from the sandbox, syntax errors, undefined names, ...
        raise TemplateRenderError(f"The Word template could not be rendered ({type(e).__name__}); "
                                  "only plain {{ placeholders }} and simple {% if %} blocks are allowed")
    tmp = tempfile.mkdtemp(prefix="docx_")
    try:
        src = os.path.join(tmp, "label.docx")
        doc.save(src)
        profile = os.path.join(tmp, "profile")
        cmd = ["soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--norestore", "--convert-to", "pdf",
               "--outdir", tmp, src]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=get_settings().render_timeout_seconds * 3)
        except FileNotFoundError:
            raise RuntimeError("LibreOffice (soffice) is not installed; DOCX templates need it")
        except subprocess.TimeoutExpired:
            raise RuntimeError("DOCX conversion timed out")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"DOCX conversion failed: {e.stderr[-200:].decode('utf-8', 'replace')}")
        with open(os.path.join(tmp, "label.pdf"), "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
