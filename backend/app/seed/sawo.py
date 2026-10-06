"""Seed: the SAWO sample label (HTML hybrid, A6) from guideline section 8."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Template
from ..render.bundle import Bundle
from ..templates_lib import service

SEED_DIR = Path(__file__).parent / "sawo"
SAWO_NAME = "SAWO Product Label (A6)"


def sawo_bundle() -> Bundle:
    files = {"label.html": (SEED_DIR / "label.html").read_bytes()}
    for f in sorted((SEED_DIR / "assets").glob("*")):
        files[f"assets/{f.name}"] = f.read_bytes()
    return Bundle("html", "label.html", files)


def ensure_sawo_template(db: Session) -> Template:
    existing = db.query(Template).filter(Template.name == SAWO_NAME).first()
    if existing:
        return existing
    return service.create_template(
        db, name=SAWO_NAME,
        description="SAWO A6 product label: logo, photo, item code, description, EAN-13, SO number, PCS/KGS/CBM, "
                    "PEFC mark and LOGO YES/NO tick box. The meaning of LOGO and PEFC is an open business decision, "
                    "so both are plain print-time toggles.",
        category="product", size="A6", orientation="portrait", scope="line", default_calc_mode=1,
        bundle=sawo_bundle(), filename="sawo_label.zip", user_uid=None, activate_if_ready=True)
