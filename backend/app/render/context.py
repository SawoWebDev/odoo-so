"""Selection + resolver output -> one value-set per label (guideline 11, steps 3-6).

A selection is {"items": [{"row": "<row_id>", "keys": ["<catalog key>", ...]}, ...]}.
Only ticked keys of ticked rows are exposed to the template; computed (PCS/KGS/CBM) and print-time keys
are always available. Labels are produced per template scope: so | line | lot | package.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..calc.pcs_kgs_cbm import apply_overrides, calculate, fmt_value
from ..catalog.catalog import BY_KEY, resolve_placeholder


class SelectionError(ValueError):
    pass


@dataclass
class Label:
    key: str  # row id of the line / lot / package (or "so")
    values: dict[str, dict]  # catalog key -> {display, raw, type}
    calc: dict  # apply_overrides() output
    line_id: int | None = None
    title: str = ""


def _index_rows(resolved: dict) -> dict[str, dict]:
    return {r["row_id"]: r for g in resolved["groups"] for r in g["rows"]}


def _norm_selection(selection: dict, rows: dict[str, dict]) -> list[tuple[dict, list[str]]]:
    items = []
    for it in (selection or {}).get("items", []):
        row = rows.get(it.get("row"))
        if not row:
            continue
        keys = [k for k in it.get("keys", []) if k in row["fields"]]
        if keys:
            items.append((row, keys))
    return items


def _collect(items: list[tuple[dict, list[str]]]) -> dict[str, dict]:
    values: dict[str, dict] = {}
    for row, keys in items:
        for k in keys:
            values.setdefault(k, row["fields"][k])  # first selected wins
    return values


def build_labels(resolved: dict, selection: dict, scope: str, *, calc_mode: int = 1, override_base: int = 1,
                 overrides: dict | None = None, toggles: dict | None = None) -> list[Label]:
    rows = _index_rows(resolved)
    items = _norm_selection(selection, rows)
    if not items:
        raise SelectionError("Nothing is selected. Tick at least one field or row.")
    overrides = overrides or {}
    labels: list[Label] = []

    def meta_for_line(line_id):
        r = rows.get(f"lines:{line_id}") if line_id else None
        return r["meta"] if r else None

    if scope == "so":
        values = _collect(items)
        line_ids = list(dict.fromkeys(r["line_id"] for r, _ in items if r["line_id"]))
        meta = meta_for_line(line_ids[0]) if line_ids else None
        deliv = [r["meta"] for r, _ in items if r["row_id"].startswith("delivery:")]
        labels.append(_label("so", values, meta, deliv, calc_mode, override_base, overrides, line_ids[0] if line_ids else None,
                             resolved["so"]))
    elif scope == "line":
        line_ids = list(dict.fromkeys(r["line_id"] for r, _ in items if r["line_id"]))
        if not line_ids:
            raise SelectionError("This template prints one label per order line: tick at least one order line row.")
        glob = [(r, k) for r, k in items if not r["line_id"]]
        for lid in line_ids:
            mine = [(r, k) for r, k in items if r["line_id"] == lid]
            deliv = [r["meta"] for r, _ in mine if r["row_id"].startswith("delivery:")]
            ln = rows.get(f"lines:{lid}")
            labels.append(_label(f"lines:{lid}", _collect(mine + glob), meta_for_line(lid), deliv, calc_mode,
                                 override_base, overrides, lid, ln["label"] if ln else str(lid)))
    elif scope in ("lot", "package"):
        def eligible(r: dict) -> bool:
            if not r["row_id"].startswith("delivery:"):
                return False
            if scope == "lot":
                return bool(r["fields"].get("delivery.lot", {}).get("display"))
            return bool(r["meta"].get("package_id"))

        sel = [(r, k) for r, k in items if eligible(r)]
        if not sel:
            raise SelectionError(f"This template prints one label per {scope}: tick at least one delivery row with a {scope}.")
        glob = [(r, k) for r, k in items if not r["line_id"]]
        groups: dict[str, list[tuple[dict, list[str]]]] = {}
        for r, k in sel:
            gk = r["row_id"] if scope == "lot" else f"pkg:{r['meta'].get('package_id')}"
            groups.setdefault(gk, []).append((r, k))
        for gk, members in groups.items():
            lid = members[0][0]["line_id"]
            same_line = [(r, k) for r, k in items if lid and r["line_id"] == lid and not r["row_id"].startswith("delivery:")]
            labels.append(_label(gk, _collect(members + same_line + glob), meta_for_line(lid),
                                 [r["meta"] for r, _ in members],
                                 3 if calc_mode == 1 else calc_mode,  # lot/package labels count what was delivered
                                 override_base, overrides, lid, members[0][0]["label"]))
    else:
        raise SelectionError(f"Unknown template scope {scope!r}")

    n = len(labels)
    for i, lab in enumerate(labels, 1):
        _add_computed(lab, toggles or {}, i, n)
    return labels


def _label(key, values, line_meta, deliv_metas, mode, base, overrides, line_id, title) -> Label:
    c = calculate(mode, line_meta, deliv_metas, override_base=base)
    ov = {**(overrides.get("*") or {}), **(overrides.get(key) or {})}
    return Label(key=key, values=values, calc=apply_overrides(c, ov), line_id=line_id, title=title)


def _add_computed(lab: Label, toggles: dict, i: int, n: int) -> None:
    for k in ("pcs", "kgs", "cbm"):
        v = lab.calc["final"][k]
        lab.values[f"calc.{k}"] = {"display": fmt_value(k, v), "raw": v, "type": "number"}
    lab.values["print.logo"] = {"display": "YES" if toggles.get("logo") else "NO", "raw": bool(toggles.get("logo")), "type": "bool"}
    lab.values["print.pefc"] = {"display": "YES" if toggles.get("pefc") else "NO", "raw": bool(toggles.get("pefc")), "type": "bool"}
    lab.values["print.date"] = {"display": toggles.get("date") or date.today().isoformat(), "raw": None, "type": "date"}
    lab.values["print.seq"] = {"display": f"{i}/{n}", "raw": None, "type": "text"}


def placeholder_values(label: Label, mappings: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    """Template placeholders -> values for this label, plus 'missing' warnings (visible, never silent)."""
    out: dict[str, dict] = {}
    warnings: list[dict] = []
    for m in mappings:
        key = m.get("catalog_key") or resolve_placeholder(m["placeholder"])
        val = label.values.get(key) if key else None
        if val is None:
            val = {"display": "", "raw": None, "type": BY_KEY[key].type if key in BY_KEY else "text"}
        out[m["placeholder"]] = {**val, "overflow": m.get("overflow_rule", "wrap")}
        empty = val["type"] != "bool" and (val.get("raw") in (None, "", False)) and not val.get("display")
        if empty and not m.get("optional"):
            reason = "not selected" if key and key not in label.values else "no value in Odoo"
            warnings.append({"code": "missing_value", "placeholder": m["placeholder"], "catalog_key": key,
                             "message": f"'{m['placeholder']}' is empty ({reason})", "label": label.key})
    return out, warnings
