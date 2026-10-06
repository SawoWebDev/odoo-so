"""Builds per-user Odoo clients. Replaceable in tests via the `get_connector` dependency."""
from __future__ import annotations

from ..config import Settings
from .client import OdooReadClient, make_client
from .errors import OdooAuthError, OdooConnectionError, OdooError
from .transports import candidate_transports, detect_server_version

_version_cache: dict[str, dict] = {}


class Connector:
    def __init__(self, settings: Settings):
        self.settings = settings

    def server_info(self) -> dict:
        s = self.settings
        if s.odoo_url not in _version_cache:
            _version_cache[s.odoo_url] = detect_server_version(s.odoo_url, s.odoo_verify_ssl)
        return _version_cache[s.odoo_url]

    def _make(self, transport: str, login: str = "", secret: str = "", uid: int | None = None) -> OdooReadClient:
        s = self.settings
        return make_client(transport, s.odoo_url, s.odoo_db, verify=s.odoo_verify_ssl, timeout=s.odoo_timeout_s,
                           login=login, secret=secret, uid=uid)

    def connect(self, login: str, secret: str) -> OdooReadClient:
        """Authenticate as the user (never a shared account). Tries transports in order of likelihood."""
        s = self.settings
        if not s.odoo_url:
            raise OdooConnectionError("ODOO_URL is not configured")
        order = candidate_transports(s.odoo_transport, None if s.odoo_transport != "auto" else self.server_info().get("major"))
        auth_err: OdooError | None = None
        conn_err: OdooError | None = None
        for name in order:
            client = self._make(name)
            try:
                client.authenticate(login, secret)
                return client
            except OdooAuthError as e:
                auth_err = e
            except OdooConnectionError as e:  # this transport is not offered by the server: try the next
                conn_err = e
        if auth_err:
            raise OdooAuthError("Invalid Odoo login or password/API key")
        raise conn_err or OdooConnectionError("Cannot reach Odoo")

    def from_session(self, transport: str, login: str, secret: str, uid: int) -> OdooReadClient:
        return self._make(transport, login, secret, uid)


def get_connector() -> Connector:
    from ..config import get_settings

    return Connector(get_settings())
