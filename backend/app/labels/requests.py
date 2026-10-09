"""Label requests, three kinds:

  missing     the order line has no label file, so someone asks for it to be made / uploaded. One open request per
              item code (everybody sees it as already requested).
  additional  the line HAS a label file but someone wants an additional image (another label file); the text says which.
  change      the line has a label file and someone wants it changed or modified; the text says what. It adds no file,
              so it is closed by hand ("Done") when the work is finished.

How a missing / additional request is finished: it counts the label files of its item code. A request asked when the
code has 3 files waits for a 4th; a second one waiting at the same time needs a 5th. As soon as the saved list (Label
files) holds that many files for the code, the request is solved and closed: it leaves the open list and keeps the link
of the newest file. Change requests do not take part in the count."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ROLE_RANK, CurrentUser, audit, current_user
from ..models import LabelFile, LabelRequest, utcnow
from .index import norm

router = APIRouter(prefix="/api/label-requests", tags=["label-requests"])


class RequestIn(BaseModel):
    code: str = Field(min_length=1, max_length=255)
    name: str = Field(default="", max_length=512)
    so: str = Field(default="", max_length=64)
    kind: Literal["missing", "additional", "change"] = "missing"
    note: str = Field(default="", max_length=1000)  # what is needed; required for a change, optional for an additional image


def file_counts(db: Session) -> dict[str, int]:
    """How many usable label files each item code has in the saved list."""
    return dict(db.query(LabelFile.code_key, func.count()).filter(LabelFile.status == "ok").group_by(LabelFile.code_key).all())


def request_json(r: LabelRequest, files_now: int | None = None) -> dict:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    out = {"id": r.id, "code": r.item_code, "name": r.product_name, "so": r.so_name, "status": r.status,
           "kind": r.kind, "note": r.note, "requested_by": r.requested_by, "requested_by_name": r.requested_by_name,
           "created_at": iso(r.created_at), "solved_at": iso(r.solved_at), "file_id": r.file_id, "file_name": r.file_name,
           "file_url": r.file_url, "expected": r.expected or (1 if r.kind == "missing" else 0), "baseline": r.baseline}
    if files_now is not None:
        out["files_now"] = files_now
    return out


def open_by_code(db: Session) -> dict[str, LabelRequest]:
    """Open 'missing label' requests by item code."""
    return {r.code_key: r for r in db.query(LabelRequest).filter(LabelRequest.status == "open", LabelRequest.kind == "missing")}


def open_all_by_code(db: Session) -> dict[str, list[dict]]:
    """Every open request (both kinds) by item code, oldest first: what the Requests column of an order line shows."""
    counts = file_counts(db)
    out: dict[str, list[dict]] = {}
    for r in db.query(LabelRequest).filter(LabelRequest.status == "open").order_by(LabelRequest.id):
        out.setdefault(r.code_key, []).append(request_json(r, counts.get(r.code_key, 0)))
    return out


def resolve_matching(db: Session) -> int:
    """Close every open request whose label count has been reached (see the module text). Returns how many."""
    counts = file_counts(db)
    solved = 0
    for r in db.query(LabelRequest).filter(LabelRequest.status == "open").order_by(LabelRequest.id).all():
        need = r.expected or (1 if r.kind == "missing" else 0)  # a change has no count: it is closed by hand
        if need <= 0 or counts.get(r.code_key, 0) < need:
            continue
        f = (db.query(LabelFile).filter(LabelFile.code_key == r.code_key, LabelFile.status == "ok")
             .order_by(LabelFile.first_seen.desc(), LabelFile.id.desc()).first())
        r.status, r.solved_at = "solved", utcnow()
        if f:
            r.file_id, r.file_name, r.file_url = f.id, f.name, f.url or f"{f.folder}/{f.name}"
        solved += 1
    if solved:
        db.commit()
    return solved


@router.post("")
def create(body: RequestIn, background: BackgroundTasks, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    """Ask for a label file (missing) or for another / changed one (change). Asking again for a code that is already
    requested as missing, or repeating the same change text, changes nothing."""
    code = body.code.strip()
    key = norm(code)
    if not key:
        raise HTTPException(422, "Enter the item code.")
    resolve_matching(db)
    have = file_counts(db).get(key, 0)
    note = " ".join(body.note.split())
    if body.kind in ("additional", "change"):
        if not have:
            raise HTTPException(409, f"There is no label file for {code} yet: request the missing label instead.")
        if body.kind == "change" and not note:
            raise HTTPException(422, "Write what has to be changed (for example: fix the barcode, new logo).")
        existing = (db.query(LabelRequest).filter(LabelRequest.code_key == key, LabelRequest.status == "open",
                                                  LabelRequest.kind == body.kind, LabelRequest.requested_by == user.uid,
                                                  LabelRequest.note == note).first())
    else:
        if have:
            raise HTTPException(409, f"A label file for {code} already exists.")
        existing = db.query(LabelRequest).filter(LabelRequest.code_key == key, LabelRequest.status == "open",
                                                 LabelRequest.kind == "missing").first()
    if existing:
        return {"request": request_json(existing, have), "existing": True}
    waiting = (db.query(LabelRequest).filter(LabelRequest.code_key == key, LabelRequest.status == "open",
                                             LabelRequest.kind.in_(("missing", "additional"))).count())
    adds_file = body.kind in ("missing", "additional")
    r = LabelRequest(code_key=key, item_code=code, product_name=body.name.strip(), so_name=body.so.strip(),
                     kind=body.kind, note=note if body.kind != "missing" else "", baseline=have,
                     # one more file than there is now, plus those already asked for; a change adds no file
                     expected=(have + waiting + 1) if adds_file else 0,
                     requested_by=user.uid, requested_by_name=user.name or user.login)
    db.add(r)
    db.commit()
    audit(db, user, {"missing": "label_request", "additional": "label_more", "change": "label_change"}[body.kind],
          body.so.strip(), code[:200])
    from .. import mailer

    background.add_task(mailer.notify_new_request, request_json(r, have))  # email the receivers (if set up on Settings)
    return {"request": request_json(r, have), "existing": False}


@router.get("")
def listing(status: str = "open", user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    """The requests (open, solved or all). Solves what can be solved first, so the list is never stale."""
    resolve_matching(db)
    counts = file_counts(db)
    q = db.query(LabelRequest)
    if status in ("open", "solved"):
        q = q.filter(LabelRequest.status == status)
    rows = q.order_by(LabelRequest.id.desc()).limit(1000).all()
    totals = {s: db.query(LabelRequest).filter(LabelRequest.status == s).count() for s in ("open", "solved")}
    return {"items": [request_json(r, counts.get(r.code_key, 0)) for r in rows], "counts": totals}


@router.post("/{request_id}/done")
def done(request_id: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    """Close an additional-image or change request by hand once the work is finished. The person who asked, or anyone who can print / admin."""
    r = db.get(LabelRequest, request_id)
    if r is None:
        raise HTTPException(404, "Unknown request")
    if r.kind == "missing":
        raise HTTPException(409, "A missing-label request closes by itself when the file is added to Label files.")
    if r.requested_by != user.uid and ROLE_RANK.get(user.role, 0) < ROLE_RANK["printer"]:
        raise HTTPException(403, "Only the person who asked, or someone who can print, can close this request.")
    if r.status != "open":
        return {"request": request_json(r)}
    r.status, r.solved_at = "solved", utcnow()
    db.commit()
    audit(db, user, "label_change_done", r.so_name, r.item_code[:200])
    return {"request": request_json(r)}


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
    audit(db, user, "label_request_del", "", code[:200])
    return {"ok": True}
