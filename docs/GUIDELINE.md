# Odoo SO Traceability and Sticker Label System
## Master Build Prompt and Implementation Guideline

How to use this file:
- **Part A** is the master prompt. Paste it as the first message to a coding agent (Claude Code or similar), in an empty project folder.
- **Part B** is the guideline the agent builds from. Give the agent this whole file, or keep it in the repo as `docs/GUIDELINE.md`.
- Items marked **[VERIFY]** depend on your Odoo version and configuration. The agent must confirm them against the real Odoo instance and must not guess.

---

# PART A. MASTER PROMPT (paste this)

```
You are a senior full-stack engineer. Build the "SO Sticker System": a web
application that, given an Odoo Sales Order (SO) number, collects every related
record from Odoo, shows it grouped by process stage, lets the user tick which
fields to use, and prints them onto a sticker template chosen from an uploaded
template library.

Read docs/GUIDELINE.md fully before writing code. It is the source of truth.
Work in the phases defined there. Finish and test one phase before starting the
next, and stop at each phase gate to summarise what works and what is unverified.

HARD RULES (never break these)
1. READ-ONLY toward Odoo. The Odoo connector may only call read methods:
   search, search_read, read, fields_get, name_get/display_name, read_group,
   and authenticate. It must NOT expose create, write, unlink, or any
   workflow/button method. Enforce this with an allow-list inside the connector
   and a unit test that fails if any other method name can be called.
2. Users sign in with their existing Odoo credentials. Odoo decides what each
   user may see. Do not copy Odoo users or build a permission model for Odoo
   data. Never store passwords. Never log credentials or tokens.
3. Our own database holds only app data: templates (versioned), field mappings,
   presets, print log, app roles keyed by Odoo user id, and an optional
   per-user short-lived cache. Do not mirror Odoo data.
4. Every Odoo field or model name in the guideline marked [VERIFY] must be
   confirmed with fields_get against the real instance before use. If it cannot
   be confirmed, stop and ask me. Do not invent field names.
5. Uploaded HTML templates are untrusted. Render them in a sandbox with scripts
   disabled and all external network requests blocked.
6. Template versioning and the print log are mandatory, not optional.
7. Printed values may be overridden by the user at print time. Overrides apply
   to the printed label and the print log only. They never go back to Odoo.

DELIVERABLES
- Working application, run with one command (docker compose up).
- README with setup, environment variables and how to run tests.
- Automated tests listed in the guideline's acceptance section.
- A seeded SAWO sample template (HTML hybrid, A6) that reproduces the sample
  label: logo, product photo, item code, description, EAN-13 barcode, SO NUMBER,
  PCS, KGS, CBM, PEFC mark, LOGO YES/NO tick box.
- A short docs/VERIFY_REPORT.md listing each [VERIFY] item, what you checked,
  and the result.

CONFIGURATION (ask me for anything missing, never hard-code)
ODOO_URL, ODOO_DB, Odoo version, hosting type (Odoo.sh / Online / on-premise),
printer type, default label size.

START NOW with Phase 0 (connection and field verification). Do not begin Phase 1
until I confirm the Phase 0 report.
```

---

# PART B. COMPLETE IMPLEMENTATION GUIDELINE

## 1. Goal and principles

1. The **SO number is the root key**. Everything else is resolved by following relations from that order.
2. **Odoo is the single source of truth and is never written to.**
3. Results are **grouped in process order** so the order's story reads top to bottom.
4. The user **chooses** which fields or rows go onto the label.
5. Labels come from an **uploaded template library**. The template is chosen at print time.
6. The same login as Odoo is used, so Odoo permissions apply automatically.

## 2. Recommended technology stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Simple Odoo RPC client, fast PDF tooling |
| Frontend | React + TypeScript (Vite) | Grouped tree with checkboxes, live preview |
| App database | PostgreSQL | Templates, versions, presets, print log |
| File storage | Local volume or S3-compatible | Uploaded template files and assets |
| HTML to PDF | Headless Chromium (Playwright) | Exact CSS control, barcode and image support |
| DOCX templates | `docxtpl` + LibreOffice headless to PDF | Business users edit in Word |
| PDF overlay | `pypdf` + `reportlab` | Background PDF with fields placed by coordinates |
| Barcode / QR | `python-barcode` (EAN-13, Code128) and `qrcode` | Rendered as SVG/PNG |
| Cache | Redis (optional) | Short per-user cache |
| Packaging | Docker Compose | One-command run |

