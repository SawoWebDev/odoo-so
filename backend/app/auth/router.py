from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..deps import COOKIE, CurrentUser, ROLE_RANK, audit, current_user, require_role
from ..models import AppUser, utcnow
from ..odoo.connect import Connector, get_connector
from ..odoo.errors import OdooAuthError, OdooConnectionError, OdooError
from ..security import encrypt_secret, get_limiter, get_session_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    login: str
    password: SecretStr  # also accepts an Odoo API key; SecretStr keeps it out of reprs and logs


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings), connector: Connector = Depends(get_connector)):
    login_name = body.login.strip()
    key = f"{_client_ip(request)}|{login_name.lower()}"
    limiter = get_limiter()
    wait = limiter.retry_after(key, settings)
    if wait:
        raise HTTPException(429, f"Too many failed attempts. Try again in {wait} seconds.", headers={"Retry-After": str(wait)})
    secret = body.password.get_secret_value()
    try:
        client = connector.connect(login_name, secret)
    except OdooAuthError:
        limiter.failed(key, settings)
        audit(db, None, "login_failed", detail=f"login={login_name}")
        raise HTTPException(401, "Invalid Odoo login or password/API key")
    except OdooConnectionError as e:
        raise HTTPException(502, f"Cannot reach Odoo: {e}")
    except OdooError as e:
        raise HTTPException(502, f"Odoo error: {e}")
    limiter.succeeded(key)

    name, email = login_name, ""
    try:
        rec = client.read("res.users", [client.uid], ["name", "email"])
        if rec:
            name = rec[0].get("name") or login_name
            email = rec[0].get("email") or ""
    except OdooError:
        pass
    if not email and "@" in login_name:
        email = login_name  # many Odoo logins are the person's email address

    user = db.get(AppUser, client.uid)
    if user is None:
        role = "template_admin" if login_name.lower() in settings.admin_logins else settings.default_role
        user = AppUser(odoo_uid=client.uid, odoo_login=login_name, display_name=name, app_role=role)
        db.add(user)
    elif login_name.lower() in settings.admin_logins and user.app_role != "template_admin":
        user.app_role = "template_admin"
    user.odoo_login, user.display_name, user.email, user.last_login = login_name, name, email, utcnow()
    db.commit()

    sid = get_session_store().create(
        {"uid": client.uid, "login": login_name, "name": name, "transport": client.transport_name,
         "cred": encrypt_secret(secret, settings)},
        settings.session_idle_seconds,
    )
    response.set_cookie(COOKIE, sid, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")
    audit(db, client.uid, "login")
    return {"uid": client.uid, "login": login_name, "name": name, "role": user.app_role}


@router.post("/logout")
def logout(request: Request, response: Response):
    sid = request.cookies.get(COOKIE)
    if sid:
        get_session_store().delete(sid)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)):
    return {"uid": user.uid, "login": user.login, "name": user.name, "role": user.role}


class RoleIn(BaseModel):
    role: str


@router.get("/users")
def list_users(user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db)):
    return [{"uid": u.odoo_uid, "login": u.odoo_login, "name": u.display_name, "role": u.app_role,
             "email": u.email or (u.odoo_login if "@" in u.odoo_login else ""),
             "last_login": u.last_login.isoformat() if u.last_login else None}
            for u in db.query(AppUser).order_by(AppUser.odoo_login)]


@router.put("/users/{uid}/role")
def set_role(uid: int, body: RoleIn, user: CurrentUser = Depends(require_role("template_admin")),
             db: Session = Depends(get_db)):
    if body.role not in ROLE_RANK:
        raise HTTPException(422, "role must be viewer, printer or template_admin")
    target = db.get(AppUser, uid)
    if not target:
        raise HTTPException(404, "Unknown user (they must sign in once first)")
    target.app_role = body.role
    db.commit()
    return {"uid": uid, "role": body.role}
