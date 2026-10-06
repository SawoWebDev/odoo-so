"""A small stand-in for an Odoo server, for demos and for testing the real HTTP transports end to end.

Speaks /jsonrpc, /xmlrpc/2/* and /json/2/<model>/<method> on top of the in-memory dataset used by the unit tests.
It is READ-ONLY by construction: it only dispatches through FakeTransport, which enforces the same allow-list.

    python -m scripts.mock_odoo --port 8069 [--version 17]
Logins: alice / pw-alice, bob / pw-bob, carol / pw-carol.   Orders: S00123 (make-to-order), S00124 (resale).
"""
from __future__ import annotations

import argparse
import xmlrpc.client

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.odoo.errors import ForbiddenOdooMethod, OdooAccessError, OdooAuthError, OdooError, OdooMissingModel
from app.odoo.transports import POSITIONAL
from tests.fake_odoo import FakeOdoo, FakeTransport, build_dataset


def create_mock_app(odoo: FakeOdoo | None = None, version: tuple[int, int] = (17, 0)) -> FastAPI:
    odoo = odoo or build_dataset(FakeOdoo())
    for uid, login in ((8, "bob"), (9, "carol")):  # the dataset ships alice; make the others readable too
        if not any(r["id"] == uid for r in odoo.data.get("res.users", [])):
            odoo.add("res.users", id=uid, name=login.title(), login=login)
    t = FakeTransport(odoo)
    app = FastAPI(docs_url=None, openapi_url=None)
    app.state.odoo = odoo
    app.state.wire_methods = []  # every method that reached the "server": tests assert these are reads only
    ver = {"server_version": f"{version[0]}.{version[1]}", "server_version_info": [version[0], version[1], 0, "final", 0, ""],
           "protocol_version": 1}

    def user_for(uid: int, secret: str) -> bool:
        return any(u[0] == uid and u[1] == secret for u in odoo.users.values())

    def run(uid: int, secret: str, model: str, method: str, args: list, kwargs: dict):
        if not user_for(uid, secret):
            raise OdooAuthError("denied")
        params = dict(kwargs)
        for name, value in zip(POSITIONAL.get(method, ()), args):
            params[name] = value
        app.state.wire_methods.append(method)
        return t.call("db", uid, "", secret, model, method, params)

    def rpc_error(e: Exception) -> dict:
        name = {OdooAccessError: "odoo.exceptions.AccessError", OdooAuthError: "odoo.exceptions.AccessDenied",
                OdooMissingModel: "builtins.KeyError"}.get(type(e), "odoo.exceptions.UserError")
        return {"code": 200, "message": "Odoo Server Error", "data": {"name": name, "message": str(e), "debug": "..."}}

    @app.post("/jsonrpc")
    async def jsonrpc(req: Request):
        body = await req.json()
        p = body["params"]
        a = p["args"]
        try:
            if p["service"] == "common" and p["method"] == "version":
                res = ver
            elif p["service"] == "common" and p["method"] == "authenticate":
                u = odoo.users.get(a[1])
                res = u[0] if u and u[1] == a[2] else False
            elif p["service"] == "object" and p["method"] == "execute_kw":
                res = run(a[1], a[2], a[3], a[4], a[5], a[6])
            else:
                raise OdooError("unknown service")
        except (OdooError, ForbiddenOdooMethod) as e:
            return JSONResponse({"jsonrpc": "2.0", "id": body.get("id"), "error": rpc_error(e)})
        return JSONResponse({"jsonrpc": "2.0", "id": body.get("id"), "result": res})

    @app.post("/xmlrpc/2/common")
    async def xml_common(req: Request):
        params, method = xmlrpc.client.loads(await req.body())
        if method == "version":
            out = ver
        else:
            u = odoo.users.get(params[1])
            out = u[0] if u and u[1] == params[2] else False
        return Response(xmlrpc.client.dumps((out,), allow_none=True), media_type="text/xml")

    @app.post("/xmlrpc/2/object")
    async def xml_object(req: Request):
        params, _ = xmlrpc.client.loads(await req.body())
        db, uid, secret, model, method, args, kwargs = params
        try:
            res = run(uid, secret, model, method, args, kwargs)
            return Response(xmlrpc.client.dumps((res,), allow_none=True), media_type="text/xml")
        except OdooAuthError as e:
            fault = xmlrpc.client.Fault(3, str(e))
        except OdooAccessError as e:
            fault = xmlrpc.client.Fault(4, str(e))
        except OdooMissingModel:
            fault = xmlrpc.client.Fault(1, f"Traceback (most recent call last):\n  ...\nKeyError: '{model}'")
        except OdooError as e:
            fault = xmlrpc.client.Fault(1, f"Traceback (most recent call last):\n  ...\nodoo.exceptions.UserError: {e}")
        return Response(xmlrpc.client.dumps(fault, allow_none=True), media_type="text/xml")

    @app.post("/json/2/{model}/{method}")
    async def json2(model: str, method: str, req: Request):
        key = (req.headers.get("authorization") or "")[7:]
        user = next((u for u in odoo.users.values() if u[1] == key), None)
        if not user:
            return JSONResponse({"name": "odoo.exceptions.AccessDenied", "message": "Invalid apikey"}, status_code=401)
        body = await req.json()
        try:
            return JSONResponse(run(user[0], key, model, method, [], body))
        except OdooAccessError as e:
            return JSONResponse({"name": "odoo.exceptions.AccessError", "message": str(e)}, status_code=403)
        except OdooMissingModel:
            return JSONResponse({"name": "builtins.KeyError", "message": model}, status_code=404)
        except (OdooError, ForbiddenOdooMethod) as e:
            return JSONResponse({"name": "odoo.exceptions.UserError", "message": str(e)}, status_code=422)

    return app


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8069)
    ap.add_argument("--version", type=int, default=17)
    ns = ap.parse_args()
    uvicorn.run(create_mock_app(version=(ns.version, 0)), host="0.0.0.0", port=ns.port, log_level="warning")
