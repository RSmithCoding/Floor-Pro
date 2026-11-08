# Research: Currency & VAT Settings and Customer Records

**Feature**: 001-settings-customer-records | **Date**: 2026-11-08

This is FloorPro's first feature, so the research covers both the feature itself and the
project foundations it needs (tooling, app shell, database, UI base). Each entry records the
decision, the reason for it, and the alternatives considered.

---

## 1. Python version and project tooling

- **Decision**: Python **3.13**, managed with **uv**. `pyproject.toml` declares dependencies,
  `uv.lock` pins them, and `.python-version` pins the interpreter. Ruff handles linting and
  formatting. pytest runs the tests.
- **Rationale**: The constitution requires Python 3.12+ and a lock file. The development Mac
  currently has Python 3.10.8 only. uv is already installed (0.13.7) and can install 3.13
  without touching the system Python. 3.13 is mature, and pywebview, PyInstaller, FastAPI and
  SQLAlchemy all support it, while 3.14 is still newer for packaging tools. One `uv sync`
  gives an identical environment on macOS, Windows and CI.
- **Alternatives considered**: pip + venv + requirements.txt (no first-class lock, slower,
  manual interpreter management). Poetry (heavier, slower, and nothing it offers here is
  needed). Python 3.12 (works, but closer to end of life with no benefit).

## 2. Storing money and percentages

- **Decision**: Store money as **integer minor units** (pence) and percentages as **integer
  basis points** (20% = `2000`). SQLAlchemy `TypeDecorator`s convert these to and from
  `decimal.Decimal` at the model boundary. All rounding lives in `floorpro/domain/money.py`
  (`ROUND_HALF_UP` to 2 dp for money).
- **Rationale**: SQLite has no true decimal type. SQLAlchemy's `Numeric` on SQLite stores
  values as floating point and warns about it, which breaks Principle II. Integers are exact,
  fast to compare, and allowed by the constitution ("or integer minor units"). Application
  code only ever sees `Decimal`.
