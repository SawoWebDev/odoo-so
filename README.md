# SO Sticker System

Type an Odoo **Sales Order number**. The app collects everything related to it from Odoo, shows it grouped in process order
(header → lines → products → BOM → manufacturing → purchasing → delivery → invoicing), lets you **tick** the fields or rows to
use, and prints them onto a sticker **template** from an uploaded library (HTML, Word, PDF overlay or ZPL), on single labels or
1/2/4-up A4 sheets.

* **Read-only toward Odoo.** The connector exposes `authenticate, search_read, read, search, fields_get, read_group` and nothing
  else; this is enforced in code, in every transport, and by tests.
* **Sign in with your Odoo account.** Odoo decides what each user sees. No Odoo users or permissions are copied; no passwords are stored.
* **Everything runs in Docker.** `docker compose up` starts Postgres, Redis, the API and the web UI.

Build plan and progress: [TRACKER.md](TRACKER.md) · source of truth: [docs/GUIDELINE.md](docs/GUIDELINE.md) ·
templates: [docs/TEMPLATES.md](docs/TEMPLATES.md) · verification status: [docs/VERIFY_REPORT.md](docs/VERIFY_REPORT.md).

> **Status:** fully built and tested against an Odoo *double* (see Tests). It has **not** been run against a real Odoo yet, so
> the `[VERIFY]` items in the guideline are open. Do Phase 0 below before trusting field names or links.

## Try it in 2 minutes (no Odoo needed)

```bash
cp .env.demo .env
docker compose --profile demo up --build
```

Open <http://localhost:8080>. Sign in as `alice` / `pw-alice` (template admin), `bob` / `pw-bob` (printer) or `carol` / `pw-carol`.
Search `S00123` (make-to-order: BOM, MO, PO, two lots/packages, invoice) or `S00124` (resale). The `mock-odoo` service is a small
read-only fake Odoo that is only started with `--profile demo`.

## Use it with your Odoo

```bash
cp .env.example .env     # set ODOO_URL, ODOO_DB, APP_SECRET_KEY (long random), POSTGRES_PASSWORD
```

**Phase 0 (do this first).** Verify the connection and every candidate field against your instance:

```bash
docker compose run --rm -v "$PWD/docs:/srv/docs" backend python -m scripts.phase0_verify --so S00123
```

It asks for an Odoo login and password/API key (never stored), detects the version and API transport, runs `fields_get` on all
models of guideline §5, probes the SO link paths, resolves your sample order and writes [docs/VERIFY_REPORT.md](docs/VERIFY_REPORT.md).
Review every **MISSING** row and the "needs a human decision" table, then start the system:

```bash
docker compose up --build -d
```

Open <http://localhost:8080> and sign in with your Odoo login. Users listed in `INITIAL_ADMIN_LOGINS` become *template admins* on
first sign-in; everyone else gets `DEFAULT_ROLE`. Admins change roles on the **Roles** tab.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ODOO_URL`, `ODOO_DB` | – | Your instance. **Required.** |
| `ODOO_TRANSPORT` | `auto` | `auto` / `jsonrpc` / `xmlrpc` / `json2` (Odoo 19+ API-key style). `auto` probes the server version. |
| `ODOO_VERIFY_SSL`, `ODOO_TIMEOUT_S` | `true`, `30` | TLS verification, per-request timeout. |
| `APP_SECRET_KEY` | – | Encrypts Odoo credentials inside the server-side session. **Set a long random value.** |
| `SESSION_IDLE_SECONDS` | `1800` | Idle timeout (sliding). |
| `COOKIE_SECURE` | `false` | Set `true` once the site is served over HTTPS. |
| `LOGIN_MAX_FAILS`, `LOGIN_LOCKOUT_SECONDS` | `5`, `900` | Login throttle per client address + login. |
| `INITIAL_ADMIN_LOGINS`, `DEFAULT_ROLE` | `admin`, `printer` | App roles for first sign-in. |
| `BOM_DEPTH` | `2` | BOM / sub-assembly levels expanded. |
| `CACHE_TTL_SECONDS` | `120` | Per-user cache of a resolved SO. "Refresh" bypasses it. |
| `WEIGHT_FACTOR_TO_KG`, `VOLUME_FACTOR_TO_M3` | `1`, `1` | If your Odoo stores lb / ft³ instead of kg / m³. |
| `DEFAULT_LABEL_SIZE`, `MAX_UPLOAD_MB`, `RENDER_TIMEOUT_SECONDS` | `A6`, `15`, `20` | Labels and limits. |
| `PRINTERS` | `{}` | JSON map of ZPL network printers, e.g. `{"zebra1":"192.168.1.50:9100"}`. |
| `HTTP_PORT` | `8080` | Published web port. |

## How it works

```
Browser (React)  ──►  nginx (frontend container)  ──►  FastAPI (backend)  ──►  Odoo   (read-only, as the logged-in user)
                                                           │
                                       PostgreSQL: templates, versions, mappings, presets, print log, roles, audit
                                       Redis: sessions (encrypted credentials, in memory only, idle TTL)
                                       Volume: uploaded template files, print snapshots
