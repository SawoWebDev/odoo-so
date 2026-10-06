"""File storage for uploaded templates and print snapshots (a local volume; swap for S3 behind the same API)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from .config import get_settings


def _root() -> Path:
    p = Path(get_settings().storage_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(rel: str) -> Path:
    root = _root()
    p = (root / rel).resolve()
    if root != p and root not in p.parents:  # path traversal guard
        raise ValueError("Path escapes storage root")
    return p


def save_bytes(rel: str, data: bytes) -> None:
    p = _safe(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def load_bytes(rel: str) -> bytes:
    return _safe(rel).read_bytes()


def exists(rel: str) -> bool:
    return _safe(rel).exists()


def list_files(rel_dir: str) -> dict[str, bytes]:
    base = _safe(rel_dir)
    out: dict[str, bytes] = {}
    if base.exists():
        for f in sorted(base.rglob("*")):
            if f.is_file():
                out[f.relative_to(base).as_posix()] = f.read_bytes()
    return out


def save_json_gz(rel: str, obj) -> None:
    save_bytes(rel, gzip.compress(json.dumps(obj, separators=(",", ":")).encode()))


def load_json_gz(rel: str):
    return json.loads(gzip.decompress(load_bytes(rel)))
