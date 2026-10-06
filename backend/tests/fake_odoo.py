"""In-memory Odoo double. Implements the Transport protocol, evaluates prefix-notation domains,
records every call (so tests can prove only read methods were used) and can deny / hide models."""
from __future__ import annotations

from app.odoo.client import OdooReadClient
from app.odoo.errors import OdooAccessError, OdooAuthError, OdooError, OdooMissingModel
from app.odoo.transports import assert_allowed

M2O = "many2one"
X2M = "one2many"


def _f(type_="char", relation=None, selection=None):
    d = {"type": type_, "string": "x"}
    if relation:
        d["relation"] = relation
    if selection:
        d["selection"] = selection
    return d


def default_fields(version: str = "17") -> dict[str, dict]:
    qty_line = "quantity" if version >= "17" else "qty_done"
    f = {
        "sale.order": {
            "name": _f(), "state": _f("selection", selection=[("draft", "Quotation"), ("sale", "Sales Order")]),
            "date_order": _f("datetime"), "partner_id": _f(M2O, "res.partner"), "partner_shipping_id": _f(M2O, "res.partner"),
            "client_order_ref": _f(), "user_id": _f(M2O, "res.users"), "commitment_date": _f("datetime"),
            "invoice_ids": _f("many2many", "account.move"), "procurement_group_id": _f(M2O, "procurement.group"),
            "order_line": _f(X2M, "sale.order.line"),
        },
        "sale.order.line": {
            "order_id": _f(M2O, "sale.order"), "product_id": _f(M2O, "product.product"), "name": _f(),
            "product_uom_qty": _f("float"), "product_uom": _f(M2O, "uom.uom"), "qty_delivered": _f("float"),
            "qty_invoiced": _f("float"), "price_unit": _f("float"), "sequence": _f("integer"), "display_type": _f(),
            "product_packaging_id": _f(M2O, "product.packaging"), "product_packaging_qty": _f("float"),
        },
        "product.product": {
            "default_code": _f(), "name": _f(), "barcode": _f(), "image_1024": _f("binary"), "weight": _f("float"),
            "volume": _f("float"), "uom_id": _f(M2O, "uom.uom"), "product_tmpl_id": _f(M2O, "product.template"),
        },
        "product.packaging": {"product_id": _f(M2O, "product.product"), "name": _f(), "qty": _f("float"), "barcode": _f()},
        "uom.uom": {"name": _f(), "factor": _f("float"), "category_id": _f(M2O, "uom.category")},
        "mrp.bom": {"product_tmpl_id": _f(M2O, "product.template"), "product_id": _f(M2O, "product.product"),
                    "product_qty": _f("float"), "product_uom_id": _f(M2O, "uom.uom"), "type": _f(), "code": _f(),
                    "sequence": _f("integer")},
        "mrp.bom.line": {"bom_id": _f(M2O, "mrp.bom"), "product_id": _f(M2O, "product.product"),
                         "product_qty": _f("float"), "product_uom_id": _f(M2O, "uom.uom"), "sequence": _f("integer")},
        "mrp.production": {"name": _f(), "state": _f("selection", selection=[("confirmed", "Confirmed"), ("done", "Done")]),
                           "product_id": _f(M2O, "product.product"), "product_qty": _f("float"),
                           "product_uom_id": _f(M2O, "uom.uom"), "date_start": _f("datetime"), "bom_id": _f(M2O, "mrp.bom"),
                           "origin": _f(), "procurement_group_id": _f(M2O, "procurement.group"), "qty_produced": _f("float")},
        "mrp.workorder": {"name": _f(), "state": _f("selection", selection=[("ready", "Ready")]),
                          "production_id": _f(M2O, "mrp.production"), "workcenter_id": _f(M2O, "mrp.workcenter"),
                          "duration_expected": _f("float"), "duration": _f("float")},
        "purchase.order": {"name": _f(), "state": _f("selection", selection=[("purchase", "Purchase Order")]),
                           "partner_id": _f(M2O, "res.partner"), "origin": _f(), "date_planned": _f("datetime")},
        "purchase.order.line": {"order_id": _f(M2O, "purchase.order"), "product_id": _f(M2O, "product.product"),
                                "name": _f(), "product_qty": _f("float"), "product_uom": _f(M2O, "uom.uom"),
                                "qty_received": _f("float"), "date_planned": _f("datetime"),
                                "sale_line_id": _f(M2O, "sale.order.line")},
        "stock.picking": {"name": _f(), "state": _f("selection", selection=[("assigned", "Ready"), ("done", "Done")]),
                          "scheduled_date": _f("datetime"), "date_done": _f("datetime"), "origin": _f(),
                          "sale_id": _f(M2O, "sale.order"), "group_id": _f(M2O, "procurement.group"),
                          "picking_type_code": _f(), "backorder_id": _f(M2O, "stock.picking")},
        "stock.move": {"picking_id": _f(M2O, "stock.picking"), "product_id": _f(M2O, "product.product"),
                       "product_uom_qty": _f("float"), "quantity": _f("float"), "product_uom": _f(M2O, "uom.uom"),
                       "state": _f(), "sale_line_id": _f(M2O, "sale.order.line"),
                       "raw_material_production_id": _f(M2O, "mrp.production")},
        "stock.move.line": {"picking_id": _f(M2O, "stock.picking"), "move_id": _f(M2O, "stock.move"),
                            "product_id": _f(M2O, "product.product"), qty_line: _f("float"),
                            "product_uom_id": _f(M2O, "uom.uom"), "lot_id": _f(M2O, "stock.lot"), "lot_name": _f(),
                            "result_package_id": _f(M2O, "stock.quant.package"), "state": _f()},
        "stock.quant.package": {"name": _f(), "shipping_weight": _f("float")},
        "account.move": {"name": _f(), "state": _f("selection", selection=[("posted", "Posted")]),
                         "amount_total": _f("float"), "invoice_date": _f("date"), "currency_id": _f(M2O, "res.currency"),
                         "move_type": _f(), "payment_state": _f("selection", selection=[("not_paid", "Not Paid")])},
        "account.move.line": {"move_id": _f(M2O, "account.move"), "sale_line_ids": _f("many2many", "sale.order.line")},
        "res.users": {"name": _f(), "login": _f()},
    }
    return f


