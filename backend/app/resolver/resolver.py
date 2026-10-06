"""SO number -> grouped, normalised records (guideline section 5).

Resolution is batched (one call per model per step, never one per record) and every group is isolated:
a model the user may not read becomes status "not_accessible", an uninstalled module "not_installed",
and neither fails the whole search. Every quantity carries its UoM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

from ..catalog.catalog import GROUP_LABELS
from ..config import Settings
from ..odoo.client import OdooReadClient
from ..odoo.errors import OdooAccessError, OdooError, OdooMissingModel
from .schema import Rec, Schema, or_domain


class SONotFound(Exception):
    pass


# ---- field/row constructors --------------------------------------------------------------------

def positive(v: float | None) -> float | None:
    """Odoo returns 0.0 for an unset weight/volume: treat it as missing so it can never print as a silent zero."""
    return v if v is not None and v > 0 else None


def fmt_num(v: float | int | None, places: int = 4) -> str:
    if v is None:
        return ""
    s = f"{float(v):.{places}f}".rstrip("0").rstrip(".")
    return s or "0"


def fld(raw: Any, display: str | None = None, type: str = "text", uom: str | None = None) -> dict:
    if display is None:
        display = "" if raw in (None, False) else str(raw)
    return {"raw": None if raw is False else raw, "display": display, "type": type, "uom": uom}


def f_text(v: Any) -> dict:
    return fld(None if v in (False, None, "") else v, "" if v in (False, None) else str(v))


def f_num(v: float | None, uom: str | None = None) -> dict:
    return fld(v, fmt_num(v), "number", uom)


def f_date(v: Any) -> dict:
    return fld(None if not v else v, "" if not v else str(v), "date")


def f_m2o(rec: Rec, logical: str) -> dict:
    i, name = rec.m2o(logical)
    return fld(i, name)


def make_row(group: str, rid: Any, label: str, scope: str, fields: dict, *, line_id: int | None = None,
             meta: dict | None = None, state: str = "") -> dict:
    return {"row_id": f"{group}:{rid}", "label": label, "scope": scope, "line_id": line_id,
            "state": state, "fields": fields, "meta": meta or {}}


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
        self.warnings: list[str] = []

    # ============================== public ====================================================
    def resolve(self, so_name: str) -> dict:
        so = self._find_so(so_name)
        self._so = so
        builders: list[tuple[str, Callable[[], list[dict]]]] = [
            ("header", self.g_header), ("lines", self.g_lines), ("products", self.g_products),
            ("bom", self.g_bom), ("mrp", self.g_mrp), ("purchasing", self.g_purchasing),
            ("delivery", self.g_delivery), ("invoicing", self.g_invoicing),
        ]
        groups = [self._run(gid, fn) for gid, fn in builders]
        return {
            "so": so.text("name"),
            "so_id": so.id,
            "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "odoo_uid": self.client.uid,
            "groups": groups,
            "warnings": self.warnings,
        }

    # ============================== plumbing ==================================================
    def _find_so(self, name: str) -> Rec:
        name = name.strip()
        rows = self.s.search_read("sale.order", self.s.d("sale.order", "name", "=", name), None, limit=1)
        if not rows:  # also finds records the user cannot see: Odoo returns nothing, we say "not found"
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

    # ============================== loaders ===================================================
    @memo
    def lines(self) -> list[Rec]:
        recs = self.s.search_read_in("sale.order.line", "order", [self._so.id], None, order="sequence, id")
        return [r for r in recs if not r.raw("display_type")]

    @memo
    def products(self) -> dict[int, Rec]:
        pids = [r.m2o("product")[0] for r in self.lines()]
        return {r.id: r for r in self.s.read("product.product", [p for p in pids if p], None)}

    @memo
    def uoms(self) -> dict[int, Rec]:
        ids: list[int] = []
        for ln in self.lines():
            ids.append(ln.m2o("uom")[0] or 0)
        for p in self.products().values():
            ids.append(p.m2o("uom")[0] or 0)
        try:
            return {r.id: r for r in self.s.read("uom.uom", ids, None)}
        except OdooError:
            return {}

    @memo
    def packagings(self) -> dict[int, list[Rec]]:
        out: dict[int, list[Rec]] = {}
        try:
            for r in self.s.search_read_in("product.packaging", "product", list(self.products()), None):
                out.setdefault(r.m2o("product")[0] or 0, []).append(r)
        except OdooError:
            pass  # packaging is optional (module/ACL); its absence just disables per-carton calc
        return out

    @memo
    def so_line_ids_by_product(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for ln in self.lines():
            out.setdefault(ln.m2o("product")[0] or 0, []).append(ln.id)
        return out

    def _line_for_product(self, pid: int | None) -> int | None:
        ids = self.so_line_ids_by_product().get(pid or 0)
        return ids[0] if ids else None

    def _uom_info(self, uom_id: int | None, uom_name: str) -> dict:
        r = self.uoms().get(uom_id or 0)
        return {"id": uom_id, "name": uom_name,
                "factor": r.num("factor") if r else None, "category": r.m2o("category")[0] if r else None}

    # ============================== groups ====================================================
    def g_header(self) -> list[dict]:
        so = self._so
        fields = {
            "header.name": f_text(so.raw("name")),
            "header.state": fld(so.raw("state"), so.state_label("state")),
            "header.date_order": f_date(so.raw("date_order")),
            "header.customer": f_m2o(so, "partner"),
            "header.shipping_address": f_m2o(so, "shipping"),
            "header.customer_ref": f_text(so.raw("client_ref")),
            "header.salesperson": f_m2o(so, "salesperson"),
            "header.commitment_date": f_date(so.raw("commitment")),
        }
        return [make_row("header", so.id, so.text("name"), "so", fields, state=so.text("state"))]

    def g_lines(self) -> list[dict]:
        wf, vf = self.cfg.weight_factor_to_kg, self.cfg.volume_factor_to_m3
        rows = []
        for ln in self.lines():
            pid, pname = ln.m2o("product")
            prod = self.products().get(pid or 0)
            uom_id, uom_name = ln.m2o("uom")
            qty = ln.num("qty")
            w0, v0 = positive(prod.num("weight")) if prod else None, positive(prod.num("volume")) if prod else None
            weight = w0 * wf if w0 is not None else None
            volume = v0 * vf if v0 is not None else None
            fields = {
                "line.product.code": f_text(prod.raw("code") if prod else None),
                "line.product.name": f_text(prod.raw("name") if prod else pname),
                "line.description": f_text(ln.raw("name")),
                "line.qty": f_num(qty, uom_name),
                "line.uom": fld(uom_id, uom_name),
                "line.qty_delivered": f_num(ln.num("qty_delivered"), uom_name),
                "line.qty_invoiced": f_num(ln.num("qty_invoiced"), uom_name),
                "line.price_unit": f_num(ln.num("price_unit")),
                "line.product.barcode": f_text(prod.raw("barcode") if prod else None),
                "line.product.image": self._image(prod),
                "line.product.weight": f_num(weight, "kg"),
                "line.product.volume": f_num(volume, "m3"),
            }
            label = f"[{prod.text('code')}] {prod.text('name')}" if prod and prod.text("code") else (pname or ln.text("name"))
            meta = self._calc_meta(ln, prod, weight, volume)
            rows.append(make_row("lines", ln.id, label, "line", fields, line_id=ln.id, meta=meta))
        return rows

    def _image(self, prod: Rec | None) -> dict:
        v = prod.raw("image") if prod else None
        return {"raw": v or None, "display": "[image]" if v else "", "type": "image", "uom": None}

    def _calc_meta(self, ln: Rec, prod: Rec | None, weight: float | None, volume: float | None) -> dict:
        uom_id, uom_name = ln.m2o("uom")
        puom_id, puom_name = prod.m2o("uom") if prod else (None, "")
        pk = [{"id": p.id, "name": p.text("name"), "qty": p.num("qty"), "barcode": p.text("barcode")}
              for p in self.packagings().get(prod.id if prod else 0, [])]
        pk_id = ln.m2o("packaging")[0]
        return {
            "qty": ln.num("qty"),
            "uom": self._uom_info(uom_id, uom_name),
            "product_uom": self._uom_info(puom_id, puom_name),
            "unit_weight_kg": weight, "unit_volume_m3": volume,
            "packagings": pk, "line_packaging_id": pk_id, "line_packaging_qty": ln.num("packaging_qty"),
        }

    def g_products(self) -> list[dict]:
        rows = []
        for ln in self.lines():
            pid = ln.m2o("product")[0]
            prod = self.products().get(pid or 0)
            if not prod:
                continue
            pks = self.packagings().get(prod.id, [])
            best = max(pks, key=lambda p: p.num("qty") or 0) if pks else None
            wf, vf = self.cfg.weight_factor_to_kg, self.cfg.volume_factor_to_m3
            w = positive(prod.num("weight"))
            v = positive(prod.num("volume"))
            fields = {
                "product.code": f_text(prod.raw("code")),
                "product.name": f_text(prod.raw("name")),
                "product.barcode": f_text(prod.raw("barcode")),
                "product.image": self._image(prod),
                "product.weight": f_num(w * wf if w is not None else None, "kg"),
                "product.volume": f_num(v * vf if v is not None else None, "m3"),
                "product.uom": f_m2o(prod, "uom"),
                "product.packaging": f_text(", ".join(f"{p.text('name')} ({fmt_num(p.num('qty'))})" for p in pks)),
                "product.packaging_qty": f_num(best.num("qty") if best else None),
                "product.packaging_barcode": f_text(best.raw("barcode") if best else None),
            }
            rows.append(make_row("products", ln.id, f"[{prod.text('code')}] {prod.text('name')}", "line", fields,
                                 line_id=ln.id, meta=self._calc_meta(ln, prod, None if w is None else w * wf,
                                                                      None if v is None else v * vf)))
        return rows

    # ---- BOM ---------------------------------------------------------------------------------
    @memo
    def _bom_for(self, product_ids: tuple, tmpl_ids: tuple) -> dict[int, Rec]:
        """product id -> best BOM (lowest sequence). One call for the whole batch."""
        if not tmpl_ids:
            return {}
        boms = self.s.search_read_in("mrp.bom", "tmpl", list(tmpl_ids), None, order="sequence, id")
        out: dict[int, Rec] = {}
        for pid, tid in zip(product_ids, tmpl_ids):
            for b in boms:
                bp = b.m2o("product")[0]
                if b.m2o("tmpl")[0] == tid and (not bp or bp == pid) and pid not in out:
                    out[pid] = b
        return out

    def g_bom(self) -> list[dict]:
        if not self.s.has_model("mrp.bom"):
            raise OdooMissingModel("mrp.bom")
        rows: list[dict] = []
        lines, prods = self.lines(), self.products()
        # frontier items: (order line, parent product rec, bom rec, parent qty needed, parent uom id, level)
        frontier: list[tuple[Rec, Rec, Rec, float | None, int | None, int]] = []
        pids, tids = [], []
        for ln in lines:
            p = prods.get(ln.m2o("product")[0] or 0)
            if p:
                pids.append(p.id)
                tids.append(p.m2o("tmpl")[0] or 0)
        boms = self._bom_for(tuple(pids), tuple(tids))
        for ln in lines:
            p = prods.get(ln.m2o("product")[0] or 0)
            if p and p.id in boms:
                frontier.append((ln, p, boms[p.id], ln.num("qty"), ln.m2o("uom")[0], 1))
        seen_products = dict(prods)
        for level in range(1, max(1, self.cfg.bom_depth) + 1):
            if not frontier:
                break
            bom_ids = [b.id for _, _, b, _, _, _ in frontier]
            comps = self.s.search_read_in("mrp.bom.line", "bom", bom_ids, None, order="sequence, id")
            by_bom: dict[int, list[Rec]] = {}
            for c in comps:
                by_bom.setdefault(c.m2o("bom")[0] or 0, []).append(c)
            need = [c.m2o("product")[0] for c in comps if c.m2o("product")[0] not in seen_products]
            for r in self.s.read("product.product", [n for n in need if n], None):
                seen_products[r.id] = r
            next_frontier = []
            nxt_pids, nxt_tids = [], []
            for c in comps:
                cp = seen_products.get(c.m2o("product")[0] or 0)
                if cp:
                    nxt_pids.append(cp.id)
                    nxt_tids.append(cp.m2o("tmpl")[0] or 0)
            child_boms = self._bom_for(tuple(nxt_pids), tuple(nxt_tids)) if level < self.cfg.bom_depth else {}
            for ln, parent, bom, parent_qty, parent_uom, _lvl in frontier:
                bom_qty = bom.num("qty") or 1.0
                for c in by_bom.get(bom.id, []):
                    cp = seen_products.get(c.m2o("product")[0] or 0)
                    cqty = c.num("qty")
                    cuom_id, cuom_name = c.m2o("uom")
                    # Scale to the order only when the BOM UoM equals the quantity's UoM; otherwise leave blank.
                    same_uom = bom.m2o("uom")[0] == parent_uom or not bom.m2o("uom")[0]
                    total = (cqty / bom_qty * parent_qty) if (cqty is not None and parent_qty is not None and same_uom) else None
                    fields = {
                        "bom.component.code": f_text(cp.raw("code") if cp else None),
                        "bom.component.name": f_text(cp.raw("name") if cp else c.m2o("product")[1]),
                        "bom.qty": f_num(cqty, cuom_name),
                        "bom.uom": fld(cuom_id, cuom_name),
                        "bom.qty_total": f_num(total, cuom_name),
                        "bom.level": fld(level, str(level), "number"),
                        "bom.parent": f_text(parent.raw("name")),
                    }
                    rows.append(make_row("bom", f"{ln.id}:{c.id}", f"{'  ' * (level - 1)}{c.m2o('product')[1]}",
                                         "line", fields, line_id=ln.id))
                    if cp and cp.id in child_boms:
                        next_frontier.append((ln, cp, child_boms[cp.id], total, cuom_id, level + 1))
            frontier = next_frontier
        return rows

    # ---- Manufacturing -----------------------------------------------------------------------
    @memo
    def mos(self) -> list[Rec]:
        if not self.s.has_model("mrp.production"):
            raise OdooMissingModel("mrp.production")
        so_name = self._so.text("name")
        group_id = self._so.m2o("procurement_group")[0]
        terms = self.s.d("mrp.production", "origin", "=", so_name)
        if group_id:
            terms += self.s.d("mrp.production", "procurement_group", "=", group_id)
        found = {m.id: m for m in self.s.search_read("mrp.production", or_domain(terms), None)} if terms else {}
        frontier = list(found.values())
        origin = self.s.pick("mrp.production", "origin")
        for _ in range(max(1, self.cfg.bom_depth)):  # sub-assembly MOs reference the parent MO name as origin
            names = [m.text("name") for m in frontier if m.text("name")]
            if not names or not origin:
                break
            kids = self.s.search_read("mrp.production", or_domain([(origin, "=", n) for n in names[:50]]), None)
            frontier = [k for k in kids if k.id not in found]
            found.update({k.id: k for k in kids})
        return list(found.values())

    @memo
    def workorders(self) -> list[Rec]:
        try:
            return self.s.search_read_in("mrp.workorder", "production", [m.id for m in self.mos()], None)
        except OdooMissingModel:
            return []  # work orders need the Manufacturing work-orders option

    @memo
    def raw_moves(self) -> list[Rec]:
        return self.s.search_read_in("stock.move", "raw_for", [m.id for m in self.mos()], None)

    @memo
    def raw_move_lots(self) -> dict[int, list[str]]:
        moves = self.raw_moves()
        out: dict[int, list[str]] = {}
        for ml in self.s.search_read_in("stock.move.line", "move", [m.id for m in moves], None):
            lot = ml.m2o("lot")[1]
            if lot:
                out.setdefault(ml.m2o("move")[0] or 0, []).append(lot)
        return out

    def g_mrp(self) -> list[dict]:
        rows = []
        for mo in self.mos():
            uom_name = mo.m2o("uom")[1]
            pid, pname = mo.m2o("product")
            fields = {
                "mrp.name": f_text(mo.raw("name")),
                "mrp.state": fld(mo.raw("state"), mo.state_label("state")),
                "mrp.product": fld(pid, pname),
                "mrp.qty": f_num(mo.num("qty"), uom_name),
                "mrp.uom": fld(mo.m2o("uom")[0], uom_name),
                "mrp.date_start": f_date(mo.raw("date_start")),
                "mrp.bom": f_m2o(mo, "bom"),
            }
            rows.append(make_row("mrp", mo.id, f"{mo.text('name')} - {pname}", "line", fields,
                                 line_id=self._line_for_product(pid), state=mo.text("state")))
        for wo in self.workorders():
            mo_id, mo_name = wo.m2o("production")
            fields = {
                "mrp.name": fld(mo_id, mo_name),
                "mrp.wo.name": f_text(wo.raw("name")),
                "mrp.wo.state": fld(wo.raw("state"), wo.state_label("state")),
                "mrp.wo.workcenter": f_m2o(wo, "workcenter"),
            }
            rows.append(make_row("mrp_wo", wo.id, f"{mo_name}: {wo.text('name')}", "line", fields, state=wo.text("state")))
        lots = self.raw_move_lots()
        for mv in self.raw_moves():
            uom_name = mv.m2o("uom")[1]
            pid, pname = mv.m2o("product")
            fields = {
                "mrp.name": f_m2o(mv, "raw_for"),
                "mrp.move.product": fld(pid, pname),
                "mrp.move.qty": f_num(mv.num("done_qty"), uom_name),
                "mrp.move.uom": fld(mv.m2o("uom")[0], uom_name),
                "mrp.move.lot": f_text(", ".join(lots.get(mv.id, []))),
            }
            rows.append(make_row("mrp_move", mv.id, f"{mv.m2o('raw_for')[1]}: {pname}", "lot", fields, state=mv.text("state")))
        return rows

    # ---- Purchasing --------------------------------------------------------------------------
    @memo
    def po_lines(self) -> list[Rec]:
        if not self.s.has_model("purchase.order.line"):
            raise OdooMissingModel("purchase.order.line")
        found: dict[int, Rec] = {}
        for r in self.s.search_read_in("purchase.order.line", "sale_line", [ln.id for ln in self.lines()], None):
            found[r.id] = r
        so_name = self._so.text("name")
        origin = self.s.pick("purchase.order", "origin")
        if origin:  # dropship / MTO purchases reference the SO (or its MOs) in their origin
            names = [so_name] + [m.text("name") for m in self._safe_mos()]
            pos = self.s.search_read("purchase.order", or_domain([(origin, "ilike", n) for n in names[:30]]), None)
            for r in self.s.search_read_in("purchase.order.line", "order", [p.id for p in pos], None):
                found[r.id] = r
        return list(found.values())

    def _safe_mos(self) -> list[Rec]:
        try:
            return self.mos()
        except OdooError:
            return []

    @memo
    def pos(self) -> dict[int, Rec]:
        ids = [r.m2o("order")[0] for r in self.po_lines()]
        return {p.id: p for p in self.s.read("purchase.order", [i for i in ids if i], None)}

    def g_purchasing(self) -> list[dict]:
        rows = []
        for pl in self.po_lines():
            po = self.pos().get(pl.m2o("order")[0] or 0)
            uom_name = pl.m2o("uom")[1]
            pid, pname = pl.m2o("product")
            fields = {
                "purchase.name": f_text(po.raw("name") if po else pl.m2o("order")[1]),
                "purchase.vendor": f_m2o(po, "partner") if po else f_text(None),
                "purchase.state": fld(po.raw("state") if po else None, po.state_label("state") if po else ""),
                "purchase.product": fld(pid, pname),
                "purchase.qty": f_num(pl.num("qty"), uom_name),
                "purchase.qty_received": f_num(pl.num("qty_received"), uom_name),
                "purchase.uom": fld(pl.m2o("uom")[0], uom_name),
                "purchase.date_planned": f_date(pl.raw("date_planned")),
            }
            rows.append(make_row("purchasing", pl.id, f"{fields['purchase.name']['display']} - {pname}", "line", fields,
                                 line_id=pl.m2o("sale_line")[0], state=po.text("state") if po else ""))
        return rows

    # ---- Delivery ----------------------------------------------------------------------------
    @memo
    def pickings(self) -> list[Rec]:
        if not self.s.has_model("stock.picking"):
            raise OdooMissingModel("stock.picking")
        group_id = self._so.m2o("procurement_group")[0]
        terms = self.s.d("stock.picking", "sale", "=", self._so.id)
        if group_id:
            terms += self.s.d("stock.picking", "group", "=", group_id)
        found = {p.id: p for p in self.s.search_read("stock.picking", or_domain(terms), None)} if terms else {}
        origin = self.s.pick("stock.picking", "origin")
        if found and origin:  # returns reference "Return of <picking name>"
            names = ["Return of " + p.text("name") for p in found.values()]
            for p in self.s.search_read("stock.picking", or_domain([(origin, "=", n) for n in names[:50]]), None):
                found.setdefault(p.id, p)
        return sorted(found.values(), key=lambda p: p.text("name"))

    @memo
    def moves(self) -> list[Rec]:
        return self.s.search_read_in("stock.move", "picking", [p.id for p in self.pickings()], None)

    @memo
    def move_lines(self) -> list[Rec]:
        return self.s.search_read_in("stock.move.line", "picking", [p.id for p in self.pickings()], None)

    @memo
    def packages(self) -> dict[int, Rec]:
        ids = [m.m2o("package")[0] for m in self.move_lines()]
        try:
            return {r.id: r for r in self.s.read("stock.quant.package", [i for i in ids if i], None)}
        except OdooError:
            return {}

    def g_delivery(self) -> list[dict]:
        pickings = {p.id: p for p in self.pickings()}
        moves = {m.id: m for m in self.moves()}
        mls = self.move_lines()
        rows = []

        def pick_fields(pk: Rec | None) -> dict:
            if not pk:
                return {}
            code = pk.text("type_code")
            is_return = "return" in pk.text("origin").lower()
            kind = "return" if is_return else {"outgoing": "delivery", "incoming": "receipt"}.get(code, code or "transfer")
            return {
                "delivery.picking": f_text(pk.raw("name")),
                "delivery.state": fld(pk.raw("state"), pk.state_label("state")),
                "delivery.scheduled": f_date(pk.raw("scheduled")),
                "delivery.done": f_date(pk.raw("done")),
                "delivery.kind": f_text(kind),
                "delivery.backorder_of": f_m2o(pk, "backorder"),
            }

        covered_moves = set()
        wf = self.cfg.weight_factor_to_kg
        for ml in mls:
            pk = pickings.get(ml.m2o("picking")[0] or 0)
            mv = moves.get(ml.m2o("move")[0] or 0)
            if mv:
                covered_moves.add(mv.id)
            uom_name = ml.m2o("uom")[1]
            pid, pname = ml.m2o("product")
            lot = ml.m2o("lot")[1] or ml.text("lot_name")
            pkg_id, pkg_name = ml.m2o("package")
            pkg = self.packages().get(pkg_id or 0)
            fields = pick_fields(pk) | {
                "delivery.product": fld(pid, pname),
                "delivery.qty": f_num(ml.num("done_qty"), uom_name),
                "delivery.uom": fld(ml.m2o("uom")[0], uom_name),
                "delivery.lot": f_text(lot),
                "delivery.package": fld(pkg_id, pkg_name or ""),
            }
            scope = "lot" if lot else ("package" if pkg_id else "line")
            w = pkg.num("weight") if pkg else None
            meta = {"qty": ml.num("done_qty"), "uom": uom_name, "package_id": pkg_id, "package_name": pkg_name,
                    "package_weight_kg": None if w is None else w * wf, "product_id": pid}
            line_id = mv.m2o("sale_line")[0] if mv else None
            rows.append(make_row("delivery", f"ml{ml.id}", f"{fields.get('delivery.picking', {}).get('display', '')} - {pname}"
                                 + (f" - {lot}" if lot else ""), scope, fields,
                                 line_id=line_id or self._line_for_product(pid), meta=meta, state=ml.text("state")))
        for mv in moves.values():  # moves with no move lines yet (not reserved / cancelled / waiting)
            if mv.id in covered_moves:
                continue
            pk = pickings.get(mv.m2o("picking")[0] or 0)
            uom_name = mv.m2o("uom")[1]
            pid, pname = mv.m2o("product")
            fields = pick_fields(pk) | {
                "delivery.product": fld(pid, pname),
                "delivery.qty": f_num(mv.num("done_qty") or mv.num("demand"), uom_name),
                "delivery.uom": fld(mv.m2o("uom")[0], uom_name),
                "delivery.lot": f_text(None),
                "delivery.package": f_text(None),
            }
            rows.append(make_row("delivery", f"mv{mv.id}", f"{fields.get('delivery.picking', {}).get('display', '')} - {pname}",
                                 "line", fields, line_id=mv.m2o("sale_line")[0] or self._line_for_product(pid),
                                 meta={"qty": mv.num("done_qty") or mv.num("demand"), "uom": uom_name, "product_id": pid},
                                 state=mv.text("state")))
        return rows

    # ---- Invoicing ---------------------------------------------------------------------------
    @memo
    def invoices(self) -> list[Rec]:
        ids = self._so.ids("invoices")
        if not ids and self.s.has_model("account.move.line"):  # fallback: invoice line -> SO line link
            mls = self.s.search_read_in("account.move.line", "sale_lines", [ln.id for ln in self.lines()], None)
            ids = [m.m2o("move")[0] for m in mls if m.m2o("move")[0]]
        return self.s.read("account.move", ids, None)

    def g_invoicing(self) -> list[dict]:
        rows = []
        for inv in self.invoices():
            cur = inv.m2o("currency")[1]
            fields = {
                "invoice.name": f_text(inv.raw("name")),
                "invoice.state": fld(inv.raw("state"), inv.state_label("state")),
                "invoice.amount_total": f_num(inv.num("amount_total"), cur),
                "invoice.currency": fld(inv.m2o("currency")[0], cur),
                "invoice.date": f_date(inv.raw("date")),
                "invoice.payment_state": fld(inv.raw("payment_state"), inv.state_label("payment_state")),
            }
            rows.append(make_row("invoicing", inv.id, inv.text("name") or f"Invoice {inv.id}", "so", fields,
                                 state=inv.text("state")))
        return rows


def to_public(resolved: dict) -> dict:
    """Copy for the browser: image payloads (base64, large) stay server-side, replaced by a flag."""
    out = {k: v for k, v in resolved.items() if k != "groups"}
    out["groups"] = []
    for g in resolved["groups"]:
        rows = []
        for r in g["rows"]:
            fields = {}
            for k, f in r["fields"].items():
                fields[k] = {**f, "raw": bool(f["raw"])} if f["type"] == "image" else f
            rows.append({**r, "fields": fields})
        out["groups"].append({**g, "rows": rows})
    return out
