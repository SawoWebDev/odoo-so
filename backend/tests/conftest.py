import os
import tempfile

import pytest

# Environment must be in place before `app` modules read settings.
_ROOT = tempfile.mkdtemp(prefix="sticker_tests_")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_ROOT}/boot.db", "STORAGE_DIR": f"{_ROOT}/storage", "APP_SECRET_KEY": "test-secret-key",
    "INITIAL_ADMIN_LOGINS": "alice", "DEFAULT_ROLE": "printer", "REDIS_URL": "", "ODOO_URL": "http://odoo.invalid",
    "ODOO_DB": "db", "LOGIN_MAX_FAILS": "3", "LOGIN_LOCKOUT_SECONDS": "600", "SESSION_IDLE_SECONDS": "1800",
})

from fastapi.testclient import TestClient  # noqa: E402

from tests.fake_odoo import FakeOdoo, FakeTransport, build_dataset  # noqa: E402


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
def env(tmp_path):
    """Fresh DB, storage, session store, limiter and caches for every test."""
    from app import security
    from app.config import get_settings
    from app.db import reset_engine
    from app.resolver.service import fields_cache, so_cache

    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/t.db"
    os.environ["STORAGE_DIR"] = str(tmp_path / "storage")
    get_settings.cache_clear()
    reset_engine()
    security.set_session_store(security.MemorySessionStore())
    security.set_limiter(security.LoginLimiter())
    so_cache.clear()
    fields_cache.clear()
    yield tmp_path
    reset_engine()


@pytest.fixture
def api(env, odoo):
    from app.main import app
    from app.odoo.connect import get_connector

    app.dependency_overrides[get_connector] = lambda: FakeConnector(odoo)
    with TestClient(app, headers={"X-Requested-With": "sticker-app"}) as c:
        c.odoo = odoo
        yield c
    app.dependency_overrides.clear()


def login(client, user="alice"):
    pw = {"alice": "pw-alice", "bob": "pw-bob", "carol": "pw-carol"}[user]
    r = client.post("/api/auth/login", json={"login": user, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def select_line(resolved_public: dict, line_id: int = 11, keys: list[str] | None = None) -> dict:
    """Selection basket as the UI builds it: every field of the chosen line row + SO header fields."""
    items = []
    for g in resolved_public["groups"]:
        for r in g["rows"]:
            if r["row_id"] == f"lines:{line_id}" or g["id"] == "header":
                items.append({"row": r["row_id"], "keys": keys if (keys and g["id"] != "header") else list(r["fields"])})
    return {"items": items}
