# VERIFY REPORT (Phase 0)

**Status: NOT YET RUN against a real Odoo instance.**

This file is overwritten by the Phase 0 script. Nothing in this repository has been checked against your real Odoo
yet: the application was built and tested against an in-memory Odoo double and a mock Odoo HTTP server that speak the
protocols as documented. Every `[VERIFY]` item in the guideline stays open until you run:

```bash
cp .env.example .env            # fill ODOO_URL, ODOO_DB, APP_SECRET_KEY
docker compose run --rm -v "$PWD/docs:/srv/docs" backend python -m scripts.phase0_verify --so S00123
```

(Use a real, ideally make-to-order, sales order number.) The script asks for an Odoo login and password / API key,
detects the server version and transport, runs `fields_get` on every model in guideline section 5, lists each candidate
field as OK / alternate / **MISSING**, probes the SO link paths, resolves your sample order and prints the group counts.

## What the application already does to stay safe before verification

| [VERIFY] item | Behaviour until verified |
|---|---|
| Field names per Odoo version | Candidates are intersected with `fields_get` at runtime. A field that does not exist is not requested; it never causes an error and is never guessed. Known renames are handled (`product_uom`/`product_uom_id`, `qty_done`/`quantity`, `date_planned_start`/`date_start`). |
| API transport | `ODOO_TRANSPORT=auto` probes the server (version, then JSON-RPC, XML-RPC, JSON-2). |
| SO to MO / PO / picking / invoice links | Several paths are unioned (procurement group, origin, `sale_id`, `sale_line_id`, invoice lines). Phase 0 reports which of them exist. |
| Weight / volume units | Assumed kg and m3; `WEIGHT_FACTOR_TO_KG` / `VOLUME_FACTOR_TO_M3` convert if your instance differs. A value of 0 is treated as **missing**, never printed as zero. |
| JSON-2 (Odoo 19+) identity | JSON-2 has no authenticate call. The user id is read from `res.users` by login (see section 5 of the generated report). |

## Open business decisions (guideline section 18)

| Decision | Current behaviour |
|---|---|
| Meaning of LOGO YES/NO | Plain print-time toggle. No meaning assumed. |
| PEFC mark on every product or only certified ones | Plain print-time toggle. No rule assumed. |
| Label scope (per carton or per line) | Template setting `scope`; PCS/KGS/CBM mode is chosen at print time. |
| Printer type | A4 sheet PDF out of the box; ZPL supported for thermal printers. |
