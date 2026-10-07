"""Attach the matching label PDFs (from the saved list) to each order line of a resolved SO. Kept out of the Odoo
resolver on purpose: the resolver only talks to Odoo, this only looks at the saved list."""
from __future__ import annotations

import copy

from .index import LabelIndex, norm


def enrich(resolved: dict, index: LabelIndex, requests: dict | None = None, all_requests: dict | None = None) -> dict:
    """`requests`: open label requests by item code (upper case) -> {id, created_at, requested_by_name}."""
    out = copy.deepcopy(resolved)  # the cached Odoo result is shared; never mutate it
    for g in out["groups"]:
        if g["id"] != "lines":
            continue
        for r in g["rows"]:
            code = r["fields"]["line.product.code"]["raw"] or ""
            cands = index.candidates(code)
            r["pdf"] = {"code": code, "files": [e.public() for e in cands],
                        "selected": cands[0].id if cands else None, "request": None,
                        "file_count": len(cands), "requests": (all_requests or {}).get(norm(code), [])}
            if not cands:
                asked = (requests or {}).get(norm(code))
                r["pdf"]["request"] = asked
                gone = index.missing(code)
                reason = (f"The label file for {code} was deleted or renamed (last saved as {gone[0].rel_path}). "
                          "Check the Label files tab." if gone else f"No label PDF found for item code {code}")
                r["disabled_reason"] = f"{reason}; {r['disabled_reason']}" if r["disabled"] else reason
                r["disabled"], r["disabled_kind"] = True, "no_label"  # shown in the warning colour
    return out
