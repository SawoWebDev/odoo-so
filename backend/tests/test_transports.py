"""The three real HTTP transports against a mock Odoo server: auth, reads, error mapping, and nothing but reads on the wire."""
import socket
import threading
import time

import pytest
import uvicorn

from app.config import Settings, get_settings
from app.odoo.client import make_client
from app.odoo.connect import Connector
from app.odoo.errors import OdooAuthError, OdooConnectionError
from app.odoo.transports import candidate_transports, detect_server_version
from app.resolver.resolver import SOResolver
from scripts.mock_odoo import create_mock_app
from tests.fake_odoo import FakeOdoo, build_dataset


@pytest.fixture
def mock():
    odoo = build_dataset(FakeOdoo())
    holder = {}

    def start(version=(17, 0)):
        app = create_mock_app(odoo, version)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        th = threading.Thread(target=server.run, daemon=True)
        th.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        holder.update(server=server, thread=th)
        return f"http://127.0.0.1:{port}", app, odoo

    yield start
    if holder:
        holder["server"].should_exit = True
        holder["thread"].join(timeout=5)


@pytest.mark.parametrize("transport", ["jsonrpc", "xmlrpc", "json2"])
def test_each_transport_authenticates_reads_and_resolves_the_same_so(mock, transport):
    url, app, odoo = mock()
    c = make_client(transport, url, "db", timeout=10)
    assert c.authenticate("alice", "pw-alice") == 7
    res = SOResolver(c, get_settings()).resolve("S00123")
    statuses = {g["id"]: g["status"] for g in res["groups"]}
    assert set(statuses.values()) == {"ok"}, statuses
    lines = next(g for g in res["groups"] if g["id"] == "lines")["rows"][0]["fields"]
    assert lines["line.product.code"]["display"] == "220-TD" and lines["line.qty"]["uom"] == "Units"
    assert [g["id"] for g in res["groups"]] == ["header", "references", "lines"]
    # defence in depth: what physically crossed the wire is reads only
    assert set(app.state.wire_methods) <= {"search_read", "read", "search", "fields_get", "read_group"}
    assert app.state.wire_methods


@pytest.mark.parametrize("transport", ["jsonrpc", "xmlrpc", "json2"])
def test_wrong_password_is_an_auth_error(mock, transport):
    url, _, _ = mock()
    with pytest.raises(OdooAuthError):
        make_client(transport, url, "db").authenticate("alice", "nope")


@pytest.mark.parametrize("transport", ["jsonrpc", "xmlrpc", "json2"])
def test_access_errors_and_missing_models_map_to_group_statuses(mock, transport):
    url, _, odoo = mock()
    odoo.deny = {"sale.order.line"}
    c = make_client(transport, url, "db")
    c.authenticate("bob", "pw-bob")
    groups = {g["id"]: g["status"] for g in SOResolver(c, get_settings()).resolve("S00123")["groups"]}
    assert groups == {"header": "ok", "references": "not_accessible", "lines": "not_accessible"}
    odoo.deny = set()
    odoo.missing = {"sale.order.line"}
    groups = {g["id"]: g["status"] for g in SOResolver(c, get_settings()).resolve("S00123")["groups"]}
    assert groups == {"header": "ok", "references": "not_installed", "lines": "not_installed"}


def test_unreachable_server_is_a_connection_error():
    c = make_client("jsonrpc", "http://127.0.0.1:1", "db", timeout=1)
    with pytest.raises(OdooConnectionError):
        c.authenticate("a", "b")


def test_version_detection_and_transport_order(mock):
    url, _, _ = mock((19, 0))
    info = detect_server_version(url)
    assert info["major"] == 19
    assert candidate_transports("auto", 19)[0] == "json2"
    assert candidate_transports("auto", 17)[0] == "jsonrpc"
    assert candidate_transports("xmlrpc", 19) == ["xmlrpc"]


def test_connector_auto_picks_a_working_transport_and_authenticates(mock):
    url, _, _ = mock((17, 0))
    s = Settings(odoo_url=url, odoo_db="db", odoo_transport="auto")
    c = Connector(s).connect("alice", "pw-alice")
    assert c.uid == 7 and c.transport_name == "jsonrpc"
    with pytest.raises(OdooAuthError):
        Connector(s).connect("alice", "bad")


def test_connector_on_odoo_19_prefers_json2(mock):
    from app.odoo import connect

    connect._version_cache.clear()
    url, _, _ = mock((19, 0))
    c = Connector(Settings(odoo_url=url, odoo_db="db", odoo_transport="auto")).connect("alice", "pw-alice")
    assert c.transport_name == "json2" and c.uid == 7
