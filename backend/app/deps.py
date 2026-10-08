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
    sid: str
    uid: int
    login: str
    name: str
    role: str
    transport: str
    _secret_token: str


def csrf_guard(request: Request) -> None:
    """State-changing requests must carry a custom header: it cannot be sent cross-site without CORS approval."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "sticker-app":
        raise HTTPException(403, "Missing X-Requested-With header")


def current_user(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> CurrentUser:
    sid = request.cookies.get(COOKIE)
    data = get_session_store().get(sid, settings.session_idle_seconds) if sid else None
    if not data:
        raise HTTPException(401, "Not signed in or session expired")
    user = db.get(AppUser, data["uid"])
    role = user.app_role if user else "viewer"  # read each request so role changes apply immediately
    return CurrentUser(sid=sid, uid=data["uid"], login=data["login"], name=data.get("name", ""), role=role,
                       transport=data["transport"], _secret_token=data["cred"])


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
    return connector.from_session(user.transport, user.login, secret, user.uid)


def audit(db: Session, user_uid: int | None, event: str, so_name: str = "", detail: str = "") -> None:
    db.add(AuditEvent(user_uid=user_uid, event=event, so_name=so_name[:64], detail=detail[:512]))
    db.commit()