- **Alternatives considered**: `Numeric` columns (stored as floats on SQLite). Decimal stored
  as `TEXT` (exact, but sorting and sums need casting, and it's easy to misuse).
- **Note**: This feature stores only the VAT rate. Money amounts arrive with quoting and
  invoicing. The `Money`/`Percent` types and the `money` display filter are built now so
  every later feature uses them.

## 3. Business settings storage and history

- **Decision**: A typed **single-row table** `business_settings` (with a `CHECK (id = 1)`
  constraint) and an append-only `settings_change` table holding one row per changed field
  (field, old value, new value, UTC timestamp, and a `change_set_id` that groups the fields
  changed in one save). On startup, a missing row is recreated with the defaults and the user
  is told.
- **Rationale**: Typed columns give database-level validation and clear code. A single row
  avoids stringly-typed key/value lookups. The change log meets FR-007 ("which settings were
  in force on a given date") and is the audit trail later invoice features can rely on.
  Future documents will still snapshot their own currency/VAT (Constitution, Principle II).
- **Alternatives considered**: Key/value settings table (flexible, but untyped and needs
  parsing everywhere). JSON settings file in app data (no transactional history, and easy to
  corrupt).

## 4. Customer reference numbers

- **Decision**: `customer.id` is `INTEGER PRIMARY KEY AUTOINCREMENT`. The reference
  `C-{id:05d}` (`C-00042`) is **computed, not stored**. Search parses reference-shaped input
  (`C-00042`, `c42`) into an id lookup. Numbers grow past 5 digits naturally (`C-123456`).
- **Rationale**: SQLite's `AUTOINCREMENT` guarantees an id is never reused, even after the
  highest row is deleted (FR-013). Storing a reference that depends on the generated id would
  need an insert followed by an update, and a NOT NULL column can't be empty in between.
  Working it out from the id avoids the problem and can never get out of step with the id.
  No separate counter table is needed.
- **Alternatives considered**: A separate counter table (more moving parts for the same
  guarantee). UUIDs (not human-friendly at a shop counter).

## 5. Customer search

- **Decision**: Plain indexed `LIKE` queries over normalised search columns:
  `mobile_phone_digits` / `other_phone_digits` (digits only, with a leading `+44` mapped to
  `0`), `postcode_compact` (upper case, no spaces), plus case-insensitive (`COLLATE NOCASE`)
  name, company and email. Reference-shaped input (`C-00042`, `c42`) also matches by id
  (see §4). The query box sends requests with HTMX on `input`,
  debounced by 250 ms. Results are capped at 50 rows, with a "showing 50 of N" note.
- **Rationale**: At 10,000 customers a `LIKE '%term%'` scan over a few short columns takes
  milliseconds in SQLite, well inside SC-002 (1 s) and the constitution's 300 ms response
  target. Normalising on write makes "07700 900123" match "07700900123" (spec scenario 1.5).
- **Alternatives considered**: SQLite FTS5 (powerful, but needs triggers and a sync table, and
  is weak at the substring and phone matching that matter here. YAGNI). Searching in Python
  (doesn't scale, and duplicates logic).

## 6. Validation rules

- **Decision**: Pure functions in `floorpro/domain/validation.py`, unit tested first:
  - **UK postcode**: normalise (upper case, collapse whitespace, insert a space before the
    last 3 characters) and check against the standard UK pattern (including `GIR 0AA`). An
    invalid postcode returns a **warning**, not an error (spec edge case).
  - **Phone**: normalise to digits for search. Require at least 7 digits once stripped, and
    allow a leading `+`.
  - **Email**: `email-validator` (through Pydantic's `EmailStr`) with deliverability DNS checks
    **off**, because the app must work offline.
  - **UK VAT number**: strip spaces, upper case, require `GB` followed by 9 digits, 12 digits,
    `GD` + 3 digits or `HA` + 3 digits.
  - **VAT rate**: a `Decimal` from 0 to 100 inclusive with at most 2 dp.
- Form input is parsed by Pydantic v2 models in `floorpro/schemas/`. Errors are mapped to
  `{field: message}` and re-rendered next to each field (FR-023).
- **Rationale**: Pure functions are easy to test first (Principle III) and are reused by
  services, forms and future import features.
- **Alternatives considered**: WTForms (a second validation system alongside Pydantic, which
  FastAPI already uses). Validating in the browser only (bypassable and duplicated).

## 7. Server-rendered UI with HTMX

- **Decision**:
  - **Pages** extend `templates/base.html` (navigation, toast region, modal region).
  - **Components** are Jinja macros in `templates/components/` (button, field, select,
    checkbox, card, table, badge, empty state, modal, toast).
  - **Partials**: routes return a partial when the `HX-Request` header is present and a full
    page otherwise, so every URL also works when typed directly.
  - **Toasts** are sent with an `hx-swap-oob` fragment into `#toasts`, with no custom JS.
  - **Confirmations** (settings change, archive, erase) use a server-rendered `<dialog>`
    fragment swapped into `#modal`.
  - **Domestic ↔ trade switching**: the VAT-breakdown checkbox group is re-rendered by the
    server (`hx-get` on change), so it's locked on for trade with no client-side logic. The
    server enforces the same rule on save.
  - **Boosting exceptions**: forms and links that open a dialog use explicit
    `hx-get`/`hx-post` with `hx-target="#modal"` and `hx-swap="innerHTML"`, which overrides
    `hx-boost`. The export link has `hx-boost="false"` so the webview handles it as a file
    download.
- **Custom JavaScript** (justified per Principle IV): one small file, `static/js/app.js` (under
  40 lines), that (a) calls `showModal()` on a swapped-in `<dialog>`, since a native modal
  can't be opened from HTML alone, and (b) warns before leaving a form with unsaved changes (a
  spec edge case). Nothing else.
- **Rationale**: This meets Principles IV and V. Server-rendered partials keep all logic in
  Python and testable with `TestClient`.
- **Alternatives considered**: Alpine.js (another library for two tiny behaviours).
  `hx-confirm` with the browser's `confirm()` (unstyled, inconsistent across WebKit and
  WebView2, and can't show what will change).

## 8. Front-end assets

- **Decision**:
  - **HTMX**: 2.x minified file vendored into `static/vendor/` and committed.
  - **Tailwind**: v4 **standalone CLI** binary (no Node), pinned to an exact version and
    downloaded per platform by `scripts/fetch_tailwind.py` into the project root (already
    gitignored).
  - **Build**: `scripts/build_css.py` compiles `static/css/input.css` → `static/css/app.css`
    (generated and gitignored). It runs in development (`--watch`), in CI and before packaging.
  - **Design tokens** (colours, radius, spacing, fonts) live in `input.css` using Tailwind v4
    `@theme`. Fonts are bundled locally.
- **Rationale**: Principle IV requires no CDN and no Node at runtime. The standalone CLI works
  identically on macOS and Windows.
- **Alternatives considered**: Tailwind via npm (adds Node to the dev toolchain). The Tailwind
  Play CDN (needs a network connection and isn't for production). Committing the compiled CSS
  (drifts from source, and noisy diffs).

## 9. Desktop shell (pywebview + local server)

- **Decision**: `python -m floorpro` (`floorpro/__main__.py` → `desktop.py`):
  1. Resolve the data directory with `platformdirs.user_data_dir("FloorPro", appauthor=False)`.
  2. Back up the database and run Alembic migrations (see §10).
  3. Bind a socket to `127.0.0.1:0` to get a free port, then start uvicorn in a daemon thread
     on that port.
  4. Wait until `GET /healthz` answers, then open a `webview.create_window("FloorPro", url,
     min_size=(1024, 700))`.
  5. Closing the window stops the server.
  - **Saving files**: the launcher gives the app a `save_file(filename, data)` hook that
    shows the native Save dialog (`window.create_file_dialog(FileDialog.SAVE, …)`). The
    customer export (FR-020) uses it in the desktop window. *Amended after testing*: the
    original plan relied on pywebview's `ALLOW_DOWNLOADS`, but on macOS the web view opens
    any file it can display (including JSON) instead of downloading it, and with no Back
    button the user is stranded. FloorPro therefore never navigates to a file in the window.
  - A `--browser` flag runs the same server in a normal browser for development.
- **Rationale**: This meets the constitution's binding and data-location rules. Native
  engines are used: WebKit on macOS and WebView2 on Windows (built into Windows 10/11).
  `desktop.py` is the only module that imports `webview`, so tests and CI never need a GUI.
- **Alternatives considered**: A fixed port (collides with other software). Electron or Tauri
  (not Python-only). Running in a browser tab (not a desktop app).
- **Platform notes**: The development Mac is Intel (x86_64) on macOS 12. Mac builds from it
  will be x86_64 until packaging decides on universal2 or an Apple Silicon build in CI. That
  decision belongs to the packaging feature.

## 10. Database setup, migrations and pre-migration backup

- **Decision**:
  - **Engine**: SQLAlchemy 2.x (typed `Mapped[]` style), one SQLite file at
    `<data dir>/floorpro.db`. On connect the app sets `PRAGMA foreign_keys=ON`,
    `journal_mode=WAL` and `busy_timeout=5000`.
  - **Migrations**: Alembic scripts live **inside the package** (`floorpro/migrations/`) so
    PyInstaller can bundle them. They run programmatically at startup through a config built
    in code (no `alembic.ini` lookup at runtime). Batch mode is enabled for SQLite
    `ALTER TABLE`.
  - **Backup before migrating**: if the database exists and isn't at the head revision, it's
    copied to `<data dir>/backups/floorpro-<UTC timestamp>-pre-<revision>.db` using SQLite's
    online backup API before migrating. The 10 most recent automatic backups are kept.
  - **Development**: an `alembic.ini` at the repo root (pointing at the package scripts) is
    used for generating new revisions.
- **Rationale**: Principle I (migrations, automatic pre-migration backup, data in the
  per-user directory) and the packaging rules (resources resolved through one path helper
  that works when frozen).
- **Scope note**: The full user-facing **backup and restore** feature (Principle I) is a
  separate later feature. This feature delivers only the automatic pre-migration backup,
  which the constitution requires whenever migrations run.

## 11. Customer data export (FR-020)

- **Decision**: In the desktop window, `POST /customers/{id}/export/save` writes the file
  through the native Save dialog and shows a toast, staying on the page (see §9). In a normal
  browser (`--browser`), `GET /customers/{id}/export` returns a pretty-printed **JSON** file
  (`FloorPro-customer-C-00042-2026-11-07.json`) as an attachment. Its format is defined in
  [contracts/customer-export.md](contracts/customer-export.md). It includes every stored
  field, labelled in plain English, plus export metadata. Later features add their linked
  records to the same file.
- **Rationale**: JSON is readable by a person and by other software (which a data-protection
  request may need), and can be extended as features add data.
- **Alternatives considered**: PDF (good to read, but needs a PDF dependency and is hard to
  extend; better suited to invoicing). CSV (flat, and handles nested future data badly).

## 12. Erasing customers (FR-021)

- **Decision**: `CustomerService.erase()` checks `has_linked_records(customer)`. That returns
  `False` until jobs/orders/invoices exist, so the customer is hard-deleted. The anonymise
  branch is designed now but implemented with the first feature that adds linked records,
  together with the migration that relaxes the "must have a name and contact" constraints for
  anonymised rows. Confirmation requires typing the customer's display name (case-insensitive,
  ignoring surrounding whitespace).
- **Rationale**: Building the anonymise path with no records to protect would be untestable
  speculation (Principle VI, YAGNI). Putting the branch point in the service now makes the
  later change local.

## 13. Testing strategy

- **Decision**:
  - **Unit** (`tests/unit/`): domain functions (validation, normalisation, money/percent
    rounding, VAT-breakdown rule for customer types), written test-first.
  - **Integration** (`tests/integration/`): every route through FastAPI `TestClient` with a
    fresh SQLite file per test (`tmp_path`). Covers full page and HTMX partial responses,
    validation errors, duplicate warnings, the confirmation flow and settings history.
  - **Migrations** (`tests/migrations/`): upgrade an empty database to head, and check a
    seeded database survives an upgrade. Also check the pre-migration backup is created.
  - **Performance check**: an integration test seeds 10,000 customers and asserts a search
    returns in under 300 ms. It's marked `slow` but runs in CI.
- **CI**: GitHub Actions (`.github/workflows/ci.yml`) with a matrix of
  `macos-latest` × `windows-latest` running `uv sync --locked`, `ruff check`,
  `ruff format --check`, the Tailwind build and `pytest`.
- **Rationale**: Principle III and the constitution's macOS + Windows CI gate. Windows is
  verified in CI while no Windows machine is available.

## 14. Times and dates

- **Decision**: Store timestamps as UTC (timezone-aware) and show them in local time in the
  UK format (`7 Nov 2026, 14:05`). Formatting is handled by Jinja filters.
- **Rationale**: Clocks change (BST/GMT). UTC storage keeps the settings history ordering
  correct.

---

## 15. Messages after a save

- **Decision**: After a successful write, HTMX requests get **no redirect**. The server
  renders the destination page directly, sets `HX-Push-Url: /customers/{id}` so the address
  bar updates, and includes the toast fragment. Plain (non-HTMX) requests get `303` plus a
  short-lived **signed cookie** `flash` (HMAC with `paths.secret_key()`), which the next page
  shows once and then clears.
- **Rationale**: Browsers discard the body of a redirect response, so a toast attached to it
  is never shown. Rendering the destination directly is also one request faster.
- **Alternatives considered**: Starlette `SessionMiddleware` (adds `itsdangerous` and a full
  session just for one message). A `?toast=` query string (the message ends up in the address
  and history).

---

All Technical Context items are resolved. No `NEEDS CLARIFICATION` remains.