The stack can be swapped, but the layering in section 3 must remain.

## 3. Architecture

```
Browser (React)
  login, SO search, grouped results, selection basket,
  template picker, live preview, print
        | HTTPS
FastAPI backend
  auth/        login against Odoo, app session
  odoo/        read-only connector (allow-listed methods)
  resolver/    SO number -> grouped related records
  catalog/     field catalog (key, label, group, source path)
  templates/   upload, placeholder scan, mapping, versioning
  render/      HTML / DOCX / PDF-overlay / ZPL -> PDF or ZPL
  layout/      sheet imposition (1-up, 2-up, 4-up A4, crop marks)
  printlog/    audit of every print job
        |
  PostgreSQL (app data)   File storage (templates, assets)
        |
Odoo (read-only, as the logged-in user)
```

## 4. Odoo connection

### 4.1 Connector rules
- One class `OdooReadClient` with exactly these public methods: `authenticate`, `search_read`, `read`, `search`, `fields_get`, `read_group`.
- Any attempt to call another method raises `ForbiddenOdooMethod`.
- A unit test enumerates the client's callable surface and fails if `create`, `write`, `unlink`, `execute_kw` with a non-allow-listed method, or similar is reachable.
- All calls run as the logged-in user. No shared admin account.
- Timeouts, retries (reads only) and per-request batching. Prefer `search_read` with `('id', 'in', ids)` domains over one call per record.

### 4.2 API styles **[VERIFY version]**
The connector must be an interface with swappable transports, because Odoo's external API is changing between versions:

| Odoo version | Typical transport | Authentication |
|---|---|---|
| 14 to 18 | `/jsonrpc` (JSON-RPC) or `/xmlrpc/2` (XML-RPC), `common.authenticate` then `object.execute_kw` | Login + password or API key |
| 19 and later | The newer `/json/2` style API may be available and the legacy RPC endpoints may be deprecated | Per-user API key (bearer) |

Phase 0 must determine which transport the instance supports. Check the instance's version first and confirm in Odoo's current external API documentation before choosing.

### 4.3 Login flow
1. User enters Odoo login and password (or API key if the version requires it).
2. Backend authenticates against Odoo and receives the user id.
3. Backend creates its own short-lived session (HTTP-only cookie, 30 minute idle timeout).
4. Any credential needed for later calls is held **encrypted in the server-side session only**, never in the database or logs, and deleted on logout or timeout.
5. If the instance only allows API keys for external access, the login screen asks for the API key instead of the password.
6. Rate-limit login attempts and lock out after repeated failures.

### 4.4 Read-only defence in depth
- Code: allow-list described above.
- Odoo: recommend placing users of this tool in a read-only access group so a code bug still cannot write.

## 5. Resolver: SO number to grouped records

Input: SO name (for example `S00123`). Output: one normalised JSON object with seven groups. Every model and field below is a **candidate to [VERIFY]** with `fields_get` for the actual version.

| # | Group | Model(s) | Candidate fields |
|---|---|---|---|
| 1 | Order header | `sale.order` | `name`, `state`, `date_order`, `partner_id`, `partner_shipping_id`, `client_order_ref`, `user_id`, `commitment_date` |
| 2 | Order lines | `sale.order.line` | `product_id`, `name`, `product_uom_qty`, `product_uom`, `qty_delivered`, `qty_invoiced`, `price_unit` |
| 3 | Product master data | `product.product` / `product.template`, `product.packaging` | `default_code`, `name`, `barcode`, `image_1920`, `weight`, `volume`, `uom_id`, packaging `qty` and `barcode` |
| 4 | Materials / BOM | `mrp.bom`, `mrp.bom.line` | `bom_line_ids`, component `product_id`, `product_qty`, `product_uom_id`, sub-assemblies |
| 5 | Manufacturing | `mrp.production`, `mrp.workorder` | `name`, `state`, `product_id`, `product_qty`, `date_start`, `bom_id`, work orders and work centers, consumed raw-material `stock.move` |
| 6 | Purchasing | `purchase.order`, `purchase.order.line` | vendor, lines, received quantities (make-to-order or dropship) |
| 7 | Delivery | `stock.picking`, `stock.move`, `stock.move.line`, `stock.lot`, packages | picking `name`, `state`, `scheduled_date`, `date_done`, move quantities, `lot_id`, package fields |
| 8 | Invoicing | `account.move` | `name`, `state`, `amount_total`, `invoice_date` |

