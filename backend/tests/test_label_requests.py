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
