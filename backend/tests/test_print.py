"""Preview, print, print log and exact reprint of label PDFs, always fetched from their saved name and location."""
import hashlib

from app.config import get_settings
from tests.conftest import file_id, login, make_viewer
from tests.helpers import make_pdf, page_count, pages_text

IND = "01 SAWO/P1/01 Individual/220-TD.pdf"
BOX = "01 SAWO/P1/02 Box Stickers/220-TD.pdf"


def req(so="S00123", items=None, **kw):
    return {"so": so, "items": items if items is not None else [{"line_id": 11}], **kw}


def ids(api):
    return file_id(api, "220-TD.pdf", "Individual"), file_id(api, "220-TD.pdf", "Box Stickers")


def test_preview_of_one_label_returns_the_file_untouched(api):
    login(api, "bob")
    r = api.post("/api/print/preview", json=req())
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content == (api.labels / IND).read_bytes()


def test_a_specific_variant_can_be_chosen_by_its_saved_id(api):
    login(api, "bob")
    _ind, box = ids(api)
    r = api.post("/api/print/preview", json=req(items=[{"line_id": 11, "file_id": box}]))
    assert r.content == (api.labels / BOX).read_bytes()


def test_copies_and_several_lines_are_combined_in_the_order_ticked(api):
    login(api, "bob")
    ind, box = ids(api)
    api.odoo.add("sale.order.line", id=21, order_id=1, product_id=100, name="second", product_uom_qty=2.0, sequence=4,
                 display_type=False, product_uom=1)
    r = api.post("/api/print/preview", json=req(items=[{"line_id": 21, "file_id": box}, {"line_id": 11, "file_id": ind}], copies=2))
    assert r.status_code == 200 and page_count(r.content) == 4 and r.headers["x-label-count"] == "4"
    assert pages_text(r.content) == ["BOX STICKER 220-TD"] * 2 + ["INDIVIDUAL 220-TD"] * 2


def test_lines_that_cannot_be_printed_are_refused_by_the_server(api):
    login(api, "bob")
    no_pdf = api.post("/api/print/print", json=req("S00124", [{"line_id": 12}]))
    assert no_pdf.status_code == 422 and "No label PDF found for item code RS-1" in no_pdf.text
    zero = api.post("/api/print/print", json=req("S00125", [{"line_id": 15}]))
    assert zero.status_code == 422 and "Ordered quantity is 0" in zero.text
    assert api.post("/api/print/print", json=req("S00125", [{"line_id": 15}, {"line_id": 16}])).status_code == 422
    assert api.get("/api/print-jobs").json() == []  # nothing was logged


def test_bad_requests(api):
    login(api, "bob")
    setx = file_id(api, "SET-X -No BG.pdf")
    assert api.post("/api/print/print", json=req(items=[])).status_code == 422
    assert api.post("/api/print/print", json=req(items=[{"line_id": 999}])).status_code == 422
    assert api.post("/api/print/print", json=req(items=[{"line_id": 12}], so="S00123")).status_code == 422  # other order's line
    other = api.post("/api/print/print", json=req(items=[{"line_id": 11, "file_id": setx}]))
    assert other.status_code == 422 and "not a label for this item code" in other.text
    assert api.post("/api/print/print", json=req(items=[{"line_id": 11, "file_id": 99999}])).status_code == 422
    assert api.post("/api/print/print", json=req("NOPE")).status_code == 404


def test_viewers_can_preview_but_not_print_or_reprint(api):
    login(api, "carol")
    make_viewer(api, 9)
    assert api.post("/api/print/preview", json=req()).status_code == 200
    assert api.post("/api/print/print", json=req()).status_code == 403
    assert api.post("/api/print-jobs/1/reprint", json={}).status_code == 403


def test_print_logs_the_exact_files_and_keeps_a_copy(api, env):
    login(api, "bob")
    _ind, box = ids(api)
    r = api.post("/api/print/print", json=req(items=[{"line_id": 11, "file_id": box}], copies=3, printer="Office A4"))
    assert r.status_code == 200 and r.headers["x-print-job-id"] == "1"
    data = (api.labels / BOX).read_bytes()
    job = api.get("/api/print-jobs/1").json()
    assert job["so_name"] == "S00123" and job["copies"] == 3 and job["printer"] == "Office A4" and job["user_uid"] == 8
    item = job["items"][0]
    assert item["code"] == "220-TD" and item["file_id"] == box and item["line_id"] == 11
    assert item["path"].endswith("01 PRINTING FILES/" + BOX)  # where it was fetched from
    assert item["sha256"] == hashlib.sha256(data).hexdigest() and item["size"] == len(data)
    assert (env / "storage/label_store" / f"{item['sha256']}.pdf").read_bytes() == data
    assert page_count(r.content) == 3


