"""Admin only: read the audit log (who did what, when). Nothing here writes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .db import get_db
from .deps import CurrentUser, require_role
from .models import AppUser, AuditEvent

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
def list_activity(user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db),
                  who: int | None = None, event: str = "", so: str = "",
                  page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)):
    q = db.query(AuditEvent)
    if who is not None:
        q = q.filter(AuditEvent.user_uid == who)
    if event:
        q = q.filter(AuditEvent.event == event)
    if so.strip():
        q = q.filter(AuditEvent.so_name.ilike(f"%{so.strip()}%"))
    total = q.count()
    rows = q.order_by(AuditEvent.id.desc()).offset((page - 1) * size).limit(size).all()

    names = {u.odoo_uid: u.shown_name for u in db.query(AppUser)}
    items = [{
        "id": r.id, "at": r.created_at.isoformat() if r.created_at else None, "event": r.event, "so": r.so_name,
        "detail": r.detail, "uid": r.user_uid,
        "who": names.get(r.user_uid, f"#{r.user_uid}") if r.user_uid is not None else "",
        "as": names.get(r.as_uid, f"#{r.as_uid}") if r.as_uid is not None else None,
    } for r in rows]
    events = [e for (e,) in db.query(AuditEvent.event).distinct()]
    people = [{"uid": uid, "name": n} for uid, n in sorted(names.items(), key=lambda x: x[1].lower())]
    return {"items": items, "total": total, "page": page, "size": size, "events": sorted(events), "people": people}
