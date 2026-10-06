"""Auth, session, roles, SO endpoint, presets, template library rules (acceptance tests 2 and 11 + roles/versioning)."""
import io
import json
import sqlite3
import zipfile

from app import security
from tests.conftest import login, select_line

SAWO_HTML = b"<html><body>{{so_number}} {{line.product.name}} {{pcs}} {{unknown_thing}}</body></html>"


# ---------------------------------------------------------------- login / session (test 11) -----------------

def test_login_success_sets_http_only_cookie_and_returns_role(api):
    r = api.post("/api/auth/login", json={"login": "alice", "password": "pw-alice"})
    assert r.status_code == 200
    assert r.json() == {"uid": 7, "login": "alice", "name": "Alice Admin", "role": "template_admin"}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert api.get("/api/auth/me").json()["login"] == "alice"


def test_bad_credentials_are_401_and_generic(api):
    r = api.post("/api/auth/login", json={"login": "alice", "password": "wrong"})
    assert r.status_code == 401 and "pw-alice" not in r.text and "wrong" not in r.text
    assert api.get("/api/auth/me").status_code == 401


def test_lockout_after_repeated_failures_then_blocks_even_correct_password(api):
    for _ in range(3):
        assert api.post("/api/auth/login", json={"login": "bob", "password": "nope"}).status_code == 401
    r = api.post("/api/auth/login", json={"login": "bob", "password": "pw-bob"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_lockout_expires(api):
    clock = {"t": 1000.0}
    security.set_limiter(security.LoginLimiter(clock=lambda: clock["t"]))
    for _ in range(3):
        api.post("/api/auth/login", json={"login": "bob", "password": "nope"})
    assert api.post("/api/auth/login", json={"login": "bob", "password": "pw-bob"}).status_code == 429
    clock["t"] += 601
    assert api.post("/api/auth/login", json={"login": "bob", "password": "pw-bob"}).status_code == 200


def test_session_expires_after_idle_timeout_and_slides_while_active(api):
    clock = {"t": 0.0}
    security.set_session_store(security.MemorySessionStore(clock=lambda: clock["t"]))
    login(api, "bob")
    clock["t"] += 1000
    assert api.get("/api/auth/me").status_code == 200  # activity renews the window
    clock["t"] += 1000
    assert api.get("/api/auth/me").status_code == 200
    clock["t"] += 1801  # idle longer than 30 minutes
    assert api.get("/api/auth/me").status_code == 401


def test_logout_destroys_session(api):
    login(api, "bob")
    assert api.post("/api/auth/logout").status_code == 200
    assert api.get("/api/auth/me").status_code == 401


def test_password_never_in_db_logs_session_store_or_responses(api, env, caplog):
    caplog.set_level("DEBUG")
    r = api.post("/api/auth/login", json={"login": "alice", "password": "pw-alice"})
    assert "pw-alice" not in r.text and "pw-alice" not in json.dumps(dict(r.headers))
    api.get("/api/so/S00123")
    api.get("/api/templates")
    # validation error must not echo the submitted value either
    bad = api.post("/api/auth/login", json={"login": 123, "password": "pw-secret-leak"})
    assert bad.status_code == 422 and "pw-secret-leak" not in bad.text
    # session store holds ciphertext only
    store = security.get_session_store()
    dump = json.dumps(list(store._d.values()), default=str)
    assert "pw-alice" not in dump and '"cred"' in dump
    assert "pw-alice" not in caplog.text
    # app database
    db_path = next(env.glob("*.db"))
    con = sqlite3.connect(db_path)
    blob = "".join(str(row) for t in con.execute("select name from sqlite_master where type='table'").fetchall()
                   for row in con.execute(f'select * from "{t[0]}"').fetchall())
    con.close()
    assert "pw-alice" not in blob and "pw-secret-leak" not in blob


def test_state_changing_requests_need_the_csrf_header(api):
    api.headers.pop("X-Requested-With")
    assert api.post("/api/auth/login", json={"login": "alice", "password": "pw-alice"}).status_code == 403


def test_credentials_are_encrypted_with_the_app_key(api):
    login(api, "bob")
    sess = next(iter(security.get_session_store()._d.values()))[1]
    assert security.decrypt_secret(sess["cred"]) == "pw-bob" and sess["cred"] != "pw-bob"


# ---------------------------------------------------------------- SO endpoint & permissions (test 2) ---------

def test_so_requires_login(api):
    assert api.get("/api/so/S00123").status_code == 401


def test_so_endpoint_returns_grouped_data_without_image_payload(api):
    login(api, "bob")
    r = api.get("/api/so/S00123")
    assert r.status_code == 200
    body = r.json()
    assert [g["id"] for g in body["groups"]][:3] == ["header", "lines", "products"]
    line = next(g for g in body["groups"] if g["id"] == "lines")["rows"][0]
    assert line["fields"]["line.product.image"]["raw"] is True
    assert "iVBOR" not in r.text


def test_so_unknown_is_404_and_user_without_access_cannot_see_it(api):
    login(api, "bob")
    assert api.get("/api/so/NOPE").status_code == 404
    api.odoo.hide_so_from = {8}
    api.get("/api/auth/me")
    assert api.get("/api/so/S00123?refresh=true").status_code == 404


def test_cache_is_per_user(api):
    login(api, "alice")
    assert api.get("/api/so/S00123").status_code == 200
    api.post("/api/auth/logout")
    api.odoo.hide_so_from = {8}
    login(api, "bob")
    assert api.get("/api/so/S00123").status_code == 404  # alice's cached copy is not served to bob


def test_limited_access_shows_not_accessible_groups_only(api):
    login(api, "bob")
    api.odoo.deny = {"mrp.production"}
    groups = {g["id"]: g for g in api.get("/api/so/S00123").json()["groups"]}
    assert groups["mrp"]["status"] == "not_accessible" and groups["delivery"]["status"] == "ok"


def test_catalog_endpoint(api):
    login(api, "bob")
    cat = api.get("/api/catalog").json()
    keys = {c["key"] for c in cat}
    assert {"header.name", "line.product.code", "calc.kgs", "print.logo"} <= keys
    assert next(c for c in cat if c["key"] == "header.name")["aliases"] == ["so_number", "so"]


# ---------------------------------------------------------------- roles -------------------------------------

def test_roles_gate_printing_and_template_admin(api, env):
    from app.db import SessionLocal
    from app.models import AppUser

    login(api, "carol")
    db = SessionLocal()
    db.get(AppUser, 9).app_role = "viewer"
    db.commit()
    db.close()
    assert api.get("/api/so/S00123").status_code == 200  # viewer can search
    r = api.post("/api/render/print", json={"so": "S00123", "template_id": 1, "selection": {"items": []}})
    assert r.status_code == 403
    up = api.post("/api/templates", files={"file": ("t.html", SAWO_HTML)}, data={"name": "x"})
    assert up.status_code == 403


def test_template_admin_can_change_roles(api):
    login(api, "bob")
    api.post("/api/auth/logout")
    login(api, "alice")
    assert api.put("/api/auth/users/8/role", json={"role": "viewer"}).json()["role"] == "viewer"
    assert api.put("/api/auth/users/8/role", json={"role": "god"}).status_code == 422
    api.post("/api/auth/logout")
    login(api, "bob")
    assert api.get("/api/auth/me").json()["role"] == "viewer"
    assert api.put("/api/auth/users/8/role", json={"role": "template_admin"}).status_code == 403


# ---------------------------------------------------------------- presets ---------------------------------------

def test_presets_are_per_user_and_shareable(api):
    login(api, "bob")
    sel = {"rules": [{"group": "lines", "keys": ["line.product.code"], "rows": "all"}]}
    p = api.post("/api/presets", json={"name": "Shipping label", "selection": sel}).json()
    api.post("/api/presets", json={"name": "Shared one", "selection": sel, "shared": True})
    assert {x["name"] for x in api.get("/api/presets").json()} == {"Shipping label", "Shared one"}
    api.post("/api/auth/logout")
    login(api, "carol")
    assert {x["name"] for x in api.get("/api/presets").json()} == {"Shared one"}
    assert api.delete(f"/api/presets/{p['id']}").status_code == 404  # not carol's
    api.post("/api/auth/logout")
    login(api, "bob")
    assert api.delete(f"/api/presets/{p['id']}").status_code == 200


# ---------------------------------------------------------------- template library (test 7 mechanics) ---------

def upload(api, content=SAWO_HTML, name="Test label", fname="t.html", **data):
    return api.post("/api/templates", files={"file": (fname, content)}, data={"name": name, "size": "A6", **data})


def test_upload_scans_placeholders_and_blocks_activation_until_mapped(api):
    login(api, "alice")
    r = upload(api)
    assert r.status_code == 201
    t = r.json()
    v1 = t["versions"][0]
    maps = {m["placeholder"]: m["catalog_key"] for m in v1["mappings"]}
    assert maps == {"so_number": "header.name", "line.product.name": "line.product.name", "pcs": "calc.pcs",
                    "unknown_thing": None}
    assert t["unresolved"] == ["unknown_thing"] and t["active"] is False
    blocked = api.post(f"/api/templates/{t['id']}/activate")
    assert blocked.status_code == 422 and "unknown_thing" in blocked.text

    fixed = [{"placeholder": "unknown_thing", "catalog_key": None, "optional": True, "overflow_rule": "wrap"}]
    v2 = api.post(f"/api/templates/{t['id']}/versions", data={"mappings": json.dumps(fixed)})
    assert v2.status_code == 201 and v2.json()["latest_version"] == 2 and v2.json()["unresolved"] == []
    act = api.post(f"/api/templates/{t['id']}/activate")
    assert act.status_code == 200 and act.json()["active"] and act.json()["active_version"] == 2
    assert [v["version"] for v in act.json()["versions"]] == [1, 2]  # v1 is kept


def test_mapping_to_unknown_catalog_key_is_rejected(api):
    login(api, "alice")
    t = upload(api).json()
    bad = [{"placeholder": "so_number", "catalog_key": "nope.nope"}]
    assert api.post(f"/api/templates/{t['id']}/versions", data={"mappings": json.dumps(bad)}).status_code == 422


def test_new_version_of_active_template_does_not_switch_until_ready(api):
    login(api, "alice")
    tpl = next(t for t in api.get("/api/templates").json() if t["name"].startswith("SAWO"))
    assert tpl["active"] and tpl["active_version"] == 1
    broken = b"<html><body>{{so_number}} {{totally_unmapped}}</body></html>"
    r = api.post(f"/api/templates/{tpl['id']}/versions", files={"file": ("n.html", broken)})
    assert r.status_code == 201 and r.json()["latest_version"] == 2 and r.json()["active_version"] == 1


def test_printers_only_see_active_templates(api):
    login(api, "alice")
    upload(api, name="Draft one")
    api.post("/api/auth/logout")
    login(api, "bob")
    names = [t["name"] for t in api.get("/api/templates").json()]
    assert names == ["SAWO Product Label (A6)"]


def test_upload_rejections(api):
    login(api, "alice")
    assert upload(api, b"MZ\x90", fname="evil.exe").status_code == 422
    assert upload(api, b"", fname="e.html").status_code == 422
    assert upload(api, b"\xff\xfe", fname="bad.html").status_code == 422  # not UTF-8
    assert upload(api, b"%PDF-", fname="bg.pdf").status_code == 422  # needs placement data
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../etc/passwd", "x")
        z.writestr("index.html", "{{so_number}}")
    assert upload(api, buf.getvalue(), fname="slip.zip").status_code == 422
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("index.html", "{{so_number}}")
        z.writestr("run.sh", "rm -rf /")
    assert upload(api, buf.getvalue(), fname="bad.zip").status_code == 422
    big = b"<html>" + b"x" * (16 * 1024 * 1024)
    assert upload(api, big, fname="big.html").status_code == 422


def test_zip_template_with_assets_and_missing_asset_check(api):
    login(api, "alice")
    ok = io.BytesIO()
    with zipfile.ZipFile(ok, "w") as z:
        z.writestr("index.html", '<img src="logo.png">{{so_number}}{{asset:logo.png}}')
        z.writestr("logo.png", b"\x89PNG")
    assert upload(api, ok.getvalue(), name="Zip ok", fname="t.zip").status_code == 201
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("index.html", "{{asset:missing.png}}{{so_number}}")
    r = upload(api, bad.getvalue(), name="Zip bad", fname="t2.zip")
    assert r.status_code == 422 and "missing.png" in r.text


def test_duplicate_name_is_rejected(api):
    login(api, "alice")
    assert upload(api, name="Dup").status_code == 201
    assert upload(api, name="Dup").status_code == 422


def test_audit_log_records_login_search_upload(api, env):
    from app.db import SessionLocal
    from app.models import AuditEvent

    login(api, "alice")
    api.get("/api/so/S00123")
    upload(api, name="Audited")
    db = SessionLocal()
    events = [e.event for e in db.query(AuditEvent).all()]
    db.close()
    assert {"login", "search", "upload"} <= set(events)