### 5.1 How records are linked **[VERIFY]**
Links differ between versions and between make-to-stock, make-to-order and dropship flows. Check each of these in Phase 0:
- SO to pickings: the SO's picking relation, and `stock.picking.sale_id`.
- SO to manufacturing orders: the procurement group on the SO, and the `origin` field matching the SO name. Support both.
- SO to purchase orders: the line-level link from the sale line, and the procurement group.
- SO to invoices: the invoice relation on the SO and the invoice line to sale line link.
- Lot and quantity fields on move lines have changed names across versions (for example the done-quantity field). Detect them from `fields_get`.
- Multi-level BOMs: expand to a configurable depth (default 2).

### 5.2 Resolver behaviour
- Resolve in batches: SO, then lines, then products (one call), then pickings and moves (one call per model), then MOs, POs, invoices.
- Empty groups are returned as empty and shown as "none".
- Return both the raw Odoo value and a display value (names, not only ids).
- Return the unit of measure with every quantity. Never drop the UoM.
- Handle partial deliveries, backorders, split MOs, cancelled moves and returns. Include state so the UI can show them.
- Respect Odoo access errors. If a user cannot read a model, show that group as "not accessible" instead of failing the whole search.

### 5.3 Response shape (illustrative)
```json
{
  "so": "S00123",
  "fetched_at": "2026-10-06T09:50:00+08:00",
  "groups": [
    { "id": "header", "label": "Order header", "fields": [ ... ] },
    { "id": "lines", "label": "Order lines", "rows": [
      { "line_id": 11, "product": {"code":"220-TD","name":"...","barcode":"..."},
        "qty": 10, "uom": "pcs",
        "materials": [ ... ], "lots": [ ... ] } ] },
    { "id": "mrp", "label": "Manufacturing", "rows": [ ... ] },
    { "id": "purchasing", "label": "Purchasing", "rows": [ ... ] },
    { "id": "delivery", "label": "Delivery", "rows": [ ... ] },
    { "id": "invoicing", "label": "Invoicing", "rows": [ ... ] }
  ]
}
```

## 6. Field catalog and selection

The **field catalog** is the contract between the results screen and the templates.

| Property | Meaning |
|---|---|
| `key` | Stable id, for example `line.product.code` |
| `label` | Name shown to the user |
| `group` | One of the groups above |
| `source_path` | Where the value comes from in the resolver output |
| `type` | text, number, date, image, barcode |
| `scope` | so, line, lot, package |
| `selectable` | Whether it can be ticked |

Selection works at three levels: single field, whole row, whole group. Ticked items go into a **selection basket**. Users can save a basket as a **preset** (for example "Shipping label", "Production label") and reapply it to another SO.

## 7. Template library

### 7.1 Upload and activation
```
Upload file -> detect placeholders -> map to field catalog
  -> preview with a sample SO -> save new version -> activate
```
- Block activation until every placeholder resolves or is explicitly marked optional.
- Each save creates a new immutable **version**. Old versions stay usable for reprints.

### 7.2 Supported formats

| Format | Placeholder style | Render path |
|---|---|---|
| HTML/CSS | `{{so_number}}`, `{{line.product.name}}`, `{{barcode:line.product.barcode}}` | Chromium to PDF |
| DOCX | `{{so_number}}` in text (docxtpl) | docxtpl then LibreOffice to PDF |
| PDF or image background + overlay | Fields placed at x/y coordinates with font and size | `pypdf` + `reportlab` |
| ZPL | `{{so_number}}` inside ZPL text | String substitution, send to printer |

