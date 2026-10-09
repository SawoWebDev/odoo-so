"""FastAPI dependencies: current session, role checks, audit, CSRF guard."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import AppUser, AuditEvent
from .odoo.client import OdooReadClient
from .odoo.connect import Connector, get_connector
from .security import decrypt_secret, get_session_store

COOKIE = "sid"
ROLE_RANK = {"viewer": 1, "printer": 2, "template_admin": 3} 


@dataclass
class CurrentUser:
    """uid / login / name / role are who the app acts as. While an admin views the app as someone else they are that
    person; real_* is always the admin who signed in, whose Odoo login every Odoo call still uses."""
    sid: str
    uid: int
    login: str
    name: str
    role: str
    transport: str
    _secret_token: str
    real_uid: int = 0
    real_login: str = ""
    real_name: str = ""

    @property
    def viewing_as(self) -> bool:
        return self.real_uid != self.uid


# While viewing as someone, only these state-changing calls are let through: nothing may be printed, requested or
# changed in that person's name. Preview only renders the PDFs.
VIEW_AS_ALLOWED = {"/api/auth/view-as/stop", "/api/auth/logout", "/api/print/preview"}


def csrf_guard(request: Request) -> None:
    """State-changing requests must carry a custom header: it cannot be sent cross-site without CORS approval."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "sticker-app":
        raise HTTPException(403, "Missing X-Requested-With header")


def current_user(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> CurrentUser:
    sid = request.cookies.get(COOKIE)
    data = get_session_store().get(sid, settings.session_idle_seconds) if sid else None
    if not data:
        raise HTTPException(401, "Not signed in or session expired")
    me = CurrentUser(sid=sid, uid=data["uid"], login=data["login"], name=data.get("name", ""), role="viewer",
                     transport=data["transport"], _secret_token=data["cred"],
                     real_uid=data["uid"], real_login=data["login"], real_name=data.get("name", ""))
    real = db.get(AppUser, data["uid"])
    me.role = real.app_role if real else "viewer"  # read each request so role and name changes apply immediately
    if real:
        me.name = me.real_name = real.shown_name
    view_as = data.get("as")
    if view_as:
        target = db.get(AppUser, view_as["uid"])
        if me.role != "template_admin" or target is None:
            # Demoted while viewing as someone, or that person was removed: quietly fall back to their own account.
            data.pop("as", None)
            get_session_store().update(sid, data, settings.session_idle_seconds)
        else:
            me.uid, me.login, me.name, me.role = target.odoo_uid, target.odoo_login, target.shown_name, target.app_role
            if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path not in VIEW_AS_ALLOWED:
                raise HTTPException(403, f"You are viewing the app as {target.shown_name}: "
                                         "nothing can be printed, requested or changed in their name. Go back to your admin account first.")
    return me


def require_role(minimum: str):
    def dep(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK[minimum]:
            raise HTTPException(403, f"Requires app role '{minimum}'")
        return user
    return dep


def odoo_client(user: CurrentUser = Depends(current_user), connector: Connector = Depends(get_connector),
                settings: Settings = Depends(get_settings)) -> OdooReadClient:
    secret = decrypt_secret(user._secret_token, settings)
    if secret is None:
        raise HTTPException(401, "Session credentials are no longer valid; sign in again")
    return connector.from_session(user.transport, user.real_login, secret, user.real_uid)


def audit(db: Session, actor: CurrentUser | int | None, event: str, so_name: str = "", detail: str = "") -> None:
    """The person who really acted is always recorded; as_uid is who they were viewing the app as, if anyone."""
    if isinstance(actor, CurrentUser):
        uid, as_uid = actor.real_uid, (actor.uid if actor.viewing_as else None)
    else:
        uid, as_uid = actor, None
    db.add(AuditEvent(user_uid=uid, as_uid=as_uid, event=event, so_name=so_name[:64], detail=detail[:512]))
    db.commit()
