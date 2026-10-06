"""Which files count as labels: PDFs and pictures. Pictures are turned into a one-page PDF when previewed or printed."""
from __future__ import annotations

import io
from pathlib import Path

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")
LABEL_EXTS = (".pdf",) + IMAGE_EXTS


def is_label_file(name: str) -> bool:
    return name.lower().endswith(LABEL_EXTS)


def is_image(name: str | Path) -> bool:
    return str(name).lower().endswith(IMAGE_EXTS)


def strip_ext(name: str) -> str:
    low = name.lower()
    for ext in LABEL_EXTS:
        if low.endswith(ext):
            return name[: -len(ext)]
    return name


def image_to_pdf(path: Path) -> bytes:
    """The picture as a PDF whose page is the picture itself (300 dpi unless the file says otherwise). Every frame of
    a multi-page TIFF / animated image becomes a page; transparency is flattened onto white."""
    from PIL import Image, ImageSequence

    frames = []
    try:
        im_ctx = Image.open(path)
    except Exception as e:  # corrupt / unsupported picture
        raise ValueError(f"{path.name} is not a readable picture ({e.__class__.__name__})") from e
    with im_ctx as im:
        dpi = im.info.get("dpi")
        res = float(dpi[0]) if isinstance(dpi, tuple) and dpi and dpi[0] and dpi[0] >= 72 else 300.0
        for fr in ImageSequence.Iterator(im):
            fr = fr.copy()
            if fr.mode in ("RGBA", "LA", "P"):
                fr = fr.convert("RGBA")
                bg = Image.new("RGB", fr.size, "white")
                bg.paste(fr, mask=fr.getchannel("A"))
                fr = bg
            elif fr.mode != "RGB" and fr.mode != "L":
                fr = fr.convert("RGB")
            frames.append(fr)
    out = io.BytesIO()
    frames[0].save(out, "PDF", resolution=res, save_all=len(frames) > 1, append_images=frames[1:])
    return out.getvalue()
