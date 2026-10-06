"""Small, safe template engine for HTML and ZPL templates (guideline 7.2).

Deliberately NOT Jinja: uploaded templates are untrusted, so only these constructs exist:
    {{name}}                 text (HTML-escaped), options: |wrap |shrink |truncate |max=NN |optional
    {{barcode:name}}         EAN-13 / Code128 as inline SVG      {{qr:name}}   QR as inline SVG
    {{image:name}}           <img> from a base64 image value      {{imgsrc:name}} data: URI only
    {{asset:file.png}}       a file bundled with the template (as data: URI)
    {{#if name}}..{{else}}..{{/if}}   and   {{#unless name}}..{{/unless}}
"""
from __future__ import annotations

import base64
import html as _html
import re
from dataclasses import dataclass, field

from .barcodes import barcode_svg, qr_svg

TOKEN = re.compile(r"\{\{\s*(.*?)\s*\}\}", re.S)
DEFAULT_MAX = 32
MIN_SHRINK_PCT = 55


@dataclass
class Tok:
    kind: str  # text barcode qr image imgsrc asset if unless else endif
    name: str = ""
    overflow: str | None = None
    max: int | None = None
    optional: bool = False


def parse_token(body: str) -> Tok:
    b = body.strip()
    if b == "else":
        return Tok("else")
    if b in ("/if", "/unless"):
        return Tok("endif")
    if b.startswith("#if "):
        return Tok("if", b[4:].strip())
    if b.startswith("#unless "):
        return Tok("unless", b[8:].strip())
    parts = [p.strip() for p in b.split("|")]
    head, opts = parts[0], parts[1:]
    kind = "text"
    for prefix in ("barcode", "qr", "image", "imgsrc", "asset"):
        if head.startswith(prefix + ":"):
            kind, head = prefix, head[len(prefix) + 1:].strip()
            break
    t = Tok(kind, head)
    for o in opts:
        if o in ("wrap", "shrink", "truncate"):
            t.overflow = o
        elif o == "optional":
            t.optional = True
        elif o.startswith("max="):
            try:
                t.max = int(o[4:])
            except ValueError:
                pass
    return t


def scan(src: str) -> tuple[dict[str, dict], list[str]]:
    """-> ({placeholder: {kinds, overflow, max, optional}}, [asset names]). Control tags are not placeholders."""
    ph: dict[str, dict] = {}
    assets: list[str] = []
    for m in TOKEN.finditer(src):
        t = parse_token(m.group(1))
        if t.kind in ("else", "endif") or not t.name:
            continue
        if t.kind == "asset":
            if t.name not in assets:
                assets.append(t.name)
            continue
        e = ph.setdefault(t.name, {"kinds": [], "overflow": None, "max": None, "optional": False})
        kind = "flag" if t.kind in ("if", "unless") else t.kind
        if kind not in e["kinds"]:
            e["kinds"].append(kind)
        e["overflow"] = e["overflow"] or t.overflow
        e["max"] = e["max"] or t.max
        e["optional"] = e["optional"] or t.optional
    for e in ph.values():  # a placeholder used only as an {{#if}} flag never blocks activation
        if e["kinds"] == ["flag"]:
            e["optional"] = True
    return ph, assets


def sniff_mime(b64: str) -> str:
    h = b64[:12]
    if h.startswith("iVBOR"):
        return "image/png"
    if h.startswith("/9j/"):
        return "image/jpeg"
    if h.startswith("R0lGOD"):
        return "image/gif"
    if h.startswith("UklGR"):
        return "image/webp"
    if h.startswith("PHN2Zy") or h.startswith("PD94bW"):
        return "image/svg+xml"
    return "image/jpeg"


def data_uri(raw: bytes | str, mime: str | None = None) -> str:
    b64 = raw if isinstance(raw, str) else base64.b64encode(raw).decode()
    return f"data:{mime or sniff_mime(b64)};base64,{b64}"


def truthy(v: dict | None) -> bool:
    if not v:
        return False
    if v.get("type") == "bool":
        return bool(v.get("raw"))
    return bool(v.get("display"))


def _fit_text(text: str, rule: str, mx: int, escape, is_html: bool) -> str:
    """Overflow rules (guideline 7.4). Shrink is computed here, not by JS, because template scripts are disabled."""
    if rule == "truncate" and len(text) > mx:
        return escape(text[: max(1, mx - 1)].rstrip() + "…")
    if not is_html:
        return escape(text)
    if rule == "shrink":
        # Shrinking has a floor (readability). Past what fits at the floor size, cut with a visible ellipsis
        # rather than letting the box clip text silently. Capacity grows with the square of the shrink factor.
        cap = int(mx * (100 / MIN_SHRINK_PCT) ** 2)
        if len(text) > cap:
            text = text[: cap - 1].rstrip() + "…"
    if rule == "shrink" and len(text) > mx:
        pct = max(MIN_SHRINK_PCT, int(100 * mx / len(text)))
        return f'<span class="ov-shrink" style="font-size:{pct}%;line-height:1.1">{escape(text)}</span>'
    return f'<span class="ov-wrap">{escape(text)}</span>'


def zpl_escape(text: str) -> str:
    # ^ and ~ are ZPL command introducers; control characters never belong in a field.
    return re.sub(r"[\^~\x00-\x1f]", " ", text)


