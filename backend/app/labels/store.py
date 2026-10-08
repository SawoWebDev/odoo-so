"""The saved list of label files: add a folder from a URL, fetch its PDFs, check they still exist, delete stale records.

  fetch  = read the folder and SAVE every PDF's name and location (new files are added; files that are no longer there
           are marked missing);
  check  = for every saved file, is it still where it was? (marks it missing, or ok again). Does not read the folder.

If a folder cannot be reached at all (network down), nothing is changed: a network problem must not turn the whole list
red. All of this is read-only toward the share.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_engine
from ..models import LabelFile, LabelLocation, utcnow
from .index import code_of, get_index
from . import share
from .kinds import is_label_file


class LocationError(ValueError):
    """The folder cannot be used; the message is safe to show to the user."""


def resolve_url(url: str, settings: Settings) -> Path:
    """file://172.16.0.4/Marketing/00%20MASTERLIST/..., \\\\172.16.0.4\\Marketing\\..., //host/share/... or a path inside
    the container -> the folder inside the container. Only folders below LABEL_MOUNT_DIR are allowed."""
    raw = (url or "").strip().strip('"').strip()
    if not raw:
        raise LocationError("Enter the folder location.")
    mount = Path(settings.label_mount_dir)
    unc: str | None = None
    if raw.lower().startswith("file:"):
        p = urlparse(raw)
        if not p.netloc:
            raise LocationError("A file:/// address points at your own PC, which the app cannot see. "
                                "Use the network address: file://server/share/folder")
        unc = f"//{p.netloc}{unquote(p.path)}"
    elif raw.startswith("\\\\") or raw.startswith("//"):
        unc = unquote(raw).replace("\\", "/")
    if unc is not None:
        m = re.match(r"^//([^/]+)/([^/]+)(?:/(.*))?$", unc)
        if not m:
            raise LocationError("Expected an address like file://server/share/folder")
        host, share, rest = m.group(1), m.group(2), m.group(3) or ""
        mounted = settings.label_share.strip().replace("\\", "/").rstrip("/")
        if not mounted:
            raise LocationError("No network share is connected to the app. Set LABEL_SHARE and the share login in .env "
                                "(see the README), or add a folder by its path inside the container.")
        if f"//{host}/{share}".lower() != mounted.lower():
            raise LocationError(f"The share //{host}/{share} is not connected. The connected share is {mounted}.")
        target = mount / rest
    else:
        target = Path(unquote(raw))
    try:
        resolved = target.resolve()
        resolved.relative_to(mount.resolve())
    except (ValueError, OSError):
        raise LocationError(f"The folder must be inside the connected location ({mount}).")
    if not _is_dir(resolved, settings):
        raise LocationError(f"That folder cannot be found or read: {resolved}")
    return resolved


def _is_dir(path: Path, settings: Settings) -> bool:
    if share.enabled(settings):
        try:
            return share.is_dir(settings, path)
        except share.ShareDown as e:
            raise LocationError(str(e))
    return path.is_dir()


def to_url(folder: Path, settings: Settings) -> str:
    """A friendly address for a folder (used for the default location)."""
    share = settings.label_share.strip().replace("\\", "/").rstrip("/")
    try:
        rest = folder.resolve().relative_to(Path(settings.label_mount_dir).resolve()).as_posix()
    except ValueError:
        return str(folder)
    if share.startswith("//"):
        return "file:" + quote(f"{share}/{rest}".rstrip("/") + "/", safe="/")
    return str(folder)


def file_url(folder: str | Path, rel_path: str, settings: Settings) -> str:
    """The address of one PDF, e.g. file://172.16.0.4/Marketing/00%20MASTERLIST/.../560-BL.pdf (percent-encoded).
    Without a connected share it is the path inside the container."""
    full = f"{str(folder).rstrip('/')}/{rel_path}"
    share = settings.label_share.strip().replace("\\", "/").rstrip("/")
    try:
        rest = Path(full).relative_to(Path(settings.label_mount_dir)).as_posix()
    except ValueError:
        return full
    if share.startswith("//"):
        return "file:" + quote(f"{share}/{rest}", safe="/")
    return full


def ensure_schema(settings: Settings) -> None:
    """Small in-place upgrades for databases created by an earlier version (create_all does not add columns)."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    if "app_user" in insp.get_table_names() and "email" not in {c["name"] for c in insp.get_columns("app_user")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE app_user ADD COLUMN email VARCHAR(255) DEFAULT '' NOT NULL"))
    if "label_request" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("label_request")}
        with engine.begin() as conn:
            if "kind" not in have:
                conn.execute(text("ALTER TABLE label_request ADD COLUMN kind VARCHAR(16) DEFAULT 'missing' NOT NULL"))
            if "expected" not in have:
                conn.execute(text("ALTER TABLE label_request ADD COLUMN expected INTEGER DEFAULT 0 NOT NULL"))
            if "baseline" not in have:
                conn.execute(text("ALTER TABLE label_request ADD COLUMN baseline INTEGER DEFAULT 0 NOT NULL"))
            if "note" not in have:
                conn.execute(text("ALTER TABLE label_request ADD COLUMN note VARCHAR(1000) DEFAULT '' NOT NULL"))
    if "label_request" in insp.get_table_names():
        with engine.begin() as conn:  # idempotent: a new-style 'change' request has no count (expected = 0)
            conn.execute(text("UPDATE label_request SET kind = 'additional' WHERE kind = 'change' AND expected > 0"))
    if "label_file" in insp.get_table_names() and "url" not in {c["name"] for c in insp.get_columns("label_file")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE label_file ADD COLUMN url VARCHAR(2048)"))


def backfill_urls(db: Session, settings: Settings) -> int:
    """Give every saved file that has no URL yet its URL."""
    n = 0
    folders = {loc.id: loc.folder for loc in db.query(LabelLocation)}
    for f in db.query(LabelFile).filter(LabelFile.url.is_(None)):
        if f.location_id in folders:
            f.url = file_url(folders[f.location_id], f.rel_path, settings)
            n += 1
    if n:
        db.commit()
    return n


def _require_reachable(loc: LabelLocation) -> Path:
    root = Path(loc.folder)
    if not _is_dir(root, get_settings()):
        raise LocationError(f"The folder cannot be reached right now ({loc.folder}); nothing was changed.")
    return root


def _walk(root: Path, settings: Settings):
    """(sub-folder, file name, size) of every PDF / image below `root`, in all sub-folders however deep."""
    if share.enabled(settings):
        try:
            items = share.listing(settings, root)
        except share.ShareDown as e:
            raise LocationError(str(e))
        for rel, size in items:
            d, _, fn = rel.rpartition("/")
            if is_label_file(fn):
                yield d, fn, size
        return
    for dirpath, _dirs, files in os.walk(root, onerror=lambda e: None):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        for fn in files:
            if is_label_file(fn):
                try:
                    size = os.stat(os.path.join(dirpath, fn)).st_size
                except OSError:
                    size = 0
                yield rel_dir, fn, size


def fetch(db: Session, loc: LabelLocation, settings: Settings) -> dict:
    """Read the folder AND ALL ITS SUB-FOLDERS, however deep; save every PDF and image file's name, location and URL;
    mark vanished ones missing."""
    root = _require_reachable(loc)
    now = utcnow()
    existing = {f.rel_path: f for f in db.query(LabelFile).filter(LabelFile.location_id == loc.id)}
    seen: set[str] = set()
    added = restored = 0
    for rel_dir, fn, size in _walk(root, settings):
        rel = f"{rel_dir}/{fn}" if rel_dir else fn
        seen.add(rel)
        rec = existing.get(rel)
        if rec is None:
            code, exact = code_of(fn)
            db.add(LabelFile(location_id=loc.id, rel_path=rel, url=file_url(loc.folder, rel, settings), name=fn,
                             folder=rel_dir, code_key=code, exact=exact, size=size, status="ok", first_seen=now,
                             last_seen=now, last_checked=now))
            added += 1
        else:
            if rec.status != "ok":
                restored += 1
            rec.status, rec.size, rec.last_seen, rec.last_checked = "ok", size, now, now
            if not rec.url:
                rec.url = file_url(loc.folder, rel, settings)
    gone = 0
    for rel, rec in existing.items():
        if rel not in seen:
            if rec.status != "missing":
                gone += 1
            rec.status, rec.last_checked = "missing", now
    loc.last_fetched_at = loc.last_checked_at = now
    db.commit()
    get_index_invalidate()
    from .requests import resolve_matching

    solved = resolve_matching(db)  # label requests whose file is now in the list are closed
    return {"requests_solved": solved, "added": added, "restored": restored, "now_missing": gone, "files": len(seen)}


def report(db: Session, loc: LabelLocation, settings: Settings) -> dict:
    """What is on the share right now, folder by folder, against what is saved: proves every sub-folder was covered."""
    root = _require_reachable(loc)
    if share.enabled(settings):
        try:
            t = share.tree(settings, root)
        except share.ShareDown as e:
            raise LocationError(str(e))
        on_share, dirs, unreadable = {r: s for r, s in t["files"]}, t["dirs"], t["unreadable"]
    else:
        on_share, dirs, unreadable = {}, [], []
        for dirpath, dnames, fnames in os.walk(root, onerror=lambda e: unreadable.append(str(e.filename))):
            rel = Path(dirpath).relative_to(root).as_posix()
            if rel != ".":
                dirs.append(rel)
            for fn in fnames:
                if is_label_file(fn):
                    on_share[f"{rel}/{fn}" if rel != "." else fn] = 0
    saved = {f.rel_path: f.status for f in db.query(LabelFile).filter(LabelFile.location_id == loc.id)}
    per: dict[str, list[int]] = {"": [0, 0]}  # folder -> [on share, saved ok]
    for d in dirs:
        per.setdefault(d, [0, 0])
    for r in on_share:
        d = r.rpartition("/")[0]
        per.setdefault(d, [0, 0])[0] += 1
    for r, st in saved.items():
        if st == "ok":
            per.setdefault(r.rpartition("/")[0], [0, 0])[1] += 1
    rows = [{"folder": d or "(top folder)", "on_share": a, "saved": b} for d, (a, b) in sorted(per.items(), key=lambda kv: kv[0].lower())
            if d or a or b]
    return {"folders": len(dirs), "empty_folders": sum(1 for d in dirs if per[d] == [0, 0]
                                                          and not any(k.startswith(d + "/") and v != [0, 0] for k, v in per.items())),
            "on_share": len(on_share), "saved": sum(1 for v in saved.values() if v == "ok"),
            "not_saved": sorted(set(on_share) - set(saved))[:50], "unreadable": unreadable[:50], "rows": rows}


def check(db: Session, loc: LabelLocation) -> dict:
    """Is every saved file still where it was? Updates each file's status; does not look for new files."""
    root = _require_reachable(loc)
    now = utcnow()
    ok = missing = changed = 0
    settings = get_settings()
    on_share = {f"{d}/{n}" if d else n for d, n, _ in _walk(root, settings)} if share.enabled(settings) else None
    for rec in db.query(LabelFile).filter(LabelFile.location_id == loc.id):
        present = rec.rel_path in on_share if on_share is not None else (root / rec.rel_path).is_file()
        new = "ok" if present else "missing"
        if new != rec.status:
            changed += 1
        rec.status, rec.last_checked = new, now
        if present:
            rec.last_seen = now
            ok += 1
        else:
            missing += 1
    loc.last_checked_at = now
    db.commit()
    get_index_invalidate()
    return {"ok": ok, "missing": missing, "changed": changed}


def add_location(db: Session, url: str, user_uid: int | None, settings: Settings) -> tuple[LabelLocation, dict]:
    folder = resolve_url(url, settings)
    children = []
    for other in db.query(LabelLocation):
        o = Path(other.folder)
        if o == folder:
            raise LocationError("That folder has already been added.")
        if folder.is_relative_to(o):
            raise LocationError(f"That folder is already covered by the folder you added earlier ({other.url}): "
                                "its sub-folders are all included.")
        if o.is_relative_to(folder):
            children.append((other, o.relative_to(folder).as_posix()))
    loc = LabelLocation(url=url.strip(), folder=str(folder), added_by=user_uid)
    db.add(loc)
    db.commit()
    for child, prefix in children:  # folders added earlier below this one now belong to it: keep their saved files (ids)
        for f in db.query(LabelFile).filter(LabelFile.location_id == child.id):
            f.location_id = loc.id
            f.rel_path = f"{prefix}/{f.rel_path}"
            f.folder = f"{prefix}/{f.folder}" if f.folder else prefix
        db.flush()
        db.delete(child)
    db.commit()
    result = fetch(db, loc, settings)
    result["absorbed"] = len(children)
    return loc, result


def remove_location(db: Session, loc: LabelLocation) -> None:
    db.query(LabelFile).filter(LabelFile.location_id == loc.id).delete()
    db.delete(loc)
    db.commit()
    get_index_invalidate()


def delete_missing_file(db: Session, file_id: int) -> str:
    """Delete the RECORD of a file that is gone. Never touches the disk, and refuses files that are still there."""
    rec = db.get(LabelFile, file_id)
    if rec is None:
        raise LocationError("Unknown file.")
    if rec.status != "missing":
        raise LocationError("This file is still in the folder, so its record cannot be deleted.")
    name = rec.rel_path
    db.delete(rec)
    db.commit()
    get_index_invalidate()
    return name


def mark_missing(db: Session, file_id: int) -> None:
    """Called when a preview/print could not read a file: flag it so the list turns red and lines warn."""
    rec = db.get(LabelFile, file_id)
    if rec and rec.status != "missing":
        rec.status, rec.last_checked = "missing", utcnow()
        db.commit()
        get_index_invalidate()


def seed_default(db: Session, settings: Settings) -> None:
    """If no folder has been added yet, add LABEL_DEFAULT_LOCATION (if set and readable)."""
    if not settings.label_default_location.strip() or db.query(LabelLocation).count():
        return
    try:
        folder = resolve_url(settings.label_default_location, settings)
    except LocationError:
        return
    loc = LabelLocation(url=to_url(folder, settings), folder=str(folder))
    db.add(loc)
    db.commit()
    try:
        fetch(db, loc, settings)
    except LocationError:
        pass


def get_index_invalidate() -> None:
    from .index import _index

    if _index is not None:
        _index.invalidate()


def _reachable(loc: LabelLocation) -> bool:
    try:
        return _is_dir(Path(loc.folder), get_settings())
    except LocationError:
        return False


def location_json(db: Session, loc: LabelLocation) -> dict:
    counts = dict(db.query(LabelFile.status, func.count()).filter(LabelFile.location_id == loc.id)
                  .group_by(LabelFile.status).all())
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"id": loc.id, "url": loc.url, "folder": loc.folder, "reachable": _reachable(loc),
            "files": counts.get("ok", 0) + counts.get("missing", 0), "missing": counts.get("missing", 0),
            "last_fetched_at": iso(loc.last_fetched_at), "last_checked_at": iso(loc.last_checked_at)}
