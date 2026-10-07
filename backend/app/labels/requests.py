"""Label requests: an order line has no label file, so someone asks for it to be made / uploaded.

One open request per item code (everybody sees it as already requested). As soon as a label file for that code is
saved in the Label files list (a folder was read, or a file came back), the request is solved and closed: it leaves
the open list and keeps the link of the file that solved it."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, audit, current_user
from ..models import LabelFile, LabelRequest, utcnow
from .index import norm

router = APIRouter(prefix="/api/label-requests", tags=["label-requests"])


class RequestIn(BaseModel):
    code: str = Field(min_length=1, max_length=255)
    name: str = Field(default="", max_length=512)
    so: str = Field(default="", max_length=64)


def request_json(r: LabelRequest) -> dict:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"id": r.id, "code": r.item_code, "name": r.product_name, "so": r.so_name, "status": r.status,
            "requested_by": r.requested_by, "requested_by_name": r.requested_by_name, "created_at": iso(r.created_at),
            "solved_at": iso(r.solved_at), "file_id": r.file_id, "file_name": r.file_name, "file_url": r.file_url}


def open_by_code(db: Session) -> dict[str, LabelRequest]:
    return {r.code_key: r for r in db.query(LabelRequest).filter(LabelRequest.status == "open")}


def resolve_matching(db: Session) -> int:
    """Close every open request for which a usable label file now exists (exact name first, then variants)."""
    solved = 0
    for r in db.query(LabelRequest).filter(LabelRequest.status == "open").all():
        f = (db.query(LabelFile).filter(LabelFile.code_key == r.code_key, LabelFile.status == "ok")
             .order_by(LabelFile.exact.desc(), LabelFile.id).first())
        if f:
            r.status, r.solved_at = "solved", utcnow()
            r.file_id, r.file_name, r.file_url = f.id, f.name, f.url or f"{f.folder}/{f.name}"
            solved += 1
    if solved:
        db.commit()
    return solved


@router.post("")
def create(body: RequestIn, background: BackgroundTasks, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    """Ask for the label file of an item code. Asking again for a code that is already requested changes nothing."""
    code = body.code.strip()
    key = norm(code)
    if not key:
        raise HTTPException(422, "Enter the item code.")
    if db.query(LabelFile).filter(LabelFile.code_key == key, LabelFile.status == "ok").first():
        resolve_matching(db)
        raise HTTPException(409, f"A label file for {code} already exists.")
    existing = db.query(LabelRequest).filter(LabelRequest.code_key == key, LabelRequest.status == "open").first()
    if existing:
        return {"request": request_json(existing), "existing": True}
    r = LabelRequest(code_key=key, item_code=code, product_name=body.name.strip(), so_name=body.so.strip(),
                     requested_by=user.uid, requested_by_name=user.name or user.login)
    db.add(r)
    db.commit()
    audit(db, user.uid, "label_request", body.so.strip(), code[:200])
    from .. import mailer

    background.add_task(mailer.notify_new_request, request_json(r))  # email the receivers (if set up on the Settings tab)
    return {"request": request_json(r), "existing": False}


@router.get("")
def listing(status: str = "open", user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    """The requests (open, solved or all). Solves what can be solved first, so the list is never stale."""
    resolve_matching(db)
    q = db.query(LabelRequest)
    if status in ("open", "solved"):
        q = q.filter(LabelRequest.status == status)
    rows = q.order_by(LabelRequest.id.desc()).limit(1000).all()
    counts = {s: db.query(LabelRequest).filter(LabelRequest.status == s).count() for s in ("open", "solved")}
    return {"items": [request_json(r) for r in rows], "counts": counts}


@router.delete("/{request_id}")
def cancel(request_id: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    """Withdraw (delete) a request. The person who asked, or an admin."""
    r = db.get(LabelRequest, request_id)
    if r is None:
        raise HTTPException(404, "Unknown request")
    if r.requested_by != user.uid and user.role != "template_admin":
        raise HTTPException(403, "Only the person who asked, or an admin, can delete this request.")
    code = r.item_code
    db.delete(r)
    db.commit()
    audit(db, user.uid, "label_request_del", "", code[:200])
    return {"ok": True}
