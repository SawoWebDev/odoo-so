"""Template library: versioned storage, mapping and activation rules (guideline sections 7, 12)."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .. import storage
from ..catalog.catalog import BY_KEY, resolve_placeholder
from ..models import Template, TemplateMapping, TemplateVersion
from ..render.bundle import Bundle, UploadError, scan_bundle
from ..render.sizes import parse_size

SCOPES = ("so", "line", "lot", "package")
OVERFLOW = ("wrap", "shrink", "truncate")


class TemplateError(ValueError):
    pass


# ---- storage ------------------------------------------------------------------------------------

def store_bundle(ref: str, bundle: Bundle) -> None:
    for name, data in bundle.files.items():
        storage.save_bytes(f"{ref}/files/{name}", data)
    storage.save_bytes(f"{ref}/manifest.json", json.dumps(
        {"format": bundle.format, "main": bundle.main, "meta": bundle.meta}).encode())


def load_bundle(ref: str) -> Bundle:
    man = json.loads(storage.load_bytes(f"{ref}/manifest.json"))
    files = storage.list_files(f"{ref}/files")
    return Bundle(man["format"], man["main"], files, man.get("meta", {}))


# ---- mapping --------------------------------------------------------------------------------------

def auto_mappings(scan: dict, previous: dict[str, TemplateMapping] | None = None) -> list[dict]:
    """One mapping per placeholder: keep the user's earlier choice, else auto-map by key or alias."""
    out = []
    for name, info in scan["placeholders"].items():
        prev = (previous or {}).get(name)
        key = (prev.catalog_key if prev else None) or resolve_placeholder(name)
        rule = (prev.overflow_rule if prev else None) or info.get("overflow") or "wrap"
        out.append({"placeholder": name, "catalog_key": key, "overflow_rule": rule,
                    "optional": bool(prev.optional) if prev else bool(info.get("optional"))})
    return out


def validate_mappings(mappings: list[dict], placeholders: set[str]) -> list[dict]:
    seen: set[str] = set()
    clean = []
    for m in mappings:
        name = m.get("placeholder")
        if name not in placeholders or name in seen:
            continue  # ignore unknown / duplicate placeholders
        seen.add(name)
        key = m.get("catalog_key") or None
        if key and key not in BY_KEY:
            raise TemplateError(f"Unknown catalog key {key!r} for placeholder {name!r}")
        rule = m.get("overflow_rule") or "wrap"
        if rule not in OVERFLOW:
            raise TemplateError(f"overflow_rule must be one of {', '.join(OVERFLOW)}")
        clean.append({"placeholder": name, "catalog_key": key, "overflow_rule": rule, "optional": bool(m.get("optional"))})
    missing = placeholders - seen
    for name in missing:  # any placeholder the caller omitted keeps its auto mapping
        clean.append({"placeholder": name, "catalog_key": resolve_placeholder(name), "overflow_rule": "wrap", "optional": False})
    return clean


def unresolved(version: TemplateVersion) -> list[str]:
    return [m.placeholder for m in version.mappings
            if not m.optional and (not m.catalog_key or m.catalog_key not in BY_KEY)]


# ---- create / version -----------------------------------------------------------------------------

def _check_meta(size: str, orientation: str, scope: str, calc_mode: int) -> None:
    try:
        parse_size(size, orientation)
    except ValueError as e:
        raise TemplateError(str(e))
    if orientation not in ("portrait", "landscape"):
        raise TemplateError("orientation must be portrait or landscape")
    if scope not in SCOPES:
        raise TemplateError(f"scope must be one of {', '.join(SCOPES)}")
    if calc_mode not in (1, 2, 3, 4):
        raise TemplateError("default_calc_mode must be 1, 2, 3 or 4")


def _write_version(db: Session, t: Template, bundle: Bundle, ref: str, mappings: list[dict], user_uid: int | None,
                   original_filename: str) -> TemplateVersion:
    n = (max((v.version for v in t.versions), default=0)) + 1
    v = TemplateVersion(template_id=t.id, version=n, file_ref=ref, original_filename=original_filename, size=t.size,
                        orientation=t.orientation, scope=t.scope, default_calc_mode=t.default_calc_mode,
                        uploaded_by=user_uid)
    for m in mappings:
        v.mappings.append(TemplateMapping(**m))
    db.add(v)
    t.versions.append(v)
    db.flush()
    return v


