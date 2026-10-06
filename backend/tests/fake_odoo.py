"""In-memory Odoo double. Implements the Transport protocol, evaluates prefix-notation domains,
records every call (so tests can prove only read methods were used) and can deny / hide models."""
from __future__ import annotations

from app.odoo.client import OdooReadClient
from app.odoo.errors import OdooAccessError, OdooAuthError, OdooError, OdooMissingModel
from app.odoo.transports import assert_allowed

M2O = "many2one"


def _f(type_="char", relation=None, selection=None):
    d = {"type": type_, "string": "x"}
    if relation:
        d["relation"] = relation
    if selection:
        d["selection"] = selection
    return d


def default_fields(version: str = "17") -> dict[str, dict]:
    """Odoo 17 field names. For "18" the order-line unit field is `product_uom_id` instead of `product_uom`."""
    uom_field = "product_uom_id" if version >= "18" else "product_uom"
    return {
        "sale.order": {
            "name": _f(), "state": _f("selection", selection=[("draft", "Quotation"), ("sale", "Sales Order")]),
            "date_order": _f("datetime"), "partner_id": _f(M2O, "res.partner"), "partner_shipping_id": _f(M2O, "res.partner"),
            "client_order_ref": _f(), "user_id": _f(M2O, "res.users"), "commitment_date": _f("datetime"),
        },
        "sale.order.line": {
            "order_id": _f(M2O, "sale.order"), "product_id": _f(M2O, "product.product"), "name": _f(),
            "product_uom_qty": _f("float"), uom_field: _f(M2O, "uom.uom"), "qty_delivered": _f("float"),
            "qty_invoiced": _f("float"), "price_unit": _f("float"), "sequence": _f("integer"), "display_type": _f(),
            "product_packaging_id": _f(M2O, "product.packaging"), "product_packaging_qty": _f("float"),
        },
        "product.product": {
            "default_code": _f(), "name": _f(), "barcode": _f(), "image_1024": _f("binary"), "weight": _f("float"),
            "volume": _f("float"), "uom_id": _f(M2O, "uom.uom"), "product_tmpl_id": _f(M2O, "product.template"),
        },
        "product.packaging": {"product_id": _f(M2O, "product.product"), "name": _f(), "qty": _f("float"), "barcode": _f()},
        "uom.uom": {"name": _f(), "factor": _f("float"), "category_id": _f(M2O, "uom.category")},
        "stock.picking": {
            "name": _f(), "partner_id": _f(M2O, "res.partner"), "scheduled_date": _f("datetime"), "origin": _f(),
            "state": _f("selection", selection=[("assigned", "Ready"), ("done", "Done"), ("confirmed", "Waiting")]),
            "sale_id": _f(M2O, "sale.order"), "location_id": _f(M2O, "stock.location"),
        },
        "stock.location": {"name": _f()},
        "stock.move": {"picking_id": _f(M2O, "stock.picking"), "product_id": _f(M2O, "product.product")},
        "res.users": {"name": _f(), "login": _f()},
        "res.partner": {"name": _f()},
    }


class FakeOdoo:
    def __init__(self, version: str = "17"):
        self.version = version
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
        if model in o.missing or model not in o.fields:
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
            if order and order.split(",")[0].strip().split(" ")[0] == "sequence":
                rows = sorted(rows, key=lambda r: (r.get("sequence", 0), r["id"]))
            if order and order.strip() == "id desc":
                rows = sorted(rows, key=lambda r: r["id"], reverse=True)
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
            if spec[f]["type"] == M2O:
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
    """SO S00123: 220-TD (weight, volume, EAN-13, photo, carton of 4) plus a note line.
    SO S00124: a resale line whose product has no weight/volume (Odoo stores 0.0)."""
    o.add("uom.uom", id=1, name="Units", factor=1.0, category_id=1)
    o.add("uom.uom", id=2, name="Dozens", factor=1 / 12, category_id=1)
    o.add("uom.uom", id=3, name="kg", factor=1.0, category_id=2)
    o.add("product.product", id=100, default_code="220-TD", name="Thermometer Cut Corner Square 140x140mm, Cedar",
          barcode="5901234123457", weight=0.35, volume=0.0012, uom_id=1, product_tmpl_id=1000,
          image_1024="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    o.add("product.product", id=101, default_code="RS-1", name="Resale Gift Box", barcode="123", weight=0, volume=0,
          uom_id=1, product_tmpl_id=1001)
    o.add("product.product", id=102, default_code=False, name="Surcharge", barcode=False, weight=0, volume=0, uom_id=1,
          product_tmpl_id=1002)
    o.add("product.packaging", id=500, product_id=100, name="Carton of 4", qty=4.0, barcode="CARTON-1")
    o.add("res.partner", id=1, name="ACME Ltd")
    o.add("res.users", id=7, name="Alice Admin", login="alice")
    o.add("sale.order", id=1, name="S00123", state="sale", date_order="2026-10-01 08:00:00", partner_id=1,
          client_order_ref="PO-77", user_id=7)
    o.add("sale.order", id=2, name="S00124", state="sale", partner_id=1)
    o.add("sale.order", id=3, name="S00125", state="sale", partner_id=1)
    uom = "product_uom_id" if o.version >= "18" else "product_uom"
    o.add("sale.order.line", id=11, order_id=1, product_id=100, name="[220-TD] Thermometer", product_uom_qty=10.0,
          qty_delivered=10.0, qty_invoiced=10.0, price_unit=12.5, sequence=1, display_type=False,
          product_packaging_id=False, **{uom: 1})
    o.add("sale.order.line", id=12, order_id=2, product_id=101, name="Resale Gift Box", product_uom_qty=5.0,
          sequence=1, display_type=False, **{uom: 1})
    o.add("sale.order.line", id=15, order_id=3, product_id=100, name="[220-TD] zero", product_uom_qty=0.0, sequence=1,
          display_type=False, **{uom: 1})  # ordered qty 0
    o.add("sale.order.line", id=16, order_id=3, product_id=101, name="Resale Gift Box", product_uom_qty=3.0, sequence=2,
          display_type=False, **{uom: 1})
    # S00123 has one transfer; PL2/OUT/00032 only quotes it as source document and is NOT linked to the order
    o.add("stock.picking", id=31, name="PL1/OUT/00031", partner_id=1, scheduled_date="2026-10-02 08:00:00",
          origin="S00123", state="done", sale_id=1, location_id=61)
    o.add("stock.picking", id=32, name="PL2/OUT/00032", partner_id=False, scheduled_date="2026-10-03 08:00:00",
          origin="S00123", state="confirmed", sale_id=False, location_id=61)  # not related to the order's Sales Order: must not be listed
    o.add("stock.location", id=61, name="PL1/Output")
    o.add("stock.location", id=62, name="PL2/Output")
    o.add("stock.picking", id=33, name="PL2/OUT/00033", partner_id=1, scheduled_date="2026-10-04 08:00:00",
          origin="S00123", state="done", sale_id=1, location_id=62)  # same order, but leaves from another location
    o.add("stock.move", id=41, picking_id=31, product_id=100)
    o.add("stock.move", id=42, picking_id=32, product_id=102)
    o.add("sale.order.line", id=13, order_id=1, product_id=False, name="Notes", sequence=2, display_type="line_note")
    o.add("sale.order.line", id=14, order_id=1, product_id=102, name="Surcharge", product_uom_qty=1.0, sequence=3,
          display_type=False, **{uom: 1})  # a fee line: product without an item code
    return o
