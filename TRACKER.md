# Build Tracker — SO Sticker System

Run: `docker compose up --build` (see [README](README.md)). Original spec: [docs/GUIDELINE.md](docs/GUIDELINE.md) (kept as
history; the product has since been narrowed, see below).

Legend: `[x]` built and tested · `[~]` built, needs confirming on the real system · `[ ]` open

**Last verified:** backend 178 tests, frontend 10 tests, full Docker stack up (slim image ~400 MB), order screen checked in a real
browser, label matching checked on real PDFs copied from the share.

## Scope decisions (what changed from the original guideline)
- Only the **order header and order lines** are used. Products master data, BOM, manufacturing, purchasing, delivery and
  invoicing were removed.
- **No template library.** Labels are the **PDFs in the network folder**, one per item code. Removed: template upload,
  mapping, versions, HTML/DOCX/overlay/ZPL rendering, PCS/KGS/CBM calculation and overrides, LOGO/PEFC toggles, sheet layouts,
  presets, field catalog. (They are in git history: commit `6fb3807`.)

## Done
- [x] Read-only Odoo connector (JSON-RPC, XML-RPC, JSON-2), allow-list enforced everywhere and tested
- [x] Login with Odoo password, server-side Redis session (encrypted), idle timeout, lockout, roles, audit
- [x] Order resolver: header + lines (code, name, qty + unit), batched, "not accessible" per group, no-code lines skipped
- [x] Label files saved in the database: add a folder by URL (file://, UNC, //), fetch name + location of every PDF; exact + variant matching; priority
- [x] Preview/print fetch each PDF from its saved location; renamed/deleted file -> red row, warning on lines, print stops and flags it
- [x] Rescan = check saved files still exist (no new files); Read folder = save new PDFs; delete icon only on red rows; outage changes nothing
- [x] Order screen: Sales Order card, lines table (3 columns + Label file), paging with page count, one checkbox per line
- [x] No PDF → warning colour, cannot be ticked; qty 0 → grey, cannot be ticked (enforced on the server too)
- [x] Several PDFs per code → dropdown; default by `LABEL_FOLDER_PRIORITY`
- [x] Preview / print: single file streamed untouched, several combined, copies, size guard
- [x] Print log with file hashes + kept copies; Reprint identical, no Odoo/share needed
- [x] Label files tab: folders list, add/remove (admin), read folder, rescan, search + 'not found only' filter, red rows, delete icon
- [x] Docker: slim backend image, local-folder mount, network-share (CIFS) override, demo profile with mock Odoo
- [x] Phase 0 script + report generator

## Open — needs you
- [ ] **Network share login**: add `LABEL_SHARE_USER` / `LABEL_SHARE_PASSWORD` to `.env` (README). Until then the app reads a
      local sample folder holding 11 real PDFs, so most lines show "No label PDF".
- [ ] Run Phase 0 on the real Odoo and review `docs/VERIFY_REPORT.md`
- [ ] Choose the default PDF type when a code has several (`LABEL_FOLDER_PRIORITY`)
- [ ] HTTPS in front of the app (`COOKIE_SECURE=true`) and an Odoo read-only group for the users
- [~] Confirm the matching on a full real order once the share is mounted (item codes with unusual file names)
