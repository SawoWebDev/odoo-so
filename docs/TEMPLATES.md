# Template authoring guide

A template turns the values of one label into a printable page. Templates are **untrusted input**: they are rendered in a
sandbox (JavaScript off, no network, CSP, hard timeout), so only the constructs below exist.

## Placeholders

A placeholder is a name from the **field catalog** (`GET /api/catalog`) or one of its aliases. On upload the system scans the
template, maps every placeholder it recognises automatically, and **blocks activation until every placeholder is mapped or
marked optional**.

| Placeholder | Alias of | Meaning |
|---|---|---|
| `{{so_number}}` | `header.name` | Sales order number |
| `{{customer}}`, `{{customer_po}}` | `header.customer`, `header.customer_ref` | Customer, customer reference |
| `{{item_code}}`, `{{description}}` | `line.product.code`, `line.product.name` | Product reference and name from Odoo |
| `{{barcode}}`, `{{photo}}` | `line.product.barcode`, `line.product.image` | Product barcode, product image |
| `{{pcs}}`, `{{kgs}}`, `{{cbm}}` | `calc.pcs`, `calc.kgs`, `calc.cbm` | Calculated (or overridden) quantities |
| `{{pefc}}`, `{{logo_yes}}` | `print.pefc`, `print.logo` | Print-time toggles (see open decisions) |
| `{{today}}`, `{{label_seq}}` | `print.date`, `print.seq` | Print date, "2/5" |
| `{{line.product.name}}` … | the key itself | Any catalog key can be used directly |

Only **ticked** fields of **ticked** rows are available to a template (that is what the selection basket is). The calculated
and print-time keys are always available.

## HTML templates (`.html`, or `.zip` with assets)

```html
<img src="assets/logo.svg">                       <!-- bundled file, inlined as a data: URI at render time -->
{{item_code}}                                     <!-- text, HTML-escaped -->
{{description|shrink|max=60}}                     <!-- overflow rule: wrap | shrink | truncate, optional max chars -->
{{barcode:barcode}}                               <!-- EAN-13 (valid check digit) or Code 128, inline SVG -->
{{qr:so_number}}                                  <!-- QR code -->
{{image:photo|optional}}                          <!-- <img> from a base64 image value; optional = never blocks activation -->
{{imgsrc:photo}}                                  <!-- just the data: URI, for CSS backgrounds -->
{{#if pefc}}<img src="assets/pefc.svg">{{/if}}    <!-- conditionals (nest freely), also {{else}} and {{#unless x}} -->
```

* Set `@page` size in your CSS if you like; the page size actually used is the template's size/orientation setting.
* Keep it to **one label per page**. Use millimetres for positioning (`105mm`, `148mm` for A6).
* Anything that is removed at render time (scripts, event handlers, external URLs, `<iframe>`, `<link>` to remote CSS,
  `@import`) is listed on the template screen so you can fix it. Bundled CSS files referenced by `<link>` are inlined.
* **Overflow:** `wrap` (default) breaks long words and wraps onto more lines. `shrink` reduces the font size in proportion
  to the length (never below 55%) and, beyond what fits at that size, cuts the text with a visible `…` instead of clipping.
  `truncate` cuts at `max` characters. Shrinking is computed on the server because scripts are disabled in the sandbox.

Allowed files in a `.zip`: html, css, png, jpg, gif, svg, webp, woff/woff2, ttf/otf, json, pdf (max 200 files, 40 MB unpacked).

## Word templates (`.docx`)

Write `{{ so_number }}`, `{{ line.product.code }}`, `{{ pcs }}` directly in the document (headers and footers too) and optional
`{% if pefc %}…{% endif %}` blocks. Rendering uses docxtpl inside a Jinja **sandbox**, then LibreOffice converts to PDF. Text
only; use HTML or overlay templates for barcodes and images. A construct the sandbox refuses is reported as HTTP 422.

## PDF / image background + overlay (`.zip`)

`background.pdf` (or `.png` / `.jpg`) plus `fields.json`. Units are millimetres from the **top-left**.

```json
{"size": "A6", "orientation": "portrait",
 "fields": [
  {"placeholder": "so_number", "kind": "text",    "x": 10, "y": 20, "w": 60, "size": 14, "font": "Helvetica-Bold", "align": "left"},
  {"placeholder": "description", "kind": "text",  "x": 10, "y": 30, "w": 60, "h": 14, "size": 11, "overflow": "wrap"},
  {"placeholder": "barcode", "kind": "barcode",   "x": 10, "y": 80, "w": 60, "h": 20},
  {"placeholder": "photo",   "kind": "image",     "x": 10, "y": 45, "w": 40, "h": 30, "optional": true}]}
```

`kind`: `text`, `barcode`, `qr`, `image`. Fonts: Helvetica, Helvetica-Bold, Helvetica-Oblique, Times-Roman, Times-Bold, Courier,
Courier-Bold. `overflow`: `wrap` (stays inside `w`×`h` by shrinking if needed), `shrink`, `truncate`.

## ZPL (`.zpl`)

Plain ZPL with `{{placeholders}}`. `^` and `~` and control characters in *data* are replaced by spaces so data can never inject
printer commands. The result is delivered as a `.zpl` file; if `PRINTERS` in `.env` maps a printer name to `host:9100`, tick
"send to printer" (API: `send_to_printer`) to push it over the network.

## Versions

Every save (new file, new mapping, new size/scope) creates an **immutable new version**. The template's *active* version is
used for new prints; an active template only moves to a new version once that version has no unmapped placeholders. Print jobs
remember their exact version **and the exact values printed**, so a reprint months later looks identical even if the template or
the Odoo data has changed.
