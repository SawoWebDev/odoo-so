"""Item code -> label PDF, answered from the SAVED LIST (database), never from the disk.

The list is loaded into memory once and reloaded whenever the list changes. Matching is by file name:

    item code "560-BL"  ->  560-BL.pdf                               (exact, case-insensitive)
                            SET-TRAD-D -No BG.pdf  for "SET-TRAD-D"   (variant: the code, then a space, "(" or "_")

The same code often exists in several folders ("Individual", "Box Stickers", "No Logo"...); all are offered and
LABEL_FOLDER_PRIORITY decides the default. Files whose last check failed (status "missing") are not offered.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path

from ..db import SessionLocal
from ..models import LabelFile, LabelLocation
from .kinds import is_image, strip_ext

_VARIANT_SPLIT = re.compile(r"[\s(_]")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().upper()


def code_of(file_name: str) -> tuple[str, bool]:
    """('560-BL', True) for 560-BL.pdf ; ('SET-TRAD-D', False) for 'SET-TRAD-D -No BG.pdf'."""
    stem = strip_ext(file_name)
    base = norm(_VARIANT_SPLIT.split(stem.strip(), 1)[0])
    return base, norm(stem) == base


@dataclass(frozen=True)
class Entry:
    id: int
    location_id: int
    root: str  # the location's folder inside the container
    rel_path: str
    name: str
    folder: str
    exact: bool
    status: str
    size: int

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "folder": self.folder, "location_id": self.location_id,
                "status": self.status}

    @property
    def full_path(self) -> str:
        return f"{self.root}/{self.rel_path}"


class LabelIndex:
    def __init__(self, priority: list[str] | None = None):
        self.priority = priority or []
        self._lock = threading.Lock()
        self._loaded = False
        self._by_code: dict[str, list[Entry]] = {}
        self._by_id: dict[int, Entry] = {}

    def invalidate(self) -> None:
        self._loaded = False

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            db = SessionLocal()
            try:
                roots = {loc.id: loc.folder for loc in db.query(LabelLocation)}
                by_code: dict[str, list[Entry]] = {}
                by_id: dict[int, Entry] = {}
                for f in db.query(LabelFile):
                    if f.location_id not in roots:
                        continue
                    e = Entry(f.id, f.location_id, roots[f.location_id], f.rel_path, f.name, f.folder, f.exact, f.status, f.size)
                    by_id[e.id] = e
                    by_code.setdefault(f.code_key, []).append(e)
            finally:
                db.close()
            self._by_code, self._by_id, self._loaded = by_code, by_id, True

    def _rank(self, e: Entry) -> tuple:
        low = e.full_path.lower()
        pri = next((i for i, w in enumerate(self.priority) if w in low), len(self.priority))
        return (0 if e.exact else 1, pri, is_image(e.name), e.rel_path.count("/"), len(e.rel_path), e.rel_path.lower())

    def candidates(self, code: str) -> list[Entry]:
        """Usable PDFs for this item code (status ok), best default first."""
        self._load()
        return sorted((e for e in self._by_code.get(norm(code), []) if e.status == "ok"), key=self._rank)

    def missing(self, code: str) -> list[Entry]:
        """Files that were known for this code but were not found at the last check (renamed / deleted)."""
        self._load()
        return sorted((e for e in self._by_code.get(norm(code), []) if e.status == "missing"), key=self._rank)

    def get(self, file_id: int) -> Entry | None:
        self._load()
        return self._by_id.get(file_id)

    def absolute(self, file_id: int) -> Path | None:
        """The file on disk for a saved file, or None when it is not there right now (or escapes its folder)."""
        e = self.get(file_id)
        if e is None:
            return None
        from ..config import get_settings
        from . import share

        settings = get_settings()
        if share.enabled(settings):  # raises ShareDown when the helper is off: that is not "the file is gone"
            return share.local(settings, e.root, e.rel_path)
        root = Path(e.root).resolve()
        p = (root / e.rel_path).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            return None
        return p if p.is_file() else None


_index: LabelIndex | None = None
_key: tuple | None = None
_glock = threading.Lock()


def get_index(settings) -> LabelIndex:
    global _index, _key
    key = tuple(settings.folder_priority)
    with _glock:
        if _index is None or _key != key:
            _index, _key = LabelIndex(settings.folder_priority), key
        return _index


def reset_index() -> None:
    global _index, _key
    with _glock:
        _index, _key = None, None
