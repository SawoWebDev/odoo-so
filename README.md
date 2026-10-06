# SO Sticker System

Type an Odoo **Sales Order number**. The app shows the order (header + order lines) and, for every line, finds the
**label PDF** named after its item code in the saved list of label files. Tick the lines you want, then **preview** or **print** the
PDFs. Nothing is uploaded or designed in the app: the PDFs in the folder *are* the labels.

* **Read-only toward Odoo.** The connector exposes `authenticate, search_read, read, search, fields_get, read_group` and nothing
  else; enforced in code, in every transport, and by tests.
* **Sign in with your Odoo account** (login + password). Odoo decides what each user sees. Passwords are never stored.
* **The label folder is read-only too.** The app never writes to, renames or deletes anything on the share.
* **Everything runs in Docker.** `docker compose up` starts Postgres, Redis, the API and the web UI.

More: [docs/LABELS.md](docs/LABELS.md) (how PDFs are matched) · [TRACKER.md](TRACKER.md) · [docs/VERIFY_REPORT.md](docs/VERIFY_REPORT.md)

## What you see

1. **Sales Order**: the order as a labelled card (SO number, customer, delivery address, dates...).
2. **Order lines**: *Item code · Product name · Ordered qty · Label file*, with paging.
   * A line with a PDF shows its file name. If the item code has several PDFs (e.g. *Individual* and
     *Box Stickers*, or *No Logo*) a dropdown lets you choose; the default follows `LABEL_FOLDER_PRIORITY`.
   * A line with **no PDF** is shown in the **warning colour** and cannot be ticked.
   * A line with **ordered quantity 0** is greyed out and cannot be ticked. Lines with no item code (surcharge, bank charge...)
     are not listed.
3. **Print**: copies per label, printer name (for the log), **Preview**, **Print / export**. Several lines are combined into one
   PDF in the order you ticked them. A single label with one copy is passed through untouched.
4. **Label files** tab (see below): add the folder by URL; its PDFs are saved in the database; red rows = renamed or deleted.
5. **Print history**: who printed what; **Reprint** reproduces the original exactly.

## Run it

```bash
cp .env.example .env     # set ODOO_URL, ODOO_DB, APP_SECRET_KEY (long random), POSTGRES_PASSWORD
docker compose up --build -d          # http://localhost:8080  (HTTP_PORT in .env)
```

Try it without Odoo: `cp .env.demo .env && docker compose --profile demo up --build` and sign in as `alice` / `pw-alice`
(admin), `bob` / `pw-bob`, `carol` / `pw-carol`; search `S00123` (a line with two label PDFs), `S00124` (a line with no PDF),
`S00125` (a zero-quantity line). The demo uses a bundled fake Odoo and two generated PDFs in `demo-labels/`.

### The Label files tab

An admin adds a folder as a URL, for example the one you copy from Windows Explorer:

```
file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/
```

(`\\172.16.0.4\Marketing\...` and `//172.16.0.4/Marketing/...` work too.) The app reads the folder and **saves every PDF's
name and location in its database**. From then on:

* **Matching, Preview and Print use the saved name and location**: the PDF is fetched from the saved location each time.
* If a file is **renamed, moved or deleted**, it is **not found** at its saved location: its row turns **red**, lines that
  needed it show the warning colour, and a print that tries to use it stops with a clear message and flags it red.
* **Rescan** checks every saved file: *is it still where it was?* It updates the colours (a restored file turns normal again) and
  does not look for new files. If the whole folder cannot be reached (network down) nothing is changed.
* **Read folder** (per folder) reads the folder again and saves *new* PDFs.
* Red rows have a **🗑 delete icon**: it removes only the saved *record* of a file that is already gone. Files that still exist
  cannot be deleted, and nothing on the share is ever touched. **Remove** forgets a whole folder's saved list.

### Connecting the network share

The URL only works for the share that Docker has connected. Docker mounts `\\172.16.0.4\Marketing` itself, so give it a Windows
account that can read it (the share refuses anonymous access). Put in `.env` (the file is git-ignored):

```
COMPOSE_FILE=docker-compose.yml:docker-compose.network.yml
LABEL_SHARE=//172.16.0.4/Marketing
LABEL_SHARE_USER=your-windows-user
LABEL_SHARE_PASSWORD=your-windows-password        # must not contain a comma
LABEL_SHARE_DOMAIN=WORKGROUP                      # your domain, if the account has one
```

then `docker compose up -d` and add the folder URL on the Label files tab. Without the user/password Compose stops with a
clear message. For a local copy instead, point `LABEL_LOCAL_DIR` at a folder whose sub-folders mirror the share
(`<folder>/00 MASTERLIST/01 PRINTING FILES/...`); the same URLs then work.

### First check against your Odoo (Phase 0)

```bash
docker compose run --rm -v "$PWD/docs:/srv/docs" backend python -m scripts.phase0_verify --so S00123
```

