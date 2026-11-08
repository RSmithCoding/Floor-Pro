# Implementation Plan: Currency & VAT Settings and Customer Records

**Branch**: `main` (no feature branch; Spec Kit labels it `001-settings-customer-records`) |
**Date**: 2026-11-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-settings-customer-records/spec.md`

## Summary

This feature lets shop staff add, find, edit, archive, export and erase customer records, and
mark each customer as domestic or trade. Trade customers always get a VAT breakdown, and
domestic customers can opt in. It also lets the owner set currency (default GBP), VAT
registration, VAT rate (default 20%), VAT number and price entry mode (default "prices include
VAT"), with a confirmed, date-stamped change history.

Because this is FloorPro's first feature, it also builds the foundations every later feature
relies on:
- the pywebview + local FastAPI desktop shell
- the SQLite database with Alembic migrations and an automatic backup before each migration
- the Jinja/HTMX/Tailwind component library and app layout, with a minimal dashboard as the
  home screen
- the exact-money and percentage types
- the pytest suite and the macOS + Windows GitHub Actions CI

The technical approach is in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.13 (managed by uv, pinned in `.python-version`)

**Primary Dependencies**: FastAPI, Uvicorn, SQLAlchemy 2.x, Alembic, Jinja2, Pydantic v2 +
`email-validator`, `python-multipart`, `platformdirs`, pywebview 5.x. Front end: HTMX 2.x
(vendored) and the Tailwind CSS v4 standalone CLI (build time only).

**Storage**: SQLite file in the per-user app-data directory (WAL mode). Money is stored as
integer minor units and percentages as integer basis points.

**Testing**: pytest (+ httpx through FastAPI `TestClient`). Ruff for lint and format.

**Target Platform**: Desktop on macOS (developed on macOS 12, Intel) and Windows 10/11
(WebView2). CI runs on both.

**Project Type**: Desktop app (local web server rendered in a native window), single Python
package.

**Performance Goals**: Pages and HTMX partials respond in under 300 ms. Search returns within
1 s of typing with 10,000 customers (target under 300 ms).

**Constraints**: Fully offline. Bound to `127.0.0.1` only. No CDN or Node at runtime. Must work
when frozen by PyInstaller (resources resolved through one path helper). No floats for money.

**Scale/Scope**: One shop per install, up to about 10,000 customers. About 12 screens and
partials in this feature.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle / rule | How this plan complies | Pre-design | Post-design |
|---|------------------|------------------------|:---------:|:-----------:|
| I | Local-first, offline | SQLite in `platformdirs` user data dir. No network calls (email DNS checks off) | ✅ | ✅ |
| I | Schema changes via Alembic, no data loss | `0001_initial` migration. Migrations run at startup | ✅ | ✅ |
| I | Backup & restore. Auto backup before migrations | Pre-migration backup delivered here. **User-facing backup/restore is a later feature** (scope note, not a violation: no user data is at risk before this feature ships). **Release blocker**: backup and restore must ship before the first release to any shop. Tracked as the next feature spec after this one | ✅ | ✅ |
| I | Confirm destructive actions. Archive vs delete | `<dialog>` confirmations for archive/erase. Erase requires typing the name | ✅ | ✅ |
| I | Personal data exportable & erasable | `GET /customers/{id}/export` (JSON contract) and erase flow | ✅ | ✅ |
| II | `Decimal`, no floats. One rounding module | `domain/money.py` + `Money`/`Percent` TypeDecorators over integers | ✅ | ✅ |
| II | Metric units | No measurements in this feature. Nothing to violate | ✅ | ✅ |
| II | Currency & VAT editable, default GBP/20%. History for documents | Settings screen, defaults, `settings_change` log. Document snapshots come with invoicing | ✅ | ✅ |
| III | Test-first for calculation/rules | Validation, normalisation, percent parsing, `resolve_vat_breakdown`, settings-at-date: unit tests written first | ✅ | ✅ |
| III | Integration test per route. Migration tests | `tests/integration/` covers every route in [contracts/routes.md](contracts/routes.md). `tests/migrations/` | ✅ | ✅ |
| IV | Python only. Jinja + HTMX + Tailwind. No SPA | Yes | ✅ | ✅ |
| IV | Minimal, justified custom JS | `static/js/app.js` (under 40 lines): open `<dialog>` modals and the unsaved-changes guard. Justified in research §7 | ✅ | ✅ |
| IV | Assets bundled locally. Tailwind built at build time | HTMX vendored. Tailwind standalone CLI. Compiled CSS generated | ✅ | ✅ |
| V | Shared components & tokens | `templates/components/` macros. `@theme` tokens in `input.css` | ✅ | ✅ |
| V | Dashboard is home | `/` dashboard shell (placeholders for future appointments/invoices) | ✅ | ✅ |
| V | Feedback, friendly errors, under 300 ms, WCAG AA | OOB toasts, inline errors, custom 404/500 pages, perf test, contrast-checked tokens | ✅ | ✅ |
| VI | Layering: routes → services → models. Pure domain | See structure below. No business logic in routes or templates | ✅ | ✅ |
| VI | Single process. Justified dependencies | One process (uvicorn thread + webview). Every dependency is PyInstaller-compatible | ✅ | ✅ |
| Platform | `127.0.0.1` + free port. Path helper. App-data dir. `pathlib`. Rotating logs | `desktop.py`, `paths.py`, `logging_setup.py` | ✅ | ✅ |
| Workflow | CI on macOS + Windows. Ruff. pytest | `.github/workflows/ci.yml` matrix | ✅ | ✅ |

**Gate result**: PASS before and after design. No violations need Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-settings-customer-records/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── routes.md            # UI/HTTP route contract
│   └── customer-export.md   # Export file format
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
pyproject.toml                # deps, ruff + pytest config, `floorpro` entry point
uv.lock
.python-version               # 3.13
alembic.ini                   # dev-only: generating revisions
.github/workflows/ci.yml      # macOS + Windows matrix

scripts/
├── fetch_tailwind.py         # download pinned Tailwind standalone CLI for this OS
└── build_css.py              # compile input.css → app.css (--watch for dev)

src/floorpro/
├── __init__.py
├── __main__.py               # `python -m floorpro` → desktop.main()
├── desktop.py                # free port, uvicorn thread, pywebview window (only module importing webview)
├── app.py                    # create_app(settings): FastAPI factory, routers, templates, error pages
├── paths.py                  # resource_path() (dev + frozen), data_dir(), backups_dir(), logs_dir()
├── logging_setup.py          # rotating file log in logs_dir()
├── db.py                     # engine, SQLite pragmas, session dependency
├── migrate.py                # backup_if_needed() + upgrade_to_head()
├── domain/                   # pure, no DB/web imports — test-first
│   ├── money.py              # Decimal rounding, minor units, percent ⇄ basis points
│   ├── currency.py           # supported currencies (code, symbol, name)
│   ├── validation.py         # postcode, phone, VAT number, VAT rate
│   └── customers.py          # resolve_vat_breakdown(), display_name(), sort_name()
├── models/
│   ├── base.py               # DeclarativeBase, Money/Percent/UTCDateTime TypeDecorators
│   ├── settings.py           # BusinessSettings, SettingsChange
│   └── customer.py           # Customer
├── schemas/
│   ├── settings_form.py      # Pydantic form models → field errors
│   └── customer_form.py
├── services/
│   ├── settings_service.py   # get/ensure defaults, diff, confirm token, apply + history, settings_at()
│   └── customer_service.py   # create/update/search/duplicates/archive/restore/export/erase
├── routes/
│   ├── dashboard.py          # /, /healthz
│   ├── settings.py           # /settings*
│   └── customers.py          # /customers*
├── templating.py             # Jinja env + filters (money, percent, local datetime)
├── templates/
│   ├── base.html             # layout, nav, #main, #modal, #toasts
│   ├── components/           # button, field, select, checkbox, card, table, badge, empty_state, modal, toast
│   ├── errors/               # 404.html, 500.html
│   ├── dashboard.html
│   ├── settings/             # index.html, _form.html, _confirm.html, _history.html
│   └── customers/            # index.html, _results.html, detail.html, form.html, _form.html,
│                             # _vat_fields.html, _duplicates.html, _confirm_archive.html, _confirm_erase.html
├── static/
│   ├── css/input.css         # Tailwind source + @theme design tokens
│   ├── css/app.css           # generated (gitignored)
│   ├── js/app.js             # dialog opener + unsaved-changes guard
│   ├── vendor/htmx.min.js    # vendored, pinned
│   └── fonts/                # bundled font files
└── migrations/
    ├── env.py
    └── versions/0001_initial.py

tests/
├── conftest.py               # tmp data dir, app + TestClient fixtures, db session, factories
├── unit/                     # domain: money, validation, customers, settings_at
├── integration/              # routes: dashboard, settings, customers, export, erase, perf (slow)
└── migrations/               # upgrade empty + seeded DB, pre-migration backup
```

