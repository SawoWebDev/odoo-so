from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..deps import COOKIE, CurrentUser, ROLE_RANK, audit, current_user, require_role
from ..models import AppUser, RoleGrant, utcnow
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
    keys = {login_name.lower(), email.lower()} - {""}
    grants = db.query(RoleGrant).filter(RoleGrant.login.in_(keys)).all() if keys else []
    if user is None:
        role = "template_admin" if keys & settings.admin_logins else (grants[0].role if grants else settings.default_role)
        user = AppUser(odoo_uid=client.uid, odoo_login=login_name, display_name=name, app_role=role)
        db.add(user)
    elif keys & settings.admin_logins and user.app_role != "template_admin":
        user.app_role = "template_admin"
    for g in grants:  # a registration is used up at the first sign-in
        db.delete(g)
    user.odoo_login, user.display_name, user.email, user.last_login = login_name, name, email, utcnow()
    db.commit()

    sid = get_session_store().create(
        {"uid": client.uid, "login": login_name, "name": name, "transport": client.transport_name,
         "cred": encrypt_secret(secret, settings)},
        settings.session_idle_seconds,
    )
    response.set_cookie(COOKIE, sid, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")
    audit(db, client.uid, "login")
    return {"uid": client.uid, "login": login_name, "name": user.shown_name, "role": user.app_role}


@router.post("/logout")
def logout(request: Request, response: Response):
    sid = request.cookies.get(COOKIE)
    if sid:
        get_session_store().delete(sid)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)):
    out = {"uid": user.uid, "login": user.login, "name": user.name, "role": user.role, "viewing_as": None}
    if user.viewing_as:
        out["viewing_as"] = {"admin_name": user.real_name or user.real_login}
    return out


