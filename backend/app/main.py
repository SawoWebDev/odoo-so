from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .auth.router import router as auth_router
from .catalog.catalog import seed_catalog
from .config import get_settings
from .db import Base, SessionLocal, get_engine
from .deps import csrf_guard
from .presets import router as presets_router
from .render.router import router as render_router
from .seed.sawo import ensure_sawo_template
from .so_router import router as so_router
from .templates_lib.router import router as templates_router

log = logging.getLogger("sticker")


def init_app_data() -> None:
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(get_engine())
    db = SessionLocal()
    try:
        seed_catalog(db)
        ensure_sawo_template(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.app_secret_key.startswith(("dev-only", "change-me")):
        log.warning("APP_SECRET_KEY is a placeholder: set a long random value before real use")
    init_app_data()
    yield


app = FastAPI(title="SO Sticker System", version="1.0.0", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json", dependencies=[Depends(csrf_guard)])


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Default FastAPI echoes the submitted value in each error: strip it so a password can never leak.
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.get("/api/health")
def health():
    return {"ok": True}


app.include_router(auth_router)
app.include_router(so_router)
app.include_router(templates_router)
app.include_router(render_router)
app.include_router(presets_router)
