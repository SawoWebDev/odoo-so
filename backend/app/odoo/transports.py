"""Swappable Odoo transports (guideline 4.2).

A transport only knows how to authenticate and how to execute ONE allow-listed read method.
Every transport re-checks the allow-list, so the guard holds even if a transport is used directly.
"""
from __future__ import annotations

import itertools
import time
import xmlrpc.client
from typing import Any, Protocol

import httpx

from .errors import (
    ForbiddenOdooMethod,
    OdooAccessError,
    OdooAuthError,
    OdooConnectionError,
    OdooError,
    OdooMissingModel,
)

# The ONLY methods that can ever reach Odoo through this application.
ALLOWED_METHODS: frozenset[str] = frozenset({"search", "search_read", "read", "fields_get", "read_group", "name_get"})

# Positional parameter names per method, so one call shape works for RPC (args+kwargs) and JSON-2 (named body).
POSITIONAL: dict[str, tuple[str, ...]] = {
    "search": ("domain",),
    "search_read": ("domain",),
    "read": ("ids",),
    "fields_get": (),
    "read_group": ("domain", "fields", "groupby"),
    "name_get": ("ids",),
}


def assert_allowed(method: str) -> None:
    if method not in ALLOWED_METHODS:
        raise ForbiddenOdooMethod(f"Odoo method {method!r} is not on the read-only allow-list")


def _classify(name: str, message: str, model: str = "") -> OdooError:
    """Map an Odoo exception name/message to one of our error types. Never echo secrets."""
    low = f"{name} {message}".lower()
    if "accessdenied" in low or "access denied" in low:
        return OdooAuthError("Odoo rejected the credentials")
    if "accesserror" in low or "not allowed to access" in low or "you are not allowed" in low:
        return OdooAccessError(message[:300] or "Access denied by Odoo")
    if "keyerror" in low or ("object" in low and "exist" in low) or ("model" in low and "exist" in low):
        return OdooMissingModel(f"Model {model or '?'} is not available on this Odoo instance")
    return OdooError(f"{name or 'OdooError'}: {message[:300]}")


# Odoo's XML-RPC fault codes (odoo.service.model): 3 = AccessDenied, 4 = AccessError, others = application errors. [VERIFY]
_FAULT_ACCESS_DENIED, _FAULT_ACCESS_ERROR = 3, 4


def _classify_fault(f: xmlrpc.client.Fault, model: str) -> OdooError:
    if f.faultCode == _FAULT_ACCESS_DENIED:
        return OdooAuthError("Odoo rejected the credentials")
    if f.faultCode == _FAULT_ACCESS_ERROR:
        return OdooAccessError(str(f.faultString)[:300])
    text = str(f.faultString or "").strip()
    last = text.splitlines()[-1] if text else ""  # tracebacks end with "ExceptionName: message"
    name, _, msg = last.partition(":")
    return _classify(name.strip(), msg.strip() or last, model)


class Transport(Protocol):
    name: str

    def authenticate(self, db: str, login: str, secret: str) -> int: ...

    def call(self, db: str, uid: int, login: str, secret: str, model: str, method: str, params: dict) -> Any: ...


class _Http:
    def __init__(self, base_url: str, verify: bool, timeout: float, retries: int = 2):
        self.base = base_url.rstrip("/")
        self.retries = retries
        self.client = httpx.Client(verify=verify, timeout=timeout, follow_redirects=False)

    def post(self, path: str, *, retry: bool, **kwargs) -> httpx.Response:
        attempts = (self.retries + 1) if retry else 1
        last: Exception | None = None
        for i in range(attempts):
            try:
                r = self.client.post(self.base + path, **kwargs)
                if r.status_code >= 502 and i < attempts - 1:
                    time.sleep(0.4 * (i + 1))
                    continue
                return r
            except httpx.HTTPError as e:  # connection, timeout, protocol
                last = e
                if i < attempts - 1:
                    time.sleep(0.4 * (i + 1))
        raise OdooConnectionError(f"Cannot reach Odoo: {type(last).__name__}")


class JsonRpcTransport:
    """Odoo 14-18: /jsonrpc with common.authenticate + object.execute_kw."""

    name = "jsonrpc"
    _ids = itertools.count(1)

    def __init__(self, base_url: str, verify: bool = True, timeout: float = 30.0):
        self.http = _Http(base_url, verify, timeout)

    def _rpc(self, service: str, method: str, args: list, *, retry: bool, model: str = "") -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": next(self._ids),
        }
        r = self.http.post("/jsonrpc", json=payload, retry=retry)
        if r.status_code == 404:
            raise OdooConnectionError("/jsonrpc endpoint not found on this Odoo")
        try:
            body = r.json()
        except ValueError:
            raise OdooConnectionError(f"Unexpected non-JSON reply from Odoo (HTTP {r.status_code})")
        if "error" in body:
            data = body["error"].get("data") or {}
            raise _classify(data.get("name", ""), data.get("message") or body["error"].get("message", ""), model)
        return body.get("result")

    def version(self) -> dict:
        return self._rpc("common", "version", [], retry=True)

    def authenticate(self, db: str, login: str, secret: str) -> int:
        uid = self._rpc("common", "authenticate", [db, login, secret, {}], retry=False)
        if not uid:
            raise OdooAuthError("Invalid Odoo login or password/API key")
        return int(uid)

    def call(self, db, uid, login, secret, model, method, params):
        assert_allowed(method)
        params = dict(params)
        args = [params.pop(n) for n in POSITIONAL[method] if n in params]
        return self._rpc("object", "execute_kw", [db, uid, secret, model, method, args, params], retry=True, model=model)


