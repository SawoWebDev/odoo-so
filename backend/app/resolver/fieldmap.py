"""Logical field -> candidate Odoo field names.

Every entry is a CANDIDATE that must be verified (guideline rule 4). At runtime the first candidate that
exists in `fields_get` for the connected instance is used; a logical field with no existing candidate is
simply not requested. `scripts/phase0_verify.py` reports the resolution for the real instance.

Alternates cover known renames between Odoo versions (for example product_uom -> product_uom_id,
qty_done -> quantity, date_planned_start -> date_start).
"""
from __future__ import annotations

LOGICAL: dict[str, dict[str, list[str]]] = {
    "sale.order": {
        "name": ["name"],
        "state": ["state"],
        "date_order": ["date_order"],
        "partner": ["partner_id"],
        "shipping": ["partner_shipping_id"],
        "client_ref": ["client_order_ref"],
        "salesperson": ["user_id"],
        "commitment": ["commitment_date"],
        "invoices": ["invoice_ids"],
        "procurement_group": ["procurement_group_id"],
    },
    "sale.order.line": {
        "order": ["order_id"],
        "product": ["product_id"],
        "name": ["name"],
        "qty": ["product_uom_qty"],
        "uom": ["product_uom", "product_uom_id"],
        "qty_delivered": ["qty_delivered"],
        "qty_invoiced": ["qty_invoiced"],
        "price_unit": ["price_unit"],
        "sequence": ["sequence"],
        "display_type": ["display_type"],
        "packaging": ["product_packaging_id"],
        "packaging_qty": ["product_packaging_qty"],
    },
    "product.product": {
        "code": ["default_code"],
        "name": ["name"],
        "barcode": ["barcode"],
        "image": ["image_1024", "image_512", "image_1920"],
        "weight": ["weight"],
        "volume": ["volume"],
        "uom": ["uom_id"],
        "tmpl": ["product_tmpl_id"],
    },
    "product.packaging": {
        "product": ["product_id"],
        "name": ["name"],
        "qty": ["qty"],
        "barcode": ["barcode"],
    },
    "uom.uom": {
        "name": ["name"],
        "factor": ["factor"],
        "category": ["category_id"],
    },
    "mrp.bom": {
        "tmpl": ["product_tmpl_id"],
        "product": ["product_id"],
        "qty": ["product_qty"],
        "uom": ["product_uom_id"],
        "type": ["type"],
        "code": ["code"],
        "sequence": ["sequence"],
    },
    "mrp.bom.line": {
        "bom": ["bom_id"],
        "product": ["product_id"],
        "qty": ["product_qty"],
        "uom": ["product_uom_id"],
        "sequence": ["sequence"],
    },
    "mrp.production": {
        "name": ["name"],
        "state": ["state"],
        "product": ["product_id"],
        "qty": ["product_qty"],
        "uom": ["product_uom_id"],
        "date_start": ["date_start", "date_planned_start"],
        "bom": ["bom_id"],
        "origin": ["origin"],
        "procurement_group": ["procurement_group_id"],
        "qty_produced": ["qty_produced"],
    },
    "mrp.workorder": {
        "name": ["name"],
        "state": ["state"],
        "production": ["production_id"],
        "workcenter": ["workcenter_id"],
        "duration_expected": ["duration_expected"],
        "duration": ["duration"],
    },
    "purchase.order": {
        "name": ["name"],
        "state": ["state"],
        "partner": ["partner_id"],
        "origin": ["origin"],
        "date_planned": ["date_planned"],
    },
    "purchase.order.line": {
        "order": ["order_id"],
        "product": ["product_id"],
        "name": ["name"],
        "qty": ["product_qty"],
        "uom": ["product_uom", "product_uom_id"],
        "qty_received": ["qty_received"],
        "date_planned": ["date_planned"],
        "sale_line": ["sale_line_id"],
    },
    "stock.picking": {
        "name": ["name"],
        "state": ["state"],
        "scheduled": ["scheduled_date"],
        "done": ["date_done"],
        "origin": ["origin"],
        "sale": ["sale_id"],
        "group": ["group_id"],
        "type_code": ["picking_type_code"],
        "backorder": ["backorder_id"],
    },
    "stock.move": {
        "picking": ["picking_id"],
        "product": ["product_id"],
        "demand": ["product_uom_qty"],
        "done_qty": ["quantity", "quantity_done"],
        "uom": ["product_uom"],
        "state": ["state"],
        "sale_line": ["sale_line_id"],
        "raw_for": ["raw_material_production_id"],
    },
    "stock.move.line": {
        "picking": ["picking_id"],
        "move": ["move_id"],
        "product": ["product_id"],
        "done_qty": ["quantity", "qty_done"],
        "uom": ["product_uom_id"],
        "lot": ["lot_id"],
        "lot_name": ["lot_name"],
        "package": ["result_package_id"],
        "state": ["state"],
    },
    "stock.quant.package": {
        "name": ["name"],
        "weight": ["shipping_weight", "weight"],
    },
    "account.move": {
        "name": ["name"],
        "state": ["state"],
        "amount_total": ["amount_total"],
        "date": ["invoice_date"],
        "currency": ["currency_id"],
        "type": ["move_type"],
        "payment_state": ["payment_state"],
    },
    "account.move.line": {
        "move": ["move_id"],
        "sale_lines": ["sale_line_ids"],
    },
}

# Link paths that Phase 0 must probe because they differ between versions and flows (guideline 5.1).
LINK_PROBES: list[tuple[str, str, str]] = [
    ("SO -> pickings", "stock.picking", "sale"),
    ("SO -> pickings (procurement group)", "stock.picking", "group"),
    ("SO -> manufacturing orders (origin)", "mrp.production", "origin"),
    ("SO -> manufacturing orders (procurement group)", "mrp.production", "procurement_group"),
    ("SO line -> purchase line", "purchase.order.line", "sale_line"),
    ("SO -> invoices", "sale.order", "invoices"),
    ("Invoice line -> SO line", "account.move.line", "sale_lines"),
    ("Delivered move -> SO line", "stock.move", "sale_line"),
]

# Fields too heavy to ship to the browser; kept server-side only.
IMAGE_LOGICALS = {("product.product", "image")}
