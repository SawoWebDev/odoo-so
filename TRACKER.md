# Build Tracker — SO Sticker System

Source of truth: [docs/GUIDELINE.md](docs/GUIDELINE.md) (copy of `task.md`). Run it: `docker compose up --build` (see [README](README.md)).

Legend: `[x]` built **and** tested · `[~]` built and tested against an Odoo double, **needs confirmation on your real Odoo** · `[ ]` not done

**Last verified:** backend 197 tests green inside the Docker image (incl. headless Chromium + LibreOffice), frontend 7 tests green,
full stack (Postgres + Redis + API + nginx + mock Odoo) driven end to end by HTTP and by a real browser.

> The Phase 0 gate (you confirm the VERIFY report from a real instance) is the one thing that cannot be done without Odoo
> credentials. Everything after it was built defensively: candidate fields are intersected with `fields_get` at runtime, so a
> wrong guess is skipped, never sent.

## Phase 0 — Connection and field verification
- [x] 0.1 Swappable transports: JSON-RPC, XML-RPC, JSON-2 (Odoo 19+), auto-detected from server version
- [x] 0.2 `scripts/phase0_verify.py`: detect version/transport, `fields_get` on every model in guideline §5, probe link paths, resolve a sample SO
- [x] 0.3 Generates `docs/VERIFY_REPORT.md` (OK / alternate / MISSING per field, open human decisions)
- [x] 0.4 Transports tested over real HTTP against a mock Odoo server (`scripts/mock_odoo.py`)
- [ ] 0.5 **YOU: run Phase 0 against the real instance and confirm the report** (`docker compose run --rm -v "$PWD/docs:/srv/docs" backend python -m scripts.phase0_verify --so <SO>`)

## Phase 1 — Login, read-only connector, resolver
- [x] 1.1 `OdooReadClient` with allow-list (authenticate, search_read, read, search, fields_get, read_group); every transport re-checks it
- [x] 1.2 Allow-list tests: public surface, write-like names refused, all real transports refuse before any network call, only reads seen on the wire
- [x] 1.3 Login against Odoo, server-side session in Redis, Fernet-encrypted credentials, 30 min sliding idle timeout
- [x] 1.4 Login throttle + lockout (verified through nginx with the real client IP)
- [x] 1.5 Resolver: header, lines, products, BOM (depth-configurable, sub-assemblies), MRP (+work orders, consumed lots), purchasing (+dropship via origin), delivery (moves, lots, packages, backorders, returns), invoicing
- [x] 1.6 Per-group "not accessible" / "module not installed" / error; UoM on every quantity; batched reads (tested)
- [x] 1.7 Per-user short-TTL cache (tested: not served across users)
- [x] 1.8 `GET /api/so/{name}`; images stay server-side
- [~] 1.9 Real SO returns correct grouped data — compare with Odoo smart buttons (needs real Odoo)

## Phase 2 — Grouped results UI
- [x] 2.1 Field catalog (`GET /api/catalog`) seeded into the DB
- [x] 2.2 React + TypeScript app, login screen, role-aware navigation
- [x] 2.3 Grouped results; checkboxes at field, row, column and group level (unit-tested; checked in a real browser)
- [x] 2.4 Selection basket
- [x] 2.5 Presets: save / apply to another SO / share

## Phase 3 — Template library + HTML render + SAWO seed
- [x] 3.1 Upload HTML / zip / docx / zpl / overlay zip; type, size and zip-slip limits
- [x] 3.2 Placeholder scan, auto-mapping by key or alias, per-placeholder overflow rule, optional flag
- [x] 3.3 Immutable versions; activation blocked until every placeholder is mapped or optional
- [x] 3.4 Sandboxed HTML → PDF (sanitiser + CSP + JS off + request interception + timeout), each layer proven separately
- [x] 3.5 Barcode (EAN-13 with check-digit validation, Code 128 fallback) and QR
- [x] 3.6 Seeded SAWO A6 template (logo, photo, item code, 2-line description, EAN-13, SO number, PCS/KGS/CBM, PEFC, LOGO YES/NO) — logo and PEFC are stand-in artwork
- [x] 3.7 `POST /api/render/preview`, `POST /api/render/print`
- [~] 3.8 SAWO label prints correctly from a real SO (verified from the mock SO; confirm with a real one)

