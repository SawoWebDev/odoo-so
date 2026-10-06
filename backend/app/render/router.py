"""Preview, print, reprint and print history (guideline sections 11, 13)."""
from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import storage
from ..config import Settings, get_settings
from ..db import get_db
from ..deps import CurrentUser, ROLE_RANK, audit, current_user, odoo_client, require_role
from ..layout.sheet import LayoutOptions
from ..models import PrintJob, Template, TemplateVersion
from ..odoo.client import OdooReadClient
from ..so_router import resolve_or_http
from ..templates_lib import service
from .errors import TemplateRenderError
from .context import Label, SelectionError, build_labels, placeholder_values
from .pipeline import RenderOutput, render_labels, send_zpl

router = APIRouter(prefix="/api", tags=["render"])
_render_slots = threading.BoundedSemaphore(2)  # Chromium is heavy: at most two renders at a time


class RenderIn(BaseModel):
    so: str
    template_id: int
    version_id: int | None = None
    selection: dict
    options: dict = Field(default_factory=dict)  # calc_mode, override_base, logo, pefc, date
    overrides: dict = Field(default_factory=dict)  # {"*": {"kgs": 1}, "lines:11": {"pcs": 5}}
    copies: int = 1
    layout: dict = Field(default_factory=dict)
    printer: str = ""
    send_to_printer: bool = False
    acknowledge_warnings: bool = False


class ReprintIn(BaseModel):
    copies: int | None = None
    layout: dict | None = None
    printer: str | None = None
    send_to_printer: bool = False


@dataclass
class Prepared:
    template: Template
    version: TemplateVersion
    labels: list[Label]
    values: list[dict]
    warnings: list[dict]


def _pick_version(db: Session, t: Template, version_id: int | None, user: CurrentUser) -> TemplateVersion:
    admin = ROLE_RANK[user.role] >= ROLE_RANK["template_admin"]
    if version_id is not None:
        v = next((x for x in t.versions if x.id == version_id), None)
        if v is None:
            raise HTTPException(404, "Template version not found")
        if not admin and v.id != t.active_version_id:
            raise HTTPException(403, "Only the active template version can be used")
        return v
    av = service.active_version(t)
    if av is not None:
        return av
    if admin and t.versions:
        return t.versions[-1]  # admins may preview a draft
    raise HTTPException(409, "This template is not active")


def prepare(body: RenderIn, user: CurrentUser, db: Session, client: OdooReadClient, settings: Settings) -> Prepared:
    t = db.get(Template, body.template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    version = _pick_version(db, t, body.version_id, user)
    resolved = resolve_or_http(client, settings, body.so)
    o = body.options or {}
    try:
        labels = build_labels(resolved, body.selection, version.scope,
                              calc_mode=int(o.get("calc_mode") or version.default_calc_mode),
                              override_base=int(o.get("override_base") or 1), overrides=body.overrides,
                              toggles={"logo": bool(o.get("logo")), "pefc": bool(o.get("pefc")), "date": o.get("date")})
    except SelectionError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:  # bad override numbers etc.
        raise HTTPException(422, str(e))
    mappings = [{"placeholder": m.placeholder, "catalog_key": m.catalog_key, "overflow_rule": m.overflow_rule,
                 "optional": m.optional} for m in version.mappings]
    values, warnings = [], []
    for lab in labels:
        vals, w = placeholder_values(lab, mappings)
        values.append(vals)
        warnings += w
        warnings += [{**cw, "label": lab.key} for cw in lab.calc["warnings"]]
    return Prepared(t, version, labels, values, warnings)


def _render(p: Prepared, copies: int, layout: dict) -> RenderOutput:
    try:
        LayoutOptions.from_dict(layout)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))
    bundle = service.load_bundle(p.version.file_ref)
    try:
        with _render_slots:
            return render_labels(bundle, p.version.size, p.version.orientation, p.values, copies=copies, layout=layout)
    except TemplateRenderError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


def _label_summary(p: Prepared) -> list[dict]:
    return [{"key": lab.key, "title": lab.title, "calc": lab.calc} for lab in p.labels]


@router.post("/render/preview")
def preview(body: RenderIn, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
            client: OdooReadClient = Depends(odoo_client), settings: Settings = Depends(get_settings)):
    p = prepare(body, user, db, client, settings)
    out = _render(p, max(1, min(body.copies, 20)), body.layout)  # previews are capped
    resp = {"format": out.ext, "mimetype": out.mimetype, "warnings": p.warnings, "render_warnings": out.warnings,
            "labels": _label_summary(p), "info": out.info, "label_count": out.label_count,
            "template": {"id": p.template.id, "name": p.template.name, "version": p.version.version,
                         "version_id": p.version.id, "scope": p.version.scope}}
    if out.ext == "pdf":
        resp["pdf_base64"] = base64.b64encode(out.content).decode()
    else:
        resp["text"] = out.content.decode("utf-8", "replace")
    return resp


def _log_job(db: Session, *, so: str, version: TemplateVersion, selection: dict, overrides: dict, labels_summary: list,
             options: dict, copies: int, layout: dict, printer: str, values: list[dict], fmt: str, user_uid: int,
             snapshot_ref: str = "") -> PrintJob:
    job = PrintJob(so_name=so, template_version_id=version.id, selection_json=selection, overrides_json=overrides,
                   calculated_json={s["key"]: s["calc"] for s in labels_summary}, options_json=options, copies=copies,
                   layout=layout, printer=printer, output_format=fmt, user_uid=user_uid)
    db.add(job)
    db.flush()
    if not snapshot_ref:
        snapshot_ref = f"snapshots/{job.id}.json.gz"
        storage.save_json_gz(snapshot_ref, {"labels": [{"key": s["key"], "title": s["title"], "values": v}
                                                       for s, v in zip(labels_summary, values)]})
    job.snapshot_ref = snapshot_ref
    db.commit()
    return job


