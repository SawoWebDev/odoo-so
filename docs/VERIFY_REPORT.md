# VERIFY REPORT (Phase 0)

**Status: the field-level report has NOT been generated from your Odoo yet.** It is overwritten by the Phase 0 script:

```bash
docker compose run --rm -v "$PWD/docs:/srv/docs" backend python -m scripts.phase0_verify --so <a real SO number>
```

It asks for an Odoo login and password (never stored), detects the server version and transport, runs `fields_get` on the
three models the app reads (`sale.order`, `sale.order.line`, `product.product`), lists each candidate field as
OK / alternate / **MISSING**, resolves the sample order and prints its header and line counts.

## What has been checked against your real systems so far

| Item | Result |
|---|---|
| Odoo server | `https://erp.sawo.com`, **Odoo 17.0 Enterprise**, database `sawo`, valid TLS certificate (probed without credentials) |
| Odoo login | Works with a normal user password over JSON-RPC (confirmed by a user signing in and loading order S08217: header and 101 lines) |
| Label folder `\\172.16.0.4\Marketing\00 MASTERLIST\01 PRINTING FILES` | Readable from Windows: 2,621 PDFs, named `<item code>.pdf`, nested in `01 SAWO` / `02 CLIENT`; 1,872 distinct names, 595 of them in 2 or more folders; sample codes of S08217 matched (559-BL, 560-BL, 393-BL, 460-D, 735-4SCD-R, SET-TRAD-D...) |
| Your example URL `file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/` | Maps correctly to the mounted folder and saved 11 sample PDFs into the app's database (tested on a local copy that mirrors the share's layout) |
| Docker reading the real share | **Not yet.** The share refuses anonymous access ("permission denied"), so a Windows login must be put in `.env` (README) |

## What the app reads from Odoo

| Model | Fields (first existing candidate is used) |
|---|---|
| `sale.order` | `name`, `state`, `date_order`, `partner_id`, `partner_shipping_id`, `client_order_ref`, `user_id`, `commitment_date` |
| `sale.order.line` | `order_id`, `product_id`, `name`, `product_uom_qty`, `product_uom` / `product_uom_id`, `sequence`, `display_type` |
| `product.product` | `default_code` (the item code), `name` |

A field that does not exist on your version is not requested and never causes an error.

## Open items

| Item | Status |
|---|---|
| JSON-2 (Odoo 19+) identity | Not relevant on Odoo 17; only if you upgrade |
| Error mapping (no access / module missing) | Tested against a mock; confirm with one user who cannot read sale orders |
| Which PDF is the normal one when a code has several | Decide, then set `LABEL_FOLDER_PRIORITY` |
| Whether to stamp the SO number or quantity on the PDF | Not done: PDFs print as designed |
