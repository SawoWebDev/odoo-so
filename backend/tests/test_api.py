"""Auth, sessions, roles, the SO endpoint with label matching, and the label folder endpoints."""
import json
import sqlite3

from app import security
from tests.conftest import file_id, login


# ---------------------------------------------------------------- login / session -----------------------------

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
    bad = api.post("/api/auth/login", json={"login": 123, "password": "pw-secret-leak"})
    assert bad.status_code == 422 and "pw-secret-leak" not in bad.text
    dump = json.dumps(list(security.get_session_store()._d.values()), default=str)
    assert "pw-alice" not in dump and '"cred"' in dump
    assert "pw-alice" not in caplog.text
    con = sqlite3.connect(next(env.glob("*.db")))
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


# ---------------------------------------------------------------- roles --------------------------------------

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


# ---------------------------------------------------------------- SO endpoint with label matching ---------------

def lines(api, so="S00123", refresh=False):
    r = api.get(f"/api/so/{so}", params={"refresh": refresh})
    assert r.status_code == 200, r.text
    return {x["line_id"]: x for g in r.json()["groups"] if g["id"] == "lines" for x in g["rows"]}


def test_so_requires_login(api):
    assert api.get("/api/so/S00123").status_code == 401


def test_each_line_gets_every_matching_pdf_and_a_default(api):
    login(api, "bob")
    row = lines(api)[11]
    ind, box = file_id(api, "220-TD.pdf", "Individual"), file_id(api, "220-TD.pdf", "Box Stickers")
    assert row["pdf"]["code"] == "220-TD"
    assert [f["id"] for f in row["pdf"]["files"]] == [ind, box]
    assert [f["folder"] for f in row["pdf"]["files"]] == ["01 SAWO/P1/01 Individual", "01 SAWO/P1/02 Box Stickers"]
    assert row["pdf"]["selected"] == ind and row["disabled"] is False


def test_variant_names_are_found_for_the_item_code(api):
    login(api, "bob")
    api.odoo.add("product.product", id=300, default_code="SET-X", name="Set X", uom_id=1, product_tmpl_id=3000)
    api.odoo.add("sale.order.line", id=31, order_id=1, product_id=300, name="x", product_uom_qty=1.0, sequence=9,
                 display_type=False, product_uom=1)
    row = lines(api, refresh=True)[31]
    assert [f["name"] for f in row["pdf"]["files"]] == ["SET-X -No BG.pdf"] and row["disabled"] is False


def test_a_line_with_no_pdf_is_flagged_for_the_warning_colour_and_cannot_be_ticked(api):
    login(api, "bob")
    row = lines(api, "S00124")[12]  # RS-1 has no PDF
    assert row["pdf"]["files"] == [] and row["pdf"]["selected"] is None
    assert row["disabled"] is True and row["disabled_kind"] == "no_label"
    assert "No label PDF found for item code RS-1" in row["disabled_reason"]


def test_zero_quantity_is_grey_and_no_pdf_wins_when_both_apply(api):
    login(api, "bob")
    rows = lines(api, "S00125")
    assert rows[15]["disabled"] and rows[15]["disabled_kind"] == "no_qty" and rows[15]["pdf"]["files"]  # has PDFs
    assert rows[16]["disabled_kind"] == "no_label"  # RS-1: no PDF, qty 3


def test_the_cached_odoo_result_follows_the_saved_list_not_a_stale_copy(api):
    from tests.helpers import make_pdf

    login(api, "bob")
    assert lines(api, "S00124")[12]["disabled"] is True
    make_pdf(api.labels / "01 SAWO/Z/RS-1.pdf", "RS-1")
    api.post("/api/labels/locations/1/fetch")  # saved into the list
    assert lines(api, "S00124")[12]["disabled"] is False  # the same cached SO now matches the new file


def test_so_unknown_is_404_and_user_without_access_cannot_see_it(api):
    login(api, "bob")
    assert api.get("/api/so/NOPE").status_code == 404
    api.odoo.hide_so_from = {8}
    assert api.get("/api/so/S00123?refresh=true").status_code == 404


def test_cache_is_per_user(api):
    login(api, "alice")
    assert api.get("/api/so/S00123").status_code == 200
    api.post("/api/auth/logout")
    api.odoo.hide_so_from = {8}
    login(api, "bob")
    assert api.get("/api/so/S00123").status_code == 404  # alice's cached copy is not served to bob


def test_limited_access_shows_not_accessible_lines_only(api):
    login(api, "bob")
    api.odoo.deny = {"sale.order.line"}
    groups = {g["id"]: g for g in api.get("/api/so/S00123").json()["groups"]}
    assert groups["lines"]["status"] == "not_accessible" and groups["header"]["status"] == "ok"


def test_audit_log_records_login_and_search(api, env):
    from app.db import SessionLocal
    from app.models import AuditEvent

    login(api, "alice")
    api.get("/api/so/S00123")
    db = SessionLocal()
    events = {e.event for e in db.query(AuditEvent).all()}
    db.close()
    assert {"login", "search"} <= events


def test_the_roles_list_shows_each_persons_email_from_odoo(api):
    from tests.conftest import login
    login(api, "alice")  # alice has an email on her Odoo profile
    login(api, "bob")    # bob has none and his login is not an address: blank
    login(api, "alice")
    users = {u["login"]: u for u in api.get("/api/auth/users").json()}
    assert users["alice"]["email"] == "alice@sawo.test" and users["alice"]["name"] == "Alice Admin"
    assert users["bob"]["email"] == ""