@router.post("/users/{uid}/view-as")
def view_as(uid: int, request: Request, user: CurrentUser = Depends(require_role("template_admin")),
            db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """An admin sees the app exactly as this person would: their role, menus, buttons and their own history. Odoo is still
    read with the admin's own login (the app never has anyone else's password), and nothing can be changed meanwhile."""
    target = db.get(AppUser, uid)
    if not target:
        raise HTTPException(404, "Unknown user (they must sign in once first)")
    if uid == user.real_uid:
        raise HTTPException(422, "That is you.")
    store = get_session_store()
    data = store.get(user.sid, settings.session_idle_seconds)
    data["as"] = {"uid": target.odoo_uid}
    store.update(user.sid, data, settings.session_idle_seconds)
    audit(db, user.real_uid, "view_as_start", detail=target.odoo_login)
    return {"uid": target.odoo_uid, "login": target.odoo_login, "name": target.shown_name, "role": target.app_role,
            "viewing_as": {"admin_name": user.real_name or user.real_login}}


@router.post("/view-as/stop")
def view_as_stop(user: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    store = get_session_store()
    data = store.get(user.sid, settings.session_idle_seconds)
    if data and data.pop("as", None):
        store.update(user.sid, data, settings.session_idle_seconds)
        audit(db, user.real_uid, "view_as_stop", detail=user.login)
    real = db.get(AppUser, user.real_uid)
    return {"uid": user.real_uid, "login": user.real_login, "name": user.real_name,
            "role": real.app_role if real else "viewer", "viewing_as": None}


class RoleIn(BaseModel):
    role: str


def is_main(login: str, email: str, settings: Settings) -> bool:
    """The main admin(s): the logins in INITIAL_ADMIN_LOGINS. They cannot be removed or demoted."""
    return bool({login.lower(), (email or "").lower()} & settings.admin_logins)


class RegisterIn(BaseModel):
    email: str
    role: str = "printer"


class DetailsIn(BaseModel):
    name: str = ""   # empty = use the name from Odoo
    email: str = ""  # empty = use the email from Odoo


@router.put("/users/{uid}/details")
def set_details(uid: int, body: DetailsIn, user: CurrentUser = Depends(require_role("template_admin")),
                db: Session = Depends(get_db)):
    """The name and email shown in this app. Sign-in never overwrites them; they never change anyone's rights."""
    from ..mailer import EMAIL_RE

    target = db.get(AppUser, uid)
    if not target:
        raise HTTPException(404, "Unknown user (they must sign in once first)")
    name, email = " ".join(body.name.split())[:255], body.email.strip().lower()[:255]
    if email and not EMAIL_RE.match(email):
        raise HTTPException(422, f"'{body.email.strip()}' is not a valid email address.")
    before = (target.custom_name, target.custom_email)
    target.custom_name, target.custom_email = name, email
    db.commit()
    if (name, email) != before:
        audit(db, user, "user_edit", detail=f"{target.odoo_login}: name={name or '(from Odoo)'} email={email or '(from Odoo)'}")
    return {"uid": uid, "name": target.shown_name, "email": target.shown_email}


@router.get("/users")
def list_users(user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings)):
    """Everyone who has signed in, plus the people registered who have not signed in yet (pending)."""
    out = []
    for u in db.query(AppUser).order_by(AppUser.odoo_login):
        odoo_email = u.email or (u.odoo_login if "@" in u.odoo_login else "")
        out.append({"uid": u.odoo_uid, "grant_id": None, "login": u.odoo_login, "name": u.shown_name, "role": u.app_role,
                    "email": u.shown_email, "odoo_name": u.display_name, "odoo_email": odoo_email,
                    "custom_name": u.custom_name, "custom_email": u.custom_email,
                    "pending": False, "main": is_main(u.odoo_login, odoo_email, settings), "you": u.odoo_uid == user.uid,
                    "last_login": u.last_login.isoformat() if u.last_login else None})
    for g in db.query(RoleGrant).order_by(RoleGrant.login):
        out.append({"uid": None, "grant_id": g.id, "login": g.login, "name": "", "role": g.role, "email": g.login,
                    "pending": True, "main": False, "you": False, "last_login": None})
    return out


@router.post("/users", status_code=201)
def register_user(body: RegisterIn, user: CurrentUser = Depends(require_role("template_admin")),
                  db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Register a person by email (their Odoo login) with a role, before or after their first sign-in."""
    from ..mailer import EMAIL_RE

    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, f"'{body.email.strip()}' is not a valid email address.")
    if body.role not in ROLE_RANK:
        raise HTTPException(422, "role must be viewer, printer or template_admin")
    existing = (db.query(AppUser).filter((AppUser.odoo_login.ilike(email)) | (AppUser.email.ilike(email))).first())
    if existing:
        if is_main(existing.odoo_login, existing.email, settings) and body.role != "template_admin":
            raise HTTPException(403, "The main admin always stays an admin.")
        existing.app_role = body.role
        db.commit()
        audit(db, user, "role_set", detail=f"{existing.odoo_login} -> {body.role}")
        return {"registered": False, "updated": True, "login": existing.odoo_login, "role": body.role}
    grant = db.query(RoleGrant).filter(RoleGrant.login == email).first()
    if grant:
        grant.role = body.role
    else:
        db.add(RoleGrant(login=email, role=body.role, added_by=user.uid))
    db.commit()
    audit(db, user, "role_register", detail=f"{email} -> {body.role}")
    return {"registered": True, "updated": False, "login": email, "role": body.role}


@router.put("/users/{uid}/role")
def set_role(uid: int, body: RoleIn, user: CurrentUser = Depends(require_role("template_admin")),
             db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if body.role not in ROLE_RANK:
        raise HTTPException(422, "role must be viewer, printer or template_admin")
    target = db.get(AppUser, uid)
    if not target:
        raise HTTPException(404, "Unknown user (they must sign in once first)")
    if is_main(target.odoo_login, target.email, settings) and body.role != "template_admin":
        raise HTTPException(403, "The main admin always stays an admin.")
    if target.odoo_uid == user.uid and body.role != target.app_role:
        raise HTTPException(403, "You cannot change your own role (ask another admin).")
    target.app_role = body.role
    db.commit()
    audit(db, user, "role_set", detail=f"{target.odoo_login} -> {body.role}")
    return {"uid": uid, "role": body.role}


@router.delete("/users/{uid}")
def remove_user(uid: int, user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db),
                settings: Settings = Depends(get_settings)):
    """Remove a person from the list. They can still sign in with Odoo, but start again with the default role."""
    target = db.get(AppUser, uid)
    if not target:
        raise HTTPException(404, "Unknown user")
    if is_main(target.odoo_login, target.email, settings):
        raise HTTPException(403, "The main admin cannot be deleted.")
    if target.odoo_uid == user.uid:
        raise HTTPException(403, "You cannot delete yourself.")
    login = target.odoo_login
    db.delete(target)
    db.commit()
    audit(db, user, "role_remove", detail=login)
    return {"ok": True}


@router.delete("/pending/{grant_id}")
def remove_pending(grant_id: int, user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db)):
    """Cancel the registration of a person who has not signed in yet."""
    g = db.get(RoleGrant, grant_id)
    if not g:
        raise HTTPException(404, "Unknown registration")
    login = g.login
    db.delete(g)
    db.commit()
    audit(db, user, "role_remove", detail=login)
    return {"ok": True}
