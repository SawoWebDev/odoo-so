"""Who may do what: registering people by email, the main admin that cannot be removed, and admin-only screens."""
from tests.conftest import login


def users(api):
    return {u["login"]: u for u in api.get("/api/auth/users").json()}


def test_only_admins_reach_roles_and_settings(api):
    login(api, "bob")  # an ordinary signed-in person (printer)
    assert api.get("/api/auth/users").status_code == 403
    assert api.post("/api/auth/users", json={"email": "x@sawo.test", "role": "admin"}).status_code in (403, 422)
    assert api.delete("/api/auth/users/7").status_code == 403
    assert api.get("/api/settings/email").status_code == 403
    assert api.put("/api/settings/email", json={}).status_code == 403


def test_an_admin_registers_a_person_before_they_sign_in(api):
    login(api, "alice")  # alice is the main admin in the tests
    r = api.post("/api/auth/users", json={"email": "Carol@Sawo.test", "role": "template_admin"})
    assert r.status_code == 201 and r.json()["registered"] is True
    pending = users(api)["carol@sawo.test"]
    assert pending["pending"] is True and pending["role"] == "template_admin" and pending["uid"] is None
    # the registration is turned into the real role when that person signs in (matched on login or Odoo email)
    from app.db import SessionLocal
    from app.models import RoleGrant
    db = SessionLocal()
    db.query(RoleGrant).filter(RoleGrant.login == "carol@sawo.test").one().login = "carol"  # her Odoo login is "carol"
    db.commit(); db.close()
    login(api, "carol")
    assert api.get("/api/auth/users").status_code == 200  # carol is an admin now
    assert users(api)["carol"]["role"] == "template_admin" and not users(api)["carol"]["pending"]


def test_registering_validates_and_updates_existing_people(api):
    login(api, "alice")
    assert api.post("/api/auth/users", json={"email": "not-an-email", "role": "printer"}).status_code == 422
    assert api.post("/api/auth/users", json={"email": "a@sawo.test", "role": "boss"}).status_code == 422
    login(api, "bob")
    login(api, "alice")
    r = api.post("/api/auth/users", json={"email": "bob", "role": "viewer"})  # not an email: refused
    assert r.status_code == 422
    api.post("/api/auth/users", json={"email": "p@sawo.test", "role": "viewer"})
    api.post("/api/auth/users", json={"email": "p@sawo.test", "role": "printer"})  # asking again just updates it
    assert users(api)["p@sawo.test"]["role"] == "printer"
    assert len([u for u in users(api).values() if u["pending"]]) == 1


def test_the_main_admin_cannot_be_deleted_or_demoted_and_nobody_deletes_themselves(api):
    login(api, "bob")
    login(api, "alice")
    me = users(api)["alice"]
    assert me["main"] is True and me["you"] is True
    assert api.delete(f"/api/auth/users/{me['uid']}").status_code == 403
    assert api.put(f"/api/auth/users/{me['uid']}/role", json={"role": "viewer"}).status_code == 403
    # a second admin can be removed by the main admin, but cannot remove the main admin
    bob = users(api)["bob"]
    api.put(f"/api/auth/users/{bob['uid']}/role", json={"role": "template_admin"})
    login(api, "bob")
    assert api.delete(f"/api/auth/users/{me['uid']}").status_code == 403  # "The main admin cannot be deleted"
    assert api.delete(f"/api/auth/users/{bob['uid']}").status_code == 403  # nor yourself
    assert api.put(f"/api/auth/users/{bob['uid']}/role", json={"role": "viewer"}).status_code == 403  # nor your own role
    login(api, "alice")
    assert api.delete(f"/api/auth/users/{bob['uid']}").status_code == 200
    assert "bob" not in users(api)


def test_a_pending_registration_can_be_cancelled(api):
    login(api, "alice")
    api.post("/api/auth/users", json={"email": "later@sawo.test", "role": "printer"})
    gid = users(api)["later@sawo.test"]["grant_id"]
    assert api.delete(f"/api/auth/pending/{gid}").status_code == 200
    assert "later@sawo.test" not in users(api)
    assert api.delete(f"/api/auth/pending/{gid}").status_code == 404