def create_template(db: Session, *, name: str, description: str, category: str, size: str, orientation: str,
                    scope: str, default_calc_mode: int, bundle: Bundle, filename: str, user_uid: int | None,
                    activate_if_ready: bool = False) -> Template:
    if not name.strip():
        raise TemplateError("Name is required")
    if db.query(Template).filter(Template.name == name.strip()).first():
        raise TemplateError(f"A template named {name!r} already exists; upload a new version instead")
    size = size or bundle.meta.get("size") or "A6"
    _check_meta(size, orientation, scope, default_calc_mode)
    scan = scan_bundle(bundle)
    if scan["assets_missing"]:
        raise TemplateError("Template references files that are not in the archive: " + ", ".join(scan["assets_missing"]))
    t = Template(name=name.strip(), description=description, category=category or "general", format=bundle.format,
                 size=size, orientation=orientation, scope=scope, default_calc_mode=default_calc_mode, active=False)
    db.add(t)
    db.flush()
    ref = f"templates/{t.id}/v1"
    store_bundle(ref, bundle)
    v = _write_version(db, t, bundle, ref, auto_mappings(scan), user_uid, filename)
    if activate_if_ready and not unresolved(v):
        t.active, t.active_version_id = True, v.id
    db.commit()
    return t


def add_version(db: Session, t: Template, *, bundle: Bundle | None, filename: str, mappings: list[dict] | None,
                meta: dict, user_uid: int | None) -> TemplateVersion:
    """Every save is a NEW immutable version; earlier versions stay renderable for reprints."""
    latest = t.versions[-1]
    if bundle is not None and bundle.format != t.format:
        raise TemplateError(f"This template is {t.format}; a new version must also be {t.format}")
    for k in ("size", "orientation", "scope", "default_calc_mode"):
        if meta.get(k) not in (None, ""):
            setattr(t, k, meta[k])
    if meta.get("description") is not None:
        t.description = meta["description"]
    if meta.get("category"):
        t.category = meta["category"]
    _check_meta(t.size, t.orientation, t.scope, t.default_calc_mode)

    if bundle is not None:
        ref = f"templates/{t.id}/v{latest.version + 1}"
        store_bundle(ref, bundle)
        use_bundle, fname = bundle, filename
    else:
        ref, use_bundle, fname = latest.file_ref, load_bundle(latest.file_ref), latest.original_filename
    scan = scan_bundle(use_bundle)
    if scan["assets_missing"]:
        raise TemplateError("Template references files that are not in the archive: " + ", ".join(scan["assets_missing"]))
    previous = {m.placeholder: m for m in latest.mappings}
    base = auto_mappings(scan, previous)
    final = validate_mappings(mappings, set(scan["placeholders"])) if mappings is not None else base
    v = _write_version(db, t, use_bundle, ref, final, user_uid, fname)
    if t.active:  # an active template only switches to the new version when it is ready to print
        if unresolved(v):
            pass  # stays on the previous version until the admin fixes the mapping and activates
        else:
            t.active_version_id = v.id
    db.commit()
    return v


def activate(db: Session, t: Template, version_id: int | None = None) -> TemplateVersion:
    v = next((x for x in t.versions if x.id == version_id), None) if version_id else t.versions[-1]
    if v is None:
        raise TemplateError("Unknown version")
    bad = unresolved(v)
    if bad:
        raise TemplateError("Cannot activate: these placeholders are not mapped to a catalog field "
                            "(map them or mark them optional): " + ", ".join(bad))
    t.active, t.active_version_id = True, v.id
    db.commit()
    return v


def deactivate(db: Session, t: Template) -> None:
    t.active = False
    db.commit()


def active_version(t: Template) -> TemplateVersion | None:
    if not t.active:
        return None
    return next((v for v in t.versions if v.id == t.active_version_id), None)


# ---- serialisation --------------------------------------------------------------------------------

def version_json(v: TemplateVersion, detail: bool = False) -> dict:
    out = {"id": v.id, "version": v.version, "created_at": v.created_at.isoformat() if v.created_at else None,
           "uploaded_by": v.uploaded_by, "size": v.size, "orientation": v.orientation, "scope": v.scope,
           "default_calc_mode": v.default_calc_mode, "original_filename": v.original_filename,
           "unresolved": unresolved(v)}
    if detail:
        out["mappings"] = [{"placeholder": m.placeholder, "catalog_key": m.catalog_key,
                            "overflow_rule": m.overflow_rule, "optional": m.optional} for m in v.mappings]
        try:
            scan = scan_bundle(load_bundle(v.file_ref))
            out["placeholder_kinds"] = {k: e["kinds"] for k, e in scan["placeholders"].items()}
            out["findings"] = scan["findings"]
        except Exception:  # pragma: no cover - missing files must not break listing
            out["placeholder_kinds"], out["findings"] = {}, []
    return out


def template_json(t: Template, detail: bool = False) -> dict:
    av = active_version(t)
    latest = t.versions[-1] if t.versions else None
    out = {"id": t.id, "name": t.name, "description": t.description, "category": t.category, "format": t.format,
           "size": t.size, "orientation": t.orientation, "scope": t.scope, "default_calc_mode": t.default_calc_mode,
           "active": t.active, "active_version_id": t.active_version_id,
           "active_version": av.version if av else None, "latest_version": latest.version if latest else None,
           "unresolved": unresolved(latest) if latest else []}
    if detail:
        out["versions"] = [version_json(v, True) for v in t.versions]
    return out


__all__ = ["TemplateError", "UploadError"]
