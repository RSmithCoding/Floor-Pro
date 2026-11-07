# FloorPro Constitution

## Core Principles

### I. Local-First & Data Safety

FloorPro is a desktop application that a flooring shop relies on to run its day.
Its data belongs to the shop and MUST stay safe on the shop's own machine.

- All business data (customers, jobs, orders, appointments, invoices) MUST be stored in a
  local SQLite database. Core features MUST work fully offline; no feature may require an
  internet connection or a third-party cloud service to function.
- Every database schema change MUST ship as an Alembic migration that upgrades existing data
  without loss. Hand-editing a production schema is prohibited.
- The application MUST provide a backup and restore mechanism for the database. Migrations MUST
  take an automatic backup before they run.
- Destructive actions (deleting a customer, job, or invoice) MUST require explicit confirmation
  in the UI. Records referenced by invoices MUST be archived rather than hard-deleted.
- Customer personal data MUST be exportable and erasable on request, so the shop can
  meet its data-protection obligations.

**Rationale**: A lost or corrupted database means lost bookings, unpaid invoices and lost
customer history. Shops can't depend on a network connection or a vendor's servers.

### II. Money & Measurement Accuracy (NON-NEGOTIABLE)

Quotes and invoices are legal and financial documents. A wrong number costs the shop money
and trust.

- Monetary values MUST use `decimal.Decimal` in Python and be stored as `Numeric` columns
  (or integer minor units). Floating-point types MUST NOT be used for money anywhere.
- Rounding rules (mode, precision, and whether tax rounds per line or per invoice) MUST be
  defined in exactly one module and used by every calculation.
- All measurements MUST be metric. Lengths are stored in millimetres and areas in square
  metres (as `Decimal`), with the unit named in the field or type. Imperial units MUST NOT be
  accepted or displayed.
- Area, waste allowance, pack/roll-quantity and price calculations MUST live in pure,
  side-effect-free functions with no database or web dependencies.
- Issued invoices MUST be immutable and sequentially numbered with no gaps or reuse.
  Corrections MUST be made through credit notes or a new invoice, never by editing an
  issued one.
- Currency and VAT MUST be settings the user can change in the app's Settings screen, never
  hard-coded constants. Defaults on first run are GBP (£) and VAT at 20%.
- Changing the currency or VAT rate MUST affect only new quotes and invoices. Every quote and
  invoice MUST store the currency and VAT rate used when it was created, so historic documents
  never change.

**Rationale**: Calculation errors show up directly in a customer's bill. Isolating and
standardising the maths makes it provable and auditable.

### III. Test-First Business Logic

- Calculation, invoicing, pricing, and scheduling logic (including appointment conflict
  detection) MUST be developed test-first: write a failing pytest test, then implement, then
  refactor.
- Every route MUST have at least one integration test using FastAPI's `TestClient` against a
  temporary SQLite database.
- Every migration MUST be tested by upgrading a database seeded with representative data.
- A bug fix MUST include a regression test that fails before the fix.
- The full test suite MUST pass before work is merged or packaged.

**Rationale**: These areas carry financial and operational risk. Tests are the only reliable
proof that they're still correct after every change.

### IV. Python-Only, Server-Rendered UI

- Python is the only application language. The backend is FastAPI with SQLAlchemy over SQLite.
- The UI MUST be server-rendered with Jinja2 templates. HTMX handles interactivity and Tailwind
  CSS handles styling. SPA frameworks (React, Vue, Svelte, etc.) MUST NOT be introduced.
- Hand-written JavaScript MUST be kept to a minimum. Any custom script MUST be justified in the
  feature plan and kept small and local to the component that needs it.
- All front-end assets (HTMX, compiled Tailwind CSS, fonts, icons) MUST be bundled locally.
  Nothing may load from a CDN at runtime.
- Tailwind CSS MUST be compiled at build time. The shipped app MUST NOT need Node.js at
  runtime.

**Rationale**: A single language and a server-rendered UI keep the codebase small and easy to
debug. Bundled assets keep the app working offline and inside a PyInstaller build.

### V. Consistent, Polished User Experience

FloorPro MUST feel like a modern, sleek product that shop staff enjoy using all day.

- Every screen MUST be built from a shared library of Jinja macros/partials (buttons, forms,
  tables, cards, modals, empty states) and shared design tokens (colours, spacing,
  typography). One-off styling of common elements is prohibited.
