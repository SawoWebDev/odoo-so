from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .catalog.catalog import catalog_json
from .config import Settings, get_settings
from .db import get_db
from .deps import CurrentUser, audit, current_user, odoo_client
from .odoo.client import OdooReadClient
from .odoo.errors import OdooAuthError, OdooConnectionError, OdooError
from .resolver.resolver import SONotFound, to_public
from .resolver.service import get_resolved

router = APIRouter(prefix="/api", tags=["so"])


def resolve_or_http(client: OdooReadClient, settings: Settings, so: str, refresh: bool = False) -> dict:
    try:
        return get_resolved(client, settings, so, refresh=refresh)
    except SONotFound:
        raise HTTPException(404, f"Sales order {so!r} was not found (or you have no access to it in Odoo)")
    except OdooAuthError:
        raise HTTPException(401, "Odoo rejected your session; sign in again")
    except OdooConnectionError as e:
        raise HTTPException(502, f"Cannot reach Odoo: {e}")
    except OdooError as e:
        raise HTTPException(502, f"Odoo error: {e}")


@router.get("/so/{name}")
def get_so(name: str, refresh: bool = False, user: CurrentUser = Depends(current_user),
           client: OdooReadClient = Depends(odoo_client), settings: Settings = Depends(get_settings),
           db: Session = Depends(get_db)):
    data = resolve_or_http(client, settings, name, refresh)
    audit(db, user.uid, "search", data["so"])
    return to_public(data)


@router.get("/catalog")
def get_catalog(user: CurrentUser = Depends(current_user)):
    return catalog_json()
