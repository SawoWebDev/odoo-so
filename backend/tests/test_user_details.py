"""Admins editing the name and email shown for a person on the Roles screen."""
from tests.conftest import login


def bob_row(api):
    return next(u for u in api.get("/api/auth/users").json() if u["uid"] == 8)


def test_admin_edits_name_and_email(api):
    login(api, "bob")
    login(api, "alice")
    r = api.put("/api/auth/users/8/details", json={"name": "  Bob   Builder ", "email": "Bob@Sawo.com"})
    assert r.status_code == 200 and r.json() == {"uid": 8, "name": "Bob Builder", "email": "bob@sawo.com"}
    row = bob_row(api)
    assert row["name"] == "Bob Builder" and row["email"] == "bob@sawo.com" and row["custom_name"] == "Bob Builder"
    assert any(i["event"] == "user_edit" for i in api.get("/api/activity").json()["items"])


def test_sign_in_keeps_the_edit_and_uses_it(api):
    login(api, "bob")
    login(api, "alice")
    api.put("/api/auth/users/8/details", json={"name": "Bob Builder", "email": ""})
    assert login(api, "bob")["name"] == "Bob Builder"  # Odoo's name does not overwrite it
    assert api.get("/api/auth/me").json()["name"] == "Bob Builder"


def test_empty_goes_back_to_odoo(api):
    login(api, "bob")
    login(api, "alice")
    api.put("/api/auth/users/8/details", json={"name": "Bob Builder", "email": "b@sawo.com"})
    api.put("/api/auth/users/8/details", json={"name": "", "email": ""})
    row = bob_row(api)
    assert row["name"] == row["odoo_name"] and row["custom_name"] == "" and row["custom_email"] == ""


def test_bad_email_and_rights(api):
    login(api, "bob")
    login(api, "alice")
    assert api.put("/api/auth/users/8/details", json={"email": "not-an-email"}).status_code == 422
    assert api.put("/api/auth/users/999/details", json={"name": "X"}).status_code == 404
    login(api, "bob")
    assert api.put("/api/auth/users/7/details", json={"name": "Hacked"}).status_code == 403


def test_edited_email_never_makes_a_main_admin(api, monkeypatch):
    from app.config import get_settings

    login(api, "bob")
    login(api, "alice")
    main = next(iter(get_settings().admin_logins))
    api.put("/api/auth/users/8/details", json={"email": main if "@" in main else f"{main}@x.com"})
    assert bob_row(api)["main"] is False
