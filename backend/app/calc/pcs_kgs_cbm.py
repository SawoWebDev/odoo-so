"""PCS / KGS / CBM calculation (guideline section 9).

Modes: 1 order-line totals, 2 per carton, 3 per delivery package, 4 editable override (base = 1 or 2).
Rules enforced here:
  * a missing weight/volume yields None plus a visible warning, never a silent zero;
  * quantities in different UoMs are never added together or mixed (converted within a category, else flagged);
  * overrides are kept next to the calculated value and only ever affect the label and the print log.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MODES = {1: "Order line totals", 2: "Per carton", 3: "Per delivery package", 4: "Editable override"}


@dataclass
class Calc:
    mode: int
    pcs: float | None = None
    kgs: float | None = None
    cbm: float | None = None
    uom: str = ""
    warnings: list[dict] = field(default_factory=list)

    def values(self) -> dict:
        return {"pcs": self.pcs, "kgs": self.kgs, "cbm": self.cbm}

    def warn(self, code: str, message: str, field_: str = "") -> None:
        self.warnings.append({"code": code, "message": message, "field": field_})


def convert_qty(qty: float | None, src: dict | None, dst: dict | None) -> tuple[float | None, str | None]:
    """Convert qty between Odoo UoMs of the same category (reference qty = qty / factor). Returns (qty, problem)."""
    if qty is None:
        return None, None
    if not src or not dst or src.get("id") == dst.get("id") or (src.get("id") is None and dst.get("id") is None):
        return qty, None
    if src.get("category") is None or src.get("category") != dst.get("category"):
        return None, f"Unit '{src.get('name')}' cannot be converted to '{dst.get('name')}' (different categories)"
    if not src.get("factor") or not dst.get("factor"):
        return None, f"No conversion factor between '{src.get('name')}' and '{dst.get('name')}'"
    return qty / src["factor"] * dst["factor"], None


def _unit_totals(c: Calc, pcs_in_product_uom: float | None, meta: dict) -> None:
    w, v = meta.get("unit_weight_kg"), meta.get("unit_volume_m3")
    if pcs_in_product_uom is None:
        return
    if w is None:
        c.warn("missing_weight", "Weight is missing on the product in Odoo - KGS cannot be calculated.", "kgs")
    else:
        c.kgs = round(pcs_in_product_uom * w, 3)
    if v is None:
        c.warn("missing_volume", "Volume is missing on the product in Odoo - CBM cannot be calculated.", "cbm")
    else:
        c.cbm = round(pcs_in_product_uom * v, 4)


def calculate(mode: int, line_meta: dict | None, delivery_metas: list[dict] | None = None, *,
              override_base: int = 1) -> Calc:
    """`line_meta` is the resolver's calc meta for the order line; `delivery_metas` the delivery rows of the label."""
    eff = override_base if mode == 4 else mode
    c = Calc(mode=mode)
    if eff == 3:
        return _mode3(c, line_meta, delivery_metas or [])
    if not line_meta:
        c.warn("no_line", "No order line is linked to this label, so PCS/KGS/CBM cannot be calculated.")
        return c
    uom = line_meta.get("uom") or {}
    c.uom = uom.get("name", "")
    if eff == 2:
        return _mode2(c, line_meta)
    # mode 1: order line totals
    qty = line_meta.get("qty")
    c.pcs = qty
    if qty is None:
        c.warn("missing_qty", "The order line has no quantity.", "pcs")
        return c
    in_prod, problem = convert_qty(qty, uom, line_meta.get("product_uom"))
    if problem:
        c.warn("uom_mismatch", problem + " - KGS/CBM left empty.", "kgs")
        return c
    _unit_totals(c, in_prod, line_meta)
    return c


def _mode2(c: Calc, meta: dict) -> Calc:
    pks = [p for p in meta.get("packagings", []) if p.get("qty")]
    chosen = next((p for p in pks if p["id"] == meta.get("line_packaging_id")), None)
    if chosen is None and pks:
        chosen = max(pks, key=lambda p: p["qty"])
    if chosen is None:
        c.warn("no_packaging", "No packaging (carton) is defined for this product in Odoo.", "pcs")
        return c
    c.pcs = chosen["qty"]  # packaging qty is expressed in the product's UoM
    c.uom = (meta.get("product_uom") or {}).get("name", c.uom)
    _unit_totals(c, chosen["qty"], meta)
    return c


def _mode3(c: Calc, line_meta: dict | None, rows: list[dict]) -> Calc:
    rows = [r for r in rows if r.get("qty") is not None]
    if not rows:
        c.warn("no_delivery", "No delivery quantity/package is selected for this label.", "pcs")
        return c
    uoms = {r.get("uom") for r in rows}
    if len(uoms) > 1:
        c.warn("uom_mixed", f"Selected delivery rows use different units ({', '.join(sorted(map(str, uoms)))}); not summed.", "pcs")
        return c
    c.uom = rows[0].get("uom") or ""
    c.pcs = sum(r["qty"] for r in rows)
    pkg_weights = {r.get("package_id"): r.get("package_weight_kg") for r in rows if r.get("package_id")}
    if len(pkg_weights) == 1 and next(iter(pkg_weights.values())):
        c.kgs = round(next(iter(pkg_weights.values())), 3)  # actual package weight recorded in Odoo
        _, v = None, (line_meta or {}).get("unit_volume_m3")
        if v is None:
            c.warn("missing_volume", "Volume is missing on the product in Odoo - CBM cannot be calculated.", "cbm")
        else:
            c.cbm = round(c.pcs * v, 4)
        return c
    if not line_meta:
        c.warn("no_line", "No order line linked: weight and volume cannot be derived from the product.", "kgs")
        return c
    _unit_totals(c, c.pcs, line_meta)
    return c


def parse_override(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(str(v).replace(",", "."))
    except ValueError:
        raise ValueError(f"'{v}' is not a number")
    if f < 0:
        raise ValueError("Overrides cannot be negative")
    return f


def apply_overrides(calc: Calc, overrides: dict | None) -> dict:
    """Return {'calculated', 'overrides', 'final', 'warnings'}; warnings for overridden fields are cleared."""
    ov = {k: parse_override(v) for k, v in (overrides or {}).items() if k in ("pcs", "kgs", "cbm")}
    ov = {k: v for k, v in ov.items() if v is not None}
    final = {**calc.values(), **ov}
    warnings = [w for w in calc.warnings if w.get("field") not in ov]
    return {"calculated": calc.values(), "overrides": ov, "final": final, "warnings": warnings,
            "mode": calc.mode, "uom": calc.uom}


def fmt_value(key: str, v: float | None) -> str:
    if v is None:
        return ""  # blank, never "0": the warning/override flow forces a conscious decision
    places = {"pcs": 3, "kgs": 3, "cbm": 4}[key]
    s = f"{v:.{places}f}".rstrip("0").rstrip(".")
    return s or "0"