def _deliver(out: RenderOutput, job: PrintJob, so: str, send: bool, printer: str, settings: Settings) -> Response:
    headers = {"X-Print-Job-Id": str(job.id), "Content-Disposition": f'inline; filename="labels_{so}_{job.id}.{out.ext}"',
               "X-Render-Warnings": json.dumps(out.warnings)[:1500], "Access-Control-Expose-Headers": "*"}
    if send and out.ext == "zpl":
        target = settings.printers.get(printer)
        if not target:
            headers["X-Printer-Status"] = "unknown-printer"
        else:
            try:
                send_zpl(target, out.content)
                headers["X-Printer-Status"] = "sent"
            except OSError as e:
                headers["X-Printer-Status"] = f"failed: {type(e).__name__}"
    return Response(out.content, media_type=out.mimetype, headers=headers)


@router.post("/render/print")
def print_labels(body: RenderIn, user: CurrentUser = Depends(require_role("printer")), db: Session = Depends(get_db),
                 client: OdooReadClient = Depends(odoo_client), settings: Settings = Depends(get_settings)):
    p = prepare(body, user, db, client, settings)
    if p.warnings and not body.acknowledge_warnings:
        # Never print a silent zero / blank: the caller must see the warnings and confirm or override.
        raise HTTPException(422, detail={"message": "Resolve or acknowledge the warnings before printing",
                                         "warnings": p.warnings})
    copies = max(1, min(body.copies, 500))
    out = _render(p, copies, body.layout)
    job = _log_job(db, so=p.labels[0].values.get("header.name", {}).get("display") or body.so, version=p.version,
                   selection=body.selection, overrides=body.overrides, labels_summary=_label_summary(p),
                   options={**body.options, "acknowledged_warnings": [w["message"] for w in p.warnings]},
                   copies=copies, layout=LayoutOptions.from_dict(body.layout).to_dict(), printer=body.printer,
                   values=p.values, fmt=out.ext, user_uid=user.uid)
    audit(db, user.uid, "print", body.so, f"job={job.id} labels={out.label_count}")
    return _deliver(out, job, body.so, body.send_to_printer, body.printer, settings)


# ---- history & reprint --------------------------------------------------------------------------------

def _job_json(j: PrintJob) -> dict:
    return {"id": j.id, "so_name": j.so_name, "template": j.version.template.name, "template_id": j.version.template_id,
            "template_version": j.version.version, "template_version_id": j.template_version_id, "copies": j.copies,
            "layout": j.layout, "printer": j.printer, "user_uid": j.user_uid, "format": j.output_format,
            "created_at": j.created_at.isoformat() if j.created_at else None, "selection": j.selection_json,
            "overrides": j.overrides_json, "calculated": j.calculated_json, "options": j.options_json}


@router.get("/print-jobs")
def list_jobs(so: str | None = None, limit: int = 100, user: CurrentUser = Depends(current_user),
              db: Session = Depends(get_db)):
    q = db.query(PrintJob).order_by(PrintJob.id.desc())
    if ROLE_RANK[user.role] < ROLE_RANK["template_admin"]:
        q = q.filter(PrintJob.user_uid == user.uid)
    if so:
        q = q.filter(PrintJob.so_name == so)
    return [_job_json(j) for j in q.limit(min(limit, 500))]


@router.get("/print-jobs/{job_id}")
def get_job(job_id: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(PrintJob, job_id)
    if not j or (ROLE_RANK[user.role] < ROLE_RANK["template_admin"] and j.user_uid != user.uid):
        raise HTTPException(404, "Print job not found")
    return _job_json(j)


@router.post("/print-jobs/{job_id}/reprint")
def reprint(job_id: int, body: ReprintIn, user: CurrentUser = Depends(require_role("printer")),
            db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Re-render from the stored value snapshot and the ORIGINAL template version (no Odoo call, no drift)."""
    j = db.get(PrintJob, job_id)
    if not j or (ROLE_RANK[user.role] < ROLE_RANK["template_admin"] and j.user_uid != user.uid):
        raise HTTPException(404, "Print job not found")
    snap = storage.load_json_gz(j.snapshot_ref)
    values = [lab["values"] for lab in snap["labels"]]
    copies = max(1, min(body.copies or j.copies, 500))
    layout = body.layout if body.layout is not None else j.layout
    try:
        LayoutOptions.from_dict(layout)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))
    bundle = service.load_bundle(j.version.file_ref)
    try:
        with _render_slots:
            out = render_labels(bundle, j.version.size, j.version.orientation, values, copies=copies, layout=layout)
    except TemplateRenderError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    summary = [{"key": lab["key"], "title": lab["title"], "calc": j.calculated_json.get(lab["key"], {})}
               for lab in snap["labels"]]
    printer = body.printer if body.printer is not None else j.printer
    job = _log_job(db, so=j.so_name, version=j.version, selection=j.selection_json, overrides=j.overrides_json,
                   labels_summary=summary, options={**j.options_json, "reprint_of": j.id}, copies=copies, layout=layout,
                   printer=printer, values=values, fmt=out.ext, user_uid=user.uid, snapshot_ref=j.snapshot_ref)
    audit(db, user.uid, "print", j.so_name, f"job={job.id} reprint_of={j.id}")
    return _deliver(out, job, j.so_name, body.send_to_printer, printer, settings)
