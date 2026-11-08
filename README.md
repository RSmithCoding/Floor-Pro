# FloorPro

FloorPro is a desktop app for flooring shops. It keeps customer records, and will grow into
the shop's all-in-one system: a planner for estimates and fittings, jobs and order history,
quotes and invoices, and a dashboard of upcoming appointments.

It runs on **macOS and Windows**, works **fully offline**, and keeps all the shop's data on
the shop's own computer.

## What it does today

- **Customers**: add, search (name, company, phone, postcode, email or customer number),
  edit, archive and restore, export one customer's data, and erase on request.
  Customers are **domestic** or **trade**; trade customers always get a VAT breakdown.
- **Settings**: currency (default GBP), VAT registration, VAT rate (default 20%), VAT
  number and price entry mode, with a confirmed, date-stamped change history.
- **Dashboard**: quick customer search, with space for appointments and invoices to come.

## Requirements

- macOS, or Windows 10/11 (Windows includes the WebView2 runtime the window needs)
- [uv](https://docs.astral.sh/uv/) 0.13 or newer. It installs the right Python (3.13) for
  you, so no system Python is needed.

## Set up

```bash
git clone https://github.com/RSmithCoding/Floor-Pro.git
cd Floor-Pro
uv sync                                   # Python 3.13 + locked dependencies
uv run python scripts/fetch_tailwind.py   # downloads the pinned Tailwind CSS tool
uv run python scripts/build_css.py        # builds the app's stylesheet
```

## Run

```bash
uv run python -m floorpro             # the desktop window
uv run python -m floorpro --browser   # the same app in your normal browser
```

While editing templates, keep the stylesheet up to date in a second terminal:

```bash
uv run python scripts/build_css.py --watch
```

## Where the data lives

| System | Folder |
|--------|--------|
| macOS | `~/Library/Application Support/FloorPro/` |
| Windows | `%LOCALAPPDATA%\FloorPro\` |

The folder holds the database (`floorpro.db`), automatic backups taken before every
database upgrade (`backups/`, the 10 most recent are kept) and log files (`logs/`). To start
from scratch, quit FloorPro and move the folder somewhere else.

## Checks

```bash
uv run ruff check .          # lint
uv run ruff format --check . # formatting
uv run pytest                # all tests, including a 10,000-customer search speed test
```

GitHub Actions runs the same checks on macOS and Windows for every push.

## How it's built

Python only: FastAPI, SQLAlchemy and SQLite, with Jinja templates, HTMX and Tailwind CSS
for the screens. The app runs a private local server (reachable only from this computer)
shown in a native window by pywebview. Packaging with PyInstaller comes later.

The project is planned with [Spec Kit](https://github.com/github/spec-kit). The rules every
feature follows are in [`.specify/memory/constitution.md`](.specify/memory/constitution.md),
and each feature's spec, plan and tasks live in [`specs/`](specs/). To check a feature works
end to end, follow its quickstart, for example
[`specs/001-settings-customer-records/quickstart.md`](specs/001-settings-customer-records/quickstart.md).
