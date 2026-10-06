"""The saved list of label files: URLs, fetch, rescan, delete, and matching item codes against the saved list."""
from pathlib import Path

import pytest

from app.config import Settings
from app.labels.index import code_of
from app.labels.store import LocationError, resolve_url, to_url
from tests.conftest import PRINT_DIR, PRINT_URL, SHARE, file_id, login, make_viewer
from tests.helpers import make_pdf

# ---------------------------------------------------------------- pure functions --------------------------------


@pytest.mark.parametrize("name,expect", [
    ("560-BL.pdf", ("560-BL", True)), ("560-bl.PDF", ("560-BL", True)),
    ("SET-TRAD-D -No BG.pdf", ("SET-TRAD-D", False)), ("SET-TRAD-D (No BG_No Logo).pdf", ("SET-TRAD-D", False)),
    ("460-D2.pdf", ("460-D2", True)), ("460-D-old.pdf", ("460-D-OLD", True)), ("  SR05-4364350  .pdf", ("SR05-4364350", True)),
])
def test_item_code_of_a_file_name(name, expect):
    assert code_of(name) == expect


@pytest.fixture
def settings(tmp_path):
    (tmp_path / PRINT_DIR / "01 SAWO").mkdir(parents=True)
    return Settings(label_mount_dir=str(tmp_path), label_share=SHARE)


def test_the_file_url_from_the_explorer_maps_to_the_mounted_folder(settings, tmp_path):
    url = "file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/"
    assert resolve_url(url, settings) == (tmp_path / PRINT_DIR / "01 SAWO").resolve()


@pytest.mark.parametrize("url", [
    r"\\172.16.0.4\Marketing\00 MASTERLIST\01 PRINTING FILES\01 SAWO",
    "//172.16.0.4/marketing/00 MASTERLIST/01 PRINTING FILES/01 SAWO/",  # share name is case-insensitive
    "file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO",
    "  FILE://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/  ",
])
def test_other_ways_of_writing_the_same_location(settings, tmp_path, url):
    assert resolve_url(url, settings) == (tmp_path / PRINT_DIR / "01 SAWO").resolve()


def test_a_container_path_inside_the_mount_is_accepted(settings, tmp_path):
    assert resolve_url(str(tmp_path / PRINT_DIR), settings) == (tmp_path / PRINT_DIR).resolve()


@pytest.mark.parametrize("url,message", [
    ("", "Enter the folder"),
    ("file:///C:/Users/me/labels", "your own PC"),
    ("file://10.0.0.9/Other/labels", "is not connected"),
    ("file://172.16.0.4/Marketing/00%20MASTERLIST/missing%20folder", "cannot be found"),
    ("file://172.16.0.4/Marketing/../../etc", "inside the connected location"),
    ("/etc", "inside the connected location"),
    ("file://172.16.0.4", "Expected an address"),
])
def test_bad_locations_are_refused_with_a_clear_message(settings, url, message):
    with pytest.raises(LocationError, match=message):
        resolve_url(url, settings)


def test_no_connected_share_gives_a_setup_hint(tmp_path):
    with pytest.raises(LocationError, match="No network share is connected"):
        resolve_url("file://172.16.0.4/Marketing/x", Settings(label_mount_dir=str(tmp_path), label_share=""))


def test_a_friendly_address_is_built_for_the_default_folder(settings, tmp_path):
    assert to_url(tmp_path / PRINT_DIR, settings) == "file:" + "//172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/"


# ---------------------------------------------------------------- the saved list (via the API) ------------------


def status(api):
    return api.get("/api/labels/status").json()


def search(api, **params):
    return api.get("/api/labels/search", params={"size": 100, **params}).json()


def test_the_default_location_was_fetched_and_saved_at_startup(api):
    login(api, "bob")
    st = status(api)
    assert [loc["url"] for loc in st["locations"]] == [PRINT_URL]
    assert st["files"] == 3 and st["missing"] == 0 and st["codes"] == 2  # 220-TD and SET-X
    loc = st["locations"][0]
    assert loc["reachable"] is True and loc["last_fetched_at"] and loc["folder"].endswith("01 PRINTING FILES")
    rows = search(api)["items"]
    assert {r["name"] for r in rows} == {"220-TD.pdf", "SET-X -No BG.pdf"} and len(rows) == 3
    assert {r["folder"] for r in rows} == {"01 SAWO/P1/01 Individual", "01 SAWO/P1/02 Box Stickers"}
    assert all(r["status"] == "ok" and r["size"] > 0 for r in rows)