### 7.3 Template record
name, description, category, file, format, label size, orientation, scope, placeholder list with mapping, per-placeholder overflow rule (wrap, shrink to fit, truncate), version, active flag, uploaded by, date.

### 7.4 Overflow rules
Every text placeholder needs a rule. Product descriptions like "Thermometer Cut Corner Square 140x140mm, Cedar" must wrap or shrink instead of clipping.

### 7.5 Safe rendering
- Strip or disable all scripts.
- Block all outbound network requests during rendering. Images come only from our storage or the data being rendered.
- Run Chromium with a locked-down profile and a render timeout.

## 8. SAWO sample template (seed this first)

Recommended build: **Hybrid (Option C)**. HTML template, A6 label, fixed artwork for logos.

| Element | Source |
|---|---|
| SAWO logo | Fixed image in template assets |
| Product photo | Product image from Odoo |
| Barcode (EAN-13) | Product barcode from Odoo, rendered as barcode |
| Item code | Product internal reference |
| Description | Product name (wrap to two lines) |
| SO NUMBER | Sales order name |
| PCS, KGS, CBM | See section 9 |
| PEFC mark and number (PEFC/01-31-1332) | Fixed image, shown depending on the unresolved PEFC rule |
| LOGO YES/NO tick box | Print-time toggle. **Meaning unresolved**: do not assume it |

The sample shows two labels with the text "Cut CornerSquare" (missing space). The system must take the description from Odoo so this cannot recur.

## 9. PCS, KGS, CBM

Offer all four calculation modes as a print-time setting:

| Mode | Behaviour |
|---|---|
| 1. Order line totals | PCS = ordered qty. KGS, CBM = qty x unit weight / volume |
| 2. Per carton | Uses packaging qty and per-carton weight / volume |
| 3. Per delivery package | Uses actual packages on the delivery |
| 4. Editable override | Pre-filled from 1 or 2, user may correct before printing |

Rules:
- Default mode is configurable per template.
- Always show the calculated value next to the editable field.
- If weight or volume is missing in Odoo, show a visible warning and leave the field editable. Never print a silent zero.
- Overrides are stored in the print log with the original calculated value.

## 10. Sheet layout (separate from label design)

- Label template = one A6 panel.
- Sheet layout options: 1-up, 2-up, 4-up on A4, crop marks on or off, margins and gaps.
- Copies and **partial sheets** (for example 3 labels, one slot empty, or choose the starting slot to reuse a partly used sheet).
- The sheet layout is applied after rendering each label, so one label design works in every layout.

## 11. Print-time flow

1. Search or scan SO number.
2. Load related Odoo records.
3. Select fields or rows (or apply a preset).
4. Choose template (only those matching scope and label size are listed).
5. Preview. Missing data shows a clear warning.
6. Set copies, sheet layout, printer, PCS/KGS/CBM mode and overrides.
7. Print or export PDF.
8. Write print log.

## 12. Database schema (app data only)

| Table | Key columns |
|---|---|
| `app_user` | `odoo_uid`, `odoo_login`, `app_role`, `last_login` (no passwords) |
| `template` | `id`, `name`, `category`, `format`, `size`, `scope`, `active` |
| `template_version` | `id`, `template_id`, `version`, `file_ref`, `uploaded_by`, `created_at` |
| `template_mapping` | `template_version_id`, `placeholder`, `catalog_key`, `overflow_rule`, `optional` |
| `field_catalog` | `key`, `label`, `group`, `source_path`, `type`, `scope` |
| `preset` | `id`, `name`, `owner_uid`, `shared`, `selection_json` |
| `print_job` | `id`, `so_name`, `template_version_id`, `selection_json`, `overrides_json`, `calculated_json`, `copies`, `layout`, `printer`, `user_uid`, `created_at` |
| `audit_event` | `user_uid`, `event` (login, search, upload, print), `so_name`, `created_at` |

## 13. API endpoints

| Endpoint | Purpose |
|---|---|
| `POST /auth/login`, `POST /auth/logout` | Odoo-backed login and session end |
| `GET /so/{name}` | Resolver result, grouped |
| `GET /catalog` | Field catalog |
| `GET/POST /presets` | Selection presets |
| `GET /templates`, `POST /templates` (upload) | Library |
| `POST /templates/{id}/versions` | New version |
| `POST /render/preview` | Preview image or PDF from selection and template |
| `POST /render/print` | Final PDF or ZPL and log entry |
| `GET /print-jobs` | History and reprint |