## Phase 4 — PCS/KGS/CBM, sheet layouts, print log
- [x] 4.1 Calculation modes 1–4; missing weight/volume = visible warning, Odoo's 0 treated as unset, print blocked until override/acknowledge
- [x] 4.2 Overrides stored with the original calculated value; verified nothing is written to Odoo
- [x] 4.3 Layouts: native, 1-up, 2-up, 4-up A4, crop marks, margin/gap, oversize → scaled + warned
- [x] 4.4 Copies and partial sheets (start slot, empty slots reported)
- [x] 4.5 Print log + render snapshot; reprint = original template version + original values, no Odoo call

## Phase 5 — More formats, roles, history
- [x] 5.1 DOCX (docxtpl in a Jinja sandbox, LibreOffice → PDF; sandbox escape returns 422)
- [x] 5.2 PDF/image background + coordinate overlay (fields.json)
- [x] 5.3 ZPL (data cannot inject commands; optional send to a network printer)
- [x] 5.4 App roles viewer / printer / template admin keyed by Odoo uid, managed in the UI
- [x] 5.5 Print history + reprint UI

## Phase 6 — Hardening and delivery
- [x] 6.1 Security headers, HTTP-only SameSite cookies, CSRF header guard, validation errors never echo input, audit log
- [x] 6.2 Docker Compose: `db`, `redis`, `backend`, `frontend` (+ `mock-odoo` under `--profile demo`); healthchecks
- [x] 6.3 README, docs/TEMPLATES.md, .env.example, .env.demo
- [x] 6.4 Automated tests for every acceptance item (below)
- [ ] 6.5 Security checklist — see below

### Security checklist (guideline §15)
- [~] HTTPS only, secure cookies — `COOKIE_SECURE` flag and cookie attributes are in place; **TLS termination is your deployment's job** (README)
- [x] No passwords/API keys in DB, logs, error messages, responses (tested)
- [x] Credentials only in the encrypted server-side session; removed on logout / idle timeout (tested)
- [x] Login rate limiting and lockout (in-process; single API worker in compose)
- [x] Read-only allow-list enforced and tested
- [x] Cache keyed per user, short TTL
- [~] Template upload limits: type/size/zip-slip enforced, sandboxed render, no script, no network — **no malware scan** (none available by default)
- [x] Audit log for login, failed login, search, upload, print
- [ ] Odoo read-only access group for tool users — **an Odoo-side action for you**

## Acceptance tests (guideline §17)
| # | Test | Status | Where |
|---|---|---|---|
| 1 | Read-only: no write-type method reachable | [x] | `test_readonly.py`, `test_transports.py` |
| 2 | Permissions: no access → not found; limited models → "not accessible" groups only | [x] (double) | `test_resolver.py`, `test_api.py` |
| 3 | Resolver: MTO links MO/BOM/delivery+lots/invoice; resale has empty MRP without errors | [x] (double) | `test_resolver.py` |
| 4 | UoM carried everywhere, never mixed | [x] | `test_resolver.py`, `test_calc.py` |
| 5 | SAWO label content for 220-TD, no "CornerSquare" | [x] | `test_render.py` |
| 6 | Overflow wraps/shrinks without clipping (measured in a browser) | [x] | `test_render.py` |
| 7 | Versioning: edit → v2; reprint of a v1 job uses v1 + original values | [x] | `test_render.py` |
| 8 | Override on label and in log with calculated value; nothing written to Odoo | [x] | `test_render.py` |
| 9 | 1/2/4-up; 3-label partial sheet leaves one slot empty | [x] | `test_layout.py`, `test_render.py` |
| 10 | Sandbox: script not executed, no network | [x] | `test_render.py` |
| 11 | Session: no password anywhere, idle expiry | [x] | `test_api.py` |

## Open decisions (guideline §18) — defaults used
| Decision | Default used | Where to change |
|---|---|---|
| Odoo version / hosting / URL / DB | `ODOO_TRANSPORT=auto`; URL/DB from `.env` | `.env` |
| Label scope: per carton or per line | per template `scope` (default `line`) | template upload form |
| Meaning of LOGO YES/NO | **unresolved** — plain toggle, nothing assumed | template |
| PEFC on every product or only certified | **unresolved** — plain toggle, nothing assumed | template |
| Printer type | A4/sheet PDF; ZPL supported | `.env` `PRINTERS` |
| BOM expansion depth | 2 | `.env` `BOM_DEPTH` |
| Presets shared or per user | per user, with a "shared" flag | preset dialog |
