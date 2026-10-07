"""Settings tab (admin only): the email setup for label requests."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import mailer
from .config import Settings, get_settings
from .db import get_db
from .deps import CurrentUser, audit, require_role

router = APIRouter(prefix="/api/settings", tags=["settings"])


class EmailIn(BaseModel):
    enabled: bool = False
    host: str = Field(default="", max_length=255)
    port: int = 587
    security: str = "starttls"
    username: str = Field(default="", max_length=255)
    password: str | None = Field(default=None, max_length=512)  # None / "" = keep the saved password
    sender_name: str = Field(default="", max_length=120)
    sender_email: str = Field(default="", max_length=255)
    receivers: str = Field(default="", max_length=4000)  # comma / semicolon / space / new-line separated
    app_url: str = Field(default="", max_length=500)


class TestIn(BaseModel):
    to: str = Field(default="", max_length=4000)  # empty = the receivers
    config: EmailIn | None = None  # the form as it is on screen (even if not saved yet); empty = the saved setup


@router.get("/email")
def get_email(user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db)):
    return mailer.public(mailer.load(db))


@router.put("/email")
def put_email(body: EmailIn, user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db),
              settings: Settings = Depends(get_settings)):
    cfg = mailer.load(db)
    cfg.update(enabled=body.enabled, host=body.host.strip(), port=body.port, security=body.security,
               username=body.username.strip(), sender_name=body.sender_name.strip(), sender_email=body.sender_email.strip(),
               receivers=mailer.parse_receivers(body.receivers), app_url=body.app_url.strip())
    problem = mailer.validate(cfg)
    if problem:
        raise HTTPException(422, problem)
    if body.password:
        cfg["password_enc"] = mailer.encrypt_password(body.password, settings)
    if not cfg["username"]:
        cfg["password_enc"] = ""
    mailer.save(db, cfg)
    audit(db, user.uid, "settings_email", detail=f"enabled={cfg['enabled']} receivers={len(cfg['receivers'])}")
    return mailer.public(cfg)


@router.post("/email/test")
def test_email(body: TestIn, user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings)):
    """Send a test message with the setup on screen (or the saved one), so the admin knows it works before real requests arrive."""
    cfg = mailer.load(db)
    if body.config is not None:
        c = body.config
        cfg.update(host=c.host.strip(), port=c.port, security=c.security, username=c.username.strip(),
                   sender_name=c.sender_name.strip(), sender_email=c.sender_email.strip(),
                   receivers=mailer.parse_receivers(c.receivers))
        if c.password:
            cfg["password_enc"] = mailer.encrypt_password(c.password, settings)
        problem = mailer.validate({**cfg, "enabled": False})
        if problem:
            raise HTTPException(422, problem)
    to = mailer.parse_receivers(body.to) if body.to.strip() else cfg["receivers"]
    bad = [t for t in to if not mailer.EMAIL_RE.match(t)]
    if bad:
        raise HTTPException(422, f"'{bad[0]}' is not a valid email address.")
    try:
        mailer.send(cfg, "SO Sticker System: test email",
                    "This is a test email from the SO Sticker System.\n\nIf you can read this, label requests will reach "
                    "the receivers.", to, settings)
    except mailer.MailError as e:
        raise HTTPException(502, str(e))
    audit(db, user.uid, "settings_email_test", detail=f"to={len(to)}")
    return {"ok": True, "sent_to": to}
