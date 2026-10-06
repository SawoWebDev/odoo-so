"""Pictures in the label folder are saved like PDFs and print as one-page PDFs."""
import io

from PIL import Image
from pypdf import PdfReader

from app.labels import store
from app.labels.index import code_of
from app.labels.kinds import is_label_file


def test_which_files_count_as_labels():
    for n in ("560-BL.pdf", "A.PNG", "a.jpg", "a.JPEG", "a.gif", "a.bmp", "a.tif", "a.tiff", "a.webp"):
        assert is_label_file(n), n
    for n in ("notes.txt", "a.docx", "thumbs.db", "pdf"):
        assert not is_label_file(n), n


def test_item_code_comes_from_the_name_without_any_label_extension():
    assert code_of("560-BL.png") == ("560-BL", True)
    assert code_of("SET-TRAD-D -No BG.JPG") == ("SET-TRAD-D", False)
    assert code_of("560-BL.pdf") == ("560-BL", True)


def test_picture_becomes_a_pdf_page_and_transparency_is_flattened(tmp_path):
    from app.labels.kinds import image_to_pdf
    p = tmp_path / "x.png"
    Image.new("RGBA", (300, 150), (255, 0, 0, 0)).save(p)
    pages = PdfReader(io.BytesIO(image_to_pdf(p))).pages
    assert len(pages) == 1
    assert round(float(pages[0].mediabox.width)) == 72 and round(float(pages[0].mediabox.height)) == 36  # 300 px at 300 dpi


def test_read_folder_saves_pictures_next_to_pdfs_and_prints_them(api):
    from tests.conftest import login
    from tests.test_print import req

    login(api, "bob")
    deep = api.labels / "01 SAWO/P9/deeper/still"
    deep.mkdir(parents=True)
    Image.new("RGB", (120, 60), "blue").save(deep / "RS-1.png")  # RS-1 had no PDF at all
    (api.labels / "01 SAWO/P9/notes.txt").write_text("not a label")
    r = api.post("/api/labels/locations/1/fetch").json()["result"]
    assert r["added"] == 1 and r["files"] == 4  # 3 PDFs + the picture; the .txt is ignored
    row = lambda: next(x for g in api.get("/api/so/S00124?refresh=true").json()["groups"] if g["id"] == "lines" for x in g["rows"])  # noqa: E731
    assert [f["name"] for f in row()["pdf"]["files"]] == ["RS-1.png"] and row()["disabled"] is False
    fid = row()["pdf"]["selected"]
    img = api.get("/api/labels/file", params={"id": fid})
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    out = api.post("/api/print/print", json=req(so="S00124", items=[{"line_id": 12, "file_id": fid}], copies=2))
    assert out.status_code == 200 and out.headers["content-type"] == "application/pdf"
    assert len(PdfReader(io.BytesIO(out.content)).pages) == 2
    # the reprint is the kept copy, even after the picture is changed or removed
    (deep / "RS-1.png").unlink()
    again = api.post("/api/print-jobs/1/reprint", json={})
    assert again.status_code == 200 and again.headers["x-reprint-source"] == "snapshot"
    assert len(PdfReader(io.BytesIO(again.content)).pages) == 2


def test_a_corrupt_picture_is_refused_cleanly(api):
    from tests.conftest import login
    from tests.test_print import req

    login(api, "bob")
    (api.labels / "01 SAWO/RS-1.jpg").write_bytes(b"not really a jpeg")
    api.post("/api/labels/locations/1/fetch")
    fid = next(f["id"] for f in api.get("/api/labels/search", params={"q": "RS-1"}).json()["items"])
    r = api.post("/api/print/print", json=req(so="S00124", items=[{"line_id": 12, "file_id": fid}]))
    assert r.status_code == 422 and "not a readable picture" in r.text
    assert api.get("/api/print-jobs").json() == []
