"""Share bridge: lets the Docker app read a Windows network share WITHOUT any password.

Run this on the Windows PC (it uses the PC's own, already signed-in access to the share, exactly like Explorer or the
browser does). It only listens on this PC (127.0.0.1), so nothing else on the network can use it, and it is read-only:
it can list folders and send files, nothing else. Nothing is copied anywhere.

    python backend\\scripts\\share_bridge.py                       (default share: \\\\172.16.0.4\\Marketing)
    python backend\\scripts\\share_bridge.py --root \\\\server\\share --port 8765

Or double-click start-share-bridge.bat in the project folder.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEFAULT_ROOT = r"\\172.16.0.4\Marketing"


class Bridge:
    def __init__(self, root: str):
        self.root = os.path.normpath(root)
        # Windows: the "\\?\" form lifts the 260 character path limit (some label folders are deeply nested)
        self.base = self.root
        if os.name == "nt":
            if self.root.startswith("\\\\"):
                self.base = "\\\\?\\UNC\\" + self.root[2:]
            elif len(self.root) > 1 and self.root[1] == ":":
                self.base = "\\\\?\\" + self.root

    def path(self, rel: str) -> str:
        """The real path of a share-relative path. Anything that could leave the share is refused."""
        parts = [p for p in (rel or "").replace("\\", "/").split("/") if p]
        if any(p in (".", "..") or ":" in p for p in parts):
            raise ValueError("bad path")
        return os.path.join(self.base, *parts)

    def is_dir(self, rel: str) -> bool:
        return os.path.isdir(self.path(rel))

    def stat(self, rel: str) -> dict:
        p = self.path(rel)
        try:
            st = os.stat(p)
        except OSError:
            return {"file": False, "dir": False}
        import stat as _s
        return {"file": _s.S_ISREG(st.st_mode), "dir": _s.S_ISDIR(st.st_mode), "size": st.st_size,
                "mtime": st.st_mtime_ns}

    def list(self, rel: str, exts: tuple[str, ...]) -> list[dict]:
        """Every file below `rel`, in all sub-folders however deep, whose name ends with one of `exts`."""
        top = self.path(rel)
        out: list[dict] = []
        stack = [(top, "")]
        while stack:
            folder, prefix = stack.pop()
            try:
                with os.scandir(folder) as it:
                    for e in it:
                        try:
                            if e.is_dir(follow_symlinks=False):
                                stack.append((e.path, f"{prefix}{e.name}/"))
                            elif e.is_file() and (not exts or e.name.lower().endswith(exts)):
                                out.append({"rel": f"{prefix}{e.name}", "size": e.stat().st_size})
                        except OSError:
                            continue
            except OSError:
                continue  # an unreadable folder must not stop the rest
        out.sort(key=lambda f: f["rel"].lower())
        return out


def make_handler(bridge: Bridge):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quiet
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, b: Bridge):
            app = os.environ.get("APP_URL", "http://localhost:8090")
            page = (
                "<!doctype html><meta charset=utf-8><title>Share bridge</title>"
                "<style>body{font:16px system-ui;max-width:640px;margin:60px auto;padding:0 16px;color:#1c2330}"
                "a.b{display:inline-block;background:#1f5fbf;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none}"
                ".ok{color:#1a7f4b;font-weight:600}code{background:#eef1f5;padding:2px 6px;border-radius:4px}</style>"
                "<h1>Share bridge</h1><p class=ok>&#9679; Running</p>"
                f"<p>Reading <code>{b.root}</code> with this PC's own access. Read-only; nothing is copied.</p>"
                "<p>Keep this window open while you use the label system.</p>"
                f'<p><a class=b href="{app}">Open the SO Sticker System</a></p>'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def do_GET(self):  # the only method there is
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path in ("/", "/index.html"):
                    return self._html(bridge)
                if u.path == "/health":
                    return self._json({"ok": True, "root": bridge.root})
                if u.path == "/isdir":
                    return self._json({"dir": bridge.is_dir(q.get("path", ""))})
                if u.path == "/stat":
                    return self._json(bridge.stat(q.get("path", "")))
                if u.path == "/list":
                    exts = tuple(x for x in q.get("exts", "").lower().split(",") if x)
                    return self._json({"files": bridge.list(q.get("path", ""), exts)})
                if u.path == "/file":
                    p = bridge.path(q.get("path", ""))
                    if not os.path.isfile(p):
                        return self._json({"error": "not found"}, 404)
                    size = os.path.getsize(p)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(size))
                    self.end_headers()
                    with open(p, "rb") as f:
                        while chunk := f.read(1024 * 1024):
                            self.wfile.write(chunk)
                    return None
                return self._json({"error": "unknown"}, 404)
            except ValueError:
                return self._json({"error": "bad path"}, 400)
            except (BrokenPipeError, ConnectionResetError):
                return None
            except OSError as e:
                return self._json({"error": str(e)}, 500)

    return Handler


def serve(root: str, port: int, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(Bridge(root)))
    httpd.daemon_threads = True
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("SHARE_BRIDGE_ROOT", DEFAULT_ROOT), help="the share to expose (read-only)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("SHARE_BRIDGE_PORT", "8765")))
    a = ap.parse_args()
    if not os.path.isdir(Bridge(a.root).base):
        print(f"Cannot open {a.root}. Open it once in Explorer (so Windows signs in), then start this again.")
        return 1
    httpd = serve(a.root, a.port)
    print(f"Share bridge running for {a.root} on http://127.0.0.1:{a.port}  (read-only, this PC only). Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
