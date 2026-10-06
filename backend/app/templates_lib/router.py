from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..deps import CurrentUser, ROLE_RANK, audit, current_user, require_role
from ..models import Template
from ..render.bundle import UploadError, parse_upload
from . import service
from .service import TemplateError

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _read_upload(file: UploadFile, settings: Settings) -> tuple[bytes, str]:
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    return data, file.filename or "upload"


def _get(db: Session, tid: int) -> Template:
    t = db.get(Template, tid)
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@router.get("")
def list_templates(active_only: bool = False, scope: str | None = None, size: str | None = None,
                   user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Template).order_by(Template.name)
    admin = ROLE_RANK[user.role] >= ROLE_RANK["template_admin"]
    if active_only or not admin:  # printers only ever see templates that are ready to use
        q = q.filter(Template.active.is_(True))
    if scope:
        q = q.filter(Template.scope == scope)
    if size:
        q = q.filter(Template.size == size)
    return [service.template_json(t) for t in q]


@router.get("/{tid}")
def get_template(tid: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    t = _get(db, tid)
    admin = ROLE_RANK[user.role] >= ROLE_RANK["template_admin"]
    if not admin and not t.active:
        raise HTTPException(404, "Template not found")
    return service.template_json(t, detail=admin)


@router.post("", status_code=201)
def upload_template(file: UploadFile = File(...), name: str = Form(...), description: str = Form(""),
                    category: str = Form("general"), size: str = Form(""), orientation: str = Form("portrait"),
                    scope: str = Form("line"), default_calc_mode: int = Form(1),
                    user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)):
    data, fname = _read_upload(file, settings)
    try:
        bundle = parse_upload(fname, data, settings.max_upload_mb * 1024 * 1024)
        t = service.create_template(db, name=name, description=description, category=category, size=size,
                                    orientation=orientation, scope=scope, default_calc_mode=default_calc_mode,
                                    bundle=bundle, filename=fname, user_uid=user.uid)
    except (UploadError, TemplateError) as e:
        db.rollback()
        raise HTTPException(422, str(e))
    audit(db, user.uid, "upload", detail=f"template={t.name} v1")
    return service.template_json(t, detail=True)


@router.post("/{tid}/versions", status_code=201)
def new_version(tid: int, file: UploadFile | None = File(None), mappings: str | None = Form(None),
                size: str | None = Form(None), orientation: str | None = Form(None), scope: str | None = Form(None),
                default_calc_mode: int | None = Form(None), description: str | None = Form(None),
                category: str | None = Form(None),
                user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db),
                settings: Settings = Depends(get_settings)):
    t = _get(db, tid)
    try:
        bundle, fname = None, ""
        if file is not None and file.filename:
            data, fname = _read_upload(file, settings)
            bundle = parse_upload(fname, data, settings.max_upload_mb * 1024 * 1024)
        mp = json.loads(mappings) if mappings else None
        v = service.add_version(db, t, bundle=bundle, filename=fname, mappings=mp,
                                meta={"size": size, "orientation": orientation, "scope": scope,
                                      "default_calc_mode": default_calc_mode, "description": description,
                                      "category": category}, user_uid=user.uid)
    except (UploadError, TemplateError) as e:
        db.rollback()
        raise HTTPException(422, str(e))
    except json.JSONDecodeError:
        db.rollback()
        raise HTTPException(422, "mappings must be valid JSON")
    audit(db, user.uid, "upload", detail=f"template={t.name} v{v.version}")
    return service.template_json(t, detail=True)


@router.post("/{tid}/activate")
def activate(tid: int, version_id: int | None = Form(None),
             user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db)):
    t = _get(db, tid)
    try:
        service.activate(db, t, version_id)
    except TemplateError as e:
        raise HTTPException(422, str(e))
    return service.template_json(t, detail=True)


@router.post("/{tid}/deactivate")
def deactivate(tid: int, user: CurrentUser = Depends(require_role("template_admin")), db: Session = Depends(get_db)):
    t = _get(db, tid)
    service.deactivate(db, t)
    return service.template_json(t, detail=True)
