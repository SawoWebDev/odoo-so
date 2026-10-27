from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .deps import CurrentUser, audit, current_user, odoo_client
from .labels.enrich import enrich
from .labels.index import get_index
from .labels.requests import open_by_code, open_all_by_code, request_json, resolve_matching
from .odoo.client import OdooReadClient
from .odoo.errors import OdooAuthError, OdooConnectionError, OdooError
from .resolver.resolver import SONotFound
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


# The only countries offered in the Country filter (the client list's codes; Odoo's ISO codes for TU and UK are TR and GB).
FILTER_COUNTRIES = (
    "DZ AU AT AZ BH BN KH CA CL CN CR CZ DK AE EE FI GE GR HK HU IN ID IR IL JP JO KZ KE KW LV LT MY MV MU MD MN MA NP NL "
    "NC NZ NO OM PG PL PT RO RW SA SC SG KR ES LC SE TW TZ TH TR UA GB US VN FR ZA UG"
).split()


def odoo_or_http(fn):
    try:
        return fn()
    except OdooAuthError:
        raise HTTPException(401, "Odoo rejected your session; sign in again")
    except OdooConnectionError as e:
        raise HTTPException(502, f"Cannot reach Odoo: {e}")
    except OdooError as e:
        raise HTTPException(502, f"Odoo error: {e}")


@router.get("/countries")
def countries(user: CurrentUser = Depends(current_user), client: OdooReadClient = Depends(odoo_client)):
    """Odoo's countries, for the Country filter on the order screen."""
    rows = odoo_or_http(lambda: client.search_read("res.country", [("code", "in", FILTER_COUNTRIES)], ["name", "code"], order="name"))
    return [{"id": r["id"], "name": r["name"], "code": r.get("code") or ""} for r in rows]


@router.get("/so-list")
def so_list(country: int, limit: int = 200, user: CurrentUser = Depends(current_user),
            client: OdooReadClient = Depends(odoo_client)):
    """The most recent sales orders whose customer is in `country` (Odoo applies the user's own access rules)."""
    rows = odoo_or_http(lambda: client.search_read(
        "sale.order", [("partner_id.country_id", "=", country)], ["name", "partner_id"],
        limit=max(1, min(limit, 500)), order="date_order desc, id desc"))
    return [{"so": r["name"], "customer": (r.get("partner_id") or [0, ""])[1]} for r in rows]


@router.get("/so/{name}")
def get_so(name: str, refresh: bool = False, country: int | None = None, user: CurrentUser = Depends(current_user),
           client: OdooReadClient = Depends(odoo_client), settings: Settings = Depends(get_settings),
           db: Session = Depends(get_db)):
    """The order from Odoo, with the matching label PDF(s) found for every order line."""
    data = resolve_or_http(client, settings, name, refresh)
    if country:  # Country filter: an order of another country is "not found" for this search
        same = odoo_or_http(lambda: client.search_read(
            "sale.order", [("id", "=", data["so_id"]), ("partner_id.country_id", "=", country)], ["name"], limit=1))
        if not same:
            raise HTTPException(404, f"Sales order {data['so']!r} is not an order of the selected country")
    audit(db, user, "search", data["so"])
    resolve_matching(db)
    asked = {k: {"id": r.id, "created_at": request_json(r)["created_at"], "requested_by_name": r.requested_by_name}
             for k, r in open_by_code(db).items()}
    return enrich(data, get_index(settings), asked, open_all_by_code(db))
