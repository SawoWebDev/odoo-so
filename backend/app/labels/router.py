"""The saved list of label files: folders (added by URL), the files found in them, checks, and streaming a PDF."""
from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..deps import CurrentUser, audit, current_user, require_role
from ..models import LabelFile, LabelLocation
from . import store
from .index import get_index
from .store import LocationError

router = APIRouter(prefix="/api/labels", tags=["labels"])


class LocationIn(BaseModel):
    url: str


def _status(db: Session) -> dict:
    locs = [store.location_json(db, loc) for loc in db.query(LabelLocation).order_by(LabelLocation.id)]
    codes = db.query(func.count(func.distinct(LabelFile.code_key))).filter(LabelFile.status == "ok").scalar() or 0
    return {"locations": locs, "files": sum(x["files"] for x in locs), "missing": sum(x["missing"] for x in locs),
            "codes": codes}


def _loc(db: Session, loc_id: int) -> LabelLocation:
    loc = db.get(LabelLocation, loc_id)
    if not loc:
        raise HTTPException(404, "Unknown folder")
    return loc


@router.get("/status")
def status(user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return _status(db)


@router.post("/locations", status_code=201)
def add_location(body: LocationIn, user: CurrentUser = Depends(require_role("template_admin")),
                 settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    """Add a folder by URL and save the name and location of every PDF in it."""
    try:
        loc, result = store.add_location(db, body.url, user.uid, settings)
    except LocationError as e:
        raise HTTPException(422, str(e))
    audit(db, user.uid, "label_add", detail=f"{loc.folder} files={result['files']}")
    return {"location": store.location_json(db, loc), "result": result}


@router.delete("/locations/{loc_id}")
def remove_location(loc_id: int, user: CurrentUser = Depends(require_role("template_admin")),
                    db: Session = Depends(get_db)):
    """Forget a folder and its saved list. Nothing on the share is touched."""
    loc = _loc(db, loc_id)
    folder = loc.folder
    store.remove_location(db, loc)
    audit(db, user.uid, "label_remove", detail=folder)
    return {"ok": True}


@router.post("/locations/{loc_id}/fetch")
def fetch_location(loc_id: int, user: CurrentUser = Depends(require_role("printer")), db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)):
    """Read the folder again: save new PDFs, flag vanished ones."""
    loc = _loc(db, loc_id)
    try:
        result = store.fetch(db, loc, settings)
    except LocationError as e:
        raise HTTPException(409, str(e))
    audit(db, user.uid, "label_fetch", detail=f"{loc.folder} {result}")
    return {"location": store.location_json(db, loc), "result": result}


@router.post("/rescan")
def rescan(user: CurrentUser = Depends(require_role("printer")), db: Session = Depends(get_db)):
    """Check that every saved file is still where it was (red = renamed / deleted). Does not look for new files."""
    results = []
    for loc in db.query(LabelLocation).order_by(LabelLocation.id).all():
        try:
            results.append({"id": loc.id, **store.check(db, loc)})
        except LocationError as e:
            results.append({"id": loc.id, "error": str(e)})
    audit(db, user.uid, "label_check", detail=str(results)[:500])
    return {"results": results, **_status(db)}


@router.get("/search")
def search(q: str = "", state: str = "", location_id: int | None = None, page: int = 1, size: int = 25,
           user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    size = max(1, min(size, 100))
    page = max(1, page)
    query = db.query(LabelFile, LabelLocation.folder).join(LabelLocation, LabelFile.location_id == LabelLocation.id)
    for w in q.split():
        like = f"%{w}%"
        query = query.filter(or_(LabelFile.name.ilike(like), LabelFile.folder.ilike(like)))
    if state in ("ok", "missing"):
        query = query.filter(LabelFile.status == state)
    if location_id:
        query = query.filter(LabelFile.location_id == location_id)
    total = query.count()
    rows = (query.order_by(case((LabelFile.status == "missing", 0), else_=1), LabelFile.name, LabelFile.id)
            .offset((page - 1) * size).limit(size).all())
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"total": total, "page": page, "size": size, "items": [
        {"id": f.id, "name": f.name, "folder": f.folder, "url": f.url, "location_id": f.location_id, "location": loc_folder,
         "status": f.status, "size": f.size, "last_checked": iso(f.last_checked)} for f, loc_folder in rows]}


@router.delete("/files/{file_id}")
def delete_file(file_id: int, user: CurrentUser = Depends(require_role("printer")), db: Session = Depends(get_db)):
    """Delete the saved RECORD of a file that is gone (red). Files still in the folder cannot be deleted here."""
    try:
        name = store.delete_missing_file(db, file_id)
    except LocationError as e:
        raise HTTPException(409, str(e))
    audit(db, user.uid, "label_delete", detail=name)
    return {"ok": True}


@router.get("/file")
def file(id: int, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings),
         db: Session = Depends(get_db)):
    """Stream one saved label PDF, found by its saved location."""
    index = get_index(settings)
    p = index.absolute(id)
    if p is None:
        store.mark_missing(db, id)
        raise HTTPException(404, "This label file was not found where it was saved (deleted, renamed or unreachable)")
    return FileResponse(p, media_type=mimetypes.guess_type(p.name)[0] or "application/pdf", filename=p.name,
                        content_disposition_type="inline")
