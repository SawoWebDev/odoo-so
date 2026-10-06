import io
import shutil

import pytest
from pypdf import PdfReader


def pdf_text(content: bytes) -> str:
    r = PdfReader(io.BytesIO(content))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def squash(s: str) -> str:
    return " ".join(s.split())


def page_count(content: bytes) -> int:
    return len(PdfReader(io.BytesIO(content)).pages)


def sawo_id(api) -> int:
    return next(t for t in api.get("/api/templates").json() if t["name"].startswith("SAWO"))["id"]


def body_for(api, template_id, *, line_id=11, so="S00123", **extra):
    """A render request exactly as the UI sends it: all fields of the chosen line + the SO header."""
    from tests.conftest import select_line

    public = api.get(f"/api/so/{so}").json()
    body = {"so": so, "template_id": template_id, "selection": select_line(public, line_id),
            "options": {"calc_mode": 1, "pefc": True, "logo": False}, "copies": 1}
    body.update(extra)
    return body


_chromium = None


def chromium_available() -> bool:
    global _chromium
    if _chromium is None:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                p.chromium.launch(args=["--no-sandbox"]).close()
            _chromium = True
        except Exception:
            _chromium = False
    return _chromium


@pytest.fixture
def chromium():
    if not chromium_available():
        pytest.skip("Playwright Chromium is not available here (it is inside the backend Docker image)")


@pytest.fixture
def soffice():
    if not shutil.which("soffice"):
        pytest.skip("LibreOffice is not available here (it is inside the backend Docker image)")