class FakeOdoo:
    def __init__(self, version: str = "17"):
        self.fields = default_fields(version)
        self.data: dict[str, list[dict]] = {m: [] for m in self.fields}
        self.users = {"alice": (7, "pw-alice"), "bob": (8, "pw-bob"), "carol": (9, "pw-carol")}
        self.deny: set[str] = set()
        self.missing: set[str] = set()
        self.calls: list[tuple[str, str]] = []  # (model, method)
        self.hide_so_from: set[int] = set()  # uids that cannot see any sale.order (record rules)

    def add(self, model: str, **rec) -> dict:
        rec.setdefault("id", len(self.data.setdefault(model, [])) + 1)
        self.data[model].append(rec)
        return rec

    def client(self, login: str = "alice") -> OdooReadClient:
        uid, pw = self.users[login]
        return OdooReadClient(FakeTransport(self), "db", login=login, secret=pw, uid=uid)


class FakeTransport:
    name = "fake"

    def __init__(self, odoo: FakeOdoo):
        self.o = odoo

    def authenticate(self, db, login, secret):
        u = self.o.users.get(login)
        if not u or u[1] != secret:
            raise OdooAuthError("bad credentials")
        return u[0]

    def call(self, db, uid, login, secret, model, method, params):
        assert_allowed(method)
        o = self.o
        o.calls.append((model, method))
        if model in o.missing:
            raise OdooMissingModel(model)
        if model not in o.fields:
            raise OdooMissingModel(model)
        if method == "fields_get":
            return o.fields[model]
        if model in o.deny:
            raise OdooAccessError(f"You are not allowed to access '{model}' records.")
        recs = o.data[model]
        if model == "sale.order" and uid in o.hide_so_from:
            recs = []
        if method in ("search", "search_read"):
            pred = compile_domain(params.get("domain") or [])
            rows = [r for r in recs if pred(r)]
            order = params.get("order")
            if order and order.split(",")[0].strip().split(" ")[0] in ("sequence",):
                rows = sorted(rows, key=lambda r: (r.get("sequence", 0), r["id"]))
            if params.get("limit"):
                rows = rows[: params["limit"]]
            if method == "search":
                return [r["id"] for r in rows]
            return [self._out(model, r, params.get("fields")) for r in rows]
        if method == "read":
            by_id = {r["id"]: r for r in recs}
            return [self._out(model, by_id[i], params.get("fields")) for i in params["ids"] if i in by_id]
        if method == "name_get":
            return [[r["id"], self._display(model, r)] for r in recs if r["id"] in params["ids"]]
        if method == "read_group":
            return []
        raise OdooError("unsupported fake method")

    # -- helpers
    def _display(self, model, r):
        if model == "product.product":
            return f"[{r['default_code']}] {r['name']}" if r.get("default_code") else r.get("name", "")
        return r.get("name") or r.get("display_name") or str(r["id"])

    def _out(self, model, r, fields):
        spec = self.o.fields[model]
        out = {"id": r["id"]}
        for f in [x for x in (fields or list(spec)) if x != "id"]:  # id is implicit in real Odoo
            if f not in spec:
                raise OdooError(f"Invalid field '{f}' on model '{model}'")
            v = r.get(f, False)
            t = spec[f]["type"]
            if t == M2O:
                if v:
                    target = next((x for x in self.o.data.get(spec[f]["relation"], []) if x["id"] == v), None)
                    v = [v, self._display(spec[f]["relation"], target) if target else str(v)]
                else:
                    v = False
            out[f] = v
        return out