def test_only_admins_add_or_remove_folders(api):
    login(api, "bob")
    other = api.mount / "00 MASTERLIST/02 OTHER"
    make_pdf(other / "X-1.pdf", "x")
    assert api.post("/api/labels/locations", json={"url": "file://172.16.0.4/Marketing/00%20MASTERLIST/02%20OTHER"}).status_code == 403
    assert api.delete("/api/labels/locations/1").status_code == 403
    api.post("/api/auth/logout")
    login(api, "alice")
    r = api.post("/api/labels/locations", json={"url": "file://172.16.0.4/Marketing/00%20MASTERLIST/02%20OTHER"})
    assert r.status_code == 201 and r.json()["result"]["added"] == 1 and r.json()["location"]["files"] == 1
    assert status(api)["files"] == 4
    assert api.delete(f"/api/labels/locations/{r.json()['location']['id']}").status_code == 200
    assert status(api)["files"] == 3 and (other / "X-1.pdf").exists()  # forgetting a folder never touches the share


def test_adding_a_bad_or_duplicate_folder_is_a_422(api):
    login(api, "alice")
    for url in ("file://172.16.0.4/Marketing/nope", "file://other/Share/x", "", "file:///C:/x", PRINT_URL):
        r = api.post("/api/labels/locations", json={"url": url})
        assert r.status_code == 422, url
    assert "already been added" in api.post("/api/labels/locations", json={"url": PRINT_URL}).text


def test_fetch_saves_new_files_and_flags_removed_ones(api):
    login(api, "bob")
    make_pdf(api.labels / "01 SAWO/P1/03 New/NEW-1.pdf", "new")
    assert search(api, q="NEW-1")["total"] == 0  # not saved until a fetch
    r = api.post("/api/labels/locations/1/fetch")
    assert r.status_code == 200 and r.json()["result"]["added"] == 1 and r.json()["result"]["files"] == 4
    assert search(api, q="NEW-1")["total"] == 1
    (api.labels / "01 SAWO/P1/03 New/NEW-1.pdf").unlink()
    assert api.post("/api/labels/locations/1/fetch").json()["result"]["now_missing"] == 1
    assert search(api, q="NEW-1")["items"][0]["status"] == "missing"


def test_rescan_only_checks_saved_files_it_does_not_add_new_ones(api):
    login(api, "bob")
    make_pdf(api.labels / "01 SAWO/Z/NEW-2.pdf", "new")
    r = api.post("/api/labels/rescan").json()
    assert r["results"][0]["ok"] == 3 and r["results"][0]["missing"] == 0 and r["files"] == 3
    assert search(api, q="NEW-2")["total"] == 0


def test_a_renamed_or_deleted_file_turns_missing_and_comes_back_when_restored(api):
    login(api, "bob")
    ind = api.labels / "01 SAWO/P1/01 Individual/220-TD.pdf"
    ind.rename(ind.with_name("220-TD-renamed.pdf"))
    r = api.post("/api/labels/rescan").json()
    assert r["results"][0]["missing"] == 1 and r["missing"] == 1 and r["results"][0]["changed"] == 1
    missing = search(api, state="missing")["items"]
    assert [m["name"] for m in missing] == ["220-TD.pdf"] and missing[0]["folder"] == "01 SAWO/P1/01 Individual"
    assert search(api)["items"][0]["status"] == "missing"  # red rows are listed first
    ind.with_name("220-TD-renamed.pdf").rename(ind)
    api.post("/api/labels/rescan")
    assert status(api)["missing"] == 0


def test_a_network_outage_does_not_turn_the_whole_list_red(api, env):
    login(api, "bob")
    api.labels.rename(api.labels.with_name("gone"))  # the whole folder disappears (share down)
    r = api.post("/api/labels/rescan").json()
    assert "cannot be reached" in r["results"][0]["error"] and r["missing"] == 0
    assert api.post("/api/labels/locations/1/fetch").status_code == 409
    assert status(api)["missing"] == 0 and status(api)["locations"][0]["reachable"] is False


def test_only_files_that_are_gone_can_be_deleted_from_the_list(api):
    login(api, "bob")
    fid = file_id(api, "220-TD.pdf", "Individual")
    r = api.delete(f"/api/labels/files/{fid}")
    assert r.status_code == 409 and "still in the folder" in r.text
    (api.labels / "01 SAWO/P1/01 Individual/220-TD.pdf").unlink()
    api.post("/api/labels/rescan")
    assert api.delete(f"/api/labels/files/{fid}").status_code == 200
    assert status(api)["files"] == 2 and search(api, q="Individual")["total"] == 0
    assert api.delete(f"/api/labels/files/{fid}").status_code == 409  # already gone


def test_viewers_cannot_change_the_list(api):
    login(api, "carol")
    make_viewer(api, 9)
    assert status(api)["files"] == 3  # but they can look
    assert search(api)["total"] == 3
    assert api.post("/api/labels/rescan").status_code == 403
    assert api.post("/api/labels/locations/1/fetch").status_code == 403
    assert api.delete("/api/labels/files/1").status_code == 403


