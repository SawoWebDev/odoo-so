"""Acceptance test 1: nothing but read methods can be called through the connector."""
import pytest

from app.odoo.client import OdooReadClient
from app.odoo.errors import ForbiddenOdooMethod
from app.odoo.transports import ALLOWED_METHODS, Json2Transport, JsonRpcTransport, XmlRpcTransport, assert_allowed
from tests.fake_odoo import FakeOdoo, FakeTransport

WRITE_LIKE = ["create", "write", "unlink", "copy", "action_confirm", "button_validate", "action_cancel", "execute",
              "execute_kw", "message_post", "name_create", "_write", "toggle_active", "init", "invalidate_cache",
              "call_kw", "with_user", "sudo", "browse", "exists", "load", "import_data", "check_access_rights"]


def test_public_surface_is_exactly_the_read_methods():
    public = {n for n in dir(OdooReadClient) if not n.startswith("_") and callable(getattr(OdooReadClient, n))}
    assert public == {"authenticate", "search_read", "read", "search", "fields_get", "read_group"}


@pytest.mark.parametrize("name", WRITE_LIKE)
def test_write_like_attributes_are_refused(name):
    client = FakeOdoo().client("alice")
    with pytest.raises(ForbiddenOdooMethod):
        getattr(client, name)


@pytest.mark.parametrize("name", WRITE_LIKE)
def test_internal_call_refuses_non_allow_listed_methods(name):
    client = FakeOdoo().client("alice")
    with pytest.raises(ForbiddenOdooMethod):
        client._call("res.partner", name, {})


@pytest.mark.parametrize("name", WRITE_LIKE)
def test_assert_allowed_rejects(name):
    with pytest.raises(ForbiddenOdooMethod):
        assert_allowed(name)


def test_allow_list_is_only_reads():
    assert ALLOWED_METHODS == {"search", "search_read", "read", "fields_get", "read_group", "name_get"}


@pytest.mark.parametrize("cls", [JsonRpcTransport, XmlRpcTransport, Json2Transport])
@pytest.mark.parametrize("method", ["write", "create", "unlink", "action_confirm"])
def test_every_real_transport_refuses_writes_before_any_network_call(cls, method):
    t = cls("http://odoo.invalid", True, 1.0)  # would raise a connection error if it ever tried the network
    with pytest.raises(ForbiddenOdooMethod):
        t.call("db", 1, "u", "secret", "sale.order", method, {"ids": [1]})


def test_fake_transport_also_guarded_and_records_calls():
    o = FakeOdoo()
    t = FakeTransport(o)
    with pytest.raises(ForbiddenOdooMethod):
        t.call("db", 1, "u", "s", "sale.order", "write", {})
    assert o.calls == []


def test_client_repr_never_contains_the_secret():
    c = FakeOdoo().client("alice")
    assert "pw-alice" not in repr(c) and "pw-alice" not in str(c)
