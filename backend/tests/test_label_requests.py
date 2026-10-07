"""Label requests: ask for a missing label file; closed automatically when the file shows up in the list."""
from tests.conftest import login
from tests.helpers import make_pdf


def line(api, so="S00124", user_refresh=True):
    r = api.get(f"/api/so/{so}" + ("?refresh=true" if user_refresh else "")).json()
    return next(x for g in r["groups"] if g["id"] == "lines" for x in g["rows"])


def ask(api, code="RS-1", name="Resale Gift Box", so="S00124"):
    return api.post("/api/label-requests", json={"code": code, "name": name, "so": so})


def test_a_line_without_a_file_can_be_requested_and_everybody_sees_it_as_requested(api):
    login(api, "bob")
    assert line(api)["pdf"]["request"] is None
    r = ask(api)
    assert r.status_code == 200 and r.json()["existing"] is False and r.json()["request"]["status"] == "open"
    row = line(api)
    assert row["pdf"]["request"]["requested_by_name"] and row["pdf"]["files"] == [] and row["disabled"] is True
    login(api, "carol")  # another user sees the same state, and asking again changes nothing
    assert line(api)["pdf"]["request"]["id"] == r.json()["request"]["id"]
    again = ask(api)
    assert again.json()["existing"] is True and again.json()["request"]["id"] == r.json()["request"]["id"]
    assert api.get("/api/label-requests").json()["counts"] == {"open": 1, "solved": 0}


def test_a_code_that_already_has_a_file_cannot_be_requested(api):
    login(api, "bob")
    r = ask(api, "220-TD", "Thermometer", "S00123")
    assert r.status_code == 409 and "already exists" in r.text


def test_the_request_is_solved_and_closed_when_the_file_is_added_to_the_list(api):
    login(api, "alice")
    ask(api)
    assert api.get("/api/label-requests").json()["counts"]["open"] == 1
    make_pdf(api.labels / "01 SAWO/P5/RS-1 -No BG.pdf", "RS-1 NEW")  # the artwork was uploaded to the share
    assert line(api)["pdf"]["files"] == []  # not in the saved list yet: the app does not see it until Read folder
    res = api.post("/api/labels/locations/1/fetch").json()["result"]
    assert res["requests_solved"] >= 1
    got = api.get("/api/label-requests", params={"status": "open"}).json()
    assert not [x for x in got["items"] if x["code"] == "RS-1"]  # gone from the open list
    solved = api.get("/api/label-requests", params={"status": "solved"}).json()["items"]
    rs1 = next(x for x in solved if x["code"] == "RS-1")
    assert rs1["file_name"] == "RS-1 -No BG.pdf" and rs1["file_url"].startswith("file://172.16.0.4/Marketing/")
    row = line(api)
    assert row["pdf"]["request"] is None and row["disabled"] is False  # the line can be printed now


def test_only_the_requester_or_an_admin_can_delete_a_request(api):
    login(api, "bob")
    rid = ask(api).json()["request"]["id"]
    login(api, "carol")
    assert api.delete(f"/api/label-requests/{rid}").status_code == 403
    login(api, "bob")
    assert api.delete(f"/api/label-requests/{rid}").status_code == 200
    assert api.get("/api/label-requests").json()["items"] == []
    rid2 = ask(api).json()["request"]["id"]
    login(api, "alice")  # admin
    assert api.delete(f"/api/label-requests/{rid2}").status_code == 200
    assert api.delete(f"/api/label-requests/{rid2}").status_code == 404


def test_requests_need_a_login(api):
    assert api.get("/api/label-requests").status_code == 401
    assert ask(api).status_code == 401


# ---------------------------------------------------------------- change requests (the line HAS a file) ------------

def change(api, note="Change the artwork to the new logo", code="220-TD", so="S00123"):
    return api.post("/api/label-requests", json={"code": code, "name": "Thermometer", "so": so, "kind": "change", "note": note})


def test_a_line_with_a_file_can_get_a_change_request_with_a_note(api):
    login(api, "bob")
    assert line(api, "S00123")["pdf"]["requests"] == []
    r = change(api)
    assert r.status_code == 200 and r.json()["request"]["kind"] == "change" and "new logo" in r.json()["request"]["note"]
    row = line(api, "S00123")
    assert [c["note"] for c in row["pdf"]["requests"]] == ["Change the artwork to the new logo"]
    assert row["disabled"] is False and row["pdf"]["files"]  # the label can still be printed meanwhile
    assert change(api).json()["existing"] is True  # same person, same text: not twice
    assert change(api, "Fix the barcode").json()["existing"] is False  # another text is another request
    login(api, "carol")
    assert len(line(api, "S00123")["pdf"]["requests"]) == 2  # everybody sees them


def test_a_change_request_needs_a_note_and_an_existing_file(api):
    login(api, "bob")
    assert change(api, "   ").status_code == 422
    r = change(api, "something", "RS-1", "S00124")
    assert r.status_code == 409 and "request the missing label instead" in r.text
    r = api.post("/api/label-requests", json={"code": "220-TD", "kind": "missing"})
    assert r.status_code == 409  # the plain request still means "no file"