def test_search_filters_and_pages(api):
    login(api, "bob")
    assert search(api, q="220-td")["total"] == 2
    assert search(api, q="box 220")["total"] == 1
    assert search(api, q="220-td", size=1)["items"][0]["name"] == "220-TD.pdf" and len(search(api, q="220-td", size=1)["items"]) == 1
    assert search(api, q="220-td", size=1, page=2)["page"] == 2
    assert search(api, state="missing")["total"] == 0 and search(api, location_id=999)["total"] == 0


def test_the_file_endpoint_streams_a_saved_file_by_id_and_flags_one_that_vanished(api):
    login(api, "bob")
    fid = file_id(api, "220-TD.pdf", "Box Stickers")
    p = api.labels / "01 SAWO/P1/02 Box Stickers/220-TD.pdf"
    r = api.get("/api/labels/file", params={"id": fid})
    assert r.status_code == 200 and r.content == p.read_bytes() and "inline" in r.headers["content-disposition"]
    p.unlink()
    assert api.get("/api/labels/file", params={"id": fid}).status_code == 404
    assert search(api, state="missing")["total"] == 1  # the failed fetch flagged it
    assert api.get("/api/labels/file", params={"id": 99999}).status_code == 404


def test_list_endpoints_need_login(api):
    for path in ("/api/labels/status", "/api/labels/search", "/api/labels/file?id=1"):
        assert api.get(path).status_code == 401
    assert Path(api.labels).is_dir()


# ---------------------------------------------------------------- every sub-folder, any depth; each file's URL ----

def test_read_folder_gets_every_pdf_in_every_sub_folder_however_deep(api):
    login(api, "bob")
    deep = api.labels / "a/b/c/d/e/f/g/h/i/j/k"  # eleven levels down
    make_pdf(deep / "DEEP-1.pdf", "deep")
    make_pdf(api.labels / "x y/z/UPPER-1.PDF", "upper")  # extension in capitals, folder names with spaces
    make_pdf(api.labels / ".hidden/HID-1.pdf", "hidden folder")
    (api.labels / "no pdf here").mkdir()
    (api.labels / "no pdf here/notes.txt").write_text("not a pdf")
    r = api.post("/api/labels/locations/1/fetch").json()["result"]
    assert r["added"] == 3 and r["files"] == 6
    names = {i["name"]: i for i in search(api)["items"]}
    assert {"DEEP-1.pdf", "UPPER-1.PDF", "HID-1.pdf"} <= set(names) and "notes.txt" not in names
    assert names["DEEP-1.pdf"]["folder"] == "a/b/c/d/e/f/g/h/i/j/k"


def test_every_file_is_saved_with_its_own_url(api):
    login(api, "bob")
    make_pdf(api.labels / "01 SAWO/P2/01 Door_Sticker/No Logo/735-4SCD-R.pdf", "door")
    api.post("/api/labels/locations/1/fetch")
    items = search(api, q="735-4SCD-R")["items"]
    assert [i["url"] for i in items] == [
        "file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/P2/01%20Door_Sticker/No%20Logo/735-4SCD-R.pdf"]
    assert all(i["url"].startswith("file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/") for i in search(api)["items"])
    assert all(i["url"].lower().endswith(".pdf") for i in search(api)["items"])


def test_the_url_of_a_saved_file_resolves_back_to_the_same_file(api, env):
    from app.config import Settings
    from app.labels.store import resolve_url

    login(api, "bob")
    st = Settings(label_mount_dir=str(env / "mnt"), label_share=SHARE)
    for i in search(api)["items"]:
        assert resolve_url(i["url"].rsplit("/", 1)[0], st).joinpath(i["name"]).is_file()


def test_a_folder_that_overlaps_an_added_one_is_refused_so_no_pdf_is_saved_twice(api):
    login(api, "alice")
    sub = "file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/P1/"
    r = api.post("/api/labels/locations", json={"url": sub})
    assert r.status_code == 422 and "already covered" in r.text and "sub-folders are all included" in r.text
    parent = "file://172.16.0.4/Marketing/00%20MASTERLIST/"
    r = api.post("/api/labels/locations", json={"url": parent})
    assert r.status_code == 422 and "contains a folder you added earlier" in r.text
    assert status(api)["files"] == 3


def test_a_database_from_the_previous_version_gets_the_url_column_and_values(api, env):
    from sqlalchemy import inspect, text

    from app.config import get_settings
    from app.db import SessionLocal, get_engine
    from app.labels import store

    eng = get_engine()
    with eng.begin() as conn:  # simulate the older table without the column
        conn.execute(text("ALTER TABLE label_file DROP COLUMN url"))
    assert "url" not in {c["name"] for c in inspect(eng).get_columns("label_file")}
    store.ensure_schema(get_settings())
    assert "url" in {c["name"] for c in inspect(eng).get_columns("label_file")}
    db = SessionLocal()
    assert store.backfill_urls(db, get_settings()) == 3
    db.close()
    login(api, "bob")
    assert all(i["url"] for i in search(api)["items"])