## 14. Application roles (our app only)

| Role | Can do |
|---|---|
| Viewer | Search and view SO traces |
| Printer | Viewer plus print |
| Template admin | Printer plus upload, edit, activate templates |

Roles are stored against the Odoo user id. Odoo still controls which data any role can see.

## 15. Security checklist

- [ ] HTTPS only, secure and HTTP-only cookies.
- [ ] No passwords or API keys stored in the database, logs or error messages.
- [ ] Credentials in session only, encrypted, deleted on logout or timeout.
- [ ] Login rate limiting and lockout.
- [ ] Read-only allow-list enforced and tested.
- [ ] Cache keyed per user, short TTL, never shared across users.
- [ ] Template upload: file type and size limits, malware scan if available, sandboxed rendering, no script execution, no external network.
- [ ] Audit log for login, search, upload and print.
- [ ] Odoo users of the tool placed in a read-only group where possible.

## 16. Build phases and gates

| Phase | Scope | Gate (must pass before the next phase) |
|---|---|---|
| 0 | Connect to Odoo, detect version and transport, run `fields_get` on all models in section 5, write VERIFY_REPORT.md | I confirm the report and the final field list |
| 1 | Login, read-only connector, resolver, `GET /so/{name}` with seven groups | Real SO returns correct grouped data, allow-list test passes |
| 2 | Grouped results UI with checkboxes, selection basket, field catalog | Ticking works at field, row and group level |
| 3 | Template library: upload, placeholder scan, mapping, versioning, HTML render, SAWO seed template, PDF export | SAWO label prints correctly from a real SO |
| 4 | PCS/KGS/CBM modes and overrides, sheet layouts (1-up, 2-up, 4-up), partial sheets, print log | Reprint of an old job reproduces the original exactly |
| 5 | DOCX, PDF-overlay and ZPL formats, presets, app roles, reprint history | Each format renders a test label |
| 6 | Hardening: security checklist, performance, error handling, deployment docs | Checklist fully ticked |

## 17. Acceptance tests

1. **Read-only:** a test proves no write-type method can be called through the connector.
2. **Permissions:** a user without access to an SO cannot see it, and a user with limited model access sees "not accessible" for those groups only.
3. **Resolver:** for a known make-to-order SO, the result links the SO to its MO, BOM components, delivery with lots, and invoice. For a resale SO, manufacturing is empty without errors.
4. **UoM:** quantities always carry their unit and are never mixed across units.
5. **SAWO label:** printed output for product 220-TD shows the correct code, wrapped description, EAN-13 barcode, SO number and PCS/KGS/CBM, with no "CornerSquare"-style text errors.
6. **Overflow:** a very long product name wraps or shrinks without clipping.
7. **Versioning:** editing a template creates version 2 and a reprint of a version-1 job still uses version 1.
8. **Overrides:** an overridden KGS value appears on the label and in the print log together with the calculated value, and nothing is written to Odoo.
9. **Sheet layout:** the same label prints 1-up, 2-up and 4-up, and a 3-label partial sheet leaves one slot empty.
10. **Sandbox:** an uploaded HTML template containing a script and an external image URL renders without executing the script or contacting the network.
11. **Session:** passwords never appear in the database, logs or responses, and the session expires after the idle timeout.

## 18. Open decisions (answer before or during Phase 0)

| Decision | Why it matters |
|---|---|
| Odoo version, hosting, URL and database | Transport, field names and authentication method |
| Label scope: per carton or per order line | Decides the PCS, KGS, CBM mode |
| Meaning of LOGO YES/NO | Currently unresolved, do not assume |
| PEFC mark on every product or only certified ones | Controls whether the mark is conditional |
| Printer type (A4 laser or inkjet, or thermal) | Decides whether ZPL is needed in phase 3 or later |
| BOM expansion depth | Resolver performance and readability |
| Whether presets are shared or per user | Preset permissions |