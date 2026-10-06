"""The app reads the label folders through the share bridge (runs on the PC, no share password)."""
import threading

import pytest
from PIL import Image

from tests.conftest import login
from tests.test_print import req


@pytest.fixture
def bridged(env, labels, monkeypatch):
    """A real bridge serving the 'share'; the app's mount dir does NOT exist locally, so only the bridge can see files."""
    from app.config import get_settings
    from scripts.share_bridge import serve

    httpd = serve(str(env / "mnt"), 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("SHARE_BRIDGE_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    monkeypatch.setenv("LABEL_MOUNT_DIR", "/virtual-share")
    get_settings.cache_clear()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def test_read_folder_through_the_bridge_saves_every_file_in_every_sub_folder(bridged, api):
    login(api, "bob")
    st = api.get("/api/labels/status").json()
    assert st["files"] == 3 and st["locations"][0]["reachable"] is True  # saved at startup, through the bridge
    deep = api.labels / "01 SAWO/P9/a/b/c/d"
    deep.mkdir(parents=True)
    Image.new("RGB", (40, 20), "red").save(deep / "RS-1.png")
    (deep / "notes.txt").write_text("x")
    r = api.post("/api/labels/locations/1/fetch").json()["result"]
    assert r["added"] == 1 and r["files"] == 4
    item = next(i for i in api.get("/api/labels/search", params={"q": "RS-1"}).json()["items"])
    assert item["url"].endswith("/01%20SAWO/P9/a/b/c/d/RS-1.png") and item["url"].startswith("file://172.16.0.4/Marketing/")


def test_preview_and_print_download_from_the_bridge_and_reprint_is_identical(bridged, api):
    login(api, "bob")
    out = api.post("/api/print/print", json=req(copies=2))
    assert out.status_code == 200 and out.headers["content-type"] == "application/pdf"
    (api.labels / "01 SAWO/P1/01 Individual/220-TD.pdf").unlink()  # gone from the share
    assert api.post("/api/print-jobs/1/reprint", json={}).status_code == 200  # reprint uses the kept copy
    api.post("/api/labels/rescan")
    assert api.get("/api/labels/search", params={"state": "missing"}).json()["total"] == 1


def test_a_stopped_bridge_is_a_clear_message_and_never_turns_files_red(bridged, api):
    login(api, "bob")
    bridged.shutdown()
    bridged.server_close()
    r = api.post("/api/labels/locations/1/fetch")
    assert r.status_code == 409 and "share helper is not running" in r.text
    assert api.post("/api/print/preview", json=req()).status_code == 503
    assert api.get("/api/labels/status").json()["locations"][0]["reachable"] is False
    assert api.get("/api/labels/search", params={"state": "missing"}).json()["total"] == 0  # nothing was marked missing


def test_the_bridge_refuses_paths_outside_the_share(bridged):
    import httpx
    base = f"http://127.0.0.1:{bridged.server_address[1]}"
    assert httpx.get(base + "/file", params={"path": "../../etc/passwd"}).status_code == 400
    assert httpx.get(base + "/isdir", params={"path": "a/../.."}).status_code == 400
    assert httpx.post(base + "/file").status_code in (501, 405)  # read-only: no other method exists
