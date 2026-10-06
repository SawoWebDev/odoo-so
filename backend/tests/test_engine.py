"""Template engine, placeholder scan, overflow rules, barcodes, sanitiser (acceptance test 6 - structure part)."""
from app.render import engine
from app.render.barcodes import barcode_svg, classify, ean13_check_digit


def val(display, raw=None, type_="text", **kw):
    return {"display": display, "raw": raw if raw is not None else display, "type": type_, **kw}


def test_scan_finds_placeholders_options_and_flags():
    src = ("{{so_number}} {{line.product.name|shrink|max=40}} {{barcode:barcode}} {{image:photo|optional}} "
           "{{#if pefc}}x{{else}}y{{/if}} {{asset:assets/logo.png}}")
    ph, assets = engine.scan(src)
    assert set(ph) == {"so_number", "line.product.name", "barcode", "photo", "pefc"}
    assert ph["line.product.name"]["overflow"] == "shrink" and ph["line.product.name"]["max"] == 40
    assert ph["barcode"]["kinds"] == ["barcode"] and ph["photo"]["optional"] is True
    assert ph["pefc"]["optional"] is True and ph["pefc"]["kinds"] == ["flag"]  # flags never block activation
    assert assets == ["assets/logo.png"]


def test_text_is_html_escaped():
    out, _ = engine.render("<b>{{x}}</b>", {"x": val('<script>alert(1)</script> & "q"')})
    assert "<script>" not in out and "&lt;script&gt;" in out and "&amp;" in out


def test_missing_placeholder_renders_empty():
    out, _ = engine.render("[{{nope}}]", {})
    assert "[<span" in out and "></span>]" in out.replace(" ", "")


def test_if_else_unless():
    src = "{{#if a}}A{{else}}notA{{/if}}|{{#unless a}}U{{/unless}}|{{#if b}}B{{/if}}"
    assert engine.render(src, {"a": val("YES", True, "bool"), "b": val("")})[0] == "A||"
    assert engine.render(src, {"a": val("NO", False, "bool"), "b": val("x")})[0] == "notA|U|B"


def test_nested_if():
    src = "{{#if a}}1{{#if b}}2{{else}}3{{/if}}4{{else}}5{{/if}}"
    t = val("y", True, "bool")
    f = val("n", False, "bool")
    assert engine.render(src, {"a": t, "b": t})[0] == "124"
    assert engine.render(src, {"a": t, "b": f})[0] == "134"
    assert engine.render(src, {"a": f, "b": t})[0] == "5"


LONG = "Thermometer Cut Corner Square 140x140mm, Cedar with extra long description that keeps going " * 2


def test_shrink_reduces_font_for_long_text_but_never_below_floor():
    out, _ = engine.render("{{x|shrink|max=40}}", {"x": val(LONG)})
    pct = int(out.split("font-size:")[1].split("%")[0])
    assert engine.MIN_SHRINK_PCT <= pct < 100
    short, _ = engine.render("{{x|shrink|max=40}}", {"x": val("Short name")})
    assert "font-size" not in short


def test_wrap_keeps_full_text_and_marks_it_wrappable():
    out, _ = engine.render("{{x|wrap}}", {"x": val(LONG)})
    assert 'class="ov-wrap"' in out and "Cedar with extra long" in out


def test_truncate_adds_ellipsis():
    out, _ = engine.render("{{x|truncate|max=10}}", {"x": val("0123456789ABCDEF")})
    assert out == "012345678…"


def test_mapping_overflow_rule_is_used_when_token_has_none():
    out, _ = engine.render("{{x}}", {"x": val(LONG, overflow="shrink")})
    assert "ov-shrink" in out


def test_description_comes_from_odoo_so_no_missing_space_typos():
    name = "Thermometer Cut Corner Square 140x140mm, Cedar"
    out, _ = engine.render("{{d}}", {"d": val(name)})
    assert "Cut Corner Square" in out and "CornerSquare" not in out


def test_barcode_ean13_and_fallback():
    assert ean13_check_digit("590123412345") == 7
    assert classify("5901234123457") == ("ean13", "590123412345", None)
    kind, payload, warn = classify("5901234123458")  # wrong check digit
    assert kind == "code128" and "not a valid EAN-13" in warn
    assert classify("ABC-123")[0] == "code128"
    svg, w = barcode_svg("5901234123457")
    assert svg.startswith("<svg") and "viewBox" in svg and w is None
    assert barcode_svg("") == ("", None)


def test_barcode_and_qr_and_image_render_inline_svg_and_data_uri():
    tiny_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    out, warns = engine.render("{{barcode:b}}|{{qr:q}}|{{image:i}}|{{imgsrc:i}}",
                               {"b": val("5901234123457"), "q": val("https://x"), "i": val("[image]", tiny_png, "image")})
    assert out.count("<svg") == 2 and "data:image/png;base64," in out and "<img" in out and not warns


def test_assets_are_inlined_as_data_uris():
    files = {"assets/logo.png": b"\x89PNG", "t.html": b""}
    out = engine.inline_assets('<img src="assets/logo.png">', files)
    assert out.startswith('<img src="data:image/png;base64,')
    out2, _ = engine.render("{{asset:assets/logo.png}}", {}, files)
    assert out2.startswith("data:image/png;base64,")


def test_sanitizer_strips_scripts_handlers_external_urls_and_unsafe_tags():
    dirty = ('<html><head><link rel="stylesheet" href="http://evil/x.css"><style>@import url(http://evil/a.css);'
             'body{background:url(http://evil/p.png)}</style></head><body onload="x()">'
             '<script>fetch("http://evil")</script><img src="https://evil/p.png" onerror="y()">'
             '<a href="javascript:alert(1)">l</a><iframe src="http://evil"></iframe><p>ok</p></body></html>')
    clean, findings = engine.sanitize_html(dirty)
    for bad in ("<script", "evil", "onload", "onerror", "javascript:", "<iframe", "<link", "@import"):
        assert bad not in clean, bad
    assert "<p>ok</p>" in clean and len(findings) >= 5


def test_zpl_mode_strips_command_characters():
    out, _ = engine.render("^FD{{x}}^FS", {"x": val("a^b~c\nd")}, mode="zpl")
    assert out == "^FDa b c d^FS"


def test_barcode_svg_viewbox_is_in_px_so_mm_coordinates_are_not_cropped():
    import re

    svg, _ = barcode_svg("5901234123457")
    root = svg.split(">", 1)[0]
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', root)
    assert vb and float(vb.group(1)) > 100  # ~32 mm wide barcode in CSS px (the bug gave 32 raw "mm" numbers)
    assert 'width="100%"' in root and 'mm"' not in root
    assert "<text" in svg  # human-readable digits are part of the SVG
