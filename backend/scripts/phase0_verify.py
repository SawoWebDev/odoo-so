"""Phase 0: connect to the REAL Odoo, detect version/transport, verify every candidate model/field, write the report.

    docker compose run --rm -v "$PWD/docs:/srv/docs" backend python -m scripts.phase0_verify --so S00123

Credentials: ODOO_LOGIN / ODOO_PASSWORD env vars, or you are prompted (the password is never printed or stored).
Read-only: it uses the same OdooReadClient as the application, so it cannot write either.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.odoo.connect import Connector
from app.odoo.errors import OdooError
from app.resolver.fieldmap import LOGICAL
from app.resolver.resolver import SONotFound, SOResolver
from app.resolver.schema import Schema

MANUAL_ITEMS = [
    ("Odoo 19 /json/2 identity", "JSON-2 has no authenticate call, so the user id is read from res.users by login. "
     "Confirm the key owner equals the login, or prefer jsonrpc/xmlrpc where available."),
    ("Error mapping", "AccessError/AccessDenied/missing-model are recognised from JSON-RPC error names, XML-RPC fault codes 3/4 "
     "and JSON-2 HTTP status. Confirm with one user who cannot read sale orders."),
    ("Read-only Odoo group", "Recommended: put users of this tool in a read-only access group (defence in depth)."),
]


def row(*cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def verify(client, settings: Settings, so: str | None, transport: str, server: dict) -> str:
    s = Schema(client)
    out: list[str] = []
    w = out.append
    w("# VERIFY REPORT (Phase 0)\n")
    w(f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} against `{settings.odoo_url}` db `{settings.odoo_db}` "
      f"as uid {client.uid} via **{transport}**.\n")
    w("## 1. Server\n")
    w(f"- Detected version: **{server.get('raw', {}).get('server_version', 'unknown')}** (major {server.get('major')}, source: {server.get('source')})")
    w(f"- Transport used: **{transport}** (configured: `{settings.odoo_transport}`)\n")

    w("## 2. Models and fields\n")
    w("Each logical field is resolved to the first candidate that exists in `fields_get`. `MISSING` means the feature that depends on it "
      "is silently skipped (never guessed). Review every MISSING row.\n")
    missing_models: list[str] = []
    missing_fields = 0
    for model in LOGICAL:
        if not s.has_model(model):
            missing_models.append(model)
            w(f"### `{model}`: NOT AVAILABLE on this instance (module not installed?)\n")
            continue
        w(f"### `{model}`\n")
        w(row("Logical field", "Odoo field", "Type", "Status"))
        w(row("---", "---", "---", "---"))
        fields = s.fields(model)
        for logical, cands in LOGICAL[model].items():
            actual = s.pick(model, logical)
            if actual:
                w(row(logical, f"`{actual}`", fields[actual].get("type"), "OK" + (f" (alternate; tried {cands[0]} first)" if actual != cands[0] else "")))
            else:
                missing_fields += 1
                w(row(logical, f"candidates: {', '.join(cands)}", "-", "**MISSING**"))
        w("")

    if so:
        w(f"## 3. Sample order `{so}`\n")
        try:
            res = SOResolver(client, settings).resolve(so)
            w(row("Group", "Status", "Rows", "Message"))
            w(row("---", "---", "---", "---"))
            for g in res["groups"]:
                w(row(g["label"], g["status"], len(g["rows"]), g["message"]))
            w("\nCompare the number of order lines with the same order in Odoo. Sample header values:\n")
            hdr = res["groups"][0]["rows"][0]["fields"]
            for k, v in hdr.items():
                w(f"- `{k}` = {v['display']!r}")
            w("")
        except SONotFound:
            w(f"Order `{so}` was not found or is not visible to this user.\n")
        except OdooError as e:
            w(f"Resolver failed: {e}\n")

    w("## 4. Items that need a human decision or confirmation\n")
    w(row("Item", "What to check"))
    w(row("---", "---"))
    for a, b in MANUAL_ITEMS:
        w(row(a, b))
    w("\n## 5. Summary\n")
    w(f"- Models not available: {', '.join(missing_models) or 'none'}")
    w(f"- Candidate fields missing: **{missing_fields}**")
    w("- **Gate:** review the MISSING rows and the table in section 4, then confirm the field list before relying on the output.")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--so", help="sample SO number to resolve (any normal sales order)")
    ap.add_argument("--out", default="docs/VERIFY_REPORT.md")
    ns = ap.parse_args()
    settings = get_settings()
    if not settings.odoo_url or not settings.odoo_db:
        print("Set ODOO_URL and ODOO_DB (see .env.example)", file=sys.stderr)
        return 2
    login = os.environ.get("ODOO_LOGIN") or input("Odoo login: ")
    password = os.environ.get("ODOO_PASSWORD") or getpass.getpass("Password or API key: ")
    conn = Connector(settings)
    server = conn.server_info()
    print(f"Server version: {server.get('raw', {}).get('server_version')} (major {server.get('major')})")
    try:
        client = conn.connect(login, password)
    except OdooError as e:
        print(f"Cannot connect: {e}", file=sys.stderr)
        return 1
    print(f"Connected via {client.transport_name} as uid {client.uid}")
    report = verify(client, settings, ns.so, client.transport_name, server)
    os.makedirs(os.path.dirname(ns.out) or ".", exist_ok=True)
    with open(ns.out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Wrote {ns.out}. MISSING rows: {report.count('**MISSING**')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
