"""The ONLY door to Odoo. Read-only by construction (guideline rule 1, section 4.1).

Public surface is exactly: authenticate, search_read, read, search, fields_get, read_group.
Anything else raises ForbiddenOdooMethod. A unit test enumerates this surface.
"""
from __future__ import annotations

from typing import Any, Iterable

from .errors import ForbiddenOdooMethod, OdooAuthError
from .transports import ALLOWED_METHODS, TRANSPORTS, Transport, assert_allowed


class OdooReadClient:
    def __init__(self, transport: Transport, db: str, *, login: str = "", secret: str = "", uid: int | None = None):
        self._transport = transport
        self._db = db
        self._login = login
        self._secret = secret  # kept in memory only; never logged, never in repr
        self._uid = uid

    def __repr__(self) -> str:  # never leak credentials via logs/tracebacks
        return f"<OdooReadClient transport={self._transport.name} db={self._db} uid={self._uid}>"

    def __getattr__(self, name: str):
        # Reached only for attributes that do not exist: turn write-ish probes into a clear refusal.
        if name.startswith("__") and name.endswith("__"):  # copy/pickle protocol probes
            raise AttributeError(name)
        raise ForbiddenOdooMethod(f"{name!r} is not available: this client is read-only")

    @property
    def uid(self) -> int | None:
        return self._uid

    @property
    def transport_name(self) -> str:
        return self._transport.name

    # ---- public, allow-listed surface -------------------------------------------------------

    def authenticate(self, login: str, secret: str) -> int:
        if not login or not secret:
            raise OdooAuthError("Login and password/API key are required")
        uid = self._transport.authenticate(self._db, login, secret)
        self._login, self._secret, self._uid = login, secret, uid
        return uid

    def search_read(self, model: str, domain: list | None = None, fields: Iterable[str] | None = None, *,
                    limit: int | None = None, offset: int = 0, order: str | None = None,
                    context: dict | None = None) -> list[dict]:
        params: dict[str, Any] = {"domain": domain or [], "fields": list(fields or [])}
        if limit is not None:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        if order:
            params["order"] = order
        return self._call(model, "search_read", params, context) or []

    def read(self, model: str, ids: list[int], fields: Iterable[str] | None = None, *,
             context: dict | None = None) -> list[dict]:
        if not ids:
            return []
        return self._call(model, "read", {"ids": list(ids), "fields": list(fields or [])}, context) or []

    def search(self, model: str, domain: list | None = None, *, limit: int | None = None, offset: int = 0,
               order: str | None = None) -> list[int]:
        params: dict[str, Any] = {"domain": domain or []}
        if limit is not None:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        if order:
            params["order"] = order
        return self._call(model, "search", params) or []

    def fields_get(self, model: str, attributes: list[str] | None = None) -> dict[str, dict]:
        return self._call(model, "fields_get", {"attributes": attributes or ["string", "type", "relation"]}) or {}

    def read_group(self, model: str, domain: list, fields: list[str], groupby: list[str], *,
                   limit: int | None = None) -> list[dict]:
        params: dict[str, Any] = {"domain": domain, "fields": fields, "groupby": groupby}
        if limit is not None:
            params["limit"] = limit
        return self._call(model, "read_group", params) or []

    # ---- internals ----------------------------------------------------------------------------

    def _call(self, model: str, method: str, params: dict, context: dict | None = None) -> Any:
        assert_allowed(method)  # guard 1 (guard 2 lives inside each transport)
        if self._uid is None:
            raise OdooAuthError("Not authenticated")
        if context:
            params = {**params, "context": context}
        return self._transport.call(self._db, self._uid, self._login, self._secret, model, method, params)


def make_client(transport_name: str, base_url: str, db: str, *, verify: bool = True, timeout: float = 30.0,
                login: str = "", secret: str = "", uid: int | None = None) -> OdooReadClient:
    cls = TRANSPORTS[transport_name]
    return OdooReadClient(cls(base_url, verify, timeout), db, login=login, secret=secret, uid=uid)


__all__ = ["OdooReadClient", "make_client", "ALLOWED_METHODS"]