class XmlRpcTransport:
    """Odoo 14-18: /xmlrpc/2/common + /xmlrpc/2/object (sent through httpx so timeouts/TLS are uniform)."""

    name = "xmlrpc"

    def __init__(self, base_url: str, verify: bool = True, timeout: float = 30.0):
        self.http = _Http(base_url, verify, timeout)

    def _rpc(self, endpoint: str, method: str, args: tuple, *, retry: bool, model: str = "") -> Any:
        body = xmlrpc.client.dumps(args, methodname=method, allow_none=True)
        r = self.http.post(f"/xmlrpc/2/{endpoint}", content=body, headers={"Content-Type": "text/xml"}, retry=retry)
        if r.status_code == 404:
            raise OdooConnectionError("/xmlrpc/2 endpoint not found on this Odoo")
        try:
            result, _ = xmlrpc.client.loads(r.content)
        except xmlrpc.client.Fault as f:
            raise _classify_fault(f, model)
        except Exception:
            raise OdooConnectionError(f"Unexpected reply from Odoo XML-RPC (HTTP {r.status_code})")
        return result[0] if result else None

    def version(self) -> dict:
        return self._rpc("common", "version", (), retry=True)

    def authenticate(self, db: str, login: str, secret: str) -> int:
        uid = self._rpc("common", "authenticate", (db, login, secret, {}), retry=False)
        if not uid:
            raise OdooAuthError("Invalid Odoo login or password/API key")
        return int(uid)

    def call(self, db, uid, login, secret, model, method, params):
        assert_allowed(method)
        params = dict(params)
        args = [params.pop(n) for n in POSITIONAL[method] if n in params]
        return self._rpc("object", "execute_kw", (db, uid, secret, model, method, args, params), retry=True, model=model)


class Json2Transport:
    """Odoo 19+: POST /json/2/<model>/<method> with a per-user API key as bearer token. [VERIFY]

    The JSON-2 API has no 'authenticate' call, so identity is established by reading the user's own
    res.users record by login. Because the key itself identifies the user server-side, every later call
    still runs with that user's rights; the uid is only used for the app role lookup.
    """

    name = "json2"

    def __init__(self, base_url: str, verify: bool = True, timeout: float = 30.0):
        self.http = _Http(base_url, verify, timeout)

    def _headers(self, db: str, secret: str) -> dict:
        h = {"Authorization": f"bearer {secret}", "Content-Type": "application/json"}
        if db:
            h["X-Odoo-Database"] = db
        return h

    def _post(self, db, secret, model, method, body, *, retry) -> Any:
        r = self.http.post(f"/json/2/{model}/{method}", json=body, headers=self._headers(db, secret), retry=retry)
        if r.status_code == 401:
            raise OdooAuthError("Odoo rejected the API key")
        if r.status_code == 404:
            if "<html" in r.text[:200].lower():
                raise OdooConnectionError("/json/2 endpoint not available on this Odoo")
            raise OdooMissingModel(f"Model {model} is not available on this Odoo instance")
        if r.status_code == 403:
            raise OdooAccessError("Access denied by Odoo")
        try:
            data = r.json()
        except ValueError:
            raise OdooConnectionError(f"Unexpected non-JSON reply from Odoo (HTTP {r.status_code})")
        if r.status_code >= 400:
            raise _classify(str(data.get("name", "")), str(data.get("message", "")), model)
        return data

    def authenticate(self, db: str, login: str, secret: str) -> int:
        rows = self._post(
            db, secret, "res.users", "search_read",
            {"domain": [["login", "=", login]], "fields": ["id", "login"], "limit": 1}, retry=False,
        )
        if not rows:
            raise OdooAuthError("Invalid Odoo login or API key")
        return int(rows[0]["id"])

    def call(self, db, uid, login, secret, model, method, params):
        assert_allowed(method)
        return self._post(db, secret, model, method, dict(params), retry=True)


TRANSPORTS = {"jsonrpc": JsonRpcTransport, "xmlrpc": XmlRpcTransport, "json2": Json2Transport}


def detect_server_version(base_url: str, verify: bool = True, timeout: float = 15.0) -> dict:
    """Best-effort, unauthenticated version probe. Returns {'major': int|None, 'raw': dict, 'source': str}."""
    for cls in (JsonRpcTransport, XmlRpcTransport):
        try:
            v = cls(base_url, verify, timeout).version()
            info = v.get("server_version_info") or []
            major = int(info[0]) if info else None
            if major is None and v.get("server_version"):
                major = int(str(v["server_version"]).split(".")[0].replace("saas~", ""))
            return {"major": major, "raw": v, "source": cls.name}
        except (OdooError, ValueError, TypeError):
            continue
    try:  # no legacy RPC at all (possible on 19+): fall back to the web client probe
        r = httpx.post(base_url.rstrip("/") + "/web/webclient/version_info", json={"jsonrpc": "2.0", "method": "call", "params": {}},
                       verify=verify, timeout=timeout)
        v = (r.json() or {}).get("result") or {}
        info = v.get("server_version_info") or []
        return {"major": int(info[0]) if info else None, "raw": v, "source": "webclient"}
    except Exception:
        return {"major": None, "raw": {}, "source": "none"}


def candidate_transports(configured: str, major: int | None) -> list[str]:
    """Order in which to try transports at login."""
    configured = (configured or "auto").lower()
    if configured != "auto":
        return [configured]
    if major is not None and major >= 19:
        return ["json2", "jsonrpc", "xmlrpc"]
    return ["jsonrpc", "xmlrpc", "json2"]
