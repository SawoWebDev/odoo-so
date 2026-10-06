"""Untrusted HTML -> PDF in a locked-down Chromium (guideline rule 5, section 7.5).

Layers, so that no single failure is enough:
  1. template is sanitised (scripts, handlers, external URLs, unsafe tags removed);
  2. a Content-Security-Policy meta blocks scripts and every non-data: resource;
  3. the browser context runs with JavaScript DISABLED, offline, service workers blocked;
  4. every request is intercepted and aborted unless it is data: / about:blank (blocked URLs are reported);
  5. a hard timeout, a fresh profile per render, no extensions, no downloads.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import get_settings
from .engine import sanitize_html
from .sizes import parse_size

CSP = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; "
       "script-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")

BASE_CSS = """
html,body{margin:0;padding:0}
.ov-wrap{overflow-wrap:anywhere;word-break:break-word;hyphens:auto}
.ov-shrink{display:inline-block;max-width:100%;overflow-wrap:anywhere}
.ph-image{display:block}
svg{max-width:100%;max-height:100%}
"""


@dataclass
class RenderReport:
    blocked_requests: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)


def wrap_document(body_html: str, width_mm: float, height_mm: float, *, csp: bool = True) -> str:
    """Insert CSP, base CSS and @page size. Works for full documents and fragments."""
    head_extra = (f'<meta charset="utf-8">'
                  + (f'<meta http-equiv="Content-Security-Policy" content="{CSP}">' if csp else "")
                  + f"<style>@page{{size:{width_mm}mm {height_mm}mm;margin:0}}{BASE_CSS}</style>")
    low = body_html.lower()
    if "<head" in low:
        i = low.index("<head")
        j = body_html.index(">", i) + 1
        return body_html[:j] + head_extra + body_html[j:]
    if "<html" in low:
        i = low.index("<html")
        j = body_html.index(">", i) + 1
        return body_html[:j] + f"<head>{head_extra}</head>" + body_html[j:]
    return f"<!doctype html><html><head>{head_extra}</head><body>{body_html}</body></html>"


def html_pages_to_pdfs(pages_html: list[str], size: str, orientation: str = "portrait", *, sanitize: bool = True,
                       csp: bool = True, javascript: bool = False) -> tuple[list[bytes], RenderReport]:
    """Render each HTML string to a single-label PDF using ONE browser launch.

    `sanitize`, `csp` and `javascript` exist so tests can switch individual defence layers off and prove the
    remaining ones still hold. Production code never overrides them.
    """
    from playwright.sync_api import sync_playwright

    settings = get_settings()
    w_mm, h_mm = parse_size(size, orientation)
    timeout_ms = settings.render_timeout_seconds * 1000
    report = RenderReport()
    pdfs: list[bytes] = []

    def handler(route):
        url = route.request.url
        if url.startswith("data:") or url == "about:blank":
            route.continue_()
        else:
            report.blocked_requests.append(url)
            route.abort()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--disable-extensions",
                  "--disable-background-networking", "--disable-sync", "--no-first-run", "--mute-audio"],
        )
        try:
            for raw in pages_html:
                src = raw
                if sanitize:
                    src, findings = sanitize_html(src)
                    report.findings += [f for f in findings if f not in report.findings]
                doc = wrap_document(src, w_mm, h_mm, csp=csp)
                context = browser.new_context(java_script_enabled=javascript, offline=True, accept_downloads=False,
                                              service_workers="block", bypass_csp=False)
                try:
                    context.set_default_timeout(timeout_ms)
                    context.route("**/*", handler)
                    page = context.new_page()
                    page.set_content(doc, wait_until="load", timeout=timeout_ms)
                    pdfs.append(page.pdf(width=f"{w_mm}mm", height=f"{h_mm}mm", print_background=True,
                                         margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                                         prefer_css_page_size=False, page_ranges="1"))
                finally:
                    context.close()
        finally:
            browser.close()
    return pdfs, report
