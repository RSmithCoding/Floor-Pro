---

description: "Task list for 001-settings-customer-records"
---

# Tasks: Currency & VAT Settings and Customer Records

**Input**: Design documents from `/specs/001-settings-customer-records/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/routes.md,
contracts/customer-export.md, quickstart.md

**Tests**: Included. The constitution (Principle III) makes them mandatory:
- test-first for validation, calculation and rule logic
- an integration test for every route
- migration tests

Write each test task before its implementation task, and confirm it **fails** first.

**Organization**: Tasks are grouped by user story (US1–US4 from spec.md), so each story can be
built and tested on its own after Phase 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: User story the task belongs to (US1, US2, US3, US4)

## Path Conventions

Single package, src layout: `src/floorpro/…`, `tests/…`, `scripts/…` at the repository root
(see plan.md → Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialisation, tooling, assets and CI

- [X] T001 Create the directory layout from plan.md, with an empty `__init__.py` in each Python package. Directories:
  - `src/floorpro/` with `domain/`, `models/`, `schemas/`, `services/`, `routes/` and `migrations/versions/`
  - `src/floorpro/templates/` with `components/`, `errors/`, `settings/` and `customers/`
  - `src/floorpro/static/` with `css/`, `js/`, `vendor/` and `fonts/`
  - `tests/` with `unit/`, `integration/` and `migrations/`
  - `scripts/`
- [X] T002 Create `pyproject.toml` and `.python-version`, then run `uv lock` and `uv sync` to produce `uv.lock`:
  - **Project**: `name = "floorpro"`, `requires-python = ">=3.13"` (the interpreter actually used is pinned by `.python-version`)
  - **Build**: hatchling backend with src layout. Package data includes `templates/**`, `static/**` and `migrations/**`
  - **Runtime dependencies**: fastapi, uvicorn, sqlalchemy>=2.0, alembic, jinja2, pydantic>=2, email-validator, python-multipart, platformdirs, pywebview>=5
  - **Dev dependency group**: pytest, httpx, ruff
  - **Entry point**: `[project.scripts] floorpro = "floorpro.desktop:main"`
  - **`.python-version`**: `3.13`
- [X] T003 [P] Add ruff and pytest configuration to `pyproject.toml`:
  - **Ruff**: `line-length = 100`, `target-version = "py313"`, lint `select = ["E","F","I","UP","B","SIM"]`
  - **pytest**: `testpaths = ["tests"]`, `markers = ["slow: 10k-row performance tests"]`, `addopts = "--strict-markers"`
- [X] T004 [P] Create `scripts/fetch_tailwind.py`. It downloads the Tailwind CSS v4 standalone CLI to the repo root (both names are already gitignored):
  - **Version**: pinned in a constant `TAILWIND_VERSION` (an exact v4 release at least 2 weeks old)
  - **Platform asset**: chosen from `platform.system()`/`platform.machine()`: `tailwindcss-macos-x64`, `tailwindcss-macos-arm64`, `tailwindcss-windows-x64.exe` or `tailwindcss-linux-x64`
  - **Output**: saved as `tailwindcss` (or `tailwindcss.exe` on Windows) and made executable on POSIX. The version is written to `tailwindcss-version.txt`
  - **Re-runs**: skip the download if the recorded version already matches
- [X] T005 [P] Create `scripts/build_css.py`:
  - runs the Tailwind binary with `-i src/floorpro/static/css/input.css -o src/floorpro/static/css/app.css --minify`
  - supports `--watch` and fails with a clear message if the binary is missing
  - add `src/floorpro/static/css/app.css` to `.gitignore`
- [X] T006 [P] Vendor HTMX into `src/floorpro/static/vendor/htmx.min.js`:
  - use an exact 2.0.x release at least 2 weeks old
  - record the name, version and source URL in `src/floorpro/static/vendor/VERSIONS.md`
- [X] T007 [P] Create `.github/workflows/ci.yml`, run on push and pull_request:
  - **Matrix**: `os: [macos-latest, windows-latest]`
  - **Steps**:
    1. checkout
    2. `astral-sh/setup-uv`
    3. `uv sync --locked`
    4. `uv run ruff check .`
    5. `uv run ruff format --check .`
    6. `uv run python scripts/fetch_tailwind.py`
    7. `uv run python scripts/build_css.py`
    8. `uv run pytest` (the slow tests run too)
- [X] T008 [P] Create the dev-only `alembic.ini` at the repo root:
  - `script_location = src/floorpro/migrations`
  - `sqlalchemy.url = sqlite:///dev-data/floorpro.db`
  - add `dev-data/` to `.gitignore`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The app shell, database, migrations, money types, layout and components that every
story needs.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T009 [P] Create `src/floorpro/paths.py` (`pathlib` only):
  - `resource_path(relative: str) -> Path`: uses `Path(sys._MEIPASS) / "floorpro"` when `getattr(sys, "frozen", False)`, otherwise `Path(__file__).parent`
  - `data_dir() -> Path`: env var `FLOORPRO_DATA_DIR` if set, else `platformdirs.user_data_dir("FloorPro", appauthor=False)`. Creates the directory
  - `backups_dir()` and `logs_dir()`: subfolders of `data_dir()`, created on demand
  - `secret_key() -> bytes`: reads `data_dir()/secret.key`, creating it on first use with `secrets.token_bytes(32)`
- [X] T010 [P] Create `src/floorpro/logging_setup.py` with `configure_logging()`:
  - a `RotatingFileHandler` at `logs_dir()/floorpro.log` (1 MB × 5 files)
  - format: time, level, logger, message
  - a module docstring stating that log messages must not include customer personal data (use customer references instead)
- [X] T011 [P] Write failing tests in `tests/unit/test_money.py`:
  - `round_money(Decimal("1.005")) == Decimal("1.01")` (ROUND_HALF_UP, 2 dp)
  - `to_minor_units(Decimal("12.34")) == 1234` and `from_minor_units(1234) == Decimal("12.34")`
  - `percent_to_bp(Decimal("17.5")) == 1750` and `bp_to_percent(2000) == Decimal("20.00")`
  - `percent_to_bp` rejects more than 2 decimal places
  - every function raises `TypeError` when given a `float`
- [X] T012 Implement `src/floorpro/domain/money.py` so T011 passes. This is the single rounding module (Principle II): `MONEY_PLACES = Decimal("0.01")` and `ROUNDING = ROUND_HALF_UP`. No float is accepted anywhere.
- [X] T013 [P] Write failing tests in `tests/unit/test_currency.py`:
  - `SUPPORTED_CURRENCIES` holds exactly GBP (£, "Pound sterling"), EUR (€, "Euro") and USD ($, "US dollar")
  - `get_currency("XYZ")` raises `ValueError`
  - `format_money(Decimal("1234.5"), "GBP") == "£1,234.50"`
  - `format_money(Decimal("-3"), "EUR") == "-€3.00"`
- [X] T014 Implement `src/floorpro/domain/currency.py` so T013 passes. Use a frozen dataclass `Currency(code, symbol, name)`. Amounts always show exactly two decimal places (FR-008).
- [X] T015 Create `src/floorpro/models/base.py`:
  - `class Base(DeclarativeBase)` with a `MetaData(naming_convention=…)` covering `ix`, `uq`, `ck`, `fk` and `pk`, so Alembic batch mode can alter constraints
  - `Money` TypeDecorator: `Integer` ↔ `Decimal` via `to_minor_units`/`from_minor_units`
  - `Percent` TypeDecorator: `Integer` basis points ↔ `Decimal` via `percent_to_bp`/`bp_to_percent`
  - `UTCDateTime` TypeDecorator: stores naive UTC, returns timezone-aware UTC, and rejects naive input
  - `utcnow()` helper
- [X] T016 [P] Create `src/floorpro/models/settings.py` with the `BusinessSettings` model (table `business_settings`), per data-model.md §1. **Columns:**
  - `id` INTEGER PK, `CHECK (id = 1)`, default 1
  - `currency_code` TEXT(3) NOT NULL, default `'GBP'`
  - `vat_registered` Boolean NOT NULL, default true
  - `vat_rate` (`Percent`, column `vat_rate_bp`) INTEGER NOT NULL, default 2000, `CHECK (vat_rate_bp BETWEEN 0 AND 10000)`
  - `vat_number` TEXT NULL
  - `price_entry_mode` TEXT NOT NULL, default `'inc_vat'`, `CHECK (price_entry_mode IN ('inc_vat','ex_vat'))`, exposed as a `PriceEntryMode(StrEnum)`
  - `updated_at` UTCDateTime NOT NULL

  Add the `SettingsChange` model (table `settings_change`) in the same file, per data-model.md §2:
  - `id` INTEGER PK AUTOINCREMENT
  - `change_set_id` TEXT(36) NOT NULL
  - `changed_at` UTCDateTime NOT NULL, indexed
  - `field` TEXT NOT NULL with `CHECK (field IN ('currency_code','vat_registered','vat_rate','vat_number','price_entry_mode'))`
  - `old_value` TEXT NULL and `new_value` TEXT NULL
- [X] T017 [P] Create `src/floorpro/models/customer.py` with the `Customer` model (table `customer`, `sqlite_autoincrement=True`), per data-model.md §3. **Identity and type:**
  - `id` INTEGER PK AUTOINCREMENT
  - a read-only `reference` property (not a column) returning `f"C-{self.id:05d}"` (research.md §4)
  - `customer_type` TEXT NOT NULL, default `'domestic'`, `CHECK (customer_type IN ('domestic','trade'))`
  - `show_vat_breakdown` Boolean NOT NULL, default false

  **Name fields:**
  - `title` TEXT NULL, "up to 20 chars"
  - `first_name` TEXT NULL, "up to 100 chars"
  - `last_name` TEXT NULL `COLLATE NOCASE`, "up to 100 chars"
  - `company_name` TEXT NULL `COLLATE NOCASE`, "up to 200 chars"

  **Contact fields:**
  - `mobile_phone` and `other_phone`: TEXT NULL, "up to 30 chars"
  - `mobile_phone_digits` and `other_phone_digits`: TEXT NULL
  - `email` TEXT NULL `COLLATE NOCASE`

  **Address fields:**
  - `address_line1` and `address_line2`: TEXT NULL, "up to 200 chars"
  - `town` and `county`: TEXT NULL, "up to 100 chars"
  - `postcode` and `postcode_compact`: TEXT NULL

  **Other fields:**
  - `notes` TEXT NULL, "no length limit"
  - `marketing_consent` Boolean NOT NULL, default false
  - `is_archived` Boolean NOT NULL, default false
  - `archived_at` UTCDateTime NULL
  - `created_at` and `updated_at`: UTCDateTime NOT NULL

  **Table CHECKs:**
  - `CHECK (COALESCE(TRIM(first_name),'') <> '' OR COALESCE(TRIM(last_name),'') <> '' OR COALESCE(TRIM(company_name),'') <> '')`
  - `CHECK (mobile_phone IS NOT NULL OR other_phone IS NOT NULL OR email IS NOT NULL)`
  - `CHECK (customer_type = 'domestic' OR show_vat_breakdown = 1)`

  **Indexes**: `last_name`, `company_name`, `email`, `mobile_phone_digits`, `other_phone_digits`, `postcode_compact`, and a composite `(is_archived, customer_type)`.
- [X] T018 Create `src/floorpro/db.py`:
  - `make_engine(db_path: Path)`: an SQLite engine with a `connect` event that runs `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`
  - `make_sessionmaker(engine)` with `expire_on_commit=False`
  - FastAPI dependency `get_session(request)`: yields a session from `request.app.state.sessionmaker`, commits on success and rolls back on exception
- [X] T019 Create the Alembic environment and initial migration:
  - **`src/floorpro/migrations/env.py`**: uses `Base.metadata` from `floorpro.models` with `render_as_batch=True`, and takes its connection from `config.attributes["connection"]` when provided
  - **`src/floorpro/migrations/versions/0001_initial.py`**: creates `business_settings`, `settings_change` and `customer` exactly as in T016/T017 (all CHECKs and indexes), with `down_revision = None`
  - **`src/floorpro/models/__init__.py`**: imports all models so `Base.metadata` is complete
- [X] T020 Create `src/floorpro/migrate.py`:
  - `alembic_config(db_path)`: builds `alembic.config.Config()` in code with `script_location = str(resource_path("migrations"))`. It doesn't read any ini file
  - `current_revision(db_path)` and `head_revision()`
  - `backup_if_needed(db_path) -> Path | None`: only if the file exists and isn't at head. Copies it with `sqlite3.Connection.backup` to `backups_dir()/f"floorpro-{UTC:%Y%m%dT%H%M%SZ}-pre-{head}.db"`, then deletes all but the 10 newest `floorpro-*-pre-*.db` files
  - `upgrade_to_head(db_path)`: calls `backup_if_needed` first. Then it opens `make_engine(db_path)` and, inside `engine.begin() as conn`, sets `cfg.attributes["connection"] = conn` before running `command.upgrade(cfg, "head")`. env.py (T019) uses that connection and never reads a URL
- [X] T021 [P] Write `tests/migrations/test_migrations.py`:
  - **Empty database**: `upgrade_to_head` on a new path creates all three tables with their CHECK constraints, verified by an insert that violates each CHECK raising `IntegrityError`
  - **Pre-migration backup**: create a database with an unrelated table and one row, not at head. `upgrade_to_head` creates exactly one `backups/floorpro-*-pre-0001*.db` containing that row, and the original row survives
  - **Already at head**: running again creates no new backup
  - **Backup retention**: only the 10 newest backups are kept
  - **Realistic data** (Principle III): after upgrading to head, insert a full `business_settings` row with non-default values, 3 `settings_change` rows, and 5 customers (domestic and trade, archived and active, with all optional fields filled). Run `upgrade_to_head` again and check every row and value is unchanged. Future migrations must extend this fixture with that migration's previous schema
- [X] T022 Create `src/floorpro/services/settings_service.py` (foundational part only). `ensure_settings(session) -> tuple[BusinessSettings, bool]` returns the single row. If the row is missing, it creates the defaults (GBP, VAT registered, 20%, `inc_vat`) and returns `created=True`. Add `get_settings(session)` as well.
- [X] T023 Create `src/floorpro/templating.py`:
  - `templates = Jinja2Templates(directory=resource_path("templates"))`
  - **Filters**: `money(value)` (uses the currency in `request.state.settings` via `format_money`), `percent(value)` (`Decimal("17.50")` → `"17.5%"`, `Decimal("20.00")` → `"20%"`) and `local_datetime(dt)` (UTC → local time, format `"7 Nov 2026, 14:05"`)
  - **`is_partial(request)`**: true when `HX-Request` is present and `HX-Boosted` is absent
  - **`render(request, page, partial, context, status_code=200, toast=None, push_url=None)`**: returns the partial or the full page. When `toast=(kind, message)` is given, appends the `components/toast.html` out-of-band fragment. When `push_url` is given, sets the `HX-Push-Url` header
  - **Messages after a save** (research.md §15):
    - `flash_redirect(url, kind, message)`: returns a `303` with a short-lived `flash` cookie signed with HMAC over `paths.secret_key()`
    - `pop_flash(request)`: reads and verifies the cookie and returns the message, and the response clears the cookie
    - `base.html` shows any popped flash message as a toast
- [X] T024 Create `src/floorpro/app.py` with `create_app(data_dir: Path | None = None) -> FastAPI`:
  - **Lifespan**:
    1. `configure_logging()`
    2. `upgrade_to_head(db_path)`
    3. create the engine and sessionmaker on `app.state`
    4. `ensure_settings`. If the database existed but the row was recreated, set `app.state.settings_notice = True`
  - **Middleware**: loads the current settings into `request.state.settings` for every request
  - **Static files**: mounted from `resource_path("static")` at `/static`
  - **Exception handlers**: 404 and 500 render `errors/404.html` and `errors/500.html` (a partial when `is_partial`), log the traceback, and never show stack traces to the user
  - **Settings-reset notice**: shown once as an info toast, "Settings were missing and have been reset to the defaults (GBP, 20% VAT)."
- [X] T025 [P] Create `src/floorpro/static/css/input.css`:
  - `@import "tailwindcss";` and `@source "../../templates";`
  - `@theme` design tokens:
    - primary brand scale
    - neutral scale
    - success, warning and danger colours, with every text/background pairing at WCAG 2.1 AA (4.5:1 or better)
    - `--radius-*`
    - `--font-sans` using a locally bundled variable font, e.g. Inter, OFL-licensed, placed in `src/floorpro/static/fonts/` with its licence file and loaded via `@font-face`
  - a CSS-only toast fade-out after 4 s (keyframes)
  - `<dialog>` and backdrop styles
- [X] T026 [P] Create `src/floorpro/static/js/app.js` (under 40 lines, no libraries):
  - **(a) Modals**: on `htmx:afterSwap`/`htmx:load`, call `showModal()` on any `dialog` inside `#modal`. Elements with `[data-close-dialog]` close the dialog
  - **(b) Unsaved-changes guard**: track `input` events on forms with `data-guard-unsaved`. While a form is dirty, intercept clicks on links and `hx-boost` navigation outside it, and show the `#discard-dialog` in `base.html`. "Discard" continues the navigation and "Keep editing" cancels it. Submitting the form clears the dirty state
- [X] T027 Create `src/floorpro/templates/base.html`:
  - `<html lang="en-GB">`, linking `/static/css/app.css`, `/static/vendor/htmx.min.js` and `/static/js/app.js`. No external URLs
  - `hx-boost="true"` on `<body>`
  - a sidebar nav (Dashboard `/`, Customers `/customers`, Settings `/settings`) showing the active state
  - `<main id="main">`, `<div id="modal">` and `<div id="toasts" aria-live="polite">`
  - `#discard-dialog` with the copy "You have unsaved changes. Discard them?"
- [X] T028 [P] Create the Jinja macro components in `src/floorpro/templates/components/`:
  - **`button.html`**: variants primary, secondary, danger, ghost. Sizes sm, md
  - **Form fields**:
    - `field.html`: label, input, hint, inline error in danger colour, warning in warning colour, `aria-describedby`
    - `select.html`
    - `checkbox.html`: supports `disabled` plus a hidden value and a hint
  - **`card.html`**
  - **`table.html`**: header cells with optional sort links
  - **`badge.html`**: domestic, trade, archived
  - **`empty_state.html`**: message plus an optional action
  - **`modal.html`**: a `<dialog>` with title, body and action slots
  - **`toast.html`**: an `hx-swap-oob="beforeend:#toasts"` fragment in success, error or info kind
- [X] T029 [P] Create the friendly error pages:
  - `src/floorpro/templates/errors/404.html`: "We couldn't find that page", with a link back to the dashboard
  - `src/floorpro/templates/errors/500.html`: "Something went wrong. Your data is safe. Please try again.", with no technical details
- [X] T030 Create `src/floorpro/routes/dashboard.py` and `src/floorpro/templates/dashboard.html`:
  - **`GET /`**: welcome heading, a quick customer search form (`GET /customers?q=`), an "Add customer" button (`/customers/new`), and placeholder cards "Upcoming appointments" and "Outstanding invoices" using `empty_state` with "Coming soon"
  - **`GET /healthz`**: returns plain-text `ok`
  - register the router in `app.py`
- [X] T031 Create `src/floorpro/desktop.py` and `src/floorpro/__main__.py`:
  - **`main()`** (argparse `--browser`), in order:
    1. find a free port by binding `("127.0.0.1", 0)`
    2. create `uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_config=None))`
    3. run it in a daemon thread
    4. poll `http://127.0.0.1:{port}/healthz` with `urllib.request` for up to 10 s
  - **Default (no `--browser`)**: `import webview` inside the function (the only module that imports it), set `webview.settings["ALLOW_DOWNLOADS"] = True`, then `webview.create_window("FloorPro", url, min_size=(1024, 700))` and `webview.start()`. Set `server.should_exit = True` on exit
  - **`--browser`**: `webbrowser.open(url)` and block until Ctrl+C
  - **`__main__.py`**: calls `main()`
- [X] T032 Create `tests/conftest.py`. **Fixtures:**
  - `data_dir`: a `tmp_path`, with `monkeypatch.setenv("FLOORPRO_DATA_DIR", ...)`
  - `app`: `create_app(data_dir)`
  - `client`: `with TestClient(app) as c` so the lifespan runs
  - `session`: from `app.state.sessionmaker`
  - `htmx`: a headers dict `{"HX-Request": "true"}`

  **Helper:**
  - `make_customer(session, **overrides)`: inserts a valid domestic customer with the derived columns, then commits
- [X] T033 [P] Write `tests/integration/test_app_shell.py`:
  - `GET /` returns 200 and contains the nav links and "Upcoming appointments"
  - `GET /healthz` returns `ok`
  - `GET /nope` returns 404 with "We couldn't find that page" and no "Traceback"
  - the same request with the `htmx` headers returns the partial (no `<html>`)
  - a handler that raises renders the 500 page. Use `TestClient(app, raise_server_exceptions=False)` and a test-only route, registered in the fixture, that raises `RuntimeError`
  - deleting the `business_settings` row and creating a new app on the same `data_dir` restores the defaults and shows the reset notice toast on the first page

**Checkpoint**: `uv run python -m floorpro --browser` opens a styled dashboard. The migration
creates all tables. CI is green on macOS and Windows.

---

## Phase 3: User Story 1 - Add and find customers (Priority: P1) 🎯 MVP

**Goal**: Staff can add customers, with validation, a unique reference and duplicate warnings,
and find them instantly by name, company, phone, postcode, email or reference.

**Independent Test**: In an empty app, add several customers, restart, and find each one by
every search term with all its details intact (quickstart.md §B).

### Tests for User Story 1 ⚠️ Write first, confirm they fail

- [X] T034 [P] [US1] Write `tests/unit/test_validation_customer.py`.

  **`normalise_postcode`**:
  - `"sw1a1aa"` → `("SW1A 1AA", warning=False)`
  - `" bs1 4dj "` → `("BS1 4DJ", False)`
  - `"gir0aa"` → `("GIR 0AA", False)`
  - `"hello"` → `("HELLO", warning=True)`

  **Other functions**:
  - `postcode_compact("BS1 4DJ") == "BS14DJ"`
  - `phone_digits`:
    - `"07700 900123"` → `"07700900123"`
    - `"+44 7700 900123"` → `"07700900123"`
    - `"(01234) 567-890"` → `"01234567890"`
  - `validate_phone("12345")` returns the error "Enter a phone number with at least 7 digits."
  - `validate_email("jane@example")` returns an error and `"Jane.Smith@Example.com"` is accepted, with no network calls
- [X] T035 [P] [US1] Write `tests/unit/test_customers_domain.py`:
  - `display_name(first="Jane", last="Smith", company=None) == "Jane Smith"`
  - with a company only, it returns the company
  - with a company and a person, it returns `"Acme Flooring (Jane Smith)"`
  - `sort_name` returns `"Smith, Jane"` for a person, and the company name when there's no last name
- [X] T036 [P] [US1] Write `tests/integration/test_customers_create.py`, covering spec scenarios 1.1, 1.2, 1.3 and 1.6 and contracts/routes.md `POST /customers`.

  **Successful saves**:
  - a valid POST with the `htmx` headers returns 200 with the record page for `/customers/{id}`, an `HX-Push-Url: /customers/{id}` header, `C-00001`, `BS1 4DJ` and the toast "Customer C-00001 added"
  - the same POST without the `htmx` headers returns 303. Following it shows the toast once, and it's gone on the next page
  - the second customer gets `C-00002`
  - an unrecognisable postcode is saved, with a toast warning that it doesn't look like a UK postcode
  - a customer with 5,000 characters of notes saves, and the record page shows them in full

  **Validation failures**:
  - no name and no company returns 422 with "Enter a first name, last name or company name.", and the entered values are kept
  - no phone and no email returns 422 with "Add a phone number or email address."

  **Duplicates**:
  - a matching mobile number (with different spacing) or email (with different case) returns 200 with the duplicate panel linking to the existing customer, and creates no new row
  - resubmitting with `confirm_duplicate=1` creates the customer
- [X] T037 [P] [US1] Write `tests/integration/test_customers_search.py`, covering spec scenarios 1.4 and 1.5 and contracts/routes.md `GET /customers`.

  **Matching**:
  - `q=07700900123` finds a customer stored as `07700 900123`
  - `q=SW1A` finds by postcode
  - search also matches part of a last name, a company, an email (case-insensitive), and references in the forms `c-00001`, `C1` and `c1`

  **Results and partials**:
  - archived customers are hidden unless `archived=1`
  - `sort=name|reference|created` with `dir` orders the results
  - with the `htmx` headers, only the `_results.html` partial is returned; without them, the full page
  - `q=zzz` shows the empty state with a link to `/customers/new?prefill=zzz`
  - 60 matches return 50 rows and "Showing 50 of 60"
  - **Persistence** (SC-005): after creating 3 customers, a new `create_app` on the same `data_dir` lists all 3 with unchanged fields

- [X] T038 [P] [US1] Write `tests/integration/test_customers_new.py`, covering contracts/routes.md `GET /customers/new` (Principle III: every route has an integration test):
  - `GET /customers/new` returns 200 with an empty form whose type defaults to domestic
  - `prefill=07700 900123` fills `mobile_phone`
  - `prefill=jane@example.com` fills `email`
  - `prefill=Jane Smith` fills first name "Jane" and last name "Smith"
  - `prefill=Acme` fills first name "Acme"
  - with the `htmx` headers, only the `_form.html` partial is returned

### Implementation for User Story 1

- [X] T039 [US1] Implement `normalise_postcode`, `postcode_compact`, `phone_digits`, `validate_phone` and `validate_email` in `src/floorpro/domain/validation.py`, so T034 passes:
  - UK postcode regex including `GIR 0AA`
  - `+44` → `0`
  - at least 7 digits for a phone number
  - `email_validator.validate_email(..., check_deliverability=False)`
- [X] T040 [US1] Implement `display_name` and `sort_name` in `src/floorpro/domain/customers.py` so T035 passes.
- [X] T041 [US1] Create `src/floorpro/schemas/customer_form.py` with a Pydantic v2 `CustomerForm`:
  - **Field limits** (quoting data-model.md): `title` "up to 20 chars", `first_name`/`last_name` "up to 100 chars", `company_name` "up to 200 chars", `mobile_phone`/`other_phone` "up to 30 chars", `email`, `address_line1`/`address_line2` "up to 200 chars", `town`/`county` "up to 100 chars", `postcode`, `notes` "no length limit"
  - **Other fields**: `marketing_consent` (checkbox `"on"` → bool), and `customer_type` (default `"domestic"`, values `domestic|trade`) plus `show_vat_breakdown`, both accepted here with their rules added in US4
  - **Before validation**: every string is trimmed and an empty string becomes `None`
  - **Model validators**:
    - "Enter a first name, last name or company name." (key `name`)
    - "Add a phone number or email address." (key `contact`)
  - **`from_form(form_data) -> tuple[CustomerForm | None, dict[str, str]]`**: maps Pydantic errors to `{field: message}`
- [X] T042 [US1] Implement `src/floorpro/services/customer_service.py` (US1 part).

  **`create(session, form) -> tuple[Customer, list[str]]`** (the list holds warnings):
  - sets `mobile_phone_digits`/`other_phone_digits` via `phone_digits`
  - sets `postcode` and `postcode_compact` via `normalise_postcode` and `postcode_compact`, adding a postcode warning when needed
  - sets `created_at`/`updated_at` to `utcnow()`
  - flushes so `id` (and therefore `reference`) is assigned

  **Other functions**:
  - `find_duplicates(session, phones, email, exclude_id=None)`: matches either `*_phone_digits` column or `email` (NOCASE), and includes archived customers
  - `search(session, q, customer_type="all", archived=False, sort="name", direction="asc", limit=50) -> tuple[list[Customer], int]`, per research.md §5:
    - the digits of `q` match the phone digit columns
    - the compact form of `q` matches `postcode_compact`
    - `LIKE %q%` matches last name, first name, company and email
    - if `q` matches `^c-?0*(\d+)$` (case-insensitive), it also matches `Customer.id == int(group)`
    - sort by name uses `sort_name` ordering (`COALESCE(last_name, company_name), first_name`)
  - `get(session, id) -> Customer | None`
- [X] T043 [US1] Create `src/floorpro/routes/customers.py` with these US1 routes, per contracts/routes.md:
  - **`GET /customers`**: query `q`, `type`, `archived`, `sort`, `dir`. Returns the full page or `_results.html`
  - **`GET /customers/new`**: `prefill` heuristic: digits go to `mobile_phone`, text containing `@` goes to `email`, otherwise the text is split into first and last name
  - **`POST /customers`**: 422 form on errors, the duplicate panel unless `confirm_duplicate=1`. On success with the toast "Customer {ref} added" (plus any postcode warning): for HTMX, render the record page with `push_url=f"/customers/{id}"`; for a plain request, use `flash_redirect`
  - **`GET /customers/{id}`**: 404 when missing
  - register the router in `src/floorpro/app.py`
- [X] T044 [P] [US1] Create the list templates:
  - **`src/floorpro/templates/customers/index.html`**: page heading, "Add customer" button, a search `<input type="search" name="q">` with `hx-get="/customers"`, `hx-trigger="input changed delay:250ms, search"`, `hx-target="#results"` and `hx-push-url="true"`, a "Show archived" toggle and sortable column headers
  - **`src/floorpro/templates/customers/_results.html`**: rows with reference, display name, phone, postcode and email linking to the record, a "Showing X of N" line, and the `empty_state` with "Add '{q}' as a new customer"
- [X] T045 [P] [US1] Create the form templates:
  - **`src/floorpro/templates/customers/form.html`** and **`src/floorpro/templates/customers/_form.html`**: grouped sections (Name, Contact, Address, Notes and preferences) built from the `field`/`checkbox` macros, with `data-guard-unsaved` on the form. Inline errors and the postcode warning are shown, and entered values are kept on 422
  - **`src/floorpro/templates/customers/_duplicates.html`**: a warning panel listing the matches (reference, name, matching phone/email, an "Open" link) and a "Save anyway" button that resubmits the form with `confirm_duplicate=1`
- [X] T046 [P] [US1] Create `src/floorpro/templates/customers/detail.html`:
  - header with the display name and reference
  - contact, address and notes cards
  - "Added" and "Last updated" times via `local_datetime`
  - a "Jobs, orders, appointments and invoices" card using `empty_state` with "These will appear here once those features are available." (FR-022)
- [X] T047 [US1] Write `tests/integration/test_customers_perf.py`, marked `@pytest.mark.slow`:
  - bulk-insert 10,000 customers with varied names, phones and postcodes (Core `insert` with the derived columns precomputed)
  - for 5 different query types, assert the median elapsed time of `GET /customers?q=…` with the `htmx` headers is under 0.3 s (SC-002, constitution under 300 ms)

**Checkpoint**: The US1 MVP is usable. Add, find and view customers in the desktop window.

---

## Phase 4: User Story 2 - Set currency and VAT (Priority: P2)

**Goal**: The Settings screen with the GBP / 20% / VAT-registered / "prices include VAT"
defaults. Changes are validated and confirmed, and recorded in a date-stamped history.

**Independent Test**: Fresh install → confirm defaults → change each setting → restart → values
kept and history listed (quickstart.md §A).

### Tests for User Story 2 ⚠️ Write first, confirm they fail

- [X] T048 [P] [US2] Write `tests/unit/test_validation_vat.py`.

  **`validate_vat_rate`**:
  - accepts `"20"` → `Decimal("20.00")`, `"17.5"` → `Decimal("17.50")`, and `"0"` and `"100"`
  - rejects `"-5"`, `"150"`, `"abc"` and `"12.345"`, each with "Enter a VAT rate between 0 and 100, with up to two decimal places."

  **`normalise_vat_number`**:
  - `"gb 123 4567 89"` → `"GB123456789"`
  - accepts `"GB123456789012"`, `"GBGD001"` and `"GBHA599"`
  - rejects `"GB12"` and `"123456789"`, each with "Enter a UK VAT number, for example GB123456789."
- [X] T049 [P] [US2] Write `tests/unit/test_settings_at.py` for the pure function `settings_at(defaults, changes, when)` in `floorpro.domain.settings_history`:
  - with no changes, it returns the defaults
  - changes are applied in `changed_at` order up to and including `when`
  - later changes are ignored
  - several fields in one change set are applied together
- [X] T050 [P] [US2] Write `tests/integration/test_settings.py`, covering spec scenarios 2.1–2.7 and contracts/routes.md.

  **Defaults**:
  - `GET /settings` shows GBP, VAT registered, 20 and "Prices include VAT"

  **Confirm flow**:
  - `POST /settings` with rate 17.5 returns the dialog containing "20% → 17.5%" and "applies to new quotes and invoices only", and doesn't save yet
  - `POST /settings/confirm` with the returned token saves, shows the "Settings saved" toast, and adds one `settings_change` row with `old_value="20.00"` and `new_value="17.50"`
  - several changes in one save share a `change_set_id`

  **Validation and special cases**:
  - invalid rates return 422 with the exact message
  - when not VAT registered, the rate and number aren't required
  - changing the currency to EUR makes the `money` filter render `€`
  - a price entry mode change is recorded
  - an unchanged POST shows the "Nothing to change" toast
  - a stale token (settings changed after staging) returns 409

  **Persistence and history**:
  - values persist across a new `create_app` on the same `data_dir`
  - `GET /settings/history` lists the changes, newest first

  **Form behaviour**:
  - an invalid `POST /settings` returns 422 with the headers `HX-Retarget: #settings-form` and `HX-Reswap: outerHTML`
  - `GET /settings/form/vat-fields` with `vat_registered` unticked returns disabled rate/number fields with "Not applicable — business isn't VAT registered" and hidden inputs holding the current values. With `vat_registered=on` the fields are enabled

### Implementation for User Story 2

- [X] T051 [US2] Implement `validate_vat_rate` and `normalise_vat_number` in `src/floorpro/domain/validation.py` so T048 passes:
  - **VAT rate**: uses `percent_to_bp` rules, range 0–100, at most 2 dp
  - **VAT number**: regex `^GB(\d{9}|\d{12}|GD\d{3}|HA\d{3})$` after removing whitespace and upper-casing
- [X] T052 [US2] Implement `src/floorpro/domain/settings_history.py` so T049 passes:
  - a `SettingsSnapshot` dataclass
  - `settings_at(defaults, changes, when)`
  - `canonical(field, value) -> str`: `"20.00"` for rates, `"true"`/`"false"`, the code or mode string, or `None`
- [X] T053 [US2] Create `src/floorpro/schemas/settings_form.py` with a Pydantic `SettingsForm`:
  - **`currency_code`**: must be in `SUPPORTED_CURRENCIES`, otherwise "Choose a currency from the list."
  - **`vat_registered`**: checkbox
  - **`vat_rate`**: required and validated only when registered
  - **`vat_number`**: optional, normalised and validated when present and registered
  - **`price_entry_mode`**: `inc_vat|ex_vat`
  - **`from_form`**: returns `(form, errors)`
- [X] T054 [US2] Extend `src/floorpro/services/settings_service.py`:
  - **`diff(current, form)`**: returns a list of `(field, old_canonical, new_canonical)`
  - **`make_token(form, current)`**: HMAC-SHA256 with `paths.secret_key()` over the staged canonical values plus `current.updated_at.isoformat()`. Add a matching `verify_token`
  - **`apply(session, form)`**: in one transaction, updates the row, sets `updated_at`, and inserts one `SettingsChange` per changed field with a shared `uuid4` `change_set_id` and the same `changed_at`
  - **`history(session, page=1, per_page=25)`**: newest first
  - **`settings_at(session, when)`**: delegates to the domain function
- [X] T055 [US2] Create `src/floorpro/routes/settings.py`, per contracts/routes.md:
  - **`GET /settings`**: the form plus the last 10 history rows
  - **`POST /settings`**: 422 on errors, with the headers `HX-Retarget: #settings-form` and `HX-Reswap: outerHTML`. The "Nothing to change" toast when there's no diff, otherwise a 200 `_confirm.html` dialog into `#modal` with hidden staged fields and the token
  - **`POST /settings/confirm`**: 409 on a bad token, otherwise apply and show the "Settings saved" toast (HTMX: render the settings page with `push_url="/settings"`; plain request: `flash_redirect`)
  - **`GET /settings/history`**: paginated
  - **`GET /settings/form/vat-fields`**: renders `_vat_fields.html` from `vat_registered`, `vat_rate` and `vat_number`
  - register the router in `src/floorpro/app.py`
- [X] T056 [P] [US2] Create the settings templates:
  - **`src/floorpro/templates/settings/index.html`** and **`src/floorpro/templates/settings/_form.html`**:
    - the `<form id="settings-form">` has `hx-post="/settings"`, `hx-target="#modal"` and `hx-swap="innerHTML"`
    - currency select showing the symbol and name
    - "VAT registered" checkbox with `hx-get="/settings/form/vat-fields"`, `hx-trigger="change"`, `hx-target="#vat-fields"` and `hx-include="closest form"`
  - **`src/floorpro/templates/settings/_vat_fields.html`** (`id="vat-fields"`): VAT rate input with a `%` suffix and VAT number field. When not registered, both are disabled with the hint "Not applicable — business isn't VAT registered", and hidden inputs keep the current values
  - **`src/floorpro/templates/settings/_form.html`** (continued):
    - price entry mode radio: "Prices include VAT" / "Prices exclude VAT", with a one-line explanation of each
  - **`src/floorpro/templates/settings/_confirm.html`**: a `modal` macro listing "Field: old → new" and the notice "These changes apply to new quotes and invoices only. Existing documents keep the values they were created with.", with Confirm and Cancel buttons
  - **`src/floorpro/templates/settings/_history.html`**: a table of date/time (local), setting, old and new values

**Checkpoint**: US1 and US2 both work on their own.

---

## Phase 5: User Story 3 - Update, archive and manage customer data (Priority: P3)

**Goal**: Edit customers, archive and restore them, export one customer's data as JSON, and
erase a customer with a typed-name confirmation.

**Independent Test**: Edit, archive/restore, export and erase customers, and verify each result
(quickstart.md §D).

### Tests for User Story 3 ⚠️ Write first, confirm they fail

- [X] T057 [P] [US3] Write `tests/integration/test_customers_edit.py` (spec scenario 3.1):
  - `GET /customers/{id}/edit` is pre-filled
  - `POST /customers/{id}` with a new phone number saves it, updates `updated_at` and shows the "Customer updated" toast
  - a validation error returns 422
  - the duplicate check runs only when a phone or email changed (editing notes on a customer who shares a phone with another doesn't warn)
  - an unknown id returns 404
- [X] T058 [P] [US3] Write `tests/integration/test_customers_archive.py` (spec scenario 3.2):
  - `GET /customers/{id}/archive` returns the dialog
  - `POST` archives: `is_archived`, `archived_at` set, the archived badge on the record, and the customer drops out of the default list and appears with `archived=1`
  - `POST /customers/{id}/restore` clears both
  - an archived customer still triggers the duplicate warning
- [X] T059 [P] [US3] Write `tests/integration/test_customers_export.py`, per contracts/customer-export.md (scenario 3.3):
  - `GET /customers/{id}/export` returns `application/json` with `Content-Disposition: attachment; filename="FloorPro-customer-C-00001-YYYY-MM-DD.json"`
  - the body parses as JSON with `export.format_version == 1`
  - `customer.reference` is present, and every `customer` table column except `id`, `mobile_phone_digits`, `other_phone_digits` and `postcode_compact` is present, with the address nested under `address`
  - timestamps end in `Z`
  - `related_records` has empty `jobs`, `orders`, `appointments` and `invoices`
- [X] T060 [P] [US3] Write `tests/integration/test_customers_erase.py` (scenario 3.4):
  - `GET /customers/{id}/erase` returns the dialog containing "Type Jane Smith to confirm"
  - a wrong name returns 422 with "The name doesn't match.", the headers `HX-Retarget: #modal` and `HX-Reswap: innerHTML`, and keeps the row
  - `"  jane smith "` deletes the row, shows `/customers` with an `HX-Push-Url: /customers` header, and shows the "Customer erased" toast
  - for a customer with company "Acme Flooring" and person "Jane Smith", the confirmation is accepted with `acme flooring` or `jane smith`
  - a customer created afterwards gets `C-00002`, not `C-00001` (FR-013)

### Implementation for User Story 3

- [X] T061 [US3] Extend `src/floorpro/services/customer_service.py`:
  - **`update(session, customer, form) -> list[str]`**: recomputes the derived columns and `updated_at`
  - **`phones_or_email_changed(customer, form) -> bool`**
  - **`archive(session, customer)`** and **`restore(session, customer)`**
  - **`export_dict(customer) -> dict`**: exactly the contracts/customer-export.md shape
  - **`has_linked_records(session, customer) -> bool`**: returns `False`, with a docstring explaining that it's extended when jobs/orders/invoices exist (research.md §12)
  - **`erase(session, customer, confirm_name) -> bool`**: compares the name with trim and `casefold` against the company name, "First Last" and `display_name` (any of them confirms). Hard-deletes when there are no linked records, otherwise raises `NotImplementedError("anonymise — implemented with first linked-records feature")`
- [X] T062 [US3] Add the US3 routes to `src/floorpro/routes/customers.py`, per contracts/routes.md. Every successful write responds per "Success after a write": HTMX renders the destination page with `push_url` and the toast, and a plain request uses `flash_redirect`:
  - **Edit**: `GET /customers/{id}/edit` and `POST /customers/{id}` (the duplicate check only when `phones_or_email_changed`)
  - **Archive and restore**: `GET`/`POST /customers/{id}/archive` and `POST /customers/{id}/restore`
  - **Export**: `GET /customers/{id}/export`, a `JSONResponse` with `indent=2`, `ensure_ascii=False` and the `Content-Disposition` header
  - **Erase**: `GET`/`POST /customers/{id}/erase`. A wrong name returns 422 with the headers `HX-Retarget: #modal` and `HX-Reswap: innerHTML`
- [X] T063 [P] [US3] Create the archive and erase dialogs, both using the `modal` macro:
  - **`src/floorpro/templates/customers/_confirm_archive.html`**: "Archive {name}? They'll be hidden from the customer list but kept, and you can restore them at any time."
  - **`src/floorpro/templates/customers/_confirm_erase.html`**: an explanation that this permanently deletes their details, a `confirm_name` input labelled "Type {display_name} to confirm", and a danger button
  - the forms inside both dialogs are plain `<form method="post">` elements, boosted by `hx-boost`, so a successful response replaces the whole page (closing the dialog). On a 422 (wrong name), the erase route sets `HX-Retarget: #modal` and `HX-Reswap: innerHTML` so the dialog is re-rendered with the error
- [X] T064 [US3] Update the customer record and form templates:
  - **`src/floorpro/templates/customers/detail.html`**: add the action bar (Edit, Archive/Restore depending on state, Export data, Erase in danger style) and the "Archived" badge with the archived date
    - the Archive and Erase buttons use `hx-get="/customers/{id}/archive"` or `"/customers/{id}/erase"` with `hx-target="#modal"` and `hx-swap="innerHTML"`
    - Restore is a plain boosted `<form method="post" action="/customers/{id}/restore">` with a single button
    - the Export data link is a plain `<a href="/customers/{id}/export" hx-boost="false">` so the webview downloads the file
  - **`src/floorpro/templates/customers/_form.html`**: support edit mode (title "Edit customer", posts to `/customers/{id}`)

**Checkpoint**: US1–US3 all work on their own.

---

## Phase 6: User Story 4 - Domestic and trade customers (Priority: P3)

**Goal**: Each customer is domestic or trade, with a "show VAT breakdown" preference. It's
locked on for trade customers and optional for domestic ones. The list can be filtered and
shows type badges.

**Independent Test**: Create one domestic and one trade customer. Check the types and
preferences, the filter, and that trade can't turn the breakdown off (quickstart.md §C).

### Tests for User Story 4 ⚠️ Write first, confirm they fail

- [X] T065 [P] [US4] Write `tests/unit/test_vat_breakdown.py`, covering every row of the data-model.md "Customer type rules" table for `resolve_vat_breakdown(old_type, new_type, requested)`:
  - `(None, "domestic", None)` → `False`
  - `(None, "trade", False)` → `True`
  - `("domestic", "trade", False)` → `True`
  - `("trade", "domestic", None)` → `True` (stays on)
  - `("trade", "domestic", False)` → `False` (an explicit untick once it's editable)
  - `("domestic", "domestic", True)` → `True`
- [X] T066 [P] [US4] Write `tests/integration/test_customer_types.py`, covering spec scenarios 4.1–4.5.

  **Saving types**:
  - a new customer saved without a type is domestic with the breakdown off
  - posting `customer_type=trade` without the checkbox saves the breakdown as on (enforced by the server)
  - a domestic customer can save the breakdown on
  - changing domestic → trade locks it on
  - changing trade → domestic keeps it on and lets a later untick save it as off

  **VAT fields partial**:
  - `GET /customers/form/vat-fields?customer_type=trade` returns the checkbox checked and `disabled`, a hidden `show_vat_breakdown=on`, and the text "Always shown for trade customers"

  **Form**:
  - `GET /customers/new` with the trade type selected renders the company/trading name field in the Name section, before the first name field (FR-029)

  **List**:
  - `GET /customers?type=trade` returns only trade customers
  - result rows show a "Trade"/"Domestic" badge

### Implementation for User Story 4

- [X] T067 [US4] Implement `resolve_vat_breakdown(old_type: str | None, new_type: str, requested: bool | None) -> bool` in `src/floorpro/domain/customers.py` so T065 passes:
  - trade always returns `True`
  - for domestic, an explicit `requested` wins
  - when `requested is None`, the previous value is kept, or `False` for a new customer
- [X] T068 [US4] Update `src/floorpro/services/customer_service.py`:
  - `create` and `update` set `show_vat_breakdown = resolve_vat_breakdown(old_type, form.customer_type, form.show_vat_breakdown)`
  - implement the `customer_type` filter in `search` (`all`/`domestic`/`trade`), using the `(is_archived, customer_type)` index
- [X] T069 [US4] Update `src/floorpro/routes/customers.py`:
  - add `GET /customers/form/vat-fields`, which renders `_vat_fields.html` from `customer_type`, `show_vat_breakdown` and `original_type`
  - pass the `type` query parameter through `GET /customers`
- [X] T070 [P] [US4] Update the templates for customer types:
  - **`src/floorpro/templates/customers/_vat_fields.html`**: the "Show VAT breakdown on quotes and invoices" checkbox. For trade it's checked and disabled, with a hidden `on` value and the hint "Always shown for trade customers". For domestic the hint is "Turn on for customers who need VAT shown separately, e.g. insurance jobs."
  - **`src/floorpro/templates/customers/_form.html`**: a Domestic/Trade segmented radio at the top that triggers `hx-get="/customers/form/vat-fields"` into the VAT fields group, and moves the company/trading name field into the Name section when Trade is selected
  - **`src/floorpro/templates/customers/index.html`**: an All/Domestic/Trade filter control wired to `type`
  - **`src/floorpro/templates/customers/_results.html`**: a type badge on each row
  - **`src/floorpro/templates/customers/detail.html`**: the type badge and the VAT breakdown preference

**Checkpoint**: All four user stories work on their own.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T071 [P] Write `tests/integration/test_assets.py`:
  - rendered `base.html` contains no `http://` or `https://` in any `src` or `href` (no CDN, Principle IV)
  - `src/floorpro/static/js/app.js` is under 40 non-blank lines
  - `/static/vendor/htmx.min.js` is served
- [ ] T072 [P] Create `README.md` at the repository root: what FloorPro is, prerequisites, setup and run commands (link to `specs/001-settings-customer-records/quickstart.md`), and where the data is stored.
- [ ] T073 Accessibility pass across `src/floorpro/templates/`:
  - every input has a `<label>`, and errors are linked via `aria-describedby`
  - focus is visible on every interactive element
  - dialogs trap focus and close on Escape
  - the `#toasts` region is `aria-live`
  - token colour pairs in `src/floorpro/static/css/input.css` are checked at 4.5:1 or better
- [ ] T074 Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest` locally and fix any failures. Then push and confirm both the `macos-latest` and `windows-latest` CI jobs pass.
- [ ] T075 Run the quickstart.md manual scenarios A–D, including §B.8 (unsaved changes) and §B.9 (persistence), in the desktop window (`uv run python -m floorpro`) on macOS, and record any deviations as follow-up issues.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T001 → T002 first, then T003–T008 in parallel.
- **Foundational (Phase 2)**: depends on Setup. It blocks all user stories. Internal order:
  1. T009–T011 and T013 in parallel
  2. T012 after T011, and T014 after T013
  3. T015 after T012
  4. T016 and T017 in parallel
  5. T018 → T019 → T020 → T021
  6. T022 → T023 → T024
  7. T025–T029 in parallel
  8. T030 → T031
  9. T032 → T033
- **US1 (Phase 3)**: after Phase 2. No dependency on other stories.
- **US2 (Phase 4)**: after Phase 2. Independent of US1 (it shares only `domain/validation.py`
  with US1, so edit that file sequentially).
- **US3 (Phase 5)**: after US1, because it extends the customer service, routes and
  templates.
- **US4 (Phase 6)**: after US1, because it extends the customer form, search and templates.
  It's independent of US3, but both edit `customer_service.py`, `routes/customers.py`,
  `_form.html` and `detail.html`, so do them one after the other.
- **Polish (Phase 7)**: after the desired stories are complete.

### Within Each User Story

- Tests are written first and must **fail** before implementation (Principle III)
- Domain functions → schemas → services → routes → templates
- Each story should be committed at its checkpoint

### Parallel Opportunities

- Setup: T003–T008
- Foundational: T009/T010/T011/T013, T016/T017, T025/T026/T028/T029
- US1: T034–T038 (all tests) together, then T044/T045/T046 (templates) together after T043
- US2: T048–T050 together, and T056 alongside T055. US2 as a whole can run alongside US1
- US3: T057–T060 together, and T063 alongside T062
- US4: T065/T066 together, and T070 alongside T069

---

## Parallel Example: User Story 1

```bash
# Write all US1 tests together (they must fail):
Task: "T034 Unit tests for postcode/phone/email validation in tests/unit/test_validation_customer.py"
Task: "T035 Unit tests for display_name/sort_name in tests/unit/test_customers_domain.py"
Task: "T036 Integration tests for POST /customers in tests/integration/test_customers_create.py"
Task: "T037 Integration tests for GET /customers search in tests/integration/test_customers_search.py"
Task: "T038 Integration tests for GET /customers/new in tests/integration/test_customers_new.py"

# After routes (T043), build the templates together:
Task: "T044 customers/index.html + _results.html"
Task: "T045 customers/form.html + _form.html + _duplicates.html"
Task: "T046 customers/detail.html"
```

## Parallel Example: User Story 2

```bash
Task: "T048 tests/unit/test_validation_vat.py"
Task: "T049 tests/unit/test_settings_at.py"
Task: "T050 tests/integration/test_settings.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup → Phase 2: Foundational. At the end, the app opens, CI is green on macOS
   and Windows, and the dashboard is styled.
2. Phase 3: US1. Add and find customers.
3. **Stop and validate**: quickstart.md §B in the desktop window. Commit and push.

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. \+ US1 → MVP (customers usable)
3. \+ US2 → settings (currency, VAT, price entry mode)
4. \+ US3 → edit, archive, export, erase
5. \+ US4 → domestic and trade types
6. Polish → README, accessibility, CI confirmation, manual quickstart run

Each increment is committed and pushed, so CI checks it on both operating systems.

---

## Notes

- [P] = different files, no dependency on incomplete tasks
- Exact user-facing messages in these tasks are test fixtures. Keep the wording in sync
  between the templates/schemas and the tests.
- Never use `float` for money or percentages (Principle II). Use `Decimal` from
  `floorpro.domain.money`.
- Only `desktop.py` imports `webview`. Tests must never need a GUI.