def test_change_requests_do_not_mix_with_missing_label_requests(api):
    login(api, "bob")
    change(api)
    ask(api)  # RS-1: no file
    lst = api.get("/api/label-requests").json()
    assert {x["code"]: x["kind"] for x in lst["items"]} == {"220-TD": "change", "RS-1": "missing"}
    make_pdf(api.labels / "01 SAWO/P5/RS-1.pdf", "RS-1")
    api.post("/api/labels/locations/1/fetch")  # solves the missing one only
    open_ = api.get("/api/label-requests").json()["items"]
    assert [(x["code"], x["kind"]) for x in open_] == [("220-TD", "change")]


def test_a_change_request_is_closed_by_hand_and_keeps_its_note(api):
    login(api, "bob")
    rid = change(api).json()["request"]["id"]
    login(api, "carol")  # a printer may close it
    assert api.post(f"/api/label-requests/{rid}/done").status_code == 200
    solved = api.get("/api/label-requests", params={"status": "solved"}).json()["items"]
    assert solved[0]["kind"] == "change" and solved[0]["note"].startswith("Change the artwork") and solved[0]["solved_at"]
    assert line(api, "S00123")["pdf"]["requests"] == []
    rid2 = ask(api).json()["request"]["id"]
    assert api.post(f"/api/label-requests/{rid2}/done").status_code == 409  # missing ones close themselves


def test_viewers_can_ask_but_cannot_close_other_peoples_change_requests(api):
    from tests.conftest import make_viewer
    login(api, "bob")
    rid = change(api).json()["request"]["id"]
    login(api, "carol")
    make_viewer(api, 9)
    assert api.post(f"/api/label-requests/{rid}/done").status_code == 403
    assert change(api, "my own request").status_code == 200


# ---------------------------------------------------------------- the label count decides when a request is done -----

def test_a_request_waits_for_one_more_label_file_than_there_is_now(api):
    login(api, "bob")
    row = line(api, "S00123")
    assert row["pdf"]["file_count"] == 2  # 220-TD has two label files
    r = change(api, "A version without logo").json()["request"]
    assert r["baseline"] == 2 and r["expected"] == 3 and r["files_now"] == 2
    info = line(api, "S00123")["pdf"]["requests"][0]
    assert info["expected"] == 3 and info["files_now"] == 2 and info["kind"] == "change"  # pending: 2 of the 3 wanted
    api.post("/api/labels/rescan")
    assert api.get("/api/label-requests").json()["counts"] == {"open": 1, "solved": 0}  # nothing changed: still pending
    make_pdf(api.labels / "01 SAWO/P1/02 Box Stickers/220-TD -No Logo.pdf", "NO LOGO")  # the 3rd label file arrives
    res = api.post("/api/labels/locations/1/fetch").json()["result"]
    assert res["requests_solved"] == 1
    assert api.get("/api/label-requests").json()["counts"] == {"open": 0, "solved": 1}
    solved = api.get("/api/label-requests", params={"status": "solved"}).json()["items"][0]
    assert solved["file_name"] == "220-TD -No Logo.pdf" and solved["file_url"].endswith("220-TD%20-No%20Logo.pdf")  # the new link
    row = line(api, "S00123")
    assert row["pdf"]["file_count"] == 3 and row["pdf"]["requests"] == []


def test_two_waiting_requests_need_two_new_files_one_after_the_other(api):
    login(api, "bob")
    change(api, "No logo version")
    login(api, "carol")
    second = change(api, "Version in German").json()["request"]
    assert second["expected"] == 4  # 2 files now + 1 request ahead + itself
    make_pdf(api.labels / "01 SAWO/P1/02 Box Stickers/220-TD -No Logo.pdf", "A")
    api.post("/api/labels/locations/1/fetch")
    open_ = api.get("/api/label-requests").json()["items"]
    assert [x["note"] for x in open_] == ["Version in German"] and open_[0]["files_now"] == 3  # the first is done, this waits
    make_pdf(api.labels / "01 SAWO/P1/02 Box Stickers/220-TD (German).pdf", "B")
    api.post("/api/labels/locations/1/fetch")
    assert api.get("/api/label-requests").json()["counts"] == {"open": 0, "solved": 2}


def test_a_file_that_goes_missing_never_counts_toward_a_request(api):
    login(api, "bob")
    change(api, "Another version")
    (api.labels / "01 SAWO/P1/01 Individual/220-TD.pdf").unlink()
    api.post("/api/labels/rescan")
    make_pdf(api.labels / "01 SAWO/P1/02 Box Stickers/220-TD (x).pdf", "X")
    api.post("/api/labels/locations/1/fetch")
    # one file went and one came: still 2 usable files, the 3 that were asked for are not there
    assert api.get("/api/label-requests").json()["counts"] == {"open": 1, "solved": 0}
