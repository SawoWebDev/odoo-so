"""Acceptance test 9: the same label prints 1-up, 2-up and 4-up; a 3-label partial sheet leaves one slot empty."""
import io

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.layout.sheet import LayoutOptions, impose
from app.render.sizes import MM_TO_PT, parse_size


def label_pdf(text: str, w_mm=105, h_mm=148) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w_mm * MM_TO_PT, h_mm * MM_TO_PT))
    c.setFont("Helvetica", 14)
    c.drawString(20, 100, text)
    c.rect(2, 2, w_mm * MM_TO_PT - 4, h_mm * MM_TO_PT - 4)
    c.showPage()
    c.save()
    return buf.getvalue()


def text_positions(page):
    """[(text, x_pt, y_pt)] in sheet coordinates (text matrix x current matrix)."""
    found = []

    def visitor(text, cm, tm, font_dict, font_size):
        if text.strip():
            a, b, c, d, e, f = cm
            x = tm[4] * a + tm[5] * c + e
            y = tm[4] * b + tm[5] * d + f
            found.append((text.strip(), round(x), round(y)))

    page.extract_text(visitor_text=visitor)
    return found


def opts(**kw):
    return LayoutOptions.from_dict(kw)


def test_native_keeps_label_sized_pages():
    pdf, w, info = impose([label_pdf("A"), label_pdf("B")], opts(kind="native"))
    r = PdfReader(io.BytesIO(pdf))
    assert len(r.pages) == 2 and round(float(r.pages[0].mediabox.width) / MM_TO_PT) == 105


def test_one_up_puts_one_label_per_a4_sheet():
    pdf, w, info = impose([label_pdf("A"), label_pdf("B")], opts(kind="1up"))
    r = PdfReader(io.BytesIO(pdf))
    assert len(r.pages) == 2 and info["slots_per_sheet"] == 1
    assert round(float(r.pages[0].mediabox.width) / MM_TO_PT) == 210


def test_two_up_and_four_up_slot_counts():
    labels = [label_pdf(f"L{i}") for i in range(5)]
    _, _, i2 = impose(labels, opts(kind="2up"))
    _, _, i4 = impose(labels, opts(kind="4up"))
    assert (i2["sheets"], i2["slots_per_sheet"]) == (3, 2)
    assert (i4["sheets"], i4["slots_per_sheet"]) == (2, 4)


def test_partial_sheet_three_labels_leave_the_last_slot_empty():
    pdf, w, info = impose([label_pdf("L1"), label_pdf("L2"), label_pdf("L3")], opts(kind="4up"))
    assert info["sheets"] == 1 and info["empty_slots"] == 1
    pos = text_positions(PdfReader(io.BytesIO(pdf)).pages[0])
    texts = sorted(t for t, _, _ in pos)
    assert texts == ["L1", "L2", "L3"]
    sheet_w = 210 * MM_TO_PT
    # slots fill row-major: L1 top-left, L2 top-right, L3 bottom-left; bottom-right stays empty
    by = {t: (x, y) for t, x, y in pos}
    assert by["L1"][0] < sheet_w / 2 and by["L2"][0] > sheet_w / 2
    assert by["L3"][0] < sheet_w / 2 and by["L3"][1] < by["L1"][1]
    assert not any(x > sheet_w / 2 and y < 297 * MM_TO_PT / 2 for _, x, y in pos)


def test_start_slot_reuses_a_partly_used_sheet():
    pdf, _, info = impose([label_pdf("L1"), label_pdf("L2")], opts(kind="4up", start_slot=2))
    pos = {t: (x, y) for t, x, y in text_positions(PdfReader(io.BytesIO(pdf)).pages[0])}
    sheet_h = 297 * MM_TO_PT
    assert pos["L1"][1] < sheet_h / 2 and pos["L2"][1] < sheet_h / 2  # both land on the bottom row
    assert info["sheets"] == 1


def test_start_slot_overflow_adds_a_sheet():
    _, _, info = impose([label_pdf("a"), label_pdf("b"), label_pdf("c")], opts(kind="4up", start_slot=3))
    assert info["sheets"] == 2


def test_same_label_in_every_layout():
    for kind in ("1up", "2up", "4up"):
        pdf, _, _ = impose([label_pdf("SAME")] * 2, opts(kind=kind))
        pages = PdfReader(io.BytesIO(pdf)).pages
        assert sum(t == "SAME" for p in pages for t, _, _ in text_positions(p)) == 2


def test_oversized_label_is_scaled_never_cropped_and_warned():
    pdf, warnings, _ = impose([label_pdf("BIG", 150, 200)], opts(kind="4up"))
    assert warnings and "scaled" in warnings[0]
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_crop_marks_are_added_as_extra_content():
    plain, _, _ = impose([label_pdf("A")], opts(kind="4up", margin_mm=10, gap_mm=5))
    marked, _, _ = impose([label_pdf("A")], opts(kind="4up", margin_mm=10, gap_mm=5, crop_marks=True))
    assert len(marked) > len(plain)


def test_invalid_layouts_are_rejected():
    with pytest.raises(ValueError):
        LayoutOptions.from_dict({"kind": "9up"})
    with pytest.raises(ValueError):
        LayoutOptions.from_dict({"kind": "4up", "start_slot": 4})
    with pytest.raises(ValueError):
        LayoutOptions.from_dict({"kind": "2up", "margin_mm": 100})


def test_parse_size():
    assert parse_size("A6") == (105, 148)
    assert parse_size("100x150") == (100, 150)
    assert parse_size("A6", "landscape") == (148, 105)
    with pytest.raises(ValueError):
        parse_size("huge")