def test_a_file_that_was_renamed_or_deleted_stops_the_print_and_turns_red(api):
    login(api, "bob")
    ind, _box = ids(api)
    (api.labels / IND).rename(api.labels / "01 SAWO/P1/01 Individual/220-TD-old.pdf")  # nobody rescanned yet
    r = api.post("/api/print/print", json=req(items=[{"line_id": 11, "file_id": ind}]))
    assert r.status_code == 409 and "renamed or deleted" in r.text and IND in r.text
    assert api.get("/api/print-jobs").json() == []  # not logged, nothing printed
    assert api.get("/api/labels/search", params={"state": "missing"}).json()["items"][0]["id"] == ind  # flagged red
    row = next(x for g in api.get("/api/so/S00123").json()["groups"] if g["id"] == "lines" for x in g["rows"])
    assert row["pdf"]["selected"] == file_id(api, "220-TD.pdf", "Box Stickers")  # the line falls back to the other PDF


def test_a_line_whose_only_file_is_gone_says_it_was_deleted_or_renamed(api):
    login(api, "bob")
    for rel in (IND, BOX):
        (api.labels / rel).unlink()
    api.post("/api/labels/rescan")
    row = next(x for g in api.get("/api/so/S00123?refresh=true").json()["groups"] if g["id"] == "lines" for x in g["rows"])
    assert row["disabled"] and row["disabled_kind"] == "no_label" and row["pdf"]["files"] == []
    assert "deleted or renamed" in row["disabled_reason"] and "220-TD.pdf" in row["disabled_reason"]
    assert api.post("/api/print/print", json=req()).status_code == 422


def test_reprint_is_identical_even_if_the_file_changes_is_renamed_or_disappears(api):
    login(api, "bob")
    ind, _box = ids(api)
    first = api.post("/api/print/print", json=req(items=[{"line_id": 11, "file_id": ind}], copies=2))
    original = first.content
    make_pdf(api.labels / IND, "EDITED AFTER PRINTING")  # the artwork is changed on the share
    calls = len(api.odoo.calls)
    again = api.post("/api/print-jobs/1/reprint", json={})
    assert again.status_code == 200 and again.headers["x-reprint-source"] == "snapshot"
    assert pages_text(again.content) == pages_text(original) == ["INDIVIDUAL 220-TD"] * 2
    assert len(api.odoo.calls) == calls  # a reprint never contacts Odoo
    (api.labels / IND).unlink()
    assert api.post("/api/print-jobs/1/reprint", json={"copies": 3}).headers["x-print-job-id"] == "3"
    job2 = api.get("/api/print-jobs/2").json()
    assert job2["reprint_of"] == 1 and job2["items"] == api.get("/api/print-jobs/1").json()["items"]


def test_files_too_large_to_keep_are_reprinted_from_their_location_and_not_merged(api, monkeypatch):
    monkeypatch.setenv("LABEL_MAX_MB", "0")  # every file counts as "too large"
    get_settings.cache_clear()
    login(api, "bob")
    one = api.post("/api/print/print", json=req())  # one file, one copy: streamed untouched
    assert one.status_code == 200 and one.content == (api.labels / IND).read_bytes()
    assert api.get("/api/print-jobs/1").json()["items"][0]["sha256"] is None
    assert api.post("/api/print/print", json=req(copies=2)).status_code == 413  # cannot combine it
    again = api.post("/api/print-jobs/1/reprint", json={})
    assert again.status_code == 200 and again.headers["x-reprint-source"] == "share"
    (api.labels / IND).unlink()
    assert api.post("/api/print-jobs/1/reprint", json={}).status_code == 409  # nothing kept, nothing there
    get_settings.cache_clear()


def test_history_is_private_to_each_printer_admins_see_all(api):
    login(api, "bob")
    api.post("/api/print/print", json=req())
    api.post("/api/auth/logout")
    login(api, "carol")
    assert api.get("/api/print-jobs").json() == [] and api.get("/api/print-jobs/1").status_code == 404
    api.post("/api/auth/logout")
    login(api, "alice")
    assert [j["id"] for j in api.get("/api/print-jobs").json()] == [1]
    assert api.get("/api/print-jobs?so=NOPE").json() == []


def test_nothing_is_ever_written_to_odoo(api):
    login(api, "bob")
    api.post("/api/print/print", json=req(copies=2))
    api.post("/api/print-jobs/1/reprint", json={})
    assert {m for _, m in api.odoo.calls} <= {"search_read", "read", "search", "fields_get", "read_group"}


def test_folder_priority_setting_picks_the_default_variant(api, monkeypatch):
    monkeypatch.setenv("LABEL_FOLDER_PRIORITY", "Box Stickers, Individual")
    get_settings.cache_clear()
    login(api, "bob")
    box = file_id(api, "220-TD.pdf", "Box Stickers")
    row = next(x for g in api.get("/api/so/S00123").json()["groups"] if g["id"] == "lines" for x in g["rows"])
    assert row["pdf"]["selected"] == box
    assert api.post("/api/print/preview", json=req()).content == (api.labels / BOX).read_bytes()
    get_settings.cache_clear()