def compile_domain(domain):
    it = iter(domain)

    def parse():
        tok = next(it)
        if tok == "|":
            a, b = parse(), parse()
            return lambda r: a(r) or b(r)
        if tok == "&":
            a, b = parse(), parse()
            return lambda r: a(r) and b(r)
        if tok == "!":
            a = parse()
            return lambda r: not a(r)
        field, op, value = tok

        def leaf(r):
            v = r.get(field, False)
            if op == "=":
                return v == value
            if op == "!=":
                return v != value
            if op == "in":
                return v in value
            if op == "not in":
                return v not in value
            if op == "ilike":
                return isinstance(v, str) and str(value).lower() in v.lower()
            raise AssertionError(f"fake domain op {op}")
        return leaf

    preds = []
    while True:
        try:
            preds.append(parse())
        except StopIteration:
            break
    return lambda r: all(p(r) for p in preds)


def build_dataset(o: FakeOdoo) -> FakeOdoo:
    """Make-to-order SO S00123 (220-TD, BOM, MO, PO, delivery with lots/packages, invoice) + resale SO S00124."""
    o.add("uom.uom", id=1, name="Units", factor=1.0, category_id=1)
    o.add("uom.uom", id=2, name="Dozens", factor=1 / 12, category_id=1)
    o.add("uom.uom", id=3, name="kg", factor=1.0, category_id=2)
    prods = [
        dict(id=100, default_code="220-TD", name="Thermometer Cut Corner Square 140x140mm, Cedar", barcode="5901234123457",
             weight=0.35, volume=0.0012, uom_id=1, product_tmpl_id=1000, image_1024="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="),
        dict(id=101, default_code="RS-1", name="Resale Gift Box", barcode="123", weight=0, volume=0, uom_id=1, product_tmpl_id=1001),
        dict(id=200, default_code="WOOD-1", name="Cedar Frame", uom_id=1, product_tmpl_id=1200, weight=0.1, volume=0.001),
        dict(id=201, default_code="GLASS-TUBE", name="Glass Tube", uom_id=1, product_tmpl_id=1201, weight=0.02, volume=0.0001),
        dict(id=202, default_code="FLUID-1", name="Safe Fluid", uom_id=3, product_tmpl_id=1202, weight=1, volume=0.001),
    ]
    for p in prods:
        o.add("product.product", **p)
    o.add("product.packaging", id=500, product_id=100, name="Carton of 4", qty=4.0, barcode="CARTON-1")
    o.add("sale.order", id=1, name="S00123", state="sale", date_order="2026-10-01 08:00:00", partner_id=1,
          client_order_ref="PO-77", invoice_ids=[900], procurement_group_id=10, user_id=7)
    o.add("sale.order", id=2, name="S00124", state="sale", partner_id=1, procurement_group_id=11)
    o.add("res.users", id=7, name="Alice Admin", login="alice")
    o.add("sale.order.line", id=11, order_id=1, product_id=100, name="[220-TD] Thermometer", product_uom_qty=10.0,
          product_uom=1, qty_delivered=10.0, qty_invoiced=10.0, price_unit=12.5, sequence=1, display_type=False,
          product_packaging_id=False)
    o.add("sale.order.line", id=12, order_id=2, product_id=101, name="Resale Gift Box", product_uom_qty=5.0,
          product_uom=1, sequence=1, display_type=False)
    o.add("sale.order.line", id=13, order_id=1, product_id=False, name="Notes", sequence=2, display_type="line_note")
    # BOM: 220-TD = 2x frame + 1x glass tube; glass tube = 0.05 kg fluid (sub-assembly, level 2)
    o.add("mrp.bom", id=700, product_tmpl_id=1000, product_id=False, product_qty=1.0, product_uom_id=1, type="normal", sequence=1)
    o.add("mrp.bom", id=710, product_tmpl_id=1201, product_id=False, product_qty=1.0, product_uom_id=1, type="normal", sequence=1)
    o.add("mrp.bom.line", id=701, bom_id=700, product_id=200, product_qty=2.0, product_uom_id=1, sequence=1)
    o.add("mrp.bom.line", id=702, bom_id=700, product_id=201, product_qty=1.0, product_uom_id=1, sequence=2)
    o.add("mrp.bom.line", id=711, bom_id=710, product_id=202, product_qty=0.05, product_uom_id=3, sequence=1)
    o.add("mrp.production", id=800, name="MO/00001", state="confirmed", product_id=100, product_qty=10.0, product_uom_id=1,
          bom_id=700, origin="S00123", procurement_group_id=10)
    o.add("mrp.workorder", id=810, name="Assemble", state="ready", production_id=800, workcenter_id=0)
    o.add("stock.move", id=820, picking_id=False, product_id=200, product_uom_qty=20.0, quantity=20.0, product_uom=1,
          state="done", raw_material_production_id=800)
    o.add("stock.move.line", id=830, picking_id=False, move_id=820, product_id=200, quantity=20.0, product_uom_id=1,
          lot_id=62, state="done")
    o.fields["stock.lot"] = {"name": _f()}
    for lot_id, lot_name in ((60, "LOT-A1"), (61, "LOT-A2"), (62, "LOT-W1")):
        o.add("stock.lot", id=lot_id, name=lot_name)
    o.add("purchase.order", id=950, name="P00001", state="purchase", partner_id=2, origin="S00123")
    o.add("purchase.order.line", id=951, order_id=950, product_id=200, name="Cedar Frame", product_qty=20.0, product_uom=1,
          qty_received=20.0, sale_line_id=False)
    o.add("res.partner", id=1, name="ACME Ltd")
    o.add("res.partner", id=2, name="Cedar Supplier")
    o.fields["res.partner"] = {"name": _f()}
    o.add("stock.picking", id=300, name="WH/OUT/00001", state="assigned", scheduled_date="2026-10-05 09:00:00",
          origin="S00123", sale_id=1, group_id=10, picking_type_code="outgoing")
    o.add("stock.move", id=310, picking_id=300, product_id=100, product_uom_qty=10.0, quantity=10.0, product_uom=1,
          state="assigned", sale_line_id=11)
    lines = [(320, 6.0, 60, 400), (321, 4.0, 61, 401)]
    for mid, q, lot, pkg in lines:
        o.add("stock.move.line", id=mid, picking_id=300, move_id=310, product_id=100, product_uom_id=1, lot_id=lot,
              result_package_id=pkg, state="assigned", **{("quantity" if "quantity" in o.fields["stock.move.line"] else "qty_done"): q})
    o.add("stock.quant.package", id=400, name="PACK0001", shipping_weight=2.5)
    o.add("stock.quant.package", id=401, name="PACK0002", shipping_weight=False)
    o.add("account.move", id=900, name="INV/2026/0001", state="posted", amount_total=125.0, invoice_date="2026-10-06",
          currency_id=3, move_type="out_invoice", payment_state="not_paid")
    o.add("res.currency", id=3, name="USD")
    o.fields["res.currency"] = {"name": _f()}
    return o
