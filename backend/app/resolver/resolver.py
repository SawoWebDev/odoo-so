"""SO number -> order header and order lines.

Odoo is only asked for what the screen shows: the order header, and per order line the product code, name,
ordered quantity and unit. Resolution is batched (one call per model, never one per record) and every group is
isolated: a model the user may not read becomes "not_accessible" instead of failing the whole search.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

from ..config import Settings
from ..odoo.client import OdooReadClient
from ..odoo.errors import OdooAccessError, OdooError, OdooMissingModel
from .schema import Rec, Schema, or_domain

GROUP_LABELS = {"header": "Sales Order", "references": "Reference", "lines": "Order lines"}

FIELD_LABELS = {
    "header.name": "SO number", "header.state": "Status", "header.date_order": "Order date", "header.customer": "Customer",
    "header.shipping_address": "Delivery address", "header.customer_ref": "Customer reference",
    "header.salesperson": "Salesperson", "header.commitment_date": "Delivery date",
    "ref.name": "Reference", "ref.contact": "Contact", "ref.scheduled": "Scheduled date",
    "ref.origin": "Source document", "ref.state": "Status",
    "line.product.code": "Item code", "line.product.name": "Product name", "line.qty": "Ordered qty",
}


class SONotFound(Exception):
    pass


def fmt_num(v: float | int | None, places: int = 4) -> str:
    if v is None:
        return ""
    s = f"{float(v):.{places}f}".rstrip("0").rstrip(".")
    return s or "0"


def fld(key: str, raw: Any, display: str | None = None, type: str = "text", uom: str | None = None) -> dict:
    if display is None:
        display = "" if raw in (None, False) else str(raw)
    return {"label": FIELD_LABELS[key], "raw": None if raw is False else raw, "display": display, "type": type, "uom": uom}


def f_text(key: str, v: Any) -> dict:
    return fld(key, None if v in (False, None, "") else v, "" if v in (False, None) else str(v))


def f_date(key: str, v: Any) -> dict:
    return fld(key, None if not v else v, "" if not v else str(v), "date")


def f_m2o(key: str, rec: Rec, logical: str) -> dict:
    i, name = rec.m2o(logical)
    return fld(key, i, name)


def make_row(group: str, rid: Any, label: str, fields: dict, *, line_id: int | None = None, state: str = "",
             disabled_reason: str = "", disabled_kind: str = "") -> dict:
    """A disabled row is shown but cannot be ticked or printed (enforced again on the server).
    `disabled_kind`: "no_qty" (grey) or "no_label" (warning colour)."""
    return {"row_id": f"{group}:{rid}", "label": label, "line_id": line_id, "state": state, "fields": fields,
            "disabled": bool(disabled_reason), "disabled_reason": disabled_reason, "disabled_kind": disabled_kind}


def memo(fn: Callable):
    """Memoise a loader, including its failure, so dependent groups share one fetch and one error."""
    @wraps(fn)
    def wrapper(self, *a):
        key = (fn.__name__, a)
        if key in self._memo:
            v = self._memo[key]
            if isinstance(v, Exception):
                raise v
            return v
        try:
            v = fn(self, *a)
        except OdooError as e:
            self._memo[key] = e
            raise
        self._memo[key] = v
        return v
    return wrapper


class SOResolver:
    def __init__(self, client: OdooReadClient, settings: Settings, fields_cache: dict | None = None):
        self.client = client
        self.cfg = settings
        self.s = Schema(client, fields_cache)
        self._memo: dict = {}

    def resolve(self, so_name: str) -> dict:
        so = self._find_so(so_name)
        self._so = so
        return {
            "so": so.text("name"),
            "so_id": so.id,
            "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "odoo_uid": self.client.uid,
            "groups": [self._run("header", self.g_header), self._run("references", self.g_references),
                       self._run("lines", self.g_lines)],
        }

    def _find_so(self, name: str) -> Rec:
        rows = self.s.search_read("sale.order", self.s.d("sale.order", "name", "=", name.strip()), None, limit=1)
        if not rows:  # also what a user without access sees: Odoo returns nothing, we say "not found"
            raise SONotFound(name)
        return rows[0]

    def _run(self, gid: str, fn: Callable[[], list[dict]]) -> dict:
        group = {"id": gid, "label": GROUP_LABELS[gid], "status": "ok", "message": "", "rows": []}
        try:
            group["rows"] = fn()
            if not group["rows"]:
                group["status"] = "empty"
        except OdooAccessError as e:
            group.update(status="not_accessible", message=str(e) or "You do not have access to this data in Odoo")
        except OdooMissingModel:
            group.update(status="not_installed", message="This Odoo module is not installed")
        except OdooError as e:
            group.update(status="error", message=str(e))
        return group

    @memo
    def lines(self) -> list[Rec]:
        recs = self.s.search_read_in("sale.order.line", "order", [self._so.id], None, order="sequence, id")
        return [r for r in recs if not r.raw("display_type")]  # skip section / note lines

    @memo
    def products(self) -> dict[int, Rec]:
        pids = [r.m2o("product")[0] for r in self.lines()]
        return {r.id: r for r in self.s.read("product.product", [p for p in pids if p], None)}

    @memo
    def pickings(self) -> list[Rec]:
        """Only the transfers whose Sales Order is this order (the "Sales Order" column in Odoo's Transfers list).
        Where Odoo has no such field, fall back to the source document being exactly this SO number. Never anything else.
        Of those, only the ones whose source location is `reference_source_location` (PL1/Output) are kept."""
        name = self._so.text("name")
        terms = self.s.d("stock.picking", "sale", "=", self._so.id) or self.s.d("stock.picking", "origin", "=", name)
        if not terms:
            return []
        picks = self.s.search_read("stock.picking", terms, None, order="id desc")
        picks = [p for p in picks if p.m2o("sale")[0] == self._so.id or (not p.has("sale") and p.text("origin") == name)]
        want = self.cfg.reference_source_location.strip().strip("/").lower()
        if want and picks and picks[0].has("source"):  # only transfers that leave from the configured source location
            def leaves_from(p: Rec) -> bool:
                loc = p.m2o("source")[1].strip().strip("/").lower()
                return loc == want or loc.startswith(want + "/")
            picks = [p for p in picks if leaves_from(p)]
        return picks

    def g_references(self) -> list[dict]:
        """One row per transfer; `line_ids` are the order lines whose product is moved by it (what choosing it shows)."""
        picks = self.pickings()
        by_prod: dict[int, list[int]] = {}
        for ln in self.lines():
            by_prod.setdefault(ln.m2o("product")[0] or 0, []).append(ln.id)
        moved: dict[int, set[int]] = {}
        for mv in self.s.search_read_in("stock.move", "picking", [p.id for p in picks], None):
            pid, prod = mv.m2o("picking")[0], mv.m2o("product")[0]
            if pid and prod:
                moved.setdefault(pid, set()).add(prod)
        rows = []
        for p in picks:
            fields = {
                "ref.name": f_text("ref.name", p.raw("name")),
                "ref.contact": f_m2o("ref.contact", p, "partner"),
                "ref.scheduled": f_date("ref.scheduled", p.raw("scheduled")),
                "ref.origin": f_text("ref.origin", p.raw("origin")),
                "ref.state": fld("ref.state", p.raw("state"), p.state_label("state")),
            }
            row = make_row("references", p.id, p.text("name"), fields, state=p.text("state"))
            row["line_ids"] = sorted({lid for prod in moved.get(p.id, ()) for lid in by_prod.get(prod, [])})
            rows.append(row)
        return rows

    def g_header(self) -> list[dict]:
        so = self._so
        fields = {
            "header.name": f_text("header.name", so.raw("name")),
            "header.state": fld("header.state", so.raw("state"), so.state_label("state")),
            "header.date_order": f_date("header.date_order", so.raw("date_order")),
            "header.customer": f_m2o("header.customer", so, "partner"),
            "header.shipping_address": f_m2o("header.shipping_address", so, "shipping"),
            "header.customer_ref": f_text("header.customer_ref", so.raw("client_ref")),
            "header.salesperson": f_m2o("header.salesperson", so, "salesperson"),
            "header.commitment_date": f_date("header.commitment_date", so.raw("commitment")),
        }
        return [make_row("header", so.id, so.text("name"), fields, state=so.text("state"))]

    def g_lines(self) -> list[dict]:
        rows = []
        for ln in self.lines():
            prod = self.products().get(ln.m2o("product")[0] or 0)
            code = prod.text("code") if prod else ""
            if not code:
                continue  # no item code = a charge/fee/service line (Surcharge, Bank Charge, ...): nothing to label
            uom_name = ln.m2o("uom")[1]
            qty = ln.num("qty")
            fields = {
                "line.product.code": f_text("line.product.code", code),
                "line.product.name": f_text("line.product.name", prod.raw("name")),
                "line.qty": fld("line.qty", qty, fmt_num(qty), "number", uom_name),
            }
            no_qty = "" if (qty is not None and qty > 0) else "Ordered quantity is 0 - nothing to print"
            rows.append(make_row("lines", ln.id, f"[{code}] {prod.text('name')}", fields, line_id=ln.id,
                                 disabled_reason=no_qty, disabled_kind="no_qty" if no_qty else ""))
        return rows


def to_public(resolved: dict) -> dict:
    return resolved
