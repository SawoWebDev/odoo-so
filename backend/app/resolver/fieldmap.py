"""Logical field -> candidate Odoo field names.

Every entry is a CANDIDATE that must be verified (guideline rule 4). At runtime the first candidate that
exists in `fields_get` for the connected instance is used; a logical field with no existing candidate is
simply not requested. `scripts/phase0_verify.py` reports the resolution for the real instance.

Alternates cover known renames between Odoo versions (for example product_uom -> product_uom_id).
Only what the app shows is read: the order header, and per order line the product code, name, quantity and unit.
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
    },
    "sale.order.line": {
        "order": ["order_id"],
        "product": ["product_id"],
        "name": ["name"],
        "qty": ["product_uom_qty"],
        "uom": ["product_uom", "product_uom_id"],
        "sequence": ["sequence"],
        "display_type": ["display_type"],
    },
    "product.product": {
        "code": ["default_code"],
        "name": ["name"],
    },
}