```

1. **Login** → Odoo authenticates; the browser gets an opaque HTTP-only cookie; the credential lives encrypted in Redis only.
2. **SO lookup** → batched reads (one call per model per step). A model you cannot read becomes a "not accessible" group, an
   uninstalled module "module not installed"; neither fails the search. Every quantity carries its unit of measure.
3. **Selection basket** → tick a field, a whole row, a column, or a group; save the basket as a **preset** and re-apply it to another SO.
4. **Print** → pick a template (only active ones are offered), PCS/KGS/CBM mode, sheet layout, copies, start slot; **Preview**;
   type overrides if needed; **Print / export**. Missing weight/volume is a visible warning, never a silent zero, and printing is
   blocked until you override it or explicitly print anyway.
5. **Print log + snapshot** → each print stores who/what/when, the template **version**, the selection, calculated values *and*
   overrides, and the exact values rendered. **Reprint** re-renders from that snapshot with the original version and never calls Odoo.

Overrides affect the label and the print log only; nothing is ever written to Odoo.

### PCS / KGS / CBM

| Mode | PCS | KGS / CBM |
|---|---|---|
| 1 Order line totals | ordered qty | qty (converted to the product's unit) × unit weight / volume |
| 2 Per carton | packaging qty (the packaging on the line, else the largest) | × unit weight / volume |
| 3 Per delivery package | qty delivered in the selected package(s) | the package's recorded weight, else qty × unit weight |
| 4 Editable override | pre-filled from 1 or 2 | you correct it |

Units are converted only within one Odoo UoM category; different units are never added together.

### Roles (this app only)

`viewer` search & view · `printer` + print and reprint · `template_admin` + upload/edit/activate templates and manage roles.

## Tests

```bash
docker compose build backend
docker compose run --rm backend python -m pytest -q        # 197 tests incl. Chromium and LibreOffice
(cd frontend && npm install && npm test)                    # selection-basket logic (vitest)
```

The backend suite covers all eleven acceptance tests of guideline §17: read-only allow-list; permissions and "not accessible"
groups; make-to-order vs resale resolution; UoM safety; the SAWO label content; overflow measured in a real browser;
versioning and exact reprint; overrides in label and log with no write to Odoo; 1/2/4-up and partial sheets; the HTML sandbox
(script + external image); sessions, idle timeout and "password nowhere". The three Odoo transports are also tested over HTTP
against the mock server. Without Docker: `cd backend && pip install -r requirements.txt && pytest` (browser/LibreOffice tests
are skipped when those are missing).

Frontend development: `cd frontend && npm install && npm run dev` (proxies `/api` to `localhost:8000`).

## Security notes

* Terminate **HTTPS** in front of the `frontend` container (reverse proxy / load balancer) and set `COOKIE_SECURE=true`.
  Do not publish the backend port; it trusts `X-Forwarded-*` from nginx.
* Put the people who use this tool in a **read-only Odoo access group** as defence in depth.
* Rate limiting and lockout are in-process: the compose file runs a single API worker. Scale out only behind a shared limiter.
* The upload path enforces type and size limits and safe unzip; there is no antivirus hook (add one if your policy requires it).
* Sessions live in Redis without persistence: restarting Redis signs everyone out, by design.

## Known limits / open decisions

* **Not yet verified against real Odoo** (see VERIFY_REPORT). In particular Odoo 19 `/json/2` identity, UoM semantics on 19, and your
  SO→MO/PO links.
* **LOGO YES/NO** and **PEFC** are plain print-time toggles; their business meaning is unresolved in the guideline and not assumed.
* The seeded SAWO logo and PEFC mark are **stand-in artwork**; upload the official files as a new template version.
* Label scope (per carton or per line) is a per-template setting; the PCS/KGS/CBM mode is chosen at print time.
* Odoo's weight/volume `0` is treated as "not set".
