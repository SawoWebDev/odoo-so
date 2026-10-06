import os
import tempfile

import pytest

# Environment must be in place before `app` modules read settings.
_ROOT = tempfile.mkdtemp(prefix="sticker_tests_")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_ROOT}/boot.db", "STORAGE_DIR": f"{_ROOT}/storage", "APP_SECRET_KEY": "test-secret-key",
    "INITIAL_ADMIN_LOGINS": "alice", "DEFAULT_ROLE": "printer", "REDIS_URL": "", "ODOO_URL": "http://odoo.invalid",
    "ODOO_DB": "db", "LOGIN_MAX_FAILS": "3", "LOGIN_LOCKOUT_SECONDS": "600", "SESSION_IDLE_SECONDS": "1800",
    "LABEL_MOUNT_DIR": f"{_ROOT}/mnt",
})

from fastapi.testclient import TestClient  # noqa: E402

from tests.fake_odoo import FakeOdoo, FakeTransport, build_dataset  # noqa: E402
from tests.helpers import make_pdf  # noqa: E402

SHARE = "//172.16.0.4/Marketing"
PRINT_URL = "file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/"
PRINT_DIR = "00 MASTERLIST/01 PRINTING FILES"


class FakeConnector:
    def __init__(self, odoo: FakeOdoo):
        self.odoo = odoo

    def connect(self, login, secret):
        from app.odoo.client import OdooReadClient

        c = OdooReadClient(FakeTransport(self.odoo), "db")
        c.authenticate(login, secret)
        return c

    def from_session(self, transport, login, secret, uid):
        from app.odoo.client import OdooReadClient

        return OdooReadClient(FakeTransport(self.odoo), "db", login=login, secret=secret, uid=uid)


@pytest.fixture
def odoo():
    return build_dataset(FakeOdoo())


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh DB, storage, mounted share, session store, limiter and caches for every test."""
    from app import security
    from app.config import get_settings
    from app.db import reset_engine
    from app.labels.index import reset_index
    from app.resolver.service import fields_cache, so_cache

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("LABEL_MOUNT_DIR", str(tmp_path / "mnt"))
    monkeypatch.setenv("LABEL_SHARE", SHARE)
    monkeypatch.setenv("LABEL_DEFAULT_LOCATION", PRINT_URL)
    get_settings.cache_clear()
    reset_engine()
    reset_index()
    security.set_session_store(security.MemorySessionStore())
    security.set_limiter(security.LoginLimiter())
    so_cache.clear()
    fields_cache.clear()
    yield tmp_path
    reset_engine()
    reset_index()
    get_settings.cache_clear()


@pytest.fixture
def labels(env):
    """The printing folder on the 'share': 220-TD exists twice (Individual / Box Stickers); RS-1 has no PDF at all."""
    root = env / "mnt" / PRINT_DIR
    make_pdf(root / "01 SAWO/P1/01 Individual/220-TD.pdf", "INDIVIDUAL 220-TD")
    make_pdf(root / "01 SAWO/P1/02 Box Stickers/220-TD.pdf", "BOX STICKER 220-TD")
    make_pdf(root / "01 SAWO/P1/02 Box Stickers/SET-X -No BG.pdf", "SET-X NO BG")
    return root


@pytest.fixture
def api(env, odoo, labels):
    from app.main import app
    from app.odoo.connect import get_connector

    app.dependency_overrides[get_connector] = lambda: FakeConnector(odoo)
    with TestClient(app, headers={"X-Requested-With": "sticker-app"}) as c:  # startup adds the default location
        c.odoo = odoo
        c.labels = labels
        c.mount = env / "mnt"
        yield c
    app.dependency_overrides.clear()


def login(client, user="alice"):
    pw = {"alice": "pw-alice", "bob": "pw-bob", "carol": "pw-carol"}[user]
    r = client.post("/api/auth/login", json={"login": user, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def make_viewer(client, uid):
    from app.db import SessionLocal
    from app.models import AppUser

    db = SessionLocal()
    db.get(AppUser, uid).app_role = "viewer"
    db.commit()
    db.close()


def file_id(client, name: str, folder_part: str = "") -> int:
    """The saved id of a label file, found through the search endpoint."""
    items = client.get("/api/labels/search", params={"q": f"{name} {folder_part}".strip(), "size": 100}).json()["items"]
    hits = [i for i in items if i["name"].lower() == name.lower()]
    assert len(hits) == 1, (name, folder_part, [(i["folder"], i["name"]) for i in items])
    return hits[0]["id"]
