"""Preview, print and reprint of label PDFs, plus the print history.

A print is: the label PDF found for each ticked order line (by its saved name and location), repeated `copies` times, in
the order ticked. Nothing is drawn on the PDFs; they are the artwork. Every print is logged with the exact files (by
SHA-256) and a copy of each file is kept, so a reprint reproduces the original even if the file is edited, renamed or
deleted later.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .deps import CurrentUser, ROLE_RANK, audit, current_user, odoo_client, require_role
from .labels import store
from .labels.enrich import enrich
from .labels.index import LabelIndex, get_index
from .labels.kinds import is_image
from .labels.pdfs import TooLarge, assemble, snapshot_file, snapshot_path
from .models import LabelPrintJob
from .odoo.client import OdooReadClient
from .so_router import resolve_or_http

router = APIRouter(prefix="/api", tags=["print"])
MAX_COPIES = 500


class Item(BaseModel):
    line_id: int
    file_id: int | None = None  # a specific saved PDF when several exist for the item code; default = best match


class PrintIn(BaseModel):
    so: str
    items: list[Item] = Field(default_factory=list)
    copies: int = 1  # copies of each ticked label
    printer: str = ""  # free text, for the log


class ReprintIn(BaseModel):
    copies: int | None = None


@dataclass
class Chosen:
    line_id: int
    code: str
    name: str
    file_id: int
    location: str  # the folder the file is in (inside the container)
    rel_path: str
    absolute: Path


def choose(body: PrintIn, client: OdooReadClient, settings: Settings, index: LabelIndex, db: Session) -> tuple[str, list[Chosen]]:
    """Validate against fresh data: only lines that exist, are printable and use one of the saved PDFs for their code.
    The PDF is fetched from the saved location; if it is not there any more it is flagged missing and the print stops."""
    if not body.items:
        raise HTTPException(422, "Nothing is selected. Tick at least one order line.")
    resolved = enrich(resolve_or_http(client, settings, body.so), index)
    rows = {r["line_id"]: r for g in resolved["groups"] if g["id"] == "lines" for r in g["rows"]}
    out: list[Chosen] = []
    for it in body.items:
        row = rows.get(it.line_id)
        if row is None:
            raise HTTPException(422, f"Order line {it.line_id} is not part of {resolved['so']}")
        code = row["fields"]["line.product.code"]["display"]
        if row["disabled"]:
            raise HTTPException(422, f"{code}: {row['disabled_reason']}")
        allowed = {f["id"] for f in row["pdf"]["files"]}
        file_id = it.file_id if it.file_id is not None else row["pdf"]["selected"]
        if file_id not in allowed:
            raise HTTPException(422, f"{code}: that PDF is not a label for this item code")
        absolute = index.absolute(file_id)
        entry = index.get(file_id)
        if absolute is None or entry is None:
            store.mark_missing(db, file_id)  # it turns red on the Label files tab and the line warns from now on
            raise HTTPException(409, f"{code}: the label file was not found where it was saved "
                                     f"({entry.rel_path if entry else file_id}). It may have been renamed or deleted.")
        out.append(Chosen(it.line_id, code, row["fields"]["line.product.name"]["display"], file_id, entry.root,
                          entry.rel_path, absolute))
    return resolved["so"], out


def _copies(n: int, cap: int) -> int:
    return max(1, min(int(n or 1), cap))


def _respond(parts: list[tuple[Path, int]], headers: dict, settings: Settings) -> Response:
    """One file, one copy: stream it untouched (some are hundreds of MB). Otherwise combine."""
    if len(parts) == 1 and parts[0][1] == 1 and not is_image(parts[0][0]):
        p = parts[0][0]
        return FileResponse(p, media_type="application/pdf", headers=headers, content_disposition_type="inline",
                            filename=p.name)
    try:
        data = assemble(parts, settings.label_max_mb * 1024 * 1024)
    except TooLarge as e:
        raise HTTPException(413, str(e))
    except ValueError as e:  # a picture that cannot be read
        raise HTTPException(422, str(e))
    return Response(data, media_type="application/pdf", headers={**headers, "Content-Disposition": 'inline; filename="labels.pdf"'})


@router.post("/print/preview")
def preview(body: PrintIn, user: CurrentUser = Depends(current_user), client: OdooReadClient = Depends(odoo_client),
            settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    _so, chosen = choose(body, client, settings, get_index(settings), db)
    copies = _copies(body.copies, 20)  # previews are capped
    return _respond([(c.absolute, copies) for c in chosen], {"X-Label-Count": str(len(chosen) * copies)}, settings)


@router.post("/print/print")
def print_labels(body: PrintIn, user: CurrentUser = Depends(require_role("printer")),
                 client: OdooReadClient = Depends(odoo_client), settings: Settings = Depends(get_settings),
                 db: Session = Depends(get_db)):
    index = get_index(settings)
    so, chosen = choose(body, client, settings, index, db)
    copies = _copies(body.copies, MAX_COPIES)
    max_bytes = settings.label_max_mb * 1024 * 1024
    items = []
    for c in chosen:
        try:
            sha, size = snapshot_file(c.absolute, max_bytes)
        except ValueError as e:
            raise HTTPException(422, f"{c.code}: {e}")
        items.append({"line_id": c.line_id, "code": c.code, "name": c.name, "file_id": c.file_id,
                      "path": f"{c.location}/{c.rel_path}", "sha256": sha, "size": size})
    parts = [(c.absolute, copies) for c in chosen]
    job = LabelPrintJob(so_name=so, user_uid=user.uid, items_json=items, copies=copies, printer=body.printer[:128])
    db.add(job)
    db.commit()
    audit(db, user.uid, "print", so, f"job={job.id} labels={len(chosen) * copies}")
    return _respond(parts, {"X-Print-Job-Id": str(job.id), "X-Label-Count": str(len(chosen) * copies)}, settings)


# ---- history & reprint -----------------------------------------------------------------------------------------

def _job_json(j: LabelPrintJob) -> dict:
    return {"id": j.id, "so_name": j.so_name, "user_uid": j.user_uid, "copies": j.copies, "printer": j.printer,
            "reprint_of": j.reprint_of, "created_at": j.created_at.isoformat() if j.created_at else None,
            "items": j.items_json}


def _visible(db: Session, job_id: int, user: CurrentUser) -> LabelPrintJob:
    j = db.get(LabelPrintJob, job_id)
    if not j or (ROLE_RANK[user.role] < ROLE_RANK["template_admin"] and j.user_uid != user.uid):
        raise HTTPException(404, "Print job not found")
    return j


@router.get("/print-jobs")
def list_jobs(so: str | None = None, limit: int = 100, user: CurrentUser = Depends(current_user),
              db: Session = Depends(get_db)):
    q = db.query(LabelPrintJob).order_by(LabelPrintJob.id.desc())
    if ROLE_RANK[user.role] < ROLE_RANK["template_admin"]:
        q = q.filter(LabelPrintJob.user_uid == user.uid)
    if so:
        q = q.filter(LabelPrintJob.so_name == so)
    return [_job_json(j) for j in q.limit(min(limit, 500))]


@router.get("/print-jobs/{job_id}")
def get_job(job_id: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return _job_json(_visible(db, job_id, user))


@router.post("/print-jobs/{job_id}/reprint")
def reprint(job_id: int, body: ReprintIn, user: CurrentUser = Depends(require_role("printer")),
            db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Re-print exactly what was printed: from the kept copies, never from Odoo. A file too large to keep is read
    from its saved location again (the response says so)."""
    j = _visible(db, job_id, user)
    index = get_index(settings)
    copies = _copies(body.copies or j.copies, MAX_COPIES)
    parts, sources = [], set()
    for it in j.items_json:
        kept = snapshot_path(it.get("sha256") or "")
        if kept is not None:
            parts.append((kept, copies))
            sources.add("snapshot")
            continue
        live = index.absolute(it.get("file_id") or -1)
        if live is None:
            raise HTTPException(409, f"{it['code']}: the original file is no longer available")
        parts.append((live, copies))
        sources.add("share")
    new = LabelPrintJob(so_name=j.so_name, user_uid=user.uid, items_json=j.items_json, copies=copies, printer=j.printer,
                        reprint_of=j.id)
    db.add(new)
    db.commit()
    audit(db, user.uid, "reprint", j.so_name, f"job={new.id} reprint_of={j.id}")
    return _respond(parts, {"X-Print-Job-Id": str(new.id), "X-Reprint-Source": "+".join(sorted(sources))}, settings)
