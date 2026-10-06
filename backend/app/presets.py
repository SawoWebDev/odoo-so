"""Selection presets (guideline section 6): save a basket, re-apply it to another SO. Per user, optionally shared."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .db import get_db
from .deps import CurrentUser, ROLE_RANK, current_user, require_role
from .models import Preset

router = APIRouter(prefix="/api/presets", tags=["presets"])


class PresetIn(BaseModel):
    name: str
    shared: bool = False
    selection: dict  # {"rules": [{"group": "lines", "keys": [...], "rows": "all"}]} - what to tick, not row ids


def _json(p: Preset) -> dict:
    return {"id": p.id, "name": p.name, "owner_uid": p.owner_uid, "shared": p.shared, "selection": p.selection_json}


@router.get("")
def list_presets(user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Preset).filter(or_(Preset.owner_uid == user.uid, Preset.shared.is_(True))).order_by(Preset.name)
    return [_json(p) for p in q]


@router.post("", status_code=201)
def create_preset(body: PresetIn, user: CurrentUser = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(422, "Name is required")
    p = Preset(name=body.name.strip(), owner_uid=user.uid, shared=body.shared, selection_json=body.selection)
    db.add(p)
    db.commit()
    return _json(p)


@router.put("/{pid}")
def update_preset(pid: int, body: PresetIn, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Preset, pid)
    if not p or (p.owner_uid != user.uid and ROLE_RANK[user.role] < ROLE_RANK["template_admin"]):
        raise HTTPException(404, "Preset not found")
    p.name, p.shared, p.selection_json = body.name.strip(), body.shared, body.selection
    db.commit()
    return _json(p)


@router.delete("/{pid}")
def delete_preset(pid: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Preset, pid)
    if not p or (p.owner_uid != user.uid and ROLE_RANK[user.role] < ROLE_RANK["template_admin"]):
        raise HTTPException(404, "Preset not found")
    db.delete(p)
    db.commit()
    return {"ok": True}
