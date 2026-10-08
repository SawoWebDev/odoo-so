"""Reading the label folders through the share bridge (backend/scripts/share_bridge.py) instead of a mounted folder.

The bridge runs on the Windows PC as the signed-in user, so the app needs no share password. Files are listed by
the bridge; a file is only downloaded (into a small cache) when it is previewed or printed."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

import httpx

from ..config import Settings
from ..storage import _root
from .kinds import LABEL_EXTS


class ShareDown(Exception):
    """The bridge cannot be reached (not started, or the PC is off). Never means the file is gone."""

    def __init__(self, msg: str = ""):
        super().__init__(msg or "The share helper is not running on your PC. Start it (double-click "
                                "start-share-bridge.bat), then try again.")


def enabled(settings: Settings) -> bool:
    return bool(settings.share_bridge_url.strip())


def rel_of(settings: Settings, path: str | Path) -> str:
    """Share-relative path of a folder or file path below LABEL_MOUNT_DIR."""
    rel = PurePosixPath(str(path).replace("\\", "/")).relative_to(PurePosixPath(settings.label_mount_dir)).as_posix()
    return "" if rel == "." else rel


def _get(settings: Settings, endpoint: str, timeout: float = 60, **params) -> httpx.Response:
    try:
        r = httpx.get(settings.share_bridge_url.rstrip("/") + endpoint, params=params, timeout=timeout)
    except httpx.HTTPError as e:
        raise ShareDown() from e
    if r.status_code >= 500:
        raise ShareDown(f"The share helper could not read the share ({r.json().get('error', r.status_code)}).")
    return r


def is_dir(settings: Settings, folder: str | Path) -> bool:
    return bool(_get(settings, "/isdir", 15, path=rel_of(settings, folder)).json().get("dir"))


def tree(settings: Settings, folder: str | Path) -> dict:
    """{'files': [(rel, size)], 'dirs': [rel], 'unreadable': [rel]}: all depths."""
    r = _get(settings, "/list", 600, path=rel_of(settings, folder), exts=",".join(LABEL_EXTS)).json()
    return {"files": [(f["rel"], int(f["size"])) for f in r["files"]], "dirs": r.get("dirs", []),
            "unreadable": r.get("unreadable", [])}


def listing(settings: Settings, folder: str | Path) -> list[tuple[str, int]]:
    """(relative path, size) of every label file below the folder, all depths."""
    return tree(settings, folder)["files"]


def local(settings: Settings, root: str | Path, rel: str) -> Path | None:
    """The file as a local path (downloaded to the cache if it is new or changed), or None if it is not on the share."""
    full = f"{rel_of(settings, root)}/{rel}".lstrip("/")
    st = _get(settings, "/stat", 15, path=full).json()
    if not st.get("file"):
        return None
    key = hashlib.sha1(full.lower().encode()).hexdigest()[:20]
    d = _root() / "label_cache" / key
    dest = d / Path(rel).name
    stamp = d / "stamp"
    want = f"{st['size']}:{st['mtime']}"
    if dest.is_file() and stamp.is_file() and stamp.read_text() == want:
        return dest
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "download.part"
    try:
        with httpx.stream("GET", settings.share_bridge_url.rstrip("/") + "/file", params={"path": full}, timeout=600) as r:
            if r.status_code == 404:
                return None
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1024 * 1024):
                    f.write(chunk)
    except httpx.HTTPError as e:
        tmp.unlink(missing_ok=True)
        raise ShareDown() from e
    os.replace(tmp, dest)
    stamp.write_text(want)
    return dest