It asks for an Odoo login and password (never stored), checks the three models and their fields on your version, resolves a
sample order and writes `docs/VERIFY_REPORT.md`.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ODOO_URL`, `ODOO_DB` | – | Your instance. **Required.** Use `https://` (redirects are not followed). |
| `ODOO_TRANSPORT` | `jsonrpc` in `.env.example` (code default `auto`) | `jsonrpc` / `xmlrpc` use the user's password (Odoo 17). `json2` (Odoo 19+) needs API keys. Accounts with two-factor auth cannot use a password over RPC. |
| `ODOO_VERIFY_SSL`, `ODOO_TIMEOUT_S` | `true`, `30` | TLS verification, per-request timeout. |
| `APP_SECRET_KEY` | – | Encrypts Odoo credentials inside the server-side session. **Set a long random value.** |
| `SESSION_IDLE_SECONDS` | `1800` | Idle timeout (sliding). |
| `COOKIE_SECURE` | `false` | Set `true` once served over HTTPS. |
| `LOGIN_MAX_FAILS`, `LOGIN_LOCKOUT_SECONDS` | `5`, `900` | Login throttle per client address + login. |
| `INITIAL_ADMIN_LOGINS`, `DEFAULT_ROLE` | `admin`, `printer` | App roles on first sign-in. Admins manage roles on the **Roles** tab. |
| `CACHE_TTL_SECONDS` | `120` | Per-user cache of an order. **Refresh** bypasses it. |
| `LABEL_MOUNT_DIR` | `/labels` | Where the share (or local folder) is mounted inside the container. Folder URLs must point below it. |
| `LABEL_SHARE` | – | The network share that is mounted there, e.g. `//172.16.0.4/Marketing`; this is how a `file://` URL is mapped to the mount. |
| `LABEL_LOCAL_DIR` | `./labels` | Host folder mounted read-only as `/labels` (local mode). |
| `LABEL_SHARE_USER`, `LABEL_SHARE_PASSWORD`, `LABEL_SHARE_DOMAIN` | – | Windows login for the share (network mode, see above). |
| `LABEL_DEFAULT_LOCATION` | empty | A folder URL added automatically once, when none has been added yet. |
| `LABEL_FOLDER_PRIORITY` | empty | Default among several PDFs for one item code: first word that appears in a folder path wins, e.g. `Box Stickers,Individual`. |
| `LABEL_MAX_MB` | `150` | Bigger PDFs can be viewed or printed alone (one copy) but are not merged or copied into the print snapshot. |
| `HTTP_PORT` | `8080` | Published web port. |

## How it works

```
Browser (React) ─► nginx ─► FastAPI ─► Odoo      (read-only, as the logged-in user)
                              ├─► label folder   (read-only, /labels)
                              ├─► PostgreSQL     roles, print log, audit
                              ├─► Redis          sessions (encrypted credentials, memory only, idle TTL)
                              └─► volume         a copy of every PDF that was printed
```

* **The saved list is the source of truth.** Searching an order looks item codes up in the database (thousands of files, instant),
  never in the folder. The folder is only read when you press *Read folder* / add it, and only *checked* by *Rescan*.
* **Print log + kept copies.** Each print stores who, which order, which files (path and SHA-256) and the copies, and keeps a copy
  of each file. **Reprint** uses those copies, never Odoo and not the share, so it is identical even if the artwork is edited
  or removed later. (A file over `LABEL_MAX_MB` is reprinted from the share instead; the screen says so.)
* The server re-checks every print request against fresh data: unknown lines, zero-quantity lines, lines without a usable PDF
  and files that are not a label for that item code are refused. A file that is no longer at its saved location stops the
  print and is flagged red.

Roles (this app only): `viewer` search, view, preview · `printer` + print, reprint, rescan · `admin` + manage roles and see
everyone's history.

## Tests

```bash
docker compose build backend
docker compose run --rm backend python -m pytest -q        # 192 tests, a few seconds
(cd frontend && npm install && npm test)                    # selection and paging logic (vitest)
```

The backend suite covers the read-only allow-list over all three Odoo transports (against a mock server), permissions, the
order resolver, the saved list (URL forms, fetch, rescan, renamed/deleted files, network outage, delete rules, roles), label
matching, preview/print/reprint, the print log,
sessions, lockout and "password nowhere".

## Security notes

* Terminate **HTTPS** in front of the `frontend` container and set `COOKIE_SECURE=true`. Do not publish the backend port.
* Put the people who use this tool in a **read-only Odoo access group** as defence in depth.
* The share account only needs **read** access; the mount is read-only regardless.
* Rate limiting is in-process: the compose file runs a single API worker.
* Sessions live in Redis without persistence: restarting Redis signs everyone out, by design.

## Known limits

* Not yet run against your real Odoo for every field (see VERIFY_REPORT); not yet run against the real share until the
  `LABEL_SHARE_*` login is configured.
* Nothing is drawn on the PDFs (no SO number or quantity is stamped). They print exactly as designed.
* Matching is by item code only; if the same code has differently-named files, the chosen file is what prints.
* New PDFs appear only after *Read folder*; a rename shows as one red record (old name) plus a new record (new name) after both.
* Print is "download/open the PDF, then print from the viewer": the app does not talk to printers directly.