def render(src: str, values: dict[str, dict], assets: dict[str, bytes] | None = None, *,
           mode: str = "html") -> tuple[str, list[str]]:
    """Render `src` with placeholder values. Returns (output, warnings)."""
    assets = assets or {}
    is_html = mode == "html"
    esc = (lambda s: _html.escape(s, quote=True)) if is_html else zpl_escape
    out: list[str] = []
    warnings: list[str] = []
    stack: list[tuple[bool, bool]] = []
    active = True
    pos = 0
    for m in TOKEN.finditer(src):
        if active:
            out.append(src[pos:m.start()])
        pos = m.end()
        t = parse_token(m.group(1))
        if t.kind in ("if", "unless"):
            cond = truthy(values.get(t.name))
            cond = cond if t.kind == "if" else not cond
            stack.append((active, cond))
            active = active and cond
            continue
        if t.kind == "else":
            if stack:
                parent, cond = stack[-1]
                active = parent and not cond
            continue
        if t.kind == "endif":
            if stack:
                active, _ = stack.pop()
            continue
        if not active:
            continue
        out.append(_value(t, values, assets, is_html, esc, warnings))
    if active:
        out.append(src[pos:])
    return "".join(out), warnings


def _value(t: Tok, values, assets, is_html, esc, warnings) -> str:
    if t.kind == "asset":
        data = assets.get(t.name)
        if data is None:
            warnings.append(f"asset '{t.name}' not found in template bundle")
            return ""
        return data_uri(data, _asset_mime(t.name))
    v = values.get(t.name) or {"display": "", "raw": None, "type": "text"}
    text = "" if v.get("display") is None else str(v["display"])
    if t.kind == "text":
        rule = t.overflow or v.get("overflow") or "wrap"
        return _fit_text(text, rule, t.max or v.get("max") or DEFAULT_MAX, esc, is_html)
    raw = v.get("raw")
    if t.kind == "barcode":
        code = str(raw or text or "")
        if not is_html:
            return zpl_escape(code)
        svg, warn = barcode_svg(code)
        if warn:
            warnings.append(warn)
        return svg
    if t.kind == "qr":
        return qr_svg(str(raw or text or "")) if is_html else zpl_escape(str(raw or text or ""))
    if t.kind in ("image", "imgsrc"):
        b64 = raw if isinstance(raw, str) else ""
        if not b64:
            return ""
        uri = data_uri(b64)
        if t.kind == "imgsrc":
            return uri
        return f'<img class="ph-image" src="{uri}" alt="" style="max-width:100%;max-height:100%;object-fit:contain">'
    return ""


def _asset_mime(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower()
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "svg": "image/svg+xml",
            "webp": "image/webp", "woff": "font/woff", "woff2": "font/woff2", "ttf": "font/ttf",
            "otf": "font/otf", "css": "text/css"}.get(ext, "application/octet-stream")


# ---- HTML safety (defence in depth; Chromium itself runs with JS off, network off, CSP) -----------------------

_SCRIPT = re.compile(r"<script\b.*?</script\s*>|<script\b[^>]*>", re.I | re.S)
_BAD_TAGS = re.compile(r"</?(?:iframe|object|embed|applet|base|frame|frameset|form|meta|link)\b[^>]*>", re.I)
_ON_ATTR = re.compile(r"""\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_JS_URL = re.compile(r"(?:javascript|vbscript)\s*:", re.I)
_EXT_ATTR = re.compile(r"""(\b(?:src|href|poster|data|action|srcset|xlink:href)\s*=\s*)(["']?)\s*(?:https?:)?//[^"'\s>]+\2""", re.I)
_EXT_CSS = re.compile(r"url\(\s*[\"']?\s*(?:https?:)?//[^)]*\)", re.I)
_IMPORT = re.compile(r"@import\b[^;]*;?", re.I)


def inline_bundle_css(src: str, files: dict[str, bytes]) -> str:
    """Replace <link rel=stylesheet href=bundled.css> with an inline <style> (links are stripped for safety)."""
    def repl(m):
        href = re.search(r"""href\s*=\s*["']?([^"'\s>]+)""", m.group(0), re.I)
        if href and href.group(1) in files and "stylesheet" in m.group(0).lower():
            return "<style>" + files[href.group(1)].decode("utf-8", "replace") + "</style>"
        return m.group(0)
    return re.sub(r"<link\b[^>]*>", repl, src, flags=re.I)


def inline_assets(src: str, files: dict[str, bytes]) -> str:
    """Rewrite references to bundled files (e.g. src="assets/logo.png") into data: URIs."""
    for name in sorted(files, key=len, reverse=True):
        ext = name.rsplit(".", 1)[-1].lower()
        if ext in ("html", "htm", "css", "json"):
            continue
        if name in src:
            src = src.replace(name, data_uri(files[name], _asset_mime(name)))
    return src


def sanitize_html(src: str) -> tuple[str, list[str]]:
    findings: list[str] = []

    def sub(pattern, repl, text, msg):
        new, n = pattern.subn(repl, text)
        if n:
            findings.append(msg)
        return new

    src = sub(_SCRIPT, "", src, "script removed")
    src = sub(_BAD_TAGS, "", src, "unsafe tag removed (iframe/object/embed/base/form/meta/link)")
    src = sub(_ON_ATTR, "", src, "inline event handler removed")
    src = sub(_JS_URL, "blocked:", src, "javascript: URL neutralised")
    src = sub(_EXT_ATTR, lambda m: f'{m.group(1)}{m.group(2)}{m.group(2)}', src, "external resource removed")
    src = sub(_EXT_CSS, "none", src, "external CSS url() removed")
    src = sub(_IMPORT, "", src, "CSS @import removed")
    return src, findings
