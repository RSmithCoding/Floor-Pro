# UI Route Contract: Settings and Customers

**Feature**: 001-settings-customer-records

FloorPro exposes HTML routes (not a JSON API) to its own pywebview window, on `127.0.0.1`
only.

**Response conventions**
- **Full page or partial**: every `GET` returns a **full page** normally, or only the named
  **partial** when the `HX-Request: true` header is present.
- **Forms** post as `application/x-www-form-urlencoded`. Checkboxes send `on` when ticked.
- **Validation failure**: `422`, with the form partial re-rendered, field errors shown inline
  and entered values kept.
- **Success after a write**:
  - HTMX request: `200` plus an `HX-Redirect` header (or a swapped partial where noted), and a
    toast fragment sent out-of-band to `#toasts`.
  - Plain request: `303 See Other`.
- **Not found**: `404` with the friendly "not found" page/partial. Raw errors are never
  shown.

---

## App shell

| Method | Path | Purpose | Response |
|--------|------|---------|----------|
| GET | `/` | Dashboard (home). In this feature: nav, quick customer search, "Add customer" button, placeholder cards for future appointments/invoices | Full page |
| GET | `/healthz` | Used by the desktop launcher to know the server is up | `200` text `ok` |

## Settings (User Story 2)

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| GET | `/settings` | Show currency & VAT settings | none | Page with the `settings/_form.html` partial and the last 10 history rows |
| POST | `/settings` | Validate and stage changes | `currency_code`, `vat_registered`, `vat_rate` (e.g. `20` or `17.5`), `vat_number`, `price_entry_mode` (`inc_vat`/`ex_vat`) | **Invalid** → `422` form with errors. **No changes** → `200` form with a "nothing to save" toast. **Changes** → `200` confirmation `<dialog>` into `#modal` listing each "old → new" and the notice "applies to new quotes and invoices only" (FR-006). The submitted values go back as hidden fields |
| POST | `/settings/confirm` | Apply the confirmed changes | Same fields + `change_set_token` (signed hash of the staged values) | **Token valid** → save, write history rows, `200` form + "Settings saved" toast. **Token mismatch** (settings changed meanwhile) → `409` with a message to review again |
| GET | `/settings/history` | Full change history | `page` (optional) | Page or `settings/_history.html` partial |

**Validation messages** (exact wording is a test fixture):
- VAT rate: "Enter a VAT rate between 0 and 100, with up to two decimal places."
- VAT number: "Enter a UK VAT number, for example GB123456789."
- Currency: "Choose a currency from the list."

## Customers (User Stories 1, 3, 4)

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| GET | `/customers` | List and search | Query: `q` (search text), `type` (`all`/`domestic`/`trade`, default `all`), `archived` (`0`/`1`), `sort` (`name`/`reference`/`created`, default `name`), `dir` (`asc`/`desc`) | Full page, or the `customers/_results.html` partial (table rows + count) for HTMX. Search input uses `hx-get`, `hx-trigger="input changed delay:250ms, search"` and `hx-push-url="true"`. **No results** → empty state with "Add '{q}' as a new customer" linking to `/customers/new?prefill={q}` |
| GET | `/customers/new` | New customer form | `prefill` (optional: put into the phone, email or name field depending on its shape) | Page with `customers/_form.html` |
| GET | `/customers/form/vat-fields` | Re-render the VAT-breakdown group when the type changes | `customer_type`, `show_vat_breakdown`, `original_type` | `customers/_vat_fields.html`. For trade: checkbox checked + disabled with a hidden `on` value and "Always shown for trade customers" |
| POST | `/customers` | Create | All customer fields (see data-model), plus optional `confirm_duplicate=1` | **Invalid** → `422` form. **Possible duplicates and not confirmed** → `200` form with a warning panel listing matches (reference, name, phone/email, link to open) and a "Save anyway" button that resubmits with `confirm_duplicate=1`. **Success** → redirect to `/customers/{id}` + toast "Customer C-00042 added". Postcode warning → saved, with the toast noting the postcode didn't look like a UK postcode |
| GET | `/customers/{id}` | Customer record | none | Page: details, type badge, VAT preference, timestamps, empty "Jobs, orders, appointments & invoices" section (FR-022), actions (Edit, Archive/Restore, Export, Erase) |
| GET | `/customers/{id}/edit` | Edit form | none | Page with `customers/_form.html` pre-filled |
| POST | `/customers/{id}` | Update | Same as create | As create. The duplicate check runs only if a phone/email changed. VAT rules applied by `resolve_vat_breakdown` (data-model) |
| GET | `/customers/{id}/archive` | Archive confirmation | none | `<dialog>` into `#modal` |
| POST | `/customers/{id}/archive` | Archive | none | Redirect to `/customers/{id}` + toast. Archived badge shown |
| POST | `/customers/{id}/restore` | Restore | none | Redirect + toast |
| GET | `/customers/{id}/export` | Export all data (FR-020) | none | `200 application/json`, `Content-Disposition: attachment; filename="FloorPro-customer-C-00042-YYYY-MM-DD.json"`. Format: [customer-export.md](customer-export.md) |
| GET | `/customers/{id}/erase` | Erase confirmation | none | `<dialog>` explaining what's deleted, with a text box "Type {display_name} to confirm" |
| POST | `/customers/{id}/erase` | Erase | `confirm_name` | **Matches** (case-insensitive, trimmed) → delete, redirect to `/customers` + toast "Customer erased". **Mismatch** → `422` dialog with the error "The name doesn't match." |

**Server-side rules enforced on every create/update, whatever the browser sends:**
- **Required fields**: a name or company name, and a phone or email (FR-012).
- **Normalisation**: email format, postcode normalisation and derived search columns
  (FR-014, FR-016).
- **VAT breakdown**: forced on for trade customers (FR-026, FR-027).
- **Timestamps**: `updated_at` set on every change (FR-018).

## Shared template regions (in `base.html`)

| Element id | Purpose |
|------------|---------|
| `#main` | Page content |
| `#modal` | Target for confirmation dialogs (`static/js/app.js` opens them with `showModal()`) |
| `#toasts` | Target for out-of-band toast fragments. Each toast disappears after 4 s (CSS only) |