**Structure Decision**: One Python package under `src/floorpro/` (src layout, so tests run
against the installed package, as they will once frozen). The layers match Principle VI:
- `routes/` handle HTTP only
- `services/` hold the business logic and transactions
- `models/` handle persistence
- `domain/` contains pure functions

Templates, static files and migrations live inside the package so one `paths.resource_path()`
helper finds them in development and in a PyInstaller build. There's no separate front-end
project: the UI is server-rendered from the same package.

## Implementation Notes

- **Order of work**: foundations (tooling, paths, db, migrations, app shell, base template,
  components, CI) → domain functions (tests first) → settings (US2) → customers add/find
  (US1) → domestic/trade (US4) → manage/export/erase (US3).
  - US1 is P1 in the spec, but it depends only on the foundations, so it can run in parallel
    with or before US2.
  - The settings row must exist at startup because the `money` filter reads the currency.
- **Settings confirmation**: `/settings/confirm` uses a token (HMAC of the staged values plus
  the current `updated_at`) so a stale dialog can't overwrite newer settings.
- **Signing key**: created once per install and stored in the data dir.
- **Messages after a save**: see research §15. **Dialogs and downloads**: explicit
  `hx-target="#modal"`, and `hx-boost="false"` for export (research §7).
- **Customer reference**: computed from `id`, not stored (research §4).
- **Erase**: hard delete in this feature, with the `has_linked_records()` hook in place (see
  research §12).

## Next Steps (outside this feature)

- `/speckit-tasks` to produce `tasks.md` for this plan.
- **Later features**:
  - user-facing backup and restore (required before first release, Principle I)
  - PyInstaller packaging for macOS and Windows, including the universal2 / Apple Silicon
    decision
  - business details for invoices (name, address, logo, bank details)
  - jobs and site addresses, the planner, and quoting and invoicing (which use the customer
    type and VAT settings defined here)

## Complexity Tracking

No constitution violations. Nothing to justify.
