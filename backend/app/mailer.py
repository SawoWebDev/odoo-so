"""Email for label requests: who sends (SMTP account / From) and who receives, edited on the Settings tab.

The configuration lives in the database (table app_setting, key "email"). The SMTP password is encrypted with the
app secret and is never sent back to the browser."""
from __future__ import annotations

import json
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import SessionLocal
from .models import AppSetting, utcnow
from .security import decrypt_secret, encrypt_secret

KEY = "email"
SECURITY = ("starttls", "ssl", "none")
EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")

DEFAULTS: dict = {
    "enabled": False, "host": "", "port": 587, "security": "starttls", "username": "", "password_enc": "",
    "sender_name": "SO Sticker System", "sender_email": "", "receivers": [], "app_url": "",
    "last_status": "", "last_at": None,
}


class MailError(Exception):
    """A sending problem, worded so it can be shown to the admin."""


def load(db: Session) -> dict:
    row = db.get(AppSetting, KEY)
    cfg = dict(DEFAULTS)
    if row and row.value:
        try:
            cfg.update(json.loads(row.value))
        except ValueError:
            pass
    return cfg


def save(db: Session, cfg: dict) -> None:
    row = db.get(AppSetting, KEY)
    if row is None:
        row = AppSetting(key=KEY, value="")
        db.add(row)
    row.value = json.dumps(cfg)
    db.commit()


def public(cfg: dict) -> dict:
    """What the browser may see: everything except the password."""
    out = {k: v for k, v in cfg.items() if k != "password_enc"}
    out["password_set"] = bool(cfg.get("password_enc"))
    return out


def parse_receivers(text: str | list[str]) -> list[str]:
    parts = re.split(r"[,;\s]+", text) if isinstance(text, str) else [p for t in text for p in re.split(r"[,;\s]+", t)]
    seen: list[str] = []
    for p in (x.strip() for x in parts):
        if p and p.lower() not in [s.lower() for s in seen]:
            seen.append(p)
    return seen


def validate(cfg: dict) -> str | None:
    """A message for the first thing that is wrong, or None."""
    if cfg["security"] not in SECURITY:
        return "Choose how the connection is secured (STARTTLS, SSL or none)."
    if not (isinstance(cfg["port"], int) and 1 <= cfg["port"] <= 65535):
        return "The port must be a number between 1 and 65535."
    incoming = {993: "IMAP over SSL", 143: "IMAP", 995: "POP3 over SSL", 110: "POP3"}
    if cfg["port"] in incoming:
        return (f"Port {cfg['port']} is for receiving mail ({incoming[cfg['port']]}), not for sending. "
                "Use 465 (SSL / TLS) or 587 (STARTTLS).")
    for r in cfg["receivers"]:
        if not EMAIL_RE.match(r):
            return f"'{r}' is not a valid email address."
    if len(cfg["receivers"]) > 20:
        return "Use at most 20 receivers."
    if cfg["sender_email"] and not EMAIL_RE.match(cfg["sender_email"]):
        return f"'{cfg['sender_email']}' is not a valid sender address."
    if cfg["enabled"]:
        if not cfg["host"].strip():
            return "Enter the SMTP server."
        if not cfg["sender_email"]:
            return "Enter the sender email address."
        if not cfg["receivers"]:
            return "Enter at least one receiver."
    return None


def _smtp_password(cfg: dict, settings: Settings) -> str:
    return (decrypt_secret(cfg["password_enc"], settings) or "") if cfg.get("password_enc") else ""


def encrypt_password(plain: str, settings: Settings | None = None) -> str:
    return encrypt_secret(plain, settings or get_settings())


def send(cfg: dict, subject: str, body: str, to: list[str], settings: Settings | None = None) -> None:
    """Send one email with the saved sender account. Raises MailError with a readable reason."""
    settings = settings or get_settings()
    if not cfg["host"].strip():
        raise MailError("Enter the SMTP server (for example mail.sawo.com).")
    if not cfg["sender_email"]:
        raise MailError("Enter the sender email address (From).")
    if not to:
        raise MailError("Enter at least one receiver, or an address in the test box.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["sender_name"] or "", cfg["sender_email"]))
    msg["To"] = ", ".join(to)
    msg.set_content(body)
    host, port = cfg["host"].strip(), int(cfg["port"])
    try:
        if cfg["security"] == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        with server:
            server.ehlo()
            if cfg["security"] == "starttls":
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if cfg["username"]:
                server.login(cfg["username"], _smtp_password(cfg, settings))
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise MailError("The mail server refused the username or password.")
    except smtplib.SMTPRecipientsRefused:
        raise MailError("The mail server refused the receiver address(es).")
    except smtplib.SMTPSenderRefused:
        raise MailError("The mail server refused the sender address.")
    except (smtplib.SMTPException, ssl.SSLError) as e:
        raise MailError(f"The mail server reported: {e}")
    except OSError as e:
        raise MailError(f"Cannot reach the mail server {host}:{port} ({e.__class__.__name__}: {e}).")


def _remember(db: Session, cfg: dict, status: str) -> None:
    cfg["last_status"], cfg["last_at"] = status, utcnow().isoformat()
    save(db, cfg)


def request_text(req: dict, app_url: str) -> tuple[str, str]:
    change = req.get("kind") == "change"
    subject = f"Label {'change request' if change else 'request'}: {req['code']}" + (f" (SO {req['so']})" if req["so"] else "")
    lines = [
        "A change to an existing label file has been requested." if change else "A label file has been requested.", "",
        f"Item code:     {req['code']}",
        f"Product name:  {req['name'] or '-'}",
        f"Sales order:   {req['so'] or '-'}",
        f"Requested by:  {req['requested_by_name']}",
        f"Requested on:  {req['created_at']}", "",
    ]
    if change:
        lines += [f"What is needed: {req['note']}", "", "Close the request on the Requests tab once it is done."]
    else:
        lines += ["There is no label file for this item code. Please add it to the label folder; the request closes by "
                  "itself once the file shows up in Label files."]
    if app_url:
        lines += ["", f"Open requests: {app_url.rstrip('/')}"]
    return subject, "\n".join(lines)


def notify_new_request(req: dict) -> None:
    """Background task: email the receivers about a new label request. A failure is remembered, never raised."""
    db = SessionLocal()
    try:
        cfg = load(db)
        if not cfg["enabled"] or not cfg["receivers"]:
            return
        subject, body = request_text(req, cfg["app_url"])
        try:
            send(cfg, subject, body, cfg["receivers"])
            _remember(db, cfg, f"Sent to {len(cfg['receivers'])} receiver(s): request for {req['code']}")
        except MailError as e:
            _remember(db, cfg, f"FAILED: {e}")
    finally:
        db.close()