- The dashboard is the home screen. It MUST show upcoming appointments and other time-critical
  information (e.g. outstanding invoices, today's fittings) at a glance.
- Core workflows (new customer → estimate booking → quote → job → fitting → invoice) MUST flow
  naturally from one step to the next. Context MUST carry forward so data is never re-entered.
- Every user action MUST give immediate visible feedback: loading indicators for HTMX
  requests, success confirmations, and clear human-readable error messages. Raw stack traces
  MUST NOT be shown to users.
- Pages and HTMX partials MUST respond in under 300 ms on a typical shop PC with several years
  of data.
- The UI MUST be usable at common laptop and desktop window sizes and meet WCAG 2.1 AA colour
  contrast.

**Rationale**: For a shop, a consistent, fast and predictable app means fewer mistakes and
faster service at the counter.

### VI. Simplicity & Layered Architecture

- Code MUST follow a clear layering. Routes handle HTTP and templates only. Services hold the
  business logic. SQLAlchemy models and repositories handle persistence. Pure domain functions
  handle calculations. Business logic MUST NOT live in routes or templates.
- The app runs as a single local process. Background workers, message queues, separate
  services and external databases MUST NOT be introduced without a written justification in
  the feature plan.
- Build only what a current spec requires (YAGNI). Any added complexity MUST be recorded and
  justified in the plan's Complexity Tracking section.
- New third-party dependencies MUST be justified and MUST be compatible with PyInstaller
  packaging.

**Rationale**: FloorPro is an "everything" app for the business. Strict layering and
restraint keep a growing feature set maintainable.

## Technology & Platform Constraints

- **Language & runtime**: Python 3.12+. Dependencies are pinned in a lock file.
- **Backend**: FastAPI, SQLAlchemy 2.x (typed ORM style), Alembic for migrations, SQLite.
- **Frontend**: Jinja2, HTMX, Tailwind CSS (compiled at build time).
- **Desktop shell**: The FastAPI server MUST bind only to `127.0.0.1` on a free port and be
  shown inside a native pywebview window. It MUST NOT be reachable from the network.
- **Packaging**: The app is distributed as a PyInstaller build. Code MUST resolve bundled
  resources (templates, static files, migrations) through a single path helper that works in
  both development and frozen builds.
- **Data location**: The database, backups and logs MUST live in the operating system's
  per-user application-data directory. They MUST NOT live beside the executable or in the
  working directory.
- **Logging**: Errors MUST be written to a rotating local log file with enough context to
  diagnose a shop's problem without exposing customer data unnecessarily.
- **Target platforms**: The finished product MUST run on both Windows and macOS, with separate
  PyInstaller builds for each. Development and day-to-day testing happen on macOS.
- **Cross-platform code**: File paths MUST use `pathlib`. App-data locations MUST come from a
  cross-platform library (e.g. `platformdirs`). Code MUST NOT assume a case-sensitive
  filesystem, a particular path separator or line ending, or a shell. Platform-specific code
  MUST be isolated behind one module and covered by tests on both operating systems.
- **Currency, tax & units**: GBP and 20% VAT by default, editable in Settings. Measurements
  are metric only (see Principle II).

## Development Workflow & Quality Gates

- Source code lives in a GitHub repository. GitHub Actions MUST run linting and the full test
  suite on both macOS and Windows for every push and pull request. CI is how Windows is tested
  while no Windows machine is available.
- Features follow the Spec Kit flow: `/speckit-specify` → `/speckit-clarify` (as needed) →
  `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.
- Every plan MUST complete the Constitution Check. Any principle a plan breaks MUST be
  justified in Complexity Tracking or the plan MUST be revised.
- Before a change is considered done:
  1. `ruff check` and `ruff format --check` pass.
  2. The full pytest suite passes on macOS and Windows CI, including migration tests.
  3. Any schema change includes an Alembic migration.
  4. UI changes are checked manually in the pywebview window and reuse the shared
     components.
  5. Money, measurement, invoicing or scheduling changes include test-first coverage per
     Principle III.
- Each release candidate MUST be smoke-tested as a PyInstaller build on a clean machine
  (launch, open the dashboard, create a customer, book an appointment, issue an invoice,
  back up and restore). The Windows build MUST be produced by CI and pass this smoke test on a
  real Windows machine or a Windows virtual machine before it's released to any shop.

## Governance

- This constitution supersedes all other development practices for FloorPro. Specs, plans and
  tasks MUST comply with it.
- Amendments MUST be made through `/speckit-constitution`. Each amendment MUST record its
  rationale in the Sync Impact Report and update the version below.
- Versioning follows semantic versioning:
  - **MAJOR**: a principle is removed or redefined in a backward-incompatible way.
  - **MINOR**: a principle or section is added or guidance is materially expanded.
  - **PATCH**: clarifications and wording fixes with no change in meaning.
- Compliance is reviewed at plan time (Constitution Check) and again before each release.
  Any deviation MUST be justified in writing. Otherwise it MUST be fixed before release.

**Version**: 1.1.0 | **Ratified**: 2026-11-07 | **Last Amended**: 2026-11-07
