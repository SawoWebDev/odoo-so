"""Field catalog (guideline section 6): the contract between the results screen and the templates.

`key` is the stable id; `aliases` are the short placeholder names templates may use (e.g. {{so_number}}).
`source_path` documents where the value comes from in the resolver output: `<group>.<row field key>`.
Computed and print-time keys (group `calc` / `print`) are produced at render time, not selected from Odoo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import FieldCatalog

GROUP_LABELS = {
    "header": "Order header",
    "lines": "Order lines",
    "products": "Product master data",
    "bom": "Materials / BOM",
    "mrp": "Manufacturing",
    "purchasing": "Purchasing",
    "delivery": "Delivery",
    "invoicing": "Invoicing",
    "calc": "Calculated (PCS / KGS / CBM)",
    "print": "Print-time options",
}
GROUP_ORDER = list(GROUP_LABELS)


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    group: str
    type: str = "text"  # text | number | date | image | barcode | bool
    scope: str = "so"  # so | line | lot | package
    selectable: bool = True
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def source_path(self) -> str:
        return f"{self.group}.{self.key}" if self.selectable else f"computed.{self.key}"


def _e(key, label, group, type="text", scope="line", selectable=True, aliases=()):
    return Entry(key, label, group, type, scope, selectable, tuple(aliases))


CATALOG: list[Entry] = [
    # 1 Order header (scope: so)
    _e("header.name", "SO number", "header", scope="so", aliases=["so_number", "so"]),
    _e("header.state", "Status", "header", scope="so"),
    _e("header.date_order", "Order date", "header", "date", "so", aliases=["order_date"]),
    _e("header.customer", "Customer", "header", scope="so", aliases=["customer"]),
    _e("header.shipping_address", "Delivery address", "header", scope="so"),
    _e("header.customer_ref", "Customer reference", "header", scope="so", aliases=["customer_po", "po_number"]),
    _e("header.salesperson", "Salesperson", "header", scope="so"),
    _e("header.commitment_date", "Delivery date", "header", "date", "so"),
    # 2 Order lines (scope: line)
    _e("line.product.code", "Item code", "lines", aliases=["item_code", "code"]),
    _e("line.product.name", "Product name", "lines", aliases=["description", "product_name"]),
    _e("line.description", "Line description", "lines"),
    _e("line.qty", "Ordered qty", "lines", "number"),
    _e("line.uom", "Unit of measure", "lines"),
    _e("line.qty_delivered", "Delivered qty", "lines", "number"),
    _e("line.qty_invoiced", "Invoiced qty", "lines", "number"),
    _e("line.price_unit", "Unit price", "lines", "number"),
    _e("line.product.barcode", "Product barcode", "lines", "barcode", aliases=["barcode", "ean"]),
    _e("line.product.image", "Product image", "lines", "image", aliases=["photo", "product_image"]),
    _e("line.product.weight", "Unit weight (kg)", "lines", "number"),
    _e("line.product.volume", "Unit volume (m3)", "lines", "number"),
    # 3 Product master data (scope: line)
    _e("product.code", "Internal reference", "products"),
    _e("product.name", "Name", "products"),
    _e("product.barcode", "Barcode", "products", "barcode"),
    _e("product.image", "Image", "products", "image"),
    _e("product.weight", "Weight (kg)", "products", "number"),
    _e("product.volume", "Volume (m3)", "products", "number"),
    _e("product.uom", "Product UoM", "products"),
    _e("product.packaging", "Packaging", "products"),
    _e("product.packaging_qty", "Packaging qty", "products", "number"),
    _e("product.packaging_barcode", "Packaging barcode", "products", "barcode"),
    # 4 BOM
    _e("bom.component.code", "Component code", "bom"),
    _e("bom.component.name", "Component", "bom"),
    _e("bom.qty", "Qty per BOM batch", "bom", "number"),
    _e("bom.uom", "BOM UoM", "bom"),
    _e("bom.qty_total", "Qty needed for order", "bom", "number"),
    _e("bom.level", "BOM level", "bom", "number"),
    _e("bom.parent", "Parent product", "bom"),
    # 5 Manufacturing
    _e("mrp.name", "MO", "mrp"),
    _e("mrp.state", "MO status", "mrp"),
    _e("mrp.product", "MO product", "mrp"),
    _e("mrp.qty", "MO qty", "mrp", "number"),
    _e("mrp.uom", "MO UoM", "mrp"),
    _e("mrp.date_start", "MO start", "mrp", "date"),
    _e("mrp.bom", "MO BOM", "mrp"),
    _e("mrp.wo.name", "Work order", "mrp"),
    _e("mrp.wo.state", "Work order status", "mrp"),
    _e("mrp.wo.workcenter", "Work center", "mrp"),
    _e("mrp.move.product", "Consumed material", "mrp"),
    _e("mrp.move.qty", "Consumed qty", "mrp", "number"),
    _e("mrp.move.uom", "Consumed UoM", "mrp"),
    _e("mrp.move.lot", "Consumed lot", "mrp", scope="lot"),
    # 6 Purchasing
    _e("purchase.name", "PO", "purchasing"),
    _e("purchase.vendor", "Vendor", "purchasing"),
    _e("purchase.state", "PO status", "purchasing"),
    _e("purchase.product", "Product", "purchasing"),
    _e("purchase.qty", "Ordered qty", "purchasing", "number"),
    _e("purchase.qty_received", "Received qty", "purchasing", "number"),
    _e("purchase.uom", "UoM", "purchasing"),
    _e("purchase.date_planned", "Expected", "purchasing", "date"),
    # 7 Delivery
    _e("delivery.picking", "Transfer", "delivery"),
    _e("delivery.state", "Transfer status", "delivery"),
    _e("delivery.scheduled", "Scheduled", "delivery", "date"),
    _e("delivery.done", "Done on", "delivery", "date"),
    _e("delivery.kind", "Kind (delivery / return)", "delivery"),
    _e("delivery.backorder_of", "Backorder of", "delivery"),
    _e("delivery.product", "Product", "delivery"),
    _e("delivery.qty", "Qty", "delivery", "number"),
    _e("delivery.uom", "UoM", "delivery"),
    _e("delivery.lot", "Lot / serial", "delivery", scope="lot", aliases=["lot"]),
    _e("delivery.package", "Package", "delivery", scope="package", aliases=["package"]),
    # 8 Invoicing
    _e("invoice.name", "Invoice", "invoicing"),
    _e("invoice.state", "Status", "invoicing"),
    _e("invoice.amount_total", "Total", "invoicing", "number"),
    _e("invoice.currency", "Currency", "invoicing"),
    _e("invoice.date", "Invoice date", "invoicing", "date"),
    _e("invoice.payment_state", "Payment status", "invoicing"),
    # Computed (never selected from Odoo, always available to templates)
    _e("calc.pcs", "PCS", "calc", "number", "line", False, ["pcs"]),
    _e("calc.kgs", "KGS", "calc", "number", "line", False, ["kgs"]),
    _e("calc.cbm", "CBM", "calc", "number", "line", False, ["cbm"]),
    # Print-time toggles. Meaning of LOGO and PEFC is an OPEN business decision (guideline 18): plain toggles only.
    _e("print.logo", "LOGO YES/NO", "print", "bool", "so", False, ["logo_yes", "logo"]),
    _e("print.pefc", "PEFC mark", "print", "bool", "so", False, ["pefc"]),
    _e("print.date", "Print date", "print", "date", "so", False, ["today", "print_date"]),
    _e("print.seq", "Label n of N", "print", "text", "so", False, ["label_seq"]),
]

BY_KEY: dict[str, Entry] = {e.key: e for e in CATALOG}
ALIAS_TO_KEY: dict[str, str] = {a: e.key for e in CATALOG for a in e.aliases}
TYPE_BY_KEY: dict[str, str] = {e.key: e.type for e in CATALOG}


def resolve_placeholder(name: str) -> str | None:
    """Placeholder -> catalog key. Accepts the key itself or one of its aliases."""
    if name in BY_KEY:
        return name
    return ALIAS_TO_KEY.get(name)


def seed_catalog(db: Session) -> None:
    """Upsert the code-defined catalog into the DB (so it can be queried and joined with mappings)."""
    existing = {r.key: r for r in db.query(FieldCatalog).all()}
    for e in CATALOG:
        row = existing.get(e.key) or FieldCatalog(key=e.key)
        row.label, row.group, row.source_path = e.label, e.group, e.source_path
        row.type, row.scope, row.selectable, row.aliases = e.type, e.scope, e.selectable, list(e.aliases)
        db.add(row)
    for key, row in existing.items():
        if key not in BY_KEY:
            db.delete(row)
    db.commit()


def catalog_json() -> list[dict]:
    return [
        {"key": e.key, "label": e.label, "group": e.group, "group_label": GROUP_LABELS[e.group],
         "source_path": e.source_path, "type": e.type, "scope": e.scope, "selectable": e.selectable,
         "aliases": list(e.aliases)}
        for e in CATALOG
    ]
