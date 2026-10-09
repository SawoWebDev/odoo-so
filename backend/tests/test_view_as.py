"""Admins viewing the app as another person, and the Activity log."""
from tests.conftest import login


def start_as_bob(api):
    login(api, "bob")  # bob must have signed in once
    login(api, "alice")
    r = api.post("/api/auth/users/8/view-as")
    assert r.status_code == 200, r.text
    return r.json()


def test_view_as_takes_the_persons_role_and_identity(api):
    out = start_as_bob(api)
    assert out["uid"] == 8 and out["role"] == "printer" and out["viewing_as"]["admin_name"] == "Alice Admin"
    me = api.get("/api/auth/me").json()
    assert me["uid"] == 8 and me["role"] == "printer" and me["viewing_as"]
    assert api.get("/api/auth/users").status_code == 403  # admin-only screens are closed, as they are for bob
    assert api.get("/api/activity").status_code == 403


def test_view_as_reads_odoo_with_the_admins_login(api):
    start_as_bob(api)
    assert api.get("/api/so/S00123").status_code == 200


def test_nothing_can_be_changed_while_viewing_as(api):
    start_as_bob(api)
    r = api.post("/api/label-requests", json={"code": "RS-1", "so": "S00123"})
    assert r.status_code == 403 and "viewing the app as" in r.json()["detail"]
    assert api.post("/api/auth/users/9/view-as").status_code == 403  # no stacking
    assert api.post("/api/print/print", json={"so": "S00123", "items": [], "copies": 1}).status_code == 403


def test_back_to_admin(api):
    start_as_bob(api)
    r = api.post("/api/auth/view-as/stop")
    assert r.status_code == 200 and r.json()["uid"] == 7 and r.json()["role"] == "template_admin"
    me = api.get("/api/auth/me").json()
    assert me["uid"] == 7 and me["viewing_as"] is None
    assert api.get("/api/auth/users").status_code == 200


def test_only_admins_can_view_as(api):
    login(api, "alice")
    login(api, "bob")
    assert api.post("/api/auth/users/7/view-as").status_code == 403


def test_cannot_view_as_yourself_or_unknown(api):
    login(api, "alice")
    assert api.post("/api/auth/users/7/view-as").status_code == 422
    assert api.post("/api/auth/users/999/view-as").status_code == 404


def test_activity_log_records_the_real_admin(api):
    start_as_bob(api)
    api.get("/api/so/S00123")
    api.post("/api/auth/view-as/stop")
    log = api.get("/api/activity").json()
    events = [i["event"] for i in log["items"]]
    assert events[:3] == ["view_as_stop", "search", "view_as_start"]
    search = log["items"][1]
    assert search["who"] == "Alice Admin" and search["as"].lower() == "bob" and search["so"] == "S00123"
    assert "login" in log["events"]
    only = api.get("/api/activity", params={"event": "search"}).json()
    assert only["items"] and all(i["event"] == "search" for i in only["items"])
